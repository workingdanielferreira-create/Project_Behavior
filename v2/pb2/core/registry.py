"""The capability registry — V2's answer to "adding a mechanic touches 7 files".

In v1, a new mechanic meant: a constant block in config.py, a class in
combat.py, a slot on Combatant, a spawn trigger, a drain in CombatSystem, a
world list in app.py, and a draw block in _paint.  Seven files, every time.

In v2 there are exactly three extension points, and each is one decorator:

    @ability("blink")      class Blink(Ability):  score() / start() / tick()
    @effect("damage")      class Damage(Effect):  apply()
    @cue("crescent")       class Crescent(Cue):   emit()

Drop a file in sim/abilities/ or render/cues/, import it in that package's
__init__, and it is immediately addressable from any character JSON.  No
engine file is edited.

Registration is fail-loud: a duplicate key or an unknown lookup raises,
rather than silently doing nothing (v1's dominant failure mode).
"""

__all__ = [
    "ability", "effect", "cue", "brain",
    "get_ability", "get_effect", "get_cue", "get_brain",
    "known_abilities", "known_effects", "known_cues",
    "RegistryError",
]


class RegistryError(LookupError):
    pass


_ABILITIES = {}
_EFFECTS = {}
_CUES = {}
_BRAINS = {}


def _make_decorator(table, kind):
    def deco(key, **meta):
        k = str(key).strip().lower()
        if not k:
            raise RegistryError("%s key must be non-empty" % kind)

        def wrap(cls):
            if k in table and table[k] is not cls:
                raise RegistryError(
                    "duplicate %s key %r (already registered by %s)"
                    % (kind, k, table[k].__module__))
            cls.KEY = k
            cls.META = dict(meta)
            table[k] = cls
            return cls
        return wrap
    return deco


ability = _make_decorator(_ABILITIES, "ability")
effect = _make_decorator(_EFFECTS, "effect")
cue = _make_decorator(_CUES, "cue")
brain = _make_decorator(_BRAINS, "brain")


def _get(table, kind, key):
    k = str(key).strip().lower()
    try:
        return table[k]
    except KeyError:
        known = ", ".join(sorted(table)) or "<none>"
        raise RegistryError(
            "unknown %s %r — registered: %s" % (kind, k, known))


def get_ability(key):
    return _get(_ABILITIES, "ability", key)


def get_effect(key):
    return _get(_EFFECTS, "effect", key)


def get_cue(key):
    return _get(_CUES, "cue", key)


def get_brain(key):
    return _get(_BRAINS, "brain", key)


def known_abilities():
    return sorted(_ABILITIES)


def known_effects():
    return sorted(_EFFECTS)


def known_cues():
    return sorted(_CUES)


def known_brains():
    return sorted(_BRAINS)


def describe():
    """Human-readable capability inventory — used by tools and the schema
    generator so documentation cannot drift from code."""
    return {
        "abilities": {k: (v.__doc__ or "").strip().split("\n")[0]
                      for k, v in sorted(_ABILITIES.items())},
        "effects": {k: (v.__doc__ or "").strip().split("\n")[0]
                    for k, v in sorted(_EFFECTS.items())},
        "cues": {k: (v.__doc__ or "").strip().split("\n")[0]
                 for k, v in sorted(_CUES.items())},
    }
