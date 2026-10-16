"""
Movement style — the character-level movement personality.  Set in FX Studio
("Movement style (whole character)", pack.movement_style); a rig-drawn
pb_character JSON can set the same block as "movement": {"style": {...}}.
Characters without it (and the built-in swordsman / runner) move exactly as
before: target() returns None and the old chase / kite / glide code runs.

A style is a list of PHASES.  Each phase names one movement PATTERN with its
own settings, a set of MODIFIERS layered on top, and WHEN conditions that say
when the phase may run.  `select` picks between the phases:

  priority  the first phase in the list whose conditions pass runs; checked
            again every tick once its hold time is up.
  weighted  when the hold time is up, a random phase among those whose
            conditions pass, by weight.
  sequence  when the hold time is up, the next phase in the list (wrapping)
            whose conditions pass.

hold_min_ms / hold_max_ms: once entered, a phase runs at least a random time
in that range before the choice is made again (weighted / sequence with no
hold use 2000 ms).  No phase passes: the character's old movement runs for
that tick, so a style can be a single "only below 30 % HP" phase.

Patterns (PATTERN_DEFAULTS has every setting; px values grow and shrink with
the character scale):

  chase        straight at the target, stopping stop_px short (0 = where it
               can attack), or running overshoot_px through it.
  orbit        round the target at radius_px, cw / ccw / alternate (swapping
               every swap_ms), lead_deg ahead; wobble_pct breathes the radius.
  kite         holds the min_px..max_px band: closes in when too far, backs
               off when too near, strafes round it while in the band.
  glide        skating orbit with momentum (drift_pct), carving S-curves
               (carve_deg every carve_ms) and breathing in and out.
  zigzag       closes in on alternating diagonal legs of leg_ms.
  hit_and_run  dives in at dive_speed_pct, peels out retreat_px at an angle,
               circles for regroup_ms, dives again.
  lunge        creeps to trigger_px, winds up (stands still), bursts in a
               straight line, recovers.
  flank        works round the target to angle_deg from its heading (180 =
               its back), then closes in.
  erratic      darts to random nearby points, pulled back toward the target
               when it strays past range_px.
  stalk        creeps to keep_px at creep_speed_pct, freezes, creeps again.
  pendulum     swings swing_px side to side across the line to the target,
               distance_px away.
  figure8      traces a figure-8 round the target (along the line to it, or
               on the screen axes).
  spiral       circles while the radius sweeps between outer_px and inner_px.
  mirror       mirror: moves opposite to the target (reflected through a
               centre point); copy: moves the same way it does.
  keep_away    backs off when the target comes inside comfort_px — faster the
               harder it presses — and sways while it keeps its distance.
  shadow       follows lag_ms behind the target's path, offset_px at angle_deg
               from its heading (180 = right behind it).

The target's "heading" is the way it is moving; standing still, it is taken
to face the fighter (so its back is the far side), as Tactical retreat does.

Driven from World.movement_target (target = nearest enemy in Battle, the
cursor in Solo) and stepped by motion.update, so Solo and Battle run the same
code.  Studio preview: tools/fx/studio/movestyle.js is a line-for-line port —
change both together (tools/fx/check_parity.py compares the tables).
"""

import copy
import math
from collections import deque

from . import config


PATTERNS = ["chase", "orbit", "kite", "glide", "zigzag", "hit_and_run", "lunge", "flank",
            "erratic", "stalk", "pendulum", "figure8", "spiral", "mirror", "keep_away", "shadow"]
SELECTS = ["priority", "weighted", "sequence"]
FACES = ["travel", "target"]
ATTACKING = ["any", "yes", "no"]
# Settings that pick from a list, and the list.
ENUMS = {"direction": ["cw", "ccw", "alternate"],
         "strafe": ["cw", "ccw", "alternate", "none"],
         "axis": ["line", "horizontal", "vertical"],
         "flow": ["in_out", "in", "out"],
         "mode": ["mirror", "copy"]}
# Settings that may be negative (degrees).
SIGNED = ["angle_deg", "retreat_angle_deg", "lead_deg", "carve_deg"]

PATTERN_DEFAULTS = {
    "chase": dict(stop_px=0, overshoot_px=0),
    "orbit": dict(radius_px=160, direction="alternate", swap_ms_min=1500, swap_ms_max=3500,
                  lead_deg=30, wobble_pct=0, wobble_ms=2400),
    "kite": dict(min_px=220, max_px=380, strafe="alternate", swap_ms_min=1500, swap_ms_max=3500),
    "glide": dict(radius_px=120, drift_pct=92, direction="alternate", swap_ms_min=1500, swap_ms_max=3500,
                  carve_deg=35, carve_ms=1600, breathe_pct=30),
    "zigzag": dict(amplitude_px=90, leg_ms=350, stop_px=0, smooth=False),
    "hit_and_run": dict(strike_px=40, dive_speed_pct=160, retreat_px=260, retreat_angle_deg=35,
                        regroup_ms=700, dive_timeout_ms=2500),
    "lunge": dict(trigger_px=260, approach_speed_pct=60, windup_ms=250, burst_speed_pct=320,
                  burst_ms=300, recover_ms=500),
    "flank": dict(angle_deg=180, radius_px=130, tolerance_deg=30, stop_px=0),
    "erratic": dict(range_px=200, hop_min_px=60, hop_max_px=160, hop_ms_min=150, hop_ms_max=450,
                    pull_pct=50),
    "stalk": dict(keep_px=150, creep_speed_pct=35, creep_ms_min=600, creep_ms_max=1400,
                  freeze_ms_min=400, freeze_ms_max=1200),
    "pendulum": dict(distance_px=200, swing_px=160, period_ms=1800),
    "figure8": dict(radius_px=140, period_ms=3200, axis="line"),
    "spiral": dict(outer_px=260, inner_px=60, period_ms=4000, direction="cw", flow="in_out"),
    "mirror": dict(mode="mirror", distance_px=220),
    "keep_away": dict(comfort_px=260, pressure_pct=150, sway_px=40, sway_ms=1400),
    "shadow": dict(offset_px=90, angle_deg=180, lag_ms=250),
}
# Layered on whatever pattern runs.  speed_pct scales the character's speed;
# pulse_pct surges it up and down every pulse_ms; inertia_pct carries the
# velocity (0 = turns instantly, 90 = drifts wide); weave_deg swings the
# heading either side every weave_ms; jitter_px shakes the aim point, re-rolled
# every jitter_ms; pause_every_ms (about, 0 = never) stops it for pause_ms;
# face "target" keeps it turned to the target whichever way it moves;
# wall_avoid nudges it off the screen edges.
MODIFIER_DEFAULTS = dict(speed_pct=100, pulse_pct=0, pulse_ms=1000, inertia_pct=0,
                         weave_deg=0, weave_ms=1600, jitter_px=0, jitter_ms=400,
                         pause_every_ms=0, pause_ms=300, face="travel", wall_avoid=True)
# A phase may run only while all of these pass.  dist_max_px 0 = no limit;
# hit_taken_ms / hit_landed_ms 0 = ignore, otherwise only within that long
# after being hit / landing a hit; attacking yes / no = only while (not)
# attacking; fight_ms = only once the fight has run this long.
WHEN_DEFAULTS = dict(dist_min_px=0, dist_max_px=0, hp_min_pct=0, hp_max_pct=100,
                     hit_taken_ms=0, hit_landed_ms=0, attacking="any", fight_ms=0)
PHASE_DEFAULTS = dict(name="", pattern="chase", hold_min_ms=0, hold_max_ms=0, weight=1)
# daze: after a knockback settles it wanders dazed for a moment (as the old
# battle movement does), then the style resumes.
DEFAULTS = dict(enabled=False, select="priority", daze=True, phases=[])

ATTACK_LINGER_MS = 300     # "attacking" stays true this long after an attack ends
SWAP_DEFAULT_HOLD_MS = 2000
HEADING_MIN_SPEED = 0.3    # px/tick: slower than this, the target "faces" the fighter


def _ticks(ms):
    return max(1, int(float(ms) / config.TICK_MS))


def _num(v, d):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return d
    return f if math.isfinite(f) else d


def _fill(raw, defaults):
    """defaults filled from raw: numbers clamped >= 0 (SIGNED: -360..360),
    enums checked, bools coerced."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k, d in defaults.items():
        v = raw.get(k, d)
        if isinstance(d, bool):
            out[k] = bool(v)
        elif isinstance(d, str):
            allowed = ENUMS.get(k) or (FACES if k == "face" else ATTACKING if k == "attacking" else None)
            out[k] = v if isinstance(v, str) and (allowed is None or v in allowed) else d
        else:
            f = _num(v, d)
            out[k] = max(-360.0, min(360.0, f)) if k in SIGNED else max(0.0, f)
    return out


def normalize_phase(raw):
    raw = raw if isinstance(raw, dict) else {}
    ph = _fill(raw, PHASE_DEFAULTS)
    ph["name"] = str(raw.get("name") or "")
    if ph["pattern"] not in PATTERNS:
        ph["pattern"] = "chase"
    ph["params"] = _fill(raw.get("params"), PATTERN_DEFAULTS[ph["pattern"]])
    ph["modifiers"] = _fill(raw.get("modifiers"), MODIFIER_DEFAULTS)
    ph["when"] = _fill(raw.get("when"), WHEN_DEFAULTS)
    if ph["hold_max_ms"] < ph["hold_min_ms"]:
        ph["hold_max_ms"] = ph["hold_min_ms"]
    return ph


def normalize(raw):
    raw = raw if isinstance(raw, dict) else {}
    out = {k: copy.deepcopy(raw.get(k, v)) for k, v in DEFAULTS.items()}
    out["enabled"] = bool(out["enabled"])
    out["daze"] = bool(out["daze"])
    if out["select"] not in SELECTS:
        out["select"] = "priority"
    out["phases"] = [normalize_phase(p) for p in (out["phases"] or []) if isinstance(p, dict)]
    return out


def cfg(fig):
    """The figure's normalised style, or None when it has none / it is off."""
    mode = fig.mode
    char = getattr(mode, "character", None) or {}
    # Keyed on the character dict, so a reload (F5) re-reads the style.
    cached = getattr(mode, "_movestyle_cache", None)
    if cached is not None and cached[0] is char:
        return cached[1]
    raw = ((char.get("_fxkit") or {}).get("movement_style")
           or (char.get("movement") or {}).get("style"))
    out = None
    if isinstance(raw, dict):
        n = normalize(raw)
        if n["enabled"] and n["phases"]:
            out = n
    try:
        mode._movestyle_cache = (char, out)
    except AttributeError:
        pass
    return out


class StyleState:
    """Per-figure style bookkeeping (MotionState.style)."""

    def __init__(self):
        self.tick = 0
        self.live = False
        self.phase = -1
        self.phase_start = 0
        self.phase_until = 0
        self.ps = {}                   # pattern-local state, reset on phase entry
        self.vx = self.vy = 0.0        # carried velocity (inertia)
        self.speed_mult = 1.0
        self.inertia = 0.0
        self.weave = 0.0
        self.face_target = False
        self.ex = self.ey = 0.0
        self.prev_e = None
        self.tvx = self.tvy = 0.0      # smoothed target velocity
        self.hx, self.hy = 1.0, 0.0    # target heading
        self.hist = deque(maxlen=240)  # recent target positions (shadow lag)
        self.hit_taken = -10 ** 9
        self.hit_landed = -10 ** 9
        self.attack_tick = -10 ** 9
        self.pause_next = None
        self.pause_until = 0
        self.jitter_next = 0
        self.jx = self.jy = 0.0


def state(fig):
    m = fig.motion
    st = m.style
    if st is None:
        st = StyleState()
        m.style = st
    return st


def live(fig):
    """True when the style moves this figure this tick (motion.update)."""
    st = fig.motion.style
    return st is not None and st.live


def note_hit_taken(fig):
    st = fig.motion.style
    if st is not None:
        st.hit_taken = st.tick


def note_hit_landed(fig):
    st = fig.motion.style
    if st is not None:
        st.hit_landed = st.tick


def reset_velocity(fig):
    st = fig.motion.style
    if st is not None:
        st.vx = st.vy = 0.0


# ------------------------------------------------------------------ choosing
def _attacking(fig):
    c = fig.combat
    try:
        busy = bool(c.busy)
    except AttributeError:
        busy = False
    return busy or str(getattr(c, "action_anim", "") or "").startswith("attack")


def _passes(fig, st, when, d, bs):
    if d < when["dist_min_px"] * bs:
        return False
    if when["dist_max_px"] > 0 and d > when["dist_max_px"] * bs:
        return False
    p = fig.personality
    hp = 100.0 * p.hp / p.max_hp if p.max_hp else 100.0
    if hp < when["hp_min_pct"] or hp > when["hp_max_pct"]:
        return False
    if when["hit_taken_ms"] > 0 and st.tick - st.hit_taken > _ticks(when["hit_taken_ms"]):
        return False
    if when["hit_landed_ms"] > 0 and st.tick - st.hit_landed > _ticks(when["hit_landed_ms"]):
        return False
    if when["attacking"] != "any":
        on = st.tick - st.attack_tick <= _ticks(ATTACK_LINGER_MS)
        if on != (when["attacking"] == "yes"):
            return False
    if when["fight_ms"] > 0 and st.tick < _ticks(when["fight_ms"]):
        return False
    return True


def _hold_ticks(sty, ph, rng):
    lo, hi = ph["hold_min_ms"], ph["hold_max_ms"]
    if hi <= 0 and sty["select"] != "priority":
        lo = hi = SWAP_DEFAULT_HOLD_MS
    return int(rng.uniform(lo, hi) / config.TICK_MS)


def _choose(fig, st, sty, d, bs, rng):
    phases = sty["phases"]
    if 0 <= st.phase < len(phases) and st.tick < st.phase_until:
        return st.phase
    ok = [i for i, ph in enumerate(phases) if _passes(fig, st, ph["when"], d, bs)]
    if not ok:
        return -1
    sel = sty["select"]
    if sel == "weighted":
        total = sum(phases[i]["weight"] for i in ok)
        if total <= 0:
            return ok[0]
        r = rng.uniform(0, total)
        for i in ok:
            r -= phases[i]["weight"]
            if r <= 0:
                return i
        return ok[-1]
    if sel == "sequence":
        n = len(phases)
        for k in range(1, n + 1):
            i = (st.phase + k) % n if st.phase >= 0 else (k - 1)
            if i in ok:
                return i
        return ok[0]
    return ok[0]


def _enter(st, sty, idx, rng):
    if idx != st.phase or idx < 0:
        st.ps = {}
        st.phase_start = st.tick
        st.pause_next = None
    st.phase = idx
    if idx >= 0:
        st.phase_until = st.tick + _hold_ticks(sty, sty["phases"][idx], rng)


# ------------------------------------------------------------------ geometry
def _rot(x, y, a):
    """(x, y) turned clockwise on screen (y down) by a radians."""
    c, s = math.cos(a), math.sin(a)
    return x * c - y * s, y * c + x * s


def _unit(x, y, fx=1.0, fy=0.0):
    d = (x * x + y * y) ** 0.5
    return (x / d, y / d) if d > 1e-6 else (fx, fy)


class _Ctx:
    """One tick of one pattern: the figure, the target and what the pattern
    leaves for the step (speed, inertia, extra weave, face the target)."""
    __slots__ = ("fig", "st", "ps", "prm", "rng", "bs", "x", "y", "ex", "ey", "d",
                 "ux", "uy", "auto_stop", "t", "speed", "inertia", "weave", "face")


def _ring(c, radius, lead, sign):
    """The point on the circle of `radius` round the target, `lead` radians
    round from the figure (sign +1 = clockwise on screen)."""
    rx, ry = _rot(c.ux, c.uy, sign * lead)
    return c.ex + rx * radius, c.ey + ry * radius


def _dir(c, mode, lo, hi):
    """+1 / -1 travel direction for cw / ccw / alternate (swapping every
    lo..hi ms); 0 for "none"."""
    ps = c.ps
    if mode == "none":
        return 0
    if mode == "cw":
        return 1
    if mode == "ccw":
        return -1
    if "dir" not in ps:
        ps["dir"] = 1 if c.rng.random() < 0.5 else -1
        ps["swap"] = c.st.tick + int(c.rng.uniform(lo, hi) / config.TICK_MS)
    elif c.st.tick >= ps["swap"]:
        ps["dir"] = -ps["dir"]
        ps["swap"] = c.st.tick + max(1, int(c.rng.uniform(lo, hi) / config.TICK_MS))
    return ps["dir"]


def _stop(c, px):
    return px * c.bs if px > 0 else c.auto_stop


# ------------------------------------------------------------------ patterns
# Each returns the aim point (x, y); it may set c.speed / c.inertia / c.weave
# / c.face for this tick.
def _p_chase(c, p):
    over = p["overshoot_px"] * c.bs
    if over > 0:
        return c.ex - c.ux * over, c.ey - c.uy * over
    s = _stop(c, p["stop_px"])
    return c.ex + c.ux * s, c.ey + c.uy * s


def _p_orbit(c, p):
    sign = _dir(c, p["direction"], p["swap_ms_min"], p["swap_ms_max"])
    r = p["radius_px"] * c.bs
    if p["wobble_pct"] > 0:
        r *= 1.0 + min(0.9, p["wobble_pct"] / 100.0) * math.sin(2 * math.pi * c.t / _ticks(p["wobble_ms"]))
    return _ring(c, r, math.radians(p["lead_deg"]), sign)


def _p_kite(c, p):
    lo, hi = p["min_px"] * c.bs, p["max_px"] * c.bs
    if hi < lo:
        lo, hi = hi, lo
    sign = _dir(c, p["strafe"], p["swap_ms_min"], p["swap_ms_max"])
    if c.d > hi:
        mid = (lo + hi) * 0.5
        return c.ex + c.ux * mid, c.ey + c.uy * mid
    if c.d < lo:
        return _ring(c, hi, math.radians(20) * (sign or 1), 1)
    if sign == 0:
        c.speed = 0.0
        return c.x, c.y
    return _ring(c, c.d, math.radians(30), sign)


def _p_glide(c, p):
    sign = _dir(c, p["direction"], p["swap_ms_min"], p["swap_ms_max"])
    r = p["radius_px"] * c.bs
    if p["breathe_pct"] > 0:
        r *= 1.0 + min(0.9, p["breathe_pct"] / 100.0) * math.sin(2 * math.pi * c.t / (_ticks(p["carve_ms"]) * 2.7))
    if p["carve_deg"]:
        c.weave += math.radians(p["carve_deg"]) * math.sin(2 * math.pi * c.t / _ticks(p["carve_ms"]))
    c.inertia = max(c.inertia, min(98.0, p["drift_pct"]))
    return _ring(c, r, math.radians(60), sign or 1)


def _p_zigzag(c, p):
    s = _stop(c, p["stop_px"])
    gap = c.d - s
    amp = p["amplitude_px"] * c.bs
    if gap <= 4 * c.bs or amp <= 0:
        return c.ex + c.ux * s, c.ey + c.uy * s
    leg = _ticks(p["leg_ms"])
    if p["smooth"]:
        side = math.sin(math.pi * c.t / leg)
    else:
        side = 1.0 if (c.t // leg) % 2 == 0 else -1.0
    amp *= min(1.0, gap / (2 * amp))
    look = min(gap, 2 * amp)
    px, py = -c.uy, c.ux
    return c.x - c.ux * look + px * side * amp, c.y - c.uy * look + py * side * amp


def _p_hit_and_run(c, p):
    ps, st = c.ps, c.st
    stage = ps.setdefault("stage", "dive")
    if "t0" not in ps:
        ps["t0"] = st.tick
    el = st.tick - ps["t0"]
    if stage == "dive":
        c.speed = p["dive_speed_pct"] / 100.0
        if (c.d <= p["strike_px"] * c.bs + 2 or el >= _ticks(p["dive_timeout_ms"])
                or st.hit_landed >= ps["t0"]):
            ps["stage"], ps["t0"] = "retreat", st.tick
            ps["sign"] = 1 if c.rng.random() < 0.5 else -1
            ps["away"] = (c.ux, c.uy)
        else:
            return c.ex, c.ey
    if ps["stage"] == "retreat":
        ax, ay = _rot(ps["away"][0], ps["away"][1], ps["sign"] * math.radians(p["retreat_angle_deg"]))
        r = p["retreat_px"] * c.bs
        wx, wy = c.ex + ax * r, c.ey + ay * r
        if (wx - c.x) ** 2 + (wy - c.y) ** 2 < (20 * c.bs) ** 2 or st.tick - ps["t0"] >= _ticks(1500):
            ps["stage"], ps["t0"] = "regroup", st.tick
        else:
            return wx, wy
    # regroup: circle at the current distance, slower, then dive again
    c.speed = 0.6
    if st.tick - ps["t0"] >= _ticks(p["regroup_ms"]):
        ps["stage"], ps["t0"] = "dive", st.tick
    return _ring(c, c.d, math.radians(25), ps.get("sign", 1))


def _p_lunge(c, p):
    ps, st = c.ps, c.st
    stage = ps.setdefault("stage", "approach")
    if "t0" not in ps:
        ps["t0"] = st.tick
    el = st.tick - ps["t0"]
    if stage == "approach":
        trig = p["trigger_px"] * c.bs
        c.speed = p["approach_speed_pct"] / 100.0
        if c.d > trig:
            return c.ex + c.ux * trig * 0.9, c.ey + c.uy * trig * 0.9
        ps["stage"], ps["t0"], el = "windup", st.tick, 0
    if ps["stage"] == "windup":
        c.speed, c.face = 0.0, True
        if el < _ticks(p["windup_ms"]):
            return c.x, c.y
        ps["stage"], ps["t0"], el = "burst", st.tick, 0
        ps["hd"] = (-c.ux, -c.uy)
    if ps["stage"] == "burst":
        c.speed, c.inertia = p["burst_speed_pct"] / 100.0, 0.0
        if el < _ticks(p["burst_ms"]):
            hx, hy = ps["hd"]
            return c.x + hx * 1000.0, c.y + hy * 1000.0
        ps["stage"], ps["t0"], el = "recover", st.tick, 0
    c.speed = 0.0
    if el >= _ticks(p["recover_ms"]):
        ps["stage"], ps["t0"] = "approach", st.tick
    return c.x, c.y


def _p_flank(c, p):
    want = math.atan2(c.st.hy, c.st.hx) + math.radians(p["angle_deg"])
    at = math.atan2(c.uy, c.ux)
    err = (want - at + math.pi) % (2 * math.pi) - math.pi
    r = p["radius_px"] * c.bs
    if abs(err) > math.radians(p["tolerance_deg"]):
        return _ring(c, r, min(abs(err), math.radians(40)), 1 if err > 0 else -1)
    s = _stop(c, p["stop_px"])
    return c.ex + math.cos(want) * s, c.ey + math.sin(want) * s


def _p_erratic(c, p):
    ps, st, rng = c.ps, c.st, c.rng
    if "wp" not in ps or st.tick >= ps["next"]:
        a = rng.uniform(0, 2 * math.pi)
        hop = rng.uniform(min(p["hop_min_px"], p["hop_max_px"]), max(p["hop_min_px"], p["hop_max_px"])) * c.bs
        wx, wy = c.x + math.cos(a) * hop, c.y + math.sin(a) * hop
        rr = p["range_px"] * c.bs
        ox, oy = wx - c.ex, wy - c.ey
        od = (ox * ox + oy * oy) ** 0.5
        if od > rr:
            k = min(1.0, p["pull_pct"] / 100.0)
            nx, ny = c.ex + ox / od * rr, c.ey + oy / od * rr
            wx, wy = wx + (nx - wx) * k, wy + (ny - wy) * k
        ps["wp"] = (wx, wy)
        lo, hi = min(p["hop_ms_min"], p["hop_ms_max"]), max(p["hop_ms_min"], p["hop_ms_max"])
        ps["next"] = st.tick + max(1, int(rng.uniform(lo, hi) / config.TICK_MS))
    return ps["wp"]


def _p_stalk(c, p):
    ps, st, rng = c.ps, c.st, c.rng
    if "until" not in ps or st.tick >= ps["until"]:
        creep = not ps.get("creep", False)
        ps["creep"] = creep
        lo, hi = (p["creep_ms_min"], p["creep_ms_max"]) if creep else (p["freeze_ms_min"], p["freeze_ms_max"])
        ps["until"] = st.tick + max(1, int(rng.uniform(min(lo, hi), max(lo, hi)) / config.TICK_MS))
    if not ps["creep"]:
        c.speed, c.face = 0.0, True
        return c.x, c.y
    c.speed = p["creep_speed_pct"] / 100.0
    k = p["keep_px"] * c.bs
    return c.ex + c.ux * k, c.ey + c.uy * k


def _p_pendulum(c, p):
    ps = c.ps
    ax, ay = ps.get("axis", (c.ux, c.uy))
    ax, ay = _unit(ax + (c.ux - ax) * 0.01, ay + (c.uy - ay) * 0.01, c.ux, c.uy)
    ps["axis"] = (ax, ay)
    dist, sw = p["distance_px"] * c.bs, p["swing_px"] * c.bs
    s = math.sin(2 * math.pi * c.t / _ticks(p["period_ms"]))
    return c.ex + ax * dist - ay * sw * s, c.ey + ay * dist + ax * sw * s


def _p_figure8(c, p):
    ps = c.ps
    if "theta" not in ps:
        ax = p["axis"]
        ps["theta"] = (math.atan2(c.uy, c.ux) if ax == "line" else 0.0 if ax == "horizontal" else math.pi / 2)
    r = p["radius_px"] * c.bs
    s = 2 * math.pi * c.t / _ticks(p["period_ms"])
    lx, ly = r * math.sin(s), r * math.sin(s) * math.cos(s)
    rx, ry = _rot(lx, ly, ps["theta"])
    return c.ex + rx, c.ey + ry


def _p_spiral(c, p):
    per = _ticks(p["period_ms"])
    cyc, f = divmod(c.t, per)
    f = f / float(per)
    sign = {"cw": 1, "ccw": -1}.get(p["direction"], 1 if cyc % 2 == 0 else -1)
    outer, inner = p["outer_px"] * c.bs, p["inner_px"] * c.bs
    flow = p["flow"]
    k = (1.0 - abs(2 * f - 1)) if flow == "in_out" else f if flow == "in" else 1.0 - f
    return _ring(c, outer - (outer - inner) * k, math.radians(35), sign)


def _p_mirror(c, p):
    ps = c.ps
    dd = p["distance_px"] * c.bs
    if "anchor" not in ps:
        ps["anchor"] = ((c.x + c.ex) * 0.5, (c.y + c.ey) * 0.5)
        ps["off"] = _unit(c.x - c.ex, c.y - c.ey, c.ux, c.uy)
    if p["mode"] == "copy":
        ox, oy = ps["off"]
        return c.ex + ox * dd, c.ey + oy * dd
    # The centre point eases to half the distance out from the target, so the
    # reflection settles at distance_px when the target holds still.
    ax, ay = ps["anchor"]
    ax += (c.ex + c.ux * dd * 0.5 - ax) * 0.01
    ay += (c.ey + c.uy * dd * 0.5 - ay) * 0.01
    ps["anchor"] = (ax, ay)
    wx, wy = 2 * ax - c.ex, 2 * ay - c.ey
    ox, oy = wx - c.ex, wy - c.ey
    if ox * ox + oy * oy < dd * dd:
        ux, uy = _unit(ox, oy, c.ux, c.uy)
        wx, wy = c.ex + ux * dd, c.ey + uy * dd
    return wx, wy


def _p_keep_away(c, p):
    comfort = p["comfort_px"] * c.bs
    if c.d < comfort:
        closing = max(0.0, c.st.tvx * c.ux + c.st.tvy * c.uy)
        base = max(0.1, c.fig.motion.speed)
        c.speed = min(3.0, 1.0 + p["pressure_pct"] / 100.0 * closing / base)
        return c.ex + c.ux * comfort * 1.2, c.ey + c.uy * comfort * 1.2
    c.speed = 0.6
    a = math.sin(2 * math.pi * c.t / _ticks(p["sway_ms"])) * p["sway_px"] * c.bs / max(1.0, comfort)
    rx, ry = _rot(c.ux, c.uy, a)
    return c.ex + rx * comfort, c.ey + ry * comfort


def _p_shadow(c, p):
    hist = c.st.hist
    lag = int(p["lag_ms"] / config.TICK_MS)
    px, py = hist[-1 - lag] if len(hist) > lag else hist[0]
    dx, dy = _rot(c.st.hx, c.st.hy, math.radians(p["angle_deg"]))
    off = p["offset_px"] * c.bs
    return px + dx * off, py + dy * off


_PATTERN_FN = {"chase": _p_chase, "orbit": _p_orbit, "kite": _p_kite, "glide": _p_glide,
               "zigzag": _p_zigzag, "hit_and_run": _p_hit_and_run, "lunge": _p_lunge,
               "flank": _p_flank, "erratic": _p_erratic, "stalk": _p_stalk,
               "pendulum": _p_pendulum, "figure8": _p_figure8, "spiral": _p_spiral,
               "mirror": _p_mirror, "keep_away": _p_keep_away, "shadow": _p_shadow}


# ------------------------------------------------------------------ per tick
def _track_target(st, x, y, ex, ey):
    if st.prev_e is not None:
        st.tvx = st.tvx * 0.8 + (ex - st.prev_e[0]) * 0.2
        st.tvy = st.tvy * 0.8 + (ey - st.prev_e[1]) * 0.2
    else:
        # First sight: it faces the fighter, so its back is the far side.
        # Standing still after that keeps the last heading (re-aiming it at
        # the fighter every tick would chase its back round and round).
        st.hx, st.hy = _unit(x - ex, y - ey, st.hx, st.hy)
    st.prev_e = (ex, ey)
    st.hist.append((ex, ey))
    if st.tvx * st.tvx + st.tvy * st.tvy > HEADING_MIN_SPEED * HEADING_MIN_SPEED:
        st.hx, st.hy = _unit(st.tvx, st.tvy)


def _daze(fig, sty):
    """Old battle daze: after a knockback settles, wander for a moment.
    Returns the wander point while dazed, else None."""
    if not sty["daze"]:
        return None
    p, m, t = fig.personality, fig.motion, fig.transform
    if m.bounce_ending and m.bounce_end_ticks == 1 and p.daze_ticks <= 0:
        p.daze_ticks = p.rng.randint(*config.DAZE_TICKS_RANGE)
    if p.daze_ticks <= 0:
        return None
    p.daze_ticks -= 1
    if p.daze_ticks == 0:
        p.hit_power = max(config.HIT_POWER_BASE, p.hit_power * 0.5)
    p.wander_angle += p.wander_sign * p.wander_drift * p.rng.uniform(0.5, 2.0)
    return (t.x + math.cos(p.wander_angle) * 80, t.y + math.sin(p.wander_angle) * 80)


def target(fig, ex, ey, auto_stop=0.0, wall=None):
    """This tick's movement target for a styled figure, or None (no style, or
    no phase passes) = the old movement runs.  (ex, ey) is the nearest enemy
    in Battle, the cursor in Solo.  auto_stop: px it stops short of the
    target when a pattern's stop_px is 0 (where it can attack).  wall:
    callable(fig) -> (dx, dy) edge nudge (ai._wall_repulsion)."""
    sty = cfg(fig)
    if sty is None:
        st = fig.motion.style
        if st is not None:
            st.live = False
        return None
    st = state(fig)
    st.tick += 1
    t = fig.transform
    x, y = t.x, t.y
    _track_target(st, x, y, ex, ey)
    st.ex, st.ey = ex, ey
    if _attacking(fig):
        st.attack_tick = st.tick
    rng = fig.personality.rng
    bs = fig.mode.body_scale()
    dx, dy = x - ex, y - ey
    d = (dx * dx + dy * dy) ** 0.5

    dz = _daze(fig, sty)
    if dz is not None:
        st.live = True
        st.speed_mult, st.inertia, st.weave, st.face_target = 1.0, 0.0, 0.0, False
        return dz

    idx = _choose(fig, st, sty, d, bs, rng)
    if idx != st.phase or st.tick >= st.phase_until:
        _enter(st, sty, idx, rng)
    if idx < 0:
        st.live = False
        return None
    ph = sty["phases"][idx]
    mod = ph["modifiers"]

    c = _Ctx()
    c.fig, c.st, c.ps, c.prm, c.rng, c.bs = fig, st, st.ps, ph["params"], rng, bs
    c.x, c.y, c.ex, c.ey, c.d = x, y, ex, ey, d
    c.ux, c.uy = _unit(dx, dy, -1.0 if t.facing_left else 1.0, 0.0)
    c.auto_stop = auto_stop
    c.t = st.tick - st.phase_start
    c.speed, c.inertia, c.weave, c.face = 1.0, 0.0, 0.0, False
    ax, ay = _PATTERN_FN[ph["pattern"]](c, c.prm)

    # --- modifiers
    sp = c.speed * mod["speed_pct"] / 100.0
    if mod["pulse_pct"] > 0:
        sp *= max(0.0, 1.0 + mod["pulse_pct"] / 100.0 * math.sin(2 * math.pi * st.tick / _ticks(mod["pulse_ms"])))
    if mod["jitter_px"] > 0:
        if st.tick >= st.jitter_next:
            a = rng.uniform(0, 2 * math.pi)
            r = mod["jitter_px"] * bs * rng.random() ** 0.5
            st.jx, st.jy = math.cos(a) * r, math.sin(a) * r
            st.jitter_next = st.tick + _ticks(mod["jitter_ms"])
        ax += st.jx
        ay += st.jy
    if mod["pause_every_ms"] > 0:
        if st.pause_next is None:
            st.pause_next = st.tick + _ticks(mod["pause_every_ms"] * rng.uniform(0.5, 1.5))
        if st.tick >= st.pause_next:
            st.pause_until = st.tick + _ticks(mod["pause_ms"])
            st.pause_next = st.pause_until + _ticks(mod["pause_every_ms"] * rng.uniform(0.5, 1.5))
        if st.tick < st.pause_until:
            sp = 0.0
    weave = c.weave
    if mod["weave_deg"] > 0:
        weave += math.radians(mod["weave_deg"]) * math.sin(2 * math.pi * st.tick / _ticks(mod["weave_ms"]))
    if mod["wall_avoid"] and wall is not None:
        wx, wy = wall(fig)
        ax += wx
        ay += wy

    st.live = True
    st.speed_mult = sp
    st.inertia = min(0.98, max(mod["inertia_pct"], c.inertia) / 100.0)
    st.weave = weave
    st.face_target = c.face or mod["face"] == "target"
    return ax, ay


def step(fig, tx, ty, sf=1.0, margin=10):
    """motion.update for a styled figure: head for (tx, ty) at the style's
    speed, turned by its weave, with its inertia carrying the velocity."""
    st = fig.motion.style
    t = fig.transform
    dx, dy = tx - t.x, ty - t.y
    d = (dx * dx + dy * dy) ** 0.5
    speed = fig.motion.speed * sf * st.speed_mult
    if speed <= 0.0 or d < 0.5:
        wx = wy = 0.0
    else:
        v = min(speed, d)
        wx, wy = dx / d * v, dy / d * v
        if st.weave and d > speed:
            wx, wy = _rot(wx, wy, st.weave)
    a = 1.0 - st.inertia
    st.vx += (wx - st.vx) * a
    st.vy += (wy - st.vy) * a
    nx, ny = t.x + st.vx, t.y + st.vy
    # carried velocity into a screen edge is dropped, not ground along it
    if not (margin <= nx <= fig.screen_w - margin):
        st.vx = 0.0
    if not (margin <= ny <= fig.screen_h - margin):
        st.vy = 0.0
    t.x += st.vx
    t.y += st.vy


def face(fig):
    """After fig.face: keep it turned to the target when the style says so."""
    st = fig.motion.style
    if st is None or not st.live or not st.face_target or fig.aim is not None:
        return
    dx = st.ex - fig.transform.x
    if dx < -0.001:
        fig.transform.facing_left = True
    elif dx > 0.001:
        fig.transform.facing_left = False
