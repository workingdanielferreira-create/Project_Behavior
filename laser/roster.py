"""
Roster — the four fighter slots the start menu (laser/startmenu.py) sets up.

Each slot holds one character (or none), the team it fights for (Team 1 /
Team 2 — any split of the four slots: 1v1, 2v2, 1v3, 3v1, ...; a battle
needs a fighter on each team, 4v0 is Solo with four fighters), its battle
state ("single", or "tag" linked to one partner slot) and its own hotkeys:

    cycle     field / cycle / retire this slot's character (was 1/2/3/4)
    ultimate  force this fighter's ultimate                (was Ctrl+1/2)
    special   force this fighter's attack_special          (was Ctrl+Shift+1..4)
    tag       Switch this fighter in from the bench        (tag pairs only)

Tag links are explicit: setting a slot to Tag in the start menu asks for
its partner, and clicking that team-mate's slot links the two (`link` =
the partner's slot index, on both).  A linked pair (laser/tag.py) has one
fighter on the field and one on the bench, swapping with the Switch
action; a team can hold more than one pair.  Only Rig Forge characters
(they author switch_in / switch_out) can tag.

`pick` is the selection order: the start menu numbers a slot when a
character is put into it, and HP bars (laser/hpbars.py), fielding order and
which tag partner starts on the field all follow it.

The roster is saved to roster.json in the game folder so the menu opens with
the last setup.  World-level: Solo (one team fielded) and Battle (both)
read the same slots.
"""

import json
import os

SLOT_COUNT = 4
TEAM_COUNT = 2
TEAM_SIZE = 4             # any split of the 4 slots
SLOT_NAMES = ("A", "B", "C", "D")
KEY_ACTIONS = ("cycle", "ultimate", "special", "tag")
KEY_LABELS = {"cycle": "Field / cycle", "ultimate": "Ultimate",
              "special": "Special", "tag": "Tag in"}
FILE_NAME = "roster.json"

# One colour per tag pair (start-menu borders, HP-bar brackets), in pair order.
PAIR_COLORS = ((255, 170, 40), (80, 220, 150), (190, 120, 255), (90, 190, 255))

# Virtual-key names a binding can use (Windows VK codes).
_VK = {}
for _i in range(10):
    _VK[str(_i)] = 0x30 + _i
    _VK["Num%d" % _i] = 0x60 + _i
for _i in range(26):
    _VK[chr(0x41 + _i)] = 0x41 + _i
for _i in range(1, 13):
    _VK["F%d" % _i] = 0x6F + _i
_VK.update({"-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, ";": 0xBA, "'": 0xDE,
            ",": 0xBC, ".": 0xBE, "/": 0xBF, "`": 0xC0, "\\": 0xDC,
            "Space": 0x20, "Up": 0x26, "Down": 0x28, "Left": 0x25, "Right": 0x27,
            "Insert": 0x2D, "Delete": 0x2E, "Home": 0x24, "End": 0x23,
            "PageUp": 0x21, "PageDown": 0x22, "Enter": 0x0D})
VK_BY_NAME = dict(_VK)
NAME_BY_VK = {v: k for k, v in _VK.items()}

# Combos the game already uses for something else (laser/systems.py
# InputSystem).  The start menu refuses them as slot hotkeys.
RESERVED = {
    "F5": "reload characters", "F6": "clash FX preview", "F7": "add figure",
    "F8": "remove figure", "F9": "figures on / off", "Ctrl+0": "roster lock",
    "Ctrl+Q": "follow path", "Ctrl+R": "runaway", "Alt+Up": "attack mode",
    "Alt+Left": "cycle behaviour", "Alt+Right": "cycle behaviour",
    "Ctrl+Shift+.": "start menu", "Ctrl+Alt+Enter": "quit",
}


def combo_name(vk, ctrl=False, shift=False, alt=False):
    """'Ctrl+Shift+1' style name for a key + modifiers, or '' when the key
    can't be bound."""
    key = NAME_BY_VK.get(vk)
    if not key:
        return ""
    return "".join(("Ctrl+" if ctrl else "", "Shift+" if shift else "",
                    "Alt+" if alt else "")) + key


def parse_combo(text):
    """'Ctrl+Shift+1' -> (ctrl, shift, alt, vk); None when empty / unknown."""
    text = str(text or "").strip()
    if not text:
        return None
    ctrl = shift = alt = False
    # The key itself may be '+'-free punctuation; modifiers lead.
    rest = text
    while True:
        low = rest.lower()
        if low.startswith("ctrl+") and len(rest) > 5:
            ctrl, rest = True, rest[5:]
        elif low.startswith("shift+") and len(rest) > 6:
            shift, rest = True, rest[6:]
        elif low.startswith("alt+") and len(rest) > 4:
            alt, rest = True, rest[4:]
        else:
            break
    vk = VK_BY_NAME.get(rest)
    if vk is None:
        vk = VK_BY_NAME.get(rest.upper())
    if vk is None:
        return None
    return (ctrl, shift, alt, vk)


def normalize_combo(text):
    c = parse_combo(text)
    return combo_name(c[3], c[0], c[1], c[2]) if c else ""


def default_keys(i):
    n = str(i + 1)
    return {"cycle": n, "ultimate": "Ctrl+" + n, "special": "Ctrl+Shift+" + n,
            "tag": "Alt+" + n}


class Slot:
    """One start-menu slot.  `fig` is the live Figure while the slot is
    filled (on the field or on the tag bench), else None."""

    __slots__ = ("index", "char", "team", "link", "keys", "pick", "fig")

    def __init__(self, index, char=None, team=0, link=None, keys=None, pick=0):
        self.index = index
        self.char = char or None
        self.team = 1 if int(team or 0) == 1 else 0
        self.link = int(link) if link is not None and 0 <= int(link) < SLOT_COUNT and int(link) != index else None
        k = default_keys(index)
        for a in KEY_ACTIONS:
            if keys and a in keys:
                k[a] = normalize_combo(keys[a])
        self.keys = k
        self.pick = int(pick or 0)
        self.fig = None

    @property
    def name(self):
        return SLOT_NAMES[self.index]

    @property
    def tag(self):
        """Set to Tag (linked to a partner slot)."""
        return self.link is not None

    def to_dict(self):
        return {"char": self.char, "team": self.team, "link": self.link,
                "keys": dict(self.keys), "pick": self.pick}

    def copy(self):
        s = Slot(self.index, self.char, self.team, self.link, self.keys, self.pick)
        s.fig = self.fig
        return s


def default_slots(order):
    """Today's start-up: P1 (Team 1) fields the first character, the other
    slots are empty — slot A/C on Team 1, B/D on Team 2 (keys 1-4)."""
    slots = [Slot(i, team=i % 2) for i in range(SLOT_COUNT)]
    if order:
        slots[0].char = order[0]
        slots[0].pick = 1
    return slots


def path_for(root):
    return os.path.join(root, FILE_NAME)


def load(root, order):
    """The saved roster (roster.json in the game folder), dropping
    characters that are no longer registered; the default when missing."""
    try:
        with open(path_for(root), "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        raw = data.get("slots") or []
    except (OSError, ValueError, AttributeError):
        return default_slots(order)
    slots = []
    for i in range(SLOT_COUNT):
        d = raw[i] if i < len(raw) and isinstance(raw[i], dict) else {}
        ch = d.get("char")
        if ch not in order:
            ch = None
        slots.append(Slot(i, ch, d.get("team", i % 2), d.get("link"), d.get("keys"),
                          d.get("pick") if ch else 0))
    # Older roster.json: "tag": true on two team-mates = linked.
    if not any("link" in (d or {}) for d in raw if isinstance(d, dict)):
        for t in range(TEAM_COUNT):
            ts = [s for s in slots if s.char and s.team == t
                  and (raw[s.index] if s.index < len(raw) else {}).get("tag")]
            if len(ts) == 2:
                ts[0].link, ts[1].link = ts[1].index, ts[0].index
    if not any(s.char for s in slots):
        return default_slots(order)
    renumber(slots)
    clean_links(slots)
    return slots


def save(root, slots):
    try:
        with open(path_for(root), "w", encoding="utf-8") as f:
            json.dump({"slots": [s.to_dict() for s in slots]}, f, indent=2)
        return True
    except OSError:
        return False


def renumber(slots):
    """Keep picks 1..n in selection order (empty slots = 0)."""
    filled = sorted((s for s in slots if s.char), key=lambda s: (s.pick or 99, s.index))
    for s in slots:
        if not s.char:
            s.pick = 0
    for n, s in enumerate(filled, 1):
        s.pick = n


def next_pick(slots):
    return 1 + max([s.pick for s in slots if s.char] or [0])


def team_slots(slots, team):
    """The filled slots on `team`, in selection order."""
    return sorted((s for s in slots if s.char and s.team == team),
                  key=lambda s: (s.pick, s.index))


def unlink(slots, s):
    """Break s's tag link (its partner goes back to Single too)."""
    if s.link is not None:
        o = slots[s.link]
        if o.link == s.index:
            o.link = None
        s.link = None


def link(slots, a, b):
    """Link slots a and b as a tag pair (each loses any older link)."""
    unlink(slots, a)
    unlink(slots, b)
    a.link, b.link = b.index, a.index


def clean_links(slots, can_tag=None):
    """Drop links that no longer hold: an empty slot, team-mates no more,
    a one-sided link, or (with can_tag) a character that can't tag."""
    for s in slots:
        if s.link is None:
            continue
        o = slots[s.link]
        if (not s.char or not o.char or o.link != s.index or o.team != s.team
                or (can_tag is not None and not (can_tag(s.char) and can_tag(o.char)))):
            unlink(slots, s)


def tag_pairs(slots, can_tag):
    """Every valid linked pair as (first pick, second pick), in pair order
    (by the earlier pick).  Index in this list = the pair's colour."""
    out = []
    for s in sorted((x for x in slots if x.char), key=lambda x: (x.pick, x.index)):
        if s.link is None or any(s in p for p in out):
            continue
        o = slots[s.link]
        if (o.char and o.link == s.index and o.team == s.team
                and can_tag(s.char) and can_tag(o.char)):
            out.append((s, o) if (s.pick, s.index) <= (o.pick, o.index) else (o, s))
    return out


def pair_index(slots, s, can_tag):
    for n, p in enumerate(tag_pairs(slots, can_tag)):
        if s in p:
            return n
    return -1


def validate(slots, can_tag):
    """Problems that stop the start menu's Start button (empty = OK)."""
    errs = []
    if not any(s.char for s in slots):
        errs.append("Pick at least one character.")
    for t in range(TEAM_COUNT):
        n = len(team_slots(slots, t))
        if n > TEAM_SIZE:
            errs.append("Team %d has %d fighters (at most %d)." % (t + 1, n, TEAM_SIZE))
    for s in slots:
        if s.char and s.tag and not can_tag(s.char):
            errs.append("Slot %s: only Rig Forge characters can be set to Tag." % s.name)
        elif s.tag and s.char and slots[s.link].team != s.team:
            errs.append("Slot %s and its Tag partner %s are on different teams."
                        % (s.name, slots[s.link].name))
    seen = {}
    for s in slots:
        for a in KEY_ACTIONS:
            k = s.keys.get(a) or ""
            if not k:
                continue
            if k in RESERVED:
                errs.append("Slot %s %s: %s is already used for %s."
                            % (s.name, KEY_LABELS[a], k, RESERVED[k]))
            elif k in seen:
                errs.append("%s is set twice (slot %s %s and slot %s %s)."
                            % (k, seen[k][0], KEY_LABELS[seen[k][1]], s.name, KEY_LABELS[a]))
            else:
                seen[k] = (s.name, a)
    return errs


def bindings(slots):
    """{vk: [(ctrl, shift, alt, slot_index, action), ...]} for InputSystem."""
    out = {}
    for s in slots:
        for a in KEY_ACTIONS:
            c = parse_combo(s.keys.get(a))
            if c is None:
                continue
            out.setdefault(c[3], []).append((c[0], c[1], c[2], s.index, a))
    return out
