/* Kicks — FX Studio's port of laser/kickfx.py: the roundhouse, thrust, axe,
 * spinning and rising kicks of the FX Kit "technique" primitive.  Same
 * timeline, same random streams (FXK.rng), same geometry and painting order
 * as the game, so the Studio preview draws what Solo and Battle draw.  Keep
 * the two in step.  Builds on swordfx.js (frame, pen, maths), hitfx.js (what
 * a kick paints: its motion, impact and environment partitions) and
 * strikefx.js (impact frame, hit options): load it after all three.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };
var K_ = function () { return G.STRIKEFX; };
var H_ = function () { return G.HITFX; };
var STYLES = ["roundhouse_kick", "thrust_kick", "axe_kick", "spinning_kick", "rising_kick"];
var ARC_STYLES = ["roundhouse_kick", "axe_kick", "rising_kick"];

var WIND = 3, RETRACT = 6, FEET_DROP = 30, RISE_REACH = 0.9;   // FEET_DROP: hitfx FEET_DROP
// When in the kick (fraction of Swing ticks) the foot meets the aim.
var CONTACT = {roundhouse_kick: 0.5, thrust_kick: 1, axe_kick: 1, spinning_kick: 1, rising_kick: 0.55};
// How much bigger than the punch's its impact is.
var HEAVY = {roundhouse_kick: 1.15, thrust_kick: 1.3, axe_kick: 1.3, spinning_kick: 1, rising_kick: 1.1};
var IMPACT_LIFE = 24;   // hitfx IMPACT_LIFE

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
// pose() mirrored in place by the animation flips (flip_h / flip_v,
// STRIKEFX.flips): flip_v across the aim line through the anchor, flip_h
// across the line square to the aim through the contact point.
function pose(inst, t, ps) {
  var q = poseRaw(inst, t, ps), fl = K_().flips(inst.fx.params), h = fl[0], v = fl[1];
  if (h > 0 && v > 0) return q;
  var f = inst.tq_f, ax = inst.x, ay = inst.y, c = 0;
  if (h < 0) {
    var cq = poseRaw(inst, contactTick(inst.fx.params), ps);
    c = (cq[0] - ax) * f[0] + (cq[1] - ay) * f[1];
  }
  function pt(x, y) {
    var dx = x - ax, dy = y - ay, u = dx * f[0] + dy * f[1], w = dy * f[0] - dx * f[1];
    if (h < 0) u = 2 * c - u;
    w *= v;
    return [ax + u * f[0] - w * f[1], ay + u * f[1] + w * f[0]];
  }
  var u = (q[4] * f[0] + q[5] * f[1]) * h, w = (q[5] * f[0] - q[4] * f[1]) * v;
  var a = pt(q[0], q[1]), o = pt(q[2], q[3]);
  return [a[0], a[1], o[0], o[1], u * f[0] - w * f[1], u * f[1] + w * f[0]];
}
// pose() before the animation flips.
function poseRaw(inst, t, ps) {
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
  if (st === "spinning_kick" && P.spin_vertical) {
    // vertical spin: the foot swings up <-> down (screen x squashed), then opens
    // back to the full circle over the last 20% so it lands on the aim
    var kx = 0.3 + 0.7 * Lb.easeOut3(Math.min(1, Math.max(0, (p - 0.8) / 0.2)));
    var tx = -sa * s * kx, ty = ca * s, n = Math.hypot(tx, ty) || 1;
    return [ox + ca * L * kx, oy + sa * L, ox, oy, tx / n, ty / n];
  }
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
  var fl = K_().flips(P);
  return FXK().rot(u, (+P.kb_angle_deg || 0) * inst.tq_m * fl[0] * fl[1]);
}
// No opponent (Solo; the Studio with every dummy down): the kick's hit weight
// (hit-stop, shake) plays as its whiff bursts.
function hitstopStep(inst, host) {
  var P = inst.fx.params;
  if (!host || STYLES.indexOf(L_().style(P)) < 0 || !(P.hitstop || P.shake) || !host.solo) return;
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
// The kick for the motion partition (HITFX.Motion): knee -> foot (a thrust:
// hip -> foot), moving the way the foot moves.
function kickMotion(inst, P, ps) {
  var thrust = L_().style(P) === "thrust_kick", Ts = L_().swing(P), Th = hold(P), Motion = H_().Motion;
  var limb = function (t) {
    var q = pose(inst, t, ps), x = q[0], y = q[1], ox = q[2], oy = q[3];
    if (thrust) return [ox, oy, x, y, q[4], q[5]];
    return [ox + (x - ox) * 0.35, oy + (y - oy) * 0.35, x, y, q[4], q[5]];
  };
  return new Motion(limb, WIND, contactTick(P), WIND + Ts, WIND + Ts + Th + RETRACT, +P.radius * ps, +P.thickness * ps);
}
// Where the target's feet were on tick b.
function feet(inst, b, ps) {
  var tp = inst.tq_tp[Math.min(Math.max(0, b), inst.tq_tp.length - 1)];
  return +tp[1] + FEET_DROP * ps;
}
// Where the axe kick's crater goes: the contact point, or under the target's
// feet (where the target was on tick b).
function craterAt(inst, P, ps, x, y, b) {
  if ((P.axe_crater || "contact") !== "feet") return [x, y];
  var tp = inst.tq_tp[Math.min(Math.max(0, b), inst.tq_tp.length - 1)];
  return [+tp[0], feet(inst, b, ps)];
}
function draw(pen, inst, host, ps) {
  var L = L_(), H = H_(), P = inst.fx.params, st = L.style(P), t = inst.age, c = L.colours(inst, host)[0];
  var Ts = L.swing(P), Th = hold(P), imps = impacts(inst, P, ps), hv = HEAVY[st];
  // 0: the impact frame, under everything else
  imps.forEach(function (m) { K_().impactFrame(pen, inst, c, ps, m[1], m[2], m[0], m[5], m[6]); });
  // 1: the surroundings (fx_env): push-off dust under the fighter as the kick
  // starts, the rising kick's kick-up, the spinning kick's vortex, and under
  // each impact a ground wave (the axe kick: its crater)
  var p0 = inst.tq_path[Math.min(WIND, inst.tq_path.length - 1)];
  H.env(pen, inst, P, c, ps, ["push", t - WIND, p0[0], p0[1] + FEET_DROP * ps, -inst.tq_m * K_().flips(P)[0], 0, hv, 0]);
  if (st === "rising_kick") {
    var w = pose(inst, WIND, ps);
    H.env(pen, inst, P, c, ps, ["kickup", t - WIND, w[0], w[1], 0, 0, 1, 0]);
  }
  var out = t >= WIND && t < WIND + Ts + Th + RETRACT;
  if (st === "spinning_kick" && out && (P.spin_mode || "centered") === "centered") {
    var fade = t < WIND + Ts + Th ? 1 : 1 - (t - WIND - Ts - Th) / RETRACT, q = pose(inst, t, ps);
    H.env(pen, inst, P, c, ps, ["vortex", t, q[2], q[3], +P.length * ps, inst.tq_m * K_().flips(P)[0] * K_().flips(P)[1], fade, 0]);
  }
  imps.forEach(function (m) {
    if (st === "axe_kick") {
      var g = craterAt(inst, P, ps, m[1], m[2], m[7]);
      H.env(pen, inst, P, c, ps, ["crater", m[0], g[0], g[1], 0, 0, m[5] * hv, m[6]]);
    } else H.env(pen, inst, P, c, ps, ["ground", m[0], m[1], feet(inst, m[7], ps), 0, 0, m[5] * hv, m[6]]);
  });
  // 2: the foot and its motion (fx_motion)
  H.motion(pen, inst, P, t, ps, c, kickMotion(inst, P, ps));
  // 3: the impacts (fx_impact), laid along the foot's motion, heavier
  imps.forEach(function (m) { H.impact(pen, inst, P, c, ps, m[1], m[2], m[0], m[5] * hv, m[6], [m[3], m[4]]); });
  pen.add(false);
}

G.KICKFX = {STYLES: STYLES, ARC_STYLES: ARC_STYLES, draw: draw, hit: hit, body: body, onHit: onHit, hitDir: hitDir, hitstopStep: hitstopStep,
              activeTicks: activeTicks, totalTicks: totalTicks, contactTick: contactTick, pose: pose};
})(window);
