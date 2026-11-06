"""
World wireframe overlay (World Camera setting `wireframe`, camera.json;
FX Studio: World Camera tab, group "Wireframe overlay").

A debug view of how the environment acts on the fighters, drawn IN THE
SCENE (through the camera, so zoom, punch-in, shake and the depth tilt warp
it exactly as they warp the world), over everything but the HUD.  Solo and
Battle alike.  It reads the live settings every frame, so an edit in the
Studio (hot-reloaded ~1 s) shows straight away.

Every part is owned by the setting(s) it shows; camera.json "wire_off"
(FX Studio: the tick box beside each setting while the wireframe is on)
hides a part when ANY of its owners is unticked (camera.WIRE_KEYS).

Layers (each its own colour):
  * Scaling grid (cyan): a plain scene grid (shows the camera's warp),
    size contours of combat.position_scale (x0.5, x1, x2 ...) and, at a
    coarse grid of spots, a bar as tall as a fighter would be drawn there
    with its size / pace; under the tiny planet each spot's ring is
    squashed exactly as the world layers are.
  * Anchor & planet (magenta): the world anchor, the planet horizon and
    squash rings (or the anchor's far-distance ring), lines to each fighter;
    the depth tilt's near / far lines and its anchor A with strength k.
  * Roll zones (orange): the outer zone_x_frac / zone_y_frac bands that roll the world, and
    the current roll direction / speed.
  * Camera & boulders (green / yellow): the follow-cam framing box (+margin)
    and the view at its current zoom; the pillar spawn radius, every
    fighter's clear zone, each pillar's collision footprint, gap and HP,
    and the respawn countdown.
"""

import math

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QFont, QPen, QPolygonF

from . import combat, config, worldfx, worldscale
from .camera import SHOTS

CYAN = (79, 209, 255)
MAGENTA = (255, 95, 210)
ORANGE = (255, 160, 64)
GREEN = (125, 255, 106)
YELLOW = (255, 225, 77)

GRID = 120          # plain scene grid spacing (px)
SAMPLE = 60         # contour sampling step (px)
SPOTS = 240         # size-bar spots spacing (px)
# The settings that shape the size rule (contours and size bars).
SIZE_KEYS = ("vscale_bottom", "vscale_top", "scale_min", "scale_max")
LEVELS = (0.1, 0.15, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0)
TICK_S = config.TICK_MS / 1000.0


def _pen(rgb, a, w, dash=False):
    pen = QPen(QColor(rgb[0], rgb[1], rgb[2], a), w)
    pen.setCosmetic(True)              # constant on-screen width at any zoom
    if dash:
        pen.setStyle(Qt.DashLine)
    return pen


class _Painter:
    def __init__(self, p, zoom):
        self.p = p
        self.z = max(0.2, zoom)
        f = QFont("Consolas")
        f.setPixelSize(max(6, int(round(12.0 / self.z))))
        f.setBold(True)
        self.font = f
        self.bounds = None         # (x0, y0, x1, y1) of the visible view (scene)
        self.sx = self.sy = 0.0    # status lines: the view's top-left corner
        self.n = 0
        self.off = set()           # camera.json wire_off: unticked owners

    def on(self, *keys):
        """A part is drawn unless ANY of its owning settings is unticked."""
        return not any(k in self.off for k in keys)

    def status(self, text, rgb):
        """A line of the status stack in the view's top-left corner."""
        self.n += 1
        self.label(self.sx, self.sy + self.n * 16.0 / self.z, text, rgb)

    def label(self, x, y, text, rgb):
        p = self.p
        p.setFont(self.font)
        fm = p.fontMetrics()
        w = fm.horizontalAdvance(text) if hasattr(fm, "horizontalAdvance") else fm.width(text)
        h = fm.height()
        pad = 2.0 / self.z
        if self.bounds is not None:       # keep it inside the visible view
            bx0, by0, bx1, by1 = self.bounds
            x = max(bx0 + 4.0 / self.z, min(bx1 - w - 4.0 / self.z, x))
            y = max(by0 + h, min(by1 - 4.0 / self.z, y))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRect(QRectF(x - pad, y - h + fm.descent() - pad, w + 2 * pad, h + 2 * pad))
        p.setPen(QColor(rgb[0], rgb[1], rgb[2], 235))
        p.drawText(QPointF(x, y), text)

    def line(self, x0, y0, x1, y1):
        self.p.drawLine(QPointF(x0, y0), QPointF(x1, y1))

    def circle(self, x, y, r, ry=None):
        self.p.setBrush(Qt.NoBrush)
        self.p.drawEllipse(QPointF(x, y), r, r if ry is None else ry)

    def arrow(self, x0, y0, x1, y1):
        self.line(x0, y0, x1, y1)
        a = math.atan2(y1 - y0, x1 - x0)
        s = 12.0 / self.z
        for da in (2.6, -2.6):
            self.line(x1, y1, x1 + math.cos(a + da) * s, y1 + math.sin(a + da) * s)


def _figs(world):
    out = []
    for f in world.all_figures():
        tr = getattr(f, "transform", None)
        if tr is None or not getattr(tr, "init", True):
            continue
        out.append(f)
    return out


# ------------------------------------------------------------ scaling grid
def _contours(sw, sh):
    """{level: [(x0, y0, x1, y1), ...]}: marching squares over
    combat.position_scale sampled every SAMPLE px."""
    nx, ny = int(sw // SAMPLE) + 2, int(sh // SAMPLE) + 2
    xs = [min(sw, i * SAMPLE) for i in range(nx)]
    ys = [min(sh, j * SAMPLE) for j in range(ny)]
    v = [[combat.position_scale(x, y, sw, sh) for x in xs] for y in ys]
    lo = min(min(r) for r in v)
    hi = max(max(r) for r in v)
    out = {}
    for L in LEVELS:
        if not (lo < L < hi):
            continue
        segs = []
        for j in range(ny - 1):
            for i in range(nx - 1):
                c = ((xs[i], ys[j], v[j][i]), (xs[i + 1], ys[j], v[j][i + 1]),
                     (xs[i + 1], ys[j + 1], v[j + 1][i + 1]), (xs[i], ys[j + 1], v[j + 1][i]))
                pts = []
                for k in range(4):
                    a, b = c[k], c[(k + 1) % 4]
                    if (a[2] - L) * (b[2] - L) < 0.0:
                        t = (L - a[2]) / (b[2] - a[2])
                        pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
                if len(pts) >= 2:
                    segs.append((pts[0][0], pts[0][1], pts[1][0], pts[1][1]))
                if len(pts) == 4:
                    segs.append((pts[2][0], pts[2][1], pts[3][0], pts[3][1]))
        if segs:
            out[L] = segs
    return out


def _scaling(d, sw, sh):
    p = d.p
    # Plain scene grid: the camera / depth tilt warp shows on it.
    if d.on("wire_grid"):
        p.setPen(_pen(CYAN, 40, 1))
        x = 0.0
        while x <= sw:
            d.line(x, 0, x, sh)
            x += GRID
        y = 0.0
        while y <= sh:
            d.line(0, y, sw, y)
            y += GRID
        p.setPen(_pen(CYAN, 120, 1.5))
        d.line(0, 0, sw, 0)
        d.line(sw, 0, sw, sh)
        d.line(sw, sh, 0, sh)
        d.line(0, sh, 0, 0)
    size_on = d.on(*SIZE_KEYS)
    pace_on = d.on("speed_min", "speed_max")
    # Size contours.
    if size_on:
        for L, segs in _contours(sw, sh).items():
            p.setPen(_pen(CYAN, 170 if L == 1.0 else 110, 2.0 if L == 1.0 else 1.2))
            for s in segs:
                d.line(*s)
            m = segs[len(segs) // 2]
            d.label(m[0] + 3, m[1] - 3, "size x%g" % L, CYAN)
    # Size bars: as tall as a fighter would be drawn here; planet squash ring.
    ring_on = worldscale.planet_on() and d.on("planet_squash")
    if not (size_on or pace_on or ring_on):
        return
    sq = worldscale.squasher(p, sw)
    y = SPOTS * 0.5
    while y < sh:
        x = SPOTS * 0.5
        while x < sw:
            s = combat.position_scale(x, y, sw, sh)
            sp = combat.position_speed_scale(x, y, sw, sh)
            if size_on:
                p.setPen(_pen(CYAN, 200, 2))
                d.line(x, y, x, y - 20.0 * s)
                d.line(x - 4, y, x + 4, y)
            if ring_on:
                sq.at(x, y)
                p.setPen(_pen(CYAN, 160, 1.2))
                d.circle(x, y, 9.0 * s)
                sq.done()
            txt = " ".join(t for t, on in (("x%.2f" % s, size_on), ("%d%%" % int(round(sp * 100)), pace_on)) if on)
            if txt:
                d.label(x + 5, y - 2, txt, CYAN)
            x += SPOTS
        y += SPOTS


# ------------------------------------------------------------ anchor / planet / depth
def _reach(d, ax, ay, rx, ry, kx, ky, rgb, what):
    """The x / y reach of an ellipse as two labelled radius lines, each
    owned by its own setting (kx / ky)."""
    p = d.p
    p.setPen(_pen(rgb, 200, 1.5))
    if d.on(kx):
        d.arrow(ax, ay, ax + rx, ay)
        d.label(ax + rx * 0.5, ay - 4, "%s x %d px" % (what, rx), rgb)
    if d.on(ky):
        d.arrow(ax, ay, ax, ay - ry)
        d.label(ax + 4, ay - ry * 0.5, "%s y %d px" % (what, ry), rgb)


def _anchor(d, world, figs, cam, view, sw, sh):
    p = d.p
    c = cam.cfg
    if worldscale.active():
        ax, ay = worldscale._A[0], worldscale._A[1]
        if d.on("anchor_scale"):
            p.setPen(_pen(MAGENTA, 120, 1, True))
            for f in figs:
                d.line(ax, ay, f.transform.x, f.transform.y)
                dist = math.hypot(f.transform.x - ax, f.transform.y - ay)
                d.label((ax + f.transform.x) / 2, (ay + f.transform.y) / 2, "%d px" % dist, MAGENTA)
            p.setPen(_pen(MAGENTA, 230, 2))
            r = 14.0 / d.z
            d.line(ax - r, ay, ax + r, ay)
            d.line(ax, ay - r, ax, ay + r)
            d.circle(ax, ay, r * 0.6)
            d.label(ax + r, ay - r, "ANCHOR", MAGENTA)
        if worldscale.planet_on():
            pl = worldscale._A[12]
            rx, ry = pl[0][0] * sw, pl[0][1] * sw
            if d.on("planet", "planet_reach_x_frac", "planet_reach_y_frac"):
                p.setPen(_pen(MAGENTA, 210, 2))
                d.circle(ax, ay, rx, ry)
                if d.on("planet_horizon_deg"):
                    d.label(ax + 4, ay - ry - 4, "planet horizon %g deg" % c["planet_horizon_deg"], MAGENTA)
            if d.on("planet_far"):
                d.label(ax + 4, ay + ry + 14 / d.z, "size x%g at the horizon" % c["planet_far"], MAGENTA)
            _reach(d, ax, ay, rx, ry, "planet_reach_x_frac", "planet_reach_y_frac", MAGENTA, "horizon")
            if d.on("planet_squash"):
                p.setPen(_pen(MAGENTA, 120, 1, True))
                for fr in (1.0 / 3.0, 2.0 / 3.0):
                    th = fr * pl[2]
                    k = max(0.05, min(1.0, 1.0 - pl[4] * (1.0 - math.cos(th))))
                    d.circle(ax, ay, rx * fr, ry * fr)
                    d.label(ax + rx * fr * 0.71 + 4, ay + ry * fr * 0.71, "squash x%.2f" % k, MAGENTA)
        else:
            rx, ry = c["dscale_far_x_frac"] * sw, c["dscale_far_y_frac"] * sw
            if d.on("dscale_far", "dscale_far_x_frac", "dscale_far_y_frac"):
                p.setPen(_pen(MAGENTA, 170, 1.5, True))
                d.circle(ax, ay, rx, ry)
                d.label(ax + 4, ay - ry - 4, "far distance: x%g" % c["dscale_far"], MAGENTA)
            _reach(d, ax, ay, rx, ry, "dscale_far_x_frac", "dscale_far_y_frac", MAGENTA, "far")
            if d.on("dscale_curve"):
                k = c["dscale_near"] + (c["dscale_far"] - c["dscale_near"]) * (0.5 ** c["dscale_curve"])
                p.setPen(_pen(MAGENTA, 90, 1, True))
                d.circle(ax, ay, rx * 0.5, ry * 0.5)
                d.label(ax - rx * 0.35, ay + ry * 0.5 + 14 / d.z, "half way: x%.2f (curve %g)" % (k, c["dscale_curve"]), MAGENTA)
            if d.on("dscale_near"):
                d.label(ax + 16 / d.z, ay + 18 / d.z, "on-anchor x%g" % c["dscale_near"], MAGENTA)
    elif d.on("anchor_scale"):
        d.status("anchor scaling OFF: corner-grid sizes", MAGENTA)
    # Depth tilt: lines of equal depth, near -> far, and its anchor A.
    if cam.depth_live() and view is not None:
        k, Ax, Ay = view[6], view[7], view[8]
        if d.on("depth"):
            p.setPen(_pen(MAGENTA, 70, 1, True))
            if c["anchor_scale"]:
                for i in range(1, 6):
                    yy = sh * i / 6.0
                    d.line(0, yy, sw, yy)
                d.arrow(sw * 0.97, sh * 0.9, sw * 0.97, sh * 0.1)
                d.label(sw * 0.97 - 120 / d.z, sh * 0.1 - 6, "near -> far", MAGENTA)
            else:
                for i in range(1, 6):
                    t = i / 6.0
                    d.line(0, sh * t * 2, sw * t * 2, 0)
                d.arrow(sw * 0.1, sh * 0.9, sw * 0.9, sh * 0.1)
                d.label(sw * 0.5, sh * 0.5, "near -> far", MAGENTA)
        if d.on("depth_base", "depth_gain", "depth_shot"):
            p.setPen(_pen(MAGENTA, 230, 2))
            d.circle(Ax, Ay, 10.0 / d.z)
            d.label(Ax + 12 / d.z, Ay + 14 / d.z, "depth A  k=%.2f" % k, MAGENTA)
    elif not d.on("depth"):
        pass
    elif c["depth"] and cam.planet_live():
        d.status("depth tilt replaced by the tiny planet", MAGENTA)
    elif getattr(cam, "depth_suspended", False):
        d.status("depth tilt suspended (paint budget)", MAGENTA)


# ------------------------------------------------------------ roll zones
def _roll(d, world, sw, sh):
    p = d.p
    R = worldfx.WORLD.get("roll") or {}
    if not R.get("enabled"):
        if d.on("roll.enabled"):
            d.status("rolling world OFF", ORANGE)
        return
    zx = max(0.05, min(0.5, R["zone_x_frac"]))
    zy = max(0.05, min(0.5, R["zone_y_frac"]))
    spd_txt = " (max %d px/s)" % R["max_speed"] if d.on("roll.max_speed") else ""
    p.setPen(_pen(ORANGE, 170, 1.5))
    p.setBrush(QColor(ORANGE[0], ORANGE[1], ORANGE[2], 22))
    if d.on("roll.zone_x_frac"):
        p.drawRect(QRectF(0, 0, sw * zx, sh))
        p.drawRect(QRectF(sw * (1 - zx), 0, sw * zx, sh))
        p.setBrush(Qt.NoBrush)
        d.label(8, sh * 0.5, "roll zone x %.2f: world rolls ->" % zx, ORANGE)
        d.label(sw * (1 - zx) + 8, sh * 0.5, "<- world rolls" + spd_txt, ORANGE)
    if R.get("vertical") and d.on("roll.zone_y_frac", "roll.vertical"):
        p.setBrush(QColor(ORANGE[0], ORANGE[1], ORANGE[2], 22))
        p.drawRect(QRectF(0, 0, sw, sh * zy))
        p.drawRect(QRectF(0, sh * (1 - zy), sw, sh * zy))
        p.setBrush(Qt.NoBrush)
        d.label(sw * 0.5, sh * zy - 6, "roll zone y %.2f (vertical)%s" % (zy, spd_txt), ORANGE)
    p.setBrush(Qt.NoBrush)
    # Off-screen: where pillars are dropped / raised (seen when zoomed out).
    mg, ah = R["margin_px"], R["spawn_ahead_px"]
    p.setPen(_pen(ORANGE, 110, 1, True))
    if d.on("roll.margin_px"):
        for xx in (-mg, sw + mg):
            d.line(xx, 0, xx, sh)
    if d.on("roll.spawn_ahead_px"):
        for xx in (-mg - ah, sw + mg + ah):
            d.line(xx, 0, xx, sh)
    st = getattr(world, "terrain", None)
    if st is not None and d.on("roll.max_speed"):
        vx, vy = st.roll_v
        spd = math.hypot(vx, vy) / TICK_S
        if spd > 1.0:
            figs = _figs(world)
            cx, cy = st._centre(figs) if figs else (sw * 0.5, sh * 0.5)    # what the roll reads
            L = min(260.0, 40.0 + spd * 0.3)
            p.setPen(_pen(ORANGE, 240, 3))
            d.arrow(cx, cy, cx + vx / max(1e-6, math.hypot(vx, vy)) * L, cy + vy / max(1e-6, math.hypot(vx, vy)) * L)
            d.label(cx + 10, cy + 22 / d.z, "rolling %d px/s" % spd, ORANGE)


# ------------------------------------------------------------ camera & boulders
def _camera(d, world, figs, cam, view, sw, sh):
    p = d.p
    c = cam.cfg
    if figs and c["follow"] and d.on("follow"):
        x0, x1 = min(f.transform.x for f in figs), max(f.transform.x for f in figs)
        y0, y1 = min(f.transform.y for f in figs), max(f.transform.y for f in figs)
        mx, my = c["margin_x_px"], c["margin_y_px"]
        p.setPen(_pen(GREEN, 200, 1.5, True))
        if d.on("margin_x_px"):          # left / right sides: the x margin
            d.line(x0 - mx, y0 - my, x0 - mx, y1 + my)
            d.line(x1 + mx, y0 - my, x1 + mx, y1 + my)
        if d.on("margin_y_px"):          # top / bottom sides: the y margin
            d.line(x0 - mx, y0 - my, x1 + mx, y0 - my)
            d.line(x0 - mx, y1 + my, x1 + mx, y1 + my)
        if c["anchor_scale"]:
            zk, zt = "anchor_zoom", "anchor pan zoom x%g" % c["anchor_zoom"]
        elif getattr(world, "battle_mode", False):
            zk, zt = "max_zoom", "battle max zoom x%g" % c["max_zoom"]
        else:
            zk, zt = "solo_zoom", "solo zoom x%g" % c["solo_zoom"]
        parts = ["framing"]
        if d.on("margin_x_px"):
            parts.append("+%d x" % mx)
        if d.on("margin_y_px"):
            parts.append("+%d y" % my)
        if d.on(zk):
            parts.append("- " + zt)
        d.label(x0 - mx + 4, y0 - my - 4, " ".join(parts), GREEN)
    if view is not None:
        cx, cy, z = view[0], view[1], view[2]
        hw, hh = sw / (2.0 * z), sh / (2.0 * z)
        ins = 6.0 / d.z
        parts = []
        if d.on("wire_view"):
            p.setPen(_pen(GREEN, 230, 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(cx - hw + ins, cy - hh + ins, 2 * hw - 2 * ins, 2 * hh - 2 * ins))
            parts.append("view x%.2f" % z)
        if abs(view[3]) > 0.05 and d.on("punch", "punch_tilt_deg"):
            parts.append("roll %.1f deg" % view[3])
        s = cam.shot
        if s is not None and s.env > 0.0:
            pre = SHOTS.get(s.kind)
            if pre is None or d.on(pre[0] + "_on"):
                parts.append("shot: %s" % s.kind)
        if cam.trauma > 0.01 and d.on("shake", "shake_max_px"):
            parts.append("shake %.2f" % cam.trauma)
        if parts:
            d.label(cx - hw + ins + 4, cy + hh - ins - 6, "  ".join(parts), GREEN)
    elif d.on("wire_view"):
        d.status("view x1.00 (camera at rest)", GREEN)


def _boulders(d, world, figs, sw, sh):
    p = d.p
    P = worldfx.WORLD.get("pillars") or {}
    st = getattr(world, "terrain", None)
    if not P.get("enabled") or not worldfx.WORLD["ground"]["enabled"]:
        if d.on("pillars.enabled"):
            d.status("pillars OFF", YELLOW)
        return
    if figs and st is not None:
        cx, cy = st._centre(figs)
        rx, ry = P["radius_x_px"], P["radius_y_px"]
        if d.on("pillars.radius_x_px", "pillars.radius_y_px"):
            p.setPen(_pen(YELLOW, 150, 1.5, True))
            d.circle(cx, cy, rx, ry)
            d.label(cx + 4, cy - ry - 4, "pillar spawn ellipse", YELLOW)
        _reach(d, cx, cy, rx, ry, "pillars.radius_x_px", "pillars.radius_y_px", YELLOW, "spawn")
        kx, ky = P["clear_x_px"], P["clear_y_px"]
        if d.on("pillars.clear_x_px", "pillars.clear_y_px"):
            p.setPen(_pen(YELLOW, 110, 1, True))
            for f in figs:
                d.circle(f.transform.x, f.transform.y, kx, ky)
        f = figs[0]
        _reach(d, f.transform.x, f.transform.y, kx, ky, "pillars.clear_x_px", "pillars.clear_y_px", YELLOW, "clear")
    if st is None:
        return
    G = worldfx.WORLD["ground"]
    seen = set()
    for q in st.pillars:
        hw = q.half_w(P)
        fl = max(0.2, worldfx.flat_at(q.ps, G))
        lift = q.lift(P)
        if lift < 2.0 and d.on("pillars.width"):
            p.setPen(_pen(YELLOW, 230, 1.8))
            d.circle(q.x, q.y, hw, hw * fl)           # what blocks the fighters' feet
        ax = q.axis(P)
        if d.on("pillars.width", "pillars.height"):
            p.setPen(_pen(YELLOW, 160, 1.2))
            d.line(ax[0] - ax[4], ax[1], ax[0] - ax[4], ax[3])    # projectile / melee body
            d.line(ax[0] + ax[4], ax[1], ax[0] + ax[4], ax[3])
            d.line(ax[0] - ax[4], ax[1], ax[0] + ax[4], ax[1])
        if d.on("pillars.hp"):
            d.label(q.x + hw + 3, ax[1] + 12 / d.z, "%d/%d" % (max(0, q.hp), q.hp0), YELLOW)
        g = id(q.cl) if q.cl is not None else id(q)
        if g not in seen and lift < 2.0:
            seen.add(g)
            if d.on("pillars.gap_x_px", "pillars.gap_y_px"):
                p.setPen(_pen(YELLOW, 60, 1, True))
                d.circle(q.x, q.y, P["gap_x_px"], P["gap_y_px"])
            if q.cl is not None and d.on("pillars.multi_chance"):
                n = sum(1 for o in st.pillars if o.cl is q.cl)
                d.label(q.x - hw, q.y + hw * fl + 14 / d.z, "multi-part: %d blocks" % n, YELLOW)
    if not d.on("pillars.count"):
        return
    ng, want = st._groups(), int(P["count"])
    txt = "pillars %d / %d" % (ng, want)
    if ng < want:
        if st.roll_v[0] or st.roll_v[1]:
            txt += "  (rolling: new ones rise off the far side)"
        elif d.on("pillars.respawn_s"):
            left = max(0, st.next_spawn - st.t) * TICK_S
            txt += "  next in %.1f s" % left
    d.status(txt, YELLOW)


# ------------------------------------------------------------ entry
def paint(p, world):
    """Overlay._paint_scene, inside the camera transform, after the scene."""
    cam = getattr(world, "camera", None)
    if cam is None or not cam.cfg.get("wireframe"):
        return
    sw, sh = float(world.screen_w), float(world.screen_h)
    if sw <= 0 or sh <= 0:
        return
    view = getattr(cam, "_view", None)
    figs = _figs(world)
    p.save()
    try:
        p.setRenderHint(p.Antialiasing, True)
        d = _Painter(p, view[2] if view is not None else 1.0)
        d.off = set(cam.cfg.get("wire_off") or ())
        if view is not None:
            hw, hh = sw / (2.0 * view[2]), sh / (2.0 * view[2])
            d.bounds = (view[0] - hw, view[1] - hh, view[0] + hw, view[1] + hh)
        else:
            d.bounds = (0.0, 0.0, sw, sh)
        d.sx = d.bounds[0] + 14.0 / d.z
        d.sy = d.bounds[1] + 40.0 / d.z
        _scaling(d, sw, sh)
        _roll(d, world, sw, sh)
        _boulders(d, world, figs, sw, sh)
        _anchor(d, world, figs, cam, view, sw, sh)
        _camera(d, world, figs, cam, view, sw, sh)
    finally:
        p.restore()
