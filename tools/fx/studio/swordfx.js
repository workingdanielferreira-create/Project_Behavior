/* Sword techniques — FX Studio's port of laser/swordfx.py, the hand-drawn
 * renderer behind the FX Kit "technique" primitive.  Same timeline, same
 * random streams (FXK.rng), same geometry and the same painting order, so the
 * Studio preview draws what Solo and Battle draw.  Keep the two in step.
 *
 * Styles: rising_slash, horizontal_sweep, diagonal_slash, crescent_wave,
 * blade_extension (see laser/swordfx.py for what each one paints).
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var HOT = [255, 255, 255], BLACK = [0, 0, 0], D = Math.PI / 180;
var CUT_DEG = {rising_slash: -90, horizontal_sweep: 0, diagonal_slash: -45};
// Every slash-family style is a list of cuts (laser/swordfx.py CUTS — keep in step):
// [deg, bend, cx, cy, scale, span_k, squash, t0]
var CUTS = {
  rising_slash: [[-90, 1, 0, 0, 1, 1, 1, 0]],
  horizontal_sweep: [[0, 1, 0, 0, 1, 1, 1, 0]],
  diagonal_slash: [[-45, 1, 0, 0, 1, 1, 1, 0]],
  forward_sweep: [[90, -1, 0.1, 0, 1, 1, 0.32, 0]],
  combo_triple: [[40, -1, 0.1, -0.1, 1, 1, 1, 0], [-40, 1, 0.15, 0.05, 1, 1, 1, 1.3], [0, 1, 0.2, -0.1, 1.5, 0.6, 1, 2.6]],
  combo_cross: [[45, -1, 0.45, 0, 1, 1, 1, 0], [-45, 1, 0.45, 0, 1, 1, 1, 0.9]],
  combo_flurry: [[30, -1, 0.55, -0.3, 0.7, 1, 1, 0], [-150, -1, 0.75, 0.15, 0.65, 1, 1, 0.6], [90, -1, 0.95, -0.05, 0.7, 0.9, 1, 1.2],
                 [-20, 1, 0.6, 0.3, 0.75, 1, 1, 1.8], [160, 1, 0.85, -0.35, 0.6, 1, 1, 2.4], [-60, 1, 0.7, 0, 0.9, 1.1, 1, 3]],
  combo_launcher: [[0, 1, 0.3, 0.35, 0.8, 0.8, 1, 0], [-35, 1, 0.25, 0.05, 1, 1, 1, 1.2], [-90, 1, 0.2, -0.25, 1.25, 1.2, 1, 2.4]],
  combo_backhand: [[90, -1, 0.05, -0.05, 1, 1.1, 0.32, 0], [-90, 1, 0.05, 0.1, 1, 1.1, 0.32, 1.2], [90, -1, 0.45, 0, 1.1, 0.9, 1, 2.4]]
};
var CROSS_LIFE = 18;
var SLASH_SLICES = 26, SPARK_LIFE = 20, WAVE_EMBER_LIFE = 30, WAVE_SHARD_LIFE = 26;
var WAVE_ARC_DEG = 95, WAVE_CX = -0.5;
var EXT_CHARGE = 4, EXT_EXTEND = 5, EXT_RETRACT = 7, EXT_DUST = 16;
var HIT_MARK_LIFE = 16;
var STRIKE = function () { return G.STRIKEFX; };

// ---------------------------------------------------------------- maths
function cl(u) { return u < 0 ? 0 : u > 1 ? 1 : u; }
function easeOut3(u) { u = cl(u); return 1 - Math.pow(1 - u, 3); }
function easeIn3(u) { u = cl(u); return u * u * u; }
function easeInOut3(u) { u = cl(u); return u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2; }
function mix(a, b, k) { return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k]; }
function frac(x) { return x - Math.floor(x); }
function rngFor(seed, a, b) {
  return FXK().rng(((seed >>> 0) ^ Math.imul(a + 1, 0x2C1B3C6D) ^ Math.imul((b || 0) + 1, 0x297A2D39)) >>> 0);
}
function dragDist(drag, k) { return drag >= 0.9999 ? k : (1 - Math.pow(drag, k)) / (1 - drag); }
function hyp(x, y) { return Math.sqrt(x * x + y * y); }

// ---------------------------------------------------------------- timeline
function style(P) { var s = P.style; return FXK().TECH_STYLES.indexOf(s) >= 0 ? s : FXK().TECH_STYLES[0]; }
function isStrike(st) { return STRIKE() && STRIKE().STYLES.indexOf(st) >= 0; }
function swing(P) { return Math.max(2, Math.trunc(+P.swing_ticks || 6)); }
function fadeT(P) { return Math.max(6, Math.round(1.6 * swing(P))); }
function holdT(P) { return Math.max(0, Math.trunc(+P.hold_ticks || 0)); }
function cutStarts(P) { var Ts = swing(P); return CUTS[style(P)].map(function (c) { return Math.round(c[7] * Ts); }); }
function lastStart(P) { var s = cutStarts(P); return s[s.length - 1]; }
function activeTicks(P) {
  var st = style(P);
  if (st === "crescent_wave") return Math.max(1, Math.trunc(+P.hold_ticks || 48));
  if (st === "blade_extension") return EXT_CHARGE + EXT_EXTEND + holdT(P) + EXT_RETRACT;
  if (isStrike(st)) return STRIKE().activeTicks(P);
  return lastStart(P) + swing(P) + 2;
}
function totalTicks(P) {
  var st = style(P);
  if (st === "crescent_wave") return activeTicks(P) + WAVE_EMBER_LIFE;
  if (st === "blade_extension") return activeTicks(P) + EXT_DUST;
  if (isStrike(st)) return STRIKE().totalTicks(P);
  return lastStart(P) + swing(P) + fadeT(P) + SPARK_LIFE;
}

// ---------------------------------------------------------------- frame
function onSpawn(inst, host) {
  var fx = inst.fx, st = style(fx.params), f, slash = CUTS[st] !== undefined;
  if (slash) f = FXK().turnBy([inst.facing, 0], FXK().bodyDeg(fx, host, [inst.x, inst.y]));
  else f = inst.dir.slice();
  var n = hyp(f[0], f[1]) || 1;
  inst.tq_f = [f[0] / n, f[1] / n];
  inst.tq_m = slash ? inst.facing : (inst.tq_f[0] >= 0 ? 1 : -1);
  inst.tq_o = [inst.x, inst.y];
  inst.tq_hits = [];
  inst.tq_cut = {};               // combo cuts that already landed
  inst.tq_path = [[inst.x, inst.y]];   // where the anchor was, per tick
  inst.tq_ki = {};                // ki shots stopped by a hit: index -> [tick, x, y]
  inst.tq_imp = [];               // punch impacts: [tick, x, y]
  inst.life = activeTicks(fx.params);
}
function onTick(inst) { inst.tq_path.push([inst.x, inst.y]); }   // ki shots launch from where the anchor was
function Frame(ox, oy, f, m) { this.ox = ox; this.oy = oy; this.fx = f[0]; this.fy = f[1]; this.vx = -f[1] * m; this.vy = f[0] * m; }
Frame.prototype.w = function (x, y) { return [this.ox + x * this.fx + y * this.vx, this.oy + x * this.fy + y * this.vy]; };
Frame.prototype.d = function (x, y) { return [x * this.fx + y * this.vx, x * this.fy + y * this.vy]; };
function frame(inst) { return new Frame(inst.x, inst.y, inst.tq_f, inst.tq_m); }

var VIVID = typeof WeakMap !== "undefined" ? new WeakMap() : null;
function vivid(lut) {
  if (VIVID && VIVID.has(lut)) return VIVID.get(lut);
  var best = lut[0], bs = -1;
  for (var i = 0; i < lut.length; i++) {
    var e = lut[i], mx = Math.max(e[0], e[1], e[2]), mn = Math.min(e[0], e[1], e[2]), sc = mx + 0.5 * (mx - mn);
    if (sc > bs) { best = e; bs = sc; }
  }
  best = [best[0], best[1], best[2]];
  if (VIVID) VIVID.set(lut, best);
  return best;
}
function colours(inst, host) {
  var c, c2;
  if (inst.fx.color.mode === "palette") { c = vivid(host.lut); c2 = c; }
  else { var cp = FXK().colorPair(inst.fx, host.lut); c = cp[0]; c2 = cp[1]; }
  return [c, mix(c, HOT, 0.45), mix(c2, BLACK, 0.84)];
}

// ---------------------------------------------------------------- slash geometry
function SlashGeo(inst, ps, ci) {
  var P = inst.fx.params;
  this.st = style(P);
  var cu = CUTS[this.st][ci || 0], bend = cu[1];
  this.R = +P.radius * ps * cu[4]; this.W = +P.thickness * ps * cu[4]; this.h = +P.span * cu[5] / 2;
  this.b = bend;
  var a = cu[0] * D;
  this.d = [Math.cos(a), Math.sin(a)];
  this.n = [-this.d[1] * bend, this.d[0] * bend];
  var k = this.R * Math.cos(this.h * D);
  this.O = [-this.n[0] * k, -this.n[1] * k];
  var R0 = +P.radius * ps;
  this.C = [cu[2] * R0, cu[3] * R0];
  this.sq = cu[6];
  this.Ts = swing(P); this.Tf = fadeT(P);
}
SlashGeo.prototype.phi = function (s) { return FXK().rot(this.n.slice(), this.b * (this.h - 2 * this.h * s)); };
SlashGeo.prototype.local = function (s, r) {
  var p = this.phi(s), x = this.O[0] + p[0] * r, y = this.O[1] + p[1] * r;
  if (this.sq !== 1) { var a = (x * this.d[0] + y * this.d[1]) * (this.sq - 1); x += this.d[0] * a; y += this.d[1] * a; }
  return [this.C[0] + x, this.C[1] + y];
};
SlashGeo.prototype.state = function (t) {
  var Ts = this.Ts, Tf = this.Tf, head = easeOut3(t / Ts);
  if (t <= Ts) return [Math.max(0, head - 0.8), head, 1, 1];
  var k = cl((t - Ts) / Tf);
  return [0.2 + 0.8 * easeInOut3(k), 1, 1 - 0.5 * k, 1 - 0.5 * k];
};
SlashGeo.prototype.width = function (u, wf) { return this.W * wf * Math.pow(Math.sin(Math.PI * Math.pow(u, 1.5)), 0.7); };
SlashGeo.prototype.slices = function (t) {
  var s = this.state(t), tail = s[0], head = s[1], wf = s[3], out = [];
  if (head - tail < 0.004) return out;
  for (var i = 0; i <= SLASH_SLICES; i++) { var u = i / SLASH_SLICES; out.push([tail + (head - tail) * u, u, this.width(u, wf)]); }
  return out;
};
function cutHit(g, fr, t, tx, ty, hr) {
  var sl = g.slices(t), hub = null;
  // A flat (squashed) cut is a swing round the body seen edge-on: it hits
  // everything between the fighter and the blade, not just the blade line.
  if (g.sq !== 1) { var lh = g.local(0.5, 0); hub = fr.w(lh[0], lh[1]); }
  for (var i = 1; i < sl.length; i++) {
    var q0 = sl[i - 1], q1 = sl[i];
    if (q1[1] < 0.15) continue;
    var l0 = g.local(q0[0], g.R - 0.2 * q0[2]), l1 = g.local(q1[0], g.R - 0.2 * q1[2]);
    var a = fr.w(l0[0], l0[1]), b = fr.w(l1[0], l1[1]);
    if (FXK().segDist(tx, ty, a[0], a[1], b[0], b[1]) <= hr + Math.max(q0[2], q1[2]) * 0.5) return true;
    if (hub && FXK().segDist(tx, ty, hub[0], hub[1], b[0], b[1]) <= hr) return true;
  }
  return false;
}
// [[cut index, its own tick]] for the cuts inside their hit window
function liveCuts(inst) {
  var P = inst.fx.params, win = swing(P) + 2, out = [];
  cutStarts(P).forEach(function (s, i) { var t = inst.age - s; if (t >= 0 && t < win) out.push([i, t]); });
  return out;
}
function slashHit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var fr = frame(inst), combo = CUTS[style(inst.fx.params)].length > 1, live = liveCuts(inst);
  for (var j = 0; j < live.length; j++) {
    var ci = live[j][0];
    if (combo && inst.tq_cut[ci]) continue;   // each combo cut lands once
    if (cutHit(new SlashGeo(inst, ps, ci), fr, live[j][1], tx, ty, hr)) return true;
  }
  return false;
}
function slashOnHit(inst) { liveCuts(inst).forEach(function (lc) { inst.tq_cut[lc[0]] = true; }); }

// ---------------------------------------------------------------- wave geometry
function WaveGeo(inst, ps) { var P = inst.fx.params; this.R = +P.radius * ps; this.W = +P.thickness * ps; this.L = activeTicks(P); }
WaveGeo.prototype.grow = function (t) {
  var g = 0.35 + 0.65 * easeOut3(t / 5);
  if (t >= this.L) g *= 1 + 0.25 * cl((t - this.L) / 8);
  return g;
};
WaveGeo.prototype.pts = function (t, g, M) {
  M = M || 20;
  var out = [], cx = WAVE_CX * this.R;
  for (var j = 0; j <= M; j++) {
    var v = -1 + 2 * j / M, a = v * WAVE_ARC_DEG * D, dx = Math.cos(a), dy = Math.sin(a);
    out.push([v, [(cx + this.R * dx) * g, this.R * dy * g], [dx, dy], this.W * g * Math.pow(1 - Math.pow(Math.abs(v), 1.8), 0.85)]);
  }
  return out;
};
function flame(v, t, ph) { return 0.5 + 0.5 * Math.sin(v * 9 + t * 0.9 + ph) * Math.sin(v * 4.3 - t * 0.55 + ph * 0.5); }
function waveHit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var g = new WaveGeo(inst, ps), fr = frame(inst), k = g.grow(inst.age), pts = g.pts(inst.age, k, 8), prev = null;
  for (var i = 0; i < pts.length; i++) {
    var o = pts[i][1], dr = pts[i][2], w = pts[i][3];
    var c = fr.w(o[0] - dr[0] * w * 0.5, o[1] - dr[1] * w * 0.5);
    if (prev && FXK().segDist(tx, ty, prev[0], prev[1], c[0], c[1]) <= hr + g.W * k * 0.5) return true;
    prev = c;
  }
  return false;
}

// ---------------------------------------------------------------- extension geometry
function extLen(P, t, L) {
  var t0 = EXT_CHARGE, t1 = t0 + EXT_EXTEND, t2 = t1 + holdT(P), t3 = t2 + EXT_RETRACT;
  if (t < t0) return 0;
  if (t < t1) return L * easeOut3((t - t0) / EXT_EXTEND);
  if (t < t2) return L;
  if (t < t3) return L * (1 - easeIn3((t - t2) / EXT_RETRACT));
  return 0;
}
function extHw(u, W) {
  var hw = u < 0.86 ? W * (0.75 + 0.25 * Math.sin(Math.PI * u)) : W * (1 - (u - 0.86) / 0.14) * (0.75 + 0.25 * Math.sin(Math.PI * 0.86));
  if (u < 0.05) hw *= 1 + 0.6 * (1 - u / 0.05);
  return Math.max(0, hw);
}
function extHit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var P = inst.fx.params, l = extLen(P, inst.age, +P.length * ps);
  if (l <= 2) return false;
  var b = frame(inst).w(l, 0);
  return FXK().segDist(tx, ty, inst.x, inst.y, b[0], b[1]) <= hr + +P.thickness * ps * 0.9;
}

function hit(inst, tx, ty, hr, ps) {
  var st = style(inst.fx.params);
  if (st === "crescent_wave") return waveHit(inst, tx, ty, hr, ps);
  if (st === "blade_extension") return extHit(inst, tx, ty, hr, ps);
  if (isStrike(st)) return STRIKE().hit(inst, tx, ty, hr, ps);
  return slashHit(inst, tx, ty, hr, ps);
}
function onHit(inst, x, y, ps) {
  var st = style(inst.fx.params);
  if (isStrike(st)) STRIKE().onHit(inst, x, y, ps || 1);
  else if (CUTS[st] !== undefined) slashOnHit(inst);
  inst.tq_hits.push([+x, +y, inst.age]);
}

// ================================================================ drawing
function Pen(g) { this.g = g; }
function col(c, a) {
  var k = function (v) { return Math.max(0, Math.min(255, Math.trunc(v))); };
  return "rgba(" + k(c[0]) + "," + k(c[1]) + "," + k(c[2]) + "," + k(a) / 255 + ")";
}
Pen.prototype.add = function (on) { this.g.globalCompositeOperation = on ? "lighter" : "source-over"; };
Pen.prototype.poly = function (pts, c, a) {
  if (a <= 1 || pts.length < 3) return;
  var g = this.g;
  g.fillStyle = col(c, a);
  g.beginPath(); g.moveTo(pts[0][0], pts[0][1]);
  for (var i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]);
  g.closePath(); g.fill();
};
Pen.prototype.glow = function (x, y, r, c, a, mid) {
  if (r <= 0.5 || a <= 1) return;
  mid = mid == null ? 0.35 : mid;
  var g = this.g, gr = g.createRadialGradient(x, y, 0, x, y, r);
  gr.addColorStop(0, col(c, a)); gr.addColorStop(mid, col(c, a * 0.45)); gr.addColorStop(1, col(c, 0));
  g.fillStyle = gr; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill();
};
Pen.prototype.line = function (x0, y0, x1, y1, c, a, w) {
  if (a <= 1 || w <= 0.05) return;
  var g = this.g;
  g.strokeStyle = col(c, a); g.lineWidth = w; g.lineCap = "round";
  g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
};
Pen.prototype.polyline = function (pts, c, a, w) {
  if (a <= 1 || w <= 0.05 || pts.length < 2) return;
  var g = this.g;
  g.strokeStyle = col(c, a); g.lineWidth = w; g.lineCap = "round"; g.lineJoin = "round";
  g.beginPath(); g.moveTo(pts[0][0], pts[0][1]);
  for (var i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]);
  g.stroke();
};
Pen.prototype.diamond = function (x0, y0, x1, y1, hw, c, a) {
  if (a <= 1 || hw <= 0.05) return;
  var dx = x1 - x0, dy = y1 - y0, L = hyp(dx, dy) || 1, nx = -dy / L * hw, ny = dx / L * hw, mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
  this.poly([[x0, y0], [mx + nx, my + ny], [x1, y1], [mx - nx, my - ny]], c, a);
};
Pen.prototype.ring = function (x, y, rx, ry, ang, c, a, w) {
  if (a <= 1 || w <= 0.05 || rx <= 0.5 || ry <= 0.5) return;
  var ca = Math.cos(ang), sa = Math.sin(ang), pts = [];
  for (var i = 0; i < 25; i++) {
    var t = i / 24 * Math.PI * 2, px = Math.cos(t) * rx, py = Math.sin(t) * ry;
    pts.push([x + px * ca - py * sa, y + px * sa + py * ca]);
  }
  this.polyline(pts, c, a, w);
};
function star(pen, x, y, ux, uy, lr, sr, c, a, w) {
  pen.line(x - ux * lr, y - uy * lr, x + ux * lr, y + uy * lr, c, a, w);
  pen.line(x + uy * sr, y - ux * sr, x - uy * sr, y + ux * sr, c, a, w);
}
function hitMarks(pen, inst, c, ps, dx, dy, dirf) {
  var t = inst.age;
  inst.tq_hits.forEach(function (h) {
    var x = h[0], y = h[1], k = t - h[2];
    if (k < 0 || k >= HIT_MARK_LIFE) return;
    var u0 = dirf ? dirf(h[2]) : [dx, dy];
    var f = 1 - k / HIT_MARK_LIFE, e = easeOut3(k / 4), L = (18 + 10 * e) * ps;
    [u0, FXK().rot(u0.slice(), 70)].forEach(function (u) {
      pen.diamond(x - u[0] * L, y - u[1] * L, x + u[0] * L, y + u[1] * L, 3.2 * ps * f + 0.3, c, 220 * f);
      pen.diamond(x - u[0] * L * 0.9, y - u[1] * L * 0.9, x + u[0] * L * 0.9, y + u[1] * L * 0.9, 1.1 * ps * f + 0.2, HOT, 255 * f);
    });
    var rr = (4 + 20 * easeOut3(k / HIT_MARK_LIFE)) * ps;
    pen.ring(x, y, rr, rr, 0, c, 200 * f, 2 * ps * f);
    pen.glow(x, y, 14 * ps * f, HOT, 230 * f);
  });
}

// ---------------------------------------------------------------- slash
// One cut of a slash-family style at its own tick t.
function drawCut(pen, inst, ps, g, fr, t, ci, c, bright) {
  var P = inst.fx.params;
  var st = g.state(t), tail = st[0], head = st[1], ga = st[2];
  var R = g.R, Ts = g.Ts;
  var sl = g.slices(t);
  var W = function (s, r) { var l = g.local(s, r); return fr.w(l[0], l[1]); };
  var i, j, k;
  if (sl.length && t <= Ts + 6) {
    var bf = ga * (t <= Ts ? 1 : 1 - (t - Ts) / 6), bm = W(tail + (head - tail) * 0.7, R);
    pen.glow(bm[0], bm[1], Math.min(0.9 * R, 36 * ps), c, 80 * bf, 0.4);
  }
  for (i = 1; i < sl.length; i++) {
    var s0 = sl[i - 1][0], w0 = sl[i - 1][2], s1 = sl[i][0], u1 = sl[i][1], w1 = sl[i][2];
    var a = ga * Math.pow(u1, 0.9);
    if (a <= 0.01) continue;
    var hz = 5 * ps;
    pen.poly([W(s0, R + 0.3 * w0 + hz), W(s1, R + 0.3 * w1 + hz), W(s1, R - 0.7 * w1 - hz), W(s0, R - 0.7 * w0 - hz)], c, 70 * a);
    pen.poly([W(s0, R + 0.3 * w0), W(s1, R + 0.3 * w1), W(s1, R - 0.7 * w1), W(s0, R - 0.7 * w0)], mix(c, bright, u1 * u1), 235 * a);
    var e0 = Math.max(1.2 * ps, 0.3 * w0), e1 = Math.max(1.2 * ps, 0.3 * w1);
    pen.poly([W(s0, R + 0.3 * w0), W(s1, R + 0.3 * w1), W(s1, R + 0.3 * w1 - e1), W(s0, R + 0.3 * w0 - e0)], HOT, 255 * Math.pow(a, 1.2));
  }
  if (t <= Ts + 4 && head - tail > 0.05) {
    var sf = t <= Ts ? 1 : 1 - (t - Ts) / 4;
    for (k = 0; k < 3; k++) {
      var r = R + (5 + 4 * k) * ps, sa = Math.max(tail, head - 0.45 + 0.1 * k), sb = head - 0.05;
      if (sb - sa < 0.02) continue;
      var pl = [];
      for (j = 0; j < 10; j++) pl.push(W(sa + (sb - sa) * j / 9, r));
      pen.polyline(pl, c, 120 * sf * (1 - k * 0.25), 1.1 * ps);
    }
  }
  var k2 = (t - (Ts - 1)) / 10;
  if (k2 >= 0 && k2 < 1) {
    var path = [];
    for (j = 0; j < 25; j++) path.push(W(j / 24, R + 0.1 * g.W));
    pen.polyline(path, c, 160 * (1 - k2), 3.5 * ps);
    pen.polyline(path, HOT, 255 * Math.pow(1 - k2, 2), 1.2 * ps);
  }
  var k3 = (t - Ts) / 12;
  if (k3 >= 0 && k3 < 1) {
    var rr = R * (1 + 0.35 * easeOut3(k3)), pw = [];
    for (j = 0; j < 21; j++) pw.push(W(0.1 + 0.8 * j / 20, rr));
    pen.polyline(pw, c, 130 * (1 - k3), 2 * ps * (1 - k3) + 0.2);
  }
  if (t <= Ts + 3) {
    var fa = t <= Ts ? 1 : 1 - (t - Ts) / 3, hp = W(head, R), pp = W(Math.max(0, head - 0.03), R);
    var ux = hp[0] - pp[0], uy = hp[1] - pp[1], n = hyp(ux, uy) || 1;
    ux /= n; uy /= n;
    pen.glow(hp[0], hp[1], 14 * ps, c, 200 * fa);
    pen.glow(hp[0], hp[1], 6 * ps, HOT, 255 * fa);
    star(pen, hp[0], hp[1], ux, uy, 16 * ps, 6 * ps, HOT, 230 * fa, 1.4 * ps);
  }
  var nsp = Math.max(0, Math.round(16 * (+P.density || 1))), drag = 0.88, grav = 0.22 * ps;
  for (i = 0; i < nsp; i++) {
    var rg = rngFor(inst.seed, i, 7 + 100 * ci), b = 1 + rg() * (Ts - 1), life = 10 + rg() * 10, kk = t - b;
    if (kk < 0 || kk >= life) continue;
    var sb2 = easeOut3(b / Ts), p0 = W(sb2, R + 0.2 * g.W), p1 = W(Math.min(1, sb2 + 0.02), R + 0.2 * g.W);
    var tx = p1[0] - p0[0], ty = p1[1] - p0[1], nn = hyp(tx, ty) || 1;
    tx /= nn; ty /= nn;
    var ph = g.phi(sb2), rd = fr.d(ph[0], ph[1]);
    var sp = rg.uniform(2.5, 6.5) * ps, out = rg.uniform(0.1, 0.7);
    var vx = (tx + rd[0] * out) * sp, vy = (ty + rd[1] * out) * sp, fd = dragDist(drag, kk);
    var x = p0[0] + vx * fd, y = p0[1] + vy * fd + 0.5 * grav * kk * kk, dk = Math.pow(drag, kk);
    var cvx = vx * dk, cvy = vy * dk + grav * kk, q = kk / life;
    pen.line(x, y, x - cvx * 1.6, y - cvy * 1.6, mix(HOT, c, q), 255 * (1 - q), 1.6 * ps);
  }
}
// combo_cross: the X flares where the two cuts cross once the second ends.
function drawCross(pen, inst, ps, fr, c, starts) {
  var a = inst.age - (starts[1] + swing(inst.fx.params));
  if (a < 0 || a >= CROSS_LIFE) return;
  var ga = new SlashGeo(inst, ps, 0), gb = new SlashGeo(inst, ps, 1);
  var pa = ga.local(0.5, ga.R), pb = gb.local(0.5, gb.R), m = fr.w((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2), x = m[0], y = m[1];
  var q = a / CROSS_LIFE, e = easeOut3(a / 6), L = (0.9 + 0.5 * e) * ga.R;
  [ga, gb].forEach(function (gg) {
    var u = fr.d(gg.d[0], gg.d[1]), ux = u[0], uy = u[1];
    pen.diamond(x - ux * L, y - uy * L, x + ux * L, y + uy * L, 6 * ps * (1 - q) + 0.3, c, 230 * (1 - q));
    pen.diamond(x - ux * L * 0.92, y - uy * L * 0.92, x + ux * L * 0.92, y + uy * L * 0.92, 2 * ps * (1 - q) + 0.2, HOT, 255 * (1 - q));
  });
  pen.glow(x, y, (20 + 26 * e) * ps * (1 - q), HOT, 240 * (1 - q));
  pen.glow(x, y, (34 + 30 * e) * ps, c, 150 * (1 - q), 0.4);
  var rr = 8 * ps + 0.9 * ga.R * easeOut3(q);
  pen.ring(x, y, rr, rr, 0, c, 200 * (1 - q), 2.6 * ps * (1 - q) + 0.2);
  for (var i = 0; i < 10; i++) {
    var r = rngFor(inst.seed, i, 31), life = 10 + 8 * r();
    if (a >= life) continue;
    var an = r.uniform(0, Math.PI * 2), sp = r.uniform(3, 8) * ps, fd = dragDist(0.86, a);
    var sx = x + Math.cos(an) * sp * fd, sy = y + Math.sin(an) * sp * fd, dk = Math.pow(0.86, a), qq = a / life;
    pen.line(sx, sy, sx - Math.cos(an) * sp * dk * 1.8, sy - Math.sin(an) * sp * dk * 1.8, mix(HOT, c, qq), 255 * (1 - qq), 1.5 * ps);
  }
}
function drawSlash(pen, inst, host, ps) {
  var P = inst.fx.params, fr = frame(inst), cs = colours(inst, host), c = cs[0], bright = cs[1];
  pen.add(true);
  var starts = cutStarts(P), end = swing(P) + fadeT(P) + SPARK_LIFE, geos = [];
  starts.forEach(function (s, ci) { geos.push(new SlashGeo(inst, ps, ci)); });
  starts.forEach(function (s, ci) {
    var t = inst.age - s;
    if (t >= 0 && t < end) drawCut(pen, inst, ps, geos[ci], fr, t, ci, c, bright);
  });
  if (style(P) === "combo_cross") drawCross(pen, inst, ps, fr, c, starts);
  var dirf = starts.length > 1 ? function (b) {
    var ci = 0;
    starts.forEach(function (s, i) { if (s <= b) ci = i; });
    return fr.d(geos[ci].d[0], geos[ci].d[1]);
  } : null;
  var dd = fr.d(geos[0].d[0], geos[0].d[1]);
  hitMarks(pen, inst, c, ps, dd[0], dd[1], dirf);
}

// ---------------------------------------------------------------- crescent wave
function waveShape(fr, g, k, t, ox) {
  ox = ox || 0;
  var pts = g.pts(t, k), outer = [], inner = [];
  pts.forEach(function (q) {
    var o = q[1], dr = q[2], w = q[3];
    outer.push(fr.w(o[0] + ox, o[1])); inner.push(fr.w(o[0] - dr[0] * w + ox, o[1] - dr[1] * w));
  });
  return [pts, outer, inner];
}
function rev(a) { return a.slice().reverse(); }
function drawWave(pen, inst, host, ps) {
  var P = inst.fx.params, t = inst.age, g = new WaveGeo(inst, ps), fr = frame(inst);
  var cs = colours(inst, host), c = cs[0], deep = cs[2];
  var L = g.L, k = g.grow(t), ph = (inst.seed % 1000) * 0.01;
  var fade = t < L ? 1 : 1 - cl((t - L) / 8);
  var fx_ = inst.tq_f[0], fy_ = inst.tq_f[1], o0 = inst.tq_o;
  var spd = hyp(inst.x - o0[0], inst.y - o0[1]) / Math.max(1, Math.min(t, L));
  var R = g.R, S = ps, i, j, a, q, e, r;
  pen.add(true);
  var posAt = function (b) { b = Math.min(b, L); return [o0[0] + fx_ * spd * b, o0[1] + fy_ * spd * b]; };
  if (t > 1) {
    var gf = t < L ? 1 : 1 - cl((t - L) / 16), back = fr.w(-0.35 * R * k, 0), n = 12;
    for (i = 0; i < n; i++) {
      var a0 = i / n, a1 = (i + 1) / n;
      var x0 = o0[0] + (back[0] - o0[0]) * a0, y0 = o0[1] + (back[1] - o0[1]) * a0;
      var x1 = o0[0] + (back[0] - o0[0]) * a1, y1 = o0[1] + (back[1] - o0[1]) * a1;
      var al = gf * Math.pow(a1, 1.5);
      pen.line(x0, y0, x1, y1, c, 90 * al, 3 * S);
      pen.line(x0, y0, x1, y1, HOT, 120 * al, 1 * S);
    }
  }
  for (var b = 0; b <= Math.min(t, L); b += 8) {
    a = t - b;
    if (a >= 14) continue;
    e = easeOut3(a / 14); q = 1 - a / 14;
    var cc = posAt(b);
    pen.ring(cc[0] - fx_ * 0.2 * R, cc[1] - fy_ * 0.2 * R, (0.25 + 0.35 * e) * R * k, (0.9 + 0.6 * e) * R * k, Math.atan2(fy_, fx_), c, 90 * q, 1.4 * S * q + 0.2);
  }
  if (t < 14) {
    q = t / 14; e = easeOut3(q);
    pen.glow(o0[0], o0[1], (14 + 30 * e) * S, c, 160 * (1 - q));
    var vx = fr.vx, vy = fr.vy;
    pen.diamond(o0[0] - vx * 45 * S, o0[1] - vy * 45 * S, o0[0] + vx * 45 * S, o0[1] + vy * 45 * S, 4 * S * (1 - q) + 0.2, c, 220 * (1 - q));
    pen.diamond(o0[0] - vx * 40 * S, o0[1] - vy * 40 * S, o0[0] + vx * 40 * S, o0[1] + vy * 40 * S, 1.3 * S * (1 - q) + 0.2, HOT, 255 * (1 - q));
    pen.ring(o0[0], o0[1], (6 + 26 * e) * S, (6 + 26 * e) * S, 0, c, 180 * (1 - q), 2.2 * S * (1 - q) + 0.2);
  }
  if (fade > 0) {
    var sh;
    for (j = 1; j < 4; j++) { sh = waveShape(fr, g, k, t, -spd * 2.2 * j); pen.poly(sh[1].concat(rev(sh[2])), c, 55 / j * fade); }
    sh = waveShape(fr, g, k, t);
    var pts = sh[0], outer = sh[1], inner = sh[2];
    var auraO = pts.map(function (p) { return fr.w(p[1][0] + p[2][0] * 6 * S * k, p[1][1] + p[2][1] * 6 * S * k); });
    var auraI = pts.map(function (p) { var m = p[3] + 4 * S * k; return fr.w(p[1][0] - p[2][0] * m, p[1][1] - p[2][1] * m); });
    pen.poly(auraO.concat(rev(auraI)), c, 80 * fade);
    var tongues = [];
    for (i = 0; i < 11; i++) {
      var v = -0.9 + 1.8 * i / 10, an = v * WAVE_ARC_DEG * D, dx = Math.cos(an), dy = Math.sin(an);
      var ww = g.W * k * Math.pow(1 - Math.pow(Math.abs(v), 1.8), 0.85);
      var bx = (WAVE_CX * R + R * dx) * k - dx * ww * 0.8, by = R * dy * k - dy * ww * 0.8;
      r = rngFor(inst.seed, i, 17);
      var ln = (18 + 30 * flame(v, t, ph + i) * r.uniform(0.6, 1.4)) * S * k * (1 - 0.45 * Math.abs(v));
      var ux = -1, uy = 0.6 * v + 0.25 * Math.sin(t * 0.7 + i * 1.7), nn = hyp(ux, uy);
      tongues.push([fr.w(bx, by), fr.w(bx + ux / nn * ln, by + uy / nn * ln), ln, r.uniform(3.4, 5.2) * S * k]);
    }
    var bk = fr.w(WAVE_CX * R * k - 0.2 * R * k, 0);
    pen.glow(bk[0], bk[1], 1.1 * R * k, c, 70 * fade, 0.4);
    tongues.forEach(function (tg) { pen.diamond(tg[0][0], tg[0][1], tg[1][0], tg[1][1], tg[3], c, 170 * fade); });
    pen.poly(outer.concat(rev(inner)), mix(c, HOT, 0.25), 235 * fade);
    pen.add(false);
    tongues.forEach(function (tg) {
      var b0 = tg[0], b1 = tg[1];
      var m0 = [b0[0] + (b1[0] - b0[0]) * 0.08, b0[1] + (b1[1] - b0[1]) * 0.08], m1 = [b0[0] + (b1[0] - b0[0]) * 0.75, b0[1] + (b1[1] - b0[1]) * 0.75];
      pen.diamond(m0[0], m0[1], m1[0], m1[1], tg[3] * 0.5, deep, 220 * fade);
    });
    var coreO = pts.map(function (p) { return fr.w(p[1][0] - p[2][0] * p[3] * 0.3, p[1][1] - p[2][1] * p[3] * 0.3); });
    var coreI = pts.map(function (p) { var m = p[3] * (0.88 + 0.2 * flame(p[0], t, ph)); return fr.w(p[1][0] - p[2][0] * m, p[1][1] - p[2][1] * m); });
    var cO = coreO.slice(2, -2), cI = coreI.slice(2, -2);
    pen.poly(cO.concat(rev(cI)), deep, 240 * fade);
    pen.add(true);
    pen.polyline(cO, c, 120 * fade, 1 * S);
    var front = [];
    for (j = 0; j < pts.length; j++) if (Math.abs(pts[j][0]) < 0.85) front.push(outer[j]);
    pen.polyline(front, HOT, 255 * fade, 2.2 * S * k);
    var mid = outer[Math.floor(outer.length / 2)];
    pen.glow(mid[0], mid[1], 20 * S * k, c, 130 * fade);
  }
  var per = Math.max(0, Math.round(3 * (+P.density || 1)));
  for (b = Math.max(0, t - WAVE_EMBER_LIFE); b < Math.min(t, L); b++) {
    for (j = 0; j < per; j++) {
      r = rngFor(inst.seed, b, j);
      var life = 14 + 16 * r();
      a = t - b;
      if (a >= life) continue;
      var v2 = r.uniform(-0.9, 0.9), an2 = v2 * WAVE_ARC_DEG * D, ww2 = g.W * Math.pow(1 - Math.pow(Math.abs(v2), 1.8), 0.85);
      var lx = WAVE_CX * R + R * Math.cos(an2) - Math.cos(an2) * ww2, ly = R * Math.sin(an2) - Math.sin(an2) * ww2;
      var bp = posAt(b), dl = fr.d(lx, ly), sx = bp[0] + dl[0], sy = bp[1] + dl[1];
      var bv = r.uniform(0.5, 2.5) * S, pv = r.uniform(-1.2, 1.2) * S;
      var evx = -fx_ * bv + fr.vx * pv, evy = -fy_ * bv + fr.vy * pv, fd = dragDist(0.93, a), grav = 0.18 * S;
      var x = sx + evx * fd, y = sy + evy * fd + 0.5 * grav * a * a;
      q = a / life;
      var ecol = q < 0.5 ? mix(HOT, c, Math.min(1, q * 2)) : mix(c, deep, (q - 0.5) * 2);
      pen.diamond(x - 1.8 * S, y, x + 1.8 * S, y, 1.4 * S * (1 - q * 0.5), ecol, 230 * (1 - q));
    }
  }
  if (t >= L) {
    a = t - L; q = a / WAVE_SHARD_LIFE;
    if (q < 1) {
      var ff = 1 - Math.min(1, a / 10);
      pen.glow(inst.x, inst.y, 40 * S * ff, HOT, 200 * ff);
      for (i = 0; i < 10; i++) {
        r = rngFor(inst.seed, i, 91);
        var v3 = r.uniform(-0.9, 0.9), an3 = v3 * WAVE_ARC_DEG * D;
        var pp = fr.w(WAVE_CX * R + R * Math.cos(an3), R * Math.sin(an3));
        var dd = fr.d(Math.cos(an3) + r.uniform(-0.4, 0.4), Math.sin(an3) + r.uniform(-0.4, 0.4));
        var sp = r.uniform(2, 6) * S, fd2 = dragDist(0.93, a);
        var sx2 = pp[0] + dd[0] * sp * fd2, sy2 = pp[1] + dd[1] * sp * fd2 + 0.05 * S * a * a;
        var rot = r.uniform(0, Math.PI * 2) + r.uniform(-0.25, 0.25) * a, ln2 = r.uniform(7, 12) * S;
        var uxs = Math.cos(rot) * ln2, uys = Math.sin(rot) * ln2;
        pen.diamond(sx2 - uxs, sy2 - uys, sx2 + uxs, sy2 + uys, 2.4 * S * (1 - q) + 0.2, c, 230 * (1 - q));
        pen.diamond(sx2 - uxs * 0.7, sy2 - uys * 0.7, sx2 + uxs * 0.7, sy2 + uys * 0.7, 0.8 * S * (1 - q) + 0.1, HOT, 255 * (1 - q));
      }
    }
  }
  hitMarks(pen, inst, c, ps, fx_, fy_);
}

// ---------------------------------------------------------------- blade extension
function drawExtension(pen, inst, host, ps) {
  var P = inst.fx.params, t = inst.age, fr = frame(inst);
  var cs = colours(inst, host), c = cs[0], bright = cs[1];
  var S = ps, Lmax = +P.length * ps, W = +P.thickness * ps, Th = holdT(P), l = extLen(P, t, Lmax);
  var ox = inst.x, oy = inst.y, fx_ = inst.tq_f[0], fy_ = inst.tq_f[1], i, j, r, a, q;
  pen.add(true);
  if (t < EXT_CHARGE + 2) {
    var cp = cl(t / EXT_CHARGE), fa = t < EXT_CHARGE ? 1 : 1 - (t - EXT_CHARGE) / 2;
    for (i = 0; i < 8; i++) {
      r = rngFor(inst.seed, i, 3);
      var an = (i * 45 + r.uniform(-15, 15)) * D, r0 = 26 * S * (1 - cp) + 4 * S, r1 = r0 * 0.4;
      pen.line(ox + Math.cos(an) * r0, oy + Math.sin(an) * r0, ox + Math.cos(an) * r1, oy + Math.sin(an) * r1, mix(c, HOT, cp), 220 * fa, 1.3 * S);
    }
    pen.glow(ox, oy, (4 + 10 * cp) * S, HOT, 230 * fa);
  }
  if (l > 0 || t < EXT_CHARGE) { pen.glow(ox, oy, 10 * S, c, 170); pen.glow(ox, oy, 4 * S, HOT, 255); }
  if (l > 1) {
    var n = 24, us = [];
    for (j = 0; j <= n; j++) us.push(j / n);
    var edge = function (m) {
      var top = us.map(function (u) { return fr.w(u * l, -extHw(u, W) * m); });
      var bot = us.map(function (u) { return fr.w(u * l, extHw(u, W) * m); });
      return top.concat(rev(bot));
    };
    var shim = 0.85 + 0.15 * Math.sin(t * 1.3);
    pen.poly(edge(2.8), c, 40);
    pen.poly(edge(1.7), c, 100 * shim);
    for (j = 0; j < n; j++) {
      var u0 = us[j], u1 = us[j + 1], h0 = extHw(u0, W), h1 = extHw(u1, W);
      pen.poly([fr.w(u0 * l, -h0), fr.w(u1 * l, -h1), fr.w(u1 * l, h1), fr.w(u0 * l, h0)], mix(c, bright, u1), 220 * (0.85 + 0.15 * Math.sin(t * 1.3 + u1 * 12)));
    }
    pen.poly(edge(0.32), HOT, 255);
    for (var kk = 0; kk < 3; kk++) {
      var phs = frac(t * 0.09 + kk / 3), x = phs * l, hw = extHw(phs, W) * 2.4, a0 = fr.w(x, -hw), a1 = fr.w(x, hw);
      pen.diamond(a0[0], a0[1], a1[0], a1[1], 2.5 * S, HOT, 200 * (1 - phs) * (l / Lmax));
    }
    if (l > 0.3 * Lmax) {
      for (kk = 0; kk < 4; kk++) {
        r = rngFor(((inst.seed >>> 0) ^ Math.imul(Math.floor(t / 2) + 1, 0x45D9F3B)) >>> 0, kk, 5);
        var side = kk % 2 ? 1 : -1, uu0 = r.uniform(0.1, 0.8), du = r.uniform(0.12, 0.25), pts = [];
        for (j = 0; j < 5; j++) {
          var u = Math.min(1, uu0 + du * j / 4);
          var off = side * extHw(u, W) * r.uniform(1.1, 1.5) + r.uniform(-2.5, 2.5) * S;
          pts.push(fr.w(u * l, off));
        }
        pen.polyline(pts, c, 200, 1.4 * S);
        pen.polyline(pts, HOT, 200, 0.6 * S);
      }
    }
    var tip = fr.w(l, 0);
    pen.glow(tip[0], tip[1], 22 * S, c, 90);
    pen.glow(tip[0], tip[1], 10 * S, HOT, 200);
    star(pen, tip[0], tip[1], fx_, fy_, 20 * S, 8 * S, HOT, 230, 1.4 * S);
  }
  var tE = EXT_CHARGE + EXT_EXTEND;
  a = t - tE;
  if (a >= 0 && a < 12) {
    q = a / 12;
    var e = easeOut3(q), tp = fr.w(Lmax, 0);
    pen.ring(tp[0], tp[1], (4 + 10 * e) * S, (6 + 26 * e) * S, Math.atan2(fy_, fx_), c, 220 * (1 - q), 2.2 * S * (1 - q) + 0.2);
    pen.glow(tp[0], tp[1], 26 * S * (1 - q), HOT, 200 * (1 - q));
    for (i = 0; i < 8; i++) {
      r = rngFor(inst.seed, i, 11);
      var life = 10 + 6 * r();
      if (a >= life) continue;
      var an2 = Math.atan2(fy_, fx_) + r.uniform(-50, 50) * D, sp = r.uniform(3, 7) * S, fd = dragDist(0.88, a);
      var sx = tp[0] + Math.cos(an2) * sp * fd, sy = tp[1] + Math.sin(an2) * sp * fd, dk = Math.pow(0.88, a), qq = a / life;
      pen.line(sx, sy, sx - Math.cos(an2) * sp * dk * 1.6, sy - Math.sin(an2) * sp * dk * 1.6, mix(HOT, c, qq), 255 * (1 - qq), 1.3 * S);
    }
  }
  var t2 = EXT_CHARGE + EXT_EXTEND + Th;
  if (t >= t2) {
    var nd = Math.max(0, Math.round(18 * (+P.density || 1)));
    for (i = 0; i < nd; i++) {
      r = rngFor(inst.seed, i, 13);
      var uu = r.uniform(0.05, 1), b = t2 + EXT_RETRACT * Math.pow(1 - uu, 1 / 3), aa = t - b;
      if (aa < 0 || aa >= EXT_DUST) continue;
      var q2 = aa / EXT_DUST, drift = r.uniform(-0.5, 0.5) * S * aa, p = fr.w(uu * Lmax, drift);
      pen.glow(p[0], p[1] - 0.15 * S * aa, 3.2 * S * (1 - q2) + 0.6, mix(c, HOT, 0.5), 230 * (1 - q2), 0.5);
    }
  }
  hitMarks(pen, inst, c, ps, fx_, fy_);
}

function draw(g, inst, host, ps) {
  var pen = new Pen(g), st = style(inst.fx.params);
  if (st === "crescent_wave") drawWave(pen, inst, host, ps);
  else if (st === "blade_extension") drawExtension(pen, inst, host, ps);
  else if (isStrike(st)) STRIKE().draw(pen, inst, host, ps);
  else drawSlash(pen, inst, host, ps);
}

// strikefx.js (ki blasts, punches) builds on these.
G.SWORDFX = {draw: draw, hit: hit, onHit: onHit, onSpawn: onSpawn, onTick: onTick, activeTicks: activeTicks, totalTicks: totalTicks,
             vivid: vivid, CUTS: CUTS,
             lib: {style: style, swing: swing, holdT: holdT, frame: frame, Frame: Frame, colours: colours, Pen: Pen, star: star,
                   rngFor: rngFor, mix: mix, easeOut3: easeOut3, easeIn3: easeIn3, dragDist: dragDist, hyp: hyp, HOT: HOT, D: D}};
})(window);
