"""
Battle AI — how a figure decides where to move while fighting, and what a hit
does to it.  All the old `behavior_mode == 1` branches are gone: temperament is
read from the figure's mode predicates (`charges_full`, `retreats`,
`wander_blend`) and its `Personality` component.
"""

import math

from . import config
from . import combat as _combat


# ---------------------------------------------------------------------------
# Activation triggers — evaluates the `activation_triggers` /
# `retrigger_cooldown_ms` schema authored in the FX Creator for
# attack_special / ultimate / special_ability (see
# tools/fx/character_creator.js ACTIVATION_TRIGGER_SEMANTICS for the
# authoring-side contract this mirrors exactly). Pure logic, identical in
# Solo & Battle. NOTE: this decides *whether* an action should fire; wiring
# a fired action into the actual animation/fx_layers playback for custom
# characters is a separate, not-yet-built pipeline (see ARCHITECTURE notes) —
# today only the swordsman/runner ultimates have a hardcoded playback path.
# ---------------------------------------------------------------------------
def _ensure_trigger_state(p):
    """Per-figure bookkeeping dict, keyed by action name. Lives on
    Personality since it's already the per-figure "brain" bag."""
    st = getattr(p, "trigger_state", None)
    if st is None:
        st = {}
        p.trigger_state = st
    return st


def _trigger_action_state(p, action_key):
    st = _ensure_trigger_state(p)
    s = st.get(action_key)
    if s is None:
        s = dict(impact_count=0, hit_count=0, hp_fired=set(),
                  next_ok_tick=0, hp_cooldown_until=0)
        st[action_key] = s
    return s


def note_impact_taken(fig):
    """Call whenever fig takes a hit (from apply_hp_damage/battle_hit) — feeds
    on_impact/after_on_impact triggers for every one of this character's
    tracked actions. Identical in Solo & Battle (both call the same hit hooks)."""
    st = _ensure_trigger_state(fig.personality)
    for s in st.values():
        s["impact_count"] += 1


def note_hit_landed(fig):
    """Call whenever fig lands a hit on the enemy — feeds after_on_hit
    triggers. NOTE: in Battle mode a landed hit currently only updates local
    state; crediting it correctly needs the same IPC treatment as HP damage
    (partner_figures), which is not yet wired — see ARCHITECTURE notes."""
    st = _ensure_trigger_state(fig.personality)
    for s in st.values():
        s["hit_count"] += 1


def evaluate_activation_triggers(action, fig, dist_to_enemy, now_tick):
    """True if `action` (a pb_character action dict carrying
    activation_triggers/retrigger_cooldown_ms) should fire right now.

    Any enabled trigger type firing is enough (OR logic). hp_threshold fires
    once per crossing unless repeatable=True, in which case it can refire on
    its own cooldown_ms. after_on_impact/after_on_hit counters reset to 0 the
    moment they fire (on_impact is equivalent to after_on_impact count=1).
    radius_proximity is a closed [min, max] px band. retrigger_cooldown_ms is
    a shared minimum gap between activations of this action regardless of
    which trigger fired it.
    """
    triggers = action.get("activation_triggers") or []
    if not triggers:
        return False
    action_key = action.get("_key", id(action))
    state = _trigger_action_state(fig.personality, action_key)
    if now_tick < state.get("next_ok_tick", 0):
        return False

    p = fig.personality
    hp_pct = (100.0 * p.hp / p.max_hp) if p.max_hp else 0.0
    fired = False
    for trig in triggers:
        ttype = trig.get("type")
        if ttype == "hp_threshold":
            pct = trig.get("pct", 50)
            if hp_pct <= pct:
                if trig.get("repeatable"):
                    if now_tick >= state.get("hp_cooldown_until", 0):
                        cd_ms = trig.get("cooldown_ms", 0) or 0
                        state["hp_cooldown_until"] = now_tick + int(cd_ms / config.TICK_MS)
                        fired = True
                elif pct not in state["hp_fired"]:
                    state["hp_fired"].add(pct)
                    fired = True
        elif ttype == "on_impact":
            if state["impact_count"] > 0:
                state["impact_count"] = 0
                fired = True
        elif ttype == "after_on_impact":
            if state["impact_count"] >= trig.get("count", 1):
                state["impact_count"] = 0
                fired = True
        elif ttype == "after_on_hit":
            if state["hit_count"] >= trig.get("count", 1):
                state["hit_count"] = 0
                fired = True
        elif ttype == "radius_proximity":
            lo, hi = trig.get("min", 0), trig.get("max", float("inf"))
            if lo <= dist_to_enemy <= hi:
                fired = True
        if fired:
            break

    if fired:
        cooldown_ms = action.get("retrigger_cooldown_ms", 0) or 0
        if cooldown_ms:
            state["next_ok_tick"] = now_tick + int(cooldown_ms / config.TICK_MS)
    return fired


def apply_hp_damage(fig, world, amount=1):
    """Deduct `amount` HP from fig (default 1, the historical flat per-hit
    value every built-in attack still uses) and signal quit when HP reaches
    0. JSON-character attacks pass their own fx_layer battle.damage here
    (see combat.fire_character_action / ipc projectile damage field).

    Safe to call from any system.  Returns True if the figure just died.
    Also triggers the runner ultimate when HP first drops to/below 30% of max,
    and the swordsman ultimate when HP first drops to/below 50% of max.
    """
    p = fig.personality
    note_impact_taken(fig)
    was_above_runner = p.hp > int(p.max_hp * config.ULTIMATE_HP_THRESHOLD)
    p.hp -= amount
    if p.hp <= 0:
        p.hp = 0
        world.request_quit()
        return True
    # Trigger runner ultimate and survival teleport on the tick HP crosses
    # the threshold.
    if (was_above_runner
            and p.hp <= int(p.max_hp * config.ULTIMATE_HP_THRESHOLD)
            and fig.mode.can_shoot()
            and not fig.mode.uses_melee()
            and p.ultimate_ticks <= 0):
        p.ultimate_ticks = config.ULTIMATE_DURATION_TICKS
        # Arm the first teleport immediately (fires on the very next tick).
        p.teleport_ticks = 0
    # Trigger the crescent ultimate at each of this figure's own thresholds
    # (config.ULTC_THRESHOLDS for Swordsman; a JSON character's own
    # ultimate_playback.thresholds if it set one). Each threshold fires
    # exactly once per life. Only figures whose ultimate_style is 'crescent'
    # get this trigger — a JSON melee character can opt into 'beam' or
    # 'none' instead via ultimate_playback.style.
    if fig.mode.uses_melee() and _combat.ultimate_style(fig) == "crescent":
        if world.battle_mode and world.partner_figures:
            tx, ty = world._nearest_enemy(fig.x, fig.y)
        else:
            tx, ty = world.cursor
        for thresh in _combat.ultc_cfg(fig)['thresholds']:
            if thresh not in p.sword_ult_fired_thresholds:
                threshold_hp = int(p.max_hp * thresh)
                if p.hp <= threshold_hp:
                    p.sword_ult_fired_thresholds.add(thresh)
                    _combat.fire_sword_ultimate(fig, tx, ty)
    return False


def battle_hit(fig, proj_vx, proj_vy, world=None, amount=1):
    """An enemy projectile struck `fig`: launch it along the bullet's velocity.
    Launch force is the figure's current hit_power, which grows per strike.

    Shooters (can_shoot + not uses_melee) cycle through a knockback window:
      • First KNOCKBACK_LIMIT hits  → normal knockback
      • Next  IMMUNITY_HIT_LIMIT hits → absorbed (no bounce), then reset
      • Repeats indefinitely

    `world` is optional; when provided, HP is decremented on every real hit,
    by `amount` (default 1 — the flat per-hit value every built-in bullet
    still uses; JSON-character bullets pass their own battle.damage).
    """
    speed = (proj_vx * proj_vx + proj_vy * proj_vy) ** 0.5
    if speed < 0.001:
        return
    p = fig.personality
    m = fig.motion

    # --- Shooter knockback cycling ---
    if fig.mode.can_shoot() and not fig.mode.uses_melee():
        if p.knockback_count >= config.KNOCKBACK_LIMIT:
            # Immune phase: absorb this hit, then check if window is exhausted.
            p.immunity_hits += 1
            if p.immunity_hits >= config.IMMUNITY_HIT_LIMIT:
                p.knockback_count = 0
                p.immunity_hits = 0
            # HP still decreases even during immunity
            if world is not None:
                apply_hp_damage(fig, world, amount)
            return  # no bounce this hit
        else:
            p.knockback_count += 1  # consume one knockback slot

    # --- Apply knockback ---
    p.hit_power = min(config.HIT_POWER_MAX, p.hit_power + config.HIT_POWER_STEP)
    scale = p.hit_power / speed
    nvx, nvy = proj_vx * scale, proj_vy * scale
    if m.bouncing:
        m.bounce_vx += nvx * 0.5      # already airborne — add impulse
        m.bounce_vy += nvy * 0.5
    else:
        m.bounce_vx, m.bounce_vy = nvx, nvy
        m.bouncing = True

    if world is not None:
        apply_hp_damage(fig, world, amount)


def battle_target(world, fig):
    """Movement target this tick, blending enemy position with wander, daze,
    retreat, and soft wall repulsion."""
    t = fig.transform
    p = fig.personality
    m = fig.motion
    rng = p.rng

    # --- Daze: wander aimlessly after recovering from a hit ---
    if p.daze_ticks > 0:
        p.daze_ticks -= 1
        if p.daze_ticks == 0:
            p.hit_power = max(config.HIT_POWER_BASE, p.hit_power * 0.5)
        p.wander_angle += p.wander_sign * p.wander_drift * rng.uniform(0.5, 2.0)
        return (t.x + math.cos(p.wander_angle) * 80,
                t.y + math.sin(p.wander_angle) * 80)

    # Trigger a daze the moment a knockback bounce finishes settling.
    if m.bounce_ending and m.bounce_end_ticks == 1:
        p.daze_ticks = rng.randint(*config.DAZE_TICKS_RANGE)

    ex, ey = world._nearest_enemy(t.x, t.y)
    dx, dy = ex - t.x, ey - t.y
    dist = (dx * dx + dy * dy) ** 0.5

    # --- Retreat: back away briefly when close and timid ---
    if p.retreat_ticks > 0:
        p.retreat_ticks -= 1
        if dist > 0.1:
            return (t.x - dx / dist * 60, t.y - dy / dist * 60)
    if (dist < 120 and p.retreat_ticks == 0 and fig.mode.retreats()
            and rng.random() < (1.0 - p.aggression) * 0.04):
        p.retreat_ticks = rng.randint(*config.RETREAT_TICKS_RANGE)

    # --- Wander: drift the chase angle laterally, blending out as it closes ---
    p.wander_angle += p.wander_sign * p.wander_drift * rng.gauss(0, 1)
    if rng.random() < 0.008:
        p.wander_sign = -p.wander_sign
    blend = fig.mode.wander_blend(dist, p.wander_strength)

    if dist > 0.1:
        bax, bay = dx / dist, dy / dist
        perp_x, perp_y = -bay, bax
        wx, wy = math.cos(p.wander_angle), math.sin(p.wander_angle)
        lat = wx * perp_x + wy * perp_y
        fx = bax + perp_x * lat * blend
        fy = bay + perp_y * lat * blend
        mag = (fx * fx + fy * fy) ** 0.5
        if mag > 0.001:
            fx /= mag
            fy /= mag
        eff = dist * (1.0 if fig.mode.charges_full() else p.aggression)
        tx, ty = t.x + fx * eff, t.y + fy * eff
    else:
        tx, ty = ex, ey

    rx, ry = _wall_repulsion(fig)
    return (tx + rx, ty + ry)


def _wall_repulsion(fig):
    """Cubic-falloff nudge back toward centre within WALL_ZONE px of an edge."""
    t = fig.transform
    z, push = config.WALL_ZONE, config.WALL_PUSH
    rx = ry = 0.0
    dl, dr = t.x, fig.screen_w - t.x
    dt_, db = t.y, fig.screen_h - t.y
    if dl < z:
        k = 1.0 - dl / z; rx += k * k * k * push
    if dr < z:
        k = 1.0 - dr / z; rx -= k * k * k * push
    if dt_ < z:
        k = 1.0 - dt_ / z; ry += k * k * k * push
    if db < z:
        k = 1.0 - db / z; ry -= k * k * k * push
    return rx, ry




