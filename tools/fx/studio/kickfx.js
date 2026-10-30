/* Kicks — FX Studio's port of laser/kickfx.py: the roundhouse, thrust, axe,
 * spinning and rising kicks of the FX Kit "technique" primitive.  Same
 * timeline, same random streams (FXK.rng), same geometry and painting order
 * as the game, so the Studio preview draws what Solo and Battle draw.  Keep
 * the two in step.  Builds on swordfx.js (frame, pen, maths) and strikefx.js
 * (the punch's impact, impact frame and hit options): load it after both.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };
var K_ = function () { return G.STRIKEFX; };
var STYLES = ["roundhouse_kick", "thrust_kick", "axe_kick", "spinning_kick", "rising_kick"];
var ARC_STYLES = ["roundhouse_kick", "axe_kick", "rising_kick"];

var WIND = 3, RETRACT = 6, TRAIL_LAG = 3, TRAIL_N = 24, FEET_DROP = 30, RISE_REACH = 0.9;
var DUST = [150, 138, 120], ROCK = [96, 84, 72], SCORCH = [40, 30, 28];
// When in the kick (fraction of Swing ticks) the foot meets the aim.
var CONTACT = {roundhouse_kick: 0.5, thrust_kick: 1, axe_kick: 1, spinning_kick: 1, rising_kick: 0.55};
// How much bigger than the punch's its impact is.
var HEAVY = {roundhouse_kick: 1.15, thrust_kick: 1.3, axe_kick: 1.3, spinning_kick: 1, rising_kick: 1.1};
var IMPACT_LIFE = 24;   // strikefx PUNCH_IMPACT_LIFE

// ---------------------------------------------------------------- timeline
function hold(P) { return Math.max(0, Math.trunc(+P.hold_ticks || 0)); }
function activeTicks(P) { return WIND + L_().swing(P) + hold(P) + 1; }
function totalTicks(P) { return WIND + L_().swing(P) + hold(P) + RETRACT + IMPACT_LIFE; }
// The tick the foot meets the aim (a whiff bursts there).
function contactTick(P) { return WIND + Math.round(L_().swing(P) * CONTACT[L_().style(P)]); }
// Time fraction of the kick at the contact tick (whole ticks).
function uc(P) { return (contactTick(P) - WIND) / L_().swing(P); }
// How far along its path the foot is at time fraction u of the kick.
function prog(st, u) {
  var L = L_();
  if (st === "thrust_kick") return L.easeOut3(u);
  if (st === "axe_kick") return L.easeIn3(u);
  return L.easeInOut3(u);
}

// ---------------------------------------------------------------- geometry
function unit(x, y) { var n = Math.hypot(x, y) || 1; return [x / n, y / n]; }
// The way the foot moves when it meets the aim (axe / rising).
function contactDir(inst, P, st) {
  var f = inst.tq_f, m = inst.tq_m, ang = (+P.kick_angle_deg || 0) * m, mode;
  if (st === "axe_kick") {
    mode = P.axe_dir || "screen_down";
    if (mode === "along_aim") return f;
    if (mode === "custom") return FXK().rot(f, ang);
    return [0, 1];
  }
  mode = P.rise_dir || "screen_up";
  if (mode === "straight_up") return [0, -1];
  if (mode === "perpendicular") {
    var vx = -f[1] * m, vy = f[0] * m;
    return vy > 0 ? [-vx, -vy] : [vx, vy];
  }
  if (mode === "custom") return FXK().rot(f, ang);
  return unit(f[0] * 0.5, -1);
}
// [pivot x, y, radius, angle at contact, turn sign] of an arc kick.
function arc(inst, P, st, ps) {
  var L = +P.length * ps, f = inst.tq_f, m = inst.tq_m, ax = inst.x, ay = inst.y;
  if (st === "roundhouse_kick") return [ax, ay, L, Math.atan2(f[1], f[0]), (P.kick_sweep || "high_low") !== "low_high" ? m : -m];
  var axe = st === "axe_kick", reach = axe ? L : L * RISE_REACH;
  var cx = ax + f[0] * reach, cy = ay + f[1] * reach, d = contactDir(inst, P, st);
  var back = (+P.span || 0) * L_().D * prog(st, uc(P)), best = null;
  // The circle through the contact point whose tangent there is d: the axe
  // kick on the side where it starts higher (it comes down onto the point),
  // then (and the rising kick only) the side whose pivot is nearer the hip;
  // a tie: the facing's.
  [m, -m].forEach(function (s) {
    var rx = s * d[1], ry = -s * d[0], ox = cx - L * rx, oy = cy - L * ry, ac = Math.atan2(ry, rx);
    var y0 = oy + Math.sin(ac - s * back) * L;
    var k = [axe ? y0 : 0, (ox - ax) * (ox - ax) + (oy - ay) * (oy - ay)];
    if (best === null || k[0] < best[0][0] - 1e-6 || (Math.abs(k[0] - best[0][0]) <= 1e-6 && k[1] < best[0][1] - 1e-6))
      best = [k, ox, oy, ac, s];
  });
  return [best[1], best[2], L, best[3], best[4]];
}
// [foot x, y, pivot x, y, unit tangent x, y] at tick t (may be fractional):
// where the foot is, what it turns round, and which way it moves.
function pose(inst, t, ps) {
  var Lb = L_(), P = inst.fx.params, st = Lb.style(P), Ts = Lb.swing(P), Th = hold(P);
  var u = Math.min(1, Math.max(0, (t - WIND) / Ts)), f = inst.tq_f, ax = inst.x, ay = inst.y, L = +P.length * ps;
  if (st === "thrust_kick") {
    var r = L * prog(st, u), k = t - WIND - Ts - Th;
    if (k > 0) r = L * (1 - Lb.easeIn3(Math.min(1, k / RETRACT)));
    return [ax + f[0] * r, ay + f[1] * r, ax, ay, f[0], f[1]];
  }
  var p = prog(st, u), ox, oy, s, a;
  if (st === "spinning_kick") {
    var mode = P.spin_mode || "centered", g;
    if (mode === "travel") g = 1.2 * p;
    else if (mode === "lunge") g = 0.6 * Lb.easeOut3(Math.min(1, Math.max(0, (u - 0.7) / 0.3)));
    else g = 0;
    ox = ax + f[0] * L * g; oy = ay + f[1] * L * g;
    s = inst.tq_m;
    var turns = Math.max(0, +P.spin_turns || 0);
    a = Math.atan2(f[1], f[0]) - s * 2 * Math.PI * turns * (1 - p);
  } else {
    var A = arc(inst, P, st, ps);
    ox = A[0]; oy = A[1]; L = A[2]; s = A[4];
    a = A[3] + s * (+P.span || 0) * Lb.D * (p - prog(st, uc(P)));
  }
  var ca = Math.cos(a), sa = Math.sin(a);
  return [ox + ca * L, oy + sa * L, ox, oy, -sa * s, ca * s];
}
// [x0, y0, x1, y1, half width] of the lower leg while it is out.
function leg(inst, t, ps) {
  var P = inst.fx.params;
  if (t < WIND) return null;
  var q = pose(inst, t, ps), x = q[0], y = q[1], ox = q[2], oy = q[3];
  var w = +P.radius * ps * 1.2 + +P.thickness * ps * 0.3;
  if (L_().style(P) === "thrust_kick") return Math.hypot(x - ox, y - oy) <= 2 ? null : [ox, oy, x, y, w];
  return [ox + (x - ox) * 0.35, oy + (y - oy) * 0.35, x, y, w];
}

// ---------------------------------------------------------------- hits
function hit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var g = leg(inst, inst.age, ps);
  return g !== null && FXK().segDist(tx, ty, g[0], g[1], g[2], g[3]) <= hr + g[4];
}
// A kick clashes along the lower leg while it is out.
function body(inst, ps) {
  if (inst.age >= inst.life) return null;
  var g = leg(inst, inst.age, ps);
  return g === null ? null : [[[g[0], g[1]], [g[2], g[3]]], g[4]];
}
// The impact stays where the foot landed, laid along its motion.
function onHit(inst, x, y, ps) {
  var q = pose(inst, inst.age, ps);
  inst.tq_imp.push([inst.age, q[0], q[1], q[4], q[5]]);
}
// Knockback direction (params kb_dir): aim, tangent (the way the foot moves
// now) or custom (kb_angle_deg turned from that).
function hitDir(inst) {
  var P = inst.fx.params, mode = P.kb_dir || "aim";
  if (mode !== "tangent" && mode !== "custom") return inst.dir;
  var q = pose(inst, inst.age, inst.ps || 1), u = [q[4], q[5]];
  if (mode === "tangent") return u;
  return FXK().rot(u, (+P.kb_angle_deg || 0) * inst.tq_m);
}
// No opponent (Solo; the Studio with every dummy down): the kick freezes as its whiff bursts.
function hitstopStep(inst, host) {
  var P = inst.fx.params;
  if (!host || STYLES.indexOf(L_().style(P)) < 0 || !P.hitstop || !host.solo) return;
  if (!inst.tq_imp.length && inst.age + 1 === contactTick(P)) K_().freeze(inst, host);
}

// ================================================================ drawing
// [age, x, y, ux, uy, size, salt, tick] of every impact on show: where the
// foot landed; a whiff bursts smaller where it met the aim.
function impacts(inst, P, ps) {
  var t = inst.age;
  if (inst.tq_imp.length) return inst.tq_imp.map(function (h, n) { return [t - h[0], h[1], h[2], h[3], h[4], 1, 11 * n, h[0]]; });
  var tc = contactTick(P), q = pose(inst, tc, ps);
  return [[t - tc, q[0], q[1], q[4], q[5], 0.55, 0, tc]];
}
function ellipse(x, y, rx, ry, n) {
  n = n || 20;
  var pts = [];
  for (var i = 0; i < n; i++) pts.push([x + Math.cos(i * 2 * Math.PI / n) * rx, y + Math.sin(i * 2 * Math.PI / n) * ry]);
  return pts;
}
// A glint where the kick starts, drawing in.
function windup(pen, inst, P, t, ps, c) {
  var q = pose(inst, WIND, ps), rf = +P.radius * ps, e = t / WIND;
  pen.glow(q[0], q[1], rf * (0.8 + 1.2 * e), c, 120 + 100 * e);
  pen.ring(q[0], q[1], rf * (3 - 2 * e), rf * (3 - 2 * e), 0, L_().HOT, 150 * e, 1.2 * ps);
}
// The crescent trail: widest at the foot, tapering back along its path,
// growing in toward the pivot (a thrust: both sides of its line).
function trail(pen, inst, P, t, ps, c, bright, fade) {
  var Lb = L_(), W = +P.thickness * ps, thrust = Lb.style(P) === "thrust_kick";
  var out = [], inn = [], cout = [], cinn = [], side = [], k;
  for (k = 0; k <= TRAIL_N; k++) {
    var q = k / TRAIL_N, p = pose(inst, t - TRAIL_LAG * q, ps), x = p[0], y = p[1], rx, ry, o_, i_;
    if (thrust) { rx = -p[5]; ry = p[4]; o_ = 0.8; i_ = 0.8; }
    else { var r = unit(x - p[2], y - p[3]); rx = r[0]; ry = r[1]; o_ = 0.35; i_ = 1; }
    var w = W * Math.pow(1 - q, 0.8);
    out.push([x + rx * w * o_, y + ry * w * o_]);
    inn.push([x - rx * w * i_, y - ry * w * i_]);
    cout.push([x + rx * w * o_ * 0.35, y + ry * w * o_ * 0.35]);
    cinn.push([x - rx * w * i_ * 0.45, y - ry * w * i_ * 0.45]);
    side.push([x, y, rx, ry]);
  }
  pen.poly(out.concat(inn.slice().reverse()), c, 110 * fade);
  pen.poly(cout.concat(cinn.slice().reverse()), bright, 170 * fade);
  // speed lines along it while it moves
  if (t <= WIND + Lb.swing(P) + 1) {
    for (var j = 0; j < 3; j++) {
      var rg = Lb.rngFor(inst.seed, j, 151), off = rg.uniform(-1.4, 0.6) * W, k0 = Math.trunc(rg.uniform(0, 4));
      var pts = side.slice(k0).map(function (sd) { return [sd[0] + sd[2] * off, sd[1] + sd[3] * off]; });
      pen.polyline(pts, Lb.mix(c, Lb.HOT, 0.4), 160 * fade, 1.2 * ps);
    }
  }
}
function foot(pen, inst, P, t, ps, c, fade) {
  var Lb = L_(), rf = +P.radius * ps;
  [[2, 60], [1, 100]].forEach(function (ja) {
    var g = pose(inst, Math.max(WIND, t - ja[0]), ps);
    pen.glow(g[0], g[1], rf * 1.8, c, ja[1] * fade);
  });
  var q = pose(inst, t, ps);
  pen.glow(q[0], q[1], rf * 2.6, c, 170 * fade);
  pen.glow(q[0], q[1], rf * 1.4, Lb.mix(c, Lb.HOT, 0.6), 235 * fade);
  pen.glow(q[0], q[1], rf * 0.7, Lb.HOT, 255 * fade, 0.7);
}
// Three arcs of an ellipse, turned by rot.
function swirl(pen, x, y, rx, ry, rot, c, a, w) {
  for (var i = 0; i < 3; i++) {
    var s0 = rot + i * 2 * Math.PI / 3, pts = [];
    for (var k = 0; k < 9; k++) pts.push([x + Math.cos(s0 + 1.2 * k / 8) * rx, y + Math.sin(s0 + 1.2 * k / 8) * ry]);
    pen.polyline(pts, c, a, w);
  }
}
// Spinning kick: a wind vortex round the body, turning with the kick.
function vortex(pen, inst, P, t, ps, c, fade) {
  var Lb = L_(), q = pose(inst, t, ps), ox = q[2], oy = q[3], L = +P.length * ps, s = inst.tq_m;
  for (var j = 0; j < 3; j++) {
    var rx = L * (0.8 + 0.25 * j);
    swirl(pen, ox, oy + L * 0.15 * (j - 1), rx, rx * 0.32, s * (t * 0.55 + j * 1.3), Lb.mix(c, Lb.HOT, 0.3),
      (150 - 30 * j) * fade, (1.8 - 0.4 * j) * ps);
  }
}
// Rising kick: dust kicked up where it starts.
function kickup(pen, inst, P, t, ps) {
  var Lb = L_(), a = t - WIND;
  if (a < 0 || a >= 18) return;
  var p = pose(inst, WIND, ps), q = a / 18, n = Math.max(0, Math.round(5 * (+P.density || 1)));
  for (var j = 0; j < n; j++) {
    var r = Lb.rngFor(inst.seed, j, 161), dx = r.uniform(-1, 1) * 14 * ps * q, dy = -r.uniform(0.6, 1.4) * 22 * ps * Lb.easeOut3(q);
    pen.glow(p[0] + dx, p[1] + dy, (6 + 10 * q) * ps * r.uniform(0.7, 1.3), DUST, 110 * (1 - q), 0.6);
  }
}
// Dust thrown out round the impact (normal blending).
function dust(pen, inst, ps, x, y, a, sc, salt) {
  var Lb = L_(), n = Math.max(0, Math.round(6 * (+inst.fx.params.density || 1) * sc));
  for (var j = 0; j < n; j++) {
    var r = Lb.rngFor(inst.seed, j, 170 + salt), life = 20 + 10 * r();
    if (a >= life) continue;
    var q = a / life, an = r.uniform(0, Math.PI * 2), d = r.uniform(0.8, 2.2) * ps * Lb.dragDist(0.9, a);
    var rad = (5 + 10 * Lb.easeOut3(q)) * ps * sc * r.uniform(0.7, 1.3);
    pen.glow(x + Math.cos(an) * d, y + Math.sin(an) * d * 0.6, rad, DUST, 90 * (1 - q), 0.6);
  }
}
// Axe kick: a scorched crater, cracks running along the ground, debris
// thrown up and a ground shock ring (laid flat).
function crater(pen, inst, c, ps, x, y, a, sc, salt) {
  var Lb = L_(), q = a / IMPACT_LIFE, e = Lb.easeOut3(Math.min(1, a / 8)), R = (22 + 26 * e) * ps * sc, j, r;
  pen.poly(ellipse(x, y, R, R * 0.32), SCORCH, 140 * (1 - q));
  pen.ring(x, y, R, R * 0.32, 0, DUST, 200 * (1 - q), 2 * ps);
  for (j = 0; j < 7; j++) {
    r = Lb.rngFor(inst.seed, j, 180 + salt);
    var an = (j % 2 === 0 ? 0 : Math.PI) + r.uniform(-0.35, 0.35), ln = (20 + 60 * e) * ps * sc * r.uniform(0.6, 1.2), pts = [[x, y]];
    for (var k = 1; k < 5; k++) {
      var d = ln * k / 4, jit = r.uniform(-0.5, 0.5) * 6 * ps;
      pts.push([x + Math.cos(an) * d, y + Math.sin(an) * d * 0.4 + jit]);
    }
    pen.polyline(pts, K_().INK, 200 * (1 - q), 1.6 * ps);
  }
  var n = Math.max(0, Math.round(8 * (+inst.fx.params.density || 1)));
  for (j = 0; j < n; j++) {
    r = Lb.rngFor(inst.seed, j, 190 + salt);
    var vx = r.uniform(-3, 3) * ps, vy = -r.uniform(3, 7) * ps, rx_ = x + vx * a, ry_ = y + vy * a + 0.225 * ps * a * a;
    if (ry_ > y + 4 * ps) continue;
    var sz = r.uniform(2, 4) * ps;
    pen.poly([[rx_ - sz, ry_], [rx_, ry_ - sz], [rx_ + sz, ry_], [rx_, ry_ + sz * 0.7]], ROCK, 230 * (1 - q));
  }
  pen.add(true);
  pen.ring(x, y, (10 + 70 * e) * ps * sc, (3 + 20 * e) * ps * sc, 0, c, 200 * (1 - q), 2.5 * ps * (1 - q) + 0.2);
  pen.add(false);
}
// Where the axe kick's crater goes: the contact point, or under the target's
// feet (where the target was on tick b).
function craterAt(inst, P, ps, x, y, b) {
  if ((P.axe_crater || "contact") !== "feet") return [x, y];
  var tp = inst.tq_tp[Math.min(Math.max(0, b), inst.tq_tp.length - 1)];
  return [+tp[0], +tp[1] + FEET_DROP * ps];
}

function draw(pen, inst, host, ps) {
  var Lb = L_(), P = inst.fx.params, st = Lb.style(P), t = inst.age;
  var cs = Lb.colours(inst, host), c = cs[0], bright = cs[1], Ts = Lb.swing(P), Th = hold(P);
  var imps = impacts(inst, P, ps);
  // 0: the impact frame, under everything else
  imps.forEach(function (m) { K_().impactFrame(pen, inst, c, ps, m[1], m[2], m[0], m[5], m[6]); });
  pen.add(true);
  if (t < WIND) windup(pen, inst, P, t, ps, c);
  else if (t < WIND + Ts + Th + RETRACT) {
    var fade = t < WIND + Ts + Th ? 1 : 1 - (t - WIND - Ts - Th) / RETRACT;
    if (st === "spinning_kick") vortex(pen, inst, P, t, ps, c, fade);
    trail(pen, inst, P, t, ps, c, bright, fade);
    foot(pen, inst, P, t, ps, c, fade);
  }
  if (st === "rising_kick") { pen.add(false); kickup(pen, inst, P, t, ps); pen.add(true); }
  // the impacts: ground and dust first (normal blending), then the punch's
  // impact laid along the foot's motion, heavier
  var hv = HEAVY[st];
  imps.forEach(function (m) {
    var a = m[0];
    if (!(a >= 0 && a < IMPACT_LIFE)) return;
    pen.add(false);
    if (st === "axe_kick") { var g = craterAt(inst, P, ps, m[1], m[2], m[7]); crater(pen, inst, c, ps, g[0], g[1], a, m[5] * hv, m[6]); }
    dust(pen, inst, ps, m[1], m[2], a, m[5] * hv, m[6]);
    pen.add(true);
    K_().impact(pen, inst, c, ps, m[1], m[2], a, m[5] * hv, m[6], [m[3], m[4]]);
  });
}

G.KICKFX = {STYLES: STYLES, ARC_STYLES: ARC_STYLES, draw: draw, hit: hit, body: body, onHit: onHit, hitDir: hitDir, hitstopStep: hitstopStep,
              activeTicks: activeTicks, totalTicks: totalTicks, contactTick: contactTick, pose: pose};
})(window);
