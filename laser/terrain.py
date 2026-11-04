"""
Destructible terrain: rock pillars and resting rubble (FX Studio "Dust & Air",
sections "pillars" and "rubble" of characters/world_physics.json).

Pillars
  Rock columns kept around the fight: when a round starts `count` of them
  rise at random spots within `radius_px` of the fighters' centre (the world
  anchor while anchor scaling is on), never on a fighter (clear_px) or on
  each other (gap_px).  When one breaks, a new one rises after respawn_s,
  so the arena steadily holds `count`.
  They are REAL obstacles, for both sides, Solo and Battle alike:
    * projectiles (built-in bullets, crescents, travelling FX, beams, gun /
      ki rounds) are stopped at their source;
    * fighters can't walk / slide through: they are pushed out, and a very
      subtle repel slides them away from the pillar's centre;
    * melee FX / built-in slashes and blasts that reach a pillar hit it.
  A hit BREAKS the pillar outright when any one of its speed (px/tick),
  FX knockback or FX damage meets that threshold (the hit then carries on:
  a projectile flies on, a fighter keeps sliding).  Anything under every
  threshold is blocked and chips the pillar's HP (chip_pct of its damage;
  a body bump chips body_chip); at 0 HP it crumbles.
  The AI does not know about pillars: decisions are unchanged, pillars only
  act physically (like the screen walls).

Rubble
  Rocks thrown by Dust & Air (slams, craters, walls, pillar breaks, the
  triggers below) land and lie on the ground for rest_s, then fade.
  Boulders: big chunks thrown high by heavy events — a hit whose knockback
  slide starts at hit_knockback px/tick or more, a heavy hit (hit_damage HP
  or more in one tick), a fighter moving at speed px/tick or more (with a
  per-fighter cooldown).  Knockback / heavy hits also crater.

2.5D look
  Each pillar is a small low-poly rock MESH (its own random shape, `facets`
  sides) drawn with an oblique 2.5D projection that keeps its on-screen
  height = the collision height.  The view turns with the pillar's place:
    yaw   = view_yaw x clamp((x - anchor x) / (view_reach_frac x width))
            -> straight on at the world anchor (the fighters' centre), and
               the side facing the fight turns into view as it moves away;
               it is one continuous rotation of a real shape, so crossing
               the anchor line has no seam or flip to hide.
    pitch = pitch_top (top of the screen) .. pitch_bottom (bottom): low on
            screen you look down on a big top face, higher up less of it,
            never the underside.
  Flat cel shading per facet (light from the top-left), ink silhouette.

World-owned, run once per tick by the overlay before worldfx.step (after
both sides moved); painted under the fighters (rubble, pillars behind a
fighter) and over them (pillars in front of a fighter).
"""

import math
import random

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF, QTransform

from . import config
from . import worldfx
from . import worldscale

# F12 see-through boulders (World.boulders_ghost): pillar opacity while on.
GHOST_ALPHA = 0.20
# Opacity of a fighter's tinted silhouette seen through a pillar.
SILHOUETTE_ALPHA = 0.80

TICK_S = config.TICK_MS / 1000.0
MAX_TRIES = 40


def _wf():
    return worldfx.WORLD


def _rgb(h):
    return worldfx._rgb(h)


def _ticks(sec):
    return max(1, int(round(float(sec) / TICK_S)))


def _seg_dist(a, b):
    from . import fxkit
    return fxkit.seg_seg_dist(a, b)


# ---- 2.5D rock mesh
_LIGHT = (-0.55, -0.45, 0.70)          # from the top-left, a little in front
_LN = math.sqrt(sum(c * c for c in _LIGHT))
_LIGHT = tuple(c / _LN for c in _LIGHT)


def _newell(pts):
    nx = ny = nz = 0.0
    m = len(pts)
    for i in range(m):
        x0, y0, z0 = pts[i]
        x1, y1, z1 = pts[(i + 1) % m]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return nx, ny, nz


def rock_mesh(seed, n):
    """A low-poly rock in unit space: X / Y across (radius ~1), Z up 0..~1.
    Returns (verts, faces); faces = (vertex indices, tone), wound so that
    Newell's normal points OUT of the rock.  No bottom face."""
    rng = random.Random(seed)
    n = max(5, min(12, int(n)))
    a0 = rng.uniform(0.0, 2.0 * math.pi)
    angs = [a0 + (i + rng.uniform(-0.28, 0.28)) * 2.0 * math.pi / n for i in range(n)]
    # Chunky: near-vertical sides, a bevel ring, then a broad faceted top.
    levels = ((0.0, 1.0), (rng.uniform(0.40, 0.60), rng.uniform(0.90, 1.0)),
              (rng.uniform(0.80, 0.88), rng.uniform(0.80, 0.92)),
              (rng.uniform(0.93, 0.98), rng.uniform(0.50, 0.66)))
    verts, rings = [], []
    for z, rf in levels:
        ring = []
        for a in angs:
            r = rf * rng.uniform(0.82, 1.12)
            a2 = a + rng.uniform(-0.12, 0.12)
            ring.append(len(verts))
            verts.append((math.cos(a2) * r, math.sin(a2) * r, z + (rng.uniform(-0.04, 0.04) if z > 0.0 else 0.0)))
        rings.append(ring)
    # Slanted, slightly off-centre peak.
    top = len(verts)
    verts.append((rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25), rng.uniform(0.99, 1.04)))
    faces = []
    for k in range(len(rings) - 1):
        lo, hi = rings[k], rings[k + 1]
        for j in range(n):
            j2 = (j + 1) % n
            faces.append([lo[j], lo[j2], hi[j2], hi[j]])
    last = rings[-1]
    for j in range(n):
        faces.append([last[j], last[(j + 1) % n], top])
    out = []
    for f in faces:
        pts = [verts[i] for i in f]
        nx, ny, nz = _newell(pts)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        cz = sum(p[2] for p in pts) / len(pts)
        if nx * cx + ny * cy + nz * (cz - 0.45) < 0.0:
            f = list(reversed(f))
        out.append((tuple(f), rng.uniform(0.9, 1.06)))
    return verts, out


class _Gust:
    """Dust & Air source: a pocket of air (radius r, flattened by the ground
    tilt) blowing along angle a at v px/tick, travelling with its own air and
    easing off over its life.  Carries a broken pillar's smoke away from the hit."""
    __slots__ = ("x", "y", "cx", "cy", "v", "r", "flat", "age", "life")

    def __init__(self, x, y, a, v, r, flat):
        self.x, self.y = x, y
        self.cx, self.cy = math.cos(a), math.sin(a)
        self.v, self.r, self.flat = v, max(6.0, r), max(0.05, flat)
        self.age, self.life = 0.0, 0.9 / TICK_S

    def _at(self):
        d = self.v * self.age * 0.6
        return self.x + self.cx * d, self.y + self.cy * d * self.flat

    def bbox(self):
        x, y = self._at()
        r = 2.0 * self.r
        return x - r, y - r * self.flat - 3.0 * self.r, x + r, y + r * self.flat

    def air(self, x, y, z):
        gx, gy = self._at()
        dx, dy = (x - gx) / self.r, (y - gy) / (self.r * self.flat)
        q = dx * dx + dy * dy
        if q > 4.0:
            return None
        w = self.v * (1.0 - self.age / self.life) * math.exp(-q)
        return self.cx * w, self.cy * w * self.flat, 0.0


class Pillar:
    __slots__ = ("x", "y", "hp", "hp0", "age", "rise_t", "flash", "ps", "jag", "cracks", "seen",
                 "seed", "_mesh")

    def __init__(self, x, y, hp, rise_t, rng):
        self.x, self.y = float(x), float(y)
        self.hp = self.hp0 = float(hp)
        self.age = 0
        self.rise_t = max(1, int(rise_t))
        self.flash = 0
        self.ps = 1.0
        # Outline jitter: left side, jagged top, right side (fractions of hw).
        self.jag = ([rng.uniform(-1, 1) for _ in range(6)], [rng.uniform(0.2, 1.0) for _ in range(3)],
                    [rng.uniform(-1, 1) for _ in range(6)])
        # Crack polylines in unit pillar space (u across -1..1, v up 0..1).
        cracks = []
        for _ in range(5):
            u, v = rng.uniform(-0.6, 0.6), rng.uniform(0.2, 0.9)
            pts = [(u, v)]
            for _ in range(3):
                u = max(-0.9, min(0.9, u + rng.uniform(-0.35, 0.35)))
                v = max(0.02, min(0.98, v + rng.uniform(-0.22, 0.1)))
                pts.append((u, v))
            cracks.append(pts)
        self.cracks = cracks
        self.seen = set()       # ids of melee / blast sources that already hit
        self.seed = rng.random()
        self._mesh = None       # (facets, verts, faces), built on first paint

    def mesh(self, n):
        n = int(n)
        if self._mesh is None or self._mesh[0] != n:
            self._mesh = (n,) + rock_mesh(self.seed, n)
        return self._mesh[1], self._mesh[2]

    def rise(self):
        f = min(1.0, self.age / float(self.rise_t))
        return 1.0 - (1.0 - f) ** 3

    def dims(self, P):
        """(half width, height) drawn now (px)."""
        return P["width"] * 0.5 * self.ps, P["height"] * self.ps * self.rise()

    def axis(self, P):
        """(x0, y0, x1, y1, half width): the pillar as a fat segment."""
        hw, h = self.dims(P)
        return (self.x, self.y - max(1.0, h), self.x, self.y, hw)


class Terrain:
    def __init__(self):
        self.pillars = []
        self.rubble = []       # [x, y, size, rot, rgb, age, life]
        self.pits = []         # craters: [x, y, rx, flat, rgb, age, life, rim, fade ticks]
        # Ground marks (worldfx.scan_ground_fx): beam trenches / crescent
        # streaks, each {"pts": [[x, y, age], ...], "kind", "w", "life",
        # "fade", "rgb"}; open ones (still being laid) by their source key.
        self.marks = []
        self.mark_open = {}
        # Rolling world: the roll velocity now (px/tick) and the next tick a
        # pillar may rise off the far side.
        self.roll_v = (0.0, 0.0)
        self.roll_next = 0
        self.filled = False
        self.next_spawn = 0
        self.t = 0
        self.rng = random.Random(0xB0A1D)
        self.sw = self.sh = 1
        self.track = {}        # id(fig) -> [x, y, hp, bouncing, last boulder tick]
        self.hit_ids = set()   # projectiles already handled this tick
        self.world = None

    # ---- spawning
    def _centre(self, figs):
        if worldscale._A is not None:
            return worldscale._A[0], worldscale._A[1]
        return (sum(f.x for f in figs) / len(figs), sum(f.y for f in figs) / len(figs))

    def _place(self, figs, P):
        cx, cy = self._centre(figs)
        R = P["radius_px"]
        rnd = self.rng.random
        for _ in range(MAX_TRIES):
            a = rnd() * 2 * math.pi
            r = R * math.sqrt(rnd())
            x = cx + math.cos(a) * r
            y = cy + math.sin(a) * r
            ps = worldfx.pscale(x, y, self.sw, self.sh)
            hw = P["width"] * 0.5 * ps
            if x < hw + 20 or x > self.sw - hw - 20 or y < self.sh * 0.12 or y > self.sh - 14:
                continue
            if any(math.hypot(f.x - x, f.y - y) < P["clear_px"] for f in figs):
                continue
            if any(math.hypot(p.x - x, p.y - y) < P["gap_px"] for p in self.pillars):
                continue
            return x, y
        return None

    def _spawn(self, figs, P):
        at = self._place(figs, P)
        if at is None:
            return False
        p = Pillar(at[0], at[1], P["hp"], _ticks(P["rise_ms"] / 1000.0), self.rng)
        p.ps = worldfx.pscale(p.x, p.y, self.sw, self.sh)
        self.pillars.append(p)
        self._rise_fx(p, P)
        return True

    def _rise_fx(self, p, P):
        wf = worldfx.state(self.world)
        if not _wf()["ground"]["enabled"]:
            return
        c = _wf()["slam"]
        wf.use(None, c)
        s = max(0.5, P["width"] / 20.0)
        wf.puffs(p.x, p.y, 10, 1.6, _rgb(P["color"]), s, 800, up=(0.1, 0.9))
        wf.debris(p.x, p.y, "rock", 5, s, _rgb(P["color"]), elev=(55.0, 80.0), spd=(2.5, 6.0), size=(2.0, 4.0))

    # ---- breaking
    def _break(self, p, P, ax=None):
        if p not in self.pillars:
            return
        self.pillars.remove(p)
        self.next_spawn = max(self.next_spawn, self.t + _ticks(P["respawn_s"]))
        if not _wf()["ground"]["enabled"]:
            return
        wf = worldfx.state(self.world)
        c = _wf()["slam"]
        wf.use(None, c)
        hw, h = P["width"] * 0.5 * p.ps, P["height"] * p.ps * p.rise()
        rgb = _rgb(P["color"])
        s = max(0.6, P["width"] / 18.0)
        fl = max(0.2, worldfx.flat_at(p.ps, _wf()["ground"]))
        # The crater it leaves: its own footprint, laid flat on the ground.
        self._add_pit(p.x, p.y, hw * 1.25, fl, rgb)
        # Break smoke: small puffs from all over the collapsing column (not
        # one width-scaled disc), drifting away from the hit (ax) in a ~90 deg cone.
        rnd = self.rng.random
        psz = max(0.8, min(2.2, P["width"] / 60.0))
        for _ in range(14):
            pa, pr = rnd() * 2 * math.pi, math.sqrt(rnd())
            a = math.radians(ax + (rnd() - 0.5) * 90.0) if ax is not None else rnd() * 2 * math.pi
            sp = 2.4 * (0.5 + 0.5 * rnd()) * p.ps
            wf.puff(p.x + math.cos(pa) * hw * pr, p.y + math.sin(pa) * hw * pr * fl, rnd() * h * 0.7,
                    math.cos(a) * sp, math.sin(a) * sp * fl, (0.1 + 0.5 * rnd()) * p.ps,
                    1100.0 / config.TICK_MS * (0.7 + 0.6 * rnd()), 6.0 * psz * (0.7 + 0.6 * rnd()), rgb)
        if ax is not None:
            # The dust otherwise settles into still air at once: a gust
            # carries it on, away from the hit.
            wf.add_src(_Gust(p.x, p.y, math.radians(ax), 1.8 * p.ps, max(hw * 1.6, 30.0 * p.ps), fl))
        # The column comes down in chunks from its whole height.
        n = int(P["rubble"])
        for i in range(max(1, n // 3)):
            yy = p.y - h * (i + 0.5) / max(1, n // 3) * 0.2
            wf.debris(p.x, yy, "rock", 3, s, rgb, az=ax, spread=360.0 if ax is None else 140.0,
                      elev=(20.0, 70.0), spd=(2.0, 6.0), size=(2.5, 5.5))
        b = int(P["boulders"])
        if b > 0:
            R = _wf()["rubble"]
            wf.debris(p.x, p.y, "rock", b, s, rgb, az=ax, spread=360.0 if ax is None else 120.0,
                      elev=(45.0, 72.0), spd=(2.5, 5.5), size=(R["boulder_min"], R["boulder_max"]))

    def _chip_fx(self, p, P, x, y):
        if not _wf()["ground"]["enabled"]:
            return
        wf = worldfx.state(self.world)
        wf.use(None, _wf()["slam"])
        wf.debris(x, y, "rock", 3, 0.6, _rgb(P["color"]), elev=(10.0, 50.0), spd=(2.0, 5.0), size=(1.5, 3.0))

    def hit(self, p, P, dmg=0.0, kb=0.0, spd=0.0, x=None, y=None, body=False, ax=None):
        """A hit reaches pillar p.  True = it broke on a threshold (the hit
        passes); False = blocked (chip damage; it may crumble at 0 HP)."""
        if dmg >= P["break_damage"] or kb >= P["break_knockback"] or spd >= P["break_speed"]:
            self._break(p, P, ax)
            return True
        p.hp -= (P["body_chip"] if body else dmg * P["chip_pct"] / 100.0)
        p.flash = 6
        if x is not None and not body:
            self._chip_fx(p, P, x, y)
        if p.hp <= 0.0:
            self._break(p, P, ax)
        return False

    # ---- per tick
    def step(self, world):
        self.world = world
        self.sw, self.sh = max(1, int(world.screen_w)), max(1, int(world.screen_h))
        self.t += 1
        P = _wf()["pillars"]
        figs = [f for f in world.all_figures() if getattr(f.transform, "init", True)]
        if not P["enabled"] or not _wf()["ground"]["enabled"]:
            self.pillars = []
            self.filled = False
        else:
            if figs:
                if not self.filled:
                    for _ in range(int(P["count"])):
                        self._spawn(figs, P)
                    self.filled = True
                    self.next_spawn = self.t + _ticks(P["respawn_s"])
                elif len(self.pillars) > int(P["count"]):
                    del self.pillars[int(P["count"]):]
                elif (len(self.pillars) < int(P["count"]) and self.t >= self.next_spawn
                      and not (self.roll_v[0] or self.roll_v[1])):
                    if self._spawn(figs, P):
                        self.next_spawn = self.t + _ticks(P["respawn_s"])
                    else:
                        self.next_spawn = self.t + 30
            for p in self.pillars:
                if len(p.seen) > 256:
                    p.seen.clear()
                p.age += 1
                p.flash = max(0, p.flash - 1)
                p.ps = worldfx.pscale(p.x, p.y, self.sw, self.sh)
            if self.pillars:
                self.hit_ids = set()
                for f in figs:
                    try:
                        self._body(f, P)
                    except Exception:
                        pass
                try:
                    self._projectiles(world, P)
                except Exception:
                    pass
                try:
                    self._melee(world, figs, P)
                except Exception:
                    pass
        try:
            self._triggers(figs)
        except Exception:
            pass
        try:
            self.roll(world, figs)
        except Exception:
            pass
        self._age_rubble()
        self._age_marks()

    # ---- fighters
    def _body(self, f, P):
        t, m = f.transform, f.motion
        ps = worldfx.pscale(t.x, t.y, self.sw, self.sh)
        fx, fy, hh = worldfx.WorldFx.foot(f, ps)
        tr = self.track.get(id(f))
        # On-screen speed this tick (a blink / teleport warp is not movement).
        spd = 0.0
        if tr is not None and id(f) not in worldfx._WARPS:
            spd = math.hypot(t.x - tr[0], t.y - tr[1])
        if m.bouncing or m.bounce_ending:
            spd = max(spd, math.hypot(m.bounce_vx, m.bounce_vy))
        br = 8.0 * ps
        fl_g = _wf()["ground"]
        for p in list(self.pillars):
            hw = P["width"] * 0.5 * p.ps
            fl = max(0.2, worldfx.flat_at(p.ps, fl_g))
            dx = fx - p.x
            dy = (fy - p.y) / fl
            d = math.hypot(dx, dy)
            reach = hw + br
            if d >= reach:
                p.seen.discard(f)          # left it: the next touch is a new hit
            if d >= reach + P["repel_px"] * p.ps:
                continue
            if d > 1e-6:
                nx, ny = dx / d, dy / d
            else:
                nx, ny = (1.0 if self.rng.random() < 0.5 else -1.0), 0.0
            if d < reach:
                if f not in p.seen:
                    p.seen.add(f)
                    if self.hit(p, P, spd=spd, body=True, ax=math.degrees(math.atan2(-ny, -nx))):
                        continue      # broke through on speed: it keeps going
                    if p not in self.pillars:
                        continue      # crumbled at 0 HP
                push = reach - d
                t.x += nx * push
                t.y += ny * push * fl
                # A knockback slide bounces off it like a wall.
                if m.bouncing or m.bounce_ending:
                    vn = m.bounce_vx * nx + m.bounce_vy * ny
                    if vn < 0:
                        m.bounce_vx -= 2.0 * vn * nx
                        m.bounce_vy -= 2.0 * vn * ny
            # The very subtle repel: away from the pillar's centre.
            k = P["repel"] * p.ps
            t.x += nx * k
            t.y += ny * k * fl
        t.x = max(10, min(self.sw - 10, t.x))
        t.y = max(10, min(self.sh - 10, t.y))

    # ---- projectiles
    def _projectiles(self, world, P):
        from . import combat, swordfx, fxkit
        for side in world.sides:
            for pr in side.projectiles:
                if not pr.alive or pr.hit_r_sq <= 0.0:
                    continue
                r = max(1.0, float(getattr(pr, "radius", 3) or 3)) * worldfx.pscale(pr.x, pr.y, self.sw, self.sh)
                self._shot(P, (pr.x, pr.y, pr.x - pr.vx, pr.y - pr.vy, r), float(getattr(pr, "damage", 1.0) or 0.0),
                           0.0, math.hypot(pr.vx, pr.vy), lambda pr=pr: combat.kill_projectile(pr), pr)
            for f in side.figures:
                drv = getattr(f, "fx", None)
                if drv is None:
                    continue
                for inst in drv.player.insts + drv.clane[0].insts + drv.stack_insts():
                    fxd = inst.fx
                    bt = fxd["battle"]
                    if not bt["deals_damage"] or inst.dead or inst.age >= inst.life or inst.lodge is not None:
                        continue
                    dmg = float(bt.get("damage") or 1.0)
                    if swordfx.shoots(inst):
                        for (ri, rx, ry, rvx, rvy) in swordfx.live_points(inst, inst.ps or 1.0):
                            ref = fxkit.RoundRef(inst, ri)
                            if ref.stopped:
                                continue
                            self._shot(P, (rx, ry, rx - rvx, ry - rvy, 4.0 * (inst.ps or 1.0)), dmg,
                                       fxkit.inst_knockback(inst, ri), math.hypot(rvx, rvy),
                                       lambda ref=ref, rx=rx, ry=ry: ref.stop(rx, ry), (id(inst), ri))
                        continue
                    if (fxd["motion"]["kind"] in ("travel", "homing", "zigzag", "path")
                            and fxd["prim"] not in ("weapon", "ghost", "particles", "pulse")):
                        b = fxkit.inst_body(inst)
                        hw = b[4] if b[4] > 0 else 8.0 * (inst.ps or 1.0)
                        self._shot(P, (b[0], b[1], b[2], b[3], hw), dmg, fxkit.inst_knockback(inst),
                                   math.hypot(inst.x - inst.px, inst.y - inst.py),
                                   lambda inst=inst: _end_inst(inst), inst)

    def _shot(self, P, body, dmg, kb, spd, kill, key):
        k = id(key) if not isinstance(key, tuple) else key
        if k in self.hit_ids:
            return
        for p in list(self.pillars):
            ax = p.axis(P)
            if _seg_dist(body, ax) - body[4] - ax[4] > 0.0:
                continue
            self.hit_ids.add(k)
            hx, hy = body[0], body[1]
            if self.hit(p, P, dmg=dmg, kb=kb, spd=spd, x=hx, y=hy,
                        ax=math.degrees(math.atan2(body[1] - body[3], body[0] - body[2]))):
                continue          # broke on a threshold: it flies on
            if P["block_projectiles"]:
                kill()
            return

    # ---- melee and blasts
    def _melee(self, world, figs, P):
        from . import swordfx, fxkit
        for f in figs:
            drv = getattr(f, "fx", None)
            if drv is not None:
                for inst in drv.player.insts + drv.clane[0].insts + drv.stack_insts():
                    fxd = inst.fx
                    bt = fxd["battle"]
                    if not bt["deals_damage"] or inst.dead or inst.age >= inst.life:
                        continue
                    if swordfx.shoots(inst) or (fxd["motion"]["kind"] in ("travel", "homing", "zigzag", "path")
                                                and fxd["prim"] not in ("weapon", "ghost", "particles", "pulse")):
                        continue          # a projectile: _projectiles
                    b = fxkit.inst_body(inst)
                    hw = (b[4] if b[4] > 0 else 0.0) + 24.0 * (inst.ps or 1.0)
                    self._area(P, (b[0], b[1], b[2], b[3], hw), float(bt.get("damage") or 1.0),
                               fxkit.inst_knockback(inst), inst)
            c = f.combat
            ps = worldfx.pscale(f.x, f.y, self.sw, self.sh)
            # Built-in sword: a slash and its crescent waves hit what they reach.
            if f.mode.uses_melee() and getattr(c, "slashing", False):
                r = (config.SLASH_HIT_RADIUS + 24.0) * ps
                self._area(P, (f.x, f.y, f.x, f.y, r), P["melee_damage"], 0.0, ("slash", id(f)))
            else:
                for p in self.pillars:       # the swing ended: the next one hits again
                    p.seen.discard(("slash", id(f)))
            for cr in getattr(c, "crescents", ()):
                if cr.alive:
                    r = 24.0 * worldfx.pscale(cr.x, cr.y, self.sw, self.sh)
                    self._area(P, (cr.x, cr.y, cr.x, cr.y, r), P["melee_damage"], 0.0, cr)
            # Built-in ultimate crescents: an ultimate always breaks through.
            for uc in getattr(c, "ult_crescents", ()):
                if uc.alive:
                    r = 40.0 * worldfx.pscale(uc.x, uc.y, self.sw, self.sh)
                    self._area(P, (uc.x, uc.y, uc.x, uc.y, r), float("inf"), 0.0, uc)

    def _area(self, P, body, dmg, kb, src):
        """A melee / area source touching a pillar hits it once (per pillar)."""
        k = id(src) if not isinstance(src, tuple) else src
        for p in list(self.pillars):
            if k in p.seen:
                continue
            ax = p.axis(P)
            if _seg_dist(body, ax) - body[4] - ax[4] > 0.0:
                continue
            p.seen.add(k)
            self.hit(p, P, dmg=dmg, kb=kb, x=p.x, y=p.y - 0.5 * (p.y - ax[1]),
                     ax=math.degrees(math.atan2(p.y - body[1], p.x - body[0])))

    def blast(self, x, y, dmg, kb=0.0):
        """A blast detonated at (x, y) (worldfx.scan_blasts)."""
        P = _wf()["pillars"]
        if not P["enabled"] or not self.pillars:
            return
        ps = worldfx.pscale(x, y, self.sw, self.sh)
        r = P["blast_reach"] * ps
        for p in list(self.pillars):
            ax = p.axis(P)
            if _seg_dist((x, y, x, y, r), ax) - r - ax[4] > 0.0:
                continue
            self.hit(p, P, dmg=dmg, kb=kb, x=p.x, y=p.y - 0.5 * (p.y - ax[1]),
                     ax=math.degrees(math.atan2(p.y - y, p.x - x)))

    # ---- rubble & boulders
    def _triggers(self, figs):
        seen = set()
        wf = None
        for f in figs:
            seen.add(id(f))
            t, m, c = f.transform, f.motion, f.combat
            tr = self.track.get(id(f))
            hp = float(getattr(f.personality, "hp", 0) or 0)
            bouncing = bool(m.bouncing)
            if tr is None:
                self.track[id(f)] = [t.x, t.y, hp, bouncing, -10 ** 9]
                continue
            R = worldfx.cfg(f, "rubble")
            spd = math.hypot(t.x - tr[0], t.y - tr[1])
            ps = worldfx.pscale(t.x, t.y, self.sw, self.sh)
            ready = (self.t - tr[4]) * config.TICK_MS >= R["cooldown_ms"]
            if R["enabled"] and R["boulders"] and ready and _wf()["ground"]["enabled"]:
                fx, fy, hh = worldfx.WorldFx.foot(f, ps)
                knock = math.hypot(m.bounce_vx, m.bounce_vy) if (bouncing and not tr[3]) else 0.0
                heavy = tr[2] - hp
                kind = None
                if knock >= R["hit_knockback"] or heavy >= R["hit_damage"]:
                    kind = "hit"
                elif spd >= R["speed"] and not worldfx._WARPS.__contains__(id(f)):
                    kind = "speed"
                if kind is not None:
                    if wf is None:
                        wf = worldfx.state(self.world)
                    sc = worldfx.cfg(f, "slam")
                    wf.use(f, sc)
                    rgb = _rgb(R["color"])
                    n = int(R["boulder_count"])
                    if kind == "hit":
                        s = max(0.8, min(2.0, max(knock / 12.0, heavy / 20.0)))
                        if R["crater"]:
                            wf.crater(f, fx, fy, ps, s, sc)
                        back = math.degrees(math.atan2(-m.bounce_vy, -m.bounce_vx)) if knock > 0 else None
                        wf.debris(fx, fy, "rock", n, s, rgb, az=back, spread=360.0 if back is None else 120.0,
                                  elev=(55.0, 78.0), spd=(3.0, 6.0), size=(R["boulder_min"], R["boulder_max"]))
                    else:
                        back = math.degrees(math.atan2(tr[1] - t.y, tr[0] - t.x))
                        wf.debris(fx, fy, "rock", max(1, n // 2), 1.0, rgb, az=back, spread=70.0,
                                  elev=(40.0, 65.0), spd=(2.5, 5.0),
                                  size=(R["boulder_min"] * 0.6, R["boulder_max"] * 0.6))
                    tr[4] = self.t
            tr[0], tr[1], tr[2], tr[3] = t.x, t.y, hp, bouncing
        for k in [k for k in self.track if k not in seen]:
            del self.track[k]

    def add_rubble(self, x, y, size, rot, rgb):
        """A thrown rock has landed (worldfx.WorldFx.move)."""
        R = _wf()["rubble"]
        if not (R["enabled"] and R["rest"]):
            return
        if len(self.rubble) >= int(R["max_rubble"]):
            self.rubble.pop(0)
        self.rubble.append([x, y, size, rot, rgb, 0, _ticks(R["rest_s"] + R["fade_s"])])

    def _add_pit(self, x, y, rx, fl, rgb, rest_s=None, fade_s=None):
        """A crater: a jagged dish rx wide, flattened by the ground's tilt
        (fl).  Stays rest_s (default: rubble rest_s), then fades over fade_s."""
        R = _wf()["rubble"]
        rest_s = R["rest_s"] if rest_s is None else rest_s
        fade_s = R["fade_s"] if fade_s is None else fade_s
        rnd = self.rng.random
        n = 15
        # Jagged rim: radius per point (fraction of rx) and a small angle jitter.
        rim = [(0.78 + 0.34 * rnd(), (rnd() - 0.5) * 0.22) for _ in range(n)]
        if len(self.pits) >= 24:
            self.pits.pop(0)
        self.pits.append([x, y, rx, fl, rgb, 0, _ticks(max(0.5, rest_s) + fade_s), rim, _ticks(fade_s)])

    # ---- FX on the ground (worldfx.scan_ground_fx / orb_crater)
    def add_crater(self, x, y, rx, rest_s, fade_s):
        fl = max(0.2, worldfx.flat_at(worldfx.pscale(x, y, self.sw, self.sh), _wf()["ground"]))
        self._add_pit(x, y, rx, fl, _rgb(_wf()["rubble"]["color"]), rest_s, fade_s)

    def add_mark(self, key, x, y, kind, w, G):
        m = self.mark_open.get(key)
        if m is None:
            if len(self.marks) >= 24:
                old = self.marks.pop(0)
                for k in [k for k, v in self.mark_open.items() if v is old]:
                    del self.mark_open[k]
            m = {"pts": [], "kind": kind, "w": float(w), "life": _ticks(max(0.1, G["mark_s"]) + G["fade_s"]),
                 "fade": _ticks(G["fade_s"]), "rgb": _rgb(G["color"])}
            self.marks.append(m)
            self.mark_open[key] = m
        m["w"] = max(m["w"] * 0.9, float(w))
        pts = m["pts"]
        if pts:
            lx, ly = pts[-1][0], pts[-1][1]
            if (x - lx) ** 2 + (y - ly) ** 2 < 9.0:
                return
        pts.append([float(x), float(y), 0, float(w)])
        if len(pts) > 260:
            del pts[0]

    def end_mark(self, key):
        self.mark_open.pop(key, None)

    def _age_marks(self):
        if not self.marks:
            return
        live = []
        for m in self.marks:
            life = m["life"]
            for q in m["pts"]:
                q[2] += 1
            m["pts"] = [q for q in m["pts"] if q[2] < life]
            if m["pts"]:
                live.append(m)
        if len(live) != len(self.marks):
            ids = {id(m) for m in live}
            for k in [k for k, v in self.mark_open.items() if id(v) not in ids]:
                del self.mark_open[k]
        self.marks = live

    def _paint_marks(self, qp, ink):
        """Trenches: a scorched gouge with a lit lip and a dark floor; streaks:
        a thinner scorch line.  Older points fade over the mark's fade."""
        qp.save()
        for m in self.marks:
            pts = m["pts"]
            if len(pts) < 2:
                continue
            life, fade = m["life"], max(1, m["fade"])
            rgb = m["rgb"]
            trench = m["kind"] == "trench"
            lip = worldfx._lift(rgb, 0.45)
            for i in range(1, len(pts)):
                a, b = pts[i - 1], pts[i]
                age = max(a[2], b[2])
                al = 1.0 if age < life - fade else max(0.0, (life - age) / float(fade))
                if al <= 0.0:
                    continue
                al = math.ceil(al * 4.0) / 4.0             # fades in steps, like the craters
                w = 0.5 * (a[3] + b[3])
                ps = worldfx.pscale(b[0], b[1], self.sw, self.sh)
                fl = max(0.2, worldfx.flat_at(ps, _wf()["ground"]))
                wf = w * (0.55 + 0.45 * fl)                # flatter ground = a thinner-looking trench
                p0, p1 = QPointF(a[0], a[1]), QPointF(b[0], b[1])
                qp.setOpacity(al)
                if trench:
                    qp.setPen(QPen(ink, wf * 1.35 + 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    qp.drawLine(p0, p1)
                    qp.setPen(QPen(QColor(*lip), wf * 1.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    qp.drawLine(p0, p1)
                    qp.setPen(QPen(QColor(*rgb), wf * 0.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    qp.drawLine(p0, p1)
                    qp.setPen(QPen(QColor(int(rgb[0] * 0.45), int(rgb[1] * 0.45), int(rgb[2] * 0.45)),
                                   max(1.0, wf * 0.35), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    qp.drawLine(QPointF(a[0], a[1] + wf * fl * 0.12), QPointF(b[0], b[1] + wf * fl * 0.12))
                else:
                    qp.setPen(QPen(QColor(*rgb), wf, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    qp.drawLine(p0, p1)
                    qp.setPen(QPen(ink, max(1.0, wf * 0.3), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                    qp.drawLine(p0, p1)
        qp.restore()

    # ---- rolling world
    def roll(self, world, figs):
        """Section roll: the world anchor in the outer zone of the screen rolls
        the world the other way (fighters stay put): pillars, rubble, craters,
        marks and Dust & Air move; pillars rolled off-screen are dropped and
        new ones rise off the side the world rolls in from."""
        Rl = _wf()["roll"]
        sw, sh = float(self.sw), float(self.sh)
        tx = ty = 0.0
        if Rl["enabled"] and figs:
            ax, ay = self._centre(figs)
            z = max(0.05, min(0.5, Rl["zone_frac"]))
            vmax = Rl["max_speed"] * TICK_S

            def axis(u):
                if u < z:
                    return (z - u) / z            # near the low edge: the world rolls +
                if u > 1.0 - z:
                    return -(u - (1.0 - z)) / z   # near the high edge: the world rolls -
                return 0.0
            tx = vmax * max(-1.0, min(1.0, axis(ax / sw)))
            if Rl["vertical"]:
                ty = vmax * max(-1.0, min(1.0, axis(ay / sh)))
        e = 1.0 if Rl["ease_ms"] <= 0 else min(1.0, config.TICK_MS / float(Rl["ease_ms"]))
        vx = self.roll_v[0] + (tx - self.roll_v[0]) * e
        vy = self.roll_v[1] + (ty - self.roll_v[1]) * e
        if abs(vx) < 0.01:
            vx = 0.0
        if abs(vy) < 0.01:
            vy = 0.0
        self.roll_v = (vx, vy)
        if not (vx or vy):
            return
        for p in self.pillars:
            p.x += vx
            p.y += vy
        for r in self.rubble:
            r[0] += vx
            r[1] += vy
        for q in self.pits:
            q[0] += vx
            q[1] += vy
        for m in self.marks:
            for q in m["pts"]:
                q[0] += vx
                q[1] += vy
        try:
            worldfx.state(world).shift(vx, vy)
        except Exception:
            pass
        # Off the trailing side: gone (no break - it just rolled away).
        P = _wf()["pillars"]
        mg = Rl["margin_px"]
        keep = []
        for p in self.pillars:
            hw, h = p.dims(P)
            gone = ((vx < 0 and p.x < -hw - mg) or (vx > 0 and p.x > sw + hw + mg) or
                    (vy < 0 and p.y < -mg) or (vy > 0 and p.y - h > sh + mg) or
                    abs(p.x - sw * 0.5) > 3.0 * sw or abs(p.y - sh * 0.5) > 3.0 * sh)
            if not gone:
                keep.append(p)
        self.pillars = keep
        if P["enabled"] and figs and len(self.pillars) < int(P["count"]) and self.t >= self.roll_next:
            if self._spawn_ahead(P, vx, vy):
                self.roll_next = self.t + _ticks(0.25 + 0.75 * self.rng.random())
                self.next_spawn = max(self.next_spawn, self.t + _ticks(P["respawn_s"]))
            else:
                self.roll_next = self.t + 10

    def _spawn_ahead(self, P, vx, vy):
        """A new pillar off the side the world rolls in from, already standing,
        a random way past the edge so they come in one after another."""
        sw, sh = float(self.sw), float(self.sh)
        Rl = _wf()["roll"]
        rnd = self.rng.random
        for _ in range(MAX_TRIES):
            horiz = rnd() * (abs(vx) + abs(vy)) < abs(vx)
            ext = Rl["margin_px"] * 0.5 + rnd() * Rl["spawn_ahead_px"]
            if horiz:
                y = sh * 0.12 + rnd() * (sh * 0.88 - 14)
                ps = worldfx.pscale(0.0 if vx > 0 else sw, y, self.sw, self.sh)
                hw = P["width"] * 0.5 * ps
                x = -hw - ext if vx > 0 else sw + hw + ext
            else:
                x = 20 + rnd() * (sw - 40)
                ps = worldfx.pscale(x, 0.0 if vy > 0 else sh, self.sw, self.sh)
                y = -10.0 - ext if vy > 0 else sh + P["height"] * ps + 10.0 + ext
            if any(math.hypot(p.x - x, p.y - y) < P["gap_px"] for p in self.pillars):
                continue
            p = Pillar(x, y, P["hp"], 1, self.rng)
            p.age = p.rise_t
            p.ps = worldfx.pscale(x, y, self.sw, self.sh)
            self.pillars.append(p)
            return True
        return False

    def _age_rubble(self):
        if self.pits:
            for q in self.pits:
                q[5] += 1
            self.pits = [q for q in self.pits if q[5] < q[6]]
        if not self.rubble:
            return
        for r in self.rubble:
            r[5] += 1
        self.rubble = [r for r in self.rubble if r[5] < r[6]]

    # ---- paint
    def _front(self, p, P, figs):
        """Is a fighter standing behind pillar p (drawn over it)?"""
        hw, h = p.dims(P)
        for f in figs:
            ps = worldfx.pscale(f.x, f.y, self.sw, self.sh)
            fx, fy, hh = worldfx.WorldFx.foot(f, ps)
            if fy < p.y and abs(fx - p.x) < hw + 2.2 * hh and fy > p.y - h - 2.2 * hh:
                return True
        return False

    def paint_back(self, qp, world):
        P = _wf()["pillars"]
        ink = QColor(_wf()["ground"]["ink"])
        if self.marks:
            self._paint_marks(qp, ink)
        if self.pits:
            self._paint_pits(qp, ink)
        if self.rubble:
            self._paint_rubble(qp, ink)
        figs = [f for f in world.all_figures() if getattr(f.transform, "init", True)]
        alpha = GHOST_ALPHA if getattr(world, "boulders_ghost", False) else 1.0
        sq = worldscale.squasher(qp, self.sw)     # tiny planet (no-op when off)
        for p in sorted(self.pillars, key=lambda q: q.y):
            if not self._front(p, P, figs):
                sq.at(p.x, p.y)
                self._paint_pillar(qp, p, P, ink, alpha)
        sq.done()

    def paint_front(self, qp, world, silhouettes=True):
        """Pillars a fighter stands behind, drawn over the fighters.  Every
        fighter they cover shows through as a flat tinted silhouette, clipped
        to the rock (skipped while F12 see-through boulders is on: the rock
        is faded then, so the fighter itself shows)."""
        P = _wf()["pillars"]
        ink = QColor(_wf()["ground"]["ink"])
        figs = [f for f in world.all_figures() if getattr(f.transform, "init", True)]
        ghost = getattr(world, "boulders_ghost", False)
        alpha = GHOST_ALPHA if ghost else 1.0
        base = qp.transform()                     # camera view (no planet squash)
        sq = worldscale.squasher(qp, self.sw)
        for p in sorted(self.pillars, key=lambda q: q.y):
            if self._front(p, P, figs):
                sq.at(p.x, p.y)
                clip = self._paint_pillar(qp, p, P, ink, alpha)
                if silhouettes and not ghost and clip is not None:
                    behind = self._behind(p, P, figs)
                    if behind:
                        qp.save()
                        qp.setClipPath(clip, Qt.IntersectClip)   # rock shape (squashed)
                        qp.setTransform(base)                     # fighters are not squashed
                        for f in behind:
                            _paint_silhouette(qp, f)
                        qp.restore()
        sq.done()

    def _behind(self, p, P, figs):
        """Fighters standing behind pillar p whose body can overlap it."""
        hw, h = p.dims(P)
        out = []
        for f in figs:
            ps = worldfx.pscale(f.x, f.y, self.sw, self.sh)
            fx, fy, hh = worldfx.WorldFx.foot(f, ps)
            if fy < p.y and abs(fx - p.x) < hw + 2.2 * hh and fy > p.y - h - 2.2 * hh:
                out.append(f)
        return out

    def _paint_pits(self, qp, ink):
        """Broken-pillar craters, flat on the ground (rx across, rx * flat
        deep): a jagged raised lip, the inner wall, and the floor shifted
        toward the viewer (the far inner wall shows, the near one is hidden)."""
        R = _wf()["rubble"]
        fade_t = max(1, _ticks(R["fade_s"]))
        qp.save()
        sq = worldscale.squasher(qp, self.sw)
        for pit in self.pits:
            x, y, rx, fl, rgb, age, life, rim = pit[:8]
            ft = max(1, pit[8]) if len(pit) > 8 else fade_t
            a = 1.0 if age < life - ft else max(0.0, (life - age) / float(ft))
            if a <= 0.0:
                continue
            a = math.ceil(a * 4.0) / 4.0                  # fades in steps, like the crater rings
            sq.at(x, y)
            qp.setOpacity(a)
            n = len(rim)

            def poly(k, dy=0.0):
                pts = []
                for i, (rr, jit) in enumerate(rim):
                    th = 2 * math.pi * i / n + jit
                    r = rx * k * (rr if k > 0.9 else 0.5 + 0.5 * rr)
                    pts.append(QPointF(x + math.cos(th) * r, y + dy + math.sin(th) * r * fl))
                return QPolygonF(pts)
            lip = worldfx._lift(rgb, 0.18)
            wall = tuple(int(c * 0.55) for c in rgb)
            floor = tuple(int(c * 0.38) for c in rgb)
            pw = max(1.0, min(2.5, rx / 40.0))
            qp.setPen(QPen(ink, pw, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            qp.setBrush(QColor(*lip))
            qp.drawPolygon(poly(1.0))
            qp.setPen(QPen(ink, max(1.0, pw * 0.7), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            qp.setBrush(QColor(*wall))
            qp.drawPolygon(poly(0.74))
            qp.setPen(Qt.NoPen)
            qp.setBrush(QColor(*floor))
            qp.drawPolygon(poly(0.5, rx * fl * 0.16))
        sq.done()
        qp.restore()

    def _paint_rubble(self, qp, ink):
        R = _wf()["rubble"]
        fade_t = max(1, _ticks(R["fade_s"]))
        qp.save()
        sq = worldscale.squasher(qp, self.sw)
        pen = QPen(ink, 1.2)
        for x, y, s, rot, rgb, age, life in self.rubble:
            a = 1.0 if age < life - fade_t else max(0.0, (life - age) / float(fade_t))
            if a <= 0.0:
                continue
            sq.at(x, y)
            qp.setOpacity(a)
            col = QColor(*rgb)
            lit = QColor(min(255, rgb[0] + 60), min(255, rgb[1] + 60), min(255, rgb[2] + 60))
            pts = []
            for i in range(4):
                an = rot + i * 1.5708 + (0.25 if i % 2 else -0.1)
                rr = s * (1.0 if i % 2 == 0 else 0.8)
                pts.append(QPointF(x + math.cos(an) * rr, y + math.sin(an) * rr))
            qp.setPen(pen)
            qp.setBrush(col)
            qp.drawPolygon(QPolygonF(pts))
            qp.setPen(Qt.NoPen)
            qp.setBrush(lit)
            qp.drawPolygon(QPolygonF([pts[0], pts[1], QPointF(x, y)]))
        qp.restore()

    def _view(self, p, P):
        """(yaw rad, depth factor s) of pillar p's 2.5D view this frame."""
        sw, sh = max(1.0, float(self.sw)), max(1.0, float(self.sh))
        ax = worldscale._A[0] if worldscale._A is not None else sw * 0.5
        reach = max(1.0, P["view_reach_frac"] * sw)
        u = max(-1.0, min(1.0, (p.x - ax) / reach))
        yaw = math.radians(P["view_yaw"]) * u
        yf = max(0.0, min(1.0, p.y / sh))
        e = math.radians(P["pitch_top"] + (P["pitch_bottom"] - P["pitch_top"]) * yf)
        return yaw, math.sin(e)

    def _paint_pillar(self, qp, p, P, ink, alpha=1.0):
        """Paint pillar p; returns its silhouette path (painter coords) or
        None.  alpha < 1 (F12 see-through boulders): the rock is rendered
        whole into an offscreen layer first, then laid down at that opacity,
        so overlapping facets / the ink pass don't stack into dark seams."""
        if alpha >= 0.999:
            return self._draw_pillar(qp, p, P, ink)
        hw, h = p.dims(P)
        if h < 0.5 or hw < 0.5:
            return None
        fl = max(0.2, worldfx.flat_at(p.ps, _wf()["ground"]))
        pad = 6.0 + 3.0 * max(1.0, p.ps)
        local = QRectF(p.x - hw * 1.6 - pad, p.y - h - hw - pad,
                       hw * 3.2 + 2 * pad, h + hw * (1.0 + 1.4 * fl) + 2 * pad)
        T = qp.transform()
        dev = qp.device()
        r = T.mapRect(local).intersected(QRectF(0, 0, dev.width(), dev.height()))
        if r.width() < 1 or r.height() < 1:
            return None
        rx, ry = math.floor(r.x()), math.floor(r.y())
        rw, rh = int(math.ceil(r.right())) - rx, int(math.ceil(r.bottom())) - ry
        try:
            dpr = float(dev.devicePixelRatioF())
        except Exception:
            dpr = 1.0
        img = QImage(max(1, int(rw * dpr)), max(1, int(rh * dpr)), QImage.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.transparent)
        ip = QPainter(img)
        ip.setRenderHint(QPainter.Antialiasing)
        ip.setTransform(T * QTransform.fromTranslate(-rx, -ry))
        clip = self._draw_pillar(ip, p, P, ink)
        ip.end()
        qp.save()
        qp.setTransform(QTransform())
        qp.setOpacity(qp.opacity() * alpha)
        qp.drawImage(QPointF(rx, ry), img)
        qp.restore()
        return clip

    def _draw_pillar(self, qp, p, P, ink):
        """A low-poly rock, oblique 2.5D projection (see the module notes):
        screen x = bx + X', screen y = by - Z - Y' s, so the drawn height is
        the collision height and the base sits on the ground spot."""
        hw, h = p.dims(P)
        if h < 0.5 or hw < 0.5:
            return None
        rgb = _rgb(P["color"])
        bx, by = p.x, p.y
        fl = max(0.2, worldfx.flat_at(p.ps, _wf()["ground"]))
        yaw, s = self._view(p, P)
        cs, sn = math.cos(yaw), math.sin(yaw)
        verts, faces = p.mesh(P["facets"])
        # Rotated, scaled vertices (px) and their screen points.
        rv, sp = [], []
        for x, y, z in verts:
            X = (x * cs - y * sn) * hw
            Y = (x * sn + y * cs) * hw
            Z = z * h
            rv.append((X, Y, Z))
            sp.append(QPointF(bx + X, by - Z - Y * s))
        # View direction of the oblique projection (what projects to a point).
        vl = math.sqrt(1.0 + s * s)
        vx, vy, vz = 0.0, 1.0 / vl, -s / vl
        vis = []
        for idx, tone in faces:
            pts = [rv[i] for i in idx]
            nx, ny, nz = _newell(pts)
            nl = math.sqrt(nx * nx + ny * ny + nz * nz)
            if nl < 1e-9:
                continue
            nx, ny, nz = nx / nl, ny / nl, nz / nl
            if nx * vx + ny * vy + nz * vz >= -1e-4:
                continue                                  # facing away
            d = sum(q[1] * vy + q[2] * vz for q in pts) / len(pts)
            lam = max(0.0, nx * _LIGHT[0] + ny * _LIGHT[1] + nz * _LIGHT[2])
            band = math.floor(lam * 4.0 + 0.5) / 4.0       # cel bands
            k = (0.42 + 0.72 * band) * tone
            col = QColor(max(0, min(255, int(rgb[0] * k))), max(0, min(255, int(rgb[1] * k))),
                         max(0, min(255, int(rgb[2] * k))))
            vis.append((d, QPolygonF([sp[i] for i in idx]), col))
        if not vis:
            return None
        vis.sort(key=lambda t: -t[0])                       # far first
        qp.save()
        # Ground shadow / base.
        qp.setPen(Qt.NoPen)
        qp.setBrush(QColor(0, 0, 0, 70))
        qp.drawEllipse(QPointF(bx + hw * 0.25, by), hw * 1.35, hw * 1.35 * fl)
        pw = max(1.0, min(3.0, 1.4 * p.ps))
        # Ink silhouette: every visible facet in ink with a fat pen, then the
        # facets over it (only the outer edge of the fat pen survives).
        qp.setPen(QPen(ink, 2.0 * pw, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        qp.setBrush(ink)
        for _d, poly, _c in vis:
            qp.drawPolygon(poly)
        for _d, poly, col in vis:
            qp.setPen(QPen(col.darker(118), 1.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            qp.setBrush(col)
            qp.drawPolygon(poly)
        frac = p.hp / p.hp0 if p.hp0 > 0 else 1.0
        nc = 0 if frac > 0.75 else 2 if frac > 0.5 else 4 if frac > 0.25 else 5
        clip = QPainterPath()
        clip.setFillRule(Qt.WindingFill)
        for _d, poly, _c in vis:
            clip.addPolygon(poly)
            clip.closeSubpath()
        if nc or p.flash > 0:
            qp.setClipPath(clip, Qt.IntersectClip)
            # Cracks grow as its HP drops (on the face toward the viewer).
            if nc:
                qp.setPen(QPen(ink, max(1.0, pw * 0.8)))
                qp.setBrush(Qt.NoBrush)
                for cr in p.cracks[:nc]:
                    qp.drawPolyline(QPolygonF([QPointF(bx + u * hw * 0.85, by - h * v + hw * s * 0.7)
                                               for u, v in cr]))
            # Hit flash.
            if p.flash > 0:
                qp.setOpacity(0.5 * p.flash / 6.0)
                qp.setPen(Qt.NoPen)
                qp.setBrush(QColor(255, 255, 255))
                qp.drawPath(clip)
        qp.restore()
        return clip

def _paint_silhouette(qp, f):
    """Fighter f's body as one flat tint (its HP-bar colour), placed exactly
    like the sprite in Figure.draw; the caller clips it to the rock."""
    try:
        if getattr(getattr(f, "ua", None), "construct", None) is not None:
            return
        if f.combat.vc_hidden or (f.blink is not None and f.blink.gone):
            return
        frame = f._current_frame()
        if frame is None:
            return
        base = tuple(f.lut[128])
        rgb = tuple(int(c + (255 - c) * 0.35) for c in base[:3])
        pm = _combat().silhouette(frame, rgb)
        qp.save()
        qp.translate(f.transform.x, f.transform.y)
        f._squash(qp)
        if f.aim is not None:
            qp.rotate(f.aim)
        elif f.motion.rotate:
            qp.rotate(f.transform.angle)
        ps = f._position_scale()
        if ps != 1.0:
            qp.scale(ps, ps)
        qp.setOpacity(SILHOUETTE_ALPHA)
        qp.drawPixmap(-pm.width() // 2, -pm.height() // 2, pm)
        qp.restore()
    except Exception:
        pass


def _combat():
    from . import combat
    return combat


def _end_inst(inst):
    inst.age = max(inst.age, inst.life)
    inst.dead = True


# ---------------------------------------------------------------- module API
def state(world):
    st = getattr(world, "terrain", None)
    if st is None:
        st = world.terrain = Terrain()
    return st


def step(world):
    """Once per tick, after both sides moved, before worldfx.step."""
    state(world).step(world)


def reset(world):
    """A fresh round (Reset & Start): pillars and rubble start over."""
    world.terrain = Terrain()


def note_blast(world, x, y, dmg, kb=0.0):
    st = getattr(world, "terrain", None)
    if st is not None:
        try:
            st.blast(x, y, dmg, kb)
        except Exception:
            pass


def note_crater(world, x, y, rx, rest_s, fade_s):
    """FX on the ground: an orb went off here (worldfx.orb_crater)."""
    st = getattr(world, "terrain", None)
    if st is not None:
        st.add_crater(x, y, rx, rest_s, fade_s)


def note_mark(world, key, x, y, kind, w, G):
    """FX on the ground: extend the trench / streak `key` to (x, y)."""
    st = getattr(world, "terrain", None)
    if st is not None:
        st.add_mark(key, x, y, kind, w, G)


def end_mark(world, key):
    st = getattr(world, "terrain", None)
    if st is not None:
        st.end_mark(key)


def note_rubble(world, x, y, size, rot, rgb):
    st = getattr(world, "terrain", None)
    if st is not None:
        st.add_rubble(x, y, size, rot, rgb)


def paint_back(qp, world):
    st = getattr(world, "terrain", None)
    if st is not None and _wf()["ground"]["enabled"]:
        st.paint_back(qp, world)


def paint_front(qp, world, silhouettes=True):
    st = getattr(world, "terrain", None)
    if st is not None and st.pillars and _wf()["ground"]["enabled"]:
        st.paint_front(qp, world, silhouettes)
