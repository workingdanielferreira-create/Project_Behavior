"""
Damage numbers — a floating combined-damage readout over whatever took the
hit.  Identical in Solo & Battle: every HP loss already funnels through one
of three choke points, and each reports here:

  * fighters (incl. Mirror Legion copies / Summoner constructs)
                     ai.apply_hp_damage, after every block / scale / shield
  * HPT clones       combat.tick_hpt_clones' enemy-projectile pass
  * structures       unique._struct_hit (Terraform walls / towers)

Consolidation: the first hit on a target opens a fixed window of
config.DMG_NUM_WINDOW_MS (2 s).  Every further hit inside it adds to the same
number (which pops on each add).  The window does NOT extend on new hits —
once it closes the number drifts up and fades, and the next hit opens a new
one.  While open the number follows the target, floating above its head.

Timing runs on world.global_tick, so hit-stop and the pre-battle menu pause
the window along with everything else.  The list lives on the World
(world.damage_numbers), shared by both sides like sparks / clash_fx.
"""

from PyQt5.QtGui import QColor, QFont

from . import config


def _ticks(ms):
    return max(1, int(round(ms / config.TICK_MS)))


class DamageNumber:
    __slots__ = ("target", "total", "start", "last_hit", "rgb", "x", "y", "lift")

    def __init__(self, target, amount, tick, rgb, x, y, lift):
        self.target = target
        self.total = float(amount)
        self.start = tick
        self.last_hit = tick
        self.rgb = rgb
        self.x, self.y = x, y        # last known anchor (kept if target goes away)
        self.lift = lift             # px above the anchor the number sits at


def _anchor(target):
    """(x, y, lift) for a fighter (Figure: transform.x/y) or anything with
    plain x/y (HPT clone, structure)."""
    t = getattr(target, "transform", None)
    if t is not None:
        return t.x, t.y, config.DMG_NUM_LIFT_PX
    r = float(getattr(target, "r", 0.0) or 0.0)
    return float(target.x), float(target.y), max(config.DMG_NUM_LIFT_SMALL_PX, r + 10.0)


def note(world, target, amount, rgb):
    """Add `amount` damage dealt to `target` (colour = the victim's own).
    Joins the target's open window, or opens a new one."""
    if world is None or target is None:
        return
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return
    if amount <= 0:
        return
    lst = getattr(world, "damage_numbers", None)
    if lst is None:
        lst = world.damage_numbers = []
    now = world.global_tick
    win = _ticks(config.DMG_NUM_WINDOW_MS)
    for e in lst:
        if e.target is target and now - e.start < win:
            e.total += amount
            e.last_hit = now
            return
    x, y, lift = _anchor(target)
    lst.append(DamageNumber(target, amount, now, tuple(rgb[:3]), x, y, lift))


def fig_rgb(fig):
    """A fighter's colour — the LUT midpoint, same as its HP readout."""
    try:
        r, g, b = fig.lut[128][:3]
        return (int(r), int(g), int(b))
    except Exception:
        return (255, 255, 255)


def _fmt(v):
    if abs(v - round(v)) < 0.05:
        return str(int(round(v)))
    return f"{v:.1f}"


_FONT = None


def draw_all(p, world, scale_at):
    """Paint every live damage number; drops the finished ones.
    `scale_at(x, y)` is the position-scale factor (combat.position_scale)."""
    lst = getattr(world, "damage_numbers", None)
    if not lst:
        return
    global _FONT
    if _FONT is None:
        _FONT = QFont("Consolas")
        _FONT.setPointSizeF(config.DMG_NUM_FONT_SIZE)   # fractional pt (QFont() takes whole pt only)
        _FONT.setBold(True)
    now = world.global_tick
    win = _ticks(config.DMG_NUM_WINDOW_MS)
    fade = _ticks(config.DMG_NUM_FADE_MS)
    pop = _ticks(config.DMG_NUM_POP_MS)
    live = []
    p.save()
    for e in lst:
        age = now - e.start
        if age >= win + fade:
            continue
        live.append(e)
        if age < win:
            # Window open: ride along with the target.
            try:
                e.x, e.y, e.lift = _anchor(e.target)
            except Exception:
                pass
            rise, alpha = 0.0, 1.0
        else:
            t = (age - win) / float(fade)
            rise, alpha = config.DMG_NUM_FADE_RISE_PX * t, 1.0 - t
        s = scale_at(e.x, e.y)
        since = now - e.last_hit
        bump = 1.0 + config.DMG_NUM_POP_SCALE * max(0.0, 1.0 - since / float(pop))
        cx, cy = e.x, e.y - (e.lift + rise) * s
        txt = _fmt(e.total)
        r, g, b = e.rgb
        a = int(255 * max(0.0, min(1.0, alpha)))
        p.save()
        p.translate(cx, cy)
        p.scale(s * bump, s * bump)
        p.setFont(_FONT)
        fm = p.fontMetrics()
        tx = -fm.horizontalAdvance(txt) / 2.0
        ty = fm.ascent() / 2.0
        # dark outline for legibility, then a glow, then the number
        p.setPen(QColor(0, 0, 0, int(a * 0.7)))
        for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            p.drawText(int(tx + ox), int(ty + oy), txt)
        p.setPen(QColor(r, g, b, max(0, a // 3)))
        p.drawText(int(tx - 1), int(ty + 1), txt)
        p.setPen(QColor(min(255, r + 60), min(255, g + 60), min(255, b + 60), a))
        p.drawText(int(tx), int(ty), txt)
        p.restore()
    p.restore()
    world.damage_numbers = live
