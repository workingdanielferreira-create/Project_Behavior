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
          float(cfg["speed_min"]), float(cfg["speed_max"]))


def active():
    return _A is not None


def size_range():
    """(s_min, s_max) of the live rule (None when off)."""
    if _A is None:
        return None
    return _A[8], _A[9]


def size(x, y, sw, sh):
    """Drawn size at (x, y) (call only while active())."""
    (ax, ay, vb, vt, dn, df, ff, cv, smin, smax, _p0, _p1) = _A
    yf = max(0.0, min(1.0, y / sh)) if sh > 0 else 0.5
    v = vt + (vb - vt) * yf
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
