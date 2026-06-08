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
                 "max_age", "hit_r_sq", "trail")

    def __init__(self, fx, fy, vx, vy, color_rgb, trail_len):
        self.x, self.y = float(fx), float(fy)
        self.vx, self.vy = vx, vy
        self.r, self.g, self.b = color_rgb
        self.age = 0
        self.max_age = config.PROJ_MAX_AGE
        self.hit_r_sq = float(config.PROJ_HIT_RADIUS ** 2)
        self.trail = deque(maxlen=max(3, trail_len))

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

        glwr = config.PROJ_RADIUS * 3
        grad = QRadialGradient(hx, hy, glwr)
        grad.setColorAt(0.0, QColor(r, g, b, int(140 * fade)))
        grad.setColorAt(1.0, QColor(r, g, b, 0))
        p.setPen(Qt.NoPen); p.setBrush(grad)
        p.drawEllipse(hx - glwr, hy - glwr, glwr * 2, glwr * 2)

        rad = config.PROJ_RADIUS
        core = QRadialGradient(hx, hy, rad)
        core.setColorAt(0.0, QColor(255, 255, 255, int(240 * fade)))
        core.setColorAt(0.5, QColor(r, g, b, int(210 * fade)))
        core.setColorAt(1.0, QColor(r, g, b, int(140 * fade)))
        p.setBrush(core)
        p.drawEllipse(hx - rad, hy - rad, rad * 2, rad * 2)


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
                            c.slash_dist_budget = ddist * 4.0
                            c.dashing = True
                            c.rebounding = False
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
