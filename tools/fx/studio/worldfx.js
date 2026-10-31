// World physics: Dust & Air — FX Studio's port of laser/worldfx.py.
//
// The dust, debris and displaced air the ARENA kicks up when fighters move,
// jump, get slammed, clash and blast.  Shared by every character (saved as
// world_physics.json, format pb_world_physics, read by the game from
// characters/world_physics.json); a character's FX pack may carry
// "world_physics" with any of these sections, which then replace the world's
// for the events that fighter causes.
//
// Ground model: the screen is a slope seen from its foot.  The position-scale
// grid says how big things are where (bottom-left near 5x, top-right far 1x).
// A particle has a ground point (x, y) and a height z, drawn at (x, y - z).
// Ground spreads are ellipses whose height / width ratio runs from
// ground.flat_near (nearest) to ground.flat_far (farthest): rounder the
// farther away.  Screen edges are the walls.
//
// Engine (hybrid): rocks / pebbles / sparks are closed-form (whole flight
// fixed at spawn); fine dust is simulated and relaxes toward the local air
// velocity, v = u + (v - u) e^(-dt/tau); the air is a short list of analytic
// sources (blast, wake, curl, column, jet).  tools/fx/check_parity.py checks
// WP_DEFAULTS / WP_RANGES / WP_FORMAT / WP_SECTIONS against the game.
(function () {
"use strict";
var WP_FORMAT = "pb_world_physics";
var WP_SECTIONS = ["ground", "dash", "jump", "slam", "clash", "blast", "sonic"];
var WP_DEFAULTS = {
  "ground": {"enabled": true, "flat_near": 0.25, "flat_far": 0.55, "max_dust": 420, "tau_ms": 140, "ink": "#1b1712"},
  "dash": {"enabled": true, "speed": 380, "rate": 40, "inherit": 40, "size": 100, "life_ms": 700,
           "start_burst": true, "wake": true, "wake_pct": 100, "curls": true, "grit": 6, "color": "#d9c4a3"},
  "jump": {"enabled": true, "dust": 14, "pebbles": 8, "ring": true, "column": true, "land": true,
           "hops": true, "size": 100, "color": "#d9c4a3"},
  "slam": {"enabled": true, "min_speed": 7, "launch": true, "skid": true, "crater": true, "wall": true,
           "dust": 22, "rocks": 10, "size": 100, "color": "#cdb391", "rock_color": "#7a6e62"},
  "clash": {"enabled": true, "sheet": true, "dust": 14, "sparks": 16, "ground_jet": true, "size": 100,
            "color": "#e6dccb", "spark_color": "#ffb347"},
  "blast": {"enabled": true, "min_damage": 4, "strength": 100, "suck_back": true, "reach": 80,
            "dust": 18, "ring": true, "size": 100, "color": "#d9c4a3"},
  "sonic": {"enabled": true, "mach": 1100, "knockback": false, "cone": true, "vapor": true,
            "boom": true, "sweep": true, "color": "#e8f2ff"}
};
var WP_RANGES = {
  "ground": {"flat_near": [0.05, 1.0], "flat_far": [0.05, 1.0], "max_dust": [0, 1500], "tau_ms": [20, 600]},
  "dash": {"speed": [50, 3000], "rate": [0, 200], "inherit": [0, 100], "size": [10, 400], "life_ms": [100, 3000],
           "wake_pct": [0, 300], "grit": [0, 60]},
  "jump": {"dust": [0, 80], "pebbles": [0, 40], "size": [10, 400]},
  "slam": {"min_speed": [0, 60], "dust": [0, 120], "rocks": [0, 40], "size": [10, 400]},
  "clash": {"dust": [0, 80], "sparks": [0, 80], "size": [10, 400]},
  "blast": {"min_damage": [0, 500], "strength": [0, 300], "reach": [20, 1200], "dust": [0, 120],
            "size": [10, 400]},
  "sonic": {"mach": [100, 6000]}
};
// Labels and hover help for the Studio page: [key, label, help].
var WP_FIELDS = {
  ground: [["enabled", "World physics on", "Every Dust & Air effect, for every character."],
           ["flat_near", "Ground flatness, near", "Height / width of a ring spreading on the ground at the nearest spot (bottom-left). Lower = flatter."],
           ["flat_far", "Ground flatness, far", "The same at the farthest spot (top-right). Higher than near = rounder the farther away (the slope rises toward your eye)."],
           ["max_dust", "Most dust puffs", "Cap on simulated dust puffs on screen; the oldest go first. Lower it if the game slows."],
           ["tau_ms", "Dust response (ms)", "How fast dust takes up the speed of the air round it: low = rides every gust, high = keeps its own momentum."],
           ["ink", "Ink outline", "The outline colour round dust clouds, rocks and rings."]],
  dash: [["enabled", "On", "Dust kicked up by fast movement."],
         ["speed", "Speed threshold (px/s)", "On-screen speed above which a fighter kicks up dust."],
         ["rate", "Puffs per second", "At the threshold speed; up to 3x faster above it."],
         ["inherit", "Velocity inherited %", "How much of the fighter's speed each puff starts with."],
         ["size", "Puff size %", ""], ["life_ms", "Puff life (ms)", ""],
         ["start_burst", "Start burst", "The first ticks of a dash throw triple the dust."],
         ["wake", "Wake", "A pocket of air dragged along behind the fighter carries the dust after it."],
         ["wake_pct", "Wake strength %", ""],
         ["curls", "Wake curls", "Curls of air shed alternately from either side of the body."],
         ["grit", "Grit per second", "Small pebbles flicked back by the feet."],
         ["color", "Dust colour", ""]],
  jump: [["enabled", "On", "Leaps (Movement leap) and hop-backs."],
         ["dust", "Dust puffs", ""], ["pebbles", "Pebbles", "Thrown steeply (55-75 degrees) on take-off."],
         ["ring", "Ground ring", ""], ["column", "Air column", "Air drawn up behind the jumper lifts the dust after them."],
         ["land", "Landing puff", ""], ["hops", "Hop-backs too", "A hop-back makes a half-size take-off and landing."],
         ["size", "Size %", ""], ["color", "Dust colour", ""]],
  slam: [["enabled", "On", "Knockback slides: launch, skid, crater, wall."],
         ["min_speed", "Minimum knockback (px/tick)", "Slower slides make no slam dust. A crater needs twice this."],
         ["launch", "Launch burst", "Dust and rocks thrown back where the hit lands."],
         ["skid", "Skid trail", "Dust along the slide."],
         ["crater", "Crater", "Where a heavy slide stops: scorched dish, rim of rising dust, rocks."],
         ["wall", "Wall slam", "A slide that hits a screen edge: a dust plane on the wall."],
         ["dust", "Dust puffs", ""], ["rocks", "Rocks", ""], ["size", "Size %", ""],
         ["color", "Dust colour", ""], ["rock_color", "Rock colour", ""]],
  clash: [["enabled", "On", "When two opposing effects clash (World Clash)."],
          ["sheet", "Splash sheet", "Dust thrown sideways to the hit, both ways."],
          ["dust", "Dust puffs", ""], ["sparks", "Sparks", ""],
          ["ground_jet", "Ground jet", "The downward half of the splash reaches the floor a beat later and runs out along it."],
          ["size", "Size %", ""], ["color", "Dust colour", ""], ["spark_color", "Spark colour", ""]],
  blast: [["enabled", "On", "Where a technique's shot detonates (ki blasts, charged blasts, rockets...)."],
          ["min_damage", "Minimum damage", "Weaker shots make no blast air."],
          ["strength", "Wind strength %", ""],
          ["suck_back", "Suck-back", "After the push, the air pulls back toward the centre."],
          ["reach", "Reach (px at damage 10)", "Grows with the cube root of the damage."],
          ["dust", "Dust puffs", ""], ["ring", "Ground ring", ""], ["size", "Size %", ""],
          ["color", "Dust colour", ""]],
  sonic: [["enabled", "On", "Breaking the sound barrier."],
          ["mach", "Sound speed (px/s)", "On-screen speed: near fighters (bottom-left) move faster on screen, so they break it more easily."],
          ["knockback", "Knockback slides count", "Off: only a fighter's own movement breaks the barrier."],
          ["cone", "Shock cone", "Bow shock lines at sin(angle) = 1 / Mach."],
          ["vapor", "Vapour collar", "Flickers just behind the nose near Mach 1."],
          ["boom", "Barrier ring", "A ring round the body the moment it crosses Mach 1."],
          ["sweep", "Ground sweep", "Where the cone meets the floor, the air pushes out and pulls back."],
          ["color", "Shock colour", ""]]
};
var WP_TITLES = {ground: "Ground & dust", dash: "Dash / fast movement", jump: "Jump take-off & landing",
  slam: "Knockback slams", clash: "Clashes", blast: "Energy blasts", sonic: "Sound barrier"};

var TICK_MS = 16, TICK_S = TICK_MS / 1000;
// Position grids (laser/config.py POSITION_SCALE_* / SPEED_SCALE_*): TL, TR, BL, BR.
var PS = [2.3333, 1.0, 5.0, 2.3333], SS = [0.6, 0.4, 1.0, 0.6];
var PS_LO = Math.min.apply(null, PS), PS_HI = Math.max.apply(null, PS);
var TELEPORT_PX = 40;

function hex(v, d) { return (typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v)) ? v.toLowerCase() : d; }
function normalizeSection(name, s) {
  s = (s && typeof s === "object") ? s : {};
  var dflt = WP_DEFAULTS[name], rng = WP_RANGES[name] || {}, out = {};
  Object.keys(dflt).forEach(function (k) {
    var d = dflt[k], v = s.hasOwnProperty(k) ? s[k] : d;
    if (typeof d === "boolean") out[k] = !!v;
    else if (typeof d === "string") out[k] = hex(v, d);
    else {
      v = parseFloat(v); if (!isFinite(v)) v = d;
      var r = rng[k] || [-1e9, 1e9];
      out[k] = Math.max(r[0], Math.min(r[1], v));
    }
  });
  return out;
}
function normalize(c) {
  c = (c && typeof c === "object") ? c : {};
  var out = {format: WP_FORMAT};
  WP_SECTIONS.forEach(function (n) { out[n] = normalizeSection(n, c[n]); });
  return out;
}
function normalizeOverride(c) {
  c = (c && typeof c === "object") ? c : {};
  var out = {};
  WP_SECTIONS.forEach(function (n) { if (c[n] && typeof c[n] === "object") out[n] = normalizeSection(n, c[n]); });
  return out;
}

function bil(xf, yf, g) {
  var top = g[0] * (1 - xf) + g[1] * xf, bot = g[2] * (1 - xf) + g[3] * xf;
  return top * (1 - yf) + bot * yf;
}
function clamp01(v) { return Math.max(0, Math.min(1, v)); }
function escale(e) { return Math.max(0.45, Math.min(2.6, Math.pow(Math.max(0, e), 1 / 3))); }
function rgb(h) { return [parseInt(h.substr(1, 2), 16), parseInt(h.substr(3, 2), 16), parseInt(h.substr(5, 2), 16)]; }
function css(c, a) { return "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + (a == null ? 1 : a) + ")"; }

// ---------------------------------------------------------------- air sources
function Blast(x, y, s, ps, reach, strength, suck, flat) {
  this.x = x; this.y = y; this.age = 0;
  this.T = Math.max(4, 0.32 * s / TICK_S); this.ts = Math.max(2, 0.2 * s / TICK_S);
  this.rmax = Math.max(10, reach * s * ps); this.amp = 4.0 * s * ps * strength;
  this.suck = suck; this.flat = Math.max(0.05, flat); this.life = this.T + 6 * this.ts;
}
Blast.prototype.bbox = function () { var r = this.rmax; return [this.x - r, this.y - r * this.flat, this.x + r, this.y + r * this.flat]; };
Blast.prototype.air = function (x, y, z) {
  var dx = x - this.x, dy = (y - this.y) / this.flat, r = Math.sqrt(dx * dx + dy * dy);
  if (r >= this.rmax) return null;
  var tau = this.age - this.T * Math.pow(r / this.rmax, 2.5);
  if (tau < 0) return null;
  var q = tau / this.ts, p = Math.exp(-q) * (1 - q);
  if (p < 0 && !this.suck) return null;
  var a = this.amp * p * (1 - r / this.rmax) / Math.max(r, 4);
  return [dx * a, dy * a * this.flat, p > 0 ? 0.35 * a * r : 0];
};
function Wake(x, y, d) { this.x = x; this.y = y; this.vx = this.vy = 0; this.d = Math.max(6, d); this.k = 0; this.age = 0; this.life = 1e9; this.live = true; }
Wake.prototype.bbox = function () { var r = this.d * 4; return [this.x - r, this.y - r * 1.5, this.x + r, this.y + r]; };
Wake.prototype.air = function (x, y, z) {
  var sp = Math.hypot(this.vx, this.vy);
  if (sp < 0.01 || this.k < 0.01) return null;
  var cx = this.x - this.vx / sp * this.d * 0.8, cy = this.y - this.vy / sp * this.d * 0.8;
  var dx = x - cx, dy = y - cy, q = (dx * dx + dy * dy + z * z) / (this.d * this.d * 1.6);
  if (q > 9) return null;
  var w = this.k * Math.exp(-q);
  return [this.vx * w, this.vy * w, 0];
};
function Curl(x, y, g, rc) { this.x = x; this.y = y; this.g = g; this.rc = Math.max(4, rc); this.age = 0; this.life = 0.6 / TICK_S; }
Curl.prototype.bbox = function () { var r = 4 * this.rc * (1 + this.age / 18); return [this.x - r, this.y - r, this.x + r, this.y + r * 3]; };
Curl.prototype.air = function (x, y, z) {
  var rc = this.rc * (1 + this.age / 18), dx = x - this.x, dy = (y - z) - this.y, r2 = dx * dx + dy * dy;
  if (r2 > 16 * rc * rc) return null;
  var f = this.g * (1 - this.age / this.life) * Math.exp(-r2 / (2 * rc * rc)) / rc;
  return [-dy * f, 0, -dx * f];
};
function Column(x, y, w, r, flat) { this.x = x; this.y = y; this.w = w; this.r = Math.max(6, r); this.age = 0; this.flat = Math.max(0.05, flat); this.life = 26; }
Column.prototype.bbox = function () { var r = 3 * this.r; return [this.x - r, this.y - r * this.flat, this.x + r, this.y + r * this.flat]; };
Column.prototype.air = function (x, y, z) {
  var dx = x - this.x, dy = (y - this.y) / this.flat, q = (dx * dx + dy * dy) / (this.r * this.r);
  if (q > 9) return null;
  var k = this.w * (1 - this.age / this.life) * Math.exp(-q);
  return [-dx / this.r * k * 0.3, -dy * this.flat / this.r * k * 0.3, k];
};
function Jet(x, y, j, c, wd, flat, axis, out) {
  this.x = x; this.y = y; this.j = j; this.c = c; this.wd = Math.max(4, wd);
  this.age = 0; this.life = 28; this.flat = Math.max(0.05, flat); this.axis = axis || null; this.out = out || [0, 0];
}
Jet.prototype.bbox = function () {
  var r = this.age * this.c + 3 * this.wd + 2, w = 3 * this.wd;
  if (this.axis === "v") return [this.x - w, this.y - r, this.x + w, this.y + r * 3];
  if (this.axis === "h") return [this.x - r, this.y - w, this.x + r, this.y + w];
  return [this.x - r, this.y - r * this.flat, this.x + r, this.y + r * this.flat];
};
Jet.prototype.air = function (x, y, z) {
  var dx, dy, fall = 1, q0;
  if (this.axis === "v") { dx = 0; dy = (y - z) - this.y; q0 = (x - this.x) / (3 * this.wd); fall = Math.exp(-q0 * q0); }
  else if (this.axis === "h") { dx = x - this.x; dy = 0; q0 = (y - this.y) / (3 * this.wd); fall = Math.exp(-q0 * q0); }
  else { dx = x - this.x; dy = (y - this.y) / this.flat; }
  var r = Math.sqrt(dx * dx + dy * dy), q = (r - this.age * this.c) / this.wd;
  if (q * q > 9 || r < 0.5) return null;
  if (fall < 0.01) return null;
  var e = Math.exp(-this.age / 10) * Math.exp(-q * q), k = this.j * fall * e / r;
  var ux = dx * k, uy = dy * k * (this.axis ? 1 : this.flat), w = this.j * fall * 0.6 * e;
  if (this.axis === "v") return [this.out[0] * w, 0, -uy];
  if (this.axis === "h") return [ux, this.out[1] * w, 0];
  return [ux, uy, 0];
};

// ---------------------------------------------------------------- closed-form debris
function Burst(x, y, ps, ss, kind, pieces, g, k, e, life, col) {
  this.x = x; this.y = y; this.ps = ps; this.ss = ss; this.age = 0; this.kind = kind; this.pieces = pieces;
  this.g = g; this.k = k; this.e = e; this.life = life; this.col = col;
}
Burst.prototype.at = function (pc, t) {
  var ca = pc[0], sa = pc[1], h = pc[2], v = pc[3], g = this.g, k = this.k, e = this.e;
  var dist = k < 0.9999 ? h * (1 - Math.pow(k, t)) / (1 - k) : h * t;
  var t1 = g > 0 ? 2 * v / g : 1e9, z;
  if (t <= t1) z = v * t - 0.5 * g * t * t;
  else {
    if (this.kind === "spark") return null;
    var d1 = k < 0.9999 ? h * (1 - Math.pow(k, t1)) / (1 - k) : h * t1;
    dist = d1 + 0.45 * (dist - d1);
    var v2 = v * e, t2 = g > 0 ? 2 * v2 / g : 0, tt = t - t1;
    z = tt <= t2 ? v2 * tt - 0.5 * g * tt * tt : 0;
  }
  return [this.x + ca * dist, this.y + sa * dist, Math.max(0, z)];
};
function Ring(kind, x, y, life, r, flat, edge, col, w) {
  this.kind = kind; this.x = x; this.y = y; this.age = 0; this.life = Math.max(2, life); this.r = r;
  this.flat = flat == null ? 1 : flat; this.edge = edge || null; this.col = col || [255, 255, 255]; this.w = w == null ? 6 : w;
}

// ---------------------------------------------------------------- the simulation
// opts: {sw, sh, world (normalized), cfgFor(fig, section) optional}
function Sim(opts) {
  this.sw = opts.sw || 1120; this.sh = opts.sh || 630;
  this.world = opts.world || normalize({});
  this.cfgFor = opts.cfgFor || null;
  this.reset();
}
Sim.prototype.reset = function () {
  this.dust = []; this.src = []; this.bursts = []; this.rings = []; this.later = []; this.tracks = new Map(); this.walls = []; this.t = 0;
};
Sim.prototype.cfg = function (fig, name) {
  if (fig && fig.wp && fig.wp[name]) return fig.wp[name];
  return this.world[name];
};
Sim.prototype.ps = function (x, y) { return bil(clamp01(x / this.sw), clamp01(y / this.sh), PS); };
Sim.prototype.ssc = function (x, y) { return bil(clamp01(x / this.sw), clamp01(y / this.sh), SS); };
Sim.prototype.flat = function (x, y) {
  var g = this.world.ground, ps = this.ps(x, y), f = clamp01((PS_HI - ps) / (PS_HI - PS_LO));
  return g.flat_near + (g.flat_far - g.flat_near) * f;
};
Sim.prototype.addSrc = function (s) { if (this.src.length >= 24) this.src.shift(); this.src.push(s); return s; };
Sim.prototype.addRing = function (r) { if (this.rings.length >= 40) this.rings.shift(); this.rings.push(r); };
Sim.prototype.puff = function (x, y, z, vx, vy, vz, life, r0, col, tau, grav) {
  var g = this.world.ground;
  this.dust.push([x, y, z, vx, vy, vz, 0, Math.max(4, life), r0, Math.max(1, tau == null ? g.tau_ms / TICK_MS : tau), col, grav == null ? -0.012 : grav]);
};
Sim.prototype.puffs = function (x, y, n, sp, col, size, lifeMs, az, spread, up, r0, flat) {
  if (n <= 0) return;
  var ps = this.ps(x, y), fl = flat == null ? this.flat(x, y) : flat, R = Math.random;
  spread = spread == null ? 360 : spread; up = up || [0.2, 1]; r0 = r0 || 6;
  for (var i = 0; i < Math.floor(n); i++) {
    var a = ((az || 0) + (R() - 0.5) * spread) * Math.PI / 180, s = sp * (0.4 + 0.6 * R()) * ps;
    this.puff(x + (R() - 0.5) * 6 * ps, y + (R() - 0.5) * 3 * ps, R() * 3 * ps, Math.cos(a) * s, Math.sin(a) * s * fl,
      (up[0] + (up[1] - up[0]) * R()) * ps, lifeMs / TICK_MS * (0.7 + 0.6 * R()), r0 * size * (0.7 + 0.6 * R()), col);
  }
};
Sim.prototype.debris = function (x, y, kind, n, s, col, o) {
  if (n <= 0) return;
  o = o || {};
  if (this.bursts.length >= 40) this.bursts.shift();
  var ps = this.ps(x, y), ss = this.ssc(x, y), fl = this.flat(x, y), R = Math.random, pieces = [];
  var spread = o.spread == null ? 360 : o.spread, elev = o.elev || [30, 62], spd = o.spd || [3, 9], size = o.size || [2, 5];
  for (var i = 0; i < Math.floor(n); i++) {
    var a = ((o.az || 0) + (R() - 0.5) * spread) * Math.PI / 180, sp, el;
    if (o.pi) { var u = 0.25 + 0.75 * R(); sp = Math.min(spd[1] * 1.6, spd[0] * Math.pow(u, -1.1)) * Math.sqrt(s); el = (62 - 27 * u) * Math.PI / 180; }
    else { sp = (spd[0] + (spd[1] - spd[0]) * R()) * Math.sqrt(s); el = (elev[0] + (elev[1] - elev[0]) * R()) * Math.PI / 180; }
    pieces.push([Math.cos(a), Math.sin(a) * fl, sp * Math.cos(el) * ps, sp * Math.sin(el) * ps,
      (size[0] + (size[1] - size[0]) * R()) * ps, (R() - 0.5) * 0.5, R() * 6.28]);
  }
  if (kind === "spark") this.bursts.push(new Burst(x, y, ps, ss, kind, pieces, 0.22 * ps, 0.974, 0, 34, col));
  else this.bursts.push(new Burst(x, y, ps, ss, kind, pieces, 0.34 * ps, kind === "rock" ? 0.994 : 0.98, 0.35, kind === "rock" ? 95 : 60, col));
};
// A preview fighter: {x, y, h (foot offset at 100 %), motion{bouncing, bounce_ending, bounce_vx, bounce_vy},
// hop_ticks, leap {sx, sy, ex, ey, t0, t1, h, done}, wp (override sections)}.
Sim.prototype.foot = function (fig, ps) { var h = (fig.h || 24) * 0.46 * ps; return [fig.x, fig.y + h, h]; };
Sim.prototype.noteWall = function (fig, edge, speed) { this.walls.push([fig, edge, fig.x, fig.y, speed]); };
Sim.prototype.step = function (figs) {
  var self = this; this.t++;
  if (!this.world.ground.enabled) { this.reset(); return; }
  var due = this.later.filter(function (e) { return e[0] <= self.t; });
  this.later = this.later.filter(function (e) { return e[0] > self.t; });
  due.forEach(function (e) { e[1].apply(self, e[2]); });
  (figs || []).forEach(function (f) { self.observe(f); });
  this.walls.forEach(function (w) { self.wall(w[0], w[1], w[2], w[3], w[4]); });
  this.walls = [];
  this.tracks.forEach(function (tr, f) { if (tr.seen !== self.t) self.tracks.delete(f); });
  this.move();
};
Sim.prototype.observe = function (fig) {
  var tr = this.tracks.get(fig), ps = this.ps(fig.x, fig.y), ft = this.foot(fig, ps), fx = ft[0], fy = ft[1], hh = ft[2];
  var lp = fig.leap, z = 0;
  if (lp && !lp.done && lp.h > 0) {
    var u = (tr && tr.leap === lp) ? Math.min(1, (tr.leap_n + 1) / Math.max(1, tr.leap_t)) : 0;
    z = lp.h * 4 * u * (1 - u); fy += z;
  }
  if (!tr) { tr = {px: fx, py: fy, fast: false, slow: 99, burst: 0, acc: 0, gacc: 0, wake: null, shed: 0, sign: 1,
    bouncing: false, v0: 0, leap: null, leap_n: 0, leap_t: 1, hop: false, mach: 0, seen: 0, nx: 0, ny: 0, sp: 0, head: [fx, fy], sweep: 0};
    this.tracks.set(fig, tr); }
  tr.seen = this.t;
  var dx = fx - tr.px, dy = fy - tr.py; tr.px = fx; tr.py = fy;
  var jump = Math.hypot(dx, dy);
  if (jump > TELEPORT_PX) { dx = dy = 0; jump = 0; }
  var sp = jump / TICK_S; tr.sp = sp;
  if (jump > 0.01) { tr.nx = dx / jump; tr.ny = dy / jump; }
  tr.head = [fig.x, fig.y];
  var m = fig.motion || {bouncing: false, bounce_ending: false, bounce_vx: 0, bounce_vy: 0};
  this.leapEvents(fig, tr, lp, fx, fy, ps);
  this.hopEvents(fig, tr, fx, fy, ps);
  this.knockEvents(fig, tr, m, fx, fy, ps, jump);
  this.dashEvents(fig, tr, fx, fy, ps, z, dx, dy, sp, hh);
  this.sonicEvents(fig, tr, m, fx, fy, ps, sp, hh);
};
Sim.prototype.leapEvents = function (fig, tr, lp, fx, fy, ps) {
  var c = this.cfg(fig, "jump"), live = lp && !lp.done && lp.h > 0;
  if (live && tr.leap !== lp) {
    tr.leap = lp; tr.leap_n = 0; tr.leap_t = Math.max(1, Math.round((lp.t1 - lp.t0) / TICK_MS));
    if (c.enabled) this.takeoff(fig, fx, fy, ps, 1, c);
  } else if (live) tr.leap_n++;
  else if (tr.leap) {
    var land = tr.leap; tr.leap = null;
    if (c.enabled && c.land) this.landing(fig, land.ex == null ? fx : land.ex, fy, ps, 1, c);
  }
};
Sim.prototype.hopEvents = function (fig, tr, fx, fy, ps) {
  var hop = (fig.hop_ticks || 0) > 0, c = this.cfg(fig, "jump");
  if (hop && !tr.hop && c.enabled && c.hops) this.takeoff(fig, fx, fy, ps, 0.5, c);
  else if (tr.hop && !hop && c.enabled && c.hops && c.land) this.landing(fig, fx, fy, ps, 0.5, c);
  tr.hop = hop;
};
Sim.prototype.takeoff = function (fig, x, y, ps, k, c) {
  var sz = c.size / 100 * k, col = rgb(c.color), fl = this.flat(x, y);
  if (c.ring) this.addRing(new Ring("ground", x, y, 16, 46 * sz * ps, fl, null, [255, 255, 255], 6 * ps * sz));
  this.puffs(x, y, c.dust * k, 2.6, col, sz, 650, 0, 360, [0.05, 0.4], 6);
  this.debris(x, y, "pebble", Math.floor(c.pebbles * k), sz, col, {elev: [55, 75], spd: [4, 8], size: [1.5, 3.5]});
  this.addSrc(new Jet(x, y, 1.6 * ps * sz, 2.2 * ps, 10 * ps, fl));
  if (c.column) this.addSrc(new Column(x, y, 1.4 * ps * sz, 26 * ps * sz, fl));
};
Sim.prototype.landing = function (fig, x, y, ps, k, c) {
  var sz = c.size / 100 * k * 0.6, col = rgb(c.color), fl = this.flat(x, y);
  if (c.ring) this.addRing(new Ring("ground", x, y, 12, 34 * sz * ps, fl, null, null, 4 * ps * sz));
  this.puffs(x, y, c.dust * k * 0.6, 2.2, col, sz, 520, 0, 360, [0.02, 0.25], 6);
  this.addSrc(new Jet(x, y, 1.0 * ps * sz, 2.0 * ps, 8 * ps, fl));
};
Sim.prototype.knockEvents = function (fig, tr, m, fx, fy, ps, jump) {
  var c = this.cfg(fig, "slam"), b = !!m.bouncing, back;
  if (b && !tr.bouncing) {
    tr.v0 = Math.hypot(m.bounce_vx, m.bounce_vy);
    if (c.enabled && c.launch && tr.v0 >= c.min_speed) {
      var s = escale(Math.pow(tr.v0 / 15, 2)) * c.size / 100, col = rgb(c.color), fl = this.flat(fx, fy);
      back = Math.atan2(-m.bounce_vy, -m.bounce_vx) * 180 / Math.PI;
      this.addRing(new Ring("ground", fx, fy, 14, 40 * s * ps, fl, null, null, 5 * ps * s));
      this.puffs(fx, fy, c.dust * 0.5, 2.0, col, s, 700, 0, 360, [0.05, 0.5]);
      this.puffs(fx, fy, c.dust * 0.5, 4.0 * s, col, s, 800, back, 70, [0.1, 0.8]);
      this.debris(fx, fy, "rock", Math.floor(c.rocks * 0.4), s, rgb(c.rock_color), {az: back, spread: 90, elev: [35, 60], spd: [3, 7], size: [2, 4.5]});
    }
  } else if (b && c.enabled && c.skid && jump > 2.5 && this.t % 2 === 0) {
    back = Math.atan2(-m.bounce_vy, -m.bounce_vx) * 180 / Math.PI;
    this.puffs(fx, fy, 1, 1.2, rgb(c.color), c.size / 100 * Math.min(1.6, jump / 8), 600, back, 80, [0.05, 0.3]);
  } else if (!b && tr.bouncing) {
    if (c.enabled && c.crater && tr.v0 >= 2 * Math.max(1, c.min_speed))
      this.crater(fig, fx, fy, ps, escale(Math.pow(tr.v0 / 15, 2)) * c.size / 100, c);
  }
  tr.bouncing = b;
};
Sim.prototype.crater = function (fig, x, y, ps, s, c) {
  var col = rgb(c.color), fl = this.flat(x, y), R = 44 * s * ps, n = Math.floor(c.dust);
  this.addRing(new Ring("ground", x, y, 22, R * 1.4, fl, null, null, 7 * ps * s));
  this.addRing(new Ring("crater", x, y, 70, R * 0.8, fl, null, rgb(c.rock_color), 3 * ps));
  for (var i = 0; i < n; i++) {
    var a = 2 * Math.PI * i / Math.max(1, n) + Math.random() * 0.3;
    this.puff(x + Math.cos(a) * R * 0.7, y + Math.sin(a) * R * 0.7 * fl, 0, Math.cos(a) * 1.2 * ps, Math.sin(a) * 1.2 * ps * fl,
      (0.8 + 1.4 * Math.random()) * ps * s, (600 + 500 * Math.random()) / TICK_MS, 6.5 * s * (0.7 + 0.6 * Math.random()), col, null, 0.02);
  }
  this.debris(x, y, "rock", Math.floor(c.rocks), s, rgb(c.rock_color), {pi: true, spd: [3.5, 10], size: [2, 5]});
  this.addSrc(new Jet(x, y, 2.2 * ps * s, 2.6 * ps, 12 * ps, fl));
};
Sim.prototype.wall = function (fig, edge, x, y, sp) {
  var c = this.cfg(fig, "slam");
  if (!(c.enabled && c.wall) || sp < c.min_speed * 0.6) return;
  var ps = this.ps(x, y), s = escale(Math.pow(sp / 15, 2)) * c.size / 100, col = rgb(c.color);
  var o = {l: [1, 0], r: [-1, 0], t: [0, 1], b: [0, -1]}[edge], ox = o[0], oy = o[1];
  var wx = edge === "l" ? 0 : (edge === "r" ? this.sw : x), wy = edge === "t" ? 0 : (edge === "b" ? this.sh : y);
  this.addRing(new Ring("wall", wx, wy, 26, 70 * s * ps, 1, edge, col, 5 * ps * s));
  for (var i = 0; i < Math.floor(c.dust); i++) {
    var along = (Math.random() - 0.5) * 2, vx, vy, vz, px, py;
    if (edge === "l" || edge === "r") { vx = ox * (0.6 + 1.8 * Math.random()) * ps * s; vy = 0; vz = along * 3.2 * ps * s; px = wx + ox * 4 * ps; py = wy; }
    else { vx = along * 3.2 * ps * s; vy = oy * (0.6 + 1.8 * Math.random()) * ps * s; vz = 0; px = wx; py = wy + oy * 4 * ps; }
    this.puff(px, py, 8 * ps * Math.random(), vx, vy, vz, (600 + 500 * Math.random()) / TICK_MS, 6 * s * (0.7 + 0.6 * Math.random()), col);
  }
  this.debris(wx + ox * 4 * ps, wy + oy * 4 * ps, "rock", Math.floor(c.rocks * 0.7), s, rgb(c.rock_color),
    {az: Math.atan2(oy, ox) * 180 / Math.PI, spread: 120, elev: [15, 55], spd: [3, 8], size: [2, 4.5]});
  this.addSrc(new Jet(wx, wy, 2.0 * ps * s, 2.8 * ps, 12 * ps, 1, (edge === "l" || edge === "r") ? "v" : "h", [ox, oy]));
};
Sim.prototype.dashEvents = function (fig, tr, fx, fy, ps, z, dx, dy, sp, hh) {
  var c = this.cfg(fig, "dash");
  if (!c.enabled) { if (tr.wake) { tr.wake.live = false; tr.wake = null; } tr.fast = false; return; }
  var thr = c.speed, fast = sp >= thr && z < 2, col = rgb(c.color), sz = c.size / 100, vx = dx, vy = dy, R = Math.random;
  if (fast) {
    if (!tr.fast && tr.slow > 6 && c.start_burst) tr.burst = 4;
    tr.slow = 0;
    var k = c.inherit / 100, rate = c.rate * Math.min(3, sp / thr) * (tr.burst > 0 ? 3 : 1);
    tr.acc += rate * TICK_S;
    while (tr.acc >= 1) {
      tr.acc -= 1;
      var spread = 1.2 * ps;
      this.puff(fx - vx * R() + (R() - 0.5) * 6 * ps, fy + (R() - 0.5) * 3 * ps, R() * 2 * ps,
        vx * k + (R() - 0.5) * spread, vy * k + (R() - 0.5) * spread * 0.5, (0.15 + 0.5 * R()) * ps * (tr.burst > 0 ? 1.5 : 1),
        c.life_ms / TICK_MS * (0.7 + 0.6 * R()), (tr.burst <= 0 ? 5 : 6.5) * sz * (0.7 + 0.6 * R()), col);
    }
    tr.gacc += c.grit * Math.min(3, sp / thr) * TICK_S;
    if (tr.gacc >= 1) {
      var n = Math.floor(tr.gacc); tr.gacc -= n;
      this.debris(fx, fy, "pebble", n, sz, col, {az: Math.atan2(-vy, -vx) * 180 / Math.PI, spread: 70, elev: [25, 55], spd: [2, 5], size: [1, 2.2]});
    }
    if (tr.burst > 0) tr.burst--;
    if (c.wake) {
      if (!tr.wake || !tr.wake.live || this.src.indexOf(tr.wake) < 0) tr.wake = this.addSrc(new Wake(fx, fy, hh * 1.2));
      var w = tr.wake;
      w.x = fx; w.y = fy; w.vx = vx; w.vy = vy; w.d = Math.max(6, hh * 1.2);
      w.k = Math.min(0.6 * c.wake_pct / 100, w.k + 0.15);
      if (c.curls) {
        var spt = Math.hypot(vx, vy), D = Math.max(6, hh * 1.6);
        tr.shed += 0.2 * spt / D;
        if (tr.shed >= 1) {
          tr.shed -= 1; tr.sign = -tr.sign;
          var nx = vx / Math.max(0.01, spt), ny = vy / Math.max(0.01, spt), px = -ny, py = nx;
          this.addSrc(new Curl(fx - nx * D * 0.8 + px * tr.sign * D * 0.3, fy - D * 0.3 - ny * D * 0.8 + py * tr.sign * D * 0.3,
            tr.sign * 0.9 * spt * w.k, D * 0.35));
        }
      }
    }
  } else {
    tr.slow++; tr.burst = 0;
    if (tr.wake) { tr.wake.live = false; tr.wake = null; }
  }
  tr.fast = fast;
};
Sim.prototype.sonicEvents = function (fig, tr, m, fx, fy, ps, sp, hh) {
  var c = this.cfg(fig, "sonic"), prev = tr.mach;
  if (!c.enabled || ((m.bouncing || m.bounce_ending) && !c.knockback)) { tr.mach = 0; return; }
  var M = sp / Math.max(1, c.mach); tr.mach = M;
  if (M >= 1 && prev < 1 && c.boom) this.addRing(new Ring("boom", fig.x, fig.y, 18, 46 * ps, 1, null, rgb(c.color), 5 * ps));
  if (M >= 1 && c.sweep) {
    tr.sweep++;
    if (tr.sweep % 4 === 0) {
      var back = hh * Math.sqrt(Math.max(0, M * M - 1)), bx = fx - tr.nx * back, by = fy - tr.ny * back;
      this.addSrc(new Blast(bx, by, 0.7, ps, 40, 0.5, true, this.flat(bx, by)));
      if (Math.random() < 0.5) this.puffs(bx, by, 2, 1.0, rgb(this.world.dash.color), 0.8, 600, 0, 360, [0.05, 0.3]);
    }
  } else tr.sweep = 0;
};
// A clash at (x, y): angle (degrees) = the hit axis, kb = the stronger knockback,
// owners = preview fighters (their feet give the floor).
Sim.prototype.clash = function (x, y, angle, kb, owners) {
  var own = (owners || []).filter(Boolean), c = this.cfg(own[0], "clash");
  if (!(c.enabled && this.world.ground.enabled)) return;
  var ps = this.ps(x, y), s = escale(Math.max(0.05, kb / 100)) * c.size / 100, col = rgb(c.color), perp = angle + 90, self = this;
  var gy = null;
  own.forEach(function (o) { var g0 = self.foot(o, self.ps(o.x, o.y))[1]; gy = gy == null ? g0 : Math.max(gy, g0); });
  var z0 = gy != null ? Math.max(0, gy - y) : 0, floor = gy != null ? gy : y;
  if (c.sheet) for (var i = 0; i < Math.floor(c.dust); i++) {
    var sgn = i % 2 === 0 ? 1 : -1, a = (perp + (Math.random() - 0.5) * 30) * Math.PI / 180, sp = (2 + 3.5 * Math.random()) * ps * s;
    this.puff(x, floor, z0, Math.cos(a) * sp * sgn, 0, -Math.sin(a) * sp * sgn, (450 + 450 * Math.random()) / TICK_MS, 5 * s * (0.7 + 0.6 * Math.random()), col, null, 0);
  }
  this.sparks2d(x, y, perp, Math.floor(c.sparks), s, rgb(c.spark_color), floor);
  this.addRing(new Ring("boom", x, y, 12, 36 * s * ps, 1, null, [255, 255, 255], 4 * ps));
  if (c.ground_jet && gy != null && gy > y + 2) {
    var delay = Math.max(1, Math.floor((gy - y) / Math.max(1, 4.5 * ps * s)));
    this.later.push([this.t + delay, this.clashFloor, [x, gy, s, c]]);
  }
};
Sim.prototype.clashFloor = function (x, y, s, c) {
  var ps = this.ps(x, y), fl = this.flat(x, y);
  this.addRing(new Ring("ground", x, y, 18, 50 * s * ps, fl, null, null, 5 * ps * s));
  this.addSrc(new Jet(x, y, 2.0 * ps * s, 3.0 * ps, 10 * ps, fl));
  this.puffs(x, y, Math.floor(c.dust * 0.8), 3.2 * s, rgb(c.color), s, 700, 0, 360, [0.02, 0.3]);
};
Sim.prototype.sparks2d = function (x, y, az, n, s, col, floor) {
  if (n <= 0) return;
  if (this.bursts.length >= 40) this.bursts.shift();
  var ps = this.ps(x, y), pieces = [];
  for (var i = 0; i < n; i++) {
    var sgn = i % 2 === 0 ? 1 : -1, a = (az + (Math.random() - 0.5) * 50) * Math.PI / 180, sp = (5 + 6 * Math.random()) * Math.sqrt(s) * ps;
    pieces.push([1, 0, Math.cos(a) * sp * sgn, -Math.sin(a) * sp * sgn, 1, 0, 0]);
  }
  var b = new Burst(x, y, ps, this.ssc(x, y), "spark", pieces, 0.22 * ps, 0.974, -1, 20, col);
  b.floor = floor == null ? null : floor;    // they die on this screen y
  this.bursts.push(b);
};
// A technique shot detonating at (x, y) with this damage; fig = its owner.
Sim.prototype.blast = function (x, y, dmg, fig) {
  var c = this.cfg(fig, "blast");
  if (!c.enabled || dmg < c.min_damage) return;
  var ps = this.ps(x, y), s = escale(dmg / 10) * c.size / 100, fl = this.flat(x, y);
  this.addSrc(new Blast(x, y, s, ps, c.reach, c.strength / 100, c.suck_back, fl));
  if (c.ring) this.addRing(new Ring("ground", x, y, 20, c.reach * 0.6 * s * ps, fl, null, null, 4 * ps * s));
  this.puffs(x, y, Math.floor(c.dust * Math.min(2, s)), 1.5, rgb(c.color), s, 900, 0, 360, [0.05, 0.6]);
};
Sim.prototype.move = function () {
  var g = this.world.ground, self = this;
  this.src.forEach(function (s) { s.age += 1; });
  this.src = this.src.filter(function (s) { return s.age < s.life && !(s instanceof Wake && !s.live && s.k < 0.02); });
  this.src.forEach(function (s) { if (s instanceof Wake && !s.live) s.k *= 0.85; });
  this.bursts.forEach(function (b) { b.age += b.ss; });
  this.bursts = this.bursts.filter(function (b) { return b.age < b.life; });
  this.rings.forEach(function (r) { r.age += 1; });
  this.rings = this.rings.filter(function (r) { return r.age < r.life; });
  var cap = Math.floor(g.max_dust);
  if (this.dust.length > cap) this.dust.splice(0, this.dust.length - cap);
  var src = this.src.map(function (s) { return [s].concat(s.bbox()); }), live = [];
  for (var i = 0; i < this.dust.length; i++) {
    var d = this.dust[i], x = d[0], y = d[1], z = d[2], ss = this.ssc(x, y), ux = 0, uy = 0, uz = 0;
    for (var j = 0; j < src.length; j++) {
      var b = src[j];
      if (x < b[1] || x > b[3] || y < b[2] || y > b[4]) continue;
      var a = b[0].air(x, y, z);
      if (a) { ux += a[0]; uy += a[1]; uz += a[2]; }
    }
    var k = Math.exp(-ss / d[9]);
    d[3] = ux + (d[3] - ux) * k; d[4] = uy + (d[4] - uy) * k; d[5] = uz + (d[5] - uz) * k - d[11] * ss;
    d[0] = x + d[3] * ss; d[1] = y + d[4] * ss; z = z + d[5] * ss;
    if (z < 0) { z = 0; if (d[5] < 0) d[5] = 0; d[3] *= 0.9; d[4] *= 0.9; }
    d[2] = z; d[6] += ss;
    if (d[6] < d[7] && d[0] > -50 && d[0] < this.sw + 50 && d[1] > -50 && d[1] < this.sh + 50) live.push(d);
  }
  this.dust = live;
};

// ---------------------------------------------------------------- paint
Sim.prototype.paintGround = function (g) {
  var ink = this.world.ground.ink, self = this;
  this.rings.forEach(function (r) { if (r.kind !== "boom") self.ring(g, r, ink); });
  this.bursts.forEach(function (b) { if (b.kind !== "spark") self.rocks(g, b, ink); });
  this.paintDust(g, ink);
};
Sim.prototype.paintAir = function (g) {
  var self = this, ink = this.world.ground.ink;
  this.rings.forEach(function (r) { if (r.kind === "boom") self.ring(g, r, ink); });
  g.save(); g.globalCompositeOperation = "lighter";
  this.bursts.forEach(function (b) { if (b.kind === "spark") self.sparks(g, b); });
  g.restore();
  this.tracks.forEach(function (tr) { if (tr.mach >= 0.9) self.sonic(g, tr); });
};
Sim.prototype.ring = function (g, r, ink) {
  var u = r.age / r.life, grow = 1 - Math.pow(1 - u, 3), w = Math.max(1, r.w * (1 - u)), rx, ry, a;
  g.save();
  if (r.kind === "crater") {
    a = 150 * (1 - Math.floor(u * 4) / 4) / 255;
    g.lineWidth = Math.max(1, r.w); g.strokeStyle = css(r.col, a);
    g.beginPath(); g.ellipse(r.x, r.y, r.r, r.r * r.flat, 0, 0, 2 * Math.PI); g.stroke();
    g.lineWidth = Math.max(1, r.w * 2.5); g.strokeStyle = "rgba(0,0,0," + (a / 2) + ")";
    g.beginPath(); g.ellipse(r.x, r.y, r.r * 0.6, r.r * 0.6 * r.flat, 0, 0, 2 * Math.PI); g.stroke();
    g.restore(); return;
  }
  var rad = r.r * (0.25 + 0.75 * grow);
  if (r.kind === "wall") {
    if (r.edge === "l" || r.edge === "r") { rx = rad * 0.16; ry = rad; } else { rx = rad; ry = rad * 0.16; }
    a = 230 * (1 - u) / 255;
    g.beginPath(); g.ellipse(r.x, r.y, rx, ry, 0, 0, 2 * Math.PI);
    g.fillStyle = css(r.col, a); g.fill();
    g.lineWidth = w + 3; g.strokeStyle = ink; g.stroke();
    g.lineWidth = w; g.strokeStyle = "rgba(255,255,255," + a + ")"; g.stroke();
    g.restore(); return;
  }
  var fl = r.kind === "ground" ? r.flat : 1;
  a = 1 - u * u;
  g.beginPath(); g.ellipse(r.x, r.y, rad, rad * fl, 0, 0, 2 * Math.PI);
  g.globalAlpha = a; g.lineWidth = w + 3; g.strokeStyle = ink; g.stroke();
  g.lineWidth = w; g.strokeStyle = css(r.col); g.stroke();
  g.restore();
};
Sim.prototype.rocks = function (g, b, ink) {
  var fade = b.age < b.life * 0.75 ? 1 : Math.max(0, (b.life - b.age) / (b.life * 0.25));
  if (fade <= 0) return;
  var col = css(b.col), lit = css([Math.min(255, b.col[0] + 60), Math.min(255, b.col[1] + 60), Math.min(255, b.col[2] + 60)]);
  g.save(); g.globalAlpha = fade; g.lineWidth = 1.2; g.strokeStyle = ink;
  for (var i = 0; i < b.pieces.length; i++) {
    var pc = b.pieces[i], at = b.at(pc, b.age);
    if (!at) continue;
    var x = at[0], sy = at[1] - at[2], s = pc[4] * (b.kind === "rock" ? 1 : 0.7), rot = at[2] > 0 ? pc[6] + pc[5] * b.age : pc[6], pts = [];
    for (var k = 0; k < 4; k++) {
      var a = rot + k * 1.5708 + (k % 2 ? 0.25 : -0.1), rr = s * (k % 2 === 0 ? 1 : 0.8);
      pts.push([x + Math.cos(a) * rr, sy + Math.sin(a) * rr]);
    }
    g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (k = 1; k < 4; k++) g.lineTo(pts[k][0], pts[k][1]); g.closePath();
    g.fillStyle = col; g.fill(); g.stroke();
    g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); g.lineTo(pts[1][0], pts[1][1]); g.lineTo(x, sy); g.closePath();
    g.fillStyle = lit; g.fill();
  }
  g.restore();
};
Sim.prototype.sparks = function (g, b) {
  g.lineCap = "round";
  for (var i = 0; i < b.pieces.length; i++) {
    var pc = b.pieces[i], x0, y0, x1, y1;
    if (b.e < 0) {
      if (b.age > 20) continue;
      var h = pc[2], v = pc[3], k = b.k;
      var pos = function (tt) { var f = (1 - Math.pow(k, tt)) / (1 - k); return [b.x + h * f, b.y - (v * f - 0.5 * b.g * tt * tt)]; };
      var p1 = pos(b.age), p0 = pos(Math.max(0, b.age - 2)); x1 = p1[0]; y1 = p1[1]; x0 = p0[0]; y0 = p0[1];
      if (b.floor != null && y0 > b.floor) continue;   // it hit the floor
      if (b.floor != null && y1 > b.floor) y1 = b.floor;
    } else {
      var a1 = b.at(pc, b.age), a0 = b.at(pc, Math.max(0, b.age - 2));
      if (!a1 || !a0) continue;
      x1 = a1[0]; y1 = a1[1] - a1[2]; x0 = a0[0]; y0 = a0[1] - a0[2];
    }
    var w = Math.max(1, 1.5 * b.ps);
    g.strokeStyle = css(b.col, 0.55); g.lineWidth = w * 2.2; g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
    g.strokeStyle = "rgba(255,255,255,0.9)"; g.lineWidth = w * 0.7; g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
  }
};
Sim.prototype.sonic = function (g, tr) {
  var M = tr.mach, x = tr.head[0], y = tr.head[1], nx = tr.nx, ny = tr.ny, c = this.world.sonic;
  if (!nx && !ny) return;
  var ps = this.ps(x, y), tip = [x + nx * 14 * ps, y + ny * 14 * ps];
  g.save();
  if (M >= 0.9 && M < 1.25 && c.vapor) {
    var a = (60 + 90 * Math.random()) / 255;
    g.save(); g.translate(x - nx * 4 * ps, y - ny * 4 * ps); g.rotate(Math.atan2(ny, nx));
    g.beginPath(); g.ellipse(0, 0, 5 * ps, 16 * ps, 0, 0, 2 * Math.PI);
    g.fillStyle = "rgba(235,245,255," + a + ")"; g.fill(); g.restore();
  }
  if (M >= 1 && c.cone) {
    var mu = Math.asin(Math.min(1, 1 / M)), L = 90 * ps, back = Math.atan2(-ny, -nx), col = rgb(c.color);
    [-1, 1].forEach(function (sgn) {
      var an = back + sgn * mu, ex = tip[0] + Math.cos(an) * L, ey = tip[1] + Math.sin(an) * L;
      var ox = -Math.sin(an) * 2 * sgn, oy = Math.cos(an) * 2 * sgn;
      g.lineWidth = 3 * Math.max(1, ps * 0.6); g.strokeStyle = "rgba(0,0,0,0.6)";
      g.beginPath(); g.moveTo(tip[0], tip[1]); g.lineTo(ex, ey); g.stroke();
      g.lineWidth = 1.5 * Math.max(1, ps * 0.6); g.strokeStyle = css(col, 0.82);
      g.beginPath(); g.moveTo(tip[0] + ox, tip[1] + oy); g.lineTo(ex + ox, ey + oy); g.stroke();
    });
  }
  g.restore();
};
Sim.prototype.paintDust = function (g, ink) {
  var items = [];
  for (var i = 0; i < this.dust.length; i++) {
    var d = this.dust[i], u = d[6] / d[7], gr;
    if (u < 0.6) gr = 1 + (1 - Math.pow(1 - u / 0.6, 2));
    else gr = 2 * (1 - (Math.floor((u - 0.6) / 0.4 * 3) + 1) / 4);
    var r = d[8] * gr * this.ps(d[0], d[1]) * 0.5;
    if (r < 1) continue;
    items.push([d[0], d[1] - d[2], Math.min(60, Math.round(r)), d[10]]);
  }
  if (!items.length) return;
  g.save();
  // Pass 1: every ink outline; pass 2: every fill (shadow, base, light),
  // so overlapping puffs merge into one outlined cloud.
  g.fillStyle = ink;
  g.beginPath();
  items.forEach(function (it) { g.moveTo(it[0] + it[2] + 2, it[1]); g.arc(it[0], it[1], it[2] + 2, 0, 2 * Math.PI); });
  g.fill();
  items.forEach(function (it) {
    var x = it[0] - it[2], y = it[1] - it[2], n = 2 * it[2], c = it[3];
    g.fillStyle = css([Math.floor(c[0] * 0.7), Math.floor(c[1] * 0.7), Math.floor(c[2] * 0.7)]);
    g.beginPath(); g.arc(x + n / 2, y + n / 2, n / 2, 0, 2 * Math.PI); g.fill();
    g.fillStyle = css(c);
    g.beginPath(); g.arc(x + n * 0.43, y + n * 0.43, n * 0.43, 0, 2 * Math.PI); g.fill();
    g.fillStyle = css([Math.floor(c[0] + (255 - c[0]) * 0.5), Math.floor(c[1] + (255 - c[1]) * 0.5), Math.floor(c[2] + (255 - c[2]) * 0.5)]);
    g.beginPath(); g.ellipse(x + n * 0.34, y + n * 0.29, n * 0.2, n * 0.17, 0, 0, 2 * Math.PI); g.fill();
  });
  g.restore();
};

window.WORLDFX = {
  FORMAT: WP_FORMAT, FILE: "world_physics.json", SECTIONS: WP_SECTIONS, DEFAULTS: WP_DEFAULTS, RANGES: WP_RANGES,
  FIELDS: WP_FIELDS, TITLES: WP_TITLES, TICK_MS: TICK_MS,
  normalize: normalize, normalizeSection: normalizeSection, normalizeOverride: normalizeOverride,
  Sim: Sim, pscale: function (x, y, sw, sh) { return bil(clamp01(x / sw), clamp01(y / sh), PS); }
};
})();
