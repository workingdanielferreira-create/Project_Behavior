"""Intent — the one contract between deciding and doing.

This module is the whole reason player control is possible in v2 and was not
in v1.  In v1, deciding and doing were fused inside a 429-line FSM, so there
was nowhere for a player to inject a decision.

In v2 every brain — AI or player — produces an Intent, and execution consumes
an Intent.  Execution cannot tell which kind of brain produced it, which
guarantees AI/player parity the same way v1's single pipeline guaranteed
Solo/Battle parity.

Channels are independent, which is what makes HYBRID control work:
the player brain may fill `move` while the AI brain fills `ability`, and
neither knows about the other.
"""

__all__ = ["Intent", "MOVE", "FACE", "ABILITY", "CHANNELS"]

MOVE = "move"        # (dx, dy) desired direction, magnitude 0..1
FACE = "face"        # desired facing in radians, or None to face movement
ABILITY = "ability"  # (key, score, params) the ability to attempt this tick

CHANNELS = (MOVE, FACE, ABILITY)


class Intent:
    """A tick's worth of desire.  Cheap: created fresh each tick per actor."""

    __slots__ = ("move_x", "move_y", "face", "ability_key",
                 "ability_score", "ability_params", "sources")

    def __init__(self):
        self.move_x = 0.0
        self.move_y = 0.0
        self.face = None
        self.ability_key = None
        self.ability_score = 0.0
        self.ability_params = None
        self.sources = {}      # channel -> brain name, for debug/cockpit

    # ---- channel writers ------------------------------------------
    def want_move(self, dx, dy, source="ai"):
        self.move_x = float(dx)
        self.move_y = float(dy)
        self.sources[MOVE] = source

    def want_face(self, radians, source="ai"):
        self.face = None if radians is None else float(radians)
        self.sources[FACE] = source

    def want_ability(self, key, score=1.0, params=None, source="ai"):
        """Highest score wins.  Ties resolve to the first writer, so brain
        order in the actor's brain list is the tiebreak — deterministic."""
        if key is None:
            return
        if float(score) > self.ability_score:
            self.ability_key = key
            self.ability_score = float(score)
            self.ability_params = params
            self.sources[ABILITY] = source

    # ---- queries ---------------------------------------------------
    @property
    def has_move(self):
        return self.move_x != 0.0 or self.move_y != 0.0

    @property
    def move_magnitude(self):
        return (self.move_x * self.move_x + self.move_y * self.move_y) ** 0.5

    def normalized_move(self):
        m = self.move_magnitude
        if m <= 1e-9:
            return 0.0, 0.0
        if m <= 1.0:
            return self.move_x, self.move_y
        return self.move_x / m, self.move_y / m

    def claimed(self, channel):
        return channel in self.sources

    def clear(self):
        self.move_x = self.move_y = 0.0
        self.face = None
        self.ability_key = None
        self.ability_score = 0.0
        self.ability_params = None
        self.sources.clear()

    def __repr__(self):
        return "Intent(move=(%.2f,%.2f) ability=%s@%.2f src=%s)" % (
            self.move_x, self.move_y, self.ability_key,
            self.ability_score, self.sources)
