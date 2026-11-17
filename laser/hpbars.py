"""
Team HUD — Character Cards with a Ready Gate (Daniel 2026-11-12, design
"02 Character Cards" + "E Ready Gate"; bare + half size, side by side along
the bottom, Daniel 2026-11-17).  Solo and Battle alike: Solo shows Team 1
only (Team 2 empty), Battle both — same code.

One card per roster slot that has a fighter, laid out SIDE BY SIDE along
the bottom edge, evenly spaced (GAP): Team 1 from the bottom-left corner
rightward, Team 2 from the bottom-right corner leftward, in selection order
(roster.Slot.pick: the first pick sits nearest its corner).  A team whose
row would run past its half of the screen (both teams fielded) or the full
width (one team) wraps into another row above.  Cards are BARE: no panel,
no border — only what they show, with text shadows for readability.  Each
card is half its old footprint (CARD_W x TOP_H + GATE_H); fonts / icons
shrink less (~70%) so they stay legible.  A card shows:

  * the fighter's portrait (its first idle frame, cropped to head and
    shoulders, cached per character) inside an HP ring; a lighter "recent
    damage" arc trails the HP; the portrait flashes white on a hit
  * slot letter badge, name, a big HP number / max, a slim HP bar
  * the Ready Gate (fielded image characters only, laser/actionbar.py):
    one icon per attack-chain action (N1 N2 .. / S1 S2 .. / ULT ..) plus
    TAG for a tag pair.  A cooling icon slides along a faint timeline
    toward the gate end by its seconds left (1 / 3 / 6 / 12 s ticks); a
    ready one waits (glowing) at the gate end.  Hover shows its name, a
    click fires it (laser/hudclick.py; ready only, a cooling one shakes).

A benched tag partner is a short card (BENCH, cooldowns frozen); a fallen
fighter's card is greyed with a K.O. stamp.  A tag pair / trio's cards are
joined UNDER the row by a bracket in the group colour.  The corner note
(TAG / TRIO / NO FX FILE) sits just above the card.  Drawn in normal frames
and on the start-menu pause screen (buttons are not clickable there).

Cached (Daniel 2026-11-14, big-ball fps; the HUD cost ~7 ms a frame): each
card's still parts (portrait, HP ring, texts, K.O. stamp, the Ready Gate's
timeline / ticks) are painted once into a pixmap and only repainted when
something they show changes (_card_sig: HP, trailing arc, hit flash,
status, layout, ready count ...).  Each icon's face (box + label) is a
cached pixmap too; what moves or pulses (icon positions, ult glow, ready
ping, press / deny flash, hover ring, tag brackets, tooltip) is still drawn
live every frame.
"""

import glob
import math
import os
import time

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QColor, QFont, QPen, QPainter, QPainterPath, QImage, QPixmap, QRadialGradient

from . import actionbar
from . import roster as _roster
from . import tag as _tag

MARGIN_X = 24
MARGIN_B = 48             # above the taskbar (old readout's margin)
CARD_W = 172              # half the old 340 (+ room for 8 Ready Gate icons)
TOP_H = 48                # portrait / name / HP part
GATE_H = 24               # Ready Gate row
ROW_H = TOP_H + GATE_H    # every card's slot in the row (tops aligned)
BENCH_H = 28
GAP = 18                  # even spacing between cards in a row
ROW_GAP = 22              # between wrapped rows (room for the corner note)
MID_GAP = 48              # kept free between Team 1's and Team 2's halves
PORTRAIT_R = 19
ICON = 18
ICON_STEP = 20            # icon + spacing in the gate
GATE_MIN_W = 44
SPAN_S = 12.0             # timeline reaches this many seconds
TICKS_S = (1, 3, 6, 12)
LAG_STEP = 0.006          # recent-damage catch-up per frame (fraction of max)
HIT_FLASH_S = 0.14
PRESS_S = 0.28
PING_S = 0.5

DANGER = (255, 70, 60)
GROUP_COL = {"normal": (214, 222, 236), "ult": (255, 204, 64)}
WARN_COL = (255, 200, 90)

_fonts = {}
_lag = {}                 # id(fig) -> displayed fraction of the trailing strip
_prev_hp = {}             # id(fig) -> last frame's HP
_hit_t = {}               # id(fig) -> perf_counter time of its last HP drop
_ready_t = {}             # icon key -> time it became ready (ping)
_was_ready = {}           # icon key -> ready last frame
_portraits = {}           # (mode key, size) -> QPixmap | None
_card_cache = {}          # (team, slot index) -> (signature, QPixmap, x, y)
_icon_cache = {}          # (label, colour, state, dpr, sub-px x, y) -> QPixmap
CACHE_PAD_X = 10          # px round a card's pixmap (hit shake, text shadow)
CACHE_PAD_TOP = 14        # the corner note sits above the card
CACHE_PAD_BOTTOM = 6
ICON_PAD = 2


def _font(key):
    f = _fonts.get(key)
    if f is None:
        spec = {
            "name":  ("Bahnschrift", 12, QFont.DemiBold),
            "hp":    ("Bahnschrift", 22, QFont.Bold),
            "max":   ("Consolas", 9, QFont.Bold),
            "badge": ("Bahnschrift", 10, QFont.Bold),
            "small": ("Consolas", 9, QFont.Bold),
            "icon":  ("Bahnschrift", 8, QFont.Bold),
            "stamp": ("Bahnschrift", 24, QFont.Bold),
            "bname": ("Bahnschrift", 11, QFont.DemiBold),
        }[key]
        f = QFont(spec[0])
        f.setPixelSize(spec[1])
        f.setWeight(spec[2])
        _fonts[key] = f
    return f


def _q(rgb, a=255):
    return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(max(0, min(255, a))))


def _lift(rgb, k):
    r, g, b = rgb
    return (int(r + (255 - r) * k), int(g + (255 - g) * k), int(b + (255 - b) * k))


def _dark(rgb, k):
    return tuple(int(v * (1 - k)) for v in rgb)


def _name(fig):
    ch = getattr(fig.mode, "character", None) or {}
    return str(ch.get("display_name") or fig.mode.key).replace("_", " ").upper()


def _text(p, s, x, y, key, col, right=False, centre=False, shadow=True):
    p.setFont(_font(key))
    w = p.fontMetrics().horizontalAdvance(s)
    tx = x - w if right else (x - w / 2.0 if centre else x)
    if shadow:
        p.setPen(QColor(0, 0, 0, 170))
        p.drawText(QPointF(tx + 1, y + 1), s)
    p.setPen(col)
    p.drawText(QPointF(tx, y), s)
    return w


def _source_frame(world, fig):
    """The character's first idle (else run) frame at full resolution: the
    PNG in its own folder (characters/<name>/idle_01.png) when it has one,
    else the in-game frame (already scaled down to game size)."""
    pk = (getattr(fig.mode, "character", None) or {}).get("_package") or {}
    base = getattr(getattr(world, "assets", None), "dir", None)
    if pk.get("dir") and base:
        folder = os.path.join(base, pk["dir"])
        for pat in ("idle_*.png", "run_*.png"):
            files = sorted(glob.glob(os.path.join(folder, pat)))
            if files:
                img = QImage(files[0])
                if not img.isNull():
                    return img
    b = fig.render.bundle
    frames = list(getattr(b, "idle", None) or []) or list(getattr(b, "run", None) or [])
    if frames and not frames[0].isNull():
        return frames[0].toImage()
    return None


def _portrait(world, fig, size):
    """The fighter's upper body (top ~70% of its first idle frame's opaque
    area), size x size, cached per character; None when it has no frame."""
    key = (getattr(fig.mode, "key", None), size)
    if key in _portraits:
        return _portraits[key]
    out = None
    try:
        img = _source_frame(world, fig)
        if img is not None:
            img = img.convertToFormat(QImage.Format_ARGB32)
            w, h = img.width(), img.height()
            step = max(1, min(w, h) // 160)
            x0, y0, x1, y1 = w, h, -1, -1
            for yy in range(0, h, step):
                for xx in range(0, w, step):
                    if (img.pixel(xx, yy) >> 24) > 60:
                        if xx < x0: x0 = xx
                        if xx > x1: x1 = xx
                        if yy < y0: y0 = yy
                        if yy > y1: y1 = yy
            if x1 >= x0 and y1 >= y0:
                bw, bh = x1 - x0 + 1, y1 - y0 + 1
                side = max(8, int(max(bw, bh * 0.72) * 1.08))
                cx = (x0 + x1) // 2
                top = y0 - int(side * 0.06)
                crop = img.copy(cx - side // 2, top, side, side)
                out = QPixmap.fromImage(crop).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    except Exception:
        out = None
    _portraits[key] = out
    return out


def _card_h(status, has_gate):
    if status == "bench":
        return BENCH_H
    if status == "ko" or not has_gate:
        return TOP_H
    return TOP_H + GATE_H


def draw(p, world):
    slots = getattr(world, "slots", None) or []
    pairs = list(getattr(world, "tag_pairs", None) or [])
    clickable = not (world.prebattle.open or getattr(world, "stats_open", False))
    world.hud_buttons = []
    now = time.perf_counter()
    live = set()
    teams = [[s for s in _roster.team_slots(slots, t) if s.fig is not None]
             for t in range(_roster.TEAM_COUNT)]
    shown = sum(1 for r in teams if r)
    avail = world.screen_w - 2 * MARGIN_X
    if shown > 1:
        avail = (avail - MID_GAP) / float(shown)
    per = max(1, int((avail + GAP) // (CARD_W + GAP)))
    p.save()
    p.setRenderHint(p.Antialiasing, True)
    for team, rows in enumerate(teams):
        if not rows:
            continue
        right = team == 1
        boxes = {}
        for i, s in enumerate(rows):
            col, line = i % per, i // per
            off = col * (CARD_W + GAP)
            x0 = world.screen_w - MARGIN_X - CARD_W - off if right else MARGIN_X + off
            y = world.screen_h - MARGIN_B - ROW_H - line * (ROW_H + ROW_GAP)
            status = _tag.status(world, s)
            ents = actionbar.entries(world, s, status) if status == "on" else []
            h = _card_h(status, bool(ents))
            boxes[s.index] = (x0, y, h)
            live.add(id(s.fig))
            _card(p, world, s, x0, y, h, right, status, ents, clickable, now, team)
        for k, pr in enumerate(pairs):
            if pr is None or pr.team != team:
                continue
            bs = [boxes[m.index] for m in pr.members if m.index in boxes]
            if len(bs) >= 2:
                col = _roster.PAIR_COLORS[k % len(_roster.PAIR_COLORS)]
                _link(p, bs, col, k)
    _tooltip(p, world)
    p.restore()
    for d in (_lag, _prev_hp, _hit_t):
        for k in list(d.keys()):
            if k not in live:
                del d[k]
    keep = {(s.team, s.index) for s in slots if getattr(s, "fig", None) is not None}
    for k in list(_card_cache.keys()):
        if k not in keep:
            del _card_cache[k]
    if len(_icon_cache) > 1024:
        _icon_cache.clear()


def _dpr(p):
    try:
        return float(p.device().devicePixelRatioF()) or 1.0
    except Exception:
        return 1.0


def _cached(p, key, sig, x, y, w, h, paint):
    """Blit the pixmap cached under key when its signature still matches;
    else paint(painter) it afresh (painter origin = screen (x, y)) first.
    x, y are whole px so the blit lands exactly where a direct draw would."""
    dpr = _dpr(p)
    ent = _card_cache.get(key)
    if ent is None or ent[0] != sig or ent[2] != x or ent[3] != y or ent[1].devicePixelRatioF() != dpr:
        pm = QPixmap(max(1, int(math.ceil(w * dpr))), max(1, int(math.ceil(h * dpr))))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing, True)
        q.setRenderHint(QPainter.SmoothPixmapTransform, True)
        q.translate(-x, -y)
        try:
            paint(q)
        finally:
            q.end()
        ent = _card_cache[key] = (sig, pm, x, y)
    p.drawPixmap(QPointF(x, y), ent[1])


def _card(p, world, s, x0, y, h, right, status, ents, clickable, now, team=0):
    fig = s.fig
    hp, mx = float(fig.personality.hp), float(max(1, fig.personality.max_hp))
    frac = max(0.0, min(1.0, hp / mx))
    lag = _lag.get(id(fig), frac)
    lag = frac if lag < frac else max(frac, lag - LAG_STEP)
    _lag[id(fig)] = lag
    prev = _prev_hp.get(id(fig))
    if prev is not None and hp < prev - 1e-6:
        _hit_t[id(fig)] = now
    _prev_hp[id(fig)] = hp
    hit = max(0.0, 1.0 - (now - _hit_t.get(id(fig), -9.0)) / HIT_FLASH_S)
    shake = 0.0 if hit <= 0 else math.sin(now * 90.0) * 2.0 * hit

    # Still parts from the cache (repainted only when what they show
    # changes); the Ready Gate's icons are drawn live on top.
    ko, bench = status == "ko", status == "bench"
    ch = getattr(fig.mode, "character", None) or {}
    note = None
    if ch.get("_package") and not ch.get("_fxkit"):
        note = ("NO FX FILE", WARN_COL)
    elif _tag.partner_of(world, s) is not None and not ko:
        grp = _tag.group_of(world, s)
        note = ("TRIO" if grp is not None and grp.trio else "TAG", actionbar.pair_color(world, s))
    n_ready = sum(1 for e in ents if e.state == "ready")
    sig = (status, h, right, int(round(hp)), int(round(mx)), round(frac, 4), round(lag, 4),
           round(hit, 3), round(shake, 2), tuple(fig.lut[128]), note, s.pick, s.name, _name(fig),
           id(_portrait(world, fig, int((PORTRAIT_R - 7) * 2))), bool(ents), n_ready)
    cx0, cy0 = int(math.floor(x0)) - CACHE_PAD_X, int(math.floor(y)) - CACHE_PAD_TOP
    cw, chh = CARD_W + 2 * CACHE_PAD_X + 1, h + CACHE_PAD_TOP + CACHE_PAD_BOTTOM + 1
    _cached(p, (team, s.index), sig, cx0, cy0, cw, chh,
            lambda q: _card_still(q, world, s, fig, x0, y, h, right, status, ents,
                                  hp, mx, frac, lag, hit, shake, note))
    if ents and not ko and not bench:
        base = tuple(fig.lut[128])
        X = (lambda d: x0 + CARD_W - d) if right else (lambda d: x0 + d)
        _gate(p, world, s, X, shake, y + TOP_H, right, base, ents, clickable, now, still=False)
    if bench and _tag.group_of(world, s) is not None:
        _bench_click(p, world, s, x0, y, h, right, clickable, now)


def _card_still(p, world, s, fig, x0, y, h, right, status, ents, hp, mx, frac, lag, hit, shake, note):
    """Everything on a card that does not move frame to frame (cached).
    Bare: no panel / border (Daniel 2026-11-17), only what the card shows."""

    ko, bench = status == "ko", status == "bench"
    base = tuple(fig.lut[128])
    col = _lift(base, 0.25)
    fill = DANGER if (frac < 0.25 and status == "on") else col
    grey = (120, 124, 132)
    accent = grey if ko else col
    X = (lambda d: x0 + CARD_W - d) if right else (lambda d: x0 + d)

    if bench:
        _bench_body(p, world, fig, s, X, shake, y, right, base, frac)
        return

    # Portrait in its HP ring.
    R = PORTRAIT_R
    cx, cy = X(R + 3) + shake, y + 4 + R
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(8, 10, 15, 200))
    p.drawEllipse(QPointF(cx, cy), R, R)
    inner = R - 4
    clip = QPainterPath()
    clip.addEllipse(QPointF(cx, cy), inner, inner)
    p.save()
    p.setClipPath(clip)
    # Mid-tone backdrop in the fighter's colour: dark-ink sprites and
    # light ones (white hoods, pale robes) both stand out against it.
    bg = QRadialGradient(QPointF(cx, cy - 3), R)
    tint = grey if ko else base
    bg.setColorAt(0.0, _q(_lift(_dark(tint, 0.15), 0.3)))
    bg.setColorAt(1.0, _q(_dark(tint, 0.45)))
    p.fillRect(QRectF(cx - R, cy - R, 2 * R, 2 * R), bg)
    pm = _portrait(world, fig, int(inner * 2))
    if pm is not None:
        if ko:
            p.setOpacity(0.35)
        p.drawPixmap(QPointF(cx - pm.width() / 2.0, cy - pm.height() / 2.0), pm)
        p.setOpacity(1.0)
    else:
        _text(p, s.name, cx, cy + 6, "name", _q(_lift(base, 0.5)), centre=True)
    if hit > 0:
        p.fillRect(QRectF(cx - R, cy - R, 2 * R, 2 * R), QColor(255, 255, 255, int(200 * hit)))
    p.restore()
    ring = QRectF(cx - (R - 2), cy - (R - 2), 2 * (R - 2), 2 * (R - 2))
    pen = QPen(QColor(255, 255, 255, 40))
    pen.setWidthF(3.5)
    pen.setCapStyle(Qt.FlatCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(ring)
    if lag > frac and not ko:
        pen.setColor(QColor(255, 255, 255, 215))
        p.setPen(pen)
        p.drawArc(ring, int((90 - 360 * frac) * 16), int(-360 * (lag - frac) * 16))
    if frac > 0:
        pen.setColor(_q(fill))
        p.setPen(pen)
        p.drawArc(ring, 90 * 16, int(-360 * frac * 16))
    # Slot letter badge.
    bx, by = cx + (-14 if right else 14), cy + 14
    p.setPen(QPen(_q(accent), 1.5))
    p.setBrush(QColor(8, 10, 15, 235))
    p.drawEllipse(QPointF(bx, by), 7, 7)
    _text(p, s.name, bx, by + 4, "badge", QColor(255, 255, 255), centre=True, shadow=False)

    # Name, HP number, bar.
    tx = X(2 * R + 10) + shake
    _text(p, "%d  %s" % (s.pick, _name(fig)), tx, y + 14, "name",
          QColor(130, 134, 142) if ko else QColor(255, 255, 255), right=right)
    hp_s = str(int(round(hp)))
    w = _text(p, hp_s, tx, y + 36, "hp", QColor(130, 134, 142) if ko else _q(_lift(fill, 0.35)), right=right)
    mx_s = "/%d" % int(round(mx))
    _text(p, mx_s, tx - w - 3 if right else tx + w + 3, y + 36, "max", QColor(255, 255, 255, 150), right=right)
    bw = CARD_W - (2 * R + 10) - 6
    bx0 = tx - bw if right else tx
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 110))
    p.drawRoundedRect(QRectF(bx0 - 1, y + 40, bw + 2, 5), 2.5, 2.5)
    p.setBrush(QColor(255, 255, 255, 45))
    p.drawRoundedRect(QRectF(bx0, y + 41, bw, 3), 1.5, 1.5)
    if lag > frac:
        p.setBrush(QColor(255, 255, 255, 150))
        p.drawRoundedRect(QRectF(tx - bw * lag if right else tx, y + 41, bw * lag, 3), 1.5, 1.5)
    if frac > 0:
        p.setBrush(_q(fill))
        p.drawRoundedRect(QRectF(tx - bw * frac if right else tx, y + 41, bw * frac, 3), 1.5, 1.5)

    # Corner note (tag pair / trio / missing FX file): just above the card.
    if note:
        _text(p, note[0], X(4), y - 3, "small", _q(note[1], 235), right=right)

    if ko:
        p.save()
        p.translate(x0 + CARD_W / 2.0 + 14 * (-1 if right else 1), y + h / 2.0 + 2)
        p.rotate(-10)
        p.setPen(QPen(QColor(255, 70, 60, 235), 2.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(-36, -17, 72, 33), 4, 4)
        _text(p, "K.O.", 0, 9, "stamp", QColor(255, 70, 60, 240), centre=True)
        p.restore()
        return

    if ents:
        _gate(p, world, s, X, shake, y + TOP_H, right, base, ents, False, 0.0, still=True)


def _bench_click(p, world, s, x0, y, h, right, clickable, now):
    """A benched tag pair / trio member's card is a button (Daniel
    2026-11-17): click = Tag that fighter in (actionbar.fire "tag_in").
    Hover ring, hint and press flash are live (not in the card cache)."""
    key = (s.index, "tag_in")
    r = QRectF(x0, y, CARD_W, h)
    fx = world.hud_fx.get(key) if hasattr(world, "hud_fx") else None
    if fx is not None:
        k = 1.0 - (now - fx[0]) / PRESS_S
        if k > 0:
            col = QColor(255, 70, 60, int(255 * k)) if fx[1] == "deny" else QColor(255, 255, 255, int(200 * k))
            p.setPen(QPen(col, 2.0))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 4, 4)
        else:
            world.hud_fx.pop(key, None)
    if getattr(world, "hud_hover", None) == key:
        p.setPen(QPen(QColor(255, 255, 255), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        _text(p, "CLICK: TAG IN", (x0 + CARD_W - 4) if right else (x0 + 4), y - 4, "small",
              QColor(255, 255, 255, 230), right=right)
    if clickable and s.fig is not None and s.fig.personality.hp > 0:
        world.hud_buttons.append((r, key))


def _bench_body(p, world, fig, s, X, dx, y, right, base, frac):
    """Benched tag partner: a short card (portrait, name, HP, frozen note)."""
    a = 170
    cx, cy = X(13) + dx, y + BENCH_H / 2.0
    p.setPen(Qt.NoPen)
    p.setBrush(_q(_lift(base, 0.6), 150))
    p.drawEllipse(QPointF(cx, cy), 10, 10)
    pm = _portrait(world, fig, 16)
    if pm is not None:
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), 8.5, 8.5)
        p.save()
        p.setClipPath(clip)
        p.setOpacity(0.55)
        p.drawPixmap(QPointF(cx - pm.width() / 2.0, cy - pm.height() / 2.0), pm)
        p.restore()
    tx = X(29) + dx
    _text(p, "%s  %s" % (s.name, _name(fig)), tx, y + 12, "bname", QColor(255, 255, 255, a), right=right)
    _text(p, "BENCH · FROZEN", tx, y + 24, "small", QColor(170, 215, 255, 200), right=right)
    hp_s = str(int(round(fig.personality.hp)))
    _text(p, "%s/%d" % (hp_s, int(round(fig.personality.max_hp))), X(CARD_W - 4) + dx, y + 24, "max",
          QColor(255, 255, 255, a), right=not right)


def _gate_col(e, base):
    if e.group == "special":
        return _lift(base, 0.25)
    if e.group == "tag":
        return None
    return GROUP_COL.get(e.group, (214, 222, 236))


def _gate(p, world, s, X, dx, y, right, base, ents, clickable, now, still=True):
    """The Ready Gate row: gate at the screen-edge side, timeline inward.
    Bare: no strip / gate box, only a faint timeline with its second ticks.
    still=True paints the timeline (cached with the card), still=False only
    the icons (live)."""
    pad = 2
    y0 = y + 2
    hh = GATE_H - 4
    ready = [e for e in ents if e.state == "ready"]
    cooling = [e for e in ents if e.state != "ready"]
    gw = max(GATE_MIN_W, 4 + len(ready) * ICON_STEP)
    full = CARD_W - 2 * pad
    tw = full - gw
    left_x = (X(CARD_W - pad) if right else X(pad)) + dx     # strip's left edge
    if right:
        gx, tx0, d = left_x + tw, left_x + tw, -1             # gate on the right
    else:
        gx, tx0, d = left_x, left_x + gw, 1

    def pos(sec):
        return tx0 + d * (6 + (tw - 14) * math.sqrt(max(0.0, min(sec, SPAN_S)) / SPAN_S))

    if not still:
        iy = y0 + (hh - ICON) / 2.0
        # Cooling icons: farthest first so the nearest-to-ready sits on top.
        for e in sorted(cooling, key=lambda e: -e.left_ms):
            if e.state == "blocked":
                ix = tx0 + d * (tw - 4) - (ICON if d > 0 else 0)
            else:
                ix = pos(e.left_ms / 1000.0) - ICON / 2.0
            _icon(p, world, s, e, ix, iy, base, clickable, now)
        for i, e in enumerate(ready):
            ix = (gx + gw - 2 - ICON - i * ICON_STEP) if right else (gx + 2 + i * ICON_STEP)
            _icon(p, world, s, e, ix, iy, base, clickable, now)
        return
    if tw < 24:                          # every icon ready: no timeline left
        return
    # Faint timeline + its second ticks (dark under-stroke so it reads on
    # light backgrounds too).
    ym = y0 + hh / 2.0
    a, b = QPointF(tx0 + d * 4, ym), QPointF(tx0 + d * (tw - 6), ym)
    p.setPen(QPen(QColor(0, 0, 0, 70), 2.5))
    p.drawLine(a, b)
    p.setPen(QPen(QColor(255, 255, 255, 60), 1.0))
    p.drawLine(a, b)
    for t in TICKS_S:
        xx = pos(t)
        p.setPen(QPen(QColor(255, 255, 255, 80), 1.0))
        p.drawLine(QPointF(xx, ym - 3), QPointF(xx, ym + 3))


def _icon(p, world, s, e, x, y, base, clickable, now):
    key = e.key
    col = _gate_col(e, base) or actionbar.pair_color(world, s)
    fx = world.hud_fx.get(key) if hasattr(world, "hud_fx") else None
    deny = ok = 0.0
    if fx is not None:
        k = 1.0 - (now - fx[0]) / PRESS_S
        if k > 0:
            if fx[1] == "deny":
                deny = k
            else:
                ok = k
        else:
            world.hud_fx.pop(key, None)
    x += math.sin(now * 80.0) * 3.0 * deny
    ready = e.state == "ready"
    if ready and not _was_ready.get(key):
        _ready_t[key] = now
    _was_ready[key] = ready
    r = QRectF(x, y, ICON, ICON)
    if ready:
        glow = 0.5 + 0.5 * math.sin(now * 6.0) if e.group == "ult" else 0.6
        p.setPen(Qt.NoPen)
        p.setBrush(_q(col, int(70 * glow)))
        p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 5, 5)
        _icon_face(p, e.label, col, "ready", x, y)
        pk = (now - _ready_t.get(key, -9.0)) / PING_S
        if 0 <= pk < 1:
            g = 2 + pk * 8
            p.setPen(QPen(QColor(255, 255, 255, int(200 * (1 - pk))), 2.0))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(-g, -g, g, g), 4 + g, 4 + g)
    else:
        _icon_face(p, e.label, col, "blocked" if e.state == "blocked" else "cool", x, y)
    if ok > 0:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, int(220 * ok)))
        p.drawRoundedRect(r, 5, 5)
    if deny > 0:
        p.setPen(QPen(QColor(255, 70, 60, int(255 * deny)), 2.5))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 5, 5)
    if getattr(world, "hud_hover", None) == key:
        p.setPen(QPen(QColor(255, 255, 255), 2.0))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), 6, 6)
        world._hud_tip = (r, s, e, col)
    if clickable and e.state != "frozen":
        world.hud_buttons.append((r, key))


def _icon_face(p, label, col, state, x, y):
    """An icon's box + label at (x, y), from a cached pixmap.  Faces are
    cached per quarter-px offset so a sliding icon moves as smoothly as a
    direct draw (blitted at whole px, never resampled)."""
    dpr = _dpr(p)
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = round((x - ix) * 4) / 4.0, round((y - iy) * 4) / 4.0
    if fx >= 1.0:
        ix, fx = ix + 1, 0.0
    if fy >= 1.0:
        iy, fy = iy + 1, 0.0
    key = (label, tuple(col), state, dpr, fx, fy)
    pm = _icon_cache.get(key)
    if pm is None:
        n = ICON + 2 * ICON_PAD + 1
        pm = QPixmap(int(math.ceil(n * dpr)), int(math.ceil(n * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        q = QPainter(pm)
        q.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(ICON_PAD + fx, ICON_PAD + fy, ICON, ICON)
        cx, cy = ICON_PAD + fx + ICON / 2.0, ICON_PAD + fy + ICON / 2.0 + 3
        if state == "ready":
            q.setPen(Qt.NoPen)
            q.setBrush(_q(col, 245))
            q.drawRoundedRect(r, 4, 4)
            _text(q, label, cx, cy, "icon", QColor(10, 13, 19), centre=True, shadow=False)
        else:
            blocked = state == "blocked"
            q.setBrush(QColor(14, 17, 24, 245))
            q.setPen(QPen(_q(col, 80 if blocked else 230), 1.4))
            q.drawRoundedRect(r, 4, 4)
            _text(q, label, cx, cy, "icon",
                  QColor(255, 255, 255, 80) if blocked else _q(_lift(col, 0.3)), centre=True, shadow=False)
        q.end()
        _icon_cache[key] = pm
    p.drawPixmap(QPointF(ix - ICON_PAD, iy - ICON_PAD), pm)


def _tooltip(p, world):
    tip = getattr(world, "_hud_tip", None)
    world._hud_tip = None
    if tip is None or getattr(world, "hud_hover", None) != tip[2].key:
        return
    r, s, e, col = tip
    l1 = "%s · %s" % (s.name, "tag switch" if e.name == "switch" else e.name)
    l2 = {"ready": "READY · click to fire", "cool": "ready in %.1f s" % (e.left_ms / 1000.0),
          "blocked": "partner unavailable", "frozen": "benched · frozen"}.get(e.state, "")
    p.setFont(_font("small"))
    fm = p.fontMetrics()
    w = max(fm.horizontalAdvance(l1), fm.horizontalAdvance(l2)) + 18
    x = min(world.screen_w - w - 6, max(6, r.center().x() - w / 2.0))
    y = r.top() - 50
    box = QRectF(x, y, w, 42)
    p.setPen(QPen(_q(col, 210), 1.2))
    p.setBrush(QColor(4, 6, 10, 240))
    p.drawRoundedRect(box, 6, 6)
    _text(p, l1, x + 9, y + 17, "small", QColor(255, 255, 255), shadow=False)
    _text(p, l2, x + 9, y + 34, "small", QColor(88, 214, 141) if e.state == "ready" else QColor(255, 255, 255, 170), shadow=False)


def _link(p, boxes, col, k):
    """Tag-pair / trio bracket in the group's colour UNDER its cards (a
    second group on the team sits one step lower); a tick up to every
    member's card.  Members on different wrapped rows get one bracket per
    row."""
    pen = QPen(_q(col, 220))
    pen.setWidthF(2.0)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    rows = {}
    for x, y, h in boxes:
        rows.setdefault(y, []).append((x, y, h))
    for y, bs in rows.items():
        ly = y + ROW_H + 4 + 4 * (k % 2)
        xs = [x + CARD_W / 2.0 for x, _, _ in bs]
        if len(xs) >= 2:
            p.drawLine(QPointF(min(xs), ly), QPointF(max(xs), ly))
        for (x, by, h), xx in zip(bs, xs):
            p.drawLine(QPointF(xx, by + h + 2), QPointF(xx, ly))
