/* Hyper FX (Daniel 2026-11-26, V3): 10 punching FX + 10 impact FX in the anime hyper-action style (speed & distortion,
 * debris & environment, elemental flavours). Technique styles of the FX Kit "technique" primitive.
 *
 *   Punching FX (pfx_*): what happens round a fist WHILE a character punches. Not a technique with its own fist path:
 *     the effect rides its anchor (default the right hand haR, Motion attached) and reads that hand's real path, so in
 *     V3 (v3/js/fx3d.js drawHyper) it follows the 3D fist of whatever punch clip plays. swing_ticks = ticks from the
 *     effect's start to the contact beat, hold_ticks = how long it lingers after. Visual by default (no damage).
 *   Impact FX (ifx_*): a standalone hit effect, normally started ON the target (anchor "target", Motion static, Aim
 *     target) so the blow's direction = caster -> target. Hits once in its first hit_ticks inside radius (if Deals
 *     damage), hit-stop (hitstop_ticks) on a hit and a camera shake (shake_px) when it bursts.
 *   Transformation FX (tfx_*, Daniel 2026-11-26 "super saiyan transformation 3D FX"): charge (swing_ticks) -> burst ->
 *     a flame aura that stays aura_s seconds after the action, on the fighter's live body (fx3d.js), Stage 1 / 2 / 3.
 *     The burst pushes enemies within radius away with no damage (damage 0 + Knockback, fxlive.js fxShove).
 *
 * Every style is ONE recipe: parts(inst, C) -> a list of shapes in a local blow frame [f forward, v up, s side] (px,
 * already x size scale), a pure function of the effect's age and seed. fx3d.js builds them as cel-shaded 3D shapes;
 * the 2D drawing here (FX Studio, or fx3d render "card") flattens the same list onto the aim plane.
 *   C = {t: age, ps: size scale, path: [[f, v, s] ...] the fist's last positions relative to it now (oldest first,
 *        punches only), sp: fist speed px / tick, gy: the floor's v (px, below = negative), solo}
 *   shape = {k: "sph" | "tube" | "ring" | "shard" | "cube" | "ball", p: [f, v, s], q: [f, v, s] (tube end), r, r1
 *            (tube end radius), n: [f, v, s] (ring axis), st: stretch along d, d: [f, v, s], c: [r, g, b], a: 0..1,
 *            core: false = no white-hot core, ink: x the effect's ink (0 = none), rot: [x, y, z] (chunks)}
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var D = Math.PI / 180, TAU = Math.PI * 2;
var PUNCH = ["pfx_speed_burst", "pfx_afterimage", "pfx_vacuum_cone", "pfx_flame_fist", "pfx_thunder_fist",
  "pfx_frost_fist", "pfx_void_fist", "pfx_cyclone_hook", "pfx_rocket_jab", "pfx_phantom_rush"];
var IMPACT = ["ifx_shock_crater", "ifx_spark_star", "ifx_ripple_dome", "ifx_pierce_through", "ifx_inferno_burst",
  "ifx_thunderclap", "ifx_glacial_shatter", "ifx_void_implosion", "ifx_earthsplitter", "ifx_sonic_boom"];
// Transformation FX (Daniel 2026-11-26, "the super saiyan transformation 3D FX"): charge / scream -> burst -> a golden
// flame aura that stays on the fighter for aura_s seconds after the action, Stage 1 / 2 / 3. The burst pushes enemies
// away with no damage (v3/js/fxlive.js fxHit -> fxShove).
var TRANSFORM = ["tfx_golden_ascension"];
var STYLES = PUNCH.concat(IMPACT, TRANSFORM);
var NAMES = {pfx_speed_burst: "Speed-line burst", pfx_afterimage: "Afterimage fists", pfx_vacuum_cone: "Vacuum cone",
  pfx_flame_fist: "Blazing fist", pfx_thunder_fist: "Thunder knuckle", pfx_frost_fist: "Frost jab", pfx_void_fist: "Void knuckle",
  pfx_cyclone_hook: "Cyclone hook", pfx_rocket_jab: "Rocket jab", pfx_phantom_rush: "Phantom rush",
  ifx_shock_crater: "Shockwave crater", ifx_spark_star: "Spark star", ifx_ripple_dome: "Distortion ripple",
  ifx_pierce_through: "Pierce-through blast", ifx_inferno_burst: "Inferno burst", ifx_thunderclap: "Thunderclap",
  ifx_glacial_shatter: "Glacial shatter", ifx_void_implosion: "Void implosion", ifx_earthsplitter: "Earthsplitter",
  ifx_sonic_boom: "Sonic boom", tfx_golden_ascension: "Golden ascension (Super Saiyan)"};
// shape of each style (applied when the style is picked, FXK.TECH_STYLE_DEFAULTS)
var DEFAULTS = {};
PUNCH.forEach(function (s) { DEFAULTS[s] = {radius: 5, length: 34, swing_ticks: 5, hold_ticks: 9, density: 1, hitstop_ticks: 0, shake_px: 0}; });
IMPACT.forEach(function (s) { DEFAULTS[s] = {radius: 14, length: 46, swing_ticks: 2, hold_ticks: 26, density: 1, hitstop_ticks: 5, shake_px: 7}; });
DEFAULTS.pfx_phantom_rush.hold_ticks = 14; DEFAULTS.pfx_rocket_jab.swing_ticks = 6;
DEFAULTS.ifx_void_implosion.hold_ticks = 32; DEFAULTS.ifx_earthsplitter.length = 80; DEFAULTS.ifx_sonic_boom.length = 70;
DEFAULTS.ifx_thunderclap.hold_ticks = 24; DEFAULTS.ifx_ripple_dome.shake_px = 4;
// transformation: swing_ticks = the charge, aura_s = how long the aura stays after the burst, radius = the burst's push
// reach, length = the light pillar's height. Every look choice is its own setting (Daniel 2026-11-26: "fx-specific
// settings ... make it look like an actual aura"), edited in FX Studio 3D's Transformation panel (TFX_UI below).
DEFAULTS.tfx_golden_ascension = {stage: 1, charge: true, burst: true, aura: true, swing_ticks: 70, aura_s: 20, radius: 60,
  length: 110, density: 1, hitstop_ticks: 0, shake_px: 9,
  // aura shape (the flame sheath round the body)
  aura_size_pct: 100, aura_width_pct: 100, aura_height_pct: 100, aura_base_pct: 60, aura_top_pct: 75, lean_pct: 100, pulse_pct: 30, aura_raise_pct: 50,
  // flames (torn into the sheath by moving noise)
  flame_count: 7, flame_height_pct: 100, flame_speed_pct: 100, flame_chaos_pct: 100, flame_gaps_pct: 40, flame_sharp_pct: 80,
  // colour & glow
  aura_color: "#ffcc30", aura_hot: "#fff6ba", aura_edge: "#e87600", aura_opacity_pct: 75, rim_pct: 100, inner_pct: 18,
  bands: 3, additive: true, inner_layer: true, sparks_pct: 100,
  // lightning
  lightning_pct: 100, bolt_color: "#a0d4ff", bolt_width_pct: 100,
  // charge / burst / ground
  charge_streaks_pct: 100, charge_glow_pct: 100, pillar_width_pct: 100, burst_rings: true, burst_streaks_pct: 100,
  ground_fx: true, cracks_pct: 100, rocks_pct: 100, dust_pct: 100,
  // outer flames (Daniel 2026-11-26 sketch): strands bursting out of the sheath's sides, flaring out, curling up
  outer_flames: false, outer_count: 8, outer_shape: "mixed", outer_spread_pct: 100, outer_from_pct: 5, outer_to_pct: 70,
  outer_length_pct: 100, outer_curl_pct: 100, outer_width_pct: 100, outer_speed_pct: 100, outer_jag_pct: 100,
  outer_color: "hot", outer_opacity_pct: 90,
  // flame layers (Daniel 2026-11-26 sketch): rings stacked from the feet to the top, each a crown of rising spiky flames
  // (the rings themselves are invisible: only their flames show)
  layers: true, layer_count: 6, layer_from_pct: 0, layer_to_pct: 85, layer_height_pct: 100, layer_spread_pct: 108,
  layer_tongues: 12, layer_tongue_pct: 100, layer_flare_pct: 60, layer_spike_pct: 70, layer_speed_pct: 100,
  layer_chaos_pct: 100, layer_color: "main", layer_opacity_pct: 55,
  // off the ground (Daniel 2026-11-28 sketch): the sheath's bottom closes into a round, sphere-like bowl under the feet
  air_close: true, air_round_pct: 100,
  // flame trail (Daniel 2026-11-28 sketch): a comet tail of the same flame along the path the body took; it holds the
  // last trail_ms of the path, so the faster the move the longer it is; it tapers to a point and a long one is thinner
  // (round 2: a long wavy tail; round 3, "one whole, a liquid flame": no second part, the aura's own surface stretches
  // back along the path into the tail, fx3d.js AURA_VS comet stretch)
  trail: true, trail_ms: 260, trail_width_pct: 100, trail_thin_pct: 100, trail_taper_pct: 80, trail_wave_pct: 100, trail_wave_len_pct: 100};
// a setting of a transformation, its default when the effect predates it
function pv(P, k) { var v = P[k]; return v == null || v === "" ? DEFAULTS.tfx_golden_ascension[k] : v; }
function pc(P, k) { return Math.max(0, +pv(P, k) || 0) / 100; }   // a _pct setting as a fraction
function hexRgb(h, d) { var m = /^#?([0-9a-f]{6})$/i.exec(String(h || "")); if (!m) return d; var n = parseInt(m[1], 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
var AFTER = 12;   // ticks the debris / embers keep going after the effect's active time

// element colours: [main, hot, deep]
var EL = {
  fire: [[255, 112, 24], [255, 220, 110], [150, 26, 8]], smoke: [[70, 62, 66], [120, 110, 112], [30, 26, 30]],
  thunder: [[110, 160, 255], [235, 245, 255], [150, 90, 255]], frost: [[120, 215, 255], [232, 250, 255], [40, 120, 210]],
  void: [[140, 50, 235], [235, 140, 255], [16, 0, 34]], wind: [[150, 255, 215], [245, 255, 250], [40, 170, 150]],
  rock: [[128, 100, 80], [196, 172, 140], [70, 54, 44]]};
var ELEMENT = {pfx_flame_fist: "fire", pfx_thunder_fist: "thunder", pfx_frost_fist: "frost", pfx_void_fist: "void",
  pfx_cyclone_hook: "wind", pfx_rocket_jab: "fire", ifx_inferno_burst: "fire", ifx_thunderclap: "thunder",
  ifx_glacial_shatter: "frost", ifx_void_implosion: "void", tfx_golden_ascension: "gold"};
EL.gold = [[255, 204, 48], [255, 246, 186], [232, 118, 0]];
var WHITE = [255, 255, 255], BOLT = [160, 212, 255];

function cl(u) { return u < 0 ? 0 : u > 1 ? 1 : u; }
function eo(u) { u = cl(u); return 1 - Math.pow(1 - u, 3); }
function ei(u) { u = cl(u); return u * u; }
function mix(a, b, k) { return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k]; }
function isHyper(st) { return STYLES.indexOf(st) >= 0; }
function isPunch(st) { return PUNCH.indexOf(st) >= 0; }
function isTransform(st) { return TRANSFORM.indexOf(st) >= 0; }
function st(P) { return P.style; }
function swing(P) { return Math.max(1, Math.trunc(+P.swing_ticks || 1)); }
function hold(P) { return Math.max(1, Math.trunc(+P.hold_ticks || 1)); }
function activeTicks(P) { return isTransform(st(P)) ? Math.max(1, tfx(P).end) : swing(P) + hold(P); }
function totalTicks(P) { return isTransform(st(P)) ? activeTicks(P) + AURA_OUT : activeTicks(P) + AFTER; }
// transformation timeline (ticks): charge c, burst b, aura a; each phase 0 when switched off
var TB = 30, AURA_OUT = 36;
function auraTicks(P) { return P.aura === false ? 0 : Math.max(1, Math.round(Math.max(0, +P.aura_s || 0) * 1000 / ((FXK() && FXK().TICK_MS) || 16))); }
function tfx(P) { var c = P.charge === false ? 0 : swing(P), b = P.burst === false ? 0 : TB, a = auraTicks(P); return {c: c, b: b, a: a, end: c + b + a}; }
function dens(P) { return Math.max(0.2, Math.min(4, +P.density || 1)); }
function R(inst, a, b) {
  return FXK().rng((((inst.seed || 1) >>> 0) ^ Math.imul(a + 1, 0x2C1B3C6D) ^ Math.imul((b || 0) + 1, 0x297A2D39)) >>> 0);
}
// a unit direction deg off +f, turned az round it
function cone(deg, az) { var s = Math.sin(deg * D); return [Math.cos(deg * D), s * Math.cos(az), s * Math.sin(az)]; }
function add(p, d, k) { return [p[0] + d[0] * k, p[1] + d[1] * k, p[2] + d[2] * k]; }
function scl(d, k) { return [d[0] * k, d[1] * k, d[2] * k]; }

// colours of an effect: {m main, h hot, d deep}; elemental styles keep their element unless Colour = palette
function colours(inst, host) {
  var s = st(inst.fx.params), e = ELEMENT[s], lut = host && host.lut;
  var base = lut && G.SWORDFX ? G.SWORDFX.lib.colours(inst, host)[0] : [255, 200, 120];
  if (isTransform(s)) {   // its own three colours (Transformation panel); Colour = palette tints them with the fighter's
    var P = inst.fx.params, m = hexRgb(pv(P, "aura_color"), EL.gold[0]), h = hexRgb(pv(P, "aura_hot"), EL.gold[1]), dd = hexRgb(pv(P, "aura_edge"), EL.gold[2]);
    if (inst.fx.color.mode === "palette") return {m: mix(m, base, 0.6), h: mix(h, base, 0.25), d: mix(dd, base, 0.4), e: "gold"};
    return {m: m, h: h, d: dd, e: "gold"};
  }
  if (e) {
    var E = EL[e];
    if (inst.fx.color.mode === "palette") return {m: mix(E[0], base, 0.6), h: mix(E[1], base, 0.25), d: E[2], e: e};
    return {m: E[0], h: E[1], d: E[2], e: e};
  }
  return {m: base, h: mix(base, WHITE, 0.6), d: mix(base, [0, 0, 0], 0.7), e: ""};
}

// ---------------------------------------------------------------- shape builders
function Sh(out) { this.o = out; }
Sh.prototype.sph = function (p, r, c, a, x) { if (r > 0.05 && a > 0.01) this.o.push(Object.assign({k: "sph", p: p, r: r, c: c, a: cl(a)}, x || {})); };
Sh.prototype.tube = function (p, q, r0, r1, c, a, x) { if (a > 0.01 && (r0 > 0.02 || r1 > 0.02)) this.o.push(Object.assign({k: "tube", p: p, q: q, r: r0, r1: r1, c: c, a: cl(a)}, x || {})); };
Sh.prototype.ring = function (p, n, R0, c, a, x) { if (R0 > 0.1 && a > 0.01) this.o.push(Object.assign({k: "ring", p: p, n: n, r: R0, c: c, a: cl(a)}, x || {})); };
// the transformation's flame sheath: base point p (the feet), radius r, height h (px), lean [f, v, s] px at the top,
// its look in o.look (fx3d.js builds it as one noise-torn shader shell; the 2D card draws a glow)
Sh.prototype.aura = function (p, r, h, lean, c, a, x) { if (r > 0.1 && h > 0.1 && a > 0.01) this.o.push(Object.assign({k: "aura", p: p, r: r, h: h, lean: lean, c: c, a: cl(a)}, x || {})); };
Sh.prototype.chunk = function (k, p, r, rot, c, a, x) { if (r > 0.05 && a > 0.01) this.o.push(Object.assign({k: k, p: p, r: r, rot: rot, c: c, a: cl(a)}, x || {})); };
// a jagged bolt from A to B: tube segments, offsets round the line
Sh.prototype.bolt = function (A, B, n, jag, w, c, a, rnd, x) {
  var prev = A;
  for (var i = 1; i <= n; i++) {
    var u = i / n, j = i < n ? jag * (1 - Math.abs(u - 0.5)) : 0;
    var q = [A[0] + (B[0] - A[0]) * u + (rnd() - 0.5) * j, A[1] + (B[1] - A[1]) * u + (rnd() - 0.5) * j * 2, A[2] + (B[2] - A[2]) * u + (rnd() - 0.5) * j * 2];
    this.tube(prev, q, w, w * 0.8, c, a, x); prev = q;
  }
};
// a thrown chunk: from p0 along d at speed sp px / tick, gravity g, rests on the floor gy
function thrown(p0, d, sp, age, g, gy) {
  var p = [p0[0] + d[0] * sp * age * Math.pow(0.95, age * 0.5), p0[1] + d[1] * sp * age - 0.5 * g * age * age, p0[2] + d[2] * sp * age * Math.pow(0.95, age * 0.5)];
  if (gy != null && p[1] < gy + 0.5) p[1] = gy + 0.5;
  return p;
}
// the fist's path point back k ticks (0 = now)
function back(C, k) { var P = C.path, n = P.length; if (!n) return [-k * 2.5 * C.ps, 0, 0]; return P[Math.max(0, n - 1 - k)]; }

// ================================================================ punching FX
// drive = 0 at the start .. 1 at contact; after = 0 at contact .. 1 at the end of hold
function punchT(P, t) { var T = swing(P); return {T: T, drive: cl(t / T), after: t < T ? 0 : cl((t - T) / hold(P)), hit: t >= T, near: Math.max(0, 1 - Math.abs(t - T) / 2.5)}; }

var PF = {};
// 1 Speed-line burst: streaks streaming off the fist along its path, then a cone of speed lines + a snapping ring at contact
PF.pfx_speed_burst = function (sh, inst, C, P, K) {
  var k = punchT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, n = Math.round(9 * dens(P)), i, rnd;
  if (!k.hit || k.after < 0.35) {
    var fade = k.hit ? 1 - k.after / 0.35 : 0.4 + 0.6 * k.drive;
    for (i = 0; i < n; i++) {
      rnd = R(inst, 1, i); var az = rnd() * TAU, off = r * (0.6 + rnd() * 1.4), o = [0, Math.cos(az) * off, Math.sin(az) * off];
      var b = back(C, 3 + Math.floor(rnd() * 3)), len = 0.6 + rnd() * 0.8;
      sh.tube(add(scl(b, len), o, 1), o, 0, r * 0.14, rnd() < 0.3 ? WHITE : K.h, fade * (0.5 + rnd() * 0.5), {core: false, ink: 0});
    }
    sh.sph([0, 0, 0], r * (0.55 + 0.35 * k.drive), K.h, 0.85 * fade, {st: 1 + Math.min(2.5, C.sp * 0.25), d: [1, 0, 0]});
  }
  if (k.hit) {
    var a = 1 - k.after, e = eo(k.after * 2.2);
    for (i = 0; i < n + 4; i++) {
      rnd = R(inst, 2, i); var d = cone(8 + rnd() * 34, rnd() * TAU), s0 = r * 0.8 + L * 0.25 * e, s1 = s0 + L * (0.35 + rnd() * 0.5) * (1 - k.after * 0.7);
      sh.tube(scl(d, s0), scl(d, s1), r * 0.16, 0, i % 3 ? K.h : WHITE, a, {core: false, ink: 0});
    }
    sh.ring([r * 0.6 + L * 0.2 * e, 0, 0], [1, 0, 0], r * (1 + 3 * e), WHITE, a * 0.9, {ink: 0.5});
    sh.ring([r * 0.3 + L * 0.1 * e, 0, 0], [1, 0, 0], r * (0.8 + 1.6 * e), K.m, a, {ink: 0.5});
    if (k.after < 0.25) sh.sph([r * 0.4, 0, 0], r * (1.6 - k.after * 4), WHITE, 1 - k.after * 4, {ink: 0});
  }
};
// 2 Afterimage fists: ghost fists left along the path, a hot smear between them, the last ghost snaps forward on contact
PF.pfx_afterimage = function (sh, inst, C, P, K) {
  var k = punchT(P, C.t), r = +P.radius * C.ps, n = Math.round(4 * dens(P)) + 1, i;
  var keep = k.hit ? 1 - k.after : 1;
  for (i = n; i >= 1; i--) {
    var rnd = R(inst, 3, i), b = back(C, i * 1.5 | 0), wob = [0, (rnd() - 0.5) * r * 0.8, (rnd() - 0.5) * r * 0.8], q = add(b, wob, 1);
    var al = keep * (0.75 - i / (n + 1) * 0.6);
    sh.sph(q, r * (1.05 - i * 0.05), i % 2 ? K.m : K.h, al, {ink: 0.6, core: i === 1});
    if (i > 1) sh.tube(add(back(C, (i - 1) * 1.5 | 0), wob, 1), q, r * 0.5, r * 0.25, K.m, al * 0.6, {core: false, ink: 0});
  }
  sh.tube(back(C, 2), [0, 0, 0], r * 0.35, r * 0.9, K.h, (k.hit ? 1 - k.after : 0.6 + 0.4 * k.drive), {ink: 0.5});
  sh.sph([0, 0, 0], r * 1.1, WHITE, k.hit ? 1 - k.after : 0.7, {st: 1 + Math.min(2, C.sp * 0.2), d: [1, 0, 0], ink: 0.8});
  if (k.hit && k.after < 0.6) {   // the ghost fists overshoot past the knuckles
    for (i = 0; i < 3; i++) { var u = eo(k.after / 0.6), rr = R(inst, 4, i);
      sh.sph([r * (1.5 + i * 1.6) * (0.4 + u), (rr() - 0.5) * r, (rr() - 0.5) * r], r * (0.9 - i * 0.15), K.h, (1 - u) * (0.7 - i * 0.15), {core: false, ink: 0.4}); }
  }
};
// 3 Vacuum cone: stacked pressure rings drawn in a cone ahead of the fist, a white vapour collar at the peak, a pressure ball
PF.pfx_vacuum_cone = function (sh, inst, C, P, K) {
  var k = punchT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, i;
  var grow = k.hit ? 1 : ei(k.drive), a = k.hit ? 1 - k.after : 0.35 + 0.65 * k.drive, push = k.hit ? eo(k.after) : 0;
  var nr = Math.round(5 * dens(P));
  for (i = 0; i < nr; i++) {
    var u = (i + 1) / nr, x = L * u * (0.3 + 0.7 * grow) + L * 0.6 * push;
    sh.ring([x, 0, 0], [1, 0, 0], r * (0.6 + u * 2.6) * (0.5 + grow), i % 2 ? WHITE : K.h, a * (1 - u * 0.5), {ink: 0.4});
  }
  sh.tube([r * 0.3, 0, 0], [L * (0.4 + 0.6 * grow) + L * 0.6 * push, 0, 0], r * 0.9, r * 2.6 * grow, K.m, a * 0.28, {core: false, ink: 0});
  if (k.near > 0) sh.ring([r * 0.4, 0, 0], [1, 0, 0], r * (1.8 + 2 * (1 - k.near)), WHITE, k.near, {ink: 1});   // vapour collar
  if (k.hit && k.after < 0.5) sh.sph([L * 0.35 * (1 + push), 0, 0], r * (1.2 + 3 * push), WHITE, (1 - k.after * 2) * 0.55, {core: false, ink: 0});
  sh.sph([0, 0, 0], r * 0.8, K.h, a, {st: 1 + Math.min(2, C.sp * 0.2), d: [1, 0, 0]});
};
// 4 Blazing fist: flame tongues licking off the fist and trailing its path, embers, a fire bloom on contact
PF.pfx_flame_fist = function (sh, inst, C, P, K) {
  var k = punchT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, n = Math.round(10 * dens(P)), i, rnd, fl = 1 - (k.hit ? k.after : 0);
  sh.sph([0, 0, 0], r * (0.95 + 0.15 * Math.sin(C.t * 1.7)), K.m, 0.95 * fl, {ink: 0.8});
  sh.sph([r * 0.2, 0, 0], r * 0.75, K.h, fl);
  for (i = 0; i < n; i++) {
    rnd = R(inst, 5, i * 31 + (C.t >> 1)); var b = back(C, 1 + Math.floor(rnd() * 5)), az = rnd() * TAU, o = r * (0.4 + rnd());
    var base = add(b, [0, Math.cos(az) * o, Math.sin(az) * o], 1), tip = add(base, [-r * (0.6 + rnd() * 1.2), r * (0.6 + rnd() * 1.5), (rnd() - 0.5) * r * 1.2], 1);
    sh.tube(base, tip, r * (0.25 + rnd() * 0.2), 0, rnd() < 0.4 ? K.h : K.m, fl * (0.6 + rnd() * 0.4), {ink: 0.5});
  }
  for (i = 0; i < 6; i++) { rnd = R(inst, 6, i); var age = (C.t + i * 3) % 12;
    sh.sph(add(back(C, 2), [-age * 0.8 * C.ps, age * (0.7 + rnd()) * C.ps, (rnd() - 0.5) * age * C.ps], 1), r * 0.18, K.h, (1 - age / 12) * fl, {core: false, ink: 0}); }
  if (k.hit && k.after < 0.8) {
    var e = eo(k.after * 1.5), a = 1 - k.after / 0.8;
    sh.sph([L * 0.3 * e, 0, 0], r * (1 + 1.6 * e), K.m, a * 0.8, {ink: 0.8});
    sh.sph([L * 0.3 * e, 0, 0], r * (0.7 + 1 * e), K.h, a);
    for (i = 0; i < n; i++) { rnd = R(inst, 7, i); var d = cone(rnd() * 55, rnd() * TAU);
      sh.tube(scl(d, r + L * 0.2 * e), scl(d, r + L * (0.35 + 0.4 * rnd()) * e), r * 0.5, 0, i % 2 ? K.h : K.m, a, {ink: 0.5}); }
    sh.ring([L * 0.2 * e, 0, 0], [1, 0, 0], r * (2 + 4 * e), K.h, a * 0.8, {ink: 0.4});
  }
};
// 5 Thunder knuckle: arcs crackling round the forearm path, sparks, a forked bolt jumping forward on contact
PF.pfx_thunder_fist = function (sh, inst, C, P, K) {
  var k = punchT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, i, fl = k.hit ? 1 - k.after : 0.6 + 0.4 * k.drive;
  sh.sph([0, 0, 0], r * 0.95, K.h, fl, {ink: 0.7});
  var na = Math.round(3 * dens(P)) + 1;
  for (i = 0; i < na; i++) {   // re-rolled every 2 ticks: crackling
    var rnd = R(inst, 8, i * 97 + (C.t >> 1)), b = back(C, 2 + Math.floor(rnd() * 4)), az = rnd() * TAU;
    sh.bolt(add(b, [0, Math.cos(az) * r, Math.sin(az) * r], 1), [r * 0.5 * Math.cos(az + 2), Math.cos(az + 1) * r * 0.8, Math.sin(az + 1) * r * 0.8], 4, r * 1.2, r * 0.12, i % 2 ? K.h : K.d, fl, rnd, {core: false, ink: 0.4});
  }
  for (i = 0; i < 5; i++) { rnd = R(inst, 9, i + C.t * 7); var d = cone(40 + rnd() * 120, rnd() * TAU);
    sh.tube(scl(d, r), scl(d, r * (1.8 + rnd() * 1.6)), r * 0.09, 0, WHITE, fl * rnd(), {core: false, ink: 0}); }
  if (k.hit && k.after < 0.7) {
    var a = 1 - k.after / 0.7, rn = R(inst, 10, C.t >> 1);
    var tip = [L * (0.7 + 0.3 * eo(k.after * 3)), 0, 0];
    sh.bolt([r * 0.6, 0, 0], tip, 7, r * 2.2, r * 0.22, K.h, a, rn, {ink: 0.6});
    for (i = 0; i < 3; i++) { var mid = [tip[0] * (0.4 + i * 0.2), 0, 0], br = add(mid, cone(35 + rn() * 30, rn() * TAU), L * 0.35);
      sh.bolt(mid, br, 4, r, r * 0.1, K.d, a * 0.9, rn, {core: false, ink: 0.4}); }
    sh.sph(tip, r * (1.4 + rn()), WHITE, a, {ink: 0.5});
    if (k.after < 0.2) sh.sph([r, 0, 0], r * 2.6, K.h, 1 - k.after * 5, {core: false, ink: 0});
  }
};
// 6 Frost jab: ice crystals forming along the path, cold mist, a frozen ring on contact that shatters into shards
PF.pfx_frost_fist = function (sh, inst, C, P, K) {
  var k = punchT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, n = Math.round(8 * dens(P)), i, rnd, fl = k.hit ? 1 - k.after : 1;
  sh.sph([0, 0, 0], r, K.h, fl, {ink: 0.8});
  for (i = 0; i < n; i++) {
    rnd = R(inst, 11, i); var b = back(C, 1 + (i % 5)), az = rnd() * TAU, o = r * (0.5 + rnd() * 0.8);
    sh.chunk("shard", add(b, [0, Math.cos(az) * o, Math.sin(az) * o], 1), r * (0.3 + rnd() * 0.35) * (0.5 + 0.5 * k.drive), [az, rnd() * 3, 0], i % 3 ? K.m : K.h, fl * 0.9, {ink: 0.6});
    if (i < 4) sh.sph(add(b, [0, o * 0.5, 0], 1), r * (0.5 + rnd() * 0.5), mix(K.h, WHITE, 0.5), fl * 0.25, {core: false, ink: 0});
  }
  if (k.hit) {
    var e = eo(k.after * 2), a = 1 - k.after;
    if (k.after < 0.3) sh.ring([r * 0.8, 0, 0], [1, 0, 0], r * (1.6 + e * 2), K.h, a, {ink: 1});
    for (i = 0; i < n + 4; i++) { rnd = R(inst, 12, i); var d = cone(10 + rnd() * 70, rnd() * TAU), age = Math.max(0, C.t - k.T);
      sh.chunk("shard", thrown([r, 0, 0], d, (2.2 + rnd() * 2.5) * C.ps, age, 0.25 * C.ps, C.gy), r * (0.3 + rnd() * 0.4), [age * 0.4 + i, age * 0.3, 0], i % 2 ? K.m : WHITE, a, {ink: 0.6}); }
    sh.sph([L * 0.2 * e, 0, 0], r * (1 + 3 * e), mix(K.h, WHITE, 0.5), a * 0.35, {core: false, ink: 0});
  }
};
// 7 Void knuckle: a dark core with a violet rim swallowing rings, an inverted (dark) shock on contact
PF.pfx_void_fist = function (sh, inst, C, P, K) {
  var k = punchT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, i, fl = k.hit ? 1 - k.after : 0.5 + 0.5 * k.drive;
  sh.sph([0, 0, 0], r * 1.25, K.m, fl * 0.8, {core: false, ink: 1});
  sh.sph([0, 0, 0], r * 0.95, K.d, fl, {core: false, ink: 0});
  for (i = 0; i < 3; i++) { var u = ((C.t * 0.18 + i / 3) % 1);   // rings pulled INTO the fist
    sh.ring([0, 0, 0], [Math.cos(i * 2.1), Math.sin(i * 2.1), 0.4], r * (3.2 - 2.4 * u), K.h, fl * u, {core: false, ink: 0.5}); }
  for (i = 0; i < 5; i++) { var rnd = R(inst, 13, i), b = back(C, 1 + i), az = rnd() * TAU;
    sh.tube(b, add(b, [r * 0.5, Math.cos(az) * r, Math.sin(az) * r], 1), r * 0.35, 0, K.d, fl * (1 - i / 6), {core: false, ink: 0.6}); }
  if (k.hit && k.after < 0.85) {
    var e = eo(k.after * 1.4), a = 1 - k.after / 0.85;
    sh.ring([L * 0.25 * e, 0, 0], [1, 0, 0], r * (1.5 + 5 * e), K.d, a, {core: false, ink: 1.2});
    sh.ring([L * 0.2 * e, 0, 0], [1, 0, 0], r * (1.2 + 4 * e), K.h, a, {ink: 0.5});
    sh.sph([L * 0.2, 0, 0], r * 2 * (1 - k.after), K.d, a, {core: false, ink: 1});
    for (i = 0; i < 8; i++) { var rr = R(inst, 14, i), d = cone(rr() * 60, rr() * TAU);
      sh.tube(scl(d, r * 2 + L * 0.6 * e), scl(d, r * 2 + L * 0.6 * e + r * 2.5), r * 0.25, 0, i % 2 ? K.h : K.d, a, {core: false, ink: 0.4}); }
  }
};
// 8 Cyclone hook: air strokes winding round the path, leaf chips caught in the wind, a corkscrew vortex driven forward
PF.pfx_cyclone_hook = function (sh, inst, C, P, K) {
  var k = punchT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, i, j, fl = k.hit ? 1 - k.after : 0.4 + 0.6 * k.drive;
  var ns = Math.round(3 * dens(P)) + 1;
  for (j = 0; j < ns; j++) {   // spiral strokes round the last 6 ticks of path
    var prev = null;
    for (i = 0; i <= 10; i++) { var u = i / 10, b = back(C, Math.round((1 - u) * 6)), an = j / ns * TAU + u * 4 + C.t * 0.7, rad = r * (0.8 + 1.4 * u);
      var q = add(b, [0, Math.cos(an) * rad, Math.sin(an) * rad], 1); if (prev) sh.tube(prev, q, r * 0.05, r * 0.16 * u, j ? K.h : WHITE, fl * u, {core: false, ink: 0}); prev = q; }
  }
  for (i = 0; i < 6; i++) { var rnd = R(inst, 15, i), an2 = rnd() * TAU + C.t * 0.5, rd = r * (1.5 + rnd() * 1.5);
    sh.chunk("shard", add(back(C, i % 4), [0, Math.cos(an2) * rd, Math.sin(an2) * rd], 1), r * 0.25, [C.t * 0.5, i, 0], K.m, fl, {ink: 0.5}); }
  if (k.hit && k.after < 0.8) {
    var a = 1 - k.after / 0.8, e = eo(k.after * 1.6);
    for (j = 0; j < 2; j++) { var pv = null;
      for (i = 0; i <= 16; i++) { var w = i / 16, x = L * w * (0.4 + 0.8 * e), ang = j * Math.PI + w * 9 - C.t * 0.9, rr2 = r * (0.5 + 2.2 * w) * (0.6 + e * 0.6);
        var p2 = [x, Math.cos(ang) * rr2, Math.sin(ang) * rr2]; if (pv) sh.tube(pv, p2, r * 0.2 * (1 - w * 0.6), r * 0.2 * (1 - w * 0.6), j ? K.m : K.h, a * (1 - w * 0.5), {ink: 0.4}); pv = p2; } }
    sh.ring([L * 0.8 * (0.4 + 0.8 * e), 0, 0], [1, 0, 0], r * 3 * (0.6 + e * 0.6), WHITE, a * 0.7, {ink: 0.3});
  }
};
// 9 Rocket jab: a jet flame blasting out behind the fist (opposite the drive) with shock diamonds, smoke puffs, a burst at contact
PF.pfx_rocket_jab = function (sh, inst, C, P, K) {
  var k = punchT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, i, rnd, thr = k.hit ? 1 - k.after : ei(k.drive) * 0.7 + 0.3;
  var jl = L * (0.45 + 0.5 * thr) * (0.9 + 0.1 * Math.sin(C.t * 2.3));
  sh.tube([-r * 0.6, 0, 0], [-r * 0.6 - jl, 0, 0], r * 1.1, 0, K.m, thr, {ink: 0.6});
  sh.tube([-r * 0.6, 0, 0], [-r * 0.6 - jl * 0.7, 0, 0], r * 0.6, 0, K.h, thr);
  for (i = 1; i <= 3; i++) sh.sph([-r * 0.6 - jl * i / 4.2, 0, 0], r * 0.45 * (1 - i * 0.15), WHITE, thr * 0.9, {st: 1.6, d: [1, 0, 0], ink: 0});   // shock diamonds
  for (i = 0; i < Math.round(6 * dens(P)); i++) { rnd = R(inst, 16, i); var age = (C.t + i * 2) % 14, b = back(C, Math.min(age, 8));
    sh.sph(add(b, [-r - age * 0.6 * C.ps, (rnd() - 0.3) * age * 0.6 * C.ps, (rnd() - 0.5) * age * 0.6 * C.ps], 1), r * (0.4 + age * 0.08), EL.smoke[1], (1 - age / 14) * 0.6, {core: false, ink: 0.4}); }
  sh.sph([0, 0, 0], r, K.h, 1, {st: 1 + Math.min(2, C.sp * 0.2), d: [1, 0, 0], ink: 0.8});
  if (k.hit && k.after < 0.6) {
    var e = eo(k.after * 2), a = 1 - k.after / 0.6;
    sh.sph([r + L * 0.2 * e, 0, 0], r * (1 + 1.6 * e), K.m, a, {ink: 0.8});
    sh.ring([r + L * 0.2 * e, 0, 0], [1, 0, 0], r * (1.6 + 3.5 * e), WHITE, a, {ink: 0.5});
  }
};
// 10 Phantom rush: a flurry of phantom fists stabbing out round the aim at uneven beats, each with a mini flash
PF.pfx_phantom_rush = function (sh, inst, C, P, K) {
  var r = +P.radius * C.ps, L = +P.length * C.ps, n = Math.round(9 * dens(P)), span = activeTicks(P), i;
  for (i = 0; i < n; i++) {
    var rnd = R(inst, 17, i), t0 = Math.floor(rnd() * Math.max(1, span - 4)), u = (C.t - t0) / 4;
    if (u < 0 || u > 1.6) continue;
    var out = u < 1 ? eo(u) : 1, a = u < 1 ? 1 : 1 - (u - 1) / 0.6, o = [0, (rnd() - 0.5) * L * 0.5, (rnd() - 0.5) * L * 0.5];
    var tip = add(o, [L * (0.35 + 0.45 * rnd()) * out, 0, 0], 1), base = add(o, [-r * 2, 0, 0], 1);
    sh.tube(base, tip, r * 0.2, r * 0.8, K.m, a * 0.55, {core: false, ink: 0});
    sh.sph(tip, r * 0.85, i % 2 ? K.h : K.m, a, {st: 1.8 - out * 0.6, d: [1, 0, 0], ink: 0.6});
    if (u >= 0.9 && u < 1.3) { sh.sph(add(tip, [r, 0, 0], 1), r * 1.6, WHITE, 1 - (u - 0.9) / 0.4, {ink: 0});
      sh.ring(add(tip, [r, 0, 0], 1), [1, 0, 0], r * (1 + (u - 0.9) * 5), K.h, 1 - (u - 0.9) / 0.4, {ink: 0.3}); }
  }
  sh.sph([0, 0, 0], r, WHITE, 0.9, {ink: 0.8});
};

// ================================================================ impact FX
// pop = 0..1 over swing_ticks (the burst), then life = 0..1 over hold_ticks, age past the active time keeps debris falling
function impactT(P, t) { var T = swing(P), H = hold(P); return {pop: eo((t + 1) / T), life: cl((t - T) / H), all: cl(t / (T + H)), age: t, T: T}; }
var IF = {};
// shared: the white flash + impact frame star (camera-facing sphere sharp for a few ticks)
function flash(sh, k, r, K, n) { if (k.age < (n || 4)) { var a = 1 - k.age / (n || 4); sh.sph([0, 0, 0], r * (0.45 + 0.35 * k.pop), WHITE, a, {ink: 0}); sh.sph([0, 0, 0], r * (0.65 + 0.55 * k.pop), K.h, a * 0.5, {core: false, ink: 0}); } }
function dust(sh, inst, C, k, r, n, col, tag) {
  for (var i = 0; i < n; i++) { var rnd = R(inst, tag || 40, i), az = rnd() * TAU, sp = (0.7 + rnd()) * C.ps, age = k.age;
    var p = [Math.cos(az) * (r * 0.6 + sp * age), C.gy + r * 0.15 + age * 0.12 * C.ps * rnd(), Math.sin(az) * (r * 0.6 + sp * age)];
    sh.sph(p, r * (0.12 + rnd() * 0.1) * (1 + age * 0.05), col, (1 - k.all) * 0.6, {core: false, ink: 0.4}); }
}
function rocks(sh, inst, C, k, r, n, col, cone0, spd, tag) {
  for (var i = 0; i < n; i++) { var rnd = R(inst, tag || 41, i), d = cone(rnd() * (cone0 || 80), rnd() * TAU), up = [d[0] * 0.5, Math.abs(d[1]) + 0.4, d[2]];
    var p = thrown([0, C.gy + 1, 0], up, (spd || 2) * (0.5 + rnd()) * C.ps, k.age, 0.22 * C.ps, C.gy);
    sh.chunk(rnd() < 0.5 ? "shard" : "cube", p, r * (0.1 + rnd() * 0.12), [k.age * 0.3 + i, k.age * 0.2, i], col, Math.min(1, 2.2 - k.all * 2), {ink: 0.7}); }
}
// 1 Shockwave crater: flash, doubled ground ring, crater rim shards thrown up, dust ring, cracks running out
IF.ifx_shock_crater = function (sh, inst, C, P, K) {
  var k = impactT(P, C.t), r = +P.radius * C.ps, i, g = C.gy + 0.6, a = 1 - k.all;
  flash(sh, k, r, K);
  sh.ring([0, g, 0], [0, 1, 0], r * (0.5 + 2.4 * eo(k.all * 1.5)), WHITE, a, {ink: 0.6});
  sh.ring([0, g, 0], [0, 1, 0], r * (0.3 + 1.6 * eo(k.all * 1.2)), K.m, a, {ink: 0.6});
  sh.ring([0, 0, 0], [1, 0, 0], r * (0.6 + 1.4 * k.pop), K.h, Math.max(0, 1 - k.age / 8), {ink: 0.4});
  for (i = 0; i < 10; i++) { var rnd = R(inst, 18, i), az = i / 10 * TAU + rnd() * 0.4, ln = r * (0.8 + rnd() * 0.9) * eo(k.all * 3);   // cracks
    var A = [Math.cos(az) * r * 0.35, g, Math.sin(az) * r * 0.35], B = [Math.cos(az + (rnd() - 0.5) * 0.4) * (r * 0.35 + ln), g, Math.sin(az + (rnd() - 0.5) * 0.4) * (r * 0.35 + ln)];
    sh.tube(A, B, r * 0.05, 0, EL.rock[2], Math.min(1, a * 1.6), {core: false, ink: 0}); }
  rocks(sh, inst, C, k, r, Math.round(12 * dens(P)), EL.rock[0], 70, 2.4);
  dust(sh, inst, C, k, r, Math.round(10 * dens(P)), EL.rock[1]);
};
// 2 Spark star: a spiky anime star, sparks sprayed in a cone along the blow and falling, an X glint
IF.ifx_spark_star = function (sh, inst, C, P, K) {
  var k = impactT(P, C.t), r = +P.radius * C.ps, i, rnd, a0 = Math.max(0, 1 - k.age / (k.T + 6));
  flash(sh, k, r, K, 5);
  for (i = 0; i < 10; i++) { rnd = R(inst, 19, i); var d = cone(rnd() * 180, rnd() * TAU), ln = r * (0.9 + rnd() * 1.2) * k.pop;
    sh.tube(scl(d, r * 0.15), scl(d, r * 0.15 + ln), r * 0.16, 0, i % 3 ? K.h : WHITE, a0, {ink: 0.5}); }
  var x = r * 1.6 * k.pop, ga = Math.max(0, 1 - k.age / 9);
  sh.tube([0, -x, -x], [0, x, x], r * 0.08, r * 0.08, WHITE, ga, {core: false, ink: 0}); sh.tube([0, -x, x], [0, x, -x], r * 0.08, r * 0.08, WHITE, ga, {core: false, ink: 0});
  for (i = 0; i < Math.round(22 * dens(P)); i++) { rnd = R(inst, 20, i); var dd = cone(rnd() * 50, rnd() * TAU), sp = (2.5 + rnd() * 3.5) * C.ps, age = k.age;
    var p0 = thrown([0, 0, 0], dd, sp, age, 0.2 * C.ps, C.gy), p1 = thrown([0, 0, 0], dd, sp, Math.max(0, age - 1.4), 0.2 * C.ps, C.gy);
    sh.tube(p1, p0, r * 0.05, r * 0.03, rnd() < 0.5 ? WHITE : K.h, Math.max(0, 1 - age / (14 + rnd() * 10)), {core: false, ink: 0}); }
  sh.ring([r * 0.3, 0, 0], [1, 0, 0], r * (0.5 + 2 * eo(k.all * 2)), K.m, 1 - k.all, {ink: 0.5});
};
// 3 Distortion ripple: see-through air shells expanding one after another, thin rings across the blow, lines rushing in
IF.ifx_ripple_dome = function (sh, inst, C, P, K) {
  var k = impactT(P, C.t), r = +P.radius * C.ps, i;
  flash(sh, k, r * 0.7, K, 3);
  for (i = 0; i < 4; i++) { var t = (C.t - i * 3) / (k.T + hold(P) * 0.7); if (t < 0 || t > 1) continue; var e = eo(t);
    sh.sph([r * 0.3 * e, 0, 0], r * (0.3 + 1.4 * e), i % 2 ? K.h : K.m, (1 - t) * 0.16, {core: false, ink: 0, st: 1.25, d: [1, 0, 0]});
    sh.ring([r * 0.3 * e, 0, 0], [1, 0, 0], r * (0.3 + 1.4 * e), WHITE, (1 - t) * 0.9, {ink: 0.3}); }
  var tin = cl(C.t / 6);   // speed lines rushing IN first, then gone
  if (tin < 1) for (i = 0; i < 14; i++) { var rnd = R(inst, 21, i), d = cone(60 + rnd() * 110, rnd() * TAU), far = r * (3 - 2.4 * eo(tin));
    sh.tube(scl(d, far + r * 1.2), scl(d, far), r * 0.05, r * 0.12, WHITE, 1 - tin, {core: false, ink: 0}); }
};
// 4 Pierce-through blast: the shock bursts OUT the back of the target: an energy cone, a ring across, debris flung on
IF.ifx_pierce_through = function (sh, inst, C, P, K) {
  var k = impactT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, i, rnd, a = 1 - k.all, e = eo(k.all * 1.6);
  flash(sh, k, r * 0.8, K);
  sh.tube([r * 0.2, 0, 0], [r * 0.2 + L * (0.5 + e), 0, 0], r * 0.5, r * (1.6 + 1.6 * e), K.m, a * 0.55, {ink: 0.6});
  sh.tube([r * 0.2, 0, 0], [r * 0.2 + L * (0.4 + 0.8 * e), 0, 0], r * 0.3, r * (0.8 + 0.8 * e), K.h, a, {core: true, ink: 0});
  for (i = 0; i < 3; i++) sh.ring([r * 0.5 + L * (0.2 + i * 0.3) * (0.4 + e), 0, 0], [1, 0, 0], r * (0.8 + i * 0.7) * (0.6 + e), i ? K.h : WHITE, a, {ink: 0.5});
  for (i = 0; i < 12; i++) { rnd = R(inst, 22, i); var d = cone(rnd() * 25, rnd() * TAU), ln = L * (0.6 + rnd() * 0.8) * e;
    sh.tube(scl(d, r + ln * 0.5), scl(d, r + ln), r * 0.06, 0, WHITE, a, {core: false, ink: 0}); }
  for (i = 0; i < Math.round(10 * dens(P)); i++) { rnd = R(inst, 23, i); var dd = cone(rnd() * 35, rnd() * TAU);
    sh.chunk("shard", thrown([r * 0.5, 0, 0], dd, (3 + rnd() * 3) * C.ps, k.age, 0.2 * C.ps, C.gy), r * (0.1 + rnd() * 0.1), [k.age * 0.4, i, 0], i % 2 ? K.h : K.m, Math.min(1, 2 - k.all * 2), {ink: 0.6}); }
};
// 5 Inferno burst: a banded fireball, flame tongues bursting out, embers rising, smoke, a scorch disc on the floor
IF.ifx_inferno_burst = function (sh, inst, C, P, K) {
  var k = impactT(P, C.t), r = +P.radius * C.ps, i, rnd, a = 1 - k.all, e = eo(k.all * 2.2);
  flash(sh, k, r, K, 3);
  sh.sph([0, r * 0.3 * e, 0], r * (0.4 + 0.6 * e) * (1 - k.life * 0.3), K.m, a * 0.95, {ink: 0.9});
  sh.sph([0, r * 0.3 * e, 0], r * (0.25 + 0.45 * e) * (1 - k.life * 0.5), K.h, a);
  for (i = 0; i < Math.round(12 * dens(P)); i++) { rnd = R(inst, 24, i * 7 + (C.t >> 1)); var az = rnd() * TAU, el = rnd() * 70 - 10, d = [Math.cos(el * D) * Math.cos(az), Math.sin(el * D), Math.cos(el * D) * Math.sin(az)];
    sh.tube(scl(d, r * 0.6 * e), add(scl(d, r * (1.2 + rnd() * 1.1) * e), [0, r * 0.5 * k.life, 0], 1), r * 0.4 * (1 - k.life * 0.5), 0, i % 2 ? K.h : K.m, a, {ink: 0.5}); }
  for (i = 0; i < 10; i++) { rnd = R(inst, 25, i); var age = k.age, d2 = [(rnd() - 0.5) * 1.2, 1, (rnd() - 0.5) * 1.2];
    sh.sph([d2[0] * age * 0.7 * C.ps, r * 0.5 + age * (0.6 + rnd() * 0.6) * C.ps, d2[2] * age * 0.7 * C.ps], r * 0.06, K.h, Math.max(0, 1 - age / 30), {core: false, ink: 0}); }
  for (i = 0; i < 6; i++) { rnd = R(inst, 26, i); var sa = cl((C.t - 4) / (hold(P) + 6)); if (sa <= 0) break;
    sh.sph([(rnd() - 0.5) * r, r * (0.8 + sa * 2.2 + rnd()), (rnd() - 0.5) * r], r * (0.4 + sa * 0.8), EL.smoke[i % 2], (1 - sa) * 0.75, {core: false, ink: 0.5}); }
  sh.ring([0, C.gy + 0.5, 0], [0, 1, 0], r * (0.4 + 1.3 * e), EL.fire[2], a, {core: false, ink: 0.5});
  sh.ring([0, C.gy + 0.5, 0], [0, 1, 0], r * (0.3 + 1.0 * e), K.m, a * 0.8, {ink: 0.3});
};
// 6 Thunderclap: a bolt from the sky onto the target, branches out along the blow, crackles over the floor, a flash
IF.ifx_thunderclap = function (sh, inst, C, P, K) {
  var k = impactT(P, C.t), r = +P.radius * C.ps, i, rn = R(inst, 27, C.t >> 1), a = Math.max(0, 1 - k.age / (k.T + hold(P) * 0.8));
  flash(sh, k, r * 1.1, K, 4);
  if (k.age < hold(P) * 0.5 && (k.age < 4 || (k.age & 3) !== 3)) {   // the sky bolt flickers
    sh.bolt([(rn() - 0.5) * r, r * 9, (rn() - 0.5) * r], [0, 0, 0], 9, r * 1.4, r * 0.18, K.h, a, rn, {ink: 0.7});
    sh.bolt([(rn() - 0.5) * r * 2, r * 7, (rn() - 0.5) * r * 2], [0, r * 0.5, 0], 6, r, r * 0.08, K.d, a * 0.8, rn, {core: false, ink: 0.4});
  }
  for (i = 0; i < Math.round(5 * dens(P)); i++) { var d = cone(20 + rn() * 70, rn() * TAU);
    sh.bolt([0, 0, 0], scl(d, r * (1.4 + rn() * 1.4)), 4, r * 0.7, r * 0.1, i % 2 ? K.h : K.d, a, rn, {core: false, ink: 0.4}); }
  for (i = 0; i < 6; i++) { var az = rn() * TAU, ln = r * (1 + rn() * 1.5);
    sh.bolt([0, C.gy + 0.6, 0], [Math.cos(az) * ln, C.gy + 0.6, Math.sin(az) * ln], 4, r * 0.4, r * 0.06, K.h, a * 0.9, rn, {core: false, ink: 0}); }
  sh.ring([0, C.gy + 0.6, 0], [0, 1, 0], r * (0.5 + 2 * eo(k.all * 2)), K.h, 1 - k.all, {ink: 0.4});
  sh.sph([0, 0, 0], r * 0.7 * (1 - k.all), WHITE, a, {ink: 0.4});
};
// 7 Glacial shatter: ice spikes erupting round the target in a cone, a frost ring on the floor, shards flying and falling
IF.ifx_glacial_shatter = function (sh, inst, C, P, K) {
  var k = impactT(P, C.t), r = +P.radius * C.ps, i, rnd, a = 1 - k.all, grow = eo((C.t + 1) / (k.T + 2)), brk = k.life > 0.55;
  flash(sh, k, r * 0.8, K, 3);
  if (!brk) for (i = 0; i < Math.round(9 * dens(P)); i++) { rnd = R(inst, 28, i); var d = cone(rnd() * 70, rnd() * TAU), up = [d[0], Math.abs(d[1]) * 0.6 + 0.3, d[2]];
    sh.tube(scl(up, r * 0.2), scl(up, r * (0.9 + rnd() * 1.1) * grow), r * (0.22 + rnd() * 0.12), 0, i % 3 ? K.m : K.h, 1, {ink: 0.9}); }
  if (brk) { var age = C.t - (k.T + hold(P) * 0.55);
    for (i = 0; i < Math.round(16 * dens(P)); i++) { rnd = R(inst, 29, i); var dd = cone(rnd() * 120, rnd() * TAU);
      sh.chunk("shard", thrown(scl(dd, r * 0.6), dd, (1.5 + rnd() * 2.5) * C.ps, age, 0.25 * C.ps, C.gy), r * (0.12 + rnd() * 0.14), [age * 0.4 + i, age * 0.3, i], i % 2 ? K.m : WHITE, Math.min(1, 2.4 - k.all * 2.4), {ink: 0.7}); } }
  sh.ring([0, C.gy + 0.6, 0], [0, 1, 0], r * (0.4 + 1.6 * eo(k.all * 1.5)), K.h, a, {ink: 0.6});
  sh.sph([0, C.gy + r * 0.2, 0], r * (0.8 + 1.5 * k.all), mix(K.h, WHITE, 0.5), a * 0.3, {core: false, ink: 0});
};
// 8 Void implosion: a dark sphere sucking rings in, a beat of stillness, then it bursts out in violet shards and a dark ring
IF.ifx_void_implosion = function (sh, inst, C, P, K) {
  var r = +P.radius * C.ps, H = activeTicks(P), cut = Math.round(H * 0.45), t = C.t, i, rnd;
  if (t < cut) {
    var u = t / cut;
    sh.sph([0, 0, 0], r * (0.3 + 0.6 * u), K.d, 1, {core: false, ink: 1.2});
    sh.sph([0, 0, 0], r * (0.36 + 0.66 * u), K.m, 0.45, {core: false, ink: 0});
    for (i = 0; i < 4; i++) { var w = ((t * 0.12 + i / 4) % 1); sh.ring([0, 0, 0], [Math.cos(i * 1.4), Math.sin(i * 1.4), 0.5], r * (2.6 - 2.2 * w), K.h, w, {core: false, ink: 0.5}); }
    for (i = 0; i < 10; i++) { rnd = R(inst, 30, i); var d = cone(rnd() * 180, rnd() * TAU), w2 = ((t * 0.09 + rnd()) % 1), far = r * (3 - 2.6 * w2);
      sh.tube(scl(d, far), scl(d, far - r * 0.6), r * 0.04, r * 0.1, K.h, w2, {core: false, ink: 0}); }
  } else {
    var b = (t - cut) / Math.max(1, H + AFTER - cut), e = eo(b * 1.8), a = 1 - b;
    if (t - cut < 3) sh.sph([0, 0, 0], r * 1.4, WHITE, 1 - (t - cut) / 3, {ink: 0});
    sh.ring([0, 0, 0], [1, 0, 0], r * (0.5 + 3 * e), K.d, a, {core: false, ink: 1.2});
    sh.ring([0, 0, 0], [0, 1, 0], r * (0.4 + 2.6 * e), K.h, a, {ink: 0.5});
    sh.sph([0, 0, 0], r * (0.9 - 0.9 * b), K.d, a, {core: false, ink: 1});
    for (i = 0; i < Math.round(14 * dens(P)); i++) { rnd = R(inst, 31, i); var dd = cone(rnd() * 180, rnd() * TAU);
      sh.chunk("shard", add(scl(dd, r * 0.4 + r * 3.2 * e), [0, 0, 0], 1), r * (0.12 + rnd() * 0.12) * (1 - b * 0.5), [t * 0.3, i, 0], i % 2 ? K.h : K.m, a, {ink: 0.7}); }
  }
};
// 9 Earthsplitter: cracks racing out along the blow, rock spires bursting up in a line, dust rolling off them
IF.ifx_earthsplitter = function (sh, inst, C, P, K) {
  var k = impactT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, i, rnd, g = C.gy, n = Math.round(7 * dens(P));
  flash(sh, k, r * 0.7, K, 3);
  var run = eo((C.t + 1) / (k.T + 6));
  sh.tube([0, g + 0.4, 0], [L * run, g + 0.4, 0], r * 0.12, r * 0.04, EL.rock[2], 1 - k.all * 0.6, {core: false, ink: 0});
  for (i = 0; i < 6; i++) { rnd = R(inst, 32, i); var x0 = L * run * rnd(), sd = (rnd() - 0.5) * r * 1.5;
    sh.tube([x0, g + 0.4, 0], [x0 + r * 0.6 * rnd(), g + 0.4, sd], r * 0.06, 0, EL.rock[2], 1 - k.all * 0.6, {core: false, ink: 0}); }
  for (i = 0; i < n; i++) { rnd = R(inst, 33, i); var x = L * (i + 0.5) / n, born = (i + 0.5) / n * (k.T + 6), age = C.t - born; if (age < 0) continue;
    var h = r * (0.5 + rnd() * 0.9) * eo(age / 3) * (1 - cl((C.t - (k.T + hold(P) * 0.7)) / 8)), sd2 = (rnd() - 0.5) * r * 0.9;
    if (h > 0.2) { sh.tube([x, g, sd2], [x + (rnd() - 0.5) * r * 0.3, g + h, sd2 + (rnd() - 0.5) * r * 0.3], r * (0.28 + rnd() * 0.12), r * 0.04, EL.rock[0], 1, {ink: 1});
      sh.tube([x + r * 0.2, g, sd2 - r * 0.2], [x + r * 0.25, g + h * 0.6, sd2 - r * 0.15], r * 0.18, 0, EL.rock[1], 1, {ink: 0.8}); }
    if (age < 14) for (var j = 0; j < 2; j++) { var rr = R(inst, 34, i * 4 + j); sh.chunk("cube", thrown([x, g + 1, sd2], [(rr() - 0.5), 1, (rr() - 0.5)], (1.5 + rr() * 1.5) * C.ps, age, 0.25 * C.ps, g), r * 0.1, [age * 0.4, j, 0], EL.rock[0], 1, {ink: 0.7}); }
    if (age < 20) sh.sph([x, g + r * 0.2 + age * 0.15 * C.ps, sd2], r * (0.3 + age * 0.04), EL.rock[1], (1 - age / 20) * 0.6, {core: false, ink: 0.3}); }
  sh.ring([0, g + 0.5, 0], [0, 1, 0], r * (0.4 + 1.2 * eo(k.all * 2)), K.m, 1 - k.all, {ink: 0.4});
};
// 10 Sonic boom: a vapour cone flaring behind the target along the blow, a shock ring, speed lines, a dust ring kicked up
IF.ifx_sonic_boom = function (sh, inst, C, P, K) {
  var k = impactT(P, C.t), r = +P.radius * C.ps, L = +P.length * C.ps, i, rnd, a = 1 - k.all, e = eo(k.all * 1.8);
  flash(sh, k, r * 0.7, K, 3);
  for (i = 0; i < 6; i++) { var u = (i + 1) / 6, x = L * u * (0.3 + 0.9 * e);
    sh.ring([x, 0, 0], [1, 0, 0], r * (0.4 + 1.6 * u) * (0.6 + e * 0.6), i % 2 ? WHITE : mix(K.h, WHITE, 0.6), a * (1 - u * 0.4), {ink: 0.3}); }
  sh.tube([0, 0, 0], [L * (0.3 + 0.9 * e), 0, 0], r * 0.2, r * 2.2 * (0.6 + e * 0.6), mix(K.h, WHITE, 0.7), a * 0.25, {core: false, ink: 0});
  sh.ring([0, 0, 0], [1, 0, 0], r * (0.6 + 2.6 * e), K.m, a, {ink: 0.7});
  for (i = 0; i < 16; i++) { rnd = R(inst, 35, i); var d = cone(rnd() * 30, rnd() * TAU), s0 = L * (0.2 + 1.1 * e) * (0.6 + rnd() * 0.4);
    sh.tube(scl(d, s0), scl(d, s0 + L * 0.4 * (1 - k.all)), r * 0.06, 0, WHITE, a, {core: false, ink: 0}); }
  dust(sh, inst, C, k, r, Math.round(12 * dens(P)), EL.rock[1], 36);
};

// ================================================================ transformation FX
// Local frame round the body CENTRE (fx3d.js stands it on the fighter's live centre, up = world up, forward = toward the
// target). C.fy = the feet (v, px, below = negative), C.gy = the floor, C.vel = the body's move per tick [f, v, s] px:
// the flames stream behind it when it moves. Every flame / spark / bolt is re-rolled per cycle from the seed, so no two
// seconds of the aura look the same (Daniel's "chaotic control, like a flame").
// Stage = a preset look on top of the settings: size / shape multipliers, how fast and wild the flames are, lightning
var STAGE = {
  1: {size: 1.0, tight: 1.0, height: 1.0, flame: 1.0, speed: 1.0, chaos: 1.0, bolts: 0, cbolts: 1.2, rocks: 6, motes: 8, quake: false},
  2: {size: 1.05, tight: 0.85, height: 1.1, flame: 1.1, speed: 1.45, chaos: 1.25, bolts: 2.6, cbolts: 3, rocks: 9, motes: 12, quake: false},
  3: {size: 1.4, tight: 1.05, height: 1.35, flame: 1.35, speed: 1.6, chaos: 1.6, bolts: 4.5, cbolts: 5, rocks: 16, motes: 16, quake: true}};
function stageOf(P) { var s = Math.round(+pv(P, "stage") || 1); return STAGE[s < 1 ? 1 : s > 3 ? 3 : s]; }
function frac(x) { return x - Math.floor(x); }
// the aura's strength A (0..1) and size x s at tick t
function auraAmt(T, t, P) {
  var on = P.aura !== false;
  if (t < T.c) { var u = t / T.c; return {A: 0.15 + 0.65 * ei(u * 1.1), s: 0.6 + 0.35 * u}; }
  var tb = t - T.c;
  if (tb < T.b) { var b = tb / T.b; return on ? {A: 1, s: 1 + 0.35 * (1 - eo(b * 1.5))} : {A: T.c ? 0.8 * (1 - b) : 0, s: 1 + 0.4 * (1 - b)}; }
  if (!on) return {A: 0, s: 1};
  var ta = tb - T.b, k = !T.c && !T.b ? cl(t / 8) : 1;   // no charge, no burst: the aura flares up on its own
  if (ta < T.a) return {A: k, s: 0.8 + 0.2 * k};
  var o = cl((ta - T.a) / AURA_OUT); return {A: 1 - o, s: 1 - 0.3 * o};
}
// crackling arcs over the body: nb bolts (a fraction = sometimes one more), each re-rolled every 4 ticks with a flicker
function arcs(sh, inst, t, nb, rw, fy, H, z, A, salt, BC, bw) {
  if (!(nb > 0) || A <= 0.01) return;
  var FL = [1, 0.4, 0.9, 0.2], n = Math.ceil(nb);
  for (var j = 0; j < n; j++) {
    if (j >= Math.floor(nb) && R(inst, salt, j)() > nb - Math.floor(nb)) continue;
    var q = R(inst, salt + 1, j * 131 + Math.floor((t + j * 7) / 4)); if (q() > 0.78) continue;
    var a1 = q() * TAU, h1 = fy + H * (0.15 + 0.7 * q()), A1 = [Math.cos(a1) * rw * 0.9, h1, Math.sin(a1) * rw * 0.9];
    var a2 = a1 + (q() - 0.5) * 1.8, r2 = rw * (0.7 + q() * 0.7), B = [Math.cos(a2) * r2, h1 + (q() - 0.5) * H * 0.5, Math.sin(a2) * r2];
    var col = q() < 0.3 ? WHITE : BC, al = A * FL[(t + j * 7) & 3];
    sh.bolt(A1, B, 5, 2.6 * z, 0.6 * z * bw, col, al, q, {ink: 0});
    if (q() < 0.5) { var M = [(A1[0] + B[0]) / 2, (A1[1] + B[1]) / 2, (A1[2] + B[2]) / 2];
      sh.bolt(M, add(M, [(q() - 0.5) * 8 * z, (q() - 0.3) * 8 * z, (q() - 0.5) * 8 * z], 1), 3, 1.6 * z, 0.35 * z * bw, col, al * 0.8, q, {ink: 0}); }
  }
}
// pebbles lifting off the floor round the feet, turning, drifting up, falling apart
function pebbles(sh, inst, C, n, rw, z, A, salt) {
  for (var i = 0; i < n; i++) {
    var rnd = R(inst, salt, i), L = 50 + rnd() * 50, x = (C.t + rnd() * L) / L, ph = frac(x), q = R(inst, salt + 1, i * 37 + Math.floor(x));
    var an = q() * TAU, rd = rw * (1.2 + q() * 2.2), h = C.gy + 0.8 + ph * (14 + q() * 20) * z, wob = Math.sin(C.t * 0.2 + i) * 0.6 * z;
    var al = A * Math.min(1, (1 - ph) * 3) * Math.min(1, ph * 8);
    sh.chunk(q() < 0.5 ? "shard" : "cube", [Math.cos(an) * rd + wob, h, Math.sin(an) * rd], (0.5 + q() * 0.9) * z, [C.t * 0.05 + i, C.t * 0.03 + i * 2, i], EL.rock[q() < 0.5 ? 0 : 1], al, {ink: 0.7});
  }
}
// the aura round the body: ONE flame sheath (fx3d.js shader: a teardrop shell hugging the body, torn into rising flame
// tongues by moving noise, cel bands, a bright rim, see-through in the middle), + sparks, the ground swirl, arcs
function auraBody(sh, inst, C, P, K, Sg, z, A, fy, d, boltK, grounded) {
  var t = C.t, H = ((14 * Sg.height + 4) * z - fy) * pc(P, "aura_height_pct"), rw = 8.5 * z * Sg.tight * pc(P, "aura_width_pct");
  // off the ground: the bottom closes into a bowl (eased in with the height, so a hop and a landing don't pop), dropped
  // below the feet so the round bottom hangs under them; cb = the bowl's share of the sheath's height
  var close = pv(P, "air_close") !== false ? cl((fy - C.gy - 3 * C.ps) / (12 * C.ps)) : 0, rnd0 = pc(P, "air_round_pct");
  var drop = close * rw * 0.75 * rnd0, fy0 = fy;
  fy -= drop; H += drop;
  // Raise (Daniel 2026-11-28: "move the centre of it up a bit"): the trail's centre line moves up by aura_raise_pct x 8 px x
  // size, so the stretched flame is centred on the body; the sheath and its layers rise with it only off the ground
  // (eased in with the round bottom), so on the floor the aura still stands on the feet
  var lift = pc(P, "aura_raise_pct") * 8 * z * (+pv(P, "aura_raise_pct") < 0 ? -1 : 1);
  fy += lift * close;
  var cb = close > 0 ? Math.min(0.55, rw * (0.35 + 0.75 * rnd0) / Math.max(1, H)) : 0;
  var v = C.vel || [0, 0, 0], lk = 5 * pc(P, "lean_pct"), lean = [-v[0] * lk, 0, -v[2] * lk], lm = Math.hypot(lean[0], lean[2]), lmax = 22 * z;
  if (lm > lmax) lean = scl(lean, lmax / lm);
  var breathe = 1 + 0.06 * pc(P, "pulse_pct") * Math.sin(t * 0.21) + 0.03 * pc(P, "pulse_pct") * Math.sin(t * 0.67 + 1.3);
  var tr = auraTrail(C, P, rw * breathe, lift);
  sh.aura([0, fy - 1.5 * z, 0], rw * breathe, H * breathe, lean, K.m, A, {hot: K.h, edge: K.d, look: {close: close, bowl: cb, trail: tr,
    base: pc(P, "aura_base_pct"), top: pc(P, "aura_top_pct"), flames: Math.max(1, +pv(P, "flame_count") || 1),
    tongue: pc(P, "flame_height_pct") * Sg.flame, speed: pc(P, "flame_speed_pct") * Sg.speed, chaos: pc(P, "flame_chaos_pct") * Sg.chaos,
    gaps: pc(P, "flame_gaps_pct"), sharp: pc(P, "flame_sharp_pct"), opacity: pc(P, "aura_opacity_pct"), rim: pc(P, "rim_pct"),
    inner: pc(P, "inner_pct"), bands: Math.max(1, Math.round(+pv(P, "bands") || 1)), additive: pv(P, "additive") !== false,
    layer2: pv(P, "inner_layer") !== false, seed: ((inst.seed || 1) % 997) / 97}});
  if (pv(P, "layers") !== false) flameLayers(sh, inst, P, K, Sg, rw * breathe, H * breathe, fy, z, A, lean, close, cb, tr);
  if (pv(P, "outer_flames") === true) outerFlames(sh, inst, t, P, K, Sg, rw, H, fy, z, A, lean, close, cb);
  fy = fy0;
  var i, rnd, nm = Math.round(Sg.motes * d * pc(P, "sparks_pct"));
  for (i = 0; i < nm; i++) {   // sparks streaking up through it
    rnd = R(inst, 65, i); var x2 = t * (0.025 + rnd() * 0.03) + rnd(), p2 = frac(x2), q3 = R(inst, 66, i * 71 + Math.floor(x2));
    var az3 = q3() * TAU, rr3 = rw * (0.5 + q3() * 0.7);
    sh.sph([Math.cos(az3) * rr3 + lean[0] * p2, fy + p2 * H * 1.3, Math.sin(az3) * rr3 + lean[2] * p2], 0.4 * z, q3() < 0.5 ? WHITE : K.h, A * (1 - p2), {core: false, ink: 0, st: 2.4, d: [0, 1, 0]});
  }
  if (grounded && pv(P, "ground_fx") !== false) {   // the air swirling round the feet; stage 3 tears the ground up the whole time
    var g = C.gy + 0.3, du = pc(P, "dust_pct");
    sh.ring([0, g, 0], [0, 1, 0], rw * (1.25 + 0.12 * Math.sin(t * 0.37)), K.m, A * 0.45, {ink: 0.3});
    for (i = 0; i < Math.round(7 * du); i++) { rnd = R(inst, 67, i); var an = rnd() * TAU + t * (0.05 + rnd() * 0.04), rd = rw * (1.4 + rnd() * 0.6);
      sh.sph([Math.cos(an) * rd, g + (1 + rnd() * 1.5) * z, Math.sin(an) * rd], (1.2 + rnd()) * z, EL.rock[1], A * 0.28, {core: false, ink: 0.3}); }
    if (Sg.quake) pebbles(sh, inst, C, Math.round(Sg.rocks * 0.6 * d * pc(P, "rocks_pct")), rw, z, A, 68);
  }
  arcs(sh, inst, t, Sg.bolts * boltK, rw, fy, H, z, A, 69, hexRgb(pv(P, "bolt_color"), BOLT), pc(P, "bolt_width_pct"));
}
// the sheath's width at height share hk (0 feet .. 1 top), as the fx3d.js shader shapes it: the teardrop (base widened as
// the bottom closes) times the round bowl over the lowest cb of it
function sheathW(hk, base, top, close, cb) {
  var sm = function (a, b, x) { x = cl((x - a) / (b - a)); return x * x * (3 - 2 * x); }, bs = base + (1 - base) * close;
  var w = (bs + (1 - bs) * sm(0, 0.32, hk)) * (1 - top * Math.pow(cl((hk - 0.38) / 0.62), 1.7));
  if (cb > 0 && hk < cb) { var q = 1 - hk / cb; w *= 1 - close + close * Math.sqrt(Math.max(0, 1 - q * q)); }
  return w;
}
// The flame trail = the path the aura's own surface stretches along (fx3d.js comet stretch; no second part, Daniel
// 2026-11-28 "one whole, a liquid flame"). C.hist = where the body centre was each past tick ([f, v, s] px in today's
// frame, newest first; fx3d.js keeps it). The last trail_ms of it, resampled evenly, is the path, so its length = speed x
// time. A wave (trail_wave_pct, wave length trail_wave_len_pct) ripples it up / down, growing toward the tail and
// travelling back like a flag. Returns {pts, k (fades it in with the length), taper, thin (width far down the tail)}.
function auraTrail(C, P, rw, lift) {
  var hs = C.hist; if (pv(P, "trail") === false || !hs || hs.length < 2) return null;
  var TM = (FXK() && FXK().TICK_MS) || 16, n = Math.max(1, Math.round(Math.max(0, +pv(P, "trail_ms") || 0) / TM));
  var src = [[0, 0, 0]], cum = [0], i;
  for (i = 1; i <= n && i < hs.length; i++) {
    var a = src[src.length - 1], b = hs[i], dd = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]);
    if (dd < 1e-4) continue;
    src.push(b); cum.push(cum[cum.length - 1] + dd);
  }
  var L = cum[cum.length - 1]; if (src.length < 2 || L < rw * 0.35) return null;
  var N = 24, pts = [], j = 0;
  for (i = 0; i < N; i++) {   // evenly spaced along the path
    var s = L * i / (N - 1); while (j < cum.length - 2 && cum[j + 1] < s) j++;
    var u = cl((s - cum[j]) / Math.max(1e-6, cum[j + 1] - cum[j])), p0 = src[j], p1 = src[j + 1];
    pts.push([p0[0] + (p1[0] - p0[0]) * u, p0[1] + (p1[1] - p0[1]) * u, p0[2] + (p1[2] - p0[2]) * u]);
  }
  var wv = pc(P, "trail_wave_pct"), wl = Math.max(0.5, rw * 5 * pc(P, "trail_wave_len_pct")), ph0 = C.t * 0.2 * pc(P, "flame_speed_pct");
  if (wv > 0) {   // the flag-like wave, up / down off the line (perpendicular to it), none at the start
    var wp = pts.map(function (q) { return q.slice(); });
    for (i = 1; i < N; i++) {
      var pa = pts[i - 1], pb = pts[Math.min(N - 1, i + 1)], T = [pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]], tl = Math.hypot(T[0], T[1], T[2]) || 1;
      T = scl(T, 1 / tl); var Nn = [-T[0] * T[1], 1 - T[1] * T[1], -T[2] * T[1]], nl = Math.hypot(Nn[0], Nn[1], Nn[2]);
      if (nl < 0.2) continue; Nn = scl(Nn, 1 / nl);
      var sk = i / (N - 1), amp = rw * 0.6 * wv * Math.pow(sk, 0.8) * Math.min(1, L / (rw * 4));
      wp[i] = add(pts[i], scl(Nn, amp * Math.sin(sk * L / wl * 6.2832 - ph0)), 1);
    }
    pts = wp;
  }
  var thin = Math.max(0.3, Math.pow(Math.max(1, L / (rw * 4)), -0.35 * pc(P, "trail_thin_pct")));
  if (lift) pts = pts.map(function (q) { return [q[0], q[1] + lift, q[2]]; });   // the raised centre line
  return {pts: pts, k: cl(L / (rw * 2.5)), taper: pc(P, "trail_taper_pct"), thin: Math.min(2, thin * pc(P, "trail_width_pct"))};
}
// Outer flames: strands born on the sheath's side at a new random spot each cycle (height between outer_from / to % of the
// aura), shooting out sideways (spread), curling up (curl), then burning off from the root. Shape curved = a smooth swoosh,
// jagged = a zigzag spike, mixed = each strand rolls one. Thick at the root, a point at the tip; they trail with the lean.
function outerFlames(sh, inst, t, P, K, Sg, rw, H, fy, z, A, lean, close, cb) {
  var n = Math.round(Math.max(0, +pv(P, "outer_count") || 0) * Sg.flame), shape = String(pv(P, "outer_shape"));
  var spread = 11 * z * pc(P, "outer_spread_pct"), len = 15 * z * pc(P, "outer_length_pct") * Sg.flame, curl = pc(P, "outer_curl_pct");
  var w0 = 0.9 * z * pc(P, "outer_width_pct"), spd = pc(P, "outer_speed_pct") * Sg.speed, jag = pc(P, "outer_jag_pct");
  var h0 = cl(pc(P, "outer_from_pct")), h1 = Math.max(h0, cl(pc(P, "outer_to_pct"))), al0 = A * pc(P, "outer_opacity_pct");
  var oc = String(pv(P, "outer_color")), col = oc === "main" ? K.m : oc === "deep" ? K.d : oc === "white" ? WHITE : K.h;
  for (var i = 0; i < n; i++) {
    var rnd = R(inst, 81, i), x = t * (0.03 + rnd() * 0.025) * spd + rnd(), ph = frac(x), q = R(inst, 82, i * 613 + Math.floor(x));
    var az = q() * TAU, hk = h0 + (h1 - h0) * q(), hb = fy + H * hk, sp = spread * (0.6 + q() * 0.8), ln = len * (0.6 + q() * 0.8);
    var jg = shape === "jagged" || (shape === "mixed" && q() < 0.5), zz = (q() < 0.5 ? 1 : -1), wk = w0 * (0.7 + q() * 0.6);
    var head = eo(cl(ph * 2.2)), tail = ei(cl((ph - 0.25) / 0.75)); if (head - tail < 0.02) continue;   // shoots out, then burns off from the root
    var ox = Math.cos(az), oz = Math.sin(az), tx = -oz, tz = ox, rr = rw * (0.85 + 0.25 * Math.sin(Math.PI * Math.min(1, hk * 1.1)));
    if (cb > 0 && hk < cb) { var qb = 1 - hk / cb; rr *= 1 - close + close * Math.sqrt(Math.max(0, 1 - qb * qb)); }   // hugging the round bottom
    var pt = function (s) {   // the strand's centre line at s (0 root .. 1 tip)
      var out = sp * (1 - Math.pow(1 - s, 2.2)), up = ln * Math.pow(s, 1.25 - 0.6 * Math.min(1.5, curl)) * (0.25 + 0.75 * curl) + ln * 0.15 * s;
      var zig = jg ? (((Math.floor(s * 5) & 1) ? 1 : -1) * (0.5 - Math.abs(frac(s * 5) - 0.5)) * 2 * 2.2 * z * jag * zz) : 0;
      var lk = (hk + up / Math.max(1, H)) * 0.8;
      return [ox * (rr + out) + tx * zig + lean[0] * lk, hb + up, oz * (rr + out) + tz * zig + lean[2] * lk];
    };
    // sample points: smooth = even steps; jagged = exactly on each zigzag corner, so the spikes snap
    var ss = [tail], k, fade = Math.min(1, (1 - ph) * 3.5);
    if (jg) { for (k = Math.ceil(tail * 10 + 1e-6); k / 10 < head; k++) ss.push(k / 10); }
    else for (k = 1; k < 8; k++) ss.push(tail + (head - tail) * k / 8);
    ss.push(head);
    // thickness along the visible part: thin where it burned off, fullest a quarter in, a point at the tip
    var wAt = function (s) { var u = (s - tail) / Math.max(1e-4, head - tail); return wk * (u < 0.25 ? 0.25 + 3 * u : 1 - (u - 0.25) / 0.75 * 0.97); };
    for (k = 1; k < ss.length; k++) {
      var A0 = pt(ss[k - 1]), B0 = pt(ss[k]), r0 = wAt(ss[k - 1]), r1 = wAt(ss[k]);
      sh.tube(A0, B0, r0 * 1.9, r1 * 1.9, K.m, al0 * fade * 0.45, {core: false, ink: 0});   // glow round it
      sh.tube(A0, B0, r0, r1, col, al0 * fade, {ink: 0});   // the bright strand (white-hot core)
    }
  }
}
// Flame layers: layer_count rings spread between layer_from and layer_to % of the aura's height, each sitting on the
// sheath's own outline at its height (layer_spread_pct of it), each a short band of the same shader flame whose top edge is
// torn into spiky tongues (layer_tongues round it, layer_spike_pct sharpness) rising and flickering on its own clock; lower
// rings flare out wider (layer_flare_pct), like a stacked skirt of flames. The ring line is never drawn (bottom faded out).
function flameLayers(sh, inst, P, K, Sg, rw, H, fy, z, A, lean, close, cb, tr) {
  var n = Math.max(0, Math.round(+pv(P, "layer_count") || 0)); if (!n) return;
  var lf = cl(pc(P, "layer_from_pct")), lt = Math.max(lf, cl(pc(P, "layer_to_pct"))), gap = n > 1 ? (lt - lf) / (n - 1) : 0.3;
  var base = pc(P, "aura_base_pct"), top = Math.min(1, pc(P, "aura_top_pct"));
  var lc = String(pv(P, "layer_color")), col = lc === "hot" ? K.h : lc === "deep" ? K.d : lc === "white" ? WHITE : K.m;
  for (var i = 0; i < n; i++) {
    var hk = n > 1 ? lf + (lt - lf) * i / (n - 1) : lf;
    var w = sheathW(hk, base, top, close || 0, cb || 0);
    var r = Math.max(0.6 * z, rw * w * pc(P, "layer_spread_pct")), bh = Math.max(2 * z, H * Math.max(0.1, gap) * 1.5 * pc(P, "layer_height_pct"));
    var lk = hk * hk, p0 = [lean[0] * lk, fy - 1.5 * z + H * hk, lean[2] * lk];
    sh.aura(p0, r, bh, scl(lean, 0.35), col, A, {hot: K.h, edge: K.d, look: {ring: 1, flare: pc(P, "layer_flare_pct") * (1.3 - hk) * (1 - 0.8 * (close || 0)),
      spike: pc(P, "layer_spike_pct"), flames: Math.max(1, +pv(P, "layer_tongues") || 1), tongue: pc(P, "layer_tongue_pct") * Sg.flame * 1.4,
      speed: pc(P, "layer_speed_pct") * Sg.speed * (0.85 + 0.3 * R(inst, 90, i)()), chaos: pc(P, "layer_chaos_pct") * Sg.chaos,
      gaps: pc(P, "flame_gaps_pct") * 0.6, sharp: Math.max(0.6, pc(P, "flame_sharp_pct")), opacity: pc(P, "layer_opacity_pct"), rim: pc(P, "rim_pct"),
      inner: pc(P, "inner_pct"), bands: Math.max(1, Math.round(+pv(P, "bands") || 1)), additive: pv(P, "additive") !== false,
      layer2: false, trail: tr, seed: ((inst.seed || 1) % 997) / 97 + i * 7.31}});
  }
}
// the charge / scream: energy pulled in from all round, a core glowing white, rumble rings, pebbles lifting, arcs
function chargeFx(sh, inst, C, P, K, Sg, z, fy, d, lp, T, grounded) {
  var t = C.t, u = t / T.c, i, rnd, rw = 8.5 * z, H = (14 * Sg.height + 4) * z - fy, gl = pc(P, "charge_glow_pct");
  for (i = 0; i < Math.round(14 * d * pc(P, "charge_streaks_pct")); i++) {
    rnd = R(inst, 71, i); var x = t * (0.05 + rnd() * 0.04) + rnd(), ph = frac(x), q = R(inst, 72, i * 59 + Math.floor(x));
    var az = q() * TAU, el = (q() * 100 - 25) * D, dir = [Math.cos(el) * Math.cos(az), Math.sin(el), Math.cos(el) * Math.sin(az)];
    var far = (26 + q() * 26) * z * (1 - ei(ph)) + rw * 0.8, ln = (5 + 6 * ph) * z;
    sh.tube(add(scl(dir, far + ln), [0, 2 * z, 0], 1), add(scl(dir, far), [0, 2 * z, 0], 1), 0.08 * z, 0.4 * z, q() < 0.4 ? WHITE : K.h, (0.3 + 0.7 * u) * Math.sin(Math.PI * ph), {core: false, ink: 0});
  }
  if (gl > 0) {
    var pul = 0.8 + 0.2 * Math.sin(t * (0.5 + u));
    sh.sph([0, 2 * z, 0], (2.5 + 4 * u) * z * pul * gl, K.h, 0.35 + 0.5 * u, {ink: 0});
    if (u > 0.75) sh.sph([0, 2 * z, 0], (5 + 32 * (u - 0.75)) * z * gl, WHITE, (u - 0.75) * 2.4 * (0.6 + 0.4 * Math.sin(t * 2.1)), {core: false, ink: 0});
  }
  if (grounded && pv(P, "ground_fx") !== false) {
    var g = C.gy + 0.3;
    for (i = 0; i < 3; i++) { var p3 = frac(t / 14 + i / 3);
      sh.ring([0, g, 0], [0, 1, 0], rw * (0.8 + p3 * 3.2), i % 2 ? EL.rock[1] : K.m, (1 - p3) * 0.6 * (0.4 + 0.6 * u), {ink: 0.3}); }
    pebbles(sh, inst, C, Math.round(Sg.rocks * d * pc(P, "rocks_pct")), rw, z, 0.4 + 0.6 * u, 73);
    if (Sg.bolts > 0 && lp > 0) for (i = 0; i < 2; i++) {   // stage 2 / 3: bolts grounding into the floor
      var q4 = R(inst, 74, i * 19 + (t >> 2)); if (q4() > 0.6 * u) continue;
      var a4 = q4() * TAU, A4 = [Math.cos(a4) * rw, fy + H * 0.3, Math.sin(a4) * rw], B4 = [Math.cos(a4) * rw * 2.6, C.gy + 0.4, Math.sin(a4) * rw * 2.6];
      sh.bolt(A4, B4, 5, 3 * z, 0.3 * z * pc(P, "bolt_width_pct"), hexRgb(pv(P, "bolt_color"), BOLT), 0.9, q4, {core: false, ink: 0});
    }
  }
  arcs(sh, inst, t, Sg.cbolts * lp * (0.3 + 0.7 * u), rw, fy, H, z, 1, 76, hexRgb(pv(P, "bolt_color"), BOLT), pc(P, "bolt_width_pct"));
}
// cracks running out from the feet: grow through the charge, break open at the burst, stay a while, fade
function cracks(sh, inst, C, P, T, z, d) {
  var t = C.t, g = C.gy + 0.25, top = T.b ? 1 : 0.6, ck = pc(P, "cracks_pct");
  var grow = T.c ? (t < T.c ? 0.6 * eo(t / T.c) : 0.6 + (top - 0.6) * eo((t - T.c) / 6)) : top * eo(t / 6);
  var a = 1 - cl((t - (T.c + T.b + 150)) / 40); if (a <= 0 || grow <= 0.01 || ck <= 0) return;
  var n = Math.round(9 * d * Math.min(2, ck));
  for (var i = 0; i < n; i++) {
    var rnd = R(inst, 75, i), az = i / n * TAU + rnd() * 0.5, ln = (14 + rnd() * 20) * z * grow * ck, prev = [Math.cos(az) * 3 * z, g, Math.sin(az) * 3 * z];
    for (var k = 1; k <= 3; k++) { var ang = az + (rnd() - 0.5) * 0.5, rr = 3 * z + ln * k / 3, p = [Math.cos(ang) * rr, g, Math.sin(ang) * rr];
      sh.tube(prev, p, 0.8 * z * (1 - k * 0.2), 0.6 * z * (1 - k * 0.25), EL.rock[2], a, {core: false, ink: 0});
      if (k === 2 && rnd() < 0.5) { var bA = ang + (rnd() < 0.5 ? 0.6 : -0.6), bq = [Math.cos(bA) * (rr + ln * 0.25), g, Math.sin(bA) * (rr + ln * 0.25)];
        sh.tube(p, bq, 0.45 * z, 0.1 * z, EL.rock[2], a, {core: false, ink: 0}); }
      prev = p; }
  }
  if (T.b && t >= T.c) sh.ring([0, g, 0], [0, 1, 0], 10 * z, EL.rock[2], a * 0.7, {core: false, ink: 0});
}
// the burst: a white flash, a light pillar shooting up, a dome and floor shock rings, streaks, bolts, rocks and dust
function burstFx(sh, inst, C, P, K, Sg, z, d, lp, T, grounded) {
  var age = C.t - T.c, b = cl(age / T.b), e = eo(b * 1.4), a = 1 - b, R0 = +P.radius * C.ps, L = +P.length * C.ps * Sg.height, g = C.gy + 0.3, i, rnd;
  if (age < T.b) {
    if (age < 5) { sh.sph([0, 2 * z, 0], (12 + 6 * age) * z, WHITE, 1 - age / 5, {ink: 0}); sh.sph([0, 2 * z, 0], (20 + 8 * age) * z, K.h, (1 - age / 5) * 0.5, {core: false, ink: 0}); }
    var ph = eo(b * 2.2), wid = 9 * z * (1 - 0.5 * b) * pc(P, "pillar_width_pct");
    if (L > 0 && wid > 0) { sh.tube([0, g, 0], [0, g + L * ph, 0], wid, wid * 0.35, K.m, a * 0.75, {ink: 0.4});
      sh.tube([0, g, 0], [0, g + L * ph * 0.92, 0], wid * 0.5, wid * 0.15, K.h, a); }
    if (pv(P, "burst_rings") !== false) {
      sh.sph([0, 0, 0], R0 * 0.55 * e, K.h, a * 0.2, {core: false, ink: 0});
      sh.ring([0, 0, 0], [0, 1, 0], R0 * 0.55 * e, WHITE, a * 0.8, {ink: 0.3});
      sh.ring([0, g, 0], [0, 1, 0], R0 * eo(b * 1.15), WHITE, a, {ink: 0.5});
      sh.ring([0, g, 0], [0, 1, 0], R0 * 0.7 * eo(b), K.m, a, {ink: 0.5});
    }
    for (i = 0; i < Math.round(18 * d * pc(P, "burst_streaks_pct")); i++) { rnd = R(inst, 77, i); var az = rnd() * TAU, el = (rnd() * 45 - 8) * D, dir = [Math.cos(el) * Math.cos(az), Math.sin(el), Math.cos(el) * Math.sin(az)];
      var s0 = R0 * 0.25 * e + 6 * z, s1 = s0 + R0 * (0.3 + rnd() * 0.4) * (1 - b * 0.8);
      sh.tube(scl(dir, s0), scl(dir, s1), 0.7 * z, 0, i % 3 ? K.h : WHITE, a, {core: false, ink: 0}); }
    var nb = Sg.bolts * lp, BC = hexRgb(pv(P, "bolt_color"), BOLT);
    if (nb > 0 && age < 14) for (i = 0; i < Math.ceil(nb * 1.5); i++) { var q = R(inst, 78, i * 17 + (age >> 1)), az4 = q() * TAU;
      var A4 = [Math.cos(az4) * 6 * z, (q() - 0.3) * 14 * z, Math.sin(az4) * 6 * z], rr4 = R0 * 0.6 * (0.5 + q() * 0.5);
      sh.bolt(A4, [Math.cos(az4) * rr4, A4[1] + (q() - 0.5) * 10 * z, Math.sin(az4) * rr4], 6, 4 * z, 0.35 * z * pc(P, "bolt_width_pct"), q() < 0.5 ? WHITE : BC, 1 - age / 14, q, {core: false, ink: 0}); }
  }
  if (!grounded || age >= 60 || pv(P, "ground_fx") === false) return;
  for (i = 0; i < Math.round(14 * d * Sg.size * pc(P, "rocks_pct")); i++) { rnd = R(inst, 79, i); var az2 = rnd() * TAU, dir2 = [Math.cos(az2) * 0.8, 0.6 + rnd() * 0.8, Math.sin(az2) * 0.8];
    var p = thrown([Math.cos(az2) * 5 * z, C.gy + 1, Math.sin(az2) * 5 * z], dir2, (1.6 + rnd() * 2.6) * z, age, 0.2 * C.ps, C.gy);
    sh.chunk(rnd() < 0.5 ? "shard" : "cube", p, (0.6 + rnd() * 1.0) * z, [age * 0.3 + i, age * 0.2, i], EL.rock[i % 2], Math.min(1, (1 - age / 60) * 1.5), {ink: 0.7}); }
  for (i = 0; i < Math.round(10 * d * pc(P, "dust_pct")); i++) { rnd = R(inst, 80, i); var az3 = rnd() * TAU, dist = 6 * z + R0 * 0.8 * eo(age / 40) * (0.6 + rnd() * 0.5);
    sh.sph([Math.cos(az3) * dist, C.gy + (2 + rnd() * 2) * z + age * 0.04 * z, Math.sin(az3) * dist], (2.5 + age * 0.12) * z, EL.rock[1], Math.max(0, 1 - age / 55) * 0.55, {core: false, ink: 0.3}); }
}
var TF = {};
TF.tfx_golden_ascension = function (sh, inst, C, P, K) {
  var T = tfx(P), Sg = stageOf(P), t = C.t, z = Math.max(0.2, pc(P, "aura_size_pct")) * Sg.size * C.ps, d = dens(P);
  var fy = C.fy == null ? C.gy : C.fy, grounded = fy - C.gy < 8 * C.ps, lp = pc(P, "lightning_pct");
  var am = auraAmt(T, t, P);
  if (am.A > 0.01) auraBody(sh, inst, C, P, K, Sg, z * am.s, am.A, fy, d, t < T.c ? 0 : lp, grounded);
  if (t < T.c) chargeFx(sh, inst, C, P, K, Sg, z, fy, d, lp, T, grounded);
  // the cracks and the burst stay where it went off (C.spot = that point now, fx3d.js), not on a fighter who moves on
  if (t <= T.c + 1) inst.tx_g = grounded;   // went off on the ground (not in the air): its marks stay even if it jumps
  var mark = sh.o.length, sp = C.spot, gs = t <= T.c + 1 ? grounded : !!inst.tx_g;
  if (gs && (T.c || T.b) && pv(P, "ground_fx") !== false) cracks(sh, inst, C, P, T, z, d);
  if (T.b && t >= T.c) burstFx(sh, inst, C, P, K, Sg, z, d, lp, T, gs);
  if (sp) for (var i = mark; i < sh.o.length; i++) { var e = sh.o[i]; e.p = add(e.p, sp, 1); if (e.q) e.q = add(e.q, sp, 1); }
};

// ---------------------------------------------------------------- the recipe
// the shapes of an effect now (C from fx3d.js, or from parts2d below)
function parts(inst, host, C) {
  var P = inst.fx.params, s = st(P), fn = PF[s] || IF[s] || TF[s], out = [];
  if (!fn) return out;
  fn(new Sh(out), inst, C, P, colours(inst, host));
  return out;
}

// ---------------------------------------------------------------- FX Kit hooks
function onSpawn(inst, host) { inst.hx_path = [[inst.x, inst.y]]; inst.hx_sh = false; inst.hx_hs = false; }
function onTick(inst, host) {
  if (!inst.hx_path) onSpawn(inst, host);
  inst.hx_path.push([inst.x, inst.y]); if (inst.hx_path.length > 16) inst.hx_path.shift();
  var P = inst.fx.params, sp = Math.max(0, +P.shake_px || 0);
  if (isTransform(st(P))) {   // the ground rumbles through the charge, the camera kicks on the burst
    var T = tfx(P);
    if (host && host.shake && sp > 0) {
      if (T.b && inst.age === T.c) host.shake(sp);
      else if (inst.age < T.c && inst.age % 8 === 0) host.shake(sp * (0.15 + 0.3 * inst.age / T.c));
    }
    return;
  }
  // the camera kicks when an impact bursts / a punch lands
  if (!inst.hx_sh && host && sp > 0 && inst.age === (isPunch(st(P)) ? swing(P) : 0)) { inst.hx_sh = true; if (host.shake) host.shake(sp); }
}
// impacts hit inside radius in their first ticks; a punch FX hits round the fist on the contact beat (when it deals damage)
function hit(inst, tx, ty, hr, ps) {
  var P = inst.fx.params, t = inst.age, d = Math.hypot(tx - inst.x, ty - inst.y);
  if (isTransform(st(P))) { var T = tfx(P); return !!T.b && t >= T.c && t <= T.c + 3 && d <= hr + +P.radius * ps; }   // the burst's push
  if (isPunch(st(P))) { var T = swing(P); return t >= T - 1 && t <= T + 1 && d <= hr + +P.radius * ps * 1.5; }
  return t <= swing(P) + 1 && d <= hr + +P.radius * ps;
}
function body() { return null; }
function hitDir(inst) { return inst.dir; }
function hitFreeze(inst, host) {
  var n = Math.max(0, Math.trunc(+inst.fx.params.hitstop_ticks || 0));
  if (n > 0 && !inst.hx_hs && host && host.hitstop) { inst.hx_hs = true; host.hitstop(n); }
}

// ---------------------------------------------------------------- 2D drawing (FX Studio, or fx3d render "card")
// The same shapes flattened onto the aim plane: f along the aim, v up the screen, s dropped (a little depth tint).
function draw(pen, inst, host, ps) {
  var u = inst.dir && (inst.dir[0] || inst.dir[1]) ? inst.dir : [inst.facing || 1, 0], n = Math.hypot(u[0], u[1]) || 1;
  u = [u[0] / n, u[1] / n];
  var up = u[0] >= 0 ? [u[1], -u[0]] : [-u[1], u[0]];   // the side of the aim that faces up the screen
  var pth = inst.hx_path || [], m = pth.length, path = [];
  for (var i = 0; i < m; i++) { var dx = pth[i][0] - inst.x, dy = pth[i][1] - inst.y; path.push([dx * u[0] + dy * u[1], dx * up[0] + dy * up[1], 0]); }
  var sp = m > 1 ? Math.hypot(pth[m - 1][0] - pth[m - 2][0], pth[m - 1][1] - pth[m - 2][1]) : 0;
  var vel = m > 1 ? [(pth[m - 1][0] - pth[m - 2][0]) * u[0] + (pth[m - 1][1] - pth[m - 2][1]) * u[1], (pth[m - 1][0] - pth[m - 2][0]) * up[0] + (pth[m - 1][1] - pth[m - 2][1]) * up[1], 0] : [0, 0, 0];
  var C = {t: inst.age, ps: ps || 1, path: path, sp: sp, gy: -(+inst.fx.params.ground_px || 14) * (ps || 1), vel: vel, solo: !!(host && host.solo)};
  var W = function (p) { return [inst.x + u[0] * p[0] + up[0] * p[1], inst.y + u[1] * p[0] + up[1] * p[1]]; };
  pen.add(inst.fx.blend === "additive");
  parts(inst, host, C).forEach(function (e) {
    var a = e.a * 255, A = W(e.p);
    if (e.k === "sph") { pen.glow(A[0], A[1], e.r * (e.st || 1) * 1.3, e.c, a, 0.75); }
    else if (e.k === "aura") { var M2 = W([e.p[0], e.p[1] + e.h * 0.5, e.p[2]]); pen.glow(M2[0], M2[1], e.h * 0.55, e.c, a * 0.6, 0.6); pen.glow(M2[0], M2[1], e.r * 1.1, e.hot || e.c, a * 0.5, 0.75); }
    else if (e.k === "tube") { var B = W(e.q), dx2 = B[0] - A[0], dy2 = B[1] - A[1], L = Math.hypot(dx2, dy2) || 1, nx = -dy2 / L, ny = dx2 / L;
      pen.poly([[A[0] + nx * e.r, A[1] + ny * e.r], [B[0] + nx * e.r1, B[1] + ny * e.r1], [B[0] - nx * e.r1, B[1] - ny * e.r1], [A[0] - nx * e.r, A[1] - ny * e.r]], e.c, a);
      if (e.r < 0.4 && e.r1 < 0.4) pen.line(A[0], A[1], B[0], B[1], e.c, a, 0.8); }
    else if (e.k === "ring") { var nn = e.n, nl = Math.hypot(nn[0], nn[1], nn[2]) || 1, ry = Math.max(0.15, Math.abs(nn[2]) / nl + 0.15 * Math.abs(nn[1]) / nl);
      var ang = Math.atan2(u[1], u[0]) + (Math.abs(nn[0]) >= Math.abs(nn[1]) ? Math.PI / 2 : 0);
      pen.ring(A[0], A[1], e.r, e.r * ry, ang, e.c, a, Math.max(0.8, e.r * 0.09)); }
    else { var s = e.r; pen.poly([[A[0], A[1] - s], [A[0] + s * 0.7, A[1]], [A[0], A[1] + s], [A[0] - s * 0.7, A[1]]], e.c, a); }
  });
  pen.add(false);
}

// FX-specific settings panels (FX Studio 3D builds a panel from these for the picked effect's style): groups of
// [key, label, kind ("rng" min max step | "chk" | "col" | "sel" options), hint]. Keys are params.<key>.
var UI = {tfx_golden_ascension: [
  ["Phases", [
    ["stage", "Stage", "sel", [[1, "1 · gold flame aura"], [2, "2 · tighter, faster + electric arcs"], [3, "3 · biggest, heavy lightning, ground breaking"]], "A preset look on top of every setting below"],
    ["charge", "Charge / scream", "chk", null, "Energy pulled in, the ground cracking, pebbles lifting before the burst"],
    ["swing_ticks", "Charge length (ticks)", "rng", [0, 240, 1], "16 ms each: 70 = 1.1 s. Set the action about this long + 30"],
    ["burst", "Burst", "chk", null, "The flash, light pillar, shock rings and push"],
    ["aura", "Lasting aura", "chk", null, "The flame aura that stays after the burst"],
    ["aura_s", "Aura lasts (s)", "rng", [0, 120, 0.5], "Seconds it stays after the burst, whatever the fighter does"]]],
  ["Aura shape", [
    ["aura_size_pct", "Size (%)", "rng", [20, 300, 1], "Everything about the aura, scaled"],
    ["aura_width_pct", "Width (%)", "rng", [20, 300, 1], "How far it stands off the body"],
    ["aura_height_pct", "Height (%)", "rng", [20, 300, 1], "How far above the head it reaches"],
    ["aura_raise_pct", "Raise (%)", "rng", [-100, 300, 1], "Moves the trail's centre line up the body (and the whole aura while off the ground); negative = down"],
    ["aura_base_pct", "Width at the feet (%)", "rng", [0, 150, 1], "0 = pinched to a point under the feet, 100 = as wide as the middle"],
    ["aura_top_pct", "Top closes (%)", "rng", [0, 100, 1], "0 = open column, 100 = closes to a flame point over the head"],
    ["lean_pct", "Trails when moving (%)", "rng", [0, 300, 1], "How much the top streams behind a moving fighter"],
    ["pulse_pct", "Breathing (%)", "rng", [0, 200, 1], "The whole aura swelling and shrinking"],
    ["air_close", "Round bottom in the air", "chk", null, "Off the ground the bottom closes into a sphere-like bowl under the feet (opens again on landing)"],
    ["air_round_pct", "Bowl depth (%)", "rng", [0, 300, 1], "How far the round bottom hangs below the feet"]]],
  ["Flame trail", [
    ["trail", "Trail when moving", "chk", null, "The aura itself stretches back along the path the fighter took into one tapering tail (ground dashes too)"],
    ["trail_ms", "Trail holds (ms)", "rng", [0, 2000, 10], "How much of the path it keeps: the faster the move, the longer the trail"],
    ["trail_width_pct", "Width (%)", "rng", [0, 300, 1], "How wide the tail stays further down it"],
    ["trail_thin_pct", "Thinner when long (%)", "rng", [0, 300, 1], "How much a long (fast) trail thins out against a short one"],
    ["trail_taper_pct", "Taper (%)", "rng", [0, 400, 1], "How quickly it narrows to a point at the tail (0 = even width)"],
    ["trail_wave_pct", "Wave (%)", "rng", [0, 400, 1], "How far it ripples up and down, growing toward the tail (0 = follows the path exactly)"],
    ["trail_wave_len_pct", "Wave length (%)", "rng", [10, 400, 1], "Longer = slower, wider swells"]]],
  ["Flames", [
    ["flame_count", "Flame tongues round it", "rng", [1, 24, 1], "How many tongues are torn out of it round the body"],
    ["flame_height_pct", "Tongue length (%)", "rng", [0, 300, 1], "How far the tongues shoot up past the top"],
    ["flame_speed_pct", "Rise speed (%)", "rng", [0, 400, 1], "How fast the flames climb"],
    ["flame_chaos_pct", "Chaos (%)", "rng", [0, 300, 1], "Turbulence: 0 = calm and even, high = wild and broken"],
    ["flame_gaps_pct", "Gaps (%)", "rng", [0, 100, 1], "Holes torn through the sheath between tongues"],
    ["flame_sharp_pct", "Hard edges (%)", "rng", [0, 100, 1], "100 = crisp cel-cut flame edges, 0 = soft"]]],
  ["Colour & glow", [
    ["aura_color", "Main colour", "col", null, "The body of the flames (Colour = palette in Look tints all three)"],
    ["aura_hot", "Hot colour", "col", null, "The bright rim / inner band"],
    ["aura_edge", "Deep colour", "col", null, "The darkest band, at the tongues' roots"],
    ["aura_opacity_pct", "Opacity (%)", "rng", [0, 100, 1], ""],
    ["rim_pct", "Rim glow (%)", "rng", [0, 200, 1], "How bright the outline of the sheath is"],
    ["inner_pct", "See-through middle (%)", "rng", [0, 100, 1], "How much of it shows over the body (low = the body stays visible)"],
    ["bands", "Cel bands", "rng", [1, 6, 1], "Flat colour steps from deep to hot"],
    ["additive", "Glow (additive)", "chk", null, "Adds light (bright on dark scenes); off = painted colour"],
    ["inner_layer", "Inner hot layer", "chk", null, "A second, tighter, brighter sheath inside"],
    ["sparks_pct", "Rising sparks (%)", "rng", [0, 300, 1], ""]]],
  ["Lightning", [
    ["lightning_pct", "Lightning (%)", "rng", [0, 400, 1], "Arcs on the body: stage 1 only while charging, stage 2 / 3 the whole time"],
    ["bolt_color", "Bolt colour", "col", null, ""],
    ["bolt_width_pct", "Bolt thickness (%)", "rng", [10, 400, 1], ""]]],
  ["Flame layers", [
    ["layers", "Flame layers", "chk", null, "Rings stacked from the feet to the top of the aura, each a crown of rising spiky flames (the rings are invisible)"],
    ["layer_count", "Layers", "rng", [1, 16, 1], "How many rings, spread evenly between the two heights below"],
    ["layer_from_pct", "Lowest layer at (%)", "rng", [0, 100, 1], "0 = at the feet"],
    ["layer_to_pct", "Highest layer at (%)", "rng", [0, 100, 1], "100 = the top of the aura"],
    ["layer_tongues", "Flames per layer", "rng", [2, 40, 1], "Spikes round each ring"],
    ["layer_tongue_pct", "Flame length (%)", "rng", [0, 400, 1], "How far each ring's flames rise"],
    ["layer_height_pct", "Layer depth (%)", "rng", [10, 400, 1], "How tall each ring's band is (more = layers overlap)"],
    ["layer_spread_pct", "Layer width (%)", "rng", [20, 300, 1], "Ring size against the aura's outline at that height"],
    ["layer_flare_pct", "Flare out (%)", "rng", [-100, 300, 1], "How much the flames lean outward as they rise (lower layers flare more)"],
    ["layer_spike_pct", "Spikiness (%)", "rng", [0, 100, 1], "0 = rounded licks, 100 = sharp spikes"],
    ["layer_speed_pct", "Rise speed (%)", "rng", [0, 400, 1], "Each layer flickers on its own clock"],
    ["layer_chaos_pct", "Chaos (%)", "rng", [0, 300, 1], ""],
    ["layer_color", "Colour", "sel", [["main", "main colour"], ["hot", "hot colour"], ["deep", "deep colour"], ["white", "white"]], ""],
    ["layer_opacity_pct", "Opacity (%)", "rng", [0, 100, 1], "Per layer: they add up where they overlap"]]],
  ["Outer flames", [
    ["outer_flames", "Outer flames", "chk", null, "Flame strands bursting out of the aura's sides, flaring out and curling up"],
    ["outer_count", "How many", "rng", [0, 40, 1], "Strands alive at once (each is born at a new random spot)"],
    ["outer_shape", "Shape", "sel", [["curved", "curved · smooth swooshes"], ["jagged", "jagged · zigzag spikes"], ["mixed", "mixed · each one rolls"]], ""],
    ["outer_spread_pct", "Spread out (%)", "rng", [0, 400, 1], "How far they fly out sideways from the aura"],
    ["outer_length_pct", "Length (%)", "rng", [0, 400, 1], "How far they reach up"],
    ["outer_curl_pct", "Curl up (%)", "rng", [0, 200, 1], "0 = straight out to the side, 100 = flare out then sweep up, 200 = shoot up fast"],
    ["outer_from_pct", "Start from height (%)", "rng", [0, 100, 1], "Lowest point on the aura they are born (0 = the feet)"],
    ["outer_to_pct", "Up to height (%)", "rng", [0, 100, 1], "Highest point on the aura they are born (100 = the top)"],
    ["outer_width_pct", "Thickness (%)", "rng", [10, 400, 1], ""],
    ["outer_jag_pct", "Zigzag size (%)", "rng", [0, 400, 1], "How sharp the jagged ones zigzag"],
    ["outer_speed_pct", "Speed (%)", "rng", [0, 400, 1], "How fast each one shoots out and burns off"],
    ["outer_color", "Colour", "sel", [["hot", "hot colour"], ["main", "main colour"], ["deep", "deep colour"], ["white", "white"]], ""],
    ["outer_opacity_pct", "Opacity (%)", "rng", [0, 100, 1], ""]]],
  ["Charge & burst", [
    ["charge_streaks_pct", "Energy pulled in (%)", "rng", [0, 300, 1], ""],
    ["charge_glow_pct", "Core glow (%)", "rng", [0, 300, 1], ""],
    ["radius", "Burst push reach (px)", "rng", [0, 300, 1], "28 px = one body. Push strength = Knockback in Damage"],
    ["length", "Light pillar height (px)", "rng", [0, 600, 1], "0 = no pillar"],
    ["pillar_width_pct", "Pillar width (%)", "rng", [0, 300, 1], ""],
    ["burst_rings", "Dome + shock rings", "chk", null, ""],
    ["burst_streaks_pct", "Burst streaks (%)", "rng", [0, 300, 1], ""],
    ["shake_px", "Camera shake", "rng", [0, 30, 1], ""]]],
  ["Ground", [
    ["ground_fx", "Ground effects", "chk", null, "Cracks, rumble rings, dust, pebbles and rocks"],
    ["cracks_pct", "Cracks (%)", "rng", [0, 300, 1], ""],
    ["rocks_pct", "Rocks & pebbles (%)", "rng", [0, 300, 1], ""],
    ["dust_pct", "Dust (%)", "rng", [0, 300, 1], ""],
    ["density", "Overall amount (x)", "rng", [0.2, 4, 0.1], "Every count above, multiplied"]]]]};
G.HYPERFX = {STYLES: STYLES, UI: UI, PUNCH: PUNCH, IMPACT: IMPACT, TRANSFORM: TRANSFORM, STAGE: STAGE, NAMES: NAMES, DEFAULTS: DEFAULTS, EL: EL, ELEMENT: ELEMENT,
  isHyper: isHyper, isPunch: isPunch, isTransform: isTransform, tfx: tfx, activeTicks: activeTicks, totalTicks: totalTicks, onSpawn: onSpawn, onTick: onTick,
  hit: hit, body: body, hitDir: hitDir, hitFreeze: hitFreeze, draw: draw, parts: parts, colours: colours, swing: swing, hold: hold};
// register the styles with the FX Kit (fxkit.js loads first)
if (G.FXK) {
  STYLES.forEach(function (s) { if (G.FXK.TECH_STYLES.indexOf(s) < 0) G.FXK.TECH_STYLES.push(s); G.FXK.TECH_STYLE_DEFAULTS[s] = DEFAULTS[s]; });
}

// ---------------------------------------------------------------- presets (FX Studio 3D; added when presets.js loaded first)
var DESC = {
  pfx_speed_burst: "Speed lines stream off the fist as it drives in; on contact a cone of speed lines bursts forward and a pressure ring snaps off the knuckles",
  pfx_afterimage: "Ghost fists left along the punch's path with a hot smear between them; on contact the afterimages overshoot past the knuckles",
  pfx_vacuum_cone: "Pressure rings stack into a cone ahead of the fist as it accelerates, a white vapour collar pops at the contact beat and the air ball is shoved forward",
  pfx_flame_fist: "The fist is wrapped in fire: flame tongues lick back along the punch, embers peel off, and a fire bloom with a ring erupts on contact. Fire colours (Colour = palette tints them)",
  pfx_thunder_fist: "Lightning crackles round the forearm's path and sparks spit off the fist; on contact a forked bolt jumps forward. Thunder colours",
  pfx_frost_fist: "Ice crystals form along the punch in a cold mist; on contact a frozen ring flashes and shatters into shards that fall to the floor. Frost colours",
  pfx_void_fist: "A dark core with a violet rim swallows rings into the fist; on contact an inverted black shock ring and dark spikes blow outward. Void colours",
  pfx_cyclone_hook: "Wind strokes spiral round the punch with debris caught in them; on contact a twin corkscrew vortex drives forward. Wind colours",
  pfx_rocket_jab: "A jet flame with shock diamonds blasts out behind the fist (opposite the drive), smoke puffs trail, and a fire burst + ring pops on contact",
  pfx_phantom_rush: "A flurry of phantom fists stabs out round the aim at uneven beats (never twice the same), each landing with its own flash and ring",
  ifx_shock_crater: "A white flash, a doubled shock ring racing over the floor, cracks running out, crater rocks thrown up and a dust ring rolling away",
  ifx_spark_star: "A spiky anime star, an X glint and a hail of sparks sprayed along the blow that arc down to the floor",
  ifx_ripple_dome: "Space bends: speed lines rush in, then see-through air shells and thin rings ripple outward one after another",
  ifx_pierce_through: "The blow goes through: an energy cone and rings blast out the BACK of the target with speed lines and shards flung onward",
  ifx_inferno_burst: "A banded fireball with flame tongues bursting out, embers rising, smoke piling up and a scorch ring on the floor. Fire colours",
  ifx_thunderclap: "A flickering bolt drops from the sky onto the target, branches fork out along the blow and crackles run over the floor. Thunder colours",
  ifx_glacial_shatter: "Ice spikes erupt round the target with a frost ring underfoot, hang for a beat, then shatter into falling shards. Frost colours",
  ifx_void_implosion: "A dark sphere sucks in rings and lines, a beat of stillness, then it bursts out in a black ring and violet shards. Void colours",
  ifx_earthsplitter: "A crack races out along the blow and rock spires burst up one after another, throwing stones and rolling dust",
  ifx_sonic_boom: "A vapour cone flares out behind the target along the blow, a shock ring, speed lines and a dust ring kicked up off the floor"};
var HEX = {fire: "#ff7018", thunder: "#6ea0ff", frost: "#78d7ff", void: "#8c32eb", wind: "#96ffd7"};
function preset(s) {
  var p = isPunch(s), e = ELEMENT[s], P = Object.assign({style: s}, DEFAULTS[s]);
  return {name: NAMES[s], group: p ? "Punching FX" : "Impact FX", desc: DESC[s] + (p
      ? ". Rides the right hand (Start at = another hand / foot to move it); set its start frame so swing ticks after it is the punch's contact beat. Visual only (turn on Deals damage to make it hit)"
      : ". Starts ON the target; hits once as it bursts, with hit-stop and a camera kick"),
    effects: [{prim: "technique", name: NAMES[s], tag: "energy", anchor: p ? "haR" : "target", blend: "normal",
      battle: p ? {deals_damage: false, damage: 0, pierce: true, rehit_ticks: 0, knockback: 0}
                : {deals_damage: true, damage: 2, pierce: true, rehit_ticks: 0, knockback: 12},
      motion: {kind: p ? "attached" : "static", aim: "target"},
      color: e ? {mode: "solid", c1: HEX[e]} : {mode: "palette"},
      params: P, fx3d: {render: "3d", toon_ink_m: 0.025}}]};
}
if (G.FX_PRESETS && !G.FX_PRESETS.some(function (q) { return q.group === "Punching FX"; })) PUNCH.concat(IMPACT).forEach(function (s) { G.FX_PRESETS.push(preset(s)); });
// Transformation FX: one preset per stage. Put it on the action that transforms (charge = swing_ticks, set the action
// about that long); the aura then stays aura_s seconds whatever the fighter does. Burst = a push, no damage.
var STAGE_DESC = {
  1: "Stage 1: the golden flame aura. The fighter charges (energy pulled in, the ground cracking, pebbles lifting, a few arcs), bursts in a white flash with a light pillar, shock rings and flung rocks, then keeps a flickering gold aura round the whole body",
  2: "Stage 2: a brighter, tighter aura that flickers faster, with blue-white electric arcs crackling over the body the whole time; bolts ground into the floor while it charges",
  3: "Stage 3: the biggest, wildest aura (taller crown, many more flames), heavy lightning, and the ground breaking up and floating round the feet the whole time it lasts"};
function tPreset(n) {
  var P = Object.assign({style: TRANSFORM[0]}, DEFAULTS[TRANSFORM[0]], {stage: n});
  if (n === 3) { P.swing_ticks = 90; P.radius = 80; P.length = 150; P.shake_px = 12; }
  return {name: "Golden ascension · Stage " + n, group: "Transformation FX",
    desc: STAGE_DESC[n] + ". Charge = swing ticks, aura lasts aura_s seconds after the burst (follows the fighter), the burst pushes enemies within radius away (Knockback) with no damage. Turn charge / burst / aura off in All look settings",
    effects: [{prim: "technique", name: "Golden ascension " + n, tag: "aura", anchor: "figure", blend: "normal",
      battle: {deals_damage: true, damage: 0, pierce: true, rehit_ticks: 0, knockback: n === 3 ? 55 : 40},
      motion: {kind: "attached", aim: "target"}, color: {mode: "solid", c1: "#ffcc30"},
      params: P, fx3d: {render: "3d", toon_ink_m: 0.02}}]};
}
if (G.FX_PRESETS && !G.FX_PRESETS.some(function (q) { return q.group === "Transformation FX"; })) [1, 2, 3].forEach(function (n) { G.FX_PRESETS.push(tPreset(n)); });
})(window);
