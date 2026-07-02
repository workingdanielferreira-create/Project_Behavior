"""
Application layer — World (central state + factory) and Overlay (the Qt widget).

Overlay is deliberately thin: it owns the window, polls the cursor, runs the
systems pipeline, and paints.  All per-tick logic lives in systems; all shared
state and entity creation lives in World.
"""

import os
import sys
import time
import traceback

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import (QPainter, QCursor, QPen, QColor, QRadialGradient,
                         QFont, QPixmap)

from . import config, modes, systems, ai, action_log, combat
from . import platform_win as win
from .assets import AssetLibrary
from .figure import Figure
from .ipc import IPCBridge
from .palette import lut_for_index, lut_for_mode

# crash_log replaced by action_log.crash() — see laser/action_log.py



# ---------------------------------------------------------------------------
# Collision-dot sprite cache — one pre-rendered pixmap per rainbow hue.
# The dot's lifetime spans ~50 ticks, so at most ~50 hue buckets are cached.
# Fade is applied with painter opacity instead of re-building gradients.
# ---------------------------------------------------------------------------
_DOT_SPRITES = {}


def _dot_sprite(hue, rad):
    key = (hue, rad)
    entry = _DOT_SPRITES.get(key)
    if entry is None:
        size = rad * 2 + 2
        c = size / 2.0
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        qp = QPainter(pm)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setPen(Qt.NoPen)
        col = QColor.fromHsv(hue, 255, 255)
        r2, g2, b2 = col.red(), col.green(), col.blue()
        gr = QRadialGradient(c, c, rad)
        gr.setColorAt(0.0, QColor(255, 255, 255, 255))
        gr.setColorAt(0.35, QColor(r2, g2, b2, 255))
        gr.setColorAt(1.0, QColor(r2, g2, b2, 0))
        qp.setBrush(gr)
        qp.drawEllipse(0, 0, size, size)
        qp.end()
        entry = (pm, size // 2)
        _DOT_SPRITES[key] = entry
    return entry

class World:
    """Central mutable state plus the figure factory and high-level commands."""

    def __init__(self, assets, screen_w, screen_h, ipc):
        self.assets = assets
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.ipc = ipc

        self.figures = []
        self.mode_key = config.MODE_ORDER[0]
        self.projectiles = []
        self.shoot_ticks = 0   # shared non-battle firing cadence counter
        self.shot_phase = 0       # current runner cycle phase (0=cone,1=zigzag,2=homing)
        self.shot_pause_ticks = 0 # counts down the inter-cycle pause

        # Flags
        self.runner_on = True
        self.collision_on = False
        self.path_follow = False
        self.runaway = False
        self.shoot_mode = False

        # Cursor + tick
        self.cursor = (screen_w // 2, screen_h // 2)
        self.global_tick = 0

        # Battle state (wired stage 3)
        self.battle_mode = False
        self.partner_figures = []
        self.enemy_projs = []
        self.intercepted_bullets = set()

        # Collision impact dots: list of [x, y, age] (drawn + culled in paintEvent)
        self.collision_dots = []

        # Slash FX state
        self.hitstop_ticks = 0              # >0 = world frozen (big-hit freeze)
        self.hitstop_broadcast_pending = False  # send freeze signal to partner
        self.impact_rings = []              # [x, y, age, max_radius] shockwaves
        self.muzzle_flashes = []            # [x, y, age, r, g, b] firing flashes
        self.sparks = []                    # [x, y, vx, vy, age, r, g, b]

        # Input bookkeeping
        self._ctrl_prev = False
        self.ctrl_used = False
        self._quit = False

        self.add_figure()

        # Action log — init after all state is ready
        _launcher_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        action_log.init(log_dir=_launcher_dir, enabled=config.LOG_ENABLED)
        action_log.install_excepthook()

    # --- factory -----------------------------------------------------------
    @property
    def mode(self):
        return modes.get_mode(self.mode_key)

    def add_figure(self):
        if len(self.figures) >= config.MAX_FIGURES:
            return False
        i = len(self.figures)
        fig = Figure(self.mode, self.assets.bundle(self.mode_key),
                     lut_for_mode(self.mode_key, i), i, self.screen_w, self.screen_h)
        self.figures.append(fig)
        return True

    def remove_figure(self):
        if self.figures:
            self.figures.pop()
            return True
        return False

    # --- commands ----------------------------------------------------------
    def cycle_mode(self, delta):
        order = modes.ordered_modes()
        if not order:
            return
        i = (order.index(self.mode_key) + delta) % len(order)
        new_key = order[i]
        if new_key == self.mode_key:
            return
        self.mode_key = new_key
        mode = self.mode
        bundle = self.assets.bundle(new_key)
        for fig in self.figures:
            fig.set_mode(mode, bundle)
            fig.lut = lut_for_mode(new_key, fig.index)
            fig.trail.lut = fig.lut

    def toggle_shoot_mode(self):
        self.shoot_mode = not self.shoot_mode
        if not self.shoot_mode:
            self.projectiles.clear()
            self.muzzle_flashes.clear()
            self.shoot_ticks = 0
            self.shot_phase = 0
            self.shot_pause_ticks = 0
            for fig in self.figures:
                fig.combat.reset()

    def movement_target(self, fig):
        """Where this figure moves toward this tick."""
        if self.battle_mode and self.partner_figures:
            return ai.battle_target(self, fig)
        return self.cursor

    def melee_target(self, fig):
        """Dash/slash target for a melee figure, or None if it shouldn't attack.
        Non-battle: the cursor while attack mode is on. Battle: nearest enemy,
        but only while attack mode is on (otherwise it just chases)."""
        if not fig.mode.uses_melee():
            return None
        if self.battle_mode and self.partner_figures:
            return self._nearest_enemy(fig.x, fig.y) if self.shoot_mode else None
        if self.shoot_mode:
            return self.cursor
        return None

    def _nearest_enemy(self, fx, fy):
        best_sq = float("inf")
        best = (fx, fy)
        for ex, ey, _dash, _parry in self.partner_figures:
            d = (ex - fx) ** 2 + (ey - fy) ** 2
            if d < best_sq:
                best_sq = d
                best = (ex, ey)
        return best

    def request_quit(self):
        self._quit = True

    @property
    def quitting(self):
        return self._quit


class Overlay(QWidget):

    def __init__(self):
        super().__init__()
        win.lower_process_priority()

        sd = os.path.dirname(os.path.abspath(sys.argv[0])) \
            if getattr(sys, "frozen", False) else _asset_dir()
        assets = AssetLibrary(sd)
        if not assets.ok:
            print("No frames loaded! Place Picture*.png and standing*.png "
                  "next to this script.")
            sys.exit(1)

        screen = QApplication.primaryScreen().geometry()
        self.world = World(assets, screen.width(), screen.height(), IPCBridge())
        self.pipeline = systems.build_pipeline()

        self._pen = QPen()
        self._pen.setCapStyle(Qt.RoundCap)
        self._hp_font = QFont("Consolas", config.HP_DISPLAY_FONT_SIZE, QFont.Bold)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Tool | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.showFullScreen()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._safe_tick)
        self._timer.start(config.TICK_MS)

    def _safe_tick(self):
        try:
            self._tick()
        except Exception as e:
            action_log.crash("_tick", e)

    def _tick(self):
        w = self.world
        pos = QCursor.pos()
        w.cursor = (pos.x(), pos.y())

        # --- HIT-STOP: freeze the world for a few ticks on big hits ---
        # Input and IPC keep running (heartbeat, partner sync, freeze
        # broadcast); combat, motion, collisions, and bullets all pause.
        # FX (rings, sparks, ghosts) keep animating in paint for punch.
        if w.hitstop_ticks > 0:
            w.hitstop_ticks -= 1
            for system in self.pipeline:
                if isinstance(system, (systems.InputSystem, systems.IpcSystem)):
                    try:
                        system.update(w)
                    except Exception as e:
                        action_log.crash(type(system).__name__, e)
                if w.quitting:
                    self._shutdown()
                    return
            self.update()
            return

        for system in self.pipeline:
            try:
                system.update(w)
            except Exception as e:
                action_log.crash(type(system).__name__, e)
            if w.quitting:
                self._shutdown()
                return

        w.global_tick += 1
        self.update()

    def _shutdown(self):
        self.world.ipc.release()
        QApplication.quit()

    def paintEvent(self, _):
        try:
            self._paint()
        except Exception as e:
            action_log.crash("paintEvent", e)

    def _paint(self):
        w = self.world
        if not w.runner_on:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        for fig in w.figures:
            fig.draw(p, self._pen)
        for proj in w.projectiles:
            proj.draw(p)
        # Enemy bullets render as comet bolts rotated to their velocity, so
        # they read as fast energy fire even without per-bullet trail history.
        import math as _math
        for ex, ey, evx, evy, er, eg, eb in w.enemy_projs:
            if evx * evx + evy * evy > 0.0001:
                pm, head_x, half_h = combat.bolt_sprite(
                    er, eg, eb, config.PROJ_RADIUS, config.BOLT_STRETCH_CONE)
                p.save()
                p.translate(int(ex), int(ey))
                p.rotate(_math.degrees(_math.atan2(evy, evx)))
                p.drawPixmap(int(-head_x), int(-half_h), pm)
                p.restore()
            else:
                pm, half = combat.bullet_sprite(er, eg, eb, config.PROJ_RADIUS)
                p.drawPixmap(int(ex) - half, int(ey) - half, pm)

        # --- Collision impact dots (rainbow radial, fade after hold period) ---
        if w.collision_dots:
            hold = config.COLLISION_DOT_HOLD
            fade = config.COLLISION_DOT_FADE
            total = hold + fade
            rad = config.COLLISION_DOT_RADIUS
            surviving = []
            p.setPen(Qt.NoPen)
            for dot in w.collision_dots:
                dx, dy, age = dot
                if age < hold:
                    alpha = 255
                else:
                    alpha = int(255 * (1.0 - (age - hold) / fade))
                if alpha > 0:
                    # Rainbow hue cycles from 0–360 over the dot's lifetime
                    hue = int((age / total) * 360) % 360
                    pm, half = _dot_sprite(hue, rad)
                    if alpha < 255:
                        p.setOpacity(alpha / 255.0)
                        p.drawPixmap(int(dx) - half, int(dy) - half, pm)
                        p.setOpacity(1.0)
                    else:
                        p.drawPixmap(int(dx) - half, int(dy) - half, pm)
                    dot[2] += 1
                if age + 1 < total:
                    surviving.append(dot)
            w.collision_dots = surviving

        # --- Impact shockwave rings (expand + fade on every landed slash) ---
        if w.impact_rings:
            live = []
            rpen = self._pen
            p.setBrush(Qt.NoBrush)
            for ring in w.impact_rings:
                rx, ry, age, maxr = ring
                t = age / config.IMPACT_RING_LIFETIME
                if t < 1.0:
                    ease = 1.0 - (1.0 - t) ** 3   # fast start, soft finish
                    rad = maxr * ease
                    alpha = int(220 * (1.0 - t))
                    rpen.setColor(QColor(255, 245, 235, alpha))
                    rpen.setWidthF(config.IMPACT_RING_WIDTH * (1.0 - 0.6 * t))
                    p.setPen(rpen)
                    irad = int(rad)
                    p.drawEllipse(int(rx) - irad, int(ry) - irad,
                                  irad * 2, irad * 2)
                ring[2] += 1
                if ring[2] < config.IMPACT_RING_LIFETIME:
                    live.append(ring)
            w.impact_rings = live

        # --- Impact sparks (white-hot streaks bursting from the hit point) ---
        if w.sparks:
            live = []
            spen = self._pen
            for s in w.sparks:
                sx, sy, svx, svy, age, sr, sg, sb = s
                t = age / config.IMPACT_SPARK_LIFETIME
                if t < 1.0:
                    alpha = int(255 * (1.0 - t))
                    spen.setWidthF(2.0)
                    spen.setColor(QColor(min(255, sr + 120),
                                         min(255, sg + 120),
                                         min(255, sb + 120), alpha))
                    p.setPen(spen)
                    p.drawLine(int(sx - svx), int(sy - svy), int(sx), int(sy))
                s[0] += svx
                s[1] += svy
                s[2] *= 0.88
                s[3] *= 0.88
                s[4] += 1
                if s[4] < config.IMPACT_SPARK_LIFETIME:
                    live.append(s)
            w.sparks = live

        # --- Muzzle flashes (bloom at the firing point of every shot) ---
        if w.muzzle_flashes:
            live = []
            p.setPen(Qt.NoPen)
            for fl in w.muzzle_flashes:
                mx, my, age, fr, fg, fb = fl
                t = age / config.MUZZLE_FLASH_LIFETIME
                if t < 1.0:
                    rad = config.MUZZLE_FLASH_RADIUS * (0.4 + 0.6 * t)
                    a = 1.0 - t
                    grad = QRadialGradient(mx, my, rad)
                    grad.setColorAt(0.0, QColor(255, 255, 255, int(230 * a)))
                    grad.setColorAt(0.4, QColor(fr, fg, fb, int(180 * a)))
                    grad.setColorAt(1.0, QColor(fr, fg, fb, 0))
                    p.setBrush(grad)
                    ir = int(rad)
                    p.drawEllipse(int(mx) - ir, int(my) - ir, ir * 2, ir * 2)
                fl[2] += 1
                if fl[2] < config.MUZZLE_FLASH_LIFETIME:
                    live.append(fl)
            w.muzzle_flashes = live

        # --- HP readout — bottom-right, one entry per figure ---
        if w.figures:
            p.setFont(self._hp_font)
            fm = p.fontMetrics()
            line_h = fm.height() + 4
            base_y = w.screen_h - config.HP_DISPLAY_MARGIN_B
            for idx, fig in enumerate(w.figures):
                hp_val = fig.personality.hp
                max_hp = fig.personality.max_hp
                label = f"{hp_val} HP"
                text_w = fm.horizontalAdvance(label)
                _hp_offset = 0 if fig.mode.uses_melee() else 70
                draw_x = w.screen_w - text_w - config.HP_DISPLAY_MARGIN_R - _hp_offset
                draw_y = base_y - idx * line_h
                # Pick colour from the figure's lut midpoint
                r2, g2, b2 = fig.lut[128]
                # Dim text slightly when low HP (below 25 %)
                alpha = 255 if hp_val > max_hp * 0.25 else 160
                # Glow pass (offset shadow for neon feel)
                p.setPen(QColor(r2, g2, b2, max(30, alpha // 4)))
                p.drawText(draw_x - 1, draw_y + 1, label)
                # Main text
                p.setPen(QColor(r2, g2, b2, alpha))
                p.drawText(draw_x, draw_y, label)

        p.end()

    def closeEvent(self, event):
        action_log.close()
        self.world.ipc.release()
        super().closeEvent(event)


def _asset_dir():
    """Directory the sprite PNGs live in — the project root (one above laser/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    overlay = Overlay()
    ret = app.exec_()
    overlay.world.ipc.release()
    sys.exit(ret)




