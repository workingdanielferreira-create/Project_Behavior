"""
Tactical retreat — a character-level dash away from harm, or round to the
target's back.  Set in FX Studio ("Tactical retreat (whole character)",
pack.retreat); a rig-drawn pb_character JSON can set the same top-level
"tactical_retreat" block.  Characters without it are untouched.

When its conditions are met (ANY / ALL) the fighter dashes at speed_pct % of
its normal speed.  The heading is measured from the direction to its target:
angle_deg 0 = straight at it, 180 / -180 = straight away, positive =
clockwise on screen.  curve_deg_s bends the path by that many degrees per
second (0 = straight).  The mode runs during the dash, for its own duration
(-1 = no limit):

  avoid     dash along the angle / curve, steering away from any harm that
            comes within proximity_px: enemy projectiles and the target itself.
  reengage  head for the target's back — the side opposite the way it was
            facing when the retreat started — steering round enemy projectiles
            within proximity_px.  With a curve it leaves along the angle and
            swings round toward that side at curve_deg_s; with curve 0 it goes
            straight there.  On arrival it attacks and the retreat ends.

A new retreat can start cooldown_ms after the last one ended.

fx (optional): "fx:<effect id>" or "group:<group id>" from the FX file; that
effect / group plays for the whole dash (laser/fxkit.py FxDriver), and still
plays on its own action too.

Conditions:
  hp_below          own HP at or below pct % (once, or again after every
                    cooldown while still below when repeat is on)
  projectile_count  `count` or more enemy projectiles in the air at once

Driven from CombatSystem for every figure (target = nearest enemy in Battle,
the cursor in Solo), so Solo and Battle run the same code.  Solo has no enemy
projectiles and the cursor has no facing: its back is the far side from the
fighter.
"""

import copy
import math

from . import config

DEFAULTS = dict(enabled=False, mode="avoid", angle_deg=180.0, curve_deg_s=0.0,
                speed_pct=200.0, proximity_px=80.0,
                avoid_duration_ms=1500.0, reengage_duration_ms=2000.0,
                cooldown_ms=3000.0, logic="any", conditions=[], fx="")
CONDITIONS = {"hp_below": dict(pct=50.0, repeat=False),
              "projectile_count": dict(count=5)}

ARRIVE_PX = 30.0          # re-engage: this close to the back point = arrived
BACK_STANDOFF_PX = 60.0   # back point distance behind the target (max)
STEER_WEIGHT = 1.6        # how hard nearby harm bends the heading


def normalize(cfg):
    out = dict(cfg or {})
    for k, v in DEFAULTS.items():
        if k not in out:
            out[k] = copy.deepcopy(v)
    conds = []
    for c in out.get("conditions") or []:
        t = (c or {}).get("type")
        if t in CONDITIONS:
            cc = dict(CONDITIONS[t])
            cc.update(c)
            conds.append(cc)
    out["conditions"] = conds
    return out


def config_for(fig):
    """Normalised retreat settings for fig, or None when it has none."""
    mode = fig.mode
    if hasattr(mode, "_retreat_cfg"):
        return mode._retreat_cfg
    cfg = None
    char = getattr(mode, "character", None)
    if char:
        raw = (char.get("_fxkit") or {}).get("retreat") or char.get("tactical_retreat")
        if isinstance(raw, dict):
            n = normalize(raw)
            if n.get("enabled") and n["conditions"]:
                cfg = n
    mode._retreat_cfg = cfg
    return cfg


class RetreatState:
    __slots__ = ("active", "mode", "ticks_left", "elapsed", "heading", "back",
                 "cooldown_until", "hp_fired")

    def __init__(self):
        self.active = False
        self.mode = "avoid"
        self.ticks_left = None      # None = no limit
        self.elapsed = 0
        self.heading = 0.0
        self.back = (1.0, 0.0)
        self.cooldown_until = 0
        self.hp_fired = set()


def _ticks(ms):
    ms = float(ms)
    if ms < 0:
        return None
    return max(1, int(round(ms / config.TICK_MS)))


def _target(world, fig):
    """(x, y, facing_left or None) of the thing this figure fights."""
    if world.battle_mode and world.partner_figures:
        best, bi = None, 0
        for i, pf in enumerate(world.partner_figures):
            d = (pf[0] - fig.x) ** 2 + (pf[1] - fig.y) ** 2
            if best is None or d < best:
                best, bi = d, i
        pf = world.partner_figures[bi]
        facing = getattr(world, "partner_facing", None) or []
        return pf[0], pf[1], (facing[bi] if bi < len(facing) else None)
    cx, cy = world.cursor
    return cx, cy, None


def _hp_pct(fig):
    p = fig.personality
    return 100.0 * p.hp / max(1e-6, p.max_hp)


def _cond_true(fig, st, c, world):
    t = c["type"]
    if t == "hp_below":
        pct = float(c.get("pct", 50))
        if _hp_pct(fig) > pct:
            return False
        return bool(c.get("repeat")) or pct not in st.hp_fired
    if t == "projectile_count":
        return len(getattr(world, "enemy_shots", None) or []) >= max(1, int(c.get("count", 5)))
    return False


def _triggered(fig, st, cfg, world):
    res = [_cond_true(fig, st, c, world) for c in cfg["conditions"]]
    return all(res) if cfg.get("logic") == "all" else any(res)


def _can_start(fig):
    c = fig.combat
    # Never cut into an ultimate / stance that owns the figure.
    return not (c.vc_phase or c.sp_phase or c.lb_phase
                or c.blinkstorm_strikes_left > 0)


def _start(fig, st, cfg, world, tx, ty, tface):
    st.active = True
    st.mode = "reengage" if cfg.get("mode") == "reengage" else "avoid"
    st.ticks_left = _ticks(cfg["reengage_duration_ms"] if st.mode == "reengage"
                           else cfg["avoid_duration_ms"])
    st.elapsed = 0
    a_t = math.atan2(ty - fig.y, tx - fig.x)
    st.heading = a_t + math.radians(float(cfg.get("angle_deg") or 0))
    if tface is None:
        # No facing (Solo cursor): the back is the far side from the fighter.
        bx, by = tx - fig.x, ty - fig.y
        d = math.hypot(bx, by)
        st.back = (bx / d, by / d) if d > 0.001 else (1.0, 0.0)
    else:
        # Opposite the way the target faces.
        st.back = (1.0, 0.0) if tface else (-1.0, 0.0)
    for c in cfg["conditions"]:
        if c["type"] == "hp_below" and _hp_pct(fig) <= float(c.get("pct", 50)):
            st.hp_fired.add(float(c.get("pct", 50)))
    # The dash takes over from any melee move in progress.
    c = fig.combat
    c.dashing = c.rebounding = c.slashing = False
    c.arc_repositioning = c.arc_recoiling = False
    c.dodge_dashing = c.dodge_counter = c.dodge_interrupt = False
    c.combo_delay_ticks = 0
    c.followup_pending = 0


def _end(st, cfg, now):
    st.active = False
    st.cooldown_until = now + int(max(0.0, float(cfg.get("cooldown_ms") or 0)) / config.TICK_MS)


def _attack_radius(fig):
    return float(config.MODE_CONFIGS.get(fig.mode.key, {}).get(
        "basic_attack_radius", config.SLASH_RADIUS)) * fig.mode.body_scale()


def _strike(fig, world, tx, ty):
    """Re-engage arrived behind the target: attack now (attack mode only)."""
    if not getattr(world, "shoot_mode", True):
        return
    from . import actions, combat
    if actions.is_image(fig):
        actions.force_attack(fig, world)
        return
    if fig.mode.uses_melee():
        c, m = fig.combat, fig.motion
        cc = combat.combo_cfg(fig)
        dx, dy = tx - fig.x, ty - fig.y
        d = math.hypot(dx, dy)
        lspd = m.speed * cc['dash_speed_mult']
        ux, uy = (dx / d, dy / d) if d > 0.001 else ((-1.0 if fig.transform.facing_left else 1.0), 0.0)
        c.attack_hits = 0
        c.slash_vx, c.slash_vy = ux * lspd, uy * lspd
        c.slash_dist_budget = max(d * 4.0, lspd * 2.0)
        c.dashing = True
        c.rebounding = False
    # Shooters: their next shot comes on their normal cadence.


def _steer(fig, world, proximity, include_target, tx, ty):
    """Push-away vector from harm within `proximity` px (0 when none)."""
    px = py = 0.0
    if proximity <= 0:
        return px, py
    threats = [(s.x, s.y) for s in (getattr(world, "enemy_shots", None) or [])]
    if include_target:
        threats.append((tx, ty))
    for (hx, hy) in threats:
        dx, dy = fig.x - hx, fig.y - hy
        d = math.hypot(dx, dy)
        if d >= proximity:
            continue
        w = 1.0 - d / proximity
        if d > 0.001:
            px += dx / d * w
            py += dy / d * w
        else:
            px += w
    return px, py


def _around_target(fig, tx, ty, gx, gy, stand):
    """Re-engage: go round the target's body, not through it.  Near the
    target, add a push along the tangent on the side of the back point (and
    out, when inside the clearance), so a straight line to the back point
    curls round the target instead of bouncing off it."""
    rx, ry = fig.x - tx, fig.y - ty
    d = math.hypot(rx, ry)
    clear = stand + 25.0
    if d >= clear * 1.6:
        return 0.0, 0.0
    if d < 0.001:
        rx, ry, d = 1.0, 0.0, 1.0
    ux, uy = rx / d, ry / d
    # Only when the back point lies on the far side of the target.
    if (gx - tx) * ux + (gy - ty) * uy > 0.5 * stand:
        return 0.0, 0.0
    t1 = (-uy, ux)
    if t1[0] * (gx - fig.x) + t1[1] * (gy - fig.y) < 0:
        t1 = (uy, -ux)
    w = max(0.0, min(1.0, 1.0 - (d - clear) / (clear * 0.6)))
    out = 1.0 if d < clear else 0.0
    return (t1[0] * 2.0 + ux * out) * w, (t1[1] * 2.0 + uy * out) * w


def _turn_toward(a, b, lim):
    da = (b - a + math.pi) % (2 * math.pi) - math.pi
    return a + max(-lim, min(lim, da))


def tick(fig, world):
    """One tick.  True while the retreat moves the figure this tick (the
    caller then skips the melee FSM and MotionSystem for it)."""
    cfg = config_for(fig)
    if cfg is None:
        return False
    st = fig.retreat
    if st is None:
        st = RetreatState()
        fig.retreat = st
    now = world.global_tick
    tx, ty, tface = _target(world, fig)
    if not st.active:
        if now < st.cooldown_until or not _can_start(fig) or not _triggered(fig, st, cfg, world):
            return False
        _start(fig, st, cfg, world, tx, ty, tface)

    # Duration (the time runs through knockback too).
    st.elapsed += 1
    if st.ticks_left is not None:
        st.ticks_left -= 1
        if st.ticks_left < 0:
            _end(st, cfg, now)
            return False
    m = fig.motion
    if m.bouncing or m.bounce_ending:
        return False          # a knockback always moves the fighter

    from . import ai, combat
    t = fig.transform
    dt = config.TICK_MS / 1000.0
    curve = math.radians(float(cfg.get("curve_deg_s") or 0))
    a_t = math.atan2(ty - fig.y, tx - fig.x)
    if st.mode == "avoid":
        # Target-relative angle, bent further by the curve over time.
        want = a_t + math.radians(float(cfg.get("angle_deg") or 0)) + curve * st.elapsed * dt
        include_target = True
    else:
        bs = fig.mode.body_scale()   # character scale: distances in proportion
        arrive = ARRIVE_PX * bs
        stand = max(arrive, min(BACK_STANDOFF_PX * bs, _attack_radius(fig) * 0.5))
        gx, gy = tx + st.back[0] * stand, ty + st.back[1] * stand
        if math.hypot(gx - fig.x, gy - fig.y) <= arrive:
            _end(st, cfg, now)
            _strike(fig, world, tx, ty)
            return False
        a_g = math.atan2(gy - fig.y, gx - fig.x)
        if curve == 0:
            want = a_g
        else:
            st.heading = _turn_toward(st.heading, a_g, abs(curve) * dt)
            want = st.heading
        include_target = False

    hx, hy = math.cos(want), math.sin(want)
    if st.mode == "reengage":
        ox_, oy_ = _around_target(fig, tx, ty, gx, gy, stand)
        hx, hy = hx + ox_, hy + oy_
    sx, sy = _steer(fig, world, float(cfg.get("proximity_px") or 0) * fig.mode.body_scale(), include_target, tx, ty)
    wx, wy = ai._wall_repulsion(fig)
    wn = max(1e-6, float(config.WALL_PUSH))
    vx = hx + sx * STEER_WEIGHT + wx / wn
    vy = hy + sy * STEER_WEIGHT + wy / wn
    vm = math.hypot(vx, vy)
    if vm < 1e-6:
        vx, vy, vm = hx, hy, 1.0
    sf = combat.position_speed_scale(fig.x, fig.y, fig.screen_w, fig.screen_h)
    spd = m.speed * max(0.0, float(cfg.get("speed_pct") or 0)) / 100.0 * sf
    ox, oy = t.x, t.y
    t.x += vx / vm * spd
    t.y += vy / vm * spd
    if st.elapsed % 2 == 0:
        combat.spawn_afterimage(fig)
    fig.face(ox, oy)
    combat._apply_trail_update(fig, t, True, False)
    fig.render.is_moving = True
    fig.render.advance()
    return True


def reset(fig):
    fig.retreat = None
