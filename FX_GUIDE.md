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
| `clashfx.py` | Clash explosion library: 11 baselines + 8 pair clashes + `derive()` variations, `world.clash_fx` |
| `clash.py` | Clash interaction (world physics): categorises both sides' FX, detects contact, plays the pair rule from the world clash table |
| `swordfx.py` | Sword techniques: the hand-drawn renderer behind the FX Kit `technique` primitive |
| `weaponfx.py` | 2.5D signature weapons (20): `technique` styles drawn through a small 3D camera |

---

## 12. Clash Explosions (`laser/clashfx.py`)

The explosion library for the Clash interaction. Each explosion is a
self-drawing object (Pattern A) living in `world.clash_fx`, drawn and aged in
`_paint` like the Pattern B lists, so it keeps animating through hit-stop. It is
one list for the whole world, so Solo and Battle behave identically.

- **Spawn:** `clashfx.spawn(world, key, x, y, angle=deg, c1=rgb, c2=rgb, winner=0)`.
  `angle` points from side A (colour `c1`) to side B (`c2`). Each half of the
  explosion takes its side's colour, with a white-hot core where they meet.
- **Sustained clashes** (`beam_struggle`, `blade_lock`, `speed_duel`, `sword_duel`) hold until
  `fx.release(winner)` (or their `hold` ticks run out; `hold=-1` = until released).
- **Baselines:** `collision_nova`, `beam_struggle`, `overpower_blowout`, `beam_struggle_won`, `orb_split`,
  `kunai_storm`, `ricochet_rain`, `blade_lock`, `reiatsu_eruption`,
  `getsuga_cross`, `implosion_pop`, `storm_fork`, `speed_duel` (a sword fight too
  fast to see: speed streaks and clash flashes in bursts of strikes).
- **New variations:** `clashfx.derive("mega_nova", "collision_nova", name="Mega Nova", size=1.8, density=1.6)`.
  Shared tunables: `size`, `density`, `speed`, `life`, `hold`, `hot`, plus each
  baseline's own (see `BASES`).
- **Preview:** `F6` fires the next variation at the cursor (P1's colour vs P2's).
  `tools/fx/clash_gallery.html` plays all of them in a browser. FX Studio has
  approximate versions under the **Clash explosions** preset group.

---

## 12b. Sword Techniques (`laser/swordfx.py`)

Hand-drawn sword FX at the clash-explosion standard, used through the FX Kit
primitive `technique` (FX Studio presets: **Sword techniques**). `params.style`
picks one: `rising_slash`, `horizontal_sweep`, `diagonal_slash` (filled
crescents of light that swing round the anchor), `crescent_wave` (a travelling
slash beam with a dark core and flames), `blade_extension` (an energy blade
that charges, shoots out of the sword tip, holds and retracts; Blade pivot /
spin / sweep turn it round a point on its centre line and Blade slide moves it
along an axis while it is out),
`forward_thrust` (a lunge stab: a tapered spear of light drives out along the
aim, an air-pressure ring at full reach, then it snaps back) or
`overhead_slash` (a vertical chop from above the head down to the feet,
bulging forward; a one-cut row of `CUTS`).

- **Hooks in fxkit.py:** `spawn` → `swordfx.on_spawn` (fixes the frame and
  sets the hit window as `inst.life`); `tick_inst` keeps it alive until
  `swordfx.total_ticks` for the afterglow; `_hit_shape` → `swordfx.hit`;
  `resolve_hits` → `swordfx.on_hit` (the X flash on the target); `_DRAW` →
  `swordfx.draw`. `clash.py` treats a technique as a `crescent` body
  (`swordfx.clash_cat`), except the Ki Barrage (each ki shot a `sprite`), the
  Charged Blast (its orb an `orb`) and the Serious Punch (a `beam`); the other
  guns and power techniques never clash.
- **Determinism:** everything is a function of age + seed (`rng_for`), so
  `tools/fx/studio/swordfx.js` draws the same pixels. Change both together;
  `check_parity.py` covers the shared tables (`TECH_STYLES`,
  `TECH_STYLE_DEFAULTS`, `PARAM_DEFAULTS.technique`).
- **Colour:** palette mode uses the LUT's most vivid entry (`vivid`); solid /
  gradient use colour 1, with colour 2 darkened for the wave's core.

---

## 12c. Slash Combos, Ki Barrage and Impact Punch

More `technique` styles at the same hand-drawn standard (FX Studio presets:
**Sword techniques**, **Sword combos**, **Ki & strikes**).

- **Slash family = one renderer, a table of cuts.** `swordfx.CUTS` maps every
  slash style to a list of cuts `(deg, bend, cx, cy, scale, span_k, squash,
  t0)`: travel direction, which side the crescent bulges, where it is centred
  (in radii), size, span, a squash along the travel direction (< 1 = a flat
  swing round the body seen edge-on) and its start (in swing lengths). The
  three original slashes are one-cut entries and draw exactly as before.
  - `forward_sweep`: one flat cut from beside the fighter, round the front at
    full reach and back. Flat cuts hit everything between the fighter and the
    blade (the area the swing passes through), not just the blade line.
  - Combos: `combo_triple` (overhead diagonal, rising diagonal, wide
    finisher), `combo_cross` (two diagonals forming an X + a flare where they
    cross), `combo_flurry` (six quick cuts from every direction),
    `combo_launcher` (feet → mid → high rising launcher), `combo_backhand`
    (flat forehand, flat backhand, overhead chop). Each cut lands once
    (`inst.tq_cut`), so give a combo Pierce and Re-hit 1. A new combo is a new
    row in `CUTS` (both `swordfx.py` and `swordfx.js`) plus its
    `TECH_STYLES` / `TECH_STYLE_DEFAULTS` entry.
- **Ki barrage (`laser/strikefx.py`).** Rapid-fire ki blasts: one shot every
  Swing ticks for Hold ticks, from alternating sides of the anchor. Every shot
  rolls its own speed, spread angle (Span), curve, size (now and then a much
  bigger one), tint, range (Length) and blast kind from the seed. Shots launch
  from where the anchor was at their launch tick (`inst.tq_path`, appended by
  `swordfx.on_tick` from `tick_inst`). A shot that hits stops and detonates
  there (`inst.tq_ki`); the rest detonate at the end of their range. Blasts:
  white flash, fireball, shock ring, sparks; smoke (painted normally, under
  the light) piles up. Ki shots never clash as a blade (`body` → None): each
  one in flight is its own `sprite` clash body (`strikefx.shot_at`); a clash
  that cancels one stops just that shot (`inst.tq_ki`).
- **Intercept on technique orbs.** The Ki Barrage's ki orbs and the Charged
  Blast's orb are each their own auto-projectile tracker
  (`strikefx.track_shots`; the charged blast via `gunfx.track_step`): a
  tracked shot flies its recorded path (`inst.tq_kd`). On contact modes:
  block, deflect, destroy and **absorb** — an enemy projectile it out-knocks
  by more than `ABSORB_LEAD_KB` (300) is swallowed (no blast) and the shot grows `ABSORB_STEP` (5%)
  up to `ABSORB_MAX` (200%): drawn size, hit size, blast, damage and
  knockback (`inst.tq_grow`). Absorb is an On contact mode of every
  Intercept (FX Kit projectiles grow through `inst.ps`, `inst.ab_g`; guard
  ribbons too); a smaller lead (or none) is left to World Clash.
- **Impact punch (`laser/strikefx.py`).** Fist out over Swing ticks, held for
  Hold ticks, pulled back in 5. Hits along the arm; the impact stays where
  the fist landed (`inst.tq_imp`). A whiff bursts at 55 % size at full reach.
  Clashes along the arm. What it paints is the strike FX partitions below.
- **Strike FX partitions (`laser/hitfx.py`, Studio: `hitfx.js`).** The punch
  and every kick paint three parts, each set on its own — `off` or one of
  three looks: `ink` (anime limited animation: white shapes with ink
  outlines, redrawn on twos, focus lines), `energy` (light: white-hot cores,
  coloured pressure bursts, rays and air-friction sparks spilling forward,
  shock rings; additive) or `gritty` (physical: dust, refraction-like
  distortion rings, debris and sweat spray, hardly any glow). Defaults: all
  `ink`.
  - `fx_motion`: how the limb moved. `motion_smear` = smear frames — 3
    afterimages of the forearm / shin along its real path during the fast
    part only, gone on the contact frame (2D animators hold the smear up to
    the hit and drop it there). `motion_arcs` = thin broken wind strokes
    tracing the fist / foot's path, tapered at both ends, lingering 4 ticks.
    Plus the fist / foot and (kicks) the wind-up glint. No solid trail.
  - `fx_impact`: the hit at the contact point, laid along the limb's motion
    (kicks `HEAVY` x bigger). ink: jagged white burst with an ink outline and
    a coloured heart, breaking into shards, ink focus lines, a pressure disc
    across the blow. energy: hot core, pressure glows pushed forward, rays
    spilling through the target, impact star, shock ring + broken ring,
    sparks. gritty: brief flash, dust burst off the body, light / dark
    distortion rings, debris chips and sweat spray with gravity.
  - `fx_env`: push-off dust under the attacker's feet as the strike starts, a
    ground wave under the target's feet (`FEET_DROP` 30 px) per impact; the
    axe kick's crater (cracks, debris, wave), the rising kick's kick-up, the
    spinning kick's vortex (`spin_mode` `centered`).
  - Every part is a pure function of the instance, so `hitfx.js` draws the
    same calls (checked call-by-call against the game).
- **Strike hit options** (`strikefx.HIT_OPTION_STYLES`, shown in the Studio
  for those styles only):
  - *Hit-stop* + *Hit-stop ticks*: the world freezes (`World.hitstop_ticks`,
    both sides at once) when the punch lands, once per punch. Solo has no
    opponent, so it freezes as the whiff bursts.
  - *Knockback direction*: `aim` (as every FX hit), `tangent` (the way the
    fist moves at contact) or `custom` (*Knockback angle °* turned from the
    strike, clockwise, mirrored with the facing). Battle only — Solo deals no
    knockback.
  - *Impact frame*: `off`, `local` (inside *Impact frame radius px*) or
    `full` (the whole overlay): a white flash crossed by ink focus lines
    converging on the contact point, then the inverse, 2 ticks (held through
    any hit-stop).
  - *Screen shake* (`shake`, `shake_px`, `shake_ticks`): fires with the
    hit-stop (once per strike; Solo: as it whiffs) — `World.add_shake`; the
    scene shakes, easing out, the HUD stays; it keeps shaking through the
    hit-stop.
  - *Target squash* (`squash`, `squash_amt`, `squash_ticks`,
    `squash_flash`): the fighter hit squashes along the blow and stretches
    across it, springing back (`Figure.hit_squash`, held through the
    hit-stop), and flashes white. Battle (Solo has no one to hit); the Studio
    squashes its target marker.
  - Style defaults (picked in the Studio): punch hit-stop 3 + squash; kicks
    hit-stop 4-6, shake 4-9 px, squash.
- **Parameters reused:** see the `strikefx.py` docstring (e.g. ki: Radius =
  shot size, Thickness = blast size, Span = spread °, Length = range).
- **Parity:** `strikefx.js` is the Studio port; `check_parity.py` also
  compares `CUTS` and the strikefx constants. Same code path in Solo and
  Battle (FX Kit Player).
- **Kicks (`laser/kickfx.py`, Studio: `kickfx.js`, presets group "Kicks").**
  Every kick is a path of the foot: a 3-tick wind-up, the kick over Swing
  ticks, held for Hold ticks, faded over 6. It hits along the lower leg and
  paints the strike FX partitions above (impact `HEAVY` x the punch's size).
  Radius = foot, Thickness = how far the air strokes spread, Length = leg
  reach, Span = arc sweep °.
  - `roundhouse_kick`: an arc round the hip meeting the aim halfway at full
    speed; `kick_sweep` `high_low` / `low_high`.
  - `thrust_kick`: straight along the aim.
  - `axe_kick`: comes down onto the point Length along the aim at full
    speed, moving `axe_dir` `screen_down` / `along_aim` / `custom`
    (`kick_angle_deg` from the aim); the arc starts on the higher side. A
    crater, cracks along the ground, debris and a flat shock ring at
    `axe_crater` `contact` or `feet` (30 px under the target).
  - `spinning_kick`: `spin_turns` circles ending on the aim; `spin_mode`
    `centered` (wind vortex round the body), `travel` (drifts forward 1.2 x
    Length), `lunge` (the last 30 % lunges 0.6 x Length).
  - `rising_kick`: a launcher rising through the point 0.9 x Length along the
    aim and on past it, moving `rise_dir` `screen_up` / `perpendicular` /
    `straight_up` / `custom`; dust kicked up as it starts.
  - The punch's hit options apply (Hit-stop, Screen shake, Target squash,
    Knockback direction — tangent = the foot's motion at contact — and Impact
    frame). Style defaults set
    Knockback direction to `tangent` (`aim` for the thrust kick).
- **Gunfire (`laser/gunfx.py`, Studio: `gunfx.js`).** Ten anime gun shots,
  each a technique style with a palette preset and a signature-colour preset
  in the Studio's "Gunfire" group, and its own settings panel:
  `machine_gun` (tracer stream, brass casings), `shotgun` (nine-pellet
  volleys, fan flash, red shells), `magnum` (boom flash with side jets,
  rifling rings, spiked impact), `charged_blast` (charge, hold, one huge orb
  that explodes), `dual_pistols` (alternating hands with gun-kata swing arcs),
  `sniper_rail` (laser sight and lock-on reticle, then an instant helix rail
  line; the hit bursts `RAIL_DELAY` ticks later), `gatling` (barrels spin up,
  fire faster and faster, glow with heat, smoke on spin-down),
  `rocket_barrage` (missiles on alternating arcs with smoke trails),
  `drill_bullet` (pierces through, shatters at the end of its range) and
  `thunder_bullet` (crackling arcs, lightning trail, lightning strike on hit).
  Fields: Radius = bullet size, Thickness = impact size, Span = spread °,
  Length = range; Swing = ticks between shots (charge / aim / spin-up ticks
  for the charged blast / sniper / gatling), Hold = firing time (held charge /
  rail linger). With Aim target every round aims at where the target is the
  tick it fires. A round that hits stops there (`inst.tq_ki`); the drill and
  the rail record their hits in `inst.tq_imp` and carry on. Per-gun numbers
  live in the `GUNS` table; `check_parity.py` compares it and every other
  gunfx constant with `gunfx.js`. Same code path in Solo and Battle.
- **Power techniques (`laser/powerfx.py`, Studio: `powerfx.js`).** Anime
  signature moves, each a technique style with its own preset in the Studio's
  "Power techniques" group:
  - `ssj_aura` — Super Saiyan aura (modern style) shaped to the fighter's
    own silhouette, with flame physics. Each tick the technique records the
    body outline (`inst.tq_sil`: `AURA_N` points from `host.outline`, read
    off the sprite on screen with `powerfx.outline_from_alpha`; an ellipse
    when there is no sprite). Flame licks are attached: each stays on the
    edge point it was born on and rises along the aura's flow, stretching
    back (capped) as the speed rises, so they never spill out on their own;
    the aura's skin is pushed out along the flow and its outer layer streams
    back into a comet at speed, with speed lines. On a sharp turn at speed
    (`_aura_turn`) a few small fragments break off and fly on the old
    heading, fading within `AURA_FRAG_LIFE` ticks. The whole aura turns about its
    anchor to point opposite the movement (`_aura_flow`): upright at rest,
    fully back along the motion at `AURA_FULL` px/tick (any direction —
    flying up points it down), swung round smoothly over the last
    `AURA_SWING_N` ticks so turns and stops don't snap. **Movement reaction %** (Span) scales
    all of it. Toggles: power-up burst (flash, shock rings, dust blast),
    rising rocks (only while standing), power surges (a flare-up at most
    every 90 ticks), ground cracks, SSJ2 lightning (crackling over the body,
    **Lightning rate** per second).
  - `rasen_shuriken` — charge (Swing ticks), throw at the target (aim and
    range taken where the target was at launch, `inst.tq_tp`), then a sphere
    of needle cuts (Thickness = radius) for Hold ticks. A hit in flight sets
    `inst.tq_det`. Give it Pierce + Re-hit so the sphere keeps hurting.
  - `gigantic_meteor` — charge over the anchor, a 30-tick lobbed drop onto
    the target growing Radius → Thickness, a Length-px drag downward for Hold
    ticks, then a towering blast. Span = grip %.
  - `ghost_kamikaze` — a ghost every Swing ticks for Hold ticks: puffs out,
    hovers 16 ticks, then homes on the live target (`inst.tq_tp`) and blows
    up on contact / at range. Flight is stepped once per tick and cached
    (`inst.tq_gh`); a hit stops the nearest ghost (`inst.tq_ki`).
  - `serious_punch` — Swing-tick wind-up, then a shock cone (Length long,
    Thickness wide) crossing in Hold ticks, vapour rings, the sky split and
    clouds blown apart. Pierce on + Re-hit 0 = one heavy hit.
  - `black_hole` — opens where the target was when cast: black horizon,
    photon ring, a tilted accretion disc split front/back round the core,
    debris spiralling in; collapses and bursts after Hold ticks.
  - **Pull** (meteor, black hole): `powerfx.pulls(inst, ps)` returns this
    tick's fields `(x, y, radius, step, falloff)`; `FxDriver` collects them
    (none while Time control freezes its FX), `World.queue_fx_pulls` stores
    them per side and `World.refresh_battle` moves the opposing fighters at
    the start of the next tick — the same one-tick boundary as FX hits.
    Black hole: Span px/s inside Length px, weaker toward the edge; meteor:
    whatever is under it is pinned to its leading edge (Span = grip %).
    Blinked-out fighters are out of reach. Solo has no opponent, so there
    the pull has nothing to move (the visuals are identical).
  - **Parity:** `check_parity.py` compares the powerfx constants;
    `inst.tq_tp` (the target per tick) is recorded by `swordfx.on_spawn` /
    `on_tick(inst, host)` in both the game and the Studio.

## 12d. Weapons (`laser/weaponfx.py`, Studio: `weaponfx.js`)

Twenty hand-drawn **2.5D weapons**, each a `technique` style with its own
settings panel and two presets (signature colours, palette colour) in the
Studio's "Weapons" group. Test dummies can attack with them too.

- **2.5D drawing.** Each weapon is a flat model (`MODELS`: parts with a role
  — blade, edge, guard, grip, accent, dark, glowing `gem` / `spirit`) lifted
  into 3D: it spins round its own long axis (yaw), tilts toward / away from
  the camera with perspective (pitch: the near end grows, the far end
  shrinks) and can sit nearer or further (depth). The near face is lit by how
  square-on it is, the far face and the side walls between them show the
  weapon's thickness when it turns (edge-on at yaw 90), and a glint runs
  along the cutting edge.
- **Controls (all numbers, so every one can be keyframed ◆):** `w_scale`
  (size), `w_flip_x` / `w_flip_y` (1 = as drawn, −1 = mirrored left/right or
  up/down on screen round the anchor; keying 1 → −1 turns it over like a
  card), `w_yaw`, `w_pitch`, `w_spin` (yaw per tick), `w_depth`, plus the
  shared `rotation_deg`. `w_mode`: **signature** (materialise → its own
  sequence → hold its last pose for Hold ticks → dissolve) or **hold** (just
  held for Hold ticks, lying along the rig's own blade: hand → `wtip` of the
  frame on show, `haL` → `wtip2` when anchored on `haL`, grip on the hand; a
  rig without that tip keeps the ready pose — animate it with keyframes).
- **Momentum and swing plane (both modes):** `w_weight` 0..1 (0 = rigid, as
  posed): the angle chases its pose through a damped spring (`DRAG_HZ`,
  `DRAG_ZETA`; heavier = slower, more lag and overshoot) and the hand's
  acceleration swings it like a rod held at one end — a rising slash drags
  the tip down behind the hand, carries it past the peak and pivots it back.
  Integrated tick by tick from the effect's start over the recorded anchor
  path, so scrubbing, trails and hits all see the same blade. `w_plane`
  (degrees out of the screen: 0 = flat, 90 = horizontal swing — the blade
  shrinks as it points at or away from the camera and stretches out toward
  the target, with perspective), `w_plane_roll` (turns that plane on screen
  for diagonals), `w_side` **front** (passes between fighter and camera,
  near end grows) / **behind** (passes round the back, far end shrinks, and
  a front-layer weapon draws behind the fighter past `BEHIND_Z`). Hits,
  clashes and trails follow the blade as drawn.
- **Signature sequences** (`WEAPONS`): per weapon slot a keyed pose track
  `(t, x, y, reach, angle, yaw, pitch, scale, ease)` over `beats × Swing
  ticks`, timed events (`slam`, `cuts`, `xflash`, `snip`, `pillar`, `runes`,
  `glyph`, `burst`, `charge`, `petals`, `blink`) and, for firearms, a fire
  list. Swinging blades leave a swept trail (or afterimages).
- **Fields:** Length = weapon length, Thickness = blade half-width, Radius =
  reach (thrown / reaching weapons) or range (shots), Span = shot spread,
  Swing = ticks per beat, Hold = how long it stays, Density = debris /
  petals / motes.
- **Hits:** the blade hits along its cutting line while the sequence plays
  (hold mode: while held); each event hits where it goes off for `EVT_HIT`
  ticks; each shot hits once and stops (`inst.tq_ki`); the void cannon's beam
  hits along its line. Give the effect Pierce and a short Re-hit. Shots are
  listed by `swordfx.live_points` like gun rounds, so Retreat / Dodge /
  projectile counts see them in Battle. A swinging blade clashes along its
  cutting line (`body`).
- **Roster:**

| Style | Weapon | Signature |
|---|---|---|
| `buster_sword` | Buster Sword (Cloud Strife) | overhead slam: shock rings, cracks, rocks |
| `masamune` | Masamune (Sephiroth) | glint, instant draw, eight flash cuts on the target |
| `oath_oblivion` | Oathkeeper & Oblivion (Roxas) | twin counter-spins into an X slash |
| `crescent_scythe` | Scythe (RWBY) | 3D-tilted body spin shedding rose petals, reaping hook |
| `scissor_blade` | Scissor Blade (Kill la Kill) | splits into giant scissors, reaches, snips shut |
| `gungnir` | Gungnir (Fate) | rune charge, spiralling throw, pillar of light |
| `light_pistols` | Light pistols (Lucian, LoL) | alternating light bolts, twirl |
| `crimson_fang` | Swordsman | rising crimson slash |
| `arc_carbine` | Runner | two three-round arc bursts |
| `void_cannon` | Runner (heavy) | long charge, line beam |
| `phase_kunai` | Jumper | thrown kunai blink behind the target and strike back |
| `astral_staff` | Mage | twirl, rune circle, three falling star bolts |
| `phantom_greatsword` | New Fighter | spectral blade grows overhead, slam |
| `neon_uzis` | pewpew | alternating neon spray, twirl |
| `halo_chakram` | Puck | tilted spinning boomerang arc through the target |
| `wisp_rapier` | Puff | five-stab flurry with afterimages, final lunge |
| `pulse_bow` | Rapid | slow draw, released energy arrow |
| `rune_reaver` | Rune | reverse-grip back-spin, rune glyph ring |
| `nodachi` | Ronin | still moment, iaido draw from the scabbard, one long cut |
| `earth_cleaver` | Thear | two-handed ground-breaking slam |
| `void_sniper` | Void sniper rifle | muzzle charge, one void rail line, implosion on the target |

- **Parity:** `weaponfx.js` is a line-for-line port; `check_parity.py`
  compares `MODELS`, `WEAPONS` and every weaponfx constant. Same code path in
  Solo and Battle (FX Kit Player).

---

## 13. The Clash Interaction (`laser/clash.py`)

Clashing is world physics: no character chooses it, and every effect of
every fighter is bound by the same rules (there is no "clash" intercept mode
any more; an old file's one loads as `block`). Every tick, before
`World.refresh_battle`, `clash.step(world)` turns both sides' live effects into
bodies (a point, a line or a polyline with a half width) in five categories:

| Category | FX Kit | Built-in |
|---|---|---|
| beam | `beam` prim; Serious Punch technique (its shock cone, fist to front) | `RichBeamProjectile` |
| orb | `sprite` with shape `orb`; Charged Blast technique (each orb in flight) | mage petals, round / homing bullets |
| trail | `ribbon` (its moving end) | the laser trail (its moving end) |
| crescent | `arc` prim; sword techniques, punches, bladed weapons | `CrescentWave`, `UltimateCrescent` |
| sprite | bolt / blade `sprite`; Ki Barrage technique (each ki shot in flight) | the runner's bolts and other shots |

Ghost, glow, pulse, particles, weapon, the other guns and the other power
techniques never clash. **Absorb** (`clash._absorb`): an effect whose
Intercept is on in `absorb` mode swallows any enemy projectile body it
out-knocks by more than `fxkit.ABSORB_LEAD_KB` (300) that it touches (beams included; never a trail or an effect
attached to its fighter) instead of clashing, and grows
(`fxkit.absorb_grow`). A technique's shots clash one by one (`clash.ShotRef`):
a cancelled shot stops and detonates where it met, the rest fly on. A held
Charged Blast orb freezes its technique and is moved where the clash puts it
(`gunfx.place`: riding a struggle node, pushing through when it wins). Split
halves of a Charged Blast orb are plain FX Kit orbs, and of a Serious Punch
plain FX Kit beams, in the technique's colour; the punch's cone is cut short
at the contact (`inst.cap`). Two opposing bodies
that touch play the rule for their categories (`RULES`; every pair has one):

| Pair | What happens |
|---|---|
| beam × beam | both damage > 10: `beam_clash` explosion. Otherwise a `beam_struggle` for `STRUGGLE_TICKS`. The struggle is anchored: it draws each beam from its origin (locked when the clash starts) to the node at its real width, the real beams are hidden meanwhile, and the node is pushed toward the losing side. A winner then pushes through for `PUSH_TICKS` (~1 s): the node is driven all the way back into the loser's origin, the loser takes the winning beam's hit (its damage and knockback, along the beam), the won blast (`beam_struggle_won`, the "Beam struggle won" slot) goes off on the loser, and the winner's beam carries on past them and fades. A non-ultimate winner never pushes an ultimate loser through. A tie overloads |
| beam × orb | the orb is held on the beam head (`beam_orb`) for `BEAM_ORB_TICKS`, then bursts. Both knockback `STRUGGLE_KB` (100) or more: a struggle exactly like beam × beam (`beam_orb_struggle`; won: push-through, hit, `beam_orb_struggle_end`; tie: overload). The real orb rides the node on its own side; a winning orb flies on from the loser |
| beam × trail / crescent / sprite | `SPLIT_CHANCE` (50%): the beam splits at the contact into two halves fanning ±30° that run to the beam's end, can hit, and explode there (`split_burst`). Otherwise the beam carries on. A beam is never cancelled by its cutter |
| orb × orb | `orb_pops`. Both knockback 100 or more: an orb struggle (`orb_orb_struggle`; won: push-through, hit, `orb_orb_struggle_end`; tie: overload), the two real orbs pressed together either side of the node |
| orb × trail / crescent / sprite (a moving orb) | like a beam split: `SPLIT_CHANCE` (50%) the orb is cut into two halves (70% size) fanning ±30° that fly on, can hit, and pop where they end (`orb_split`, `orb_split_tip`); otherwise the pair's burst below plays and the orb carries on. An orb is never cancelled by its cutter; an ultimate orb is split only by a cutter with higher knockback |
| trail × trail | `sword_duel`: the two fighters are moved by the clash. They dash in, their blades meet, they spring apart, and it ends on one big clash back where they started; the knockback rule then settles it. The FX is anchored to their real positions. A pair that just duelled (`DUEL_REARM_TICKS`) gets `sword_slash_clash` instead |
| crescent × crescent | `crescent_struggle` for `CRESCENT_TICKS`, then the blades shatter |
| sprite × sprite | `kunai_clash` |
| orb × trail, trail × crescent | `sword_slash_clash` |
| orb × crescent, crescent × sprite | `getsuga_cross` |
| orb × sprite | `collision_nova` (orb not split) |
| trail × sprite | `kunai_clash` |

The six pairs at the bottom are one-shot bursts settled by the knockback rule.

**Knockback rule:** the higher `battle.knockback` (built-ins: `knockback_px`)
survives at full power and the other is cancelled at its source. A tie
cancels both. A trail can't be cancelled, so its owner recoils by the
knockback difference instead (a tie pushes both back a little). Sustained
clashes pin both effects where they met until they are decided. The same pair
can clash again once the two have been apart for `REARM_TICKS`.

**Clash length (`clash._budget`):** a clash lasts no longer than the shorter
*remaining* life of the two effects at contact (e.g. 50 ms and 40 ms left →
40 ms), and never less than `min_ticks` (default 6 ticks ≈ 100 ms). An
effect with no lifespan (a fighter's own sword trail, a hovering petal, an FX
with endless life) leaves it to the other one; with neither, the clash FX
plays at its normal length. A clash FX longer than its budget plays faster so
its whole loop fits (`ClashFX.fit`); a held clash (struggle, orb on the beam
head) holds for the fitted share of its hold; a sword duel that cannot fit
plays the one-shot `sword_slash_clash` instead.

**Clash size (`clash._pair_size`):** random for each clash FX, between 10%
and the higher knockback of the two effects (capped at 100) as a % of the
slot's Size % (knockback 100 → up to 100% of it, 50 → up to 50%, 0 → 10%).
A split half's end burst reuses its clash's size.

**One clash, one FX (`clash._quiet`):** contacts between the same two
fighters within `MERGE_TICKS` (6) and `MERGE_PX` (60 px) of a clash FX are
part of that clash: each is still settled by the knockback rule, but only
the first plays an FX and the clash action (one effect touching several
enemy effects at once no longer stacks FX).

**Overpower (`clash._overpower`):** a knockback lead of more than
`OVERPOWER_KB` (100) is no clash at all: the weaker effect is destroyed at
its source (a trail's owner recoils), and the stronger carries on untouched
(never pinned, split or slowed, no FX, no clash action).

**The fighter's clash action:** an image character with a Rig Forge `clash`
action shows its own action (looping), standing still, for exactly the
clash's length (`actions.force_clash`). FX built on the `clash` action in FX
Studio play with it.

**World Clash table (`clash.WORLD_SLOTS`):** for each rule slot, which clash
FX plays (or none) and its size and density, plus `min_ticks`. The trail ×
trail slot also has **Loop X %** and **Loop Y %** (0–400, default 100): they
stretch the sword duel's whole sequence (where each strike meets, how far
the fighters spring apart, the mid-duel circle back) on the screen's x and y
axes around where the blades first met (`clashfx.duel_plan` `loop`,
`clash.duel_loop`); the blades still meet at arm's length and each fighter
starts where it was. **Flurry %** (0–100, default 30) is the chance each
strike is a flurry combo: 2–4 quick hits at nearly the same spot, then a
bigger spring apart (`clash.duel_flurry`). The duel ends on its final hit
(`clash._final_hit`): the knockback winner (random on a tie) launches the
loser `FINAL_KB_BASE_PX` (240) + `FINAL_KB_PER_KB` (0.5) × its trail's
knockback px away (up to 900), then finishes (`clash._finisher`): its
`attack_special` at 50% HP or less, its ultimate (the Ctrl+1 / Ctrl+2 path,
built-ins included) below 30%, nothing above 50%. The defaults
live in `laser/clash.py`; FX Studio's **⚔ World Clash** page edits them and
saves `world_clash.json` (format `pb_world_clash`). Drop it like an FX file
(`update_game.bat` files it as `characters/world_clash.json`) or put it there
yourself; the game reads it at start-up (`clash.load_world`). It is the same
for every character; an old character file's `pack.clash` is ignored.
`tools/fx/check_parity.py` keeps the Studio's `CLASH_SLOTS` / `MIN_TICKS` /
`CLASH_FX` in step with the game.

Solo and Battle share this path. A clash needs two fielded sides, so Solo
(with only the cursor as an opponent) never finds a pair.

### World Physics: Dust & Air (`laser/worldfx.py`)

The dust, rocks and air the ARENA kicks up. It belongs to the world, not to
any fighter: `worldfx.step` runs once per tick after both sides moved and only
reads the fighters, so Solo and Battle run the same code (a clash needs two
sides, so clash dust is Battle-only; everything else plays in Solo too).

* **Ground:** the screen is a slope seen from its foot. The position-scale grid
  sets size and pace; a particle has a ground point plus a height drawn
  straight up the screen. Ground rings are ellipses, `flat_near` (nearest) to
  `flat_far` (farthest): rounder the farther away. Screen edges are the walls.
* **Engine:** rocks, pebbles and sparks are closed-form; fine dust is
  simulated and relaxes toward the local air velocity
  (`v = u + (v - u) e^(-dt/tau)`); air = blast (push, then suck-back), wake
  and shed curls, jump column, ground / wall jets. Size grows with the cube
  root of energy.
* **Events:** dash (on-screen speed over `dash.speed`), leap and hop-back
  take-off / landing, knockback launch / skid / crater (a slide of 2x
  `slam.min_speed` that stops), wall slam (a slide that hits a screen edge,
  `motion.check_walls`), clash (`clash._spawn_fx`), blast (a technique shot
  detonating, damage >= `blast.min_damage`), sound barrier (on-screen speed
  over `sonic.mach`; knockback slides only with `sonic.knockback`).

FX Studio's **🌪 Dust & Air** page edits the shared settings with a live
preview and saves `world_physics.json` (format `pb_world_physics`); drop it
like an FX file (`update_game.bat` files it as `characters/world_physics.json`).
A character's **Character FX → Dust & Air** section can give it its own copy
of any section (saved in its FX file as `world_physics`), used for the events
that fighter causes. `tools/fx/check_parity.py` keeps the Studio's tables in
step with the game.

---

## 14. Tag Pairs and the Switch Action (`laser/tag.py`)

In the start menu, set a slot to **Tag** and then click its partner (another
slot, or a character card to fill an empty slot); both get the pair's border
colour and form a tag pair (a team of 3 or 4 can hold one or two pairs): one fights, the other waits on the bench (off screen, frozen:
HP, cooldowns and timers wait). **Switch** swaps them, and each character
authors its own Switch:

| Where | What |
|---|---|
| Rig Forge | `switch_in` (incoming fighter) and `switch_out` (outgoing fighter) actions: "+ Action", type the name |
| FX Studio, `switch_in` | its FX, plus **Switch trigger (reads the on-field partner)**: the conditions and **Switch cooldown ms** |
| FX Studio, `switch_out` | its FX (no trigger: it plays when the partner's `switch_in` starts) |

Sequence: the benched fighter's `switch_in` conditions pass (read against the
on-field partner: its HP, its target, hits it took ...) or its **Tag in**
hotkey is pressed (default Alt+1..4), the cooldown is over, and the on-field
fighter is free (not mid ultimate / special / defend / clash). The on-field
fighter plays `switch_out` where it stands; then the incoming fighter takes
its spot and facing and plays `switch_in`. A missing animation is skipped. A
KO'd on-field fighter with a standing partner is replaced at once (no
conditions, no cooldown), so a tag team only loses when both are down.

Only Rig Forge characters can be set to Tag. Solo and Battle share this path.


---

## 15. Targeting (`laser/targeting.py`, FX Studio "Targeting (whole character)")

Which enemy the fighter fights in Battle (1v3 and other uneven splits make
this matter). Off = the nearest enemy, as before; built-in characters always
use the nearest. The chosen target drives movement and chasing, attacks and
aiming, FX aimed at the target, and every `target_*` condition. A Black Ox
Effigy's taunt still overrides it.

| Setting | What |
|---|---|
| Mode | Nearest, Farthest, Lowest HP, Highest HP (by HP % or amount), Stick until KO, Last attacker, Weighted score |
| Otherwise | the mode Stick / Last attacker use when they have no one |
| Weighted score | Closeness, Low HP, Is attacking, Targets me, Melee fighter, Ranged fighter: -100..100 % each |
| Retarget timing | Hold at least ms; Switch margin % (the new pick must score this much better) |
| Range limits | Min / Max range px (0 = none; nobody inside = nearest); Ignore blinked out |
| Team coordination | Focus (same target as team-mates) or Spread (different targets), Strength % |
| Conditional rules | Rule list: trigger conditions (ANY / ALL) + a mode; the first rule that passes sets the mode |
