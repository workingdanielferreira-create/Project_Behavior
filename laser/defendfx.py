"""
Defender FX — six ATTACHED techniques for the FX Kit "technique" primitive
(params.style), built on the sword techniques' pen, frame and colours
(laser/swordfx.py).  Daniel 2026-11-18: defensive FX that ARE the defender
doing the work (never a projectile shot at the target); each one carries
its own mechanics, separate from guard.py's defend types.

  aegis_wall        Block.  A curved wall of hexagonal energy cells snaps up
                    in front of the body, turning to face the target.  Enemy
                    shots crossing it are blocked at their source; direct
                    hits from the front lose df_reduce_pct; enemy melee /
                    area FX in front are cancelled (df_area).  Cells ripple,
                    crack and re-light where hits land; past df_hp damage the
                    wall shatters into shards.
  mirror_kata       Deflect / reflect.  Crescent blades of light whirl round
                    the body on a tilted ring at a surging, never-steady
                    speed.  Shots entering the ring are deflected off it,
                    reflected back at the target, or destroyed (df_result);
                    each catch flashes a mirror rune and a streak.
  chain_bastion     Intercept.  Spectral chains coil out of a sigil behind
                    the shoulder.  Any shot inside length px is lashed by a
                    free chain (moons = chains) and caught (df_result); with
                    df_enemies the chains also lash enemies in reach (hit,
                    knockback toward the defender with df_pull).
  repulse_nova      Knockback.  The defender plants, energy rushes in round a
                    ground glyph (swing_ticks), then a dome shockwave bursts
                    out to radius px over hold_ticks: every enemy it sweeps
                    is hit once and knocked straight OUT from the centre,
                    shots inside it are destroyed, ground cracks and dust.
  sanctuary_tether  Barrier an ally (Battle only).  A twisting tether of
                    light runs from the defender to a team-mate (df_pick) and
                    a dome of light rises round it: shots entering the dome
                    are blocked, hits on that team-mate lose df_reduce_pct,
                    the dome shatters past df_hp.
  lotus_mend        Heal an ally (Battle only).  Petals stream from the
                    defender into a team-mate while a lotus sigil blooms
                    under it; df_heal HP flows in over hold_ticks, with heal
                    rings running up its body.

Solo (Daniel): the two ally styles do nothing (no team-mate); the rest act
on the cursor's world as usual.  FX Studio previews the ally styles on a
stand-in team-mate behind the fighter.

Mechanics run from swordfx.on_tick (step) with the fighter's host (enemy
shots, intercepts at the source through host.on_intercept, the world);
direct-hit reduction from ai.apply_hp_damage (on_hit).  Drawing is a pure
function of the instance and its recorded events (impacts, chains, heal
pulses), so the Studio port (tools/fx/studio/defendfx.js) draws the same
pixels.  Keep the two in step.
"""

import math

from . import fxkit as F
from . import swordfx as L

STYLES = ("aegis_wall", "mirror_kata", "chain_bastion", "repulse_nova", "sanctuary_tether", "lotus_mend")
ALLY_STYLES = ("sanctuary_tether", "lotus_mend")
RESULTS = ("destroy", "deflect", "reflect")
PICKS = ("threatened", "lowest_hp", "nearest")
HOT = L.HOT
D = L.D
TWO_PI = math.pi * 2.0
FADE = 14            # ticks a defence fades out after its life
SHATTER = 30         # ticks the shards of a broken wall / dome fly
TAIL = 40            # total_ticks headroom past the hit window
IMPACT_LIFE = 22
LASH, CHAIN_HOLD, RETRACT = 4, 3, 8
FOE_COOLDOWN = 30    # ticks before a chain lashes the same enemy again
HEAL_EVERY = 12      # ticks between heal rings
NOVA_AFTER = 30      # nova dust / cracks after the burst
PREVIEW_ALLY = (-70.0, 0.0)   # Studio stand-in team-mate (local px, behind the fighter)

# Aegis wall cells: pointy-top hexagons on the wall's (u, v) surface.
HEX_HU, HEX_HV = 0.358, 0.1033
CELLS = []
for _j in range(-6, 7):
    for _u in ((-0.62, 0.0, 0.62) if _j % 2 == 0 else (-0.31, 0.31)):
        CELLS.append((_u, _j * 0.155))


# ---------------------------------------------------------------- params / timeline
def _num(P, k, d):
    v = P.get(k)
    try:
        return float(d) if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return float(d)


def _style(P):
    return L._style(P)


def _rise(P):
    return L._swing(P)


def _hold(P):
    return max(0, F.trunc(_num(P, "hold_ticks", 60)))


def _result(P):
    v = P.get("df_result")
    return v if v in RESULTS else "destroy"


def _pick_mode(P):
    v = P.get("df_pick")
    return v if v in PICKS else "lowest_hp"


def active_ticks(P):
    """Hit window = how long the defence stands (rise + hold); the nova's
    = charge + expansion + 2."""
    if _style(P) == "repulse_nova":
        return _rise(P) + max(1, _hold(P)) + 2
    return _rise(P) + _hold(P)


def total_ticks(P):
    if _style(P) == "repulse_nova":
        return active_ticks(P) + NOVA_AFTER
    return active_ticks(P) + FADE + SHATTER + TAIL


# ---------------------------------------------------------------- state
def _new_state():
    return {"end": None, "broke": False, "imp": [], "dmg": 0.0, "chains": [], "seen": set(), "foes": {},
            "ally": None, "ax": 0.0, "ay": 0.0, "sx": 0.0, "sy": 0.0, "aim": (1.0, 0.0), "sc": None,
            "healed": 0.0, "shook": False, "skip": False}


def on_spawn(inst, host):
    """After swordfx.on_spawn: the defence's own state; the ally styles pick
    their team-mate (none = Solo / nobody standing: the effect is skipped)."""
    P = inst.fx["params"]
    st = _style(P)
    df = _new_state()
    inst.df = df
    df["aim"] = tuple(inst.tq_f)
    df["sx"], df["sy"] = inst.x, inst.y
    fig = getattr(host, "fig", None) if host is not None else None
    sw, sh = getattr(fig, "screen_w", 0), getattr(fig, "screen_h", 0)
    if fig is not None and sw and sh:
        from . import combat as _combat
        df["sc"] = (_combat.position_scale(fig.x, fig.y, sw, sh), sw, sh)
    if st in ALLY_STYLES:
        world = getattr(host, "world", None)
        ally = _pick_ally(fig, world, _pick_mode(P)) if fig is not None else None
        if ally is None:
            df["skip"] = True
            inst.life = 0
            inst.dead = True
            return
        df["ally"] = ally
        df["ax"], df["ay"] = ally.x, ally.y
        inst.x, inst.y = ally.x, ally.y


def _alive(m):
    return m is not None and getattr(m.transform, "init", False) and m.personality.hp > 0 \
        and getattr(m, "bench_since", None) is None


def _pick_ally(fig, world, mode):
    """The team-mate an ally style works on (Battle only)."""
    if world is None or not getattr(world, "battle_mode", False):
        return None
    from . import guard
    mates = [m for m in guard._mates(world, fig) if _alive(m)]
    if not mates:
        return None
    if mode == "threatened":
        gs = getattr(fig, "guard", None)
        a = getattr(gs, "ally", None) if gs is not None else None
        if a in mates:
            return a
        mode = "lowest_hp"
    if mode == "nearest":
        return min(mates, key=lambda m: math.hypot(m.x - fig.x, m.y - fig.y))
    return min(mates, key=lambda m: m.personality.hp / max(1.0, float(m.personality.max_hp)))


def size(inst, ps, x=None, y=None):
    """Size factor at (x, y) (default: the instance's spot): what it was
    fired at times how much bigger / smaller that spot is than where the
    caster stood (kamehameha style)."""
    base = inst.ps or ps or 1.0
    df = getattr(inst, "df", None)
    det = df.get("sc") if df else None
    if not det or det[0] <= 0:
        return base
    from . import combat as _combat
    s = _combat.position_scale(inst.x if x is None else x, inst.y if y is None else y, det[1], det[2])
    return base * s / det[0]


def _end(inst, broke=False):
    df = inst.df
    if df["end"] is None:
        df["end"] = inst.age
        df["broke"] = broke
    inst.life = min(inst.life, inst.age)


def _shot_key(s):
    ref = s.ref
    i = getattr(ref, "i", None)
    inner = getattr(ref, "inst", None)
    if inner is not None and i is not None:
        return (id(inner), i)
    return id(ref)


def _shot_dmg(s):
    try:
        from . import guard
        return float(guard._shot_damage(s) or 0)
    except Exception:
        return 1.0


def _takes(s, mode):
    return not (s.dead or F._shot_gone(s)) and F.orb_takes(s, mode)


def _catch(inst, host, s, result, out_v=None):
    """Take enemy shot s at its source: destroy / deflect (out_v) / reflect."""
    s.dead = True
    cb = getattr(host, "on_intercept", None)
    if cb is None:
        return
    if result == "destroy" or out_v is None:
        cb(inst, s, "block", None, False)
    else:
        cb(inst, s, "deflect", out_v, bool(inst.fx["params"].get("df_hurts", True)))


def _area(host):
    w = getattr(host, "world", None)
    return (getattr(w, "enemy_area", None) or []) if w is not None else []


def _cancel_area(inst, s):
    s.dead = True
    s.ref.age = max(s.ref.age, s.ref.life)
    s.ref.dead = True


def _hits_durability(inst, dmg):
    """A blocked hit wears the wall / dome down; past df_hp it shatters."""
    P = inst.fx["params"]
    df = inst.df
    df["dmg"] += max(0.0, dmg)
    hp = _num(P, "df_hp", 0)
    if hp > 0 and df["dmg"] >= hp and df["end"] is None:
        _end(inst, broke=True)


# ---------------------------------------------------------------- per-tick mechanics
def step(inst, host):
    """swordfx.on_tick: the defence's work this tick (before age += 1)."""
    df = getattr(inst, "df", None)
    if df is None:
        return
    P = inst.fx["params"]
    st = _style(P)
    t = inst.age
    if df["end"] is None and t >= inst.life:
        df["end"] = inst.life
    if df["end"] is not None and t > df["end"] + FADE + SHATTER:
        inst.dead = True
        return
    if st in ALLY_STYLES:
        _ally_track(inst, host)
    elif df["end"] is None:
        df["sx"], df["sy"] = inst.x, inst.y
    if df["end"] is not None:
        if st == "chain_bastion":
            _chain_step(inst, host, live=False)
        return
    if st == "aegis_wall":
        _aegis_step(inst, host)
    elif st == "mirror_kata":
        _mirror_step(inst, host)
    elif st == "chain_bastion":
        _chain_step(inst, host, live=True)
    elif st == "repulse_nova":
        _nova_step(inst, host)
    elif st == "sanctuary_tether":
        _sanct_step(inst, host)
    elif st == "lotus_mend":
        _lotus_step(inst, host)


def _ally_track(inst, host):
    """Ally styles: the instance stands on the team-mate (it is drawn and
    sized there); the defender's spot is kept for the tether / petals."""
    df = inst.df
    if df["end"] is None:
        df["sx"], df["sy"] = inst.x, inst.y
        a = df["ally"]
        if not _alive(a):
            _end(inst)
        else:
            df["ax"], df["ay"] = a.x, a.y
    inst.x, inst.y = df["ax"], df["ay"]


# -- aegis wall
def _aim_ease(inst, host):
    df = inst.df
    tx, ty = host.target[0] - inst.x, host.target[1] - inst.y
    n = math.hypot(tx, ty)
    if n < 1e-6:
        return
    ax, ay = df["aim"]
    ax, ay = ax + (tx / n - ax) * 0.35, ay + (ty / n - ay) * 0.35
    m = math.hypot(ax, ay) or 1.0
    df["aim"] = (ax / m, ay / m)


class WallGeo:
    """The aegis wall in local space (+x = toward the threat): a lens of
    half-height H standing `d0` px out, bulging forward."""

    def __init__(self, inst, S):
        P = inst.fx["params"]
        self.H = max(4.0, _num(P, "radius", 26)) * S
        self.d0 = _num(P, "length", 14) * S
        self.B = 0.32 * self.H
        self.Wd = 0.30 * self.H
        ax, ay = inst.df["aim"]
        self.fr = L.Frame(inst.x, inst.y, (ax, ay), 1)

    def local(self, u, v):
        c = math.sqrt(max(0.0, 1.0 - v * v))
        return (self.d0 + self.B * (1.0 - v * v) + u * self.Wd * c, v * self.H)

    def at(self, u, v):
        lx, ly = self.local(u, v)
        return self.fr.w(lx, ly)

    def uv(self, x, y):
        """(u, v) on the wall nearest world point (x, y)."""
        fr = self.fr
        dx, dy = x - fr.ox, y - fr.oy
        lx, ly = dx * fr.fx + dy * fr.fy, dx * fr.vx + dy * fr.vy
        v = max(-0.95, min(0.95, ly / self.H))
        c = math.sqrt(max(0.0, 1.0 - v * v))
        u = (lx - self.d0 - self.B * (1.0 - v * v)) / max(1e-6, self.Wd * c)
        return max(-1.0, min(1.0, u)), v

    def spine(self, n=10):
        return [self.at(0.0, -0.98 + 1.96 * i / n) for i in range(n + 1)]


def _aegis_step(inst, host):
    df = inst.df
    P = inst.fx["params"]
    _aim_ease(inst, host)
    if inst.age < max(1, _rise(P) // 2):
        return   # cells still forming
    ps = getattr(host, "pscale", 1.0) or 1.0
    S = size(inst, ps)
    g = WallGeo(inst, S)
    sp = g.spine(10)
    tol = 0.22 * g.H
    for s in getattr(host, "shots", None) or ():
        if not _takes(s, "block"):
            continue
        path = (s.x, s.y, s.x + s.vx, s.y + s.vy)
        if s.body[0] != s.body[2] or s.body[1] != s.body[3]:
            path = s.body[0:4]
        hw = s.body[4] if len(s.body) > 4 else 0.0
        hit = None
        for i in range(1, len(sp)):
            if F.seg_seg_dist((sp[i - 1][0], sp[i - 1][1], sp[i][0], sp[i][1]), path) - hw <= tol:
                hit = i
                break
        if hit is None:
            continue
        dmg = _shot_dmg(s)
        _catch(inst, host, s, "destroy")
        u, v = g.uv(s.x, s.y)
        df["imp"].append((inst.age, u, v, 0))
        _hits_durability(inst, dmg)
        if df["end"] is not None:
            return
    if P.get("df_area", True):
        reach = g.d0 + g.B + 1.1 * g.H
        for s in _area(host):
            if s.dead or F._shot_gone(s):
                continue
            dx, dy = s.x - inst.x, s.y - inst.y
            fwd = dx * g.fr.fx + dy * g.fr.fy
            if math.hypot(dx, dy) > reach or fwd < -0.2 * g.H:
                continue
            dmg = _shot_dmg(s)
            _cancel_area(inst, s)
            u, v = g.uv(s.x, s.y)
            df["imp"].append((inst.age, u, v, 0))
            _hits_durability(inst, dmg)
            if df["end"] is not None:
                return


# -- mirror kata
def _ring(inst, S, t):
    """(cx, cy, R, ry, tilt radians) of the whirling ring at tick t."""
    P = inst.fx["params"]
    k = L.ease_out3(t / float(_rise(P)))
    R = max(4.0, _num(P, "radius", 28)) * S * (0.4 + 0.6 * k)
    ph = L.rng_for(inst.seed, 7, 1)() * TWO_PI
    tilt = (-14.0 + 8.0 * math.sin(t * 0.05 + ph)) * D * inst.tq_m
    return inst.x, inst.y, R, R * 0.58, tilt


def _ring_metric(x, y, cx, cy, R, ry, tilt):
    dx, dy = x - cx, y - cy
    ca, sa = math.cos(tilt), math.sin(tilt)
    a, b = (dx * ca + dy * sa) / R, (-dx * sa + dy * ca) / ry
    return math.sqrt(a * a + b * b)


def _blade_theta(inst, i, n, t):
    """Angle of blade i at tick t: a base spin plus two surges, uneven gaps."""
    P = inst.fx["params"]
    r = L.rng_for(inst.seed, i, 31)
    gap = (i + r.uniform(-0.22, 0.22)) * TWO_PI / max(1, n)
    p1, p2 = r() * TWO_PI, r() * TWO_PI
    base = _num(P, "spin_deg", 19) * D
    th = gap + base * t + 0.9 * math.sin(t * 0.11 + p1) + 0.5 * math.sin(t * 0.27 + p2)
    return th * inst.tq_m


def _mirror_step(inst, host):
    df = inst.df
    P = inst.fx["params"]
    ps = getattr(host, "pscale", 1.0) or 1.0
    S = size(inst, ps)
    cx, cy, R, ry, tilt = _ring(inst, S, inst.age)
    res = _result(P)
    mode = "block" if res == "destroy" else "deflect"
    for s in getattr(host, "shots", None) or ():
        if not _takes(s, mode):
            continue
        m0 = _ring_metric(s.x, s.y, cx, cy, R, ry, tilt)
        m1 = _ring_metric(s.x + s.vx, s.y + s.vy, cx, cy, R, ry, tilt)
        if min(m0, m1) > 1.12:
            continue
        spd = max(6.0, math.hypot(s.vx, s.vy))
        nx, ny = s.x - cx, s.y - cy
        nl = math.hypot(nx, ny) or 1.0
        nx, ny = nx / nl, ny / nl
        r = L.rng_for(inst.seed, len(df["imp"]), 47)
        if res == "reflect":
            tx, ty = host.target[0] - s.x, host.target[1] - s.y
            tl = math.hypot(tx, ty) or 1.0
            vel = [tx / tl * spd, ty / tl * spd]
            kind = 2
        elif res == "deflect":
            dot = s.vx * nx + s.vy * ny
            vx, vy = s.vx - 2.0 * dot * nx, s.vy - 2.0 * dot * ny
            if vx * nx + vy * ny < 0:
                vx, vy = -s.vx, -s.vy
            vx, vy = F.rot([vx, vy], r.uniform(-18, 18))
            vl = math.hypot(vx, vy) or 1.0
            vel = [vx / vl * spd, vy / vl * spd]
            kind = 1
        else:
            vel = [nx * spd, ny * spd]
            kind = 3
        _catch(inst, host, s, res, vel)
        vl = math.hypot(vel[0], vel[1]) or 1.0
        df["imp"].append((inst.age, s.x - cx, s.y - cy, vel[0] / vl, vel[1] / vl, kind))
    if P.get("df_area", False):
        for s in _area(host):
            if s.dead or F._shot_gone(s):
                continue
            if _ring_metric(s.x, s.y, cx, cy, R, ry, tilt) > 1.12:
                continue
            _cancel_area(inst, s)
            nx, ny = s.x - cx, s.y - cy
            nl = math.hypot(nx, ny) or 1.0
            df["imp"].append((inst.age, nx, ny, nx / nl, ny / nl, 3))


# -- chain bastion
def _sigil(inst, S):
    return inst.x - inst.facing * 10.0 * S, inst.y - 9.0 * S


def _chain_free(df, t, n):
    busy = sum(1 for c in df["chains"] if t - c["t0"] < LASH + CHAIN_HOLD + RETRACT)
    return busy < n


def _chain_step(inst, host, live):
    df = inst.df
    P = inst.fx["params"]
    t = inst.age
    shots = getattr(host, "shots", None) or ()
    by_key = {}
    for s in shots:
        by_key[_shot_key(s)] = s
    # 1) lashing chains follow their target; a shot is caught as the tip lands
    for c in df["chains"]:
        k = t - c["t0"]
        if c["kind"] == "shot" and not c["done"]:
            s = by_key.get(c["key"])
            if s is not None and not s.dead and not F._shot_gone(s):
                c["tx"], c["ty"] = s.x, s.y
                if k >= LASH and live:
                    res = _result(P)
                    vel = None
                    if res != "destroy":
                        spd = max(6.0, math.hypot(s.vx, s.vy))
                        if res == "reflect":
                            ox, oy = host.target[0] - s.x, host.target[1] - s.y
                        else:
                            ox, oy = s.x - inst.x, s.y - inst.y
                        ol = math.hypot(ox, oy) or 1.0
                        vel = [ox / ol * spd, oy / ol * spd]
                    _catch(inst, host, s, res, vel)
                    c["done"] = True
                    df["imp"].append((t, s.x, s.y, 0.0, 0.0, 0))
            elif k < LASH:
                c["done"] = True    # gone before the chain got there: it whips back
        elif c["kind"] == "foe" and k <= LASH + CHAIN_HOLD:
            # hurt keys are snapshot positions (they move): follow the slot
            hurts = getattr(host, "hurts", None) or ()
            if c["fi"] is not None and c["fi"] < len(hurts):
                c["tx"], c["ty"] = hurts[c["fi"]][0], hurts[c["fi"]][1]
    if not live:
        return
    # 2) free chains lash at new shots / enemies in reach
    ps = getattr(host, "pscale", 1.0) or 1.0
    S = size(inst, ps)
    reach = _num(P, "length", 180) * S
    n = max(1, F.trunc(_num(P, "moons", 3)))
    if t < _rise(P):
        return
    res = _result(P)
    mode = "block" if res == "destroy" else "deflect"
    cand = []
    for s in shots:
        if not _takes(s, mode):
            continue
        key = _shot_key(s)
        if key in df["seen"]:
            continue
        d = math.hypot(s.x - inst.x, s.y - inst.y)
        if d <= reach:
            cand.append((d, 0, key, s.x, s.y, None))
    if P.get("df_enemies", True):
        for i, (hx, hy, _hr, key) in enumerate(getattr(host, "hurts", None) or ()):
            if t - df["foes"].get(i, -10 ** 9) < FOE_COOLDOWN:
                continue
            d = math.hypot(hx - inst.x, hy - inst.y)
            if d <= reach:
                cand.append((d, 1, key, hx, hy, i))
    cand.sort(key=lambda q: (q[0], q[1]))
    for (d, kind, key, x, y, fi) in cand:
        if not _chain_free(df, t, n):
            break
        side = 1.0 if L.rng_for(inst.seed, len(df["chains"]), 53)() < 0.5 else -1.0
        df["chains"].append({"t0": t, "kind": "foe" if kind else "shot", "key": key, "fi": fi, "tx": x, "ty": y,
                             "done": False, "side": side, "n": len(df["chains"])})
        if kind:
            df["foes"][fi] = t
        else:
            df["seen"].add(key)


def chain_curve(inst, S, c, t):
    """(points, tip index) of a lashing chain c at tick t; None once back."""
    sx, sy = _sigil(inst, S)
    k = t - c["t0"]
    if k < 0 or k >= LASH + CHAIN_HOLD + RETRACT:
        return None
    if k < LASH:
        e = L.ease_out3((k + 1) / float(LASH))
    elif k < LASH + CHAIN_HOLD:
        e = 1.0
    else:
        e = 1.0 - L.ease_in3((k - LASH - CHAIN_HOLD + 1) / float(RETRACT))
    tx, ty = c["tx"], c["ty"]
    dx, dy = tx - sx, ty - sy
    dl = math.hypot(dx, dy) or 1.0
    px, py = -dy / dl, dx / dl
    bend = 0.35 * dl * c["side"]
    mx, my = sx + dx * 0.5 + px * bend, sy + dy * 0.5 + py * bend
    whip = 0.0 if k < LASH + CHAIN_HOLD else (k - LASH - CHAIN_HOLD) / float(RETRACT)
    pts = []
    N = 18
    for j in range(N + 1):
        u = e * j / N
        a, b = (1 - u) * (1 - u), 2 * u * (1 - u)
        x = a * sx + b * mx + u * u * tx
        y = a * sy + b * my + u * u * ty
        w = math.sin(u * 9.0 - t * 0.9 + c["n"]) * (2.0 + 9.0 * whip) * S * math.sin(math.pi * j / N)
        pts.append((x + px * w, y + py * w))
    return pts


def _idle_chain(inst, S, i, n, t, k_out):
    """Coiled chain i swaying behind the fighter (k_out 0..1 grows it)."""
    sx, sy = _sigil(inst, S)
    r = L.rng_for(inst.seed, i, 61)
    base = (-100.0 - 130.0 * i / max(1, n - 1) + r.uniform(-14, 14)) if n > 1 else -125.0
    a0 = base * D
    ux, uy = math.cos(a0) * -inst.facing, math.sin(a0)
    Ln = (20.0 + r() * 16.0) * S * k_out
    f, ph = 0.10 + r() * 0.08, r() * TWO_PI
    pts = []
    for j in range(13):
        s = j / 12.0
        sw = 0.55 * math.sin(s * 4.5 - t * f * 1.6 + ph) * s
        ca, sa = math.cos(sw), math.sin(sw)
        vx, vy = ux * ca - uy * sa, ux * sa + uy * ca
        pts.append((sx + vx * s * Ln, sy + vy * s * Ln))
    return pts


# -- repulse nova
def nova_radius(inst, S, t):
    P = inst.fx["params"]
    C = _rise(P)
    E = max(1, _hold(P))
    if t < C:
        return 0.0
    return max(4.0, _num(P, "radius", 120)) * S * L.ease_out3((t - C + 1) / float(E))


def _nova_step(inst, host):
    df = inst.df
    P = inst.fx["params"]
    C = _rise(P)
    t = inst.age
    if t < C:
        return
    if not df["shook"]:
        df["shook"] = True
        fn = getattr(host, "shake", None)
        if fn is not None:
            fn(6.0, 12)
    ps = getattr(host, "pscale", 1.0) or 1.0
    S = size(inst, ps)
    r = nova_radius(inst, S, t)
    for s in getattr(host, "shots", None) or ():
        if not _takes(s, "block"):
            continue
        if math.hypot(s.x - inst.x, s.y - inst.y) <= r:
            _catch(inst, host, s, "destroy")
            df["imp"].append((t, s.x, s.y, 0.0, 0.0, 3))
    if P.get("df_area", True):
        for s in _area(host):
            if s.dead or F._shot_gone(s):
                continue
            if math.hypot(s.x - inst.x, s.y - inst.y) <= r:
                _cancel_area(inst, s)
                df["imp"].append((t, s.x, s.y, 0.0, 0.0, 3))


# -- sanctuary tether
def dome(inst, S):
    """(cx, ground y, rx, height) of the sanctuary dome round the ally."""
    P = inst.fx["params"]
    R = max(4.0, _num(P, "radius", 24)) * S
    gp = _num(P, "ground_px", 14) * S
    return inst.x, inst.y + gp, R, max(R * 1.3, gp * 2.6)


def _sanct_step(inst, host):
    df = inst.df
    P = inst.fx["params"]
    if inst.age < max(1, _rise(P) // 2):
        return
    ps = getattr(host, "pscale", 1.0) or 1.0
    S = size(inst, ps)
    cx, gy, R, Hd = dome(inst, S)
    cy = gy - Hd * 0.5
    for s in getattr(host, "shots", None) or ():
        if not _takes(s, "block"):
            continue
        if _dome_metric(s.x, s.y, cx, cy, R, Hd) > 1.0 and _dome_metric(s.x + s.vx, s.y + s.vy, cx, cy, R, Hd) > 1.0:
            continue
        dmg = _shot_dmg(s)
        _catch(inst, host, s, "destroy")
        df["imp"].append((inst.age, s.x - cx, s.y - gy, 0.0, 0.0, 0))
        _hits_durability(inst, dmg)
        if df["end"] is not None:
            return
    if P.get("df_area", True):
        for s in _area(host):
            if s.dead or F._shot_gone(s):
                continue
            if _dome_metric(s.x, s.y, cx, cy, R, Hd) > 1.0:
                continue
            dmg = _shot_dmg(s)
            _cancel_area(inst, s)
            df["imp"].append((inst.age, s.x - cx, s.y - gy, 0.0, 0.0, 0))
            _hits_durability(inst, dmg)
            if df["end"] is not None:
                return


def _dome_metric(x, y, cx, cy, R, Hd):
    a, b = (x - cx) / max(1e-6, R * 1.1), (y - cy) / max(1e-6, Hd * 0.55)
    return math.sqrt(a * a + b * b)


# -- lotus mend
def _lotus_step(inst, host):
    df = inst.df
    P = inst.fx["params"]
    t = inst.age
    R0 = _rise(P)
    H = max(1, _hold(P))
    if t < R0:
        return
    a = df["ally"]
    if a is None or not _alive(a):
        return
    per = max(0.0, _num(P, "df_heal", 30)) / float(H)
    if per > 0:
        p = a.personality
        before = p.hp
        p.hp = min(float(p.max_hp), p.hp + per)
        df["healed"] += p.hp - before


# ---------------------------------------------------------------- direct hits (ai.apply_hp_damage)
def _players(fig):
    drv = getattr(fig, "fx", None)
    if drv is None:
        return []
    return [drv.player, drv.clane[0]] + [ln[0] for ln in drv.rlanes] + drv.stack_players()


def _live(fig, styles):
    for pl in _players(fig):
        for inst in pl.insts:
            if inst.dead or inst.fx.get("prim") != "technique":
                continue
            df = getattr(inst, "df", None)
            if df is None or df["end"] is not None or inst.age >= inst.life:
                continue
            if _style(inst.fx["params"]) in styles:
                yield inst


def on_hit(fig, world, amount, kind="melee"):
    """A blockable hit about to land on fig: its own aegis wall facing the
    attacker, or a team-mate's sanctuary dome round it, takes df_reduce_pct
    of it (the strongest one).  Returns the damage that still lands."""
    if amount <= 0 or world is None:
        return amount
    best, bk = None, 0.0
    att = None
    try:
        from . import guard
        att = guard._find_fig(world, getattr(fig, "last_hit_by", None))
        mates = guard._mates(world, fig)
    except Exception:
        mates = []
    for inst in _live(fig, ("aegis_wall",)):
        if att is not None:
            ax, ay = inst.df["aim"]
            if (att.x - fig.x) * ax + (att.y - fig.y) * ay < 0:
                continue    # struck from behind the wall
        k = max(0.0, min(100.0, _num(inst.fx["params"], "df_reduce_pct", 70)))
        if k > bk:
            best, bk = inst, k
    for m in mates:
        for inst in _live(m, ("sanctuary_tether",)):
            if inst.df["ally"] is not fig:
                continue
            k = max(0.0, min(100.0, _num(inst.fx["params"], "df_reduce_pct", 60)))
            if k > bk:
                best, bk = inst, k
    if best is None or bk <= 0:
        return amount
    cut = amount * bk / 100.0
    df = best.df
    if _style(best.fx["params"]) == "aegis_wall":
        S = size(best, best.ps or 1.0)
        g = WallGeo(best, S)
        px, py = (att.x, att.y) if att is not None else (fig.x + g.fr.fx * g.d0, fig.y + g.fr.fy * g.d0)
        u, v = g.uv(px, py)
        df["imp"].append((best.age, u, v, 0))
    else:
        S = size(best, best.ps or 1.0)
        cx, gy, R, Hd = dome(best, S)
        sx, sy = (att.x, att.y) if att is not None else (cx + R, gy - Hd * 0.5)
        dx, dy = sx - cx, sy - (gy - Hd * 0.5)
        dl = math.hypot(dx, dy) or 1.0
        df["imp"].append((best.age, dx / dl * R, dy / dl * Hd * 0.5 - Hd * 0.5, 0.0, 0.0, 0))
    _hits_durability(best, cut)
    return amount - cut


# ---------------------------------------------------------------- hit / body / knockback
def hit(inst, tx, ty, hr, ps):
    if inst.age >= inst.life or getattr(inst, "df", None) is None:
        return False
    P = inst.fx["params"]
    st = _style(P)
    S = size(inst, ps)
    t = inst.age
    if st == "repulse_nova":
        C = _rise(P)
        if t < C:
            return False
        r0 = nova_radius(inst, S, t - 1) if t > C else 0.0
        r1 = nova_radius(inst, S, t)
        d = math.hypot(tx - inst.x, ty - inst.y)
        return r0 - hr - 10.0 * S <= d <= r1 + hr
    if st == "chain_bastion":
        for c in inst.df["chains"]:
            k = t - c["t0"]
            if c["kind"] != "foe" or k < LASH - 1 or k > LASH + CHAIN_HOLD:
                continue
            pts = chain_curve(inst, S, c, t)
            if pts and math.hypot(pts[-1][0] - tx, pts[-1][1] - ty) <= hr + 6.0 * S:
                return True
        return False
    if st == "aegis_wall":
        g = WallGeo(inst, S)
        sp = g.spine(10)
        for i in range(1, len(sp)):
            if F.seg_dist(tx, ty, sp[i - 1][0], sp[i - 1][1], sp[i][0], sp[i][1]) <= hr + 0.2 * g.H:
                return True
        return False
    if st == "mirror_kata":
        cx, cy, R, ry, tilt = _ring(inst, S, t)
        return abs(_ring_metric(tx, ty, cx, cy, R, ry, tilt) - 1.0) * R <= hr + 4.0 * S
    return False


def body(inst, ps):
    return None


def hit_dir(inst, x=None, y=None):
    """Knockback: the nova pushes straight out from its centre; chains pull
    the enemy toward the defender (df_pull) or shove it away."""
    st = _style(inst.fx["params"])
    if x is None or y is None:
        return inst.dir
    if st == "repulse_nova" or st == "chain_bastion":
        dx, dy = x - inst.x, y - inst.y
        d = math.hypot(dx, dy)
        if d < 1e-6:
            return inst.dir
        if st == "chain_bastion" and inst.fx["params"].get("df_pull", True):
            return [-dx / d, -dy / d]
        return [dx / d, dy / d]
    return inst.dir


# ---------------------------------------------------------------- drawing
def _cols(inst, host):
    """(c1, c2, bright): the colour pair (palette = its vivid colour twice)."""
    if inst.fx["color"]["mode"] == "palette":
        c = L.vivid(host.lut)
        return c, c, L.mix(c, HOT, 0.5)
    c1, c2 = F.color_pair(inst.fx, host.lut)
    c1, c2 = tuple(c1), tuple(c2)
    return c1, c2, L.mix(c1, HOT, 0.5)


def _fade_k(inst):
    """1 while it stands, easing to 0 over FADE after it ends."""
    df = inst.df
    if df["end"] is None:
        return 1.0
    return max(0.0, 1.0 - (inst.age - df["end"]) / float(FADE))


def _flicker(seed, i, t):
    r = L.rng_for(seed, i, 71)
    f1, f2, p1, p2 = 0.17 + r() * 0.2, 0.41 + r() * 0.3, r() * TWO_PI, r() * TWO_PI
    return 0.5 + 0.3 * math.sin(t * f1 + p1) + 0.2 * math.sin(t * f2 + p2)


def draw(pen, inst, host, ps):
    df = getattr(inst, "df", None)
    if df is None or df["skip"]:
        return
    st = _style(inst.fx["params"])
    pen.add(True)
    if st == "aegis_wall":
        _draw_aegis(pen, inst, host, ps)
    elif st == "mirror_kata":
        _draw_mirror(pen, inst, host, ps)
    elif st == "chain_bastion":
        _draw_chain(pen, inst, host, ps)
    elif st == "repulse_nova":
        _draw_nova(pen, inst, host, ps)
    elif st == "sanctuary_tether":
        _draw_sanct(pen, inst, host, ps)
    elif st == "lotus_mend":
        _draw_lotus(pen, inst, host, ps)


def _shards(pen, inst, pts_fn, n, c, bright, S, t0, ux, uy):
    """Shards of a broken wall / dome: n triangles flung from pts_fn(i)
    along (ux, uy) with spread, spin and gravity."""
    t = inst.age - t0
    if t < 0 or t >= SHATTER:
        return
    q = t / float(SHATTER)
    for i in range(n):
        r = L.rng_for(inst.seed, i, 83)
        x0, y0 = pts_fn(i, r)
        ang = math.atan2(uy, ux) + r.uniform(-1.3, 1.3)
        sp = r.uniform(2.0, 7.0) * S
        fd = L.drag_dist(0.9, t)
        x = x0 + math.cos(ang) * sp * fd
        y = y0 + math.sin(ang) * sp * fd + 0.5 * 0.25 * S * t * t
        rot = r() * TWO_PI + t * r.uniform(-0.4, 0.4)
        sz = r.uniform(2.0, 5.0) * S * (1.0 - 0.5 * q)
        pts = [(x + math.cos(rot + k * 2.1) * sz * (1.0 if k == 0 else 0.6), y + math.sin(rot + k * 2.1) * sz * (1.0 if k == 0 else 0.6))
               for k in range(3)]
        pen.poly(pts, L.mix(bright, c, q), 230 * (1 - q))
        pen.glow(x, y, sz * 1.6, c, 90 * (1 - q))
    if t < 6:
        x0, y0 = pts_fn(-1, None)
        pen.glow(x0, y0, (18 + 26 * t / 6.0) * S, HOT, 230 * (1 - t / 6.0))


def _crack(inst, n, u0, v0, t, k_len):
    """Seeded jagged crack branches from (u0, v0) in wall space."""
    out = []
    for b in range(3):
        r = L.rng_for(inst.seed, n * 7 + b, 97)
        a = r() * TWO_PI
        L_ = (0.25 + r() * 0.3) * k_len
        pts = [(u0, v0)]
        u, v = u0, v0
        for _s in range(4):
            a += r.uniform(-0.8, 0.8)
            u += math.cos(a) * L_ / 4.0 * 1.6
            v += math.sin(a) * L_ / 4.0 * 0.6
            pts.append((max(-1.0, min(1.0, u)), max(-0.97, min(0.97, v))))
        out.append(pts)
    return out


def _draw_aegis(pen, inst, host, ps):
    df = inst.df
    P = inst.fx["params"]
    t = inst.age
    S = size(inst, ps)
    g = WallGeo(inst, S)
    c1, c2, bright = _cols(inst, host)
    Rz = _rise(P)
    fk = _fade_k(inst)
    hp = _num(P, "df_hp", 0)
    wear = min(1.0, df["dmg"] / hp) if hp > 0 else 0.0
    if df["broke"]:
        e0 = df["end"]
        fx_, fy_ = g.fr.fx, g.fr.fy

        def at(i, r):
            if i < 0:
                return g.at(0.0, 0.0)
            u, v = CELLS[i % len(CELLS)]
            return g.at(u, v)
        _shards(pen, inst, at, len(CELLS), c1, bright, S, e0, fx_, fy_)
        return
    if fk <= 0:
        return
    # 0: bloom behind the wall + a spine of light
    mid = g.at(0.0, 0.0)
    rise_k = L.ease_out3(t / float(Rz))
    pen.glow(mid[0], mid[1], g.H * 1.1, c1, 70 * fk * rise_k, 0.4)
    # 1: cells pop in from the centre out (seeded order), then shimmer
    for i, (u, v) in enumerate(CELLS):
        r = L.rng_for(inst.seed, i, 101)
        delay = (abs(v) * 0.75 + abs(u) * 0.25) * Rz * 0.8 + r() * Rz * 0.4
        k = t - delay
        if k < 0:
            continue
        pop = min(1.0, k / 3.0)
        fl = _flicker(inst.seed, i, t)
        a = (0.30 + 0.35 * fl) * (1.0 - 0.45 * wear * fl) * fk * pop
        # ripples from impacts light the cells they cross
        for (b, iu, iv, _kd) in df["imp"]:
            q = t - b
            if 0 <= q < IMPACT_LIFE:
                front = q * 0.11
                dd = math.hypot((u - iu) * 0.55, v - iv)
                if abs(dd - front) < 0.14:
                    a += 0.9 * (1.0 - q / float(IMPACT_LIFE)) * fk
        flash = max(0.0, 1.0 - k / 4.0)
        pts = [g.at(u + HEX_HU * math.cos((30 + 60 * kk) * D) * 0.92, v + HEX_HV * math.sin((30 + 60 * kk) * D) * 0.92)
               for kk in range(6)]
        pen.poly(pts, L.mix(c1, c2, 0.5 + 0.5 * math.sin(v * 3.0 + t * 0.07)), 90 * min(1.6, a))
        pts.append(pts[0])
        pen.polyline(pts, L.mix(bright, HOT, flash), 230 * min(1.0, a + flash), 1.1 * S)
    # 2: rim of the lens, bright edge
    for side in (1.0, -1.0):
        rim = [g.at(side, -1.0 + 2.0 * j / 16.0) for j in range(17)]
        pen.polyline(rim, c1, 140 * fk * rise_k, 3.2 * S)
        pen.polyline(rim, HOT, 200 * fk * rise_k, 1.0 * S)
    # 3: energy crawling along the spine (uneven pulses)
    for j in range(3):
        r = L.rng_for(inst.seed, j, 113)
        sp = 0.04 + r() * 0.05
        v = -1.0 + 2.0 * L.frac(r() + t * sp)
        p = g.at(r.uniform(-0.6, 0.6), v * 0.95)
        pen.glow(p[0], p[1], 4.5 * S, bright, 200 * fk)
    # 4: impacts: cracks (stay), spark burst, flash
    for n, (b, iu, iv, _kd) in enumerate(df["imp"]):
        q = t - b
        if q < 0:
            continue
        for br in _crack(inst, n, iu, iv, t, min(1.0, q / 4.0)):
            pen.polyline([g.at(u, v) for (u, v) in br], HOT, 170 * fk * (0.45 + 0.55 * max(0.0, 1 - q / 30.0)), 1.0 * S)
        if q < IMPACT_LIFE:
            f = 1.0 - q / float(IMPACT_LIFE)
            p = g.at(iu, iv)
            pen.glow(p[0], p[1], (9 + 7 * L.ease_out3(q / 6.0)) * S, bright, 230 * f * fk)
            L._star(pen, p[0], p[1], -g.fr.vx, -g.fr.vy, 12 * S * f, 5 * S * f, HOT, 255 * f, 1.2 * S)
            for k in range(6):
                r = L.rng_for(inst.seed, n * 11 + k, 127)
                a = math.atan2(-g.fr.fy, -g.fr.fx) + r.uniform(-1.1, 1.1)
                sp = r.uniform(3.0, 7.0) * S
                fd = L.drag_dist(0.85, q)
                x, y = p[0] + math.cos(a) * sp * fd, p[1] + math.sin(a) * sp * fd + 0.1 * S * q * q
                pen.line(x, y, x - math.cos(a) * sp, y - math.sin(a) * sp, L.mix(HOT, c1, 1 - f), 255 * f, 1.4 * S)


def _draw_mirror(pen, inst, host, ps):
    df = inst.df
    P = inst.fx["params"]
    t = inst.age
    S = size(inst, ps)
    c1, c2, bright = _cols(inst, host)
    fk = _fade_k(inst)
    if fk <= 0:
        return
    cx, cy, R, ry, tilt = _ring(inst, S, t)
    ca, sa = math.cos(tilt), math.sin(tilt)

    def ring_pt(th, rr=1.0):
        x, y = math.cos(th) * R * rr, math.sin(th) * ry * rr
        return cx + x * ca - y * sa, cy + x * sa + y * ca

    # 0: faint ring trace + start flash
    pen.ring(cx, cy, R, ry, tilt, c1, 70 * fk, 1.2 * S)
    if t < 6:
        pen.glow(cx, cy, R * (0.6 + 0.08 * t), HOT, 200 * (1 - t / 6.0))
    n = max(1, F.trunc(_num(P, "moons", 3)))
    span = 1.15
    W = max(1.0, _num(P, "thickness", 7)) * S
    for i in range(n):
        th = _blade_theta(inst, i, n, t)
        th_prev = _blade_theta(inst, i, n, t - 1)
        dirn = 1.0 if th >= th_prev else -1.0
        depth = math.sin(th)
        da = 0.45 + 0.55 * (0.5 + 0.5 * depth)
        # afterimages: the last two ticks' blades, fainter
        for g_ in (2, 1, 0):
            thg = _blade_theta(inst, i, n, t - g_)
            ag = da * fk * (1.0 if g_ == 0 else 0.28 / g_)
            pts_o, pts_i = [], []
            for j in range(13):
                s = j / 12.0
                a = thg - dirn * span * (1.0 - s)
                # a crescent smear: thin tail, fat just behind the head, a point at the head
                w = W * (math.sin(math.pi * (s ** 0.7)) ** 0.8) * (0.3 + 0.7 * s)
                pts_o.append(ring_pt(a, 1.0 + w / (2 * R)))
                pts_i.append(ring_pt(a, 1.0 - w / (2 * R)))
            if g_ == 0:
                spine = [ring_pt(thg - dirn * span * (1.0 - j / 12.0), 1.0) for j in range(13)]
                pen.polyline(spine, c1, 70 * ag, W * 1.7)
            pen.poly(pts_o + pts_i[::-1], L.mix(c2, c1, 0.6), 190 * ag)
            if g_ == 0:
                pen.polyline(pts_o, HOT, 235 * ag, 1.3 * S)
        hx, hy = ring_pt(th)
        pen.glow(hx, hy, 6 * S, bright, 210 * da * fk)
        # motes shed off the head
        for k in range(3):
            r = L.rng_for(inst.seed, i * 5 + k, 139)
            life = 8 + int(r() * 8)
            b = t - ((t + int(r() * life)) % life)
            q = (t - b) / float(life)
            thb = _blade_theta(inst, i, n, b)
            bx, by = ring_pt(thb, 1.0 + 0.25 * q)
            pen.glow(bx, by, 2.4 * S * (1 - q) + 0.4, bright, 220 * (1 - q) * fk)
    # catches: a mirror rune (hexagram) + a streak along the new way
    for (b, ox, oy, ux, uy, kd) in df["imp"]:
        q = t - b
        if q < 0 or q >= IMPACT_LIFE:
            continue
        f = 1.0 - q / float(IMPACT_LIFE)
        x, y = cx + ox, cy + oy
        rr = (5 + 10 * L.ease_out3(q / 8.0)) * S * (1.4 if kd == 2 else 1.0)
        rot = math.atan2(uy, ux) + q * 0.08
        col = HOT if kd == 2 else bright
        for tri in (0.0, math.pi):
            pts = [(x + math.cos(rot + tri + k * TWO_PI / 3) * rr, y + math.sin(rot + tri + k * TWO_PI / 3) * rr)
                   for k in range(4)]
            pen.polyline(pts, col, 230 * f * fk, 1.3 * S)
        pen.ring(x, y, rr * 1.15, rr * 1.15, 0.0, c1, 160 * f * fk, 1.0 * S)
        pen.glow(x, y, 9 * S * f + 2, HOT, 255 * f * fk)
        Ls = (14 + 44 * L.ease_out3(q / 6.0)) * S
        pen.line(x, y, x + ux * Ls, y + uy * Ls, bright, 200 * f * fk, 2.4 * S * f + 0.3)
        pen.line(x, y, x + ux * Ls * 0.8, y + uy * Ls * 0.8, HOT, 255 * f * fk, 1.0 * S)


def _draw_links(pen, pts, c, bright, S, a, glow_tip=True):
    if len(pts) < 2:
        return
    pen.polyline(pts, c, 70 * a, 3.0 * S)
    # links every ~9 px along the curve, alternating flat / edge-on
    acc, idx = 0.0, 0
    step = 5.5 * S
    for j in range(1, len(pts)):
        x0, y0 = pts[j - 1]
        x1, y1 = pts[j]
        sl = math.hypot(x1 - x0, y1 - y0)
        if sl < 1e-6:
            continue
        ux, uy = (x1 - x0) / sl, (y1 - y0) / sl
        d = step - acc
        while d <= sl:
            x, y = x0 + ux * d, y0 + uy * d
            if idx % 2 == 0:
                pen.ring(x, y, 3.0 * S, 1.6 * S, math.atan2(uy, ux), bright, 220 * a, 1.0 * S)
            else:
                pen.line(x - ux * 2.2 * S, y - uy * 2.2 * S, x + ux * 2.2 * S, y + uy * 2.2 * S, HOT, 230 * a, 1.2 * S)
            idx += 1
            d += step
        acc = sl - (d - step)
    if glow_tip:
        x0, y0 = pts[-2]
        x1, y1 = pts[-1]
        dx, dy = x1 - x0, y1 - y0
        dl = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dl, dy / dl
        pen.diamond(x1 - ux * 3 * S, y1 - uy * 3 * S, x1 + ux * 8 * S, y1 + uy * 8 * S, 2.8 * S, bright, 240 * a)
        pen.diamond(x1 - ux * 1.5 * S, y1 - uy * 1.5 * S, x1 + ux * 6.5 * S, y1 + uy * 6.5 * S, 1.1 * S, HOT, 255 * a)
        pen.glow(x1, y1, 6 * S, c, 160 * a)


def _draw_chain(pen, inst, host, ps):
    df = inst.df
    P = inst.fx["params"]
    t = inst.age
    S = size(inst, ps)
    c1, c2, bright = _cols(inst, host)
    fk = _fade_k(inst)
    if fk <= 0:
        return
    sx, sy = _sigil(inst, S)
    Rz = _rise(P)
    k_out = L.ease_out3(t / float(Rz))
    # 0: the sigil gate behind the shoulder
    rs = 8 * S * (0.4 + 0.6 * k_out)
    pen.glow(sx, sy, rs * 2.2, c1, 110 * fk)
    pen.ring(sx, sy, rs, rs * 0.55, -0.35 * inst.facing, bright, 220 * fk, 1.6 * S)
    for k in range(8):
        a = k * TWO_PI / 8 + t * 0.06 * inst.facing
        x, y = sx + math.cos(a) * rs, sy + math.sin(a) * rs * 0.55
        pen.line(x, y, sx + math.cos(a) * rs * 1.25, sy + math.sin(a) * rs * 1.25 * 0.55, HOT, 200 * fk, 1.1 * S)
    # 1: idle chains coiled behind (the ones not lashing)
    n = max(1, F.trunc(_num(P, "moons", 3)))
    busy = sum(1 for c in df["chains"] if t - c["t0"] < LASH + CHAIN_HOLD + RETRACT)
    for i in range(max(0, n - busy)):
        _draw_links(pen, _idle_chain(inst, S, i, n, t, k_out), c2, bright, S, 0.85 * fk)
    # 2: lashing chains
    for c in df["chains"]:
        pts = chain_curve(inst, S, c, t)
        if pts is None:
            continue
        _draw_links(pen, pts, c1, bright, S, fk)
        k = t - c["t0"]
        if LASH - 1 <= k <= LASH + 1:
            x, y = pts[-1]
            pen.glow(x, y, 13 * S, HOT, 220 * fk)
    # 3: clank bursts where a shot was caught
    for n_, (b, x, y, _ux, _uy, _kd) in enumerate(df["imp"]):
        q = t - b
        if q < 0 or q >= IMPACT_LIFE:
            continue
        f = 1.0 - q / float(IMPACT_LIFE)
        pen.ring(x, y, (4 + 14 * L.ease_out3(q / 10.0)) * S, (4 + 14 * L.ease_out3(q / 10.0)) * S, 0.0, bright, 200 * f, 1.6 * S * f)
        pen.glow(x, y, 10 * S * f + 2, HOT, 255 * f)
        for k in range(7):
            r = L.rng_for(inst.seed, n_ * 13 + k, 149)
            a = r() * TWO_PI
            sp = r.uniform(2.5, 6.5) * S
            fd = L.drag_dist(0.86, q)
            x2, y2 = x + math.cos(a) * sp * fd, y + math.sin(a) * sp * fd + 0.12 * S * q * q
            pen.line(x2, y2, x2 - math.cos(a) * sp * 1.3, y2 - math.sin(a) * sp * 1.3, L.mix(HOT, c1, 1 - f), 255 * f, 1.3 * S)


def _jag_ring(inst, cx, cy, rx, ry, t, amp, salt):
    """A wobbling, never-round ring (flame-like edge)."""
    pts = []
    r = L.rng_for(inst.seed, salt, 157)
    p1, p2 = r() * TWO_PI, r() * TWO_PI
    for j in range(41):
        a = j / 40.0 * TWO_PI
        w = 1.0 + amp * (0.6 * math.sin(a * 5 + t * 0.31 + p1) + 0.4 * math.sin(a * 11 - t * 0.47 + p2))
        pts.append((cx + math.cos(a) * rx * w, cy + math.sin(a) * ry * w))
    return pts


def _draw_nova(pen, inst, host, ps):
    df = inst.df
    P = inst.fx["params"]
    t = inst.age
    S = size(inst, ps)
    c1, c2, bright = _cols(inst, host)
    C = _rise(P)
    E = max(1, _hold(P))
    Rn = max(4.0, _num(P, "radius", 120)) * S
    gy = inst.y + _num(P, "ground_px", 14) * S
    cx, cy = inst.x, inst.y
    end_t = C + E + 2 + NOVA_AFTER
    if t >= end_t:
        return
    # 0: ground glyph + cracks (charge, then held while it bursts / fades)
    kc = L.ease_out3(t / float(C)) if t < C else 1.0
    after = max(0.0, (t - C - E) / float(NOVA_AFTER))
    ga = (1.0 - after) * kc
    gr = (0.35 + 0.25 * kc) * Rn * 0.5
    pen.ring(cx, gy, gr, gr * 0.36, 0.0, c1, 200 * ga, 2.0 * S)
    pen.ring(cx, gy, gr * 0.72, gr * 0.72 * 0.36, 0.0, bright, 160 * ga, 1.2 * S)
    for k in range(12):
        a = k * TWO_PI / 12 + t * 0.05
        x0, y0 = cx + math.cos(a) * gr * 0.72, gy + math.sin(a) * gr * 0.72 * 0.36
        x1, y1 = cx + math.cos(a) * gr, gy + math.sin(a) * gr * 0.36
        pen.line(x0, y0, x1, y1, HOT, 170 * ga, 1.0 * S)
    for k in range(9):
        r = L.rng_for(inst.seed, k, 163)
        a = r() * TWO_PI
        Lc = (0.35 + 0.5 * r()) * Rn * min(1.0, kc * 0.6 + (0.4 if t >= C else 0.0))
        pts = [(cx, gy)]
        x, y = cx, gy
        for s in range(5):
            a += r.uniform(-0.5, 0.5)
            x += math.cos(a) * Lc / 5.0
            y += math.sin(a) * Lc / 5.0 * 0.36
            pts.append((x, y))
        pen.polyline(pts, L.mix(bright, c1, 0.3), 170 * ga, 1.6 * S)
    # 1: charge: motes rushing in, body glow growing
    if t < C:
        for k in range(18):
            r = L.rng_for(inst.seed, k, 167)
            b = r() * C * 0.7
            q = (t - b) / max(1.0, C - b)
            if q < 0 or q >= 1:
                continue
            a = r() * TWO_PI
            d0 = Rn * (0.5 + 0.4 * r())
            e = L.ease_in3(q)
            x, y = cx + math.cos(a) * d0 * (1 - e), cy + math.sin(a) * d0 * (1 - e) * 0.7
            x2, y2 = cx + math.cos(a) * d0 * (1 - e) * 1.18 + 0.0, cy + math.sin(a) * d0 * (1 - e) * 1.18 * 0.7
            pen.line(x, y, x2, y2, bright, 230 * q, 1.6 * S)
        pen.glow(cx, cy, (12 + 18 * kc) * S, c1, 150 * kc)
        pen.glow(cx, cy, (5 + 6 * kc) * S, HOT, 200 * kc)
        return
    # 2: burst: flash, dome shell, ground pressure ring, shock lines
    k = t - C
    if k < 5:
        pen.glow(cx, cy, (26 + 40 * k / 5.0) * S, HOT, 255 * (1 - k / 5.0))
    r1 = nova_radius(inst, S, min(t, C + E - 1))
    e = min(1.0, (t - C + 1) / float(E))
    fa = (1.0 - e * e) if t < C + E else 0.0
    if r1 > 1 and fa > 0:
        shell = _jag_ring(inst, cx, gy, r1, r1 * 0.38, t, 0.05, 1)
        pen.polyline(shell, c1, 200 * fa, 4.0 * S)
        pen.polyline(shell, HOT, 230 * fa, 1.4 * S)
        dome_pts = [(cx + math.cos(math.pi + j / 20.0 * math.pi) * r1, gy + math.sin(math.pi + j / 20.0 * math.pi) * r1 * 0.78)
                    for j in range(21)]
        pen.polyline(dome_pts, bright, 170 * fa, 2.6 * S)
        pen.glow(cx, gy - r1 * 0.3, r1 * 0.9, c1, 70 * fa, 0.55)
        for j in range(14):
            r = L.rng_for(inst.seed, j, 173)
            a = j * TWO_PI / 14 + r.uniform(-0.2, 0.2)
            ln = (10 + 18 * r()) * S
            x0, y0 = cx + math.cos(a) * r1, gy + math.sin(a) * r1 * 0.38
            pen.line(x0, y0, x0 + math.cos(a) * ln, y0 + math.sin(a) * ln * 0.38, HOT, 210 * fa, 1.4 * S)
    # 3: after: dust puffs on the final ring, inner ring fading
    if t >= C + E - 2:
        q = (t - (C + E - 2)) / float(NOVA_AFTER + 4)
        Rf = nova_radius(inst, S, C + E - 1)
        for j in range(16):
            r = L.rng_for(inst.seed, j, 179)
            a = j * TWO_PI / 16 + r.uniform(-0.15, 0.15)
            x, y = cx + math.cos(a) * Rf * (1 + 0.15 * q), gy + math.sin(a) * Rf * 0.38 * (1 + 0.15 * q)
            pen.glow(x, y - 8 * S * q, (10 + 14 * q) * S * (0.7 + 0.6 * r()), L.mix(c2, (200, 200, 200), 0.5), 120 * (1 - q))
    # 4: destroyed shots
    for (b, x, y, _ux, _uy, _kd) in df["imp"]:
        q = t - b
        if 0 <= q < 12:
            f = 1.0 - q / 12.0
            pen.glow(x, y, 12 * S * f + 2, HOT, 240 * f)


def _draw_sanct(pen, inst, host, ps):
    df = inst.df
    P = inst.fx["params"]
    t = inst.age
    S = size(inst, ps)
    c1, c2, bright = _cols(inst, host)
    cx, gy, R, Hd = dome(inst, S)
    Rz = _rise(P)
    if df["broke"]:
        def at(i, r):
            if i < 0:
                return cx, gy - Hd * 0.5
            a = math.pi + r() * math.pi
            return cx + math.cos(a) * R, gy + math.sin(a) * Hd
        _shards(pen, inst, at, 22, c1, bright, S, df["end"], 0.0, -1.0)
        return
    fk = _fade_k(inst)
    if fk <= 0:
        return
    kr = L.ease_out3(t / float(Rz))
    hp = _num(P, "df_hp", 0)
    wear = min(1.0, df["dmg"] / hp) if hp > 0 else 0.0
    # 0: tether from the defender's chest to the dome
    sx, sy = df["sx"], df["sy"] - 5 * S
    tx, ty = cx, gy - Hd * 0.62
    dx, dy = tx - sx, ty - sy
    dl = math.hypot(dx, dy) or 1.0
    px, py = -dy / dl, dx / dl
    reach = min(1.0, t / max(1.0, Rz * 0.6))
    for strand in (1.0, -1.0):
        pts = []
        for j in range(25):
            s = j / 24.0 * reach
            w = strand * 4.0 * S * math.sin(s * math.pi * 5 - t * 0.35) * math.sin(math.pi * s)
            pts.append((sx + dx * s + px * w, sy + dy * s + py * w))
        pen.polyline(pts, c1, 170 * fk, 1.8 * S)
    pen.line(sx, sy, sx + dx * reach, sy + dy * reach, HOT, 200 * fk, 1.1 * S)
    for k in range(6):
        r = L.rng_for(inst.seed, k, 191)
        s = L.frac(r() + t * (0.02 + 0.03 * r()))
        if s > reach:
            continue
        pen.glow(sx + dx * s, sy + dy * s, 4 * S, bright, 230 * fk)
    pen.glow(sx, sy, 7 * S, c1, 150 * fk)
    # 1: dome (grows up from the ground)
    hk = Hd * kr
    fl = 0.75 + 0.25 * _flicker(inst.seed, 3, t) - 0.35 * wear * _flicker(inst.seed, 5, t * 2)
    pen.glow(cx, gy - hk * 0.45, max(R, hk * 0.6), c1, 60 * fk * fl, 0.6)
    shell = [(cx + math.cos(math.pi + j / 24.0 * math.pi) * R, gy + math.sin(math.pi + j / 24.0 * math.pi) * hk)
             for j in range(25)]
    pen.polyline(shell, c1, 190 * fk * fl, 3.4 * S)
    pen.polyline(shell, HOT, 210 * fk * fl, 1.1 * S)
    for m in range(4):
        ph = m * math.pi / 4 + t * 0.03
        cm = math.cos(ph)
        mer = [(cx + cm * math.cos(math.pi + j / 16.0 * math.pi) * R, gy + math.sin(math.pi + j / 16.0 * math.pi) * hk)
               for j in range(17)]
        pen.polyline(mer, bright, 90 * fk * fl * (0.4 + 0.6 * abs(math.sin(ph))), 1.0 * S)
    for lat in (0.35, 0.7):
        yy = gy - hk * lat
        rx = R * math.sqrt(max(0.0, 1.0 - lat * lat))
        pen.ring(cx, yy, rx, rx * 0.3, 0.0, bright, 80 * fk * fl, 1.0 * S)
    # 2: base rune ring, rotating
    pen.ring(cx, gy, R * 1.05, R * 1.05 * 0.32, 0.0, c1, 200 * fk, 2.2 * S)
    for k in range(10):
        a = k * TWO_PI / 10 + t * 0.04
        x, y = cx + math.cos(a) * R * 1.05, gy + math.sin(a) * R * 1.05 * 0.32
        pen.diamond(x - 2 * S, y, x + 2 * S, y, 1.4 * S, HOT, 220 * fk)
    # 3: pillar of light as it rises
    if t < Rz + 6:
        q = t / float(Rz + 6)
        pen.poly([(cx - R * 0.5 * (1 - q), gy), (cx + R * 0.5 * (1 - q), gy), (cx + 3 * S, gy - Hd * 1.6), (cx - 3 * S, gy - Hd * 1.6)],
                 bright, 150 * (1 - q))
    # 4: hits on the dome: ripple + flash
    for (b, ox, oy, _ux, _uy, _kd) in df["imp"]:
        q = t - b
        if q < 0 or q >= IMPACT_LIFE:
            continue
        f = 1.0 - q / float(IMPACT_LIFE)
        x, y = cx + ox, gy + oy
        rr = (3 + 14 * L.ease_out3(q / 10.0)) * S
        pen.ring(x, y, rr, rr * 0.7, 0.0, bright, 220 * f * fk, 2.0 * S * f + 0.3)
        pen.glow(x, y, 12 * S * f + 2, HOT, 255 * f * fk)


def _leaf(pen, x, y, ux, uy, Lp, Wp, c, a):
    """A petal / leaf: pointed both ends, widest a third of the way."""
    px, py = -uy, ux
    pts = [(x, y), (x + ux * Lp * 0.33 + px * Wp, y + uy * Lp * 0.33 + py * Wp), (x + ux * Lp, y + uy * Lp),
           (x + ux * Lp * 0.33 - px * Wp, y + uy * Lp * 0.33 - py * Wp)]
    pen.poly(pts, c, a)


def _draw_lotus(pen, inst, host, ps):
    df = inst.df
    P = inst.fx["params"]
    t = inst.age
    S = size(inst, ps)
    c1, c2, bright = _cols(inst, host)
    fk = _fade_k(inst)
    if fk <= 0:
        return
    Rz = _rise(P)
    H = max(1, _hold(P))
    Rl = max(4.0, _num(P, "radius", 24)) * S
    gp = _num(P, "ground_px", 14) * S
    cx, gy = inst.x, inst.y + gp
    # 0: lotus sigil on the ground, blooming open then turning slowly
    for layer, (cnt, sc, off, col) in enumerate(((8, 1.0, 0.0, c1), (8, 0.62, math.pi / 8, c2))):
        for k in range(cnt):
            r = L.rng_for(inst.seed, layer * 20 + k, 197)
            op = L.ease_out3((t - r() * Rz * 0.5) / float(Rz))
            if op <= 0:
                continue
            a = off + k * TWO_PI / cnt + t * 0.01
            ux, uy = math.cos(a), math.sin(a) * 0.4
            ul = math.hypot(ux, uy) or 1.0
            Lp = Rl * sc * op * (1.0 + 0.06 * math.sin(t * 0.13 + k))
            _leaf(pen, cx, gy, ux / ul, uy / ul, Lp * ul, Lp * 0.2 * (0.55 + 0.45 * abs(math.cos(a))), col, 120 * fk * op)
    pen.ring(cx, gy, Rl * 1.08, Rl * 1.08 * 0.4, 0.0, bright, 170 * fk, 1.4 * S)
    pen.ring(cx, gy, Rl * 0.3, Rl * 0.3 * 0.4, 0.0, HOT, 200 * fk, 1.2 * S)
    pen.glow(cx, gy, Rl * 0.6, c1, 100 * fk)
    # 1: petals streaming from the defender to the ally
    sx, sy = df["sx"], df["sy"] - 4 * S
    tx, ty = cx, inst.y
    dx, dy = tx - sx, ty - sy
    dl = math.hypot(dx, dy) or 1.0
    px, py = -dy / dl, dx / dl
    live_end = Rz + H if df["end"] is None else df["end"]
    for j in range(int((Rz + H) / 2) + 1):
        r = L.rng_for(inst.seed, j, 211)
        b = j * 2 + r() * 2.5
        fl = 16.0 + r() * 10.0
        q = (t - b) / fl
        if q < 0 or q >= 1 or b > live_end:
            continue
        side = r.uniform(-1.0, 1.0) * 0.45 * dl
        u = L.ease_inout3(q)
        a_, b_ = (1 - u) * (1 - u), 2 * u * (1 - u)
        mx, my = sx + dx * 0.5 + px * side, sy + dy * 0.5 + py * side - 18 * S
        x = a_ * sx + b_ * mx + u * u * tx
        y = a_ * sy + b_ * my + u * u * ty
        spin = r() * TWO_PI + t * r.uniform(0.15, 0.35)
        col = L.mix(c2, c1, r())
        sz = 0.8 + 0.6 * r()
        _leaf(pen, x, y, math.cos(spin), math.sin(spin), 9 * S * sz, 2.6 * S * sz, col, 230 * (1 - q * q) * fk)
        pen.glow(x, y, 4.5 * S * sz, bright, 130 * (1 - q) * fk)
    # 2: healing motes rising off the sigil
    for k in range(14):
        r = L.rng_for(inst.seed, k, 223)
        per = 22 + int(r() * 14)
        q = L.frac((t + r() * per) / float(per))
        a = r() * TWO_PI
        rr = Rl * 0.8 * r()
        x = cx + math.cos(a) * rr + math.sin(t * 0.1 + k) * 4 * S
        y = gy + math.sin(a) * rr * 0.4 - q * gp * 2.6
        pen.glow(x, y, 3.0 * S * (1 - q) + 0.5, bright, 220 * math.sin(math.pi * q) * fk)
    # 3: heal rings running up the body + glints
    if t >= Rz:
        for n_ in range(int((min(t, live_end) - Rz) / HEAL_EVERY) + 1):
            b = Rz + n_ * HEAL_EVERY
            q = (t - b) / 16.0
            if q < 0 or q >= 1:
                continue
            y = gy - gp * 2.4 * L.ease_out3(q)
            rx = Rl * (0.7 - 0.25 * q)
            pen.ring(cx, y, rx, rx * 0.3, 0.0, bright, 220 * (1 - q) * fk, 2.0 * S)
            r = L.rng_for(inst.seed, n_, 229)
            gx_, gy_ = cx + r.uniform(-0.6, 0.6) * Rl, inst.y - r() * gp
            ln = 5 * S * (1 - q)
            pen.line(gx_ - ln, gy_, gx_ + ln, gy_, HOT, 255 * (1 - q) * fk, 1.6 * S)
            pen.line(gx_, gy_ - ln, gx_, gy_ + ln, HOT, 255 * (1 - q) * fk, 1.6 * S)
