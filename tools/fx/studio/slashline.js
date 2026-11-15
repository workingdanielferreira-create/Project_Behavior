/* Straight slash — FX Studio's port of laser/slashline.py: one sword cut of
 * the FX Kit "technique" primitive (params.style "straight_slash") laid out
 * yourself: cut_deg (the way the blade travels, local, mirrors with the
 * facing), length, curve_pct (0 = straight, 100 = half circle, negative =
 * the other way), slash_from start / end / centre, thickness, swing_ticks,
 * hold_ticks.  Its MIDDLE is the anchor point, so anchored on the target it
 * always lands on the target.  Same timeline, random streams (FXK.rng),
 * geometry and painting order as the game.  Keep the two in step.
 *
 * Size: in the game it follows the world's position scale at its own spot
 * (kamehameha style) and stands upright there on the big ball; the Studio
 * has no world scale, so here it is the size it was fired at.
 * Builds on swordfx.js (pen, maths, colours): load it after it.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };
var STYLES = ["straight_slash"];
var FROMS = ["start", "end", "centre"];
var SLICES = 28, SPARK_LIFE = 20, FADE_MIN = 6;
var HOT = [255, 255, 255], D = Math.PI / 180;

// ---------------------------------------------------------------- params / timeline
function num(P, k, d) { var v = P[k]; if (v === undefined || v === null || v === "") return d; v = +v; return isFinite(v) ? v : d; }
function from_(P) { return FROMS.indexOf(P.slash_from) >= 0 ? P.slash_from : "start"; }
function hold(P) { return Math.max(0, Math.trunc(num(P, "hold_ticks", 8))); }
function fade(P) { return Math.max(FADE_MIN, Math.round(1.6 * L_().swing(P))); }
function activeTicks(P) { return L_().swing(P) + 2; }
function totalTicks(P) { return L_().swing(P) + hold(P) + fade(P) + SPARK_LIFE; }

// ---------------------------------------------------------------- size
function onSpawn(inst, host) { inst.sl_sc = null; }   // no world scale in the Studio
function size(inst, ps) { return inst.ps || ps || 1; }

// ---------------------------------------------------------------- geometry
function Geo(inst, S) {
  var P = inst.fx.params;
  this.L = num(P, "length", 240) * S;
  this.W = Math.max(0, num(P, "thickness", 12)) * S;
  var a = num(P, "cut_deg", -30) * D;
  this.u = [Math.cos(a), Math.sin(a)];
  this.n = [-this.u[1], this.u[0]];
  var c = this.L / 2, h = num(P, "curve_pct", 25) / 100 * c;
  this.c = c; this.h = h;
  if (Math.abs(h) < 1e-6 || c <= 1e-9) this.R = null;
  else { this.R = (c * c + h * h) / (2 * h); this.th = 2 * Math.atan2(h, c); }
}
Geo.prototype.at = function (s) {
  var x, y;
  if (this.R === null) { x = this.L * (s - 0.5); y = 0; }
  else {
    var a = -this.th + 2 * this.th * s;
    x = this.R * Math.sin(a);
    y = -((this.h - this.R) + this.R * Math.cos(a) - this.h);
  }
  return [this.u[0] * x + this.n[0] * y, this.u[1] * x + this.n[1] * y];
};
Geo.prototype.tangent = function (s) {
  var a = this.at(Math.max(0, s - 0.01)), b = this.at(Math.min(1, s + 0.01));
  var dx = b[0] - a[0], dy = b[1] - a[1], n = Math.sqrt(dx * dx + dy * dy) || 1;
  return [dx / n, dy / n];
};
Geo.prototype.width = function (s) { return this.W * Math.pow(Math.sin(Math.PI * L_().cl(s)), 0.6); };

// [lo, hi, head (null = none), alpha, width factor] at tick t.
function span(P, t) {
  var L = L_(), Ts = L.swing(P), hd = hold(P), Tf = fade(P), k = L.easeOut3(t / Ts), fr = from_(P), lo, hi, head;
  if (fr === "end") { lo = 1 - k; hi = 1; head = 1 - k; }
  else if (fr === "centre") { lo = 0.5 - 0.5 * k; hi = 0.5 + 0.5 * k; head = null; }
  else { lo = 0; hi = k; head = k; }
  if (t <= Ts) return [lo, hi, head, 1, 1];
  if (t <= Ts + hd) return [lo, hi, null, 1, 1 - 0.25 * (t - Ts) / Math.max(1, hd)];
  var q = L.cl((t - Ts - hd) / Tf);
  return [lo, hi, null, 1 - q, 0.75 * (1 - q)];
}
function slices(g, lo, hi, wf) {
  var out = [];
  for (var i = 0; i <= SLICES; i++) { var s = lo + (hi - lo) * i / SLICES; out.push([s, g.width(s) * wf]); }
  return out;
}
function edge(fr, g, s, off) {
  var p = g.at(s), t = g.tangent(s);
  return fr.w(p[0] - t[1] * off, p[1] + t[0] * off);
}

// ---------------------------------------------------------------- hit / body
function hit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var sp = span(inst.fx.params, inst.age), lo = sp[0], hi = sp[1], wf = sp[4];
  if (hi - lo < 0.01) return false;
  var g = new Geo(inst, size(inst, ps)), fr = L_().frame(inst), sl = slices(g, lo, hi, wf);
  for (var i = 1; i < sl.length; i++) {
    var a = fr.w.apply(fr, g.at(sl[i - 1][0])), b = fr.w.apply(fr, g.at(sl[i][0]));
    if (FXK().segDist(tx, ty, a[0], a[1], b[0], b[1]) <= hr + Math.max(sl[i - 1][1], sl[i][1]) * 0.5) return true;
  }
  return false;
}
function body(inst, ps) {
  if (inst.age >= inst.life) return null;
  var sp = span(inst.fx.params, inst.age), lo = sp[0], hi = sp[1], wf = sp[4];
  if (hi - lo < 0.01) return null;
  var g = new Geo(inst, size(inst, ps)), fr = L_().frame(inst), pts = [];
  for (var j = 0; j <= 8; j++) pts.push(fr.w.apply(fr, g.at(lo + (hi - lo) * j / 8)));
  return [pts, Math.max(1, g.W * 0.5 * wf)];
}
function cutDir(inst) {
  var g = new Geo(inst, 1), fr = L_().frame(inst), t = g.tangent(0.5);
  if (from_(inst.fx.params) === "end") t = [-t[0], -t[1]];
  return fr.d(t[0], t[1]);
}

// ---------------------------------------------------------------- drawing
function draw(pen, inst, host, ps) {
  var L = L_(), P = inst.fx.params, t = inst.age, S = size(inst, ps), g = new Geo(inst, S), fr = L.frame(inst);
  var cs = L.colours(inst, host), c = cs[0], bright = cs[1], Ts = L.swing(P), hd = hold(P);
  pen.add(true);
  var sp = span(P, t), lo = sp[0], hi = sp[1], head = sp[2], ga = sp[3], wf = sp[4], i, j, k;
  var endT = Ts + hd + fade(P);
  if (t < endT && hi - lo > 0.004 && ga > 0.01) {
    var sl = slices(g, lo, hi, wf);
    if (t <= Ts + 6) {
      var bf = t <= Ts ? 1 : 1 - (t - Ts) / 6, m = fr.w.apply(fr, g.at((lo + hi) / 2));
      pen.glow(m[0], m[1], Math.min(0.45 * g.L, 40 * S), c, 80 * bf * ga, 0.4);
    }
    var hz = 5 * S;
    for (i = 1; i < sl.length; i++) {
      var s0 = sl[i - 1][0], w0 = sl[i - 1][1], s1 = sl[i][0], w1 = sl[i][1];
      if (w0 + w1 <= 0.02) continue;
      var u = head !== null && hi > lo ? 1 - Math.abs(s1 - head) / Math.max(1e-6, hi - lo) : 0.7;
      var a = ga * (0.35 + 0.65 * u);
      pen.poly([edge(fr, g, s0, 0.5 * w0 + hz), edge(fr, g, s1, 0.5 * w1 + hz), edge(fr, g, s1, -0.5 * w1 - hz), edge(fr, g, s0, -0.5 * w0 - hz)], c, 70 * a);
      pen.poly([edge(fr, g, s0, 0.5 * w0), edge(fr, g, s1, 0.5 * w1), edge(fr, g, s1, -0.5 * w1), edge(fr, g, s0, -0.5 * w0)],
               L.mix(c, bright, u * u), 235 * a);
      var e0 = Math.max(0.8 * S, 0.22 * w0), e1 = Math.max(0.8 * S, 0.22 * w1);
      pen.poly([edge(fr, g, s0, e0 * 0.5), edge(fr, g, s1, e1 * 0.5), edge(fr, g, s1, -e1 * 0.5), edge(fr, g, s0, -e0 * 0.5)], HOT, 255 * Math.pow(a, 1.2));
    }
    if (t <= Ts + 4) {
      var sf = t <= Ts ? 1 : 1 - (t - Ts) / 4;
      for (k = 0; k < 2; k++) [1, -1].forEach(function (sd) {
        var off = sd * (g.W * 0.5 + (5 + 5 * k) * S), a0 = lo + (hi - lo) * (0.1 + 0.1 * k), a1 = hi - (hi - lo) * 0.05;
        if (a1 - a0 < 0.02) return;
        var pl = [];
        for (var jj = 0; jj < 10; jj++) pl.push(edge(fr, g, a0 + (a1 - a0) * jj / 9, off));
        pen.polyline(pl, c, 110 * sf * (1 - 0.35 * k), 1.1 * S);
      });
    }
  }
  var k2 = (t - (Ts - 1)) / 10;
  if (k2 >= 0 && k2 < 1) {
    var path = [];
    for (j = 0; j < 25; j++) path.push(fr.w.apply(fr, g.at(j / 24)));
    pen.polyline(path, c, 160 * (1 - k2), 3.5 * S);
    pen.polyline(path, HOT, 255 * Math.pow(1 - k2, 2), 1.2 * S);
  }
  var k3 = (t - Ts) / 12;
  if (k3 >= 0 && k3 < 1) {
    var off3 = g.W * 0.5 + 18 * S * L.easeOut3(k3);
    [1, -1].forEach(function (sd) {
      var pl = [];
      for (var jj = 0; jj <= 20; jj++) pl.push(edge(fr, g, 0.1 + 0.8 * jj / 20, sd * off3));
      pen.polyline(pl, c, 110 * (1 - k3), 1.8 * S * (1 - k3) + 0.2);
    });
  }
  var frm = from_(P);
  if (t <= Ts + 3) {
    var fa = t <= Ts ? 1 : 1 - (t - Ts) / 3, kk = L.easeOut3(Math.min(t, Ts) / Ts);
    var heads = frm === "end" ? [1 - kk] : frm === "centre" ? [0.5 - 0.5 * kk, 0.5 + 0.5 * kk] : [kk];
    heads.forEach(function (hs) {
      var hp = fr.w.apply(fr, g.at(hs)), tg = g.tangent(hs), ud = fr.d(tg[0], tg[1]), ux = ud[0], uy = ud[1];
      if (frm === "end" || (frm === "centre" && hs < 0.5)) { ux = -ux; uy = -uy; }
      pen.glow(hp[0], hp[1], 14 * S, c, 200 * fa);
      pen.glow(hp[0], hp[1], 6 * S, HOT, 255 * fa);
      L.star(pen, hp[0], hp[1], ux, uy, 16 * S, 6 * S, HOT, 230 * fa, 1.4 * S);
    });
  }
  var nSp = Math.max(0, Math.round(16 * num(P, "density", 1))), drag = 0.88, grav = 0.22 * S;
  for (i = 0; i < nSp; i++) {
    var r = L.rngFor(inst.seed, i, 211), b = 1 + r() * (Ts - 1), life = 10 + r() * 10, kt = t - b;
    if (kt < 0 || kt >= life) continue;
    var kb = L.easeOut3(b / Ts);
    var sb = frm === "end" ? 1 - kb : frm === "centre" ? 0.5 + (i % 2 ? 0.5 : -0.5) * kb : kb;
    var p0 = fr.w.apply(fr, g.at(sb)), tg2 = g.tangent(sb), td = fr.d(tg2[0], tg2[1]), tx = td[0], ty = td[1];
    if (frm === "end" || (frm === "centre" && i % 2 === 0)) { tx = -tx; ty = -ty; }
    var side = r.uniform(-0.7, 0.7), spd = r.uniform(2.5, 6.5) * S;
    var vx = (tx - ty * side) * spd, vy = (ty + tx * side) * spd, fd = L.dragDist(drag, kt);
    var x = p0[0] + vx * fd, y = p0[1] + vy * fd + 0.5 * grav * kt * kt, dk = Math.pow(drag, kt);
    var cvx = vx * dk, cvy = vy * dk + grav * kt, q = kt / life;
    pen.line(x, y, x - cvx * 1.6, y - cvy * 1.6, L.mix(HOT, c, q), 255 * (1 - q), 1.6 * S);
  }
  var cd = cutDir(inst);
  L.hitMarks(pen, inst, c, S, cd[0], cd[1]);
}

G.SLASHLINE = {STYLES: STYLES, FROMS: FROMS, activeTicks: activeTicks, totalTicks: totalTicks, onSpawn: onSpawn,
               hit: hit, body: body, draw: draw, Geo: Geo};
})(window);
