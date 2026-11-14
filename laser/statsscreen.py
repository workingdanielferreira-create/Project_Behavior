"""
Results window — damage dealt by action (data: laser/battlestats.py).

Opens by itself when a fight is over (Battle: a KO leaves one team standing,
after the KO shot; Solo: the final KO, instead of quitting).  Like the start
menu it is an ordinary window you can click — the overlay is click-through.
Solo and Battle use the same window (Solo's damage = attacks that reached
the cursor).

  * Title      TEAM n WINS / DRAW / RUN OVER
  * Chart      one 100% stacked bar per fighter: each damaging action's share
               of that fighter's damage dealt, total beside the name, a
               legend line (action, %, damage) under the bar, hover = tooltip.
               An action keeps the same colour on every bar.
  * Buttons    Rematch (same roster, fresh) / Character select / Keep watching
               (not offered once a Solo run is over) / Quit

on_done(choice): "resume", "rematch", "select" or "quit" (exactly once).
"""

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QFont
from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
                             QScrollArea, QApplication, QToolTip)

from . import battlestats as B

TEAM_RGB = [(124, 196, 255), (255, 143, 177)]

# Categorical slots (validated dark-surface steps), assigned to actions in a
# fixed order (never by rank); a 9th+ action folds into OTHER.
SERIES = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"]
OTHER = "#6b7480"
SURFACE = "#12161c"
BAR_H = 26
GAP = 2              # surface gap between segments
RADIUS = 4

STYLE = """
QWidget#Stats { background: #12161c; }
QWidget { color: #e6edf3; font-family: Consolas, 'Courier New', monospace; font-size: 12px; }
QLabel#Title { font-size: 26px; font-weight: bold; letter-spacing: 3px; }
QLabel#Sub { color: #8b98a5; }
QLabel#Name { font-size: 14px; font-weight: bold; }
QLabel#Total { font-size: 14px; font-weight: bold; }
QPushButton { background: #252d38; border: 1px solid #3a4553; border-radius: 5px; padding: 6px 14px; }
QPushButton:hover { border: 1px solid #ffe600; }
QPushButton#Primary { background: #0b6e4f; border: 1px solid #12a378; font-weight: bold; padding: 7px 20px; }
QPushButton#Danger { background: #4a1d1d; border: 1px solid #8a3434; }
QScrollArea { border: none; background: #12161c; }
QWidget#Pane { background: #12161c; }
"""

n = B.fmt_num


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb[:3])


def _order_key(name):
    """Fixed action order: attack, special, ultimate (each by number), then
    everything else alphabetically — so colours never depend on rank."""
    s = str(name)
    for i, base in enumerate(("attack_normal", "attack_special", "ultimate")):
        if s == base:
            return (i, 0, "")
        if s.startswith(base + "_") and s[len(base) + 1:].isdigit():
            return (i, int(s[len(base) + 1:]), "")
    return (3, 0, s.lower())


def colour_map(fighters):
    names = sorted({k for s in fighters for k, v in s.by_action.items() if v > 0}, key=_order_key)
    return {k: (SERIES[i] if i < len(SERIES) else OTHER) for i, k in enumerate(names)}


def segments(st, colours):
    """[(label, damage, colour)] in fixed action order; actions past the 8th
    colour slot merged into one OTHER segment."""
    out, other = [], 0.0
    for k in sorted((k for k, v in st.by_action.items() if v > 0), key=_order_key):
        c = colours[k]
        if c == OTHER:
            other += st.by_action[k]
        else:
            out.append((B.action_label(k), st.by_action[k], c))
    if other > 0:
        out.append(("Other", other, OTHER))
    return out


# ============================================================ chart
class StackBar(QWidget):
    """One fighter's 100% stacked bar; hover a segment for its numbers."""

    def __init__(self, segs, total):
        super().__init__()
        self.segs, self.total = segs, total
        self.setFixedHeight(BAR_H)
        self.setMinimumWidth(200)
        self.setMouseTracking(True)
        self._rects = []

    def _layout(self):
        W = float(self.width())
        live = [s for s in self.segs if s[1] > 0]
        room = W - GAP * max(0, len(live) - 1)
        x, out = 0.0, []
        for seg in live:
            w = room * seg[1] / self.total
            out.append((QRectF(x, 0, w, BAR_H), seg))
            x += w + GAP
        self._rects = out
        return out

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        full = QRectF(0, 0, self.width(), BAR_H)
        clip = QPainterPath()
        clip.addRoundedRect(full, RADIUS, RADIUS)
        if self.total <= 0:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(27, 33, 41))
            p.drawPath(clip)
            p.setPen(QColor(139, 152, 165))
            p.drawText(full, Qt.AlignCenter, "No damage dealt")
            p.end()
            return
        p.setClipPath(clip)
        p.setPen(Qt.NoPen)
        f = QFont("Consolas", 9, QFont.Bold)
        p.setFont(f)
        fm = p.fontMetrics()
        for r, (label, dmg, col) in self._layout():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col))
            p.drawRect(r)
            pct = "%d%%" % int(round(100.0 * dmg / self.total))
            if fm.horizontalAdvance(pct) + 8 <= r.width():
                p.setPen(QColor(SURFACE))
                p.drawText(r, Qt.AlignCenter, pct)
        p.end()

    def mouseMoveEvent(self, e):
        for r, (label, dmg, _c) in self._rects:
            if r.left() - GAP <= e.x() <= r.right() + GAP:
                QToolTip.showText(e.globalPos(), "%s\n%s damage  ·  %.1f%%" % (
                    label, n(dmg), 100.0 * dmg / self.total), self)
                return
        QToolTip.hideText()


def _fighter_row(st, colours):
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 6, 0, 10)
    v.setSpacing(4)
    head = QHBoxLayout()
    head.setSpacing(12)
    nm = QLabel("<span style='color:%s'>■</span>&nbsp;%s%s" % (
        _hex(st.rgb), ("%s&nbsp;&nbsp;" % st.slot) if st.slot else "", st.name))
    nm.setObjectName("Name")
    nm.setTextFormat(Qt.RichText)
    head.addWidget(nm)
    team = QLabel("Team %d" % (st.team + 1))
    team.setObjectName("Sub")
    team.setStyleSheet("color: %s;" % _hex(TEAM_RGB[st.team % 2]))
    head.addWidget(team)
    head.addStretch(1)
    tot = QLabel("%s damage" % n(st.dealt))
    tot.setObjectName("Total")
    head.addWidget(tot)
    v.addLayout(head)
    segs = segments(st, colours)
    v.addWidget(StackBar(segs, st.dealt))
    if segs:
        leg = QLabel("&nbsp;&nbsp;&nbsp;".join(
            "<span style='color:%s'>■</span>&nbsp;%s&nbsp;<b>%d%%</b>&nbsp;<span style='color:#8b98a5'>(%s)</span>"
            % (c, label, int(round(100.0 * d / st.dealt)), n(d)) for label, d, c in segs))
        leg.setTextFormat(Qt.RichText)
        leg.setWordWrap(True)
        v.addWidget(leg)
    return box


# ============================================================ window
class StatsWindow(QWidget):
    def __init__(self, world, kind, on_done):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setObjectName("Stats")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle("Project Behavior - Battle Results")
        self.setStyleSheet(STYLE)
        self.world, self.kind, self.on_done = world, kind, on_done
        self._done = False
        st = world.stats
        st.sync(world)
        fs = st.ordered()
        self.solo_end = bool(st.solo_end and kind == "end")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)

        if st.solo_end:
            title, tcol = "RUN OVER", "#ff8a80"
        elif st.winner is not None and st.winner >= 0:
            title, tcol = "TEAM %d WINS" % (st.winner + 1), _hex(TEAM_RGB[st.winner % 2])
        elif st.winner == -1:
            title, tcol = "DRAW", "#ffe600"
        else:
            title, tcol = "BATTLE RESULTS", "#ffffff"
        t = QLabel(title)
        t.setObjectName("Title")
        t.setStyleSheet("color: %s;" % tcol)
        root.addWidget(t)
        cap = QLabel("Damage dealt by action — share of each fighter's total"
                     + ("  (Solo: attacks that reached the cursor)" if not st.battle_seen else ""))
        cap.setObjectName("Sub")
        root.addWidget(cap)

        pane = QWidget()
        pane.setObjectName("Pane")
        pane.setAttribute(Qt.WA_StyledBackground, True)
        col = QVBoxLayout(pane)
        col.setContentsMargins(0, 4, 8, 4)
        colours = colour_map(fs)
        for s in fs:
            col.addWidget(_fighter_row(s, colours))
        if not fs:
            empty = QLabel("No fighters.")
            empty.setObjectName("Sub")
            col.addWidget(empty)
        col.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(pane)
        sc.viewport().setStyleSheet("background: %s;" % SURFACE)
        root.addWidget(sc, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        quit_b = QPushButton("Quit")
        quit_b.setObjectName("Danger")
        quit_b.clicked.connect(lambda: self.finish("quit"))
        btns.addWidget(quit_b)
        sel = QPushButton("Character select")
        sel.clicked.connect(lambda: self.finish("select"))
        btns.addWidget(sel)
        if not self.solo_end:
            keep = QPushButton("Keep watching")
            keep.clicked.connect(lambda: self.finish("resume"))
            btns.addWidget(keep)
        rem = QPushButton("Rematch")
        rem.setObjectName("Primary")
        rem.clicked.connect(lambda: self.finish("rematch"))
        rem.setDefault(True)
        btns.addWidget(rem)
        root.addLayout(btns)

        scr = QApplication.primaryScreen().availableGeometry()
        h = min(scr.height() - 60, 170 + 96 * max(1, len(fs)))
        self.resize(min(1000, scr.width() - 60), h)
        self.move(scr.x() + (scr.width() - self.width()) // 2,
                  scr.y() + max(0, (scr.height() - self.height()) // 2))

    # ---- close ------------------------------------------------------------
    def finish(self, choice):
        if self._done:
            return
        self._done = True
        self.close()
        self.on_done(choice)

    def close_silently(self):
        self._done = True
        self.close()

    def closeEvent(self, e):
        if not self._done:
            self._done = True
            # Closing the window = Keep watching; once a Solo run is over
            # there is nothing to watch, so it quits like the game used to.
            self.on_done("quit" if self.solo_end else "resume")
        super().closeEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            if not self.solo_end:        # a stray Esc never quits the game
                self.finish("resume")
            return
        super().keyPressEvent(e)
