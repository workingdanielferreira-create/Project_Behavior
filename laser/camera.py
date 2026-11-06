"""
Dynamic action camera — a VIEW transform only.

The camera never moves a fighter.  Every position the simulation uses
(hit tests, walls, targeting, the per-tick battle snapshots) stays in plain
screen coordinates; the camera only changes how the scene is PAINTED
(Overlay._paint_scene), so both sides keep fully independent decision
streams.  The HUD (team HP bars, HP readout, notices) is drawn after the
camera is undone, so it never zooms or shakes.  The only thing mapped back
through the camera is the mouse cursor (Overlay._tick ->
Camera.screen_to_world), so a fighter told to go "to the cursor" is DRAWN
under the real cursor.

Four layers, one transform:

  1. Follow-cam      frames every fielded fighter (box + margin) and eases
                     there (follow_s ~ time to catch up).  Battle zooms in
                     up to max_zoom when the fight is tight; Solo follows the
                     fighter at a light fixed zoom (solo_zoom).  Never below
                     1.0x, and the view never leaves the screen, so at 1.0x
                     the picture is exactly the old, untransformed one.
  2. Cinematic shots one scripted move at a time, blended over the follow:
                     ultimate  push in on the caster while its ultimate plays
                               (seen through actions.current_action_name, so
                               every character gets it), up to ult_max_s;
                     switch_in quick move onto a tag partner coming in
                               (tag._swap -> World.camera_shot);
                     ko        hold on the fallen fighter (World.
                               on_figure_death); the World also runs a real
                               slow-mo (ko_slow x speed for ko_slow_s);
                     clash     snap onto a new clash point (clash.step).
                     Priority ko > ultimate > switch_in > clash: a shot
                     only replaces one of lower or equal priority, or one
                     already easing out.  Each: zoom, in / hold / out time.
  3. Hit-stop punch  a big hit (World.hitstop_ticks — finishers, ultimates,
                     strikes with Hit-stop) snaps punch_zoom extra zoom
                     toward the impact with a punch_tilt_deg roll along the
                     knockback, holds through the freeze, eases back out.
  4. Trauma shake    every World.add_shake adds "trauma" (0..1).  Amplitude =
                     shake_max_px * trauma^2 on smooth value noise, so
                     overlapping hits build up and fade naturally.  A single
                     hit from rest still shakes exactly its authored px.
  5. Depth tilt      a real (projective) perspective along the arena's own
                     depth axis (combat.position_scale: bottom-left near,
                     top-right far), applied in scene space under the rest:
                     a point at depth t (0 near .. 1 far) is drawn at
                     A + (p - A) / w with w = 1 + k (t - t_A), where A is the
                     NEAREST fielded fighter.  Every fighter is therefore
                     only ever pulled in toward A (never off-screen) and the
                     far side shrinks — the slope reads deeper.  Dynamic:
                     k = depth_base + depth_gain * (1 - t_A) (action near
                     the front = lower, stronger camera) + depth_shot during
                     a cinematic shot; eased like the follow-cam.  Drawing
                     only: position_scale, hit tests, walls and dust physics
                     are untouched.

  6. World anchor   (anchor_scale) an invisible point eased to the centre of
                     every fielded fighter (Solo: the lone fighter).  It
                     drives laser/worldscale.py — every fighter / FX / pace
                     scales by vertical (x5 bottom .. x1 top) x distance from
                     the anchor (x1 on it .. x0.10 far, tunable curve) — and
                     the follow-cam pans onto it.  So closeness is shown by
                     the scaling, not the camera: the follow zoom is a fixed
                     anchor_zoom (just enough to pan), only ever reduced to
                     keep everyone in view; punch-in / cinematic shots keep
                     their own zoom.  The depth tilt's axis turns vertical
                     (bottom near, top far) to match.  Off = the old corner
                     grid and the old follow zoom, unchanged.

  7. Tiny planet    (planet, needs anchor_scale) the anchor is the top of a
                     small planet: worldscale's distance term becomes a
                     sphere curve (big near the top, dropping fast toward a
                     horizon ellipse planet_reach_x/y_frac x width away) and the world
                     layers - terrain, rubble, debris, dust & air - are
                     squashed along the line to the anchor toward the rim
                     (foreshortening; drawn in place, never moved).
                     Fighters and their FX only take the size curve.  While
                     on, the depth tilt is off (the planet replaces it).

Identical in Solo and Battle: the same step / view runs either way; the
only difference is the follow zoom rule (battle_mode) when anchor_scale is
off.

Settings: characters/camera.json (format pb_camera), any key optional,
hot-reloaded about once a second and on F5.  Missing file = DEFAULTS.
"""

import json
import math
import os

from . import config

FILE = "camera.json"            # in characters/
FORMAT = "pb_camera"
WATCH_TICKS = 60                 # re-check the file about once a second

DEFAULTS = {
    "follow": True,          # follow-cam on/off (off = fixed 1.0x, centred)
    "punch": True,           # hit-stop punch-in on/off
    "shake": True,           # trauma shake on/off
    "max_zoom": 1.6,         # Battle: tightest follow zoom (fighters close)
    "solo_zoom": 1.15,       # Solo: light fixed follow zoom
    "follow_s": 0.4,         # seconds to (95%) catch up with the fighters
    "margin_x_px": 220.0,    # space kept left / right of the framed fighters
    "margin_y_px": 220.0,    # space kept above / below the framed fighters
    "punch_zoom": 0.3,       # extra zoom on a hit-stop punch-in
    "punch_tilt_deg": 3.0,   # roll along the knockback during the punch
    "punch_pull": 0.6,       # 0..1: how far the centre moves onto the impact
    "punch_in_ticks": 3,     # snap-in time (ticks)
    "punch_out_s": 0.35,     # ease-back time after the freeze ends
    "shake_max_px": 16.0,    # amplitude at full trauma (1.0)
    "shake_hz": 18.0,        # shake noise frequency
    # Cinematic shots
    "ult_on": True,          # ultimate: push in on the caster
    "ult_zoom": 2.3,
    "ult_in_s": 0.6,         # slow push-in
    "ult_max_s": 1.5,        # holds while the ultimate plays, at most this
    "ult_out_s": 0.5,
    "switch_on": True,       # tag switch-in: move onto the incoming partner
    "switch_zoom": 1.8,
    "switch_in_s": 0.15,
    "switch_hold_s": 0.5,
    "switch_out_s": 0.4,
    "ko_on": True,           # KO: hold on the fallen fighter
    "ko_zoom": 2.5,
    "ko_in_s": 0.2,
    "ko_hold_s": 1.0,
    "ko_out_s": 0.6,
    "ko_slow": 0.25,         # KO slow-mo: game speed (1 = no slow-mo)
    "ko_slow_s": 0.9,        # KO slow-mo: how long (real seconds)
    "clash_on": True,        # clash: snap onto the clash point
    "clash_zoom": 2.0,
    "clash_in_s": 0.08,
    "clash_hold_s": 0.3,
    "clash_out_s": 0.35,
    # Depth tilt (perspective along the arena's depth axis)
    "depth": True,
    "depth_base": 0.10,      # always-on perspective strength
    "depth_gain": 0.20,      # extra when the action is at the near side
    "depth_shot": 0.15,      # extra at the peak of a cinematic shot
    "depth_budget_ms": 14.0, # paint-time budget: over it ~2 s = depth off
    # World anchor scaling (laser/worldscale.py)
    "anchor_scale": True,    # on = vertical x distance rule; off = corner grid
    "anchor_s": 0.3,         # seconds for the anchor to (95%) catch up
    "anchor_zoom": 1.15,     # fixed follow zoom while on (only reduced to fit)
    "vscale_bottom": 5.0,    # size at the very bottom of the screen
    "vscale_top": 1.0,       # size at the very top
    "dscale_near": 1.0,      # distance factor on the anchor
    "dscale_far": 0.10,      # distance factor at the far ellipse
    "dscale_far_x_frac": 0.5,  # far ellipse half-width, x screen width (0.5 = opposite edges)
    "dscale_far_y_frac": 0.5,  # far ellipse half-height, x screen width
    "dscale_curve": 1.0,     # falloff exponent (1 linear, >1 soft near, <1 fast)
    "scale_min": 0.10,       # final size clamp
    "scale_max": 5.0,
    "speed_min": 0.40,       # pace at scale_min
    "speed_max": 1.00,       # pace at scale_max
    # Tiny planet (laser/worldscale.py; replaces the depth tilt + distance term)
    "planet": True,          # on = sphere curve around the anchor
    "planet_reach_x_frac": 0.6,  # anchor -> horizon left / right, x screen width
    "planet_reach_y_frac": 0.6,  # anchor -> horizon up / down, x screen width
    "planet_horizon_deg": 80.0, # how far round the sphere the horizon is
    "planet_far": 0.15,      # size factor at the horizon
    "planet_squash": 0.85,   # foreshortening at the horizon (0 = none)
    # Wireframe overlay (laser/wireframe.py): how the environment acts on the
    # fighters - scaling, anchor / planet / depth, roll zones, camera framing,
    # pillar spawning - drawn in the scene over everything but the HUD.
    "wireframe": False,
}
# [lo, hi] per numeric key (FX Studio's port: tools/fx/studio/camera.js
# CAM_RANGES; tools/fx/check_parity.py keeps the two in step).
RANGES = {
    "max_zoom": [1.0, 3.0], "solo_zoom": [1.0, 3.0], "follow_s": [0.02, 5.0],
    "margin_x_px": [0.0, 1000.0], "margin_y_px": [0.0, 1000.0], "punch_zoom": [0.0, 1.5],
    "punch_tilt_deg": [0.0, 30.0], "punch_pull": [0.0, 1.0],
    "punch_in_ticks": [1, 30], "punch_out_s": [0.02, 5.0],
    "shake_max_px": [0.0, 100.0], "shake_hz": [1.0, 60.0],
    "ult_zoom": [1.0, 4.0], "ult_in_s": [0.02, 5.0], "ult_max_s": [0.0, 10.0], "ult_out_s": [0.02, 5.0],
    "switch_zoom": [1.0, 4.0], "switch_in_s": [0.02, 5.0], "switch_hold_s": [0.0, 10.0], "switch_out_s": [0.02, 5.0],
    "ko_zoom": [1.0, 4.0], "ko_in_s": [0.02, 5.0], "ko_hold_s": [0.0, 10.0], "ko_out_s": [0.02, 5.0],
    "ko_slow": [0.05, 1.0], "ko_slow_s": [0.0, 5.0],
    "clash_zoom": [1.0, 4.0], "clash_in_s": [0.02, 5.0], "clash_hold_s": [0.0, 10.0], "clash_out_s": [0.02, 5.0],
    "depth_base": [0.0, 0.6], "depth_gain": [0.0, 0.6], "depth_shot": [0.0, 0.6],
    "depth_budget_ms": [4.0, 60.0],
    "anchor_s": [0.02, 5.0], "anchor_zoom": [1.0, 3.0],
    "vscale_bottom": [0.1, 10.0], "vscale_top": [0.1, 10.0],
    "dscale_near": [0.05, 2.0], "dscale_far": [0.05, 2.0],
    "dscale_far_x_frac": [0.1, 1.5], "dscale_far_y_frac": [0.1, 1.5], "dscale_curve": [0.2, 5.0],
    "scale_min": [0.05, 10.0], "scale_max": [0.05, 10.0],
    "speed_min": [0.05, 2.0], "speed_max": [0.05, 2.0],
    "planet_reach_x_frac": [0.1, 2.0], "planet_reach_y_frac": [0.1, 2.0], "planet_horizon_deg": [10.0, 90.0],
    "planet_far": [0.05, 1.0], "planet_squash": [0.0, 0.95],
}
# Settings split into x / y: an old file's single value seeds both.
LEGACY_XY = {"margin_px": ("margin_x_px", "margin_y_px"),
             "dscale_far_frac": ("dscale_far_x_frac", "dscale_far_y_frac"),
             "planet_reach_frac": ("planet_reach_x_frac", "planet_reach_y_frac")}
# Wireframe overlay toggles (camera.json "wire_off" = the keys whose part of
# the wireframe is hidden; FX Studio: a tick box beside each setting while
# the wireframe is on).  Camera settings, two wireframe-only parts
# (wire_grid, wire_view) and "section.key" Dust & Air settings.  A part with
# several owners is hidden when ANY of them is unticked (laser/wireframe.py).
WIRE_KEYS = [
    "follow", "margin_x_px", "margin_y_px", "max_zoom", "solo_zoom", "anchor_zoom",
    "punch", "punch_tilt_deg", "shake", "shake_max_px", "ult_on", "switch_on", "ko_on", "clash_on",
    "depth", "depth_base", "depth_gain", "depth_shot",
    "anchor_scale", "vscale_bottom", "vscale_top", "dscale_near", "dscale_far",
    "dscale_far_x_frac", "dscale_far_y_frac", "dscale_curve", "scale_min", "scale_max", "speed_min", "speed_max",
    "planet", "planet_reach_x_frac", "planet_reach_y_frac", "planet_horizon_deg", "planet_far", "planet_squash",
    "wire_grid", "wire_view",
    "roll.enabled", "roll.max_speed", "roll.zone_x_frac", "roll.zone_y_frac", "roll.vertical",
    "roll.spawn_ahead_px", "roll.margin_px",
    "pillars.enabled", "pillars.count", "pillars.respawn_s", "pillars.radius_x_px", "pillars.radius_y_px",
    "pillars.clear_x_px", "pillars.clear_y_px", "pillars.gap_x_px", "pillars.gap_y_px",
    "pillars.width", "pillars.height", "pillars.hp", "pillars.multi_chance",
]
DEPTH_SLOW_FRAMES = 120   # ~2 s of over-budget frames before depth turns off
DEPTH_MAX = 0.6     # total perspective strength cap (keeps w > 0 everywhere)
# Shot kinds: settings prefix and priority (higher wins).
SHOTS = {"clash": ("clash", 1), "switch_in": ("switch", 2), "ultimate": ("ult", 3), "ko": ("ko", 4)}

_DT = config.TICK_MS / 1000.0


def _num(v, d, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return d
    if v != v:          # NaN
        return d
    return max(lo, min(hi, v))


def normalize(obj):
    """A camera.json dict -> a complete, range-checked settings dict."""
    s = dict(DEFAULTS)
    s["wire_off"] = []
    if not isinstance(obj, dict):
        return s
    obj = dict(obj)
    for old, new in LEGACY_XY.items():
        if old in obj:
            for k in new:
                obj.setdefault(k, obj[old])
    wo = obj.get("wire_off")
    if isinstance(wo, list):
        s["wire_off"] = [k for k in WIRE_KEYS if k in wo]
    for k, d in DEFAULTS.items():
        if isinstance(d, bool) and k in obj:
            s[k] = bool(obj[k])
    for k, (lo, hi) in RANGES.items():
        if k in obj:
            s[k] = _num(obj[k], DEFAULTS[k], lo, hi)
    s["punch_in_ticks"] = int(s["punch_in_ticks"])
    if s["scale_min"] > s["scale_max"]:
        s["scale_min"], s["scale_max"] = s["scale_max"], s["scale_min"]
    return s


def _hash(i, seed):
    """Integer lattice point -> pseudo-random value in [-1, 1]."""
    h = (i * 374761393 + seed * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return (h & 0xFFFF) / 32767.5 - 1.0


def _noise(x, seed):
    """Smooth 1-D value noise in [-1, 1] (smoothstep between lattice points)."""
    i = math.floor(x)
    f = x - i
    a = _hash(int(i), seed)
    b = _hash(int(i) + 1, seed)
    u = f * f * (3.0 - 2.0 * f)
    return a + (b - a) * u


def _ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _mul(a, b):
    """3x3 matrix product (row-vector convention, as QTransform)."""
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _inv(m):
    """3x3 inverse (None when singular)."""
    (a, b, c), (d, e, f), (g, h, i) = m
    A, B, C = e * i - f * h, -(d * i - f * g), d * h - e * g
    det = a * A + b * B + c * C
    if abs(det) < 1e-12:
        return None
    D, E, F = -(b * i - c * h), a * i - c * g, -(a * h - b * g)
    G, H, I = b * f - c * e, -(a * f - c * d), a * e - b * d
    return [[A / det, D / det, G / det], [B / det, E / det, H / det], [C / det, F / det, I / det]]


def _ticks(s):
    return max(1, int(round(s / _DT)))


def _fig_pos(fig):
    tr = getattr(fig, "transform", None)
    if tr is None:
        return None
    return float(tr.x), float(tr.y)


class _Shot:
    """One cinematic move: ramps in, holds, eases out.  `fig` (optional) is
    followed while the shot plays (its last position when it is gone).
    `while_fn` (optional) keeps the hold going while it returns True, up to
    hold ticks."""

    def __init__(self, kind, x, y, fig, zoom, in_t, hold_t, out_t, while_fn=None):
        self.kind = kind
        self.prio = SHOTS[kind][1]
        self.x, self.y = x, y
        self.fig = fig
        self.zoom = zoom
        self.in_t = max(1, in_t)
        self.hold_t = max(0, hold_t)
        self.out_t = max(1, out_t)
        self.while_fn = while_fn
        self.env = 0.0
        self.age = 0
        self.out = False

    def step(self):
        """Advance one tick; False when finished."""
        if self.fig is not None:
            p = _fig_pos(self.fig)
            if p is not None:
                self.x, self.y = p
        self.age += 1
        if not self.out:
            self.env = min(1.0, self.env + 1.0 / self.in_t)
            held = self.age - self.in_t
            if self.while_fn is not None:
                try:
                    going = bool(self.while_fn())
                except Exception:
                    going = False
                if held >= 0 and (not going or held >= self.hold_t):
                    self.out = True
            elif held >= self.hold_t:
                self.out = True
        else:
            self.env = max(0.0, self.env - 1.0 / self.out_t)
        return not (self.out and self.env <= 0.0)


class Camera:

    def __init__(self, screen_w, screen_h, root_dir=None):
        self.sw = float(screen_w)
        self.sh = float(screen_h)
        self.root = root_dir
        self.cfg = normalize({})
        self._stamp = None
        self._next = 0
        # Follow state (smoothed)
        self.cx = self.sw / 2.0
        self.cy = self.sh / 2.0
        self.zoom = 1.0
        # Cinematic shot (one at a time) + who was in an ultimate last tick
        self.shot = None
        self._ult_seen = set()
        # Depth tilt: strength k and anchor A (the nearest fighter), eased
        self.k = 0.0
        self.ax = self.sw / 2.0
        self.ay = self.sh / 2.0
        # World anchor (eased centre of all fighters; None until first seen)
        self.anc = None
        # Perspective painting is slower than affine in Qt's raster engine:
        # note_paint() watches the frame paint time and turns the depth
        # tilt off for the session when it runs over depth_budget_ms
        # (re-armed whenever the settings are (re)loaded).
        self.paint_ms = 0.0
        self._slow = 0
        self.depth_suspended = False
        self.suspend_note = None    # message for the World notice, once
        # Hit-stop punch
        self.env = 0.0              # 0..1 punch envelope (linear; eased on use)
        self.in_left = 0            # snap-in ticks still forcing the punch
        self.px = self.cx
        self.py = self.cy
        self.roll = 0.0             # signed roll (degrees) at full punch
        self._req = None            # (x, y, dx, dy) asked for this tick
        self._prev_hitstop = 0
        # Trauma shake
        self.trauma = 0.0
        self.decay = 0.0            # trauma lost per tick
        self.t = 0                  # camera clock (ticks; stands still paused)
        self._view = None           # last view() result (None = identity)
        self.load()

    # --- settings ---------------------------------------------------------
    def _path(self):
        if not self.root:
            return None
        return os.path.join(self.root, "characters", FILE)

    @staticmethod
    def _file_stamp(path):
        try:
            st = os.stat(path)
            return (st.st_mtime_ns, st.st_size)
        except (OSError, TypeError):
            return None

    def load(self, keep_on_error=False):
        """Read characters/camera.json (defaults when missing).  A file that
        can't be parsed right now (caught mid-save) keeps the current
        settings when keep_on_error, and is retried on the next check."""
        path = self._path()
        self._stamp = self._file_stamp(path)
        # (Re)loading re-arms a depth tilt switched off for being too slow.
        self.depth_suspended = False
        self._slow = 0
        if path is None:
            self.cfg = normalize({})
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                obj = json.load(f)
        except OSError:
            self.cfg = normalize({})
            return
        except ValueError:
            if not keep_on_error:
                self.cfg = normalize({})
            return
        ok = isinstance(obj, dict) and obj.get("format") == FORMAT
        self.cfg = normalize(obj if ok else {})

    def _watch(self):
        self._next -= 1
        if self._next > 0:
            return
        self._next = WATCH_TICKS
        if self._file_stamp(self._path()) != self._stamp:
            self.load(keep_on_error=True)

    # --- events -----------------------------------------------------------
    def add_shake(self, px, ticks):
        """A screen shake of `px` easing out over `ticks` adds trauma.  From
        rest it shakes exactly px; on top of a running shake it stacks."""
        mx = self.cfg["shake_max_px"]
        if px <= 0 or mx <= 0:
            return
        add = math.sqrt(min(1.0, float(px) / mx))
        rate = add / float(max(1, int(ticks)))
        before = self.trauma
        if before <= 1e-4:
            self.decay = rate
        else:
            self.decay = (before * self.decay + add * rate) / (before + add)
        self.trauma = min(1.0, before + add)

    def punch(self, x, y, dx=0.0, dy=0.0):
        """A hit-stop starts at (x, y), knockback roughly along (dx, dy)."""
        self._req = (float(x), float(y), float(dx), float(dy))

    def shot_on(self, kind):
        """Is this cinematic shot kind switched on?"""
        pre = SHOTS.get(kind, (None,))[0]
        return bool(pre) and bool(self.cfg.get(pre + "_on"))

    def ko_hold_ticks(self):
        """How long a KO shot takes to reach and hold its frame (ticks)."""
        c = self.cfg
        return _ticks(c["ko_in_s"]) + _ticks(c["ko_hold_s"])

    def start_shot(self, kind, x=None, y=None, fig=None, while_fn=None):
        """Start cinematic shot `kind` ('ultimate', 'switch_in', 'ko',
        'clash') on (x, y) or on `fig` (followed).  Returns True if it
        started (it is on, and nothing of higher priority is playing)."""
        if kind not in SHOTS or not self.shot_on(kind):
            return False
        cur = self.shot
        if cur is not None and not cur.out and cur.prio > SHOTS[kind][1]:
            return False
        if fig is not None:
            p = _fig_pos(fig)
            if p is not None:
                x, y = p
        if x is None or y is None:
            return False
        pre = SHOTS[kind][0]
        c = self.cfg
        hold = c["ult_max_s"] if kind == "ultimate" else c[pre + "_hold_s"]
        s = _Shot(kind, float(x), float(y), fig, c[pre + "_zoom"],
                  _ticks(c[pre + "_in_s"]), int(round(hold / _DT)),
                  _ticks(c[pre + "_out_s"]), while_fn)
        # Carry the current blend so a replaced shot doesn't pop.
        if cur is not None:
            s.env = cur.env
        self.shot = s
        return True

    # --- per tick ---------------------------------------------------------
    @staticmethod
    def _fielded(world):
        """[(x, y)] of every fielded fighter, both sides."""
        out = []
        for f in world.all_figures():
            tr = getattr(f, "transform", None)
            if tr is None or not getattr(tr, "init", True):
                continue
            out.append((float(tr.x), float(tr.y)))
        return out

    def _step_anchor(self, pts):
        """Ease the world anchor to the centre of the fighters and hand it to
        laser/worldscale.py (off = the corner grid)."""
        from . import worldscale
        c = self.cfg
        if not c["anchor_scale"]:
            self.anc = None
            worldscale.set_anchor(None)
            return
        if pts:
            tx = sum(p[0] for p in pts) / len(pts)
            ty = sum(p[1] for p in pts) / len(pts)
            if self.anc is None:
                self.anc = (tx, ty)          # first sight: no glide in
            else:
                a = 1.0 - math.exp(-_DT * 3.0 / c["anchor_s"])
                ax, ay = self.anc
                self.anc = (ax + (tx - ax) * a, ay + (ty - ay) * a)
        if self.anc is None:
            worldscale.set_anchor(None)
        else:
            worldscale.set_anchor(self.anc[0], self.anc[1], c)

    def _target(self, world, pts=None):
        """(cx, cy, zoom) the follow-cam wants this tick."""
        c = self.cfg
        cx0, cy0 = self.sw / 2.0, self.sh / 2.0
        if not c["follow"]:
            return cx0, cy0, 1.0
        if pts is None:
            pts = self._fielded(world)
        if not pts:
            return cx0, cy0, 1.0
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        bw = max(xs) - min(xs) + 2.0 * c["margin_x_px"]
        bh = max(ys) - min(ys) + 2.0 * c["margin_y_px"]
        fit = min(self.sw / max(1.0, bw), self.sh / max(1.0, bh))
        if c["anchor_scale"] and self.anc is not None:
            # Closeness is the scaling's job: a fixed pan zoom, only ever
            # reduced to keep everyone in view; centred on the anchor.
            z = max(1.0, min(c["anchor_zoom"], fit))
            cx, cy = self.anc
        else:
            if getattr(world, "battle_mode", False):
                z = max(1.0, min(c["max_zoom"], fit))
            else:
                z = max(1.0, min(c["solo_zoom"], fit))
            cx = (max(xs) + min(xs)) / 2.0
            cy = (max(ys) + min(ys)) / 2.0
        cx, cy = self._clamp(cx, cy, z)
        return cx, cy, z

    def planet_live(self):
        """Tiny planet on (it needs the anchor; it replaces the depth tilt)."""
        return bool(self.cfg.get("planet")) and bool(self.cfg["anchor_scale"])

    def depth_live(self):
        return (bool(self.cfg["depth"]) and not self.planet_live()
                and not getattr(self, "depth_suspended", False))

    def note_paint(self, ms, used_depth):
        """Overlay._paint: how long the scene took (ms) and whether the depth
        tilt was in the transform.  Over budget for DEPTH_SLOW_FRAMES frames
        in a row with depth on = depth off for this session."""
        self.paint_ms += (ms - self.paint_ms) * 0.1
        if not used_depth or self.depth_suspended:
            self._slow = 0
            return
        if self.paint_ms > self.cfg["depth_budget_ms"]:
            self._slow += 1
            if self._slow >= DEPTH_SLOW_FRAMES:
                self.depth_suspended = True
                self.suspend_note = ("Depth tilt off: painting took %.0f ms a frame "
                                     "(budget %.0f). Save camera.json or F5 to retry."
                                     % (self.paint_ms, self.cfg["depth_budget_ms"]))
        else:
            self._slow = 0

    def _depth_w(self):
        """(wx, wy) of the depth axis t = wx x/sw + wy (1 - y/sh): the
        corner grid's diagonal (bottom-left near), or vertical (bottom
        near) while anchor_scale is on."""
        if self.cfg.get("anchor_scale"):
            return 0.0, 1.0
        return 0.5, 0.5

    def _depth_t(self, x, y):
        """Depth of a scene point: 0 at the near side, 1 at the far side —
        the axis combat.position_scale shrinks along."""
        wx, wy = self._depth_w()
        return wx * (x / self.sw) + wy * (1.0 - y / self.sh)

    def _depth_target(self, world):
        """(k, ax, ay) the depth tilt wants this tick."""
        c = self.cfg
        if not self.depth_live():
            return 0.0, self.ax, self.ay
        best = None
        for f in world.all_figures():
            tr = getattr(f, "transform", None)
            if tr is None or not getattr(tr, "init", True):
                continue
            t = self._depth_t(tr.x, tr.y)
            if best is None or t < best[0]:
                best = (t, tr.x, tr.y)
        if best is None:
            return 0.0, self.ax, self.ay
        t, x, y = best
        t = max(0.0, min(1.0, t))
        k = c["depth_base"] + c["depth_gain"] * (1.0 - t)
        return min(DEPTH_MAX, k), x, y

    def _clamp(self, cx, cy, z):
        """Keep the zoomed view inside the screen (at 1.0x: dead centre)."""
        hw = self.sw / (2.0 * z)
        hh = self.sh / (2.0 * z)
        return (min(max(cx, hw), self.sw - hw),
                min(max(cy, hh), self.sh - hh))

    def _watch_ultimates(self, world):
        """Start the ultimate shot on the edge of any fighter's ultimate
        (Mirror Legion copies excluded).  Read-only on the fighters."""
        from . import actions, unique
        now = set()
        for f in world.all_figures():
            if unique.is_clone(f):
                continue
            try:
                ult = actions.current_action_name(f) == "ultimate"
            except Exception:
                ult = False
            if not ult:
                continue
            now.add(id(f))
            if id(f) not in self._ult_seen:
                def going(f=f):
                    return actions.current_action_name(f) == "ultimate"
                self.start_shot("ultimate", fig=f, while_fn=going)
        self._ult_seen = now

    def step(self, world):
        """Once per game tick (hit-stop and slow-mo included; not while the
        start menu pauses the game).  Read-only on the world."""
        self._watch()
        self.t += 1
        c = self.cfg

        # 0. World anchor (drives laser/worldscale.py and the follow centre).
        pts = self._fielded(world)
        self._step_anchor(pts)

        # 1. Follow-cam: exponential ease, ~95% caught up after follow_s.
        tx, ty, tz = self._target(world, pts)
        a = 1.0 - math.exp(-_DT * 3.0 / c["follow_s"])
        self.cx += (tx - self.cx) * a
        self.cy += (ty - self.cy) * a
        self.zoom += (tz - self.zoom) * a
        # Depth tilt eases with the follow-cam.
        tk, tax, tay = self._depth_target(world)
        self.k += (tk - self.k) * a
        self.ax += (tax - self.ax) * a
        self.ay += (tay - self.ay) * a

        # 2. Cinematic shots.
        self._watch_ultimates(world)
        if self.shot is not None:
            if not self.shot_on(self.shot.kind) or not self.shot.step():
                self.shot = None

        # 3. Hit-stop punch-in.
        hs = int(getattr(world, "hitstop_ticks", 0) or 0)
        req, self._req = self._req, None
        if c["punch"]:
            if req is None and hs > 0 and self._prev_hitstop <= 0:
                # A freeze nobody described: punch on the framed centre.
                req = (self.cx, self.cy, 0.0, 0.0)
            if req is not None:
                x, y, dx, dy = req
                self.px, self.py = x, y
                d = math.hypot(dx, dy)
                # Roll with the knockback's horizontal direction.
                self.roll = (c["punch_tilt_deg"] * dx / d) if d > 1e-6 else 0.0
                self.in_left = c["punch_in_ticks"]
            if self.in_left > 0 or hs > 0:
                self.env = min(1.0, self.env + 1.0 / c["punch_in_ticks"])
                self.in_left = max(0, self.in_left - 1)
            else:
                self.env = max(0.0, self.env - _DT / c["punch_out_s"])
        else:
            self.env = 0.0
            self.in_left = 0
        self._prev_hitstop = hs

        # 4. Trauma decays.
        if self.trauma > 0.0:
            self.trauma = max(0.0, self.trauma - self.decay)

    # --- view -------------------------------------------------------------
    def view(self):
        """This frame's (cx, cy, zoom, roll_deg, shake_dx, shake_dy, k, ax,
        ay), or None when the camera is exactly identity.  Deterministic per
        camera tick, so a paused frame (start menu) holds perfectly still."""
        c = self.cfg
        cx, cy, z = self.cx, self.cy, self.zoom
        live = self.depth_live()
        k = self.k if live else 0.0
        s = self.shot
        if s is not None and s.env > 0.0:
            e = _ease(s.env)
            cx += (s.x - cx) * e
            cy += (s.y - cy) * e
            z += (max(z, s.zoom) - z) * e
            if live:
                k += c["depth_shot"] * e
        k = max(0.0, min(DEPTH_MAX, k))
        e = _ease(self.env) if c["punch"] else 0.0
        z += c["punch_zoom"] * e
        pull = c["punch_pull"] * e
        cx += (self.px - cx) * pull
        cy += (self.py - cy) * pull
        cx, cy = self._clamp(cx, cy, z)
        roll = self.roll * e
        sx = sy = 0.0
        if c["shake"] and self.trauma > 0.0:
            amp = c["shake_max_px"] * self.trauma * self.trauma
            ph = self.t * _DT * c["shake_hz"]
            sx = amp * _noise(ph, 1)
            sy = amp * _noise(ph, 2)
        ident = (abs(z - 1.0) < 1e-4 and abs(roll) < 1e-3 and k < 1e-4
                 and abs(sx) < 0.05 and abs(sy) < 0.05
                 and abs(cx - self.sw / 2.0) < 0.05
                 and abs(cy - self.sh / 2.0) < 0.05)
        self._view = None if ident else (cx, cy, z, roll, sx, sy, k, self.ax, self.ay)
        self._mat = None if ident else self.matrix(self._view)
        return self._view

    def matrix(self, view):
        """The full scene -> screen transform of `view` as a 3x3 matrix in
        QTransform's row-vector convention: depth tilt first (scene space),
        then the camera (centre, zoom, roll, shake)."""
        cx, cy, z, roll, sx, sy, k, ax, ay = view
        # Depth tilt: p' = A + (p - A) / w, w = 1 + k (t(p) - t(A)),
        # t(p) = wx x / sw + wy (1 - y / sh).
        wx, wy = self._depth_w()
        pa = wx * k / self.sw
        pb = -wy * k / self.sh
        pc = 1.0 + k * (wy - self._depth_t(ax, ay))
        P = [[1.0 + ax * pa, ay * pa, pa],
             [ax * pb, 1.0 + ay * pb, pb],
             [ax * (pc - 1.0), ay * (pc - 1.0), pc]]
        r = math.radians(roll)
        cs, sn = math.cos(r), math.sin(r)
        T2 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [-cx, -cy, 1.0]]
        S = [[z, 0.0, 0.0], [0.0, z, 0.0], [0.0, 0.0, 1.0]]
        R = [[cs, sn, 0.0], [-sn, cs, 0.0], [0.0, 0.0, 1.0]]
        T1 = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
              [self.sw / 2.0 + sx, self.sh / 2.0 + sy, 1.0]]
        return _mul(_mul(_mul(_mul(P, T2), S), R), T1)

    def apply(self, p, view):
        """Push `view` onto QPainter p (caller save()s / restore()s).  The
        shake is in screen pixels, so it never scales with the zoom."""
        from PyQt5.QtGui import QTransform
        m = self.matrix(view)
        p.setTransform(QTransform(m[0][0], m[0][1], m[0][2],
                                  m[1][0], m[1][1], m[1][2],
                                  m[2][0], m[2][1], m[2][2]), True)

    def screen_to_world(self, x, y):
        """A screen point (the real mouse cursor) -> scene coordinates under
        the last painted view."""
        m = getattr(self, "_mat", None)
        if self._view is None or m is None:
            return x, y
        mi = _inv(m)
        if mi is None:
            return x, y
        X = x * mi[0][0] + y * mi[1][0] + mi[2][0]
        Y = x * mi[0][1] + y * mi[1][1] + mi[2][1]
        W = x * mi[0][2] + y * mi[1][2] + mi[2][2]
        if abs(W) < 1e-9:
            return x, y
        return X / W, Y / W
