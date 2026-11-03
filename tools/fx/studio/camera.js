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
  "shake_max_px": 16.0, "shake_hz": 18.0
};
var CAM_RANGES = {
  "max_zoom": [1.0, 3.0], "solo_zoom": [1.0, 3.0], "follow_s": [0.02, 5.0], "margin_px": [0.0, 1000.0],
  "punch_zoom": [0.0, 1.5], "punch_tilt_deg": [0.0, 30.0], "punch_pull": [0.0, 1.0],
  "punch_in_ticks": [1, 30], "punch_out_s": [0.02, 5.0],
  "shake_max_px": [0.0, 100.0], "shake_hz": [1.0, 60.0]
};
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
  ]]
];
var TICK_MS = 16, DT = TICK_MS / 1000;

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function normalize(o) {
  var s = {format: CAM_FORMAT};
  Object.keys(CAM_DEFAULTS).forEach(function (k) { s[k] = CAM_DEFAULTS[k]; });
  if (!o || typeof o !== "object") return s;
  ["follow", "punch", "shake"].forEach(function (k) { if (k in o) s[k] = !!o[k]; });
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

// The camera.  figs = [{x, y}], battle = bool, hitstop = ticks left.
function Cam(sw, sh, cfg) {
  this.sw = sw; this.sh = sh; this.cfg = cfg || normalize({});
  this.reset();
}
Cam.prototype.reset = function () {
  this.cx = this.sw / 2; this.cy = this.sh / 2; this.zoom = 1;
  this.env = 0; this.inLeft = 0; this.px = this.cx; this.py = this.cy; this.roll = 0;
  this.req = null; this.prevHs = 0; this.trauma = 0; this.decay = 0; this.t = 0;
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
  var c = this.cfg, e = c.punch ? ease(this.env) : 0, z = this.zoom + c.punch_zoom * e, pull = c.punch_pull * e;
  var cc = this.clampC(this.cx + (this.px - this.cx) * pull, this.cy + (this.py - this.cy) * pull, z);
  var sx = 0, sy = 0;
  if (c.shake && this.trauma > 0) {
    var amp = c.shake_max_px * this.trauma * this.trauma, ph = this.t * DT * c.shake_hz;
    sx = amp * noise(ph, 1); sy = amp * noise(ph, 2);
  }
  return [cc[0], cc[1], z, this.roll * e, sx, sy];
};
// Push the view onto a 2D canvas context (the caller saves / restores).
Cam.prototype.apply = function (g, v) {
  g.translate(this.sw / 2 + v[4], this.sh / 2 + v[5]);
  if (v[3]) g.rotate(v[3] * Math.PI / 180);
  g.scale(v[2], v[2]);
  g.translate(-v[0], -v[1]);
};

window.CAMERA = {
  FORMAT: CAM_FORMAT, DEFAULTS: CAM_DEFAULTS, RANGES: CAM_RANGES, GROUPS: CAM_GROUPS,
  TICK_MS: TICK_MS, normalize: normalize, Cam: Cam
};
})();
