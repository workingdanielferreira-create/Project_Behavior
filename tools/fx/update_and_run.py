"""
Project Behavior - FX Creator updater/launcher
Checks GitHub for changes to the 6 fx_creator files, downloads only the
ones that actually changed, then starts a local server and opens the
FX Creator in your browser.

Just double-click run_update.bat (which calls this) any time you want
to check for updates and launch the tool.
"""
import base64
import json
import os
import sys
import time
import threading
import webbrowser
import urllib.request
import http.server
import socketserver

REPO = "workingdanielferreira-create/Project_Behavior"
BRANCH = "main"
REMOTE_DIR = "tools/fx"
PORT = 8000
# No token needed: this repo's files are fetched via the public,
# unauthenticated GitHub API. That's plenty of quota (60 req/hour) for
# checking 6 files occasionally. Never commit a real token into a file
# that lives in the repo itself.

FILES = [
    "fx_creator.html",
    "fx_creator.css",
    "rig.js",
    "fx_engine.js",
    "character_creator.js",
    "main.js",
]

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(HERE, ".fx_manifest.json")


def load_manifest():
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_manifest(m):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)


def gh_get(path):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}?ref={BRANCH}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def update_files():
    manifest = load_manifest()
    changed = []
    unchanged = []
    failed = []

    for fname in FILES:
        remote_path = f"{REMOTE_DIR}/{fname}"
        try:
            info = gh_get(remote_path)
        except Exception as e:
            failed.append(f"{fname} (couldn't check: {e})")
            continue

        remote_sha = info.get("sha")
        local_sha = manifest.get(fname)

        if remote_sha == local_sha and os.path.exists(os.path.join(HERE, fname)):
            unchanged.append(fname)
            continue

        content = base64.b64decode(info["content"])
        with open(os.path.join(HERE, fname), "wb") as f:
            f.write(content)
        manifest[fname] = remote_sha
        changed.append(fname)

    save_manifest(manifest)
    return changed, unchanged, failed


def start_server_and_open():
    os.chdir(HERE)
    handler = http.server.SimpleHTTPRequestHandler
    httpd = socketserver.TCPServer(("", PORT), handler)

    def serve():
        httpd.serve_forever()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    time.sleep(0.5)
    webbrowser.open(f"http://localhost:{PORT}/fx_creator.html")
    print(f"\nServing at http://localhost:{PORT}/fx_creator.html")
    print("Leave this window open while you work. Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server.")
        httpd.shutdown()


def main():
    print("Checking for FX Creator updates...\n")
    changed, unchanged, failed = update_files()

    if changed:
        print("Updated:")
        for f in changed:
            print(f"  - {f}")
    if unchanged:
        print("Already up to date:")
        for f in unchanged:
            print(f"  - {f}")
    if failed:
        print("Could not check:")
        for f in failed:
            print(f"  - {f}")

    start_server_and_open()


if __name__ == "__main__":
    main()
