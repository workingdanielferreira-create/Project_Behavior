"""
Character loader — imports Character Creator `pb_character` JSON files at
startup and turns them into fully playable figure types.

Pipeline (runs once inside AssetLibrary._load_all, after Qt is up):
  1. Scan `<launcher>/characters/*.json` for files with format == "pb_character".
  2. A Python port of the FX Creator rig maths (tools/fx/rig.js `joints()`)
     rasterises every keyframe of the baseline actions into transparent
     QPixmaps — keyframes only, no interpolation, so the animation plays the
     exact authored poses (snappy).
  3. The frames are packed into a FrameBundle:
        run            -> run frames
        idle           -> idle frames
        attack_normal  -> slash frames
        defend kf 0/1  -> slide / slide2
  4. A FigureMode subclass, MODE_CONFIGS entry, MODE_ORDER key, and a palette
     LUT (built from the character's body/accent colours) are registered, so
     every system — Solo AND Battle, which all route through the mode
     predicates — treats the character exactly like a built-in figure.

Archetype inference: a character whose weapon polyline is empty is treated as
a *shooter* (can_shoot + retreats — projectiles, beam ultimate, survival
teleport); a character with a drawn weapon is treated as *melee*
(uses_melee + charges_full — dash-lunge, slash frames, sword ultimates).

Battle properties from the JSON (`damage`, `pierce`, `explode`, ...) and the
raw fx_layers are kept on the mode instance (`mode.character`) for combat/VFX
integration.  Runtime FX are played live by the game's existing VFX engine
(trail component, projectiles, beam ultimate, muzzle flashes, crescents),
coloured through the character's palette LUT — identical in Solo and Battle.
"""

import glob
import json
import math
import os

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QTransform

from . import config, modes, palette

_D = math.pi / 180.0

# Default pose (rig.js `Z`) — merged under every keyframe pose defensively.
_ZERO_POSE = dict(rx=0, ry=0, sp=0, sp2=0, hd=0, lsht=0, rsht=0, lpvt=0,
                  rpvt=0, lua=15, lfa=5, rua=-15, rfa=-5, lth=8, lsh=5,
                  rth=-8, rsh=-5, wp=-45, luas=1, lfas=1, ruas=1, rfas=1,
                  lths=1, lshs=1, rths=1, rshs=1)

_DEFAULT_BONES = dict(ua=22, fa=20, th=26, sh=24, torso=36)

# Native rig head diameter (radius 10 in rig.js) — used to normalise the
# character to the same on-screen size as the sprite figures.
_RIG_HEAD_DIAMETER = 20.0

_BODY_SEGMENTS = [
    ("hip", "torso_mid"), ("torso_mid", "chest"),
    ("chest", "l_shoulder"), ("chest", "r_shoulder"),
    ("hip", "l_hip"), ("hip", "r_hip"),
    ("l_shoulder", "l_elbow"), ("l_elbow", "l_hand"),
    ("r_shoulder", "r_elbow"), ("r_elbow", "r_hand"),
    ("l_hip", "l_knee"), ("l_knee", "l_foot"),
    ("r_hip", "r_knee"), ("r_knee", "r_foot"),
]


# ---------------------------------------------------------------------------
# Rig maths — faithful port of tools/fx/rig.js `joints()` (y-down, like Qt)
# ---------------------------------------------------------------------------
def _bone_end(origin, angle, length):
    return (origin[0] + math.cos(angle) * length,
            origin[1] + math.sin(angle) * length)


def rig_joints(pose, bones, weapon_points):
    """World joint positions for a pose, with the root (before rx/ry) at (0,0)."""
    p = dict(_ZERO_POSE)
    p.update(pose)
    B = _bone_end
    BL = bones
    J = {}
    hip = (p["rx"], p["ry"])
    J["hip"] = hip

    sp_w = (-90 + p["sp"]) * _D
    J["torso_mid"] = B(hip, sp_w, BL["torso"] / 2.0)
    sp_w2 = sp_w + p.get("sp2", 0) * _D
    J["chest"] = B(J["torso_mid"], sp_w2, BL["torso"] / 2.0)
    hd_w = sp_w2 + p["hd"] * _D
    J["head"] = B(J["chest"], hd_w, 16)

    J["r_shoulder"] = B(J["chest"], sp_w2 + math.pi / 2 + p["rsht"] * _D, 11)
    J["l_shoulder"] = B(J["chest"], sp_w2 - math.pi / 2 + p["lsht"] * _D, 11)
    J["r_hip"] = B(hip, p["rpvt"] * _D, 8)
    J["l_hip"] = B(hip, math.pi + p["lpvt"] * _D, 8)

    arm_base = sp_w2 + math.pi
    lua_w = arm_base + p["lua"] * _D
    J["l_elbow"] = B(J["l_shoulder"], lua_w, BL["ua"] * p.get("luas", 1))
    lfa_w = lua_w + p["lfa"] * _D
    J["l_hand"] = B(J["l_elbow"], lfa_w, BL["fa"] * p.get("lfas", 1))
    rua_w = arm_base + p["rua"] * _D
    J["r_elbow"] = B(J["r_shoulder"], rua_w, BL["ua"] * p.get("ruas", 1))
    rfa_w = rua_w + p["rfa"] * _D
    J["r_hand"] = B(J["r_elbow"], rfa_w, BL["fa"] * p.get("rfas", 1))

    lth_w = (90 + p["lth"]) * _D
    J["l_knee"] = B(J["l_hip"], lth_w, BL["th"] * p.get("lths", 1))
    J["l_foot"] = B(J["l_knee"], lth_w + p["lsh"] * _D, BL["sh"] * p.get("lshs", 1))
    rth_w = (90 + p["rth"]) * _D
    J["r_knee"] = B(J["r_hip"], rth_w, BL["th"] * p.get("rths", 1))
    J["r_foot"] = B(J["r_knee"], rth_w + p["rsh"] * _D, BL["sh"] * p.get("rshs", 1))

    # Custom weapon polyline — points are local to r_hand, rotated by wW
    # (rig.js wpnWorld).  Empty polyline => no weapon geometry.
    w_w = rfa_w + p["wp"] * _D
    pts = []
    if weapon_points:
        c, s = math.cos(w_w), math.sin(w_w)
        hx, hy = J["r_hand"]
        pts = [(hx + wx * c - wy * s, hy + wx * s + wy * c)
               for wx, wy in weapon_points]
    J["_weapon_pts"] = pts
    return J


# ---------------------------------------------------------------------------
# Rasterisation
# ---------------------------------------------------------------------------
def _pose_extent(J):
    """Max |x|, |y| this pose reaches, including head circle and weapon."""
    max_x = max_y = 0.0
    for k, v in J.items():
        if k.startswith("_"):
            continue
        max_x = max(max_x, abs(v[0]))
        max_y = max(max_y, abs(v[1]))
    hx, hy = J["head"]
    max_x = max(max_x, abs(hx) + 10)
    max_y = max(max_y, abs(hy - 4) + 10)
    for wx, wy in J["_weapon_pts"]:
        max_x = max(max_x, abs(wx))
        max_y = max(max_y, abs(wy))
    return max_x, max_y


def _render_pose(J, char, half_w, half_h, scale):
    """Draw one pose into a transparent QPixmap.  The pixmap centre is the
    figure root, so Figure.draw's centred drawPixmap keeps frames aligned."""
    w = max(2, int(math.ceil(half_w * scale)) * 2)
    h = max(2, int(math.ceil(half_h * scale)) * 2)
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing)
    qp.translate(w / 2.0, h / 2.0)
    qp.scale(scale, scale)

    body_col = QColor(char["palette"].get("body", "#8fa0b8"))
    pen = QPen(body_col)
    pen.setWidthF(3.5)
    pen.setCapStyle(Qt.RoundCap)
    qp.setPen(pen)
    for a, b in _BODY_SEGMENTS:
        qp.drawLine(QPointF(*J[a]), QPointF(*J[b]))
    hx, hy = J["head"]
    qp.setBrush(Qt.NoBrush)
    qp.drawEllipse(QPointF(hx, hy - 4), 10, 10)

    pts = J["_weapon_pts"]
    if pts:
        wpn = char.get("weapon", {})
        chain = [QPointF(*J["r_hand"])] + [QPointF(*p) for p in pts]
        glow = QPen(QColor(char["palette"].get("accent", "#ff5050")))
        glow.setWidthF(float(wpn.get("thickness", 3)) + 3.0)
        glow.setCapStyle(Qt.RoundCap)
        qp.setOpacity(0.55)
        qp.setPen(glow)
        for i in range(len(chain) - 1):
            qp.drawLine(chain[i], chain[i + 1])
        qp.setOpacity(1.0)
        wp_pen = QPen(QColor(wpn.get("color", "#d8dee9")))
        wp_pen.setWidthF(float(wpn.get("thickness", 3)))
        wp_pen.setCapStyle(Qt.RoundCap)
        qp.setPen(wp_pen)
        for i in range(len(chain) - 1):
            qp.drawLine(chain[i], chain[i + 1])

    qp.end()
    return pm


def rasterize_character(char):
    """Rasterise every action's keyframes.  Returns {action: [QPixmap, ...]}.

    One shared canvas size is computed over ALL actions so the root stays at
    the pixmap centre in every frame (no jitter between animations)."""
    bones = dict(_DEFAULT_BONES)
    bones.update(char.get("bones", {}))
    wpn_pts = char.get("weapon", {}).get("points", []) or []
    scale = config.TARGET_HEAD_PX / _RIG_HEAD_DIAMETER

    joints_per_action = {}
    half_w = half_h = 1.0
    for name, action in char.get("actions", {}).items():
        js = []
        for kf in action.get("keyframes", []):
            J = rig_joints(kf.get("p", {}), bones, wpn_pts)
            ex, ey = _pose_extent(J)
            half_w = max(half_w, ex)
            half_h = max(half_h, ey)
            js.append(J)
        joints_per_action[name] = js
    half_w += 4.0
    half_h += 4.0

    frames = {}
    for name, js in joints_per_action.items():
        frames[name] = [_render_pose(J, char, half_w, half_h, scale)
                        for J in js]
    return frames


def _flip(pixmaps):
    t = QTransform().scale(-1, 1)
    return [pm.transformed(t) for pm in pixmaps]


# ---------------------------------------------------------------------------
# Registration — mode, tuning, palette LUT
# ---------------------------------------------------------------------------
def _hex_rgb(h):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _anim_ticks(action, fallback):
    """Ticks-per-frame so the keyframe sequence roughly spans duration_ms."""
    if not action:
        return fallback
    n = max(1, len(action.get("keyframes", [])))
    dur = float(action.get("duration_ms", 0) or 0)
    if dur <= 0:
        return fallback
    return max(1, int(round(dur / n / config.TICK_MS)))


def _register(char):
    """Register mode class, tuning, cycle-order key, and palette LUT."""
    key = str(char.get("name", "custom")).strip().lower().replace(" ", "_")
    is_melee = bool(char.get("weapon", {}).get("points"))

    if key not in modes.MODE_REGISTRY:
        if is_melee:
            attrs = {"key": key,
                     "uses_melee": lambda self: True,
                     "charges_full": lambda self: True}
        else:
            attrs = {"key": key,
                     "can_shoot": lambda self: True,
                     "retreats": lambda self: True}
        cls = type(key.title() + "CharacterMode", (modes.FigureMode,), attrs)
        inst = cls()
        inst.character = char           # battle props + fx_layers for combat
        modes.MODE_REGISTRY[key] = inst
    else:
        modes.MODE_REGISTRY[key].character = char

    actions = char.get("actions", {})
    if key not in config.MODE_CONFIGS:
        config.MODE_CONFIGS[key] = dict(
            chase_speed=3.0, follow_speed=4.5,
            anim_speed=_anim_ticks(actions.get("run"), 5),
            idle_anim_speed=_anim_ticks(actions.get("idle"), 10),
            max_hp=100,
        )
    if key not in config.MODE_ORDER:
        config.MODE_ORDER.append(key)

    pal = char.get("palette", {})
    body = _hex_rgb(pal.get("body", "#8fa0b8"))
    accent = _hex_rgb(pal.get("accent", "#ff5050"))
    palette.register_custom_lut(key, palette.build_lut([body, accent]))
    return key


def _build_bundle(frames):
    """Pack rasterised action frames into a FrameBundle."""
    from .assets import FrameBundle   # lazy: avoids circular import at load
    run = frames.get("run", [])
    idle = frames.get("idle", [])
    slash = frames.get("attack_normal", [])
    defend = frames.get("defend", [])
    slide = defend[0] if defend else None
    slide2 = defend[1] if len(defend) > 1 else slide
    return FrameBundle(
        run, _flip(run), idle, _flip(idle),
        slide, _flip([slide])[0] if slide else None,
        slide2, _flip([slide2])[0] if slide2 else None,
        slash, _flip(slash),
    )


# ---------------------------------------------------------------------------
# Entry point — called by AssetLibrary._load_all (Solo and Battle both build
# their worlds from the same AssetLibrary, so parity is automatic).
# ---------------------------------------------------------------------------
def load_all(root_dir, bundles):
    """Scan <root>/characters/*.json, register each, add its FrameBundle."""
    folder = os.path.join(root_dir, "characters")
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                char = json.load(f)
            if char.get("format") != "pb_character":
                continue
            key = _register(char)
            bundles[key] = _build_bundle(rasterize_character(char))
        except Exception as e:                        # never kill the game
            print("Character load failed for %s: %s" % (path, e))
