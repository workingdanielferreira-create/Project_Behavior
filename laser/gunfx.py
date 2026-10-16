"""
Gunfire — anime gun shots for the FX Kit "technique" primitive, painted by
hand at the same standard as the ki barrage (laser/strikefx.py), on the
frame, pen and timeline of laser/swordfx.py.

Styles (params.style):

  machine_gun     rapid-fire tracers: a short star flash per round, a stream
                  of brass casings and sparks / dust where they land
  shotgun         heavy volleys of pellets in a cone: a fan-shaped flash,
                  a pressure ring, muzzle smoke and a red shell per volley
  magnum          premium hand-cannon slugs: a big boom flash with cylinder
                  side jets, a thick tracer wrapped in rifling rings, and a
                  spiked impact star with shockwave rings
  charged_blast   energy gathers (streaks rushing in, rings closing on a
                  growing orb), holds, then one huge orb flies and explodes
  dual_pistols    gun-kata: rounds from alternating hands, each flash with a
                  swing arc, casings flying off both sides
  sniper_rail     a laser sight and a lock-on reticle, then one rail shot:
                  an instant line wrapped in a helix and shock rings; the
                  hit bursts a beat later
  gatling         the barrels spin up, fire faster and faster, glow with
                  heat and smoke as they spin down
  rocket_barrage  missiles launch on alternate arcs, speed up, leave smoke
                  trails and explode on the target
  drill_bullet    a spinning drill of light inside a spiral of wind that
                  pierces everything in its path and shatters at the end
  thunder_bullet  a bullet wrapped in crackling arcs with a lightning trail;
                  where it hits, lightning strikes from the sky

Parameters (the technique's own, reused — FX Studio labels them per gun):

  radius = bullet size, thickness = impact size, span = spread (degrees),
  length = range (px), swing_ticks = ticks between shots (charged blast:
  charge ticks; sniper: aim ticks; gatling: spin-up ticks), hold_ticks =
  how long it fires (charged blast: held at full charge; sniper: how long
  the shot lingers), density = sparks / smoke / casings.

Aim: with Aim target every round aims at where the target is the tick it
fires (tracking fire); otherwise along the effect's direction.

Hits: a round hits once and stops there (give the effect Pierce and a short
Re-hit, as for the ki barrage); the drill keeps going through; the rail hits
along its whole line for RAIL_HIT ticks.  Everything is a pure function of
the instance (age, seed, the anchor's and the target's paths), so FX
Studio's port (tools/fx/studio/gunfx.js) draws the same pixels.  Keep the
two in step (tools/fx/check_parity.py compares the tables).
"""

import math

from . import fxkit as F
from . import swordfx as S

STYLES = ("machine_gun", "shotgun", "magnum", "charged_blast", "dual_pistols", "sniper_rail", "gatling",
          "rocket_barrage", "drill_bullet", "thunder_bullet")

# Per gun: look, speed (px per tick, x scale), range (times length), rounds
# per volley, side offset of alternate rounds (px), muzzle flash ticks and
# size (px), casings (0 none, 1 brass, 2 shotgun shell), muzzle smoke puffs,
# dust / smoke puffs where a round lands.
GUNS = {
    "machine_gun": dict(look="tracer", speed=[16, 19], range=[0.9, 1.05], pellets=1, side=0, flash=3, flash_px=9,
                        shells=1, smoke=0, dust=1),
    "shotgun": dict(look="pellet", speed=[12, 16], range=[0.55, 1.0], pellets=9, side=0, flash=8, flash_px=22,
                    shells=2, smoke=4, dust=0),
    "magnum": dict(look="slug", speed=[21, 23], range=[1.0, 1.0], pellets=1, side=0, flash=9, flash_px=20,
                   shells=0, smoke=3, dust=2),
    "charged_blast": dict(look="orb", speed=[8, 9], range=[1.0, 1.0], pellets=1, side=0, flash=10, flash_px=30,
                          shells=0, smoke=3, dust=5),
    "dual_pistols": dict(look="tracer", speed=[14, 17], range=[0.85, 1.05], pellets=1, side=9, flash=5,
                         flash_px=11, shells=1, smoke=0, dust=1),
    "sniper_rail": dict(look="rail", speed=[0, 0], range=[1.0, 1.0], pellets=1, side=0, flash=10, flash_px=26,
                        shells=1, smoke=3, dust=3),
    "gatling": dict(look="tracer", speed=[17, 20], range=[0.85, 1.05], pellets=1, side=4, flash=2, flash_px=8,
                    shells=1, smoke=0, dust=1),
    "rocket_barrage": dict(look="rocket", speed=[7, 9], range=[1.0, 1.0], pellets=1, side=6, flash=6, flash_px=14,
                           shells=0, smoke=2, dust=5),
    "drill_bullet": dict(look="drill", speed=[12, 13], range=[1.0, 1.0], pellets=1, side=0, flash=8, flash_px=18,
                         shells=0, smoke=2, dust=2),
    "thunder_bullet": dict(look="bolt", speed=[13, 15], range=[0.9, 1.05], pellets=1, side=0, flash=6, flash_px=16,
                           shells=1, smoke=0, dust=2),
}
IMPACT_LIFE = {"tracer": 14, "pellet": 11, "slug": 26, "orb": 36, "rail": 28, "rocket": 32, "drill": 22, "bolt": 22}
EXPLODES = ["orb", "rocket", "bolt", "drill"]   # these go off at the end of their range too

TRACER_TAIL = 3.2        # tracer streak, ticks of flight behind the head
FADE_TAIL = 0.25         # a round that hits nothing fades over this last part of its range
CASING_LIFE = 28
CASING_G = 0.32          # casing gravity, px per tick^2 (x scale)
SMOKE_LIFE = 40
GAT_GAP = [4.0, 1.0]     # gatling: ticks between rounds, first -> full speed
GAT_RAMP = 0.45          # gatling: part of the firing time it takes to reach full speed
GAT_BARREL = 1.0472      # gatling: barrel turn between rounds, radians
GAT_SPIN = 0.55          # gatling: barrel spin at full speed, radians per tick
GAT_SPIN_DOWN = 18
RAIL_HIT = 3             # sniper: ticks the rail line hits for
RAIL_DELAY = 5           # sniper: the hit bursts this many ticks after the line
CHARGE_P = 14            # charged blast: ticks a gathering streak takes to rush in
CHARGE_RING = 9          # charged blast: a closing ring every this many ticks
ROCKET_ARC = 0.55        # rocket: sideways bow of the flight, times the distance
ROCKET_EASE = 1.35       # rocket: speeds up along its flight
ROCKET_MIN = 12          # rocket: shortest flight, ticks
ROCKET_PUFF = 2          # rocket: a smoke puff every this many ticks
DRILL_SPIN = 0.22        # drill: groove turns per tick
DRILL_RING = 5           # drill: a wind ring every this many ticks
BOLT_SEG = 20            # thunder: lightning trail segment, px
BRASS = (255, 198, 92)
HULL = (214, 44, 40)
SMOKE = (96, 90, 84)
STEEL = (226, 230, 236)


# ---------------------------------------------------------------- timeline
def _g(P):
    return GUNS[S._style(P)]


def _cad(P):
    return max(1, F.trunc(float(P.get("swing_ticks") or 1)))


def _hold(P):
    return max(0, F.trunc(float(P.get("hold_ticks") or 0)))


def launches(P):
    """Ticks the shots (volleys) fire on."""
    st = S._style(P)
    cad, hold = _cad(P), _hold(P)
    if st == "charged_blast":
        return [cad + hold]
    if st == "sniper_rail":
        return [cad]
    if st == "gatling":
        out, t, end = [], float(cad), cad + hold
        ramp = max(1.0, hold * GAT_RAMP)
        while t <= end:
            out.append(F.trunc(t))
            u = min(1.0, (t - cad) / ramp)
            t += GAT_GAP[0] + (GAT_GAP[1] - GAT_GAP[0]) * u
        return out
    return [k * cad for k in range(hold // cad + 1)]


def _flight_max(P):
    g = _g(P)
    if g["look"] == "rail":
        return RAIL_HIT
    n = int(math.ceil(float(P["length"]) * g["range"][1] / g["speed"][0]))
    if g["look"] == "rocket":
        n = max(n, ROCKET_MIN)
    return n


def active_ticks(P):
    return launches(P)[-1] + _flight_max(P) + 1


def total_ticks(P):
    g = _g(P)
    tail = max(IMPACT_LIFE[g["look"]], SMOKE_LIFE, CASING_LIFE)
    if S._style(P) == "gatling":
        tail += GAT_SPIN_DOWN
    if g["look"] == "rail":
        tail += _hold(P) + RAIL_DELAY
    return active_ticks(P) + tail


def _at(lst, k):
    return lst[max(0, min(k, len(lst) - 1))]


def _tracks(inst):
    return (inst.fx.get("motion") or {}).get("aim") == "target"


def _aim(inst, k):
    """(origin, forward) of the gun at tick k: at the target when tracking."""
    ox, oy = _at(inst.tq_path, k)
    f = inst.tq_f
    if _tracks(inst):
        tx, ty = _at(inst.tq_tp, k)
        dx, dy = tx - ox, ty - oy
        d = math.hypot(dx, dy)
        if d > 1:
            f = (dx / d, dy / d)
    return ox, oy, f


# ---------------------------------------------------------------- rounds
class Round:
    """One round: everything about it is rolled from the seed."""
    __slots__ = ("i", "v", "j", "b", "look", "sp", "ang", "size", "tint", "rng", "flight", "arc", "fr", "ox", "oy")

    def __init__(self, inst, i, v, j, b, ps):
        P = inst.fx["params"]
        st = S._style(P)
        g = GUNS[st]
        r = S.rng_for(inst.seed, i, 43)
        su = r.uniform(g["speed"][0], g["speed"][1])
        n = g["pellets"]
        span = float(P.get("span") or 0)
        if n > 1:
            a = ((j + 0.5) / n - 0.5) * span + r.uniform(-0.5, 0.5) * span / n
        else:
            a = r.uniform(-0.5, 0.5) * span
        ru = r.uniform(g["range"][0], g["range"][1])
        self.i, self.v, self.j, self.b = i, v, j, b
        self.look = g["look"]
        self.ang = a * S.D
        self.size = r.uniform(0.85, 1.15)
        self.tint = r.uniform(0.0, 0.35)
        ox, oy, f = _aim(inst, b)
        m = (1 if f[0] >= 0 else -1) if _tracks(inst) else inst.tq_m
        self.fr = S.Frame(0.0, 0.0, f, m)
        sd = float(g["side"]) * ps
        if st == "gatling":
            lat = sd * math.sin(v * GAT_BARREL)
        else:
            lat = sd if v % 2 == 0 else -sd
        so = self.fr.d(0.0, lat)
        self.ox, self.oy = ox + so[0], oy + so[1]
        self.sp = su * ps
        self.arc = 0.0
        L = float(P["length"])
        if self.look == "rail":
            self.rng = L * ps
            self.flight = RAIL_HIT
        elif self.look == "rocket":
            dist = L * ru * ps
            if _tracks(inst):
                tx, ty = _at(inst.tq_tp, b)
                dist = min(dist, math.hypot(tx - self.ox, ty - self.oy))
            dist = max(dist, 30.0 * ps)
            self.rng = dist
            self.flight = max(ROCKET_MIN, int(math.ceil(dist / self.sp)))
            self.arc = (1 if v % 2 == 0 else -1) * r.uniform(0.6, 1.0) * ROCKET_ARC * dist
        else:
            self.rng = L * ru * ps
            self.flight = max(1, int(math.ceil(L * ru / su)))

    def pos(self, k):
        """World position k ticks after launch."""
        if self.look == "rocket":
            u = max(0.0, min(1.0, k / float(self.flight)))
            e = u ** ROCKET_EASE
            lx = 2 * (1 - e) * e * self.rng * 0.4 + e * e * self.rng
            ly = 2 * (1 - e) * e * self.arc
            d = self.fr.d(lx, ly)
        else:
            d0 = self.sp * k
            d = self.fr.d(math.cos(self.ang) * d0, math.sin(self.ang) * d0)
        return self.ox + d[0], self.oy + d[1]

    def head(self, k):
        """Unit direction of travel k ticks after launch."""
        if self.look == "rocket":
            x1, y1 = self.pos(k)
            x0, y0 = self.pos(k - 0.5)
            d = math.hypot(x1 - x0, y1 - y0)
            if d > 1e-6:
                return (x1 - x0) / d, (y1 - y0) / d
            return self.fr.d(1.0, 0.0)
        return self.fr.d(math.cos(self.ang), math.sin(self.ang))

    def end(self, inst):
        """(tick it stops, stopped by a hit?)."""
        h = inst.tq_ki.get(self.i)
        if h is not None:
            return h[0], True
        return self.b + self.flight, False


def _rounds(inst, ps):
    """Every round fired up to now, in firing order."""
    P = inst.fx["params"]
    n = _g(P)["pellets"]
    out = []
    for v, b in enumerate(launches(P)):
        if b > inst.age:
            break
        for j in range(n):
            out.append(Round(inst, v * n + j, v, j, b, ps))
    return out


def _live(inst, ps):
    """[(round, position)] for the rounds in flight this tick (not the rail)."""
    out = []
    t = inst.age
    for s in _rounds(inst, ps):
        if s.look == "rail":
            continue
        e, _stopped = s.end(inst)
        if t < e:
            out.append((s, s.pos(t - s.b)))
    return out


def _rail_line(s):
    d = s.fr.d(s.rng, 0.0)
    return s.ox, s.oy, s.ox + d[0], s.oy + d[1]


# ---------------------------------------------------------------- public
def hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    P = inst.fx["params"]
    r0 = float(P["radius"]) * ps
    if _g(P)["look"] == "rail":
        for s in _rounds(inst, ps):
            if s.b <= inst.age < s.b + RAIL_HIT:
                x0, y0, x1, y1 = _rail_line(s)
                if F.seg_dist(tx, ty, x0, y0, x1, y1) <= hr + r0:
                    return True
        return False
    for (s, (x, y)) in _live(inst, ps):
        if math.hypot(x - tx, y - ty) <= hr + r0 * s.size:
            return True
    return False


def body(inst, ps):
    """Bullets never clash as a blade."""
    return None


def on_hit(inst, x, y, ps):
    P = inst.fx["params"]
    if _g(P)["look"] == "rail":
        for s in _rounds(inst, ps):
            if s.b <= inst.age < s.b + RAIL_HIT:
                x0, y0, x1, y1 = _rail_line(s)
                dx, dy = x1 - x0, y1 - y0
                L2 = dx * dx + dy * dy
                u = max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / L2)) if L2 > 0 else 0.0
                inst.tq_imp.append((inst.age, x0 + dx * u, y0 + dy * u))
        return
    best, bd = None, None
    for (s, (sx, sy)) in _live(inst, ps):
        d = math.hypot(sx - x, sy - y)
        if bd is None or d < bd:
            best, bd = (s, sx, sy), d
    if best is None:
        return
    s, sx, sy = best
    if s.look == "drill":
        inst.tq_imp.append((inst.age, sx, sy))   # it drills on through
    else:
        inst.tq_ki[s.i] = (inst.age, sx, sy)


# ================================================================ drawing
def _blast_at(inst, s):
    """(tick, x, y, stopped) where the round ends, or None when it just fades out."""
    e, stopped = s.end(inst)
    if stopped:
        h = inst.tq_ki[s.i]
        return e, h[1], h[2], True
    if s.look in EXPLODES:
        x, y = s.pos(s.flight)
        return e, x, y, False
    return None


def _puffs(pen, inst, key, x, y, a, life, n, size, ps, smoke, rise):
    if a < 0 or a >= life or n <= 0:
        return
    q = a / float(life)
    for j in range(n):
        r = S.rng_for(inst.seed, key, 300 + j)
        an = r.uniform(0, math.pi * 2)
        dr = r.uniform(0.2, 1.0) * size * S.ease_out3(a / 14.0)
        px = x + math.cos(an) * dr
        py = y + math.sin(an) * dr - r.uniform(0.3, 1.0) * rise * ps * a
        rad = size * r.uniform(0.5, 0.9) * (0.5 + 0.8 * S.ease_out3(a / 18.0))
        pen.glow(px, py, rad, smoke, 90 * (1 - q) ** 1.5 * min(1.0, a / 3.0), 0.6)


def _casing(pen, inst, key, ox, oy, fx_, a, ps, kind):
    if a < 0 or a >= CASING_LIFE:
        return
    r = S.rng_for(inst.seed, key, 200)
    sg = 1 if fx_ >= 0 else -1
    vx = -sg * r.uniform(1.0, 2.2) * ps
    vy = -r.uniform(2.4, 3.8) * ps
    x = ox + vx * a
    y = oy + vy * a + 0.5 * CASING_G * ps * a * a
    rt = r.uniform(0, math.pi * 2) + sg * a * r.uniform(0.35, 0.6)
    fade = 1.0 if a < CASING_LIFE - 8 else (CASING_LIFE - a) / 8.0
    hl = (5.5 if kind == 2 else 3.6) * ps / 2
    hw = (2.4 if kind == 2 else 1.5) * ps / 2
    ux, uy = math.cos(rt), math.sin(rt)
    nx, ny = -uy, ux

    def box(a0, a1):
        return [(x + ux * a0 + nx * hw, y + uy * a0 + ny * hw), (x + ux * a1 + nx * hw, y + uy * a1 + ny * hw),
                (x + ux * a1 - nx * hw, y + uy * a1 - ny * hw), (x + ux * a0 - nx * hw, y + uy * a0 - ny * hw)]

    if kind == 2:
        pen.poly(box(-hl, hl * 0.35), HULL, 235 * fade)
        pen.poly(box(hl * 0.35, hl), BRASS, 235 * fade)
    else:
        pen.poly(box(-hl, hl), BRASS, 235 * fade)
    pen.line(x - ux * hl * 0.8 + nx * hw * 0.4, y - uy * hl * 0.8 + ny * hw * 0.4,
             x + ux * hl * 0.8 + nx * hw * 0.4, y + uy * hl * 0.8 + ny * hw * 0.4,
             S.mix(BRASS, S.HOT, 0.6), 200 * fade, 0.6 * ps)


def _sparks(pen, inst, key, x, y, ang, cone, a, n, c, ps, sp_lo, sp_hi, life0):
    for j in range(n):
        r = S.rng_for(inst.seed, key, 500 + j)
        life = life0 * (0.6 + 0.6 * r())
        if a >= life:
            continue
        an = ang + r.uniform(-cone, cone) * S.D
        sp = r.uniform(sp_lo, sp_hi) * ps
        fd = S.drag_dist(0.86, a)
        sx = x + math.cos(an) * sp * fd
        sy = y + math.sin(an) * sp * fd + 0.1 * ps * a * a
        dk = 0.86 ** a
        qq = a / life
        pen.line(sx, sy, sx - math.cos(an) * sp * dk * 1.6, sy - math.sin(an) * sp * dk * 1.6, S.mix(S.HOT, c, qq),
                 255 * (1 - qq), 1.3 * ps)


def _jag(inst, key, x0, y0, x1, y1, n, amp):
    """A jagged lightning line from (x0, y0) to (x1, y1)."""
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    r = S.rng_for(inst.seed, key, 700)
    pts = [(x0, y0)]
    for m in range(1, n):
        u = m / float(n)
        o = r.uniform(-1.0, 1.0) * amp
        pts.append((x0 + dx * u + nx * o, y0 + dy * u + ny * o))
    pts.append((x1, y1))
    return pts


def _spikes(pen, x, y, ang, n, r_out, r_in, c, a):
    pts = []
    for j in range(2 * n):
        rr = r_out if j % 2 == 0 else r_in
        an = ang + math.pi * j / n
        pts.append((x + math.cos(an) * rr, y + math.sin(an) * rr))
    pen.poly(pts, c, a)


def _heavy(pen, inst, key, c, ps, x, y, ang, a, life, B, dens):
    """A heavy hit: flash, spiked star, shockwave rings across the line, speed lines, sparks."""
    if a < 0 or a >= life:
        return
    q = a / float(life)
    if a < 5:
        pen.glow(x, y, B * (0.6 + 0.8 * S.ease_out3(a / 5.0)), S.HOT, 255 * (1 - a / 5.0))
    if a < 9:
        e = S.ease_out3(a / 4.0)
        qs = a / 9.0
        _spikes(pen, x, y, ang + 0.2 * qs, 6, B * (0.5 + 0.9 * e), B * (0.2 + 0.2 * e), c, 225 * (1 - qs))
        _spikes(pen, x, y, ang + 0.2 * qs, 6, B * (0.3 + 0.5 * e), B * (0.12 + 0.1 * e), S.HOT, 255 * (1 - qs) ** 1.5)
    pen.glow(x, y, B * (0.9 + 0.7 * S.ease_out3(q)), c, 140 * (1 - q), 0.4)
    ca, sa = math.cos(ang), math.sin(ang)
    for (d0, k) in ((0, 1.0), (3, 1.4)):
        aa = a - d0
        if aa < 0:
            continue
        qq = aa / float(life - d0)
        e = S.ease_out3(qq)
        cx, cy = x + ca * B * 0.4 * e * k, y + sa * B * 0.4 * e * k
        pen.ring(cx, cy, B * (0.15 + 0.45 * e) * k, B * (0.3 + 1.5 * e) * k, ang, c, 210 * (1 - qq), 2.6 * ps * (1 - qq) + 0.2)
    if a < 11:
        ql = a / 11.0
        for j in range(10):
            r = S.rng_for(inst.seed, key, 600 + j)
            an = r.uniform(0, math.pi * 2)
            r1 = B * (0.4 + 1.5 * S.ease_out3(ql)) * r.uniform(0.8, 1.2)
            ln = B * r.uniform(0.4, 0.8) * (1 - ql)
            cb, sb = math.cos(an), math.sin(an)
            pen.line(x + cb * r1, y + sb * r1, x + cb * (r1 + ln), y + sb * (r1 + ln), S.mix(S.HOT, c, ql), 230 * (1 - ql), 1.3 * ps)
    _sparks(pen, inst, key, x, y, ang + math.pi, 80, a, max(0, F.jround(9 * dens)), c, ps, 3.0, 7.5, 18)


def _explode(pen, inst, key, c, ps, x, y, a, life, B, dens):
    """Fireball: flash, swelling fire, two rings, debris."""
    if a < 0 or a >= life:
        return
    q = a / float(life)
    ee = S.ease_out3(a / 9.0)
    if a < 6:
        pen.glow(x, y, B * (0.8 + 0.9 * S.ease_out3(a / 6.0)), S.HOT, 255 * (1 - a / 6.0))
    pen.glow(x, y, B * (1.0 + 0.9 * ee), c, 215 * (1 - q), 0.45)
    pen.glow(x, y, B * (0.55 + 0.5 * ee), S.mix(c, S.HOT, 0.6), 240 * (1 - q) ** 2)
    for (d0, k) in ((0, 1.0), (4, 1.5)):
        aa = a - d0
        if aa < 0:
            continue
        qq = aa / float(life - d0)
        rr = B * (0.5 + 1.6 * S.ease_out3(qq)) * k
        pen.ring(x, y, rr, rr * 0.8, 0.0, c, 190 * (1 - qq), 3.0 * ps * (1 - qq) + 0.2)
    _sparks(pen, inst, key, x, y, 0.0, 180, a, max(0, F.jround(12 * dens)), c, ps, 3.0, 8.0, 22)


def _strike(pen, inst, key, c, ps, x, y, a, life, B, dens):
    """Lightning drops from the sky onto (x, y) and crackles outward."""
    if a < 0 or a >= life:
        return
    q = a / float(life)
    if a < 10:
        r = S.rng_for(inst.seed, key, 800)
        top_x = x + r.uniform(-30, 30) * ps
        fl = 0.75 + 0.25 * math.sin(a * 3.1)
        pts = _jag(inst, key * 64 + a // 2, top_x, y - 170 * ps, x, y, 9, 12 * ps)
        pen.polyline(pts, c, 210 * fl * (1 - a / 10.0), 4.2 * ps)
        pen.polyline(pts, S.HOT, 255 * (1 - a / 10.0), 1.6 * ps)
    if a < 5:
        pen.glow(x, y, B * (0.8 + 0.8 * S.ease_out3(a / 5.0)), S.HOT, 255 * (1 - a / 5.0))
    pen.glow(x, y, B * (0.9 + 0.6 * S.ease_out3(q)), c, 160 * (1 - q), 0.4)
    rr = B * (0.4 + 1.4 * S.ease_out3(q))
    pen.ring(x, y, rr, rr * 0.45, 0.0, c, 190 * (1 - q), 2.4 * ps * (1 - q) + 0.2)
    if a < 14:
        for j in range(6):
            r2 = S.rng_for(inst.seed, key, 820 + j)
            an = r2.uniform(0, math.pi * 2)
            ln = B * r2.uniform(0.6, 1.1)
            pts = _jag(inst, key * 64 + 32 + j + (a // 2) * 6, x, y, x + math.cos(an) * ln, y + math.sin(an) * ln, 4,
                       5 * ps)
            pen.polyline(pts, S.mix(c, S.HOT, 0.5), 230 * (1 - a / 14.0), 1.2 * ps)
    _sparks(pen, inst, key, x, y, -math.pi / 2, 120, a, max(0, F.jround(6 * dens)), c, ps, 2.5, 6.0, 16)


def _shatter(pen, inst, key, c, ps, x, y, ang, a, life, B, dens):
    """The drill bursts into spinning shards at the end of its range."""
    if a < 0 or a >= life:
        return
    q = a / float(life)
    if a < 5:
        pen.glow(x, y, B * (0.6 + 0.6 * S.ease_out3(a / 5.0)), S.HOT, 255 * (1 - a / 5.0))
    pen.glow(x, y, B * (0.7 + 0.6 * S.ease_out3(q)), c, 150 * (1 - q), 0.4)
    for j in range(max(0, F.jround(8 * dens))):
        r = S.rng_for(inst.seed, key, 900 + j)
        an = ang + r.uniform(-70, 70) * S.D
        sp = r.uniform(2.5, 6.0) * ps
        fd = S.drag_dist(0.9, a)
        sx, sy = x + math.cos(an) * sp * fd, y + math.sin(an) * sp * fd
        sz = B * r.uniform(0.15, 0.3)
        rt = r.uniform(0, math.pi * 2) + a * r.uniform(-0.4, 0.4)
        pts = [(sx + math.cos(rt + k * 2.1) * sz * (1.0 if k == 0 else 0.5), sy + math.sin(rt + k * 2.1) * sz * (1.0 if k == 0 else 0.5))
               for k in range(3)]
        pen.poly(pts, S.mix(c, S.HOT, 0.5), 230 * (1 - q))


def _muzzle(pen, inst, g, s, k, c, ps, P):
    if k >= g["flash"]:
        return
    q = k / float(g["flash"])
    x, y = s.ox, s.oy
    ux, uy = s.head(0)
    fs = float(g["flash_px"]) * ps * s.size * (1 - 0.35 * q)
    look = s.look
    pen.glow(x, y, fs * 1.3, c, 210 * (1 - q))
    pen.glow(x, y, fs * 0.5, S.HOT, 255 * (1 - q))
    S._star(pen, x, y, ux, uy, fs * 1.4, fs * 0.6, S.HOT, 235 * (1 - q), 1.6 * ps)
    for (j, dg) in enumerate((-28, 0, 28)):
        r = S.rng_for(inst.seed, s.i, 120 + j)
        ln = fs * (1.2 if dg == 0 else 0.75) * r.uniform(0.8, 1.2) * (1 - 0.5 * q)
        vx, vy = F.rot([ux, uy], dg)
        pen.diamond(x, y, x + vx * ln, y + vy * ln, fs * 0.22, S.mix(c, S.HOT, 0.5), 230 * (1 - q))
    ang = math.atan2(uy, ux)
    e = S.ease_out3(q)
    if look == "pellet":
        half = (float(P.get("span") or 0) * 0.6 + 6) * S.D
        ln = fs * 2.4 * (0.6 + 0.4 * e)
        pts = [(x, y)]
        for m in range(7):
            an = ang - half + 2 * half * m / 6.0
            pts.append((x + math.cos(an) * ln, y + math.sin(an) * ln))
        pen.poly(pts, c, 120 * (1 - q))
        pen.ring(x + ux * fs * 1.4 * e, y + uy * fs * 1.4 * e, fs * (0.3 + 0.5 * e), fs * (0.6 + 1.3 * e), ang, S.HOT,
                 200 * (1 - q), 2.0 * ps * (1 - q) + 0.2)
    elif look in ("slug", "orb", "rail", "drill"):
        if look == "slug":
            for sd in (1, -1):
                jx, jy = x + ux * fs * 0.25, y + uy * fs * 0.25
                pen.diamond(jx, jy, jx - uy * sd * fs * 0.8, jy + ux * sd * fs * 0.8, fs * 0.16, S.HOT, 220 * (1 - q))
        for (d0, kk) in ((0, 1.0), (2, 1.5)):
            aa = k - d0
            if aa < 0:
                continue
            qq = aa / float(g["flash"] - d0) if g["flash"] > d0 else 1.0
            ee = S.ease_out3(qq)
            pen.ring(x + ux * fs * 0.6 * ee * kk, y + uy * fs * 0.6 * ee * kk, fs * (0.25 + 0.4 * ee) * kk,
                     fs * (0.5 + 1.1 * ee) * kk, ang, S.HOT, 200 * (1 - qq), 2.2 * ps * (1 - qq) + 0.2)
    elif look == "rocket":
        pen.diamond(x, y, x - ux * fs * 1.6, y - uy * fs * 1.6, fs * 0.35, S.mix(c, S.HOT, 0.3), 200 * (1 - q))
    if S._style(P) == "dual_pistols":
        # gun-kata: the swing arc of the hand that fired
        sd = 1 if s.v % 2 == 0 else -1
        pts = []
        for m in range(9):
            an = ang + sd * (-0.9 + 1.4 * m / 8.0)
            pts.append((x + math.cos(an) * 14 * ps, y + math.sin(an) * 14 * ps))
        pen.polyline(pts, S.mix(c, S.HOT, 0.4), 200 * (1 - q), 2.0 * ps * (1 - q) + 0.3)


def _fade(s, k, stopped):
    if stopped:
        return 1.0
    return max(0.0, min(1.0, (s.flight - k) / max(1.0, s.flight * FADE_TAIL)))


def _round(pen, inst, s, k, t, c, tint, ps, P, stopped):
    """A round in flight, k ticks after launch."""
    r = float(P["radius"]) * ps * s.size
    x, y = s.pos(k)
    ux, uy = s.head(k)
    look = s.look
    fa = _fade(s, k, stopped) if look in ("tracer", "pellet", "slug") else 1.0
    if look == "tracer":
        tx, ty = s.pos(max(0.0, k - TRACER_TAIL))
        pen.diamond(tx, ty, x, y, r * 1.1, c, 150 * fa)
        pen.line(tx, ty, x, y, tint, 230 * fa, r * 0.9)
        pen.glow(x, y, r * 3.0, c, 110 * fa)
        pen.glow(x, y, r * 1.2, S.HOT, 255 * fa, 0.7)
    elif look == "pellet":
        tx, ty = s.pos(max(0.0, k - 1.6))
        pen.diamond(tx, ty, x, y, r * 0.9, c, 160 * fa)
        pen.glow(x, y, r * 2.4, c, 120 * fa)
        pen.glow(x, y, r, S.HOT, 255 * fa, 0.7)
    elif look == "slug":
        ang = math.atan2(uy, ux)
        for j in range(4):
            kj = k - (j + 1) * 0.8
            if kj < 0:
                break
            gx, gy = s.pos(kj)
            pen.ring(gx, gy, r * 0.7, r * (1.6 + 0.5 * j), ang, S.mix(c, S.HOT, 0.3), 170 * (1 - j / 4.0) * fa, 1.3 * ps)
        tx, ty = s.pos(max(0.0, k - 2.6))
        pen.diamond(tx, ty, x, y, r * 1.3, c, 150 * fa)
        pen.diamond(tx, ty, x, y, r * 0.5, S.HOT, 230 * fa)
        pen.glow(x, y, r * 3.6, c, 130 * fa)
        pen.glow(x, y, r * 1.5, S.HOT, 255 * fa, 0.7)
    elif look == "orb":
        fl = 0.88 + 0.12 * math.sin(t * 1.7)
        for (j, al) in ((4, 40), (2, 70)):
            gx, gy = s.pos(max(0.0, k - j))
            pen.glow(gx, gy, r * 1.8, c, al)
        tx, ty = s.pos(max(0.0, k - 5))
        pen.diamond(tx, ty, x, y, r * 1.0, c, 120)
        pen.diamond(tx, ty, x, y, r * 0.45, tint, 200)
        pen.glow(x, y, r * 2.6 * fl, c, 140)
        pen.glow(x, y, r * 1.4, tint, 230)
        pen.glow(x, y, r * 0.7, S.HOT, 255, 0.75)
        for j in range(2):
            pen.ring(x, y, r * 1.3, r * 0.45, t * 0.35 + j * math.pi / 2, S.HOT, 170, 1.4 * ps)
    elif look == "rocket":
        r2 = S.rng_for(inst.seed, s.i, 140 + t % 16)
        ln = r * (2.6 + 1.6 * r2())
        bx, by = x - ux * r * 1.6, y - uy * r * 1.6
        pen.diamond(bx, by, bx - ux * ln, by - uy * ln, r * 0.55, c, 220)
        pen.diamond(bx, by, bx - ux * ln * 0.6, by - uy * ln * 0.6, r * 0.25, S.HOT, 255)
        pen.glow(bx, by, r * 2.2, c, 150)
    elif look == "drill":
        R = r
        nx, ny = -uy, ux
        bx, by = x - ux * R * 0.6, y - uy * R * 0.6
        tipx, tipy = x + ux * R * 2.4, y + uy * R * 2.4
        # spiral of wind behind it
        for sd in (1, -1):
            pts = []
            for m in range(15):
                db = m * R * 0.9
                lat = sd * math.sin(t * 0.9 + m * 0.7) * R * (1.3 - m * 0.06)
                pts.append((bx - ux * db + nx * lat, by - uy * db + ny * lat))
            pen.polyline(pts, c, 150, 1.4 * ps)
        pen.glow(x, y, R * 2.8, c, 120)
        pen.poly([(tipx, tipy), (bx + nx * R * 1.05, by + ny * R * 1.05), (bx - nx * R * 1.05, by - ny * R * 1.05)], c, 200)
        pen.poly([(tipx, tipy), (bx + nx * R * 0.55, by + ny * R * 0.55), (bx - nx * R * 0.55, by - ny * R * 0.55)],
                 S.mix(c, S.HOT, 0.6), 220)
        for j in range(4):
            p = S.frac(t * DRILL_SPIN + j / 4.0)
            p2 = min(1.0, p + 0.18)
            ax, ay = bx + (tipx - bx) * p + nx * R * 1.05 * (1 - p), by + (tipy - by) * p + ny * R * 1.05 * (1 - p)
            cx, cy = bx + (tipx - bx) * p2 - nx * R * 1.05 * (1 - p2), by + (tipy - by) * p2 - ny * R * 1.05 * (1 - p2)
            pen.line(ax, ay, cx, cy, S.HOT, 200, 1.2 * ps)
    elif look == "bolt":
        d = s.sp * k
        d0 = max(0.0, d - 160 * ps)
        n = max(1, min(24, int((d - d0) / (BOLT_SEG * ps)) + 1))
        rr = S.rng_for(inst.seed, s.i, 400 + (t // 2))
        pts = []
        for m in range(n + 1):
            dm = d0 + (d - d0) * m / float(n)
            o = 0.0 if m == n else rr.uniform(-7, 7) * ps
            w = s.fr.d(math.cos(s.ang) * dm, math.sin(s.ang) * dm)
            pts.append((s.ox + w[0] - uy * o, s.oy + w[1] + ux * o))
        fl = 0.7 + 0.3 * math.sin(t * 2.7 + s.i)
        pen.polyline(pts, c, 150 * fl, 2.6 * ps)
        pen.polyline(pts, S.HOT, 200 * fl, 1.0 * ps)
        tx, ty = s.pos(max(0.0, k - 2))
        pen.diamond(tx, ty, x, y, r * 0.9, c, 160)
        pen.glow(x, y, r * 3.0, c, 140)
        pen.glow(x, y, r * 1.4, S.HOT, 255, 0.7)
        for j in range(3):
            ra = S.rng_for(inst.seed, s.i, 420 + (t // 2) * 3 + j)
            an = ra.uniform(0, math.pi * 2)
            px, py = x, y
            arc = [(px, py)]
            for m in range(3):
                an += ra.uniform(-0.9, 0.9)
                px, py = px + math.cos(an) * r * 1.6, py + math.sin(an) * r * 1.6
                arc.append((px, py))
            pen.polyline(arc, c, 150, 2.4 * ps)
            pen.polyline(arc, S.HOT, 220, 1.1 * ps)


def _impact(pen, inst, s, a, x, y, stopped, c, ps, P, dens):
    look = s.look
    life = IMPACT_LIFE[look]
    B = float(P["thickness"]) * ps * s.size
    ux, uy = s.head(s.flight if not stopped else max(0, inst.tq_ki[s.i][0] - s.b))
    ang = math.atan2(uy, ux)
    key = s.i * 4 + 1
    if look in ("tracer", "pellet"):
        if a >= life:
            return
        sc = 0.7 if look == "pellet" else 1.0
        q = a / float(life)
        if a < 3:
            pen.glow(x, y, B * (0.5 + 0.5 * S.ease_out3(a / 3.0)) * sc, S.HOT, 255 * (1 - a / 3.0))
        pen.glow(x, y, B * (0.8 + 0.8 * S.ease_out3(q)) * sc, c, 180 * (1 - q), 0.4)
        _sparks(pen, inst, key, x, y, ang + math.pi, 70, a, max(0, F.jround(4 * dens)), c, ps, 2.0, 5.5, 12)
    elif look == "slug":
        _heavy(pen, inst, key, c, ps, x, y, ang, a, life, B, dens)
    elif look in ("orb", "rocket"):
        _explode(pen, inst, key, c, ps, x, y, a, life, B, dens)
    elif look == "bolt":
        _strike(pen, inst, key, c, ps, x, y, a, life, B, dens)
    elif look == "drill":
        _shatter(pen, inst, key, c, ps, x, y, ang, a, life, B, dens)


def _gat_phi(P, t):
    cad, hold = _cad(P), _hold(P)
    w = GAT_SPIN
    if t <= cad:
        return 0.5 * w * t * t / cad
    if t <= cad + hold:
        return 0.5 * w * cad + w * (t - cad)
    k = min(t - cad - hold, GAT_SPIN_DOWN)
    return 0.5 * w * cad + w * hold + w * (k - 0.5 * k * k / GAT_SPIN_DOWN)


def _draw_gatling(pen, inst, P, c, ps, t, fired, total):
    cad, hold = _cad(P), _hold(P)
    endf = cad + hold
    if t > endf + GAT_SPIN_DOWN:
        return
    ox, oy, f = _aim(inst, t)
    fade = 1.0 if t <= endf else 1 - (t - endf) / float(GAT_SPIN_DOWN)
    phi = _gat_phi(P, t)
    nx, ny = -f[1], f[0]
    mx, my = ox + f[0] * 4 * ps, oy + f[1] * 4 * ps
    pen.ring(mx, my, 2.0 * ps, 6.0 * ps, math.atan2(f[1], f[0]), c, 170 * fade, 1.2 * ps)
    for j in range(6):
        an = phi + j * math.pi / 3
        lat, dep = math.cos(an) * 5 * ps, math.sin(an) * 1.6 * ps
        bx, by = mx + nx * lat + f[0] * dep, my + ny * lat + f[1] * dep
        pen.glow(bx, by, 2.6 * ps, c, 200 * fade * (0.6 + 0.4 * math.sin(an)))
    heat = fired / float(max(1, total))
    pen.glow(mx, my, 10 * ps, S.mix((255, 90, 30), c, 0.3), 170 * heat * fade)
    pen.glow(mx, my, 4 * ps, S.mix((255, 200, 120), S.HOT, 0.3), 200 * heat * fade)


def _draw_charge(pen, inst, P, c, tint, ps, t, b, dens):
    if t > b:
        return
    cad = _cad(P)
    ox, oy, f = _aim(inst, t)
    mx, my = ox + f[0] * 6 * ps, oy + f[1] * 6 * ps
    R = float(P["radius"]) * ps
    e = S.ease_out3(t / float(cad))
    fl = 0.85 + 0.15 * math.sin(t * 1.3)
    rr = R * (0.25 + 0.85 * e)
    pen.glow(mx, my, rr * 2.4 * fl, c, 150)
    pen.glow(mx, my, rr * 1.3, tint, 220)
    pen.glow(mx, my, rr * 0.6, S.HOT, 255, 0.75)
    for j in range(max(0, F.jround(12 * dens))):
        r0 = S.rng_for(inst.seed, j, 640)
        off = r0.uniform(0, CHARGE_P)
        cyc = int((t + off) // CHARGE_P)
        p = S.frac((t + off) / float(CHARGE_P))
        r = S.rng_for(inst.seed, j, 650 + cyc)
        an = r.uniform(0, math.pi * 2)
        rad = r.uniform(36, 70) * ps
        d = rad * (1 - S.ease_in3(p)) + rr * 0.6
        d2 = d + rad * 0.25 * (1 - p)
        ca, sa = math.cos(an), math.sin(an)
        pen.line(mx + ca * d, my + sa * d, mx + ca * d2, my + sa * d2, S.mix(c, S.HOT, p), 230 * p, 1.4 * ps)
    if t < cad:
        for m in range(2):
            q = S.frac((t + m * CHARGE_RING) / float(2 * CHARGE_RING))
            rad = 50 * ps * (1 - S.ease_in3(q)) + rr * 0.3
            pen.ring(mx, my, rad, rad, 0.0, c, 180 * q, 1.6 * ps)
    else:
        a = t - cad
        if a < 5:
            S._star(pen, mx, my, 1.0, 0.0, R * 3.2 * (1 - a / 5.0), R * 3.2 * (1 - a / 5.0), S.HOT, 255 * (1 - a / 5.0),
                    2.0 * ps)
        if e > 0.6:
            for j in range(2):
                ra = S.rng_for(inst.seed, j, 680 + t // 2)
                an = ra.uniform(0, math.pi * 2)
                pts = _jag(inst, 690 + (t // 2) * 2 + j, mx, my, mx + math.cos(an) * rr * 2.2, my + math.sin(an) * rr * 2.2,
                           3, 3 * ps)
                pen.polyline(pts, S.HOT, 200, 1.0 * ps)


def _draw_aim(pen, inst, P, c, ps, t, b):
    if t >= b:
        return
    ox, oy, f = _aim(inst, t)
    L = float(P["length"]) * ps
    e = S.ease_out3(t / float(max(1, b)))
    fl = 0.6 + 0.4 * math.sin(t * 2.1)
    ex, ey = ox + f[0] * L, oy + f[1] * L
    pen.line(ox, oy, ex, ey, c, 120 * fl, 1.0 * ps)
    pen.line(ox, oy, ex, ey, S.HOT, 150 * fl, 0.5 * ps)
    if _tracks(inst):
        tx, ty = _at(inst.tq_tp, t)
        if math.hypot(tx - ox, ty - oy) < L:
            ex, ey = tx, ty
    rad = (26 - 18 * e) * ps
    pen.ring(ex, ey, rad, rad, 0.0, c, 210, 1.4 * ps)
    rt = (1 - e) * math.pi / 2
    for j in range(4):
        an = rt + j * math.pi / 2
        ca, sa = math.cos(an), math.sin(an)
        pen.line(ex + ca * rad * 0.6, ey + sa * rad * 0.6, ex + ca * rad * 1.4, ey + sa * rad * 1.4, S.HOT, 230, 1.2 * ps)
    if e > 0.8 and t % 4 < 2:
        pen.glow(ex, ey, 4 * ps, S.HOT, 255)
    if b - t <= 6:
        q = (b - t) / 6.0
        S._star(pen, ox, oy, f[0], f[1], 14 * ps * (1 - q) + 2, 14 * ps * (1 - q) + 2, S.HOT, 255 * (1 - q), 1.4 * ps)


def _draw_rail(pen, inst, s, P, c, ps, t, dens):
    k = t - s.b
    linger = max(1, _hold(P))
    if k < 0:
        return
    x0, y0, x1, y1 = _rail_line(s)
    ux, uy = s.head(0)
    nx, ny = -uy, ux
    L = s.rng
    if k < linger:
        q = k / float(linger)
        W = float(P["radius"]) * ps * (2.2 if k < 2 else 1.0) * (1 - q)
        pen.line(x0, y0, x1, y1, c, 200 * (1 - q), W * 2.6 + 0.3)
        pen.line(x0, y0, x1, y1, S.HOT, 255 * (1 - q) ** 1.5, W + 0.2)
        amp = float(P["radius"]) * ps * (1.8 + 2.4 * S.ease_out3(q))
        for sd in (0, 1):
            pts = []
            for m in range(41):
                d = L * m / 40.0
                lat = math.sin(d / (14 * ps) + sd * math.pi + k * 0.5) * amp
                pts.append((x0 + ux * d + nx * lat, y0 + uy * d + ny * lat))
            pen.polyline(pts, S.mix(c, S.HOT, 0.3), 170 * (1 - q), 1.3 * ps)
        for (j, fr_) in enumerate((0.15, 0.4, 0.65, 0.9)):
            aa = k - j
            if aa < 0:
                continue
            qq = min(1.0, aa / float(linger))
            ee = S.ease_out3(qq)
            cx, cy = x0 + ux * L * fr_, y0 + uy * L * fr_
            pen.ring(cx, cy, (2 + 6 * ee) * ps, (6 + 22 * ee) * ps, math.atan2(uy, ux), c, 170 * (1 - qq), 1.8 * ps * (1 - qq) + 0.2)
    life = IMPACT_LIFE["rail"]
    B = float(P["thickness"]) * ps
    for (n, (h, hx, hy)) in enumerate(inst.tq_imp):
        a = t - h - RAIL_DELAY
        if a < 0:
            if t >= h:
                pen.glow(hx, hy, 6 * ps, S.HOT, 230)
            continue
        _heavy(pen, inst, 9000 + n, c, ps, hx, hy, math.atan2(uy, ux), a, life, B, dens)


def draw(pen, inst, host, ps):
    P = inst.fx["params"]
    st = S._style(P)
    g = GUNS[st]
    t = inst.age
    c, bright, deep = S._colours(inst, host)
    dens = float(P.get("density") or 1)
    rounds = _rounds(inst, ps)
    smoke = S.mix(SMOKE, deep, 0.25)
    lb = launches(P)
    # 1: smoke, casings and rocket bodies (painted normally, under the light)
    pen.add(False)
    n_dust = max(0, F.jround(g["dust"] * dens))
    n_smoke = max(0, F.jround(g["smoke"] * dens))
    for s in rounds:
        k = t - s.b
        if s.j == 0:
            ux, uy = s.head(0)
            if n_smoke:
                _puffs(pen, inst, s.i * 4 + 2, s.ox + ux * 8 * ps, s.oy + uy * 8 * ps, k, SMOKE_LIFE, n_smoke,
                       float(g["flash_px"]) * 0.7 * ps, ps, smoke, 0.45)
            if g["shells"] and dens > 0:
                _casing(pen, inst, s.i * 4 + 3, s.ox, s.oy, ux, k, ps, g["shells"])
        if s.look == "rail":
            for (n, (h, hx, hy)) in enumerate(inst.tq_imp):
                _puffs(pen, inst, 9100 + n, hx, hy, t - h - RAIL_DELAY, SMOKE_LIFE, n_dust, float(P["thickness"]) * 0.6 * ps,
                       ps, smoke, 0.35)
            continue
        e, stopped = s.end(inst)
        if s.look == "rocket":
            # smoke trail, then the missile itself
            kp = 0
            while kp < min(k, e - s.b):
                px, py = s.pos(kp)
                _puffs(pen, inst, 20000 + s.i * 64 + kp // ROCKET_PUFF, px, py, k - kp, 30, 1,
                       float(P["radius"]) * 1.6 * ps, ps, smoke, 0.15)
                kp += ROCKET_PUFF
            if t < e:
                r = float(P["radius"]) * ps * s.size
                x, y = s.pos(k)
                ux, uy = s.head(k)
                nx, ny = -uy, ux
                body = S.mix(STEEL, c, 0.15)

                def w(a, l):
                    return x + ux * a * r + nx * l * r, y + uy * a * r + ny * l * r
                pen.poly([w(2.2, 0), w(1.0, 0.6), w(-1.6, 0.6), w(-1.6, -0.6), w(1.0, -0.6)], body, 245)
                pen.poly([w(-0.6, 0.6), w(-1.7, 1.3), w(-1.7, 0.6)], c, 245)
                pen.poly([w(-0.6, -0.6), w(-1.7, -1.3), w(-1.7, -0.6)], c, 245)
                pen.poly([w(1.4, 0.45), w(1.0, 0.6), w(1.0, -0.6), w(1.4, -0.45)], c, 245)
        bl = _blast_at(inst, s)
        if bl is not None and n_dust:
            _puffs(pen, inst, s.i * 4 + 1, bl[1], bl[2], t - bl[0], SMOKE_LIFE, n_dust,
                   float(P["thickness"]) * 0.6 * ps * s.size, ps, smoke, 0.35)
    if st == "gatling" and t > lb[-1]:
        mx, my = _at(inst.tq_path, t)
        for m in range(4):
            _puffs(pen, inst, 9200 + m, mx, my - 4 * ps, t - lb[-1] - m * 3, SMOKE_LIFE, max(0, F.jround(2 * dens)),
                   6 * ps, ps, smoke, 0.6)
    pen.add(True)
    # 2: the gun itself before / while it fires
    if st == "gatling":
        fired = 0
        for b in lb:
            if b <= t:
                fired += 1
        _draw_gatling(pen, inst, P, c, ps, t, fired, len(lb))
    elif st == "charged_blast":
        _draw_charge(pen, inst, P, c, S.mix(c, S.HOT, 0.4), ps, t, lb[0], dens)
    elif st == "sniper_rail":
        _draw_aim(pen, inst, P, c, ps, t, lb[0])
    # 3: muzzle flashes, rounds in flight and where they land
    for s in rounds:
        k = t - s.b
        if s.j == 0:
            _muzzle(pen, inst, g, s, k, c, ps, P)
        if s.look == "rail":
            _draw_rail(pen, inst, s, P, c, ps, t, dens)
            continue
        e, stopped = s.end(inst)
        if t < e:
            _round(pen, inst, s, k, t, c, S.mix(c, S.HOT, 0.25 + s.tint), ps, P, stopped)
            continue
        bl = _blast_at(inst, s)
        if bl is not None:
            _impact(pen, inst, s, t - bl[0], bl[1], bl[2], bl[3], c, ps, P, dens)
    if g["look"] == "drill":
        for (n, (h, hx, hy)) in enumerate(inst.tq_imp):
            _heavy(pen, inst, 9300 + n, c, ps, hx, hy, 0.0, t - h, IMPACT_LIFE["drill"], float(P["thickness"]) * ps, dens)
