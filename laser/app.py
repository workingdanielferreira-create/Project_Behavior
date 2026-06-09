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
from PyQt5.QtGui import QPainter, QCursor, QPen, QColor, QRadialGradient

from . import config, modes, systems, ai, action_log
from . import platform_win as win
from .assets import AssetLibrary
from .figure import Figure
from .ipc import IPCBridge
from .palette import lut_for_index

_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "laser_cursor_crash.log")


def crash_log(label, exc):
    try:
        with open(_LOG_PATH, "a") as f:
            f.write("[%s] %s: %s\n%s\n" % (
                time.strftime("%H:%M:%S"), label, exc, traceback.format_exc()))
    except Exception:
        pass


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

        # Input bookkeeping
        self._ctrl_prev = False
        self.ctrl_used = False
        self._quit = False

        self.add_figure()

        # Action log — init after all state is ready
        _launcher_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        action_log.init(log_dir=_launcher_dir, enabled=config.LOG_ENABLED)

    # --- factory -----------------------------------------------------------
    @property
    def mode(self):
        return modes.get_mode(self.mode_key)

    def add_figure(self):
        if len(self.figures) >= config.MAX_FIGURES:
            return False
        i = len(self.figures)
        fig = Figure(self.mode, self.assets.bundle(self.mode_key),
                     lut_for_index(i), i, self.screen_w, self.screen_h)
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

    def toggle_shoot_mode(self):
        self.shoot_mode = not self.shoot_mode
        if not self.shoot_mode:
            self.projectiles.clear()
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
        for ex, ey, _dash in self.partner_figures:
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
            crash_log("_tick", e)

    def _tick(self):
        w = self.world
        pos = QCursor.pos()
        w.cursor = (pos.x(), pos.y())

        for system in self.pipeline:
            system.update(w)
            if w.quitting:
                self._shutdown()
                return

        w.global_tick += 1
        self.update()

    def _shutdown(self):
        self.world.ipc.release()
        QApplication.quit()

    def paintEvent(self, _):
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
        _eglwr = config.PROJ_RADIUS * 3
        _erad  = config.PROJ_RADIUS
        for ex, ey, evx, evy, er, eg, eb in w.enemy_projs:
            hx, hy = int(ex), int(ey)
            grad = QRadialGradient(hx, hy, _eglwr)
            grad.setColorAt(0.0, QColor(er, eg, eb, 160))
            grad.setColorAt(1.0, QColor(er, eg, eb, 0))
            p.setPen(Qt.NoPen); p.setBrush(grad)
            p.drawEllipse(hx - _eglwr, hy - _eglwr, _eglwr * 2, _eglwr * 2)
            core = QRadialGradient(hx, hy, _erad)
            core.setColorAt(0.0, QColor(255, 255, 255, 220))
            core.setColorAt(1.0, QColor(er, eg, eb, 180))
            p.setBrush(core)
            p.drawEllipse(hx - _erad, hy - _erad, _erad * 2, _erad * 2)

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
                    col = QColor.fromHsv(hue, 255, 255, alpha)
                    r2, g2, b2 = col.red(), col.green(), col.blue()
                    gr = QRadialGradient(int(dx), int(dy), rad)
                    gr.setColorAt(0.0, QColor(255, 255, 255, alpha))
                    gr.setColorAt(0.35, QColor(r2, g2, b2, alpha))
                    gr.setColorAt(1.0, QColor(r2, g2, b2, 0))
                    p.setBrush(gr)
                    p.drawEllipse(int(dx) - rad, int(dy) - rad, rad * 2, rad * 2)
                    dot[2] += 1
                if age + 1 < total:
                    surviving.append(dot)
            w.collision_dots = surviving

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



