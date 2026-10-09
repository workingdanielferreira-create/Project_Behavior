"""
Strikes — the ki blasts and punches of the FX Kit "technique" primitive,
painted by hand at the same standard as the sword techniques
(laser/swordfx.py, whose frame, pen and timeline they share).

Styles (params.style):

  ki_barrage    rapid-fire ki blasts (Vegeta's barrage): a stream of glowing
                orbs (white-hot core, coloured halo, comet tail) fired from
                alternating sides of the anchor with a muzzle flash each.
                No two shots are alike: size (now and then a much bigger
                one), tint, spread, speed, range and a curve in the flight
                path all vary.  Each shot detonates where it hits, or at the
                end of its range: a white flash, a fireball, shock ring and
                sparks (three blast kinds), and smoke that piles up over the
                target while the barrage keeps coming.
  impact_punch  the fist drives out along the aim inside a pressure streak
                with speed lines and afterimages, an air ring compressing in
                front of it; when it lands: a white flash, a spiked impact
                star, two shockwave rings standing across the punch line,
                radial speed lines and sparks.  A whiff gives a smaller burst
                at full reach.

Parameters (the technique's own, reused):

  ki_barrage    radius = shot radius, thickness = blast radius, span = spread
                (degrees), length = range (px), swing_ticks = ticks between
                shots, hold_ticks = how long it fires, density = sparks/smoke
  impact_punch  radius = fist radius, thickness = streak width, length =
                reach (px), swing_ticks = punch-out ticks, hold_ticks = ticks
                held at full reach, density = sparks

Hits: every ki shot can hit once (it stops and detonates there: inst.tq_ki),
so give the effect Pierce and a short Re-hit; the punch hits along the arm
while it is out.  Everything else is a pure function of the instance (age,
seed, the anchor's path), so FX Studio's port (tools/fx/studio/strikefx.js)
draws the same pixels.
"""

import math

from . import fxkit as F
from . import swordfx as S

STYLES = ("ki_barrage", "impact_punch")

KI_SPEED = (9.0, 13.0)       # shot speed range, px per tick (x scale)
KI_RANGE = (0.85, 1.12)      # shot range, times length
KI_SIDE = 7.0                # alternating launch offset either side of the anchor, px
KI_FLASH = 6                 # muzzle flash ticks
KI_BLAST_LIFE = 22
KI_SMOKE_LIFE = 44
SMOKE = (92, 86, 80)

PUNCH_RETRACT = 5
PUNCH_IMPACT_LIFE = 24


# ---------------------------------------------------------------- timeline
def _cad(P):
    return max(1, F.trunc(float(P.get("swing_ticks") or 3)))


def _hold(P):
    return max(0, F.trunc(float(P.get("hold_ticks") or 0)))


def ki_count(P):
    return _hold(P) // _cad(P) + 1


def _ki_flight_max(P):
    return int(math.ceil(float(P["length"]) * KI_RANGE[1] / KI_SPEED[0]))


def active_ticks(P):
    if S._style(P) == "ki_barrage":
        return (ki_count(P) - 1) * _cad(P) + _ki_flight_max(P) + 1
    return S._swing(P) + _hold(P) + 1


def total_ticks(P):
    if S._style(P) == "ki_barrage":
        return active_ticks(P) + KI_SMOKE_LIFE
    return S._swing(P) + _hold(P) + PUNCH_RETRACT + PUNCH_IMPACT_LIFE


# ---------------------------------------------------------------- ki shots
class Shot:
    """One ki blast: everything about it is rolled from the seed."""
    __slots__ = ("i", "b", "sp", "ang", "curve", "size", "rng", "flight", "side", "tint", "kind", "ox", "oy")

    def __init__(self, inst, i, ps):
        P = inst.fx["params"]
        r = S.rng_for(inst.seed, i, 41)
        su = r.uniform(KI_SPEED[0], KI_SPEED[1])
        self.i = i
        self.b = i * _cad(P)
        self.sp = su * ps
        self.ang = r.uniform(-0.5, 0.5) * float(P.get("span") or 0) * S.D
        self.curve = r.uniform(-22.0, 22.0) * ps
        self.size = r.uniform(0.75, 1.25)
        if r() < 0.18:
            self.size *= 1.55          # now and then a much bigger one
        ru = r.uniform(KI_RANGE[0], KI_RANGE[1])
        self.rng = float(P["length"]) * ru * ps
        self.flight = max(1, int(math.ceil(float(P["length"]) * ru / su)))
        self.side = 1 if i % 2 == 0 else -1
        self.tint = r.uniform(0.0, 0.4)
        self.kind = min(2, int(r() * 3))
        path = inst.tq_path
        self.ox, self.oy = path[min(self.b, len(path) - 1)]

    def pos(self, fr, k):
        """World position k ticks after launch (k may run past the range)."""
        d = self.sp * k
        u = min(1.0, d / self.rng) if self.rng > 0 else 1.0
        lat = self.curve * math.sin(math.pi * u)
        ca, sa = math.cos(self.ang), math.sin(self.ang)
        lx, ly = ca * d - sa * lat, sa * d + ca * lat + self.side * KI_SIDE * fr.s
        dx, dy = fr.f.d(lx, ly)
        return self.ox + dx, self.oy + dy

    def end(self, inst):
        """(tick it detonates, stopped by a hit?)."""
        h = inst.tq_ki.get(self.i)
        if h is not None:
            return h[0], True
        return self.b + self.flight, False


class _Fr:
    __slots__ = ("f", "s")

    def __init__(self, inst, ps):
        self.f = S.Frame(0.0, 0.0, inst.tq_f, inst.tq_m)
        self.s = ps


def _shots(inst, ps):
    return [Shot(inst, i, ps) for i in range(ki_count(inst.fx["params"]))]


def _live(inst, ps):
    """[(shot, position)] for the shots in flight this tick."""
    out = []
    fr = _Fr(inst, ps)
    t = inst.age
    for s in _shots(inst, ps):
        if s.b > t:
            break
        e, _stopped = s.end(inst)
        if t < e:
            out.append((s, s.pos(fr, t - s.b)))
    return out


def _ki_hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    r0 = float(inst.fx["params"]["radius"]) * ps
    for (s, (x, y)) in _live(inst, ps):
        if math.hypot(x - tx, y - ty) <= hr + r0 * s.size:
            return True
    return False


def _ki_on_hit(inst, tx, ty, ps):
    """The shot nearest the target stops there and detonates."""
    best, bd = None, None
    for (s, (x, y)) in _live(inst, ps):
        d = math.hypot(x - tx, y - ty)
        if bd is None or d < bd:
            best, bd = (s, x, y), d
    if best is not None:
        s, x, y = best
        inst.tq_ki[s.i] = (inst.age, x, y)


# ---------------------------------------------------------------- punch
def _reach(P, t, L):
    Ts, Th = S._swing(P), _hold(P)
    if t < Ts:
        return L * S.ease_out3(t / float(Ts))
    if t < Ts + Th:
        return L
    if t < Ts + Th + PUNCH_RETRACT:
        return L * (1 - S.ease_in3((t - Ts - Th) / float(PUNCH_RETRACT)))
    return 0.0


def _punch_hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    P = inst.fx["params"]
    l = _reach(P, inst.age, float(P["length"]) * ps)
    if l <= 2:
        return False
    b = S._frame(inst).w(l, 0)
    return F.seg_dist(tx, ty, inst.x, inst.y, b[0], b[1]) <= hr + float(P["radius"]) * ps * 1.2


def _punch_body(inst, ps):
    P = inst.fx["params"]
    l = _reach(P, inst.age, float(P["length"]) * ps)
    if l <= 2 or inst.age >= inst.life:
        return None
    return [(inst.x, inst.y), S._frame(inst).w(l, 0)], float(P["radius"]) * ps


# ---------------------------------------------------------------- public
def hit(inst, tx, ty, hr, ps):
    if S._style(inst.fx["params"]) == "ki_barrage":
        return _ki_hit(inst, tx, ty, hr, ps)
    return _punch_hit(inst, tx, ty, hr, ps)


def body(inst, ps):
    """A punch clashes along the arm; ki shots never clash as a blade."""
    if S._style(inst.fx["params"]) == "ki_barrage":
        return None
    return _punch_body(inst, ps)


def on_hit(inst, x, y, ps):
    P = inst.fx["params"]
    if S._style(P) == "ki_barrage":
        _ki_on_hit(inst, x, y, ps)
    else:
        # the impact stays where the fist landed
        l = _reach(P, inst.age, float(P["length"]) * ps) + float(P["radius"]) * ps * 0.8
        ix, iy = S._frame(inst).w(l, 0)
        inst.tq_imp.append((inst.age, ix, iy))


# ================================================================ drawing
def _blast_at(inst, s, fr):
    e, stopped = s.end(inst)
    if stopped:
        h = inst.tq_ki[s.i]
        return e, h[1], h[2]
    x, y = s.pos(fr, s.flight)
    return e, x, y


def _draw_ki(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    c, bright, deep = S._colours(inst, host)
    fr = _Fr(inst, ps)
    r0 = float(P["radius"]) * ps
    B0 = float(P["thickness"]) * ps
    dens = float(P.get("density") or 1)
    shots = _shots(inst, ps)
    smoke = S.mix(SMOKE, deep, 0.25)
    # 1: smoke piling up where the shots went off (painted normally, under the light)
    pen.add(False)
    n_puff = max(0, F.jround(3 * dens))
    for s in shots:
        if s.b > t:
            break
        e, x, y = _blast_at(inst, s, fr)
        a = t - e
        if a < 0 or a >= KI_SMOKE_LIFE:
            continue
        q = a / float(KI_SMOKE_LIFE)
        B = B0 * s.size
        for j in range(n_puff):
            r = S.rng_for(inst.seed, s.i, 60 + j)
            an = r.uniform(0, math.pi * 2)
            dr = r.uniform(0.2, 0.9) * B * S.ease_out3(a / 18.0)
            rise = r.uniform(0.3, 0.8) * ps * a
            px, py = x + math.cos(an) * dr, y + math.sin(an) * dr - rise
            rad = B * r.uniform(0.6, 1.0) * (0.5 + 0.9 * S.ease_out3(a / 20.0))
            pen.glow(px, py, rad, smoke, 95 * (1 - q) ** 1.5 * min(1.0, a / 3.0), 0.6)
    pen.add(True)
    # 2: the hands glow while the barrage fires
    last = shots[-1].b if shots else 0
    if t <= last + 4:
        fa = 1.0 if t <= last else 1 - (t - last) / 4.0
        fl = 0.8 + 0.2 * math.sin(t * 2.3)
        for side in (1, -1):
            hx, hy = fr.f.d(0.0, side * KI_SIDE * ps)
            pen.glow(inst.x + hx, inst.y + hy, 16 * ps * fl, c, 150 * fa)
            pen.glow(inst.x + hx, inst.y + hy, 6 * ps, S.HOT, 220 * fa)
    for s in shots:
        if s.b > t:
            break
        k = t - s.b
        e, stopped = s.end(inst)
        tint = S.mix(c, S.HOT, 0.3 + s.tint)
        r = r0 * s.size
        # 3: muzzle flash at launch
        if k < KI_FLASH:
            q = k / float(KI_FLASH)
            mx, my = s.pos(fr, 0)
            ux, uy = fr.f.d(math.cos(s.ang), math.sin(s.ang))
            pen.glow(mx, my, (10 + 10 * S.ease_out3(q)) * ps * s.size, c, 220 * (1 - q))
            pen.glow(mx, my, 6 * ps * s.size, S.HOT, 255 * (1 - q))
            S._star(pen, mx, my, ux, uy, 16 * ps * s.size * (1 - 0.4 * q), 7 * ps * s.size, S.HOT, 230 * (1 - q), 1.3 * ps)
        # 4: the shot in flight — comet tail, halo, body, white-hot core
        if t < e:
            x, y = s.pos(fr, k)
            tx, ty = s.pos(fr, max(0.0, k - 2.5))
            fl = 0.88 + 0.12 * math.sin(t * 1.7 + s.i * 2.1)
            pen.diamond(tx, ty, x, y, r * 0.95, c, 140)
            pen.diamond(tx, ty, x, y, r * 0.4, tint, 200)
            pen.glow(x, y, r * 3.4 * fl, c, 120)
            pen.glow(x, y, r * 1.8, tint, 235)
            pen.glow(x, y, r * 0.85, S.HOT, 255, 0.75)
            continue
        # 5: detonation
        a = t - e
        if a >= KI_BLAST_LIFE:
            continue
        _e, x, y = _blast_at(inst, s, fr)
        q = a / float(KI_BLAST_LIFE)
        ee = S.ease_out3(a / 8.0)
        B = B0 * s.size * (1.0 if stopped else 0.85)
        if a < 5:
            pen.glow(x, y, B * (0.7 + 0.9 * S.ease_out3(a / 5.0)), S.HOT, 255 * (1 - a / 5.0))
        pen.glow(x, y, B * (0.9 + 1.0 * ee), c, 210 * (1 - q), 0.45)
        pen.glow(x, y, B * (0.5 + 0.45 * ee), S.mix(c, S.HOT, 0.6), 235 * (1 - q) ** 2)
        if s.kind >= 1:
            rr = B * (0.5 + 1.7 * S.ease_out3(q))
            pen.ring(x, y, rr, rr * (0.75 if s.kind == 2 else 1.0), 0.0, c, 190 * (1 - q), 2.4 * ps * (1 - q) + 0.2)
        n_sp = max(0, F.jround((4 + 5 * (s.kind == 2)) * dens))
        for j in range(n_sp):
            rr_ = S.rng_for(inst.seed, s.i, 80 + j)
            life = 9 + 9 * rr_()
            if a >= life:
                continue
            an = rr_.uniform(0, math.pi * 2)
            sp = rr_.uniform(2.5, 6.5) * ps
            fd = S.drag_dist(0.87, a)
            sx, sy = x + math.cos(an) * sp * fd, y + math.sin(an) * sp * fd + 0.08 * ps * a * a
            dk = 0.87 ** a
            qq = a / life
            pen.line(sx, sy, sx - math.cos(an) * sp * dk * 1.6, sy - math.sin(an) * sp * dk * 1.6, S.mix(S.HOT, c, qq),
                     255 * (1 - qq), 1.4 * ps)


def _spikes(pen, x, y, ang, n, r_out, r_in, c, a):
    pts = []
    for j in range(2 * n):
        rr = r_out if j % 2 == 0 else r_in
        an = ang + math.pi * j / n
        pts.append((x + math.cos(an) * rr, y + math.sin(an) * rr))
    pen.poly(pts, c, a)


def _impact(pen, inst, c, ps, x, y, a, sc, salt):
    """The punch landing (sc = size; a whiff is smaller)."""
    q = a / float(PUNCH_IMPACT_LIFE)
    fx_, fy_ = inst.tq_f
    ang = math.atan2(fy_, fx_)
    if a < 6:
        pen.glow(x, y, (18 + 24 * S.ease_out3(a / 6.0)) * ps * sc, S.HOT, 255 * (1 - a / 6.0))
    if a < 10:
        qs = a / 10.0
        e = S.ease_out3(a / 4.0)
        rot = ang + 0.15 * a / 10.0
        _spikes(pen, x, y, rot, 8, (16 + 28 * e) * ps * sc, (6 + 8 * e) * ps * sc, c, 225 * (1 - qs))
        _spikes(pen, x, y, rot, 8, (9 + 16 * e) * ps * sc, (3.5 + 4 * e) * ps * sc, S.HOT, 255 * (1 - qs) ** 1.5)
    pen.glow(x, y, (26 + 20 * S.ease_out3(q)) * ps * sc, c, 140 * (1 - q), 0.4)
    # shockwave rings standing across the punch line
    for (d0, k) in ((0, 1.0), (3, 1.45)):
        aa = a - d0
        if aa < 0:
            continue
        qq = aa / float(PUNCH_IMPACT_LIFE - d0)
        e = S.ease_out3(qq)
        cx, cy = x + fx_ * 10 * ps * sc * e * k, y + fy_ * 10 * ps * sc * e * k
        pen.ring(cx, cy, (5 + 14 * e) * ps * sc * k, (10 + 46 * e) * ps * sc * k, ang, c, 210 * (1 - qq),
                 3.0 * ps * (1 - qq) + 0.2)
        pen.ring(cx, cy, (5 + 14 * e) * ps * sc * k, (10 + 46 * e) * ps * sc * k, ang, S.HOT, 160 * (1 - qq) ** 2,
                 1.0 * ps * (1 - qq) + 0.1)
    # radial speed lines
    if a < 12:
        ql = a / 12.0
        for j in range(12):
            r = S.rng_for(inst.seed, j, 70 + salt)
            an = r.uniform(0, math.pi * 2)
            r1 = (12 + 46 * S.ease_out3(ql)) * ps * sc * r.uniform(0.8, 1.2)
            ln = r.uniform(12, 26) * ps * sc * (1 - ql)
            ca, sa = math.cos(an), math.sin(an)
            pen.line(x + ca * r1, y + sa * r1, x + ca * (r1 + ln), y + sa * (r1 + ln), S.mix(S.HOT, c, ql), 230 * (1 - ql),
                     1.4 * ps)
    # sparks thrown mostly forward
    n_sp = max(0, F.jround(10 * float(inst.fx["params"].get("density") or 1) * sc))
    for j in range(n_sp):
        r = S.rng_for(inst.seed, j, 90 + salt)
        life = 10 + 10 * r()
        if a >= life:
            continue
        an = ang + r.uniform(-75, 75) * S.D
        sp = r.uniform(3, 8) * ps
        fd = S.drag_dist(0.87, a)
        sx, sy = x + math.cos(an) * sp * fd, y + math.sin(an) * sp * fd + 0.1 * ps * a * a
        dk = 0.87 ** a
        qq = a / life
        pen.line(sx, sy, sx - math.cos(an) * sp * dk * 1.6, sy - math.sin(an) * sp * dk * 1.6, S.mix(S.HOT, c, qq),
                 255 * (1 - qq), 1.5 * ps)


def _draw_punch(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    fr = S._frame(inst)
    c, bright, _deep = S._colours(inst, host)
    L = float(P["length"]) * ps
    rf = float(P["radius"]) * ps
    W = float(P["thickness"]) * ps
    Ts, Th = S._swing(P), _hold(P)
    l = _reach(P, t, L)
    out = t < Ts + Th + PUNCH_RETRACT
    pen.add(True)
    if out and l > 1:
        fade = 1.0 if t < Ts + Th else 1 - (t - Ts - Th) / float(PUNCH_RETRACT)
        # 1: pressure streak from the shoulder to the fist
        tail = max(0.0, l - max(L * 0.9, 3 * rf))
        pen.poly([fr.w(tail, -0.12 * W), fr.w(l, -W), fr.w(l + rf * 0.6, 0), fr.w(l, W), fr.w(tail, 0.12 * W)], c,
                 95 * fade)
        pen.poly([fr.w(tail + (l - tail) * 0.3, -0.06 * W), fr.w(l, -0.45 * W), fr.w(l + rf * 0.4, 0), fr.w(l, 0.45 * W),
                  fr.w(tail + (l - tail) * 0.3, 0.06 * W)], bright, 170 * fade)
        # 2: speed lines alongside it while it drives out
        if t <= Ts + 2:
            sf = 1.0 if t <= Ts else 1 - (t - Ts) / 2.0
            for j in range(4):
                r = S.rng_for(inst.seed, j, 51)
                off = (1 if j % 2 else -1) * W * r.uniform(1.1, 2.0)
                x0, x1 = l - r.uniform(0.5, 0.9) * L, l - r.uniform(0.0, 0.2) * L
                a0, a1 = fr.w(max(0.0, x0), off), fr.w(max(0.0, x1), off)
                pen.line(a0[0], a0[1], a1[0], a1[1], S.mix(c, S.HOT, 0.4), 170 * sf, 1.2 * ps)
        # 3: afterimages of the fist
        for (j, al) in ((2, 60), (1, 100)):
            lj = _reach(P, max(0, t - j), L)
            gx, gy = fr.w(lj, 0)
            pen.glow(gx, gy, rf * 1.8, c, al * fade)
        # 4: air ring compressing in front of the fist
        if t <= Ts + 1:
            e = S.ease_out3(t / float(Ts))
            ax, ay = fr.w(l + rf * (0.9 + 0.5 * e), 0)
            pen.ring(ax, ay, rf * 0.45, rf * (1.0 + 0.9 * e), math.atan2(inst.tq_f[1], inst.tq_f[0]), S.HOT, 200 * (0.4 + 0.6 * e),
                     1.4 * ps)
        # 5: the fist
        fx_, fy_ = fr.w(l, 0)
        pen.glow(fx_, fy_, rf * 2.6, c, 170 * fade)
        pen.glow(fx_, fy_, rf * 1.4, S.mix(c, S.HOT, 0.6), 235 * fade)
        pen.glow(fx_, fy_, rf * 0.7, S.HOT, 255 * fade, 0.7)
    # 6: the impact — where the fist was when it landed; a whiff bursts at full reach
    if inst.tq_imp:
        for n, (b, x, y) in enumerate(inst.tq_imp):
            a = t - b
            if 0 <= a < PUNCH_IMPACT_LIFE:
                _impact(pen, inst, c, ps, x, y, a, 1.0, 11 * n)
    else:
        a = t - Ts
        if 0 <= a < PUNCH_IMPACT_LIFE:
            x, y = fr.w(L + rf * 0.8, 0)
            _impact(pen, inst, c, ps, x, y, a, 0.55, 0)


def draw(pen, inst, host, ps):
    if S._style(inst.fx["params"]) == "ki_barrage":
        _draw_ki(pen, inst, host, ps)
    else:
        _draw_punch(pen, inst, host, ps)
