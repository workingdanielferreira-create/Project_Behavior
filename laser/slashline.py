"""
Straight slash — a single sword cut for the FX Kit "technique" primitive
(params.style "straight_slash"), built on the sword techniques
(laser/swordfx.py: its pen, maths, colours and timeline).

Daniel 2026-11-15: a slash you lay out yourself, that always lands where it
is anchored.

  * The cut's MIDDLE is its anchor point.  Whatever its angle, length or
    curve, the point halfway along the blade sits exactly on the instance
    (anchor + offset), so anchor "target" puts the middle of the cut on the
    target every time.
  * cut_deg      direction the blade travels along the cut, local degrees
                 (0 = forward, -90 = up, 90 = down, 180 = backward); mirrors
                 with the facing and turns with Follow direction / Turn
  * length       how long the cut is, end to end (px)
  * curve_pct    0 = a dead-straight line, 100 = a half circle; negative
                 bends it the other way (no limits: any value is used)
  * slash_from   where the blade starts: "start" (one end to the other),
                 "end" (the other way round) or "centre" (opens from the
                 middle outward both ways)
  * thickness    blade width at its widest (px)
  * swing_ticks  how long the blade takes to cross the whole cut
  * hold_ticks   how long the finished cut hangs in the air before it fades
                 (drawing only: it hits while it swings + 2 ticks)

Size (like the kamehameha's head, fxkit params.pos_scale): it starts at the
size the caster had when it fired and from then on follows the world's
position scale AT ITS OWN SPOT (combat.position_scale there / where the
caster stood).  So a cut anchored on a far-off target is the target spot's
size, and a travelling cut grows / shrinks as it flies.  On the big ball it
always stands upright at its own middle (fxkit CharacterFx.draw ->
speedband.travel_at), never about the caster's feet.

Everything is a pure function of the instance (age, seed, position, its
spawn frame), so FX Studio's port (tools/fx/studio/slashline.js) draws the
same pixels (the Studio has no world scale: there the size factor is 1).
Keep the two in step.
"""

import math

from . import fxkit as F
from . import swordfx as L

STYLES = ("straight_slash",)
FROMS = ("start", "end", "centre")
SLICES = 28
SPARK_LIFE = 20
FADE_MIN = 6
HOT = L.HOT
D = L.D


# ---------------------------------------------------------------- params / timeline
def _num(P, k, d):
    v = P.get(k)
    try:
        return float(d) if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return float(d)


def _from(P):
    v = P.get("slash_from")
    return v if v in FROMS else "start"


def _hold(P):
    return max(0, F.trunc(_num(P, "hold_ticks", 8)))


def _fade(P):
    return max(FADE_MIN, F.jround(1.6 * L._swing(P)))


def active_ticks(P):
    """Hit window (the instance's life): the swing + 2 ticks."""
    return L._swing(P) + 2


def total_ticks(P):
    return L._swing(P) + _hold(P) + _fade(P) + SPARK_LIFE


# ---------------------------------------------------------------- size at its own spot
def on_spawn(inst, host):
    """Remember the position scale where the caster stood when it fired:
    the cut's own size is inst.ps x (scale here / this) from then on."""
    fig = getattr(host, "fig", None) if host is not None else None
    sw, sh = getattr(fig, "screen_w", 0), getattr(fig, "screen_h", 0)
    s0 = 0.0
    if fig is not None and sw and sh:
        from . import combat as _combat
        s0 = _combat.position_scale(fig.x, fig.y, sw, sh)
    inst.sl_sc = (s0, sw, sh)      # (caster's spot scale, screen w, h); s0 0 = no world (preview)


def size(inst, ps):
    """The cut's own size factor: what it was fired at (inst.ps, else ps)
    times how much bigger / smaller its spot is than where the caster
    stood (kamehameha style)."""
    base = inst.ps or ps or 1.0
    det = getattr(inst, "sl_sc", None)
    if not det or det[0] <= 0:
        return base
    from . import combat as _combat
    s = _combat.position_scale(inst.x, inst.y, det[1], det[2])
    return base * s / det[0]


# ---------------------------------------------------------------- geometry
class Geo:
    """The cut in local space (+x forward, +y down, mirrored with the
    facing by swordfx.Frame): its middle on (0, 0)."""

    def __init__(self, inst, S):
        P = inst.fx["params"]
        self.L = _num(P, "length", 240) * S
        self.W = max(0.0, _num(P, "thickness", 12)) * S
        a = _num(P, "cut_deg", -30) * D
        self.u = (math.cos(a), math.sin(a))          # along the cut
        self.n = (-self.u[1], self.u[0])             # its bulge side (+curve)
        c = self.L / 2.0
        h = _num(P, "curve_pct", 25) / 100.0 * c     # sagitta: 100 % = half circle
        self.c, self.h = c, h
        if abs(h) < 1e-6 or c <= 1e-9:
            self.R = None
        else:
            self.R = (c * c + h * h) / (2.0 * h)
            self.th = 2.0 * math.atan2(h, c)

    def at(self, s):
        """Local point at s (0 = one end, 0.5 = the middle = (0, 0), 1 = the
        other end)."""
        if self.R is None:
            x, y = self.L * (s - 0.5), 0.0
        else:
            a = -self.th + 2.0 * self.th * s
            x = self.R * math.sin(a)
            y = (self.h - self.R) + self.R * math.cos(a) - self.h
            # (the cut bulges toward -n: its middle is the far point)
            y = -y
        return (self.u[0] * x + self.n[0] * y, self.u[1] * x + self.n[1] * y)

    def tangent(self, s):
        a, b = self.at(max(0.0, s - 0.01)), self.at(min(1.0, s + 0.01))
        dx, dy = b[0] - a[0], b[1] - a[1]
        n = math.hypot(dx, dy) or 1.0
        return dx / n, dy / n

    def width(self, s):
        """Blade width along the cut: tapered to points at both ends."""
        return self.W * (math.sin(math.pi * L._cl(s)) ** 0.6)


def _span(P, t):
    """(lo, hi, head, alpha, width factor) of the visible blade at tick t:
    the part of the cut [lo, hi] drawn, the blade head's s (None = no head)."""
    Ts, hold, Tf = L._swing(P), _hold(P), _fade(P)
    k = L.ease_out3(t / float(Ts))
    fr = _from(P)
    if fr == "end":
        lo, hi, head = 1.0 - k, 1.0, 1.0 - k
    elif fr == "centre":
        lo, hi, head = 0.5 - 0.5 * k, 0.5 + 0.5 * k, None
    else:
        lo, hi, head = 0.0, k, k
    if t <= Ts:
        return lo, hi, head, 1.0, 1.0
    if t <= Ts + hold:
        return lo, hi, None, 1.0, 1.0 - 0.25 * (t - Ts) / float(max(1, hold))
    q = L._cl((t - Ts - hold) / float(Tf))
    return lo, hi, None, 1.0 - q, 0.75 * (1.0 - q)


def _slices(g, lo, hi, wf):
    out = []
    for i in range(SLICES + 1):
        s = lo + (hi - lo) * i / SLICES
        out.append((s, g.width(s) * wf))
    return out


def _edge(fr, g, s, off):
    """World point at s, off px to the bulge side (+) of the blade line."""
    p = g.at(s)
    tx, ty = g.tangent(s)
    return fr.w(p[0] - ty * off, p[1] + tx * off)


# ---------------------------------------------------------------- hit / body
def hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    P = inst.fx["params"]
    lo, hi, _h, _a, wf = _span(P, inst.age)
    if hi - lo < 0.01:
        return False
    S = size(inst, ps)
    g = Geo(inst, S)
    fr = L._frame(inst)
    sl = _slices(g, lo, hi, wf)
    for i in range(1, len(sl)):
        a = fr.w(*g.at(sl[i - 1][0]))
        b = fr.w(*g.at(sl[i][0]))
        if F.seg_dist(tx, ty, a[0], a[1], b[0], b[1]) <= hr + max(sl[i - 1][1], sl[i][1]) * 0.5:
            return True
    return False


def body(inst, ps):
    """(points, half width) a clash treats as a cutting blade, or None."""
    if inst.age >= inst.life:
        return None
    P = inst.fx["params"]
    lo, hi, _h, _a, wf = _span(P, inst.age)
    if hi - lo < 0.01:
        return None
    S = size(inst, ps)
    g = Geo(inst, S)
    fr = L._frame(inst)
    pts = [fr.w(*g.at(lo + (hi - lo) * j / 8.0)) for j in range(9)]
    return pts, max(1.0, g.W * 0.5 * wf)


def cut_dir(inst):
    """World unit direction the blade travels (hit flashes)."""
    P = inst.fx["params"]
    g = Geo(inst, 1.0)
    fr = L._frame(inst)
    tx, ty = g.tangent(0.5)
    if _from(P) == "end":
        tx, ty = -tx, -ty
    return fr.d(tx, ty)


# ---------------------------------------------------------------- drawing
def draw(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    S = size(inst, ps)
    g = Geo(inst, S)
    fr = L._frame(inst)
    c, bright, _deep = L._colours(inst, host)
    Ts = L._swing(P)
    hold = _hold(P)
    pen.add(True)
    lo, hi, head, ga, wf = _span(P, t)
    end_t = Ts + hold + _fade(P)
    if t < end_t and hi - lo > 0.004 and ga > 0.01:
        sl = _slices(g, lo, hi, wf)
        # 0: bloom behind the blade while it is fresh
        if t <= Ts + 6:
            bf = 1.0 if t <= Ts else 1 - (t - Ts) / 6.0
            m = fr.w(*g.at((lo + hi) / 2.0))
            pen.glow(m[0], m[1], min(0.45 * g.L, 40 * S), c, 80 * bf * ga, 0.4)
        # 1-3: haze, blade body, white-hot cutting edge
        hz = 5.0 * S
        for i in range(1, len(sl)):
            s0, w0 = sl[i - 1]
            s1, w1 = sl[i]
            if w0 + w1 <= 0.02:
                continue
            # brighter toward the head while it swings
            if head is not None and hi > lo:
                u = 1.0 - abs(s1 - head) / max(1e-6, hi - lo)
            else:
                u = 0.7
            a = ga * (0.35 + 0.65 * u)
            pen.poly([_edge(fr, g, s0, 0.5 * w0 + hz), _edge(fr, g, s1, 0.5 * w1 + hz),
                      _edge(fr, g, s1, -0.5 * w1 - hz), _edge(fr, g, s0, -0.5 * w0 - hz)], c, 70 * a)
            pen.poly([_edge(fr, g, s0, 0.5 * w0), _edge(fr, g, s1, 0.5 * w1),
                      _edge(fr, g, s1, -0.5 * w1), _edge(fr, g, s0, -0.5 * w0)],
                     L.mix(c, bright, u * u), 235 * a)
            e0, e1 = max(0.8 * S, 0.22 * w0), max(0.8 * S, 0.22 * w1)
            pen.poly([_edge(fr, g, s0, e0 * 0.5), _edge(fr, g, s1, e1 * 0.5),
                      _edge(fr, g, s1, -e1 * 0.5), _edge(fr, g, s0, -e0 * 0.5)], HOT, 255 * (a ** 1.2))
        # 4: speed lines either side of the blade while it swings
        if t <= Ts + 4:
            sf = 1.0 if t <= Ts else 1 - (t - Ts) / 4.0
            for k in range(2):
                for sd in (1, -1):
                    off = sd * (g.W * 0.5 + (5 + 5 * k) * S)
                    a0, a1 = lo + (hi - lo) * (0.1 + 0.1 * k), hi - (hi - lo) * 0.05
                    if a1 - a0 < 0.02:
                        continue
                    pen.polyline([_edge(fr, g, a0 + (a1 - a0) * j / 9.0, off) for j in range(10)],
                                 c, 110 * sf * (1 - 0.35 * k), 1.1 * S)
    # 5: the finished cut flashes along its whole line, a pressure line rolls off it
    k2 = (t - (Ts - 1)) / 10.0
    if 0 <= k2 < 1:
        path = [fr.w(*g.at(j / 24.0)) for j in range(25)]
        pen.polyline(path, c, 160 * (1 - k2), 3.5 * S)
        pen.polyline(path, HOT, 255 * (1 - k2) ** 2, 1.2 * S)
    k3 = (t - Ts) / 12.0
    if 0 <= k3 < 1:
        off = (g.W * 0.5 + 18 * S * L.ease_out3(k3))
        for sd in (1, -1):
            pen.polyline([_edge(fr, g, 0.1 + 0.8 * j / 20.0, sd * off) for j in range(21)],
                         c, 110 * (1 - k3), 1.8 * S * (1 - k3) + 0.2)
    # 6: flare at the blade head (one end -> the other) or at both ends (from the centre)
    if t <= Ts + 3:
        fa = 1.0 if t <= Ts else 1 - (t - Ts) / 3.0
        k = L.ease_out3(min(t, Ts) / float(Ts))
        fr_ = _from(P)
        heads = ([1.0 - k] if fr_ == "end" else [0.5 - 0.5 * k, 0.5 + 0.5 * k] if fr_ == "centre" else [k])
        for hs in heads:
            hp = fr.w(*g.at(hs))
            ux, uy = fr.d(*g.tangent(hs))
            if (fr_ == "end") or (fr_ == "centre" and hs < 0.5):
                ux, uy = -ux, -uy
            pen.glow(hp[0], hp[1], 14 * S, c, 200 * fa)
            pen.glow(hp[0], hp[1], 6 * S, HOT, 255 * fa)
            L._star(pen, hp[0], hp[1], ux, uy, 16 * S, 6 * S, HOT, 230 * fa, 1.4 * S)
    # 7: sparks thrown off the blade as it passes
    n_sp = max(0, F.jround(16 * _num(P, "density", 1)))
    drag, grav = 0.88, 0.22 * S
    fr_ = _from(P)
    for i in range(n_sp):
        r = L.rng_for(inst.seed, i, 211)
        b = 1 + r() * (Ts - 1)
        life = 10 + r() * 10
        k = t - b
        if k < 0 or k >= life:
            continue
        kb = L.ease_out3(b / float(Ts))
        sb = 1.0 - kb if fr_ == "end" else (0.5 + (0.5 if i % 2 else -0.5) * kb) if fr_ == "centre" else kb
        p0 = fr.w(*g.at(sb))
        tx, ty = fr.d(*g.tangent(sb))
        if fr_ == "end" or (fr_ == "centre" and i % 2 == 0):
            tx, ty = -tx, -ty
        side = r.uniform(-0.7, 0.7)
        sp = r.uniform(2.5, 6.5) * S
        vx, vy = (tx - ty * side) * sp, (ty + tx * side) * sp
        fd = L.drag_dist(drag, k)
        x, y = p0[0] + vx * fd, p0[1] + vy * fd + 0.5 * grav * k * k
        dk = drag ** k
        cvx, cvy = vx * dk, vy * dk + grav * k
        q = k / life
        pen.line(x, y, x - cvx * 1.6, y - cvy * 1.6, L.mix(HOT, c, q), 255 * (1 - q), 1.6 * S)
    L._hit_marks(pen, inst, c, S, *cut_dir(inst))
