"""
Pre-battle menu — a light text + line-art overlay toggled with Ctrl+Shift+.
(Ctrl+'>').

While it is open the whole game is paused (Overlay._tick skips the pipeline,
hit-stop and paint-aged FX), so every cooldown, timer, bullet and HP value
picks up exactly where it left off when the menu closes.  The fighters are
painted standing in their idle pose for the duration.

Keys 1 / 2 / 3 / 4 keep their normal job (cycle that slot's character, see
systems.InputSystem) and also reveal that slot's corner panel:

    1 = top-left     (P1 slot 1)        2 = top-right    (P2 slot 1)
    4 = bottom-left  (P2 slot 2)        3 = bottom-right (P1 slot 2)

Each panel shows the slot's character name and one dot per registered
character, the slot's current character lit yellow.  The menu is
world-level, so Solo and Battle behave identically.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont

from . import modes, combat


# slot key -> (side index, figure index on that side, corner)
SLOTS = {
    1: (0, 0, "tl"),
    2: (1, 0, "tr"),
    3: (0, 1, "br"),
    4: (1, 1, "bl"),
}

MARGIN_X = 40
MARGIN_TOP = 40
MARGIN_BOTTOM = 70          # clear of the Windows taskbar
BRACKET_LEN = 60
DOT_R = 11
DOT_GAP = 34                # centre-to-centre
DOT_COLS = 6

COL_LINE = QColor(255, 255, 255, 150)
COL_DIM = QColor(255, 255, 255, 110)
COL_EMPTY = QColor(170, 170, 170, 200)
COL_DOT = QColor(0, 72, 92, 235)
COL_DOT_EDGE = QColor(0, 40, 55, 255)
COL_DOT_ON = QColor(255, 232, 0, 255)
COL_DOT_ON_EDGE = QColor(150, 130, 0, 255)


class PreBattleMenu:
    """Open/closed flag, revealed corners and the menu's own animation clock
    (the game's global_tick is frozen while the menu is up)."""

    def __init__(self):
        self.open = False
        self.shown = set()
        self.tick = 0
        self._name_font = QFont("Consolas", 20, QFont.Bold)
        self._tag_font = QFont("Consolas", 11, QFont.Bold)
        self._title_font = QFont("Consolas", 14, QFont.Bold)

    def toggle(self):
        self.open = not self.open
        self.shown.clear()
        self.tick = 0

    def reveal(self, slot):
        if self.open:
            self.shown.add(slot)

    # --- painting -----------------------------------------------------------
    def paint(self, p, world, pen):
        for fig in world.all_figures():
            self._draw_idle(p, fig, world)
        self._draw_title(p, world)
        order = modes.ordered_modes()
        for slot in sorted(self.shown):
            self._draw_corner(p, world, slot, order, pen)

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
        text = "PRE-BATTLE"
        tw = fm.horizontalAdvance(text)
        cx = world.screen_w // 2
        y = MARGIN_TOP + fm.ascent()
        p.setPen(COL_DIM)
        p.drawText(cx - tw // 2, y, text)
        mid = y - fm.ascent() // 2 + 2
        p.drawLine(cx - tw // 2 - 90, mid, cx - tw // 2 - 14, mid)
        p.drawLine(cx + tw // 2 + 14, mid, cx + tw // 2 + 90, mid)

    def _draw_corner(self, p, world, slot, order, pen):
        side_i, fig_i, corner = SLOTS[slot]
        side = world.sides[side_i]
        fig = side.figures[fig_i] if len(side.figures) > fig_i else None
        right = corner in ("tr", "br")
        bottom = corner in ("bl", "br")
        sw, sh = world.screen_w, world.screen_h

        # Line-art bracket hugging the screen corner.
        pen.setWidthF(2.0)
        pen.setColor(COL_LINE)
        p.setPen(pen)
        bx = sw - MARGIN_X // 2 if right else MARGIN_X // 2
        by = sh - MARGIN_BOTTOM // 2 if bottom else MARGIN_TOP // 2
        hx = -BRACKET_LEN if right else BRACKET_LEN
        vy = -BRACKET_LEN if bottom else BRACKET_LEN
        p.drawLine(bx, by, bx + hx, by)
        p.drawLine(bx, by, bx, by + vy)

        # Text block: tag line, name, rule, dot grid (mirrored for the
        # bottom corners so the name always sits nearest the edge).
        n = len(order)
        cols = min(DOT_COLS, max(1, n))
        rows = (n + DOT_COLS - 1) // DOT_COLS
        grid_w = (cols - 1) * DOT_GAP + 2 * DOT_R
        grid_h = (max(1, rows) - 1) * DOT_GAP + 2 * DOT_R

        if fig is not None:
            key = fig.mode.key
            ch = getattr(fig.mode, "character", None) or {}
            name = str(ch.get("display_name") or key).replace("_", " ").upper()
            # The fighter's own palette colour, lifted toward white so even
            # the deep blues / greens read on a dark desktop.
            r, g, b = fig.lut[128]
            name_col = QColor(r + (255 - r) * 2 // 5, g + (255 - g) * 2 // 5,
                              b + (255 - b) * 2 // 5, 255)
            cur = order.index(key) if key in order else -1
        else:
            name = "- EMPTY -"
            name_col = COL_EMPTY
            cur = -1
        tag = "P%d  SLOT %d" % (side_i + 1, fig_i + 1)

        p.setFont(self._tag_font)
        tfm = p.fontMetrics()
        tag_w = tfm.horizontalAdvance(tag)
        tag_h = tfm.height()
        p.setFont(self._name_font)
        nfm = p.fontMetrics()
        name_w = nfm.horizontalAdvance(name)
        name_h = nfm.height()
        block_w = max(grid_w, name_w, tag_w)
        x0 = sw - MARGIN_X - block_w if right else MARGIN_X

        def ax(w):
            """Left x of an item of width w, aligned to the panel's edge."""
            return x0 + block_w - w if right else x0

        gap = 10
        heights = [tag_h, name_h, gap, grid_h]
        total = sum(heights) + gap
        y = sh - MARGIN_BOTTOM - total if bottom else MARGIN_TOP + 26

        # Top-to-bottom layout for the top corners; the bottom corners stack
        # the dots first and the name last.
        parts = ["tag", "name", "rule", "grid"]
        if bottom:
            parts = ["grid", "rule", "tag", "name"]
        for part in parts:
            if part == "tag":
                p.setFont(self._tag_font)
                p.setPen(COL_DIM)
                p.drawText(ax(tag_w), y + tfm.ascent(), tag)
                y += tag_h
            elif part == "name":
                p.setFont(self._name_font)
                p.setPen(QColor(0, 0, 0, 160))
                p.drawText(ax(name_w) + 1, y + nfm.ascent() + 1, name)
                p.setPen(name_col)
                p.drawText(ax(name_w), y + nfm.ascent(), name)
                y += name_h
            elif part == "rule":
                y += gap // 2
                pen.setWidthF(1.0)
                pen.setColor(COL_LINE)
                p.setPen(pen)
                p.drawLine(x0, y, x0 + block_w, y)
                y += gap // 2 + (gap if not bottom else 0)
            elif part == "grid":
                gx = ax(grid_w)
                for i in range(n):
                    cx = gx + DOT_R + (i % DOT_COLS) * DOT_GAP
                    cy = y + DOT_R + (i // DOT_COLS) * DOT_GAP
                    on = i == cur
                    pen.setWidthF(2.0)
                    pen.setColor(COL_DOT_ON_EDGE if on else COL_DOT_EDGE)
                    p.setPen(pen)
                    p.setBrush(COL_DOT_ON if on else COL_DOT)
                    p.drawEllipse(cx - DOT_R, cy - DOT_R, 2 * DOT_R, 2 * DOT_R)
                p.setBrush(Qt.NoBrush)
                y += grid_h + (gap if bottom else 0)
