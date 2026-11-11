"""
Results window — the post-battle stats screen (data: laser/battlestats.py).

Opens by itself when a fight is over (Battle: a KO leaves one team standing,
after the KO shot; Solo: the final KO, instead of quitting) and mid-fight
with Ctrl+Shift+, ("live", the game pauses).  Like the start menu it is an
ordinary window you can click — the overlay is click-through.  Solo and
Battle use the same window (Solo's "damage dealt" = attacks that reached the
cursor).

  * Header     winner banner (team colour), fight time, total damage
  * Awards     MVP, Heavy Hitter, Combo King, Burst, Speed Demon, Marathon,
               Finisher, Iron Wall, Phantom, Untouchable, Clutch, First Blood
  * Tabs
      Fighters      a card per fighter, Team 1 | VS | Team 2: dealt / taken /
                    KOs, offence, defence, movement, time, damage by action
      Compare       every headline stat as side-by-side bars
      Actions       sortable table: uses / hits / damage / share / biggest /
                    average per action, per fighter
      Head-to-head  who dealt how much to whom
      Timeline      HP % and damage dealt over the fight, KO markers
  * Buttons    Rematch (same roster, fresh) / Character select / Keep watching
               (Resume when opened mid-fight; not offered once a Solo run is
               over) / Quit, plus Copy (the sheet as text, to the clipboard)

on_done(choice): "resume", "rematch", "select" or "quit" (exactly once).
"""

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QColor, QPainter, QPen, QFont, QPainterPath, QBrush
from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
                             QGridLayout, QFrame, QScrollArea, QApplication, QSizePolicy,
                             QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView)

from . import battlestats as B

TEAM_RGB = [(124, 196, 255), (255, 143, 177)]
PORTRAIT = 64

STYLE = """
QWidget#Stats { background: #12161c; }
QWidget { color: #e6edf3; font-family: Consolas, 'Courier New', monospace; font-size: 12px; }
QLabel#Title { font-size: 26px; font-weight: bold; letter-spacing: 3px; }
QLabel#Sub { color: #8b98a5; }
QLabel#Big { font-size: 22px; font-weight: bold; }
QLabel#BigCap { color: #8b98a5; font-size: 10px; letter-spacing: 1px; }
QLabel#Sec { color: #ffe600; font-size: 11px; font-weight: bold; letter-spacing: 2px; padding-top: 6px; }
QLabel#Key { color: #8b98a5; }
QLabel#Val { color: #e6edf3; font-weight: bold; }
QLabel#Chip { border-radius: 8px; padding: 1px 8px; font-size: 10px; font-weight: bold; }
QLabel#Vs { color: #59636e; font-size: 30px; font-weight: bold; }
QFrame#Card { background: #1b2129; border: 2px solid #2a323d; border-radius: 10px; }
QFrame#Award { background: #1b2129; border: 1px solid #2a323d; border-radius: 8px; }
QPushButton { background: #252d38; border: 1px solid #3a4553; border-radius: 5px; padding: 6px 14px; }
QPushButton:hover { border: 1px solid #ffe600; }
QPushButton#Primary { background: #0b6e4f; border: 1px solid #12a378; font-weight: bold; padding: 7px 20px; }
QPushButton#Danger { background: #4a1d1d; border: 1px solid #8a3434; }
QScrollArea { border: none; background: #12161c; }
QWidget#Pane { background: #12161c; }
QTabWidget::pane { border: 1px solid #2a323d; border-radius: 6px; top: -1px; }
QTabBar::tab { background: #1b2129; border: 1px solid #2a323d; padding: 6px 16px; margin-right: 2px;
               border-top-left-radius: 6px; border-top-right-radius: 6px; color: #8b98a5; }
QTabBar::tab:selected { background: #243040; color: #ffffff; border-bottom-color: #243040; }
QTableWidget { background: #161b22; gridline-color: #2a323d; border: none;
               alternate-background-color: #1b2129; selection-background-color: #3a4553; }
QHeaderView::section { background: #252d38; color: #e6edf3; border: none; border-right: 1px solid #12161c;
                       padding: 5px; font-weight: bold; }
QTableCornerButton::section { background: #252d38; border: none; }
"""

n = B.fmt_num


def _hex(rgb, k=0.0):
    r, g, b = (int(c + (255 - c) * k) for c in rgb[:3])
    return "#%02x%02x%02x" % (r, g, b)


def _pct(a, b):
    return (100.0 * a / b) if b else 0.0


def _secs(s):
    return "%d:%04.1f" % (int(s // 60), s % 60)


def _status(st, stats, world):
    if st.deaths and st.hp <= 0:
        return "KO", (255, 90, 80)
    if stats.over and stats.winner is not None and stats.winner >= 0 and st.team == stats.winner:
        return "WINNER", (255, 214, 0)
    if st.fig is not None:
        for p in getattr(world, "tag_pairs", None) or []:
            if p.off.fig is st.fig:
                return "BENCHED", (139, 152, 165)
    if not any(st.fig is f for sd in world.sides for f in sd.figures):
        return "OFF FIELD", (139, 152, 165)
    return "STANDING", (124, 220, 140)


# ============================================================ small widgets
class Bar(QWidget):
    """A thin horizontal bar (fraction in fighter colour) with an optional
    trailing marker (e.g. lowest HP)."""

    def __init__(self, frac, rgb, mark=None, h=8):
        super().__init__()
        self.frac, self.rgb, self.mark = max(0.0, min(1.0, frac)), rgb, mark
        self.setFixedHeight(h)
        self.setMinimumWidth(40)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(10, 14, 20))
        p.drawRoundedRect(r, 3, 3)
        if self.frac > 0:
            p.setBrush(QColor(*self.rgb[:3]))
            p.drawRoundedRect(QRectF(0, 0, self.width() * self.frac, self.height()), 3, 3)
        if self.mark is not None:
            x = self.width() * max(0.0, min(1.0, self.mark))
            p.setPen(QPen(QColor(255, 90, 80), 2))
            p.drawLine(QPointF(x, -1), QPointF(x, self.height() + 1))
        p.end()


def _lbl(text, name=None, color=None, wrap=False):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    if color is not None:
        l.setStyleSheet("color: %s;" % color)
    l.setWordWrap(wrap)
    return l


# ============================================================ fighter card
class Card(QFrame):
    def __init__(self, st, stats, world):
        super().__init__()
        self.setObjectName("Card")
        self.setStyleSheet("QFrame#Card { border: 2px solid %s; }" % _hex(st.rgb))
        self.setFixedWidth(360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(3)

        # Header: portrait, slot / name / team, status chip.
        head = QHBoxLayout()
        pic = QLabel()
        try:
            from .startmenu import char_pixmap
            pic.setPixmap(char_pixmap(world.assets, st.key, PORTRAIT))
        except Exception:
            pass
        pic.setFixedSize(PORTRAIT, PORTRAIT)
        head.addWidget(pic)
        names = QVBoxLayout()
        names.setSpacing(0)
        nm = _lbl(st.name, "Big", _hex(st.rgb, 0.35))
        nm.setStyleSheet(nm.styleSheet() + "font-size: 18px;")
        names.addWidget(nm)
        tag = ("Slot %s  ·  " % st.slot if st.slot else "") + "Team %d" % (st.team + 1)
        names.addWidget(_lbl(tag, "Sub", _hex(TEAM_RGB[st.team % 2])))
        word, col = _status(st, stats, world)
        chip = _lbl(word, "Chip")
        chip.setStyleSheet("background: %s; color: #12161c;" % _hex(col))
        chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        names.addWidget(chip)
        head.addLayout(names, 1)
        lay.addLayout(head)

        # HP at the end (with lowest HP marker).
        hpf = st.hp / st.max_hp if st.max_hp else 0.0
        hprow = QHBoxLayout()
        hprow.addWidget(_lbl("HP", "Key"))
        hprow.addWidget(Bar(hpf, st.rgb, st.low_hp / st.max_hp if st.low_hp < st.hp else None, 10), 1)
        hprow.addWidget(_lbl("%s / %s" % (n(st.hp), n(st.max_hp)), "Val"))
        lay.addLayout(hprow)

        # Big three.
        big = QHBoxLayout()
        for cap, val, c in (("DEALT", n(st.dealt), "#ffb86b"), ("TAKEN", n(st.taken), "#ff8a80"),
                            ("KOs", str(st.kos), "#ffe600")):
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(_lbl(val, "Big", c), 0, Qt.AlignHCenter)
            col.addWidget(_lbl(cap, "BigCap"), 0, Qt.AlignHCenter)
            big.addLayout(col)
        lay.addLayout(big)
        ratio = (st.dealt / st.taken) if st.taken > 0 else None
        lay.addWidget(_lbl("Damage ratio  %s" % ("%.2f : 1" % ratio if ratio is not None
                                                  else ("∞ (untouched)" if st.dealt > 0 else "-")),
                           "Sub"), 0, Qt.AlignHCenter)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(1)
        row = [0]

        def sec(title):
            grid.addWidget(_lbl(title, "Sec"), row[0], 0, 1, 2)
            row[0] += 1

        def kv(k, v, tip=None):
            a, b = _lbl(k, "Key"), _lbl(v, "Val")
            b.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if tip:
                a.setToolTip(tip)
                b.setToolTip(tip)
            grid.addWidget(a, row[0], 0)
            grid.addWidget(b, row[0], 1)
            row[0] += 1

        solo = not stats.battle_seen
        sec("OFFENCE" + ("  (hits on the cursor)" if solo else ""))
        kv("Hits landed", n(st.hits))
        kv("Biggest hit", ("%s  (%s)" % (n(st.max_hit), B.action_label(st.max_hit_action)))
           if st.max_hit > 0 else "-")
        kv("Longest combo", ("%d hits / %s dmg" % (st.best_combo, n(st.best_combo_dmg)))
           if st.best_combo else "-", "Hits on one target no more than 1.2 s apart, broken when you get hit")
        kv("Best 1-second burst", n(st.best_burst), "Most damage landed inside any 1 second")
        kv("Damage per second", "%.1f" % st.dps, "Damage dealt / time on the field")
        kv("Avg damage per hit", "%.1f" % (st.dealt / st.hits) if st.hits else "-")
        if st.first_hit_tick is not None:
            kv("First hit at", B.fmt_clock(st.first_hit_tick - stats.start_tick)
               + ("  \U0001FA78" if st.first_blood else ""))
        sec("DEFENCE")
        kv("Hits taken", n(st.hits_taken))
        kv("Biggest hit taken", ("%s  (%s)" % (n(st.max_taken), st.max_taken_from)) if st.max_taken else "-")
        kv("Blocked / negated", str(st.blocked), "Parries, defend, special stance, Phase Shift, Riposte")
        if st.absorbed > 0:
            kv("Shield absorbed", n(st.absorbed))
        if st.healed > 0:
            kv("Healed", n(st.healed))
        kv("Lowest HP", "%s  (%d%%)" % (n(st.low_hp), int(round(_pct(st.low_hp, st.max_hp)))))
        kv("Dodges", str(st.dodges))
        sec("MOVEMENT")
        sw = float(getattr(world, "screen_w", 1920) or 1920)
        kv("Distance travelled", "%s px" % n(st.distance))
        kv("Screen widths", "%.1f" % (st.distance / sw), "Distance travelled / the screen's width")
        kv("Top speed", "%s px/s" % n(st.top_speed), "Own movement, averaged over 4 ticks")
        kv("Avg speed moving", "%s px/s" % n(st.avg_speed))
        kv("Time moving", "%d%%" % int(round(_pct(st.moving_ticks, st.field_ticks))))
        kv("Knocked back", "%s px" % n(st.kb_distance))
        if st.top_kb_speed > 0:
            kv("Fastest launch", "%s px/s" % n(st.top_kb_speed), "Top speed while knocked back")
        kv("Warps / vanishes", "%d / %d" % (st.teleports, st.vanishes),
           "Warps = jumps over 60 px in one tick (blinks, teleports); vanishes = blinked out")
        sec("TIME")
        kv("On the field", _secs(st.field_s))
        if st.ko_tick is not None:
            kv("Knocked out at", B.fmt_clock(st.ko_tick - stats.start_tick))
        lay.addLayout(grid)

        # Damage by action (top 6) with share bars.
        acts = sorted(((k, a) for k, a in st.by_action.items() if a.dmg > 0),
                      key=lambda e: -e[1].dmg)
        if acts:
            lay.addWidget(_lbl("DAMAGE BY ACTION", "Sec"))
            for k, a in acts[:6]:
                r = QHBoxLayout()
                nmw = _lbl(B.action_label(k), "Key")
                nmw.setFixedWidth(110)
                r.addWidget(nmw)
                r.addWidget(Bar(a.dmg / st.dealt if st.dealt else 0, st.rgb, None, 8), 1)
                v = _lbl("%s  %d%%" % (n(a.dmg), int(round(_pct(a.dmg, st.dealt)))), "Val")
                v.setFixedWidth(92)
                v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                r.addWidget(v)
                lay.addLayout(r)
        lay.addStretch(1)


# ============================================================ compare tab
class CompareChart(QWidget):
    """Every headline stat as bars, one per fighter, scaled to the leader."""

    METRICS = [
        ("Damage dealt", lambda s: s.dealt, n),
        ("Damage taken", lambda s: s.taken, n),
        ("Hits landed", lambda s: s.hits, n),
        ("Biggest hit", lambda s: s.max_hit, n),
        ("Longest combo (hits)", lambda s: s.best_combo, n),
        ("Best 1-second burst", lambda s: s.best_burst, n),
        ("Damage per second", lambda s: s.dps, lambda v: "%.1f" % v),
        ("KOs", lambda s: s.kos, n),
        ("Blocked / negated", lambda s: s.blocked, n),
        ("Top speed (px/s)", lambda s: s.top_speed, n),
        ("Distance (px)", lambda s: s.distance, n),
        ("Knocked back (px)", lambda s: s.kb_distance, n),
        ("Warps + vanishes", lambda s: s.teleports + s.vanishes, n),
        ("Time on field (s)", lambda s: s.field_s, lambda v: "%.1f" % v),
    ]
    ROW = 22
    GAP = 14

    def __init__(self, fighters):
        super().__init__()
        self.fs = fighters
        h = len(self.METRICS) * (len(self.fs) * self.ROW + self.GAP + 20) + 30
        self.setMinimumHeight(h)
        self.setMinimumWidth(600)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(18, 22, 28))
        W = self.width()
        name_w, val_w = 170, 110
        bar_x, bar_w = name_w + 20, max(80, W - name_w - val_w - 50)
        y = 14
        f = QFont("Consolas", 10)
        fb = QFont("Consolas", 10, QFont.Bold)
        for title, key, fmt in self.METRICS:
            vals = [float(key(s)) for s in self.fs]
            top = max(vals) if vals else 0.0
            p.setFont(fb)
            p.setPen(QColor(255, 230, 0))
            p.drawText(QRectF(10, y, W - 20, 18), Qt.AlignLeft | Qt.AlignVCenter, title.upper())
            y += 20
            for s, v in zip(self.fs, vals):
                p.setFont(f)
                p.setPen(QColor(_hex(s.rgb, 0.35)))
                p.drawText(QRectF(20, y, name_w, self.ROW), Qt.AlignLeft | Qt.AlignVCenter,
                           "%s %s" % (s.slot or "-", s.name))
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(10, 14, 20))
                p.drawRoundedRect(QRectF(bar_x, y + 5, bar_w, self.ROW - 10), 3, 3)
                if top > 0 and v > 0:
                    p.setBrush(QColor(*s.rgb[:3]))
                    p.drawRoundedRect(QRectF(bar_x, y + 5, bar_w * v / top, self.ROW - 10), 3, 3)
                p.setFont(fb if (v == top and top > 0 and len(self.fs) > 1) else f)
                p.setPen(QColor(255, 214, 0) if (v == top and top > 0 and len(self.fs) > 1)
                         else QColor(230, 237, 243))
                p.drawText(QRectF(bar_x + bar_w + 8, y, val_w, self.ROW), Qt.AlignLeft | Qt.AlignVCenter,
                           fmt(v) + ("  ★" if (v == top and top > 0 and len(self.fs) > 1) else ""))
                y += self.ROW
            y += self.GAP
        p.end()


# ============================================================ timeline tab
class Timeline(QWidget):
    """HP % (top) and damage dealt (bottom) over the fight, KO markers."""

    def __init__(self, stats, fighters):
        super().__init__()
        self.stats, self.fs = stats, fighters
        self.setMinimumHeight(520)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(18, 22, 28))
        t0 = self.stats.start_tick
        t1 = max([t0 + 1] + [e[0] for s in self.fs for e in s.timeline]
                 + ([self.stats.end_tick] if self.stats.end_tick else []))
        W, H = self.width(), self.height()
        L, R = 64, 40
        legend_h = 26
        half = (H - legend_h - 30) / 2.0
        boxes = [QRectF(L, legend_h + 10, W - L - R, half - 30),
                 QRectF(L, legend_h + 10 + half, W - L - R, half - 30)]
        top_dmg = max([1.0] + [s.dealt for s in self.fs])
        f = QFont("Consolas", 9)
        p.setFont(f)
        # Legend.
        x = L
        for s in self.fs:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(*s.rgb[:3]))
            p.drawRoundedRect(QRectF(x, 8, 14, 10), 2, 2)
            p.setPen(QColor(_hex(s.rgb, 0.35)))
            label = "%s %s" % (s.slot or "-", s.name)
            p.drawText(QPointF(x + 20, 17), label)
            x += 40 + p.fontMetrics().horizontalAdvance(label)
        for bi, (box, title, vmax, fmt) in enumerate(((boxes[0], "HP %", 1.0, lambda v: "%d%%" % int(v * 100)),
                                                      (boxes[1], "DAMAGE DEALT", top_dmg, n))):
            p.setPen(QPen(QColor(42, 50, 61), 1))
            p.setBrush(QColor(22, 27, 34))
            p.drawRect(box)
            p.setPen(QColor(139, 152, 165))
            for k in range(5):
                gy = box.bottom() - box.height() * k / 4.0
                p.setPen(QPen(QColor(42, 50, 61), 1, Qt.DashLine))
                p.drawLine(QPointF(box.left(), gy), QPointF(box.right(), gy))
                p.setPen(QColor(139, 152, 165))
                p.drawText(QRectF(0, gy - 8, L - 6, 16), Qt.AlignRight | Qt.AlignVCenter, fmt(vmax * k / 4.0))
            p.setPen(QColor(255, 230, 0))
            p.drawText(QPointF(box.left() + 6, box.top() - 4), title)
            # Time axis.
            p.setPen(QColor(139, 152, 165))
            span_s = (t1 - t0) * B.TICK_S
            for k in range(6):
                tx = box.left() + box.width() * k / 5.0
                p.drawText(QRectF(tx - 30, box.bottom() + 2, 60, 14), Qt.AlignCenter,
                           _secs(span_s * k / 5.0))

            def px(t, v):
                return QPointF(box.left() + box.width() * (t - t0) / float(t1 - t0),
                               box.bottom() - box.height() * max(0.0, min(1.0, v / vmax)))
            for s in self.fs:
                pts = s.timeline if bi == 0 else s.dealt_line
                if len(pts) < 2:
                    continue
                path = QPainterPath(px(*pts[0]))
                for t, v in pts[1:]:
                    path.lineTo(px(t, v))
                pen = QPen(QColor(*s.rgb[:3]), 2.2)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
                if s.ko_tick is not None:
                    v = 0.0 if bi == 0 else s.dealt
                    pt = px(s.ko_tick, v)
                    p.setPen(QPen(QColor(255, 90, 80), 2))
                    p.drawLine(QPointF(pt.x() - 5, pt.y() - 5), QPointF(pt.x() + 5, pt.y() + 5))
                    p.drawLine(QPointF(pt.x() - 5, pt.y() + 5), QPointF(pt.x() + 5, pt.y() - 5))
        p.end()


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
        self.stats = st
        fs = st.ordered()
        self.fs = fs
        self.solo_end = bool(st.solo_end and kind == "end")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)

        # ---- header -------------------------------------------------------
        if kind == "live" and not st.over:
            title, tcol = "BATTLE STATS  ·  PAUSED", "#ffffff"
        elif st.solo_end:
            title, tcol = "RUN OVER", "#ff8a80"
        elif st.winner is not None and st.winner >= 0:
            title, tcol = "TEAM %d WINS" % (st.winner + 1), _hex(TEAM_RGB[st.winner % 2])
        elif st.winner == -1:
            title, tcol = "DRAW", "#ffe600"
        else:
            title, tcol = "BATTLE STATS", "#ffffff"
        t = _lbl(title, "Title", tcol)
        total = sum(s.dealt for s in fs)
        mode = "Battle" if st.battle_seen else "Solo"
        sub = _lbl("%s  ·  fight time %s  ·  %d fighter%s  ·  %s total damage%s" % (
            mode, _secs(st.duration_s(world)), len(fs), "" if len(fs) == 1 else "s", n(total),
            "  ·  Solo damage = attacks that reached the cursor" if not st.battle_seen else ""), "Sub")
        root.addWidget(t)
        root.addWidget(sub)

        # ---- awards -------------------------------------------------------
        aw = st.awards()
        if aw:
            ag = QGridLayout()
            ag.setSpacing(6)
            cols = 4
            for i, (icon, name, who, rgb, why) in enumerate(aw):
                fr = QFrame()
                fr.setObjectName("Award")
                hl = QHBoxLayout(fr)
                hl.setContentsMargins(8, 4, 8, 4)
                ic = _lbl(icon)
                ic.setStyleSheet("font-size: 20px; font-family: 'Segoe UI Emoji';")
                hl.addWidget(ic)
                vl = QVBoxLayout()
                vl.setSpacing(0)
                top = _lbl("%s  ·  <span style='color:%s'>%s</span>" % (name.upper(), _hex(rgb, 0.35), who))
                top.setTextFormat(Qt.RichText)
                top.setStyleSheet("font-weight: bold;")
                vl.addWidget(top)
                vl.addWidget(_lbl(why, "Sub"))
                hl.addLayout(vl, 1)
                ag.addWidget(fr, i // cols, i % cols)
            root.addLayout(ag)

        # ---- tabs ---------------------------------------------------------
        tabs = QTabWidget()
        tabs.addTab(self._fighters_tab(), "Fighters")
        tabs.addTab(self._scroll(CompareChart(fs)), "Compare")
        tabs.addTab(self._actions_tab(), "Actions")
        tabs.addTab(self._h2h_tab(), "Head-to-head")
        tabs.addTab(Timeline(st, fs), "Timeline")
        root.addWidget(tabs, 1)

        # ---- buttons ------------------------------------------------------
        btns = QHBoxLayout()
        hint = _lbl("Game is paused.  Ctrl+Shift+, opens this window any time.", "Sub")
        btns.addWidget(hint)
        btns.addStretch(1)
        copy = QPushButton("Copy")
        copy.setToolTip("Copy these stats as text to the clipboard.")
        copy.clicked.connect(self._copy)
        btns.addWidget(copy)
        quit_b = QPushButton("Quit")
        quit_b.setObjectName("Danger")
        quit_b.setToolTip("Close the game.")
        quit_b.clicked.connect(lambda: self.finish("quit"))
        btns.addWidget(quit_b)
        sel = QPushButton("Character select")
        sel.setToolTip("Open the start menu to pick different characters.")
        sel.clicked.connect(lambda: self.finish("select"))
        btns.addWidget(sel)
        if not self.solo_end:
            keep = QPushButton("Resume" if (kind == "live" and not st.over) else "Keep watching")
            keep.setToolTip("Close this window; the fight carries on (stats keep counting).")
            keep.clicked.connect(lambda: self.finish("resume"))
            btns.addWidget(keep)
        rem = QPushButton("Rematch")
        rem.setObjectName("Primary")
        rem.setToolTip("Same characters, everyone fresh at full HP; stats start from zero.")
        rem.clicked.connect(lambda: self.finish("rematch"))
        rem.setDefault(True)
        btns.addWidget(rem)
        root.addLayout(btns)

        scr = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1400, scr.width() - 60), min(900, scr.height() - 60))
        self.move(scr.x() + (scr.width() - self.width()) // 2,
                  scr.y() + max(0, (scr.height() - self.height()) // 2))

    # ---- tabs -----------------------------------------------------------
    @staticmethod
    def _scroll(w):
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(w)
        sc.viewport().setStyleSheet("background: #12161c;")
        return sc

    def _fighters_tab(self):
        host = QWidget()
        host.setObjectName("Pane")
        host.setAttribute(Qt.WA_StyledBackground, True)
        row = QHBoxLayout(host)
        row.setSpacing(12)
        teams = sorted({s.team for s in self.fs})
        if not self.fs:
            row.addWidget(_lbl("No fighters yet.", "Sub"))
        for i, t in enumerate(teams):
            if i:
                row.addWidget(_lbl("VS", "Vs"), 0, Qt.AlignVCenter)
            col = QVBoxLayout()
            col.addWidget(_lbl("TEAM %d" % (t + 1), "Sec", _hex(TEAM_RGB[t % 2])))
            cards = QHBoxLayout()
            cards.setSpacing(10)
            for s in self.fs:
                if s.team == t:
                    cards.addWidget(Card(s, self.stats, self.world), 0, Qt.AlignTop)
            col.addLayout(cards)
            col.addStretch(1)
            row.addLayout(col)
        row.addStretch(1)
        return self._scroll(host)

    def _table(self, headers, rows, numeric_from=1):
        tb = QTableWidget(len(rows), len(headers))
        tb.setHorizontalHeaderLabels(headers)
        tb.verticalHeader().setVisible(False)
        tb.setAlternatingRowColors(True)
        tb.setEditTriggers(QTableWidget.NoEditTriggers)
        tb.setSelectionBehavior(QTableWidget.SelectRows)
        for r, cells in enumerate(rows):
            for c, cell in enumerate(cells):
                text, val, color = cell if isinstance(cell, tuple) else (str(cell), None, None)
                it = _Item(text, val)
                if color:
                    it.setForeground(QBrush(QColor(color)))
                if c >= numeric_from:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                tb.setItem(r, c, it)
        tb.setSortingEnabled(True)
        hh = tb.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setStretchLastSection(True)
        return tb

    def _actions_tab(self):
        headers = ["Fighter", "Action", "Uses", "Hits", "Damage", "Share", "Biggest", "Avg / hit"]
        rows = []
        for s in self.fs:
            for k, a in sorted(s.by_action.items(), key=lambda e: -e[1].dmg):
                if a.uses == 0 and a.hits == 0:
                    continue
                rows.append([("%s %s" % (s.slot or "-", s.name), s.pick * 100 + s.team, _hex(s.rgb, 0.35)),
                             (B.action_label(k), None, None),
                             (str(a.uses), a.uses, None), (str(a.hits), a.hits, None),
                             (n(a.dmg), a.dmg, "#ffb86b"),
                             ("%d%%" % int(round(_pct(a.dmg, s.dealt))), _pct(a.dmg, s.dealt), None),
                             (n(a.max_hit), a.max_hit, None),
                             ("%.1f" % (a.dmg / a.hits) if a.hits else "-", (a.dmg / a.hits) if a.hits else 0, None)])
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(_lbl("Uses = times the action started; Hits / Damage = what it landed.  "
                         "Click a column to sort.", "Sub"))
        v.addWidget(self._table(headers, rows, numeric_from=2), 1)
        return w

    def _h2h_tab(self):
        cols = [s.name for s in self.fs]
        extra = []
        for s in self.fs:
            for k in s.by_target:
                if k not in cols and k not in extra:
                    extra.append(k)
        targets = cols + extra
        headers = ["Dealt ↓ to →"] + [("Cursor" if t == B.CURSOR else t) for t in targets] + ["Total"]
        rows = []
        for s in self.fs:
            r = [("%s %s" % (s.slot or "-", s.name), s.pick, _hex(s.rgb, 0.35))]
            for t in targets:
                v = s.by_target.get(t, 0.0)
                r.append((n(v) if v else "-", v, "#ffb86b" if v else "#59636e"))
            r.append((n(s.dealt), s.dealt, "#ffffff"))
            rows.append(r)
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(_lbl("Each row = damage that fighter dealt to each column.  "
                         "Taken from (per fighter) is on its card's defence lines and below.", "Sub"))
        v.addWidget(self._table(headers, rows), 1)
        # Taken-from breakdown.
        src = []
        for s in self.fs:
            for k in s.by_source:
                if k not in src:
                    src.append(k)
        if src:
            rows2 = []
            for s in self.fs:
                r = [("%s %s" % (s.slot or "-", s.name), s.pick, _hex(s.rgb, 0.35))]
                for k in src:
                    val = s.by_source.get(k, 0.0)
                    r.append((n(val) if val else "-", val, "#ff8a80" if val else "#59636e"))
                r.append((n(s.taken), s.taken, "#ffffff"))
                rows2.append(r)
            v.addWidget(_lbl("Damage TAKEN from", "Sec"))
            v.addWidget(self._table(["Took ↓ from →"] + src + ["Total"], rows2), 1)
        return w

    # ---- text export ------------------------------------------------------
    def _copy(self):
        st, w = self.stats, self.world
        lines = ["PROJECT BEHAVIOR - BATTLE RESULTS",
                 "Fight time %s" % _secs(st.duration_s(w))]
        if st.winner is not None and st.winner >= 0:
            lines.append("Winner: Team %d" % (st.winner + 1))
        lines.append("")
        for s in self.fs:
            lines.append("[%s] %s  (Team %d)  %s" % (s.slot or "-", s.name, s.team + 1, _status(s, st, w)[0]))
            lines.append("  Dealt %s  Taken %s  KOs %d  Hits %d  Biggest %s%s" % (
                n(s.dealt), n(s.taken), s.kos, s.hits, n(s.max_hit),
                (" (%s)" % B.action_label(s.max_hit_action)) if s.max_hit > 0 else ""))
            lines.append("  Combo %d hits / %s  Burst %s  Blocked %d  Lowest HP %s" % (
                s.best_combo, n(s.best_combo_dmg), n(s.best_burst), s.blocked, n(s.low_hp)))
            lines.append("  Distance %s px  Top speed %s px/s  Knocked back %s px  Warps %d" % (
                n(s.distance), n(s.top_speed), n(s.kb_distance), s.teleports))
            for k, a in sorted(s.by_action.items(), key=lambda e: -e[1].dmg):
                if a.dmg > 0 or a.uses:
                    lines.append("    %-18s uses %3d  hits %4d  dmg %8s  max %s" % (
                        B.action_label(k), a.uses, a.hits, n(a.dmg), n(a.max_hit)))
            lines.append("")
        aw = st.awards()
        if aw:
            lines.append("AWARDS")
            for _i, name, who, _rgb, why in aw:
                lines.append("  %s - %s: %s" % (name, who, why))
        QApplication.clipboard().setText("\n".join(lines))

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


class _Item(QTableWidgetItem):
    """Table cell sorting by its number, not its text."""

    def __init__(self, text, val):
        super().__init__(text)
        self.val = val

    def __lt__(self, other):
        a, b = self.val, getattr(other, "val", None)
        if a is not None and b is not None:
            try:
                return float(a) < float(b)
            except (TypeError, ValueError):
                pass
        return self.text() < other.text()
