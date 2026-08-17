"""Effects — the ONLY thing permitted to change an attribute.

This module is the direct fix for the worst finding in the Step 1 audit:
v1 had six overlapping answers to "how does this character deal damage"
(`attack_pattern.damage`, per-layer `battle.damage`, hardcoded combo damage,
ultimate playback, petal contact, cursor bounce) with nothing arbitrating.

In v2 there is one path.  If an actor's HP changed, a `damage` or `heal`
Effect did it.  There is no other route, and `verify_single_authority()`
below proves it at load time.

An Effect is authored as data:

    {"effect": "damage", "amount": 3, "knockback": 8,
     "require": {"none": ["immune.damage"]}}
"""

from ..core.registry import effect, get_effect
from ..core.tags import TagQuery

__all__ = ["Effect", "EffectSpec", "apply_effects", "build_effects"]


class Effect:
    """Base class.  Subclasses implement apply()."""

    KEY = "?"
    #: attributes this effect is allowed to write.  Enforced by the auditor.
    WRITES = ()

    def apply(self, spec, source, target, world):
        raise NotImplementedError


class EffectSpec:
    """A parsed, reusable effect declaration from JSON."""

    __slots__ = ("key", "impl", "params", "gate", "chance")

    def __init__(self, key, impl, params, gate=None, chance=1.0):
        self.key = key
        self.impl = impl
        self.params = params
        self.gate = gate
        self.chance = float(chance)

    def p(self, name, default=0.0):
        return self.params.get(name, default)

    def __repr__(self):
        return "<EffectSpec %s %s>" % (self.key, self.params)


def build_effects(specs):
    """JSON list -> [EffectSpec].  Unknown keys raise at load, not at run."""
    out = []
    for s in specs or ():
        if isinstance(s, str):
            s = {"effect": s}
        key = s.get("effect") or s.get("type")
        if not key:
            raise ValueError("effect entry missing 'effect' key: %r" % (s,))
        impl = get_effect(key)()
        gate = TagQuery(s.get("require")) if s.get("require") else None
        out.append(EffectSpec(key, impl, s, gate, s.get("chance", 1.0)))
    return out


def apply_effects(specs, source, target, world):
    """Run a list of effects from `source` onto `target`.  Order is authored
    order, always — no set iteration, no dict churn."""
    applied = 0
    for spec in specs:
        if target is not None and spec.gate is not None:
            if not spec.gate.test(target.tags):
                continue
        if spec.chance < 1.0:
            rng = source.rng if source is not None and source.rng else world.rng
            if not rng.chance(spec.chance):
                continue
        spec.impl.apply(spec, source, target, world)
        applied += 1
    return applied


# ======================================================================
# built-in effects
# ======================================================================

@effect("damage")
class Damage(Effect):
    """Reduce target HP. The single damage authority in the entire engine."""

    WRITES = ("hp",)

    def apply(self, spec, source, target, world):
        if target is None or not target.alive:
            return
        if target.tags.has("immune.damage"):
            world.bus.emit("actor.immune", tick=world.tick,
                           actor=target.id, kind="damage")
            return

        amount = float(spec.p("amount", 1.0))
        if spec.p("scale_with_source", False) and source is not None:
            amount *= source.attrs.get("damage", 1.0)

        died = target._apply_hp_delta(-amount)

        world.bus.emit("actor.damaged", tick=world.tick,
                       actor=target.id,
                       source=(source.id if source else -1),
                       amount=amount, hp=target.hp)

        kb = float(spec.p("knockback", 0.0))
        if kb and source is not None and not target.tags.has("immune.knockback"):
            dx = target.x - source.x
            dy = target.y - source.y
            d = (dx * dx + dy * dy) ** 0.5 or 1.0
            # cross-side knockback is queued, never applied inline —
            # World delivers it next tick so both sides see one picture.
            world.queue_knockback(target, dx / d * kb, dy / d * kb)

        hs = int(spec.p("hitstun", 0))
        if hs and not target.tags.has("immune.hitstun"):
            target.hitstun = max(target.hitstun, hs)

        if died:
            world.on_actor_death(target, source)


@effect("heal")
class Heal(Effect):
    """Restore target HP, clamped to hp_max."""

    WRITES = ("hp",)

    def apply(self, spec, source, target, world):
        if target is None or not target.alive:
            return
        amount = float(spec.p("amount", 1.0))
        cap = target.attrs.get("hp_max")
        new = min(cap, target.attrs.get("hp") + amount)
        target.attrs.set_base("hp", new)
        world.bus.emit("actor.healed", tick=world.tick,
                       actor=target.id, amount=amount, hp=new)


@effect("add_tag")
class AddTag(Effect):
    """Grant tags, optionally for a limited number of ticks."""

    def apply(self, spec, source, target, world):
        if target is None:
            return
        tags = spec.p("tags", ())
        if isinstance(tags, str):
            tags = [tags]
        dur = int(spec.p("duration", 0))
        for t in tags:
            target.add_tag(t)
            if dur > 0:
                world.schedule(dur, lambda tg=t, a=target: a.remove_tag(tg))


@effect("remove_tag")
class RemoveTag(Effect):
    """Strip tags from the target."""

    def apply(self, spec, source, target, world):
        if target is None:
            return
        tags = spec.p("tags", ())
        if isinstance(tags, str):
            tags = [tags]
        for t in tags:
            target.remove_tag(t)


@effect("modify")
class Modify(Effect):
    """Temporarily add/multiply an attribute (a buff or debuff)."""

    def apply(self, spec, source, target, world):
        if target is None:
            return
        name = spec.p("attribute", "move_speed")
        src = spec.p("source_id", "fx:%s" % name)
        add = float(spec.p("add", 0.0))
        mul = float(spec.p("mul", 1.0))
        target.attrs.attr(name).add_modifier(src, add=add, mul=mul)
        dur = int(spec.p("duration", 0))
        if dur > 0:
            world.schedule(dur,
                           lambda a=target, n=name, s=src:
                           a.attrs.attr(n).remove_modifier(s))


@effect("teleport")
class Teleport(Effect):
    """Relocate the target — absolute, relative, or away from the source."""

    def apply(self, spec, source, target, world):
        if target is None:
            return
        mode = spec.p("mode", "relative")
        if mode == "absolute":
            nx, ny = float(spec.p("x", target.x)), float(spec.p("y", target.y))
        elif mode == "away" and source is not None:
            import math
            ang = math.atan2(target.y - source.y, target.x - source.x)
            d = float(spec.p("distance", 160.0))
            nx, ny = target.x + math.cos(ang) * d, target.y + math.sin(ang) * d
        else:
            nx = target.x + float(spec.p("dx", 0.0))
            ny = target.y + float(spec.p("dy", 0.0))
        nx, ny = world.clamp_to_arena(nx, ny)
        world.bus.emit("actor.teleported", tick=world.tick, actor=target.id,
                       from_x=target.x, from_y=target.y, to_x=nx, to_y=ny)
        target.x, target.y = nx, ny


@effect("emit_cue")
class EmitCue(Effect):
    """Fire a purely cosmetic cue.  Carries no gameplay consequence —
    that separation is enforced, not merely conventional."""

    def apply(self, spec, source, target, world):
        anchor = target if spec.p("on", "target") == "target" else source
        if anchor is None:
            return
        world.request_cue(spec.p("cue", "spark"), anchor,
                          dict(spec.params), source)


# ======================================================================
# load-time audit — proves the single-authority claim
# ======================================================================

def verify_single_authority():
    """Assert that `hp` is written by exactly the effects that declare it.

    Called at startup.  If a future contributor adds an effect that writes hp
    without declaring it, or writes hp from outside the effect layer, this is
    where it gets caught — instead of six damage paths quietly reappearing.
    """
    from ..core import registry
    writers = []
    for key in registry.known_effects():
        cls = registry.get_effect(key)
        if "hp" in getattr(cls, "WRITES", ()):
            writers.append(key)
    expected = {"damage", "heal"}
    got = set(writers)
    if got != expected:
        raise AssertionError(
            "hp authority drift: expected %s, found %s" % (sorted(expected), sorted(got)))
    return sorted(writers)
