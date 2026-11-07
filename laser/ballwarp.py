"""
Big ball - the tiny planet's curved look (camera.json "planet_ball", needs
the tiny planet).  The battle happens on top of a big ball: the finished
scene (fighters, FX, bullets, trails, terrain, dust, wireframe: everything
the camera draws) is bent onto the ball at paint time, so the ground curves
away over one horizon arc ABOVE the fight, things off to the side drop down
the curve and lean outward (they stand straight off the ball), and nothing
is drawn above the horizon (the desktop shows through there).

Screen space, after the camera (so zoom / shake / shots stay as they are):

    R      = planet_ball_radius_frac x screen width   (the horizon arc's radius)
    top    = planet_ball_top_frac x screen height    (the horizon's top on screen)
    C      = (px, top + R)          the ball's centre; px = the anchor's x on screen
    py     = the anchor's y on screen (the fight's row)
    Rref   = R - (py - top)         radius of the fight's row

    a scene point (x, y) is drawn at   C + r (sin phi, -cos phi)
        r   = R - (y - top)         (the horizon row lands on the arc)
        phi = (x - px) / Rref       (the fight's row keeps its lengths)

So vertical lines become radial (lean outward) and the fight's row keeps
its scale; the anchor's spot is drawn where it is.  The scene is painted
into an offscreen image and redrawn as planet_ball_cols x planet_ball_bands
wedge cells (one projective QTransform each, shared edges line up so there
are no seams).

Drawing only: hit tests, walls, targeting and the battle snapshots stay in
plain screen coordinates.  The mouse cursor is mapped back (unwarp ->
Camera.screen_to_world).  The HUD (HP bars, notices) is drawn after it,
unbent.  Identical in Solo and Battle.
"""

import math

_HALF_PI = math.pi * 0.5


class BallWarp:

    def __init__(self):
        self.geo = None         # (px, py, R, top, Rref, cy, y_bot, sw, sh) of this frame
        self._key = None
        self._cells = []        # [(QTransform, QRectF target, (x, y, w, h) source)]
        self._img = None

    # --- per frame ----------------------------------------------------
    def setup(self, cam, sw, sh):
        """Work out this frame's ball from the camera (call after
        cam.view()).  True when the ball is on."""
        c = cam.cfg
        if not (c.get("planet_ball") and cam.planet_live()):
            self.geo = None
            return False
        sw, sh = float(sw), float(sh)
        R = max(16.0, c["planet_ball_radius_frac"] * sw)
        top = c["planet_ball_top_frac"] * sh
        px, py = sw * 0.5, sh * 0.6
        if cam.anc is not None:
            px, py = cam.world_to_screen(cam.anc[0], cam.anc[1])
        py = max(top + 1.0, min(sh, py))
        rref = max(0.3 * R, R - (py - top))
        cy = top + R
        y_bot = min(sh, top + 0.97 * R)          # never past the ball's centre
        self.geo = (px, py, R, top, rref, cy, y_bot, sw, sh)
        return True

    def _map(self, x, y):
        px, _py, R, top, rref, cy = self.geo[:6]
        r = R - (y - top)
        phi = (x - px) / rref
        return px + r * math.sin(phi), cy - r * math.cos(phi)

    def unwarp(self, x, y):
        """A drawn screen point -> the unbent screen point (cursor)."""
        if self.geo is None:
            return x, y
        px, _py, R, top, rref, cy = self.geo[:6]
        dx, dy = x - px, cy - y
        r = math.hypot(dx, dy)
        phi = math.atan2(dx, dy)
        return px + phi * rref, top + R - r

    def _build(self, cols, bands):
        from PyQt5.QtCore import QPointF, QRectF
        from PyQt5.QtGui import QPolygonF, QTransform
        px, _py, R, top, rref, _cy, y_bot, sw, _sh = self.geo
        cells = []
        if y_bot - top < 1.0:
            return cells
        # Columns: whole screen width, cut to the side of the ball (|phi| < 90 deg).
        x_lo = max(0.0, px - _HALF_PI * rref)
        x_hi = min(sw, px + _HALF_PI * rref)
        if x_hi - x_lo < 1.0:
            return cells
        xs = [x_lo + (x_hi - x_lo) * i / cols for i in range(cols + 1)]
        ys = [top + (y_bot - top) * j / bands for j in range(bands + 1)]
        for j in range(bands):
            y0, y1 = ys[j], ys[j + 1]
            for i in range(cols):
                x0, x1 = xs[i], xs[i + 1]
                src = QPolygonF([QPointF(x0, y0), QPointF(x1, y0), QPointF(x1, y1), QPointF(x0, y1)])
                dst = QPolygonF([QPointF(*self._map(x0, y0)), QPointF(*self._map(x1, y0)),
                                 QPointF(*self._map(x1, y1)), QPointF(*self._map(x0, y1))])
                t = QTransform()
                if not QTransform.quadToQuad(src, dst, t):
                    continue
                cells.append((t, QRectF(x0, y0, x1 - x0, y1 - y0), (x0, y0, x1 - x0, y1 - y0)))
        return cells

    def image(self, w, h, dpr):
        """The reused offscreen scene image (cleared)."""
        from PyQt5.QtGui import QImage
        from PyQt5.QtCore import Qt
        iw, ih = max(1, int(round(w * dpr))), max(1, int(round(h * dpr)))
        img = self._img
        if img is None or img.width() != iw or img.height() != ih:
            img = QImage(iw, ih, QImage.Format_ARGB32_Premultiplied)
            self._img = img
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.transparent)
        return img

    def paint(self, p, img, cfg, dpr):
        """Draw the scene image bent onto the ball through QPainter p."""
        from PyQt5.QtCore import QRectF
        from PyQt5.QtGui import QPainter
        if self.geo is None:
            return
        cols, bands = int(cfg["planet_ball_cols"]), int(cfg["planet_ball_bands"])
        key = tuple(round(v * 2.0) for v in self.geo) + (cols, bands)
        if key != self._key:
            self._cells = self._build(cols, bands)
            self._key = key
        p.save()
        # Hard cell edges: anti-aliased edges would leave faint seams.
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        base = p.transform()
        for t, tgt, (sx, sy, sw_, sh_) in self._cells:
            p.setTransform(t * base)
            p.drawImage(tgt, img, QRectF(sx * dpr, sy * dpr, sw_ * dpr, sh_ * dpr))
        p.restore()
