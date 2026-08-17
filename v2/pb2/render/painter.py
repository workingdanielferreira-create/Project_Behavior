"""The paint pass.

RULE: painting reads simulation state and writes NOTHING.

v1's `_paint` aged sparks, rings, flashes and dots inline — so FX timing
depended on whether a frame was drawn, which blocked batching, blocked
interpolation and made the world unhashable.  Here, paint is pure.  A frame
that is skipped changes nothing.

Draw order (back to front):
    motes (batched)  ->  cue overlays  ->  actors  ->  HUD

Interpolation: the simulation runs on a fixed tick; the renderer draws
between the previous and current state using `alpha`, so motion stays smooth
even when render rate and tick rate differ.
"""

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen

from .batch import FragmentBatcher, SpriteAtlas
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


class Renderer:
    def __init__(self, world, show_hud=True):
        self.world = world
        self.atlas = SpriteAtlas(self._palette_colors(world))
        self.batcher = FragmentBatcher(self.atlas)
        self.show_hud = show_hud
        self.cue_overlays = []          # short-lived, owned by the renderer
        self.frame = 0
        self.last_stats = {"fragments": 0, "calls": 0}
        self._prev = {}                 # actor id -> (x, y) last tick

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
        that keeps painting pure."""
        alive = []
        for c in self.cue_overlays:
            c["t"] += 1
            if c["t"] < c["life"]:
                alive.append(c)
        self.cue_overlays = alive

    def remember_positions(self):
        self._prev = {a.id: (a.x, a.y) for a in self.world.all_actors()}

    # ------------------------------------------------------------------
    # paint
    # ------------------------------------------------------------------
    def paint(self, p, alpha=1.0):
        self.frame += 1
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        self._paint_motes(p)
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

    # -- cues: cosmetic overlays --------------------------------------
    def _paint_cues(self, p):
        for c in self.cue_overlays:
            f = c["t"] / max(1, c["life"])
            fade = max(0.0, 1.0 - f)
            name = c["name"]
            if name == "crescent":
                self._crescent(p, c, fade)
            elif name in ("ring", "burst"):
                pen = QPen(QColor(255, 194, 72, int(200 * fade)))
                pen.setWidthF(2.5)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                r = 18.0 + 120.0 * f * c["scale"]
                p.drawEllipse(QPointF(c["x"], c["y"]), r, r)
            elif name in ("flash", "muzzle"):
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, int(190 * fade)))
                r = 16.0 * c["scale"] * (1.0 - f * 0.5)
                p.drawEllipse(QPointF(c["x"], c["y"]), r, r)
            elif name == "impact":
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 120, 90, int(210 * fade)))
                p.drawEllipse(QPointF(c["x"], c["y"]), 6.0 * (1 + f), 6.0 * (1 + f))

    def _crescent(self, p, c, fade):
        pen = QPen(QColor(220, 245, 255, int(230 * fade)))
        pen.setWidthF(3.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        r = c["reach"]
        rect = QRectF(c["x"] - r, c["y"] - r, r * 2, r * 2)
        start = int((-c["angle"] * 180.0 / math.pi - 55) * 16)
        p.drawArc(rect, start, 110 * 16)

    # -- actors --------------------------------------------------------
    def _paint_actors(self, p, alpha):
        w = self.world
        for a in w.all_actors():
            px, py = self._prev.get(a.id, (a.x, a.y))
            x = px + (a.x - px) * alpha
            y = py + (a.y - py) * alpha

            if a.tags.has("state.vanished"):
                continue

            s = w.size_field.at(x, y) * a.attrs.get("scale")
            pal = a.visual.get("palette") or {}
            rgb = pal.get("primary", 0x39D5FF)
            col = QColor((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255)

            body_r = 12.0 * s
            # simple stick figure — sprite frames plug in here later
            pen = QPen(col)
            pen.setWidthF(max(1.6, 2.6 * s))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)

            head = QPointF(x, y - 22 * s)
            p.drawEllipse(head, 7 * s, 7 * s)
            p.drawLine(QPointF(x, y - 15 * s), QPointF(x, y + 6 * s))
            lean = math.cos(a.facing) * 8 * s
            p.drawLine(QPointF(x, y - 10 * s), QPointF(x + lean, y - 2 * s))
            p.drawLine(QPointF(x, y - 10 * s), QPointF(x - lean * 0.6, y - 1 * s))
            swing = math.sin(a.anim_t * 0.35) * 7 * s if a.anim == "run" else 3 * s
            p.drawLine(QPointF(x, y + 6 * s), QPointF(x + swing, y + 20 * s))
            p.drawLine(QPointF(x, y + 6 * s), QPointF(x - swing, y + 20 * s))

            if a.tags.has("state.guarding") or a.tags.has("state.deflecting"):
                gp = QPen(QColor(255, 255, 255, 150))
                gp.setWidthF(2.0)
                p.setPen(gp)
                p.drawEllipse(QPointF(x, y), 28 * s, 28 * s)

            if a.tags.has("player.controlled"):
                mp = QPen(QColor(255, 194, 72, 220))
                mp.setWidthF(2.0)
                p.setPen(mp)
                p.drawEllipse(QPointF(x, y + 24 * s), 10 * s, 4 * s)

            self._hp_bar(p, a, x, y - 36 * s, s)

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
