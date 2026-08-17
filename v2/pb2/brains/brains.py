"""Brains — sources of Intent.

The whole player-control feature is this file plus core/intent.py.

Execution consumes an Intent and cannot tell which brain produced it.  That
guarantees AI/player parity by construction, the same way v1's single
pipeline guaranteed Solo/Battle parity: not by discipline, but because there
is only one path.

HYBRID control (the chosen model) falls out for free: the player brain fills
the MOVE channel, the AI brain fills the ABILITY channel, and neither knows
the other exists.  Channels are independent.
"""

import math

from ..core.intent import Intent, MOVE, ABILITY
from ..core.registry import brain

__all__ = ["Brain", "UtilityBrain", "PlayerBrain", "ScriptBrain"]


class Brain:
    """Base.  `think` writes into the shared Intent for this tick."""

    KEY = "?"
    #: channels this brain is permitted to write
    CHANNELS = (MOVE, ABILITY)

    def think(self, actor, world, intent):
        raise NotImplementedError

    def wants(self, channel):
        return channel in self.CHANNELS


@brain("utility")
class UtilityBrain(Brain):
    """Scores every owned ability and picks the best.

    This replaces v1's 429-line, 70-branch FSM.  Abilities do not know about
    each other and are not ordered relative to each other, so adding one
    cannot change how another behaves — the property the FSM lacked.
    """

    KEY = "utility"
    CHANNELS = (MOVE, ABILITY)

    def __init__(self, movement="kite", params=None):
        self.movement = movement
        self.params = params or {}
        self.last_scores = {}          # exposed to the cockpit for debugging

    # -- movement ----------------------------------------------------
    def _move(self, actor, world, intent):
        t = world.target_for(actor)
        if t is None:
            return
        tx, ty = world.position_of(t)
        dx, dy = tx - actor.x, ty - actor.y
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d

        style = self.movement
        if actor.tags.has("state.stationary"):
            return

        if style == "charge":
            mx, my = ux, uy
        elif style == "kite":
            ideal = float(self.params.get("ideal_range", 280.0))
            band = float(self.params.get("band", 60.0))
            if d < ideal - band:
                mx, my = -ux, -uy
            elif d > ideal + band:
                mx, my = ux, uy
            else:
                mx, my = -uy, ux          # strafe
        elif style == "orbit":
            lead = math.radians(float(self.params.get("orbit_lead_deg", 12.0)))
            a = math.atan2(dy, dx) + math.pi / 2 + lead
            mx, my = math.cos(a), math.sin(a)
        elif style == "retreat":
            mx, my = -ux, -uy
        else:
            mx, my = 0.0, 0.0

        # wander: v1's wander_blend, preserved
        wander = float(self.params.get("wander", 0.0))
        if wander > 0.0:
            blend = min(wander, d / 300.0) * wander
            a = actor.rng.uniform(0.0, math.tau)
            mx += math.cos(a) * blend
            my += math.sin(a) * blend

        m = math.hypot(mx, my) or 1.0
        intent.want_move(mx / m, my / m, source="utility")
        intent.want_face(math.atan2(dy, dx), source="utility")

    # -- ability selection -------------------------------------------
    def _choose(self, actor, world, intent):
        best_key, best_score = None, 0.0
        scores = {}
        for inst in actor.ordered_abilities():          # insertion order
            if inst.impl.BODY_TAGS and actor.busy:
                continue
            if not inst.ready():
                continue
            if inst.gate is not None and not inst.gate.test(actor.tags):
                continue
            if actor.tags.has("block.ability." + inst.key):
                continue
            try:
                s = float(inst.impl.score(inst, actor, world))
            except Exception:
                world.fault("score", inst.key, actor.id)
                continue
            s *= (1.0 + inst.priority)
            scores[inst.key] = s
            if s > best_score:
                best_key, best_score = inst.key, s
        self.last_scores = scores
        threshold = float(self.params.get("threshold", 0.12))
        if best_key and best_score >= threshold:
            intent.want_ability(best_key, best_score, source="utility")

    def think(self, actor, world, intent):
        if not intent.claimed(MOVE):
            self._move(actor, world, intent)
        if not intent.claimed(ABILITY):
            self._choose(actor, world, intent)


@brain("player")
class PlayerBrain(Brain):
    """Translates held input into Intent.

    In HYBRID mode this brain claims MOVE only, and the utility brain fills
    ABILITY — so you steer while the fighter defends and attacks itself.
    Switching to full manual is a one-line CHANNELS change, not a rewrite,
    because both brains speak the same contract.
    """

    KEY = "player"

    def __init__(self, pad=None, mode="hybrid"):
        self.pad = pad if pad is not None else Pad()
        self.mode = mode
        self.CHANNELS = (MOVE,) if mode == "hybrid" else (MOVE, ABILITY)

    def think(self, actor, world, intent):
        p = self.pad
        dx = (1.0 if p.right else 0.0) - (1.0 if p.left else 0.0)
        dy = (1.0 if p.down else 0.0) - (1.0 if p.up else 0.0)
        if dx or dy:
            m = math.hypot(dx, dy) or 1.0
            intent.want_move(dx / m, dy / m, source="player")
            intent.want_face(math.atan2(dy, dx), source="player")
        elif self.mode == "hybrid":
            # No input this tick: yield MOVE back so the AI keeps manoeuvring
            # instead of the fighter standing still.  This is what makes
            # hybrid feel like co-driving rather than fighting the controls.
            return

        if ABILITY in self.CHANNELS:
            for key, pressed in p.ability_slots():
                if pressed:
                    intent.want_ability(key, 999.0, source="player")
                    break


class Pad:
    """Plain held-state container.  The Qt layer writes it; the sim reads it.

    Deliberately Qt-free so the simulation can be driven from a recorded
    input tape in tests exactly as it is from a keyboard.
    """

    __slots__ = ("up", "down", "left", "right", "slots")

    def __init__(self):
        self.up = self.down = self.left = self.right = False
        self.slots = {}          # ability_key -> bool

    def ability_slots(self):
        return sorted(self.slots.items())      # deterministic order

    def set_move(self, up=False, down=False, left=False, right=False):
        self.up, self.down, self.left, self.right = up, down, left, right

    def press(self, key, down=True):
        self.slots[key] = bool(down)

    def clear(self):
        self.up = self.down = self.left = self.right = False
        self.slots.clear()

    def encode(self):
        """Compact form for the input tape."""
        bits = (int(self.up) | int(self.down) << 1 |
                int(self.left) << 2 | int(self.right) << 3)
        return (bits, tuple(k for k, v in sorted(self.slots.items()) if v))

    def decode(self, rec):
        bits, keys = rec
        self.up = bool(bits & 1)
        self.down = bool(bits & 2)
        self.left = bool(bits & 4)
        self.right = bool(bits & 8)
        self.slots = {k: True for k in keys}


@brain("script")
class ScriptBrain(Brain):
    """Replays a fixed intent sequence.  Used by the golden tests to drive
    deterministic scenarios without a keyboard."""

    KEY = "script"

    def __init__(self, steps):
        self.steps = list(steps)
        self.i = 0

    def think(self, actor, world, intent):
        if self.i >= len(self.steps):
            return
        step = self.steps[self.i]
        self.i += 1
        if "move" in step:
            intent.want_move(step["move"][0], step["move"][1], source="script")
        if "ability" in step:
            intent.want_ability(step["ability"], 999.0, source="script")
