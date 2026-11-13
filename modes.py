"""
Figure modes — the polymorphic replacement for scattered `behavior_mode == 1`.

A mode encodes one figure type's *policy*: which sprite bundle it uses, its
speeds, and a handful of behavioural predicates the systems query instead of
branching on an integer.  Modes are stateless singletons; a Figure just holds a
reference to one.

Adding a new figure type:
  1. write a `FigureMode` subclass and decorate it with `@register`
  2. add its tuning dict to config.MODE_CONFIGS (and key to MODE_ORDER)
  3. drop its sprite files next to the script
No other file changes.  Every system already routes through the predicates.
"""

from . import config

MODE_REGISTRY = {}


def register(cls):
    inst = cls()
    MODE_REGISTRY[inst.key] = inst
    return cls


def get_mode(key):
    return MODE_REGISTRY[key]


def ordered_modes():
    """Modes in cycle order, skipping any whose key isn't registered."""
    return [k for k in config.MODE_ORDER if k in MODE_REGISTRY]


class FigureMode:
    key = "base"

    # --- tuning ---
    def speeds(self):
        return config.MODE_CONFIGS[self.key]

    # --- behavioural predicates (queried by systems) ---
    def can_shoot(self):
        """Does this figure fire projectiles in shoot/battle mode?"""
        return False

    def uses_melee(self):
        """Does this figure dash-lunge and react to threats with dodges?"""
        return False

    def retreats(self):
        """May this figure back away from a close enemy in battle?"""
        return False

    def charges_full(self):
        """Ignore aggression-scaled standoff distance and close all the way?"""
        return False

    def wander_blend(self, dist, strength):
        """How much lateral wander to mix into the chase vector in battle."""
        return min(1.0, dist / 300.0) * strength


@register
class RunnerMode(FigureMode):
    key = "runner"

    def can_shoot(self):
        return True

    def retreats(self):
        return True


@register
class SwordsmanMode(FigureMode):
    key = "swordsman"

    def uses_melee(self):
        return True

    def charges_full(self):
        return True

    def wander_blend(self, dist, strength):
        # Charge straight: only a sliver of lateral wander so it reaches range.
        return min(0.15, dist / 300.0) * strength
