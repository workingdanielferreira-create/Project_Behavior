"""
Live camera settings window (Daniel 2026-11-21) — Ctrl+Alt+C opens / closes.

An ordinary clickable window (the overlay is click-through) that edits
World.live_view (laser/liveview.py) while the fight keeps running; every
change applies on the next tick and is saved to characters/live_view.json
(debounced, background write).  Solo and Battle alike.

  Battle speed   slider 10% .. 300% + "100%" reset
  Camera         Auto (World Camera) / Character focus / Duel cam
    focus        which fighter (by slot) + zoom 0.5x .. 4x
    duel         tick 2+ fighters + margin, min zoom (below 1.0x allowed),
                 max zoom
  Background     colour (picker) + opacity 0% .. 100%

The fighter lists follow the roster: rebuilt about twice a second when the
slots / fielded fighters change.  A benched tag / trio member stays
pickable — the camera follows whichever member of its group is on the
field.
"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QComboBox, QSlider,
                             QHBoxLayout, QVBoxLayout, QGridLayout, QCheckBox,
                             QFrame, QColorDialog)

from . import liveview as _lv

STYLE = """
QWidget#LiveView { background: #12161c; }
QWidget { color: #e6edf3; font-family: Consolas, 'Courier New', monospace; font-size: 12px; }
QLabel#Title { font-size: 16px; font-weight: bold; color: #ffffff; letter-spacing: 2px; }
QLabel#Sub { color: #8b98a5; }
QLabel#Head { font-weight: bold; color: #9ecbff; margin-top: 6px; }
QLabel#Val { color: #ffd479; min-width: 58px; }
QFrame#Box { background: #1a2029; border: 1px solid #2b3440; border-radius: 6px; }
QPushButton { background: #243041; border: 1px solid #36465c; border-radius: 4px; padding: 4px 10px; }
QPushButton:hover { background: #2e3d53; }
QComboBox { background: #1f2733; border: 1px solid #36465c; border-radius: 4px; padding: 3px 6px; }
QComboBox QAbstractItemView { background: #1f2733; selection-background-color: #36465c; }
QSlider::groove:horizontal { height: 6px; background: #2b3440; border-radius: 3px; }
QSlider::handle:horizontal { background: #9ecbff; width: 14px; margin: -5px 0; border-radius: 7px; }
QCheckBox::indicator { width: 14px; height: 14px; }
"""

REFRESH_MS = 500
SAVE_MS = 400


class LiveViewPanel(QWidget):
    def __init__(self, world, on_closed):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setObjectName("LiveView")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle("Project Behavior - Live Camera")
        self.setStyleSheet(STYLE)
        self.world = world
        self.lv = world.live_view
        self.on_closed = on_closed
        self._loading = False
        self._sig = None
        self._duel_boxes = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        t = QLabel("LIVE CAMERA")
        t.setObjectName("Title")
        sub = QLabel("Changes apply instantly.  Ctrl+Alt+C closes.")
        sub.setObjectName("Sub")
        root.addWidget(t)
        root.addWidget(sub)

        # --- Battle speed ---
        root.addWidget(self._head("Battle speed"))
        box, lay = self._box()
        row = QHBoxLayout()
        self.speed = self._slider(10, 300, self._on_speed)
        self.speed_val = self._val()
        b100 = QPushButton("100%")
        b100.clicked.connect(lambda: self.speed.setValue(100))
        row.addWidget(self.speed, 1)
        row.addWidget(self.speed_val)
        row.addWidget(b100)
        lay.addLayout(row)
        root.addWidget(box)

        # --- Camera ---
        root.addWidget(self._head("Camera"))
        box, lay = self._box()
        self.mode = QComboBox()
        for m in _lv.MODES:
            self.mode.addItem(_lv.MODE_LABELS[m], m)
        self.mode.currentIndexChanged.connect(self._on_mode)
        lay.addWidget(self.mode)

        # Character focus
        self.focus_w = QWidget()
        fl = QGridLayout(self.focus_w)
        fl.setContentsMargins(0, 4, 0, 0)
        fl.addWidget(QLabel("Fighter"), 0, 0)
        self.focus = QComboBox()
        self.focus.currentIndexChanged.connect(self._on_focus)
        fl.addWidget(self.focus, 0, 1, 1, 2)
        fl.addWidget(QLabel("Zoom"), 1, 0)
        self.fzoom = self._slider(50, 400, self._on_fzoom)
        self.fzoom_val = self._val()
        fl.addWidget(self.fzoom, 1, 1)
        fl.addWidget(self.fzoom_val, 1, 2)
        lay.addWidget(self.focus_w)

        # Duel cam
        self.duel_w = QWidget()
        dl = QVBoxLayout(self.duel_w)
        dl.setContentsMargins(0, 4, 0, 0)
        dl.addWidget(QLabel("Keep these fighters in frame (pick 2+):"))
        self.duel_list = QWidget()
        self.duel_lay = QGridLayout(self.duel_list)
        self.duel_lay.setContentsMargins(6, 0, 0, 0)
        dl.addWidget(self.duel_list)
        g = QGridLayout()
        g.addWidget(QLabel("Margin"), 0, 0)
        self.dmargin = self._slider(0, 600, self._on_dmargin)
        self.dmargin_val = self._val()
        g.addWidget(self.dmargin, 0, 1)
        g.addWidget(self.dmargin_val, 0, 2)
        g.addWidget(QLabel("Min zoom"), 1, 0)
        self.dmin = self._slider(25, 100, self._on_dmin)
        self.dmin_val = self._val()
        g.addWidget(self.dmin, 1, 1)
        g.addWidget(self.dmin_val, 1, 2)
        g.addWidget(QLabel("Max zoom"), 2, 0)
        self.dmax = self._slider(100, 400, self._on_dmax)
        self.dmax_val = self._val()
        g.addWidget(self.dmax, 2, 1)
        g.addWidget(self.dmax_val, 2, 2)
        dl.addLayout(g)
        self.duel_note = QLabel("")
        self.duel_note.setObjectName("Sub")
        dl.addWidget(self.duel_note)
        lay.addWidget(self.duel_w)
        root.addWidget(box)

        # --- Background ---
        root.addWidget(self._head("Background"))
        box, lay = self._box()
        row = QHBoxLayout()
        row.addWidget(QLabel("Colour"))
        self.color_btn = QPushButton("")
        self.color_btn.setFixedWidth(70)
        self.color_btn.clicked.connect(self._pick_color)
        row.addWidget(self.color_btn)
        row.addStretch(1)
        lay.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Opacity"))
        self.alpha = self._slider(0, 100, self._on_alpha)
        self.alpha_val = self._val()
        row.addWidget(self.alpha, 1)
        row.addWidget(self.alpha_val)
        lay.addLayout(row)
        root.addWidget(box)

        close = QPushButton("Close")
        close.clicked.connect(self.close)
        root.addWidget(close, 0, Qt.AlignRight)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.lv.save)
        self._refresh = QTimer(self)
        self._refresh.timeout.connect(self._refresh_fighters)
        self._refresh.start(REFRESH_MS)

        self.setMinimumWidth(380)
        self._load()

    # --- widgets ----------------------------------------------------------
    @staticmethod
    def _head(text):
        h = QLabel(text.upper())
        h.setObjectName("Head")
        return h

    @staticmethod
    def _box():
        f = QFrame()
        f.setObjectName("Box")
        lay = QVBoxLayout(f)
        lay.setContentsMargins(10, 8, 10, 8)
        return f, lay

    @staticmethod
    def _val():
        v = QLabel("")
        v.setObjectName("Val")
        v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return v

    @staticmethod
    def _slider(lo, hi, fn):
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.valueChanged.connect(fn)
        return s

    # --- state <-> widgets -------------------------------------------------
    def _load(self):
        c = self.lv.cfg
        self._loading = True
        self.speed.setValue(int(round(c["speed"] * 100)))
        self.mode.setCurrentIndex(max(0, _lv.MODES.index(c["cam_mode"])))
        self.fzoom.setValue(int(round(c["focus_zoom"] * 100)))
        self.dmargin.setValue(int(round(c["duel_margin_px"])))
        self.dmin.setValue(int(round(c["duel_min_zoom"] * 100)))
        self.dmax.setValue(int(round(c["duel_max_zoom"] * 100)))
        self.alpha.setValue(int(round(c["bg_alpha"])))
        self._loading = False
        self._labels()
        self._show_color()
        self._show_mode()
        self._refresh_fighters(force=True)

    def _labels(self):
        c = self.lv.cfg
        self.speed_val.setText("%d%%" % int(round(c["speed"] * 100)))
        self.fzoom_val.setText("%.2fx" % c["focus_zoom"])
        self.dmargin_val.setText("%d px" % int(c["duel_margin_px"]))
        self.dmin_val.setText("%.2fx" % c["duel_min_zoom"])
        self.dmax_val.setText("%.2fx" % c["duel_max_zoom"])
        self.alpha_val.setText("%d%%" % int(round(c["bg_alpha"])))

    def _show_mode(self):
        m = self.lv.cfg["cam_mode"]
        self.focus_w.setVisible(m == "focus")
        self.duel_w.setVisible(m == "duel")
        self.adjustSize()

    def _show_color(self):
        col = self.lv.cfg["bg_color"]
        fg = "#000000" if QColor(col).lightness() > 128 else "#ffffff"
        self.color_btn.setText(col)
        self.color_btn.setStyleSheet("background: %s; color: %s;" % (col, fg))

    def _set(self, key, value):
        if self._loading:
            return
        self.lv.set(key, value)
        self._labels()
        self._save_timer.start(SAVE_MS)

    # --- handlers -----------------------------------------------------------
    def _on_speed(self, v):
        self._set("speed", v / 100.0)

    def _on_mode(self, i):
        if self._loading:
            return
        self._set("cam_mode", self.mode.itemData(i))
        self._show_mode()
        self._duel_note()

    def _on_focus(self, i):
        if self._loading or i < 0:
            return
        self._set("focus_slot", self.focus.itemData(i))

    def _on_fzoom(self, v):
        self._set("focus_zoom", v / 100.0)

    def _on_dmargin(self, v):
        self._set("duel_margin_px", float(v))

    def _on_dmin(self, v):
        self._set("duel_min_zoom", v / 100.0)

    def _on_dmax(self, v):
        self._set("duel_max_zoom", v / 100.0)

    def _on_alpha(self, v):
        self._set("bg_alpha", float(v))

    def _on_duel_box(self, idx, on):
        if self._loading:
            return
        cur = set(self.lv.cfg["duel_slots"])
        if on:
            cur.add(idx)
        else:
            cur.discard(idx)
        self._set("duel_slots", sorted(cur))
        self._duel_note()

    def _pick_color(self):
        col = QColorDialog.getColor(QColor(self.lv.cfg["bg_color"]), self,
                                    "Background colour")
        if col.isValid():
            self._set("bg_color", col.name())
            self._show_color()

    def _duel_note(self):
        n = len([i for i in self.lv.cfg["duel_slots"] if i in self._duel_boxes])
        self.duel_note.setText("" if n >= 2 else
                               "Pick at least 2 fighters (1 = it follows that one).")

    # --- fighter lists ------------------------------------------------------
    def _entries(self):
        """[(slot index, label)] for every slot holding a character."""
        w = self.world
        out = []
        live = {id(f) for f in w.all_figures()}
        for s in getattr(w, "slots", None) or ():
            if not s.char:
                continue
            on = s.fig is not None and id(s.fig) in live
            out.append((s.index, "%s  %s  (Team %d)%s" % (
                getattr(s, "name", chr(65 + s.index)), s.char, s.team + 1,
                "" if on else "  - benched / off")))
        return out

    def _refresh_fighters(self, force=False):
        try:
            ents = self._entries()
        except Exception:
            return
        sig = tuple(ents)
        if not force and sig == self._sig:
            return
        self._sig = sig
        c = self.lv.cfg
        self._loading = True
        try:
            # Focus dropdown
            self.focus.clear()
            pick = -1
            for k, (idx, label) in enumerate(ents):
                self.focus.addItem(label, idx)
                if idx == c["focus_slot"]:
                    pick = k
            if pick < 0 and ents:
                pick = 0
            if pick >= 0:
                self.focus.setCurrentIndex(pick)
            # Duel tick boxes
            while self.duel_lay.count():
                it = self.duel_lay.takeAt(0)
                if it.widget() is not None:
                    it.widget().deleteLater()
            self._duel_boxes = {}
            chosen = set(c["duel_slots"])
            for k, (idx, label) in enumerate(ents):
                cb = QCheckBox(label)
                cb.setChecked(idx in chosen)
                cb.toggled.connect(lambda on, i=idx: self._on_duel_box(i, on))
                self.duel_lay.addWidget(cb, k, 0)
                self._duel_boxes[idx] = cb
            if not ents:
                self.duel_lay.addWidget(QLabel("(no fighters in the roster)"), 0, 0)
        finally:
            self._loading = False
        # A focus slot that no longer holds a character -> the first one.
        if ents and c["focus_slot"] not in [e[0] for e in ents]:
            self.lv.set("focus_slot", self.focus.itemData(self.focus.currentIndex()))
            self._save_timer.start(SAVE_MS)
        self._duel_note()
        self.adjustSize()

    # --- closing ------------------------------------------------------------
    def closeEvent(self, e):
        self._refresh.stop()
        if self._save_timer.isActive():
            self._save_timer.stop()
        self.lv.save()
        cb, self.on_closed = self.on_closed, None
        if cb is not None:
            cb()
        super().closeEvent(e)
