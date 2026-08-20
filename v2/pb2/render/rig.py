"""Rig animation — the V1 stick-figure rig, reborn as a presentation module.

V1 rasterised every keyframe of a character's rig into pixmaps and played
them back frame-by-frame: no in-betweens, so motion snapped from pose to
pose ("stiff sticks").  Here the rig stays VECTOR all the way to the paint
call: every render frame interpolates between the surrounding keyframes
with an easing curve, so a 5-keyframe sword swing renders as a continuous
anticipation -> strike -> follow-through arc at full frame rate.

Everything in this module is cosmetic.  It reads `visual` blocks from
character JSON and actor state (anim / anim_t / facing / tags) and writes
nothing back — the RULE from painter.py applies here in full.  Nothing
here may ever touch gameplay numbers; the sim never imports this module.

Coordinate system: y-down, root (hip, before rx/ry offsets) at (0, 0),
exactly like V1's laser/characters.py port of rig.js `joints()`.  Poses
authored in the V1 Character Creator therefore transfer verbatim.
"""

import math
import os

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QColor, QPen, QPixmap, QImage, QPainter, QTransform

__all__ = ["RigAnimator", "SpriteBank", "draw_rig", "rig_joints",
           "ZERO_POSE", "DEFAULT_BONES", "BODY_SEGMENTS", "lerp_pose",
           "RIG_HEAD_DIAMETER", "TARGET_HEAD_PX", "qcolor"]

_D = math.pi / 180.0

# Default pose (rig.js `Z`) — merged under every keyframe pose defensively.
ZERO_POSE = dict(rx=0, ry=0, sp=0, sp2=0, hd=0, lsht=0, rsht=0, lpvt=0,
                 rpvt=0, lua=15, lfa=5, rua=-15, rfa=-5, lth=8, lsh=5,
                 rth=-8, rsh=-5, wp=-45, luas=1, lfas=1, ruas=1, rfas=1,
                 lths=1, lshs=1, rths=1, rshs=1)

DEFAULT_BONES = dict(ua=22, fa=20, th=26, sh=24, torso=36)

# Native rig head diameter (radius 10 in rig.js) — normalises the figure to
# the same on-screen size regardless of authored bone lengths.
RIG_HEAD_DIAMETER = 20.0
# On-screen head size at scale 1.0 — V1's config.TARGET_HEAD_PX, kept
# identical so a ported character reads exactly the same size.
TARGET_HEAD_PX = 16.0

BODY_SEGMENTS = [
    ("hip", "torso_mid"), ("torso_mid", "chest"),
    ("chest", "l_shoulder"), ("chest", "r_shoulder"),
    ("hip", "l_hip"), ("hip", "r_hip"),
    ("l_shoulder", "l_elbow"), ("l_elbow", "l_hand"),
    ("r_shoulder", "r_elbow"), ("r_elbow", "r_hand"),
    ("l_hip", "l_knee"), ("l_knee", "l_foot"),
    ("r_hip", "r_knee"), ("r_knee", "r_foot"),
]


def qcolor(rgb, alpha=255):
    """int 0xRRGGBB (or '#rrggbb') -> QColor."""
    if isinstance(rgb, str):
        rgb = int(rgb.lstrip("#") or "0", 16)
    return QColor((int(rgb) >> 16) & 255, (int(rgb) >> 8) & 255,
                  int(rgb) & 255, int(alpha))


# ---------------------------------------------------------------------------
# Rig maths — faithful port of V1 laser/characters.py (itself a port of
# tools/fx/rig.js `joints()`).  y-down, like Qt.
# ---------------------------------------------------------------------------
def _bone_end(origin, angle, length):
    return (origin[0] + math.cos(angle) * length,
            origin[1] + math.sin(angle) * length)


def rig_joints(pose, bones, weapon_points):
    """World joint positions for a pose, with the root at (0,0)."""
    p = dict(ZERO_POSE)
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

    # Custom weapon polyline — points local to r_hand, rotated by wW.
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
# Easing + pose interpolation — the "not stiff" part V1 never had
# ---------------------------------------------------------------------------
def _ease(t, kind):
    if kind == "in":                       # slow start (anticipation build)
        return t * t * t
    if kind == "out":                      # fast start, soft landing
        u = 1.0 - t
        return 1.0 - u * u * u
    if kind == "inout":
        return t * t * (3.0 - 2.0 * t)     # smoothstep
    if kind == "snap":                     # near-instant hit, long settle
        return 1.0 - math.pow(1.0 - t, 6)
    if kind == "overshoot":                # back-ease: whips past, springs back
        c = 1.70158
        u = t - 1.0
        return 1.0 + (c + 1.0) * u * u * u + c * u * u
    return t                               # linear


def lerp_pose(a, b, t, ease="inout"):
    """Interpolate every numeric pose param between two keyframe poses."""
    t = _ease(max(0.0, min(1.0, t)), ease)
    out = dict(ZERO_POSE)
    out.update(a)
    for k, bv in b.items():
        av = out.get(k, ZERO_POSE.get(k, 0.0))
        out[k] = av + (bv - av) * t
    # keys only present in `a` still need blending toward b's default
    for k, av in a.items():
        if k not in b:
            bv = ZERO_POSE.get(k, 0.0)
            out[k] = av + (bv - av) * t
    return out


class RigAnimator:
    """One character's rig actions, answering `pose for anim state at tick t`.

    Built once per character from visual["rig"].  Loops idle/run, clamps
    one-shot actions (attack/defend) with hold-on-last-frame, and blends
    between keyframes with the per-action easing curve.
    """

    #  v2 sim anim/tag names -> rig action names (with fallback chain)
    _ACTION_MAP = {
        "attack":  ("attack", "attack_normal", "attack_special"),
        "guard":   ("guard", "defend"),
        "idle":    ("idle",),
        "run":     ("run",),
    }

    def __init__(self, rig_block):
        rig_block = rig_block or {}
        self.bones = dict(DEFAULT_BONES)
        self.bones.update(rig_block.get("bones") or {})
        wpn = rig_block.get("weapon") or {}
        self.weapon = wpn
        self.weapon_pts = [(float(px), float(py))
                           for px, py in (wpn.get("points") or [])]
        try:
            self.scale = max(0.1, min(2.0, float(rig_block.get("scale", 1.0))))
        except (TypeError, ValueError):
            self.scale = 1.0
        self.actions = {}
        for name, act in (rig_block.get("actions") or {}).items():
            kfs = [dict(k.get("p") or {}) for k in (act.get("keyframes") or [])]
            if not kfs:
                continue
            self.actions[name] = {
                "poses": kfs,
                "duration_ms": float(act.get("duration_ms") or 600.0),
                "ease": act.get("ease", "inout"),
                "loop": bool(act.get("loop",
                             name in ("idle", "run"))),
            }

    def has(self, anim):
        return self._resolve(anim) is not None

    def _resolve(self, anim):
        for cand in self._ACTION_MAP.get(anim, (anim,)):
            if cand in self.actions:
                return self.actions[cand]
        return self.actions.get("idle")

    def pose_at(self, anim, anim_ticks, tick_ms=16.0):
        """Interpolated pose dict for an anim state at anim_ticks age."""
        act = self._resolve(anim)
        if act is None:
            return dict(ZERO_POSE)
        poses = act["poses"]
        n = len(poses)
        if n == 1:
            return dict(ZERO_POSE, **poses[0])
        elapsed = anim_ticks * tick_ms
        dur = max(tick_ms, act["duration_ms"])
        if act["loop"]:
            # n segments: last pose blends back into the first (seamless loop)
            u = (elapsed % dur) / dur * n
            i = int(u) % n
            j = (i + 1) % n
            return lerp_pose(poses[i], poses[j], u - int(u), act["ease"])
        # one-shot: n-1 segments, clamp and hold the final pose
        u = min(1.0, elapsed / dur) * (n - 1)
        i = min(n - 2, int(u))
        return lerp_pose(poses[i], poses[i + 1], u - i, act["ease"])

    def joints_at(self, anim, anim_ticks, tick_ms=16.0):
        return rig_joints(self.pose_at(anim, anim_ticks, tick_ms),
                          self.bones, self.weapon_pts)


# ---------------------------------------------------------------------------
# Vector drawing — segments + head + weapon at the painter's current origin
# ---------------------------------------------------------------------------
def draw_rig(p, J, body_rgb, accent_rgb, weapon_cfg=None,
             stroke=3.5, alpha=255, flat=False):
    """Draw one posed rig.  Caller owns translate/scale/mirror on `p`.

    flat=True paints everything in body_rgb at the given alpha — the
    silhouette style used for afterimage ghosts.
    """
    col = qcolor(body_rgb, alpha)
    pen = QPen(col)
    pen.setWidthF(stroke)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    for a, b in BODY_SEGMENTS:
        p.drawLine(QPointF(*J[a]), QPointF(*J[b]))
    hx, hy = J["head"]
    p.drawEllipse(QPointF(hx, hy - 4), 10, 10)

    pts = J.get("_weapon_pts") or []
    if pts:
        wpn = weapon_cfg or {}
        chain = [QPointF(*J["r_hand"])] + [QPointF(*q) for q in pts]
        thick = float(wpn.get("thickness", 3))
        if not flat:
            glow = QPen(qcolor(accent_rgb if accent_rgb is not None
                               else 0xFF5050, int(0.55 * alpha)))
            glow.setWidthF(thick + 3.0)
            glow.setCapStyle(Qt.RoundCap)
            p.setPen(glow)
            for i in range(len(chain) - 1):
                p.drawLine(chain[i], chain[i + 1])
        wp_pen = QPen(qcolor(body_rgb if flat else wpn.get("color", 0xD8DEE9),
                             alpha))
        wp_pen.setWidthF(thick)
        wp_pen.setCapStyle(Qt.RoundCap)
        p.setPen(wp_pen)
        for i in range(len(chain) - 1):
            p.drawLine(chain[i], chain[i + 1])


# ---------------------------------------------------------------------------
# Sprite characters (runner / swordsman) — PNG frame playback, V1 art
# ---------------------------------------------------------------------------
def _remove_background(pm, tol=40):
    """Near-black background -> transparent (port of V1 assets.py)."""
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    ptr = img.bits()
    ptr.setsize(w * h * 4)
    buf = bytearray(ptr)
    tol_sq = tol * tol * 3
    for i in range(0, len(buf), 4):
        b, g, r = buf[i], buf[i + 1], buf[i + 2]
        if r * r + g * g + b * b <= tol_sq:
            buf[i + 3] = 0
    out = QImage(bytes(buf), w, h, img.bytesPerLine(), QImage.Format_ARGB32)
    return QPixmap.fromImage(out.copy())


def silhouette(pm, rgb):
    """Flat single-colour copy of a frame (afterimages / glow rings)."""
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    ptr = img.bits()
    ptr.setsize(w * h * 4)
    buf = bytearray(ptr)
    r = (rgb >> 16) & 255
    g = (rgb >> 8) & 255
    b = rgb & 255
    for i in range(0, len(buf), 4):
        if buf[i + 3]:
            buf[i], buf[i + 1], buf[i + 2] = b, g, r
    out = QImage(bytes(buf), w, h, img.bytesPerLine(), QImage.Format_ARGB32)
    return QPixmap.fromImage(out.copy())


def _natural_key(path):
    import re
    m = re.search(r"(\d+)", os.path.basename(path))
    return int(m.group(1)) if m else 0


class SpriteBank:
    """PNG frame sets for one character, from visual["sprites"].

    Frames are searched relative to each directory in `search_dirs` (the
    repo root holds V1's art; v2/assets can override).  Missing art is not
    an error — `ok` is False and the caller falls back to the rig.
    """

    def __init__(self, sprite_block, search_dirs):
        import glob as _glob
        self.ok = False
        self.frames = {}          # action -> [QPixmap]
        self.flipped = {}
        self._silhouettes = {}    # (action, idx, rgb) -> QPixmap
        sprite_block = sprite_block or {}
        sets = sprite_block.get("sets") or {}
        src_head = sprite_block.get("src_head") or {}
        target = float(sprite_block.get("target_head_px", TARGET_HEAD_PX))
        flip = QTransform().scale(-1, 1)
        for action, pattern in sets.items():
            files = []
            for d in search_dirs:
                files = sorted(_glob.glob(os.path.join(d, pattern)),
                               key=_natural_key)
                if files:
                    break
            if not files:
                continue
            scale = 1.0
            try:
                sh = float(src_head.get(action, 0) or 0)
                if sh > 0:
                    scale = target / sh
            except (TypeError, ValueError):
                pass
            fr, fl = [], []
            for fp in files:
                px = QPixmap(fp)
                if px.isNull():
                    continue
                if sprite_block.get("remove_bg", True):
                    px = _remove_background(px)
                if scale != 1.0:
                    px = px.scaled(max(1, int(px.width() * scale)),
                                   max(1, int(px.height() * scale)),
                                   Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
                fr.append(px)
                fl.append(px.transformed(flip))
            if fr:
                self.frames[action] = fr
                self.flipped[action] = fl
        self.ok = bool(self.frames.get("run") or self.frames.get("idle"))

    def frame(self, anim, anim_ticks, ticks_per_frame=5, facing_left=False):
        """Current frame for an anim state, or None if this bank lacks it."""
        for cand in (anim, {"attack": "run", "guard": "idle",
                            "run": "idle", "idle": "run"}.get(anim, "idle")):
            fr = (self.flipped if facing_left else self.frames).get(cand)
            if fr:
                idx = (anim_ticks // max(1, ticks_per_frame))
                if cand in ("attack",):
                    idx = min(idx, len(fr) - 1)      # one-shot: hold last
                else:
                    idx %= len(fr)
                return fr[int(idx)]
        return None

    def silhouette_frame(self, anim, anim_ticks, rgb,
                         ticks_per_frame=5, facing_left=False):
        pm = self.frame(anim, anim_ticks, ticks_per_frame, facing_left)
        if pm is None:
            return None
        key = (id(pm), rgb)
        s = self._silhouettes.get(key)
        if s is None:
            s = silhouette(pm, rgb)
            if len(self._silhouettes) > 256:
                self._silhouettes.clear()
            self._silhouettes[key] = s
        return s
