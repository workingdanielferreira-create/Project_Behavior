"""
Team HP bars — one bar per roster slot in its team's corner: Team 1
top-left, Team 2 top-right, stacked down in selection order (roster.Slot
.pick, the order the start menu numbered them).

Each bar shows the slot letter, the character, its HP (a lighter "recent
damage" strip trails behind the fill) and its state: a tag pair's benched
fighter is dimmed with BENCH and the pair is joined by a TAG bracket; a
fallen fighter reads KO.  The floating HP readout bottom-right stays as it
is.  Drawn in normal frames and on the start-menu pause screen; Solo shows
Team 1 only (Team 2 empty), Battle both — same code.
"""

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QFont, QPen

from . import roster as _roster
from . import tag as _tag

MARGIN_X = 24
MARGIN_Y = 22
BAR_W = 260
BAR_H = 14
ROW_H = 46
LAG_STEP = 0.006          # recent-damage strip catch-up per frame (fraction of max)

_fonts = {}
_lag = {}                 # id(fig) -> displayed fraction of the trailing strip


def _font(key):
    f = _fonts.get(key)
    if f is None:
        f = (QFont("Consolas", 10, QFont.Bold) if key == "label"
             else QFont("Consolas", 9, QFont.Bold))
        _fonts[key] = f
    return f


def _lift(rgb, k):
    r, g, b = rgb
    return (int(r + (255 - r) * k), int(g + (255 - g) * k), int(b + (255 - b) * k))


def _name(slot):
    fig = slot.fig
    ch = getattr(fig.mode, "character", None) or {}
    return str(ch.get("display_name") or fig.mode.key).replace("_", " ").upper()


def draw(p, world):
    slots = getattr(world, "slots", None) or []
    live = set()
    for team in range(_roster.TEAM_COUNT):
        rows = [s for s in _roster.team_slots(slots, team) if s.fig is not None]
        if not rows:
            continue
        right = team == 1
        x0 = world.screen_w - MARGIN_X - BAR_W if right else MARGIN_X
        ys = []
        for n, s in enumerate(rows):
            y = MARGIN_Y + n * ROW_H
            ys.append(y)
            live.add(id(s.fig))
            _row(p, s, x0, y, right, _tag.status(world, s),
                 _tag.partner_of(world, s) is not None)
        pair = world.tag_pairs[team] if team < len(getattr(world, "tag_pairs", ())) else None
        if pair is not None and len(rows) == 2:
            _link(p, x0, ys, right)
    for k in list(_lag.keys()):
        if k not in live:
            del _lag[k]


def _row(p, s, x0, y, right, status, linked):
    fig = s.fig
    hp, mx = float(fig.personality.hp), float(max(1, fig.personality.max_hp))
    frac = max(0.0, min(1.0, hp / mx))
    lag = _lag.get(id(fig), frac)
    lag = frac if lag < frac else max(frac, lag - LAG_STEP)
    _lag[id(fig)] = lag
    dim = status in ("bench", "ko")
    a = 120 if dim else 235
    base = tuple(fig.lut[128])
    col = _lift(base, 0.25)
    if frac < 0.25 and status == "on":
        col = (255, 70, 60)

    # Label line: "1  A  RONIN" ... state on the far side.
    p.setFont(_font("label"))
    fm = p.fontMetrics()
    label = "%d  %s  %s" % (s.pick, s.name, _name(s))
    state = {"on": "TAG" if linked else "",
             "bench": "BENCH", "ko": "KO"}.get(status, "")
    ty = y + fm.ascent()
    lw = fm.horizontalAdvance(label)
    lx = x0 + BAR_W - lw if right else x0
    p.setPen(QColor(0, 0, 0, 150))
    p.drawText(lx + 1, ty + 1, label)
    lc = _lift(base, 0.45)
    p.setPen(QColor(lc[0], lc[1], lc[2], a))
    p.drawText(lx, ty, label)
    if state:
        p.setFont(_font("small"))
        sfm = p.fontMetrics()
        sw = sfm.horizontalAdvance(state)
        sx = x0 if right else x0 + BAR_W - sw
        p.setPen(QColor(255, 90, 80, 220) if status == "ko" else QColor(255, 255, 255, 150))
        p.drawText(sx, ty, state)

    # Bar: frame, recent-damage strip, fill (drains toward the team's edge).
    by = y + fm.height() + 3
    rect = QRectF(x0, by, BAR_W, BAR_H)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(10, 14, 20, 150 if dim else 190))
    p.drawRoundedRect(rect, 3, 3)

    def part(f):
        w = BAR_W * f
        return QRectF(x0 + BAR_W - w, by, w, BAR_H) if right else QRectF(x0, by, w, BAR_H)

    if lag > frac:
        p.setBrush(QColor(255, 255, 255, 70 if dim else 140))
        p.drawRoundedRect(part(lag), 3, 3)
    if frac > 0:
        p.setBrush(QColor(col[0], col[1], col[2], a))
        p.drawRoundedRect(part(frac), 3, 3)
    pen = QPen(QColor(255, 255, 255, 80 if dim else 150))
    pen.setWidthF(1.0)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(rect, 3, 3)

    p.setFont(_font("small"))
    sfm = p.fontMetrics()
    txt = "%d / %d" % (int(round(hp)), int(round(mx)))
    tx = x0 + 6 if right else x0 + BAR_W - 6 - sfm.horizontalAdvance(txt)
    p.setPen(QColor(0, 0, 0, 170))
    p.drawText(tx + 1, by + BAR_H - 3 + 1, txt)
    p.setPen(QColor(255, 255, 255, 200 if not dim else 120))
    p.drawText(tx, by + BAR_H - 3, txt)


def _link(p, x0, ys, right):
    """TAG bracket joining a pair's two bars on the screen-edge side."""
    pen = QPen(QColor(255, 255, 255, 120))
    pen.setWidthF(1.5)
    p.setPen(pen)
    ex = x0 + BAR_W + 8 if right else x0 - 8
    hx = ex - 5 if right else ex + 5
    y0, y1 = ys[0] + ROW_H // 2 + 2, ys[1] + ROW_H // 2 + 2
    p.drawLine(int(hx), int(y0), int(ex), int(y0))
    p.drawLine(int(ex), int(y0), int(ex), int(y1))
    p.drawLine(int(ex), int(y1), int(hx), int(y1))
