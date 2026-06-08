# laser_cursor — Architecture

A PyQt5 fullscreen transparent overlay of animated neon companions that chase,
flee, follow, shoot, and sword-fight (across two instances). This document is
the map: how the pieces fit, where to add things, and the staged rebuild plan.

## Why it was restructured

The previous build was two ~700-line god-objects (`RunnerSprite`, `Overlay`) and
behaviour gated by `if behavior_mode == 1` checks scattered across ~10 sites.
Every new feature meant surgery across unrelated concerns, and adding a third
figure type meant hunting every `== 1`. Three ideas fix that.

## The three pillars

### 1. Components (composition over a 90-attribute blob)
A `Figure` is a thin container of focused components, each owning one concern and
(if visual) drawing itself:

| Component        | Owns                                             |
|------------------|--------------------------------------------------|
| `Transform`      | position, facing, rotation, init flag            |
| `MotionState`    | speeds, bounce/path/runaway state                |
| `TrailComponent` | the neon trail (its deque + draw)                |
| `Renderable`     | sprite frames + animation cursor                 |
| `Combatant`      | dash/slash/dodge/combo/crescent state            |
| `Personality`    | per-figure RNG + battle temperament              |

A localized feature ("make the trail fade faster") touches one component.

### 2. Mode registry (polymorphism, not `== 1`)
Each figure type is a `FigureMode` singleton registered by key. Systems query
predicates instead of branching on an int:
`mode.can_shoot()`, `mode.uses_melee()`, `mode.retreats()`, `mode.charges_full()`,
`mode.wander_blend(dist, strength)`.

**Add a figure type** (e.g. an archer):
1. `@register class ArcherMode(FigureMode): key="archer"` + override predicates
2. add `"archer": dict(chase_speed=..., ...)` to `config.MODE_CONFIGS`,
   and `"archer"` to `config.MODE_ORDER`
3. drop `archer*.png` next to the launcher and load it in `AssetLibrary`

No edits to motion, combat, collision, AI, or input. They already route through
the predicates.

### 3. Systems pipeline (ordered, swappable)
The old 340-line `_tick` is now an ordered list of `System` objects, each doing
one job over the whole `World`:

```
InputSystem -> CombatSystem -> MotionSystem -> CollisionSystem
            -> ProjectileSystem -> IpcSystem
```

**Add a cross-cutting feature** that "many components must consider" (e.g. a
freeze field, status effects, screen shake): write one `System`, insert it into
`build_pipeline()`. Every entity flows through it automatically. Combat runs
before motion so a mid-attack figure moves there and `MotionSystem` skips it
(`fig.combat.busy`).

Rendering is intentionally *not* a system — Qt requires painting inside
`paintEvent` — but each component still draws itself, so render stays declarative.

## File map

```
laser_cursor.pyw     thin launcher (portable double-click); fixes sys.path
laser/
  config.py          ALL tunables, grouped; per-mode dicts in MODE_CONFIGS
  platform_win.py    Win32 key polling / priority (guarded; no-op off-Windows)
  palette.py         neon palettes -> precomputed 256-entry LUTs
  geometry.py        dist / normalise / reflect / arc-angle helpers
  assets.py          bg removal, scaling, FrameBundle, AssetLibrary
  components.py      Transform / MotionState / TrailComponent / Renderable /
                     Combatant / Personality
  figure.py          Figure entity: composes components + mode; facing + draw
  modes.py           FigureMode base + @register + RunnerMode / SwordsmanMode
  motion.py          chase / follow-path / runaway / cursor-bounce + walls
  combat.py          Projectile / CrescentWave / make_shot (+ slash FSM stage 2)
  ipc.py             shared-memory bridge; layout derived from struct strides
  ai.py              battle targeting / wander / daze / retreat (stage 3)
  systems.py         System base + the pipeline
  app.py             World (state + factory) + Overlay (window, loop, paint)
```

Dependency direction is one-way: `config`/`geometry`/`palette` depend on
nothing; components/entities depend on those; systems depend on entities;
`app` wires it all. No cycles.

## One tick

1. `Overlay._tick` reads the cursor into `world.cursor`.
2. Each system in the pipeline runs in order, reading/mutating `world`.
3. `world.global_tick += 1`, then `self.update()` requests a repaint.
4. `paintEvent` draws every figure (trail + sprite + crescents), then
   projectiles, then enemy projectiles.

`World` is the single source of shared state and the only place figures are
created (`add_figure`) or retuned for a mode (`cycle_mode` → `figure.set_mode`).

## Staged rebuild

All stages complete. Each was validated with `ast.parse` + a headless import
and logic smoke test before delivery.

- **Stage 0 — foundation + movement:** full skeleton; chase, follow, runaway,
  cursor-collision, trail, multi-figure, add/remove, mode cycling.
- **Stage 1 — shooting:** `ProjectileSystem` non-battle cadence; shooters fire
  formations at the cursor, gated by `mode.can_shoot()`.
- **Stage 2 — swordsman combat:** `combat.advance_combat` dash/rebound/slash/
  combo FSM driving `CombatSystem`; crescent emitted on hit, aimed at the struck
  target; gated by `mode.uses_melee()`. The dash-trigger tick still takes one
  normal step (faithful) via the `Combatant.acted` signal.
- **Stage 3 — battle/IPC + AI:** `IpcSystem` (heartbeat + share/read), `ai.py`
  (battle target with wander/daze/retreat + cubic wall repulsion, and growing-
  knockback hit physics), per-figure battle firing, and `CollisionSystem`
  (crescent bullet-erasure, projectile hits, dodge/counter triggers, body
  collisions) — which activate the dodge code ported in stage 2.

### Adding the next feature
A new figure type is a `FigureMode` subclass + a `MODE_CONFIGS` entry + sprites
(see "Mode registry" above) — every system already routes through the
predicates. A new cross-cutting mechanic is a new `System` in `build_pipeline()`.
A localized tweak is one edit to the relevant component.

## Performance notes

- LUTs precomputed once; the draw hot path only indexes + masks.
- Trail/crescent draws reuse a single `QPen`; no per-segment allocation beyond
  the unavoidable `QColor`.
- `__slots__` on every component and entity for memory + attribute-access speed.
- `remove_background` is a per-pixel Python loop but runs once at load only.
- Systems iterate each entity list once per tick; no hidden O(n²) except the
  intentional figure↔projectile checks (bounded by 8 figures × 16 projectiles).
