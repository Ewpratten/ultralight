import requests
import flask
import json
import yaml
from datetime import datetime
import os
from webapputils import Webapp

# Settings
static_directory = "static"
google_tracking_code=os.environ.get("GA_TRACKING_ID", "")

# Handle Github tokens
GH_ID = os.environ.get("GH_CLI_ID", "")
GH_PRIV = os.environ.get("GH_CLI_PRIV", "")

# Caching
CACHE_SECONDS = 60

# Flask app configuration
app = Webapp(__name__, static_directory=static_directory, google_tracking_code=google_tracking_code)

# Function to load the sources yml
def loadSourcesYML() -> dict:
    return yaml.load(open("sources.yml"))

# Index route
@app.flask.route("/")
def handleIndex():
    app.trackPageFetch("/")

    # Load the index
    index = open("static/index.html", "r").read()

    # Push the analytics tracking ID
    index = index.replace("{GA_TRACKING_ID}", app._google_tracking_code)

    # Build a flask response
    res = flask.make_response(index)

    # Add a caching header for Vercel
    res.headers.set('Cache-Control', f"s-maxage={CACHE_SECONDS}, stale-while-revalidate")

    return res

# Sources route
@app.flask.route("/sources.yml")
def handleSources():
    app.trackPageFetch("/sources.yml")

    # Load the sources file
    sources = open("sources.yml", "r").read()

    # Build a flask response
    res = flask.make_response(sources)

    # Add a caching header for Vercel
    res.headers.set('Cache-Control', f"s-maxage={CACHE_SECONDS}, stale-while-revalidate")

    # Set the content type
    res.headers.set('content-type', 'application/yaml')

    return res

# Sources api
@app.flask.route("/api/sources")
def handleSourcesAPI():
    app.trackAPICall("/api/sources")

    # Get the YML config
    sources = loadSourcesYML()["sources"]
    output = []

    # Parse config
    for source in sources:
        output.append(source)

    # Build a flask response
    res = flask.make_response(flask.jsonify(
        {
            "success": True,
            "sources": output
        }
    ))

    # Add a caching header for Vercel
    res.headers.set('Cache-Control', f"s-maxage={CACHE_SECONDS}, stale-while-revalidate")

    # Set the content type
    res.headers.set('content-type', 'application/json')

    return res

@app.flask.route("/api/artifact/<group>/<artifact>/versions")
def handleArtifactAPI(group, artifact):
    app.trackAPICall(f"/api/artifact/{group}/{artifact}/versions")

    # Check that the artifact exists
    repocode = ""
    fmt = ""
    for source in loadSourcesYML()["sources"]:
        if source["groupID"] == group and source["artifactID"] == artifact:
            repocode = source["github"]["owner"] + "/" + source["github"]["repository"]
            fmt = source["github"]["assetFormat"]
            break
    else:
        return "Artifact not on this server", 404

    # Get version data
    version_data = []
    raw_versions = getAllValidVersions(repocode)
    for v in raw_versions:
        version_data.append({
            "code": v,
            "timestamp": raw_versions[v]["timestamp"]
        })


    # Build a flask response
    res = flask.make_response(flask.jsonify(
        {
            "success": True,
            "versions": version_data
        }
    ))

    # Add a caching header for Vercel
    res.headers.set('Cache-Control', f"s-maxage={CACHE_SECONDS}, stale-while-revalidate")

    # Set the content type
    res.headers.set('content-type', 'application/json')

    return res

@app.flask.route("/api/artifact/<group>/<artifact>/shield")
def handleArtifactShieldAPI(group, artifact):
    app.trackAPICall(f"/api/artifact/{group}/{artifact}/shield")

    # Check that the artifact exists
    repocode = ""
    fmt = ""
    for source in loadSourcesYML()["sources"]:
        if source["groupID"] == group and source["artifactID"] == artifact:
            repocode = source["github"]["owner"] + "/" + source["github"]["repository"]
            fmt = source["github"]["assetFormat"]
            break
    else:
        return "Artifact not on this server", 404

    # Get version data
    raw_versions = getAllValidVersions(repocode)
    latest_version = list(raw_versions.keys())[0]

    # Select correct title text based on inputs
    title_text = "Ultralight"
    if "d" in flask.request.args:
        title_text = flask.request.args.get("d")
    if title_text == "127.0.0.1":
        title_text = "Ultralight"

    # Create a response
    res = flask.make_response(flask.jsonify({
        "success": True,
        "redirect": True
    }), 302)
    res.headers.set("content-type", "application/x-maven-pom+xml")
    res.headers.set("Location", f"https://img.shields.io/badge/{title_text}-{latest_version}-blue")
    return res


# Generates a fake .pom file for input data
def generatePOMForPackage(group, artifact, version) -> str:
    return f"""
<project xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd" xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <modelVersion>4.0.0</modelVersion>
  <groupId>{group}</groupId>
  <artifactId>{artifact}</artifactId>
  <version>{version}</version>
</project>
"""

def generateMavenMetadata(group, artifact, versions):

    # Get the latest timestamp
    latest_timestamp = 0
    for version in versions.values():
        if int(version["timestamp"]) > latest_timestamp:
            latest_timestamp = int(version["timestamp"])

    # Build a versions list
    generated_versions = ""
    for version in versions:
        generated_versions += f"<version>{version}</version>\n"

    latest_version = list(versions.keys())[0]

    # Build file
    return f"""
<metadata modelVersion="1.1.0">
  <groupId>{group}</groupId>
  <artifactId>{artifact}</artifactId>
  <version>{latest_version}</version>
  <versioning>
    <latest>{latest_version}</latest>
    <release>{latest_version}</release>
    <versions>
        {generated_versions}
    </versions>
    <lastUpdated>{latest_timestamp}</lastUpdated>
  </versioning>
</metadata>
"""

# Fetches a list of valid versions for a repository
def getAllValidVersions(repocode) -> dict:
    # Read from the GitHub API
    data = requests.get(f"https://api.github.com/repos/{repocode}/releases", auth=(GH_ID, GH_PRIV)).json()

    # Build version list
    output = {}
    for entry in data:
        output[entry["tag_name"].strip("v")] = {
            "url": entry["assets_url"],

            # Make a timestamp
            "timestamp": (datetime.strptime(entry["published_at"], '%Y-%m-%dT%H:%M:%SZ') - datetime(1970, 1, 1)).total_seconds(),
        }

    return output

# Fetches a JAR through GitHub
def fetchJAR(url, fmt):
    # Read from the GitHub API
    data = requests.get(url, auth=(GH_ID, GH_PRIV)).json()

    # Look for an entry in data with a matching filename
    for entry in data:
        if entry["name"] == fmt:
            res = flask.make_response(flask.jsonify({
                "success": True,
                "redirect": True
            }), 302)
            res.headers.set("content-type", "application/x-maven-pom+xml")
            res.headers.set("Location", entry["browser_download_url"])
            return res

    return flask.make_response("Not found", 404)

# Fetches github data from YML file
def getGitHubArtifactData(group, artifact) -> dict:
    for source in loadSourcesYML()["sources"]:
        if source["groupID"] == group and source["artifactID"] == artifact:
            return {
                "repository": source["github"]["owner"] + "/" + source["github"]["repository"],
                "asset_pattern": source["github"]["assetFormat"]
            }
    else:
        return None

# metadata handler
@app.flask.route("/maven/<path:group>/<artifact>/maven-metadata.xml")
def handleMetadata(group: str, artifact: str):
    """Handles generating a metadata file

    Args:
        group (str): Raw group id string
        artifact (str): Raw artifactID string

    Returns:
        flask.response: generated metadata
    """
    app.trackAPICall(f"/maven/{group}/{artifact}/maven-metadata.xml")

    # Convert group to a groupID
    groupID = ".".join(group.split("/"))

    # Get data about where to find the artifact
    artifact_data = getGitHubArtifactData(groupID, artifact)

    # Handle the artifact not being available
    if artifact_data == None:
        return "Artifact not on this server", 404

    # Get a list of valid versions for the asset
    all_versions = getAllValidVersions(artifact_data["repository"])
    
    # Build and return a response
    res = flask.make_response(generateMavenMetadata(groupID, artifact, all_versions))
    res.headers.set("content-type", "application/xml")
    res.headers.set('Cache-Control', f"s-maxage={CACHE_SECONDS}, stale-while-revalidate")
    return res

# POM handler
@app.flask.route("/maven/<path:group>/<artifact>/<version>/<file>.pom")
def handlePOM(group: str, artifact: str, version: str, file: str):
    """Generate a POM file

    Args:
        group (str): Artifact group
        artifact (str): Artifact
        version (str): Version
        file (str): Filename

    Returns:
        flask.response: Generated POM
    """

    app.trackAPICall(f"/maven/{group}/{artifact}/{version}/{file}.pom")

    # Convert group to a groupID
    groupID = ".".join(group.split("/"))

    # Build and return response
    res = flask.make_response(generatePOMForPackage(groupID, artifact, version))
    res.headers.set("content-type", "application/java-archive")
    res.headers.set('Cache-Control', f"s-maxage={CACHE_SECONDS}, stale-while-revalidate")
    return res

@app.flask.route("/maven/<path:group>/<artifact>/<version>/<file>.jar")
def handleJAR(group: str, artifact: str, version: str, file: str):
    """Get the requested JAR file

    Args:
        group (str): Artifact group
        artifact (str): Artifact
        version (str): Version
        file (str): Filename

    Returns:
        flask.response: JAR file
    """

    app.trackAPICall(f"/maven/{group}/{artifact}/{version}/{file}.jar")

    # Convert group to a groupID
    groupID = ".".join(group.split("/"))

    # Get data about where to find the artifact
    artifact_data = getGitHubArtifactData(groupID, artifact)

    # Handle the artifact not being available
    if artifact_data == None:
        return "Artifact not on this server", 404

    # Get a list of valid versions for the asset
    try:
        all_versions = getAllValidVersions(artifact_data["repository"])
    
        # Determine the URL to the actual asset
        asset_url = all_versions[version]["url"]
    except:
        return "Not found. Invalid version", 404

    # Build and return a response
    res = fetchJAR(asset_url, artifact_data["asset_pattern"].replace("{version}", version))
    res.headers.set('Cache-Control', f"s-maxage={CACHE_SECONDS}, stale-while-revalidate")
    return res

# Runner for local development
if __name__ == "__main__":
    app.flask.run(debug=True)
