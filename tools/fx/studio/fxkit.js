/* FX Kit runtime (pb_fxkit v1) — the reference implementation.
 *
 * Every FX the Studio authors is an EFFECT: one drawing primitive + where it
 * starts (anchor joint), how it moves (motion), what colour it takes (colour
 * source) and when it plays (frames of the character's action).  The seven
 * primitives are the engine's own drawing routines, lifted out of the
 * hardcoded effect classes so any character can compose them:
 *
 *   ribbon     components.TrailComponent.draw       (laser trail)
 *   arc        combat.CrescentWave.draw             (slash crescent)
 *   beam       combat.RichBeamProjectile.draw       (segmented beam)
 *   sprite     combat.bullet_sprite / bolt_sprite + Projectile.draw (orbs, bolts)
 *   particles  combat.BurstParticle                 (sparks, dust)
 *   glow       TrailComponent head glow/core        (spheres, flares)
 *   ghost      figure afterimages (silhouette)      (speed ghosts)
 *   weapon     melee hitbox: a capsule between two anchors (e.g. near hand ->
 *              weapon tip) that follows the frames; invisible in-game
 *
 * PURPOSE: every effect is either visual-only or a damaging attack
 * (fx.battle.deals_damage).  A damaging effect hits a target when the shape
 * it DRAWS comes within the target's hurt radius (16 px = PROJ_HIT_RADIUS for
 * every figure), so it damages exactly where it is seen to touch.
 *
 * PORTING CONTRACT (Phase 2: laser/fxkit.py must mirror this file 1:1)
 *   - One update() per 16 ms tick (config.TICK_MS); nothing reads wall time.
 *   - All randomness goes through FXK.rng (mulberry32), seeded per instance,
 *     so the same effect produces the same particles in both runtimes.
 *   - Coordinates are game px, y down, relative to the figure position.
 *     Joint anchors come from the exported joint_track × px_per_unit and are
 *     mirrored on x when the figure faces left.
 *   - Where the Qt code truncates with int(), this file uses Math.trunc.
 *   - pscale is the engine's position_scale(); widths/radii multiply by it.
 */
(function (G) {
"use strict";
var TICK_MS = 16, TICK_S = TICK_MS / 1000, D = Math.PI / 180;
var trunc = Math.trunc;

// ---------------------------------------------------------------- random
function rng(seed) {
  var a = seed >>> 0;
  var f = function () {
    a = (a + 0x6D2B79F5) >>> 0;
    var t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  f.uniform = function (lo, hi) { return lo + (hi - lo) * f(); };
  return f;
}
// FNV-1a over a string -> uint32 (stable effect-id salt for seeds).
function hash32(s) {
  var h = 0x811C9DC5;
  for (var i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h >>> 0;
}

// ---------------------------------------------------------------- colour
// palette.build_lut(): identical interpolation and int() truncation.
function buildLut(pal, size) {
  size = size || 256;
  var n = pal.length, lut = [];
  for (var i = 0; i < size; i++) {
    var t = i / size * n, lo = trunc(t) % n, hi = (lo + 1) % n, f = t - trunc(t);
    lut.push([trunc(pal[lo][0] + (pal[hi][0] - pal[lo][0]) * f),
              trunc(pal[lo][1] + (pal[hi][1] - pal[lo][1]) * f),
              trunc(pal[lo][2] + (pal[hi][2] - pal[lo][2]) * f)]);
  }
  return lut;
}
function hexRgb(h, d) {
  if (typeof h !== "string") return d;
  h = h.replace("#", "");
  if (h.length !== 6) return d;
  var v = [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  return v.some(isNaN) ? d : v;
}
function rgba(c, a) { return "rgba(" + trunc(c[0]) + "," + trunc(c[1]) + "," + trunc(c[2]) + "," + Math.max(0, Math.min(255, trunc(a))) / 255 + ")"; }

// Colour at position t (0 = tail/start .. 1 = head/end) for an instance.
//   palette : the character LUT, flowing by inst.flow (TrailComponent._color_at)
//   gradient: c1 solid up to start_fraction, then linear to c2 (trail_gradient)
//   solid   : c1
function colorAt(fx, inst, t, lut) {
  var c = fx.color;
  if (c.mode === "palette") {
    var idx = trunc((((t + inst.flow + (c.lut_offset || 0)) % 1) + 1) % 1 * 256) & 255;
    return lut[idx];
  }
  var c1 = hexRgb(c.c1, [255, 255, 255]);
  if (c.mode === "gradient") {
    var c2 = hexRgb(c.c2, c1), sf = c.start_fraction == null ? 0 : +c.start_fraction;
    if (t <= sf) return c1;
    var k = (t - sf) / Math.max(1e-6, 1 - sf);
    return [c1[0] + (c2[0] - c1[0]) * k, c1[1] + (c2[1] - c1[1]) * k, c1[2] + (c2[2] - c1[2]) * k];
  }
  return c1;
}
// Fixed colour pair (start, end) for primitives that fade over LIFE rather
// than along a path (particles, beam gradient, sprite).
function colorPair(fx, lut) {
  var c = fx.color;
  if (c.mode === "palette") {
    var a = (trunc(c.lut_index == null ? 128 : c.lut_index)) & 255;
    var b = (trunc(c.lut_index2 == null ? a : c.lut_index2)) & 255;
    return [lut[a], lut[b]];
  }
  var c1 = hexRgb(c.c1, [255, 255, 255]);
  return [c1, c.mode === "gradient" ? hexRgb(c.c2, c1) : c1];
}

// ---------------------------------------------------------------- geometry
function angleDegQt(dx, dy) { return Math.atan2(-dy, dx) / D; }   // geometry.angle_deg_qt
function norm(dx, dy) { var d = Math.sqrt(dx * dx + dy * dy); return d > 0.001 ? [dx / d, dy / d] : [1, 0]; }

// ---------------------------------------------------------------- sprites
// combat.bullet_sprite / bolt_sprite rendered once per key to an offscreen
// canvas, with the same int() ellipse bounds and gradient stops.
var SPR = {};
function canvas(w, h) { var c = document.createElement("canvas"); c.width = Math.max(1, w); c.height = Math.max(1, h); return c; }
function radial(g, cx, cy, r, stops) {
  var gr = g.createRadialGradient(cx, cy, 0, cx, cy, Math.max(0.0001, r));
  stops.forEach(function (s) { gr.addColorStop(s[0], s[1]); });
  return gr;
}
function ellipse(g, x, y, w, h) { g.beginPath(); g.ellipse(x + w / 2, y + h / 2, Math.max(0, w / 2), Math.max(0, h / 2), 0, 0, 6.283185307179586); g.fill(); }
function bulletSprite(r, gc, b, radius) {
  var key = "b" + r + "," + gc + "," + b + "," + Math.round(radius * 100) / 100;
  if (SPR[key]) return SPR[key];
  var glow = Math.max(1, radius * 3), size = Math.ceil(glow * 2) + 2, c = size / 2;
  var cv = canvas(size, size), g = cv.getContext("2d");
  g.fillStyle = radial(g, c, c, glow, [[0, rgba([r, gc, b], 140)], [1, rgba([r, gc, b], 0)]]);
  ellipse(g, trunc(c - glow), trunc(c - glow), trunc(glow * 2), trunc(glow * 2));
  var rad = Math.max(1, radius);
  g.fillStyle = radial(g, c, c, rad, [[0, "rgba(255,255,255," + 240 / 255 + ")"], [0.5, rgba([r, gc, b], 210)], [1, rgba([r, gc, b], 140)]]);
  ellipse(g, trunc(c - rad), trunc(c - rad), trunc(rad * 2), trunc(rad * 2));
  return (SPR[key] = {cv: cv, half: trunc(size / 2)});
}
function boltSprite(r, gc, b, radius, stretch, hot) {
  var key = "o" + r + "," + gc + "," + b + "," + Math.round(radius * 100) / 100 + "," + Math.round(stretch * 100) / 100 + "," + (hot ? 1 : 0);
  if (SPR[key]) return SPR[key];
  var glow = Math.max(1, radius * 3);
  var w = Math.ceil(glow * 2 * stretch) + 2, h = Math.ceil(glow * 2) + 2;
  var cx = w / 2, cy = h / 2, headX = w - glow;
  var cv = canvas(w, h), g = cv.getContext("2d");
  g.save(); g.translate(cx, cy); g.scale(stretch, 1);
  g.fillStyle = radial(g, 0, 0, glow, [[0, rgba([r, gc, b], 170)], [1, rgba([r, gc, b], 0)]]);
  ellipse(g, trunc(-glow), trunc(-glow), trunc(glow * 2), trunc(glow * 2));
  if (hot) {
    var g6 = glow * 0.6;
    g.fillStyle = radial(g, 0, 0, g6, [[0, "rgba(255,255,255," + 150 / 255 + ")"], [1, "rgba(255,255,255,0)"]]);
    ellipse(g, trunc(-g6), trunc(-g6), trunc(g6 * 2), trunc(g6 * 2));
  }
  g.restore();
  var rad = Math.max(1, radius) * 1.2;
  g.fillStyle = radial(g, headX, cy, rad, [[0, "rgba(255,255,255," + 245 / 255 + ")"], [0.5, rgba([r, gc, b], 220)], [1, rgba([r, gc, b], 0)]]);
  ellipse(g, trunc(headX - rad), trunc(cy - rad), trunc(rad * 2), trunc(rad * 2));
  return (SPR[key] = {cv: cv, headX: headX, halfH: h / 2});
}

// ---------------------------------------------------------------- schema
var PRIMS = ["ribbon", "arc", "beam", "sprite", "particles", "glow", "ghost", "weapon"];
var MOTIONS = ["attached", "static", "travel", "homing", "zigzag", "orbit"];
var AIMS = ["target", "facing", "angle", "weapon"];
// Default params per primitive = the engine constants of the effect it came from.
var PARAM_DEFAULTS = {
  ribbon: {max_points: 50, min_dist: 2, decay: 2, taper: true, w_tail: 1, w_head: 5, alpha: 220, head_glow_r: 1, head_dot_r: 1},
  arc: {radius: 42, span: 170, width: 6.5, tail: 0.95, segs: 16, grow: 0.85, core_alpha: 0.7, core_width: 0.3, orient: "motion", angle_deg: 0,
        placement: "anchor", back: 51, lead: 26},
  beam: {length: 200, w_start0: 6, w_start1: 6, w_end0: 2, w_end1: 2, segments: 1, glow: 0, glow_color: "", pulse_hz: 0, jitter: 0, detach_ticks: 0, grow_ticks: 0},
  sprite: {shape: "orb", radius: 3, stretch: 1, hot: false, halo: false, fade: true, trail_len: 5},
  particles: {mode: "burst", count: 12, rate_per_s: 60, angle_deg: 0, spread_deg: 30, speed_min: 50, speed_max: 150, gravity: 0, drag: 1, size_min: 3, size_max: 3, size_over_life: "shrink", life_min_ms: 200, life_max_ms: 400},
  glow: {r_start: 6, r_end: 6, a_center: 140, a_mid: 60, mid: 0.4, core_r: 0, fade: "out", pulse_hz: 0},
  ghost: {interval: 2, ghost_life: 14, alpha: 150, max: 12},
  weapon: {to_anchor: "wtip", width: 6}
};
var MOTION_DEFAULTS = {kind: "attached", aim: "target", angle_deg: 0, aim_offset_deg: 0, speed: 8,
  turn_deg: 6, amplitude: 55, freq: 0.18, orbit_rx: 46, orbit_ry: 46, orbit_deg: 1.12};
var COLOR_DEFAULTS = {mode: "palette", lut_index: 128, lut_index2: 128, lut_offset: 0, flow_speed: 0.008,
  c1: "#ffffff", c2: "#ff2200", start_fraction: 0};
// Damage settings (fx.battle).  damage is HP per hit, matching
// ai.apply_hp_damage(amount) — every built-in attack deals 1.
var BATTLE_DEFAULTS = {deals_damage: false, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0};
// Per-action settings (pack.action_settings[action]).  WHEN an action plays:
//   idle / run      locomotion (standing still / moving), no conditions
//   attack actions  the archetype decides when to attack; `chain_next` makes
//                   attacks run as a combo (attack_normal -> attack_normal_2 ...)
//                   that resets after `chain_reset_ms` without attacking
//   other actions   fire when their conditions are met (ANY or ALL), no more
//                   often than every `cooldown_ms`
var CONDITION_TYPES = {
  hp_below:      {pct: 50, repeat: false},             // own HP <= pct % (once per crossing unless repeat)
  attacks_made:  {count: 3},                           // after N attacks since this action last fired
  hits_taken:    {count: 3},                           // after being hit N times since it last fired
  target_within: {px: 80},                             // target closer than px
  target_beyond: {px: 200},                            // target further than px
  hit_by_fx:     {tags: ""},                           // hit by an enemy FX with one of these tags ("" = any)
  fx_near:       {tags: "", px: 60},                   // an enemy FX with one of these tags comes within px
  bullet_deflected: {},                                // this character just deflected a bullet
  after_actions: {sequence: ""}                        // just completed these actions in order, comma separated
};
var ACTION_DEFAULTS = {logic: "any", cooldown_ms: 0, conditions: [], chain_next: "", chain_reset_ms: 1000};
function actionKind(name) {
  if (name === "idle" || name === "run") return "locomotion";
  if (/^attack_normal/.test(name)) return "attack";
  return "triggered";
}
function normalizeAction(cfg) {
  cfg = fill(cfg || {}, ACTION_DEFAULTS);
  cfg.conditions = (cfg.conditions || []).filter(function (c) { return c && CONDITION_TYPES[c.type]; })
    .map(function (c) { return fill(c, CONDITION_TYPES[c.type]); });
  return cfg;
}
var _eid = 1;
function newEffect(prim, action) {
  return normalize({id: "E" + Date.now().toString(36) + (_eid++), name: prim, action: action || "idle",
    prim: prim, enabled: true});
}
function fill(dst, def) { for (var k in def) if (dst[k] === undefined) dst[k] = JSON.parse(JSON.stringify(def[k])); return dst; }
// Fill every missing field with its default so exported files are explicit.
function normalize(fx) {
  if (PRIMS.indexOf(fx.prim) < 0) fx.prim = "glow";
  fill(fx, {name: fx.prim, tag: "", enabled: true, start_frame: 0, end_frame: -1, life_ticks: 0,
    anchor: "figure", offset: [0, 0], layer: "front", blend: "normal"});
  fx.emit = fill(fx.emit || {}, {every_ticks: 0, count: 1, fan_deg: 0});
  fx.motion = fill(fx.motion || {}, MOTION_DEFAULTS);
  fx.color = fill(fx.color || {}, COLOR_DEFAULTS);
  fx.params = fill(fx.params || {}, PARAM_DEFAULTS[fx.prim]);
  fx.battle = fill(fx.battle || {}, BATTLE_DEFAULTS);
  if (fx.prim === "ghost") fx.battle.deals_damage = false;   // afterimages are visual only
  if (fx.prim === "weapon") fx.motion.kind = "attached";      // a hitbox rides its anchors
  return fx;
}

// ---------------------------------------------------------------- instances
// host (supplied by the Studio now, by laser/fxkit.py's caller in Phase 2):
//   host.anchor(name) -> [x, y] game px, facing already applied
//   host.facing       -> 1 (right) or -1 (left)
//   host.target       -> [x, y]
//   host.wang         -> weapon world angle (deg, rig convention, unmirrored)
//   host.snapshot()   -> opaque figure frame for ghosts
//   host.lut          -> 256-entry palette LUT
function aimDir(fx, host, x, y) {
  var m = fx.motion, f = host.facing, dx, dy;
  if (m.aim === "target") { var d = norm(host.target[0] - x, host.target[1] - y); dx = d[0]; dy = d[1]; }
  else if (m.aim === "angle") { dx = Math.cos(m.angle_deg * D) * f; dy = Math.sin(m.angle_deg * D); }
  else if (m.aim === "weapon") { dx = Math.sin(host.wang * D) * f; dy = -Math.cos(host.wang * D); }
  else { dx = f; dy = 0; }
  return [dx, dy];
}
function rot(v, deg) { var c = Math.cos(deg * D), s = Math.sin(deg * D); return [v[0] * c - v[1] * s, v[0] * s + v[1] * c]; }
function anchorPos(fx, host) {
  var a = host.anchor(fx.anchor);
  return [a[0] + (+fx.offset[0] || 0) * host.facing, a[1] + (+fx.offset[1] || 0)];
}

function spawn(fx, host, windowTicks, seed, idx, n) {
  var p = anchorPos(fx, host), m = fx.motion;
  var dir = aimDir(fx, host, p[0], p[1]);
  if (n > 1 && fx.emit.fan_deg) dir = rot(dir, (-fx.emit.fan_deg / 2 + fx.emit.fan_deg * idx / (n - 1)) * host.facing);
  if (m.aim_offset_deg) dir = rot(dir, m.aim_offset_deg * host.facing);
  var life = fx.life_ticks > 0 ? fx.life_ticks : Math.max(1, windowTicks);
  var inst = {fx: fx, x: p[0], y: p[1], px: p[0], py: p[1], vx: 0, vy: 0, dir: dir, age: 0, life: life,
    seed: seed >>> 0, r: rng(seed), flow: 0, ended: false, dead: false, hist: [], trail: [], parts: [],
    ghosts: [], acc: 0, facing: host.facing, orbitA: 0, phase: 0, zx: 0, zy: 0,
    hits: 0, lastHit: -1e9};
  var spd = +m.speed || 0;
  if (m.kind === "travel" || m.kind === "homing" || m.kind === "zigzag") { inst.vx = dir[0] * spd; inst.vy = dir[1] * spd; }
  if (m.kind === "zigzag") {   // ZigzagProjectile.__init__
    var pr = spd > 0.001 ? [-inst.vy / spd, inst.vx / spd] : [0, 1];
    inst.zx = pr[0] * m.amplitude; inst.zy = pr[1] * m.amplitude;
    inst.phase = n > 1 ? Math.PI * idx : 0;
  }
  if (m.kind === "orbit") {
    inst.orbitA = 360 * idx / Math.max(1, n);
    var c = p; inst.x = c[0] + Math.cos(inst.orbitA * D) * m.orbit_rx; inst.y = c[1] + Math.sin(inst.orbitA * D) * m.orbit_ry;
  }
  if (fx.prim === "arc") {
    // CrescentWave: centre angle perpendicular to the direction of travel.
    var od = fx.params.orient === "angle" ? [Math.cos(fx.params.angle_deg * D) * host.facing, Math.sin(fx.params.angle_deg * D)] : dir;
    inst.centreDeg = angleDegQt(-od[1], od[0]);
    // CrescentWave.__init__ placements relative to the target (the aim
    // direction runs from the anchor to the target):
    //   wrap_target    centre = target - dir * back           (default slash, back 51)
    //   through_target centre = target + R*(dir_y, -dir_x) - dir * lead
    //                  so the arc's midpoint starts `lead` short of the target
    var tg = host.target, P = fx.params;
    if (P.placement === "wrap_target") { inst.x = tg[0] - od[0] * P.back; inst.y = tg[1] - od[1] * P.back; }
    else if (P.placement === "through_target") {
      var R = P.radius;
      inst.x = tg[0] + od[1] * R - od[0] * P.lead; inst.y = tg[1] - od[0] * R - od[1] * P.lead;
    }
  }
  if (fx.prim === "particles" && fx.params.mode === "burst") emitParticles(inst, fx, host, trunc(fx.params.count));
  if (fx.prim === "weapon") { var e2 = host.anchor(fx.params.to_anchor); inst.x2 = e2[0]; inst.y2 = e2[1]; }
  inst.px = inst.x; inst.py = inst.y;
  return inst;
}

function moveInst(inst, host) {
  var fx = inst.fx, m = fx.motion;
  inst.px = inst.x; inst.py = inst.y;
  if (m.kind === "attached") { var a = anchorPos(fx, host); inst.x = a[0]; inst.y = a[1]; }
  if (fx.prim === "weapon") { var b2 = host.anchor(fx.params.to_anchor); inst.x2 = b2[0]; inst.y2 = b2[1]; }
  else if (m.kind === "travel") { inst.x += inst.vx; inst.y += inst.vy; }
  else if (m.kind === "homing") {
    var spd = Math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy) || (+m.speed || 0);
    var want = Math.atan2(host.target[1] - inst.y, host.target[0] - inst.x);
    var cur = Math.atan2(inst.vy, inst.vx), dA = want - cur;
    while (dA > Math.PI) dA -= 2 * Math.PI;
    while (dA < -Math.PI) dA += 2 * Math.PI;
    var lim = (+m.turn_deg || 0) * D;
    cur += Math.max(-lim, Math.min(lim, dA));
    inst.vx = Math.cos(cur) * spd; inst.vy = Math.sin(cur) * spd;
    inst.x += inst.vx; inst.y += inst.vy;
  } else if (m.kind === "zigzag") {   // ZigzagProjectile.update (sf = 1)
    var lat = Math.sin(inst.phase) * m.freq;
    inst.x += inst.vx + inst.zx * lat; inst.y += inst.vy + inst.zy * lat;
    inst.phase += m.freq;
  } else if (m.kind === "orbit") {
    var c = anchorPos(fx, host);
    inst.orbitA += m.orbit_deg;
    inst.x = c[0] + Math.cos(inst.orbitA * D) * m.orbit_rx; inst.y = c[1] + Math.sin(inst.orbitA * D) * m.orbit_ry;
  }
  if (m.kind === "travel" || m.kind === "homing" || m.kind === "zigzag") {
    var mdx = inst.x - inst.px, mdy = inst.y - inst.py;
    if (mdx * mdx + mdy * mdy > 1e-6) inst.dir = norm(mdx, mdy);
  } else if (fx.prim === "beam") {
    // A held beam keeps re-aiming (at the target, the facing, the fixed
    // angle or the weapon) while its anchor moves.
    var d = aimDir(fx, host, inst.x, inst.y);
    inst.dir = m.aim_offset_deg ? rot(d, m.aim_offset_deg * host.facing) : d;
  }
}

function emitParticles(inst, fx, host, n) {
  // combat._spawn_burst_now: fan around angle_deg, mirrored with facing.
  var P = fx.params, cp = colorPair(fx, host.lut);
  var spread = P.spread_deg * D, base = P.angle_deg * D;
  if (inst.facing < 0) base = Math.PI - base;
  var smin = +P.speed_min, smax = Math.max(smin, +P.speed_max);
  var s0 = Math.max(0.5, +P.size_min), s1 = Math.max(s0, +P.size_max);
  var l0 = Math.max(1, +P.life_min_ms), l1 = Math.max(l0, +P.life_max_ms);
  for (var i = 0; i < n; i++) {
    var a = base + inst.r.uniform(-spread / 2, spread / 2);
    var spd = smax > smin ? inst.r.uniform(smin, smax) : smin;
    var lifeMs = inst.r.uniform(l0, l1);
    inst.parts.push({x: inst.x, y: inst.y, vx: Math.cos(a) * spd, vy: Math.sin(a) * spd, age: 0,
      life: Math.max(1, trunc(lifeMs / TICK_MS)), s0: s0, s1: s1, rgb1: cp[0], rgb2: cp[1], hits: 0, lastHit: -1e9});
  }
}

function tickInst(inst, host) {
  var fx = inst.fx, P = fx.params;
  var active = inst.age < inst.life;
  if (active) {
    if (fx.prim === "sprite" || fx.prim === "beam") { inst.trail.push([inst.x, inst.y]); if (inst.trail.length > Math.max(0, trunc(P.trail_len || 0))) inst.trail.shift(); }
    moveInst(inst, host);
  }
  inst.flow = (inst.flow + (+fx.color.flow_speed || 0)) % 1;
  if (fx.prim === "ribbon") {   // TrailComponent.update (path_follow = False)
    var h = inst.hist;
    if (active) {
      var moved = true;
      if (h.length) { var l = h[h.length - 1], dx = inst.x - l[0], dy = inst.y - l[1]; moved = dx * dx + dy * dy >= P.min_dist * P.min_dist; }
      if (moved) { h.push([inst.x, inst.y]); while (h.length > P.max_points) h.shift(); }
      var mx = inst.x - inst.px, my = inst.y - inst.py;
      if (mx * mx + my * my < 0.01) for (var d = 0; d < P.decay; d++) if (h.length > 1) h.shift();
    } else {
      for (var e = 0; e < Math.max(1, P.decay); e++) if (h.length) h.shift();
    }
    if (!active && h.length <= 1) inst.dead = true;
  } else if (fx.prim === "particles") {
    if (active && P.mode === "stream") {
      inst.acc += P.rate_per_s * TICK_S;
      var k = trunc(inst.acc); if (k > 0) { inst.acc -= k; emitParticles(inst, fx, host, k); }
    }
    inst.parts.forEach(function (q) {   // BurstParticle.update (sf = 1)
      var drag = +P.drag;
      q.vx *= drag; q.vy = q.vy * drag + P.gravity * TICK_S;
      q.x += q.vx * TICK_S; q.y += q.vy * TICK_S; q.age += 1;
    });
    inst.parts = inst.parts.filter(function (q) { return q.age < q.life; });
    if (!active && !inst.parts.length) inst.dead = true;
  } else if (fx.prim === "ghost") {
    if (active && inst.age % Math.max(1, trunc(P.interval)) === 0 && inst.ghosts.length < P.max)
      inst.ghosts.push({snap: host.snapshot(), x: inst.x, y: inst.y, facing: host.facing, age: 0});
    inst.ghosts.forEach(function (g) { g.age += 1; });
    inst.ghosts = inst.ghosts.filter(function (g) { return g.age < P.ghost_life; });
    if (!active && !inst.ghosts.length) inst.dead = true;
  } else if (!active) {
    inst.dead = true;
  }
  inst.age += 1;
}

// ---------------------------------------------------------------- drawing
function line(g, x0, y0, x1, y1) { g.beginPath(); g.moveTo(trunc(x0), trunc(y0)); g.lineTo(trunc(x1), trunc(y1)); g.stroke(); }

var DRAW = {};
DRAW.ribbon = function (g, inst, host, ps) {   // TrailComponent.draw
  var fx = inst.fx, P = fx.params, tl = inst.hist, n = tl.length;
  if (n <= 1) return;
  var inv = 1 / n;
  g.lineCap = "round";
  for (var i = 1; i < n; i++) {
    var t = i * inv, c = colorAt(fx, inst, t, host.lut);
    if (P.taper) { g.strokeStyle = rgba(c, P.alpha * t); g.lineWidth = (P.w_tail + (P.w_head - P.w_tail) * t) * ps; }
    else { g.strokeStyle = rgba(c, P.alpha); g.lineWidth = P.w_head * ps; }
    line(g, tl[i - 1][0], tl[i - 1][1], tl[i][0], tl[i][1]);
  }
  var hx = trunc(tl[n - 1][0]), hy = trunc(tl[n - 1][1]), hc = colorAt(fx, inst, 1, host.lut).map(trunc);
  var gr = P.head_glow_r * ps, igr = trunc(gr);
  if (igr > 0) {
    g.fillStyle = radial(g, hx, hy, gr, [[0, rgba(hc, 140)], [0.4, rgba(hc, 60)], [1, rgba(hc, 0)]]);
    ellipse(g, hx - igr, hy - igr, igr * 2, igr * 2);
  }
  var dr = P.head_dot_r * ps, idr = trunc(dr);
  if (idr > 0) {
    g.fillStyle = radial(g, hx, hy, dr, [[0, "rgba(255,255,255," + 200 / 255 + ")"], [0.5, rgba(hc, 180)], [1, rgba(hc, 100)]]);
    ellipse(g, hx - idr, hy - idr, idr * 2, idr * 2);
  }
};
// Visible arc segments [a0_deg, step_deg, width, tail_t, alpha] (Qt angles).
function arcSegs(inst, ps) {   // CrescentWave.draw visibility rules
  var P = inst.fx.params, life = inst.life, age = inst.age, out = [];
  if (age >= life) return out;
  var segs = trunc(P.segs), half = P.span / 2, start = inst.centreDeg - half, step = P.span / segs;
  var halfLife = life * P.grow, tip, fade;
  if (age <= halfLife) { tip = age / halfLife; fade = 1; }
  else { tip = 1; fade = 1 - (age - halfLife) / (life - halfLife); }
  for (var i = 0; i < segs; i++) {
    var st = (i + 0.5) / segs;
    if (st > tip) continue;
    var dft = tip - st;
    if (dft > P.tail) continue;
    var tt = 1 - dft / P.tail, a = trunc(255 * Math.pow(tt, 0.6) * fade);
    if (a < 4) continue;
    out.push([start + i * step, step, P.width * (0.25 + 0.75 * tt) * ps, tt, a, st]);
  }
  return out;
}
DRAW.arc = function (g, inst, host, ps) {   // CrescentWave.draw
  var fx = inst.fx, P = fx.params, r2 = P.radius * ps;
  g.lineCap = "round"; g.lineJoin = "round";
  arcSegs(inst, ps).forEach(function (q) {
    var a0 = q[0], step = q[1], a = q[4];
    var c = fx.color.mode === "palette" ? colorAt(fx, inst, q[5], host.lut) : colorPair(fx, host.lut)[0];
    // Qt arc angles run CCW with y up; canvas angles run CW with y down.
    var path = function () { g.beginPath(); g.arc(inst.x, inst.y, r2, -a0 * D, -(a0 + step) * D, true); g.stroke(); };
    g.strokeStyle = rgba(c, a); g.lineWidth = q[2]; path();
    g.strokeStyle = "rgba(255,255,255," + trunc(a * P.core_alpha) / 255 + ")";
    g.lineWidth = P.width * P.core_width * (0.25 + 0.75 * q[3]) * ps; path();
  });
};
// Beam geometry shared by draw and hit test: [[x0,y0,x1,y1,width,rgb], ...]
// plus the alpha multiplier; null when nothing is visible.
function beamSegs(inst, host, ps) {   // RichBeamProjectile.draw geometry
  var fx = inst.fx, P = fx.params, m = fx.motion;
  var fade = Math.max(0, 1 - inst.age / inst.life);
  if (fade <= 0) return null;
  var ux = inst.dir[0], uy = inst.dir[1], reach, hx = inst.x, hy = inst.y;
  var spd = Math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy);
  var detach = P.detach_ticks > 0 ? P.detach_ticks : 1e9;
  if (m.kind === "attached" || m.kind === "static" || m.kind === "orbit" || spd < 0.0001) {
    // FX Kit extension: a beam held at its anchor, extending along the aim
    // over grow_ticks (0 = full length at once).
    reach = P.length * (P.grow_ticks > 0 ? Math.min(1, inst.age / P.grow_ticks) : 1);
    hx = inst.x + ux * reach; hy = inst.y + uy * reach;
  } else {
    var dist = spd * inst.age;
    if (inst.age < detach) reach = Math.min(P.length, dist);
    else {
      var rd = Math.min(P.length, spd * detach), post = Math.max(1, inst.life - detach);
      reach = Math.max(0, rd * (1 - Math.min(1, (inst.age - detach) / post)));
    }
  }
  if (reach <= 0) return null;
  var prog = Math.min(1, inst.age / Math.max(1, inst.life));
  var wT = P.w_start0 + (P.w_start1 - P.w_start0) * prog, wH = P.w_end0 + (P.w_end1 - P.w_end0) * prog;
  var pulse = 1;
  if (P.pulse_hz > 0) pulse = 0.65 + 0.35 * Math.sin(2 * Math.PI * P.pulse_hz * (inst.age * TICK_MS / 1000));
  var cp = colorPair(fx, host.lut), c1 = cp[0], c2 = cp[1];
  var segs = Math.max(1, trunc(P.segments)), jr = rng(inst.seed + trunc(inst.age)), out = [];
  for (var i = 0; i < segs; i++) {
    var t0 = i / segs, t1 = (i + 1) / segs;
    var x0 = hx - ux * reach * t0, y0 = hy - uy * reach * t0, x1 = hx - ux * reach * t1, y1 = hy - uy * reach * t1;
    if (P.jitter > 0) { var j = (jr() * 2 - 1) * P.jitter; x0 += -uy * j; y0 += ux * j; x1 += -uy * j; y1 += ux * j; }
    out.push([x0, y0, x1, y1, (wH + (wT - wH) * t0) * ps,
      [c2[0] + (c1[0] - c2[0]) * t0, c2[1] + (c1[1] - c2[1]) * t0, c2[2] + (c1[2] - c2[2]) * t0]]);
  }
  return {segs: out, am: fade * pulse};
}
DRAW.beam = function (g, inst, host, ps) {   // RichBeamProjectile.draw
  var P = inst.fx.params, b = beamSegs(inst, host, ps);
  if (!b) return;
  var gc = P.glow_color ? hexRgb(P.glow_color, null) : null;
  g.lineCap = "round";
  b.segs.forEach(function (q) {
    var w = q[4], col = q[5];
    if (P.glow > 0) { g.strokeStyle = rgba(gc || col.map(trunc), 70 * b.am); g.lineWidth = w + P.glow * ps; line(g, q[0], q[1], q[2], q[3]); }
    g.strokeStyle = rgba(col, 235 * b.am); g.lineWidth = Math.max(1, w); line(g, q[0], q[1], q[2], q[3]);
  });
};
DRAW.sprite = function (g, inst, host, ps) {   // Projectile.draw
  var fx = inst.fx, P = fx.params, fade = P.fade ? Math.max(0, 1 - inst.age / inst.life) : 1;
  if (inst.age >= inst.life) return;
  var c = colorPair(fx, host.lut)[0].map(trunc), hx = trunc(inst.x), hy = trunc(inst.y);
  var pts = inst.trail, n = pts.length;
  g.lineCap = "round";
  for (var i = 1; i < n; i++) {
    var t = i / n;
    g.strokeStyle = rgba(c, 200 * t * fade); g.lineWidth = (1 + 2 * t) * ps;
    line(g, pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]);
  }
  var spd2 = inst.vx * inst.vx + inst.vy * inst.vy;
  g.save(); g.translate(hx, hy);
  if (P.shape === "bolt" && spd2 > 0.0001 && P.stretch > 1.001) {
    var b = boltSprite(c[0], c[1], c[2], P.radius, P.stretch, !!P.hot);
    g.rotate(Math.atan2(inst.vy, inst.vx)); g.scale(ps, ps); g.globalAlpha *= fade;
    g.drawImage(b.cv, trunc(-b.headX), trunc(-b.halfH));
  } else if (P.shape === "bolt") {
    var o = boltSprite(c[0], c[1], c[2], P.radius, 1, !!P.hot);
    g.scale(ps, ps); g.globalAlpha *= fade;
    g.drawImage(o.cv, -trunc(o.cv.width / 2), -trunc(o.cv.height / 2));
  } else {
    var s = bulletSprite(c[0], c[1], c[2], P.radius);
    g.scale(ps, ps); g.globalAlpha *= fade;
    g.drawImage(s.cv, -s.half, -s.half);
  }
  g.restore();
  if (P.halo) {   // homing flair: pulsing ring
    var ha = trunc((110 + 70 * Math.sin(inst.age * 0.5)) * fade);
    if (ha > 4) { var ihr = trunc(P.radius * 3.6 * ps); g.strokeStyle = rgba(c, ha); g.lineWidth = 1.4;
      g.beginPath(); g.ellipse(hx, hy, ihr, ihr, 0, 0, 6.2832); g.stroke(); }
  }
};
DRAW.particles = function (g, inst, host, ps) {   // BurstParticle.draw
  var P = inst.fx.params;
  inst.parts.forEach(function (q) {
    var t = Math.min(1, q.age / q.life), s0 = q.s0, s1 = q.s1, size;
    if (P.size_over_life === "shrink") size = s1 + (s0 - s1) * (1 - t);
    else if (P.size_over_life === "grow") size = s0 + (s1 - s0) * t;
    else if (P.size_over_life === "pulse") size = s0 + (s1 - s0) * Math.sin(Math.min(1, t) * Math.PI);
    else size = s0;
    size = Math.max(0.5, size);
    var cl = function (v) { return Math.max(0, Math.min(255, v)); };
    var r = cl(trunc(q.rgb1[0] + (q.rgb2[0] - q.rgb1[0]) * t)), gg = cl(trunc(q.rgb1[1] + (q.rgb2[1] - q.rgb1[1]) * t)),
        b = cl(trunc(q.rgb1[2] + (q.rgb2[2] - q.rgb1[2]) * t));
    var s = bulletSprite(r, gg, b, size / 2);
    g.save(); g.translate(trunc(q.x), trunc(q.y)); g.scale(ps, ps);
    g.globalAlpha *= Math.max(0, 1 - t); g.drawImage(s.cv, -s.half, -s.half); g.restore();
  });
};
DRAW.glow = function (g, inst, host, ps) {   // TrailComponent head glow + core, as a standalone sphere
  var fx = inst.fx, P = fx.params;
  if (inst.age >= inst.life) return;
  var t = Math.min(1, inst.age / inst.life), c = colorPair(fx, host.lut)[0].map(trunc);
  var k = P.fade === "out" ? 1 - t : P.fade === "in" ? t : P.fade === "inout" ? Math.sin(t * Math.PI) : 1;
  if (P.pulse_hz > 0) k *= 0.65 + 0.35 * Math.sin(2 * Math.PI * P.pulse_hz * (inst.age * TICK_MS / 1000));
  var hx = trunc(inst.x), hy = trunc(inst.y);
  var gr = (P.r_start + (P.r_end - P.r_start) * t) * ps, igr = trunc(gr);
  if (igr > 0) {
    g.fillStyle = radial(g, hx, hy, gr, [[0, rgba(c, P.a_center * k)], [P.mid, rgba(c, P.a_mid * k)], [1, rgba(c, 0)]]);
    ellipse(g, hx - igr, hy - igr, igr * 2, igr * 2);
  }
  var dr = P.core_r * ps, idr = trunc(dr);
  if (idr > 0) {
    g.fillStyle = radial(g, hx, hy, dr, [[0, "rgba(255,255,255," + 200 * k / 255 + ")"], [0.5, rgba(c, 180 * k)], [1, rgba(c, 100 * k)]]);
    ellipse(g, hx - idr, hy - idr, idr * 2, idr * 2);
  }
};
DRAW.weapon = function (g, inst, host, ps) {   // invisible in-game; the Studio outlines it
  if (!host.showHitboxes || inst.age >= inst.life) return;
  g.strokeStyle = inst.fx.battle.deals_damage ? "rgba(255,90,90,.85)" : "rgba(150,160,180,.7)";
  g.lineWidth = Math.max(1, inst.fx.params.width * ps); g.lineCap = "round"; g.setLineDash([4, 3]);
  g.beginPath(); g.moveTo(inst.x, inst.y); g.lineTo(inst.x2, inst.y2); g.stroke(); g.setLineDash([]);
};
DRAW.ghost = function (g, inst, host, ps) {   // Figure.draw afterimages
  var P = inst.fx.params, c = colorPair(inst.fx, host.lut)[0].map(trunc);
  inst.ghosts.forEach(function (gh) {
    var a = P.alpha * (1 - gh.age / P.ghost_life);
    if (a > 1) host.drawGhost(g, gh, c, a / 255);
  });
};

// ---------------------------------------------------------------- damage
// Distance from point (px,py) to segment (x0,y0)-(x1,y1).
function segDist(px, py, x0, y0, x1, y1) {
  var dx = x1 - x0, dy = y1 - y0, L = dx * dx + dy * dy, t = L > 0 ? ((px - x0) * dx + (py - y0) * dy) / L : 0;
  t = Math.max(0, Math.min(1, t));
  var ex = x0 + dx * t - px, ey = y0 + dy * t - py;
  return Math.sqrt(ex * ex + ey * ey);
}
// Does the shape this instance currently DRAWS touch a hurt circle
// (tx, ty, hr)?  Line shapes count their half stroke width; sprites use the
// engine's point-vs-hurt-radius rule (Projectile hit_r_sq).
var HIT = {};
HIT.ribbon = function (inst, tx, ty, hr, ps) {
  var P = inst.fx.params, h = inst.hist, n = h.length;
  for (var i = 1; i < n; i++) {
    var t = i / n, w = (P.taper ? P.w_tail + (P.w_head - P.w_tail) * t : P.w_head) * ps;
    if (segDist(tx, ty, h[i - 1][0], h[i - 1][1], h[i][0], h[i][1]) <= hr + w / 2) return true;
  }
  return false;
};
HIT.arc = function (inst, tx, ty, hr, ps) {
  var r2 = inst.fx.params.radius * ps, segs = arcSegs(inst, ps);
  for (var i = 0; i < segs.length; i++) {
    var q = segs[i], a0 = q[0] * D, a1 = (q[0] + q[1]) * D;   // Qt: (cx + R cos a, cy - R sin a)
    if (segDist(tx, ty, inst.x + r2 * Math.cos(a0), inst.y - r2 * Math.sin(a0),
                inst.x + r2 * Math.cos(a1), inst.y - r2 * Math.sin(a1)) <= hr + q[2] / 2) return true;
  }
  return false;
};
HIT.beam = function (inst, tx, ty, hr, ps, host) {
  var b = beamSegs(inst, host, ps);
  if (!b) return false;
  for (var i = 0; i < b.segs.length; i++) { var q = b.segs[i]; if (segDist(tx, ty, q[0], q[1], q[2], q[3]) <= hr + Math.max(1, q[4]) / 2) return true; }
  return false;
};
HIT.sprite = function (inst, tx, ty, hr) {
  if (inst.age >= inst.life) return false;
  var dx = inst.x - tx, dy = inst.y - ty;
  return dx * dx + dy * dy <= hr * hr;
};
HIT.glow = function (inst, tx, ty, hr, ps) {
  var P = inst.fx.params;
  if (inst.age >= inst.life) return false;
  var t = Math.min(1, inst.age / inst.life), gr = Math.max(P.core_r, P.r_start + (P.r_end - P.r_start) * t) * ps;
  var dx = inst.x - tx, dy = inst.y - ty;
  return Math.sqrt(dx * dx + dy * dy) <= hr + gr;
};
HIT.ghost = function () { return false; };
HIT.weapon = function (inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  return segDist(tx, ty, inst.x, inst.y, inst.x2, inst.y2) <= hr + inst.fx.params.width * ps / 2;
};
function canHit(b, obj, now) { return b.rehit_ticks > 0 ? now - obj.lastHit >= b.rehit_ticks : obj.hits === 0; }
// Resolve this tick's hits against host.hurt = {x, y, r}.  host.onHit(inst,
// damage, dirX, dirY, knockback) is called once per hit (the engine routes it
// to ai.apply_hp_damage + the knockback channel).  A non-piercing hit ends
// the instance (a hit particle is removed instead).
function resolveHits(inst, host, ps) {
  var b = inst.fx.battle, hurt = host.hurt;
  if (!b.deals_damage || !hurt || inst.dead) return;
  var now = inst.age;
  if (inst.fx.prim === "particles") {
    inst.parts = inst.parts.filter(function (q) {
      var size = Math.max(0.5, q.s0), dx = q.x - hurt.x, dy = q.y - hurt.y;
      if (Math.sqrt(dx * dx + dy * dy) > hurt.r + size / 2 || !canHit(b, q, now)) return true;
      q.hits += 1; q.lastHit = now;
      var d = norm(q.vx, q.vy);
      if (host.onHit) host.onHit(inst, b.damage, d[0], d[1], b.knockback);
      return !!b.pierce;
    });
    return;
  }
  if (!canHit(b, inst, now) || !HIT[inst.fx.prim](inst, hurt.x, hurt.y, hurt.r, ps, host)) return;
  inst.hits += 1; inst.lastHit = now;
  if (host.onHit) host.onHit(inst, b.damage, inst.dir[0], inst.dir[1], b.knockback);
  if (!b.pierce) inst.age = Math.max(inst.age, inst.life);
}

function drawInst(g, inst, host, ps) {
  var add = inst.fx.blend === "additive";
  g.save();
  if (add) g.globalCompositeOperation = "lighter";
  DRAW[inst.fx.prim](g, inst, host, ps || 1);
  g.restore();
}

// ---------------------------------------------------------------- player
// Plays every effect bound to one action, in lock-step with the action's
// frames.  frameMs = duration_ms / frame count (the engine plays Rig Forge
// keyframes at exactly this rate).
function Player() { this.insts = []; this.t = 0; }
Player.prototype.reset = function () { this.insts = []; this.t = 0; };
Player.prototype.window = function (fx, frames, frameMs) {
  var total = Math.max(1, Math.round(frames * frameMs / TICK_MS));
  var s = Math.round(Math.max(0, fx.start_frame) * frameMs / TICK_MS);
  var e = fx.end_frame < 0 ? total : Math.round((Math.min(frames - 1, fx.end_frame) + 1) * frameMs / TICK_MS);
  return [Math.min(s, total - 1), Math.max(s + 1, e), total];
};
// Advance one tick.  `t` counts ticks since the action started (it wraps
// when the action loops; instances already alive keep running).
Player.prototype.tick = function (effects, host, t, frames, frameMs) {
  var self = this;
  effects.forEach(function (fx) {
    if (!fx.enabled) return;
    var w = self.window(fx, frames, frameMs), s = w[0], e = w[1];
    var fire = t === s || (fx.emit.every_ticks > 0 && t > s && t < e && (t - s) % fx.emit.every_ticks === 0);
    if (!fire) return;
    var n = Math.max(1, trunc(fx.emit.count)), win = e - t;
    for (var i = 0; i < n; i++)
      self.insts.push(spawn(fx, host, win, (hash32(fx.id) ^ Math.imul(t + 1, 0x9E3779B1) ^ (i * 0x85EBCA6B)) >>> 0, i, n));
  });
  var ps = host.pscale || 1;
  this.insts.forEach(function (inst) { tickInst(inst, host); resolveHits(inst, host, ps); });
  this.insts = this.insts.filter(function (i) { return !i.dead; });
};
Player.prototype.draw = function (g, host, layer, ps) {
  this.insts.forEach(function (inst) { if (inst.fx.layer === layer) drawInst(g, inst, host, ps); });
};

G.FXK = {TICK_MS: TICK_MS, rng: rng, hash32: hash32, buildLut: buildLut, hexRgb: hexRgb,
  PRIMS: PRIMS, MOTIONS: MOTIONS, AIMS: AIMS, PARAM_DEFAULTS: PARAM_DEFAULTS,
  MOTION_DEFAULTS: MOTION_DEFAULTS, COLOR_DEFAULTS: COLOR_DEFAULTS, BATTLE_DEFAULTS: BATTLE_DEFAULTS,
  newEffect: newEffect, normalize: normalize, CONDITION_TYPES: CONDITION_TYPES, ACTION_DEFAULTS: ACTION_DEFAULTS,
  actionKind: actionKind, normalizeAction: normalizeAction, Player: Player, bulletSprite: bulletSprite};
})(window);
