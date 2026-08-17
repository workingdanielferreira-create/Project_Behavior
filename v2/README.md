# Project Behavior V2

A self-contained rebuild living alongside v1. **Nothing outside `v2/` is touched** —
the v1 engine in `laser/` keeps running exactly as before.

> A transparent desktop overlay hosting fighters that think for themselves,
> any of which you can take control of — where a fighter is a data file and
> adding one costs no engine code.

---

## Quick start

```bat
run_v2.bat                      :: runner vs swordsman
run_v2.bat mage ronin           :: pick the roster
run_v2.bat mage ronin 4242      :: fixed seed (reproducible)
test_v2.bat                     :: determinism + goldens + scale bench
```

numpy is **optional**. It raises the FX budget; without it the engine runs
in a pure-Python fallback that produces *byte-identical* results, just with a
lower mote ceiling. Install with `python -m pip install numpy`.

**Controls** — `1`/`2` cycle each side's fighter · `3`/`4` possess that side
(hybrid: you steer, the AI keeps fighting) · `WASD`/arrows move when possessed ·
`P` pause · `Ctrl+Alt+Esc` quit.

---

## The model — five nouns

Everything in v2 decomposes into five things. There is no sixth.

| Noun | What it is | The rule it enforces |
|---|---|---|
| **Attributes** | every number (hp, speed, scale, damage) | only an Effect may write one |
| **Tags** | hierarchical labels (`state.airborne`, `immune.knockback`) | replaces *every* boolean flag |
| **Abilities** | the only unit of "a thing a character does" | adding one can't break another |
| **Effects** | the only thing that changes an attribute | **one damage authority** |
| **Cues** | cosmetic output only | can never carry gameplay |

V1 had six competing answers to *"how does this character deal damage?"*
(`attack_pattern.damage`, per-layer `battle.damage`, hardcoded combo damage,
ultimate playback, petal contact, cursor bounce) with nothing arbitrating.
In v2 the question has exactly one answer, and
`effects.verify_single_authority()` asserts it at startup.

---

## Layers

```
CONTENT     characters/*.json          validated loudly against a generated schema
   |
DECISION    AI brain  ||  player brain     both emit the same Intent
   |
SIMULATION  Actors (tens)  |  Motes (thousands, SoA)     fixed tick, Qt-free, pure
   |
PRESENTATION  Cues -> atlas -> drawPixmapFragments        reads state, writes nothing
   |
SHELL       PyQt5 transparent click-through overlay
```

**`pb2.core`, `pb2.sim`, `pb2.brains`, `pb2.content` and `pb2.harness` import
no Qt at all.** Only `pb2.render` and `pb2.app` do. That is what lets the whole
simulation run, test and checksum headless.

---

## The four priorities, answered

### 1. Scale — more fighters, more FX

Two tiers, split by population rather than by kind:

* **Actors** (tens) — Python objects with full ability machinery.
* **Motes** (thousands) — rows in parallel arrays. One vector op advances
  every bullet, spark and particle in the world. No per-mote Python call.

Rendering batches every mote into a **single `drawPixmapFragments` call**
against one procedurally-built atlas, instead of one `drawPixmap` per object.
Collision uses a uniform spatial grid instead of figures × projectiles.

Measured on this machine:

| Fighters | ms/tick | Peak motes | Headroom vs 16 ms |
|---:|---:|---:|---:|
| 2 | 0.25 | 24 | 63× |
| 8 | 1.56 | 609 | 10× |
| 16 | 4.41 | 912 | 3.6× |
| 32 | 11.23 | 1,714 | 1.4× |

Mote pool alone: **2,000 motes at 0.033 ms/tick** (481× headroom).

### 2. Schema ambiguity & dead fields

* Unknown keys are **rejected, not ignored** — dead fields can't accumulate.
* Validation names the exact JSON path and refuses to load.
* `schema/character.schema.json` is **generated from the live registry**
  (`tools/gen_schema.py`), so documentation cannot drift from code.
* Ported characters: **58 KB → 2.8 KB** (the duplicated `*_semantics` prose
  now lives once, in the schema).

### 3. Adding a mechanic

V1's `FX_GUIDE.md §9` recipe touched seven files. V2 has three decorators:

```python
@ability("my_thing")   class MyThing(Ability): score() / start() / tick()
@effect("my_effect")   class MyEffect(Effect): apply()
@cue("my_visual")      class MyVisual(Cue):    emit()
```

Drop a file in `pb2/sim/abilities/`, import it in that package's `__init__`,
and it is addressable from any character JSON. **No engine file changes.**

Ability selection is **utility scoring**, not a state machine: each ability
scores itself 0..1 each tick and the best one wins. Nothing branches on
anything else, so a new ability cannot alter an existing one — the property
v1's 429-line, 70-branch FSM lacked.

### 4. Silent failures & testing

* **Strict mode raises** with the original traceback chained. V1 swallowed
  every exception into a log file, so a typo produced no symptom at all.
* **Golden checksum replay.** Seed + input tape + fixed tick → replay → hash
  the world → compare. One assertion covers the entire simulation.

```
python -m pb2.harness.golden determinism   # same seed, 3 runs, same hash
python -m pb2.harness.golden verify        # no behaviour drifted
```

Goldens are **2.3 KB** for six scenarios, versus v1's 25 MB of committed
capture bundles.

---

## Player control — how it actually works

The whole feature is `core/intent.py` plus `brains/brains.py`.

Every brain — AI or player — produces an **Intent**. Execution consumes an
Intent and *cannot tell which kind of brain produced it*. So an AI-driven and
a player-driven fighter run the identical code path, and "the AI version
behaves differently" is not a possible bug.

Channels are independent, which is what makes **hybrid** work: the player
brain fills `MOVE`, the utility brain fills `ABILITY`, and neither knows the
other exists. Release a key and the AI resumes steering mid-stride.

This is the same trick that made Solo/Battle parity work in v1 (one pipeline,
no mode branching), applied to the control axis.

---

## Solo / Battle parity

Unchanged and still structural. `battle_mode` is **derived**, never set:

```python
return bool(self.sides[0].living() and self.sides[1].living())
```

The pipeline runs once per fielded side against a frozen snapshot of the
other. Cross-side knockback is queued and delivered next tick. The Battle-only
arena oval remains the single signed-off exception.

---

## The complexity ladder

One format serves a 10-line character and a 500-line one:

| Rung | You write | Cost |
|---|---|---|
| 0 — statline | attributes only | ~10 lines |
| 1 — composed | pick abilities from the library, tune params | ~60 lines |
| 2 — dressed | + custom cues / palette | ~200 lines |
| 3 — extended | + one capability plugin file | 1 .py + JSON |

A rung-3 mechanic is immediately available at rung 1 to **every** character.
The library compounds — the opposite of v1, where each mechanic stayed welded
to the character it was built for.

---

## Roster

All six ported and loading clean. Runner and Swordsman were **hardcoded
`FigureMode` classes in v1**; in v2 they are ordinary JSON, which is the
clearest proof the built-in/data distinction is gone.

| Character | Origin | Abilities |
|---|---|---|
| runner | v1 built-in → data | cone, zigzag, homing, survival_teleport, ultimate |
| swordsman | v1 built-in → data | string, parry, dash, ultimate |
| ronin | v1 JSON | melee_combo, evade, guard |
| mage | v1 JSON | projectile_volley, orbitals, threshold_summon, reactive_teleport, guard, ultimate |
| new_fighter | v1 JSON | beam_shot, orbitals, evade, guard, ultimate |
| jumper | v1 JSON | melee_combo, blink, evade, guard, ultimate |

Re-run the port any time:

```
python tools/migrate_v1.py ../characters characters
```

---

## Layout

```
v2/
  pb2/
    core/      tags, attributes, rng, intent, events, registry   (no deps)
    sim/       world, actor, motes, grid, scaling, effects,      (no Qt)
               ability, abilities/
    brains/    utility, player, script                           (no Qt)
    content/   loader (validate -> migrate -> resolve)           (no Qt)
    harness/   golden checksum tests, scale benchmark            (no Qt)
    render/    atlas + fragment batching, painter                 Qt
    app/       overlay shell, entry point                         Qt
  characters/  the six ported fighters
  schema/      generated JSON Schema
  tools/       migrate_v1.py, gen_schema.py
  run_v2.bat   test_v2.bat
```

---

## Known gaps

Called out honestly rather than left to be discovered:

* **Figures render as stick figures.** The rig/keyframe rasteriser and sprite
  loading from v1 are not ported; `render/painter.py::_paint_actors` is the
  single place that changes.
* **Cue plugins are inline**, not yet registered via `@cue` — the decorator
  and registry exist and are wired, the library is small.
* **The Cockpit is not ported.** `World.digest()` already emits exactly the
  per-tick state the cockpit bundle format wants.
* **Untested on Windows/Qt.** The simulation is fully verified headless; the
  render and overlay layers are compile-checked only, since PyQt5 isn't
  available in the build environment.
