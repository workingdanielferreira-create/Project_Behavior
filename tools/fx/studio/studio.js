/* FX Studio — UI.  Phase 2 of character creation.
 *
 * Input: a character folder exported by Rig Forge ("Export character
 * package"): character.json (name, archetype, stats, palette, per-action
 * frame timing, starting anchors) + <action>_NN.png keyframe images, plus the
 * <name>.fxkit.json this Studio saved there before (if any).
 * Output: <name>.fxkit.json in the same folder — the FX, the anchors you
 * placed on each frame and every effect's damage settings.
 * FX maths: fxkit.js (the reference the game's laser/fxkit.py mirrors).
 */
(function () {
"use strict";
var $ = function (id) { return document.getElementById(id); };
var TARGET_HEAD_PX = 16;   // laser/config.py TARGET_HEAD_PX
var LS_PROJECT = "pbfxstudio.v2.project.", LS_PRESETS = "pbfxstudio.v1.presets";
var FRAME_RE = /^(.+)_(\d+)\.png$/i;

// C = the loaded character package; S = editor state.
var C = null;
var S = {effects: [], anchors: {}, labels: {}, actionCfg: {}, action: null, sel: null, selAnchor: null, place: false,
  t: 0, playing: false, target: [60, 0], pan: [0, 0], figX: 0, walkDir: 1, hits: [], dealt: 0, dir: null};
var player = new FXK.Player(), lut = FXK.buildLut([[255, 255, 255], [63, 176, 234]]);
var cv = $("stage"), g = cv.getContext("2d");

// ------------------------------------------------------------ helpers
function toast(msg, ms) { var t = $("toast"); t.textContent = msg; t.style.display = "block"; clearTimeout(toast._h); toast._h = setTimeout(function () { t.style.display = "none"; }, ms || 3200); }
function clone(o) { return JSON.parse(JSON.stringify(o)); }
// In-page dialogs: published pages run in a sandboxed frame where
// prompt()/confirm() never show, so every question goes through #dlg.
function ask(msg, opts, cb) {
  var d = $("dlg"), i = $("dlgIn");
  $("dlgMsg").textContent = msg;
  i.hidden = !opts.text; i.value = opts.value || "";
  $("dlgOk").textContent = opts.ok || "OK"; $("dlgNo").textContent = opts.no || "Cancel";
  var done = function (ok) { d.hidden = true; $("dlgOk").onclick = $("dlgNo").onclick = i.onkeydown = null; cb(ok, i.value); };
  $("dlgOk").onclick = function () { done(true); };
  $("dlgNo").onclick = function () { done(false); };
  i.onkeydown = function (e) { e.stopPropagation(); if (e.key === "Enter") done(true); if (e.key === "Escape") done(false); };
  d.hidden = false;
  if (opts.text) setTimeout(function () { i.focus(); i.select(); }, 20);
}
function askText(msg, value, cb) { ask(msg, {text: true, value: value}, function (ok, v) { if (ok && v.trim()) cb(v.trim()); }); }
function inFrame() { try { return window.self !== window.top; } catch (e) { return true; } }
function lsGet(k) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (e) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch (e) { return false; } }
function act() { return C && S.action ? C.actions[S.action] : null; }
function frames() { var a = act(); return a ? a.images.length : 0; }
function frameMs() { var a = act(); return a ? Math.max(1, a.frame_ms) : 16; }
function totalTicks() { return Math.max(1, Math.round(frames() * frameMs() / FXK.TICK_MS)); }
function frameAt(t) { return Math.max(0, Math.min(frames() - 1, Math.floor(Math.min(t, totalTicks() - 1) * FXK.TICK_MS / frameMs()))); }
function facing() { return +$("facing").value; }
function pscale() { return Math.max(0.25, +$("pscale").value || 1); }
function imgScale() { return TARGET_HEAD_PX / Math.max(1, C.headPx); }   // game px per image px
function actionEffects() { return S.effects.filter(function (e) { return e.action === S.action; }); }
function selFx() { return S.effects.filter(function (e) { return e.id === S.sel; })[0] || null; }
function save() { if (C) lsSet(LS_PROJECT + C.name, {effects: S.effects, anchors: S.anchors, labels: S.labels, action: S.action, action_settings: S.actionCfg}); }
function cfgOf(a) { return (S.actionCfg[a] = FXK.normalizeAction(S.actionCfg[a])); }
function anchorIds() { return Object.keys(S.labels); }

// ------------------------------------------------------------ anchors
// S.anchors[action][id] = per-frame [x, y] in image px, or null = hold the
// previous frame's position.  resolveAnchor fills holds (and leading gaps
// from the first placed frame) — the same rule the exporter bakes in.
function anchorRow(action, id) {
  var a = S.anchors[action] || (S.anchors[action] = {});
  var n = C.actions[action].images.length, row = a[id] || (a[id] = []);
  while (row.length < n) row.push(null);
  return row;
}
function resolveAnchor(action, id, f) {
  var row = (S.anchors[action] || {})[id];
  if (!row) return null;
  for (var i = Math.min(f, row.length - 1); i >= 0; i--) if (row[i]) return row[i];
  for (var j = f + 1; j < row.length; j++) if (row[j]) return row[j];
  return null;
}
function imgToGame(p) { var k = imgScale() * pscale(); return [S.figX + (p[0] - C.origin[0]) * k * facing(), (p[1] - C.origin[1]) * k]; }
function gameToImg(w) { var k = imgScale() * pscale(); return [Math.round(((w[0] - S.figX) / (k * facing()) + C.origin[0]) * 100) / 100, Math.round((w[1] / k + C.origin[1]) * 100) / 100]; }
function jointAt(name, fr) {
  if (name === "figure") return [S.figX, 0];
  if (name === "target") return S.target.slice();
  var p = resolveAnchor(S.action, name, fr);
  return p ? imgToGame(p) : [S.figX, 0];
}

// ------------------------------------------------------------ figure host
var TINT = new Map();
function tinted(img, rgb) {   // combat.silhouette(): flat colour, the frame's own alpha
  var key = img.src + "|" + rgb.join(","), c = TINT.get(key);
  if (c) return c;
  c = document.createElement("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight;
  var x = c.getContext("2d"); x.drawImage(img, 0, 0); x.globalCompositeOperation = "source-in";
  x.fillStyle = "rgb(" + rgb.join(",") + ")"; x.fillRect(0, 0, c.width, c.height);
  TINT.set(key, c); return c;
}
function drawFrame(gc, img, figX, fac, alpha, tint) {
  var k = imgScale() * pscale();
  gc.save(); gc.translate(figX, 0); gc.scale(fac * k, k);
  if (alpha != null) gc.globalAlpha *= alpha;
  gc.drawImage(tint ? tinted(img, tint) : img, -C.origin[0], -C.origin[1]);
  gc.restore();
}
var host = {
  get facing() { return facing(); },
  get target() { return S.target; },
  get wang() { return 90; },
  get lut() { return lut; },
  get pscale() { return pscale(); },
  get showHitboxes() { return true; },
  get hurt() { return {x: S.target[0], y: S.target[1], r: Math.max(1, +$("hurtR").value || 16)}; },
  anchor: function (n) { return jointAt(n, frameAt(S.t)); },
  snapshot: function () { return {action: S.action, frame: frameAt(S.t), figX: S.figX}; },
  drawGhost: function (gc, gh, rgb, a) {
    var img = C.actions[gh.snap.action].images[gh.snap.frame];
    if (img) drawFrame(gc, img, gh.snap.figX, gh.facing, a, rgb);
  },
  // Preview of what the engine does on a hit (ai.apply_hp_damage + knockback).
  onHit: function (inst, dmg, dx, dy, kb) {
    S.dealt += dmg;
    S.hits.push({t: S.t, dmg: dmg, kb: kb, name: inst.fx.name});
    if (S.hits.length > 60) S.hits.shift();
  }
};

// ------------------------------------------------------------ load
// files: [{name, file}] from a folder (picker, <input webkitdirectory> or drop).
function loadImage(file) {
  return new Promise(function (res, rej) {
    var im = new Image(); im.onload = function () { res(im); }; im.onerror = function () { rej(new Error("bad image " + file.name)); };
    im.src = URL.createObjectURL(file);
  });
}
function readText(file) { return file.text ? file.text() : new Promise(function (r) { var fr = new FileReader(); fr.onload = function () { r(fr.result); }; fr.readAsText(file); }); }
function openFiles(list, dirHandle) {
  var byName = {}, rel = (list[0] && list[0].webkitRelativePath) || "";
  var folder = dirHandle ? dirHandle.name : rel.indexOf("/") > 0 ? rel.split("/").slice(-2, -1)[0] : "";
  list.forEach(function (f) { byName[f.name] = f; });
  var manF = byName["character.json"];
  var pngs = list.filter(function (f) { return FRAME_RE.test(f.name); });
  if (!pngs.length) { toast("No <action>_NN.png frames in that folder. Export the character package from Rig Forge first.", 6000); return; }
  (manF ? readText(manF).then(JSON.parse) : Promise.resolve(null)).then(function (man) {
    if (man && man.format !== "pb_char_pkg") throw new Error("character.json is not a Rig Forge character package (format pb_char_pkg)");
    var groups = {};
    pngs.forEach(function (f) { var m = f.name.match(FRAME_RE); (groups[m[1]] = groups[m[1]] || []).push({n: +m[2], f: f}); });
    var names = man ? Object.keys(man.actions).filter(function (k) { return groups[k] || (man.actions[k].frames || []).some(function (n) { return byName[n]; }); }) : Object.keys(groups);
    var jobs = [], acts = {};
    names.forEach(function (k) {
      var files = man && man.actions[k].frames ? man.actions[k].frames.map(function (n) { return byName[n]; }).filter(Boolean)
        : (groups[k] || []).sort(function (a, b) { return a.n - b.n; }).map(function (x) { return x.f; });
      var ma = man ? man.actions[k] : null;
      acts[k] = {frame_ms: ma ? (+ma.frame_ms || (+ma.duration_ms || 100 * files.length) / files.length) : 100,
        trigger: ma ? ma.trigger : "", files: files.map(function (f) { return f.name; }), images: []};
      files.forEach(function (f, i) { jobs.push(loadImage(f).then(function (im) { acts[k].images[i] = im; })); });
    });
    var fxName = man ? man.name + ".fxkit.json" : null;
    var fxF = (fxName && byName[fxName]) || list.filter(function (f) { return /\.fxkit\.json$/i.test(f.name); })[0];
    jobs.push(fxF ? readText(fxF).then(JSON.parse) : Promise.resolve(null));
    return Promise.all(jobs).then(function (res) { return {man: man, acts: acts, pack: res[res.length - 1]}; });
  }).then(function (r) { useCharacter(r.man, r.acts, r.pack, dirHandle, folder); })
    .catch(function (e) { toast("Could not open the folder: " + e.message, 6000); });
}
function useCharacter(man, acts, pack, dirHandle, folder) {
  var first = acts[Object.keys(acts)[0]].images[0];
  var name = man ? man.name : (pack && pack.character) || folder || "character";
  C = {man: man, name: name, display: man ? man.display_name || name : name, actions: acts,
    origin: man && man.image ? man.image.origin_px : [first.naturalWidth / 2, first.naturalHeight / 2],
    headPx: man && man.image ? +man.image.head_px : 58};
  S.dir = dirHandle || null;
  var pal = (man && man.palette) || {};
  lut = FXK.buildLut([FXK.hexRgb(pal.body, [242, 244, 246]), FXK.hexRgb(pal.accent, [63, 176, 234])]);   // palette.build_lut([body, accent])
  // Anchors: this Studio's saved work wins, then the FX pack in the folder,
  // then the starting points Rig Forge exported.
  var local = lsGet(LS_PROJECT + name), src = local || pack;
  S.labels = clone((src && (src.labels || src.anchor_labels)) || (man && man.anchor_labels) || {});
  S.anchors = clone((src && src.anchors) || (man && man.anchors) || {});
  if (!Object.keys(S.labels).length) Object.keys(S.anchors[Object.keys(S.anchors)[0]] || {}).forEach(function (k) { S.labels[k] = k; });
  S.effects = ((src && src.effects) || []).map(function (e) { return FXK.normalize(e); });
  S.actionCfg = clone((src && src.action_settings) || {});
  if (local && pack) {
    ask("This browser has Studio work for " + name + " that may differ from " + name + ".fxkit.json in the folder. Which should open?",
      {ok: "My browser work", no: "The folder's file"}, function (keep) {
        if (!keep) {
          S.labels = clone(pack.anchor_labels || S.labels); S.anchors = clone(pack.anchors || {}); S.effects = (pack.effects || []).map(FXK.normalize);
          S.actionCfg = clone(pack.action_settings || {});
        }
        finishOpen(man, acts, pack, name, local);
      });
    return;
  }
  finishOpen(man, acts, pack, name, local);
}
function finishOpen(man, acts, pack, name, local) {
  var names = Object.keys(acts);
  S.action = (local && names.indexOf(local.action) >= 0) ? local.action : names.indexOf("attack_normal") >= 0 ? "attack_normal" : names[0];
  S.sel = null; S.selAnchor = null; S.figX = 0;
  $("charname").textContent = C.display + "  (" + name + ")" + (man ? "" : "  — no character.json: timing 100 ms/frame, head 58 px");
  $("empty").style.display = "none";
  rebuild(); resetSim(0); save();
  toast("Opened " + C.display + ": " + names.length + " actions" + (pack ? ", " + S.effects.length + " FX" : ""));
}
function pickFolder() {
  if (window.showDirectoryPicker && !inFrame()) {
    window.showDirectoryPicker({mode: "readwrite"}).then(function (dir) {
      var list = [];
      return (async function () { for await (var e of dir.values()) if (e.kind === "file") list.push(await e.getFile()); })()
        .then(function () { openFiles(list, dir); });
    }).catch(function (e) { if (e && e.name !== "AbortError") toast("Could not open: " + e.message, 5000); });
  } else $("dirIn").click();
}

// ------------------------------------------------------------ export
function packData() {
  var anchors = {};
  Object.keys(C.actions).forEach(function (a) {
    anchors[a] = {};
    anchorIds().forEach(function (id) {
      var n = C.actions[a].images.length, row = [];
      for (var f = 0; f < n; f++) { var p = resolveAnchor(a, id, f); row.push(p ? [p[0], p[1]] : null); }
      if (row.some(Boolean)) anchors[a][id] = row;
    });
  });
  return {format: "pb_fxkit", version: 2, tick_ms: FXK.TICK_MS, character: C.name,
    space: {coords: "game px, y down, relative to the figure position; x mirrors when facing left",
      anchors: "image px of the character's keyframe PNGs (per action, per frame); game px = (p - image_origin_px) * game_px_per_image_px * position_scale",
      image_origin_px: C.origin, head_px: C.headPx, target_head_px: TARGET_HEAD_PX,
      game_px_per_image_px: Math.round(imgScale() * 1e6) / 1e6},
    timing: Object.fromEntries(Object.keys(C.actions).map(function (k) { return [k, {frame_ms: C.actions[k].frame_ms, frames: C.actions[k].images.length}]; })),
    palette_lut: {built_from: ["palette.body", "palette.accent"], rule: "palette.build_lut([body, accent])"},
    anchor_labels: S.labels, anchors: anchors,
    action_settings: Object.fromEntries(Object.keys(C.actions).map(function (k) { return [k, cfgOf(k)]; })),
    effects: S.effects.map(function (e) { return FXK.normalize(clone(e)); }),
    spec: "tools/fx/FX_KIT_SPEC.md — runtime reference tools/fx/studio/fxkit.js"};
}
function saveFx() {
  if (!C) return toast("Open a character folder first");
  var name = C.name + ".fxkit.json", txt = JSON.stringify(packData(), null, 1);
  if (S.dir && S.dir.getFileHandle && !inFrame()) {
    S.dir.getFileHandle(name, {create: true}).then(function (h) { return h.createWritable(); })
      .then(function (w) { return w.write(txt).then(function () { return w.close(); }); })
      .then(function () { toast("Saved " + name + " into " + S.dir.name + "/"); })
      .catch(function (e) { toast("Could not write into the folder (" + e.message + "); downloading instead.", 5000); download(name, txt); });
  } else download(name, txt);
}
function download(name, txt) {
  // A published page hands files over through the downloads capability
  // (the viewer confirms each save); opened from disk it is a plain download.
  if (inFrame() && window.claude && typeof window.claude.use === "function") {
    window.claude.use("downloads").then(function (d) {
      if (!d) return openModal("Copy this JSON into " + name, txt, null);
      d.save({filename: name, data: new Blob([txt], {type: "application/json"})}).then(function () {
        toast("Saved " + name + ": put it in characters/" + (C ? C.name : "<name>") + "/");
      }, function (e) {
        var c = e && e.code;
        if (c === "declined") return toast("Save cancelled");
        if (c === "rate_limited") return toast("A save prompt is already open. Try again in a moment.");
        openModal("Copy this JSON into " + name, txt, null);
      });
    });
    return;
  }
  try {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([txt], {type: "application/json"}));
    a.download = name; document.body.appendChild(a); a.click(); a.remove();
    toast("Downloaded " + name + ": put it in characters/" + (C ? C.name : "<name>") + "/");
  } catch (e) { openModal("Copy this JSON (" + name + ")", txt, null); }
}

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
  if (!C) return toast("Open a character folder first");
  var x = allPresets()[+$("presetSel").value]; if (!x) return;
  var added = x.p.effects.map(function (e) {
    var fx = clone(e); fx.id = FXK.newEffect(fx.prim).id; fx.action = S.action;
    if (fx.prim === "ghost" && !fx.layer) fx.layer = "behind";
    return FXK.normalize(fx);
  });
  S.effects = S.effects.concat(added); S.sel = added[0].id; rebuild(); resetSim(S.t); save();
  var missing = added.filter(function (fx) { return fx.anchor !== "figure" && fx.anchor !== "target" && !S.labels[fx.anchor]; });
  if (missing.length) toast("This character has no \"" + missing[0].anchor + "\" anchor: add it under Anchors, or pick another joint.", 6000);
}
function savePreset() {
  var fx = selFx(); if (!fx) return;
  askText("Save this effect as a preset named:", fx.name, function (name) {
  var e = clone(fx); delete e.id; delete e.action;
  var mine = userPresets().filter(function (p) { return p.name !== name; });
  mine.push({name: name, desc: "Your preset (" + fx.prim + ")", effects: [e]});
  if (!lsSet(LS_PRESETS, mine)) toast("Browser storage unavailable; use Export to keep presets.", 5000);
  buildPresets(); toast("Saved preset " + name);
  });
}
function ingestPresets(o) {
  if (!o || o.format !== "pb_fx_presets") return toast("Not a presets file (pb_fx_presets)");
  var mine = userPresets(), n = 0;
  (o.presets || []).forEach(function (p) { if (p && p.name && p.effects) { mine = mine.filter(function (q) { return q.name !== p.name; }); mine.push(p); n++; } });
  lsSet(LS_PRESETS, mine); buildPresets(); toast("Imported " + n + " presets");
}

// ------------------------------------------------------------ lists
function rebuild() { buildActions(); buildAnchors(); buildEffects(); buildProps(); buildTimeline(); }
function buildActions() {
  var d = $("actions"); d.innerHTML = "";
  if (!C) return;
  Object.keys(C.actions).forEach(function (n) {
    var a = C.actions[n], c = S.effects.filter(function (e) { return e.action === n; }).length;
    var el = document.createElement("div"); el.className = n === S.action ? "sel" : "";
    el.innerHTML = '<span class="n"></span><span class="m"></span>';
    el.querySelector(".n").textContent = n;
    el.querySelector(".m").textContent = a.images.length + "f · " + Math.round(a.images.length * a.frame_ms) + "ms" + (c ? " · " + c + " fx" : "");
    el.onclick = function () { S.action = n; S.sel = null; rebuild(); resetSim(0); save(); };
    d.appendChild(el);
  });
}
function buildAnchors() {
  var d = $("anchors"); d.innerHTML = "";
  if (!C) return;
  anchorIds().forEach(function (id) {
    var placed = ((S.anchors[S.action] || {})[id] || []).filter(Boolean).length;
    var el = document.createElement("div"); el.className = id === S.selAnchor ? "sel" : "";
    el.innerHTML = '<span class="n"></span><span class="m"></span><span class="x" title="Delete anchor">✕</span>';
    el.querySelector(".n").textContent = S.labels[id] + (S.labels[id] !== id ? " (" + id + ")" : "");
    el.querySelector(".m").textContent = placed + "/" + frames();
    el.querySelector(".x").onclick = function (ev) {
      ev.stopPropagation();
      ask("Delete anchor \"" + S.labels[id] + "\" on every action?", {ok: "Delete"}, function (ok) {
        if (!ok) return;
        delete S.labels[id]; Object.keys(S.anchors).forEach(function (a) { delete S.anchors[a][id]; });
        if (S.selAnchor === id) S.selAnchor = null; rebuild(); resetSim(S.t); save();
      });
    };
    el.onclick = function () { S.selAnchor = S.selAnchor === id ? null : id; buildAnchors(); anchorTools(); };
    d.appendChild(el);
  });
  anchorTools();
}
function anchorTools() {
  var on = !!S.selAnchor;
  $("bPlace").disabled = !on; $("bFill").disabled = !on; $("bClearKf").disabled = !on;
  $("bPlace").className = S.place && on ? "on" : ""; $("bPlace").textContent = S.place && on ? "Placing… (P)" : "Place (P)";
  if (!on) S.place = false;
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
  ghost: [["interval", "Every N ticks", 1, 60, 1], ["ghost_life", "Ghost life ticks", 1, 240, 1], ["alpha", "Start alpha", 0, 255, 1], ["max", "Max ghosts", 1, 60, 1]],
  weapon: [["to_anchor", "To anchor", "anchor"], ["width", "Hitbox width px", 1, 80, 0.5]]
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
function note(parent, text) { var n = document.createElement("div"); n.className = "note"; n.textContent = text; parent.appendChild(n); }
function changed(rebuildProps) { resetSim(S.t); buildTimeline(); save(); if (rebuildProps) buildProps(); }
function anchorOptions(withSpecial) {
  var o = anchorIds().map(function (j) { return [j, S.labels[j] + (S.labels[j] !== j ? " (" + j + ")" : "")]; });
  return withSpecial ? [["figure", "figure (image centre)"], ["target", "target"]].concat(o) : o;
}

function buildProps() {
  var d = $("props"); d.innerHTML = ""; d.className = "";
  var fx = selFx();
  if (!fx) { if (C) buildActionProps(d); else { d.className = "note"; d.textContent = "Open a character folder to begin."; } return; }
  var s = sec(d, "Effect");
  field(s, "Name", inp("text", fx.name, function (v) { fx.name = v; buildEffects(); buildTimeline(); save(); }));
  field(s, "Tag (FX type)", inp("text", fx.tag, function (v) { fx.tag = v.trim().toLowerCase(); save(); })).title =
    "What kind of FX this is (e.g. fireball, slash, beam). Other characters' defend / deflect triggers react to these tags.";
  field(s, "Primitive", inp(FXK.PRIMS, fx.prim, function (v) { fx.prim = v; fx.params = {}; FXK.normalize(fx); buildEffects(); changed(true); }));
  if (fx.prim !== "weapon") {
    field(s, "Layer", inp([["front", "in front of figure"], ["behind", "behind figure"]], fx.layer, function (v) { fx.layer = v; changed(); }));
    field(s, "Blend", inp(["normal", "additive"], fx.blend, function (v) { fx.blend = v; changed(); }));
  }
  field(s, "Action", inp(Object.keys(C.actions), fx.action, function (v) { fx.action = v; S.action = v; rebuild(); resetSim(0); save(); }));

  s = sec(d, "Purpose");
  var bt = fx.battle;
  if (fx.prim === "ghost") note(s, "Afterimages are visual only.");
  else {
    field(s, "Deals damage", inp("chk", bt.deals_damage, function (v) { bt.deals_damage = v; buildEffects(); changed(true); })).title =
      "Checked: this FX is an attack and damages the target where it touches. Unchecked: visual only.";
    if (bt.deals_damage) {
      field(s, "Damage HP per hit", inp("n", bt.damage, function (v) { bt.damage = Math.max(0, v); buildEffects(); changed(); }, 0, 1000, 0.5));
      field(s, "Pierce (keeps going)", inp("chk", bt.pierce, function (v) { bt.pierce = v; changed(); }));
      field(s, "Re-hit every N ticks (0 = once)", inp("n", bt.rehit_ticks, function (v) { bt.rehit_ticks = Math.max(0, Math.round(v)); changed(); }, 0, 600, 1));
      field(s, "Knockback px", inp("n", bt.knockback, function (v) { bt.knockback = Math.max(0, v); changed(); }, 0, 200, 0.5));
    } else note(s, fx.prim === "weapon" ? "The weapon doesn't damage in this window." : "Visual only — this FX never damages.");
  }

  s = sec(d, "Timing (frames of " + fx.action + ": 0–" + (frames() - 1) + ")");
  field(s, "Start frame", inp("n", fx.start_frame, function (v) { fx.start_frame = Math.max(0, Math.round(v)); changed(); }, 0, frames() - 1, 1));
  field(s, "End frame (-1 = end)", inp("n", fx.end_frame, function (v) { fx.end_frame = Math.round(v); changed(); }, -1, frames() - 1, 1));
  if (fx.prim !== "weapon") {
    field(s, "Life ticks (0 = to end)", inp("n", fx.life_ticks, function (v) { fx.life_ticks = Math.max(0, Math.round(v)); changed(); }, 0, 5000, 1));
    field(s, "Re-emit every N ticks", inp("n", fx.emit.every_ticks, function (v) { fx.emit.every_ticks = Math.max(0, Math.round(v)); changed(); }, 0, 600, 1));
    field(s, "Count per emit", inp("n", fx.emit.count, function (v) { fx.emit.count = Math.max(1, Math.round(v)); changed(); }, 1, 64, 1));
    field(s, "Fan ° (count > 1)", inp("n", fx.emit.fan_deg, function (v) { fx.emit.fan_deg = v; changed(); }, 0, 360, 1));
  }

  s = sec(d, fx.prim === "weapon" ? "Hitbox (from anchor → to anchor)" : "Anchor");
  field(s, fx.prim === "weapon" ? "From anchor" : "Joint", inp(anchorOptions(fx.prim !== "weapon"), fx.anchor, function (v) { fx.anchor = v; changed(); }));
  if (fx.prim !== "weapon") {
    field(s, "Offset X px", inp("n", fx.offset[0], function (v) { fx.offset[0] = v; changed(); }, -500, 500, 0.5));
    field(s, "Offset Y px", inp("n", fx.offset[1], function (v) { fx.offset[1] = v; changed(); }, -500, 500, 0.5));
  }

  if (fx.prim !== "weapon") {
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
  }

  s = sec(d, fx.prim + " parameters");
  PARAM_UI[fx.prim].forEach(function (u) {
    var k = u[0], kind = u[2];
    field(s, u[1], Array.isArray(kind) ? inp(kind, fx.params[k], function (v) { fx.params[k] = v; changed(); })
      : kind === "chk" ? inp("chk", fx.params[k], function (v) { fx.params[k] = v; changed(); })
      : kind === "color" ? inp("color", fx.params[k] || "#000000", function (v) { fx.params[k] = v; changed(); })
      : kind === "anchor" ? inp(anchorOptions(false), fx.params[k], function (v) { fx.params[k] = v; changed(); })
      : inp("n", fx.params[k], function (v) { fx.params[k] = v; changed(); }, u[2], u[3], u[4]));
  });
  var r = document.createElement("div"); r.className = "row";
  var b = document.createElement("button"); b.textContent = "Save as preset…"; b.onclick = savePreset; r.appendChild(b);
  d.appendChild(r);
}

var COND_LABEL = {hp_below: "own HP at or below %", attacks_made: "after N attacks made", hits_taken: "after N hits taken",
  target_within: "target closer than px", target_beyond: "target further than px", hit_by_fx: "hit by FX tagged",
  fx_near: "enemy FX tagged … within px", bullet_deflected: "a bullet was deflected", after_actions: "after completing actions in order"};
var COND_FIELDS = {pct: ["HP %", 1, 100, 1], count: ["Count", 1, 100, 1], px: ["Distance px", 1, 2000, 1],
  tags: ["Tags (comma, empty = any)", "text"], sequence: ["Actions (comma separated)", "text"], repeat: ["Repeat on cooldown", "chk"]};
// Right panel when no effect is selected: WHEN this action plays.
function buildActionProps(d) {
  var a = S.action, cfg = cfgOf(a), kind = FXK.actionKind(a);
  var s = sec(d, "Action: " + a);
  note(s, kind === "locomotion" ? (a === "idle" ? "Plays while the fighter stands still." : "Plays while the fighter moves.")
    : kind === "attack" ? "The archetype decides when to attack. The attack plays in full, and only this action's FX with Deals damage (and weapon hitboxes) hurt."
    : "Plays when its conditions are met, then runs in full.");
  note(s, frames() + " frames × " + Math.round(frameMs() * 10) / 10 + " ms = " + Math.round(frames() * frameMs()) + " ms (timing comes from Rig Forge)");
  if (kind === "locomotion") return;
  if (kind === "attack") {
    s = sec(d, "Attack chain (combo)");
    var others = [["", "— none (every attack plays " + a + ") —"]].concat(Object.keys(C.actions).filter(function (k) { return k !== a && FXK.actionKind(k) === "attack"; }).map(function (k) { return [k, k]; }));
    field(s, "Next attack", inp(others, cfg.chain_next, function (v) { cfg.chain_next = v; save(); buildProps(); }));
    field(s, "Reset after ms idle", inp("n", cfg.chain_reset_ms, function (v) { cfg.chain_reset_ms = Math.max(0, v); save(); }, 0, 10000, 50));
    if (others.length === 1) note(s, "To chain, add more attack actions in Rig Forge named attack_normal_2, attack_normal_3 … and export again.");
    return;
  }
  s = sec(d, "Trigger conditions");
  field(s, "Fire when", inp([["any", "ANY condition is met"], ["all", "ALL conditions are met"]], cfg.logic, function (v) { cfg.logic = v; save(); }));
  field(s, "Cooldown ms", inp("n", cfg.cooldown_ms, function (v) { cfg.cooldown_ms = Math.max(0, v); save(); }, 0, 60000, 50));
  cfg.conditions.forEach(function (c, i) {
    var box = sec(d, (i + 1) + ". " + COND_LABEL[c.type]);
    Object.keys(FXK.CONDITION_TYPES[c.type]).forEach(function (k) {
      var u = COND_FIELDS[k];
      field(box, u[0], u[1] === "text" ? inp("text", c[k], function (v) { c[k] = v; save(); })
        : u[1] === "chk" ? inp("chk", c[k], function (v) { c[k] = v; save(); })
        : inp("n", c[k], function (v) { c[k] = v; save(); }, u[1], u[2], u[3]));
    });
    var rm = document.createElement("button"); rm.textContent = "Remove"; rm.onclick = function () { cfg.conditions.splice(i, 1); save(); buildProps(); };
    box.appendChild(rm);
  });
  var row = document.createElement("div"); row.className = "row";
  var sel = inp(Object.keys(FXK.CONDITION_TYPES).map(function (k) { return [k, COND_LABEL[k]]; }), "hp_below", function () {});
  var add = document.createElement("button"); add.textContent = "+ Condition";
  add.onclick = function () { cfg.conditions.push(FXK.normalizeAction({conditions: [{type: sel.value}]}).conditions[0]); save(); buildProps(); };
  row.appendChild(sel); row.appendChild(add); d.appendChild(row);
  if (!cfg.conditions.length) note(d, "No conditions yet: this action never fires on its own.");
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
  if (!C) return;
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
  if (S.playing && C && act()) {
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
  if (!C || !act()) return;
  var c = camera(dpr), z = c.z;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.strokeStyle = "rgba(255,255,255,.04)"; g.lineWidth = 1;   // grid: one line per 10 game px
  var step10 = 10 * z, x0 = ((c.x % step10) + step10) % step10, y0 = ((c.y % step10) + step10) % step10;
  for (var x = x0; x < cv.width / dpr; x += step10) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, cv.height); g.stroke(); }
  for (var y = y0; y < cv.height / dpr; y += step10) { g.beginPath(); g.moveTo(0, y); g.lineTo(cv.width, y); g.stroke(); }
  g.translate(c.x, c.y); g.scale(z, z);
  var ps = pscale(), fr = frameAt(S.t), img = act().images[fr];
  if ($("lightbg").checked) { g.fillStyle = "rgba(235,238,244,.9)"; var k = imgScale() * ps; g.fillRect(S.figX - C.origin[0] * k, -C.origin[1] * k, img.naturalWidth * k, img.naturalHeight * k); }
  player.draw(g, host, "behind", ps);
  drawFrame(g, img, S.figX, facing());
  player.draw(g, host, "front", ps);
  // target + hurt radius (the circle damaging FX must touch)
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
  // anchors: all (when "anchors" is ticked), the selected FX's, and the one being placed with its path
  var fx = selFx(), show = $("joints").checked;
  anchorIds().forEach(function (j) {
    var on = (fx && (fx.anchor === j || (fx.prim === "weapon" && fx.params.to_anchor === j))) || j === S.selAnchor;
    if (!show && !on) return;
    var own = ((S.anchors[S.action] || {})[j] || [])[fr], p = resolveAnchor(S.action, j, fr);
    if (!p) return;
    var q = imgToGame(p);
    g.fillStyle = j === S.selAnchor ? "#7de0a8" : on ? "#f0c24a" : "rgba(63,176,234,.85)";
    g.beginPath(); g.arc(q[0], q[1], (on ? 3 : 2) / z * 2, 0, 6.2832); if (own) g.fill(); else { g.lineWidth = 1 / z; g.strokeStyle = g.fillStyle; g.stroke(); }
    if (j === S.selAnchor || show) { g.fillStyle = "rgba(220,230,240,.8)"; g.font = (9 / z) + "px sans-serif"; g.fillText(S.labels[j], q[0] + 5 / z, q[1] - 4 / z); }
  });
  if (S.selAnchor) {   // the anchor's path over the whole action
    g.strokeStyle = "rgba(125,224,168,.35)"; g.lineWidth = 1 / z; g.beginPath();
    for (var f = 0; f < frames(); f++) { var pp = resolveAnchor(S.action, S.selAnchor, f); if (!pp) continue; var w = imgToGame(pp); if (f) g.lineTo(w[0], w[1]); else g.moveTo(w[0], w[1]); }
    g.stroke();
  }
  $("hud").textContent = S.action + "   frame " + fr + "/" + (frames() - 1) + "   tick " + S.t + "/" + totalTicks() +
    "   " + Math.round(frameMs() * 10) / 10 + " ms/frame   " + player.insts.length + " live FX   damage this loop " + S.dealt + " HP" +
    (S.place && S.selAnchor ? "   PLACING \"" + S.labels[S.selAnchor] + "\": click the figure" : "");
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
$("bOpen").onclick = pickFolder;
$("dirIn").onchange = function () { var l = Array.prototype.slice.call(this.files); this.value = ""; if (l.length) openFiles(l, null); };
$("bSave").onclick = saveFx;
$("bAdd").onclick = function () {
  if (!C) return toast("Open a character folder first");
  var fx = FXK.newEffect($("newPrim").value, S.action);
  if (fx.prim === "ghost") fx.layer = "behind";
  if (["arc", "beam", "sprite"].indexOf(fx.prim) >= 0) { fx.motion.kind = "travel"; fx.life_ticks = fx.prim === "arc" ? 5 : 60; }
  if (fx.prim === "particles") { fx.motion.kind = "static"; fx.life_ticks = 1; }
  if (fx.prim === "weapon") {
    fx.name = "Weapon hitbox"; fx.battle.deals_damage = true;
    fx.anchor = S.labels.haR ? "haR" : anchorIds()[0] || "figure";
    fx.params.to_anchor = S.labels.wtip ? "wtip" : anchorIds()[1] || fx.anchor;
  }
  S.effects.push(fx); S.sel = fx.id; rebuild(); resetSim(S.t); save();
};
$("bAnchorAdd").onclick = function () {
  if (!C) return;
  askText("New anchor name (e.g. blade tip, gun muzzle):", "", function (label) {
  var id = label.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "anchor";
  while (S.labels[id]) id += "_2";
  S.labels[id] = label.trim(); S.selAnchor = id; S.place = true; rebuild(); save();
  toast("Click on the figure to place \"" + label + "\" on this frame; it holds on later frames until you place it again.", 5000);
  });
};
$("bPlace").onclick = function () { S.place = !S.place; anchorTools(); };
$("bFill").onclick = function () {
  var p = resolveAnchor(S.action, S.selAnchor, frameAt(S.t)); if (!p) return toast("Place it on this frame first");
  var row = anchorRow(S.action, S.selAnchor); for (var i = 0; i < row.length; i++) row[i] = p.slice();
  buildAnchors(); resetSim(S.t); save(); toast("Copied to all " + row.length + " frames");
};
$("bClearKf").onclick = function () { var row = anchorRow(S.action, S.selAnchor); row[frameAt(S.t)] = null; buildAnchors(); resetSim(S.t); save(); };
$("presetSel").onchange = showPresetDesc; $("bPreset").onclick = addPreset;
$("bPresetDel").onclick = function () {
  var x = allPresets()[+$("presetSel").value]; if (!x) return;
  if (x.builtin) return toast("Built-in presets can't be deleted.");
  lsSet(LS_PRESETS, userPresets().filter(function (p) { return p.name !== x.p.name; })); buildPresets();
};
$("bPresetExport").onclick = function () { var mine = userPresets(); if (!mine.length) return toast("No saved presets yet"); download("fx_presets.json", JSON.stringify({format: "pb_fx_presets", version: 1, presets: mine}, null, 1)); };
$("bPresetImport").onclick = function () { $("pfile").click(); };
$("pfile").onchange = function () { var f = this.files[0]; this.value = ""; if (f) readText(f).then(function (t) { ingestPresets(JSON.parse(t)); }).catch(function (e) { toast("Could not read: " + e.message); }); };
$("bPlay").onclick = function () { if (!C) return; S.playing = !S.playing; if (S.playing && S.t >= totalTicks()) resetSim(0); this.textContent = S.playing ? "❚❚ Pause" : "▶ Play"; };
function gotoFrame(f) { if (!C) return; S.playing = false; $("bPlay").textContent = "▶ Play"; f = (f + frames()) % frames(); resetSim(Math.ceil(f * frameMs() / FXK.TICK_MS)); }
$("bPrev").onclick = function () { gotoFrame(frameAt(S.t) - 1); };
$("bNext").onclick = function () { gotoFrame(frameAt(S.t) + 1); };
["facing", "walk", "pscale", "hurtR"].forEach(function (id) { $(id).onchange = function () { resetSim(S.t); }; });
$("timeline").onclick = function (ev) { if (!C) return; var r = this.getBoundingClientRect(); S.playing = false; $("bPlay").textContent = "▶ Play"; resetSim(Math.round((ev.clientX - r.left) / r.width * totalTicks())); };
window.addEventListener("resize", buildTimeline);
document.addEventListener("keydown", function (ev) {
  if (/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
  if (ev.code === "Space") { ev.preventDefault(); $("bPlay").click(); }
  if (ev.key === "ArrowLeft") $("bPrev").click();
  if (ev.key === "ArrowRight") $("bNext").click();
  if ((ev.key === "p" || ev.key === "P") && S.selAnchor) $("bPlace").click();
});
// canvas: place an anchor or drag the target (left), pan (right/middle), zoom (wheel)
var drag = null;
cv.addEventListener("contextmenu", function (e) { e.preventDefault(); });
cv.addEventListener("pointerdown", function (e) {
  if (!C) return;
  var r = cv.getBoundingClientRect(), w = toWorld(e.clientX - r.left, e.clientY - r.top);
  if (e.button === 0 && S.place && S.selAnchor) {
    var fr = frameAt(S.t); anchorRow(S.action, S.selAnchor)[fr] = gameToImg(w);
    buildAnchors(); save();
    if ($("autoNext").checked && fr < frames() - 1) gotoFrame(fr + 1); else resetSim(S.t);
    return;
  }
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
// drag-and-drop: a whole character folder, or its files
var dropEl = $("drop");
function walkEntry(entry, out) {
  return new Promise(function (res) {
    if (entry.isFile) entry.file(function (f) { out.push(f); res(); }, function () { res(); });
    else if (entry.isDirectory) {
      var rd = entry.createReader(), all = [];
      (function more() { rd.readEntries(function (es) { if (!es.length) Promise.all(all.map(function (x) { return walkEntry(x, out); })).then(res); else { all = all.concat(es); more(); } }, function () { res(); }); })();
    } else res();
  });
}
window.addEventListener("dragover", function (e) { e.preventDefault(); dropEl.style.display = "flex"; });
window.addEventListener("dragleave", function (e) { if (!e.relatedTarget) dropEl.style.display = "none"; });
window.addEventListener("drop", function (e) {
  e.preventDefault(); dropEl.style.display = "none";
  var items = e.dataTransfer.items, out = [];
  var entries = items ? Array.prototype.map.call(items, function (it) { return it.webkitGetAsEntry && it.webkitGetAsEntry(); }).filter(Boolean) : [];
  if (entries.length) Promise.all(entries.map(function (en) { return walkEntry(en, out); })).then(function () {
    if (out.length === 1 && /\.json$/i.test(out[0].name) && !/^character\.json$/i.test(out[0].name)) readText(out[0]).then(function (t) { ingestPresets(JSON.parse(t)); });
    else openFiles(out, null);
  });
  else openFiles(Array.prototype.slice.call(e.dataTransfer.files), null);
});

// Collapsible left-panel sections; open/closed state remembered per browser.
Array.prototype.forEach.call(document.querySelectorAll("details.panel"), function (d) {
  var k = "pbfxstudio.v1.sec." + d.id, v = lsGet(k);
  if (v === false) d.open = false;
  d.addEventListener("toggle", function () { lsSet(k, d.open); if (d.id === "secEffects" && d.open) buildTimeline(); });
});
buildPresets();
requestAnimationFrame(loop);
window.FXStudio = {S: S, get C() { return C; }, openFiles: openFiles, packData: packData, resetSim: resetSim, player: player, host: host, rebuild: rebuild};
})();
