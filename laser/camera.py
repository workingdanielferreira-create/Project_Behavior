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

Identical in Solo and Battle: the same step / view runs either way; the
only difference is the follow zoom rule (battle_mode).

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
    "margin_px": 220.0,      # space kept around the framed fighters
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
}
# [lo, hi] per numeric key (FX Studio's port: tools/fx/studio/camera.js
# CAM_RANGES; tools/fx/check_parity.py keeps the two in step).
RANGES = {
    "max_zoom": [1.0, 3.0], "solo_zoom": [1.0, 3.0], "follow_s": [0.02, 5.0],
    "margin_px": [0.0, 1000.0], "punch_zoom": [0.0, 1.5],
    "punch_tilt_deg": [0.0, 30.0], "punch_pull": [0.0, 1.0],
    "punch_in_ticks": [1, 30], "punch_out_s": [0.02, 5.0],
    "shake_max_px": [0.0, 100.0], "shake_hz": [1.0, 60.0],
    "ult_zoom": [1.0, 4.0], "ult_in_s": [0.02, 5.0], "ult_max_s": [0.0, 10.0], "ult_out_s": [0.02, 5.0],
    "switch_zoom": [1.0, 4.0], "switch_in_s": [0.02, 5.0], "switch_hold_s": [0.0, 10.0], "switch_out_s": [0.02, 5.0],
    "ko_zoom": [1.0, 4.0], "ko_in_s": [0.02, 5.0], "ko_hold_s": [0.0, 10.0], "ko_out_s": [0.02, 5.0],
    "ko_slow": [0.05, 1.0], "ko_slow_s": [0.0, 5.0],
    "clash_zoom": [1.0, 4.0], "clash_in_s": [0.02, 5.0], "clash_hold_s": [0.0, 10.0], "clash_out_s": [0.02, 5.0],
}
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
    if not isinstance(obj, dict):
        return s
    for k, d in DEFAULTS.items():
        if isinstance(d, bool) and k in obj:
            s[k] = bool(obj[k])
    for k, (lo, hi) in RANGES.items():
        if k in obj:
            s[k] = _num(obj[k], DEFAULTS[k], lo, hi)
    s["punch_in_ticks"] = int(s["punch_in_ticks"])
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
        self.cfg = dict(DEFAULTS)
        self._stamp = None
        self._next = 0
        # Follow state (smoothed)
        self.cx = self.sw / 2.0
        self.cy = self.sh / 2.0
        self.zoom = 1.0
        # Cinematic shot (one at a time) + who was in an ultimate last tick
        self.shot = None
        self._ult_seen = set()
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
        if path is None:
            self.cfg = dict(DEFAULTS)
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                obj = json.load(f)
        except OSError:
            self.cfg = dict(DEFAULTS)
            return
        except ValueError:
            if not keep_on_error:
                self.cfg = dict(DEFAULTS)
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
    def _target(self, world):
        """(cx, cy, zoom) the follow-cam wants this tick."""
        c = self.cfg
        cx0, cy0 = self.sw / 2.0, self.sh / 2.0
        if not c["follow"]:
            return cx0, cy0, 1.0
        xs, ys = [], []
        for f in world.all_figures():
            tr = getattr(f, "transform", None)
            if tr is None or not getattr(tr, "init", True):
                continue
            xs.append(tr.x)
            ys.append(tr.y)
        if not xs:
            return cx0, cy0, 1.0
        m = c["margin_px"]
        bw = max(xs) - min(xs) + 2.0 * m
        bh = max(ys) - min(ys) + 2.0 * m
        fit = min(self.sw / max(1.0, bw), self.sh / max(1.0, bh))
        if getattr(world, "battle_mode", False):
            z = max(1.0, min(c["max_zoom"], fit))
        else:
            z = max(1.0, min(c["solo_zoom"], fit))
        cx = (max(xs) + min(xs)) / 2.0
        cy = (max(ys) + min(ys)) / 2.0
        cx, cy = self._clamp(cx, cy, z)
        return cx, cy, z

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

        # 1. Follow-cam: exponential ease, ~95% caught up after follow_s.
        tx, ty, tz = self._target(world)
        a = 1.0 - math.exp(-_DT * 3.0 / c["follow_s"])
        self.cx += (tx - self.cx) * a
        self.cy += (ty - self.cy) * a
        self.zoom += (tz - self.zoom) * a

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
        """This frame's (cx, cy, zoom, roll_deg, shake_dx, shake_dy), or None
        when the camera is exactly identity.  Deterministic per camera tick,
        so a paused frame (start menu) holds perfectly still."""
        c = self.cfg
        cx, cy, z = self.cx, self.cy, self.zoom
        s = self.shot
        if s is not None and s.env > 0.0:
            k = _ease(s.env)
            cx += (s.x - cx) * k
            cy += (s.y - cy) * k
            z += (max(z, s.zoom) - z) * k
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
        ident = (abs(z - 1.0) < 1e-4 and abs(roll) < 1e-3
                 and abs(sx) < 0.05 and abs(sy) < 0.05
                 and abs(cx - self.sw / 2.0) < 0.05
                 and abs(cy - self.sh / 2.0) < 0.05)
        self._view = None if ident else (cx, cy, z, roll, sx, sy)
        return self._view

    def apply(self, p, view):
        """Push `view` onto QPainter p (caller save()s / restore()s).  The
        shake is in screen pixels, so it never scales with the zoom."""
        cx, cy, z, roll, sx, sy = view
        p.translate(self.sw / 2.0 + sx, self.sh / 2.0 + sy)
        if roll:
            p.rotate(roll)
        p.scale(z, z)
        p.translate(-cx, -cy)

    def screen_to_world(self, x, y):
        """A screen point (the real mouse cursor) -> scene coordinates under
        the last painted view."""
        v = self._view
        if v is None:
            return x, y
        cx, cy, z, roll, sx, sy = v
        u = x - self.sw / 2.0 - sx
        w = y - self.sh / 2.0 - sy
        if roll:
            r = math.radians(-roll)
            cs, sn = math.cos(r), math.sin(r)
            u, w = u * cs - w * sn, u * sn + w * cs
        return cx + u / z, cy + w / z
