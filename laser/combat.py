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
        b0 = ZigzagProjectile(fx, fy, vx, vy, cr, tl,
                               amplitude=amp, frequency=freq,
                               phase_offset=0.0)
        return [b0]

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
# UltimateCrescent — swordsman ultimate: a large slow blade launched at 50% HP
# ---------------------------------------------------------------------------
class UltimateCrescent:
    """A large crescent blade that travels forward at ~100 px/s.

    Visual:  dark filled body (thick arc) + bright blue rim (thin inner arc).
    Reveal:  sweeps in from bottom of the arc to top over the first 10 frames
             so it appears to materialise upward.
    Fade:    after ULTC_FADE_DIST px of travel, fades from bottom to top.
    Damage:  any enemy figure whose centre is within ULTC_HIT_FIGURE_DIST of
             the arc surface takes 1 HP per tick (checked by CollisionSystem).
    Bullets: destroys any bullet whose centre lies within the blade band.
    """

    __slots__ = ("x", "y", "dir_x", "dir_y", "age", "dist_travelled",
                 "centre_angle_deg", "reveal_t")

    def __init__(self, fig_x, fig_y, target_x, target_y):
        dx, dy = target_x - fig_x, target_y - fig_y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0.001:
            self.dir_x, self.dir_y = dx / dist, dy / dist
        else:
            self.dir_x, self.dir_y = 1.0, 0.0
        # Spawn slightly ahead of the figure so it clears the sprite
        self.x = fig_x + self.dir_x * (config.ULTC_RADIUS * 0.5)
        self.y = fig_y + self.dir_y * (config.ULTC_RADIUS * 0.5)
        self.age = 0
        self.dist_travelled = 0.0
        self.centre_angle_deg = angle_deg_qt(self.dir_x, self.dir_y)
        self.reveal_t = 0.0   # 0.0 = hidden, 1.0 = fully revealed (ramps over ~10 ticks)

    @property
    def alive(self):
        return self.age < config.ULTC_LIFETIME

    def update(self):
        self.x += self.dir_x * config.ULTC_SPEED
        self.y += self.dir_y * config.ULTC_SPEED
        self.dist_travelled += config.ULTC_SPEED
        self.age += 1
        # Reveal sweeps in over ~10 ticks (bottom-to-top materialise)
        if self.reveal_t < 1.0:
            self.reveal_t = min(1.0, self.reveal_t + 0.1)

    def check_bullet_erase(self, bx, by):
        """True if bullet (bx, by) lies within the blade's arc band."""
        r = config.ULTC_RADIUS
        margin = config.ULTC_WIDTH_OUTER * 0.5 + 10.0
        ddx, ddy = bx - self.x, by - self.y
        d = (ddx * ddx + ddy * ddy) ** 0.5
        if d < 0.001 or not (r - margin <= d <= r + margin):
            return False
        diff = angle_diff(angle_deg_qt(ddx, ddy), self.centre_angle_deg)
        return abs(diff) <= config.ULTC_SPAN / 2.0

    def check_figure_hit(self, fx, fy):
        """True if figure (fx, fy) is within the blade's damage band."""
        r = config.ULTC_RADIUS
        margin = config.ULTC_HIT_FIGURE_DIST
        ddx, ddy = fx - self.x, fy - self.y
        d = (ddx * ddx + ddy * ddy) ** 0.5
        if d < 0.001 or not (r - margin <= d <= r + margin):
            return False
        diff = angle_diff(angle_deg_qt(ddx, ddy), self.centre_angle_deg)
        return abs(diff) <= config.ULTC_SPAN / 2.0

    def draw(self, p, pen):
        """Draw the blade: dark filled body + bright blue rim, with reveal/fade."""
        if not self.alive:
            return

        r = config.ULTC_RADIUS
        half_span = config.ULTC_SPAN / 2.0
        segs = config.ULTC_SEGS

        # --- Global alpha ---
        # Fade phase: after ULTC_FADE_DIST, fade linearly to 0
        if self.dist_travelled > config.ULTC_FADE_DIST:
            excess = self.dist_travelled - config.ULTC_FADE_DIST
            # Fade over ~200 px of additional travel
            fade_alpha = max(0.0, 1.0 - excess / 200.0)
        else:
            fade_alpha = 1.0

        if fade_alpha <= 0.0:
            return

        # The arc's orientation: centre_angle_deg points in the travel direction.
        # We want the OPEN side of the crescent (concave) to face FORWARD so it
        # looks like the images — the blade curves away from travel direction.
        # Qt arcTo: 0° = 3 o'clock, angles go CCW in screen-space (y-down).
        # We lay the arc centred on (self.x, self.y) at radius r, with the
        # bounding box rect_x, rect_y, diam, diam.
        start_deg = self.centre_angle_deg - half_span
        step = config.ULTC_SPAN / segs
        rect_x, rect_y = self.x - r, self.y - r
        diam = r * 2

        # Reveal: bottom→top sweep.  segment 0 is at start_deg (one end of the
        # blade), segment segs-1 is at the other end.  We reveal from seg 0
        # upward so the blade appears to grow from one tip across to the other.
        reveal_segs = int(self.reveal_t * segs)

        # --- Fade is bottom-to-top during the fade-out phase ---
        # "Bottom" = lower y on screen = higher segment index (since arc sweeps
        # CCW in Qt screen space).  We fade from seg segs-1 downward.
        if self.dist_travelled > config.ULTC_FADE_DIST:
            excess = self.dist_travelled - config.ULTC_FADE_DIST
            fade_segs_from_bottom = int((excess / 200.0) * segs)
        else:
            fade_segs_from_bottom = 0

        p.setBrush(Qt.NoBrush)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)

        for i in range(segs):
            if i >= reveal_segs:
                continue   # not yet revealed
            # Fade bottom-to-top: segments near end of arc fade first
            visible_from_bottom = segs - 1 - i
            if visible_from_bottom < fade_segs_from_bottom:
                continue

            seg_t = (i + 0.5) / segs   # 0 = one tip, 1 = other tip

            # Taper: thickest in the middle, tapered at tips
            taper = 1.0 - abs(seg_t - 0.5) * 2.0   # 0 at tips, 1 at midpoint
            taper = taper ** 0.5

            a0 = start_deg + i * step

            # --- Pass 1: dark body ---
            body_w = config.ULTC_WIDTH_OUTER * (0.4 + 0.6 * taper)
            body_alpha = int(215 * fade_alpha)
            pen.setWidthF(body_w)
            pen.setColor(QColor(8, 8, 12, body_alpha))
            p.setPen(pen)
            path = QPainterPath()
            path.arcMoveTo(rect_x, rect_y, diam, diam, a0)
            path.arcTo(rect_x, rect_y, diam, diam, a0, step)
            p.drawPath(path)

            # --- Pass 2: bright blue rim (outer edge) ---
            rim_w = config.ULTC_WIDTH_INNER * (0.3 + 0.7 * taper)
            rim_alpha = int(220 * fade_alpha)
            pen.setWidthF(rim_w)
            pen.setColor(QColor(30, 120, 200, rim_alpha))
            p.setPen(pen)
            # Rim arc is offset slightly outward — draw at radius r+rim_offset
            rim_off = config.ULTC_WIDTH_OUTER * 0.3
            rr = r + rim_off
            rr_rect_x, rr_rect_y = self.x - rr, self.y - rr
            rr_diam = rr * 2
            rim_path = QPainterPath()
            rim_path.arcMoveTo(rr_rect_x, rr_rect_y, rr_diam, rr_diam, a0)
            rim_path.arcTo(rr_rect_x, rr_rect_y, rr_diam, rr_diam, a0, step)
            p.drawPath(rim_path)


def fire_sword_ultimate(fig, target_x, target_y):
    """Spawn the first UltimateCrescent and arm the 2nd via the pending counter."""
    c = fig.combat
    uc = UltimateCrescent(fig.x, fig.y, target_x, target_y)
    c.ult_crescents.append(uc)
    c.ult_crescent_pending = config.ULTC_SECOND_DELAY_TICKS


def tick_ult_crescents(fig, target_x, target_y):
    """Advance ult_crescents list and fire the delayed 2nd shot when due.
    Called from advance_combat every tick for melee figures."""
    c = fig.combat
    # Tick the 2nd-shot delay counter
    if c.ult_crescent_pending > 0:
        c.ult_crescent_pending -= 1
        if c.ult_crescent_pending == 0:
            uc2 = UltimateCrescent(fig.x, fig.y, target_x, target_y)
            c.ult_crescents.append(uc2)
    # Advance + cull
    if c.ult_crescents:
        live = []
        for uc in c.ult_crescents:
            uc.update()
            if uc.alive:
                live.append(uc)
        c.ult_crescents = live


# ---------------------------------------------------------------------------
# Swordsman attack FSM — operates on a Figure's components.
# Returns True if it consumed the tick (motion should be skipped this tick),
# False if the figure should still take a normal movement step (faithful to the
# original, which does one chase step on the dash-trigger tick).
# ---------------------------------------------------------------------------

def tick_parry_cooldown(fig):
    """Tick parry cooldown and stance timers every frame (regardless of other state)."""
    c = fig.combat
    if c.parry_cooldown_ticks > 0:
        c.parry_cooldown_ticks -= 1
    if c.parry_stance_ticks > 0:
        c.parry_stance_ticks -= 1
        if c.parry_stance_ticks <= 0:
            c.parrying = False


def trigger_parry(fig):
    """Arm the parry stance if the cooldown has expired. Returns True if parry was triggered."""
    c = fig.combat
    if c.parry_cooldown_ticks > 0:
        return False
    c.parrying = True
    c.parry_stance_ticks = config.PARRY_STANCE_TICKS
    c.parry_cooldown_ticks = config.PARRY_COOLDOWN_TICKS
    # Play the slash animation to show the parry deflect
    c.slash_phase = c.slash_idx = c.slash_tick = 0
    return True


def advance_combat(fig, slash_target, fallback):
    t = fig.transform
    c = fig.combat
    m = fig.motion
    rng = fig.personality.rng
    bundle = fig.render.bundle

    if not bundle.slash:
        return False  # this mode has no melee capability

    # --- Attack-string cooldown tick (~1 s after a completed 3-hit string) ---
    if c.attack_cooldown_ticks > 0:
        c.attack_cooldown_ticks -= 1
    # --- Follow-up type lock tick (0.2 s window after a 50/50 pick) ---
    if c.followup_lock_ticks > 0:
        c.followup_lock_ticks -= 1
        if c.followup_lock_ticks <= 0:
            c.followup_lock_type = 0

    # --- Follow-up dashslash delay: count down, then launch a STRAIGHT dash ---
    if c.combo_delay_ticks > 0:
        c.combo_delay_ticks -= 1
        if c.combo_delay_ticks == 0 and slash_target is not None:
            tx, ty = slash_target
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

    # -----------------------------------------------------------------------
    # ARC PHASES — shared by the primary arcslash (shrinking-radius approach)
    # and the follow-up arcslash (recoil + constant-radius 150° orbit).
    # -----------------------------------------------------------------------

    # --- Arc recoil: dash directly away from target after a hit (follow-up arcslash) ---
    if c.arc_recoiling:
        ox, oy = t.x, t.y
        c.arc_recoil_ticks -= 1
        t.x += c.slash_vx
        t.y += c.slash_vy
        if c.arc_recoil_ticks <= 0:
            c.arc_recoiling = False
            # Arm the constant-radius orbit around the hit target.
            cx_, cy_ = c.arc_center_x, c.arc_center_y
            dx_, dy_ = t.x - cx_, t.y - cy_
            c.arc_orbit_r = max((dx_*dx_ + dy_*dy_)**0.5, 20.0)
            c.arc_r_start = c.arc_orbit_r
            c.arc_r_end = c.arc_orbit_r
            c.arc_start_angle = math.atan2(dy_, dx_)
            arc_rad = math.radians(config.ARC_ORBIT_ANGLE_DEG) * c.arc_combo_dir
            c.arc_end_angle = c.arc_start_angle + arc_rad
            c.arc_repo_t = 0
            c.arc_repo_steps = config.ARC_REPO_TICKS
            c.arc_repositioning = True
        fig.face(ox, oy)
        fig.trail.update(t.x, t.y, t.facing_left, True, False)
        fig.render.is_moving = True
        fig.render.advance()
        return True

    # --- Arc travel: curved path around the target.  Radius interpolates from
    #     arc_r_start to arc_r_end (constant for the follow-up orbit; shrinking
    #     for the primary arcslash approach).  Ends with a dash-in. ---
    if c.arc_repositioning:
        ox, oy = t.x, t.y
        c.arc_repo_t += 1
        # Smooth cubic ease-in-out for natural arc travel
        raw = c.arc_repo_t / max(c.arc_repo_steps, 1)
        ease = raw * raw * (3.0 - 2.0 * raw)
        angle = c.arc_start_angle + (c.arc_end_angle - c.arc_start_angle) * ease
        radius = c.arc_r_start + (c.arc_r_end - c.arc_r_start) * ease
        t.x = c.arc_center_x + math.cos(angle) * radius
        t.y = c.arc_center_y + math.sin(angle) * radius
        if c.arc_repo_t >= c.arc_repo_steps:
            c.arc_repositioning = False
            # Launch the dash-in toward the LIVE target if available.
            if slash_target is not None:
                tx_, ty_ = slash_target
            else:
                tx_, ty_ = c.arc_center_x, c.arc_center_y
            ddx, ddy = tx_ - t.x, ty_ - t.y
            ddist = (ddx*ddx + ddy*ddy)**0.5
            lspd = m.speed * config.SLASH_SPEED_MUL
            if ddist > 1.0:
                inv = 1.0 / ddist
                c.slash_vx = ddx * inv * lspd
                c.slash_vy = ddy * inv * lspd
            # else: keep current slash velocity direction — we are on top of the
            # target and the hit check will fire on the first dash tick anyway.
            c.slash_dist_budget = max(ddist * 4.0, lspd * 2.0)
            c.dashing = True
            c.rebounding = False
            # Alternate orbit direction for the next arc (CW ↔ CCW).
            c.arc_combo_dir *= -1
        fig.face(ox, oy)
        fig.trail.update(t.x, t.y, t.facing_left, True, False)
        fig.render.is_moving = True
        fig.render.advance()
        return True

    # --- Crescent advance + cull (emission happens on dash hit) ---
    if c.crescents:
        live = []
        for cr in c.crescents:
            cr.update()
            if cr.alive:
                live.append(cr)
        c.crescents = live

    # --- Ultimate crescent advance + 2nd-shot delay (always tick for melee) ---
    tick_ult_crescents(fig, fallback[0], fallback[1])

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
                    # --- Launch the queued follow-up attack, if any ---
                    if c.followup_pending == 2:
                        # Follow-up ARCSLASH: recoil away, then 150° orbit, then dash-in.
                        c.followup_pending = 0
                        ndx = t.x - c.arc_center_x
                        ndy = t.y - c.arc_center_y
                        ndist = (ndx*ndx + ndy*ndy)**0.5
                        if ndist > 0.001:
                            nx_, ny_ = ndx / ndist, ndy / ndist
                        else:
                            nx_, ny_ = 1.0, 0.0
                        recoil_spd = config.ARC_RECOIL_PX / max(config.ARC_RECOIL_TICKS, 1)
                        c.slash_vx = nx_ * recoil_spd
                        c.slash_vy = ny_ * recoil_spd
                        c.arc_recoil_ticks = config.ARC_RECOIL_TICKS
                        c.arc_recoiling = True
                    elif c.followup_pending == 1:
                        # Follow-up DASHSLASH: randomised pause, then straight dash
                        # (gives the target breathing room after knockback).
                        c.followup_pending = 0
                        c.combo_delay_ticks = rng.randint(
                            config.COMBO_TRAVEL_TICKS_MIN,
                            config.COMBO_TRAVEL_TICKS_MAX)
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
                    # ---------------------------------------------------------
                    # ATTACK STRING — count the hit; queue a follow-up (50/50
                    # dashslash vs arcslash with a 0.2 s type lock) until the
                    # string reaches ATTACK_STRING_MAX_HITS, then cool down.
                    # ---------------------------------------------------------
                    c.arc_center_x = float(tx)
                    c.arc_center_y = float(ty)
                    chain = False
                    if c.attack_cooldown_ticks <= 0:
                        c.attack_hits += 1
                        if c.attack_hits < config.ATTACK_STRING_MAX_HITS:
                            chain = True
                        else:
                            # String complete — reset and start the ~1 s cooldown.
                            c.attack_hits = 0
                            c.attack_cooldown_ticks = config.ATTACK_STRING_COOLDOWN_TICKS
                    if chain:
                        # Pick the follow-up type: locked type wins within the
                        # 0.2 s window, otherwise a fresh 50/50 roll locks it.
                        if c.followup_lock_ticks > 0 and c.followup_lock_type:
                            ftype = c.followup_lock_type
                        else:
                            ftype = 1 if rng.random() < 0.5 else 2
                            c.followup_lock_type = ftype
                            c.followup_lock_ticks = config.FOLLOWUP_TYPE_LOCK_TICKS
                        c.followup_pending = ftype
                        # Stop dead and play the slash; the follow-up launches
                        # when the animation completes.
                        c.dashing = c.rebounding = False
                        c.slashing = True
                        c.slash_phase = c.slash_idx = c.slash_tick = 0
                        c.slash_vx = c.slash_vy = 0.0
                    else:
                        # No chain (string finished or on cooldown): reflect
                        # velocity off the contact and rebound away.
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
                        # Missed string — clear hit progress so the next primary
                        # starts a fresh string.
                        c.attack_hits = 0
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

    # --- Primary attack trigger (arms an attack; does NOT consume the tick) ---
    # 50/50 between:
    #   dashslash — straight dash at the target (classic)
    #   arcslash  — curved approach sweeping around the target, ending in a slash
    if (slash_target is not None and not m.bouncing and not m.bounce_ending
            and c.combo_delay_ticks == 0):
        tx, ty = slash_target
        dx, dy = tx - t.x, ty - t.y
        dist = (dx * dx + dy * dy) ** 0.5
        if config.SLASH_HIT_RADIUS < dist <= config.SLASH_RADIUS:
            c.attack_hits = 0  # fresh string
            if rng.random() < 0.5:
                # --- Primary DASHSLASH: straight in ---
                inv = 1.0 / dist
                lspd = m.speed * config.SLASH_SPEED_MUL
                c.slash_vx = dx * inv * lspd
                c.slash_vy = dy * inv * lspd
                c.slash_dist_budget = dist * 4.0
                c.dashing = True
                c.rebounding = False
            else:
                # --- Primary ARCSLASH: curved approach, radius shrinking from
                #     current distance down to just outside the hit radius, then
                #     a short dash-in lands the slash from a new direction. ---
                c.arc_center_x = float(tx)
                c.arc_center_y = float(ty)
                c.arc_combo_dir = rng.choice([1, -1])
                c.arc_r_start = dist
                c.arc_r_end = config.SLASH_HIT_RADIUS * 1.5
                c.arc_start_angle = math.atan2(t.y - ty, t.x - tx)
                sweep = math.radians(config.ARC_APPROACH_SWEEP_DEG) * c.arc_combo_dir
                c.arc_end_angle = c.arc_start_angle + sweep
                c.arc_repo_t = 0
                c.arc_repo_steps = config.ARC_APPROACH_TICKS
                c.arc_repositioning = True

    return False


