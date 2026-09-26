# FX Kit — `pb_fxkit` v2 specification

Characters are **keyframe images**. FX are data. The pipeline:

```
Rig Forge (rigforge.html)          FX Studio (studio/fx_studio.html)        game (laser/)
  pose + animate the rig      ──►    open the character folder         ──►   loads the folder:
  "Export character package"         anchors, FX, weapon hitbox              PNG frames + character.json
  writes characters/<name>/          "Save FX to folder" writes               + <name>.fxkit.json
    character.json + PNG frames        <name>.fxkit.json into it
```

The runtime reference is `tools/fx/studio/fxkit.js`. The engine port
(`laser/fxkit.py`, Phase 2) mirrors that file function for function. If this
document and `fxkit.js` ever disagree, `fxkit.js` is correct and this file must
be fixed.

---

## 1. The character folder

`characters/<name>/` holds everything for one character:

| File | Written by | Holds |
|---|---|---|
| `<action>_NN.png` | Rig Forge | every frame of every action (in-betweens included), facing right, on one shared square canvas; the image centre is the figure's position |
| `character.json` | Rig Forge | `format: "pb_char_pkg"`: name, display name, archetype, predicates, movement, stats, palette, per-action `trigger` / `duration_ms` / `frame_ms` / frame file list, `image {size, origin_px, head_px}`, and the starting `anchors` (every Rig Forge joint, per frame, in image px) |
| `<name>.fxkit.json` | FX Studio | `format: "pb_fxkit"` v2: the effects, the anchors as you placed them, and each effect's damage |

`character.json` contains no rig, poses or FX. The game never draws a rig for
these characters; it plays the PNGs.

```json
{
  "format": "pb_fxkit", "version": 2, "tick_ms": 16, "character": "ronin",
  "space": {"image_origin_px": [720, 720], "head_px": 58, "target_head_px": 16, "game_px_per_image_px": 0.275862},
  "timing": {"attack_normal": {"frame_ms": 17.143, "frames": 35}},
  "palette_lut": {"built_from": ["palette.body", "palette.accent"], "rule": "palette.build_lut([body, accent])"},
  "anchor_labels": {"haR": "near hand", "wtip": "weapon tip", "muzzle": "gun muzzle"},
  "anchors": {"attack_normal": {"haR": [[x, y], "... one per frame"], "wtip": []}},
  "action_settings": {"ultimate": {"logic": "all", "cooldown_ms": 0,
                                    "conditions": [{"type": "hp_below", "pct": 50, "repeat": false}, {"type": "target_within", "px": 80}],
                                    "chain_next": "", "chain_reset_ms": 1000, "fx_continuous": false,
                                    "movement": "stand", "move_speed_pct": 100, "anim_loops": 1, "back_stop_pct": 80}},
  "aim": {"enabled": false, "source": "attack_normal", "from_anchor": "haR", "to_anchor": "wtip", "max_deg": 75},
  "effects": [ { "...": "section 3" } ]
}
```

### When each action plays (`action_settings`)
- **`idle` / `run`**: locomotion (standing still / moving). No conditions.
- **Attack actions (`attack_normal*`)**: the archetype decides when to
  attack. `chain_next` names the next attack in a combo (e.g.
  `attack_normal → attack_normal_2 → attack_normal_3`). The chain resets
  after `chain_reset_ms` without attacking.
- **Every other action** (`defend`, `deflect`, `attack_special`, `ultimate`,
  …) fires when its `conditions` are met: `logic: "any"` (OR) or `"all"`
  (AND), no more often than every `cooldown_ms`. Condition types:

| type | fields | met when |
|---|---|---|
| `hp_below` | `pct`, `repeat` | own HP ≤ pct % (once per crossing unless `repeat`) |
| `attacks_made` | `count` | N attacks made since this action last fired |
| `hits_taken` | `count` | hit N times since this action last fired |
| `target_within` / `target_beyond` | `px` | target closer / further than px |
| `hit_by_fx` | `tags` | hit by an enemy FX whose `tag` is listed (empty = any) |
| `fx_near` | `tags`, `px` | an enemy FX with a listed tag comes within px |
| `bullet_deflected` | — | this character just deflected a bullet |
| `after_actions` | `sequence` | just completed these actions in order (comma separated) |

Every action also has `fx_continuous` (the Studio's **continuous FX** toggle).
When the action loops (idle, run, or any action that repeats) and this is on,
an effect that lasts to the end of the action (`life_ticks 0`, window
reaching the last frame) keeps running across the loop. It isn't spawned
again while it's alive, so a trail keeps flowing instead of restarting.
Effects with a fixed life, and periodic re-emits, fire as usual on each loop.

Every action also has `movement` (the Studio's **Movement** section) for
attack and triggered actions: `"stand"` roots the fighter in place for the
whole action; `"move"` lets it keep moving while the action plays, at
`move_speed_pct` % of its normal speed (100 = full); `"back"` retreats straight
away from the target at `move_speed_pct` % of its normal speed until
`back_stop_pct` % of the whole action (all loops) has played, then holds
still for the rest. `idle` always stands and
`run` always moves, so the field is ignored for them. The engine applies it in
Solo and Battle alike (`FXK.moveFactor(name, cfg)` gives the speed fraction).

Every attack and triggered action also has `anim_loops` (the Studio's
**Animation loops**, default 1): the animation plays this many times back to
back, then the action ends, so the action lasts `anim_loops × frames ×
frame_ms`. Each pass is an ordinary animation loop for the FX: effects fire
and carry over exactly as they do whenever an animation loops (`fx_continuous`
and `continuous` effects included). `idle` and `run` ignore it; they loop for
as long as the fighter stands or moves. `FXK.animLoops(name, cfg)` gives the
count.

Every effect carries a `tag` (its FX type, e.g. `fireball`, `slash`) that
other characters' `hit_by_fx` / `fx_near` conditions match against.

## 2. Space and time

- **Tick.** Everything advances once per 16 ms tick (`config.TICK_MS`). Nothing
  reads wall-clock time.
- **Action clock.** Each action's frames play at its `frame_ms` (Rig Forge's
  `duration_ms / frames`). Frame `f` begins at tick `round(f * frame_ms / 16)`.
  The game shows every frame of the action at this rate (Phase 2 decision:
  "play the full Rig Forge action").
- **Coordinates.** Game px, y down. `(0, 0)` is the figure position, which is the
  image centre (`image_origin_px`). x is mirrored when the figure faces left.
- **Image to game scale.** The game sizes every character by head diameter:
  `game_px_per_image_px = TARGET_HEAD_PX (16) / head_px`. The figure sprite and
  every anchor use this scale, times `position_scale()`.
- **Anchors.** `anchors[action][id][frame]` is an image-px point.
  - Rig Forge pre-fills every joint:
    - body: `hip chest neck head shB root` (`root` = above the head)
    - arms: `shL shR elL elR haL haR`
    - legs: `hpL hpR knL knR ftL ftR`
    - weapon: `wtip`

    `L` joints are the far limb and `R` joints the near limb.
  - The Studio lets you move any of them per frame (click to place) and add
    your own (e.g. `muzzle`).
  - A frame you leave empty holds the previous frame's point. The saved file
    has every frame resolved.
  - Game px: `(p - image_origin_px) * game_px_per_image_px * position_scale`,
    mirrored in x when facing left.
- **Special anchors.** `figure` (the image centre) and `target`.

## 3. Effect

```json
{
  "id": "E…", "name": "Blade trail", "tag": "slash", "action": "attack_normal", "enabled": true,
  "prim": "ribbon",
  "start_frame": 0, "end_frame": -1, "life_ticks": 0, "continuous": false,
  "emit": {"every_ticks": 0, "count": 1, "fan_deg": 0},
  "anchor": "wtip", "offset": [0, 0],
  "motion": {"kind": "attached", "aim": "target", "angle_deg": 0, "aim_offset_deg": 0, "speed": 8,
             "turn_deg": 6, "amplitude": 55, "freq": 0.18, "orbit_rx": 46, "orbit_ry": 46, "orbit_deg": 1.12},
  "color": {"mode": "palette", "lut_index": 128, "lut_index2": 128, "lut_offset": 0, "flow_speed": 0.008,
            "c1": "#ffffff", "c2": "#ff2200", "start_fraction": 0},
  "layer": "front", "blend": "normal",
  "battle": {"deals_damage": false, "damage": 1, "pierce": false, "rehit_ticks": 0, "knockback": 0},
  "params": { "...": "per primitive, section 5" }
}
```

Every field is always written out (`FXK.normalize`); a reader never has to guess
a default.

### Timing
- The effect is **active** from `start_frame` until the end of `end_frame`
  (`-1` = end of the action).
- It **emits** `emit.count` instances at the start tick, then again every
  `emit.every_ticks` while active (`0` = once).
- With `count > 1`, instances fan across `fan_deg`. Orbit instances spread
  evenly around the circle, and zigzag pairs weave in opposite phase.
- Each instance lives `life_ticks` (`0` = until the active window ends). After
  that, a ribbon keeps decaying its tail, and particles and ghosts finish
  fading, before the instance is removed.
- When the action loops, instances that are already alive keep running.
- `continuous: true` (the Studio's per-effect **∞ Continuous** toggle) makes
  the effect produce without ever stopping or resetting while its action
  plays, loop after loop (an always-on laser trail). From `start_frame` on,
  one set of `emit.count` instances is kept alive with no end: `end_frame`,
  `life_ticks` and `emit.every_ticks` are ignored and it never fades out
  (a glow set to fade `in` fades in once over its window, then holds; size
  and width ramps run once over the window, then hold). A new set starts
  only if the running one ends, e.g. a non-piercing damaging hit consumes it,
  or the action restarts. It ends when the action changes. It applies only
  to effects that stay on the fighter (`attached`, `static` or `orbit`
  motion) and are not `arc`; for travelling shots and crescents the flag
  does nothing. It is stronger than the action's `fx_continuous`, which only
  carries over effects that already last to the end of the action.

### Motion (`motion.kind`)
| kind | behaviour | engine source |
|---|---|---|
| `attached` | sits on the anchor every tick | trail / held FX |
| `static` | stays where it spawned | bursts |
| `travel` | `speed` px/tick along the aim | `Projectile` |
| `homing` | travel, steering up to `turn_deg`/tick toward the target | `HomingProjectile` |
| `zigzag` | travel plus a lateral sine weave (`amplitude`, `freq`) | `ZigzagProjectile.update` |
| `orbit` | circles the anchor (`orbit_rx`, `orbit_ry`, `orbit_deg`/tick) | petals |
| `path` | travels along the path `motion.path` from where it spawns (see 3b) | FX Kit extension |

The aim (`motion.aim`) is one of:
- `target`
- `facing`
- `angle` (`angle_deg`: 0 = forward, positive = down; mirrored when facing left)
- `weapon` (the blade's world angle on that frame)

`aim_offset_deg` rotates the aim.

### Colour (`color.mode`)
- `palette`: the character LUT, built as `palette.build_lut([body, accent])`,
  exactly what `characters.py` registers.
  - Along-path primitives (`ribbon`, `arc`) flow through it at `flow_speed` per
    tick, like `TrailComponent`.
  - Every other primitive takes `lut_index` (start) → `lut_index2` (end).
- `gradient`: `c1` → `c2`. For ribbons and arcs, `c1` holds solid until
  `start_fraction` (the `trail_gradient` rule).
- `solid`: `c1`.

## 3b. Entry points and paths (shared library)

The FX file carries two lists that every action's effects can use:

```json
"entry_sets": [{"id": "P…", "name": "Halo of 3", "base": "figure", "mode": "simultaneous",
                "interval_ticks": 6, "points": [[-16, -44], [0, -50], [16, -44]]}],
"paths": [{"id": "T…", "name": "Arc over", "points": [[0, 0], [50, -40], [100, 0]], "smooth": true,
           "ticks": 24, "orient": "aim", "end": "continue", "follow": false}]
```

**Entry sets.** An effect whose `anchor` is `"set:<id>"` comes out of every
point in the set instead of one anchor. Points are game px from `base`
(`"figure"` or an anchor id), x forward (mirrored when facing left), y down.
The effect's `offset` is added on top. Each time the effect fires (start
frame, each re-emit, a continuous start), it spawns `emit.count` copies at
each point:
- `simultaneous`: all points at once;
- `sequential`: point 1 at once, point 2 `interval_ticks` later, and so on.
  Each copy's life is shortened by its delay so they all end with the window.
Attached and orbit motions ride their own point. An empty or missing set
plays from the figure.

**Paths.** An effect with `motion.kind "path"` and `motion.path = <id>`
travels along the path from where it spawns:
- `points[0]` is always `[0, 0]`, the spawn point; x forward, y down, game px.
- With `smooth`, the route is a Catmull-Rom curve through the points (12
  steps per segment); otherwise straight lines. Movement is at constant
  speed by distance, start to end in `ticks`.
- `orient "facing"`: mirrored with the facing. `orient "aim"`: also turned
  so the start→end line points along the effect's aim direction (`motion.aim`,
  `aim_offset_deg`), fixed when it spawns.
- `end`: `stop` holds at the end; `loop` starts over; `continue` carries on
  straight along the last direction at the same speed.
- `follow`: the path's start moves with the spawn point every tick (orbits,
  boomerangs); otherwise it stays where it spawned.
- The instance's direction is the path tangent, so bolts, trails and beams
  line up with the route.

`fxkit.js` (`entrySetOf`, `entryPoint`, `pathLine`, `pathAt`, `pathMatrix`,
`pathStep`, `Player.tick`'s `fireFx` / pending queue) is the reference; the
engine supplies the lists as `host.lib = {entry_sets, paths}`.

## 4. Randomness

All randomness goes through **mulberry32** (`FXK.rng`), seeded per instance with
`hash32(effect.id) ^ imul(tick + 1, 0x9E3779B1) ^ (index * 0x85EBCA6B)`. The
Python port must implement the same generator (32-bit arithmetic:
`imul(a, b) = (a * b) & 0xFFFFFFFF`), so a given effect throws the same
particles in the Studio and in the game. The Studio re-simulates from tick 0
when you scrub, so any paused frame is exactly the state playback reaches.

## 5. Primitives

Each one is a drawing routine the engine already has. The defaults are that
routine's `config.py` values.

| prim | engine routine | params |
|---|---|---|
| `ribbon` | `TrailComponent.update/draw` | `max_points 50, min_dist 2, decay 2, taper, w_tail 1, w_head 5, alpha 220, head_glow_r 1, head_dot_r 1` |
| `arc` | `CrescentWave.__init__/draw` | `radius 42, span 170, width 6.5, tail 0.95, segs 16, grow 0.85, core_alpha 0.7, core_width 0.3, orient motion\|angle, angle_deg, placement anchor\|wrap_target\|through_target, back 51, lead 26` |
| `beam` | `RichBeamProjectile.draw` | `length, w_start0/1, w_end0/1, segments, glow, glow_color, pulse_hz, jitter, detach_ticks, grow_ticks` |
| `sprite` | `bullet_sprite` / `bolt_sprite` + `Projectile.draw` | `shape orb\|bolt, radius, stretch, hot, halo, fade, trail_len` |
| `particles` | `BurstParticle` / `_spawn_burst_now` | `mode burst\|stream, count, rate_per_s, angle_deg, spread_deg, speed_min/max (px/s), gravity (px/s²), drag, size_min/max, size_over_life, life_min_ms/max_ms` |
| `glow` | `TrailComponent` head glow + core | `r_start, r_end, a_center, a_mid, mid, core_r, fade none\|out\|in\|inout, pulse_hz` |
| `ghost` | `Figure.draw` afterimages (`silhouette`) | `interval 2, ghost_life 14, alpha 150, max 12` |
| `weapon` | melee hitbox (new) | `to_anchor wtip, width 6`: a capsule from the effect's `anchor` to `to_anchor`, following the frames; never drawn in-game (the Studio outlines it) |

A few rules are FX Kit's own; the engine's classes don't need them:
- A beam that isn't travelling (`attached`, `static`, `orbit`) extends from its
  anchor along the aim over `grow_ticks` and re-aims every tick.
- `particles` values are in game px directly. The old `fx_layers` path
  multiplied by a canvas-to-game scale; FX Kit does not.
- `blend: additive` maps to `QPainter.CompositionMode_Plus` in Qt and
  `lighter` in the canvas.
- `layer: behind | front` places the effect before or after the figure sprite.

Arc `placement` reproduces `CrescentWave.__init__`. The aim direction `dir`
runs from the anchor to the target.
- `anchor`: the arc is centred on the anchor.
- `wrap_target`: `centre = target - dir * back`, the default slash (`back 51`).
- `through_target`: `centre = target + R * (dir_y, -dir_x) - dir * lead`, so the
  arc's midpoint starts `lead` px short of the target and cuts through it.

## 5b. Damage (`battle`)

Every effect has a **Deals damage** checkbox (`battle.deals_damage`). Unticked
means visual only: the effect never touches HP. Ticked, the effect is an attack:

| field | meaning |
|---|---|
| `damage` | HP per hit, passed to `ai.apply_hp_damage(fig, world, amount)`. Every built-in attack deals 1. |
| `pierce` | `false`: the first hit ends the instance (a bolt stops, a travelling beam or arc vanishes; a particle that hits is removed). `true`: it keeps going. |
| `rehit_ticks` | `0`: one hit per instance per target. `N`: may hit the same target again every N ticks (held beams, orbiting orbs). Particles count each particle separately. |
| `knockback` | px of push along the effect's direction on hit, delivered through the existing `fig.combat.hit_pending/hit_vx/hit_vy` channel. |

**Hit rule: what you see is what hits.** An instance hits when the shape it
*draws* this tick touches the target's hurt circle (centre = target figure,
radius `PROJ_HIT_RADIUS` = 16 px; the Studio's "hurt r" box previews it). Per
primitive (`HIT.*` in `fxkit.js`):
- `sprite`: the centre is within the hurt radius (the engine's `Projectile`
  `hit_r_sq` rule).
- `ribbon`, `beam`, `arc`: any visible segment passes within `hurt r + half
  stroke width`. Beams use the same jittered geometry they draw, and arcs only
  the segments currently shown.
- `particles`: each particle is within `hurt r + size/2`.
- `glow`: the circle of the current radius overlaps the hurt circle.
- `ghost`: never (afterimages are visual only, and the checkbox is disabled).
- `weapon`: the segment `anchor → to_anchor` passes within `hurt r + width/2`.
  This is how the weapon deals damage: add a `weapon` effect over the frames
  where the blade should hurt, and tick **Deals damage**.

Hits are resolved after each tick's movement (`resolveHits`), with the same
deterministic state that is drawn, so the Studio's hit count is what the engine
must reproduce.

Built-in attack presets are ticked with the engine's values:
- 1 HP: crescent, through crescent, cone/zigzag bolts, homing orb, petal orbs,
  and the held beam (re-hit every 8 ticks)
- 8 HP: rich beam (`LOOP_BEAM_DAMAGE`)

Trails, sparks, spheres and afterimages are visual.

## 6. Presets

Built-in presets (`studio/presets.js`) rebuild the game's hardcoded effects from
these primitives with their `config.py` numbers: laser trail, blade trail,
crescent slash, through crescent, cone/zigzag bolts, homing orb, rich and held
beams, petal orbs, energy sphere, afterimages and spark burst. Your own presets
are kept in the browser, and **Export**/**Import** moves them as a
`pb_fx_presets` file:

```json
{"format": "pb_fx_presets", "version": 1, "presets": [{"name": "…", "desc": "…", "effects": [ … ]}]}
```

The built-in characters (Swordsman, Runner) keep their original effect code.
The presets only seed new FX.

## 7. Phase 2 — engine integration

**Done:**

1. **Getting characters in.** `laser/drops.py` files a Rig Forge package
   (`<name>.zip` or `<name>/`) and `<name>.fxkit.json`, dropped at the repo
   top level or in `drop/`, into `characters/<name>/`. It runs in
   `update_game.py` after syncing and at game start-up.
2. **Image characters.** `characters.load_all` loads each `characters/<name>/`
   holding a `character.json` (`pb_char_pkg`). It is converted to the
   `sprite_files` shape (the same path `rapid.json` uses):
   - `run`, `idle` and `attack_normal` become run/idle/slash;
   - `defend` becomes slide;
   - every action is also an extra set by its own name;
   - timing comes from `frame_ms`;
   - archetype, stats and palette come from `character.json`.

   A package replaces a rig-drawn `characters/<name>.json` of the same name.
   Solo and Battle use the identical path.
3. **Runtime port.** `laser/fxkit.py` mirrors `fxkit.js`:
   - mulberry32 and `jround` (JavaScript's Math.round; Python's round()
     rounds halves to even);
   - `spawn`, `move`, `tick`, entry sets, paths and continuous effects;
   - `Player`;
   - drawing with QPainter, reusing `combat.bullet_sprite` / `bolt_sprite`
     and `silhouette`;
   - the hit tests.
4. **Game hook.** One `FxDriver` per figure whose character has an FX file:
   - It is ticked by `CombatSystem` and drawn by `Figure.draw`: the "behind"
     layer before the sprite, "front" after.
   - The action and frame come from the same state `Figure._current_frame`
     uses.
   - Action time follows the frame on screen: it advances inside a frame's
     span, jumps ahead with fast frames, holds on a held frame, and starts a
     new pass when frames loop.
   - Anchors map as (image px − origin) × 16/head_px × position scale,
     mirrored with facing and rotated with the sprite.
   - Target: the nearest opponent's snapshot position in Battle, the cursor
     in Solo.
5. **Damage.** Hits are tested against the opponent snapshot's 16 px hurt
   circles and queued on `SideState.fx_hits`. `World.refresh_battle`
   delivers them at the start of the next tick:
   - damage goes through `ai.apply_hp_damage(damage)`;
   - knockback px becomes a bounce at px × (1 − BOUNCE_FRICTION), the same
     conversion as the dash push.

   Solo deals no FX damage.
6. **Parity test.** Tick-by-tick instance positions and the full hit list,
   `fxkit.js` against `fxkit.py`: identical, except a homing shot circling
   exactly on its target, where last-digit differences between JavaScript's
   and Python's trig functions can flip its turn.

7. **Actions** (`laser/actions.py`, one `ActionRunner` per image fighter,
   ticked by `CombatSystem` before its FX):
   - Every attack or triggered action plays all its frames at `frame_ms`,
     `anim_loops` times, through `Combatant.action_anim` / `action_idx`.
     The sprite, FX and anchors follow it.
   - `movement: "stand"` roots the fighter, facing the target. A knockback
     still moves it.
   - `movement: "move"` scales its speed to `move_speed_pct` while the
     action plays.
   - `movement: "back"` moves it straight away from the target at
     `move_speed_pct` % speed until `back_stop_pct` % of the action.
   - **Aim** (`aim.enabled`): every tick the fighter faces the target and
     its frame on show turns (`Figure.aim`, degrees, after mirroring) so the
     barrel line `from_anchor -> to_anchor` of that frame passes through the
     target (`fxkit.aim_angle`; frames without both anchors use the
     `source` action's average barrel), at most `max_deg` either way.
     Anchors and FX turn with it.
   - **Attacks.** The archetype decides when: melee inside
     `basic_attack_radius`, shooters from `max(radius, 420 px)`. Attacks are
     at least 350 ms apart, or `cooldown_ms`. `chain_next` continues the
     combo when the next attack starts within `chain_reset_ms`.
   - **Triggered actions** (defend first, then ultimate, attack_special,
     others) play when their conditions pass (ANY / ALL), no more often
     than `cooldown_ms`. With no conditions, an action never triggers.
   - **Conditions:**
     - `hp_below`: once per crossing unless `repeat`.
     - `attacks_made` / `hits_taken`: counted since that action last fired.
     - `target_within` / `target_beyond`: distance to the target.
     - `hit_by_fx`: tags of hits taken this tick. An FX hit carries its
       tag; any other hit counts as "".
     - `fx_near`: the opponent's live damaging FX and bullets (tag
       "bullet") within px, from `SideState.enemy_fx`, rebuilt each tick by
       `refresh_battle`.
     - `bullet_deflected`: a parry just started.
     - `after_actions`: the last completed actions, in order.
   - Attack mode (Alt+Up) gates attacks and triggered actions exactly as it
     gates the built-in fighters. `defend` always works.
8. **Damage is FX only.** For image characters:
   - The loader sets `disable_basic_attack`, `disable_survival_teleport` and
     `ultimate_playback.style: none`.
   - `CombatSystem` skips the melee dash-slash FSM.
   - Their body never deals contact damage, and a plain bump never costs
     them HP. The opponent's dash still does.
   - In Battle they close only to ~60% of their attack radius instead of
     charging into the opponent.
9. **Defence.** While `defend` plays, every incoming hit is blocked: FX,
   bullets (no knockback either) and contact. An FX hit on a parrying or
   defending fighter is blocked, and a non-piercing FX that was blocked
   ends at its source.

**Still to do:**

- Parry reflection, petals and deflect crescents acting on FX instances
  directly. Today they block FX hits; they don't yet destroy FX in flight
  the way they destroy bullets.

`pb_fxkit` v1 files (`joint_track` in rig units, from the earlier rig-based
Studio) are superseded by v2 image-px `anchors`.
