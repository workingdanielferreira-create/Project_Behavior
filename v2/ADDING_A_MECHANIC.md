# Adding a mechanic

In v1 this took seven files (`FX_GUIDE.md` §9): a constant block in
`config.py`, a class in `combat.py`, a slot on `Combatant`, a spawn trigger,
a drain in `CombatSystem`, a world list in `app.py`, and a draw block in
`_paint`.

In v2 it takes one file.

## 1. Write the ability

`pb2/sim/abilities/my_mechanic.py`:

```python
import math
from ..ability import Ability, SCORE_NEVER
from ..effects import build_effects, apply_effects
from ..motes import K_BULLET
from ...core.registry import ability


@ability("shockwave")
class Shockwave(Ability):
    """Expanding ring that damages everything it passes through."""

    DEFAULT_COOLDOWN = 180

    def score(self, inst, actor, world):
        # 0..1 desire.  Nothing else branches on this, so you cannot
        # break another ability by adding yours.
        n = len([f for f in world.enemies_of(actor)
                 if actor.distance_to(f) < inst.p("radius", 200)])
        return min(1.0, n / 2.0) if n else SCORE_NEVER

    def start(self, inst, actor, world):
        inst.state["fx"] = build_effects(inst.p("on_hit", [
            {"effect": "damage", "amount": inst.p("damage", 4.0),
             "knockback": 12.0}]))
        world.request_cue("ring", actor, {"scale": 2.5}, actor)

    def tick(self, inst, actor, world):
        r = inst.phase_t * float(inst.p("speed", 9.0))
        for foe in world.enemies_of(actor):
            if foe.id in inst.state.setdefault("hit", []):
                continue
            if abs(actor.distance_to(foe) - r) < 24.0:
                apply_effects(inst.state["fx"], actor, foe, world)
                inst.state["hit"].append(foe.id)

    def finish(self, inst, actor, world):
        inst.start_cooldown(inst.p("cooldown", self.DEFAULT_COOLDOWN),
                            actor.attrs.get("cooldown_rate", 1.0))
```

## 2. Register the module

`pb2/sim/abilities/__init__.py` — add one line:

```python
from . import library, my_mechanic          # noqa: F401
```

## 3. Use it from any character

```json
{ "key": "shockwave",
  "params": { "damage": 6, "speed": 11, "radius": 240,
              "phases": [["charge", 10], ["expand", 30]],
              "cooldown": 200 } }
```

## 4. Regenerate the schema and re-verify

```
python tools/gen_schema.py
python -m pb2.harness.golden verify
```

The schema picks the new ability up automatically — the contract is generated
from the registry, so it cannot drift from the code.

---

## Rules

* **Never write an attribute directly.** Emit an Effect. `hp` is written only
  by `damage` and `heal`, and `verify_single_authority()` asserts it at
  startup.
* **Never render from an ability.** Call `world.request_cue(...)`. Cues are
  cosmetic and can carry no gameplay consequence.
* **Never use `random`.** Use `actor.rng` or `world.rng`, which are seeded
  from the world. Anything else breaks the golden test.
* **Never iterate a `set` or an unordered `dict`** where the order affects
  outcomes — it makes replay non-reproducible. Use lists.
* **State belongs on the instance** (`inst.state`), not on the Actor. That is
  why `Actor` has ~20 slots where v1's `Combatant` had 85.
* Passive abilities implement `passive_tick(inst, actor, world)` and return
  `SCORE_NEVER` from `score`, so they run every tick without competing for
  the body.

## Adding an effect or a cue

Identical shape:

```python
@effect("burn")
class Burn(Effect):
    WRITES = ("hp",)      # declare every attribute you touch
    def apply(self, spec, source, target, world): ...
```

If you declare `WRITES = ("hp",)`, `verify_single_authority()` will fail on
next startup — deliberately. Damage has one authority; if you genuinely need
a second, that is a design decision to make explicitly, not by accident.
