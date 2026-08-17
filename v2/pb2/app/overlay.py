"""The overlay shell — the only place Qt meets the simulation.

Identity constraint from v1, preserved exactly: a frameless, always-on-top,
click-through, translucent fullscreen widget.  The desktop is the arena.

What changed from v1:

  * FIXED TIMESTEP ACCUMULATOR.  The sim advances in whole 16 ms ticks; the
    renderer draws as often as it can and interpolates between the last two
    states.  A heavy frame now degrades smoothness instead of changing
    behaviour — and it is what makes the golden checksum meaningful.

  * PAINT IS PURE.  Cue ageing happens in the sim step, never in paintEvent.

  * HYBRID CONTROL.  Arrow keys / WASD drive the possessed fighter's
    movement while its utility brain keeps fighting.  Possession is a
    one-object swap on the actor's brain list — there is no separate
    "player character" type.
"""

import sys
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCursor, QPainter
from PyQt5.QtWidgets import QApplication, QWidget

from ..brains.brains import PlayerBrain, Pad, UtilityBrain
from ..content import load_all
from ..render.painter import Renderer
from ..sim import World

__all__ = ["Overlay", "run"]

TICK_MS = 16
MAX_CATCHUP = 5          # never simulate more than this many ticks per frame


class Overlay(QWidget):
    def __init__(self, characters_dir, seed=None, p1="runner", p2=None,
                 strict=False):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint |
                            Qt.Tool |
                            Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

        self.defs, errors = load_all(characters_dir, strict=True)
        for e in errors:
            print("[pb2] character error:", e, file=sys.stderr)
        if not self.defs:
            raise SystemExit("[pb2] no characters loaded from %s" % characters_dir)

        self.world = World(seed=seed if seed is not None else 20260817,
                           width=screen.width(), height=screen.height(),
                           config={"strict": strict})
        self.renderer = Renderer(self.world)

        self.pad = Pad()
        self.possessed = None
        self.roster = sorted(self.defs)
        self.slot = [None, None]        # actor per side

        self.field(0, p1)
        if p2:
            self.field(1, p2)

        self._accum = 0.0
        self._last = time.perf_counter()
        self._alpha = 1.0
        self.paused = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._frame)
        self.timer.start(TICK_MS // 2)          # render faster than we simulate

        self._keys = KeyPoller(self)

    # ------------------------------------------------------------------
    # roster management
    # ------------------------------------------------------------------
    def field(self, side, key):
        if key not in self.defs:
            return None
        old = self.slot[side]
        if old is not None and old.alive:
            self.world.despawn(old)
        w = self.world
        x = w.width * (0.25 if side == 0 else 0.75)
        a = w.spawn_actor(self.defs[key], side=side, x=x, y=w.height * 0.5)
        self.slot[side] = a
        self.renderer.refresh_palette()
        return a

    def cycle(self, side):
        cur = self.slot[side]
        curkey = cur.archetype.key if cur is not None else None
        i = self.roster.index(curkey) + 1 if curkey in self.roster else 0
        if i >= len(self.roster):
            if side == 1:
                self.slot[1] = None
                for a in list(self.world.sides[1].actors):
                    self.world.despawn(a)
                return
            i = 0
        self.field(side, self.roster[i])

    def possess(self, side):
        """Attach/detach the player brain.  HYBRID: the player brain claims
        MOVE, the existing utility brain keeps ABILITY.  Execution is
        byte-identical either way — that is the AI/player parity guarantee."""
        a = self.slot[side]
        if a is None or not a.alive:
            return
        if self.possessed is a:
            a.brains = [b for b in a.brains if not isinstance(b, PlayerBrain)]
            a.remove_tag("player.controlled")
            self.possessed = None
            return
        if self.possessed is not None:
            self.possessed.brains = [b for b in self.possessed.brains
                                     if not isinstance(b, PlayerBrain)]
            self.possessed.remove_tag("player.controlled")
        a.brains = [PlayerBrain(self.pad, mode="hybrid")] + list(a.brains)
        a.add_tag("player.controlled")
        self.possessed = a

    # ------------------------------------------------------------------
    # the frame — fixed timestep accumulator
    # ------------------------------------------------------------------
    def _frame(self):
        now = time.perf_counter()
        dt = now - self._last
        self._last = now
        if dt > 0.25:                  # tab-out / debugger pause: don't spiral
            dt = 0.25
        self._accum += dt * 1000.0

        if not self.paused:
            steps = 0
            while self._accum >= TICK_MS and steps < MAX_CATCHUP:
                self._sim_step()
                self._accum -= TICK_MS
                steps += 1
            if steps == MAX_CATCHUP:
                self._accum = 0.0      # drop the backlog rather than lag

        self._alpha = min(1.0, self._accum / TICK_MS)
        self.update()

    def _sim_step(self):
        self._keys.poll(self.pad, self)
        pos = QCursor.pos()
        self.world.cursor = (float(pos.x()), float(pos.y()))
        self.renderer.remember_positions()
        self.world.step()
        # cue intake and ageing belong to the SIM step, never to paint
        self.renderer.consume_cues()
        self.renderer.age_cues()

    def paintEvent(self, _ev):
        p = QPainter(self)
        try:
            self.renderer.paint(p, self._alpha)
        finally:
            p.end()


class KeyPoller:
    """Win32 key polling — the overlay is click-through, so it never receives
    Qt key events.  Off Windows this degrades to a no-op and the sim runs
    autonomously, which is exactly what the headless harness needs."""

    VK = {
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44,
        "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
        "q": 0x51, "e": 0x45, "p": 0x50, "esc": 0x1B,
        "ctrl": 0x11, "alt": 0x12,
    }

    def __init__(self, owner):
        self.enabled = sys.platform.startswith("win")
        self._down = {}
        self._get = None
        if self.enabled:
            try:
                import ctypes
                self._get = ctypes.windll.user32.GetAsyncKeyState
            except Exception:
                self.enabled = False

    def _held(self, name):
        if not self.enabled:
            return False
        return bool(self._get(self.VK[name]) & 0x8000)

    def _pressed(self, name):
        """Edge-triggered."""
        now = self._held(name)
        was = self._down.get(name, False)
        self._down[name] = now
        return now and not was

    def poll(self, pad, owner):
        if not self.enabled:
            return
        pad.set_move(
            up=self._held("up") or self._held("w"),
            down=self._held("down") or self._held("s"),
            left=self._held("left") or self._held("a"),
            right=self._held("right") or self._held("d"))

        if self._pressed("1"):
            owner.cycle(0)
        if self._pressed("2"):
            owner.cycle(1)
        if self._pressed("3"):
            owner.possess(0)
        if self._pressed("4"):
            owner.possess(1)
        if self._pressed("p"):
            owner.paused = not owner.paused
        if self._held("ctrl") and self._held("alt") and self._held("esc"):
            QApplication.quit()


def run(characters_dir, p1="runner", p2="swordsman", seed=None, strict=False):
    app = QApplication(sys.argv)
    ov = Overlay(characters_dir, seed=seed, p1=p1, p2=p2, strict=strict)
    ov.show()
    return app.exec_()
