/* FX Studio — UI.  Phase 2 of character creation: import a Rig Forge
 * pb_character, author FX around each action with FX Kit primitives, export
 * a pb_fxkit block the game reads.  Rig maths: rig_rf.js.  FX maths: fxkit.js.
 */
(function () {
"use strict";
var $ = function (id) { return document.getElementById(id); };
var TARGET_HEAD_PX = 16;   // laser/config.py TARGET_HEAD_PX
var LS_PROJECT = "pbfxstudio.v1.project", LS_PRESETS = "pbfxstudio.v1.presets";

var S = {ch: null, effects: [], action: null, sel: null, t: 0, playing: false, headUnits: 29, hits: [], dealt: 0,
  target: [140, 0], pan: [0, 0], figX: 0, walkDir: 1};
var player = new FXK.Player(), lut = FXK.buildLut([[255, 255, 255], [63, 176, 234]]);
var cv = $("stage"), g = cv.getContext("2d"), trackCache = null, originCache = null;

// ------------------------------------------------------------ helpers
function toast(msg, ms) { var t = $("toast"); t.textContent = msg; t.style.display = "block"; clearTimeout(toast._h); toast._h = setTimeout(function () { t.style.display = "none"; }, ms || 3200); }
function clone(o) { return JSON.parse(JSON.stringify(o)); }
function lsGet(k) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } }
function act() { return S.ch && S.action ? S.ch.actions[S.action] : null; }
function frames() { var a = act(); return a ? (a.keyframes || []).length : 0; }
function frameMs() { var a = act(), n = frames(); return a && n ? Math.max(1, (+a.duration_ms || n * 16) / n) : 16; }
function totalTicks() { return Math.max(1, Math.round(frames() * frameMs() / FXK.TICK_MS)); }
function frameAt(t) { return Math.min(frames() - 1, Math.floor(Math.min(t, totalTicks() - 1) * FXK.TICK_MS / frameMs())); }
function ppu() { return TARGET_HEAD_PX / Math.max(1, S.headUnits); }
function facing() { return +$("facing").value; }
function pscale() { return Math.max(0.25, +$("pscale").value || 1); }
function actionEffects() { return S.effects.filter(function (e) { return e.action === S.action; }); }
function selFx() { return S.effects.filter(function (e) { return e.id === S.sel; })[0] || null; }
function save() { if (S.ch) lsSet(LS_PROJECT, {ch: S.ch, effects: S.effects, action: S.action, headUnits: S.headUnits}); }
function download(name, obj) {
  var txt = JSON.stringify(obj, null, 1);
  try {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([txt], {type: "application/json"}));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
    toast("Saved " + name);
  } catch (e) { openModal("Copy this JSON (" + name + ")", txt, null); }
}

// ------------------------------------------------------------ figure host
function jointAt(name, fr) {
  if (name === "figure") return [S.figX, 0];
  if (name === "target") return S.target.slice();
  var tr = trackCache && trackCache[S.action], f = tr && tr.frames[fr];
  if (!f || !f[name]) return [S.figX, 0];
  var k = ppu() * pscale();   // the sprite scales by position_scale(), so its joints do too
  return [S.figX + f[name][0] * k * facing(), f[name][1] * k];
}
var host = {
  get facing() { return facing(); },
  get target() { return S.target; },
  get wang() { var tr = trackCache && trackCache[S.action], f = tr && tr.frames[frameAt(S.t)]; return f ? f.wang : 90; },
  get lut() { return lut; },
  get pscale() { return pscale(); },
  get hurt() { return {x: S.target[0], y: S.target[1], r: Math.max(1, +$("hurtR").value || 16)}; },
  // Preview of what the engine does on a hit (ai.apply_hp_damage + knockback).
  onHit: function (inst, dmg, dx, dy, kb) {
    S.dealt += dmg;
    S.hits.push({t: S.t, dmg: dmg, kb: kb, name: inst.fx.name});
    if (S.hits.length > 60) S.hits.shift();
  },
  anchor: function (n) { return jointAt(n, frameAt(S.t)); },
  snapshot: function () { return {action: S.action, frame: frameAt(S.t), figX: S.figX}; },
  drawGhost: function (gc, gh, rgb, a) {
    var p = (S.ch.actions[gh.snap.action].keyframes || [])[gh.snap.frame];
    if (!p) return;
    gc.save(); gc.translate(gh.snap.figX, 0); gc.scale(gh.facing, 1);
    RF.drawFigure(gc, p, S.ch, ppu() * pscale(), {tint: rgb, alpha: a});
    gc.restore();
  }
};

// ------------------------------------------------------------ load
function loadCharacter(ch, effects) {
  var chk = RF.inspect(ch);
  if (!chk.ok) { toast(chk.why, 6000); return false; }
  S.ch = ch;
  var rig = RF.rigOf(ch);
  S.headUnits = rig.head * 2 + 1;   // measured baked head diameter (e.g. 29 px for head 14 at 1 px/unit)
  var blk = ch.fx_studio;
  S.effects = (effects || (blk && blk.effects) || []).map(function (e) { return FXK.normalize(e); });
  if (blk && blk.space && blk.space.head_units) S.headUnits = +blk.space.head_units;
  var body = FXK.hexRgb((ch.palette || {}).body, [242, 244, 246]), accent = FXK.hexRgb((ch.palette || {}).accent, [63, 176, 234]);
  lut = FXK.buildLut([body, accent]);   // characters.py: palette.build_lut([body, accent])
  trackCache = RF.jointTrack(ch); originCache = RF.origin(ch);
  var names = Object.keys(ch.actions).filter(function (n) { return (ch.actions[n].keyframes || []).length; });
  if (names.indexOf(S.action) < 0) S.action = names.indexOf("attack_normal") >= 0 ? "attack_normal" : names[0];
  S.sel = null; S.figX = 0;
  $("charname").textContent = (ch.display_name || ch.name || "?") + "  (" + (ch.name || "") + ")";
  $("empty").style.display = "none";
  rebuild(); resetSim(0); save();
  return true;
}
function ingest(o, label) {
  if (!o || typeof o !== "object") { toast("Not JSON"); return; }
  if (o.format === "pb_character") { if (loadCharacter(o)) toast("Loaded " + (o.display_name || o.name) + " — " + Object.keys(o.actions).length + " actions"); return; }
  if (o.format === "pb_fxkit") {
    if (!S.ch) { toast("Load the character first, then its FX pack."); return; }
    if (o.character && S.ch.name && o.character !== S.ch.name && !confirm("This FX pack was made for \"" + o.character + "\". Load it onto \"" + S.ch.name + "\" anyway?")) return;
    S.effects = (o.effects || []).map(FXK.normalize); if (o.space && o.space.head_units) S.headUnits = +o.space.head_units;
    rebuild(); resetSim(0); save(); toast("Loaded " + S.effects.length + " effects"); return;
  }
  if (o.format === "pb_fx_presets") {
    var mine = userPresets(), n = 0;
    (o.presets || []).forEach(function (p) { if (p && p.name && p.effects) { mine = mine.filter(function (q) { return q.name !== p.name; }); mine.push(p); n++; } });
    lsSet(LS_PRESETS, mine); buildPresets(); toast("Imported " + n + " presets"); return;
  }
  toast("Unrecognised file" + (label ? " (" + label + ")" : "") + ": expected pb_character, pb_fxkit or pb_fx_presets.", 5000);
}
function readFile(f) { var r = new FileReader(); r.onload = function () { try { ingest(JSON.parse(r.result), f.name); } catch (e) { toast("Could not parse " + f.name + ": " + e.message, 5000); } }; r.readAsText(f); }

// ------------------------------------------------------------ export
function fxBlock() {
  var o = originCache || [0, 0];
  return {format: "pb_fxkit", version: 1, tick_ms: FXK.TICK_MS, character: S.ch.name,
    space: {coords: "game px, y down, relative to the figure position; x mirrors when facing left",
      joints: "joint_track values are rig units relative to the bake origin (hip x = 0, idle bbox centre y), rx zeroed",
      origin_rig: [Math.round(o[0] * 100) / 100, Math.round(o[1] * 100) / 100],
      target_head_px: TARGET_HEAD_PX, head_units: S.headUnits, px_per_unit: Math.round(ppu() * 1e6) / 1e6},
    palette_lut: {built_from: ["palette.body", "palette.accent"], rule: "palette.build_lut([body, accent])"},
    joint_track: trackCache,
    effects: S.effects.map(function (e) { return FXK.normalize(clone(e)); }),
    spec: "tools/fx/FX_KIT_SPEC.md — runtime reference tools/fx/studio/fxkit.js"};
}
function exportChar() { if (!S.ch) return toast("Import a character first"); var ch = clone(S.ch); ch.fx_studio = fxBlock(); download((S.ch.name || "character") + ".json", ch); }
function exportPack() { if (!S.ch) return toast("Import a character first"); download((S.ch.name || "character") + ".fxkit.json", fxBlock()); }

// ------------------------------------------------------------ presets
function userPresets() { return lsGet(LS_PRESETS) || []; }
function allPresets() { return FX_PRESETS.map(function (p) { return {p: p, builtin: true}; }).concat(userPresets().map(function (p) { return {p: p, builtin: false}; })); }
function buildPresets() {
  var s = $("presetSel"); s.innerHTML = "";
  allPresets().forEach(function (x, i) { var o = document.createElement("option"); o.value = i; o.textContent = (x.builtin ? "" : "★ ") + x.p.name; s.appendChild(o); });
  showPresetDesc();
}
function showPresetDesc() { var x = allPresets()[+$("presetSel").value]; $("presetDesc").textContent = x ? (x.p.desc || (x.builtin ? "" : "Your preset")) : ""; }
function addPreset() {
  if (!S.ch) return toast("Import a character first");
  var x = allPresets()[+$("presetSel").value]; if (!x) return;
  var added = x.p.effects.map(function (e) {
    var fx = clone(e); fx.id = FXK.newEffect(fx.prim).id; fx.action = S.action;
    if (fx.prim === "ghost" && !fx.layer) fx.layer = "behind";
    return FXK.normalize(fx);
  });
  S.effects = S.effects.concat(added); S.sel = added[0].id; rebuild(); resetSim(S.t); save();
}
function savePreset() {
  var fx = selFx(); if (!fx) return;
  var name = prompt("Preset name", fx.name); if (!name) return;
  var e = clone(fx); delete e.id; delete e.action;
  var mine = userPresets().filter(function (p) { return p.name !== name; });
  mine.push({name: name, desc: "Your preset (" + fx.prim + ")", effects: [e]});
  if (!lsSet(LS_PRESETS, mine)) toast("Browser storage unavailable; use Export to keep presets.", 5000);
  buildPresets(); toast("Saved preset " + name);
}

// ------------------------------------------------------------ lists
function rebuild() { buildActions(); buildEffects(); buildProps(); buildTimeline(); }
function buildActions() {
  var d = $("actions"); d.innerHTML = "";
  if (!S.ch) return;
  Object.keys(S.ch.actions).forEach(function (n) {
    var a = S.ch.actions[n], k = (a.keyframes || []).length; if (!k) return;
    var c = S.effects.filter(function (e) { return e.action === n; }).length;
    var el = document.createElement("div"); el.className = n === S.action ? "sel" : "";
    el.innerHTML = '<span class="n"></span><span class="m"></span>';
    el.querySelector(".n").textContent = n;
    el.querySelector(".m").textContent = k + "f · " + (a.duration_ms || "?") + "ms" + (c ? " · " + c + " fx" : "");
    el.onclick = function () { S.action = n; S.sel = null; rebuild(); resetSim(0); save(); };
    d.appendChild(el);
  });
}
function buildEffects() {
  var d = $("effects"); d.innerHTML = "";
  actionEffects().forEach(function (fx) {
    var el = document.createElement("div"); el.className = fx.id === S.sel ? "sel" : "";
    el.innerHTML = '<input type="checkbox"><span class="n"></span><span class="m"></span><span class="x" title="Duplicate">⧉</span><span class="x" title="Delete">✕</span>';
    var cb = el.querySelector("input"); cb.checked = fx.enabled;
    cb.onclick = function (ev) { ev.stopPropagation(); fx.enabled = cb.checked; resetSim(S.t); save(); };
    el.querySelector(".n").textContent = fx.name;
    el.querySelector(".m").textContent = (fx.battle.deals_damage ? "⚔ " + fx.battle.damage + " · " : "visual · ") + fx.prim;
    el.title = fx.battle.deals_damage ? "Deals " + fx.battle.damage + " HP per hit" : "Visual only — never damages";
    var xs = el.querySelectorAll(".x");
    xs[0].onclick = function (ev) { ev.stopPropagation(); var c = clone(fx); c.id = FXK.newEffect(c.prim).id; c.name += " copy"; S.effects.push(c); S.sel = c.id; rebuild(); resetSim(S.t); save(); };
    xs[1].onclick = function (ev) { ev.stopPropagation(); S.effects = S.effects.filter(function (e) { return e !== fx; }); if (S.sel === fx.id) S.sel = null; rebuild(); resetSim(S.t); save(); };
    el.onclick = function () { S.sel = fx.id; buildEffects(); buildProps(); buildTimeline(); };
    d.appendChild(el);
  });
}

// ------------------------------------------------------------ properties
var PARAM_UI = {
  ribbon: [["max_points", "Max points", 2, 400, 1], ["min_dist", "Min step px", 0, 40, 0.5], ["decay", "Decay pts/tick", 0, 20, 1],
    ["taper", "Taper width/alpha", "chk"], ["w_tail", "Width tail", 0, 60, 0.5], ["w_head", "Width head", 0, 60, 0.5],
    ["alpha", "Alpha (0-255)", 0, 255, 1], ["head_glow_r", "Head glow r", 0, 80, 0.5], ["head_dot_r", "Head dot r", 0, 40, 0.5]],
  arc: [["radius", "Radius", 1, 600, 1], ["span", "Span °", 5, 360, 1], ["width", "Width", 0.5, 80, 0.5], ["tail", "Tail fraction", 0.05, 1, 0.01],
    ["segs", "Segments", 2, 64, 1], ["grow", "Grow fraction", 0.05, 1, 0.01], ["core_alpha", "Core alpha", 0, 1, 0.05],
    ["core_width", "Core width", 0, 1, 0.05], ["orient", "Orient", ["motion", "angle"]], ["angle_deg", "Orient angle °", -180, 180, 1],
    ["placement", "Placement", ["anchor", "wrap_target", "through_target"]], ["back", "Wrap: centre behind target px", 0, 400, 1],
    ["lead", "Through: start short px", 0, 400, 1]],
  beam: [["length", "Length", 4, 3000, 5], ["w_start0", "Tail W begin", 0, 200, 0.5], ["w_start1", "Tail W end", 0, 200, 0.5],
    ["w_end0", "Head W begin", 0, 200, 0.5], ["w_end1", "Head W end", 0, 200, 0.5], ["segments", "Segments", 1, 64, 1],
    ["glow", "Glow extra W", 0, 80, 0.5], ["glow_color", "Glow colour", "color"], ["pulse_hz", "Pulse Hz", 0, 30, 0.5],
    ["jitter", "Jitter px", 0, 30, 0.5], ["detach_ticks", "Detach tick (0=never)", 0, 2000, 1], ["grow_ticks", "Grow ticks (held)", 0, 600, 1]],
  sprite: [["shape", "Shape", ["orb", "bolt"]], ["radius", "Radius", 0.5, 60, 0.5], ["stretch", "Bolt stretch", 1, 8, 0.1],
    ["hot", "White-hot streak", "chk"], ["halo", "Pulsing halo", "chk"], ["fade", "Fade over life", "chk"], ["trail_len", "Trail points", 0, 60, 1]],
  particles: [["mode", "Mode", ["burst", "stream"]], ["count", "Burst count", 1, 400, 1], ["rate_per_s", "Stream /s", 1, 600, 1],
    ["angle_deg", "Angle °", -180, 180, 1], ["spread_deg", "Spread °", 0, 360, 1], ["speed_min", "Speed min px/s", 0, 2000, 5],
    ["speed_max", "Speed max px/s", 0, 2000, 5], ["gravity", "Gravity px/s²", -2000, 2000, 10], ["drag", "Drag /tick", 0.5, 1, 0.01],
    ["size_min", "Size min", 0.5, 60, 0.5], ["size_max", "Size max", 0.5, 80, 0.5], ["size_over_life", "Size over life", ["shrink", "grow", "pulse", "constant"]],
    ["life_min_ms", "Life min ms", 16, 5000, 10], ["life_max_ms", "Life max ms", 16, 5000, 10]],
  glow: [["r_start", "Radius start", 0, 300, 0.5], ["r_end", "Radius end", 0, 300, 0.5], ["a_center", "Centre alpha", 0, 255, 1],
    ["a_mid", "Mid alpha", 0, 255, 1], ["mid", "Mid stop", 0.05, 0.95, 0.05], ["core_r", "White core r", 0, 100, 0.5],
    ["fade", "Alpha curve", ["none", "out", "in", "inout"]], ["pulse_hz", "Pulse Hz", 0, 30, 0.5]],
  ghost: [["interval", "Every N ticks", 1, 60, 1], ["ghost_life", "Ghost life ticks", 1, 240, 1], ["alpha", "Start alpha", 0, 255, 1], ["max", "Max ghosts", 1, 60, 1]]
};
var MOTION_UI = {
  kind: ["Motion", FXK.MOTIONS], aim: ["Aim", FXK.AIMS], angle_deg: ["Aim angle °", -180, 180, 1], aim_offset_deg: ["Aim offset °", -180, 180, 1],
  speed: ["Speed px/tick", 0, 80, 0.1], turn_deg: ["Turn °/tick", 0, 45, 0.5], amplitude: ["Zigzag amplitude", 0, 300, 1],
  freq: ["Zigzag freq rad/tick", 0, 2, 0.01], orbit_rx: ["Orbit radius X", 0, 400, 1], orbit_ry: ["Orbit radius Y", 0, 400, 1], orbit_deg: ["Orbit °/tick", -30, 30, 0.02]
};
var MOTION_KEYS = {attached: [], static: [], travel: ["aim", "angle_deg", "aim_offset_deg", "speed"],
  homing: ["aim", "angle_deg", "aim_offset_deg", "speed", "turn_deg"], zigzag: ["aim", "angle_deg", "aim_offset_deg", "speed", "amplitude", "freq"],
  orbit: ["orbit_rx", "orbit_ry", "orbit_deg"]};
function field(parent, label, input) { var w = document.createElement("div"); w.className = "f"; var l = document.createElement("label"); l.textContent = label; w.appendChild(l); w.appendChild(input); parent.appendChild(w); return input; }
function inp(kind, val, onch, a, b, st) {
  var e;
  if (Array.isArray(kind)) { e = document.createElement("select"); kind.forEach(function (o) { var op = document.createElement("option"); if (Array.isArray(o)) { op.value = o[0]; op.textContent = o[1]; } else { op.value = o; op.textContent = o; } e.appendChild(op); }); e.value = val; e.onchange = function () { onch(e.value); }; return e; }
  e = document.createElement("input");
  if (kind === "chk") { e.type = "checkbox"; e.checked = !!val; e.onchange = function () { onch(e.checked); }; return e; }
  if (kind === "color") { e.type = "color"; e.value = /^#[0-9a-f]{6}$/i.test(val) ? val : "#ffffff"; e.oninput = function () { onch(e.value); }; return e; }
  if (kind === "text") { e.type = "text"; e.value = val; e.oninput = function () { onch(e.value); }; return e; }
  e.type = "number"; e.value = val; if (a != null) e.min = a; if (b != null) e.max = b; if (st) e.step = st;
  e.oninput = function () { var v = parseFloat(e.value); if (isFinite(v)) onch(v); }; return e;
}
function sec(parent, title) { var s = document.createElement("div"); s.className = "sec"; var b = document.createElement("b"); b.textContent = title; s.appendChild(b); parent.appendChild(s); return s; }
function changed(rebuildProps) { resetSim(S.t); buildTimeline(); save(); if (rebuildProps) buildProps(); }
function anchorOptions() { return [["figure", "figure (sprite centre)"], ["target", "target"]].concat(RF.JOINTS.map(function (j) { return [j, j + " — " + RF.JOINT_LABEL[j]]; })); }

function buildProps() {
  var d = $("props"); d.innerHTML = ""; d.className = "";
  var fx = selFx();
  if (!fx) { d.className = "note"; d.textContent = S.ch ? "Select an effect, or add one from a primitive or a preset." : "Import a character to begin."; return; }
  var s = sec(d, "Effect");
  field(s, "Name", inp("text", fx.name, function (v) { fx.name = v; buildEffects(); buildTimeline(); save(); }));
  field(s, "Primitive", inp(FXK.PRIMS, fx.prim, function (v) { fx.prim = v; fx.params = {}; FXK.normalize(fx); buildEffects(); changed(true); }));
  field(s, "Layer", inp([["front", "in front of figure"], ["behind", "behind figure"]], fx.layer, function (v) { fx.layer = v; changed(); }));
  field(s, "Blend", inp(["normal", "additive"], fx.blend, function (v) { fx.blend = v; changed(); }));
  field(s, "Action", inp(Object.keys(S.ch.actions), fx.action, function (v) { fx.action = v; S.action = v; rebuild(); resetSim(0); save(); }));

  s = sec(d, "Purpose");
  var bt = fx.battle;
  if (fx.prim === "ghost") {
    var gn = document.createElement("div"); gn.className = "note"; gn.textContent = "Afterimages are visual only."; s.appendChild(gn);
  } else {
    field(s, "Deals damage", inp("chk", bt.deals_damage, function (v) { bt.deals_damage = v; buildEffects(); changed(true); })).title =
      "Checked: this FX is an attack and damages the target where it touches. Unchecked: visual only.";
    if (bt.deals_damage) {
      field(s, "Damage HP per hit", inp("n", bt.damage, function (v) { bt.damage = Math.max(0, v); buildEffects(); changed(); }, 0, 1000, 0.5));
      field(s, "Pierce (keeps going)", inp("chk", bt.pierce, function (v) { bt.pierce = v; changed(); }));
      field(s, "Re-hit every N ticks (0 = once)", inp("n", bt.rehit_ticks, function (v) { bt.rehit_ticks = Math.max(0, Math.round(v)); changed(); }, 0, 600, 1));
      field(s, "Knockback px", inp("n", bt.knockback, function (v) { bt.knockback = Math.max(0, v); changed(); }, 0, 200, 0.5));
    } else {
      var vn = document.createElement("div"); vn.className = "note"; vn.textContent = "Visual only — this FX never damages."; s.appendChild(vn);
    }
  }

  s = sec(d, "Timing (frames of " + fx.action + ": 0–" + (frames() - 1) + ")");
  field(s, "Start frame", inp("n", fx.start_frame, function (v) { fx.start_frame = Math.max(0, Math.round(v)); changed(); }, 0, frames() - 1, 1));
  field(s, "End frame (-1 = end)", inp("n", fx.end_frame, function (v) { fx.end_frame = Math.round(v); changed(); }, -1, frames() - 1, 1));
  field(s, "Life ticks (0 = to end)", inp("n", fx.life_ticks, function (v) { fx.life_ticks = Math.max(0, Math.round(v)); changed(); }, 0, 5000, 1));
  field(s, "Re-emit every N ticks", inp("n", fx.emit.every_ticks, function (v) { fx.emit.every_ticks = Math.max(0, Math.round(v)); changed(); }, 0, 600, 1));
  field(s, "Count per emit", inp("n", fx.emit.count, function (v) { fx.emit.count = Math.max(1, Math.round(v)); changed(); }, 1, 64, 1));
  field(s, "Fan ° (count > 1)", inp("n", fx.emit.fan_deg, function (v) { fx.emit.fan_deg = v; changed(); }, 0, 360, 1));

  s = sec(d, "Anchor");
  field(s, "Joint", inp(anchorOptions(), fx.anchor, function (v) { fx.anchor = v; changed(); }));
  field(s, "Offset X px", inp("n", fx.offset[0], function (v) { fx.offset[0] = v; changed(); }, -500, 500, 0.5));
  field(s, "Offset Y px", inp("n", fx.offset[1], function (v) { fx.offset[1] = v; changed(); }, -500, 500, 0.5));

  s = sec(d, "Motion");
  field(s, MOTION_UI.kind[0], inp(MOTION_UI.kind[1], fx.motion.kind, function (v) { fx.motion.kind = v; changed(true); }));
  MOTION_KEYS[fx.motion.kind].forEach(function (k) {
    var u = MOTION_UI[k];
    if (k === "angle_deg" && fx.motion.aim !== "angle") return;
    field(s, u[0], Array.isArray(u[1]) ? inp(u[1], fx.motion[k], function (v) { fx.motion[k] = v; changed(true); })
      : inp("n", fx.motion[k], function (v) { fx.motion[k] = v; changed(); }, u[1], u[2], u[3]));
  });

  s = sec(d, "Colour");
  var c = fx.color;
  field(s, "Source", inp([["palette", "character palette (LUT)"], ["gradient", "two-colour gradient"], ["solid", "solid"]], c.mode, function (v) { c.mode = v; changed(true); }));
  if (c.mode === "palette") {
    var strip = document.createElement("canvas"); strip.id = "lut"; strip.width = 256; strip.height = 1; strip.style.width = "100%";
    var sg = strip.getContext("2d"); lut.forEach(function (q, i) { sg.fillStyle = "rgb(" + q + ")"; sg.fillRect(i, 0, 1, 1); }); s.appendChild(strip);
    if (["ribbon", "arc"].indexOf(fx.prim) >= 0) {
      field(s, "Flow speed /tick", inp("n", c.flow_speed, function (v) { c.flow_speed = v; changed(); }, 0, 0.2, 0.001));
      field(s, "LUT offset", inp("n", c.lut_offset, function (v) { c.lut_offset = v; changed(); }, 0, 1, 0.01));
    } else {
      field(s, "LUT index (start)", inp("n", c.lut_index, function (v) { c.lut_index = Math.round(v); changed(); }, 0, 255, 1));
      field(s, "LUT index (end)", inp("n", c.lut_index2, function (v) { c.lut_index2 = Math.round(v); changed(); }, 0, 255, 1));
    }
  } else {
    field(s, c.mode === "gradient" ? "Colour 1" : "Colour", inp("color", c.c1, function (v) { c.c1 = v; changed(); }));
    if (c.mode === "gradient") {
      field(s, "Colour 2", inp("color", c.c2, function (v) { c.c2 = v; changed(); }));
      if (["ribbon", "arc"].indexOf(fx.prim) >= 0) field(s, "Solid until", inp("n", c.start_fraction, function (v) { c.start_fraction = v; changed(); }, 0, 0.99, 0.01));
    }
  }

  s = sec(d, fx.prim + " parameters");
  PARAM_UI[fx.prim].forEach(function (u) {
    var k = u[0], kind = u[2];
    field(s, u[1], Array.isArray(kind) ? inp(kind, fx.params[k], function (v) { fx.params[k] = v; changed(); })
      : kind === "chk" ? inp("chk", fx.params[k], function (v) { fx.params[k] = v; changed(); })
      : kind === "color" ? inp("color", fx.params[k] || "#000000", function (v) { fx.params[k] = v; changed(); })
      : inp("n", fx.params[k], function (v) { fx.params[k] = v; changed(); }, u[2], u[3], u[4]));
  });
  var r = document.createElement("div"); r.className = "row";
  var b = document.createElement("button"); b.textContent = "Save as preset…"; b.onclick = savePreset; r.appendChild(b);
  d.appendChild(r);
}

// ------------------------------------------------------------ timeline
function buildTimeline() {
  var tl = $("timeline"), ph = $("playhead"); tl.innerHTML = ""; tl.appendChild(ph);
  var n = frames(); if (!n) return;
  var W = tl.clientWidth || 600, fw = W / n, lab = Math.max(1, Math.ceil(28 / fw));
  for (var i = 0; i < n; i += 1) {
    if (i % lab) continue;
    var f = document.createElement("div"); f.className = "tlf"; f.style.left = (i * fw) + "px"; f.textContent = i; tl.appendChild(f);
  }
  var total = totalTicks();
  tl.style.height = Math.min(260, Math.max(96, 24 + actionEffects().length * 15)) + "px";
  actionEffects().forEach(function (fx, row) {
    var w = player.window(fx, n, frameMs());
    var b = document.createElement("div"); b.className = "tlbar" + (fx.id === S.sel ? " sel" : "") + (fx.battle.deals_damage ? " dmg" : "");
    // Bar = the emission window; a one-shot with a fixed life shows that life.
    var span = (fx.life_ticks > 0 && !(fx.emit.every_ticks > 0)) ? fx.life_ticks : w[1] - w[0];
    b.style.left = (w[0] / total * W) + "px"; b.style.width = Math.max(4, span / total * W) + "px";
    b.title = fx.name + " — " + fx.prim + ", starts frame " + fx.start_frame;
    b.style.top = (18 + row * 15) + "px"; b.style.opacity = fx.enabled ? 1 : 0.4; b.textContent = fx.name;
    b.onclick = function (ev) { ev.stopPropagation(); S.sel = fx.id; buildEffects(); buildProps(); buildTimeline(); };
    tl.appendChild(b);
  });
  placeHead();
}
function placeHead() { var W = $("timeline").clientWidth || 600; $("playhead").style.left = (Math.min(S.t, totalTicks()) / totalTicks() * W) + "px"; }

// ------------------------------------------------------------ simulation
// Scrubbing re-simulates deterministically from tick 0, so a paused frame
// shows exactly what that tick looks like during playback.
function resetSim(t) {
  player.reset(); S.figX = 0; S.walkDir = 1; S.t = 0; S.hits = []; S.dealt = 0;
  var target = Math.max(0, Math.min(t, totalTicks() - 1));
  while (S.t < target) step(false);
}
function step(allowWrap) {
  if (!S.ch) return;
  var walk = +$("walk").value || 0;
  if (walk) { S.figX += walk * S.walkDir; if (Math.abs(S.figX) > 160) S.walkDir *= -1; }
  player.tick(actionEffects(), host, S.t, frames(), frameMs());
  S.t += 1;
  if (S.t >= totalTicks() && allowWrap && $("loop").checked) { S.t = 0; S.dealt = 0; S.hits = []; }
}
var last = 0, acc = 0;
function loop(now) {
  requestAnimationFrame(loop);
  var dt = Math.min(100, now - (last || now)); last = now;
  if (S.playing && S.ch) {
    acc += dt * (+$("speed").value || 1);
    while (acc >= FXK.TICK_MS) { acc -= FXK.TICK_MS; step(true); if (S.t >= totalTicks() && !$("loop").checked && !player.insts.length) { S.playing = false; $("bPlay").textContent = "▶ Play"; } }
  }
  draw();
}

// ------------------------------------------------------------ render
function fit() { var r = cv.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1); var w = Math.round(r.width * dpr), h = Math.round(r.height * dpr); if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; } return dpr; }
function zoom() { return Math.max(0.25, +$("zoom").value || 4); }
function camera(dpr) { return {x: cv.width / 2 / dpr + S.pan[0], y: cv.height * 0.55 / dpr + S.pan[1], z: zoom()}; }
function toWorld(mx, my) { var dpr = Math.min(2, window.devicePixelRatio || 1), c = camera(dpr); return [(mx - c.x) / c.z, (my - c.y) / c.z]; }
function draw() {
  var dpr = fit(); g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cv.width, cv.height);
  if (!S.ch) return;
  var c = camera(dpr), z = c.z;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  // grid: one line per 10 game px
  g.strokeStyle = "rgba(255,255,255,.04)"; g.lineWidth = 1;
  var step10 = 10 * z, x0 = ((c.x % step10) + step10) % step10, y0 = ((c.y % step10) + step10) % step10;
  for (var x = x0; x < cv.width / dpr; x += step10) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, cv.height); g.stroke(); }
  for (var y = y0; y < cv.height / dpr; y += step10) { g.beginPath(); g.moveTo(0, y); g.lineTo(cv.width, y); g.stroke(); }
  g.translate(c.x, c.y); g.scale(z, z);
  var ps = pscale(), fr = frameAt(S.t), p = act().keyframes[fr];
  player.draw(g, host, "behind", ps);
  g.save(); g.translate(S.figX, 0); g.scale(facing(), 1); RF.drawFigure(g, p, S.ch, ppu() * ps, {}); g.restore();
  player.draw(g, host, "front", ps);
  // target marker + its hurt radius (the circle damaging FX must touch)
  var hr = host.hurt.r, lastHit = S.hits.length ? S.hits[S.hits.length - 1] : null, flash = lastHit && S.t - lastHit.t < 8;
  g.fillStyle = flash ? "rgba(255,80,80,.35)" : "rgba(240,194,74,.06)";
  g.beginPath(); g.arc(S.target[0], S.target[1], hr, 0, 6.2832); g.fill();
  g.setLineDash([6 / z, 6 / z]); g.strokeStyle = flash ? "rgba(255,90,90,.95)" : "rgba(240,194,74,.45)"; g.lineWidth = 1 / z;
  g.beginPath(); g.arc(S.target[0], S.target[1], hr, 0, 6.2832); g.stroke(); g.setLineDash([]);
  g.font = (11 / z) + "px sans-serif"; g.textAlign = "center";
  S.hits.forEach(function (h, i) {
    var age = S.t - h.t; if (age < 0 || age > 40) return;
    g.fillStyle = "rgba(255,110,110," + (1 - age / 40) + ")";
    g.fillText("-" + h.dmg + (h.kb ? " ⇢" + h.kb : ""), S.target[0] + ((i % 3) - 1) * 6, S.target[1] - hr - 4 - age * 0.4);
  });
  g.textAlign = "start";
  g.strokeStyle = "rgba(240,194,74,.9)"; g.lineWidth = 1.5 / z;
  g.beginPath(); g.arc(S.target[0], S.target[1], 6, 0, 6.2832); g.moveTo(S.target[0] - 9, S.target[1]); g.lineTo(S.target[0] + 9, S.target[1]);
  g.moveTo(S.target[0], S.target[1] - 9); g.lineTo(S.target[0], S.target[1] + 9); g.stroke();
  var fx = selFx();
  if ($("joints").checked || fx) {
    RF.JOINTS.forEach(function (j) {
      var q = jointAt(j, fr), on = fx && fx.anchor === j;
      if (!$("joints").checked && !on) return;
      g.fillStyle = on ? "#f0c24a" : "rgba(63,176,234,.8)"; g.beginPath(); g.arc(q[0], q[1], (on ? 3 : 1.8) / z * 2, 0, 6.2832); g.fill();
    });
  }
  $("hud").textContent = S.action + "   frame " + fr + "/" + (frames() - 1) + "   tick " + S.t + "/" + totalTicks() +
    "   " + Math.round(frameMs() * 10) / 10 + " ms/frame   " + player.insts.length + " live FX   damage this loop " + S.dealt + " HP   1 game px = " + z + " screen px";
  $("frameInfo").textContent = "frame " + fr;
  placeHead();
}

// ------------------------------------------------------------ modal
var modalApply = null;
function openModal(title, text, apply) { $("mTitle").textContent = title; $("mText").value = text || ""; $("mApply").style.display = apply ? "" : "none"; modalApply = apply; $("modal").style.display = "flex"; }
$("mClose").onclick = function () { $("modal").style.display = "none"; };
$("mCopy").onclick = function () { var t = $("mText"); t.select(); try { navigator.clipboard.writeText(t.value); } catch (e) { document.execCommand("copy"); } toast("Copied"); };
$("mApply").onclick = function () { try { var o = JSON.parse($("mText").value); $("modal").style.display = "none"; if (modalApply) modalApply(o); } catch (e) { toast("Invalid JSON: " + e.message, 5000); } };

// ------------------------------------------------------------ wiring
$("newPrim").innerHTML = FXK.PRIMS.map(function (p) { return "<option>" + p + "</option>"; }).join("");
$("bImport").onclick = function () { $("file").click(); };
$("file").onchange = function () { var f = this.files[0]; this.value = ""; if (f) readFile(f); };
$("bPaste").onclick = function () { openModal("Paste a pb_character, pb_fxkit or pb_fx_presets JSON", "", function (o) { ingest(o, "pasted"); }); };
$("bExportChar").onclick = exportChar; $("bExportPack").onclick = exportPack;
$("bAdd").onclick = function () {
  if (!S.ch) return toast("Import a character first");
  var fx = FXK.newEffect($("newPrim").value, S.action);
  if (fx.prim === "ghost") fx.layer = "behind";
  if (["arc", "beam", "sprite"].indexOf(fx.prim) >= 0) { fx.motion.kind = "travel"; fx.life_ticks = fx.prim === "arc" ? 5 : 60; }
  if (fx.prim === "particles") { fx.motion.kind = "static"; fx.life_ticks = 1; }
  S.effects.push(fx); S.sel = fx.id; rebuild(); resetSim(S.t); save();
};
$("presetSel").onchange = showPresetDesc; $("bPreset").onclick = addPreset;
$("bPresetDel").onclick = function () {
  var x = allPresets()[+$("presetSel").value]; if (!x) return;
  if (x.builtin) return toast("Built-in presets can't be deleted.");
  lsSet(LS_PRESETS, userPresets().filter(function (p) { return p.name !== x.p.name; })); buildPresets();
};
$("bPresetExport").onclick = function () { var mine = userPresets(); if (!mine.length) return toast("No saved presets yet"); download("fx_presets.json", {format: "pb_fx_presets", version: 1, presets: mine}); };
$("bPresetImport").onclick = function () { $("pfile").click(); };
$("pfile").onchange = function () { var f = this.files[0]; this.value = ""; if (f) readFile(f); };
$("bPlay").onclick = function () { if (!S.ch) return; S.playing = !S.playing; if (S.playing && S.t >= totalTicks()) resetSim(0); this.textContent = S.playing ? "❚❚ Pause" : "▶ Play"; };
function gotoFrame(f) { if (!S.ch) return; S.playing = false; $("bPlay").textContent = "▶ Play"; f = (f + frames()) % frames(); resetSim(Math.ceil(f * frameMs() / FXK.TICK_MS)); }
$("bPrev").onclick = function () { gotoFrame(frameAt(S.t) - 1); };
$("bNext").onclick = function () { gotoFrame(frameAt(S.t) + 1); };
["facing", "walk", "pscale", "hurtR"].forEach(function (id) { $(id).onchange = function () { resetSim(S.t); }; });
$("timeline").onclick = function (ev) { if (!S.ch) return; var r = this.getBoundingClientRect(); S.playing = false; $("bPlay").textContent = "▶ Play"; resetSim(Math.round((ev.clientX - r.left) / r.width * totalTicks())); };
window.addEventListener("resize", buildTimeline);
document.addEventListener("keydown", function (ev) {
  if (/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
  if (ev.code === "Space") { ev.preventDefault(); $("bPlay").click(); }
  if (ev.key === "ArrowLeft") $("bPrev").click();
  if (ev.key === "ArrowRight") $("bNext").click();
});
// canvas: drag the target (left), pan (right/middle), zoom (wheel)
var drag = null;
cv.addEventListener("contextmenu", function (e) { e.preventDefault(); });
cv.addEventListener("pointerdown", function (e) {
  var r = cv.getBoundingClientRect(), w = toWorld(e.clientX - r.left, e.clientY - r.top);
  drag = e.button === 0 ? {kind: "target"} : {kind: "pan", x: e.clientX, y: e.clientY, p: S.pan.slice()};
  if (drag.kind === "target") { S.target = w; if (!S.playing) resetSim(S.t); }
  cv.setPointerCapture(e.pointerId);
});
cv.addEventListener("pointermove", function (e) {
  if (!drag) return;
  var r = cv.getBoundingClientRect();
  if (drag.kind === "target") { S.target = toWorld(e.clientX - r.left, e.clientY - r.top); if (!S.playing) resetSim(S.t); }
  else S.pan = [drag.p[0] + e.clientX - drag.x, drag.p[1] + e.clientY - drag.y];
});
cv.addEventListener("pointerup", function () { drag = null; });
cv.addEventListener("wheel", function (e) { e.preventDefault(); var z = zoom() * (e.deltaY < 0 ? 1.15 : 1 / 1.15); $("zoom").value = Math.round(Math.max(0.5, Math.min(40, z)) * 100) / 100; }, {passive: false});
// drag-and-drop files
var dropEl = $("drop");
window.addEventListener("dragover", function (e) { e.preventDefault(); dropEl.style.display = "flex"; });
window.addEventListener("dragleave", function (e) { if (!e.relatedTarget) dropEl.style.display = "none"; });
window.addEventListener("drop", function (e) { e.preventDefault(); dropEl.style.display = "none"; var f = e.dataTransfer.files[0]; if (f) readFile(f); });

buildPresets();
var saved = lsGet(LS_PROJECT);
if (saved && saved.ch) { S.action = saved.action; if (loadCharacter(saved.ch, saved.effects) && saved.headUnits) S.headUnits = saved.headUnits; }
requestAnimationFrame(loop);
window.FXStudio = {S: S, ingest: ingest, rebuild: rebuild, fxBlock: fxBlock, resetSim: resetSim, player: player, host: host};
})();
