"""
Battle AI — how a figure decides where to move while fighting, and what a hit
does to it.  All the old `behavior_mode == 1` branches are gone: temperament is
read from the figure's mode predicates (`charges_full`, `retreats`,
`wander_blend`) and its `Personality` component.
"""

import math

from . import config


def apply_hp_damage(fig, world):
    """Deduct 1 HP from fig and signal quit when HP reaches 0.

    Safe to call from any system.  Returns True if the figure just died.
    Also triggers the runner ultimate when HP first drops to/below 50 % of max.
    """
    p = fig.personality
    was_above = p.hp > int(p.max_hp * config.ULTIMATE_HP_THRESHOLD)
    p.hp -= 1
    if p.hp <= 0:
        p.hp = 0
        world.request_quit()
        return True
    # Trigger runner ultimate on the tick HP crosses the 50 % threshold.
    if (was_above
            and p.hp <= int(p.max_hp * config.ULTIMATE_HP_THRESHOLD)
            and fig.mode.can_shoot()
            and not fig.mode.uses_melee()
            and p.ultimate_ticks <= 0):
        p.ultimate_ticks = config.ULTIMATE_DURATION_TICKS
    return False


def battle_hit(fig, proj_vx, proj_vy, world=None):
    """An enemy projectile struck `fig`: launch it along the bullet's velocity.
    Launch force is the figure's current hit_power, which grows per strike.

    Shooters (can_shoot + not uses_melee) cycle through a knockback window:
      • First KNOCKBACK_LIMIT hits  → normal knockback
      • Next  IMMUNITY_HIT_LIMIT hits → absorbed (no bounce), then reset
      • Repeats indefinitely

    `world` is optional; when provided, HP is decremented on every real hit.
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
                apply_hp_damage(fig, world)
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
        apply_hp_damage(fig, world)


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

