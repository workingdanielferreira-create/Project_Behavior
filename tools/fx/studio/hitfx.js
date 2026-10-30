/* Strike FX partitions — FX Studio's port of laser/hitfx.py: what the punch
 * (strikefx.js) and the kicks (kickfx.js) paint, split into fx_motion (smear
 * frames, air strokes, the fist / foot), fx_impact (the hit) and fx_env
 * (push-off dust, ground waves, the axe crater, the rising kick-up, the
 * spinning vortex), each off / ink / energy / gritty.  Same random streams
 * (FXK.rng), same geometry and painting order as the game, so the Studio
 * preview draws what Solo and Battle draw.  Keep the two in step.  Builds on
 * swordfx.js (pen, maths): load it after swordfx.js, before strikefx.js.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };

var LOOKS = ["ink", "energy", "gritty"];
var PARTS = ["fx_motion", "fx_impact", "fx_env"];
var IMPACT_LIFE = 24, ENV_LIFE = 26, CRATER_LIFE = 40, FEET_DROP = 30;
var SMEAR_N = 3, SMEAR_STEP = 0.55, SMEAR_LEN = 3, ARC_N = 4, ARC_LINGER = 4;
var INK = [16, 10, 22], PAPER = [236, 238, 246], DUST = [150, 138, 120], GREY = [176, 174, 178];
var ROCK = [96, 84, 72], SCORCH = [40, 30, 28];

function look(P, part) {
  var v = P[part];
  if (v == null) v = "ink";
  return LOOKS.indexOf(v) >= 0 ? v : "off";
}

// ---------------------------------------------------------------- shapes
function unit(x, y) { var n = Math.hypot(x, y) || 1; return [x / n, y / n]; }
function circle(x, y, r, n) {
  n = n == null ? 14 : n;
  var out = [];
  for (var i = 0; i < n; i++) out.push([x + Math.cos(i * 2 * Math.PI / n) * r, y + Math.sin(i * 2 * Math.PI / n) * r]);
  return out;
}
function ellipse(x, y, rx, ry, ang, n) {
  n = n == null ? 20 : n;
  var ca = Math.cos(ang), sa = Math.sin(ang), out = [];
  for (var i = 0; i < n; i++) {
    var t = i * 2 * Math.PI / n, px = Math.cos(t) * rx, py = Math.sin(t) * ry;
    out.push([x + px * ca - py * sa, y + px * sa + py * ca]);
  }
  return out;
}
// A filled shape with an ink outline (normal blending).
function outlined(pen, pts, fill, a, line, la, w) {
  pen.poly(pts, fill, a);
  pen.polyline(pts.concat([pts[0]]), line, la, w);
}
// A stroke through pts as a polygon: zero width at both ends, w at the middle.
function taper(pts, w) {
  var n = pts.length;
  if (n < 2) return [];
  var left = [], right = [];
  for (var i = 0; i < n; i++) {
    var a = pts[Math.max(0, i - 1)], b = pts[Math.min(n - 1, i + 1)], t = unit(b[0] - a[0], b[1] - a[1]);
    var h = w * 0.5 * Math.sin(Math.PI * i / (n - 1));
    left.push([pts[i][0] - t[1] * h, pts[i][1] + t[0] * h]);
    right.push([pts[i][0] + t[1] * h, pts[i][1] - t[0] * h]);
  }
  return left.concat(right.reverse());
}
// A limb from (rx, ry) to (x, y): w0 half-width at the root, w1 at the tip, the tip rounded.
function capsule(rx, ry, x, y, w0, w1) {
  var u = unit(x - rx, y - ry), ux = u[0], uy = u[1], nx = -uy, ny = ux;
  var pts = [[rx + nx * w0, ry + ny * w0]];
  for (var k = 0; k < 7; k++) {
    var an = Math.PI * 0.5 - Math.PI * k / 6, ca = Math.cos(an), sa = Math.sin(an);
    pts.push([x + (nx * ca + ux * sa) * w1, y + (ny * ca + uy * sa) * w1]);
  }
  pts.push([rx - nx * w0, ry - ny * w0]);
  return pts;
}
// A jagged burst: n spikes of uneven length, longest along ang, a shorter kick back the other way.
function burst(inst, x, y, ang, n, rOut, rIn, salt) {
  var L = L_(), pts = [];
  for (var j = 0; j < 2 * n; j++) {
    var an = ang + Math.PI * j / n, rr = rIn;
    if (j % 2 === 0) {
      var r = L.rngFor(inst.seed, j, salt);
      an += r.uniform(-0.35, 0.35) * Math.PI / n;
      var k = Math.cos(an - ang);
      rr = rOut * (0.42 + 0.7 * Math.pow(Math.max(0, k), 2) + 0.3 * Math.pow(Math.max(0, -k), 2)) * r.uniform(0.7, 1.25);
    } else {
      rr = rIn * L.rngFor(inst.seed, j, salt + 1).uniform(0.8, 1.15);
    }
    pts.push([x + Math.cos(an) * rr, y + Math.sin(an) * rr]);
  }
  return pts;
}
// A triangular shard d out from (x, y) along an, pointing outward.
function shard(x, y, an, d, ln, wd) {
  var ca = Math.cos(an), sa = Math.sin(an), bx = x + ca * d, by = y + sa * d;
  return [[bx - sa * wd, by + ca * wd], [bx + ca * ln, by + sa * ln], [bx + sa * wd, by - ca * wd]];
}

// ================================================================ motion
// What the motion partition needs from a strike: limb(t) -> [root x, y, tip
// x, y, unit motion x, y] at tick t (fractional); t0 = the fast part starts,
// tc = contact, tm = the end of the move, tout = the limb gone; rf = fist /
// foot radius, W = the stroke spread (thickness).
function Motion(limb, t0, tc, tm, tout, rf, W) {
  this.limb = limb; this.t0 = t0; this.tc = tc; this.tm = tm; this.tout = tout; this.rf = rf; this.W = W;
}
function motion(pen, inst, P, t, ps, c, M) {
  var lk = look(P, "fx_motion");
  if (lk === "off") return;
  if (t < M.t0) { windup(pen, inst, lk, t, ps, c, M); return; }
  if ((P.motion_arcs === undefined ? true : P.motion_arcs) && t <= M.tm + ARC_LINGER) arcs(pen, inst, lk, t, ps, c, M);
  if ((P.motion_smear === undefined ? true : P.motion_smear) && t < M.tc) smear(pen, inst, lk, t, ps, c, M);
  if (t < M.tout) {
    var fade = t <= M.tm ? 1 : 1 - (t - M.tm) / Math.max(1, M.tout - M.tm);
    tip(pen, inst, lk, t, ps, c, M, fade);
  }
}
// A glint where the strike starts, drawing in.
function windup(pen, inst, lk, t, ps, c, M) {
  var L = L_(), p = M.limb(M.t0), x = p[2], y = p[3], e = (t + 1) / Math.max(1, M.t0), rf = M.rf;
  if (lk === "energy") {
    pen.add(true);
    pen.glow(x, y, rf * (0.8 + 1.2 * e), c, 120 + 100 * e);
    pen.ring(x, y, rf * (3 - 2 * e), rf * (3 - 2 * e), 0, L.HOT, 150 * e, 1.2 * ps);
  } else if (lk === "ink") {
    pen.add(false);
    var Ln = rf * (1.2 + 1.6 * e);
    [[1, 0, 1], [0, 1, 0.55]].forEach(function (d) {
      var dx = d[0], dy = d[1], k = d[2];
      pen.diamond(x - dx * Ln * k, y - dy * Ln * k, x + dx * Ln * k, y + dy * Ln * k, 2.6 * ps, INK, 230 * e);
      pen.diamond(x - dx * Ln * k * 0.9, y - dy * Ln * k * 0.9, x + dx * Ln * k * 0.9, y + dy * Ln * k * 0.9, 1.3 * ps, PAPER, 255 * e);
    });
  } else {
    pen.add(false);
    pen.glow(x, y, rf * (1 + 0.8 * e), GREY, 70 * e, 0.5);
  }
}
// Thin broken wind strokes along the limb's path, offset either side of it, each in two pieces.
function arcs(pen, inst, lk, t, ps, c, M) {
  var L = L_(), te = Math.min(t, M.tm), f = t <= M.tm ? 1 : 1 - (t - M.tm) / (ARC_LINGER + 1);
  pen.add(lk === "energy");
  var nn = ARC_N + (lk === "energy" ? 1 : 0);
  for (var j = 0; j < nn; j++) {
    var r = L.rngFor(inst.seed, j, 300);
    var off = r.uniform(-1, 1) * (M.rf * 0.6 + M.W * 0.4), lag = r.uniform(0, 0.5), span = r.uniform(2, 3.4);
    var gap = r.uniform(0.38, 0.55), wmax = r.uniform(1.4, 2.6) * ps;
    var s1 = te - lag, s0 = Math.max(M.t0, s1 - span);
    if (s1 - s0 < 0.3) continue;
    [[0, gap - 0.06], [gap + 0.06, 1]].forEach(function (uu) {
      var pts = [];
      for (var k = 0; k < 9; k++) {
        var s = s0 + (s1 - s0) * (uu[0] + (uu[1] - uu[0]) * k / 8), q = M.limb(s);
        pts.push([q[2] - q[5] * off, q[3] + q[4] * off]);
      }
      if (lk === "ink") {
        pen.poly(taper(pts, wmax + 2.2 * ps), INK, 200 * f);
        pen.poly(taper(pts, wmax), PAPER, 245 * f);
      } else if (lk === "energy") {
        pen.poly(taper(pts, wmax * 1.6), c, 150 * f);
        pen.poly(taper(pts, wmax * 0.6), L.HOT, 200 * f);
      } else {
        pen.poly(taper(pts, wmax * 0.8), GREY, 120 * f);
      }
    });
    if (lk === "gritty") {
      // dust flecks shed along the stroke
      for (var k2 = 0; k2 < 3; k2++) {
        var qq = r(), s = s0 + (s1 - s0) * qq, p = M.limb(s), age = t - s;
        var x = p[2], y = p[3], ux = p[4], uy = p[5];
        pen.glow(x - uy * off * 1.4 - ux * age * 1.5 * ps, y + ux * off * 1.4 - uy * age * 1.5 * ps, (2.5 + 2 * qq) * ps, DUST, 110 * f, 0.6);
      }
    }
  }
}
// Smear frames: afterimages of the limb along its path, oldest first.
function smear(pen, inst, lk, t, ps, c, M) {
  var L = L_();
  pen.add(lk === "energy");
  for (var k = SMEAR_N; k > 0; k--) {
    var s = t - SMEAR_STEP * k;
    if (s < M.t0) continue;
    var p = M.limb(s), rx = p[0], ry = p[1], x = p[2], y = p[3], ln = Math.hypot(x - rx, y - ry);
    if (ln < 2) continue;
    // only the end of the limb (forearm / shin): a run of stepped copies rather than one long shape
    var k_ = Math.min(1, SMEAR_LEN * M.rf / ln);
    rx = x + (rx - x) * k_; ry = y + (ry - y) * k_;
    var q = 1 - (k - 1) / SMEAR_N, cap = capsule(rx, ry, x, y, M.rf * 0.45, M.rf * (0.75 + 0.2 * q));
    if (lk === "ink") outlined(pen, cap, PAPER, 150 * q, INK, 170 * q, 1.2 * ps);
    else if (lk === "energy") {
      pen.poly(cap, c, 95 * q);
      pen.poly(capsule(rx, ry, x, y, M.rf * 0.2, M.rf * 0.45), L.HOT, 90 * q);
    } else pen.poly(cap, GREY, 70 * q);
  }
}
// The fist / foot (not while it is still at the shoulder / hip).
function tip(pen, inst, lk, t, ps, c, M, fade) {
  var L = L_(), p = M.limb(t), rx = p[0], ry = p[1], x = p[2], y = p[3], ux = p[4], uy = p[5], rf = M.rf;
  if (Math.hypot(x - rx, y - ry) <= 1) return;
  if (lk === "energy") {
    pen.add(true);
    [[2, 60], [1, 100]].forEach(function (ja) {
      var g = M.limb(Math.max(M.t0, t - ja[0]));
      pen.glow(g[2], g[3], rf * 1.8, c, ja[1] * fade);
    });
    pen.glow(x, y, rf * 2.6, c, 170 * fade);
    pen.glow(x, y, rf * 1.4, L.mix(c, L.HOT, 0.6), 235 * fade);
    pen.glow(x, y, rf * 0.7, L.HOT, 255 * fade, 0.7);
  } else if (lk === "ink") {
    pen.add(false);
    outlined(pen, ellipse(x, y, rf * 1.25, rf * 0.9, Math.atan2(uy, ux), 16), PAPER, 240 * fade, INK, 235 * fade, 1.6 * ps);
    pen.poly(ellipse(x - ux * rf * 0.25, y - uy * rf * 0.25, rf * 0.55, rf * 0.4, Math.atan2(uy, ux), 12), c, 200 * fade);
  } else {
    pen.add(false);
    pen.glow(x, y, rf * 1.5, [232, 230, 226], 130 * fade, 0.55);
  }
}

// ================================================================ impact
// The impact a ticks after contact at (x, y), laid along u (sc = size).
function impact(pen, inst, P, c, ps, x, y, a, sc, salt, u) {
  if (!(a >= 0 && a < IMPACT_LIFE)) return;
  var lk = look(P, "fx_impact");
  if (lk === "ink") impInk(pen, inst, P, c, ps, x, y, a, sc, salt, u);
  else if (lk === "energy") impEnergy(pen, inst, P, c, ps, x, y, a, sc, salt, u);
  else if (lk === "gritty") impGritty(pen, inst, P, c, ps, x, y, a, sc, salt, u);
}
// Anime impact, on twos: a white jagged burst with an ink outline and a
// coloured heart, then it breaks into shards flying out mostly forward; ink
// focus lines round it, a pressure disc standing across the blow.
function impInk(pen, inst, P, c, ps, x, y, a, sc, salt, u) {
  var L = L_(), ang = Math.atan2(u[1], u[0]), k2 = a - a % 2, sk = salt + 7 * k2, j, r, q, e, f;
  pen.add(false);
  // focus lines: ink wedges pointing at the contact point
  if (a < 6) {
    f = 1 - a / 6;
    for (j = 0; j < 18; j++) {
      r = L.rngFor(inst.seed, j, 400 + sk);
      var an = (j + r.uniform(-0.35, 0.35)) * Math.PI * 2 / 18;
      var r0 = (24 + 12 * r()) * ps * sc + 4 * ps * k2, r1 = r0 + r.uniform(36, 70) * ps * sc, hw = r.uniform(0.012, 0.028);
      pen.poly([[x + Math.cos(an - hw) * r1, y + Math.sin(an - hw) * r1], [x + Math.cos(an + hw) * r1, y + Math.sin(an + hw) * r1],
                [x + Math.cos(an) * r0, y + Math.sin(an) * r0]], j % 2 ? INK : PAPER, 230 * f);
    }
  }
  // the burst
  if (a < 6) {
    e = k2 > 0 ? 1 : 0.75;
    var R = (30 + 8 * (k2 / 2)) * ps * sc * e;
    outlined(pen, burst(inst, x, y, ang, 9, R, R * 0.42, 420 + sk), PAPER, 255, INK, 255, 2.4 * ps);
    pen.poly(burst(inst, x, y, ang, 9, R * 0.55, R * 0.24, 440 + sk), c, 235);
    pen.poly(circle(x, y, R * 0.16, 10), L.HOT, 255);
  }
  // shards: the burst broken apart, flying out mostly forward
  if (a >= 2 && a < 14) {
    q = (a - 2) / 12; e = L.easeOut3(q);
    for (j = 0; j < 8; j++) {
      r = L.rngFor(inst.seed, j, 460 + salt);
      var an2 = ang + (j < 6 ? r.uniform(-100, 100) : 180 + r.uniform(-40, 40)) * L.D;
      var d = (16 + r.uniform(30, 60) * e) * ps * sc, ln = r.uniform(10, 18) * ps * sc * (1 - q), wd = r.uniform(3, 5) * ps * sc * (1 - q * 0.6);
      outlined(pen, shard(x, y, an2 + r.uniform(-0.15, 0.15) * (k2 % 4), d, ln, wd), PAPER, 255 * (1 - q), INK, 255 * (1 - q), 1.6 * ps);
    }
  }
  // pressure disc across the blow, pushed forward
  if (a >= 1 && a < 12) {
    q = (a - 1) / 11; e = L.easeOut3(q);
    var cx = x + u[0] * 14 * ps * sc * e, cy = y + u[1] * 14 * ps * sc * e, rx = (5 + 9 * e) * ps * sc, ry = (14 + 42 * e) * ps * sc;
    pen.ring(cx, cy, rx, ry, ang, INK, 230 * (1 - q), 4.4 * ps * (1 - q) + 0.6);
    pen.ring(cx, cy, rx, ry, ang, PAPER, 255 * (1 - q), 2.2 * ps * (1 - q) + 0.3);
  }
  // after the burst: a lingering ink star glint, blinking out on twos
  if (a >= 6 && a < 16 && Math.floor(k2 / 2) % 2 === 1) {
    f = 1 - (a - 6) / 10;
    var Ls = 12 * ps * sc;
    [[u[0], u[1]], [-u[1], u[0]]].forEach(function (dd) {
      var dx = dd[0], dy = dd[1];
      pen.diamond(x - dx * Ls, y - dy * Ls, x + dx * Ls, y + dy * Ls, 2.4 * ps, INK, 230 * f);
      pen.diamond(x - dx * Ls * 0.88, y - dy * Ls * 0.88, x + dx * Ls * 0.88, y + dy * Ls * 0.88, 1.1 * ps, PAPER, 255 * f);
    });
  }
}
// Light: a white-hot core, a coloured pressure burst, rays spilling forward
// through the target, air-friction sparks, a clean shock ring.
function impEnergy(pen, inst, P, c, ps, x, y, a, sc, salt, u) {
  var L = L_(), HOT = L.HOT, ang = Math.atan2(u[1], u[0]), q = a / IMPACT_LIFE, e, k, j, r, f;
  pen.add(true);
  if (a < 6) pen.glow(x, y, (18 + 24 * L.easeOut3(a / 6)) * ps * sc, HOT, 255 * (1 - a / 6));
  // the pressure burst: glows pushed forward along the blow
  if (a < 10) {
    e = L.easeOut3(a / 10);
    for (k = 0; k < 3; k++) {
      var d = (6 + 16 * k) * ps * sc * e;
      pen.glow(x + u[0] * d, y + u[1] * d, (22 - 5 * k) * ps * sc * (0.6 + 0.6 * e), c, (190 - 50 * k) * (1 - a / 10));
    }
  }
  pen.glow(x, y, (26 + 20 * L.easeOut3(q)) * ps * sc, c, 120 * (1 - q), 0.4);
  // rays spilling forward
  if (a < 9) {
    f = 1 - a / 9; e = L.easeOut3(a / 4);
    for (j = 0; j < 9; j++) {
      r = L.rngFor(inst.seed, j, 500 + salt);
      var an = ang + r.uniform(-38, 38) * L.D, ln = r.uniform(40, 110) * ps * sc * e, w = r.uniform(3, 6) * ps * sc, d0 = 6 * ps * sc, pts = [];
      for (k = 0; k < 7; k++) pts.push([x + Math.cos(an) * (d0 + ln * k / 6), y + Math.sin(an) * (d0 + ln * k / 6)]);
      pen.poly(taper(pts, w * f), c, 170 * f);
      pen.poly(taper(pts, w * 0.35 * f), HOT, 230 * f);
    }
  }
  // small impact star
  if (a < 7) {
    var qs = a / 7;
    e = L.easeOut3(a / 3);
    pen.poly(burst(inst, x, y, ang, 8, (14 + 22 * e) * ps * sc, (5 + 6 * e) * ps * sc, 520 + salt), c, 210 * (1 - qs));
    pen.poly(burst(inst, x, y, ang, 8, (8 + 12 * e) * ps * sc, (3 + 3 * e) * ps * sc, 520 + salt), HOT, 255 * Math.pow(1 - qs, 1.5));
  }
  // shock ring across the blow, squashed along it, and a broken one further out
  [[0, 0, 1], [1, 4, 1.6]].forEach(function (ring) {
    var n = ring[0], dd0 = ring[1], kk = ring[2], aa = a - dd0;
    if (aa < 0) return;
    var qq = aa / (IMPACT_LIFE - dd0), ee = L.easeOut3(qq);
    var cx = x + u[0] * 10 * ps * sc * ee * kk, cy = y + u[1] * 10 * ps * sc * ee * kk;
    var rx = (4 + 10 * ee) * ps * sc * kk, ry = (10 + 46 * ee) * ps * sc * kk;
    if (n === 0) {
      pen.ring(cx, cy, rx, ry, ang, c, 210 * (1 - qq), 3 * ps * (1 - qq) + 0.2);
      pen.ring(cx, cy, rx, ry, ang, HOT, 160 * Math.pow(1 - qq, 2), 1 * ps * (1 - qq) + 0.1);
    } else arcRing(pen, inst, cx, cy, rx, ry, ang, c, 190 * (1 - qq), 2.2 * ps * (1 - qq) + 0.2, 540 + salt);
  });
  // air-friction sparks thrown mostly forward
  var nSp = Math.max(0, Math.round(14 * (+P.density || 1) * sc));
  for (j = 0; j < nSp; j++) {
    r = L.rngFor(inst.seed, j, 560 + salt);
    var life = 10 + 10 * r();
    if (a >= life) continue;
    var an2 = ang + r.uniform(-65, 65) * L.D, sp = r.uniform(3, 9) * ps, fd = L.dragDist(0.87, a);
    var sx = x + Math.cos(an2) * sp * fd, sy = y + Math.sin(an2) * sp * fd + 0.1 * ps * a * a, dk = Math.pow(0.87, a), q2 = a / life;
    pen.line(sx, sy, sx - Math.cos(an2) * sp * dk * 1.6, sy - Math.sin(an2) * sp * dk * 1.6, L.mix(HOT, c, q2), 255 * (1 - q2), 1.5 * ps);
  }
}
// A ring broken into 3-5 arcs with gaps (rx along ang).
function arcRing(pen, inst, x, y, rx, ry, ang, c, a, w, salt) {
  if (a <= 1 || w <= 0.05 || rx <= 0.5 || ry <= 0.5) return;
  var r = L_().rngFor(inst.seed, 0, salt), n = 3 + Math.trunc(r() * 3), t0 = r() * Math.PI * 2;
  var ca = Math.cos(ang), sa = Math.sin(ang), st = Math.PI * 2 / n;
  for (var i = 0; i < n; i++) {
    var s0 = t0 + i * st, s1 = s0 + st * r.uniform(0.55, 0.85), pts = [];
    for (var k = 0; k < 9; k++) {
      var t = s0 + (s1 - s0) * k / 8, px = Math.cos(t) * rx, py = Math.sin(t) * ry;
      pts.push([x + px * ca - py * sa, y + px * sa + py * ca]);
    }
    pen.polyline(pts, c, a, w);
  }
}
// Physical: a brief flash, a distortion ring (light and dark side by side,
// like refraction), a dust burst off the body, debris and sweat spray flying
// on with the blow.
function impGritty(pen, inst, P, c, ps, x, y, a, sc, salt, u) {
  var L = L_(), ang = Math.atan2(u[1], u[0]), j, r, life, q;
  pen.add(false);
  // dust burst off the body, pushed along the blow
  for (j = 0; j < 7; j++) {
    r = L.rngFor(inst.seed, j, 600 + salt);
    life = 16 + 10 * r();
    if (a >= life) continue;
    q = a / life;
    var an = ang + r.uniform(-70, 70) * L.D, d = r.uniform(1, 2.4) * ps * L.dragDist(0.85, a) * sc;
    var rad = (7 + 17 * L.easeOut3(q)) * ps * sc * r.uniform(0.7, 1.3);
    pen.glow(x + Math.cos(an) * d, y + Math.sin(an) * d, rad, DUST, 185 * (1 - q), 0.6);
  }
  // distortion rings
  [[0, 1], [3, 1.5]].forEach(function (dk) {
    var aa = a - dk[0], k = dk[1];
    if (aa < 0 || aa >= 12) return;
    var qq = aa / 12, e = L.easeOut3(qq);
    var cx = x + u[0] * 8 * ps * sc * e * k, cy = y + u[1] * 8 * ps * sc * e * k, rx = (5 + 10 * e) * ps * sc * k, ry = (12 + 40 * e) * ps * sc * k;
    pen.ring(cx, cy, rx, ry, ang, INK, 110 * (1 - qq), 3 * ps * (1 - qq) + 0.3);
    pen.ring(cx, cy, rx + 2.5 * ps, ry + 2.5 * ps, ang, [225, 228, 235], 120 * (1 - qq), 1.6 * ps * (1 - qq) + 0.2);
  });
  // debris chips and sweat spray, with gravity
  var n = Math.max(0, Math.round(12 * (+P.density || 1) * sc));
  for (j = 0; j < n; j++) {
    r = L.rngFor(inst.seed, j, 620 + salt);
    life = 14 + 10 * r();
    if (a >= life) continue;
    q = a / life;
    var an2 = ang + r.uniform(-55, 55) * L.D, sp = r.uniform(2.5, 7) * ps, fd = L.dragDist(0.9, a);
    var px = x + Math.cos(an2) * sp * fd, py = y + Math.sin(an2) * sp * fd + 0.16 * ps * a * a;
    if (j % 3 === 0) {
      var sz = r.uniform(2.2, 3.8) * ps;
      pen.poly([[px - sz, py], [px, py - sz * 0.8], [px + sz, py], [px, py + sz * 0.7]], ROCK, 245 * (1 - q));
    } else pen.glow(px, py, r.uniform(2, 3.4) * ps, [225, 230, 238], 240 * (1 - q), 0.7);
  }
  // the flash, brief
  if (a < 3) {
    pen.add(true);
    pen.glow(x, y, (18 + 10 * a) * ps * sc, L.HOT, 230 * (1 - a / 3));
    pen.add(false);
  }
  // a few short dark impact lines
  if (a < 8) {
    var f = 1 - a / 8;
    for (j = 0; j < 6; j++) {
      r = L.rngFor(inst.seed, j, 640 + salt);
      var an3 = ang + r.uniform(-80, 80) * L.D, r0 = (14 + 20 * L.easeOut3(a / 8)) * ps * sc, ln = r.uniform(8, 16) * ps * sc;
      pen.line(x + Math.cos(an3) * r0, y + Math.sin(an3) * r0, x + Math.cos(an3) * (r0 + ln), y + Math.sin(an3) * (r0 + ln), INK, 170 * f, 1.4 * ps);
    }
  }
}

// ================================================================ environment
// An event: [kind, age, x, y, ux, uy, size, salt].  push = dust under the
// attacker as the strike starts (u = the way it is thrown); ground = a wave
// along the ground under the impact; crater = the axe kick's crater; kickup =
// dust thrown up as the rising kick starts; vortex = wind round the body
// (x, y = centre, ux = radius, uy = turn sign, size = fade, age = tick).
function env(pen, inst, P, c, ps, ev) {
  var lk = look(P, "fx_env");
  if (lk === "off") return;
  if (ev[0] === "vortex") vortex(pen, inst, lk, c, ps, ev);
  else if (ev[0] === "crater") crater(pen, inst, P, lk, c, ps, ev);
  else ground(pen, inst, P, lk, c, ps, ev);
}
// n dust puffs born at (x, y), drifting along the ground (dirx: the way; 0 =
// both ways), rising and shrinking away.  ink: one cloud — every puff's ink
// rim first, then the paper over them, so only the outside edge shows.
function puffs(pen, inst, lk, ps, x, y, a, life, n, spreadX, rise, size, salt, dirx, c) {
  var L = L_(), live = [], j;
  for (j = 0; j < n; j++) {
    var r = L.rngFor(inst.seed, j, salt), lf = life * r.uniform(0.7, 1);
    if (a >= lf) continue;
    var q = a / lf, e = L.easeOut3(q), sd = dirx ? dirx : (j % 2 === 0 ? 1 : -1);
    var px = x + sd * spreadX * e * r.uniform(0.4, 1) * (lk === "ink" ? 0.55 : 1);
    var py = y - rise * e * r.uniform(0.3, 1), rad = size * (0.6 + 0.9 * e) * r.uniform(0.7, 1.3);
    live.push([px, py, rad, q]);
  }
  if (lk === "ink") {
    live.forEach(function (p) { var rr = p[2] * (1 - p[3]); if (rr > 0.8) pen.poly(circle(p[0], p[1], rr + 1.6 * ps, 14), INK, 235); });
    live.forEach(function (p) {
      var rr = p[2] * (1 - p[3]);
      if (rr > 0.8) {
        pen.poly(circle(p[0], p[1], rr, 14), PAPER, 245);
        pen.poly(circle(p[0] + rr * 0.25, p[1] + rr * 0.3, rr * 0.55, 10), [196, 200, 214], 200);
      }
    });
  } else if (lk === "energy") live.forEach(function (p) { pen.glow(p[0], p[1], p[2] * 0.8, c, 150 * (1 - p[3]), 0.5); });
  else live.forEach(function (p) { pen.glow(p[0], p[1], p[2] * 1.4, DUST, 150 * (1 - p[3]), 0.6); });
}
function ground(pen, inst, P, lk, c, ps, ev) {
  var L = L_(), kind = ev[0], a = ev[1], x = ev[2], y = ev[3], ux = ev[4], sc = ev[6], salt = ev[7], q, e;
  if (kind === "push") {
    if (a < 0 || a >= 16) return;
    pen.add(lk === "energy");
    if (lk === "energy") {
      q = a / 16; e = L.easeOut3(q);
      pen.ring(x, y, (6 + 26 * e) * ps * sc, (2 + 6 * e) * ps * sc, 0, c, 180 * (1 - q), 2 * ps * (1 - q) + 0.2);
    }
    puffs(pen, inst, lk, ps, x, y, a, 16, 4, 26 * ps * sc, 8 * ps * sc, 6 * ps * sc, 700 + salt, ux ? ux : 0, c);
    return;
  }
  if (kind === "kickup") {
    if (a < 0 || a >= 18) return;
    pen.add(lk === "energy");
    var nk = Math.max(1, Math.round(5 * (+P.density || 1)));
    puffs(pen, inst, lk, ps, x, y, a, 18, nk, 12 * ps, 26 * ps, 7 * ps, 720 + salt, 0, c);
    return;
  }
  // ground: the wave along the ground under an impact
  if (a < 0 || a >= ENV_LIFE) return;
  q = a / ENV_LIFE; e = L.easeOut3(q);
  var R = (14 + 56 * e) * ps * sc;
  if (lk === "energy") {
    pen.add(true);
    pen.ring(x, y, R, R * 0.2, 0, c, 200 * (1 - q), 2.6 * ps * (1 - q) + 0.2);
    pen.glow(x, y, R * 0.7, c, 90 * (1 - q), 0.4);
    for (var j = 0; j < 6; j++) {
      var r = L.rngFor(inst.seed, j, 740 + salt), sd = j % 2 === 0 ? 1 : -1, px = x + sd * R * r.uniform(0.5, 1);
      pen.line(px, y, px + sd * 8 * ps, y - r.uniform(2, 10) * ps * (1 - q), L.mix(c, L.HOT, 0.5), 220 * (1 - q), 1.3 * ps);
    }
    return;
  }
  pen.add(false);
  if (lk === "ink") {
    pen.ring(x, y, R, R * 0.2, 0, INK, 220 * (1 - q), 3.6 * ps * (1 - q) + 0.4);
    pen.ring(x, y, R, R * 0.2, 0, PAPER, 240 * (1 - q), 1.6 * ps * (1 - q) + 0.2);
  }
  puffs(pen, inst, lk, ps, x, y, a, ENV_LIFE, 6, R * 1.1, 10 * ps * sc, 7 * ps * sc, 760 + salt, 0, c);
}
// Axe kick: a crater, cracks running along the ground, debris thrown up and a ground wave (laid flat).
function crater(pen, inst, P, lk, c, ps, ev) {
  var L = L_(), a = ev[1], x = ev[2], y = ev[3], sc = ev[6], salt = ev[7], j, r;
  if (a < 0 || a >= CRATER_LIFE) return;
  var q = a / CRATER_LIFE, e = L.easeOut3(Math.min(1, a / 8)), R = (22 + 26 * e) * ps * sc;
  var ink = lk === "ink", energy = lk === "energy";
  pen.add(false);
  if (ink) outlined(pen, ellipse(x, y, R, R * 0.32, 0), INK, 200 * (1 - q), PAPER, 220 * (1 - q), 1.4 * ps);
  else if (energy) pen.poly(ellipse(x, y, R, R * 0.32, 0), SCORCH, 120 * (1 - q));
  else {
    pen.poly(ellipse(x, y, R, R * 0.32, 0), SCORCH, 140 * (1 - q));
    pen.ring(x, y, R, R * 0.32, 0, DUST, 200 * (1 - q), 2 * ps);
  }
  // cracks
  pen.add(energy);
  for (j = 0; j < 7; j++) {
    r = L.rngFor(inst.seed, j, 780 + salt);
    var side = j % 2 === 0 ? 0 : Math.PI, an = side + r.uniform(-0.35, 0.35), ln = (20 + 60 * e) * ps * sc * r.uniform(0.6, 1.2), pts = [[x, y]];
    for (var k = 1; k < 5; k++) {
      var d = ln * k / 4, jit = r.uniform(-0.5, 0.5) * 6 * ps;
      pts.push([x + Math.cos(an) * d, y + Math.sin(an) * d * 0.4 + jit]);
    }
    if (energy) {
      pen.polyline(pts, c, 220 * (1 - q), 2.6 * ps);
      pen.polyline(pts, L.HOT, 200 * Math.pow(1 - q, 2), 1 * ps);
    } else if (ink) pen.polyline(pts, INK, 240 * (1 - q), 2.4 * ps);
    else pen.polyline(pts, [24, 18, 16], 200 * (1 - q), 1.6 * ps);
  }
  // debris thrown up
  pen.add(false);
  var n = Math.max(0, Math.round(8 * (+P.density || 1)));
  for (j = 0; j < n; j++) {
    r = L.rngFor(inst.seed, j, 800 + salt);
    var vx = r.uniform(-3, 3) * ps, vy = -r.uniform(3, 7) * ps, rx = x + vx * a, ry = y + vy * a + 0.225 * ps * a * a;
    if (ry > y + 4 * ps) continue;
    var sz = r.uniform(2, 4) * ps, rock = [[rx - sz, ry], [rx, ry - sz], [rx + sz, ry], [rx, ry + sz * 0.7]];
    if (ink) outlined(pen, rock, PAPER, 240, INK, 240, 1.3 * ps);
    else if (energy) {
      pen.add(true);
      pen.glow(rx, ry, sz * 1.6, c, 200 * (1 - q), 0.5);
      pen.add(false);
      pen.poly(rock, ROCK, 220 * (1 - q));
    } else pen.poly(rock, ROCK, 230 * (1 - q));
  }
  // the ground wave and dust
  ground(pen, inst, P, lk, c, ps, ["ground", a, x, y, 0, 0, sc * 1.2, salt + 1]);
}
// Three arcs of an ellipse, turned by rot.
function swirl(pen, x, y, rx, ry, rot, c, a, w, ink) {
  for (var i = 0; i < 3; i++) {
    var s0 = rot + i * 2 * Math.PI / 3, pts = [];
    for (var k = 0; k < 9; k++) pts.push([x + Math.cos(s0 + 1.2 * k / 8) * rx, y + Math.sin(s0 + 1.2 * k / 8) * ry]);
    if (ink) {
      pen.poly(taper(pts, w + 2.2), INK, a * 0.85);
      pen.poly(taper(pts, w), PAPER, a);
    } else pen.poly(taper(pts, w), c, a);
  }
}
// Spinning kick: wind round the body, turning with the kick.
function vortex(pen, inst, lk, c, ps, ev) {
  var L = L_(), t = ev[1], ox = ev[2], oy = ev[3], Ln = ev[4], s = ev[5], fade = ev[6], ink = lk === "ink";
  pen.add(lk === "energy");
  var col = lk === "energy" ? L.mix(c, L.HOT, 0.3) : DUST;
  for (var j = 0; j < 3; j++) {
    var rx = Ln * (0.8 + 0.25 * j);
    swirl(pen, ox, oy + Ln * 0.15 * (j - 1), rx, rx * 0.32, s * (t * 0.55 + j * 1.3), col, (190 - 40 * j) * fade, (3.2 - 0.7 * j) * ps, ink);
  }
}

// ================================================================ hit weight
// Screen shake (params shake / shake_px / shake_ticks), with the strike's
// hit-stop (strikefx.js freeze): once per strike.
function shake(inst, host) {
  var P = inst.fx.params;
  if (!P.shake || !host || typeof host.shake !== "function") return;
  var n = Math.max(0, Math.trunc(+P.shake_ticks || 0)), px = Math.max(0, +P.shake_px || 0);
  if (n > 0 && px > 0) host.shake(px, n);
}
// [ticks, amount, flash] of a strike's target squash, or null.
function squashOf(P) {
  if (!P.squash) return null;
  var n = Math.max(0, Math.trunc(+P.squash_ticks || 0)), amt = Math.min(0.8, Math.max(0, +P.squash_amt || 0));
  if (n <= 0 || (amt <= 0 && !P.squash_flash)) return null;
  return [n, amt, !!P.squash_flash];
}

G.HITFX = {LOOKS: LOOKS, PARTS: PARTS, IMPACT_LIFE: IMPACT_LIFE, FEET_DROP: FEET_DROP, INK: INK, Motion: Motion, look: look,
           motion: motion, impact: impact, env: env, shake: shake, squashOf: squashOf};
})(window);
