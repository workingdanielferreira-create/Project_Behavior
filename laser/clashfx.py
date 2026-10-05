"""
Clash explosion FX — the visual library for the Clash interaction.

When two attacks clash (energy blasts colliding, a beam struggle, a storm of
kunai meeting kunai, two blades locked), the spot where they meet gets one of
the explosions below.  This module only DRAWS them; deciding when a clash
happens (and which explosion it gets) belongs to the clash interaction.

Ten baselines (BASES).  Every one is drawn in a local frame centred on the
clash point whose +x axis points from side A (colour c1) toward side B
(colour c2), so each half of an explosion takes the colour of its own side's
attack, with a white-hot core where they meet:

  collision_nova     two blasts meet: core flash, split shockwave rings, sparks
  beam_struggle      SUSTAINED: pulsing node between two beams, lightning arcs,
                     tug-of-war wobble, ripples; detonates on release
  overpower_blowout  a struggle won: cone blast driven toward the loser, smoke
  kunai_storm        dozens of tiny steel-on-steel clashes, kunai spinning off
  ricochet_rain      chains of spark pops ricocheting outward over ~1 s
  blade_lock         SUSTAINED: two blades crossed in an X, grinding sparks,
                     pressure ripples; ends in a screen-cutting slash line
  reiatsu_eruption   a pillar of spiritual pressure, ground rings, rising embers
  getsuga_cross      two crescents collide: cross flare, crescent shards
  implosion_pop      energies cancel: particles collapse inward, pause, pop
  storm_fork         branching lightning forks with a flickering afterglow

Variations: every baseline takes the same tunables (size, density, speed,
life, hold, hot, plus a few of its own — see BASES).  derive() registers a
new variation from a baseline with overrides, e.g.

    derive("mega_nova", "collision_nova", name="Mega Nova", size=1.8, density=1.6)

Spawning (the clash interaction will call this; F6 previews it in game):

    fx = spawn(world, "beam_struggle", x, y, angle=deg, c1=(r, g, b), c2=(r, g, b))
    ...
    fx.release(winner=0)   # end a sustained clash (hold=-1 means "until released")

Live explosions sit in world.clash_fx (one list for the whole world, so Solo
and Battle behave identically) and age inside Overlay._paint like the other
Pattern-B eye-candy, so they keep animating through hit-stop.  The browser
gallery tools/fx/clash_gallery.html ports these same algorithms.
"""

import math
import random

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import (QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF,
                         QRadialGradient)

MAX_LIVE = 16                 # oldest explosion is dropped past this
FINALE_GRACE = 60             # ticks a finished explosion waits for its last particles
HOT = (255, 255, 255)
STEEL = (198, 208, 224)
SMOKE = (70, 66, 72)
TAU = math.pi * 2

# Shared tunables, overridable per variation: size / density / speed scale
# the geometry, particle counts and particle speeds; life = ticks of the burst
# (of the finale, for a sustained clash); hold = ticks a sustained clash
# lasts before it detonates by itself (-1 = until release()); hot = the
# colour of the meeting core.
COMMON = dict(size=1.0, density=1.0, speed=1.0, hot=HOT)

BASES = {
    "collision_nova": dict(name="Collision Nova", kind="burst", life=40),
    "beam_struggle": dict(name="Beam Struggle Node", kind="sustain", life=36, hold=150, stubs=True, stub_len=150),
    "overpower_blowout": dict(name="Overpower Blowout", kind="burst", life=56, cone_deg=34),
    "kunai_storm": dict(name="Kunai Storm", kind="burst", life=62, area_rx=120, area_ry=80, clashes=56),
    "ricochet_rain": dict(name="Ricochet Rain", kind="burst", life=66, chains=6, hops=8),
    "blade_lock": dict(name="Blade Lock", kind="sustain", life=38, hold=120, blade_len=78, cross_deg=35),
    "reiatsu_eruption": dict(name="Reiatsu Eruption", kind="burst", life=74, pillar_h=280, world_up=True),
    "getsuga_cross": dict(name="Getsuga Cross", kind="burst", life=44, shards=12),
    "implosion_pop": dict(name="Implosion Pop", kind="burst", life=58, gather=22, pause=5),
    "storm_fork": dict(name="Storm Fork", kind="burst", life=42, forks=7),
}
BASE_ORDER = list(BASES)

# Derived variations: key -> (base key, overrides).
VARIANTS = {}


def derive(key, base, name=None, **overrides):
    """Register a variation of a baseline (or of another variation)."""
    if base in VARIANTS:
        root, prev = VARIANTS[base]
        merged = dict(prev)
        merged.update(overrides)
        base, overrides = root, merged
    if base not in BASES:
        raise KeyError("unknown clash FX baseline: %r" % (base,))
    if name:
        overrides = dict(overrides, name=name)
    VARIANTS[key] = (base, dict(overrides))
    return key


def resolve(key):
    """(base key, full spec) for a baseline or derived variation."""
    if key in VARIANTS:
        base, ov = VARIANTS[key]
    else:
        base, ov = key, {}
    spec = dict(COMMON)
    spec.update(BASES[base])
    spec.update(ov)
    return base, spec


def preview_order():
    """Every baseline, then every derived variation (F6 cycles these)."""
    return BASE_ORDER + [k for k in VARIANTS if k not in BASES]


def display_name(key):
    return resolve(key)[1]["name"]


# ---------------------------------------------------------------- helpers
def _cl(v):
    return 0 if v < 0 else 255 if v > 255 else int(v)


def _q(c, a=255):
    return QColor(_cl(c[0]), _cl(c[1]), _cl(c[2]), _cl(a))


def _mix(a, b, k):
    return (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k)


def _ease_out(u):
    u = 0.0 if u < 0 else 1.0 if u > 1 else u
    return 1.0 - (1.0 - u) ** 3


def _ease_in(u):
    u = 0.0 if u < 0 else 1.0 if u > 1 else u
    return u * u * u


def _glow(p, x, y, r, c, a, mid=0.35):
    if r <= 0.5 or a <= 1:
        return
    g = QRadialGradient(x, y, r)
    g.setColorAt(0.0, _q(c, a))
    g.setColorAt(mid, _q(c, a * 0.45))
    g.setColorAt(1.0, _q(c, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(x, y), r, r)


def _glow_ellipse(p, x, y, rx, ry, c, a, mid=0.35):
    if rx <= 0.5 or ry <= 0.5 or a <= 1:
        return
    p.save()
    p.translate(x, y)
    p.scale(1.0, ry / rx)
    _glow(p, 0.0, 0.0, rx, c, a, mid)
    p.restore()


def _split_ring(p, cx, cy, rx, ry, w, ca, cb, a):
    """An (elliptical) ring whose left half is ca and right half cb."""
    if rx <= 0.5 or a <= 1 or w <= 0.05:
        return
    rect = QRectF(cx - rx, cy - ry, rx * 2, ry * 2)
    pen = QPen(_q(ca, a), w)
    pen.setCapStyle(Qt.FlatCap)
    p.setBrush(Qt.NoBrush)
    p.setPen(pen)
    p.drawArc(rect, 90 * 16, 180 * 16)
    pen.setColor(_q(cb, a))
    p.setPen(pen)
    p.drawArc(rect, -90 * 16, 180 * 16)


def _line(p, x0, y0, x1, y1, c, a, w):
    if a <= 1 or w <= 0.05:
        return
    pen = QPen(_q(c, a), w)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(x0, y0), QPointF(x1, y1))


def _star(p, x, y, long_r, short_r, c, a, w=1.6):
    """Four-point glint: a long arm on the local y axis, a short one on x."""
    _line(p, x, y - long_r, x, y + long_r, c, a, w)
    _line(p, x - short_r, y, x + short_r, y, c, a, w)


def _diamond(p, x0, y0, x1, y1, half_w, c, a):
    """A thin diamond (lens) from (x0, y0) to (x1, y1), widest in the middle."""
    if a <= 1 or half_w <= 0.05:
        return
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L * half_w, dx / L * half_w
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    poly = QPolygonF([QPointF(x0, y0), QPointF(mx + nx, my + ny), QPointF(x1, y1), QPointF(mx - nx, my - ny)])
    p.setPen(Qt.NoPen)
    p.setBrush(_q(c, a))
    p.drawPolygon(poly)


def _bolt(rng, x0, y0, ang, length, segs, jit, depth, out):
    """A jagged lightning polyline with random side branches."""
    step = length / max(1, segs)
    x, y = x0, y0
    pts = [QPointF(x, y)]
    for _ in range(segs):
        a = ang + rng.uniform(-jit, jit)
        x += math.cos(a) * step
        y += math.sin(a) * step
        pts.append(QPointF(x, y))
        if depth > 0 and rng.random() < 0.24:
            side = 1 if rng.random() < 0.5 else -1
            _bolt(rng, x, y, a + side * rng.uniform(0.4, 0.95), length * 0.45, max(2, segs // 2), jit, depth - 1, out)
    out.append((QPolygonF(pts), depth))
    return out


def _draw_bolts(p, bolts, c, a, glow_w=5.0, core_w=1.6):
    p.setBrush(Qt.NoBrush)
    for poly, depth in bolts:
        k = 1.0 if depth >= 1 else 0.6
        pen = QPen(_q(c, a * 0.4 * k), glow_w * k)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(poly)
        pen = QPen(_q(_mix(c, HOT, 0.75), a * k), core_w * k)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(poly)


# ---------------------------------------------------------------- particles
# kinds: spark (velocity streak), dot (soft glow), ember (flickering dot),
# smoke (dark puff, drawn underneath), kunai (spinning steel blade, drawn
# underneath), crescent (spinning arc), glint (four-point flare, static),
# ring (expanding split ring, static), streak (fixed line x,y -> x+vx,y+vy).
STATIC_KINDS = ("glint", "ring", "streak")
UNDER_KINDS = ("smoke", "kunai")


class _P:
    __slots__ = ("x", "y", "vx", "vy", "age", "life", "size", "col", "col2", "kind", "rot", "vr", "drag", "grav",
                 "delay")

    def __init__(self, kind, x, y, vx, vy, life, size, col, drag=0.94, grav=0.0, delay=0, rot=0.0, vr=0.0, col2=None):
        self.kind, self.x, self.y, self.vx, self.vy = kind, x, y, vx, vy
        self.life, self.size, self.col, self.col2 = max(1, int(life)), size, col, col2 or col
        self.drag, self.grav, self.delay, self.rot, self.vr = drag, grav, int(delay), rot, vr
        self.age = 0


# ---------------------------------------------------------------- the effect
class ClashFX:
    """One live clash explosion.  step() advances one tick, draw() paints it
    at its world position (pscale = the position scale at that point)."""

    def __init__(self, key, x, y, angle=0.0, c1=(90, 170, 255), c2=(255, 120, 60), scale=1.0, winner=0, hold=None,
                 seed=None):
        self.key = key
        self.base, self.spec = resolve(key)
        sp = self.spec
        self.name = sp["name"]
        self.x, self.y, self.angle = float(x), float(y), float(angle)
        self.c1, self.c2 = tuple(c1), tuple(c2)
        self.hot = tuple(sp["hot"])
        self.S = float(sp["size"]) * float(scale)
        self.D = max(0.05, float(sp["density"]))
        self.V = float(sp["speed"])
        self.life = max(1, int(sp["life"]))
        self.winner = 1 if winner else 0
        self.rng = random.Random(seed)
        self.t = 0
        self.ft = 0                      # ticks since the finale / burst started
        self.sustain = sp["kind"] == "sustain"
        self.phase = "hold" if self.sustain else "burst"
        self.hold = int(sp.get("hold", 0) if hold is None else hold)
        self.parts = []
        self.done = False
        a = math.radians(self.angle)
        # World "down" in the local (rotated) frame.
        self.down = (math.sin(a), math.cos(a))
        self.state = {}
        getattr(self, "_init_" + self.base)()

    # ---- lifecycle
    def release(self, winner=None):
        """End a sustained clash: it detonates (its finale) from here."""
        if winner is not None:
            self.winner = 1 if winner else 0
        if self.phase == "hold":
            self.phase = "finale"
            self.ft = 0
            fin = getattr(self, "_finale_" + self.base, None)
            if fin:
                fin()

    @property
    def alive(self):
        if self.phase == "hold":
            return True
        if self.ft < self.life:
            return True
        return bool(self.parts) and self.ft < self.life + FINALE_GRACE

    def step(self):
        self.t += 1
        if self.phase == "hold":
            if self.hold >= 0 and self.t >= self.hold:
                self.release()
        else:
            self.ft += 1
        tick = getattr(self, "_tick_" + self.base, None)
        if tick:
            tick()
        gx, gy = self.down
        live = []
        for q in self.parts:
            if q.delay > 0:
                q.delay -= 1
                live.append(q)
                continue
            if q.kind not in STATIC_KINDS:
                q.x += q.vx
                q.y += q.vy
                q.vx = q.vx * q.drag + gx * q.grav
                q.vy = q.vy * q.drag + gy * q.grav
                q.rot += q.vr
            q.age += 1
            if q.age < q.life:
                live.append(q)
        self.parts = live

    # ---- shared spawners
    def _side_col(self, lx):
        return self.c1 if lx < 0 else self.c2

    def _hotc(self, c, k=0.55):
        return _mix(c, self.hot, k)

    def _sparks(self, n, x=0.0, y=0.0, ang=None, spread=math.pi, spd=(3.0, 9.0), life=(16, 32), size=(1.6, 3.0),
                drag=0.92, grav=0.0, delay=0, col=None, kind="spark"):
        r = self.rng
        for _ in range(max(0, int(round(n * self.D)))):
            a = r.uniform(0, TAU) if ang is None else ang + r.uniform(-spread, spread)
            v = r.uniform(*spd) * self.V * self.S
            vx, vy = math.cos(a) * v, math.sin(a) * v
            c = col if col is not None else self._side_col(vx if abs(vx) > 1e-6 else r.uniform(-1, 1))
            d = delay if isinstance(delay, int) else r.randint(*delay)
            self.parts.append(_P(kind, x, y, vx, vy, r.randint(*life), r.uniform(*size) * self.S, c,
                                 drag=drag, grav=grav * self.S, delay=d))

    # ---- drawing
    def draw(self, p, pscale=1.0):
        p.save()
        p.translate(self.x, self.y)
        if not self.spec.get("world_up"):
            p.rotate(self.angle)
        if pscale != 1.0:
            p.scale(pscale, pscale)
        prev = p.compositionMode()
        getattr(self, "_draw_" + self.base)(p)
        p.setCompositionMode(prev)
        p.restore()

    def _draw_parts(self, p):
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        for q in self.parts:
            if q.delay <= 0 and q.kind in UNDER_KINDS:
                self._draw_part(p, q)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        for q in self.parts:
            if q.delay <= 0 and q.kind not in UNDER_KINDS:
                self._draw_part(p, q)

    def _draw_part(self, p, q):
        u = q.age / q.life
        f = 1.0 - u
        k = q.kind
        if k == "spark":
            L = 2.2
            _line(p, q.x - q.vx * L, q.y - q.vy * L, q.x, q.y, self._hotc(q.col, 0.45), 255 * f, q.size * (0.4 + 0.6 * f))
        elif k == "dot":
            _glow(p, q.x, q.y, q.size * (1.0 - 0.4 * u) * 2.4, self._hotc(q.col, 0.35), 220 * f)
        elif k == "ember":
            fl = 0.55 + 0.45 * math.sin(q.age * 0.9 + q.size * 7.0)
            _glow(p, q.x, q.y, q.size * 2.0, self._hotc(q.col, 0.3), 230 * f * fl)
        elif k == "smoke":
            r = q.size * (1.0 + 1.6 * u)
            c = _mix(SMOKE, q.col, 0.22)
            g = QRadialGradient(q.x, q.y, r)
            g.setColorAt(0.0, _q(c, 120 * f))
            g.setColorAt(1.0, _q(c, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(q.x, q.y), r, r)
        elif k == "kunai":
            self._draw_kunai(p, q, f)
        elif k == "crescent":
            self._draw_crescent(p, q, f)
        elif k == "glint":
            e = _ease_out(min(1.0, q.age / 3.0))
            a = 255 * f
            _glow(p, q.x, q.y, q.size * 1.6 * e, self._hotc(q.col, 0.4), a * 0.8)
            _star(p, q.x, q.y, q.size * 2.2 * e, q.size * 1.1 * e, self._hotc(q.col, 0.8), a, 1.3 * self.S)
        elif k == "ring":
            r = q.size * _ease_out(u)
            _split_ring(p, q.x, q.y, r, r, 2.4 * self.S * f + 0.4, self._hotc(q.col, 0.3), self._hotc(q.col2, 0.3), 220 * f)
        elif k == "streak":
            _line(p, q.x, q.y, q.x + q.vx, q.y + q.vy, self._hotc(q.col, 0.5), 200 * f * f, 1.4 * self.S)

    def _draw_kunai(self, p, q, f):
        s = q.size
        p.save()
        p.translate(q.x, q.y)
        p.rotate(math.degrees(q.rot))
        a = 255 * min(1.0, f * 1.6)
        # blade (diamond) + grip + ring
        p.setPen(Qt.NoPen)
        p.setBrush(_q(STEEL, a))
        p.drawPolygon(QPolygonF([QPointF(s * 1.0, 0), QPointF(s * 0.25, -s * 0.22), QPointF(-s * 0.1, 0),
                                 QPointF(s * 0.25, s * 0.22)]))
        _line(p, -s * 0.1, 0, -s * 0.7, 0, (52, 50, 60), a, max(1.0, s * 0.12))
        pen = QPen(_q(STEEL, a), max(0.8, s * 0.07))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(-s * 0.85, 0), s * 0.15, s * 0.15)
        p.restore()
        if q.age < 8:   # tip glint in the owner's colour
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            tx = q.x + math.cos(q.rot) * s
            ty = q.y + math.sin(q.rot) * s
            _glow(p, tx, ty, s * 0.6, self._hotc(q.col, 0.5), 200 * (1 - q.age / 8.0))
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    def _draw_crescent(self, p, q, f):
        s = q.size
        p.save()
        p.translate(q.x, q.y)
        p.rotate(math.degrees(q.rot))
        path = QPainterPath()
        path.moveTo(0, -s)
        path.quadTo(s * 1.1, 0, 0, s)
        path.quadTo(s * 0.45, 0, 0, -s)
        p.setPen(Qt.NoPen)
        p.setBrush(_q(self._hotc(q.col, 0.35), 235 * f))
        p.drawPath(path)
        p.restore()

    # ================================================================ 1
    def _init_collision_nova(self):
        self._sparks(46, spd=(3.0, 10.0), life=(16, 34))
        self._sparks(12, kind="dot", spd=(0.8, 3.0), life=(20, 36), size=(2.0, 3.5), drag=0.95)

    def _draw_collision_nova(self, p):
        S, t = self.S, self.ft
        u = min(1.0, t / self.life)
        f = 1.0 - u
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        e = _ease_out(t / 14.0)
        for c, sx in ((self.c1, -1), (self.c2, 1)):
            _glow(p, sx * 16 * S * (1 - e), 0, 52 * S * (0.6 + 0.8 * e), c, 210 * f ** 1.5)
        for delay, maxr, life, k in ((0, 175, 24, 0.55), (5, 128, 22, 0.25)):
            if delay <= t < delay + life:
                v = (t - delay) / life
                r = maxr * S * _ease_out(v)
                _split_ring(p, 0, 0, r, r, (6 * (1 - v) + 1) * S, self._hotc(self.c1, k), self._hotc(self.c2, k),
                            230 * (1 - v))
        cr = 48 * S * min(1.0, (t + 1) / 3.0) * f ** 0.5
        _glow(p, 0, 0, cr, self.hot, 255 * f * f, 0.5)
        self._draw_parts(p)

    # ================================================================ 2
    def _init_beam_struggle(self):
        self.state.update(arcs=[], ripples=[], cx=0.0, core=0.0, fx0=0.0)

    def _tick_beam_struggle(self):
        st, r, S = self.state, self.rng, self.S
        if self.phase != "hold":
            return
        t = self.t
        st["cx"] = (10 * math.sin(t * 0.09) + 4 * math.sin(t * 0.31 + 1.3)) * S
        g = min(1.0, t / 90.0)
        st["core"] = (18 + 14 * g) * S + 3 * S * math.sin(t * 0.6)
        cx, core = st["cx"], st["core"]
        if t % 3 == 0:
            arcs = []
            for _ in range(r.randint(3, 5)):
                a = r.uniform(0, TAU)
                L = r.uniform(40, 110) * S * (0.6 + 0.6 * g)
                arcs.append((_bolt(r, cx + math.cos(a) * core * 0.6, math.sin(a) * core * 0.6, a, L, 6, 0.55, 1, []),
                             self._side_col(math.cos(a))))
            st["arcs"] = arcs
        if t % 16 == 0:
            st["ripples"].append(0)
        st["ripples"] = [a + 1 for a in st["ripples"] if a + 1 < 30]
        # debris spray, mostly perpendicular to the beams
        for _ in range(2):
            if r.random() < self.D:
                side = 1 if r.random() < 0.5 else -1
                a = side * math.pi / 2 + r.gauss(0, 0.6)
                v = r.uniform(3, 7.5) * self.V * S
                self.parts.append(_P("spark", cx + math.cos(a) * core, math.sin(a) * core, math.cos(a) * v, math.sin(a) * v,
                                     r.randint(12, 24), r.uniform(1.4, 2.6) * S,
                                     self.c1 if r.random() < 0.5 else self.c2, drag=0.93))

    def _finale_beam_struggle(self):
        st = self.state
        st["fx0"] = st["cx"]
        cx = st["cx"]
        self._sparks(70, x=cx, spd=(4.0, 13.0), life=(18, 38))
        self._sparks(16, x=cx, kind="smoke", spd=(0.6, 2.2), life=(30, 50), size=(10, 18), drag=0.96)
        self._sparks(18, x=cx, kind="dot", spd=(1.0, 4.0), life=(22, 40), size=(2.0, 4.0), drag=0.95)

    def _draw_beam_struggle(self, p):
        st, S = self.state, self.S
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        if self.phase == "hold":
            cx, core, t = st["cx"], st["core"], self.t
            if self.spec.get("stubs"):
                L = float(self.spec.get("stub_len", 150)) * S
                for c, sx in ((self.c1, -1), (self.c2, 1)):
                    x_far, x_near = cx + sx * L, cx
                    for w, k, a in ((core * 1.3, 0.0, 120), (core * 0.55, 0.6, 230)):
                        gr = QLinearGradient(x_far, 0, x_near, 0)
                        gr.setColorAt(0.0, _q(_mix(c, HOT, k), 0))
                        gr.setColorAt(0.35, _q(_mix(c, HOT, k), a * 0.7))
                        gr.setColorAt(1.0, _q(_mix(c, HOT, k), a))
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(gr))
                        wob = 1 + 0.08 * math.sin(t * 0.8 + sx)
                        p.drawRect(QRectF(min(x_far, x_near), -w / 2 * wob, abs(x_near - x_far), w * wob))
            _glow(p, cx - 10 * S, 0, core * 2.4, self.c1, 200)
            _glow(p, cx + 10 * S, 0, core * 2.4, self.c2, 200)
            for a in st["ripples"]:
                v = a / 30.0
                r = (core + 90 * S * _ease_out(v))
                _split_ring(p, cx, 0, r * 0.45, r, 3 * S * (1 - v) + 0.5, self._hotc(self.c1, 0.4),
                            self._hotc(self.c2, 0.4), 200 * (1 - v))
            for bolts, c in st["arcs"]:
                _draw_bolts(p, bolts, c, 230, 4.0 * S, 1.3 * S)
            _glow(p, cx, 0, core * 1.15, self.hot, 255, 0.55)
        else:
            t = self.ft
            u = min(1.0, t / self.life)
            f = 1.0 - u
            cx = st["fx0"]
            _glow(p, cx, 0, 120 * S * _ease_out(t / 8.0), self._hotc(_mix(self.c1, self.c2, 0.5), 0.4), 255 * f ** 1.5)
            r = 230 * S * _ease_out(u)
            _split_ring(p, cx, 0, r, r, 9 * S * f + 1, self._hotc(self.c1, 0.4), self._hotc(self.c2, 0.4), 230 * f)
            r2 = 150 * S * _ease_out(min(1.0, t / 20.0))
            _split_ring(p, cx, 0, r2 * 0.5, r2, 5 * S * f + 0.5, self.c1, self.c2, 180 * f)
        self._draw_parts(p)

    # ================================================================ 3
    def _wdir(self):
        """+1 when side A (c1) won (blast drives toward +x), else -1."""
        return 1 if self.winner == 0 else -1

    def _init_overpower_blowout(self):
        d = self._wdir()
        cw, cl = (self.c1, self.c2) if self.winner == 0 else (self.c2, self.c1)
        base = 0.0 if d > 0 else math.pi
        cone = math.radians(float(self.spec.get("cone_deg", 34)))
        r = self.rng
        self._sparks(54, ang=base, spread=cone, spd=(5.0, 14.0), life=(18, 36), col=cw)
        self._sparks(20, ang=base, spread=cone * 1.6, spd=(3.0, 9.0), life=(16, 30), col=cl)
        self._sparks(18, ang=base, spread=cone, kind="dot", spd=(2.0, 6.0), life=(24, 44), size=(2.0, 4.0), col=cw,
                     drag=0.95)
        ux, uy = -self.down[0], -self.down[1]
        for _ in range(int(16 * self.D)):
            k = r.uniform(0.2, 1.0)
            v = r.uniform(0.6, 1.8) * self.S
            x = d * k * 110 * self.S
            self.parts.append(_P("smoke", x, r.uniform(-14, 14) * self.S, d * v * 0.6 + ux * v, uy * v,
                                 r.randint(34, 56), r.uniform(10, 18) * self.S, cw, drag=0.97, delay=r.randint(2, 12)))

    def _draw_overpower_blowout(self, p):
        S, t = self.S, self.ft
        u = min(1.0, t / self.life)
        f = 1.0 - u
        d = self._wdir()
        cw = self.c1 if self.winner == 0 else self.c2
        self._draw_parts_under(p)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        e = _ease_out(t / 16.0)
        _glow_ellipse(p, d * 70 * S * e, 0, 105 * S * (0.3 + 0.7 * e), 40 * S * (0.3 + 0.7 * e), cw, 230 * f ** 1.3)
        _glow_ellipse(p, d * 40 * S * e, 0, 60 * S * (0.3 + 0.7 * e), 20 * S, self.hot, 240 * f ** 2)
        _glow(p, 0, 0, 40 * S * min(1.0, (t + 1) / 3.0), self.hot, 255 * max(0.0, 1 - t / 10.0))
        v = min(1.0, t / 26.0)
        r = 150 * S * _ease_out(v)
        _split_ring(p, d * 20 * S, 0, r * 0.35, r, 5 * S * (1 - v) + 0.5, self._hotc(self.c1, 0.3),
                    self._hotc(self.c2, 0.3), 220 * (1 - v))
        self._draw_parts_over(p)

    def _draw_parts_under(self, p):
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        for q in self.parts:
            if q.delay <= 0 and q.kind in UNDER_KINDS:
                self._draw_part(p, q)

    def _draw_parts_over(self, p):
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        for q in self.parts:
            if q.delay <= 0 and q.kind not in UNDER_KINDS:
                self._draw_part(p, q)

    # ================================================================ 4
    def _init_kunai_storm(self):
        r, S, sp = self.rng, self.S, self.spec
        rx, ry = float(sp.get("area_rx", 120)) * S, float(sp.get("area_ry", 80)) * S
        n = int(float(sp.get("clashes", 56)) * self.D)
        span = max(4, int(self.life * 0.55))
        for _ in range(n):
            a = r.uniform(0, TAU)
            k = math.sqrt(r.random())
            x, y = math.cos(a) * rx * k, math.sin(a) * ry * k
            dl = r.randint(0, span)
            c = self._side_col(x + r.uniform(-30, 30) * S)
            self.parts.append(_P("glint", x, y, 0, 0, r.randint(7, 11), r.uniform(3.0, 5.0) * S, c, delay=dl))
            for _ in range(2):
                b = r.uniform(0, TAU)
                v = r.uniform(2.5, 6.0) * self.V * S
                self.parts.append(_P("spark", x, y, math.cos(b) * v, math.sin(b) * v, r.randint(8, 14),
                                     r.uniform(1.0, 1.8) * S, c, drag=0.9, delay=dl))
            # the two kunai that met bounce apart
            b = r.uniform(0, TAU)
            for sgn in (1, -1):
                bb = b + (0 if sgn > 0 else math.pi) + r.uniform(-0.5, 0.5)
                v = r.uniform(2.0, 4.5) * self.V * S
                self.parts.append(_P("kunai", x, y, math.cos(bb) * v, math.sin(bb) * v, r.randint(22, 36),
                                     r.uniform(9.0, 12.0) * S, self.c1 if sgn > 0 else self.c2, drag=0.95,
                                     grav=0.22, delay=dl, rot=r.uniform(0, TAU), vr=r.uniform(-0.45, 0.45)))

    def _draw_kunai_storm(self, p):
        S, t = self.S, self.ft
        u = min(1.0, t / self.life)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        fl = 0.6 + 0.4 * math.sin(t * 1.7)
        rx, ry = float(self.spec.get("area_rx", 120)) * S, float(self.spec.get("area_ry", 80)) * S
        _glow_ellipse(p, -rx * 0.3, 0, rx * 0.9, ry * 0.9, self.c1, 70 * (1 - u) * fl)
        _glow_ellipse(p, rx * 0.3, 0, rx * 0.9, ry * 0.9, self.c2, 70 * (1 - u) * fl)
        self._draw_parts(p)

    # ================================================================ 5
    def _init_ricochet_rain(self):
        r, S, sp = self.rng, self.S, self.spec
        chains = max(1, int(round(float(sp.get("chains", 6)) * self.D)))
        hops = int(sp.get("hops", 8))
        for ci in range(chains):
            a = ci * TAU / chains + r.uniform(-0.4, 0.4)
            x = y = 0.0
            off = r.randint(0, 6)
            for h in range(hops):
                step = r.uniform(12, 20) * S * self.V
                a += r.gauss(0, 0.75)
                nx, ny = x + math.cos(a) * step, y + math.sin(a) * step
                dl = off + h * 4
                c = self.c1 if (h + ci) % 2 == 0 else self.c2
                c2 = self.c2 if c is self.c1 else self.c1
                self.parts.append(_P("streak", x, y, nx - x, ny - y, 10, 1.0, c, delay=dl))
                self.parts.append(_P("ring", nx, ny, 0, 0, 14, r.uniform(9, 14) * S, c, col2=c2, delay=dl + 1))
                self.parts.append(_P("glint", nx, ny, 0, 0, 9, r.uniform(2.6, 4.0) * S, c, delay=dl + 1))
                for _ in range(2):
                    b = a + r.uniform(-1.2, 1.2)
                    v = r.uniform(2.0, 5.0) * S * self.V
                    self.parts.append(_P("spark", nx, ny, math.cos(b) * v, math.sin(b) * v, r.randint(8, 14),
                                         r.uniform(1.0, 1.8) * S, c, drag=0.9, delay=dl + 1))
                x, y = nx, ny

    def _draw_ricochet_rain(self, p):
        t = self.ft
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        _glow(p, 0, 0, 30 * self.S, self.hot, 240 * max(0.0, 1 - t / 8.0))
        self._draw_parts(p)

    # ================================================================ 6
    def _init_blade_lock(self):
        self.state.update(ripples=[], shake=(0.0, 0.0), split=0)

    def _tick_blade_lock(self):
        st, r, S = self.state, self.rng, self.S
        if self.phase != "hold":
            st["split"] += 1
            return
        t = self.t
        st["shake"] = (r.uniform(-2, 2) * S, r.uniform(-2, 2) * S)
        if t % 12 == 0:
            st["ripples"].append(0)
        st["ripples"] = [a + 1 for a in st["ripples"] if a + 1 < 26]
        for _ in range(3):
            if r.random() < self.D:
                up = -1 if r.random() < 0.75 else 1   # mostly sprays up the blades
                a = math.atan2(up, 0) + r.gauss(0, 0.65)
                v = r.uniform(4, 10) * self.V * S
                self.parts.append(_P("spark", 0, 0, math.cos(a) * v, math.sin(a) * v, r.randint(12, 22),
                                     r.uniform(1.2, 2.2) * S, self.c1 if math.cos(a) < 0 else self.c2,
                                     drag=0.93, grav=0.38 * S))

    def _finale_blade_lock(self):
        self._sparks(54, spd=(5.0, 15.0), life=(14, 30), grav=0.2)
        self._sparks(10, kind="dot", spd=(1.0, 4.0), life=(18, 32), size=(2.0, 3.6), drag=0.95)

    def _blade_ends(self, side, push):
        """Hilt and tip of side's blade, crossing the origin at cross_deg."""
        S = self.S
        L = float(self.spec.get("blade_len", 78)) * S
        a = math.radians(float(self.spec.get("cross_deg", 35)))
        wob = math.radians(3.0) * math.sin(self.t * 0.2 + side)
        a += wob * side
        ca, sa = math.cos(a), math.sin(a)
        # side -1 (A) comes from the left, hilt low-left, tip up-right
        hx, hy = side * ca * L + side * push, sa * L
        tx, ty = -side * ca * L * 0.38 + side * push, -sa * L * 0.38
        return hx, hy, tx, ty

    def _draw_blade(self, p, side, push, alpha):
        c = self.c1 if side < 0 else self.c2
        hx, hy, tx, ty = self._blade_ends(side, push)
        S = self.S
        _line(p, hx, hy, tx, ty, c, 110 * alpha, 9 * S)
        _diamond(p, hx, hy, tx, ty, 2.6 * S, self._hotc(c, 0.7), 255 * alpha)
        _line(p, hx, hy, tx, ty, self.hot, 220 * alpha, 1.0 * S)

    def _draw_blade_lock(self, p):
        st, S = self.state, self.S
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        if self.phase == "hold":
            t = self.t
            p.save()
            p.translate(*st["shake"])
            for a in st["ripples"]:
                v = a / 26.0
                r = 20 * S + 110 * S * _ease_out(v)
                _split_ring(p, 0, 0, r * 0.35, r, 3.5 * S * (1 - v) + 0.4, self._hotc(self.c1, 0.3),
                            self._hotc(self.c2, 0.3), 200 * (1 - v))
            _glow(p, -14 * S, 0, 46 * S, self.c1, 120)
            _glow(p, 14 * S, 0, 46 * S, self.c2, 120)
            self._draw_blade(p, -1, 0.0, 1.0)
            self._draw_blade(p, 1, 0.0, 1.0)
            fl = 0.75 + 0.25 * math.sin(t * 2.3)
            _glow(p, 0, 0, 16 * S * fl, self.hot, 255, 0.5)
            _star(p, 0, 0, (30 + 10 * math.sin(t * 1.7)) * S, 14 * S * fl, self.hot, 240, 1.8 * S)
            p.restore()
        else:
            t = self.ft
            u = min(1.0, t / self.life)
            f = 1.0 - u
            k = min(1.0, st["split"] / 10.0)
            if k < 1.0:
                self._draw_blade(p, -1, 40 * S * _ease_out(k), 1 - k)
                self._draw_blade(p, 1, 40 * S * _ease_out(k), 1 - k)
            L = 300 * S * _ease_out(min(1.0, t / 4.0))
            mix = _mix(self.c1, self.c2, 0.5)
            _diamond(p, 0, -L, 0, L, 10 * S * f, mix, 150 * f)
            _diamond(p, 0, -L, 0, L, 3.0 * S * f + 0.4, self.hot, 255 * f)
            _diamond(p, -90 * S * f, 0, 90 * S * f, 0, 4 * S * f, self.hot, 200 * f)
            _glow(p, 0, 0, 70 * S * f, mix, 220 * f * f)
        self._draw_parts(p)

    # ================================================================ 7
    def _lr(self):
        """(left, right) colours on screen for the world-up effects."""
        return (self.c1, self.c2) if math.cos(math.radians(self.angle)) >= 0 else (self.c2, self.c1)

    def _init_reiatsu_eruption(self):
        r, S = self.rng, self.S
        cl, cr = self._lr()
        for _ in range(int(54 * self.D)):
            x = r.uniform(-22, 22) * S
            self.parts.append(_P("ember", x, r.uniform(-6, 6) * S, r.uniform(-0.6, 0.6) * S,
                                 -r.uniform(1.8, 6.0) * S * self.V, r.randint(28, 58), r.uniform(1.4, 2.8) * S,
                                 cl if x < 0 else cr, drag=0.985, delay=r.randint(0, 40)))
        self._sparks(24, spd=(3.0, 8.0), life=(14, 26))
        for q in self.parts:
            if q.kind == "spark":
                q.vy = -abs(q.vy) * 0.6
                q.col = cl if q.vx < 0 else cr

    def _draw_reiatsu_eruption(self, p):
        S, t = self.S, self.ft
        u = min(1.0, t / self.life)
        cl, cr = self._lr()
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        H = float(self.spec.get("pillar_h", 280)) * S * _ease_out(t / 14.0)
        fade = 1.0 if u < 0.55 else max(0.0, 1 - (u - 0.55) / 0.45)
        W = 34 * S * (1 + 0.25 * math.sin(t * 0.9)) * (1 - 0.5 * u)
        if H > 1:   # soft halo so the column has no hard edges
            _glow_ellipse(p, -W * 0.5, -H * 0.45, W * 1.6, H * 0.6, cl, 110 * fade, 0.5)
            _glow_ellipse(p, W * 0.5, -H * 0.45, W * 1.6, H * 0.6, cr, 110 * fade, 0.5)
        for c, x0, x1 in ((cl, -W, 0.0), (cr, 0.0, W)):
            gr = QLinearGradient(0, 0, 0, -H)
            gr.setColorAt(0.0, _q(c, 230 * fade))
            gr.setColorAt(0.6, _q(c, 140 * fade))
            gr.setColorAt(1.0, _q(c, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(gr))
            p.drawRect(QRectF(x0, -H, x1 - x0, H))
        gr = QLinearGradient(0, 0, 0, -H)
        gr.setColorAt(0.0, _q(self.hot, 255 * fade))
        gr.setColorAt(1.0, _q(self.hot, 0))
        p.setBrush(QBrush(gr))
        p.drawRect(QRectF(-W * 0.18, -H, W * 0.36, H))
        _glow_ellipse(p, 0, 0, 70 * S, 26 * S, _mix(cl, cr, 0.5), 220 * fade)
        for i in range(4):
            a = t - i * 6
            if 0 <= a < 30:
                v = a / 30.0
                rx = 160 * S * _ease_out(v)
                _split_ring(p, 0, 0, rx, rx * 0.28, 4 * S * (1 - v) + 0.4, self._hotc(cl, 0.3), self._hotc(cr, 0.3),
                            220 * (1 - v))
        self._draw_parts(p)

    # ================================================================ 8
    def _init_getsuga_cross(self):
        r, S = self.rng, self.S
        n = int(float(self.spec.get("shards", 12)) * self.D)
        for i in range(n):
            a = (math.pi / 4) * (1 + 2 * (i % 4)) + r.uniform(-0.3, 0.3)
            v = r.uniform(4.0, 9.0) * self.V * S
            vx, vy = math.cos(a) * v, math.sin(a) * v
            self.parts.append(_P("crescent", 0, 0, vx, vy, r.randint(22, 36), r.uniform(9, 17) * S,
                                 self._side_col(vx), drag=0.95, rot=a, vr=r.uniform(-0.25, 0.25)))
        self._sparks(30, spd=(3.0, 11.0), life=(14, 28))

    def _draw_getsuga_cross(self, p):
        S, t = self.S, self.ft
        u = min(1.0, t / self.life)
        f = 1.0 - u
        e = _ease_out(t / 4.0)
        w = (1 - u) ** 1.5
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        Ly, Lx = 165 * S * e, 115 * S * e
        _diamond(p, -Lx, 0, 0, 0, 9 * S * w, self.c1, 220 * f)
        _diamond(p, 0, 0, Lx, 0, 9 * S * w, self.c2, 220 * f)
        mix = _mix(self.c1, self.c2, 0.5)
        _diamond(p, 0, -Ly, 0, Ly, 11 * S * w, mix, 200 * f)
        _diamond(p, 0, -Ly * 0.9, 0, Ly * 0.9, 3 * S * w + 0.3, self.hot, 255 * f)
        _diamond(p, -Lx * 0.9, 0, Lx * 0.9, 0, 2.4 * S * w + 0.3, self.hot, 255 * f)
        _glow(p, 0, 0, 50 * S * f, self.hot, 255 * f * f, 0.45)
        self._draw_parts(p)

    # ================================================================ 9
    def _init_implosion_pop(self):
        r, S = self.rng, self.S
        self.state["inw"] = [(r.uniform(0, TAU), r.uniform(115, 170) * S, r.randint(0, 6))
                             for _ in range(int(64 * self.D))]
        self.state["popped"] = False

    def _tick_implosion_pop(self):
        gather = int(self.spec.get("gather", 22))
        pause = int(self.spec.get("pause", 5))
        if not self.state["popped"] and self.ft >= gather + pause:
            self.state["popped"] = True
            self._sparks(38, spd=(4.0, 12.0), life=(14, 30))
            self._sparks(10, kind="dot", spd=(1.0, 3.5), life=(18, 30), size=(2.0, 3.5), drag=0.95)

    def _draw_implosion_pop(self, p):
        S, t = self.S, self.ft
        gather = int(self.spec.get("gather", 22))
        pop = gather + int(self.spec.get("pause", 5))
        if t < gather:
            k = t / float(gather)
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            for a, R0, dl in self.state["inw"]:
                kk = max(0.0, (t - dl) / float(max(1, gather - dl)))
                rr = R0 * (1 - _ease_in(kk))
                L = 8 * S + 20 * S * _ease_in(kk)
                ca, sa = math.cos(a), math.sin(a)
                _line(p, ca * (rr + L), sa * (rr + L), ca * rr, sa * rr, self._hotc(self._side_col(ca), 0.35),
                      230 * min(1.0, kk * 3 + 0.2), 1.6 * S)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            dr = (8 + 20 * k) * S
            _glow(p, 0, 0, dr * 1.3, (8, 4, 14), 200 * k, 0.6)
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            _split_ring(p, 0, 0, dr, dr, 1.6 * S, self._hotc(self.c1, 0.5), self._hotc(self.c2, 0.5), 230 * k)
        elif t < pop:
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            k = 1 - (t - gather) / float(max(1, pop - gather))
            _glow(p, 0, 0, 34 * S * k, (8, 4, 14), 200 * k, 0.6)
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            _glow(p, 0, 0, (3 + 3 * math.sin(t * 2.5)) * S, self.hot, 255)
        else:
            v = t - pop
            span = max(1, self.life - pop)
            f = max(0.0, 1 - v / span)
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            _glow(p, 0, 0, 62 * S * min(1.0, (v + 1) / 3.0) * f ** 0.6, self.hot, 255 * f * f, 0.45)
            for delay, maxr, life in ((0, 155, 16), (4, 100, 18)):
                if delay <= v < delay + life:
                    w = (v - delay) / float(life)
                    r = maxr * S * _ease_out(w)
                    _split_ring(p, 0, 0, r, r, 3 * S * (1 - w) + 0.5, self._hotc(self.c1, 0.4),
                                self._hotc(self.c2, 0.4), 240 * (1 - w))
        self._draw_parts(p)

    # ================================================================ 10
    def _init_storm_fork(self):
        r = self.rng
        n = max(1, int(round(float(self.spec.get("forks", 7)) * self.D)))
        self.state["dirs"] = [(i * TAU / n + r.uniform(-0.35, 0.35), r.uniform(95, 155) * self.S) for i in range(n)]
        self.state["bolts"] = []
        self._sparks(20, spd=(3.0, 9.0), life=(12, 24))

    def _tick_storm_fork(self):
        t = self.ft
        if t % 2 == 0 and t < self.life * 0.75:
            grow = _ease_out(min(1.0, (t + 1) / 6.0))
            bolts = []
            for a, L in self.state["dirs"]:
                bolts.append((_bolt(self.rng, 0, 0, a, L * grow, 8, 0.5, 2, []), self._side_col(math.cos(a))))
            self.state["bolts"] = bolts

    def _draw_storm_fork(self, p):
        S, t = self.S, self.ft
        u = min(1.0, t / self.life)
        f = 1.0 - u
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        fl = 0.6 + 0.4 * (1 if (t // 2) % 2 else 0)
        mix = _mix(self.c1, self.c2, 0.5)
        _glow(p, 0, 0, 42 * S, mix, 200 * f * fl)
        if t < 3:
            _glow(p, 0, 0, 90 * S, self.hot, 230 * (1 - t / 3.0))
        if u < 0.85:
            a = 255 * (1 - u / 0.85) * fl
            for bolts, c in self.state["bolts"]:
                _draw_bolts(p, bolts, c, a, 5.0 * S, 1.6 * S)
        _glow(p, 0, 0, 14 * S, self.hot, 255 * f)
        self._draw_parts(p)


# ---------------------------------------------------------------- world API
def spawn(world, key, x, y, angle=0.0, c1=(90, 170, 255), c2=(255, 120, 60), scale=1.0, winner=0, hold=None,
          seed=None):
    """Start a clash explosion at (x, y).  angle = degrees from side A toward
    side B (screen coordinates, y down).  Returns the live ClashFX."""
    lst = getattr(world, "clash_fx", None)
    if lst is None:
        lst = world.clash_fx = []
    fx = ClashFX(key, x, y, angle, c1, c2, scale, winner, hold, seed)
    lst.append(fx)
    if len(lst) > MAX_LIVE:
        del lst[0:len(lst) - MAX_LIVE]
    return fx


def draw_all(p, world, pscale_at=None):
    """Draw, then age, every live clash explosion (called from _paint)."""
    lst = getattr(world, "clash_fx", None)
    if not lst:
        return
    live = []
    for fx in lst:
        s = pscale_at(fx.x, fx.y) if pscale_at else 1.0
        fx.draw(p, s)
        fx.step()
        if fx.alive:
            live.append(fx)
    world.clash_fx = live
