"""Hierarchical gameplay tags.

Replaces every boolean flag in v1 (`stationary`, `counter_only`,
`disable_basic_attack`, `disable_survival_teleport`, ...) with one uniform
mechanism.

A tag is a dotted string: "state.airborne", "immune.knockback",
"block.ability.basic".  Tags nest: holding "immune" matches a query for
"immune.knockback", but holding "immune.knockback" does NOT match a query
for "immune.stun".  Parent implies child; child does not imply sibling.

Determinism note: TagSet iterates in insertion order (dict), never in set
order, so any behaviour driven by tag iteration is reproducible.
"""

__all__ = ["TagSet", "TagQuery", "normalize"]


def normalize(tag):
    """Lowercase, strip, collapse separators.  '  State.AirBorne ' -> 'state.airborne'."""
    t = str(tag).strip().lower().replace("/", ".").replace(" ", "_")
    while ".." in t:
        t = t.replace("..", ".")
    return t.strip(".")


class TagSet:
    """An ordered, reference-counted set of hierarchical tags.

    Reference counting matters: two independent effects may both grant
    "immune.knockback", and the first one expiring must not strip immunity
    that the second is still providing.
    """

    __slots__ = ("_counts",)

    def __init__(self, tags=()):
        self._counts = {}
        for t in tags:
            self.add(t)

    # ---- mutation -------------------------------------------------
    def add(self, tag, n=1):
        t = normalize(tag)
        if not t:
            return
        self._counts[t] = self._counts.get(t, 0) + n

    def remove(self, tag, n=1):
        t = normalize(tag)
        c = self._counts.get(t, 0) - n
        if c > 0:
            self._counts[t] = c
        else:
            self._counts.pop(t, None)

    def clear(self):
        self._counts.clear()

    # ---- query ----------------------------------------------------
    def has(self, tag):
        """True if `tag` is held, or if any ancestor of `tag` is held.

        has('immune.knockback') is True when 'immune' is held.
        """
        t = normalize(tag)
        if not t:
            return False
        if t in self._counts:
            return True
        parts = t.split(".")
        for i in range(1, len(parts)):
            if ".".join(parts[:i]) in self._counts:
                return True
        return False

    def has_exact(self, tag):
        return normalize(tag) in self._counts

    def has_any(self, tags):
        return any(self.has(t) for t in tags)

    def has_all(self, tags):
        return all(self.has(t) for t in tags)

    def under(self, prefix):
        """All held tags at or below `prefix`, in insertion order."""
        p = normalize(prefix)
        return [t for t in self._counts if t == p or t.startswith(p + ".")]

    # ---- dunder ---------------------------------------------------
    def __contains__(self, tag):
        return self.has(tag)

    def __iter__(self):
        return iter(self._counts)

    def __len__(self):
        return len(self._counts)

    def __repr__(self):
        return "TagSet(%s)" % ", ".join(sorted(self._counts))

    def snapshot(self):
        """Deterministic sorted tuple — used by the state checksum."""
        return tuple(sorted(self._counts))


class TagQuery:
    """A declarative requirement, authored in JSON as:

        {"all": ["state.grounded"], "any": [...], "none": ["stunned"]}

    Empty query passes.  This is the single gating mechanism used by
    abilities, effects and cues alike.
    """

    __slots__ = ("all_", "any_", "none_")

    def __init__(self, spec=None):
        spec = spec or {}
        if isinstance(spec, (list, tuple)):
            spec = {"all": list(spec)}
        self.all_ = [normalize(t) for t in spec.get("all", ())]
        self.any_ = [normalize(t) for t in spec.get("any", ())]
        self.none_ = [normalize(t) for t in spec.get("none", ())]

    def test(self, tagset):
        if self.all_ and not tagset.has_all(self.all_):
            return False
        if self.any_ and not tagset.has_any(self.any_):
            return False
        if self.none_ and tagset.has_any(self.none_):
            return False
        return True

    def is_empty(self):
        return not (self.all_ or self.any_ or self.none_)

    def __repr__(self):
        return "TagQuery(all=%s any=%s none=%s)" % (self.all_, self.any_, self.none_)
