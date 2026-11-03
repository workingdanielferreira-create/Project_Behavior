// World Camera — FX Studio's port of laser/camera.py.
//
// The dynamic action camera: a paint-time VIEW only (the game never moves a
// fighter for it).  Follow-cam frames every fielded fighter and eases there
// (Battle zooms in up to max_zoom when the fight is tight, Solo follows at a
// light fixed solo_zoom; never below 1.0x, never off-screen); a hit-stop
// punches in toward the impact with a roll along the knockback; every
// screen shake adds trauma (amplitude = shake_max_px * trauma^2, smooth
// noise), so overlapping hits stack.  Saved as camera.json (format
// pb_camera), read by the game from characters/camera.json and hot-reloaded
// about once a second.  tools/fx/check_parity.py checks CAM_DEFAULTS /
// CAM_RANGES / CAM_FORMAT against the game.
(function () {
"use strict";
var CAM_FORMAT = "pb_camera";
var CAM_DEFAULTS = {
  "follow": true, "punch": true, "shake": true,
  "max_zoom": 1.6, "solo_zoom": 1.15, "follow_s": 0.4, "margin_px": 220.0,
  "punch_zoom": 0.3, "punch_tilt_deg": 3.0, "punch_pull": 0.6, "punch_in_ticks": 3, "punch_out_s": 0.35,
  "shake_max_px": 16.0, "shake_hz": 18.0,
  "ult_on": true, "ult_zoom": 2.3, "ult_in_s": 0.6, "ult_max_s": 1.5, "ult_out_s": 0.5,
  "switch_on": true, "switch_zoom": 1.8, "switch_in_s": 0.15, "switch_hold_s": 0.5, "switch_out_s": 0.4,
  "ko_on": true, "ko_zoom": 2.5, "ko_in_s": 0.2, "ko_hold_s": 1.0, "ko_out_s": 0.6, "ko_slow": 0.25, "ko_slow_s": 0.9,
  "clash_on": true, "clash_zoom": 2.0, "clash_in_s": 0.08, "clash_hold_s": 0.3, "clash_out_s": 0.35,
  "depth": true, "depth_base": 0.10, "depth_gain": 0.20, "depth_shot": 0.15, "depth_budget_ms": 14.0
};
var CAM_RANGES = {
  "max_zoom": [1.0, 3.0], "solo_zoom": [1.0, 3.0], "follow_s": [0.02, 5.0], "margin_px": [0.0, 1000.0],
  "punch_zoom": [0.0, 1.5], "punch_tilt_deg": [0.0, 30.0], "punch_pull": [0.0, 1.0],
  "punch_in_ticks": [1, 30], "punch_out_s": [0.02, 5.0],
  "shake_max_px": [0.0, 100.0], "shake_hz": [1.0, 60.0],
  "ult_zoom": [1.0, 4.0], "ult_in_s": [0.02, 5.0], "ult_max_s": [0.0, 10.0], "ult_out_s": [0.02, 5.0],
  "switch_zoom": [1.0, 4.0], "switch_in_s": [0.02, 5.0], "switch_hold_s": [0.0, 10.0], "switch_out_s": [0.02, 5.0],
  "ko_zoom": [1.0, 4.0], "ko_in_s": [0.02, 5.0], "ko_hold_s": [0.0, 10.0], "ko_out_s": [0.02, 5.0],
  "ko_slow": [0.05, 1.0], "ko_slow_s": [0.0, 5.0],
  "clash_zoom": [1.0, 4.0], "clash_in_s": [0.02, 5.0], "clash_hold_s": [0.0, 10.0], "clash_out_s": [0.02, 5.0],
  "depth_base": [0.0, 0.6], "depth_gain": [0.0, 0.6], "depth_shot": [0.0, 0.6],
  "depth_budget_ms": [4.0, 60.0]
};
var DEPTH_MAX = 0.6;
// Cinematic shot kinds: settings prefix and priority (higher wins).
var CAM_SHOTS = {"clash": ["clash", 1], "switch_in": ["switch", 2], "ultimate": ["ult", 3], "ko": ["ko", 4]};
// [group title, [[key, label, tip, step], ...]]
var CAM_GROUPS = [
  ["Follow-cam", [
    ["follow", "Follow-cam", "Frame the fighters and follow them. Off = the camera stays still at 1.0x (punch-in and shake still work)."],
    ["max_zoom", "Battle max zoom ×", "Battle: how far the camera zooms in when the fighters are close. It never zooms out below 1.0x, so nobody is pushed off the overlay.", 0.05],
    ["solo_zoom", "Solo zoom ×", "Solo: the light fixed zoom the camera follows the fighter at.", 0.05],
    ["follow_s", "Follow time (s)", "How long the camera takes to catch up with the fighters (about 95% of the way). Lower = snappier, higher = floatier.", 0.05],
    ["margin_px", "Margin (px)", "Space kept around the outermost fighters when framing them. Bigger = zooms in less.", 10]
  ]],
  ["Hit-stop punch-in", [
    ["punch", "Punch-in", "On every hit-stop (finishers, ultimates, strikes with Hit-stop) the camera snaps in toward the impact, holds through the freeze, then eases back."],
    ["punch_zoom", "Extra zoom ×", "Zoom added on top of the follow zoom at the peak of the punch.", 0.05],
    ["punch_tilt_deg", "Tilt (°)", "Roll along the knockback's left/right direction at the peak. 0 = level.", 0.5],
    ["punch_pull", "Pull to impact", "0..1: how far the view centre moves onto the impact point.", 0.05],
    ["punch_in_ticks", "Snap-in (ticks)", "How fast the punch reaches full zoom (1 tick = 16 ms).", 1],
    ["punch_out_s", "Ease-back (s)", "How long the camera takes to settle back after the freeze ends.", 0.05]
  ]],
  ["Screen shake", [
    ["shake", "Shake", "Strike shakes (Hit weight: shake / shake_px / shake_ticks) add trauma; overlapping hits build up and fade together. Off = no screen shake at all."],
    ["shake_max_px", "Max shake (px)", "Amplitude at full trauma. A single shake from rest still shakes its own px (up to this).", 1],
    ["shake_hz", "Shake speed (Hz)", "How fast the smooth shake moves. Higher = buzzier, lower = rolling.", 1]
  ]],
  ["Cinematic: Ultimate", [
    ["ult_on", "Ultimate push-in", "When any fighter starts its ultimate, the camera pushes in on it and holds while the ultimate plays."],
    ["ult_zoom", "Zoom ×", "How close the push-in gets.", 0.05],
    ["ult_in_s", "Push-in time (s)", "A slow push-in reads as a wind-up.", 0.05],
    ["ult_max_s", "Max hold (s)", "Holds while the ultimate plays, but never longer than this.", 0.1],
    ["ult_out_s", "Ease-back (s)", "How long it takes to return to the follow-cam.", 0.05]
  ]],
  ["Cinematic: Tag switch-in", [
    ["switch_on", "Switch-in shot", "When a tag partner switches in, the camera moves onto it."],
    ["switch_zoom", "Zoom ×", "", 0.05],
    ["switch_in_s", "Move-in time (s)", "", 0.05],
    ["switch_hold_s", "Hold (s)", "", 0.05],
    ["switch_out_s", "Ease-back (s)", "", 0.05]
  ]],
  ["Cinematic: KO", [
    ["ko_on", "KO shot", "On a KO the camera holds on the fallen fighter, then re-frames whoever is left. In Solo the final KO holds the frame, then the run ends."],
    ["ko_zoom", "Zoom ×", "", 0.05],
    ["ko_in_s", "Move-in time (s)", "", 0.05],
    ["ko_hold_s", "Hold (s)", "", 0.05],
    ["ko_out_s", "Ease-back (s)", "", 0.05],
    ["ko_slow", "Slow-mo speed", "Game speed during the KO slow-mo (both sides at once). 1 = no slow-mo, 0.25 = quarter speed.", 0.05],
    ["ko_slow_s", "Slow-mo time (s)", "How long the slow-mo lasts (real seconds). 0 = none.", 0.05]
  ]],
  ["Cinematic: Clash", [
    ["clash_on", "Clash shot", "When two opposing FX clash, the camera snaps onto the clash point."],
    ["clash_zoom", "Zoom ×", "", 0.05],
    ["clash_in_s", "Snap-in time (s)", "", 0.02],
    ["clash_hold_s", "Hold (s)", "", 0.05],
    ["clash_out_s", "Ease-back (s)", "", 0.05]
  ]],
  ["Depth tilt", [
    ["depth", "Depth tilt", "A real perspective along the arena's depth (bottom-left near, top-right far): far things shrink and draw in toward the nearest fighter, so the slope reads deeper. Drawing only — sizes, hits and walls in the game are unchanged."],
    ["depth_base", "Base strength", "Perspective always applied (0 = none).", 0.01],
    ["depth_gain", "Near-side extra", "Added when the action is at the near (bottom-left) side: a lower, more dramatic camera.", 0.01],
    ["depth_shot", "Cinematic extra", "Added at the peak of a cinematic shot (ultimate, switch-in, KO, clash).", 0.01],
    ["depth_budget_ms", "Paint budget (ms)", "Perspective painting costs more. If drawing a frame takes longer than this for about 2 s, the game turns the depth tilt off for the session (save camera.json or press F5 to retry).", 1]
  ]]
];
var TICK_MS = 16, DT = TICK_MS / 1000;

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function normalize(o) {
  var s = {format: CAM_FORMAT};
  Object.keys(CAM_DEFAULTS).forEach(function (k) { s[k] = CAM_DEFAULTS[k]; });
  if (!o || typeof o !== "object") return s;
  Object.keys(CAM_DEFAULTS).forEach(function (k) { if (typeof CAM_DEFAULTS[k] === "boolean" && k in o) s[k] = !!o[k]; });
  Object.keys(CAM_RANGES).forEach(function (k) {
    if (!(k in o)) return;
    var v = parseFloat(o[k]);
    if (isFinite(v)) s[k] = clamp(v, CAM_RANGES[k][0], CAM_RANGES[k][1]);
  });
  s.punch_in_ticks = Math.round(s.punch_in_ticks);
  return s;
}
function hash(i, seed) {
  var h = (Math.imul(i, 374761393) + Math.imul(seed, 668265263)) >>> 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
  h = (h ^ (h >>> 16)) >>> 0;
  return (h & 0xFFFF) / 32767.5 - 1;
}
function noise(x, seed) {
  var i = Math.floor(x), f = x - i, a = hash(i, seed), b = hash(i + 1, seed), u = f * f * (3 - 2 * f);
  return a + (b - a) * u;
}
function ease(t) { t = clamp(t, 0, 1); return t * t * (3 - 2 * t); }
function ticks(sec) { return Math.max(1, Math.round(sec / DT)); }

// One cinematic move (laser/camera.py _Shot): ramps in, holds, eases out;
// follows `fig` ({x, y}) when given; whileFn keeps the hold going.
function Shot(kind, x, y, fig, zoom, inT, holdT, outT, whileFn) {
  this.kind = kind; this.prio = CAM_SHOTS[kind][1]; this.x = x; this.y = y; this.fig = fig; this.zoom = zoom;
  this.inT = Math.max(1, inT); this.holdT = Math.max(0, holdT); this.outT = Math.max(1, outT); this.whileFn = whileFn || null;
  this.env = 0; this.age = 0; this.out = false;
}
Shot.prototype.step = function () {
  if (this.fig) { this.x = this.fig.x; this.y = this.fig.y; }
  this.age++;
  if (!this.out) {
    this.env = Math.min(1, this.env + 1 / this.inT);
    var held = this.age - this.inT;
    if (this.whileFn) { var going = false; try { going = !!this.whileFn(); } catch (e) {} if (held >= 0 && (!going || held >= this.holdT)) this.out = true; }
    else if (held >= this.holdT) this.out = true;
  } else this.env = Math.max(0, this.env - 1 / this.outT);
  return !(this.out && this.env <= 0);
};

// The camera.  figs = [{x, y}], battle = bool, hitstop = ticks left.
function Cam(sw, sh, cfg) {
  this.sw = sw; this.sh = sh; this.cfg = cfg || normalize({});
  this.reset();
}
Cam.prototype.reset = function () {
  this.cx = this.sw / 2; this.cy = this.sh / 2; this.zoom = 1;
  this.env = 0; this.inLeft = 0; this.px = this.cx; this.py = this.cy; this.roll = 0;
  this.req = null; this.prevHs = 0; this.trauma = 0; this.decay = 0; this.t = 0; this.shot = null;
  this.k = 0; this.ax = this.sw / 2; this.ay = this.sh / 2;
};
Cam.prototype.depthT = function (x, y) { return 0.5 * (x / this.sw) + 0.5 * (1 - y / this.sh); };
Cam.prototype.depthTarget = function (figs) {
  var c = this.cfg, best = null, self = this;
  if (!c.depth || !figs.length) return [0, this.ax, this.ay];
  figs.forEach(function (f) { var t = self.depthT(f.x, f.y); if (!best || t < best[0]) best = [t, f.x, f.y]; });
  var t = clamp(best[0], 0, 1);
  return [Math.min(DEPTH_MAX, c.depth_base + c.depth_gain * (1 - t)), best[1], best[2]];
};
// Depth tilt of a scene point under view v: [x', y', w] (draw sizes at 1/w).
Cam.prototype.depth = function (v, x, y) {
  var k = v[6], w = 1 + k * (this.depthT(x, y) - this.depthT(v[7], v[8]));
  return [v[7] + (x - v[7]) / w, v[8] + (y - v[8]) / w, w];
};
Cam.prototype.shotOn = function (kind) { var s = CAM_SHOTS[kind]; return !!s && !!this.cfg[s[0] + "_on"]; };
Cam.prototype.koHoldTicks = function () { return ticks(this.cfg.ko_in_s) + ticks(this.cfg.ko_hold_s); };
// kind: "ultimate" / "switch_in" / "ko" / "clash"; on (x, y) or on fig.
Cam.prototype.startShot = function (kind, x, y, fig, whileFn) {
  if (!CAM_SHOTS[kind] || !this.shotOn(kind)) return false;
  var cur = this.shot;
  if (cur && !cur.out && cur.prio > CAM_SHOTS[kind][1]) return false;
  if (fig) { x = fig.x; y = fig.y; }
  var pre = CAM_SHOTS[kind][0], c = this.cfg, hold = kind === "ultimate" ? c.ult_max_s : c[pre + "_hold_s"];
  var s = new Shot(kind, x, y, fig, c[pre + "_zoom"], ticks(c[pre + "_in_s"]), Math.round(hold / DT), ticks(c[pre + "_out_s"]), whileFn);
  if (cur) s.env = cur.env;
  this.shot = s;
  return true;
};
Cam.prototype.addShake = function (px, ticks) {
  var mx = this.cfg.shake_max_px;
  if (px <= 0 || mx <= 0) return;
  var add = Math.sqrt(Math.min(1, px / mx)), rate = add / Math.max(1, Math.round(ticks)), b = this.trauma;
  this.decay = b <= 1e-4 ? rate : (b * this.decay + add * rate) / (b + add);
  this.trauma = Math.min(1, b + add);
};
Cam.prototype.punch = function (x, y, dx, dy) { this.req = [x, y, dx || 0, dy || 0]; };
Cam.prototype.clampC = function (cx, cy, z) {
  var hw = this.sw / (2 * z), hh = this.sh / (2 * z);
  return [Math.min(Math.max(cx, hw), this.sw - hw), Math.min(Math.max(cy, hh), this.sh - hh)];
};
Cam.prototype.target = function (figs, battle) {
  var c = this.cfg;
  if (!c.follow || !figs.length) return [this.sw / 2, this.sh / 2, 1];
  var xs = figs.map(function (f) { return f.x; }), ys = figs.map(function (f) { return f.y; });
  var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs), y0 = Math.min.apply(null, ys), y1 = Math.max.apply(null, ys);
  var m = c.margin_px, fit = Math.min(this.sw / Math.max(1, x1 - x0 + 2 * m), this.sh / Math.max(1, y1 - y0 + 2 * m));
  var z = battle ? clamp(fit, 1, c.max_zoom) : clamp(Math.min(c.solo_zoom, fit), 1, c.solo_zoom);
  var cc = this.clampC((x0 + x1) / 2, (y0 + y1) / 2, z);
  return [cc[0], cc[1], z];
};
Cam.prototype.step = function (figs, battle, hs) {
  var c = this.cfg; this.t++;
  var tg = this.target(figs, battle), a = 1 - Math.exp(-DT * 3 / c.follow_s);
  this.cx += (tg[0] - this.cx) * a; this.cy += (tg[1] - this.cy) * a; this.zoom += (tg[2] - this.zoom) * a;
  var dt = this.depthTarget(figs);
  this.k += (dt[0] - this.k) * a; this.ax += (dt[1] - this.ax) * a; this.ay += (dt[2] - this.ay) * a;
  if (this.shot && (!this.shotOn(this.shot.kind) || !this.shot.step())) this.shot = null;
  var req = this.req; this.req = null;
  if (c.punch) {
    if (!req && hs > 0 && this.prevHs <= 0) req = [this.cx, this.cy, 0, 0];
    if (req) {
      this.px = req[0]; this.py = req[1];
      var d = Math.hypot(req[2], req[3]);
      this.roll = d > 1e-6 ? c.punch_tilt_deg * req[2] / d : 0;
      this.inLeft = c.punch_in_ticks;
    }
    if (this.inLeft > 0 || hs > 0) { this.env = Math.min(1, this.env + 1 / c.punch_in_ticks); this.inLeft = Math.max(0, this.inLeft - 1); }
    else this.env = Math.max(0, this.env - DT / c.punch_out_s);
  } else { this.env = 0; this.inLeft = 0; }
  this.prevHs = hs;
  if (this.trauma > 0) this.trauma = Math.max(0, this.trauma - this.decay);
};
// [cx, cy, zoom, roll_deg, shake_dx, shake_dy]
Cam.prototype.view = function () {
  var c = this.cfg, cx = this.cx, cy = this.cy, z = this.zoom, s = this.shot;
  var dk = c.depth ? this.k : 0;
  if (s && s.env > 0) { var k = ease(s.env); cx += (s.x - cx) * k; cy += (s.y - cy) * k; z += (Math.max(z, s.zoom) - z) * k; if (c.depth) dk += c.depth_shot * k; }
  dk = clamp(dk, 0, DEPTH_MAX);
  var e = c.punch ? ease(this.env) : 0, pull = c.punch_pull * e;
  z += c.punch_zoom * e;
  var cc = this.clampC(cx + (this.px - cx) * pull, cy + (this.py - cy) * pull, z);
  var sx = 0, sy = 0;
  if (c.shake && this.trauma > 0) {
    var amp = c.shake_max_px * this.trauma * this.trauma, ph = this.t * DT * c.shake_hz;
    sx = amp * noise(ph, 1); sy = amp * noise(ph, 2);
  }
  return [cc[0], cc[1], z, this.roll * e, sx, sy, dk, this.ax, this.ay];
};
// Push the view onto a 2D canvas context (the caller saves / restores).
Cam.prototype.apply = function (g, v) {
  g.translate(this.sw / 2 + v[4], this.sh / 2 + v[5]);
  if (v[3]) g.rotate(v[3] * Math.PI / 180);
  g.scale(v[2], v[2]);
  g.translate(-v[0], -v[1]);
};

window.CAMERA = {
  FORMAT: CAM_FORMAT, DEFAULTS: CAM_DEFAULTS, RANGES: CAM_RANGES, GROUPS: CAM_GROUPS, SHOTS: CAM_SHOTS,
  TICK_MS: TICK_MS, normalize: normalize, Cam: Cam
};
})();
