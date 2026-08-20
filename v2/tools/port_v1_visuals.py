"""Port V1 character visuals (rigs, keyframes, sprites, FX identity) into
the v2 character JSONs' `visual` blocks — with the anime-feel enhancements
the v2 renderer supports (easing curves, punch-amplified attack poses).

Idempotent: reads characters/<key>.json (v1) and v2/characters/<key>.json,
replaces only the `visual` block, leaves gameplay untouched.  Run from the
repo root:  python3 v2/tools/port_v1_visuals.py
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
V1_DIR = os.path.join(ROOT, "characters")
V2_DIR = os.path.join(ROOT, "v2", "characters")

# pose keys that are ANGLES (amplify these for punchier attacks); rx/ry are
# offsets and *s keys are bone-length scales — never amplified.
_ANGLE_KEYS = {"sp", "sp2", "hd", "lsht", "rsht", "lpvt", "rpvt",
               "lua", "lfa", "rua", "rfa", "lth", "lsh", "rth", "rsh", "wp"}

_ATTACK_ACTIONS = {"attack_normal", "attack_special", "ultimate"}
_LOOP_ACTIONS = {"idle", "run"}

_EASE = {
    "idle": "inout", "run": "inout",
    "attack_normal": "snap", "attack_special": "snap",
    "ultimate": "out", "defend": "out",
    "special_ability": "out", "impact": "overshoot",
}


def _rgb(v, default=0xFFFFFF):
    if isinstance(v, int):
        return v & 0xFFFFFF
    if isinstance(v, str) and v.lstrip("#"):
        try:
            return int(v.lstrip("#"), 16) & 0xFFFFFF
        except ValueError:
            pass
    return default


def _round_pose(p, amp=1.0):
    out = {}
    for k, v in p.items():
        if not isinstance(v, (int, float)):
            continue
        if amp != 1.0 and k in _ANGLE_KEYS:
            v = v * amp
        out[k] = round(float(v), 2)
    return out


def _port_actions(v1_actions):
    """v1 actions -> v2 rig actions: keyframes kept, timing kept, plus an
    easing curve per action and a 1.18x angle amplification on attack poses
    (the 'punch-up' — same silhouette, harder extremes)."""
    out = {}
    for name, act in (v1_actions or {}).items():
        kfs = act.get("keyframes") or []
        poses = []
        amp = 1.18 if name in _ATTACK_ACTIONS else 1.0
        for kf in kfs:
            poses.append({"p": _round_pose(kf.get("p") or {}, amp)})
        if not poses:
            continue
        entry = {"keyframes": poses}
        dur = act.get("duration_ms")
        if isinstance(dur, (int, float)) and dur > 0:
            entry["duration_ms"] = float(dur)
        entry["ease"] = _EASE.get(name, "inout")
        if name in _LOOP_ACTIONS:
            entry["loop"] = True
        out[name] = entry
    return out


def _fx_block(v1, body, accent):
    fx = {}
    ai = _rgb(v1.get("afterimage_color"), None) \
        if v1.get("afterimage_color") else None
    fx["afterimage"] = {"color": ai if ai is not None else accent,
                        "alpha": 96, "life": 13}
    tg = v1.get("trail_gradient") or {}
    if not isinstance(tg, dict):
        tg = {}
    head = _rgb(tg.get("start_color", tg.get("head")), body)
    tail = _rgb(tg.get("end_color", tg.get("tail")), accent)
    fx["trail"] = {"colors": [head, tail], "width": 3.0, "length": 16}
    fx["crescent"] = {"color": 0xFFFFFF if accent < 0x202020 else accent,
                      "glow": accent}
    return fx


def _glow_block(v1, accent):
    og = v1.get("outline_glow")
    if isinstance(og, dict):
        if og.get("enabled") is False:
            return False
        return {"color": _rgb(og.get("color"), accent),
                "radius": float(og.get("radius", 2.0)),
                "opacity": int(og.get("opacity", 120))}
    # default: a light accent glow so dark bodies read on any desktop
    return {"color": accent, "radius": 1.8, "opacity": 110}


def port_rig_character(key):
    with open(os.path.join(V1_DIR, key + ".json"), encoding="utf-8") as f:
        v1 = json.load(f)
    p2 = os.path.join(V2_DIR, key + ".json")
    with open(p2, encoding="utf-8") as f:
        v2 = json.load(f)

    pal1 = v1.get("palette") or {}
    body = _rgb(pal1.get("body"), 0x8FA0B8)
    accent = _rgb(pal1.get("accent"), 0xFF5050)
    # near-black accents (new_fighter) vanish on the overlay — the FX layer
    # substitutes a readable variant while the body keeps its authored tone
    if accent < 0x101018:
        # ronin's identity colour is its ice-blue afterimage/weapon tone
        accent = {"new_fighter": 0x7A2EA8,
                  "ronin": 0xC2E0F9}.get(key, 0x9AA6FF)

    wpn = v1.get("weapon") or {}
    rig = {
        "bones": {k: v for k, v in (v1.get("bones") or {}).items()
                  if isinstance(v, (int, float))},
        "scale": float((v1.get("stats") or {}).get("scale", 1.0)),
        "actions": _port_actions(v1.get("actions")),
    }
    pts = wpn.get("points") or []
    if pts:
        rig["weapon"] = {"points": [[round(float(a), 2), round(float(b), 2)]
                                    for a, b in pts],
                         "thickness": float(wpn.get("thickness", 3)),
                         "color": _rgb(wpn.get("color"), 0xD8DEE9)}

    old_pal = dict((v2.get("visual") or {}).get("palette") or {})
    old_pal.update({"body": body, "accent": accent,
                    "primary": old_pal.get("primary", body)})
    v2["visual"] = {
        "palette": old_pal,
        "outline_glow": _glow_block(v1, accent),
        "rig": rig,
        "fx": _fx_block(v1, body, accent),
    }
    with open(p2, "w", encoding="utf-8") as f:
        json.dump(v2, f, indent=1)
        f.write("\n")
    n_kf = sum(len(a["keyframes"]) for a in rig["actions"].values())
    print("%-12s rig ported: %d actions, %d keyframes" %
          (key, len(rig["actions"]), n_kf))


# ---------------------------------------------------------------------
# sprite characters — V1's original PNG art, referenced by glob pattern
# ---------------------------------------------------------------------
_SPRITES = {
    "runner": {
        "sets": {"run": "Picture*.png", "idle": "standing*.png"},
        "src_head": {"run": 75.0, "idle": 60.0},
        "ticks_per_frame": 5,
    },
    "swordsman": {
        "sets": {"run": "swordrun*.png", "idle": "swordstanding*.png",
                 "attack": "slash*.png"},
        "src_head": {"run": 105.0, "idle": 205.0, "attack": 155.0},
        "ticks_per_frame": 4,
    },
}

_SPRITE_FX = {
    "runner": {
        "afterimage": {"color": 0xDC3C50, "alpha": 90, "life": 13},
        "trail": {"colors": [0x39D5FF, 0xC2E0F9], "width": 2.6, "length": 14},
        "crescent": {"color": 0xDCF5FF, "glow": 0x39D5FF},
    },
    "swordsman": {
        "afterimage": {"color": 0xDC3C50, "alpha": 100, "life": 14},
        "trail": {"colors": [0xFF8A5A, 0xFFC248], "width": 2.8, "length": 14},
        "crescent": {"color": 0xFFFFFF, "glow": 0xFFC248},
    },
}


def port_sprite_character(key):
    p2 = os.path.join(V2_DIR, key + ".json")
    with open(p2, encoding="utf-8") as f:
        v2 = json.load(f)
    old_pal = dict((v2.get("visual") or {}).get("palette") or {})
    v2["visual"] = {
        "palette": old_pal or {"primary": 0x39D5FF, "accent": 0xC2E0F9},
        "outline_glow": False,       # V1 sprite figures had no glow ring
        "sprites": _SPRITES[key],
        "fx": _SPRITE_FX[key],
    }
    with open(p2, "w", encoding="utf-8") as f:
        json.dump(v2, f, indent=1)
        f.write("\n")
    print("%-12s sprite sets: %s" % (key, sorted(_SPRITES[key]["sets"])))


if __name__ == "__main__":
    for key in ("ronin", "mage", "jumper", "new_fighter"):
        port_rig_character(key)
    for key in ("runner", "swordsman"):
        port_sprite_character(key)
    print("done — validate with pb2.content.load_all before shipping")
