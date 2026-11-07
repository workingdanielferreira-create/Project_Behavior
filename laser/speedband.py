"""
Speed band + speed barrier - the big ball's bend follows the fighters'
speeds (camera.json "band" / "barrier", World Camera tab group "Speed band
& barrier"; needs the big ball).  Daniel 2026-11-07.

The world is seen by the SLOWEST fighter; a faster fighter is seen by that
slow fighter (forced perspective):

  * World band.  The slowest fielded fighter's BASE speed (its movement
    stat, not its live speed) sets how deep the horizon's bend reaches down
    the screen: band_depth_slow at band_speed_slow (or slower) .. 1.0 = the
    full ball (today's look) at band_speed_fast (or faster).  Eased over
    band_ease_s (tag switches, KOs).  The ground, boulders, rubble, dust and
    every world layer are drawn with it (laser/ballwarp.py: flat ground,
    then a smaller ball over the top share of the screen; laser/worldscale.py:
    the planet size / squash only in the outer share round the anchor).
  * Fighter band.  Each fighter's own base speed sets its own depth (never
    less than the world's).  The fighter, and the FX it fires that TRAVEL
    (bullets, crescents, FX Studio travel / homing / zigzag), are drawn with
    it: a fast fighter shrinks and squashes toward the horizon while the
    ground under it stays the slow world's.  Every band gives the same
    size near the fight row, so fighters meet at matching scale.
  * Pace is NOT banded: movement keeps today's rule (worldscale.speed reads
    the full ball), so this is drawing only.

Speed barrier (the screen-edge wall's top, made a speed gradient):

    an ellipse centred on the bottom middle of the screen,
    barrier_rx_frac x width wide, barrier_ry_frac x height tall (outer edge);
    its inner band (thickness barrier_depth_slow .. _fast of the radius,
    following the world band) is the barrier.

    r     = how deep a fighter is in the band (0 inner edge .. 1 outer edge)
    v     = its LIVE speed (smoothed movement per tick, divided by the
            position pace so the slowdown near the top does not count;
            blinks / teleports ignored)
    allow = clamp((v - barrier_speed_lo) / (barrier_speed_hi - barrier_speed_lo))

  Moving in deeper than allow: held there (like the wall; a knockback
  slide reflects).  Deeper than allow because it was faster a moment ago:
  eased back out over barrier_return_s, while the rolling world (Dust & Air
  "roll") rolls toward the camera (from the barrier toward the bottom
  middle) faster by up to barrier_roll x roll max_speed, so it still looks
  like travelling on.  Fighters only (FX fly on); F11's puppet and F10's
  freeze are left alone.

Solo and Battle: the same code (Solo = the lone fighter is the slowest).
Simulation side once per tick in Overlay._tick (after both sides and the
puppet, before terrain.step); paint side via the helpers below.
"""

import math

from . import config
from . import worldscale

TICK_S = config.TICK_MS / 1000.0
JUMP_PX = 60.0          # a step longer than this is a blink / teleport: not speed
RISE = 0.5              # live speed: share of a rise taken per tick
FALL = 0.15             # ... of a fall


def _clamp01(v):
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _frac(v, lo, hi):
    if hi - lo < 1e-6:
        return 1.0 if v >= hi else 0.0
    return _clamp01((v - lo) / (hi - lo))


def base_speed(fig):
    """The fighter's movement stat (an action's move_speed_pct excluded)."""
    r = getattr(fig, "act", None)
    b = getattr(r, "base_speed", None) if r is not None else None
    if b is None:
        b = getattr(fig.motion, "speed", 3.0)
    try:
        return float(b)
    except (TypeError, ValueError):
        return 3.0


class _Fig:
    __slots__ = ("lx", "ly", "v", "cap", "D", "r", "allow")

    def __init__(self, x, y):
        self.lx, self.ly = x, y
        self.v = 0.0
        self.cap = 1.0          # fielded inside the barrier: eased out, not snapped
        self.D = 1.0
        self.r = 0.0
        self.allow = 0.0


class SpeedBand:
    """World-owned state (World.speedband, made on first step)."""

    def __init__(self):
        self.wf = None          # eased world speed share 0..1 (None = first sight)
        self.D = 1.0            # world band depth (1 = full ball)
        self.slow = None        # slowest fielded base speed (wireframe)
        self.figs = {}          # id(fig) -> _Fig
        self.over = None        # (amount 0..1, nx, ny): strongest overshoot, inward normal
        self.live = False
        self.bar = False

    # ---- geometry ---------------------------------------------------------
    def geom(self, c, sw, sh):
        """(cx, cy, rx, ry, thickness) of the barrier ellipse."""
        wf = self.wf if self.wf is not None else 1.0
        T = c["barrier_depth_slow"] + (c["barrier_depth_fast"] - c["barrier_depth_slow"]) * wf
        return (sw * 0.5, float(sh), max(8.0, c["barrier_rx_frac"] * sw),
                max(8.0, c["barrier_ry_frac"] * sh), max(0.01, min(0.95, T)))

    @staticmethod
    def depth_at(x, y, g):
        """(r, u, gx, gy): depth in the barrier band (<0 = inside, free) and
        the ellipse gradient (outward) at (x, y)."""
        cx, cy, rx, ry, T = g
        dx, dy = (x - cx) / rx, (y - cy) / ry
        u = math.hypot(dx, dy)
        return (u - (1.0 - T)) / T, u, dx / rx, dy / ry

    # ---- per tick ---------------------------------------------------------
    def step(self, w):
        cam = w.camera
        c = cam.cfg
        self.live = bool(c.get("band") and c.get("planet_ball") and cam.planet_live())
        self.bar = bool(self.live and c.get("barrier"))
        figs = list(w.all_figures())
        seen = set()
        if figs:
            slow = min(base_speed(f) for f in figs)
            self.slow = slow
            tgt = _frac(slow, c["band_speed_slow"], c["band_speed_fast"])
            if self.wf is None:
                self.wf = tgt
            else:
                e = 1.0 - math.exp(-3.0 * TICK_S / max(0.02, c["band_ease_s"]))
                self.wf += (tgt - self.wf) * e
        dmin = c["band_depth_slow"]
        wf = self.wf if self.wf is not None else 1.0
        self.D = (dmin + (1.0 - dmin) * wf) if self.live else 1.0
        cam.band_D = self.D
        sw, sh = float(w.screen_w), float(w.screen_h)
        g = self.geom(c, sw, sh)
        puppet = w.puppet_fig()
        frozen = bool(getattr(w, "freeze_fighters", False))
        e_ret = 1.0 - math.exp(-3.0 * TICK_S / max(0.02, c["barrier_return_s"]))
        over = None
        from . import combat
        for f in figs:
            t = f.transform
            st = self.figs.get(id(f))
            if st is None:
                st = self.figs[id(f)] = _Fig(t.x, t.y)
            seen.add(id(f))
            own = dmin + (1.0 - dmin) * _frac(base_speed(f), c["band_speed_slow"], c["band_speed_fast"])
            st.D = max(self.D, own) if self.live else 1.0
            # Live speed: this tick's own move (from where the barrier left
            # it), in un-paced px so the slowdown near the top does not count.
            d = math.hypot(t.x - st.lx, t.y - st.ly)
            if d <= JUMP_PX:
                sf = combat.position_speed_scale(t.x, t.y, sw, sh)
                vr = d / max(0.05, sf)
                st.v += (vr - st.v) * (RISE if vr > st.v else FALL)
            st.allow = _frac(st.v, c["barrier_speed_lo"], c["barrier_speed_hi"])
            if self.bar and f is not puppet and not frozen:
                o = self._hold(f, st, g, e_ret)
                if o is not None and (over is None or o[0] > over[0]):
                    over = o
            else:
                st.r = self.depth_at(t.x, t.y, g)[0]
                st.cap = max(st.allow, st.r)
            st.lx, st.ly = t.x, t.y
        for k in [k for k in self.figs if k not in seen]:
            del self.figs[k]
        self.over = over

    def _hold(self, f, st, g, e_ret):
        """Keep fighter f no deeper in the barrier than its speed allows.
        Returns (overshoot, nx, ny) (inward normal) or None."""
        t = f.transform
        r, u, gx, gy = self.depth_at(t.x, t.y, g)
        a = st.allow
        # cap: how deep it may be.  Eases down to the allowance (a fighter
        # that slowed down is brought back out gradually); never deeper
        # than where it already was (moving in deeper is held at once).
        cap = st.cap
        cap = a if cap <= a else cap + (a - cap) * e_ret
        out = None
        if r > cap and u > 1e-6:
            cx, cy, rx, ry, T = g
            ut = (1.0 - T) + cap * T
            k = ut / u
            t.x = cx + (t.x - cx) * k
            t.y = cy + (t.y - cy) * k
            m = f.motion
            gl = math.hypot(gx, gy)
            if gl > 1e-9 and (m.bouncing or m.bounce_ending):
                nx, ny = gx / gl, gy / gl
                vn = m.bounce_vx * nx + m.bounce_vy * ny
                if vn > 0:              # sliding outward: reflect like a wall
                    m.bounce_vx -= 2.0 * vn * nx
                    m.bounce_vy -= 2.0 * vn * ny
            r = cap
        st.r = r
        st.cap = min(cap, max(a, r))
        if r > a + 1e-3:
            gl = math.hypot(gx, gy)
            if gl > 1e-9:
                out = (_clamp01(r - a), -gx / gl, -gy / gl)
        return out

    def roll_boost(self, w, vmax):
        """(bx, by) px/tick added to the rolling world: toward the camera
        while a fighter is eased back out of the barrier."""
        if not self.bar or self.over is None:
            return 0.0, 0.0
        amt, nx, ny = self.over
        b = amt * w.camera.cfg["barrier_roll"] * vmax
        return nx * b, ny * b


def state(w):
    sb = getattr(w, "speedband", None)
    if sb is None:
        sb = w.speedband = SpeedBand()
    return sb


def step(w):
    state(w).step(w)


def fig_depth(w, fig):
    """Band depth fighter fig is drawn with (1 = full ball)."""
    sb = getattr(w, "speedband", None)
    if sb is None or not sb.live:
        return 1.0
    if fig is None:
        return sb.D
    st = sb.figs.get(id(fig))
    return sb.D if st is None else st.D


# ---- paint ----------------------------------------------------------------
# Overlay._paint_ball sets these for its passes: the observer depth every
# position_scale call draws with (worldscale), and, for the "objects" pass,
# the camera transform + the stand hook so a travelling FX can be redrawn
# upright at its OWN spot on the ball.
_W = None
_BASE = None
_HOOK = None


def paint_begin(w):
    """Start of a big-ball frame: the world band for every layer."""
    global _W
    _W = w
    worldscale.set_observer(fig_depth(w, None))


def paint_end():
    global _W, _BASE, _HOOK
    _W = _BASE = _HOOK = None
    worldscale.set_observer(1.0)


def observe(fig):
    """Draw what follows with fig's band (None = the world's)."""
    if _W is not None:
        worldscale.set_observer(fig_depth(_W, fig))


def objects(base, hook):
    """Objects pass: base = the camera transform, hook(x, y, fig) = the
    screen-space stand transform at world (x, y) for fig's band."""
    global _BASE, _HOOK
    _BASE, _HOOK = base, hook


def travel_at(p, x, y, fig, own_ps=None):
    """Redraw a travelling FX standing at its own world spot (x, y) on the
    ball with its owner's band (instead of riding the owner's feet).
    own_ps: the size it is drawn at (the owner's); the size at its own spot
    is applied on top.  Returns the transform to restore, or None (off)."""
    if _HOOK is None or _BASE is None:
        return None
    old = p.transform()
    t = _BASE * _HOOK(x, y, fig)
    if own_ps:
        from PyQt5.QtGui import QTransform
        from . import combat
        sw, sh = _W.screen_w, _W.screen_h
        k = combat.position_scale(x, y, sw, sh) / own_ps
        if abs(k - 1.0) > 1e-3:
            s = QTransform()
            s.translate(x, y)
            s.scale(k, k)
            s.translate(-x, -y)
            t = s * t
    p.setTransform(t)
    return old
