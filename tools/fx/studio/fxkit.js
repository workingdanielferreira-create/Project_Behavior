/* FX Kit runtime (pb_fxkit v2) — the reference implementation.
 *
 * Every FX the Studio authors is an EFFECT: one drawing primitive + where it
 * starts (anchor joint), how it moves (motion), what colour it takes (colour
 * source) and when it plays (frames of the character's action).  The nine
 * primitives are the engine's own drawing routines, lifted out of the
 * hardcoded effect classes so any character can compose them:
 *
 *   ribbon     components.TrailComponent.draw       (laser trail)
 *   arc        combat.CrescentWave.draw             (slash crescent)
 *   beam       combat.RichBeamProjectile.draw       (segmented beam)
 *   sprite     combat.bullet_sprite / bolt_sprite + Projectile.draw (orbs, bolts)
 *   particles  combat.BurstParticle                 (sparks, dust)
 *   glow       TrailComponent head glow/core        (spheres, flares)
 *   pulse      radial pulse rings (new)             (shockwaves, auras)
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
// glowPct: brightness of the soft outer glow (0 = none, 100 = the original);
// glowSizePct: how far it spreads (100 = 3 x radius).  combat.bullet_sprite.
function bulletSprite(r, gc, b, radius, glowPct, glowSizePct) {
  var ga = Math.max(0, Math.min(255, Math.round(140 * Math.max(0, glowPct == null ? 100 : +glowPct) / 100)));
  var gs = Math.max(0, glowSizePct == null ? 100 : +glowSizePct) / 100;
  var key = "b" + r + "," + gc + "," + b + "," + Math.round(radius * 100) / 100 + "," + ga + "," + Math.round(gs * 100) / 100;
  if (SPR[key]) return SPR[key];
  var glow = Math.max(1, radius * 3 * gs), rad = Math.max(1, radius), size = Math.ceil(Math.max(glow, rad) * 2) + 2, c = size / 2;
  var cv = canvas(size, size), g = cv.getContext("2d");
  if (ga > 0) {
    g.fillStyle = radial(g, c, c, glow, [[0, rgba([r, gc, b], ga)], [1, rgba([r, gc, b], 0)]]);
    ellipse(g, trunc(c - glow), trunc(c - glow), trunc(glow * 2), trunc(glow * 2));
  }
  g.fillStyle = radial(g, c, c, rad, [[0, "rgba(255,255,255," + 240 / 255 + ")"], [0.5, rgba([r, gc, b], 210)], [1, rgba([r, gc, b], 140)]]);
  ellipse(g, trunc(c - rad), trunc(c - rad), trunc(rad * 2), trunc(rad * 2));
  return (SPR[key] = {cv: cv, half: trunc(size / 2)});
}
function boltSprite(r, gc, b, radius, stretch, hot, glowPct, glowSizePct) {
  var ga = Math.max(0, Math.min(255, Math.round(170 * Math.max(0, glowPct == null ? 100 : +glowPct) / 100)));
  var gs = Math.max(0, glowSizePct == null ? 100 : +glowSizePct) / 100;
  var key = "o" + r + "," + gc + "," + b + "," + Math.round(radius * 100) / 100 + "," + Math.round(stretch * 100) / 100 + "," + (hot ? 1 : 0) + "," + ga + "," + Math.round(gs * 100) / 100;
  if (SPR[key]) return SPR[key];
  var glow = Math.max(1, radius * 3 * gs, Math.max(1, radius) * 1.2);   // never smaller than the head
  var w = Math.ceil(glow * 2 * stretch) + 2, h = Math.ceil(glow * 2) + 2;
  var cx = w / 2, cy = h / 2, headX = w - glow;
  var cv = canvas(w, h), g = cv.getContext("2d");
  g.save(); g.translate(cx, cy); g.scale(stretch, 1);
  g.fillStyle = radial(g, 0, 0, glow, [[0, rgba([r, gc, b], ga)], [1, rgba([r, gc, b], 0)]]);
  if (ga > 0) ellipse(g, trunc(-glow), trunc(-glow), trunc(glow * 2), trunc(glow * 2));
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
// Ethereal blade: a sword of light, tip pointing +x.  Half-width = radius,
// length = 2 x radius x stretch (tip to pommel).  A diamond-faceted blade
// (light upper facet, deeper lower facet, white ridge) widest near the tip,
// a crystal guard at 82 % of the length, a fading grip, a tight bloom and a
// wide halo (glow / glow_size) along it, and a four-point glint at the tip
// (hot makes the ridge and glint brighter and the glint bigger).
// laser/fxkit.py blade_sprite.  Returns {cv, tipX, halfH}; blitBlade draws
// it end for end (the glint at the hilt, the fading grip as the point).
var BLADE_SHOULDER = 0.18, BLADE_BASE = 0.82, BLADE_LODGE_FADE_MS = 300;
function bladeSprite(r, gc, b, radius, stretch, hot, glowPct, glowSizePct) {
  var ga = Math.max(0, Math.min(255, Math.round(150 * Math.max(0, glowPct == null ? 100 : +glowPct) / 100)));
  var gs = Math.max(0, glowSizePct == null ? 100 : +glowSizePct) / 100;
  var key = "k" + r + "," + gc + "," + b + "," + Math.round(radius * 100) / 100 + "," + Math.round(stretch * 100) / 100 + "," + (hot ? 1 : 0) + "," + ga + "," + Math.round(gs * 100) / 100;
  if (SPR[key]) return SPR[key];
  var rad = Math.max(0.5, +radius), L = 2 * rad * Math.max(1, +stretch), gw = rad * 3 * gs;
  var ry = rad + gw, rx = L / 2 + gw, fl = rad * 2.4 * (hot ? 1.5 : 1), gh = rad * 1.9;
  var pad = Math.max(1, gw, fl);
  var w = Math.ceil(L + 2 * pad) + 2, h = Math.ceil(2 * Math.max(ry, fl, gh)) + 2;
  var tipX = w - pad, cy = h / 2, sx = tipX - L * BLADE_SHOULDER, bx = tipX - L * BLADE_BASE, ex = tipX - L;
  var cv = canvas(w, h), g = cv.getContext("2d"), col = [r, gc, b];
  var lt = [trunc(r + (255 - r) * 0.55), trunc(gc + (255 - gc) * 0.55), trunc(b + (255 - b) * 0.55)];   // light facet tint
  var poly = function (pts, x0, x1, stops) {
    var gr = g.createLinearGradient(x0, cy, x1, cy);
    stops.forEach(function (st) { gr.addColorStop(st[0], st[1]); });
    g.fillStyle = gr; g.beginPath(); g.moveTo(pts[0][0], pts[0][1]);
    for (var i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]);
    g.closePath(); g.fill();
  };
  var halo = function (cx, hrx, hry, c, a) {   // radial glow stretched along the blade
    g.save(); g.translate(cx, cy); g.scale(hrx / hry, 1);
    g.fillStyle = radial(g, 0, 0, hry, [[0, rgba(c, a)], [1, rgba(c, 0)]]);
    ellipse(g, trunc(-hry), trunc(-hry), trunc(hry * 2), trunc(hry * 2));
    g.restore();
  };
  if (ga > 0) {
    halo(tipX - L / 2, rx, ry, col, ga);   // wide halo
    halo(tipX - L * 0.4, L * 0.45 + rad, rad * 1.9, lt, Math.round(ga * 0.8));   // tight bloom
  }
  // grip, fading toward the pommel
  poly([[bx - rad * 0.3, cy - rad * 0.3], [ex, cy - rad * 0.18], [ex, cy + rad * 0.18], [bx - rad * 0.3, cy + rad * 0.3]], ex, bx,
       [[0, rgba(lt, 0)], [1, rgba(lt, 170)]]);
  // blade facets: light upper, deeper lower, brightest at the tip
  var fs = function (c) { return [[0, rgba(c, 110)], [0.7, rgba(c, 200)], [1, rgba(c, 245)]]; };
  poly([[tipX, cy], [sx, cy - rad], [bx, cy - rad * 0.55], [bx, cy]], bx, tipX, fs(lt));
  poly([[tipX, cy], [sx, cy + rad], [bx, cy + rad * 0.55], [bx, cy]], bx, tipX, fs(col));
  // white ridge down the middle
  var ra = hot ? 255 : 200;
  poly([[tipX, cy], [sx, cy - rad * 0.14], [bx, cy - rad * 0.1], [bx, cy + rad * 0.1], [sx, cy + rad * 0.14]], bx, tipX,
       [[0, "rgba(255,255,255," + 60 / 255 + ")"], [1, "rgba(255,255,255," + ra / 255 + ")"]]);
  // crystal guard
  poly([[bx, cy - gh], [bx + rad * 0.3, cy], [bx, cy + gh], [bx - rad * 0.3, cy]], bx - rad * 0.3, bx + rad * 0.3,
       [[0, rgba(lt, 200)], [1, rgba([255, 255, 255], 220)]]);
  // four-point glint at the tip
  g.fillStyle = radial(g, tipX, cy, fl * 0.45, [[0, "rgba(255,255,255," + 245 / 255 + ")"], [0.5, rgba(col, 180)], [1, rgba(col, 0)]]);
  ellipse(g, trunc(tipX - fl * 0.45), trunc(cy - fl * 0.45), trunc(fl * 0.9), trunc(fl * 0.9));
  [[1, 0.1], [0.1, 1]].forEach(function (k) {
    g.save(); g.translate(tipX, cy); g.scale(k[0], k[1]);
    g.fillStyle = radial(g, 0, 0, fl, [[0, "rgba(255,255,255," + 230 / 255 + ")"], [1, "rgba(255,255,255,0)"]]);
    ellipse(g, trunc(-fl), trunc(-fl), trunc(fl * 2), trunc(fl * 2));
    g.restore();
  });
  return (SPR[key] = {cv: cv, tipX: tipX, halfH: h / 2});
}
// Which way a blade's tip points: its impact angle while lodged; with
// blade_orient "angle" the held blade_angle_deg (mirrored by Flip); else
// along its velocity, else along this tick's movement (orbit, attached),
// else straight down.  laser/fxkit.py blade_angle.
function bladeAngle(inst) {
  if (inst.lodge) return inst.lodge.a;
  var P = inst.fx.params;
  if (P.blade_orient === "angle") { var fa = (+P.blade_angle_deg || 0) * D; return inst.flip < 0 ? Math.PI - fa : fa; }
  if (inst.vx * inst.vx + inst.vy * inst.vy > 0.0001) return Math.atan2(inst.vy, inst.vx);
  var dx = inst.x - inst.px, dy = inst.y - inst.py;
  if (dx * dx + dy * dy > 1e-6) return Math.atan2(dy, dx);
  return Math.PI / 2;
}
// Draw a blade sprite (already translated to the blade's tip, rotated to its
// angle and scaled) end for end: the art is mirrored along the blade so the
// fading end leads and the glint sits at the hilt; the blade covers the same
// tip-to-pommel line as before (hits and lodging unchanged).
// laser/fxkit.py _blit_blade.
function blitBlade(g, k, P) { g.scale(-1, 1); g.drawImage(k.cv, trunc(bladeLength(P, 1) - k.tipX), trunc(-k.halfH)); }
function bladeLength(P, ps) { var rad = Math.max(0.5, +P.radius); return 2 * rad * Math.max(1, +P.stretch) * ps; }
// Each particle on a blade: the target it aims at (copied each tick), else
// null.  laser/fxkit.py aim_target.
function aimTarget(fx, host) {
  return fx.follow_each && fx.prim === "sprite" && fx.params.shape === "blade" ? [+host.target[0], +host.target[1]] : null;
}
// Where a blade's tip is and which way it points: [x, y, angle].  As authored,
// inst.x / inst.y is the tip and bladeAngle the direction.  With Each
// particle the blade pivots on its own centre (the middle of
// the authored blade) so its tip points at the target; lodged and deflected
// blades keep their own pose.  laser/fxkit.py blade_pose.
function bladePose(inst, ps) {
  var a = bladeAngle(inst), T = inst.tgt;
  if (!T || inst.lodge || inst.free || inst.vx * inst.vx + inst.vy * inst.vy > 0.0001) return [inst.x, inst.y, a];   // flying blades point along their flight
  var h = bladeLength(inst.fx.params, ps) / 2, cx = inst.x - Math.cos(a) * h, cy = inst.y - Math.sin(a) * h;
  var dx = T[0] - cx, dy = T[1] - cy;
  if (dx * dx + dy * dy < 1e-6) return [inst.x, inst.y, a];
  a = Math.atan2(dy, dx);
  return [cx + Math.cos(a) * h, cy + Math.sin(a) * h, a];
}
// A non-piercing blade that hits a hurt circle (hx, hy, hr) lodges instead of
// ending: turned up to BLADE_LODGE_JITTER_DEG off its impact direction (the
// instance's seeded rng, so blades on one path don't stack), its tip is
// driven along it toward the point nearest the circle's centre (70-100 % of
// the way, no deeper than 45 % of the blade), it stays at that
// angle and offset from the target, following it, for lodge_ms (fading out
// over the last 300 ms), hidden where it is inside the target, and deals no
// more damage.  laser/fxkit.py blade_lodge.
var BLADE_LODGE_JITTER_DEG = 10;
function bladeLodge(inst, hx, hy, hr, ps) {
  var P = inst.fx.params, bp = bladePose(inst, ps), bx = bp[0], by = bp[1];
  var a = bp[2] + inst.r.uniform(-BLADE_LODGE_JITTER_DEG, BLADE_LODGE_JITTER_DEG) * D, ux = Math.cos(a), uy = Math.sin(a), L = bladeLength(P, ps);
  var s0 = (hx - bx) * ux + (hy - by) * uy;   // along the blade to the point nearest the centre
  var px = hx - (bx + ux * s0), py = hy - (by + uy * s0), half = Math.sqrt(Math.max(0, hr * hr - px * px - py * py));
  var inside = Math.min(half * inst.r.uniform(0.7, 1), L * 0.45), tx = bx + ux * s0, ty = by + uy * s0;
  if (half > inside) { tx -= ux * (half - inside); ty -= uy * (half - inside); }
  var n = Math.max(1, Math.round(+P.lodge_ms / TICK_MS));
  inst.lodge = {a: a, ox: tx - hx, oy: ty - hy, hx: hx, hy: hy, depth: inside, n: n};
  inst.x = tx; inst.y = ty; inst.px = tx; inst.py = ty; inst.vx = 0; inst.vy = 0; inst.trail = [];
  inst.life = inst.age + n;
}
// Each tick a lodged blade follows the hurt circle nearest where its target
// last was (within 200 px x scale); with none (target gone) it stays put.
function bladeFollow(inst, hurts, ps) {
  var lg = inst.lodge, best = null, bd = 200 * ps * 200 * ps;
  hurts.forEach(function (q) { var dx = q[0] - lg.hx, dy = q[1] - lg.hy, d = dx * dx + dy * dy; if (d <= bd) { bd = d; best = q; } });
  if (best) { lg.hx = best[0]; lg.hy = best[1]; }
  inst.px = inst.x; inst.py = inst.y; inst.x = lg.hx + lg.ox; inst.y = lg.hy + lg.oy;
}

// ---------------------------------------------------------------- schema
var PRIMS = ["ribbon", "arc", "beam", "sprite", "particles", "glow", "pulse", "ghost", "weapon"];
var MOTIONS = ["attached", "static", "travel", "homing", "zigzag", "orbit", "path"];
var AIMS = ["target", "facing", "angle", "weapon"];
// Default params per primitive = the engine constants of the effect it came from.
var PARAM_DEFAULTS = {
  ribbon: {max_points: 50, min_dist: 2, decay: 2, taper: true, w_tail: 1, w_head: 5, alpha: 220, head_glow_r: 1, head_dot_r: 1},
  arc: {radius: 42, span: 170, width: 6.5, tail: 0.95, segs: 16, grow: 0.85, core_alpha: 0.7, core_width: 0.3, orient: "motion", angle_deg: 0,
        placement: "anchor", back: 51, lead: 26},
  beam: {length: 200, w_start0: 6, w_start1: 6, w_end0: 2, w_end1: 2, segments: 1, glow: 0, glow_color: "", pulse_hz: 0, jitter: 0, detach_ticks: 0, grow_ticks: 0, tip_fade: 0},
  // Blade only: lodge_ms = how long a non-piercing blade stays stuck in the target it hits (0 = it ends on the hit);
  // blade_orient motion = the tip points where it moves, angle = it holds blade_angle_deg (0 = right, 90 = down; Flip mirrors it).
  sprite: {shape: "orb", radius: 3, stretch: 1, hot: false, halo: false, fade: true, trail_len: 5, glow: 100, glow_size: 100, lodge_ms: 1500,
           blade_orient: "motion", blade_angle_deg: 90},
  particles: {mode: "burst", count: 12, rate_per_s: 60, angle_deg: 0, spread_deg: 30, speed_min: 50, speed_max: 150, gravity: 0, drag: 1, size_min: 3, size_max: 3, size_over_life: "shrink", life_min_ms: 200, life_max_ms: 400},
  glow: {r_start: 6, r_end: 6, a_center: 140, a_mid: 60, mid: 0.4, core_r: 0, fade: "out", pulse_hz: 0},
  // Radial pulse: rings that expand from r_start to r_end over expand_ms
  // stretch_x / stretch_y stretch them into ellipses (radius multipliers,
  // 1 = round) tilted by tilt_deg, like an orbit's radius X / Y (pulseShape).
  // (pulseRings).  rings = how many, gap_ms apart (0 = one every gap_ms for
  // as long as the effect lasts).
  pulse: {r_start: 0, r_end: 120, width: 6, width_end: 2, expand_ms: 400, rings: 1, gap_ms: 200, ease: "out", fade: "out", glow: 8, fill_alpha: 0,
    stretch_x: 1, stretch_y: 1, tilt_deg: 0},
  ghost: {interval: 2, ghost_life: 14, alpha: 150, max: 12},
  weapon: {to_anchor: "wtip", width: 6}
};
var MOTION_DEFAULTS = {kind: "attached", aim: "target", angle_deg: 0, aim_offset_deg: 0, speed: 8,
  turn_deg: 6, amplitude: 55, freq: 0.18, orbit_rx: 46, orbit_ry: 46, orbit_deg: 1.12, orbit_dir: "clockwise", path: ""};
// orbit_dir: which way an orbit spins on screen, clockwise or anticlockwise (Flip mirrors it, like the rest of the effect).
function orbitStep(m) { return (+m.orbit_deg || 0) * (m.orbit_dir === "anticlockwise" ? -1 : 1); }
var COLOR_DEFAULTS = {mode: "palette", lut_index: 128, lut_index2: 128, lut_offset: 0, flow_speed: 0.008,
  c1: "#ffffff", c2: "#ff2200", start_fraction: 0};
// Damage settings (fx.battle).  damage is HP per hit, matching
// ai.apply_hp_damage(amount) — every built-in attack deals 1.
// blockable / deflectable: whether the OTHER fighter's defences can stop this
// effect.  Block = its defend action, special stance, parry stance and
// Intercept "block" / "destroy"; deflect = Intercept "deflect" (and parry
// ricochets).  Off = that defence ignores the effect and the hit lands.
var BATTLE_DEFAULTS = {deals_damage: false, damage: 1, pierce: false, rehit_ticks: 0, knockback: 0,
  blockable: true, deflectable: true};
// Intercept settings (fx.intercept): the auto-projectile tracker.  Only for
// projectiles (travel, homing or zigzag motion).  When an enemy projectile
// comes within `radius` px the shot steers at it (up to `turn_deg` per tick,
// like homing); when it gets within `contact` px of it:
//   block    both projectiles are nullified
//   deflect  the enemy projectile (deflect_who "enemy") or both ("both") fly
//            off along their combined momentum; hurts_owner makes the
//            deflected enemy projectile able to damage the fighter who fired it
//   destroy  the enemy projectile is nullified, this one keeps going
//   clash    beats every non-clash projectile; against another clash one,
//            knockback decides (see CLASH_KB_MARGIN / interceptStep)
// With no enemy projectile in range the shot resumes its own motion.
var INTERCEPT_DEFAULTS = {enabled: false, radius: 90, turn_deg: 10, contact: 10, mode: "block",
  deflect_who: "enemy", hurts_owner: false};
var INTERCEPT_MODES = ["block", "deflect", "destroy", "clash"];
// Flip (fx.flip): when enabled the effect is laid out toward the side the
// target is on (fxFacing), whichever way the fighter itself faces, and it
// plays as the mirror image (left <-> right only, never up <-> down) when
// that side is the other one from `facing` (the Studio facing it was created
// at, 1 right / -1 left): on top of offsets, entry points, paths and
// particle / fixed angles, flip mirrors the arc's sweep and the orbit's side
// and spin.  Target-aimed effects still aim at the target.  Off = everything
// follows the fighter's facing (the old behaviour).
var FLIP_DEFAULTS = {enabled: false, facing: 1};
// -1 when this effect plays mirrored for a fighter facing `facing`, else 1.
function flipSign(fx, facing) {
  var f = fx.flip;
  return f && f.enabled && facing !== (+f.facing < 0 ? -1 : 1) ? -1 : 1;
}
// 1 when the target is right of the figure, -1 left (the facing when level).
function targetSide(host) {
  var b = host.anchor("figure"), dx = host.target[0] - b[0];
  return dx < -0.001 ? -1 : dx > 0.001 ? 1 : host.facing;
}
// The facing an effect is laid out for: the target's side with Flip on,
// else the fighter's facing.
function fxFacing(fx, host) { return fx.flip && fx.flip.enabled ? targetSide(host) : host.facing; }
// Follow direction (fx.follow_dir): the whole effect turns toward the target
// at any angle.  As authored it points straight forward (along its facing);
// it turns by the angle from there to the figure -> target line (degrees,
// applied after mirroring, the way anchors turn): target above -> it turns
// up.  With Flip on as well it first mirrors to the target's side, so it
// only ever tilts up / down; without Flip a target behind turns it right
// round.  Offsets, entry points, facing / angle / weapon aims, the arc's
// angle, particle angles, orbits and paths all turn; target aims already
// track the target.
// The two ticks are independent:
//   Follow direction (follow_dir)  the offset and entry points swing round
//                                  the anchor (placeDeg).
//   Each particle (follow_each)    every particle turns on its own sub-anchor
//                                  (its own centre) and stays where it was
//                                  placed; blades aim their tips at the
//                                  target (bladePose).
// Either one turns the effect's own direction (bodyDeg); both together do
// both.  With Each particle the turn is measured from the particle's own spot
// (`at`) to the target, so every particle points at the target from where it
// is (aims, launches, arcs, beams, particle angles, paths, orbits, tilt).
function degToTarget(fx, host, b) {
  var dx = host.target[0] - b[0], dy = host.target[1] - b[1];
  if (dx * dx + dy * dy < 1e-6) return 0;
  var a = Math.atan2(dy, dx) / D - (fxFacing(fx, host) < 0 ? 180 : 0);
  return ((a % 360) + 540) % 360 - 180;
}
function bodyDeg(fx, host, at) {
  if (fx.follow_each && at) return degToTarget(fx, host, at);
  if (!fx.follow_dir && !fx.follow_each) return 0;
  return degToTarget(fx, host, host.anchor("figure"));
}
// The turn for where the effect sits (offset, entry points): only Follow
// direction swings it round its anchor.
function placeDeg(fx, host) { return fx.follow_dir ? degToTarget(fx, host, host.anchor("figure")) : 0; }
function turnBy(v, deg) { return deg ? rot(v, deg) : v; }
// Sign for the facing-relative turns (fan, aim offset) and, times inst.flip,
// the arc / zigzag side.  Without Flip: the facing (the old behaviour).  With
// Flip, a target aim heading backward counts as forward, so the effect's
// up / down never swaps.
function turnSign(fx, host, d, at) {
  var f = fxFacing(fx, host);
  if (!fx.flip || !fx.flip.enabled || fx.motion.aim !== "target") return f;
  var u = turnBy(d, -bodyDeg(fx, host, at));
  return u[0] * f < 0 ? -f : f;
}
// Per-action settings (pack.action_settings[action]).  WHEN an action plays:
//   idle / run      locomotion (standing still / moving), no conditions
//   attack actions  the archetype decides when to attack (target in range);
//                   trigger conditions, if any, must ALSO pass.  `chain_next`
//                   makes attacks run as a combo (attack_normal -> attack_normal_2
//                   ...) that resets after `chain_reset_ms` without attacking
//   other actions   fire when their conditions are met (ANY or ALL), no more
//                   often than every `cooldown_ms`
// Every condition also has `not` (false): true inverts it.  Mirrored by
// laser/actions.py CONDITION_TYPES.  Speeds are game px per second.  In Solo
// the target is the cursor: no HP, never attacks / defends, and "faces" the
// way it last moved sideways.
var CONDITION_TYPES = {
  // own state
  hp_below:      {pct: 50, repeat: false},             // own HP <= pct % (once per crossing unless repeat)
  hp_above:      {pct: 80},                            // own HP >= pct %
  self_speed_above: {px_s: 120},                       // moving at least px/s
  self_speed_below: {px_s: 20},                        // moving at most px/s (20 ~ standing)
  // the target
  target_within: {px: 80},                             // target closer than px
  target_beyond: {px: 200},                            // target further than px
  target_between: {min_px: 60, max_px: 200},           // target distance inside the band
  target_above:  {px: 40},                             // target at least px higher on screen
  target_below:  {px: 40},                             // target at least px lower on screen
  target_facing: {dir: "toward"},                      // target faces toward / away from this fighter
  target_attacking: {},                                // target is attacking (dash, slash, attack / ultimate action)
  target_defending: {},                                // target is parrying / playing defend
  target_hp_below: {pct: 50},                          // target HP <= pct % (Battle)
  target_hp_above: {pct: 80},                          // target HP >= pct % (Battle)
  target_speed_above: {px_s: 120},                     // target moving at least px/s
  target_speed_below: {px_s: 20},                      // target moving at most px/s
  // hits and projectiles
  attacks_made:  {count: 3},                           // after N attacks since this action last fired
  hits_taken:    {count: 3},                           // after being hit N times since it last fired
  damage_taken:  {hp: 10, ms: 2000},                   // lost at least hp HP in the last ms
  landed_hit:    {},                                   // one of this fighter's FX just hit the target
  hit_by_fx:     {tags: ""},                           // hit by an enemy FX with one of these tags ("" = any)
  fx_near:       {tags: "", px: 60},                   // an enemy FX with one of these tags comes within px
  projectile_count: {count: 5},                        // count or more enemy projectiles / damaging FX live
  bullet_deflected: {},                                // this character just deflected a bullet
  // timing and order
  after_actions: {sequence: ""},                       // just completed these actions in order, comma separated
  since_action:  {action: "", ms: 2000},               // action ("" = this one) last ended at least ms ago (or never ran)
  every_ms:      {ms: 3000},                           // at least ms since this action last started (or the fight began)
  idle_for:      {ms: 1000},                           // no action playing for at least ms
  chance:        {pct_s: 30}                           // random: pct % chance per second
};
var CONDITION_COMMON = {not: false};
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
// attack_px (normal attacks): how close the target must be for this attack to
// start, game px at 100 % character scale; 0 = the character's
// stats.basic_attack_radius (shooters: their shooting range).
var ACTION_DEFAULTS = {logic: "any", cooldown_ms: 0, conditions: [], chain_next: "", chain_reset_ms: 1000, fx_continuous: false,
  movement: "stand", move_speed_pct: 100, anim_loops: 1, back_stop_pct: 80, attack_px: 0};
// blink: the action's Blink (BLINK_DEFAULTS below).
// Character-level aiming (pack.aim): the fighter always faces the target and
// the whole frame on show turns so its barrel (from -> to anchor of that
// frame; the source action's average when the frame has none) points at the
// target, at most max_deg either way.  Same maths as laser/fxkit.py aim_angle.
var AIM_DEFAULTS = {enabled: false, source: "attack_normal", from_anchor: "haR", to_anchor: "wtip", max_deg: 75};
function normalizeAim(a) { return fill(a || {}, AIM_DEFAULTS); }
// Character-level "Damaged" settings (pack.damaged): after a hit ticks HP the
// fighter is invincible (no HP loss, no knockback) for cooldown_ms; the next
// hit after that ticks HP again.  0 = every hit ticks HP (the old behaviour).
// Read by laser/ai.py damage_immune() for every HP source.
var DAMAGED_DEFAULTS = {cooldown_ms: 0};
function normalizeDamaged(a) { return fill(a || {}, DAMAGED_DEFAULTS); }
// Character-level "Tactical retreat" (pack.retreat), run by laser/retreat.py.
// When its conditions are met (ANY / ALL) the fighter dashes at speed_pct % of
// its speed.  angle_deg is measured from the direction to the target: 0 = at
// it, 180 / -180 = straight away, positive = clockwise; curve_deg_s bends the
// path that many degrees per second.  The mode runs during the dash for its own
// duration (-1 = no limit):
//   avoid     steer away from harm (enemy projectiles, the target) within proximity_px
//   reengage  head for the target's back (opposite the way it faced when the
//             retreat started), dodging projectiles within proximity_px, and
//             attack on arrival
// A new retreat can start cooldown_ms after the last one ended.
var RETREAT_DEFAULTS = {enabled: false, mode: "avoid", angle_deg: 180, curve_deg_s: 0, speed_pct: 200,
  proximity_px: 80, avoid_duration_ms: 1500, reengage_duration_ms: 2000, cooldown_ms: 3000, logic: "any", conditions: [], fx: ""};
// Retreat conditions: every action trigger condition (CONDITION_TYPES, with
// `not`).  "This action" means the retreat: attacks_made / hits_taken /
// every_ms count from the last retreat start, since_action "" from the last
// retreat end.  projectile_count counts enemy shots only.
var RETREAT_CONDITIONS = CONDITION_TYPES;
function normalizeRetreat(a) {
  a = fill(a || {}, RETREAT_DEFAULTS);
  a.conditions = (a.conditions || []).filter(function (c) { return c && RETREAT_CONDITIONS[c.type]; })
    .map(function (c) { return fill(fill(c, RETREAT_CONDITIONS[c.type]), CONDITION_COMMON); });
  return a;
}
// Blink (action_settings[action].blink), run by laser/blink.py: a teleport
// inside one action, set per action.  While that action plays, the fighter
// vanishes when it reaches start_frame and reappears once it passes
// end_frame (-1 = the last frame), or when the action ends, whichever comes
// first.  It reappears proximity_px from the anchor ("target" = the target
// where it is at that moment, "self" = the spot the fighter vanished from)
// in the chosen direction (blinkLanding):
//   behind  the target's back (opposite the way it faces; the Solo cursor
//           and the Studio target have no facing: the far side from the fighter)
//   front   the side the target faces (no facing: the fighter's side)
//   toward  along the fighter -> target line
//   away    along the target -> fighter line
//   random  any direction
//   angle   angle_deg from the fighter -> target line (0 = toward, 180 = away,
//           positive = clockwise)
// While gone it is invisible and untouchable, stays put and fires no new FX
// (shots already flying carry on); the action and its animation keep running
// hidden, so the frames tick on to end_frame.  flash = crackle + afterimage
// at both ends.  Each loop of a looping action blinks again.  cooldown_ms
// (0 = none): after it reappears, the action's Blink stays off this long (the
// action still plays, without vanishing or its Blink FX).
var BLINK_DEFAULTS = {enabled: false, start_frame: 0, end_frame: -1, anchor: "target", direction: "behind", angle_deg: 0,
  proximity_px: 60, flash: true, cooldown_ms: 0};
var BLINK_ANCHORS = ["target", "self"];
var BLINK_DIRECTIONS = ["behind", "front", "toward", "away", "random", "angle"];
function normalizeBlink(a) {
  a = fill(a || {}, BLINK_DEFAULTS);
  if (BLINK_ANCHORS.indexOf(a.anchor) < 0) a.anchor = BLINK_DEFAULTS.anchor;
  if (BLINK_DIRECTIONS.indexOf(a.direction) < 0) a.direction = BLINK_DEFAULTS.direction;
  a.start_frame = Math.max(0, Math.round(+a.start_frame || 0));
  a.end_frame = Math.round(+a.end_frame);
  if (!(a.end_frame >= -1)) a.end_frame = -1;
  return a;
}
// Whether frame `fr` of an action with `frames` frames is inside the blink.
function blinkActive(b, fr, frames) {
  if (!b || !b.enabled) return false;
  var e = b.end_frame < 0 ? frames - 1 : Math.min(frames - 1, b.end_frame);
  return fr >= b.start_frame && fr <= e;
}
// Landing spot: from = where the fighter vanished, target = [x, y],
// tface = the target's facing (1 / -1) or null (no facing), facing = the
// fighter's (a fallback when it stands on the target), rnd = 0..1 (random).
function blinkLanding(b, from, target, tface, facing, rnd) {
  var lx = target[0] - from[0], ly = target[1] - from[1], d = Math.hypot(lx, ly), ux, uy, dx, dy;
  if (d > 0.001) { ux = lx / d; uy = ly / d; } else { ux = facing < 0 ? -1 : 1; uy = 0; }
  if (b.direction === "toward") { dx = ux; dy = uy; }
  else if (b.direction === "away") { dx = -ux; dy = -uy; }
  else if (b.direction === "behind" || b.direction === "front") {
    if (tface == null) { dx = ux; dy = uy; } else { dx = tface < 0 ? 1 : -1; dy = 0; }
    if (b.direction === "front") { dx = -dx; dy = -dy; }
  } else if (b.direction === "random") { var r = rnd * 2 * Math.PI; dx = Math.cos(r); dy = Math.sin(r); }
  else { var a = Math.atan2(uy, ux) + (+b.angle_deg || 0) * D; dx = Math.cos(a); dy = Math.sin(a); }
  var an = b.anchor === "target" ? target : from, prox = Math.max(0, +b.proximity_px || 0);
  return [an[0] + dx * prox, an[1] + dy * prox];
}
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
  particles: ["speed_min", "speed_max", "gravity", "size_min", "size_max"], glow: ["r_start", "r_end", "core_r"],
  pulse: ["r_start", "r_end", "width", "width_end", "glow"], ghost: [], weapon: ["width"]};
var SCALE_MOTION = ["speed", "amplitude", "orbit_rx", "orbit_ry"];
var SCALE_INTERCEPT = ["radius", "contact"];
function rescaleEffects(effects, lib, r) {
  if (Math.abs(r - 1) < 1e-6) return;
  effects.forEach(function (fx) {
    var off = fx.offset || [0, 0]; fx.offset = [(+off[0] || 0) * r, (+off[1] || 0) * r];
    var m = fx.motion || {}; SCALE_MOTION.forEach(function (k) { if (typeof m[k] === "number") m[k] *= r; });
    var P = fx.params || {}; (SCALE_PARAMS[fx.prim] || []).forEach(function (k) { if (typeof P[k] === "number") P[k] *= r; });
    var I = fx.intercept || {}; SCALE_INTERCEPT.forEach(function (k) { if (typeof I[k] === "number") I[k] *= r; });
    var scaled = ["offset.0", "offset.1"].concat(SCALE_MOTION.map(function (k) { return "motion." + k; }),
      (SCALE_PARAMS[fx.prim] || []).map(function (k) { return "params." + k; }), SCALE_INTERCEPT.map(function (k) { return "intercept." + k; }));
    (fx.keys || []).forEach(function (key) { scaled.forEach(function (p) { if (typeof key.set[p] === "number") key.set[p] *= r; }); });
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
  cfg.blink = normalizeBlink(cfg.blink);
  cfg.conditions = (cfg.conditions || []).filter(function (c) { return c && CONDITION_TYPES[c.type]; })
    .map(function (c) { return fill(fill(c, CONDITION_TYPES[c.type]), CONDITION_COMMON); });
  return cfg;
}
// fx.always_on (∞ Always on): the effect never stops producing while its
// action plays, loop after loop (a laser trail that is always on).  One
// instance is kept alive with no end (it restarts only if something ends it,
// e.g. a non-piercing hit, or the action restarts after a key launched it);
// End frame / Life ticks / Emit every are ignored and it does not fade out.
// Only for effects that stay on the fighter (attached, static or orbit
// motion) and are not arcs.
function canContinue(fx) {
  return fx.prim !== "arc" && ["attached", "static", "orbit", "path"].indexOf(fx.motion.kind) >= 0;
}
function isAlwaysOn(fx) { return !!fx.always_on && canContinue(fx); }
// fx.continuous (⟳ Continuous): the effect plays its whole sequence through,
// exactly as authored (start / end frame, Emit every, count, fan, entry
// points, Life ticks, keys, any motion), on its own clock: it carries on to
// the end when the action ends early, changes or restarts.  Each time the
// action reaches the start frame a run starts; replaying the action starts
// another alongside (at most CYCLE_MAX_RUNS per effect; the oldest stops).
// A run lasts its sequence: start frame -> end frame, or the first copy's
// Life ticks if that is longer.  fx.cycles {enabled, count} then replays the
// whole sequence: count -1 = forever, 0 = once, N = N more times.
var CYCLE_DEFAULTS = {enabled: false, count: 0};
var CYCLE_MAX_RUNS = 8;
function isContinuous(fx) { return !!fx.continuous; }
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
  // Files from before ∞ Always on was split out (no always_on, no cycles):
  // their continuous meant always on.
  if (fx.always_on === undefined && fx.cycles === undefined && fx.continuous) { fx.always_on = true; fx.continuous = false; }
  fill(fx, {name: fx.prim, tag: "", enabled: true, start_frame: 0, end_frame: -1, life_ticks: 0, continuous: false, always_on: false,
    anchor: "figure", offset: [0, 0], layer: "front", blend: "normal"});
  fx.emit = fill(fx.emit || {}, {every_ticks: 0, count: 1, fan_deg: 0});
  fx.cycles = fill(fx.cycles || {}, CYCLE_DEFAULTS);
  fx.motion = fill(fx.motion || {}, MOTION_DEFAULTS);
  fx.color = fill(fx.color || {}, COLOR_DEFAULTS);
  fx.params = fill(fx.params || {}, PARAM_DEFAULTS[fx.prim]);
  fx.battle = fill(fx.battle || {}, BATTLE_DEFAULTS);
  fx.intercept = fill(fx.intercept || {}, INTERCEPT_DEFAULTS);
  fx.flip = fill(fx.flip || {}, FLIP_DEFAULTS);
  fx.flip.facing = +fx.flip.facing < 0 ? -1 : 1;
  fx.follow_dir = !!fx.follow_dir;
  fx.follow_each = !!fx.follow_each;
  if (fx.prim === "ghost") fx.battle.deals_damage = false;   // afterimages are visual only
  if (fx.prim === "weapon") fx.motion.kind = "attached";      // a hitbox rides its anchors
  normalizeKeys(fx);
  return fx;
}

// ---------------------------------------------------------------- keyframes
// fx.keys = [{frame, ease, set: {"motion.speed": 100, "color.c1": "#ff0000", ...}}]
// sorted by frame.  The effect's own settings are its values at its start
// frame; each key sets new values for the settings it lists, and every such
// setting moves from the previous point that set it (the start, or an earlier
// key) to this key along the key's ease.  After its last key a setting holds.
// Keyable: number settings and custom colours (#rrggbb) in params, motion,
// emit, color, battle and intercept, plus offset.0 / offset.1 and life_ticks.
// Live instances sample the effect at their own action time (the tick they
// spawned + their age), so a shot already flying follows the animation.
// Mirrored by laser/fxkit.py (fx_at / ease).
var EASES = ["linear", "in", "out", "inout", "strong_in", "strong_out", "strong_inout", "hold", "bounce", "elastic"];
var KEY_GROUPS = ["params", "motion", "emit", "color", "battle", "intercept"];
function bounceOut(u) {
  var n = 7.5625, d = 2.75;
  if (u < 1 / d) return n * u * u;
  if (u < 2 / d) { u -= 1.5 / d; return n * u * u + 0.75; }
  if (u < 2.5 / d) { u -= 2.25 / d; return n * u * u + 0.9375; }
  u -= 2.625 / d; return n * u * u + 0.984375;
}
function ease(name, u) {
  u = Math.max(0, Math.min(1, u));
  switch (name) {
    case "linear": return u;
    case "in": return u * u;
    case "out": return 1 - (1 - u) * (1 - u);
    case "strong_in": return u * u * u * u;
    case "strong_out": return 1 - Math.pow(1 - u, 4);
    case "strong_inout": return u < 0.5 ? 8 * u * u * u * u : 1 - Math.pow(-2 * u + 2, 4) / 2;
    case "hold": return u < 1 ? 0 : 1;
    case "bounce": return bounceOut(u);
    case "elastic": return u <= 0 ? 0 : u >= 1 ? 1 : Math.pow(2, -10 * u) * Math.sin((u * 10 - 0.75) * (2 * Math.PI / 3)) + 1;
    default: return u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2;   // inout
  }
}
function keyableValue(v) { return (typeof v === "number" && isFinite(v)) || (typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v)); }
// Choice settings keys can switch: the value holds until the next key (no
// in-between), and instances already alive switch with it (motionSwitch):
// an orbit keyed to travel launches from where it is.
var KEY_CHOICES = {"motion.kind": ["attached", "static", "orbit", "travel", "homing", "zigzag"],
  "motion.aim": ["target", "facing", "angle", "weapon"], "motion.orbit_dir": ["clockwise", "anticlockwise"]};
function keyableAt(path, v) { return keyableValue(v) || (KEY_CHOICES[path] ? KEY_CHOICES[path].indexOf(v) >= 0 : false); }
function getPath(fx, path) {
  var i = path.indexOf("."), a = i < 0 ? path : path.slice(0, i), b = i < 0 ? null : path.slice(i + 1);
  var o = fx[a];
  return b == null ? o : (o && o[b]);
}
// Every keyable setting of fx: [path, ...].
function keyPaths(fx) {
  var out = [];
  KEY_GROUPS.forEach(function (g) { var o = fx[g] || {}; Object.keys(o).forEach(function (k) {
    if (keyableAt(g + "." + k, o[k]) && !(fx.prim === "weapon" && g === "motion")) out.push(g + "." + k); }); });
  out.push("offset.0", "offset.1", "life_ticks");
  return out;
}
function isKeyable(fx, path) { return keyPaths(fx).indexOf(path) >= 0; }
function normalizeKeys(fx) {
  fx.keys = (Array.isArray(fx.keys) ? fx.keys : []).filter(function (k) { return k && typeof k.set === "object"; }).map(function (k) {
    var set = {};
    Object.keys(k.set || {}).forEach(function (p) { if (keyableAt(p, k.set[p])) set[p] = k.set[p]; });
    return {frame: Math.max(0, Math.round(+k.frame || 0)), ease: EASES.indexOf(k.ease) >= 0 ? k.ease : "inout", set: set};
  }).sort(function (a, b) { return a.frame - b.frame; });
  return fx;
}
function hexLerp(a, b, u) {
  var A = hexRgb(a, [255, 255, 255]), B = hexRgb(b, [255, 255, 255]);
  return "#" + [0, 1, 2].map(function (i) { var v = Math.round(Math.max(0, Math.min(255, A[i] + (B[i] - A[i]) * u))); return (v < 16 ? "0" : "") + v.toString(16); }).join("");
}
function lerpVal(a, b, u) {
  if (typeof a === "number" && typeof b === "number") return a + (b - a) * u;
  if (keyableValue(a) && keyableValue(b) && typeof a === "string" && typeof b === "string") return hexLerp(a, b, u);
  return u < 1 ? a : b;   // choices hold until the key
}
// The value of one setting at action frame tf (fractional).
function sampleKey(fx, path, tf) {
  var pts = [[Math.max(0, fx.start_frame || 0), getPath(fx, path), "linear"]];
  (fx.keys || []).forEach(function (k) { if (path in k.set) pts.push([k.frame, k.set[path], k.ease]); });
  pts.sort(function (a, b) { return a[0] - b[0]; });
  if (tf <= pts[0][0]) return pts[0][1];
  for (var i = 0; i + 1 < pts.length; i++) {
    var p0 = pts[i], p1 = pts[i + 1];
    if (tf < p1[0]) return lerpVal(p0[1], p1[1], p1[0] > p0[0] ? ease(p1[2], (tf - p0[0]) / (p1[0] - p0[0])) : 1);
  }
  return pts[pts.length - 1][1];
}
// fx with every keyed setting at its value at action frame tf (fx itself when it has no keys).
function fxAt(fx, tf) {
  if (!fx.keys || !fx.keys.length) return fx;
  var v = {};
  for (var k in fx) v[k] = fx[k];
  KEY_GROUPS.forEach(function (g) { var o = {}, src = fx[g] || {}; for (var q in src) o[q] = src[q]; v[g] = o; });
  v.offset = (fx.offset || [0, 0]).slice();
  var done = {};
  fx.keys.forEach(function (key) {
    Object.keys(key.set).forEach(function (path) {
      if (done[path]) return; done[path] = 1;
      var val = sampleKey(fx, path, tf), i = path.indexOf(".");
      if (i < 0) v[path] = val;
      else if (path.slice(0, i) === "offset") v.offset[+path.slice(i + 1)] = val;
      else v[path.slice(0, i)][path.slice(i + 1)] = val;
    });
  });
  return v;
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
  var m = fx.motion, f = fxFacing(fx, host), dx, dy;
  if (m.aim === "target") return norm(host.target[0] - x, host.target[1] - y);   // tracks the target, never turned
  if (m.aim === "angle") { dx = Math.cos(m.angle_deg * D) * f; dy = Math.sin(m.angle_deg * D); }
  else if (m.aim === "weapon") { dx = Math.sin(host.wang * D) * f; dy = -Math.cos(host.wang * D); }
  else { dx = f; dy = 0; }
  return turnBy([dx, dy], bodyDeg(fx, host, [x, y]));
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
// start_frame / stop_frame: the action frames the set produces particles in
// (stop -1 = to the end); what it already spawned lives on as usual.
// order (sequential): forward, reverse, pingpong (1..n..1) or random (seeded).
var ENTRY_DEFAULTS = {name: "entry points", base: "figure", mode: "simultaneous", interval_ticks: 6, points: [],
  start_frame: 0, stop_frame: -1, order: "forward"};
var ENTRY_ORDERS = ["forward", "reverse", "pingpong", "random"];
var PATH_DEFAULTS = {name: "path", points: [[0, 0]], smooth: true, ticks: 30, orient: "facing", end: "stop", follow: false};
function normalizeEntrySet(e) {
  e = fill(e || {}, ENTRY_DEFAULTS); e.points = (e.points || []).map(function (p) { return [+p[0] || 0, +p[1] || 0]; });
  e.start_frame = Math.max(0, Math.round(+e.start_frame || 0));
  e.stop_frame = Math.max(-1, Math.round(e.stop_frame == null ? -1 : +e.stop_frame));
  if (ENTRY_ORDERS.indexOf(e.order) < 0) e.order = "forward";
  return e;
}
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
// Figure size (laser/fxkit.py host_scale): every FX distance is authored at
// pscale 1 and multiplied by the figure's on-screen size like widths and
// radii.  Placement around the body follows the current size; what is
// launched (shot speed, zigzag sway, particle speed / gravity, intercept
// range) keeps the size it was fired at (inst.ps).
function hostScale(host) { return +(host && host.pscale) || 1; }
function entrySetOf(fx, host) {
  if (typeof fx.anchor !== "string" || fx.anchor.indexOf("set:") !== 0) return null;
  var e = libFind(host, "entry_sets", fx.anchor.slice(4));
  return e && e.points.length ? e : null;
}
function entryPoint(set, k, host, deg, f) {
  var b = host.anchor(set.base || "figure"), q = set.points[k] || [0, 0], ps = hostScale(host), o = turnBy([q[0] * ps * (f || host.facing), q[1] * ps], deg);
  return [b[0] + o[0], b[1] + o[1]];
}
function anchorPos(fx, host, inst) {
  var a, set = entrySetOf(fx, host), deg = placeDeg(fx, host), f = fxFacing(fx, host);
  if (set) a = entryPoint(set, inst && inst.ep != null ? inst.ep % set.points.length : 0, host, deg, f);
  else if (typeof fx.anchor === "string" && fx.anchor.indexOf("set:") === 0) a = host.anchor("figure");   // empty / missing set
  else a = host.anchor(fx.anchor);
  var ps = hostScale(host), o = turnBy([(+fx.offset[0] || 0) * ps * f, (+fx.offset[1] || 0) * ps], deg);
  return [a[0] + o[0], a[1] + o[1]];
}
// Orbit position around centre c (flip mirrors its side and spin).
function orbitPos(inst, host, c) {
  var m = inst.fx.motion, ps = hostScale(host), o = turnBy([Math.cos(inst.orbitA * D) * m.orbit_rx * ps * inst.flip, Math.sin(inst.orbitA * D) * m.orbit_ry * ps], bodyDeg(inst.fx, host, c));
  return [c[0] + o[0], c[1] + o[1]];
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
// turn the start→end line onto the aim direction, else turn it by `deg`
// (Follow direction's body turn).
function pathMatrix(path, host, dir, deg) {
  var f = host.facing, P = path.points, last = P[P.length - 1];
  if (path.orient !== "aim" || (!last[0] && !last[1])) {
    if (!deg) return [f, 0, 0, 1];
    var c0 = Math.cos(deg * D), s0 = Math.sin(deg * D);
    return [c0 * f, -s0, s0 * f, c0];
  }
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
  var ps = hostScale(host); local = [local[0] * ps, local[1] * ps];
  var w = pathWorld(inst, local), M = inst.pm;
  inst.x = w[0]; inst.y = w[1];
  var wd = norm(M[0] * ld[0] + M[1] * ld[1], M[2] * ld[0] + M[3] * ld[1]);
  if (wd[0] || wd[1]) inst.dir = wd;
}

function spawn(fx, host, windowTicks, seed, idx, n, ep) {
  var p = anchorPos(fx, host, {ep: ep}), m = fx.motion, ef = fxFacing(fx, host);
  var dir = aimDir(fx, host, p[0], p[1]), ts = turnSign(fx, host, dir, p);
  if (n > 1 && fx.emit.fan_deg) dir = rot(dir, (-fx.emit.fan_deg / 2 + fx.emit.fan_deg * idx / (n - 1)) * ts);
  if (m.aim_offset_deg) dir = rot(dir, m.aim_offset_deg * ts);
  var life = fx.life_ticks > 0 ? fx.life_ticks : Math.max(1, windowTicks);
  var inst = {fx: fx, x: p[0], y: p[1], px: p[0], py: p[1], vx: 0, vy: 0, dir: dir, age: 0, life: life,
    seed: seed >>> 0, r: rng(seed), flow: 0, ended: false, dead: false, hist: [], trail: [], parts: [],
    ghosts: [], acc: 0, facing: ef, flip: flipSign(fx, ef), orbitA: 0, phase: 0, zx: 0, zy: 0,
    hits: 0, lastHit: -1e9, ep: ep == null ? null : ep, ps: hostScale(host), tgt: aimTarget(fx, host)};
  var ps = inst.ps;   // the figure's size when fired: what is launched keeps it
  // Arc / zigzag side of its line: flipped with the facing, kept up / down.
  inst.side = inst.flip * ts * ef;
  var spd = +m.speed || 0;
  inst.spd = spd;   // keyframed speed: moveInst rescales the velocity when it changes
  if (m.kind === "path") {
    inst.path = libFind(host, "paths", m.path);
    if (inst.path) { inst.pl = pathLine(inst.path); inst.po = p.slice(); inst.pm = pathMatrix(inst.path, {facing: ef}, dir, bodyDeg(fx, host, p)); }
  }
  if (m.kind === "travel" || m.kind === "homing" || m.kind === "zigzag") { inst.vx = dir[0] * spd * ps; inst.vy = dir[1] * spd * ps; }
  if (m.kind === "zigzag") {   // ZigzagProjectile.__init__
    var pr = spd > 0.001 ? [-dir[1] * inst.side, dir[0] * inst.side] : [0, inst.side];
    inst.zx = pr[0] * m.amplitude * ps; inst.zy = pr[1] * m.amplitude * ps;
    inst.phase = n > 1 ? Math.PI * idx : 0;
  }
  if (m.kind === "orbit") {
    inst.orbitA = 360 * idx / Math.max(1, n);
    var op = orbitPos(inst, host, p); inst.x = op[0]; inst.y = op[1];
  }
  if (fx.prim === "arc") {
    // CrescentWave: centre angle perpendicular to the direction of travel.
    var od = fx.params.orient === "angle" ? turnBy([Math.cos(fx.params.angle_deg * D) * ef, Math.sin(fx.params.angle_deg * D)], bodyDeg(fx, host, p)) : dir;
    // Which side of its line the crescent sits (inst.side, see turnSign).
    var sd = fx.params.orient === "angle" ? inst.flip : inst.side;
    inst.centreDeg = angleDegQt(-od[1] * sd, od[0] * sd);
    // CrescentWave.__init__ placements relative to the target (the aim
    // direction runs from the anchor to the target):
    //   wrap_target    centre = target - dir * back           (default slash, back 51)
    //   through_target centre = target + R*(dir_y, -dir_x) - dir * lead
    //                  so the arc's midpoint starts `lead` short of the target
    var tg = host.target, P = fx.params;
    if (P.placement === "wrap_target") { inst.x = tg[0] - od[0] * P.back * ps; inst.y = tg[1] - od[1] * P.back * ps; }
    else if (P.placement === "through_target") {
      var R = P.radius * ps;
      var Rf = R * sd;
      inst.x = tg[0] + od[1] * Rf - od[0] * P.lead * ps; inst.y = tg[1] - od[0] * Rf - od[1] * P.lead * ps;
    }
  }
  if (fx.prim === "particles" && fx.params.mode === "burst") emitParticles(inst, fx, host, trunc(fx.params.count));
  if (fx.prim === "weapon") { var e2 = host.anchor(fx.params.to_anchor); inst.x2 = e2[0]; inst.y2 = e2[1]; }
  if (fx.prim === "pulse") inst.ringHits = {};   // "ring" -> true: each ring hits once
  inst.px = inst.x; inst.py = inst.y;
  inst.mk = m.kind; inst.ma = m.aim;   // keyed switches compare against these (motionSwitch)
  return inst;
}

function moveInst(inst, host) {
  var fx = inst.fx, m = fx.motion;
  inst.px = inst.x; inst.py = inst.y;
  inst.tgt = aimTarget(fx, host);
  if (m.kind === "attached") { var a = anchorPos(fx, host, inst); inst.x = a[0]; inst.y = a[1]; }
  if (m.kind === "path" && inst.path) {
    pathStep(inst, host);
    inst.vx = inst.x - inst.px; inst.vy = inst.y - inst.py;   // beams / trails read the travel speed
    return;
  }
  if ((m.kind === "travel" || m.kind === "homing" || m.kind === "zigzag") && !inst.free) {
    // Keyframed speed: an instance in flight follows it (its direction is kept).
    var ns = +m.speed || 0;
    if (ns !== inst.spd) {
      var cs = Math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy);
      if (cs > 1e-6 && inst.spd > 1e-6) { var f = ns / inst.spd; inst.vx *= f; inst.vy *= f; }
      else { inst.vx = inst.dir[0] * ns * (inst.ps || 1); inst.vy = inst.dir[1] * ns * (inst.ps || 1); }
      inst.spd = ns;
    }
  }
  if (fx.prim === "weapon") { var b2 = host.anchor(fx.params.to_anchor); inst.x2 = b2[0]; inst.y2 = b2[1]; }
  else if (m.kind === "travel") { inst.x += inst.vx; inst.y += inst.vy; }
  else if (m.kind === "homing") {
    var spd = Math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy) || (+m.speed || 0) * (inst.ps || 1);
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
    inst.orbitA += orbitStep(m);
    var op2 = orbitPos(inst, host, c); inst.x = op2[0]; inst.y = op2[1];
  }
  if (m.kind === "travel" || m.kind === "homing" || m.kind === "zigzag") {
    var mdx = inst.x - inst.px, mdy = inst.y - inst.py;
    if (mdx * mdx + mdy * mdy > 1e-6) inst.dir = norm(mdx, mdy);
  } else if (fx.prim === "beam") {
    // A held beam keeps re-aiming (at the target, the facing, the fixed
    // angle or the weapon) while its anchor moves.
    var d = aimDir(fx, host, inst.x, inst.y);
    inst.dir = m.aim_offset_deg ? rot(d, m.aim_offset_deg * turnSign(fx, host, d, [inst.x, inst.y])) : d;
  }
}

function emitParticles(inst, fx, host, n) {
  // combat._spawn_burst_now: fan around angle_deg, mirrored with the effect's facing (fxFacing).
  var P = fx.params, cp = colorPair(fx, host.lut);
  var spread = P.spread_deg * D, base = P.angle_deg * D;
  if (inst.facing < 0) base = Math.PI - base;
  base += bodyDeg(fx, host, [inst.x, inst.y]) * D;   // Follow direction / Each particle: turns toward the target
  var ips = inst.ps || 1, smin = +P.speed_min * ips, smax = Math.max(smin, +P.speed_max * ips);
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

// ---------------------------------------------------------------- intercept
// The auto-projectile tracker (fx.intercept, see INTERCEPT_DEFAULTS).
// host.shots: the enemy's live projectiles [{x, y, vx, vy, dead}], read-only
// except `dead`, which marks one already taken this tick.  In the game a shot
// also carries clash / knockback (the enemy effect's intercept mode and
// battle.knockback; bullets: no clash, knockback 0).
// host.onIntercept(inst, shot, mode, enemyVel, hurtsOwner): the host applies
// the result to the enemy projectile at its source (nullify, or send it off
// at enemyVel for a deflect; "clash_lock" leaves it).  laser/fxkit.py
// intercept_step mirrors this.
//
// Clash: an effect WITHOUT clash always loses to one with it — the clash
// projectile nullifies any non-clash projectile it touches, and a non-clash
// interceptor touching an enemy clash projectile is the one nullified.  Two
// clash projectiles compare knockback: more than CLASH_KB_MARGIN apart, the
// higher one nullifies the lower and keeps going; otherwise both freeze
// where they met until one's life runs out or its owner is hit, and the
// survivor then resumes the motion it had before the clash.
var DEFLECT_FAN_DEG = 15;   // with deflect "both", the two fly apart this far either side
var CLASH_KB_MARGIN = 10;
function canIntercept(fx) {
  return fx.prim !== "weapon" && fx.prim !== "ghost" && fx.prim !== "pulse" && ["travel", "homing", "zigzag"].indexOf(fx.motion.kind) >= 0;
}
function interceptOn(fx) { return !!(fx.intercept && fx.intercept.enabled) && canIntercept(fx); }
function clashOn(fx) { return interceptOn(fx) && fx.intercept.mode === "clash"; }
function fxKnockback(fx) { return +((fx.battle || {}).knockback) || 0; }
// Whether an intercept in `mode` may take shot s: clash takes anything; the
// others never go after a clash shot (they would lose to it); deflect needs a
// deflectable shot, block / destroy a blockable one (shots without the flags,
// e.g. built-in bullets, are both).
function shotTakes(s, mode) {
  if (mode === "clash") return true;
  if (s.clash) return false;
  return mode === "deflect" ? s.deflectable !== false : s.blockable !== false;
}
function shotGone(s) { return s.kind === "fx" && s.ref && (s.ref.dead || s.ref.age >= s.ref.life); }
function nearestShot(inst, host, r, mode, onlyClash) {
  var best = null, bd = 0, shots = host.shots || [], r2 = r * r;
  for (var i = 0; i < shots.length; i++) {
    var s = shots[i]; if (s.dead || shotGone(s)) continue;
    if (onlyClash ? !s.clash : (mode && !shotTakes(s, mode))) continue;
    var dx = s.x - inst.x, dy = s.y - inst.y, d = dx * dx + dy * dy;
    if (d <= r2 && (best === null || d < bd)) { best = s; bd = d; }
  }
  return best;
}
// Deflect: the new direction is the two velocities added together (their
// combined momentum).  Head-on at similar speeds they nearly cancel, so the
// enemy projectile is knocked sideways instead, to the side it hit on.
function deflectVels(inst, s, both) {
  var si = Math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy), ss = Math.sqrt(s.vx * s.vx + s.vy * s.vy);
  var sx = inst.vx + s.vx, sy = inst.vy + s.vy, sm = Math.sqrt(sx * sx + sy * sy);
  var side = inst.vx * (s.y - inst.y) - inst.vy * (s.x - inst.x) >= 0 ? 1 : -1;
  var dir = sm >= 0.25 * Math.max(si, ss, 0.001) ? [sx / sm, sy / sm] : rot(norm(inst.vx, inst.vy), 90 * side);
  var de = both ? rot(dir, DEFLECT_FAN_DEG * side) : dir, dm = rot(dir, -DEFLECT_FAN_DEG * side);
  return {enemy: [de[0] * ss, de[1] * ss], mine: [dm[0] * si, dm[1] * si]};
}
function straightStep(inst) {
  inst.px = inst.x; inst.py = inst.y;
  inst.x += inst.vx; inst.y += inst.vy;
  var mdx = inst.x - inst.px, mdy = inst.y - inst.py;
  if (mdx * mdx + mdy * mdy > 1e-6) inst.dir = norm(mdx, mdy);
}
function endChase(inst) { if (inst.chase) { inst.chase = false; inst.vx = inst.bvx; inst.vy = inst.bvy; } }
function clashLock(inst) { endChase(inst); inst.cvx = inst.vx; inst.cvy = inst.vy; inst.px = inst.x; inst.py = inst.y; }
// While locked: hold still until the partner ends, then resume.  True while held.
function clashHold(inst) {
  var q = inst.clashWith;
  if (!(q.dead || q.age >= q.life || q.clashWith !== inst)) { inst.px = inst.x; inst.py = inst.y; return true; }
  inst.clashWith = null; inst.vx = inst.cvx; inst.vy = inst.cvy;
  return false;
}
// inst (clash mode) touched shot hit: "lost" (inst nullified), "locked", or null (hit nullified).
function clashContact(inst, hit, host) {
  if (hit.clash) {
    var diff = fxKnockback(inst.fx) - (+hit.knockback || 0);
    if (diff < -CLASH_KB_MARGIN) { inst.age = Math.max(inst.age, inst.life); return "lost"; }
    if (diff <= CLASH_KB_MARGIN) {
      var q = hit.ref; clashLock(inst); clashLock(q); inst.clashWith = q; q.clashWith = inst;
      if (host.onIntercept) host.onIntercept(inst, hit, "clash_lock", null, false);
      return "locked";
    }
  }
  if (host.onIntercept) host.onIntercept(inst, hit, "clash", null, false);
  return null;
}
// Runs before the instance moves; true when it moved the instance itself.
function interceptStep(inst, host) {
  if (inst.clashWith && clashHold(inst)) return true;
  if (inst.free) { straightStep(inst); return true; }   // deflected: flies straight on
  var fx = inst.fx;
  if (!interceptOn(fx)) return false;
  var I = fx.intercept, ips = inst.ps || 1, contact = Math.max(0, +I.contact || 0) * ips;
  if (I.mode !== "clash" && nearestShot(inst, host, contact, null, true)) {   // loses to a clash projectile
    inst.age = Math.max(inst.age, inst.life); return true;
  }
  var hit = nearestShot(inst, host, contact, I.mode);
  if (hit) {
    hit.dead = true;
    endChase(inst);
    if (I.mode === "clash") {
      if (clashContact(inst, hit, host) !== null) return true;
    } else if (I.mode === "deflect") {
      var both = I.deflect_who === "both", v = deflectVels(inst, hit, both);
      if (host.onIntercept) host.onIntercept(inst, hit, "deflect", v.enemy, !!I.hurts_owner);
      if (both) { inst.vx = v.mine[0]; inst.vy = v.mine[1]; inst.free = true; straightStep(inst); return true; }
    } else {
      if (host.onIntercept) host.onIntercept(inst, hit, I.mode, null, false);
      if (I.mode === "block") { inst.age = Math.max(inst.age, inst.life); return true; }
    }
  }
  var tgt = nearestShot(inst, host, Math.max(0, +I.radius || 0) * ips, I.mode);
  if (!tgt) { endChase(inst); return false; }   // back to its own motion
  if (!inst.chase) { inst.chase = true; inst.bvx = inst.vx; inst.bvy = inst.vy; }
  var spd = Math.sqrt(inst.vx * inst.vx + inst.vy * inst.vy) || (+fx.motion.speed || 0) * ips;
  var want = Math.atan2(tgt.y - inst.y, tgt.x - inst.x), cur = Math.atan2(inst.vy, inst.vx), dA = want - cur;
  while (dA > Math.PI) dA -= 2 * Math.PI;
  while (dA < -Math.PI) dA += 2 * Math.PI;
  var lim = (+I.turn_deg || 0) * D;
  cur += Math.max(-lim, Math.min(lim, dA));
  inst.vx = Math.cos(cur) * spd; inst.vy = Math.sin(cur) * spd;
  straightStep(inst);
  return true;
}

function tickInst(inst, host) {
  var fx = inst.fx, P = fx.params;
  var active = inst.age < inst.life;
  if (active && inst.lodge) bladeFollow(inst, host.hurt ? [[host.hurt.x, host.hurt.y]] : [], inst.ps || 1);
  else if (active) {
    if (fx.prim === "sprite" || fx.prim === "beam") { inst.trail.push([inst.x, inst.y]); if (inst.trail.length > Math.max(0, trunc(P.trail_len || 0))) inst.trail.shift(); }
    if (!interceptStep(inst, host)) moveInst(inst, host);
  }
  inst.flow = (inst.flow + (+fx.color.flow_speed || 0)) % 1;
  if (fx.prim === "ribbon") {   // TrailComponent.update (path_follow = False)
    var h = inst.hist;
    if (active) {
      var moved = true;
      if (h.length) { var l = h[h.length - 1], dx = inst.x - l[0], dy = inst.y - l[1]; var md = P.min_dist * hostScale(host); moved = dx * dx + dy * dy >= md * md; }
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
      q.vx *= drag; q.vy = q.vy * drag + P.gravity * (inst.ps || 1) * TICK_S;
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
  } else if (fx.prim === "pulse") {
    if (!active && !pulseRings(inst, inst.ps || 1).length) inst.dead = true;   // expanding rings finish
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
    // Flipped: the sweep grows the other way round (mirror image).
    out.push([inst.flip < 0 ? inst.centreDeg + half - (i + 1) * step : start + i * step, step, P.width * (0.25 + 0.75 * tt) * ps, tt, a, st]);
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
// Beam geometry shared by draw and hit test: [[x0,y0,x1,y1,width,rgb,alpha], ...]
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
    reach = P.length * ps * (P.grow_ticks > 0 ? Math.min(1, inst.age / P.grow_ticks) : 1);
    hx = inst.x + ux * reach; hy = inst.y + uy * reach;
  } else {
    var dist = spd * inst.age;
    if (inst.age < detach) reach = Math.min(P.length * ps, dist);
    else {
      var rd = Math.min(P.length * ps, spd * detach), post = Math.max(1, inst.life - detach);
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
  var tf = Math.max(0, Math.min(1, +P.tip_fade || 0));   // fraction of the length, from the head, that fades out
  for (var i = 0; i < segs; i++) {
    var t0 = i / segs, t1 = (i + 1) / segs;
    var x0 = hx - ux * reach * t0, y0 = hy - uy * reach * t0, x1 = hx - ux * reach * t1, y1 = hy - uy * reach * t1;
    if (P.jitter > 0) { var j = (jr() * 2 - 1) * P.jitter * ps; x0 += -uy * j; y0 += ux * j; x1 += -uy * j; y1 += ux * j; }
    out.push([x0, y0, x1, y1, (wH + (wT - wH) * t0) * ps,
      [c2[0] + (c1[0] - c2[0]) * t0, c2[1] + (c1[1] - c2[1]) * t0, c2[2] + (c1[2] - c2[2]) * t0],
      tf > 0 ? Math.min(1, (t0 + t1) / 2 / tf) : 1]);
  }
  // Smooth-draw info for straight beams: head and tail points, widths, colours, tip fade.
  return {segs: out, am: fade * pulse, hx: hx, hy: hy, tx: hx - ux * reach, ty: hy - uy * reach,
          wH: wH * ps, wT: wT * ps, c1: c1, c2: c2, tf: tf};
}
// A straight multi-segment beam (no jitter) is drawn as one tapered capsule filled
// with a smooth gradient along its length (colour c2 at the head to c1 at the tail,
// tip_fade alpha), so it has no joints, seams or width steps.  Jittered and
// single-segment beams stroke their segments with round caps as before.
function beamCapsule(b, wHead, wTail) {
  var ah = Math.atan2(b.hy - b.ty, b.hx - b.tx), pts = [], k, a;
  for (k = 0; k <= 12; k++) { a = ah + Math.PI + (k / 12 - 0.5) * Math.PI; pts.push([b.tx + Math.cos(a) * wTail / 2, b.ty + Math.sin(a) * wTail / 2]); }
  for (k = 0; k <= 12; k++) { a = ah + (k / 12 - 0.5) * Math.PI; pts.push([b.hx + Math.cos(a) * wHead / 2, b.hy + Math.sin(a) * wHead / 2]); }
  return pts;
}
function beamStops(b, colAt, a) {   // [t from head, rgb, alpha]
  var ts = [0, 1];
  if (b.tf > 0 && b.tf < 1) ts.splice(1, 0, b.tf);
  return ts.map(function (t) { return [t, colAt(t), a * (b.tf > 0 ? Math.min(1, t / b.tf) : 1)]; });
}
DRAW.beam = function (g, inst, host, ps) {   // RichBeamProjectile.draw
  var P = inst.fx.params, b = beamSegs(inst, host, ps);
  if (!b) return;
  var gc = P.glow_color ? hexRgb(P.glow_color, null) : null;
  if (b.segs.length > 1 && !(P.jitter > 0)) {
    var colAt = function (t) { return [b.c2[0] + (b.c1[0] - b.c2[0]) * t, b.c2[1] + (b.c1[1] - b.c2[1]) * t, b.c2[2] + (b.c1[2] - b.c2[2]) * t]; };
    var fill = function (cAt, a, wHead, wTail) {
      var gr = g.createLinearGradient(b.hx, b.hy, b.tx, b.ty);
      beamStops(b, cAt, a).forEach(function (s) { gr.addColorStop(s[0], rgba(s[1], s[2])); });
      var pts = beamCapsule(b, wHead, wTail);
      g.fillStyle = gr; g.beginPath(); g.moveTo(pts[0][0], pts[0][1]);
      for (var i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]);
      g.closePath(); g.fill();
    };
    if (P.glow > 0) fill(gc ? function () { return gc; } : function (t) { return colAt(t).map(trunc); }, 70 * b.am, b.wH + P.glow * ps, b.wT + P.glow * ps);
    fill(colAt, 235 * b.am, Math.max(1, b.wH), Math.max(1, b.wT));
    return;
  }
  g.lineCap = "round";
  b.segs.forEach(function (q) {
    var w = q[4], col = q[5];
    if (P.glow > 0) { g.strokeStyle = rgba(gc || col.map(trunc), 70 * b.am * q[6]); g.lineWidth = w + P.glow * ps; line(g, q[0], q[1], q[2], q[3]); }
    g.strokeStyle = rgba(col, 235 * b.am * q[6]); g.lineWidth = Math.max(1, w); line(g, q[0], q[1], q[2], q[3]);
  });
};
DRAW.sprite = function (g, inst, host, ps) {   // Projectile.draw
  var fx = inst.fx, P = fx.params, fade = P.fade ? Math.max(0, 1 - inst.age / inst.life) : 1;
  if (inst.age >= inst.life) return;
  if (inst.lodge) { drawLodged(g, inst, host, ps); return; }
  var c = colorPair(fx, host.lut)[0].map(trunc), hx = trunc(inst.x), hy = trunc(inst.y), bp = null;
  if (P.shape === "blade") { bp = bladePose(inst, ps); hx = trunc(bp[0]); hy = trunc(bp[1]); }   // Each in place turns it on its own centre
  var pts = inst.trail, n = pts.length;
  g.lineCap = "round";
  for (var i = 1; i < n; i++) {
    var t = i / n;
    g.strokeStyle = rgba(c, 200 * t * fade); g.lineWidth = (1 + 2 * t) * ps;
    line(g, pts[i - 1][0], pts[i - 1][1], pts[i][0], pts[i][1]);
  }
  var spd2 = inst.vx * inst.vx + inst.vy * inst.vy;
  g.save(); g.translate(hx, hy);
  if (P.shape === "blade") {
    var k = bladeSprite(c[0], c[1], c[2], P.radius, P.stretch, !!P.hot, P.glow, P.glow_size);
    g.rotate(bp[2]); g.scale(ps, ps); g.globalAlpha *= fade;
    blitBlade(g, k, P);
  } else if (P.shape === "bolt" && spd2 > 0.0001 && P.stretch > 1.001) {
    var b = boltSprite(c[0], c[1], c[2], P.radius, P.stretch, !!P.hot, P.glow, P.glow_size);
    g.rotate(Math.atan2(inst.vy, inst.vx)); g.scale(ps, ps); g.globalAlpha *= fade;
    g.drawImage(b.cv, trunc(-b.headX), trunc(-b.halfH));
  } else if (P.shape === "bolt") {
    var o = boltSprite(c[0], c[1], c[2], P.radius, 1, !!P.hot, P.glow, P.glow_size);
    g.scale(ps, ps); g.globalAlpha *= fade;
    g.drawImage(o.cv, -trunc(o.cv.width / 2), -trunc(o.cv.height / 2));
  } else {
    var s = bulletSprite(c[0], c[1], c[2], P.radius, P.glow, P.glow_size);
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
// A lodged blade: only the part outside the target is drawn, with a soft
// glow where it enters; it fades out over its last BLADE_LODGE_FADE_MS.
// Drawn with normal blending and BLADE_LODGE_GLOW of its glow, so dozens
// stuck in one target stay separate swords instead of one white mass.
var BLADE_LODGE_GLOW = 0.35;
function drawLodged(g, inst, host, ps) {
  var P = inst.fx.params, lg = inst.lodge, c = colorPair(inst.fx, host.lut)[0].map(trunc);
  var k = Math.min(1, (inst.life - inst.age) / Math.max(1, BLADE_LODGE_FADE_MS / TICK_MS));
  var sp = bladeSprite(c[0], c[1], c[2], P.radius, P.stretch, !!P.hot, (P.glow == null ? 100 : +P.glow) * BLADE_LODGE_GLOW, P.glow_size);
  g.globalCompositeOperation = "source-over";
  var cut = lg.depth / ps;   // sprite units hidden inside the target
  g.save(); g.translate(trunc(inst.x), trunc(inst.y)); g.rotate(lg.a); g.scale(ps, ps); g.globalAlpha *= k;
  g.beginPath(); g.rect(-sp.cv.width - 2, -sp.cv.height, sp.cv.width + 2 - cut, sp.cv.height * 2); g.clip();
  blitBlade(g, sp, P);
  g.restore();
  var er = Math.max(1, +P.radius) * 1.4 * ps, ex = inst.x - Math.cos(lg.a) * lg.depth, ey = inst.y - Math.sin(lg.a) * lg.depth;
  g.fillStyle = radial(g, ex, ey, er, [[0, rgba([255, 255, 255], 110 * k)], [0.4, rgba(c, 70 * k)], [1, rgba(c, 0)]]);
  ellipse(g, trunc(ex - er), trunc(ey - er), trunc(er * 2), trunc(er * 2));
}
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
// Radial pulse rings at `age` (default now): [{k, r, w, a}].  Ring k starts
// k * gap_ms in (only while the effect lasts) and grows r_start -> r_end over
// expand_ms (eased), its line width -> width_end, fading by `fade`.
function pulseEase(u, m) { return m === "out" ? 1 - (1 - u) * (1 - u) : m === "in" ? u * u : u; }
function pulseFade(u, m) { return m === "out" ? 1 - u : m === "in" ? u : m === "inout" ? Math.sin(u * Math.PI) : 1; }
function pulseRings(inst, ps, age) {
  var P = inst.fx.params, out = [];
  if (age == null) age = inst.age;
  if (age < 0) return out;
  var exp = Math.max(1, +P.expand_ms / TICK_MS), gap = Math.max(1, +P.gap_ms / TICK_MS), n = trunc(P.rings);
  for (var k = Math.max(0, trunc((age - exp) / gap)); k * gap <= age && (n <= 0 || k < n) && k * gap < inst.life; k++) {
    var u = (age - k * gap) / exp;
    if (u < 0 || u >= 1) continue;
    var e = pulseEase(u, P.ease);
    out.push({k: k, r: Math.max(0, (P.r_start + (P.r_end - P.r_start) * e) * ps),
      w: Math.max(0, (P.width + (P.width_end - P.width) * u) * ps), a: pulseFade(u, P.fade)});
  }
  return out;
}
// (stretch_x, stretch_y, tilt_deg) of a pulse's rings.  Flip mirrors the tilt
// and Follow direction turns it, as they do an orbit's ellipse (orbitPos).
var PULSE_MIN_STRETCH = 0.05;
function pulseShape(inst, host) {
  var P = inst.fx.params, sx = P.stretch_x == null ? 1 : +P.stretch_x, sy = P.stretch_y == null ? 1 : +P.stretch_y;
  return {sx: Math.max(PULSE_MIN_STRETCH, sx), sy: Math.max(PULSE_MIN_STRETCH, sy),
    tilt: (+P.tilt_deg || 0) * (inst.flip || 1) + bodyDeg(inst.fx, host, [inst.x, inst.y])};
}
// How far a ring of radius 1 reaches toward offset (dx, dy).
function pulseScaleToward(sh, dx, dy) {
  var l = rot([dx, dy], -sh.tilt), d = Math.sqrt(l[0] * l[0] + l[1] * l[1]);
  if (d < 1e-6) return Math.min(sh.sx, sh.sy);
  return d / Math.sqrt((l[0] / sh.sx) * (l[0] / sh.sx) + (l[1] / sh.sy) * (l[1] / sh.sy));
}
DRAW.pulse = function (g, inst, host, ps) {
  var P = inst.fx.params, cp = colorPair(inst.fx, host.lut), c1 = cp[0].map(trunc), c2 = cp[1].map(trunc);
  var sh = pulseShape(inst, host), ta = sh.tilt * D;
  pulseRings(inst, ps).forEach(function (q) {
    if (q.a <= 0.004) return;
    if (P.fill_alpha > 0 && q.r >= 1) {
      g.save(); g.translate(inst.x, inst.y); g.rotate(ta); g.scale(sh.sx, sh.sy);
      g.fillStyle = radial(g, 0, 0, q.r, [[0, rgba(c2, 0)], [0.7, rgba(c2, P.fill_alpha * q.a * 0.35)], [1, rgba(c2, P.fill_alpha * q.a)]]);
      ellipse(g, -q.r, -q.r, q.r * 2, q.r * 2);
      g.restore();
    }
    if (P.glow > 0) {
      g.strokeStyle = rgba(c2, 70 * q.a); g.lineWidth = q.w + P.glow * ps;
      g.beginPath(); g.ellipse(inst.x, inst.y, q.r * sh.sx, q.r * sh.sy, ta, 0, 2 * Math.PI); g.stroke();
    }
    if (q.w > 0) {
      g.strokeStyle = rgba(c1, 235 * q.a); g.lineWidth = q.w;
      g.beginPath(); g.ellipse(inst.x, inst.y, q.r * sh.sx, q.r * sh.sy, ta, 0, 2 * Math.PI); g.stroke();
    }
  });
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
HIT.sprite = function (inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var P = inst.fx.params;
  if (P.shape === "blade") {   // the whole blade, tip to pommel, half-width wide
    if (inst.lodge) return false;
    var L = bladeLength(P, ps), bp = bladePose(inst, ps), a = bp[2];
    return segDist(tx, ty, bp[0], bp[1], bp[0] - Math.cos(a) * L, bp[1] - Math.sin(a) * L) <= hr + Math.max(0.5, +P.radius) * ps;
  }
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
HIT.pulse = function () { return false; };   // resolved per ring in resolveHits
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
  if (!b.deals_damage || !hurt || inst.dead || inst.lodge) return;
  var now = inst.age;
  if (inst.fx.prim === "pulse") {
    // Each ring hits once, when its edge sweeps over the target (this tick's
    // radius and last tick's), pushing outward.  Rings never end on a hit.
    // Stretched rings reach r * the ellipse's radius toward the target.
    var prev = {}, sh = pulseShape(inst, host);
    pulseRings(inst, ps, inst.age - 1).forEach(function (q) { prev[q.k] = q.r; });
    pulseRings(inst, ps).forEach(function (q) {
      if (inst.ringHits[q.k]) return;
      var dx = hurt.x - inst.x, dy = hurt.y - inst.y, d = Math.sqrt(dx * dx + dy * dy), f = pulseScaleToward(sh, dx, dy);
      var rp = prev[q.k] == null ? q.r : prev[q.k], lo = Math.min(q.r, rp) * f - q.w / 2, hi = Math.max(q.r, rp) * f + q.w / 2;
      if (d < lo - hurt.r || d > hi + hurt.r) return;
      inst.ringHits[q.k] = true; inst.hits += 1; inst.lastHit = now;
      if (host.onHit) host.onHit(inst, b.damage, d > 0.001 ? dx / d : inst.dir[0], d > 0.001 ? dy / d : inst.dir[1], b.knockback);
    });
    return;
  }
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
  if (b.pierce) return;
  if (canLodge(inst)) bladeLodge(inst, hurt.x, hurt.y, hurt.r, ps);
  else inst.age = Math.max(inst.age, inst.life);
}
function canLodge(inst) { var fx = inst.fx; return fx.prim === "sprite" && fx.params.shape === "blade" && +fx.params.lodge_ms > 0; }

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
// A key switched an alive instance's motion (or aim): it changes from where
// it is.  Into travel / homing / zigzag it launches along its Aim at the
// keyed Speed; coming off the fighter (from attached / static / orbit) it is
// a shot from then on, living Life ticks from the launch (0 = LAUNCH_LIFE).
// Into orbit it carries on round its anchor from its own angle; into
// attached / static it stops.  Returns true when an always-on instance
// launched (its set is spent).  laser/fxkit.py motion_switch.
var MOVERS = {travel: 1, homing: 1, zigzag: 1};
var LAUNCH_LIFE = 220;
function motionSwitch(inst, host) {
  var fx = inst.fx, m = fx.motion, from = inst.mk, wasCont = !!inst.cont;
  inst.mk = m.kind; inst.ma = m.aim;
  if (inst.free || inst.lodge || fx.prim === "weapon" || inst.age >= inst.life) return false;
  var ps = inst.ps || 1;
  if (MOVERS[m.kind]) {
    var d = aimDir(fx, host, inst.x, inst.y), at = [inst.x, inst.y];
    if (!MOVERS[from] && inst.tgt) {
      // Each particle blade: it launches from where it is drawn, along where
      // it points (bladePose).
      var bp = bladePose(inst, hostScale(host));
      inst.x = inst.px = bp[0]; inst.y = inst.py = bp[1];
      d = [Math.cos(bp[2]), Math.sin(bp[2])]; at = [bp[0], bp[1]];
    }
    if (m.aim_offset_deg) d = rot(d, m.aim_offset_deg * turnSign(fx, host, d, at));
    var spd = +m.speed || 0;
    inst.dir = d; inst.spd = spd; inst.vx = d[0] * spd * ps; inst.vy = d[1] * spd * ps;
    if (m.kind === "zigzag") {   // as spawn: its side of the new line
      inst.side = inst.flip * turnSign(fx, host, d, at) * inst.facing;
      var pr = spd > 0.001 ? [-d[1] * inst.side, d[0] * inst.side] : [0, inst.side];
      inst.zx = pr[0] * m.amplitude * ps; inst.zy = pr[1] * m.amplitude * ps; inst.phase = 0;
    }
    if (!MOVERS[from]) {
      inst.cont = false; inst.open = false; inst.trail = [];
      inst.life = inst.age + (fx.life_ticks > 0 ? fx.life_ticks : LAUNCH_LIFE);
      return wasCont;
    }
    return false;
  }
  inst.vx = 0; inst.vy = 0;
  if (m.kind === "orbit") {
    var c = anchorPos(fx, host, inst), hs = hostScale(host);
    var v = turnBy([inst.x - c[0], inst.y - c[1]], -bodyDeg(fx, host, c));
    inst.orbitA = Math.atan2(v[1] / Math.max(1e-6, m.orbit_ry * hs), v[0] / Math.max(1e-6, m.orbit_rx * hs * inst.flip)) / D;
  }
  return false;
}

// runs: Continuous runs (stepRun); spent: always-on effects whose set
// launched (no new set until the action restarts or changes); lastT: the
// previous tick's t (a smaller t = the action restarted).
function Player() { this.reset(); }
Player.prototype.reset = function () { this.insts = []; this.t = 0; this.clock = 0; this.pending = []; this.runs = []; this.spent = []; this.lastT = -1; };
// An entry-set effect's production window in action ticks: [first tick, stop
// tick].  Nothing is produced before the set's Start frame or from the tick
// after its Stop frame on.  laser/fxkit.py Player.entry_window.
Player.prototype.entryWindow = function (fx, host, frames, frameMs) {
  var set = entrySetOf(fx, host);
  if (!set) return [0, Infinity];
  var s = Math.round(Math.max(0, set.start_frame) * frameMs / TICK_MS), st = set.stop_frame;
  return [s, st < 0 ? Infinity : Math.round((Math.min(frames - 1, st) + 1) * frameMs / TICK_MS)];
};
// The order a sequential set's points fire in.  laser/fxkit.py Player.entry_order.
function entryOrder(set, fx, t, salt) {
  var n = set.points.length, o = set.order, idx = [], i;
  for (i = 0; i < n; i++) idx.push(i);
  if (set.mode !== "sequential" || o === "forward" || n < 2) return idx;
  if (o === "reverse") return idx.reverse();
  if (o === "pingpong") { for (i = n - 2; i > 0; i--) idx.push(i); return idx; }
  var r = rng((hash32(fx.id) ^ Math.imul(t + 1, 0x2C1B3C6D) ^ Math.imul(salt, 0x297A2D39)) >>> 0);
  for (i = n - 1; i > 0; i--) { var j = Math.min(i, Math.floor(r() * (i + 1))), tmp = idx[i]; idx[i] = idx[j]; idx[j] = tmp; }
  return idx;
}
Player.prototype.window = function (fx, frames, frameMs) {
  var total = Math.max(1, Math.round(frames * frameMs / TICK_MS));
  var s = Math.round(Math.max(0, fx.start_frame) * frameMs / TICK_MS);
  var e = fx.end_frame < 0 ? total : Math.round((Math.min(frames - 1, fx.end_frame) + 1) * frameMs / TICK_MS);
  return [Math.min(s, total - 1), Math.max(s + 1, e), total];
};
// Advance one tick.  `t` counts ticks since the action started (it wraps
// when the action loops; instances already alive keep running).
// opts.hold (Blink, while the fighter is gone): nothing new fires; live
// instances keep updating.
// opts.continuous (the action's fx_continuous while it loops): an "open"
// instance (life 0 = to the end, window reaching the action's end) is kept
// alive across the loop, and its effect is not spawned again while it lives.
Player.prototype.tick = function (effects, host, t, frames, frameMs, opts) {
  var self = this, cont = !!(opts && opts.continuous);
  // Spawn `n` copies of fx.  With an entry set they come out of every point:
  // together, or (sequential) one point every interval_ticks.
  // run (Continuous): its frame time and cycle number, so its keys play on
  // the action's timing and each cycle's randomness differs.
  // stop: the entry set's stop tick (entryWindow).
  function fireFx(fx, t, n, win, tag, run, stop) {
    var set = entrySetOf(fx, host), salt = run ? run.k + 1 : 0, order = set ? entryOrder(set, fx, t, salt) : [null];
    for (var pos = 0; pos < order.length; pos++) {
      var delay = set && set.mode === "sequential" ? pos * Math.max(0, trunc(set.interval_ticks)) : 0;
      var job = {fx: fx, t: t, n: n, win: win - delay, ep: order[pos], tag: tag, due: self.clock + delay, delay: delay,
        fms: run ? run.fms : frameMs, salt: salt, stop: run ? run.stop : stop == null ? Infinity : stop};
      if (delay > 0) self.pending.push(job); else spawnJob(job);
    }
  }
  function spawnJob(j) {
    for (var i = 0; i < j.n; i++) {
      var seed = (hash32(j.fx.id) ^ Math.imul(j.t + 1, 0x9E3779B1) ^ (i * 0x85EBCA6B) ^ Math.imul((j.ep == null ? 0 : j.ep + 1), 0xC2B2AE35)
        ^ Math.imul(j.salt || 0, 0x27D4EB2F)) >>> 0;
      var t0 = j.t + (j.delay || 0);
      if (t0 >= j.stop) return;   // past its entry set's Stop frame: no more particles
      var inst = spawn(fxAt(j.fx, t0 * TICK_MS / j.fms), host, Math.max(1, j.win), seed, i, j.n, j.ep);
      inst.src = j.fx; inst.t0 = t0; inst.fms = j.fms;
      if (j.tag === "cont") { inst.cont = true; inst.win = inst.life; inst.life = Infinity; }
      else { inst.open = j.tag === "open"; inst.run = j.tag === "run"; }
      self.insts.push(inst);
    }
  }
  // One tick of a Continuous run: the effect's own emissions at run time
  // r.rt (exactly as the action would fire them), then the clock moves on.
  // False once the sequence (and every cycle) is done.
  function stepRun(r) {
    var fx = r.fx, ev = fx.emit.every_ticks;
    if (r.rt === r.s || (ev > 0 && r.rt > r.s && r.rt < r.e && (r.rt - r.s) % ev === 0))
      fireFx(fx, r.rt, Math.max(1, trunc(fx.emit.count)), r.e - r.rt, "run", r);
    r.rt += 1;
    if (r.rt - r.s < r.len) return true;
    if (!r.loop || r.left === 0) return false;
    if (r.left > 0) r.left -= 1;
    r.k += 1; r.rt = r.s;
    return true;
  }
  var due = this.pending.filter(function (j) { return j.due <= self.clock; });
  this.pending = this.pending.filter(function (j) { return j.due > self.clock; });
  due.forEach(function (j) { if (j.tag === "run" || (j.fx.enabled && effects.indexOf(j.fx) >= 0)) spawnJob(j); });
  // The action restarted (t went back) or an effect left it: its spent
  // always-on set may start again.
  if (t < this.lastT) this.spent = [];
  this.spent = this.spent.filter(function (f) { return effects.indexOf(f) >= 0; });
  this.lastT = t;
  // Continuous runs, on their own clock whatever the action is doing.
  this.runs = this.runs.filter(stepRun);
  // An always-on instance ends when its effect is removed, disabled or no
  // longer always on.
  this.insts.forEach(function (inst) {
    var src = inst.src || inst.fx;
    if (inst.cont && (!src.enabled || effects.indexOf(src) < 0 || !isAlwaysOn(src))) inst.dead = true;
  });
  effects.forEach(function (fx) {
    if (!fx.enabled || (opts && opts.hold)) return;
    var w = self.window(fx, frames, frameMs), s = w[0], e = w[1], ew = self.entryWindow(fx, host, frames, frameMs), stop = ew[1];
    if (ew[0] > s) {   // the entry set starts producing later than the effect
      s = ew[0];
      if (s >= w[2] || (s >= e && !isAlwaysOn(fx))) return;
    }
    if (isAlwaysOn(fx)) {   // one never-ending instance, started at its start frame
      if (t < s || self.spent.indexOf(fx) >= 0 || self.insts.some(function (q) { return (q.src || q.fx) === fx && q.cont && !q.dead && q.age < q.life; })
        || self.pending.some(function (q) { return q.fx === fx; })) return;
      fireFx(fx, t, Math.max(1, trunc(fx.emit.count)), w[2] - s, "cont", null, stop);
      return;
    }
    if (isContinuous(fx)) {   // a run of its whole sequence each time the action reaches the start frame
      if (t !== s) return;
      var mine = self.runs.filter(function (r) { return r.fx === fx; });
      if (mine.length >= CYCLE_MAX_RUNS) self.runs.splice(self.runs.indexOf(mine[0]), 1);
      var run = {fx: fx, s: s, e: e, rt: s, len: Math.max(1, e - s, fx.life_ticks > 0 ? trunc(fx.life_ticks) : 0), fms: frameMs, k: 0,
        loop: !!fx.cycles.enabled, left: trunc(fx.cycles.count), stop: stop};
      if (stepRun(run)) self.runs.push(run);   // its first tick is this one
      return;
    }
    var periodic = fx.emit.every_ticks > 0 && t > s && t < e && (t - s) % fx.emit.every_ticks === 0;
    var fire = t === s || periodic;
    if (!fire) return;
    var open = fx.life_ticks <= 0 && e >= w[2];
    if (cont && open && !periodic && self.insts.some(function (q) { return (q.src || q.fx) === fx && q.open && !q.dead; })) return;
    fireFx(fx, t, Math.max(1, trunc(fx.emit.count)), e - t, open ? "open" : "", null, stop);
  });
  this.clock += 1;
  var ps = host.pscale || 1;
  if (cont) this.insts.forEach(function (inst) { if (inst.open && inst.age < inst.life) inst.life = Math.max(inst.life, inst.age + 2); });
  this.insts.forEach(function (inst) {
    // Keyframes: this tick's values at the instance's own action time.
    if (inst.src && inst.src.keys && inst.src.keys.length) inst.fx = fxAt(inst.src, (inst.t0 + inst.age) * TICK_MS / inst.fms);
    if ((inst.mk !== inst.fx.motion.kind || inst.ma !== inst.fx.motion.aim) && motionSwitch(inst, host) && self.spent.indexOf(inst.src) < 0) self.spent.push(inst.src);
    tickInst(inst, host); resolveHits(inst, host, ps);
  });
  this.insts = this.insts.filter(function (i) { return !i.dead; });
};
// hidden (Blink, while the fighter is gone): its body FX are not drawn.
Player.prototype.draw = function (g, host, layer, ps, hidden) {
  this.insts.forEach(function (inst) { if (inst.fx.layer === layer && !(hidden && bodyBound(inst))) drawInst(g, inst, host, ps); });
};
// FX that sit on the fighter's body (attached / orbit motion, weapon
// hitboxes): hidden and harmless while it is blinked out.
function bodyBound(inst) { var fx = inst.fx; return fx.motion.kind === "attached" || fx.motion.kind === "orbit" || fx.prim === "weapon"; }

G.FXK = {TICK_MS: TICK_MS, rng: rng, hash32: hash32, buildLut: buildLut, hexRgb: hexRgb,
  PRIMS: PRIMS, MOTIONS: MOTIONS, AIMS: AIMS, PARAM_DEFAULTS: PARAM_DEFAULTS,
  MOTION_DEFAULTS: MOTION_DEFAULTS, COLOR_DEFAULTS: COLOR_DEFAULTS, BATTLE_DEFAULTS: BATTLE_DEFAULTS,
  INTERCEPT_DEFAULTS: INTERCEPT_DEFAULTS, FLIP_DEFAULTS: FLIP_DEFAULTS, flipSign: flipSign, fxFacing: fxFacing, bodyDeg: bodyDeg, placeDeg: placeDeg, rot: rot, turnBy: turnBy, INTERCEPT_MODES: INTERCEPT_MODES, canIntercept: canIntercept, interceptOn: interceptOn, clashOn: clashOn, CLASH_KB_MARGIN: CLASH_KB_MARGIN,
  newEffect: newEffect, normalize: normalize, normalizeEntrySet: normalizeEntrySet, normalizePath: normalizePath,
  ENTRY_DEFAULTS: ENTRY_DEFAULTS, ENTRY_ORDERS: ENTRY_ORDERS, PATH_DEFAULTS: PATH_DEFAULTS, pathLine: pathLine, pathAt: pathAt, pathMatrix: pathMatrix, canContinue: canContinue, isContinuous: isContinuous, CONDITION_TYPES: CONDITION_TYPES, ACTION_DEFAULTS: ACTION_DEFAULTS, AIM_DEFAULTS: AIM_DEFAULTS, normalizeAim: normalizeAim, aimAngle: aimAngle,
  DAMAGED_DEFAULTS: DAMAGED_DEFAULTS, normalizeDamaged: normalizeDamaged,
  RETREAT_DEFAULTS: RETREAT_DEFAULTS, RETREAT_CONDITIONS: RETREAT_CONDITIONS, normalizeRetreat: normalizeRetreat,
  BLINK_DEFAULTS: BLINK_DEFAULTS, BLINK_ANCHORS: BLINK_ANCHORS, BLINK_DIRECTIONS: BLINK_DIRECTIONS, normalizeBlink: normalizeBlink,
  blinkActive: blinkActive, blinkLanding: blinkLanding, bodyBound: bodyBound,
  STAND_HEIGHT_PX: STAND_HEIGHT_PX, rescaleEffects: rescaleEffects, standHeight: standHeight,
  EASES: EASES, ease: ease, fxAt: fxAt, sampleKey: sampleKey, keyPaths: keyPaths, isKeyable: isKeyable, getPath: getPath, normalizeKeys: normalizeKeys,
  KEY_CHOICES: KEY_CHOICES, CYCLE_DEFAULTS: CYCLE_DEFAULTS, CYCLE_MAX_RUNS: CYCLE_MAX_RUNS, isAlwaysOn: isAlwaysOn, LAUNCH_LIFE: LAUNCH_LIFE,
  actionKind: actionKind, moveFactor: moveFactor, animLoops: animLoops, normalizeAction: normalizeAction, Player: Player, bulletSprite: bulletSprite, bladeSprite: bladeSprite};
})(window);
