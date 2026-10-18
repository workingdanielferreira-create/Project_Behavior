/* Gunfire — FX Studio's port of laser/gunfx.py: the anime gun shots of the
 * FX Kit "technique" primitive (machine gun, shotgun, magnum, charged blast,
 * dual pistols, sniper rail shot, gatling, rocket barrage, drill bullet,
 * thunder bullet).  Same timeline, same random streams (FXK.rng), same
 * geometry and painting order as the game, so the Studio preview draws what
 * Solo and Battle draw.  Keep the two in step.
 * Builds on swordfx.js (frame, pen, maths): load it after that file.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };
var STYLES = ["machine_gun", "shotgun", "magnum", "charged_blast", "dual_pistols", "sniper_rail", "gatling",
  "rocket_barrage", "drill_bullet", "thunder_bullet"];

// Per gun: look, speed (px per tick, x scale), range (times length), rounds
// per volley, side offset of alternate rounds (px), muzzle flash ticks and
// size (px), casings (0 none, 1 brass, 2 shotgun shell), muzzle smoke puffs,
// dust / smoke puffs where a round lands.
var GUNS = {
  machine_gun: {look: "tracer", speed: [16, 19], range: [0.9, 1.05], pellets: 1, side: 0, flash: 3, flash_px: 9,
    shells: 1, smoke: 0, dust: 1},
  shotgun: {look: "pellet", speed: [12, 16], range: [0.55, 1.0], pellets: 9, side: 0, flash: 8, flash_px: 22,
    shells: 2, smoke: 4, dust: 0},
  magnum: {look: "slug", speed: [21, 23], range: [1.0, 1.0], pellets: 1, side: 0, flash: 9, flash_px: 20,
    shells: 0, smoke: 3, dust: 2},
  charged_blast: {look: "orb", speed: [8, 9], range: [1.0, 1.0], pellets: 1, side: 0, flash: 10, flash_px: 30,
    shells: 0, smoke: 3, dust: 5},
  dual_pistols: {look: "tracer", speed: [14, 17], range: [0.85, 1.05], pellets: 1, side: 9, flash: 5,
    flash_px: 11, shells: 1, smoke: 0, dust: 1},
  sniper_rail: {look: "rail", speed: [0, 0], range: [1.0, 1.0], pellets: 1, side: 0, flash: 10, flash_px: 26,
    shells: 1, smoke: 3, dust: 3},
  gatling: {look: "tracer", speed: [17, 20], range: [0.85, 1.05], pellets: 1, side: 4, flash: 2, flash_px: 8,
    shells: 1, smoke: 0, dust: 1},
  rocket_barrage: {look: "rocket", speed: [7, 9], range: [1.0, 1.0], pellets: 1, side: 6, flash: 6, flash_px: 14,
    shells: 0, smoke: 2, dust: 5},
  drill_bullet: {look: "drill", speed: [12, 13], range: [1.0, 1.0], pellets: 1, side: 0, flash: 8, flash_px: 18,
    shells: 0, smoke: 2, dust: 2},
  thunder_bullet: {look: "bolt", speed: [13, 15], range: [0.9, 1.05], pellets: 1, side: 0, flash: 6, flash_px: 16,
    shells: 1, smoke: 0, dust: 2}
};
var IMPACT_LIFE = {tracer: 14, pellet: 11, slug: 26, orb: 36, rail: 28, rocket: 32, drill: 22, bolt: 22};
var EXPLODES = ["orb", "rocket", "bolt", "drill"];   // these go off at the end of their range too

var TRACER_TAIL = 3.2, FADE_TAIL = 0.25, CASING_LIFE = 28, CASING_G = 0.32, SMOKE_LIFE = 40;
var GAT_GAP = [4.0, 1.0], GAT_RAMP = 0.45, GAT_BARREL = 1.0472, GAT_SPIN = 0.55, GAT_SPIN_DOWN = 18;
var RAIL_HIT = 3, RAIL_DELAY = 5, CHARGE_P = 14, CHARGE_RING = 9;
var ROCKET_ARC = 0.55, ROCKET_EASE = 1.35, ROCKET_MIN = 12, ROCKET_PUFF = 2;
var DRILL_SPIN = 0.22, DRILL_RING = 5, BOLT_SEG = 20;
var BRASS = [255, 198, 92], HULL = [214, 44, 40], SMOKE = [96, 90, 84], STEEL = [226, 230, 236];

function frac(x) { return x - Math.floor(x); }
function minmax(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// ---------------------------------------------------------------- timeline
function g_(P) { return GUNS[L_().style(P)]; }
function cad(P) { return Math.max(1, Math.trunc(+P.swing_ticks || 1)); }
function hold(P) { return Math.max(0, Math.trunc(+P.hold_ticks || 0)); }
// Ticks the shots (volleys) fire on.
function launches(P) {
  var st = L_().style(P), c = cad(P), h = hold(P), out = [], k;
  if (st === "charged_blast") return [c + h];
  if (st === "sniper_rail") return [c];
  if (st === "gatling") {
    var t = c, end = c + h, ramp = Math.max(1, h * GAT_RAMP);
    while (t <= end) {
      out.push(Math.trunc(t));
      var u = Math.min(1, (t - c) / ramp);
      t += GAT_GAP[0] + (GAT_GAP[1] - GAT_GAP[0]) * u;
    }
    return out;
  }
  for (k = 0; k < Math.floor(h / c) + 1; k++) out.push(k * c);
  return out;
}
function flightMax(P) {
  var g = g_(P);
  if (g.look === "rail") return RAIL_HIT;
  var n = Math.ceil(+P.length * g.range[1] / g.speed[0]);
  if (g.look === "rocket") n = Math.max(n, ROCKET_MIN);
  return n;
}
function activeTicks(P) { var lb = launches(P); return lb[lb.length - 1] + flightMax(P) + 1; }
function totalTicks(P) {
  var g = g_(P), tail = Math.max(IMPACT_LIFE[g.look], SMOKE_LIFE, CASING_LIFE);
  if (L_().style(P) === "gatling") tail += GAT_SPIN_DOWN;
  if (g.look === "rail") tail += hold(P) + RAIL_DELAY;
  return activeTicks(P) + tail;
}
function at(lst, k) { return lst[Math.max(0, Math.min(k, lst.length - 1))]; }
function tracks(inst) { return (inst.fx.motion || {}).aim === "target"; }
// [origin x, origin y, forward] of the gun at tick k: at the target when tracking.
function aim(inst, k) {
  var o = at(inst.tq_path, k), ox = o[0], oy = o[1], f = inst.tq_f;
  if (tracks(inst)) {
    var tp = at(inst.tq_tp, k), dx = tp[0] - ox, dy = tp[1] - oy, d = L_().hyp(dx, dy);
    if (d > 1) f = [dx / d, dy / d];
  }
  return [ox, oy, f];
}

// ---------------------------------------------------------------- rounds
// One round: everything about it is rolled from the seed.
function Round(inst, i, v, j, b, ps) {
  var L = L_(), P = inst.fx.params, st = L.style(P), g = GUNS[st], r = L.rngFor(inst.seed, i, 43);
  var su = r.uniform(g.speed[0], g.speed[1]), n = g.pellets, span = +P.span || 0, a;
  if (n > 1) a = ((j + 0.5) / n - 0.5) * span + r.uniform(-0.5, 0.5) * span / n;
  else a = r.uniform(-0.5, 0.5) * span;
  var ru = r.uniform(g.range[0], g.range[1]);
  this.i = i; this.v = v; this.j = j; this.b = b;
  this.look = g.look;
  this.ang = a * L.D;
  this.size = r.uniform(0.85, 1.15) * ((inst.tq_grow || {})[i] || 1);   // grown by absorbing
  this.tint = r.uniform(0, 0.35);
  var am = aim(inst, b), ox = am[0], oy = am[1], f = am[2];
  var m = tracks(inst) ? (f[0] >= 0 ? 1 : -1) : inst.tq_m;
  this.fr = new L.Frame(0, 0, f, m);
  var sd = st === "dual_pistols" ? Math.max(0, +(P.gap_px == null ? 18 : P.gap_px) || 0) * 0.5 * ps : +g.side * ps, lat;
  if (st === "gatling") lat = sd * Math.sin(v * GAT_BARREL);
  else lat = v % 2 === 0 ? sd : -sd;
  var so = this.fr.d(0, lat);
  this.ox = ox + so[0]; this.oy = oy + so[1];
  this.sp = su * ps;
  this.arc = 0;
  // A clash holding / carrying this round (laser/clash.py) shifts its whole
  // flight: inst.tq_off[i] = [dx, dy].
  var off = (inst.tq_off || {})[i];
  this.dx = off ? off[0] : 0; this.dy = off ? off[1] : 0;
  // An intercept pulled it off its path (charged blast, trackStep): from then
  // on it flies its recorded path (STRIKEFX.trackShots).
  this.trk = (inst.tq_kd || {})[i] || null;
  var Lp = +P.length;
  if (this.look === "rail") {
    this.rng = Lp * ps;
    this.flight = RAIL_HIT;
  } else if (this.look === "rocket") {
    var dist = Lp * ru * ps;
    if (tracks(inst)) {
      var tp = at(inst.tq_tp, b);
      dist = Math.min(dist, L.hyp(tp[0] - this.ox, tp[1] - this.oy));
    }
    dist = Math.max(dist, 30 * ps);
    this.rng = dist;
    this.flight = Math.max(ROCKET_MIN, Math.ceil(dist / this.sp));
    this.arc = (v % 2 === 0 ? 1 : -1) * r.uniform(0.6, 1.0) * ROCKET_ARC * dist;
  } else {
    this.rng = Lp * ru * ps;
    this.flight = Math.max(1, Math.ceil(Lp * ru / su));
  }
}
Round.prototype.pos = function (k) {   // world position k ticks after launch
  var d, tr = this.trk;
  if (tr && this.b + k >= tr[0]) {
    var h = tr[1], j = this.b + k - tr[0], n = Math.floor(j);
    if (n >= h.length - 1) return h[h.length - 1].slice();
    var u = j - n, a = h[n], b2 = h[n + 1];
    return [a[0] + (b2[0] - a[0]) * u, a[1] + (b2[1] - a[1]) * u];
  }
  if (this.look === "rocket") {
    var u = minmax(k / this.flight, 0, 1), e = Math.pow(u, ROCKET_EASE);
    var lx = 2 * (1 - e) * e * this.rng * 0.4 + e * e * this.rng, ly = 2 * (1 - e) * e * this.arc;
    d = this.fr.d(lx, ly);
  } else {
    var d0 = this.sp * k;
    d = this.fr.d(Math.cos(this.ang) * d0, Math.sin(this.ang) * d0);
  }
  return [this.ox + d[0] + this.dx, this.oy + d[1] + this.dy];
};
Round.prototype.head = function (k) {   // unit direction of travel k ticks after launch
  if (this.look === "rocket") {
    var p1 = this.pos(k), p0 = this.pos(k - 0.5), d = L_().hyp(p1[0] - p0[0], p1[1] - p0[1]);
    if (d > 1e-6) return [(p1[0] - p0[0]) / d, (p1[1] - p0[1]) / d];
    return this.fr.d(1, 0);
  }
  return this.fr.d(Math.cos(this.ang), Math.sin(this.ang));
};
Round.prototype.end = function (inst) {   // [tick it stops, stopped by a hit?]
  var h = inst.tq_ki[this.i];
  return h ? [h[0], true] : [this.b + this.flight, false];
};
function rounds(inst, ps) {   // every round fired up to now, in firing order
  var P = inst.fx.params, n = g_(P).pellets, lb = launches(P), out = [];
  for (var v = 0; v < lb.length; v++) {
    if (lb[v] > inst.age) break;
    for (var j = 0; j < n; j++) out.push(new Round(inst, v * n + j, v, j, lb[v], ps));
  }
  return out;
}
function live(inst, ps) {   // [[round, position]] in flight this tick (not the rail)
  var out = [], t = inst.age, all = rounds(inst, ps);
  for (var i = 0; i < all.length; i++) {
    var s = all[i];
    if (s.look === "rail") continue;
    if (t < s.end(inst)[0]) out.push([s, s.pos(t - s.b)]);
  }
  return out;
}
// [[i, x, y, vx, vy]] for the rounds in flight this tick (i = the round's
// index): what retreat / dodge / projectile counts see of a gun.
// laser/gunfx.py live_points.
function livePoints(inst, ps) {
  return live(inst, ps).map(function (e) {
    var s = e[0], p = e[1], k = inst.age - s.b, q;
    if (k >= 1) { q = s.pos(k - 1); return [s.i, p[0], p[1], p[0] - q[0], p[1] - q[1]]; }
    q = s.pos(1); return [s.i, p[0], p[1], q[0] - p[0], q[1] - p[1]];
  });
}
// ---------------------------------------------------------------- clash
// A charged blast's orb clashes on its own (an orb body per round in
// flight); every other gun never clashes.  laser/gunfx.py clashes.
function clashes(P) { return L_().style(P) === "charged_blast"; }
function roundI(inst, i, ps) {   // round i, once it has fired (else null)
  var P = inst.fx.params, n = g_(P).pellets, lb = launches(P), v = Math.floor(i / n);
  if (i < 0 || v >= lb.length || lb[v] > inst.age) return null;
  return new Round(inst, i, v, i % n, lb[v], ps);
}
// Intercept for the charged blast: its orb is an auto-projectile tracker
// exactly like a ki barrage orb.  laser/gunfx.py track_step.
function trackStep(inst, host) {
  if (!host || !clashes(inst.fx.params) || inst.age >= inst.life || !G.STRIKEFX) return;
  G.STRIKEFX.trackShots(inst, host, live(inst, inst.ps || 1), function (s, k) { return s.pos(k); });
}
function shotIds(inst, ps) {   // indices of the rounds in flight this tick that clash
  if (!clashes(inst.fx.params) || inst.age >= inst.life) return [];
  return live(inst, ps).map(function (e) { return e[0].i; });
}
// [x, y, vx, vy, radius, ticks left] of round i while it flies, else null.
function shotAt(inst, i, ps) {
  var s = roundI(inst, i, ps);
  if (!s || s.look === "rail") return null;
  var e = s.end(inst)[0];
  if (inst.age >= e) return null;
  var k = inst.age - s.b, p = s.pos(k), q = s.pos(k + 1);
  return [p[0], p[1], q[0] - p[0], q[1] - p[1], +inst.fx.params.radius * ps * s.size, e - inst.age];
}
// Round i is at (x, y) this tick: its whole flight shifts there.
function place(inst, i, x, y, ps) {
  var s = roundI(inst, i, ps);
  if (!s) return;
  var p = s.pos(inst.age - s.b), tr = s.trk;
  if (tr && inst.age >= tr[0]) {   // flying its recorded (tracked) path: the path shifts instead
    tr[1] = tr[1].map(function (q) { return [q[0] + x - p[0], q[1] + y - p[1]]; });
    return;
  }
  if (!inst.tq_off) inst.tq_off = {};
  inst.tq_off[i] = [s.dx + x - p[0], s.dy + y - p[1]];
}
function railLine(s) { var d = s.fr.d(s.rng, 0); return [s.ox, s.oy, s.ox + d[0], s.oy + d[1]]; }

// ---------------------------------------------------------------- public
function hit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var P = inst.fx.params, r0 = +P.radius * ps, i;
  if (g_(P).look === "rail") {
    var all = rounds(inst, ps);
    for (i = 0; i < all.length; i++) {
      var s = all[i];
      if (s.b <= inst.age && inst.age < s.b + RAIL_HIT) {
        var ln = railLine(s);
        if (FXK().segDist(tx, ty, ln[0], ln[1], ln[2], ln[3]) <= hr + r0) return true;
      }
    }
    return false;
  }
  var lv = live(inst, ps);
  for (i = 0; i < lv.length; i++) {
    var p = lv[i][1];
    if (L_().hyp(p[0] - tx, p[1] - ty) <= hr + r0 * lv[i][0].size) return true;
  }
  return false;
}
function onHit(inst, x, y, ps) {
  var P = inst.fx.params, i;
  if (g_(P).look === "rail") {
    var all = rounds(inst, ps);
    for (i = 0; i < all.length; i++) {
      var s = all[i];
      if (s.b <= inst.age && inst.age < s.b + RAIL_HIT) {
        var ln = railLine(s), dx = ln[2] - ln[0], dy = ln[3] - ln[1], L2 = dx * dx + dy * dy;
        var u = L2 > 0 ? minmax(((x - ln[0]) * dx + (y - ln[1]) * dy) / L2, 0, 1) : 0;
        inst.tq_imp.push([inst.age, ln[0] + dx * u, ln[1] + dy * u]);
      }
    }
    return;
  }
  var best = null, bd = null, lv = live(inst, ps);
  for (i = 0; i < lv.length; i++) {
    var p = lv[i][1], d = L_().hyp(p[0] - x, p[1] - y);
    if (bd === null || d < bd) { best = lv[i]; bd = d; }
  }
  if (!best) return;
  if (best[0].look === "drill") inst.tq_imp.push([inst.age, best[1][0], best[1][1]]);   // it drills on through
  else inst.tq_ki[best[0].i] = [inst.age, best[1][0], best[1][1]];
}

// ================================================================ drawing
// [tick, x, y, stopped] where the round ends, or null when it just fades out.
function blastAt(inst, s) {
  var en = s.end(inst);
  if (en[1]) {
    var h = inst.tq_ki[s.i];
    if (h[3]) return null;   // gone without a blast (a clash split it: its halves fly on)
    return [en[0], h[1], h[2], true];
  }
  if (EXPLODES.indexOf(s.look) >= 0) { var p = s.pos(s.flight); return [en[0], p[0], p[1], false]; }
  return null;
}
function puffs(pen, inst, key, x, y, a, life, n, size, ps, smoke, rise) {
  if (a < 0 || a >= life || n <= 0) return;
  var L = L_(), q = a / life;
  for (var j = 0; j < n; j++) {
    var r = L.rngFor(inst.seed, key, 300 + j), an = r.uniform(0, Math.PI * 2);
    var dr = r.uniform(0.2, 1.0) * size * L.easeOut3(a / 14);
    var px = x + Math.cos(an) * dr, py = y + Math.sin(an) * dr - r.uniform(0.3, 1.0) * rise * ps * a;
    var rad = size * r.uniform(0.5, 0.9) * (0.5 + 0.8 * L.easeOut3(a / 18));
    pen.glow(px, py, rad, smoke, 90 * Math.pow(1 - q, 1.5) * Math.min(1, a / 3), 0.6);
  }
}
function casing(pen, inst, key, ox, oy, fx_, a, ps, kind) {
  if (a < 0 || a >= CASING_LIFE) return;
  var L = L_(), r = L.rngFor(inst.seed, key, 200), sg = fx_ >= 0 ? 1 : -1;
  var vx = -sg * r.uniform(1.0, 2.2) * ps, vy = -r.uniform(2.4, 3.8) * ps;
  var x = ox + vx * a, y = oy + vy * a + 0.5 * CASING_G * ps * a * a;
  var rt = r.uniform(0, Math.PI * 2) + sg * a * r.uniform(0.35, 0.6);
  var fade = a < CASING_LIFE - 8 ? 1 : (CASING_LIFE - a) / 8;
  var hl = (kind === 2 ? 5.5 : 3.6) * ps / 2, hw = (kind === 2 ? 2.4 : 1.5) * ps / 2;
  var ux = Math.cos(rt), uy = Math.sin(rt), nx = -uy, ny = ux;
  function box(a0, a1) {
    return [[x + ux * a0 + nx * hw, y + uy * a0 + ny * hw], [x + ux * a1 + nx * hw, y + uy * a1 + ny * hw],
            [x + ux * a1 - nx * hw, y + uy * a1 - ny * hw], [x + ux * a0 - nx * hw, y + uy * a0 - ny * hw]];
  }
  if (kind === 2) {
    pen.poly(box(-hl, hl * 0.35), HULL, 235 * fade);
    pen.poly(box(hl * 0.35, hl), BRASS, 235 * fade);
  } else pen.poly(box(-hl, hl), BRASS, 235 * fade);
  pen.line(x - ux * hl * 0.8 + nx * hw * 0.4, y - uy * hl * 0.8 + ny * hw * 0.4,
           x + ux * hl * 0.8 + nx * hw * 0.4, y + uy * hl * 0.8 + ny * hw * 0.4,
           L.mix(BRASS, L.HOT, 0.6), 200 * fade, 0.6 * ps);
}
function sparks(pen, inst, key, x, y, ang, cone, a, n, c, ps, spLo, spHi, life0) {
  var L = L_();
  for (var j = 0; j < n; j++) {
    var r = L.rngFor(inst.seed, key, 500 + j), life = life0 * (0.6 + 0.6 * r());
    if (a >= life) continue;
    var an = ang + r.uniform(-cone, cone) * L.D, sp = r.uniform(spLo, spHi) * ps, fd = L.dragDist(0.86, a);
    var sx = x + Math.cos(an) * sp * fd, sy = y + Math.sin(an) * sp * fd + 0.1 * ps * a * a;
    var dk = Math.pow(0.86, a), qq = a / life;
    pen.line(sx, sy, sx - Math.cos(an) * sp * dk * 1.6, sy - Math.sin(an) * sp * dk * 1.6, L.mix(L.HOT, c, qq),
             255 * (1 - qq), 1.3 * ps);
  }
}
function jag(inst, key, x0, y0, x1, y1, n, amp) {   // a jagged lightning line
  var dx = x1 - x0, dy = y1 - y0, Ln = L_().hyp(dx, dy) || 1, nx = -dy / Ln, ny = dx / Ln;
  var r = L_().rngFor(inst.seed, key, 700), pts = [[x0, y0]];
  for (var m = 1; m < n; m++) {
    var u = m / n, o = r.uniform(-1, 1) * amp;
    pts.push([x0 + dx * u + nx * o, y0 + dy * u + ny * o]);
  }
  pts.push([x1, y1]);
  return pts;
}
function spikes(pen, x, y, ang, n, rOut, rIn, c, a) {
  var pts = [];
  for (var j = 0; j < 2 * n; j++) {
    var rr = j % 2 === 0 ? rOut : rIn, an = ang + Math.PI * j / n;
    pts.push([x + Math.cos(an) * rr, y + Math.sin(an) * rr]);
  }
  pen.poly(pts, c, a);
}
// A heavy hit: flash, spiked star, shockwave rings across the line, speed lines, sparks.
function heavy(pen, inst, key, c, ps, x, y, ang, a, life, B, dens) {
  if (a < 0 || a >= life) return;
  var L = L_(), HOT = L.HOT, mix = L.mix, q = a / life, e, j;
  if (a < 5) pen.glow(x, y, B * (0.6 + 0.8 * L.easeOut3(a / 5)), HOT, 255 * (1 - a / 5));
  if (a < 9) {
    e = L.easeOut3(a / 4);
    var qs = a / 9;
    spikes(pen, x, y, ang + 0.2 * qs, 6, B * (0.5 + 0.9 * e), B * (0.2 + 0.2 * e), c, 225 * (1 - qs));
    spikes(pen, x, y, ang + 0.2 * qs, 6, B * (0.3 + 0.5 * e), B * (0.12 + 0.1 * e), HOT, 255 * Math.pow(1 - qs, 1.5));
  }
  pen.glow(x, y, B * (0.9 + 0.7 * L.easeOut3(q)), c, 140 * (1 - q), 0.4);
  var ca = Math.cos(ang), sa = Math.sin(ang);
  [[0, 1.0], [3, 1.4]].forEach(function (dk) {
    var aa = a - dk[0], k = dk[1];
    if (aa < 0) return;
    var qq = aa / (life - dk[0]), ee = L.easeOut3(qq);
    var cx = x + ca * B * 0.4 * ee * k, cy = y + sa * B * 0.4 * ee * k;
    pen.ring(cx, cy, B * (0.15 + 0.45 * ee) * k, B * (0.3 + 1.5 * ee) * k, ang, c, 210 * (1 - qq), 2.6 * ps * (1 - qq) + 0.2);
  });
  if (a < 11) {
    var ql = a / 11;
    for (j = 0; j < 10; j++) {
      var r = L.rngFor(inst.seed, key, 600 + j), an = r.uniform(0, Math.PI * 2);
      var r1 = B * (0.4 + 1.5 * L.easeOut3(ql)) * r.uniform(0.8, 1.2), ln = B * r.uniform(0.4, 0.8) * (1 - ql);
      var cb = Math.cos(an), sb = Math.sin(an);
      pen.line(x + cb * r1, y + sb * r1, x + cb * (r1 + ln), y + sb * (r1 + ln), mix(HOT, c, ql), 230 * (1 - ql), 1.3 * ps);
    }
  }
  sparks(pen, inst, key, x, y, ang + Math.PI, 80, a, Math.max(0, Math.round(9 * dens)), c, ps, 3.0, 7.5, 18);
}
// Fireball: flash, swelling fire, two rings, debris.
function explode(pen, inst, key, c, ps, x, y, a, life, B, dens) {
  if (a < 0 || a >= life) return;
  var L = L_(), HOT = L.HOT, q = a / life, ee = L.easeOut3(a / 9);
  if (a < 6) pen.glow(x, y, B * (0.8 + 0.9 * L.easeOut3(a / 6)), HOT, 255 * (1 - a / 6));
  pen.glow(x, y, B * (1.0 + 0.9 * ee), c, 215 * (1 - q), 0.45);
  pen.glow(x, y, B * (0.55 + 0.5 * ee), L.mix(c, HOT, 0.6), 240 * Math.pow(1 - q, 2));
  [[0, 1.0], [4, 1.5]].forEach(function (dk) {
    var aa = a - dk[0];
    if (aa < 0) return;
    var qq = aa / (life - dk[0]), rr = B * (0.5 + 1.6 * L.easeOut3(qq)) * dk[1];
    pen.ring(x, y, rr, rr * 0.8, 0, c, 190 * (1 - qq), 3.0 * ps * (1 - qq) + 0.2);
  });
  sparks(pen, inst, key, x, y, 0, 180, a, Math.max(0, Math.round(12 * dens)), c, ps, 3.0, 8.0, 22);
}
// Lightning drops from the sky onto (x, y) and crackles outward.
function strike(pen, inst, key, c, ps, x, y, a, life, B, dens) {
  if (a < 0 || a >= life) return;
  var L = L_(), HOT = L.HOT, q = a / life, pts, j;
  if (a < 10) {
    var r = L.rngFor(inst.seed, key, 800), topX = x + r.uniform(-30, 30) * ps, fl = 0.75 + 0.25 * Math.sin(a * 3.1);
    pts = jag(inst, key * 64 + Math.floor(a / 2), topX, y - 170 * ps, x, y, 9, 12 * ps);
    pen.polyline(pts, c, 210 * fl * (1 - a / 10), 4.2 * ps);
    pen.polyline(pts, HOT, 255 * (1 - a / 10), 1.6 * ps);
  }
  if (a < 5) pen.glow(x, y, B * (0.8 + 0.8 * L.easeOut3(a / 5)), HOT, 255 * (1 - a / 5));
  pen.glow(x, y, B * (0.9 + 0.6 * L.easeOut3(q)), c, 160 * (1 - q), 0.4);
  var rr = B * (0.4 + 1.4 * L.easeOut3(q));
  pen.ring(x, y, rr, rr * 0.45, 0, c, 190 * (1 - q), 2.4 * ps * (1 - q) + 0.2);
  if (a < 14) {
    for (j = 0; j < 6; j++) {
      var r2 = L.rngFor(inst.seed, key, 820 + j), an = r2.uniform(0, Math.PI * 2), ln = B * r2.uniform(0.6, 1.1);
      pts = jag(inst, key * 64 + 32 + j + Math.floor(a / 2) * 6, x, y, x + Math.cos(an) * ln, y + Math.sin(an) * ln, 4, 5 * ps);
      pen.polyline(pts, L.mix(c, HOT, 0.5), 230 * (1 - a / 14), 1.2 * ps);
    }
  }
  sparks(pen, inst, key, x, y, -Math.PI / 2, 120, a, Math.max(0, Math.round(6 * dens)), c, ps, 2.5, 6.0, 16);
}
// The drill bursts into spinning shards at the end of its range.
function shatter(pen, inst, key, c, ps, x, y, ang, a, life, B, dens) {
  if (a < 0 || a >= life) return;
  var L = L_(), HOT = L.HOT, q = a / life;
  if (a < 5) pen.glow(x, y, B * (0.6 + 0.6 * L.easeOut3(a / 5)), HOT, 255 * (1 - a / 5));
  pen.glow(x, y, B * (0.7 + 0.6 * L.easeOut3(q)), c, 150 * (1 - q), 0.4);
  var n = Math.max(0, Math.round(8 * dens));
  for (var j = 0; j < n; j++) {
    var r = L.rngFor(inst.seed, key, 900 + j), an = ang + r.uniform(-70, 70) * L.D, sp = r.uniform(2.5, 6.0) * ps;
    var fd = L.dragDist(0.9, a), sx = x + Math.cos(an) * sp * fd, sy = y + Math.sin(an) * sp * fd;
    var sz = B * r.uniform(0.15, 0.3), rt = r.uniform(0, Math.PI * 2) + a * r.uniform(-0.4, 0.4), pts = [];
    for (var k = 0; k < 3; k++) {
      var f = k === 0 ? 1.0 : 0.5;
      pts.push([sx + Math.cos(rt + k * 2.1) * sz * f, sy + Math.sin(rt + k * 2.1) * sz * f]);
    }
    pen.poly(pts, L.mix(c, HOT, 0.5), 230 * (1 - q));
  }
}
function muzzle(pen, inst, g, s, k, c, ps, P) {
  if (k >= g.flash) return;
  var L = L_(), HOT = L.HOT, mix = L.mix, q = k / g.flash, x = s.ox, y = s.oy, h = s.head(0), ux = h[0], uy = h[1];
  var fs = +g.flash_px * ps * s.size * (1 - 0.35 * q), look = s.look, j, m, pts;
  pen.glow(x, y, fs * 1.3, c, 210 * (1 - q));
  pen.glow(x, y, fs * 0.5, HOT, 255 * (1 - q));
  L.star(pen, x, y, ux, uy, fs * 1.4, fs * 0.6, HOT, 235 * (1 - q), 1.6 * ps);
  [-28, 0, 28].forEach(function (dg, jj) {
    var r = L.rngFor(inst.seed, s.i, 120 + jj), ln = fs * (dg === 0 ? 1.2 : 0.75) * r.uniform(0.8, 1.2) * (1 - 0.5 * q);
    var w = FXK().rot([ux, uy], dg);
    pen.diamond(x, y, x + w[0] * ln, y + w[1] * ln, fs * 0.22, mix(c, HOT, 0.5), 230 * (1 - q));
  });
  var ang = Math.atan2(uy, ux), e = L.easeOut3(q);
  if (look === "pellet") {
    var half = ((+P.span || 0) * 0.6 + 6) * L.D, lnc = fs * 2.4 * (0.6 + 0.4 * e);
    pts = [[x, y]];
    for (m = 0; m < 7; m++) {
      var an = ang - half + 2 * half * m / 6;
      pts.push([x + Math.cos(an) * lnc, y + Math.sin(an) * lnc]);
    }
    pen.poly(pts, c, 120 * (1 - q));
    pen.ring(x + ux * fs * 1.4 * e, y + uy * fs * 1.4 * e, fs * (0.3 + 0.5 * e), fs * (0.6 + 1.3 * e), ang, HOT,
             200 * (1 - q), 2.0 * ps * (1 - q) + 0.2);
  } else if (["slug", "orb", "rail", "drill"].indexOf(look) >= 0) {
    if (look === "slug") {
      [1, -1].forEach(function (sd) {
        var jx = x + ux * fs * 0.25, jy = y + uy * fs * 0.25;
        pen.diamond(jx, jy, jx - uy * sd * fs * 0.8, jy + ux * sd * fs * 0.8, fs * 0.16, HOT, 220 * (1 - q));
      });
    }
    [[0, 1.0], [2, 1.5]].forEach(function (dk) {
      var aa = k - dk[0], kk = dk[1];
      if (aa < 0) return;
      var qq = g.flash > dk[0] ? aa / (g.flash - dk[0]) : 1, ee = L.easeOut3(qq);
      pen.ring(x + ux * fs * 0.6 * ee * kk, y + uy * fs * 0.6 * ee * kk, fs * (0.25 + 0.4 * ee) * kk,
               fs * (0.5 + 1.1 * ee) * kk, ang, HOT, 200 * (1 - qq), 2.2 * ps * (1 - qq) + 0.2);
    });
  } else if (look === "rocket") {
    pen.diamond(x, y, x - ux * fs * 1.6, y - uy * fs * 1.6, fs * 0.35, mix(c, HOT, 0.3), 200 * (1 - q));
  }
  if (L.style(P) === "dual_pistols") {
    // gun-kata: the swing arc of the hand that fired
    var sd2 = s.v % 2 === 0 ? 1 : -1;
    pts = [];
    for (m = 0; m < 9; m++) {
      var an2 = ang + sd2 * (-0.9 + 1.4 * m / 8);
      pts.push([x + Math.cos(an2) * 14 * ps, y + Math.sin(an2) * 14 * ps]);
    }
    pen.polyline(pts, mix(c, HOT, 0.4), 200 * (1 - q), 2.0 * ps * (1 - q) + 0.3);
  }
}
function fadeOf(s, k, stopped) {
  if (stopped) return 1;
  return minmax((s.flight - k) / Math.max(1, s.flight * FADE_TAIL), 0, 1);
}
// A round in flight, k ticks after launch.
function drawRound(pen, inst, s, k, t, c, tint, ps, P, stopped) {
  var L = L_(), HOT = L.HOT, mix = L.mix, r = +P.radius * ps * s.size, p = s.pos(k), x = p[0], y = p[1];
  var h = s.head(k), ux = h[0], uy = h[1], look = s.look, j, m, tp, pts;
  var fa = ["tracer", "pellet", "slug"].indexOf(look) >= 0 ? fadeOf(s, k, stopped) : 1;
  if (look === "tracer") {
    tp = s.pos(Math.max(0, k - TRACER_TAIL));
    pen.diamond(tp[0], tp[1], x, y, r * 1.1, c, 150 * fa);
    pen.line(tp[0], tp[1], x, y, tint, 230 * fa, r * 0.9);
    pen.glow(x, y, r * 3.0, c, 110 * fa);
    pen.glow(x, y, r * 1.2, HOT, 255 * fa, 0.7);
  } else if (look === "pellet") {
    tp = s.pos(Math.max(0, k - 1.6));
    pen.diamond(tp[0], tp[1], x, y, r * 0.9, c, 160 * fa);
    pen.glow(x, y, r * 2.4, c, 120 * fa);
    pen.glow(x, y, r, HOT, 255 * fa, 0.7);
  } else if (look === "slug") {
    var ang = Math.atan2(uy, ux);
    for (j = 0; j < 4; j++) {
      var kj = k - (j + 1) * 0.8;
      if (kj < 0) break;
      var gp = s.pos(kj);
      pen.ring(gp[0], gp[1], r * 0.7, r * (1.6 + 0.5 * j), ang, mix(c, HOT, 0.3), 170 * (1 - j / 4) * fa, 1.3 * ps);
    }
    tp = s.pos(Math.max(0, k - 2.6));
    pen.diamond(tp[0], tp[1], x, y, r * 1.3, c, 150 * fa);
    pen.diamond(tp[0], tp[1], x, y, r * 0.5, HOT, 230 * fa);
    pen.glow(x, y, r * 3.6, c, 130 * fa);
    pen.glow(x, y, r * 1.5, HOT, 255 * fa, 0.7);
  } else if (look === "orb") {
    var fl = 0.88 + 0.12 * Math.sin(t * 1.7);
    [[4, 40], [2, 70]].forEach(function (ja) {
      var g = s.pos(Math.max(0, k - ja[0]));
      pen.glow(g[0], g[1], r * 1.8, c, ja[1]);
    });
    tp = s.pos(Math.max(0, k - 5));
    pen.diamond(tp[0], tp[1], x, y, r * 1.0, c, 120);
    pen.diamond(tp[0], tp[1], x, y, r * 0.45, tint, 200);
    pen.glow(x, y, r * 2.6 * fl, c, 140);
    pen.glow(x, y, r * 1.4, tint, 230);
    pen.glow(x, y, r * 0.7, HOT, 255, 0.75);
    for (j = 0; j < 2; j++) pen.ring(x, y, r * 1.3, r * 0.45, t * 0.35 + j * Math.PI / 2, HOT, 170, 1.4 * ps);
  } else if (look === "rocket") {
    var r2 = L.rngFor(inst.seed, s.i, 140 + t % 16), ln = r * (2.6 + 1.6 * r2());
    var bx = x - ux * r * 1.6, by = y - uy * r * 1.6;
    pen.diamond(bx, by, bx - ux * ln, by - uy * ln, r * 0.55, c, 220);
    pen.diamond(bx, by, bx - ux * ln * 0.6, by - uy * ln * 0.6, r * 0.25, HOT, 255);
    pen.glow(bx, by, r * 2.2, c, 150);
  } else if (look === "drill") {
    var R = r, nx = -uy, ny = ux, dbx = x - ux * R * 0.6, dby = y - uy * R * 0.6, tipx = x + ux * R * 2.4, tipy = y + uy * R * 2.4;
    // spiral of wind behind it
    [1, -1].forEach(function (sd) {
      var ps_ = [];
      for (var mm = 0; mm < 15; mm++) {
        var db = mm * R * 0.9, lat = sd * Math.sin(t * 0.9 + mm * 0.7) * R * (1.3 - mm * 0.06);
        ps_.push([dbx - ux * db + nx * lat, dby - uy * db + ny * lat]);
      }
      pen.polyline(ps_, c, 150, 1.4 * ps);
    });
    pen.glow(x, y, R * 2.8, c, 120);
    pen.poly([[tipx, tipy], [dbx + nx * R * 1.05, dby + ny * R * 1.05], [dbx - nx * R * 1.05, dby - ny * R * 1.05]], c, 200);
    pen.poly([[tipx, tipy], [dbx + nx * R * 0.55, dby + ny * R * 0.55], [dbx - nx * R * 0.55, dby - ny * R * 0.55]],
             mix(c, HOT, 0.6), 220);
    for (j = 0; j < 4; j++) {
      var pp = frac(t * DRILL_SPIN + j / 4), p2 = Math.min(1, pp + 0.18);
      var ax = dbx + (tipx - dbx) * pp + nx * R * 1.05 * (1 - pp), ay = dby + (tipy - dby) * pp + ny * R * 1.05 * (1 - pp);
      var cx = dbx + (tipx - dbx) * p2 - nx * R * 1.05 * (1 - p2), cy = dby + (tipy - dby) * p2 - ny * R * 1.05 * (1 - p2);
      pen.line(ax, ay, cx, cy, HOT, 200, 1.2 * ps);
    }
  } else if (look === "bolt") {
    var d = s.sp * k, d0 = Math.max(0, d - 160 * ps);
    var n = Math.max(1, Math.min(24, Math.trunc((d - d0) / (BOLT_SEG * ps)) + 1));
    var rr = L.rngFor(inst.seed, s.i, 400 + Math.floor(t / 2));
    pts = [];
    for (m = 0; m < n + 1; m++) {
      var dm = d0 + (d - d0) * m / n, o = m === n ? 0 : rr.uniform(-7, 7) * ps;
      var w = s.fr.d(Math.cos(s.ang) * dm, Math.sin(s.ang) * dm);
      pts.push([s.ox + w[0] - uy * o, s.oy + w[1] + ux * o]);
    }
    var flb = 0.7 + 0.3 * Math.sin(t * 2.7 + s.i);
    pen.polyline(pts, c, 150 * flb, 2.6 * ps);
    pen.polyline(pts, HOT, 200 * flb, 1.0 * ps);
    tp = s.pos(Math.max(0, k - 2));
    pen.diamond(tp[0], tp[1], x, y, r * 0.9, c, 160);
    pen.glow(x, y, r * 3.0, c, 140);
    pen.glow(x, y, r * 1.4, HOT, 255, 0.7);
    for (j = 0; j < 3; j++) {
      var ra = L.rngFor(inst.seed, s.i, 420 + Math.floor(t / 2) * 3 + j), an = ra.uniform(0, Math.PI * 2);
      var px = x, py = y, arc = [[px, py]];
      for (m = 0; m < 3; m++) {
        an += ra.uniform(-0.9, 0.9);
        px = px + Math.cos(an) * r * 1.6; py = py + Math.sin(an) * r * 1.6;
        arc.push([px, py]);
      }
      pen.polyline(arc, c, 150, 2.4 * ps);
      pen.polyline(arc, HOT, 220, 1.1 * ps);
    }
  }
}
function impact(pen, inst, s, a, x, y, stopped, c, ps, P, dens) {
  var L = L_(), look = s.look, life = IMPACT_LIFE[look], B = +P.thickness * ps * s.size;
  var h = s.head(!stopped ? s.flight : Math.max(0, inst.tq_ki[s.i][0] - s.b)), ang = Math.atan2(h[1], h[0]);
  var key = s.i * 4 + 1;
  if (look === "tracer" || look === "pellet") {
    if (a >= life) return;
    var sc = look === "pellet" ? 0.7 : 1.0, q = a / life;
    if (a < 3) pen.glow(x, y, B * (0.5 + 0.5 * L.easeOut3(a / 3)) * sc, L.HOT, 255 * (1 - a / 3));
    pen.glow(x, y, B * (0.8 + 0.8 * L.easeOut3(q)) * sc, c, 180 * (1 - q), 0.4);
    sparks(pen, inst, key, x, y, ang + Math.PI, 70, a, Math.max(0, Math.round(4 * dens)), c, ps, 2.0, 5.5, 12);
  } else if (look === "slug") heavy(pen, inst, key, c, ps, x, y, ang, a, life, B, dens);
  else if (look === "orb" || look === "rocket") explode(pen, inst, key, c, ps, x, y, a, life, B, dens);
  else if (look === "bolt") strike(pen, inst, key, c, ps, x, y, a, life, B, dens);
  else if (look === "drill") shatter(pen, inst, key, c, ps, x, y, ang, a, life, B, dens);
}
function gatPhi(P, t) {
  var c = cad(P), h = hold(P), w = GAT_SPIN;
  if (t <= c) return 0.5 * w * t * t / c;
  if (t <= c + h) return 0.5 * w * c + w * (t - c);
  var k = Math.min(t - c - h, GAT_SPIN_DOWN);
  return 0.5 * w * c + w * h + w * (k - 0.5 * k * k / GAT_SPIN_DOWN);
}
function drawGatling(pen, inst, P, c, ps, t, fired, total) {
  var L = L_(), endf = cad(P) + hold(P);
  if (t > endf + GAT_SPIN_DOWN) return;
  var am = aim(inst, t), ox = am[0], oy = am[1], f = am[2];
  var fade = t <= endf ? 1 : 1 - (t - endf) / GAT_SPIN_DOWN, phi = gatPhi(P, t), nx = -f[1], ny = f[0];
  var mx = ox + f[0] * 4 * ps, my = oy + f[1] * 4 * ps;
  pen.ring(mx, my, 2.0 * ps, 6.0 * ps, Math.atan2(f[1], f[0]), c, 170 * fade, 1.2 * ps);
  for (var j = 0; j < 6; j++) {
    var an = phi + j * Math.PI / 3, lat = Math.cos(an) * 5 * ps, dep = Math.sin(an) * 1.6 * ps;
    pen.glow(mx + nx * lat + f[0] * dep, my + ny * lat + f[1] * dep, 2.6 * ps, c, 200 * fade * (0.6 + 0.4 * Math.sin(an)));
  }
  var heat = fired / Math.max(1, total);
  pen.glow(mx, my, 10 * ps, L.mix([255, 90, 30], c, 0.3), 170 * heat * fade);
  pen.glow(mx, my, 4 * ps, L.mix([255, 200, 120], L.HOT, 0.3), 200 * heat * fade);
}
function drawCharge(pen, inst, P, c, tint, ps, t, b, dens) {
  if (t > b) return;
  var L = L_(), HOT = L.HOT, c0 = cad(P), am = aim(inst, t), f = am[2], j, pts;
  var mx = am[0] + f[0] * 6 * ps, my = am[1] + f[1] * 6 * ps, R = +P.radius * ps;
  var e = L.easeOut3(t / c0), fl = 0.85 + 0.15 * Math.sin(t * 1.3), rr = R * (0.25 + 0.85 * e);
  pen.glow(mx, my, rr * 2.4 * fl, c, 150);
  pen.glow(mx, my, rr * 1.3, tint, 220);
  pen.glow(mx, my, rr * 0.6, HOT, 255, 0.75);
  var n = Math.max(0, Math.round(12 * dens));
  for (j = 0; j < n; j++) {
    var r0 = L.rngFor(inst.seed, j, 640), off = r0.uniform(0, CHARGE_P);
    var cyc = Math.floor((t + off) / CHARGE_P), p = frac((t + off) / CHARGE_P);
    var r = L.rngFor(inst.seed, j, 650 + cyc), an = r.uniform(0, Math.PI * 2), rad = r.uniform(36, 70) * ps;
    var d = rad * (1 - L.easeIn3(p)) + rr * 0.6, d2 = d + rad * 0.25 * (1 - p), ca = Math.cos(an), sa = Math.sin(an);
    pen.line(mx + ca * d, my + sa * d, mx + ca * d2, my + sa * d2, L.mix(c, HOT, p), 230 * p, 1.4 * ps);
  }
  if (t < c0) {
    for (var m = 0; m < 2; m++) {
      var q = frac((t + m * CHARGE_RING) / (2 * CHARGE_RING)), rg = 50 * ps * (1 - L.easeIn3(q)) + rr * 0.3;
      pen.ring(mx, my, rg, rg, 0, c, 180 * q, 1.6 * ps);
    }
  } else {
    var a = t - c0;
    if (a < 5) L.star(pen, mx, my, 1, 0, R * 3.2 * (1 - a / 5), R * 3.2 * (1 - a / 5), HOT, 255 * (1 - a / 5), 2.0 * ps);
    if (e > 0.6) {
      for (j = 0; j < 2; j++) {
        var ra = L.rngFor(inst.seed, j, 680 + Math.floor(t / 2)), an2 = ra.uniform(0, Math.PI * 2);
        pts = jag(inst, 690 + Math.floor(t / 2) * 2 + j, mx, my, mx + Math.cos(an2) * rr * 2.2, my + Math.sin(an2) * rr * 2.2, 3, 3 * ps);
        pen.polyline(pts, HOT, 200, 1.0 * ps);
      }
    }
  }
}
function drawAim(pen, inst, P, c, ps, t, b) {
  if (t >= b) return;
  var L = L_(), HOT = L.HOT, am = aim(inst, t), ox = am[0], oy = am[1], f = am[2], Lp = +P.length * ps;
  var e = L.easeOut3(t / Math.max(1, b)), fl = 0.6 + 0.4 * Math.sin(t * 2.1), ex = ox + f[0] * Lp, ey = oy + f[1] * Lp;
  pen.line(ox, oy, ex, ey, c, 120 * fl, 1.0 * ps);
  pen.line(ox, oy, ex, ey, HOT, 150 * fl, 0.5 * ps);
  if (tracks(inst)) {
    var tp = at(inst.tq_tp, t);
    if (L.hyp(tp[0] - ox, tp[1] - oy) < Lp) { ex = tp[0]; ey = tp[1]; }
  }
  var rad = (26 - 18 * e) * ps;
  pen.ring(ex, ey, rad, rad, 0, c, 210, 1.4 * ps);
  var rt = (1 - e) * Math.PI / 2;
  for (var j = 0; j < 4; j++) {
    var an = rt + j * Math.PI / 2, ca = Math.cos(an), sa = Math.sin(an);
    pen.line(ex + ca * rad * 0.6, ey + sa * rad * 0.6, ex + ca * rad * 1.4, ey + sa * rad * 1.4, HOT, 230, 1.2 * ps);
  }
  if (e > 0.8 && t % 4 < 2) pen.glow(ex, ey, 4 * ps, HOT, 255);
  if (b - t <= 6) {
    var q = (b - t) / 6;
    L.star(pen, ox, oy, f[0], f[1], 14 * ps * (1 - q) + 2, 14 * ps * (1 - q) + 2, HOT, 255 * (1 - q), 1.4 * ps);
  }
}
function drawRail(pen, inst, s, P, c, ps, t, dens) {
  var L = L_(), HOT = L.HOT, k = t - s.b, linger = Math.max(1, hold(P));
  if (k < 0) return;
  var ln = railLine(s), x0 = ln[0], y0 = ln[1], x1 = ln[2], y1 = ln[3], h = s.head(0), ux = h[0], uy = h[1];
  var nx = -uy, ny = ux, Lr = s.rng;
  if (k < linger) {
    var q = k / linger, W = +P.radius * ps * (k < 2 ? 2.2 : 1.0) * (1 - q);
    pen.line(x0, y0, x1, y1, c, 200 * (1 - q), W * 2.6 + 0.3);
    pen.line(x0, y0, x1, y1, HOT, 255 * Math.pow(1 - q, 1.5), W + 0.2);
    var amp = +P.radius * ps * (1.8 + 2.4 * L.easeOut3(q));
    [0, 1].forEach(function (sd) {
      var pts = [];
      for (var m = 0; m < 41; m++) {
        var d = Lr * m / 40, lat = Math.sin(d / (14 * ps) + sd * Math.PI + k * 0.5) * amp;
        pts.push([x0 + ux * d + nx * lat, y0 + uy * d + ny * lat]);
      }
      pen.polyline(pts, L.mix(c, HOT, 0.3), 170 * (1 - q), 1.3 * ps);
    });
    [0.15, 0.4, 0.65, 0.9].forEach(function (fr_, j) {
      var aa = k - j;
      if (aa < 0) return;
      var qq = Math.min(1, aa / linger), ee = L.easeOut3(qq);
      pen.ring(x0 + ux * Lr * fr_, y0 + uy * Lr * fr_, (2 + 6 * ee) * ps, (6 + 22 * ee) * ps, Math.atan2(uy, ux), c,
               170 * (1 - qq), 1.8 * ps * (1 - qq) + 0.2);
    });
  }
  var life = IMPACT_LIFE.rail, B = +P.thickness * ps;
  inst.tq_imp.forEach(function (im, n) {
    var a = t - im[0] - RAIL_DELAY;
    if (a < 0) { if (t >= im[0]) pen.glow(im[1], im[2], 6 * ps, HOT, 230); return; }
    heavy(pen, inst, 9000 + n, c, ps, im[1], im[2], Math.atan2(uy, ux), a, life, B, dens);
  });
}

function draw(pen, inst, host, ps) {
  var L = L_(), HOT = L.HOT, mix = L.mix, P = inst.fx.params, st = L.style(P), g = GUNS[st], t = inst.age;
  var cs = L.colours(inst, host), c = cs[0], deep = cs[2], dens = +P.density || 1;
  var all = rounds(inst, ps), smoke = mix(SMOKE, deep, 0.25), lb = launches(P), i, s, k, en, bl, h, m;
  // 1: smoke, casings and rocket bodies (painted normally, under the light)
  pen.add(false);
  var nDust = Math.max(0, Math.round(g.dust * dens)), nSmoke = Math.max(0, Math.round(g.smoke * dens));
  for (i = 0; i < all.length; i++) {
    s = all[i]; k = t - s.b;
    if (s.j === 0) {
      h = s.head(0);
      if (nSmoke) puffs(pen, inst, s.i * 4 + 2, s.ox + h[0] * 8 * ps, s.oy + h[1] * 8 * ps, k, SMOKE_LIFE, nSmoke,
                        +g.flash_px * 0.7 * ps, ps, smoke, 0.45);
      if (g.shells && dens > 0) casing(pen, inst, s.i * 4 + 3, s.ox, s.oy, h[0], k, ps, g.shells);
    }
    if (s.look === "rail") {
      inst.tq_imp.forEach(function (im, n) {
        puffs(pen, inst, 9100 + n, im[1], im[2], t - im[0] - RAIL_DELAY, SMOKE_LIFE, nDust, +P.thickness * 0.6 * ps, ps, smoke, 0.35);
      });
      continue;
    }
    en = s.end(inst);
    if (s.look === "rocket") {
      // smoke trail, then the missile itself
      for (var kp = 0; kp < Math.min(k, en[0] - s.b); kp += ROCKET_PUFF) {
        var pp = s.pos(kp);
        puffs(pen, inst, 20000 + s.i * 64 + Math.floor(kp / ROCKET_PUFF), pp[0], pp[1], k - kp, 30, 1,
              +P.radius * 1.6 * ps, ps, smoke, 0.15);
      }
      if (t < en[0]) {
        var r = +P.radius * ps * s.size, p = s.pos(k), hd = s.head(k), x = p[0], y = p[1], ux = hd[0], uy = hd[1];
        var nx = -uy, ny = ux, body = mix(STEEL, c, 0.15);
        var w = function (a, l) { return [x + ux * a * r + nx * l * r, y + uy * a * r + ny * l * r]; };
        pen.poly([w(2.2, 0), w(1.0, 0.6), w(-1.6, 0.6), w(-1.6, -0.6), w(1.0, -0.6)], body, 245);
        pen.poly([w(-0.6, 0.6), w(-1.7, 1.3), w(-1.7, 0.6)], c, 245);
        pen.poly([w(-0.6, -0.6), w(-1.7, -1.3), w(-1.7, -0.6)], c, 245);
        pen.poly([w(1.4, 0.45), w(1.0, 0.6), w(1.0, -0.6), w(1.4, -0.45)], c, 245);
      }
    }
    bl = blastAt(inst, s);
    if (bl && nDust) puffs(pen, inst, s.i * 4 + 1, bl[1], bl[2], t - bl[0], SMOKE_LIFE, nDust,
                           +P.thickness * 0.6 * ps * s.size, ps, smoke, 0.35);
  }
  if (st === "gatling" && t > lb[lb.length - 1]) {
    var mp = at(inst.tq_path, t);
    for (m = 0; m < 4; m++) {
      puffs(pen, inst, 9200 + m, mp[0], mp[1] - 4 * ps, t - lb[lb.length - 1] - m * 3, SMOKE_LIFE,
            Math.max(0, Math.round(2 * dens)), 6 * ps, ps, smoke, 0.6);
    }
  }
  pen.add(true);
  // 2: the gun itself before / while it fires
  if (st === "gatling") {
    var fired = 0;
    for (i = 0; i < lb.length; i++) if (lb[i] <= t) fired += 1;
    drawGatling(pen, inst, P, c, ps, t, fired, lb.length);
  } else if (st === "charged_blast") drawCharge(pen, inst, P, c, mix(c, HOT, 0.4), ps, t, lb[0], dens);
  else if (st === "sniper_rail") drawAim(pen, inst, P, c, ps, t, lb[0]);
  // 3: muzzle flashes, rounds in flight and where they land
  for (i = 0; i < all.length; i++) {
    s = all[i]; k = t - s.b;
    if (s.j === 0) muzzle(pen, inst, g, s, k, c, ps, P);
    if (s.look === "rail") { drawRail(pen, inst, s, P, c, ps, t, dens); continue; }
    en = s.end(inst);
    if (t < en[0]) { drawRound(pen, inst, s, k, t, c, mix(c, HOT, 0.25 + s.tint), ps, P, en[1]); continue; }
    bl = blastAt(inst, s);
    if (bl) impact(pen, inst, s, t - bl[0], bl[1], bl[2], bl[3], c, ps, P, dens);
  }
  if (g.look === "drill") {
    inst.tq_imp.forEach(function (im, n) {
      heavy(pen, inst, 9300 + n, c, ps, im[1], im[2], 0, t - im[0], IMPACT_LIFE.drill, +P.thickness * ps, dens);
    });
  }
}

G.GUNFX = {STYLES: STYLES, GUNS: GUNS, draw: draw, hit: hit, onHit: onHit, activeTicks: activeTicks, totalTicks: totalTicks,
           launches: launches, livePoints: livePoints, shotIds: shotIds, shotAt: shotAt, place: place, trackStep: trackStep};
})(window);
