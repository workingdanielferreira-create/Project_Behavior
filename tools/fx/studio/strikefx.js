/* Strikes — FX Studio's port of laser/strikefx.py: the ki barrage and impact
 * punch styles of the FX Kit "technique" primitive.  Same timeline, same
 * random streams (FXK.rng), same geometry and painting order as the game, so
 * the Studio preview draws what Solo and Battle draw.  Keep the two in step.
 * Builds on swordfx.js (frame, pen, maths): load it after that file.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };
var STYLES = ["ki_barrage", "impact_punch"];

var KI_SPEED = [9, 13], KI_RANGE = [0.85, 1.12], KI_SIDE = 7, KI_FLASH = 6, KI_BLAST_LIFE = 22, KI_SMOKE_LIFE = 44;
var SMOKE = [92, 86, 80];
var PUNCH_RETRACT = 5, PUNCH_IMPACT_LIFE = 24;

// ---------------------------------------------------------------- timeline
function cad(P) { return Math.max(1, Math.trunc(+P.swing_ticks || 3)); }
function hold(P) { return L_().holdT(P); }
function kiCount(P) { return Math.floor(hold(P) / cad(P)) + 1; }
function kiFlightMax(P) { return Math.ceil(+P.length * KI_RANGE[1] / KI_SPEED[0]); }
function activeTicks(P) {
  if (L_().style(P) === "ki_barrage") return (kiCount(P) - 1) * cad(P) + kiFlightMax(P) + 1;
  return L_().swing(P) + hold(P) + 1;
}
function totalTicks(P) {
  if (L_().style(P) === "ki_barrage") return activeTicks(P) + KI_SMOKE_LIFE;
  return L_().swing(P) + hold(P) + PUNCH_RETRACT + PUNCH_IMPACT_LIFE;
}

// ---------------------------------------------------------------- ki shots
// One ki blast: everything about it is rolled from the seed.
function Shot(inst, i, ps) {
  var P = inst.fx.params, L = L_(), r = L.rngFor(inst.seed, i, 41);
  var su = r.uniform(KI_SPEED[0], KI_SPEED[1]);
  this.i = i;
  this.b = i * cad(P);
  this.sp = su * ps;
  this.ang = r.uniform(-0.5, 0.5) * (+P.span || 0) * L.D;
  this.curve = r.uniform(-22, 22) * ps;
  this.size = r.uniform(0.75, 1.25);
  if (r() < 0.18) this.size *= 1.55;   // now and then a much bigger one
  var ru = r.uniform(KI_RANGE[0], KI_RANGE[1]);
  this.rng = +P.length * ru * ps;
  this.flight = Math.max(1, Math.ceil(+P.length * ru / su));
  this.side = i % 2 === 0 ? 1 : -1;
  this.tint = r.uniform(0, 0.4);
  this.kind = Math.min(2, Math.trunc(r() * 3));
  var path = inst.tq_path, o = path[Math.min(this.b, path.length - 1)];
  this.ox = o[0]; this.oy = o[1];
}
Shot.prototype.pos = function (fr, k) {
  var d = this.sp * k, u = this.rng > 0 ? Math.min(1, d / this.rng) : 1;
  var lat = this.curve * Math.sin(Math.PI * u), ca = Math.cos(this.ang), sa = Math.sin(this.ang);
  var w = fr.f.d(ca * d - sa * lat, sa * d + ca * lat + this.side * KI_SIDE * fr.s);
  return [this.ox + w[0], this.oy + w[1]];
};
Shot.prototype.end = function (inst) {   // [tick it detonates, stopped by a hit?]
  var h = inst.tq_ki[this.i];
  return h ? [h[0], true] : [this.b + this.flight, false];
};
function Fr(inst, ps) { this.f = new (L_().Frame)(0, 0, inst.tq_f, inst.tq_m); this.s = ps; }
function shots(inst, ps) {
  var out = [], n = kiCount(inst.fx.params);
  for (var i = 0; i < n; i++) out.push(new Shot(inst, i, ps));
  return out;
}
function live(inst, ps) {   // [[shot, position]] for the shots in flight this tick
  var out = [], fr = new Fr(inst, ps), t = inst.age, all = shots(inst, ps);
  for (var i = 0; i < all.length; i++) {
    var s = all[i];
    if (s.b > t) break;
    if (t < s.end(inst)[0]) out.push([s, s.pos(fr, t - s.b)]);
  }
  return out;
}
function kiHit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var r0 = +inst.fx.params.radius * ps, lv = live(inst, ps);
  for (var i = 0; i < lv.length; i++) {
    var p = lv[i][1];
    if (L_().hyp(p[0] - tx, p[1] - ty) <= hr + r0 * lv[i][0].size) return true;
  }
  return false;
}
function kiOnHit(inst, tx, ty, ps) {   // the shot nearest the target stops there and detonates
  var best = null, bd = null, lv = live(inst, ps);
  for (var i = 0; i < lv.length; i++) {
    var p = lv[i][1], d = L_().hyp(p[0] - tx, p[1] - ty);
    if (bd === null || d < bd) { best = lv[i]; bd = d; }
  }
  if (best) inst.tq_ki[best[0].i] = [inst.age, best[1][0], best[1][1]];
}

// ---------------------------------------------------------------- punch
function reach(P, t, Lm) {
  var L = L_(), Ts = L.swing(P), Th = hold(P);
  if (t < Ts) return Lm * L.easeOut3(t / Ts);
  if (t < Ts + Th) return Lm;
  if (t < Ts + Th + PUNCH_RETRACT) return Lm * (1 - L.easeIn3((t - Ts - Th) / PUNCH_RETRACT));
  return 0;
}
function punchHit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var P = inst.fx.params, l = reach(P, inst.age, +P.length * ps);
  if (l <= 2) return false;
  var b = L_().frame(inst).w(l, 0);
  return FXK().segDist(tx, ty, inst.x, inst.y, b[0], b[1]) <= hr + +P.radius * ps * 1.2;
}

// ---------------------------------------------------------------- public
function hit(inst, tx, ty, hr, ps) {
  return L_().style(inst.fx.params) === "ki_barrage" ? kiHit(inst, tx, ty, hr, ps) : punchHit(inst, tx, ty, hr, ps);
}
function onHit(inst, x, y, ps) {
  var P = inst.fx.params;
  if (L_().style(P) === "ki_barrage") { kiOnHit(inst, x, y, ps); return; }
  // the impact stays where the fist landed
  var l = reach(P, inst.age, +P.length * ps) + +P.radius * ps * 0.8, w = L_().frame(inst).w(l, 0);
  inst.tq_imp.push([inst.age, w[0], w[1]]);
}

// ================================================================ drawing
function blastAt(inst, s, fr) {
  var e = s.end(inst);
  if (e[1]) { var h = inst.tq_ki[s.i]; return [e[0], h[1], h[2]]; }
  var p = s.pos(fr, s.flight);
  return [e[0], p[0], p[1]];
}
function drawKi(pen, inst, host, ps) {
  var L = L_(), HOT = L.HOT, mix = L.mix, P = inst.fx.params, t = inst.age;
  var cs = L.colours(inst, host), c = cs[0], deep = cs[2];
  var fr = new Fr(inst, ps), r0 = +P.radius * ps, B0 = +P.thickness * ps, dens = +P.density || 1;
  var all = shots(inst, ps), smoke = mix(SMOKE, deep, 0.25), i, j, s;
  // 1: smoke piling up where the shots went off (painted normally, under the light)
  pen.add(false);
  var nPuff = Math.max(0, Math.round(3 * dens));
  for (i = 0; i < all.length; i++) {
    s = all[i];
    if (s.b > t) break;
    var bl = blastAt(inst, s, fr), a = t - bl[0];
    if (a < 0 || a >= KI_SMOKE_LIFE) continue;
    var q = a / KI_SMOKE_LIFE, B = B0 * s.size;
    for (j = 0; j < nPuff; j++) {
      var r = L.rngFor(inst.seed, s.i, 60 + j), an = r.uniform(0, Math.PI * 2);
      var dr = r.uniform(0.2, 0.9) * B * L.easeOut3(a / 18), rise = r.uniform(0.3, 0.8) * ps * a;
      var rad = B * r.uniform(0.6, 1) * (0.5 + 0.9 * L.easeOut3(a / 20));
      pen.glow(bl[1] + Math.cos(an) * dr, bl[2] + Math.sin(an) * dr - rise, rad, smoke,
               95 * Math.pow(1 - q, 1.5) * Math.min(1, a / 3), 0.6);
    }
  }
  pen.add(true);
  // 2: the hands glow while the barrage fires
  var last = all.length ? all[all.length - 1].b : 0;
  if (t <= last + 4) {
    var fa = t <= last ? 1 : 1 - (t - last) / 4, fl = 0.8 + 0.2 * Math.sin(t * 2.3);
    [1, -1].forEach(function (side) {
      var h = fr.f.d(0, side * KI_SIDE * ps);
      pen.glow(inst.x + h[0], inst.y + h[1], 16 * ps * fl, c, 150 * fa);
      pen.glow(inst.x + h[0], inst.y + h[1], 6 * ps, HOT, 220 * fa);
    });
  }
  for (i = 0; i < all.length; i++) {
    s = all[i];
    if (s.b > t) break;
    var k = t - s.b, en = s.end(inst), e = en[0], stopped = en[1];
    var tint = mix(c, HOT, 0.3 + s.tint), rs = r0 * s.size;
    // 3: muzzle flash at launch
    if (k < KI_FLASH) {
      var qf = k / KI_FLASH, m = s.pos(fr, 0), u = fr.f.d(Math.cos(s.ang), Math.sin(s.ang));
      pen.glow(m[0], m[1], (10 + 10 * L.easeOut3(qf)) * ps * s.size, c, 220 * (1 - qf));
      pen.glow(m[0], m[1], 6 * ps * s.size, HOT, 255 * (1 - qf));
      L.star(pen, m[0], m[1], u[0], u[1], 16 * ps * s.size * (1 - 0.4 * qf), 7 * ps * s.size, HOT, 230 * (1 - qf), 1.3 * ps);
    }
    // 4: the shot in flight — comet tail, halo, body, white-hot core
    if (t < e) {
      var p = s.pos(fr, k), tp = s.pos(fr, Math.max(0, k - 2.5)), fl2 = 0.88 + 0.12 * Math.sin(t * 1.7 + s.i * 2.1);
      pen.diamond(tp[0], tp[1], p[0], p[1], rs * 0.95, c, 140);
      pen.diamond(tp[0], tp[1], p[0], p[1], rs * 0.4, tint, 200);
      pen.glow(p[0], p[1], rs * 3.4 * fl2, c, 120);
      pen.glow(p[0], p[1], rs * 1.8, tint, 235);
      pen.glow(p[0], p[1], rs * 0.85, HOT, 255, 0.75);
      continue;
    }
    // 5: detonation
    var ad = t - e;
    if (ad >= KI_BLAST_LIFE) continue;
    var bp = blastAt(inst, s, fr), x = bp[1], y = bp[2];
    var qd = ad / KI_BLAST_LIFE, ee = L.easeOut3(ad / 8), Bd = B0 * s.size * (stopped ? 1 : 0.85);
    if (ad < 5) pen.glow(x, y, Bd * (0.7 + 0.9 * L.easeOut3(ad / 5)), HOT, 255 * (1 - ad / 5));
    pen.glow(x, y, Bd * (0.9 + 1.0 * ee), c, 210 * (1 - qd), 0.45);
    pen.glow(x, y, Bd * (0.5 + 0.45 * ee), mix(c, HOT, 0.6), 235 * Math.pow(1 - qd, 2));
    if (s.kind >= 1) {
      var rr = Bd * (0.5 + 1.7 * L.easeOut3(qd));
      pen.ring(x, y, rr, rr * (s.kind === 2 ? 0.75 : 1), 0, c, 190 * (1 - qd), 2.4 * ps * (1 - qd) + 0.2);
    }
    var nsp = Math.max(0, Math.round((4 + 5 * (s.kind === 2 ? 1 : 0)) * dens));
    for (j = 0; j < nsp; j++) {
      var rg = L.rngFor(inst.seed, s.i, 80 + j), life = 9 + 9 * rg();
      if (ad >= life) continue;
      var an2 = rg.uniform(0, Math.PI * 2), sp = rg.uniform(2.5, 6.5) * ps, fd = L.dragDist(0.87, ad);
      var sx = x + Math.cos(an2) * sp * fd, sy = y + Math.sin(an2) * sp * fd + 0.08 * ps * ad * ad;
      var dk = Math.pow(0.87, ad), qq = ad / life;
      pen.line(sx, sy, sx - Math.cos(an2) * sp * dk * 1.6, sy - Math.sin(an2) * sp * dk * 1.6, mix(HOT, c, qq), 255 * (1 - qq), 1.4 * ps);
    }
  }
}

function spikes(pen, x, y, ang, n, rOut, rIn, c, a) {
  var pts = [];
  for (var j = 0; j < 2 * n; j++) {
    var rr = j % 2 === 0 ? rOut : rIn, an = ang + Math.PI * j / n;
    pts.push([x + Math.cos(an) * rr, y + Math.sin(an) * rr]);
  }
  pen.poly(pts, c, a);
}
// The punch landing (sc = size; a whiff is smaller).
function impact(pen, inst, c, ps, x, y, a, sc, salt) {
  var L = L_(), HOT = L.HOT, mix = L.mix, q = a / PUNCH_IMPACT_LIFE, fx_ = inst.tq_f[0], fy_ = inst.tq_f[1];
  var ang = Math.atan2(fy_, fx_), j, e;
  if (a < 6) pen.glow(x, y, (18 + 24 * L.easeOut3(a / 6)) * ps * sc, HOT, 255 * (1 - a / 6));
  if (a < 10) {
    var qs = a / 10, rot = ang + 0.15 * a / 10;
    e = L.easeOut3(a / 4);
    spikes(pen, x, y, rot, 8, (16 + 28 * e) * ps * sc, (6 + 8 * e) * ps * sc, c, 225 * (1 - qs));
    spikes(pen, x, y, rot, 8, (9 + 16 * e) * ps * sc, (3.5 + 4 * e) * ps * sc, HOT, 255 * Math.pow(1 - qs, 1.5));
  }
  pen.glow(x, y, (26 + 20 * L.easeOut3(q)) * ps * sc, c, 140 * (1 - q), 0.4);
  // shockwave rings standing across the punch line
  [[0, 1], [3, 1.45]].forEach(function (dk) {
    var aa = a - dk[0], k = dk[1];
    if (aa < 0) return;
    var qq = aa / (PUNCH_IMPACT_LIFE - dk[0]), ee = L.easeOut3(qq);
    var cx = x + fx_ * 10 * ps * sc * ee * k, cy = y + fy_ * 10 * ps * sc * ee * k;
    pen.ring(cx, cy, (5 + 14 * ee) * ps * sc * k, (10 + 46 * ee) * ps * sc * k, ang, c, 210 * (1 - qq), 3 * ps * (1 - qq) + 0.2);
    pen.ring(cx, cy, (5 + 14 * ee) * ps * sc * k, (10 + 46 * ee) * ps * sc * k, ang, HOT, 160 * Math.pow(1 - qq, 2), 1 * ps * (1 - qq) + 0.1);
  });
  // radial speed lines
  if (a < 12) {
    var ql = a / 12;
    for (j = 0; j < 12; j++) {
      var r = L.rngFor(inst.seed, j, 70 + salt), an = r.uniform(0, Math.PI * 2);
      var r1 = (12 + 46 * L.easeOut3(ql)) * ps * sc * r.uniform(0.8, 1.2), ln = r.uniform(12, 26) * ps * sc * (1 - ql);
      var ca = Math.cos(an), sa = Math.sin(an);
      pen.line(x + ca * r1, y + sa * r1, x + ca * (r1 + ln), y + sa * (r1 + ln), mix(HOT, c, ql), 230 * (1 - ql), 1.4 * ps);
    }
  }
  // sparks thrown mostly forward
  var nsp = Math.max(0, Math.round(10 * (+inst.fx.params.density || 1) * sc));
  for (j = 0; j < nsp; j++) {
    var rg = L.rngFor(inst.seed, j, 90 + salt), life = 10 + 10 * rg();
    if (a >= life) continue;
    var an2 = ang + rg.uniform(-75, 75) * L.D, sp = rg.uniform(3, 8) * ps, fd = L.dragDist(0.87, a);
    var sx = x + Math.cos(an2) * sp * fd, sy = y + Math.sin(an2) * sp * fd + 0.1 * ps * a * a;
    var dk2 = Math.pow(0.87, a), q2 = a / life;
    pen.line(sx, sy, sx - Math.cos(an2) * sp * dk2 * 1.6, sy - Math.sin(an2) * sp * dk2 * 1.6, mix(HOT, c, q2), 255 * (1 - q2), 1.5 * ps);
  }
}
function drawPunch(pen, inst, host, ps) {
  var Lb = L_(), HOT = Lb.HOT, mix = Lb.mix, P = inst.fx.params, t = inst.age, fr = Lb.frame(inst);
  var cs = Lb.colours(inst, host), c = cs[0], bright = cs[1];
  var L = +P.length * ps, rf = +P.radius * ps, W = +P.thickness * ps, Ts = Lb.swing(P), Th = hold(P);
  var l = reach(P, t, L), out = t < Ts + Th + PUNCH_RETRACT, j, a;
  pen.add(true);
  if (out && l > 1) {
    var fade = t < Ts + Th ? 1 : 1 - (t - Ts - Th) / PUNCH_RETRACT;
    // 1: pressure streak from the shoulder to the fist
    var tail = Math.max(0, l - Math.max(L * 0.9, 3 * rf));
    pen.poly([fr.w(tail, -0.12 * W), fr.w(l, -W), fr.w(l + rf * 0.6, 0), fr.w(l, W), fr.w(tail, 0.12 * W)], c, 95 * fade);
    var t3 = tail + (l - tail) * 0.3;
    pen.poly([fr.w(t3, -0.06 * W), fr.w(l, -0.45 * W), fr.w(l + rf * 0.4, 0), fr.w(l, 0.45 * W), fr.w(t3, 0.06 * W)], bright, 170 * fade);
    // 2: speed lines alongside it while it drives out
    if (t <= Ts + 2) {
      var sf = t <= Ts ? 1 : 1 - (t - Ts) / 2;
      for (j = 0; j < 4; j++) {
        var r = Lb.rngFor(inst.seed, j, 51), off = (j % 2 ? 1 : -1) * W * r.uniform(1.1, 2);
        var x0 = l - r.uniform(0.5, 0.9) * L, x1 = l - r.uniform(0, 0.2) * L;
        var a0 = fr.w(Math.max(0, x0), off), a1 = fr.w(Math.max(0, x1), off);
        pen.line(a0[0], a0[1], a1[0], a1[1], mix(c, HOT, 0.4), 170 * sf, 1.2 * ps);
      }
    }
    // 3: afterimages of the fist
    [[2, 60], [1, 100]].forEach(function (ja) {
      var g = fr.w(reach(P, Math.max(0, t - ja[0]), L), 0);
      pen.glow(g[0], g[1], rf * 1.8, c, ja[1] * fade);
    });
    // 4: air ring compressing in front of the fist
    if (t <= Ts + 1) {
      var e = Lb.easeOut3(t / Ts), ar = fr.w(l + rf * (0.9 + 0.5 * e), 0);
      pen.ring(ar[0], ar[1], rf * 0.45, rf * (1 + 0.9 * e), Math.atan2(inst.tq_f[1], inst.tq_f[0]), HOT, 200 * (0.4 + 0.6 * e), 1.4 * ps);
    }
    // 5: the fist
    var f = fr.w(l, 0);
    pen.glow(f[0], f[1], rf * 2.6, c, 170 * fade);
    pen.glow(f[0], f[1], rf * 1.4, mix(c, HOT, 0.6), 235 * fade);
    pen.glow(f[0], f[1], rf * 0.7, HOT, 255 * fade, 0.7);
  }
  // 6: the impact — where the fist was when it landed; a whiff bursts at full reach
  if (inst.tq_imp.length) {
    inst.tq_imp.forEach(function (h, n) {
      var aa = t - h[0];
      if (aa >= 0 && aa < PUNCH_IMPACT_LIFE) impact(pen, inst, c, ps, h[1], h[2], aa, 1, 11 * n);
    });
  } else {
    a = t - Ts;
    if (a >= 0 && a < PUNCH_IMPACT_LIFE) { var w = fr.w(L + rf * 0.8, 0); impact(pen, inst, c, ps, w[0], w[1], a, 0.55, 0); }
  }
}

function draw(pen, inst, host, ps) {
  if (L_().style(inst.fx.params) === "ki_barrage") drawKi(pen, inst, host, ps);
  else drawPunch(pen, inst, host, ps);
}

G.STRIKEFX = {STYLES: STYLES, draw: draw, hit: hit, onHit: onHit, activeTicks: activeTicks, totalTicks: totalTicks};
})(window);
