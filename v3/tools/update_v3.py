"""
Project Behavior V3 - updater
Double-click v3\\update_v3.bat (or "Update V3.bat" in the game folder).  It:

  1. asks GitHub for the newest commit on main (no caching) and prints it,
  2. downloads that exact commit as one zip (codeload.github.com: no API
     rate limit, pinned to the commit so no stale branch copy),
  3. writes only the V3 parts that differ from your copy, checking each file
     after writing:
       - v3/                 the 3D game + Rig Forge 3D (v3/tools/rigforge3d.html) + FX Studio 3D
                             (v3/tools/fxstudio3d.html) + World Studio 3D (v3/tools/worldstudio3d.html)
       - Rig Forge 3D.bat    the Rig Forge 3D launcher
       - FX Studio 3D.bat    the FX Studio 3D launcher
       - World Studio 3D.bat the World Studio 3D launcher (the little planet's settings)
       - Update V3.bat       this updater's launcher in the game folder
       - tools/fx/studio/    FX Studio's runtime (V3 plays every FX with it)
       - characters/         the characters V3 packs into its kits
     The 2D game files are left alone (update_latest.bat updates those),
  4. keeps your own edits to characters/ files, e.g. a .glb you saved from
     Rig Forge 3D (same rule and the same .sync_state.json record as
     update_latest.py / update_game.py),
  5. then asks what to open: 1 = V3 game, 2 = Rig Forge 3D, 3 = FX Studio 3D, 4 = World Studio 3D,
     Enter = nothing.

The commit it installed is saved in .last_update_v3.json in the game folder.
No token needed (the repo is public); a GITHUB_TOKEN env var or .gh_token
file is used for the one API call if present.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile

REPO = "workingdanielferreira-create/Project_Behavior"
BRANCH = "main"
TOOLS = os.path.dirname(os.path.abspath(__file__))
V3 = os.path.dirname(TOOLS)
ROOT = os.path.dirname(V3)
SYNC_STATE = os.path.join(ROOT, ".sync_state.json")
LAST_UPDATE = os.path.join(ROOT, ".last_update_v3.json")
UA = "Project_Behavior-update_v3"

# What the V3 updater writes (repo paths).  Folders end in "/".
V3_PATHS = (
    "v3/",
    "Rig Forge 3D.bat",
    "FX Studio 3D.bat",
    "World Studio 3D.bat",
    "Update V3.bat",
    "tools/fx/studio/",
    "characters/",
)
RIGFORGE3D = ("v3/tools/rigforge3d.html", "v3/lib/", "Rig Forge 3D.bat")
FXSTUDIO3D = ("v3/tools/fxstudio3d.html", "v3/js/fx3d.js", "v3/lib/", "FX Studio 3D.bat")
WORLDSTUDIO3D = ("v3/tools/worldstudio3d.html", "v3/js/world3d.js", "World Studio 3D.bat")
# Never written: local-only files (also gitignored, listed here to be safe).
GENERATED = re.compile(r"characters/ual_swordsman/(ual_moves(_drafts)?|paragon/[^/]+)\.glb$")
SKIP = ("v3/.window-profile/", "v3/data/kits.gen.js", "v3/data/world.gen.js", "characters/live_view.json",
        "characters/_baked/")


# ---------------------------------------------------------------- helpers
def _token():
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    p = os.path.join(ROOT, ".gh_token")
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


def _matches(rel, paths):
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in paths)


def _wanted(rel):
    if "__pycache__" in rel.split("/") or rel.endswith((".pyc", ".pyo")):
        return False
    return _matches(rel, V3_PATHS) and not _matches(rel, SKIP)


# ---------------------------------------------------------------- steps
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
    """Write every V3 file that differs; returns (changed, kept, failed, total)."""
    state = _load_json(SYNC_STATE)
    changed, kept, failed = [], [], []
    total = 0
    for info in z.infolist():
        if info.is_dir():
            continue
        parts = info.filename.split("/", 1)   # strip "<repo>-<ref>/"
        if len(parts) < 2 or not parts[1]:
            continue
        rel = parts[1]
        if not _wanted(rel):
            continue
        total += 1
        content = z.read(info)
        sha = _blob_sha(content)
        path = os.path.join(ROOT, *rel.split("/"))
        local = _local_sha(path)
        if local == sha:
            if rel.startswith("characters/"):
                state[rel] = sha
            continue
        # A characters/ file changed on this PC since the last update: keep it. Generated move packs
        # (ual_moves*.glb, built by move_library.py) are never edited by hand: always take the new one.
        if rel.startswith("characters/") and local is not None and not GENERATED.search(rel):
            rec = state.get(rel)
            if rec is not None and rec != local:
                kept.append(rel)
                continue
        try:
            os.makedirs(os.path.dirname(path) or ROOT, exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)
            if _local_sha(path) != sha:
                failed.append(rel + " (written but did not match after writing)")
                continue
            changed.append(rel)
            if rel.startswith("characters/"):
                state[rel] = sha
        except OSError as e:
            failed.append(f"{rel} ({e})")
    _save_json(SYNC_STATE, state)
    return changed, kept, failed, total


def _open_bat(name):
    path = os.path.join(ROOT, *name.split("/"))
    if not os.path.exists(path):
        print(f"Could not find {name}.")
        return
    if os.name == "nt":
        os.startfile(path)                    # runs the .bat in its own window
    else:
        subprocess.Popen(["sh", path], cwd=os.path.dirname(path))


def ask_launch():
    print("\nOpen now?  1 = V3 game   2 = Rig Forge 3D   3 = FX Studio 3D   4 = World Studio 3D   Enter = nothing")
    try:
        pick = input("> ").strip()
    except EOFError:
        pick = ""
    if pick == "1":
        _open_bat("v3/run_v3.bat")
        print("V3 game opening.")
    elif pick == "2":
        _open_bat("Rig Forge 3D.bat")
        print("Rig Forge 3D opening.")
    elif pick == "3":
        _open_bat("FX Studio 3D.bat")
        print("FX Studio 3D opening.")
    elif pick == "4":
        _open_bat("World Studio 3D.bat")
        print("World Studio 3D opening.")


def main():
    print("Project Behavior V3 updater\n")
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
        print(f"Download failed ({e}). Your current V3 files are unchanged.")
        ask_launch()
        return
    with z:
        changed, kept, failed, total = apply_zip(z)

    print(f"Checked {total} V3 files.")
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
    if failed:
        print("FAILED:")
        for f in failed:
            print(f"  - {f}")
    if any(_matches(f, RIGFORGE3D) for f in changed):
        print("\nRig Forge 3D updated: if it is open, close it and open it again.")
    if any(_matches(f, FXSTUDIO3D) for f in changed) or any(f.startswith("tools/fx/studio/") for f in changed):
        print("FX Studio 3D updated: if it is open, press Ctrl+F5 in it.")
    if any(_matches(f, WORLDSTUDIO3D) for f in changed):
        print("World Studio 3D updated: if it is open, press Ctrl+F5 in it.")
    if any(f.startswith("tools/fx/studio/") for f in changed):
        print("FX Studio files changed: if FX Studio is open, press Ctrl+F5 in it.")
    if any(f.startswith("v3/") for f in changed):
        print("V3 game files changed: if the V3 window is open, press Ctrl+F5 in it (or reopen it).")
    if sha != BRANCH and not failed:
        _save_json(LAST_UPDATE, {"sha": sha, "message": msg, "date": date})

    ask_launch()


if __name__ == "__main__":
    main()
