"""
Systems — the ordered pipeline that runs every tick.

`Overlay._tick`'s old 340-line body is now a list of `System` objects.  Each
system does one job over the whole world; a cross-cutting feature is a new
system inserted into the list, not edits sprinkled across a monolith.

Pipeline order (run once per fielded side each tick — see app.py):
    CombatSystem -> MotionSystem -> CollisionSystem -> ProjectileSystem
InputSystem runs once per tick, outside the per-side loop.  Combat runs
before motion so a mid-attack figure moves there and the motion system skips
it (`fig.combat.busy`).  Rendering is NOT a system — Qt requires it inside
paintEvent (see app.py).
"""

import math
import random

from . import motion, modes, config, combat, ai
from . import platform_win as win
from . import action_log



def _spawn_bullet_burst(world, x, y, r, g, b):
    """Particle burst for a bullet impact that reduced the target's HP.

    Small expanding ring + sparks in the bullet's colour.  NOT spawned for
    blocked (parried) bullets — those ricochet without bursting.
    """
    world.impact_rings.append([x, y, 0, config.BULLET_BURST_RING_RADIUS])
    for _ in range(config.BULLET_BURST_SPARKS):
        ang = random.uniform(0.0, 2.0 * math.pi)
        spd = random.uniform(*config.IMPACT_SPARK_SPEED)
        world.sparks.append([x, y, math.cos(ang) * spd, math.sin(ang) * spd,
                             0, r, g, b])


class System:
    """One unit of per-tick behaviour over the world."""
    def update(self, world):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------
class InputSystem(System):
    """Edge-detected hotkey handling. Holds its own previous-key state."""

    def __init__(self):
        self.prev = {}

    def _pressed(self, vk):
        """True only on the rising edge (key was up last tick, down now)."""
        now = win.key_down(vk)
        was = self.prev.get(vk, False)
        self.prev[vk] = now
        return now and not was

    def update(self, world):
        ctrl = win.key_down(win.VK_CTRL)
        alt = win.key_down(win.VK_ALT)

        # Quit: Ctrl+Alt+Enter
        if ctrl and alt and win.key_down(win.VK_ENTER):
            world.request_quit()
            return

        if self._pressed(win.VK_F9):
            world.runner_on = not world.runner_on

        # 1 / 2: cycle P1's / P2's character.  P1 wraps through every
        # registered character; P2 cycles through them and then OFF (side
        # cleared — battle ends), tap again to re-field.
        if self._pressed(win.VK_1):
            world.cycle_side_char(0)
        if self._pressed(win.VK_2):
            world.cycle_side_char(1)
        if self._pressed(win.VK_F7):
            world.add_figure()
        if self._pressed(win.VK_F8):
            world.remove_figure()

        # Ctrl-combos: track whether Ctrl was used as a modifier this hold, so a
        # plain Ctrl tap toggles collision while Ctrl+Q / Ctrl+R do their thing.
        q_edge = self._pressed(win.VK_Q)
        r_edge = self._pressed(win.VK_R)
        if ctrl and q_edge:
            world.path_follow = not world.path_follow
            world.ctrl_used = True
        if ctrl and r_edge:
            world.runaway = not world.runaway
            world.ctrl_used = True

        ctrl_edge_down = ctrl and not world._ctrl_prev
        ctrl_edge_up = world._ctrl_prev and not ctrl
        if ctrl_edge_down:
            world.ctrl_used = False
        elif ctrl_edge_up and not world.ctrl_used:
            world.collision_on = not world.collision_on
        world._ctrl_prev = ctrl

        # Alt+Up: toggle attack/shoot for all modes
        if alt and self._pressed(win.VK_UP):
            world.toggle_shoot_mode()

        # Alt+Left / Alt+Right: cycle behaviour mode
        if alt:
            if self._pressed(win.VK_LEFT):
                world.cycle_mode(-1)
            if self._pressed(win.VK_RIGHT):
                world.cycle_mode(+1)


# ---------------------------------------------------------------------------
# Motion
# ---------------------------------------------------------------------------
class MotionSystem(System):
    """Moves every non-attacking figure toward its target, then clamps walls."""

    def update(self, world):
        if not world.runner_on:
            return
        battle = world.battle_mode and world.partner_figures
        for fig in world.figures:
            if fig.combat.acted:
                continue  # combat system already advanced this figure this tick

            # --- Runner survival teleport (active while HP <= 30% threshold) ---
            # Works in both solo (target = cursor) and battle (target = nearest enemy).
            # Teleport is a pure position warp — it does NOT set combat.acted, so
            # ProjectileSystem fires on the same tick uninterrupted.
            p = fig.personality
            _char = getattr(fig.mode, "character", None)
            if (fig.mode.can_shoot()
                    and not fig.mode.uses_melee()
                    and not (_char and _char.get("disable_survival_teleport"))
                    and p.hp <= int(p.max_hp * config.ULTIMATE_HP_THRESHOLD)):
                if p.teleport_ticks <= 0:
                    # Compute destination: 100px behind the runner relative to target.
                    # "Behind" = opposite of the runner's current facing direction,
                    # so the runner always lands on the far side of the target from
                    # where it was.
                    if battle:
                        tx, ty = world._nearest_enemy(fig.x, fig.y)
                    else:
                        tx, ty = world.cursor
                    # Vector from target → runner (runner's current outward direction)
                    dx, dy = fig.x - tx, fig.y - ty
                    dist = (dx * dx + dy * dy) ** 0.5
                    if dist > 0.001:
                        nx, ny = dx / dist, dy / dist
                    else:
                        nx, ny = 1.0, 0.0
                    # Land TELEPORT_DISTANCE_PX behind the runner from the target's POV
                    # i.e. further away in the same outward direction.
                    new_x = tx + nx * config.TELEPORT_DISTANCE_PX
                    new_y = ty + ny * config.TELEPORT_DISTANCE_PX
                    # Clamp to screen bounds
                    margin = 20.0
                    new_x = max(margin, min(fig.screen_w - margin, new_x))
                    new_y = max(margin, min(fig.screen_h - margin, new_y))
                    fig.transform.x = new_x
                    fig.transform.y = new_y
                    p.teleport_ticks = config.TELEPORT_INTERVAL_TICKS
                else:
                    p.teleport_ticks -= 1

            # --- Approach blink (blink characters, JSON `blink.approach`) ---
            # Proactive gap-closer: when far from the combat target and off
            # cooldown, warp approach_range_px toward it.  Pure position
            # warp (no combat.acted), reuses p.teleport_ticks as its
            # cooldown (the runner survival path above is shooter-gated, a
            # melee blink character never collides with it).  Identical in
            # Solo (target = cursor) and Battle (target = nearest enemy).
            bl = combat.blink_cfg(fig)
            if (bl is not None and bl['approach']
                    and fig.mode.uses_melee()
                    and not fig.combat.busy
                    and not fig.motion.bouncing
                    and not fig.motion.bounce_ending):
                if p.teleport_ticks <= 0:
                    if battle:
                        tx, ty = world._nearest_enemy(fig.x, fig.y)
                    else:
                        tx, ty = world.cursor
                    dxa, dya = tx - fig.x, ty - fig.y
                    dista = (dxa * dxa + dya * dya) ** 0.5
                    if dista > bl['approach_trigger_px']:
                        inv = 1.0 / dista
                        hop = min(bl['approach_range_px'],
                                  dista - bl['approach_trigger_px'] * 0.5)
                        combat.blink_warp(fig,
                                          fig.x + dxa * inv * hop,
                                          fig.y + dya * inv * hop)
                        p.teleport_ticks = bl['approach_cooldown_ticks']
                else:
                    p.teleport_ticks -= 1

            tx_motion, ty_motion = world.movement_target(fig)
            _char = getattr(fig.mode, "character", None)
            if _char and _char.get("stationary"):
                # Generic opt-out (JSON `stationary: true`): zero locomotion
                # (no chase/wander/kite), but still turns to face the target
                # and animates/attacks normally — combat firing is handled
                # entirely by ProjectileSystem/CombatSystem, unaffected by
                # this. Identical in Solo & Battle; tx_motion/ty_motion are
                # computed the same way for every figure above.
                dx = tx_motion - fig.x
                if dx < -0.001:
                    fig.transform.facing_left = True
                elif dx > 0.001:
                    fig.transform.facing_left = False
                fig.render.is_moving = False
                fig.render.advance()
                continue
            if battle:
                motion.update(fig, tx_motion, ty_motion, False, False, False)
            else:
                hit = motion.update(fig, tx_motion, ty_motion, world.collision_on,
                                    world.path_follow, world.runaway)
                if hit is not None:
                    world.collision_dots.append([hit[0], hit[1], 0])
                    # Solo mode cursor bounce costs 1 HP — unless parrying
                    if not fig.combat.parrying:
                        ai.apply_hp_damage(fig, world)
        for fig in world.figures:
            motion.check_walls(fig)
        # Battle-only invisible oval arena boundary — confirmed intentional
        # Solo/Battle exception (Solo: no arena wall; Battle: active). See
        # motion.apply_arena_oval docstring for rationale.
        if battle:
            for fig in world.figures:
                motion.apply_arena_oval(fig, world)


# ---------------------------------------------------------------------------
# Staged systems — registered into the pipeline as each stage lands.
# They are no-ops today so the pipeline shape is final and visible now.
# ---------------------------------------------------------------------------
class CombatSystem(System):
    """Advances the swordsman attack FSM for every melee figure and records
    whether it consumed the tick (so MotionSystem can skip those figures)."""

    def update(self, world):
        for fig in world.figures:
            combat.update_petals(fig, world)   # ambient defensive FX — all archetypes, always ticks
            combat.update_character_bursts(fig)  # cosmetic particle-burst FX, all archetypes
            combat.update_sprite_emitter(fig)  # sprite-line emitter FX (JSON sprite_emitter), all archetypes
            combat.check_hpt_clone_spawns(fig, world)  # HP-threshold stationary clones, all archetypes
            # Parry cooldown/stance ticks for ANY archetype that can deflect
            # (swordsman via uses_melee(), or a JSON character whose `defend`
            # action authors a can_hit+deflect layer — combat.has_defend_deflect).
            if fig.mode.uses_melee() or combat.has_defend_deflect(fig):
                combat.tick_parry_cooldown(fig)
            # --- Generic proximity reaction (JSON `reaction`): counter/dodge
            # roll + charge-based vanish-cut launch. Runs before
            # advance_combat so an armed retaliation dash executes this
            # same tick. No-op for characters without the block. ---
            combat.check_reaction(fig, world)
            # --- Vanish-cut strike bullets -> live projectile list (same
            # standard fire -> snapshot channel the clones use). ---
            if fig.combat.vc_shots_pending:
                world.projectiles.extend(fig.combat.vc_shots_pending)
                fig.combat.vc_shots_pending = []
            # --- Blink crackle FX: drain warp endpoints into world sparks ---
            if fig.combat.blink_fx_pending:
                bl_cfg = combat.blink_cfg(fig)
                bolt_hex = bl_cfg.get("bolt_color") if bl_cfg else ""
                if bolt_hex:
                    rr, gg, bb = combat._hex_to_rgb(bolt_hex, fig.lut[200])
                else:
                    rr, gg, bb = fig.lut[200]
                rng = fig.personality.rng
                for (x0, y0, x1, y1) in fig.combat.blink_fx_pending:
                    # Crackle bursts at both warp endpoints.
                    for (bx, by) in ((x0, y0), (x1, y1)):
                        for _ in range(config.BLINK_FX_SPARKS):
                            ang = rng.uniform(0.0, 2.0 * math.pi)
                            spd = rng.uniform(*config.BLINK_FX_SPARK_SPEED)
                            world.sparks.append([bx, by,
                                                 math.cos(ang) * spd,
                                                 math.sin(ang) * spd,
                                                 0, rr, gg, bb])
                    # Jagged electric bolt between the endpoints —
                    # zig-zag spark chain replaces the old trail smear.
                    ddx, ddy = x1 - x0, y1 - y0
                    seg_d = (ddx * ddx + ddy * ddy) ** 0.5
                    if seg_d > 1.0:
                        nx_, ny_ = -ddy / seg_d, ddx / seg_d
                        n_seg = int(config.BLINK_BOLT_SEGMENTS)
                        amp = config.BLINK_BOLT_JITTER_PX
                        for i in range(1, n_seg):
                            f = i / float(n_seg)
                            # alternate sides for the zig-zag read
                            side = 1.0 if (i % 2) else -1.0
                            off = side * rng.uniform(0.35, 1.0) * amp
                            px_ = x0 + ddx * f + nx_ * off
                            py_ = y0 + ddy * f + ny_ * off
                            world.sparks.append([px_, py_,
                                                 rng.uniform(-0.6, 0.6),
                                                 rng.uniform(-0.6, 0.6),
                                                 0, rr, gg, bb])
                fig.combat.blink_fx_pending.clear()
            # --- Clone system: tick autonomous ghosts (preset 'clone') ---
            if fig.combat.clone_cd > 0:
                fig.combat.clone_cd -= 1
            if fig.combat.clones:
                if world.battle_mode and world.partner_figures:
                    ctx, cty = world._nearest_enemy(fig.x, fig.y)
                else:
                    ctx, cty = world.cursor
                live_clones = []
                for cl in fig.combat.clones:
                    res = cl.tick(ctx, cty)
                    if res is None:
                        # Dissolve crackle at the clone's last position.
                        fig.combat.blink_fx_pending.append(
                            (cl.x, cl.y, cl.x, cl.y))
                        continue
                    if res:
                        world.projectiles.extend(res)
                    live_clones.append(cl)
                fig.combat.clones = live_clones
            if not fig.mode.uses_melee():
                fig.combat.acted = False
                continue
            tgt = world.melee_target(fig)
            fig.combat.acted = combat.advance_combat(fig, tgt, world.cursor)

            # --- Slash FX: drain hit events into world FX lists ---
            c = fig.combat
            if c.impact_fx_pending:
                rr, gg, bb = fig.lut[80]
                rng = fig.personality.rng
                for (ix, iy) in c.impact_fx_pending:
                    world.impact_rings.append(
                        [ix, iy, 0, config.IMPACT_RING_RADIUS])
                    for _ in range(config.IMPACT_SPARK_COUNT):
                        ang = rng.uniform(0.0, 2.0 * math.pi)
                        spd = rng.uniform(*config.IMPACT_SPARK_SPEED)
                        world.sparks.append([ix, iy,
                                             math.cos(ang) * spd,
                                             math.sin(ang) * spd,
                                             0, rr, gg, bb])
                c.impact_fx_pending.clear()

            # --- Hit-stop: big hit (string finisher / ultimate) freezes the
            # world.  Both sides share one clock, so attacker and victim
            # freeze together by construction. ---
            if c.hitstop_request:
                c.hitstop_request = False
                world.hitstop_ticks = config.HITSTOP_TICKS

        # HP-threshold stationary clones: orbit/attack + hittability for
        # every clone this side owns (spawn checks already ran per-figure
        # above). Identical in Solo & Battle.
        combat.tick_hpt_clones(world)


def _basic_shot(fig, tx, ty):
    """Basic-attack projectile spawn for the shared shot cadence. JSON
    characters with a per-layer battle attack_normal (see
    combat.fire_character_action) fire their own attack instead of the
    built-in legacy fan shot. Identical in Solo & Battle."""
    char = getattr(fig.mode, "character", None)
    if char and combat._character_action_layers(char, "attack_normal"):
        return combat.fire_character_action(fig, "attack_normal", tx, ty)
    return combat.make_shot(fig.x, fig.y, tx, ty, fig.lut[128])


class ProjectileSystem(System):
    """Spawn, advance, and cull bullets.

    Both battle and non-battle cadences use the same 3-phase cycle for runners:
      Phase 0 — CONE   : 3 clusters in a fan spread
      Phase 1 — ZIGZAG : 2 clusters weaving in opposing sine waves
      Phase 2 — HOMING : 1 cluster that tracks the target at half speed
    After all three phases fire, a SHOT_CYCLE_PAUSE_TICKS pause runs before
    the cycle repeats.  Non-runner shooters use the legacy fan shot in both modes.

    In battle mode the target for each figure is its nearest enemy instead of
    the cursor.  Non-runner (swordsman) figures keep their own per-figure
    randomised cadence with the legacy fan aimed at the nearest enemy.
    """

    def update(self, world):
        if world.runner_on and world.shoot_mode:
            battle = bool(world.battle_mode and world.partner_figures)
            # Fire when in an active battle, or when not in battle mode at all.
            # (battle_mode True with no partner figures yet = hold fire, as before.)
            if battle or not world.battle_mode:
                self._fire(world, battle)

        # JSON-character attack_special/ultimate: evaluated every tick against
        # each action's own activation_triggers, independent of the
        # runner_on/basic-cadence gate above (mirrors mage's radius_proximity
        # attack_special and hp_threshold ultimate). Identical in Solo &
        # Battle — both call the exact same trigger + fire path.
        if world.shoot_mode:
            self._fire_attack_pattern(world)
            self._fire_json_actions(world)

        # Update homing bullet targets — cursor in solo, nearest enemy in battle.
        if world.projectiles:
            if world.battle_mode and world.partner_figures:
                # Point each homing bullet at the nearest enemy to the figure
                # that fired it.  Since we don't track ownership, we use the
                # single nearest enemy position as a shared target — good enough
                # for the current one-vs-one architecture.
                if world.figures:
                    ref_fig = world.figures[0]
                    bx, by = world._nearest_enemy(ref_fig.x, ref_fig.y)
                    combat.update_homing_targets(world.projectiles, bx, by)
            else:
                cx, cy = world.cursor
                combat.update_homing_targets(world.projectiles, cx, cy)

        # Advance + cull (runs every tick).
        # Also checks bullet-vs-cursor (solo) and bullet-vs-figure (both modes).
        if world.projectiles:
            cx, cy = world.cursor
            alive = []
            _cm = config.OFFSCREEN_CULL_MARGIN
            _sw, _sh = world.screen_w, world.screen_h
            for proj in world.projectiles:
                proj.update()
                _beam_diag = (proj.style == "beam")
                if not proj.alive:
                    if _beam_diag:
                        action_log.log("BEAM_CULL",
                            f"expired age={proj.age}/{proj.max_age} "
                            f"at=({proj.x:.0f},{proj.y:.0f})")
                    continue
                # Off-screen cull: drop bullets beyond the margin instead of
                # simulating them far off-screen for the rest of PROJ_MAX_AGE.
                if (proj.x < -_cm or proj.x > _sw + _cm
                        or proj.y < -_cm or proj.y > _sh + _cm):
                    if _beam_diag:
                        action_log.log("BEAM_CULL",
                            f"offscreen age={proj.age} "
                            f"at=({proj.x:.0f},{proj.y:.0f})")
                    continue

                # Skip splinters — hit_r_sq == 0.0 means no collision checking
                if proj.hit_r_sq == 0.0:
                    alive.append(proj)
                    continue

                hit = False

                # --- Bullet vs swordsman parry (solo and battle) ---
                # Check before cursor/figure-hit so a parried bullet is erased
                # without dealing damage.  The parry radius is smaller than the
                # dodge radius, so this is only reached by bullets that got past
                # the dodge sidestep.
                # Pierce ignores deflect/parry entirely (see battle.attack.pierce
                # in fx-authoring.md): a piercing shot ignores all things and
                # compels its action, so it never enters the parry check below.
                # Identical in Solo & Battle.
                if not hit and not proj.pierce:
                    parry_rsq = config.PARRY_RADIUS * config.PARRY_RADIUS
                    for fig in world.figures:
                        if not (fig.mode.uses_melee()
                                or combat.has_defend_deflect(fig)):
                            continue
                        # Never parry your OWN bullet — every shot spawns at
                        # its firer's position, inside its own parry radius,
                        # so without this check any shooter with a deflect
                        # defend layer eats each of its own shots at birth
                        # (BEAM_CULL 'parried age=1'). Cross-figure parries
                        # (e.g. solo swordsman parrying runner bullets) keep
                        # working. Identical in Solo & Battle.
                        if proj.owner is fig:
                            continue
                        ddx, ddy = proj.x - fig.x, proj.y - fig.y
                        if ddx * ddx + ddy * ddy <= parry_rsq:
                            # Stance already open: absorb silently, no new crescent
                            if fig.combat.parrying:
                                world.collision_dots.append([proj.x, proj.y, 0])
                                hit = True
                            elif combat.trigger_parry(fig):
                                world.collision_dots.append([proj.x, proj.y, 0])
                                hit = True
                            if hit:
                                if _beam_diag:
                                    action_log.log("BEAM_CULL",
                                        f"parried age={proj.age} "
                                        f"at=({proj.x:.0f},{proj.y:.0f})")
                                # Deflect: the blocked bullet ricochets away in
                                # a random cone (cosmetic, original colour).
                                alive.append(combat.make_deflect_bullet(
                                    fig.x, fig.y, proj.x, proj.y,
                                    proj.vx, proj.vy,
                                    (proj.r, proj.g, proj.b)))
                            break  # only one figure handles the parry per bullet

                # --- Bullet vs cursor (solo and battle) ---
                if not hit:
                    ddx, ddy = proj.x - cx, proj.y - cy
                    if ddx * ddx + ddy * ddy <= proj.hit_r_sq:
                        world.collision_dots.append([proj.x, proj.y, 0])
                        if not proj.pierce:
                            if _beam_diag:
                                action_log.log("BEAM_CULL",
                                    f"cursor-hit age={proj.age} "
                                    f"at=({proj.x:.0f},{proj.y:.0f}) "
                                    f"pierce={proj.pierce}")
                            hit = True

                # --- Bullet vs enemy figures (battle only) ---
                if not hit and world.battle_mode and world.partner_figures:
                    for ex, ey, _edash, eparry in world.partner_figures:
                        ddx, ddy = proj.x - ex, proj.y - ey
                        if ddx * ddx + ddy * ddy <= proj.hit_r_sq:
                            world.collision_dots.append([proj.x, proj.y, 0])
                            if not eparry:
                                # Partner takes the HP loss on their side --
                                # HP-reducing impact, so the bullet bursts.
                                # A parrying partner blocks it: no burst.
                                _spawn_bullet_burst(world, proj.x, proj.y,
                                                    proj.r, proj.g, proj.b)
                            # Pierce (battle.attack.pierce on the fx layer
                            # that fired this shot — see combat.fire_attack_pattern):
                            # register the hit visual/burst same as any other
                            # bullet, but the bullet itself survives and keeps
                            # travelling instead of being destroyed on contact.
                            if not proj.pierce:
                                if _beam_diag:
                                    action_log.log("BEAM_CULL",
                                        f"figure-hit age={proj.age} "
                                        f"at=({proj.x:.0f},{proj.y:.0f}) "
                                        f"pierce={proj.pierce}")
                                hit = True
                            break

                if not hit:
                    alive.append(proj)
            world.projectiles = alive



    def _fire(self, world, battle):
        """Unified firing cadence for BOTH Solo and Battle mode.

        The two modes share one code path; the only differences are:
          * target — nearest enemy (battle) vs cursor (solo)
          * non-runner cadence — per-figure randomised interval (battle) vs
            immediate legacy fan on the shared timer (solo)
        Ultimate, pause, phase-advance, and runner cycle logic are identical.
        """
        tag = "BATTLE " if battle else ""

        def _target(fig):
            return (world._nearest_enemy(fig.x, fig.y) if battle
                    else world.cursor)

        # --- Ultimate: bypass the shared timer and fire every tick ---
        _ultimate_active = any(
            fig.personality.ultimate_ticks > 0
            for fig in world.figures
            if fig.mode.can_shoot() and not fig.mode.uses_melee()
        )
        if _ultimate_active:
            for fig in world.figures:
                p = fig.personality
                if p.ultimate_ticks > 0:
                    p.ultimate_ticks -= 1
            for fig in world.figures:
                if not fig.mode.can_shoot() or fig.personality.ultimate_ticks <= 0:
                    continue
                if combat.ultimate_style(fig) == "beam":
                    # BEAM ULTIMATE: N parallel long-tailed bolts every tick
                    # (N/spacing/trail/age/speed from combat.beam_cfg — Runner's
                    # own numbers by default, or a JSON character's own if it
                    # set ultimate_playback fields). Aim is recomputed at the
                    # live target each tick; bolts already in flight keep
                    # their fixed straight heading.
                    tx, ty = _target(fig)
                    new_projs = combat.make_beam_shot_cfg(fig, tx, ty)
                    world.projectiles.extend(new_projs)
                    rr, gg, bb = fig.lut[128]
                    world.muzzle_flashes.append(
                        [fig.x, fig.y, 0, rr, gg, bb])
            # shot_phase intentionally frozen during the beam; the normal
            # cone/zigzag/homing cycle resumes where it left off afterwards.

        # --- Inter-cycle pause: count down before the next fire ---
        elif world.shot_pause_ticks > 0:
            world.shot_pause_ticks -= 1
            if world.shot_pause_ticks % 15 == 0:
                action_log.log("SHOT_PAUSE",
                    f"{tag}remaining={world.shot_pause_ticks} ticks "
                    f"(next phase will be phase {world.shot_phase})")

        # --- Shared timer: fire one phase of the cycle ---
        else:
            world.shoot_ticks += 1
            if world.shoot_ticks >= config.SHOOT_INTERVAL:
                world.shoot_ticks = 0
                _phase_names = {0: "CONE", 1: "ZIGZAG", 2: "HOMING"}
                action_log.log("SHOT_PHASE",
                    f"{tag}phase={world.shot_phase} "
                    f"({_phase_names.get(world.shot_phase, '?')}) "
                    f"figures={len(world.figures)}")
                for fig in world.figures:
                    if not fig.mode.can_shoot():
                        action_log.log("SHOT_SKIP",
                            f"{tag}mode={fig.mode.key} cannot shoot")
                        continue
                    tx, ty = _target(fig)
                    if fig.mode.key == "runner":
                        new_projs = combat.make_runner_cycle_shot(
                            fig.x, fig.y, tx, ty,
                            fig.lut[128], world.shot_phase)
                        world.projectiles.extend(new_projs)
                        _fr, _fg, _fb = fig.lut[128]
                        world.muzzle_flashes.append(
                            [fig.x, fig.y, 0, _fr, _fg, _fb])
                        action_log.log("SHOT",
                            f"{tag}runner fig=({fig.x:.0f},{fig.y:.0f}) "
                            f"phase={world.shot_phase} "
                            f"target=({tx:.0f},{ty:.0f}) "
                            f"spawned={len(new_projs)} "
                            f"types={[type(pr).__name__ for pr in new_projs]}")
                    elif combat.has_attack_pattern(getattr(fig.mode, "character", None)):
                        # Has its own attack_pattern.cycle — handled entirely
                        # by _fire_attack_pattern's independent per-figure
                        # cadence below; skip here to avoid double-firing.
                        continue
                    elif battle:
                        # Battle non-runner: per-figure randomised cadence.
                        p = fig.personality
                        p.shoot_tick += 1
                        if p.shoot_tick >= p.battle_shoot_interval:
                            p.shoot_tick = 0
                            p.battle_shoot_interval = p.rng.randint(
                                *config.SHOOT_INTERVAL_RANGE)
                            new_projs = _basic_shot(fig, tx, ty)
                            world.projectiles.extend(new_projs)
                            _fr, _fg, _fb = fig.lut[128]
                            world.muzzle_flashes.append(
                                [fig.x, fig.y, 0, _fr, _fg, _fb])
                            action_log.log("SHOT",
                                f"{tag}non-runner mode={fig.mode.key} "
                                f"fig=({fig.x:.0f},{fig.y:.0f}) "
                                f"target=({tx:.0f},{ty:.0f}) "
                                f"count={len(new_projs)}")
                    else:
                        # Solo non-runner: legacy fan on the shared timer.
                        new_projs = _basic_shot(fig, tx, ty)
                        world.projectiles.extend(new_projs)
                        _fr, _fg, _fb = fig.lut[128]
                        world.muzzle_flashes.append(
                            [fig.x, fig.y, 0, _fr, _fg, _fb])
                        action_log.log("SHOT",
                            f"{tag}non-runner mode={fig.mode.key} "
                            f"fig=({fig.x:.0f},{fig.y:.0f}) "
                            f"spawned={len(new_projs)} legacy-fan projs")
                # Advance phase; insert pause after the final phase.
                prev_phase = world.shot_phase
                world.shot_phase = (world.shot_phase + 1) % 3
                if world.shot_phase == 0:
                    world.shot_pause_ticks = config.SHOT_CYCLE_PAUSE_TICKS
                    action_log.log("SHOT_PAUSE",
                        f"{tag}cycle complete after phase {prev_phase} — "
                        f"pause={config.SHOT_CYCLE_PAUSE_TICKS} ticks starting")

    def _fire_attack_pattern(self, world):
        """Independent per-figure cadence for JSON characters carrying an
        `attack_pattern` block (see combat.fire_attack_pattern). Each figure
        tracks its own tick/phase/pause in personality.trigger_state['_pattern']
        so characters with different cycle lengths/intervals run completely
        independently of each other and of Runner's own hardcoded cycle.
        Suppressed while that figure's own ultimate window is active (mirrors
        runner/swordsman's ultimate-bypass). Identical in Solo & Battle."""
        battle = bool(world.battle_mode and world.partner_figures)
        for fig in world.figures:
            char = getattr(fig.mode, "character", None)
            if not combat.has_attack_pattern(char) or not fig.mode.can_shoot():
                continue
            if fig.personality.ultimate_ticks > 0:
                continue
            pattern = char.get("attack_pattern") or {}
            cycle = pattern.get("cycle") or []
            st = fig.personality.trigger_state.setdefault(
                "_pattern", {"tick": 0, "phase": 0, "pause": 0})
            if st["pause"] > 0:
                st["pause"] -= 1
                continue
            try:
                interval = max(1, int(pattern.get("interval_ticks",
                                                    config.SHOOT_INTERVAL)))
            except (TypeError, ValueError):
                interval = config.SHOOT_INTERVAL
            st["tick"] += 1
            if st["tick"] < interval:
                continue
            st["tick"] = 0
            tx, ty = (world._nearest_enemy(fig.x, fig.y) if battle
                      else world.cursor)
            phase_cfg = cycle[st["phase"] % len(cycle)]
            new_projs = combat.fire_attack_pattern(fig, phase_cfg, tx, ty)
            world.projectiles.extend(new_projs)
            _fr, _fg, _fb = fig.lut[128]
            world.muzzle_flashes.append([fig.x, fig.y, 0, _fr, _fg, _fb])
            _pdiag = "; ".join(
                f"{type(pr).__name__}(spd={(pr.vx**2 + pr.vy**2) ** 0.5:.1f}"
                f",max_age={pr.max_age},pierce={pr.pierce})"
                for pr in new_projs)
            action_log.log("SHOT",
                f"attack_pattern mode={fig.mode.key} "
                f"fig=({fig.x:.0f},{fig.y:.0f}) phase={st['phase']} "
                f"style={phase_cfg.get('style')} spawned={len(new_projs)} "
                f"[{_pdiag}]")
            st["phase"] += 1
            if st["phase"] >= len(cycle):
                st["phase"] = 0
                st["pause"] = int(pattern.get("cycle_pause_ticks", 0) or 0)

    def _fire_json_actions(self, world):
        """attack_special / ultimate for JSON characters: fire whenever that
        action's own activation_triggers say so (ai.evaluate_activation_triggers
        — hp_threshold, radius_proximity, on_impact, after_on_hit, ...).
        attack_normal is handled by the shared cadence in _fire/_basic_shot;
        this covers the two triggered actions. Identical in Solo & Battle."""
        battle = bool(world.battle_mode and world.partner_figures)
        for fig in world.figures:
            char = getattr(fig.mode, "character", None)
            if not char:
                continue
            tx, ty = (world._nearest_enemy(fig.x, fig.y) if battle
                      else world.cursor)
            dx, dy = tx - fig.x, ty - fig.y
            dist = (dx * dx + dy * dy) ** 0.5
            for key in ("attack_special", "ultimate"):
                action = (char.get("actions") or {}).get(key)
                if not action or not action.get("activation_triggers"):
                    continue
                if ai.evaluate_activation_triggers(action, fig, dist,
                                                   world.global_tick):
                    # A particle-type can_hit layer means this character has
                    # its own authored burst FX (spread/speed/gravity/color)
                    # — show that instead of the plain simplified dot.
                    has_particle_layers = any(
                        l.get("type") == "particles"
                        for l in (action.get("fx_layers") or [])
                        if l.get("can_hit"))
                    new_projs = combat.fire_character_action(
                        fig, key, tx, ty, suppress_visual=has_particle_layers)
                    if has_particle_layers:
                        combat.spawn_character_burst_fx(fig, key)
                    if new_projs:
                        world.projectiles.extend(new_projs)
                        _fr, _fg, _fb = fig.lut[128]
                        world.muzzle_flashes.append(
                            [fig.x, fig.y, 0, _fr, _fg, _fb])


class CollisionSystem(System):
    """Battle interactions, after movement: crescent bullet-erasure, enemy
    projectile hits, swordsman dodge/counter triggers, and body collisions."""

    def update(self, world):
        if not (world.battle_mode and (world.enemy_projs or world.partner_figures)):
            if world.intercepted_bullets:
                world.intercepted_bullets.clear()
            return

        # --- Bullet-vs-enemy-bullet scatter ---
        # Each of our live projectiles is checked independently against each
        # enemy projectile.  On a hit the our bullet is replaced with 3 tiny
        # splinters and the enemy bullet is removed.  Splinters have hit_r_sq=0
        # so they cannot cascade.  The enemy bullet is consumed (removed from
        # enemy_projs) so it cannot also trigger figure-hit logic this tick.
        if world.projectiles and world.enemy_projs:
            dsq = config.BULLET_COLLIDE_DIST_SQ
            new_mine = []
            consumed_enemy = set()   # indices into world.enemy_projs
            for proj in world.projectiles:
                if proj.hit_r_sq == 0.0:
                    # Splinters pass through everything
                    new_mine.append(proj)
                    continue
                scattered = False
                for ei, etup in enumerate(world.enemy_projs):
                    if ei in consumed_enemy:
                        continue
                    ex, ey = etup[0], etup[1]
                    ddx, ddy = proj.x - ex, proj.y - ey
                    if ddx * ddx + ddy * ddy <= dsq:
                        # Pierce: a piercing shot (battle.attack.pierce on the
                        # fx layer that fired it) is not shredded by enemy
                        # bullets — it destroys the enemy bullet and keeps
                        # flying, unshaken. Non-pierce keeps the historical
                        # scatter-into-splinters behaviour.
                        consumed_enemy.add(ei)
                        combat.kill_projectile(etup[8])
                        world.collision_dots.append([proj.x, proj.y, 0])
                        if proj.pierce:
                            action_log.log("BULLET_HIT",
                                f"pierce-through at ({proj.x:.0f},{proj.y:.0f}) "
                                f"enemy_idx={ei} style={proj.style}")
                            continue
                        # Collision — scatter this bullet into splinters
                        # and destroy the enemy bullet for real (tuple[8]
                        # is the live Projectile on the other side).
                        splinters = combat.make_splinter_bullets(proj)
                        new_mine.extend(splinters)
                        action_log.log("BULLET_HIT",
                            f"scatter at ({proj.x:.0f},{proj.y:.0f}) "
                            f"enemy_idx={ei} splinters={len(splinters)}")
                        if proj.style == "beam":
                            action_log.log("BEAM_CULL",
                                f"bullet-scatter age={proj.age} "
                                f"at=({proj.x:.0f},{proj.y:.0f})")
                        scattered = True
                        break
                if not scattered:
                    new_mine.append(proj)
            world.projectiles = new_mine
            if consumed_enemy:
                world.enemy_projs = [
                    tup for i, tup in enumerate(world.enemy_projs)
                    if i not in consumed_enemy
                ]

                # --- Crescent arc erasure (must precede the hit check) ---
        # Regular crescents: erase per-tick — an erased bullet is destroyed
        # at the source (tuple[8].alive = False), so it never re-enters the
        # snapshot on later ticks.
        # Ult crescents: use velocity fingerprinting so bullets stay erased even after
        # they travel out of the ult crescent's zone.
        if world.enemy_projs:
            surviving = []
            for tup in world.enemy_projs:
                ex, ey, evx, evy = tup[0], tup[1], tup[2], tup[3]
                fp = (round(evx, 2), round(evy, 2))
                # Pre-filter bullets already intercepted by ult crescent
                if fp in world.intercepted_bullets:
                    continue
                hit = False
                # Pierce (battle.attack.pierce): a piercing incoming shot
                # ignores crescent erasure entirely — it is never erased by
                # a regular or ultimate crescent, surviving to the HP-damage
                # check below just like it ignores parry/deflect. Identical
                # in Solo & Battle.
                if not getattr(tup[8], "pierce", False):
                    # --- Regular crescent erasure (per-tick, no fingerprint) ---
                    for fig in world.figures:
                        if hit:
                            break
                        for cr in fig.combat.crescents:
                            if cr.check_bullet_erase(ex, ey):
                                world.collision_dots.append([ex, ey, 0])
                                combat.kill_projectile(tup[8])
                                hit = True
                                break
                    # --- Ultimate crescent erasure (fingerprinted for persistence) ---
                    if not hit:
                        for fig in world.figures:
                            if hit:
                                break
                            for uc in fig.combat.ult_crescents:
                                if uc.check_bullet_erase(ex, ey):
                                    world.intercepted_bullets.add(fp)
                                    world.collision_dots.append([ex, ey, 0])
                                    combat.kill_projectile(tup[8])
                                    hit = True
                                    break
                if not hit:
                    surviving.append(tup)
            world.enemy_projs = surviving

        # --- Enemy projectile -> figure hit ---
        # Note: we do NOT skip figures that are already bouncing.  Calling
        # battle_hit while airborne is safe (it stacks the impulse), and — more
        # importantly — it is the only way knockback_count can accumulate quickly
        # enough for the immunity cycle to kick in.  Skipping would mean a
        # stun-locked figure never reaches KNOCKBACK_LIMIT and stays bouncing
        # forever.
        #
        # Parry window: if a swordsman is within PARRY_RADIUS and its parry
        # cooldown has expired, the bullet is deflected instead of hitting.
        if world.enemy_projs:
            parry_rsq = config.PARRY_RADIUS * config.PARRY_RADIUS
            surviving_enemy = []
            for tup in world.enemy_projs:
                ex, ey, evx, evy = tup[0], tup[1], tup[2], tup[3]
                erased_by_parry = False
                # Pierce (battle.attack.pierce on the fx layer that fired this
                # shot): a piercing incoming shot ignores deflect/parry
                # entirely — it is never erased or ricocheted here, and never
                # even triggers the parry stance on the defending figure. It
                # simply survives to the HP-damage check below. Identical in
                # Solo & Battle.
                if not getattr(tup[8], "pierce", False):
                    for fig in world.figures:
                        if not (fig.mode.uses_melee()
                                or combat.has_defend_deflect(fig)):
                            continue
                        ddx, ddy = ex - fig.x, ey - fig.y
                        if ddx * ddx + ddy * ddy <= parry_rsq:
                            if fig.combat.parrying:
                                world.collision_dots.append([ex, ey, 0])
                                erased_by_parry = True
                            elif combat.trigger_parry(fig):
                                world.collision_dots.append([ex, ey, 0])
                                erased_by_parry = True
                            if erased_by_parry:
                                # Deflect: enemy bullet ricochets off the swordsman
                                # (cosmetic, keeps the shooter's original colour),
                                # and the real bullet dies at the source.
                                combat.kill_projectile(tup[8])
                                world.projectiles.append(combat.make_deflect_bullet(
                                    fig.x, fig.y, ex, ey, evx, evy,
                                    (tup[4], tup[5], tup[6])))
                            break
                if not erased_by_parry:
                    surviving_enemy.append(tup)
            world.enemy_projs = surviving_enemy

            for fig in world.figures:
                hb = fig.mode.hurtbox_radius()
                proj_hit_sq = hb * hb if hb else config.BATTLE_PROJ_HIT_SQ
                for ex, ey, evx, evy, _r, _g, _b, _dmg, _src in world.enemy_projs:
                    # Pierce ignores an active parry stance too — a piercing
                    # shot still damages a parrying figure. Non-piercing shots
                    # keep the historical "no damage while parrying" gate.
                    if fig.combat.parrying and not getattr(_src, "pierce", False):
                        continue
                    ddx, ddy = ex - fig.x, ey - fig.y
                    if ddx * ddx + ddy * ddy <= proj_hit_sq:
                        ai.battle_hit(fig, evx, evy, world, amount=_dmg,
                                      knockback_px=getattr(_src, "knockback_px", 0))
                        world.collision_dots.append([ex, ey, 0])
                        # HP was reduced -> the bullet explodes in a burst.
                        _spawn_bullet_burst(world, ex, ey, _r, _g, _b)
                        # one_hit bullets (e.g. vanish-cut strikes) die at
                        # source after their first landed hit — pierce keeps
                        # them alive through parry/crescent/contact culls,
                        # this is the one sanctioned kill so each deals
                        # exactly one hit.
                        if getattr(_src, "one_hit", False):
                            combat.kill_projectile(_src)
                        break

        # --- Swordsman bullet-dodge trigger ---
        if world.enemy_projs:
            dsq = config.DODGE_TRIGGER_RADIUS * config.DODGE_TRIGGER_RADIUS
            dodge_dist = (config.SLASH_RADIUS * 4.0) * 0.15
            live_proj_ids = {id(p[-1]) for p in world.enemy_projs}
            for fig in world.figures:
                if not fig.mode.uses_melee():
                    continue
                c, m = fig.combat, fig.motion
                if c.dodge_dashing or c.slashing or m.bouncing or m.bounce_ending:
                    continue
                if c.dodged_proj_ids:
                    c.dodged_proj_ids &= live_proj_ids  # drop ids of bullets no longer alive
                for ex, ey, evx, evy, _r, _g, _b, _dmg, _src in world.enemy_projs:
                    if id(_src) in c.dodged_proj_ids:
                        continue   # already dodged this exact bullet once
                    ddx, ddy = ex - fig.x, ey - fig.y
                    if ddx * ddx + ddy * ddy > dsq:
                        continue
                    bspd = (evx * evx + evy * evy) ** 0.5
                    if bspd < 0.001:
                        continue
                    bux, buy = evx / bspd, evy / bspd
                    # Sidestep toward the open side (cross of travel vs offset).
                    if bux * ddy - buy * ddx >= 0:
                        sx, sy = -buy, bux
                    else:
                        sx, sy = buy, -bux
                    c.dodged_proj_ids.add(id(_src))
                    if combat.dodge_style_cfg(fig) == "blink":
                        combat.dodge_blink(fig, fig.x + sx * dodge_dist,
                                            fig.y + sy * dodge_dist)
                    else:
                        c.dodge_vx = sx * config.DODGE_SPEED
                        c.dodge_vy = sy * config.DODGE_SPEED
                        c.dodge_dist_budget = dodge_dist
                        if c.dashing:
                            c.dodge_interrupt = True   # cut the forward dash short
                        else:
                            c.dodge_dashing = True
                            combat.spawn_clone(fig)
                    break

        # --- Swordsman counter-dash trigger (vs an incoming dashing enemy) ---
        if world.partner_figures:
            csq = config.SLASH_RADIUS * config.SLASH_RADIUS
            for fig in world.figures:
                if not fig.mode.uses_melee():
                    continue
                c, m = fig.combat, fig.motion
                if (c.dodge_dashing or c.dodge_counter
                        or c.slashing or m.bouncing or m.bounce_ending):
                    continue
                for ex, ey, edash, _eparry in world.partner_figures:
                    if not edash:
                        continue
                    ddx, ddy = ex - fig.x, ey - fig.y
                    d_sq = ddx * ddx + ddy * ddy
                    if d_sq > csq or d_sq < 0.001:
                        continue
                    if combat.dodge_style_cfg(fig) == "blink":
                        combat.dodge_blink(fig, ex, ey, counter_target=(ex, ey))
                    else:
                        inv = 1.0 / (d_sq ** 0.5)
                        c.dodge_vx = ddx * inv * config.DODGE_SPEED
                        c.dodge_vy = ddy * inv * config.DODGE_SPEED
                        c.dodge_dist_budget = d_sq ** 0.5
                        c.dodge_counter = True
                        if c.dashing:
                            c.dashing = c.rebounding = c.dodge_interrupt = False
                        c.dodge_dashing = True
                        combat.spawn_clone(fig)
                    break

        # --- Figure-to-figure body collision ---
        if world.partner_figures:
            bsq = config.BATTLE_BODY_HIT_SQ
            push = config.BATTLE_BODY_PUSH
            # Launch speed that produces DASH_HIT_KNOCKBACK_PX total travel
            # under BOUNCE_FRICTION per tick: v = dist * (1 - friction).
            dash_push_spd = config.DASH_HIT_KNOCKBACK_PX * (1.0 - config.BOUNCE_FRICTION)
            for fig in world.figures:
                m = fig.motion
                # bounce_ending is the slide-stop hold phase — don't interrupt it.
                # bouncing (active travel) CAN be interrupted: new impulse stacks.
                if m.bounce_ending:
                    continue
                # A dash-slashing swordsman is fully immune to figure-to-figure
                # body collision — both as the attacker and as the target.
                # The actual hit is handled exclusively by the dash-hit detection
                # in the combat FSM (advance_combat), so we skip it entirely here.
                if fig.mode.uses_melee() and fig.combat.dashing:
                    continue
                for ex, ey, edash, _eparry in world.partner_figures:
                    ddx, ddy = fig.x - ex, fig.y - ey
                    d_sq = ddx * ddx + ddy * ddy
                    if 0 < d_sq <= bsq:
                        dist = d_sq ** 0.5
                        if edash:
                            inv = dash_push_spd / dist
                        else:
                            inv = push / dist
                        nvx = ddx * inv
                        nvy = ddy * inv
                        if m.bouncing:
                            # Already airborne: launch opposite to the collision
                            # source — away from the collider's direction.
                            m.bounce_vx = -nvx
                            m.bounce_vy = -nvy
                        else:
                            m.bounce_vx = nvx
                            m.bounce_vy = nvy
                            m.bouncing = True
                        # Dot on every collision, including mid-knockback re-hits
                        if edash or m.bouncing:
                            cx = (fig.x + ex) * 0.5
                            cy = (fig.y + ey) * 0.5
                            world.collision_dots.append([cx, cy, 0])
                        # Body collision costs 1 HP to the TARGET only.
                        # Skip if parrying, or if the target is a swordsman
                        # mid-dash-slash (immune — handled by the FSM instead).
                        if not fig.combat.parrying:
                            ai.apply_hp_damage(fig, world)
                        break

        # --- Ultimate crescent → enemy figure HP damage (battle mode) ---
        # Each partner figure within the arc band takes 1 HP per tick.
        if world.battle_mode and world.partner_figures:
            for fig in world.figures:
                if not fig.mode.uses_melee():
                    continue
                for uc in fig.combat.ult_crescents:
                    for ex, ey, _edash, _eparry in world.partner_figures:
                        if uc.check_figure_hit(ex, ey):
                            # partner_figures is a read-only snapshot — the
                            # opposing side registers crescent damage through
                            # the normal projectile pipeline on its own pass.
                            # Here we only mark the visual contact dot.
                            world.collision_dots.append([ex, ey, 0])

        # --- Ultimate crescent → own figure HP damage (ult hits our figs back) ---
        # Only apply in solo mode (target = cursor proximity) or when enemy
        # ult crescents overlap our figures.  Ult-crescent-vs-figure damage
        # across sides is a documented gap (visual + bullet-erase only), the
        # same behaviour Battle mode has always had.

        # --- Ultimate crescent → solo mode cursor/figure zone ---
        # In solo mode, every our-figure ult crescent that is still alive and
        # has passed ULTC_FADE_DIST fires per-tick damage to the cursor target
        # by calling apply_hp_damage on the figure itself (the cursor = enemy).
        # This mirrors the "1 HP per tick while overlapping" spec.
        # (In solo, the crescent travels away from the figure, so the figure
        # itself is never in the damage zone; only an approaching enemy would be.)


def build_pipeline():
    """The ordered per-side systems list, run once per fielded side each
    tick (app.py binds the side first).  Input is handled once per tick by
    Overlay, outside this pipeline; collisions run after movement; rendering
    is in paintEvent (not a system)."""
    return [
        CombatSystem(),     # advance attacks (uses fresh enemy snapshots)
        MotionSystem(),     # move non-attacking figures
        CollisionSystem(),  # post-movement battle interactions
        ProjectileSystem(), # fire + advance bullets
    ]








