"""
Big ball - the tiny planet's curved look (camera.json "planet_ball", needs
the tiny planet).  The battle happens on the near face of a big ball, like a
globe with its pole on the top edge of the horizon (Daniel 2026-11-07):

  * The GROUND (dust, rubble on the floor, craters, trenches, rings, air FX,
    bullets: everything that isn't standing on it) is bent onto the ball.
    Ground lines running away from the camera are the globe's meridians:
    they curve round the ball and pinch to a point at the horizon's top,
    and the ground squeezes flat toward the horizon.  Nothing is cut: it
    shrinks into the horizon.
  * Things STANDING on the ground (boulders, fighters and the FX they carry,
    clones) are not bent: each is drawn whole at its spot on the ball,
    leaning with it and shrunk toward the horizon (planet_ball_horizon_size
    at the horizon .. full size on the fight's row).  They are never clipped,
    so they stick up past the horizon.

Screen space, after the camera (zoom / shake / shots stay as they are):

    px, py = the anchor on screen (the fight's row = the ball's equator)
    Rx     = planet_ball_radius_frac x screen width   (half-width of the ball)
    top    = planet_ball_top_frac x screen height    (the horizon's top)
    Ry     = py - top                                 (equator -> horizon top)

    lon = (x - px) / Rx                      (sideways round the ball)
    above the row (s = py - y > 0):  lat = s / Ry           (pole at 90 deg)
        drawn at (px + Rx sin lon cos lat,  py - Ry sin lat)
    on / below the row:
        drawn at (px + Rx sin lon,  y)

Speed band (laser/speedband.py; band depth D, 1 = the look above): only the
top share D of the way to the pole bends.  The ground stays flat for
s0 = (1 - D) x Ry x 90deg above the row, then rolls over a smaller ball of
radius D x Ry (smooth join, same pole in flat px):
    s <= s0:  lat = 0, drawn at (px + Rx sin lon, y)
    s >  s0:  lat = (s - s0) / (D Ry)
              drawn at (px + Rx sin lon cos lat,  py - s0 - D Ry sin lat)
so a slow world is near flat with its horizon high (off the top when D is
small) and a fast one is today's ball.  The ground layers use the world's D
(the slowest fighter's); a standing thing is PLACED by the world's D but
SIZED (and, for fighters, squashed) by its own observer D, so a fast
fighter shrinks toward the horizon on the slow world's ground.

A big Rx (default 3 x width) keeps the fight row nearly straight and full
width; smaller = the sides wrap round the ball too.  The screen's own edges
become the ball's outline, pinching to the horizon's top (lat 90, one point
above the anchor), so it leans with the fight when the anchor is off centre.
The ground image is painted with room above the screen (head) so the ground
reaches all the way to the pole.  Standing things: size
    k = h + (1 - h) * max(0, cos lat * cos lon)       h = horizon size
and lean outward by atan2(cos lat sin lon, 1 + sin lat).

The ground layers are painted into offscreen images and redrawn as
planet_ball_cols x planet_ball_bands affine cells (bands spread over the
bending latitudes; the flat part and below the row are one band each).
Drawing only: hit tests, walls, targeting and the battle snapshots stay in
plain screen coordinates.  The mouse cursor is mapped back (unwarp ->
Camera.screen_to_world).  The HUD is drawn after it, flat.  Solo + Battle.
"""

import math

_HALF_PI = math.pi * 0.5
LAT_MAX = math.radians(89.0)     # cells stop just short of the pole
D_MIN = 0.02                     # smallest band depth (a near-flat world)


class BallWarp:

    def __init__(self):
        self.geo = None         # (px, py, Rx, Ry, top, h, sw, sh) of this frame
        self.D = 1.0            # world band depth of this frame (laser/speedband.py)
        self.head = 0           # px of room painted above the screen (ground reaches the pole)
        self._key = None
        self._cells = []
        self._imgs = {}

    # --- per frame ----------------------------------------------------
    def setup(self, cam, sw, sh):
        """Work out this frame's ball from the camera (call after
        cam.view()).  True when the ball is on."""
        c = cam.cfg
        if not (c.get("planet_ball") and cam.planet_live()):
            self.geo = None
            return False
        sw, sh = float(sw), float(sh)
        rx = max(16.0, c["planet_ball_radius_frac"] * sw)
        top = c["planet_ball_top_frac"] * sh
        px, py = sw * 0.5, sh * 0.6
        if cam.anc is not None:
            px, py = cam.world_to_screen(cam.anc[0], cam.anc[1])
        py = max(top + 20.0, min(sh, py))
        ry = py - top
        self.D = max(D_MIN, min(1.0, float(getattr(cam, "band_D", 1.0) or 1.0)))
        self.geo = (px, py, rx, ry, top, c["planet_ball_horizon_size"], sw, sh)
        self.head = int(max(0.0, self._s_max() - py)) + 2
        return True

    def live(self):
        return self.geo is not None

    def _s0(self, d=None):
        """Flat px above the row before the bend starts (band depth d)."""
        d = self.D if d is None else d
        return (1.0 - d) * self.geo[3] * _HALF_PI

    def _s_max(self):
        """Flat px above the row where the cells stop (just short of the pole)."""
        return self._s0() + self.D * self.geo[3] * LAT_MAX

    def _lat(self, s, d):
        """Latitude of flat height s above the row for band depth d."""
        if s <= 0.0:
            return 0.0
        s0 = (1.0 - d) * self.geo[3] * _HALF_PI
        if s <= s0:
            return 0.0
        return min(_HALF_PI, (s - s0) / (d * self.geo[3]))

    def _latlon(self, x, y, d=None):
        px, py, rx = self.geo[:3]
        lon = max(-_HALF_PI, min(_HALF_PI, (x - px) / rx))
        return self._lat(py - y, self.D if d is None else d), lon

    def map(self, x, y):
        """A flat screen point -> where the ball draws it (world band)."""
        px, py, rx, ry = self.geo[:4]
        lon = max(-_HALF_PI, min(_HALF_PI, (x - px) / rx))
        s = py - y
        s0 = self._s0()
        if s <= s0:
            return px + rx * math.sin(lon), y
        R = self.D * ry
        lat = min(_HALF_PI, (s - s0) / R)
        return px + rx * math.sin(lon) * math.cos(lat), py - s0 - R * math.sin(lat)

    def stand(self, x, y, d=None):
        """(X, Y, k, lean_deg, lat) for a thing standing at flat screen
        (x, y): placed and leaning by the world band, sized by band depth d
        (None = the world's; laser/speedband.py)."""
        lat_w, lon = self._latlon(x, y)
        lat = lat_w if d is None or d <= self.D else self._latlon(x, y, max(D_MIN, min(1.0, d)))[0]
        h = self.geo[5]
        k = h + (1.0 - h) * max(0.0, math.cos(lat) * math.cos(lon))
        lean = math.degrees(math.atan2(math.cos(lat_w) * math.sin(lon), 1.0 + math.sin(lat_w)))
        X, Y = self.map(x, y)
        return X, Y, k, lean, lat

    def stand_transform(self, x, y, d=None, squash=0.0):
        """QTransform (screen space) that redraws a thing standing at flat
        screen (x, y) upright at its spot on the ball.  d = its band depth
        (None = the world's), squash = how much it flattens toward the
        horizon at the pole (0 = none)."""
        from PyQt5.QtGui import QTransform
        X, Y, k, lean, lat = self.stand(x, y, d)
        q = 1.0
        if squash > 0.0 and lat > 0.0:
            q = max(0.05, 1.0 - squash * (1.0 - math.cos(lat)))
        t = QTransform()
        t.translate(X, Y)
        t.rotate(lean)
        t.scale(k, k * q)
        t.translate(-x, -y)
        return t

    def unwarp(self, x, y):
        """A drawn screen point -> the flat screen point (cursor)."""
        if self.geo is None:
            return x, y
        px, py, rx, ry = self.geo[:4]
        sd = py - y
        s0 = self._s0()
        if sd <= s0:
            u = max(-1.0, min(1.0, (x - px) / rx))
            return px + math.asin(u) * rx, y
        R = self.D * ry
        lat = math.asin(max(0.0, min(1.0, (sd - s0) / R)))
        c = max(1e-3, math.cos(lat))
        u = max(-1.0, min(1.0, (x - px) / (rx * c)))
        return px + math.asin(u) * rx, py - s0 - lat * R

    def horizon_y(self, frac=0.97):
        """Flat screen y of the row frac of the way to the horizon's top
        (the pole is Ry x 90deg flat px above the row for every band)."""
        px, py, rx, ry = self.geo[:4]
        return py - ry * _HALF_PI * frac

    # --- drawing ------------------------------------------------------
    def _build(self, cols, bands):
        """[(QTransform, padded source QRectF)]: one affine cell per grid
        cell (fitted through the cell's centre and mid-edges), grown by its
        own corner error so neighbours overlap (no gaps).  Affine is ~2x
        faster than projective in Qt's raster engine; paint() draws them in
        Source mode so the overlaps never double up see-through pixels."""
        from PyQt5.QtCore import QRectF
        from PyQt5.QtGui import QTransform
        px, py, rx, ry, _top, _h, sw, sh = self.geo
        cells = []
        x_lo = max(0.0, px - _HALF_PI * rx)
        x_hi = min(sw, px + _HALF_PI * rx)
        if x_hi - x_lo < 1.0:
            return cells
        xs = [x_lo + (x_hi - x_lo) * i / cols for i in range(cols + 1)]
        # Rows: latitude bands over the bending part (the squeeze needs
        # them), one band over the flat part above the row (speed band) and
        # one straight band below the row.
        s_top = min(self._s_max(), py + self.head)
        s0 = self._s0()
        if s_top <= s0:
            ys = [py - s_top]
        else:
            ys = [py - s0 - (s_top - s0) * (1.0 - j / bands) for j in range(bands + 1)]
        if s0 > 0.5:
            ys.append(py)
        if py < sh - 0.5:
            ys.append(sh)
        m = self.map
        for j in range(len(ys) - 1):
            y0, y1 = ys[j], ys[j + 1]
            h = y1 - y0
            if h < 0.25:
                continue
            for i in range(cols):
                x0, x1 = xs[i], xs[i + 1]
                w = x1 - x0
                cx, cy = x0 + w * 0.5, y0 + h * 0.5
                C = m(cx, cy)
                L, R = m(x0, cy), m(x1, cy)
                T, B = m(cx, y0), m(cx, y1)
                exx, exy = (R[0] - L[0]) / w, (R[1] - L[1]) / w
                eyx, eyy = (B[0] - T[0]) / h, (B[1] - T[1]) / h
                dx = C[0] - exx * cx - eyx * cy
                dy = C[1] - exy * cx - eyy * cy
                err = 0.0
                for (qx, qy) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
                    tx, ty = m(qx, qy)
                    ax = exx * qx + eyx * qy + dx
                    ay = exy * qx + eyy * qy + dy
                    err = max(err, math.hypot(tx - ax, ty - ay))
                sc = max(1e-3, min(math.hypot(exx, exy), math.hypot(eyx, eyy)))
                pad = min(12.0, err / sc + 0.75)
                cells.append((QTransform(exx, exy, eyx, eyy, dx, dy),
                              QRectF(x0 - pad, y0 - pad, w + 2.0 * pad, h + 2.0 * pad)))
        return cells

    def image(self, w, h, dpr, slot=0):
        """A reused offscreen image (cleared); one per slot (ground / air),
        head px taller than the screen: paint into it translated down by
        self.head (the room above the screen)."""
        return self._img(("src", slot), w, h + self.head, dpr)

    def _img(self, key, w, h, dpr):
        from PyQt5.QtGui import QImage
        from PyQt5.QtCore import Qt
        iw, ih = max(1, int(round(w * dpr))), max(1, int(round(h * dpr)))
        img = self._imgs.get(key)
        if img is None or img.width() != iw or img.height() != ih:
            img = QImage(iw, ih, QImage.Format_ARGB32_Premultiplied)
            self._imgs[key] = img
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.transparent)
        return img

    def paint(self, p, img, cfg, dpr, slot=0):
        """Draw a ground image bent onto the ball through QPainter p (whose
        transform is the plain screen)."""
        from PyQt5.QtCore import QRectF
        from PyQt5.QtGui import QPainter
        if self.geo is None:
            return
        cols, bands = int(cfg["planet_ball_cols"]), int(cfg["planet_ball_bands"])
        key = tuple(round(v * 2.0) for v in self.geo) + (cols, bands, self.head, round(self.D * 400.0))
        if key != self._key:
            self._cells = self._build(cols, bands)
            self._key = key
        sw, sh = self.geo[6], self.geo[7]
        out = self._img(("out", slot), sw, sh, dpr)
        q = QPainter(out)
        try:
            # Hard cell edges + Source mode: overlapping cells replace each
            # other instead of stacking see-through pixels (no seams).
            q.setCompositionMode(QPainter.CompositionMode_Source)
            q.setRenderHint(QPainter.Antialiasing, False)
            q.setRenderHint(QPainter.SmoothPixmapTransform, True)
            hd = self.head
            for t, r in self._cells:
                q.setTransform(t)
                q.drawImage(r, img, QRectF(r.x() * dpr, (r.y() + hd) * dpr,
                                           r.width() * dpr, r.height() * dpr))
        finally:
            q.end()
        p.drawImage(QRectF(0.0, 0.0, sw, sh), out)
