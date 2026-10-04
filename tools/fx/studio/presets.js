/* FX Studio — built-in presets.
 *
 * Each preset rebuilds one of the game's hardcoded effects out of FX Kit
 * primitives, using the constant values from laser/config.py (cited per
 * field), so you start from exactly what the game draws today.  Built-in
 * presets are read-only; "Save as preset" stores your own copies.
 * The engine's built-in characters keep their original effect code — these
 * presets only seed new FX.
 * `group` sorts the preset list; every effect carries its FX `tag` so other
 * characters' defend / deflect triggers can react to it.  The special-ability
 * presets (Fire, Lightning, Shadow, Holy, Ice & wind, Earth & poison, Arcane & cosmic, Energy, Ethereal) use keyframes (fx.keys).
 */
(function (G) {
"use strict";
G.FX_PRESETS = [
  {name: "Laser trail", group: "Trails", desc: "TrailComponent: TRAIL_LEN 50, W 1→5, flow 0.008, glow/dot 1",
   effects: [{prim: "ribbon", name: "Laser trail", tag: "trail", anchor: "figure", offset: [-8, 6],   // TRAIL_BACK / TRAIL_DOWN
     motion: {kind: "attached"}, color: {mode: "palette", flow_speed: 0.008},
     params: {max_points: 50, min_dist: 2, decay: 2, taper: true, w_tail: 1, w_head: 5, alpha: 220, head_glow_r: 1, head_dot_r: 1}}]},
  {name: "Blade trail", group: "Trails", desc: "The laser-trail ribbon pinned to the weapon tip",
   effects: [{prim: "ribbon", name: "Blade trail", tag: "trail", anchor: "wtip", motion: {kind: "attached"},
     color: {mode: "palette", flow_speed: 0.008},
     params: {max_points: 14, min_dist: 2, decay: 3, taper: true, w_tail: 1, w_head: 6, alpha: 220, head_glow_r: 4, head_dot_r: 2}}]},
  {name: "Crescent slash", group: "Slashes", desc: "CrescentWave: R 42, span 170, width 6.5, 5 ticks, 0.4 px/tick, centre 51 px behind the target",
   effects: [{prim: "arc", battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 0, knockback: 0},
     name: "Crescent slash", tag: "slash", anchor: "figure", offset: [0, 0], life_ticks: 5,
     motion: {kind: "travel", aim: "target", speed: 0.4}, color: {mode: "palette", flow_speed: 0.008},
     params: {radius: 42, span: 170, width: 6.5, tail: 0.95, segs: 16, grow: 0.85, core_alpha: 0.7, core_width: 0.3, orient: "motion", placement: "wrap_target", back: 51}}]},
  {name: "Through crescent", group: "Slashes", desc: "Through-slash: starts 26 px short, 10 px/tick, cuts through the target",
   effects: [{prim: "arc", battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 0, knockback: 0},
     name: "Through crescent", tag: "slash", anchor: "figure", life_ticks: 5,
     motion: {kind: "travel", aim: "target", speed: 10}, color: {mode: "palette", flow_speed: 0.008},
     params: {radius: 42, span: 170, width: 6.5, tail: 0.95, segs: 16, grow: 0.85, core_alpha: 0.7, core_width: 0.3, orient: "motion", placement: "through_target", lead: 26}}]},
  {name: "Cone bolt", group: "Shots", desc: "Projectile: PROJ_SPEED 8, radius 3, 220 ticks, 5-point trail",
   effects: [{prim: "sprite", battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0},
     name: "Cone bolt", tag: "bolt", anchor: "haR", life_ticks: 220, emit: {count: 3, fan_deg: 90},   // SHOT_CONE_ANGLES ±45
     motion: {kind: "travel", aim: "target", speed: 8}, color: {mode: "palette", lut_index: 128},
     params: {shape: "bolt", radius: 3, stretch: 1, hot: false, halo: false, fade: true, trail_len: 5}}]},
  {name: "Zigzag bolt", group: "Shots", desc: "ZigzagProjectile: amplitude 55, frequency 0.18, hot streak",
   effects: [{prim: "sprite", battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0},
     name: "Zigzag bolt", tag: "bolt", anchor: "haR", life_ticks: 220, emit: {count: 2},
     motion: {kind: "zigzag", aim: "target", speed: 8, amplitude: 55, freq: 0.18}, color: {mode: "palette", lut_index: 128},
     params: {shape: "bolt", radius: 3, stretch: 1, hot: true, fade: true, trail_len: 5}}]},
  {name: "Homing orb", group: "Shots", desc: "HomingProjectile: 0.5 × PROJ_SPEED with the pulsing halo",
   effects: [{prim: "sprite", battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0},
     name: "Homing orb", tag: "orb", anchor: "haR", life_ticks: 220,
     motion: {kind: "homing", aim: "target", speed: 4, turn_deg: 6}, color: {mode: "palette", lut_index: 128},
     params: {shape: "orb", radius: 3, halo: true, fade: true, trail_len: 5}}]},
  {name: "Rich beam", group: "Beams", desc: "RichBeamProjectile: segmented, glowing, detaches and withers",
   effects: [{prim: "beam", battle: {deals_damage: true, damage: 8, pierce: true, rehit_ticks: 0, knockback: 0},
     name: "Rich beam", tag: "beam", anchor: "haR", life_ticks: 150, blend: "additive",
     motion: {kind: "travel", aim: "target", speed: 12}, color: {mode: "gradient", c1: "#ffffff", c2: "#3fb0ea"},
     params: {length: 260, w_start0: 10, w_start1: 4, w_end0: 4, w_end1: 1, segments: 14, glow: 8, pulse_hz: 6, jitter: 1.5, detach_ticks: 40}}]},
  {name: "Held beam", group: "Beams", desc: "A beam held from the hand, growing along the aim",
   effects: [{prim: "beam", battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 8, knockback: 0},
     name: "Held beam", tag: "beam", anchor: "haR", blend: "additive",
     motion: {kind: "attached", aim: "target"}, color: {mode: "gradient", c1: "#ffffff", c2: "#ff3a3a"},
     params: {length: 320, w_start0: 12, w_start1: 12, w_end0: 6, w_end1: 6, segments: 16, glow: 10, pulse_hz: 8, jitter: 1, grow_ticks: 8}}]},
  {name: "Petal orbs", group: "Orbs & auras", desc: "Petals: 3 orbs, hover 46 px, 70°/s, radius 8, #fbeef3. Lower Glow % / Glow size % for a crisper orb",
   effects: [{prim: "sprite", battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0},
     name: "Petal orbs", tag: "petal", anchor: "figure", emit: {count: 3},
     motion: {kind: "orbit", orbit_rx: 46, orbit_ry: 46, orbit_deg: 1.12},   // 70 deg/s × 0.016 s
     color: {mode: "solid", c1: "#fbeef3"}, params: {shape: "orb", radius: 8, fade: false, trail_len: 0, glow: 100, glow_size: 100}}]},
  {name: "Energy sphere", group: "Orbs & auras", desc: "Radial glow + white core (the trail head, scaled up)",
   effects: [{prim: "glow", name: "Energy sphere", tag: "orb", anchor: "haR", motion: {kind: "attached"},
     color: {mode: "palette", lut_index: 128}, params: {r_start: 6, r_end: 18, a_center: 160, a_mid: 70, mid: 0.4, core_r: 5, fade: "none", pulse_hz: 4}}]},
  {name: "Afterimages", group: "Bursts & afterimages", desc: "Dash ghosts: every 2 ticks, 14-tick fade, alpha 150, crimson",
   effects: [{prim: "ghost", name: "Afterimages", tag: "ghost", anchor: "figure", motion: {kind: "attached"},
     color: {mode: "solid", c1: "#e12837"}, params: {interval: 2, ghost_life: 14, alpha: 150, max: 12}}]},
  {name: "Spark burst", group: "Bursts & afterimages", desc: "BurstParticle swarm: gravity, drag, shrinking sparks",
   effects: [{prim: "particles", name: "Spark burst", tag: "spark", anchor: "wtip", life_ticks: 1, motion: {kind: "static"},
     color: {mode: "gradient", c1: "#ffffff", c2: "#ff6a00"},
     params: {mode: "burst", count: 18, angle_deg: -30, spread_deg: 120, speed_min: 80, speed_max: 260, gravity: 420, drag: 0.94, size_min: 1.5, size_max: 4, size_over_life: "shrink", life_min_ms: 180, life_max_ms: 420}}]},
  {name: "Soft petal orbs", group: "Orbs & auras", desc: "Petal orbs with a dim, tight glow (Glow 35 %, size 60 %)",
   effects: [{prim: "sprite", battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0},
     name: "Soft petal orbs", tag: "petal", anchor: "figure", emit: {count: 3},
     motion: {kind: "orbit", orbit_rx: 46, orbit_ry: 46, orbit_deg: 1.12},
     color: {mode: "solid", c1: "#fbeef3"}, params: {shape: "orb", radius: 6, fade: false, trail_len: 0, glow: 35, glow_size: 60}}]},

  // ---------------------------------------------------------------- special abilities
  // Built from the same primitives; keyframes (fx.keys) animate them.  Key
  // frames are action frames: a shot keeps playing its keys after the action ends.
  {name: "Fireball", group: "Fire", desc: "A blazing orb that accelerates (keyframed speed 3 → 9, ease in) with a rising ember trail",
   effects: [
     {prim: "sprite", name: "Fireball", tag: "fireball", anchor: "haR", life_ticks: 120,
      battle: {deals_damage: true, damage: 2, pierce: false, rehit_ticks: 0, knockback: 6},
      motion: {kind: "travel", aim: "target", speed: 3}, color: {mode: "solid", c1: "#ff7a1a"},
      params: {shape: "orb", radius: 5, fade: false, trail_len: 10, glow: 140, glow_size: 120},
      keys: [{frame: 6, ease: "in", set: {"motion.speed": 9}}]},
     {prim: "particles", name: "Ember trail", tag: "fireball", anchor: "haR", life_ticks: 120,
      motion: {kind: "travel", aim: "target", speed: 3}, color: {mode: "gradient", c1: "#ffd27a", c2: "#ff3300"},
      params: {mode: "stream", rate_per_s: 90, angle_deg: -90, spread_deg: 120, speed_min: 10, speed_max: 45, gravity: -80, drag: 0.95,
               size_min: 1.5, size_max: 3.5, size_over_life: "shrink", life_min_ms: 180, life_max_ms: 420},
      keys: [{frame: 6, ease: "in", set: {"motion.speed": 9}}]}]},
  {name: "Flame slash", group: "Fire", desc: "A fiery crescent that cuts through the target, swelling and thinning as it goes (keyframed radius / width, ease out)",
   effects: [
     {prim: "arc", name: "Flame slash", tag: "flame", anchor: "figure", life_ticks: 9,
      battle: {deals_damage: true, damage: 2, pierce: true, rehit_ticks: 0, knockback: 10},
      motion: {kind: "travel", aim: "target", speed: 9}, color: {mode: "gradient", c1: "#fff1a8", c2: "#ff4000"}, blend: "additive",
      params: {radius: 40, span: 170, width: 11, tail: 0.95, segs: 18, grow: 0.85, core_alpha: 0.8, core_width: 0.35, orient: "motion",
               placement: "through_target", lead: 26},
      keys: [{frame: 3, ease: "out", set: {"params.radius": 56, "params.width": 4, "color.c1": "#ffb35c"}}]},
     {prim: "particles", name: "Flame sparks", tag: "flame", anchor: "figure", life_ticks: 1, motion: {kind: "static"},
      color: {mode: "gradient", c1: "#fff1a8", c2: "#ff4000"},
      params: {mode: "burst", count: 24, angle_deg: 0, spread_deg: 70, speed_min: 90, speed_max: 280, gravity: -40, drag: 0.93,
               size_min: 1.5, size_max: 4, size_over_life: "shrink", life_min_ms: 200, life_max_ms: 450}}]},
  {name: "Eruption", group: "Fire", desc: "Fire bursts up under the target: a swelling heat glow (keyframed, strong ease out) and a fountain of embers",
   effects: [
     {prim: "glow", name: "Eruption heat", tag: "flame", anchor: "target", life_ticks: 40, motion: {kind: "static"},
      battle: {deals_damage: true, damage: 2, pierce: true, rehit_ticks: 12, knockback: 8}, blend: "additive",
      color: {mode: "solid", c1: "#ff6a00"}, params: {r_start: 4, r_end: 4, a_center: 200, a_mid: 90, mid: 0.45, core_r: 3, fade: "out", pulse_hz: 6},
      keys: [{frame: 4, ease: "strong_out", set: {"params.r_start": 26, "params.r_end": 30, "params.core_r": 9}}]},
     {prim: "particles", name: "Eruption embers", tag: "flame", anchor: "target", life_ticks: 36, motion: {kind: "static"},
      color: {mode: "gradient", c1: "#ffe08a", c2: "#ff2a00"},
      params: {mode: "stream", rate_per_s: 160, angle_deg: -90, spread_deg: 28, speed_min: 140, speed_max: 320, gravity: 380, drag: 0.97,
               size_min: 2, size_max: 4.5, size_over_life: "shrink", life_min_ms: 260, life_max_ms: 600}}]},

  {name: "Chain lightning", group: "Lightning", desc: "A crackling bolt that lashes out to full length (keyframed length, strong ease out) and flickers",
   effects: [{prim: "beam", name: "Chain lightning", tag: "lightning", anchor: "haR", life_ticks: 18, blend: "additive",
     battle: {deals_damage: true, damage: 2, pierce: true, rehit_ticks: 6, knockback: 4},
     motion: {kind: "attached", aim: "target"}, color: {mode: "gradient", c1: "#ffffff", c2: "#7fd4ff"},
     params: {length: 40, w_start0: 3, w_start1: 2.5, w_end0: 2, w_end1: 1, segments: 9, glow: 5, glow_color: "#3fa9ff", pulse_hz: 22, jitter: 4},
     keys: [{frame: 2, ease: "strong_out", set: {"params.length": 320}}, {frame: 5, ease: "linear", set: {"params.jitter": 8, "params.glow": 2}}]}]},
  {name: "Thunder strike", group: "Lightning", desc: "Lightning drops onto the target from above, with a flash and a spray of sparks",
   effects: [
     {prim: "beam", name: "Thunder bolt", tag: "lightning", anchor: "target", offset: [0, -260], life_ticks: 14, blend: "additive",
      battle: {deals_damage: true, damage: 3, pierce: true, rehit_ticks: 0, knockback: 12},
      motion: {kind: "static", aim: "angle", angle_deg: 90}, color: {mode: "gradient", c1: "#ffffff", c2: "#a8dcff"},
      params: {length: 270, w_start0: 5, w_start1: 2, w_end0: 3, w_end1: 1, segments: 8, glow: 7, glow_color: "#5ab8ff", pulse_hz: 30, jitter: 6}},
     {prim: "glow", name: "Strike flash", tag: "lightning", anchor: "target", life_ticks: 12, motion: {kind: "static"}, blend: "additive",
      color: {mode: "solid", c1: "#d8f0ff"}, params: {r_start: 6, r_end: 34, a_center: 230, a_mid: 90, mid: 0.4, core_r: 6, fade: "out", pulse_hz: 0}},
     {prim: "particles", name: "Strike sparks", tag: "lightning", anchor: "target", life_ticks: 1, motion: {kind: "static"},
      color: {mode: "gradient", c1: "#ffffff", c2: "#5ab8ff"},
      params: {mode: "burst", count: 26, angle_deg: -90, spread_deg: 200, speed_min: 120, speed_max: 340, gravity: 600, drag: 0.94,
               size_min: 1, size_max: 3, size_over_life: "shrink", life_min_ms: 160, life_max_ms: 380}}]},
  {name: "Spark volley", group: "Lightning", desc: "Three crackling bolts that zigzag at the target, bright white-hot heads",
   effects: [{prim: "sprite", name: "Spark volley", tag: "lightning", anchor: "haR", life_ticks: 140, emit: {count: 3, fan_deg: 36},
     battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0},
     motion: {kind: "zigzag", aim: "target", speed: 9, amplitude: 28, freq: 0.38}, color: {mode: "solid", c1: "#bfe8ff"}, blend: "additive",
     params: {shape: "bolt", radius: 2.5, stretch: 2.4, hot: true, fade: true, trail_len: 8, glow: 150, glow_size: 110}}]},

  {name: "Void orb", group: "Shadow", desc: "A slow homing orb of darkness that swells as it closes in (keyframed size / glow, strong ease in)",
   effects: [{prim: "sprite", name: "Void orb", tag: "void", anchor: "haR", life_ticks: 200,
     battle: {deals_damage: true, damage: 3, pierce: false, rehit_ticks: 0, knockback: 14},
     motion: {kind: "homing", aim: "target", speed: 3, turn_deg: 4}, color: {mode: "solid", c1: "#7a3cff"},
     params: {shape: "orb", radius: 4, halo: true, fade: false, trail_len: 12, glow: 160, glow_size: 130},
     keys: [{frame: 12, ease: "strong_in", set: {"params.radius": 11, "params.glow_size": 190, "color.c1": "#3b0a8f", "motion.speed": 4.5}}]}]},
  {name: "Shadow dash", group: "Shadow", desc: "Dark violet afterimages with a fading shadow trail behind the fighter",
   effects: [
     {prim: "ghost", name: "Shadow images", tag: "shadow", anchor: "figure", layer: "behind", motion: {kind: "attached"},
      color: {mode: "solid", c1: "#3a1466"}, params: {interval: 1, ghost_life: 18, alpha: 170, max: 16}},
     {prim: "ribbon", name: "Shadow trail", tag: "shadow", anchor: "figure", layer: "behind", motion: {kind: "attached"},
      color: {mode: "gradient", c1: "#120020", c2: "#8a4dff"},
      params: {max_points: 30, min_dist: 2, decay: 2, taper: true, w_tail: 1, w_head: 9, alpha: 200, head_glow_r: 3, head_dot_r: 1}}]},
  {name: "Void collapse", group: "Shadow", desc: "Orbs ring the target and spiral inward faster and faster (keyframed orbit radius / spin, strong ease in), then a dark flash",
   effects: [
     {prim: "sprite", name: "Collapsing orbs", tag: "void", anchor: "target", life_ticks: 40, emit: {count: 6},
      battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 10, knockback: 0},
      motion: {kind: "orbit", orbit_rx: 70, orbit_ry: 70, orbit_deg: 3}, color: {mode: "solid", c1: "#9b59ff"},
      params: {shape: "orb", radius: 3.5, fade: false, trail_len: 6, glow: 120, glow_size: 100},
      keys: [{frame: 10, ease: "strong_in", set: {"motion.orbit_rx": 6, "motion.orbit_ry": 6, "motion.orbit_deg": 14}}]},
     {prim: "glow", name: "Collapse flash", tag: "void", anchor: "target", start_frame: 9, life_ticks: 14, motion: {kind: "static"},
      battle: {deals_damage: true, damage: 2, pierce: true, rehit_ticks: 0, knockback: 16},
      color: {mode: "solid", c1: "#5a1fb8"}, params: {r_start: 4, r_end: 40, a_center: 220, a_mid: 100, mid: 0.5, core_r: 0, fade: "out", pulse_hz: 0}}]},

  {name: "Radiant beam", group: "Holy", desc: "A golden beam held from the hand that opens up and brightens (keyframed width / glow, ease out)",
   effects: [{prim: "beam", name: "Radiant beam", tag: "holy", anchor: "haR", blend: "additive",
     battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 6, knockback: 2},
     motion: {kind: "attached", aim: "target"}, color: {mode: "gradient", c1: "#ffffff", c2: "#ffd96a"},
     params: {length: 340, w_start0: 1, w_start1: 1, w_end0: 1, w_end1: 1, segments: 1, glow: 2, glow_color: "#ffe9a8", pulse_hz: 5, jitter: 0, grow_ticks: 8},
     keys: [{frame: 3, ease: "out", set: {"params.w_start0": 7, "params.w_start1": 7, "params.w_end0": 4, "params.w_end1": 4, "params.glow": 7}}]}]},
  {name: "Halo burst", group: "Holy", desc: "A ring of light orbs bursts outward around the fighter (keyframed orbit, elastic) with a golden flare",
   effects: [
     {prim: "sprite", name: "Halo ring", tag: "holy", anchor: "figure", life_ticks: 36, emit: {count: 8},
      battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 12, knockback: 10},
      motion: {kind: "orbit", orbit_rx: 12, orbit_ry: 12, orbit_deg: 4}, color: {mode: "solid", c1: "#ffe08a"},
      params: {shape: "orb", radius: 3, fade: true, trail_len: 4, glow: 90, glow_size: 90},
      keys: [{frame: 6, ease: "elastic", set: {"motion.orbit_rx": 80, "motion.orbit_ry": 80}}]},
     {prim: "glow", name: "Halo flare", tag: "holy", anchor: "figure", life_ticks: 18, motion: {kind: "attached"}, blend: "additive",
      color: {mode: "solid", c1: "#fff3b0"}, params: {r_start: 8, r_end: 64, a_center: 190, a_mid: 70, mid: 0.4, core_r: 8, fade: "out", pulse_hz: 0}},
     {prim: "particles", name: "Halo motes", tag: "holy", anchor: "figure", life_ticks: 1, motion: {kind: "static"},
      color: {mode: "gradient", c1: "#ffffff", c2: "#ffc94a"},
      params: {mode: "burst", count: 36, angle_deg: 0, spread_deg: 360, speed_min: 90, speed_max: 240, gravity: -30, drag: 0.92,
               size_min: 1.5, size_max: 3, size_over_life: "shrink", life_min_ms: 300, life_max_ms: 650}}]},

  {name: "Ice shards", group: "Ice & wind", desc: "A tight volley of five frozen shards, crisp low glow",
   effects: [{prim: "sprite", name: "Ice shards", tag: "ice", anchor: "haR", life_ticks: 90, emit: {count: 5, fan_deg: 24},
     battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 3},
     motion: {kind: "travel", aim: "target", speed: 10}, color: {mode: "solid", c1: "#cfefff"},
     params: {shape: "bolt", radius: 2, stretch: 3, hot: false, fade: false, trail_len: 6, glow: 60, glow_size: 70}}]},
  {name: "Frost nova", group: "Ice & wind", desc: "Shards burst out in every direction from the fighter with an icy flash and frost motes",
   effects: [
     {prim: "sprite", name: "Nova shards", tag: "ice", anchor: "figure", life_ticks: 24, emit: {count: 10, fan_deg: 324},
      battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 0, knockback: 12},
      motion: {kind: "travel", aim: "facing", speed: 3}, color: {mode: "solid", c1: "#e6f8ff"},
      params: {shape: "bolt", radius: 2.2, stretch: 2.6, hot: true, fade: true, trail_len: 5, glow: 80, glow_size: 80},
      keys: [{frame: 3, ease: "strong_out", set: {"motion.speed": 9}}]},
     {prim: "glow", name: "Nova flash", tag: "ice", anchor: "figure", life_ticks: 16, motion: {kind: "attached"}, blend: "additive",
      color: {mode: "solid", c1: "#a8e6ff"}, params: {r_start: 6, r_end: 72, a_center: 170, a_mid: 60, mid: 0.4, core_r: 5, fade: "out", pulse_hz: 0}},
     {prim: "particles", name: "Frost motes", tag: "ice", anchor: "figure", life_ticks: 1, motion: {kind: "static"},
      color: {mode: "gradient", c1: "#ffffff", c2: "#7fd0ff"},
      params: {mode: "burst", count: 30, angle_deg: 0, spread_deg: 360, speed_min: 60, speed_max: 200, gravity: 40, drag: 0.9,
               size_min: 1, size_max: 2.5, size_over_life: "shrink", life_min_ms: 300, life_max_ms: 700}}]},
  {name: "Wind blades", group: "Ice & wind", desc: "Two quick pale-green crescents that cut through the target one after the other",
   effects: [{prim: "arc", name: "Wind blades", tag: "wind", anchor: "figure", start_frame: 0, end_frame: 6, life_ticks: 6, emit: {every_ticks: 5},
     battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 0, knockback: 6}, blend: "additive",
     motion: {kind: "travel", aim: "target", speed: 11}, color: {mode: "gradient", c1: "#f2fff8", c2: "#4fd18b"},
     params: {radius: 34, span: 150, width: 4, tail: 0.9, segs: 16, grow: 0.8, core_alpha: 0.6, core_width: 0.3, orient: "motion",
              placement: "through_target", lead: 20}}]},
  {name: "Cyclone", group: "Ice & wind", desc: "A whirling column on the target: wind streaks spinning in a flat ring while gusts rise, tightening as it spins up",
   effects: [
     {prim: "sprite", name: "Cyclone streaks", tag: "wind", anchor: "target", life_ticks: 60, emit: {count: 8},
      battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 10, knockback: 0},
      motion: {kind: "orbit", orbit_rx: 44, orbit_ry: 12, orbit_deg: 9}, color: {mode: "solid", c1: "#d8fff0"},
      params: {shape: "orb", radius: 2, fade: false, trail_len: 9, glow: 50, glow_size: 80},
      keys: [{frame: 12, ease: "inout", set: {"motion.orbit_rx": 22, "motion.orbit_ry": 6, "motion.orbit_deg": 16}}]},
     {prim: "particles", name: "Cyclone gusts", tag: "wind", anchor: "target", life_ticks: 56, motion: {kind: "static"},
      color: {mode: "gradient", c1: "#ffffff", c2: "#8fe8c0"},
      params: {mode: "stream", rate_per_s: 70, angle_deg: -90, spread_deg: 50, speed_min: 60, speed_max: 160, gravity: -60, drag: 0.96,
               size_min: 1, size_max: 2.5, size_over_life: "shrink", life_min_ms: 250, life_max_ms: 550}}]},

  {name: "Quake", group: "Earth & poison", desc: "The ground bursts under the target: heavy rock chunks fly up and fall back in a dust cloud",
   effects: [
     {prim: "particles", name: "Quake rocks", tag: "earth", anchor: "target", offset: [0, 10], life_ticks: 1, motion: {kind: "static"},
      color: {mode: "gradient", c1: "#c8a070", c2: "#5a3a1e"},
      params: {mode: "burst", count: 28, angle_deg: -90, spread_deg: 130, speed_min: 150, speed_max: 380, gravity: 950, drag: 0.98,
               size_min: 2, size_max: 5, size_over_life: "constant", life_min_ms: 400, life_max_ms: 800}},
     {prim: "glow", name: "Quake dust", tag: "earth", anchor: "target", offset: [0, 10], life_ticks: 30, motion: {kind: "static"},
      battle: {deals_damage: true, damage: 3, pierce: true, rehit_ticks: 0, knockback: 18},
      color: {mode: "solid", c1: "#9a7a55"}, params: {r_start: 8, r_end: 46, a_center: 110, a_mid: 45, mid: 0.5, core_r: 0, fade: "out", pulse_hz: 0}}]},
  {name: "Toxic cloud", group: "Earth & poison", desc: "A lingering green cloud on the target that breathes in and out and bubbles, hurting while it lasts",
   effects: [
     {prim: "glow", name: "Toxic cloud", tag: "poison", anchor: "target", life_ticks: 120, motion: {kind: "static"},
      battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 20, knockback: 0},
      color: {mode: "solid", c1: "#7dff4a"}, params: {r_start: 6, r_end: 30, a_center: 120, a_mid: 55, mid: 0.55, core_r: 0, fade: "none", pulse_hz: 1.5},
      keys: [{frame: 6, ease: "out", set: {"params.r_start": 30, "params.r_end": 36}}]},
     {prim: "particles", name: "Toxic bubbles", tag: "poison", anchor: "target", life_ticks: 110, motion: {kind: "static"},
      color: {mode: "gradient", c1: "#d6ff9a", c2: "#3c8f1a"},
      params: {mode: "stream", rate_per_s: 22, angle_deg: -90, spread_deg: 80, speed_min: 10, speed_max: 40, gravity: -25, drag: 0.98,
               size_min: 1.5, size_max: 3.5, size_over_life: "grow", life_min_ms: 500, life_max_ms: 1000}}]},

  {name: "Arcane missiles", group: "Arcane & cosmic", desc: "Four magenta missiles fan out, then curve in and speed up toward the target",
   effects: [{prim: "sprite", name: "Arcane missiles", tag: "arcane", anchor: "haR", life_ticks: 160, emit: {count: 4, fan_deg: 120},
     battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 2},
     motion: {kind: "homing", aim: "target", speed: 4, turn_deg: 7}, color: {mode: "solid", c1: "#ff5ef2"}, blend: "additive",
     params: {shape: "orb", radius: 2.5, halo: false, fade: false, trail_len: 12, glow: 120, glow_size: 100},
     keys: [{frame: 8, ease: "in", set: {"motion.speed": 9}}]}]},
  {name: "Rune circle", group: "Arcane & cosmic", desc: "A flat ring of runes circles the fighter's feet over a soft blue aura (guards against contact)",
   effects: [
     {prim: "sprite", name: "Rune ring", tag: "arcane", anchor: "figure", offset: [0, 12], emit: {count: 6},
      battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 20, knockback: 6},
      motion: {kind: "orbit", orbit_rx: 34, orbit_ry: 10, orbit_deg: 2.5}, color: {mode: "solid", c1: "#8fd3ff"},
      params: {shape: "orb", radius: 2, fade: false, trail_len: 3, glow: 80, glow_size: 90}},
     {prim: "glow", name: "Rune aura", tag: "arcane", anchor: "figure", offset: [0, 4], motion: {kind: "attached"}, layer: "behind",
      color: {mode: "solid", c1: "#4aa8ff"}, params: {r_start: 22, r_end: 22, a_center: 60, a_mid: 25, mid: 0.5, core_r: 0, fade: "none", pulse_hz: 2}}]},
  {name: "Meteor", group: "Arcane & cosmic", desc: "A burning rock falls from the sky behind the fighter and slams into the target, speeding up as it drops",
   effects: [
     {prim: "sprite", name: "Meteor", tag: "meteor", anchor: "target", offset: [-150, -230], life_ticks: 90,
      battle: {deals_damage: true, damage: 4, pierce: false, rehit_ticks: 0, knockback: 22},
      motion: {kind: "travel", aim: "target", speed: 3}, color: {mode: "solid", c1: "#ff9a3c"},
      params: {shape: "orb", radius: 7, fade: false, trail_len: 14, glow: 150, glow_size: 110},
      keys: [{frame: 10, ease: "strong_in", set: {"motion.speed": 14}}]},
     {prim: "particles", name: "Meteor fire", tag: "meteor", anchor: "target", offset: [-150, -230], life_ticks: 90,
      motion: {kind: "travel", aim: "target", speed: 3}, color: {mode: "gradient", c1: "#ffe08a", c2: "#ff2a00"},
      params: {mode: "stream", rate_per_s: 120, angle_deg: -150, spread_deg: 60, speed_min: 20, speed_max: 70, gravity: -40, drag: 0.94,
               size_min: 2, size_max: 4.5, size_over_life: "shrink", life_min_ms: 200, life_max_ms: 450},
      keys: [{frame: 10, ease: "strong_in", set: {"motion.speed": 14}}]}]},
  {name: "Starfall", group: "Arcane & cosmic", desc: "Little stars rain down around the target in waves",
   effects: [{prim: "sprite", name: "Starfall", tag: "star", anchor: "target", offset: [0, -200], life_ticks: 40, emit: {every_ticks: 6, count: 3, fan_deg: 40},
     battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0}, blend: "additive",
     motion: {kind: "travel", aim: "angle", angle_deg: 90, speed: 7}, color: {mode: "solid", c1: "#fff6c8"},
     params: {shape: "bolt", radius: 1.8, stretch: 2.2, hot: true, fade: true, trail_len: 6, glow: 110, glow_size: 90}}]},

  {name: "Charged laser", group: "Energy", desc: "Energy gathers in the hand (keyframed charge, strong ease in), then a thin piercing laser fires",
   effects: [
     {prim: "glow", name: "Laser charge", tag: "laser", anchor: "haR", start_frame: 0, end_frame: 8, motion: {kind: "attached"}, blend: "additive",
      color: {mode: "solid", c1: "#ff4a6a"}, params: {r_start: 2, r_end: 2, a_center: 220, a_mid: 90, mid: 0.4, core_r: 1, fade: "none", pulse_hz: 10},
      keys: [{frame: 8, ease: "strong_in", set: {"params.r_start": 18, "params.r_end": 18, "params.core_r": 6}}]},
     {prim: "beam", name: "Charged laser", tag: "laser", anchor: "haR", start_frame: 8, life_ticks: 16, blend: "additive",
      battle: {deals_damage: true, damage: 3, pierce: true, rehit_ticks: 0, knockback: 10},
      motion: {kind: "attached", aim: "target"}, color: {mode: "gradient", c1: "#ffffff", c2: "#ff3a5a"},
      params: {length: 420, w_start0: 7, w_start1: 7, w_end0: 4, w_end1: 4, segments: 1, glow: 10, glow_color: "#ff6a80", pulse_hz: 14, jitter: 0, grow_ticks: 3},
      keys: [{frame: 12, ease: "linear", set: {"params.glow": 12}},
             {frame: 18, ease: "strong_in", set: {"params.w_start0": 1, "params.w_start1": 1, "params.w_end0": 0.5, "params.w_end1": 0.5, "params.glow": 1}}]}]},
  // Radiant core: visual only, built for a 30+ frame action.  The core grows from nothing
  // (frames 0-20); once it passes half size (frame 10) the light halo and rays fade in
  // (additive, keyed up from black); frames 24-30 the rays retract into the core.
  // A held beam re-aims every tick (emit fan is not kept), so each ray is its own effect.
  // 10 bright solid rays (tips dim over the last 25%, width set by each ray's 3D depth) over 16 faint
  // rays that fade from core to tip; all spin clockwise at a constant 6 deg/frame (angle keyed to +120 by frame 30).
  {name: "Radiant core", group: "Energy", desc: "Energy charges from nothing into a light source; past half size light rays fade in, then retract into the core (frames 0-30)",
   effects: [
     {prim: "glow", name: "Core charge", tag: "energy", anchor: "figure", start_frame: 0, motion: {kind: "attached"}, blend: "additive",
      color: {mode: "solid", c1: "#8ff2ff"}, params: {r_start: 0, r_end: 0, a_center: 150, a_mid: 60, mid: 0.45, core_r: 0, fade: "none", pulse_hz: 6},
      keys: [{frame: 20, ease: "inout", set: {"params.r_start": 16, "params.r_end": 16, "params.core_r": 5, "params.a_center": 255, "params.a_mid": 120}},
             {frame: 24, ease: "linear", set: {"params.r_start": 16, "params.r_end": 16, "params.core_r": 5}},
             {frame: 30, ease: "strong_in", set: {"params.r_start": 19, "params.r_end": 19, "params.core_r": 7}}]},
     {prim: "glow", name: "Light halo", tag: "energy", anchor: "figure", start_frame: 10, motion: {kind: "attached"}, layer: "behind", blend: "additive",
      color: {mode: "solid", c1: "#000000"}, params: {r_start: 8, r_end: 8, a_center: 200, a_mid: 70, mid: 0.3, core_r: 0, fade: "none", pulse_hz: 0},
      keys: [{frame: 18, ease: "out", set: {"color.c1": "#1aa8d8", "params.r_start": 44, "params.r_end": 44}},
             {frame: 24, ease: "linear", set: {"color.c1": "#1aa8d8", "params.r_start": 44, "params.r_end": 44}},
             {frame: 30, ease: "strong_in", set: {"color.c1": "#0a4a60", "params.r_start": 14, "params.r_end": 14}}]},
     {prim: "particles", name: "Core sparkles", tag: "energy", anchor: "figure", start_frame: 0, motion: {kind: "attached"}, blend: "additive",
      color: {mode: "gradient", c1: "#ffffff", c2: "#3fd8ff"},
      params: {mode: "stream", rate_per_s: 0, angle_deg: 0, spread_deg: 360, speed_min: 20, speed_max: 90, gravity: 0, drag: 0.93,
               size_min: 1.5, size_max: 3.5, size_over_life: "pulse", life_min_ms: 250, life_max_ms: 650},
      keys: [{frame: 20, ease: "in", set: {"params.rate_per_s": 160}},
             {frame: 24, ease: "linear", set: {"params.rate_per_s": 160}},
             {frame: 30, ease: "strong_in", set: {"params.rate_per_s": 0}}]}
   ].concat([[15.9, 82], [23.4, 83], [57.7, 80], [74.2, 83], [102.1, 82], [109.0, 40], [118.0, 84], [154.4, 83],
             [164.5, 79], [197.6, 78], [217.1, 58], [238.3, 78], [276.4, 57], [296.5, 65], [323.4, 81], [343.0, 73]
   ].map(function (r, i) {   // faint inner rays: [angle deg, length px], fade from core to tip
     var deg = r[0], len = r[1], w = 2.4 + 1.4 * len / 84, wt = w * 1.18;
     return {prim: "beam", name: "Faint ray " + (i + 1), tag: "light", anchor: "figure", start_frame: 10, life_ticks: 120, blend: "additive",
       motion: {kind: "attached", aim: "angle", angle_deg: deg}, color: {mode: "gradient", c1: "#000000", c2: "#000000"},
       params: {length: len, w_start0: w, w_start1: w, w_end0: wt, w_end1: wt, segments: 2, glow: 3, glow_color: "", pulse_hz: 0, jitter: 0, grow_ticks: 0, tip_fade: 0},
       keys: [{frame: 16 + (i % 3), ease: "out", set: {"color.c1": "#3f8896", "color.c2": "#000000"}},
              {frame: 24, ease: "linear", set: {"params.length": len}},
              {frame: 30, ease: "strong_in", set: {"params.length": 0}},
              {frame: 30, ease: "linear", set: {"motion.angle_deg": deg + 120}}]};   // constant clockwise spin
   })).concat([[24.3, 164, 1.08], [26.2, 117, 0.4], [92.6, 111, 0.35], [104.1, 165, 1.09], [166.2, 126, 2.14],
             [231.0, 145, 0.76], [235.6, 137, 2.1], [303.1, 99, 0.35], [330.3, 171, 1.23], [357.3, 122, 2.15]
   ].map(function (r, i) {   // bright rays: [angle deg, length px, tip/base width] from a random 3D direction:
     // leaning toward the viewer widens the tip (wedge), leaning into the background narrows it
     var deg = r[0], len = r[1], w = 5, wt = w * r[2];
     return {prim: "beam", name: "Bright ray " + (i + 1), tag: "light", anchor: "figure", start_frame: 10, life_ticks: 120, blend: "additive",
       motion: {kind: "attached", aim: "angle", angle_deg: deg}, color: {mode: "solid", c1: "#000000"},
       params: {length: len, w_start0: w, w_start1: w, w_end0: wt, w_end1: wt, segments: 2, glow: 0, glow_color: "", pulse_hz: 0, jitter: 0, grow_ticks: 0,
                tip_fade: 0.25},   // solid, dimming over the last 25% of its length
       keys: [{frame: 15 + (i % 3), ease: "out", set: {"color.c1": "#c4ffff"}},
              {frame: 24, ease: "linear", set: {"params.length": len}},
              {frame: 30, ease: "strong_in", set: {"params.length": 0}},
              {frame: 30, ease: "linear", set: {"motion.angle_deg": deg + 120}}]};   // constant clockwise spin
   }))},

  // ---------------------------------------------------------------- Ethereal
  // Ethereal blade: one sword of light (sprite shape "blade"), standing still
  // above the fighter, visual only.  Set its count, motion, anchor and damage
  // yourself; without Pierce a damaging blade lodges in what it hits.
  {name: "Ethereal blade", group: "Ethereal", desc: "One sword of light (sprite shape blade), still and visual only: the building block for your own blade FX",
   effects: [{prim: "sprite", name: "Ethereal blade", tag: "blade", anchor: "figure", offset: [0, -34], motion: {kind: "static"}, blend: "additive",
     color: {mode: "solid", c1: "#a9c1ff"},
     params: {shape: "blade", radius: 2.2, stretch: 9, hot: true, halo: false, fade: false, trail_len: 0, glow: 100, glow_size: 90,
              lodge_ms: 1500, blade_orient: "motion", blade_angle_deg: 90}}]},
  // Ethereal blades, built for a 30-frame action.  After Ye Shunguang's sword
  // formation (Zenless Zone Zero) and Byakuya's Senkei (Bleach):
  //   0-12  six swords rise above the fighter, points up, slowly turning;
  //   0-26  three rows of upright swords close in round the target and
  //         circle it, each row the other way (visual only);
  //   10-22 swords rain on the target down six converging lanes and lodge
  //         in it (no pierce);
  //   22-   a giant blade drops on the target and lodges, with a light-blade
  //         sweep, a flash and shards.
  {name: "Ethereal blades", group: "Ethereal", desc: "A sword formation: six swords rise over the fighter, three rows of swords close in round the target, a rain of swords lodges in it, then a giant blade drops (frames 0-30)",
   effects: [
     {prim: "glow", name: "Ethereal aura", tag: "blade", anchor: "figure", start_frame: 0, end_frame: 24, motion: {kind: "attached"}, layer: "behind", blend: "additive",
      color: {mode: "solid", c1: "#4f6dff"}, params: {r_start: 24, r_end: 28, a_center: 80, a_mid: 34, mid: 0.45, core_r: 0, fade: "none", pulse_hz: 2}},
     {prim: "sprite", name: "Summoned swords", tag: "blade", anchor: "figure", offset: [0, -40], start_frame: 0, end_frame: 12, emit: {count: 6}, blend: "additive",
      motion: {kind: "orbit", orbit_rx: 18, orbit_ry: 5, orbit_deg: 1.5}, color: {mode: "solid", c1: "#b8ccff"},
      params: {shape: "blade", radius: 1.8, stretch: 8, hot: true, halo: false, fade: false, trail_len: 0, glow: 100, glow_size: 90,
               lodge_ms: 0, blade_orient: "angle", blade_angle_deg: -90},
      keys: [{frame: 6, ease: "out", set: {"motion.orbit_rx": 26, "motion.orbit_ry": 7}}]}
   ].concat([[-8, 1.1], [-30, -0.9], [-52, 0.7]].map(function (row, i) {
     return {prim: "sprite", name: "Sword ring " + (i + 1), tag: "blade", anchor: "target", offset: [0, row[0]], start_frame: 0, end_frame: 26,
       emit: {count: 14}, blend: "additive",
       motion: {kind: "orbit", orbit_rx: 120, orbit_ry: 26, orbit_deg: row[1]}, color: {mode: "solid", c1: i === 1 ? "#c9d6ff" : "#9fb6ff"},
       params: {shape: "blade", radius: 1.6, stretch: 8, hot: false, halo: false, fade: false, trail_len: 0, glow: 80, glow_size: 80,
                lodge_ms: 0, blade_orient: "angle", blade_angle_deg: 90},
       keys: [{frame: 8, ease: "strong_out", set: {"motion.orbit_rx": 64, "motion.orbit_ry": 16}}]};
   })).concat([[-70, -240, 74, 10, 8], [-30, -250, 83, 12, 7], [0, -260, 90, 11, 9], [12, -230, 93, 13, 8], [30, -250, 97, 10, 10], [70, -240, 106, 12, 9]].map(function (c, i) {
     // [x, y, angle, start frame, every ticks]: six lanes converging on the target from above
     return {prim: "sprite", name: "Sword rain " + (i + 1), tag: "blade", anchor: "target", offset: [c[0], c[1]],
       start_frame: c[3], end_frame: 22, life_ticks: 40, emit: {every_ticks: c[4], count: 1},
       battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 1}, blend: "additive",
       motion: {kind: "travel", aim: "angle", angle_deg: c[2], speed: 8}, color: {mode: "solid", c1: "#c4d3ff"},
       params: {shape: "blade", radius: 1.5, stretch: 10, hot: true, halo: false, fade: false, trail_len: 4, glow: 100, glow_size: 85,
                lodge_ms: 1500, blade_orient: "motion", blade_angle_deg: 90},
       keys: [{frame: 16, ease: "strong_in", set: {"motion.speed": 14}}]};
   })).concat([
     {prim: "sprite", name: "Heaven-cleaving blade", tag: "blade", anchor: "target", offset: [0, -280], start_frame: 22, life_ticks: 60,
      battle: {deals_damage: true, damage: 4, pierce: false, rehit_ticks: 0, knockback: 16}, blend: "additive",
      motion: {kind: "travel", aim: "angle", angle_deg: 90, speed: 6}, color: {mode: "solid", c1: "#d4e0ff"},
      params: {shape: "blade", radius: 5, stretch: 14, hot: true, halo: false, fade: false, trail_len: 6, glow: 120, glow_size: 100,
               lodge_ms: 1800, blade_orient: "motion", blade_angle_deg: 90},
      keys: [{frame: 24, ease: "strong_in", set: {"motion.speed": 22}}]},
     {prim: "arc", name: "Spectral sweep", tag: "blade", anchor: "figure", start_frame: 22, life_ticks: 12, blend: "additive",
      battle: {deals_damage: true, damage: 2, pierce: true, rehit_ticks: 0, knockback: 10},
      motion: {kind: "travel", aim: "target", speed: 9}, color: {mode: "gradient", c1: "#ffffff", c2: "#6c8bff"},
      params: {radius: 64, span: 200, width: 9, tail: 0.95, segs: 24, grow: 0.8, core_alpha: 0.85, core_width: 0.35, orient: "motion",
               placement: "through_target", lead: 30},
      keys: [{frame: 25, ease: "out", set: {"params.radius": 84, "params.width": 3}}]},
     {prim: "glow", name: "Impact flash", tag: "blade", anchor: "target", start_frame: 25, life_ticks: 18, motion: {kind: "static"}, blend: "additive",
      color: {mode: "solid", c1: "#9fb6ff"}, params: {r_start: 10, r_end: 60, a_center: 220, a_mid: 90, mid: 0.35, core_r: 8, fade: "out", pulse_hz: 0}},
     {prim: "particles", name: "Blade shards", tag: "blade", anchor: "target", start_frame: 25, life_ticks: 1, motion: {kind: "static"},
      color: {mode: "gradient", c1: "#ffffff", c2: "#6c8bff"},
      params: {mode: "burst", count: 40, angle_deg: -90, spread_deg: 200, speed_min: 80, speed_max: 320, gravity: 260, drag: 0.93,
               size_min: 1, size_max: 2.5, size_over_life: "shrink", life_min_ms: 250, life_max_ms: 700}}
   ])}
];
// Built-in entry-set and path presets (Paths & entry points panel).  kind
// "set" items are entry sets, "path" items paths, in the shapes
// FXK.normalizeEntrySet / FXK.normalizePath read; points are game px, x forward.
G.GEO_PRESETS = [
  {kind: "set", desc: "Three points in an arc above the head, firing together.",
    item: {name: "Halo of 3", base: "figure", mode: "simultaneous", interval_ticks: 6, points: [[-16, -44], [0, -50], [16, -44]]}},
  {kind: "set", desc: "Three points behind the back, firing one after another.",
    item: {name: "Back row of 3", base: "figure", mode: "sequential", interval_ticks: 6, points: [[-22, -36], [-30, -18], [-22, 0]]}},
  {kind: "set", desc: "One point each side of the body, firing together.",
    item: {name: "Both sides", base: "figure", mode: "simultaneous", interval_ticks: 6, points: [[-26, -20], [26, -20]]}},
  {kind: "set", desc: "Six points in a ring around the fighter, firing in turn.",
    item: {name: "Ring of 6", base: "figure", mode: "sequential", interval_ticks: 4,
      points: [0, 1, 2, 3, 4, 5].map(function (i) { var a = i * Math.PI / 3 - Math.PI / 2; return [Math.round(Math.cos(a) * 34), Math.round(Math.sin(a) * 34 - 16)]; })}},
  {kind: "set", desc: "A column of four points in front of the body, firing top to bottom.",
    item: {name: "Front column of 4", base: "figure", mode: "sequential", interval_ticks: 5, points: [[16, -42], [18, -28], [18, -14], [16, 0]]}},
  {kind: "path", desc: "Straight ahead, turned toward the aim, and keeps going.",
    item: {name: "Straight", points: [[0, 0], [120, 0]], smooth: false, ticks: 20, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "Lobs up and over toward the aim, then keeps going.",
    item: {name: "Arc over", points: [[0, 0], [50, -40], [100, 0]], smooth: true, ticks: 24, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "Dips under toward the aim, then keeps going.",
    item: {name: "Arc under", points: [[0, 0], [50, 40], [100, 0]], smooth: true, ticks: 24, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "Weaves once each way on its way to the aim.",
    item: {name: "S-curve", points: [[0, 0], [30, -25], [60, 0], [90, 25], [120, 0]], smooth: true, ticks: 28, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "A tight wave toward the aim.",
    item: {name: "Sine wave", points: [0, 1, 2, 3, 4, 5, 6, 7, 8].map(function (i) { return [i * 20, i % 2 ? (i % 4 === 1 ? -14 : 14) : 0]; }), smooth: true, ticks: 36, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "A loop-the-loop, then on toward the aim.",
    item: {name: "Loop", points: [[0, 0], [40, 0], [62, -20], [40, -42], [18, -20], [40, 0], [110, 0]], smooth: true, ticks: 36, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "Out and back to the fighter, like a boomerang.",
    item: {name: "Boomerang", points: [[0, 0], [60, -18], [100, 0], [60, 18], [0, 0]], smooth: true, ticks: 40, orient: "aim", end: "stop", follow: true}},
  {kind: "path", desc: "Rises straight up above the fighter.",
    item: {name: "Rise up", points: [[0, 0], [0, -80]], smooth: false, ticks: 30, orient: "facing", end: "stop", follow: false}},
  {kind: "path", desc: "Spirals outward from where it starts.",
    item: {name: "Spiral out", points: (function () { var o = []; for (var i = 0; i <= 16; i++) { var a = i * Math.PI / 4, r = 3 + i * 3; o.push([Math.round(Math.cos(a) * r - 3), Math.round(Math.sin(a) * r)]); } o[0] = [0, 0]; return o; })(),
      smooth: true, ticks: 48, orient: "facing", end: "stop", follow: false}},
  {kind: "path", desc: "Circles the fighter again and again (use with ∞ Continuous).",
    item: {name: "Circle around", points: (function () { var o = []; for (var i = 0; i <= 12; i++) { var a = i * Math.PI / 6; o.push([Math.round(30 - Math.cos(a) * 30), Math.round(-Math.sin(a) * 30)]); } o[0] = [0, 0]; return o; })(),
      smooth: true, ticks: 60, orient: "facing", end: "loop", follow: true}}
];
})(window);
