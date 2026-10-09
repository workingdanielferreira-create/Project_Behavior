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
                     tug-of-war wobble, ripples; detonates on release.  In a
                     clash it is anchored (anchor_beams): it draws both real
                     beams itself, origin to node at their real widths, and
                     the node is pushed toward the losing side
  overpower_blowout  a struggle won: cone blast driven toward the loser, smoke
  kunai_storm        dozens of tiny steel-on-steel clashes, kunai spinning off
  ricochet_rain      chains of spark pops ricocheting outward over ~1 s
  blade_lock         SUSTAINED: two blades crossed in an X, grinding sparks,
                     pressure ripples; ends in a screen-cutting slash line
  reiatsu_eruption   a pillar of spiritual pressure, ground rings, rising embers
  getsuga_cross      two crescents collide: cross flare, crescent shards
  implosion_pop      energies cancel: particles collapse inward, pause, pop
  storm_fork         branching lightning forks with a flickering afterglow
  speed_duel         SUSTAINED: two fighters too fast to see — streaks zip round
                     the area and clash flashes pop where they meet, in bursts
                     of strikes broken by pauses; ends in one final big clash

Pair clashes (played by laser/clash.py when two opposing FX meet; +x points
from the first effect toward the second):

  beam_clash         beam x beam, both strong: two beam fronts slam together,
                     a huge two-tone blast with rays shooting out sideways
  beam_orb           beam x orb: the orb is pressed against the beam head,
                     squashes and crackles, then bursts
  beam_split         beam cut by a blade / crescent / sprite: a forked flare
                     where the beam splits into two halves (+x = beam heading)
  split_burst        the small blast at the end of each split half
  orb_pops           orb x orb: little energy blasts hitting each other and
                     popping in rapid succession
  sword_slash_clash  two slash strokes cross, an X flash and a fan of sparks
                     along both cuts (trail x trail while a pair is re-arming)
  sword_duel         SUSTAINED trail x trail, anchored: the two real fighters
                     dash in and out (duel_plan), each cut drawn from the
                     fighter's hand through the blade contact, blades crossed
                     in an X while they bind; ends in one big clash
  crescent_struggle  SUSTAINED crescent x crescent: two crescent blades grind
                     against each other, then shatter into shards
  kunai_clash        sprite x sprite: two kunai meet tip to tip, a glint, and
                     both ricochet away spinning

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
# Real effects (id of an FX Kit Inst / combat Projectile) an anchored clash FX
# currently draws in their place (laser/clash.py fills it): their own draw is
# skipped meanwhile (fxkit.Player.draw, Overlay._paint).
HIDDEN = set()
BEAM_PUSH = 0.55              # anchored struggle: share of the way the node is pushed toward the loser
RIM = (8, 10, 16)             # dark rim drawn under the beam struggle node's FX (reads on bright desktops)
SHOCK_TICKS = 26              # beam struggle node: life of each shockwave ring
SURGE_MAX = 0.45              # tug of war: furthest a surge carries the node toward a side (share of the way)
SURGE_TICKS = (18, 40)        # ticks between surges
COMMIT_AT = 0.7               # share of the struggle after which it commits (winner push / overload build-up)

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
    # strikes = (min, max) per burst, gap = ticks between strikes in a burst,
    # pause = ticks between bursts, bind = chance a strike locks and grinds.
    "speed_duel": dict(name="Speed Duel", kind="sustain", life=44, hold=190, area_rx=150, area_ry=95,
                       strikes=(3, 6), gap=(4, 8), pause=(16, 28), bind=0.25),
    # ---- pair clashes (laser/clash.py)
    "beam_clash": dict(name="Beam Clash", kind="burst", life=56, rays=9),
    # press = ticks the orb is held against the beam head before it bursts
    "beam_orb": dict(name="Beam vs Orb", kind="burst", life=52, press=18),
    "beam_split": dict(name="Beam Split", kind="burst", life=30, fork_deg=30),
    "split_burst": dict(name="Split Burst", kind="burst", life=30),
    "orb_pops": dict(name="Orb Pops", kind="burst", life=44, pops=12),
    "sword_slash_clash": dict(name="Sword Slash Clash", kind="burst", life=30),
    # SUSTAINED, anchored to the two fighters (laser/clash.py moves them):
    # strikes = (min, max) over the whole duel, bind = chance a strike locks.
    "sword_duel": dict(name="Sword Duel", kind="sustain", life=40, hold=-1, world_up=True,
                       strikes=(4, 7), bind=0.3, reach=34),
    "crescent_struggle": dict(name="Crescent Struggle", kind="sustain", life=34, hold=48),
    "kunai_clash": dict(name="Kunai Clash", kind="burst", life=34),
}
# The baselines F6 previews and the gallery shows first; PAIR_FX follow.
PAIR_FX = ("beam_clash", "beam_orb", "beam_split", "split_burst", "orb_pops", "sword_slash_clash",
           "sword_duel", "crescent_struggle", "kunai_clash")
BASE_ORDER = [k for k in BASES if k not in PAIR_FX] + list(PAIR_FX)

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


def _vivid(a, b):
    """The more saturated of two colours (white loses to any real colour)."""
    sat = lambda c: max(c) - min(c)
    return tuple(a) if sat(a) >= sat(b) else tuple(b)


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
# ring (expanding split ring, static), streak (fixed line x,y -> x+vx,y+vy),
# dash (a fighter's glowing speed streak, fixed line like streak).
STATIC_KINDS = ("glint", "ring", "streak", "dash")
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
                 seed=None, density=1.0):
        self.key = key
        self.base, self.spec = resolve(key)
        sp = self.spec
        self.name = sp["name"]
        self.x, self.y, self.angle = float(x), float(y), float(angle)
        self.c1, self.c2 = tuple(c1), tuple(c2)
        self.hot = tuple(sp["hot"])
        self.S = float(sp["size"]) * float(scale)
        self.D = max(0.05, float(sp["density"]) * float(density))
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
        self.rim = False                 # dark rim under the particles (beam struggle node)
        # Anchored (laser/clash.py): parts of it are drawn at the fighters'
        # real positions, so it ignores the position scale when drawn.
        self.anchored = False
        # Playback rate (fit): clash-FX ticks per world tick, never under 1.
        # _wt world ticks played, _done clash-FX ticks run so far.
        self.rate = 1.0
        self._fit = None
        self._wt = self._done = 0
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

    def fit(self, ticks):
        """Play the whole loop (hold + burst / finale) within `ticks` world
        ticks: faster when it is longer, never slower (laser/clash.py fits a
        clash to the shorter remaining life of the two effects)."""
        n = (max(0, self.hold) if self.sustain else 0) + self.life
        if ticks and ticks > 0 and n > ticks:
            self.rate = n / float(ticks)
            self._fit = (n, int(ticks))
        return self

    def length(self):
        """World ticks its loop takes at its rate (a hold of -1 counts 0)."""
        if self._fit is not None:
            return self._fit[1]
        return max(1, (max(0, self.hold) if self.sustain else 0) + self.life)

    def step(self):
        """One world tick: rate clash-FX ticks (fit), scheduled in whole
        numbers so the loop ends exactly on its last world tick."""
        if self._fit is None:
            self._step1()
            return
        n, ticks = self._fit
        self._wt += 1
        want = (self._wt * n) // ticks if self._wt < ticks else n + (self._wt - ticks)
        while self._done < want:
            self._done += 1
            self._step1()

    def _step1(self):
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
    def _local(self, wx, wy):
        """World point -> this effect's local (drawing) frame."""
        dx, dy = wx - self.x, wy - self.y
        if self.spec.get("world_up"):
            return dx, dy
        a = math.radians(self.angle)
        ca, sa = math.cos(a), math.sin(a)
        return dx * ca + dy * sa, -dx * sa + dy * ca

    def _world(self, lx, ly):
        """Local (drawing) frame point -> world."""
        if self.spec.get("world_up"):
            return self.x + lx, self.y + ly
        a = math.radians(self.angle)
        ca, sa = math.cos(a), math.sin(a)
        return self.x + lx * ca - ly * sa, self.y + lx * sa + ly * ca

    def draw(self, p, pscale=1.0):
        p.save()
        p.translate(self.x, self.y)
        if not self.spec.get("world_up"):
            p.rotate(self.angle)
        if pscale != 1.0 and not self.anchored:
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
        self._draw_parts_over(p)

    def _draw_rims(self, p):
        """A soft dark rim under each spark / dot (self.rim), so light FX
        still read over a bright desktop."""
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        for q in self.parts:
            if q.delay > 0:
                continue
            f = 1.0 - q.age / q.life
            if q.kind == "spark":
                L = 2.2
                _line(p, q.x - q.vx * L, q.y - q.vy * L, q.x, q.y, RIM, 95 * f,
                      q.size * (0.4 + 0.6 * f) + 1.4 * self.S)
            elif q.kind == "dot":
                _glow(p, q.x, q.y, q.size * 2.2, RIM, 80 * f, 0.55)

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
        elif k == "dash":
            # the tail fades first: the streak shrinks toward the head
            tx, ty = q.x + q.vx * min(1.0, u * 1.4), q.y + q.vy * min(1.0, u * 1.4)
            hx, hy = q.x + q.vx, q.y + q.vy
            _line(p, tx, ty, hx, hy, q.col, 90 * f, q.size * 3.2)
            _line(p, tx, ty, hx, hy, self._hotc(q.col, 0.6), 255 * f, q.size)
            _glow(p, hx, hy, q.size * 3.0, self._hotc(q.col, 0.4), 160 * f)

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
        self.state.update(arcs=[], shocks=[], nx=0.0, ny=0.0, core=0.0, R=0.0, f0=(0.0, 0.0), fR=0.0, ax=0.0,
                          o=None, looks=None, bw=(0.0, 0.0), loser=None,
                          s=0.0, sv=0.0, tgt=0.0, next=0, over=0.0, overload=False)
        self.rim = True

    def anchor_beams(self, look1, look2, loser=None):
        """laser/clash.py: tie the struggle to the two real beams.  look1 /
        look2 = how each side's beam is drawn right now (clash._beam_look:
        o = where it starts, world, locked when the clash starts; tail /
        head width, colours, glow, alpha, blend — screen px).  The node
        starts at the contact and surges back and forth between the two
        origins (a tug of war), then commits toward the loser's origin
        (loser = 0 / 1) or, on a tie (None), shakes in place building to an
        overload.  Both
        beams are then drawn here with their own look, from each origin to
        the node, so the real ones can be hidden (HIDDEN) without a seam.
        Its size (S) is already set from the beams' widths, so the position
        scale is not applied again."""
        self.anchored = True
        looks = (dict(look1), dict(look2))
        for lk in looks:
            lk["o"] = self._local(*lk["o"])
        l1, l2 = looks[0]["o"], looks[1]["o"]
        dx, dy = l2[0] - l1[0], l2[1] - l1[1]
        # The node takes each beam's own colour (the more vivid of its tail /
        # head colours), not the bullet's base colour.
        self.c1, self.c2 = (_vivid(lk["ct"], lk["ch"]) for lk in looks)
        self.state.update(o=(l1, l2), looks=looks,
                          bw=tuple(max(2.0, lk["wh"]) for lk in looks), loser=loser,
                          ax=math.atan2(dy, dx) if math.hypot(dx, dy) > 1e-6 else 0.0)

    def node_world(self):
        """Where the struggle's node is now (its finale spot once released)."""
        st = self.state
        if self.base != "beam_struggle":
            return self.x, self.y
        lx, ly = (st["nx"], st["ny"]) if self.phase == "hold" else st["f0"]
        return self._world(lx, ly)

    def _tick_beam_struggle(self):
        st, r, S = self.state, self.rng, self.S
        if self.phase != "hold":
            return
        t = self.t
        g = min(1.0, t / 90.0)
        sway = (10 * math.sin(t * 0.09) + 4 * math.sin(t * 0.31 + 1.3)) * S
        ax = st["ax"]
        ux, uy = math.cos(ax), math.sin(ax)
        core0 = 0.0
        over = 0.0
        if self.anchored:
            # Tug of war: s = where the node is between the two origins
            # (-1 = side A's origin, 0 = the contact, +1 = side B's).  It
            # surges back and forth in irregular pushes, sprung so it
            # overshoots and recoils; after COMMIT_AT it commits toward the
            # loser, or (a tie) shakes in place building to an overload.
            span = float(self.hold) if self.hold > 0 else 90.0
            u = min(1.0, t / span)
            lo = st["loser"]
            if t >= st["next"]:
                side = -1.0 if st["tgt"] > 0 else 1.0
                st["tgt"] = side * r.uniform(0.15, SURGE_MAX)
                st["next"] = t + r.randint(*SURGE_TICKS)
            tgt = st["tgt"]
            if u > COMMIT_AT:
                k = _ease_in((u - COMMIT_AT) / (1.0 - COMMIT_AT))
                if lo is not None:
                    tgt += ((BEAM_PUSH if lo == 1 else -BEAM_PUSH) - tgt) * min(1.0, 3.0 * k)
                else:
                    tgt *= 1.0 - min(1.0, 3.0 * k)
                    over = (u - COMMIT_AT) / (1.0 - COMMIT_AT)
            st["sv"] = st["sv"] * 0.86 + (tgt - st["s"]) * 0.035
            st["s"] = max(-0.9, min(0.9, st["s"] + st["sv"]))
            sv = st["s"]
            ox, oy = st["o"][1] if sv >= 0 else st["o"][0]
            nx, ny = ox * abs(sv), oy * abs(sv)
            if over > 0:    # the overload build-up shakes the node
                j = 7.0 * S * over
                nx, ny = nx + r.uniform(-j, j), ny + r.uniform(-j, j)
            core0 = 0.55 * max(st["bw"]) * (1.0 + 0.25 * g)
        else:
            nx, ny = sway, 0.0
        st["nx"], st["ny"] = nx, ny
        st["core"] = max((18 + 14 * g) * S, core0) + 3 * S * math.sin(t * 0.6)
        core = st["core"]
        # The energy sphere: 2-3x the beams' width, swelling as it goes on,
        # pulsing.
        base = 1.25 * max(st["bw"]) if self.anchored else core * 1.4
        st["over"] = over
        R = max(base, 24 * S) * (1.0 + 0.25 * g) * (1.0 + 0.07 * math.sin(t * 0.5) + 0.04 * math.sin(t * 1.3 + 0.7))
        if over > 0:    # swelling and throbbing harder before it blows
            R *= 1.0 + 0.6 * over + 0.12 * over * math.sin(t * 2.1)
        st["R"] = R
        if t % 3 == 0:
            arcs = []
            for _ in range(r.randint(3, 5)):
                a = r.uniform(0, TAU)
                L = r.uniform(40, 110) * S * (0.6 + 0.6 * g)
                arcs.append((_bolt(r, nx + math.cos(a) * R * 0.8, ny + math.sin(a) * R * 0.8, a, L, 6, 0.55, 1, []),
                             self._side_col(math.cos(a - ax))))
            st["arcs"] = arcs
        # shockwave rings bursting off the sphere
        if t % 14 == 0:
            st["shocks"].append(0)
        st["shocks"] = [a + 1 for a in st["shocks"] if a + 1 < SHOCK_TICKS]
        # heavy spark / debris spray off the sphere, mostly sideways to the
        # beams, like grinding metal
        for _ in range(5 + int(6 * over)):
            if r.random() < self.D:
                side = 1 if r.random() < 0.5 else -1
                a = ax + side * math.pi / 2 + r.gauss(0, 0.75)
                v = r.uniform(5.0, 12.0) * self.V * S
                self.parts.append(_P("spark", nx + math.cos(a) * R * 0.85, ny + math.sin(a) * R * 0.85,
                                     math.cos(a) * v, math.sin(a) * v,
                                     r.randint(18, 34), r.uniform(2.2, 4.0) * S,
                                     self.c1 if r.random() < 0.5 else self.c2, drag=0.94, grav=0.12 * S))
        if r.random() < 0.6 * self.D:
            side = 1 if r.random() < 0.5 else -1
            a = ax + side * math.pi / 2 + r.gauss(0, 0.9)
            v = r.uniform(2.0, 6.0) * self.V * S
            self.parts.append(_P("dot", nx + math.cos(a) * R * 0.8, ny + math.sin(a) * R * 0.8,
                                 math.cos(a) * v, math.sin(a) * v,
                                 r.randint(24, 40), r.uniform(3.0, 5.5) * S,
                                 self.c1 if r.random() < 0.5 else self.c2, drag=0.95, grav=0.25 * S))

    def _finale_beam_struggle(self):
        st = self.state
        st["f0"] = (st["nx"], st["ny"])
        st["fR"] = st["R"]
        x, y = st["f0"]
        self._sparks(90, x=x, y=y, spd=(4.0, 14.0), life=(20, 40), size=(2.0, 3.6))
        self._sparks(16, x=x, y=y, kind="smoke", spd=(0.6, 2.2), life=(30, 50), size=(10, 18), drag=0.96)
        self._sparks(24, x=x, y=y, kind="dot", spd=(1.0, 5.0), life=(22, 40), size=(3.0, 5.5), drag=0.95)

    def overload(self):
        """laser/clash.py: a tied struggle overloads — call after release().
        A far bigger blast (sparks, debris, smoke) and a larger flash and
        rings in the finale."""
        if self.base != "beam_struggle":
            return
        st = self.state
        st["overload"] = True
        x, y = st["f0"]
        self._sparks(170, x=x, y=y, spd=(6.0, 22.0), life=(24, 46), size=(2.4, 4.4))
        self._sparks(30, x=x, y=y, kind="smoke", spd=(1.0, 3.5), life=(36, 60), size=(14, 26), drag=0.96)
        self._sparks(44, x=x, y=y, kind="dot", spd=(2.0, 9.0), life=(26, 46), size=(3.5, 6.5), drag=0.95,
                     grav=0.15)

    def _draw_sphere(self, p, R, a):
        """The struggle's energy sphere at the origin (already translated to
        the node): a dark rim, a body mixing both beams' colours with a
        white-hot core, each side's colour leaning in from its own beam."""
        if R <= 0.5 or a <= 1:
            return
        k = a / 255.0
        S = self.S
        mid = _mix(self.c1, self.c2, 0.5)
        deep = _mix(mid, RIM, 0.25)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        # a thin soft dark halo just outside the sphere
        g = QRadialGradient(0, 0, R * 1.25)
        g.setColorAt(0.0, _q(RIM, 0))
        g.setColorAt(0.7, _q(RIM, 0))
        g.setColorAt(0.8, _q(RIM, 120 * k))
        g.setColorAt(1.0, _q(RIM, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(0, 0), R * 1.25, R * 1.25)
        g = QRadialGradient(0, 0, R)
        g.setColorAt(0.0, _q(HOT, 255 * k))
        g.setColorAt(0.3, _q(_mix(mid, HOT, 0.6), 255 * k))
        g.setColorAt(0.75, _q(mid, 250 * k))
        g.setColorAt(1.0, _q(deep, 250 * k))
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(0, 0), R, R)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        _glow(p, -R * 0.35, 0, R * 0.9, self.c1, 150 * k)
        _glow(p, R * 0.35, 0, R * 0.9, self.c2, 150 * k)
        _glow(p, 0, 0, R * 0.6, HOT, 255 * k, 0.5)
        # a few bright flecks swirling in the sphere
        for i in range(3):
            b = self.t * (0.21 + 0.07 * i) + i * 2.1
            _glow(p, math.cos(b) * R * 0.55, math.sin(b * 1.3) * R * 0.45, 5 * S, HOT, 200 * k)

    def _draw_shock(self, p, r, w, a):
        """One shockwave ring: a dark rim under a ring in each side's colour."""
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        _split_ring(p, 0, 0, r, r, w + 2.5 * self.S, RIM, RIM, 0.45 * a)
        _split_ring(p, 0, 0, r, r, w, self.c1, self.c2, a)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        _split_ring(p, 0, 0, r, r, w * 0.4, self._hotc(self.c1, 0.6), self._hotc(self.c2, 0.6), a * 0.8)

    def _draw_struggle_beam(self, p, nx, ny, lk, wob):
        """One side's beam, anchored: from its real origin to the node, drawn
        the way the real beam is (fxkit _draw_beam: a tapered capsule, tail
        width / colour at the origin, head width / colour at the node, its
        glow pass under the body), so it lines up with the beam it replaces.
        On top, a white-hot core that builds from the origin into the node,
        and a pulse (wob) that grows toward the node only."""
        ox, oy = lk["o"]
        L = math.hypot(nx - ox, ny - oy)
        if L < 1.0:
            return
        ah = math.atan2(ny - oy, nx - ox)

        def capsule(wt, wh):
            path = QPainterPath()
            for k in range(13):
                a = ah + math.pi + (k / 12 - 0.5) * math.pi
                q = QPointF(ox + math.cos(a) * wt / 2, oy + math.sin(a) * wt / 2)
                if k == 0:
                    path.moveTo(q)
                else:
                    path.lineTo(q)
            for k in range(13):
                a = ah + (k / 12 - 0.5) * math.pi
                path.lineTo(QPointF(nx + math.cos(a) * wh / 2, ny + math.sin(a) * wh / 2))
            path.closeSubpath()
            return path

        def fill(path, ct, ch, a, a_tail=None):
            gr = QLinearGradient(ox, oy, nx, ny)
            gr.setColorAt(0.0, _q(ct, a if a_tail is None else a_tail))
            gr.setColorAt(1.0, _q(ch, a))
            p.setBrush(QBrush(gr))
            p.drawPath(path)

        am = lk["am"]
        wt, wh = max(1.0, lk["wt"]), max(1.0, lk["wh"]) * wob
        p.setPen(Qt.NoPen)
        p.setCompositionMode(QPainter.CompositionMode_Plus if lk["add"] else QPainter.CompositionMode_SourceOver)
        if lk["glow"] > 0:
            g = lk["gcol"]
            fill(capsule(wt + lk["glow"], wh + lk["glow"]), g or lk["ct"], g or lk["ch"], 70 * am)
        fill(capsule(wt, wh), lk["ct"], lk["ch"], 235 * am)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        fill(capsule(wt * 0.4, wh * 0.45), _mix(lk["ct"], HOT, 0.85), _mix(lk["ch"], HOT, 0.85), 230 * am, 0)
        _glow(p, nx, ny, wh * 0.9, self._hotc(lk["ch"], 0.4), 160 * am)

    def _draw_beam_struggle(self, p):
        st, S = self.state, self.S
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        if self.phase == "hold":
            nx, ny, R, t, ax = st["nx"], st["ny"], st["R"], self.t, st["ax"]
            if self.anchored:
                for i in (0, 1):
                    self._draw_struggle_beam(p, nx, ny, st["looks"][i], 1 + 0.08 * math.sin(t * 0.8 + i))
                p.setCompositionMode(QPainter.CompositionMode_Plus)
            elif self.spec.get("stubs"):
                L = float(self.spec.get("stub_len", 150)) * S
                core = st["core"]
                for c, sx in ((self.c1, -1), (self.c2, 1)):
                    x_far, x_near = nx + sx * L, nx
                    for w, k, a in ((core * 1.3, 0.0, 120), (core * 0.55, 0.6, 230)):
                        gr = QLinearGradient(x_far, 0, x_near, 0)
                        gr.setColorAt(0.0, _q(_mix(c, HOT, k), 0))
                        gr.setColorAt(0.35, _q(_mix(c, HOT, k), a * 0.7))
                        gr.setColorAt(1.0, _q(_mix(c, HOT, k), a))
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(gr))
                        wob = 1 + 0.08 * math.sin(t * 0.8 + sx)
                        p.drawRect(QRectF(min(x_far, x_near), -w / 2 * wob, abs(x_near - x_far), w * wob))
            # shockwaves and the sphere, oriented along the line between the beams
            p.save()
            p.translate(nx, ny)
            p.rotate(math.degrees(ax))
            for a in st["shocks"]:
                v = a / float(SHOCK_TICKS)
                r = R * (1.0 + 1.8 * _ease_out(v))
                self._draw_shock(p, r, 5 * S * (1 - v) + 1.0, 235 * (1 - v))
            self._draw_sphere(p, R, 255)
            p.restore()
            for bolts, c in st["arcs"]:
                p.setCompositionMode(QPainter.CompositionMode_SourceOver)
                _draw_bolts(p, bolts, RIM, 90, 5.0 * S, 2.6 * S)
                p.setCompositionMode(QPainter.CompositionMode_Plus)
                _draw_bolts(p, bolts, c, 230, 4.0 * S, 1.3 * S)
        else:
            t = self.ft
            u = min(1.0, t / self.life)
            f = 1.0 - u
            x, y = st["f0"]
            R0 = st["fR"] or 30 * S
            big = 2.0 if st["overload"] else 1.0    # an overload blows far bigger
            p.save()
            p.translate(x, y)
            p.rotate(math.degrees(st["ax"]))
            # the sphere flares, then collapses
            e = min(1.0, t / 10.0)
            self._draw_sphere(p, R0 * (1.0 + 0.6 * big * _ease_out(e)) * (1.0 - 0.8 * _ease_in(u)), 255 * f ** 1.2)
            r = max(230 * S, R0 * 3.0) * big * _ease_out(u)
            self._draw_shock(p, r, 9 * S * f * big + 1, 230 * f)
            r2 = max(150 * S, R0 * 2.0) * big * _ease_out(min(1.0, t / 20.0))
            self._draw_shock(p, r2, 5 * S * f * big + 0.5, 180 * f)
            if st["overload"]:
                r3 = max(110 * S, R0 * 1.5) * big * _ease_out(min(1.0, t / 12.0))
                self._draw_shock(p, r3, 7 * S * f + 0.5, 220 * f)
                p.setCompositionMode(QPainter.CompositionMode_Plus)
                _glow(p, 0, 0, R0 * 4.0 * _ease_out(e), HOT, 255 * f ** 2, 0.4)
            p.restore()
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
        if self.rim:
            self._draw_rims(p)
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


    # ================================================================ 11
    def _init_speed_duel(self):
        S, sp = self.S, self.spec
        rx, ry = float(sp.get("area_rx", 150)) * S, float(sp.get("area_ry", 95)) * S
        self.state.update(rx=rx, ry=ry, a=[-rx * 0.6, 0.0], b=[rx * 0.6, 0.0], next=0, left=0, flash=[], pausing=False)

    def _duel_point(self, k=0.8):
        st, r = self.state, self.rng
        a = r.uniform(0, TAU)
        m = math.sqrt(r.random()) * k
        return [math.cos(a) * st["rx"] * m, math.sin(a) * st["ry"] * m]

    def _duel_dash(self, who, to, delay=0, life=9):
        st = self.state
        fr = st[who]
        c = self.c1 if who == "a" else self.c2
        self.parts.append(_P("dash", fr[0], fr[1], to[0] - fr[0], to[1] - fr[1], life, 1.9 * self.S, c, delay=delay))
        st[who] = [to[0], to[1]]

    def _duel_contact(self, x, y, delay, big=False):
        r, S = self.rng, self.S
        k = 1.6 if big else 1.0
        c = self.c1 if r.random() < 0.5 else self.c2
        self.parts.append(_P("glint", x, y, 0, 0, 12 if big else 9, (5.5 if big else 3.6) * S, c, delay=delay))
        self.parts.append(_P("ring", x, y, 0, 0, 14, (26 if big else 15) * S, self.c1, col2=self.c2, delay=delay))
        self._sparks(9 * k, x=x, y=y, spd=(3.0, 9.0 * k), life=(8, 16), size=(1.1, 2.0), drag=0.88, delay=delay)
        self.state["flash"].append([x, y, -delay, 1.0 if big else 0.6])

    def _duel_strike(self):
        st, r, S = self.state, self.rng, self.S
        P = self._duel_point()
        self._duel_dash("a", P, 0, 11)
        self._duel_dash("b", P, 0, 11)
        bind = r.random() < float(self.spec.get("bind", 0.25))
        self._duel_contact(P[0], P[1], 2, bind)
        if bind:   # blades lock and grind for a moment
            for d in (4, 6, 8):
                self._sparks(4, x=P[0], y=P[1], ang=-math.pi / 2, spread=1.0, spd=(3.0, 8.0), life=(10, 18),
                             grav=0.35, delay=d)
        # both recoil away from the contact along a random clash axis
        a = r.uniform(0, TAU)
        d = r.uniform(14, 26) * S
        ux, uy = math.cos(a) * d, math.sin(a) * d
        if ux > 0:
            ux, uy = -ux, -uy   # A recoils toward its own (left) side
        self._duel_dash("a", [P[0] + ux, P[1] + uy], 3, 8)
        self._duel_dash("b", [P[0] - ux, P[1] - uy], 3, 8)

    def _duel_spot(self, who):
        """A standby spot on the fighter's own side (A left, B right)."""
        st, r = self.state, self.rng
        sx = -1 if who == "a" else 1
        return [sx * r.uniform(0.3, 0.95) * st["rx"], r.uniform(-0.8, 0.8) * st["ry"]]

    def _duel_reposition(self):
        r = self.rng
        self._duel_dash("a", self._duel_spot("a"), r.randint(0, 3), 12)
        self._duel_dash("b", self._duel_spot("b"), r.randint(0, 3), 12)

    def _tick_speed_duel(self):
        st, r, sp = self.state, self.rng, self.spec
        st["flash"] = [[x, y, a + 1, k] for x, y, a, k in st["flash"] if a + 1 < 10]
        if self.phase != "hold":
            return
        if self.t < st["next"]:
            if st["pausing"]:   # circling between bursts: short flickers on each side
                for who in ("a", "b"):
                    if r.random() < 0.16:
                        self._duel_dash(who, self._duel_spot(who), 0, 10)
            return
        if st["left"] > 0:
            st["pausing"] = False
            self._duel_strike()
            st["left"] -= 1
            st["next"] = self.t + r.randint(*sp.get("gap", (4, 8)))
        else:
            self._duel_reposition()
            st["pausing"] = self.t > 0
            st["left"] = r.randint(*sp.get("strikes", (3, 6)))
            st["next"] = self.t + (r.randint(*sp.get("pause", (16, 28))) if self.t > 0 else 8)

    def _finale_speed_duel(self):
        st, S = self.state, self.S
        rx = st["rx"]
        st["a"], st["b"] = [-rx * 1.05, 0.0], [rx * 1.05, 0.0]
        self._duel_dash("a", [0.0, 0.0], 0, 12)
        self._duel_dash("b", [0.0, 0.0], 0, 12)
        self._sparks(56, spd=(4.0, 14.0), life=(16, 34), delay=3)
        self._sparks(12, kind="dot", spd=(1.0, 4.0), life=(20, 34), size=(2.0, 3.6), drag=0.95, delay=3)

    def _draw_speed_duel(self, p):
        st, S = self.state, self.S
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        for x, y, a, k in st["flash"]:
            if a >= 0:
                v = a / 10.0
                _glow(p, x, y, 34 * S * k * (0.5 + 0.5 * v), self.hot, 230 * (1 - v) * k)
        if self.phase != "hold":
            t = self.ft - 3
            if t >= 0:
                u = min(1.0, t / float(self.life))
                f = 1.0 - u
                _glow(p, 0, 0, 95 * S * _ease_out(t / 6.0), self._hotc(_mix(self.c1, self.c2, 0.5), 0.45), 255 * f ** 1.4)
                r = 210 * S * _ease_out(u)
                _split_ring(p, 0, 0, r, r, 7 * S * f + 0.8, self._hotc(self.c1, 0.4), self._hotc(self.c2, 0.4), 230 * f)
                L = 240 * S * _ease_out(min(1.0, t / 4.0))
                _diamond(p, 0, -L, 0, L, 7 * S * f, _mix(self.c1, self.c2, 0.5), 160 * f)
                _diamond(p, 0, -L, 0, L, 2.2 * S * f + 0.3, self.hot, 255 * f)
        self._draw_parts(p)

    # ================================================================ pair: beam x beam (strong)
    def _init_beam_clash(self):
        r, S = self.rng, self.S
        n = max(3, int(round(float(self.spec.get("rays", 9)) * self.D)))
        # rays mostly perpendicular to the beams (the blast squeezes out sideways)
        self.state["rays"] = [((1 if i % 2 else -1) * math.pi / 2 + r.gauss(0, 0.45), r.uniform(110, 200) * S,
                               r.uniform(3.0, 6.0) * S) for i in range(n)]
        self._sparks(60, spd=(4.0, 15.0), life=(18, 40))
        self._sparks(18, kind="smoke", spd=(0.5, 2.0), life=(36, 56), size=(12, 22), drag=0.96, delay=(4, 14))
        self._sparks(16, kind="dot", spd=(1.0, 5.0), life=(24, 44), size=(2.0, 4.0), drag=0.95)

    def _draw_beam_clash(self, p):
        S, t = self.S, self.ft
        u = min(1.0, t / float(self.life))
        f = 1.0 - u
        self._draw_parts_under(p)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        e = _ease_out(t / 10.0)
        # the two beam fronts flatten against each other
        for c, sx in ((self.c1, -1), (self.c2, 1)):
            _glow_ellipse(p, sx * 22 * S * (1 - e * 0.5), 0, 46 * S * (0.6 + 0.6 * e), 90 * S * (0.4 + 0.8 * e), c,
                          230 * f ** 1.2)
        for a, L, w in self.state["rays"]:
            k = _ease_out(min(1.0, t / 7.0))
            ex, ey = math.cos(a) * L * k, math.sin(a) * L * k
            c = self._side_col(math.cos(a) + 1e-3)
            _diamond(p, 0, 0, ex, ey, w * f, self._hotc(c, 0.4), 230 * f)
        _glow(p, 0, 0, 110 * S * _ease_out(t / 6.0), self.hot, 255 * f ** 2, 0.45)
        for delay, maxr, life, k in ((0, 240, 30, 0.5), (6, 170, 26, 0.2)):
            if delay <= t < delay + life:
                v = (t - delay) / float(life)
                r = maxr * S * _ease_out(v)
                _split_ring(p, 0, 0, r * 0.75, r, (9 * (1 - v) + 1) * S, self._hotc(self.c1, k), self._hotc(self.c2, k),
                            230 * (1 - v))
        self._draw_parts_over(p)

    # ================================================================ pair: beam x orb
    def _init_beam_orb(self):
        self.state["burst"] = False

    def _tick_beam_orb(self):
        press = int(self.spec.get("press", 18))
        r = self.rng
        if self.ft < press:
            # crackle + sideways spray while the orb is held on the beam head
            if r.random() < 0.8 * self.D:
                side = 1 if r.random() < 0.5 else -1
                a = side * math.pi / 2 + r.gauss(0, 0.5)
                v = r.uniform(2.5, 6.0) * self.S
                self.parts.append(_P("spark", 6 * self.S, 0, math.cos(a) * v, math.sin(a) * v, r.randint(8, 14),
                                     r.uniform(1.0, 2.0) * self.S, self.c2 if r.random() < 0.6 else self.c1, drag=0.9))
        elif not self.state["burst"]:
            self.state["burst"] = True
            self._sparks(34, x=14 * self.S, spd=(3.0, 11.0), life=(14, 30))
            self._sparks(14, x=14 * self.S, kind="dot", spd=(1.0, 4.5), life=(18, 32), size=(2.0, 3.6), drag=0.94,
                         col=self.c2)
            self._sparks(10, x=14 * self.S, kind="smoke", spd=(0.4, 1.6), life=(26, 40), size=(8, 14), drag=0.96)

    def _draw_beam_orb(self, p):
        S, t = self.S, self.ft
        press = int(self.spec.get("press", 18))
        self._draw_parts_under(p)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        if t < press:
            k = t / float(press)
            # beam head pushing in from -x
            _glow_ellipse(p, -14 * S, 0, 40 * S, 26 * S, self.c1, 220)
            _glow(p, -6 * S, 0, 14 * S, self._hotc(self.c1, 0.7), 255, 0.5)
            # the orb squashes against it and swells
            ox = 16 * S - 4 * S * k
            sq = 1.0 - 0.35 * k
            rr = (12 + 6 * k) * S * (1 + 0.08 * math.sin(t * 1.9))
            _glow_ellipse(p, ox, 0, rr * 1.9 * sq, rr * 1.9 / sq, self.c2, 210)
            _glow_ellipse(p, ox, 0, rr * 0.8 * sq, rr * 0.8 / sq, self._hotc(self.c2, 0.6), 255, 0.6)
            if t % 2 == 0:
                bolts = []
                for _ in range(2):
                    a = self.rng.uniform(-1.2, 1.2) + (math.pi if self.rng.random() < 0.3 else 0)
                    _bolt(self.rng, ox, 0, a, rr * 2.2, 4, 0.6, 0, bolts)
                self.state["arcs"] = bolts
            _draw_bolts(p, self.state.get("arcs") or [], self._hotc(self.c2, 0.3), 220, 3.0 * S, 1.0 * S)
        else:
            v = t - press
            span = max(1, self.life - press)
            f = max(0.0, 1 - v / float(span))
            _glow(p, 14 * S, 0, 70 * S * min(1.0, (v + 1) / 3.0) * f ** 0.6, self.hot, 255 * f * f, 0.45)
            _glow(p, 14 * S, 0, 90 * S * _ease_out(v / 10.0), self.c2, 200 * f)
            r = 150 * S * _ease_out(min(1.0, v / 18.0))
            _split_ring(p, 14 * S, 0, r, r, 5 * S * f + 0.5, self._hotc(self.c1, 0.35), self._hotc(self.c2, 0.35),
                        230 * f)
        self._draw_parts_over(p)

    # ================================================================ pair: beam split
    def _init_beam_split(self):
        fd = math.radians(float(self.spec.get("fork_deg", 30)))
        self._sparks(26, ang=0.0, spread=fd * 1.4, spd=(3.0, 10.0), life=(10, 22), col=self.c1)
        self._sparks(14, ang=math.pi, spread=1.2, spd=(2.0, 6.0), life=(8, 16), col=self.c2)

    def _draw_beam_split(self, p):
        S, t = self.S, self.ft
        u = min(1.0, t / float(self.life))
        f = 1.0 - u
        fd = math.radians(float(self.spec.get("fork_deg", 30)))
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        L = 70 * S * _ease_out(min(1.0, t / 5.0))
        for sgn in (1, -1):
            ex, ey = math.cos(fd * sgn) * L, math.sin(fd * sgn) * L
            _diamond(p, 0, 0, ex, ey, 6 * S * f, self.c1, 200 * f)
            _diamond(p, 0, 0, ex, ey, 2 * S * f + 0.3, self.hot, 255 * f)
        # the cutting edge: a short bright bar across the beam
        _diamond(p, 0, -26 * S, 0, 26 * S, 3.5 * S * f, self._hotc(self.c2, 0.4), 230 * f)
        _glow(p, 0, 0, 34 * S * (0.6 + 0.4 * f), self.hot, 255 * f * f, 0.5)
        self._draw_parts(p)

    # ================================================================ pair: split-half tip
    def _init_split_burst(self):
        self._sparks(24, spd=(2.5, 8.0), life=(12, 26))
        self._sparks(6, kind="smoke", spd=(0.4, 1.4), life=(22, 34), size=(6, 10), drag=0.96)

    def _draw_split_burst(self, p):
        S, t = self.S, self.ft
        u = min(1.0, t / float(self.life))
        f = 1.0 - u
        self._draw_parts_under(p)
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        _glow(p, 0, 0, 44 * S * min(1.0, (t + 1) / 3.0) * f ** 0.5, self.hot, 255 * f * f, 0.45)
        _glow(p, 0, 0, 60 * S * _ease_out(t / 8.0), _mix(self.c1, self.c2, 0.5), 180 * f)
        r = 90 * S * _ease_out(u)
        _split_ring(p, 0, 0, r, r, 4 * S * f + 0.5, self._hotc(self.c1, 0.3), self._hotc(self.c2, 0.3), 220 * f)
        self._draw_parts_over(p)

    # ================================================================ pair: orb x orb
    def _init_orb_pops(self):
        r, S = self.rng, self.S
        n = max(2, int(round(float(self.spec.get("pops", 12)) * self.D)))
        span = max(4, int(self.life * 0.6))
        pops = []
        for i in range(n):
            a = r.uniform(0, TAU)
            m = math.sqrt(r.random())
            px, py = math.cos(a) * 46 * S * m, math.sin(a) * 34 * S * m
            t0 = int(i * span / n) + r.randint(0, 2)
            pops.append([px, py, t0])
            # the two little blasts flying in from each side
            for c, sx in ((self.c1, -1), (self.c2, 1)):
                fx_ = px + sx * r.uniform(28, 44) * S
                fy_ = py + r.uniform(-14, 14) * S
                self.parts.append(_P("dash", fx_, fy_, px - fx_, py - fy_, 6, 1.4 * S, c, delay=max(0, t0 - 4)))
            self.parts.append(_P("glint", px, py, 0, 0, 8, 3.0 * S, self.c1 if i % 2 else self.c2, delay=t0))
            self.parts.append(_P("ring", px, py, 0, 0, 11, r.uniform(10, 16) * S, self.c1, col2=self.c2, delay=t0))
            self._sparks(5, x=px, y=py, spd=(2.0, 6.0), life=(7, 13), size=(1.0, 1.8), drag=0.88, delay=t0)
        self.state["pops"] = pops

    def _draw_orb_pops(self, p):
        S, t = self.S, self.ft
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        for px, py, t0 in self.state["pops"]:
            v = t - t0
            if 0 <= v < 8:
                _glow(p, px, py, 16 * S * (0.5 + 0.5 * v / 8.0), self.hot, 240 * (1 - v / 8.0), 0.45)
        u = min(1.0, t / float(self.life))
        _glow(p, 0, 0, 60 * S, _mix(self.c1, self.c2, 0.5), 70 * (1 - u))
        self._draw_parts(p)

    # ================================================================ pair: trail x trail
    def _init_sword_slash_clash(self):
        r = self.rng
        # two slash strokes: A sweeps down-right, B sweeps up-right, crossing at the origin
        self.state["cuts"] = [(self.c1, math.radians(-35 + r.uniform(-8, 8))),
                              (self.c2, math.radians(35 + r.uniform(-8, 8)))]
        for c, a in self.state["cuts"]:
            self._sparks(16, ang=a, spread=0.35, spd=(4.0, 12.0), life=(10, 22), col=c)
            self._sparks(10, ang=a + math.pi, spread=0.35, spd=(3.0, 9.0), life=(8, 18), col=c)
        self._sparks(10, ang=-math.pi / 2, spread=0.9, spd=(3.0, 8.0), life=(10, 20), grav=0.3)

    def _draw_sword_slash_clash(self, p):
        S, t = self.S, self.ft
        u = min(1.0, t / float(self.life))
        f = 1.0 - u
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        sweep = _ease_out(min(1.0, t / 5.0))
        for c, a in self.state["cuts"]:
            L = 95 * S
            ca, sa = math.cos(a), math.sin(a)
            # the stroke sweeps from its tail end through the origin to its head
            hx, hy = ca * L * (2 * sweep - 1), sa * L * (2 * sweep - 1)
            tx, ty = -ca * L, -sa * L
            _line(p, tx, ty, hx, hy, c, 120 * f, 8 * S * f + 1)
            _diamond(p, tx, ty, hx, hy, 3.2 * S * f, self._hotc(c, 0.6), 245 * f)
        fl = 1.0 if t < 3 else f
        _glow(p, 0, 0, 40 * S * fl, self.hot, 255 * fl * fl, 0.45)
        _star(p, 0, 0, 38 * S * fl, 26 * S * fl, self.hot, 255 * fl, 2.0 * S)
        r = 70 * S * _ease_out(min(1.0, t / 12.0))
        _split_ring(p, 0, 0, r, r * 0.6, 3 * S * f + 0.4, self._hotc(self.c1, 0.3), self._hotc(self.c2, 0.3), 200 * f)
        self._draw_parts(p)

    # ================================================================ pair: trail x trail (sword duel)
    def _init_sword_duel(self):
        self.state.update(pose=None, contact=None, cuts=[], flash=[], plan=None, i=0, f0=(0.0, 0.0), grind=0)

    def anchor_duel(self, pscale=1.0):
        """laser/clash.py: the duel is played by the two real fighters; it
        feeds their positions each tick (duel_frame)."""
        self.anchored = True
        self.S *= pscale

    def duel_frame(self, fr):
        """One tick of a duel_plan() frame, in world coordinates: the two
        fighters' positions, the blade contact (None = apart) and the event."""
        ax, ay = self._local(fr[0], fr[1])
        bx, by = self._local(fr[2], fr[3])
        con = None if fr[4] is None else self._local(fr[4][0], fr[4][1])
        self._duel_apply(ax, ay, bx, by, con, fr[5])

    def _duel_apply(self, ax, ay, bx, by, con, ev):
        st = self.state
        st["pose"] = (ax, ay, bx, by)
        st["contact"] = con
        if con is not None:
            st["f0"] = con
        if ev in ("strike", "bind", "big") and con is not None:
            self._duel_hit(con, ev == "big")
        elif ev == "grind" and con is not None:
            st["grind"] += 1
            if st["grind"] % 2 == 0:   # blades locked: sparks spray up off the bind
                self._sparks(4, x=con[0], y=con[1], ang=-math.pi / 2, spread=1.0, spd=(3.0, 8.0), life=(10, 18),
                             grav=0.35)
        elif ev == "release" and self.phase == "hold":
            self.release()

    def _duel_hit(self, con, big):
        """The blades meet at con: a cut from each fighter's hand through the
        contact, a glint, a ring and sparks."""
        st, r, S = self.state, self.rng, self.S
        x, y = con
        k = 1.7 if big else 1.0
        ax, ay, bx, by = st["pose"]
        for fx_, fy_, c in ((ax, ay, self.c1), (bx, by, self.c2)):
            hx, hy = fx_ + (x - fx_) * 0.35, fy_ + (y - fy_) * 0.35
            ex, ey = x + (x - hx) * 0.7, y + (y - hy) * 0.7
            st["cuts"].append([hx, hy, ex, ey, c, 0, k])
            a = math.atan2(ey - hy, ex - hx)
            self._sparks(7 * k, x=x, y=y, ang=a, spread=0.45, spd=(3.0, 10.0 * k), life=(8, 18), col=c)
        self.parts.append(_P("glint", x, y, 0, 0, 12 if big else 9, (5.5 if big else 3.8) * S,
                             self.c1 if r.random() < 0.5 else self.c2))
        self.parts.append(_P("ring", x, y, 0, 0, 16 if big else 13, (34 if big else 18) * S, self.c1, col2=self.c2))
        self._sparks(8 * k, x=x, y=y, spd=(3.0, 9.0 * k), life=(8, 16), size=(1.1, 2.0), drag=0.88)
        st["flash"].append([x, y, 0, 1.0 if big else 0.6])

    def _tick_sword_duel(self):
        st, S = self.state, self.S
        st["flash"] = [[x, y, a + 1, k] for x, y, a, k in st["flash"] if a + 1 < 10]
        st["cuts"] = [c[:5] + [c[5] + 1, c[6]] for c in st["cuts"] if c[5] + 1 < 9]
        if self.anchored or self.phase != "hold":
            return
        # F6 preview: no fighters, so it plays its own choreography with two
        # glowing stand-ins.
        if st["plan"] is None:
            reach = float(self.spec.get("reach", 34)) * S
            st["plan"] = duel_plan(self.rng, (-110 * S, 12 * S), (110 * S, -12 * S), (0.0, 0.0), reach,
                                   strikes=self.spec.get("strikes", (4, 7)), bind=float(self.spec.get("bind", 0.3)))
        plan, i = st["plan"], st["i"]
        if i >= len(plan):
            self.release()
            return
        fr = plan[i]
        st["i"] = i + 1
        prev = st["pose"]
        self._duel_apply(fr[0], fr[1], fr[2], fr[3], fr[4], fr[5])
        if prev is not None:
            for j, c in ((0, self.c1), (2, self.c2)):
                dx, dy = fr[j] - prev[j], fr[j + 1] - prev[j + 1]
                if dx * dx + dy * dy > 36:
                    self.parts.append(_P("dash", prev[j], prev[j + 1], dx, dy, 8, 1.9 * S, c))

    def _finale_sword_duel(self):
        x, y = self.state["f0"]
        self._sparks(56, x=x, y=y, spd=(4.0, 14.0), life=(16, 34), grav=0.15)
        self._sparks(12, x=x, y=y, kind="dot", spd=(1.0, 4.0), life=(20, 34), size=(2.0, 3.6), drag=0.95)

    def _duel_blade(self, p, fx_, fy_, con, c, sign):
        """A fighter's blade while the two are bound: from its hand, through
        the contact, crossing the other blade in an X."""
        S = self.S
        x, y = con
        d = math.hypot(x - fx_, y - fy_)
        if d < 1.0:
            return
        a = math.atan2(y - fy_, x - fx_) + sign * (0.32 + 0.04 * math.sin(self.t * 0.5))
        ux, uy = math.cos(a), math.sin(a)
        L = max(30 * S, min(90 * S, d * 1.25))
        hx, hy = x - ux * L * 0.62, y - uy * L * 0.62
        tx, ty = x + ux * L * 0.38, y + uy * L * 0.38
        _line(p, hx, hy, tx, ty, c, 110, 8 * S)
        _diamond(p, hx, hy, tx, ty, 2.4 * S, self._hotc(c, 0.7), 255)
        _line(p, hx, hy, tx, ty, self.hot, 220, 1.0 * S)

    def _draw_sword_duel(self, p):
        st, S = self.state, self.S
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        for x, y, a, k in st["flash"]:
            v = a / 10.0
            _glow(p, x, y, 36 * S * k * (0.5 + 0.5 * v), self.hot, 230 * (1 - v) * k)
        for hx, hy, ex, ey, c, a, k in st["cuts"]:
            f = 1.0 - a / 9.0
            sw = _ease_out(min(1.0, (a + 1) / 3.0))
            tx, ty = hx + (ex - hx) * sw, hy + (ey - hy) * sw
            _line(p, hx, hy, tx, ty, c, 120 * f, (7 * S * k) * f + 1)
            _diamond(p, hx, hy, tx, ty, 2.8 * S * k * f, self._hotc(c, 0.6), 245 * f)
        pose = st["pose"]
        if self.phase == "hold":
            if not self.anchored and pose is not None:     # preview stand-ins
                _glow(p, pose[0], pose[1], 14 * S, self.c1, 230)
                _glow(p, pose[2], pose[3], 14 * S, self.c2, 230)
            con = st["contact"]
            if con is not None and pose is not None:
                self._duel_blade(p, pose[0], pose[1], con, self.c1, 1)
                self._duel_blade(p, pose[2], pose[3], con, self.c2, -1)
                fl = 0.75 + 0.25 * math.sin(self.t * 2.3)
                _glow(p, con[0], con[1], 14 * S * fl, self.hot, 255, 0.5)
                _star(p, con[0], con[1], (24 + 8 * math.sin(self.t * 1.7)) * S, 11 * S * fl, self.hot, 230, 1.6 * S)
        else:
            t = self.ft
            u = min(1.0, t / float(self.life))
            f = 1.0 - u
            x, y = st["f0"]
            # the final cut runs across the line between the two fighters
            ang = 0.0
            if pose is not None:
                ang = math.atan2(pose[3] - pose[1], pose[2] - pose[0])
            p.save()
            p.translate(x, y)
            p.rotate(math.degrees(ang))
            L = 260 * S * _ease_out(min(1.0, t / 4.0))
            mix = _mix(self.c1, self.c2, 0.5)
            _diamond(p, 0, -L, 0, L, 9 * S * f, mix, 150 * f)
            _diamond(p, 0, -L, 0, L, 2.8 * S * f + 0.4, self.hot, 255 * f)
            r = 180 * S * _ease_out(u)
            _split_ring(p, 0, 0, r * 0.6, r, 6 * S * f + 0.6, self._hotc(self.c1, 0.4), self._hotc(self.c2, 0.4), 220 * f)
            p.restore()
            _glow(p, x, y, 80 * S * _ease_out(t / 6.0) * f + 1, self._hotc(mix, 0.45), 240 * f * f)
        self._draw_parts(p)

    # ================================================================ pair: crescent x crescent
    def _init_crescent_struggle(self):
        self.state.update(ripples=[], shake=(0.0, 0.0), split=0)

    def _tick_crescent_struggle(self):
        st, r, S = self.state, self.rng, self.S
        if self.phase != "hold":
            st["split"] += 1
            return
        st["shake"] = (r.uniform(-1.6, 1.6) * S, r.uniform(-1.6, 1.6) * S)
        if self.t % 14 == 0:
            st["ripples"].append(0)
        st["ripples"] = [a + 1 for a in st["ripples"] if a + 1 < 24]
        for _ in range(3):
            if r.random() < self.D:
                y = r.uniform(-30, 30) * S
                a = (-1 if y < 0 else 1) * math.pi / 2 + r.gauss(0, 0.5)
                v = r.uniform(3, 8) * S
                self.parts.append(_P("spark", 0, y, math.cos(a) * v, math.sin(a) * v, r.randint(10, 18),
                                     r.uniform(1.1, 2.0) * S, self.c1 if r.random() < 0.5 else self.c2, drag=0.92))

    def _finale_crescent_struggle(self):
        r, S = self.rng, self.S
        for i in range(int(10 * self.D)):
            side = -1 if i % 2 else 1
            a = (math.pi if side < 0 else 0.0) + r.uniform(-1.3, 1.3)
            v = r.uniform(3.0, 8.0) * S
            self.parts.append(_P("crescent", side * 10 * S, r.uniform(-30, 30) * S, math.cos(a) * v, math.sin(a) * v,
                                 r.randint(20, 32), r.uniform(7, 13) * S, self.c1 if side < 0 else self.c2,
                                 drag=0.94, rot=a, vr=r.uniform(-0.3, 0.3)))
        self._sparks(40, spd=(4.0, 12.0), life=(12, 26))

    def _draw_crescent_struggle(self, p):
        st, S = self.state, self.S
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        if self.phase == "hold":
            t = self.t
            p.save()
            p.translate(*st["shake"])
            for a in st["ripples"]:
                v = a / 24.0
                r = 30 * S + 90 * S * _ease_out(v)
                _split_ring(p, 0, 0, r * 0.3, r, 3 * S * (1 - v) + 0.4, self._hotc(self.c1, 0.3),
                            self._hotc(self.c2, 0.3), 190 * (1 - v))
            push = 2 * S * math.sin(t * 0.35)
            for c, sx in ((self.c1, -1), (self.c2, 1)):
                # each crescent bulges toward the other; they touch along x = 0
                R = 46 * S
                cx = sx * (R + 2 * S) + push * sx
                rect = QRectF(cx - R, -R, 2 * R, 2 * R)
                start = -55 if sx < 0 else 125   # Qt degrees: the 110° of arc facing the centre
                for w, k, a in ((11 * S, 0.0, 110), (4.5 * S, 0.6, 245)):
                    pen = QPen(_q(self._hotc(c, k), a), w)
                    pen.setCapStyle(Qt.RoundCap)
                    p.setPen(pen)
                    p.setBrush(Qt.NoBrush)
                    p.drawArc(rect, int(start * 16), int(110 * 16))
            fl = 0.7 + 0.3 * math.sin(t * 2.1)
            _diamond(p, 0, -34 * S, 0, 34 * S, 4 * S * fl, self.hot, 240)
            _glow(p, 0, 0, 30 * S * fl, self.hot, 220, 0.5)
            p.restore()
        else:
            t = self.ft
            u = min(1.0, t / float(self.life))
            f = 1.0 - u
            _glow(p, 0, 0, 80 * S * _ease_out(t / 6.0), self._hotc(_mix(self.c1, self.c2, 0.5), 0.4), 255 * f ** 1.5)
            r = 160 * S * _ease_out(u)
            _split_ring(p, 0, 0, r * 0.6, r, 6 * S * f + 0.6, self._hotc(self.c1, 0.4), self._hotc(self.c2, 0.4), 230 * f)
        self._draw_parts(p)

    # ================================================================ pair: sprite x sprite
    def _init_kunai_clash(self):
        r, S = self.rng, self.S
        self.parts.append(_P("glint", 0, 0, 0, 0, 12, 6.0 * S, self.c1))
        self.parts.append(_P("ring", 0, 0, 0, 0, 14, 22 * S, self.c1, col2=self.c2))
        for c, sx in ((self.c1, -1), (self.c2, 1)):
            a = (math.pi if sx < 0 else 0.0) + (-1 if sx < 0 else 1) * r.uniform(0.5, 1.1) * (1 if r.random() < 0.5 else -1)
            v = r.uniform(3.5, 6.0) * S
            self.parts.append(_P("kunai", sx * 6 * S, 0, math.cos(a) * v, math.sin(a) * v, r.randint(26, 34),
                                 11 * S, c, drag=0.95, grav=0.22, rot=r.uniform(0, TAU), vr=sx * r.uniform(0.35, 0.55)))
        self._sparks(18, spd=(3.0, 9.0), life=(8, 18), size=(1.0, 2.0), drag=0.9)

    def _draw_kunai_clash(self, p):
        S, t = self.S, self.ft
        p.setCompositionMode(QPainter.CompositionMode_Plus)
        if t < 6:
            _glow(p, 0, 0, 30 * S * (1 - t / 6.0), self.hot, 255 * (1 - t / 6.0), 0.45)
        self._draw_parts(p)


# ---------------------------------------------------------------- world API
def _smooth(u):
    return u * u * (3.0 - 2.0 * u)


def duel_plan(rng, a0, b0, c, reach, strikes=(4, 7), bind=0.3):
    """Choreography of a sword duel (sword_duel), one frame per tick:
    (ax, ay, bx, by, contact, event, swing).  a0 / b0 = where the two
    fighters start, c = where their blades first met, reach = how far each
    stands from the blade contact.  Each strike both dash in from opposite
    sides of a point near c, their blades meet there (event "strike", or
    "bind" then "grind" while they lock), and they spring apart; halfway
    through they circle to their own sides for a breath; the duel closes on
    one big clash at c ("big", then "release" = the finale) and both return
    to where they started.  swing (0..1, None = not swinging) drives the
    fighters' slash frames.  laser/clash.py uses it to move the real
    fighters; the F6 preview plays it with two stand-ins."""
    ux, uy = b0[0] - a0[0], b0[1] - a0[1]
    d = math.hypot(ux, uy)
    ux, uy = (ux / d, uy / d) if d > 1e-6 else (1.0, 0.0)
    vx, vy = -uy, ux
    R = max(40.0, reach * 1.9)
    A, B = [float(a0[0]), float(a0[1])], [float(b0[0]), float(b0[1])]
    out = []

    def move(ta, tb, n, ease=_ease_out, swing=False, ev=None):
        fa, fb = tuple(A), tuple(B)
        for i in range(1, n + 1):
            k = ease(i / float(n))
            A[0], A[1] = fa[0] + (ta[0] - fa[0]) * k, fa[1] + (ta[1] - fa[1]) * k
            B[0], B[1] = fb[0] + (tb[0] - fb[0]) * k, fb[1] + (tb[1] - fb[1]) * k
            out.append((A[0], A[1], B[0], B[1], None, ev if i == 1 else None, (i - 1) / float(n) if swing else None))

    def hold(n, contact, first=None, each=None):
        for i in range(n):
            out.append((A[0], A[1], B[0], B[1], contact, first if i == 0 else each, 0.999 if contact else None))

    def strike(P, dx, dy, n, kind):
        move((P[0] - dx * reach, P[1] - dy * reach), (P[0] + dx * reach, P[1] + dy * reach), n, swing=True)
        if kind == "strike":
            hold(2, P, "strike")
        else:
            hold(rng.randint(8, 12) if kind == "bind" else 10, P, kind, "grind")

    total = rng.randint(*strikes)
    first = max(1, total // 2)
    for burst, n_str in ((0, first), (1, total - first)):
        for _ in range(n_str):
            P = (c[0] + ux * rng.uniform(-0.6, 0.6) * R + vx * rng.uniform(-0.6, 0.6) * R,
                 c[1] + uy * rng.uniform(-0.6, 0.6) * R + vy * rng.uniform(-0.6, 0.6) * R)
            th = rng.uniform(-1.1, 1.1)
            dx, dy = ux * math.cos(th) - uy * math.sin(th), ux * math.sin(th) + uy * math.cos(th)
            strike(P, dx, dy, rng.randint(4, 6), "bind" if rng.random() < bind else "strike")
            back = reach + rng.uniform(22.0, 40.0)
            move((P[0] - dx * back, P[1] - dy * back), (P[0] + dx * back, P[1] + dy * back), rng.randint(4, 6))
            hold(rng.randint(1, 4), None)
        if burst == 0:
            # circle back to their own sides for a breath
            move((c[0] - ux * R + vx * rng.uniform(-0.7, 0.7) * R, c[1] - uy * R + vy * rng.uniform(-0.7, 0.7) * R),
                 (c[0] + ux * R + vx * rng.uniform(-0.7, 0.7) * R, c[1] + uy * R + vy * rng.uniform(-0.7, 0.7) * R),
                 10, ease=_smooth)
            hold(rng.randint(6, 12), None)
    strike((float(c[0]), float(c[1])), ux, uy, 6, "big")
    move(tuple(a0), tuple(b0), 12, ease=_smooth, ev="release")
    return out


def spawn(world, key, x, y, angle=0.0, c1=(90, 170, 255), c2=(255, 120, 60), scale=1.0, winner=0, hold=None,
          seed=None, density=1.0):
    """Start a clash explosion at (x, y).  angle = degrees from side A toward
    side B (screen coordinates, y down).  Returns the live ClashFX."""
    lst = getattr(world, "clash_fx", None)
    if lst is None:
        lst = world.clash_fx = []
    fx = ClashFX(key, x, y, angle, c1, c2, scale, winner, hold, seed, density)
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
