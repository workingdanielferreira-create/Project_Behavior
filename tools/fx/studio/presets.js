/* FX Studio — built-in presets.
 *
 * Each preset rebuilds one of the game's hardcoded effects out of FX Kit
 * primitives, using the constant values from laser/config.py (cited per
 * field), so you start from exactly what the game draws today.  Built-in
 * presets are read-only; "Save as preset" stores your own copies.
 * The engine's built-in characters keep their original effect code — these
 * presets only seed new FX.
 */
(function (G) {
"use strict";
G.FX_PRESETS = [
  {name: "Laser trail", desc: "TrailComponent: TRAIL_LEN 50, W 1→5, flow 0.008, glow/dot 1",
   effects: [{prim: "ribbon", name: "Laser trail", anchor: "figure", offset: [-8, 6],   // TRAIL_BACK / TRAIL_DOWN
     motion: {kind: "attached"}, color: {mode: "palette", flow_speed: 0.008},
     params: {max_points: 50, min_dist: 2, decay: 2, taper: true, w_tail: 1, w_head: 5, alpha: 220, head_glow_r: 1, head_dot_r: 1}}]},
  {name: "Blade trail", desc: "The laser-trail ribbon pinned to the weapon tip",
   effects: [{prim: "ribbon", name: "Blade trail", anchor: "wtip", motion: {kind: "attached"},
     color: {mode: "palette", flow_speed: 0.008},
     params: {max_points: 14, min_dist: 2, decay: 3, taper: true, w_tail: 1, w_head: 6, alpha: 220, head_glow_r: 4, head_dot_r: 2}}]},
  {name: "Crescent slash", desc: "CrescentWave: R 42, span 170, width 6.5, 5 ticks, 0.4 px/tick, centre 51 px behind the target",
   effects: [{prim: "arc", battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 0, knockback: 0},
     name: "Crescent slash", anchor: "figure", offset: [0, 0], life_ticks: 5,
     motion: {kind: "travel", aim: "target", speed: 0.4}, color: {mode: "palette", flow_speed: 0.008},
     params: {radius: 42, span: 170, width: 6.5, tail: 0.95, segs: 16, grow: 0.85, core_alpha: 0.7, core_width: 0.3, orient: "motion", placement: "wrap_target", back: 51}}]},
  {name: "Through crescent", desc: "Through-slash: starts 26 px short, 10 px/tick, cuts through the target",
   effects: [{prim: "arc", battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 0, knockback: 0},
     name: "Through crescent", anchor: "figure", life_ticks: 5,
     motion: {kind: "travel", aim: "target", speed: 10}, color: {mode: "palette", flow_speed: 0.008},
     params: {radius: 42, span: 170, width: 6.5, tail: 0.95, segs: 16, grow: 0.85, core_alpha: 0.7, core_width: 0.3, orient: "motion", placement: "through_target", lead: 26}}]},
  {name: "Cone bolt", desc: "Projectile: PROJ_SPEED 8, radius 3, 220 ticks, 5-point trail",
   effects: [{prim: "sprite", battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0},
     name: "Cone bolt", anchor: "haR", life_ticks: 220, emit: {count: 3, fan_deg: 90},   // SHOT_CONE_ANGLES ±45
     motion: {kind: "travel", aim: "target", speed: 8}, color: {mode: "palette", lut_index: 128},
     params: {shape: "bolt", radius: 3, stretch: 1, hot: false, halo: false, fade: true, trail_len: 5}}]},
  {name: "Zigzag bolt", desc: "ZigzagProjectile: amplitude 55, frequency 0.18, hot streak",
   effects: [{prim: "sprite", battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0},
     name: "Zigzag bolt", anchor: "haR", life_ticks: 220, emit: {count: 2},
     motion: {kind: "zigzag", aim: "target", speed: 8, amplitude: 55, freq: 0.18}, color: {mode: "palette", lut_index: 128},
     params: {shape: "bolt", radius: 3, stretch: 1, hot: true, fade: true, trail_len: 5}}]},
  {name: "Homing orb", desc: "HomingProjectile: 0.5 × PROJ_SPEED with the pulsing halo",
   effects: [{prim: "sprite", battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0},
     name: "Homing orb", anchor: "haR", life_ticks: 220,
     motion: {kind: "homing", aim: "target", speed: 4, turn_deg: 6}, color: {mode: "palette", lut_index: 128},
     params: {shape: "orb", radius: 3, halo: true, fade: true, trail_len: 5}}]},
  {name: "Rich beam", desc: "RichBeamProjectile: segmented, glowing, detaches and withers",
   effects: [{prim: "beam", battle: {deals_damage: true, damage: 8, pierce: true, rehit_ticks: 0, knockback: 0},
     name: "Rich beam", anchor: "haR", life_ticks: 150, blend: "additive",
     motion: {kind: "travel", aim: "target", speed: 12}, color: {mode: "gradient", c1: "#ffffff", c2: "#3fb0ea"},
     params: {length: 260, w_start0: 10, w_start1: 4, w_end0: 4, w_end1: 1, segments: 14, glow: 8, pulse_hz: 6, jitter: 1.5, detach_ticks: 40}}]},
  {name: "Held beam", desc: "A beam held from the hand, growing along the aim",
   effects: [{prim: "beam", battle: {deals_damage: true, damage: 1, pierce: true, rehit_ticks: 8, knockback: 0},
     name: "Held beam", anchor: "haR", blend: "additive",
     motion: {kind: "attached", aim: "target"}, color: {mode: "gradient", c1: "#ffffff", c2: "#ff3a3a"},
     params: {length: 320, w_start0: 12, w_start1: 12, w_end0: 6, w_end1: 6, segments: 16, glow: 10, pulse_hz: 8, jitter: 1, grow_ticks: 8}}]},
  {name: "Petal orbs", desc: "Petals: 3 orbs, hover 46 px, 70°/s, radius 8, #fbeef3",
   effects: [{prim: "sprite", battle: {deals_damage: true, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0},
     name: "Petal orbs", anchor: "figure", emit: {count: 3},
     motion: {kind: "orbit", orbit_rx: 46, orbit_ry: 46, orbit_deg: 1.12},   // 70 deg/s × 0.016 s
     color: {mode: "solid", c1: "#fbeef3"}, params: {shape: "orb", radius: 8, fade: false, trail_len: 0}}]},
  {name: "Energy sphere", desc: "Radial glow + white core (the trail head, scaled up)",
   effects: [{prim: "glow", name: "Energy sphere", anchor: "haR", motion: {kind: "attached"},
     color: {mode: "palette", lut_index: 128}, params: {r_start: 6, r_end: 18, a_center: 160, a_mid: 70, mid: 0.4, core_r: 5, fade: "none", pulse_hz: 4}}]},
  {name: "Afterimages", desc: "Dash ghosts: every 2 ticks, 14-tick fade, alpha 150, crimson",
   effects: [{prim: "ghost", name: "Afterimages", anchor: "figure", motion: {kind: "attached"},
     color: {mode: "solid", c1: "#e12837"}, params: {interval: 2, ghost_life: 14, alpha: 150, max: 12}}]},
  {name: "Spark burst", desc: "BurstParticle swarm: gravity, drag, shrinking sparks",
   effects: [{prim: "particles", name: "Spark burst", anchor: "wtip", life_ticks: 1, motion: {kind: "static"},
     color: {mode: "gradient", c1: "#ffffff", c2: "#ff6a00"},
     params: {mode: "burst", count: 18, angle_deg: -30, spread_deg: 120, speed_min: 80, speed_max: 260, gravity: 420, drag: 0.94, size_min: 1.5, size_max: 4, size_over_life: "shrink", life_min_ms: 180, life_max_ms: 420}}]}
];
})(window);
