"""The paint pass.

RULE: painting reads simulation state and writes NOTHING.

v1's `_paint` aged sparks, rings, flashes and dots inline — so FX timing
depended on whether a frame was drawn, which blocked batching, blocked
interpolation and made the world unhashable.  Here, paint is pure.  A frame
that is skipped changes nothing.  All renderer-owned FX state (cue
overlays, motion trails, afterimage ghosts) is advanced in `age_cues`,
which the app calls from the SIM step — never from paint.

Draw order (back to front):
    motes (batched)  ->  cue overlays  ->  actors  ->  HUD

Actors are no longer a hardcoded stick figure: each character's `visual`
block supplies either a V1-style rig (bones + keyframe actions, played
back with continuous interpolation — see rig.py) or PNG sprite frame sets
(runner / swordsman, V1's original art).  On top of the figure itself sit
the V1 FX suite, all cosmetic and all renderer-owned: outline glow,
motion trails, dash afterimage ghosts, layered crescent slashes, impact
shockwaves and guard shells.  Everything keys off actor state and tags —
never off battle/solo mode — so Solo and Battle stay visually identical
by construction.

Interpolation: the simulation runs on a fixed tick; the renderer draws
between the previous and current state using `alpha`, so motion stays smooth
even when render rate and tick rate differ.
"""

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen

from .batch import FragmentBatcher, SpriteAtlas
from . import rig as _rig
from ..sim.motes import (F_ALIVE, F_FADE, KIND_NAMES,
                         K_AFTERIMAGE, K_BEAM, K_BULLET, K_PETAL,
                         K_RING, K_SPARK, K_DEBRIS)

__all__ = ["Renderer"]

_KIND_SHAPE = {
    K_BULLET: "bullet",
    K_SPARK: "spark",
    K_PETAL: "orb",
    K_AFTERIMAGE: "dot",
    K_RING: "ring",
    K_BEAM: "beam",
    K_DEBRIS: "shard",
}

_RIG_BASE = _rig.TARGET_HEAD_PX / _rig.RIG_HEAD_DIAMETER   # 0.8

# FX defaults — a character opts in / restyles via visual["fx"]; these keep
# every fighter looking alive even before its block is authored.
_AFTERIMAGE_DEFAULTS = {"alpha": 96, "life": 13, "min_step": 6.0, "every": 2}
_TRAIL_DEFAULTS = {"width": 3.0, "length": 16, "min_step": 1.2, "alpha": 120}


class _FigureStyle:
    """Per-character presentation bundle, built once from `visual`."""

    __slots__ = ("rig", "sprites", "palette", "fx", "glow", "sprite_tpf")

    def __init__(self, visual, search_dirs):
        visual = visual or {}
        self.palette = dict(visual.get("palette") or {})
        self.fx = dict(visual.get("fx") or {})
        self.rig = None
        self.sprites = None
        self.sprite_tpf = 5
        rig_block = visual.get("rig")
        if rig_block:
            self.rig = _rig.RigAnimator(rig_block)
        spr = visual.get("sprites")
        if spr:
            bank = _rig.SpriteBank(spr, search_dirs)
            if bank.ok:
                self.sprites = bank
                self.sprite_tpf = int(spr.get("ticks_per_frame", 5))
        og = visual.get("outline_glow")
        if og is True:
            og = {}
        if isinstance(og, dict):
            self.glow = {
                "color": og.get("color", self.accent()),
                "radius": float(og.get("radius", 2.4)),
                "opacity": int(og.get("opacity", 110)),
            }
        else:
            self.glow = None

    def body(self):
        return self.palette.get("body", self.palette.get("primary", 0x8FA0B8))

    def accent(self):
        return self.palette.get("accent",
                                self.palette.get("primary", 0x39D5FF))

    def fx_cfg(self, name, defaults):
        cfg = dict(defaults)
        block = self.fx.get(name)
        if isinstance(block, dict):
            cfg.update(block)
        return cfg


class Renderer:
    def __init__(self, world, show_hud=True, asset_dirs=None):
        self.world = world
        self.atlas = SpriteAtlas(self._palette_colors(world))
        self.batcher = FragmentBatcher(self.atlas)
        self.show_hud = show_hud
        self.cue_overlays = []          # short-lived, owned by the renderer
        self.frame = 0
        self.last_stats = {"fragments": 0, "calls": 0}
        self._prev = {}                 # actor id -> (x, y) last tick
        self._styles = {}               # character key -> _FigureStyle
        self._trails = {}               # actor id -> [(x, y), ...] newest last
        self._ghosts = []               # afterimage ghosts, renderer-owned
        if asset_dirs is None:
            import os
            here = os.path.dirname(os.path.abspath(__file__))
            v2_root = os.path.dirname(os.path.dirname(here))
            repo_root = os.path.dirname(v2_root)
            asset_dirs = [os.path.join(v2_root, "assets"), repo_root]
        self._asset_dirs = asset_dirs

    @staticmethod
    def _palette_colors(world):
        cols = {0xFFFFFF, 0x39D5FF, 0xFF5AD0, 0xFFC248}
        for a in world.all_actors():
            for v in (a.visual.get("palette") or {}).values():
                if isinstance(v, int):
                    cols.add(v)
        return sorted(cols)

    def refresh_palette(self):
        self.atlas.ensure_colors(self._palette_colors(self.world))

    def _style(self, actor):
        key = getattr(actor.archetype, "key", None) or "?"
        st = self._styles.get(key)
        if st is None:
            st = _FigureStyle(actor.visual, self._asset_dirs)
            self._styles[key] = st
        return st

    # ------------------------------------------------------------------
    # cue intake — cues are cosmetic ONLY, and are consumed here
    # ------------------------------------------------------------------
    def consume_cues(self):
        for name, aid, ax, ay, params, tick in self.world.drain_cues():
            x = float(params.get("x", ax))
            y = float(params.get("y", ay))
            self.cue_overlays.append({
                "name": name, "x": x, "y": y, "t": 0,
                "life": int(params.get("life", 18)),
                "angle": float(params.get("angle", 0.0)),
                "reach": float(params.get("reach", 60.0)),
                "scale": float(params.get("scale", 1.0)),
                "actor": aid,
            })
        if len(self.cue_overlays) > 600:
            del self.cue_overlays[:-600]

    def age_cues(self):
        """Called from the SIM step, not from paint — this is the discipline
        that keeps painting pure.  Also advances every renderer-owned FX
        system (trails, afterimages) exactly once per sim tick."""
        alive = []
        for c in self.cue_overlays:
            c["t"] += 1
            if c["t"] < c["life"]:
                alive.append(c)
        self.cue_overlays = alive
        self._update_actor_fx()

    def _update_actor_fx(self):
        """Advance trails + spawn/age afterimage ghosts.  Sim-step cadence,
        reads actor state only, writes only renderer-owned buffers."""
        w = self.world
        seen = set()
        for a in w.all_actors():
            if not a.alive or a.tags.has("state.vanished"):
                continue
            seen.add(a.id)
            st = self._style(a)

            # -- motion trail ------------------------------------------
            tr_cfg = st.fx_cfg("trail", _TRAIL_DEFAULTS)
            if tr_cfg.get("colors"):
                trail = self._trails.setdefault(a.id, [])
                if (not trail or
                        math.hypot(a.x - trail[-1][0], a.y - trail[-1][1])
                        >= float(tr_cfg["min_step"])):
                    trail.append((a.x, a.y))
                cap = int(tr_cfg["length"])
                if len(trail) > cap:
                    del trail[:-cap]

            # -- dash afterimages --------------------------------------
            ai_cfg = st.fx_cfg("afterimage", _AFTERIMAGE_DEFAULTS)
            if ai_cfg.get("color") is not None:
                px, py = self._prev.get(a.id, (a.x, a.y))
                step = math.hypot(a.x - px, a.y - py)
                if (step >= float(ai_cfg["min_step"])
                        and w.tick % max(1, int(ai_cfg["every"])) == 0):
                    self._ghosts.append({
                        "actor": a.id, "key": getattr(a.archetype, "key", "?"),
                        "x": px, "y": py,
                        "anim": a.anim, "anim_t": a.anim_t,
                        "facing": a.facing, "age": 0,
                        "life": int(ai_cfg["life"]),
                        "color": int(ai_cfg["color"]),
                        "alpha": int(ai_cfg["alpha"]),
                        "scale": self._figure_scale(a),
                    })
        for g in self._ghosts:
            g["age"] += 1
        self._ghosts = [g for g in self._ghosts if g["age"] < g["life"]]
        if len(self._ghosts) > 240:
            del self._ghosts[:-240]
        for aid in [i for i in self._trails if i not in seen]:
            del self._trails[aid]

    def remember_positions(self):
        self._prev = {a.id: (a.x, a.y) for a in self.world.all_actors()}

    def _figure_scale(self, a):
        return (self.world.size_field.at(a.x, a.y)
                * a.attrs.get("scale"))

    # ------------------------------------------------------------------
    # paint
    # ------------------------------------------------------------------
    def paint(self, p, alpha=1.0):
        self.frame += 1
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        self._paint_motes(p)
        self._paint_trails(p)
        self._paint_ghosts(p)
        self._paint_cues(p)
        self._paint_actors(p, alpha)
        if self.show_hud:
            self._paint_hud(p)

    # -- motes: the whole point of the batcher -------------------------
    def _paint_motes(self, p):
        w = self.world
        m = w.motes
        a = m._arrays
        b = self.batcher
        b.begin()
        size_field = w.size_field

        for i in m.live_indices():
            i = int(i)
            x = float(a["x"][i])
            y = float(a["y"][i])
            kind = int(a["kind"][i])
            shape = _KIND_SHAPE.get(kind, "dot")
            rgb = int(a["color"][i]) or 0xFFFFFF

            scale = float(a["size"][i]) * size_field.at(x, y) * 0.5
            opacity = 1.0
            if a["flag"][i] & F_FADE:
                life = max(1, int(a["life"][i]))
                opacity = max(0.0, 1.0 - float(a["age"][i]) / life)
            b.add(shape, rgb, x, y, scale, float(a["rot"][i]), opacity)

        n = b.flush(p)          # <- ONE call for every mote in the world
        self.last_stats = {"fragments": n, "calls": b.calls}

    # -- motion trails: fading ribbon behind fast movers ---------------
    def _paint_trails(self, p):
        for aid, trail in self._trails.items():
            if len(trail) < 2:
                continue
            a = self.world.actor_by_id(aid)
            if a is None:
                continue
            st = self._style(a)
            cfg = st.fx_cfg("trail", _TRAIL_DEFAULTS)
            colors = cfg.get("colors") or [st.accent(), st.accent()]
            c0 = _rig.qcolor(colors[0])
            c1 = _rig.qcolor(colors[-1])
            n = len(trail)
            base_a = int(cfg.get("alpha", 120))
            width = float(cfg.get("width", 3.0))
            pen = QPen()
            pen.setCapStyle(Qt.RoundCap)
            for i in range(n - 1):
                f = i / max(1, n - 1)          # 0 = oldest, 1 = newest
                col = QColor(
                    int(c0.red() + (c1.red() - c0.red()) * f),
                    int(c0.green() + (c1.green() - c0.green()) * f),
                    int(c0.blue() + (c1.blue() - c0.blue()) * f),
                    int(base_a * f))
                pen.setColor(col)
                pen.setWidthF(width * (0.35 + 0.65 * f))
                p.setPen(pen)
                p.drawLine(QPointF(*trail[i]), QPointF(*trail[i + 1]))

    # -- afterimages: V1's dash speed-ghosts ---------------------------
    def _paint_ghosts(self, p):
        for g in self._ghosts:
            st = self._styles.get(g["key"])
            if st is None:
                continue
            fade = 1.0 - g["age"] / max(1, g["life"])
            alpha = int(g["alpha"] * fade)
            if alpha <= 3:
                continue
            facing_left = math.cos(g["facing"]) < 0.0
            s = g["scale"]
            if st.sprites is not None:
                pm = st.sprites.silhouette_frame(
                    g["anim"], g["anim_t"], g["color"],
                    st.sprite_tpf, facing_left)
                if pm is not None:
                    p.setOpacity(alpha / 255.0)
                    p.save()
                    p.translate(g["x"], g["y"])
                    if s != 1.0:
                        p.scale(s, s)
                    p.drawPixmap(-pm.width() // 2, -pm.height() // 2, pm)
                    p.restore()
                    p.setOpacity(1.0)
                continue
            if st.rig is not None:
                J = st.rig.joints_at(g["anim"], g["anim_t"])
                p.save()
                p.translate(g["x"], g["y"])
                rs = s * _RIG_BASE * st.rig.scale
                p.scale(-rs if facing_left else rs, rs)
                _rig.draw_rig(p, J, g["color"], None,
                              stroke=3.5, alpha=alpha, flat=True)
                p.restore()

    # -- cues: cosmetic overlays --------------------------------------
    def _cue_accent(self, c, fallback=0xDCF5FF):
        a = self.world.actor_by_id(c.get("actor", -1))
        if a is not None:
            st = self._style(a)
            cr = st.fx.get("crescent") or {}
            return cr.get("color", st.accent()), cr.get("glow")
        return fallback, None

    def _paint_cues(self, p):
        for c in self.cue_overlays:
            f = c["t"] / max(1, c["life"])
            fade = max(0.0, 1.0 - f)
            name = c["name"]
            if name == "crescent":
                self._crescent(p, c, fade, f)
            elif name in ("ring", "burst"):
                pen = QPen(QColor(255, 194, 72, int(200 * fade)))
                pen.setWidthF(2.5)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                r = 18.0 + 120.0 * f * c["scale"]
                p.drawEllipse(QPointF(c["x"], c["y"]), r, r)
            elif name in ("flash", "muzzle"):
                rgb, _ = self._cue_accent(c, 0xFFFFFF)
                p.setPen(Qt.NoPen)
                p.setBrush(_rig.qcolor(rgb, int(190 * fade)))
                r = 16.0 * c["scale"] * (1.0 - f * 0.5)
                p.drawEllipse(QPointF(c["x"], c["y"]), r, r)
            elif name == "impact":
                self._impact(p, c, fade, f)

    def _crescent(self, p, c, fade, f):
        """Layered anime slash arc: wide soft glow, saturated mid stroke,
        white-hot core — sweeping outward slightly as it fades."""
        rgb, glow_rgb = self._cue_accent(c)
        r = c["reach"] * (1.0 + 0.25 * f)
        rect = QRectF(c["x"] - r, c["y"] - r, r * 2, r * 2)
        sweep = 110 + 30 * f
        start = int((-c["angle"] * 180.0 / math.pi - sweep / 2) * 16)
        span = int(sweep * 16)
        p.setBrush(Qt.NoBrush)
        layers = (
            (glow_rgb if glow_rgb is not None else rgb, 10.0, 70),
            (rgb, 5.0, 200),
            (0xFFFFFF, 2.2, 235),
        )
        for lrgb, width, alpha in layers:
            pen = QPen(_rig.qcolor(lrgb, int(alpha * fade)))
            pen.setWidthF(width * (0.9 + 0.4 * (1.0 - f)))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, start, span)

    def _impact(self, p, c, fade, f):
        """Hit-stop feel: expanding shockwave ring + radial spark lines +
        hot core flash, replacing the old plain dot."""
        x, y = c["x"], c["y"]
        # shockwave ring
        pen = QPen(QColor(255, 235, 200, int(190 * fade)))
        pen.setWidthF(2.6 * fade + 0.6)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        r = 4.0 + 34.0 * f
        p.drawEllipse(QPointF(x, y), r, r)
        # radial sparks
        spen = QPen(QColor(255, 170, 110, int(220 * fade)))
        spen.setWidthF(2.0)
        spen.setCapStyle(Qt.RoundCap)
        p.setPen(spen)
        inner = 5.0 + 26.0 * f
        outer = inner + 9.0 * fade
        for k in range(6):
            ang = k * (math.pi / 3.0) + 0.35
            ca, sa = math.cos(ang), math.sin(ang)
            p.drawLine(QPointF(x + ca * inner, y + sa * inner),
                       QPointF(x + ca * outer, y + sa * outer))
        # core flash
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, int(210 * fade * fade)))
        p.drawEllipse(QPointF(x, y), 5.0 * fade + 1.0, 5.0 * fade + 1.0)

    # -- actors --------------------------------------------------------
    def _paint_actors(self, p, alpha):
        w = self.world
        for a in w.all_actors():
            px, py = self._prev.get(a.id, (a.x, a.y))
            x = px + (a.x - px) * alpha
            y = py + (a.y - py) * alpha

            if a.tags.has("state.vanished"):
                continue

            s = self._figure_scale(a)
            st = self._style(a)
            facing_left = math.cos(a.facing) < 0.0
            anim = a.anim
            if a.tags.has("state.guarding") or a.tags.has("state.deflecting"):
                anim = "guard"

            # hitstun shake — read-only, derived from the sim tick
            if a.hitstun > 0:
                x += math.sin(w.tick * 2.1) * 2.2 * s
                y += math.cos(w.tick * 1.7) * 1.4 * s

            # slight forward lean while running: cheap weight/urgency
            lean_deg = 0.0
            if anim == "run":
                lean_deg = 8.0 * (-1.0 if facing_left else 1.0)

            drew = False
            if st.sprites is not None:
                drew = self._draw_sprite_actor(p, a, st, x, y, s,
                                               anim, facing_left, lean_deg)
            if not drew and st.rig is not None:
                self._draw_rig_actor(p, a, st, x, y, s,
                                     anim, facing_left, lean_deg)
                drew = True
            if not drew:
                self._draw_fallback_actor(p, a, st, x, y, s)

            if a.tags.has("state.guarding") or a.tags.has("state.deflecting"):
                self._guard_shell(p, st, x, y, s,
                                  deflect=a.tags.has("state.deflecting"))

            if a.tags.has("player.controlled"):
                mp = QPen(QColor(255, 194, 72, 220))
                mp.setWidthF(2.0)
                p.setPen(mp)
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(x, y + 24 * s), 10 * s, 4 * s)

            self._hp_bar(p, a, x, y - 40 * s, s)

    def _draw_rig_actor(self, p, a, st, x, y, s, anim, facing_left, lean_deg):
        J = st.rig.joints_at(anim, a.anim_t)
        rs = s * _RIG_BASE * st.rig.scale
        glow = st.glow
        if glow is not None:
            p.save()
            p.translate(x, y)
            if lean_deg:
                p.rotate(lean_deg)
            p.scale(-rs if facing_left else rs, rs)
            steps = 6
            rad = glow["radius"] / max(0.05, rs)
            for i in range(steps):
                ang = (2 * math.pi * i) / steps
                p.save()
                p.translate(math.cos(ang) * rad, math.sin(ang) * rad)
                _rig.draw_rig(p, J, glow["color"], None, stroke=3.5,
                              alpha=glow["opacity"] // 2, flat=True)
                p.restore()
            p.restore()
        p.save()
        p.translate(x, y)
        if lean_deg:
            p.rotate(lean_deg)
        p.scale(-rs if facing_left else rs, rs)
        _rig.draw_rig(p, J, st.body(), st.accent(),
                      weapon_cfg=st.rig.weapon, stroke=3.5)
        p.restore()

    def _draw_sprite_actor(self, p, a, st, x, y, s, anim, facing_left,
                           lean_deg):
        pm = st.sprites.frame(anim, a.anim_t, st.sprite_tpf, facing_left)
        if pm is None:
            return False
        glow = st.glow
        if glow is not None:
            silh = st.sprites.silhouette_frame(anim, a.anim_t, glow["color"],
                                               st.sprite_tpf, facing_left)
            if silh is not None:
                p.save()
                p.translate(x, y)
                if lean_deg:
                    p.rotate(lean_deg)
                if s != 1.0:
                    p.scale(s, s)
                p.setOpacity(glow["opacity"] / 255.0)
                steps = 6
                sx, sy = -silh.width() // 2, -silh.height() // 2
                for i in range(steps):
                    ang = (2 * math.pi * i) / steps
                    p.drawPixmap(round(math.cos(ang) * glow["radius"]) + sx,
                                 round(math.sin(ang) * glow["radius"]) + sy,
                                 silh)
                p.setOpacity(1.0)
                p.restore()
        p.save()
        p.translate(x, y)
        if lean_deg:
            p.rotate(lean_deg)
        if s != 1.0:
            p.scale(s, s)
        p.drawPixmap(-pm.width() // 2, -pm.height() // 2, pm)
        p.restore()
        return True

    def _draw_fallback_actor(self, p, a, st, x, y, s):
        """No rig, no sprites: the original simple figure, kept as the
        guaranteed-to-render floor for half-authored characters."""
        col = _rig.qcolor(st.body())
        pen = QPen(col)
        pen.setWidthF(max(1.6, 2.6 * s))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(x, y - 22 * s), 7 * s, 7 * s)
        p.drawLine(QPointF(x, y - 15 * s), QPointF(x, y + 6 * s))
        lean = math.cos(a.facing) * 8 * s
        p.drawLine(QPointF(x, y - 10 * s), QPointF(x + lean, y - 2 * s))
        p.drawLine(QPointF(x, y - 10 * s), QPointF(x - lean * 0.6, y - 1 * s))
        swing = math.sin(a.anim_t * 0.35) * 7 * s if a.anim == "run" else 3 * s
        p.drawLine(QPointF(x, y + 6 * s), QPointF(x + swing, y + 20 * s))
        p.drawLine(QPointF(x, y + 6 * s), QPointF(x - swing, y + 20 * s))

    def _guard_shell(self, p, st, x, y, s, deflect=False):
        """Guard/deflect shell: double ring in the character's accent, with
        a brighter leading arc when actively deflecting."""
        acc = st.accent()
        outer = QPen(_rig.qcolor(acc, 90))
        outer.setWidthF(2.0)
        p.setPen(outer)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(x, y), 28 * s, 28 * s)
        inner = QPen(QColor(255, 255, 255, 170 if deflect else 110))
        inner.setWidthF(2.6 if deflect else 1.6)
        p.setPen(inner)
        p.drawEllipse(QPointF(x, y), 23 * s, 23 * s)

    @staticmethod
    def _hp_bar(p, a, x, y, s):
        w = 34.0 * s
        frac = max(0.0, min(1.0, a.hp_frac))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawRect(QRectF(x - w / 2, y, w, 3.5 * s))
        p.setBrush(QColor(93, 255, 157) if frac > 0.35 else QColor(255, 99, 99))
        p.drawRect(QRectF(x - w / 2, y, w * frac, 3.5 * s))

    # -- HUD -----------------------------------------------------------
    def _paint_hud(self, p):
        w = self.world
        p.setPen(QColor(214, 218, 228, 190))
        f = QFont("Consolas", 9)
        p.setFont(f)
        lines = [
            "PB2  tick %d  %s" % (w.tick, "BATTLE" if w.battle_mode else "SOLO"),
            "actors %d   motes %d   frags %d in %d call(s)" % (
                w.stats["actors"], w.stats["motes"],
                self.last_stats["fragments"], self.last_stats["calls"]),
        ]
        if w.stats["faults"]:
            p.setPen(QColor(255, 99, 99))
            lines.append("FAULTS %d — see console" % w.stats["faults"])
        for i, line in enumerate(lines):
            p.drawText(14, 22 + i * 14, line)
