// Movement style — FX Studio's copy of laser/movestyle.py (the game's
// character-level movement patterns and phases, pack.movement_style).  The
// tables below must match the game's (tools/fx/check_parity.py compares
// them) and the pattern code is a line-for-line port, so the preview moves
// the way the fighter will in Solo and Battle.  Change both together.
(function (G) {
"use strict";
var TICK_MS = 16;
var WALL_ZONE = 250, WALL_PUSH = 400;   // laser/config.py (edge nudge)

var PATTERNS = ["chase", "orbit", "kite", "glide", "zigzag", "hit_and_run", "lunge", "flank",
  "erratic", "stalk", "pendulum", "figure8", "spiral", "mirror", "keep_away", "shadow"];
var SELECTS = ["priority", "weighted", "sequence"];
var FACES = ["travel", "target"];
var ATTACKING = ["any", "yes", "no"];
var ENEMIES = ["any", "melee", "ranged"];
var ENUMS = {direction: ["cw", "ccw", "alternate"],
  strafe: ["cw", "ccw", "alternate", "none"],
  axis: ["line", "horizontal", "vertical"],
  flow: ["in_out", "in", "out"],
  mode: ["mirror", "copy"]};
var SIGNED = ["angle_deg", "retreat_angle_deg", "lead_deg", "carve_deg"];

var PATTERN_DEFAULTS = {
  chase: {stop_px: 0, overshoot_px: 0},
  orbit: {radius_px: 160, direction: "alternate", swap_ms_min: 1500, swap_ms_max: 3500,
    lead_deg: 30, wobble_pct: 0, wobble_ms: 2400},
  kite: {min_px: 220, max_px: 380, strafe: "alternate", swap_ms_min: 1500, swap_ms_max: 3500},
  glide: {radius_px: 120, drift_pct: 92, direction: "alternate", swap_ms_min: 1500, swap_ms_max: 3500,
    carve_deg: 35, carve_ms: 1600, breathe_pct: 30},
  zigzag: {amplitude_px: 90, leg_ms: 350, stop_px: 0, smooth: false},
  hit_and_run: {strike_px: 40, dive_speed_pct: 160, retreat_px: 260, retreat_angle_deg: 35,
    regroup_ms: 700, dive_timeout_ms: 2500},
  lunge: {trigger_px: 260, approach_speed_pct: 60, windup_ms: 250, burst_speed_pct: 320,
    burst_ms: 300, recover_ms: 500},
  flank: {angle_deg: 180, radius_px: 130, tolerance_deg: 30, stop_px: 0},
  erratic: {range_px: 200, hop_min_px: 60, hop_max_px: 160, hop_ms_min: 150, hop_ms_max: 450,
    pull_pct: 50},
  stalk: {keep_px: 150, creep_speed_pct: 35, creep_ms_min: 600, creep_ms_max: 1400,
    freeze_ms_min: 400, freeze_ms_max: 1200},
  pendulum: {distance_px: 200, swing_px: 160, period_ms: 1800},
  figure8: {radius_px: 140, period_ms: 3200, axis: "line"},
  spiral: {outer_px: 260, inner_px: 60, period_ms: 4000, direction: "cw", flow: "in_out"},
  mirror: {mode: "mirror", distance_px: 220},
  keep_away: {comfort_px: 260, pressure_pct: 150, sway_px: 40, sway_ms: 1400},
  shadow: {offset_px: 90, angle_deg: 180, lag_ms: 250}
};
var MODIFIER_DEFAULTS = {speed_pct: 100, pulse_pct: 0, pulse_ms: 1000, inertia_pct: 0,
  weave_deg: 0, weave_ms: 1600, jitter_px: 0, jitter_ms: 400,
  pause_every_ms: 0, pause_ms: 300, face: "travel", wall_avoid: true};
var WHEN_DEFAULTS = {dist_min_px: 0, dist_max_px: 0, hp_min_pct: 0, hp_max_pct: 100,
  hit_taken_ms: 0, hit_landed_ms: 0, attacking: "any", fight_ms: 0, enemy: "any"};
var PHASE_DEFAULTS = {name: "", pattern: "chase", hold_min_ms: 0, hold_max_ms: 0, weight: 1};
var DEFAULTS = {enabled: false, select: "priority", daze: true, phases: []};

var ATTACK_LINGER_MS = 300;
var SWAP_DEFAULT_HOLD_MS = 2000;
var HEADING_MIN_SPEED = 0.3;

// ------------------------------------------------------------ normalising
function ticks(ms) { return Math.max(1, Math.floor(+ms / TICK_MS)); }
function num(v, d) { var f = +v; return (v === null || v === "" || !isFinite(f)) ? d : f; }
function fill(raw, defaults) {
  raw = raw && typeof raw === "object" ? raw : {};
  var out = {};
  Object.keys(defaults).forEach(function (k) {
    var d = defaults[k], v = k in raw ? raw[k] : d;
    if (typeof d === "boolean") out[k] = !!v;
    else if (typeof d === "string") {
      var allowed = ENUMS[k] || (k === "face" ? FACES : k === "attacking" ? ATTACKING : k === "enemy" ? ENEMIES : null);
      out[k] = typeof v === "string" && (!allowed || allowed.indexOf(v) >= 0) ? v : d;
    } else {
      var f = num(v, d);
      out[k] = SIGNED.indexOf(k) >= 0 ? Math.max(-360, Math.min(360, f)) : Math.max(0, f);
    }
  });
  return out;
}
function normalizePhase(raw) {
  raw = raw && typeof raw === "object" ? raw : {};
  var ph = fill(raw, PHASE_DEFAULTS);
  ph.name = String(raw.name || "");
  if (PATTERNS.indexOf(ph.pattern) < 0) ph.pattern = "chase";
  ph.params = fill(raw.params, PATTERN_DEFAULTS[ph.pattern]);
  ph.modifiers = fill(raw.modifiers, MODIFIER_DEFAULTS);
  ph.when = fill(raw.when, WHEN_DEFAULTS);
  if (ph.hold_max_ms < ph.hold_min_ms) ph.hold_max_ms = ph.hold_min_ms;
  return ph;
}
function normalize(raw) {
  raw = raw && typeof raw === "object" ? raw : {};
  var out = {};
  Object.keys(DEFAULTS).forEach(function (k) { out[k] = k in raw ? JSON.parse(JSON.stringify(raw[k])) : JSON.parse(JSON.stringify(DEFAULTS[k])); });
  out.enabled = !!out.enabled; out.daze = !!out.daze;
  if (SELECTS.indexOf(out.select) < 0) out.select = "priority";
  out.phases = (Array.isArray(out.phases) ? out.phases : []).filter(function (p) { return p && typeof p === "object"; }).map(normalizePhase);
  return out;
}

// ------------------------------------------------------------ geometry
function rot(x, y, a) { var c = Math.cos(a), s = Math.sin(a); return [x * c - y * s, y * c + x * s]; }
function unit(x, y, fx, fy) { var d = Math.hypot(x, y); return d > 1e-6 ? [x / d, y / d] : [fx == null ? 1 : fx, fy || 0]; }
var R = Math.PI / 180;
var rng = {random: Math.random, uniform: function (a, b) { return a + (b - a) * Math.random(); }};

function ring(c, radius, lead, sign) { var r = rot(c.ux, c.uy, sign * lead); return [c.ex + r[0] * radius, c.ey + r[1] * radius]; }
function dir(c, mode, lo, hi) {
  var ps = c.ps;
  if (mode === "none") return 0;
  if (mode === "cw") return 1;
  if (mode === "ccw") return -1;
  if (!("dir" in ps)) { ps.dir = c.st.last_dir || (rng.random() < 0.5 ? 1 : -1); ps.swap = c.st.tick + Math.floor(rng.uniform(lo, hi) / TICK_MS); }
  else if (c.st.tick >= ps.swap) { ps.dir = -ps.dir; ps.swap = c.st.tick + Math.max(1, Math.floor(rng.uniform(lo, hi) / TICK_MS)); }
  c.st.last_dir = ps.dir;
  return ps.dir;
}
function stopOf(c, px) { return px > 0 ? px * c.bs : c.auto_stop; }

// ------------------------------------------------------------ patterns
var P = {};
P.chase = function (c, p) {
  var over = p.overshoot_px * c.bs;
  if (over > 0) return [c.ex - c.ux * over, c.ey - c.uy * over];
  var s = stopOf(c, p.stop_px); return [c.ex + c.ux * s, c.ey + c.uy * s];
};
P.orbit = function (c, p) {
  var sign = dir(c, p.direction, p.swap_ms_min, p.swap_ms_max), r = p.radius_px * c.bs;
  if (p.wobble_pct > 0) r *= 1 + Math.min(0.9, p.wobble_pct / 100) * Math.sin(2 * Math.PI * c.t / ticks(p.wobble_ms));
  return ring(c, r, p.lead_deg * R, sign);
};
P.kite = function (c, p) {
  var lo = p.min_px * c.bs, hi = p.max_px * c.bs;
  if (hi < lo) { var tmp = lo; lo = hi; hi = tmp; }
  var sign = dir(c, p.strafe, p.swap_ms_min, p.swap_ms_max);
  if (c.d > hi) { var mid = (lo + hi) * 0.5; return [c.ex + c.ux * mid, c.ey + c.uy * mid]; }
  if (c.d < lo) return ring(c, hi, 20 * R * (sign || 1), 1);
  if (sign === 0) { c.speed = 0; return [c.x, c.y]; }
  return ring(c, c.d, 30 * R, sign);
};
P.glide = function (c, p) {
  var sign = dir(c, p.direction, p.swap_ms_min, p.swap_ms_max), r = p.radius_px * c.bs;
  if (p.breathe_pct > 0) r *= 1 + Math.min(0.9, p.breathe_pct / 100) * Math.sin(2 * Math.PI * c.t / (ticks(p.carve_ms) * 2.7));
  if (p.carve_deg) c.weave += p.carve_deg * R * Math.sin(2 * Math.PI * c.t / ticks(p.carve_ms));
  c.inertia = Math.max(c.inertia, Math.min(98, p.drift_pct));
  return ring(c, r, 60 * R, sign || 1);
};
P.zigzag = function (c, p) {
  var s = stopOf(c, p.stop_px), gap = c.d - s, amp = p.amplitude_px * c.bs;
  if (gap <= 4 * c.bs || amp <= 0) return [c.ex + c.ux * s, c.ey + c.uy * s];
  var leg = ticks(p.leg_ms), side = p.smooth ? Math.sin(Math.PI * c.t / leg) : (Math.floor(c.t / leg) % 2 === 0 ? 1 : -1);
  amp *= Math.min(1, gap / (2 * amp));
  var look = Math.min(gap, 2 * amp), px = -c.uy, py = c.ux;
  return [c.x - c.ux * look + px * side * amp, c.y - c.uy * look + py * side * amp];
};
P.hit_and_run = function (c, p) {
  var ps = c.ps, st = c.st;
  if (!ps.stage) ps.stage = "dive";
  if (!("t0" in ps)) ps.t0 = st.tick;
  var el = st.tick - ps.t0;
  if (ps.stage === "dive") {
    c.speed = p.dive_speed_pct / 100;
    if (c.d <= p.strike_px * c.bs + 2 || el >= ticks(p.dive_timeout_ms) || st.hit_landed >= ps.t0) {
      ps.stage = "retreat"; ps.t0 = st.tick; ps.sign = rng.random() < 0.5 ? 1 : -1; ps.away = [c.ux, c.uy];
    } else return [c.ex, c.ey];
  }
  if (ps.stage === "retreat") {
    var a = rot(ps.away[0], ps.away[1], ps.sign * p.retreat_angle_deg * R), r = p.retreat_px * c.bs;
    var wx = c.ex + a[0] * r, wy = c.ey + a[1] * r;
    if (Math.pow(wx - c.x, 2) + Math.pow(wy - c.y, 2) < Math.pow(20 * c.bs, 2) || st.tick - ps.t0 >= ticks(1500)) { ps.stage = "regroup"; ps.t0 = st.tick; }
    else return [wx, wy];
  }
  c.speed = 0.6;
  if (st.tick - ps.t0 >= ticks(p.regroup_ms)) { ps.stage = "dive"; ps.t0 = st.tick; }
  return ring(c, c.d, 25 * R, ps.sign || 1);
};
P.lunge = function (c, p) {
  var ps = c.ps, st = c.st;
  if (!ps.stage) ps.stage = "approach";
  if (!("t0" in ps)) ps.t0 = st.tick;
  var el = st.tick - ps.t0;
  if (ps.stage === "approach") {
    var trig = p.trigger_px * c.bs; c.speed = p.approach_speed_pct / 100;
    if (c.d > trig) return [c.ex + c.ux * trig * 0.9, c.ey + c.uy * trig * 0.9];
    ps.stage = "windup"; ps.t0 = st.tick; el = 0;
  }
  if (ps.stage === "windup") {
    c.speed = 0; c.face = true;
    if (el < ticks(p.windup_ms)) return [c.x, c.y];
    ps.stage = "burst"; ps.t0 = st.tick; el = 0; ps.hd = [-c.ux, -c.uy];
  }
  if (ps.stage === "burst") {
    c.speed = p.burst_speed_pct / 100; c.inertia = 0;
    if (el < ticks(p.burst_ms)) return [c.x + ps.hd[0] * 1000, c.y + ps.hd[1] * 1000];
    ps.stage = "recover"; ps.t0 = st.tick; el = 0;
  }
  c.speed = 0;
  if (el >= ticks(p.recover_ms)) { ps.stage = "approach"; ps.t0 = st.tick; }
  return [c.x, c.y];
};
P.flank = function (c, p) {
  var want = Math.atan2(c.st.hy, c.st.hx) + p.angle_deg * R, at = Math.atan2(c.uy, c.ux);
  var err = ((want - at + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
  var r = p.radius_px * c.bs;
  if (Math.abs(err) > p.tolerance_deg * R) return ring(c, r, Math.min(Math.abs(err), 40 * R), err > 0 ? 1 : -1);
  var s = stopOf(c, p.stop_px); return [c.ex + Math.cos(want) * s, c.ey + Math.sin(want) * s];
};
P.erratic = function (c, p) {
  var ps = c.ps, st = c.st;
  if (!ps.wp || st.tick >= ps.next) {
    var a = rng.uniform(0, 2 * Math.PI), hop = rng.uniform(Math.min(p.hop_min_px, p.hop_max_px), Math.max(p.hop_min_px, p.hop_max_px)) * c.bs;
    var wx = c.x + Math.cos(a) * hop, wy = c.y + Math.sin(a) * hop, rr = p.range_px * c.bs;
    var ox = wx - c.ex, oy = wy - c.ey, od = Math.hypot(ox, oy);
    if (od > rr) { var k = Math.min(1, p.pull_pct / 100), nx = c.ex + ox / od * rr, ny = c.ey + oy / od * rr; wx += (nx - wx) * k; wy += (ny - wy) * k; }
    ps.wp = [wx, wy];
    ps.next = st.tick + Math.max(1, Math.floor(rng.uniform(Math.min(p.hop_ms_min, p.hop_ms_max), Math.max(p.hop_ms_min, p.hop_ms_max)) / TICK_MS));
  }
  return ps.wp;
};
P.stalk = function (c, p) {
  var ps = c.ps, st = c.st;
  if (!("until" in ps) || st.tick >= ps.until) {
    var creep = !ps.creep; ps.creep = creep;
    var lo = creep ? p.creep_ms_min : p.freeze_ms_min, hi = creep ? p.creep_ms_max : p.freeze_ms_max;
    ps.until = st.tick + Math.max(1, Math.floor(rng.uniform(Math.min(lo, hi), Math.max(lo, hi)) / TICK_MS));
  }
  if (!ps.creep) { c.speed = 0; c.face = true; return [c.x, c.y]; }
  c.speed = p.creep_speed_pct / 100;
  var k = p.keep_px * c.bs; return [c.ex + c.ux * k, c.ey + c.uy * k];
};
P.pendulum = function (c, p) {
  var ps = c.ps, ax = ps.axis || [c.ux, c.uy];
  ax = unit(ax[0] + (c.ux - ax[0]) * 0.01, ax[1] + (c.uy - ax[1]) * 0.01, c.ux, c.uy); ps.axis = ax;
  var dist = p.distance_px * c.bs, sw = p.swing_px * c.bs, s = Math.sin(2 * Math.PI * c.t / ticks(p.period_ms));
  return [c.ex + ax[0] * dist - ax[1] * sw * s, c.ey + ax[1] * dist + ax[0] * sw * s];
};
P.figure8 = function (c, p) {
  var ps = c.ps;
  if (!("theta" in ps)) ps.theta = p.axis === "line" ? Math.atan2(c.uy, c.ux) : p.axis === "horizontal" ? 0 : Math.PI / 2;
  var r = p.radius_px * c.bs, s = 2 * Math.PI * c.t / ticks(p.period_ms);
  var q = rot(r * Math.sin(s), r * Math.sin(s) * Math.cos(s), ps.theta);
  return [c.ex + q[0], c.ey + q[1]];
};
P.spiral = function (c, p) {
  var per = ticks(p.period_ms), cyc = Math.floor(c.t / per), f = (c.t % per) / per;
  var sign = p.direction === "cw" ? 1 : p.direction === "ccw" ? -1 : (cyc % 2 === 0 ? 1 : -1);
  var outer = p.outer_px * c.bs, inner = p.inner_px * c.bs;
  var k = p.flow === "in_out" ? 1 - Math.abs(2 * f - 1) : p.flow === "in" ? f : 1 - f;
  return ring(c, outer - (outer - inner) * k, 35 * R, sign);
};
P.mirror = function (c, p) {
  var ps = c.ps, dd = p.distance_px * c.bs;
  if (!ps.anchor) { ps.anchor = [(c.x + c.ex) * 0.5, (c.y + c.ey) * 0.5]; ps.off = unit(c.x - c.ex, c.y - c.ey, c.ux, c.uy); }
  if (p.mode === "copy") return [c.ex + ps.off[0] * dd, c.ey + ps.off[1] * dd];
  var ax = ps.anchor[0], ay = ps.anchor[1];
  ax += (c.ex + c.ux * dd * 0.5 - ax) * 0.01;
  ay += (c.ey + c.uy * dd * 0.5 - ay) * 0.01;
  ps.anchor = [ax, ay];
  var wx = 2 * ax - c.ex, wy = 2 * ay - c.ey, ox = wx - c.ex, oy = wy - c.ey;
  if (ox * ox + oy * oy < dd * dd) { var u = unit(ox, oy, c.ux, c.uy); wx = c.ex + u[0] * dd; wy = c.ey + u[1] * dd; }
  return [wx, wy];
};
P.keep_away = function (c, p) {
  var comfort = p.comfort_px * c.bs, k = Math.max(0, Math.min(1, (comfort - c.d) / Math.max(1, comfort * 0.25)));
  c.speed = 0.6;
  if (k > 0) {
    var closing = Math.max(0, c.st.tvx * c.ux + c.st.tvy * c.uy), base = Math.max(0.1, c.fig.speed);
    c.speed += (Math.min(3, 1 + p.pressure_pct / 100 * closing / base) - 0.6) * k;
  }
  var a = Math.sin(2 * Math.PI * c.t / ticks(p.sway_ms)) * p.sway_px * c.bs / Math.max(1, comfort), q = rot(c.ux, c.uy, a);
  var r = comfort * (1 + 0.2 * k);
  return [c.ex + q[0] * r, c.ey + q[1] * r];
};
P.shadow = function (c, p) {
  var hist = c.st.hist, lag = Math.floor(p.lag_ms / TICK_MS);
  var pt = hist.length > lag ? hist[hist.length - 1 - lag] : hist[0];
  var q = rot(c.st.hx, c.st.hy, p.angle_deg * R), off = p.offset_px * c.bs;
  return [pt[0] + q[0] * off, pt[1] + q[1] * off];
};

// ------------------------------------------------------------ the sim
// fig: {x, y, speed (px/tick), facing_left, hp, max_hp, attacking, enemy_melee, w, h}.
// One Sim per preview; tick(ex, ey) moves fig one game tick (16 ms).
function Sim(style, fig) {
  this.style = normalize(style); this.fig = fig;
  this.st = {tick: 0, phase: -1, phase_start: 0, phase_until: 0, ps: {}, vx: 0, vy: 0,
    prev: null, tvx: 0, tvy: 0, hx: 1, hy: 0, hist: [], hit_taken: -1e9, hit_landed: -1e9, attack_tick: -1e9,
    pause_next: null, pause_until: 0, jitter_next: 0, jx: 0, jy: 0, last_dir: 0};
  this.aim = null; this.live = false; this.face_target = false;
}
Sim.prototype.noteHitTaken = function () { this.st.hit_taken = this.st.tick; };
Sim.prototype.noteHitLanded = function () { this.st.hit_landed = this.st.tick; };
Sim.prototype.passes = function (w, d, bs) {
  var st = this.st, f = this.fig;
  if (d < w.dist_min_px * bs) return false;
  if (w.dist_max_px > 0 && d > w.dist_max_px * bs) return false;
  var hp = f.max_hp ? 100 * f.hp / f.max_hp : 100;
  if (hp < w.hp_min_pct || hp > w.hp_max_pct) return false;
  if (w.hit_taken_ms > 0 && st.tick - st.hit_taken > ticks(w.hit_taken_ms)) return false;
  if (w.hit_landed_ms > 0 && st.tick - st.hit_landed > ticks(w.hit_landed_ms)) return false;
  if (w.attacking !== "any") { var on = st.tick - st.attack_tick <= ticks(ATTACK_LINGER_MS); if (on !== (w.attacking === "yes")) return false; }
  if (w.fight_ms > 0 && st.tick < ticks(w.fight_ms)) return false;
  if (w.enemy !== "any" && (f.enemy_melee !== false) !== (w.enemy === "melee")) return false;
  return true;
};
Sim.prototype.choose = function (d, bs) {
  var st = this.st, sty = this.style, phases = sty.phases, self = this;
  if (st.phase >= 0 && st.phase < phases.length && st.tick < st.phase_until) return st.phase;
  var ok = []; phases.forEach(function (ph, i) { if (self.passes(ph.when, d, bs)) ok.push(i); });
  if (!ok.length) return -1;
  if (sty.select === "weighted") {
    var total = ok.reduce(function (a, i) { return a + phases[i].weight; }, 0);
    if (total <= 0) return ok[0];
    var r = rng.uniform(0, total);
    for (var j = 0; j < ok.length; j++) { r -= phases[ok[j]].weight; if (r <= 0) return ok[j]; }
    return ok[ok.length - 1];
  }
  if (sty.select === "sequence") {
    var n = phases.length;
    for (var k = 1; k <= n; k++) { var i = st.phase >= 0 ? (st.phase + k) % n : k - 1; if (ok.indexOf(i) >= 0) return i; }
    return ok[0];
  }
  return ok[0];
};
Sim.prototype.enter = function (idx) {
  var st = this.st, sty = this.style;
  if (idx !== st.phase || idx < 0) { st.ps = {}; st.phase_start = st.tick; st.pause_next = null; }
  st.phase = idx;
  if (idx >= 0) {
    var ph = sty.phases[idx], lo = ph.hold_min_ms, hi = ph.hold_max_ms;
    if (hi <= 0 && sty.select !== "priority") lo = hi = SWAP_DEFAULT_HOLD_MS;
    st.phase_until = st.tick + Math.floor(rng.uniform(lo, hi) / TICK_MS);
  }
};
Sim.prototype.wall = function () {
  var f = this.fig, rx = 0, ry = 0, z = WALL_ZONE, k;
  if (f.x < z) { k = 1 - f.x / z; rx += k * k * k * WALL_PUSH; }
  if (f.w - f.x < z) { k = 1 - (f.w - f.x) / z; rx -= k * k * k * WALL_PUSH; }
  if (f.y < z) { k = 1 - f.y / z; ry += k * k * k * WALL_PUSH; }
  if (f.h - f.y < z) { k = 1 - (f.h - f.y) / z; ry -= k * k * k * WALL_PUSH; }
  return [rx, ry];
};
// The game's target(): the aim point, or null when no phase passes (the
// game then runs the character's old movement; the preview just chases).
Sim.prototype.target = function (ex, ey, autoStop) {
  var st = this.st, f = this.fig, sty = this.style, bs = 1;
  st.tick++;
  if (st.prev) { st.tvx = st.tvx * 0.8 + (ex - st.prev[0]) * 0.2; st.tvy = st.tvy * 0.8 + (ey - st.prev[1]) * 0.2; }
  else { var h0 = unit(f.x - ex, f.y - ey, st.hx, st.hy); st.hx = h0[0]; st.hy = h0[1]; }
  st.prev = [ex, ey]; st.hist.push([ex, ey]); if (st.hist.length > 240) st.hist.shift();
  if (st.tvx * st.tvx + st.tvy * st.tvy > HEADING_MIN_SPEED * HEADING_MIN_SPEED) { var h = unit(st.tvx, st.tvy); st.hx = h[0]; st.hy = h[1]; }
  if (f.attacking) st.attack_tick = st.tick;
  var dx = f.x - ex, dy = f.y - ey, d = Math.hypot(dx, dy);
  if (!sty.enabled || !sty.phases.length) { this.live = false; return null; }
  var idx = this.choose(d, bs);
  if (idx !== st.phase || st.tick >= st.phase_until) this.enter(idx);
  if (idx < 0) { this.live = false; return null; }
  var ph = sty.phases[idx], mod = ph.modifiers, u = unit(dx, dy, f.facing_left ? -1 : 1, 0);
  var c = {fig: f, st: st, ps: st.ps, bs: bs, x: f.x, y: f.y, ex: ex, ey: ey, d: d, ux: u[0], uy: u[1],
    auto_stop: autoStop || 0, t: st.tick - st.phase_start, speed: 1, inertia: 0, weave: 0, face: false};
  var a = P[ph.pattern](c, ph.params), ax = a[0], ay = a[1];
  var sp = c.speed * mod.speed_pct / 100;
  if (mod.pulse_pct > 0) sp *= Math.max(0, 1 + mod.pulse_pct / 100 * Math.sin(2 * Math.PI * st.tick / ticks(mod.pulse_ms)));
  if (mod.jitter_px > 0) {
    if (st.tick >= st.jitter_next) {
      var ja = rng.uniform(0, 2 * Math.PI), jr = mod.jitter_px * bs * Math.sqrt(rng.random());
      st.jx = Math.cos(ja) * jr; st.jy = Math.sin(ja) * jr; st.jitter_next = st.tick + ticks(mod.jitter_ms);
    }
    ax += st.jx; ay += st.jy;
  }
  if (mod.pause_every_ms > 0) {
    if (st.pause_next === null) st.pause_next = st.tick + ticks(mod.pause_every_ms * rng.uniform(0.5, 1.5));
    if (st.tick >= st.pause_next) { st.pause_until = st.tick + ticks(mod.pause_ms); st.pause_next = st.pause_until + ticks(mod.pause_every_ms * rng.uniform(0.5, 1.5)); }
    if (st.tick < st.pause_until) sp = 0;
  }
  var weave = c.weave;
  if (mod.weave_deg > 0) weave += mod.weave_deg * R * Math.sin(2 * Math.PI * st.tick / ticks(mod.weave_ms));
  if (mod.wall_avoid) { var wr = this.wall(); ax += wr[0]; ay += wr[1]; }
  this.live = true;
  st.speed_mult = sp; st.inertia = Math.min(0.98, Math.max(mod.inertia_pct, c.inertia) / 100); st.weave = weave;
  this.face_target = c.face || mod.face === "target";
  return [ax, ay];
};
// The game's step() plus the edge clamp (motion.check_walls).
Sim.prototype.step = function (tx, ty) {
  var st = this.st, f = this.fig, margin = 10;
  var dx = tx - f.x, dy = ty - f.y, d = Math.hypot(dx, dy), speed = f.speed * st.speed_mult, wx = 0, wy = 0;
  if (speed > 0 && d >= 0.5) {
    var v = Math.min(speed, d); wx = dx / d * v; wy = dy / d * v;
    if (st.weave && d > speed) { var q = rot(wx, wy, st.weave); wx = q[0]; wy = q[1]; }
  }
  var a = 1 - st.inertia; st.vx += (wx - st.vx) * a; st.vy += (wy - st.vy) * a;
  var nx = f.x + st.vx, ny = f.y + st.vy;
  if (!(margin <= nx && nx <= f.w - margin)) st.vx = 0;
  if (!(margin <= ny && ny <= f.h - margin)) st.vy = 0;
  var ox = f.x; f.x += st.vx; f.y += st.vy;
  f.x = Math.max(margin, Math.min(f.w - margin, f.x)); f.y = Math.max(margin, Math.min(f.h - margin, f.y));
  if (f.x - ox < -0.001) f.facing_left = true; else if (f.x - ox > 0.001) f.facing_left = false;
};
// One whole tick: style target (or a plain chase when no phase passes), step.
Sim.prototype.tick = function (ex, ey, autoStop) {
  var f = this.fig, pt = this.target(ex, ey, autoStop);
  if (pt === null) {
    var u = unit(f.x - ex, f.y - ey); pt = [ex + u[0] * (autoStop || 0), ey + u[1] * (autoStop || 0)];
    this.st.speed_mult = 1; this.st.inertia = 0; this.st.weave = 0; this.face_target = false;
  }
  this.aim = pt; this.step(pt[0], pt[1]);
  if (this.face_target) f.facing_left = ex < f.x;
};

G.MOVESTYLE = {PATTERNS: PATTERNS, SELECTS: SELECTS, FACES: FACES, ATTACKING: ATTACKING, ENEMIES: ENEMIES, ENUMS: ENUMS, SIGNED: SIGNED,
  PATTERN_DEFAULTS: PATTERN_DEFAULTS, MODIFIER_DEFAULTS: MODIFIER_DEFAULTS, WHEN_DEFAULTS: WHEN_DEFAULTS,
  PHASE_DEFAULTS: PHASE_DEFAULTS, DEFAULTS: DEFAULTS, normalize: normalize, normalizePhase: normalizePhase, Sim: Sim};
})(window);
