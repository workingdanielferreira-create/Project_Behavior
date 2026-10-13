"""
Unique Abilities (FX Studio: the "Unique Abilities" section).

A character can carry ONE unique ability: the core mechanism it is built
around.  FX Studio saves it in <name>.fxkit.json as

    "unique_ability": {
        "type": "none" | "mirror_legion" | "berserker" | "phase_shift"
                | "ricochet" | "riposte",
        "mirror_legion": {...}, "berserker": {...}, ...   # each one's settings
    }

Only the block named by `type` is used (the others are kept so switching
back in the Studio doesn't lose them).  A hand-written pb_character JSON can
carry the same block at its top level.  Mirror of tools/fx/studio/fxkit.js
UNIQUE_DEFAULTS / normalizeUnique.

    mirror_legion  split into ghost copies (combat.CloneEffect) on a trigger
    berserker      attack + movement speed (every state) rise as HP falls
    phase_shift    a hit is nullified and the fighter teleports away
    ricochet       its bullets and moving FX bounce off walls / fighters / FX
    riposte        a hit inside the counter stance (or by chance) is
                   cancelled and answered with a counter-strike

Hooks (all shared by Solo and Battle; Solo's enemy is the cursor):
    ai.apply_hp_damage / ai.battle_hit   intercept(), after_damage(), taken_mult()
    systems.CombatSystem                 tick() once per body step
    timefx.plan                          speed_mult() / fx_speed_mult()
    systems.ProjectileSystem             proj_step(), proj_wants_figures(), proj_off_point()
    systems.CollisionSystem (victim)     proj_off_figure()
    fxkit.tick_inst / hit                inst_step(), inst_off_figure()
    app.refresh_battle / fxkit._Host     out_mult()
    combat.spawn_clone                   on_dodge()
    figure.Figure.draw                   draw()
"""

import math
import random

from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QColor, QPen, QBrush, QPainter, QRadialGradient

from . import config

TICK_MS = config.TICK_MS
TYPES = ("none", "mirror_legion", "berserker", "phase_shift", "ricochet", "riposte")

DEFAULTS = {
    "mirror_legion": dict(
        trigger="hp_below",          # hp_below | hits_taken | timer | on_dodge
        hp_thresholds="70,50,30",    # % HP; each fires once per life
        every_hits=5, every_ms=10000,
        count=2, duration_ms=4000, cooldown_ms=6000,
        formation="around",          # around | at_self | corners | mirror
        spread_px=90.0, damage=1.0, speed_pct=80.0, opacity_pct=60.0),
    "berserker": dict(
        start_lost_pct=0.0, max_lost_pct=90.0, max_bonus_pct=500.0,
        curve="linear",              # linear | exponential | steps
        steps=5, damage_bonus_pct=0.0, damage_taken_pct=0.0,
        speed_fx=True, aura=True, aura_color="#ff2a2a"),
    "phase_shift": dict(
        trigger="every_hit",         # every_hit | min_damage | hp_below | chance
        min_damage=5.0, hp_below_pct=50.0, chance_pct=50.0,
        charges=3, recharge_ms=8000,
        destinations=dict(behind_attacker=True, random=True, far_corner=False,
                          spawn=False, mirror=False, fixed=False),
        random_min_px=120.0, random_max_px=260.0, behind_px=70.0,
        fixed_x_pct=50.0, fixed_y_pct=50.0, invuln_ms=300, show_charges=True),
    "ricochet": dict(
        bounces=3, walls=True, characters=True, fx=True, fx_contact_px=18.0,
        keep_speed_pct=100.0, keep_damage_pct=100.0,
        angle="reflect",             # reflect | seek | random
        random_deg=25.0, split=0, split_deg=20.0, sparks=True),
    "riposte": dict(
        mode="stance",               # stance | chance | both
        stance_every_ms=3000, stance_ms=600, chance_pct=25.0,
        counter_mult_pct=150.0, base_damage=5.0,
        counter="strike",            # strike | blink_strike
        knockback_px=60.0, cooldown_ms=1500, invuln_ms=250, color="#ffd34a"),
}

_LIMITS = {
    "count": (1, 8), "every_hits": (1, 99), "bounces": (0, 20), "split": (0, 4),
    "charges": (0, 99), "steps": (1, 20), "max_bonus_pct": (0, 700),
}


# ------------------------------------------------------------ config
def _norm(kind, raw):
    """Fill one ability's settings from its defaults, keeping each value's
    type (bool / int / float / str / dict)."""
    out = {}
    raw = raw if isinstance(raw, dict) else {}
    for k, dv in DEFAULTS[kind].items():
        v = raw.get(k, dv)
        try:
            if isinstance(dv, bool):
                v = bool(v)
            elif isinstance(dv, int):
                v = int(round(float(v)))
            elif isinstance(dv, float):
                v = float(v)
            elif isinstance(dv, dict):
                v = {kk: bool((v or {}).get(kk, dd)) if isinstance(v, dict) else dd
                     for kk, dd in dv.items()}
            else:
                v = str(v)
        except (TypeError, ValueError):
            v = dv
        if k in _LIMITS and not isinstance(v, (bool, dict, str)):
            lo, hi = _LIMITS[k]
            v = max(lo, min(hi, v))
        out[k] = v
    return out


def cfg(fig):
    """(type, settings) of this figure's unique ability, or None.  Cached on
    the mode instance like the other generic *_cfg parsers."""
    mode = getattr(fig, "mode", None)
    if mode is None:
        return None
    if hasattr(mode, "_ua_cfg"):
        return mode._ua_cfg
    char = getattr(mode, "character", None) or {}
    raw = (char.get("_fxkit") or {}).get("unique_ability") or char.get("unique_ability")
    res = None
    if isinstance(raw, dict):
        kind = raw.get("type")
        if kind in DEFAULTS:
            res = (kind, _norm(kind, raw.get(kind)))
    mode._ua_cfg = res
    return res


def _of(fig, kind):
    c = cfg(fig) if fig is not None else None
    return c[1] if c is not None and c[0] == kind else None


def _ticks(ms):
    return max(1, int(round(float(ms) / TICK_MS)))


def _rgb(hexs, fallback=(255, 255, 255)):
    s = str(hexs or "").lstrip("#")
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except (ValueError, IndexError):
        return fallback


# ------------------------------------------------------------ per-figure state
class UAState:
    __slots__ = ("shots", "sparks", "legion_fired", "legion_cd", "legion_timer", "hits",
                 "charges", "recharge", "spawn", "stance_left", "stance_timer",
                 "riposte_cd", "flash", "flash_rgb")

    def __init__(self, fig):
        self.shots = []          # projectiles queued for this figure's side
        self.sparks = []
        self.legion_fired = set()
        self.legion_cd = 0
        self.legion_timer = 0
        self.hits = 0
        self.charges = None      # phase shift charges left (set on first use)
        self.recharge = 0
        self.spawn = (fig.transform.x, fig.transform.y)
        self.stance_left = 0
        self.stance_timer = 0
        self.riposte_cd = 0
        self.flash = 0
        self.flash_rgb = (255, 255, 255)


def state(fig):
    st = getattr(fig, "ua", None)
    if st is None:
        st = UAState(fig)
        fig.ua = st
    return st


# ------------------------------------------------------------ helpers
def _enemy_points(fig, world):
    """Where this figure's enemies are: the partner snapshot when the
    world is bound to its side, the other sides' fighters when called from
    the world-level hit delivery, the cursor in Solo."""
    if world is None:
        return []
    if getattr(world, "battle_mode", False):
        if fig in (world.figures or []) and world.partner_figures:
            return [(e[0], e[1]) for e in world.partner_figures]
        pts = []
        for s in getattr(world, "sides", ()) or ():
            if fig in s.figures:
                continue
            pts.extend((f.x, f.y) for f in s.figures)
        if pts:
            return pts
    return [tuple(world.cursor)]


def _nearest(pts, x, y):
    if not pts:
        return None
    return min(pts, key=lambda q: (q[0] - x) ** 2 + (q[1] - y) ** 2)


def _clamp_xy(fig, x, y, margin=24.0):
    return (max(margin, min(fig.screen_w - margin, x)),
            max(margin, min(fig.screen_h - margin, y)))


def _burst(dst, x, y, rgb, n=10, spd=(1.0, 4.0), rng=random):
    r, g, b = rgb
    for _ in range(n):
        a = rng.uniform(0.0, 2.0 * math.pi)
        s = rng.uniform(*spd)
        dst.append([x, y, math.cos(a) * s, math.sin(a) * s, 0, r, g, b])


def _warp(fig, nx, ny):
    """Move the figure, cancel any knockback slide, queue the blink crackle."""
    t, m = fig.transform, fig.motion
    ox, oy = t.x, t.y
    nx, ny = _clamp_xy(fig, nx, ny)
    t.x, t.y = nx, ny
    m.bouncing = False
    m.bounce_vx = m.bounce_vy = 0.0
    fig.combat.blink_fx_pending.append((ox, oy, nx, ny))


def _protect(fig, world, ms):
    """Nullified hit: invincible for `ms` and no knockback this tick."""
    if world is None:
        return
    p = fig.personality
    p.dmg_immune_until = max(p.dmg_immune_until, world.global_tick + max(2, _ticks(ms)))
    p.dmg_hit_tick = world.global_tick - 2


# ------------------------------------------------------------ per tick
def tick(fig, world):
    """CombatSystem hook, once per body step (world bound to fig's side)."""
    c = cfg(fig)
    st = getattr(fig, "ua", None)
    if c is None and st is None:
        return
    st = state(fig)
    if st.shots:
        world.projectiles.extend(st.shots)
        st.shots = []
    if st.sparks:
        world.sparks.extend(st.sparks)
        st.sparks = []
    if st.flash > 0:
        st.flash -= 1
    if c is None:
        return
    kind, P = c
    if kind == "mirror_legion":
        if st.legion_cd > 0:
            st.legion_cd -= 1
        if P["trigger"] == "timer":
            st.legion_timer += 1
            if st.legion_timer >= _ticks(P["every_ms"]) and st.legion_cd <= 0:
                st.legion_timer = 0
                _spawn_legion(fig, world, P)
    elif kind == "phase_shift":
        if st.charges is None:
            st.charges = P["charges"]
        if P["charges"] > 0 and P["recharge_ms"] > 0 and st.charges < P["charges"]:
            st.recharge += 1
            if st.recharge >= _ticks(P["recharge_ms"]):
                st.recharge = 0
                st.charges += 1
    elif kind == "riposte":
        if st.riposte_cd > 0:
            st.riposte_cd -= 1
        if st.stance_left > 0:
            st.stance_left -= 1
        elif P["mode"] in ("stance", "both"):
            st.stance_timer += 1
            if st.stance_timer >= _ticks(P["stance_every_ms"]) and st.riposte_cd <= 0:
                st.stance_timer = 0
                st.stance_left = _ticks(P["stance_ms"])


# ------------------------------------------------------------ being hit
def intercept(fig, world, amount):
    """Called for every incoming hit before it lands (after the normal
    blocks).  True = the hit is nullified (Phase Shift / Riposte)."""
    c = cfg(fig)
    if c is None:
        return False
    kind, P = c
    if kind == "phase_shift":
        return _phase_shift(fig, world, amount, P)
    if kind == "riposte":
        return _riposte(fig, world, amount, P)
    return False


def after_damage(fig, world, amount):
    """Called after a hit took HP (the figure is still alive)."""
    P = _of(fig, "mirror_legion")
    if P is None:
        return
    st = state(fig)
    st.hits += 1
    if P["trigger"] == "hp_below":
        p = fig.personality
        if not p.max_hp:
            return
        hp_pct = 100.0 * p.hp / p.max_hp
        for part in str(P["hp_thresholds"]).replace(";", ",").split(","):
            try:
                th = float(part)
            except ValueError:
                continue
            if th not in st.legion_fired and hp_pct <= th:
                st.legion_fired.add(th)
                _spawn_legion(fig, world, P)
    elif P["trigger"] == "hits_taken":
        if st.hits >= P["every_hits"] and st.legion_cd <= 0:
            st.hits = 0
            _spawn_legion(fig, world, P)


def taken_mult(fig):
    """Berserker weakness: incoming damage multiplier while enraged."""
    P = _of(fig, "berserker")
    if P is None or P["damage_taken_pct"] == 0:
        return 1.0
    return max(0.0, 1.0 + P["damage_taken_pct"] / 100.0 * _rage(fig, P))


def on_dodge(fig):
    """combat.spawn_clone hook: Mirror Legion with the on_dodge trigger
    spawns its legion instead.  True when it handled the dodge."""
    P = _of(fig, "mirror_legion")
    if P is None or P["trigger"] != "on_dodge":
        return False
    if state(fig).legion_cd <= 0:
        _spawn_legion(fig, None, P)
    return True


# ------------------------------------------------------------ Mirror Legion
def _spawn_legion(fig, world, P):
    from . import combat
    st = state(fig)
    st.legion_cd = _ticks(P["cooldown_ms"])
    x, y = fig.transform.x, fig.transform.y
    n = P["count"]
    rng = fig.personality.rng
    sp = P["spread_px"]
    pts = []
    if P["formation"] == "at_self":
        pts = [(x + rng.uniform(-12, 12), y + rng.uniform(-12, 12)) for _ in range(n)]
    elif P["formation"] == "corners":
        ins = 60.0
        cs = [(ins, ins), (fig.screen_w - ins, ins), (ins, fig.screen_h - ins),
              (fig.screen_w - ins, fig.screen_h - ins)]
        pts = [cs[i % 4] for i in range(n)]
    elif P["formation"] == "mirror":
        tgt = _nearest(_enemy_points(fig, world), x, y) if world is not None else None
        tx, ty = tgt if tgt else (x + 1.0, y)
        dx, dy = tx - x, ty - y
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        bx, by = tx + ux * sp, ty + uy * sp
        for i in range(n):
            off = (i - (n - 1) / 2.0) * 50.0
            pts.append((bx - uy * off, by + ux * off))
    else:   # around
        a0 = rng.uniform(0, 2 * math.pi)
        pts = [(x + math.cos(a0 + 2 * math.pi * i / n) * sp,
                y + math.sin(a0 + 2 * math.pi * i / n) * sp) for i in range(n)]
    speed = fig.motion.follow_speed * P["speed_pct"] / 100.0
    alpha = max(10, min(255, int(255 * P["opacity_pct"] / 100.0)))
    for (px, py) in pts:
        px, py = _clamp_xy(fig, px, py)
        fig.combat.clones.append(combat.CloneEffect(
            px, py, _ticks(P["duration_ms"]), speed, P["damage"], alpha=alpha))
        fig.combat.blink_fx_pending.append((x, y, px, py))


# ------------------------------------------------------------ Berserker
def _rage(fig, P):
    """0..1: how far into the rage curve the figure's lost HP is."""
    p = fig.personality
    if not p.max_hp:
        return 0.0
    lost = 100.0 * (1.0 - max(0.0, p.hp) / float(p.max_hp))
    lo, hi = P["start_lost_pct"], max(P["start_lost_pct"] + 0.01, P["max_lost_pct"])
    f = max(0.0, min(1.0, (lost - lo) / (hi - lo)))
    if P["curve"] == "exponential":
        f = f * f
    elif P["curve"] == "steps":
        n = max(1, P["steps"])
        f = math.floor(f * n + 1e-9) / n
    return f


def speed_mult(fig):
    """Body time scale (movement + attack speed, every state)."""
    P = _of(fig, "berserker")
    if P is None:
        return 1.0
    return 1.0 + P["max_bonus_pct"] / 100.0 * _rage(fig, P)


def fx_speed_mult(fig):
    """Time scale of the figure's own FX / bullets (Berserker 'speed FX')."""
    P = _of(fig, "berserker")
    if P is None or not P["speed_fx"]:
        return 1.0
    return speed_mult(fig)


def out_mult(fig):
    """Outgoing damage multiplier (Berserker damage bonus)."""
    P = _of(fig, "berserker")
    if P is None or P["damage_bonus_pct"] == 0:
        return 1.0
    return max(0.0, 1.0 + P["damage_bonus_pct"] / 100.0 * _rage(fig, P))


# ------------------------------------------------------------ Phase Shift
def _phase_shift(fig, world, amount, P):
    st = state(fig)
    if st.charges is None:
        st.charges = P["charges"]
    if P["charges"] > 0 and st.charges <= 0:
        return False
    p = fig.personality
    trig = P["trigger"]
    if trig == "min_damage" and amount < P["min_damage"]:
        return False
    if trig == "hp_below" and (not p.max_hp or 100.0 * p.hp / p.max_hp > P["hp_below_pct"]):
        return False
    if trig == "chance" and p.rng.uniform(0, 100) >= P["chance_pct"]:
        return False
    dests = [k for k, on in P["destinations"].items() if on] or ["random"]
    pick = p.rng.choice(dests)
    x, y = fig.transform.x, fig.transform.y
    ex, ey = _nearest(_enemy_points(fig, world), x, y) or (x + 1.0, y)
    if pick == "behind_attacker":
        dx, dy = ex - x, ey - y
        d = math.hypot(dx, dy) or 1.0
        nx, ny = ex + dx / d * P["behind_px"], ey + dy / d * P["behind_px"]
    elif pick == "far_corner":
        ins = 40.0
        cs = [(ins, ins), (fig.screen_w - ins, ins), (ins, fig.screen_h - ins),
              (fig.screen_w - ins, fig.screen_h - ins)]
        nx, ny = max(cs, key=lambda q: (q[0] - ex) ** 2 + (q[1] - ey) ** 2)
    elif pick == "spawn":
        nx, ny = st.spawn
    elif pick == "mirror":
        nx, ny = 2 * ex - x, 2 * ey - y
    elif pick == "fixed":
        nx, ny = fig.screen_w * P["fixed_x_pct"] / 100.0, fig.screen_h * P["fixed_y_pct"] / 100.0
    else:   # random
        a = p.rng.uniform(0, 2 * math.pi)
        lo = P["random_min_px"]
        dist = p.rng.uniform(lo, max(lo, P["random_max_px"]))
        nx, ny = x + math.cos(a) * dist, y + math.sin(a) * dist
    _warp(fig, nx, ny)
    _protect(fig, world, P["invuln_ms"])
    if P["charges"] > 0:
        st.charges -= 1
    st.flash = 8
    st.flash_rgb = tuple(fig.lut[200])
    return True


# ------------------------------------------------------------ Riposte
def in_stance(fig):
    st = getattr(fig, "ua", None)
    return bool(st is not None and st.stance_left > 0 and _of(fig, "riposte") is not None)


def _riposte(fig, world, amount, P):
    from . import combat
    st = state(fig)
    if st.riposte_cd > 0:
        return False
    rng = fig.personality.rng
    ok = False
    if P["mode"] in ("stance", "both") and st.stance_left > 0:
        ok = True
    if not ok and P["mode"] in ("chance", "both") and rng.uniform(0, 100) < P["chance_pct"]:
        ok = True
    if not ok:
        return False
    st.stance_left = 0
    st.stance_timer = 0
    st.riposte_cd = _ticks(P["cooldown_ms"])
    _protect(fig, world, P["invuln_ms"])
    x, y = fig.transform.x, fig.transform.y
    ex, ey = _nearest(_enemy_points(fig, world), x, y) or (x + 1.0, y)
    if P["counter"] == "blink_strike":
        dx, dy = x - ex, y - ey
        d = math.hypot(dx, dy) or 1.0
        _warp(fig, ex + dx / d * 45.0, ey + dy / d * 45.0)
        x, y = fig.transform.x, fig.transform.y
    rgb = _rgb(P["color"], (255, 211, 74))
    dx, dy = ex - x, ey - y
    d = math.hypot(dx, dy) or 1.0
    spd = config.PROJ_SPEED * 1.6
    pr = combat.Projectile(x, y, dx / d * spd, dy / d * spd, rgb, config.BEAM_TRAIL_LEN)
    pr.style = "beam"
    pr.damage = max(P["base_damage"], float(amount) * P["counter_mult_pct"] / 100.0)
    pr.knockback_px = P["knockback_px"]
    pr.one_hit = True
    pr.owner = fig
    pr.max_age = max(6, int(d / spd) + 8)
    st.shots.append(pr)
    _burst(st.sparks, x, y, rgb, n=14, spd=(1.5, 5.0), rng=rng)
    st.flash = 12
    st.flash_rgb = rgb
    return True


# ------------------------------------------------------------ Ricochet
_RC_PRIMS_OFF = ("weapon", "ghost", "particles", "pulse")


def _reflect(vx, vy, nx, ny):
    dot = vx * nx + vy * ny
    if dot >= 0:            # already moving away from the surface
        return vx, vy
    return vx - 2 * dot * nx, vy - 2 * dot * ny


def _aim(P, vx, vy, x, y, targets, rng):
    """Apply the bounce angle style to an already reflected velocity."""
    spd = math.hypot(vx, vy)
    if P["angle"] == "seek" and targets:
        tx, ty = _nearest(targets, x, y)
        d = math.hypot(tx - x, ty - y)
        if d > 1.0:
            return (tx - x) / d * spd, (ty - y) / d * spd
    if P["angle"] == "random":
        a = math.atan2(vy, vx) + math.radians(rng.uniform(-P["random_deg"], P["random_deg"]))
        return math.cos(a) * spd, math.sin(a) * spd
    return vx, vy


def _proj_cfg(proj):
    rb = getattr(proj, "ua_rb", None)
    if rb is None:
        P = _of(getattr(proj, "owner", None), "ricochet")
        rb = P["bounces"] if P else 0
        proj.ua_rb = rb
        proj.ua_cd = 0
    if rb <= 0:
        return None
    return _of(proj.owner, "ricochet")


def _bounce_proj(proj, P, nx, ny, targets, rng):
    from . import combat
    vx, vy = _reflect(proj.vx, proj.vy, nx, ny)
    vx, vy = _aim(P, vx, vy, proj.x, proj.y, targets, rng)
    k = P["keep_speed_pct"] / 100.0
    proj.vx, proj.vy = vx * k, vy * k
    proj.damage = float(getattr(proj, "damage", 1.0)) * P["keep_damage_pct"] / 100.0
    proj.ua_rb -= 1
    proj.ua_cd = 3
    # A bounced shot gets a fresh life so it can reach its next surface.
    proj.age = 0
    st = state(proj.owner)
    if P["sparks"]:
        _burst(st.sparks, proj.x, proj.y, (proj.r, proj.g, proj.b), n=6, spd=(1.0, 3.5), rng=rng)
    for i in range(P["split"]):
        side = 1 if i % 2 == 0 else -1
        a = math.atan2(proj.vy, proj.vx) + math.radians(P["split_deg"] * (i // 2 + 1) * side)
        s = math.hypot(proj.vx, proj.vy)
        cp = combat.Projectile(proj.x, proj.y, math.cos(a) * s, math.sin(a) * s,
                               (proj.r, proj.g, proj.b), max(3, len(proj.trail)))
        for f in ("style", "damage", "pierce", "knockback_px", "owner", "no_knockback",
                  "max_age", "radius", "hit_r_sq", "one_hit"):
            setattr(cp, f, getattr(proj, f))
        cp.ua_rb = proj.ua_rb
        cp.ua_cd = 3
        st.shots.append(cp)


def proj_step(proj, world):
    """ProjectileSystem hook (owner side), after the bullet moved: walls and
    enemy shots.  A bullet fired without an owner (older fire paths) belongs
    to its side's only fighter, the same fallback timefx.proj_steps uses."""
    if getattr(proj, "ua_rb", None) is None and proj.owner is None:
        figs = world.figures or []
        if len(figs) == 1 and _of(figs[0], "ricochet") is not None:
            proj.owner = figs[0]
    P = _proj_cfg(proj)
    if P is None:
        return
    if proj.ua_cd > 0:
        proj.ua_cd -= 1
        return
    rng = proj.owner.personality.rng
    targets = _enemy_points(proj.owner, world)
    if P["walls"]:
        sw, sh = world.screen_w, world.screen_h
        nx = 1.0 if proj.x < 0 else -1.0 if proj.x > sw else 0.0
        ny = 1.0 if proj.y < 0 else -1.0 if proj.y > sh else 0.0
        if nx or ny:
            proj.x = max(0.0, min(sw, proj.x))
            proj.y = max(0.0, min(sh, proj.y))
            n = math.hypot(nx, ny)
            _bounce_proj(proj, P, nx / n, ny / n, targets, rng)
            return
    if P["fx"]:
        cr = P["fx_contact_px"]
        for s in getattr(world, "enemy_shots", None) or ():
            if s.dead:
                continue
            dx, dy = proj.x - s.x, proj.y - s.y
            d = math.hypot(dx, dy)
            if d <= cr:
                if d < 0.01:
                    dx, dy, d = -proj.vx, -proj.vy, math.hypot(proj.vx, proj.vy) or 1.0
                nx, ny = dx / d, dy / d
                proj.x, proj.y = s.x + nx * (cr + 1), s.y + ny * (cr + 1)
                _bounce_proj(proj, P, nx, ny, targets, rng)
                return


def proj_wants_figures(proj):
    """True while this bullet bounces off fighters (the owner side then
    leaves it alive on contact; the struck side bounces it)."""
    P = _proj_cfg(proj)
    return bool(P and P["characters"])


def proj_off_point(proj, px, py, radius, world=None):
    """Bounce a bullet off a fighter / the cursor at (px, py).  True when it
    bounced (the caller must not destroy it)."""
    P = _proj_cfg(proj)
    if not (P and P["characters"]):
        return False
    dx, dy = proj.x - px, proj.y - py
    d = math.hypot(dx, dy)
    if d < 0.01:
        dx, dy, d = -proj.vx, -proj.vy, math.hypot(proj.vx, proj.vy) or 1.0
    nx, ny = dx / d, dy / d
    proj.x, proj.y = px + nx * (radius + 2), py + ny * (radius + 2)
    _bounce_proj(proj, P, nx, ny, None, proj.owner.personality.rng)
    return True


def proj_off_figure(proj, fx, fy, radius):
    """Struck-side hook (CollisionSystem): the bullet that just hit a
    fighter bounces off it instead of dying (sanctioned mutation of the
    source bullet through the snapshot's tuple[8])."""
    return proj_off_point(proj, fx, fy, radius)


def _inst_cfg(inst, host):
    fx = inst.fx
    if fx["prim"] in _RC_PRIMS_OFF:
        return None
    if not (inst.free or fx["motion"]["kind"] in ("travel", "homing", "zigzag")):
        return None
    if inst.ua_rb is None:
        P = _of(getattr(host, "fig", None), "ricochet")
        inst.ua_rb = P["bounces"] if P else 0
    if inst.ua_rb <= 0:
        return None
    return _of(host.fig, "ricochet")


def _bounce_inst(inst, host, P, nx, ny, targets):
    rng = host.fig.personality.rng
    vx, vy = _reflect(inst.vx, inst.vy, nx, ny)
    vx, vy = _aim(P, vx, vy, inst.x, inst.y, targets, rng)
    k = P["keep_speed_pct"] / 100.0
    inst.vx, inst.vy = vx * k, vy * k
    s = math.hypot(inst.vx, inst.vy)
    if s > 1e-6:
        inst.dir = [inst.vx / s, inst.vy / s]
    # zigzag: its side-to-side offset mirrors with the bounce
    inst.zx, inst.zy = _reflect(inst.zx, inst.zy, nx, ny)
    inst.ua_dm *= P["keep_damage_pct"] / 100.0
    inst.ua_rb -= 1
    inst.ua_cd = 3
    # Fresh life for the next leg (its hit window restarts too).
    inst.age = 0
    if P["sparks"] and getattr(host, "world", None) is not None:
        rgb = tuple(host.fig.lut[200])
        _burst(host.world.sparks, inst.x, inst.y, rgb, n=6, spd=(1.0, 3.5), rng=rng)


def inst_step(inst, host):
    """fxkit.tick_inst hook (owner side), after the effect moved."""
    P = _inst_cfg(inst, host)
    if P is None:
        return
    if inst.ua_cd > 0:
        inst.ua_cd -= 1
        return
    fig = host.fig
    targets = [tuple(host.target)] if getattr(host, "target", None) else None
    if P["walls"]:
        sw, sh = fig.screen_w, fig.screen_h
        nx = 1.0 if inst.x < 0 else -1.0 if inst.x > sw else 0.0
        ny = 1.0 if inst.y < 0 else -1.0 if inst.y > sh else 0.0
        if nx or ny:
            inst.x = max(0.0, min(sw, inst.x))
            inst.y = max(0.0, min(sh, inst.y))
            n = math.hypot(nx, ny)
            _bounce_inst(inst, host, P, nx / n, ny / n, targets)
            return
    if P["fx"]:
        cr = P["fx_contact_px"]
        for s in getattr(host, "shots", None) or ():
            if s.dead:
                continue
            dx, dy = inst.x - s.x, inst.y - s.y
            d = math.hypot(dx, dy)
            if d <= cr:
                if d < 0.01:
                    dx, dy, d = -inst.vx, -inst.vy, math.hypot(inst.vx, inst.vy) or 1.0
                nx, ny = dx / d, dy / d
                inst.x, inst.y = s.x + nx * (cr + 1), s.y + ny * (cr + 1)
                _bounce_inst(inst, host, P, nx, ny, targets)
                return


def inst_off_figure(inst, host, hx, hy, hr):
    """fxkit hit hook: the effect that just hit a fighter bounces off it
    instead of ending.  True when it bounced."""
    P = _inst_cfg(inst, host)
    if not (P and P["characters"]):
        return False
    dx, dy = inst.x - hx, inst.y - hy
    d = math.hypot(dx, dy)
    if d < 0.01:
        dx, dy, d = -inst.vx, -inst.vy, math.hypot(inst.vx, inst.vy) or 1.0
    nx, ny = dx / d, dy / d
    inst.x, inst.y = hx + nx * (hr + 2), hy + ny * (hr + 2)
    _bounce_inst(inst, host, P, nx, ny, None)
    return True


def inst_dmg_mult(inst):
    return getattr(inst, "ua_dm", 1.0) or 0.0


# ------------------------------------------------------------ drawing
def draw(fig, p, pscale=1.0):
    """Ability overlays around the figure (drawn behind the sprite)."""
    c = cfg(fig)
    if c is None:
        return
    kind, P = c
    st = getattr(fig, "ua", None)
    x, y = fig.transform.x, fig.transform.y
    try:
        bs = float(fig.mode.body_scale())
    except Exception:
        bs = 1.0
    R = 34.0 * bs * pscale
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    if kind == "berserker" and P["aura"]:
        f = _rage(fig, P)
        if f > 0.01:
            r, g, b = _rgb(P["aura_color"], (255, 42, 42))
            pulse = 0.85 + 0.15 * math.sin(getattr(fig.render, "anim_tick", 0) * 0.6)
            rr = R * (1.1 + 0.6 * f) * pulse
            grad = QRadialGradient(QPointF(x, y), rr)
            grad.setColorAt(0.0, QColor(r, g, b, int(150 * f)))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(x, y), rr, rr)
    if kind == "riposte" and st is not None and st.stance_left > 0:
        r, g, b = _rgb(P["color"], (255, 211, 74))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(r, g, b, 200), 2.5 * pscale))
        p.drawEllipse(QPointF(x, y), R * 1.15, R * 1.15)
    if kind == "phase_shift" and P["show_charges"] and P["charges"] > 0 and st is not None:
        n = st.charges if st.charges is not None else P["charges"]
        r, g, b = fig.lut[200]
        p.setPen(Qt.NoPen)
        tot = min(P["charges"], 10)
        for i in range(tot):
            on = i < n
            p.setBrush(QColor(r, g, b, 230 if on else 60))
            px = x + (i - (tot - 1) / 2.0) * 9 * pscale
            p.drawEllipse(QPointF(px, y - R * 1.6), 3 * pscale, 3 * pscale)
    if st is not None and st.flash > 0:
        r, g, b = st.flash_rgb
        a = int(220 * st.flash / 12.0)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(r, g, b, max(0, min(255, a))), 3 * pscale))
        rr = R * (1.6 - st.flash / 12.0 * 0.5)
        p.drawEllipse(QPointF(x, y), rr, rr)
    p.restore()
