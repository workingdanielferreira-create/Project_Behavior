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

from . import config, modes, systems, ai, action_log
from . import platform_win as win
from .assets import AssetLibrary
from .figure import Figure
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

class SideState:
    """Everything one fighter's side owns: its figures, its bullets, its
    firing cadence, and its snapshot view of the opponent.  Two of these in
    one World replace what used to be two whole processes."""

    def __init__(self, mode_key):
        self.figures = []
        self.projectiles = []
        self.mode_key = mode_key
        self.shoot_ticks = 0
        self.shot_phase = 0
        self.shot_pause_ticks = 0
        self.intercepted_bullets = set()
        self.partner_figures = []   # opponent snapshot: (x, y, dash, parry)
        self.enemy_projs = []       # opponent bullets: (x,y,vx,vy,r,g,b,dmg,proj)
        self.clones = []            # this side's own HPTClone instances
                                    # (see combat.HPTClone / hp_threshold_clones)


class World:
    """Central mutable state plus the figure factory and high-level commands."""

    def __init__(self, assets, screen_w, screen_h):
        self.assets = assets
        self.screen_w = screen_w
        self.screen_h = screen_h

        # Two locally-hosted sides. Side 0 = P1 (always fielded, key '1'
        # cycles its character), side 1 = P2 (key '2' cycles characters and
        # then OFF).  Battle mode is simply "both sides have figures" — the
        # per-tick pipeline runs once per fielded side, each side seeing the
        # other through read-only snapshots (partner_figures / enemy_projs),
        # so the two fighters keep fully independent decision streams
        # (separate Personality RNGs, separate cadences, separate FSMs).
        self.sides = [SideState(config.MODE_ORDER[0]),
                      SideState(config.MODE_ORDER[0])]
        self.side_idx = 0
        self._dead = []   # figures killed this tick; culled next refresh

        # Bound view of the current side (refreshed by bind_side).
        self.figures = self.sides[0].figures
        self.mode_key = self.sides[0].mode_key
        self.projectiles = self.sides[0].projectiles
        self.clones = self.sides[0].clones
        self.shoot_ticks = 0   # per-side firing cadence counter (bound)
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

        # Battle state — bound per-side views of the opposing side.
        self.battle_mode = False
        self.partner_figures = []
        self.enemy_projs = []
        self.intercepted_bullets = set()

        # Collision impact dots: list of [x, y, age] (drawn + culled in paintEvent)
        self.collision_dots = []

        # Slash FX state
        self.hitstop_ticks = 0              # >0 = world frozen (big-hit freeze)
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

    def add_figure(self, side_idx=0):
        side = self.sides[side_idx]
        if len(side.figures) >= config.MAX_FIGURES:
            return False
        i = len(side.figures)
        # Side 1 figures take the next offset/palette slot so the two sides
        # spawn apart and read as distinct fighters at a glance.
        slot = i + side_idx
        fig = Figure(modes.get_mode(side.mode_key),
                     self.assets.bundle(side.mode_key),
                     lut_for_mode(side.mode_key, slot), slot,
                     self.screen_w, self.screen_h)
        side.figures.append(fig)
        return True

    def remove_figure(self, side_idx=0):
        side = self.sides[side_idx]
        if side.figures:
            side.figures.pop()
            return True
        return False

    # --- commands ----------------------------------------------------------
    def _reskin_side(self, side_idx):
        """Re-apply a side's current mode_key to its live figures."""
        side = self.sides[side_idx]
        mode = modes.get_mode(side.mode_key)
        bundle = self.assets.bundle(side.mode_key)
        for fig in side.figures:
            fig.set_mode(mode, bundle)
            fig.lut = lut_for_mode(side.mode_key, fig.index)
            fig.trail.lut = fig.lut

    def cycle_mode(self, delta, side_idx=0):
        order = modes.ordered_modes()
        if not order:
            return
        side = self.sides[side_idx]
        cur = order.index(side.mode_key) if side.mode_key in order else 0
        new_key = order[(cur + delta) % len(order)]
        if new_key == side.mode_key:
            return
        side.mode_key = new_key
        if side_idx == self.side_idx:
            self.mode_key = new_key
        self._reskin_side(side_idx)

    def cycle_side_char(self, side_idx):
        """Key '1' / '2' character cycling.  P1 (side 0) always keeps a
        fighter: tap to advance through every registered character, wrapping.
        P2 (side 1) cycles through every character and then OFF (side
        cleared, battle ends); tapping again fields the first character."""
        order = modes.ordered_modes()
        if not order:
            return
        side = self.sides[side_idx]
        if not side.figures:
            if side.mode_key not in order:
                side.mode_key = order[0]
            self.add_figure(side_idx)
            return
        cur = order.index(side.mode_key) if side.mode_key in order else -1
        nxt = cur + 1
        if side_idx == 1 and nxt >= len(order):
            side.figures.clear()
            side.projectiles.clear()
            side.mode_key = order[0]
            return
        side.mode_key = order[nxt % len(order)]
        if side_idx == self.side_idx:
            self.mode_key = side.mode_key
        self._reskin_side(side_idx)

    def toggle_shoot_mode(self):
        self.shoot_mode = not self.shoot_mode
        if not self.shoot_mode:
            self.muzzle_flashes.clear()
            self.shoot_ticks = 0
            self.shot_phase = 0
            self.shot_pause_ticks = 0
            self.projectiles.clear()
            for side in self.sides:
                side.projectiles.clear()
                side.clones.clear()
                side.shoot_ticks = side.shot_phase = side.shot_pause_ticks = 0
                for fig in side.figures:
                    fig.combat.reset()

    def movement_target(self, fig):
        """Where this figure moves toward this tick."""
        if fig.mode.kites():
            # Kiting is identical in Solo (target=cursor) and Battle
            # (target=nearest enemy) — ai.kite_target takes a plain point
            # and doesn't know or care which mode it came from.
            if self.battle_mode and self.partner_figures:
                ex, ey = self._nearest_enemy(fig.x, fig.y)
            else:
                ex, ey = self.cursor
            return ai.kite_target(fig, ex, ey)
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

    def on_figure_death(self, fig):
        """A figure reached 0 HP.  Solo keeps the historical behaviour (the
        run ends); in battle the fallen fighter is removed and the survivor
        fights on — the winner stays standing."""
        if self.battle_mode:
            if fig not in self._dead:
                self._dead.append(fig)
        else:
            self.request_quit()

    # --- side binding (one simulation pass per fielded side) ---------------
    def bind_side(self, i):
        s = self.sides[i]
        self.side_idx = i
        self.figures = s.figures
        self.projectiles = s.projectiles
        self.mode_key = s.mode_key
        self.shoot_ticks = s.shoot_ticks
        self.shot_phase = s.shot_phase
        self.shot_pause_ticks = s.shot_pause_ticks
        self.intercepted_bullets = s.intercepted_bullets
        self.partner_figures = s.partner_figures
        self.enemy_projs = s.enemy_projs
        self.clones = s.clones

    def unbind_side(self):
        s = self.sides[self.side_idx]
        s.figures = self.figures
        s.projectiles = self.projectiles
        s.shoot_ticks = self.shoot_ticks
        s.shot_phase = self.shot_phase
        s.shot_pause_ticks = self.shot_pause_ticks
        s.intercepted_bullets = self.intercepted_bullets
        s.enemy_projs = self.enemy_projs
        s.clones = self.clones

    def refresh_battle(self):
        """Start-of-tick sync: cull fallen fighters, decide battle mode, and
        rebuild each side's read-only snapshot of its opponent.  Snapshots are
        frozen for the whole tick so both sides act on the same picture of
        the world — the same one-tick information boundary the fighters have
        always had, which is what keeps their decisions independent."""
        if self._dead:
            for side in self.sides:
                if any(f in self._dead for f in side.figures):
                    side.figures[:] = [f for f in side.figures
                                       if f not in self._dead]
                    if not side.figures:
                        # The side is eliminated — its in-flight shots (and
                        # any stationary clones) die with it (an unfielded
                        # side is never simulated).
                        side.projectiles.clear()
                        side.clones.clear()
            self._dead.clear()
        self.battle_mode = bool(self.sides[0].figures
                                and self.sides[1].figures)
        for i, side in enumerate(self.sides):
            other = self.sides[1 - i]
            if self.battle_mode:
                side.partner_figures = [
                    (f.x, f.y, bool(f.combat.dashing),
                     bool(f.combat.parrying))
                    for f in other.figures if f.transform.init]
                # Real bullets only (hit_r_sq > 0); cosmetic deflects and
                # splinters can never deal damage across the boundary.  The
                # live Projectile rides along as tuple[8] so an interception
                # (petal / crescent / parry / scatter) truly destroys it.
                side.enemy_projs = [
                    (pr.x, pr.y, pr.vx, pr.vy, pr.r, pr.g, pr.b,
                     float(getattr(pr, "damage", 1.0)), pr)
                    for pr in other.projectiles
                    if pr.alive and pr.hit_r_sq > 0.0]
            else:
                side.partner_figures = []
                side.enemy_projs = []
                side.intercepted_bullets.clear()
        # Deliver dash-slash knockback landed last tick to the other side.
        for i, side in enumerate(self.sides):
            other = self.sides[1 - i]
            for f in side.figures:
                if f.combat.hit_pending:
                    f.combat.hit_pending = False
                    if not self.battle_mode:
                        continue
                    for ef in other.figures:
                        m = ef.motion
                        if m.bouncing or m.bounce_ending:
                            continue
                        m.bounce_vx = f.combat.hit_vx
                        m.bounce_vy = f.combat.hit_vy
                        m.bouncing = True

    def cinematic_frozen(self, i):
        """True while a figure on ANOTHER fielded side is mid vanish-cut —
        side `i`'s entire pipeline pass is skipped, freezing its figures
        AND its in-flight projectiles until the cut completes.  A side
        running its own vanish-cut is never frozen (own ult takes
        precedence), so two simultaneous cuts play out instead of
        deadlocking each other.  Generic and data-driven: any character
        whose ultimate_playback.style is 'vanish_cut' gets this for free.
        Solo has no opposing fielded side, so nothing freezes — the code
        path is identical in Solo and Battle."""
        own = self.sides[i]
        for f in own.figures:
            if f.combat.vc_phase != 0:
                return False
        for j in self.fielded_sides():
            if j == i:
                continue
            for f in self.sides[j].figures:
                if f.combat.vc_phase != 0:
                    return True
        return False

    def fielded_sides(self):
        return [i for i, s in enumerate(self.sides) if s.figures]

    def all_figures(self):
        for s in self.sides:
            for f in s.figures:
                yield f

    def all_projectiles(self):
        for s in self.sides:
            for pr in s.projectiles:
                yield pr

    def all_clones(self):
        for s in self.sides:
            for c in s.clones:
                yield c

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
        self.world = World(assets, screen.width(), screen.height())
        self.input = systems.InputSystem()
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
        # Input keeps running; combat, motion, collisions, and bullets all
        # pause — for BOTH sides at once, since they now share one clock.
        # FX (rings, sparks, ghosts) keep animating in paint for punch.
        if w.hitstop_ticks > 0:
            w.hitstop_ticks -= 1
            try:
                self.input.update(w)
            except Exception as e:
                action_log.crash("InputSystem", e)
            if w.quitting:
                self._shutdown()
                return
            self.update()
            return

        try:
            self.input.update(w)
        except Exception as e:
            action_log.crash("InputSystem", e)
        if w.quitting:
            self._shutdown()
            return

        # One simulation pass per fielded side.  Snapshots are rebuilt once,
        # up front, so both sides read the same frozen picture of each other
        # regardless of pass order — preserving the independent, reactive
        # feel of two fighters thinking for themselves.
        w.refresh_battle()
        for i in w.fielded_sides():
            # Cinematic freeze: a vanish-cut on the other side suspends this
            # side's whole pass (combat, motion, collisions, projectiles).
            # Rendering still paints the frozen pose each frame.
            if w.cinematic_frozen(i):
                continue
            w.bind_side(i)
            for system in self.pipeline:
                try:
                    system.update(w)
                except Exception as e:
                    action_log.crash(type(system).__name__, e)
                if w.quitting:
                    self._shutdown()
                    return
            w.unbind_side()

        w.global_tick += 1
        self.update()

    def _shutdown(self):
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
        for fig in w.all_figures():
            fig.draw(p, self._pen)
        # Every bullet on screen is a live Projectile drawn with its own
        # authored visuals — both sides render identically, no downgraded
        # "enemy dot" pass.
        for proj in w.all_projectiles():
            proj.draw(p)
        # HP-threshold stationary clones (glowing-orb marker + orbiting sphere).
        for clone in w.all_clones():
            clone.draw(p)

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

        # --- HP readout — bottom-right, one entry per figure (both sides) ---
        _hp_rows = [(si, fig) for si, s in enumerate(w.sides)
                    for fig in s.figures]
        if _hp_rows:
            p.setFont(self._hp_font)
            fm = p.fontMetrics()
            line_h = fm.height() + 4
            base_y = w.screen_h - config.HP_DISPLAY_MARGIN_B
            _battle = w.battle_mode
            for idx, (side_i, fig) in enumerate(_hp_rows):
                hp_val = fig.personality.hp
                max_hp = fig.personality.max_hp
                label = (f"P{side_i + 1} {hp_val} HP" if _battle
                         else f"{hp_val} HP")
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
        super().closeEvent(event)


def _asset_dir():
    """Directory the sprite PNGs live in — the project root (one above laser/)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    overlay = Overlay()
    ret = app.exec_()
    sys.exit(ret)




