"""
Speed lift + gravity (Daniel 2026-11-22), Solo + Battle, every fighter.

A fighter's on-screen movement speed decides how high it flies: up to
ground_speed (px/tick at full position pace, i.e. the live move divided by
combat.position_speed_scale) it stays on the ground; faster it lifts off,
reaching max_height at top_speed and above (curve shapes the incline:
1 = linear, > 1 = stays low longer, < 1 = shoots up early).  Going up it
eases toward that height (rise_pct % of the gap per tick); once the target
height drops below it, gravity (px/tick^2) pulls it back down with
accelerating fall until it lands or meets the new target.

Visual height only: fig.x / fig.y (hits, walls, targeting, snapshots) stay
on the ground spot.  Figure.draw raises the body (and its parry ring) by
z x position_scale and paints a shadow on the ground under it.

Measured from each fighter's per-tick position change (blinks / teleports
over WARP_PX ignored), smoothed (RISE / FALL).  Freeze (F10) holds it.
Settings: per character `pack.lift` (FX Studio file) over DEFAULTS;
enabled False = always on the ground.
"""

import math

from . import combat

DEFAULTS = dict(
    enabled=True,
    ground_speed=7.0,       # px/tick: at or below = on the ground
    top_speed=24.0,         # px/tick: max_height from here up
    max_height=34.0,        # px (body scale 1)
    curve=1.0,
    rise_pct=18.0,          # % of the gap closed per tick going up
    gravity=0.55,           # px/tick^2 coming down
)
WARP_PX = 60.0
RISE = 0.5
FALL = 0.15


def config_for(fig):
    mode = fig.mode
    cfg = getattr(mode, "_lift_cfg", False)
    if cfg is not False:
        return cfg
    out = dict(DEFAULTS)
    char = getattr(mode, "character", None)
    if char and char.get("_package"):
        raw = (char.get("_fxkit") or {}).get("lift")
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in DEFAULTS:
                    out[k] = v
    cfg = out if out.get("enabled") else None
    try:
        mode._lift_cfg = cfg
    except Exception:
        pass
    return cfg


class LiftState:
    __slots__ = ("z", "vz", "spd", "px", "py")

    def __init__(self, x, y):
        self.z = 0.0
        self.vz = 0.0
        self.spd = 0.0
        self.px, self.py = x, y


def target_height(cfg, spd):
    lo, hi = float(cfg["ground_speed"]), float(cfg["top_speed"])
    if spd <= lo:
        return 0.0
    u = 1.0 if hi <= lo else min(1.0, (spd - lo) / (hi - lo))
    c = float(cfg["curve"] or 1.0)
    if c > 0 and c != 1.0:
        u = u ** c
    return u * float(cfg["max_height"])


def _step_fig(fig, cfg):
    t = fig.transform
    lf = getattr(fig, "lift", None)
    if lf is None:
        lf = LiftState(t.x, t.y)
        fig.lift = lf
    d = math.hypot(t.x - lf.px, t.y - lf.py)
    lf.px, lf.py = t.x, t.y
    if d > WARP_PX:
        d = None                    # a blink / teleport is not speed
    if d is not None:
        pace = combat.position_speed_scale(t.x, t.y, fig.screen_w, fig.screen_h) or 1.0
        s = d / max(0.05, pace)
        k = RISE if s > lf.spd else FALL
        lf.spd += (s - lf.spd) * k
    tgt = target_height(cfg, lf.spd)
    if tgt >= lf.z:
        lf.z += (tgt - lf.z) * max(0.0, min(100.0, float(cfg["rise_pct"]))) / 100.0
        lf.vz = 0.0
    else:
        lf.vz -= max(0.0, float(cfg["gravity"]))
        lf.z += lf.vz
        if lf.z <= tgt:
            lf.z, lf.vz = tgt, 0.0
    if lf.z < 0.05:
        lf.z = 0.0


def step(world):
    """Overlay sim tick, after both sides + the puppet."""
    if getattr(world, "freeze_fighters", False):
        return
    for fig in world.all_figures():
        cfg = config_for(fig)
        if cfg is None:
            if getattr(fig, "lift", None) is not None:
                fig.lift.z = 0.0
            continue
        _step_fig(fig, cfg)


def z_of(fig):
    lf = getattr(fig, "lift", None)
    return lf.z if lf is not None else 0.0


def draw_shadow(p, fig, frame, pscale):
    """Figure.draw, before the body: a soft ground shadow under an airborne
    fighter (fainter and smaller the higher it is)."""
    z = z_of(fig)
    if z < 0.5 or frame is None:
        return
    from PyQt5.QtGui import QColor
    from PyQt5.QtCore import Qt, QPointF
    cfg = config_for(fig) or DEFAULTS
    h = min(1.0, z / max(1.0, float(cfg["max_height"])))
    rx = frame.width() * 0.42 * pscale * (1.0 - 0.35 * h)
    ry = max(1.0, rx * 0.32)
    fy = fig.transform.y + frame.height() * 0.5 * pscale
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, int(110 * (1.0 - 0.55 * h))))
    p.drawEllipse(QPointF(fig.transform.x, fy), rx, ry)
    p.restore()


def reset(fig):
    fig.lift = None
