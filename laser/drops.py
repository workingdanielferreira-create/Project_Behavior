"""Organise exported characters dropped into the game folder.

You export a character in two parts:
  * Rig Forge -> ``<name>.zip`` (``<name>/character.json`` + ``<action>_NN.png``
    keyframes), or the same files unzipped into a ``<name>/`` folder;
  * FX Studio -> ``<name>.fxkit.json`` (the character's FX, anchors, entry
    points, paths and action settings).

Upload either or both to the repo's main branch: to the top level, or into
a ``drop/`` folder.  ``update_game.bat`` downloads them, and this module
then files them where the game reads them:

    characters/<name>/character.json
    characters/<name>/<action>_NN.png
    characters/<name>/<name>.fxkit.json

The dropped copies are left alone (they are tracked files, so the updater
would only fetch them again).  Organising is idempotent: a file is written
only when its bytes differ, so unchanged drops cost nothing on later runs.
A new character package also removes old keyframes of that character that
the new export no longer has.

Called by update_game.py after it syncs, and by the game at start-up.
"""
import json
import os
import re
import time
import zipfile

FRAME_RE = re.compile(r"^(.+)_(\d+)\.png$", re.IGNORECASE)
SKIP_DIRS = {"characters", "laser", "tools", "captures", "scripts", "v2", "drop",
             ".git", "__pycache__", ".github"}


def _slug(name):
    s = re.sub(r"[^a-z0-9_-]+", "_", str(name or "").lower()).strip("_")
    return s or "character"


def _write(path, data, log):
    """Write bytes only when they differ; returns True when written."""
    try:
        with open(path, "rb") as f:
            if f.read() == data:
                return False
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    log.append(os.path.relpath(path, os.path.dirname(os.path.dirname(path))))
    return True


def _is_pkg(obj):
    return isinstance(obj, dict) and obj.get("format") == "pb_char_pkg" and isinstance(obj.get("actions"), dict)


def _is_fxkit(obj):
    return isinstance(obj, dict) and obj.get("format") == "pb_fxkit" and obj.get("character")


def _install_package(root, man, read_file, log):
    """man: parsed character.json; read_file(name) -> bytes or None."""
    name = _slug(man.get("name"))
    dest = os.path.join(root, "characters", name)
    wanted = []
    for act in man["actions"].values():
        for fn in act.get("frames") or []:
            if fn not in wanted:
                wanted.append(fn)
    written = []
    missing = []
    for fn in wanted:
        data = read_file(fn)
        if data is None:
            missing.append(fn)
            continue
        if _write(os.path.join(dest, fn), data, written):
            pass
    _write(os.path.join(dest, "character.json"),
           json.dumps(man, indent=1).encode("utf-8"), written)
    # Keyframes of this character that the new export no longer has.
    removed = []
    if not missing and os.path.isdir(dest):
        keep = set(wanted)
        for fn in os.listdir(dest):
            if FRAME_RE.match(fn) and fn not in keep:
                try:
                    os.remove(os.path.join(dest, fn))
                    removed.append(fn)
                except OSError:
                    pass
    if written or removed:
        log.append(f"characters/{name}/: {len(written)} file(s) updated"
                   + (f", {len(removed)} old frame(s) removed" if removed else ""))
    if missing:
        log.append(f"characters/{name}/: WARNING {len(missing)} frame(s) listed in "
                   f"character.json were not in the drop (e.g. {missing[0]})")
    return name


def _packages_in_zip(path):
    """[(man, read_file, stamp)] for every pb_char_pkg inside a zip; stamp =
    the export time recorded in the zip."""
    out = []
    try:
        z = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return out
    with z:
        names = z.namelist()
        for n in names:
            if n.replace("\\", "/").split("/")[-1] != "character.json":
                continue
            try:
                man = json.loads(z.read(n).decode("utf-8-sig"))
            except Exception:
                continue
            if not _is_pkg(man):
                continue
            base = n[: -len("character.json")]
            blobs = {}
            for m in names:
                if m.startswith(base) and "/" not in m[len(base):]:
                    blobs[m[len(base):]] = z.read(m)
            try:
                stamp = time.mktime(z.getinfo(n).date_time + (0, 0, -1))
            except Exception:
                stamp = 0
            out.append((man, blobs.get, stamp))
    return out


def _package_in_dir(d):
    p = os.path.join(d, "character.json")
    try:
        with open(p, "r", encoding="utf-8-sig") as f:
            man = json.load(f)
    except (OSError, ValueError):
        return None
    if not _is_pkg(man):
        return None

    def read_file(fn):
        try:
            with open(os.path.join(d, fn), "rb") as f:
                return f.read()
        except OSError:
            return None
    return man, read_file, os.path.getmtime(p)


def _candidate_dirs(root):
    """Where drops can sit: the top level, drop/ (and its sub-folders), and
    any top-level folder holding a Rig Forge character.json."""
    out = [root]
    drop = os.path.join(root, "drop")
    if os.path.isdir(drop):
        for r, dirs, _files in os.walk(drop):
            dirs.sort()
            out.append(r)
    for n in sorted(os.listdir(root)):
        p = os.path.join(root, n)
        if os.path.isdir(p) and n.lower() not in SKIP_DIRS and not n.startswith("."):
            out.append(p)
    return out


def organize_drops(root):
    """File every dropped character package and FX file under characters/.
    Returns a list of human-readable lines describing what changed.  When
    one character was dropped more than once, the newest export wins (and
    the log says so: delete the old drop from the repo)."""
    log = []
    try:
        dirs = _candidate_dirs(root)
    except OSError:
        return log
    pkgs, fxs = {}, {}   # name -> [(stamp, label, payload)]
    for d in dirs:
        pkg = _package_in_dir(d)   # an unzipped folder, or loose files at the top level
        if pkg:
            pkgs.setdefault(_slug(pkg[0].get("name")), []).append((pkg[2], os.path.relpath(d, root), pkg))
        try:
            entries = sorted(os.listdir(d))
        except OSError:
            continue
        for n in entries:
            p = os.path.join(d, n)
            if not os.path.isfile(p):
                continue
            low = n.lower()
            if low.endswith(".zip") and low != "python314.zip":
                for man, read_file, stamp in _packages_in_zip(p):
                    pkgs.setdefault(_slug(man.get("name")), []).append((stamp, os.path.relpath(p, root), (man, read_file)))
            elif low.endswith(".json") and low != "character.json":
                # FX Studio files are recognised by their content, not their
                # name: browsers rename repeat downloads ("rapid.fxkit (2).json").
                try:
                    with open(p, "rb") as f:
                        raw = f.read()
                    obj = json.loads(raw.decode("utf-8-sig"))
                except (OSError, ValueError):
                    continue
                if _is_fxkit(obj):
                    fxs.setdefault(_slug(obj["character"]), []).append((os.path.getmtime(p), os.path.relpath(p, root), raw))
    for name in sorted(pkgs):
        c = sorted(pkgs[name], key=lambda x: (x[0], x[1]))
        if len(c) > 1:
            log.append(f"NOTE: {len(c)} exports of {name} dropped ({', '.join(x[1] for x in c)}); "
                       f"using the newest, {c[-1][1]}. Delete the others from the repo.")
        # Never overwrite newer local work: a Rig Forge export or FX Studio
        # save made straight into characters/<name>/ is newer than the drop.
        src = os.path.join(root, c[-1][1])
        src = os.path.join(src, "character.json") if os.path.isdir(src) else src
        dest_cj = os.path.join(root, "characters", name, "character.json")
        if os.path.exists(dest_cj) and os.path.getmtime(dest_cj) > os.path.getmtime(src) + 1:
            continue
        _install_package(root, c[-1][2][0], c[-1][2][1], log)
    # FX files last, so they land in the folder their package just made.
    for name in sorted(fxs):
        c = sorted(fxs[name], key=lambda x: (x[0], x[1]))
        if len(c) > 1:
            log.append(f"NOTE: {len(c)} FX files for {name} dropped ({', '.join(x[1] for x in c)}); "
                       f"using {c[-1][1]}. Delete the others from the repo.")
        written = []
        dest_fx = os.path.join(root, "characters", name, name + ".fxkit.json")
        if os.path.exists(dest_fx) and os.path.getmtime(dest_fx) > os.path.getmtime(os.path.join(root, c[-1][1])) + 1:
            continue   # a newer FX Studio save is already in the character folder
        _write(dest_fx, c[-1][2], written)
        if written:
            log.append(f"characters/{name}/: FX file updated ({c[-1][1]})")
    return log
