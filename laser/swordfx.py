"""
Sword techniques — the hand-drawn renderer behind the FX Kit "technique"
primitive (laser/fxkit.py).  Like the clash explosions (laser/clashfx.py)
every technique is painted procedurally — filled gradient crescents, glows,
sparks, shards, shock rings — instead of being assembled from simple layers.

Styles (params.style, fxkit.TECH_STYLES):

  rising_slash      vertical: a crescent blade of light rising from below the
                    feet to above the head in front of the fighter
  horizontal_sweep  a wide, flat sweep from behind the fighter to well in
                    front of it
  diagonal_slash    a cross-body cut from bottom-back to top-front
  crescent_wave     a travelling crescent of energy (Getsuga-style): bright
                    rim, dark core, flames licking off its back, embers
                    falling behind it, shock rings and a gouge along its path;
                    shatters into shards when it ends
  blade_extension   an energy blade that charges at the sword tip, shoots out
                    along the aim, holds with ripples and crackle running up
                    it, then retracts in a trail of sparkle dust
  forward_sweep     a flat sweep seen edge-on: from beside the fighter, out
                    round the front at full reach and back beside it
  combo_triple      overhead diagonal down, rising diagonal, wide finisher
  combo_cross       two diagonals crossing in front, an X flare where they meet
  combo_flurry      six quick cuts from every direction, scattered in front
  combo_launcher    low sweep at the feet, mid diagonal, high rising launcher
  combo_backhand    flat forehand round the front, flat backhand, overhead chop
  ki_barrage        rapid-fire ki blasts (laser/strikefx.py)
  impact_punch      a punch with a shockwave impact (laser/strikefx.py)

The slash family (CUTS) is one renderer: every cut of a combo is the same
hand-drawn slash with its own direction, bend, position, size and start.

Every slash swings fast (ease out) with a white-hot cutting edge, speed
lines, a flare at the blade head, sparks thrown along the swing and a
"space cut" line flashing along the chord when the swing ends.  Every hit
leaves an X-shaped slash flash with a ring on the target (inst.tq_hits).

Everything is a pure function of the instance (age, seed, position, the
spawn frame), so FX Studio's port (tools/fx/studio/swordfx.js) draws the
same pixels.  Colours: the effect's colour pair (palette by default) with a
white-hot core; the crescent wave's core is the second colour darkened.

Timeline (ticks): active_ticks() is the hit window (= inst.life); the
instance keeps drawing its afterglow until total_ticks().
"""

import math

from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF, QRadialGradient
from PyQt5.QtCore import Qt

from . import fxkit as F

HOT = (255, 255, 255)
BLACK = (0, 0, 0)
D = math.pi / 180.0
# Slash cut directions, local degrees (+x = forward, +y = down), facing right.
CUT_DEG = {"rising_slash": -90.0, "horizontal_sweep": 0.0, "diagonal_slash": -45.0}
# Every slash-family style is a list of cuts, each one the same hand-drawn
# slash laid out its own way:
#   (deg, bend, cx, cy, scale, span_k, squash, t0)
#   deg     the direction the blade travels (local, see CUT_DEG)
#   bend    1 = the crescent bulges to the right of that direction, -1 = left
#   cx, cy  where the cut is centred, in radii (+x forward, +y down)
#   scale   radius and thickness multiplier
#   span_k  span multiplier
#   squash  scale along the travel direction (< 1 flattens the cut into a
#           sweep seen edge-on, like a horizontal swing round the body)
#   t0      when the cut starts, in swing lengths (swing_ticks)
CUTS = {
    "rising_slash": ((-90.0, 1, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0),),
    "horizontal_sweep": ((0.0, 1, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0),),
    "diagonal_slash": ((-45.0, 1, 0.0, 0.0, 1.0, 1.0, 1.0, 0.0),),
    # beside the fighter, flat round the front at full reach, back beside it
    "forward_sweep": ((90.0, -1, 0.1, 0.0, 1.0, 1.0, 0.32, 0.0),),
    # overhead diagonal down, rising diagonal back up, wide flat finisher
    "combo_triple": ((40.0, -1, 0.1, -0.1, 1.0, 1.0, 1.0, 0.0),
                     (-40.0, 1, 0.15, 0.05, 1.0, 1.0, 1.0, 1.3),
                     (0.0, 1, 0.2, -0.1, 1.5, 0.6, 1.0, 2.6)),
    # two diagonals crossing in front of the fighter, then a burst at the X
    "combo_cross": ((45.0, -1, 0.45, 0.0, 1.0, 1.0, 1.0, 0.0),
                    (-45.0, 1, 0.45, 0.0, 1.0, 1.0, 1.0, 0.9)),
    # six quick cuts from every direction, scattered in front, a bigger last one
    "combo_flurry": ((30.0, -1, 0.55, -0.3, 0.7, 1.0, 1.0, 0.0),
                     (-150.0, -1, 0.75, 0.15, 0.65, 1.0, 1.0, 0.6),
                     (90.0, -1, 0.95, -0.05, 0.7, 0.9, 1.0, 1.2),
                     (-20.0, 1, 0.6, 0.3, 0.75, 1.0, 1.0, 1.8),
                     (160.0, 1, 0.85, -0.35, 0.6, 1.0, 1.0, 2.4),
                     (-60.0, 1, 0.7, 0.0, 0.9, 1.1, 1.0, 3.0)),
    # low sweep at the feet, mid diagonal, high rising launcher
    "combo_launcher": ((0.0, 1, 0.3, 0.35, 0.8, 0.8, 1.0, 0.0),
                       (-35.0, 1, 0.25, 0.05, 1.0, 1.0, 1.0, 1.2),
                       (-90.0, 1, 0.2, -0.25, 1.25, 1.2, 1.0, 2.4)),
    # flat forehand round the front, flat backhand back, overhead chop
    "combo_backhand": ((90.0, -1, 0.05, -0.05, 1.0, 1.1, 0.32, 0.0),
                       (-90.0, 1, 0.05, 0.1, 1.0, 1.1, 0.32, 1.2),
                       (90.0, -1, 0.45, 0.0, 1.1, 0.9, 1.0, 2.4)),
}
CROSS_LIFE = 18
SLASH_SLICES = 26
SPARK_LIFE = 20
WAVE_EMBER_LIFE = 30
WAVE_SHARD_LIFE = 26
WAVE_ARC_DEG = 95.0       # the crescent spans +-this round its centre: the tips curl back
WAVE_CX = -0.5            # crescent circle centre, x (times radius) behind the instance
EXT_CHARGE, EXT_EXTEND, EXT_RETRACT, EXT_DUST = 4, 5, 7, 16
HIT_MARK_LIFE = 16


# ---------------------------------------------------------------- maths
def _cl(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def ease_out3(u):
    u = _cl(u)
    return 1.0 - (1.0 - u) ** 3


def ease_in3(u):
    u = _cl(u)
    return u * u * u


def ease_inout3(u):
    u = _cl(u)
    return 4 * u * u * u if u < 0.5 else 1 - ((-2 * u + 2) ** 3) / 2


def mix(a, b, k):
    return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k)


def frac(x):
    return x - math.floor(x)


def rng_for(seed, a, b=0):
    return F.Rng((seed ^ F.imul(a + 1, 0x2C1B3C6D) ^ F.imul(b + 1, 0x297A2D39)) & F.M32)


def drag_dist(drag, k):
    """Distance factor after k ticks of v *= drag each tick."""
    return k if drag >= 0.9999 else (1 - drag ** k) / (1 - drag)


# ---------------------------------------------------------------- timeline
def _style(P):
    s = P.get("style")
    return s if s in F.TECH_STYLES else F.TECH_STYLES[0]


def _swing(P):
    return max(2, F.trunc(float(P.get("swing_ticks") or 6)))


def _fade(P):
    return max(6, F.jround(1.6 * _swing(P)))


def cut_starts(P):
    """Tick each cut of a slash-family style starts on."""
    Ts = _swing(P)
    return [F.jround(c[7] * Ts) for c in CUTS[_style(P)]]


def active_ticks(P):
    """Hit window (the instance's life)."""
    st = _style(P)
    if st == "crescent_wave":
        return max(1, F.trunc(float(P.get("hold_ticks") or 48)))
    if st == "blade_extension":
        return EXT_CHARGE + EXT_EXTEND + max(0, F.trunc(float(P.get("hold_ticks") or 0))) + EXT_RETRACT
    if st in strikefx.STYLES:
        return strikefx.active_ticks(P)
    return cut_starts(P)[-1] + _swing(P) + 2


def total_ticks(P):
    """Ticks the instance draws for (afterglow, sparks, shards included)."""
    st = _style(P)
    if st == "crescent_wave":
        return active_ticks(P) + WAVE_EMBER_LIFE
    if st == "blade_extension":
        return active_ticks(P) + EXT_DUST
    if st in strikefx.STYLES:
        return strikefx.total_ticks(P)
    return cut_starts(P)[-1] + _swing(P) + _fade(P) + SPARK_LIFE


# ---------------------------------------------------------------- frame
def on_spawn(inst, host):
    """Fix the technique's frame at spawn: origin, forward, mirror."""
    fx = inst.fx
    st = _style(fx["params"])
    if st in CUTS:
        ef = inst.facing
        f = F.turn_by([float(ef), 0.0], F.body_deg(fx, host, (inst.x, inst.y)))
    else:
        f = list(inst.dir)
    n = math.hypot(f[0], f[1]) or 1.0
    inst.tq_f = (f[0] / n, f[1] / n)
    inst.tq_m = (inst.facing if st in CUTS else (1 if inst.tq_f[0] >= 0 else -1))
    inst.tq_o = (inst.x, inst.y)
    inst.tq_hits = []
    inst.tq_cut = set()            # combo cuts that already landed
    inst.tq_path = [(inst.x, inst.y)]   # where the anchor was, per tick
    inst.tq_ki = {}                # ki shots stopped by a hit: index -> (tick, x, y)
    inst.tq_imp = []               # punch impacts: (tick, x, y)
    inst.life = active_ticks(fx["params"])


def on_tick(inst):
    """Each tick: remember where the anchor is (shots launch from there)."""
    inst.tq_path.append((inst.x, inst.y))


class Frame:
    """Local -> world: +x forward, +y down (mirrored with the facing)."""
    __slots__ = ("ox", "oy", "fx", "fy", "vx", "vy")

    def __init__(self, ox, oy, f, m):
        self.ox, self.oy = ox, oy
        self.fx, self.fy = f[0], f[1]
        self.vx, self.vy = -f[1] * m, f[0] * m

    def w(self, x, y):
        return (self.ox + x * self.fx + y * self.vx, self.oy + x * self.fy + y * self.vy)

    def d(self, x, y):
        return (x * self.fx + y * self.vx, x * self.fy + y * self.vy)


def _frame(inst):
    return Frame(inst.x, inst.y, inst.tq_f, inst.tq_m)


_VIVID = {}


def vivid(lut):
    """The palette's most vivid entry (brightest channel + half its
    saturation; first wins a tie) — a palette's slot 128 is its dark trough."""
    k = id(lut)
    if k not in _VIVID:
        best, bs = lut[0], -1.0
        for e in lut:
            sc = max(e) + 0.5 * (max(e) - min(e))
            if sc > bs:
                best, bs = e, sc
        _VIVID[k] = tuple(best)
    return _VIVID[k]


def _colours(inst, host):
    """(colour, bright, deep): palette = its vivid colour; else c1 / c2."""
    if inst.fx["color"]["mode"] == "palette":
        c = vivid(host.lut)
        c2 = c
    else:
        c1, c2 = F.color_pair(inst.fx, host.lut)
        c = tuple(c1)
    return c, mix(c, HOT, 0.45), mix(tuple(c2), BLACK, 0.84)


# ---------------------------------------------------------------- slash geometry
class SlashGeo:
    def __init__(self, inst, ps, ci=0):
        P = inst.fx["params"]
        self.st = _style(P)
        deg, bend, cx, cy, sc, sk, sq, _t0 = CUTS[self.st][ci]
        self.R = float(P["radius"]) * ps * sc
        self.W = float(P["thickness"]) * ps * sc
        self.h = float(P["span"]) * sk / 2.0
        self.b = bend
        a = deg * D
        self.d = (math.cos(a), math.sin(a))
        self.n = (-self.d[1] * bend, self.d[0] * bend)
        k = self.R * math.cos(self.h * D)
        self.O = (-self.n[0] * k, -self.n[1] * k)
        R0 = float(P["radius"]) * ps
        self.C = (cx * R0, cy * R0)
        self.sq = sq
        self.Ts, self.Tf = _swing(P), _fade(P)

    def phi(self, s):
        return F.rot(list(self.n), self.b * (self.h - 2 * self.h * s))

    def local(self, s, r):
        p = self.phi(s)
        x, y = self.O[0] + p[0] * r, self.O[1] + p[1] * r
        if self.sq != 1:
            a = (x * self.d[0] + y * self.d[1]) * (self.sq - 1)
            x, y = x + self.d[0] * a, y + self.d[1] * a
        return (self.C[0] + x, self.C[1] + y)

    def state(self, t):
        """(tail, head, global alpha, width factor)."""
        Ts, Tf = self.Ts, self.Tf
        head = ease_out3(t / Ts)
        if t <= Ts:
            return max(0.0, head - 0.8), head, 1.0, 1.0
        k = _cl((t - Ts) / Tf)
        return 0.2 + 0.8 * ease_inout3(k), 1.0, 1.0 - 0.5 * k, 1.0 - 0.5 * k

    def width(self, u, wf):
        return self.W * wf * (math.sin(math.pi * (u ** 1.5)) ** 0.7)

    def slices(self, t):
        """[(s, u, w)] along the visible blade, tail -> head."""
        tail, head, _ga, wf = self.state(t)
        if head - tail < 0.004:
            return []
        out = []
        for i in range(SLASH_SLICES + 1):
            u = i / SLASH_SLICES
            out.append((tail + (head - tail) * u, u, self.width(u, wf)))
        return out


def _cut_hit(g, fr, t, tx, ty, hr):
    sl = g.slices(t)
    # A flat (squashed) cut is a swing round the body seen edge-on: it hits
    # everything between the fighter and the blade, not just the blade line.
    hub = fr.w(*g.local(0.5, 0.0)) if g.sq != 1 else None
    for i in range(1, len(sl)):
        s0, u0, w0 = sl[i - 1]
        s1, u1, w1 = sl[i]
        if u1 < 0.15:
            continue
        a = fr.w(*g.local(s0, g.R - 0.2 * w0))
        b = fr.w(*g.local(s1, g.R - 0.2 * w1))
        if F.seg_dist(tx, ty, a[0], a[1], b[0], b[1]) <= hr + max(w0, w1) * 0.5:
            return True
        if hub is not None and F.seg_dist(tx, ty, hub[0], hub[1], b[0], b[1]) <= hr:
            return True
    return False


def _live_cuts(inst):
    """[(cut index, its own tick)] for the cuts inside their hit window."""
    P = inst.fx["params"]
    win = _swing(P) + 2
    return [(i, inst.age - s) for i, s in enumerate(cut_starts(P)) if 0 <= inst.age - s < win]


def _slash_hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    fr = _frame(inst)
    combo = len(CUTS[_style(inst.fx["params"])]) > 1
    for (ci, t) in _live_cuts(inst):
        if combo and ci in inst.tq_cut:
            continue   # each combo cut lands once
        if _cut_hit(SlashGeo(inst, ps, ci), fr, t, tx, ty, hr):
            return True
    return False


def _slash_on_hit(inst):
    for (ci, _t) in _live_cuts(inst):
        inst.tq_cut.add(ci)


def _slash_body(inst, ps):
    fr = _frame(inst)
    live = _live_cuts(inst)
    if not live:
        return None
    ci, t = live[-1]
    g = SlashGeo(inst, ps, ci)
    sl = g.slices(t)
    if not sl:
        return None
    pts = [fr.w(*g.local(sl[j][0], g.R - 0.2 * sl[j][2])) for j in range(0, len(sl), 4)]
    return pts, g.W * 0.5


# ---------------------------------------------------------------- wave geometry
class WaveGeo:
    def __init__(self, inst, ps):
        P = inst.fx["params"]
        self.R = float(P["radius"]) * ps
        self.W = float(P["thickness"]) * ps
        self.L = active_ticks(P)
        self.S = ps

    def grow(self, t):
        g = 0.35 + 0.65 * ease_out3(t / 5.0)
        if t >= self.L:
            g *= 1 + 0.25 * _cl((t - self.L) / 8.0)
        return g

    def pts(self, t, g, M=20):
        """[(v, outer(x, y), dir(x, y), w)] along the crescent, top -> bottom."""
        out = []
        cx = WAVE_CX * self.R
        for j in range(M + 1):
            v = -1 + 2.0 * j / M
            a = v * WAVE_ARC_DEG * D
            dx, dy = math.cos(a), math.sin(a)
            o = ((cx + self.R * dx) * g, self.R * dy * g)
            w = self.W * g * ((1 - abs(v) ** 1.8) ** 0.85)
            out.append((v, o, (dx, dy), w))
        return out


def _flame(v, t, ph):
    return 0.5 + 0.5 * math.sin(v * 9 + t * 0.9 + ph) * math.sin(v * 4.3 - t * 0.55 + ph * 0.5)


def _wave_hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    g, fr = WaveGeo(inst, ps), _frame(inst)
    k = g.grow(inst.age)
    pts = g.pts(inst.age, k, 8)
    prev = None
    for (_v, o, dr, w) in pts:
        c = fr.w(o[0] - dr[0] * w * 0.5, o[1] - dr[1] * w * 0.5)
        if prev is not None and F.seg_dist(tx, ty, prev[0], prev[1], c[0], c[1]) <= hr + g.W * k * 0.5:
            return True
        prev = c
    return False


def _wave_body(inst, ps):
    if inst.age >= inst.life:
        return None
    g, fr = WaveGeo(inst, ps), _frame(inst)
    k = g.grow(inst.age)
    return [fr.w(o[0] - dr[0] * w * 0.5, o[1] - dr[1] * w * 0.5) for (_v, o, dr, w) in g.pts(inst.age, k, 6)], g.W * k * 0.5


# ---------------------------------------------------------------- extension geometry
def _ext_len(P, t, L):
    Th = max(0, F.trunc(float(P.get("hold_ticks") or 0)))
    t0 = EXT_CHARGE
    t1 = t0 + EXT_EXTEND
    t2 = t1 + Th
    t3 = t2 + EXT_RETRACT
    if t < t0:
        return 0.0
    if t < t1:
        return L * ease_out3((t - t0) / EXT_EXTEND)
    if t < t2:
        return L
    if t < t3:
        return L * (1 - ease_in3((t - t2) / EXT_RETRACT))
    return 0.0


def _ext_hw(u, W):
    hw = W * (0.75 + 0.25 * math.sin(math.pi * u)) if u < 0.86 else W * (1 - (u - 0.86) / 0.14) * (0.75 + 0.25 * math.sin(math.pi * 0.86))
    if u < 0.05:
        hw *= 1 + 0.6 * (1 - u / 0.05)
    return max(0.0, hw)


def _ext_hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    P = inst.fx["params"]
    l = _ext_len(P, inst.age, float(P["length"]) * ps)
    if l <= 2:
        return False
    fr = _frame(inst)
    b = fr.w(l, 0)
    return F.seg_dist(tx, ty, inst.x, inst.y, b[0], b[1]) <= hr + float(P["thickness"]) * ps * 0.9


def _ext_body(inst, ps):
    P = inst.fx["params"]
    l = _ext_len(P, inst.age, float(P["length"]) * ps)
    if l <= 2 or inst.age >= inst.life:
        return None
    fr = _frame(inst)
    return [(inst.x, inst.y), fr.w(l, 0)], float(P["thickness"]) * ps


# ---------------------------------------------------------------- public: hit / body
def hit(inst, tx, ty, hr, ps):
    st = _style(inst.fx["params"])
    if st == "crescent_wave":
        return _wave_hit(inst, tx, ty, hr, ps)
    if st == "blade_extension":
        return _ext_hit(inst, tx, ty, hr, ps)
    if st in strikefx.STYLES:
        return strikefx.hit(inst, tx, ty, hr, ps)
    return _slash_hit(inst, tx, ty, hr, ps)


def body(inst, ps):
    """(points, half width) a clash treats as a cutting blade, or None."""
    st = _style(inst.fx["params"])
    if st == "crescent_wave":
        return _wave_body(inst, ps)
    if st == "blade_extension":
        return _ext_body(inst, ps)
    if st in strikefx.STYLES:
        return strikefx.body(inst, ps)
    if inst.age >= inst.life:
        return None
    return _slash_body(inst, ps)


def on_hit(inst, x, y, ps=1.0):
    st = _style(inst.fx["params"])
    if st in strikefx.STYLES:
        strikefx.on_hit(inst, x, y, ps)
    elif st in CUTS:
        _slash_on_hit(inst)
    inst.tq_hits.append((float(x), float(y), inst.age))


# ================================================================ drawing
class Pen:
    """The few primitives every technique is painted with (world coords).
    tools/fx/studio/swordfx.js implements the same set on a canvas."""

    def __init__(self, p):
        self.p = p

    def add(self, on):
        self.p.setCompositionMode(QPainter.CompositionMode_Plus if on else QPainter.CompositionMode_SourceOver)

    @staticmethod
    def _q(c, a):
        return QColor(int(_cl(c[0] / 255.0) * 255), int(_cl(c[1] / 255.0) * 255), int(_cl(c[2] / 255.0) * 255),
                      int(_cl(a / 255.0) * 255))

    def poly(self, pts, c, a):
        if a <= 1 or len(pts) < 3:
            return
        self.p.setPen(Qt.NoPen)
        self.p.setBrush(self._q(c, a))
        self.p.drawPolygon(QPolygonF([QPointF(x, y) for (x, y) in pts]))

    def glow(self, x, y, r, c, a, mid=0.35):
        if r <= 0.5 or a <= 1:
            return
        g = QRadialGradient(x, y, r)
        g.setColorAt(0.0, self._q(c, a))
        g.setColorAt(mid, self._q(c, a * 0.45))
        g.setColorAt(1.0, self._q(c, 0))
        self.p.setPen(Qt.NoPen)
        self.p.setBrush(QBrush(g))
        self.p.drawEllipse(QPointF(x, y), r, r)

    def line(self, x0, y0, x1, y1, c, a, w):
        if a <= 1 or w <= 0.05:
            return
        pen = QPen(self._q(c, a), w)
        pen.setCapStyle(Qt.RoundCap)
        self.p.setPen(pen)
        self.p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

    def polyline(self, pts, c, a, w):
        if a <= 1 or w <= 0.05 or len(pts) < 2:
            return
        pen = QPen(self._q(c, a), w)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.p.setPen(pen)
        self.p.setBrush(Qt.NoBrush)
        self.p.drawPolyline(QPolygonF([QPointF(x, y) for (x, y) in pts]))

    def diamond(self, x0, y0, x1, y1, hw, c, a):
        if a <= 1 or hw <= 0.05:
            return
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / L * hw, dx / L * hw
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        self.poly([(x0, y0), (mx + nx, my + ny), (x1, y1), (mx - nx, my - ny)], c, a)

    def ring(self, x, y, rx, ry, ang, c, a, w):
        """An ellipse outline, rx along the direction ang (radians)."""
        if a <= 1 or w <= 0.05 or rx <= 0.5 or ry <= 0.5:
            return
        ca, sa = math.cos(ang), math.sin(ang)
        pts = []
        for i in range(25):
            t = i / 24.0 * math.pi * 2
            px, py = math.cos(t) * rx, math.sin(t) * ry
            pts.append((x + px * ca - py * sa, y + px * sa + py * ca))
        self.polyline(pts, c, a, w)


def _star(pen, x, y, ux, uy, long_r, short_r, c, a, w):
    pen.line(x - ux * long_r, y - uy * long_r, x + ux * long_r, y + uy * long_r, c, a, w)
    pen.line(x + uy * short_r, y - ux * short_r, x - uy * short_r, y + ux * short_r, c, a, w)


def _hit_marks(pen, inst, c, ps, dx, dy, dirf=None):
    """X slash flash + ring on every hit; dirf(tick) -> (dx, dy) when the cut
    direction changes over the technique (combos)."""
    t = inst.age
    for (x, y, b) in inst.tq_hits:
        k = t - b
        if k < 0 or k >= HIT_MARK_LIFE:
            continue
        if dirf is not None:
            dx, dy = dirf(b)
        f = 1 - k / float(HIT_MARK_LIFE)
        e = ease_out3(k / 4.0)
        L = (18 + 10 * e) * ps
        for (ux, uy) in ((dx, dy), tuple(F.rot([dx, dy], 70))):
            pen.diamond(x - ux * L, y - uy * L, x + ux * L, y + uy * L, 3.2 * ps * f + 0.3, c, 220 * f)
            pen.diamond(x - ux * L * 0.9, y - uy * L * 0.9, x + ux * L * 0.9, y + uy * L * 0.9, 1.1 * ps * f + 0.2, HOT, 255 * f)
        pen.ring(x, y, (4 + 20 * ease_out3(k / float(HIT_MARK_LIFE))) * ps, (4 + 20 * ease_out3(k / float(HIT_MARK_LIFE))) * ps,
                 0.0, c, 200 * f, 2.0 * ps * f)
        pen.glow(x, y, 14 * ps * f, HOT, 230 * f)


# ---------------------------------------------------------------- slash
def _draw_cut(pen, inst, ps, g, fr, t, ci, c, bright):
    """One cut of a slash-family style at its own tick t."""
    P = inst.fx["params"]
    tail, head, ga, wf = g.state(t)
    R, Ts = g.R, g.Ts
    sl = g.slices(t)

    def W(s, r):
        return fr.w(*g.local(s, r))

    # 0: bloom behind the blade while it is fresh
    if sl and t <= Ts + 6:
        bf = ga * (1.0 if t <= Ts else 1 - (t - Ts) / 6.0)
        bm = W(tail + (head - tail) * 0.7, R)
        pen.glow(bm[0], bm[1], min(0.9 * R, 36 * ps), c, 80 * bf, 0.4)
    # 1-3: haze, blade body, white-hot cutting edge (slices, tail fades)
    for i in range(1, len(sl)):
        s0, u0, w0 = sl[i - 1]
        s1, u1, w1 = sl[i]
        a = ga * (u1 ** 0.9)
        if a <= 0.01:
            continue
        hz = 5.0 * ps
        pen.poly([W(s0, R + 0.3 * w0 + hz), W(s1, R + 0.3 * w1 + hz), W(s1, R - 0.7 * w1 - hz), W(s0, R - 0.7 * w0 - hz)],
                 c, 70 * a)
        pen.poly([W(s0, R + 0.3 * w0), W(s1, R + 0.3 * w1), W(s1, R - 0.7 * w1), W(s0, R - 0.7 * w0)],
                 mix(c, bright, u1 * u1), 235 * a)
        e0, e1 = max(1.2 * ps, 0.3 * w0), max(1.2 * ps, 0.3 * w1)
        pen.poly([W(s0, R + 0.3 * w0), W(s1, R + 0.3 * w1), W(s1, R + 0.3 * w1 - e1), W(s0, R + 0.3 * w0 - e0)],
                 HOT, 255 * (a ** 1.2))
    # 4: speed lines outside the blade while it swings
    if t <= Ts + 4 and head - tail > 0.05:
        sf = 1.0 if t <= Ts else 1 - (t - Ts) / 4.0
        for k in range(3):
            r = R + (5 + 4 * k) * ps
            s_a = max(tail, head - 0.45 + 0.1 * k)
            s_b = head - 0.05
            if s_b - s_a < 0.02:
                continue
            pen.polyline([W(s_a + (s_b - s_a) * j / 9.0, r) for j in range(10)], c, 120 * sf * (1 - k * 0.25), 1.1 * ps)
    # 5: the cut left hanging in the air — the whole path flashes as a thin
    # bright line as the swing ends, and a pressure wave rolls off it
    k2 = (t - (Ts - 1)) / 10.0
    if 0 <= k2 < 1:
        path = [W(j / 24.0, R + 0.1 * g.W) for j in range(25)]
        pen.polyline(path, c, 160 * (1 - k2), 3.5 * ps)
        pen.polyline(path, HOT, 255 * (1 - k2) ** 2, 1.2 * ps)
    k3 = (t - Ts) / 12.0
    if 0 <= k3 < 1:
        rr = R * (1 + 0.35 * ease_out3(k3))
        pen.polyline([W(0.1 + 0.8 * j / 20.0, rr) for j in range(21)], c, 130 * (1 - k3), 2.0 * ps * (1 - k3) + 0.2)
    # 6: flare at the blade head
    if t <= Ts + 3:
        fa = 1.0 if t <= Ts else 1 - (t - Ts) / 3.0
        hp = W(head, R)
        pp = W(max(0.0, head - 0.03), R)
        ux, uy = hp[0] - pp[0], hp[1] - pp[1]
        n = math.hypot(ux, uy) or 1.0
        ux, uy = ux / n, uy / n
        pen.glow(hp[0], hp[1], 14 * ps, c, 200 * fa)
        pen.glow(hp[0], hp[1], 6 * ps, HOT, 255 * fa)
        _star(pen, hp[0], hp[1], ux, uy, 16 * ps, 6 * ps, HOT, 230 * fa, 1.4 * ps)
    # 7: sparks thrown along the swing
    n_sp = max(0, F.jround(16 * float(P.get("density") or 1)))
    drag, grav = 0.88, 0.22 * ps
    for i in range(n_sp):
        r = rng_for(inst.seed, i, 7 + 100 * ci)
        b = 1 + r() * (Ts - 1)
        life = 10 + r() * 10
        k = t - b
        if k < 0 or k >= life:
            continue
        sb = ease_out3(b / Ts)
        p0 = W(sb, R + 0.2 * g.W)
        p1 = W(min(1.0, sb + 0.02), R + 0.2 * g.W)
        tx, ty = p1[0] - p0[0], p1[1] - p0[1]
        n = math.hypot(tx, ty) or 1.0
        tx, ty = tx / n, ty / n
        rx, ry = fr.d(*g.phi(sb))
        sp = r.uniform(2.5, 6.5) * ps
        out = r.uniform(0.1, 0.7)
        vx, vy = (tx + rx * out) * sp, (ty + ry * out) * sp
        fd = drag_dist(drag, k)
        x, y = p0[0] + vx * fd, p0[1] + vy * fd + 0.5 * grav * k * k
        dk = drag ** k
        cvx, cvy = vx * dk, vy * dk + grav * k
        q = k / life
        pen.line(x, y, x - cvx * 1.6, y - cvy * 1.6, mix(HOT, c, q), 255 * (1 - q), 1.6 * ps)


def _draw_cross(pen, inst, ps, fr, c, starts):
    """combo_cross: the X flares where the two cuts cross once the second ends."""
    a = inst.age - (starts[1] + _swing(inst.fx["params"]))
    if a < 0 or a >= CROSS_LIFE:
        return
    ga, gb = SlashGeo(inst, ps, 0), SlashGeo(inst, ps, 1)
    pa, pb = ga.local(0.5, ga.R), gb.local(0.5, gb.R)
    x, y = fr.w((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
    q = a / float(CROSS_LIFE)
    e = ease_out3(a / 6.0)
    L = (0.9 + 0.5 * e) * ga.R
    for gg in (ga, gb):
        ux, uy = fr.d(*gg.d)
        pen.diamond(x - ux * L, y - uy * L, x + ux * L, y + uy * L, 6 * ps * (1 - q) + 0.3, c, 230 * (1 - q))
        pen.diamond(x - ux * L * 0.92, y - uy * L * 0.92, x + ux * L * 0.92, y + uy * L * 0.92, 2 * ps * (1 - q) + 0.2,
                    HOT, 255 * (1 - q))
    pen.glow(x, y, (20 + 26 * e) * ps * (1 - q), HOT, 240 * (1 - q))
    pen.glow(x, y, (34 + 30 * e) * ps, c, 150 * (1 - q), 0.4)
    rr = 8 * ps + 0.9 * ga.R * ease_out3(q)
    pen.ring(x, y, rr, rr, 0.0, c, 200 * (1 - q), 2.6 * ps * (1 - q) + 0.2)
    for i in range(10):
        r = rng_for(inst.seed, i, 31)
        life = 10 + 8 * r()
        if a >= life:
            continue
        an = r.uniform(0, math.pi * 2)
        sp = r.uniform(3, 8) * ps
        fd = drag_dist(0.86, a)
        sx, sy = x + math.cos(an) * sp * fd, y + math.sin(an) * sp * fd
        dk = 0.86 ** a
        qq = a / life
        pen.line(sx, sy, sx - math.cos(an) * sp * dk * 1.8, sy - math.sin(an) * sp * dk * 1.8, mix(HOT, c, qq),
                 255 * (1 - qq), 1.5 * ps)


def _draw_slash(pen, inst, host, ps):
    P = inst.fx["params"]
    st = _style(P)
    fr = _frame(inst)
    c, bright, _deep = _colours(inst, host)
    pen.add(True)
    starts = cut_starts(P)
    end = _swing(P) + _fade(P) + SPARK_LIFE
    geos = [SlashGeo(inst, ps, ci) for ci in range(len(starts))]
    for ci, s in enumerate(starts):
        t = inst.age - s
        if 0 <= t < end:
            _draw_cut(pen, inst, ps, geos[ci], fr, t, ci, c, bright)
    if st == "combo_cross":
        _draw_cross(pen, inst, ps, fr, c, starts)

    def dirf(b):
        ci = 0
        for i, s in enumerate(starts):
            if s <= b:
                ci = i
        return fr.d(*geos[ci].d)

    _hit_marks(pen, inst, c, ps, *fr.d(*geos[0].d), dirf=dirf if len(starts) > 1 else None)


# ---------------------------------------------------------------- crescent wave
def _wave_shape(fr, g, k, t, ox=0.0):
    pts = g.pts(t, k)
    outer = [fr.w(o[0] + ox, o[1]) for (_v, o, dr, w) in pts]
    inner = [fr.w(o[0] - dr[0] * w + ox, o[1] - dr[1] * w) for (_v, o, dr, w) in pts]
    return pts, outer, inner


def _draw_wave(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    g = WaveGeo(inst, ps)
    fr = _frame(inst)
    c, bright, deep = _colours(inst, host)
    L = g.L
    k = g.grow(t)
    ph = (inst.seed % 1000) * 0.01
    fade = 1.0 if t < L else 1 - _cl((t - L) / 8.0)
    fx_, fy_ = inst.tq_f
    o0 = inst.tq_o
    spd = math.hypot(inst.x - o0[0], inst.y - o0[1]) / max(1, min(t, L))
    R, S = g.R, ps
    pen.add(True)

    def pos_at(b):
        b = min(b, L)
        return (o0[0] + fx_ * spd * b, o0[1] + fy_ * spd * b)

    # 1: gouge along the path, brighter toward the wave
    if t > 1:
        gf = 1.0 if t < L else 1 - _cl((t - L) / 16.0)
        back = fr.w(-0.35 * R * k, 0)
        n = 12
        for i in range(n):
            a0, a1 = i / float(n), (i + 1) / float(n)
            x0, y0 = o0[0] + (back[0] - o0[0]) * a0, o0[1] + (back[1] - o0[1]) * a0
            x1, y1 = o0[0] + (back[0] - o0[0]) * a1, o0[1] + (back[1] - o0[1]) * a1
            al = gf * (a1 ** 1.5)
            pen.line(x0, y0, x1, y1, c, 90 * al, 3.0 * S)
            pen.line(x0, y0, x1, y1, HOT, 120 * al, 1.0 * S)
    # 2: shock rings shed every 6 ticks
    for b in range(0, min(t, L) + 1, 8):
        a = t - b
        if a >= 14:
            continue
        e = ease_out3(a / 14.0)
        q = 1 - a / 14.0
        cx, cy = pos_at(b)
        cx, cy = cx - fx_ * 0.2 * R, cy - fy_ * 0.2 * R
        pen.ring(cx, cy, (0.25 + 0.35 * e) * R * k, (0.9 + 0.6 * e) * R * k, math.atan2(fy_, fx_), c, 90 * q, 1.4 * S * q + 0.2)
    # 3: launch burst at the origin
    if t < 14:
        q = t / 14.0
        e = ease_out3(q)
        pen.glow(o0[0], o0[1], (14 + 30 * e) * S, c, 160 * (1 - q))
        vx, vy = fr.vx, fr.vy
        pen.diamond(o0[0] - vx * 45 * S, o0[1] - vy * 45 * S, o0[0] + vx * 45 * S, o0[1] + vy * 45 * S,
                    4 * S * (1 - q) + 0.2, c, 220 * (1 - q))
        pen.diamond(o0[0] - vx * 40 * S, o0[1] - vy * 40 * S, o0[0] + vx * 40 * S, o0[1] + vy * 40 * S,
                    1.3 * S * (1 - q) + 0.2, HOT, 255 * (1 - q))
        pen.ring(o0[0], o0[1], (6 + 26 * e) * S, (6 + 26 * e) * S, 0.0, c, 180 * (1 - q), 2.2 * S * (1 - q) + 0.2)
    if fade > 0:
        # 4: afterimages trailing the wave
        for j in range(1, 4):
            pts, outer, inner = _wave_shape(fr, g, k, t, -spd * 2.2 * j)
            pen.poly(outer + inner[::-1], c, 55.0 / j * fade)
        pts, outer, inner = _wave_shape(fr, g, k, t)
        # 5: aura round the whole crescent
        aura_o = [fr.w(o[0] + dr[0] * 6 * S * k, o[1] + dr[1] * 6 * S * k) for (_v, o, dr, w) in pts]
        aura_i = [fr.w(o[0] - dr[0] * (w + 4 * S * k), o[1] - dr[1] * (w + 4 * S * k)) for (_v, o, dr, w) in pts]
        pen.poly(aura_o + aura_i[::-1], c, 80 * fade)
        # 6: flames streaming back off the back edge, spreading outward
        tongues = []
        for i in range(11):
            v = -0.9 + 1.8 * i / 10.0
            a = v * WAVE_ARC_DEG * D
            dx, dy = math.cos(a), math.sin(a)
            ww = g.W * k * ((1 - abs(v) ** 1.8) ** 0.85)
            bx, by = (WAVE_CX * R + R * dx) * k - dx * ww * 0.8, R * dy * k - dy * ww * 0.8
            r = rng_for(inst.seed, i, 17)
            ln = (18 + 30 * _flame(v, t, ph + i) * r.uniform(0.6, 1.4)) * S * k * (1 - 0.45 * abs(v))
            ux, uy = -1.0, 0.6 * v + 0.25 * math.sin(t * 0.7 + i * 1.7)
            n = math.hypot(ux, uy)
            tongues.append((fr.w(bx, by), fr.w(bx + ux / n * ln, by + uy / n * ln), ln, r.uniform(3.4, 5.2) * S * k))
        back = fr.w(WAVE_CX * R * k - 0.2 * R * k, 0)
        pen.glow(back[0], back[1], 1.1 * R * k, c, 70 * fade, 0.4)
        for (b0, b1, ln, wd) in tongues:
            pen.diamond(b0[0], b0[1], b1[0], b1[1], wd, c, 170 * fade)
        # 7: bright rim (the whole body; the dark core is cut out of it)
        pen.poly(outer + inner[::-1], mix(c, HOT, 0.25), 235 * fade)
        # 8: dark core and dark flame tongues (painted over the light),
        # outlined in the colour
        pen.add(False)
        for (b0, b1, ln, wd) in tongues:
            m0 = (b0[0] + (b1[0] - b0[0]) * 0.08, b0[1] + (b1[1] - b0[1]) * 0.08)
            m1 = (b0[0] + (b1[0] - b0[0]) * 0.75, b0[1] + (b1[1] - b0[1]) * 0.75)
            pen.diamond(m0[0], m0[1], m1[0], m1[1], wd * 0.5, deep, 220 * fade)
        core_o = [fr.w(o[0] - dr[0] * w * 0.3, o[1] - dr[1] * w * 0.3) for (_v, o, dr, w) in pts]
        core_i = [fr.w(o[0] - dr[0] * w * (0.88 + 0.2 * _flame(v, t, ph)), o[1] - dr[1] * w * (0.88 + 0.2 * _flame(v, t, ph)))
                  for (v, o, dr, w) in pts]
        pen.poly(core_o[2:-2] + core_i[2:-2][::-1], deep, 240 * fade)
        pen.add(True)
        pen.polyline(core_o[2:-2], c, 120 * fade, 1.0 * S)
        # 9: white-hot leading edge and its glow
        front = [outer[j] for j in range(len(pts)) if abs(pts[j][0]) < 0.85]
        pen.polyline(front, HOT, 255 * fade, 2.2 * S * k)
        mid = outer[len(outer) // 2]
        pen.glow(mid[0], mid[1], 20 * S * k, c, 130 * fade)
    # 10: embers falling behind it
    dens = float(P.get("density") or 1)
    per = max(0, F.jround(3 * dens))
    for b in range(max(0, t - WAVE_EMBER_LIFE), min(t, L)):
        for j in range(per):
            r = rng_for(inst.seed, b, j)
            life = 14 + 16 * r()
            a = t - b
            if a >= life:
                continue
            v = r.uniform(-0.9, 0.9)
            an = v * WAVE_ARC_DEG * D
            ww = g.W * ((1 - abs(v) ** 1.8) ** 0.85)
            lx, ly = WAVE_CX * R + R * math.cos(an) - math.cos(an) * ww, R * math.sin(an) - math.sin(an) * ww
            bx, by = pos_at(b)
            dx, dy = fr.d(lx, ly)
            sx, sy = bx + dx, by + dy
            bv = r.uniform(0.5, 2.5) * S
            pv = r.uniform(-1.2, 1.2) * S
            vx, vy = -fx_ * bv + fr.vx * pv, -fy_ * bv + fr.vy * pv
            drag, grav = 0.93, 0.18 * S
            fd = drag_dist(drag, a)
            x, y = sx + vx * fd, sy + vy * fd + 0.5 * grav * a * a
            q = a / life
            col = mix(HOT, c, min(1.0, q * 2)) if q < 0.5 else mix(c, deep, (q - 0.5) * 2)
            pen.diamond(x - 1.8 * S, y, x + 1.8 * S, y, 1.4 * S * (1 - q * 0.5), col, 230 * (1 - q))
    # 11: shatter into shards when it ends
    if t >= L:
        a = t - L
        q = a / float(WAVE_SHARD_LIFE)
        if q < 1:
            pen.glow(inst.x, inst.y, 40 * S * (1 - min(1.0, a / 10.0)), HOT, 200 * (1 - min(1.0, a / 10.0)))
            for i in range(10):
                r = rng_for(inst.seed, i, 91)
                v = r.uniform(-0.9, 0.9)
                an = v * WAVE_ARC_DEG * D
                lx, ly = (WAVE_CX * R + R * math.cos(an)), R * math.sin(an)
                px, py = fr.w(lx, ly)
                dx, dy = fr.d(math.cos(an) + r.uniform(-0.4, 0.4), math.sin(an) + r.uniform(-0.4, 0.4))
                sp = r.uniform(2.0, 6.0) * S
                fd = drag_dist(0.93, a)
                x, y = px + dx * sp * fd, py + dy * sp * fd + 0.05 * S * a * a
                rot = r.uniform(0, math.pi * 2) + r.uniform(-0.25, 0.25) * a
                ln = r.uniform(7, 12) * S
                ux, uy = math.cos(rot) * ln, math.sin(rot) * ln
                pen.diamond(x - ux, y - uy, x + ux, y + uy, 2.4 * S * (1 - q) + 0.2, c, 230 * (1 - q))
                pen.diamond(x - ux * 0.7, y - uy * 0.7, x + ux * 0.7, y + uy * 0.7, 0.8 * S * (1 - q) + 0.1, HOT, 255 * (1 - q))
    _hit_marks(pen, inst, c, ps, fx_, fy_)


# ---------------------------------------------------------------- blade extension
def _draw_extension(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    fr = _frame(inst)
    c, bright, _deep = _colours(inst, host)
    S = ps
    Lmax = float(P["length"]) * ps
    W = float(P["thickness"]) * ps
    Th = max(0, F.trunc(float(P.get("hold_ticks") or 0)))
    l = _ext_len(P, t, Lmax)
    ox, oy = inst.x, inst.y
    fx_, fy_ = inst.tq_f
    pen.add(True)
    # 1: charge — light converging on the sword tip
    if t < EXT_CHARGE + 2:
        cp = _cl(t / float(EXT_CHARGE))
        fa = 1.0 if t < EXT_CHARGE else 1 - (t - EXT_CHARGE) / 2.0
        for i in range(8):
            r = rng_for(inst.seed, i, 3)
            an = (i * 45 + r.uniform(-15, 15)) * D
            r0 = 26 * S * (1 - cp) + 4 * S
            r1 = r0 * 0.4
            pen.line(ox + math.cos(an) * r0, oy + math.sin(an) * r0, ox + math.cos(an) * r1, oy + math.sin(an) * r1,
                     mix(c, HOT, cp), 220 * fa, 1.3 * S)
        pen.glow(ox, oy, (4 + 10 * cp) * S, HOT, 230 * fa)
    # 2: guard glow at the base
    if l > 0 or t < EXT_CHARGE:
        pen.glow(ox, oy, 10 * S, c, 170)
        pen.glow(ox, oy, 4 * S, HOT, 255)
    if l > 1:
        n = 24
        us = [j / float(n) for j in range(n + 1)]

        def edge(m):
            top = [fr.w(u * l, -_ext_hw(u, W) * m) for u in us]
            bot = [fr.w(u * l, _ext_hw(u, W) * m) for u in us]
            return top + bot[::-1]

        shim = 0.85 + 0.15 * math.sin(t * 1.3)
        # 3: layered blade — wide glow, mid glow, body, white core
        pen.poly(edge(2.8), c, 40)
        pen.poly(edge(1.7), c, 100 * shim)
        for j in range(n):
            u0, u1 = us[j], us[j + 1]
            h0, h1 = _ext_hw(u0, W), _ext_hw(u1, W)
            pen.poly([fr.w(u0 * l, -h0), fr.w(u1 * l, -h1), fr.w(u1 * l, h1), fr.w(u0 * l, h0)],
                     mix(c, bright, u1), 220 * (0.85 + 0.15 * math.sin(t * 1.3 + u1 * 12)))
        pen.poly(edge(0.32), HOT, 255)
        # 4: energy ripples running up the blade
        for kk in range(3):
            phs = frac(t * 0.09 + kk / 3.0)
            x = phs * l
            hw = _ext_hw(phs, W) * 2.4
            a0, a1 = fr.w(x, -hw), fr.w(x, hw)
            pen.diamond(a0[0], a0[1], a1[0], a1[1], 2.5 * S, HOT, 200 * (1 - phs) * (l / Lmax))
        # 5: crackle along the edges (re-rolled every 2 ticks)
        if l > 0.3 * Lmax:
            for kk in range(4):
                r = rng_for(inst.seed ^ F.imul((t // 2) + 1, 0x45D9F3B), kk, 5)
                side = 1 if kk % 2 else -1
                u0 = r.uniform(0.1, 0.8)
                du = r.uniform(0.12, 0.25)
                pts = []
                for j in range(5):
                    u = min(1.0, u0 + du * j / 4.0)
                    off = side * _ext_hw(u, W) * r.uniform(1.1, 1.5) + r.uniform(-2.5, 2.5) * S
                    pts.append(fr.w(u * l, off))
                pen.polyline(pts, c, 200, 1.4 * S)
                pen.polyline(pts, HOT, 200, 0.6 * S)
        # 6: spear point
        tip = fr.w(l, 0)
        pen.glow(tip[0], tip[1], 22 * S, c, 90)
        pen.glow(tip[0], tip[1], 10 * S, HOT, 200)
        _star(pen, tip[0], tip[1], fx_, fy_, 20 * S, 8 * S, HOT, 230, 1.4 * S)
    # 7: shock cone + burst the moment it reaches full length
    tE = EXT_CHARGE + EXT_EXTEND
    a = t - tE
    if 0 <= a < 12:
        q = a / 12.0
        e = ease_out3(q)
        tip = fr.w(Lmax, 0)
        pen.ring(tip[0], tip[1], (4 + 10 * e) * S, (6 + 26 * e) * S, math.atan2(fy_, fx_), c, 220 * (1 - q), 2.2 * S * (1 - q) + 0.2)
        pen.glow(tip[0], tip[1], 26 * S * (1 - q), HOT, 200 * (1 - q))
        for i in range(8):
            r = rng_for(inst.seed, i, 11)
            life = 10 + 6 * r()
            if a >= life:
                continue
            an = math.atan2(fy_, fx_) + r.uniform(-50, 50) * D
            sp = r.uniform(3, 7) * S
            fd = drag_dist(0.88, a)
            x, y = tip[0] + math.cos(an) * sp * fd, tip[1] + math.sin(an) * sp * fd
            dk = 0.88 ** a
            qq = a / life
            pen.line(x, y, x - math.cos(an) * sp * dk * 1.6, y - math.sin(an) * sp * dk * 1.6, mix(HOT, c, qq), 255 * (1 - qq), 1.3 * S)
    # 8: sparkle dust left behind as it retracts
    t2 = EXT_CHARGE + EXT_EXTEND + Th
    if t >= t2:
        nd = max(0, F.jround(18 * float(P.get("density") or 1)))
        for i in range(nd):
            r = rng_for(inst.seed, i, 13)
            u = r.uniform(0.05, 1.0)
            b = t2 + EXT_RETRACT * ((1 - u) ** (1 / 3.0))
            aa = t - b
            if aa < 0 or aa >= EXT_DUST:
                continue
            q = aa / float(EXT_DUST)
            drift = r.uniform(-0.5, 0.5) * S * aa
            px, py = fr.w(u * Lmax, drift)
            py -= 0.15 * S * aa
            pen.glow(px, py, 3.2 * S * (1 - q) + 0.6, mix(c, HOT, 0.5), 230 * (1 - q), 0.5)
    _hit_marks(pen, inst, c, ps, fx_, fy_)


def draw(p, inst, host, ps):
    pen = Pen(p)
    st = _style(inst.fx["params"])
    if st == "crescent_wave":
        _draw_wave(pen, inst, host, ps)
    elif st == "blade_extension":
        _draw_extension(pen, inst, host, ps)
    elif st in strikefx.STYLES:
        strikefx.draw(pen, inst, host, ps)
    else:
        _draw_slash(pen, inst, host, ps)


# Ki blasts and punches (laser/strikefx.py) share this module's frame, pen and
# timeline; imported last because it builds on them.
from . import strikefx  # noqa: E402
