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
var MOTIONS = ["attached", "static", "travel", "homing", "zigzag", "orbit", "path"];
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
  turn_deg: 6, amplitude: 55, freq: 0.18, orbit_rx: 46, orbit_ry: 46, orbit_deg: 1.12, path: ""};
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
// fx_continuous: when the action loops (idle, run, a held action), effects
// that last to the end of the action keep running across the loop instead
// of ending and starting again.
// movement: "stand" = the fighter stays in place while the action plays;
// "move" = it keeps moving (at move_speed_pct % of its normal speed);
// "back" = it retreats straight away from the target at move_speed_pct % of
// its normal speed until back_stop_pct % of the whole action, then holds.  Only
// for attack / triggered actions; idle always stands and run always moves.
// anim_loops: how many times the animation plays before the action ends
// (attack / triggered actions; idle and run loop for as long as they last).
// Each pass is a normal animation loop for the FX: they carry on exactly as
// they do when an animation loops (fx_continuous and ∞ effects included).
var ACTION_DEFAULTS = {logic: "any", cooldown_ms: 0, conditions: [], chain_next: "", chain_reset_ms: 1000, fx_continuous: false,
  movement: "stand", move_speed_pct: 100, anim_loops: 1, back_stop_pct: 80};
// Character-level aiming (pack.aim): the fighter always faces the target and
// the whole frame on show turns so its barrel (from -> to anchor of that
// frame; the source action's average when the frame has none) points at the
// target, at most max_deg either way.  Same maths as laser/fxkit.py aim_angle.
var AIM_DEFAULTS = {enabled: false, source: "attack_normal", from_anchor: "haR", to_anchor: "wtip", max_deg: 75};
function normalizeAim(a) { return fill(a || {}, AIM_DEFAULTS); }
// ref = {dir: [x, y] unit, from: [x, y]} fallback barrel (image px, right facing);
// pa / pb = this frame's from / to anchors (image px) or null; origin, k =
// image origin and game px per image px (incl. position scale); fig, target
// = game positions.  Returns degrees (0 when the barrel is unknown).
function aimAngle(aim, pa, pb, ref, origin, k, facing, fig, target) {
  var dir, start;
  if (pa && pb && Math.hypot(pb[0] - pa[0], pb[1] - pa[1]) > 1e-6) { var d = Math.hypot(pb[0] - pa[0], pb[1] - pa[1]); dir = [(pb[0] - pa[0]) / d, (pb[1] - pa[1]) / d]; start = pa; }
  else if (ref) { dir = ref.dir; start = ref.from; }
  else return 0;
  var rx = dir[0] * facing, ry = dir[1], ox = (start[0] - origin[0]) * k * facing, oy = (start[1] - origin[1]) * k;
  var base = Math.atan2(ry, rx), lim = Math.max(0, Math.min(180, +aim.max_deg || 0)) * Math.PI / 180, a = 0;
  for (var i = 0; i < 4; i++) {
    var ca = Math.cos(a), sa = Math.sin(a), px = fig[0] + ox * ca - oy * sa, py = fig[1] + ox * sa + oy * ca;
    if ((target[0] - px) * (target[0] - px) + (target[1] - py) * (target[1] - py) < 4) break;
    a = Math.atan2(target[1] - py, target[0] - px) - base;
    a = ((a + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
    a = Math.max(-lim, Math.min(lim, a));
  }
  return a * 180 / Math.PI;
}
function animLoops(name, cfg) {
  if (actionKind(name) === "locomotion") return 1;
  return Math.max(1, Math.round(+(cfg || ACTION_DEFAULTS).anim_loops || 1));
}
function actionKind(name) {
  if (name === "idle" || name === "run") return "locomotion";
  if (/^attack_normal/.test(name)) return "attack";
  return "triggered";
}
// Fraction of normal movement speed the fighter keeps while this action plays.
function moveFactor(name, cfg) {
  var k = actionKind(name);
  if (k === "locomotion") return name === "idle" ? 0 : 1;
  cfg = cfg || ACTION_DEFAULTS;
  return cfg.movement === "move" || cfg.movement === "back" ? Math.max(0, +cfg.move_speed_pct || 0) / 100 : 0;
}
// ---------------------------------------------------------------- character scale
// Image characters stand STAND_HEIGHT_PX tall in game (laser/config.py
// IMAGE_STAND_HEIGHT_PX, the roster's height), measured on the first idle
// frame.  An FX file records the scale it was authored at
// (space.game_px_per_image_px); a file authored at another scale has every
// distance multiplied by the ratio (laser/fxkit.py rescale_effects).
var STAND_HEIGHT_PX = 28;
var SCALE_PARAMS = {ribbon: ["min_dist", "w_tail", "w_head", "head_glow_r", "head_dot_r"], arc: ["radius", "width", "back", "lead"],
  beam: ["length", "w_start0", "w_start1", "w_end0", "w_end1", "glow", "jitter"], sprite: ["radius"],
  particles: ["speed_min", "speed_max", "gravity", "size_min", "size_max"], glow: ["r_start", "r_end", "core_r"], ghost: [], weapon: ["width"]};
var SCALE_MOTION = ["speed", "amplitude", "orbit_rx", "orbit_ry"];
function rescaleEffects(effects, lib, r) {
  if (Math.abs(r - 1) < 1e-6) return;
  effects.forEach(function (fx) {
    var off = fx.offset || [0, 0]; fx.offset = [(+off[0] || 0) * r, (+off[1] || 0) * r];
    var m = fx.motion || {}; SCALE_MOTION.forEach(function (k) { if (typeof m[k] === "number") m[k] *= r; });
    var P = fx.params || {}; (SCALE_PARAMS[fx.prim] || []).forEach(function (k) { if (typeof P[k] === "number") P[k] *= r; });
  });
  ((lib && lib.entry_sets) || []).forEach(function (e) { e.points = (e.points || []).map(function (p) { return [p[0] * r, p[1] * r]; }); });
  ((lib && lib.paths) || []).forEach(function (p) { p.points = (p.points || []).map(function (q) { return [q[0] * r, q[1] * r]; }); });
}
// Visible height (alpha > 40) of an <img>, in image px (characters.py stand_height_px).
function standHeight(img) {
  var w = img.naturalWidth, h = img.naturalHeight;
  if (!w || !h) return 0;
  var c = document.createElement("canvas"); c.width = w; c.height = h;
  var g = c.getContext("2d"); g.drawImage(img, 0, 0);
  var d = g.getImageData(0, 0, w, h).data, top = -1, bot = -1;
  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) if (d[(y * w + x) * 4 + 3] > 40) { if (top < 0) top = y; bot = y; break; }
  }
  return top < 0 ? 0 : bot - top + 1;
}
function normalizeAction(cfg) {
  cfg = fill(cfg || {}, ACTION_DEFAULTS);
  cfg.conditions = (cfg.conditions || []).filter(function (c) { return c && CONDITION_TYPES[c.type]; })
    .map(function (c) { return fill(c, CONDITION_TYPES[c.type]); });
  return cfg;
}
// fx.continuous: the effect never stops producing while its action plays,
// loop after loop (a laser trail that is always on).  One instance is kept
// alive with no end (it restarts only if something ends it, e.g. a
// non-piercing hit); End frame / Life ticks / Emit every are ignored and it
// does not fade out.  Only for effects that stay on the fighter (attached,
// static or orbit motion) and are not arcs; travelling shots and crescents
// are one-shots, so the flag does nothing for them.
function canContinue(fx) {
  return fx.prim !== "arc" && ["attached", "static", "orbit", "path"].indexOf(fx.motion.kind) >= 0;
}
function isContinuous(fx) { return !!fx.continuous && canContinue(fx); }
// Progress 0..1 through an instance's window (a continuous instance goes
// through its window once, then holds at 1).
function lifeT(inst) { return Math.min(1, inst.age / Math.max(1, inst.cont ? inst.win : inst.life)); }
var _eid = 1;
function newEffect(prim, action) {
  return normalize({id: "E" + Date.now().toString(36) + (_eid++), name: prim, action: action || "idle",
    prim: prim, enabled: true});
}
function fill(dst, def) { for (var k in def) if (dst[k] === undefined) dst[k] = JSON.parse(JSON.stringify(def[k])); return dst; }
// Fill every missing field with its default so exported files are explicit.
function normalize(fx) {
  if (PRIMS.indexOf(fx.prim) < 0) fx.prim = "glow";
  fill(fx, {name: fx.prim, tag: "", enabled: true, start_frame: 0, end_frame: -1, life_ticks: 0, continuous: false,
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
// ---------------------------------------------------------------- entry sets / paths
// host.lib = {entry_sets: [...], paths: [...]} (the character's shared
// library, saved in the FX file).
//
// Entry set: {id, name, base, mode, interval_ticks, points: [[x, y], ...]}.
//   An effect whose anchor is "set:<id>" comes out of every point: all at
//   once ("simultaneous") or one after another, interval_ticks apart
//   ("sequential").  Points are game px from `base` ("figure" or an anchor
//   id), x forward (mirrored when facing left).
// Path: {id, name, points: [[0, 0], [x, y], ...], smooth, ticks, orient, end, follow}.
//   An effect with motion "path" travels along it from where it spawns,
//   start to end in `ticks`.  orient "facing" mirrors it with the facing;
//   "aim" also turns it so its start→end line points along the aim.
//   end: "stop" holds at the end, "loop" starts over, "continue" carries on
//   straight along the last direction at the same speed.  follow: the path
//   rides along with the fighter instead of staying where it started.
var ENTRY_DEFAULTS = {name: "entry points", base: "figure", mode: "simultaneous", interval_ticks: 6, points: []};
var PATH_DEFAULTS = {name: "path", points: [[0, 0]], smooth: true, ticks: 30, orient: "facing", end: "stop", follow: false};
function normalizeEntrySet(e) { e = fill(e || {}, ENTRY_DEFAULTS); e.points = (e.points || []).map(function (p) { return [+p[0] || 0, +p[1] || 0]; }); return e; }
function normalizePath(p) {
  p = fill(p || {}, PATH_DEFAULTS);
  p.points = (p.points || []).map(function (q) { return [+q[0] || 0, +q[1] || 0]; });
  if (!p.points.length) p.points = [[0, 0]];
  p.points[0] = [0, 0];
  p.ticks = Math.max(1, Math.round(+p.ticks || 1));
  return p;
}
function libFind(host, key, id) {
  var l = host.lib && host.lib[key];
  if (!l || !id) return null;
  for (var i = 0; i < l.length; i++) if (l[i].id === id) return l[i];
  return null;
}
function entrySetOf(fx, host) {
  if (typeof fx.anchor !== "string" || fx.anchor.indexOf("set:") !== 0) return null;
  var e = libFind(host, "entry_sets", fx.anchor.slice(4));
  return e && e.points.length ? e : null;
}
function entryPoint(set, k, host) {
  var b = host.anchor(set.base || "figure"), q = set.points[k] || [0, 0];
  return [b[0] + q[0] * host.facing, b[1] + q[1]];
}
function anchorPos(fx, host, inst) {
  var a, set = entrySetOf(fx, host);
  if (set) a = entryPoint(set, inst && inst.ep != null ? inst.ep % set.points.length : 0, host);
  else if (typeof fx.anchor === "string" && fx.anchor.indexOf("set:") === 0) a = host.anchor("figure");   // empty / missing set
  else a = host.anchor(fx.anchor);
  return [a[0] + (+fx.offset[0] || 0) * host.facing, a[1] + (+fx.offset[1] || 0)];
}
// A path as an evenly-spaced polyline (Catmull-Rom through the points when
// smooth): {pts, len, cum}.
function pathLine(path) {
  var P = path.points, pts = [];
  if (P.length < 2) return {pts: [[0, 0], [0, 0]], cum: [0, 0], len: 0};
  if (!path.smooth || P.length < 3) pts = P.map(function (q) { return q.slice(); });
  else {
    for (var i = 0; i < P.length - 1; i++) {
      var p0 = P[Math.max(0, i - 1)], p1 = P[i], p2 = P[i + 1], p3 = P[Math.min(P.length - 1, i + 2)];
      for (var k = 0; k < 12; k++) {
        var t = k / 12, t2 = t * t, t3 = t2 * t;
        pts.push([0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                  0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)]);
      }
    }
    pts.push(P[P.length - 1].slice());
  }
  var cum = [0];
  for (var j = 1; j < pts.length; j++) cum.push(cum[j - 1] + Math.hypot(pts[j][0] - pts[j - 1][0], pts[j][1] - pts[j - 1][1]));
  return {pts: pts, cum: cum, len: cum[cum.length - 1]};
}
// Point and unit direction at fraction u (0..1) of the way along, by distance.
function pathAt(pl, u) {
  var n = pl.pts.length, d = Math.max(0, Math.min(1, u)) * pl.len, i = 1;
  while (i < n - 1 && pl.cum[i] < d) i++;
  var a = pl.pts[i - 1], b = pl.pts[i], seg = pl.cum[i] - pl.cum[i - 1], f = seg > 1e-9 ? (d - pl.cum[i - 1]) / seg : 0;
  var dir = norm(b[0] - a[0], b[1] - a[1]);
  return [[a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f], dir];
}
// Local path px -> world offset: mirror with the facing, then (orient "aim")
// turn the start→end line onto the aim direction.
function pathMatrix(path, host, dir) {
  var f = host.facing, P = path.points, last = P[P.length - 1];
  if (path.orient !== "aim" || (!last[0] && !last[1])) return [f, 0, 0, 1];
  var th = Math.atan2(dir[1], dir[0]) - Math.atan2(last[1], last[0] * f), c = Math.cos(th), s = Math.sin(th);
  return [c * f, -s, s * f, c];
}
function pathWorld(inst, local) { var M = inst.pm; return [inst.po[0] + M[0] * local[0] + M[1] * local[1], inst.po[1] + M[2] * local[0] + M[3] * local[1]]; }
function pathStep(inst, host) {
  var path = inst.path, pl = inst.pl, k = inst.age / path.ticks, local, ld;
  if (path.follow) { var o = anchorPos(inst.fx, host, inst); inst.po = o; }
  if (path.end === "loop") k = k - Math.floor(k);
  if (k > 1 && path.end === "continue" && pl.len > 0) {
    var e = pathAt(pl, 1); ld = e[1];
    local = [e[0][0] + ld[0] * (k - 1) * pl.len, e[0][1] + ld[1] * (k - 1) * pl.len];
  } else { var r = pathAt(pl, k); local = r[0]; ld = r[1]; }
  var w = pathWorld(inst, local), M = inst.pm;
  inst.x = w[0]; inst.y = w[1];
  var wd = norm(M[0] * ld[0] + M[1] * ld[1], M[2] * ld[0] + M[3] * ld[1]);
  if (wd[0] || wd[1]) inst.dir = wd;
}

function spawn(fx, host, windowTicks, seed, idx, n, ep) {
  var p = anchorPos(fx, host, {ep: ep}), m = fx.motion;
  var dir = aimDir(fx, host, p[0], p[1]);
  if (n > 1 && fx.emit.fan_deg) dir = rot(dir, (-fx.emit.fan_deg / 2 + fx.emit.fan_deg * idx / (n - 1)) * host.facing);
  if (m.aim_offset_deg) dir = rot(dir, m.aim_offset_deg * host.facing);
  var life = fx.life_ticks > 0 ? fx.life_ticks : Math.max(1, windowTicks);
  var inst = {fx: fx, x: p[0], y: p[1], px: p[0], py: p[1], vx: 0, vy: 0, dir: dir, age: 0, life: life,
    seed: seed >>> 0, r: rng(seed), flow: 0, ended: false, dead: false, hist: [], trail: [], parts: [],
    ghosts: [], acc: 0, facing: host.facing, orbitA: 0, phase: 0, zx: 0, zy: 0,
    hits: 0, lastHit: -1e9, ep: ep == null ? null : ep};
  var spd = +m.speed || 0;
  if (m.kind === "path") {
    inst.path = libFind(host, "paths", m.path);
    if (inst.path) { inst.pl = pathLine(inst.path); inst.po = p.slice(); inst.pm = pathMatrix(inst.path, host, dir); }
  }
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
  if (m.kind === "attached") { var a = anchorPos(fx, host, inst); inst.x = a[0]; inst.y = a[1]; }
  if (m.kind === "path" && inst.path) {
    pathStep(inst, host);
    inst.vx = inst.x - inst.px; inst.vy = inst.y - inst.py;   // beams / trails read the travel speed
    return;
  }
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
    var c = anchorPos(fx, host, inst);
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
  var prog = lifeT(inst);
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
  var t = lifeT(inst), c = colorPair(fx, host.lut)[0].map(trunc);
  var k = P.fade === "out" ? 1 - t : P.fade === "in" ? t : P.fade === "inout" ? Math.sin(t * Math.PI) : 1;
  if (inst.cont) k = P.fade === "in" ? t : 1;   // continuous: fades in once, never out
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
  var t = lifeT(inst), gr = Math.max(P.core_r, P.r_start + (P.r_end - P.r_start) * t) * ps;
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
function Player() { this.insts = []; this.t = 0; this.clock = 0; this.pending = []; }
Player.prototype.reset = function () { this.insts = []; this.t = 0; this.clock = 0; this.pending = []; };
Player.prototype.window = function (fx, frames, frameMs) {
  var total = Math.max(1, Math.round(frames * frameMs / TICK_MS));
  var s = Math.round(Math.max(0, fx.start_frame) * frameMs / TICK_MS);
  var e = fx.end_frame < 0 ? total : Math.round((Math.min(frames - 1, fx.end_frame) + 1) * frameMs / TICK_MS);
  return [Math.min(s, total - 1), Math.max(s + 1, e), total];
};
// Advance one tick.  `t` counts ticks since the action started (it wraps
// when the action loops; instances already alive keep running).
// opts.continuous (the action's fx_continuous while it loops): an "open"
// instance (life 0 = to the end, window reaching the action's end) is kept
// alive across the loop, and its effect is not spawned again while it lives.
Player.prototype.tick = function (effects, host, t, frames, frameMs, opts) {
  var self = this, cont = !!(opts && opts.continuous);
  // Spawn `n` copies of fx.  With an entry set they come out of every point:
  // together, or (sequential) one point every interval_ticks.
  function fireFx(fx, t, n, win, tag) {
    var set = entrySetOf(fx, host), pts = set ? set.points.length : 1;
    for (var k = 0; k < pts; k++) {
      var delay = set && set.mode === "sequential" ? k * Math.max(0, trunc(set.interval_ticks)) : 0;
      var job = {fx: fx, t: t, n: n, win: win - delay, ep: set ? k : null, tag: tag, due: self.clock + delay};
      if (delay > 0) self.pending.push(job); else spawnJob(job);
    }
  }
  function spawnJob(j) {
    for (var i = 0; i < j.n; i++) {
      var seed = (hash32(j.fx.id) ^ Math.imul(j.t + 1, 0x9E3779B1) ^ (i * 0x85EBCA6B) ^ Math.imul((j.ep == null ? 0 : j.ep + 1), 0xC2B2AE35)) >>> 0;
      var inst = spawn(j.fx, host, Math.max(1, j.win), seed, i, j.n, j.ep);
      if (j.tag === "cont") { inst.cont = true; inst.win = inst.life; inst.life = Infinity; }
      else inst.open = j.tag === "open";
      self.insts.push(inst);
    }
  }
  var due = this.pending.filter(function (j) { return j.due <= self.clock; });
  this.pending = this.pending.filter(function (j) { return j.due > self.clock; });
  due.forEach(function (j) { if (j.fx.enabled && effects.indexOf(j.fx) >= 0) spawnJob(j); });
  // A continuous instance ends when its effect is removed, disabled or no
  // longer continuous.
  this.insts.forEach(function (inst) {
    if (inst.cont && (!inst.fx.enabled || effects.indexOf(inst.fx) < 0 || !isContinuous(inst.fx))) inst.dead = true;
  });
  effects.forEach(function (fx) {
    if (!fx.enabled) return;
    var w = self.window(fx, frames, frameMs), s = w[0], e = w[1];
    if (isContinuous(fx)) {   // one never-ending instance, started at its start frame
      if (t < s || self.insts.some(function (q) { return q.fx === fx && q.cont && !q.dead && q.age < q.life; })
        || self.pending.some(function (q) { return q.fx === fx; })) return;
      fireFx(fx, t, Math.max(1, trunc(fx.emit.count)), w[2] - s, "cont");
      return;
    }
    var periodic = fx.emit.every_ticks > 0 && t > s && t < e && (t - s) % fx.emit.every_ticks === 0;
    var fire = t === s || periodic;
    if (!fire) return;
    var open = fx.life_ticks <= 0 && e >= w[2];
    if (cont && open && !periodic && self.insts.some(function (q) { return q.fx === fx && q.open && !q.dead; })) return;
    fireFx(fx, t, Math.max(1, trunc(fx.emit.count)), e - t, open ? "open" : "");
  });
  this.clock += 1;
  var ps = host.pscale || 1;
  if (cont) this.insts.forEach(function (inst) { if (inst.open && inst.age < inst.life) inst.life = Math.max(inst.life, inst.age + 2); });
  this.insts.forEach(function (inst) { tickInst(inst, host); resolveHits(inst, host, ps); });
  this.insts = this.insts.filter(function (i) { return !i.dead; });
};
Player.prototype.draw = function (g, host, layer, ps) {
  this.insts.forEach(function (inst) { if (inst.fx.layer === layer) drawInst(g, inst, host, ps); });
};

G.FXK = {TICK_MS: TICK_MS, rng: rng, hash32: hash32, buildLut: buildLut, hexRgb: hexRgb,
  PRIMS: PRIMS, MOTIONS: MOTIONS, AIMS: AIMS, PARAM_DEFAULTS: PARAM_DEFAULTS,
  MOTION_DEFAULTS: MOTION_DEFAULTS, COLOR_DEFAULTS: COLOR_DEFAULTS, BATTLE_DEFAULTS: BATTLE_DEFAULTS,
  newEffect: newEffect, normalize: normalize, normalizeEntrySet: normalizeEntrySet, normalizePath: normalizePath,
  ENTRY_DEFAULTS: ENTRY_DEFAULTS, PATH_DEFAULTS: PATH_DEFAULTS, pathLine: pathLine, pathAt: pathAt, pathMatrix: pathMatrix, canContinue: canContinue, isContinuous: isContinuous, CONDITION_TYPES: CONDITION_TYPES, ACTION_DEFAULTS: ACTION_DEFAULTS, AIM_DEFAULTS: AIM_DEFAULTS, normalizeAim: normalizeAim, aimAngle: aimAngle,
  STAND_HEIGHT_PX: STAND_HEIGHT_PX, rescaleEffects: rescaleEffects, standHeight: standHeight,
  actionKind: actionKind, moveFactor: moveFactor, animLoops: animLoops, normalizeAction: normalizeAction, Player: Player, bulletSprite: bulletSprite};
})(window);
