/* Weapons — FX Studio's port of laser/weaponfx.py: the 2.5D signature
 * weapons of the FX Kit "technique" primitive (Buster Sword, Masamune,
 * Oathkeeper & Oblivion, Crescent scythe, Scissor Blade, Gungnir, light
 * pistols and one per character).  Same timeline, same random streams
 * (FXK.rng), same 3D camera, geometry and painting order as the game, so the
 * Studio preview draws what Solo and Battle draw.  Keep the two in step
 * (tools/fx/check_parity.py compares the tables).
 * Builds on swordfx.js (frame, pen, maths): load it after that file.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };
var STYLES = ["buster_sword", "masamune", "oath_oblivion", "crescent_scythe", "scissor_blade", "gungnir", "light_pistols", "crimson_fang", "arc_carbine", "void_cannon", "phase_kunai", "astral_staff", "phantom_greatsword", "neon_uzis", "halo_chakram", "wisp_rapier", "pulse_bow", "rune_reaver", "nodachi", "earth_cleaver", "void_sniper"];
var HU = 10;
var SUMMON = 8;
var DISMISS = 12;
var FOCAL = 4;
var THICK_K = 0.5;
var TRAIL_N = 6;
var TRAIL_SUB = 5;
var TRAIL_BAND = 0.62;
var EVT_HIT = 4;
var BEAM_T = 14;
var RAIL_T = 10;
var LINE_T = {beam: BEAM_T, rail: RAIL_T};   // shots that are an instant line to the end of their range
var LINE_HW = {beam: 7, rail: 5};          // their hit half-width (px, times the shot size)
var IMPLODE_IN = 10;   // ticks a void implosion takes to collapse before it pops
var VOID = [10, 4, 18];   // the void's black core (drawn over, not added)
var IMPACT_LIFE = 16;
var TAIL = 48;
var EVT_LIFE = {slam: 28, cuts: 18, xflash: 16, snip: 16, pillar: 30, runes: 36, glyph: 22, burst: 16, charge: 0, petals: 30, blink: 12, implode: 26};
var EVT_R = {slam: 46, cuts: 26, xflash: 20, snip: 22, pillar: 26, runes: 18, glyph: 24, burst: 20, charge: 0, petals: 0, blink: 0, implode: 0};
var SHOTS = {light: {speed: 15, size: 1.1}, spark: {speed: 18, size: 0.9}, neon: {speed: 17, size: 0.75}, arrow: {speed: 14, size: 1}, beam: {speed: 0, size: 1.6}, rail: {speed: 0, size: 0.7}};
var GLOWS = ["gem", "spirit"];
// Models and weapons: laser/weaponfx.py MODELS / WEAPONS (see there for the layout).
var MODELS = {
  buster_sword: {vs: "w", blade: true, hit: [0.06, 0, 1, 0, 0.8], muzzle: [1, 0], mat: {blade: [150, 160, 172], edge: [228, 234, 240], guard: [118, 122, 130], grip: [70, 52, 40], dark: [30, 30, 36], accent: [150, 160, 172], gem: [90, 255, 140]}, parts: [["grip", [[-0.28, -0.16], [0, -0.16], [0, 0.16], [-0.28, 0.16]]], ["guard", [[-0.33, -0.24], [-0.28, -0.24], [-0.28, 0.24], [-0.33, 0.24]]], ["guard", [[0, -0.6], [0.06, -0.6], [0.06, 0.6], [0, 0.6]]], ["blade", [[0.06, -0.8], [0.9, -0.8], [1, 0.8], [0.06, 0.8]]], ["edge", [[0.06, 0.58], [0.97, 0.58], [1, 0.8], [0.06, 0.8]]], ["dark", [[0.1, -0.42], [0.16, -0.42], [0.16, 0], [0.1, 0]]], ["dark", [[0.19, -0.42], [0.25, -0.42], [0.25, 0], [0.19, 0]]], ["gem", [[0.115, -0.32], [0.145, -0.32], [0.145, -0.1], [0.115, -0.1]]]]},
  masamune: {vs: "w", blade: true, hit: [0.03, 0, 1, -2, 1], muzzle: [1, -2], mat: {blade: [200, 206, 216], edge: [245, 248, 252], guard: [150, 140, 110], grip: [60, 60, 72], dark: [30, 30, 36], accent: [150, 140, 110], gem: [190, 220, 255]}, parts: [["grip", [[-0.17, -0.38], [0, -0.34], [0, 0.34], [-0.17, 0.38]]], ["guard", [[-0.01, -1], [0.02, -1], [0.03, 0], [0.02, 1], [-0.01, 1], [-0.02, 0]]], ["blade", [[0.02, -0.45], [0.3, -0.62], [0.6, -0.98], [0.85, -1.45], [1, -2], [0.86, -1.1], [0.6, -0.1], [0.3, 0.45], [0.02, 0.5]]], ["edge", [[0.02, 0.22], [0.3, 0.16], [0.6, -0.34], [0.85, -1.25], [1, -2], [0.86, -1.1], [0.6, -0.1], [0.3, 0.45], [0.02, 0.5]]]]},
  oathkeeper: {vs: "w", blade: true, hit: [0.04, 0, 1.03, 0, 1], muzzle: [1, 0], mat: {blade: [226, 230, 238], edge: [255, 255, 255], guard: [206, 214, 230], grip: [70, 86, 140], dark: [40, 40, 60], accent: [236, 240, 250], gem: [150, 220, 255]}, parts: [["grip", [[-0.2, -0.3], [0, -0.3], [0, 0.3], [-0.2, 0.3]]], ["guard", [[-0.24, -0.9], [0, -1.15], [0.05, -0.6], [0.05, 0.6], [0, 1.15], [-0.24, 0.9], [-0.24, 0.7], [-0.03, 0.8], [-0.03, -0.8], [-0.24, -0.7]]], ["blade", [[0.05, -0.28], [0.86, -0.28], [0.86, 0.28], [0.05, 0.28]]], ["accent", [[0.78, -0.28], [0.84, -1.5], [0.91, -0.7], [0.99, -1.7], [1, 0.28], [0.78, 0.28]]], ["blade", [[0.86, -0.4], [1.03, 0], [0.86, 0.4]]], ["gem", [[-0.38, 0.95], [-0.33, 1.4], [-0.28, 0.95], [-0.33, 0.62]]]]},
  oblivion: {vs: "w", blade: true, hit: [0.04, 0, 1.03, 0, 1], muzzle: [1, 0], mat: {blade: [56, 52, 66], edge: [150, 150, 170], guard: [40, 36, 50], grip: [110, 30, 40], dark: [20, 18, 26], accent: [70, 64, 84], gem: [255, 80, 110]}, parts: [["grip", [[-0.2, -0.3], [0, -0.3], [0, 0.3], [-0.2, 0.3]]], ["guard", [[-0.24, -0.95], [0, -1.2], [0.05, -0.6], [0.05, 0.6], [0, 1.2], [-0.24, 0.95], [-0.24, 0.72], [-0.03, 0.82], [-0.03, -0.82], [-0.24, -0.72]]], ["blade", [[0.05, -0.3], [0.86, -0.3], [0.86, 0.3], [0.05, 0.3]]], ["accent", [[0.76, -0.3], [0.8, -1.25], [0.86, -0.7], [0.93, -1.6], [1, -0.3], [1, 0.3], [0.76, 0.3]]], ["edge", [[0.86, -0.42], [1.03, 0], [0.86, 0.42]]], ["gem", [[-0.38, 0.95], [-0.33, 1.4], [-0.28, 0.95], [-0.33, 0.62]]]]},
  crescent_scythe: {vs: "w", blade: true, hit: [0.95, 0.4, 0.56, 7.1, 1.4], muzzle: [1, 0], mat: {blade: [52, 50, 58], edge: [230, 232, 240], guard: [150, 20, 34], grip: [36, 34, 40], dark: [20, 18, 22], accent: [200, 26, 44], gem: [255, 60, 80]}, parts: [["grip", [[-0.6, -0.12], [0.9, -0.12], [0.9, 0.12], [-0.6, 0.12]]], ["accent", [[-0.62, -0.16], [-0.5, -0.16], [-0.5, 0.16], [-0.62, 0.16]]], ["guard", [[0.82, -0.4], [1, -0.4], [1, 0.4], [0.82, 0.4]]], ["blade", [[0.98, 0.3], [0.92, 3], [0.78, 5.5], [0.56, 7.3], [0.63, 5.2], [0.79, 2.8], [0.85, 0.3]]], ["edge", [[0.56, 7.3], [0.63, 5.2], [0.79, 2.8], [0.85, 0.3], [0.89, 0.3], [0.84, 2.9], [0.69, 5.4]]], ["gem", [[0.86, -0.18], [0.95, -0.18], [0.95, 0.18], [0.86, 0.18]]]]},
  scissor_a: {vs: "w", blade: true, hit: [0.05, -0.4, 1, -0.05, 0.6], muzzle: [1, 0], mat: {blade: [196, 28, 40], edge: [250, 236, 236], guard: [30, 28, 32], grip: [24, 22, 26], dark: [16, 14, 18], accent: [196, 28, 40], gem: [255, 70, 70]}, parts: [["grip", [[-0.4, -0.1], [-0.22, -0.95], [-0.04, -0.82], [-0.04, -0.16], [-0.2, -0.56], [-0.3, -0.1]]], ["blade", [[0.05, -0.92], [0.7, -0.92], [1, -0.1], [1, 0], [0.05, 0]]], ["edge", [[0.05, -0.16], [0.98, -0.16], [1, 0], [0.05, 0]]], ["guard", [[-0.06, -0.42], [0.06, -0.42], [0.06, 0], [-0.06, 0]]]]},
  scissor_b: {vs: "w", blade: true, hit: [0.05, 0.4, 1, 0.05, 0.6], muzzle: [1, 0], mat: {blade: [176, 20, 32], edge: [250, 236, 236], guard: [30, 28, 32], grip: [24, 22, 26], dark: [16, 14, 18], accent: [176, 20, 32], gem: [255, 70, 70]}, parts: [["grip", [[-0.4, 0.1], [-0.22, 0.95], [-0.04, 0.82], [-0.04, 0.16], [-0.2, 0.56], [-0.3, 0.1]]], ["blade", [[0.05, 0], [1, 0], [0.82, 0.6], [0.4, 0.92], [0.05, 0.92]]], ["edge", [[0.05, 0], [1, 0], [0.97, 0.12], [0.05, 0.14]]], ["guard", [[-0.06, 0], [0.06, 0], [0.06, 0.42], [-0.06, 0.42]]], ["gem", [[-0.03, 0.12], [0.03, 0.12], [0.03, 0.3], [-0.03, 0.3]]]]},
  gungnir: {vs: "w", blade: true, hit: [0.6, 0, 1, 0, 1.2], muzzle: [1, 0], mat: {blade: [236, 200, 96], edge: [255, 250, 220], guard: [200, 150, 60], grip: [150, 110, 50], dark: [60, 40, 20], accent: [236, 200, 96], gem: [120, 220, 255]}, parts: [["grip", [[-0.45, -0.22], [0.72, -0.22], [0.72, 0.22], [-0.45, 0.22]]], ["guard", [[-0.45, -0.32], [-0.53, 0], [-0.45, 0.32]]], ["guard", [[0.68, -0.62], [0.74, -0.62], [0.74, 0.62], [0.68, 0.62]]], ["blade", [[0.74, -0.9], [0.8, -1.7], [0.84, -0.7], [1, 0], [0.84, 0.7], [0.8, 1.7], [0.74, 0.9]]], ["edge", [[0.82, -0.22], [1, 0], [0.82, 0.22]]], ["gem", [[0.08, -0.08], [0.62, -0.08], [0.62, 0.08], [0.08, 0.08]]]]},
  light_pistol: {vs: "w", blade: false, hit: [0, 0, 1, 0, 0.5], muzzle: [1, -0.05], mat: {blade: [236, 238, 244], edge: [255, 255, 255], guard: [180, 150, 80], grip: [60, 64, 80], dark: [30, 32, 40], accent: [214, 180, 96], gem: [170, 255, 250]}, parts: [["grip", [[-0.1, 0.2], [0.1, 0.2], [0.02, 1.6], [-0.18, 1.5]]], ["blade", [[-0.2, -0.5], [0.8, -0.5], [0.95, -0.25], [0.95, 0.3], [-0.2, 0.3]]], ["accent", [[-0.1, -0.66], [0.6, -0.66], [0.7, -0.46], [-0.1, -0.46]]], ["guard", [[0.95, -0.18], [1, -0.18], [1, 0.12], [0.95, 0.12]]], ["gem", [[0.2, -0.22], [0.72, -0.22], [0.72, 0.04], [0.2, 0.04]]]]},
  crimson_fang: {vs: "w", blade: true, hit: [0.05, 0, 1, 0, 0.6], muzzle: [1, 0], mat: {blade: [176, 168, 172], edge: [255, 236, 236], guard: [110, 20, 28], grip: [50, 20, 24], dark: [30, 10, 14], accent: [140, 24, 32], gem: [255, 40, 50]}, parts: [["grip", [[-0.22, -0.2], [0, -0.2], [0, 0.2], [-0.22, 0.2]]], ["guard", [[-0.28, -0.34], [-0.22, -0.34], [-0.22, 0.34], [-0.28, 0.34]]], ["guard", [[0, -1.4], [0.05, -1.2], [0.05, 1.2], [0, 1.4]]], ["blade", [[0.05, -0.6], [0.9, -0.55], [1, 0], [0.9, 0.55], [0.05, 0.6]]], ["edge", [[0.05, 0.42], [0.9, 0.4], [1, 0], [0.9, 0.55], [0.05, 0.6]]], ["gem", [[0.08, -0.15], [0.8, -0.12], [0.8, 0.12], [0.08, 0.15]]]]},
  arc_carbine: {vs: "w", blade: false, hit: [0, 0, 1, 0, 0.5], muzzle: [1, -0.15], mat: {blade: [70, 86, 104], edge: [200, 220, 236], guard: [44, 50, 60], grip: [36, 40, 48], dark: [20, 22, 28], accent: [90, 200, 255], gem: [120, 230, 255]}, parts: [["grip", [[-0.45, -0.3], [-0.15, -0.35], [-0.15, 0.35], [-0.45, 0.7]]], ["blade", [[-0.15, -0.45], [0.55, -0.45], [0.6, 0.35], [-0.15, 0.35]]], ["grip", [[0, 0.35], [0.12, 0.35], [0.06, 1.2], [-0.06, 1.15]]], ["guard", [[0.22, 0.35], [0.34, 0.35], [0.38, 1.1], [0.26, 1.15]]], ["guard", [[0.55, -0.3], [1, -0.3], [1, 0], [0.55, 0]]], ["gem", [[0.1, -0.3], [0.5, -0.3], [0.5, -0.1], [0.1, -0.1]]]]},
  void_cannon: {vs: "w", blade: false, hit: [0, 0, 1, 0, 0.8], muzzle: [1, 0], mat: {blade: [58, 30, 82], edge: [170, 120, 220], guard: [30, 18, 44], grip: [24, 16, 34], dark: [12, 8, 18], accent: [110, 60, 160], gem: [200, 110, 255]}, parts: [["blade", [[-0.3, -0.8], [0.7, -0.9], [1, -0.6], [1, 0.6], [0.7, 0.9], [-0.3, 0.8]]], ["accent", [[0.3, -0.96], [0.38, -0.96], [0.38, 0.96], [0.3, 0.96]]], ["accent", [[0.55, -0.98], [0.62, -0.98], [0.62, 0.98], [0.55, 0.98]]], ["dark", [[0.82, -0.45], [1, -0.45], [1, 0.45], [0.82, 0.45]]], ["gem", [[0.86, -0.3], [1, -0.3], [1, 0.3], [0.86, 0.3]]]]},
  void_sniper: {vs: "w", blade: false, hit: [0, 0, 1, 0, 0.6], muzzle: [1, 0], mat: {blade: [34, 24, 46], edge: [150, 110, 200], guard: [22, 16, 30], grip: [18, 12, 24], dark: [8, 6, 12], accent: [120, 60, 180], gem: [190, 100, 255]}, parts: [["grip", [[-0.5, -0.7], [-0.12, -0.8], [-0.12, 0.6], [-0.3, 0.6], [-0.42, 1.5], [-0.52, 1.4]]], ["blade", [[-0.12, -0.9], [0.38, -0.9], [0.42, 0.7], [-0.12, 0.7]]], ["grip", [[-0.02, 0.7], [0.08, 0.7], [0.03, 2], [-0.07, 1.9]]], ["guard", [[0.13, 0.7], [0.22, 0.7], [0.22, 1.5], [0.13, 1.5]]], ["guard", [[0.06, -1.1], [0.1, -1.1], [0.1, -0.9], [0.06, -0.9]]], ["guard", [[0.22, -1.1], [0.26, -1.1], [0.26, -0.9], [0.22, -0.9]]], ["dark", [[0, -2], [0.32, -2], [0.32, -1.1], [0, -1.1]]], ["gem", [[0.27, -1.9], [0.32, -1.9], [0.32, -1.2], [0.27, -1.2]]], ["blade", [[0.38, -0.45], [1, -0.35], [1, 0.35], [0.38, 0.45]]], ["accent", [[0.5, -0.62], [0.55, -0.62], [0.55, 0.62], [0.5, 0.62]]], ["accent", [[0.64, -0.58], [0.69, -0.58], [0.69, 0.58], [0.64, 0.58]]], ["accent", [[0.78, -0.54], [0.83, -0.54], [0.83, 0.54], [0.78, 0.54]]], ["gem", [[0.42, -0.14], [0.93, -0.1], [0.93, 0.1], [0.42, 0.14]]], ["dark", [[0.93, -0.55], [1, -0.55], [1, 0.55], [0.93, 0.55]]]]},
  kunai: {vs: "w", blade: true, hit: [0, 0, 1, 0, 0.7], muzzle: [1, 0], mat: {blade: [84, 90, 104], edge: [220, 228, 240], guard: [60, 64, 76], grip: [140, 40, 50], dark: [20, 22, 28], accent: [140, 40, 50], gem: [140, 255, 220]}, parts: [["grip", [[-0.3, -0.15], [0, -0.15], [0, 0.15], [-0.3, 0.15]]], ["guard", [[-0.44, -0.3], [-0.3, -0.3], [-0.3, 0.3], [-0.44, 0.3]]], ["blade", [[0, -0.3], [0.35, -0.75], [1, 0], [0.35, 0.75], [0, 0.3]]], ["edge", [[0.05, -0.08], [1, 0], [0.05, 0.08]]], ["gem", [[-0.4, -0.12], [-0.34, -0.12], [-0.34, 0.12], [-0.4, 0.12]]]]},
  astral_staff: {vs: "w", blade: true, hit: [0.6, 0, 1, 0, 1.4], muzzle: [1, 0], mat: {blade: [120, 92, 70], edge: [240, 230, 210], guard: [214, 190, 120], grip: [96, 70, 52], dark: [40, 30, 24], accent: [214, 190, 120], gem: [160, 200, 255]}, parts: [["grip", [[-0.6, -0.18], [0.78, -0.15], [0.78, 0.15], [-0.6, 0.18]]], ["accent", [[0.2, -0.24], [0.26, -0.24], [0.26, 0.24], [0.2, 0.24]]], ["accent", [[-0.35, -0.24], [-0.29, -0.24], [-0.29, 0.24], [-0.35, 0.24]]], ["guard", [[0.72, -0.25], [0.78, -1.4], [0.9, -1.65], [0.84, -0.9], [0.8, -0.25]]], ["guard", [[0.72, 0.25], [0.78, 1.4], [0.9, 1.65], [0.84, 0.9], [0.8, 0.25]]], ["gem", [[0.8, 0], [0.9, -0.7], [1, 0], [0.9, 0.7]]]]},
  phantom_greatsword: {vs: "w", blade: true, hit: [0.08, 0, 1, 0, 0.8], muzzle: [1, 0], mat: {blade: [90, 70, 130], edge: [255, 255, 255], guard: [60, 40, 90], grip: [36, 26, 52], dark: [20, 14, 30], accent: [120, 90, 170], gem: [220, 190, 255]}, parts: [["grip", [[-0.2, -0.2], [0, -0.2], [0, 0.2], [-0.2, 0.2]]], ["guard", [[0, -1.2], [0.04, -1.55], [0.08, -0.9], [0.08, 0.9], [0.04, 1.55], [0, 1.2]]], ["spirit", [[0.08, -0.8], [0.85, -0.7], [1, 0], [0.85, 0.7], [0.08, 0.8]]], ["gem", [[0.1, -0.2], [0.9, -0.1], [0.97, 0], [0.9, 0.1], [0.1, 0.2]]]]},
  neon_uzi: {vs: "w", blade: false, hit: [0, 0, 1, 0, 0.5], muzzle: [1, -0.1], mat: {blade: [34, 34, 42], edge: [200, 200, 220], guard: [60, 60, 72], grip: [26, 26, 32], dark: [12, 12, 16], accent: [255, 60, 200], gem: [255, 90, 220]}, parts: [["blade", [[-0.15, -0.45], [0.7, -0.45], [0.7, 0.3], [-0.15, 0.3]]], ["grip", [[0, 0.3], [0.14, 0.3], [0.12, 1.3], [-0.02, 1.3]]], ["guard", [[0.7, -0.25], [1, -0.25], [1, 0.05], [0.7, 0.05]]], ["gem", [[-0.1, -0.26], [0.6, -0.26], [0.6, -0.12], [-0.1, -0.12]]]]},
  halo_chakram: {vs: "l", blade: true, hit: [-0.5, 0, 0.5, 0, 0.35], muzzle: [0.5, 0], mat: {blade: [236, 222, 160], edge: [255, 255, 240], guard: [200, 170, 90], grip: [120, 96, 50], dark: [60, 46, 20], accent: [236, 222, 160], gem: [255, 250, 200]}, parts: [["blade", [[0.492, 0.087], [0.305, 0.126], [0.287, 0.41], [0.126, 0.305], [-0.087, 0.492], [-0.126, 0.305], [-0.41, 0.287], [-0.305, 0.126], [-0.492, -0.087], [-0.305, -0.126], [-0.287, -0.41], [-0.126, -0.305], [0.087, -0.492], [0.126, -0.305], [0.41, -0.287], [0.305, -0.126]]], ["guard", [[0.24, 0], [0.17, 0.17], [0, 0.24], [-0.17, 0.17], [-0.24, 0], [-0.17, -0.17], [0, -0.24], [0.17, -0.17]]], ["gem", [[0.111, 0.046], [0.046, 0.111], [-0.046, 0.111], [-0.111, 0.046], [-0.111, -0.046], [-0.046, -0.111], [0.046, -0.111], [0.111, -0.046]]]]},
  wisp_rapier: {vs: "w", blade: true, hit: [0.06, 0, 1, 0, 0.5], muzzle: [1, 0], mat: {blade: [200, 236, 255], edge: [255, 255, 255], guard: [170, 190, 220], grip: [70, 80, 110], dark: [30, 34, 50], accent: [170, 190, 220], gem: [200, 240, 255]}, parts: [["grip", [[-0.2, -0.15], [0, -0.15], [0, 0.15], [-0.2, 0.15]]], ["guard", [[-0.02, -0.9], [0.06, -0.7], [0.06, 0.7], [-0.02, 0.9], [-0.06, 0]]], ["guard", [[-0.22, 0.2], [-0.2, 0.92], [0, 0.96], [0, 0.8], [-0.15, 0.76], [-0.16, 0.2]]], ["spirit", [[0.06, -0.3], [1, -0.02], [1, 0.02], [0.06, 0.3]]], ["edge", [[0.06, -0.07], [1, 0], [0.06, 0.07]]]]},
  pulse_bow: {vs: "l", blade: false, hit: [0, -0.5, 0, 0.5, 0.05], muzzle: [0.06, 0], mat: {blade: [40, 60, 80], edge: [200, 240, 255], guard: [70, 110, 140], grip: [30, 40, 52], dark: [16, 20, 26], accent: [90, 200, 255], gem: [140, 230, 255]}, parts: [["blade", [[0.03, -0.06], [0.14, -0.28], [0.05, -0.5], [-0.01, -0.5], [0.06, -0.28], [-0.04, -0.06]]], ["blade", [[0.03, 0.06], [0.14, 0.28], [0.05, 0.5], [-0.01, 0.5], [0.06, 0.28], [-0.04, 0.06]]], ["grip", [[-0.035, -0.08], [0.035, -0.08], [0.035, 0.08], [-0.035, 0.08]]], ["gem", [[0, -0.53], [0.035, -0.49], [0, -0.45], [-0.035, -0.49]]], ["gem", [[0, 0.53], [0.035, 0.49], [0, 0.45], [-0.035, 0.49]]]]},
  rune_reaver: {vs: "w", blade: true, hit: [0.06, 0, 1, -0.6, 0.7], muzzle: [1, 0], mat: {blade: [70, 84, 96], edge: [220, 240, 250], guard: [40, 48, 56], grip: [30, 34, 40], dark: [16, 18, 22], accent: [70, 84, 96], gem: [110, 255, 200]}, parts: [["grip", [[-0.2, -0.2], [0, -0.2], [0, 0.2], [-0.2, 0.2]]], ["guard", [[0, -0.72], [0.06, -0.5], [0.06, 0.5], [0, 0.72]]], ["blade", [[0.06, -0.45], [0.7, -0.5], [1, -0.9], [0.85, 0.15], [0.4, 0.5], [0.06, 0.45]]], ["edge", [[0.4, 0.34], [0.85, 0], [1, -0.9], [0.85, 0.15], [0.4, 0.5]]], ["gem", [[0.15, -0.1], [0.2, -0.26], [0.25, -0.1], [0.2, 0.05]]], ["gem", [[0.35, -0.12], [0.4, -0.28], [0.45, -0.12], [0.4, 0.03]]], ["gem", [[0.55, -0.16], [0.6, -0.32], [0.65, -0.16], [0.6, -0.01]]]]},
  nodachi: {vs: "w", blade: true, hit: [0.03, 0, 1, -1.8, 1], muzzle: [1, -1.8], mat: {blade: [186, 192, 204], edge: [250, 252, 255], guard: [190, 150, 60], grip: [30, 28, 34], dark: [40, 40, 48], accent: [190, 150, 60], gem: [255, 220, 140]}, parts: [["grip", [[-0.2, -0.36], [0, -0.32], [0, 0.32], [-0.2, 0.36]]], ["guard", [[-0.01, -1.1], [0.025, -1.1], [0.035, 0], [0.025, 1.1], [-0.01, 1.1], [-0.02, 0]]], ["blade", [[0.03, -0.5], [0.3, -0.68], [0.6, -1], [0.85, -1.38], [1, -1.8], [0.86, -0.95], [0.6, 0], [0.3, 0.5], [0.03, 0.55]]], ["edge", [[0.03, 0.2], [0.3, 0.14], [0.6, -0.32], [0.85, -1.15], [1, -1.8], [0.86, -0.95], [0.6, 0], [0.3, 0.5], [0.03, 0.55]]]]},
  saya: {vs: "w", blade: false, hit: [0, 0, 1, 0, 0.5], muzzle: [1, 0], mat: {blade: [26, 24, 30], edge: [80, 76, 90], guard: [190, 150, 60], grip: [26, 24, 30], dark: [14, 12, 16], accent: [190, 150, 60], gem: [255, 220, 140]}, parts: [["blade", [[0.02, -0.7], [0.3, -0.85], [0.6, -1.15], [0.85, -1.58], [1.03, -2.05], [0.88, -1.05], [0.6, 0.1], [0.3, 0.7], [0.02, 0.7]]], ["accent", [[0.12, -0.8], [0.16, -0.82], [0.16, 0.72], [0.12, 0.72]]], ["accent", [[0.96, -2], [1.03, -2.05], [0.99, -1.4], [0.92, -1.3]]]]},
  earth_cleaver: {vs: "w", blade: true, hit: [0.08, 0.3, 0.98, 0.5, 0.8], muzzle: [1, 0], mat: {blade: [110, 104, 98], edge: [224, 216, 204], guard: [70, 60, 50], grip: [60, 40, 28], dark: [40, 36, 32], accent: [150, 120, 80], gem: [255, 150, 60]}, parts: [["grip", [[-0.34, -0.2], [0.05, -0.2], [0.05, 0.2], [-0.34, 0.2]]], ["guard", [[0, -0.5], [0.08, -0.5], [0.08, 0.5], [0, 0.5]]], ["blade", [[0.08, -1], [0.95, -1.1], [1, -0.7], [0.97, 1], [0.6, 1.1], [0.55, 0.95], [0.45, 1.1], [0.08, 1]]], ["dark", [[0.08, -1], [0.95, -1.1], [0.95, -0.82], [0.08, -0.74]]], ["edge", [[0.08, 0.82], [0.45, 0.92], [0.55, 0.78], [0.6, 0.92], [0.97, 0.82], [0.97, 1], [0.6, 1.1], [0.55, 0.95], [0.45, 1.1], [0.08, 1]]], ["accent", [[0.16, -0.5], [0.22, -0.5], [0.22, -0.38], [0.16, -0.38]]], ["accent", [[0.16, 0.38], [0.22, 0.38], [0.22, 0.5], [0.16, 0.5]]], ["gem", [[0.4, -0.3], [0.6, -0.34], [0.62, -0.2], [0.42, -0.16]]]]}
};
var WEAPONS = {
  buster_sword: {models: ["buster_sword"], beats: 4, aim: false, trail: "swept", shot: "", tracks: [[[0, -0.2, -0.4, 0, 210, 0, 0, 1, 3], [0.4, -0.1, -1, 0, 250, 20, 0, 1.05, 3], [0.62, 0.5, 0.2, 0, 440, 0, 0, 1.08, 2], [0.75, 0.55, 0.3, 0, 445, 0, 0, 1.05, 1], [1, 0.4, 0.2, 0, 430, 0, 0, 1, 3]]], events: [[0.62, "slam", "tip0", 1.3, 0]], fire: []},
  masamune: {models: ["masamune"], beats: 4, aim: false, trail: "swept", shot: "", tracks: [[[0, -0.3, 0.3, 0, 160, 0, 0, 1, 3], [0.3, -0.3, 0.2, 0, 150, 40, 0, 1, 3], [0.4, 0.5, -0.4, 0, 340, 0, 0, 1, 1], [0.6, 0.4, -0.3, 0, 350, 0, 0, 1, 3], [1, 0.2, 0, 0, 380, 20, 0, 1, 3]]], events: [[0.42, "cuts", "target", 8, 0]], fire: []},
  oath_oblivion: {models: ["oathkeeper", "oblivion"], beats: 5, aim: false, trail: "swept", shot: "", tracks: [[[0, -0.2, -0.6, 0, -60, 0, 0, 1, 3], [0.45, 0.3, -1.4, 0, 300, 180, 0, 1, 3], [0.7, 0.6, -1.6, 0, 405, 360, 0, 1, 1], [1, 0.5, -1.4, 0, 395, 360, 0, 1, 3]], [[0, -0.2, 0.6, 0, 60, 0, 0, 1, 3], [0.45, 0.3, 1.4, 0, -300, -180, 0, 1, 3], [0.7, 0.6, 1.6, 0, -405, -360, 0, 1, 1], [1, 0.5, 1.4, 0, -395, -360, 0, 1, 3]]], events: [[0.7, "xflash", "mid", 1.3, 0]], fire: []},
  crescent_scythe: {models: ["crescent_scythe"], beats: 5, aim: false, trail: "swept", shot: "", tracks: [[[0, -0.4, -0.3, 0, -100, 0, 0, 1, 3], [0.15, -0.2, -0.4, 0, -100, 0, 40, 1, 3], [0.55, 0.2, -0.3, 0, 260, 0, 50, 1, 0], [0.75, 0.9, 0, 0, 390, 0, 0, 1.1, 1], [1, 0.7, 0, 0, 380, 0, 0, 1, 3]]], events: [[0.1, "petals", "tip0", 1, 0], [0.74, "burst", "tip0", 1, 0]], fire: []},
  scissor_blade: {models: ["scissor_a", "scissor_b"], beats: 5, aim: true, trail: "", shot: "", tracks: [[[0, 0.2, -0.3, 0, -30, 0, 0, 1, 3], [0.3, 0.6, -0.2, 0.2, -75, 0, 0, 1.5, 3], [0.6, 0.6, -0.2, 1, -80, 0, 0, 1.6, 3], [0.72, 0.6, -0.2, 1, -5, 0, 0, 1.6, 2], [1, 0.3, -0.2, 0, -30, 0, 0, 1, 3]], [[0, 0.2, -0.3, 0, -30, 0, 0, 1, 3], [0.3, 0.6, -0.2, 0.2, 15, 0, 0, 1.5, 3], [0.6, 0.6, -0.2, 1, 20, 0, 0, 1.6, 3], [0.72, 0.6, -0.2, 1, -5, 0, 0, 1.6, 2], [1, 0.3, -0.2, 0, -30, 0, 0, 1, 3]]], events: [[0.72, "snip", "mid", 1.4, 0]], fire: []},
  gungnir: {models: ["gungnir"], beats: 6, aim: true, trail: "", shot: "", tracks: [[[0, -0.2, -0.6, 0, 0, 0, 0, 1, 3], [0.35, -0.9, -0.9, 0, -8, 90, 0, 1, 3], [0.45, -0.6, -0.9, 0, -4, 180, 0, 1.05, 2], [0.72, 0, -0.5, 1, 0, 1440, 0, 1.05, 2], [1, 0, -0.5, 1, 0, 1440, 0, 1, 3]]], events: [[0.05, "charge", "tip0", 1, 0.4], [0.72, "pillar", "tip0", 1.3, 0]], fire: []},
  light_pistols: {models: ["light_pistol", "light_pistol"], beats: 6, aim: true, trail: "", shot: "light", tracks: [[[0, 0.3, -0.4, 0, 0, 0, 0, 1, 3], [0.9, 0.3, -0.4, 0, 0, 0, 0, 1, 3], [1, 0.3, -0.4, 0, 0, 360, 0, 1, 3]], [[0, 0.1, 0.5, 0, 0, 0, 0, 1, 3], [0.9, 0.1, 0.5, 0, 0, 0, 0, 1, 3], [1, 0.1, 0.5, 0, 0, -360, 0, 1, 3]]], events: [], fire: [[0.08, 0], [0.16, 1], [0.24, 0], [0.32, 1], [0.4, 0], [0.48, 1], [0.56, 0], [0.64, 1], [0.72, 0], [0.8, 1]]},
  crimson_fang: {models: ["crimson_fang"], beats: 3, aim: false, trail: "swept", shot: "", tracks: [[[0, 0, 0.3, 0, 130, 0, 0, 1, 3], [0.25, -0.1, 0.4, 0, 140, 30, 0, 1, 3], [0.6, 0.4, -0.6, 0, -80, 0, 0, 1.05, 1], [1, 0.3, -0.5, 0, -70, 0, 0, 1, 3]]], events: [[0.6, "burst", "tip0", 1, 0]], fire: []},
  arc_carbine: {models: ["arc_carbine"], beats: 5, aim: true, trail: "", shot: "spark", tracks: [[[0, 0.2, -0.1, 0, 0, 0, 0, 1, 3], [1, 0.2, -0.1, 0, 0, 0, 0, 1, 3]]], events: [], fire: [[0.15, 0], [0.21, 0], [0.27, 0], [0.55, 0], [0.61, 0], [0.67, 0]]},
  void_cannon: {models: ["void_cannon"], beats: 5, aim: true, trail: "", shot: "beam", tracks: [[[0, 0.3, 0, 0, 0, 0, 0, 1, 3], [0.5, 0.3, 0, 0, 0, 0, 0, 1.05, 3], [1, 0.3, 0, 0, 0, 0, 0, 1, 3]]], events: [[0, "charge", "tip0", 1.4, 0.55]], fire: [[0.55, 0]]},
  phase_kunai: {models: ["kunai", "kunai"], beats: 6, aim: true, trail: "", shot: "", tracks: [[[0, 0.2, -0.3, 0, -20, 0, 0, 1, 3], [0.15, -0.3, -0.5, 0, -30, 0, 0, 1, 3], [0.45, 0, -0.3, 1, -6, 720, 0, 1, 2], [0.48, 0, -0.3, 1, -6, 720, 0, 0, 0], [0.6, 0, -0.3, 1.35, 180, 720, 0, 0, 0], [0.63, 0, -0.3, 1.35, 180, 720, 0, 1, 0], [0.75, 0, -0.3, 1, 180, 720, 0, 1, 1], [1, 0, -0.3, 1.1, 180, 720, 0, 1, 3]], [[0, 0.1, 0.3, 0, 20, 0, 0, 1, 3], [0.15, -0.3, 0.4, 0, 30, 0, 0, 1, 3], [0.45, 0, 0.3, 1, 6, -720, 0, 1, 2], [0.48, 0, 0.3, 1, 6, -720, 0, 0, 0], [0.6, 0, 0.3, 1.35, 180, -720, 0, 0, 0], [0.63, 0, 0.3, 1.35, 180, -720, 0, 1, 0], [0.75, 0, 0.3, 1, 180, -720, 0, 1, 1], [1, 0, 0.3, 1.1, 180, -720, 0, 1, 3]]], events: [[0.46, "blink", "tip0", 1, 0], [0.46, "blink", "tip1", 1, 0], [0.62, "blink", "tip0", 1, 0], [0.62, "blink", "tip1", 1, 0], [0.75, "xflash", "target", 1, 0]], fire: []},
  astral_staff: {models: ["astral_staff"], beats: 6, aim: false, trail: "swept", shot: "", tracks: [[[0, 0.3, 0.2, 0, -95, 0, 0, 1, 3], [0.1, 0.2, -0.2, 0, -95, 0, 0, 1, 3], [0.5, 0.2, -0.4, 0, 625, 360, 0, 1, 0], [0.6, 0.6, 0.3, 0, 640, 360, 0, 1.05, 1], [1, 0.5, 0.2, 0, 635, 360, 0, 1, 3]]], events: [[0.6, "runes", "target", 1, 0]], fire: []},
  phantom_greatsword: {models: ["phantom_greatsword"], beats: 4, aim: false, trail: "swept", shot: "", tracks: [[[0, 0, -0.5, 0, -90, 0, 0, 0.8, 3], [0.35, -0.2, -1.6, 0, -100, 0, 0, 1.25, 3], [0.6, 0.6, 0.1, 0, 80, 0, 0, 1.3, 2], [1, 0.5, 0.1, 0, 85, 0, 0, 1.2, 3]]], events: [[0.6, "slam", "tip0", 1.6, 0]], fire: []},
  neon_uzis: {models: ["neon_uzi", "neon_uzi"], beats: 8, aim: true, trail: "", shot: "neon", tracks: [[[0, 0.3, -0.4, 0, 0, 0, 0, 1, 3], [0.85, 0.3, -0.4, 0, 0, 0, 0, 1, 3], [1, 0.3, -0.4, 0, 0, 360, 0, 1, 3]], [[0, 0.1, 0.45, 0, 0, 0, 0, 1, 3], [0.85, 0.1, 0.45, 0, 0, 0, 0, 1, 3], [1, 0.1, 0.45, 0, 0, -360, 0, 1, 3]]], events: [], fire: [[0.05, 0], [0.1, 1], [0.15, 0], [0.2, 1], [0.25, 0], [0.3, 1], [0.35, 0], [0.4, 1], [0.45, 0], [0.5, 1], [0.55, 0], [0.6, 1], [0.65, 0], [0.7, 1], [0.75, 0], [0.8, 1]]},
  halo_chakram: {models: ["halo_chakram"], beats: 6, aim: true, trail: "ghost", shot: "", tracks: [[[0, 0.4, -0.3, 0, 0, 0, 60, 1, 3], [0.15, 0, -0.5, 0, 0, 0, 60, 1, 3], [0.32, 0, -3, 0.5, 540, 0, 60, 1, 0], [0.5, 0, 0, 1, 900, 0, 60, 1, 1], [0.68, 0, 3, 0.5, 1350, 0, 60, 1, 0], [0.85, 0, 0, 0, 1800, 0, 60, 1, 2], [1, 0.4, -0.3, 0, 1840, 0, 60, 1, 1]]], events: [[0.5, "burst", "mid", 1.2, 0]], fire: []},
  wisp_rapier: {models: ["wisp_rapier"], beats: 6, aim: false, trail: "ghost", shot: "", tracks: [[[0, 0.2, 0, 0, 0, 0, 0, 1, 3], [0.1, 1.6, -0.4, 0, -10, 0, 0, 1, 1], [0.18, 0.4, -0.2, 0, -6, 0, 0, 1, 3], [0.28, 1.7, 0.3, 0, 8, 0, 0, 1, 1], [0.36, 0.4, 0.1, 0, 4, 0, 0, 1, 3], [0.46, 1.8, -0.6, 0, -14, 0, 0, 1, 1], [0.54, 0.4, -0.2, 0, -5, 0, 0, 1, 3], [0.64, 1.7, 0.5, 0, 12, 0, 0, 1, 1], [0.72, 0.2, 0, 0, 0, 0, 0, 1, 3], [0.85, 2.6, 0, 0, 0, 0, 0, 1.15, 1], [1, 1.2, 0, 0, 0, 0, 0, 1, 3]]], events: [[0.85, "burst", "tip0", 1.1, 0]], fire: []},
  pulse_bow: {models: ["pulse_bow"], beats: 5, aim: true, trail: "", shot: "arrow", tracks: [[[0, 0.5, -0.2, 0, 0, 0, 0, 1, 3], [1, 0.5, -0.2, 0, 0, 0, 0, 1, 3]]], events: [], fire: [[0.6, 0]]},
  rune_reaver: {models: ["rune_reaver"], beats: 4, aim: false, trail: "swept", shot: "", tracks: [[[0, 0.3, -0.2, 0, 120, 0, 0, 1, 3], [0.2, 0.1, -0.1, 0, 130, 0, 0, 1, 3], [0.65, 0.5, -0.4, 0, -410, 180, 0, 1.05, 1], [1, 0.4, -0.3, 0, -400, 180, 0, 1, 3]]], events: [[0.66, "glyph", "tip0", 1, 0]], fire: []},
  nodachi: {models: ["nodachi", "saya"], beats: 5, aim: false, trail: "swept", shot: "", tracks: [[[0, -0.2, 0.3, 0, 195, 0, 0, 1, 3], [0.45, -0.2, 0.3, 0, 195, 0, 0, 1, 3], [0.52, 0.6, 0, 0, 360, 0, 0, 1, 1], [1, 0.5, 0, 0, 365, 0, 0, 1, 3]], [[0, -0.2, 0.35, 0, 195, 0, 0, 1, 3], [1, -0.25, 0.4, 0, 200, 0, 0, 1, 3]]], events: [[0.53, "cuts", "target", 1, 0]], fire: []},
  earth_cleaver: {models: ["earth_cleaver"], beats: 4, aim: false, trail: "swept", shot: "", tracks: [[[0, 0, -0.3, 0, -120, 0, 0, 1, 3], [0.4, -0.3, -1.2, 0, -110, 0, 0, 1.05, 3], [0.62, 0.6, 0.3, 0, 85, 0, 0, 1.1, 2], [1, 0.55, 0.3, 0, 88, 0, 0, 1.05, 3]]], events: [[0.62, "slam", "tip0", 1.7, 0]], fire: []},
  void_sniper: {models: ["void_sniper"], beats: 6, aim: true, trail: "", shot: "rail", tracks: [[[0, 0.2, -0.2, 0, 0, 0, 0, 1, 3], [0.58, 0.2, -0.2, 0, 0, 0, 0, 1, 3], [0.76, 0, -0.3, 0, -16, 0, 0, 1, 1], [1, 0.2, -0.2, 0, -4, 0, 0, 1, 3]]], events: [[0.05, "charge", "tip0", 1, 0.53], [0.58, "implode", "target", 1, 0]], fire: [[0.58, 0]]}
};

// ---------------------------------------------------------------- timeline
function W_(P) { return WEAPONS[L_().style(P)]; }
function sig(P) { return P.w_mode !== "hold"; }
function moveT(P) { return W_(P).beats * Math.max(1, Math.trunc(+P.swing_ticks || 6)); }   // the sequence, ticks
function holdT(P) { return Math.max(0, Math.trunc(+P.hold_ticks || 0)); }
function tickOf(P, t) { return SUMMON + Math.round(t * moveT(P)); }
function shotFlight(P) {
  var w = W_(P);
  if (!w.shot) return 0;
  if (LINE_T[w.shot] !== undefined) return LINE_T[w.shot];
  return Math.ceil(Math.max(20, +P.radius || 0) / SHOTS[w.shot].speed);
}
// The weapon's life: the hit window (and how long it stays).
function activeTicks(P) {
  if (!sig(P)) return SUMMON + Math.max(1, holdT(P));
  var w = W_(P), n = SUMMON + moveT(P) + holdT(P), i;
  for (i = 0; i < w.fire.length; i++) n = Math.max(n, tickOf(P, w.fire[i][0]) + shotFlight(P) + 1);
  for (i = 0; i < w.events.length; i++) {
    var e = w.events[i];
    if (EVT_R[e[1]] > 0) n = Math.max(n, tickOf(P, e[0]) + EVT_HIT + (e[1] === "runes" ? 24 : 0) + 1);
  }
  return n;
}
function totalTicks(P) { return activeTicks(P) + DISMISS + TAIL; }
// [u through the sequence, materialise 0..1, fade 1..0] at tick.
function phase(P, life, tick) {
  var ap = Math.min(1, tick / SUMMON);
  var fd = tick < life ? 1 : Math.max(0, 1 - (tick - life) / DISMISS);
  if (!sig(P) || tick < SUMMON) return [0, ap, fd];
  return [Math.min(1, (tick - SUMMON) / moveT(P)), ap, fd];
}
function ease(e, k) {
  var L = L_();
  if (e === 1) return L.easeOut3(k);
  if (e === 2) return L.easeIn3(k);
  if (e === 3) return L.easeInOut3(k);
  return L.cl(k);
}
// The pose [x, y, r, ang, yaw, pitch, scale] at u.
function track(rows, u) {
  if (u <= rows[0][0]) return rows[0].slice(1, 8);
  for (var i = 0; i < rows.length - 1; i++) {
    var a = rows[i], b = rows[i + 1];
    if (u < b[0]) {
      var k = b[0] > a[0] ? (u - a[0]) / (b[0] - a[0]) : 1, e = ease(b[8], k), out = [];
      for (var j = 1; j < 8; j++) out.push(a[j] + (b[j] - a[j]) * e);
      return out;
    }
  }
  return rows[rows.length - 1].slice(1, 8);
}
function at(lst, k) { return lst[Math.max(0, Math.min(Math.trunc(k), lst.length - 1))]; }

// ---------------------------------------------------------------- 3D
// One weapon slot at one moment: model (u, v) -> world, through the yaw /
// pitch / perspective camera, the pose, the size and the flips.
function XF() {}
XF.prototype.pt = function (u, v, t) {
  t = t || 0;
  var x3 = u * this.L, y3 = v * this.W * this.cy - t * this.sy * this.tk, z3 = v * this.W * this.sy + t * this.cy * this.tk;
  var x4 = x3 * this.cp - z3 * this.sp, z4 = x3 * this.sp + z3 * this.cp;
  var s = this.Fc / Math.max(this.Fc * 0.25, this.Fc * (1 + this.dz) + z4);
  var wx = x4 * s * this.K, wy = y3 * s * this.K;
  var lx = this.px + wx * this.ca - wy * this.sa, ly = this.py + wx * this.sa + wy * this.ca;
  // the flips mirror on screen round the anchor (left / right, up / down)
  var g = this.fr.d(lx, ly);
  return [this.fr.ox + g[0] * this.fx_, this.fr.oy + g[1] * this.fy_];
};
// Local angle (degrees) from the anchor to the target at tick, held within
// +-75 degrees of forward, and the distance.
function aimAng(inst, tick) {
  var o = at(inst.tq_path, tick), tp = at(inst.tq_tp, tick), dx = tp[0] - o[0], dy = tp[1] - o[1];
  var fr = new (L_().Frame)(0, 0, inst.tq_f, inst.tq_m);
  var lx = dx * fr.fx + dy * fr.fy, ly = dx * fr.vx + dy * fr.vy;
  if (Math.abs(lx) + Math.abs(ly) < 1e-6) return [0, 0];
  return [Math.max(-75, Math.min(75, Math.atan2(ly, lx) / L_().D)), Math.hypot(lx, ly)];
}
function recoil(w, P, slot, tick) {
  var k = 0;
  for (var i = 0; i < w.fire.length; i++) {
    var f = w.fire[i];
    if (f[1] !== slot) continue;
    var a = tick - tickOf(P, f[0]);
    if (a >= 0 && a < 12) k += Math.exp(-a / 2.5);
  }
  return Math.min(1.5, k);
}
// The XF of weapon slot `slot` at tick (fractional ticks allowed).
function xf(inst, ps, slot, tick) {
  var P = inst.fx.params, w = W_(P), md = MODELS[w.models[slot]], L = L_();
  var ph = phase(P, inst.life, tick), ap = ph[1];
  var rows = w.tracks[slot];
  var q = sig(P) ? track(rows, ph[0]) : rows[0].slice(1, 8);
  var x = q[0], y = q[1], r = q[2], ang = q[3], yaw = q[4], pitch = q[5], sc = q[6];
  if (!sig(P)) y += Math.sin(tick * 0.12) * 0.15;
  var Lp = Math.max(1, +P.length || 40) * ps;
  var Wp = md.vs === "l" ? Lp : Math.max(0.5, +P.thickness || 4) * ps;
  var Gs = P.w_scale != null ? +P.w_scale : 1;
  var dz = Math.max(-0.75, +P.w_depth || 0);
  var ad = w.aim ? aimAng(inst, tick) : [0, 0], aa = ad[0], dist = ad[1];
  ang += aa;
  if (w.shot) {
    var kick = recoil(w, P, slot, tick);
    ang -= 9 * kick;
    x -= 0.25 * kick;
  }
  var o = new XF(), p0 = at(inst.tq_path, tick);
  o.fr = new L.Frame(p0[0], p0[1], inst.tq_f, inst.tq_m);
  o.Y = (yaw + (+P.w_yaw || 0) + (+P.w_spin || 0) * tick) * L.D;
  o.Pt = (pitch + (+P.w_pitch || 0)) * L.D;
  o.cy = Math.cos(o.Y); o.sy = Math.sin(o.Y);
  o.cp = Math.cos(o.Pt); o.sp = Math.sin(o.Pt);
  o.ca = Math.cos(ang * L.D); o.sa = Math.sin(ang * L.D);
  o.L = Lp; o.W = Wp;
  o.tk = THICK_K * (md.vs === "w" ? Wp : Lp * 0.06);
  o.Fc = FOCAL * Lp;
  o.dz = dz;
  var s0 = 1 / (1 + dz);
  var K = sc * Gs * (0.75 + 0.25 * L.easeOut3(ap));
  o.K = K;
  var hx = x * HU * ps, hy = y * HU * ps;
  if (r > 0 && w.aim) {
    // reach toward the target: the blade tip lands on it at r = 1
    var reach = Math.max(0, Math.min(dist, (+P.radius || 0) * ps) - md.hit[2] * Lp * K);
    hx += Math.cos(aa * L.D) * reach * r;
    hy += Math.sin(aa * L.D) * reach * r;
  }
  o.px = hx * s0 * Gs; o.py = hy * s0 * Gs;
  o.fx_ = P.w_flip_x != null ? +P.w_flip_x : 1;
  o.fy_ = P.w_flip_y != null ? +P.w_flip_y : 1;
  o.nz = o.cy * o.cp;
  o.m = md;
  return o;
}
// Slot's cutting line: [x0, y0, x1, y1, half width] in world px.
function seg(o) {
  var h = o.m.hit, a = o.pt(h[0], h[1]), b = o.pt(h[2], h[3]);
  return [a[0], a[1], b[0], b[1], h[4] * o.W * Math.abs(o.K) * Math.max(0.35, Math.abs(o.cy))];
}
function slots(P) { return W_(P).models.length; }
function evPos(inst, ps, e, tick) {
  var a = e[2], s;
  if (a === "target") return at(inst.tq_tp, tick);
  if (a === "mid") { s = seg(xf(inst, ps, 0, tick)); return [(s[0] + s[2]) * 0.5, (s[1] + s[3]) * 0.5]; }
  s = seg(xf(inst, ps, a === "tip1" ? 1 : 0, tick));
  return [s[2], s[3]];
}

// ---------------------------------------------------------------- shots
// One shot: everything about it is rolled from the seed.
function Shot(inst, ps, i, f) {
  var P = inst.fx.params, w = W_(P), r = L_().rngFor(inst.seed, i, 47);
  this.i = i;
  this.b = tickOf(P, f[0]);
  this.kind = w.shot;
  var o = xf(inst, ps, f[1], this.b), mu = o.m.muzzle[0], mv = o.m.muzzle[1];
  var m = o.pt(mu, mv), a = o.pt(mu - 0.2, mv);
  this.ox = m[0]; this.oy = m[1];
  var dx = this.ox - a[0], dy = this.oy - a[1];
  if ((inst.fx.motion || {}).aim === "target") {
    var tp = at(inst.tq_tp, this.b);
    if (Math.hypot(tp[0] - this.ox, tp[1] - this.oy) > 4) { dx = tp[0] - this.ox; dy = tp[1] - this.oy; }
  }
  var d = Math.hypot(dx, dy) || 1;
  var sp = FXK().rot([dx / d, dy / d], r.uniform(-0.5, 0.5) * (+P.span || 0));
  this.dx = sp[0]; this.dy = sp[1];
  var g = SHOTS[this.kind];
  this.size = g.size * r.uniform(0.9, 1.1);
  var R = Math.max(20, +P.radius || 0);
  this.rng = R * ps;
  this.sp = g.speed * ps;
  this.flight = LINE_T[this.kind] !== undefined ? LINE_T[this.kind] : Math.ceil(R / g.speed);
}
Shot.prototype.pos = function (k) { var d = this.sp * k; return [this.ox + this.dx * d, this.oy + this.dy * d]; };
Shot.prototype.end = function (inst) {   // [tick it stops, stopped by a hit?]
  var h = inst.tq_ki[this.i];
  return h ? [h[0], true] : [this.b + this.flight, false];
};
function shots(inst, ps) {
  var P = inst.fx.params, out = [];
  if (!sig(P)) return out;
  var fire = W_(P).fire;
  for (var i = 0; i < fire.length; i++) {
    if (tickOf(P, fire[i][0]) > inst.age) break;
    out.push(new Shot(inst, ps, i, fire[i]));
  }
  return out;
}
function live(inst, ps) {
  var out = [], all = shots(inst, ps);
  for (var i = 0; i < all.length; i++) {
    var s = all[i];
    if (LINE_T[s.kind] !== undefined) continue;
    if (inst.age < s.end(inst)[0]) out.push([s, s.pos(inst.age - s.b)]);
  }
  return out;
}
function fires(style) { return WEAPONS[style] !== undefined && WEAPONS[style].shot !== "" && LINE_T[WEAPONS[style].shot] === undefined; }
// [[i, x, y, vx, vy]] for the shots in flight this tick.  laser/weaponfx.py live_points.
function livePoints(inst, ps) {
  return live(inst, ps).map(function (q) { var s = q[0]; return [s.i, q[1][0], q[1][1], s.dx * s.sp, s.dy * s.sp]; });
}

// ---------------------------------------------------------------- public
function bladeLive(inst, P) {
  if (!sig(P)) return inst.age < inst.life;
  return SUMMON <= inst.age && inst.age <= SUMMON + moveT(P);
}
function hit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var P = inst.fx.params, w = W_(P), t = inst.age, i, p, s;
  var segDist = FXK().segDist;
  if (bladeLive(inst, P)) {
    for (var sl = 0; sl < slots(P); sl++) {
      var o = xf(inst, ps, sl, t);
      if (!o.m.blade || Math.abs(o.K) < 0.05) continue;
      s = seg(o);
      if (segDist(tx, ty, s[0], s[1], s[2], s[3]) <= hr + s[4]) return true;
    }
  }
  if (!sig(P)) return false;
  for (i = 0; i < w.events.length; i++) {
    var e = w.events[i], R = EVT_R[e[1]];
    if (R <= 0) continue;
    var te = tickOf(P, e[0]);
    if (e[1] === "runes") {
      var bs = [6, 12, 18];
      for (var j = 0; j < 3; j++) {
        if (te + bs[j] <= t && t < te + bs[j] + EVT_HIT) {
          p = evPos(inst, ps, e, te);
          if (Math.hypot(tx - p[0], ty - p[1]) <= hr + R * ps * e[3]) return true;
        }
      }
      continue;
    }
    if (te <= t && t < te + EVT_HIT) {
      p = evPos(inst, ps, e, te);
      if (Math.hypot(tx - p[0], ty - p[1]) <= hr + R * ps * e[3]) return true;
    }
  }
  var lv = live(inst, ps);
  for (i = 0; i < lv.length; i++) {
    if (Math.hypot(lv[i][1][0] - tx, lv[i][1][1] - ty) <= hr + 4 * ps * lv[i][0].size) return true;
  }
  var all = shots(inst, ps);
  for (i = 0; i < all.length; i++) {
    s = all[i];
    if (LINE_T[s.kind] !== undefined && s.b <= t && t < s.end(inst)[0]) {
      var a0 = s.pos(0);
      if (segDist(tx, ty, a0[0], a0[1], s.ox + s.dx * s.rng, s.oy + s.dy * s.rng) <= hr + LINE_HW[s.kind] * ps * s.size) return true;
    }
  }
  return false;
}
// A swinging blade clashes along its cutting line; guns never do.
function body(inst, ps) {
  var P = inst.fx.params;
  if (inst.age >= inst.life || !bladeLive(inst, P)) return null;
  var o = xf(inst, ps, 0, inst.age);
  if (!o.m.blade || Math.abs(o.K) < 0.05) return null;
  var s = seg(o);
  return [[[s[0], s[1]], [s[2], s[3]]], s[4]];
}
// A shot that hit stops there and bursts.
function onHit(inst, x, y, ps) {
  var best = null, bd = null, lv = live(inst, ps);
  for (var i = 0; i < lv.length; i++) {
    var d = Math.hypot(lv[i][1][0] - x, lv[i][1][1] - y);
    if (bd === null || d < bd) { best = lv[i]; bd = d; }
  }
  if (best !== null && bd <= 40 * ps) inst.tq_ki[best[0].i] = [inst.age, best[1][0], best[1][1]];
}

// ================================================================ drawing
function mat(o, role, c) {
  if (role === "spirit") return c;
  var m = o.m.mat;
  return m[role] !== undefined ? m[role] : m.blade;
}
function isGlow(role) { return GLOWS.indexOf(role) >= 0; }
function proj(o, pts, t) { return pts.map(function (p) { return o.pt(p[0], p[1], t); }); }
// The weapon itself: far face, side walls, near face lit by how square-on
// it is, glowing parts, and a glint running along the edge.
function drawWeapon(pen, o, c, a, ps, tick) {
  if (a <= 0.01 || Math.abs(o.K) < 0.02) return;
  var L = L_(), back = o.nz > 0, near = back ? -1 : 1, lit = 0.5 + 0.5 * Math.abs(o.nz), parts = o.m.parts, i, k;
  pen.add(false);
  for (i = 0; i < parts.length; i++) {
    var role = parts[i][0], pts = parts[i][1];
    if (isGlow(role)) continue;
    var far = proj(o, pts, -near), nr = proj(o, pts, near), side = L.mix(mat(o, role, c), L.BLACK, 0.55);
    pen.poly(far, L.mix(mat(o, role, c), L.BLACK, 0.62), 255 * a);
    // the side walls between the two faces: the weapon's thickness
    var n = pts.length;
    for (k = 0; k < n; k++) {
      var j = (k + 1) % n;
      pen.poly([far[k], far[j], nr[j], nr[k]], side, 255 * a);
    }
  }
  var dk = (1 - lit) * 0.75 + (back ? 0.15 : 0);
  for (i = 0; i < parts.length; i++) {
    if (isGlow(parts[i][0])) continue;
    pen.poly(proj(o, parts[i][1], near), L.mix(mat(o, parts[i][0], c), L.BLACK, dk), 255 * a);
  }
  pen.add(true);
  for (i = 0; i < parts.length; i++) {
    var rl = parts[i][0];
    if (!isGlow(rl)) continue;
    var q = proj(o, parts[i][1], near), col = rl === "spirit" ? c : mat(o, "gem", c);
    pen.poly(q, col, (rl === "spirit" ? 150 : 235) * a);
    var cx = 0, cy = 0, rr = 0;
    for (k = 0; k < q.length; k++) { cx += q[k][0]; cy += q[k][1]; }
    cx /= q.length; cy /= q.length;
    for (k = 0; k < q.length; k++) rr = Math.max(rr, Math.hypot(q[k][0] - cx, q[k][1] - cy));
    pen.glow(cx, cy, rr * 0.9 + 3 * ps, col, 80 * a);
  }
  // glint along the cutting line, strongest square-on
  var s = seg(o), x0 = s[0], y0 = s[1], x1 = s[2], y1 = s[3];
  var g = 0.5 + 0.45 * Math.sin((o.Y + o.Pt) * 1.3 + tick * 0.07);
  var st = 190 * a * o.nz * o.nz;
  var gx = x0 + (x1 - x0) * g, gy = y0 + (y1 - y0) * g;
  if (st > 4) {
    var Ls = Math.hypot(x1 - x0, y1 - y0), kk = Math.min(0.12, 6 * ps / Math.max(1, Ls));
    pen.diamond(x0 + (x1 - x0) * (g - kk), y0 + (y1 - y0) * (g - kk), x0 + (x1 - x0) * (g + kk),
      y0 + (y1 - y0) * (g + kk), 1.3 * ps, L.HOT, st);
    pen.glow(gx, gy, 6 * ps * Math.abs(o.K), L.HOT, st * 0.7);
  }
}
// Light rushes in and a scan line runs up the blade as it appears.
function drawSummon(pen, inst, o, c, ps, t) {
  if (t >= SUMMON) return;
  var L = L_(), q = t / SUMMON, s = seg(o), x0 = s[0], y0 = s[1], x1 = s[2], y1 = s[3];
  var mx = (x0 + x1) * 0.5, my = (y0 + y1) * 0.5;
  for (var j = 0; j < 8; j++) {
    var r = L.rngFor(inst.seed, j, 53), an = r.uniform(0, Math.PI * 2);
    var d0 = r.uniform(30, 50) * ps * (1 - L.easeOut3(q)), d1 = d0 + r.uniform(8, 18) * ps * (1 - q);
    var ca = Math.cos(an), sa = Math.sin(an);
    pen.line(mx + ca * d1, my + sa * d1, mx + ca * d0, my + sa * d0, L.mix(c, L.HOT, 0.5), 220 * (1 - q), 1.3 * ps);
  }
  pen.glow(x0 + (x1 - x0) * q, y0 + (y1 - y0) * q, 9 * ps, L.HOT, 230 * (1 - q * 0.5));
  pen.glow(mx, my, 18 * ps * (1 - q), c, 160 * (1 - q));
}
// Motes drift off the blade as it dissolves.
function drawDismiss(pen, inst, o, c, ps, t) {
  var k = t - inst.life;
  if (k < 0 || k >= DISMISS + 10) return;
  var L = L_(), s = seg(o), x0 = s[0], y0 = s[1], x1 = s[2], y1 = s[3];
  var n = Math.max(0, Math.round(10 * (+inst.fx.params.density || 1)));
  for (var j = 0; j < n; j++) {
    var r = L.rngFor(inst.seed, j, 57), u = r(), life = r.uniform(10, 20);
    if (k >= life) continue;
    var q = k / life, px = x0 + (x1 - x0) * u, py = y0 + (y1 - y0) * u;
    px += r.uniform(-6, 6) * ps * q;
    py -= r.uniform(4, 18) * ps * q;
    pen.glow(px, py, 3.2 * ps * (1 - q) + 0.5, L.mix(c, L.HOT, 0.4), 220 * (1 - q));
  }
}
// A swept ribbon between where the tip and the inner end of the trail band
// were over the last TRAIL_N ticks.
function drawTrail(pen, inst, ps, c, sl, t) {
  var P = inst.fx.params, L = L_(), t0 = SUMMON, t1 = SUMMON + moveT(P);
  if (t < t0 || t > t1 + TRAIL_N) return;
  var pts = [];
  for (var i = 0; i < TRAIL_N * TRAIL_SUB + 1; i++) {
    var tt = Math.min(t, t1) - i / TRAIL_SUB;
    if (tt < t0) break;
    var s = seg(xf(inst, ps, sl, tt));
    pts.push([s[2], s[3], s[0] + (s[2] - s[0]) * TRAIL_BAND, s[1] + (s[3] - s[1]) * TRAIL_BAND]);
  }
  var fade = t <= t1 ? 1 : 1 - (t - t1) / TRAIL_N, bright = L.mix(c, L.HOT, 0.45), n = pts.length;
  for (var k = 0; k < n - 1; k++) {
    var a = pts[k], b = pts[k + 1], q = k / Math.max(1, n - 1);
    pen.poly([[a[0], a[1]], [b[0], b[1]], [b[2], b[3]], [a[2], a[3]]], c, 110 * (1 - q) * fade);
    pen.line(a[0], a[1], b[0], b[1], bright, 230 * (1 - q) * fade, 2.0 * ps * (1 - q) + 0.3);
  }
}
// Afterimages: the blade's outline where it was a few ticks ago.
function drawGhosts(pen, inst, ps, c, sl, t) {
  var P = inst.fx.params;
  if (t < SUMMON || t > SUMMON + moveT(P) + 6) return;
  [2, 4, 6].forEach(function (k) {
    var tt = t - k;
    if (tt < SUMMON) return;
    var o = xf(inst, ps, sl, tt), near = o.nz > 0 ? -1 : 1;
    o.m.parts.forEach(function (pt) {
      if (pt[0] === "grip" || pt[0] === "dark") return;
      pen.poly(proj(o, pt[1], near), c, 70 * (1 - k / 8));
    });
  });
}

// ---------------------------------------------------------------- events
function spikes(pen, x, y, ang, n, ro, ri, c, a) {
  var pts = [];
  for (var j = 0; j < 2 * n; j++) {
    var rr = j % 2 === 0 ? ro : ri, an = ang + Math.PI * j / n;
    pts.push([x + Math.cos(an) * rr, y + Math.sin(an) * rr]);
  }
  pen.poly(pts, c, a);
}
function evSlam(pen, inst, c, ps, x, y, a, k, salt) {
  var L = L_(), life = EVT_LIFE.slam, q = a / life, j;
  if (a < 5) pen.glow(x, y, (26 + 30 * L.easeOut3(a / 5)) * ps * k, L.HOT, 255 * (1 - a / 5));
  var e = L.easeOut3(q);
  [[0, 1], [4, 1.5]].forEach(function (dk) {
    var aa = a - dk[0];
    if (aa < 0) return;
    var qq = aa / (life - dk[0]), ee = L.easeOut3(qq), rr = (10 + 60 * ee) * ps * k * dk[1];
    pen.ring(x, y, rr, rr * 0.28, 0, c, 210 * (1 - qq), 3.2 * ps * (1 - qq) + 0.3);
    pen.ring(x, y, rr, rr * 0.28, 0, L.HOT, 150 * Math.pow(1 - qq, 2), 1.2 * ps * (1 - qq) + 0.2);
  });
  pen.glow(x, y, (20 + 26 * e) * ps * k, c, 150 * (1 - q), 0.4);
  var dens = +inst.fx.params.density || 1;
  // cracks running along the ground
  for (j = 0; j < 6; j++) {
    var r = L.rngFor(inst.seed, j, 71 + salt), side = j % 2 === 0 ? 1 : -1;
    var Lc = r.uniform(30, 60) * ps * k * L.easeOut3(Math.min(1, a / 6)), pts = [[x, y]];
    for (var s = 1; s < 5; s++) pts.push([x + side * Lc * s / 4, y + r.uniform(-4, 4) * ps + r.uniform(-0.15, 0.15) * Lc * s / 4]);
    pen.polyline(pts, L.mix(c, L.HOT, 0.5), 230 * (1 - q), 1.6 * ps);
  }
  // rocks thrown up
  pen.add(false);
  var n = Math.max(0, Math.round(8 * dens * k));
  for (j = 0; j < n; j++) {
    var rk = L.rngFor(inst.seed, j, 73 + salt), lj = rk.uniform(16, 26);
    if (a >= lj) continue;
    var vx = rk.uniform(-3.5, 3.5) * ps, vy = rk.uniform(-7, -3.5) * ps;
    var px = x + vx * a, py = y + vy * a + 0.35 * ps * a * a, sz = rk.uniform(1.6, 3.8) * ps * k;
    var rot = rk.uniform(0, 6.28) + a * 0.3, tri = [];
    for (var i = 0; i < 3; i++) tri.push([px + Math.cos(rot + i * 2.1) * sz, py + Math.sin(rot + i * 2.1) * sz]);
    pen.poly(tri, L.mix([90, 80, 70], c, 0.15), 230 * (1 - a / lj));
  }
  pen.add(true);
}
function evCuts(pen, inst, c, ps, x, y, a, n, salt) {
  var L = L_(), life = EVT_LIFE.cuts, bright = L.mix(c, L.HOT, 0.5);
  for (var j = 0; j < n; j++) {
    var aj = a - j;
    if (aj < 0 || aj >= life - 4) continue;
    var r = L.rngFor(inst.seed, j, 77 + salt), an, Lc, ox, oy;
    if (n === 1) { an = r.uniform(-0.1, 0.1); Lc = 120 * ps; ox = 0; oy = 0; }
    else { an = r.uniform(0, Math.PI); Lc = r.uniform(40, 70) * ps; ox = r.uniform(-12, 12) * ps; oy = r.uniform(-12, 12) * ps; }
    var q = aj / (life - 4), e = L.easeOut3(Math.min(1, aj / 2)), ux = Math.cos(an), uy = Math.sin(an);
    var cx = x + ox, cy = y + oy, hl = Lc * (0.4 + 0.6 * e);
    pen.diamond(cx - ux * hl, cy - uy * hl, cx + ux * hl, cy + uy * hl, 2.6 * ps * (1 - q) + 0.3, c, 230 * (1 - q));
    pen.diamond(cx - ux * hl * 0.9, cy - uy * hl * 0.9, cx + ux * hl * 0.9, cy + uy * hl * 0.9, 0.9 * ps * (1 - q) + 0.2, L.HOT, 255 * (1 - q));
  }
  // the delayed burst when every cut lands at once
  var b = a - (n + 2);
  if (b >= 0 && b < 10) {
    var qb = b / 10;
    pen.glow(x, y, (22 + 30 * L.easeOut3(qb)) * ps, bright, 230 * (1 - qb));
    var rr = (8 + 40 * L.easeOut3(qb)) * ps;
    pen.ring(x, y, rr, rr, 0, c, 200 * (1 - qb), 2.4 * ps * (1 - qb) + 0.2);
  }
}
function evXflash(pen, inst, c, ps, x, y, a, k, spread) {
  var L = L_(), life = EVT_LIFE.xflash, q = a / life, e = L.easeOut3(Math.min(1, a / 4));
  var ang = Math.atan2(inst.tq_f[1], inst.tq_f[0]), Lx = (22 + 14 * e) * ps * k;
  [1, -1].forEach(function (sg) {
    var an = ang + sg * spread * L.D, ux = Math.cos(an), uy = Math.sin(an);
    pen.diamond(x - ux * Lx, y - uy * Lx, x + ux * Lx, y + uy * Lx, 3.4 * ps * k * (1 - q) + 0.3, c, 230 * (1 - q));
    pen.diamond(x - ux * Lx * 0.9, y - uy * Lx * 0.9, x + ux * Lx * 0.9, y + uy * Lx * 0.9, 1.2 * ps * (1 - q) + 0.2, L.HOT, 255 * (1 - q));
  });
  var rr = (6 + 26 * L.easeOut3(q)) * ps * k;
  pen.ring(x, y, rr, rr, 0, c, 200 * (1 - q), 2.0 * ps * (1 - q) + 0.2);
  if (a < 6) pen.glow(x, y, 20 * ps * k, L.HOT, 255 * (1 - a / 6));
}
function evPillar(pen, inst, c, ps, x, y, a, k) {
  var L = L_(), life = EVT_LIFE.pillar, q = a / life, e = L.easeOut3(Math.min(1, a / 5));
  var H = 260 * ps * e, w = 14 * ps * k * (1 - q) * (0.85 + 0.15 * Math.sin(a * 1.7));
  pen.poly([[x - w, y], [x - w * 0.6, y - H], [x + w * 0.6, y - H], [x + w, y]], c, 170 * (1 - q));
  pen.poly([[x - w * 0.4, y], [x - w * 0.2, y - H], [x + w * 0.2, y - H], [x + w * 0.4, y]], L.HOT, 230 * (1 - q));
  for (var j = 0; j < 3; j++) {
    var rr = (14 + 40 * L.easeOut3(Math.min(1, (a - j * 3) / 14))) * ps * k;
    if (a < j * 3) continue;
    pen.ring(x, y, rr, rr * 0.3, 0, c, 200 * (1 - q), 2.4 * ps * (1 - q) + 0.2);
  }
  if (a < 6) pen.glow(x, y, 40 * ps * k, L.HOT, 255 * (1 - a / 6));
  pen.glow(x, y, 30 * ps * k * (1 - q), c, 160 * (1 - q));
}
function runeRing(pen, inst, c, ps, x, y, R, ry, rot, a8, alpha, salt) {
  var L = L_();
  pen.ring(x, y, R, ry, 0, c, alpha, 1.6 * ps);
  pen.ring(x, y, R * 0.8, ry * 0.8, 0, L.mix(c, L.HOT, 0.4), alpha * 0.8, 1.0 * ps);
  for (var j = 0; j < 8; j++) {
    var an = rot + j * Math.PI / 4, gx = x + Math.cos(an) * R * 0.9, gy = y + Math.sin(an) * ry * 0.9;
    var sz = L.rngFor(inst.seed, j, 81 + salt).uniform(2.5, 4.0) * ps;
    pen.diamond(gx - sz, gy, gx + sz, gy, sz * 0.6, L.HOT, alpha * a8);
  }
}
function evRunes(pen, inst, c, ps, x, y, a, k, salt) {
  var L = L_(), life = EVT_LIFE.runes, q = a / life, e = L.easeOut3(Math.min(1, a / 6)), R = 36 * ps * k * e;
  runeRing(pen, inst, c, ps, x, y + 4 * ps, R, R * 0.32, a * 0.08, 1, 220 * (1 - q * q), salt);
  [6, 12, 18].forEach(function (b, j) {
    var ab = a - b;
    if (ab < 0 || ab >= 14) return;
    var r = L.rngFor(inst.seed, j, 83 + salt), bx = x + r.uniform(-10, 10) * ps;
    if (ab < 3) {
      var yy = y - 120 * ps * (1 - ab / 3);
      pen.line(bx, yy - 30 * ps, bx, yy, c, 220, 3.0 * ps);
      pen.line(bx, yy - 30 * ps, bx, yy, L.HOT, 255, 1.2 * ps);
      pen.glow(bx, yy, 8 * ps, L.HOT, 240);
    } else {
      var qb = (ab - 3) / 11;
      pen.glow(bx, y, (14 + 16 * L.easeOut3(qb)) * ps * k, L.mix(c, L.HOT, 0.5), 230 * (1 - qb));
      spikes(pen, bx, y, r.uniform(0, 1), 5, (10 + 10 * L.easeOut3(qb)) * ps * k, 4 * ps * k, L.HOT, 220 * (1 - qb));
    }
  });
}
function evGlyph(pen, inst, c, ps, x, y, a, k, salt) {
  var L = L_(), q = a / EVT_LIFE.glyph, R = (8 + 34 * L.easeOut3(q)) * ps * k;
  runeRing(pen, inst, c, ps, x, y, R, R, a * 0.12, 1, 230 * (1 - q), salt);
  if (a < 5) pen.glow(x, y, 18 * ps * k, L.HOT, 255 * (1 - a / 5));
}
function evBurst(pen, inst, c, ps, x, y, a, k, salt) {
  var L = L_(), q = a / EVT_LIFE.burst;
  if (a < 5) pen.glow(x, y, (14 + 20 * L.easeOut3(a / 5)) * ps * k, L.HOT, 255 * (1 - a / 5));
  pen.glow(x, y, (18 + 18 * L.easeOut3(q)) * ps * k, c, 170 * (1 - q), 0.4);
  for (var j = 0; j < 10; j++) {
    var r = L.rngFor(inst.seed, j, 87 + salt), an = r.uniform(0, Math.PI * 2);
    var r1 = (6 + 30 * L.easeOut3(q)) * ps * k, ln = r.uniform(8, 18) * ps * k * (1 - q), ca = Math.cos(an), sa = Math.sin(an);
    pen.line(x + ca * r1, y + sa * r1, x + ca * (r1 + ln), y + sa * (r1 + ln), L.mix(L.HOT, c, q), 230 * (1 - q), 1.4 * ps);
  }
  var rr = (6 + 30 * L.easeOut3(q)) * ps * k;
  pen.ring(x, y, rr, rr, 0, c, 190 * (1 - q), 2.0 * ps * (1 - q) + 0.2);
}
function evCharge(pen, inst, c, ps, x, y, a, dur, k, salt) {
  if (a >= dur + 3) return;
  var L = L_(), q = Math.min(1, a / Math.max(1, dur)), fade = a < dur ? 1 : 1 - (a - dur) / 3;
  pen.glow(x, y, (4 + 14 * L.easeIn3(q)) * ps * k, c, 200 * fade);
  pen.glow(x, y, (2 + 6 * q) * ps * k, L.HOT, 240 * fade);
  for (var j = 0; j < 8; j++) {
    var r = L.rngFor(inst.seed, j, 89 + salt), per = r.uniform(6, 10);
    var ph = ((a + r.uniform(0, per)) % per) / per, an = r.uniform(0, Math.PI * 2);
    var d0 = (34 * (1 - ph) + 4) * ps * k, d1 = d0 + 10 * ps * k * (1 - ph), ca = Math.cos(an), sa = Math.sin(an);
    pen.line(x + ca * d1, y + sa * d1, x + ca * d0, y + sa * d0, L.mix(c, L.HOT, 0.4), 200 * fade * ph, 1.2 * ps);
  }
  var rr = 26 * ps * k * (1 - q) + 4 * ps;
  pen.ring(x, y, rr, rr, 0, c, 160 * fade * q, 1.4 * ps);
}
function evPetals(pen, inst, ps, c, te, t, salt) {
  var P = inst.fx.params, L = L_(), life = EVT_LIFE.petals, t1 = SUMMON + moveT(P), dens = +P.density || 1;
  pen.add(false);
  for (var tau = Math.max(te, t - life + 1); tau <= Math.min(t, t1); tau++) {
    var n = Math.max(0, Math.round(2 * dens)), s = seg(xf(inst, ps, 0, tau)), x1 = s[2], y1 = s[3];
    for (var j = 0; j < n; j++) {
      var r = L.rngFor(inst.seed, tau * 7 + j, 91 + salt), a = t - tau, q = a / life;
      var vx = r.uniform(-1.5, 1.5) * ps, vy = r.uniform(-1.2, 0.4) * ps;
      var px = x1 + vx * a + Math.sin(a * 0.3 + j) * 3 * ps, py = y1 + vy * a + 0.04 * ps * a * a;
      var rot = r.uniform(0, 6.28) + a * 0.25, sz = r.uniform(1.8, 3.0) * ps, ux = Math.cos(rot) * sz, uy = Math.sin(rot) * sz;
      pen.diamond(px - ux, py - uy, px + ux, py + uy, sz * 0.55, L.mix(c, [200, 20, 40], 0.6), 230 * (1 - q));
    }
  }
  pen.add(true);
}
function evBlink(pen, inst, c, ps, x, y, a, k) {
  var L = L_(), q = a / EVT_LIFE.blink, rr = (20 * (1 - L.easeOut3(q)) + 2) * ps * k;
  pen.ring(x, y, rr, rr, 0, L.mix(c, L.HOT, 0.4), 230 * (1 - q), 2.0 * ps);
  if (a < 4) pen.glow(x, y, 16 * ps * k, L.HOT, 255 * (1 - a / 4));
  pen.glow(x, y, 12 * ps * k * (1 - q), c, 170 * (1 - q));
}
// Void implosion: rings, streaks and a dark sphere collapse to a point, then it pops in a flash and a ring.
function evImplode(pen, inst, c, ps, x, y, a, k, salt) {
  var L = L_(), R = 34 * ps * k, q, e, j, r, an, ca, sa, rr;
  if (a < IMPLODE_IN) {
    q = a / IMPLODE_IN; e = L.easeIn3(q);
    pen.glow(x, y, R * (1 - 0.6 * e), c, 120 + 80 * q);
    for (j = 0; j < 3; j++) {
      rr = R * (1 - e) * (1 - 0.25 * j) + 1.5 * ps;
      pen.ring(x, y, rr, rr, 0, L.mix(c, L.HOT, 0.3 * j), 200 * (0.4 + 0.6 * q), 1.6 * ps);
    }
    for (j = 0; j < 10; j++) {
      r = L.rngFor(inst.seed, j, 93 + salt); an = r.uniform(0, Math.PI * 2);
      var d0 = R * 1.3 * (1 - e) * r.uniform(0.7, 1.1) + 2 * ps, d1 = d0 + 9 * ps * k * (1 - q);
      ca = Math.cos(an); sa = Math.sin(an);
      pen.line(x + ca * d1, y + sa * d1, x + ca * d0, y + sa * d0, L.mix(c, L.HOT, 0.4), 210 * q, 1.2 * ps);
    }
    pen.add(false);
    pen.glow(x, y, (4 + 0.55 * R / ps * (1 - e)) * ps, VOID, 235, 0.7);
    pen.add(true);
    return;
  }
  var b = a - IMPLODE_IN;
  q = b / (EVT_LIFE.implode - IMPLODE_IN);
  if (b < 4) pen.glow(x, y, (10 + 18 * L.easeOut3(b / 4)) * ps * k, L.HOT, 255 * (1 - b / 4));
  pen.glow(x, y, (14 + 26 * L.easeOut3(q)) * ps * k, c, 190 * (1 - q), 0.4);
  for (j = 0; j < 8; j++) {
    r = L.rngFor(inst.seed, j, 95 + salt); an = r.uniform(0, Math.PI * 2);
    var r1 = (4 + 34 * L.easeOut3(q)) * ps * k, ln = r.uniform(8, 16) * ps * k * (1 - q);
    ca = Math.cos(an); sa = Math.sin(an);
    pen.line(x + ca * r1, y + sa * r1, x + ca * (r1 + ln), y + sa * (r1 + ln), L.mix(L.HOT, c, q), 230 * (1 - q), 1.3 * ps);
  }
  rr = (4 + 40 * L.easeOut3(q)) * ps * k;
  pen.ring(x, y, rr, rr, 0, c, 220 * (1 - q), 2.2 * ps * (1 - q) + 0.2);
  pen.add(false);
  pen.glow(x, y, 6 * ps * k * (1 - q), VOID, 220 * (1 - q), 0.7);
  pen.add(true);
}
function drawEvents(pen, inst, ps, c, t) {
  var P = inst.fx.params;
  if (!sig(P)) return;
  W_(P).events.forEach(function (e, n) {
    var kind = e[1], te = tickOf(P, e[0]), a = t - te, p;
    if (kind === "petals") { if (a >= 0) evPetals(pen, inst, ps, c, te, t, n * 13); return; }
    if (kind === "charge") {
      var dur = Math.round(e[4] * moveT(P));
      if (a >= 0 && a < dur + 3) { p = evPos(inst, ps, e, t); evCharge(pen, inst, c, ps, p[0], p[1], a, dur, e[3], n * 13); }
      return;
    }
    if (a < 0 || a >= EVT_LIFE[kind]) return;
    p = evPos(inst, ps, e, te);
    var x = p[0], y = p[1], k = e[3];
    if (kind === "slam") evSlam(pen, inst, c, ps, x, y, a, k, n * 13);
    else if (kind === "cuts") evCuts(pen, inst, c, ps, x, y, a, Math.trunc(k), n * 13);
    else if (kind === "xflash") evXflash(pen, inst, c, ps, x, y, a, k, 45);
    else if (kind === "snip") evXflash(pen, inst, c, ps, x, y, a, k, 18);
    else if (kind === "pillar") evPillar(pen, inst, c, ps, x, y, a, k);
    else if (kind === "runes") evRunes(pen, inst, c, ps, x, y, a, k, n * 13);
    else if (kind === "glyph") evGlyph(pen, inst, c, ps, x, y, a, k, n * 13);
    else if (kind === "burst") evBurst(pen, inst, c, ps, x, y, a, k, n * 13);
    else if (kind === "blink") evBlink(pen, inst, c, ps, x, y, a, k);
    else if (kind === "implode") evImplode(pen, inst, c, ps, x, y, a, k, n * 13);
  });
}

// ---------------------------------------------------------------- shots drawing
function drawShots(pen, inst, ps, c, t) {
  var L = L_();
  shots(inst, ps).forEach(function (s) {
    var k = t - s.b, en = s.end(inst), e = en[0], stopped = en[1], sz = s.size * ps, bright = L.mix(c, L.HOT, 0.5), q, x, y, p, tp, j;
    // muzzle flash
    if (k < 4) {
      q = k / 4;
      pen.glow(s.ox, s.oy, (8 + 8 * q) * sz, c, 220 * (1 - q));
      L.star(pen, s.ox, s.oy, s.dx, s.dy, 12 * sz * (1 - 0.4 * q), 5 * sz, L.HOT, 230 * (1 - q), 1.2 * ps);
    }
    if (s.kind === "beam") {
      if (t < e) {
        q = k / BEAM_T;
        var Lb = s.rng * L.easeOut3(Math.min(1, k / 2)), x2 = s.ox + s.dx * Lb, y2 = s.oy + s.dy * Lb;
        var wd = (7 + 2 * Math.sin(k * 1.9)) * sz * (1 - q * q);
        pen.line(s.ox, s.oy, x2, y2, c, 200, wd * 2.0);
        pen.line(s.ox, s.oy, x2, y2, bright, 230, wd);
        pen.line(s.ox, s.oy, x2, y2, L.HOT, 255, wd * 0.4);
        for (j = 0; j < 4; j++) {
          var u = (k * 0.11 + j * 0.25) % 1.0;
          pen.ring(s.ox + s.dx * Lb * u, s.oy + s.dy * Lb * u, 3 * sz, wd * 1.3, Math.atan2(s.dy, s.dx), L.HOT, 160 * (1 - q), 1.0 * ps);
        }
        pen.glow(x2, y2, wd * 2.4, c, 200 * (1 - q));
      }
      return;
    }
    if (s.kind === "rail") {
      if (t < e) {
        // an instant thin line with a black void core, a violet rim and two strands of light twisting round it
        q = k / RAIL_T;
        var xr = s.ox + s.dx * s.rng, yr = s.oy + s.dy * s.rng, wr = 3.0 * sz * (1 - q * q), n = 32;
        pen.line(s.ox, s.oy, xr, yr, c, 150, wr * 3.2);
        pen.line(s.ox, s.oy, xr, yr, bright, 230, wr * 1.5);
        [1, -1].forEach(function (sg) {
          var pts = [];
          for (var jj = 0; jj <= n; jj++) {
            var u = jj / n, o = sg * Math.sin(u * 30 - k * 1.3) * wr * 2.2;
            pts.push([s.ox + s.dx * s.rng * u - s.dy * o, s.oy + s.dy * s.rng * u + s.dx * o]);
          }
          pen.polyline(pts, L.mix(c, L.HOT, 0.3), 200 * (1 - q), 0.9 * ps);
        });
        pen.glow(xr, yr, wr * 3.0, c, 160 * (1 - q));
        pen.add(false);
        pen.line(s.ox, s.oy, xr, yr, VOID, 240, wr * 0.7);
        pen.add(true);
      }
      return;
    }
    if (t < e) {
      p = s.pos(k); x = p[0]; y = p[1];
      if (s.kind === "arrow") {
        tp = s.pos(Math.max(0, k - 2.2));
        pen.diamond(tp[0], tp[1], x, y, 1.6 * sz, c, 200);
        pen.diamond(tp[0], tp[1], x, y, 0.6 * sz, L.HOT, 255);
        [1, -1].forEach(function (sg) {
          pen.line(tp[0], tp[1], tp[0] - s.dx * 5 * sz - s.dy * sg * 4 * sz, tp[1] - s.dy * 5 * sz + s.dx * sg * 4 * sz, bright, 200, 1.2 * ps);
        });
        pen.glow(x, y, 6 * sz, bright, 220);
      } else {
        tp = s.pos(Math.max(0, k - (s.kind === "neon" ? 1.6 : 2.4)));
        pen.diamond(tp[0], tp[1], x, y, 2.4 * sz, c, 190);
        pen.diamond(tp[0], tp[1], x, y, 1.0 * sz, L.HOT, 255);
        pen.glow(x, y, 7 * sz, c, 170);
        if (s.kind === "spark") {
          var pts = [];
          for (j = 0; j < 6; j++) {
            var r = L.rngFor(inst.seed, s.i * 31 + j, t), uu = j / 5;
            var px = tp[0] + (x - tp[0]) * uu, py = tp[1] + (y - tp[1]) * uu, o = r.uniform(-4, 4) * sz;
            pts.push([px - s.dy * o, py + s.dx * o]);
          }
          pen.polyline(pts, bright, 230, 1.1 * ps);
        }
      }
      return;
    }
    var a = t - e;
    if (a >= IMPACT_LIFE) return;
    if (stopped) { var h = inst.tq_ki[s.i]; x = h[1]; y = h[2]; }
    else { p = s.pos(s.flight); x = p[0]; y = p[1]; }
    q = a / IMPACT_LIFE;
    if (a < 4) pen.glow(x, y, (8 + 10 * L.easeOut3(a / 4)) * sz, L.HOT, 255 * (1 - a / 4));
    pen.glow(x, y, (8 + 12 * L.easeOut3(q)) * sz, c, 190 * (1 - q), 0.4);
    var rr = (3 + 14 * L.easeOut3(q)) * sz;
    pen.ring(x, y, rr, rr, 0, bright, 200 * (1 - q), 1.6 * ps * (1 - q) + 0.2);
  });
}
// The bow string, pulled back while it draws, and the nocked arrow.
function drawBow(pen, inst, o, c, a, ps, t) {
  var P = inst.fx.params, w = W_(P), L = L_();
  var ft = (w.fire.length && sig(P)) ? tickOf(P, w.fire[0][0]) : (1 << 30), d0 = tickOf(P, 0.1), pull;
  if (t < d0) pull = 0;
  else if (t < ft) pull = L.easeIn3((t - d0) / Math.max(1, ft - d0));
  else pull = -0.15 * Math.max(0, 1 - (t - ft) / 3);   // the string snaps past rest
  var pu = -0.32 * pull, top = o.pt(0.02, -0.5), bot = o.pt(0.02, 0.5), mid = o.pt(pu, 0);
  pen.add(true);
  pen.polyline([top, mid, bot], L.mix(c, L.HOT, 0.5), 230 * a, 1.1 * ps);
  if (t < ft && sig(P)) {
    var tip = o.pt(pu + 0.62, 0);
    pen.line(mid[0], mid[1], tip[0], tip[1], c, 220 * a, 2.0 * ps);
    pen.line(mid[0], mid[1], tip[0], tip[1], L.HOT, 255 * a, 0.8 * ps);
    pen.glow(tip[0], tip[1], (4 + 6 * pull) * ps, c, 220 * a);
  }
}

function draw(pen, inst, host, ps) {
  var P = inst.fx.params, L = L_(), t = inst.age, c = L.colours(inst, host)[0], w = W_(P), sl;
  var ph = phase(P, inst.life, t), fd = ph[2], a = L.easeOut3(ph[1]) * fd;
  pen.add(true);
  drawEvents(pen, inst, ps, c, t);
  var xfs = [];
  for (sl = 0; sl < slots(P); sl++) xfs.push(xf(inst, ps, sl, t));
  if (sig(P)) {
    for (sl = 0; sl < slots(P); sl++) {
      if (!xfs[sl].m.blade) continue;
      if (w.trail === "swept") drawTrail(pen, inst, ps, c, sl, t);
      else if (w.trail === "ghost") drawGhosts(pen, inst, ps, c, sl, t);
    }
  }
  for (sl = 0; sl < slots(P); sl++) {
    var o = xfs[sl];
    if (fd > 0) {
      drawWeapon(pen, o, c, a, ps, t);
      if (w.models[sl] === "pulse_bow") drawBow(pen, inst, o, c, a, ps, t);
    }
    pen.add(true);
    drawSummon(pen, inst, o, c, ps, t);
    drawDismiss(pen, inst, o, c, ps, t);
  }
  pen.add(true);
  drawShots(pen, inst, ps, c, t);
  L.hitMarks(pen, inst, c, ps, inst.tq_f[0], inst.tq_f[1]);
}

G.WEAPONFX = {STYLES: STYLES, WEAPONS: WEAPONS, MODELS: MODELS, draw: draw, hit: hit, body: body, onHit: onHit,
              activeTicks: activeTicks, totalTicks: totalTicks, fires: fires, livePoints: livePoints};
})(window);
