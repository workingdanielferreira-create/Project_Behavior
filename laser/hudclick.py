"""
Hover-to-click for the HUD action buttons (Daniel 2026-11-12).  Solo and
Battle alike.

The overlay is click-through (Qt.WindowTransparentForInput): the desktop
under it keeps working.  Each painted HUD button (laser/hpbars.py, Ready
Gate icons) is listed in world.hud_buttons as (QRectF in overlay pixels,
key).  Once per tick (Overlay._tick, right after the cursor is read):

  * cursor over a button -> the window stops being click-through
    (platform_win.set_click_through(hwnd, False)), so the click lands on
    the overlay instead of the app below; anywhere else -> click-through
    again.  The window never takes keyboard focus (WS_EX_NOACTIVATE).
  * a left-button press that STARTS over a button fires it
    (actionbar.fire).  Ready-only: a cooling icon shakes instead.

Nothing is clickable while the start menu or the results window is open.
world.hud_hover = the key under the cursor (painted highlighted);
world.hud_fx[key] = (perf_counter time, "ok" | "deny") press feedback.
"""

import time

from PyQt5.QtGui import QCursor

from . import actionbar
from . import platform_win as win

PAD = 3                      # px of slack round each button


class HudClick:
    __slots__ = ("hwnd", "clickable", "was_down", "ready")

    def __init__(self):
        self.hwnd = None
        self.clickable = False
        self.was_down = False
        self.ready = False

    def attach(self, widget):
        try:
            self.hwnd = int(widget.winId())
        except Exception:
            self.hwnd = None
        self.ready = bool(self.hwnd) and win.set_no_activate(self.hwnd)

    def _set(self, clickable):
        if clickable == self.clickable:
            return
        self.clickable = clickable
        if self.ready:
            win.set_click_through(self.hwnd, not clickable)

    def step(self, widget, world):
        paused = bool(world.prebattle.open or world.stats_open)
        key = None
        if not paused:
            pt = widget.mapFromGlobal(QCursor.pos())
            for rect, k in getattr(world, "hud_buttons", None) or ():
                if rect.adjusted(-PAD, -PAD, PAD, PAD).contains(pt.x(), pt.y()):
                    key = k
                    break
        world.hud_hover = key
        self._set(key is not None)
        down = win.key_down(win.VK_LBUTTON)
        if down and not self.was_down and key is not None:
            ok = actionbar.fire(world, key)
            world.hud_fx[key] = (time.perf_counter(), "ok" if ok else "deny")
        self.was_down = down
