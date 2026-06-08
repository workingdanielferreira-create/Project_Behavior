"""
Systems — the ordered pipeline that runs every tick.

`Overlay._tick`'s old 340-line body is now a list of `System` objects.  Each
system does one job over the whole world; a cross-cutting feature is a new
system inserted into the list, not edits sprinkled across a monolith.

Pipeline order (later stages fill the no-op systems in):
    InputSystem -> CombatSystem -> MotionSystem -> CollisionSystem
    -> ProjectileSystem -> IpcSystem
Combat runs before motion so a mid-attack figure moves there and the motion
system skips it (`fig.combat.busy`).  Rendering is NOT a system — Qt requires
it inside paintEvent (see app.py).
"""

from . import motion, modes, config, combat, ai
from . import platform_win as win


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
            tx, ty = world.movement_target(fig)
            if battle:
                motion.update(fig, tx, ty, False, False, False)
            else:
                hit = motion.update(fig, tx, ty, world.collision_on,
                                    world.path_follow, world.runaway)
                if hit is not None:
                    world.collision_dots.append([hit[0], hit[1], 0])
        for fig in world.figures:
            motion.check_walls(fig)


# ---------------------------------------------------------------------------
# Staged systems — registered into the pipeline as each stage lands.
# They are no-ops today so the pipeline shape is final and visible now.
# ---------------------------------------------------------------------------
class CombatSystem(System):
    """Advances the swordsman attack FSM for every melee figure and records
    whether it consumed the tick (so MotionSystem can skip those figures)."""

    def update(self, world):
        for fig in world.figures:
            if not fig.mode.uses_melee():
                fig.combat.acted = False
                continue
            tgt = world.melee_target(fig)
            fig.combat.acted = combat.advance_combat(fig, tgt, world.cursor)


class ProjectileSystem(System):
    """Spawn, advance, and cull bullets.

    Stage 1 handles the non-battle cadence: a single shared timer fires every
    config.SHOOT_INTERVAL ticks, and each figure whose mode `can_shoot()` emits
    one formation toward the cursor.  Per-figure battle firing lands in stage 3.
    """

    def update(self, world):
        if world.runner_on and world.shoot_mode:
            if world.battle_mode and world.partner_figures:
                # Battle: each shooter fires at its nearest enemy on its own
                # randomised cadence.
                for fig in world.figures:
                    if not fig.mode.can_shoot():
                        continue
                    p = fig.personality
                    p.shoot_tick += 1
                    if p.shoot_tick >= p.battle_shoot_interval:
                        p.shoot_tick = 0
                        p.battle_shoot_interval = p.rng.randint(
                            *config.SHOOT_INTERVAL_RANGE)
                        bx, by = world._nearest_enemy(fig.x, fig.y)
                        world.projectiles.extend(
                            combat.make_shot(fig.x, fig.y, bx, by, fig.lut[128]))
            elif not world.battle_mode:
                # Non-battle: one shared timer; everyone fires at the cursor.
                world.shoot_ticks += 1
                if world.shoot_ticks >= config.SHOOT_INTERVAL:
                    world.shoot_ticks = 0
                    cx, cy = world.cursor
                    for fig in world.figures:
                        if not fig.mode.can_shoot():
                            continue
                        world.projectiles.extend(
                            combat.make_shot(fig.x, fig.y, cx, cy, fig.lut[128]))

        # Advance + cull (runs every tick).
        if world.projectiles:
            alive = []
            for proj in world.projectiles:
                proj.update()
                if proj.alive:
                    alive.append(proj)
            world.projectiles = alive


class CollisionSystem(System):
    """Battle interactions, after movement: crescent bullet-erasure, enemy
    projectile hits, swordsman dodge/counter triggers, and body collisions."""

    def update(self, world):
        if not (world.battle_mode and (world.enemy_projs or world.partner_figures)):
            if world.intercepted_bullets:
                world.intercepted_bullets.clear()
            return

        # --- Crescent arc erasure (must precede the hit check) ---
        if world.enemy_projs:
            surviving = []
            for tup in world.enemy_projs:
                ex, ey, evx, evy = tup[0], tup[1], tup[2], tup[3]
                fp = (round(evx, 2), round(evy, 2))
                if fp in world.intercepted_bullets:
                    continue
                hit = False
                for fig in world.figures:
                    if hit:
                        break
                    for cr in fig.combat.crescents:
                        if cr.check_bullet_erase(ex, ey):
                            world.intercepted_bullets.add(fp)
                            hit = True
                            break
                if not hit:
                    surviving.append(tup)
            world.enemy_projs = surviving

        # --- Enemy projectile -> figure hit ---
        if world.enemy_projs:
            for fig in world.figures:
                m = fig.motion
                if m.bouncing or m.bounce_ending:
                    continue
                for ex, ey, evx, evy, _r, _g, _b in world.enemy_projs:
                    ddx, ddy = ex - fig.x, ey - fig.y
                    if ddx * ddx + ddy * ddy <= config.BATTLE_PROJ_HIT_SQ:
                        ai.battle_hit(fig, evx, evy)
                        world.collision_dots.append([ex, ey, 0])
                        break

        # --- Swordsman bullet-dodge trigger ---
        if world.enemy_projs:
            dsq = config.DODGE_TRIGGER_RADIUS * config.DODGE_TRIGGER_RADIUS
            dodge_dist = (config.SLASH_RADIUS * 4.0) * 0.15
            for fig in world.figures:
                if not fig.mode.uses_melee():
                    continue
                c, m = fig.combat, fig.motion
                if c.dodge_dashing or c.slashing or m.bouncing or m.bounce_ending:
                    continue
                for ex, ey, evx, evy, _r, _g, _b in world.enemy_projs:
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
                    c.dodge_vx = sx * config.DODGE_SPEED
                    c.dodge_vy = sy * config.DODGE_SPEED
                    c.dodge_dist_budget = dodge_dist
                    if c.dashing:
                        c.dodge_interrupt = True   # cut the forward dash short
                    else:
                        c.dodge_dashing = True
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
                for ex, ey, edash in world.partner_figures:
                    if not edash:
                        continue
                    ddx, ddy = ex - fig.x, ey - fig.y
                    d_sq = ddx * ddx + ddy * ddy
                    if d_sq > csq or d_sq < 0.001:
                        continue
                    inv = 1.0 / (d_sq ** 0.5)
                    c.dodge_vx = ddx * inv * config.DODGE_SPEED
                    c.dodge_vy = ddy * inv * config.DODGE_SPEED
                    c.dodge_dist_budget = d_sq ** 0.5
                    c.dodge_counter = True
                    if c.dashing:
                        c.dashing = c.rebounding = c.dodge_interrupt = False
                    c.dodge_dashing = True
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
                if m.bouncing or m.bounce_ending:
                    continue
                # A dashing swordsman passes through — its hit is handled by the
                # dash-hit detection in the combat FSM.
                if fig.mode.uses_melee() and fig.combat.dashing:
                    continue
                for ex, ey, edash in world.partner_figures:
                    ddx, ddy = fig.x - ex, fig.y - ey
                    d_sq = ddx * ddx + ddy * ddy
                    if 0 < d_sq <= bsq:
                        dist = d_sq ** 0.5
                        if edash:
                            # Dash-slash hit: fixed 60 px knockback distance.
                            inv = dash_push_spd / dist
                        else:
                            inv = push / dist
                        m.bounce_vx = ddx * inv
                        m.bounce_vy = ddy * inv
                        m.bouncing = True
                        # Dot only when at least one party is mid-dash
                        if edash or (fig.mode.uses_melee() and fig.combat.dashing):
                            cx = (fig.x + ex) * 0.5
                            cy = (fig.y + ey) * 0.5
                            world.collision_dots.append([cx, cy, 0])
                        break


class IpcSystem(System):
    """Heartbeat + share figures/projectiles, then read the partner's and set
    battle mode.  Runs early (after input) so targets are fresh for combat."""

    def update(self, world):
        ipc = world.ipc
        if not ipc.alive():
            return
        ipc.write_heartbeat()
        ipc.write_figures(world.figures)
        ipc.write_projectiles(world.projectiles)

        # Collect any pending dash-slash knockback from this tick and write it.
        kb_vx = kb_vy = 0.0
        kb_pending = False
        for fig in world.figures:
            if fig.combat.hit_pending:
                kb_vx, kb_vy = fig.combat.hit_vx, fig.combat.hit_vy
                kb_pending = True
                fig.combat.hit_pending = False
        ipc.write_knockback(kb_vx, kb_vy, kb_pending)

        was_battle = world.battle_mode
        world.battle_mode = ipc.partner_alive()
        if world.battle_mode:
            world.partner_figures = ipc.read_partner_figures()
            world.enemy_projs = ipc.read_partner_projectiles()
            # Apply any knockback the partner sent this tick.
            pvx, pvy, ppending = ipc.read_partner_knockback()
            if ppending:
                ipc.clear_partner_knockback()
                for fig in world.figures:
                    m = fig.motion
                    if m.bouncing or m.bounce_ending:
                        continue
                    m.bounce_vx, m.bounce_vy = pvx, pvy
                    m.bouncing = True
        else:
            world.partner_figures = []
            world.enemy_projs = []
            if was_battle:
                world.intercepted_bullets.clear()


def build_pipeline():
    """The ordered systems list. IPC runs early so battle targets are fresh;
    collisions run after movement; rendering is in paintEvent (not a system)."""
    return [
        InputSystem(),
        IpcSystem(),        # share + read partner; set battle mode
        CombatSystem(),     # advance attacks (uses fresh enemy targets)
        MotionSystem(),     # move non-attacking figures
        CollisionSystem(),  # post-movement battle interactions
        ProjectileSystem(), # fire + advance bullets
    ]

