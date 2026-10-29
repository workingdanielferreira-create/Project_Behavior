"""
Start-menu pause layer.

While the start menu window (laser/startmenu.py — opened on launch with
--prebattle, or with Ctrl+Shift+. / Ctrl+'>') is up, the whole game is
paused (Overlay._tick skips the pipeline, hit-stop and paint-aged FX), so
every cooldown, timer, bullet and HP value picks up exactly where it left
off when the menu closes.  This draws the paused screen behind the window:
the frozen FX layer, the fighters standing in their idle pose, a PAUSED
title and the team HP bars.  The menu is world-level, so Solo and Battle
behave identically.
"""

from PyQt5.QtGui import QColor, QFont

from . import combat, hpbars

MARGIN_TOP = 40
COL_DIM = QColor(255, 255, 255, 110)


class PreBattleMenu:
    """Open/closed flag and the pause layer's own animation clock (the
    game's global_tick is frozen while the menu is up)."""

    def __init__(self):
        self.open = False
        self.tick = 0
        # Frozen FX layer: everything on screen except the fighters' bodies
        # (bullets, clones, trails, rings, sparks, clash FX ...), captured
        # once when the menu opens and redrawn unchanged every paused frame
        # (see Overlay._paint).  frozen_sig = roster_sig at capture time.
        self.frozen = None
        self.frozen_front = None   # "absolute front" FX, drawn over the fighters
        self.frozen_sig = None
        self._title_font = QFont("Consolas", 14, QFont.Bold)

    def toggle(self):
        self.open = not self.open
        self.tick = 0
        self.frozen = None

    @staticmethod
    def roster_sig(world):
        """Changes whenever a fighter is fielded, retired, re-skinned or
        tagged in / out, so the frozen FX layer is re-captured to match the
        roster on screen."""
        return tuple((id(f), f.mode.key) for f in world.all_figures())

    # --- painting -----------------------------------------------------------
    def paint_fighters(self, p, world):
        for fig in world.all_figures():
            self._draw_idle(p, fig, world)

    def paint_menu(self, p, world, pen):
        self._draw_title(p, world)
        hpbars.draw(p, world)

    def _draw_idle(self, p, fig, world):
        """The figure's idle frame at its frozen position, animated by the
        menu clock.  A fighter fielded while paused has not been placed yet
        (motion places it on its first tick), so it stands at the cursor."""
        b = fig.render.bundle
        left = fig.transform.facing_left
        if b.idle:
            fs = b.idle_flipped if left else b.idle
            step = max(1, int(fig.render.idle_anim_speed or 1))
            frame = fs[(fig.render.idle_idx + self.tick // step) % len(fs)]
        elif b.run:
            fs = b.run_flipped if left else b.run
            frame = fs[0]
        else:
            return
        if frame is None:
            return
        if fig.transform.init:
            x, y = fig.transform.x, fig.transform.y
        else:
            x, y = world.cursor
        s = combat.position_scale(x, y, world.screen_w, world.screen_h)
        p.save()
        p.translate(x, y)
        if s != 1.0:
            p.scale(s, s)
        p.drawPixmap(-frame.width() // 2, -frame.height() // 2, frame)
        p.restore()

    def _draw_title(self, p, world):
        p.setFont(self._title_font)
        fm = p.fontMetrics()
        text = "PAUSED  -  START MENU"
        tw = fm.horizontalAdvance(text)
        cx = world.screen_w // 2
        y = MARGIN_TOP + fm.ascent()
        p.setPen(COL_DIM)
        p.drawText(cx - tw // 2, y, text)
        mid = y - fm.ascent() // 2 + 2
        p.drawLine(cx - tw // 2 - 90, mid, cx - tw // 2 - 14, mid)
        p.drawLine(cx + tw // 2 + 14, mid, cx + tw // 2 + 90, mid)
