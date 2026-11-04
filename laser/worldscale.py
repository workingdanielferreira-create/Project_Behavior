"""
World anchor scaling — the size / pace rule every fighter and FX draws by
when camera.json "anchor_scale" is on (otherwise the old 4-corner
config.POSITION_SCALE_* / SPEED_SCALE_* grid is used, unchanged).

The anchor is an invisible point kept (eased) at the centre of every
fielded fighter, both sides (Solo: the lone fighter).  laser/camera.py
moves it once per tick and pushes it here with set_anchor(); the follow-cam
pans onto the same point, so the world moves with the fight.

Size at a point (x, y):

    vertical  = v_top + (v_bottom - v_top) * (y / screen_h)
                  -> x5 at the very bottom .. x1 at the very top, whatever
                     the left/right position
    u         = clamp(dist((x, y), anchor) / (far_frac * screen_w), 0, 1)
    distance  = d_near + (d_far - d_near) * u ** curve
                  -> x1 on the anchor .. x0.10 at far_frac of the screen
                     width away (0.5 = two fighters on opposite edges)
    size      = clamp(vertical * distance, s_min, s_max)

Tiny planet (camera.json "planet", needs anchor_scale): the distance term
is replaced by a sphere curve.  The anchor is the top of a small planet
and the ground bends away over a horizon planet_reach_frac x screen_w
from it, in every direction:

    u         = clamp(dist / (reach_frac * screen_w), 0, 1)
    theta     = u * horizon_deg
    c         = (cos theta - cos horizon) / (1 - cos horizon)   (1 .. 0)
    distance  = far + (1 - far) * c         -> stays big near the top,
                                               drops fast toward the rim
    squash    = 1 - squash_amt * (1 - cos theta)   along the line to the
                anchor (foreshortening), width kept

The squash is drawing only and only for the world layers (terrain,
rubble, debris, dust & air: see squasher()); every object stays at its true
spot, so pillars / dust still line up with where fighters touch them.

Pace follows size linearly: s_min -> sp_min, s_max -> sp_max, so the
bigger (nearer) a thing is drawn the faster it moves on screen, as before.

Drawing / pace only: hit tests, walls, targeting and the battle snapshots
stay in plain screen coordinates.  The same rule runs in Solo and Battle.
"""

import math

# None = anchor scaling off (callers fall back to the corner grid).
# Otherwise a tuple, see set_anchor().
_A = None


def set_anchor(ax=None, ay=None, cfg=None):
    """Camera.step: the eased anchor and the camera settings.  ax None or
    cfg None (or cfg["anchor_scale"] off) = anchor scaling off."""
    global _A
    if ax is None or cfg is None or not cfg.get("anchor_scale"):
        _A = None
        return
    _A = (float(ax), float(ay),
          float(cfg["vscale_bottom"]), float(cfg["vscale_top"]),
          float(cfg["dscale_near"]), float(cfg["dscale_far"]),
          float(cfg["dscale_far_frac"]), float(cfg["dscale_curve"]),
          float(cfg["scale_min"]), float(cfg["scale_max"]),
          float(cfg["speed_min"]), float(cfg["speed_max"]),
          _planet(cfg))


def _planet(cfg):
    """(reach_frac, cos_horizon, horizon_rad, far, squash) or None (off)."""
    if not cfg.get("planet"):
        return None
    hz = math.radians(max(1.0, min(90.0, float(cfg.get("planet_horizon_deg", 80.0)))))
    return (float(cfg.get("planet_reach_frac", 0.6)), math.cos(hz), hz,
            float(cfg.get("planet_far", 0.15)), float(cfg.get("planet_squash", 0.85)))


def planet_on():
    return _A is not None and _A[12] is not None


def _theta(x, y, sw):
    """(theta, dx, dy, dist) of (x, y) on the planet (planet_on() only)."""
    ax, ay = _A[0], _A[1]
    reach, _ch, hz = _A[12][0], _A[12][1], _A[12][2]
    dx, dy = x - ax, y - ay
    dist = math.hypot(dx, dy)
    r = reach * sw
    u = max(0.0, min(1.0, dist / r)) if r > 1e-6 else 0.0
    return u * hz, dx, dy, dist


def active():
    return _A is not None


def size_range():
    """(s_min, s_max) of the live rule (None when off)."""
    if _A is None:
        return None
    return _A[8], _A[9]


def size(x, y, sw, sh):
    """Drawn size at (x, y) (call only while active())."""
    (ax, ay, vb, vt, dn, df, ff, cv, smin, smax, _p0, _p1, pl) = _A
    yf = max(0.0, min(1.0, y / sh)) if sh > 0 else 0.5
    v = vt + (vb - vt) * yf
    if pl is not None:
        th = _theta(x, y, sw)[0]
        ch = pl[1]
        c = (math.cos(th) - ch) / (1.0 - ch) if ch < 1.0 - 1e-6 else 1.0
        d = pl[3] + (1.0 - pl[3]) * max(0.0, min(1.0, c))
        return max(smin, min(smax, v * d))
    reach = ff * sw
    if reach > 1e-6:
        u = max(0.0, min(1.0, math.hypot(x - ax, y - ay) / reach))
    else:
        u = 0.0
    d = dn + (df - dn) * (u ** cv if u > 0.0 else 0.0)
    return max(smin, min(smax, v * d))


def speed(x, y, sw, sh):
    """Pace at (x, y): linear in size (call only while active())."""
    smin, smax, pmin, pmax = _A[8], _A[9], _A[10], _A[11]
    s = size(x, y, sw, sh)
    if smax - smin < 1e-6:
        return pmax
    f = (s - smin) / (smax - smin)
    return pmin + (pmax - pmin) * f


def squash(x, y, sw):
    """(k, ux, uy): the planet's foreshortening at (x, y) - drawn k x as
    long along the unit direction (ux, uy) from the anchor, width kept.
    None when the planet is off or there is nothing to squash."""
    if _A is None or _A[12] is None:
        return None
    th, dx, dy, dist = _theta(x, y, sw)
    if dist < 1e-3:
        return None
    k = 1.0 - _A[12][4] * (1.0 - math.cos(th))
    k = max(0.05, min(1.0, k))
    if k > 0.999:
        return None
    return k, dx / dist, dy / dist


class _Squasher:
    """Per-object planet squash on a QPainter, cheap enough for every dust
    puff: one setTransform per object on top of the layer's own transform
    (the camera).  Usage:  sq = squasher(p, sw);  sq.at(x, y); draw ...;
    sq.at(x2, y2); draw ...;  sq.done()."""

    def __init__(self, p, sw):
        self.p = p
        self.sw = sw
        self.base = p.transform() if planet_on() else None

    def at(self, x, y):
        """Squash whatever is drawn next about its own spot (x, y)."""
        if self.base is None:
            return
        from PyQt5.QtGui import QTransform
        q = squash(x, y, self.sw)
        if q is None:
            self.p.setTransform(self.base)
            return
        k, ux, uy = q
        f = 1.0 - k
        m11, m12 = 1.0 - f * ux * ux, -f * ux * uy
        m21, m22 = m12, 1.0 - f * uy * uy
        dx = x - (x * m11 + y * m21)
        dy = y - (x * m12 + y * m22)
        self.p.setTransform(QTransform(m11, m12, m21, m22, dx, dy) * self.base)

    def done(self):
        if self.base is not None:
            self.p.setTransform(self.base)


def squasher(p, sw):
    return _Squasher(p, sw)
