"""
FX Kit runtime — the game's port of tools/fx/studio/fxkit.js (pb_fxkit v2).

FX Studio authors every effect of an image character (characters/<name>/
<name>.fxkit.json).  This module plays them in game exactly as the Studio
previews them: same fixed 16 ms tick, same mulberry32 random streams, same
maths for every primitive, motion, entry set and path, and the same "the
shape that's drawn is the shape that hits" damage rule.  fxkit.js is the
reference; keep the two in step (see its PORTING CONTRACT).

Game side (bottom of this file): one FxDriver per figure whose character
carries an FX file.  CombatSystem ticks it every tick (Solo and Battle
alike); Figure.draw paints its "behind" layer before the sprite and its
"front" layer after.  The action being played and its frame come from the
same state Figure._current_frame uses to pick the sprite, so FX stay locked
to the keyframes on screen.  Damage in Battle is queued on the side
(SideState.fx_hits) and delivered to the opposing fighter by
World.refresh_battle at the start of the next tick — the same one-tick
boundary the cross-side knockback uses.
"""

import math
import re

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import (QBrush, QColor, QLinearGradient, QPen, QPainter, QPainterPath, QPixmap, QPolygonF,
                         QRadialGradient)

from . import config

TICK_MS = 16
TICK_S = TICK_MS / 1000.0
D = math.pi / 180.0
M32 = 0xFFFFFFFF
INF = float("inf")


def trunc(v):
    return int(v)


def jround(v):
    """Math.round: halves round up (Python's round() rounds half to even)."""
    return int(math.floor(v + 0.5))


def imul(a, b):
    return ((a & M32) * (b & M32)) & M32


# ---------------------------------------------------------------- random
class Rng:
    """mulberry32 — identical stream to FXK.rng."""
    __slots__ = ("a",)

    def __init__(self, seed):
        self.a = seed & M32

    def __call__(self):
        self.a = (self.a + 0x6D2B79F5) & M32
        t = self.a
        t = imul(t ^ (t >> 15), t | 1)
        t ^= (t + imul(t ^ (t >> 7), t | 61)) & M32
        return ((t ^ (t >> 14)) & M32) / 4294967296.0

    def uniform(self, lo, hi):
        return lo + (hi - lo) * self()


def hash32(s):
    h = 0x811C9DC5
    for ch in str(s):
        h ^= ord(ch)
        h = imul(h, 0x01000193)
    return h & M32


# ---------------------------------------------------------------- colour
def hex_rgb(h, d):
    if not isinstance(h, str):
        return d
    h = h.replace("#", "")
    if len(h) != 6:
        return d
    try:
        return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)]
    except ValueError:
        return d


def qcolor(c, a=255):
    return QColor(max(0, min(255, trunc(c[0]))), max(0, min(255, trunc(c[1]))),
                  max(0, min(255, trunc(c[2]))), max(0, min(255, trunc(a))))


def color_at(fx, inst, t, lut):
    c = fx["color"]
    if c["mode"] == "palette":
        idx = trunc((((t + inst.flow + (c.get("lut_offset") or 0)) % 1) + 1) % 1 * 256) & 255
        return lut[idx]
    c1 = hex_rgb(c.get("c1"), [255, 255, 255])
    if c["mode"] == "gradient":
        c2 = hex_rgb(c.get("c2"), c1)
        sf = 0 if c.get("start_fraction") is None else float(c["start_fraction"])
        if t <= sf:
            return c1
        k = (t - sf) / max(1e-6, 1 - sf)
        return [c1[0] + (c2[0] - c1[0]) * k, c1[1] + (c2[1] - c1[1]) * k, c1[2] + (c2[2] - c1[2]) * k]
    return c1


def color_pair(fx, lut):
    c = fx["color"]
    if c["mode"] == "palette":
        a = trunc(128 if c.get("lut_index") is None else c["lut_index"]) & 255
        b = trunc(a if c.get("lut_index2") is None else c["lut_index2"]) & 255
        return [list(lut[a]), list(lut[b])]
    c1 = hex_rgb(c.get("c1"), [255, 255, 255])
    return [c1, hex_rgb(c.get("c2"), c1) if c["mode"] == "gradient" else c1]


# ---------------------------------------------------------------- geometry
def angle_deg_qt(dx, dy):
    return math.atan2(-dy, dx) / D


def norm(dx, dy):
    d = math.sqrt(dx * dx + dy * dy)
    return [dx / d, dy / d] if d > 0.001 else [1.0, 0.0]


def rot(v, deg):
    c, s = math.cos(deg * D), math.sin(deg * D)
    return [v[0] * c - v[1] * s, v[0] * s + v[1] * c]


def seg_dist(px, py, x0, y0, x1, y1):
    dx, dy = x1 - x0, y1 - y0
    L = dx * dx + dy * dy
    t = ((px - x0) * dx + (py - y0) * dy) / L if L > 0 else 0
    t = max(0.0, min(1.0, t))
    ex, ey = x0 + dx * t - px, y0 + dy * t - py
    return math.sqrt(ex * ex + ey * ey)


# ---------------------------------------------------------------- schema
PRIMS = ["ribbon", "arc", "beam", "sprite", "particles", "glow", "pulse", "ghost", "weapon"]
PARAM_DEFAULTS = {
    "ribbon": dict(max_points=50, min_dist=2, decay=2, taper=True, w_tail=1, w_head=5, alpha=220, head_glow_r=1, head_dot_r=1),
    "arc": dict(radius=42, span=170, width=6.5, tail=0.95, segs=16, grow=0.85, core_alpha=0.7, core_width=0.3, orient="motion",
                angle_deg=0, placement="anchor", back=51, lead=26),
    "beam": dict(length=200, w_start0=6, w_start1=6, w_end0=2, w_end1=2, segments=1, glow=0, glow_color="", pulse_hz=0,
                 jitter=0, detach_ticks=0, grow_ticks=0, tip_fade=0),
    # Blade only: lodge_ms = how long a non-piercing blade stays stuck in the
    # target it hits (0 = it ends on the hit); blade_orient motion = the tip
    # points where it moves, angle = it holds blade_angle_deg (0 = right,
    # 90 = down; Flip mirrors it).
    "sprite": dict(shape="orb", radius=3, stretch=1, hot=False, halo=False, fade=True, trail_len=5, glow=100, glow_size=100,
                   lodge_ms=1500, blade_orient="motion", blade_angle_deg=90),
    "particles": dict(mode="burst", count=12, rate_per_s=60, angle_deg=0, spread_deg=30, speed_min=50, speed_max=150, gravity=0,
                      drag=1, size_min=3, size_max=3, size_over_life="shrink", life_min_ms=200, life_max_ms=400),
    "glow": dict(r_start=6, r_end=6, a_center=140, a_mid=60, mid=0.4, core_r=0, fade="out", pulse_hz=0),
    # Radial pulse: rings that expand from r_start to r_end over expand_ms
    # (see pulse_rings).  stretch_x / stretch_y stretch them into ellipses
    # (radius multipliers, 1 = round) tilted by tilt_deg, like an orbit's
    # radius X / Y (pulse_shape).  rings = how many, gap_ms apart (0 = one every
    # gap_ms for as long as the effect lasts).
    "pulse": dict(r_start=0, r_end=120, width=6, width_end=2, expand_ms=400, rings=1, gap_ms=200, ease="out",
                  fade="out", glow=8, fill_alpha=0, stretch_x=1, stretch_y=1, tilt_deg=0),
    "ghost": dict(interval=2, ghost_life=14, alpha=150, max=12),
    "weapon": dict(to_anchor="wtip", width=6),
}
MOTION_DEFAULTS = dict(kind="attached", aim="target", angle_deg=0, aim_offset_deg=0, speed=8, turn_deg=6, amplitude=55,
                       freq=0.18, orbit_rx=46, orbit_ry=46, orbit_deg=1.12, orbit_dir="clockwise", path="")


def orbit_step(m):
    """Degrees an orbit turns this tick: orbit_deg, reversed for
    orbit_dir "anticlockwise" (fxkit.js orbitStep).  Clockwise / anticlockwise
    as seen on screen; Flip mirrors it like the rest of the effect."""
    return float(m.get("orbit_deg") or 0) * (-1.0 if m.get("orbit_dir") == "anticlockwise" else 1.0)


COLOR_DEFAULTS = dict(mode="palette", lut_index=128, lut_index2=128, lut_offset=0, flow_speed=0.008, c1="#ffffff",
                      c2="#ff2200", start_fraction=0)
# blockable / deflectable (FXK.BATTLE_DEFAULTS): whether the other fighter's
# defences can stop this effect.  Block = defend action, special stance,
# parry stance, Intercept block / destroy; deflect = Intercept deflect.  Off =
# that defence ignores it and the hit lands.
BATTLE_DEFAULTS = dict(deals_damage=False, damage=1, pierce=False, rehit_ticks=0, knockback=0,
                       blockable=True, deflectable=True)
# Intercept settings (fx.intercept): the auto-projectile tracker, mirrors
# FXK.INTERCEPT_DEFAULTS.  Only for projectiles (travel, homing or zigzag
# motion): an enemy projectile within `radius` px is chased (up to
# `turn_deg`/tick); within `contact` px the two collide:
#   block    both nullified
#   deflect  the enemy projectile ("enemy") or both ("both") fly off along
#            their combined momentum; hurts_owner turns the deflected enemy
#            projectile against the fighter who fired it
#   destroy  the enemy projectile is nullified, this one keeps going
#   clash    beats every non-clash projectile; against another clash one,
#            knockback decides (see CLASH_KB_MARGIN / intercept_step)
INTERCEPT_DEFAULTS = dict(enabled=False, radius=90, turn_deg=10, contact=10, mode="block", deflect_who="enemy",
                          hurts_owner=False)
# Flip (fx.flip, FXK.FLIP_DEFAULTS): when enabled the effect is laid out
# toward the side the target is on (fx_facing), whichever way the fighter
# itself faces, and it plays as the mirror image (left <-> right only, never
# up <-> down) when that side is the other one from `facing` (the side the
# target was on when the effect was created, 1 right / -1 left): on top of
# offsets, entry points, paths and particle / fixed angles, flip mirrors the
# arc's sweep and the orbit's side and spin.  Target-aimed effects still aim
# at the target.  Off = everything follows the fighter's facing.
FLIP_DEFAULTS = dict(enabled=False, facing=1)


def flip_sign(fx, facing):
    """-1 when this effect plays mirrored for a fighter facing `facing`, else 1."""
    f = fx.get("flip") or {}
    if not f.get("enabled"):
        return 1
    return -1 if facing != (-1 if float(f.get("facing") or 1) < 0 else 1) else 1


def target_side(host):
    """1 when the target is right of the figure, -1 left (the facing when level)."""
    b = host.anchor("figure")
    dx = host.target[0] - b[0]
    return -1 if dx < -0.001 else 1 if dx > 0.001 else host.facing


def fx_facing(fx, host):
    """The facing an effect is laid out for: the target's side with Flip on,
    else the fighter's facing."""
    return target_side(host) if (fx.get("flip") or {}).get("enabled") else host.facing


# Follow direction (fx.follow_dir, FXK.bodyDeg): the whole effect turns
# toward the target at any angle.  As authored it points straight forward
# (along its facing); it turns by the angle from there to the figure ->
# target line (degrees, after mirroring, the way anchors turn): target above
# -> it turns up.  With Flip on as well it first mirrors to the target's side,
# so it only ever tilts up / down; without Flip a target behind turns it right
# round.  Offsets, entry points, facing / angle / weapon aims, the arc's
# angle, particle angles, orbits and paths all turn; target aims already
# track the target.
# The two ticks are independent:
#   Follow direction (follow_dir)  the offset and entry points swing round
#                                  the anchor (place_deg).
#   Each particle (follow_each)    every particle turns on its own sub-anchor
#                                  (its own centre) and stays where it was
#                                  placed; blades aim their tips at the
#                                  target (blade_pose).
# Either one turns the effect's own direction (body_deg); both together do
# both.  With Each particle the turn is measured from the particle's own spot
# (`at`) to the target, so every particle points at the target from where it
# is (aims, launches, arcs, beams, particle angles, paths, orbits, tilt).
def _deg_to_target(fx, host, b):
    dx, dy = host.target[0] - b[0], host.target[1] - b[1]
    if dx * dx + dy * dy < 1e-6:
        return 0.0
    a = math.degrees(math.atan2(dy, dx)) - (180.0 if fx_facing(fx, host) < 0 else 0.0)
    return (math.fmod(a, 360.0) + 540.0) % 360.0 - 180.0


def body_deg(fx, host, at=None):
    if fx.get("follow_each") and at is not None:
        return _deg_to_target(fx, host, at)
    if not (fx.get("follow_dir") or fx.get("follow_each")):
        return 0.0
    return _deg_to_target(fx, host, host.anchor("figure"))


def place_deg(fx, host):
    """The turn for where the effect sits (offset, entry points): only
    Follow direction swings it round its anchor."""
    return _deg_to_target(fx, host, host.anchor("figure")) if fx.get("follow_dir") else 0.0


def turn_by(v, deg):
    return rot(v, deg) if deg else v


def turn_sign(fx, host, d, at=None):
    """Sign for the facing-relative turns (fan, aim offset); times inst.flip,
    the arc / zigzag side.  Without Flip: the facing.  With Flip, a target aim
    heading backward counts as forward, so up / down never swaps."""
    f = fx_facing(fx, host)
    if not (fx.get("flip") or {}).get("enabled") or fx["motion"]["aim"] != "target":
        return f
    u = turn_by(d, -body_deg(fx, host, at))
    return -f if u[0] * f < 0 else f


# attack_px (normal attacks): how close the target must be for this attack
# to start, game px at 100 % character scale; 0 = the character's
# stats.basic_attack_radius (shooters: their shooting range).  laser/actions.py.
ACTION_DEFAULTS = dict(logic="any", cooldown_ms=0, conditions=[], chain_next="", chain_reset_ms=1000, fx_continuous=False,
                       movement="stand", move_speed_pct=100, anim_loops=1, back_stop_pct=80, attack_px=0)
# The action's Blink (action_settings[action].blink, FXK.BLINK_DEFAULTS): the
# fighter vanishes at start_frame and reappears after end_frame (-1 = the
# last frame) or when the action ends.  cooldown_ms: after it reappears, the
# action blinks again only once this long has passed (meanwhile it plays
# without vanishing).  Run by laser/blink.py.
BLINK_DEFAULTS = dict(enabled=False, start_frame=0, end_frame=-1, anchor="target", direction="behind", angle_deg=0.0,
                      proximity_px=60.0, flash=True, cooldown_ms=0.0)
BLINK_ANCHORS = ("target", "self")
BLINK_DIRECTIONS = ("behind", "front", "toward", "away", "random", "angle")
# Triggered-reaction FX (effect "action"): built in FX Studio under Actions >
# Triggered reactions.  "@retreat" plays for the whole Tactical retreat dash;
# "@blink:<action>" plays over <action> while its Blink is on.
RETREAT_KEY = "@retreat"
BLINK_KEY = "@blink:"


def normalize_blink(b):
    b = _fill(dict(b or {}), BLINK_DEFAULTS)
    if b.get("anchor") not in BLINK_ANCHORS:
        b["anchor"] = BLINK_DEFAULTS["anchor"]
    if b.get("direction") not in BLINK_DIRECTIONS:
        b["direction"] = BLINK_DEFAULTS["direction"]
    try:
        b["start_frame"] = max(0, jround(float(b.get("start_frame") or 0)))
    except (TypeError, ValueError):
        b["start_frame"] = 0
    try:
        b["end_frame"] = max(-1, jround(float(b.get("end_frame"))))
    except (TypeError, ValueError):
        b["end_frame"] = -1
    return b
# Character-level aiming (pack.aim): the whole frame turns so the weapon
# direction of the reference action (from -> to anchors, averaged over its
# frames) points at the target; the fighter always faces the target.
AIM_DEFAULTS = dict(enabled=False, source="attack_normal", from_anchor="haR", to_anchor="wtip", max_deg=75)
# Character-level "Damaged" (pack.damaged, FXK.DAMAGED_DEFAULTS): after a hit
# ticks HP the fighter is invincible for cooldown_ms (read by ai.py
# damage_cooldown_ticks straight from the pack).
DAMAGED_DEFAULTS = dict(cooldown_ms=0)
# start_frame / stop_frame: the action frames the set produces particles in
# (stop -1 = to the end); what it already spawned lives on as usual.
# order (sequential): forward, reverse, pingpong (1..n..1) or random (seeded).
ENTRY_DEFAULTS = dict(name="entry points", base="figure", mode="simultaneous", interval_ticks=6, points=[],
                      start_frame=0, stop_frame=-1, order="forward")
ENTRY_ORDERS = ("forward", "reverse", "pingpong", "random")
PATH_DEFAULTS = dict(name="path", points=[[0, 0]], smooth=True, ticks=30, orient="facing", end="stop", follow=False)


def _fill(dst, default):
    import copy
    for k, v in default.items():
        if k not in dst:
            dst[k] = copy.deepcopy(v)
    return dst


def normalize(fx):
    if fx.get("prim") not in PRIMS:
        fx["prim"] = "glow"
    # Files from before ∞ Always on was split out (no always_on, no cycles):
    # their continuous meant always on.
    if "always_on" not in fx and "cycles" not in fx and fx.get("continuous"):
        fx["always_on"], fx["continuous"] = True, False
    _fill(fx, dict(name=fx["prim"], tag="", enabled=True, start_frame=0, end_frame=-1, life_ticks=0, continuous=False,
                   always_on=False,
                   anchor="figure", offset=[0, 0], layer="front", blend="normal"))
    fx["emit"] = _fill(dict(fx.get("emit") or {}), dict(every_ticks=0, count=1, fan_deg=0))
    fx["cycles"] = _fill(dict(fx.get("cycles") or {}), CYCLE_DEFAULTS)
    fx["motion"] = _fill(dict(fx.get("motion") or {}), MOTION_DEFAULTS)
    fx["color"] = _fill(dict(fx.get("color") or {}), COLOR_DEFAULTS)
    fx["params"] = _fill(dict(fx.get("params") or {}), PARAM_DEFAULTS[fx["prim"]])
    fx["battle"] = _fill(dict(fx.get("battle") or {}), BATTLE_DEFAULTS)
    fx["intercept"] = _fill(dict(fx.get("intercept") or {}), INTERCEPT_DEFAULTS)
    fx["flip"] = _fill(dict(fx.get("flip") or {}), FLIP_DEFAULTS)
    fx["flip"]["facing"] = -1 if float(fx["flip"]["facing"] or 1) < 0 else 1
    fx["follow_dir"] = bool(fx.get("follow_dir"))
    fx["follow_each"] = bool(fx.get("follow_each"))
    if fx["prim"] == "ghost":
        fx["battle"]["deals_damage"] = False
    if fx["prim"] == "weapon":
        fx["motion"]["kind"] = "attached"
    fx.setdefault("id", "E" + str(id(fx)))
    normalize_keys(fx)
    return fx


# ---------------------------------------------------------------- character scale
# Image characters stand config.IMAGE_STAND_HEIGHT_PX tall (the roster's
# height).  An FX file records the scale it was authored at
# (space.game_px_per_image_px); when the character's game scale differs, every
# distance in the file is multiplied by the ratio so the FX keep exactly the
# size and placement they had around the figure.  FXK.rescaleEffects mirrors
# this (FX Studio applies it when it opens an older file).
_SCALE_PARAMS = {
    "ribbon": ("min_dist", "w_tail", "w_head", "head_glow_r", "head_dot_r"),
    "arc": ("radius", "width", "back", "lead"),
    "beam": ("length", "w_start0", "w_start1", "w_end0", "w_end1", "glow", "jitter"),
    "sprite": ("radius",),
    "particles": ("speed_min", "speed_max", "gravity", "size_min", "size_max"),
    "glow": ("r_start", "r_end", "core_r"),
    "pulse": ("r_start", "r_end", "width", "width_end", "glow"),
    "ghost": (),
    "weapon": ("width",),
}
_SCALE_MOTION = ("speed", "amplitude", "orbit_rx", "orbit_ry")
_SCALE_INTERCEPT = ("radius", "contact")


# ---------------------------------------------------------------- keyframes
# fx["keys"] = [{frame, ease, set: {"motion.speed": 100, "color.c1": "#ff0000"}}]
# (FX Studio: FXK.fxAt).  The effect's own settings are its values at its
# start frame; each key sets new values for the settings it lists, and each
# such setting moves from the previous point that set it to this key along the
# key's ease.  After its last key a setting holds.  Live instances sample the
# effect at their own action time (spawn tick + age), so a shot in flight
# follows the animation.
EASES = ("linear", "in", "out", "inout", "strong_in", "strong_out", "strong_inout", "hold", "bounce", "elastic")
KEY_GROUPS = ("params", "motion", "emit", "color", "battle", "intercept")


def _bounce_out(u):
    n, d = 7.5625, 2.75
    if u < 1 / d:
        return n * u * u
    if u < 2 / d:
        u -= 1.5 / d
        return n * u * u + 0.75
    if u < 2.5 / d:
        u -= 2.25 / d
        return n * u * u + 0.9375
    u -= 2.625 / d
    return n * u * u + 0.984375


def ease(name, u):
    u = max(0.0, min(1.0, u))
    if name == "linear":
        return u
    if name == "in":
        return u * u
    if name == "out":
        return 1 - (1 - u) * (1 - u)
    if name == "strong_in":
        return u ** 4
    if name == "strong_out":
        return 1 - (1 - u) ** 4
    if name == "strong_inout":
        return 8 * u ** 4 if u < 0.5 else 1 - (-2 * u + 2) ** 4 / 2
    if name == "hold":
        return 0.0 if u < 1 else 1.0
    if name == "bounce":
        return _bounce_out(u)
    if name == "elastic":
        if u <= 0:
            return 0.0
        if u >= 1:
            return 1.0
        return 2 ** (-10 * u) * math.sin((u * 10 - 0.75) * (2 * math.pi / 3)) + 1
    return 2 * u * u if u < 0.5 else 1 - (-2 * u + 2) ** 2 / 2   # inout


def _keyable(v, path=None):
    """A value keys can hold: a number, a #rrggbb colour, or (path given) one
    of KEY_CHOICES[path] — FXK.keyableAt."""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        return math.isfinite(v)
    if isinstance(v, str) and len(v) == 7 and v[0] == "#" and hex_rgb(v, None) is not None:
        return True
    return path in KEY_CHOICES and v in KEY_CHOICES[path]


# Choice settings keys can switch: the value holds until the next key (no
# in-between), and instances already alive switch with it (motion_switch):
# an orbit keyed to travel launches from where it is.  FXK.KEY_CHOICES.
KEY_CHOICES = {"motion.kind": ["attached", "static", "orbit", "travel", "homing", "zigzag"],
               "motion.aim": ["target", "facing", "angle", "weapon"], "motion.orbit_dir": ["clockwise", "anticlockwise"]}


def normalize_keys(fx):
    out = []
    for k in fx.get("keys") or []:
        if not isinstance(k, dict) or not isinstance(k.get("set"), dict):
            continue
        try:
            frame = max(0, int(round(float(k.get("frame") or 0))))
        except (TypeError, ValueError):
            frame = 0
        out.append({"frame": frame, "ease": k.get("ease") if k.get("ease") in EASES else "inout",
                    "set": {p: v for p, v in k["set"].items() if _keyable(v, p)}})
    out.sort(key=lambda k: k["frame"])
    fx["keys"] = out
    return fx


def _get_path(fx, path):
    a, _, b = path.partition(".")
    o = fx.get(a)
    if not b:
        return o
    if a == "offset":
        try:
            return (o or [0, 0])[int(b)]
        except (IndexError, ValueError):
            return 0
    return (o or {}).get(b)


def _lerp_val(a, b, u):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return a + (b - a) * u
    if isinstance(a, str) and isinstance(b, str) and _keyable(a) and _keyable(b):
        A, B = hex_rgb(a, [255, 255, 255]), hex_rgb(b, [255, 255, 255])
        return "#" + "".join("%02x" % int(round(max(0, min(255, A[i] + (B[i] - A[i]) * u)))) for i in range(3))
    return a if u < 1 else b   # choices hold until the key


def sample_key(fx, path, tf):
    """The value of one setting at action frame tf (fractional) — FXK.sampleKey."""
    pts = [(max(0, fx.get("start_frame") or 0), _get_path(fx, path), "linear")]
    pts += [(k["frame"], k["set"][path], k["ease"]) for k in fx.get("keys") or [] if path in k["set"]]
    pts.sort(key=lambda q: q[0])
    if tf <= pts[0][0]:
        return pts[0][1]
    for i in range(len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]
        if tf < p1[0]:
            u = ease(p1[2], (tf - p0[0]) / (p1[0] - p0[0])) if p1[0] > p0[0] else 1.0
            return _lerp_val(p0[1], p1[1], u)
    return pts[-1][1]


def fx_at(fx, tf):
    """fx with every keyed setting at its value at action frame tf (fx itself
    when it has no keys) — FXK.fxAt."""
    keys = fx.get("keys")
    if not keys:
        return fx
    v = dict(fx)
    for g in KEY_GROUPS:
        v[g] = dict(fx.get(g) or {})
    v["offset"] = list(fx.get("offset") or [0, 0])
    done = set()
    for key in keys:
        for path in key["set"]:
            if path in done:
                continue
            done.add(path)
            val = sample_key(fx, path, tf)
            a, _, b = path.partition(".")
            if not b:
                v[a] = val
            elif a == "offset":
                v["offset"][int(b)] = val
            elif a in KEY_GROUPS:
                v[a][b] = val
    return v


def rescale_effects(effects, lib, r):
    """Multiply every game-px distance in effects + entry sets + paths by r."""
    if abs(r - 1.0) < 1e-6:
        return
    for fx in effects:
        off = fx.get("offset") or [0, 0]
        fx["offset"] = [float(off[0] or 0) * r, float(off[1] or 0) * r]
        m = fx.get("motion") or {}
        for k in _SCALE_MOTION:
            if isinstance(m.get(k), (int, float)):
                m[k] = m[k] * r
        P = fx.get("params") or {}
        for k in _SCALE_PARAMS.get(fx.get("prim"), ()):
            if isinstance(P.get(k), (int, float)) and not isinstance(P.get(k), bool):
                P[k] = P[k] * r
        ic = fx.get("intercept") or {}
        for k in _SCALE_INTERCEPT:
            if isinstance(ic.get(k), (int, float)) and not isinstance(ic.get(k), bool):
                ic[k] = ic[k] * r
        scaled = (["offset.0", "offset.1"] + ["motion." + k for k in _SCALE_MOTION]
                  + ["params." + k for k in _SCALE_PARAMS.get(fx.get("prim"), ())]
                  + ["intercept." + k for k in _SCALE_INTERCEPT])
        for key in fx.get("keys") or []:
            for path in scaled:
                val = key.get("set", {}).get(path)
                if isinstance(val, (int, float)) and not isinstance(val, bool):
                    key["set"][path] = val * r
    for e in (lib or {}).get("entry_sets") or []:
        e["points"] = [[p[0] * r, p[1] * r] for p in e.get("points") or []]
    for p in (lib or {}).get("paths") or []:
        p["points"] = [[q[0] * r, q[1] * r] for q in p.get("points") or []]


def normalize_action(cfg):
    cfg = _fill(dict(cfg or {}), ACTION_DEFAULTS)
    cfg["blink"] = normalize_blink(cfg.get("blink"))
    return cfg


def normalize_entry_set(e):
    e = _fill(dict(e or {}), ENTRY_DEFAULTS)
    e["points"] = [[float(p[0] or 0), float(p[1] or 0)] for p in (e.get("points") or [])]
    e["start_frame"] = max(0, jround(float(e.get("start_frame") or 0)))
    e["stop_frame"] = max(-1, jround(float(e.get("stop_frame") if e.get("stop_frame") is not None else -1)))
    if e.get("order") not in ENTRY_ORDERS:
        e["order"] = "forward"
    return e


def normalize_path(p):
    p = _fill(dict(p or {}), PATH_DEFAULTS)
    p["points"] = [[float(q[0] or 0), float(q[1] or 0)] for q in (p.get("points") or [])] or [[0.0, 0.0]]
    p["points"][0] = [0.0, 0.0]
    p["ticks"] = max(1, jround((float(p.get("ticks") or 1))))
    return p


def action_kind(name):
    if name in ("idle", "run"):
        return "locomotion"
    if re.match(r"^attack_normal", name or ""):
        return "attack"
    return "triggered"


def can_continue(fx):
    """Whether fx can be ∞ Always on: it stays on the fighter (attached,
    static, orbit or path motion) and is not an arc."""
    return fx["prim"] != "arc" and fx["motion"]["kind"] in ("attached", "static", "orbit", "path")


def is_always_on(fx):
    """fx["always_on"] (∞ Always on): the effect never stops producing while
    its action plays, loop after loop (an always-on laser trail): one set kept
    alive with no end; End frame / Life ticks / Emit every are ignored and it
    does not fade out.  FXK.isAlwaysOn."""
    return bool(fx.get("always_on")) and can_continue(fx)


# fx["continuous"] (⟳ Continuous): the effect plays its whole sequence
# through, exactly as authored (start / end frame, Emit every, count, fan,
# entry points, Life ticks, keys, any motion), on its own clock: it carries
# on to the end when the action ends early, changes or restarts.  Each time
# the action reaches the start frame a run starts; replaying the action
# starts another alongside (at most CYCLE_MAX_RUNS per effect; the oldest
# stops).  A run lasts its sequence: start frame -> end frame, or the first
# copy's Life ticks if that is longer.  fx["cycles"] {enabled, count} then
# replays the whole sequence: -1 = forever, 0 = once, N = N more times.
CYCLE_DEFAULTS = dict(enabled=False, count=0)
CYCLE_MAX_RUNS = 8


def is_continuous(fx):
    return bool(fx.get("continuous"))


def life_t(inst):
    return min(1.0, inst.age / max(1, inst.win if inst.cont else inst.life))


# ---------------------------------------------------------------- figure size
# Every FX distance is authored at the figure's base size (FX Studio pscale 1)
# and multiplied by its on-screen size (host.pscale, combat.position_scale)
# the same way widths and radii are, so a fighter drawn 3x shows its FX as a
# 3x zoom of what was built.  Placement around the body (offsets, entry
# points, orbit radius, path shape, beam length / jitter, arc placement,
# ribbon spacing) follows the figure's current size; what is launched (shot
# speed, zigzag sway, particle speed / gravity, intercept range) keeps the
# size it was fired at (inst.ps).  FXK.hostScale mirrors this.
def host_scale(host):
    return float(getattr(host, "pscale", None) or 1.0)


# ---------------------------------------------------------------- entry sets / paths
def lib_find(host, key, ident):
    lib = host.lib
    if not lib or not ident:
        return None
    for it in lib.get(key) or []:
        if it.get("id") == ident:
            return it
    return None


def entry_set_of(fx, host):
    a = fx.get("anchor")
    if not isinstance(a, str) or not a.startswith("set:"):
        return None
    e = lib_find(host, "entry_sets", a[4:])
    return e if e and e["points"] else None


def entry_point(eset, k, host, deg=0.0, f=None):
    b = host.anchor(eset.get("base") or "figure")
    q = eset["points"][k] if k < len(eset["points"]) else [0, 0]
    ps = host_scale(host)
    o = turn_by([q[0] * ps * (host.facing if f is None else f), q[1] * ps], deg)
    return [b[0] + o[0], b[1] + o[1]]


def anchor_pos(fx, host, ep=None):
    eset = entry_set_of(fx, host)
    a = fx.get("anchor")
    deg = place_deg(fx, host)
    f = fx_facing(fx, host)
    if eset:
        p = entry_point(eset, (ep if ep is not None else 0) % len(eset["points"]), host, deg, f)
    elif isinstance(a, str) and a.startswith("set:"):
        p = host.anchor("figure")
    else:
        p = host.anchor(a)
    off = fx.get("offset") or [0, 0]
    ps = host_scale(host)
    o = turn_by([float(off[0] or 0) * ps * f, float(off[1] or 0) * ps], deg)
    return [p[0] + o[0], p[1] + o[1]]


def orbit_pos(inst, host, c):
    """Orbit position around centre c (flip mirrors its side and spin)."""
    m, ps = inst.fx["motion"], host_scale(host)
    o = turn_by([math.cos(inst.orbitA * D) * m["orbit_rx"] * ps * inst.flip, math.sin(inst.orbitA * D) * m["orbit_ry"] * ps],
                body_deg(inst.fx, host, c))
    return [c[0] + o[0], c[1] + o[1]]


def path_line(path):
    P = path["points"]
    if len(P) < 2:
        return {"pts": [[0, 0], [0, 0]], "cum": [0, 0], "len": 0}
    if not path.get("smooth") or len(P) < 3:
        pts = [list(q) for q in P]
    else:
        pts = []
        for i in range(len(P) - 1):
            p0, p1, p2, p3 = P[max(0, i - 1)], P[i], P[i + 1], P[min(len(P) - 1, i + 2)]
            for k in range(12):
                t = k / 12.0
                t2, t3 = t * t, t * t * t
                pts.append([0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                                   + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                            0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                                   + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)])
        pts.append(list(P[-1]))
    cum = [0.0]
    for j in range(1, len(pts)):
        cum.append(cum[-1] + math.hypot(pts[j][0] - pts[j - 1][0], pts[j][1] - pts[j - 1][1]))
    return {"pts": pts, "cum": cum, "len": cum[-1]}


def path_at(pl, u):
    n = len(pl["pts"])
    d = max(0.0, min(1.0, u)) * pl["len"]
    i = 1
    while i < n - 1 and pl["cum"][i] < d:
        i += 1
    a, b = pl["pts"][i - 1], pl["pts"][i]
    seg = pl["cum"][i] - pl["cum"][i - 1]
    f = (d - pl["cum"][i - 1]) / seg if seg > 1e-9 else 0.0
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f], norm(b[0] - a[0], b[1] - a[1])


def path_matrix(path, host, d, deg=0.0, f=None):
    f = host.facing if f is None else f
    last = path["points"][-1]
    if path.get("orient") != "aim" or (not last[0] and not last[1]):
        if not deg:
            return [f, 0, 0, 1]
        c0, s0 = math.cos(deg * D), math.sin(deg * D)
        return [c0 * f, -s0, s0 * f, c0]
    th = math.atan2(d[1], d[0]) - math.atan2(last[1], last[0] * f)
    c, s = math.cos(th), math.sin(th)
    return [c * f, -s, s * f, c]


def path_step(inst, host):
    path, pl = inst.path, inst.pl
    k = inst.age / path["ticks"]
    if path.get("follow"):
        inst.po = anchor_pos(inst.fx, host, inst.ep)
    if path.get("end") == "loop":
        k = k - math.floor(k)
    if k > 1 and path.get("end") == "continue" and pl["len"] > 0:
        e, ld = path_at(pl, 1)
        local = [e[0] + ld[0] * (k - 1) * pl["len"], e[1] + ld[1] * (k - 1) * pl["len"]]
    else:
        local, ld = path_at(pl, k)
    ps = host_scale(host)
    local = [local[0] * ps, local[1] * ps]
    M = inst.pm
    inst.x = inst.po[0] + M[0] * local[0] + M[1] * local[1]
    inst.y = inst.po[1] + M[2] * local[0] + M[3] * local[1]
    wd = norm(M[0] * ld[0] + M[1] * ld[1], M[2] * ld[0] + M[3] * ld[1])
    inst.dir = wd


# ---------------------------------------------------------------- instances
def aim_dir(fx, host, x, y):
    m, f = fx["motion"], fx_facing(fx, host)
    if m["aim"] == "target":
        return norm(host.target[0] - x, host.target[1] - y)
    if m["aim"] == "angle":
        v = [math.cos(m["angle_deg"] * D) * f, math.sin(m["angle_deg"] * D)]
    elif m["aim"] == "weapon":
        v = [math.sin(host.wang * D) * f, -math.cos(host.wang * D)]
    else:
        v = [float(f), 0.0]
    return turn_by(v, body_deg(fx, host, (x, y)))


class Inst:
    __slots__ = ("fx", "x", "y", "px", "py", "vx", "vy", "dir", "age", "life", "seed", "r", "flow", "dead", "hist",
                 "trail", "parts", "ghosts", "acc", "facing", "flip", "orbitA", "phase", "zx", "zy", "hits", "last_hit", "ep",
                 "path", "pl", "po", "pm", "centre_deg", "x2", "y2", "cont", "win", "open", "hit_targets",
                 "chase", "bvx", "bvy", "free", "src", "t0", "fms", "spd", "ps", "ring_hits",
                 "clash_with", "cvx", "cvy", "lodge", "mk", "ma", "run", "tgt")

    def __init__(self):
        self.mk = self.ma = None   # motion kind / aim at the last tick (motion_switch)
        self.run = False       # spawned by a Continuous run
        self.tgt = None        # Each in place: the target this blade aims at (blade_pose)
        self.lodge = None      # blade stuck in the target it hit (blade_lodge)
        self.chase = False     # intercept: steering at an enemy projectile
        self.bvx = self.bvy = 0.0   # its own velocity from before the chase
        self.free = False      # deflected: flies straight on
        self.clash_with = None  # clash: the enemy instance it is locked with
        self.cvx = self.cvy = 0.0   # its velocity from before the clash
        self.path = None
        self.cont = False
        self.win = 1
        self.open = False
        self.x2 = self.y2 = 0.0
        self.centre_deg = 0.0
        self.flip = 1
        self.src = None        # the authored effect (identity); fx is its keyframed view
        self.t0 = 0
        self.fms = 100.0
        self.spd = 0.0
        self.ps = 1.0          # figure size when fired (host_scale)
        self.ring_hits = None  # pulse: {(ring, target slot)} already hit


def emit_particles(inst, fx, host, n):
    P, cp = fx["params"], color_pair(fx, host.lut)
    spread, base = P["spread_deg"] * D, P["angle_deg"] * D
    if inst.facing < 0:
        base = math.pi - base
    base += body_deg(fx, host, (inst.x, inst.y)) * D   # Follow direction / Each particle: turns toward the target
    smin = float(P["speed_min"]) * inst.ps
    smax = max(smin, float(P["speed_max"]) * inst.ps)
    s0 = max(0.5, float(P["size_min"]))
    s1 = max(s0, float(P["size_max"]))
    l0 = max(1.0, float(P["life_min_ms"]))
    l1 = max(l0, float(P["life_max_ms"]))
    for _ in range(n):
        a = base + inst.r.uniform(-spread / 2, spread / 2)
        spd = inst.r.uniform(smin, smax) if smax > smin else smin
        life_ms = inst.r.uniform(l0, l1)
        inst.parts.append(dict(x=inst.x, y=inst.y, vx=math.cos(a) * spd, vy=math.sin(a) * spd, age=0,
                               life=max(1, trunc(life_ms / TICK_MS)), s0=s0, s1=s1, rgb1=cp[0], rgb2=cp[1], hits=0,
                               last_hit=-1e9))


def spawn(fx, host, window_ticks, seed, idx, n, ep):
    m = fx["motion"]
    p = anchor_pos(fx, host, ep)
    d = aim_dir(fx, host, p[0], p[1])
    ts = turn_sign(fx, host, d, p)
    if n > 1 and fx["emit"]["fan_deg"]:
        d = rot(d, (-fx["emit"]["fan_deg"] / 2 + fx["emit"]["fan_deg"] * idx / (n - 1)) * ts)
    if m["aim_offset_deg"]:
        d = rot(d, m["aim_offset_deg"] * ts)
    life = fx["life_ticks"] if fx["life_ticks"] > 0 else max(1, window_ticks)
    inst = Inst()
    inst.fx = fx
    inst.x, inst.y = p[0], p[1]
    inst.px, inst.py = p[0], p[1]
    inst.vx = inst.vy = 0.0
    inst.dir = d
    inst.age = 0
    inst.life = life
    inst.seed = seed & M32
    inst.r = Rng(seed)
    inst.flow = 0.0
    inst.dead = False
    inst.hist, inst.trail, inst.parts, inst.ghosts = [], [], [], []
    inst.acc = 0.0
    ef = fx_facing(fx, host)
    inst.facing = ef
    inst.flip = flip_sign(fx, ef)
    side = inst.flip * ts * ef   # arc / zigzag side of its line (turn_sign)
    inst.orbitA = inst.phase = inst.zx = inst.zy = 0.0
    inst.hits = 0
    inst.last_hit = -1e9
    inst.ep = ep
    inst.tgt = aim_target(fx, host)
    spd = float(m["speed"] or 0)
    ps = host_scale(host)
    inst.ps = ps     # the figure's size when fired: what is launched keeps it
    inst.spd = spd   # keyframed speed: move_inst rescales the velocity when it changes
    if m["kind"] == "path":
        inst.path = lib_find(host, "paths", m.get("path"))
        if inst.path:
            inst.pl = path_line(inst.path)
            inst.po = list(p)
            inst.pm = path_matrix(inst.path, host, d, body_deg(fx, host, p), ef)
    if m["kind"] in ("travel", "homing", "zigzag"):
        inst.vx, inst.vy = d[0] * spd * ps, d[1] * spd * ps
    if m["kind"] == "zigzag":
        pr = [-d[1] * side, d[0] * side] if spd > 0.001 else [0, side]
        inst.zx, inst.zy = pr[0] * m["amplitude"] * ps, pr[1] * m["amplitude"] * ps
        inst.phase = math.pi * idx if n > 1 else 0.0
    if m["kind"] == "orbit":
        inst.orbitA = 360.0 * idx / max(1, n)
        inst.x, inst.y = orbit_pos(inst, host, p)
    if fx["prim"] == "arc":
        P = fx["params"]
        if P["orient"] == "angle":
            od = turn_by([math.cos(P["angle_deg"] * D) * ef, math.sin(P["angle_deg"] * D)], body_deg(fx, host, p))
        else:
            od = d
        # Which side of its line the crescent sits (see turn_sign).
        sd = inst.flip if P["orient"] == "angle" else side
        inst.centre_deg = angle_deg_qt(-od[1] * sd, od[0] * sd)
        tg = host.target
        if P["placement"] == "wrap_target":
            inst.x, inst.y = tg[0] - od[0] * P["back"] * ps, tg[1] - od[1] * P["back"] * ps
        elif P["placement"] == "through_target":
            R = P["radius"] * ps * sd
            inst.x = tg[0] + od[1] * R - od[0] * P["lead"] * ps
            inst.y = tg[1] - od[0] * R - od[1] * P["lead"] * ps
    if fx["prim"] == "particles" and fx["params"]["mode"] == "burst":
        emit_particles(inst, fx, host, trunc(fx["params"]["count"]))
    if fx["prim"] == "pulse":
        inst.ring_hits = set()
    if fx["prim"] == "weapon":
        e2 = host.anchor(fx["params"]["to_anchor"])
        inst.x2, inst.y2 = e2[0], e2[1]
    inst.px, inst.py = inst.x, inst.y
    inst.mk, inst.ma = m["kind"], m["aim"]   # keyed switches compare against these (motion_switch)
    return inst


MOVERS = ("travel", "homing", "zigzag")
LAUNCH_LIFE = 220


def motion_switch(inst, host):
    """A key switched an alive instance's motion (or aim): it changes from
    where it is (FXK motionSwitch).  Into travel / homing / zigzag it launches
    along its Aim at the keyed Speed; coming off the fighter (from attached /
    static / orbit) it is a shot from then on, living Life ticks from the
    launch (0 = LAUNCH_LIFE).  Into orbit it carries on round its anchor from
    its own angle; into attached / static it stops.  Returns True when an
    always-on instance launched (its set is spent)."""
    fx = inst.fx
    m = fx["motion"]
    frm, was_cont = inst.mk, bool(inst.cont)
    inst.mk, inst.ma = m["kind"], m["aim"]
    if inst.free or inst.lodge is not None or fx["prim"] == "weapon" or inst.age >= inst.life:
        return False
    ps = inst.ps or 1.0
    if m["kind"] in MOVERS:
        d = aim_dir(fx, host, inst.x, inst.y)
        at = (inst.x, inst.y)
        if frm not in MOVERS and inst.tgt is not None:
            # Each particle blade: it launches from where it is drawn, along
            # where it points (blade_pose).
            bx, by, ba = blade_pose(inst, host_scale(host))
            inst.x = inst.px = bx
            inst.y = inst.py = by
            d, at = [math.cos(ba), math.sin(ba)], (bx, by)
        if m["aim_offset_deg"]:
            d = rot(d, m["aim_offset_deg"] * turn_sign(fx, host, d, at))
        spd = float(m["speed"] or 0)
        inst.dir, inst.spd = d, spd
        inst.vx, inst.vy = d[0] * spd * ps, d[1] * spd * ps
        if m["kind"] == "zigzag":   # as spawn: its side of the new line
            side = inst.flip * turn_sign(fx, host, d, at) * inst.facing
            pr = (-d[1] * side, d[0] * side) if spd > 0.001 else (0.0, side)
            inst.zx, inst.zy = pr[0] * m["amplitude"] * ps, pr[1] * m["amplitude"] * ps
            inst.phase = 0.0
        if frm not in MOVERS:
            inst.cont = inst.open = False
            inst.trail = []
            inst.life = inst.age + (fx["life_ticks"] if fx["life_ticks"] > 0 else LAUNCH_LIFE)
            return was_cont
        return False
    inst.vx = inst.vy = 0.0
    if m["kind"] == "orbit":
        c, hs = anchor_pos(fx, host, inst.ep), host_scale(host)
        v = turn_by([inst.x - c[0], inst.y - c[1]], -body_deg(fx, host, c))
        inst.orbitA = math.atan2(v[1] / max(1e-6, m["orbit_ry"] * hs), v[0] / max(1e-6, m["orbit_rx"] * hs * inst.flip)) / D
    return False


def move_inst(inst, host):
    fx, m = inst.fx, inst.fx["motion"]
    inst.px, inst.py = inst.x, inst.y
    inst.tgt = aim_target(fx, host)
    if m["kind"] == "attached":
        a = anchor_pos(fx, host, inst.ep)
        inst.x, inst.y = a[0], a[1]
    if m["kind"] == "path" and inst.path:
        path_step(inst, host)
        inst.vx, inst.vy = inst.x - inst.px, inst.y - inst.py
        return
    if m["kind"] in ("travel", "homing", "zigzag") and not inst.free:
        # Keyframed speed: an instance in flight follows it (direction kept).
        ns = float(m["speed"] or 0)
        if ns != inst.spd:
            cs = math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy)
            if cs > 1e-6 and inst.spd > 1e-6:
                f = ns / inst.spd
                inst.vx *= f
                inst.vy *= f
            else:
                inst.vx, inst.vy = inst.dir[0] * ns * inst.ps, inst.dir[1] * ns * inst.ps
            inst.spd = ns
    if fx["prim"] == "weapon":
        b2 = host.anchor(fx["params"]["to_anchor"])
        inst.x2, inst.y2 = b2[0], b2[1]
    elif m["kind"] == "travel":
        inst.x += inst.vx
        inst.y += inst.vy
    elif m["kind"] == "homing":
        spd = math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy) or float(m["speed"] or 0) * inst.ps
        want = math.atan2(host.target[1] - inst.y, host.target[0] - inst.x)
        cur = math.atan2(inst.vy, inst.vx)
        da = want - cur
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        lim = float(m["turn_deg"] or 0) * D
        cur += max(-lim, min(lim, da))
        inst.vx, inst.vy = math.cos(cur) * spd, math.sin(cur) * spd
        inst.x += inst.vx
        inst.y += inst.vy
    elif m["kind"] == "zigzag":
        lat = math.sin(inst.phase) * m["freq"]
        inst.x += inst.vx + inst.zx * lat
        inst.y += inst.vy + inst.zy * lat
        inst.phase += m["freq"]
    elif m["kind"] == "orbit":
        c = anchor_pos(fx, host, inst.ep)
        inst.orbitA += orbit_step(m)
        inst.x, inst.y = orbit_pos(inst, host, c)
    if m["kind"] in ("travel", "homing", "zigzag"):
        mdx, mdy = inst.x - inst.px, inst.y - inst.py
        if mdx * mdx + mdy * mdy > 1e-6:
            inst.dir = norm(mdx, mdy)
    elif fx["prim"] == "beam":
        d = aim_dir(fx, host, inst.x, inst.y)
        inst.dir = rot(d, m["aim_offset_deg"] * turn_sign(fx, host, d, (inst.x, inst.y))) if m["aim_offset_deg"] else d


# ---------------------------------------------------------------- intercept
# The auto-projectile tracker (fx.intercept) — FXK.interceptStep.
# host.shots: the enemy's live projectiles (Shot: x, y, vx, vy, dead), read
# only except `dead`, which marks one already taken this tick.
# host.on_intercept(inst, shot, mode, enemy_vel, hurts_owner) applies the
# result to the enemy projectile at its source.
#
# Clash mode (FXK.CLASH_*): an effect WITHOUT clash always loses to one with
# it — the clash projectile nullifies any non-clash projectile / bullet it
# touches, and a non-clash interceptor touching an enemy clash projectile is
# the one nullified.  Two clash projectiles compare battle.knockback (bullets
# count 0): more than CLASH_KB_MARGIN apart, the higher one nullifies the
# lower and keeps going; otherwise both freeze where they met, locked to each
# other, until one's life runs out or its owner is hit (the hit owner's
# projectile ends, FxDriver.update) — the survivor then resumes the motion it
# had before the clash.
DEFLECT_FAN_DEG = 15   # with deflect "both", the two fly apart this far either side
INTERCEPT_MOTIONS = ("travel", "homing", "zigzag")
CLASH_KB_MARGIN = 10.0


def can_intercept(fx):
    return fx["prim"] not in ("weapon", "ghost", "pulse") and fx["motion"]["kind"] in INTERCEPT_MOTIONS


def intercept_on(fx):
    return bool((fx.get("intercept") or {}).get("enabled")) and can_intercept(fx)


def clash_on(fx):
    """True when this effect intercepts in clash mode."""
    return intercept_on(fx) and fx["intercept"].get("mode") == "clash"


def fx_knockback(fx):
    try:
        return float((fx.get("battle") or {}).get("knockback") or 0)
    except (TypeError, ValueError):
        return 0.0


class Shot:
    """One enemy projectile in a side's snapshot: a built-in bullet
    (kind "bullet", ref = the live combat.Projectile) or an FX Studio
    instance (kind "fx", ref = the live Inst).  blockable / deflectable come
    from the effect's battle settings (built-in bullets are both); clash /
    knockback from its intercept mode and battle.knockback (bullets: no
    clash, knockback 0)."""
    __slots__ = ("x", "y", "vx", "vy", "dead", "kind", "ref", "blockable", "deflectable", "clash", "knockback")

    def __init__(self, x, y, vx, vy, kind, ref, blockable=True, deflectable=True, clash=False, knockback=0.0):
        self.x, self.y, self.vx, self.vy = float(x), float(y), float(vx), float(vy)
        self.dead = False
        self.kind, self.ref = kind, ref
        self.blockable, self.deflectable = bool(blockable), bool(deflectable)
        self.clash, self.knockback = bool(clash), float(knockback or 0)


def _shot_takes(s, mode):
    """Whether an intercept in `mode` may take shot s (FXK.shotTakes).  A
    clash interceptor takes anything; the others never go after an enemy
    clash projectile (they would lose to it)."""
    if mode == "clash":
        return True
    if s.clash:
        return False
    return s.deflectable if mode == "deflect" else s.blockable


def _shot_gone(s):
    """An FX shot whose instance already ended this tick (e.g. nullified by
    the other side's clash) can no longer touch anything."""
    return s.kind == "fx" and (s.ref.dead or s.ref.age >= s.ref.life)


def _nearest_shot(inst, host, r, mode=None, only_clash=False):
    best, bd, r2 = None, 0.0, r * r
    for s in getattr(host, "shots", None) or ():
        if s.dead or _shot_gone(s):
            continue
        if only_clash:
            if not s.clash:
                continue
        elif mode and not _shot_takes(s, mode):
            continue
        dx, dy = s.x - inst.x, s.y - inst.y
        d = dx * dx + dy * dy
        if d <= r2 and (best is None or d < bd):
            best, bd = s, d
    return best


def deflect_vels(inst, s, both):
    """Combined momentum: the two velocities added together.  Head-on at
    similar speeds they nearly cancel, so the enemy projectile is knocked
    sideways instead, to the side it hit on."""
    si = math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy)
    ss = math.sqrt(s.vx * s.vx + s.vy * s.vy)
    sx, sy = inst.vx + s.vx, inst.vy + s.vy
    sm = math.sqrt(sx * sx + sy * sy)
    side = 1 if inst.vx * (s.y - inst.y) - inst.vy * (s.x - inst.x) >= 0 else -1
    d = [sx / sm, sy / sm] if sm >= 0.25 * max(si, ss, 0.001) else rot(norm(inst.vx, inst.vy), 90 * side)
    de = rot(d, DEFLECT_FAN_DEG * side) if both else d
    dm = rot(d, -DEFLECT_FAN_DEG * side)
    return [de[0] * ss, de[1] * ss], [dm[0] * si, dm[1] * si]


def _straight_step(inst):
    inst.px, inst.py = inst.x, inst.y
    inst.x += inst.vx
    inst.y += inst.vy
    mdx, mdy = inst.x - inst.px, inst.y - inst.py
    if mdx * mdx + mdy * mdy > 1e-6:
        inst.dir = norm(mdx, mdy)


def _end_chase(inst):
    if inst.chase:
        inst.chase = False
        inst.vx, inst.vy = inst.bvx, inst.bvy


def _clash_lock(inst):
    """Freeze inst in a clash, remembering the motion it resumes after."""
    _end_chase(inst)
    inst.cvx, inst.cvy = inst.vx, inst.vy
    inst.px, inst.py = inst.x, inst.y


def _clash_hold(inst):
    """While locked: hold still until the partner ends (life out / its owner
    hit / nullified), then resume.  True while it is still held."""
    q = inst.clash_with
    if not (q.dead or q.age >= q.life or q.clash_with is not inst):
        inst.px, inst.py = inst.x, inst.y
        return True
    inst.clash_with = None
    inst.vx, inst.vy = inst.cvx, inst.cvy
    return False


def _clash_contact(inst, hit, cb):
    """inst (clash mode) touched shot `hit`.  Returns "lost" when inst is the
    one nullified, "locked" when the two clash, else None (hit nullified)."""
    if hit.clash:
        diff = fx_knockback(inst.fx) - hit.knockback
        if diff < -CLASH_KB_MARGIN:
            inst.age = max(inst.age, inst.life)
            return "lost"
        if diff <= CLASH_KB_MARGIN:
            q = hit.ref
            _clash_lock(inst)
            _clash_lock(q)
            inst.clash_with, q.clash_with = q, inst
            if cb:
                cb(inst, hit, "clash_lock", None, False)
            return "locked"
    if cb:
        cb(inst, hit, "clash", None, False)
    return None


def intercept_step(inst, host):
    """Runs before the instance moves; True when it moved the instance."""
    if inst.clash_with is not None and _clash_hold(inst):
        return True
    if inst.free:
        _straight_step(inst)
        return True
    fx = inst.fx
    if not intercept_on(fx):
        return False
    ic = fx["intercept"]
    mode = ic.get("mode")
    contact = max(0.0, float(ic.get("contact") or 0)) * inst.ps
    cb = getattr(host, "on_intercept", None)
    if mode != "clash" and _nearest_shot(inst, host, contact, only_clash=True) is not None:
        # A non-clash interceptor always loses to a clash projectile.
        inst.age = max(inst.age, inst.life)
        return True
    hit = _nearest_shot(inst, host, contact, mode)
    if hit is not None:
        hit.dead = True
        _end_chase(inst)
        if mode == "clash":
            res = _clash_contact(inst, hit, cb)
            if res is not None:
                return True
        elif mode == "deflect":
            both = ic.get("deflect_who") == "both"
            ev, mv = deflect_vels(inst, hit, both)
            if cb:
                cb(inst, hit, "deflect", ev, bool(ic.get("hurts_owner")))
            if both:
                inst.vx, inst.vy = mv[0], mv[1]
                inst.free = True
                _straight_step(inst)
                return True
        else:
            if cb:
                cb(inst, hit, mode, None, False)
            if mode == "block":
                inst.age = max(inst.age, inst.life)
                return True
    tgt = _nearest_shot(inst, host, max(0.0, float(ic.get("radius") or 0)) * inst.ps, mode)
    if tgt is None:
        _end_chase(inst)   # back to its own motion
        return False
    if not inst.chase:
        inst.chase = True
        inst.bvx, inst.bvy = inst.vx, inst.vy
    spd = math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy) or float(fx["motion"]["speed"] or 0) * inst.ps
    want = math.atan2(tgt.y - inst.y, tgt.x - inst.x)
    cur = math.atan2(inst.vy, inst.vx)
    da = want - cur
    while da > math.pi:
        da -= 2 * math.pi
    while da < -math.pi:
        da += 2 * math.pi
    lim = float(ic.get("turn_deg") or 0) * D
    cur += max(-lim, min(lim, da))
    inst.vx, inst.vy = math.cos(cur) * spd, math.sin(cur) * spd
    _straight_step(inst)
    return True


def tick_inst(inst, host):
    fx, P = inst.fx, inst.fx["params"]
    active = inst.age < inst.life
    if active and inst.lodge is not None:
        blade_follow(inst, host.hurts or [], inst.ps)
    elif active:
        if fx["prim"] in ("sprite", "beam"):
            inst.trail.append((inst.x, inst.y))
            while len(inst.trail) > max(0, trunc(P.get("trail_len") or 0)):
                inst.trail.pop(0)
        if not intercept_step(inst, host):
            move_inst(inst, host)
    inst.flow = (inst.flow + float(fx["color"].get("flow_speed") or 0)) % 1
    prim = fx["prim"]
    if prim == "ribbon":
        h = inst.hist
        if active:
            moved = True
            if h:
                lx, ly = h[-1]
                dx, dy = inst.x - lx, inst.y - ly
                md = P["min_dist"] * host_scale(host)
                moved = dx * dx + dy * dy >= md * md
            if moved:
                h.append((inst.x, inst.y))
                while len(h) > P["max_points"]:
                    h.pop(0)
            mx, my = inst.x - inst.px, inst.y - inst.py
            if mx * mx + my * my < 0.01:
                for _ in range(int(P["decay"])):
                    if len(h) > 1:
                        h.pop(0)
        else:
            for _ in range(max(1, int(P["decay"]))):
                if h:
                    h.pop(0)
        if not active and len(h) <= 1:
            inst.dead = True
    elif prim == "particles":
        if active and P["mode"] == "stream":
            inst.acc += P["rate_per_s"] * TICK_S
            k = trunc(inst.acc)
            if k > 0:
                inst.acc -= k
                emit_particles(inst, fx, host, k)
        drag = float(P["drag"])
        for q in inst.parts:
            q["vx"] *= drag
            q["vy"] = q["vy"] * drag + P["gravity"] * inst.ps * TICK_S
            q["x"] += q["vx"] * TICK_S
            q["y"] += q["vy"] * TICK_S
            q["age"] += 1
        inst.parts = [q for q in inst.parts if q["age"] < q["life"]]
        if not active and not inst.parts:
            inst.dead = True
    elif prim == "ghost":
        if active and inst.age % max(1, trunc(P["interval"])) == 0 and len(inst.ghosts) < P["max"]:
            inst.ghosts.append({"snap": host.snapshot(), "x": inst.x, "y": inst.y, "facing": host.facing, "age": 0})
        for gh in inst.ghosts:
            gh["age"] += 1
        inst.ghosts = [gh for gh in inst.ghosts if gh["age"] < P["ghost_life"]]
        if not active and not inst.ghosts:
            inst.dead = True
    elif prim == "pulse":
        # Rings already expanding finish after the effect's life ends.
        if not active and not pulse_rings(inst, inst.ps):
            inst.dead = True
    elif not active:
        inst.dead = True
    inst.age += 1


# ---------------------------------------------------------------- shapes (draw + hit)
def arc_segs(inst, ps):
    P, life, age, out = inst.fx["params"], inst.life, inst.age, []
    if age >= life:
        return out
    segs = trunc(P["segs"])
    half = P["span"] / 2.0
    start = inst.centre_deg - half
    step = P["span"] / segs
    half_life = life * P["grow"]
    if age <= half_life:
        tip, fade = age / half_life, 1.0
    else:
        tip, fade = 1.0, 1 - (age - half_life) / (life - half_life)
    for i in range(segs):
        st = (i + 0.5) / segs
        if st > tip:
            continue
        dft = tip - st
        if dft > P["tail"]:
            continue
        tt = 1 - dft / P["tail"]
        a = trunc(255 * (tt ** 0.6) * fade)
        if a < 4:
            continue
        # Flipped: the sweep grows the other way round (mirror image).
        a0 = inst.centre_deg + half - (i + 1) * step if inst.flip < 0 else start + i * step
        out.append((a0, step, P["width"] * (0.25 + 0.75 * tt) * ps, tt, a, st))
    return out


def beam_segs(inst, host, ps):
    fx, P, m = inst.fx, inst.fx["params"], inst.fx["motion"]
    fade = max(0.0, 1 - inst.age / inst.life)
    if fade <= 0:
        return None
    ux, uy = inst.dir
    hx, hy = inst.x, inst.y
    spd = math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy)
    detach = P["detach_ticks"] if P["detach_ticks"] > 0 else 1e9
    if m["kind"] in ("attached", "static", "orbit") or spd < 0.0001:
        reach = P["length"] * ps * (min(1.0, inst.age / P["grow_ticks"]) if P["grow_ticks"] > 0 else 1.0)
        hx, hy = inst.x + ux * reach, inst.y + uy * reach
    else:
        dist = spd * inst.age
        if inst.age < detach:
            reach = min(P["length"] * ps, dist)
        else:
            rd = min(P["length"] * ps, spd * detach)
            post = max(1, inst.life - detach)
            reach = max(0.0, rd * (1 - min(1.0, (inst.age - detach) / post)))
    if reach <= 0:
        return None
    prog = life_t(inst)
    wT = P["w_start0"] + (P["w_start1"] - P["w_start0"]) * prog
    wH = P["w_end0"] + (P["w_end1"] - P["w_end0"]) * prog
    pulse = 1.0
    if P["pulse_hz"] > 0:
        pulse = 0.65 + 0.35 * math.sin(2 * math.pi * P["pulse_hz"] * (inst.age * TICK_MS / 1000.0))
    c1, c2 = color_pair(fx, host.lut)
    segs = max(1, trunc(P["segments"]))
    jr = Rng((inst.seed + trunc(inst.age if inst.age != INF else 0)) & M32)
    tf = max(0.0, min(1.0, float(P.get("tip_fade") or 0)))   # fraction of the length, from the head, that fades out
    out = []
    for i in range(segs):
        t0, t1 = i / segs, (i + 1) / segs
        x0, y0 = hx - ux * reach * t0, hy - uy * reach * t0
        x1, y1 = hx - ux * reach * t1, hy - uy * reach * t1
        if P["jitter"] > 0:
            j = (jr() * 2 - 1) * P["jitter"] * ps
            x0 += -uy * j
            y0 += ux * j
            x1 += -uy * j
            y1 += ux * j
        out.append((x0, y0, x1, y1, (wH + (wT - wH) * t0) * ps,
                    [c2[0] + (c1[0] - c2[0]) * t0, c2[1] + (c1[1] - c2[1]) * t0, c2[2] + (c1[2] - c2[2]) * t0],
                    min(1.0, (t0 + t1) / 2 / tf) if tf > 0 else 1.0))
    # Smooth-draw info for straight beams: head and tail points, widths, colours, tip fade.
    info = {"hx": hx, "hy": hy, "tx": hx - ux * reach, "ty": hy - uy * reach,
            "wH": wH * ps, "wT": wT * ps, "c1": c1, "c2": c2, "tf": tf}
    return out, fade * pulse, info


def _pulse_ease(u, mode):
    return 1 - (1 - u) * (1 - u) if mode == "out" else u * u if mode == "in" else u


def _pulse_fade(u, mode):
    return 1 - u if mode == "out" else u if mode == "in" else math.sin(u * math.pi) if mode == "inout" else 1.0


def pulse_rings(inst, ps, age=None):
    """Live rings of a radial pulse at `age` (default: now), as
    [(ring index, radius, width, alpha 0..1)].  Ring k starts k * gap_ms
    into the effect (only while the effect still lasts) and grows from
    r_start to r_end over expand_ms (eased), its line going from width to
    width_end and fading by `fade`.  rings 0 = keep starting rings."""
    P = inst.fx["params"]
    age = inst.age if age is None else age
    if age < 0:
        return []
    exp = max(1.0, float(P["expand_ms"]) / TICK_MS)
    gap = max(1.0, float(P["gap_ms"]) / TICK_MS)
    n = trunc(P["rings"])
    out = []
    k = max(0, trunc((age - exp) / gap))
    while k * gap <= age and (n <= 0 or k < n) and k * gap < inst.life:
        u = (age - k * gap) / exp
        if 0 <= u < 1:
            e = _pulse_ease(u, P["ease"])
            r = (P["r_start"] + (P["r_end"] - P["r_start"]) * e) * ps
            w = (P["width"] + (P["width_end"] - P["width"]) * u) * ps
            out.append((k, max(0.0, r), max(0.0, w), _pulse_fade(u, P["fade"])))
        k += 1
    return out


PULSE_MIN_STRETCH = 0.05


def pulse_shape(inst, host):
    """(stretch_x, stretch_y, tilt_deg) of a pulse's rings: radius X / Y
    multipliers and the ellipse's tilt.  Flip mirrors the tilt and Follow
    direction turns it, as they do an orbit's ellipse (orbit_pos)."""
    P = inst.fx["params"]
    sx = max(PULSE_MIN_STRETCH, float(P.get("stretch_x", 1)))
    sy = max(PULSE_MIN_STRETCH, float(P.get("stretch_y", 1)))
    tilt = float(P.get("tilt_deg", 0) or 0) * inst.flip + body_deg(inst.fx, host, (inst.x, inst.y))
    return sx, sy, tilt


def pulse_scale_toward(sx, sy, tilt, dx, dy):
    """How far a ring of radius 1 reaches toward offset (dx, dy): the
    ellipse's radius in that direction."""
    lx, ly = rot([dx, dy], -tilt)
    d = math.hypot(lx, ly)
    if d < 1e-6:
        return min(sx, sy)
    rho = math.hypot(lx / sx, ly / sy)
    return d / rho


def _hit_shape(inst, tx, ty, hr, ps, host):
    prim, P = inst.fx["prim"], inst.fx["params"]
    if prim == "ribbon":
        h, n = inst.hist, len(inst.hist)
        for i in range(1, n):
            t = i / n
            w = (P["w_tail"] + (P["w_head"] - P["w_tail"]) * t if P["taper"] else P["w_head"]) * ps
            if seg_dist(tx, ty, h[i - 1][0], h[i - 1][1], h[i][0], h[i][1]) <= hr + w / 2:
                return True
        return False
    if prim == "arc":
        r2 = P["radius"] * ps
        for q in arc_segs(inst, ps):
            a0, a1 = q[0] * D, (q[0] + q[1]) * D
            if seg_dist(tx, ty, inst.x + r2 * math.cos(a0), inst.y - r2 * math.sin(a0),
                        inst.x + r2 * math.cos(a1), inst.y - r2 * math.sin(a1)) <= hr + q[2] / 2:
                return True
        return False
    if prim == "beam":
        b = beam_segs(inst, host, ps)
        if not b:
            return False
        for q in b[0]:
            if seg_dist(tx, ty, q[0], q[1], q[2], q[3]) <= hr + max(1, q[4]) / 2:
                return True
        return False
    if prim == "sprite":
        if inst.age >= inst.life:
            return False
        if P["shape"] == "blade":   # the whole blade, tip to pommel, half-width wide
            if inst.lodge is not None:
                return False
            L = blade_length(P, ps)
            bx, by, a = blade_pose(inst, ps)
            return seg_dist(tx, ty, bx, by, bx - math.cos(a) * L, by - math.sin(a) * L) \
                <= hr + max(0.5, float(P["radius"])) * ps
        dx, dy = inst.x - tx, inst.y - ty
        return dx * dx + dy * dy <= hr * hr
    if prim == "glow":
        if inst.age >= inst.life:
            return False
        t = life_t(inst)
        gr = max(P["core_r"], P["r_start"] + (P["r_end"] - P["r_start"]) * t) * ps
        return math.hypot(inst.x - tx, inst.y - ty) <= hr + gr
    if prim == "weapon":
        if inst.age >= inst.life:
            return False
        return seg_dist(tx, ty, inst.x, inst.y, inst.x2, inst.y2) <= hr + P["width"] * ps / 2
    return False


def _can_hit(b, obj_hits, obj_last, now):
    return now - obj_last >= b["rehit_ticks"] if b["rehit_ticks"] > 0 else obj_hits == 0


def resolve_hits(inst, host, ps):
    """host.hurts = [(x, y, r, target_key)]; host.on_hit(inst, damage, dx, dy,
    knockback, target_key) once per hit.  A non-piercing hit ends the instance
    (a hit particle is removed instead)."""
    b = inst.fx["battle"]
    hurts = host.hurts
    if not b["deals_damage"] or not hurts or inst.dead or inst.lodge is not None:
        return
    now = inst.age
    if inst.fx["prim"] == "pulse":
        # Each ring hits each target once, when its edge sweeps over it
        # (this tick's radius and last tick's, so a fast ring can't skip a
        # target), pushing outward from the centre.  Rings never end on a
        # hit: Pierce and Re-hit don't apply.
        # Stretched rings: the edge reaches r * the ellipse's radius in the
        # target's direction (pulse_scale_toward).
        sx, sy, tilt = pulse_shape(inst, host)
        prev = {k: r for (k, r, _w, _a) in pulse_rings(inst, ps, inst.age - 1)}
        for (k, r, w, _a) in pulse_rings(inst, ps):
            rp = prev.get(k, r)
            for i, (hx, hy, hr, key) in enumerate(hurts):
                # The hurt key is the target's snapshot position (it moves):
                # remember the target by its slot instead.
                if (k, i) in inst.ring_hits:
                    continue
                dx, dy = hx - inst.x, hy - inst.y
                d = math.hypot(dx, dy)
                f = pulse_scale_toward(sx, sy, tilt, dx, dy)
                lo, hi = min(r, rp) * f - w / 2, max(r, rp) * f + w / 2
                if lo - hr <= d <= hi + hr:
                    inst.ring_hits.add((k, i))
                    inst.hits += 1
                    inst.last_hit = now
                    ux, uy = (dx / d, dy / d) if d > 0.001 else (inst.dir[0], inst.dir[1])
                    host.on_hit(inst, b["damage"], ux, uy, b["knockback"], key)
        return
    if inst.fx["prim"] == "particles":
        keep = []
        for q in inst.parts:
            hit_key = None
            size = max(0.5, q["s0"])
            for (hx, hy, hr, key) in hurts:
                if math.hypot(q["x"] - hx, q["y"] - hy) <= hr + size / 2:
                    hit_key = key
                    break
            if hit_key is None or not _can_hit(b, q["hits"], q["last_hit"], now):
                keep.append(q)
                continue
            q["hits"] += 1
            q["last_hit"] = now
            d = norm(q["vx"], q["vy"])
            host.on_hit(inst, b["damage"], d[0], d[1], b["knockback"], hit_key)
            if b["pierce"]:
                keep.append(q)
        inst.parts = keep
        return
    if not _can_hit(b, inst.hits, inst.last_hit, now):
        return
    for (hx, hy, hr, key) in hurts:
        if _hit_shape(inst, hx, hy, hr, ps, host):
            inst.hits += 1
            inst.last_hit = now
            host.on_hit(inst, b["damage"], inst.dir[0], inst.dir[1], b["knockback"], key)
            if not b["pierce"]:
                if can_lodge(inst):
                    blade_lodge(inst, hx, hy, hr, ps)
                else:
                    inst.age = max(inst.age, inst.life)
            return


# ---------------------------------------------------------------- drawing (QPainter)
def _pen(color, width):
    pen = QPen(color)
    pen.setWidthF(max(0.0, width))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _line(p, x0, y0, x1, y1):
    p.drawLine(trunc(x0), trunc(y0), trunc(x1), trunc(y1))


def _radial_ellipse(p, cx, cy, r, stops, ir):
    g = QRadialGradient(cx, cy, max(0.0001, r))
    for at, col in stops:
        g.setColorAt(at, col)
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(trunc(cx - ir), trunc(cy - ir), ir * 2, ir * 2)
    p.setBrush(Qt.NoBrush)


def _draw_ribbon(p, inst, host, ps):
    fx, P, tl = inst.fx, inst.fx["params"], inst.hist
    n = len(tl)
    if n <= 1:
        return
    inv = 1.0 / n
    for i in range(1, n):
        t = i * inv
        c = color_at(fx, inst, t, host.lut)
        if P["taper"]:
            p.setPen(_pen(qcolor(c, P["alpha"] * t), (P["w_tail"] + (P["w_head"] - P["w_tail"]) * t) * ps))
        else:
            p.setPen(_pen(qcolor(c, P["alpha"]), P["w_head"] * ps))
        _line(p, tl[i - 1][0], tl[i - 1][1], tl[i][0], tl[i][1])
    hx, hy = trunc(tl[-1][0]), trunc(tl[-1][1])
    hc = [trunc(v) for v in color_at(fx, inst, 1, host.lut)]
    gr = P["head_glow_r"] * ps
    igr = trunc(gr)
    if igr > 0:
        _radial_ellipse(p, hx, hy, gr, [(0, qcolor(hc, 140)), (0.4, qcolor(hc, 60)), (1, qcolor(hc, 0))], igr)
    dr = P["head_dot_r"] * ps
    idr = trunc(dr)
    if idr > 0:
        _radial_ellipse(p, hx, hy, dr, [(0, QColor(255, 255, 255, 200)), (0.5, qcolor(hc, 180)), (1, qcolor(hc, 100))], idr)


def _draw_arc(p, inst, host, ps):
    fx, P = inst.fx, inst.fx["params"]
    r2 = P["radius"] * ps
    rect = QRectF(inst.x - r2, inst.y - r2, r2 * 2, r2 * 2)
    p.setBrush(Qt.NoBrush)
    for q in arc_segs(inst, ps):
        a0, step, a = q[0], q[1], q[4]
        c = color_at(fx, inst, q[5], host.lut) if fx["color"]["mode"] == "palette" else color_pair(fx, host.lut)[0]
        path = QPainterPath()
        path.arcMoveTo(rect, a0)
        path.arcTo(rect, a0, step)
        p.setPen(_pen(qcolor(c, a), q[2]))
        p.drawPath(path)
        p.setPen(_pen(QColor(255, 255, 255, max(0, min(255, trunc(a * P["core_alpha"])))),
                      P["width"] * P["core_width"] * (0.25 + 0.75 * q[3]) * ps))
        p.drawPath(path)


def _beam_capsule(b, w_head, w_tail):
    """Outline of a tapered capsule from the tail to the head (FXK beamCapsule)."""
    ah = math.atan2(b["hy"] - b["ty"], b["hx"] - b["tx"])
    pts = []
    for k in range(13):
        a = ah + math.pi + (k / 12 - 0.5) * math.pi
        pts.append((b["tx"] + math.cos(a) * w_tail / 2, b["ty"] + math.sin(a) * w_tail / 2))
    for k in range(13):
        a = ah + (k / 12 - 0.5) * math.pi
        pts.append((b["hx"] + math.cos(a) * w_head / 2, b["hy"] + math.sin(a) * w_head / 2))
    return pts


def _beam_stops(b, col_at, a):
    """[(t from head, rgb, alpha)] (FXK beamStops)."""
    ts = [0.0, 1.0]
    if 0 < b["tf"] < 1:
        ts.insert(1, b["tf"])
    return [(t, col_at(t), a * (min(1.0, t / b["tf"]) if b["tf"] > 0 else 1.0)) for t in ts]


def _draw_beam(p, inst, host, ps):
    P = inst.fx["params"]
    b = beam_segs(inst, host, ps)
    if not b:
        return
    segs, am, info = b
    gc = hex_rgb(P["glow_color"], None) if P.get("glow_color") else None
    # A straight multi-segment beam (no jitter) is drawn as one tapered capsule filled
    # with a smooth gradient along its length (colour c2 at the head to c1 at the tail,
    # tip_fade alpha), so it has no joints, seams or width steps.  Jittered and
    # single-segment beams stroke their segments with round caps as before.
    if len(segs) > 1 and not P["jitter"] > 0:
        c1, c2 = info["c1"], info["c2"]

        def col_at(t):
            return [c2[i] + (c1[i] - c2[i]) * t for i in range(3)]

        def fill(c_at, a, w_head, w_tail):
            grad = QLinearGradient(info["hx"], info["hy"], info["tx"], info["ty"])
            for t, col, al in _beam_stops(info, c_at, a):
                grad.setColorAt(t, qcolor(col, al))
            pts = _beam_capsule(info, w_head, w_tail)
            path = QPainterPath(QPointF(*pts[0]))
            for q in pts[1:]:
                path.lineTo(*q)
            path.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawPath(path)
            p.setBrush(Qt.NoBrush)

        if P["glow"] > 0:
            fill((lambda t: gc) if gc else (lambda t: [trunc(v) for v in col_at(t)]), 70 * am,
                 info["wH"] + P["glow"] * ps, info["wT"] + P["glow"] * ps)
        fill(col_at, 235 * am, max(1.0, info["wH"]), max(1.0, info["wT"]))
        return
    for q in segs:
        w, col = q[4], q[5]
        if P["glow"] > 0:
            p.setPen(_pen(qcolor(gc or [trunc(v) for v in col], 70 * am * q[6]), w + P["glow"] * ps))
            _line(p, q[0], q[1], q[2], q[3])
        p.setPen(_pen(qcolor(col, 235 * am * q[6]), max(1.0, w)))
        _line(p, q[0], q[1], q[2], q[3])


_BLADE_SPRITES = {}


def _js_round(v):
    """Math.round: halves round up (Python's round() rounds them to even)."""
    return int(math.floor(v + 0.5))


BLADE_SHOULDER, BLADE_BASE, BLADE_LODGE_FADE_MS, BLADE_LODGE_JITTER_DEG = 0.18, 0.82, 300, 10
BLADE_LODGE_GLOW = 0.35


def blade_sprite(r, g, b, radius, stretch, hot=False, glow_pct=100.0, glow_size_pct=100.0):
    """Ethereal blade (fxkit.js bladeSprite): a sword of light, tip pointing
    +x.  Half-width = radius, length = 2 x radius x stretch (tip to pommel).
    A diamond-faceted blade (light upper facet, deeper lower facet, white
    ridge) widest near the tip, a crystal guard at 82 % of the length, a
    fading grip, a tight bloom and a wide halo (glow / glow_size) along it,
    and a four-point glint at the tip (hot: brighter ridge and glint, bigger
    glint).  Returns (pixmap, tip_x, half_h); _blit_blade draws it end for
    end (the glint at the hilt, the fading grip as the point)."""
    ga = max(0, min(255, _js_round(150 * max(0.0, float(glow_pct)) / 100.0)))
    gs = max(0.0, float(glow_size_pct)) / 100.0
    key = (r, g, b, round(float(radius), 2), round(float(stretch), 2), bool(hot), ga, round(gs, 2))
    entry = _BLADE_SPRITES.get(key)
    if entry is not None:
        return entry
    rad = max(0.5, float(radius))
    L = 2 * rad * max(1.0, float(stretch))
    gw = rad * 3 * gs
    ry, rx = rad + gw, L / 2 + gw
    fl = rad * 2.4 * (1.5 if hot else 1.0)
    gh = rad * 1.9
    pad = max(1.0, gw, fl)
    w = int(math.ceil(L + 2 * pad)) + 2
    h = int(math.ceil(2 * max(ry, fl, gh))) + 2
    tip_x, cy = w - pad, h / 2.0
    sx, bx, ex = tip_x - L * BLADE_SHOULDER, tip_x - L * BLADE_BASE, tip_x - L
    col = (r, g, b)
    lt = (trunc(r + (255 - r) * 0.55), trunc(g + (255 - g) * 0.55), trunc(b + (255 - b) * 0.55))   # light facet tint
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing)
    qp.setPen(Qt.NoPen)

    def poly(pts, x0, x1, stops):
        lg = QLinearGradient(x0, cy, x1, cy)
        for t, qc in stops:
            lg.setColorAt(t, qc)
        qp.setBrush(lg)
        qp.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))

    def halo(cx, hrx, hry, c, a):   # radial glow stretched along the blade
        qp.save()
        qp.translate(cx, cy)
        qp.scale(hrx / hry, 1.0)
        grad = QRadialGradient(0, 0, hry)
        grad.setColorAt(0.0, qcolor(c, a))
        grad.setColorAt(1.0, qcolor(c, 0))
        qp.setBrush(grad)
        qp.drawEllipse(int(-hry), int(-hry), int(hry * 2), int(hry * 2))
        qp.restore()

    if ga > 0:
        halo(tip_x - L / 2, rx, ry, col, ga)   # wide halo
        halo(tip_x - L * 0.4, L * 0.45 + rad, rad * 1.9, lt, _js_round(ga * 0.8))   # tight bloom
    # grip, fading toward the pommel
    poly([(bx - rad * 0.3, cy - rad * 0.3), (ex, cy - rad * 0.18), (ex, cy + rad * 0.18), (bx - rad * 0.3, cy + rad * 0.3)],
         ex, bx, [(0.0, qcolor(lt, 0)), (1.0, qcolor(lt, 170))])

    def fs(c):   # blade facets: brightest at the tip
        return [(0.0, qcolor(c, 110)), (0.7, qcolor(c, 200)), (1.0, qcolor(c, 245))]

    poly([(tip_x, cy), (sx, cy - rad), (bx, cy - rad * 0.55), (bx, cy)], bx, tip_x, fs(lt))
    poly([(tip_x, cy), (sx, cy + rad), (bx, cy + rad * 0.55), (bx, cy)], bx, tip_x, fs(col))
    # white ridge down the middle
    ra = 255 if hot else 200
    poly([(tip_x, cy), (sx, cy - rad * 0.14), (bx, cy - rad * 0.1), (bx, cy + rad * 0.1), (sx, cy + rad * 0.14)], bx, tip_x,
         [(0.0, QColor(255, 255, 255, 60)), (1.0, QColor(255, 255, 255, ra))])
    # crystal guard
    poly([(bx, cy - gh), (bx + rad * 0.3, cy), (bx, cy + gh), (bx - rad * 0.3, cy)], bx - rad * 0.3, bx + rad * 0.3,
         [(0.0, qcolor(lt, 200)), (1.0, QColor(255, 255, 255, 220))])
    # four-point glint at the tip
    core = QRadialGradient(tip_x, cy, fl * 0.45)
    core.setColorAt(0.0, QColor(255, 255, 255, 245))
    core.setColorAt(0.5, qcolor(col, 180))
    core.setColorAt(1.0, qcolor(col, 0))
    qp.setBrush(core)
    qp.drawEllipse(int(tip_x - fl * 0.45), int(cy - fl * 0.45), int(fl * 0.9), int(fl * 0.9))
    for kx, ky in ((1.0, 0.1), (0.1, 1.0)):
        qp.save()
        qp.translate(tip_x, cy)
        qp.scale(kx, ky)
        st = QRadialGradient(0, 0, fl)
        st.setColorAt(0.0, QColor(255, 255, 255, 230))
        st.setColorAt(1.0, QColor(255, 255, 255, 0))
        qp.setBrush(st)
        qp.drawEllipse(int(-fl), int(-fl), int(fl * 2), int(fl * 2))
        qp.restore()
    qp.end()
    entry = (pm, tip_x, h / 2.0)
    _BLADE_SPRITES[key] = entry
    return entry


def _blit_blade(p, pm, tip_x, half_h, P):
    """Draw a blade sprite (already translated to the blade's tip, rotated to
    its angle and scaled) end for end: the art is mirrored along the blade so
    the fading end leads and the glint sits at the hilt; the blade covers the
    same tip-to-pommel line as before (hits and lodging unchanged).
    fxkit.js blitBlade."""
    p.scale(-1.0, 1.0)
    p.drawPixmap(trunc(blade_length(P, 1.0) - tip_x), trunc(-half_h), pm)


def blade_angle(inst):
    """Which way a blade's tip points (radians): its impact angle while
    lodged; with blade_orient "angle" the held blade_angle_deg (mirrored by
    Flip); else along its velocity, else along this tick's movement (orbit,
    attached), else straight down.  fxkit.js bladeAngle."""
    if inst.lodge is not None:
        return inst.lodge["a"]
    P = inst.fx["params"]
    if P.get("blade_orient") == "angle":
        fa = float(P.get("blade_angle_deg") or 0) * D
        return math.pi - fa if inst.flip < 0 else fa
    if inst.vx * inst.vx + inst.vy * inst.vy > 0.0001:
        return math.atan2(inst.vy, inst.vx)
    dx, dy = inst.x - inst.px, inst.y - inst.py
    if dx * dx + dy * dy > 1e-6:
        return math.atan2(dy, dx)
    return math.pi / 2


def blade_length(P, ps):
    rad = max(0.5, float(P["radius"]))
    return 2 * rad * max(1.0, float(P["stretch"])) * ps


def aim_target(fx, host):
    """Each particle on a blade: the target it aims at (copied each tick),
    else None.  fxkit.js aimTarget."""
    if fx.get("follow_each") and fx["prim"] == "sprite" and fx["params"]["shape"] == "blade":
        return (float(host.target[0]), float(host.target[1]))
    return None


def blade_pose(inst, ps):
    """Where a blade's tip is and which way it points: (x, y, angle).  As
    authored, inst.x / inst.y is the tip and blade_angle the direction.  With
    Each particle the blade pivots on its own centre (the
    middle of the authored blade) so its tip points at the target; lodged and
    deflected blades keep their own pose.  fxkit.js bladePose."""
    a = blade_angle(inst)
    T = inst.tgt
    if T is None or inst.lodge is not None or inst.free or inst.vx * inst.vx + inst.vy * inst.vy > 0.0001:
        return inst.x, inst.y, a   # flying blades point along their flight
    h = blade_length(inst.fx["params"], ps) / 2
    cx, cy = inst.x - math.cos(a) * h, inst.y - math.sin(a) * h
    dx, dy = T[0] - cx, T[1] - cy
    if dx * dx + dy * dy < 1e-6:
        return inst.x, inst.y, a
    a = math.atan2(dy, dx)
    return cx + math.cos(a) * h, cy + math.sin(a) * h, a


def can_lodge(inst):
    fx = inst.fx
    return fx["prim"] == "sprite" and fx["params"]["shape"] == "blade" and float(fx["params"].get("lodge_ms", 0)) > 0


def blade_lodge(inst, hx, hy, hr, ps):
    """A non-piercing blade that hits a hurt circle (hx, hy, hr) lodges
    instead of ending (fxkit.js bladeLodge): turned up to
    BLADE_LODGE_JITTER_DEG off its impact direction (the instance's seeded
    rng, so blades on one path don't stack), its tip is driven along it
    toward the point nearest the circle's centre (70-100 % of the way, no
    deeper than 45 % of the blade), it stays at that angle and offset from the
    target, following it, for lodge_ms (fading out over the last 300 ms),
    hidden where it is inside the target, and deals no more damage."""
    P = inst.fx["params"]
    bx, by, a = blade_pose(inst, ps)
    a += inst.r.uniform(-BLADE_LODGE_JITTER_DEG, BLADE_LODGE_JITTER_DEG) * D
    ux, uy = math.cos(a), math.sin(a)
    L = blade_length(P, ps)
    s0 = (hx - bx) * ux + (hy - by) * uy   # along the blade to the point nearest the centre
    tx, ty = bx + ux * s0, by + uy * s0
    px, py = hx - tx, hy - ty
    half = math.sqrt(max(0.0, hr * hr - px * px - py * py))
    inside = min(half * inst.r.uniform(0.7, 1), L * 0.45)
    if half > inside:
        tx -= ux * (half - inside)
        ty -= uy * (half - inside)
    n = max(1, _js_round(float(P["lodge_ms"]) / TICK_MS))
    inst.lodge = {"a": a, "ox": tx - hx, "oy": ty - hy, "hx": hx, "hy": hy, "depth": inside, "n": n}
    inst.x = inst.px = tx
    inst.y = inst.py = ty
    inst.vx = inst.vy = 0.0
    inst.trail = []
    inst.life = inst.age + n


def blade_follow(inst, hurts, ps):
    """Each tick a lodged blade follows the hurt circle nearest where its
    target last was (within 200 px x scale); with none (target gone or
    blinked out) it stays put.  fxkit.js bladeFollow."""
    lg = inst.lodge
    best, bd = None, (200 * ps) ** 2
    for q in hurts:
        dx, dy = q[0] - lg["hx"], q[1] - lg["hy"]
        d = dx * dx + dy * dy
        if d <= bd:
            bd, best = d, q
    if best is not None:
        lg["hx"], lg["hy"] = best[0], best[1]
    inst.px, inst.py = inst.x, inst.y
    inst.x, inst.y = lg["hx"] + lg["ox"], lg["hy"] + lg["oy"]


def _draw_lodged(p, inst, host, ps):
    """A lodged blade (fxkit.js drawLodged): only the part outside the
    target is drawn, with a soft glow where it enters; it fades out over its
    last BLADE_LODGE_FADE_MS.  Drawn with normal blending and
    BLADE_LODGE_GLOW of its glow, so dozens stuck in one target stay
    separate swords instead of one white mass."""
    P, lg = inst.fx["params"], inst.lodge
    c = [trunc(v) for v in color_pair(inst.fx, host.lut)[0]]
    k = min(1.0, (inst.life - inst.age) / max(1.0, BLADE_LODGE_FADE_MS / TICK_MS))
    pm, tip_x, half_h = blade_sprite(c[0], c[1], c[2], P["radius"], P["stretch"], bool(P["hot"]),
                                     float(P.get("glow", 100)) * BLADE_LODGE_GLOW, P.get("glow_size", 100))
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)
    cut = lg["depth"] / ps   # sprite units hidden inside the target
    p.save()
    p.translate(trunc(inst.x), trunc(inst.y))
    p.rotate(math.degrees(lg["a"]))
    p.scale(ps, ps)
    p.setOpacity(p.opacity() * k)
    p.setClipRect(QRectF(-pm.width() - 2, -pm.height(), pm.width() + 2 - cut, pm.height() * 2))
    _blit_blade(p, pm, tip_x, half_h, P)
    p.restore()
    er = max(1.0, float(P["radius"])) * 1.4 * ps
    ex, ey = inst.x - math.cos(lg["a"]) * lg["depth"], inst.y - math.sin(lg["a"]) * lg["depth"]
    grad = QRadialGradient(ex, ey, er)
    grad.setColorAt(0.0, qcolor((255, 255, 255), 110 * k))
    grad.setColorAt(0.4, qcolor(c, 70 * k))
    grad.setColorAt(1.0, qcolor(c, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawEllipse(int(ex - er), int(ey - er), int(er * 2), int(er * 2))


def _draw_sprite(p, inst, host, ps):
    from . import combat as _combat
    fx, P = inst.fx, inst.fx["params"]
    if inst.age >= inst.life:
        return
    if inst.lodge is not None:
        _draw_lodged(p, inst, host, ps)
        return
    fade = max(0.0, 1 - inst.age / inst.life) if P["fade"] else 1.0
    c = [trunc(v) for v in color_pair(fx, host.lut)[0]]
    hx, hy = trunc(inst.x), trunc(inst.y)
    if P["shape"] == "blade":   # Each in place turns it on its own centre (blade_pose)
        bx, by, ba = blade_pose(inst, ps)
        hx, hy = trunc(bx), trunc(by)
    pts, n = inst.trail, len(inst.trail)
    for i in range(1, n):
        t = i / n
        p.setPen(_pen(qcolor(c, 200 * t * fade), (1 + 2 * t) * ps))
        _line(p, pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1])
    spd2 = inst.vx * inst.vx + inst.vy * inst.vy
    p.save()
    p.translate(hx, hy)
    p.setOpacity(p.opacity() * fade)
    if P["shape"] == "blade":
        pm, tip_x, half_h = blade_sprite(c[0], c[1], c[2], P["radius"], P["stretch"], bool(P["hot"]),
                                         P.get("glow", 100), P.get("glow_size", 100))
        p.rotate(math.degrees(ba))
        p.scale(ps, ps)
        _blit_blade(p, pm, tip_x, half_h, P)
    elif P["shape"] == "bolt" and spd2 > 0.0001 and P["stretch"] > 1.001:
        pm, head_x, half_h = _combat.bolt_sprite(c[0], c[1], c[2], P["radius"], P["stretch"], bool(P["hot"]),
                                                     P.get("glow", 100), P.get("glow_size", 100))
        p.rotate(math.degrees(math.atan2(inst.vy, inst.vx)))
        p.scale(ps, ps)
        p.drawPixmap(trunc(-head_x), trunc(-half_h), pm)
    elif P["shape"] == "bolt":
        pm, head_x, half_h = _combat.bolt_sprite(c[0], c[1], c[2], P["radius"], 1, bool(P["hot"]),
                                                     P.get("glow", 100), P.get("glow_size", 100))
        p.scale(ps, ps)
        p.drawPixmap(-trunc(pm.width() / 2), -trunc(pm.height() / 2), pm)
    else:
        pm, half = _combat.bullet_sprite(c[0], c[1], c[2], P["radius"], P.get("glow", 100), P.get("glow_size", 100))
        p.scale(ps, ps)
        p.drawPixmap(-half, -half, pm)
    p.restore()
    if P["halo"]:
        ha = trunc((110 + 70 * math.sin(inst.age * 0.5)) * fade)
        if ha > 4:
            ihr = trunc(P["radius"] * 3.6 * ps)
            p.setBrush(Qt.NoBrush)
            p.setPen(_pen(qcolor(c, ha), 1.4))
            p.drawEllipse(QPointF(hx, hy), ihr, ihr)


def _draw_particles(p, inst, host, ps):
    from . import combat as _combat
    P = inst.fx["params"]
    base = p.opacity()
    for q in inst.parts:
        t = min(1.0, q["age"] / q["life"])
        s0, s1 = q["s0"], q["s1"]
        sol = P["size_over_life"]
        if sol == "shrink":
            size = s1 + (s0 - s1) * (1 - t)
        elif sol == "grow":
            size = s0 + (s1 - s0) * t
        elif sol == "pulse":
            size = s0 + (s1 - s0) * math.sin(min(1.0, t) * math.pi)
        else:
            size = s0
        size = max(0.5, size)
        r = max(0, min(255, trunc(q["rgb1"][0] + (q["rgb2"][0] - q["rgb1"][0]) * t)))
        g = max(0, min(255, trunc(q["rgb1"][1] + (q["rgb2"][1] - q["rgb1"][1]) * t)))
        b = max(0, min(255, trunc(q["rgb1"][2] + (q["rgb2"][2] - q["rgb1"][2]) * t)))
        pm, half = _combat.bullet_sprite(r, g, b, size / 2)
        p.save()
        p.translate(trunc(q["x"]), trunc(q["y"]))
        p.scale(ps, ps)
        p.setOpacity(base * max(0.0, 1 - t))
        p.drawPixmap(-half, -half, pm)
        p.restore()


def _draw_glow(p, inst, host, ps):
    fx, P = inst.fx, inst.fx["params"]
    if inst.age >= inst.life:
        return
    t = life_t(inst)
    c = [trunc(v) for v in color_pair(fx, host.lut)[0]]
    fade = P["fade"]
    k = 1 - t if fade == "out" else t if fade == "in" else math.sin(t * math.pi) if fade == "inout" else 1.0
    if inst.cont:
        k = t if fade == "in" else 1.0
    if P["pulse_hz"] > 0:
        k *= 0.65 + 0.35 * math.sin(2 * math.pi * P["pulse_hz"] * (inst.age * TICK_MS / 1000.0))
    hx, hy = trunc(inst.x), trunc(inst.y)
    gr = (P["r_start"] + (P["r_end"] - P["r_start"]) * t) * ps
    igr = trunc(gr)
    if igr > 0:
        _radial_ellipse(p, hx, hy, gr, [(0, qcolor(c, P["a_center"] * k)), (P["mid"], qcolor(c, P["a_mid"] * k)),
                                        (1, qcolor(c, 0))], igr)
    dr = P["core_r"] * ps
    idr = trunc(dr)
    if idr > 0:
        _radial_ellipse(p, hx, hy, dr, [(0, QColor(255, 255, 255, max(0, min(255, trunc(200 * k))))),
                                        (0.5, qcolor(c, 180 * k)), (1, qcolor(c, 100 * k))], idr)


def _draw_pulse(p, inst, host, ps):
    P = inst.fx["params"]
    c1, c2 = color_pair(inst.fx, host.lut)
    sx, sy, tilt = pulse_shape(inst, host)
    p.save()
    p.translate(inst.x, inst.y)
    if tilt:
        p.rotate(tilt)
    for (_k, r, w, k) in pulse_rings(inst, ps):
        if k <= 0.004:
            continue
        if P["fill_alpha"] > 0 and r >= 1:
            p.save()
            p.scale(sx, sy)
            _radial_ellipse(p, 0.0, 0.0, r, [(0, qcolor(c2, 0)), (0.7, qcolor(c2, P["fill_alpha"] * k * 0.35)),
                                             (1, qcolor(c2, P["fill_alpha"] * k))], trunc(r))
            p.restore()
        p.setBrush(Qt.NoBrush)
        if P["glow"] > 0:
            p.setPen(_pen(qcolor(c2, 70 * k), w + P["glow"] * ps))
            p.drawEllipse(QPointF(0.0, 0.0), r * sx, r * sy)
        if w > 0:
            p.setPen(_pen(qcolor(c1, 235 * k), w))
            p.drawEllipse(QPointF(0.0, 0.0), r * sx, r * sy)
    p.restore()


def _draw_ghost(p, inst, host, ps):
    P = inst.fx["params"]
    c = tuple(trunc(v) for v in color_pair(inst.fx, host.lut)[0])
    for gh in inst.ghosts:
        a = P["alpha"] * (1 - gh["age"] / P["ghost_life"])
        if a > 1:
            host.draw_ghost(p, gh, c, a / 255.0)


_DRAW = {"ribbon": _draw_ribbon, "arc": _draw_arc, "beam": _draw_beam, "sprite": _draw_sprite,
         "particles": _draw_particles, "glow": _draw_glow, "pulse": _draw_pulse, "ghost": _draw_ghost, "weapon": lambda *a: None}


def draw_inst(p, inst, host, ps):
    p.save()
    if inst.fx.get("blend") == "additive":
        p.setCompositionMode(QPainter.CompositionMode_Plus)
    _DRAW[inst.fx["prim"]](p, inst, host, ps or 1.0)
    p.restore()


# ---------------------------------------------------------------- player
class Player:
    """Plays every effect bound to one action in lock-step with its frames
    (FXK.Player).  `t` counts ticks since the action started; `t_prev` is the
    previous tick's value (the game can skip ahead when an attack's frames
    advance faster than 16 ms, so a start tick is 'crossed' rather than hit
    exactly)."""

    def __init__(self):
        self._fms = 100.0
        self.reset()

    def reset(self):
        self.insts = []
        self.clock = 0
        self.pending = []
        self.runs = []      # Continuous runs (_step_run)
        self.spent = []     # always-on effects whose set launched: none again until the action restarts / changes
        self._last_t = -1   # previous tick's t (a smaller t = the action restarted)

    @staticmethod
    def entry_window(fx, host, frames, frame_ms):
        """An entry-set effect's production window in action ticks: (first
        tick, stop tick).  Nothing is produced before the set's Start frame or
        from the tick after its Stop frame on (FXK entryWindow)."""
        eset = entry_set_of(fx, host)
        if not eset:
            return 0, INF
        s = jround(max(0, eset["start_frame"]) * frame_ms / TICK_MS)
        st = eset["stop_frame"]
        return s, (INF if st < 0 else jround((min(frames - 1, st) + 1) * frame_ms / TICK_MS))

    @staticmethod
    def entry_order(eset, fx, t, salt):
        """The order a sequential set's points fire in (FXK entryOrder)."""
        n = len(eset["points"])
        o = eset.get("order")
        if eset.get("mode") != "sequential" or o == "forward" or n < 2:
            return list(range(n))
        if o == "reverse":
            return list(range(n - 1, -1, -1))
        if o == "pingpong":
            return list(range(n)) + list(range(n - 2, 0, -1))
        idx = list(range(n))
        r = Rng(hash32(fx["id"]) ^ imul(t + 1, 0x2C1B3C6D) ^ imul(salt, 0x297A2D39))
        for i in range(n - 1, 0, -1):
            j = min(i, int(r() * (i + 1)))
            idx[i], idx[j] = idx[j], idx[i]
        return idx

    @staticmethod
    def window(fx, frames, frame_ms):
        total = max(1, jround((frames * frame_ms / TICK_MS)))
        s = jround((max(0, fx["start_frame"]) * frame_ms / TICK_MS))
        e = total if fx["end_frame"] < 0 else jround(((min(frames - 1, fx["end_frame"]) + 1) * frame_ms / TICK_MS))
        return min(s, total - 1), max(s + 1, e), total

    def _spawn_job(self, j, host):
        for i in range(j["n"]):
            ep = j["ep"]
            seed = (hash32(j["fx"]["id"]) ^ imul(j["t"] + 1, 0x9E3779B1) ^ imul(i, 0x85EBCA6B)
                    ^ imul(0 if ep is None else ep + 1, 0xC2B2AE35) ^ imul(j.get("salt", 0), 0x27D4EB2F)) & M32
            t0 = j["t"] + j.get("delay", 0)
            if t0 >= j.get("stop", INF):   # past its entry set's Stop frame: no more particles
                return
            inst = spawn(fx_at(j["fx"], t0 * TICK_MS / j["fms"]), host, max(1, j["win"]), seed, i, j["n"], ep)
            inst.src, inst.t0, inst.fms = j["fx"], t0, j["fms"]
            if j["tag"] == "cont":
                inst.cont = True
                inst.win = inst.life
                inst.life = INF
            else:
                inst.open = j["tag"] == "open"
                inst.run = j["tag"] == "run"
            self.insts.append(inst)

    def _fire(self, fx, t, n, win, tag, host, run=None, stop=INF):
        # run (Continuous): its frame time and cycle number, so its keys play
        # on the action's timing and each cycle's randomness differs.
        # stop: the entry set's stop tick (entry_window).
        eset = entry_set_of(fx, host)
        salt = run["k"] + 1 if run else 0
        order = self.entry_order(eset, fx, t, salt) if eset else [None]
        for pos, k in enumerate(order):
            delay = pos * max(0, trunc(eset["interval_ticks"])) if eset and eset.get("mode") == "sequential" else 0
            job = {"fx": fx, "t": t, "n": n, "win": win - delay, "ep": k, "tag": tag,
                   "due": self.clock + delay, "delay": delay, "fms": run["fms"] if run else self._fms,
                   "salt": salt, "stop": run["stop"] if run else stop}
            if delay > 0:
                self.pending.append(job)
            else:
                self._spawn_job(job, host)

    def tick(self, effects, host, t, frames, frame_ms, continuous=False, t_prev=None):
        # t_prev == t: the action is holding a frame (time did not advance),
        # so nothing new fires this tick; live instances still update.
        held = t_prev is not None and t_prev == t
        self._fms = max(1e-6, float(frame_ms))
        if t_prev is None or t_prev > t:
            t_prev = t - 1
        due = [j for j in self.pending if j["due"] <= self.clock]
        self.pending = [j for j in self.pending if j["due"] > self.clock]
        for j in due:
            if j["tag"] == "run" or (j["fx"].get("enabled", True) and any(e is j["fx"] for e in effects)):
                self._spawn_job(j, host)
        # The action restarted (t went back) or an effect left it: its spent
        # always-on set may start again.
        if t < self._last_t:
            self.spent = []
        self.spent = [f for f in self.spent if any(e is f for e in effects)]
        self._last_t = t
        # Continuous runs, on their own clock whatever the action is doing.
        self.runs = [r for r in self.runs if self._step_run(r, host)]
        for inst in self.insts:
            src = inst.src or inst.fx
            if inst.cont and (not src.get("enabled", True) or not any(e is src for e in effects) or not is_always_on(src)):
                inst.dead = True
        for fx in (() if held else effects):
            if not fx.get("enabled", True):
                continue
            s, e, total = self.window(fx, frames, frame_ms)
            es, stop = self.entry_window(fx, host, frames, frame_ms)
            if es > s:   # the entry set starts producing later than the effect
                s = es
                if s >= total or (s >= e and not is_always_on(fx)):
                    continue
            if is_always_on(fx):
                if t < s or any(f is fx for f in self.spent) \
                        or any((q.src or q.fx) is fx and q.cont and not q.dead and q.age < q.life for q in self.insts) \
                        or any(q["fx"] is fx for q in self.pending):
                    continue
                self._fire(fx, t, max(1, trunc(fx["emit"]["count"])), total - s, "cont", host, stop=stop)
                continue
            if is_continuous(fx):   # a run of its whole sequence each time the action reaches the start frame
                if not (t_prev < s <= t):
                    continue
                mine = [r for r in self.runs if r["fx"] is fx]
                if len(mine) >= CYCLE_MAX_RUNS:
                    self.runs.remove(mine[0])
                run = {"fx": fx, "s": s, "e": e, "rt": s,
                       "len": max(1, e - s, trunc(fx["life_ticks"]) if fx["life_ticks"] > 0 else 0),
                       "fms": self._fms, "k": 0, "loop": bool(fx["cycles"]["enabled"]), "left": trunc(fx["cycles"]["count"]),
                       "stop": stop}
                if self._step_run(run, host):   # its first tick is this one
                    self.runs.append(run)
                continue
            every = fx["emit"]["every_ticks"]
            periodic = every > 0 and s < t < e and (t - s) % every == 0
            fire = (t_prev < s <= t) or periodic
            if not fire:
                continue
            opn = fx["life_ticks"] <= 0 and e >= total
            if continuous and opn and not periodic and any((q.src or q.fx) is fx and q.open and not q.dead for q in self.insts):
                continue
            self._fire(fx, t, max(1, trunc(fx["emit"]["count"])), e - t, "open" if opn else "", host, stop=stop)
        self.clock += 1
        ps = host.pscale or 1.0
        if continuous:
            for inst in self.insts:
                if inst.open and inst.age < inst.life:
                    inst.life = max(inst.life, inst.age + 2)
        for inst in self.insts:
            src = inst.src
            if src is not None and src.get("keys"):
                # Keyframes: this tick's values at the instance's own action time.
                inst.fx = fx_at(src, (inst.t0 + inst.age) * TICK_MS / inst.fms)
            if (inst.mk != inst.fx["motion"]["kind"] or inst.ma != inst.fx["motion"]["aim"]) and motion_switch(inst, host) \
                    and not any(f is inst.src for f in self.spent):
                self.spent.append(inst.src)
            tick_inst(inst, host)
            resolve_hits(inst, host, ps)
        self.insts = [i for i in self.insts if not i.dead]

    def _step_run(self, r, host):
        """One tick of a Continuous run: the effect's own emissions at run
        time r["rt"] (exactly as the action would fire them), then the clock
        moves on.  False once the sequence (and every cycle) is done."""
        fx, rt, s = r["fx"], r["rt"], r["s"]
        ev = fx["emit"]["every_ticks"]
        if rt == s or (ev > 0 and s < rt < r["e"] and (rt - s) % ev == 0):
            self._fire(fx, rt, max(1, trunc(fx["emit"]["count"])), r["e"] - rt, "run", host, r)
        r["rt"] = rt + 1
        if r["rt"] - s < r["len"]:
            return True
        if not r["loop"] or r["left"] == 0:
            return False
        if r["left"] > 0:
            r["left"] -= 1
        r["k"] += 1
        r["rt"] = s
        return True

    def draw(self, p, host, layer, hidden=False):
        ps = host.pscale or 1.0
        for inst in self.insts:
            if inst.dead:   # ended at its source by the other side this tick
                continue
            if hidden and body_bound(inst):
                continue    # blinked out: the fighter's own body FX are hidden
            if inst.fx.get("layer", "front") == layer:
                draw_inst(p, inst, host, ps)


def body_bound(inst):
    """FX that sit on the fighter's body (attached / orbit motion, weapon
    hitboxes): hidden and harmless while it is blinked out (laser/blink.py)."""
    fx = inst.fx
    return fx["motion"]["kind"] in ("attached", "orbit") or fx["prim"] == "weapon"


# ===========================================================================
# Game side
# ===========================================================================
class CharacterFx:
    """The FX file of one character, normalised once (cached on its mode)."""

    def __init__(self, char):
        pkg = char.get("_package") or {}
        fxk = char.get("_fxkit") or {}
        img = pkg.get("image") or {}
        space = fxk.get("space") or {}
        # The frames on disk define image space: the package's origin/head.
        pkg_origin = list(img.get("origin_px") or space.get("image_origin_px") or [0, 0])
        pkg_head = float(img.get("head_px") or space.get("head_px") or 58)
        fx_origin = list(space.get("image_origin_px") or pkg_origin)
        fx_head = float(space.get("head_px") or pkg_head)
        self.origin = pkg_origin
        # Game px per image px: the character's stand-height scale (set by
        # the loader), else the old head-size rule.
        self.k = float(char.get("_game_scale") or config.TARGET_HEAD_PX / max(1.0, pkg_head))
        # An FX file made against ANOTHER export of the same Rig Forge
        # character (different frame size / head px) has its anchors in that
        # export's pixels.  Rig Forge renders every export around the same
        # camera centre, so image px convert exactly:
        #   p_pkg = (p_fx - origin_fx) * head_pkg / head_fx + origin_pkg
        f = pkg_head / max(1e-6, fx_head)
        same_space = abs(f - 1.0) < 1e-6 and fx_origin == pkg_origin
        anchors = fxk.get("anchors") or pkg.get("anchors") or {}
        if fxk.get("anchors") and not same_space:
            anchors = {act: {jid: [None if p is None else
                                   [(p[0] - fx_origin[0]) * f + pkg_origin[0], (p[1] - fx_origin[1]) * f + pkg_origin[1]]
                                   for p in row]
                             for jid, row in (joints or {}).items()}
                       for act, joints in anchors.items()}
        # An action whose frames changed after the FX file was saved (Rig
        # Forge added or removed keyframes) takes the package's own anchors —
        # the same rule FX Studio applies when it opens the folder.
        pkg_anchors = pkg.get("anchors") or {}
        if fxk.get("anchors"):
            anchors = dict(anchors)
            for act, a in (char.get("actions") or {}).items():
                n = len(a.get("keyframes") or [])
                mine = anchors.get(act)
                if act in pkg_anchors and (not mine or any(len(r or []) != n for r in mine.values())):
                    anchors[act] = pkg_anchors[act]
        self.anchors = anchors
        self.effects = [normalize(dict(e)) for e in (fxk.get("effects") or [])]
        self.by_action = {}
        for e in self.effects:
            self.by_action.setdefault(e.get("action") or "idle", []).append(e)
        self.settings = {k: normalize_action(v) for k, v in (fxk.get("action_settings") or {}).items()}
        # Triggered reactions (FX Studio > Actions > Triggered reactions):
        # "@blink:<action>" FX play over that action alongside its own while
        # its Blink is on; "@retreat" FX play for the whole Tactical retreat
        # dash (FxDriver._retreat_tick).  Neither plays on its own.
        self.with_blink = {a: (self.by_action.get(a) or []) + self.by_action[BLINK_KEY + a]
                           for a in [k[len(BLINK_KEY):] for k in self.by_action if k.startswith(BLINK_KEY)]}
        self.retreat_own = self.by_action.get(RETREAT_KEY) or []
        self.aim = _fill(dict(fxk.get("aim") or {}), AIM_DEFAULTS)
        self.aim_ref = None
        self.aim_from = None
        if self.aim["enabled"]:
            ref = (self.anchors.get(self.aim["source"]) or {})
            a_row, b_row = ref.get(self.aim["from_anchor"]) or [], ref.get(self.aim["to_anchor"]) or []
            sx = sy = ax = ay = 0.0
            n = 0
            for pa, pb in zip(a_row, b_row):
                if pa and pb:
                    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
                    dd = math.hypot(dx, dy)
                    if dd > 1e-6:
                        sx += dx / dd
                        sy += dy / dd
                        ax += pa[0]
                        ay += pa[1]
                        n += 1
            if n:
                self.aim_ref = norm(sx, sy)            # barrel direction, right-facing image space
                self.aim_from = (ax / n, ay / n)       # where the barrel starts (image px)
        self.lib = {"entry_sets": [normalize_entry_set(e) for e in (fxk.get("entry_sets") or [])],
                    "paths": [normalize_path(p) for p in (fxk.get("paths") or [])]}
        # Distances were authored around the figure at its authoring size;
        # keep them in proportion: r = new game px per rig unit / authored.
        authored = float(space.get("game_px_per_image_px") or 0)
        if authored > 0:
            rescale_effects(self.effects, self.lib, (self.k / authored) * f)
        self.timing = {}
        for name, act in (char.get("actions") or {}).items():
            n = len(act.get("keyframes") or []) or 1
            fm = float(act.get("frame_ms") or 0) or float(act.get("duration_ms") or 100 * n) / n
            self.timing[name] = (n, fm)
        # The animation the dash shows (and FX Studio builds "@retreat" FX on).
        self.retreat_host = "run" if "run" in self.timing else "idle" if "idle" in self.timing \
            else next(iter(self.timing), "run")
        self._retreat_fx = {}

    def retreat_effects(self, key):
        """The effects a Tactical retreat plays for its whole dash (retreat
        "fx": "fx:<effect id>" or "group:<group id>"), as copies that start
        on the dash's first tick (keys shifted with them) and hold while it
        lasts when they can.  The originals keep playing on their own action.
        Returns (effects, action whose timing they use); ([], None) = none."""
        key = key or ""
        if key in self._retreat_fx:
            return self._retreat_fx[key]
        kind, _, ident = key.partition(":")
        if kind == "fx":
            src = [e for e in self.effects if e.get("id") == ident][:1]
        elif kind == "group":
            src = [e for e in self.effects if e.get("group") == ident]
        else:
            src = []
        out = []
        for e in src:
            c = dict(e)
            sf = max(0, int(c.get("start_frame") or 0))
            c["start_frame"], c["end_frame"] = 0, -1
            c["keys"] = [dict(k, frame=max(0, int(k["frame"]) - sf)) for k in (c.get("keys") or [])]
            c["always_on"] = can_continue(c)
            out.append(c)
        res = (out, (src[0].get("action") or "idle") if src else None)
        self._retreat_fx[key] = res
        return res

    def anchor_px(self, action, ident, frame):
        row = (self.anchors.get(action) or {}).get(ident)
        if not row:
            return None
        frame = max(0, min(frame, len(row) - 1))
        for i in range(frame, -1, -1):
            if row[i]:
                return row[i]
        for i in range(frame + 1, len(row)):
            if row[i]:
                return row[i]
        return None


def character_fx(mode):
    """CharacterFx for a mode, or None when its character has no FX file."""
    char = getattr(mode, "character", None)
    if not char or not char.get("_fxkit"):
        return None
    cfx = getattr(mode, "_fxkit_cache", None)
    if cfx is None:
        cfx = CharacterFx(char)
        mode._fxkit_cache = cfx
    return cfx


def aim_angle(cfx, action, frame, facing, pscale, fx, fy, tx, ty):
    """Degrees to turn the whole frame so the barrel of the frame on show
    (pack.aim from -> to anchors of this action/frame; the source action's
    average when the frame has none) points at the target.  facing is +1
    right / -1 left; the frame is mirrored first, then turned, exactly as
    Figure draws it and _Host.anchor maps anchors.  None when not aiming."""
    if cfx is None or not cfx.aim.get("enabled") or cfx.aim_ref is None:
        return None
    pa = cfx.anchor_px(action, cfx.aim["from_anchor"], frame)
    pb = cfx.anchor_px(action, cfx.aim["to_anchor"], frame)
    if pa and pb and math.hypot(pb[0] - pa[0], pb[1] - pa[1]) > 1e-6:
        (rx, ry), start = norm(pb[0] - pa[0], pb[1] - pa[1]), pa
    else:
        (rx, ry), start = cfx.aim_ref, cfx.aim_from
    rx *= facing
    k = cfx.k * (pscale or 1.0)
    ox = (start[0] - cfx.origin[0]) * k * facing
    oy = (start[1] - cfx.origin[1]) * k
    base = math.atan2(ry, rx)
    lim = math.radians(max(0.0, min(180.0, float(cfx.aim.get("max_deg") or 0))))
    a = 0.0
    for _ in range(4):   # the barrel start turns with the frame: settle it
        ca, sa = math.cos(a), math.sin(a)
        px, py = fx + ox * ca - oy * sa, fy + ox * sa + oy * ca
        if (tx - px) ** 2 + (ty - py) ** 2 < 4.0:
            break
        a = math.atan2(ty - py, tx - px) - base
        a = (a + math.pi) % (2 * math.pi) - math.pi
        a = max(-lim, min(lim, a))
    return math.degrees(a)


def current_action(fig):
    """(action name, frame index) the figure is showing — the same choice
    Figure._current_frame makes for the sprite."""
    b, c, m, r = fig.render.bundle, fig.combat, fig.motion, fig.render
    if c.action_anim:
        ex = b.extra.get(c.action_anim)
        if ex and ex[0]:
            return c.action_anim, max(0, min(c.action_idx, len(ex[0]) - 1))
    if c.slashing and b.slash:
        return "attack_normal", min(c.slash_idx, len(b.slash) - 1)
    if m.bouncing and b.slide is not None:
        return "defend", 0
    if m.bounce_ending and b.slide2 is not None:
        return "defend", 1
    if r.is_moving and b.run:
        return "run", r.run_idx % len(b.run)
    if b.idle:
        return "idle", r.idle_idx % len(b.idle)
    return "run", r.run_idx % max(1, len(b.run))


class _Host:
    """What the runtime asks the game: anchors, facing, target, hurt circles."""

    def __init__(self, drv, fig, world):
        self.drv, self.fig, self.world = drv, fig, world
        self.facing = -1 if fig.transform.facing_left else 1
        self.pscale = fig._position_scale()
        self.lut = fig.lut
        self.lib = drv.cfx.lib
        self.wang = 90.0
        self.target = drv.target
        self.hurts = drv.hurts
        # Enemy projectiles for the auto-projectile tracker (Battle only;
        # Solo has no opponent, so there is nothing to intercept).
        self.shots = getattr(world, "enemy_shots", None) or []

    @property
    def rot(self):
        """Body rotation (degrees, after mirroring): the turn anchors get."""
        fig = self.fig
        return fig.aim if fig.aim is not None else (fig.transform.angle if fig.motion.rotate else 0.0)

    def anchor(self, name):
        fig, cfx, drv = self.fig, self.drv.cfx, self.drv
        if name == "figure" or not name:
            return [fig.x, fig.y]
        if name == "target":
            return list(self.target)
        p = cfx.anchor_px(drv.action, name, drv.frame)
        if p is None:
            return [fig.x, fig.y]
        k = cfx.k * self.pscale
        ox, oy = (p[0] - cfx.origin[0]) * k * self.facing, (p[1] - cfx.origin[1]) * k
        ang = self.rot
        if ang:
            a = math.radians(ang)
            ox, oy = ox * math.cos(a) - oy * math.sin(a), ox * math.sin(a) + oy * math.cos(a)
        return [fig.x + ox, fig.y + oy]

    def snapshot(self):
        return self.fig._current_frame()

    def draw_ghost(self, p, gh, rgb, a):
        from . import combat as _combat
        frame = gh["snap"]
        if frame is None:
            return
        pm = _combat.silhouette(frame, rgb)
        p.save()
        p.setOpacity(p.opacity() * a)
        p.drawPixmap(trunc(gh["x"]) - pm.width() // 2, trunc(gh["y"]) - pm.height() // 2, pm)
        p.restore()

    def on_intercept(self, inst, shot, mode, vel, hurts_owner):
        """Apply an interception to the enemy projectile AT ITS SOURCE (the
        same rule as petals / parries): block, destroy and clash nullify it;
        deflect replaces it with a copy flying at `vel` on this side —
        harmless, or (hurts_owner) able to damage the fighter who fired it;
        clash_lock leaves it (both instances are already held in place)."""
        from . import combat as _combat
        ref = shot.ref
        if mode == "clash_lock":   # both held in place; nothing is nullified
            pass
        elif shot.kind == "bullet":
            _combat.kill_projectile(ref)
            if mode == "deflect":
                pr = _combat.Projectile(ref.x, ref.y, vel[0], vel[1], (ref.r, ref.g, ref.b), config.PROJ_TRAIL_LEN)
                pr.style = ref.style
                pr.radius = ref.radius
                pr.owner = self.fig
                if hurts_owner:
                    pr.damage = float(getattr(ref, "damage", 1.0))
                else:
                    pr.hit_r_sq = 0.0
                    pr.max_age = config.DEFLECT_MAX_AGE
                self.world.projectiles.append(pr)
        else:
            if mode == "deflect":   # copied before the source is ended (keeps its remaining life)
                self.drv.player.insts.append(_deflected_copy(ref, vel, hurts_owner))
            ref.age = max(ref.age, ref.life)
            ref.dead = True
        dots = getattr(self.world, "collision_dots", None)
        if dots is not None:
            dots.append([shot.x, shot.y, 0])

    def on_hit(self, inst, damage, dx, dy, knockback, key):
        self.drv.hits_out.append((key, float(damage), dx, dy, float(knockback or 0), inst.fx.get("tag", ""), inst))


def _deflected_copy(src, vel, hurts_owner):
    """An enemy FX projectile knocked away by a deflect, now owned by the
    deflecting side: it flies straight at vel, damaging (hurts_owner) or
    visual only, and never intercepts anything itself."""
    import copy
    fx = copy.deepcopy(src.fx)
    fx["battle"]["deals_damage"] = bool(hurts_owner)
    fx.setdefault("intercept", {})["enabled"] = False
    fx["motion"]["kind"] = "travel"
    fx["keys"] = []   # frozen at the values it had when deflected
    q = copy.copy(src)
    q.fx = fx
    q.src = fx
    q.r = copy.copy(src.r)
    q.hist, q.trail, q.ghosts = list(src.hist), list(src.trail), []
    q.parts = [dict(p) for p in src.parts]
    q.vx, q.vy = float(vel[0]), float(vel[1])
    q.free, q.chase, q.dead, q.cont, q.open = True, False, False, False, False
    q.clash_with = None
    q.lodge = None
    q.mk, q.ma = "travel", fx["motion"]["aim"]
    q.path = None
    q.age = 0
    q.life = max(config.DEFLECT_MAX_AGE, trunc(src.life - src.age) if src.life != INF else 0)
    q.hits, q.last_hit = 0, -1e9
    return q


class FxDriver:
    """Per-figure FX playback for an image character with an FX file."""

    def __init__(self, cfx):
        self.cfx = cfx
        self.player = Player()
        self.action = None
        self.frame = 0
        self.t = 0
        self.t_prev = -1
        self.cycle = 0
        self.target = (0.0, 0.0)
        self.hurts = []
        self.hits_out = []
        self.host = None
        self.last_hp = None    # owner HP last tick (clash ends when it drops)
        # Tactical retreat FX, each lane on its own player and clock for as
        # long as the dash lasts: the borrowed retreat "fx" (on its action's
        # timing) and the FX built on the reaction ("@retreat", on the run
        # timing).  Lane = [player, on, t, t_prev].
        self.rlanes = [[Player(), False, 0, -1], [Player(), False, 0, -1]]

    def _time_for(self, action):
        n, fm = self.cfx.timing.get(action, (1, 100.0))
        return n, fm

    def update(self, fig, world, hold=None):
        # Action time follows the frame on screen: it advances one tick per
        # tick inside the frame's own span (frame_ms), jumps forward when the
        # engine's frames run ahead, holds when a frame is held, and starts
        # a new pass when the frames loop back (idle / run cycles).
        # hold (an action's Blink, while the fighter is gone): nothing new
        # fires, live instances keep updating.  "freeze" also stops the
        # action time; "run" (what laser/blink.py uses) lets it follow the
        # frames as usual.
        self._clash_owner_hit(fig)
        action, frame = current_action(fig)
        n, fm = self._time_for(action)
        f0 = jround(frame * fm / TICK_MS)
        f1 = max(f0, jround((frame + 1) * fm / TICK_MS) - 1)
        if hold == "freeze" and action == self.action:
            self.t_prev = self.t
        elif action != self.action:
            self.action, self.cycle = action, 0
            self.t, self.t_prev = f0, -1
        elif frame < self.frame:
            self.cycle += 1
            self.t, self.t_prev = f0, -1
        else:
            self.t_prev = self.t
            self.t = min(max(self.t + 1, f0), f1)
        self.frame = frame
        # Target and hurt circles: the nearest opposing fighter in Battle
        # (its snapshot position), the cursor in Solo (no damage there).
        hurts = []
        if world.battle_mode and world.partner_figures:
            best = None
            pgone = getattr(world, "partner_gone", None) or []
            pscale = getattr(world, "partner_scale", None) or []
            for idx, pf in enumerate(world.partner_figures):
                d = (pf[0] - fig.x) ** 2 + (pf[1] - fig.y) ** 2
                if best is None or d < best[0]:
                    best = (d, pf)
                if idx < len(pgone) and pgone[idx]:
                    continue    # blinked out: nothing can hit it
                bs = pscale[idx] if idx < len(pscale) else 1.0   # its character scale
                hurts.append((pf[0], pf[1], float(config.PROJ_HIT_RADIUS) * bs, (pf[0], pf[1])))
            self.target = (best[1][0], best[1][1])
        else:
            self.target = tuple(world.cursor)
        self.hurts = hurts
        host = _Host(self, fig, world)
        self.host = host
        cfg = self.cfx.settings.get(action) or normalize_action({})
        from . import blink as _blink
        if (cfg["blink"]["enabled"] and action in self.cfx.with_blink
                and _blink.fx_on(fig, action, world.global_tick)):
            effects = self.cfx.with_blink[action]
        else:
            effects = self.cfx.by_action.get(action) or []
        self.player.tick(effects, host, self.t, n, fm, continuous=bool(cfg.get("fx_continuous")),
                         t_prev=self.t if hold else self.t_prev)
        self._retreat_tick(fig, host, hold)
        if hold:
            # Blinked out: the body-bound FX land no hits.
            self.hits_out = [h for h in self.hits_out if not body_bound(h[6])]

    def _clash_owner_hit(self, fig):
        """Owner hit (HP dropped since last tick): every one of its
        projectiles locked in a clash ends; the enemy one resumes."""
        hp = getattr(getattr(fig, "personality", None), "hp", None)
        hit = hp is not None and self.last_hp is not None and hp < self.last_hp
        self.last_hp = hp
        if not hit:
            return
        for pl in [self.player] + [ln[0] for ln in self.rlanes]:
            for inst in pl.insts:
                if inst.clash_with is not None:
                    inst.age = max(inst.age, inst.life)

    def _retreat_tick(self, fig, host, hold):
        """Tactical retreat FX: the borrowed effect / group and the FX built
        on the reaction play for the whole dash, each looping on its own
        action's timing (shots re-fire each pass and on their own cadence);
        when the dash ends the held FX stop and shots already flying finish."""
        from . import retreat
        st, cfg = fig.retreat, retreat.config_for(fig)
        dashing = bool(cfg and st is not None and st.active)
        borrowed = self.cfx.retreat_effects(cfg.get("fx")) if dashing else ([], None)
        own = (self.cfx.retreat_own, self.cfx.retreat_host) if dashing else ([], None)
        for lane, (effs, act) in zip(self.rlanes, (borrowed, own)):
            self._lane_tick(lane, effs, act, host, hold)

    def _lane_tick(self, lane, effs, act, host, hold):
        pl = lane[0]
        if effs:
            n, fm = self._time_for(act)
            total = max(1, jround(n * fm / TICK_MS))
            if not lane[1] or lane[2] >= total:
                lane[1], lane[2], lane[3] = True, 0, -1
            pl.tick(effs, host, lane[2], n, fm, continuous=True,
                    t_prev=lane[2] if hold else lane[3])
            if not hold:
                lane[3], lane[2] = lane[2], lane[2] + 1
            return
        if lane[1]:
            lane[1] = False
            for inst in pl.insts:
                if inst.cont or inst.open:
                    inst.dead = True
            pl.pending = []
        if pl.insts:
            pl.tick((), host, 0, 1, TICK_MS, t_prev=0)

    def draw(self, p, fig, layer, hidden=False):
        if self.host is None or not (self.player.insts or any(ln[0].insts for ln in self.rlanes)):
            return
        self.host.fig = fig
        self.player.draw(p, self.host, layer, hidden)
        for ln in self.rlanes:
            ln[0].draw(p, self.host, layer, hidden)

    def take_hits(self):
        h, self.hits_out = self.hits_out, []
        return h


def update_figure(fig, world, hold=None):
    """CombatSystem hook: tick this figure's FX (no-op without an FX file).
    hold: see FxDriver.update (FX Studio blink)."""
    cfx = character_fx(fig.mode)
    drv = getattr(fig, "fx", None)
    if cfx is None:
        if drv is not None:
            fig.fx = None
        return
    if drv is None or drv.cfx is not cfx:
        drv = FxDriver(cfx)
        fig.fx = drv
    drv.update(fig, world, hold)
    hits = drv.take_hits()
    if hits and world.battle_mode:
        world.queue_fx_hits(hits)
