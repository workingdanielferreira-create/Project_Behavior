"""
Project Behavior - whole-repo updater/launcher
Compares EVERY tracked file in the GitHub repo against your local copy,
downloads only the ones that actually changed, then launches the game
(same as run.bat).

Just double-click update_game.bat any time you want to pull the latest
changes and play.

How change detection works
--------------------------
One request fetches the full repo tree (every tracked file + its git blob
SHA).  For each local file we compute the same git blob SHA
(sha1 of b"blob <size>\\0" + content) — if it matches, the file is already
up to date and nothing is downloaded.  No manifest file needed: detection
is self-healing even if you edit or delete local files by hand.

No token needed: this repo is public and files are fetched via the
unauthenticated GitHub API (60 req/hour — 1 for the tree + 1 per changed
file, which is plenty).  Never commit a real token into a file that lives
in the repo itself.
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.request

REPO = "workingdanielferreira-create/Project_Behavior"
BRANCH = "main"

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.basename(os.path.abspath(__file__))

# Big binary blobs (embedded Python runtime) rarely change and may be locked
# while anything Python is running.  They're still checked like everything
# else, but a failed write on these is reported as "locked", not an error.
LOCKABLE_EXTS = (".exe", ".dll", ".pyd", ".zip", ".cat")


def _token():
    """Optional auth for higher rate limits: GITHUB_TOKEN env var, or a
    one-line .gh_token file next to this script.  The file is NOT tracked
    by the repo — never commit a real token into a repo file."""
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    p = os.path.join(HERE, ".gh_token")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            pass
    return ""


def gh_json(url):
    headers = {"Accept": "application/vnd.github+json"}
    tok = _token()
    if tok:
        headers["Authorization"] = "token " + tok
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def remote_tree():
    """Every tracked blob in the repo: [(path, sha, size), ...]."""
    data = gh_json(f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}"
                   "?recursive=1")
    if data.get("truncated"):
        print("WARNING: repo tree was truncated by GitHub; "
              "some files may not be checked.")
    return [(t["path"], t["sha"], t.get("size", 0))
            for t in data.get("tree", []) if t["type"] == "blob"]


def local_blob_sha(path):
    """Git blob SHA of a local file (matches the SHAs in the remote tree)."""
    try:
        with open(path, "rb") as f:
            content = f.read()
    except OSError:
        return None
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(content))
    h.update(content)
    return h.hexdigest()


def download_blob(sha):
    data = gh_json(f"https://api.github.com/repos/{REPO}/git/blobs/{sha}")
    return base64.b64decode(data["content"])


def update_files():
    changed, failed, locked = [], [], []
    self_updated = False

    tree = remote_tree()
    print(f"Checking {len(tree)} tracked files...\n")

    for rel_path, sha, _size in tree:
        local_path = os.path.join(HERE, *rel_path.split("/"))
        if local_blob_sha(local_path) == sha:
            continue  # up to date
        try:
            content = download_blob(sha)
            os.makedirs(os.path.dirname(local_path) or HERE, exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(content)
            changed.append(rel_path)
            if rel_path == SELF:
                self_updated = True
        except OSError as e:
            if rel_path.lower().endswith(LOCKABLE_EXTS):
                locked.append(rel_path)
            else:
                failed.append(f"{rel_path} ({e})")
        except Exception as e:
            failed.append(f"{rel_path} ({e})")

    return changed, failed, locked, self_updated


def launch_game():
    """Start the game exactly like run.bat: pythonw.exe laser_cursor.pyw."""
    pythonw = os.path.join(HERE, "pythonw.exe")
    game = os.path.join(HERE, "laser_cursor.pyw")
    if os.name == "nt" and os.path.exists(pythonw) and os.path.exists(game):
        subprocess.Popen([pythonw, game], cwd=HERE)
        print("\nGame launched.")
    elif os.path.exists(game):
        subprocess.Popen([sys.executable, game], cwd=HERE)
        print("\nGame launched.")
    else:
        print("\nCould not find laser_cursor.pyw to launch.")


def main():
    print("Checking GitHub for updates...\n")
    try:
        changed, failed, locked, self_updated = update_files()
    except Exception as e:
        print(f"Could not reach GitHub ({e}). Launching current version.")
        launch_game()
        return

    if changed:
        print("Updated:")
        for f in changed:
            print(f"  - {f}")
    else:
        print("Everything already up to date.")
    if locked:
        print("Skipped (file in use — close the game and re-run to update):")
        for f in locked:
            print(f"  - {f}")
    if failed:
        print("Failed:")
        for f in failed:
            print(f"  - {f}")

    if self_updated:
        print("\nNOTE: update_game.py itself was updated — "
              "the new version will be used next run.")

    launch_game()


if __name__ == "__main__":
    main()
