"""Export every existing character as an FX Studio package.

    python tools/fx/export_packages.py            (from the game folder)

Writes fx_packages/<name>/character.json + <action>_NN.png for the built-in
runner and swordsman and for every characters/<name>.json fighter, in the
Rig Forge package format (pb_char_pkg) that FX Studio opens with
"Open character folder...".

The frames are made by the game's own code, so they look exactly like the
fighter on screen: the same source PNGs, background removal, per-set size
ratios and tints (laser/assets.py, laser/characters.py), or the same rig
drawing for skeleton characters.  They are rendered EXPORT_MULT times the
in-game size so anchors can be placed precisely; FX Studio and the game
size every package by its stand height, so the resolution does not change
how big the fighter is.  Each character's frames share one canvas with the
figure position at its centre, as the game draws them.

Timing is the game's: frames per tick from MODE_CONFIGS / the JSON actions.
Skeleton characters get every joint as an anchor (hip, chest, hands, weapon
tip, ...), per frame; image characters get the same anchor names with no
positions yet, ready to place in the Studio.

fx_packages/ is not read by the game, so exporting changes nothing in play.
To switch a character over once its FX are done, put its whole folder
(frames, character.json and <name>.fxkit.json) into drop/ and run
update_game.bat, as with rapid.
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import Qt                                        # noqa: E402
from PyQt5.QtGui import QPixmap, QPainter                          # noqa: E402
from PyQt5.QtWidgets import QApplication                           # noqa: E402

EXPORT_MULT = 4          # frames are drawn this many times the in-game size
OUT_DIR = os.path.join(HERE, "fx_packages")

# The Rig Forge joint names FX Studio uses (as in characters/rapid).
ANCHOR_LABELS = {"hip": "hip centre", "chest": "chest", "neck": "neck", "head": "head",
                 "shB": "shoulder base", "shL": "far shoulder", "shR": "near shoulder",
                 "elL": "far elbow", "elR": "near elbow", "haL": "far hand", "haR": "near hand",
                 "hpL": "far hip", "hpR": "near hip", "knL": "far knee", "knR": "near knee",
                 "ftL": "far foot", "ftR": "near foot", "wtip": "weapon tip", "root": "above head"}
# laser/characters.py rig_joints name -> anchor id
RIG_TO_ANCHOR = {"hip": "hip", "chest": "chest", "l_shoulder": "shL", "r_shoulder": "shR",
                 "l_elbow": "elL", "r_elbow": "elR", "l_hand": "haL", "r_hand": "haR",
                 "l_hip": "hpL", "r_hip": "hpR", "l_knee": "knL", "r_knee": "knR",
                 "l_foot": "ftL", "r_foot": "ftR"}
# Game frame set -> package action name
SET_TO_ACTION = {"run": "run", "idle": "idle", "slash": "attack_normal", "slide": "defend"}
TRIGGERS = {"idle": "always", "run": "moving", "attack_normal": "in_range", "defend": "incoming",
            "attack_special": "charge_full", "ultimate": "ultimate_ready"}


def _pad(frames):
    """Put every frame on one canvas, centred like Figure.draw centres it."""
    w = max(p.width() for p in frames)
    h = max(p.height() for p in frames)
    w += w % 2
    h += h % 2
    out = []
    for p in frames:
        c = QPixmap(w, h)
        c.fill(Qt.transparent)
        qp = QPainter(c)
        qp.drawPixmap(w // 2 - p.width() // 2, h // 2 - p.height() // 2, p)
        qp.end()
        out.append(c)
    return out, (w, h)


def _sprite_sets(name, sets, remove_bg, tint=None):
    """sets: [(action, files, game_scale)] -> {action: [QPixmap]} at EXPORT_MULT."""
    from laser import assets, characters
    out = {}
    for action, files, sc in sets:
        frames, _fl = assets._load_frames(files, sc * EXPORT_MULT, remove_bg)
        if not frames:
            continue
        if tint:
            kind, colour = tint
            fn = characters._tint_pixmap if kind == "flat" else characters._tint_pixmap_colorize
            frames = [fn(p, colour) for p in frames]
        out[action] = frames
    return out


def _json_action_ms(char, action, n, fallback_ticks):
    """frame_ms the game plays this JSON action at (characters._anim_ticks)."""
    from laser import characters, config
    a = (char.get("actions") or {}).get(action)
    if a and "keyframes" not in a:
        a = dict(a, keyframes=[{}] * n)
    return characters._anim_ticks(a, fallback_ticks) * config.TICK_MS


def builtin_sources():
    """(key, meta, {action: [QPixmap]}, {action: frame_ms}, anchors) for runner / swordsman."""
    from laser import config
    d = HERE
    import glob

    def g(p):
        from laser.assets import natural_key
        return sorted(glob.glob(os.path.join(d, p)), key=natural_key)
    T = config.TARGET_HEAD_PX
    mc = config.MODE_CONFIGS
    out = []
    frames = _sprite_sets("runner", [
        ("run", g("Picture*.png"), T / config.RUN_SRC_HEAD),
        ("idle", g("standing*.png"), T / config.IDLE_SRC_HEAD),
        ("defend", [os.path.join(d, "slidingback.png"), os.path.join(d, "slidingback2.png")], T / config.SLIDE_SRC_HEAD),
    ], True)
    ms = {"run": mc["runner"]["anim_speed"] * config.TICK_MS, "idle": mc["runner"]["idle_anim_speed"] * config.TICK_MS,
          "defend": 150.0}
    out.append(("runner", dict(display_name="Runner", archetype="shooter",
                               predicates={"can_shoot": True, "uses_melee": False, "retreats": True, "charges_full": False},
                               movement={},
                               stats=dict(max_hp=mc["runner"]["max_hp"], chase_speed=mc["runner"]["chase_speed"],
                                          follow_speed=mc["runner"]["follow_speed"], scale=1.0,
                                          basic_attack_radius=mc["runner"]["basic_attack_radius"]),
                               palette={"body": "#00ffff", "accent": "#0000ff"}), frames, ms, None))   # palette.PAL_BLUE
    sword = [("run", g("swordrun*.png"), T / config.SWORD_RUN_SRC_HEAD),
             ("idle", g("swordstanding*.png"), T / config.SWORD_IDLE_SRC_HEAD),
             ("attack_normal", g("slash*.png"), T / config.SWORD_SLASH_SRC_HEAD)]
    frames = _sprite_sets("swordsman", sword, True)
    ms = {"run": mc["swordsman"]["anim_speed"] * config.TICK_MS, "idle": mc["swordsman"]["idle_anim_speed"] * config.TICK_MS,
          "attack_normal": config.SLASH_ANIM_SPD * config.TICK_MS}
    out.append(("swordsman", dict(display_name="Swordsman", archetype="melee",
                                  predicates={"can_shoot": False, "uses_melee": True, "retreats": False, "charges_full": True},
                                  movement={"wander_strength": 0.15},
                                  stats=dict(max_hp=mc["swordsman"]["max_hp"], chase_speed=mc["swordsman"]["chase_speed"],
                                             follow_speed=mc["swordsman"]["follow_speed"], scale=1.0,
                                             basic_attack_radius=mc["swordsman"]["basic_attack_radius"]),
                                  palette={"body": "#ff2200", "accent": "#cc0000"}), frames, ms, None))   # palette.PAL_RED
    return out, sword


def json_sources(sword_sets):
    """Every characters/<name>.json fighter (pb_character)."""
    import glob
    from laser import characters, config
    out = []
    for path in sorted(glob.glob(os.path.join(HERE, "characters", "*.json"))):
        with open(path, "r", encoding="utf-8") as f:
            char = json.load(f)
        if char.get("format") != "pb_character":
            continue
        key = str(char.get("name", "custom")).strip().lower().replace(" ", "_")
        if os.path.isdir(os.path.join(HERE, "characters", key)) and \
                os.path.exists(os.path.join(HERE, "characters", key, "character.json")):
            continue   # already an image-character package (e.g. rapid)
        meta = dict(display_name=char.get("display_name") or key, archetype=char.get("archetype") or "",
                    predicates=dict(zip(characters._PREDICATE_KEYS,
                                        [n in characters._predicates_for(char) for n in characters._PREDICATE_KEYS])),
                    movement=char.get("movement") or {}, stats=char.get("stats") or {},
                    palette=char.get("palette") or {}, description=char.get("description", ""))
        acts = char.get("actions") or {}
        anchors = None
        src = str(char.get("sprite_source", "") or "").strip().lower()
        sf = char.get("sprite_files")
        tint_col = char.get("sprite_tint_color") or (char.get("palette") or {}).get("body", "#ffffff")
        if src == "swordsman":
            frames = _sprite_sets(key, sword_sets, True, ("flat", tint_col) if char.get("sprite_tint") else None)
        elif isinstance(sf, dict):
            def sc(blk):
                try:
                    return config.TARGET_HEAD_PX / max(float(blk.get("src_head_px", 100.0) or 100.0), 1.0)
                except (TypeError, ValueError):
                    return config.TARGET_HEAD_PX / 100.0
            sets = []
            for set_name, blk in sf.items():
                if not isinstance(blk, dict) or not blk.get("files"):
                    continue
                if set_name == "slide" and len(blk["files"]) < 2:
                    continue
                files = [os.path.join(HERE, str(f)) for f in blk["files"]]
                if set_name == "slide":
                    files = files[:2]
                act = SET_TO_ACTION.get(set_name, set_name)
                # An extra set that is an action's frames under a short name
                # ("special" = attack_special's 42 keyframes) takes that name.
                alt = (acts.get("attack_" + act) or {})
                if act not in acts and len(alt.get("keyframes") or []) == len(files):
                    act = "attack_" + act
                sets.append((act, files, sc(blk)))
            frames = _sprite_sets(key, sets, bool(sf.get("remove_bg", True)),
                                  ("colorize", tint_col) if char.get("sprite_tint") else None)
        else:
            frames, anchors = _rig_frames(char)
        ms = {}
        melee = "uses_melee" in characters._predicates_for(char)
        for a, fr in frames.items():
            fb = 5 if a == "run" else 10 if a == "idle" else config.SLASH_ANIM_SPD
            ms[a] = _json_action_ms(char, a, len(fr), fb)
            if a == "attack_normal" and melee and (src or isinstance(sf, dict)):
                # Melee image fighters slash through the combat FSM at
                # SLASH_ANIM_SPD ticks a frame (combat.py), not the JSON duration.
                ms[a] = config.SLASH_ANIM_SPD * config.TICK_MS
        out.append((key, meta, frames, ms, anchors))
    return out


def _rig_frames(char):
    """Skeleton characters: draw every keyframe the way rasterize_character
    does (common canvas, root at the centre) and record each joint."""
    from laser import characters, config
    bones = dict(characters._DEFAULT_BONES)
    bones.update(char.get("bones", {}))
    wpn = char.get("weapon", {}).get("points", []) or []
    base = config.TARGET_HEAD_PX / characters._RIG_HEAD_DIAMETER
    S = base * characters._char_scale(char) * EXPORT_MULT
    per = {}
    hw = hh = 1.0
    for name, action in (char.get("actions") or {}).items():
        js = []
        for kf in action.get("keyframes", []):
            J = characters.rig_joints(kf.get("p", {}), bones, wpn)
            ex, ey = characters._pose_extent(J)
            hw, hh = max(hw, ex), max(hh, ey)
            js.append(J)
        if js:
            per[name] = js
    hw += 4.0
    hh += 4.0
    frames, anchors = {}, {}
    w = max(2, int(math.ceil(hw * S)) * 2)
    h = max(2, int(math.ceil(hh * S)) * 2)
    for name, js in per.items():
        frames[name] = [characters._render_pose(J, char, hw, hh, S) for J in js]
        rows = {a: [] for a in ANCHOR_LABELS}
        for J in js:
            def px(p):
                return [round(w / 2.0 + p[0] * S, 2), round(h / 2.0 + p[1] * S, 2)]
            got = {RIG_TO_ANCHOR[k]: px(v) for k, v in J.items() if k in RIG_TO_ANCHOR}
            hx, hy = J["head"]
            got["neck"] = px(J["head"])
            got["head"] = px((hx, hy - 4))                     # centre of the drawn head circle
            got["root"] = px((hx, hy - 16))                    # just above the head
            got["shB"] = px(J["chest"])
            if J["_weapon_pts"]:
                got["wtip"] = px(J["_weapon_pts"][-1])
            for a in ANCHOR_LABELS:
                rows[a].append(got.get(a))
        anchors[name] = {a: r for a, r in rows.items() if any(r)}
    return frames, anchors


def write_package(key, meta, frames, ms, anchors):
    if not frames:
        print("  %s: no frames found, skipped" % key)
        return
    order = [a for a in ("idle", "run", "attack_normal", "defend", "attack_special", "ultimate") if a in frames]
    order += [a for a in frames if a not in order]
    allf = [p for a in order for p in frames[a]]
    # One canvas for the whole character.  Rig frames already share one.
    padded, (w, h) = _pad(allf)
    dest = os.path.join(OUT_DIR, key)
    os.makedirs(dest, exist_ok=True)
    for fn in os.listdir(dest):
        if fn.lower().endswith(".png"):
            os.remove(os.path.join(dest, fn))
    shift = {}
    actions, i = {}, 0
    for a in order:
        names = []
        for j, p in enumerate(frames[a]):
            fn = "%s_%02d.png" % (a, j + 1)
            padded[i].save(os.path.join(dest, fn), "PNG")
            shift.setdefault(a, []).append((w // 2 - p.width() // 2, h // 2 - p.height() // 2))
            names.append(fn)
            i += 1
        fm = round(float(ms.get(a) or 48.0), 3)
        actions[a] = {"trigger": TRIGGERS.get(a, "triggered"), "duration_ms": round(fm * len(names), 3),
                      "frame_ms": fm, "frames": names}
    # Anchors move with the padding (rig frames: a no-op, the canvas is shared).
    anc = {}
    for a in order:
        rows = (anchors or {}).get(a) or {}
        anc[a] = {j: [None if p is None else [round(p[0] + dx, 2), round(p[1] + dy, 2)]
                      for p, (dx, dy) in zip(row, shift[a])] for j, row in rows.items()}
    from laser import config
    man = {"format": "pb_char_pkg", "version": 1, "name": key,
           "display_name": meta.get("display_name") or key, "description": meta.get("description", ""),
           "archetype": meta.get("archetype") or "",
           "predicates": meta.get("predicates") or {}, "movement": meta.get("movement") or {},
           "stats": meta.get("stats") or {}, "palette": meta.get("palette") or {},
           "image": {"size": [w, h], "origin_px": [w // 2, h // 2],
                     "head_px": config.TARGET_HEAD_PX * EXPORT_MULT, "facing": "right"},
           "actions": actions, "anchors": anc, "anchor_labels": dict(ANCHOR_LABELS),
           "note": "Exported from the game by tools/fx/export_packages.py for FX Studio. Frames face right; "
                   "the image centre (origin_px) is the figure's position in-game; anchors are image px per "
                   "frame. FX Studio saves <name>.fxkit.json into this folder."}
    with open(os.path.join(dest, "character.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    placed = sum(1 for a in anc.values() for r in a.values() for p in r if p)
    print("  %-16s %3d frames  %dx%d px  actions: %s  anchors placed: %d"
          % (key, len(allf), w, h, ", ".join("%s(%d)" % (a, len(frames[a])) for a in order), placed))


def main():
    app = QApplication.instance() or QApplication(sys.argv[:1])   # noqa: F841 (QPixmap needs it)
    print("Exporting FX Studio packages to %s" % OUT_DIR)
    built, sword_sets = builtin_sources()
    for item in built + json_sources(sword_sets):
        write_package(*item)
    print("Done. Open a folder under fx_packages/ in FX Studio (Open character folder...).")


if __name__ == "__main__":
    main()
