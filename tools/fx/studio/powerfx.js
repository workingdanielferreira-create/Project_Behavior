/* Power techniques — FX Studio's port of laser/powerfx.py: the Super Saiyan
 * aura, rasen-shuriken, gigantic meteor, ghost kamikaze, serious punch and
 * black hole styles of the FX Kit "technique" primitive.  Same timeline,
 * same random streams (FXK.rng), same geometry and painting order as the
 * game, so the Studio preview draws what Solo and Battle draw.  Keep the two
 * in step.  (The meteor / black hole pull moves the opposing fighter in
 * Battle only: laser/powerfx.py pulls.)
 * Builds on swordfx.js (frame, pen, maths): load it after that file.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };
var STYLES = ["ssj_aura", "rasen_shuriken", "gigantic_meteor", "ghost_kamikaze", "serious_punch", "black_hole"];
var PULL_STYLES = ["gigantic_meteor", "black_hole"];

var AURA_FADE = 30, AURA_N = 28, AURA_LICK_LIFE = 16, AURA_RATE = 5, AURA_RISE = 1.6, AURA_LAG = 0.9, AURA_STRETCH = 2.2;
var AURA_FULL = 3.0, AURA_SWING = 0.72, AURA_SWING_N = 12, AURA_DRIFT = 0.6, AURA_FRAG_LIFE = 14, AURA_FRAG_P = 0.7;
var AURA_SURGE_SLOT = 90, AURA_SURGE_LEN = 20, AURA_CRACKS = 7, AURA_ROCK_EVERY = 3, AURA_ROCK_LIFE = 70;
var AURA_SLOT = 4, AURA_BOLT_LIFE = 6;
var AURA_BOLT_FLICKER = [1.0, 0.35, 1.0, 0.7, 0.3, 0.15];
var BOLT = [150, 205, 255], ROCK = [78, 66, 54], CRACK = [26, 20, 18];
var RS_SPEED = 8.0, RS_SPIN = [0.04, 0.55], RS_GROW = 9, RS_SHRINK = 12, RS_FADE = 18;
var MET_FALL = 30, MET_LOB = 0.22, MET_GROW_DRAG = 0.12, MET_BLAST_HIT = 8, MET_BLAST_LIFE = 44;
var DUST = [110, 98, 84];
var GH_FLOAT = 16, GH_OUT = 3.2, GH_DRAG = 0.86, GH_SPEED = 6.5, GH_ACCEL = 0.35, GH_TURN = 0.16, GH_FAN = 55.0, GH_ARRIVE = 1.2;
var GH_BLAST_LIFE = 30;
var GH_BODY = [236, 240, 255];
var SMOKE = [92, 86, 80];
var SP_OUT = 2, SP_FLASH = 8, SP_RINGS = 5, SP_SPLIT_LIFE = 46;
var CLOUD = [214, 220, 232];
var BH_COLLAPSE = 12, BH_BURST_HIT = 6, BH_BURST_LIFE = 34, BH_TILT = -0.32, BH_SQ = 0.3, BH_CLUMPS = 9;
var PI = Math.PI;

// ---------------------------------------------------------------- helpers
function ti(P, k, lo) { return Math.max(lo || 0, Math.trunc(+P[k] || 0)); }
function at(lst, k) { return lst[Math.max(0, Math.min(k, lst.length - 1))]; }
function hyp(x, y) { return Math.sqrt(x * x + y * y); }
function cl(u) { return u < 0 ? 0 : u > 1 ? 1 : u; }
function frac(x) { return x - Math.floor(x); }
function smooth(u) { u = cl(u); return u * u * (3 - 2 * u); }
function rev(a) { return a.slice().reverse(); }
function arc(pen, x, y, rx, ry, tilt, a0, a1, c, a, w, n) {   // part of a tilted ellipse
  if (a <= 1 || w <= 0.05 || rx <= 0.5) return;
  n = n || 24;
  var ca = Math.cos(tilt), sa = Math.sin(tilt), pts = [];
  for (var i = 0; i <= n; i++) {
    var t = a0 + (a1 - a0) * i / n, px = Math.cos(t) * rx, py = Math.sin(t) * ry;
    pts.push([x + px * ca - py * sa, y + px * sa + py * ca]);
  }
  pen.polyline(pts, c, a, w);
}
function circle(cx, cy, r, n) {
  n = n || 20;
  var out = [];
  for (var i = 0; i < n; i++) out.push([cx + Math.cos(i * PI * 2 / n) * r, cy + Math.sin(i * PI * 2 / n) * r]);
  return out;
}
function ellipse(cx, cy, rx, ry, n) {
  n = n || 12;
  var out = [];
  for (var i = 0; i < n; i++) out.push([cx + Math.cos(i * PI * 2 / n) * rx, cy + Math.sin(i * PI * 2 / n) * ry]);
  return out;
}
function lin(a, b, n) { var out = []; for (var j = 0; j < n; j++) out.push(a + (b - a) * j / (n - 1)); return out; }
// Sparks thrown from (x, y), a ticks ago.
function sparks(pen, inst, x, y, a, n, salt, c, ps, sp, life, grav, ang0, spread) {
  var L = L_();
  sp = sp || [3, 8]; life = life || [10, 20]; grav = grav == null ? 0.08 : grav; ang0 = ang0 || 0; spread = spread == null ? PI : spread;
  for (var j = 0; j < n; j++) {
    var r = L.rngFor(inst.seed, j, salt), lf = life[0] + (life[1] - life[0]) * r();
    if (a >= lf) continue;
    var an = ang0 + r.uniform(-spread, spread), v = r.uniform(sp[0], sp[1]) * ps, fd = L.dragDist(0.87, a);
    var sx = x + Math.cos(an) * v * fd, sy = y + Math.sin(an) * v * fd + grav * ps * a * a, dk = Math.pow(0.87, a), q = a / lf;
    pen.line(sx, sy, sx - Math.cos(an) * v * dk * 1.6, sy - Math.sin(an) * v * dk * 1.6, L.mix(L.HOT, c, q), 255 * (1 - q), 1.4 * ps);
  }
}
function bolt(r, x0, y0, ang, len, n, jit) {   // a jagged line of n segments from (x0, y0)
  var ca = Math.cos(ang), sa = Math.sin(ang), pts = [];
  for (var m = 0; m <= n; m++) {
    var u = m / n, j = (m === 0 || m === n) ? 0 : r.uniform(-1, 1) * jit;
    pts.push([x0 + ca * len * u - sa * j, y0 + sa * len * u + ca * j]);
  }
  return pts;
}

// ---------------------------------------------------------------- timeline
function rsFmax(P) { return Math.max(1, Math.ceil(+P.length / RS_SPEED)); }
function ghCount(P) { return Math.floor(ti(P, "hold_ticks") / ti(P, "swing_ticks", 1)) + 1; }
function ghMax(P) { return GH_FLOAT + Math.ceil(+P.length / GH_SPEED) + 24; }
function activeTicks(P) {
  var st = L_().style(P);
  if (st === "ssj_aura") return ti(P, "swing_ticks", 1) + ti(P, "hold_ticks", 1);
  if (st === "rasen_shuriken") return ti(P, "swing_ticks", 1) + rsFmax(P) + ti(P, "hold_ticks", 1) + 1;
  if (st === "gigantic_meteor") return ti(P, "swing_ticks", 1) + MET_FALL + ti(P, "hold_ticks", 1) + MET_BLAST_HIT;
  if (st === "ghost_kamikaze") return (ghCount(P) - 1) * ti(P, "swing_ticks", 1) + ghMax(P) + 1;
  if (st === "serious_punch") return ti(P, "swing_ticks", 1) + SP_OUT + ti(P, "hold_ticks", 1) + 1;
  return ti(P, "swing_ticks", 1) + ti(P, "hold_ticks", 1) + BH_COLLAPSE + BH_BURST_HIT;
}
function totalTicks(P) {
  var st = L_().style(P);
  if (st === "ssj_aura") return activeTicks(P) + AURA_FADE;
  if (st === "rasen_shuriken") return activeTicks(P) + RS_FADE;
  if (st === "gigantic_meteor") return ti(P, "swing_ticks", 1) + MET_FALL + ti(P, "hold_ticks", 1) + MET_BLAST_LIFE;
  if (st === "ghost_kamikaze") return activeTicks(P) + GH_BLAST_LIFE;
  if (st === "serious_punch") return activeTicks(P) + SP_SPLIT_LIFE;
  return ti(P, "swing_ticks", 1) + ti(P, "hold_ticks", 1) + BH_COLLAPSE + BH_BURST_LIFE;
}
function onSpawn(inst, host) {
  inst.tq_sil = [];     // aura: the body outline per tick (swordfx.js onTick)
  inst.tq_det = null;   // rasen-shuriken: where it went off when a hit stopped it [tick, x, y]
  inst.tq_gh = {};      // ghosts: index -> flight state (ghSim)
}

// ================================================================ ssj aura
// The aura hugs the fighter's real silhouette (inst.tq_sil, from host.outline;
// an ellipse when there is none) and reacts to movement like a flame in the
// wind: licks born on the body's edge rise and keep only part of the
// fighter's speed, so at rest they stand straight up and on the move they
// stream behind it.  laser/powerfx.py.
// Radial outline of a sprite: n points (image px) round its alpha centroid,
// the farthest opaque pixel along each ray (clockwise from the top); null
// when empty.  laser/powerfx.py outline_from_alpha.
function outlineFromAlpha(w, h, alpha, n, thr) {
  n = n || AURA_N; thr = thr == null ? 40 : thr;
  var step = Math.max(1, Math.floor(Math.min(w, h) / 32)), sx = 0, sy = 0, cnt = 0, x, y;
  for (y = 0; y < h; y += step) for (x = 0; x < w; x += step) if (alpha(x, y) > thr) { sx += x; sy += y; cnt++; }
  if (!cnt) return null;
  var cx = sx / cnt, cy = sy / cnt, far = Math.sqrt(w * w + h * h), dstep = Math.max(0.5, step * 0.5), out = [];
  for (var i = 0; i < n; i++) {
    var an = 2 * PI * i / n - PI / 2, ca = Math.cos(an), sa = Math.sin(an), best = 0, d = 0;
    while (d < far) {
      x = Math.trunc(cx + ca * d); y = Math.trunc(cy + sa * d);
      if (x >= 0 && x < w && y >= 0 && y < h && alpha(x, y) > thr) best = d;
      d += dstep;
    }
    out.push([cx + ca * best, cy + sa * best]);
  }
  return out;
}
function auraSil(inst, ps, t) {   // the body outline at tick t, or an ellipse round the anchor
  var s = inst.tq_sil && inst.tq_sil.length ? at(inst.tq_sil, t) : null;
  if (s) return s;
  var p = at(inst.tq_path, t), out = [];
  for (var i = 0; i < AURA_N; i++) {
    var a = 2 * PI * i / AURA_N - PI / 2;
    out.push([p[0] + Math.cos(a) * 8 * ps, p[1] + Math.sin(a) * 14 * ps]);
  }
  return out;
}
function centroid(pts) {
  var sx = 0, sy = 0;
  pts.forEach(function (p) { sx += p[0]; sy += p[1]; });
  return [sx / pts.length, sy / pts.length];
}
function auraVel(inst, t) {   // px per tick, smoothed over 3 ticks
  var p1 = at(inst.tq_path, t), p0 = at(inst.tq_path, t - 3), k = Math.min(3, Math.max(1, t));
  return [(p1[0] - p0[0]) / k, (p1[1] - p0[1]) / k];
}
// Angle the aura points at tick t: up at rest, toward the opposite of the
// movement as the speed rises (fully at AURA_FULL).  laser/powerfx.py _aura_aim.
function auraAim(inst, ps, react, t) {
  var v = auraVel(inst, Math.max(0, t)), s = Math.min(1, hyp(v[0], v[1]) / ps * react / AURA_FULL);
  if (s <= 0) return -PI / 2;
  var to = Math.atan2(-v[1], -v[0]), d = Math.atan2(Math.sin(to + PI / 2), Math.cos(to + PI / 2));
  return -PI / 2 + d * s;
}
// The way the flames point at tick t (unit vector), swung round smoothly over
// the last AURA_SWING_N ticks.  laser/powerfx.py _aura_flow.
function auraFlow(inst, ps, react, t) {
  var sx = 0, sy = 0, w = 1, a;
  for (var j = 0; j <= AURA_SWING_N; j++) {
    a = auraAim(inst, ps, react, t - j);
    sx += w * Math.cos(a); sy += w * Math.sin(a); w *= AURA_SWING;
  }
  var d = hyp(sx, sy);
  if (d < 1e-6) { a = auraAim(inst, ps, react, t); return [Math.cos(a), Math.sin(a)]; }
  return [sx / d, sy / d];
}
// How sharply the fighter turned at tick t (0-1): the bend between its heading
// now and 4 ticks ago (a reversal = 1), scaled by its speed.  laser/powerfx.py _aura_turn.
function auraTurn(inst, ps, react, t) {
  var v1 = auraVel(inst, t), v0 = auraVel(inst, t - 4), s1 = hyp(v1[0], v1[1]), s0 = hyp(v0[0], v0[1]);
  if (t < 4 || s1 < 0.5 * ps || s0 < 0.5 * ps) return 0;
  var co = (v1[0] * v0[0] + v1[1] * v0[1]) / (s1 * s0), bend = (1 - co) / 2;
  return Math.min(1, bend * 2) * Math.min(1, Math.max(s1, s0) / ps * react / AURA_FULL);
}
function auraK(P, t) {   // [size, alpha] at tick t
  var Ti = ti(P, "swing_ticks", 1), act = activeTicks(P), L = L_();
  if (t < Ti) { var u = t / Ti; return [L.easeOut3(u) * (1 + 0.25 * Math.sin(PI * u)), 1]; }
  if (t < act) return [1, 1];
  var q = cl((t - act) / AURA_FADE);
  return [1 + 0.1 * q, Math.pow(1 - q, 1.5)];
}
function auraSurge(inst, P, t) {   // [intensity 1-1.6, tick the surge began or null]
  if (!P.aura_surges || t < ti(P, "swing_ticks", 1) || t >= activeTicks(P)) return [1, null];
  var slot = Math.floor(t / AURA_SURGE_SLOT), r = L_().rngFor(inst.seed, slot, 251);
  var b = slot * AURA_SURGE_SLOT + Math.trunc(r() * (AURA_SURGE_SLOT - AURA_SURGE_LEN)), a = t - b;
  if (a < 0 || a >= AURA_SURGE_LEN) return [1, null];
  return [1 + 0.6 * Math.sin(PI * a / AURA_SURGE_LEN), b];
}
function auraHit(inst, tx, ty, hr, ps) {
  var P = inst.fx.params, t = inst.age;
  if (t >= activeTicks(P)) return false;
  var k = auraK(P, t)[0], sil = auraSil(inst, ps, t), c0 = centroid(sil), rmax = 0;
  sil.forEach(function (p) { rmax = Math.max(rmax, hyp(p[0] - c0[0], p[1] - c0[1])); });
  return hyp(tx - c0[0], ty - c0[1]) <= hr + (rmax + +P.radius * ps) * k;
}
// A flame tongue: round at its base (cx, cy), tapering to a tip ln px along (ux, uy), curling by bend px.
function lick(cx, cy, ux, uy, ln, w, bend) {
  var px = -uy, py = ux, left = [], right = [];
  for (var j = 0; j < 8; j++) {
    var s = j / 7, hw = w * (s < 0.75 ? Math.sin(PI * Math.min(1, 0.25 + s)) : 1) * Math.pow(1 - s, 0.8), cv = bend * s * s;
    var bx = cx + ux * (s - 0.2) * ln + px * cv, by = cy + uy * (s - 0.2) * ln + py * cv;
    left.push([bx + px * hw, by + py * hw]); right.push([bx - px * hw, by - py * hw]);
  }
  return left.concat(rev(right));
}
function drawAura(pen, inst, host, ps) {
  var P = inst.fx.params, t = inst.age, L = L_(), HOT = L.HOT, i, j, r, a, q, b;
  if (t >= totalTicks(P)) return;
  var cs = L.colours(inst, host), c = cs[0], bright = cs[1];
  var ka = auraK(P, t), k = ka[0], al = ka[1], act = activeTicks(P), Ti = ti(P, "swing_ticks", 1);
  var R = +P.radius * ps, Lf = +P.length * ps, Tw = +P.thickness * ps;
  var react = Math.max(0, P.span != null ? +P.span : 100) / 100, dens = +P.density || 1;
  var su = auraSurge(inst, P, t), sk = su[0], sb = su[1];
  var sil = auraSil(inst, ps, t), c0 = centroid(sil), cx = c0[0], cy = c0[1];
  var v = auraVel(inst, t), vx = v[0], vy = v[1], sp = hyp(vx, vy);
  var ux = sp > 0.05 ? vx / sp : 0, uy = sp > 0.05 ? vy / sp : 0;
  var feetY = -Infinity, halfW = 0, n = sil.length;
  sil.forEach(function (p) { feetY = Math.max(feetY, p[1]); halfW = Math.max(halfW, Math.abs(p[0] - cx)); });
  var fl = 0.92 + 0.08 * Math.sin(t * 1.7) + 0.05 * Math.sin(t * 4.3);
  // 1: ground — cracks at the feet, rocks and dust (painted normally, under the light)
  pen.add(false);
  if (P.aura_cracks && t >= 1) auraCracks(pen, inst, P, ps, c, t, act);
  if (P.aura_burst && t < 34) {
    var s0 = auraSil(inst, ps, 0), x0 = centroid(s0)[0], fy0 = -Infinity;
    s0.forEach(function (p) { fy0 = Math.max(fy0, p[1]); });
    for (j = 0; j < Math.max(0, Math.round(14 * dens)); j++) {
      r = L.rngFor(inst.seed, j, 261);
      var an = r.uniform(0, PI * 2), v0 = r.uniform(3, 7) * ps, d = v0 * L.dragDist(0.9, t);
      q = t / 34;
      pen.glow(x0 + Math.cos(an) * d, fy0 + Math.sin(an) * d * 0.3 - t * 0.2 * ps, (4 + 6 * q) * ps * r.uniform(0.8, 1.3),
               DUST, 110 * Math.pow(1 - q, 1.5), 0.6);
    }
  }
  if (P.aura_debris) auraRocks(pen, inst, P, ps, c, t, act);
  pen.add(true);
  if (al <= 0) return;
  // 2: a soft glow over the whole aura
  var G = auraFlow(inst, ps, react, t), Gx = G[0], Gy = G[1], hh = 0.15 * (feetY - cy);
  pen.glow(cx + Gx * hh, cy + Gy * hh, (halfW + R * 2 + Lf * 0.5) * k * sk, c, 55 * al * fl, 0.5);
  // 3: the aura's skin: the silhouette pushed out, taller along the flow, streaming behind when it moves
  var gx = Gx, gy = Gy;   // up at rest, turned to point back along the motion
  sil.forEach(function (p) { pen.glow(p[0], p[1], (R * 1.8 + Tw) * k * sk, c, 34 * al * fl, 0.5); });
  [[1.0, c, 30], [0.6, L.mix(c, bright, 0.5), 30], [0.28, bright, 30]].forEach(function (lay) {
    var m = lay[0], pts = [];
    sil.forEach(function (p, ii) {
      var dx = p[0] - cx, dy = p[1] - cy, dd = hyp(dx, dy) || 1, nx = dx / dd, ny = dy / dd;
      var ext = R * (1 + 0.22 * Math.sin(t * 0.55 + ii * 1.7) + 0.14 * Math.sin(t * 1.35 - ii * 0.9));
      ext += R * 0.6 * Math.abs(nx);
      ext += Lf * 0.6 * Math.pow(Math.max(0, nx * gx + ny * gy), 1.5) * (1 + 0.25 * Math.sin(t * 0.8 + ii));
      var back = Math.max(0, -(nx * ux + ny * uy)), tail = Math.pow(back, 1.5) * sp * AURA_STRETCH * react * ps, e = ext * m * k * sk;
      var tl = tail * k * (m === 1.0 ? 0.6 : 0);   // only the outer skin streams back; the licks make the comet
      pts.push([p[0] + nx * e - ux * tl, p[1] + ny * e - uy * tl]);
    });
    pen.poly(pts, lay[1], lay[2] * al * fl);
  });
  // 4: flame licks, attached: each is born on a point of the body's edge and
  //    stays with that point, rising along the aura's flow (so they never spill
  //    out on their own); at speed they stretch back along the flow (capped)
  var stretch = Math.min(1, sp / ps * react / AURA_FULL);
  for (b = Math.max(0, t - AURA_LICK_LIFE + 1); b <= t; b++) {
    if (b >= act) break;
    var bk = auraK(P, b)[0], bs = auraSurge(inst, P, b)[0];
    a = t - b;
    for (j = 0; j < Math.max(0, Math.round(AURA_RATE * dens * bs)); j++) {
      r = L.rngFor(inst.seed, b, 271 + j);
      var ep = sil[Math.min(n - 1, Math.trunc(r() * n))], ex = ep[0], ey = ep[1];
      var ldx = ex - cx, ldy = ey - cy, ld = hyp(ldx, ldy) || 1, nx = ldx / ld, ny = ldy / ld;
      var off = R * r.uniform(0.2, 1.1) * bk, life = AURA_LICK_LIFE * r.uniform(0.6, 1.0), u = a / life;
      if (u >= 1) continue;
      var rise = AURA_RISE * ps * r.uniform(0.8, 1.35) * bs;
      // a little outward, laid out in the aura's frame (wider across the flow than along it)
      var npp = nx * -gy + ny * gx, npl = nx * gx + ny * gy;
      var ox_ = (-gy * npp * 0.7 + gx * npl * 0.35) * ps, oy_ = (gx * npp * 0.7 + gy * npl * 0.35) * ps;
      var rx = gx * rise + ox_, ry = gy * rise + oy_, rl = hyp(rx, ry) || 1, fx_ = rx / rl, fy_ = ry / rl;
      var ph = r.uniform(0, PI * 2), sway = Math.sin(a * 0.45 + ph) * 1.6 * ps * u;
      var drift = AURA_DRIFT * a * (1 + 1.5 * stretch);
      var px = ex + nx * off + rx * drift - fy_ * sway, py = ey + ny * off + ry * drift + fx_ * sway;
      var ln = Lf * r.uniform(0.55, 1.0) * (0.45 + 0.8 * Math.sin(PI * Math.min(1, u * 1.15))) * bk * (1 + 1.2 * stretch);
      var w = Tw * r.uniform(0.7, 1.2) * Math.pow(1 - u, 0.5) * bk;
      var fade = Math.sin(PI * Math.min(1, 0.15 + u * 0.85)) * al, bend = Math.sin(a * 0.3 + ph) * w * 1.2;
      pen.poly(lick(px, py, fx_, fy_, ln, w, bend), c, 60 * fade);
      pen.poly(lick(px, py, fx_, fy_, ln * 0.7, w * 0.5, bend * 0.7), L.mix(c, bright, 0.6), 50 * fade);
      if (u < 0.45) pen.poly(lick(px, py, fx_, fy_, ln * 0.4, w * 0.22, bend * 0.4), HOT, 55 * fade * (1 - u / 0.45));
    }
  }
  // 4b: on a sharp turn at speed, a few small fragments of the aura break off
  //     and fly on the way the fighter was going, fading fast
  for (b = Math.max(0, t - AURA_FRAG_LIFE + 1); b <= t; b++) {
    if (b >= act) break;
    var sharp = auraTurn(inst, ps, react, b);
    if (sharp <= 0) continue;
    r = L.rngFor(inst.seed, b, 281);
    if (r() >= sharp * AURA_FRAG_P) continue;
    var silb = auraSil(inst, ps, b), bc = centroid(silb), ov = auraVel(inst, b - 4), bg = auraFlow(inst, ps, react, b);
    a = t - b;
    var nfrag = 1 + Math.trunc(r() * 2);   // rolled once (laser/powerfx.py range())
    for (j = 0; j < nfrag; j++) {
      var fp = silb[Math.min(n - 1, Math.trunc(r() * n))], flife = r.uniform(9, AURA_FRAG_LIFE), sv = r.uniform(0.45, 0.75);
      if (a >= flife) continue;
      var fu = a / flife;
      var fvx = ov[0] * sv + bg[0] * AURA_RISE * ps, fvy = ov[1] * sv + bg[1] * AURA_RISE * ps, fvl = hyp(fvx, fvy) || 1;
      var fpx = fp[0] + (fp[0] - bc[0]) * 0.3 + fvx * L.dragDist(0.9, a), fpy = fp[1] + (fp[1] - bc[1]) * 0.3 + fvy * L.dragDist(0.9, a);
      var fln = Lf * 0.45 * (1 - 0.5 * fu) * k, fw = Tw * 0.6 * (1 - fu) * k, ffade = Math.pow(1 - fu, 1.2) * al;
      pen.poly(lick(fpx, fpy, -fvx / fvl, -fvy / fvl, fln, fw, 0), c, 80 * ffade);
      pen.poly(lick(fpx, fpy, -fvx / fvl, -fvy / fvl, fln * 0.6, fw * 0.45, 0), bright, 90 * ffade);
    }
  }
  // 5: sparks of energy rising off it, riding with the body along the flow
  for (b = Math.max(0, t - 23); b <= t; b++) {
    if (b >= act) break;
    a = t - b;
    for (j = 0; j < Math.max(0, Math.round(1 * dens)); j++) {
      r = L.rngFor(inst.seed, b, 291 + j);
      var sp0 = sil[Math.min(n - 1, Math.trunc(r() * n))], lf = r.uniform(14, 24);
      if (a >= lf) continue;
      q = a / lf;
      var rs = AURA_RISE * ps * r.uniform(1.2, 2.0), sside = r.uniform(-1, 1) * R * 0.5;
      var sx = sp0[0] + gx * rs * a * 0.8 - gy * sside, sy = sp0[1] + gy * rs * a * 0.8 + gx * sside, tl = 2 * ps + rs * 1.2;
      pen.line(sx, sy, sx - gx * tl, sy - gy * tl, L.mix(c, HOT, 0.6), 200 * (1 - q) * al, 1.1 * ps);
      pen.glow(sx, sy, 2.2 * ps, HOT, 200 * (1 - q) * al, 0.6);
    }
  }
  // 6: a white-hot rim hugging the body
  var rim = sil.map(function (p) {
    var dx = p[0] - cx, dy = p[1] - cy, dd = hyp(dx, dy) || 1;
    return [p[0] + dx / dd * 1.5 * ps, p[1] + dy / dd * 1.5 * ps];
  });
  rim.push(rim[0]);
  pen.polyline(rim, c, 80 * al * k, 3 * ps);
  pen.polyline(rim, HOT, 110 * al * fl * k, 1 * ps);
  // 7: speed lines streaming off it when it moves fast
  if (sp * react > 2) {
    var g = Math.min(1, (sp * react - 2) / 4);
    for (j = 0; j < Math.max(0, Math.round(4 * dens)); j++) {
      r = L.rngFor(inst.seed, t, 301 + j);
      var e2 = sil[Math.min(n - 1, Math.trunc(r() * n))], sl = sp * r.uniform(1.5, 3) * react;
      pen.line(e2[0], e2[1], e2[0] - ux * sl, e2[1] - uy * sl, L.mix(c, HOT, 0.5), 170 * g * al, 1.1 * ps);
    }
  }
  // 8: ignition — a flash and a shock ring (Burst on)
  if (P.aura_burst) {
    if (t < 6) pen.glow(cx, cy, (halfW + R) * (1.6 + 1.5 * t / 6), HOT, 240 * (1 - t / 6));
    a = t - Math.floor(Ti / 3);
    if (a >= 0 && a < 18) {
      q = a / 18;
      var rr = (halfW + R) * (1.2 + 4 * L.easeOut3(q));
      pen.ring(cx, cy, rr, rr * 0.85, 0, c, 210 * (1 - q), 3.5 * ps * (1 - q) + 0.2);
      pen.ring(cx, feetY, rr * 1.2, rr * 0.3, 0, HOT, 170 * (1 - q), 2 * ps * (1 - q) + 0.2);
    }
  }
  // 9: a power surge flares a ring off the body as it starts
  if (sb !== null) {
    a = t - sb;
    if (a < 12) {
      q = a / 12;
      var sr = (halfW + R) * (1.3 + 2 * L.easeOut3(q));
      pen.ring(cx, cy, sr, sr * 1.15, 0, bright, 160 * (1 - q), 2.2 * ps * (1 - q) + 0.2);
    }
  }
  // 10: Super Saiyan 2 lightning, every now and then, crackling over the body
  if (P.lightning) {
    var pSlot = Math.min(1, Math.max(0, +P.lightning_rate || 0) * AURA_SLOT * FXK().TICK_MS / 1000), sNow = Math.floor(t / AURA_SLOT);
    for (var s = Math.max(0, sNow - 2); s <= sNow; s++) {
      for (j = 0; j < 2; j++) {
        r = L.rngFor(inst.seed, s, 231 + j);
        if (r() >= pSlot * (j === 0 ? 1 : 0.35)) continue;
        b = s * AURA_SLOT + Math.trunc(r() * AURA_SLOT);
        var kk = t - b;
        if (kk < 0 || kk >= AURA_BOLT_LIFE || b >= act) continue;
        var f = AURA_BOLT_FLICKER[kk] * al, bp0 = sil[Math.min(n - 1, Math.trunc(r() * n))];
        var bx0 = bp0[0], by0 = bp0[1];
        bx0 += (cx - bx0) * r.uniform(0, 0.5);
        by0 += (cy - by0) * r.uniform(0, 0.5);
        var ang = r.uniform(0, PI * 2), len = r.uniform(12, 28) * ps * k;
        var rj = L.rngFor(inst.seed, s * 7 + j, 240 + kk);   // the bolt re-jags every tick
        var pts = bolt(rj, bx0, by0, ang, len, 6, 5 * ps), bp = pts[3];
        var br = bolt(rj, bp[0], bp[1], ang + (rj() < 0.5 ? 0.6 : -0.6), len * 0.45, 3, 3 * ps);
        pen.glow(bx0, by0, 10 * ps, BOLT, 160 * f);
        pen.polyline(pts, BOLT, 140 * f, 3.2 * ps);
        pen.polyline(br, BOLT, 110 * f, 2.2 * ps);
        pen.polyline(pts, HOT, 255 * f, 1.1 * ps);
        pen.polyline(br, HOT, 220 * f, 0.8 * ps);
      }
    }
  }
}
function auraCracks(pen, inst, P, ps, c, t, act) {   // cracks spreading from the feet as it ignites
  var L = L_(), s0 = auraSil(inst, ps, 0), x0 = centroid(s0)[0], y0 = -Infinity, half = 0;
  s0.forEach(function (p) { y0 = Math.max(y0, p[1]); });
  s0.forEach(function (p) { half = Math.max(half, Math.abs(p[0] - x0)); });
  var grow = L.easeOut3(t / 10), fade = t < act ? 1 : Math.max(0, 1 - (t - act) / AURA_FADE), hot = Math.max(0, 1 - t / 45);
  for (var i = 0; i < AURA_CRACKS; i++) {
    var r = L.rngFor(inst.seed, i, 311), an = (i + r.uniform(-0.3, 0.3)) * 2 * PI / AURA_CRACKS, ln = half * r.uniform(2, 4) * grow;
    var pts = [[x0, y0]];
    for (var m = 1; m < 6; m++) {
      var u = m / 5, j = r.uniform(-1, 1) * 0.35;
      pts.push([x0 + Math.cos(an + j) * ln * u, y0 + Math.sin(an + j) * ln * u * 0.3]);
    }
    pen.polyline(pts, CRACK, 200 * fade, 1.6 * ps);
    if (hot > 0) { pen.add(true); pen.polyline(pts, c, 170 * hot * fade, 0.9 * ps); pen.add(false); }
  }
}
function auraRocks(pen, inst, P, ps, c, t, act) {   // rocks lifting off the ground round the feet
  var L = L_();
  for (var b = Math.max(0, t - AURA_ROCK_LIFE); b <= Math.min(t, act); b += AURA_ROCK_EVERY) {
    var bv = auraVel(inst, b);
    if (hyp(bv[0], bv[1]) > 1.5) continue;   // only off the ground it stands on
    var a = t - b, silb = auraSil(inst, ps, b), x0 = centroid(silb)[0], y0 = -Infinity, half = 0;
    silb.forEach(function (p) { y0 = Math.max(y0, p[1]); half = Math.max(half, Math.abs(p[0] - x0)); });
    var r = L.rngFor(inst.seed, b, 321), life = AURA_ROCK_LIFE * r.uniform(0.6, 1.0);
    if (a >= life) continue;
    var q = a / life;
    var x = x0 + r.uniform(-2.4, 2.4) * half + Math.sin(a * 0.12 + r() * 6) * 2 * ps;
    var y = y0 + r.uniform(-2, 3) * ps - r.uniform(0.35, 0.9) * ps * a;
    var sz = r.uniform(1.0, 2.6) * ps, rot = r.uniform(0, PI) + a * r.uniform(-0.08, 0.08);
    var fa = Math.min(1, a / 6) * Math.pow(1 - q, 0.7), pts = [];
    for (var m = 0; m < 4; m++) {
      var ra = rot + m * 1.6 + 0.3 * (m % 2), rk = 0.8 + 0.3 * (m % 2);
      pts.push([x + Math.cos(ra) * sz * rk, y + Math.sin(ra) * sz * rk]);
    }
    pen.poly(pts, ROCK, 230 * fa);
    pen.add(true); pen.glow(x, y - sz * 0.4, sz * 1.6, c, 90 * fa); pen.add(false);
  }
}

// ================================================================ rasen-shuriken
function rsLaunch(inst, ps) {   // [x0, y0, ux, uy, flight ticks, range] of the throw
  var P = inst.fx.params, Tc = ti(P, "swing_ticks", 1), o = at(inst.tq_path, Tc), tg = at(inst.tq_tp, Tc);
  var dx = tg[0] - o[0], dy = tg[1] - o[1], d = hyp(dx, dy), Lr = +P.length * ps, ux, uy, rng;
  if (d < 1) { ux = inst.tq_f[0]; uy = inst.tq_f[1]; rng = Lr; }
  else { ux = dx / d; uy = dy / d; rng = Math.max(30 * ps, Math.min(Lr, d)); }
  return [o[0], o[1], ux, uy, Math.max(1, Math.ceil(rng / (RS_SPEED * ps))), rng];
}
function rsDet(inst, ps) {   // [tick, x, y] where it goes off
  if (inst.tq_det) return inst.tq_det;
  var l = rsLaunch(inst, ps);
  return [ti(inst.fx.params, "swing_ticks", 1) + l[4], l[0] + l[2] * l[5], l[1] + l[3] * l[5]];
}
function rsOrbAt(inst, ps, t) {
  var Tc = ti(inst.fx.params, "swing_ticks", 1);
  if (t <= Tc) return at(inst.tq_path, t);
  var l = rsLaunch(inst, ps), d = RS_SPEED * ps * (t - Tc);
  return [l[0] + l[2] * d, l[1] + l[3] * d];
}
function rsSpin(t, Tc) {
  if (t <= Tc) return RS_SPIN[0] * t + (RS_SPIN[1] - RS_SPIN[0]) * t * t / (2 * Tc);
  return RS_SPIN[0] * Tc + (RS_SPIN[1] - RS_SPIN[0]) * Tc / 2 + RS_SPIN[1] * (t - Tc);
}
function rsSphere(P, ps, a) {   // explosion radius a ticks after it went off (0 = gone)
  var Th = ti(P, "hold_ticks", 1), L = L_();
  if (a < 0 || a >= Th) return 0;
  var B = +P.thickness * ps, g = L.easeOut3(a / RS_GROW), sh = 1;
  if (a > Th - RS_SHRINK) sh = 1 - L.easeIn3((a - (Th - RS_SHRINK)) / RS_SHRINK);
  return B * (0.15 + 0.85 * g) * (0.4 + 0.6 * sh) * (1 + 0.03 * Math.sin(a * 1.3));
}
function rsHit(inst, tx, ty, hr, ps) {
  var P = inst.fx.params, t = inst.age, Tc = ti(P, "swing_ticks", 1);
  if (t < Tc || t >= inst.life) return false;
  var e = rsDet(inst, ps);
  if (t < e[0]) {
    var o = rsOrbAt(inst, ps, t);
    return hyp(o[0] - tx, o[1] - ty) <= hr + +P.radius * ps + +P.span * ps * 0.5;
  }
  var R = rsSphere(P, ps, t - e[0]);
  return R > 0 && hyp(e[1] - tx, e[2] - ty) <= hr + R;
}
function rsOnHit(inst, ps) {
  var P = inst.fx.params, t = inst.age;
  if (!inst.tq_det && t >= ti(P, "swing_ticks", 1)) {
    var e = rsDet(inst, ps);
    if (t < e[0]) { var o = rsOrbAt(inst, ps, t); inst.tq_det = [t, o[0], o[1]]; }
  }
}
// The four wind blades, swept back against the spin: a coloured blade with a white-hot inner blade.
function rsBlades(pen, x, y, R, span, ang, c, a, ps) {
  if (span <= R * 0.9 || a <= 1 / 255) return;
  var n = 10, HOT = L_().HOT;
  for (var i = 0; i < 4; i++) {
    var th = ang + i * PI / 2;
    [[0.5, c, 150], [0.22, HOT, 200]].forEach(function (lay) {
      var lead = [], trail = [];
      for (var j = 0; j <= n; j++) {
        var u = j / n, rr = R * 0.8 + (span - R * 0.8) * u, base = th - 0.55 * u, wa = lay[0] * Math.pow(1 - u, 0.9);
        lead.push([x + Math.cos(base + wa) * rr, y + Math.sin(base + wa) * rr]);
        trail.push([x + Math.cos(base - wa * 1.6) * rr, y + Math.sin(base - wa * 1.6) * rr]);
      }
      pen.poly(lead.concat(rev(trail)), lay[1], lay[2] * a);
    });
  }
}
function rsOrb(pen, x, y, R, span, ang, c, bright, a, ps, spinFast) {
  var HOT = L_().HOT;
  pen.glow(x, y, R * 2.4 + span * 0.6, c, 90 * a);
  // the thin disc it spins in, seen at an angle
  pen.ring(x, y, span * 0.95, span * 0.95 * 0.42, 0, HOT, 120 * a, 1.4 * ps);
  pen.ring(x, y, span * 0.95, span * 0.95 * 0.42, 0, c, 90 * a, 4 * ps);
  if (spinFast) {
    rsBlades(pen, x, y, R, span, ang - 0.36, c, 0.2 * a, ps);
    rsBlades(pen, x, y, R, span, ang - 0.18, c, 0.37 * a, ps);
  }
  rsBlades(pen, x, y, R, span, ang, c, a, ps);
  pen.glow(x, y, R * 1.9, c, 200 * a);
  pen.glow(x, y, R * 1.15, bright, 235 * a);
  pen.glow(x, y, R * 0.6, HOT, 255 * a, 0.7);
  for (var i = 0; i < 3; i++) {
    var a0 = ang * 1.7 + i * 2.09;
    arc(pen, x, y, R * 0.55, R * 0.55, 0, a0, a0 + 1.2, HOT, 170 * a, 1.1 * ps, 8);
  }
}
function drawRasen(pen, inst, host, ps) {
  var P = inst.fx.params, t = inst.age, L = L_(), HOT = L.HOT, i, j, r;
  var cs = L.colours(inst, host), c = cs[0], bright = cs[1];
  var Tc = ti(P, "swing_ticks", 1), Th = ti(P, "hold_ticks", 1);
  var R0 = +P.radius * ps, SP = +P.span * ps, B = +P.thickness * ps, dens = +P.density || 1;
  var det = rsDet(inst, ps), e = det[0], ex = det[1], ey = det[2], ang = rsSpin(t, Tc);
  pen.add(true);
  if (t < e) {
    var o = rsOrbAt(inst, ps, t), x = o[0], y = o[1];
    if (t <= Tc) {
      // 1: charge — the orb forms, the blades grow out, wind is drawn in
      var g = L.easeOut3(t / Tc), R = R0 * (0.35 + 0.65 * g), span = SP * Math.pow(g, 1.5);
      for (i = 0; i < Math.max(0, Math.round(14 * dens)); i++) {
        r = L.rngFor(inst.seed, i, 301);
        var per = r.uniform(10, 18), u = frac(t / per + r()), rad = (1 - u) * SP * 2.2 + R, an = r.uniform(0, PI * 2) + u * 2.5;
        var px = x + Math.cos(an) * rad, py = y + Math.sin(an) * rad, tl = 8 * ps;
        pen.line(px, py, px - Math.sin(an) * tl, py + Math.cos(an) * tl, L.mix(c, HOT, 0.5), 180 * Math.sin(PI * u), 1.2 * ps);
      }
      rsOrb(pen, x, y, R, Math.max(span, R * 0.9), ang, c, bright, 1, ps, g > 0.6);
    } else {
      // 2: flight — wind streaks behind it, afterimages, the spinning orb
      var l = rsLaunch(inst, ps), ux = l[2], uy = l[3];
      for (j = 0; j < 6; j++) {
        r = L.rngFor(inst.seed, j, 311);
        var off = r.uniform(-0.5, 0.5) * SP, ln = r.uniform(18, 40) * ps;
        var sx = x - ux * R0 - uy * off, sy = y - uy * R0 + ux * off;
        pen.line(sx, sy, sx - ux * ln, sy - uy * ln, L.mix(c, HOT, 0.4), 120, 1.3 * ps);
      }
      [[2, 50], [1, 90]].forEach(function (ga) {
        var gp = rsOrbAt(inst, ps, t - ga[0]);
        pen.glow(gp[0], gp[1], R0 * 2, c, ga[1]);
      });
      rsOrb(pen, x, y, R0, SP, ang, c, bright, 1, ps, true);
    }
    return;
  }
  // 3: the explosion — a huge sphere of wind full of needle cuts
  var a = t - e, q, rr;
  if (a >= Th + RS_FADE) return;
  var RR = rsSphere(P, ps, a);
  if (a < 6) pen.glow(ex, ey, B * (0.5 + 0.6 * a / 6), HOT, 255 * (1 - a / 6));
  if (RR > 0) {
    var sh = RR / Math.max(1e-6, B), al = Math.min(1, sh * 1.2);
    pen.glow(ex, ey, RR * 1.35, c, 120 * al, 0.6);
    pen.glow(ex, ey, RR, bright, 150 * al, 0.75);
    pen.ring(ex, ey, RR, RR, 0, c, 90 * al, 5 * ps);
    pen.ring(ex, ey, RR, RR, 0, HOT, 150 * al, 2.2 * ps);
    for (i = 0; i < 3; i++) pen.ring(ex, ey, RR * 0.95, RR * 0.95 * 0.25, i * 1.05 + a * 0.05 * (i + 1), HOT, 110 * al, 1.3 * ps);
    var n = Math.max(0, Math.round(22 * dens));
    for (var b = Math.max(0, a - 2); b <= a; b++) {
      if (b >= Th) continue;
      var kk = a - b;
      for (j = 0; j < n; j++) {
        r = L.rngFor(inst.seed, b, 321 + j);
        var cr = RR * Math.sqrt(r()), can = r.uniform(0, PI * 2), ca = r.uniform(0, PI), cln = r.uniform(5, 13) * ps;
        var cx = ex + Math.cos(can) * cr, cy = ey + Math.sin(can) * cr, dx = Math.cos(ca) * cln / 2, dy = Math.sin(ca) * cln / 2;
        var f = 1 - kk / 3;
        pen.line(cx - dx, cy - dy, cx + dx, cy + dy, c, 120 * f, 2.2 * ps);
        pen.line(cx - dx, cy - dy, cx + dx, cy + dy, HOT, 255 * f, 1 * ps);
      }
    }
    if (a < 14) rsBlades(pen, ex, ey, R0, RR * 1.15, rsSpin(t, Tc), c, 1 - a / 14, ps);
  }
  if (a < 16) {
    q = a / 16; rr = B * (0.3 + 1.4 * L.easeOut3(q));
    pen.ring(ex, ey, rr, rr, 0, c, 200 * (1 - q), 3 * ps * (1 - q) + 0.2);
  }
  sparks(pen, inst, ex, ey, a, Math.max(0, Math.round(14 * dens)), 331, c, ps, [4, 10], [14, 24], 0.05);
  if (a >= Th && a < Th + RS_FADE) {
    q = (a - Th) / RS_FADE; rr = B * (0.2 + 0.6 * L.easeOut3(q));
    pen.ring(ex, ey, rr, rr, 0, HOT, 160 * (1 - q), 2 * ps * (1 - q) + 0.2);
    pen.glow(ex, ey, B * 0.4 * (1 - q), c, 160 * (1 - q));
  }
}

// ================================================================ gigantic meteor
// [phase, x, y, R]: phase 0 charge, 1 fall, 2 drag, 3 blast (x, y = where).
function metState(inst, ps, t) {
  var P = inst.fx.params, L = L_(), Tc = ti(P, "swing_ticks", 1), Th = ti(P, "hold_ticks", 1);
  var r0 = +P.radius * ps, r1 = +P.thickness * ps, p;
  if (t <= Tc) { p = at(inst.tq_path, t); return [0, p[0], p[1], r0 * (0.4 + 0.6 * L.easeOut3(t / Tc))]; }
  var o = at(inst.tq_path, Tc), tg = at(inst.tq_tp, Tc), ex = tg[0], ey = tg[1] - 0.45 * r1;
  if (t <= Tc + MET_FALL) {
    var u = (t - Tc) / MET_FALL, k = Math.pow(u, 1.6), lob = MET_LOB * hyp(ex - o[0], ey - o[1]) * Math.sin(PI * u);
    return [1, o[0] + (ex - o[0]) * k, o[1] + (ey - o[1]) * k - lob, r0 + (r1 - r0) * Math.pow(u, 0.9)];
  }
  var Ld = +P.length * ps;
  if (t <= Tc + MET_FALL + Th) {
    var v = (t - Tc - MET_FALL) / Th;
    return [2, ex, ey + Ld * smooth(v), r1 * (1 + MET_GROW_DRAG * v)];
  }
  return [3, ex, ey + Ld, r1 * (1 + MET_GROW_DRAG)];
}
function metHit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var s = metState(inst, ps, inst.age);
  if (s[0] === 0) return false;
  if (s[0] === 3) return hyp(s[1] - tx, s[2] - ty) <= hr + 2 * s[3];
  return hyp(s[1] - tx, s[2] - ty) <= hr + s[3];
}
function metOrb(pen, inst, x, y, R, c, bright, t, ps, a) {
  var L = L_(), HOT = L.HOT, i, j, r;
  a = a == null ? 1 : a;
  pen.glow(x, y, R * 2.2, c, 90 * a);
  pen.glow(x, y, R * 1.25, c, 210 * a, 0.6);
  pen.glow(x, y, R * 0.95, bright, 220 * a, 0.7);
  pen.glow(x, y, R * 0.55, HOT, 230 * a);
  // plasma swirling over the surface
  for (i = 0; i < 5; i++) {
    r = L.rngFor(inst.seed, i, 401);
    var rr = R * r.uniform(0.6, 0.92), a0 = r.uniform(0, PI * 2) + t * r.uniform(0.05, 0.14) * (i % 2 ? 1 : -1);
    arc(pen, x, y, rr, rr * r.uniform(0.75, 1), r.uniform(0, PI), a0, a0 + 1, HOT, 150 * a, 1.6 * ps, 8);
  }
  // crackle on the rim, re-rolled every tick
  for (j = 0; j < 2; j++) {
    r = L.rngFor(inst.seed, t, 411 + j);
    var an = r.uniform(0, PI * 2);
    var pts = bolt(r, x + Math.cos(an) * R * 0.85, y + Math.sin(an) * R * 0.85, an + r.uniform(-1.2, 1.2), R * 0.5, 4, 3 * ps);
    pen.polyline(pts, L.mix(c, HOT, 0.6), 200 * a, 1.3 * ps);
  }
  pen.ring(x, y, R * 1.06, R * 1.06, 0, c, 90 * a, 4 * ps);
  pen.ring(x, y, R, R, 0, HOT, 140 * a, 2 * ps);
}
function drawMeteor(pen, inst, host, ps) {
  var P = inst.fx.params, t = inst.age, L = L_(), HOT = L.HOT, i, j, r, u;
  var cs = L.colours(inst, host), c = cs[0], bright = cs[1];
  var Tc = ti(P, "swing_ticks", 1), Th = ti(P, "hold_ticks", 1), dens = +P.density || 1;
  var s = metState(inst, ps, t), ph = s[0], x = s[1], y = s[2], R = s[3], tb = Tc + MET_FALL + Th;
  // 1: dust thrown up along the trench while it drags (painted normally, under the light)
  if (t > Tc + MET_FALL) {
    pen.add(false);
    var nP = Math.max(0, Math.round(2 * dens));
    for (var b = Tc + MET_FALL; b <= Math.min(t, tb); b += 2) {
      var a0 = t - b;
      if (a0 >= 30) continue;
      var bs = metState(inst, ps, b), bx = bs[1], by = bs[2], bR = bs[3];
      for (j = 0; j < nP; j++) {
        r = L.rngFor(inst.seed, b, 421 + j);
        var side = j % 2 === 0 ? -1 : 1;
        var dpx = bx + side * bR * r.uniform(0.6, 1.05) + side * a0 * r.uniform(0.3, 0.9) * ps;
        var dpy = by + bR * 0.6 - a0 * r.uniform(0.4, 1.0) * ps, dq = a0 / 30;
        pen.glow(dpx, dpy, bR * r.uniform(0.35, 0.6) * (0.5 + dq), DUST, 120 * Math.pow(1 - dq, 1.5) * Math.min(1, a0 / 3), 0.6);
      }
    }
  }
  pen.add(true);
  if (ph === 0) {
    // 2: charge — rings compressing into the orb, energy drawn in
    var g = t / Tc;
    for (j = 0; j < 3; j++) {
      u = frac(t / 12 + j / 3);
      var cr = R * (1 + 3.5 * (1 - u));
      pen.ring(x, y, cr, cr, 0, c, 150 * u * g, 1.6 * ps);
    }
    for (i = 0; i < Math.max(0, Math.round(10 * dens)); i++) {
      r = L.rngFor(inst.seed, i, 431);
      var per = r.uniform(9, 15);
      u = frac(t / per + r());
      var an = r.uniform(0, PI * 2), r1 = R * (1.2 + 4 * (1 - u)), r2 = R * (1.2 + 4 * Math.max(0, 1 - u - 0.15));
      pen.line(x + Math.cos(an) * r1, y + Math.sin(an) * r1, x + Math.cos(an) * r2, y + Math.sin(an) * r2,
               L.mix(c, HOT, 0.5), 200 * Math.sin(PI * u), 1.2 * ps);
    }
    metOrb(pen, inst, x, y, R, c, bright, t, ps);
    return;
  }
  if (ph === 1 || ph === 2) {
    if (ph === 1) {
      // 3: falling — streaks behind it
      var pv = metState(inst, ps, t - 1), dx = x - pv[1], dy = y - pv[2], d = hyp(dx, dy) || 1, ux = dx / d, uy = dy / d;
      for (j = 0; j < 7; j++) {
        r = L.rngFor(inst.seed, j, 441);
        var off = r.uniform(-0.9, 0.9) * R, ln = r.uniform(1, 2.2) * R;
        var sx = x - ux * R * 0.6 - uy * off, sy = y - uy * R * 0.6 + ux * off;
        pen.line(sx, sy, sx - ux * ln, sy - uy * ln, L.mix(c, HOT, 0.3), 110, 1.6 * ps);
      }
    } else {
      // 4: dragging — the glowing trench it gouges, sparks off the leading edge
      var st0 = metState(inst, ps, Tc + MET_FALL);
      pen.line(st0[1], st0[2] + R * 0.6, x, y + R * 0.6, c, 90, R * 0.8);
      pen.line(st0[1], st0[2] + R * 0.6, x, y + R * 0.6, HOT, 140, 2 * ps);
      for (j = 0; j < Math.max(0, Math.round(4 * dens)); j++) {
        r = L.rngFor(inst.seed, t, 451 + j);
        var ea = PI / 2 + r.uniform(-1.4, 1.4), v = r.uniform(3, 8) * ps;
        var lx = x + Math.cos(ea) * R * 0.9, ly = y + Math.sin(ea) * R * 0.9;
        pen.line(lx, ly, lx + Math.cos(ea) * v * 2, ly + Math.sin(ea) * v * 2 - 2 * ps, L.mix(HOT, c, 0.4), 220, 1.4 * ps);
      }
    }
    metOrb(pen, inst, x, y, R, c, bright, t, ps);
    return;
  }
  // 5: the blast — flash, fireball, ground shock, a pillar of light, debris
  var a = t - tb;
  if (a >= MET_BLAST_LIFE) return;
  var q = a / MET_BLAST_LIFE, e = L.easeOut3(a / 12), B = R;
  if (a < 8) pen.glow(x, y, B * (1.2 + 1.5 * a / 8), HOT, 255 * (1 - a / 8));
  var w = B * (0.9 + 0.6 * e), hgt = B * 3.2 * e;
  pen.poly([[x - w, y], [x - w * 0.45, y - hgt], [x + w * 0.45, y - hgt], [x + w, y]], c, 120 * Math.pow(1 - q, 1.5));
  pen.poly([[x - w * 0.4, y], [x - w * 0.15, y - hgt * 1.1], [x + w * 0.15, y - hgt * 1.1], [x + w * 0.4, y]], HOT, 120 * (1 - q) * (1 - q));
  pen.glow(x, y, B * (1.2 + 1.6 * L.easeOut3(q)), c, 220 * (1 - q), 0.5);
  pen.glow(x, y, B * (0.8 + 0.9 * e), L.mix(c, HOT, 0.6), 230 * (1 - q) * (1 - q));
  [[0, 1.0], [4, 1.4]].forEach(function (dk) {
    var aa = a - dk[0];
    if (aa < 0) return;
    var qq = aa / (MET_BLAST_LIFE - dk[0]), ee = L.easeOut3(qq), rr = B * (0.5 + 2.6 * ee) * dk[1];
    pen.ring(x, y, rr, rr * 0.4, 0, c, 200 * (1 - qq), 4 * ps * (1 - qq) + 0.2);
    pen.ring(x, y, rr * 0.8, rr * 0.8, 0, HOT, 130 * (1 - qq) * (1 - qq), 1.6 * ps * (1 - qq) + 0.2);
  });
  sparks(pen, inst, x, y, a, Math.max(0, Math.round(26 * dens)), 461, c, ps, [4, 11], [16, 34], 0.12, -PI / 2, PI * 0.75);
}

// ================================================================ ghost kamikaze
// The ghost's flight up to tick upto: {b, pts, vx, vy, dist, done, size, ph}.
// Stepped once per tick and kept (the path only ever grows).
function ghSim(inst, i, ps, upto) {
  var P = inst.fx.params, L = L_(), st = inst.tq_gh[i];
  if (!st) {
    var r = L.rngFor(inst.seed, i, 501), b = i * ti(P, "swing_ticks", 1), o = at(inst.tq_path, b);
    var fan = r.uniform(-1, 1) * GH_FAN * L.D, f = inst.tq_f, ca = Math.cos(fan), sa = Math.sin(fan);
    var dx = f[0] * ca - f[1] * sa, dy = f[0] * sa + f[1] * ca - 0.35, d = hyp(dx, dy) || 1;
    st = {b: b, pts: [[o[0], o[1]]], vx: dx / d * GH_OUT * ps, vy: dy / d * GH_OUT * ps, dist: 0, done: null,
          size: r.uniform(0.85, 1.15), ph: r.uniform(0, PI * 2)};
    inst.tq_gh[i] = st;
  }
  var Lr = +P.length * ps, arrive = GH_ARRIVE * +P.radius * ps * st.size, mx = ghMax(P);
  while (st.done === null && st.b + st.pts.length - 1 < upto) {
    var h = inst.tq_ki[i];
    if (h) { st.done = h[0]; break; }
    var k = st.pts.length, tick = st.b + k, last = st.pts[st.pts.length - 1], x = last[0], y = last[1];
    var tg = at(inst.tq_tp, tick), tx = tg[0], ty = tg[1], vx = st.vx, vy = st.vy;
    if (k <= GH_FLOAT) { vx = vx * GH_DRAG; vy = vy * GH_DRAG - 0.04 * ps; }
    else {
      var sp = hyp(vx, vy), ta = Math.atan2(ty - y, tx - x), an;
      if (sp < 0.5) an = ta;
      else {
        an = Math.atan2(vy, vx);
        var da = Math.atan2(Math.sin(ta - an), Math.cos(ta - an));
        an += Math.max(-GH_TURN, Math.min(GH_TURN, da));
      }
      sp = Math.min(GH_SPEED * ps, sp + GH_ACCEL * ps);
      vx = Math.cos(an) * sp; vy = Math.sin(an) * sp;
    }
    x += vx; y += vy;
    st.vx = vx; st.vy = vy;
    st.dist += hyp(vx, vy);
    st.pts.push([x, y]);
    if ((k > GH_FLOAT && hyp(x - tx, y - ty) <= arrive) || st.dist >= Lr || k >= mx) st.done = tick;
  }
  return st;
}
function ghLive(inst, ps) {   // [[index, x, y, state]] for the ghosts out this tick
  var P = inst.fx.params, t = inst.age, out = [];
  for (var i = 0; i < ghCount(P); i++) {
    var b = i * ti(P, "swing_ticks", 1);
    if (b > t) break;
    var st = ghSim(inst, i, ps, t);
    if (st.done !== null && t >= st.done) continue;
    var p = st.pts[Math.min(t - b, st.pts.length - 1)];
    out.push([i, p[0], p[1], st]);
  }
  return out;
}
function ghHit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var r0 = +inst.fx.params.radius * ps;
  return ghLive(inst, ps).some(function (g) { return hyp(g[1] - tx, g[2] - ty) <= hr + r0 * g[3].size; });
}
function ghOnHit(inst, tx, ty, ps) {
  var best = null, bd = null;
  ghLive(inst, ps).forEach(function (g) {
    var d = hyp(g[1] - tx, g[2] - ty);
    if (bd === null || d < bd) { best = g; bd = d; }
  });
  if (best) inst.tq_ki[best[0]] = [inst.age, best[1], best[2]];
}
function drawGhost(pen, inst, x, y, R, vx, vy, k, st, c, span, t) {
  var L = L_(), sp = hyp(vx, vy), bx, by, j, s;
  if (sp > 0.3) { bx = -vx / sp; by = -vy / sp; } else { bx = 0; by = 1; }
  if (by < -0.2) { by = -0.2; var n = hyp(bx, by) || 1; bx /= n; by /= n; }
  var px_ = -by, py_ = bx;
  // bob across its line of flight
  var wob = span * 0.3 * Math.sin(k * 0.33 + st.ph);
  x += px_ * wob; y += py_ * wob;
  var facing = (sp > 0.3 ? vx : inst.tq_f[0]) >= 0 ? 1 : -1, body = L.mix(GH_BODY, c, 0.12);
  pen.add(true);
  pen.glow(x, y, R * 2.4, c, 110);
  pen.add(false);
  // tail streaming behind
  var left = [], right = [];
  for (j = 0; j < 7; j++) {
    var u = j / 6, sw = Math.sin(t * 0.4 + u * 4 + st.ph) * R * 0.35 * u;
    var cx = x + bx * (R * 0.6 + u * R * 2.2) + px_ * sw, cy = y + by * (R * 0.6 + u * R * 2.2) + py_ * sw;
    var hw = R * 0.85 * Math.pow(1 - u, 0.9);
    left.push([cx + px_ * hw, cy + py_ * hw]);
    right.push([cx - px_ * hw, cy - py_ * hw]);
  }
  pen.poly(left.concat(rev(right)), body, 235);
  pen.poly(circle(x, y, R, 18), body, 245);
  // little arms
  for (s = -1; s <= 1; s += 2) {
    var ax = x + px_ * R * 0.95 * s, ay = y + py_ * R * 0.95 * s + R * 0.25;
    pen.line(ax, ay, ax + px_ * R * 0.5 * s - bx * R * 0.2, ay + py_ * R * 0.5 * s + R * 0.15, body, 235, R * 0.32);
  }
  // eyes and the grin
  var ex = x + facing * R * 0.18;
  for (s = -1; s <= 1; s += 2) pen.poly(ellipse(ex + s * R * 0.3, y - R * 0.22, R * 0.15, R * 0.26), L.BLACK, 240);
  var open = 0.25 + 0.2 * (k > GH_FLOAT ? 1 : 0) + 0.06 * Math.sin(t * 0.9 + st.ph);
  var mx = x + facing * R * 0.1, my = y + R * 0.12;
  var top = lin(PI * 0.08, PI * 0.92, 9).map(function (a) { return [mx + Math.cos(a) * R * 0.55, my + Math.sin(a) * R * 0.2]; });
  var bot = lin(PI * 0.92, PI * 0.08, 9).map(function (a) { return [mx + Math.cos(a) * R * 0.5, my + Math.sin(a) * R * (0.2 + open * 1.6)]; });
  pen.poly(top.concat(bot), L.BLACK, 240);
  pen.add(true);
}
function drawKamikaze(pen, inst, host, ps) {
  var P = inst.fx.params, t = inst.age, L = L_(), HOT = L.HOT, i, j, r;
  var cs = L.colours(inst, host), c = cs[0], deep = cs[2];
  var r0 = +P.radius * ps, B0 = +P.thickness * ps, span = +P.span * ps, dens = +P.density || 1, cad = ti(P, "swing_ticks", 1);
  var ghosts = [];
  for (i = 0; i < ghCount(P); i++) {
    var b = i * cad;
    if (b > t) break;
    ghosts.push([i, b, ghSim(inst, i, ps, t)]);
  }
  var smoke = L.mix(SMOKE, deep, 0.25);
  // 1: smoke left where they blew up (painted normally, under the light)
  pen.add(false);
  ghosts.forEach(function (g) {
    var st = g[2];
    if (st.done === null) return;
    var a = t - st.done;
    if (a < 0 || a >= GH_BLAST_LIFE + 10) return;
    var p = st.pts[Math.min(st.done - g[1], st.pts.length - 1)], B = B0 * st.size;
    for (var jj = 0; jj < Math.max(0, Math.round(3 * dens)); jj++) {
      var rr = L.rngFor(inst.seed, g[0], 520 + jj), an = rr.uniform(0, PI * 2), dr = rr.uniform(0.2, 0.8) * B * L.easeOut3(a / 14);
      var q = a / (GH_BLAST_LIFE + 10);
      pen.glow(p[0] + Math.cos(an) * dr, p[1] + Math.sin(an) * dr - rr.uniform(0.3, 0.7) * ps * a,
               B * rr.uniform(0.6, 1.0) * (0.5 + 0.8 * L.easeOut3(a / 16)), smoke, 95 * Math.pow(1 - q, 1.5) * Math.min(1, a / 3), 0.6);
    }
  });
  pen.add(true);
  ghosts.forEach(function (g) {
    var gi = g[0], b = g[1], st = g[2], k = t - b, R = r0 * st.size * (0.4 + 0.6 * L.easeOut3(k / 6));
    // 2: the puff it comes out in
    if (k < 8) pen.glow(st.pts[0][0], st.pts[0][1], (8 + 10 * k / 8) * ps, GH_BODY, 200 * (1 - k / 8));
    if (st.done === null || t < st.done) {
      // 3: the ghost in flight
      var jx = Math.min(k, st.pts.length - 1), p = st.pts[jx], pp = st.pts[Math.max(0, jx - 1)];
      drawGhost(pen, inst, p[0], p[1], R, p[0] - pp[0], p[1] - pp[1], k, st, c, span, t);
      return;
    }
    // 4: it blows up
    var a = t - st.done;
    if (a >= GH_BLAST_LIFE) return;
    var e = st.pts[Math.min(st.done - b, st.pts.length - 1)], x = e[0], y = e[1];
    var q = a / GH_BLAST_LIFE, B = B0 * st.size, ee = L.easeOut3(a / 8);
    if (a < 5) pen.glow(x, y, B * (0.8 + 0.9 * a / 5), HOT, 255 * (1 - a / 5));
    pen.glow(x, y, B * (1 + 1 * ee), c, 210 * (1 - q), 0.45);
    pen.glow(x, y, B * (0.55 + 0.45 * ee), L.mix(c, HOT, 0.6), 235 * (1 - q) * (1 - q));
    var rr = B * (0.5 + 1.7 * L.easeOut3(q));
    pen.ring(x, y, rr, rr, 0, c, 190 * (1 - q), 2.6 * ps * (1 - q) + 0.2);
    sparks(pen, inst, x, y, a, Math.max(0, Math.round(8 * dens)), 540 + gi, c, ps, [2.5, 7], [9, 18], 0.08);
  });
}

// ================================================================ serious punch
function spFrame(inst) {
  var o = at(inst.tq_path, ti(inst.fx.params, "swing_ticks", 1));
  return new (L_().Frame)(o[0], o[1], inst.tq_f, inst.tq_m);
}
function spFront(P, ps, k) { return +P.length * ps * L_().easeOut3(Math.min(1, k / ti(P, "hold_ticks", 1))); }
function spHw(P, ps, lx) { return +P.radius * ps * 2 + +P.thickness * ps * Math.pow(cl(lx / (+P.length * ps)), 0.75); }
function spHit(inst, tx, ty, hr, ps) {
  var P = inst.fx.params, t = inst.age, Tw = ti(P, "swing_ticks", 1);
  if (t < Tw || t >= inst.life) return false;
  var fr = spFrame(inst), dx = tx - fr.ox, dy = ty - fr.oy, lx = dx * fr.fx + dy * fr.fy, ly = dx * fr.vx + dy * fr.vy;
  var df = spFront(P, ps, t - Tw);
  if (lx < -hr || lx > df + hr) return false;
  return Math.abs(ly) <= spHw(P, ps, Math.max(0, Math.min(lx, df))) + hr;
}
function spikes(pen, x, y, ang, n, rOut, rIn, c, a) {
  var pts = [];
  for (var j = 0; j < 2 * n; j++) {
    var rr = j % 2 === 0 ? rOut : rIn, an = ang + PI * j / n;
    pts.push([x + Math.cos(an) * rr, y + Math.sin(an) * rr]);
  }
  pen.poly(pts, c, a);
}
function drawSerious(pen, inst, host, ps) {
  var P = inst.fx.params, t = inst.age, L = L_(), HOT = L.HOT, i, j, r, v;
  var cs = L.colours(inst, host), c = cs[0], bright = cs[1];
  var Tw = ti(P, "swing_ticks", 1), Th = ti(P, "hold_ticks", 1), rf = +P.radius * ps, Lr = +P.length * ps, dens = +P.density || 1;
  var fist;
  if (t < Tw) {
    // 1: the wind-up — stillness, air pulling in, dust lifting, a glint
    var fr0 = L.frame(inst), u = t / Tw;
    fist = fr0.w(-rf * 1.0 * L.easeOut3(u), 0);
    pen.add(true);
    for (j = 0; j < 2; j++) {
      v = frac(t / 9 + j * 0.5);
      var rr0 = rf * (1.2 + 5 * (1 - v));
      pen.ring(fist[0], fist[1], rr0, rr0, 0, L.mix(c, HOT, 0.5), 120 * u * v, 1.2 * ps);
    }
    for (i = 0; i < Math.max(0, Math.round(8 * dens)); i++) {
      r = L.rngFor(inst.seed, i, 601);
      var per = r.uniform(26, 44);
      v = frac(t / per + r());
      var px0 = inst.x + r.uniform(-60, 60) * ps, py0 = inst.y + 18 * ps - v * 40 * ps;
      pen.glow(px0, py0, 2.2 * ps, L.mix(c, HOT, 0.3), 140 * Math.sin(PI * v) * u, 0.6);
    }
    pen.glow(fist[0], fist[1], rf * 2, c, 100 * u);
    pen.glow(fist[0], fist[1], rf * 0.6, HOT, 160 * u);
    if (t >= Tw - 4) {
      var g = (t - (Tw - 4)) / 4;
      L.star(pen, fist[0], fist[1], inst.tq_f[0], inst.tq_f[1], rf * (1 + 2.5 * g), rf * (0.5 + 1.2 * g), HOT, 255, 1.2 * ps);
    }
    return;
  }
  var k = t - Tw, fr = spFrame(inst), ang = Math.atan2(inst.tq_f[1], inst.tq_f[0]), df = spFront(P, ps, k);
  var aC = k < SP_OUT + Th ? 1 : Math.max(0, 1 - (k - SP_OUT - Th) / 14);
  var aS = cl(k / (Th * 0.6 + 1)) * (k < SP_OUT + Th ? 1 : Math.max(0, 1 - (k - SP_OUT - Th) / SP_SPLIT_LIFE));
  // 2: clouds blown apart either side of the line (painted normally)
  pen.add(false);
  var nC = Math.max(0, Math.round(10 * dens));
  for (j = 0; j < nC; j++) {
    for (var s = -1; s <= 1; s += 2) {
      r = L.rngFor(inst.seed, j, 611 + (s > 0 ? 1 : 0));
      var clx = (j + 0.5) / nC * Lr * 1.4;
      if (clx > df * 1.4) continue;
      var push = (k - clx / (Lr * 1.4) * Th) * r.uniform(1.2, 2.4) * ps;
      var cly = s * (spHw(P, ps, Math.min(clx, Lr)) * 0.6 + Math.max(0, push)), cp = fr.w(clx, cly);
      pen.glow(cp[0], cp[1], r.uniform(18, 34) * ps, CLOUD, 60 * aS, 0.6);
    }
  }
  pen.add(true);
  // 3: the shock cone
  if (aC > 0 && df > 2) {
    var n = 12;
    var cone = function (m) {
      var top = [], bot = [];
      for (var jj = 0; jj <= n; jj++) {
        top.push(fr.w(df * jj / n, -spHw(P, ps, df * jj / n) * m));
        bot.push(fr.w(df * jj / n, spHw(P, ps, df * jj / n) * m));
      }
      return top.concat(rev(bot));
    };
    pen.poly(cone(1.0), c, 55 * aC);
    pen.poly(cone(0.6), bright, 70 * aC);
    pen.poly(cone(0.22), HOT, 110 * aC);
    // vapour rings left where the front passed
    for (i = 0; i < SP_RINGS; i++) {
      var ki = (i + 0.5) * Th / SP_RINGS, aa = k - ki;
      if (aa < 0 || aa >= 20) continue;
      var qq = aa / 20, rlx = spFront(P, ps, ki), hw0 = spHw(P, ps, rlx) * (1 + 0.3 * qq), rp = fr.w(rlx, 0);
      pen.ring(rp[0], rp[1], Math.max(4 * ps, hw0 * 0.18), hw0, ang, HOT, 170 * (1 - qq) * aC, 2 * ps);
    }
    // speed lines racing along it
    for (i = 0; i < Math.max(0, Math.round(18 * dens)); i++) {
      r = L.rngFor(inst.seed, i, 621);
      v = r.uniform(-1, 1);
      var sln = r.uniform(40, 120) * ps, slx = frac(k * r.uniform(0.04, 0.08) + r()) * df, sly = v * spHw(P, ps, slx) * 0.9;
      var a0 = fr.w(Math.max(0, slx - sln), sly), a1 = fr.w(slx, sly);
      pen.line(a0[0], a0[1], a1[0], a1[1], L.mix(c, HOT, 0.6), 200 * aC, 1.3 * ps);
    }
    // the shock front
    if (k < SP_OUT + Th + 8) {
      var aF = k < SP_OUT + Th ? 1 : 1 - (k - SP_OUT - Th) / 8, fp = fr.w(df, 0), hw = spHw(P, ps, df);
      var rx = Math.max(6 * ps, +P.thickness * ps * 0.12 * df / Lr + rf);
      pen.ring(fp[0], fp[1], rx, hw, ang, c, 120 * aF, 9 * ps);
      pen.ring(fp[0], fp[1], rx, hw, ang, HOT, 230 * aF, 4 * ps);
    }
  }
  // 4: the sky split along its line, reaching past the blast
  if (aS > 0) {
    var end = Math.min(Lr * 1.6, df * 1.6), s0 = fr.w(0, 0), s1 = fr.w(end, 0);
    pen.line(s0[0], s0[1], s1[0], s1[1], c, 70 * aS, 10 * ps);
    pen.line(s0[0], s0[1], s1[0], s1[1], HOT, 230 * aS, 2.6 * ps);
    for (var sd = -1; sd <= 1; sd += 2) {
      var b0 = fr.w(end * 0.1, sd * 6 * ps), b1 = fr.w(end * 0.85, sd * 6 * ps);
      pen.line(b0[0], b0[1], b1[0], b1[1], HOT, 90 * aS, 1 * ps);
    }
    pen.glow(s1[0], s1[1], 24 * ps, HOT, 160 * aS);
  }
  // 5: the fist and its flash
  var lf = rf * 3 * L.easeOut3(Math.min(1, k / SP_OUT));
  fist = fr.w(lf, 0);
  if (aC > 0) {
    pen.glow(fist[0], fist[1], rf * 2.4, c, 170 * aC);
    pen.glow(fist[0], fist[1], rf * 0.8, HOT, 255 * aC, 0.7);
  }
  if (k < SP_FLASH) {
    var q = k / SP_FLASH, e = L.easeOut3(q);
    pen.glow(fist[0], fist[1], (30 + 60 * e) * ps, HOT, 255 * (1 - q));
    spikes(pen, fist[0], fist[1], ang, 10, (20 + 50 * e) * ps, (7 + 10 * e) * ps, HOT, 240 * (1 - q));
  }
  sparks(pen, inst, fist[0], fist[1], k, Math.max(0, Math.round(16 * dens)), 631, c, ps, [5, 12], [12, 22], 0.05, ang, PI * 0.35);
}

// ================================================================ black hole
function bhK(P, t) {   // core size (0-1) at tick t
  var L = L_(), Tf = ti(P, "swing_ticks", 1), Th = ti(P, "hold_ticks", 1);
  if (t < Tf) return L.easeOut3(t / Tf);
  if (t < Tf + Th) return 1;
  if (t < Tf + Th + BH_COLLAPSE) return 1 - L.easeIn3((t - Tf - Th) / BH_COLLAPSE);
  return 0;
}
function bhHit(inst, tx, ty, hr, ps) {
  var P = inst.fx.params, t = inst.age;
  if (t >= inst.life) return false;
  var c0 = inst.tq_tp[0], d = hyp(tx - c0[0], ty - c0[1]);
  var tb = ti(P, "swing_ticks", 1) + ti(P, "hold_ticks", 1) + BH_COLLAPSE;
  if (t >= tb) return d <= hr + +P.radius * ps * 4;
  return d <= hr + +P.radius * ps * bhK(P, t) * 1.8;
}
function bhDisc(pen, cx, cy, Rc, Wd, c, k, t, front, ps) {
  var L = L_(), a0 = front ? 0 : PI, a1 = front ? PI : 2 * PI, inner = Rc * 1.35, j, i;
  for (j = 0; j < 5; j++) {
    var rr = inner + Wd * j / 4;
    arc(pen, cx, cy, rr, rr * BH_SQ, BH_TILT, a0, a1, L.mix(c, L.HOT, 0.6 - j * 0.12), (160 - 25 * j) * k, Wd / 4 * 1.2 + 0.5 * ps, 20);
  }
  for (i = 0; i < BH_CLUMPS; i++) {
    var u = (i % 5) / 4, cr = inner + Wd * u;
    var an = (i * 2.4 + t * 0.09 * inner / Math.max(cr, 1e-6)) % (2 * PI);
    if ((an < PI) !== front) continue;
    var px = Math.cos(an) * cr, py = Math.sin(an) * cr * BH_SQ, ca = Math.cos(BH_TILT), sa = Math.sin(BH_TILT);
    pen.glow(cx + px * ca - py * sa, cy + px * sa + py * ca, Wd * 0.45 + 2 * ps, L.mix(c, L.HOT, 0.7), 200 * k);
  }
}
function drawBlackhole(pen, inst, host, ps) {
  var P = inst.fx.params, t = inst.age, L = L_(), HOT = L.HOT, i, r;
  var cs = L.colours(inst, host), c = cs[0], bright = cs[1];
  var Tf = ti(P, "swing_ticks", 1), Th = ti(P, "hold_ticks", 1), k = bhK(P, t);
  var R0 = +P.radius * ps, Rc = R0 * k * (1 + 0.04 * Math.sin(t * 0.7)), Wd = +P.thickness * ps * k, Lp = +P.length * ps;
  var dens = +P.density || 1, cx = inst.tq_tp[0][0], cy = inst.tq_tp[0][1], end = Tf + Th + BH_COLLAPSE;
  pen.add(true);
  if (k > 0) {
    // 1: haze over the whole pull radius
    pen.glow(cx, cy, Lp * 0.55 * k, c, 50 * k, 0.5);
    // 2: debris spiralling in
    for (i = 0; i < Math.max(0, Math.round(26 * dens)); i++) {
      r = L.rngFor(inst.seed, i, 701);
      var per = r.uniform(26, 50), off = r(), u = frac(t / per + off), cyc = Math.floor(t / per + off);
      var r2 = L.rngFor(inst.seed, i * 131 + cyc, 702), rad0 = r2.uniform(0.45, 1.0) * Lp, a0 = r2.uniform(0, PI * 2);
      var pos = function (uu) {
        var rad = Rc * 1.1 + (rad0 - Rc * 1.1) * Math.pow(1 - uu, 1.6), an = a0 + 5 * Math.pow(uu, 1.4);
        var px = Math.cos(an) * rad, py = Math.sin(an) * rad * 0.55, ca = Math.cos(BH_TILT), sa = Math.sin(BH_TILT);
        return [cx + px * ca - py * sa, cy + px * sa + py * ca];
      };
      var p1 = pos(u), p0 = pos(Math.max(0, u - 0.04));
      pen.line(p0[0], p0[1], p1[0], p1[1], L.mix(c, HOT, u), 220 * Math.sin(PI * u) * k, 1.4 * ps);
    }
    // 3: energy drawn in while it forms / collapses
    if (t < Tf || t >= Tf + Th) {
      var g = t < Tf ? 1 - t / Tf : (t - Tf - Th) / BH_COLLAPSE;
      for (i = 0; i < 12; i++) {
        r = L.rngFor(inst.seed, i, 711);
        var an = r.uniform(0, PI * 2), uu = frac(t / 8 + r()), r1 = R0 * (1.2 + 5 * (1 - uu)), rr2 = R0 * (1.2 + 5 * Math.max(0, 1 - uu - 0.2));
        pen.line(cx + Math.cos(an) * r1, cy + Math.sin(an) * r1, cx + Math.cos(an) * rr2, cy + Math.sin(an) * rr2,
                 HOT, 200 * g * Math.sin(PI * uu), 1.3 * ps);
      }
    }
    // 4: back half of the disc, behind the core
    bhDisc(pen, cx, cy, Rc, Wd, c, k, t, false, ps);
    // 5: the event horizon (painted normally: black)
    pen.add(false);
    pen.glow(cx, cy, Rc * 1.3, L.BLACK, 200 * k, 0.75);
    pen.poly(circle(cx, cy, Rc, 28), L.BLACK, 255 * Math.min(1, k * 1.5));
    pen.add(true);
    // 6: photon ring, the lensed arc of the disc round it
    pen.ring(cx, cy, Rc * 1.1, Rc * 1.1, 0, c, 140 * k, 3.5 * ps);
    pen.ring(cx, cy, Rc * 1.04, Rc * 1.04, 0, HOT, 200 * k, 1.6 * ps);
    pen.ring(cx, cy, Rc * 1.35 + Wd * 0.5, Rc * 1.3, BH_TILT, c, 70 * k, 2.5 * ps);
    // 7: front half of the disc
    bhDisc(pen, cx, cy, Rc, Wd, c, k, t, true, ps);
    // 8: Einstein ring
    var er = Rc * 2.2 * (1 + 0.03 * Math.sin(t * 0.21));
    pen.ring(cx, cy, er, er, 0, bright, 40 * k, 1.2 * ps);
  }
  // 9: the collapse bursts
  var a = t - end;
  if (a >= 0 && a < BH_BURST_LIFE) {
    var q = a / BH_BURST_LIFE;
    if (a < 6) pen.glow(cx, cy, R0 * (1.5 + 3 * a / 6), HOT, 255 * (1 - a / 6));
    var rr = R0 * (1 + 6 * L.easeOut3(q));
    pen.ring(cx, cy, rr, rr, 0, c, 220 * (1 - q), 4 * ps * (1 - q) + 0.2);
    pen.ring(cx, cy, rr * 0.75, rr * 0.75 * BH_SQ * 2, BH_TILT, HOT, 160 * (1 - q) * (1 - q), 2 * ps * (1 - q) + 0.2);
    pen.glow(cx, cy, R0 * 3 * (1 - q), c, 160 * (1 - q));
    sparks(pen, inst, cx, cy, a, Math.max(0, Math.round(20 * dens)), 721, c, ps, [4, 10], [14, 28], 0);
  }
}

// ================================================================ public
function hit(inst, tx, ty, hr, ps) {
  var st = L_().style(inst.fx.params);
  if (st === "ssj_aura") return auraHit(inst, tx, ty, hr, ps);
  if (st === "rasen_shuriken") return rsHit(inst, tx, ty, hr, ps);
  if (st === "gigantic_meteor") return metHit(inst, tx, ty, hr, ps);
  if (st === "ghost_kamikaze") return ghHit(inst, tx, ty, hr, ps);
  if (st === "serious_punch") return spHit(inst, tx, ty, hr, ps);
  return bhHit(inst, tx, ty, hr, ps);
}
function body() { return null; }   // none of these clash as a blade
function onHit(inst, x, y, ps) {
  var st = L_().style(inst.fx.params);
  if (st === "rasen_shuriken") rsOnHit(inst, ps);
  else if (st === "ghost_kamikaze") ghOnHit(inst, x, y, ps);
}
function draw(pen, inst, host, ps) {
  var st = L_().style(inst.fx.params);
  if (st === "ssj_aura") drawAura(pen, inst, host, ps);
  else if (st === "rasen_shuriken") drawRasen(pen, inst, host, ps);
  else if (st === "gigantic_meteor") drawMeteor(pen, inst, host, ps);
  else if (st === "ghost_kamikaze") drawKamikaze(pen, inst, host, ps);
  else if (st === "serious_punch") drawSerious(pen, inst, host, ps);
  else drawBlackhole(pen, inst, host, ps);
}

G.POWERFX = {STYLES: STYLES, PULL_STYLES: PULL_STYLES, AURA_N: AURA_N, outlineFromAlpha: outlineFromAlpha, activeTicks: activeTicks, totalTicks: totalTicks, onSpawn: onSpawn,
             hit: hit, body: body, onHit: onHit, draw: draw};
})(window);
