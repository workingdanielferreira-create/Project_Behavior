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
                front of it; when it lands: a white flash, an uneven impact
                star (spikes longest along the punch), three shockwave rings
                standing across the punch line and squashed along it (the
                outer two broken into arcs), a punch-through blast out of the
                target's far side, radial speed lines and sparks.  A whiff
                gives a smaller burst at full reach.

Hit options (HIT_OPTION_STYLES; params, fxkit.PRIM_DEFAULTS["technique"]):

  hitstop / hitstop_ticks   the world freezes (World.hitstop_ticks) for that
                many ticks when the strike lands, once per strike.  Solo has
                no opponent, so it freezes as the whiff bursts instead.
  kb_dir / kb_angle_deg     which way a landed strike pushes (Battle): aim
                (as every FX hit), tangent (the way the fist moves at contact)
                or custom (kb_angle_deg turned from that, clockwise, mirrored
                with the facing).
  impact_frame / impact_frame_r   off / local / full: for IMPACT_FRAME_TICKS
                a white flash crossed by ink focus lines converging on the
                contact point, then the inverse; local inside impact_frame_r
                px, full over the whole overlay.

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

Intercept (fx.intercept, ki barrage; the charged blast's orb shares it,
laser/gunfx.py track_step): every orb in flight is its own
auto-projectile tracker (track_step).  An enemy projectile within the
tracker radius pulls the orb off its path (up to turn_deg per tick, speed
kept); from then on the orb flies a recorded path (inst.tq_kd) instead of
its rolled one, straight on once nothing is in range.  Within contact px
the two meet: block = both gone (the orb detonates there), destroy = the
enemy projectile is gone and the orb flies on, deflect = the enemy
projectile is knocked away (deflect "both": the orb too, which then stops
tracking).  Orbs also take the enemy's gun / ki bullets, which other
intercepts cannot (fxkit.orb_takes).  Solo has no enemy projectiles, so
the orbs fly their own paths there.
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
IMPACT_FRAME_TICKS = 2       # impact frame: a white flash with ink focus lines, then the inverse
FULL_FRAME = 20000.0         # half-size of the full-overlay impact frame, px
THROUGH_LIFE = 14            # punch-through: the blast out of the target's far side
THROUGH_GAP = 22.0           # ...bursting this far past the contact point, px (x scale)
INK = (16, 10, 22)           # impact-frame ink

# Hit options (params hitstop / hitstop_ticks, kb_dir / kb_angle_deg,
# impact_frame / impact_frame_r): the strikes they apply to.
HIT_OPTION_STYLES = ("impact_punch",)


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
    __slots__ = ("i", "b", "sp", "ang", "curve", "size", "rng", "flight", "side", "tint", "kind", "ox", "oy", "trk")

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
        self.size *= inst.tq_grow.get(i, 1.0)   # grown by absorbing (fxkit.absorb_grow)
        ru = r.uniform(KI_RANGE[0], KI_RANGE[1])
        self.rng = float(P["length"]) * ru * ps
        self.flight = max(1, int(math.ceil(float(P["length"]) * ru / su)))
        self.side = 1 if i % 2 == 0 else -1
        self.tint = r.uniform(0.0, 0.4)
        self.kind = min(2, int(r() * 3))
        path = inst.tq_path
        self.ox, self.oy = path[min(self.b, len(path) - 1)]
        self.trk = inst.tq_kd.get(i)

    def pos(self, fr, k):
        """World position k ticks after launch (k may run past the range).
        From the tick an intercept pulled it off its path: the recorded one."""
        tr = self.trk
        if tr is not None and self.b + k >= tr[0]:
            h = tr[1]
            j = self.b + k - tr[0]
            n = int(j)
            if n >= len(h) - 1:
                return h[-1]
            u = j - n
            (ax, ay), (bx, by) = h[n], h[n + 1]
            return ax + (bx - ax) * u, ay + (by - ay) * u
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


def live_points(inst, ps):
    """[(i, x, y, vx, vy)] for the ki shots in flight this tick (i = the
    shot's index; ki barrage only; strikefx.js livePoints)."""
    if _style_of(inst) != "ki_barrage":
        return []
    out = []
    fr = _Fr(inst, ps)
    for (s, (x, y)) in _live(inst, ps):
        k = inst.age - s.b
        if k >= 1:
            x0, y0 = s.pos(fr, k - 1)
            vx, vy = x - x0, y - y0
        else:
            x1, y1 = s.pos(fr, 1)
            vx, vy = x1 - x, y1 - y
        out.append((s.i, x, y, vx, vy))
    return out


def shot_ids(inst, ps):
    """Indices of the ki shots in flight this tick: each clashes on its own
    as a sprite (laser/clash.py)."""
    if _style_of(inst) != "ki_barrage" or inst.age >= inst.life:
        return []
    return [s.i for (s, _p) in _live(inst, ps)]


def shot_at(inst, i, ps):
    """(x, y, vx, vy, radius, ticks left) of ki shot i while it flies, else None."""
    P = inst.fx["params"]
    if not 0 <= i < ki_count(P):
        return None
    s = Shot(inst, i, ps)
    e = s.end(inst)[0]
    if not s.b <= inst.age < e:
        return None
    fr = _Fr(inst, ps)
    k = inst.age - s.b
    x, y = s.pos(fr, k)
    x1, y1 = s.pos(fr, k + 1)
    return x, y, x1 - x, y1 - y, float(P["radius"]) * ps * s.size, e - inst.age


def _style_of(inst):
    return S._style(inst.fx["params"])


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


# ---------------------------------------------------------------- intercept
class _Mover:
    """An orb as fxkit.deflect_vels reads a projectile."""
    __slots__ = ("x", "y", "vx", "vy")

    def __init__(self, x, y, vx, vy):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy


def _trk_put(tr, t, x, y):
    """Record where a tracked orb is on tick t + 1 (tr[1][j] = tick tr[0] + j)."""
    h = tr[1]
    n = t + 1 - tr[0]
    while len(h) < n:
        h.append(h[-1])
    del h[n:]
    h.append((x, y))


def track_step(inst, host):
    """Intercept for the ki barrage (fx.intercept): each orb in flight this
    tick meets, chases or ignores the enemy's projectiles (host.shots), and
    a tracked orb's next position is recorded (strikefx.js trackStep)."""
    fx = inst.fx
    if host is None or S._style(fx["params"]) != "ki_barrage" or inst.age >= inst.life:
        return
    ps = inst.ps or 1.0
    fr = _Fr(inst, ps)
    track_shots(inst, host, _live(inst, ps), lambda s, k: s.pos(fr, k))


def track_shots(inst, host, live, pos):
    """Intercept for a technique's own shots (ki orbs, the charged blast's
    orb: gunfx.track_step): live = [(shot, (x, y))] in flight this tick, pos(s,
    k) = shot s k ticks after launch.  A shot has i, b, size and trk (its
    recorded path, inst.tq_kd[i])."""
    fx = inst.fx
    ic = fx.get("intercept") or {}
    on = bool(ic.get("enabled"))
    if not on and not inst.tq_kd:
        return
    ps = inst.ps or 1.0
    mode = ic.get("mode") if ic.get("mode") in F.INTERCEPT_MODES else "block"
    contact = max(0.0, float(ic.get("contact") or 0)) * ps
    radius = max(0.0, float(ic.get("radius") or 0)) * ps
    lim = max(0.0, float(ic.get("turn_deg") or 0)) * S.D
    r0 = float(fx["params"]["radius"]) * ps
    cb = getattr(host, "on_intercept", None)
    t = inst.age
    for (s, (x, y)) in live:
        tr = s.trk
        if tr is not None:
            vx, vy = tr[2], tr[3]
        else:
            x1, y1 = pos(s, t - s.b + 1)
            vx, vy = x1 - x, y1 - y
        kb = F.inst_knockback(inst, s.i)
        if on and not (tr is not None and tr[4]):
            hit = F.orb_contact(x, y, r0 * s.size, host, contact, mode, kb)
            if hit is not None:
                hit.dead = True
                if mode == "deflect":
                    both = ic.get("deflect_who") == "both"
                    ev, mv = F.deflect_vels(_Mover(x, y, vx, vy), hit, both)
                    if cb:
                        cb(inst, hit, "deflect", ev, bool(ic.get("hurts_owner")))
                    if both:   # knocked away too: flies straight on, tracking no more
                        if tr is None:
                            tr = inst.tq_kd[s.i] = [t, [(x, y)], vx, vy, False]
                        tr[2], tr[3], tr[4] = mv[0], mv[1], True
                else:
                    if cb:
                        cb(inst, hit, mode, None, False)
                    if mode == "block":   # both gone: the orb detonates where they met
                        inst.tq_ki[s.i] = (t, x, y)
                        continue
                    if mode == "absorb":  # swallowed: this orb grows
                        F.absorb_grow(inst, s.i)
                        kb = F.inst_knockback(inst, s.i)
            if tr is None or not tr[4]:
                tgt = F.orb_nearest(x, y, host, radius, mode, kb)
                if tgt is not None:
                    spd = math.hypot(vx, vy)
                    cur = math.atan2(vy, vx)
                    da = math.atan2(tgt.y - y, tgt.x - x) - cur
                    while da > math.pi:
                        da -= 2 * math.pi
                    while da < -math.pi:
                        da += 2 * math.pi
                    cur += max(-lim, min(lim, da))
                    vx, vy = math.cos(cur) * spd, math.sin(cur) * spd
                    if tr is None:
                        tr = inst.tq_kd[s.i] = [t, [(x, y)], vx, vy, False]
                    tr[2], tr[3] = vx, vy
        if tr is not None:
            _trk_put(tr, t, x + tr[2], y + tr[3])


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


# ---------------------------------------------------------------- hit options
def _opts_on(P):
    return S._style(P) in HIT_OPTION_STYLES


def hitstop_ticks(P):
    """Hit-stop (params hitstop / hitstop_ticks): how many ticks the world
    freezes when the strike lands; 0 = none."""
    if not _opts_on(P) or not P.get("hitstop"):
        return 0
    return max(0, F.trunc(float(P.get("hitstop_ticks") or 0)))


def _freeze(inst, host):
    n = hitstop_ticks(inst.fx["params"])
    fn = getattr(host, "hitstop", None) if host is not None else None
    if n > 0 and fn is not None and not inst.tq_hs:
        inst.tq_hs = True          # one freeze per strike, however often it re-hits
        fn(n)


def hit_freeze(inst, host):
    """The strike just landed: its hit-stop (World.hitstop_ticks)."""
    _freeze(inst, host)


def hitstop_step(inst, host):
    """Solo has no opponent, so nothing lands: the strike freezes as its whiff
    bursts at full reach instead (on_tick runs before the age moves on)."""
    P = inst.fx["params"]
    if host is None or not _opts_on(P) or not getattr(host, "solo", False):
        return
    if not inst.tq_imp and inst.age + 1 == S._swing(P):
        _freeze(inst, host)


def hit_dir(inst):
    """Knockback direction of a landed strike (params kb_dir): aim = the
    effect's aim (as every FX hit), tangent = the way the fist / foot moves at
    contact, custom = kb_angle_deg turned from that (clockwise, mirrors with
    the facing)."""
    P = inst.fx["params"]
    mode = P.get("kb_dir") or "aim"
    if not _opts_on(P) or mode not in ("tangent", "custom"):
        return inst.dir
    if mode == "tangent":
        return inst.tq_f
    return tuple(F.rot(inst.tq_f, float(P.get("kb_angle_deg") or 0) * inst.tq_m))


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
def gone_silent(inst, i):
    """Shot i vanished without a blast (absorbed by an enemy, or split by a
    clash: its halves fly on)."""
    h = inst.tq_ki.get(i)
    return h is not None and len(h) > 3 and bool(h[3])


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
        if a < 0 or a >= KI_SMOKE_LIFE or gone_silent(inst, s.i):
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
        if a >= KI_BLAST_LIFE or gone_silent(inst, s.i):
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


def _star(pen, inst, x, y, ang, n, r_out, r_in, c, a, salt):
    """An uneven impact star: the spikes are longest along the strike (ang),
    shortest across it, with a shorter kick back the way the fist came."""
    pts = []
    for j in range(2 * n):
        an = ang + math.pi * j / n
        rr = r_in
        if j % 2 == 0:
            r = S.rng_for(inst.seed, j, 60 + salt)
            an += r.uniform(-0.3, 0.3) * math.pi / n
            k = math.cos(an - ang)
            rr = r_out * (0.45 + 0.65 * max(0.0, k) ** 2 + 0.25 * max(0.0, -k) ** 2) * r.uniform(0.75, 1.2)
        pts.append((x + math.cos(an) * rr, y + math.sin(an) * rr))
    pen.poly(pts, c, a)


def _arc_ring(pen, inst, x, y, rx, ry, ang, c, a, w, salt):
    """A shock ring broken into 3-5 arcs with gaps (rx along ang)."""
    if a <= 1 or w <= 0.05 or rx <= 0.5 or ry <= 0.5:
        return
    r = S.rng_for(inst.seed, 0, 80 + salt)
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


def _through(pen, inst, c, ps, x, y, a, sc, salt):
    """Punch-through: the blow carries on out of the target's far side, a
    cone of wind and light bursting along the punch line (a whiff: the air
    it pushed)."""
    if a < 0 or a >= THROUGH_LIFE:
        return
    q = a / float(THROUGH_LIFE)
    e = S.ease_out3(min(1.0, a / 6.0))
    fx_, fy_ = inst.tq_f
    nx, ny = -fy_, fx_
    g = THROUGH_GAP * ps * sc
    bx, by = x + fx_ * g, y + fy_ * g

    def p(u, v):
        return bx + fx_ * u + nx * v, by + fy_ * u + ny * v

    L = (30 + 90 * e) * ps * sc
    W = (10 + 34 * e) * ps * sc
    fade = 1 - q
    pen.poly([p(0, W * 0.25), p(L * 0.75, W), p(L, 0), p(L * 0.75, -W), p(0, -W * 0.25)], c, 120 * fade)
    pen.poly([p(0, W * 0.1), p(L * 0.6, W * 0.45), p(L * 0.85, 0), p(L * 0.6, -W * 0.45), p(0, -W * 0.1)], S.HOT,
             170 * fade ** 1.5)
    for j in range(7):
        r = S.rng_for(inst.seed, j, 110 + salt)
        off = r.uniform(-1.0, 1.0) * W * 0.9
        s0 = r.uniform(0.1, 0.5) * L
        ln = r.uniform(0.35, 0.7) * L
        x0, y0 = p(s0, off)
        x1, y1 = p(s0 + ln, off * 1.4)
        pen.line(x0, y0, x1, y1, S.mix(S.HOT, c, q), 220 * fade, 1.3 * ps)


def _impact_frame(pen, inst, c, ps, x, y, a, sc, salt):
    """Impact frame (params impact_frame): a white flash crossed by ink focus
    lines converging on the contact point, then the inverse (ink, light lines).
    local = inside impact_frame_r, full = the whole overlay."""
    P = inst.fx["params"]
    mode = P.get("impact_frame") or "off"
    if not _opts_on(P) or mode not in ("local", "full") or a < 0 or a >= IMPACT_FRAME_TICKS:
        return
    full = mode == "full"
    R = FULL_FRAME if full else float(P.get("impact_frame_r") or 0) * ps * sc
    if R <= 1:
        return
    lit = a == 0
    bg, fg = (S.HOT, INK) if lit else (INK, S.mix(c, S.HOT, 0.5))
    pen.add(False)
    if full:
        pen.poly([(x - R, y - R), (x + R, y - R), (x + R, y + R), (x - R, y + R)], bg, 190 if lit else 150)
    else:
        pen.glow(x, y, R, bg, 235 if lit else 200, 0.7)
    Rl = 1400.0 * ps if full else R
    n = 32 if full else 22
    for j in range(n):
        r = S.rng_for(inst.seed, j, 130 + salt)
        an = (j + r.uniform(-0.4, 0.4)) * math.pi * 2 / n
        r0 = Rl * r.uniform(0.18, 0.45)
        hw = r.uniform(0.012, 0.03)
        pen.poly([(x + math.cos(an - hw) * Rl, y + math.sin(an - hw) * Rl),
                  (x + math.cos(an + hw) * Rl, y + math.sin(an + hw) * Rl),
                  (x + math.cos(an) * r0, y + math.sin(an) * r0)], fg, 230 if lit else 200)
    pen.add(True)


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
        _star(pen, inst, x, y, ang, 8, (16 + 28 * e) * ps * sc, (6 + 8 * e) * ps * sc, c, 225 * (1 - qs), salt)
        _star(pen, inst, x, y, ang, 8, (9 + 16 * e) * ps * sc, (3.5 + 4 * e) * ps * sc, S.HOT, 255 * (1 - qs) ** 1.5,
              salt)
    pen.glow(x, y, (26 + 20 * S.ease_out3(q)) * ps * sc, c, 140 * (1 - q), 0.4)
    _through(pen, inst, c, ps, x, y, a, sc, salt)
    # shockwave rings standing across the punch line, squashed along it: a
    # full one, then two broken into arcs, each further out and faster
    for (n, d0, k) in ((0, 0, 1.0), (1, 3, 1.45), (2, 6, 1.9)):
        aa = a - d0
        if aa < 0:
            continue
        qq = aa / float(PUNCH_IMPACT_LIFE - d0)
        e = S.ease_out3(qq)
        cx, cy = x + fx_ * 10 * ps * sc * e * k, y + fy_ * 10 * ps * sc * e * k
        rx, ry = (4 + 10 * e) * ps * sc * k, (10 + 50 * e) * ps * sc * k
        if n == 0:
            pen.ring(cx, cy, rx, ry, ang, c, 210 * (1 - qq), 3.0 * ps * (1 - qq) + 0.2)
            pen.ring(cx, cy, rx, ry, ang, S.HOT, 160 * (1 - qq) ** 2, 1.0 * ps * (1 - qq) + 0.1)
        else:
            _arc_ring(pen, inst, cx, cy, rx, ry, ang, c, 200 * (1 - qq), (3.4 - n) * ps * (1 - qq) + 0.2, salt + n)
            _arc_ring(pen, inst, cx, cy, rx, ry, ang, S.HOT, 150 * (1 - qq) ** 2, 0.9 * ps * (1 - qq) + 0.1, salt + n)
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


def _impacts(inst, P, fr, ps):
    """(age, x, y, size, salt) of every impact on show: where the fist was
    when it landed; a whiff bursts smaller at full reach."""
    t = inst.age
    if inst.tq_imp:
        return [(t - b, x, y, 1.0, 11 * n) for n, (b, x, y) in enumerate(inst.tq_imp)]
    L = float(P["length"]) * ps
    x, y = fr.w(L + float(P["radius"]) * ps * 0.8, 0)
    return [(t - S._swing(P), x, y, 0.55, 0)]


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
    imps = _impacts(inst, P, fr, ps)
    # 0: the impact frame, under everything else
    for (a, x, y, sc, salt) in imps:
        _impact_frame(pen, inst, c, ps, x, y, a, sc, salt)
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
    # 6: the impacts
    for (a, x, y, sc, salt) in imps:
        if 0 <= a < PUNCH_IMPACT_LIFE:
            _impact(pen, inst, c, ps, x, y, a, sc, salt)


def draw(pen, inst, host, ps):
    if S._style(inst.fx["params"]) == "ki_barrage":
        _draw_ki(pen, inst, host, ps)
    else:
        _draw_punch(pen, inst, host, ps)
