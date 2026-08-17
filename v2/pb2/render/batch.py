"""Sprite atlas + fragment batching.

v1 issued one Python-level `drawPixmap` per visual object per frame.  At
62.5 Hz with a few hundred objects that is tens of thousands of Python->C++
boundary crossings per second — the real reason FX density had a ceiling.
The pixels were never the problem; the calls were.

`QPainter.drawPixmapFragments` takes an ARRAY of fragments against one
pixmap.  Each fragment carries position, source sub-rect, scaleX, scaleY,
rotation and opacity independently — which is exactly the set v2 needs for
position-based size scaling, rotation-to-facing and fade-out.  Qt documents
it as faster than repeated drawPixmap because the backend can optimise state
changes, and pyqtgraph uses this same call in this same binding to draw tens
of thousands of points.

So: every mote of a given (sprite, blend) pair becomes ONE call.

All sprites are generated procedurally at startup into a single atlas
pixmap, tinted per palette entry.  No PNG assets required for FX.
"""

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPixmap, QRadialGradient

__all__ = ["SpriteAtlas", "FragmentBatcher"]

_CELL = 64          # atlas cell size in px
_COLS = 8


class SpriteAtlas:
    """One QPixmap holding every procedurally drawn FX sprite.

    Cells are addressed by (shape, colour) and resolved to a source QRectF.
    Because every mote of any colour lives in the same pixmap, a whole frame
    of mixed-colour bullets is still a single draw call.
    """

    SHAPES = ("dot", "bullet", "bolt", "orb", "ring", "beam", "spark", "shard")

    def __init__(self, colors=(0xFFFFFF,), cell=_CELL):
        self.cell = cell
        self.colors = []
        self._index = {}
        self.pixmap = None
        self._build(list(dict.fromkeys(colors)))

    def _build(self, colors):
        self.colors = colors or [0xFFFFFF]
        n = len(self.SHAPES) * len(self.colors)
        rows = max(1, (n + _COLS - 1) // _COLS)
        pm = QPixmap(_COLS * self.cell, rows * self.cell)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        i = 0
        for ci, rgb in enumerate(self.colors):
            col = QColor((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255)
            for shape in self.SHAPES:
                cx = (i % _COLS) * self.cell
                cy = (i // _COLS) * self.cell
                self._index[(shape, rgb)] = QRectF(cx, cy, self.cell, self.cell)
                p.save()
                p.translate(cx, cy)
                self._paint_shape(p, shape, col)
                p.restore()
                i += 1
        p.end()
        self.pixmap = pm

    def _paint_shape(self, p, shape, col):
        c = self.cell
        h = c / 2.0
        if shape in ("dot", "bullet", "orb", "spark"):
            radius = {"dot": 0.16, "bullet": 0.26, "orb": 0.38, "spark": 0.12}[shape]
            g = QRadialGradient(h, h, c * radius)
            core = QColor(col)
            core.setAlpha(255)
            edge = QColor(col)
            edge.setAlpha(0)
            mid = QColor(255, 255, 255, 210) if shape != "spark" else QColor(col)
            g.setColorAt(0.0, mid)
            g.setColorAt(0.45, core)
            g.setColorAt(1.0, edge)
            p.setBrush(g)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(h, h), c * radius, c * radius)
        elif shape == "bolt":
            g = QRadialGradient(h, h, h)
            core = QColor(col)
            edge = QColor(col)
            edge.setAlpha(0)
            g.setColorAt(0.0, QColor(255, 255, 255, 235))
            g.setColorAt(0.35, core)
            g.setColorAt(1.0, edge)
            p.setBrush(g)
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(h - c * 0.34, h - c * 0.14, c * 0.68, c * 0.28))
        elif shape == "ring":
            pen = p.pen()
            pen.setColor(col)
            pen.setWidthF(c * 0.07)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(h, h), c * 0.38, c * 0.38)
        elif shape == "beam":
            g = QRadialGradient(h, h, h)
            edge = QColor(col)
            edge.setAlpha(0)
            g.setColorAt(0.0, QColor(255, 255, 255, 245))
            g.setColorAt(0.30, QColor(col))
            g.setColorAt(1.0, edge)
            p.setBrush(g)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(h - c * 0.44, h - c * 0.10,
                                     c * 0.88, c * 0.20), c * 0.1, c * 0.1)
        elif shape == "shard":
            p.setBrush(col)
            p.setPen(Qt.NoPen)
            from PyQt5.QtGui import QPolygonF
            poly = QPolygonF([QPointF(h, h - c * 0.34), QPointF(h + c * 0.16, h),
                              QPointF(h, h + c * 0.34), QPointF(h - c * 0.16, h)])
            p.drawPolygon(poly)

    def ensure_colors(self, colors):
        """Rebuild if a character introduces a palette entry we lack."""
        missing = [c for c in colors if (self.SHAPES[0], c) not in self._index]
        if missing:
            self._build(self.colors + missing)

    def rect(self, shape, rgb):
        r = self._index.get((shape, rgb))
        if r is None:
            r = self._index.get((shape, self.colors[0]))
        if r is None:
            r = self._index[(self.SHAPES[0], self.colors[0])]
        return r


class FragmentBatcher:
    """Accumulates PixmapFragments, then flushes them in one call.

    Usage per frame:
        batcher.begin()
        batcher.add(shape, rgb, x, y, scale, rotation, opacity)   # x N
        batcher.flush(painter)
    """

    __slots__ = ("atlas", "_frags", "calls", "fragments_drawn")

    def __init__(self, atlas):
        self.atlas = atlas
        self._frags = []
        self.calls = 0
        self.fragments_drawn = 0

    def begin(self):
        self._frags = []
        self.calls = 0
        self.fragments_drawn = 0

    def add(self, shape, rgb, x, y, scale=1.0, rotation=0.0, opacity=1.0):
        src = self.atlas.rect(shape, rgb)
        self._frags.append(
            QPainter.PixmapFragment.create(
                QPointF(x, y), src,
                float(scale), float(scale),
                float(rotation * 180.0 / math.pi),
                max(0.0, min(1.0, float(opacity)))))

    def flush(self, painter):
        """One drawPixmapFragments call for everything queued."""
        if not self._frags:
            return 0
        n = len(self._frags)
        painter.drawPixmapFragments(self._frags, self.atlas.pixmap)
        self.calls += 1
        self.fragments_drawn += n
        self._frags = []
        return n

    def __len__(self):
        return len(self._frags)
