"""
Dodge — a character-level reaction to incoming projectiles.  Set in FX
Studio ("Dodge (whole character)", pack.dodge) for image characters (Rig
Forge + FX Studio).  Characters without it are untouched; the built-in
swordsman and rig-drawn melee JSON characters keep their own bullet dodge
(systems.CollisionSystem), which image characters never use (their combat
runs through the action runner, so that dodge could never move them).

What it reacts to (react_to): enemy projectiles in the side's snapshot
(world.enemy_shots) — "bullets" = the built-in bullets, "fx" = FX Studio
projectiles (thrown blades, sword rain, homing / zigzag / path shots ...
anything with Deals damage that travels), "all" = both.  A projectile
triggers it once it comes within trigger_px (times the character scale),
heading at the fighter when incoming_only is on.  The check looks
LOOKAHEAD_TICKS ahead along the projectile's path: the snapshot it reads
is one tick old and the shot moves again before its hit lands, so a fast
shot (more px per tick than trigger_px) would otherwise only be seen on
the tick it hits.  Each projectile is
rolled once (chance_pct); the optional trigger conditions (ANY / ALL, the
action trigger conditions, "this action" = the dodge) gate it on top.
A new dodge can start cooldown_ms after the last one started.  It can
start mid-knockback: like a blink, the dodge takes the fighter out of the
slide.  A knockback that lands while it sidesteps still ends the sidestep.

style — how it gets out of the way:
  sidestep          a fast physical sidestep, distance_px long at speed_pct %
                    of the built-in dodge speed (config.DODGE_SPEED px/tick)
  blink             an instant teleport to the same spot (blink crackle and
                    afterimages, like the built-in blink dodge)
  action            plays `action` (any Rig Forge action, e.g. a "Dodge ·
                    roll"); its own Movement and its own Blink (FX Studio
                    "Blink (this action)") carry the fighter
  sidestep_action / blink_action   both at once
Direction (sidestep / blink): side = "open" (away from the projectile's
line, like the built-in dodge), "random" or "alternate" (left, right, ...),
then turned angle_deg toward the target (negative = away from it).

While the dodge lasts — the sidestep, the dodge action, plus invuln_ms
after it (a blink lasts just invuln_ms) — fx ("fx:<id>" / "group:<id>")
plays (laser/fxkit.py FxDriver._dodge_tick), and with invulnerable on the
fighter takes no hits: shots and FX pass through it (World.refresh_battle
lists it in partner_gone) and no damage or knockback lands (ai.damage_immune).

counter_action: an action played straight after the dodge (and its action)
ends, counter_delay_ms later, when Attack mode is on and the target is
within counter_range_px (0 = any distance).  It skips its own conditions
and cooldown.

Driven from CombatSystem for every figure, so Solo and Battle run the same
code.  Solo has no enemy projectiles, so nothing triggers it there.
"""

import copy
import math

from . import config

from .actions import CONDITION_TYPES as CONDITIONS

STYLES = ("sidestep", "blink", "action", "sidestep_action", "blink_action")
SIDES = ("open", "random", "alternate")
REACT_TO = ("all", "bullets", "fx")
DEFAULTS = dict(enabled=False, style="sidestep", action="", react_to="all",
                trigger_px=90.0, incoming_only=True, chance_pct=100.0, cooldown_ms=300.0,
                distance_px=108.0, speed_pct=100.0, side="open", angle_deg=0.0,
                flash=True, afterimages=True, during_attacks=True,
                invulnerable=False, invuln_ms=150.0,
                counter_action="", counter_delay_ms=0.0, counter_range_px=0.0,
                logic="any", conditions=[], fx="")
KEY = "@dodge"            # the dodge's name in the condition tracker
MARGIN_PX = 20.0          # keep the fighter this far inside the screen
LOOKAHEAD_TICKS = 2       # stale snapshot + the shot's own move before it hits


def normalize(cfg):
    out = dict(cfg or {})
    for k, v in DEFAULTS.items():
        if k not in out:
            out[k] = copy.deepcopy(v)
    if out["style"] not in STYLES:
        out["style"] = DEFAULTS["style"]
    if out["side"] not in SIDES:
        out["side"] = DEFAULTS["side"]
    if out["react_to"] not in REACT_TO:
        out["react_to"] = DEFAULTS["react_to"]
    conds = []
    for c in out.get("conditions") or []:
        t = (c or {}).get("type")
        if t in CONDITIONS:
            cc = dict(CONDITIONS[t])
            cc["not"] = False
            cc.update(c)
            conds.append(cc)
    out["conditions"] = conds
    return out


def config_for(fig):
    """Normalised dodge settings for fig, or None when it has none (or
    they are switched off)."""
    mode = fig.mode
    if hasattr(mode, "_dodge_cfg"):
        return mode._dodge_cfg
    cfg = None
    char = getattr(mode, "character", None)
    if char and char.get("_package"):
        raw = (char.get("_fxkit") or {}).get("dodge")
        if isinstance(raw, dict):
            n = normalize(raw)
            if n.get("enabled"):
                cfg = n
    mode._dodge_cfg = cfg
    return cfg


class DodgeState:
    __slots__ = ("moving", "vx", "vy", "budget", "hold_until", "act", "act_started",
                 "cooldown_until", "seen", "flip", "counter", "counter_at", "ticks")

    def __init__(self):
        self.moving = False
        self.vx = self.vy = 0.0
        self.budget = 0.0
        self.hold_until = -1      # tick the dodge (and its invulnerability) ends after moving
        self.act = None           # the dodge action this dodge started (name), until it ends
        self.act_started = None   # ... and the tick it started
        self.cooldown_until = 0
        self.seen = set()         # id() of every projectile already rolled for
        self.flip = False         # "alternate" side: the next one goes the other way
        self.counter = False      # a counter is owed once the dodge is over
        self.counter_at = None    # tick it fires (set when the dodge ends)
        self.ticks = 0


def _ticks(ms):
    return max(0, int(round(max(0.0, float(ms or 0)) / config.TICK_MS)))


def _act_playing(fig, st):
    """The dodge's own action is still playing."""
    if st.act is None:
        return False
    r = getattr(fig, "act", None)
    if r is not None and r.playing == st.act and r.started == st.act_started:
        return True
    st.act = None
    return False


def active(fig, now=None):
    """True while fig is dodging (sidestep, its dodge action, or the
    invuln_ms after it)."""
    st = getattr(fig, "dodge", None)
    if st is None:
        return False
    if st.moving or _act_playing(fig, st):
        return True
    return now is not None and now < st.hold_until


def untouchable(fig, now):
    """True while a dodge with Invulnerable on makes fig unhittable."""
    st = getattr(fig, "dodge", None)
    if st is None:
        return False
    cfg = config_for(fig)
    return bool(cfg and cfg.get("invulnerable") and active(fig, now))


def _in_ultimate(fig):
    r = getattr(fig, "act", None)
    return r is not None and r.playing == "ultimate"


def _can_start(fig, cfg):
    from . import blink, timefx, actions
    c = fig.combat
    if not fig.transform.init or blink.gone(fig) or timefx.frozen(fig):
        return False
    if (c.vc_phase or c.sp_phase or c.lb_phase or c.blinkstorm_strikes_left > 0
            or _in_ultimate(fig)):
        return False
    rt = getattr(fig, "retreat", None)
    if rt is not None and rt.active:
        return False
    r = getattr(fig, "act", None)
    if r is not None and r.playing:
        if r.forced is not None:
            return False          # a clash owns the fighter
        kind = actions._kind(r.playing)
        if kind == "attack" and not cfg.get("during_attacks"):
            return False
        if kind == "triggered" and r.playing != cfg.get("action"):
            return False          # never cut into defend / special / ...
    return True


def _cond_met(fig, r, c, ctx, world):
    if c["type"] == "projectile_count":
        v = len(getattr(world, "enemy_shots", None) or []) >= max(1, int(c.get("count", 5)))
    else:
        v = r._cond_true(fig, KEY, c, ctx)
    return (not v) if c.get("not") else v


def _threat(fig, world, cfg, st, shots):
    """The nearest projectile that should make fig dodge now, or None."""
    want = cfg.get("react_to")
    reach = max(0.0, float(cfg.get("trigger_px") or 0)) * fig.mode.body_scale()
    r2 = reach * reach
    best = None
    for s in shots:
        if s.dead or id(s.ref) in st.seen:
            continue
        if want == "bullets" and s.kind != "bullet":
            continue
        if want == "fx" and s.kind != "fx":
            continue
        dx, dy = s.x - fig.x, s.y - fig.y
        d2 = dx * dx + dy * dy
        if d2 > r2:
            # Not in reach yet: does its path over the next ticks pass
            # within reach?  Closest point of that segment to the fighter.
            mx, my = s.vx * LOOKAHEAD_TICKS, s.vy * LOOKAHEAD_TICKS
            mm = mx * mx + my * my
            if mm < 1e-9:
                continue
            k = max(0.0, min(1.0, -(dx * mx + dy * my) / mm))
            cx, cy = dx + mx * k, dy + my * k
            if cx * cx + cy * cy > r2:
                continue
        if cfg.get("incoming_only") and (s.vx * dx + s.vy * dy) >= 0:
            continue              # moving away (or not moving)
        if best is None or d2 < best[0]:
            best = (d2, s)
    return None if best is None else best[1]


def _direction(fig, world, cfg, st, s):
    """Unit dodge direction away from projectile s."""
    from . import retreat
    spd = math.hypot(s.vx, s.vy)
    ddx, ddy = s.x - fig.x, s.y - fig.y
    if spd > 0.001:
        bux, buy = s.vx / spd, s.vy / spd
    else:
        d = math.hypot(ddx, ddy)
        bux, buy = ((-ddx / d, -ddy / d) if d > 0.001 else (1.0, 0.0))
    left, right = (-buy, bux), (buy, -bux)
    side = cfg.get("side")
    if side == "random":
        sx, sy = left if fig.personality.rng.random() < 0.5 else right
    elif side == "alternate":
        sx, sy = left if st.flip else right
        st.flip = not st.flip
    else:   # "open": away from the projectile's line (the built-in rule)
        sx, sy = left if bux * ddy - buy * ddx >= 0 else right
    a = math.radians(max(-180.0, min(180.0, float(cfg.get("angle_deg") or 0))))
    if abs(a) > 1e-6:
        tx, ty, _f = retreat._target(world, fig)
        tdx, tdy = tx - fig.x, ty - fig.y
        ca, sa = math.cos(a), math.sin(a)
        p = (sx * ca - sy * sa, sx * sa + sy * ca)
        q = (sx * ca + sy * sa, -sx * sa + sy * ca)
        # Positive turns toward the target, negative away from it.
        dp, dq = p[0] * tdx + p[1] * tdy, q[0] * tdx + q[1] * tdy
        sx, sy = p if (dp >= dq) == (a > 0) else q
    return sx, sy


def _clamp(fig, x, y):
    return (max(MARGIN_PX, min(fig.screen_w - MARGIN_PX, x)),
            max(MARGIN_PX, min(fig.screen_h - MARGIN_PX, y)))


def _stop_melee(fig):
    c = fig.combat
    c.dashing = c.rebounding = c.slashing = False
    c.arc_repositioning = c.arc_recoiling = False
    c.dodge_dashing = c.dodge_counter = c.dodge_interrupt = False


def _start(fig, world, cfg, st, s, r, ctx, now):
    from . import actions, combat
    style = cfg.get("style")
    # Every dodge takes the fighter out of a knockback slide (as a blink does).
    m = fig.motion
    m.bouncing = m.bounce_ending = False
    m.bounce_vx = m.bounce_vy = 0.0
    st.cooldown_until = now + _ticks(cfg.get("cooldown_ms"))
    st.counter = bool(cfg.get("counter_action"))
    st.counter_at = None
    r.mark_fired(KEY, cfg, ctx, now)
    if style in ("action", "sidestep_action", "blink_action") and cfg.get("action"):
        if actions.force_action(fig, world, cfg["action"]):
            st.act, st.act_started = cfg["action"], now
    dist = max(0.0, float(cfg.get("distance_px") or 0)) * fig.mode.body_scale()
    if style in ("sidestep", "sidestep_action") and dist > 0:
        sx, sy = _direction(fig, world, cfg, st, s)
        spd = config.DODGE_SPEED * max(1.0, float(cfg.get("speed_pct") or 0)) / 100.0
        _stop_melee(fig)
        st.moving = True
        st.vx, st.vy = sx * spd, sy * spd
        st.budget = dist
        st.ticks = 0
        st.hold_until = -1
    elif style in ("blink", "blink_action") and dist > 0:
        sx, sy = _direction(fig, world, cfg, st, s)
        nx, ny = _clamp(fig, fig.x + sx * dist, fig.y + sy * dist)
        _stop_melee(fig)
        if cfg.get("flash", True):
            combat.blink_warp(fig, nx, ny)
            combat.drain_blink_fx(fig, world)
        else:
            fig.transform.x, fig.transform.y = nx, ny
            fig.trail.clear()
        st.hold_until = now + _ticks(cfg.get("invuln_ms"))
    else:
        st.hold_until = now + _ticks(cfg.get("invuln_ms"))
    from . import action_log
    action_log.log("COMBAT", f"dodge style={style} shot={s.kind} at=({fig.x:.0f},{fig.y:.0f})")


def _move(fig, world, cfg, st, now):
    """One sidestep tick.  True while it moves the fighter."""
    from . import combat
    m = fig.motion
    if m.bouncing or m.bounce_ending:
        st.moving = False          # a knockback always moves the fighter
        st.hold_until = now + _ticks(cfg.get("invuln_ms"))
        return False
    t = fig.transform
    step = math.hypot(st.vx, st.vy)
    k = min(1.0, st.budget / step) if step > 1e-6 else 0.0
    t.x, t.y = _clamp(fig, t.x + st.vx * k, t.y + st.vy * k)
    st.budget -= step
    st.ticks += 1
    if cfg.get("afterimages", True) and st.ticks % 2 == 1:
        combat.spawn_afterimage(fig)
    combat._apply_trail_update(fig, t, True, False)
    fig.render.is_moving = True
    fig.render.advance()
    if st.budget <= 0:
        st.moving = False
        st.hold_until = now + _ticks(cfg.get("invuln_ms"))
    return True


def _counter(fig, world, cfg):
    from . import actions, retreat
    name = cfg.get("counter_action")
    if not name or not getattr(world, "shoot_mode", True):
        return
    rng = max(0.0, float(cfg.get("counter_range_px") or 0)) * fig.mode.body_scale()
    if rng > 0:
        tx, ty, _f = retreat._target(world, fig)
        if math.hypot(tx - fig.x, ty - fig.y) > rng:
            return
    actions.force_action(fig, world, name)


def tick(fig, world):
    """One tick, after the action runner.  True while the sidestep moves the
    figure this tick (the caller then skips everything else that moves it)."""
    cfg = config_for(fig)
    if cfg is None:
        return False
    st = getattr(fig, "dodge", None)
    if st is None:
        st = DodgeState()
        fig.dodge = st
    now = world.global_tick
    if st.moving:
        return _move(fig, world, cfg, st, now)
    from . import actions
    r, ctx = actions.tracker_ctx(fig, world)
    # The counter, once the dodge (and its action) is over.
    if st.counter and not _act_playing(fig, st):
        if st.counter_at is None:
            st.counter_at = now + _ticks(cfg.get("counter_delay_ms"))
            r.last_end[KEY] = now
        if now >= st.counter_at:
            st.counter = False
            st.counter_at = None
            _counter(fig, world, cfg)
    shots = getattr(world, "enemy_shots", None) or []
    if st.seen:
        st.seen &= {id(s.ref) for s in shots}   # forget projectiles that are gone
    if not shots or now < st.cooldown_until or not _can_start(fig, cfg):
        return False
    s = _threat(fig, world, cfg, st, shots)
    if s is None:
        return False
    conds = cfg.get("conditions") or []
    if conds:
        res = [_cond_met(fig, r, c, ctx, world) for c in conds]
        if not (all(res) if cfg.get("logic") == "all" else any(res)):
            return False          # not now; it may still dodge this one later
    st.seen.add(id(s.ref))       # one roll per projectile
    pct = max(0.0, min(100.0, float(cfg.get("chance_pct") or 0)))
    if pct < 100.0 and fig.personality.rng.random() * 100.0 >= pct:
        return False
    _start(fig, world, cfg, st, s, r, ctx, now)
    return _move(fig, world, cfg, st, now) if st.moving else False


def reset(fig):
    fig.dodge = None
