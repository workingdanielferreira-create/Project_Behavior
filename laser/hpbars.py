"""
Team HUD — Character Cards with a Ready Gate (Daniel 2026-11-12, design
"02 Character Cards" + "E Ready Gate").  Solo and Battle alike: Solo shows
Team 1 only (Team 2 empty), Battle both — same code.

One card per roster slot that has a fighter, stacked UP from its team's
bottom corner (Team 1 bottom-left, Team 2 bottom-right) in selection order
(roster.Slot.pick: the first pick sits lowest).  A card shows:

  * the fighter's portrait (its first idle frame, cropped to head and
    shoulders, cached per character) inside an HP ring; a lighter "recent
    damage" arc trails the HP; the portrait flashes white on a hit
  * slot letter badge, name, a big HP number / max, a slim HP bar
  * the Ready Gate (fielded image characters only, laser/actionbar.py):
    one icon per attack-chain action (N1 N2 .. / S1 S2 .. / ULT ..) plus
    TAG for a tag pair.  A cooling icon slides along a short timeline
    toward the gate by its seconds left (1 / 3 / 6 / 12 s marks); a ready
    one waits in the glowing gate.  Hover shows its name, a click fires it
    (laser/hudclick.py; ready only, a cooling one shakes).

A benched tag partner is a short card (BENCH, cooldowns frozen); a fallen
fighter's card is greyed with a K.O. stamp.  A tag pair's two cards are
joined on the screen-edge side by a bracket in the pair colour.  The old
bottom-right "P1 87 HP" readout is gone (its "(no FX file)" warning is on
the card).  Drawn in normal frames and on the start-menu pause screen
(buttons are not clickable there).
"""

import glob
import math
import os
import time

from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QColor, QFont, QPen, QPainterPath, QPolygonF, QImage, QPixmap, QRadialGradient

from . import actionbar
from . import roster as _roster
from . import tag as _tag

MARGIN_X = 24
MARGIN_B = 48             # above the taskbar (old readout's margin)
CARD_W = 340
TOP_H = 96                # portrait / name / HP part
GATE_H = 48               # Ready Gate row (timeline + its second marks)
BENCH_H = 50
GAP = 12
SLANT = 10                # card skew, px
PORTRAIT_R = 36
ICON = 24
GATE_MIN_W = 86
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


def _font(key):
    f = _fonts.get(key)
    if f is None:
        spec = {
            "name":  ("Bahnschrift", 17, QFont.DemiBold),
            "hp":    ("Bahnschrift", 34, QFont.Bold),
            "max":   ("Consolas", 12, QFont.Bold),
            "badge": ("Bahnschrift", 14, QFont.Bold),
            "small": ("Consolas", 11, QFont.Bold),
            "icon":  ("Bahnschrift", 10, QFont.Bold),
            "tick":  ("Consolas", 9, QFont.Normal),
            "stamp": ("Bahnschrift", 40, QFont.Bold),
            "bname": ("Bahnschrift", 14, QFont.DemiBold),
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
    p.save()
    p.setRenderHint(p.Antialiasing, True)
    for team in range(_roster.TEAM_COUNT):
        rows = [s for s in _roster.team_slots(slots, team) if s.fig is not None]
        if not rows:
            continue
        right = team == 1
        x0 = world.screen_w - MARGIN_X - CARD_W if right else MARGIN_X
        y_cur = world.screen_h - MARGIN_B
        boxes = {}
        for s in rows:
            status = _tag.status(world, s)
            ents = actionbar.entries(world, s, status) if status == "on" else []
            h = _card_h(status, bool(ents))
            y = y_cur - h
            y_cur = y - GAP
            boxes[s.index] = (y, h)
            live.add(id(s.fig))
            _card(p, world, s, x0, y, h, right, status, ents, clickable, now)
        for k, pr in enumerate(pairs):
            if pr is not None and pr.team == team and pr.on.index in boxes and pr.off.index in boxes:
                col = _roster.PAIR_COLORS[k % len(_roster.PAIR_COLORS)]
                _link(p, x0, boxes[pr.on.index], boxes[pr.off.index], right, col, k)
    _tooltip(p, world)
    p.restore()
    for d in (_lag, _prev_hp, _hit_t):
        for k in list(d.keys()):
            if k not in live:
                del d[k]


def _card(p, world, s, x0, y, h, right, status, ents, clickable, now):
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
    shake = 0.0 if hit <= 0 else math.sin(now * 90.0) * 4.0 * hit

    ko, bench = status == "ko", status == "bench"
    base = tuple(fig.lut[128])
    col = _lift(base, 0.25)
    fill = DANGER if (frac < 0.25 and status == "on") else col
    grey = (120, 124, 132)
    accent = grey if ko else col
    X = (lambda d: x0 + CARD_W - d) if right else (lambda d: x0 + d)
    xs = x0 + shake

    # Card body: a slanted glass panel with a colour edge on top.
    if right:
        pts = [QPointF(xs, y), QPointF(xs + CARD_W, y), QPointF(xs + CARD_W - SLANT, y + h), QPointF(xs - SLANT, y + h)]
    else:
        pts = [QPointF(xs + SLANT, y), QPointF(xs + CARD_W + SLANT, y), QPointF(xs + CARD_W, y + h), QPointF(xs, y + h)]
    path = QPainterPath()
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    a_body = 150 if bench else 225
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(14, 18, 26, a_body))
    p.drawPath(path)
    edge = QPen(_q(accent, 110 if bench else 200))
    edge.setWidthF(1.5)
    p.setPen(edge)
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    top = QPen(_q(accent, 150 if bench else 255))
    top.setWidthF(4.0)
    p.setPen(top)
    p.drawLine(pts[0], pts[1])

    if bench:
        _bench_body(p, world, fig, s, X, xs - x0, y, right, base, frac)
        return

    # Portrait in its HP ring.
    R = PORTRAIT_R
    cx, cy = X(58) + shake, y + 50
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(8, 10, 15, 240))
    p.drawEllipse(QPointF(cx, cy), R, R)
    inner = R - 7
    clip = QPainterPath()
    clip.addEllipse(QPointF(cx, cy), inner, inner)
    p.save()
    p.setClipPath(clip)
    # Mid-tone backdrop in the fighter's colour: dark-ink sprites and
    # light ones (white hoods, pale robes) both stand out against it.
    bg = QRadialGradient(QPointF(cx, cy - 6), R)
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
        _text(p, s.name, cx, cy + 10, "hp", _q(_lift(base, 0.5)), centre=True)
    if hit > 0:
        p.fillRect(QRectF(cx - R, cy - R, 2 * R, 2 * R), QColor(255, 255, 255, int(200 * hit)))
    p.restore()
    ring = QRectF(cx - (R - 3), cy - (R - 3), 2 * (R - 3), 2 * (R - 3))
    pen = QPen(QColor(255, 255, 255, 30))
    pen.setWidthF(6.0)
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
    bx, by = cx + (-25 if right else 25), cy + 27
    p.setPen(QPen(_q(accent), 2.0))
    p.setBrush(QColor(8, 10, 15, 245))
    p.drawEllipse(QPointF(bx, by), 12, 12)
    _text(p, s.name, bx, by + 5, "badge", QColor(255, 255, 255), centre=True, shadow=False)

    # Name, HP number, bar.
    tx = X(110) + shake
    _text(p, "%d  %s" % (s.pick, _name(fig)), tx, y + 28, "name",
          QColor(130, 134, 142) if ko else QColor(255, 255, 255), right=right)
    hp_s = str(int(round(hp)))
    w = _text(p, hp_s, tx, y + 66, "hp", QColor(130, 134, 142) if ko else _q(_lift(fill, 0.35)), right=right)
    mx_s = "/%d" % int(round(mx))
    _text(p, mx_s, tx - w - 5 if right else tx + w + 5, y + 66, "max", QColor(255, 255, 255, 120), right=right, shadow=False)
    bw = 170
    bx0 = tx - bw if right else tx
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(255, 255, 255, 30))
    p.drawRoundedRect(QRectF(bx0, y + 76, bw, 6), 3, 3)
    if lag > frac:
        p.setBrush(QColor(255, 255, 255, 150))
        p.drawRoundedRect(QRectF(tx - bw * lag if right else tx, y + 76, bw * lag, 6), 3, 3)
    if frac > 0:
        p.setBrush(_q(fill))
        p.drawRoundedRect(QRectF(tx - bw * frac if right else tx, y + 76, bw * frac, 6), 3, 3)

    # Corner note: tag pair / missing FX file.
    ch = getattr(fig.mode, "character", None) or {}
    note = None
    if ch.get("_package") and not ch.get("_fxkit"):
        note = ("NO FX FILE", WARN_COL)
    elif _tag.partner_of(world, s) is not None and not ko:
        note = ("TAG", actionbar.pair_color(world, s))
    if note:
        _text(p, note[0], X(CARD_W - 16), y + 24, "small", _q(note[1], 230), right=not right)

    if ko:
        p.save()
        p.translate(x0 + CARD_W / 2.0 + 30 * (-1 if right else 1), y + h / 2.0 + 4)
        p.rotate(-10)
        p.setPen(QPen(QColor(255, 70, 60, 235), 4.0))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(-62, -30, 124, 56), 6, 6)
        _text(p, "K.O.", 0, 15, "stamp", QColor(255, 70, 60, 240), centre=True, shadow=False)
        p.restore()
        return

    if ents:
        _gate(p, world, s, X, shake, y + TOP_H, right, base, ents, clickable, now)


def _bench_body(p, world, fig, s, X, dx, y, right, base, frac):
    """Benched tag partner: a short card (portrait, name, HP, frozen note)."""
    a = 150
    cx, cy = X(30) + dx, y + BENCH_H / 2.0
    p.setPen(Qt.NoPen)
    p.setBrush(_q(_lift(base, 0.6), 150))
    p.drawEllipse(QPointF(cx, cy), 17, 17)
    pm = _portrait(world, fig, 26)
    if pm is not None:
        clip = QPainterPath()
        clip.addEllipse(QPointF(cx, cy), 14, 14)
        p.save()
        p.setClipPath(clip)
        p.setOpacity(0.55)
        p.drawPixmap(QPointF(cx - pm.width() / 2.0, cy - pm.height() / 2.0), pm)
        p.restore()
    tx = X(58) + dx
    _text(p, "%s  %s" % (s.name, _name(fig)), tx, y + 21, "bname", QColor(255, 255, 255, a), right=right)
    _text(p, "BENCH  ·  COOLDOWNS FROZEN", tx, y + 39, "small", QColor(170, 215, 255, 190), right=right, shadow=False)
    hp_s = str(int(round(fig.personality.hp)))
    _text(p, "%s /%d" % (hp_s, int(round(fig.personality.max_hp))), X(CARD_W - 18) + dx, y + 30, "badge",
          QColor(255, 255, 255, a), right=not right)


def _gate_col(e, base):
    if e.group == "special":
        return _lift(base, 0.25)
    if e.group == "tag":
        return None
    return GROUP_COL.get(e.group, (214, 222, 236))


def _gate(p, world, s, X, dx, y, right, base, ents, clickable, now):
    """The Ready Gate row: gate at the screen-edge side, timeline inward."""
    pad = 14
    y0 = y + 4
    hh = GATE_H - 12
    ready = [e for e in ents if e.state == "ready"]
    cooling = [e for e in ents if e.state != "ready"]
    gw = max(GATE_MIN_W, 10 + len(ready) * (ICON + 4))
    full = CARD_W - 2 * pad
    tw = full - gw
    left_x = (X(CARD_W - pad) if right else X(pad)) + dx     # strip's left edge
    if right:
        gx, tx0, d = left_x + tw, left_x + tw, -1             # gate on the right
    else:
        gx, tx0, d = left_x, left_x + gw, 1
    # Strip background + timeline.
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(6, 8, 12, 200))
    p.drawRoundedRect(QRectF(left_x, y0, full, hh), 7, 7)
    p.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
    p.drawLine(QPointF(tx0 + d * 6, y0 + hh / 2.0), QPointF(tx0 + d * (tw - 8), y0 + hh / 2.0))

    def pos(sec):
        return tx0 + d * (10 + (tw - 22) * math.sqrt(max(0.0, min(sec, SPAN_S)) / SPAN_S))

    for t in TICKS_S:
        xx = pos(t)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1.0))
        p.drawLine(QPointF(xx, y0 + hh - 6), QPointF(xx, y0 + hh - 2))
        if tw >= 150:                    # room for the second marks
            _text(p, "%ds" % t, xx, y0 + hh + 10, "tick", QColor(255, 255, 255, 110), centre=True, shadow=False)
    # The gate.
    lit = bool(ready)
    gpen = QPen(_q(_lift(base, 0.3), 220) if lit else QColor(255, 255, 255, 50), 1.6)
    p.setPen(gpen)
    p.setBrush(_q(base, 40) if lit else QColor(255, 255, 255, 8))
    p.drawRoundedRect(QRectF(gx + 2, y0 + 2, gw - 4, hh - 4), 6, 6)
    if not lit:
        _text(p, "READY", gx + gw / 2.0, y0 + hh / 2.0 + 4, "small", QColor(255, 255, 255, 60), centre=True, shadow=False)
    iy = y0 + (hh - ICON) / 2.0
    # Cooling icons: farthest first so the nearest-to-ready sits on top.
    for e in sorted(cooling, key=lambda e: -e.left_ms):
        if e.state == "blocked":
            ix = tx0 + d * (tw - 6) - (ICON if d > 0 else 0)
        else:
            ix = pos(e.left_ms / 1000.0) - ICON / 2.0
        _icon(p, world, s, e, ix, iy, base, clickable, now)
    for i, e in enumerate(ready):
        ix = (gx + gw - 6 - ICON - i * (ICON + 4)) if right else (gx + 6 + i * (ICON + 4))
        _icon(p, world, s, e, ix, iy, base, clickable, now)


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
        p.drawRoundedRect(r.adjusted(-4, -4, 4, 4), 7, 7)
        p.setBrush(_q(col, 245))
        p.drawRoundedRect(r, 5, 5)
        _text(p, e.label, x + ICON / 2.0, y + ICON / 2.0 + 4, "icon", QColor(10, 13, 19), centre=True, shadow=False)
        pk = (now - _ready_t.get(key, -9.0)) / PING_S
        if 0 <= pk < 1:
            g = 2 + pk * 12
            p.setPen(QPen(QColor(255, 255, 255, int(200 * (1 - pk))), 2.0))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(-g, -g, g, g), 5 + g, 5 + g)
    else:
        blocked = e.state == "blocked"
        p.setBrush(QColor(14, 17, 24, 245))
        p.setPen(QPen(_q(col, 80 if blocked else 230), 1.4))
        p.drawRoundedRect(r, 5, 5)
        _text(p, e.label, x + ICON / 2.0, y + ICON / 2.0 + 4, "icon",
              QColor(255, 255, 255, 80) if blocked else _q(_lift(col, 0.3)), centre=True, shadow=False)
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


def _link(p, x0, box_a, box_b, right, col, k):
    """Tag-pair bracket in the pair's colour on the screen-edge side of the
    two cards (a second pair on the team sits one step further out)."""
    pen = QPen(_q(col, 220))
    pen.setWidthF(2.5)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    off = 8 + 6 * (k % 2)
    ex = x0 + CARD_W + off if right else x0 - off
    hx = ex - 6 if right else ex + 6
    ya = box_a[0] + box_a[1] / 2.0
    yb = box_b[0] + box_b[1] / 2.0
    y0, y1 = min(ya, yb), max(ya, yb)
    p.drawLine(QPointF(hx, y0), QPointF(ex, y0))
    p.drawLine(QPointF(ex, y0), QPointF(ex, y1))
    p.drawLine(QPointF(ex, y1), QPointF(hx, y1))
