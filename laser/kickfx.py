"""
Kicks — the kick styles of the FX Kit "technique" primitive, painted by hand
at the same standard as the punch (laser/strikefx.py, whose impact, impact
frame and hit options they share) and the sword techniques (laser/swordfx.py,
whose frame, pen and timeline they share).

Every kick is a path of the foot: a short wind-up (WIND ticks), the kick
itself over Swing ticks, held for Hold ticks, then it fades over RETRACT
ticks.  It hits along the lower leg.  What it paints is laser/hitfx.py's
three partitions, each off / ink / energy / gritty: fx_motion (smear frames
of the leg up to contact, broken air strokes along the foot's path, the
foot), fx_impact (the hit where the foot lands, or on a whiff where it meets
the aim at its contact moment, laid along the way the foot was moving and
HEAVY times the punch's size) and fx_env (push-off dust as the kick starts, a
ground wave under the target; the axe kick's crater, the rising kick's
kick-up, the spinning kick's vortex).

Styles (params.style):

  roundhouse_kick  an arc round the hip (the anchor), radius Length, Span
                   degrees, centred on the aim: it meets the aim halfway, at
                   full speed.  kick_sweep: high_low (from above the aim line
                   down through it) or low_high.
  thrust_kick      a straight front / side kick along the aim, heavier than
                   the punch: a wide streak, bigger rings, ground dust.
  axe_kick         an arc that comes down onto the point Length along the aim
                   and lands there at full speed, moving the way axe_dir says:
                   screen_down (straight down whatever the aim), along_aim, or
                   custom (kick_angle_deg turned from the aim, clockwise,
                   mirrors with the facing).  A crater, cracks spreading along
                   the ground and debris thrown up, at the contact point
                   (axe_crater contact) or under the target's feet (feet)
                   (fx_env).
  spinning_kick    spin_turns full circles of radius Length, ending on the aim.
                   spin_mode: centered (round the anchor, a wind vortex round
                   the body: fx_env), travel (drifting forward along the aim while it
                   spins), lunge (spins in place, the last part lunges forward
                   and lands the heavy hit).
  rising_kick      a launcher: an arc rising through the point 0.9 x Length
                   along the aim and on past it, moving the way rise_dir says:
                   screen_up (up and forward), perpendicular (square to the
                   aim, the side away from screen-down), straight_up, or custom
                   (kick_angle_deg from the aim).  Dust kicked up as it starts
                   (fx_env).

Parameters (the technique's own, reused): radius = foot size, thickness =
how far the air strokes spread, length = leg reach (arc radius / thrust reach), span = arc sweep
(degrees; roundhouse / axe / rising), swing_ticks = kick ticks, hold_ticks =
ticks held at the end, density = sparks / dust / debris.

Hit options (strikefx.HIT_OPTION_STYLES): Hit-stop, screen shake, target
squash, Knockback direction (aim / tangent = the way the foot moves at
contact / custom) and Impact frame work as for the punch.  Everything is a pure function of the instance (age, seed,
the anchor, the target's path), so FX Studio's port (tools/fx/studio/kickfx.js)
draws the same pixels.
"""

import math

from . import fxkit as F
from . import swordfx as S
from . import strikefx as K
from . import hitfx as H

STYLES = ("roundhouse_kick", "thrust_kick", "axe_kick", "spinning_kick", "rising_kick")
ARC_STYLES = ("roundhouse_kick", "axe_kick", "rising_kick")

WIND = 3                 # wind-up ticks before the kick moves
RETRACT = 6              # ticks the foot fades after the hold
FEET_DROP = H.FEET_DROP  # target centre to its feet, px (x scale): ground waves, axe_crater feet
RISE_REACH = 0.9         # the rising kick meets the aim this far out (x Length)
# When in the kick (fraction of Swing ticks) the foot meets the aim.
CONTACT = {"roundhouse_kick": 0.5, "thrust_kick": 1.0, "axe_kick": 1.0, "spinning_kick": 1.0, "rising_kick": 0.55}
# How much bigger than the punch's its impact is.
HEAVY = {"roundhouse_kick": 1.15, "thrust_kick": 1.3, "axe_kick": 1.3, "spinning_kick": 1.0, "rising_kick": 1.1}
IMPACT_LIFE = H.IMPACT_LIFE


# ---------------------------------------------------------------- timeline
def _hold(P):
    return max(0, F.trunc(float(P.get("hold_ticks") or 0)))


def active_ticks(P):
    return WIND + S._swing(P) + _hold(P) + 1


def total_ticks(P):
    return WIND + S._swing(P) + _hold(P) + RETRACT + IMPACT_LIFE


def contact_tick(P):
    """The tick the foot meets the aim (a whiff bursts there)."""
    return WIND + F.jround(S._swing(P) * CONTACT[S._style(P)])


def _uc(P):
    """Time fraction of the kick at the contact tick (whole ticks)."""
    return (contact_tick(P) - WIND) / float(S._swing(P))


def _prog(st, u):
    """How far along its path the foot is at time fraction u of the kick."""
    if st == "thrust_kick":
        return S.ease_out3(u)
    if st == "axe_kick":
        return S.ease_in3(u)
    return S.ease_inout3(u)


# ---------------------------------------------------------------- geometry
def _unit(x, y):
    n = math.hypot(x, y) or 1.0
    return x / n, y / n


def _contact_dir(inst, P, st):
    """The way the foot moves when it meets the aim (axe / rising)."""
    f, m = inst.tq_f, inst.tq_m
    ang = float(P.get("kick_angle_deg") or 0) * m
    if st == "axe_kick":
        mode = P.get("axe_dir") or "screen_down"
        if mode == "along_aim":
            return f
        if mode == "custom":
            return tuple(F.rot(f, ang))
        return 0.0, 1.0
    mode = P.get("rise_dir") or "screen_up"
    if mode == "straight_up":
        return 0.0, -1.0
    if mode == "perpendicular":
        vx, vy = -f[1] * m, f[0] * m
        return (-vx, -vy) if vy > 0 else (vx, vy)
    if mode == "custom":
        return tuple(F.rot(f, ang))
    return _unit(f[0] * 0.5, -1.0)


def _arc(inst, P, st, ps):
    """(pivot x, y, radius, angle at contact, turn sign) of an arc kick."""
    L = float(P["length"]) * ps
    f, m = inst.tq_f, inst.tq_m
    ax, ay = inst.x, inst.y
    if st == "roundhouse_kick":
        s = m if (P.get("kick_sweep") or "high_low") != "low_high" else -m
        return ax, ay, L, math.atan2(f[1], f[0]), s
    axe = st == "axe_kick"
    reach = L if axe else L * RISE_REACH
    cx, cy = ax + f[0] * reach, ay + f[1] * reach
    d = _contact_dir(inst, P, st)
    back = float(P.get("span") or 0) * S.D * _prog(st, _uc(P))
    best = None
    # The circle through the contact point whose tangent there is d: the axe
    # kick on the side where it starts higher (it comes down onto the point),
    # then (and the rising kick only) the side whose pivot is nearer the hip;
    # a tie: the facing's.
    for s in (m, -m):
        rx, ry = s * d[1], -s * d[0]
        ox, oy = cx - L * rx, cy - L * ry
        ac = math.atan2(ry, rx)
        y0 = oy + math.sin(ac - s * back) * L
        k = (y0 if axe else 0.0, (ox - ax) ** 2 + (oy - ay) ** 2)
        if best is None or k[0] < best[0][0] - 1e-6 or (abs(k[0] - best[0][0]) <= 1e-6 and k[1] < best[0][1] - 1e-6):
            best = (k, ox, oy, ac, s)
    return best[1], best[2], L, best[3], best[4]


def pose(inst, t, ps):
    """(foot x, y, pivot x, y, unit tangent x, y) at tick t (may be
    fractional): where the foot is, what it turns round, and which way it
    moves."""
    P = inst.fx["params"]
    st = S._style(P)
    Ts, Th = S._swing(P), _hold(P)
    u = min(1.0, max(0.0, (t - WIND) / float(Ts)))
    f = inst.tq_f
    ax, ay = inst.x, inst.y
    L = float(P["length"]) * ps
    if st == "thrust_kick":
        r = L * _prog(st, u)
        k = t - WIND - Ts - Th
        if k > 0:
            r = L * (1 - S.ease_in3(min(1.0, k / float(RETRACT))))
        return ax + f[0] * r, ay + f[1] * r, ax, ay, f[0], f[1]
    p = _prog(st, u)
    if st == "spinning_kick":
        mode = P.get("spin_mode") or "centered"
        if mode == "travel":
            g = 1.2 * p
        elif mode == "lunge":
            g = 0.6 * S.ease_out3(min(1.0, max(0.0, (u - 0.7) / 0.3)))
        else:
            g = 0.0
        ox, oy = ax + f[0] * L * g, ay + f[1] * L * g
        s = inst.tq_m
        turns = max(0.0, float(P.get("spin_turns") or 0))
        a = math.atan2(f[1], f[0]) - s * 2 * math.pi * turns * (1 - p)
    else:
        ox, oy, L, ac, s = _arc(inst, P, st, ps)
        span = float(P.get("span") or 0) * S.D
        a = ac + s * span * (p - _prog(st, _uc(P)))
    ca, sa = math.cos(a), math.sin(a)
    return ox + ca * L, oy + sa * L, ox, oy, -sa * s, ca * s


def _leg(inst, t, ps):
    """(x0, y0, x1, y1, half width) of the lower leg while it is out."""
    P = inst.fx["params"]
    if t < WIND:
        return None
    x, y, ox, oy, _ux, _uy = pose(inst, t, ps)
    w = float(P["radius"]) * ps * 1.2 + float(P["thickness"]) * ps * 0.3
    if S._style(P) == "thrust_kick":
        if math.hypot(x - ox, y - oy) <= 2:
            return None
        return ox, oy, x, y, w
    return ox + (x - ox) * 0.35, oy + (y - oy) * 0.35, x, y, w


# ---------------------------------------------------------------- hits
def hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    g = _leg(inst, inst.age, ps)
    return g is not None and F.seg_dist(tx, ty, g[0], g[1], g[2], g[3]) <= hr + g[4]


def body(inst, ps):
    """A kick clashes along the lower leg while it is out."""
    if inst.age >= inst.life:
        return None
    g = _leg(inst, inst.age, ps)
    if g is None:
        return None
    return [(g[0], g[1]), (g[2], g[3])], g[4]


def on_hit(inst, x, y, ps):
    # the impact stays where the foot landed, laid along its motion
    fx_, fy_, _ox, _oy, ux, uy = pose(inst, inst.age, ps)
    inst.tq_imp.append((inst.age, fx_, fy_, ux, uy))


def hit_dir(inst):
    """Knockback direction (params kb_dir): aim, tangent (the way the foot
    moves now) or custom (kb_angle_deg turned from that)."""
    P = inst.fx["params"]
    mode = P.get("kb_dir") or "aim"
    if mode not in ("tangent", "custom"):
        return inst.dir
    _x, _y, _ox, _oy, ux, uy = pose(inst, inst.age, inst.ps or 1.0)
    if mode == "tangent":
        return ux, uy
    return tuple(F.rot((ux, uy), float(P.get("kb_angle_deg") or 0) * inst.tq_m))


def hitstop_step(inst, host):
    """Solo has no opponent: the kick's hit weight (hit-stop, shake) plays
    as its whiff bursts."""
    P = inst.fx["params"]
    if host is None or S._style(P) not in STYLES or not (P.get("hitstop") or P.get("shake")) or not getattr(host, "solo", False):
        return
    if not inst.tq_imp and inst.age + 1 == contact_tick(P):
        K._freeze(inst, host)


# ================================================================ drawing
def _impacts(inst, P, ps):
    """(age, x, y, ux, uy, size, salt, tick) of every impact on show: where
    the foot landed; a whiff bursts smaller where it met the aim."""
    t = inst.age
    if inst.tq_imp:
        return [(t - b, x, y, ux, uy, 1.0, 11 * n, b) for n, (b, x, y, ux, uy) in enumerate(inst.tq_imp)]
    tc = contact_tick(P)
    x, y, _ox, _oy, ux, uy = pose(inst, tc, ps)
    return [(t - tc, x, y, ux, uy, 0.55, 0, tc)]


def _motion(inst, P, ps):
    """The kick for the motion partition (hitfx.Motion): knee -> foot (a
    thrust: hip -> foot), moving the way the foot moves."""
    thrust = S._style(P) == "thrust_kick"

    def limb(t):
        x, y, ox, oy, ux, uy = pose(inst, t, ps)
        if thrust:
            return ox, oy, x, y, ux, uy
        return ox + (x - ox) * 0.35, oy + (y - oy) * 0.35, x, y, ux, uy
    Ts, Th = S._swing(P), _hold(P)
    return H.Motion(limb, WIND, contact_tick(P), WIND + Ts, WIND + Ts + Th + RETRACT, float(P["radius"]) * ps,
                    float(P["thickness"]) * ps)


def _feet(inst, b, ps):
    """Where the target's feet were on tick b."""
    tp = inst.tq_tp[min(max(0, b), len(inst.tq_tp) - 1)]
    return float(tp[1]) + FEET_DROP * ps


def _crater_at(inst, P, ps, x, y, b):
    """Where the axe kick's crater goes: the contact point, or under the
    target's feet (where the target was on tick b)."""
    if (P.get("axe_crater") or "contact") != "feet":
        return x, y
    tp = inst.tq_tp[min(max(0, b), len(inst.tq_tp) - 1)]
    return float(tp[0]), _feet(inst, b, ps)


def draw(pen, inst, host, ps):
    P = inst.fx["params"]
    st = S._style(P)
    t = inst.age
    c, _bright, _deep = S._colours(inst, host)
    Ts, Th = S._swing(P), _hold(P)
    imps = _impacts(inst, P, ps)
    hv = HEAVY[st]
    # 0: the impact frame, under everything else
    for (a, x, y, _ux, _uy, sc, salt, _b) in imps:
        K._impact_frame(pen, inst, c, ps, x, y, a, sc, salt)
    # 1: the surroundings (fx_env): push-off dust under the fighter as the
    # kick starts, the rising kick's kick-up, the spinning kick's vortex, and
    # under each impact a ground wave (the axe kick: its crater)
    p0 = inst.tq_path[min(WIND, len(inst.tq_path) - 1)]
    H.env(pen, inst, P, c, ps, ("push", t - WIND, p0[0], p0[1] + FEET_DROP * ps, -inst.tq_m, 0.0, hv, 0))
    if st == "rising_kick":
        x, y = pose(inst, WIND, ps)[:2]
        H.env(pen, inst, P, c, ps, ("kickup", t - WIND, x, y, 0.0, 0.0, 1.0, 0))
    out = WIND <= t < WIND + Ts + Th + RETRACT
    if st == "spinning_kick" and out and (P.get("spin_mode") or "centered") == "centered":
        fade = 1.0 if t < WIND + Ts + Th else 1 - (t - WIND - Ts - Th) / float(RETRACT)
        _x, _y, ox, oy, _ux, _uy = pose(inst, t, ps)
        H.env(pen, inst, P, c, ps, ("vortex", t, ox, oy, float(P["length"]) * ps, inst.tq_m, fade, 0))
    for (a, x, y, _ux, _uy, sc, salt, b) in imps:
        if st == "axe_kick":
            gx, gy = _crater_at(inst, P, ps, x, y, b)
            H.env(pen, inst, P, c, ps, ("crater", a, gx, gy, 0.0, 0.0, sc * hv, salt))
        else:
            H.env(pen, inst, P, c, ps, ("ground", a, x, _feet(inst, b, ps), 0.0, 0.0, sc * hv, salt))
    # 2: the foot and its motion (fx_motion)
    H.motion(pen, inst, P, t, ps, c, _motion(inst, P, ps))
    # 3: the impacts (fx_impact), laid along the foot's motion, heavier
    for (a, x, y, ux, uy, sc, salt, _b) in imps:
        H.impact(pen, inst, P, c, ps, x, y, a, sc * hv, salt, (ux, uy))
    pen.add(False)
