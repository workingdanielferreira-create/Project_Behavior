"""
Power techniques — anime signature moves for the FX Kit "technique"
primitive, painted by hand at the same standard as the sword techniques
(laser/swordfx.py, whose frame, pen and timeline they share) and the ki
strikes (laser/strikefx.py).

Styles (params.style):

  ssj_aura         Super Saiyan aura (modern Dragon Ball style) shaped to
                   the fighter's own silhouette, with flame physics: licks
                   of flame born on the body's edge rise and keep only part
                   of the fighter's speed, so at rest they stand straight up
                   and on the move they stream behind it; at speed the
                   aura's skin stretches into a comet trail with speed lines.
                   Toggles: power-up burst (flash, shock rings, dust blast),
                   rising rocks, power surges (flare-ups now and then),
                   ground cracks, SSJ2 lightning.
  rasen_shuriken   Rasen-shuriken: an orb of wind charges in the palm, four
                   blades grow out of it and spin up with a high whine ring,
                   wind is sucked in; then it is thrown at the target, and
                   where it lands (the target, a hit, or the end of its range)
                   it bursts into a huge sphere of wind full of countless
                   needle cuts that keeps hitting (Pierce + Re-hit) until it
                   collapses.
  gigantic_meteor  Gigantic Meteor (Broly): a small, dense orb gathers over
                   the anchor with rings compressing into it, then drops on
                   the target, growing as it falls; anything under it is
                   caught and dragged down with it (Grip, a real pull in
                   Battle), ground into the trench it gouges while it keeps
                   hitting, until it explodes in a towering blast.
  ghost_kamikaze   Super Ghost Kamikaze Attack (Gotenks): grinning ghosts
                   puff out of the anchor one after another, hover a moment
                   with a bob, then chase the target and blow up on contact
                   (or at the end of their range).
  serious_punch    Serious Punch (Saitama): a long, still wind-up (air
                   rings pulling in, dust lifting, a glint), then one punch:
                   a blinding flash and a colossal shock cone that tears
                   across the screen with vapour rings and speed lines,
                   splitting the sky along its line and blowing the clouds
                   apart.
  black_hole       Black hole gravity (Welt Yang): a black hole opens on the
                   target — a black event horizon, a photon ring, a tilted
                   accretion disc (front and back halves either side of the
                   core) with hot clumps orbiting, debris spiralling in — and
                   pulls every opposing fighter inside its pull radius toward
                   it (a real pull in Battle), hurting what it holds, until
                   it collapses and bursts.

Parameters (the technique's own, reused; see TECH_STYLE_DEFAULTS):

  ssj_aura         radius = aura size round the body, length = flame
                   height, thickness = flame width, span = movement reaction
                   %, swing_ticks = ignite, hold_ticks = how long it burns;
                   aura_burst / aura_debris / aura_surges / aura_cracks /
                   lightning toggles, lightning_rate (sparks per second)
  rasen_shuriken   radius = orb radius, span = blade reach (px), thickness =
                   explosion radius, length = range, swing_ticks = charge,
                   hold_ticks = explosion time
  gigantic_meteor  radius = orb radius at launch, thickness = radius when it
                   lands, length = how far it drags down (px), span = grip
                   (0-100 %), swing_ticks = charge, hold_ticks = drag time
  ghost_kamikaze   radius = ghost size, thickness = blast radius, length =
                   range, span = bob (px), swing_ticks = ticks between ghosts,
                   hold_ticks = release time
  serious_punch    radius = fist radius, thickness = cone half-width at full
                   reach, length = reach, swing_ticks = wind-up, hold_ticks =
                   the blast's travel time
  black_hole       radius = event horizon radius, thickness = accretion disc
                   width, length = pull radius, span = pull speed (px/s),
                   swing_ticks = forming, hold_ticks = how long it holds

Hits: give these effects Pierce (a non-piercing hit cuts the instance short)
and, for the ones that keep hurting (rasen-shuriken explosion, meteor drag,
black hole), a Re-hit.  Every ghost can hit once.

Pull (gigantic_meteor, black_hole): pulls() lists this tick's pull fields;
fxkit.FxDriver collects them and World.refresh_battle moves the opposing
fighters at the start of the next tick, the same boundary FX hits use.

Everything drawn is a pure function of the instance (age, seed, the anchor's
path, the target's path), so FX Studio's port (tools/fx/studio/powerfx.js)
draws the same pixels.
"""

import math

from . import fxkit as F
from . import swordfx as S

STYLES = ("ssj_aura", "rasen_shuriken", "gigantic_meteor", "ghost_kamikaze", "serious_punch", "black_hole")
PULL_STYLES = ("gigantic_meteor", "black_hole")

AURA_FADE = 30
AURA_N = 28                  # silhouette points round the body
AURA_FPS = 24                # the aura animates at 24 fps (_draw_aura_fps)
AURA_LICK_LIFE = 16
AURA_RATE = 5                # flame licks born per tick (x density)
AURA_RISE = 1.6              # how fast flames rise, px per tick (x scale)
AURA_LAG = 0.9               # share of the fighter's speed the flames fall behind by (x reaction)
AURA_FULL = 3.0              # speed (px/tick, x scale / reaction) at which the aura points fully back
AURA_SWING = 0.72            # how slowly it swings round: weight kept per tick of history
AURA_SWING_N = 12            # ticks of history the swing looks at
AURA_DRIFT = 0.6             # how far a lick drifts along the flow (x its rise per tick)
AURA_FRAG_LIFE = 14          # fragments that break off on a sharp turn
AURA_FRAG_P = 0.7            # chance per tick of a full-speed hairpin turn
AURA_STRETCH = 2.2           # how far the skin streams behind per px/tick of speed
AURA_SURGE_SLOT = 90         # surges: at most one in each slot of this many ticks
AURA_SURGE_LEN = 20
AURA_CRACKS = 7
AURA_ROCK_EVERY = 3
AURA_ROCK_LIFE = 70
AURA_SLOT = 4                # lightning: one roll every this many ticks
AURA_BOLT_LIFE = 6
AURA_BOLT_FLICKER = (1.0, 0.35, 1.0, 0.7, 0.3, 0.15)
BOLT = (150, 205, 255)
ROCK = (78, 66, 54)
CRACK = (26, 20, 18)

RS_SPEED = 8.0               # thrown orb, px per tick (x scale)
RS_SPIN = (0.04, 0.55)       # blade spin at the start / end of the charge, rad per tick
RS_GROW = 9
RS_SHRINK = 12
RS_FADE = 18

MET_FALL = 30
MET_LOB = 0.22               # the drop's lob, times its distance
MET_GROW_DRAG = 0.12         # extra growth while it drags
MET_BLAST_HIT = 8
MET_BLAST_LIFE = 44
DUST = (110, 98, 84)

GH_FLOAT = 16                # ticks a ghost hovers before it charges
GH_OUT = 3.2                 # puff-out speed, px per tick
GH_DRAG = 0.86
GH_SPEED = 6.5
GH_ACCEL = 0.35
GH_TURN = 0.16               # rad per tick
GH_FAN = 55.0                # puff-out spread, +- degrees
GH_ARRIVE = 1.2              # blows up this close (times its size)
GH_BLAST_LIFE = 30
GH_BODY = (236, 240, 255)
SMOKE = (92, 86, 80)

SP_OUT = 2
SP_FLASH = 8
SP_RINGS = 5
SP_SPLIT_LIFE = 46
CLOUD = (214, 220, 232)

BH_COLLAPSE = 12
BH_BURST_HIT = 6
BH_BURST_LIFE = 34
BH_TILT = -0.32
BH_SQ = 0.3
BH_CLUMPS = 9


# ---------------------------------------------------------------- helpers
def _ti(P, k, lo=0):
    return max(lo, F.trunc(float(P.get(k) or 0)))


def _at(lst, k):
    return lst[max(0, min(k, len(lst) - 1))]


def _hyp(x, y):
    return math.sqrt(x * x + y * y)


def _smooth(u):
    u = S._cl(u)
    return u * u * (3 - 2 * u)


def _arc(pen, x, y, rx, ry, tilt, a0, a1, c, a, w, n=24):
    """Part of a tilted ellipse, from angle a0 to a1 (radians)."""
    if a <= 1 or w <= 0.05 or rx <= 0.5:
        return
    ca, sa = math.cos(tilt), math.sin(tilt)
    pts = []
    for i in range(n + 1):
        t = a0 + (a1 - a0) * i / n
        px, py = math.cos(t) * rx, math.sin(t) * ry
        pts.append((x + px * ca - py * sa, y + px * sa + py * ca))
    pen.polyline(pts, c, a, w)


def _circle(cx, cy, r, n=20):
    return [(cx + math.cos(i * math.pi * 2 / n) * r, cy + math.sin(i * math.pi * 2 / n) * r) for i in range(n)]


def _sparks(pen, inst, x, y, a, n, salt, c, ps, sp=(3.0, 8.0), life=(10.0, 20.0), grav=0.08, ang0=0.0, spread=math.pi):
    """Sparks thrown from (x, y), a ticks ago."""
    for j in range(n):
        r = S.rng_for(inst.seed, j, salt)
        lf = life[0] + (life[1] - life[0]) * r()
        if a >= lf:
            continue
        an = ang0 + r.uniform(-spread, spread)
        v = r.uniform(sp[0], sp[1]) * ps
        fd = S.drag_dist(0.87, a)
        sx, sy = x + math.cos(an) * v * fd, y + math.sin(an) * v * fd + grav * ps * a * a
        dk = 0.87 ** a
        q = a / lf
        pen.line(sx, sy, sx - math.cos(an) * v * dk * 1.6, sy - math.sin(an) * v * dk * 1.6, S.mix(S.HOT, c, q),
                 255 * (1 - q), 1.4 * ps)


def _bolt(r, x0, y0, ang, L, n, jit):
    """A jagged line of n segments from (x0, y0)."""
    ca, sa = math.cos(ang), math.sin(ang)
    pts = []
    for m in range(n + 1):
        u = m / float(n)
        j = 0.0 if m in (0, n) else r.uniform(-1, 1) * jit
        pts.append((x0 + ca * L * u - sa * j, y0 + sa * L * u + ca * j))
    return pts


# ---------------------------------------------------------------- timeline
def _rs_fmax(P):
    return max(1, int(math.ceil(float(P["length"]) / RS_SPEED)))


def gh_count(P):
    return _ti(P, "hold_ticks") // _ti(P, "swing_ticks", 1) + 1


def gh_max(P):
    return GH_FLOAT + int(math.ceil(float(P["length"]) / GH_SPEED)) + 24


def active_ticks(P):
    st = S._style(P)
    if st == "ssj_aura":
        return _ti(P, "swing_ticks", 1) + _ti(P, "hold_ticks", 1)
    if st == "rasen_shuriken":
        return _ti(P, "swing_ticks", 1) + _rs_fmax(P) + _ti(P, "hold_ticks", 1) + 1
    if st == "gigantic_meteor":
        return _ti(P, "swing_ticks", 1) + MET_FALL + _ti(P, "hold_ticks", 1) + MET_BLAST_HIT
    if st == "ghost_kamikaze":
        return (gh_count(P) - 1) * _ti(P, "swing_ticks", 1) + gh_max(P) + 1
    if st == "serious_punch":
        return _ti(P, "swing_ticks", 1) + SP_OUT + _ti(P, "hold_ticks", 1) + 1
    return _ti(P, "swing_ticks", 1) + _ti(P, "hold_ticks", 1) + BH_COLLAPSE + BH_BURST_HIT


def total_ticks(P):
    st = S._style(P)
    if st == "ssj_aura":
        return active_ticks(P) + AURA_FADE
    if st == "rasen_shuriken":
        return active_ticks(P) + RS_FADE
    if st == "gigantic_meteor":
        return _ti(P, "swing_ticks", 1) + MET_FALL + _ti(P, "hold_ticks", 1) + MET_BLAST_LIFE
    if st == "ghost_kamikaze":
        return active_ticks(P) + GH_BLAST_LIFE
    if st == "serious_punch":
        return active_ticks(P) + SP_SPLIT_LIFE
    return _ti(P, "swing_ticks", 1) + _ti(P, "hold_ticks", 1) + BH_COLLAPSE + BH_BURST_LIFE


def on_spawn(inst, host):
    inst.tq_sil = []          # aura: the body outline per tick (swordfx.on_tick)
    inst.tq_lk = {}           # aura: flame-lick random draws per birth tick (_aura_licks)
    inst.tq_pic = None        # aura: (24 fps frame, its recorded drawing) (_draw_aura_fps)
    inst.tq_det = None        # rasen-shuriken: where it went off when a hit stopped it (tick, x, y)
    inst.tq_gh = {}           # ghosts: index -> flight state (_gh_sim)


# ================================================================ ssj aura
# The aura hugs the fighter's real silhouette (inst.tq_sil: AURA_N points
# round the body per tick, from the sprite on screen; an ellipse when there
# is none) and reacts to movement like a flame in the wind: flame licks are
# born on the body's edge every tick, rise, and keep only part of the
# fighter's speed, so at rest they stand straight up and on the move they
# stream behind it; the aura's skin stretches into a comet trail at speed.
def outline_from_alpha(w, h, alpha, n=AURA_N, thr=40):
    """Radial outline of a sprite: n points (image px) round its alpha
    centroid, the farthest opaque pixel along each ray (clockwise from the
    top).  None when the image is empty.  FX Studio's port is
    POWERFX.outlineFromAlpha."""
    step = max(1, min(w, h) // 32)
    sx = sy = cnt = 0
    for y in range(0, h, step):
        for x in range(0, w, step):
            if alpha(x, y) > thr:
                sx += x
                sy += y
                cnt += 1
    if cnt == 0:
        return None
    cx, cy = sx / float(cnt), sy / float(cnt)
    far = math.hypot(w, h)
    dstep = max(0.5, step * 0.5)
    out = []
    for i in range(n):
        an = 2 * math.pi * i / n - math.pi / 2
        ca, sa = math.cos(an), math.sin(an)
        best, d = 0.0, 0.0
        while d < far:
            x, y = int(cx + ca * d), int(cy + sa * d)
            if 0 <= x < w and 0 <= y < h and alpha(x, y) > thr:
                best = d
            d += dstep
        out.append((cx + ca * best, cy + sa * best))
    return out


def _aura_sil(inst, ps, t):
    """The body outline at tick t (AURA_N world points), or an ellipse
    round the anchor when the fighter has no sprite to read."""
    s = _at(inst.tq_sil, t) if inst.tq_sil else None
    if s:
        return s
    x, y = _at(inst.tq_path, t)
    return [(x + math.cos(2 * math.pi * i / AURA_N - math.pi / 2) * 8 * ps,
             y + math.sin(2 * math.pi * i / AURA_N - math.pi / 2) * 14 * ps) for i in range(AURA_N)]


def _centroid(pts):
    n = float(len(pts))
    return sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n


def _aura_vel(inst, t):
    """The fighter's velocity at tick t, px per tick (smoothed over 3 ticks)."""
    x1, y1 = _at(inst.tq_path, t)
    x0, y0 = _at(inst.tq_path, t - 3)
    k = float(min(3, max(1, t)))
    return (x1 - x0) / k, (y1 - y0) / k


def _aura_aim(inst, ps, react, t):
    """Angle the aura should point at tick t: straight up at rest, turning
    toward the opposite of the movement as the speed rises (fully opposite
    at AURA_FULL)."""
    vx, vy = _aura_vel(inst, max(0, t))
    s = min(1.0, _hyp(vx, vy) / ps * react / AURA_FULL)
    if s <= 0:
        return -math.pi / 2
    to = math.atan2(-vy, -vx)
    d = math.atan2(math.sin(to + math.pi / 2), math.cos(to + math.pi / 2))
    return -math.pi / 2 + d * s


def _aura_flow(inst, ps, react, t):
    """The way the aura's flames point at tick t (unit vector): its aim,
    swung round smoothly over the last AURA_SWING_N ticks so turns and stops
    don't snap.  Everything "up" in the aura follows it, about the anchor."""
    sx = sy = 0.0
    w = 1.0
    for j in range(AURA_SWING_N + 1):
        a = _aura_aim(inst, ps, react, t - j)
        sx += w * math.cos(a)
        sy += w * math.sin(a)
        w *= AURA_SWING
    d = _hyp(sx, sy)
    if d < 1e-6:
        a = _aura_aim(inst, ps, react, t)
        return math.cos(a), math.sin(a)
    return sx / d, sy / d


def _aura_turn(inst, ps, react, t):
    """How sharply the fighter turned at tick t (0-1): the bend between its
    heading now and 4 ticks ago (a reversal = 1), scaled by its speed."""
    v1x, v1y = _aura_vel(inst, t)
    v0x, v0y = _aura_vel(inst, t - 4)
    s1, s0 = _hyp(v1x, v1y), _hyp(v0x, v0y)
    if t < 4 or s1 < 0.5 * ps or s0 < 0.5 * ps:
        return 0.0
    co = (v1x * v0x + v1y * v0y) / (s1 * s0)
    bend = (1 - co) / 2.0
    return min(1.0, bend * 2.0) * min(1.0, max(s1, s0) / ps * react / AURA_FULL)


def _aura_k(P, t):
    """(size, alpha) of the aura at tick t."""
    Ti = _ti(P, "swing_ticks", 1)
    act = active_ticks(P)
    if t < Ti:
        u = t / float(Ti)
        return S.ease_out3(u) * (1 + 0.25 * math.sin(math.pi * u)), 1.0
    if t < act:
        return 1.0, 1.0
    q = S._cl((t - act) / float(AURA_FADE))
    return 1.0 + 0.1 * q, (1.0 - q) ** 1.5


def _aura_surge(inst, P, t):
    """(intensity 1-1.6, tick the surge began or None): a flare of power now
    and then, while it burns (Surges on)."""
    if not P.get("aura_surges") or t < _ti(P, "swing_ticks", 1) or t >= active_ticks(P):
        return 1.0, None
    slot = t // AURA_SURGE_SLOT
    r = S.rng_for(inst.seed, slot, 251)
    b = slot * AURA_SURGE_SLOT + F.trunc(r() * (AURA_SURGE_SLOT - AURA_SURGE_LEN))
    a = t - b
    if a < 0 or a >= AURA_SURGE_LEN:
        return 1.0, None
    return 1.0 + 0.6 * math.sin(math.pi * a / float(AURA_SURGE_LEN)), b


def _aura_hit(inst, tx, ty, hr, ps):
    P = inst.fx["params"]
    t = inst.age
    if t >= active_ticks(P):
        return False
    k, _a = _aura_k(P, t)
    sil = _aura_sil(inst, ps, t)
    cx, cy = _centroid(sil)
    rmax = max(_hyp(x - cx, y - cy) for (x, y) in sil)
    return _hyp(tx - cx, ty - cy) <= hr + (rmax + float(P["radius"]) * ps) * k


# The lick's 8 samples along its length: (s, taper, falloff, s - 0.2), worked
# out once (the same values _lick used to compute for every lick, every frame).
_LICK_S = tuple((j / 7.0,
                 math.sin(math.pi * min(1.0, 0.25 + j / 7.0)) if j / 7.0 < 0.75 else 1.0,
                 (1 - j / 7.0) ** 0.8,
                 j / 7.0 - 0.2) for j in range(8))


def _lick(cx, cy, ux, uy, ln, w, bend):
    """A flame tongue: round at its base (cx, cy), tapering to a tip ln px
    along (ux, uy), curling by bend px."""
    px, py = -uy, ux
    left, right = [], []
    for (s, ta, fo, s2) in _LICK_S:
        hw = w * ta * fo
        cv = bend * s * s
        bx, by = cx + ux * s2 * ln + px * cv, cy + uy * s2 * ln + py * cv
        left.append((bx + px * hw, by + py * hw))
        right.append((bx - px * hw, by - py * hw))
    right.reverse()
    return left + right


def _aura_licks(inst, P, b, dens):
    """The flame licks born at tick b: (size k, [7 random draws per lick]).
    Rolled once when first needed and kept while they can still show
    (inst.tq_lk), instead of re-rolled every frame of their life."""
    lk = inst.tq_lk
    got = lk.get(b)
    if got is None:
        bk, _b0 = _aura_k(P, b)
        bs, _s0 = _aura_surge(inst, P, b)
        draws = []
        for j in range(max(0, F.jround(AURA_RATE * dens * bs))):
            r = S.rng_for(inst.seed, b, 271 + j)
            draws.append((r(), r(), r(), r(), r(), r(), r()))
        got = lk[b] = (bk, bs, draws)
        for old in [k for k in lk if k <= b - AURA_LICK_LIFE]:
            del lk[old]
    return got


def _draw_aura(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    if t >= total_ticks(P):
        return
    c, bright, _deep = S._colours(inst, host)
    k, al = _aura_k(P, t)
    act = active_ticks(P)
    Ti = _ti(P, "swing_ticks", 1)
    R = float(P["radius"]) * ps
    Lf = float(P["length"]) * ps
    Tw = float(P["thickness"]) * ps
    react = max(0.0, float(P.get("span") if P.get("span") is not None else 100)) / 100.0
    dens = float(P.get("density") or 1)
    sk, sb = _aura_surge(inst, P, t)
    sil = _aura_sil(inst, ps, t)
    cx, cy = _centroid(sil)
    vx, vy = _aura_vel(inst, t)
    sp = _hyp(vx, vy)
    ux, uy = (vx / sp, vy / sp) if sp > 0.05 else (0.0, 0.0)
    feet_y = max(y for (_x, y) in sil)
    half_w = max(abs(x - cx) for (x, _y) in sil)
    fl = 0.92 + 0.08 * math.sin(t * 1.7) + 0.05 * math.sin(t * 4.3)
    # 1: ground — cracks at the feet, rocks and dust (painted normally, under the light)
    pen.add(False)
    if P.get("aura_cracks") and t >= 1:
        _aura_cracks(pen, inst, P, ps, c, t, act)
    if P.get("aura_burst") and t < 34:
        x0, _y = _centroid(_aura_sil(inst, ps, 0))
        fy0 = max(y for (_x, y) in _aura_sil(inst, ps, 0))
        for j in range(max(0, F.jround(14 * dens))):
            r = S.rng_for(inst.seed, j, 261)
            an = r.uniform(0, math.pi * 2)
            v0 = r.uniform(3, 7) * ps
            d = v0 * S.drag_dist(0.9, t)
            q = t / 34.0
            pen.glow(x0 + math.cos(an) * d, fy0 + math.sin(an) * d * 0.3 - t * 0.2 * ps, (4 + 6 * q) * ps * r.uniform(0.8, 1.3),
                     DUST, 110 * (1 - q) ** 1.5, 0.6)
    if P.get("aura_debris"):
        _aura_rocks(pen, inst, P, ps, c, t, act)
    if hasattr(pen, "light"):
        pen.light()           # _draw_aura_fps: the rest goes on the light layer
    pen.add(True)
    if al <= 0:
        return
    # 2: a soft glow over the whole aura
    Gx, Gy = _aura_flow(inst, ps, react, t)
    hh = 0.15 * (feet_y - cy)
    pen.glow(cx + Gx * hh, cy + Gy * hh, (half_w + R * 2 + Lf * 0.5) * k * sk, c, 55 * al * fl, 0.5)
    # 3: the aura's skin: the silhouette pushed out, taller on top, streaming
    #    behind the fighter when it moves (a comet at speed)
    n = len(sil)
    # the way the flames flow: up at rest, turned to point back along the motion
    gx, gy = Gx, Gy
    for (x, y) in sil:
        pen.glow(x, y, (R * 1.8 + Tw) * k * sk, c, 34 * al * fl, 0.5)
    for (m, col, alpha) in ((1.0, c, 30), (0.6, S.mix(c, bright, 0.5), 30), (0.28, bright, 30)):
        pts = []
        for i, (x, y) in enumerate(sil):
            dx, dy = x - cx, y - cy
            d = _hyp(dx, dy) or 1.0
            nx, ny = dx / d, dy / d
            ext = R * (1 + 0.22 * math.sin(t * 0.55 + i * 1.7) + 0.14 * math.sin(t * 1.35 - i * 0.9))
            ext += R * 0.6 * abs(nx)   # wider at the sides: an egg round the body
            ext += Lf * 0.6 * max(0.0, nx * gx + ny * gy) ** 1.5 * (1 + 0.25 * math.sin(t * 0.8 + i))
            back = max(0.0, -(nx * ux + ny * uy))
            tail = back ** 1.5 * sp * AURA_STRETCH * react * ps
            e = ext * m * k * sk
            tl = tail * k * (0.6 if m == 1.0 else 0.0)   # only the outer skin streams back; the licks make the comet
            pts.append((x + nx * e - ux * tl, y + ny * e - uy * tl))
        pen.poly(pts, col, alpha * al * fl)
    # 4: flame licks, attached: each is born on a point of the body's edge
    #    and stays with that point, rising along the aura's flow (so they never
    #    spill out on their own); the aura's turn makes the trail
    life_max = AURA_LICK_LIFE
    # at speed the attached flames stretch back along the flow (capped): the comet
    stretch = min(1.0, sp / ps * react / AURA_FULL)
    c_mid = S.mix(c, bright, 0.6)
    for b in range(max(0, t - life_max + 1), t + 1):
        if b >= act:
            break
        bk, bs, draws = _aura_licks(inst, P, b, dens)
        a = t - b
        for (r0, r1, r2, r3, r4, r5, r6) in draws:
            life = life_max * (0.6 + (1.0 - 0.6) * r2)
            u = a / life
            if u >= 1:
                continue
            fade = math.sin(math.pi * min(1.0, 0.15 + u * 0.85)) * al
            if 60 * fade <= 1:
                continue      # too faint to draw (Pen.poly would skip all three)
            ex, ey = sil[min(n - 1, int(r0 * n))]
            dx, dy = ex - cx, ey - cy
            d = _hyp(dx, dy) or 1.0
            nx, ny = dx / d, dy / d
            off = R * (0.2 + (1.1 - 0.2) * r1) * bk
            rise = AURA_RISE * ps * (0.8 + (1.35 - 0.8) * r3) * bs
            # a little outward, laid out in the aura's frame (wider across the flow than along it)
            npp, npl = nx * -gy + ny * gx, nx * gx + ny * gy
            ox_ = (-gy * npp * 0.7 + gx * npl * 0.35) * ps
            oy_ = (gx * npp * 0.7 + gy * npl * 0.35) * ps
            rx, ry = gx * rise + ox_, gy * rise + oy_
            rl = _hyp(rx, ry) or 1.0
            fx_, fy_ = rx / rl, ry / rl
            ph = 0 + (math.pi * 2 - 0) * r4
            sway = math.sin(a * 0.45 + ph) * 1.6 * ps * u
            drift = AURA_DRIFT * a * (1 + 1.5 * stretch)
            px = ex + nx * off + rx * drift - fy_ * sway
            py = ey + ny * off + ry * drift + fx_ * sway
            ln = Lf * (0.55 + (1.0 - 0.55) * r5) * (0.45 + 0.8 * math.sin(math.pi * min(1.0, u * 1.15))) * bk * (1 + 1.2 * stretch)
            w = Tw * (0.7 + (1.2 - 0.7) * r6) * (1 - u) ** 0.5 * bk
            bend = math.sin(a * 0.3 + ph) * w * 1.2
            pen.poly(_lick(px, py, fx_, fy_, ln, w, bend), c, 60 * fade)
            pen.poly(_lick(px, py, fx_, fy_, ln * 0.7, w * 0.5, bend * 0.7), c_mid, 50 * fade)
            if u < 0.45:
                pen.poly(_lick(px, py, fx_, fy_, ln * 0.4, w * 0.22, bend * 0.4), S.HOT, 55 * fade * (1 - u / 0.45))
    # 4b: on a sharp turn at speed, a few small fragments of the aura break off
    #     and fly on the way the fighter was going, fading fast
    for b in range(max(0, t - AURA_FRAG_LIFE + 1), t + 1):
        if b >= act:
            break
        sharp = _aura_turn(inst, ps, react, b)
        if sharp <= 0:
            continue
        r = S.rng_for(inst.seed, b, 281)
        if r() >= sharp * AURA_FRAG_P:
            continue
        silb = _aura_sil(inst, ps, b)
        bcx, bcy = _centroid(silb)
        ovx, ovy = _aura_vel(inst, b - 4)
        bgx, bgy = _aura_flow(inst, ps, react, b)
        a = t - b
        for j in range(1 + int(r() * 2)):
            ex, ey = silb[min(n - 1, int(r() * n))]
            life = r.uniform(9, AURA_FRAG_LIFE)
            sv = r.uniform(0.45, 0.75)
            if a >= life:
                continue
            u = a / life
            vx_, vy_ = ovx * sv + bgx * AURA_RISE * ps, ovy * sv + bgy * AURA_RISE * ps
            vl = _hyp(vx_, vy_) or 1.0
            px = ex + (ex - bcx) * 0.3 + vx_ * S.drag_dist(0.9, a)
            py = ey + (ey - bcy) * 0.3 + vy_ * S.drag_dist(0.9, a)
            ln = Lf * 0.45 * (1 - 0.5 * u) * k
            w = Tw * 0.6 * (1 - u) * k
            fade = (1 - u) ** 1.2 * al
            pen.poly(_lick(px, py, -vx_ / vl, -vy_ / vl, ln, w, 0.0), c, 80 * fade)
            pen.poly(_lick(px, py, -vx_ / vl, -vy_ / vl, ln * 0.6, w * 0.45, 0.0), bright, 90 * fade)
    # 5: sparks of energy rising off it, riding with the body along the flow
    for b in range(max(0, t - 23), t + 1):
        if b >= act:
            break
        a = t - b
        for j in range(max(0, F.jround(1 * dens))):
            r = S.rng_for(inst.seed, b, 291 + j)
            ex, ey = sil[min(n - 1, int(r() * n))]
            life = r.uniform(14, 24)
            if a >= life:
                continue
            q = a / life
            rise = AURA_RISE * ps * r.uniform(1.2, 2.0)
            side = r.uniform(-1, 1) * R * 0.5
            x = ex + gx * rise * a * 0.8 - gy * side
            y = ey + gy * rise * a * 0.8 + gx * side
            tl = 2 * ps + rise * 1.2
            pen.line(x, y, x - gx * tl, y - gy * tl, S.mix(c, S.HOT, 0.6), 200 * (1 - q) * al, 1.1 * ps)
            pen.glow(x, y, 2.2 * ps, S.HOT, 200 * (1 - q) * al, 0.6)
    # 6: a white-hot rim hugging the body
    rim = []
    for (x, y) in sil:
        dx, dy = x - cx, y - cy
        d = _hyp(dx, dy) or 1.0
        rim.append((x + dx / d * 1.5 * ps, y + dy / d * 1.5 * ps))
    pen.polyline(rim + rim[:1], c, 80 * al * k, 3.0 * ps)
    pen.polyline(rim + rim[:1], S.HOT, 110 * al * fl * k, 1.0 * ps)
    # 7: speed lines streaming off it when it moves fast
    if sp * react > 2.0:
        g = min(1.0, (sp * react - 2.0) / 4.0)
        for j in range(max(0, F.jround(4 * dens))):
            r = S.rng_for(inst.seed, t, 301 + j)
            ex, ey = sil[min(n - 1, int(r() * n))]
            ln = sp * r.uniform(1.5, 3) * react
            pen.line(ex, ey, ex - ux * ln, ey - uy * ln, S.mix(c, S.HOT, 0.5), 170 * g * al, 1.1 * ps)
    # 8: ignition — a flash and a shock ring (Burst on)
    if P.get("aura_burst"):
        if t < 6:
            pen.glow(cx, cy, (half_w + R) * (1.6 + 1.5 * t / 6.0), S.HOT, 240 * (1 - t / 6.0))
        a = t - Ti // 3
        if 0 <= a < 18:
            q = a / 18.0
            rr = (half_w + R) * (1.2 + 4.0 * S.ease_out3(q))
            pen.ring(cx, cy, rr, rr * 0.85, 0.0, c, 210 * (1 - q), 3.5 * ps * (1 - q) + 0.2)
            pen.ring(cx, feet_y, rr * 1.2, rr * 0.3, 0.0, S.HOT, 170 * (1 - q), 2.0 * ps * (1 - q) + 0.2)
    # 9: a power surge flares a ring off the body as it starts
    if sb is not None:
        a = t - sb
        if a < 12:
            q = a / 12.0
            rr = (half_w + R) * (1.3 + 2.0 * S.ease_out3(q))
            pen.ring(cx, cy, rr, rr * 1.15, 0.0, bright, 160 * (1 - q), 2.2 * ps * (1 - q) + 0.2)
    # 10: Super Saiyan 2 lightning, every now and then, crackling over the body
    if P.get("lightning"):
        p_slot = min(1.0, max(0.0, float(P.get("lightning_rate") or 0)) * AURA_SLOT * F.TICK_S)
        s_now = t // AURA_SLOT
        for s in range(max(0, s_now - 2), s_now + 1):
            for j in range(2):
                r = S.rng_for(inst.seed, s, 231 + j)
                if r() >= p_slot * (1.0 if j == 0 else 0.35):
                    continue
                b = s * AURA_SLOT + F.trunc(r() * AURA_SLOT)
                kk = t - b
                if kk < 0 or kk >= AURA_BOLT_LIFE or b >= act:
                    continue
                f = AURA_BOLT_FLICKER[kk] * al
                x0, y0 = sil[min(n - 1, int(r() * n))]
                x0 += (cx - x0) * r.uniform(0.0, 0.5)
                y0 += (cy - y0) * r.uniform(0.0, 0.5)
                ang = r.uniform(0, math.pi * 2)
                L = r.uniform(12, 28) * ps * k
                rj = S.rng_for(inst.seed, s * 7 + j, 240 + kk)   # the bolt re-jags every tick
                pts = _bolt(rj, x0, y0, ang, L, 6, 5 * ps)
                bx, by = pts[3]
                br = _bolt(rj, bx, by, ang + (0.6 if rj() < 0.5 else -0.6), L * 0.45, 3, 3 * ps)
                pen.glow(x0, y0, 10 * ps, BOLT, 160 * f)
                pen.polyline(pts, BOLT, 140 * f, 3.2 * ps)
                pen.polyline(br, BOLT, 110 * f, 2.2 * ps)
                pen.polyline(pts, S.HOT, 255 * f, 1.1 * ps)
                pen.polyline(br, S.HOT, 220 * f, 0.8 * ps)


def _aura_snap(t):
    """(24 fps frame number, the tick it starts on) for tick t (FX Studio:
    auraSnap)."""
    q = t * F.TICK_MS * AURA_FPS // 1000
    return q, -(-q * 1000 // (F.TICK_MS * AURA_FPS))


class _LayerPen(S.Pen):
    """Records the aura in two layers: the ground (cracks, rocks, dust;
    painted normally) and, from light() on, the light (painted additively)."""

    def __init__(self, hints):
        from PyQt5.QtGui import QPainter, QPicture
        self.pics = [QPicture(), QPicture()]
        self.hints = hints
        S.Pen.__init__(self, QPainter(self.pics[0]))
        self.p.setRenderHints(hints)

    def light(self):
        from PyQt5.QtGui import QPainter
        self.p.end()
        S.Pen.__init__(self, QPainter(self.pics[1]))
        self.p.setRenderHints(self.hints)

    def end(self):
        if self.p.isActive():
            self.p.end()


def _layer_image(pic, plus):
    """A recorded layer rendered once into an image of just its size
    (plus: painted additively): (image, x, y), or None when it drew nothing."""
    from PyQt5.QtGui import QImage, QPainter
    r = pic.boundingRect()
    if r.isEmpty():
        return None
    img = QImage(r.width() + 2, r.height() + 2, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    if plus:
        p.setCompositionMode(QPainter.CompositionMode_Plus)
    p.translate(1 - r.x(), 1 - r.y())
    p.drawPicture(0, 0, pic)
    p.end()
    return img, r.x() - 1, r.y() - 1


def _draw_aura_fps(pen, inst, host, ps):
    """The aura at 24 fps: drawn as it is on the first tick of its 24 fps
    frame, once, in two recorded layers (_LayerPen), then put down on every
    tick of that frame, moved with the fighter so it stays on the body.  The
    ground (a few cracks / rocks, mixing normal and added paint) is replayed
    as recorded; the light (the flames: almost all the work) is rendered once
    into an image and added on whole pixels (a painter that is scaled or
    turned replays it as recorded instead: no resampled images)."""
    from PyQt5.QtGui import QPainter, QTransform
    t = inst.age
    q, ts = _aura_snap(t)
    ts = min(ts, t)
    p = pen.p
    cache = inst.tq_pic
    if cache is None or cache[0] != q:
        lp = _LayerPen(p.renderHints())
        inst.age = ts
        try:
            _draw_aura(lp, inst, host, ps)
        finally:
            inst.age = t
            lp.end()
        cache = inst.tq_pic = (q, lp.pics, None)
    ax, ay = _at(inst.tq_path, t)
    bx, by = _at(inst.tq_path, ts)
    dx, dy = ax - bx, ay - by
    p.save()
    p.translate(dx, dy)
    p.drawPicture(0, 0, cache[1][0])
    p.setCompositionMode(QPainter.CompositionMode_Plus)
    if p.worldTransform().type() <= QTransform.TxTranslate:
        if cache[2] is None:
            cache = inst.tq_pic = (q, cache[1], _layer_image(cache[1][1], True))
        if cache[2] is not None:
            img, ix, iy = cache[2]
            m = p.worldTransform()
            p.resetTransform()
            p.drawImage(round(m.dx() + ix), round(m.dy() + iy), img)
    else:
        p.drawPicture(0, 0, cache[1][1])
    p.restore()


def _aura_cracks(pen, inst, P, ps, c, t, act):
    """Cracks spreading over the ground from the feet as it ignites (Cracks on)."""
    sil0 = _aura_sil(inst, ps, 0)
    x0, _y = _centroid(sil0)
    y0 = max(y for (_x, y) in sil0)
    half = max(abs(x - x0) for (x, _y2) in sil0)
    grow = S.ease_out3(t / 10.0)
    fade = 1.0 if t < act else max(0.0, 1 - (t - act) / float(AURA_FADE))
    hot = max(0.0, 1 - t / 45.0)
    for i in range(AURA_CRACKS):
        r = S.rng_for(inst.seed, i, 311)
        an = (i + r.uniform(-0.3, 0.3)) * 2 * math.pi / AURA_CRACKS
        ln = half * r.uniform(2.0, 4.0) * grow
        pts = [(x0, y0)]
        for m in range(1, 6):
            u = m / 5.0
            j = r.uniform(-1, 1) * 0.35
            pts.append((x0 + math.cos(an + j) * ln * u, y0 + math.sin(an + j) * ln * u * 0.3))
        pen.polyline(pts, CRACK, 200 * fade, 1.6 * ps)
        if hot > 0:
            pen.add(True)
            pen.polyline(pts, c, 170 * hot * fade, 0.9 * ps)
            pen.add(False)


def _aura_rocks(pen, inst, P, ps, c, t, act):
    """Rocks lifting off the ground round the feet while it burns (Debris on)."""
    for b in range(max(0, t - AURA_ROCK_LIFE), min(t, act) + 1, AURA_ROCK_EVERY):
        bvx, bvy = _aura_vel(inst, b)
        if _hyp(bvx, bvy) > 1.5:
            continue          # only off the ground it stands on
        a = t - b
        silb = _aura_sil(inst, ps, b)
        x0, _y = _centroid(silb)
        y0 = max(y for (_x, y) in silb)
        half = max(abs(x - x0) for (x, _y2) in silb)
        r = S.rng_for(inst.seed, b, 321)
        life = AURA_ROCK_LIFE * r.uniform(0.6, 1.0)
        if a >= life:
            continue
        q = a / life
        x = x0 + r.uniform(-2.4, 2.4) * half + math.sin(a * 0.12 + r() * 6) * 2 * ps
        y = y0 + r.uniform(-2, 3) * ps - r.uniform(0.35, 0.9) * ps * a
        sz = r.uniform(1.0, 2.6) * ps
        rot = r.uniform(0, math.pi) + a * r.uniform(-0.08, 0.08)
        fa = min(1.0, a / 6.0) * (1 - q) ** 0.7
        pts = [(x + math.cos(rot + m * 1.6 + 0.3 * (m % 2)) * sz * (0.8 + 0.3 * (m % 2)),
                y + math.sin(rot + m * 1.6 + 0.3 * (m % 2)) * sz * (0.8 + 0.3 * (m % 2))) for m in range(4)]
        pen.poly(pts, ROCK, 230 * fa)
        pen.add(True)
        pen.glow(x, y - sz * 0.4, sz * 1.6, c, 90 * fa)
        pen.add(False)


# ================================================================ rasen-shuriken
def _rs_launch(inst, ps):
    """(x0, y0, ux, uy, flight ticks, range) of the throw."""
    P = inst.fx["params"]
    Tc = _ti(P, "swing_ticks", 1)
    x0, y0 = _at(inst.tq_path, Tc)
    tx, ty = _at(inst.tq_tp, Tc)
    dx, dy = tx - x0, ty - y0
    d = _hyp(dx, dy)
    L = float(P["length"]) * ps
    if d < 1:
        ux, uy = inst.tq_f
        rng = L
    else:
        ux, uy = dx / d, dy / d
        rng = max(30 * ps, min(L, d))
    return x0, y0, ux, uy, max(1, int(math.ceil(rng / (RS_SPEED * ps)))), rng


def _rs_det(inst, ps):
    """(tick, x, y) where it goes off."""
    if inst.tq_det is not None:
        return inst.tq_det
    x0, y0, ux, uy, n, rng = _rs_launch(inst, ps)
    return (_ti(inst.fx["params"], "swing_ticks", 1) + n, x0 + ux * rng, y0 + uy * rng)


def _rs_orb_at(inst, ps, t):
    P = inst.fx["params"]
    Tc = _ti(P, "swing_ticks", 1)
    if t <= Tc:
        return _at(inst.tq_path, t)
    x0, y0, ux, uy, _n, _rng = _rs_launch(inst, ps)
    d = RS_SPEED * ps * (t - Tc)
    return x0 + ux * d, y0 + uy * d


def _rs_spin(t, Tc):
    if t <= Tc:
        return RS_SPIN[0] * t + (RS_SPIN[1] - RS_SPIN[0]) * t * t / (2.0 * Tc)
    return RS_SPIN[0] * Tc + (RS_SPIN[1] - RS_SPIN[0]) * Tc / 2.0 + RS_SPIN[1] * (t - Tc)


def _rs_sphere(P, ps, a):
    """Explosion radius a ticks after it went off (0 = gone)."""
    Th = _ti(P, "hold_ticks", 1)
    if a < 0 or a >= Th:
        return 0.0
    B = float(P["thickness"]) * ps
    g = S.ease_out3(a / float(RS_GROW))
    sh = 1.0
    if a > Th - RS_SHRINK:
        sh = 1 - S.ease_in3((a - (Th - RS_SHRINK)) / float(RS_SHRINK))
    return B * (0.15 + 0.85 * g) * (0.4 + 0.6 * sh) * (1 + 0.03 * math.sin(a * 1.3))


def _rs_hit(inst, tx, ty, hr, ps):
    P = inst.fx["params"]
    t = inst.age
    Tc = _ti(P, "swing_ticks", 1)
    if t < Tc or t >= inst.life:
        return False
    e, ex, ey = _rs_det(inst, ps)
    if t < e:
        x, y = _rs_orb_at(inst, ps, t)
        return _hyp(x - tx, y - ty) <= hr + float(P["radius"]) * ps + float(P["span"]) * ps * 0.5
    R = _rs_sphere(P, ps, t - e)
    return R > 0 and _hyp(ex - tx, ey - ty) <= hr + R


def _rs_on_hit(inst, ps):
    P = inst.fx["params"]
    t = inst.age
    if inst.tq_det is None and t >= _ti(P, "swing_ticks", 1):
        e, _x, _y = _rs_det(inst, ps)
        if t < e:
            x, y = _rs_orb_at(inst, ps, t)
            inst.tq_det = (t, x, y)


def _rs_blades(pen, x, y, R, span, ang, c, a, ps):
    """The four wind blades, swept back against the spin: a coloured blade
    with a white-hot inner blade."""
    if span <= R * 0.9 or a <= 1.0 / 255:
        return
    n = 10
    for i in range(4):
        th = ang + i * math.pi / 2
        for (wk, col, al) in ((0.5, c, 150), (0.22, S.HOT, 200)):
            lead, trail = [], []
            for j in range(n + 1):
                u = j / float(n)
                rr = R * 0.8 + (span - R * 0.8) * u
                base = th - 0.55 * u
                wa = wk * (1 - u) ** 0.9
                lead.append((x + math.cos(base + wa) * rr, y + math.sin(base + wa) * rr))
                trail.append((x + math.cos(base - wa * 1.6) * rr, y + math.sin(base - wa * 1.6) * rr))
            pen.poly(lead + trail[::-1], col, al * a)


def _rs_orb(pen, x, y, R, span, ang, c, bright, a, ps, spin_fast):
    pen.glow(x, y, R * 2.4 + span * 0.6, c, 90 * a)
    # the thin disc it spins in, seen at an angle
    pen.ring(x, y, span * 0.95, span * 0.95 * 0.42, 0.0, S.HOT, 120 * a, 1.4 * ps)
    pen.ring(x, y, span * 0.95, span * 0.95 * 0.42, 0.0, c, 90 * a, 4.0 * ps)
    if spin_fast:
        _rs_blades(pen, x, y, R, span, ang - 0.36, c, 0.2 * a, ps)
        _rs_blades(pen, x, y, R, span, ang - 0.18, c, 0.37 * a, ps)
    _rs_blades(pen, x, y, R, span, ang, c, a, ps)
    pen.glow(x, y, R * 1.9, c, 200 * a)
    pen.glow(x, y, R * 1.15, bright, 235 * a)
    pen.glow(x, y, R * 0.6, S.HOT, 255 * a, 0.7)
    for i in range(3):
        a0 = ang * 1.7 + i * 2.09
        _arc(pen, x, y, R * 0.55, R * 0.55, 0.0, a0, a0 + 1.2, S.HOT, 170 * a, 1.1 * ps, 8)


def _draw_rasen(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    c, bright, _deep = S._colours(inst, host)
    Tc = _ti(P, "swing_ticks", 1)
    Th = _ti(P, "hold_ticks", 1)
    R0 = float(P["radius"]) * ps
    SP = float(P["span"]) * ps
    B = float(P["thickness"]) * ps
    dens = float(P.get("density") or 1)
    e, ex, ey = _rs_det(inst, ps)
    ang = _rs_spin(t, Tc)
    pen.add(True)
    if t < e:
        x, y = _rs_orb_at(inst, ps, t)
        if t <= Tc:
            # 1: charge — the orb forms, the blades grow out, wind is drawn in
            g = S.ease_out3(t / float(Tc))
            R, span = R0 * (0.35 + 0.65 * g), SP * g ** 1.5
            for i in range(max(0, F.jround(14 * dens))):
                r = S.rng_for(inst.seed, i, 301)
                per = r.uniform(10, 18)
                u = S.frac(t / per + r())
                rad = (1 - u) * SP * 2.2 + R
                an = r.uniform(0, math.pi * 2) + u * 2.5
                px, py = x + math.cos(an) * rad, y + math.sin(an) * rad
                tl = 8 * ps
                pen.line(px, py, px - math.sin(an) * tl, py + math.cos(an) * tl, S.mix(c, S.HOT, 0.5),
                         180 * math.sin(math.pi * u), 1.2 * ps)
            _rs_orb(pen, x, y, R, max(span, R * 0.9), ang, c, bright, 1.0, ps, g > 0.6)
        else:
            # 2: flight — wind streaks behind it, afterimages, the spinning orb
            x0, y0, ux, uy, _n, _rng = _rs_launch(inst, ps)
            for j in range(6):
                r = S.rng_for(inst.seed, j, 311)
                off = r.uniform(-0.5, 0.5) * SP
                ln = r.uniform(18, 40) * ps
                sx, sy = x - ux * R0 - uy * off, y - uy * R0 + ux * off
                pen.line(sx, sy, sx - ux * ln, sy - uy * ln, S.mix(c, S.HOT, 0.4), 120, 1.3 * ps)
            for (j, al) in ((2, 50), (1, 90)):
                gx, gy = _rs_orb_at(inst, ps, t - j)
                pen.glow(gx, gy, R0 * 2.0, c, al)
            _rs_orb(pen, x, y, R0, SP, ang, c, bright, 1.0, ps, True)
        return
    # 3: the explosion — a huge sphere of wind full of needle cuts
    a = t - e
    if a >= Th + RS_FADE:
        return
    RR = _rs_sphere(P, ps, a)
    if a < 6:
        pen.glow(ex, ey, B * (0.5 + 0.6 * a / 6.0), S.HOT, 255 * (1 - a / 6.0))
    if RR > 0:
        sh = RR / max(1e-6, B)
        al = min(1.0, sh * 1.2)
        pen.glow(ex, ey, RR * 1.35, c, 120 * al, 0.6)
        pen.glow(ex, ey, RR, bright, 150 * al, 0.75)
        pen.ring(ex, ey, RR, RR, 0.0, c, 90 * al, 5.0 * ps)
        pen.ring(ex, ey, RR, RR, 0.0, S.HOT, 150 * al, 2.2 * ps)
        for i in range(3):
            pen.ring(ex, ey, RR * 0.95, RR * 0.95 * 0.25, i * 1.05 + a * 0.05 * (i + 1), S.HOT, 110 * al, 1.3 * ps)
        n = max(0, F.jround(22 * dens))
        for b in range(max(0, a - 2), a + 1):
            if b >= Th:
                continue
            kk = a - b
            for j in range(n):
                r = S.rng_for(inst.seed, b, 321 + j)
                rr = RR * math.sqrt(r())
                an = r.uniform(0, math.pi * 2)
                ca = r.uniform(0, math.pi)
                ln = r.uniform(5, 13) * ps
                px, py = ex + math.cos(an) * rr, ey + math.sin(an) * rr
                dx, dy = math.cos(ca) * ln / 2, math.sin(ca) * ln / 2
                f = 1 - kk / 3.0
                pen.line(px - dx, py - dy, px + dx, py + dy, c, 120 * f, 2.2 * ps)
                pen.line(px - dx, py - dy, px + dx, py + dy, S.HOT, 255 * f, 1.0 * ps)
        if a < 14:
            _rs_blades(pen, ex, ey, R0, RR * 1.15, _rs_spin(t, Tc), c, 1 - a / 14.0, ps)
    if a < 16:
        q = a / 16.0
        rr = B * (0.3 + 1.4 * S.ease_out3(q))
        pen.ring(ex, ey, rr, rr, 0.0, c, 200 * (1 - q), 3.0 * ps * (1 - q) + 0.2)
    _sparks(pen, inst, ex, ey, a, max(0, F.jround(14 * dens)), 331, c, ps, (4.0, 10.0), (14.0, 24.0), 0.05)
    if Th <= a < Th + RS_FADE:
        q = (a - Th) / float(RS_FADE)
        rr = B * (0.2 + 0.6 * S.ease_out3(q))
        pen.ring(ex, ey, rr, rr, 0.0, S.HOT, 160 * (1 - q), 2.0 * ps * (1 - q) + 0.2)
        pen.glow(ex, ey, B * 0.4 * (1 - q), c, 160 * (1 - q))


# ================================================================ gigantic meteor
def _met_state(inst, ps, t):
    """(phase, x, y, R): phase 0 charge, 1 fall, 2 drag, 3 blast (x, y = where)."""
    P = inst.fx["params"]
    Tc = _ti(P, "swing_ticks", 1)
    Th = _ti(P, "hold_ticks", 1)
    r0, r1 = float(P["radius"]) * ps, float(P["thickness"]) * ps
    if t <= Tc:
        x, y = _at(inst.tq_path, t)
        return 0, x, y, r0 * (0.4 + 0.6 * S.ease_out3(t / float(Tc)))
    x0, y0 = _at(inst.tq_path, Tc)
    tx, ty = _at(inst.tq_tp, Tc)
    ex, ey = tx, ty - 0.45 * r1
    if t <= Tc + MET_FALL:
        u = (t - Tc) / float(MET_FALL)
        k = u ** 1.6
        lob = MET_LOB * _hyp(ex - x0, ey - y0) * math.sin(math.pi * u)
        return 1, x0 + (ex - x0) * k, y0 + (ey - y0) * k - lob, r0 + (r1 - r0) * u ** 0.9
    Ld = float(P["length"]) * ps
    if t <= Tc + MET_FALL + Th:
        v = (t - Tc - MET_FALL) / float(Th)
        return 2, ex, ey + Ld * _smooth(v), r1 * (1 + MET_GROW_DRAG * v)
    return 3, ex, ey + Ld, r1 * (1 + MET_GROW_DRAG)


def _met_hit(inst, tx, ty, hr, ps):
    P = inst.fx["params"]
    t = inst.age
    if t >= inst.life:
        return False
    ph, x, y, R = _met_state(inst, ps, t)
    if ph == 0:
        return False
    if ph == 3:
        return _hyp(x - tx, y - ty) <= hr + 2 * R
    return _hyp(x - tx, y - ty) <= hr + R


def _met_orb(pen, inst, x, y, R, c, bright, t, ps, a=1.0):
    pen.glow(x, y, R * 2.2, c, 90 * a)
    pen.glow(x, y, R * 1.25, c, 210 * a, 0.6)
    pen.glow(x, y, R * 0.95, bright, 220 * a, 0.7)
    pen.glow(x, y, R * 0.55, S.HOT, 230 * a)
    # plasma swirling over the surface
    for i in range(5):
        r = S.rng_for(inst.seed, i, 401)
        rr = R * r.uniform(0.6, 0.92)
        a0 = r.uniform(0, math.pi * 2) + t * r.uniform(0.05, 0.14) * (1 if i % 2 else -1)
        _arc(pen, x, y, rr, rr * r.uniform(0.75, 1.0), r.uniform(0, math.pi), a0, a0 + 1.0, S.HOT, 150 * a, 1.6 * ps, 8)
    # crackle on the rim, re-rolled every tick
    for j in range(2):
        r = S.rng_for(inst.seed, t, 411 + j)
        an = r.uniform(0, math.pi * 2)
        pts = _bolt(r, x + math.cos(an) * R * 0.85, y + math.sin(an) * R * 0.85, an + r.uniform(-1.2, 1.2), R * 0.5, 4, 3 * ps)
        pen.polyline(pts, S.mix(c, S.HOT, 0.6), 200 * a, 1.3 * ps)
    pen.ring(x, y, R * 1.06, R * 1.06, 0.0, c, 90 * a, 4.0 * ps)
    pen.ring(x, y, R, R, 0.0, S.HOT, 140 * a, 2.0 * ps)


def _draw_meteor(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    c, bright, _deep = S._colours(inst, host)
    Tc = _ti(P, "swing_ticks", 1)
    Th = _ti(P, "hold_ticks", 1)
    dens = float(P.get("density") or 1)
    ph, x, y, R = _met_state(inst, ps, t)
    tb = Tc + MET_FALL + Th
    # 1: dust thrown up along the trench while it drags (painted normally, under the light)
    if t > Tc + MET_FALL:
        pen.add(False)
        n_p = max(0, F.jround(2 * dens))
        for b in range(Tc + MET_FALL, min(t, tb) + 1, 2):
            a = t - b
            if a >= 30:
                continue
            _p, bx, by, bR = _met_state(inst, ps, b)
            for j in range(n_p):
                r = S.rng_for(inst.seed, b, 421 + j)
                side = -1 if j % 2 == 0 else 1
                px = bx + side * bR * r.uniform(0.6, 1.05) + side * a * r.uniform(0.3, 0.9) * ps
                py = by + bR * 0.6 - a * r.uniform(0.4, 1.0) * ps
                q = a / 30.0
                pen.glow(px, py, bR * r.uniform(0.35, 0.6) * (0.5 + q), DUST, 120 * (1 - q) ** 1.5 * min(1.0, a / 3.0), 0.6)
    pen.add(True)
    if ph == 0:
        # 2: charge — rings compressing into the orb, energy drawn in
        g = t / float(Tc)
        for j in range(3):
            u = S.frac(t / 12.0 + j / 3.0)
            rr = R * (1 + 3.5 * (1 - u))
            pen.ring(x, y, rr, rr, 0.0, c, 150 * u * g, 1.6 * ps)
        for i in range(max(0, F.jround(10 * dens))):
            r = S.rng_for(inst.seed, i, 431)
            per = r.uniform(9, 15)
            u = S.frac(t / per + r())
            an = r.uniform(0, math.pi * 2)
            r1 = R * (1.2 + 4.0 * (1 - u))
            r2 = R * (1.2 + 4.0 * max(0.0, 1 - u - 0.15))
            pen.line(x + math.cos(an) * r1, y + math.sin(an) * r1, x + math.cos(an) * r2, y + math.sin(an) * r2,
                     S.mix(c, S.HOT, 0.5), 200 * math.sin(math.pi * u), 1.2 * ps)
        _met_orb(pen, inst, x, y, R, c, bright, t, ps)
        return
    if ph in (1, 2):
        if ph == 1:
            # 3: falling — streaks behind it
            _p, px, py, _r = _met_state(inst, ps, t - 1)
            dx, dy = x - px, y - py
            d = _hyp(dx, dy) or 1.0
            ux, uy = dx / d, dy / d
            for j in range(7):
                r = S.rng_for(inst.seed, j, 441)
                off = r.uniform(-0.9, 0.9) * R
                ln = r.uniform(1.0, 2.2) * R
                sx, sy = x - ux * R * 0.6 - uy * off, y - uy * R * 0.6 + ux * off
                pen.line(sx, sy, sx - ux * ln, sy - uy * ln, S.mix(c, S.HOT, 0.3), 110, 1.6 * ps)
        else:
            # 4: dragging — the glowing trench it gouges, sparks off the leading edge
            _p, sx, sy, _r = _met_state(inst, ps, Tc + MET_FALL)
            pen.line(sx, sy + R * 0.6, x, y + R * 0.6, c, 90, R * 0.8)
            pen.line(sx, sy + R * 0.6, x, y + R * 0.6, S.HOT, 140, 2.0 * ps)
            for j in range(max(0, F.jround(4 * dens))):
                r = S.rng_for(inst.seed, t, 451 + j)
                an = math.pi / 2 + r.uniform(-1.4, 1.4)
                v = r.uniform(3, 8) * ps
                lx, ly = x + math.cos(an) * R * 0.9, y + math.sin(an) * R * 0.9
                pen.line(lx, ly, lx + math.cos(an) * v * 2, ly + math.sin(an) * v * 2 - 2 * ps, S.mix(S.HOT, c, 0.4), 220,
                         1.4 * ps)
        _met_orb(pen, inst, x, y, R, c, bright, t, ps)
        return
    # 5: the blast — flash, fireball, ground shock, a pillar of light, debris
    a = t - tb
    if a >= MET_BLAST_LIFE:
        return
    q = a / float(MET_BLAST_LIFE)
    e = S.ease_out3(a / 12.0)
    B = R
    if a < 8:
        pen.glow(x, y, B * (1.2 + 1.5 * a / 8.0), S.HOT, 255 * (1 - a / 8.0))
    w = B * (0.9 + 0.6 * e)
    hgt = B * 3.2 * e
    pen.poly([(x - w, y), (x - w * 0.45, y - hgt), (x + w * 0.45, y - hgt), (x + w, y)], c, 120 * (1 - q) ** 1.5)
    pen.poly([(x - w * 0.4, y), (x - w * 0.15, y - hgt * 1.1), (x + w * 0.15, y - hgt * 1.1), (x + w * 0.4, y)], S.HOT,
             120 * (1 - q) ** 2)
    pen.glow(x, y, B * (1.2 + 1.6 * S.ease_out3(q)), c, 220 * (1 - q), 0.5)
    pen.glow(x, y, B * (0.8 + 0.9 * e), S.mix(c, S.HOT, 0.6), 230 * (1 - q) ** 2)
    for (d0, k) in ((0, 1.0), (4, 1.4)):
        aa = a - d0
        if aa < 0:
            continue
        qq = aa / float(MET_BLAST_LIFE - d0)
        ee = S.ease_out3(qq)
        rr = B * (0.5 + 2.6 * ee) * k
        pen.ring(x, y, rr, rr * 0.4, 0.0, c, 200 * (1 - qq), 4.0 * ps * (1 - qq) + 0.2)
        pen.ring(x, y, rr * 0.8, rr * 0.8, 0.0, S.HOT, 130 * (1 - qq) ** 2, 1.6 * ps * (1 - qq) + 0.2)
    _sparks(pen, inst, x, y, a, max(0, F.jround(26 * dens)), 461, c, ps, (4.0, 11.0), (16.0, 34.0), 0.12, -math.pi / 2,
            math.pi * 0.75)


# ================================================================ ghost kamikaze
def _gh_sim(inst, i, ps, upto):
    """The ghost's flight up to tick upto: dict(b, pts, vx, vy, dist, done,
    size, ph).  Stepped once per tick and kept (the path only ever grows)."""
    P = inst.fx["params"]
    st = inst.tq_gh.get(i)
    if st is None:
        r = S.rng_for(inst.seed, i, 501)
        b = i * _ti(P, "swing_ticks", 1)
        ox, oy = _at(inst.tq_path, b)
        fan = r.uniform(-1, 1) * GH_FAN * S.D
        fx_, fy_ = inst.tq_f
        ca, sa = math.cos(fan), math.sin(fan)
        dx, dy = fx_ * ca - fy_ * sa, fx_ * sa + fy_ * ca - 0.35
        d = _hyp(dx, dy) or 1.0
        st = dict(b=b, pts=[(ox, oy)], vx=dx / d * GH_OUT * ps, vy=dy / d * GH_OUT * ps, dist=0.0, done=None,
                  size=r.uniform(0.85, 1.15), ph=r.uniform(0, math.pi * 2))
        inst.tq_gh[i] = st
    L = float(P["length"]) * ps
    arrive = GH_ARRIVE * float(P["radius"]) * ps * st["size"]
    mx = gh_max(P)
    while st["done"] is None and st["b"] + len(st["pts"]) - 1 < upto:
        h = inst.tq_ki.get(i)
        if h is not None:
            st["done"] = h[0]
            break
        k = len(st["pts"])            # ticks since it was born, after this step
        tick = st["b"] + k
        x, y = st["pts"][-1]
        tx, ty = _at(inst.tq_tp, tick)
        vx, vy = st["vx"], st["vy"]
        if k <= GH_FLOAT:
            vx, vy = vx * GH_DRAG, vy * GH_DRAG - 0.04 * ps
        else:
            sp = _hyp(vx, vy)
            ta = math.atan2(ty - y, tx - x)
            if sp < 0.5:
                an = ta
            else:
                an = math.atan2(vy, vx)
                da = math.atan2(math.sin(ta - an), math.cos(ta - an))
                an += max(-GH_TURN, min(GH_TURN, da))
            sp = min(GH_SPEED * ps, sp + GH_ACCEL * ps)
            vx, vy = math.cos(an) * sp, math.sin(an) * sp
        x, y = x + vx, y + vy
        st["vx"], st["vy"] = vx, vy
        st["dist"] += _hyp(vx, vy)
        st["pts"].append((x, y))
        if (k > GH_FLOAT and _hyp(x - tx, y - ty) <= arrive) or st["dist"] >= L or k >= mx:
            st["done"] = tick
    return st


def _gh_live(inst, ps):
    """[(index, x, y, state)] for the ghosts out this tick."""
    P = inst.fx["params"]
    t = inst.age
    out = []
    for i in range(gh_count(P)):
        b = i * _ti(P, "swing_ticks", 1)
        if b > t:
            break
        st = _gh_sim(inst, i, ps, t)
        if st["done"] is not None and t >= st["done"]:
            continue
        x, y = st["pts"][min(t - b, len(st["pts"]) - 1)]
        out.append((i, x, y, st))
    return out


def _gh_hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    r0 = float(inst.fx["params"]["radius"]) * ps
    for (_i, x, y, st) in _gh_live(inst, ps):
        if _hyp(x - tx, y - ty) <= hr + r0 * st["size"]:
            return True
    return False


def _gh_on_hit(inst, tx, ty, ps):
    best, bd = None, None
    for (i, x, y, _st) in _gh_live(inst, ps):
        d = _hyp(x - tx, y - ty)
        if bd is None or d < bd:
            best, bd = (i, x, y), d
    if best is not None:
        inst.tq_ki[best[0]] = (inst.age, best[1], best[2])


def _draw_ghost(pen, inst, x, y, R, vx, vy, k, st, c, span, t):
    sp = _hyp(vx, vy)
    if sp > 0.3:
        bx, by = -vx / sp, -vy / sp
    else:
        bx, by = 0.0, 1.0
    if by < -0.2:
        by = -0.2
        n = _hyp(bx, by) or 1.0
        bx, by = bx / n, by / n
    px_, py_ = -by, bx
    # bob across its line of flight
    wob = span * 0.3 * math.sin(k * 0.33 + st["ph"])
    x, y = x + px_ * wob, y + py_ * wob
    facing = 1 if (vx if sp > 0.3 else inst.tq_f[0]) >= 0 else -1
    body = S.mix(GH_BODY, c, 0.12)
    pen.add(True)
    pen.glow(x, y, R * 2.4, c, 110)
    pen.add(False)
    # tail streaming behind
    left, right = [], []
    for j in range(7):
        u = j / 6.0
        cx = x + bx * (R * 0.6 + u * R * 2.2) + px_ * math.sin(t * 0.4 + u * 4 + st["ph"]) * R * 0.35 * u
        cy = y + by * (R * 0.6 + u * R * 2.2) + py_ * math.sin(t * 0.4 + u * 4 + st["ph"]) * R * 0.35 * u
        hw = R * 0.85 * (1 - u) ** 0.9
        left.append((cx + px_ * hw, cy + py_ * hw))
        right.append((cx - px_ * hw, cy - py_ * hw))
    pen.poly(left + right[::-1], body, 235)
    pen.poly(_circle(x, y, R, 18), body, 245)
    # little arms
    for s in (-1, 1):
        ax, ay = x + px_ * R * 0.95 * s, y + py_ * R * 0.95 * s + R * 0.25
        pen.line(ax, ay, ax + px_ * R * 0.5 * s - bx * R * 0.2, ay + py_ * R * 0.5 * s + R * 0.15, body, 235, R * 0.32)
    # eyes and the grin
    ex = x + facing * R * 0.18
    for s in (-1, 1):
        pen.poly(_ellipse(ex + s * R * 0.3, y - R * 0.22, R * 0.15, R * 0.26), S.BLACK, 240)
    open_ = 0.25 + 0.2 * (1 if k > GH_FLOAT else 0) + 0.06 * math.sin(t * 0.9 + st["ph"])
    mx, my = x + facing * R * 0.1, y + R * 0.12
    top = [(mx + math.cos(a_) * R * 0.55, my + math.sin(a_) * R * 0.2) for a_ in _lin(math.pi * 0.08, math.pi * 0.92, 9)]
    bot = [(mx + math.cos(a_) * R * 0.5, my + math.sin(a_) * R * (0.2 + open_ * 1.6)) for a_ in _lin(math.pi * 0.92, math.pi * 0.08, 9)]
    pen.poly(top + bot, S.BLACK, 240)
    pen.add(True)


def _lin(a, b, n):
    return [a + (b - a) * j / float(n - 1) for j in range(n)]


def _ellipse(cx, cy, rx, ry, n=12):
    return [(cx + math.cos(i * math.pi * 2 / n) * rx, cy + math.sin(i * math.pi * 2 / n) * ry) for i in range(n)]


def _draw_kamikaze(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    c, bright, deep = S._colours(inst, host)
    r0 = float(P["radius"]) * ps
    B0 = float(P["thickness"]) * ps
    span = float(P["span"]) * ps
    dens = float(P.get("density") or 1)
    cad = _ti(P, "swing_ticks", 1)
    ghosts = []
    for i in range(gh_count(P)):
        b = i * cad
        if b > t:
            break
        ghosts.append((i, b, _gh_sim(inst, i, ps, t)))
    smoke = S.mix(SMOKE, deep, 0.25)
    # 1: smoke left where they blew up (painted normally, under the light)
    pen.add(False)
    for (i, b, st) in ghosts:
        if st["done"] is None:
            continue
        a = t - st["done"]
        if a < 0 or a >= GH_BLAST_LIFE + 10:
            continue
        x, y = st["pts"][min(st["done"] - b, len(st["pts"]) - 1)]
        B = B0 * st["size"]
        for j in range(max(0, F.jround(3 * dens))):
            r = S.rng_for(inst.seed, i, 520 + j)
            an = r.uniform(0, math.pi * 2)
            dr = r.uniform(0.2, 0.8) * B * S.ease_out3(a / 14.0)
            q = a / float(GH_BLAST_LIFE + 10)
            pen.glow(x + math.cos(an) * dr, y + math.sin(an) * dr - r.uniform(0.3, 0.7) * ps * a,
                     B * r.uniform(0.6, 1.0) * (0.5 + 0.8 * S.ease_out3(a / 16.0)), smoke,
                     95 * (1 - q) ** 1.5 * min(1.0, a / 3.0), 0.6)
    pen.add(True)
    for (i, b, st) in ghosts:
        k = t - b
        R = r0 * st["size"] * (0.4 + 0.6 * S.ease_out3(k / 6.0))
        # 2: the puff it comes out in
        if k < 8:
            ox, oy = st["pts"][0]
            pen.glow(ox, oy, (8 + 10 * k / 8.0) * ps, GH_BODY, 200 * (1 - k / 8.0))
        if st["done"] is None or t < st["done"]:
            # 3: the ghost in flight
            j = min(k, len(st["pts"]) - 1)
            x, y = st["pts"][j]
            px, py = st["pts"][max(0, j - 1)]
            _draw_ghost(pen, inst, x, y, R, x - px, y - py, k, st, c, span, t)
            continue
        # 4: it blows up
        a = t - st["done"]
        if a >= GH_BLAST_LIFE:
            continue
        x, y = st["pts"][min(st["done"] - b, len(st["pts"]) - 1)]
        q = a / float(GH_BLAST_LIFE)
        B = B0 * st["size"]
        ee = S.ease_out3(a / 8.0)
        if a < 5:
            pen.glow(x, y, B * (0.8 + 0.9 * a / 5.0), S.HOT, 255 * (1 - a / 5.0))
        pen.glow(x, y, B * (1.0 + 1.0 * ee), c, 210 * (1 - q), 0.45)
        pen.glow(x, y, B * (0.55 + 0.45 * ee), S.mix(c, S.HOT, 0.6), 235 * (1 - q) ** 2)
        rr = B * (0.5 + 1.7 * S.ease_out3(q))
        pen.ring(x, y, rr, rr, 0.0, c, 190 * (1 - q), 2.6 * ps * (1 - q) + 0.2)
        _sparks(pen, inst, x, y, a, max(0, F.jround(8 * dens)), 540 + i, c, ps, (2.5, 7.0), (9.0, 18.0), 0.08)


# ================================================================ serious punch
def _sp_frame(inst):
    P = inst.fx["params"]
    ox, oy = _at(inst.tq_path, _ti(P, "swing_ticks", 1))
    return S.Frame(ox, oy, inst.tq_f, inst.tq_m)


def _sp_front(P, ps, k):
    Th = _ti(P, "hold_ticks", 1)
    return float(P["length"]) * ps * S.ease_out3(min(1.0, k / float(Th)))


def _sp_hw(P, ps, lx):
    L = float(P["length"]) * ps
    return float(P["radius"]) * ps * 2 + float(P["thickness"]) * ps * (S._cl(lx / L) ** 0.75)


def _sp_hit(inst, tx, ty, hr, ps):
    P = inst.fx["params"]
    t = inst.age
    Tw = _ti(P, "swing_ticks", 1)
    if t < Tw or t >= inst.life:
        return False
    fr = _sp_frame(inst)
    dx, dy = tx - fr.ox, ty - fr.oy
    lx = dx * fr.fx + dy * fr.fy
    ly = dx * fr.vx + dy * fr.vy
    df = _sp_front(P, ps, t - Tw)
    if lx < -hr or lx > df + hr:
        return False
    return abs(ly) <= _sp_hw(P, ps, max(0.0, min(lx, df))) + hr


def _draw_serious(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    c, bright, _deep = S._colours(inst, host)
    Tw = _ti(P, "swing_ticks", 1)
    Th = _ti(P, "hold_ticks", 1)
    rf = float(P["radius"]) * ps
    L = float(P["length"]) * ps
    dens = float(P.get("density") or 1)
    if t < Tw:
        # 1: the wind-up — stillness, air pulling in, dust lifting, a glint
        fr = S._frame(inst)
        u = t / float(Tw)
        fx_, fy_ = fr.w(-rf * 1.0 * S.ease_out3(u), 0)
        pen.add(True)
        for j in range(2):
            v = S.frac(t / 9.0 + j * 0.5)
            rr = rf * (1.2 + 5 * (1 - v))
            pen.ring(fx_, fy_, rr, rr, 0.0, S.mix(c, S.HOT, 0.5), 120 * u * v, 1.2 * ps)
        for i in range(max(0, F.jround(8 * dens))):
            r = S.rng_for(inst.seed, i, 601)
            per = r.uniform(26, 44)
            v = S.frac(t / per + r())
            px = inst.x + r.uniform(-60, 60) * ps
            py = inst.y + 18 * ps - v * 40 * ps
            pen.glow(px, py, 2.2 * ps, S.mix(c, S.HOT, 0.3), 140 * math.sin(math.pi * v) * u, 0.6)
        pen.glow(fx_, fy_, rf * 2.0, c, 100 * u)
        pen.glow(fx_, fy_, rf * 0.6, S.HOT, 160 * u)
        if t >= Tw - 4:
            g = (t - (Tw - 4)) / 4.0
            ux, uy = inst.tq_f
            S._star(pen, fx_, fy_, ux, uy, rf * (1 + 2.5 * g), rf * (0.5 + 1.2 * g), S.HOT, 255, 1.2 * ps)
        return
    k = t - Tw
    fr = _sp_frame(inst)
    ang = math.atan2(inst.tq_f[1], inst.tq_f[0])
    df = _sp_front(P, ps, k)
    a_c = 1.0 if k < SP_OUT + Th else max(0.0, 1 - (k - SP_OUT - Th) / 14.0)
    a_s = S._cl(k / (Th * 0.6 + 1)) * (1.0 if k < SP_OUT + Th else max(0.0, 1 - (k - SP_OUT - Th) / float(SP_SPLIT_LIFE)))
    # 2: clouds blown apart either side of the line (painted normally)
    pen.add(False)
    n_c = max(0, F.jround(10 * dens))
    for j in range(n_c):
        for s in (-1, 1):
            r = S.rng_for(inst.seed, j, 611 + (s > 0))
            lx = (j + 0.5) / n_c * L * 1.4
            if lx > df * 1.4:
                continue
            push = (k - lx / (L * 1.4) * Th) * r.uniform(1.2, 2.4) * ps
            ly = s * (_sp_hw(P, ps, min(lx, L)) * 0.6 + max(0.0, push))
            px, py = fr.w(lx, ly)
            pen.glow(px, py, r.uniform(18, 34) * ps, CLOUD, 60 * a_s, 0.6)
    pen.add(True)
    # 3: the shock cone
    if a_c > 0 and df > 2:
        n = 12

        def cone(m):
            top = [fr.w(df * j / n, -_sp_hw(P, ps, df * j / n) * m) for j in range(n + 1)]
            bot = [fr.w(df * j / n, _sp_hw(P, ps, df * j / n) * m) for j in range(n + 1)]
            return top + bot[::-1]

        pen.poly(cone(1.0), c, 55 * a_c)
        pen.poly(cone(0.6), bright, 70 * a_c)
        pen.poly(cone(0.22), S.HOT, 110 * a_c)
        # vapour rings left where the front passed
        for i in range(SP_RINGS):
            ki = (i + 0.5) * Th / float(SP_RINGS)
            aa = k - ki
            if aa < 0 or aa >= 20:
                continue
            qq = aa / 20.0
            lx = _sp_front(P, ps, ki)
            hw = _sp_hw(P, ps, lx) * (1 + 0.3 * qq)
            px, py = fr.w(lx, 0)
            pen.ring(px, py, max(4 * ps, hw * 0.18), hw, ang, S.HOT, 170 * (1 - qq) * a_c, 2.0 * ps)
        # speed lines racing along it
        for i in range(max(0, F.jround(18 * dens))):
            r = S.rng_for(inst.seed, i, 621)
            v = r.uniform(-1, 1)
            ln = r.uniform(40, 120) * ps
            lx = S.frac(k * r.uniform(0.04, 0.08) + r()) * df
            ly = v * _sp_hw(P, ps, lx) * 0.9
            a0, a1 = fr.w(max(0.0, lx - ln), ly), fr.w(lx, ly)
            pen.line(a0[0], a0[1], a1[0], a1[1], S.mix(c, S.HOT, 0.6), 200 * a_c, 1.3 * ps)
        # the shock front
        if k < SP_OUT + Th + 8:
            a_f = 1.0 if k < SP_OUT + Th else 1 - (k - SP_OUT - Th) / 8.0
            px, py = fr.w(df, 0)
            hw = _sp_hw(P, ps, df)
            rx = max(6 * ps, float(P["thickness"]) * ps * 0.12 * df / L + rf)
            pen.ring(px, py, rx, hw, ang, c, 120 * a_f, 9.0 * ps)
            pen.ring(px, py, rx, hw, ang, S.HOT, 230 * a_f, 4.0 * ps)
    # 4: the sky split along its line, reaching past the blast
    if a_s > 0:
        end = min(L * 1.6, df * 1.6)
        a0, a1 = fr.w(0, 0), fr.w(end, 0)
        pen.line(a0[0], a0[1], a1[0], a1[1], c, 70 * a_s, 10 * ps)
        pen.line(a0[0], a0[1], a1[0], a1[1], S.HOT, 230 * a_s, 2.6 * ps)
        for s in (-1, 1):
            b0, b1 = fr.w(end * 0.1, s * 6 * ps), fr.w(end * 0.85, s * 6 * ps)
            pen.line(b0[0], b0[1], b1[0], b1[1], S.HOT, 90 * a_s, 1.0 * ps)
        pen.glow(a1[0], a1[1], 24 * ps, S.HOT, 160 * a_s)
    # 5: the fist and its flash
    lf = rf * 3 * S.ease_out3(min(1.0, k / float(SP_OUT)))
    fx_, fy_ = fr.w(lf, 0)
    if a_c > 0:
        pen.glow(fx_, fy_, rf * 2.4, c, 170 * a_c)
        pen.glow(fx_, fy_, rf * 0.8, S.HOT, 255 * a_c, 0.7)
    if k < SP_FLASH:
        q = k / float(SP_FLASH)
        e = S.ease_out3(q)
        pen.glow(fx_, fy_, (30 + 60 * e) * ps, S.HOT, 255 * (1 - q))
        _spikes(pen, fx_, fy_, ang, 10, (20 + 50 * e) * ps, (7 + 10 * e) * ps, S.HOT, 240 * (1 - q))
    _sparks(pen, inst, fx_, fy_, k, max(0, F.jround(16 * dens)), 631, c, ps, (5.0, 12.0), (12.0, 22.0), 0.05, ang,
            math.pi * 0.35)


def _spikes(pen, x, y, ang, n, r_out, r_in, c, a):
    pts = []
    for j in range(2 * n):
        rr = r_out if j % 2 == 0 else r_in
        an = ang + math.pi * j / n
        pts.append((x + math.cos(an) * rr, y + math.sin(an) * rr))
    pen.poly(pts, c, a)


# ================================================================ black hole
def _bh_k(P, t):
    """Core size (0-1) at tick t."""
    Tf = _ti(P, "swing_ticks", 1)
    Th = _ti(P, "hold_ticks", 1)
    if t < Tf:
        return S.ease_out3(t / float(Tf))
    if t < Tf + Th:
        return 1.0
    if t < Tf + Th + BH_COLLAPSE:
        return 1 - S.ease_in3((t - Tf - Th) / float(BH_COLLAPSE))
    return 0.0


def _bh_hit(inst, tx, ty, hr, ps):
    P = inst.fx["params"]
    t = inst.age
    if t >= inst.life:
        return False
    cx, cy = inst.tq_tp[0]
    d = _hyp(tx - cx, ty - cy)
    tb = _ti(P, "swing_ticks", 1) + _ti(P, "hold_ticks", 1) + BH_COLLAPSE
    if t >= tb:
        return d <= hr + float(P["radius"]) * ps * 4
    return d <= hr + float(P["radius"]) * ps * _bh_k(P, t) * 1.8


def _bh_disc(pen, cx, cy, Rc, Wd, c, k, t, front, ps):
    a0, a1 = (0.0, math.pi) if front else (math.pi, 2 * math.pi)
    inner = Rc * 1.35
    for j in range(5):
        rr = inner + Wd * j / 4.0
        _arc(pen, cx, cy, rr, rr * BH_SQ, BH_TILT, a0, a1, S.mix(c, S.HOT, 0.6 - j * 0.12), (160 - 25 * j) * k,
             Wd / 4.0 * 1.2 + 0.5 * ps, 20)
    for i in range(BH_CLUMPS):
        u = (i % 5) / 4.0
        rr = inner + Wd * u
        an = i * 2.4 + t * 0.09 * inner / max(rr, 1e-6)
        an = an % (2 * math.pi)
        if (an < math.pi) != front:
            continue
        px, py = math.cos(an) * rr, math.sin(an) * rr * BH_SQ
        ca, sa = math.cos(BH_TILT), math.sin(BH_TILT)
        pen.glow(cx + px * ca - py * sa, cy + px * sa + py * ca, Wd * 0.45 + 2 * ps, S.mix(c, S.HOT, 0.7), 200 * k)


def _draw_blackhole(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    c, bright, _deep = S._colours(inst, host)
    Tf = _ti(P, "swing_ticks", 1)
    Th = _ti(P, "hold_ticks", 1)
    k = _bh_k(P, t)
    R0 = float(P["radius"]) * ps
    Rc = R0 * k * (1 + 0.04 * math.sin(t * 0.7))
    Wd = float(P["thickness"]) * ps * k
    Lp = float(P["length"]) * ps
    dens = float(P.get("density") or 1)
    cx, cy = inst.tq_tp[0]
    end = Tf + Th + BH_COLLAPSE
    pen.add(True)
    if k > 0:
        # 1: haze over the whole pull radius
        pen.glow(cx, cy, Lp * 0.55 * k, c, 50 * k, 0.5)
        # 2: debris spiralling in
        for i in range(max(0, F.jround(26 * dens))):
            r = S.rng_for(inst.seed, i, 701)
            per = r.uniform(26, 50)
            off = r()
            u = S.frac(t / per + off)
            cyc = int(math.floor(t / per + off))
            r2 = S.rng_for(inst.seed, i * 131 + cyc, 702)
            rad0 = r2.uniform(0.45, 1.0) * Lp
            a0 = r2.uniform(0, math.pi * 2)

            def at(uu):
                rad = Rc * 1.1 + (rad0 - Rc * 1.1) * (1 - uu) ** 1.6
                an = a0 + 5.0 * uu ** 1.4
                px, py = math.cos(an) * rad, math.sin(an) * rad * 0.55
                ca, sa = math.cos(BH_TILT), math.sin(BH_TILT)
                return cx + px * ca - py * sa, cy + px * sa + py * ca

            x1, y1 = at(u)
            x0, y0 = at(max(0.0, u - 0.04))
            pen.line(x0, y0, x1, y1, S.mix(c, S.HOT, u), 220 * math.sin(math.pi * u) * k, 1.4 * ps)
        # 3: energy drawn in while it forms / collapses
        if t < Tf or t >= Tf + Th:
            g = 1 - t / float(Tf) if t < Tf else (t - Tf - Th) / float(BH_COLLAPSE)
            for i in range(12):
                r = S.rng_for(inst.seed, i, 711)
                an = r.uniform(0, math.pi * 2)
                u = S.frac(t / 8.0 + r())
                r1 = R0 * (1.2 + 5 * (1 - u))
                r2 = R0 * (1.2 + 5 * max(0.0, 1 - u - 0.2))
                pen.line(cx + math.cos(an) * r1, cy + math.sin(an) * r1, cx + math.cos(an) * r2, cy + math.sin(an) * r2,
                         S.HOT, 200 * g * math.sin(math.pi * u), 1.3 * ps)
        # 4: back half of the disc, behind the core
        _bh_disc(pen, cx, cy, Rc, Wd, c, k, t, False, ps)
        # 5: the event horizon (painted normally: black)
        pen.add(False)
        pen.glow(cx, cy, Rc * 1.3, S.BLACK, 200 * k, 0.75)
        pen.poly(_circle(cx, cy, Rc, 28), S.BLACK, 255 * min(1.0, k * 1.5))
        pen.add(True)
        # 6: photon ring, the lensed arc of the disc round it
        pen.ring(cx, cy, Rc * 1.1, Rc * 1.1, 0.0, c, 140 * k, 3.5 * ps)
        pen.ring(cx, cy, Rc * 1.04, Rc * 1.04, 0.0, S.HOT, 200 * k, 1.6 * ps)
        pen.ring(cx, cy, Rc * 1.35 + Wd * 0.5, Rc * 1.3, BH_TILT, c, 70 * k, 2.5 * ps)
        # 7: front half of the disc
        _bh_disc(pen, cx, cy, Rc, Wd, c, k, t, True, ps)
        # 8: Einstein ring
        rr = Rc * 2.2 * (1 + 0.03 * math.sin(t * 0.21))
        pen.ring(cx, cy, rr, rr, 0.0, bright, 40 * k, 1.2 * ps)
    # 9: the collapse bursts
    a = t - end
    if 0 <= a < BH_BURST_LIFE:
        q = a / float(BH_BURST_LIFE)
        if a < 6:
            pen.glow(cx, cy, R0 * (1.5 + 3 * a / 6.0), S.HOT, 255 * (1 - a / 6.0))
        rr = R0 * (1 + 6 * S.ease_out3(q))
        pen.ring(cx, cy, rr, rr, 0.0, c, 220 * (1 - q), 4.0 * ps * (1 - q) + 0.2)
        pen.ring(cx, cy, rr * 0.75, rr * 0.75 * BH_SQ * 2, BH_TILT, S.HOT, 160 * (1 - q) ** 2, 2.0 * ps * (1 - q) + 0.2)
        pen.glow(cx, cy, R0 * 3 * (1 - q), c, 160 * (1 - q))
        _sparks(pen, inst, cx, cy, a, max(0, F.jround(20 * dens)), 721, c, ps, (4.0, 10.0), (14.0, 28.0), 0.0)


# ================================================================ pull
def pulls(inst, ps):
    """This tick's pull fields [(x, y, radius, step px, falloff 0/1)]: an
    opposing fighter inside radius is moved toward (x, y) by up to step px
    (falloff 1: less toward the edge).  World.refresh_battle applies them."""
    P = inst.fx["params"]
    st = S._style(P)
    t = inst.age
    if inst.dead or t >= inst.life:
        return []
    if st == "gigantic_meteor":
        grip = S._cl(float(P.get("span") or 0) / 100.0)
        ph, x, y, R = _met_state(inst, ps, t)
        if ph not in (1, 2) or grip <= 0:
            return []
        return [(x, y + R * 0.55, R * 1.2, R * 1.2 * grip, 0)]
    if st == "black_hole":
        k = _bh_k(P, t)
        if k <= 0 or t >= _ti(P, "swing_ticks", 1) + _ti(P, "hold_ticks", 1) + BH_COLLAPSE:
            return []
        cx, cy = inst.tq_tp[0]
        return [(cx, cy, float(P["length"]) * ps, max(0.0, float(P.get("span") or 0)) * F.TICK_S * ps * k, 1)]
    return []


# ================================================================ public
def hit(inst, tx, ty, hr, ps):
    st = S._style(inst.fx["params"])
    if st == "ssj_aura":
        return _aura_hit(inst, tx, ty, hr, ps)
    if st == "rasen_shuriken":
        return _rs_hit(inst, tx, ty, hr, ps)
    if st == "gigantic_meteor":
        return _met_hit(inst, tx, ty, hr, ps)
    if st == "ghost_kamikaze":
        return _gh_hit(inst, tx, ty, hr, ps)
    if st == "serious_punch":
        return _sp_hit(inst, tx, ty, hr, ps)
    return _bh_hit(inst, tx, ty, hr, ps)


def body(inst, ps):
    """None of these clash as a blade."""
    return None


def on_hit(inst, x, y, ps):
    st = S._style(inst.fx["params"])
    if st == "rasen_shuriken":
        _rs_on_hit(inst, ps)
    elif st == "ghost_kamikaze":
        _gh_on_hit(inst, x, y, ps)


def draw(pen, inst, host, ps):
    st = S._style(inst.fx["params"])
    if st == "ssj_aura":
        _draw_aura_fps(pen, inst, host, ps)
    elif st == "rasen_shuriken":
        _draw_rasen(pen, inst, host, ps)
    elif st == "gigantic_meteor":
        _draw_meteor(pen, inst, host, ps)
    elif st == "ghost_kamikaze":
        _draw_kamikaze(pen, inst, host, ps)
    elif st == "serious_punch":
        _draw_serious(pen, inst, host, ps)
    else:
        _draw_blackhole(pen, inst, host, ps)
