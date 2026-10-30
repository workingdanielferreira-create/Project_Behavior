"""
Strike FX partitions — what the punch (laser/strikefx.py, impact_punch) and
the kicks (laser/kickfx.py) paint, split into three parts set on their own so
they can be mixed freely (params):

  fx_motion  how the limb moved.
             motion_smear: smear frames — afterimages of the limb (shoulder ->
             fist, knee -> foot) along its real path during the fast part of
             the strike only; gone on the contact frame (the way 2D animators
             hold the smear up to the hit and drop it there).
             motion_arcs: thin broken wind strokes tracing the fist / foot's
             path, tapered at both ends, lingering a few ticks past contact.
             Plus the fist / foot itself and the wind-up glint.
  fx_impact  the hit, at the contact point, laid along the way the limb moved;
             on a hit it spills forward onto / through the target.  A whiff
             bursts smaller (sc) where the limb met the aim.
  fx_env     what the strike does to its surroundings: push-off dust under
             the attacker as the strike starts, a ground wave under the
             impact, the axe kick's crater, the rising kick's kick-up and the
             spinning kick's vortex.

Each part is "off" or one of three looks (LOOKS):

  ink     anime limited animation: white shapes with ink outlines, redrawn on
          twos (a new hand-drawn-looking shape every 2 ticks), focus lines.
  energy  light: white-hot cores, coloured pressure bursts, air-friction
          sparks spilling forward, clean shock rings (additive).
  gritty  physical: dust, refraction-like distortion rings (a light and a dark
          ring side by side), debris, sweat spray; hardly any glow.

Hit weight (the hit options, strikefx.HIT_OPTION_STYLES): hitstop (the world
freezes), shake / shake_px / shake_ticks (the overlay shakes: World.shake;
both fire when the strike lands, Solo: as it whiffs) and squash / squash_amt
/ squash_ticks / squash_flash (the fighter hit squashes along the blow and
flashes white: Figure.hit_squash, Battle; the Studio's target dummy).

Everything is a pure function of the instance (age, seed, the limb's path),
so FX Studio's port (tools/fx/studio/hitfx.js) draws the same pixels.
"""

import math

from . import fxkit as F
from . import swordfx as S

LOOKS = ("ink", "energy", "gritty")
PARTS = ("fx_motion", "fx_impact", "fx_env")
IMPACT_LIFE = 24         # ticks an impact plays (strikefx PUNCH_IMPACT_LIFE)
ENV_LIFE = 26            # ticks a ground event plays
CRATER_LIFE = 40         # ticks the axe kick's crater stays
FEET_DROP = 30.0         # a fighter's centre to its feet, px (x scale)
SMEAR_N = 3              # smear afterimages
SMEAR_STEP = 0.55        # ticks between them
SMEAR_LEN = 3.0          # each afterimage's length, x the fist / foot radius
ARC_N = 4                # air strokes
ARC_LINGER = 4           # ticks the air strokes stay past the end of the move
INK = (16, 10, 22)
PAPER = (236, 238, 246)  # the ink look's "white" (a touch cool, so pure white stays the hottest)
DUST = (150, 138, 120)
GREY = (176, 174, 178)
ROCK = (96, 84, 72)
SCORCH = (40, 30, 28)


def look(P, part):
    v = P.get(part)
    if v is None:
        v = "ink"
    return v if v in LOOKS else "off"


# ---------------------------------------------------------------- shapes
def _unit(x, y):
    n = math.hypot(x, y) or 1.0
    return x / n, y / n


def _circle(x, y, r, n=14):
    return [(x + math.cos(i * 2 * math.pi / n) * r, y + math.sin(i * 2 * math.pi / n) * r) for i in range(n)]


def _ellipse(x, y, rx, ry, ang, n=20):
    ca, sa = math.cos(ang), math.sin(ang)
    out = []
    for i in range(n):
        t = i * 2 * math.pi / n
        px, py = math.cos(t) * rx, math.sin(t) * ry
        out.append((x + px * ca - py * sa, y + px * sa + py * ca))
    return out


def _outlined(pen, pts, fill, a, line, la, w):
    """A filled shape with an ink outline (normal blending)."""
    pen.poly(pts, fill, a)
    pen.polyline(pts + pts[:1], line, la, w)


def _taper(pts, w):
    """A stroke through pts as a polygon: zero width at both ends, w at the
    middle."""
    n = len(pts)
    if n < 2:
        return []
    left, right = [], []
    for i in range(n):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        tx, ty = _unit(b[0] - a[0], b[1] - a[1])
        h = w * 0.5 * math.sin(math.pi * i / float(n - 1))
        left.append((pts[i][0] - ty * h, pts[i][1] + tx * h))
        right.append((pts[i][0] + ty * h, pts[i][1] - tx * h))
    return left + right[::-1]


def _capsule(rx, ry, x, y, w0, w1):
    """A limb from (rx, ry) to (x, y): w0 half-width at the root, w1 at the
    tip, the tip rounded."""
    ux, uy = _unit(x - rx, y - ry)
    nx, ny = -uy, ux
    pts = [(rx + nx * w0, ry + ny * w0)]
    for k in range(7):
        an = math.pi * 0.5 - math.pi * k / 6.0
        ca, sa = math.cos(an), math.sin(an)
        pts.append((x + (nx * ca + ux * sa) * w1, y + (ny * ca + uy * sa) * w1))
    pts.append((rx - nx * w0, ry - ny * w0))
    return pts


def _burst(inst, x, y, ang, n, r_out, r_in, salt):
    """A jagged burst: n spikes of uneven length, longest along ang, a shorter
    kick back the other way."""
    pts = []
    for j in range(2 * n):
        an = ang + math.pi * j / n
        rr = r_in
        if j % 2 == 0:
            r = S.rng_for(inst.seed, j, salt)
            an += r.uniform(-0.35, 0.35) * math.pi / n
            k = math.cos(an - ang)
            rr = r_out * (0.42 + 0.7 * max(0.0, k) ** 2 + 0.3 * max(0.0, -k) ** 2) * r.uniform(0.7, 1.25)
        else:
            rr = r_in * S.rng_for(inst.seed, j, salt + 1).uniform(0.8, 1.15)
        pts.append((x + math.cos(an) * rr, y + math.sin(an) * rr))
    return pts


def _shard(x, y, an, d, ln, wd):
    """A triangular shard d out from (x, y) along an, pointing outward."""
    ca, sa = math.cos(an), math.sin(an)
    bx, by = x + ca * d, y + sa * d
    return [(bx - sa * wd, by + ca * wd), (bx + ca * ln, by + sa * ln), (bx + sa * wd, by - ca * wd)]


# ================================================================ motion
class Motion:
    """What the motion partition needs from a strike: limb(t) -> (root x, y,
    tip x, y, unit motion x, y) at tick t (fractional); t0 = the tick the
    fast part starts, tc = contact, tm = the end of the move, tout = the limb
    gone; rf = fist / foot radius, W = the stroke spread (thickness)."""

    __slots__ = ("limb", "t0", "tc", "tm", "tout", "rf", "W")

    def __init__(self, limb, t0, tc, tm, tout, rf, W):
        self.limb, self.t0, self.tc, self.tm, self.tout, self.rf, self.W = limb, t0, tc, tm, tout, rf, W


def motion(pen, inst, P, t, ps, c, M):
    lk = look(P, "fx_motion")
    if lk == "off":
        return
    if t < M.t0:
        _windup(pen, inst, lk, t, ps, c, M)
        return
    if P.get("motion_arcs", True) and t <= M.tm + ARC_LINGER:
        _arcs(pen, inst, lk, t, ps, c, M)
    if P.get("motion_smear", True) and t < M.tc:
        _smear(pen, inst, lk, t, ps, c, M)
    if t < M.tout:
        fade = 1.0 if t <= M.tm else 1 - (t - M.tm) / float(max(1, M.tout - M.tm))
        _tip(pen, inst, lk, t, ps, c, M, fade)


def _windup(pen, inst, lk, t, ps, c, M):
    """A glint where the strike starts, drawing in."""
    _rx, _ry, x, y, _ux, _uy = M.limb(M.t0)
    e = (t + 1) / float(max(1, M.t0))
    rf = M.rf
    if lk == "energy":
        pen.add(True)
        pen.glow(x, y, rf * (0.8 + 1.2 * e), c, 120 + 100 * e)
        pen.ring(x, y, rf * (3 - 2 * e), rf * (3 - 2 * e), 0.0, S.HOT, 150 * e, 1.2 * ps)
    elif lk == "ink":
        pen.add(False)
        L = rf * (1.2 + 1.6 * e)
        for (dx, dy, k) in ((1, 0, 1.0), (0, 1, 0.55)):
            pen.diamond(x - dx * L * k, y - dy * L * k, x + dx * L * k, y + dy * L * k, 2.6 * ps, INK, 230 * e)
            pen.diamond(x - dx * L * k * 0.9, y - dy * L * k * 0.9, x + dx * L * k * 0.9, y + dy * L * k * 0.9,
                        1.3 * ps, PAPER, 255 * e)
    else:
        pen.add(False)
        pen.glow(x, y, rf * (1.0 + 0.8 * e), GREY, 70 * e, 0.5)


def _arcs(pen, inst, lk, t, ps, c, M):
    """Thin broken wind strokes along the limb's path, offset either side of
    it, each in two pieces."""
    te = min(float(t), float(M.tm))
    f = 1.0 if t <= M.tm else 1 - (t - M.tm) / float(ARC_LINGER + 1)
    pen.add(lk == "energy")
    for j in range(ARC_N + (1 if lk == "energy" else 0)):
        r = S.rng_for(inst.seed, j, 300)
        off = r.uniform(-1.0, 1.0) * (M.rf * 0.6 + M.W * 0.4)
        lag = r.uniform(0.0, 0.5)
        span = r.uniform(2.0, 3.4)
        gap = r.uniform(0.38, 0.55)
        wmax = r.uniform(1.4, 2.6) * ps
        s1 = te - lag
        s0 = max(float(M.t0), s1 - span)
        if s1 - s0 < 0.3:
            continue
        for (u0, u1) in ((0.0, gap - 0.06), (gap + 0.06, 1.0)):
            pts = []
            for k in range(9):
                s = s0 + (s1 - s0) * (u0 + (u1 - u0) * k / 8.0)
                _rx, _ry, x, y, ux, uy = M.limb(s)
                pts.append((x - uy * off, y + ux * off))
            if lk == "ink":
                pen.poly(_taper(pts, wmax + 2.2 * ps), INK, 200 * f)
                pen.poly(_taper(pts, wmax), PAPER, 245 * f)
            elif lk == "energy":
                pen.poly(_taper(pts, wmax * 1.6), c, 150 * f)
                pen.poly(_taper(pts, wmax * 0.6), S.HOT, 200 * f)
            else:
                pen.poly(_taper(pts, wmax * 0.8), GREY, 120 * f)
        if lk == "gritty":
            # dust flecks shed along the stroke
            for k in range(3):
                q = r()
                s = s0 + (s1 - s0) * q
                _rx, _ry, x, y, ux, uy = M.limb(s)
                age = t - s
                pen.glow(x - uy * off * 1.4 - ux * age * 1.5 * ps, y + ux * off * 1.4 - uy * age * 1.5 * ps,
                         (2.5 + 2 * q) * ps, DUST, 110 * f, 0.6)


def _smear(pen, inst, lk, t, ps, c, M):
    """Smear frames: afterimages of the limb along its path, oldest first."""
    pen.add(lk == "energy")
    for k in range(SMEAR_N, 0, -1):
        s = t - SMEAR_STEP * k
        if s < M.t0:
            continue
        rx, ry, x, y, _ux, _uy = M.limb(s)
        ln = math.hypot(x - rx, y - ry)
        if ln < 2:
            continue
        # only the end of the limb (forearm / shin): a run of stepped copies
        # rather than one long shape
        k_ = min(1.0, SMEAR_LEN * M.rf / ln)
        rx, ry = x + (rx - x) * k_, y + (ry - y) * k_
        q = 1 - (k - 1) / float(SMEAR_N)
        cap = _capsule(rx, ry, x, y, M.rf * 0.45, M.rf * (0.75 + 0.2 * q))
        if lk == "ink":
            _outlined(pen, cap, PAPER, 150 * q, INK, 170 * q, 1.2 * ps)
        elif lk == "energy":
            pen.poly(cap, c, 95 * q)
            pen.poly(_capsule(rx, ry, x, y, M.rf * 0.2, M.rf * 0.45), S.HOT, 90 * q)
        else:
            pen.poly(cap, GREY, 70 * q)


def _tip(pen, inst, lk, t, ps, c, M, fade):
    """The fist / foot (not while it is still at the shoulder / hip)."""
    rx, ry, x, y, ux, uy = M.limb(t)
    if math.hypot(x - rx, y - ry) <= 1:
        return
    rf = M.rf
    if lk == "energy":
        pen.add(True)
        for (j, al) in ((2, 60), (1, 100)):
            gx, gy = M.limb(max(float(M.t0), t - j))[2:4]
            pen.glow(gx, gy, rf * 1.8, c, al * fade)
        pen.glow(x, y, rf * 2.6, c, 170 * fade)
        pen.glow(x, y, rf * 1.4, S.mix(c, S.HOT, 0.6), 235 * fade)
        pen.glow(x, y, rf * 0.7, S.HOT, 255 * fade, 0.7)
    elif lk == "ink":
        pen.add(False)
        _outlined(pen, _ellipse(x, y, rf * 1.25, rf * 0.9, math.atan2(uy, ux), 16), PAPER, 240 * fade, INK,
                  235 * fade, 1.6 * ps)
        pen.poly(_ellipse(x - ux * rf * 0.25, y - uy * rf * 0.25, rf * 0.55, rf * 0.4, math.atan2(uy, ux), 12), c,
                 200 * fade)
    else:
        pen.add(False)
        pen.glow(x, y, rf * 1.5, (232, 230, 226), 130 * fade, 0.55)


# ================================================================ impact
def impact(pen, inst, P, c, ps, x, y, a, sc, salt, u):
    """The impact a ticks after contact at (x, y), laid along u (sc = size)."""
    if not 0 <= a < IMPACT_LIFE:
        return
    lk = look(P, "fx_impact")
    if lk == "ink":
        _imp_ink(pen, inst, P, c, ps, x, y, a, sc, salt, u)
    elif lk == "energy":
        _imp_energy(pen, inst, P, c, ps, x, y, a, sc, salt, u)
    elif lk == "gritty":
        _imp_gritty(pen, inst, P, c, ps, x, y, a, sc, salt, u)


def _imp_ink(pen, inst, P, c, ps, x, y, a, sc, salt, u):
    """Anime impact, on twos: a white jagged burst with an ink outline and a
    coloured heart, then it breaks into shards flying out mostly forward;
    ink focus lines round it, a pressure disc standing across the blow."""
    ang = math.atan2(u[1], u[0])
    k2 = a - a % 2                      # on twos
    sk = salt + 7 * k2                  # a new drawing every 2 ticks
    pen.add(False)
    # focus lines: ink wedges pointing at the contact point
    if a < 6:
        f = 1 - a / 6.0
        for j in range(18):
            r = S.rng_for(inst.seed, j, 400 + sk)
            an = (j + r.uniform(-0.35, 0.35)) * math.pi * 2 / 18
            r0 = (24 + 12 * r()) * ps * sc + 4 * ps * k2
            r1 = r0 + r.uniform(36, 70) * ps * sc
            hw = r.uniform(0.012, 0.028)
            pen.poly([(x + math.cos(an - hw) * r1, y + math.sin(an - hw) * r1),
                      (x + math.cos(an + hw) * r1, y + math.sin(an + hw) * r1),
                      (x + math.cos(an) * r0, y + math.sin(an) * r0)], INK if j % 2 else PAPER, 230 * f)
    # the burst
    if a < 6:
        e = 1.0 if k2 > 0 else 0.75
        R = (30 + 8 * (k2 / 2.0)) * ps * sc * e
        b = _burst(inst, x, y, ang, 9, R, R * 0.42, 420 + sk)
        _outlined(pen, b, PAPER, 255, INK, 255, 2.4 * ps)
        pen.poly(_burst(inst, x, y, ang, 9, R * 0.55, R * 0.24, 440 + sk), c, 235)
        pen.poly(_circle(x, y, R * 0.16, 10), S.HOT, 255)
    # shards: the burst broken apart, flying out mostly forward
    if 2 <= a < 14:
        q = (a - 2) / 12.0
        e = S.ease_out3(q)
        for j in range(8):
            r = S.rng_for(inst.seed, j, 460 + salt)
            an = ang + (r.uniform(-100, 100) if j < 6 else 180 + r.uniform(-40, 40)) * S.D
            d = (16 + r.uniform(30, 60) * e) * ps * sc
            ln = r.uniform(10, 18) * ps * sc * (1 - q)
            wd = r.uniform(3, 5) * ps * sc * (1 - q * 0.6)
            _outlined(pen, _shard(x, y, an + r.uniform(-0.15, 0.15) * (k2 % 4), d, ln, wd), PAPER, 255 * (1 - q),
                      INK, 255 * (1 - q), 1.6 * ps)
    # pressure disc across the blow, pushed forward
    if 1 <= a < 12:
        q = (a - 1) / 11.0
        e = S.ease_out3(q)
        cx, cy = x + u[0] * 14 * ps * sc * e, y + u[1] * 14 * ps * sc * e
        rx, ry = (5 + 9 * e) * ps * sc, (14 + 42 * e) * ps * sc
        pen.ring(cx, cy, rx, ry, ang, INK, 230 * (1 - q), 4.4 * ps * (1 - q) + 0.6)
        pen.ring(cx, cy, rx, ry, ang, PAPER, 255 * (1 - q), 2.2 * ps * (1 - q) + 0.3)
    # after the burst: a lingering ink star glint, blinking out on twos
    if 6 <= a < 16 and (k2 // 2) % 2 == 1:
        f = 1 - (a - 6) / 10.0
        L = 12 * ps * sc
        for (dx, dy) in ((u[0], u[1]), (-u[1], u[0])):
            pen.diamond(x - dx * L, y - dy * L, x + dx * L, y + dy * L, 2.4 * ps, INK, 230 * f)
            pen.diamond(x - dx * L * 0.88, y - dy * L * 0.88, x + dx * L * 0.88, y + dy * L * 0.88, 1.1 * ps, PAPER,
                        255 * f)


def _imp_energy(pen, inst, P, c, ps, x, y, a, sc, salt, u):
    """Light: a white-hot core, a coloured pressure burst, rays spilling
    forward through the target, air-friction sparks, a clean shock ring."""
    ang = math.atan2(u[1], u[0])
    q = a / float(IMPACT_LIFE)
    pen.add(True)
    if a < 6:
        pen.glow(x, y, (18 + 24 * S.ease_out3(a / 6.0)) * ps * sc, S.HOT, 255 * (1 - a / 6.0))
    # the pressure burst: glows pushed forward along the blow
    if a < 10:
        e = S.ease_out3(a / 10.0)
        for k in range(3):
            d = (6 + 16 * k) * ps * sc * e
            pen.glow(x + u[0] * d, y + u[1] * d, (22 - 5 * k) * ps * sc * (0.6 + 0.6 * e), c, (190 - 50 * k) * (1 - a / 10.0))
    pen.glow(x, y, (26 + 20 * S.ease_out3(q)) * ps * sc, c, 120 * (1 - q), 0.4)
    # rays spilling forward
    if a < 9:
        f = 1 - a / 9.0
        e = S.ease_out3(a / 4.0)
        for j in range(9):
            r = S.rng_for(inst.seed, j, 500 + salt)
            an = ang + r.uniform(-38, 38) * S.D
            ln = r.uniform(40, 110) * ps * sc * e
            w = r.uniform(3, 6) * ps * sc
            d0 = 6 * ps * sc
            pts = [(x + math.cos(an) * (d0 + ln * k / 6.0), y + math.sin(an) * (d0 + ln * k / 6.0)) for k in range(7)]
            pen.poly(_taper(pts, w * f), c, 170 * f)
            pen.poly(_taper(pts, w * 0.35 * f), S.HOT, 230 * f)
    # small impact star
    if a < 7:
        qs = a / 7.0
        e = S.ease_out3(a / 3.0)
        pen.poly(_burst(inst, x, y, ang, 8, (14 + 22 * e) * ps * sc, (5 + 6 * e) * ps * sc, 520 + salt), c, 210 * (1 - qs))
        pen.poly(_burst(inst, x, y, ang, 8, (8 + 12 * e) * ps * sc, (3 + 3 * e) * ps * sc, 520 + salt), S.HOT,
                 255 * (1 - qs) ** 1.5)
    # shock ring across the blow, squashed along it, and a broken one further out
    for (n, d0, k) in ((0, 0, 1.0), (1, 4, 1.6)):
        aa = a - d0
        if aa < 0:
            continue
        qq = aa / float(IMPACT_LIFE - d0)
        e = S.ease_out3(qq)
        cx, cy = x + u[0] * 10 * ps * sc * e * k, y + u[1] * 10 * ps * sc * e * k
        rx, ry = (4 + 10 * e) * ps * sc * k, (10 + 46 * e) * ps * sc * k
        if n == 0:
            pen.ring(cx, cy, rx, ry, ang, c, 210 * (1 - qq), 3.0 * ps * (1 - qq) + 0.2)
            pen.ring(cx, cy, rx, ry, ang, S.HOT, 160 * (1 - qq) ** 2, 1.0 * ps * (1 - qq) + 0.1)
        else:
            _arc_ring(pen, inst, cx, cy, rx, ry, ang, c, 190 * (1 - qq), 2.2 * ps * (1 - qq) + 0.2, 540 + salt)
    # air-friction sparks thrown mostly forward
    n_sp = max(0, F.jround(14 * float(P.get("density") or 1) * sc))
    for j in range(n_sp):
        r = S.rng_for(inst.seed, j, 560 + salt)
        life = 10 + 10 * r()
        if a >= life:
            continue
        an = ang + r.uniform(-65, 65) * S.D
        sp = r.uniform(3, 9) * ps
        fd = S.drag_dist(0.87, a)
        sx, sy = x + math.cos(an) * sp * fd, y + math.sin(an) * sp * fd + 0.1 * ps * a * a
        dk = 0.87 ** a
        qq = a / life
        pen.line(sx, sy, sx - math.cos(an) * sp * dk * 1.6, sy - math.sin(an) * sp * dk * 1.6, S.mix(S.HOT, c, qq),
                 255 * (1 - qq), 1.5 * ps)


def _arc_ring(pen, inst, x, y, rx, ry, ang, c, a, w, salt):
    """A ring broken into 3-5 arcs with gaps (rx along ang)."""
    if a <= 1 or w <= 0.05 or rx <= 0.5 or ry <= 0.5:
        return
    r = S.rng_for(inst.seed, 0, salt)
    n = 3 + F.trunc(r() * 3)
    t0 = r() * math.pi * 2
    ca, sa = math.cos(ang), math.sin(ang)
    st = math.pi * 2 / n
    for i in range(n):
        s0 = t0 + i * st
        s1 = s0 + st * r.uniform(0.55, 0.85)
        pts = []
        for k in range(9):
            t = s0 + (s1 - s0) * k / 8.0
            px, py = math.cos(t) * rx, math.sin(t) * ry
            pts.append((x + px * ca - py * sa, y + px * sa + py * ca))
        pen.polyline(pts, c, a, w)


def _imp_gritty(pen, inst, P, c, ps, x, y, a, sc, salt, u):
    """Physical: a brief flash, a distortion ring (light and dark side by
    side, like refraction), a dust burst off the body, debris and sweat
    spray flying on with the blow."""
    ang = math.atan2(u[1], u[0])
    pen.add(False)
    # dust burst off the body, pushed along the blow
    for j in range(7):
        r = S.rng_for(inst.seed, j, 600 + salt)
        life = 16 + 10 * r()
        if a >= life:
            continue
        q = a / life
        an = ang + r.uniform(-70, 70) * S.D
        d = r.uniform(1.0, 2.4) * ps * S.drag_dist(0.85, a) * sc
        rad = (7 + 17 * S.ease_out3(q)) * ps * sc * r.uniform(0.7, 1.3)
        pen.glow(x + math.cos(an) * d, y + math.sin(an) * d, rad, DUST, 185 * (1 - q), 0.6)
    # distortion rings
    for (d0, k) in ((0, 1.0), (3, 1.5)):
        aa = a - d0
        if aa < 0 or aa >= 12:
            continue
        qq = aa / 12.0
        e = S.ease_out3(qq)
        cx, cy = x + u[0] * 8 * ps * sc * e * k, y + u[1] * 8 * ps * sc * e * k
        rx, ry = (5 + 10 * e) * ps * sc * k, (12 + 40 * e) * ps * sc * k
        pen.ring(cx, cy, rx, ry, ang, INK, 110 * (1 - qq), 3.0 * ps * (1 - qq) + 0.3)
        pen.ring(cx, cy, rx + 2.5 * ps, ry + 2.5 * ps, ang, (225, 228, 235), 120 * (1 - qq), 1.6 * ps * (1 - qq) + 0.2)
    # debris chips and sweat spray, with gravity
    n = max(0, F.jround(12 * float(P.get("density") or 1) * sc))
    for j in range(n):
        r = S.rng_for(inst.seed, j, 620 + salt)
        life = 14 + 10 * r()
        if a >= life:
            continue
        q = a / life
        an = ang + r.uniform(-55, 55) * S.D
        sp = r.uniform(2.5, 7.0) * ps
        fd = S.drag_dist(0.9, a)
        px, py = x + math.cos(an) * sp * fd, y + math.sin(an) * sp * fd + 0.16 * ps * a * a
        if j % 3 == 0:
            sz = r.uniform(2.2, 3.8) * ps
            pen.poly([(px - sz, py), (px, py - sz * 0.8), (px + sz, py), (px, py + sz * 0.7)], ROCK, 245 * (1 - q))
        else:
            pen.glow(px, py, r.uniform(2.0, 3.4) * ps, (225, 230, 238), 240 * (1 - q), 0.7)
    # the flash, brief
    if a < 3:
        pen.add(True)
        pen.glow(x, y, (18 + 10 * a) * ps * sc, S.HOT, 230 * (1 - a / 3.0))
        pen.add(False)
    # a few short dark impact lines
    if a < 8:
        f = 1 - a / 8.0
        for j in range(6):
            r = S.rng_for(inst.seed, j, 640 + salt)
            an = ang + r.uniform(-80, 80) * S.D
            r0 = (14 + 20 * S.ease_out3(a / 8.0)) * ps * sc
            ln = r.uniform(8, 16) * ps * sc
            pen.line(x + math.cos(an) * r0, y + math.sin(an) * r0, x + math.cos(an) * (r0 + ln),
                     y + math.sin(an) * (r0 + ln), INK, 170 * f, 1.4 * ps)


# ================================================================ environment
# An event: (kind, age, x, y, ux, uy, size, salt).  push = dust under the
# attacker as the strike starts (u = the way it is thrown); ground = a wave
# along the ground under the impact; crater = the axe kick's crater; kickup =
# dust thrown up as the rising kick starts; vortex = wind round the body
# (x, y = centre, ux = radius, uy = turn sign, size = fade, age = tick).
def env(pen, inst, P, c, ps, ev):
    lk = look(P, "fx_env")
    if lk == "off":
        return
    kind = ev[0]
    if kind == "vortex":
        _vortex(pen, inst, lk, c, ps, ev)
    elif kind == "crater":
        _crater(pen, inst, P, lk, c, ps, ev)
    else:
        _ground(pen, inst, P, lk, c, ps, ev)


def _puffs(pen, inst, lk, ps, x, y, a, life, n, spread_x, rise, size, salt, dirx=0.0, c=None):
    """n dust puffs born at (x, y), drifting along the ground (dirx: the way;
    0 = both ways), rising and shrinking away.  ink: one cloud — every puff's
    ink rim first, then the paper over them, so only the outside edge shows."""
    live = []
    for j in range(n):
        r = S.rng_for(inst.seed, j, salt)
        lf = life * r.uniform(0.7, 1.0)
        if a >= lf:
            continue
        q = a / lf
        e = S.ease_out3(q)
        sd = dirx if dirx else (1.0 if j % 2 == 0 else -1.0)
        px = x + sd * spread_x * e * r.uniform(0.4, 1.0) * (0.55 if lk == "ink" else 1.0)
        py = y - rise * e * r.uniform(0.3, 1.0)
        rad = size * (0.6 + 0.9 * e) * r.uniform(0.7, 1.3)
        live.append((px, py, rad, q))
    if lk == "ink":
        for (px, py, rad, q) in live:
            rr = rad * (1 - q)
            if rr > 0.8:
                pen.poly(_circle(px, py, rr + 1.6 * ps, 14), INK, 235)
        for (px, py, rad, q) in live:
            rr = rad * (1 - q)
            if rr > 0.8:
                pen.poly(_circle(px, py, rr, 14), PAPER, 245)
                pen.poly(_circle(px + rr * 0.25, py + rr * 0.3, rr * 0.55, 10), (196, 200, 214), 200)
    elif lk == "energy":
        for (px, py, rad, q) in live:
            pen.glow(px, py, rad * 0.8, c, 150 * (1 - q), 0.5)
    else:
        for (px, py, rad, q) in live:
            pen.glow(px, py, rad * 1.4, DUST, 150 * (1 - q), 0.6)


def _ground(pen, inst, P, lk, c, ps, ev):
    kind, a, x, y, ux, uy, sc, salt = ev
    if kind == "push":
        if a < 0 or a >= 16:
            return
        pen.add(lk == "energy")
        if lk == "energy":
            q = a / 16.0
            e = S.ease_out3(q)
            pen.ring(x, y, (6 + 26 * e) * ps * sc, (2 + 6 * e) * ps * sc, 0.0, c, 180 * (1 - q), 2.0 * ps * (1 - q) + 0.2)
        _puffs(pen, inst, lk, ps, x, y, a, 16, 4, 26 * ps * sc, 8 * ps * sc, 6 * ps * sc, 700 + salt, ux if ux else 0.0, c)
        return
    if kind == "kickup":
        if a < 0 or a >= 18:
            return
        pen.add(lk == "energy")
        n = max(1, F.jround(5 * float(P.get("density") or 1)))
        _puffs(pen, inst, lk, ps, x, y, a, 18, n, 12 * ps, 26 * ps, 7 * ps, 720 + salt, 0.0, c)
        return
    # ground: the wave along the ground under an impact
    if a < 0 or a >= ENV_LIFE:
        return
    q = a / float(ENV_LIFE)
    e = S.ease_out3(q)
    R = (14 + 56 * e) * ps * sc
    if lk == "energy":
        pen.add(True)
        pen.ring(x, y, R, R * 0.2, 0.0, c, 200 * (1 - q), 2.6 * ps * (1 - q) + 0.2)
        pen.glow(x, y, R * 0.7, c, 90 * (1 - q), 0.4)
        for j in range(6):
            r = S.rng_for(inst.seed, j, 740 + salt)
            sd = 1.0 if j % 2 == 0 else -1.0
            px = x + sd * R * r.uniform(0.5, 1.0)
            pen.line(px, y, px + sd * 8 * ps, y - r.uniform(2, 10) * ps * (1 - q), S.mix(c, S.HOT, 0.5), 220 * (1 - q),
                     1.3 * ps)
        return
    pen.add(False)
    if lk == "ink":
        pen.ring(x, y, R, R * 0.2, 0.0, INK, 220 * (1 - q), 3.6 * ps * (1 - q) + 0.4)
        pen.ring(x, y, R, R * 0.2, 0.0, PAPER, 240 * (1 - q), 1.6 * ps * (1 - q) + 0.2)
    _puffs(pen, inst, lk, ps, x, y, a, ENV_LIFE, 6, R * 1.1, 10 * ps * sc, 7 * ps * sc, 760 + salt, 0.0, c)


def _crater(pen, inst, P, lk, c, ps, ev):
    """Axe kick: a crater, cracks running along the ground, debris thrown up
    and a ground wave (laid flat)."""
    _k, a, x, y, _ux, _uy, sc, salt = ev
    if a < 0 or a >= CRATER_LIFE:
        return
    q = a / float(CRATER_LIFE)
    e = S.ease_out3(min(1.0, a / 8.0))
    R = (22 + 26 * e) * ps * sc
    ink, energy = lk == "ink", lk == "energy"
    pen.add(False)
    if ink:
        _outlined(pen, _ellipse(x, y, R, R * 0.32, 0.0), INK, 200 * (1 - q), PAPER, 220 * (1 - q), 1.4 * ps)
    elif energy:
        pen.poly(_ellipse(x, y, R, R * 0.32, 0.0), SCORCH, 120 * (1 - q))
    else:
        pen.poly(_ellipse(x, y, R, R * 0.32, 0.0), SCORCH, 140 * (1 - q))
        pen.ring(x, y, R, R * 0.32, 0.0, DUST, 200 * (1 - q), 2.0 * ps)
    # cracks
    pen.add(energy)
    for j in range(7):
        r = S.rng_for(inst.seed, j, 780 + salt)
        side = 0.0 if j % 2 == 0 else math.pi
        an = side + r.uniform(-0.35, 0.35)
        ln = (20 + 60 * e) * ps * sc * r.uniform(0.6, 1.2)
        pts = [(x, y)]
        for k in range(1, 5):
            d = ln * k / 4.0
            jit = r.uniform(-0.5, 0.5) * 6 * ps
            pts.append((x + math.cos(an) * d, y + math.sin(an) * d * 0.4 + jit))
        if energy:
            pen.polyline(pts, c, 220 * (1 - q), 2.6 * ps)
            pen.polyline(pts, S.HOT, 200 * (1 - q) ** 2, 1.0 * ps)
        elif ink:
            pen.polyline(pts, INK, 240 * (1 - q), 2.4 * ps)
        else:
            pen.polyline(pts, (24, 18, 16), 200 * (1 - q), 1.6 * ps)
    # debris thrown up
    pen.add(False)
    n = max(0, F.jround(8 * float(P.get("density") or 1)))
    for j in range(n):
        r = S.rng_for(inst.seed, j, 800 + salt)
        vx = r.uniform(-3.0, 3.0) * ps
        vy = -r.uniform(3.0, 7.0) * ps
        rx_, ry_ = x + vx * a, y + vy * a + 0.225 * ps * a * a
        if ry_ > y + 4 * ps:
            continue
        sz = r.uniform(2.0, 4.0) * ps
        rock = [(rx_ - sz, ry_), (rx_, ry_ - sz), (rx_ + sz, ry_), (rx_, ry_ + sz * 0.7)]
        if ink:
            _outlined(pen, rock, PAPER, 240, INK, 240, 1.3 * ps)
        elif energy:
            pen.add(True)
            pen.glow(rx_, ry_, sz * 1.6, c, 200 * (1 - q), 0.5)
            pen.add(False)
            pen.poly(rock, ROCK, 220 * (1 - q))
        else:
            pen.poly(rock, ROCK, 230 * (1 - q))
    # the ground wave and dust
    _ground(pen, inst, P, lk, c, ps, ("ground", a, x, y, 0.0, 0.0, sc * 1.2, salt + 1))


def _swirl(pen, x, y, rx, ry, rot, c, a, w, ink):
    """Three arcs of an ellipse, turned by rot."""
    for i in range(3):
        s0 = rot + i * 2 * math.pi / 3
        pts = [(x + math.cos(s0 + 1.2 * k / 8.0) * rx, y + math.sin(s0 + 1.2 * k / 8.0) * ry) for k in range(9)]
        if ink:
            pen.poly(_taper(pts, w + 2.2), INK, a * 0.85)
            pen.poly(_taper(pts, w), PAPER, a)
        else:
            pen.poly(_taper(pts, w), c, a)


def _vortex(pen, inst, lk, c, ps, ev):
    """Spinning kick: wind round the body, turning with the kick."""
    _k, t, ox, oy, L, s, fade, _salt = ev
    ink = lk == "ink"
    pen.add(lk == "energy")
    col = S.mix(c, S.HOT, 0.3) if lk == "energy" else DUST
    for j in range(3):
        rx = L * (0.8 + 0.25 * j)
        _swirl(pen, ox, oy + L * 0.15 * (j - 1), rx, rx * 0.32, s * (t * 0.55 + j * 1.3), col, (190 - 40 * j) * fade,
               (3.2 - 0.7 * j) * ps, ink)


# ================================================================ hit weight
def shake(inst, host):
    """Screen shake (params shake / shake_px / shake_ticks), with the strike's
    hit-stop (strikefx._freeze): once per strike."""
    P = inst.fx["params"]
    fn = getattr(host, "shake", None) if host is not None else None
    if not P.get("shake") or fn is None:
        return
    n = max(0, F.trunc(float(P.get("shake_ticks") or 0)))
    px = max(0.0, float(P.get("shake_px") or 0))
    if n > 0 and px > 0:
        fn(px, n)


def squash_of(P):
    """(ticks, amount, flash) of a strike's target squash, or None."""
    if not P.get("squash"):
        return None
    n = max(0, F.trunc(float(P.get("squash_ticks") or 0)))
    amt = min(0.8, max(0.0, float(P.get("squash_amt") or 0)))
    if n <= 0 or (amt <= 0 and not P.get("squash_flash")):
        return None
    return n, amt, bool(P.get("squash_flash"))
