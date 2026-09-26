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
                                    "movement": "stand", "move_speed_pct": 100}},
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
`move_speed_pct` % of its normal speed (100 = full). `idle` always stands and
`run` always moves, so the field is ignored for them. The engine applies it in
Solo and Battle alike (`FXK.moveFactor(name, cfg)` gives the speed fraction).

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

## 7. Phase 2 — engine integration (decisions so far)

The engine does **not** read character folders or `pb_fxkit` yet. These
decisions are agreed:

1. **Image characters.** `characters.load_all` loads each `characters/<name>/`
   that holds a `character.json` (`pb_char_pkg`): its PNG frames per action,
   the stats/archetype/palette from `character.json`, and `<name>.fxkit.json`.
   The existing rig-drawn JSON characters keep working until you replace them.
2. **Full actions.** When an action starts, the game shows every one of its
   frames at `frame_ms` and holds the fighter in that action until it ends, so
   a 2.4 s attack takes 2.4 s. Identical in Solo and Battle.
3. **Archetype = behaviour, FX + weapon = damage.** The archetype still decides
   how the fighter moves and when it attacks. For these characters, the only
   damage comes from effects with **Deals damage** ticked, including the
   `weapon` hitbox. The archetype's built-in hit or projectile damage is off.
4. **Runtime port.** Create `laser/fxkit.py`, a line-for-line port of
   `fxkit.js`: mulberry32, `build_lut`, `spawn`, `move`, `tick`, the draw
   routines with QPainter, and `resolveHits`/`HIT.*`. It must be one
   self-drawing object per instance (FX_GUIDE Pattern A).
5. **Defence works like bullets.** Hits are resolved on the defender's side.
   Each tick, `World.refresh_battle` adds a read-only `enemy_fx` snapshot of the
   opponent's live damaging instances (the same one-tick boundary as
   `enemy_projs`; no extra cross-process data, since both sides run in one
   process).
   - Parry, special-stance block, petals and deflect act on them.
   - A blocked or intercepted instance is ended at its source through a kill
     call, never by editing it directly.
   - Damage goes through `ai.apply_hp_damage(amount=damage)`, and knockback
     through `hit_pending/hit_vx/hit_vy`.
   - Solo: the target is the cursor.
6. **Action triggers** are authored in the Studio (`action_settings` above)
   and evaluated by the game, extending `ai.evaluate_activation_triggers` with
   ANY/ALL logic, the new condition types, FX tags (read from the opponent's
   `enemy_fx` snapshot) and attack chains.
7. **Parity test.** Render one character folder in headless Chromium
   (`fxkit.js`) and in offscreen Qt (`fxkit.py`) at fixed ticks, and diff the
   frames with a tolerance for antialiasing. Also compare the per-tick hit
   list (tick, effect, damage), which must match exactly.

`pb_fxkit` v1 files (`joint_track` in rig units, from the earlier rig-based
Studio) are superseded by v2 image-px `anchors`.
