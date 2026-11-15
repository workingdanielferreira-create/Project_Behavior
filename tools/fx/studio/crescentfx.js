/* Crescent waves — FX Studio's port of laser/crescentfx.py: six more
 * travelling crescents of the FX Kit "technique" primitive (ground drag, twin
 * helix, barrage, returning moon, splitting moon, moonfall).  Same timeline,
 * same random streams (FXK.rng), same geometry and painting order as the
 * game, so the Studio preview draws what Solo and Battle draw.  Keep the two
 * in step.  Builds on swordfx.js (pen, maths, colours): load it after it.
 *
 * The ground itself (trench, rocks, dust, craters under the ground drag and
 * the moonfall) belongs to the world (laser/worldfx.py) and shows in the game.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };
var STYLES = ["crescent_drag", "crescent_helix", "crescent_scatter", "crescent_return", "crescent_split", "crescent_fall"];
var GROUND_STYLES = ["crescent_drag", "crescent_fall"];
var SCATTER_PATHS = ["fan", "converge", "wild"];
var ARC_DEG = 95, CX = -0.5, EMBER_LIFE = 30, SHARD_LIFE = 26;
var FALL_WIND = 6, FALL_SLAM = 4, DRAG_MIN_X = 0.3, MAX_MOONS = 12;
var HOT = [255, 255, 255], D = Math.PI / 180;

// ---------------------------------------------------------------- params / timeline
function num(P, k, d) { var v = P[k]; return v === undefined || v === null || v === "" ? d : +v; }
function count(P) { return Math.max(1, Math.min(MAX_MOONS, Math.trunc(num(P, "moons", 5)))); }
function hold(P) { return Math.max(1, Math.trunc(+P.hold_ticks || 48)); }
function impactTick(P) { return FALL_WIND + L_().swing(P); }
function activeTicks(P) {
  var st = L_().style(P);
  if (st === "crescent_scatter") return (count(P) - 1) * L_().swing(P) + hold(P);
  if (st === "crescent_fall") return impactTick(P) + Math.max(FALL_SLAM, Math.trunc(+P.hold_ticks || 0));
  return hold(P);
}
function totalTicks(P) { return activeTicks(P) + EMBER_LIFE; }

// ---------------------------------------------------------------- frames / geometry
// Local -> world with any two axes: a = forward (+x), b = down (+y).
function Fr(ox, oy, ax, ay, bx, by) { this.ox = ox; this.oy = oy; this.ax = ax; this.ay = ay; this.bx = bx; this.by = by; }
Fr.prototype.w = function (x, y) { return [this.ox + x * this.ax + y * this.bx, this.oy + x * this.ay + y * this.by]; };
Fr.prototype.d = function (x, y) { return [x * this.ax + y * this.bx, x * this.ay + y * this.by]; };
function fr_(x, y, dx, dy, m) { return new Fr(x, y, dx, dy, -dy * m, dx * m); }
function hyp(x, y) { return Math.sqrt(x * x + y * y); }
function unit(x, y) { var n = hyp(x, y) || 1; return [x / n, y / n]; }
function taper(v) { return Math.pow(1 - Math.pow(Math.abs(v), 1.8), 0.85); }
// [[v, outer, dir, w]] along the blade, top -> bottom (half: top -> middle, the fin).
function pts_(R, W, k, M, half) {
  var out = [], n = half ? Math.floor(M / 2) : M;
  for (var j = 0; j <= n; j++) {
    var v = -1 + 2 * j / M, a = v * ARC_DEG * D, dx = Math.cos(a), dy = Math.sin(a);
    out.push([v, [(CX * R + R * dx) * k, R * dy * k], [dx, dy], W * k * taper(v)]);
  }
  return out;
}
function grow(tl, ea) {
  var g = 0.35 + 0.65 * L_().easeOut3(tl / 5);
  if (ea >= 0) g *= 1 + 0.25 * L_().cl(ea / 8);
  return g;
}
// Where the instance was at age b (its own path, whatever its Motion).
function pos(inst, b) { var p = inst.tq_path; return p[Math.max(0, Math.min(p.length - 1, Math.trunc(b)))]; }
function spd_(inst) {
  var p = inst.tq_path;
  if (p.length > 1) return hyp(p[1][0] - p[0][0], p[1][1] - p[0][1]);
  return hyp(inst.vx, inst.vy);
}
// Distance from the launch point to where the target stood, along the aim.
function reach(inst, ps) {
  var o = inst.tq_o, f = inst.tq_f, tp = inst.tq_tp[0];
  return Math.max(60 * ps, (tp[0] - o[0]) * f[0] + (tp[1] - o[1]) * f[1]);
}
function gp_(inst, ps) { return num(inst.fx.params, "ground_px", 30) * ps; }
// Where a ground style touches the ground now.
function groundPoint(inst, ps) {
  var p = pos(inst, Math.min(inst.age, activeTicks(inst.fx.params)));
  return [p[0], p[1] + gp_(inst, ps)];
}
function onGround(inst) { return inst.fx.prim === "technique" && GROUND_STYLES.indexOf(L_().style(inst.fx.params)) >= 0; }
// Launch tick, angle, speed and size of every moon of a barrage.
function scatterPlan(inst, P, n) {
  var L = L_(), T = (n - 1) * L.swing(P), r = L.rngFor(inst.seed, 0, 211), us = [], keys = [], order = [], rank = [], i;
  for (i = 0; i < Math.max(0, n - 2); i++) us.push(r());
  us.sort(function (a, b) { return a - b; });
  us = [0].concat(us, n > 1 ? [1] : []);
  for (i = 0; i < n; i++) { keys.push(L.rngFor(inst.seed, i, 227)()); order.push(i); }
  order.sort(function (a, b) { return keys[a] - keys[b]; });
  order.forEach(function (i2, p) { rank[i2] = p; });
  var span = num(P, "span", 70), plan = [];
  for (i = 0; i < n; i++) {
    var q = L.rngFor(inst.seed, i, 223);
    var ang = (-0.5 + (rank[i] + 0.15 + 0.7 * q()) / n) * span;
    var sp = q.uniform(0.8, 1.35), sz = q.uniform(0.5, 0.72), wf = q.uniform(0.3, 0.66), wph = q.uniform(0, Math.PI * 2);
    if (i === n - 1 && n > 1) sz = 0.9;        // the last one out is the heavy one
    plan.push([Math.round(T * us[i]), ang, sp, sz, wf, wph]);
  }
  return plan;
}

// ---------------------------------------------------------------- the moons
// Every blade of the technique at age t:
// [[index, frame, size, fade, own age, half, ticks since it ended (< 0 = live)]].
function moons(inst, ps, t) {
  var L = L_(), P = inst.fx.params, st = L.style(P), f = inst.tq_f, m = inst.tq_m, o = inst.tq_o;
  var R = +P.radius * ps, W = +P.thickness * ps, Lf = activeTicks(P), tl = Math.min(t, Lf), ea = t - Lf;
  if (ea >= SHARD_LIFE || t < 0) return [];
  var fade = ea < 0 ? 1 : 1 - L.cl(ea / 8), nx = -f[1] * m, ny = f[0] * m;
  var p, k, n, d0, s, out, i, d, lat, dl, u, q;
  if (st === "crescent_drag") {
    p = pos(inst, tl); k = grow(tl, ea);
    var sx = (m >= 0 ? 1 : -1) * Math.max(Math.abs(f[0]), DRAG_MIN_X);
    var off = (CX + 1) * R * k - 0.5 * W * k;        // frame origin -> the middle of the base
    return [[0, new Fr(p[0] - sx * off, p[1] + gp_(inst, ps) - f[1] * off, sx, f[1], 0, 1), k, fade, tl, true, ea]];
  }
  if (st === "crescent_return") {
    p = pos(inst, tl);
    d = FXK().rot([f[0], f[1]], num(P, "spin_deg", 34) * tl * m);
    return [[0, fr_(p[0], p[1], d[0], d[1], m), grow(tl, ea), fade, tl, false, ea]];
  }
  if (st === "crescent_helix") {
    n = count(P);
    var wv = Math.max(0.25, num(P, "weaves", 2)), A = num(P, "span", 55) * ps;
    d0 = reach(inst, ps); p = pos(inst, tl); s = hyp(p[0] - o[0], p[1] - o[1]); k = grow(tl, ea);
    var sph = (inst.seed % 1000) * 0.01;
    out = [];
    for (i = 0; i < n; i++) {
      var ph = Math.PI * wv * s / d0 + 2 * Math.PI * i / n;
      var Ai = A * (1 + 0.22 * Math.sin(s * 0.021 / ps + i * 2.4 + sph));
      lat = Ai * Math.sin(ph); dl = Ai * Math.cos(ph) * Math.PI * wv / d0;
      u = unit(f[0] + nx * dl, f[1] + ny * dl);
      out.push([i, fr_(p[0] + nx * lat, p[1] + ny * lat, u[0], u[1], m), k * (0.74 + 0.26 * Math.cos(ph)), fade, tl, false, ea]);
    }
    return out;
  }
  if (st === "crescent_scatter") {
    n = count(P);
    var H = hold(P), mode = P.scatter_path, spd = spd_(inst);
    d0 = reach(inst, ps); out = [];
    scatterPlan(inst, P, n).forEach(function (pl, i2) {
      var b = pl[0], ang = pl[1], sp = pl[2], sz = pl[3], wf = pl[4], wph = pl[5], ti = t - b;
      if (ti < 0 || ti - H >= SHARD_LIFE) return;
      var tt = Math.min(ti, H), e2 = ti - H, s2 = spd * sp * tt, x, y, dx, dy;
      if (mode === "converge") {
        var amp = Math.sin(ang * D) * d0 * 0.6;
        var la = amp * Math.sin(Math.PI * s2 / d0), dla = amp * Math.cos(Math.PI * s2 / d0) * Math.PI / d0;
        x = o[0] + f[0] * s2 + nx * la; y = o[1] + f[1] * s2 + ny * la;
        var uu = unit(f[0] + nx * dla, f[1] + ny * dla); dx = uu[0]; dy = uu[1];
      } else {
        var dd = FXK().rot([f[0], f[1]], ang * m);
        x = o[0] + dd[0] * s2; y = o[1] + dd[1] * s2; dx = dd[0]; dy = dd[1];
        if (mode === "wild") {
          var wb = 18 * ps * Math.min(1, tt / 6);
          x += -dd[1] * wb * Math.sin(tt * wf + wph);
          y += dd[0] * wb * Math.sin(tt * wf + wph);
          var d2 = FXK().rot([dd[0], dd[1]], 16 * Math.cos(tt * wf + wph) * Math.min(1, tt / 6));
          dx = d2[0]; dy = d2[1];
        }
      }
      out.push([i2, fr_(x, y, dx, dy, m), grow(tt, e2) * sz, e2 < 0 ? 1 : 1 - L.cl(e2 / 8), tt, false, e2]);
    });
    return out;
  }
  if (st === "crescent_split") {
    n = count(P); d0 = reach(inst, ps);
    var ss = L.cl(num(P, "split_pct", 45) / 100) * d0;
    p = pos(inst, tl); s = hyp(p[0] - o[0], p[1] - o[1]);
    if (s < ss) return [[0, fr_(p[0], p[1], f[0], f[1], m), grow(tl, ea) * (1 + 0.07 * Math.sin(tl * 1.3)), fade, tl, false, ea]];
    var run = Math.max(1, d0 - ss), us = Math.min((s - ss) / run, 1.5), ts = (s - ss) / Math.max(0.01, spd_(inst));
    var A2 = num(P, "span", 110) * ps;
    out = [];
    for (i = 0; i < n; i++) {
      q = L.rngFor(inst.seed, i, 241);
      var w = -1 + 2 * (i + 0.2 + 0.6 * q()) / n;
      var stag = q.uniform(-0.7, 0.7) * R * Math.min(1, ts / 6), sz2 = q.uniform(0.5, 0.68);
      lat = A2 * w * Math.sin(Math.PI * us);
      dl = us < 1.5 ? A2 * w * Math.cos(Math.PI * us) * Math.PI / run : 0;
      u = unit(f[0] + nx * dl, f[1] + ny * dl);
      out.push([i + 1, fr_(p[0] + f[0] * stag + nx * lat, p[1] + f[1] * stag + ny * lat, u[0], u[1], m), grow(ts, ea) * sz2, fade, tl, false, ea]);
    }
    return out;
  }
  // crescent_fall
  if (t < FALL_WIND) return [];
  var Ts = L.swing(P);
  p = pos(inst, tl);
  var gy = p[1] + gp_(inst, ps), th = num(P, "fall_angle_deg", 18) * D, ax = Math.sin(th) * m, ay = Math.cos(th);
  var uf = (t - FALL_WIND) / Ts, h = (+P.length || 0) * ps * (1 - L.easeIn3(uf));
  k = 0.6 + 0.4 * L.cl(uf);
  if (uf >= 1) k *= 1 + 0.05 * Math.sin(t * 2.1) * Math.max(0, 1 - (uf - 1) * Ts / 10);
  if (ea >= 0) k *= 1 + 0.25 * L.cl(ea / 8);
  var nose = (CX + 1) * R * k;
  return [[0, fr_(p[0] - ax * (h + nose), gy - ay * (h + nose), ax, ay, m), k, fade, t, false, ea]];
}
function mid_(fr, pts) { return pts.map(function (q) { return fr.w(q[1][0] - q[2][0] * q[3] * 0.5, q[1][1] - q[2][1] * q[3] * 0.5); }); }

// ---------------------------------------------------------------- public: hit / body
function hit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var P = inst.fx.params, st = L_().style(P), R = +P.radius * ps, W = +P.thickness * ps;
  if (st === "crescent_fall") {
    var a = inst.age - impactTick(P);
    if (a < -2) return false;
    if (a >= 0 && a < FALL_SLAM) {
      var g = groundPoint(inst, ps);
      if (hyp(tx - g[0], (ty - g[1]) * 2) <= hr + 1.2 * R) return true;
    }
  }
  var mo = moons(inst, ps, inst.age);
  for (var i = 0; i < mo.length; i++) {
    var q = mo[i];
    if (q[6] >= 0) continue;
    var ms = mid_(q[1], pts_(R, W, q[2], 8, q[5])), prev = null;
    for (var j = 0; j < ms.length; j++) {
      if (prev && FXK().segDist(tx, ty, prev[0], prev[1], ms[j][0], ms[j][1]) <= hr + W * q[2] * 0.5) return true;
      prev = ms[j];
    }
  }
  return false;
}
// [points, half width] a clash treats as a cutting blade: its first live moon.
function body(inst, ps) {
  if (inst.age >= inst.life) return null;
  var P = inst.fx.params, R = +P.radius * ps, W = +P.thickness * ps, mo = moons(inst, ps, inst.age);
  for (var i = 0; i < mo.length; i++)
    if (mo[i][6] < 0) return [mid_(mo[i][1], pts_(R, W, mo[i][2], 6, mo[i][5])), W * mo[i][2] * 0.5];
  return null;
}

// ================================================================ drawing
function rev(a) { return a.slice().reverse(); }
function shape(fr, pts, ox) {
  ox = ox || 0;
  var outer = [], inner = [];
  pts.forEach(function (q) {
    outer.push(fr.w(q[1][0] + ox, q[1][1])); inner.push(fr.w(q[1][0] - q[2][0] * q[3] + ox, q[1][1] - q[2][1] * q[3]));
  });
  return [outer, inner];
}
// One crescent blade: aura, flames off its back, bright rim, dark core,
// white-hot leading edge.
function blade(pen, inst, fr, R, W, k, tl, mi, fade, half, c, deep, S) {
  var L = L_(), ph = (inst.seed % 1000) * 0.01 + mi * 1.7, pts = pts_(R, W, k, 20, half), sh = shape(fr, pts);
  var outer = sh[0], inner = sh[1], i, j;
  var auraO = pts.map(function (q) { return fr.w(q[1][0] + q[2][0] * 6 * S * k, q[1][1] + q[2][1] * 6 * S * k); });
  var auraI = pts.map(function (q) { var mm = q[3] + 4 * S * k; return fr.w(q[1][0] - q[2][0] * mm, q[1][1] - q[2][1] * mm); });
  pen.poly(auraO.concat(rev(auraI)), c, 80 * fade);
  var tongues = [];
  for (i = 0; i < 11; i++) {
    var v = -0.9 + 1.8 * i / 10, r = L.rngFor(inst.seed, i, 17 + 40 * mi);
    var u1 = r.uniform(0.6, 1.4), u2 = r.uniform(3.4, 5.2);
    if (half && v > 0.05) continue;
    var a = v * ARC_DEG * D, dx = Math.cos(a), dy = Math.sin(a), ww = W * k * taper(v);
    var bx = (CX * R + R * dx) * k - dx * ww * 0.8, by = R * dy * k - dy * ww * 0.8;
    var ln = (18 + 30 * L.flame(v, tl, ph + i) * u1) * S * k * (1 - 0.45 * Math.abs(v));
    var ux = -1, uy = 0.6 * v + 0.25 * Math.sin(tl * 0.7 + i * 1.7 + mi), n = hyp(ux, uy);
    tongues.push([fr.w(bx, by), fr.w(bx + ux / n * ln, by + uy / n * ln), u2 * S * k]);
  }
  var back = fr.w(CX * R * k - 0.2 * R * k, half ? -0.45 * R * k : 0);
  pen.glow(back[0], back[1], (half ? 0.8 : 1.1) * R * k, c, 70 * fade, 0.4);
  tongues.forEach(function (tg) { pen.diamond(tg[0][0], tg[0][1], tg[1][0], tg[1][1], tg[2], c, 170 * fade); });
  pen.poly(outer.concat(rev(inner)), L.mix(c, HOT, 0.25), 235 * fade);
  pen.add(false);
  tongues.forEach(function (tg) {
    var b0 = tg[0], b1 = tg[1];
    var m0 = [b0[0] + (b1[0] - b0[0]) * 0.08, b0[1] + (b1[1] - b0[1]) * 0.08], m1 = [b0[0] + (b1[0] - b0[0]) * 0.75, b0[1] + (b1[1] - b0[1]) * 0.75];
    pen.diamond(m0[0], m0[1], m1[0], m1[1], tg[2] * 0.5, deep, 220 * fade);
  });
  var coreO = pts.map(function (q) { return fr.w(q[1][0] - q[2][0] * q[3] * 0.3, q[1][1] - q[2][1] * q[3] * 0.3); });
  var coreI = pts.map(function (q) { var mm = q[3] * (0.88 + 0.2 * L.flame(q[0], tl, ph)); return fr.w(q[1][0] - q[2][0] * mm, q[1][1] - q[2][1] * mm); });
  var e = half ? pts.length : pts.length - 2, co = coreO.slice(2, e), ci = coreI.slice(2, e);
  pen.poly(co.concat(rev(ci)), deep, 240 * fade);
  pen.add(true);
  pen.polyline(co, c, 120 * fade, 1 * S);
  var front = [];
  for (j = 0; j < pts.length; j++) if (Math.abs(pts[j][0]) < 0.85) front.push(outer[j]);
  pen.polyline(front, HOT, 255 * fade, 2.2 * S * k);
  var mid = half ? outer[outer.length - 1] : outer[Math.floor(outer.length / 2)];
  pen.glow(mid[0], mid[1], 20 * S * k, c, 130 * fade);
}
// Launch flash: glow, a cross-cut diamond and a ring (flat < 1: on the ground).
function burst(pen, x, y, vx, vy, t, c, S, flat) {
  if (t >= 14) return;
  if (flat === undefined) flat = 1;
  var q = t / 14, e = L_().easeOut3(q);
  pen.glow(x, y, (14 + 30 * e) * S, c, 160 * (1 - q));
  pen.diamond(x - vx * 45 * S, y - vy * 45 * S, x + vx * 45 * S, y + vy * 45 * S, 4 * S * (1 - q) + 0.2, c, 220 * (1 - q));
  pen.diamond(x - vx * 40 * S, y - vy * 40 * S, x + vx * 40 * S, y + vy * 40 * S, 1.3 * S * (1 - q) + 0.2, HOT, 255 * (1 - q));
  pen.ring(x, y, (6 + 26 * e) * S, (6 + 26 * e) * S * flat, 0, c, 180 * (1 - q), 2.2 * S * (1 - q) + 0.2);
}
// An X glint where blades cross / split (age a of life).
function cross(pen, x, y, f, a, life, size, c, S) {
  var q = a / life, e = L_().easeOut3(a / 5), ln = size * (0.7 + 0.5 * e);
  [38, -38].forEach(function (dg) {
    var u = FXK().rot([f[0], f[1]], dg);
    pen.diamond(x - u[0] * ln, y - u[1] * ln, x + u[0] * ln, y + u[1] * ln, 3.4 * S * (1 - q) + 0.3, c, 230 * (1 - q));
    pen.diamond(x - u[0] * ln * 0.9, y - u[1] * ln * 0.9, x + u[0] * ln * 0.9, y + u[1] * ln * 0.9, 1.1 * S * (1 - q) + 0.2, HOT, 255 * (1 - q));
  });
  pen.glow(x, y, (10 + 16 * e) * S * (1 - q), HOT, 230 * (1 - q));
  var rr = 6 * S + size * 0.8 * L_().easeOut3(q);
  pen.ring(x, y, rr, rr, 0, c, 190 * (1 - q), 2.2 * S * (1 - q) + 0.2);
}
// What lies under the blades: launch flashes, crossing glints, the moonfall's mark.
function under(pen, inst, ps, t, st, c, R, W) {
  var L = L_(), P = inst.fx.params, f = inst.tq_f, m = inst.tq_m, o = inst.tq_o, nx = -f[1] * m, ny = f[0] * m, S = ps;
  var Lf = activeTicks(P), a;
  if (st === "crescent_drag") burst(pen, o[0], o[1] + gp_(inst, ps), 0, -1, t, c, S, 0.4);
  else if (st === "crescent_helix" || st === "crescent_split" || st === "crescent_return") burst(pen, o[0], o[1], nx, ny, t, c, S);
  var spd = spd_(inst);
  if (st === "crescent_helix" && spd > 0.01) {
    var d0 = reach(inst, ps), wv = Math.max(0.25, num(P, "weaves", 2));
    for (var j = 1; j < 40; j++) {
      var sj = j * d0 / wv, tj = sj / spd;
      if (tj >= Lf) break;
      a = t - tj;
      if (a >= 0 && a < 10) cross(pen, o[0] + f[0] * sj, o[1] + f[1] * sj, f, a, 10, 0.8 * R, c, S);
    }
  } else if (st === "crescent_split" && spd > 0.01) {
    var ss = L.cl(num(P, "split_pct", 45) / 100) * reach(inst, ps);
    a = t - ss / spd;
    if (a >= 0 && a < 14 && ss / spd < Lf) {
      cross(pen, o[0] + f[0] * ss, o[1] + f[1] * ss, f, a, 14, 1.5 * R, c, S);
      cross(pen, o[0] + f[0] * ss, o[1] + f[1] * ss, [nx, ny], a, 14, 1.0 * R, c, S);
    }
  } else if (st === "crescent_scatter") {
    scatterPlan(inst, P, count(P)).forEach(function (pl) {
      var a2 = t - pl[0];
      if (a2 < 0 || a2 >= 8) return;
      var q = a2 / 8, d = FXK().rot([f[0], f[1]], pl[1] * m), ln = 38 * S * pl[3];
      pen.glow(o[0], o[1], (10 + 18 * L.easeOut3(q)) * S, c, 150 * (1 - q));
      pen.diamond(o[0] + d[1] * ln, o[1] - d[0] * ln, o[0] - d[1] * ln, o[1] + d[0] * ln, 3 * S * (1 - q) + 0.2, c, 220 * (1 - q));
      pen.diamond(o[0], o[1], o[0] + d[0] * ln * 1.6, o[1] + d[1] * ln * 1.6, 1.4 * S * (1 - q) + 0.2, HOT, 240 * (1 - q));
    });
  } else if (st === "crescent_fall") {
    var ti = impactTick(P), g = groundPoint(inst, ps);
    if (t < ti) {
      var u = t / ti, rx = R * (1.6 - 0.5 * u);
      pen.ring(g[0], g[1], rx, rx * 0.35, 0, c, 60 + 160 * u, (1.2 + 1.6 * u) * S);
      pen.ring(g[0], g[1], rx * 0.55, rx * 0.55 * 0.35, 0, HOT, 140 * u * u, 1 * S);
      var th = num(P, "fall_angle_deg", 18) * D, ax = Math.sin(th) * m, ay = Math.cos(th);
      var hh = (+P.length || 0) * ps + 2 * R;
      pen.line(g[0] - ax * hh, g[1] - ay * hh, g[0], g[1], c, 30 + 90 * u, (0.8 + 1.4 * u) * S);
      pen.glow(g[0], g[1], (8 + 14 * u) * S, c, 120 * u);
    }
  }
}
// Embers shed off every blade's back as it flew.
function embers(pen, inst, ps, t, st, c, deep, R, W) {
  var L = L_(), P = inst.fx.params, S = ps;
  var n = st === "crescent_helix" || st === "crescent_scatter" || st === "crescent_split" ? count(P) : 1;
  var per = Math.max(0, Math.round(3 * (+P.density || 1) / Math.sqrt(n)));
  if (!per) return;
  var grav = 0.18 * S;
  for (var b = Math.max(0, t - EMBER_LIFE); b < t; b++) {
    var mo = moons(inst, ps, b);
    for (var i = 0; i < mo.length; i++) {
      var mi = mo[i][0], fr = mo[i][1], k = mo[i][2], half = mo[i][5];
      if (mo[i][6] >= 0) continue;
      for (var j = 0; j < per; j++) {
        var r = L.rngFor(inst.seed, b * 16 + mi, 300 + j);
        var life = 14 + 16 * r(), a = t - b, v = r.uniform(-0.9, 0.9), bv = r.uniform(0.5, 2.5) * S, pv = r.uniform(-1.2, 1.2) * S;
        if (a >= life) continue;
        if (half) v = -Math.abs(v);
        var an = v * ARC_DEG * D, ww = W * taper(v);
        var s = fr.w((CX * R + R * Math.cos(an) - Math.cos(an) * ww) * k, (R * Math.sin(an) - Math.sin(an) * ww) * k);
        var vv = fr.d(-bv, pv), fd = L.dragDist(0.93, a);
        var x = s[0] + vv[0] * fd, y = s[1] + vv[1] * fd + 0.5 * grav * a * a, q = a / life;
        var col = q < 0.5 ? L.mix(HOT, c, Math.min(1, q * 2)) : L.mix(c, deep, (q - 0.5) * 2);
        pen.diamond(x - 1.8 * S, y, x + 1.8 * S, y, 1.4 * S * (1 - q * 0.5), col, 230 * (1 - q));
      }
    }
  }
}
// Ground drag: wind streaks off the fin's back, the white-hot contact point
// and the sparks / chips it throws up behind it.
function dragFx(pen, inst, ps, t, c, R, W) {
  var L = L_(), P = inst.fx.params, S = ps, f = inst.tq_f, m = inst.tq_m, Lf = activeTicks(P), dens = +P.density || 1;
  var sx = (m >= 0 ? 1 : -1) * Math.max(Math.abs(f[0]), DRAG_MIN_X), gp = gp_(inst, ps), j, r;
  if (t < Lf) {
    var mo = moons(inst, ps, t);
    if (mo.length) {
      var fr = mo[0][1], k = mo[0][2];
      for (j = 0; j < Math.round(6 * dens); j++) {
        var slot = Math.floor((t + j * 3) / 5);
        r = L.rngFor(inst.seed, slot, 600 + j);
        var v = -r.uniform(0.05, 0.92), ln = r.uniform(1.4, 3.6) * R, rise = r.uniform(-0.18, 0.1);
        var u = ((t + j * 3) % 5) / 5, an = v * ARC_DEG * D, ww = W * k * taper(v);
        var p0 = fr.w((CX * R + R * Math.cos(an)) * k - Math.cos(an) * ww - u * 0.5 * R, R * Math.sin(an) * k);
        var p1 = [p0[0] - sx * ln * (0.4 + 0.6 * u), p0[1] - f[1] * ln * (0.4 + 0.6 * u) + rise * ln];
        var al = Math.sin(Math.PI * u);
        pen.line(p0[0], p0[1], p1[0], p1[1], c, 150 * al, (1 + 1.4 * (1 - Math.abs(v))) * S);
        pen.line(p0[0], p0[1], (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, HOT, 170 * al, 0.7 * S);
      }
      var g = groundPoint(inst, ps), gx = g[0], gy = g[1];
      var fl = 0.75 + 0.25 * Math.sin(t * 1.9 + (inst.seed % 97));
      pen.glow(gx, gy, 26 * S * k, c, 170 * fl);
      pen.glow(gx, gy, 11 * S * k, HOT, 255 * fl);
      [1, -1].forEach(function (sgn) {
        pen.diamond(gx, gy, gx - sx * 0.9 * R * k, gy - f[1] * 0.9 * R * k + sgn * 0.16 * R * k, 2.6 * S * k, c, 200 * fl);
      });
      pen.diamond(gx + sx * 0.25 * R * k, gy + f[1] * 0.25 * R * k, gx - sx * 1.5 * R * k, gy - f[1] * 1.5 * R * k, 1.2 * S * k, HOT, 230 * fl);
    }
  }
  var per = Math.max(0, Math.round(4 * dens)), grav = 0.34 * S;
  for (var b = Math.max(0, t - 20); b < Math.min(t, Lf); b++) {
    var pp = pos(inst, b), px = pp[0], py = pp[1] + gp;
    for (j = 0; j < per; j++) {
      r = L.rngFor(inst.seed, b, 500 + j);
      var life = 8 + 12 * r(), a = t - b, bv = r.uniform(1.5, 7.5) * S, up = r.uniform(0.6, 5.5) * S, side = r.uniform(-1, 1) * S;
      var chip = r() < 0.3;
      if (a >= life) continue;
      var vx = -sx * bv + side * 0.4, vy = -f[1] * bv - up, fd = L.dragDist(0.9, a);
      var x = px + vx * fd, y = py + vy * fd + 0.5 * grav * a * a;
      if (y > py) y = py - (y - py) * 0.35;        // a low bounce off the ground
      var dk = Math.pow(0.9, a), cvx = vx * dk, cvy = vy * dk + grav * a, q = a / life;
      if (chip) pen.diamond(x - 2.6 * S, y, x + 2.6 * S, y, 2 * S * (1 - q * 0.4), L.mix(c, HOT, 0.2), 235 * (1 - q));
      else pen.line(x, y, x - cvx * 1.9, y - cvy * 1.9, L.mix(HOT, c, q), 255 * (1 - q), 1.5 * S);
    }
  }
}
// Moonfall: speed lines while it drops, then the slam.
function fallFx(pen, inst, ps, t, c, R, W) {
  var L = L_(), P = inst.fx.params, S = ps, m = inst.tq_m, ti = impactTick(P);
  var th = num(P, "fall_angle_deg", 18) * D, ax = Math.sin(th) * m, ay = Math.cos(th);
  var g = groundPoint(inst, ps), gx = g[0], gy = g[1], j, r, ln;
  if (t >= FALL_WIND && t < ti) {
    var mo = moons(inst, ps, t);
    if (mo.length) {
      var fr = mo[0][1], k = mo[0][2];
      for (j = 0; j < 7; j++) {
        r = L.rngFor(inst.seed, Math.floor(t / 2), 700 + j);
        var yy = r.uniform(-0.95, 0.95) * R * k;
        ln = r.uniform(1.2, 3.2) * R;
        var p0 = fr.w(CX * R * k - 0.2 * R, yy);
        pen.line(p0[0], p0[1], p0[0] - ax * ln, p0[1] - ay * ln, c, 150, 1.4 * S);
        pen.line(p0[0], p0[1], p0[0] - ax * ln * 0.5, p0[1] - ay * ln * 0.5, HOT, 150, 0.7 * S);
      }
    }
  }
  var a = t - ti;
  if (a < 0 || a >= 24) return;
  var q = a / 24, e = L.easeOut3(a / 9), ff = 1 - Math.min(1, a / 10);
  pen.glow(gx, gy, (30 + 50 * e) * S, HOT, 240 * ff);
  pen.glow(gx, gy, 2.2 * R * (0.5 + 0.5 * e), c, 150 * (1 - q), 0.4);
  var hh = ((+P.length || 0) * ps * 0.6 + 2.5 * R) * (1 - 0.3 * q);
  pen.diamond(gx, gy, gx - ax * hh, gy - ay * hh, (0.5 * W + 6 * S) * ff + 0.3, c, 200 * ff);
  pen.diamond(gx, gy, gx - ax * hh * 0.92, gy - ay * hh * 0.92, (0.16 * W + 2 * S) * ff + 0.2, HOT, 255 * ff);
  for (j = 0; j < 3; j++) {
    var aa = a - j * 3;
    if (aa < 0) continue;
    var qq = aa / 20;
    if (qq >= 1) continue;
    var rx = (0.5 + 2.3 * L.easeOut3(qq)) * R * (1 + 0.25 * j);
    pen.ring(gx, gy, rx, rx * 0.35, 0, j ? c : HOT, 220 * (1 - qq), (3.4 - j) * S * (1 - qq) + 0.3);
  }
  var dens = +P.density || 1, grav = 0.3 * S;
  for (var i = 0; i < Math.max(0, Math.round(18 * dens)); i++) {
    r = L.rngFor(inst.seed, i, 720);
    var life = 12 + 12 * r(), an = -Math.PI * r.uniform(0.08, 0.92), sp = r.uniform(3, 10) * S;
    ln = r.uniform(5, 11) * S;
    if (a >= life) continue;
    var vx = Math.cos(an) * sp, vy = Math.sin(an) * sp, fd = L.dragDist(0.92, a);
    var x = gx + vx * fd, y = gy + vy * fd + 0.5 * grav * a * a, dk = Math.pow(0.92, a);
    var cv = unit(vx * dk, vy * dk + grav * a), q2 = a / life;
    pen.diamond(x - cv[0] * ln, y - cv[1] * ln, x + cv[0] * ln, y + cv[1] * ln, 2.2 * S * (1 - q2) + 0.2, c, 235 * (1 - q2));
    pen.diamond(x - cv[0] * ln * 0.7, y - cv[1] * ln * 0.7, x + cv[0] * ln * 0.7, y + cv[1] * ln * 0.7, 0.8 * S * (1 - q2) + 0.1, HOT, 255 * (1 - q2));
  }
}
// A blade shatters where it ended (age a since).
function shards(pen, inst, fr, R, k, mi, a, half, cnt, c, S) {
  var L = L_(), q = a / SHARD_LIFE;
  if (q >= 1) return;
  var ff = 1 - Math.min(1, a / 10), ctr = fr.w((CX + 1) * R * k * 0.5, half ? -0.4 * R * k : 0);
  pen.glow(ctr[0], ctr[1], 40 * S * k * ff, HOT, 200 * ff);
  for (var i = 0; i < cnt; i++) {
    var r = L.rngFor(inst.seed, i, 91 + 40 * mi);
    var v = r.uniform(-0.9, 0.9), j1 = r.uniform(-0.4, 0.4), j2 = r.uniform(-0.4, 0.4), sp = r.uniform(2, 6) * S;
    var rot = r.uniform(0, Math.PI * 2) + r.uniform(-0.25, 0.25) * a, ln = r.uniform(7, 12) * S * (0.6 + 0.4 * k);
    if (half) v = -Math.abs(v);
    var an = v * ARC_DEG * D, p = fr.w((CX * R + R * Math.cos(an)) * k, R * Math.sin(an) * k);
    var dd = fr.d(Math.cos(an) + j1, Math.sin(an) + j2), fd = L.dragDist(0.93, a);
    var x = p[0] + dd[0] * sp * fd, y = p[1] + dd[1] * sp * fd + 0.05 * S * a * a;
    var ux = Math.cos(rot) * ln, uy = Math.sin(rot) * ln;
    pen.diamond(x - ux, y - uy, x + ux, y + uy, 2.4 * S * (1 - q) + 0.2, c, 230 * (1 - q));
    pen.diamond(x - ux * 0.7, y - uy * 0.7, x + ux * 0.7, y + uy * 0.7, 0.8 * S * (1 - q) + 0.1, HOT, 255 * (1 - q));
  }
}
function draw(pen, inst, host, ps) {
  var L = L_(), P = inst.fx.params, st = L.style(P), t = inst.age, cs = L.colours(inst, host), c = cs[0], deep = cs[2], S = ps;
  var R = +P.radius * ps, W = +P.thickness * ps;
  pen.add(true);
  under(pen, inst, ps, t, st, c, R, W);
  var mo = moons(inst, ps, t);
  // (no afterimages once the moonfall has landed)
  (st === "crescent_fall" && t > impactTick(P) + 1 ? [] : [3, 2, 1]).forEach(function (j) {
    moons(inst, ps, t - 2 * j).forEach(function (q) {
      if (q[6] >= 0) return;
      var now = mo.filter(function (z) { return z[0] === q[0]; });
      if (!now.length || now[0][3] <= 0) return;
      var sh = shape(q[1], pts_(R, W, q[2], 20, q[5]));
      pen.poly(sh[0].concat(rev(sh[1])), c, 55 / j * now[0][3]);
    });
  });
  mo.forEach(function (q) { if (q[3] > 0) blade(pen, inst, q[1], R, W, q[2], q[4], q[0], q[3], q[5], c, deep, S); });
  embers(pen, inst, ps, t, st, c, deep, R, W);
  if (st === "crescent_drag") dragFx(pen, inst, ps, t, c, R, W);
  else if (st === "crescent_fall") fallFx(pen, inst, ps, t, c, R, W);
  var cnt = mo.length <= 1 ? 10 : 6;
  mo.forEach(function (q) { if (q[6] >= 0) shards(pen, inst, q[1], R, q[2], q[0], q[6], q[5], cnt, c, S); });
  L.hitMarks(pen, inst, c, ps, inst.tq_f[0], inst.tq_f[1]);
}

G.CRESCENTFX = {STYLES: STYLES, GROUND_STYLES: GROUND_STYLES, SCATTER_PATHS: SCATTER_PATHS, activeTicks: activeTicks, totalTicks: totalTicks,
                impactTick: impactTick, hit: hit, body: body, draw: draw, groundPoint: groundPoint, onGround: onGround, moons: moons};
})(window);
