"""Ability — the only unit of "a thing a character does".

Every mechanic v1 implemented as bespoke code in combat.py is, in v2, an
Ability: petals, blink, clones, vanish-cut, damage-teleport, attack patterns,
combos, ultimates.  There is no second category.

An ability has four hooks; all are optional except `score`:

    score(actor, world)    -> 0..1 desire this tick (the utility function)
    start(inst, actor, w)  -> called once when it wins and fires
    tick(inst, actor, w)   -> called each tick while active
    finish(inst, actor, w) -> called once when it ends

Phases give the multi-stage shapes v1 hand-rolled (windup / freeze / burst /
hold for Flash Cut).  Declared as data:

    "phases": [["windup", 12], ["strike", 6], ["recover", 18]]

Utility scoring is what makes abilities independent: adding one cannot break
another, because nothing branches on anything else.  That is the property
v1's 429-line, 70-branch FSM lacked.
"""

from ..core.tags import TagQuery

__all__ = ["Ability", "SCORE_NEVER", "SCORE_ALWAYS", "curve"]

SCORE_NEVER = 0.0
SCORE_ALWAYS = 1.0


def curve(x, kind="linear", exponent=2.0):
    """Response curves — the standard utility-AI shaping toolkit.

    Keeps authored scores readable: a designer says "closer is better,
    sharply" rather than writing maths in JSON.
    """
    x = 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
    if kind == "linear":
        return x
    if kind == "inverse":
        return 1.0 - x
    if kind == "quadratic":
        return x ** exponent
    if kind == "inverse_quadratic":
        return 1.0 - (x ** exponent)
    if kind == "step":
        return 1.0 if x >= 0.5 else 0.0
    if kind == "bell":
        return 1.0 - abs(x * 2.0 - 1.0)
    return x


class Ability:
    """Base class for every mechanic."""

    KEY = "?"
    #: tags applied to the actor for the duration of the ability
    BODY_TAGS = ("state.busy",)
    #: default cooldown in ticks if the character doesn't override it
    DEFAULT_COOLDOWN = 60

    # -- decision ---------------------------------------------------
    def score(self, inst, actor, world):
        """Return 0..1.  0 means "don't want it this tick"."""
        return SCORE_NEVER

    # -- execution --------------------------------------------------
    def start(self, inst, actor, world):
        pass

    def tick(self, inst, actor, world):
        pass

    def finish(self, inst, actor, world):
        pass

    # -- shared helpers used by many abilities ----------------------
    @staticmethod
    def target_of(actor, world):
        return world.target_for(actor)

    @staticmethod
    def range_score(actor, world, ideal, falloff=220.0, invert=False):
        """1.0 at `ideal` distance, decaying with |distance - ideal|."""
        t = Ability.target_of(actor, world)
        if t is None:
            return SCORE_NEVER
        d = actor.distance_to(t) if hasattr(t, "distance_to") else \
            ((t[0] - actor.x) ** 2 + (t[1] - actor.y) ** 2) ** 0.5
        err = abs(d - ideal) / max(1.0, falloff)
        s = 1.0 - min(1.0, err)
        return (1.0 - s) if invert else s

    @staticmethod
    def hp_score(actor, below=0.5, sharpness=2.0):
        """Rises as HP falls below the threshold — the standard 'panic' input."""
        f = actor.hp_frac
        if f >= below:
            return SCORE_NEVER
        return curve(1.0 - (f / max(0.01, below)), "quadratic", sharpness)


class PhaseRunner:
    """Drives an ability's declared phase list.  Shared by all abilities so
    multi-stage behaviour is authored, not coded."""

    @staticmethod
    def begin(inst):
        phases = inst.params.get("phases")
        if phases:
            inst.phase = phases[0][0]
            inst.phase_t = 0
            inst.state["_phase_i"] = 0
        else:
            inst.phase = "active"
            inst.phase_t = 0

    @staticmethod
    def advance(inst):
        """Returns True while still running, False when the last phase ends."""
        phases = inst.params.get("phases")
        inst.phase_t += 1
        if not phases:
            dur = int(inst.params.get("duration", 1))
            return inst.phase_t < dur
        i = inst.state.get("_phase_i", 0)
        name, dur = phases[i][0], int(phases[i][1])
        if inst.phase_t < dur:
            return True
        i += 1
        if i >= len(phases):
            return False
        inst.state["_phase_i"] = i
        inst.phase = phases[i][0]
        inst.phase_t = 0
        return True

    @staticmethod
    def phase_is(inst, name):
        return inst.phase == name


def make_gate(spec):
    """Build the tag gate for an ability from its JSON `require` block."""
    return TagQuery(spec.get("require")) if spec.get("require") else None
