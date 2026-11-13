// Fight rhythm (pack.fight_rhythm) — the Studio side of laser/tempo.py.
//
// Tables (TEMPO_DEFAULTS / TEMPO_RANGES / TEMPO_PRESETS / TEMPO_INTENTS /
// TEMPO_ENUMS) mirror laser/tempo.py DEFAULTS / RANGES / PRESETS / INTENTS /
// ENUMS (tools/fx/check_parity.py).  The live preview runs a small sparring
// sim with the same intent machine (neutral / feint / engage / pressure /
// punish / reset / wait), the fight director (Dust & Air "Fight director")
// and melee attack tokens: this character (blue, plus an optional team-mate)
// against a sparring dummy (red) with a temperament of its own.  Attacks are
// plain 300 ms swings that hit inside reach; the game uses the character's
// real actions.
(function (G) {
"use strict";

var TICK_MS = 16;
var TEMPO_INTENTS = ["neutral", "feint", "engage", "pressure", "punish", "reset", "wait"];
var TEMPO_PHASES = ["calm", "build", "burst"];
var TEMPO_ENUMS = {
  preset: ["custom", "berserker", "duelist", "trickster", "counter", "sniper"],
  role: ["auto", "vanguard", "striker", "flanker", "controller", "support"],
  movement: ["auto", "always", "speed_only"],
  wait_style: ["mixed", "flank", "circle", "zone"],
  feint_kind: ["mixed", "dash_in", "fake_retreat"]
};
var TEMPO_DEFAULTS = {
  enabled: false, preset: "duelist", role: "auto", movement: "auto", wait_style: "mixed",
  neutral_ms_min: 700, neutral_ms_max: 2200, spacing_px: 60, sway_px: 40,
  feint_pct: 25, feint_kind: "mixed", feint_ms: 380,
  engage_speed_pct: 175, engage_ms_max: 1400,
  string_min: 2, string_max: 5, gap_start_ms: 380, gap_end_ms: 80, gap_jitter_pct: 35,
  pressure_speed_pct: 115,
  punish_pct: 70, punish_range_px: 280, punish_ms: 900, punish_speed_pct: 230,
  reset_ms_min: 350, reset_ms_max: 1100, reset_px: 220,
  director_pct: 100, aggression_pct: 100, momentum_pct: 35, gate_triggered: false
};
var TEMPO_RANGES = {
  neutral_ms_min: [0, 20000], neutral_ms_max: [0, 20000], spacing_px: [-200, 2000], sway_px: [0, 600],
  feint_pct: [0, 100], feint_ms: [50, 5000], engage_speed_pct: [10, 1000], engage_ms_max: [100, 20000],
  string_min: [1, 30], string_max: [1, 30], gap_start_ms: [0, 5000], gap_end_ms: [0, 5000],
  gap_jitter_pct: [0, 100], pressure_speed_pct: [10, 1000],
  punish_pct: [0, 100], punish_range_px: [0, 3000], punish_ms: [50, 10000], punish_speed_pct: [10, 1000],
  reset_ms_min: [0, 20000], reset_ms_max: [0, 20000], reset_px: [0, 3000],
  director_pct: [0, 300], aggression_pct: [10, 400], momentum_pct: [0, 200]
};
var TEMPO_PRESETS = {
  custom: {},
  berserker: {neutral_ms_min: 250, neutral_ms_max: 900, feint_pct: 8, engage_speed_pct: 210,
              string_min: 4, string_max: 8, gap_start_ms: 260, gap_end_ms: 50,
              punish_pct: 85, reset_ms_min: 200, reset_ms_max: 600, reset_px: 140,
              aggression_pct: 140, wait_style: "circle"},
  duelist: {},
  trickster: {feint_pct: 60, feint_ms: 420, neutral_ms_min: 600, neutral_ms_max: 1800,
              string_min: 2, string_max: 4, gap_start_ms: 340, gap_end_ms: 90,
              wait_style: "flank", feint_kind: "mixed"},
  counter: {neutral_ms_min: 1200, neutral_ms_max: 3000, feint_pct: 15, punish_pct: 100,
            punish_range_px: 340, punish_speed_pct: 260, string_min: 2, string_max: 3,
            aggression_pct: 70},
  sniper: {spacing_px: 220, neutral_ms_min: 900, neutral_ms_max: 2400, engage_speed_pct: 130,
           string_min: 3, string_max: 6, gap_start_ms: 300, gap_end_ms: 140,
           wait_style: "zone", reset_px: 320, punish_pct: 40}
};
var ROLE_WAIT = {vanguard: "circle", flanker: "flank", support: "zone", controller: "circle"};
var OPEN_MS = 260, STRING_BURST_BONUS = 2, PUNISH_OWN_MS = 700;
var PUNISH_FROM = ["neutral", "wait", "feint", "reset"], PUNISH_CD_MS = 1500, WHIFF_MS = 500;

function normalize(raw) {
  raw = raw && typeof raw === "object" ? raw : {};
  var out = {};
  Object.keys(TEMPO_DEFAULTS).forEach(function (k) {
    var d = TEMPO_DEFAULTS[k], v = k in raw ? raw[k] : d;
    if (typeof d === "boolean") out[k] = !!v;
    else if (TEMPO_ENUMS[k]) out[k] = TEMPO_ENUMS[k].indexOf(v) >= 0 ? v : d;
    else {
      var f = parseFloat(v); if (!isFinite(f)) f = d;
      var r = TEMPO_RANGES[k] || [-1e9, 1e9];
      out[k] = Math.max(r[0], Math.min(r[1], f));
    }
  });
  return out;
}
// The settings of a temperament: DEFAULTS + its changes (keeps on / role /
// movement of `cur`).
function presetValues(name, cur) {
  var o = normalize(Object.assign({}, TEMPO_DEFAULTS, TEMPO_PRESETS[name] || {}));
  o.preset = name;
  if (cur) { o.enabled = cur.enabled; o.role = cur.role; o.movement = cur.movement; o.gate_triggered = cur.gate_triggered; }
  return o;
}

// ------------------------------------------------------------ preview sim
function ticks(ms) { return Math.max(1, Math.round(ms / TICK_MS)); }
function Rng(seed) { this.s = seed >>> 0 || 1; }
Rng.prototype.next = function () { this.s = (this.s * 1664525 + 1013904223) >>> 0; return this.s / 4294967296; };
Rng.prototype.uni = function (a, b) { return a + (b - a) * this.next(); };

// The director settings: the Studio's live Dust & Air ones when the page
// passes them (opts.director), else the defaults.
function directorCfg(live) {
  var d = (G.WORLDFX && G.WORLDFX.DEFAULTS && G.WORLDFX.DEFAULTS.director) || {};
  return Object.assign({}, d, live || {});
}

function Fighter(name, team, cfg, x, y, rng, color) {
  this.name = name; this.team = team; this.cfg = cfg; this.x = x; this.y = y; this.color = color;
  this.rng = rng; this.hp = 100; this.intent = "neutral"; this.since = 0; this.until = 0;
  this.string_n = 0; this.string_done = 0; this.momentum = 0; this.orbit = rng.next() < 0.5 ? 1 : -1;
  this.sway_ph = rng.uni(0, 6.28); this.sway_ms = rng.uni(900, 2200); this.feint_kind = "dash_in";
  this.feint_bit = false; this.open_seen = false; this.reset_ang = 0; this.wait_style = "circle";
  this.atk_until = -1; this.atk_end = -1e9; this.gap_until = 0; this.daze = 0; this.kbx = 0; this.kby = 0;
  this.last_landed = -1e9; this.punish_ready = 0; this.role = "striker"; this.flash = 0; this.target = null; this.far = 0; this.hits_at = [];
  this.reach = 70; this.speed = 2.6; this.label = "";
}
Fighter.prototype.aggr = function () { return this.cfg.aggression_pct / 100 * (1 + this.cfg.momentum_pct / 100 * this.momentum); };
Fighter.prototype.randMs = function (lo, hi, k) {
  if (hi < lo) { var t = lo; lo = hi; hi = t; }
  var u = this.rng.next(); u = this.rng.next() < 0.5 ? u * u : 1 - (1 - u) * (1 - u);
  return ticks(Math.max(0, (lo + (hi - lo) * u) * (k == null ? 1 : k)));
};

function Sim(cfgA, cfgB, opts) {
  opts = opts || {};
  this.w = 360; this.h = 190; this.tick = 0; this.rng = new Rng(opts.seed || 12345);
  this.I = 0; this.phase = "calm"; this.burstLeft = 0; this.burstAt = null; this.quiet = 0; this.hist = [];
  this.tokens = opts.tokens == null ? 1 : opts.tokens;
  this.dirLive = opts.director || null;
  this.events = [];
  this.figs = [new Fighter("you", 0, cfgA, 90, 95, new Rng((opts.seed || 12345) + 1), "#3fb0ea")];
  if (opts.mate) this.figs.push(new Fighter("mate", 0, cfgA, 70, 140, new Rng((opts.seed || 12345) + 7), "#7fd0ff"));
  this.figs.push(new Fighter("dummy", 1, cfgB, 270, 95, new Rng((opts.seed || 12345) + 3), "#ff6b6b"));
  var self = this;
  this.figs.forEach(function (f, i) {
    var melee = f.cfg.spacing_px < 160;
    f.melee = melee; f.reach = melee ? 70 : 170;
    f.role = f.cfg.role !== "auto" ? f.cfg.role : (melee ? (i === 0 || f.team === 1 ? "striker" : "flanker") : "support");
    self.enter(f, "neutral");
  });
  this.board = {0: {}, 1: {}};
}
Sim.prototype.enemyOf = function (f) {
  var best = null, bd = 1e9;
  this.figs.forEach(function (g) { if (g.team !== f.team) { var d = Math.hypot(g.x - f.x, g.y - f.y); if (d < bd) { bd = d; best = g; } } });
  return best;
};
Sim.prototype.tokenFree = function (f) {
  if (!f.melee || this.tokens <= 0) return true;
  var b = this.board[f.team], n = 0, now = this.tick;
  Object.keys(b).forEach(function (k) { if (k !== f.name && now - b[k] <= 3) n++; });
  return n < this.tokens;
};
Sim.prototype.enter = function (f, it) {
  var c = f.cfg, I = this.I * c.director_pct / 100, burst = this.phase === "burst" && c.director_pct > 0;
  var prev = f.intent; f.intent = it; f.since = this.tick;
  if (it === "neutral" || it === "wait") {
    var k = (1 - 0.6 * I) * (burst ? 0.45 : 1) / Math.max(0.25, f.aggr());
    f.until = this.tick + f.randMs(c.neutral_ms_min, c.neutral_ms_max, k);
    if (it === "wait") f.until = this.tick + Math.max(ticks(200), Math.floor((f.until - this.tick) / 2));
  } else if (it === "feint") {
    var kind = c.feint_kind === "mixed" ? (f.rng.next() < 0.6 ? "dash_in" : "fake_retreat") : c.feint_kind;
    f.feint_kind = kind; f.feint_bit = false;
    f.until = this.tick + f.randMs(c.feint_ms * 0.7, c.feint_ms * 1.3);
  } else if (it === "engage") {
    f.until = this.tick + ticks(c.engage_ms_max);
    var lo = Math.round(Math.min(c.string_min, c.string_max)), hi = Math.round(Math.max(c.string_min, c.string_max));
    f.string_n = lo + Math.floor(f.rng.next() * (hi - lo + 1)) + (burst ? STRING_BURST_BONUS : 0);
    f.string_done = 0;
  } else if (it === "punish") {
    f.until = this.tick + f.randMs(c.punish_ms * 0.8, c.punish_ms * 1.2);
    f.open_seen = true;
    if (f.string_n - f.string_done < 2) f.string_n = f.string_done + 2 + Math.floor(f.rng.next() * 3);
  } else if (it === "reset") {
    f.until = this.tick + f.randMs(c.reset_ms_min, c.reset_ms_max, burst ? 0.5 : 1);
    f.reset_ang = f.rng.uni(-0.8, 0.8);
    if (f.rng.next() < 0.5) f.orbit = -f.orbit;
  } else if (it === "pressure") f.until = this.tick + ticks(8000);
  if (it === "feint" || it === "punish" || it === "engage") this.events.push([this.tick, f.color, it.toUpperCase()]);
};
Sim.prototype.think = function (f) {
  var c = f.cfg, e = this.enemyOf(f), now = this.tick;
  if (!e) return;
  f.target = e;
  var I = this.I * c.director_pct / 100, burst = this.phase === "burst";
  var dist = Math.hypot(e.x - f.x, e.y - f.y);
  var took = f.hits_at.some(function (t) { return now - t <= ticks(WHIFF_MS); });
  var open = (e.daze > 0 || (!took && e.atk_until < now && now - e.atk_end <= ticks(OPEN_MS))) && now - f.last_landed > ticks(PUNISH_OWN_MS);
  if (!open) f.open_seen = false;
  if (open && !f.open_seen && now >= f.punish_ready && dist <= c.punish_range_px && PUNISH_FROM.indexOf(f.intent) >= 0) {
    f.open_seen = true;
    if (f.rng.next() * 100 < c.punish_pct * (0.7 + 0.6 * I) && this.tokenFree(f)) this.enter(f, "punish");
  }
  var it = f.intent;
  if (it === "neutral" || it === "wait") {
    var tok = this.tokenFree(f);
    if (tok && dist <= f.reach && (now - f.since) % ticks(200) === 0 && f.rng.next() < 0.35 * f.aggr() * (0.6 + I)) this.enter(f, "engage");
    else if (now >= f.until) {
      if (!tok) { f.wait_style = c.wait_style === "mixed" ? (ROLE_WAIT[f.role] || ["flank", "circle", "zone"][Math.floor(f.rng.next() * 3)]) : c.wait_style; this.enter(f, "wait"); }
      else if (f.rng.next() * 100 < c.feint_pct * (0.7 + 0.8 * I)) this.enter(f, "feint");
      else this.enter(f, "engage");
    }
  } else if (it === "feint") {
    if (e.atk_until >= now) f.feint_bit = true;
    if (now >= f.until) {
      if (f.feint_bit && f.rng.next() * 100 < c.punish_pct) this.enter(f, "punish");
      else if (f.feint_kind === "fake_retreat") this.enter(f, "engage");
      else { this.enter(f, "neutral"); f.until = f.since + Math.max(ticks(150), Math.floor((f.until - f.since) / 3)); }
    }
  } else if (it === "engage") {
    if (now >= f.until) this.enter(f, "reset");
  } else if (it === "pressure" || it === "punish") {
    f.far = dist > f.reach * 2.5 ? f.far + 1 : 0;
    var recent = f.hits_at.filter(function (t) { return now - t <= ticks(500); }).length;
    if (it === "punish" && now >= f.until) { f.punish_ready = now + ticks(PUNISH_CD_MS); this.enter(f, "pressure"); }
    else if ((f.string_done >= f.string_n && f.atk_until < now) || f.far > ticks(600) || recent >= 2) this.enter(f, "reset");
  } else if (it === "reset" && now >= f.until) this.enter(f, "neutral");
  if (f.melee && ["engage", "pressure", "punish"].indexOf(f.intent) >= 0) {
    if (this.tokenFree(f)) this.board[f.team][f.name] = now;
    else if (f.intent !== "punish") { f.wait_style = c.wait_style === "mixed" ? (ROLE_WAIT[f.role] || "circle") : c.wait_style; this.enter(f, "wait"); }
  } else delete this.board[f.team][f.name];
  // attack: only in attack intents (ranged keep zoning while waiting)
  var may = ["engage", "pressure", "punish"].indexOf(f.intent) >= 0 || (f.intent === "wait" && !f.melee);
  if (may && f.atk_until < now && now >= f.gap_until && dist <= f.reach && f.daze <= 0) {
    f.atk_until = now + ticks(300);
    if (f.intent === "engage") { this.enter(f, "pressure"); }
    f.string_done++;
    f.swing = true;
  }
};
Sim.prototype.moveTarget = function (f) {
  var c = f.cfg, e = f.target; if (!e) return [f.x, f.y];
  var dx = f.x - e.x, dy = f.y - e.y, d = Math.hypot(dx, dy) || 1, ux = dx / d, uy = dy / d, now = this.tick;
  var ring = function (r, lead) { var a = Math.atan2(uy, ux) + lead * f.orbit; return [e.x + Math.cos(a) * r, e.y + Math.sin(a) * r]; };
  var it = f.intent;
  if (it === "neutral") {
    var sw = c.sway_px * Math.sin(f.sway_ph + 2 * Math.PI * now * TICK_MS / f.sway_ms);
    if (f.rng.next() < 0.004) f.orbit = -f.orbit;
    return ring(Math.max(10, f.reach + c.spacing_px + sw), 0.35);
  }
  if (it === "wait") {
    if (f.wait_style === "flank") return [e.x + (e.x > f.x ? 1 : -1) * (f.reach + 40), e.y + 20 * f.orbit];
    if (f.wait_style === "zone") return ring(Math.max(f.reach * 1.6, 160), 0.15);
    return ring(Math.max(f.reach * 1.4, f.reach + 90), 0.5);
  }
  if (it === "feint") {
    var u = (now - f.since) / Math.max(1, f.until - f.since);
    if (f.feint_kind === "fake_retreat") return [e.x + ux * (d + 160), e.y + uy * (d + 160)];
    if (u < 0.6 && d > f.reach * 1.15) return [e.x + ux * f.reach * 1.1, e.y + uy * f.reach * 1.1];
    return ring(f.reach * 1.6, 1.1);
  }
  if (it === "reset") { var a = Math.atan2(uy, ux) + f.reset_ang; return [e.x + Math.cos(a) * (d + c.reset_px), e.y + Math.sin(a) * (d + c.reset_px)]; }
  return [e.x + ux * f.reach * 0.5, e.y + uy * f.reach * 0.5];
};
Sim.prototype.speedMult = function (f) {
  var c = f.cfg;
  return {engage: c.engage_speed_pct, punish: c.punish_speed_pct, pressure: c.pressure_speed_pct,
          feint: c.engage_speed_pct * 1.1, reset: 120}[f.intent] / 100 || 1;
};
Sim.prototype.step = function () {
  var self = this, now = this.tick, dc = directorCfg(this.dirLive), dt = TICK_MS / 1000, add = 0, hits = 0;
  this.figs.forEach(function (f) { self.think(f); });
  this.figs.forEach(function (f) {
    if (f.daze > 0) { f.daze--; f.x += f.kbx; f.y += f.kby; f.kbx *= 0.86; f.kby *= 0.86; }
    else {
      var p = self.moveTarget(f);
      // the arena's walls (the game's wall repulsion): aim inside them
      p = [p[0] + (self.w / 2 - p[0]) * 0.12, p[1] + ((self.h - 40) / 2 - p[1]) * 0.12];
      p = [Math.max(30, Math.min(self.w - 30, p[0])), Math.max(24, Math.min(self.h - 56, p[1]))];
      var dx = p[0] - f.x, dy = p[1] - f.y, d = Math.hypot(dx, dy), s = f.speed * self.speedMult(f);
      if (f.atk_until >= now) s *= 0.3;
      if (d > 0.5) { f.x += dx / d * Math.min(s, d); f.y += dy / d * Math.min(s, d); }
    }
    f.x = Math.max(12, Math.min(self.w - 12, f.x)); f.y = Math.max(18, Math.min(self.h - 50, f.y));
    if (f.flash > 0) f.flash--;
    // a swing lands at its middle if the target is in reach
    if (f.atk_until >= now && f.atk_until - now === ticks(150) && f.target) {
      var e = f.target;
      if (Math.hypot(e.x - f.x, e.y - f.y) <= f.reach * 1.1 && e.intent !== "reset" || (e.daze > 0 && Math.hypot(e.x - f.x, e.y - f.y) <= f.reach * 1.3)) {
        hits++; e.hits_at.push(now); e.hp = Math.max(5, e.hp - 4); f.momentum = Math.min(1, f.momentum + 0.15); f.last_landed = now; e.momentum = Math.max(-1, e.momentum - 0.2);
        var k = Math.hypot(e.x - f.x, e.y - f.y) || 1; e.kbx = (e.x - f.x) / k * 3; e.kby = (e.y - f.y) / k * 3; e.daze = ticks(160);
        e.flash = 8; e.atk_until = -1;
      }
    }
    if (f.atk_until === now) {
      f.atk_end = now;
      // uneven accelerating gaps
      var c = f.cfg, u = Math.min(1, f.string_done / Math.max(1, f.string_n)), g = c.gap_start_ms + (c.gap_end_ms - c.gap_start_ms) * Math.pow(u, 0.7);
      if (f.intent === "punish") g = Math.min(g, c.gap_end_ms) * 0.5;
      if (self.phase === "burst") g *= 0.7;
      var j = c.gap_jitter_pct / 100; g *= 1 + f.rng.uni(-j, j);
      f.gap_until = now + Math.round(Math.max(0, g) / TICK_MS);
    }
    f.momentum *= 1 - 0.15 * dt;
    f.hits_at = f.hits_at.filter(function (t) { return now - t < ticks(1000); });
    if (f.hp < 30 && f.rng.next() < 0.002) f.hp = 100;
  });
  // director
  var dmin = 1e9;
  this.figs.forEach(function (a) { self.figs.forEach(function (b) { if (a.team !== b.team) dmin = Math.min(dmin, Math.hypot(a.x - b.x, a.y - b.y)); }); });
  if (this.burstAt === null) this.burstAt = Math.max(0.05, dc.burst_at / 100 * (1 + this.rng.uni(-dc.burst_jitter_pct / 100, dc.burst_jitter_pct / 100)));
  add += hits * dc.hit_pct / 100 + hits * 4 / 100 * dc.damage_pct / 100 + hits * 4 / 100 * dc.hp_swing_pct / 100;
  if (dc.close_px > 0) add += Math.max(0, 1 - dmin / dc.close_px) * dc.close_pct_s / 100 * dt;
  this.quiet = hits ? 0 : this.quiet + 1;
  if (this.quiet * dt >= dc.idle_after_s) add += dc.idle_pct_s / 100 * dt;
  if (!dc.enabled) { this.I = 0; this.phase = "calm"; }
  else if (this.phase === "burst") {
    this.burstLeft--; this.I = Math.min(1, this.I + add * 0.25);
    if (this.burstLeft <= 0) { this.I = dc.after_burst_pct / 100; this.phase = "calm"; this.burstAt = null; }
  } else {
    this.I = Math.max(0, Math.min(1, this.I + add - dc.decay_pct_s / 100 * dt));
    if (this.burstAt !== null && this.I >= this.burstAt) { this.phase = "burst"; this.burstLeft = ticks(1000 * this.rng.uni(Math.min(dc.burst_s_min, dc.burst_s_max), Math.max(dc.burst_s_min, dc.burst_s_max))); this.events.push([now, "#ff463c", "BURST"]); }
    else this.phase = this.I >= dc.build_at / 100 ? "build" : "calm";
  }
  this.hist.push([this.I, this.phase]); if (this.hist.length > 360) this.hist.shift();
  this.events = this.events.filter(function (ev) { return now - ev[0] < ticks(900); });
  this.tick++;
};
var INTENT_COLOR = {neutral: "#c8c8c8", feint: "#ffa040", engage: "#ffe14d", pressure: "#ff463c",
  punish: "#ff5fd2", reset: "#4fd1ff", wait: "#7dff6a"};
var PHASE_COLOR = {calm: "#4fd1ff", build: "#ffe14d", burst: "#ff463c"};
Sim.prototype.draw = function (cv) {
  var g = cv.getContext("2d"), W = cv.width, H = cv.height, sc = W / this.w, self = this, now = this.tick;
  g.clearRect(0, 0, W, H);
  g.fillStyle = "#11141a"; g.fillRect(0, 0, W, H);
  g.font = "bold " + Math.round(10 * sc) + "px Consolas, monospace";
  // token lines
  this.figs.forEach(function (f) {
    if (self.board[f.team][f.name] === undefined || !f.target) return;
    g.strokeStyle = "rgba(255,225,77,.55)"; g.setLineDash([4, 4]); g.beginPath();
    g.moveTo(f.x * sc, f.y * sc); g.lineTo(f.target.x * sc, f.target.y * sc); g.stroke(); g.setLineDash([]);
  });
  this.figs.forEach(function (f) {
    g.strokeStyle = "rgba(255,255,255,.08)"; g.beginPath(); g.arc(f.x * sc, f.y * sc, f.reach * sc, 0, 7); g.stroke();
    var r = 7 * sc;
    if (f.atk_until >= now) { g.fillStyle = "rgba(255,255,255,.35)"; g.beginPath(); g.arc(f.x * sc, f.y * sc, r * 2.1, 0, 7); g.fill(); }
    g.fillStyle = f.flash > 0 ? "#ffffff" : f.color;
    g.beginPath(); g.arc(f.x * sc, f.y * sc, r, 0, 7); g.fill();
    var txt = f.intent.toUpperCase() + (["engage", "pressure", "punish"].indexOf(f.intent) >= 0 ? " " + f.string_done + "/" + f.string_n : f.intent === "wait" ? " (" + f.wait_style + ")" : f.intent === "feint" ? " (" + f.feint_kind.replace("_", " ") + ")" : "");
    g.fillStyle = INTENT_COLOR[f.intent] || "#fff";
    g.fillText(txt, f.x * sc - 26 * sc, f.team === 1 ? f.y * sc + 20 * sc : f.y * sc - 13 * sc);   // dummy's label below it
  });
  // director bar + graph
  var gy = H - 34 * sc, gh = 30 * sc;
  g.fillStyle = "#0b0d12"; g.fillRect(0, gy, W, gh + 4 * sc);
  this.hist.forEach(function (h, i) {
    g.fillStyle = PHASE_COLOR[h[1]]; var x = i / 360 * W, y = gy + gh - h[0] * gh;
    g.fillRect(x, y, Math.max(1, W / 360), gy + gh - y);
  });
  g.fillStyle = "rgba(0,0,0,.6)"; g.fillRect(2 * sc, gy + 1 * sc, 150 * sc, 13 * sc);
  g.fillStyle = PHASE_COLOR[this.phase]; g.fillText("DIRECTOR " + Math.round(this.I * 100) + "% " + this.phase.toUpperCase(), 6 * sc, gy + 11 * sc);
  this.events.forEach(function (ev, i) { g.fillStyle = ev[1]; g.fillText(ev[2], W - 70 * sc, 14 * sc + i * 12 * sc); });
};

G.TEMPO = {DEFAULTS: TEMPO_DEFAULTS, RANGES: TEMPO_RANGES, PRESETS: TEMPO_PRESETS, INTENTS: TEMPO_INTENTS,
  PHASES: TEMPO_PHASES, ENUMS: TEMPO_ENUMS, normalize: normalize, presetValues: presetValues, Sim: Sim};
})(typeof window !== "undefined" ? window : this);
