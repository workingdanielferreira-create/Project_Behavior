"""
World physics: Dust & Air (FX Studio's "World Physics" page).

Kicked-up dust, debris and displaced air that the ARENA makes when fighters
move, jump, get slammed, clash and blast.  Owned by the world, not by any
fighter: Solo and Battle run the very same code, once per tick, after both
sides have moved (World tick -> step), and it only ever READS the fighters
(positions, knockback, leaps).  Nothing here feeds back into combat.

Ground model (confirmed with Daniel 2026-10-31): the screen is a slope seen
from its foot.  The position-scale grid (config.POSITION_SCALE_*) already
says how big things are where: bottom-left is near (5x), top-right far (1x).
Every particle has a ground point (x, y) on screen and a height z above it,
drawn straight up the screen at (x, y - z).  Spreads along the ground
(rings, craters, wall jets) are ellipses whose height / width ratio is
ground.flat_near at the nearest spot and ground.flat_far at the farthest:
ROUNDER the farther away (the slope rises toward the line of sight).
Screen edges are the walls.

Engine (hybrid, Daniel's pick):
  * Rocks, pebbles, sparks are closed-form: their whole flight is fixed when
    they spawn and evaluated at draw time (no per-tick cost).
  * Fine dust is simulated in one capped pool.  Each tick a puff relaxes
    toward the local AIR velocity with its own response time tau:
        v = u + (v - u) * exp(-dt / tau)
    so in still air it is plain drag, and inside a blast, a wake or a jump
    column it rides the wind.
  * Air is a short list of analytic sources summed at each puff (no grid):
    Blast (Friedlander push then suck-back, front R ~ t^0.4), Wake (pocket
    of air dragged behind a fast mover + alternately shed curls), Column
    (air drawn up under a jumper), Jet (a ring of wind running out along
    the ground or a wall).
  * Effect size scales with the cube root of the event's energy.

Settings: characters/world_physics.json (format pb_world_physics) is shared
by every character; a character's FX pack may carry "world_physics" with
any of the sections below, which then replace the world's for the events
THAT fighter causes (dash, jump, sonic: the mover; slam: the one slammed;
clash: the first side; blast: the shot's owner).

Mirrored by tools/fx/studio/worldfx.js (FX Studio's preview);
tools/fx/check_parity.py checks DEFAULTS / RANGES / FORMAT agree.
"""
import math
import random

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF

from . import config
from .geometry import bilinear

FORMAT = "pb_world_physics"
FILE = "world_physics.json"     # in characters/
SECTIONS = ["ground", "dash", "jump", "slam", "clash", "blast", "sonic"]

# Every setting, with its default.  Numbers are clamped to RANGES; true /
# false are switches; "#rrggbb" strings are colours.  Speeds in px/s and
# sizes in px are at 100 % position scale.
DEFAULTS = {
    "ground": {"enabled": True, "flat_near": 0.25, "flat_far": 0.55, "max_dust": 420,
               "tau_ms": 140, "ink": "#1b1712"},
    "dash": {"enabled": True, "speed": 380, "rate": 40, "inherit": 40, "size": 100, "life_ms": 700,
             "start_burst": True, "wake": True, "wake_pct": 100, "curls": True, "grit": 6,
             "color": "#d9c4a3"},
    "jump": {"enabled": True, "dust": 14, "pebbles": 8, "ring": True, "column": True, "land": True,
             "hops": True, "size": 100, "color": "#d9c4a3"},
    "slam": {"enabled": True, "min_speed": 7, "launch": True, "skid": True, "crater": True, "wall": True,
             "dust": 22, "rocks": 10, "size": 100, "color": "#cdb391", "rock_color": "#7a6e62"},
    "clash": {"enabled": True, "sheet": True, "dust": 14, "sparks": 16, "ground_jet": True, "size": 100,
              "color": "#e6dccb", "spark_color": "#ffb347"},
    "blast": {"enabled": True, "min_damage": 4, "strength": 100, "suck_back": True, "reach": 80,
              "dust": 18, "ring": True, "size": 100, "color": "#d9c4a3"},
    "sonic": {"enabled": True, "mach": 1100, "knockback": False, "cone": True, "vapor": True,
              "boom": True, "sweep": True, "color": "#e8f2ff"},
}
RANGES = {
    "ground": {"flat_near": [0.05, 1.0], "flat_far": [0.05, 1.0], "max_dust": [0, 1500], "tau_ms": [20, 600]},
    "dash": {"speed": [50, 3000], "rate": [0, 200], "inherit": [0, 100], "size": [10, 400], "life_ms": [100, 3000],
             "wake_pct": [0, 300], "grit": [0, 60]},
    "jump": {"dust": [0, 80], "pebbles": [0, 40], "size": [10, 400]},
    "slam": {"min_speed": [0, 60], "dust": [0, 120], "rocks": [0, 40], "size": [10, 400]},
    "clash": {"dust": [0, 80], "sparks": [0, 80], "size": [10, 400]},
    "blast": {"min_damage": [0, 500], "strength": [0, 300], "reach": [20, 1200], "dust": [0, 120],
              "size": [10, 400]},
    "sonic": {"mach": [100, 6000]},
}

TICK_S = config.TICK_MS / 1000.0
MAX_SOURCES = 24
MAX_BURSTS = 40
MAX_RINGS = 40


def _hex(v, d):
    if isinstance(v, str) and len(v) == 7 and v[0] == "#":
        try:
            int(v[1:], 16)
            return v.lower()
        except ValueError:
            pass
    return d


def normalize_section(name, s):
    """One section with every key filled in and clamped, unknown keys dropped
    (FXK.WORLDFX.normalizeSection)."""
    s = s if isinstance(s, dict) else {}
    dflt = DEFAULTS[name]
    rng = RANGES.get(name, {})
    out = {}
    for k, d in dflt.items():
        v = s.get(k, d)
        if isinstance(d, bool):
            out[k] = bool(v)
        elif isinstance(d, str):
            out[k] = _hex(v, d)
        else:
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = float(d)
            if v != v:
                v = float(d)
            lo, hi = rng.get(k, [-1e9, 1e9])
            out[k] = max(float(lo), min(float(hi), v))
    return out


def normalize(c):
    """The whole world file: every section filled in."""
    c = c if isinstance(c, dict) else {}
    out = {"format": FORMAT}
    for name in SECTIONS:
        out[name] = normalize_section(name, c.get(name))
    return out


def normalize_override(c):
    """A character's override: only the sections it carries, each filled in."""
    c = c if isinstance(c, dict) else {}
    return {name: normalize_section(name, c[name]) for name in SECTIONS if isinstance(c.get(name), dict)}


WORLD = normalize({})


def load_world(root_dir):
    """Read characters/world_physics.json into WORLD (defaults when missing or
    unreadable).  Called at start-up and on reload (assets)."""
    import json
    import os
    global WORLD
    path = os.path.join(root_dir, "characters", FILE)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            obj = json.load(f)
    except (OSError, ValueError):
        WORLD = normalize({})
        return WORLD
    WORLD = normalize(obj if isinstance(obj, dict) and obj.get("format") == FORMAT else {})
    return WORLD


def cfg(fig, name):
    """Section `name` for events `fig` causes: its own override, else the world's."""
    if fig is not None:
        mode = getattr(fig, "mode", None)
        if mode is not None:
            ov = getattr(mode, "_wphys_cfg", None)
            if ov is None:
                ov = {}
                char = getattr(mode, "character", None)
                if char and char.get("_package"):
                    ov = normalize_override((char.get("_fxkit") or {}).get("world_physics"))
                try:
                    mode._wphys_cfg = ov
                except AttributeError:
                    pass
            s = ov.get(name)
            if s is not None:
                return s
    return WORLD[name]


# ---------------------------------------------------------------- perspective
_PS = (config.POSITION_SCALE_TOP_LEFT, config.POSITION_SCALE_TOP_RIGHT,
       config.POSITION_SCALE_BOTTOM_LEFT, config.POSITION_SCALE_BOTTOM_RIGHT)
_PS_LO, _PS_HI = min(_PS), max(_PS)
_SS = (config.SPEED_SCALE_TOP_LEFT, config.SPEED_SCALE_TOP_RIGHT,
       config.SPEED_SCALE_BOTTOM_LEFT, config.SPEED_SCALE_BOTTOM_RIGHT)


def _fr(x, y, sw, sh):
    return (max(0.0, min(1.0, x / sw)) if sw > 0 else 0.5,
            max(0.0, min(1.0, y / sh)) if sh > 0 else 0.5)


def pscale(x, y, sw, sh):
    """Drawn size at (x, y): combat.position_scale's grid."""
    if not config.POSITION_SCALE_ENABLED:
        return 1.0
    xf, yf = _fr(x, y, sw, sh)
    return bilinear(xf, yf, *_PS)


def sscale(x, y, sw, sh):
    """Pace at (x, y): combat.position_speed_scale's grid."""
    if not config.SPEED_SCALE_ENABLED:
        return 1.0
    xf, yf = _fr(x, y, sw, sh)
    return bilinear(xf, yf, *_SS)


def flat_at(ps, g):
    """Ground ellipse height / width at a spot drawn at size ps: flat_near at
    the nearest (largest) spot, flat_far at the farthest (smallest)."""
    if _PS_HI - _PS_LO < 1e-6:
        return g["flat_near"]
    f = max(0.0, min(1.0, (_PS_HI - ps) / (_PS_HI - _PS_LO)))
    return g["flat_near"] + (g["flat_far"] - g["flat_near"]) * f


def escale(e):
    """Effect size from energy: cube root (Hopkinson-Cranz), kept sane."""
    return max(0.45, min(2.6, max(0.0, e) ** (1.0 / 3.0)))


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


# ---------------------------------------------------------------- air sources
class Blast:
    """Friedlander blast: the front runs out at R = Rmax (t/T)^0.4; where it
    has passed, air moves radially with p = e^(-tau/ts) (1 - tau/ts): a hard
    push, then a long shallow pull back (suck=False drops the pull)."""
    __slots__ = ("x", "y", "age", "T", "ts", "rmax", "amp", "suck", "life", "flat")

    def __init__(self, x, y, s, ps, reach, strength, suck, flat):
        self.x, self.y, self.age = x, y, 0.0
        self.T = max(4.0, 0.32 * s / TICK_S)
        self.ts = max(2.0, 0.2 * s / TICK_S)
        self.rmax = max(10.0, reach * s * ps)
        self.amp = 4.0 * s * ps * strength
        self.suck = suck
        self.flat = max(0.05, flat)
        self.life = self.T + 6.0 * self.ts

    def bbox(self):
        r = self.rmax
        return self.x - r, self.y - r * self.flat, self.x + r, self.y + r * self.flat

    def air(self, x, y, z):
        dx, dy = x - self.x, (y - self.y) / self.flat
        r = math.sqrt(dx * dx + dy * dy)
        if r >= self.rmax:
            return None
        ta = self.T * (r / self.rmax) ** 2.5
        tau = self.age - ta
        if tau < 0.0:
            return None
        q = tau / self.ts
        p = math.exp(-q) * (1.0 - q)
        if p < 0.0 and not self.suck:
            return None
        a = self.amp * p * (1.0 - r / self.rmax) / max(r, 4.0)
        return dx * a, dy * a * self.flat, (0.35 * a * r if p > 0 else 0.0)


class Wake:
    """A pocket of air dragged along behind a fast mover; refreshed every tick
    it keeps moving fast, fading once it stops."""
    __slots__ = ("x", "y", "vx", "vy", "d", "k", "age", "life", "live")

    def __init__(self, x, y, d):
        self.x, self.y, self.vx, self.vy, self.d = x, y, 0.0, 0.0, max(6.0, d)
        self.k, self.age, self.life, self.live = 0.0, 0.0, 1e9, True

    def bbox(self):
        r = self.d * 4.0
        return self.x - r, self.y - r * 1.5, self.x + r, self.y + r

    def air(self, x, y, z):
        sp = math.hypot(self.vx, self.vy)
        if sp < 0.01 or self.k < 0.01:
            return None
        cx = self.x - self.vx / sp * self.d * 0.8
        cy = self.y - self.vy / sp * self.d * 0.8
        dx, dy = x - cx, y - cy
        q = (dx * dx + dy * dy + z * z) / (self.d * self.d * 1.6)
        if q > 9.0:
            return None
        w = self.k * math.exp(-q)
        return self.vx * w, self.vy * w, 0.0


class Curl:
    """A shed vortex: air swirls round it, the curl widening and weakening as
    it takes in air."""
    __slots__ = ("x", "y", "g", "rc", "age", "life")

    def __init__(self, x, y, g, rc):
        self.x, self.y, self.g, self.rc, self.age = x, y, g, max(4.0, rc), 0.0
        self.life = 0.6 / TICK_S

    def bbox(self):
        r = 4.0 * self.rc * (1.0 + self.age / 18.0)
        return self.x - r, self.y - r, self.x + r, self.y + r * 3.0

    def air(self, x, y, z):
        rc = self.rc * (1.0 + self.age / 18.0)
        dx, dy = x - self.x, (y - z) - self.y
        r2 = dx * dx + dy * dy
        if r2 > 16.0 * rc * rc:
            return None
        f = self.g * (1.0 - self.age / self.life) * math.exp(-r2 / (2.0 * rc * rc)) / rc
        # tangential (-dy, dx) on screen: screen x drives the ground x,
        # screen y (down) is minus the height
        return -dy * f, 0.0, -dx * f


class Column:
    """Air drawn up behind a jumper and in from the sides."""
    __slots__ = ("x", "y", "w", "r", "age", "life", "flat")

    def __init__(self, x, y, w, r, flat):
        self.x, self.y, self.w, self.r, self.age, self.flat = x, y, w, max(6.0, r), 0.0, max(0.05, flat)
        self.life = 26.0

    def bbox(self):
        r = 3.0 * self.r
        return self.x - r, self.y - r * self.flat, self.x + r, self.y + r * self.flat

    def air(self, x, y, z):
        dx, dy = x - self.x, (y - self.y) / self.flat
        q = (dx * dx + dy * dy) / (self.r * self.r)
        if q > 9.0:
            return None
        k = self.w * (1.0 - self.age / self.life) * math.exp(-q)
        return -dx / self.r * k * 0.3, -dy * self.flat / self.r * k * 0.3, k


class Jet:
    """A ring of wind running out from (x, y): along the ground (axis None),
    or along a wall (axis "v": a left / right wall, "h": top / bottom)."""
    __slots__ = ("x", "y", "c", "j", "wd", "age", "life", "flat", "axis", "out")

    def __init__(self, x, y, j, c, wd, flat, axis=None, out=(0.0, 0.0)):
        self.x, self.y, self.j, self.c, self.wd = x, y, j, c, max(4.0, wd)
        self.age, self.life, self.flat, self.axis, self.out = 0.0, 28.0, max(0.05, flat), axis, out

    def bbox(self):
        r = self.age * self.c + 3.0 * self.wd + 2.0
        if self.axis == "v":
            return self.x - 3.0 * self.wd, self.y - r, self.x + 3.0 * self.wd, self.y + r * 3.0
        if self.axis == "h":
            return self.x - r, self.y - 3.0 * self.wd, self.x + r, self.y + 3.0 * self.wd
        return self.x - r, self.y - r * self.flat, self.x + r, self.y + r * self.flat

    def air(self, x, y, z):
        fall = 1.0
        if self.axis == "v":
            dx, dy = 0.0, (y - z) - self.y
            q0 = (x - self.x) / (3.0 * self.wd)
            fall = math.exp(-q0 * q0)
        elif self.axis == "h":
            dx, dy = x - self.x, 0.0
            q0 = (y - self.y) / (3.0 * self.wd)
            fall = math.exp(-q0 * q0)
        else:
            dx, dy = x - self.x, (y - self.y) / self.flat
        r = math.sqrt(dx * dx + dy * dy)
        front = self.age * self.c
        q = (r - front) / self.wd
        if q * q > 9.0 or r < 0.5:
            return None
        if fall < 0.01:
            return None
        k = self.j * fall * math.exp(-self.age / 10.0) * math.exp(-q * q) / r
        ux, uy = dx * k, dy * k * (self.flat if self.axis is None else 1.0)
        ox, oy = self.out
        w = self.j * fall * 0.6 * math.exp(-self.age / 10.0) * math.exp(-q * q)
        if self.axis == "v":
            return ox * w, 0.0, -uy
        if self.axis == "h":
            return ux, oy * w, 0.0
        return ux, uy, 0.0


# ---------------------------------------------------------------- closed-form debris
class Burst:
    """Rocks / pebbles / sparks: every piece's flight fixed at spawn.
    pieces: (cos az, sin az * flat, h speed, v speed, size, spin, rot0)."""
    __slots__ = ("x", "y", "age", "ss", "kind", "pieces", "g", "k", "e", "life", "col", "ps", "floor")

    def __init__(self, x, y, ps, ss, kind, pieces, g, k, e, life, col):
        self.x, self.y, self.ps, self.ss = x, y, ps, ss
        self.age, self.kind, self.pieces = 0.0, kind, pieces
        self.g, self.k, self.e, self.life, self.col = g, k, e, life, col
        self.floor = None      # screen-plane sparks: they die on this screen y

    def at(self, pc, t):
        """(x, y screen, z) of piece pc at age t, or None once a spark lands."""
        ca, sa, h, v, _s, _sp, _r = pc
        g, k, e = self.g, self.k, self.e
        dist = h * (1.0 - k ** t) / (1.0 - k) if k < 0.9999 else h * t
        t1 = 2.0 * v / g if g > 0 else 1e9
        if t <= t1:
            z = v * t - 0.5 * g * t * t
        else:
            if self.kind == "spark":
                return None
            d1 = h * (1.0 - k ** t1) / (1.0 - k) if k < 0.9999 else h * t1
            dist = d1 + 0.45 * (dist - d1)
            v2 = v * e
            t2 = 2.0 * v2 / g if g > 0 else 0.0
            tt = t - t1
            z = v2 * tt - 0.5 * g * tt * tt if tt <= t2 else 0.0
        return self.x + ca * dist, self.y + sa * dist, max(0.0, z)


class Ring:
    """kind: "ground" (flattened, spreading along the ground), "wall" (a dust
    plane on a screen edge: edge l/r/t/b), "boom" (round, round the body)."""
    __slots__ = ("kind", "x", "y", "age", "life", "r", "flat", "edge", "col", "w")

    def __init__(self, kind, x, y, life, r, flat=1.0, edge=None, col=(255, 255, 255), w=6.0):
        self.kind, self.x, self.y, self.age, self.life = kind, x, y, 0.0, max(2.0, life)
        self.r, self.flat, self.edge, self.col, self.w = r, flat, edge, col, w


# ---------------------------------------------------------------- per-fighter tracking
class _Track:
    __slots__ = ("px", "py", "fast", "slow", "burst", "acc", "gacc", "wake", "shed", "sign",
                 "bouncing", "v0", "leap", "leap_n", "leap_t", "hop", "mach", "seen", "nx", "ny",
                 "sp", "head", "sweep")

    def __init__(self, x, y):
        self.px, self.py = x, y
        self.fast = False
        self.slow = 99
        self.burst = 0
        self.acc = self.gacc = 0.0
        self.wake = None
        self.shed = 0.0
        self.sign = 1.0
        self.bouncing = False
        self.v0 = 0.0
        self.leap = None
        self.leap_n = 0
        self.leap_t = 1
        self.hop = False
        self.mach = 0.0
        self.seen = 0
        self.nx = self.ny = 0.0
        self.sp = 0.0
        self.head = (x, y)
        self.sweep = 0


# Events noted from inside a side's pass (motion.check_walls): consumed by
# step() after both sides moved.
_WALLS = []


def note_wall(fig, edge, speed):
    """A knockback slide hit a screen edge (motion.check_walls)."""
    if len(_WALLS) < 32:
        _WALLS.append((fig, edge, fig.x, fig.y, float(speed)))


def state(world):
    st = getattr(world, "worldfx", None)
    if st is None:
        st = world.worldfx = WorldFx()
    return st


def step(world):
    """One world tick: read the fighters, spawn what they kicked up, move the
    dust.  Called once per tick by the overlay after both sides moved."""
    state(world).step(world)


def note_clash(world, x, y, angle, kb, owners):
    """Two opposing effects met (laser/clash.py): throw the splash sheet."""
    try:
        state(world).clash(world, x, y, angle, kb, owners)
    except Exception:
        pass


def paint_ground(p, world):
    st = getattr(world, "worldfx", None)
    if st is not None and WORLD["ground"]["enabled"]:
        st.paint_ground(p, world)


def paint_air(p, world):
    st = getattr(world, "worldfx", None)
    if st is not None and WORLD["ground"]["enabled"]:
        st.paint_air(p, world)


# ---------------------------------------------------------------- the world's dust & air
class WorldFx:
    def __init__(self):
        self.dust = []      # [x, y, z, vx, vy, vz, age, life, r0, tau, rgb, grav]
        self.src = []
        self.bursts = []
        self.rings = []
        self.later = []     # [due tick, fn, args]
        self.tracks = {}
        self.ki = {}        # id(inst) -> [inst, seen detonation indices, touched]
        self.t = 0
        self.rng = random.Random(0x5EED)
        self.sw = self.sh = 1

    # ---- helpers
    def ps(self, x, y):
        return pscale(x, y, self.sw, self.sh)

    def ss(self, x, y):
        return sscale(x, y, self.sw, self.sh)

    def flat(self, x, y):
        return flat_at(self.ps(x, y), WORLD["ground"])

    def add_src(self, s):
        if len(self.src) >= MAX_SOURCES:
            self.src.pop(0)
        self.src.append(s)
        return s

    def add_ring(self, r):
        if len(self.rings) >= MAX_RINGS:
            self.rings.pop(0)
        self.rings.append(r)

    def puff(self, x, y, z, vx, vy, vz, life, r0, rgb, tau=None, grav=-0.012):
        g = WORLD["ground"]
        tau = (g["tau_ms"] / config.TICK_MS) if tau is None else tau
        self.dust.append([x, y, z, vx, vy, vz, 0.0, max(4.0, life), r0, max(1.0, tau), rgb, grav])

    def puffs(self, x, y, n, sp, rgb, size, life_ms, az=None, spread=360.0, up=(0.2, 1.0), r0=6.0, flat=None):
        """n dust puffs from ground point (x, y), sp px/tick (at 100 %)."""
        if n <= 0:
            return
        ps = self.ps(x, y)
        fl = self.flat(x, y) if flat is None else flat
        rnd = self.rng.random
        for _ in range(int(n)):
            a = math.radians((az if az is not None else 0.0) + (rnd() - 0.5) * spread)
            s = sp * (0.4 + 0.6 * rnd()) * ps
            self.puff(x + (rnd() - 0.5) * 6 * ps, y + (rnd() - 0.5) * 3 * ps, rnd() * 3 * ps,
                      math.cos(a) * s, math.sin(a) * s * fl, (up[0] + (up[1] - up[0]) * rnd()) * ps,
                      life_ms / config.TICK_MS * (0.7 + 0.6 * rnd()),
                      r0 * size * (0.7 + 0.6 * rnd()), rgb)

    def debris(self, x, y, kind, n, s, rgb, az=None, spread=360.0, elev=(30.0, 62.0), spd=(3.0, 9.0),
               size=(2.0, 5.0), pi_scale=False):
        """A closed-form burst.  pi_scale: speed falls with launch distance u
        (u^-1.1) and the angle flattens farther out (62 - 27 u)."""
        if n <= 0:
            return
        if len(self.bursts) >= MAX_BURSTS:
            self.bursts.pop(0)
        ps, ss = self.ps(x, y), self.ss(x, y)
        fl = self.flat(x, y)
        rnd = self.rng.random
        pieces = []
        for _ in range(int(n)):
            a = math.radians((az if az is not None else 0.0) + (rnd() - 0.5) * spread)
            if pi_scale:
                u = 0.25 + 0.75 * rnd()
                sp = min(spd[1] * 1.6, spd[0] * u ** -1.1) * math.sqrt(s)
                el = math.radians(62.0 - 27.0 * u)
            else:
                sp = (spd[0] + (spd[1] - spd[0]) * rnd()) * math.sqrt(s)
                el = math.radians(elev[0] + (elev[1] - elev[0]) * rnd())
            pieces.append((math.cos(a), math.sin(a) * fl, sp * math.cos(el) * ps, sp * math.sin(el) * ps,
                           (size[0] + (size[1] - size[0]) * rnd()) * ps, (rnd() - 0.5) * 0.5, rnd() * 6.28))
        if kind == "spark":
            self.bursts.append(Burst(x, y, ps, ss, kind, pieces, 0.22 * ps, 0.974, 0.0, 34.0, rgb))
        else:
            self.bursts.append(Burst(x, y, ps, ss, kind, pieces, 0.34 * ps, 0.994 if kind == "rock" else 0.98,
                                     0.35, 95.0 if kind == "rock" else 60.0, rgb))

    # ---- body helpers
    @staticmethod
    def foot(fig, ps):
        h = 24.0
        try:
            fr = fig._current_frame()
            if fr is not None:
                h = float(fr.height())
        except Exception:
            pass
        return fig.x, fig.y + h * 0.46 * ps, h * 0.46 * ps

    # ---- tick
    def step(self, world):
        self.sw, self.sh = max(1, int(world.screen_w)), max(1, int(world.screen_h))
        self.t += 1
        g = WORLD["ground"]
        if not g["enabled"]:
            if self.dust or self.src or self.bursts or self.rings:
                self.__init__()
            del _WALLS[:]
            return
        # Delayed events (the clash sheet reaching the floor).
        if self.later:
            due = [e for e in self.later if e[0] <= self.t]
            self.later = [e for e in self.later if e[0] > self.t]
            for _, fn, args in due:
                try:
                    fn(*args)
                except Exception:
                    pass
        for fig in list(world.all_figures()):
            try:
                self.observe(world, fig)
            except Exception:
                pass
        for fig, edge, x, y, sp in _WALLS:
            try:
                self.wall(fig, edge, x, y, sp)
            except Exception:
                pass
        del _WALLS[:]
        try:
            self.scan_blasts(world)
        except Exception:
            pass
        for k in [k for k, tr in self.tracks.items() if tr.seen != self.t]:
            del self.tracks[k]
        self.move()

    def observe(self, world, fig):
        tr = self.tracks.get(id(fig))
        ps = self.ps(fig.x, fig.y)
        fx, fy, hh = self.foot(fig, ps)
        # A leap: the fighter's y carries the arc; the ground is under it.
        act = getattr(fig, "act", None)
        lp = getattr(act, "leap", None) if act is not None else None
        z = 0.0
        if lp is not None and not lp.get("done") and lp.get("h", 0) > 0:
            u = 0.0
            if tr is not None and tr.leap is lp:
                u = min(1.0, (tr.leap_n + 1) / float(max(1, tr.leap_t)))
            z = lp["h"] * 4.0 * u * (1.0 - u)
            fy += z
        if tr is None:
            tr = self.tracks[id(fig)] = _Track(fx, fy)
        tr.seen = self.t
        dx, dy = fx - tr.px, fy - tr.py
        tr.px, tr.py = fx, fy
        jump = math.hypot(dx, dy)
        if jump > config.ARENA_OVAL_TELEPORT_PX:    # blink / teleport / respawn: no momentum
            dx = dy = 0.0
            jump = 0.0
        sp_s = jump / TICK_S           # on-screen px/s (position-scaled, Daniel's pick)
        tr.sp = sp_s
        if jump > 0.01:
            tr.nx, tr.ny = dx / jump, dy / jump
        tr.head = (fig.x, fig.y)
        m = fig.motion
        self.leap_events(fig, tr, lp, fx, fy, ps)
        self.hop_events(fig, tr, fx, fy, ps)
        self.knock_events(fig, tr, m, fx, fy, ps, jump)
        self.dash_events(fig, tr, fx, fy, ps, z, dx, dy, sp_s, hh)
        self.sonic_events(fig, tr, m, fx, fy, ps, sp_s, hh)

    def leap_events(self, fig, tr, lp, fx, fy, ps):
        c = cfg(fig, "jump")
        live = lp is not None and not lp.get("done") and lp.get("h", 0) > 0
        if live and tr.leap is not lp:
            tr.leap, tr.leap_n = lp, 0
            tr.leap_t = max(1, int(round((lp["t1"] - lp["t0"]) / config.TICK_MS)))
            if c["enabled"]:
                self.takeoff(fig, fx, fy, ps, 1.0, c)
        elif live:
            tr.leap_n += 1
        elif tr.leap is not None:
            land = tr.leap
            tr.leap = None
            if c["enabled"] and c["land"]:
                self.landing(fig, land.get("ex", fx), fy, ps, 1.0, c)

    def hop_events(self, fig, tr, fx, fy, ps):
        hop = getattr(fig.combat, "hop_ticks", 0) > 0
        c = cfg(fig, "jump")
        if hop and not tr.hop and c["enabled"] and c["hops"]:
            self.takeoff(fig, fx, fy, ps, 0.5, c)
        elif tr.hop and not hop and c["enabled"] and c["hops"] and c["land"]:
            self.landing(fig, fx, fy, ps, 0.5, c)
        tr.hop = hop

    def takeoff(self, fig, x, y, ps, k, c):
        sz = c["size"] / 100.0 * k
        rgb = _rgb(c["color"])
        fl = self.flat(x, y)
        if c["ring"]:
            self.add_ring(Ring("ground", x, y, 16, 46 * sz * ps, fl, col=(255, 255, 255), w=6 * ps * sz))
        self.puffs(x, y, c["dust"] * k, 2.6, rgb, sz, 650, up=(0.05, 0.4), r0=6.0)
        self.debris(x, y, "pebble", int(c["pebbles"] * k), sz, rgb, elev=(55.0, 75.0), spd=(4.0, 8.0),
                    size=(1.5, 3.5))
        self.add_src(Jet(x, y, 1.6 * ps * sz, 2.2 * ps, 10 * ps, fl))
        if c["column"]:
            self.add_src(Column(x, y, 1.4 * ps * sz, 26 * ps * sz, fl))

    def landing(self, fig, x, y, ps, k, c):
        sz = c["size"] / 100.0 * k * 0.6
        rgb = _rgb(c["color"])
        fl = self.flat(x, y)
        if c["ring"]:
            self.add_ring(Ring("ground", x, y, 12, 34 * sz * ps, fl, w=4 * ps * sz))
        self.puffs(x, y, c["dust"] * k * 0.6, 2.2, rgb, sz, 520, up=(0.02, 0.25), r0=6.0)
        self.add_src(Jet(x, y, 1.0 * ps * sz, 2.0 * ps, 8 * ps, fl))

    def knock_events(self, fig, tr, m, fx, fy, ps, jump):
        c = cfg(fig, "slam")
        b = bool(m.bouncing)
        if b and not tr.bouncing:
            tr.v0 = math.hypot(m.bounce_vx, m.bounce_vy)
            if c["enabled"] and c["launch"] and tr.v0 >= c["min_speed"]:
                s = escale((tr.v0 / 15.0) ** 2) * c["size"] / 100.0
                rgb = _rgb(c["color"])
                fl = self.flat(fx, fy)
                back = math.degrees(math.atan2(-m.bounce_vy, -m.bounce_vx))
                self.add_ring(Ring("ground", fx, fy, 14, 40 * s * ps, fl, w=5 * ps * s))
                self.puffs(fx, fy, c["dust"] * 0.5, 2.0, rgb, s, 700, up=(0.05, 0.5))
                self.puffs(fx, fy, c["dust"] * 0.5, 4.0 * s, rgb, s, 800, az=back, spread=70.0, up=(0.1, 0.8))
                self.debris(fx, fy, "rock", int(c["rocks"] * 0.4), s, _rgb(c["rock_color"]), az=back,
                            spread=90.0, elev=(35.0, 60.0), spd=(3.0, 7.0), size=(2.0, 4.5))
        elif b and c["enabled"] and c["skid"] and jump > 2.5 and self.t % 2 == 0:
            rgb = _rgb(c["color"])
            back = math.degrees(math.atan2(-m.bounce_vy, -m.bounce_vx))
            self.puffs(fx, fy, 1, 1.2, rgb, c["size"] / 100.0 * min(1.6, jump / 8.0), 600, az=back,
                       spread=80.0, up=(0.05, 0.3))
        elif not b and tr.bouncing:
            # The slide stopped: a heavy one (2x the minimum) leaves a crater.
            if c["enabled"] and c["crater"] and tr.v0 >= 2.0 * max(1.0, c["min_speed"]):
                self.crater(fig, fx, fy, ps, escale((tr.v0 / 15.0) ** 2) * c["size"] / 100.0, c)
        tr.bouncing = b

    def crater(self, fig, x, y, ps, s, c):
        rgb = _rgb(c["color"])
        fl = self.flat(x, y)
        R = 44 * s * ps
        self.add_ring(Ring("ground", x, y, 22, R * 1.4, fl, w=7 * ps * s))
        self.add_ring(Ring("crater", x, y, 70, R * 0.8, fl, col=_rgb(c["rock_color"]), w=3 * ps))
        # dust walls rising round the rim
        rnd = self.rng.random
        n = int(c["dust"])
        for i in range(n):
            a = 2 * math.pi * i / max(1, n) + rnd() * 0.3
            px, py = x + math.cos(a) * R * 0.7, y + math.sin(a) * R * 0.7 * fl
            self.puff(px, py, 0.0, math.cos(a) * 1.2 * ps, math.sin(a) * 1.2 * ps * fl,
                      (0.8 + 1.4 * rnd()) * ps * s, (600 + 500 * rnd()) / config.TICK_MS,
                      6.5 * s * (0.7 + 0.6 * rnd()), rgb, grav=0.02)
        self.debris(x, y, "rock", int(c["rocks"]), s, _rgb(c["rock_color"]), pi_scale=True, spd=(3.5, 10.0),
                    size=(2.0, 5.0))
        self.add_src(Jet(x, y, 2.2 * ps * s, 2.6 * ps, 12 * ps, fl))

    def wall(self, fig, edge, x, y, sp):
        c = cfg(fig, "slam")
        if not (c["enabled"] and c["wall"]) or sp < c["min_speed"] * 0.6:
            return
        ps = self.ps(x, y)
        s = escale((sp / 15.0) ** 2) * c["size"] / 100.0
        rgb = _rgb(c["color"])
        ox, oy = {"l": (1.0, 0.0), "r": (-1.0, 0.0), "t": (0.0, 1.0), "b": (0.0, -1.0)}[edge]
        wx = 0.0 if edge == "l" else (self.sw if edge == "r" else x)
        wy = 0.0 if edge == "t" else (self.sh if edge == "b" else y)
        R = 70 * s * ps
        self.add_ring(Ring("wall", wx, wy, 26, R, edge=edge, col=rgb, w=5 * ps * s))
        az = math.degrees(math.atan2(oy, ox))
        rnd = self.rng.random
        for _ in range(int(c["dust"])):
            if edge in ("l", "r"):
                along = (rnd() - 0.5) * 2.0
                vx, vy = ox * (0.6 + 1.8 * rnd()) * ps * s, 0.0
                vz = along * 3.2 * ps * s
                px, py = wx + ox * 4 * ps, wy
            else:
                along = (rnd() - 0.5) * 2.0
                vx, vy = along * 3.2 * ps * s, oy * (0.6 + 1.8 * rnd()) * ps * s
                vz = 0.0
                px, py = wx, wy + oy * 4 * ps
            self.puff(px, py, 8 * ps * rnd(), vx, vy, vz,
                      (600 + 500 * rnd()) / config.TICK_MS, 6.0 * s * (0.7 + 0.6 * rnd()), rgb)
        self.debris(wx + ox * 4 * ps, wy + oy * 4 * ps, "rock", int(c["rocks"] * 0.7), s, _rgb(c["rock_color"]),
                    az=az, spread=120.0, elev=(15.0, 55.0), spd=(3.0, 8.0), size=(2.0, 4.5))
        self.add_src(Jet(wx, wy, 2.0 * ps * s, 2.8 * ps, 12 * ps, 1.0,
                         axis="v" if edge in ("l", "r") else "h", out=(ox, oy)))

    def dash_events(self, fig, tr, fx, fy, ps, z, dx, dy, sp_s, hh):
        c = cfg(fig, "dash")
        if not c["enabled"]:
            if tr.wake is not None:
                tr.wake.live = False
                tr.wake = None
            tr.fast = False
            return
        thr = c["speed"]
        fast = sp_s >= thr and z < 2.0
        rgb = _rgb(c["color"])
        sz = c["size"] / 100.0
        vx, vy = dx, dy      # px/tick on screen
        if fast:
            if not tr.fast and tr.slow > 6 and c["start_burst"]:
                tr.burst = 4
            tr.slow = 0
            k = c["inherit"] / 100.0
            rate = c["rate"] * min(3.0, sp_s / thr) * (3.0 if tr.burst > 0 else 1.0)
            tr.acc += rate * TICK_S
            rnd = self.rng.random
            while tr.acc >= 1.0:
                tr.acc -= 1.0
                spread = 1.2 * ps
                self.puff(fx - vx * rnd() + (rnd() - 0.5) * 6 * ps, fy + (rnd() - 0.5) * 3 * ps, rnd() * 2 * ps,
                          vx * k + (rnd() - 0.5) * spread, vy * k + (rnd() - 0.5) * spread * 0.5,
                          (0.15 + 0.5 * rnd()) * ps * (1.5 if tr.burst > 0 else 1.0),
                          c["life_ms"] / config.TICK_MS * (0.7 + 0.6 * rnd()),
                          (5.0 if tr.burst <= 0 else 6.5) * sz * (0.7 + 0.6 * rnd()), rgb)
            tr.gacc += c["grit"] * min(3.0, sp_s / thr) * TICK_S
            if tr.gacc >= 1.0:
                n = int(tr.gacc)
                tr.gacc -= n
                az = math.degrees(math.atan2(-vy, -vx))
                self.debris(fx, fy, "pebble", n, sz, rgb, az=az, spread=70.0, elev=(25.0, 55.0),
                            spd=(2.0, 5.0), size=(1.0, 2.2))
            if tr.burst > 0:
                tr.burst -= 1
            if c["wake"]:
                if tr.wake is None or not tr.wake.live or tr.wake not in self.src:
                    tr.wake = self.add_src(Wake(fx, fy, hh * 1.2))
                w = tr.wake
                w.x, w.y, w.vx, w.vy, w.d = fx, fy, vx, vy, max(6.0, hh * 1.2)
                w.k = min(0.6 * c["wake_pct"] / 100.0, w.k + 0.15)
                if c["curls"]:
                    sp_t = math.hypot(vx, vy)
                    D = max(6.0, hh * 1.6)
                    tr.shed += 0.2 * sp_t / D
                    if tr.shed >= 1.0:
                        tr.shed -= 1.0
                        tr.sign = -tr.sign
                        nx, ny = vx / max(0.01, sp_t), vy / max(0.01, sp_t)
                        px, py = -ny, nx
                        self.add_src(Curl(fx - nx * D * 0.8 + px * tr.sign * D * 0.3,
                                          fy - D * 0.3 - ny * D * 0.8 + py * tr.sign * D * 0.3,
                                          tr.sign * 0.9 * sp_t * w.k, D * 0.35))
        else:
            tr.slow += 1
            tr.burst = 0
            if tr.wake is not None:
                tr.wake.live = False
                tr.wake = None
        tr.fast = fast

    def sonic_events(self, fig, tr, m, fx, fy, ps, sp_s, hh):
        c = cfg(fig, "sonic")
        prev = tr.mach
        if not c["enabled"] or ((m.bouncing or m.bounce_ending) and not c["knockback"]):
            tr.mach = 0.0
            return
        M = sp_s / max(1.0, c["mach"])
        tr.mach = M
        if M >= 1.0 and prev < 1.0 and c["boom"]:
            self.add_ring(Ring("boom", fig.x, fig.y, 18, 46 * ps, 1.0, col=_rgb(c["color"]), w=5 * ps))
        if M >= 1.0 and c["sweep"]:
            tr.sweep += 1
            if tr.sweep % 4 == 0:
                # Where the cone meets the floor: push out, pull back, release.
                back = hh * math.sqrt(max(0.0, M * M - 1.0))
                bx, by = fx - tr.nx * back, fy - tr.ny * back
                self.add_src(Blast(bx, by, 0.7, ps, 40.0, 0.5, True, self.flat(bx, by)))
                if self.rng.random() < 0.5:
                    self.puffs(bx, by, 2, 1.0, _rgb(WORLD["dash"]["color"]), 0.8, 600, up=(0.05, 0.3))
        else:
            tr.sweep = 0

    # ---- clash / blast
    def clash(self, world, x, y, angle, kb, owners):
        self.sw, self.sh = max(1, int(world.screen_w)), max(1, int(world.screen_h))
        own = [o for o in owners if o is not None]
        c = cfg(own[0] if own else None, "clash")
        if not (c["enabled"] and WORLD["ground"]["enabled"]):
            return
        ps = self.ps(x, y)
        s = escale(max(0.05, kb / 100.0)) * c["size"] / 100.0
        rgb = _rgb(c["color"])
        perp = angle + 90.0
        gy = None
        for o in own:
            try:
                gy0 = self.foot(o, self.ps(o.x, o.y))[1]
            except Exception:
                continue
            gy = gy0 if gy is None else max(gy, gy0)
        z0 = max(0.0, gy - y) if gy is not None else 0.0
        floor = gy if gy is not None else y
        if c["sheet"]:
            rnd = self.rng.random
            for i in range(int(c["dust"])):
                sgn = 1.0 if i % 2 == 0 else -1.0
                a = math.radians(perp + (rnd() - 0.5) * 30.0)
                sp = (2.0 + 3.5 * rnd()) * ps * s
                # the sheet: sideways to the hit; screen-up is height
                ux, uy = math.cos(a) * sp * sgn, math.sin(a) * sp * sgn
                self.puff(x, floor, z0, ux, 0.0, -uy, (450 + 450 * rnd()) / config.TICK_MS,
                          5.0 * s * (0.7 + 0.6 * rnd()), rgb, grav=0.0)
        self.sparks2d(x, y, perp, int(c["sparks"]), s, _rgb(c["spark_color"]), floor)
        self.add_ring(Ring("boom", x, y, 12, 36 * s * ps, 1.0, col=(255, 255, 255), w=4 * ps))
        if c["ground_jet"]:
            if gy is not None and gy > y + 2:
                delay = max(1, int((gy - y) / max(1.0, 4.5 * ps * s)))
                self.later.append([self.t + delay, self._clash_floor, (x, gy, s, c)])

    def _clash_floor(self, x, y, s, c):
        ps = self.ps(x, y)
        fl = self.flat(x, y)
        self.add_ring(Ring("ground", x, y, 18, 50 * s * ps, fl, w=5 * ps * s))
        self.add_src(Jet(x, y, 2.0 * ps * s, 3.0 * ps, 10 * ps, fl))
        self.puffs(x, y, int(c["dust"] * 0.8), 3.2 * s, _rgb(c["color"]), s, 700, up=(0.02, 0.3))

    def sparks2d(self, x, y, az, n, s, rgb, floor=None):
        """Sparks thrown in the screen plane both ways along az (a clash)."""
        if n <= 0:
            return
        if len(self.bursts) >= MAX_BURSTS:
            self.bursts.pop(0)
        ps, ss = self.ps(x, y), self.ss(x, y)
        rnd = self.rng.random
        pieces = []
        for i in range(n):
            sgn = 1.0 if i % 2 == 0 else -1.0
            a = math.radians(az + (rnd() - 0.5) * 50.0)
            sp = (5.0 + 6.0 * rnd()) * math.sqrt(s) * ps
            # screen x -> ground x; screen y -> height (z), so it arcs down
            pieces.append((1.0, 0.0, math.cos(a) * sp * sgn, -math.sin(a) * sp * sgn, 1.0, 0.0, 0.0))
        b = Burst(x, y, ps, ss, "spark", pieces, 0.22 * ps, 0.974, 0.0, 20.0, rgb)
        b.e = -1.0      # mark: z may go negative (it is a screen-plane spray)
        b.floor = floor
        self.bursts.append(b)

    def scan_blasts(self, world):
        for fig in world.all_figures():
            drv = getattr(fig, "fx", None)
            if drv is None:
                continue
            c = cfg(fig, "blast")
            try:
                players = [drv.player, drv.clane[0]] + [ln[0] for ln in drv.rlanes] + drv.stack_players()
            except Exception:
                continue
            for pl in players:
                for inst in pl.insts:
                    ki = getattr(inst, "tq_ki", None)
                    if not ki:
                        continue
                    rec = self.ki.get(id(inst))
                    if rec is None or rec[0] is not inst:
                        rec = self.ki[id(inst)] = [inst, set(), 0]
                    rec[2] = self.t
                    for i, v in list(ki.items()):
                        if i in rec[1]:
                            continue
                        rec[1].add(i)
                        if len(v) >= 4 and v[3]:
                            continue      # a split orb vanishing: no detonation
                        if not c["enabled"]:
                            continue
                        dmg = float(((inst.fx or {}).get("battle") or {}).get("damage") or 1.0)
                        if dmg >= c["min_damage"]:
                            self.blast(v[1], v[2], dmg, c)
        for k in [k for k, r in self.ki.items() if r[2] != self.t]:
            del self.ki[k]

    def blast(self, x, y, dmg, c):
        ps = self.ps(x, y)
        s = escale(dmg / 10.0) * c["size"] / 100.0
        fl = self.flat(x, y)
        self.add_src(Blast(x, y, s, ps, c["reach"], c["strength"] / 100.0, c["suck_back"], fl))
        if c["ring"]:
            self.add_ring(Ring("ground", x, y, 20, c["reach"] * 0.6 * s * ps, fl, w=4 * ps * s))
        self.puffs(x, y, int(c["dust"] * min(2.0, s)), 1.5, _rgb(c["color"]), s, 900, up=(0.05, 0.6))

    # ---- integrate
    def move(self):
        g = WORLD["ground"]
        for s in self.src:
            s.age += 1.0
        self.src = [s for s in self.src if s.age < s.life and not (isinstance(s, Wake) and not s.live and s.k < 0.02)]
        for s in self.src:
            if isinstance(s, Wake) and not s.live:
                s.k *= 0.85
        for b in self.bursts:
            b.age += b.ss
        self.bursts = [b for b in self.bursts if b.age < b.life]
        for r in self.rings:
            r.age += 1.0
        self.rings = [r for r in self.rings if r.age < r.life]
        cap = int(g["max_dust"])
        if len(self.dust) > cap:
            del self.dust[:len(self.dust) - cap]
        # Each source's reach this tick (screen box; dust above the ground is
        # tested at its ground point, so boxes reach up for lifted dust).
        src = [(s,) + s.bbox() for s in self.src]
        sw, sh = self.sw, self.sh
        exp = math.exp
        live = []
        for d in self.dust:
            x, y, z = d[0], d[1], d[2]
            ss = sscale(x, y, sw, sh)
            ux = uy = uz = 0.0
            for s, x0, y0, x1, y1 in src:
                if x < x0 or x > x1 or y < y0 or y > y1:
                    continue
                a = s.air(x, y, z)
                if a is not None:
                    ux += a[0]
                    uy += a[1]
                    uz += a[2]
            k = exp(-ss / d[9])
            d[3] = ux + (d[3] - ux) * k
            d[4] = uy + (d[4] - uy) * k
            d[5] = uz + (d[5] - uz) * k - d[11] * ss
            d[0] = x + d[3] * ss
            d[1] = y + d[4] * ss
            z = z + d[5] * ss
            if z < 0.0:
                z = 0.0
                if d[5] < 0.0:
                    d[5] = 0.0
                d[3] *= 0.9
                d[4] *= 0.9
            d[2] = z
            d[6] += ss
            if d[6] < d[7] and -50 < d[0] < sw + 50 and -50 < d[1] < sh + 50:
                live.append(d)
        self.dust = live

    # ---- paint
    def paint_ground(self, p, world):
        if not (self.rings or self.dust or self.bursts):
            return
        g = WORLD["ground"]
        ink = QColor(g["ink"])
        p.save()
        p.setBrush(Qt.NoBrush)
        for r in self.rings:
            if r.kind in ("ground", "crater", "wall"):
                self._ring(p, r, ink)
        for b in self.bursts:
            if b.kind != "spark":
                self._rocks(p, b, ink)
        self._dust(p, ink)
        p.restore()

    def paint_air(self, p, world):
        has_sonic = any(tr.mach >= 0.9 for tr in self.tracks.values())
        if not (self.rings or self.bursts or has_sonic):
            return
        p.save()
        ink = QColor(WORLD["ground"]["ink"])
        for r in self.rings:
            if r.kind == "boom":
                self._ring(p, r, ink)
        sparks = [b for b in self.bursts if b.kind == "spark"]
        if sparks:
            p.setCompositionMode(QPainter.CompositionMode_Plus)
            for b in sparks:
                self._sparks(p, b)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        if has_sonic:
            for fid, tr in self.tracks.items():
                if tr.mach >= 0.9:
                    self._sonic(p, tr)
        p.restore()

    def _ring(self, p, r, ink):
        u = r.age / r.life
        grow = 1.0 - (1.0 - u) ** 3
        w = max(1.0, r.w * (1.0 - u))
        if r.kind == "crater":
            # a dark scorched dish that stays a while, fading in steps
            a = int(150 * (1.0 - math.floor(u * 4) / 4.0))
            col = QColor(*r.col, max(0, a))
            p.setPen(QPen(col, max(1.0, r.w)))
            rx = r.r
            p.drawEllipse(QRectF(r.x - rx, r.y - rx * r.flat, 2 * rx, 2 * rx * r.flat))
            p.setPen(QPen(QColor(0, 0, 0, max(0, a // 2)), max(1.0, r.w * 2.5)))
            rx *= 0.6
            p.drawEllipse(QRectF(r.x - rx, r.y - rx * r.flat, 2 * rx, 2 * rx * r.flat))
            return
        rad = r.r * (0.25 + 0.75 * grow)
        if r.kind == "wall":
            if r.edge in ("l", "r"):
                rx, ry = rad * 0.16, rad
            else:
                rx, ry = rad, rad * 0.16
            rect = QRectF(r.x - rx, r.y - ry, 2 * rx, 2 * ry)
            a = int(230 * (1.0 - u))
            p.setPen(QPen(ink, w + 3))
            p.setBrush(QColor(*r.col, a))
            p.drawEllipse(rect)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, a), w))
            p.drawEllipse(rect)
            return
        fl = r.flat if r.kind == "ground" else 1.0
        rect = QRectF(r.x - rad, r.y - rad * fl, 2 * rad, 2 * rad * fl)
        a = int(255 * (1.0 - u * u))
        inkc = QColor(ink)
        inkc.setAlpha(a)
        p.setPen(QPen(inkc, w + 3))
        p.drawEllipse(rect)
        p.setPen(QPen(QColor(*r.col, a), w))
        p.drawEllipse(rect)

    def _rocks(self, p, b, ink):
        col = QColor(*b.col)
        lit = QColor(min(255, b.col[0] + 60), min(255, b.col[1] + 60), min(255, b.col[2] + 60))
        fade = 1.0 if b.age < b.life * 0.75 else max(0.0, (b.life - b.age) / (b.life * 0.25))
        if fade <= 0.0:
            return
        p.setOpacity(fade)
        pen = QPen(ink, 1.2)
        for pc in b.pieces:
            at = b.at(pc, b.age)
            if at is None:
                continue
            x, y, z = at
            sy = y - z
            s = pc[4] * (1.0 if b.kind == "rock" else 0.7)
            rot = pc[6] + pc[5] * b.age if z > 0.0 else pc[6]
            pts = []
            for i in range(4):
                a = rot + i * 1.5708 + (0.25 if i % 2 else -0.1)
                rr = s * (1.0 if i % 2 == 0 else 0.8)
                pts.append(QPointF(x + math.cos(a) * rr, sy + math.sin(a) * rr))
            p.setPen(pen)
            p.setBrush(col)
            p.drawPolygon(QPolygonF(pts))
            p.setPen(Qt.NoPen)
            p.setBrush(lit)
            p.drawPolygon(QPolygonF([pts[0], pts[1], QPointF(x, sy)]))
        p.setOpacity(1.0)
        p.setBrush(Qt.NoBrush)

    def _sparks(self, p, b):
        glow = QColor(*b.col, 140)
        for pc in b.pieces:
            if b.e < 0:      # screen-plane spray: z is just "up the screen"
                ca, sa, h, v, _s, _sp, _r = pc
                t = b.age
                k = b.k
                def pos(tt):
                    d = h * (1.0 - k ** tt) / (1.0 - k)
                    zz = v * (1.0 - k ** tt) / (1.0 - k) - 0.5 * b.g * tt * tt
                    return b.x + d, b.y - zz
                if t > 20:
                    continue
                x1, y1 = pos(t)
                x0, y0 = pos(max(0.0, t - 2.0))
                if b.floor is not None and y0 > b.floor:
                    continue          # it hit the floor
                if b.floor is not None and y1 > b.floor:
                    y1 = b.floor
            else:
                a1 = b.at(pc, b.age)
                a0 = b.at(pc, max(0.0, b.age - 2.0))
                if a1 is None or a0 is None:
                    continue
                x1, y1 = a1[0], a1[1] - a1[2]
                x0, y0 = a0[0], a0[1] - a0[2]
            w = max(1.0, 3.0 * b.ps * 0.5)
            p.setPen(QPen(glow, w * 2.2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
            p.setPen(QPen(QColor(255, 255, 255, 230), w * 0.7, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

    def _sonic(self, p, tr):
        M = tr.mach
        x, y = tr.head
        nx, ny = tr.nx, tr.ny
        if nx == 0.0 and ny == 0.0:
            return
        ps = self.ps(x, y)
        tip = (x + nx * 14 * ps, y + ny * 14 * ps)
        if 0.9 <= M < 1.25 and WORLD["sonic"]["vapor"]:
            # flickering vapour collar just behind the nose
            a = int(60 + 90 * self.rng.random())
            p.save()
            p.translate(x - nx * 4 * ps, y - ny * 4 * ps)
            p.rotate(math.degrees(math.atan2(ny, nx)))
            p.setPen(QPen(QColor(255, 255, 255, a // 2), 1.0))
            p.setBrush(QColor(235, 245, 255, a))
            p.drawEllipse(QRectF(-5 * ps, -16 * ps, 10 * ps, 32 * ps))
            p.restore()
        if M >= 1.0 and WORLD["sonic"]["cone"]:
            mu = math.asin(min(1.0, 1.0 / M))
            L = 90 * ps
            back = math.atan2(-ny, -nx)
            col = QColor(WORLD["sonic"]["color"])
            for sgn in (-1.0, 1.0):
                a = back + sgn * mu
                ex, ey = tip[0] + math.cos(a) * L, tip[1] + math.sin(a) * L
                # schlieren pair: a dark line beside a light one
                p.setPen(QPen(QColor(0, 0, 0, 150), 3.0 * max(1.0, ps * 0.6)))
                p.drawLine(QPointF(*tip), QPointF(ex, ey))
                ox, oy = -math.sin(a) * 2.0 * sgn, math.cos(a) * 2.0 * sgn
                col.setAlpha(210)
                p.setPen(QPen(col, 1.5 * max(1.0, ps * 0.6)))
                p.drawLine(QPointF(tip[0] + ox, tip[1] + oy), QPointF(ex + ox, ey + oy))

    # ---- cel dust
    def _dust(self, p, ink):
        if not self.dust:
            return
        sw, sh = self.sw, self.sh
        items = []
        for d in self.dust:
            u = d[6] / d[7]
            # grow to 2x over the first 60 %, then shrink away in 3 snapped steps
            if u < 0.6:
                gr = 1.0 + (1.0 - (1.0 - u / 0.6) ** 2)
            else:
                gr = 2.0 * (1.0 - math.floor((u - 0.6) / 0.4 * 3.0 + 1.0) / 4.0)
            r = d[8] * gr * pscale(d[0], d[1], sw, sh) * 0.5
            if r < 1.0:
                continue
            items.append((int(d[0]), int(d[1] - d[2]), min(60, int(r + 0.5)), d[10]))
        if not items:
            return
        inkrgb = (ink.red(), ink.green(), ink.blue())
        # Pass 1: every ink outline; pass 2: every fill, so overlapping puffs
        # merge into one outlined cloud.
        for x, y, r, rgb in items:
            pm = _outline_sprite(r, inkrgb)
            p.drawPixmap(x - r - 2, y - r - 2, pm)
        for x, y, r, rgb in items:
            pm = _fill_sprite(r, rgb)
            p.drawPixmap(x - r, y - r, pm)


_SPRITES = {}


def _outline_sprite(r, rgb):
    key = ("o", r, rgb)
    pm = _SPRITES.get(key)
    if pm is None:
        n = 2 * r + 4
        pm = QPixmap(n, n)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing)
        q.setPen(Qt.NoPen)
        q.setBrush(QColor(*rgb))
        q.drawEllipse(QRectF(0.5, 0.5, n - 1, n - 1))
        q.end()
        _SPRITES[key] = pm
    return pm


def _fill_sprite(r, rgb):
    key = ("f", r, rgb)
    pm = _SPRITES.get(key)
    if pm is None:
        n = 2 * r
        pm = QPixmap(max(1, n), max(1, n))
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing)
        q.setPen(Qt.NoPen)
        sh = tuple(int(c * 0.7) for c in rgb)
        lt = tuple(int(c + (255 - c) * 0.5) for c in rgb)
        q.setBrush(QColor(*sh))          # shadow (lower right)
        q.drawEllipse(QRectF(0, 0, n, n))
        q.setBrush(QColor(*rgb))         # base, lit from the upper left
        q.drawEllipse(QRectF(0, 0, n * 0.86, n * 0.86))
        q.setBrush(QColor(*lt))          # light
        q.drawEllipse(QRectF(n * 0.14, n * 0.12, n * 0.4, n * 0.34))
        q.end()
        _SPRITES[key] = pm
    if len(_SPRITES) > 1200:
        _SPRITES.clear()
    return pm
