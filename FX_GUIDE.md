# Project Behavior — Visual Effects (FX) Framework Guide

This is the reference manual for how visual effects work in Project Behavior:
slashes, bullets, ultimates, afterimages, sparks, rings, flashes — and how to
build your own. Everything here reflects the actual code in `laser/` as of
July 2026.

---

## 1. The Big Picture

The game runs a fixed tick loop (~62 fps). Every tick:

1. **Systems pipeline** runs in strict order:
   `Input → IPC → Combat → Motion → Collision → Projectile`
   (built in `systems.py :: build_pipeline()`).
   Systems mutate state — they never draw.
2. **`paintEvent`** (`app.py :: Overlay._paint`) draws everything using
   QPainter. Paint reads state — with one deliberate exception (§5), it never
   changes game logic.

Solo and Battle run **the same pipeline**. Battle is two OS processes talking
through shared memory (`ipc.py`). This means every effect you build works in
both modes automatically **unless** the *opponent's process* needs to see it —
then it needs an IPC channel (§7).

---

## 2. The Four FX Patterns

Every effect in the game follows one of four patterns. When you invent an
effect, your first decision is which pattern it belongs to.

### Pattern A — Self-drawing effect object (the workhorse)
A class with three methods:

```python
class MyEffect:
    def __init__(self, ...):   # capture spawn position/target/colour
    def update(self):          # advance one tick (move, age)
    def alive(self) -> bool    # False = remove me
    def draw(self, p):         # QPainter rendering
```

Existing examples in `combat.py`:
- `Projectile` (line ~210) — round bullet with trail
- `ZigzagProjectile`, `HomingProjectile` — subclasses overriding `update()`
  only, inheriting draw. **Subclassing = new behaviour, same look.**
- `CrescentWave` (~539) — normal slash arc
- `UltimateCrescent` (~633) — X-blade ult, with its own hit tests
  (`check_bullet_erase`, `check_figure_hit`)

Use Pattern A when the effect has: its own position, its own lifetime, its own
geometry, and possibly gameplay interaction (hit tests).

**Where they live and get ticked:**
- Projectiles → `world.projectiles`, ticked by `ProjectileSystem`, drawn in
  `app._paint` (`proj.draw(p)`).
- Crescents / ult crescents → per-figure lists `fig.combat.crescents` /
  `fig.combat.ult_crescents`, ticked in `combat.py` (`advance_combat`,
  `tick_ult_crescents`), drawn inside `figure.py :: Figure.draw` (~148–159).

### Pattern B — World particle lists (cheap eye-candy)
Dumb Python lists of plain values, no class. Declared in `app.py` (~95–103):

```python
self.collision_dots = []   # [x, y, age]
self.impact_rings  = []    # [x, y, age, max_radius]
self.muzzle_flashes = []   # [x, y, age, r, g, b]
self.sparks        = []    # [x, y, vx, vy, age, r, g, b]
```

They are **spawned** by systems (`CombatSystem` ~192–207,
`_spawn_bullet_burst` ~25) and **drawn + aged + culled inside `_paint`**
(rings ~329, sparks ~352, flashes ~377). Cheapest possible pattern. Use for
short-lived, purely visual bursts with no gameplay meaning.

### Pattern C — Per-figure combat state
FX tied to a specific figure's state, stored on its `Combatant` component
(`components.py :: Combatant`, ~184). Example: **dash afterimages** —
`c.afterimages` is a list of `[x, y, frame, age]`, spawned by
`combat.py :: spawn_afterimage` (~160) at `AFTERIMAGE_INTERVAL` during dashes,
drawn *behind the figure* in `figure.py :: Figure.draw` (~119–135).

Use when the effect follows one figure's behaviour (dashing, parrying,
charging).

⚠️ `Combatant` uses `__slots__` (~209). **Any new field you add must also be
added to the `__slots__` tuple** or Python raises `AttributeError` at runtime.

### Pattern D — Pre-rendered sprite caches
Expensive gradients rendered **once** into a `QPixmap`, then blitted every
frame. `combat.py`:
- `bullet_sprite(r, g, b, radius)` (~38) — round glow bullet
- `bolt_sprite(r, g, b, radius, stretch, hot=False)` (~89) — stretched bolt

Both are `lru_cache`-style keyed by their arguments. **Restriction:** a cached
sprite cannot animate its internal appearance per-frame — every visual variant
needs its own cache key (that's exactly what the `hot` flag does for the
zigzag white-hot core). If you need per-frame shape animation, draw live with
QPainter instead (like crescents do) and accept the cost.

---

## 3. Draw Order (what covers what)

`app._paint` draws in this order — later = on top:

1. `fig.draw(...)` per figure, which internally draws:
   afterimages (bottom) → figure sprite → crescents → ult crescents
2. Own projectiles (`world.projectiles`)
3. Enemy projectiles from IPC (`world.enemy_projs`, sprite blits)
4. Collision dots
5. Impact shockwave rings
6. Sparks
7. Muzzle flashes
8. HP text (topmost)

If your new effect must appear above/below something specific, its insertion
point in `_paint` (or in `Figure.draw`) *is* its z-order. There is no z-index
system — order of code is order of layers.

---

## 4. Timing & the Tick Contract

- Everything is measured in **ticks** (~62/sec, ~16 ms each).
  Lifetime 12 ticks ≈ 0.19 s. Speed 4 px/tick ≈ 250 px/s.
- Effects age in exactly one place. Pattern A objects age in `update()`;
  Pattern B lists age inside `_paint` (see §5 for why).
- Every effect needs a **hard cap or cull** — the game runs indefinitely:
  - afterimages capped at `AFTERIMAGE_MAX = 12`
  - shared bullets capped at 160 IPC slots
  - projectiles culled off-screen (`Projectile.alive`)
  - `UltimateCrescent` has `ULTC_LIFETIME = 600` as a safety cap
  A new effect without a cap/cull is a slow memory leak and FPS drain.

---

## 5. Hitstop — the one paint/logic exception

Big hits (slash finisher, sword ultimate launch) set
`c.hitstop_request = True`. `CombatSystem` (~211) converts that into
`world.hitstop_ticks = HITSTOP_TICKS` (5 ≈ 80 ms) and broadcasts it over IPC
so **both processes freeze in the same frame**.

While `hitstop_ticks > 0`, the systems pipeline is skipped — **but Pattern B
FX keep animating**, because they are aged inside `_paint`, not in a system.
This is intentional (`app.py` ~247: "FX keep animating in paint for punch").

Design lever for you:
- Effect should **freeze** during hitstop → tick it in a system / `update()`.
- Effect should **stay alive** during hitstop (sparks flying while the world
  is frozen) → age it in `_paint` like rings/sparks/flashes.

To make your own effect *trigger* a freeze: set
`fig.combat.hitstop_request = True` at the moment of impact — everything else
is already wired.

---

## 6. Config Constants — the tuning surface

Every effect exposes its numbers in `config.py`, grouped in blocks. The main
FX blocks:

| Block | Constants (examples) |
|---|---|
| Figure trail | `TRAIL_LEN`, `TRAIL_FLOW_SPD`, `TRAIL_W_HEAD` … |
| Slash crescent | `CRESCENT_SPEED/LIFETIME/RADIUS/SPAN/WIDTH/TAIL/SEGS` |
| Sword ultimate | `ULTC_THRESHOLDS/RADIUS/SPAN/SPEED/FADE_DIST/WIDTH_*/CROSS_ANGLE` … |
| Afterimages | `AFTERIMAGE_INTERVAL/LIFETIME/ALPHA/RGB/MAX` |
| Hitstop | `HITSTOP_TICKS` |
| Impact FX | `IMPACT_SPARK_COUNT/SPEED/LIFETIME`, ring constants |
| Bullets | `PROJ_TRAIL_LEN`, `BOLT_STRETCH_*`, `MUZZLE_FLASH_*`, `BULLET_BURST_*` |
| Runner ultimate | `ULTIMATE_HP_THRESHOLD/DURATION_TICKS`, `BEAM_ROWS/ROW_SPACING` |

**Rule:** never hard-code a magic number inside an effect. Add a named
constant with a comment stating its unit (px, ticks, degrees, fraction).
That's what makes effects tunable later without re-reading the code.

**Rule:** when you change a timing/frequency constant, audit its associated
values in the same change (e.g. raising `CRESCENT_SPEED` may require
re-checking `CRESCENT_LIFETIME` so travel distance stays sane).

---

## 7. The IPC Boundary — the hard restriction

Battle mode = two processes. Shared memory (`ipc.py`) carries **only**:

| Channel | Fields | Notes |
|---|---|---|
| Figures | x, y, alive, dashing, parrying | per figure |
| Projectiles | x, y, vx, vy, r, g, b, alive | **160 slots**, fixed struct |
| Knockback | vx, vy, pending | one slot per side |
| Hitstop | pending flag | world-freeze broadcast |
| Heartbeat | timestamp | liveness |

Consequences:

- **Bullets sync** — the opponent renders your bullets from the 7-field
  struct using the shared round sprite. Fancy per-bullet visuals (zigzag core,
  homing halo, phase flair) only render on the *owning* side; the partner sees
  the plain round sprite. If a new bullet look must be visible to the
  opponent, the struct format (`_PROJ_FMT`) must gain a field — a breaking
  change to the byte layout on **both** sides simultaneously.
- **Crescents / ult crescents do NOT sync** (noted in `systems.py` ~727–732:
  enemy ult crescents are not yet in IPC). The opponent cannot see or be
  hit-tested against your arcs from their process; hits are resolved on the
  owner's side and communicated as knockback/HP effects.
- **Pure eye-candy never needs IPC.** Sparks, rings, flashes, afterimages are
  local — each process spawns its own from the events it observes. This is
  the cheapest, safest category: build here first.
- The IPC byte layout is declared once at the top of `ipc.py` from struct
  strides. Any layout change: bump/verify both processes together, never one
  side.

**Decision test for any new effect:** "Does the *other process* need to react
to or render this differently from what it can already infer from figure
positions and the bullet stream?" If no → local FX, zero IPC work.

---

## 8. Performance Rules (learned the hard way)

1. **Never create fonts, gradients, or pixmaps inside `_paint`** — build once
   at init or cache (font creation was explicitly moved out of the paint
   loop; sprites are cached).
2. **Blit > stroke > gradient stroke.** Prefer cached pixmap blits; live
   gradient strokes (crescents) are the expensive tier — note they use `SEGS`
   segment counts as a quality/cost dial.
3. **Fade with `p.setOpacity()`**, not by rebuilding coloured sprites
   (`app.py` ~33 documents this).
4. **Cull early**: off-screen bullets die (`Projectile.alive`), dead entries
   are filtered every frame with `live = [...]` rebuild — copy that idiom.
5. **Cap counts** (§4). The 160-bullet IPC cap is also your effective
   worst-case draw budget for bullets.

---

## 9. How to Add a New Effect — the recipe

1. **Pick the pattern** (§2). Eye-candy burst → B. Travelling entity with
   geometry/hits → A. Follows one figure's state → C. Needs a new look for a
   fast repeated shape → D (sprite cache).
2. **Add config constants** with units in comments.
3. **State**: add the list/field — world list in `app.py __init__`
   (Pattern B), or Combatant field **plus `__slots__` entry** (Pattern C), or
   a class in `combat.py` (Pattern A).
4. **Spawn**: set it at the gameplay moment. If the moment is detected inside
   per-figure combat code but the FX is world-level, use the *pending queue*
   idiom: combat code appends to `c.something_pending`, `CombatSystem` drains
   it into world lists (exactly how `impact_fx_pending` → rings + sparks
   works, `systems.py` ~192–207).
5. **Tick**: in a system / owner's `update()` (freezes with hitstop) or in
   `_paint` (survives hitstop) — choose deliberately (§5).
6. **Draw**: insert at the right layer (§3).
7. **Cull/cap** (§4).
8. **Both modes**: if all spawn sites are in shared pipeline code, Solo and
   Battle get it automatically. Verify the trigger isn't inside a
   `if battle:` branch.
9. **Validate**: `ast.parse` + `py_compile` before pushing.

---

## 10. Worked Example — "Parry Nova"

Goal: when a figure triggers a parry, an expanding cyan double-ring bursts
outward from the figure with a small spark spray. Pure eye-candy → local
(no IPC), identical in Solo and Battle because `trigger_parry` is shared code.
We use the pending-queue idiom (Pattern C trigger → Pattern B render), plus
one Pattern A element (a small self-drawing class) to show both styles.

### Step 1 — Constants (`config.py`, new block near the impact-FX block)

```python
# ---------------------------------------------------------------------------
# Parry Nova (visual burst when a parry triggers)
# ---------------------------------------------------------------------------
PARRY_NOVA_LIFETIME   = 16          # ticks the rings take to expand + fade
PARRY_NOVA_RADIUS     = 55.0        # px outer ring radius at full bloom
PARRY_NOVA_RING_GAP   = 12.0        # px between the two rings
PARRY_NOVA_WIDTH      = 3.0         # stroke width at spawn (thins as it fades)
PARRY_NOVA_RGB        = (80, 220, 255)   # cyan
PARRY_NOVA_SPARKS     = 5           # sparks per nova (reuses world.sparks)
PARRY_NOVA_SPARK_SPD  = (3.0, 6.0)  # px/tick launch speed range
```

### Step 2 — Effect class (`combat.py`, near CrescentWave)

```python
class ParryNova:
    """Expanding cyan double-ring spawned when a parry triggers.

    Pure visual — no hit tests, no IPC. Ages in its own update() so it
    freezes during hitstop like other combat-owned FX.
    """

    __slots__ = ("x", "y", "age")

    def __init__(self, x, y):
        self.x, self.y = float(x), float(y)
        self.age = 0

    def update(self):
        self.age += 1

    def alive(self):
        return self.age < config.PARRY_NOVA_LIFETIME

    def draw(self, p):
        t = self.age / config.PARRY_NOVA_LIFETIME          # 0..1
        alpha = int(230 * (1.0 - t))
        if alpha <= 0:
            return
        r, g, b = config.PARRY_NOVA_RGB
        width = max(1.0, config.PARRY_NOVA_WIDTH * (1.0 - t))
        pen = QPen(QColor(r, g, b, alpha))
        pen.setWidthF(width)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        outer = config.PARRY_NOVA_RADIUS * t
        for rad in (outer, max(0.0, outer - config.PARRY_NOVA_RING_GAP)):
            ir = int(rad)
            if ir > 0:
                p.drawEllipse(int(self.x) - ir, int(self.y) - ir,
                              ir * 2, ir * 2)
```

### Step 3 — Pending flag on the Combatant (`components.py`)

Add `"parry_nova_pending"` to the `Combatant.__slots__` tuple (~209) — this
is mandatory — and initialise it in `__init__`:

```python
self.parry_nova_pending = False    # set by trigger_parry; drained by CombatSystem
```

### Step 4 — Spawn trigger (`combat.py :: trigger_parry`, ~842)

At the point the parry actually activates, add:

```python
c.parry_nova_pending = True
```

Because `trigger_parry` is shared combat code, Solo and Battle both fire it —
no divergence.

### Step 5 — Drain into the world (`systems.py :: CombatSystem.update`)

Right beside the existing `impact_fx_pending` drain (~194), add:

```python
if c.parry_nova_pending:
    c.parry_nova_pending = False
    world.parry_novas.append(
        combat.ParryNova(fig.transform.x, fig.transform.y))
    for _ in range(config.PARRY_NOVA_SPARKS):
        ang = random.uniform(0.0, math.tau)
        spd = random.uniform(*config.PARRY_NOVA_SPARK_SPD)
        r, g, b = config.PARRY_NOVA_RGB
        world.sparks.append([fig.transform.x, fig.transform.y,
                             math.cos(ang) * spd, math.sin(ang) * spd,
                             0, r, g, b])
```

(Reusing `world.sparks` means the spark half of the effect inherits the
existing draw/age/cull code for free — zero new paint code for sparks.)

### Step 6 — World list + tick (`app.py`)

In `__init__` next to the other FX lists (~101):

```python
self.parry_novas = []               # ParryNova instances (parry burst rings)
```

Tick them where the world advances (novas are combat-owned FX, so tick them
in the normal tick path so they freeze under hitstop — e.g. in
`ProjectileSystem` alongside projectile updates, or a small loop in
`CombatSystem`):

```python
live = []
for nova in world.parry_novas:
    nova.update()
    if nova.alive():
        live.append(nova)
world.parry_novas = live
```

### Step 7 — Draw (`app.py :: _paint`)

Insert **after** the figures and projectiles but **before** the impact rings,
so novas sit under the white slash-impact FX:

```python
for nova in w.parry_novas:
    nova.draw(p)
```

### Step 8 — Validate & push

`ast.parse()` + `py_compile` on `combat.py`, `components.py`, `systems.py`,
`app.py`, `config.py`; fetch fresh SHAs; push.

That's the complete lifecycle: **constants → class → pending flag →
system drain → world list → tick → draw → cull**. Every effect in the game —
slashes, bullets, ultimates — is a variation of exactly this loop, just with
more geometry in `draw()` and, for gameplay-relevant effects, hit tests in
`update()`/collision.

---

## 11. Quick Reference — file responsibilities

| File | FX role |
|---|---|
| `config.py` | All tunable constants |
| `combat.py` | Effect classes, sprite caches, spawn helpers, per-figure FX logic |
| `components.py` | Combatant FX state fields (**`__slots__`!**) |
| `systems.py` | Ticking, pending-queue drains, gameplay triggers, bullet bursts |
| `figure.py` | Figure-attached drawing: afterimages, crescents, ult crescents |
| `app.py` | World FX lists, draw order, paint-time aging (hitstop-immune FX) |
| `ipc.py` | The only cross-process channel; fixed struct layout, 160 bullet slots |
