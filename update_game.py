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

No token needed: this repo is public.  The whole check costs 2 GitHub API
requests (latest commit + file tree); every changed file is then downloaded
from raw.githubusercontent.com pinned to that commit (not counted against
the API rate limit) and verified against its git blob SHA before it is
written, falling back to the API blob endpoint if the raw download fails.
An optional token (GITHUB_TOKEN env var or a .gh_token file next to this
script) only raises the API limit; if GitHub rejects it (HTTP 401 — revoked,
expired, stale or mis-pasted) the updater says so and carries on without it
instead of aborting.  Never commit a real token into the repo itself.
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = "workingdanielferreira-create/Project_Behavior"
BRANCH = "main"
# Optional auth for higher rate limits (5000 req/hour instead of 60):
# GITHUB_TOKEN env var, or a one-line .gh_token file next to this script.
# GitHub's push protection rejects any commit containing a raw token, so
# the token can never be hardcoded here — it must live in a local,
# untracked file or env var instead.

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.basename(os.path.abspath(__file__))

# Big binary blobs (embedded Python runtime) rarely change and may be locked
# while anything Python is running.  They're still checked like everything
# else, but a failed write on these is reported as "locked", not an error.
LOCKABLE_EXTS = (".exe", ".dll", ".pyd", ".zip", ".cat")

# Compiled bytecode cache should never be synced or trusted: depending on the
# interpreter's pyc invalidation mode, a stale cached .pyc can get loaded
# instead of freshly-compiled source, silently masking real code changes
# (this bit us once — see CLAUDE.md). Never download these even if one
# somehow ends up committed again, and always wipe local caches before a run
# so every launch recompiles fresh from the just-synced source.
def _is_pycache_path(rel_path):
    parts = rel_path.replace("\\", "/").split("/")
    return "__pycache__" in parts or rel_path.endswith((".pyc", ".pyo"))


def purge_local_pycache():
    """Delete every __pycache__ directory under HERE so the interpreter is
    forced to recompile from the source we just synced, rather than
    potentially trusting some leftover stale bytecode."""
    removed = []
    for root, dirs, _files in os.walk(HERE):
        if "__pycache__" in dirs:
            target = os.path.join(root, "__pycache__")
            try:
                import shutil
                shutil.rmtree(target)
                removed.append(os.path.relpath(target, HERE))
                dirs.remove("__pycache__")
            except OSError:
                pass
    return removed


def _token_source():
    """Where _token() will read from (never the token itself)."""
    if os.environ.get("GITHUB_TOKEN", "").strip():
        return "the GITHUB_TOKEN environment variable"
    if os.path.exists(os.path.join(HERE, ".gh_token")):
        return "the .gh_token file next to update_game.py"
    return "no token"


def _token():
    """Optional auth for higher rate limits: GITHUB_TOKEN env var, or a
    one-line .gh_token file next to this script.  The file is NOT tracked
    by the repo — never commit a real token into a file that lives in
    the repo itself.  Read with utf-8-sig so a Notepad-saved BOM can't
    corrupt the header."""
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    p = os.path.join(HERE, ".gh_token")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                return f.read().strip()
        except OSError:
            pass
    return ""


# Set once GitHub answers 401 to our token: every later call goes out
# unauthenticated (the repo is public, so nothing needs a token).
_TOKEN_REJECTED = False


def gh_json(url):
    global _TOKEN_REJECTED
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "Project_Behavior-updater"}
    tok = "" if _TOKEN_REJECTED else _token()
    if tok:
        headers["Authorization"] = "token " + tok
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401 and tok:
            _TOKEN_REJECTED = True
            print(f"NOTE: GitHub rejected the token from {_token_source()} "
                  "(401 - revoked, expired or wrong). Continuing without it; "
                  "replace or delete it to silence this.\n")
            return gh_json(url)
        raise


def head_commit():
    """SHA of the branch's latest commit (one API request)."""
    return gh_json(f"https://api.github.com/repos/{REPO}/git/ref/heads/"
                   f"{BRANCH}")["object"]["sha"]


def remote_tree(commit):
    """Every tracked blob at `commit`: [(path, sha, size), ...]."""
    data = gh_json(f"https://api.github.com/repos/{REPO}/git/trees/{commit}"
                   "?recursive=1")
    if data.get("truncated"):
        print("WARNING: repo tree was truncated by GitHub; "
              "some files may not be checked.")
    return [(t["path"], t["sha"], t.get("size", 0))
            for t in data.get("tree", []) if t["type"] == "blob"]


def _git_blob_sha(content):
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(content))
    h.update(content)
    return h.hexdigest()


def local_blob_sha(path):
    """Git blob SHA of a local file (matches the SHAs in the remote tree)."""
    try:
        with open(path, "rb") as f:
            content = f.read()
    except OSError:
        return None
    return _git_blob_sha(content)


def download_blob(sha):
    data = gh_json(f"https://api.github.com/repos/{REPO}/git/blobs/{sha}")
    return base64.b64decode(data["content"])


def download_file(commit, rel_path, sha):
    """Fetch one file.  Primary: raw.githubusercontent.com pinned to the
    commit (not counted against the API rate limit), verified against the
    tree's blob SHA.  Fallback: the API blob endpoint."""
    url = (f"https://raw.githubusercontent.com/{REPO}/{commit}/"
           + urllib.parse.quote(rel_path))
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Project_Behavior-updater"})
        with urllib.request.urlopen(req, timeout=60) as r:
            content = r.read()
        if _git_blob_sha(content) == sha:
            return content
    except Exception:
        pass
    return download_blob(sha)


def update_files():
    changed, failed, locked = [], [], []
    self_updated = False

    commit = head_commit()
    tree = remote_tree(commit)
    print(f"Checking {len(tree)} tracked files (commit {commit[:7]})...\n")

    for rel_path, sha, _size in tree:
        if _is_pycache_path(rel_path):
            continue  # never sync/trust compiled bytecode cache
        local_path = os.path.join(HERE, *rel_path.split("/"))
        if local_blob_sha(local_path) == sha:
            continue  # up to date
        try:
            content = download_file(commit, rel_path, sha)
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


def _pids_running_game():
    """PIDs of any process whose command line mentions laser_cursor.pyw.
    Tries wmic first (older Windows), falls back to PowerShell's
    Get-CimInstance (wmic was dropped by default in newer Windows builds).
    Best-effort: returns [] if neither tool is available rather than
    raising, so a locked-down machine still falls through to a normal
    update-without-closing run."""
    my_pid = os.getpid()
    pids = []

    try:
        out = subprocess.check_output(
            ["wmic", "process", "where",
             "CommandLine like '%laser_cursor.pyw%'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            stderr=subprocess.DEVNULL, text=True, timeout=15)
        for line in out.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("node,"):
                continue
            pid_str = line.split(",")[-1].strip()
            if pid_str.isdigit():
                pids.append(int(pid_str))
    except Exception:
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process | "
                 "Where-Object { $_.CommandLine -like '*laser_cursor.pyw*' } | "
                 "Select-Object -ExpandProperty ProcessId"],
                stderr=subprocess.DEVNULL, text=True, timeout=15)
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
        except Exception:
            return []

    return [p for p in pids if p != my_pid]


def close_running_game():
    """Force-close any running instance(s) of the game so locked engine/
    binary files can be overwritten cleanly before we pull. Windows-only
    (this build only ships as a Windows portable folder) and best-effort —
    a machine without wmic/PowerShell just skips this step silently and
    falls through to the normal update (previous behaviour)."""
    if os.name != "nt":
        return []
    killed = []
    for pid in _pids_running_game():
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10)
            killed.append(pid)
        except Exception:
            pass
    return killed


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
    print("Closing any running game instance...\n")
    killed = close_running_game()
    if killed:
        print(f"Closed {len(killed)} running game process(es): {killed}\n")
        time.sleep(1.0)  # give Windows a moment to release file handles
    else:
        print("No running game instance found (or couldn't check).\n")

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
        print("Skipped (still in use — try re-running the updater):")
        for f in locked:
            print(f"  - {f}")
    if failed:
        print("Failed:")
        for f in failed:
            print(f"  - {f}")

    if self_updated:
        print("\nNOTE: update_game.py itself was updated — "
              "the new version will be used next run.")

    purged = purge_local_pycache()
    if purged:
        print(f"\nCleared {len(purged)} local __pycache__ folder(s) so the "
              f"game recompiles fresh from the updated source:")
        for p in purged:
            print(f"  - {p}")

    launch_game()


if __name__ == "__main__":
    main()
