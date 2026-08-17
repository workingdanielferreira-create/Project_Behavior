"""Attributes — every number that describes an actor.

THE RULE THAT DEFINES V2:  an attribute's base value may only be changed by
an Effect.  Nothing else writes.  This is what makes "how does this character
deal damage?" have exactly one answer, where v1 had six.

Each attribute has:
    base        the authored value, changed only by effects
    modifiers   temporary add/mul contributions, keyed by source id
    current     derived  =  clamp((base + sum(add)) * prod(mul))

`current` is cached and invalidated on write, because it is read many times
per tick per actor.
"""

__all__ = ["Attribute", "AttributeSet", "ATTR_DEFAULTS"]

# Canonical attribute names.  Anything not listed here is still allowed
# (characters may define their own), but these are the ones the engine reads.
ATTR_DEFAULTS = {
    "hp":             100.0,
    "hp_max":         100.0,
    "move_speed":       2.0,
    "chase_speed":      2.6,
    "scale":            1.0,
    "attack_range":    52.0,
    "hurt_radius":     18.0,
    "damage":           1.0,
    "knockback":        6.0,
    "cooldown_rate":    1.0,   # multiplier on all ability cooldowns
    "aggression":       0.5,   # utility bias toward offence
    "caution":          0.5,   # utility bias toward retreat/defence
}

_UNBOUNDED = float("inf")

# (min, max) clamps for attributes where a nonsense value would corrupt the sim.
_CLAMPS = {
    "hp":            (0.0, _UNBOUNDED),
    "hp_max":        (1.0, _UNBOUNDED),
    "move_speed":    (0.0, 40.0),
    "chase_speed":   (0.0, 40.0),
    "scale":         (0.05, 12.0),
    "hurt_radius":   (1.0, 400.0),
    "cooldown_rate": (0.05, 20.0),
}


class Attribute:
    __slots__ = ("name", "base", "_add", "_mul", "_cache")

    def __init__(self, name, base=0.0):
        self.name = name
        self.base = float(base)
        self._add = {}      # source_id -> flat addend
        self._mul = {}      # source_id -> multiplier
        self._cache = None

    # ---- writes (effects only) ------------------------------------
    def set_base(self, v):
        self.base = float(v)
        self._cache = None

    def add_base(self, dv):
        self.base += float(dv)
        self._cache = None

    def add_modifier(self, source, add=0.0, mul=1.0):
        if add:
            self._add[source] = float(add)
        if mul != 1.0:
            self._mul[source] = float(mul)
        self._cache = None

    def remove_modifier(self, source):
        self._add.pop(source, None)
        self._mul.pop(source, None)
        self._cache = None

    def clear_modifiers(self):
        self._add.clear()
        self._mul.clear()
        self._cache = None

    # ---- read -----------------------------------------------------
    @property
    def current(self):
        if self._cache is not None:
            return self._cache
        v = self.base
        for a in self._add.values():
            v += a
        for m in self._mul.values():
            v *= m
        lo, hi = _CLAMPS.get(self.name, (-_UNBOUNDED, _UNBOUNDED))
        if v < lo:
            v = lo
        elif v > hi:
            v = hi
        self._cache = v
        return v

    def __float__(self):
        return self.current

    def __repr__(self):
        return "<%s %.3f (base %.3f)>" % (self.name, self.current, self.base)


class AttributeSet:
    """Ordered map of name -> Attribute.  Iteration order is insertion order,
    so checksums are stable."""

    __slots__ = ("_a",)

    def __init__(self, values=None):
        self._a = {}
        for k, v in ATTR_DEFAULTS.items():
            self._a[k] = Attribute(k, v)
        if values:
            for k, v in values.items():
                self.set_base(k, v)

    def define(self, name, base=0.0):
        if name not in self._a:
            self._a[name] = Attribute(name, base)
        return self._a[name]

    def attr(self, name):
        a = self._a.get(name)
        if a is None:
            a = self.define(name, ATTR_DEFAULTS.get(name, 0.0))
        return a

    def get(self, name, default=0.0):
        a = self._a.get(name)
        return a.current if a is not None else default

    def set_base(self, name, v):
        self.attr(name).set_base(v)

    def add_base(self, name, dv):
        self.attr(name).add_base(dv)

    def has(self, name):
        return name in self._a

    def names(self):
        return list(self._a)

    def snapshot(self):
        """Deterministic ((name, rounded_value), ...) for checksums.

        Rounded to 4dp so that irrelevant float noise does not churn the
        hash while real behavioural drift still shows up.
        """
        return tuple((k, round(a.current, 4)) for k, a in self._a.items())

    def __repr__(self):
        return "AttributeSet(%d)" % len(self._a)
