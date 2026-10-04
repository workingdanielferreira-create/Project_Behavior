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
                                    "movement": "stand", "move_speed_pct": 100, "anim_loops": 1, "back_stop_pct": 80,
                                    "attack_px": 0,
                                    "blink": {"enabled": false, "start_frame": 0, "end_frame": -1, "anchor": "target",
                                              "direction": "behind", "angle_deg": 0, "proximity_px": 60, "flash": true,
                                              "cooldown_ms": 0}}},
  "aim": {"enabled": false, "source": "attack_normal", "from_anchor": "haR", "to_anchor": "wtip", "max_deg": 75},
  "damaged": {"cooldown_ms": 0},
  "retreat": {"enabled": false, "mode": "avoid", "angle_deg": 180, "curve_deg_s": 0, "speed_pct": 200,
              "proximity_px": 80, "avoid_duration_ms": 1500, "reengage_duration_ms": 2000, "cooldown_ms": 3000,
              "logic": "any", "conditions": [{"type": "hp_below", "pct": 50, "repeat": false, "not": false},
                                              {"type": "projectile_count", "count": 5, "not": false}]},
  "effects": [ { "...": "section 3" } ],
  "groups": [{"id": "G…", "name": "Group 1", "action": "attack_normal", "anchor": "haR", "offset": [0, 0]}]
}
```

### When each action plays (`action_settings`)
- **`idle` / `run`**: locomotion (standing still / moving). No conditions.
- **Attack actions (`attack_normal*`)**: the archetype decides when to
  attack (target inside attack range). `attack_px` (the Studio's **Attack
  distance**) sets that range for this attack in game px at 100 % character
  scale; `0` = the character's `basic_attack_radius` (shooters:
  `max(radius, 420 px)`). Each attack in a chain has its own. If the attack has `conditions`, they
  must ALSO pass (`logic` any / all); with none it attacks on range alone.
  `chain_next` names the next attack in a combo (e.g.
  `attack_normal → attack_normal_2 → attack_normal_3`). The chain resets
  after `chain_reset_ms` without attacking.
- **Every other action** (`defend`, `deflect`, `attack_special`, `ultimate`,
  …) fires when its `conditions` are met: `logic: "any"` (OR) or `"all"`
  (AND), no more often than every `cooldown_ms`.

Every condition has `not` (default `false`): `true` inverts it (met when the
check is false). Speeds are game px per second. In Solo the target is the
cursor: it has no HP and never attacks or defends (those checks are false),
and it "faces" the way it last moved sideways. Condition types
(`FXK.CONDITION_TYPES`, mirrored by `laser/actions.py CONDITION_TYPES`):

| type | fields | met when |
|---|---|---|
| `hp_below` | `pct`, `repeat` | own HP ≤ pct % (once per crossing unless `repeat`) |
| `hp_above` | `pct` | own HP ≥ pct % |
| `self_speed_above` / `self_speed_below` | `px_s` | own speed ≥ / ≤ px_s (averaged over 6 ticks) |
| `target_within` / `target_beyond` | `px` | target closer / further than px |
| `target_between` | `min_px`, `max_px` | target distance inside the band |
| `target_above` / `target_below` | `px` | target at least px higher / lower on screen |
| `target_facing` | `dir` (`toward` / `away`) | target faces this fighter / has its back turned |
| `target_attacking` | — | target dashing / slashing, or playing an `attack*` or `ultimate` action |
| `target_defending` | — | target parrying or playing `defend` |
| `target_hp_below` / `target_hp_above` | `pct` | target HP ≤ / ≥ pct % |
| `target_speed_above` / `target_speed_below` | `px_s` | target speed ≥ / ≤ px_s |
| `attacks_made` | `count` | N attacks made since this action last fired |
| `hits_taken` | `count` | hit N times since this action last fired |
| `damage_taken` | `hp`, `ms` | lost at least hp HP within the last ms |
| `landed_hit` | — | one of this fighter's FX hits connected this tick |
| `hit_by_fx` | `tags` | hit by an enemy FX whose `tag` is listed (empty = any) |
| `fx_near` | `tags`, `px` | an enemy FX with a listed tag comes within px |
| `projectile_count` | `count` | count or more enemy damaging FX / bullets live |
| `bullet_deflected` | — | this character just deflected a bullet |
| `after_actions` | `sequence` | just completed these actions in order (comma separated) |
| `since_action` | `action`, `ms` | `action` ("" = this one) last ended ≥ ms ago, or never played |
| `every_ms` | `ms` | ≥ ms since this action last started (or since the fighter spawned) |
| `idle_for` | `ms` | no attack / triggered action has played for ≥ ms |
| `chance` | `pct_s` | random roll: pct_s % chance per second |

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
- **Character scale (`character_scale`, top level, default 1 = 100 %, 10-200 %).**
  The whole character at that size, in proportion (`laser/characters.py`
  `character_scale`): the game scale (sprite and anchors) is multiplied by it,
  so every FX distance and width follows (`game_px_per_image_px` stays the
  100 % value), and so do its body hit circles (cursor bounce, enemy bullets,
  enemy FX via `partner_scale`), attack range (`basic_attack_radius`), and the
  Tactical retreat / Blink distances (`proximity_px`, re-engage stand-off and
  arrival). Movement and dash speed are unchanged. FX Studio previews it on
  top of `pscale`; FX are still stored at 100 %.
- **FX scale with the figure (`position_scale`).** Every FX distance is
  authored at the figure's base size (FX Studio `pscale` 1) and multiplied by
  the figure's on-screen size, the same factor its sprite, anchors, widths and
  radii use, so a fighter drawn 3x shows its FX as a 3x zoom of what was
  built (`laser/fxkit.py` `host_scale`, `FXK.hostScale`):
  - Placement around the body follows the figure's current size: `offset`,
    entry-set points, orbit `orbit_rx` / `orbit_ry`, path points, beam
    `length` / `jitter`, arc `back` / `lead` / `radius` placement, ribbon
    `min_dist`.
  - What is launched keeps the size it was fired at (`inst.ps`): `motion.speed`
    (travel / homing / zigzag, keyframed speed included), zigzag `amplitude`,
    particle `speed_min` / `speed_max` / `gravity`, intercept `radius` /
    `contact`. A shot fired by a 3x figure moves 3x as far per tick.
  - Widths and radii (ribbon, arc, beam, sprite, particles, glow, weapon) are
    multiplied when drawn and hit-tested, as before.
  The Studio's stage editors (dragging a group, placing entry / path points,
  their guides) convert by the preview `pscale`, so edits made at any pscale
  are stored at base size.

## 3. Effect

```json
{
  "id": "E…", "name": "Blade trail", "tag": "slash", "action": "attack_normal", "enabled": true,
  "prim": "ribbon",
  "start_frame": 0, "end_frame": -1, "life_ticks": 0, "continuous": false, "always_on": false,
  "cycles": {"enabled": false, "count": 0},
  "emit": {"every_ticks": 0, "count": 1, "fan_deg": 0},
  "anchor": "wtip", "offset": [0, 0],
  "motion": {"kind": "attached", "aim": "target", "angle_deg": 0, "aim_offset_deg": 0, "speed": 8,
             "turn_deg": 6, "amplitude": 55, "freq": 0.18, "orbit_rx": 46, "orbit_ry": 46, "orbit_deg": 1.12, "orbit_dir": "clockwise"},
  "color": {"mode": "palette", "lut_index": 128, "lut_index2": 128, "lut_offset": 0, "flow_speed": 0.008,
            "c1": "#ffffff", "c2": "#ff2200", "start_fraction": 0},
  "layer": "front", "blend": "normal",
  "battle": {"deals_damage": false, "damage": 1, "pierce": false, "rehit_ticks": 0, "knockback": 0,
             "blockable": true, "deflectable": true},
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
- `continuous: true` (the Studio's **⟳ Continuous**): the effect plays its
  whole sequence through, exactly as authored, and restricts nothing: start /
  end frame, `emit.every_ticks`, `count`, `fan_deg`, entry sets (sequential
  too), `life_ticks`, keys and any motion all work as usual. Each time the
  action reaches `start_frame` a **run** starts and plays the effect's own
  timeline on its own clock (`stepRun` / `_step_run`): it finishes even if
  the action ends early, changes or restarts, and playing the action again
  starts another run alongside (at most `CYCLE_MAX_RUNS` 8 per effect;
  starting a ninth stops the oldest). A run lasts `start_frame` →
  `end_frame`, or the first copy's `life_ticks` if that is longer; every copy
  lives its own life. Keys that switch the motion (orbit → travel) act on
  every copy made so far.
- `cycles: {enabled, count}` (with `continuous`, `CYCLE_DEFAULTS`
  `{enabled: false, count: 0}`): **loop cycles**: when a run's sequence is
  done it plays again from `start_frame` (keys and emissions replayed, new
  copies). `count` -1 = forever, 0 = once, N = N more times.
- `always_on: true` (the Studio's per-effect **∞ Always on**) makes the
  effect produce without ever stopping or resetting while its action plays,
  loop after loop (an always-on laser trail). From `start_frame` on, one set
  of `emit.count` instances is kept alive with no end: `end_frame`,
  `life_ticks` and `emit.every_ticks` are ignored and it never fades out
  (a glow set to fade `in` fades in once over its window, then holds; size
  and width ramps run once over the window, then hold). A new set starts
  only if the running one ends, e.g. a non-piercing damaging hit consumes it,
  or the action restarts. It ends when the action changes. It applies only
  to effects that stay on the fighter (`attached`, `static` or `orbit`
  motion) and are not `arc`. It is stronger than the action's
  `fx_continuous`, which only carries over effects that already last to the
  end of the action. Files written before `always_on` existed (no
  `always_on` and no `cycles`) had this under `continuous`; they are read as
  `always_on`.

### Motion (`motion.kind`)
| kind | behaviour | engine source |
|---|---|---|
| `attached` | sits on the anchor every tick | trail / held FX |
| `static` | stays where it spawned | bursts |
| `travel` | `speed` px/tick along the aim | `Projectile` |
| `homing` | travel, steering up to `turn_deg`/tick toward the target | `HomingProjectile` |
| `zigzag` | travel plus a lateral sine weave (`amplitude`, `freq`) | `ZigzagProjectile.update` |
| `orbit` | circles the anchor (`orbit_rx`, `orbit_ry`, `orbit_deg`/tick; `orbit_dir` `clockwise`\|`anticlockwise` as seen on screen, Flip mirrors it; a negative `orbit_deg` still reverses it) | petals |
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

### Keyframes (`keys`)
An effect can animate its numbers and custom colours over the action
(`FXK.fxAt`, mirrored by `laser/fxkit.py fx_at`):

```json
"keys": [{"frame": 8,  "ease": "strong_out", "set": {"motion.speed": 100, "color.c1": "#ff8000", "offset.1": -12}},
         {"frame": 14, "ease": "elastic",    "set": {"motion.speed": 40}}]
```

- The effect's own settings are its values at its `start_frame`. Each key
  sets new values for the settings it lists. A setting moves from the
  previous point that set it (the start, or an earlier key) to this key
  along the key's `ease`, and holds after its last key.
- Keyable: every number and every `#rrggbb` colour in `params`, `motion`,
  `emit`, `color`, `battle` and `intercept`, plus `offset.0`, `offset.1` and
  `life_ticks`. Three choices are keyable too (`KEY_CHOICES`): `motion.kind`
  (`attached`, `static`, `orbit`, `travel`, `homing`, `zigzag`), `motion.aim`
  and `motion.orbit_dir`. A choice has no in-between: it holds, then switches
  at its key. Other choices and toggles aren't keyable.
- **Motion switches** (`motionSwitch` / `motion_switch`): when a keyed
  `motion.kind` or `motion.aim` changes, every live instance changes from
  where it is. Into `travel` / `homing` / `zigzag` it launches along its aim
  (with `aim_offset_deg`) at the keyed `speed`; coming off the fighter (from
  `attached` / `static` / `orbit`) it is a shot from then on: it lives
  `life_ticks` from the launch (0 = `LAUNCH_LIFE` 220), and an always-on
  instance stops being always on (its effect makes no new set until the
  action restarts or changes). Into `orbit` it carries on round its anchor at
  the angle it is at (at the orbit's radius); into `attached` / `static` it
  stops. Deflected, lodged and weapon instances never switch.
- `ease` (how the value moves into this key): `linear`, `in`, `out`, `inout`,
  `strong_in`, `strong_out`, `strong_inout` (quartic), `hold` (stays, then
  jumps at the key), `bounce`, `elastic`.
- Live instances sample the effect each tick at their own action time (the
  tick they spawned + their age, in frames at the action's `frame_ms`), so a
  shot already in flight follows the animation. A keyed `motion.speed`
  rescales the velocity of travelling, homing and zigzag shots while keeping
  their direction. A deflected copy freezes at its values when deflected.
- `rescaleEffects` / `rescale_effects` scale keyed distances the same way as
  the base settings.

### Groups (`groups`, `group`) — Studio only

An effect with `"group": "<id>"` belongs to that entry of `groups`. Every
member shares the group's `anchor` (its pivot) and the same `flip` and
`follow_dir` / `follow_each`, and keeps its own `offset` from the pivot, so the group moves
and re-attaches as one rigid piece. Grouping converts each member's spot on
the current frame into an offset from the pivot. Moving the group adds the
same delta to every member's `offset` and offset keys; the group's `offset`
records the total move. Re-attaching sets every member's `anchor` and keeps
the offsets. The saved effects already carry their final `anchor` and
`offset`, so the game ignores `group` / `groups`.

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
| `beam` | `RichBeamProjectile.draw` | `length, w_start0/1, w_end0/1, segments, glow, glow_color, pulse_hz, jitter, detach_ticks, grow_ticks, tip_fade` (`tip_fade`: fraction of the length, from the head, over which the beam fades out; 0 = off; use enough `segments` for a smooth fade) |
| `sprite` | `bullet_sprite` / `bolt_sprite` / `fxkit.blade_sprite` + `Projectile.draw` | `shape orb\|bolt\|blade, radius, stretch, hot, halo, fade, trail_len, glow, glow_size, lodge_ms 1500, blade_orient motion\|angle, blade_angle_deg 90` (glow: outer-glow brightness %, 0 = none, 100 = original; glow_size: its spread %, 100 = 3 × radius). `blade`: a sword of light (`blade_sprite`), `radius` = half-width, length = 2 × `radius` × `stretch` (tip to pommel), tip at the instance position; `blade_orient motion`: it points along its velocity, else along this tick's movement (orbit, attached), else straight down; `angle`: it holds `blade_angle_deg` (Flip mirrors it) (`blade_angle`). It hits along its whole length (tip-to-pommel segment, + half-width). Without pierce, a hit **lodges** it for `lodge_ms` (0 = it ends on the hit): turned up to 10° (seeded rng) off its impact angle, its tip driven toward the point nearest the hurt circle's centre (70–100 % of the way, at most 45 % of the blade deep), it follows the nearest hurt circle (within 200 px × scale), draws only outside the target with normal blending and 35 % glow, fades over its last 300 ms, never hits again and is left out of the opponent's projectile lists (`blade_lodge` / `blade_follow`) |
| `particles` | `BurstParticle` / `_spawn_burst_now` | `mode burst\|stream, count, rate_per_s, angle_deg, spread_deg, speed_min/max (px/s), gravity (px/s²), drag, size_min/max, size_over_life, life_min_ms/max_ms` |
| `glow` | `TrailComponent` head glow + core | `r_start, r_end, a_center, a_mid, mid, core_r, fade none\|out\|in\|inout, pulse_hz` |
| `pulse` | radial pulse rings (new) | `r_start 0, r_end 120, width 6, width_end 2, expand_ms 400, rings 1, gap_ms 200, ease out\|linear\|in, fade out\|none\|in\|inout, glow 8, fill_alpha 0`: ring *k* starts `k × gap_ms` in (only while the effect lasts; `rings 0` = keep starting rings) and grows `r_start → r_end` over `expand_ms`, its line `width → width_end`; `glow` = a soft wider ring, `fill_alpha` = a faint inner fill (both colour 2). Rings already growing finish after the effect's life ends |
| `ghost` | `Figure.draw` afterimages (`silhouette`) | `interval 2, ghost_life 14, alpha 150, max 12` |
| `weapon` | melee hitbox (new) | `to_anchor wtip, width 6`: a capsule from the effect's `anchor` to `to_anchor`, following the frames; never drawn in-game (the Studio outlines it) |

A few rules are FX Kit's own; the engine's classes don't need them:
- A beam that isn't travelling (`attached`, `static`, `orbit`) extends from its
  anchor along the aim over `grow_ticks` and re-aims every tick.
- A straight beam with `segments > 1` (no `jitter`) is drawn as one tapered,
  round-ended capsule filled with a smooth gradient along its length (colour and
  `tip_fade`), so it has no joints, seams or width steps. A jittered or
  single-segment beam strokes each segment with round caps.
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
| `blockable` | `true`: the other fighter's blocks stop it: its `defend` action, special stance, parry stance, and Intercept `block` / `destroy`. `false`: those ignore it and the hit lands. |
| `deflectable` | `true`: the other fighter's deflects knock it away (Intercept `deflect`). `false`: deflects ignore it and the hit lands. |

**Damaged (`damaged`, whole character).** `cooldown_ms`: after a hit takes
HP, the character is invincible (no HP loss, no knockback) until it ends; the
next hit after that takes HP again. `0` = every hit takes HP. It covers every
HP source (bullets, FX, dash-slash, contact, petals, clones), in Solo and
Battle alike (`ai.damage_immune`). A rig-drawn `pb_character` JSON can set the
same top-level `"damaged": {"cooldown_ms": N}` block.

**Tactical retreat (`retreat`, whole character; `laser/retreat.py`).** When
its conditions are met (`logic` any / all) the fighter dashes at `speed_pct` %
of its speed. `angle_deg` is measured from the direction to the target: 0 = at
it, 180 / -180 = straight away, positive = clockwise on screen. `curve_deg_s`
bends the path that many degrees per second. The mode runs during the dash for
its own duration (`-1` = no limit):
- `avoid` (`avoid_duration_ms`): dash along the angle and curve, steering away
  from harm within `proximity_px` (enemy projectiles and the target).
- `reengage` (`reengage_duration_ms`): head for the target's back, the side
  opposite the way it faced when the retreat started, going round its body and
  steering round enemy projectiles within `proximity_px`. With a curve it
  leaves along the angle and swings round at `curve_deg_s`; with 0 it goes
  straight there. On arrival it attacks (melee dash-slash, or an image
  character's `attack_normal`) and the retreat ends.

A new retreat can start `cooldown_ms` after the last one ended. Conditions:
every action trigger condition (section "Conditions" above, each with `not`),
read the same way. Where one means "this action" it means the retreat:
`hp_below` (`pct`, `repeat`: once, or again every cooldown while below),
`attacks_made` / `hits_taken` count from the last retreat start, `every_ms`
times from the last retreat start, and `since_action` with `action ""` from
the last retreat end. `projectile_count` counts enemy projectiles in the air
(shots, not stationary damaging FX). A rig-drawn character without an action
runner gets a condition tracker that counts its dashes / slashes as attacks
and its melee hits as `landed_hit`. The
dash owns the fighter's movement (knockback still wins) and cancels a melee
move in progress, but never an ultimate or special stance. Solo and Battle run
the same code; Solo has no enemy projectiles, and the cursor's back is the far
side from the fighter. A rig-drawn `pb_character` JSON can set the same block
as top-level `"tactical_retreat"`.

`fx` (optional, default `""`): `"fx:<effect id>"` or `"group:<group id>"`.
That effect, or every member of that group, plays for the whole dash
(`laser/fxkit.py` `FxDriver._retreat_tick`) on its own player, as a copy that
starts on the dash's first tick (keys shifted with it) and loops on its
action's timing. FX that can be always on (attached, static, orbit, path; not
arcs) are held for the dash; shots fire at the start of each pass and on their
`emit.every_ticks`. When the dash ends the held FX stop and shots already
flying finish. The original effect still plays on its own action. A missing id
plays nothing.

**Triggered-reaction FX (effect `action`).** Besides an action name, an
effect's `action` can be a reaction key (FX Studio: Actions > Triggered
reactions). These never play on an action of their own:
- `"@retreat"`: built on the run frames (`run`, else `idle`) and played for
  the whole Tactical retreat dash (`FxDriver._retreat_tick`), on their own
  player and clock from the dash's first tick, looping on the run timing with
  continuous FX on. When the dash ends the held FX stop and shots already
  flying finish. They play alongside `retreat.fx`, which keeps its own lane.
- `"@blink:<action>"`: built on `<action>`'s frames and played with that
  action's own FX, on the same clock, while its Blink is `enabled`
  (`CharacterFx.with_blink`). The Blink rules apply to them as to the
  action's own FX: while gone nothing new fires and body-bound FX are hidden.

**Blink (`action_settings[action].blink`, per action; `laser/blink.py`).** A
teleport inside one action; each action has its own. While that action plays,
the fighter vanishes when the frame on show reaches `start_frame` and
reappears once it passes `end_frame` (`-1` = the last frame), or when the
action ends, whichever comes first. A looping action blinks again on every
loop. `cooldown_ms` (0 = none): after the fighter reappears, that action's
Blink stays off this long; the action still plays when it triggers, without
vanishing and without its `@blink:` FX. It reappears `proximity_px` from `anchor`:
- `anchor`: `target` (the target, where it is when the fighter reappears) or
  `self` (the spot the fighter vanished from).
- `direction`: `behind` / `front` (opposite / along the way the target faces;
  Solo and the Studio: the target's far / near side from the fighter),
  `toward` / `away` (along the fighter → target line / the reverse),
  `random`, or `angle` (`angle_deg` from the fighter → target line: 0 =
  toward, 180 = away, positive = clockwise).
- The landing spot is kept 20 px inside the screen.

While gone the fighter is invisible and untouchable (`ai.damage_immune`: no
HP, knockback or body contact; enemy shots and FX pass where it was), doesn't
move, and fires no new FX. Its body-bound FX (`attached` / `orbit` motion,
`weapon`) are hidden and land no hits; shots already in flight carry on. Its
action and animation keep running hidden, so the frames reach `end_frame`.
`flash` adds a crackle and an afterimage at both ends. A blink never starts
during a tactical retreat dash, an ultimate or a special stance, and it
cancels a knockback in progress. Solo and Battle run the same code. The
Studio previews it on the stage: the figure disappears over those frames, a
faint outline marks where it vanished and a ring marks where it lands. (The
older character-wide `pack.blink` block is no longer read.)

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
- `pulse`: each ring hits each target once, when its edge (this tick's and
  last tick's radius, ± half its width) sweeps over the hurt circle, pushing
  outward from the centre. Rings never end on a hit (`pierce` / `rehit_ticks`
  don't apply), and a pulse is never a projectile (no Intercept).
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

## 5c. Intercept (`intercept`) — auto-projectile tracker

Projectiles only (motion `travel`, `homing` or `zigzag`; not weapon or ghost).
FX Studio shows it as the **Intercept** section.

```json
"intercept": {"enabled": false, "radius": 90, "turn_deg": 10, "contact": 10,
              "mode": "block", "deflect_who": "enemy", "hurts_owner": false}
```

| field | meaning |
|---|---|
| `enabled` | **Auto-projectile tracker** on/off. Off: the shot ignores enemy projectiles, as before. |
| `radius` | px. The nearest enemy projectile inside it is chased: the shot steers at it like homing, keeping its speed. |
| `turn_deg` | max turn per tick while chasing. |
| `contact` | px between centres at which the two collide. |
| `mode` | `block`: both are nullified. `deflect`: see below. `destroy`: the enemy projectile is nullified and this one keeps going. |
| `deflect_who` | `enemy`: only the enemy projectile is knocked away and this one carries on. `both`: this one is knocked away too, and then flies straight. |
| `hurts_owner` | deflect only. `true`: the deflected enemy projectile changes sides and can damage the fighter who fired it. `false`: it flies off harmlessly. |

- **Deflect direction** is the combined momentum (the two velocities added).
  Each projectile keeps its own speed. If they meet head-on at similar
  speeds, the sum nearly cancels (under 25% of the faster speed), so the
  enemy projectile is knocked sideways instead, to the side it struck. With
  `both`, the two fly apart ±15° (`DEFLECT_FAN_DEG`).
- **After the chase**, when nothing is left in range, the shot goes back to
  the velocity it had before the chase and carries on with its own motion.
- **Enemy projectiles** are the opponent's real bullets (runner-style,
  `hit_r_sq > 0`) and its travelling damaging FX instances (travel, homing,
  zigzag or path motion; not particles, weapon or ghost).
  `World.refresh_battle` rebuilds them each tick as `fxkit.Shot` in
  `SideState.enemy_shots`, and each Shot carries its live object, so the
  result is applied at the source:
  - bullets are killed with `combat.kill_projectile`;
  - FX instances are ended;
  - a deflect adds a copy on the deflecting side (a `Projectile`, or an FX
    instance with motion `travel`), harmless or damaging per `hurts_owner`.
- Solo has no opponent, so there is nothing to intercept. It is the same
  code path in both modes.
- **Studio preview:** tick **test shots** under the stage. A dummy enemy at
  the target marker fires a shot at the fighter every 40 ticks. Deflected
  shots fly off red (they hurt their owner) or grey (harmless), and every
  contact flashes a ring: gold = block, red = destroy, green = deflect.
- **Parity:** `fxkit.js interceptStep` and `fxkit.py intercept_step` produce
  identical positions and events.

## 5d. Flip (`flip`) and Follow direction (`follow_dir`)

Every effect except the weapon hitbox. FX Studio shows both in the **Flip &
direction** section.

```json
"flip": {"enabled": false, "facing": 1},
"follow_dir": false,
"follow_each": false
```

| field | meaning |
|---|---|
| `flip.enabled` | Off (default): the effect follows the fighter's facing. On: it plays on the side the target is on, mirrored left ↔ right (never up ↔ down) when that side is the other one from `flip.facing`. |
| `flip.facing` | The side the target was on when the effect was created: `1` right, `-1` left. The Studio records it when the effect is added, and the **Created side** dropdown changes it. |
| `follow_dir` | Off (default): no turn. On: the whole effect turns toward the target at any angle. |
| `follow_each` | Independent of `follow_dir`. Off (default): no per-particle turn. On ("Each particle"): every particle stays where it was placed and turns on its own sub-anchor (its own centre) toward the target. |

**Flip**
- The effect's facing (`fxFacing` / `fx_facing`) is the side the target is on
  (target x vs. the figure's x; level = the fighter's facing), whichever way
  the fighter itself faces. Offsets, entry points, paths, particle angles,
  fixed / weapon aims and the arc's `orient "angle"` all mirror with it.
  Anchors are body points and stay where the body puts them.
- On top of that, when the target's side differs from `flip.facing`, flip
  mirrors the arc's sweep (it grows the other way round) and the orbit (its
  side and spin).
- Target-aimed effects still aim at the target. Their up / down (the side of
  its line the arc sits on, the zigzag's first swing, the aim offset and fan)
  never swaps (`turnSign` / `turn_sign`).
- Decided per instance at spawn (`inst.facing`, `inst.flip`, `inst.side`);
  attached and orbiting effects re-read the target's side every tick for
  their position.

**Follow direction**
- As authored the effect points straight forward along its facing. It turns
  by the angle from there to the figure → target line (`bodyDeg` /
  `body_deg`, degrees, applied after mirroring): target above → it turns up.
- With Flip on as well it first mirrors to the target's side, so it only ever
  tilts up / down (at most ±90°). Without Flip a target behind turns it right
  round (upside down).
- Turned by it: the offset, entry points, facing / angle / weapon aims (and
  so held beams and projectiles fired along them), the arc's `orient
  "angle"`, particle angles, the orbit ellipse, and `orient "facing"` paths.
  `orient "aim"` paths already follow the aim.
- Target aims already track the target and are not turned.
- **Each particle** (`follow_each`) works on its own, without `follow_dir`.
  It never turns the offset or entry points (`placeDeg` / `place_deg` turns
  them only with `follow_dir`), so every particle keeps the spot it was
  placed at and a group never swings round its pivot. The effect's own
  direction (aims, arc angle, particle angles, orbit, paths) turns about the
  particle's own centre (`bodyDeg` / `body_deg` is on when either tick is).
  With both ticks on, the spots swing round the anchor and each particle
  also turns on its own sub-anchor.
  Blades (`sprite` shape `blade`) each pivot on their own centre (the middle
  of the blade as authored) so the tip points straight at the target, re-aimed
  every tick (`bladePose` / `blade_pose`, which drawing, hits and lodging all
  use). Lodged and deflected blades keep their own angle.
- Attached and orbiting effects read the angle every tick. Projectiles, arcs
  and particle bursts take it at spawn.

Both are the same code in Solo and Battle. **Parity:** `fxkit.js` and
`fxkit.py` produce identical positions, directions, particle velocities and
arc segments across random effects with both settings on and off. The
exception is a homing shot that passes within a fraction of a pixel of its
target, where float rounding picks the turn.

**Studio stage:** changing the facing dropdown moves a target that's now
behind the fighter to the mirrored spot in front, as in the game, where the
fighter faces its target while it acts.

## 6. Presets

Built-in presets (`studio/presets.js`) rebuild the game's hardcoded effects from
these primitives with their `config.py` numbers: laser trail, blade trail,
crescent slash, through crescent, cone/zigzag bolts, homing orb, rich and held
beams, petal orbs, energy sphere, afterimages and spark burst. Your own presets
are kept in the browser, and **Export**/**Import** moves them as a
`pb_fx_presets` file:

```json
{"format": "pb_fx_presets", "version": 2, "presets": [{"name": "…", "desc": "…", "effects": [ … ]}],
 "geo_presets": [{"kind": "set" | "path", "desc": "…", "item": { … an entry set or path … }}]}
```

A group preset also has `"group": {"name", "anchor", "offset"}` (an object);
adding it makes a new group on the current action with its effects laid out
as saved. In the built-in list `group` is a string, the preset's category,
and never makes a group. `geo_presets` (version 2) carries your entry-set
and path presets; version 1 files have none and still import. Importing a
preset whose name you already have replaces yours.

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
     `basic_attack_radius`, shooters from `max(radius, 420 px)`, or inside the
     attack's own `attack_px` when set (× character scale). Attacks are
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
     - Target state (`target_facing`, `target_attacking`,
       `target_defending`, `target_hp_*`): the nearest enemy, from
       `partner_facing` / `partner_state`, rebuilt each tick by
       `refresh_battle`. Solo: the cursor (no HP, never attacks / defends,
       faces the way it last moved sideways).
     - `landed_hit`: noted by `refresh_battle` when one of this fighter's FX
       hits is delivered (not blocked, not immune).
     - Any condition with `not: true` is inverted. An attack's conditions
       gate it on top of the range check.
   - Attack mode (Alt+Up) gates attacks and triggered actions exactly as it
     gates the built-in fighters. `defend` always works.
8. **Damage is FX only.** For image characters:
   - The loader sets `disable_basic_attack`, `disable_survival_teleport` and
     `ultimate_playback.style: none`.
   - `CombatSystem` skips the melee dash-slash FSM.
   - Their body never deals contact damage, and body contact never costs
     them HP. A landed dash-slash costs them 1 HP, delivered once per hit
     with its knockback (`World.refresh_battle`).
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
