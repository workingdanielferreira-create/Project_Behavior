"""Motes — the thousands-tier.

v1 gave every bullet, spark, petal and afterimage its own Python object with
its own `update()` and its own `drawPixmap` call.  Cost scaled with the
number of Python objects, which is why FX density had a low ceiling.

A mote is a row in a set of parallel arrays (structure-of-arrays).  One
vectorised operation advances every mote in the world:

    x += vx * sf ;  y += vy * sf ;  age += 1

There is no per-mote Python call.  A 2000-mote frame costs roughly what a
20-mote frame costs.

BACKENDS
    numpy present  -> real vector ops (the fast path)
    numpy absent   -> the identical API over `array.array`, looping in
                      Python.  Slower, lower budget, but the engine runs.

The two backends are behaviourally identical; only the budget differs.
Determinism is preserved in both: no operation depends on iteration order.

Slot reuse: dead rows are recycled from a free list, so the arrays reach a
steady-state size instead of growing forever.
"""

import math

try:
    import numpy as _np
    HAVE_NUMPY = True
except Exception:                                   # pragma: no cover
    _np = None
    HAVE_NUMPY = False

__all__ = ["MotePool", "HAVE_NUMPY", "KIND_NAMES",
           "K_BULLET", "K_SPARK", "K_PETAL", "K_AFTERIMAGE", "K_RING",
           "K_BEAM", "K_DEBRIS"]

# Mote kinds.  Kind drives draw-atlas selection and collision participation.
K_BULLET = 0
K_SPARK = 1
K_PETAL = 2
K_AFTERIMAGE = 3
K_RING = 4
K_BEAM = 5
K_DEBRIS = 6
KIND_NAMES = ["bullet", "spark", "petal", "afterimage", "ring", "beam", "debris"]

# Flags (bitfield in the `flag` array)
F_ALIVE = 1
F_HITS = 2         # participates in collision (a real hitbox)
F_PIERCE = 4       # survives contact
F_HOMING = 8
F_GRAVITY = 16
F_FADE = 32        # alpha ramps down over life

_FIELDS_F = ("x", "y", "vx", "vy", "radius", "damage", "size",
             "spin", "rot", "drag", "homing_rate")
_FIELDS_I = ("age", "life", "kind", "flag", "side", "owner", "cue", "color")

_GROW = 512


class MotePool:
    """Fixed-field, slot-recycling pool of simple moving things."""

    def __init__(self, capacity=2048):
        self.capacity = 0
        self.count = 0            # highest occupied slot + 1 (watermark)
        self._free = []
        self._arrays = {}
        self._grow(max(_GROW, int(capacity)))

    # ------------------------------------------------------------------
    # allocation
    # ------------------------------------------------------------------
    def _grow(self, new_cap):
        if HAVE_NUMPY:
            for f in _FIELDS_F:
                old = self._arrays.get(f)
                arr = _np.zeros(new_cap, dtype=_np.float64)
                if old is not None:
                    arr[:len(old)] = old
                self._arrays[f] = arr
            for f in _FIELDS_I:
                old = self._arrays.get(f)
                arr = _np.zeros(new_cap, dtype=_np.int32)
                if old is not None:
                    arr[:len(old)] = old
                self._arrays[f] = arr
        else:
            from array import array
            for f in _FIELDS_F:
                old = self._arrays.get(f)
                arr = array("d", [0.0]) * new_cap
                if old is not None:
                    arr[:len(old)] = old
                self._arrays[f] = arr
            for f in _FIELDS_I:
                old = self._arrays.get(f)
                arr = array("l", [0]) * new_cap
                if old is not None:
                    arr[:len(old)] = old
                self._arrays[f] = arr
        self.capacity = new_cap

    def __getattr__(self, name):
        # x, y, vx ... resolve straight to the backing array
        arrays = self.__dict__.get("_arrays")
        if arrays and name in arrays:
            return arrays[name]
        raise AttributeError(name)

    def _alloc(self):
        if self._free:
            return self._free.pop()
        if self.count >= self.capacity:
            self._grow(self.capacity * 2)
        i = self.count
        self.count += 1
        return i

    # ------------------------------------------------------------------
    # spawning
    # ------------------------------------------------------------------
    def spawn(self, x, y, vx=0.0, vy=0.0, kind=K_BULLET, life=120,
              radius=0.0, damage=0.0, size=1.0, side=0, owner=-1,
              cue=0, color=0, spin=0.0, rot=0.0, drag=1.0,
              homing_rate=0.0, hits=False, pierce=False, homing=False,
              gravity=False, fade=True):
        """Create one mote.  Returns its slot index."""
        i = self._alloc()
        a = self._arrays
        a["x"][i] = x
        a["y"][i] = y
        a["vx"][i] = vx
        a["vy"][i] = vy
        a["radius"][i] = radius
        a["damage"][i] = damage
        a["size"][i] = size
        a["spin"][i] = spin
        a["rot"][i] = rot
        a["drag"][i] = drag
        a["homing_rate"][i] = homing_rate
        a["age"][i] = 0
        a["life"][i] = int(life)
        a["kind"][i] = int(kind)
        a["side"][i] = int(side)
        a["owner"][i] = int(owner)
        a["cue"][i] = int(cue)
        a["color"][i] = int(color)
        flag = F_ALIVE
        if hits:
            flag |= F_HITS
        if pierce:
            flag |= F_PIERCE
        if homing:
            flag |= F_HOMING
        if gravity:
            flag |= F_GRAVITY
        if fade:
            flag |= F_FADE
        a["flag"][i] = flag
        return i

    def spawn_burst(self, x, y, n, speed_min, speed_max, rng,
                    angle_from=0.0, angle_to=math.tau, **kw):
        """Spawn `n` motes in a fan.  Angles are deterministic given `rng`."""
        out = []
        span = angle_to - angle_from
        for k in range(int(n)):
            frac = (k + 0.5) / max(1, n)
            ang = angle_from + span * frac + rng.jitter(span / max(2, n) * 0.5)
            spd = rng.uniform(speed_min, speed_max)
            out.append(self.spawn(x, y,
                                  math.cos(ang) * spd, math.sin(ang) * spd,
                                  rot=ang, **kw))
        return out

    def kill(self, i):
        a = self._arrays
        if a["flag"][i] & F_ALIVE:
            a["flag"][i] = 0
            a["life"][i] = 0
            self._free.append(int(i))

    def alive(self, i):
        return bool(self._arrays["flag"][i] & F_ALIVE)

    # ------------------------------------------------------------------
    # the tick — this is the whole point of the module
    # ------------------------------------------------------------------
    def tick(self, speed_field=None, gravity=0.28, bounds=None):
        """Advance every mote by one step.

        `speed_field` is a callable (xs, ys) -> scale factors, implementing
        position-based time dilation.  Movement AND age advance by the same
        factor, so range is preserved and motion simply plays slower —
        matching v1's behaviour.
        """
        n = self.count
        if n == 0:
            return 0
        a = self._arrays

        if HAVE_NUMPY:
            live = (a["flag"][:n] & F_ALIVE).astype(bool)
            if not live.any():
                return 0
            x, y = a["x"][:n], a["y"][:n]
            vx, vy = a["vx"][:n], a["vy"][:n]

            sf = _np.ones(n)
            if speed_field is not None:
                sf = speed_field(x, y)

            grav = (a["flag"][:n] & F_GRAVITY).astype(bool)
            if grav.any():
                vy[grav] += gravity * sf[grav]

            drag = a["drag"][:n]
            has_drag = drag != 1.0
            if has_drag.any():
                vx[has_drag] *= drag[has_drag]
                vy[has_drag] *= drag[has_drag]

            x[live] += vx[live] * sf[live]
            y[live] += vy[live] * sf[live]
            a["rot"][:n][live] += a["spin"][:n][live]

            # age advances with the same dilation, in whole ticks
            a["age"][:n][live] += _np.maximum(1, _np.round(sf[live])).astype(_np.int32)

            expired = live & (a["age"][:n] >= a["life"][:n])
            if bounds is not None:
                x0, y0, x1, y1 = bounds
                oob = live & ((x < x0 - 64) | (x > x1 + 64) |
                              (y < y0 - 64) | (y > y1 + 64))
                expired = expired | oob
            if expired.any():
                idx = _np.nonzero(expired)[0]
                a["flag"][:n][expired] = 0
                self._free.extend(int(i) for i in idx)
            return int(live.sum())

        # ---- pure-python fallback -------------------------------------
        alive_n = 0
        x, y = a["x"], a["y"]
        vx, vy = a["vx"], a["vy"]
        flag, age, life = a["flag"], a["age"], a["life"]
        for i in range(n):
            if not (flag[i] & F_ALIVE):
                continue
            sf = 1.0
            if speed_field is not None:
                sf = speed_field(x[i], y[i])
            if flag[i] & F_GRAVITY:
                vy[i] += gravity * sf
            d = a["drag"][i]
            if d != 1.0:
                vx[i] *= d
                vy[i] *= d
            x[i] += vx[i] * sf
            y[i] += vy[i] * sf
            a["rot"][i] += a["spin"][i]
            age[i] += max(1, int(round(sf)))
            dead = age[i] >= life[i]
            if not dead and bounds is not None:
                x0, y0, x1, y1 = bounds
                dead = (x[i] < x0 - 64 or x[i] > x1 + 64 or
                        y[i] < y0 - 64 or y[i] > y1 + 64)
            if dead:
                flag[i] = 0
                self._free.append(i)
            else:
                alive_n += 1
        return alive_n

    # ------------------------------------------------------------------
    # queries used by collision and rendering
    # ------------------------------------------------------------------
    def live_indices(self):
        n = self.count
        a = self._arrays
        if HAVE_NUMPY:
            return _np.nonzero((a["flag"][:n] & F_ALIVE).astype(bool))[0]
        return [i for i in range(n) if a["flag"][i] & F_ALIVE]

    def hitting_indices(self, side=None):
        """Live motes that carry a real hitbox, optionally filtered to a side."""
        n = self.count
        a = self._arrays
        if HAVE_NUMPY:
            m = ((a["flag"][:n] & (F_ALIVE | F_HITS)) == (F_ALIVE | F_HITS))
            if side is not None:
                m &= (a["side"][:n] == side)
            return _np.nonzero(m)[0]
        want = F_ALIVE | F_HITS
        return [i for i in range(n)
                if (a["flag"][i] & want) == want
                and (side is None or a["side"][i] == side)]

    def alive_count(self):
        n = self.count
        a = self._arrays
        if HAVE_NUMPY:
            return int(((a["flag"][:n] & F_ALIVE) != 0).sum())
        return sum(1 for i in range(n) if a["flag"][i] & F_ALIVE)

    def compact(self):
        """Lower the watermark when the tail is empty — keeps tick cost
        proportional to live motes after a burst subsides."""
        a = self._arrays
        n = self.count
        while n > 0 and not (a["flag"][n - 1] & F_ALIVE):
            n -= 1
        if n != self.count:
            self.count = n
            self._free = [i for i in self._free if i < n]

    def clear(self):
        n = self.count
        if n:
            if HAVE_NUMPY:
                self._arrays["flag"][:n] = 0
            else:
                for i in range(n):
                    self._arrays["flag"][i] = 0
        self.count = 0
        self._free = []

    def checksum_rows(self, limit=None):
        """Deterministic digest input: live motes, rounded, ordered by slot."""
        out = []
        a = self._arrays
        for i in self.live_indices():
            i = int(i)
            out.append((i, round(float(a["x"][i]), 2), round(float(a["y"][i]), 2),
                        int(a["kind"][i]), int(a["age"][i])))
            if limit and len(out) >= limit:
                break
        return out

    def __len__(self):
        return self.alive_count()

    def __repr__(self):
        return "MotePool(alive=%d watermark=%d cap=%d backend=%s)" % (
            self.alive_count(), self.count, self.capacity,
            "numpy" if HAVE_NUMPY else "python")
