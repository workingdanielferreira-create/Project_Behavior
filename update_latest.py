"""
Project Behavior - "get the latest" updater/launcher
Double-click update_latest.bat.  It:

  1. closes any running game,
  2. asks GitHub for the newest commit on main (no caching) and prints it,
     so you can see exactly which version you are getting,
  3. downloads that exact commit as one zip (codeload.github.com: no API
     rate limit, and pinned to the commit so no stale branch copy),
  4. writes every file that differs from your copy and checks each one
     after writing,
  5. keeps your own edits to characters/ files (same rule and the same
     .sync_state.json record as update_game.py),
  6. clears __pycache__ folders, files dropped character exports, and
     launches the game with the character selector open.

The commit it installed is saved in .last_update.json.  No token needed
(the repo is public); a GITHUB_TOKEN env var or .gh_token file is used for
the one API call if present.
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

REPO = "workingdanielferreira-create/Project_Behavior"
BRANCH = "main"
HERE = os.path.dirname(os.path.abspath(__file__))
SYNC_STATE = os.path.join(HERE, ".sync_state.json")
LAST_UPDATE = os.path.join(HERE, ".last_update.json")
LOCKABLE_EXTS = (".exe", ".dll", ".pyd", ".zip", ".cat")
UA = "Project_Behavior-update_latest"


# ---------------------------------------------------------------- helpers
def _token():
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


def _get(url, timeout=60, api=False, use_token=True):
    headers = {"User-Agent": UA, "Cache-Control": "no-cache", "Pragma": "no-cache"}
    if api:
        headers["Accept"] = "application/vnd.github+json"
        tok = _token() if use_token else ""
        if tok:
            headers["Authorization"] = "token " + tok
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if api and use_token and e.code == 401:
            print("NOTE: GitHub rejected your token (401); continuing without it.\n")
            return _get(url, timeout, api, use_token=False)
        raise


def _blob_sha(content):
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(content))
    h.update(content)
    return h.hexdigest()


def _local_sha(path):
    try:
        with open(path, "rb") as f:
            return _blob_sha(f.read())
    except OSError:
        return None


def _is_pycache(rel):
    return "__pycache__" in rel.split("/") or rel.endswith((".pyc", ".pyo"))


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
    except OSError:
        pass


# ---------------------------------------------------------------- steps
def close_running_game():
    """Force-close laser_cursor.pyw so its files can be overwritten."""
    if os.name != "nt":
        return []
    pids = []
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | "
             "Where-Object { $_.CommandLine -like '*laser_cursor.pyw*' } | "
             "Select-Object -ExpandProperty ProcessId"],
            stderr=subprocess.DEVNULL, text=True, timeout=20)
        pids = [int(x) for x in out.split() if x.strip().isdigit()]
    except Exception:
        return []
    killed = []
    for pid in pids:
        if pid == os.getpid():
            continue
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            killed.append(pid)
        except Exception:
            pass
    return killed


def latest_commit():
    """(sha, first line of message, date) of the newest commit on main."""
    data = json.loads(_get(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}", api=True).decode())
    msg = (data.get("commit", {}).get("message") or "").splitlines()
    date = data.get("commit", {}).get("committer", {}).get("date", "")
    return data["sha"], (msg[0] if msg else ""), date


def download_zip(ref):
    print(f"Downloading {ref[:12]} as one zip (this can take a minute)...")
    data = _get(f"https://codeload.github.com/{REPO}/zip/{ref}", timeout=600)
    print(f"Downloaded {len(data) / 1e6:.1f} MB.\n")
    return zipfile.ZipFile(io.BytesIO(data))


def apply_zip(z):
    """Write every file that differs; returns (changed, kept, locked, failed, total)."""
    state = _load_json(SYNC_STATE)
    changed, kept, locked, failed = [], [], [], []
    total = 0
    for info in z.infolist():
        if info.is_dir():
            continue
        parts = info.filename.split("/", 1)   # strip "<repo>-<ref>/"
        if len(parts) < 2 or not parts[1]:
            continue
        rel = parts[1]
        if _is_pycache(rel):
            continue
        total += 1
        content = z.read(info)
        sha = _blob_sha(content)
        path = os.path.join(HERE, *rel.split("/"))
        local = _local_sha(path)
        if local == sha:
            if rel.startswith("characters/"):
                state[rel] = sha
            continue
        # A characters/ file changed on this PC since the last update: keep it.
        if rel.startswith("characters/") and local is not None:
            rec = state.get(rel)
            if rec is not None and rec != local:
                kept.append(rel)
                continue
        try:
            os.makedirs(os.path.dirname(path) or HERE, exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)
            if _local_sha(path) != sha:
                failed.append(rel + " (written but did not match after writing)")
                continue
            changed.append(rel)
            if rel.startswith("characters/"):
                state[rel] = sha
        except OSError as e:
            if rel.lower().endswith(LOCKABLE_EXTS):
                locked.append(rel)
            else:
                failed.append(f"{rel} ({e})")
    _save_json(SYNC_STATE, state)
    return changed, kept, locked, failed, total


def purge_pycache():
    n = 0
    for root, dirs, _files in os.walk(HERE):
        if "__pycache__" in dirs:
            try:
                shutil.rmtree(os.path.join(root, "__pycache__"))
                n += 1
            except OSError:
                pass
            dirs.remove("__pycache__")
    return n


def organize_exported_characters():
    path = os.path.join(HERE, "laser", "drops.py")
    if not os.path.exists(path):
        return
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("pb_drops", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        lines = mod.organize_drops(HERE)
    except Exception as e:
        print(f"Could not organise dropped characters ({e}).")
        return
    if lines:
        print("Exported characters:")
        for line in lines:
            print(f"  - {line}")


def launch_game():
    pythonw = os.path.join(HERE, "pythonw.exe")
    game = os.path.join(HERE, "laser_cursor.pyw")
    if not os.path.exists(game):
        print("\nCould not find laser_cursor.pyw to launch.")
        return
    exe = pythonw if (os.name == "nt" and os.path.exists(pythonw)) else sys.executable
    subprocess.Popen([exe, game, "--prebattle"], cwd=HERE)
    print("\nGame launched (character selector open).")


def main():
    print("Closing any running game instance...")
    killed = close_running_game()
    if killed:
        print(f"Closed {len(killed)} game process(es).")
        time.sleep(1.0)
    print()

    prev = _load_json(LAST_UPDATE).get("sha", "")
    try:
        sha, msg, date = latest_commit()
        print(f"Latest on GitHub: {sha[:7]}  {date}\n  \"{msg}\"\n")
    except Exception as e:
        # API refused (rate limit / outage): the branch zip still works.
        print(f"Could not ask GitHub for the latest commit ({e}).\n"
              f"Falling back to the '{BRANCH}' branch zip.\n")
        sha, msg, date = BRANCH, "", ""
    if prev:
        print(f"Last installed by this updater: {prev[:7]}\n")

    try:
        z = download_zip(sha)
    except Exception as e:
        print(f"Download failed ({e}). Launching the version you already have.")
        launch_game()
        return
    with z:
        changed, kept, locked, failed, total = apply_zip(z)

    print(f"Checked {total} files.")
    if changed:
        print(f"Updated {len(changed)} file(s):")
        for f in changed:
            print(f"  - {f}")
    else:
        print("Everything already matched the latest version.")
    if kept:
        print("Kept your local character edits (not overwritten):")
        for f in kept:
            print(f"  - {f}")
    if locked:
        print("Skipped, file in use (close everything and run again):")
        for f in locked:
            print(f"  - {f}")
    if failed:
        print("FAILED:")
        for f in failed:
            print(f"  - {f}")
    if any(f.startswith("tools/fx/studio/") for f in changed):
        print("\nFX Studio files changed: if FX Studio is open, press Ctrl+F5 in it.")
    if sha != BRANCH and not failed:
        _save_json(LAST_UPDATE, {"sha": sha, "message": msg, "date": date})

    print()
    organize_exported_characters()
    n = purge_pycache()
    if n:
        print(f"Cleared {n} __pycache__ folder(s).")
    launch_game()


if __name__ == "__main__":
    main()
