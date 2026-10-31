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
  impact_punch  the fist drives out along the aim and lands.  What it paints
                is laser/hitfx.py's three partitions: fx_motion (smear frames
                of the arm up to contact, broken air strokes, the fist),
                fx_impact (the hit, laid along the punch) and fx_env (push-off
                dust, a ground wave under the target), each off / ink /
                energy / gritty.  A whiff bursts smaller at full reach.

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

  flip_h / flip_v   mirror the ANIMATION in place (punch, ki barrage, every
                kick), never its placement: flip_v mirrors it across the aim
                line (through the anchor), flip_h front <-> back across the
                line square to the aim through the contact point (the punch:
                full reach; the ki barrage: Length out), so the strike still
                lands where it did.  The hit area follows the drawn limb /
                shots; push-off dust stays under the fighter (its direction
                follows flip_h), knockback "tangent" / "custom" follow the
                mirrored motion.  Fixed to the fighter: the facing still
                mirrors the whole thing as before.

  shake / shake_px / shake_ticks   the overlay shakes (World.shake) with
                the hit-stop: when it lands, Solo as it whiffs.
  squash / squash_amt / squash_ticks / squash_flash   the fighter hit squashes
                along the blow and flashes white (Figure.hit_squash; Battle).

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
from . import hitfx as H

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
INK = (16, 10, 22)           # impact-frame ink

# Hit options (params hitstop / hitstop_ticks, kb_dir / kb_angle_deg,
# impact_frame / impact_frame_r): the strikes they apply to.
HIT_OPTION_STYLES = ("impact_punch", "roundhouse_kick", "thrust_kick", "axe_kick", "spinning_kick", "rising_kick")


# Animation flips (params flip_h / flip_v): the strikes they apply to.
FLIP_STYLES = ("ki_barrage", "impact_punch", "roundhouse_kick", "thrust_kick", "axe_kick", "spinning_kick", "rising_kick")


def flips(P):
    """(h, v) signs of the animation flips: -1 = mirrored (params flip_h /
    flip_v; FLIP_STYLES only)."""
    if S._style(P) not in FLIP_STYLES:
        return 1.0, 1.0
    return (-1.0 if P.get("flip_h") else 1.0), (-1.0 if P.get("flip_v") else 1.0)


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
        if fr.h < 0:
            lx = 2 * fr.c - lx
        if fr.v < 0:
            ly = -ly
        dx, dy = fr.f.d(lx, ly)
        return self.ox + dx, self.oy + dy

    def end(self, inst):
        """(tick it detonates, stopped by a hit?)."""
        h = inst.tq_ki.get(self.i)
        if h is not None:
            return h[0], True
        return self.b + self.flight, False


class _Fr:
    """A ki shot's frame: the aim, the scale, the flips (h, v) and the line
    flip_h mirrors across (c px along the aim)."""
    __slots__ = ("f", "s", "h", "v", "c")

    def __init__(self, inst, ps):
        P = inst.fx["params"]
        self.f = S.Frame(0.0, 0.0, inst.tq_f, inst.tq_m)
        self.s = ps
        self.h, self.v = flips(P)
        self.c = float(P["length"]) * ps


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


def _along(P, u, L):
    """How far along the aim a point u px out of the punch is drawn: flip_h
    mirrors it across full reach L (the fist then comes in from 2 L)."""
    return 2 * L - u if flips(P)[0] < 0 else u


def _arm(inst, P, t, ps):
    """(shoulder, fist) world points of the punch at tick t, or None while
    it is in."""
    L = float(P["length"]) * ps
    l = _reach(P, t, L)
    if l <= 2:
        return None
    fr = S._frame(inst)
    return fr.w(_along(P, 0.0, L), 0), fr.w(_along(P, l, L), 0)


def _punch_hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life:
        return False
    P = inst.fx["params"]
    g = _arm(inst, P, inst.age, ps)
    if g is None:
        return False
    (ax, ay), (bx, by) = g
    return F.seg_dist(tx, ty, ax, ay, bx, by) <= hr + float(P["radius"]) * ps * 1.2


def _punch_body(inst, ps):
    P = inst.fx["params"]
    g = _arm(inst, P, inst.age, ps) if inst.age < inst.life else None
    if g is None:
        return None
    return [g[0], g[1]], float(P["radius"]) * ps


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
    """The strike's hit weight: its hit-stop and screen shake, once per
    strike however often it re-hits."""
    if inst.tq_hs or host is None or not _opts_on(inst.fx["params"]):
        return
    inst.tq_hs = True
    n = hitstop_ticks(inst.fx["params"])
    fn = getattr(host, "hitstop", None)
    if n > 0 and fn is not None:
        fn(n)
    H.shake(inst, host)


def hit_freeze(inst, host):
    """The strike just landed: its hit-stop (World.hitstop_ticks)."""
    _freeze(inst, host)


def hitstop_step(inst, host):
    """Solo has no opponent, so nothing lands: the strike freezes as its whiff
    bursts at full reach instead (on_tick runs before the age moves on)."""
    P = inst.fx["params"]
    if host is None or S._style(P) not in STYLES or not _opts_on(P) or not getattr(host, "solo", False):
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
    h, v = flips(P)
    f = (inst.tq_f[0] * h, inst.tq_f[1] * h)   # the way the (mirrored) fist moves
    if mode == "tangent":
        return f
    return tuple(F.rot(f, float(P.get("kb_angle_deg") or 0) * inst.tq_m * h * v))


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
        L = float(P["length"]) * ps
        l = _reach(P, inst.age, L) + float(P["radius"]) * ps * 0.8
        ix, iy = S._frame(inst).w(_along(P, l, L), 0)
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
            ux, uy = fr.f.d(math.cos(s.ang) * fr.h, math.sin(s.ang) * fr.v)
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


def _impacts(inst, P, fr, ps):
    """(age, x, y, size, salt, tick) of every impact on show: where the fist
    was when it landed; a whiff bursts smaller at full reach."""
    t = inst.age
    if inst.tq_imp:
        return [(t - b, x, y, 1.0, 11 * n, b) for n, (b, x, y) in enumerate(inst.tq_imp)]
    L = float(P["length"]) * ps
    x, y = fr.w(_along(P, L + float(P["radius"]) * ps * 0.8, L), 0)
    return [(t - S._swing(P), x, y, 0.55, 0, S._swing(P))]


def _motion(inst, P, fr, ps):
    """The punch for the motion partition (hitfx.Motion): shoulder -> fist."""
    L = float(P["length"]) * ps
    Ts, Th = S._swing(P), _hold(P)
    h = flips(P)[0]
    f = (inst.tq_f[0] * h, inst.tq_f[1] * h)
    rx, ry = fr.w(_along(P, 0.0, L), 0)

    def limb(t):
        tx, ty = fr.w(_along(P, _reach(P, t, L), L), 0)
        return rx, ry, tx, ty, f[0], f[1]
    return H.Motion(limb, 0, Ts, Ts, Ts + Th + PUNCH_RETRACT, float(P["radius"]) * ps, float(P["thickness"]) * ps)


def _feet(inst, b, ps):
    """Where the target's feet were on tick b."""
    tp = inst.tq_tp[min(max(0, b), len(inst.tq_tp) - 1)]
    return float(tp[1]) + H.FEET_DROP * ps


def _draw_punch(pen, inst, host, ps):
    P = inst.fx["params"]
    t = inst.age
    fr = S._frame(inst)
    c, _bright, _deep = S._colours(inst, host)
    imps = _impacts(inst, P, fr, ps)
    # 0: the impact frame, under everything else
    for (a, x, y, sc, salt, _b) in imps:
        _impact_frame(pen, inst, c, ps, x, y, a, sc, salt)
    # 1: the surroundings (fx_env): push-off dust under the fighter, a ground
    # wave under the target
    p0 = inst.tq_path[0]
    h = flips(P)[0]
    H.env(pen, inst, P, c, ps, ("push", t, p0[0], p0[1] + H.FEET_DROP * ps, -inst.tq_m * h, 0.0, 0.8, 0))
    for (a, x, y, sc, salt, b) in imps:
        H.env(pen, inst, P, c, ps, ("ground", a, x, _feet(inst, b, ps), 0.0, 0.0, sc * 0.7, salt))
    # 2: the fist and its motion (fx_motion)
    H.motion(pen, inst, P, t, ps, c, _motion(inst, P, fr, ps))
    # 3: the impacts (fx_impact)
    for (a, x, y, sc, salt, _b) in imps:
        H.impact(pen, inst, P, c, ps, x, y, a, sc, salt, (inst.tq_f[0] * h, inst.tq_f[1] * h))
    pen.add(False)


def draw(pen, inst, host, ps):
    if S._style(inst.fx["params"]) == "ki_barrage":
        _draw_ki(pen, inst, host, ps)
    else:
        _draw_punch(pen, inst, host, ps)
