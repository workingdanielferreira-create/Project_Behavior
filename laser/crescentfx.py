"""
Crescent waves — six more travelling crescents for the FX Kit "technique"
primitive, built on the sword techniques (laser/swordfx.py: its pen, maths,
colours and timeline).  The plain crescent wave stays in swordfx.

Styles (params.style, STYLES):

  crescent_drag     a fin: the upper half of a crescent standing on the
                    ground, its base ploughing along it.  Always upright (it
                    foreshortens when it runs up / down the screen, never
                    thinner than DRAG_MIN_X).  Sparks, chips and wind streaks
                    fly off the contact point.  The ground itself is the
                    world's: laser/worldfx.py lays a trench under the base,
                    throws rocks and dust the way it travels and leaves a
                    crater where it ends (ground_point).
  crescent_helix    2+ crescents weaving round each other on one line; they
                    cross every (target distance / weaves), so the last
                    crossing is on the target.  The one "in front" is bigger.
  crescent_scatter  a barrage: `moons` smaller crescents thrown at uneven
                    moments and uneven angles inside the cone `span`;
                    scatter_path fan / converge / wild.
  crescent_return   a spinning crescent.  Give it Motion boomerang: it flies
                    past the target, comes round and cuts again on the way
                    back.
  crescent_split    one big crescent that bursts split_pct % of the way to
                    the target into `moons` smaller ones; they fan out and
                    curve back in to cross on the target.
  crescent_fall     a giant crescent drops out of the sky onto the spot
                    (Motion static on the target) and slams the ground; the
                    world adds the crater, rocks and dust (worldfx).

Every style is a list of "moons" (_moons): the same hand-painted blade, each
with its own frame, size and age, a pure function of the instance (age,
seed, where it has been: tq_path), so FX Studio's port
(tools/fx/studio/crescentfx.js) draws the same pixels.  Keep the two in step.
"""

import math

from . import fxkit as F
from . import swordfx as L

STYLES = ("crescent_drag", "crescent_helix", "crescent_scatter", "crescent_return", "crescent_split", "crescent_fall")
# Styles whose base is on the ground (params.ground_px below the instance).
GROUND_STYLES = ("crescent_drag", "crescent_fall")
SCATTER_PATHS = ("fan", "converge", "wild")
ARC_DEG = 95.0            # the crescent spans +-this round its centre (swordfx WAVE_ARC_DEG)
CX = -0.5                 # crescent circle centre, x (times radius) behind the frame origin
EMBER_LIFE = 30
SHARD_LIFE = 26
FALL_WIND = 6             # moonfall: ticks the spot is marked before the blade shows
FALL_SLAM = 4             # ... and ticks its landing shock hits round the spot
DRAG_MIN_X = 0.3          # ground drag: the fin is never seen thinner than this
MAX_MOONS = 12
HOT = L.HOT
D = L.D


# ---------------------------------------------------------------- params / timeline
def _num(P, k, d):
    v = P.get(k)
    return float(d) if v is None or v == "" else float(v)


def _count(P):
    return max(1, min(MAX_MOONS, F.trunc(_num(P, "moons", 5))))


def _hold(P):
    return max(1, F.trunc(float(P.get("hold_ticks") or 48)))


def impact_tick(P):
    """Moonfall: the tick the blade meets the ground."""
    return FALL_WIND + L._swing(P)


def active_ticks(P):
    """Hit window (the instance's life)."""
    st = L._style(P)
    if st == "crescent_scatter":
        return (_count(P) - 1) * L._swing(P) + _hold(P)
    if st == "crescent_fall":
        return impact_tick(P) + max(FALL_SLAM, F.trunc(float(P.get("hold_ticks") or 0)))
    return _hold(P)


def total_ticks(P):
    return active_ticks(P) + EMBER_LIFE


# ---------------------------------------------------------------- frames / geometry
class Fr:
    """Local -> world with any two axes: a = forward (+x), b = down (+y)."""
    __slots__ = ("ox", "oy", "ax", "ay", "bx", "by")

    def __init__(self, ox, oy, ax, ay, bx, by):
        self.ox, self.oy, self.ax, self.ay, self.bx, self.by = ox, oy, ax, ay, bx, by

    def w(self, x, y):
        return (self.ox + x * self.ax + y * self.bx, self.oy + x * self.ay + y * self.by)

    def d(self, x, y):
        return (x * self.ax + y * self.bx, x * self.ay + y * self.by)


def _fr(x, y, dx, dy, m):
    return Fr(x, y, dx, dy, -dy * m, dx * m)


def _unit(x, y):
    n = math.hypot(x, y) or 1.0
    return x / n, y / n


def _pts(R, W, k, M, half):
    """[(v, outer(x, y), dir(x, y), w)] along the blade, top -> bottom (half:
    top -> middle, the fin)."""
    out = []
    n = M // 2 if half else M
    for j in range(n + 1):
        v = -1 + 2.0 * j / M
        a = v * ARC_DEG * D
        dx, dy = math.cos(a), math.sin(a)
        out.append((v, ((CX * R + R * dx) * k, R * dy * k), (dx, dy), W * k * ((1 - abs(v) ** 1.8) ** 0.85)))
    return out


def _grow(tl, ea):
    g = 0.35 + 0.65 * L.ease_out3(tl / 5.0)
    if ea >= 0:
        g *= 1 + 0.25 * L._cl(ea / 8.0)
    return g


def _pos(inst, b):
    """Where the instance was at age b (its own path, whatever its Motion)."""
    p = inst.tq_path
    return p[max(0, min(len(p) - 1, F.trunc(b)))]


def _spd(inst):
    p = inst.tq_path
    if len(p) > 1:
        return math.hypot(p[1][0] - p[0][0], p[1][1] - p[0][1])
    return math.hypot(inst.vx, inst.vy)


def _reach(inst, ps):
    """Distance from the launch point to where the target stood, along the aim."""
    o, f, tp = inst.tq_o, inst.tq_f, inst.tq_tp[0]
    return max(60.0 * ps, (tp[0] - o[0]) * f[0] + (tp[1] - o[1]) * f[1])


def _gp(inst, ps):
    return _num(inst.fx["params"], "ground_px", 30) * ps


def ground_point(inst, ps):
    """Where a ground style touches the ground now (the fin's base / the spot
    the moon falls on): the world's trench and crater go exactly here."""
    x, y = _pos(inst, min(inst.age, active_ticks(inst.fx["params"])))
    return x, y + _gp(inst, ps)


def swordfx_style(P):
    return L._style(P)


def on_ground(inst):
    return inst.fx.get("prim") == "technique" and L._style(inst.fx["params"]) in GROUND_STYLES


def _scatter_plan(inst, P, n):
    """Launch tick, angle (deg), speed and size of every moon of a barrage:
    uneven moments (first at 0, last at the end) and one angle slot each,
    handed out in a seeded order so neighbours never follow each other."""
    T = (n - 1) * L._swing(P)
    r = L.rng_for(inst.seed, 0, 211)
    us = sorted([r() for _ in range(max(0, n - 2))])
    us = [0.0] + us + ([1.0] if n > 1 else [])
    keys = [L.rng_for(inst.seed, i, 227)() for i in range(n)]
    order = sorted(range(n), key=lambda i: keys[i])
    rank = [0] * n
    for pos, i in enumerate(order):
        rank[i] = pos
    span = _num(P, "span", 70)
    plan = []
    for i in range(n):
        q = L.rng_for(inst.seed, i, 223)
        ang = (-0.5 + (rank[i] + 0.15 + 0.7 * q()) / n) * span
        sp = q.uniform(0.8, 1.35)
        sz = q.uniform(0.5, 0.72)
        wf = q.uniform(0.3, 0.66)
        wph = q.uniform(0.0, math.pi * 2)
        if i == n - 1 and n > 1:
            sz = 0.9        # the last one out is the heavy one
        plan.append((F.jround(T * us[i]), ang, sp, sz, wf, wph))
    return plan


# ---------------------------------------------------------------- the moons
def _moons(inst, ps, t):
    """Every blade of the technique at age t:
    [(index, frame, size, fade, own age, half, ticks since it ended (< 0 = live))]."""
    P = inst.fx["params"]
    st = L._style(P)
    f, m, o = inst.tq_f, inst.tq_m, inst.tq_o
    R = float(P["radius"]) * ps
    W = float(P["thickness"]) * ps
    Lf = active_ticks(P)
    tl, ea = min(t, Lf), t - Lf
    if ea >= SHARD_LIFE or t < 0:
        return []
    fade = 1.0 if ea < 0 else 1 - L._cl(ea / 8.0)
    nx, ny = -f[1] * m, f[0] * m
    if st == "crescent_drag":
        x, y = _pos(inst, tl)
        k = _grow(tl, ea)
        sx = (1.0 if m >= 0 else -1.0) * max(abs(f[0]), DRAG_MIN_X)
        off = (CX + 1) * R * k - 0.5 * W * k        # frame origin -> the middle of the base
        return [(0, Fr(x - sx * off, y + _gp(inst, ps) - f[1] * off, sx, f[1], 0.0, 1.0), k, fade, tl, True, ea)]
    if st == "crescent_return":
        x, y = _pos(inst, tl)
        d = F.rot([f[0], f[1]], _num(P, "spin_deg", 34) * tl * m)
        return [(0, _fr(x, y, d[0], d[1], m), _grow(tl, ea), fade, tl, False, ea)]
    if st == "crescent_helix":
        n = _count(P)
        wv = max(0.25, _num(P, "weaves", 2))
        A = _num(P, "span", 55) * ps
        d0 = _reach(inst, ps)
        x, y = _pos(inst, tl)
        s = math.hypot(x - o[0], y - o[1])
        k = _grow(tl, ea)
        sph = (inst.seed % 1000) * 0.01
        out = []
        for i in range(n):
            ph = math.pi * wv * s / d0 + 2 * math.pi * i / n
            Ai = A * (1 + 0.22 * math.sin(s * 0.021 / ps + i * 2.4 + sph))
            lat = Ai * math.sin(ph)
            dl = Ai * math.cos(ph) * math.pi * wv / d0
            dx, dy = _unit(f[0] + nx * dl, f[1] + ny * dl)
            out.append((i, _fr(x + nx * lat, y + ny * lat, dx, dy, m), k * (0.74 + 0.26 * math.cos(ph)), fade, tl, False, ea))
        return out
    if st == "crescent_scatter":
        n = _count(P)
        H = _hold(P)
        mode = P.get("scatter_path")
        spd = _spd(inst)
        d0 = _reach(inst, ps)
        out = []
        for i, (b, ang, sp, sz, wf, wph) in enumerate(_scatter_plan(inst, P, n)):
            ti = t - b
            if ti < 0 or ti - H >= SHARD_LIFE:
                continue
            tt, e2 = min(ti, H), ti - H
            s = spd * sp * tt
            if mode == "converge":
                amp = math.sin(ang * D) * d0 * 0.6
                lat = amp * math.sin(math.pi * s / d0)
                dl = amp * math.cos(math.pi * s / d0) * math.pi / d0
                x, y = o[0] + f[0] * s + nx * lat, o[1] + f[1] * s + ny * lat
                dx, dy = _unit(f[0] + nx * dl, f[1] + ny * dl)
            else:
                d = F.rot([f[0], f[1]], ang * m)
                x, y = o[0] + d[0] * s, o[1] + d[1] * s
                dx, dy = d[0], d[1]
                if mode == "wild":
                    wb = 18.0 * ps * min(1.0, tt / 6.0)
                    x += -d[1] * wb * math.sin(tt * wf + wph)
                    y += d[0] * wb * math.sin(tt * wf + wph)
                    d2 = F.rot([d[0], d[1]], 16.0 * math.cos(tt * wf + wph) * min(1.0, tt / 6.0))
                    dx, dy = d2[0], d2[1]
            out.append((i, _fr(x, y, dx, dy, m), _grow(tt, e2) * sz, 1.0 if e2 < 0 else 1 - L._cl(e2 / 8.0), tt, False, e2))
        return out
    if st == "crescent_split":
        n = _count(P)
        d0 = _reach(inst, ps)
        ss = L._cl(_num(P, "split_pct", 45) / 100.0) * d0
        x, y = _pos(inst, tl)
        s = math.hypot(x - o[0], y - o[1])
        if s < ss:
            return [(0, _fr(x, y, f[0], f[1], m), _grow(tl, ea) * (1 + 0.07 * math.sin(tl * 1.3)), fade, tl, False, ea)]
        run = max(1.0, d0 - ss)
        u = min((s - ss) / run, 1.5)
        ts = (s - ss) / max(0.01, _spd(inst))
        A = _num(P, "span", 110) * ps
        out = []
        for i in range(n):
            q = L.rng_for(inst.seed, i, 241)
            w = -1 + 2 * (i + 0.2 + 0.6 * q()) / n
            stag = q.uniform(-0.7, 0.7) * R * min(1.0, ts / 6.0)
            sz = q.uniform(0.5, 0.68)
            lat = A * w * math.sin(math.pi * u)
            dl = A * w * math.cos(math.pi * u) * math.pi / run if u < 1.5 else 0.0
            dx, dy = _unit(f[0] + nx * dl, f[1] + ny * dl)
            out.append((i + 1, _fr(x + f[0] * stag + nx * lat, y + f[1] * stag + ny * lat, dx, dy, m),
                        _grow(ts, ea) * sz, fade, tl, False, ea))
        return out
    # crescent_fall
    if t < FALL_WIND:
        return []
    Ts = L._swing(P)
    x, y = _pos(inst, tl)
    gy = y + _gp(inst, ps)
    th = _num(P, "fall_angle_deg", 18) * D
    ax, ay = math.sin(th) * m, math.cos(th)
    u = (t - FALL_WIND) / float(Ts)
    h = float(P.get("length") or 0) * ps * (1 - L.ease_in3(u))
    k = 0.6 + 0.4 * L._cl(u)
    if u >= 1:
        k *= 1 + 0.05 * math.sin(t * 2.1) * max(0.0, 1 - (u - 1) * Ts / 10.0)
    if ea >= 0:
        k *= 1 + 0.25 * L._cl(ea / 8.0)
    nose = (CX + 1) * R * k
    return [(0, _fr(x - ax * (h + nose), gy - ay * (h + nose), ax, ay, m), k, fade, t, False, ea)]


def _mid(fr, pts):
    return [fr.w(o[0] - dr[0] * w * 0.5, o[1] - dr[1] * w * 0.5) for (_v, o, dr, w) in pts]


# ---------------------------------------------------------------- public: hit / body
def hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    P = inst.fx["params"]
    st = L._style(P)
    R, W = float(P["radius"]) * ps, float(P["thickness"]) * ps
    if st == "crescent_fall":
        a = inst.age - impact_tick(P)
        if a < -2:
            return False
        if 0 <= a < FALL_SLAM:
            gx, gy = ground_point(inst, ps)
            if math.hypot(tx - gx, (ty - gy) * 2.0) <= hr + 1.2 * R:
                return True
    for (_i, fr, k, _fd, _tl, half, ea) in _moons(inst, ps, inst.age):
        if ea >= 0:
            continue
        prev = None
        for c in _mid(fr, _pts(R, W, k, 8, half)):
            if prev is not None and F.seg_dist(tx, ty, prev[0], prev[1], c[0], c[1]) <= hr + W * k * 0.5:
                return True
            prev = c
    return False


def body(inst, ps):
    """(points, half width) a clash treats as a cutting blade: its first live moon."""
    if inst.age >= inst.life:
        return None
    P = inst.fx["params"]
    R, W = float(P["radius"]) * ps, float(P["thickness"]) * ps
    for (_i, fr, k, _fd, _tl, half, ea) in _moons(inst, ps, inst.age):
        if ea < 0:
            return _mid(fr, _pts(R, W, k, 6, half)), W * k * 0.5
    return None


# ================================================================ drawing
def _shape(fr, pts, ox=0.0):
    outer = [fr.w(o[0] + ox, o[1]) for (_v, o, dr, w) in pts]
    inner = [fr.w(o[0] - dr[0] * w + ox, o[1] - dr[1] * w) for (_v, o, dr, w) in pts]
    return outer, inner


def _blade(pen, inst, fr, R, W, k, tl, mi, fade, half, c, deep, S):
    """One crescent blade: aura, flames off its back, bright rim, dark core,
    white-hot leading edge (the crescent wave's blade, in any frame)."""
    ph = (inst.seed % 1000) * 0.01 + mi * 1.7
    pts = _pts(R, W, k, 20, half)
    outer, inner = _shape(fr, pts)
    aura_o = [fr.w(o[0] + dr[0] * 6 * S * k, o[1] + dr[1] * 6 * S * k) for (_v, o, dr, w) in pts]
    aura_i = [fr.w(o[0] - dr[0] * (w + 4 * S * k), o[1] - dr[1] * (w + 4 * S * k)) for (_v, o, dr, w) in pts]
    pen.poly(aura_o + aura_i[::-1], c, 80 * fade)
    tongues = []
    for i in range(11):
        v = -0.9 + 1.8 * i / 10.0
        r = L.rng_for(inst.seed, i, 17 + 40 * mi)
        u1, u2 = r.uniform(0.6, 1.4), r.uniform(3.4, 5.2)
        if half and v > 0.05:
            continue
        a = v * ARC_DEG * D
        dx, dy = math.cos(a), math.sin(a)
        ww = W * k * ((1 - abs(v) ** 1.8) ** 0.85)
        bx, by = (CX * R + R * dx) * k - dx * ww * 0.8, R * dy * k - dy * ww * 0.8
        ln = (18 + 30 * L._flame(v, tl, ph + i) * u1) * S * k * (1 - 0.45 * abs(v))
        ux, uy = -1.0, 0.6 * v + 0.25 * math.sin(tl * 0.7 + i * 1.7 + mi)
        n = math.hypot(ux, uy)
        tongues.append((fr.w(bx, by), fr.w(bx + ux / n * ln, by + uy / n * ln), u2 * S * k))
    back = fr.w(CX * R * k - 0.2 * R * k, -0.45 * R * k if half else 0.0)
    pen.glow(back[0], back[1], (0.8 if half else 1.1) * R * k, c, 70 * fade, 0.4)
    for (b0, b1, wd) in tongues:
        pen.diamond(b0[0], b0[1], b1[0], b1[1], wd, c, 170 * fade)
    pen.poly(outer + inner[::-1], L.mix(c, HOT, 0.25), 235 * fade)
    pen.add(False)
    for (b0, b1, wd) in tongues:
        m0 = (b0[0] + (b1[0] - b0[0]) * 0.08, b0[1] + (b1[1] - b0[1]) * 0.08)
        m1 = (b0[0] + (b1[0] - b0[0]) * 0.75, b0[1] + (b1[1] - b0[1]) * 0.75)
        pen.diamond(m0[0], m0[1], m1[0], m1[1], wd * 0.5, deep, 220 * fade)
    core_o = [fr.w(o[0] - dr[0] * w * 0.3, o[1] - dr[1] * w * 0.3) for (_v, o, dr, w) in pts]
    core_i = []
    for (v, o, dr, w) in pts:
        mm = w * (0.88 + 0.2 * L._flame(v, tl, ph))
        core_i.append(fr.w(o[0] - dr[0] * mm, o[1] - dr[1] * mm))
    e = len(pts) if half else len(pts) - 2
    co, ci = core_o[2:e], core_i[2:e]
    pen.poly(co + ci[::-1], deep, 240 * fade)
    pen.add(True)
    pen.polyline(co, c, 120 * fade, 1.0 * S)
    front = [outer[j] for j in range(len(pts)) if abs(pts[j][0]) < 0.85]
    pen.polyline(front, HOT, 255 * fade, 2.2 * S * k)
    mid = outer[-1] if half else outer[len(outer) // 2]
    pen.glow(mid[0], mid[1], 20 * S * k, c, 130 * fade)


def _burst(pen, x, y, vx, vy, t, c, S, flat=1.0):
    """Launch flash: glow, a cross-cut diamond and a ring (flat < 1: on the ground)."""
    if t >= 14:
        return
    q = t / 14.0
    e = L.ease_out3(q)
    pen.glow(x, y, (14 + 30 * e) * S, c, 160 * (1 - q))
    pen.diamond(x - vx * 45 * S, y - vy * 45 * S, x + vx * 45 * S, y + vy * 45 * S, 4 * S * (1 - q) + 0.2, c, 220 * (1 - q))
    pen.diamond(x - vx * 40 * S, y - vy * 40 * S, x + vx * 40 * S, y + vy * 40 * S, 1.3 * S * (1 - q) + 0.2, HOT, 255 * (1 - q))
    pen.ring(x, y, (6 + 26 * e) * S, (6 + 26 * e) * S * flat, 0.0, c, 180 * (1 - q), 2.2 * S * (1 - q) + 0.2)


def _cross(pen, x, y, f, a, life, size, c, S):
    """An X glint where blades cross / split (age a of life)."""
    q = a / float(life)
    e = L.ease_out3(a / 5.0)
    ln = size * (0.7 + 0.5 * e)
    for dg in (38.0, -38.0):
        u = F.rot([f[0], f[1]], dg)
        pen.diamond(x - u[0] * ln, y - u[1] * ln, x + u[0] * ln, y + u[1] * ln, 3.4 * S * (1 - q) + 0.3, c, 230 * (1 - q))
        pen.diamond(x - u[0] * ln * 0.9, y - u[1] * ln * 0.9, x + u[0] * ln * 0.9, y + u[1] * ln * 0.9, 1.1 * S * (1 - q) + 0.2,
                    HOT, 255 * (1 - q))
    pen.glow(x, y, (10 + 16 * e) * S * (1 - q), HOT, 230 * (1 - q))
    rr = 6 * S + size * 0.8 * L.ease_out3(q)
    pen.ring(x, y, rr, rr, 0.0, c, 190 * (1 - q), 2.2 * S * (1 - q) + 0.2)


def _under(pen, inst, ps, t, st, c, R, W):
    """What lies under the blades: launch flashes, crossing glints, the
    moonfall's mark on the ground."""
    P = inst.fx["params"]
    f, m, o = inst.tq_f, inst.tq_m, inst.tq_o
    nx, ny = -f[1] * m, f[0] * m
    S = ps
    Lf = active_ticks(P)
    if st == "crescent_drag":
        _burst(pen, o[0], o[1] + _gp(inst, ps), 0.0, -1.0, t, c, S, 0.4)
    elif st in ("crescent_helix", "crescent_split", "crescent_return"):
        _burst(pen, o[0], o[1], nx, ny, t, c, S)
    spd = _spd(inst)
    if st == "crescent_helix" and spd > 0.01:
        d0 = _reach(inst, ps)
        wv = max(0.25, _num(P, "weaves", 2))
        j = 1
        while j < 40:
            sj = j * d0 / wv
            tj = sj / spd
            if tj >= Lf:
                break
            a = t - tj
            if 0 <= a < 10:
                _cross(pen, o[0] + f[0] * sj, o[1] + f[1] * sj, f, a, 10, 0.8 * R, c, S)
            j += 1
    elif st == "crescent_split" and spd > 0.01:
        ss = L._cl(_num(P, "split_pct", 45) / 100.0) * _reach(inst, ps)
        a = t - ss / spd
        if 0 <= a < 14 and ss / spd < Lf:
            _cross(pen, o[0] + f[0] * ss, o[1] + f[1] * ss, f, a, 14, 1.5 * R, c, S)
            _cross(pen, o[0] + f[0] * ss, o[1] + f[1] * ss, (nx, ny), a, 14, 1.0 * R, c, S)
    elif st == "crescent_scatter":
        for i, (b, ang, _sp, sz, _wf, _wph) in enumerate(_scatter_plan(inst, P, _count(P))):
            a = t - b
            if a < 0 or a >= 8:
                continue
            q = a / 8.0
            d = F.rot([f[0], f[1]], ang * m)
            ln = 38 * S * sz
            pen.glow(o[0], o[1], (10 + 18 * L.ease_out3(q)) * S, c, 150 * (1 - q))
            pen.diamond(o[0] + d[1] * ln, o[1] - d[0] * ln, o[0] - d[1] * ln, o[1] + d[0] * ln, 3 * S * (1 - q) + 0.2, c, 220 * (1 - q))
            pen.diamond(o[0], o[1], o[0] + d[0] * ln * 1.6, o[1] + d[1] * ln * 1.6, 1.4 * S * (1 - q) + 0.2, HOT, 240 * (1 - q))
    elif st == "crescent_fall":
        ti = impact_tick(P)
        gx, gy = ground_point(inst, ps)
        if t < ti:
            u = t / float(ti)
            rx = R * (1.6 - 0.5 * u)
            pen.ring(gx, gy, rx, rx * 0.35, 0.0, c, 60 + 160 * u, (1.2 + 1.6 * u) * S)
            pen.ring(gx, gy, rx * 0.55, rx * 0.55 * 0.35, 0.0, HOT, 140 * u * u, 1.0 * S)
            th = _num(P, "fall_angle_deg", 18) * D
            ax, ay = math.sin(th) * m, math.cos(th)
            hh = float(P.get("length") or 0) * ps + 2 * R
            pen.line(gx - ax * hh, gy - ay * hh, gx, gy, c, 30 + 90 * u, (0.8 + 1.4 * u) * S)
            pen.glow(gx, gy, (8 + 14 * u) * S, c, 120 * u)


def _embers(pen, inst, ps, t, st, c, deep, R, W):
    """Embers shed off every blade's back as it flew."""
    P = inst.fx["params"]
    S = ps
    n = _count(P) if st in ("crescent_helix", "crescent_scatter", "crescent_split") else 1
    per = max(0, F.jround(3 * float(P.get("density") or 1) / math.sqrt(n)))
    if not per:
        return
    grav = 0.18 * S
    for b in range(max(0, t - EMBER_LIFE), t):
        for (mi, fr, k, _fd, _tl, half, ea) in _moons(inst, ps, b):
            if ea >= 0:
                continue
            for j in range(per):
                r = L.rng_for(inst.seed, b * 16 + mi, 300 + j)
                life = 14 + 16 * r()
                a = t - b
                v = r.uniform(-0.9, 0.9)
                bv, pv = r.uniform(0.5, 2.5) * S, r.uniform(-1.2, 1.2) * S
                if a >= life:
                    continue
                if half:
                    v = -abs(v)
                an = v * ARC_DEG * D
                ww = W * ((1 - abs(v) ** 1.8) ** 0.85)
                sx, sy = fr.w((CX * R + R * math.cos(an) - math.cos(an) * ww) * k, (R * math.sin(an) - math.sin(an) * ww) * k)
                vx, vy = fr.d(-bv, pv)
                fd = L.drag_dist(0.93, a)
                x, y = sx + vx * fd, sy + vy * fd + 0.5 * grav * a * a
                q = a / life
                col = L.mix(HOT, c, min(1.0, q * 2)) if q < 0.5 else L.mix(c, deep, (q - 0.5) * 2)
                pen.diamond(x - 1.8 * S, y, x + 1.8 * S, y, 1.4 * S * (1 - q * 0.5), col, 230 * (1 - q))


def _drag_fx(pen, inst, ps, t, c, R, W):
    """Ground drag: wind streaks off the fin's back, the white-hot contact
    point and the sparks / chips it throws up behind it.  (The trench, rocks
    and dust belong to the world: laser/worldfx.py.)"""
    P = inst.fx["params"]
    S = ps
    f, m = inst.tq_f, inst.tq_m
    Lf = active_ticks(P)
    dens = float(P.get("density") or 1)
    sx = (1.0 if m >= 0 else -1.0) * max(abs(f[0]), DRAG_MIN_X)
    gp = _gp(inst, ps)
    if t < Lf:
        mo = _moons(inst, ps, t)
        if mo:
            (_i, fr, k, _fd, _tl, _h, _ea) = mo[0]
            # wind streaks: long, uneven lines torn off the back of the fin
            for j in range(F.jround(6 * dens)):
                slot = (t + j * 3) // 5
                r = L.rng_for(inst.seed, slot, 600 + j)
                v = -r.uniform(0.05, 0.92)
                ln = r.uniform(1.4, 3.6) * R
                rise = r.uniform(-0.18, 0.1)
                u = ((t + j * 3) % 5) / 5.0
                an = v * ARC_DEG * D
                ww = W * k * ((1 - abs(v) ** 1.8) ** 0.85)
                p0 = fr.w((CX * R + R * math.cos(an)) * k - math.cos(an) * ww - u * 0.5 * R, R * math.sin(an) * k)
                p1 = (p0[0] - sx * ln * (0.4 + 0.6 * u), p0[1] - f[1] * ln * (0.4 + 0.6 * u) + rise * ln)
                al = math.sin(math.pi * u)
                pen.line(p0[0], p0[1], p1[0], p1[1], c, 150 * al, (1.0 + 1.4 * (1 - abs(v))) * S)
                pen.line(p0[0], p0[1], (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, HOT, 170 * al, 0.7 * S)
            # the contact point: white-hot, with a low bow wave of light each side
            gx, gy = ground_point(inst, ps)
            fl = 0.75 + 0.25 * math.sin(t * 1.9 + (inst.seed % 97))
            pen.glow(gx, gy, 26 * S * k, c, 170 * fl)
            pen.glow(gx, gy, 11 * S * k, HOT, 255 * fl)
            for sgn in (1.0, -1.0):
                pen.diamond(gx, gy, gx - sx * 0.9 * R * k, gy - f[1] * 0.9 * R * k + sgn * 0.16 * R * k, 2.6 * S * k, c, 200 * fl)
            pen.diamond(gx + sx * 0.25 * R * k, gy + f[1] * 0.25 * R * k, gx - sx * 1.5 * R * k, gy - f[1] * 1.5 * R * k,
                        1.2 * S * k, HOT, 230 * fl)
    # sparks and chips thrown up and back from the contact point
    per = max(0, F.jround(4 * dens))
    grav = 0.34 * S
    for b in range(max(0, t - 20), min(t, Lf)):
        px, py = _pos(inst, b)
        py += gp
        for j in range(per):
            r = L.rng_for(inst.seed, b, 500 + j)
            life = 8 + 12 * r()
            a = t - b
            bv = r.uniform(1.5, 7.5) * S
            up = r.uniform(0.6, 5.5) * S
            side = r.uniform(-1.0, 1.0) * S
            chip = r() < 0.3
            if a >= life:
                continue
            vx, vy = -sx * bv + side * 0.4, -f[1] * bv - up
            fd = L.drag_dist(0.9, a)
            x, y = px + vx * fd, py + vy * fd + 0.5 * grav * a * a
            if y > py:
                y = py - (y - py) * 0.35        # a low bounce off the ground
            dk = 0.9 ** a
            cvx, cvy = vx * dk, vy * dk + grav * a
            q = a / life
            if chip:
                pen.diamond(x - 2.6 * S, y, x + 2.6 * S, y, 2.0 * S * (1 - q * 0.4), L.mix(c, HOT, 0.2), 235 * (1 - q))
            else:
                pen.line(x, y, x - cvx * 1.9, y - cvy * 1.9, L.mix(HOT, c, q), 255 * (1 - q), 1.5 * S)


def _fall_fx(pen, inst, ps, t, c, R, W):
    """Moonfall: speed lines while it drops, then the slam - a pillar of
    light, ground shock rings and shards thrown up."""
    P = inst.fx["params"]
    S = ps
    m = inst.tq_m
    ti = impact_tick(P)
    th = _num(P, "fall_angle_deg", 18) * D
    ax, ay = math.sin(th) * m, math.cos(th)
    gx, gy = ground_point(inst, ps)
    if FALL_WIND <= t < ti:
        mo = _moons(inst, ps, t)
        if mo:
            (_i, fr, k, _fd, _tl, _h, _ea) = mo[0]
            for j in range(7):
                r = L.rng_for(inst.seed, t // 2, 700 + j)
                yy = r.uniform(-0.95, 0.95) * R * k
                ln = r.uniform(1.2, 3.2) * R
                p0 = fr.w(CX * R * k - 0.2 * R, yy)
                pen.line(p0[0], p0[1], p0[0] - ax * ln, p0[1] - ay * ln, c, 150, 1.4 * S)
                pen.line(p0[0], p0[1], p0[0] - ax * ln * 0.5, p0[1] - ay * ln * 0.5, HOT, 150, 0.7 * S)
    a = t - ti
    if a < 0 or a >= 24:
        return
    q = a / 24.0
    e = L.ease_out3(a / 9.0)
    ff = 1 - min(1.0, a / 10.0)
    pen.glow(gx, gy, (30 + 50 * e) * S, HOT, 240 * ff)
    pen.glow(gx, gy, 2.2 * R * (0.5 + 0.5 * e), c, 150 * (1 - q), 0.4)
    hh = (float(P.get("length") or 0) * ps * 0.6 + 2.5 * R) * (1 - 0.3 * q)
    pen.diamond(gx, gy, gx - ax * hh, gy - ay * hh, (0.5 * W + 6 * S) * ff + 0.3, c, 200 * ff)
    pen.diamond(gx, gy, gx - ax * hh * 0.92, gy - ay * hh * 0.92, (0.16 * W + 2 * S) * ff + 0.2, HOT, 255 * ff)
    for j in range(3):
        aa = a - j * 3
        if aa < 0:
            continue
        qq = aa / 20.0
        if qq >= 1:
            continue
        rx = (0.5 + 2.3 * L.ease_out3(qq)) * R * (1 + 0.25 * j)
        pen.ring(gx, gy, rx, rx * 0.35, 0.0, c if j else HOT, 220 * (1 - qq), (3.4 - j) * S * (1 - qq) + 0.3)
    dens = float(P.get("density") or 1)
    grav = 0.3 * S
    for i in range(max(0, F.jround(18 * dens))):
        r = L.rng_for(inst.seed, i, 720)
        life = 12 + 12 * r()
        an = -math.pi * r.uniform(0.08, 0.92)
        sp = r.uniform(3.0, 10.0) * S
        ln = r.uniform(5, 11) * S
        if a >= life:
            continue
        vx, vy = math.cos(an) * sp, math.sin(an) * sp
        fd = L.drag_dist(0.92, a)
        x, y = gx + vx * fd, gy + vy * fd + 0.5 * grav * a * a
        dk = 0.92 ** a
        cvx, cvy = _unit(vx * dk, vy * dk + grav * a)
        qq = a / life
        pen.diamond(x - cvx * ln, y - cvy * ln, x + cvx * ln, y + cvy * ln, 2.2 * S * (1 - qq) + 0.2, c, 235 * (1 - qq))
        pen.diamond(x - cvx * ln * 0.7, y - cvy * ln * 0.7, x + cvx * ln * 0.7, y + cvy * ln * 0.7, 0.8 * S * (1 - qq) + 0.1,
                    HOT, 255 * (1 - qq))


def _shards(pen, inst, fr, R, k, mi, a, half, cnt, c, S):
    """A blade shatters where it ended (age a since)."""
    q = a / float(SHARD_LIFE)
    if q >= 1:
        return
    ff = 1 - min(1.0, a / 10.0)
    ctr = fr.w((CX + 1) * R * k * 0.5, -0.4 * R * k if half else 0.0)
    pen.glow(ctr[0], ctr[1], 40 * S * k * ff, HOT, 200 * ff)
    for i in range(cnt):
        r = L.rng_for(inst.seed, i, 91 + 40 * mi)
        v = r.uniform(-0.9, 0.9)
        j1, j2 = r.uniform(-0.4, 0.4), r.uniform(-0.4, 0.4)
        sp = r.uniform(2.0, 6.0) * S
        rot = r.uniform(0, math.pi * 2) + r.uniform(-0.25, 0.25) * a
        ln = r.uniform(7, 12) * S * (0.6 + 0.4 * k)
        if half:
            v = -abs(v)
        an = v * ARC_DEG * D
        px, py = fr.w((CX * R + R * math.cos(an)) * k, R * math.sin(an) * k)
        dx, dy = fr.d(math.cos(an) + j1, math.sin(an) + j2)
        fd = L.drag_dist(0.93, a)
        x, y = px + dx * sp * fd, py + dy * sp * fd + 0.05 * S * a * a
        ux, uy = math.cos(rot) * ln, math.sin(rot) * ln
        pen.diamond(x - ux, y - uy, x + ux, y + uy, 2.4 * S * (1 - q) + 0.2, c, 230 * (1 - q))
        pen.diamond(x - ux * 0.7, y - uy * 0.7, x + ux * 0.7, y + uy * 0.7, 0.8 * S * (1 - q) + 0.1, HOT, 255 * (1 - q))


def draw(pen, inst, host, ps):
    P = inst.fx["params"]
    st = L._style(P)
    t = inst.age
    c, _bright, deep = L._colours(inst, host)
    S = ps
    R, W = float(P["radius"]) * ps, float(P["thickness"]) * ps
    pen.add(True)
    _under(pen, inst, ps, t, st, c, R, W)
    mo = _moons(inst, ps, t)
    # afterimages: where each blade was 2, 4 and 6 ticks ago (none once the moonfall has landed)
    ghosts = () if st == "crescent_fall" and t > impact_tick(P) + 1 else (3, 2, 1)
    for j in ghosts:
        for (mi, fr, k, fd, _tl, half, ea) in _moons(inst, ps, t - 2 * j):
            if ea >= 0:
                continue
            now = [q for q in mo if q[0] == mi]
            if not now or now[0][3] <= 0:
                continue
            outer, inner = _shape(fr, _pts(R, W, k, 20, half))
            pen.poly(outer + inner[::-1], c, 55.0 / j * now[0][3])
    for (mi, fr, k, fd, tl, half, ea) in mo:
        if fd > 0:
            _blade(pen, inst, fr, R, W, k, tl, mi, fd, half, c, deep, S)
    _embers(pen, inst, ps, t, st, c, deep, R, W)
    if st == "crescent_drag":
        _drag_fx(pen, inst, ps, t, c, R, W)
    elif st == "crescent_fall":
        _fall_fx(pen, inst, ps, t, c, R, W)
    cnt = 10 if len(mo) <= 1 else 6
    for (mi, fr, k, _fd, _tl, half, ea) in mo:
        if ea >= 0:
            _shards(pen, inst, fr, R, k, mi, ea, half, cnt, c, S)
    L._hit_marks(pen, inst, c, ps, inst.tq_f[0], inst.tq_f[1])
