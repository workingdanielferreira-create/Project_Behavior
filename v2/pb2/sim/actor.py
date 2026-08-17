"""Actor — the tens-tier entity.

Fighters, clones and summons are Actors.  Bullets and sparks are not (see
motes.py).  An Actor is rich and individually addressable; there are never
enough of them for that to cost anything.

v1's Combatant had 85 __slots__ because every mechanic bolted its own state
onto the component.  An Actor has ~20, because mechanic state lives inside
the AbilityInstance that owns it.  Adding a mechanic adds nothing here.
"""

import math

from ..core.attributes import AttributeSet
from ..core.tags import TagSet
from ..core.intent import Intent

__all__ = ["Actor", "AbilityInstance"]


class AbilityInstance:
    """A live ability owned by an actor.

    Owns its own cooldown, phase and scratch state.  This is why the Actor
    doesn't grow slots when a mechanic is added: the mechanic's state lives
    here, in the instance, not on the entity.
    """

    __slots__ = ("key", "impl", "params", "cooldown", "phase", "phase_t",
                 "active", "state", "last_used", "uses", "tags_while_active",
                 "gate", "priority")

    def __init__(self, key, impl, params=None):
        self.key = key
        self.impl = impl
        self.params = params or {}
        self.cooldown = 0
        self.phase = None
        self.phase_t = 0
        self.active = False
        self.state = {}
        self.last_used = -99999
        self.uses = 0
        self.tags_while_active = []
        self.gate = None          # TagQuery, set by the loader
        self.priority = 0.0

    def p(self, name, default=0.0):
        """Read an authored parameter with a default."""
        v = self.params.get(name, default)
        return v

    def ready(self):
        return self.cooldown <= 0 and not self.active

    def start_cooldown(self, ticks, rate=1.0):
        self.cooldown = int(max(0, ticks / max(0.05, rate)))

    def __repr__(self):
        return "<Ability %s cd=%d %s>" % (
            self.key, self.cooldown, "ACTIVE" if self.active else "")


class Actor:
    __slots__ = ("id", "side", "archetype", "x", "y", "vx", "vy", "facing",
                 "attrs", "tags", "abilities", "brains", "intent",
                 "rng", "alive", "world", "anim", "anim_t", "hitstun",
                 "target_id", "scratch", "visual", "spawn_tick")

    def __init__(self, ident, archetype, side=0, x=0.0, y=0.0,
                 attrs=None, rng=None):
        self.id = int(ident)
        self.side = int(side)
        self.archetype = archetype          # the loaded CharacterDef
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.facing = 0.0
        self.attrs = attrs if attrs is not None else AttributeSet()
        self.tags = TagSet()
        self.abilities = {}                 # key -> AbilityInstance
        self.brains = []                    # ordered; first writer wins ties
        self.intent = Intent()
        self.rng = rng
        self.alive = True
        self.world = None
        self.anim = "idle"
        self.anim_t = 0
        self.hitstun = 0
        self.target_id = None
        self.scratch = {}
        self.visual = {}                    # palette / sprite hints for render
        self.spawn_tick = 0

    # ---- convenience readers --------------------------------------
    @property
    def hp(self):
        return self.attrs.get("hp")

    @property
    def hp_max(self):
        return self.attrs.get("hp_max")

    @property
    def hp_frac(self):
        m = self.attrs.get("hp_max")
        return self.attrs.get("hp") / m if m > 0 else 0.0

    @property
    def busy(self):
        """True while an ability owns the body.  Movement is suppressed."""
        return self.tags.has("state.busy") or self.hitstun > 0

    def distance_to(self, other):
        return math.hypot(other.x - self.x, other.y - self.y)

    def angle_to(self, tx, ty):
        return math.atan2(ty - self.y, tx - self.x)

    # ---- abilities -------------------------------------------------
    def grant(self, inst):
        self.abilities[inst.key] = inst
        return inst

    def revoke(self, key):
        return self.abilities.pop(key, None)

    def ability(self, key):
        return self.abilities.get(key)

    def ordered_abilities(self):
        """Insertion order — deterministic iteration for scoring/ticking."""
        return list(self.abilities.values())

    # ---- tags ------------------------------------------------------
    def add_tag(self, t, n=1):
        self.tags.add(t, n)

    def remove_tag(self, t, n=1):
        self.tags.remove(t, n)

    def has_tag(self, t):
        return self.tags.has(t)

    # ---- damage entry point ---------------------------------------
    # NOTE: nothing calls this directly.  Damage arrives only through the
    # `damage` Effect, which is the single authority (see effects.py).
    def _apply_hp_delta(self, delta):
        self.attrs.add_base("hp", delta)
        hp = self.attrs.get("hp")
        if hp <= 0.0 and self.alive:
            self.alive = False
            return True          # died this call
        return False

    def snapshot(self):
        """Read-only tuple for the opposing side's frozen view."""
        return (self.id, self.side, round(self.x, 2), round(self.y, 2),
                round(self.hp, 2), self.alive)

    def checksum_row(self):
        return (self.id, self.side,
                round(self.x, 2), round(self.y, 2),
                round(self.vx, 3), round(self.vy, 3),
                round(self.hp, 3), int(self.alive),
                self.anim, self.tags.snapshot())

    def __repr__(self):
        return "<Actor %d %s side%d (%.0f,%.0f) hp %.0f/%.0f>" % (
            self.id, getattr(self.archetype, "key", "?"), self.side,
            self.x, self.y, self.hp, self.hp_max)
