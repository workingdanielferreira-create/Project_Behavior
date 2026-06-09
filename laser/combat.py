"""
Combat — projectiles, crescent waves, and (stage 2) the swordsman attack FSM.

Projectile and CrescentWave are self-contained entities ported faithfully from
the original.  The dash / rebound / slash / combo / dodge controller and the
collision triggers that drive a swordsman are ported in stage 2; this module is
where they will live, operating on a Figure's `Combatant` component.
"""

import math
import random
from collections import deque

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPen, QRadialGradient, QPainterPath

from . import config
from .geometry import angle_deg_qt, angle_diff
from .palette import LUT_MASK


# ---------------------------------------------------------------------------
# Projectile — a bullet with a short position-history trail
# ---------------------------------------------------------------------------
class Projectile:
    __slots__ = ("x", "y", "vx", "vy", "age", "r", "g", "b",
                 "max_age", "hit_r_sq", "trail", "radius")

    def __init__(self, fx, fy, vx, vy, color_rgb, trail_len):
        self.x, self.y = float(fx), float(fy)
        self.vx, self.vy = vx, vy
        self.r, self.g, self.b = color_rgb
        self.age = 0
        self.max_age = config.PROJ_MAX_AGE
        self.hit_r_sq = float(config.PROJ_HIT_RADIUS ** 2)
        self.trail = deque(maxlen=max(3, trail_len))
        self.radius = float(config.PROJ_RADIUS)  # overridable for splinters

    @property
    def alive(self):
        return self.age < self.max_age

    def update(self):
        self.trail.append((self.x, self.y))
        self.x += self.vx
        self.y += self.vy
        self.age += 1

    def draw(self, p):
        fade = max(0.0, 1.0 - self.age / self.max_age)
        r, g, b = self.r, self.g, self.b
        hx, hy = int(self.x), int(self.y)

        pts = list(self.trail)
        n = len(pts)
        if n > 1:
            pen = QPen()
            pen.setCapStyle(Qt.RoundCap)
            for i in range(1, n):
                t = i / n
                pen.setColor(QColor(r, g, b, int(200 * t * fade)))
                pen.setWidthF(1.0 + 2.0 * t)
                p.setPen(pen)
                x0, y0 = pts[i - 1]; x1, y1 = pts[i]
                p.drawLine(int(x0), int(y0), int(x1), int(y1))

        glwr = max(1.0, self.radius * 3)
        iglwr = int(glwr)
        grad = QRadialGradient(hx, hy, glwr)
        grad.setColorAt(0.0, QColor(r, g, b, int(140 * fade)))
        grad.setColorAt(1.0, QColor(r, g, b, 0))
        p.setPen(Qt.NoPen); p.setBrush(grad)
        p.drawEllipse(hx - iglwr, hy - iglwr, iglwr * 2, iglwr * 2)

        rad = max(1.0, self.radius)
        irad = int(rad)
        core = QRadialGradient(hx, hy, rad)
        core.setColorAt(0.0, QColor(255, 255, 255, int(240 * fade)))
        core.setColorAt(0.5, QColor(r, g, b, int(210 * fade)))
        core.setColorAt(1.0, QColor(r, g, b, int(140 * fade)))
        p.setBrush(core)
        p.drawEllipse(hx - irad, hy - irad, irad * 2, irad * 2)


# ---------------------------------------------------------------------------
# ZigzagProjectile — weaves laterally while travelling toward the target
# ---------------------------------------------------------------------------
class ZigzagProjectile(Projectile):
    """Travels in a sinusoidal path perpendicular to the launch direction.

    `phase_offset` staggers the two zigzag bullets so they weave in opposite
    directions (one starts swinging left, the other right), creating a
    crossing/figure-eight look as they fly toward the target.
    """
    __slots__ = ("ax", "ay", "freq", "phase")

    def __init__(self, fx, fy, vx, vy, color_rgb, trail_len,
                 amplitude, frequency, phase_offset=0.0):
        super().__init__(fx, fy, vx, vy, color_rgb, trail_len)
        # Perpendicular unit vector (rotate 90°)
        spd = (vx * vx + vy * vy) ** 0.5
        if spd > 0.001:
            px, py = -vy / spd, vx / spd
        else:
            px, py = 0.0, 1.0
        self.ax = px * amplitude
        self.ay = py * amplitude
        self.freq = frequency
        self.phase = phase_offset

    def update(self):
        self.trail.append((self.x, self.y))
        # Sinusoidal lateral nudge
        lateral = math.sin(self.phase) * self.freq
        self.x += self.vx + self.ax * lateral
        self.y += self.vy + self.ay * lateral
        self.phase += self.freq
        self.age += 1


# ---------------------------------------------------------------------------
# HomingProjectile — steers toward a moving target at half normal speed
# ---------------------------------------------------------------------------
class HomingProjectile(Projectile):
    """Gradually turns toward (tx, ty) each tick.

    `target` is a mutable list [x, y] so the caller can update it as the
    cursor/enemy moves; the projectile will track the updated position.
    `turn_rate` caps how many radians the heading can change per tick.
    """
    __slots__ = ("target", "turn_rate", "speed")

    def __init__(self, fx, fy, vx, vy, color_rgb, trail_len,
                 target, turn_rate=0.06):
        super().__init__(fx, fy, vx, vy, color_rgb, trail_len)
        self.target = target      # [x, y]  — updated externally each tick
        self.turn_rate = turn_rate
        self.speed = (vx * vx + vy * vy) ** 0.5

    def update(self):
        self.trail.append((self.x, self.y))
        # Steer toward target
        tx, ty = self.target[0], self.target[1]
        dx, dy = tx - self.x, ty - self.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0.001 and self.speed > 0.001:
            desired_vx = dx / dist * self.speed
            desired_vy = dy / dist * self.speed
            # Blend current heading toward desired heading
            self.vx += (desired_vx - self.vx) * self.turn_rate
            self.vy += (desired_vy - self.vy) * self.turn_rate
            # Re-normalise to constant speed
            cur_spd = (self.vx * self.vx + self.vy * self.vy) ** 0.5
            if cur_spd > 0.001:
                self.vx = self.vx / cur_spd * self.speed
                self.vy = self.vy / cur_spd * self.speed
        self.x += self.vx
        self.y += self.vy
        self.age += 1


# ---------------------------------------------------------------------------
# Runner shot-cycle factory
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Splinter factory — called when a bullet collides with an enemy bullet
# ---------------------------------------------------------------------------
def make_splinter_bullets(proj):
    """Return 3 tiny Projectile objects bursting perpendicular to the parent.

    The burst is centred on the parent's current position.  The three bullets
    fan out symmetrically: one straight perpendicular-left, one straight
    perpendicular-right, and one straight ahead — each offset by
    SPLINTER_SPREAD_DEG so none retrace the original path.

    Perpendicular is computed from the parent velocity so the scatter always
    looks natural regardless of the bullet's travel direction.
    """
    spd = (proj.vx * proj.vx + proj.vy * proj.vy) ** 0.5
    if spd < 0.001:
        spd = config.PROJ_SPEED

    # Forward unit vector from parent velocity
    fx, fy = proj.vx / spd, proj.vy / spd
    # Perpendicular unit vector (90° left of travel)
    px, py = -fy, fx

    srad = config.PROJ_RADIUS * config.SPLINTER_RADIUS_SCALE
    sspd = spd * config.SPLINTER_SPEED_MULT
    half = math.radians(config.SPLINTER_SPREAD_DEG)
    tl = max(2, config.PROJ_TRAIL_LEN - 1)
    cr = (proj.r, proj.g, proj.b)

    # Three directions: left-perp, right-perp, straight-back-through
    # (visually: two side-bursts + one that carries forward at an angle)
    angles = (-half, 0.0, half)   # relative to perpendicular axis
    splinters = []
    for a in angles:
        ca, sa = math.cos(a), math.sin(a)
        # Rotate perpendicular vector by a around the forward axis
        dvx = (px * ca - fx * sa) * sspd
        dvy = (py * ca - fy * sa) * sspd
        s = Projectile(proj.x, proj.y, dvx, dvy, cr, tl)
        s.radius = srad
        s.max_age = config.SPLINTER_MAX_AGE
        s.hit_r_sq = 0.0   # splinters do not trigger further collisions
        splinters.append(s)
    return splinters


def make_runner_cycle_shot(fx, fy, cx, cy, color_rgb, phase):
    """Return a list of Projectile objects for the given cycle phase.

    phase 0 — CONE   : 3 clusters spread in a fan (config.SHOT_CONE_ANGLES)
    phase 1 — ZIGZAG : 2 clusters that weave in opposing sine waves
    phase 2 — HOMING : 1 cluster that slowly tracks the target
    """
    dx, dy = cx - fx, cy - fy
    d = (dx * dx + dy * dy) ** 0.5
    base_deg = math.degrees(math.atan2(dy, dx)) if d > 0.01 else 0.0
    tl = config.PROJ_TRAIL_LEN
    cr = color_rgb

    if phase == 0:
        # --- CONE ---
        bullets = []
        for off in config.SHOT_CONE_ANGLES:
            a = math.radians(base_deg + off)
            vx = math.cos(a) * config.PROJ_SPEED
            vy = math.sin(a) * config.PROJ_SPEED
            bullets.append(Projectile(fx, fy, vx, vy, cr, tl))
        return bullets

    elif phase == 1:
        # --- ZIGZAG ---
        base_rad = math.radians(base_deg)
        vx = math.cos(base_rad) * config.PROJ_SPEED
        vy = math.sin(base_rad) * config.PROJ_SPEED
        amp = config.SHOT_ZIGZAG_AMPLITUDE
        freq = config.SHOT_ZIGZAG_FREQUENCY
        # Two bullets with opposite starting phases so they weave past each other
        b0 = ZigzagProjectile(fx, fy, vx, vy, cr, tl,
                               amplitude=amp, frequency=freq,
                               phase_offset=0.0)
        b1 = ZigzagProjectile(fx, fy, vx, vy, cr, tl,
                               amplitude=amp, frequency=freq,
                               phase_offset=math.pi)
        return [b0, b1]

    else:
        # --- HOMING ---
        base_rad = math.radians(base_deg)
        hspd = config.PROJ_SPEED * config.SHOT_HOMING_SPEED_MULT
        vx = math.cos(base_rad) * hspd
        vy = math.sin(base_rad) * hspd
        target_ref = [float(cx), float(cy)]
        return [HomingProjectile(fx, fy, vx, vy, cr, tl,
                                 target=target_ref, turn_rate=0.06)]


def update_homing_targets(projectiles, cx, cy):
    """Refresh the target reference for all HomingProjectiles this tick.

    Called once per tick by ProjectileSystem before advancing projectiles,
    so that homing bullets always track the current cursor / enemy position.
    """
    for proj in projectiles:
        if isinstance(proj, HomingProjectile):
            proj.target[0] = float(cx)
            proj.target[1] = float(cy)


# ---------------------------------------------------------------------------
# Legacy make_shot — used for non-runner modes (swordsman battle fire etc.)
# ---------------------------------------------------------------------------
def make_shot(fx, fy, cx, cy, color_rgb):
    """Fire a fan of bullets toward (cx, cy) per config.SHOT_ANGLES."""
    dx, dy = cx - fx, cy - fy
    d = (dx * dx + dy * dy) ** 0.5
    base = math.degrees(math.atan2(dy, dx)) if d > 0.01 else 0.0
    bullets = []
    for off in config.SHOT_ANGLES:
        a = math.radians(base + off)
        vx = math.cos(a) * config.PROJ_SPEED
        vy = math.sin(a) * config.PROJ_SPEED
        bullets.append(Projectile(fx, fy, vx, vy, color_rgb,
                                  trail_len=random.randint(3, 15)))
    return bullets


# ---------------------------------------------------------------------------
# CrescentWave — an arc that flies toward a target, fades, and erases bullets
# ---------------------------------------------------------------------------
class CrescentWave:
    __slots__ = ("x", "y", "dir_x", "dir_y", "age", "color_rgb", "centre_angle_deg")

    def __init__(self, fig_x, fig_y, target_x, target_y, color_rgb):
        dx, dy = target_x - fig_x, target_y - fig_y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0.001:
            self.dir_x, self.dir_y = dx / dist, dy / dist
        else:
            self.dir_x, self.dir_y = 1.0, 0.0
        self.x = fig_x + self.dir_x * config.CRESCENT_AHEAD
        self.y = fig_y + self.dir_y * config.CRESCENT_AHEAD
        self.age = 0
        self.color_rgb = color_rgb
        self.centre_angle_deg = angle_deg_qt(self.dir_x, self.dir_y)

    @property
    def alive(self):
        return self.age < config.CRESCENT_LIFETIME

    def update(self):
        self.x += self.dir_x * config.CRESCENT_SPEED
        self.y += self.dir_y * config.CRESCENT_SPEED
        self.age += 1

    def check_bullet_erase(self, bx, by):
        """True if a bullet at (bx, by) lies on the arc's surface band + span."""
        r2 = config.CRESCENT_RADIUS
        margin = config.CRESCENT_WIDTH + 20.0
        ddx, ddy = bx - self.x, by - self.y
        dist = (ddx * ddx + ddy * ddy) ** 0.5
        if dist < 0.001 or not (r2 - margin <= dist <= r2 + margin):
            return False
        diff = angle_diff(angle_deg_qt(ddx, ddy), self.centre_angle_deg)
        return abs(diff) <= config.CRESCENT_SPAN / 2.0

    def draw(self, p, pen, lut=None, flow_off=0.0):
        if not self.alive:
            return
        segs = config.CRESCENT_SEGS
        r2 = config.CRESCENT_RADIUS
        half_span = config.CRESCENT_SPAN / 2.0
        start_deg = self.centre_angle_deg - half_span
        step = config.CRESCENT_SPAN / segs
        rect_x, rect_y = self.x - r2, self.y - r2
        diam = r2 * 2

        half_life = config.CRESCENT_LIFETIME * 0.85
        if self.age <= half_life:
            tip_t = self.age / half_life
            fade_alpha = 1.0
        else:
            tip_t = 1.0
            fade_alpha = 1.0 - (self.age - half_life) / (config.CRESCENT_LIFETIME - half_life)

        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setBrush(Qt.NoBrush)

        for i in range(segs):
            seg_t = (i + 0.5) / segs
            if seg_t > tip_t:
                continue
            dist_from_tip = tip_t - seg_t
            if dist_from_tip > config.CRESCENT_TAIL:
                continue
            tail_t = 1.0 - (dist_from_tip / config.CRESCENT_TAIL)
            lut_idx = int(((seg_t + flow_off) % 1.0) * 256) & LUT_MASK
            r, g, b = lut[lut_idx] if lut is not None else self.color_rgb
            alpha = int(230 * (tail_t ** 0.6) * fade_alpha)
            if alpha < 4:
                continue
            pen.setColor(QColor(r, g, b, alpha))
            pen.setWidthF(config.CRESCENT_WIDTH * (0.25 + 0.75 * tail_t))
            p.setPen(pen)
            a0 = start_deg + i * step
            path = QPainterPath()
            path.arcMoveTo(rect_x, rect_y, diam, diam, a0)
            path.arcTo(rect_x, rect_y, diam, diam, a0, step)
            p.drawPath(path)


# ---------------------------------------------------------------------------
# Swordsman attack FSM — operates on a Figure's components.
# Returns True if it consumed the tick (motion should be skipped this tick),
# False if the figure should still take a normal movement step (faithful to the
# original, which does one chase step on the dash-trigger tick).
# ---------------------------------------------------------------------------
def advance_combat(fig, slash_target, fallback):
    t = fig.transform
    c = fig.combat
    m = fig.motion
    rng = fig.personality.rng
    bundle = fig.render.bundle

    if not bundle.slash:
        return False  # this mode has no melee capability

    # --- Combo follow-up cooldown tick ---
    if c.combo_cooldown_ticks > 0:
        c.combo_cooldown_ticks -= 1

    # --- Combo follow-up delay: count down, then launch the dash ---
    if c.combo_delay_ticks > 0:
        c.combo_delay_ticks -= 1
        if c.combo_delay_ticks == 0 and slash_target is not None:
            tx, ty = slash_target
            if c.combo_count == 1:
                approach = math.atan2(t.y - ty, t.x - tx)
                arc_off = rng.choice([1, -1]) * rng.uniform(
                    math.radians(90), math.radians(150))
                fa = approach + arc_off
                fd = config.SLASH_RADIUS * 0.9
                t.x = tx + math.cos(fa) * fd
                t.y = ty + math.sin(fa) * fd
            ddx, ddy = tx - t.x, ty - t.y
            ddist = (ddx * ddx + ddy * ddy) ** 0.5
            if ddist > config.SLASH_HIT_RADIUS:
                inv = 1.0 / ddist
                lspd = m.speed * config.SLASH_SPEED_MUL
                c.slash_vx = ddx * inv * lspd
                c.slash_vy = ddy * inv * lspd
                # Budget proportional to actual gap — same formula as initial dash.
                c.slash_dist_budget = ddist * 4.0
                c.dashing = True
                c.rebounding = False

    # --- Crescent advance + cull (emission happens on dash hit) ---
    if c.crescents:
        live = []
        for cr in c.crescents:
            cr.update()
            if cr.alive:
                live.append(cr)
        c.crescents = live

    # --- Slash cycle (stationary; plays once at end of dash/rebound) ---
    if c.slashing:
        ox, oy = t.x, t.y
        c.slash_tick += 1
        if c.slash_tick >= config.SLASH_ANIM_SPD:
            c.slash_tick = 0
            if c.slash_phase == 0:
                c.slash_idx += 1
                if c.slash_idx >= 2:
                    c.slash_idx = 2
                    c.slash_phase = 1
            elif c.slash_phase == 1:
                c.slash_phase = 2
                c.slash_idx = 3
            else:
                c.slash_idx += 1
                if c.slash_idx >= 5:
                    c.slashing = c.rebounding = c.dashing = False
                    fig.render.run_idx = 0
                    fig.render.anim_tick = 0
                    # --- Follow-up combo dash ---
                    if c.combo_pending and slash_target is not None:
                        c.combo_pending = False
                        # Enforce max follow-ups and cooldown.
                        if (c.combo_follow_ups >= config.COMBO_MAX
                                or c.combo_cooldown_ticks > 0):
                            # Exhausted or on cooldown — reset and skip.
                            c.combo_cooldown_ticks = config.COMBO_COOLDOWN_TICKS
                            c.combo_follow_ups = 0
                        else:
                            c.combo_follow_ups += 1
                            # Arm a randomised delay before the follow-up dash fires.
                            # travel_ticks is a PRE-LAUNCH PAUSE, not a budget multiplier.
                            # This gives the target breathing room after knockback.
                            c.combo_delay_ticks = rng.randint(
                                config.COMBO_TRAVEL_TICKS_MIN,
                                config.COMBO_TRAVEL_TICKS_MAX)
                            # If this was the last allowed follow-up, start cooldown.
                            if c.combo_follow_ups >= config.COMBO_MAX:
                                c.combo_cooldown_ticks = config.COMBO_COOLDOWN_TICKS
                                c.combo_follow_ups = 0
        fig.face(ox, oy)
        fig.trail.update(t.x, t.y, t.facing_left, False, False)
        fig.render.is_moving = False
        return True

    # --- Dash / Rebound ---
    if c.dashing:
        if c.dodge_interrupt:
            # A dodge was requested mid-dash: cancel the dash and fall through to
            # the dodge block below (do NOT return). Triggers wired in stage 3.
            c.dashing = c.rebounding = c.dodge_interrupt = False
            c.dodge_dashing = True
        else:
            ox, oy = t.x, t.y
            if not c.rebounding:
                tx, ty = slash_target if slash_target is not None else fallback
                dx, dy = tx - t.x, ty - t.y
                dist = (dx * dx + dy * dy) ** 0.5
                if dist <= config.SLASH_HIT_RADIUS:
                    # Crescent aimed at the struck target.
                    r, g, b = fig.lut[80]
                    c.crescents.append(CrescentWave(t.x, t.y, tx, ty, (r, g, b)))
                    # Signal knockback to partner process via IPC.
                    kb_spd = config.DASH_HIT_KNOCKBACK_PX * (1.0 - config.BOUNCE_FRICTION)
                    ddx2, ddy2 = tx - t.x, ty - t.y
                    ddist2 = (ddx2 * ddx2 + ddy2 * ddy2) ** 0.5
                    if ddist2 > 0.001:
                        c.hit_vx = (ddx2 / ddist2) * kb_spd
                        c.hit_vy = (ddy2 / ddist2) * kb_spd
                    else:
                        c.hit_vx = c.slash_vx / max(abs(c.slash_vx) + abs(c.slash_vy), 0.001) * kb_spd
                        c.hit_vy = c.slash_vy / max(abs(c.slash_vx) + abs(c.slash_vy), 0.001) * kb_spd
                    c.hit_pending = True
                    if c.combo_count == 0:
                        c.combo_count = 2
                    if c.combo_count > 0:
                        c.combo_count -= 1
                        c.combo_pending = True
                        c.combo_target = (tx, ty)
                    if c.combo_pending:
                        # Stop dead, go straight into the slash animation.
                        c.dashing = c.rebounding = False
                        c.slashing = True
                        c.slash_phase = c.slash_idx = c.slash_tick = 0
                        c.slash_vx = c.slash_vy = 0.0
                    else:
                        # Final hit: reflect velocity off the contact normal.
                        if dist > 0.001:
                            nx = (t.x - tx) / dist
                            ny = (t.y - ty) / dist
                        else:
                            spd = (c.slash_vx ** 2 + c.slash_vy ** 2) ** 0.5
                            nx = -c.slash_vx / spd if spd > 0 else 1.0
                            ny = -c.slash_vy / spd if spd > 0 else 0.0
                        dot = c.slash_vx * nx + c.slash_vy * ny
                        rx = c.slash_vx - 2.0 * dot * nx
                        ry = c.slash_vy - 2.0 * dot * ny
                        rmag = (rx * rx + ry * ry) ** 0.5
                        if rmag > 0.001:
                            lspd = (c.slash_vx ** 2 + c.slash_vy ** 2) ** 0.5
                            c.slash_vx = rx / rmag * lspd
                            c.slash_vy = ry / rmag * lspd
                        c.rebounding = True
                else:
                    t.x += c.slash_vx
                    t.y += c.slash_vy
                    c.slash_dist_budget -= (c.slash_vx ** 2 + c.slash_vy ** 2) ** 0.5
                    if c.slash_dist_budget <= 0:
                        c.dashing = False
            else:
                t.x += c.slash_vx
                t.y += c.slash_vy
                c.slash_dist_budget -= (c.slash_vx ** 2 + c.slash_vy ** 2) ** 0.5
                if c.slash_dist_budget <= 0:
                    c.dashing = False
                    c.slashing = True
                    c.slash_phase = c.slash_idx = c.slash_tick = 0
            fig.face(ox, oy)
            fig.trail.update(t.x, t.y, t.facing_left, True, False)
            fig.render.is_moving = True
            fig.render.advance()
            return True

    # --- Dodge dash execution (triggers wired stage 3; also reached via the
    #     dodge_interrupt fall-through above) ---
    if c.dodge_dashing:
        ox, oy = t.x, t.y
        step = (c.dodge_vx ** 2 + c.dodge_vy ** 2) ** 0.5
        t.x += c.dodge_vx
        t.y += c.dodge_vy
        c.dodge_dist_budget -= step
        if c.dodge_dist_budget <= 0:
            c.dodge_dashing = False
            if c.dodge_counter and slash_target is not None:
                c.dodge_counter = False
                tx, ty = slash_target
                dx, dy = tx - t.x, ty - t.y
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > config.SLASH_HIT_RADIUS:
                    inv = 1.0 / max(dist, 0.001)
                    lspd = m.speed * config.SLASH_SPEED_MUL
                    c.slash_vx = dx * inv * lspd
                    c.slash_vy = dy * inv * lspd
                    c.slash_dist_budget = dist * 4.0
                    c.dashing = True
                    c.rebounding = False
            else:
                c.dodge_counter = False
        fig.face(ox, oy)
        fig.trail.update(t.x, t.y, t.facing_left, True, False)
        fig.render.is_moving = True
        fig.render.advance()
        return True

    # --- Dash trigger (arms a dash; does NOT consume the tick) ---
    if slash_target is not None and not m.bouncing and not m.bounce_ending:
        tx, ty = slash_target
        dx, dy = tx - t.x, ty - t.y
        dist = (dx * dx + dy * dy) ** 0.5
        if config.SLASH_HIT_RADIUS < dist <= config.SLASH_RADIUS:
            inv = 1.0 / dist
            lspd = m.speed * config.SLASH_SPEED_MUL
            c.slash_vx = dx * inv * lspd
            c.slash_vy = dy * inv * lspd
            c.slash_dist_budget = dist * 4.0
            c.dashing = True
            c.rebounding = False

    return False


# ---------------------------------------------------------------------------
# Swordsman parry — triggered by CollisionSystem when a bullet enters PARRY_RADIUS.
# Returns True if the bullet that triggered it should be erased.
# ---------------------------------------------------------------------------
def trigger_parry(fig):
    """Arm the parry state on `fig` if the cooldown has expired.

    Emits a crescent arc aimed away from the figure centre (omnidirectional
    deflect), plays the slash animation, and starts the 1-second cooldown.
    Returns True if the parry was successfully triggered, False if on cooldown
    or already parrying.
    """
    c = fig.combat
    if c.parry_cooldown_ticks > 0 or c.parrying:
        return False
    # Emit a wide crescent (reuse same arc type as a dash-slash hit) aimed at
    # a point directly ahead of the figure based on its current facing.
    t = fig.transform
    r, g, b = fig.lut[200]  # slightly different lut index → distinct hue
    # Point the arc in the figure's current facing direction
    dir_x = -1.0 if t.facing_left else 1.0
    target_x = t.x + dir_x * config.CRESCENT_RADIUS * 2
    target_y = t.y
    c.crescents.append(CrescentWave(t.x, t.y, target_x, target_y, (r, g, b)))
    # Enter the parry slash animation at phase 0
    c.parrying = True
    c.parry_stance_ticks = config.PARRY_STANCE_TICKS   # active deflect window
    c.parry_cooldown_ticks = config.PARRY_COOLDOWN_TICKS
    # Do NOT enter the slash FSM — that would halt movement via c.busy.
    # The crescent arc is the visual; the figure keeps moving freely.
    return True


def tick_parry_cooldown(fig):
    """Decrement the parry cooldown and stance timer every tick."""
    c = fig.combat
    if c.parry_cooldown_ticks > 0:
        c.parry_cooldown_ticks -= 1
    # Stance window: count down; clear parrying flag when it expires
    if c.parrying:
        if c.parry_stance_ticks > 0:
            c.parry_stance_ticks -= 1
        if c.parry_stance_ticks <= 0:
            c.parrying = False
