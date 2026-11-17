"""
Start menu — the character select window.

Opens when the updater launches the game (update_game.py / update_latest.py
pass --prebattle) and with Ctrl+Shift+. (Ctrl+'>') mid-game.  The game is
paused behind it (laser/prebattle.py draws the paused screen).  It replaces
the old on-overlay corner panels: the overlay itself is click-through, so
the menu is an ordinary window you can click.

Left: every registered character (built-ins and Rig Forge packages) as a
card.  Right: the roster slots (laser/roster.py): A-D always, "+ Add
fighter" adds E-H (roster.MAX_SLOTS) and an added slot has its own Remove
button; "Clear all" empties every slot (teams, hotkeys and the number of
slots stay).  Click a slot, then a
character card, to put that character in it — the slot gets the next
selection number, which orders the HP bars and the fielding.  Per slot:

  * Team       Team 1 or Team 2
  * State      Single (fights alone), Trio (Rig Forge: click two
               team-mates, click order = rotation order; Rotation dropdown
               1 > 2 > 3 / ping-pong / healthiest / random), or Tag (Rig
               Forge characters only):
               choosing Tag asks for the partner — click its slot (or a
               character card, which fills an empty slot); the partner
               switches to Tag, joins the team, and both borders take the
               pair's colour.  The pair swaps in and out with the Switch
               action (laser/tag.py)
  * Teams      any split of the slots (1v1, 2v2, 1v3, 3v1, 4v4 ...)
  * Hotkeys    Field / cycle, Ultimate, Special and Tag in — click a key
               box and press the combo (Esc cancels, Delete / Backspace
               clears it)

Start applies the roster and keeps the state (HP, cooldowns, position) of
every fighter whose slot kept its character and team; Reset & Start fields
everyone fresh; Cancel (or closing the window) resumes unchanged.  The
roster is saved to roster.json.  World-level: Solo and Battle read the same
roster.
"""

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QIcon, QPainter
from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QToolButton, QComboBox,
                             QHBoxLayout, QVBoxLayout, QGridLayout, QFrame,
                             QScrollArea, QApplication, QSizePolicy)

from . import modes
from . import roster as _roster
from . import tag as _tag

CARD_ICON = 84
SLOT_THUMB = 56

STYLE = """
QWidget#StartMenu { background: #12161c; }
QWidget { color: #e6edf3; font-family: Consolas, 'Courier New', monospace; font-size: 12px; }
QLabel#Title { font-size: 20px; font-weight: bold; color: #ffffff; letter-spacing: 2px; }
QLabel#Sub { color: #8b98a5; }
QLabel#SlotName { font-size: 15px; font-weight: bold; }
QLabel#Pick { font-size: 13px; font-weight: bold; color: #ffe600; }
QLabel#Info { color: #8b98a5; font-size: 11px; }
QLabel#Errors { color: #ff8a80; }
QFrame#Slot { background: #1b2129; border: 2px solid #2a323d; border-radius: 8px; }
QFrame#Slot[selected="true"] { border: 2px solid #ffe600; background: #243040; }
QFrame#Slot[team="0"] QLabel#SlotName { color: #7cc4ff; }
QFrame#Slot[team="1"] QLabel#SlotName { color: #ff8fb1; }
QToolButton#Card { background: #1b2129; border: 2px solid #2a323d; border-radius: 8px; padding: 6px; }
QToolButton#Card:hover { border: 2px solid #ffe600; }
QPushButton, QComboBox { background: #252d38; border: 1px solid #3a4553; border-radius: 5px; padding: 4px 8px; }
QPushButton:hover, QComboBox:hover { border: 1px solid #ffe600; }
QPushButton:disabled { color: #59636e; }
QPushButton#Key { min-width: 96px; text-align: center; }
QPushButton#Key[capturing="true"] { background: #4a3f00; border: 1px solid #ffe600; }
QPushButton#Primary { background: #0b6e4f; border: 1px solid #12a378; font-weight: bold; padding: 7px 18px; }
QPushButton#Primary:disabled { background: #253029; border: 1px solid #33443a; }
QComboBox QAbstractItemView { background: #252d38; selection-background-color: #3a4553; }
QScrollArea { border: none; background: #12161c; }
QWidget#Grid { background: #12161c; }
QScrollBar:vertical { background: #12161c; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #3a4553; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #ffe600; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""


def char_name(key):
    m = modes.MODE_REGISTRY.get(key)
    ch = getattr(m, "character", None) if m is not None else None
    return str((ch or {}).get("display_name") or key).replace("_", " ")


def char_pixmap(assets, key, size):
    """The character's first idle frame (else run frame) fitted in size x size."""
    pm = None
    try:
        b = assets.bundle(key)
        frames = (b.idle or []) or (b.run or [])
        pm = frames[0] if frames else None
    except Exception:
        pm = None
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    if pm is None or pm.isNull():
        return out
    sc = pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    qp = QPainter(out)
    qp.drawPixmap((size - sc.width()) // 2, (size - sc.height()) // 2, sc)
    qp.end()
    return out


def has_action(assets, key, name):
    try:
        return name in assets.bundle(key).extra
    except Exception:
        return False


# Qt key -> Windows VK, for when the event carries no native key (non-Windows).
_QT_VK = {Qt.Key_Minus: 0xBD, Qt.Key_Equal: 0xBB, Qt.Key_BracketLeft: 0xDB,
          Qt.Key_BracketRight: 0xDD, Qt.Key_Semicolon: 0xBA, Qt.Key_Apostrophe: 0xDE,
          Qt.Key_Comma: 0xBC, Qt.Key_Period: 0xBE, Qt.Key_Slash: 0xBF,
          Qt.Key_QuoteLeft: 0xC0, Qt.Key_Backslash: 0xDC, Qt.Key_Space: 0x20,
          Qt.Key_Up: 0x26, Qt.Key_Down: 0x28, Qt.Key_Left: 0x25, Qt.Key_Right: 0x27,
          Qt.Key_Insert: 0x2D, Qt.Key_Home: 0x24, Qt.Key_End: 0x23,
          Qt.Key_PageUp: 0x21, Qt.Key_PageDown: 0x22, Qt.Key_Return: 0x0D, Qt.Key_Enter: 0x0D}


def event_vk(e):
    if sys.platform.startswith("win"):
        vk = int(e.nativeVirtualKey() or 0)
        if vk:
            return vk
    k = e.key()
    if Qt.Key_0 <= k <= Qt.Key_9:
        return (0x60 if e.modifiers() & Qt.KeypadModifier else 0x30) + (k - Qt.Key_0)
    if Qt.Key_A <= k <= Qt.Key_Z:
        return 0x41 + (k - Qt.Key_A)
    if Qt.Key_F1 <= k <= Qt.Key_F12:
        return 0x70 + (k - Qt.Key_F1)
    return _QT_VK.get(k, 0)


class KeyButton(QPushButton):
    """A hotkey box: click, then press the combo."""

    def __init__(self, combo, on_change):
        super().__init__()
        self.setObjectName("Key")
        self.combo = combo or ""
        self.on_change = on_change
        self.capturing = False
        self.setFocusPolicy(Qt.StrongFocus)
        self.clicked.connect(self._start)
        self._show()

    def _show(self):
        self.setProperty("capturing", "true" if self.capturing else "false")
        self.setText("press keys..." if self.capturing else (self.combo or "- none -"))
        self.style().unpolish(self)
        self.style().polish(self)

    def _start(self):
        self.capturing = True
        self.grabKeyboard()
        self._show()

    def _stop(self):
        self.capturing = False
        self.releaseKeyboard()
        self._show()

    def focusOutEvent(self, e):
        if self.capturing:
            self._stop()
        super().focusOutEvent(e)

    def keyPressEvent(self, e):
        if not self.capturing:
            return super().keyPressEvent(e)
        k = e.key()
        if k in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr):
            return
        mods = e.modifiers()
        if k == Qt.Key_Escape:
            self._stop()
            return
        if k in (Qt.Key_Delete, Qt.Key_Backspace) and not (mods & (Qt.ControlModifier | Qt.AltModifier)):
            self.combo = ""
            self._stop()
            self.on_change(self.combo)
            return
        name = _roster.combo_name(event_vk(e), bool(mods & Qt.ControlModifier),
                                  bool(mods & Qt.ShiftModifier), bool(mods & Qt.AltModifier))
        if not name:
            self.setText("can't use that key")
            return
        self.combo = name
        self._stop()
        self.on_change(self.combo)


class SlotPanel(QFrame):
    def __init__(self, menu, slot):
        super().__init__()
        self.menu = menu
        self.slot = slot
        self.setObjectName("Slot")
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        top = QHBoxLayout()
        self.thumb = QLabel()
        self.thumb.setFixedSize(SLOT_THUMB, SLOT_THUMB)
        top.addWidget(self.thumb)
        col = QVBoxLayout()
        hdr = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("SlotName")
        self.pick = QLabel()
        self.pick.setObjectName("Pick")
        self.title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.pick.setMinimumWidth(36)
        self.pick.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hdr.addWidget(self.title, 1)
        hdr.addWidget(self.pick)
        col.addLayout(hdr)
        row = QHBoxLayout()
        self.team = QComboBox()
        self.team.addItems(["Team 1", "Team 2"])
        self.team.currentIndexChanged.connect(self._team)
        self.state = QComboBox()
        self.state.addItems(["Single", "Tag", "Trio"])
        self.state.currentIndexChanged.connect(self._state)
        # Trio rotation (roster.ROTATIONS): shown on trio slots only.
        self.rot = QComboBox()
        for r in _roster.ROTATIONS:
            self.rot.addItem(_roster.ROTATION_LABELS[r], r)
        self.rot.setToolTip("Who each Switch brings in.")
        self.rot.currentIndexChanged.connect(self._rot)
        self.clear = QPushButton("Clear")
        self.clear.clicked.connect(self._clear)
        row.addWidget(self.team)
        row.addWidget(self.state)
        row.addWidget(self.rot)
        row.addStretch(1)
        row.addWidget(self.clear)
        # Added slots (E-H) can be removed again (roster.remove_slot).
        if slot.index >= _roster.MIN_SLOTS:
            self.remove = QPushButton("Remove")
            self.remove.setToolTip("Remove this slot (the later slots move up a letter).")
            self.remove.clicked.connect(lambda: self.menu.remove_slot(self.slot.index))
            row.addWidget(self.remove)
        col.addLayout(row)
        top.addLayout(col, 1)
        lay.addLayout(top)

        keys = QGridLayout()
        keys.setHorizontalSpacing(8)
        keys.setVerticalSpacing(2)
        self.keybtn = {}
        for n, a in enumerate(_roster.KEY_ACTIONS):
            lab = QLabel(_roster.KEY_LABELS[a])
            lab.setObjectName("Info")
            b = KeyButton(slot.keys.get(a), lambda v, a=a: self._key(a, v))
            keys.addWidget(lab, 0, n)
            keys.addWidget(b, 1, n)
            self.keybtn[a] = b
        lay.addLayout(keys)
        self.info = QLabel()
        self.info.setObjectName("Info")
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.refresh()

    def mousePressEvent(self, e):
        self.menu.slot_clicked(self.slot.index)
        super().mousePressEvent(e)

    def _team(self, i):
        if self.menu.loading:
            return
        self.slot.team = i
        # A tag partner / trio moves with it, so the group stays together.
        if self.slot.link is not None:
            self.menu.slots[self.slot.link].team = i
        for o in _roster.trio_members(self.menu.slots, self.slot) or ():
            o.team = i
        self.menu.changed()

    def _rot(self, i):
        if self.menu.loading:
            return
        _roster.set_rotation(self.menu.slots, self.slot, self.rot.itemData(i))
        self.menu.changed()

    def _state(self, i):
        if self.menu.loading:
            return
        if i in (1, 2):
            # Tag: pick the partner next; Trio: the next two team-mates, in
            # rotation order (slots, or character cards).
            self.menu.start_linking(self.slot.index, "trio" if i == 2 else "tag")
        else:
            _roster.unlink(self.menu.slots, self.slot)
            if self.menu.linking == self.slot.index:
                self.menu._cancel_link()
        self.menu.changed()

    def _clear(self):
        _roster.unlink(self.menu.slots, self.slot)
        if self.menu.linking == self.slot.index:
            self.menu._cancel_link()
        self.slot.char = None
        self.slot.pick = 0
        self.menu.select(self.slot.index)
        self.menu.changed()

    def _key(self, action, combo):
        self.slot.keys[action] = combo
        self.menu.changed()

    def refresh(self):
        s, m = self.slot, self.menu
        m.loading = True
        self.setProperty("selected", "true" if m.selected == s.index else "false")
        self.setProperty("team", str(s.team))
        # Linked tag partners share a border colour (roster.PAIR_COLORS);
        # the slot waiting for its partner blinks in the selection yellow.
        k = _roster.pair_index(m.slots, s, _tag.can_tag)
        if m.linking is not None and s.index in m.link_buf:
            self.setStyleSheet("QFrame#Slot { border: 3px dashed #ffe600; }")
        elif k >= 0:
            c = _roster.PAIR_COLORS[k % len(_roster.PAIR_COLORS)]
            self.setStyleSheet("QFrame#Slot { border: 3px solid rgb(%d,%d,%d); }" % c)
        else:
            self.setStyleSheet("")
        self.style().unpolish(self)
        self.style().polish(self)
        for w in self.findChildren(QLabel):
            w.style().unpolish(w)
            w.style().polish(w)
        self.title.setText("SLOT %s   %s" % (s.name, char_name(s.char).upper() if s.char else "- empty -"))
        self.pick.setText("#%d" % s.pick if s.char else "")
        self.thumb.setPixmap(char_pixmap(m.assets, s.char, SLOT_THUMB) if s.char else QPixmap())
        self.team.setCurrentIndex(s.team)
        taggable = bool(s.char) and _tag.can_tag(s.char)
        pending = m.linking == s.index
        trio = s.trio is not None or (pending and m.link_mode == "trio")
        self.state.setCurrentIndex(2 if trio else (1 if (s.tag or pending) else 0))
        self.state.setEnabled(taggable)
        self.state.setToolTip("" if taggable else "Only Rig Forge characters can Tag / Trio.")
        self.rot.setVisible(s.trio is not None)
        self.rot.setCurrentIndex(max(0, _roster.ROTATIONS.index(s.rot) if s.rot in _roster.ROTATIONS else 0))
        self.clear.setEnabled(bool(s.char))
        for a, b in self.keybtn.items():
            b.combo = s.keys.get(a) or ""
            b._show()
        self.info.setText(m.slot_info(s))
        m.loading = False


class StartMenu(QWidget):
    def __init__(self, world, on_done):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.setObjectName("StartMenu")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle("Project Behavior - Character Select")
        self.setStyleSheet(STYLE)
        self.world = world
        self.assets = world.assets
        self.on_done = on_done
        self.loading = False
        self._done = False
        self.slots = [s.copy() for s in world.slots]
        for s in self.slots:
            s.fig = None
        self.selected = next((s.index for s in self.slots if not s.char), 0)
        self.linking = None      # slot index waiting for its Tag partner / Trio mates
        self.link_mode = "tag"   # "tag" | "trio"
        self.link_buf = []       # slots picked so far (trio: rotation order)
        self.flash = ""          # one-off message under the slots

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        t = QLabel("CHARACTER SELECT")
        t.setObjectName("Title")
        sub = QLabel("Click a slot, then a character.  Set a slot to Tag, then click its partner.")
        sub.setObjectName("Sub")
        root.addWidget(t)
        root.addWidget(sub)

        body = QHBoxLayout()
        body.setSpacing(16)
        # Character grid
        grid_host = QWidget()
        grid_host.setObjectName("Grid")
        grid_host.setAttribute(Qt.WA_StyledBackground, True)
        grid = QGridLayout(grid_host)
        grid.setSpacing(8)
        order = modes.ordered_modes()
        cols = 4
        for n, key in enumerate(order):
            b = QToolButton()
            b.setObjectName("Card")
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIcon(QIcon(char_pixmap(self.assets, key, CARD_ICON)))
            b.setIconSize(char_pixmap(self.assets, key, CARD_ICON).size())
            kind = "Rig Forge - Tag" if _tag.can_tag(key) else "built-in"
            b.setText("%s\n%s" % (char_name(key), kind))
            b.setFixedSize(132, 132)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.pick_char(k))
            grid.addWidget(b, n // cols, n % cols)
        grid.setRowStretch(len(order) // cols + 1, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_host)
        scroll.viewport().setStyleSheet("background: #12161c;")
        scroll.setMinimumWidth(4 * 140 + 24)
        body.addWidget(scroll, 1)
        # Slots: a header row (count, + Add fighter, Clear all) over a
        # scrolling column of slot panels (4 by default, up to MAX_SLOTS).
        right = QVBoxLayout()
        right.setSpacing(8)
        head = QHBoxLayout()
        self.count_lbl = QLabel()
        self.count_lbl.setObjectName("Sub")
        self.add_btn = QPushButton("+ Add fighter")
        self.add_btn.setToolTip("Add another slot (up to %d)." % _roster.MAX_SLOTS)
        self.add_btn.clicked.connect(self.add_slot)
        self.clear_all_btn = QPushButton("Clear all")
        self.clear_all_btn.setToolTip("Empty every slot and break every Tag link.  "
                                      "Teams, hotkeys and the number of slots stay.")
        self.clear_all_btn.clicked.connect(self.clear_all)
        head.addWidget(self.count_lbl)
        head.addStretch(1)
        head.addWidget(self.add_btn)
        head.addWidget(self.clear_all_btn)
        right.addLayout(head)
        self.slot_host = QWidget()
        self.slot_host.setObjectName("Grid")
        self.slot_host.setAttribute(Qt.WA_StyledBackground, True)
        self.slot_lay = QVBoxLayout(self.slot_host)
        self.slot_lay.setContentsMargins(0, 0, 4, 0)
        self.slot_lay.setSpacing(8)
        self.slot_scroll = QScrollArea()
        self.slot_scroll.setWidgetResizable(True)
        self.slot_scroll.setWidget(self.slot_host)
        self.slot_scroll.viewport().setStyleSheet("background: #12161c;")
        right.addWidget(self.slot_scroll, 1)
        self.panels = []
        self._build_panels()
        body.addLayout(right, 1)
        root.addLayout(body, 1)

        self.errors = QLabel()
        self.errors.setObjectName("Errors")
        self.errors.setWordWrap(True)
        root.addWidget(self.errors)
        btns = QHBoxLayout()
        hint = QLabel("Game is paused.  Start keeps unchanged fighters' HP and cooldowns.")
        hint.setObjectName("Sub")
        btns.addWidget(hint)
        btns.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(lambda: self.finish(None, False))
        self.reset_btn = QPushButton("Reset && Start")
        self.reset_btn.setToolTip("Field every fighter fresh (full HP, no cooldowns).")
        self.reset_btn.clicked.connect(lambda: self.finish(self.slots, True))
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setDefault(True)
        self.start_btn.clicked.connect(lambda: self.finish(self.slots, False))
        btns.addWidget(self.cancel_btn)
        btns.addWidget(self.reset_btn)
        btns.addWidget(self.start_btn)
        root.addLayout(btns)

        self.resize(1240, 800)
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.x() + (scr.width() - self.width()) // 2,
                  scr.y() + max(0, (scr.height() - self.height()) // 2))
        self.changed()

    def _build_panels(self):
        """(Re)build one SlotPanel per slot (after a slot is added / removed)."""
        for pn in self.panels:
            self.slot_lay.removeWidget(pn)
            pn.setParent(None)
            pn.deleteLater()
        while self.slot_lay.count():
            self.slot_lay.takeAt(0)
        self.panels = []
        for s in self.slots:
            pn = SlotPanel(self, s)
            pn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            self.panels.append(pn)
            self.slot_lay.addWidget(pn)
        self.slot_lay.addStretch(1)

    # --- model -------------------------------------------------------------
    def add_slot(self):
        s = _roster.add_slot(self.slots)
        if s is None:
            self.flash = "At most %d fighters." % _roster.MAX_SLOTS
            self.changed()
            return
        self.selected = s.index
        self._build_panels()
        self.changed()
        self.slot_scroll.ensureWidgetVisible(self.panels[-1])

    def remove_slot(self, i):
        if self.linking is not None:
            self._cancel_link()
        if not _roster.remove_slot(self.slots, i):
            return
        if self.selected >= len(self.slots) or self.selected == i:
            self.selected = min(i, len(self.slots) - 1)
        elif self.selected > i:
            self.selected -= 1
        self._build_panels()
        self.changed()

    def clear_all(self):
        _roster.clear_all(self.slots)
        self._cancel_link()
        self.selected = 0
        self.changed()

    def select(self, i):
        self.selected = i
        for pn in self.panels:
            pn.refresh()

    def start_linking(self, i, mode="tag"):
        """Slot i was set to Tag / Trio: the next slot clicked (or character
        card, which fills an empty slot) becomes its partner; a Trio takes
        two, and the click order is the rotation order (i is 1st)."""
        _roster.unlink(self.slots, self.slots[i])
        self.linking = i
        self.link_mode = mode
        self.link_buf = [i]
        self.selected = i

    def _cancel_link(self):
        self.linking = None
        self.link_buf = []

    def _finish_link(self, j):
        a, b = self.slots[self.linking], self.slots[j]
        if j in self.link_buf:
            return
        if not b.char or not _tag.can_tag(b.char):
            self.flash = "Slot %s can't %s: %s." % (
                b.name, "join a Trio" if self.link_mode == "trio" else "tag",
                "it is empty" if not b.char else "only Rig Forge characters can")
            self._cancel_link()
            return
        b.team = a.team              # the partner joins its team
        if self.link_mode == "trio":
            self.link_buf.append(j)
            if len(self.link_buf) < 3:
                return               # waiting for the third
            members = [self.slots[k] for k in self.link_buf]
            self._cancel_link()
            _roster.make_trio(self.slots, members, a.rot)
            return
        self._cancel_link()
        _roster.link(self.slots, a, b)

    def slot_clicked(self, i):
        if self.linking is not None and i not in self.link_buf:
            self._finish_link(i)
            self.changed()
            return
        if self.linking == i:
            self._cancel_link()      # clicked itself again: cancel
        self.select(i)

    def pick_char(self, key):
        if self.linking is not None:
            # Linking: the card goes into the first empty slot as the partner.
            empty = next((o for o in self.slots if not o.char), None)
            if empty is None:
                self.flash = "No empty slot for a team-mate - click a filled slot (or + Add fighter)."
                self.changed()
                return
            empty.char = key
            empty.pick = _roster.next_pick(self.slots)
            self._finish_link(empty.index)
            self.changed()
            return
        s = self.slots[self.selected]
        if not s.char:
            s.pick = _roster.next_pick(self.slots)
        s.char = key
        # Next empty slot is selected, so clicking cards fills them in turn.
        nxt = next((o.index for o in self.slots[self.selected + 1:] + self.slots[:self.selected]
                    if not o.char), None)
        if nxt is not None:
            self.selected = nxt
        self.changed()

    def slot_info(self, s):
        if self.linking == s.index:
            if self.link_mode == "trio":
                return ("Trio: click team-mate %d of 2 (a slot, or a character card).  Click order = "
                        "rotation order.  Click this slot again to cancel." % len(self.link_buf))
            return "Tag: click the slot (or a character card) to tag with.  Click this slot again to cancel."
        if self.linking is not None and s.index in self.link_buf:
            return "Trio: picked as #%d of 3." % (self.link_buf.index(s.index) + 1)
        if not s.char:
            return "Empty.  Select this slot and click a character."
        ms = _roster.trio_members(self.slots, s)
        if ms is not None:
            n = ms.index(s) + 1
            order = " > ".join(m.name for m in ms)
            txt = "Trio #%d of 3 (rotation %s, %s).  %s  Click its benched HP card in game to tag it in." % (
                n, order, _roster.ROTATION_LABELS[s.rot],
                "Starts on the field." if n == 1 else "Starts on the bench.")
            miss = [a for a in ("switch_in", "switch_out") if not has_action(self.assets, s.char, a)]
            if miss:
                txt += "  No %s animation (Rig Forge) - skipped." % " / ".join(miss)
            return txt
        if not s.tag:
            return "Single: fights on its own."
        o = self.slots[s.link]
        lead = s if (s.pick, s.index) < (o.pick, o.index) else o
        miss = [a for a in ("switch_in", "switch_out") if not has_action(self.assets, s.char, a)]
        txt = "Tag: linked with slot %s.  %s" % (
            o.name, "Starts on the field." if lead is s else "Starts on the bench.")
        if miss:
            txt += "  No %s animation (Rig Forge) - skipped." % " / ".join(miss)
        return txt

    def changed(self):
        _roster.renumber(self.slots)
        _roster.clean_links(self.slots, _tag.can_tag)
        if self.linking is not None and not self.slots[self.linking].char:
            self._cancel_link()
        for pn in self.panels:
            pn.refresh()
        errs = _roster.validate(self.slots, _tag.can_tag)
        if self.linking is not None:
            errs = ["Pick slot %s's %s first." % (self.slots[self.linking].name,
                    "Trio team-mates" if self.link_mode == "trio" else "Tag partner")] + errs
        msg = errs + ([self.flash] if self.flash else [])
        self.flash = ""
        n = sum(1 for s in self.slots if s.char)
        self.count_lbl.setText("FIGHTERS  %d picked  -  %d / %d slots"
                               % (n, len(self.slots), _roster.MAX_SLOTS))
        self.add_btn.setEnabled(len(self.slots) < _roster.MAX_SLOTS)
        self.clear_all_btn.setEnabled(any(s.char or s.grouped for s in self.slots))
        self.errors.setText("\n".join(msg))
        self.start_btn.setEnabled(not errs)
        self.reset_btn.setEnabled(not errs)

    # --- closing -----------------------------------------------------------
    def finish(self, slots, reset):
        if self._done:
            return
        self._done = True
        out = [s.copy() for s in slots] if slots is not None else None
        self.close()
        self.on_done(out, reset)

    def close_silently(self):
        self._done = True
        self.close()

    def closeEvent(self, e):
        if not self._done:
            self._done = True
            self.on_done(None, False)
        super().closeEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.finish(None, False)
            return
        super().keyPressEvent(e)
