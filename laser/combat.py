"""
Combat — projectiles, crescent waves, and (stage 2) the swordsman attack FSM.

Projectile and CrescentWave are self-contained entities ported faithfully from
the original.  The dash / rebound / slash / combo / dodge controller and the
collision triggers that drive a swordsman are ported in stage 2; this module is
where they will live, operating on a Figure's `Combatant` component.
"""

import math
import random
from collections import deque

from PyQt5.QtCore import Qt
from PyQt5.QtGui import (QColor, QPen, QRadialGradient, QPainterPath,
                         QPixmap, QPainter, QImage)

from . import config
from .geometry import angle_deg_qt, angle_diff
from .palette import LUT_MASK


# ---------------------------------------------------------------------------
# Bullet sprite cache — pre-rendered glow+core pixmaps, keyed by colour/radius.
#
# QRadialGradient construction per bullet per frame was the single largest
# paint cost (hundreds of live bullets during ultimates).  Each unique
# (r, g, b, radius) combination is rasterised ONCE into a QPixmap and reused
# every frame via drawPixmap, with painter opacity providing the age fade.
# Colours come from a small set of LUT midpoints, so the cache stays tiny.
# Pixmaps are built lazily at first draw (QApplication exists by then).
# ---------------------------------------------------------------------------
_BULLET_SPRITES = {}
_TRAIL_PEN = QPen()
_TRAIL_PEN.setCapStyle(Qt.RoundCap)


def bullet_sprite(r, g, b, radius):
    """Return (pixmap, half_size) for a bullet of this colour and radius."""
    key = (r, g, b, round(float(radius), 2))
    entry = _BULLET_SPRITES.get(key)
    if entry is None:
        glow = max(1.0, float(radius) * 3.0)
        size = int(math.ceil(glow * 2)) + 2
        c = size / 2.0
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        qp = QPainter(pm)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setPen(Qt.NoPen)
        grad = QRadialGradient(c, c, glow)
        grad.setColorAt(0.0, QColor(r, g, b, 140))
        grad.setColorAt(1.0, QColor(r, g, b, 0))
        qp.setBrush(grad)
        qp.drawEllipse(int(c - glow), int(c - glow), int(glow * 2), int(glow * 2))
        rad = max(1.0, float(radius))
        core = QRadialGradient(c, c, rad)
        core.setColorAt(0.0, QColor(255, 255, 255, 240))
        core.setColorAt(0.5, QColor(r, g, b, 210))
        core.setColorAt(1.0, QColor(r, g, b, 140))
        qp.setBrush(core)
        qp.drawEllipse(int(c - rad), int(c - rad), int(rad * 2), int(rad * 2))
        qp.end()
        entry = (pm, size // 2)
        _BULLET_SPRITES[key] = entry
    return entry


# ---------------------------------------------------------------------------
# Comet bolt sprite cache — elongated energy bolts stretched along velocity.
# Rendered once per (colour, radius, stretch, hot) and drawn rotated to the
# bullet's heading each frame.  Bright head sits at the bullet position with
# the tail trailing behind.  `hot` adds an extra white-hot streak (zigzag).
# Returns (pixmap, head_x, half_h) — draw at (-head_x, -half_h) after
# translating to the bullet and rotating to its velocity angle.
# ---------------------------------------------------------------------------
_BOLT_SPRITES = {}


def _style_stretch(style):
    return {
        "cone":   config.BOLT_STRETCH_CONE,
        "zigzag": config.BOLT_STRETCH_ZIGZAG,
        "homing": config.BOLT_STRETCH_HOMING,
        "beam":   config.BOLT_STRETCH_BEAM,
    }.get(style, config.BOLT_STRETCH_CONE)


def bolt_sprite(r, g, b, radius, stretch, hot=False):
    key = (r, g, b, round(float(radius), 2), round(float(stretch), 2), hot)
    entry = _BOLT_SPRITES.get(key)
    if entry is None:
        glow = max(1.0, float(radius) * 3.0)
        w = int(math.ceil(glow * 2 * stretch)) + 2
        h = int(math.ceil(glow * 2)) + 2
        cx, cy = w / 2.0, h / 2.0
        head_x = w - glow          # bright head, one glow-radius from front
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        qp = QPainter(pm)
        qp.setRenderHint(QPainter.Antialiasing)
        qp.setPen(Qt.NoPen)
        # Elongated glow body (scaled radial gradient -> ellipse streak)
        qp.save()
        qp.translate(cx, cy)
        qp.scale(stretch, 1.0)
        grad = QRadialGradient(0, 0, glow)
        grad.setColorAt(0.0, QColor(r, g, b, 170))
        grad.setColorAt(1.0, QColor(r, g, b, 0))
        qp.setBrush(grad)
        qp.drawEllipse(int(-glow), int(-glow), int(glow * 2), int(glow * 2))
        if hot:
            # White-hot inner streak for the zigzag flair
            hotg = QRadialGradient(0, 0, glow * 0.6)
            hotg.setColorAt(0.0, QColor(255, 255, 255, 150))
            hotg.setColorAt(1.0, QColor(255, 255, 255, 0))
            qp.setBrush(hotg)
            g6 = glow * 0.6
            qp.drawEllipse(int(-g6), int(-g6), int(g6 * 2), int(g6 * 2))
        qp.restore()
        # White-hot round head at the front
        rad = max(1.0, float(radius)) * 1.2
        core = QRadialGradient(head_x, cy, rad)
        core.setColorAt(0.0, QColor(255, 255, 255, 245))
        core.setColorAt(0.5, QColor(r, g, b, 220))
        core.setColorAt(1.0, QColor(r, g, b, 0))
        qp.setBrush(core)
        qp.drawEllipse(int(head_x - rad), int(cy - rad), int(rad * 2), int(rad * 2))
        qp.end()
        entry = (pm, head_x, h / 2.0)
        _BOLT_SPRITES[key] = entry
    return entry


# ---------------------------------------------------------------------------
# Silhouette cache — tinted copies of sprite frames. Used by dash afterimages
# (crimson) and by the generic outline-glow feature (any authored colour, e.g.
# black). One silhouette is rasterised per unique (frame pixmap, colour) pair
# (frames live for the program lifetime, so id()-keying is safe) and reused.
# ---------------------------------------------------------------------------
_SILHOUETTES = {}


def silhouette(frame, rgb=None):
    """Return the cached tinted silhouette pixmap for a sprite frame.

    rgb defaults to the crimson afterimage colour for backward compatibility;
    pass an explicit (r, g, b) tuple for other tints (e.g. outline glow).
    """
    r, g, b = rgb if rgb is not None else config.AFTERIMAGE_RGB
    key = (id(frame), r, g, b)
    pm = _SILHOUETTES.get(key)
    if pm is None:
        pm = QPixmap(frame.size())
        pm.fill(Qt.transparent)
        qp = QPainter(pm)
        qp.drawPixmap(0, 0, frame)
        qp.setCompositionMode(QPainter.CompositionMode_SourceIn)
        qp.fillRect(pm.rect(), QColor(r, g, b))
        qp.end()
        _SILHOUETTES[key] = pm
    return pm


def spawn_afterimage(fig):
    """Drop a crimson speed-ghost at the figure's current position.

    Called from every dash-movement branch of the combat FSM (straight dash,
    arc approach/orbit, recoil, dodge) so ghosts trail all fast movement.
    Rate-limited by AFTERIMAGE_INTERVAL; capped at AFTERIMAGE_MAX live ghosts.
    """
    c = fig.combat
    c.afterimage_tick += 1
    if c.afterimage_tick < config.AFTERIMAGE_INTERVAL:
        return
    c.afterimage_tick = 0
    frame = fig._current_frame()
    if frame is None:
        return
    c.afterimages.append([fig.transform.x, fig.transform.y, frame, 0])
    if len(c.afterimages) > config.AFTERIMAGE_MAX:
        c.afterimages.pop(0)


# ---------------------------------------------------------------------------
# Parry deflect factory — a blocked bullet ricochets off the swordsman.
# ---------------------------------------------------------------------------
def make_deflect_bullet(fig_x, fig_y, bx, by, bvx, bvy, color_rgb):
    """Return one cosmetic ricochet Projectile for a parried bullet.

    Direction: away from the swordsman (fig -> bullet axis) plus a random
    angle inside DEFLECT_CONE_DEG.  Keeps the shooter's original colour.
    hit_r_sq = 0 marks it cosmetic: no collisions of any kind, and the battle snapshot
    excludes it from sharing so it can never deal damage in either mode.
    """
    dx, dy = bx - fig_x, by - fig_y
    d = (dx * dx + dy * dy) ** 0.5
    if d > 0.001:
        base = math.atan2(dy, dx)
    else:
        base = random.uniform(0.0, 2.0 * math.pi)
    half = math.radians(config.DEFLECT_CONE_DEG) * 0.5
    a = base + random.uniform(-half, half)
    spd = max((bvx * bvx + bvy * bvy) ** 0.5, 0.001) * config.DEFLECT_SPEED_MULT
    pr = Projectile(bx, by, math.cos(a) * spd, math.sin(a) * spd,
                    color_rgb, max(3, config.PROJ_TRAIL_LEN))
    pr.max_age = config.DEFLECT_MAX_AGE
    pr.hit_r_sq = 0.0
    return pr


# ---------------------------------------------------------------------------
# Projectile — a bullet with a short position-history trail
# ---------------------------------------------------------------------------
def kill_projectile(pr):
    """Destroy a live projectile immediately (alive is derived from age, so
    ageing it out is the one uniform kill switch for every bullet class).
    Used when the enemy side intercepts a bullet through its snapshot —
    petals, crescents, parries, and bullet-vs-bullet scatter all destroy
    the bullet at its source."""
    pr.age = pr.max_age


class Projectile:
    __slots__ = ("x", "y", "vx", "vy", "age", "r", "g", "b",
                 "max_age", "hit_r_sq", "trail", "radius", "style", "damage",
                 "pierce", "knockback_px", "owner", "one_hit")

    def __init__(self, fx, fy, vx, vy, color_rgb, trail_len):
        self.x, self.y = float(fx), float(fy)
        self.vx, self.vy = vx, vy
        self.r, self.g, self.b = color_rgb
        self.age = 0
        self.max_age = config.PROJ_MAX_AGE
        self.hit_r_sq = float(config.PROJ_HIT_RADIUS ** 2)
        self.trail = deque(maxlen=max(3, trail_len))
        self.radius = float(config.PROJ_RADIUS)  # overridable for splinters
        self.style = None    # None=round | cone|zigzag|homing|beam comet bolt
        # one_hit: generic cap — the victim-side damage pass kills this
        # bullet at source after its FIRST landed hit, so pierce bullets
        # (which are never culled on contact) can still deal exactly one
        # hit each (see CollisionSystem enemy-projectile damage loop).
        self.one_hit = False
        # HP damage this bullet deals on a real hit (see ai.battle_hit /
        # ai.apply_hp_damage and the enemy-side snapshot). Every built-in
        # shot (runner/swordsman fan, splinters, deflects) keeps the
        # historical flat 1 HP per hit; only JSON-character attacks
        # (combat.fire_character_action) set a different value from their
        # per-fx-layer `battle.damage`. Identical in Solo & Battle.
        self.damage = 1.0
        # Pierce (see battle_semantics.attack.pierce in a character's JSON):
        # a piercing projectile survives contact with the cursor/an enemy
        # figure instead of being destroyed on the spot (see the cull loop
        # in systems.ProjectileSystem.update) — it still registers the
        # hit/visual, it just keeps flying afterwards. Default False keeps
        # every existing bullet's behaviour exactly as before. Identical
        # gate in Solo & Battle.
        self.pierce = False
        # Optional generic knockback override (see battle_semantics.knockback_px
        # in a character's JSON): when > 0, a hit from this projectile forces
        # a FIXED total knockback travel distance in px, replacing the default
        # growing hit_power-based knockback (see ai.battle_hit). 0.0 (default)
        # means "use standard knockback" — every existing bullet's behaviour
        # is unchanged. Identical gate in Solo & Battle.
        self.knockback_px = 0.0
        # The Figure that fired this shot, or None for ownerless bullets
        # (splinters, deflect ricochets, legacy make_shot paths). Used by the
        # same-side parry check in systems.ProjectileSystem so a figure never
        # parries its OWN bullet at the moment of firing — a shooter with a
        # deflect-flagged defend layer would otherwise eat every shot it
        # fires at birth (spawn point is always inside its own parry radius).
        # Never crosses the IPC boundary — the snapshot reads only physics
        # fields. Identical in Solo & Battle.
        self.owner = None

    @property
    def alive(self):
        return self.age < self.max_age

    def update(self):
        self.trail.append((self.x, self.y))
        self.x += self.vx
        self.y += self.vy
        self.age += 1

    def draw(self, p):
        if self.style == "invisible":
            # Damage/snapshot/hit-detection still run normally — only the round-
            # dot sprite is skipped because a richer local burst (see
            # combat.spawn_character_burst_fx) is providing the real visual.
            return
        fade = max(0.0, 1.0 - self.age / self.max_age)
        r, g, b = self.r, self.g, self.b
        hx, hy = int(self.x), int(self.y)

        pts = list(self.trail)
        n = len(pts)
        if n > 1:
            pen = _TRAIL_PEN
            for i in range(1, n):
                t = i / n
                pen.setColor(QColor(r, g, b, int(200 * t * fade)))
                pen.setWidthF(1.0 + 2.0 * t)
                p.setPen(pen)
                x0, y0 = pts[i - 1]; x1, y1 = pts[i]
                p.drawLine(int(x0), int(y0), int(x1), int(y1))

        # Comet bolt: rotate a cached elongated sprite to the heading.
        style = self.style
        spd_sq = self.vx * self.vx + self.vy * self.vy
        if style is not None and spd_sq > 0.0001:
            stretch = _style_stretch(style)
            pm, head_x, half_h = bolt_sprite(
                r, g, b, self.radius, stretch, hot=(style == "zigzag"))
            if stretch <= 1.001:
                # Round bullet (stretch reverted to 1.0): centred draw, no
                # rotation needed — classic look with the flair kept.
                if fade < 1.0:
                    p.setOpacity(fade)
                p.drawPixmap(hx - pm.width() // 2, hy - pm.height() // 2, pm)
                p.setOpacity(1.0)
            else:
                p.save()
                p.translate(hx, hy)
                p.rotate(math.degrees(math.atan2(self.vy, self.vx)))
                if fade < 1.0:
                    p.setOpacity(fade)
                p.drawPixmap(int(-head_x), int(-half_h), pm)
                p.restore()
                p.setOpacity(1.0)
            if style == "homing":
                # Pulsing halo — the homing flair
                halo_a = int((110 + 70 * math.sin(self.age * 0.5)) * fade)
                if halo_a > 4:
                    hr = self.radius * 3.6
                    _TRAIL_PEN.setColor(QColor(r, g, b, halo_a))
                    _TRAIL_PEN.setWidthF(1.4)
                    p.setPen(_TRAIL_PEN)
                    p.setBrush(Qt.NoBrush)
                    ihr = int(hr)
                    p.drawEllipse(hx - ihr, hy - ihr, ihr * 2, ihr * 2)
            return

        # Round sprite (deflect ricochets, splinters, legacy)
        pm, half = bullet_sprite(r, g, b, self.radius)
        if fade < 1.0:
            p.setOpacity(fade)
            p.drawPixmap(hx - half, hy - half, pm)
            p.setOpacity(1.0)
        else:
            p.drawPixmap(hx - half, hy - half, pm)


def _hex_to_rgb(hexstr, default=(255, 255, 255)):
    """'#rrggbb' -> (r, g, b) int tuple; falls back to `default` on anything
    malformed so a bad/missing colour in the JSON never raises."""
    try:
        s = str(hexstr).lstrip("#")
        if len(s) != 6:
            return default
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except (TypeError, ValueError):
        return default


def resolve_beam_layer_ref(char, ref):
    """Resolve an attack_pattern cycle phase's 'beam_layer_ref' (format
    'action_key:layer_id', e.g. 'attack_normal:L4') to the fx_layer dict it
    points at, or None if the ref is missing/malformed/stale (character was
    edited and the layer id no longer exists). Re-resolved fresh every shot
    from the live character JSON, so wizard edits take effect with no engine
    changes. Identical lookup in Solo & Battle (both read the same JSON)."""
    if not ref or ":" not in str(ref):
        return None
    action_key, _, layer_id = str(ref).partition(":")
    action = (char.get("actions") or {}).get(action_key) or {}
    for layer in action.get("fx_layers") or []:
        if layer.get("type") == "beam" and layer.get("_id") == layer_id:
            return layer
    return None


# ---------------------------------------------------------------------------
# RichBeamProjectile — a travelling attack_pattern "beam" shot that renders
# using an AUTHORED beam fx_layer's own visual params (length, tapering
# start/end width, dual-colour gradient, glow, segment jitter, pulse) instead
# of the generic comet-bolt sprite every other attack_pattern style shares
# (see attack_pattern.cycle[].beam_layer_ref). Only draw() is overridden —
# position/velocity/damage/hit-detection still flow through the exact same
# Projectile fields, so Solo & Battle parity is untouched: the battle
# snapshot only ever reads x/y/vx/vy/r/g/b/damage off ANY
# Projectile subclass, so none of the extra visual fields below cross the
# snapshot boundary — purely local/cosmetic rendering, per boundary discipline.
# ---------------------------------------------------------------------------
class RichBeamProjectile(Projectile):
    __slots__ = ("length", "w_start0", "w_start1", "w_end0", "w_end1",
                 "c1", "c2", "glow", "glow_color", "segments", "pulse_hz",
                 "jitter", "additive", "_jitter_seed", "detach_ticks")

    def __init__(self, fx, fy, vx, vy, color_rgb, trail_len, layer):
        super().__init__(fx, fy, vx, vy, color_rgb, trail_len)
        self.style = "beam"
        try:
            self.length = max(4.0, float(layer.get("length", 200)))
        except (TypeError, ValueError):
            self.length = 200.0
        self.w_start0 = float(layer.get("w_start0", 6) or 6)
        self.w_start1 = float(layer.get("w_start1", 6) or 6)
        self.w_end0 = float(layer.get("w_end0", 2) or 2)
        self.w_end1 = float(layer.get("w_end1", 2) or 2)
        self.c1 = _hex_to_rgb(layer.get("c1"), color_rgb)
        self.c2 = _hex_to_rgb(layer.get("c2"), color_rgb)
        try:
            self.glow = max(0.0, float(layer.get("glow", 0) or 0))
        except (TypeError, ValueError):
            self.glow = 0.0
        # Optional independent tint for the widened glow pass (e.g. black
        # outline glow); None keeps the old behaviour of glowing in the
        # beam's own gradient colour.
        self.glow_color = _hex_to_rgb(layer.get("glow_color"), None) \
            if layer.get("glow_color") else None
        try:
            self.segments = max(1, int(layer.get("segments", 1) or 1))
        except (TypeError, ValueError):
            self.segments = 1
        try:
            self.pulse_hz = float(layer.get("pulse_hz", 0) or 0)
        except (TypeError, ValueError):
            self.pulse_hz = 0.0
        try:
            self.jitter = max(0.0, float(layer.get("jitter", 0) or 0))
        except (TypeError, ValueError):
            self.jitter = 0.0
        self.additive = str(layer.get("blend", "normal")) == "additive"
        self._jitter_seed = random.randint(0, 1_000_000)
        # detach_ms (existing authored field — see fx-authoring.md) lets a
        # sustained beam cut loose from its source after a delay: before
        # this point the trailing edge stays anchored at the fire point (a
        # continuous connected beam, like a still-firing Kamehameha); after
        # it, the trailing edge is no longer pinned to the source and the
        # beam withers from the tail forward as it keeps flying (see draw()).
        # 0/absent -> never detaches, preserving old grow-and-hold behaviour
        # for any character that doesn't set it.
        try:
            detach_ms = float(layer.get("detach_ms", 0) or 0)
        except (TypeError, ValueError):
            detach_ms = 0.0
        self.detach_ticks = (max(1, int(round(detach_ms / config.TICK_MS)))
                             if detach_ms > 0 else 10 ** 9)

    def draw(self, p):
        fade = max(0.0, 1.0 - self.age / self.max_age)
        if fade <= 0.0:
            return
        spd = (self.vx * self.vx + self.vy * self.vy) ** 0.5
        if spd < 0.0001:
            return
        ux, uy = self.vx / spd, self.vy / spd  # heading; tail sits -u*length
        # Cap the visible trailing shape to how far this bolt has actually
        # travelled since it fired, so a long authored length (e.g. a big
        # death-beam body) grows out from the character over the first few
        # ticks instead of always being drawn as a fixed-length shape whose
        # far end sits in space the bolt hasn't reached yet (that mismatch
        # is what makes a long beam collapse into a small blob near the
        # head — only the near-head segments land somewhere meaningful).
        #
        # Before detach_ticks: connected mode — the trailing edge is pinned
        # to the fire point (reach == distance travelled so far), so the
        # beam reads as one continuous shot still linked to the character.
        # At/after detach_ticks: the trailing edge is released and the
        # whole segment withers — its length shrinks from whatever it was
        # at the moment of detach down to nothing by the end of life, while
        # the head keeps travelling the entire time. That's the classic
        # "beam cuts loose and dwindles away at the tail" look.
        dist_travelled = spd * self.age
        if self.age < self.detach_ticks:
            reach = min(self.length, dist_travelled)
        else:
            reach_at_detach = min(self.length, spd * self.detach_ticks)
            post_span = max(1, self.max_age - self.detach_ticks)
            shrink = min(1.0, (self.age - self.detach_ticks) / post_span)
            reach = max(0.0, reach_at_detach * (1.0 - shrink))
        if reach <= 0.0:
            return

        progress = min(1.0, self.age / max(1, self.max_age))
        w_tail = self.w_start0 + (self.w_start1 - self.w_start0) * progress
        w_head = self.w_end0 + (self.w_end1 - self.w_end0) * progress

        pulse = 1.0
        if self.pulse_hz > 0:
            t_sec = (self.age * config.TICK_MS) / 1000.0
            pulse = 0.65 + 0.35 * math.sin(2 * math.pi * self.pulse_hz * t_sec)
        alpha_mult = fade * pulse

        prev_mode = p.compositionMode()
        if self.additive:
            p.setCompositionMode(QPainter.CompositionMode_Plus)

        segs = self.segments
        rng = random.Random(self._jitter_seed + self.age)
        for i in range(segs):
            t0, t1 = i / segs, (i + 1) / segs
            hx0 = self.x - ux * reach * t0
            hy0 = self.y - uy * reach * t0
            hx1 = self.x - ux * reach * t1
            hy1 = self.y - uy * reach * t1
            if self.jitter > 0:
                j = (rng.random() * 2 - 1) * self.jitter
                hx0 += -uy * j; hy0 += ux * j
                hx1 += -uy * j; hy1 += ux * j
            w = w_head + (w_tail - w_head) * t0
            cr = self.c2[0] + (self.c1[0] - self.c2[0]) * t0
            cg = self.c2[1] + (self.c1[1] - self.c2[1]) * t0
            cb = self.c2[2] + (self.c1[2] - self.c2[2]) * t0
            if self.glow > 0:
                if self.glow_color is not None:
                    gr, gg, gb = self.glow_color
                else:
                    gr, gg, gb = int(cr), int(cg), int(cb)
                _TRAIL_PEN.setColor(QColor(gr, gg, gb, int(70 * alpha_mult)))
                _TRAIL_PEN.setWidthF(w + self.glow)
                p.setPen(_TRAIL_PEN)
                p.drawLine(int(hx0), int(hy0), int(hx1), int(hy1))
            _TRAIL_PEN.setColor(QColor(int(cr), int(cg), int(cb),
                                        int(235 * alpha_mult)))
            _TRAIL_PEN.setWidthF(max(1.0, w))
            p.setPen(_TRAIL_PEN)
            p.drawLine(int(hx0), int(hy0), int(hx1), int(hy1))

        if self.additive:
            p.setCompositionMode(prev_mode)


# ---------------------------------------------------------------------------
# ZigzagProjectile — weaves laterally while travelling toward the target
# ---------------------------------------------------------------------------
class ZigzagProjectile(Projectile):
    """Travels in a sinusoidal path perpendicular to the launch direction.

    `phase_offset` staggers the two zigzag bullets so they weave in opposite
    directions (one starts swinging left, the other right), creating a
    crossing/figure-eight look as they fly toward the target.
    """
    __slots__ = ("ax", "ay", "freq", "phase")

    def __init__(self, fx, fy, vx, vy, color_rgb, trail_len,
                 amplitude, frequency, phase_offset=0.0):
        super().__init__(fx, fy, vx, vy, color_rgb, trail_len)
        # Perpendicular unit vector (rotate 90°)
        spd = (vx * vx + vy * vy) ** 0.5
        if spd > 0.001:
            px, py = -vy / spd, vx / spd
        else:
            px, py = 0.0, 1.0
        self.ax = px * amplitude
        self.ay = py * amplitude
        self.freq = frequency
        self.phase = phase_offset

    def update(self):
        self.trail.append((self.x, self.y))
        # Sinusoidal lateral nudge
        lateral = math.sin(self.phase) * self.freq
        self.x += self.vx + self.ax * lateral
        self.y += self.vy + self.ay * lateral
        self.phase += self.freq
        self.age += 1


# ---------------------------------------------------------------------------
# HomingProjectile — steers toward a moving target at half normal speed
# ---------------------------------------------------------------------------
class HomingProjectile(Projectile):
    """Gradually turns toward (tx, ty) each tick.

    `target` is a mutable list [x, y] so the caller can update it as the
    cursor/enemy moves; the projectile will track the updated position.
    `turn_rate` caps how many radians the heading can change per tick.
    """
    __slots__ = ("target", "turn_rate", "speed")

    def __init__(self, fx, fy, vx, vy, color_rgb, trail_len,
                 target, turn_rate=0.06):
        super().__init__(fx, fy, vx, vy, color_rgb, trail_len)
        self.target = target      # [x, y]  — updated externally each tick
        self.turn_rate = turn_rate
        self.speed = (vx * vx + vy * vy) ** 0.5

    def update(self):
        self.trail.append((self.x, self.y))
        # Steer toward target
        tx, ty = self.target[0], self.target[1]
        dx, dy = tx - self.x, ty - self.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0.001 and self.speed > 0.001:
            desired_vx = dx / dist * self.speed
            desired_vy = dy / dist * self.speed
            # Blend current heading toward desired heading
            self.vx += (desired_vx - self.vx) * self.turn_rate
            self.vy += (desired_vy - self.vy) * self.turn_rate
            # Re-normalise to constant speed
            cur_spd = (self.vx * self.vx + self.vy * self.vy) ** 0.5
            if cur_spd > 0.001:
                self.vx = self.vx / cur_spd * self.speed
                self.vy = self.vy / cur_spd * self.speed
        self.x += self.vx
        self.y += self.vy
        self.age += 1


# ---------------------------------------------------------------------------
# Runner shot-cycle factory
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Splinter factory — called when a bullet collides with an enemy bullet
# ---------------------------------------------------------------------------
def make_splinter_bullets(proj):
    """Return 3 tiny Projectile objects bursting perpendicular to the parent.

    The burst is centred on the parent's current position.  The three bullets
    fan out symmetrically: one straight perpendicular-left, one straight
    perpendicular-right, and one straight ahead — each offset by
    SPLINTER_SPREAD_DEG so none retrace the original path.

    Perpendicular is computed from the parent velocity so the scatter always
    looks natural regardless of the bullet's travel direction.
    """
    spd = (proj.vx * proj.vx + proj.vy * proj.vy) ** 0.5
    if spd < 0.001:
        spd = config.PROJ_SPEED

    # Forward unit vector from parent velocity
    fx, fy = proj.vx / spd, proj.vy / spd
    # Perpendicular unit vector (90° left of travel)
    px, py = -fy, fx

    srad = config.PROJ_RADIUS * config.SPLINTER_RADIUS_SCALE
    sspd = spd * config.SPLINTER_SPEED_MULT
    half = math.radians(config.SPLINTER_SPREAD_DEG)
    tl = max(2, config.PROJ_TRAIL_LEN - 1)
    cr = (proj.r, proj.g, proj.b)

    # Three directions: left-perp, right-perp, straight-back-through
    # (visually: two side-bursts + one that carries forward at an angle)
    angles = (-half, 0.0, half)   # relative to perpendicular axis
    splinters = []
    for a in angles:
        ca, sa = math.cos(a), math.sin(a)
        # Rotate perpendicular vector by a around the forward axis
        dvx = (px * ca - fx * sa) * sspd
        dvy = (py * ca - fy * sa) * sspd
        s = Projectile(proj.x, proj.y, dvx, dvy, cr, tl)
        s.radius = srad
        s.max_age = config.SPLINTER_MAX_AGE
        s.hit_r_sq = 0.0   # splinters do not trigger further collisions
        splinters.append(s)
    return splinters


def make_runner_cycle_shot(fx, fy, cx, cy, color_rgb, phase):
    """Return a list of Projectile objects for the given cycle phase.

    phase 0 — CONE   : 3 clusters spread in a fan (config.SHOT_CONE_ANGLES)
    phase 1 — ZIGZAG : 2 clusters that weave in opposing sine waves
    phase 2 — HOMING : 1 cluster that slowly tracks the target
    """
    dx, dy = cx - fx, cy - fy
    d = (dx * dx + dy * dy) ** 0.5
    base_deg = math.degrees(math.atan2(dy, dx)) if d > 0.01 else 0.0
    tl = config.PROJ_TRAIL_LEN
    cr = color_rgb

    if phase == 0:
        # --- CONE ---
        bullets = []
        for off in config.SHOT_CONE_ANGLES:
            a = math.radians(base_deg + off)
            vx = math.cos(a) * config.PROJ_SPEED
            vy = math.sin(a) * config.PROJ_SPEED
            pr = Projectile(fx, fy, vx, vy, cr, tl)
            pr.style = "cone"
            bullets.append(pr)
        return bullets

    elif phase == 1:
        # --- ZIGZAG ---
        base_rad = math.radians(base_deg)
        vx = math.cos(base_rad) * config.PROJ_SPEED
        vy = math.sin(base_rad) * config.PROJ_SPEED
        amp = config.SHOT_ZIGZAG_AMPLITUDE
        freq = config.SHOT_ZIGZAG_FREQUENCY
        b0 = ZigzagProjectile(fx, fy, vx, vy, cr, tl,
                               amplitude=amp, frequency=freq,
                               phase_offset=0.0)
        b0.style = "zigzag"
        return [b0]

    else:
        # --- HOMING ---
        base_rad = math.radians(base_deg)
        hspd = config.PROJ_SPEED * config.SHOT_HOMING_SPEED_MULT
        vx = math.cos(base_rad) * hspd
        vy = math.sin(base_rad) * hspd
        target_ref = [float(cx), float(cy)]
        hp_ = HomingProjectile(fx, fy, vx, vy, cr, tl,
                               target=target_ref, turn_rate=0.06)
        hp_.style = "homing"
        return [hp_]


# ---------------------------------------------------------------------------
# Generic attack-pattern interpreter — reads a character's own
# `attack_pattern.cycle[phase]` block (see characters/*.json + FX Creator's
# attack-pattern step) and produces Projectiles using the SAME math as
# make_runner_cycle_shot above, except every number (style, count, angles,
# amplitude, frequency, speed_mult, turn_rate) comes from JSON instead of
# config.SHOT_* constants. Feeding this Runner's own numbers reproduces
# Runner's cycle exactly (see the "runner_cycle" wizard preset) — this
# function is a superset, not a replacement, of make_runner_cycle_shot.
# Damage comes from attack_pattern.damage (default 1.0). Identical call site
# and math in Solo & Battle (see systems.ProjectileSystem._fire_attack_pattern).
# ---------------------------------------------------------------------------
def has_attack_pattern(char):
    """True if this JSON character authors a non-empty attack_pattern.cycle."""
    if not char:
        return False
    return bool((char.get("attack_pattern") or {}).get("cycle"))


def fire_attack_pattern(fig, phase_cfg, target_x, target_y):
    """Return the Projectiles for one phase of a JSON character's
    attack_pattern.cycle. `phase_cfg` is cycle[<phase index>]:
      style        : "cone" | "zigzag" | "homing" | "beam"   (default "cone")
      count        : bullets this phase spawns                (default 1)
      angles_deg   : list of fan offsets, cone style only      (default [0.0])
      amplitude    : zigzag lateral swing in px                (default 55.0)
      frequency    : zigzag weave rate, radians/tick            (default 0.18)
      turn_rate    : homing steer-per-tick, 0..1                (default 0.06)
      speed_mult   : multiplies config.PROJ_SPEED                (default 1.0)
    """
    dx, dy = target_x - fig.x, target_y - fig.y
    d = (dx * dx + dy * dy) ** 0.5
    base_deg = math.degrees(math.atan2(dy, dx)) if d > 0.01 else 0.0
    tl = config.PROJ_TRAIL_LEN
    cr = fig.lut[128]
    char = getattr(fig.mode, "character", None) or {}
    try:
        damage = float((char.get("attack_pattern") or {}).get("damage", 1.0))
    except (TypeError, ValueError):
        damage = 1.0

    style = str(phase_cfg.get("style", "cone"))
    try:
        speed = config.PROJ_SPEED * float(phase_cfg.get("speed_mult", 1.0))
    except (TypeError, ValueError):
        speed = config.PROJ_SPEED
    out = []

    if style == "cone":
        angles = phase_cfg.get("angles_deg") or [0.0]
        for off in angles:
            try:
                off = float(off)
            except (TypeError, ValueError):
                off = 0.0
            a = math.radians(base_deg + off)
            vx, vy = math.cos(a) * speed, math.sin(a) * speed
            pr = Projectile(fig.x, fig.y, vx, vy, cr, tl)
            pr.style, pr.damage = "cone", damage
            pr.owner = fig
            out.append(pr)

    elif style == "zigzag":
        count = max(1, int(phase_cfg.get("count", 1) or 1))
        amp = float(phase_cfg.get("amplitude", config.SHOT_ZIGZAG_AMPLITUDE))
        freq = float(phase_cfg.get("frequency", config.SHOT_ZIGZAG_FREQUENCY))
        base_rad = math.radians(base_deg)
        vx, vy = math.cos(base_rad) * speed, math.sin(base_rad) * speed
        for i in range(count):
            sign = 1.0 if i % 2 == 0 else -1.0
            pr = ZigzagProjectile(fig.x, fig.y, vx, vy, cr, tl,
                                  amplitude=amp * sign, frequency=freq,
                                  phase_offset=0.0)
            pr.style, pr.damage = "zigzag", damage
            pr.owner = fig
            out.append(pr)

    elif style == "homing":
        count = max(1, int(phase_cfg.get("count", 1) or 1))
        turn_rate = float(phase_cfg.get("turn_rate", 0.06))
        base_rad = math.radians(base_deg)
        vx, vy = math.cos(base_rad) * speed, math.sin(base_rad) * speed
        target_ref = [float(target_x), float(target_y)]
        for _ in range(count):
            pr = HomingProjectile(fig.x, fig.y, vx, vy, cr, tl,
                                  target=target_ref, turn_rate=turn_rate)
            pr.style, pr.damage = "homing", damage
            pr.owner = fig
            out.append(pr)

    elif style == "beam":
        count = max(1, int(phase_cfg.get("count", 1) or 1))
        base_rad = math.radians(base_deg)
        # beam_layer_ref ('action_key:layer_id') lets a character's own
        # authored beam fx_layer (length/width/colour/glow/segments/pulse/
        # jitter) drive the look of this travelling shot instead of the
        # generic comet-bolt every other style shares. Missing/stale ref ->
        # unchanged legacy behaviour. Cosmetic only; damage/hit-detection
        # identical either way. Identical in Solo & Battle.
        beam_layer = resolve_beam_layer_ref(char, phase_cfg.get("beam_layer_ref"))

        # Lifespan: the beam layer's own life_min/life_max (ms, averaged —
        # existing documented FX-layer field, see fx-authoring.md) overrides
        # the generic config.BEAM_MAX_AGE when authored, so a character's
        # beam can live exactly as long as it was designed to. Identical in
        # Solo & Battle.
        max_age = config.BEAM_MAX_AGE
        if beam_layer is not None:
            try:
                lmin = float(beam_layer.get("life_min", 0) or 0)
                lmax = float(beam_layer.get("life_max", 0) or 0)
            except (TypeError, ValueError):
                lmin = lmax = 0.0
            life_ms = (lmin + lmax) / 2.0
            if life_ms > 0:
                max_age = max(1, int(round(life_ms / config.TICK_MS)))

        # Speed: `travel_distance_px` on the cycle phase (new, generic —
        # any character's beam-style phase can opt in) is authoritative
        # when present: it fixes the EXACT total distance this beam covers
        # over its lifespan (distance = speed * max_age), which is a more
        # precise knob than an abstract px/s rate. Falls back to the beam
        # layer's own authored travel_speed/travel_forward_speed (px/s) if
        # no distance is given, and finally to the generic PROJ_SPEED base.
        # speed_mult only applies to the travel_speed fallback, since
        # travel_distance_px already fully determines speed given max_age.
        beam_speed = speed
        try:
            travel_distance_px = float(phase_cfg.get("travel_distance_px", 0) or 0)
        except (TypeError, ValueError):
            travel_distance_px = 0.0
        if travel_distance_px > 0:
            beam_speed = travel_distance_px / max_age
        elif beam_layer is not None:
            authored_sps = beam_layer.get("travel_speed") or \
                           beam_layer.get("travel_forward_speed")
            try:
                authored_sps = float(authored_sps)
            except (TypeError, ValueError):
                authored_sps = 0.0
            if authored_sps > 0:
                beam_speed = (authored_sps * config.TICK_MS / 1000.0) * \
                             float(phase_cfg.get("speed_mult", 1.0) or 1.0)
        vx, vy = math.cos(base_rad) * beam_speed, math.sin(base_rad) * beam_speed
        pierce = False
        knockback_px = 0.0
        if beam_layer is not None:
            beam_battle = beam_layer.get("battle") or {}
            pierce = bool((beam_battle.get("attack") or {}).get("pierce"))
            try:
                knockback_px = float(beam_battle.get("knockback_px", 0) or 0)
            except (TypeError, ValueError):
                knockback_px = 0.0
        for _ in range(count):
            if beam_layer is not None:
                pr = RichBeamProjectile(fig.x, fig.y, vx, vy, cr,
                                        config.BEAM_TRAIL_LEN, beam_layer)
            else:
                pr = Projectile(fig.x, fig.y, vx, vy, cr, config.BEAM_TRAIL_LEN)
                pr.style = "beam"
            pr.max_age = max_age
            pr.damage = damage
            pr.pierce = pierce
            pr.knockback_px = knockback_px
            pr.owner = fig
            out.append(pr)

    return out


# ---------------------------------------------------------------------------
# Generic JSON-character attacks — turns a character's own can_hit fx_layers
# (attack_normal / attack_special / ultimate — see battle_semantics.attach in
# the character JSON) into real Projectiles carrying that layer's own
# battle.damage. Reuses the existing Projectile/HomingProjectile pipeline —
# every JSON-character projectile already flows through the same
# fire -> world.projectiles -> battle snapshot -> world.enemy_projs -> petals/parry/HP
# path built for runner/swordsman, so Solo & Battle parity is automatic.
#
# Motion per layer:
#   homing=True        -> HomingProjectile (steers toward a live target ref)
#   homing=False        -> plain Projectile, which already flies straight at
#                          its launch heading with no further steering — this
#                          IS "travel_forward" (fire straight, once, forever).
#
# Cosmetic-only fields (per fx_semantics/battle_semantics: explode, scatter,
# pierce, slash, beam_travel, beam_width) are visual flourishes on the FX
# Creator side and intentionally not modelled here; only the damage-bearing
# hit itself is wired into combat.
# ---------------------------------------------------------------------------
def _character_action_layers(char, action_key):
    """can_hit fx_layers (each carrying a battle dict) for one action, or []."""
    action = (char.get("actions") or {}).get(action_key)
    if not action:
        return []
    return [l for l in (action.get("fx_layers") or [])
            if l.get("can_hit") and l.get("battle")]


def fire_character_action(fig, action_key, target_x, target_y,
                          suppress_visual=False):
    """Fire every can_hit fx_layer of `action_key` on fig's own JSON character
    as a Projectile aimed at (target_x, target_y). Multiple layers on the same
    action (e.g. mage's 5-particle attack_special) fan out symmetrically
    across config.CHAR_ATTACK_SPREAD_DEG. Returns the list of new Projectiles
    (caller extends world.projectiles). `suppress_visual=True` marks the
    resulting Projectiles style="invisible" — damage/snapshot/hit-detection still
    run identically, but the plain round-dot sprite is hidden because a
    richer local burst (spawn_character_burst_fx) is the real visual for
    that action. No-op for built-in (non-JSON) characters. Identical in
    Solo & Battle."""
    char = getattr(fig.mode, "character", None)
    if not char:
        return []
    layers = _character_action_layers(char, action_key)
    if not layers:
        return []

    dx, dy = target_x - fig.x, target_y - fig.y
    dist = (dx * dx + dy * dy) ** 0.5
    base_deg = math.degrees(math.atan2(dy, dx)) if dist > 0.01 else 0.0

    n = len(layers)
    if n == 1:
        offsets = [0.0]
    else:
        spread = config.CHAR_ATTACK_SPREAD_DEG
        offsets = [-spread / 2.0 + spread * i / (n - 1) for i in range(n)]

    cr = fig.lut[128]
    out = []
    for layer, off in zip(layers, offsets):
        battle = layer.get("battle") or {}
        try:
            damage = float(battle.get("damage", 1))
        except (TypeError, ValueError):
            damage = 1.0
        a = math.radians(base_deg + off)
        vx = math.cos(a) * config.PROJ_SPEED
        vy = math.sin(a) * config.PROJ_SPEED

        if layer.get("homing"):
            target_ref = [float(target_x), float(target_y)]
            # Tighter turn_rate than runner's cluster bullets (0.06): a
            # character's own "beam"-style attack is meant to track its
            # target closely, not drift in wide wandering arcs.
            pr = HomingProjectile(fig.x, fig.y, vx, vy, cr,
                                  config.PROJ_TRAIL_LEN,
                                  target=target_ref, turn_rate=0.35)
            pr.style = "homing"
        else:
            pr = Projectile(fig.x, fig.y, vx, vy, cr, config.PROJ_TRAIL_LEN)
            pr.style = "beam" if layer.get("type") == "beam" else None
        if suppress_visual:
            pr.style = "invisible"
        pr.damage = damage
        try:
            pr.knockback_px = float(battle.get("knockback_px", 0) or 0)
        except (TypeError, ValueError):
            pr.knockback_px = 0.0
        pr.owner = fig
        out.append(pr)
    return out


def _defend_deflect_flag(fig):
    """True if this JSON character's `defend` action has a can_hit fx_layer
    with battle.defence == 'deflect'. Cached on the mode instance (character
    JSON doesn't change after load), same pattern as _petals_config."""
    mode = fig.mode
    if hasattr(mode, "_defend_deflect"):
        return mode._defend_deflect
    flag = False
    char = getattr(mode, "character", None)
    if char:
        for layer in _character_action_layers(char, "defend"):
            if (layer.get("battle") or {}).get("defence") == "deflect":
                flag = True
                break
    mode._defend_deflect = flag
    return flag


def has_defend_deflect(fig):
    """True if fig's character should get the parry/deflect stance generalized
    to it — swordsman gets this from uses_melee() already; this extends the
    same trigger_parry/parrying mechanism to any archetype (e.g. a shooter
    mage) whose `defend` action authors a can_hit + defence:'deflect' layer.
    Identical in Solo & Battle — both share the same trigger_parry code path.

    Note: the top-level JSON `defense` field ('block'/'dodge') is purely a
    wizard pose-selector (which keyframes seed the `defend` action) — it does
    NOT gate this mechanic. The per-layer battle.defence value an author
    actually puts on a can_hit layer is the sole authority here, so an
    explicit deflect layer is never silently overridden by that field."""
    return _defend_deflect_flag(fig)


# ---------------------------------------------------------------------------
# Character particle bursts — purely cosmetic, LOCAL-ONLY rendering of a
# JSON character's own 'particles' fx_layers, matching the FX Creator export
# directly: count, spread_deg, angle_deg, speed_min/max, gravity, drag,
# size_over_life, life_min/max, c1/c2, anchor px/py. Never enters the battle
# snapshot (per the established boundary: locally-rendered eye-candy stays local;
# cross-process state uses the fixed struct layout) — the actual can_hit
# damage for these same layers is handled separately by
# fire_character_action(..., suppress_visual=True), so the two don't
# double-render. Identical call site in Solo & Battle — each process spawns
# and draws its own figures' bursts the same way, from the same JSON.
# ---------------------------------------------------------------------------
def _burst_scale(char):
    """Same FX-Creator-canvas -> game-pixel scale characters.py uses to
    rasterize the rig (TARGET_HEAD_PX / native 20px head * stats.scale), so
    a layer's px/py/size fields land at the same size the wizard previewed."""
    stats = char.get("stats", {}) or {}
    try:
        cs = float(stats.get("scale", 1.0))
    except (TypeError, ValueError):
        cs = 1.0
    cs = max(0.5, min(2.0, cs))
    return (config.TARGET_HEAD_PX / 20.0) * cs


class BurstParticle:
    """One physically-simulated particle from a character's 'particles'
    fx_layer. gravity/drag/size_over_life/color-over-life are all read
    straight from the layer so this matches the FX Creator preview.
    Cosmetic only — never affects combat resolution."""
    __slots__ = ("x", "y", "vx", "vy", "age", "life", "size0", "size1",
                 "size_mode", "rgb1", "rgb2", "gravity", "drag")

    def __init__(self, x, y, vx, vy, life_ticks, size0, size1, size_mode,
                 rgb1, rgb2, gravity, drag):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.age = 0
        self.life = max(1, life_ticks)
        self.size0, self.size1 = size0, size1
        self.size_mode = size_mode
        self.rgb1, self.rgb2 = rgb1, rgb2
        self.gravity = gravity
        self.drag = drag

    @property
    def alive(self):
        return self.age < self.life

    def update(self):
        tick_s = config.TICK_MS / 1000.0
        self.vx *= self.drag
        self.vy = self.vy * self.drag + self.gravity * tick_s
        self.x += self.vx * tick_s
        self.y += self.vy * tick_s
        self.age += 1

    def _current_size(self, t):
        s0, s1 = self.size0, self.size1
        if self.size_mode == "shrink":
            return s1 + (s0 - s1) * (1.0 - t)
        if self.size_mode == "grow":
            return s0 + (s1 - s0) * t
        if self.size_mode == "pulse":
            return s0 + (s1 - s0) * math.sin(min(1.0, t) * math.pi)
        return s0

    def draw(self, p):
        t = min(1.0, self.age / self.life)
        size = max(0.5, self._current_size(t))
        r = int(self.rgb1[0] + (self.rgb2[0] - self.rgb1[0]) * t)
        g = int(self.rgb1[1] + (self.rgb2[1] - self.rgb1[1]) * t)
        b = int(self.rgb1[2] + (self.rgb2[2] - self.rgb1[2]) * t)
        fade = max(0.0, 1.0 - t)
        pm, half = bullet_sprite(max(0, min(255, r)), max(0, min(255, g)),
                                 max(0, min(255, b)), size / 2.0)
        if fade < 1.0:
            p.setOpacity(fade)
            p.drawPixmap(int(self.x) - half, int(self.y) - half, pm)
            p.setOpacity(1.0)
        else:
            p.drawPixmap(int(self.x) - half, int(self.y) - half, pm)


def spawn_character_burst_fx(fig, action_key):
    """Queue every 'particles' fx_layer of `action_key` on fig's own JSON
    character to spawn its matching BurstParticle swarm (honoring authored
    delay_ms/trig_delay_ms). No-op for built-in characters."""
    char = getattr(fig.mode, "character", None)
    if not char:
        return
    action = (char.get("actions") or {}).get(action_key)
    if not action:
        return
    scale = _burst_scale(char)
    facing = -1.0 if fig.transform.facing_left else 1.0
    c = fig.combat
    for layer in (action.get("fx_layers") or []):
        if layer.get("type") != "particles":
            continue
        delay_ticks = int(((layer.get("delay_ms", 0) or 0)
                          + (layer.get("trig_delay_ms", 0) or 0))
                          / config.TICK_MS)
        c.pending_bursts.append([delay_ticks, layer, scale, facing])


def _spawn_burst_now(fig, layer, scale, facing):
    """Create the BurstParticle swarm for one layer once its queued delay
    has elapsed. 'point' and 'r_hand' anchors both approximate to a fixed
    px/py offset from the figure root — the runtime doesn't track live rig
    joint positions after the rig is baked into pixmaps, so this is the
    closest available anchor."""
    c = fig.combat
    px = float(layer.get("px", 0) or 0) * scale * facing
    py = float(layer.get("py", 0) or 0) * scale
    ax, ay = fig.x + px, fig.y + py

    count = max(1, int(layer.get("count", 1) or 1))
    spread = math.radians(float(layer.get("spread_deg", 30) or 0))
    base_angle = math.radians(float(layer.get("angle_deg", 0) or 0))
    if facing < 0:
        base_angle = math.pi - base_angle   # mirror fan direction with facing

    smin = float(layer.get("speed_min", 50) or 0) * scale
    smax = float(layer.get("speed_max", smin) or smin) * scale
    size_min = max(0.5, float(layer.get("size_min", 3) or 3) * scale)
    size_max = max(size_min, float(layer.get("size_max", size_min) or size_min) * scale)
    size_mode = layer.get("size_over_life", "shrink")
    life_min = max(1.0, float(layer.get("life_min", 200) or 200))
    life_max = max(life_min, float(layer.get("life_max", life_min) or life_min))
    gravity = float(layer.get("gravity", 0) or 0) * scale
    drag = float(layer.get("drag", 1.0) if layer.get("drag") is not None else 1.0)
    rgb1 = _hex_rgb_safe(layer.get("c1"), (255, 255, 255))
    rgb2 = _hex_rgb_safe(layer.get("c2"), rgb1)

    rng = fig.personality.rng
    for _ in range(count):
        a = base_angle + rng.uniform(-spread / 2.0, spread / 2.0)
        spd = rng.uniform(smin, smax) if smax > smin else smin
        vx, vy = math.cos(a) * spd, math.sin(a) * spd
        life_ms = rng.uniform(life_min, life_max)
        life_ticks = max(1, int(life_ms / config.TICK_MS))
        c.particle_bursts.append(BurstParticle(
            ax, ay, vx, vy, life_ticks, size_min, size_max, size_mode,
            rgb1, rgb2, gravity, drag))


# ---------------------------------------------------------------------------
# Sprite-line emitter — generic cosmetic FX (JSON `sprite_emitter` block).
# Particles rise off colour-matched "lines" painted inside a character's own
# sprite frames (e.g. a blade edge). Two source modes:
#   "emit" — continuously spawns small rising/fading particles from random
#            points on the line; particles inherit a fraction of the figure's
#            velocity backwards so they trail behind movement.
#   "glow" — no spawning; pulsing glow dots drawn pinned to the line points
#            (rendered by Figure.draw inside the sprite transform).
# Frame pixel positions are colour-scanned once per mode and cached; frames
# with no match borrow the nearest matching frame's points normalised to
# frame size (`infer_missing_frames`), keeping the effect alive across the
# whole loop. Purely cosmetic — never enters combat resolution or the IPC
# boundary. Identical in Solo & Battle.
# ---------------------------------------------------------------------------

def sprite_emitter_cfg(fig):
    """Parsed `sprite_emitter` block for fig's character, or None. Cached on
    the mode instance like blink_cfg/clone_cfg."""
    mode = fig.mode
    if hasattr(mode, "_sprite_emitter_cfg"):
        return mode._sprite_emitter_cfg
    char = getattr(mode, "character", None)
    raw = char.get("sprite_emitter") if char else None
    if not (isinstance(raw, dict) and isinstance(raw.get("sources"), list)):
        mode._sprite_emitter_cfg = None
        return None

    def _f(d, key, default):
        try:
            return float(d.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    sources = []
    for s in raw["sources"]:
        if not isinstance(s, dict):
            continue
        m = str(s.get("mode", "emit")).lower()
        src = dict(
            mode=("glow" if m == "glow" else "emit"),
            match_rgb=_hex_rgb_safe(s.get("match_color"), (255, 255, 255)),
            tol=_f(s, "tolerance", config.SPRITE_EMITTER_MATCH_TOL_DEFAULT),
            core_rgb=_hex_rgb_safe(s.get("core_color"), (255, 255, 255)),
            glow_rgb=_hex_rgb_safe(s.get("glow_color"),
                                   _hex_rgb_safe(s.get("match_color"),
                                                 (255, 255, 255))),
            rate_hz=_f(s, "rate_hz", config.SPRITE_EMITTER_RATE_HZ_DEFAULT),
            rise_speed=_f(s, "rise_speed",
                          config.SPRITE_EMITTER_RISE_SPEED_DEFAULT),
            trail_inherit=_f(s, "trail_inherit",
                             config.SPRITE_EMITTER_TRAIL_INHERIT_DEFAULT),
            life_ms_min=_f(s, "life_ms_min",
                           config.SPRITE_EMITTER_LIFE_MS_MIN_DEFAULT),
            life_ms_max=_f(s, "life_ms_max",
                           config.SPRITE_EMITTER_LIFE_MS_MAX_DEFAULT),
            size_min=_f(s, "size_min", config.SPRITE_EMITTER_SIZE_MIN_DEFAULT),
            size_max=_f(s, "size_max", config.SPRITE_EMITTER_SIZE_MAX_DEFAULT),
            pulse_hz=_f(s, "pulse_hz",
                        config.SPRITE_EMITTER_GLOW_PULSE_HZ_DEFAULT),
            glow_size=_f(s, "size", config.SPRITE_EMITTER_GLOW_SIZE_DEFAULT),
            glow_alpha=_f(s, "glow_alpha",
                          config.SPRITE_EMITTER_GLOW_ALPHA_DEFAULT),
            trail_anchor=bool(s.get("trail_anchor", False)),
        )
        sources.append(src)
    if not sources:
        mode._sprite_emitter_cfg = None
        return None
    mode._sprite_emitter_cfg = dict(
        sources=sources,
        infer=bool(raw.get("infer_missing_frames", True)),
    )
    return mode._sprite_emitter_cfg


def _scan_frame_points(frame, src):
    """Grid-scan one (unflipped) QPixmap frame for pixels within `tol` RGB
    distance of the source's match colour. Returns [(x, y), ...] in frame
    pixel coords (top-left origin), capped at SPRITE_EMITTER_MAX_POINTS."""
    img = frame.toImage()
    w, h = img.width(), img.height()
    mr, mg, mb = src["match_rgb"]
    tol_sq = src["tol"] * src["tol"]
    step = max(1, int(config.SPRITE_EMITTER_SCAN_STEP))
    pts = []
    for y in range(0, h, step):
        for x in range(0, w, step):
            c = img.pixelColor(x, y)
            if c.alpha() < 100:
                continue
            dr, dg, db = c.red() - mr, c.green() - mg, c.blue() - mb
            if dr * dr + dg * dg + db * db <= tol_sq:
                pts.append((x, y))
    if len(pts) > config.SPRITE_EMITTER_MAX_POINTS:
        k = len(pts) / float(config.SPRITE_EMITTER_MAX_POINTS)
        pts = [pts[int(i * k)] for i in range(config.SPRITE_EMITTER_MAX_POINTS)]
    return pts


_SRC_SCAN_CACHE = {}


def _scan_source_points(path, sources):
    """Scan an original full-resolution source PNG for every source's match
    colour in one pass. Returns (src_w, src_h, [[(x, y), ...] per source])
    in source pixel coords, or None if the file can't be read.

    Scanning the source art instead of the scaled in-game pixmap keeps thin
    authored lines detectable at any render scale (at small TARGET_HEAD_PX
    scales the lines become sub-pixel in the pixmap and vanish). The scan
    step grows with image size so startup cost stays bounded; results are
    cached per (path, colour/tolerance signature). Purely cosmetic path —
    identical in Solo & Battle."""
    sig = tuple((s["match_rgb"], s["tol"]) for s in sources)
    key = (path, sig)
    if key in _SRC_SCAN_CACHE:
        return _SRC_SCAN_CACHE[key]
    img = QImage(path)
    if img.isNull():
        _SRC_SCAN_CACHE[key] = None
        return None
    w, h = img.width(), img.height()
    step = max(int(config.SPRITE_EMITTER_SCAN_STEP), int(max(w, h) / 160))
    match = [(s["match_rgb"], s["tol"] * s["tol"]) for s in sources]
    per = [[] for _ in sources]
    for y in range(0, h, step):
        for x in range(0, w, step):
            c = img.pixelColor(x, y)
            if c.alpha() < 100:
                continue
            cr, cg, cb = c.red(), c.green(), c.blue()
            for si, ((mr, mg, mb), tol_sq) in enumerate(match):
                dr, dg, db = cr - mr, cg - mg, cb - mb
                if dr * dr + dg * dg + db * db <= tol_sq:
                    per[si].append((x, y))
    for si, pts in enumerate(per):
        if len(pts) > config.SPRITE_EMITTER_MAX_POINTS:
            k = len(pts) / float(config.SPRITE_EMITTER_MAX_POINTS)
            per[si] = [pts[int(i * k)]
                       for i in range(config.SPRITE_EMITTER_MAX_POINTS)]
    out = (w, h, per)
    _SRC_SCAN_CACHE[key] = out
    return out


def sprite_emitter_points(fig):
    """Per-frame cached line points for every source, keyed by sprite set.
    Structure: {set_name: [frame_entries]}, one entry per frame, where an
    entry is a list (parallel to cfg sources) of [(x, y), ...] point lists
    plus the frame's (w, h). Built once per mode on first call; frames with
    no match borrow the nearest matching frame's points normalised to frame
    size when `infer_missing_frames` is on."""
    mode = fig.mode
    if hasattr(mode, "_sprite_emitter_pts"):
        return mode._sprite_emitter_pts
    cfg = sprite_emitter_cfg(fig)
    if cfg is None:
        mode._sprite_emitter_pts = None
        return None
    b = fig.render.bundle
    sets = dict(run=b.run, idle=b.idle, slash=b.slash)
    char = getattr(mode, "character", None) or {}
    src_paths = char.get("_sprite_src_paths") or {}
    data = {}
    for name, frames in sets.items():
        if not frames:
            continue
        paths = src_paths.get(name) or []
        entries = []
        for fi, frame in enumerate(frames):
            fw, fh = frame.width(), frame.height()
            per_src = None
            path = paths[fi] if fi < len(paths) else None
            if path:
                # Preferred: colour-scan the original full-res source PNG
                # and remap points into scaled-frame coords, so thin lines
                # survive any render scale.
                scan = _scan_source_points(path, cfg["sources"])
                if scan is not None:
                    sw, sh, per = scan
                    per_src = [[(px * fw / float(max(1, sw)),
                                 py * fh / float(max(1, sh)))
                                for (px, py) in pts] for pts in per]
            if per_src is None:
                # Fallback (no sprite_files source on disk): scan the
                # scaled pixmap as before.
                per_src = [_scan_frame_points(frame, s)
                           for s in cfg["sources"]]
            entries.append(dict(w=fw, h=fh, pts=per_src))
        data[name] = entries
    if cfg["infer"]:
        # Fill empty frames from the nearest matching frame (same set first,
        # then any set), remapping points through normalised coordinates so
        # differently-sized frames line up proportionally.
        for si in range(len(cfg["sources"])):
            donors = []          # (set, idx, entry) with points for source si
            for name, entries in data.items():
                for i, e in enumerate(entries):
                    if e["pts"][si]:
                        donors.append((name, i, e))
            if not donors:
                continue
            for name, entries in data.items():
                for i, e in enumerate(entries):
                    if e["pts"][si]:
                        continue
                    same = [d for d in donors if d[0] == name]
                    pool = same or donors
                    donor = min(pool, key=lambda d: abs(d[1] - i))[2]
                    dw = max(1, donor["w"])
                    dh = max(1, donor["h"])
                    e["pts"][si] = [
                        (px * e["w"] / float(dw), py * e["h"] / float(dh))
                        for (px, py) in donor["pts"][si]]
    mode._sprite_emitter_pts = data
    return data


class SpriteEmitParticle:
    """One rising/fading cosmetic particle emitted off a sprite line.
    Drawn as a glow ring (glow colour) with a bright core, matching the
    authored two-colour look. Never affects combat resolution."""
    __slots__ = ("x", "y", "vx", "vy", "age", "life", "size",
                 "core_rgb", "glow_rgb")

    def __init__(self, x, y, vx, vy, life_ticks, size, core_rgb, glow_rgb):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.age = 0
        self.life = max(1, life_ticks)
        self.size = size
        self.core_rgb = core_rgb
        self.glow_rgb = glow_rgb

    @property
    def alive(self):
        return self.age < self.life

    def update(self):
        tick_s = config.TICK_MS / 1000.0
        self.vx *= 0.96
        self.vy *= 0.985
        self.x += self.vx * tick_s
        self.y += self.vy * tick_s
        self.age += 1

    def draw(self, p):
        t = min(1.0, self.age / float(self.life))
        fade = max(0.0, 1.0 - t)
        size = max(0.6, self.size * (1.0 - 0.35 * t))
        gr, gg, gb = self.glow_rgb
        cr, cg, cb = self.core_rgb
        glow_pm, gh = bullet_sprite(gr, gg, gb,
                                    size * config.SPRITE_EMITTER_GLOW_SCALE)
        core_pm, ch = bullet_sprite(cr, cg, cb, size)
        p.setOpacity(fade * 0.7)
        p.drawPixmap(int(self.x) - gh, int(self.y) - gh, glow_pm)
        p.setOpacity(fade)
        p.drawPixmap(int(self.x) - ch, int(self.y) - ch, core_pm)
        p.setOpacity(1.0)


def _frame_point_to_world(fig, e, px, py):
    """Map a frame-local point (top-left origin, unflipped frame) to world
    coordinates, honouring the flipped frame set and optional sprite
    rotation — mirroring exactly how Figure.draw places the pixmap."""
    lx = px - e["w"] / 2.0
    ly = py - e["h"] / 2.0
    if fig.transform.facing_left:
        lx = -lx
    if fig.motion.rotate and fig.transform.angle:
        a = math.radians(fig.transform.angle)
        ca, sa = math.cos(a), math.sin(a)
        lx, ly = lx * ca - ly * sa, lx * sa + ly * ca
    return fig.x + lx, fig.y + ly


def _current_sprite_entry(fig, data):
    """The cached point entry matching the frame Figure.draw shows this
    tick (mirrors Figure._current_frame's selection order), or None."""
    b = fig.render.bundle
    c = fig.combat
    m = fig.motion
    r = fig.render
    if c.slashing and b.slash and "slash" in data:
        idx = min(c.slash_idx, len(data["slash"]) - 1)
        return data["slash"][idx]
    if (m.bouncing and b.slide is not None) or        (m.bounce_ending and b.slide2 is not None):
        return None                       # slide frames aren't scanned
    if r.is_moving and b.run and "run" in data:
        return data["run"][r.run_idx % len(data["run"])]
    if b.idle and "idle" in data:
        return data["idle"][r.idle_idx % len(data["idle"])]
    if b.run and "run" in data:
        return data["run"][r.run_idx % len(data["run"])]
    return None


def update_sprite_emitter(fig):
    """Spawn new line particles for every "emit" source at its authored rate
    and tick/cull the live ones. Cheap no-op for characters without the
    `sprite_emitter` block. Call every tick for every figure — identical in
    Solo & Battle."""
    cfg = sprite_emitter_cfg(fig)
    c = fig.combat
    if cfg is None:
        return
    data = sprite_emitter_points(fig)
    # Per-tick velocity (px/s) from last position — powers the trail-behind
    # feel; first tick has no history so velocity starts at zero.
    tick_s = config.TICK_MS / 1000.0
    if c.sprite_prev_x is None:
        fvx = fvy = 0.0
    else:
        fvx = (fig.x - c.sprite_prev_x) / tick_s
        fvy = (fig.y - c.sprite_prev_y) / tick_s
    c.sprite_prev_x, c.sprite_prev_y = fig.x, fig.y
    if data:
        entry = _current_sprite_entry(fig, data)
        if entry is not None and not c.vc_hidden:
            rng = fig.personality.rng
            total_rate = sum(s["rate_hz"] for s in cfg["sources"]
                             if s["mode"] == "emit")
            c.sprite_emit_acc += total_rate * tick_s
            spawns = int(c.sprite_emit_acc)
            c.sprite_emit_acc -= spawns
            emit_srcs = [(i, s) for i, s in enumerate(cfg["sources"])
                         if s["mode"] == "emit" and entry["pts"][i]]
            for _ in range(spawns):
                if not emit_srcs:
                    break
                si, s = emit_srcs[rng.randrange(len(emit_srcs))]
                px, py = entry["pts"][si][rng.randrange(len(entry["pts"][si]))]
                wx, wy = _frame_point_to_world(fig, entry, px, py)
                vx = -fvx * s["trail_inherit"] + rng.uniform(-6.0, 6.0)
                vy = (-s["rise_speed"] + rng.uniform(-5.0, 5.0)
                      - fvy * s["trail_inherit"])
                life_ms = rng.uniform(s["life_ms_min"], s["life_ms_max"])
                life_ticks = max(1, int(life_ms / config.TICK_MS))
                size = rng.uniform(s["size_min"], s["size_max"])
                c.sprite_particles.append(SpriteEmitParticle(
                    wx, wy, vx, vy, life_ticks, size,
                    s["core_rgb"], s["glow_rgb"]))
    if c.sprite_particles:
        alive = []
        for sp in c.sprite_particles:
            sp.update()
            if sp.alive:
                alive.append(sp)
        c.sprite_particles = alive


def draw_sprite_emitter_glow(fig, p, tick_count):
    """Draw the pulsing glow dots for every "glow" source pinned to the
    current frame's line points. Called by Figure.draw in world space (the
    points are transformed through the same flip/rotation as the sprite).
    No-op without the block."""
    cfg = sprite_emitter_cfg(fig)
    if cfg is None or fig.combat.vc_hidden:
        return
    data = sprite_emitter_points(fig)
    if not data:
        return
    entry = _current_sprite_entry(fig, data)
    if entry is None:
        return
    t_s = tick_count * config.TICK_MS / 1000.0
    for si, s in enumerate(cfg["sources"]):
        if s["mode"] != "glow" or not entry["pts"][si]:
            continue
        pulse = 0.5 + 0.5 * math.sin(2.0 * math.pi * s["pulse_hz"] * t_s)
        alpha = (0.35 + 0.65 * pulse) * s["glow_alpha"] / 255.0
        gr, gg, gb = s["glow_rgb"]
        cr, cg, cb = s["core_rgb"]
        glow_pm, gh = bullet_sprite(gr, gg, gb,
                                    s["glow_size"]
                                    * config.SPRITE_EMITTER_GLOW_SCALE)
        core_pm, ch = bullet_sprite(cr, cg, cb, s["glow_size"] * 0.6)
        step = max(1, len(entry["pts"][si]) // 40)
        pts = entry["pts"][si][::step]
        p.setOpacity(alpha * 0.6)
        for (px, py) in pts:
            wx, wy = _frame_point_to_world(fig, entry, px, py)
            p.drawPixmap(int(wx) - gh, int(wy) - gh, glow_pm)
        p.setOpacity(alpha)
        for (px, py) in pts:
            wx, wy = _frame_point_to_world(fig, entry, px, py)
            p.drawPixmap(int(wx) - ch, int(wy) - ch, core_pm)
        p.setOpacity(1.0)


def _apply_trail_update(fig, t, is_moving, path_follow):
    """fig.trail.update honouring an optional sprite_emitter trail_anchor
    override (see sprite_emitter_trail_anchor below) so the trail stays
    pinned to the same live anchor through combat movement (dashes, arc
    recoils, dodges) exactly as it does during normal chase movement in
    motion.py — no anchor flicker between states. Falls back to the default
    body-anchored trail for every character without the opt-in."""
    anchor = sprite_emitter_trail_anchor(fig)
    if anchor is not None:
        ax, ay = anchor
        fig.trail.update(ax, ay, t.facing_left, is_moving, path_follow,
                          apply_offset=False)
    else:
        fig.trail.update(t.x, t.y, t.facing_left, is_moving, path_follow)


def sprite_emitter_trail_anchor(fig):
    """World-space (x, y) for the movement trail's anchor when the
    character's `sprite_emitter` block flags one source with
    `"trail_anchor": true` (e.g. pinning the trail to a weapon tip instead
    of the body). Picks that source's current-frame point farthest from the
    sprite centre — re-evaluated every tick, so the anchor tracks the line
    live as the pose/frame changes. Returns None for characters without the
    opt-in (unchanged default body-anchored trail). Purely cosmetic —
    identical in Solo & Battle."""
    cfg = sprite_emitter_cfg(fig)
    if cfg is None:
        return None
    idx = next((i for i, s in enumerate(cfg["sources"]) if s["trail_anchor"]),
               None)
    if idx is None:
        return None
    data = sprite_emitter_points(fig)
    if not data:
        return None
    entry = _current_sprite_entry(fig, data)
    if entry is None or not entry["pts"][idx]:
        return None
    cx, cy = entry["w"] / 2.0, entry["h"] / 2.0
    px, py = max(entry["pts"][idx],
                 key=lambda pt: (pt[0] - cx) ** 2 + (pt[1] - cy) ** 2)
    return _frame_point_to_world(fig, entry, px, py)


def update_character_bursts(fig):
    """Advance pending-delay timers (spawning bursts when due) and tick/cull
    live burst particles. Cheap no-op for figures with none of either. Call
    every tick for every figure — identical in Solo & Battle."""
    c = fig.combat
    if c.pending_bursts:
        still_pending = []
        for entry in c.pending_bursts:
            entry[0] -= 1
            if entry[0] <= 0:
                _spawn_burst_now(fig, entry[1], entry[2], entry[3])
            else:
                still_pending.append(entry)
        c.pending_bursts = still_pending
    if c.particle_bursts:
        alive = []
        for bp in c.particle_bursts:
            bp.update()
            if bp.alive:
                alive.append(bp)
        c.particle_bursts = alive


def update_homing_targets(projectiles, cx, cy):
    """Refresh the target reference for all HomingProjectiles this tick.

    Called once per tick by ProjectileSystem before advancing projectiles,
    so that homing bullets always track the current cursor / enemy position.
    """
    for proj in projectiles:
        if isinstance(proj, HomingProjectile):
            proj.target[0] = float(cx)
            proj.target[1] = float(cy)


# ---------------------------------------------------------------------------
# Legacy make_shot — used for non-runner modes (swordsman battle fire etc.)
# ---------------------------------------------------------------------------
def make_shot(fx, fy, cx, cy, color_rgb):
    """Fire a fan of bullets toward (cx, cy) per config.SHOT_ANGLES."""
    dx, dy = cx - fx, cy - fy
    d = (dx * dx + dy * dy) ** 0.5
    base = math.degrees(math.atan2(dy, dx)) if d > 0.01 else 0.0
    bullets = []
    for off in config.SHOT_ANGLES:
        a = math.radians(base + off)
        vx = math.cos(a) * config.PROJ_SPEED
        vy = math.sin(a) * config.PROJ_SPEED
        pr = Projectile(fx, fy, vx, vy, color_rgb,
                        trail_len=random.randint(3, 15))
        pr.style = "cone"
        bullets.append(pr)
    return bullets


def make_beam_shot(fx, fy, tx, ty, color_rgb):
    """Runner Beam Ultimate: BEAM_ROWS parallel long-tailed bolts, one volley.

    Fired EVERY tick while the ultimate is active.  Each bolt keeps a fixed
    straight heading once fired; the aim point (tx, ty) is recomputed by the
    caller each tick, so the beam sweeps as the shooter tracks its target.
    Rows are offset perpendicular to the firing axis by BEAM_ROW_SPACING.
    """
    dx, dy = tx - fx, ty - fy
    d = (dx * dx + dy * dy) ** 0.5
    if d > 0.01:
        ux, uy = dx / d, dy / d
    else:
        ux, uy = 1.0, 0.0
    px, py = -uy, ux                      # perpendicular (row offset axis)
    out = []
    half = (config.BEAM_ROWS - 1) / 2.0
    for i in range(config.BEAM_ROWS):
        off = (i - half) * config.BEAM_ROW_SPACING
        pr = Projectile(fx + px * off, fy + py * off,
                        ux * config.PROJ_SPEED, uy * config.PROJ_SPEED,
                        color_rgb, config.BEAM_TRAIL_LEN)
        pr.style = "beam"
        pr.max_age = config.BEAM_MAX_AGE
        out.append(pr)
    return out


# ---------------------------------------------------------------------------
# CrescentWave — an arc that flies toward a target, fades, and erases bullets
# ---------------------------------------------------------------------------
class CrescentWave:
    __slots__ = ("x", "y", "dir_x", "dir_y", "age", "color_rgb", "centre_angle_deg")

    def __init__(self, fig_x, fig_y, target_x, target_y, color_rgb):
        dx, dy = target_x - fig_x, target_y - fig_y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0.001:
            self.dir_x, self.dir_y = dx / dist, dy / dist
        else:
            self.dir_x, self.dir_y = 1.0, 0.0
        # Place arc centre directly ON the target. The arc spans around the
        # target using the perpendicular to the attack direction so the slash
        # wraps around the figure rather than extending away from it.
        self.x = float(target_x) - self.dir_x * 51
        self.y = float(target_y) - self.dir_y * 51
        self.age = 0
        self.color_rgb = color_rgb
        # Orient perpendicular to attack direction (rotate dir 90°)
        self.centre_angle_deg = angle_deg_qt(-self.dir_y, self.dir_x)

    @property
    def alive(self):
        return self.age < config.CRESCENT_LIFETIME

    def update(self):
        self.x += self.dir_x * config.CRESCENT_SPEED
        self.y += self.dir_y * config.CRESCENT_SPEED
        self.age += 1

    def check_bullet_erase(self, bx, by):
        """True if a bullet at (bx, by) lies on the arc's surface band + span."""
        r2 = config.CRESCENT_RADIUS
        margin = config.CRESCENT_WIDTH + 20.0
        ddx, ddy = bx - self.x, by - self.y
        dist = (ddx * ddx + ddy * ddy) ** 0.5
        if dist < 0.001 or not (r2 - margin <= dist <= r2 + margin):
            return False
        diff = angle_diff(angle_deg_qt(ddx, ddy), self.centre_angle_deg)
        return abs(diff) <= config.CRESCENT_SPAN / 2.0

    def draw(self, p, pen, lut=None, flow_off=0.0):
        if not self.alive:
            return
        segs = config.CRESCENT_SEGS
        r2 = config.CRESCENT_RADIUS
        half_span = config.CRESCENT_SPAN / 2.0
        start_deg = self.centre_angle_deg - half_span
        step = config.CRESCENT_SPAN / segs
        rect_x, rect_y = self.x - r2, self.y - r2
        diam = r2 * 2

        half_life = config.CRESCENT_LIFETIME * 0.85
        if self.age <= half_life:
            tip_t = self.age / half_life
            fade_alpha = 1.0
        else:
            tip_t = 1.0
            fade_alpha = 1.0 - (self.age - half_life) / (config.CRESCENT_LIFETIME - half_life)

        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setBrush(Qt.NoBrush)

        for i in range(segs):
            seg_t = (i + 0.5) / segs
            if seg_t > tip_t:
                continue
            dist_from_tip = tip_t - seg_t
            if dist_from_tip > config.CRESCENT_TAIL:
                continue
            tail_t = 1.0 - (dist_from_tip / config.CRESCENT_TAIL)
            lut_idx = int(((seg_t + flow_off) % 1.0) * 256) & LUT_MASK
            r, g, b = lut[lut_idx] if lut is not None else self.color_rgb
            alpha = int(255 * (tail_t ** 0.6) * fade_alpha)
            if alpha < 4:
                continue
            pen.setColor(QColor(r, g, b, alpha))
            pen.setWidthF(config.CRESCENT_WIDTH * (0.25 + 0.75 * tail_t))
            p.setPen(pen)
            a0 = start_deg + i * step
            path = QPainterPath()
            path.arcMoveTo(rect_x, rect_y, diam, diam, a0)
            path.arcTo(rect_x, rect_y, diam, diam, a0, step)
            p.drawPath(path)
            # White-hot inner edge — anime-blade brightness on the leading arc
            pen.setColor(QColor(255, 255, 255, int(alpha * 0.7)))
            pen.setWidthF(config.CRESCENT_WIDTH * 0.3 * (0.25 + 0.75 * tail_t))
            p.setPen(pen)
            p.drawPath(path)


# ---------------------------------------------------------------------------
# UltimateCrescent — swordsman ultimate: a large slow blade launched at 50% HP
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Petals — hovering defensive FX (see character JSON `petals` fx_layer, and
# tools/fx/fx_engine.js `fx_semantics.petals`). Works for ANY archetype
# (shooter or melee); a no-op for characters that don't define one. Runs every
# tick for every figure identically in Solo & Battle — in Solo there is
# simply nothing in world.enemy_projs to intercept, so petals just hover.
# ---------------------------------------------------------------------------
def _hex_rgb_safe(h, default):
    """Parse '#rrggbb' to an (r,g,b) int tuple; returns `default` on any
    missing/malformed input instead of raising."""
    if not h or not isinstance(h, str):
        return default
    h = h.lstrip("#")
    if len(h) != 6:
        return default
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return default


_PETAL_DEFAULTS = dict(count=3, hover_radius=46.0, orbit_speed_deg=70.0,
                        detect_range=150.0, approach_speed=320.0,
                        cooldown_ms=2500.0,
                        # Ellipse orbit: X / Y radii; 0 means "use hover_radius"
                        # so older character JSONs keep their circular orbit.
                        hover_radius_x=0.0, hover_radius_y=0.0,
                        # independent >= 0.5: each petal keeps its own target
                        # lock & cooldown and ignores every other petal;
                        # otherwise petals share one threat pool and re-target
                        # the nearest live threat each tick (historical
                        # behaviour). JSON true/false floats to 1.0/0.0.
                        independent=0.0,
                        # HP dealt on enemy-FIGURE contact (falls back to the
                        # layer's battle.damage when not set at layer top
                        # level). FX interception still deals no damage — it
                        # negates the incoming FX instead.
                        damage=1.0)
# Rendering-only (not floated like the mechanics keys above): resolved once
# in _petals_config from the layer's own size_min/size_max/c1, since Petal
# objects previously had no visual at all (see Petal.draw).
_PETAL_DEFAULT_RADIUS = 8.0
_PETAL_DEFAULT_RGB = (251, 238, 243)


class Petal:
    """One hovering defensive particle. Orbits its figure while idle — a
    circle of hover_radius px, or an ellipse when hover_radius_x /
    hover_radius_y are set (0 falls back to hover_radius). Detection is
    measured from the petal itself: when an enemy projectile OR an enemy
    figure enters detect_range of this petal, it breaks orbit and moves to
    intercept at approach_speed. Contact with a projectile negates it;
    contact with an enemy figure deals cfg["damage"] HP (delivered by
    update_petals through the one projectile/snapshot damage pipeline). Either
    contact consumes the petal into cooldown_ms, during which it is hidden;
    when cooldown ends it respawns like a new particle at a random angle on
    the orbit. With cfg["independent"] on,
    each petal keeps its own target lock & cooldown and ignores every other
    petal; otherwise petals share a threat pool and re-target the nearest
    live threat every tick (historical behaviour)."""
    __slots__ = ("x", "y", "phase", "state", "cooldown_ticks", "cfg",
                 "lock_kind", "lock_x", "lock_y")

    def __init__(self, phase, cfg):
        self.x = 0.0
        self.y = 0.0
        self.phase = phase
        self.state = "hover"   # 'hover' | 'intercept' | 'cooldown'
        self.cooldown_ticks = 0
        self.cfg = cfg
        # Independent-mode target lock. Threat tuples are rebuilt from the snapshot
        # every tick, so identity can't persist across ticks — the lock is
        # kept by POSITION continuity instead (re-acquire the same-kind
        # threat nearest to where the locked target was last tick).
        self.lock_kind = None   # None | 'proj' | 'fig'
        self.lock_x = 0.0
        self.lock_y = 0.0

    def update(self, anchor_x, anchor_y, threats):
        """Advance one tick. `threats` is a list of (x, y, kind, payload)
        entries — kind 'proj' (payload = the world.enemy_projs tuple) or
        'fig' (payload = partner-figure index). Returns a
        (kind, payload, contact_x, contact_y, dir_x, dir_y) tuple on the
        tick this petal makes contact with its target, else None."""
        cfg = self.cfg
        tick_s = config.TICK_MS / 1000.0
        if self.state == "cooldown":
            self.cooldown_ticks -= 1
            if self.cooldown_ticks <= 0:
                # Respawn as a brand-new particle: rejoin the rotating loop
                # at a RANDOM angle on the orbit, never at the spot where the
                # old petal was consumed. Position is set immediately so the
                # first visible frame is already on-orbit (no lerp from the
                # anchor point). Identical in Solo & Battle.
                self.state = "hover"
                self.phase = random.uniform(0.0, 2.0 * math.pi)
                rx = cfg.get("hover_radius_x") or cfg["hover_radius"]
                ry = cfg.get("hover_radius_y") or cfg["hover_radius"]
                self.x = anchor_x + math.cos(self.phase) * rx
                self.y = anchor_y + math.sin(self.phase) * ry
            else:
                self.x, self.y = anchor_x, anchor_y
            return None

        independent = cfg.get("independent", 0.0) >= 0.5
        det2 = cfg["detect_range"] ** 2
        target = None

        if independent and self.lock_kind is not None:
            # Own target lock: chase the same threat as last tick, found by
            # position continuity, even if a nearer threat exists and even if
            # other petals are chasing it too.
            best_d2 = det2
            for tx, ty, kind, payload in threats:
                if kind != self.lock_kind:
                    continue
                ddx, ddy = tx - self.lock_x, ty - self.lock_y
                d2 = ddx * ddx + ddy * ddy
                if d2 <= best_d2:
                    best_d2 = d2
                    target = (tx, ty, kind, payload)
            if target is None:
                self.lock_kind = None   # locked target is gone — drop it

        if target is None:
            # Acquire: nearest threat within detect_range of THIS petal
            # (detection has always been petal-centric; it now also covers
            # enemy figures, not just enemy FX).
            best_d2 = det2
            for tx, ty, kind, payload in threats:
                ddx, ddy = tx - self.x, ty - self.y
                d2 = ddx * ddx + ddy * ddy
                if d2 <= best_d2:
                    best_d2 = d2
                    target = (tx, ty, kind, payload)

        if target is not None:
            tx, ty, kind, payload = target
            if independent:
                self.lock_kind, self.lock_x, self.lock_y = kind, tx, ty
            self.state = "intercept"
            ddx, ddy = tx - self.x, ty - self.y
            dist = (ddx * ddx + ddy * ddy) ** 0.5
            step = cfg["approach_speed"] * tick_s
            if dist <= max(step, config.PETAL_CATCH_RADIUS):
                self.state = "cooldown"
                self.cooldown_ticks = max(1, int(cfg["cooldown_ms"] / config.TICK_MS))
                self.lock_kind = None
                if dist > 0.001:
                    dx, dy = ddx / dist, ddy / dist
                else:
                    dx, dy = 1.0, 0.0
                return (kind, payload, tx, ty, dx, dy)
            if dist > 0.001:
                self.x += ddx / dist * step
                self.y += ddy / dist * step
            return None

        self.state = "hover"
        self.phase += math.radians(cfg["orbit_speed_deg"]) * tick_s
        rx = cfg.get("hover_radius_x") or cfg["hover_radius"]
        ry = cfg.get("hover_radius_y") or cfg["hover_radius"]
        self.x = anchor_x + math.cos(self.phase) * rx
        self.y = anchor_y + math.sin(self.phase) * ry
        return None

    def draw(self, p):
        """Render as a small glowing dot in the character's own petal colour
        (previously Petal had no visual at all — logic-only). A petal on
        cooldown is fully hidden — it only becomes visible again when it
        respawns as a new particle at a random angle on the orbit."""
        if self.state == "cooldown":
            return
        r, g, b = self.cfg.get("_rgb", _PETAL_DEFAULT_RGB)
        radius = self.cfg.get("_radius", _PETAL_DEFAULT_RADIUS)
        pm, half = bullet_sprite(r, g, b, radius)
        p.drawPixmap(int(self.x) - half, int(self.y) - half, pm)


def _petals_config(fig):
    """First `petals` fx_layer found across this character's actions, merged
    over _PETAL_DEFAULTS; None for characters (incl. built-ins) without one.
    Cached on the mode instance since the character JSON doesn't change
    after load."""
    mode = fig.mode
    if hasattr(mode, "_petals_cfg"):
        return mode._petals_cfg
    cfg = None
    char = getattr(mode, "character", None)
    if char:
        for action in (char.get("actions") or {}).values():
            found = None
            for layer in (action.get("fx_layers") or []):
                if layer.get("type") == "petals":
                    found = layer
                    break
            if found:
                cfg = dict(_PETAL_DEFAULTS)
                for k in cfg:
                    if k in found:
                        try:
                            cfg[k] = float(found[k])
                        except (TypeError, ValueError):
                            pass
                if "damage" not in found:
                    # Older layers carry damage in the per-layer battle block
                    # (see mage.json); honour it as the figure-contact damage.
                    try:
                        cfg["damage"] = float(
                            (found.get("battle") or {}).get("damage",
                                                            cfg["damage"]))
                    except (TypeError, ValueError):
                        pass
                cfg["_rgb"] = _hex_rgb_safe(found.get("c1"), _PETAL_DEFAULT_RGB)
                try:
                    smin = float(found.get("size_min", _PETAL_DEFAULT_RADIUS))
                    smax = float(found.get("size_max", smin))
                    cfg["_radius"] = max(2.0, (smin + smax) / 2.0 / 2.0)
                except (TypeError, ValueError):
                    cfg["_radius"] = _PETAL_DEFAULT_RADIUS
                break
    mode._petals_cfg = cfg
    return cfg


def update_petals(fig, world):
    """Advance this figure's Petals by one tick. Petals intercept nearby
    entries in world.enemy_projs (negating them) AND chase enemy figures in
    world.partner_figures, dealing cfg damage on figure contact via an
    invisible short-lived Projectile pushed through the one damage pipeline
    (world.projectiles -> battle snapshot -> enemy_projs -> ai.battle_hit).
    Identical code path in Solo & Battle — Solo simply has nothing in
    enemy_projs or partner_figures, so petals just hover."""
    cfg = _petals_config(fig)
    if not cfg:
        return
    c = fig.combat
    if not c.petals_init:
        n = max(1, int(cfg.get("count", 3)))
        c.petals = [Petal((i / n) * 2 * math.pi, cfg) for i in range(n)]
        c.petals_init = True

    independent = cfg.get("independent", 0.0) >= 0.5
    figures = [(f[0], f[1]) for f in (world.partner_figures or [])]

    surviving = list(world.enemy_projs)
    # Independent petals evaluate a frozen snapshot of the tick's full threat
    # pool (ignoring what other petals consume mid-tick); coordinated petals
    # share `surviving`, which shrinks as threats are consumed.
    pool_projs = list(world.enemy_projs)
    # Independent-mode exclusivity: once a petal locks onto a threat this
    # tick, no other petal may also acquire/continue-chasing that SAME
    # threat until the first petal resolves it (hit or lost). Threat tuples
    # are rebuilt fresh from the snapshot every tick (no cross-tick identity),
    # but within a single tick the same objects are reused across all petals'
    # threat lists here, so id()/index identity is stable for one pass.
    # Generic — applies to any character's petals fx_layer with
    # independent >= 0.5, not just this one.
    claimed = set()

    def _threat_key(kind, payload):
        return (kind, id(payload) if kind == "proj" else payload)

    for pt in c.petals:
        projs = pool_projs if independent else surviving
        threats = [(t[0], t[1], "proj", t) for t in projs]
        threats += [(fx_, fy_, "fig", i)
                    for i, (fx_, fy_) in enumerate(figures)]
        if independent and claimed:
            threats = [th for th in threats
                       if _threat_key(th[2], th[3]) not in claimed]
        hit = pt.update(fig.x, fig.y, threats)
        if independent and pt.state == "intercept" and pt.lock_kind is not None:
            # Find which live threat this petal ended up locked onto (by the
            # position the lock now points at) so later petals this tick
            # see it excluded. A petal that made contact this same tick
            # clears its own lock inside Petal.update, so it never lands
            # here and doesn't need to reserve anything further.
            for th in threats:
                if th[2] != pt.lock_kind:
                    continue
                if abs(th[0] - pt.lock_x) < 0.01 and abs(th[1] - pt.lock_y) < 0.01:
                    claimed.add(_threat_key(th[2], th[3]))
                    break
        if hit is None:
            continue
        kind, payload, cx, cy, dx, dy = hit
        if kind == "proj":
            # Pierce (battle.attack.pierce): a piercing incoming shot ignores
            # petal interception entirely — the petal doesn't destroy it, and
            # it isn't removed from the surviving pool. Identical in Solo &
            # Battle, and generic to any character's petals fx_layer.
            if payload in surviving and not getattr(payload[8], "pierce", False):
                surviving.remove(payload)
                # Destroy the intercepted bullet at its source (tuple[8]
                # is the live Projectile on the enemy side).
                kill_projectile(payload[8])
                world.collision_dots.append([cx, cy, 0])
        else:
            # Enemy-figure contact: deliver this layer's damage through the
            # normal projectile/snapshot pipeline so the enemy side registers a
            # real battle_hit, exactly like any other damage source.
            pr = Projectile(cx, cy, dx * 2.0, dy * 2.0,
                            cfg.get("_rgb", _PETAL_DEFAULT_RGB), 3)
            pr.style = "invisible"
            pr.max_age = config.PETAL_TOUCH_PROJ_AGE
            pr.damage = float(cfg.get("damage", 1.0))
            world.projectiles.append(pr)
            world.collision_dots.append([cx, cy, 0])
    if len(surviving) != len(world.enemy_projs):
        world.enemy_projs = surviving


# ---------------------------------------------------------------------------
# HP-threshold stationary clones (see config.HPT_CLONE_* and
# json-character.md's `hp_threshold_clones`). Generic, data-driven mechanic:
# any character opts in via that top-level JSON block. Reuses the Petal
# class as-is for the clone's single orbiting sphere — Petal.update takes a
# plain anchor point rather than a Figure, so no changes to Petal were
# needed. Identical in Solo & Battle: Solo simply has no enemy figure for
# the sphere to reach and no incoming shots to be hit by, exactly like
# ambient petals already behave in Solo.
# ---------------------------------------------------------------------------
def hpt_clone_cfg(fig):
    """Per-figure HP-threshold-clone tuning from the character's top-level
    `hp_threshold_clones` block, or None. Cached on the mode instance like
    clone_cfg/blink_cfg/_petals_cfg."""
    mode = fig.mode
    if hasattr(mode, "_hpt_clone_cfg"):
        return mode._hpt_clone_cfg
    char = getattr(mode, "character", None)
    raw = char.get("hp_threshold_clones") if char else None
    if not isinstance(raw, dict) or not raw.get("thresholds"):
        mode._hpt_clone_cfg = None
        return None

    def _f(name, default):
        try:
            return float(raw.get(name, default))
        except (TypeError, ValueError):
            return default

    thresholds = []
    for t in raw["thresholds"]:
        try:
            pct = float(t.get("pct"))
        except (TypeError, ValueError, AttributeError):
            continue
        positions = [pos for pos in (t.get("positions") or [])
                     if pos in ("top_left", "top_right",
                               "bottom_left", "bottom_right")]
        if positions:
            thresholds.append((pct, positions))
    if not thresholds:
        mode._hpt_clone_cfg = None
        return None

    cfg = dict(
        thresholds=thresholds,
        clone_hp=int(_f("clone_hp", config.HPT_CLONE_HP_DEFAULT)),
        damage=_f("damage", config.HPT_CLONE_DAMAGE_DEFAULT),
        hover_radius=_f("hover_radius", config.HPT_CLONE_HOVER_RADIUS_DEFAULT),
        detect_range=_f("detect_range", config.HPT_CLONE_DETECT_RANGE_DEFAULT),
        orbit_speed_deg=_f("orbit_speed_deg", config.HPT_CLONE_ORBIT_SPEED_DEFAULT),
        approach_speed=_f("approach_speed", config.HPT_CLONE_APPROACH_SPEED_DEFAULT),
        cooldown_ms=_f("cooldown_ms", config.HPT_CLONE_COOLDOWN_MS_DEFAULT),
        corner_inset=_f("corner_inset_px", config.HPT_CLONE_CORNER_INSET_PX),
    )
    mode._hpt_clone_cfg = cfg
    return cfg


def _hpt_corner_xy(world, position, inset):
    """World-bounds corner position for a clone spawn, inset so the marker
    stays fully on-screen. Recomputed from the LIVE screen_w/h at spawn
    time, so it holds up at any resolution — identical in Solo & Battle."""
    sw, sh = world.screen_w, world.screen_h
    if position == "top_left":
        return inset, inset
    if position == "top_right":
        return sw - inset, inset
    if position == "bottom_left":
        return inset, sh - inset
    return sw - inset, sh - inset   # bottom_right


class HPTClone:
    """A stationary clone spawned when its owner's HP crosses a threshold
    (see hpt_clone_cfg). Never moves; attacks only through its own single
    orbiting Petal-style sphere anchored at its fixed position; dies the
    instant it takes any hit (hp defaults to 1). Lives and dies entirely
    within its owner's own SideState — never crosses the Solo/Battle
    one-tick information boundary."""
    __slots__ = ("x", "y", "hp", "damage", "sphere", "rgb")

    def __init__(self, x, y, cfg):
        self.x = float(x)
        self.y = float(y)
        self.hp = max(1, int(cfg["clone_hp"]))
        self.damage = float(cfg["damage"])
        self.rgb = config.HPT_CLONE_MARKER_RGB
        petal_cfg = dict(
            hover_radius=cfg["hover_radius"],
            hover_radius_x=0.0, hover_radius_y=0.0,
            orbit_speed_deg=cfg["orbit_speed_deg"],
            detect_range=cfg["detect_range"],
            approach_speed=cfg["approach_speed"],
            cooldown_ms=cfg["cooldown_ms"],
            damage=cfg["damage"],
            independent=0.0,
            _rgb=self.rgb,
            _radius=6.0,
        )
        self.sphere = Petal(random.uniform(0.0, 2.0 * math.pi), petal_cfg)

    @property
    def alive(self):
        return self.hp > 0

    def draw(self, p):
        r, g, b = self.rgb
        pm, half = bullet_sprite(r, g, b, config.HPT_CLONE_MARKER_RADIUS_PX)
        p.drawPixmap(int(self.x) - half, int(self.y) - half, pm)
        self.sphere.draw(p)


def check_hpt_clone_spawns(fig, world):
    """Once per tick per figure: has HP just crossed a NEW
    hp_threshold_clones threshold (one that hasn't fired before for this
    life)? If so, spawn a stationary clone at each corner listed for that
    threshold. Fires once ever per threshold — see json-character.md.
    Identical in Solo & Battle; corners come from the live screen bounds so
    they hold up at any resolution."""
    cfg = hpt_clone_cfg(fig)
    if cfg is None:
        return
    p = fig.personality
    if not p.max_hp:
        return
    hp_pct = 100.0 * p.hp / p.max_hp
    fired = fig.combat.hpt_fired
    for pct, positions in cfg["thresholds"]:
        if pct in fired or hp_pct > pct:
            continue
        fired.add(pct)
        for position in positions:
            cx, cy = _hpt_corner_xy(world, position, cfg["corner_inset"])
            world.clones.append(HPTClone(cx, cy, cfg))


def tick_hpt_clones(world):
    """Advance every clone this side owns: orbit/attack its sphere against
    the enemy figure (world.partner_figures) exactly like an ambient petal,
    and check whether any live incoming shot (world.enemy_projs — this also
    catches enemy petal-contact damage, which rides the same invisible-
    Projectile channel) lands on the clone's own body, killing it in one
    hit (consumes the shot the same way a figure-hit would, unless it
    pierces). Identical in Solo & Battle: Solo simply has no
    partner_figures/enemy_projs, so clones just orbit with nothing to hit
    or be hit by."""
    if not world.clones:
        return
    figures = [(f[0], f[1]) for f in (world.partner_figures or [])]
    hurt_rsq = config.HPT_CLONE_HURTBOX_RADIUS_PX ** 2
    surviving_projs = list(world.enemy_projs)
    survivors = []
    for clone in world.clones:
        threats = [(fx_, fy_, "fig", i) for i, (fx_, fy_) in enumerate(figures)]
        hit = clone.sphere.update(clone.x, clone.y, threats)
        if hit is not None:
            _kind, _payload, cx, cy, dx, dy = hit
            pr = Projectile(cx, cy, dx * 2.0, dy * 2.0, clone.rgb, 3)
            pr.style = "invisible"
            pr.max_age = config.PETAL_TOUCH_PROJ_AGE
            pr.damage = clone.damage
            world.projectiles.append(pr)
            world.collision_dots.append([cx, cy, 0])

        for tup in list(surviving_projs):
            ex, ey = tup[0], tup[1]
            ddx, ddy = ex - clone.x, ey - clone.y
            if ddx * ddx + ddy * ddy <= hurt_rsq:
                world.collision_dots.append([clone.x, clone.y, 0])
                clone.hp -= float(tup[7])
                if not getattr(tup[8], "pierce", False):
                    kill_projectile(tup[8])
                    surviving_projs.remove(tup)
                break
        if clone.hp > 0:
            survivors.append(clone)
    if len(surviving_projs) != len(world.enemy_projs):
        world.enemy_projs = surviving_projs
    if len(survivors) != len(world.clones):
        world.clones = survivors


# ---------------------------------------------------------------------------
# Damage-teleport (see config.DAMAGE_TELEPORT_* and json-character.md's
# `damage_teleport`). Generic, data-driven mechanic: any character opts in
# via that top-level JSON block. Identical in Solo & Battle — both route
# every hit through ai.apply_hp_damage, which calls check_damage_teleport
# right after applying the damage.
# ---------------------------------------------------------------------------
def damage_teleport_cfg(fig):
    """Per-figure damage-teleport tuning from the character's top-level
    `damage_teleport` block, or None. Cached on the mode instance like the
    other generic *_cfg parsers."""
    mode = fig.mode
    if hasattr(mode, "_damage_teleport_cfg"):
        return mode._damage_teleport_cfg
    char = getattr(mode, "character", None)
    raw = char.get("damage_teleport") if char else None
    if not isinstance(raw, dict):
        mode._damage_teleport_cfg = None
        return None

    def _f(name, default):
        try:
            v = float(raw.get(name, default))
        except (TypeError, ValueError):
            v = default
        return v

    cfg = dict(
        threshold_hp=_f("threshold_hp", config.DAMAGE_TELEPORT_THRESHOLD_HP_DEFAULT),
        distance_px=_f("distance_px", config.DAMAGE_TELEPORT_DISTANCE_PX_DEFAULT),
    )
    mode._damage_teleport_cfg = cfg
    return cfg


def check_damage_teleport(fig, amount):
    """Called right after a hit's damage is applied (from
    ai.apply_hp_damage). Accumulates `amount` into the figure's running
    damage-since-last-jump total; every time it reaches threshold_hp, warps
    the figure distance_px away from ITS OWN current position in a random
    direction (independent of the target), clamped to screen bounds by the
    normal check_walls() pass later this tick, then carries any remainder
    forward so a single big hit can trigger more than one jump. A pure
    position warp — does not set combat.acted — reusing the same
    blink_fx_pending departure/arrival crackle FX as the generic blink
    system. Identical in Solo & Battle."""
    cfg = damage_teleport_cfg(fig)
    if cfg is None or amount <= 0:
        return
    threshold = cfg["threshold_hp"]
    if threshold <= 0:
        return
    c = fig.combat
    t = fig.transform
    c.dmg_teleport_accum += amount
    while c.dmg_teleport_accum >= threshold:
        c.dmg_teleport_accum -= threshold
        ox, oy = t.x, t.y
        ang = random.uniform(0.0, 2.0 * math.pi)
        dist = cfg["distance_px"]
        new_x = ox + math.cos(ang) * dist
        new_y = oy + math.sin(ang) * dist
        margin = 20.0
        new_x = max(margin, min(fig.screen_w - margin, new_x))
        new_y = max(margin, min(fig.screen_h - margin, new_y))
        t.x, t.y = new_x, new_y
        c.blink_fx_pending.append((ox, oy, new_x, new_y))


# ---------------------------------------------------------------------------
# Generic ultimate-playback tuning — Swordsman's crescent-wave ultimate and
# Runner's beam ultimate are each a real, polished visual system; rather than
# inventing a third generic shape, ultimate_playback lets ANY character pick
# one of these two existing playbacks and override its numbers, the same
# field-by-field-override pattern as combo_cfg. Built-in figures (no
# .character) always get their own hardcoded defaults unchanged.
# ---------------------------------------------------------------------------
_ULTC_DEFAULTS = dict(
    radius=float(config.ULTC_RADIUS), span=float(config.ULTC_SPAN),
    speed=float(config.ULTC_SPEED), fade_dist=float(config.ULTC_FADE_DIST),
    width_outer=float(config.ULTC_WIDTH_OUTER),
    width_inner=float(config.ULTC_WIDTH_INNER), segs=int(config.ULTC_SEGS),
    lifetime=int(config.ULTC_LIFETIME),
    second_delay_ticks=int(config.ULTC_SECOND_DELAY_TICKS),
    hit_figure_dist=float(config.ULTC_HIT_FIGURE_DIST),
    cross_angle=float(config.ULTC_CROSS_ANGLE),
    thresholds=list(config.ULTC_THRESHOLDS),
)
_BEAM_DEFAULTS = dict(
    rows=int(config.BEAM_ROWS), row_spacing=float(config.BEAM_ROW_SPACING),
    trail_len=int(config.BEAM_TRAIL_LEN), max_age=int(config.BEAM_MAX_AGE),
    speed_mult=1.0,
)


def ultimate_style(fig):
    """'crescent' | 'beam' | 'none' for this figure's ultimate playback.
    Built-ins keep their historical automatic behaviour (Swordsman ->
    crescent via uses_melee(), Runner -> beam via mode.key == 'runner',
    both unconditional and untouched by this function). For a JSON
    character, reads ultimate_playback.style, defaulting to 'crescent' for
    melee archetypes and 'beam' for shooter archetypes — matching what the
    HP-threshold triggers in ai.py/systems.py already fire for each kind —
    so an unconfigured JSON character's ultimate window is never silent."""
    char = getattr(fig.mode, "character", None)
    if not char:
        return "crescent" if fig.mode.uses_melee() else "beam"
    style = (char.get("ultimate_playback") or {}).get("style")
    if style in ("crescent", "beam", "blinkstorm", "vanish_cut", "none"):
        return style
    return "crescent" if fig.mode.uses_melee() else "beam"


def ultc_cfg(fig):
    """Per-figure crescent-ultimate tuning dict — see module comment above."""
    mode = fig.mode
    if hasattr(mode, "_ultc_cfg"):
        return mode._ultc_cfg
    cc = dict(_ULTC_DEFAULTS)
    char = getattr(mode, "character", None)
    if char:
        raw = char.get("ultimate_playback") or {}
        for k in cc:
            if k in raw:
                try:
                    cc[k] = (list(raw[k]) if isinstance(cc[k], list)
                             else type(cc[k])(raw[k]))
                except (TypeError, ValueError):
                    pass
    mode._ultc_cfg = cc
    return cc


def beam_cfg(fig):
    """Per-figure beam-ultimate tuning dict — see module comment above."""
    mode = fig.mode
    if hasattr(mode, "_beam_cfg"):
        return mode._beam_cfg
    bc = dict(_BEAM_DEFAULTS)
    char = getattr(mode, "character", None)
    if char:
        raw = char.get("ultimate_playback") or {}
        for k in bc:
            if k in raw:
                try:
                    bc[k] = type(bc[k])(raw[k])
                except (TypeError, ValueError):
                    pass
    mode._beam_cfg = bc
    return bc


def make_beam_shot_cfg(fig, tx, ty):
    """Same volley as make_beam_shot, but rows/spacing/trail/age/speed come
    from beam_cfg(fig) instead of fixed config.BEAM_* constants — lets any
    'beam'-style character have a different beam feel from Runner's."""
    bc = beam_cfg(fig)
    fx, fy = fig.x, fig.y
    color_rgb = fig.lut[128]
    dx, dy = tx - fx, ty - fy
    d = (dx * dx + dy * dy) ** 0.5
    if d > 0.01:
        ux, uy = dx / d, dy / d
    else:
        ux, uy = 1.0, 0.0
    px, py = -uy, ux
    speed = config.PROJ_SPEED * bc['speed_mult']
    out = []
    rows = max(1, bc['rows'])
    half = (rows - 1) / 2.0
    for i in range(rows):
        off = (i - half) * bc['row_spacing']
        pr = Projectile(fx + px * off, fy + py * off,
                        ux * speed, uy * speed, color_rgb, bc['trail_len'])
        pr.style = "beam"
        pr.max_age = bc['max_age']
        out.append(pr)
    return out


class UltimateCrescent:
    """A large crescent blade that travels forward at ~100 px/s.

    Spawns AT the target position.  The two blades are rotated ±ULTC_CROSS_ANGLE
    so their tips cross like an X in front of the target.

    Visual:  dark filled body (thick arc) + bright blue rim (thin inner arc).
    Reveal:  sweeps in from bottom of the arc to top over the first 10 ticks.
    Fade:    after ULTC_FADE_DIST px of travel, fades from bottom to top.
    Damage:  any enemy figure within ULTC_HIT_FIGURE_DIST of the arc surface
             takes 1 HP per tick (checked by CollisionSystem).
    Bullets: destroys any bullet whose centre lies within the blade band.
    """

    __slots__ = ("x", "y", "dir_x", "dir_y", "age", "dist_travelled",
                 "centre_angle_deg", "reveal_t", "cfg")

    def __init__(self, fig_x, fig_y, target_x, target_y, cross_angle_deg=0.0,
                 cfg=None):
        self.cfg = cfg if cfg is not None else _ULTC_DEFAULTS
        dx, dy = target_x - fig_x, target_y - fig_y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 0.001:
            self.dir_x, self.dir_y = dx / dist, dy / dist
        else:
            self.dir_x, self.dir_y = 1.0, 0.0

        # Spawn ULTC_RADIUS behind the swordsman so the front edge of the arc
        # (facing the travel direction) sits on the figure at launch.
        self.x = float(fig_x) - self.dir_x * self.cfg['radius']
        self.y = float(fig_y) - self.dir_y * self.cfg['radius']
        self.age = 0
        self.dist_travelled = 0.0

        # Arc orientation = travel direction PLUS the cross-angle rotation.
        # This tilts each blade's concave opening so the two blades cross like
        # an X at the target point.
        base_angle = angle_deg_qt(self.dir_x, self.dir_y)
        self.centre_angle_deg = base_angle + cross_angle_deg

        self.reveal_t = 0.0   # 0 → 1 over ~10 ticks (bottom-to-top materialise)

    @property
    def alive(self):
        return self.age < self.cfg['lifetime']

    def update(self):
        self.x += self.dir_x * self.cfg['speed']
        self.y += self.dir_y * self.cfg['speed']
        self.dist_travelled += self.cfg['speed']
        self.age += 1
        if self.reveal_t < 1.0:
            self.reveal_t = min(1.0, self.reveal_t + 0.1)

    def check_bullet_erase(self, bx, by):
        """True if bullet (bx, by) lies within the blade's arc band."""
        r = self.cfg['radius']
        margin = self.cfg['width_outer'] * 0.5 + 10.0
        ddx, ddy = bx - self.x, by - self.y
        d = (ddx * ddx + ddy * ddy) ** 0.5
        if d < 0.001 or not (r - margin <= d <= r + margin):
            return False
        diff = angle_diff(angle_deg_qt(ddx, ddy), self.centre_angle_deg)
        return abs(diff) <= self.cfg['span'] / 2.0

    def check_figure_hit(self, fx, fy):
        """True if figure (fx, fy) is within the blade's damage band."""
        r = self.cfg['radius']
        margin = self.cfg['hit_figure_dist']
        ddx, ddy = fx - self.x, fy - self.y
        d = (ddx * ddx + ddy * ddy) ** 0.5
        if d < 0.001 or not (r - margin <= d <= r + margin):
            return False
        diff = angle_diff(angle_deg_qt(ddx, ddy), self.centre_angle_deg)
        return abs(diff) <= self.cfg['span'] / 2.0

    def draw(self, p, pen):
        """Draw the blade: dark filled body + bright blue rim, with reveal/fade."""
        if not self.alive:
            return

        r = self.cfg['radius']
        half_span = self.cfg['span'] / 2.0
        segs = self.cfg['segs']

        # Fade: after ULTC_FADE_DIST px fades linearly over 200 px more
        if self.dist_travelled > self.cfg['fade_dist']:
            excess = self.dist_travelled - self.cfg['fade_dist']
            fade_alpha = max(0.0, 1.0 - excess / 200.0)
        else:
            fade_alpha = 1.0

        if fade_alpha <= 0.0:
            return

        # centre_angle_deg already includes the cross rotation set at init.
        start_deg = self.centre_angle_deg - half_span
        step = self.cfg['span'] / segs
        rect_x, rect_y = self.x - r, self.y - r
        diam = r * 2

        # Reveal: grow from seg 0 → segs over the first 10 ticks
        reveal_segs = int(self.reveal_t * segs)

        # Fade bottom-to-top: higher-index segments (lower on screen) fade first
        if self.dist_travelled > self.cfg['fade_dist']:
            excess = self.dist_travelled - self.cfg['fade_dist']
            fade_segs_from_bottom = int((excess / 200.0) * segs)
        else:
            fade_segs_from_bottom = 0

        p.setBrush(Qt.NoBrush)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)

        for i in range(segs):
            if i >= reveal_segs:
                continue
            visible_from_bottom = segs - 1 - i
            if visible_from_bottom < fade_segs_from_bottom:
                continue

            seg_t = (i + 0.5) / segs
            taper = (1.0 - abs(seg_t - 0.5) * 2.0) ** 0.5  # thick mid, thin tips

            a0 = start_deg + i * step

            # Pass 1: dark body
            body_w = self.cfg['width_outer'] * (0.4 + 0.6 * taper)
            pen.setWidthF(body_w)
            pen.setColor(QColor(8, 8, 12, int(215 * fade_alpha)))
            p.setPen(pen)
            path = QPainterPath()
            path.arcMoveTo(rect_x, rect_y, diam, diam, a0)
            path.arcTo(rect_x, rect_y, diam, diam, a0, step)
            p.drawPath(path)

            # Pass 2: bright blue rim offset outward
            rim_off = self.cfg['width_outer'] * 0.3
            rr = r + rim_off
            rim_w = self.cfg['width_inner'] * (0.3 + 0.7 * taper)
            pen.setWidthF(rim_w)
            pen.setColor(QColor(30, 120, 200, int(220 * fade_alpha)))
            p.setPen(pen)
            rr_rect_x, rr_rect_y = self.x - rr, self.y - rr
            rr_diam = rr * 2
            rim_path = QPainterPath()
            rim_path.arcMoveTo(rr_rect_x, rr_rect_y, rr_diam, rr_diam, a0)
            rim_path.arcTo(rr_rect_x, rr_rect_y, rr_diam, rr_diam, a0, step)
            p.drawPath(rim_path)


def fire_sword_ultimate(fig, target_x, target_y):
    """Spawn blade 1 (+cross angle) at the target; arm blade 2 (-cross angle)
    to fire second_delay_ticks later.  Both travel in the same forward
    direction but their arcs are rotated ± so the tips cross like an X."""
    c = fig.combat
    cfg = ultc_cfg(fig)
    ca = cfg['cross_angle']
    # Blade 1: rotated +cross_angle
    uc1 = UltimateCrescent(fig.x, fig.y, target_x, target_y,
                           cross_angle_deg=+ca, cfg=cfg)
    c.ult_crescents.append(uc1)
    c.hitstop_request = True   # ultimate launch = big hit -> world freeze
    # Store target for the delayed 2nd blade
    c.ult_crescent_pending = cfg['second_delay_ticks']
    # Stash target so tick_ult_crescents can use it (reuse arc_center fields)
    c.arc_center_x = float(target_x)
    c.arc_center_y = float(target_y)


def tick_ult_crescents(fig, target_x, target_y):
    """Advance ult_crescents list and fire the delayed 2nd shot when due.
    Called from advance_combat every tick for melee figures."""
    c = fig.combat
    cfg = ultc_cfg(fig)
    # Tick the 2nd-shot delay counter; use stored arc_center as fixed target
    if c.ult_crescent_pending > 0:
        c.ult_crescent_pending -= 1
        if c.ult_crescent_pending == 0:
            ca = cfg['cross_angle']
            tx2, ty2 = c.arc_center_x, c.arc_center_y
            uc2 = UltimateCrescent(fig.x, fig.y, tx2, ty2,
                                   cross_angle_deg=-ca, cfg=cfg)
            c.ult_crescents.append(uc2)
    # Advance + cull
    if c.ult_crescents:
        live = []
        for uc in c.ult_crescents:
            uc.update()
            if uc.alive:
                live.append(uc)
        c.ult_crescents = live


# ---------------------------------------------------------------------------
# Swordsman attack FSM — operates on a Figure's components.
# Returns True if it consumed the tick (motion should be skipped this tick),
# False if the figure should still take a normal movement step (faithful to the
# original, which does one chase step on the dash-trigger tick).
# ---------------------------------------------------------------------------

def tick_parry_cooldown(fig):
    """Tick parry cooldown and stance timers every frame (regardless of other state)."""
    c = fig.combat
    if c.parry_cooldown_ticks > 0:
        c.parry_cooldown_ticks -= 1
    if c.parry_stance_ticks > 0:
        c.parry_stance_ticks -= 1
        if c.parry_stance_ticks <= 0:
            c.parrying = False


def trigger_parry(fig):
    """Arm the parry stance if the cooldown has expired. Returns True if parry was triggered."""
    c = fig.combat
    if c.parry_cooldown_ticks > 0:
        return False
    c.parrying = True
    c.parry_stance_ticks = config.PARRY_STANCE_TICKS
    c.parry_cooldown_ticks = config.PARRY_COOLDOWN_TICKS
    # Play the slash animation to show the parry deflect
    c.slash_phase = c.slash_idx = c.slash_tick = 0
    return True


# ---------------------------------------------------------------------------
# Generic combo tuning — the melee dash/arc combo FSM below (advance_combat)
# already runs for ANY fig.mode.uses_melee() figure, JSON or built-in; the
# only thing that was Swordsman-specific was that its numbers came straight
# from module constants. combo_cfg() lets a character's own `combo` JSON
# block override any of those numbers field-by-field — missing/invalid
# fields fall back individually to Swordsman's own values, so a built-in
# figure (no .character) or a JSON character with no `combo` block behaves
# byte-identically to today. Cached on the mode instance (JSON never changes
# after load). Identical in Solo & Battle — advance_combat runs the same
# call site in both.
# ---------------------------------------------------------------------------
_COMBO_DEFAULTS = dict(
    max_hits=int(config.ATTACK_STRING_MAX_HITS),
    cooldown_ticks=int(config.ATTACK_STRING_COOLDOWN_TICKS),
    followup_lock_ticks=int(config.FOLLOWUP_TYPE_LOCK_TICKS),
    dash_speed_mult=float(config.SLASH_SPEED_MUL),
    hit_radius=float(config.SLASH_HIT_RADIUS),
    arc_orbit_angle_deg=float(config.ARC_ORBIT_ANGLE_DEG),
    arc_approach_sweep_deg=float(config.ARC_APPROACH_SWEEP_DEG),
    arc_recoil_px=float(config.ARC_RECOIL_PX),
    arc_recoil_ticks=int(config.ARC_RECOIL_TICKS),
    arc_repo_ticks=int(config.ARC_REPO_TICKS),
    arc_approach_ticks=int(config.ARC_APPROACH_TICKS),
    combo_travel_ticks_min=int(config.COMBO_TRAVEL_TICKS_MIN),
    combo_travel_ticks_max=int(config.COMBO_TRAVEL_TICKS_MAX),
)


def combo_cfg(fig):
    """Per-figure combo tuning dict — see module comment above."""
    mode = fig.mode
    if hasattr(mode, "_combo_cfg"):
        return mode._combo_cfg
    cc = dict(_COMBO_DEFAULTS)
    char = getattr(mode, "character", None)
    if char:
        raw = char.get("combo") or {}
        for k in cc:
            if k in raw:
                try:
                    cc[k] = type(cc[k])(raw[k])
                except (TypeError, ValueError):
                    pass
    mode._combo_cfg = cc
    return cc


_BLINK_DEFAULTS = dict(
    combo=True,
    combo_cooldown_ticks=int(config.BLINK_COMBO_COOLDOWN_TICKS),
    approach=True,
    approach_range_px=float(config.BLINK_APPROACH_RANGE_PX),
    approach_trigger_px=float(config.BLINK_APPROACH_TRIGGER_PX),
    approach_cooldown_ticks=int(config.BLINK_APPROACH_COOLDOWN_TICKS),
    defend=True,
    storm_strikes=int(config.BLINK_STORM_STRIKES),
    storm_interval_ticks=int(config.BLINK_STORM_INTERVAL_TICKS),
    storm_radius_px=float(config.BLINK_STORM_RADIUS_PX),
    # Optional hex override for the crackle/zig-zag bolt spark colour spawned
    # on every warp (combo teleport, approach-blink, blinkstorm strikes —
    # all route through blink_warp). Empty string = use the character's own
    # palette (fig.lut[200]), preserving old behaviour for any character
    # that doesn't set it.
    bolt_color="",
)


def blink_cfg(fig):
    """Per-figure blink tuning dict, or None when the character has no
    `blink` block (all built-ins).  Cached on the mode instance like
    combo_cfg/ultc_cfg.  Presence of the block enables the system; the
    booleans inside gate each hook (combo / approach / defend)."""
    mode = fig.mode
    if hasattr(mode, "_blink_cfg"):
        return mode._blink_cfg
    char = getattr(mode, "character", None)
    raw = char.get("blink") if char else None
    if not isinstance(raw, dict):
        mode._blink_cfg = None
        return None
    bl = dict(_BLINK_DEFAULTS)
    for k in bl:
        if k in raw:
            try:
                bl[k] = type(bl[k])(raw[k])
            except (TypeError, ValueError):
                pass
    mode._blink_cfg = bl
    return bl


def clone_cfg(fig):
    """Per-figure clone tuning from the character's top-level
    special_ability block (wizard preset "clone"), or None.  Cached on the
    mode instance like blink_cfg.  Ticks derived from ms at load."""
    mode = fig.mode
    if hasattr(mode, "_clone_cfg"):
        return mode._clone_cfg
    char = getattr(mode, "character", None)
    sa = char.get("special_ability") if char else None
    if not (isinstance(sa, dict) and sa.get("preset") == "clone"):
        mode._clone_cfg = None
        return None
    params = sa.get("params") or {}

    def _ms(name, default_ms):
        try:
            v = float(params.get(name, default_ms))
        except (TypeError, ValueError):
            v = default_ms
        return max(1, int(round(v / config.TICK_MS)))

    try:
        dmg = float(params.get("damage", 1))
    except (TypeError, ValueError):
        dmg = 1.0
    mode._clone_cfg = dict(
        duration_ticks=_ms("duration_ms", config.CLONE_DURATION_MS_DEFAULT),
        cooldown_ticks=_ms("cooldown_ms", config.CLONE_COOLDOWN_MS_DEFAULT),
        damage=dmg,
    )
    return mode._clone_cfg


class CloneEffect:
    """Autonomous ghost of its owner: chases the owner's live target and
    strikes on contact.  Damage rides invisible Projectiles through the
    standard fire -> world.projectiles -> enemy snapshot channel, so battle
    HP/parry/petals all interact normally and nothing new crosses IPC.
    Ticked by CombatSystem during the owner's side pass; drawn ghosted in
    Figure.draw.  In Solo the target is the cursor — same chase/strike
    behaviour, simply nothing with HP to damage."""

    __slots__ = ("x", "y", "ticks_left", "duration", "speed", "damage",
                 "facing_left", "run_idx", "anim_tick", "attack_cd", "moving")

    def __init__(self, x, y, duration_ticks, speed, damage):
        self.x, self.y = float(x), float(y)
        self.ticks_left = int(duration_ticks)
        self.duration = max(1, int(duration_ticks))
        self.speed = float(speed)
        self.damage = float(damage)
        self.facing_left = False
        self.run_idx = 0
        self.anim_tick = 0
        self.attack_cd = 0
        self.moving = False

    def tick(self, tx, ty):
        """Advance one tick toward (tx, ty).  Returns a list of new
        Projectiles to append to the owner side's world.projectiles
        (empty most ticks), or None when the clone has expired."""
        self.ticks_left -= 1
        if self.ticks_left <= 0:
            return None
        out = []
        dx, dy = tx - self.x, ty - self.y
        dist = (dx * dx + dy * dy) ** 0.5
        self.facing_left = dx < 0
        if dist > config.CLONE_STRIKE_RADIUS_PX:
            inv = 1.0 / max(dist, 0.001)
            self.x += dx * inv * self.speed
            self.y += dy * inv * self.speed
            self.moving = True
        else:
            self.moving = False
        if self.attack_cd > 0:
            self.attack_cd -= 1
        elif dist <= config.CLONE_STRIKE_RADIUS_PX:
            # Contact strike: short-lived invisible bullet at the target.
            a = math.atan2(dy, dx)
            vx = math.cos(a) * config.PROJ_SPEED
            vy = math.sin(a) * config.PROJ_SPEED
            pr = Projectile(self.x, self.y, vx, vy, (57, 215, 255), 3)
            pr.style = "invisible"
            pr.damage = self.damage
            # Die shortly past strike range so it can't snipe across screen.
            pr.max_age = max(2, int(config.CLONE_STRIKE_RADIUS_PX * 1.4
                                    / max(config.PROJ_SPEED, 0.001)))
            out.append(pr)
            self.attack_cd = config.CLONE_ATTACK_INTERVAL_TICKS
        self.anim_tick += 1
        if self.anim_tick >= 5:
            self.anim_tick = 0
            self.run_idx += 1
        return out

    def frame(self, bundle):
        """Current ghost frame from the owner's FrameBundle."""
        if self.moving and bundle.run:
            fs = bundle.run_flipped if self.facing_left else bundle.run
            return fs[self.run_idx % len(fs)]
        if bundle.idle:
            fs = bundle.idle_flipped if self.facing_left else bundle.idle
            return fs[self.run_idx % len(fs)]
        return None

    def draw(self, p, bundle):
        fr = self.frame(bundle)
        if fr is None:
            return
        # Fade out over the last quarter of its life.
        fade = min(1.0, self.ticks_left / max(1.0, 0.25 * self.duration))
        p.setOpacity((config.CLONE_ALPHA / 255.0) * fade)
        p.drawPixmap(int(self.x) - fr.width() // 2,
                     int(self.y) - fr.height() // 2, fr)
        p.setOpacity(1.0)


def spawn_clone(fig):
    """Spawn a clone at the figure's current position if the character has
    the clone preset and the cooldown is clear.  Called from the dodge-arm
    sites in MotionSystem — the clone is left at the departure point."""
    cfg = clone_cfg(fig)
    c = fig.combat
    if cfg is None or c.clone_cd > 0:
        return
    speed = fig.motion.follow_speed * config.CLONE_SPEED_FACTOR
    c.clones.append(CloneEffect(fig.transform.x, fig.transform.y,
                                cfg['duration_ticks'], speed, cfg['damage']))
    c.clone_cd = cfg['cooldown_ticks']
    c.blink_fx_pending.append((fig.transform.x, fig.transform.y,
                               fig.transform.x, fig.transform.y))


def dodge_style_cfg(fig):
    """Top-level `dodge_style` JSON opt-in. Both generic melee dodge
    triggers in systems.py (incoming-projectile sidestep, incoming-dash
    counter) default to a multi-tick physical dodge_dashing move; a
    character can opt into "blink" so either trigger instead resolves as
    one instant teleport (see dodge_blink). Returns the raw string or None
    — no branching beyond this single check, and no other character's
    behaviour changes."""
    char = getattr(fig.mode, "character", None)
    if not char:
        return None
    style = char.get("dodge_style")
    return style if style in ("blink",) else None


def dodge_blink(fig, dest_x, dest_y, counter_target=None):
    """Instant blink-dodge: resolves a melee dodge trigger as a single
    teleport to (dest_x, dest_y) instead of the default multi-tick
    physical dodge_dashing move, reusing blink_warp's own departure/arrival
    afterimage ghosts for the visual trail (no clone spawn needed).

    counter_target, if given as (tx, ty), mirrors the default dodge's
    post-arrival behaviour for a counter-dash vs an incoming dashing enemy:
    if still out of melee range on arrival, arms an immediate retaliation
    dash-in at that target so a blink-style counter-dash still finishes the
    same way a physical one would. Purely a delivery-mechanism swap;
    identical in Solo & Battle since both trigger sites already are."""
    c = fig.combat
    if c.dashing:
        c.dashing = c.rebounding = False
    blink_warp(fig, dest_x, dest_y)
    c.dodge_dashing = False
    c.dodge_counter = False
    if counter_target is not None:
        cc = combo_cfg(fig)
        t = fig.transform
        tx, ty = counter_target
        ddx, ddy = tx - t.x, ty - t.y
        ddist = (ddx * ddx + ddy * ddy) ** 0.5
        if ddist > cc['hit_radius']:
            inv = 1.0 / max(ddist, 0.001)
            lspd = fig.motion.speed * cc['dash_speed_mult']
            c.slash_vx = ddx * inv * lspd
            c.slash_vy = ddy * inv * lspd
            c.slash_dist_budget = ddist * 4.0
            c.dashing = True
            c.rebounding = False


def blink_warp(fig, nx, ny):
    """Pure position warp with departure/arrival afterimages + queued spark
    FX (drained by CombatSystem into world.sparks).  Clamps to screen
    bounds.  Never touches FSM flags — callers own their own state."""
    t = fig.transform
    margin = 20.0
    nx = max(margin, min(fig.screen_w - margin, nx))
    ny = max(margin, min(fig.screen_h - margin, ny))
    spawn_afterimage(fig)
    fig.combat.blink_fx_pending.append((t.x, t.y, nx, ny))
    t.x = nx
    t.y = ny
    spawn_afterimage(fig)
    # Rebase the run trail so no ribbon bridges the discontinuity —
    # the jagged bolt sparks (CombatSystem drain) carry the visual.
    fig.trail.clear()


def tick_blinkstorm(fig, target_x, target_y):
    """Blinkstorm ultimate: N rapid teleport strikes on a ring around the
    live target.  Each strike warps the figure adjacent to the target,
    queues impact FX and cross-side knockback (delivered by
    World.refresh_battle); HP damage flows through the existing
    body-collision path on the enemy side's own pass — identical in Solo
    and Battle.  Returns True while the storm is consuming the figure."""
    c = fig.combat
    if c.blinkstorm_strikes_left <= 0:
        return False
    bl = blink_cfg(fig)
    if bl is None:
        c.blinkstorm_strikes_left = 0
        return False
    if c.blinkstorm_tick > 0:
        c.blinkstorm_tick -= 1
        return True
    # Strike: warp to the next ring position around the live target.
    c.blinkstorm_angle += math.radians(137.5)   # golden-angle rotation
    r = bl['storm_radius_px']
    nx = target_x + math.cos(c.blinkstorm_angle) * r
    ny = target_y + math.sin(c.blinkstorm_angle) * r
    blink_warp(fig, nx, ny)
    fig.face(target_x + (target_x - nx), target_y + (target_y - ny))
    # Impact FX at the target + knockback away from the strike point.
    c.impact_fx_pending.append((target_x, target_y))
    ddx, ddy = target_x - fig.transform.x, target_y - fig.transform.y
    ddist = (ddx * ddx + ddy * ddy) ** 0.5
    kb_spd = config.DASH_HIT_KNOCKBACK_PX * (1.0 - config.BOUNCE_FRICTION)
    if ddist > 0.001:
        c.hit_vx = (ddx / ddist) * kb_spd
        c.hit_vy = (ddy / ddist) * kb_spd
        c.hit_pending = True
    c.blinkstorm_strikes_left -= 1
    if c.blinkstorm_strikes_left <= 0:
        c.hitstop_request = True   # storm finisher freezes the world
    else:
        c.blinkstorm_tick = bl['storm_interval_ticks']
    return True




# ---------------------------------------------------------------------------
# Generic proximity-reaction system (JSON `reaction` block) — the "Counter"
# fantasy.  When an enemy body enters radius_px, roll counter_chance:
#   COUNTER — open the deflect window (trigger_parry, the generalized parry)
#             and arm an immediate retaliation slash at the enemy;
#   DODGE   — blink_warp to blink_behind_px PAST the enemy along the
#             approach line, primed to punish.
# Both outcomes share ONE cooldown (cooldown_ms).  Each activation may add
# one ultimate charge (charge_ultimate) for charge-based ultimates such as
# `vanish_cut`.  Data-driven, opt-in: any character can author the block.
# Solo target = cursor, Battle target = nearest enemy — the same sources
# every other proximity system uses, so Solo/Battle parity is automatic.
# ---------------------------------------------------------------------------

_REACTION_DEFAULTS = dict(
    radius_px=50.0,
    cooldown_ms=200.0,
    counter_chance=0.5,
    blink_behind_px=60.0,
    charge_ultimate=True,
)


def reaction_cfg(fig):
    """Per-figure reaction tuning dict, or None when the character has no
    `reaction` block.  Cached on the mode instance like blink_cfg."""
    mode = fig.mode
    if hasattr(mode, "_reaction_cfg"):
        return mode._reaction_cfg
    char = getattr(mode, "character", None)
    raw = char.get("reaction") if char else None
    if not isinstance(raw, dict):
        mode._reaction_cfg = None
        return None
    rc = dict(_REACTION_DEFAULTS)
    for k in rc:
        if k in raw:
            try:
                rc[k] = type(rc[k])(raw[k])
            except (TypeError, ValueError):
                pass
    rc["cooldown_ticks"] = max(1, int(round(rc["cooldown_ms"]
                                            / config.TICK_MS)))
    mode._reaction_cfg = rc
    return rc


# ---------------------------------------------------------------------------
# Generic vanish-cut ultimate (ultimate_playback.style == "vanish_cut") —
# the anime flash-cut: the figure vanishes (freeze frame), a blitz of
# crossing slashes strikes the target, a crossed finisher pair lands the
# "split in half" read, and the figure reappears PAST the target facing the
# walk-through direction.  Charge-based: launched by check_reaction when
# ult_charges reaches charges_required (charges come from reactions).
# Damage rides invisible Projectiles through the standard
# fire -> world.projectiles -> enemy snapshot channel (queued on
# vc_shots_pending, drained by CombatSystem), so HP/parry/petals interact
# normally and nothing new crosses IPC.  Identical in Solo & Battle.
# ---------------------------------------------------------------------------

_VC_DEFAULTS = dict(
    charges_required=5,
    trigger_range_px=100000.0,
    hits=5,
    hit_damage=9.0,
    hit_interval_ms=96.0,
    vanish_ms=400.0,
    impact_ms=250.0,
    reappear_past_px=70.0,
)


def vanish_cut_cfg(fig):
    """Per-figure vanish-cut tuning from ultimate_playback, or None unless
    the character's ultimate_playback.style is 'vanish_cut'.  Cached on the
    mode instance like ultc_cfg/beam_cfg."""
    mode = fig.mode
    if hasattr(mode, "_vc_cfg"):
        return mode._vc_cfg
    char = getattr(mode, "character", None)
    raw = (char.get("ultimate_playback") or {}) if char else {}
    if raw.get("style") != "vanish_cut":
        mode._vc_cfg = None
        return None
    vc = dict(_VC_DEFAULTS)
    for k in vc:
        if k in raw:
            try:
                vc[k] = type(vc[k])(raw[k])
            except (TypeError, ValueError):
                pass
    vc["interval_ticks"] = max(1, int(round(vc["hit_interval_ms"]
                                            / config.TICK_MS)))
    vc["vanish_ticks"] = max(1, int(round(vc["vanish_ms"] / config.TICK_MS)))
    vc["impact_ticks"] = max(1, int(round(vc["impact_ms"] / config.TICK_MS)))
    mode._vc_cfg = vc
    return vc


def start_vanish_cut(fig, tx, ty):
    """Arm the vanish-cut: hide the figure, freeze-frame, let
    tick_vanish_cut run the blitz.  The fig->target direction is captured
    now so the reappear point continues the same line ('walked through')."""
    c = fig.combat
    t = fig.transform
    dx, dy = tx - t.x, ty - t.y
    dist = (dx * dx + dy * dy) ** 0.5
    if dist > 0.001:
        c.vc_dir_x, c.vc_dir_y = dx / dist, dy / dist
    else:
        c.vc_dir_x, c.vc_dir_y = 1.0, 0.0
    vc = vanish_cut_cfg(fig)
    c.vc_phase = 1
    c.vc_tick = vc["vanish_ticks"]
    c.vc_hits_left = int(vc["hits"])
    c.vc_hidden = True
    # Departure crackle at the vanish point + the dramatic freeze frame.
    c.blink_fx_pending.append((t.x, t.y, t.x, t.y))
    c.hitstop_request = True
    fig.trail.clear()


def tick_vanish_cut(fig, target_x, target_y):
    """Advance the vanish-cut sequence.  Returns True while it consumes the
    figure (advance_combat early-outs, MotionSystem skips)."""
    c = fig.combat
    if c.vc_phase == 0:
        return False
    vc = vanish_cut_cfg(fig)
    if vc is None:                      # config vanished mid-run — bail safe
        c.vc_phase = 0
        c.vc_hidden = False
        return False
    rng = fig.personality.rng
    if c.vc_phase == 1:
        # --- Vanished: dramatic pause before the blitz ---
        c.vc_tick -= 1
        if c.vc_tick <= 0:
            c.vc_phase = 2
            c.vc_tick = 0
        return True
    if c.vc_phase == 2:
        # --- Blitz: rapid slashes crossing the target from random angles ---
        if c.vc_tick > 0:
            c.vc_tick -= 1
            return True
        # Blitz slashes are pure visuals while the target is frozen —
        # the HP payload is queued as one burst at completion (below), so
        # the split lands the moment the world resumes.
        ang = rng.uniform(0.0, 2.0 * math.pi)
        ox = target_x + math.cos(ang) * 90.0
        oy = target_y + math.sin(ang) * 90.0
        r, g, b = fig.lut[80]
        c.crescents.append(CrescentWave(ox, oy, target_x, target_y,
                                        (r, g, b)))
        c.impact_fx_pending.append((target_x, target_y))
        c.vc_hits_left -= 1
        if c.vc_hits_left <= 0:
            c.vc_phase = 3
            c.vc_tick = vc["impact_ticks"]
            # Finisher: crossed slash pair through the target — the
            # 'split in half' read — plus a second world freeze.
            r2, g2, b2 = fig.lut[200]
            for sgn in (1.0, -1.0):
                px_ = target_x - c.vc_dir_y * sgn * 90.0
                py_ = target_y + c.vc_dir_x * sgn * 90.0
                c.crescents.append(CrescentWave(px_, py_,
                                                target_x, target_y,
                                                (r2, g2, b2)))
        else:
            c.vc_tick = vc["interval_ticks"]
        return True
    # --- Phase 3: impact hold, then reappear past the target ---
    c.vc_tick -= 1
    if c.vc_tick <= 0:
        t = fig.transform
        blink_warp(fig,
                   target_x + c.vc_dir_x * vc["reappear_past_px"],
                   target_y + c.vc_dir_y * vc["reappear_past_px"])
        # Stand-down pose: face the walk-through direction (away from the
        # target) — face() treats its argument as the previous position.
        fig.face(t.x - c.vc_dir_x, t.y - c.vc_dir_y)
        fig.render.is_moving = False
        # The HP payload: every hit's strike bullet, released together as
        # the freeze lifts.  Perfect-pursuit homing + pierce, spawned on a
        # ring around the target so each spends ticks airborne (a bullet
        # born touching the enemy is culled before the victim's side ever
        # snapshots it).  The victim's first unfrozen pass reads the whole
        # volley from enemy_projs — the split lands at the resume moment.
        spd = config.PROJ_SPEED * 1.5
        r3, g3, b3 = fig.lut[80]
        n_hits = max(1, int(vc["hits"]))
        for k in range(n_hits):
            ang = c.blinkstorm_angle + k * math.radians(137.5)
            ox = target_x + math.cos(ang) * 60.0
            oy = target_y + math.sin(ang) * 60.0
            ddx, ddy = target_x - ox, target_y - oy
            pr = HomingProjectile(ox, oy,
                                  ddx / 60.0 * spd, ddy / 60.0 * spd,
                                  (r3, g3, b3), 3,
                                  target=[float(target_x), float(target_y)],
                                  turn_rate=1.0)
            pr.style = "invisible"
            pr.damage = vc["hit_damage"]
            pr.pierce = True          # a parry stance can't undo the cut
            pr.one_hit = True         # ...but each strike lands exactly once
            pr.max_age = int(60.0 / max(spd, 0.001)) + 30
            c.vc_shots_pending.append(pr)
        c.vc_hidden = False
        c.vc_phase = 0
    return True


def check_reaction(fig, world):
    """Per-tick proximity reaction + charge-based vanish-cut launch.
    Called by CombatSystem for every figure BEFORE advance_combat (so an
    armed retaliation dash executes the same tick); no-ops unless the
    character authors the JSON blocks.  Identical in Solo & Battle."""
    c = fig.combat
    if c.reaction_cd > 0:
        c.reaction_cd -= 1
    rc = reaction_cfg(fig)
    if rc is None:
        return
    if world.battle_mode and world.partner_figures:
        tx, ty = world._nearest_enemy(fig.x, fig.y)
    else:
        tx, ty = world.cursor
    # --- Charge-based vanish-cut launch (gated on trigger_range_px so
    #     the cut lands as a duel finisher, not a cross-map snipe) ---
    vc = vanish_cut_cfg(fig)
    if (vc is not None and c.vc_phase == 0 and not c.busy
            and c.ult_charges >= int(vc["charges_required"])):
        _ldx, _ldy = tx - fig.transform.x, ty - fig.transform.y
        if (_ldx * _ldx + _ldy * _ldy) ** 0.5 <= vc["trigger_range_px"]:
            c.ult_charges = 0
            start_vanish_cut(fig, tx, ty)
            return
    if c.vc_phase != 0 or c.blinkstorm_strikes_left > 0:
        return
    if c.reaction_cd > 0 or c.busy:
        return
    t = fig.transform
    dx, dy = tx - t.x, ty - t.y
    dist = (dx * dx + dy * dy) ** 0.5
    if dist > rc["radius_px"] or dist < 0.001:
        return
    rng = fig.personality.rng
    c.reaction_cd = rc["cooldown_ticks"]
    can_slash = bool(fig.render.bundle.slash)
    if can_slash and rng.random() < rc["counter_chance"]:
        # --- COUNTER: block (deflect window) + retaliation slash ---
        trigger_parry(fig)
        cc = combo_cfg(fig)
        if dist > cc["hit_radius"]:
            inv = 1.0 / dist
            lspd = fig.motion.speed * cc["dash_speed_mult"]
            c.slash_vx = dx * inv * lspd
            c.slash_vy = dy * inv * lspd
            c.slash_dist_budget = dist * 4.0
            c.dashing = True
            c.rebounding = False
        else:
            c.slashing = True
            c.slash_phase = c.slash_idx = c.slash_tick = 0
            c.slash_vx = c.slash_vy = 0.0
        # Face the enemy (face() takes the previous position).
        fig.face(t.x - dx, t.y - dy)
    else:
        # --- DODGE: blink PAST the enemy on the approach line ---
        inv = 1.0 / dist
        blink_warp(fig,
                   tx + dx * inv * rc["blink_behind_px"],
                   ty + dy * inv * rc["blink_behind_px"])
        ndx, ndy = tx - t.x, ty - t.y
        fig.face(t.x - ndx, t.y - ndy)
    if rc["charge_ultimate"]:
        c.ult_charges += 1


def advance_combat(fig, slash_target, fallback):
    t = fig.transform
    c = fig.combat
    m = fig.motion
    rng = fig.personality.rng
    bundle = fig.render.bundle
    cc = combo_cfg(fig)

    if not bundle.slash:
        return False  # this mode has no melee capability

    # --- Attack-string cooldown tick (~1 s after a completed 3-hit string) ---
    if c.attack_cooldown_ticks > 0:
        c.attack_cooldown_ticks -= 1
    # --- Follow-up type lock tick (0.2 s window after a 50/50 pick) ---
    if c.followup_lock_ticks > 0:
        c.followup_lock_ticks -= 1
        if c.followup_lock_ticks <= 0:
            c.followup_lock_type = 0

    # --- Follow-up dashslash delay: count down, then launch a STRAIGHT dash ---
    if c.combo_delay_ticks > 0:
        c.combo_delay_ticks -= 1
        if c.combo_delay_ticks == 0 and slash_target is not None:
            tx, ty = slash_target
            ddx, ddy = tx - t.x, ty - t.y
            ddist = (ddx * ddx + ddy * ddy) ** 0.5
            if ddist > cc['hit_radius']:
                inv = 1.0 / ddist
                lspd = m.speed * cc['dash_speed_mult']
                c.slash_vx = ddx * inv * lspd
                c.slash_vy = ddy * inv * lspd
                # Budget proportional to actual gap — same formula as initial dash.
                c.slash_dist_budget = ddist * 4.0
                c.dashing = True
                c.rebounding = False

    # -----------------------------------------------------------------------
    # ARC PHASES — shared by the primary arcslash (shrinking-radius approach)
    # and the follow-up arcslash (recoil + constant-radius 150° orbit).
    # -----------------------------------------------------------------------

    # --- Arc recoil: dash directly away from target after a hit (follow-up arcslash) ---
    if c.arc_recoiling:
        ox, oy = t.x, t.y
        _bl = blink_cfg(fig)
        if (_bl is not None and _bl['combo'] and c.arc_recoil_ticks > 1
                and c.blink_windup <= 0):
            # Blink: take the whole remaining recoil in one warp, then let
            # the final tick below arm the orbit exactly as authored.
            steps = c.arc_recoil_ticks - 1
            blink_warp(fig, t.x + c.slash_vx * steps, t.y + c.slash_vy * steps)
            c.arc_recoil_ticks = 1
            c.blink_windup = _bl['combo_cooldown_ticks']
        c.arc_recoil_ticks -= 1
        t.x += c.slash_vx
        t.y += c.slash_vy
        spawn_afterimage(fig)
        if c.arc_recoil_ticks <= 0:
            c.arc_recoiling = False
            # Arm the constant-radius orbit around the hit target.
            cx_, cy_ = c.arc_center_x, c.arc_center_y
            dx_, dy_ = t.x - cx_, t.y - cy_
            c.arc_orbit_r = max((dx_*dx_ + dy_*dy_)**0.5, 20.0)
            c.arc_r_start = c.arc_orbit_r
            c.arc_r_end = c.arc_orbit_r
            c.arc_start_angle = math.atan2(dy_, dx_)
            arc_rad = math.radians(cc['arc_orbit_angle_deg']) * c.arc_combo_dir
            c.arc_end_angle = c.arc_start_angle + arc_rad
            c.arc_repo_t = 0
            c.arc_repo_steps = cc['arc_repo_ticks']
            c.arc_repositioning = True
        fig.face(ox, oy)
        _apply_trail_update(fig, t, True, False)
        fig.render.is_moving = True
        fig.render.advance()
        return True

    # --- Arc travel: curved path around the target.  Radius interpolates from
    #     arc_r_start to arc_r_end (constant for the follow-up orbit; shrinking
    #     for the primary arcslash approach).  Ends with a dash-in. ---
    if c.arc_repositioning:
        ox, oy = t.x, t.y
        _bl = blink_cfg(fig)
        if (_bl is not None and _bl['combo']
                and c.arc_repo_t < c.arc_repo_steps - 1
                and c.blink_windup <= 0):
            # Blink: skip the curved travel — warp straight to the arc's
            # end position; the final tick launches the dash-in as usual.
            end_x = c.arc_center_x + math.cos(c.arc_end_angle) * c.arc_r_end
            end_y = c.arc_center_y + math.sin(c.arc_end_angle) * c.arc_r_end
            blink_warp(fig, end_x, end_y)
            c.arc_repo_t = c.arc_repo_steps - 1
            c.blink_windup = _bl['combo_cooldown_ticks']
        c.arc_repo_t += 1
        # Smooth cubic ease-in-out for natural arc travel
        raw = c.arc_repo_t / max(c.arc_repo_steps, 1)
        ease = raw * raw * (3.0 - 2.0 * raw)
        angle = c.arc_start_angle + (c.arc_end_angle - c.arc_start_angle) * ease
        radius = c.arc_r_start + (c.arc_r_end - c.arc_r_start) * ease
        t.x = c.arc_center_x + math.cos(angle) * radius
        t.y = c.arc_center_y + math.sin(angle) * radius
        spawn_afterimage(fig)
        if c.arc_repo_t >= c.arc_repo_steps:
            c.arc_repositioning = False
            # Launch the dash-in toward the LIVE target if available.
            if slash_target is not None:
                tx_, ty_ = slash_target
            else:
                tx_, ty_ = c.arc_center_x, c.arc_center_y
            ddx, ddy = tx_ - t.x, ty_ - t.y
            ddist = (ddx*ddx + ddy*ddy)**0.5
            lspd = m.speed * cc['dash_speed_mult']
            if ddist > 1.0:
                inv = 1.0 / ddist
                c.slash_vx = ddx * inv * lspd
                c.slash_vy = ddy * inv * lspd
            # else: keep current slash velocity direction — we are on top of the
            # target and the hit check will fire on the first dash tick anyway.
            c.slash_dist_budget = max(ddist * 4.0, lspd * 2.0)
            c.dashing = True
            c.rebounding = False
            # Alternate orbit direction for the next arc (CW ↔ CCW).
            c.arc_combo_dir *= -1
        fig.face(ox, oy)
        _apply_trail_update(fig, t, True, False)
        fig.render.is_moving = True
        fig.render.advance()
        return True

    # --- Crescent advance + cull (emission happens on dash hit) ---
    if c.crescents:
        live = []
        for cr in c.crescents:
            cr.update()
            if cr.alive:
                live.append(cr)
        c.crescents = live

    # --- Blink combo cooldown (shared 0.2 s gate between teleports) ---
    if c.blink_windup > 0:
        c.blink_windup -= 1

    # --- Ultimate crescent advance + 2nd-shot delay (always tick for melee) ---
    tick_ult_crescents(fig, fallback[0], fallback[1])

    # --- Blinkstorm ultimate (blink characters): consumes the figure while
    #     active — strikes ride the live melee target, fallback = cursor. ---
    _bs_tx, _bs_ty = slash_target if slash_target is not None else fallback
    if tick_blinkstorm(fig, _bs_tx, _bs_ty):
        _apply_trail_update(fig, t, False, False)
        fig.render.is_moving = False
        return True

    # --- Vanish-cut ultimate (charge characters): consumes the figure while
    #     active — the blitz rides the live melee target, fallback = cursor. ---
    if tick_vanish_cut(fig, _bs_tx, _bs_ty):
        _apply_trail_update(fig, t, False, False)
        fig.render.is_moving = False
        return True

    # --- Slash cycle (stationary; plays once at end of dash/rebound) ---
    if c.slashing:
        ox, oy = t.x, t.y
        c.slash_tick += 1
        if c.slash_tick >= config.SLASH_ANIM_SPD:
            c.slash_tick = 0
            if c.slash_phase == 0:
                c.slash_idx += 1
                if c.slash_idx >= 2:
                    c.slash_idx = 2
                    c.slash_phase = 1
            elif c.slash_phase == 1:
                c.slash_phase = 2
                c.slash_idx = 3
            else:
                c.slash_idx += 1
                if c.slash_idx >= 5:
                    c.slashing = c.rebounding = c.dashing = False
                    fig.render.run_idx = 0
                    fig.render.anim_tick = 0
                    # --- Launch the queued follow-up attack, if any ---
                    if c.followup_pending == 2:
                        # Follow-up ARCSLASH: recoil away, then 150° orbit, then dash-in.
                        c.followup_pending = 0
                        ndx = t.x - c.arc_center_x
                        ndy = t.y - c.arc_center_y
                        ndist = (ndx*ndx + ndy*ndy)**0.5
                        if ndist > 0.001:
                            nx_, ny_ = ndx / ndist, ndy / ndist
                        else:
                            nx_, ny_ = 1.0, 0.0
                        recoil_spd = cc['arc_recoil_px'] / max(cc['arc_recoil_ticks'], 1)
                        c.slash_vx = nx_ * recoil_spd
                        c.slash_vy = ny_ * recoil_spd
                        c.arc_recoil_ticks = cc['arc_recoil_ticks']
                        c.arc_recoiling = True
                    elif c.followup_pending == 1:
                        # Follow-up DASHSLASH: randomised pause, then straight dash
                        # (gives the target breathing room after knockback).
                        c.followup_pending = 0
                        c.combo_delay_ticks = rng.randint(
                            cc['combo_travel_ticks_min'],
                            cc['combo_travel_ticks_max'])
        fig.face(ox, oy)
        _apply_trail_update(fig, t, False, False)
        fig.render.is_moving = False
        return True

    # --- Dash / Rebound ---
    if c.dashing:
        if c.dodge_interrupt:
            # A dodge was requested mid-dash: cancel the dash and fall through to
            # the dodge block below (do NOT return). Triggers wired in stage 3.
            c.dashing = c.rebounding = c.dodge_interrupt = False
            c.dodge_dashing = True
        else:
            ox, oy = t.x, t.y
            if not c.rebounding:
                tx, ty = slash_target if slash_target is not None else fallback
                dx, dy = tx - t.x, ty - t.y
                dist = (dx * dx + dy * dy) ** 0.5
                if dist <= cc['hit_radius']:
                    # Crescent aimed at the struck target.
                    r, g, b = fig.lut[80]
                    c.crescents.append(CrescentWave(t.x, t.y, tx, ty, (r, g, b)))
                    # Signal knockback to the enemy side (delivered by
                    # World.refresh_battle at the start of the next tick).
                    kb_spd = config.DASH_HIT_KNOCKBACK_PX * (1.0 - config.BOUNCE_FRICTION)
                    ddx2, ddy2 = tx - t.x, ty - t.y
                    ddist2 = (ddx2 * ddx2 + ddy2 * ddy2) ** 0.5
                    if ddist2 > 0.001:
                        c.hit_vx = (ddx2 / ddist2) * kb_spd
                        c.hit_vy = (ddy2 / ddist2) * kb_spd
                    else:
                        c.hit_vx = c.slash_vx / max(abs(c.slash_vx) + abs(c.slash_vy), 0.001) * kb_spd
                        c.hit_vy = c.slash_vy / max(abs(c.slash_vx) + abs(c.slash_vy), 0.001) * kb_spd
                    c.hit_pending = True
                    # Impact FX: shockwave ring + spark burst at the hit point
                    # (spawned by CombatSystem into world FX lists).
                    c.impact_fx_pending.append((tx, ty))
                    # ---------------------------------------------------------
                    # ATTACK STRING — count the hit; queue a follow-up (50/50
                    # dashslash vs arcslash with a 0.2 s type lock) until the
                    # string reaches ATTACK_STRING_MAX_HITS, then cool down.
                    # ---------------------------------------------------------
                    c.arc_center_x = float(tx)
                    c.arc_center_y = float(ty)
                    chain = False
                    if c.attack_cooldown_ticks <= 0:
                        c.attack_hits += 1
                        if c.attack_hits < cc['max_hits']:
                            chain = True
                        else:
                            # String complete — reset and start the ~1 s cooldown.
                            c.attack_hits = 0
                            c.attack_cooldown_ticks = cc['cooldown_ticks']
                            c.hitstop_request = True   # finisher = big hit -> world freeze
                    if chain:
                        # Pick the follow-up type: locked type wins within the
                        # 0.2 s window, otherwise a fresh 50/50 roll locks it.
                        if c.followup_lock_ticks > 0 and c.followup_lock_type:
                            ftype = c.followup_lock_type
                        else:
                            ftype = 1 if rng.random() < 0.5 else 2
                            c.followup_lock_type = ftype
                            c.followup_lock_ticks = cc['followup_lock_ticks']
                        c.followup_pending = ftype
                        # Stop dead and play the slash; the follow-up launches
                        # when the animation completes.
                        c.dashing = c.rebounding = False
                        c.slashing = True
                        c.slash_phase = c.slash_idx = c.slash_tick = 0
                        c.slash_vx = c.slash_vy = 0.0
                    else:
                        # No chain (string finished or on cooldown): reflect
                        # velocity off the contact and rebound away.
                        if dist > 0.001:
                            nx = (t.x - tx) / dist
                            ny = (t.y - ty) / dist
                        else:
                            spd = (c.slash_vx ** 2 + c.slash_vy ** 2) ** 0.5
                            nx = -c.slash_vx / spd if spd > 0 else 1.0
                            ny = -c.slash_vy / spd if spd > 0 else 0.0
                        dot = c.slash_vx * nx + c.slash_vy * ny
                        rx = c.slash_vx - 2.0 * dot * nx
                        ry = c.slash_vy - 2.0 * dot * ny
                        rmag = (rx * rx + ry * ry) ** 0.5
                        if rmag > 0.001:
                            lspd = (c.slash_vx ** 2 + c.slash_vy ** 2) ** 0.5
                            c.slash_vx = rx / rmag * lspd
                            c.slash_vy = ry / rmag * lspd
                        c.rebounding = True
                else:
                    bl = blink_cfg(fig)
                    if bl is not None and bl['combo']:
                        # Combo blink: warp to just inside hit range once
                        # the shared 0.2 s teleport cooldown expires —
                        # the hit-check above fires next tick against
                        # the live target.
                        if c.blink_windup <= 0:
                            inv = 1.0 / max(dist, 0.001)
                            land = cc['hit_radius'] * 0.85
                            blink_warp(fig,
                                       tx - dx * inv * land,
                                       ty - dy * inv * land)
                            c.blink_windup = bl['combo_cooldown_ticks']
                        fig.face(tx, ty)
                        _apply_trail_update(fig, t, False, False)
                        fig.render.is_moving = False
                        return True
                    t.x += c.slash_vx
                    t.y += c.slash_vy
                    spawn_afterimage(fig)
                    c.slash_dist_budget -= (c.slash_vx ** 2 + c.slash_vy ** 2) ** 0.5
                    if c.slash_dist_budget <= 0:
                        c.dashing = False
                        # Missed string — clear hit progress so the next primary
                        # starts a fresh string.
                        c.attack_hits = 0
            else:
                t.x += c.slash_vx
                t.y += c.slash_vy
                spawn_afterimage(fig)
                c.slash_dist_budget -= (c.slash_vx ** 2 + c.slash_vy ** 2) ** 0.5
                if c.slash_dist_budget <= 0:
                    c.dashing = False
                    c.slashing = True
                    c.slash_phase = c.slash_idx = c.slash_tick = 0
            fig.face(ox, oy)
            _apply_trail_update(fig, t, True, False)
            fig.render.is_moving = True
            fig.render.advance()
            return True

    # --- Dodge dash execution (triggers wired stage 3; also reached via the
    #     dodge_interrupt fall-through above) ---
    if c.dodge_dashing:
        ox, oy = t.x, t.y
        _bl = blink_cfg(fig)
        if _bl is not None and _bl['defend'] and c.dodge_dist_budget > 0:
            # Defend blink: the whole dodge displacement lands in one warp.
            step0 = (c.dodge_vx ** 2 + c.dodge_vy ** 2) ** 0.5
            if step0 > 0.001:
                # Warp all-but-one step; the normal += below lands the last
                # step so the completion math stays exactly as authored.
                k = max(c.dodge_dist_budget / step0 - 1.0, 0.0)
                if k > 0.0:
                    blink_warp(fig, t.x + c.dodge_vx * k, t.y + c.dodge_vy * k)
                c.dodge_dist_budget = step0
        step = (c.dodge_vx ** 2 + c.dodge_vy ** 2) ** 0.5
        t.x += c.dodge_vx
        t.y += c.dodge_vy
        spawn_afterimage(fig)
        c.dodge_dist_budget -= step
        if c.dodge_dist_budget <= 0:
            c.dodge_dashing = False
            if c.dodge_counter and slash_target is not None:
                c.dodge_counter = False
                tx, ty = slash_target
                dx, dy = tx - t.x, ty - t.y
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > cc['hit_radius']:
                    inv = 1.0 / max(dist, 0.001)
                    lspd = m.speed * cc['dash_speed_mult']
                    c.slash_vx = dx * inv * lspd
                    c.slash_vy = dy * inv * lspd
                    c.slash_dist_budget = dist * 4.0
                    c.dashing = True
                    c.rebounding = False
            else:
                c.dodge_counter = False
        fig.face(ox, oy)
        _apply_trail_update(fig, t, True, False)
        fig.render.is_moving = True
        fig.render.advance()
        return True

    # --- Primary attack trigger (arms an attack; does NOT consume the tick) ---
    # Generic `counter_only` JSON flag (top-level, opt-in): suppresses ALL
    # self-initiated primary attacks — the character still approaches and
    # stands ready in range, attacking only through the reaction system's
    # counter/dodge retaliations (combat.check_reaction) and their combo
    # follow-ups. Identical in Solo & Battle.
    _char = getattr(fig.mode, "character", None)
    if _char and _char.get("counter_only"):
        return False
    # 50/50 between:
    #   dashslash — straight dash at the target (classic)
    #   arcslash  — curved approach sweeping around the target, ending in a slash
    if (slash_target is not None and not m.bouncing and not m.bounce_ending
            and c.combo_delay_ticks == 0):
        tx, ty = slash_target
        dx, dy = tx - t.x, ty - t.y
        dist = (dx * dx + dy * dy) ** 0.5
        # Per-character basic attack radius (MODE_CONFIGS, set from the
        # character's stats.basic_attack_radius; falls back to the classic
        # SLASH_RADIUS for figures that don't define one). Identical in
        # Solo & Battle — both read the same MODE_CONFIGS entry.
        atk_radius = config.MODE_CONFIGS.get(fig.mode.key, {}).get(
            "basic_attack_radius", config.SLASH_RADIUS)
        if cc['hit_radius'] < dist <= atk_radius:
            c.attack_hits = 0  # fresh string
            if rng.random() < 0.5:
                # --- Primary DASHSLASH: straight in ---
                inv = 1.0 / dist
                lspd = m.speed * cc['dash_speed_mult']
                c.slash_vx = dx * inv * lspd
                c.slash_vy = dy * inv * lspd
                c.slash_dist_budget = dist * 4.0
                c.dashing = True
                c.rebounding = False
            else:
                # --- Primary ARCSLASH: curved approach, radius shrinking from
                #     current distance down to just outside the hit radius, then
                #     a short dash-in lands the slash from a new direction. ---
                c.arc_center_x = float(tx)
                c.arc_center_y = float(ty)
                c.arc_combo_dir = rng.choice([1, -1])
                c.arc_r_start = dist
                c.arc_r_end = cc['hit_radius'] * 1.5
                c.arc_start_angle = math.atan2(t.y - ty, t.x - tx)
                sweep = math.radians(cc['arc_approach_sweep_deg']) * c.arc_combo_dir
                c.arc_end_angle = c.arc_start_angle + sweep
                c.arc_repo_t = 0
                c.arc_repo_steps = cc['arc_approach_ticks']
                c.arc_repositioning = True

    return False








