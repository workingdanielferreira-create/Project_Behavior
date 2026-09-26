# FX Kit — `pb_fxkit` v1 specification

The FX format written by **FX Studio** (`tools/fx/studio/fx_studio.html`), the
second phase of character creation:

```
Rig Forge (rigforge.html)  ──pb_character──►  FX Studio  ──pb_fxkit──►  game (laser/)
  pose + animate the rig                       build FX around each action
```

The runtime reference is `tools/fx/studio/fxkit.js`. The engine port
(`laser/fxkit.py`, Phase 2) mirrors that file function for function. If this
document and `fxkit.js` ever disagree, `fxkit.js` is correct and this file must
be fixed.

---

## 1. Where the block lives

The Studio exports it in two ways, and both hold the same block:

| Export | File | Shape |
|---|---|---|
| **Export character + FX** | `<name>.json` | the imported Rig Forge `pb_character`, unchanged, plus a top-level `fx_studio` key holding the block |
| **Export FX pack** | `<name>.fxkit.json` | the block on its own (`"format": "pb_fxkit"`) |

The FX pack is self-contained: it carries its own joint table, so it doesn't
need the baked character file next to it to resolve anchors.

```json
{
  "format": "pb_fxkit", "version": 1, "tick_ms": 16, "character": "ReverseSwordman",
  "space": {
    "coords": "game px, y down, relative to the figure position; x mirrors when facing left",
    "joints": "joint_track values are rig units relative to the bake origin (hip x = 0, idle bbox centre y), rx zeroed",
    "origin_rig": [0, -6.36], "target_head_px": 16, "head_units": 29, "px_per_unit": 0.551724
  },
  "palette_lut": {"built_from": ["palette.body", "palette.accent"], "rule": "palette.build_lut([body, accent])"},
  "joint_track": { "<action>": { "duration_ms": 2400, "frames": [ { "haR": [x, y], "wtip": [x, y], "...": [], "wang": 90.0 } ],
                                 "root_rx": [], "root_ry": [] } },
  "effects": [ { "...": "section 3" } ]
}
```

## 2. Space and time

- **Tick.** Everything advances once per 16 ms tick (`config.TICK_MS`). Nothing
  reads wall-clock time.
- **Action clock.** Each action's frames play at `frame_ms = duration_ms / frames`,
  which is the clock Rig Forge animates on. Frame `f` begins at tick
  `round(f * frame_ms / 16)`.
- **Coordinates.** Game px, y down. `(0, 0)` is the figure position, which is the
  centre of the baked sprite, i.e. the bake origin. x is mirrored when the figure
  faces left.
- **Joints.** `joint_track[action].frames[f][joint]` is in rig units relative to
  the bake origin, with `rx` zeroed (the engine moves the figure itself).
  It converts to game px like this:

  `px = joint * px_per_unit * position_scale`, where `px_per_unit = TARGET_HEAD_PX / head_units`

  `head_units` is the baked head diameter per rig unit (`2*head + 1`, i.e. 29 for
  head 14). That's the same number `sprite_files.<set>.src_head_px` holds at
  `px_per_unit 1`, so joints and sprite pixels share one scale.
- **Identical tables.** `rigforge_bake.py` writes the same table into
  `bake_manifest.json` (`actions.<name>.joints`), and `--joints-only` writes it
  without rendering. The Studio's JavaScript table and the bake's Python table
  have been checked equal (6,900 values, max difference 0.0000 for
  ReverseSwordman).
- **Anchors.** `figure` (sprite centre), `target`, and the Rig Forge joints
  `hip chest neck head shB shL shR elL elR haL haR hpL hpR knL knR ftL ftR wtip root`
  (the `L` joints are the far limb, the `R` joints the near limb).

## 3. Effect

```json
{
  "id": "E…", "name": "Blade trail", "action": "attack_normal", "enabled": true,
  "prim": "ribbon",
  "start_frame": 0, "end_frame": -1, "life_ticks": 0,
  "emit": {"every_ticks": 0, "count": 1, "fan_deg": 0},
  "anchor": "wtip", "offset": [0, 0],
  "motion": {"kind": "attached", "aim": "target", "angle_deg": 0, "aim_offset_deg": 0, "speed": 8,
             "turn_deg": 6, "amplitude": 55, "freq": 0.18, "orbit_rx": 46, "orbit_ry": 46, "orbit_deg": 1.12},
  "color": {"mode": "palette", "lut_index": 128, "lut_index2": 128, "lut_offset": 0, "flow_speed": 0.008,
            "c1": "#ffffff", "c2": "#ff2200", "start_fraction": 0},
  "layer": "front", "blend": "normal",
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
| `arc` | `CrescentWave.draw` | `radius 42, span 170, width 6.5, tail 0.95, segs 16, grow 0.85, core_alpha 0.7, core_width 0.3, orient motion\|angle, angle_deg` |
| `beam` | `RichBeamProjectile.draw` | `length, w_start0/1, w_end0/1, segments, glow, glow_color, pulse_hz, jitter, detach_ticks, grow_ticks` |
| `sprite` | `bullet_sprite` / `bolt_sprite` + `Projectile.draw` | `shape orb\|bolt, radius, stretch, hot, halo, fade, trail_len` |
| `particles` | `BurstParticle` / `_spawn_burst_now` | `mode burst\|stream, count, rate_per_s, angle_deg, spread_deg, speed_min/max (px/s), gravity (px/s²), drag, size_min/max, size_over_life, life_min_ms/max_ms` |
| `glow` | `TrailComponent` head glow + core | `r_start, r_end, a_center, a_mid, mid, core_r, fade none\|out\|in\|inout, pulse_hz` |
| `ghost` | `Figure.draw` afterimages (`silhouette`) | `interval 2, ghost_life 14, alpha 150, max 12` |

A few rules are FX Kit's own; the engine's classes don't need them:
- A beam that isn't travelling (`attached`, `static`, `orbit`) extends from its
  anchor along the aim over `grow_ticks` and re-aims every tick.
- `particles` values are in game px directly. The old `fx_layers` path
  multiplied by a canvas-to-game scale; FX Kit does not.
- `blend: additive` maps to `QPainter.CompositionMode_Plus` in Qt and
  `lighter` in the canvas.
- `layer: behind | front` places the effect before or after the figure sprite.

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

## 7. Phase 2 — engine integration checklist

The engine does **not** read `fx_studio` / `pb_fxkit` yet. To make it play
exactly as in the Studio, Phase 2 must:

1. **Port the runtime.** Create `laser/fxkit.py`, a line-for-line port of
   `fxkit.js`: mulberry32, `build_lut`, `spawn`, `move`, `tick`, and the seven
   draw routines with QPainter. It must be one self-drawing object per instance
   (FX_GUIDE Pattern A).
2. **Load the block.** Load `fx_studio` from the character JSON, or
   `characters/<name>.fxkit.json`, in `characters.load_all`, and keep it on
   `mode.character`.
3. **Resolve joints.** Resolve anchors from `joint_track` on the current frame,
   using `px_per_unit` from the character's own `sprite_files.src_head_px`.
   Warn if that differs from the exported `head_units`.
4. **Play on the Rig Forge clock.** Play the action frames at
   `duration_ms / frames`. Today a baked character's in-game frame sets are a
   subset of the Rig Forge frames (e.g. ReverseSwordman `slash` = 5 of 42), so
   the displayed frame must map back to its source keyframe (the
   `rigforge_bake.frame_map`), or FX drift off the animation.
5. **Start effects on action start.** Start an action's effects when that
   action starts in the combat FSM, identically in Solo and Battle. All of this
   is cosmetic and local, so nothing crosses the IPC boundary.
6. **Parity test.** Render one FX pack in headless Chromium (`fxkit.js`) and in
   offscreen Qt (`fxkit.py`) at fixed ticks, and diff the frames with a
   tolerance for antialiasing.
