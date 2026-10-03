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
var LS_PROJECT = "pbfxstudio.v2.project.", LS_PRESETS = "pbfxstudio.v1.presets", LS_GEO = "pbfxstudio.v1.geopresets";
var FRAME_RE = /^(.+)_(\d+)\.png$/i;

// C = the loaded character package; S = editor state.
var C = null;
var S = {effects: [], groups: [], multi: [], selGroup: null, anchors: {}, labels: {}, actionCfg: {}, action: null, sel: null, selAnchor: null, place: false,
  entries: [], paths: [], geo: null, geoPlace: false, aim: FXK.normalizeAim({}), damaged: FXK.normalizeDamaged({}), retreat: FXK.normalizeRetreat({}),
  t: 0, playing: false, target: [60, 0], pan: [0, 0], figX: 0, figY: 0, vel: [0, 0], walkDir: 1, hits: [], dealt: 0, dir: null};
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
// Facing: the chosen side, or (with "face movement") the side the figure is
// moving toward, the way the game flips a moving fighter.
function facing() {
  if (S.aim.enabled && aimRef()) return S.target[0] < S.figX - 0.001 ? -1 : 1;   // aiming: always faces the target
  if ($("faceMove").checked && Math.abs(S.vel[0]) > 0.01) return S.vel[0] < 0 ? -1 : 1;
  return +$("facing").value;
}
function pscale() { return Math.max(0.25, +$("pscale").value || 1); }
function imgScale() { return C.k || TARGET_HEAD_PX / Math.max(1, C.headPx); }   // game px per image px (stand-height scale)
function actionEffects() { return S.effects.filter(function (e) { return e.action === S.action; }); }
function selFx() { return S.effects.filter(function (e) { return e.id === S.sel; })[0] || null; }
function save() { if (C) { syncKeyView(); persist(); record(); } }
function persist() { lsSet(LS_PROJECT + C.name, {effects: S.effects, groups: S.groups, anchors: S.anchors, labels: S.labels, action: S.action, action_settings: S.actionCfg, entry_sets: S.entries, paths: S.paths, aim: S.aim, damaged: S.damaged, retreat: S.retreat, scale: imgScale(), img_head: C.headPx, img_origin: C.origin, saved_at: Date.now()}); }

// ------------------------------------------------------------ undo / redo
// Every edit ends in save(), so history snapshots the editable data there:
// effects, anchors (and their names) and action settings.  A burst of edits
// (typing in a field, placing anchors quickly) settles into one step after
// 400 ms.  Ctrl+Z undoes, Ctrl+Y / Ctrl+Shift+Z redoes.
var HIST = {past: [], future: [], cur: null, timer: 0};
function snapState() { return JSON.stringify({e: S.effects, g: S.groups, a: S.anchors, l: S.labels, c: S.actionCfg, en: S.entries, pa: S.paths, am: S.aim, dm: S.damaged, rt: S.retreat}); }
function histReset() { HIST.past = []; HIST.future = []; HIST.cur = snapState(); clearTimeout(HIST.timer); HIST.timer = 0; histUI(); }
function record() {
  clearTimeout(HIST.timer);
  HIST.timer = setTimeout(commitHist, 400);
}
function commitHist() {
  HIST.timer = 0;
  var now = snapState();
  if (HIST.cur === null) { HIST.cur = now; return; }
  if (now === HIST.cur) return;
  HIST.past.push(HIST.cur); if (HIST.past.length > 200) HIST.past.shift();
  HIST.cur = now; HIST.future = []; histUI();
}
function applyState(str) {
  var o = JSON.parse(str);
  S.effects = o.e.map(FXK.normalize); S.groups = o.g || []; S.anchors = o.a; S.labels = o.l; S.actionCfg = o.c;
  S.entries = (o.en || []).map(FXK.normalizeEntrySet); S.paths = (o.pa || []).map(FXK.normalizePath);
  S.aim = FXK.normalizeAim(o.am);
  S.damaged = FXK.normalizeDamaged(o.dm);
  S.retreat = FXK.normalizeRetreat(o.rt);
  if (S.geo && !geoItem()) { S.geo = null; S.geoPlace = false; }
  if (S.sel && !S.effects.some(function (e) { return e.id === S.sel; })) S.sel = null;
  pruneGroups();
  if (S.selAnchor && !S.labels[S.selAnchor]) { S.selAnchor = null; S.place = false; }
  HIST.cur = str; persist(); rebuild(); resetSim(S.t); histUI();
}
function undo() {
  if (!C) return;
  if (HIST.timer) { clearTimeout(HIST.timer); commitHist(); }
  if (!HIST.past.length) return toast("Nothing to undo");
  HIST.future.push(HIST.cur); applyState(HIST.past.pop()); toast("Undone");
}
function redo() {
  if (!C) return;
  if (HIST.timer) { clearTimeout(HIST.timer); commitHist(); }
  if (!HIST.future.length) return toast("Nothing to redo");
  HIST.past.push(HIST.cur); applyState(HIST.future.pop()); toast("Redone");
}
function histUI() { var u = $("bUndo"), r = $("bRedo"); if (u) u.disabled = !HIST.past.length; if (r) r.disabled = !HIST.future.length; }
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
// Aim (pack.aim): the frame turns by aimDeg() around the figure position,
// after mirroring — the same order the game draws in.
function imgToGame(p, rot) {
  var k = imgScale() * pscale(), ox = (p[0] - C.origin[0]) * k * facing(), oy = (p[1] - C.origin[1]) * k;
  var a = (rot == null ? aimDeg() : rot) * Math.PI / 180;
  if (a) { var c = Math.cos(a), s = Math.sin(a), t = ox * c - oy * s; oy = ox * s + oy * c; ox = t; }
  return [S.figX + ox, S.figY + oy];
}
function gameToImg(w) {
  var k = imgScale() * pscale(), ox = w[0] - S.figX, oy = w[1] - S.figY, a = -aimDeg() * Math.PI / 180;
  if (a) { var c = Math.cos(a), s = Math.sin(a), t = ox * c - oy * s; oy = ox * s + oy * c; ox = t; }
  return [Math.round((ox / (k * facing()) + C.origin[0]) * 100) / 100, Math.round((oy / k + C.origin[1]) * 100) / 100];
}
// The fallback barrel: from -> to anchor averaged over the source action.
function aimRef() {
  if (!C || !S.aim.enabled || !C.actions[S.aim.source]) return null;
  var n = C.actions[S.aim.source].images.length, sx = 0, sy = 0, ax = 0, ay = 0, m = 0;
  for (var f = 0; f < n; f++) {
    var pa = resolveAnchor(S.aim.source, S.aim.from_anchor, f), pb = resolveAnchor(S.aim.source, S.aim.to_anchor, f);
    if (!pa || !pb) continue;
    var d = Math.hypot(pb[0] - pa[0], pb[1] - pa[1]); if (d < 1e-6) continue;
    sx += (pb[0] - pa[0]) / d; sy += (pb[1] - pa[1]) / d; ax += pa[0]; ay += pa[1]; m++;
  }
  if (!m) return null;
  var L = Math.hypot(sx, sy) || 1;
  return {dir: [sx / L, sy / L], from: [ax / m, ay / m]};
}
function aimDeg(action, fr) {
  var ref = aimRef(); if (!ref) return 0;
  action = action || S.action; fr = fr == null ? frameAt(S.t) : fr;
  return FXK.aimAngle(S.aim, resolveAnchor(action, S.aim.from_anchor, fr), resolveAnchor(action, S.aim.to_anchor, fr), ref,
    C.origin, imgScale() * pscale(), facing(), [S.figX, S.figY], S.target);
}
function jointAt(name, fr) {
  if (name === "figure") return [S.figX, S.figY];
  if (name === "target") return S.target.slice();
  var p = resolveAnchor(S.action, name, fr);
  return p ? imgToGame(p) : [S.figX, S.figY];
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
function drawFrame(gc, img, pos, fac, alpha, tint, rot) {
  var k = imgScale() * pscale();
  gc.save(); gc.translate(pos[0], pos[1]); if (rot) gc.rotate(rot * Math.PI / 180); gc.scale(fac * k, k);
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
  get lib() { return {entry_sets: S.entries, paths: S.paths}; },
  get showHitboxes() { return true; },
  get hurt() { return {x: S.target[0], y: S.target[1], r: Math.max(1, +$("hurtR").value || 16)}; },
  anchor: function (n) { return jointAt(n, frameAt(S.t)); },
  snapshot: function () { return {action: S.action, frame: frameAt(S.t), pos: [S.figX, S.figY], rot: aimDeg()}; },
  drawGhost: function (gc, gh, rgb, a) {
    var img = C.actions[gh.snap.action].images[gh.snap.frame];
    if (img) drawFrame(gc, img, gh.snap.pos, gh.facing, a, rgb, gh.snap.rot);
  },
  // Test enemy projectiles (the "test shots" toggle) for the auto-projectile tracker.
  get shots() { return S.shots || []; },
  onIntercept: function (inst, shot, mode, vel, hurtsOwner) {
    shot.dead = true;
    if (mode === "deflect") S.ricochets.push({x: shot.x, y: shot.y, vx: vel[0], vy: vel[1], age: 0, hurts: hurtsOwner, trail: []});
    S.bursts.push({x: shot.x, y: shot.y, age: 0, mode: mode});
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
    // The folder's FX file: the most recently saved one.  Browsers rename a
    // repeat download ("new_fighter.fxkit (1).json"), so the exact name can
    // be the OLDER copy; the same rule as laser/drops.py (newest wins).
    var fxFiles = list.filter(function (f) { return /\.fxkit[^/\\]*\.json$/i.test(f.name); })
      .sort(function (a, b) { return (b.lastModified || 0) - (a.lastModified || 0); });
    var fxF = fxFiles[0] || null;
    jobs.push(fxF ? readText(fxF).then(JSON.parse) : Promise.resolve(null));
    return Promise.all(jobs).then(function (res) {
      return {man: man, acts: acts, pack: res[res.length - 1],
        packFile: fxF ? {name: fxF.name, time: fxF.lastModified || 0, others: fxFiles.length - 1} : null};
    });
  }).then(function (r) { useCharacter(r.man, r.acts, r.pack, dirHandle, folder, r.packFile); })
    .catch(function (e) { toast("Could not open the folder: " + e.message, 6000); });
}
function useCharacter(man, acts, pack, dirHandle, folder, packFile) {
  var first = acts[Object.keys(acts)[0]].images[0];
  var name = man ? man.name : (pack && pack.character) || folder || "character";
  C = {man: man, name: name, display: man ? man.display_name || name : name, actions: acts,
    origin: man && man.image ? man.image.origin_px : [first.naturalWidth / 2, first.naturalHeight / 2],
    headPx: man && man.image ? +man.image.head_px : 58};
  // Game size: the character stands FXK.STAND_HEIGHT_PX tall (the roster's
  // height), measured on its first idle frame — the same rule the game uses.
  var standImg = (acts.idle || acts[Object.keys(acts)[0]]).images[0], sh = standImg ? FXK.standHeight(standImg) : 0;
  if (sh > 0) C.k = FXK.STAND_HEIGHT_PX / sh;
  S.dir = dirHandle || null;
  var pal = (man && man.palette) || {};
  lut = FXK.buildLut([FXK.hexRgb(pal.body, [242, 244, 246]), FXK.hexRgb(pal.accent, [63, 176, 234])]);   // palette.build_lut([body, accent])
  // Where the work comes from: this browser's saved Studio work or the
  // folder's FX file.  When both exist (or the browser has work and the
  // folder has none) you choose; the chosen source fills EVERYTHING
  // (effects, anchors, labels, action settings, entry sets, paths, aim,
  // scale) and nothing is carried over from the other.  The browser's copy
  // is only replaced by what opens once the choice is made.
  var local = lsGet(LS_PROJECT + name);
  var oldRule = TARGET_HEAD_PX / Math.max(1, C.headPx);
  function loadFrom(src, isLocal) {
    src = src || {};
    S.labels = clone(src.labels || src.anchor_labels || (man && man.anchor_labels) || {});
    S.anchors = clone(src.anchors || (man && man.anchors) || {});
    if (!Object.keys(S.labels).length) Object.keys(S.anchors[Object.keys(S.anchors)[0]] || {}).forEach(function (k) { S.labels[k] = k; });
    S.effects = (src.effects || []).map(function (e) { return FXK.normalize(clone(e)); });
    S.groups = clone(src.groups || []); pruneGroups();
    S.actionCfg = clone(src.action_settings || {});
    S.entries = (src.entry_sets || []).map(FXK.normalizeEntrySet); S.paths = (src.paths || []).map(FXK.normalizePath);
    S.aim = FXK.normalizeAim(clone(src.aim || {}));
    S.damaged = FXK.normalizeDamaged(clone(src.damaged || {}));
    S.retreat = FXK.normalizeRetreat(clone(src.retreat || {}));
    // The scale and frames this work was made against (older saves used the
    // head-size rule; another export of the same Rig Forge character can
    // have a different frame size / head px).
    if (isLocal) {
      S.srcScale = +src.scale || oldRule;
      S.srcHead = +src.img_head || C.headPx; S.srcOrigin = src.img_origin || C.origin;
    } else {
      var sp = src.space || {};
      S.srcScale = +sp.game_px_per_image_px || oldRule;
      S.srcHead = +sp.head_px || C.headPx; S.srcOrigin = sp.image_origin_px || C.origin;
    }
  }
  function when(t) { return t ? new Date(t).toLocaleString() : "unknown time"; }
  function fxCount(src) { return ((src && src.effects) || []).length; }
  function open(useLocal) {
    loadFrom(useLocal ? local : pack, useLocal);
    S.openedFrom = useLocal ? "your browser work" : pack ? packFile.name + " from the folder" : "the folder (no FX file)";
    finishOpen(man, acts, pack, name, useLocal ? local : null);
  }
  if (local) {
    var folderTxt = pack
      ? "The folder's file: " + packFile.name + " — " + fxCount(pack) + " FX, saved " + when(packFile.time) +
        (packFile.others > 0 ? " (newest of " + (packFile.others + 1) + " FX files in the folder)" : "") + "."
      : "The folder has no FX file (opening it starts with no FX).";
    ask("This browser has saved Studio work for " + name + ".\n\nMy browser work: " + fxCount(local) + " FX, last saved " + when(local.saved_at) +
      ".\n" + folderTxt + "\n\nWhich should open? (The one you don't pick is replaced in this browser.)",
      {ok: "My browser work", no: pack ? "The folder's file" : "The folder (no FX)"}, function (keep) { open(!!keep); });
    return;
  }
  open(false);
}
function finishOpen(man, acts, pack, name, local) {
  var names = Object.keys(acts);
  // Work authored at another scale keeps its look around the figure: every
  // distance is multiplied by the ratio (the game does the same on load).
  // Anchors from another export: convert into these frames' pixels (Rig
  // Forge renders every export around the same camera centre) — the same
  // rule as laser/fxkit.py CharacterFx.
  var f = C.headPx / Math.max(1e-6, S.srcHead || C.headPx), so = S.srcOrigin || C.origin;
  if (Math.abs(f - 1) > 1e-6 || so[0] !== C.origin[0] || so[1] !== C.origin[1]) {
    Object.keys(S.anchors).forEach(function (a) {
      Object.keys(S.anchors[a] || {}).forEach(function (j) {
        S.anchors[a][j] = (S.anchors[a][j] || []).map(function (p) { return p ? [(p[0] - so[0]) * f + C.origin[0], (p[1] - so[1]) * f + C.origin[1]] : null; });
      });
    });
  }
  // An action whose frames changed after this FX work was saved (Rig Forge
  // added or removed keyframes) takes the package's anchors for it; the
  // game applies the same rule (laser/fxkit.py CharacterFx).
  var fresh = [], pa = (man && man.anchors) || {};
  Object.keys(acts).forEach(function (a) {
    if (!pa[a]) return;
    var n = acts[a].images.length, mine = S.anchors[a];
    var changed = mine && Object.keys(mine).some(function (j) { return (mine[j] || []).length !== n; });
    if (!mine || !Object.keys(mine).length || changed) { S.anchors[a] = clone(pa[a]); if (changed) fresh.push(a); }
  });
  Object.keys((man && man.anchor_labels) || {}).forEach(function (j) { if (!S.labels[j]) S.labels[j] = man.anchor_labels[j]; });
  if (fresh.length) setTimeout(function () { toast("Frames changed in Rig Forge for " + fresh.join(", ") + ": their anchors were taken from the package. Check any FX on them.", 6000); }, 1800);
  var ratio = S.srcScale ? (imgScale() / S.srcScale) * f : 1;
  if (Math.abs(ratio - 1) > 1e-3) {
    FXK.rescaleEffects(S.effects, {entry_sets: S.entries, paths: S.paths}, ratio);
    S.groups.forEach(function (gr) { gr.offset = [(+gr.offset[0] || 0) * ratio, (+gr.offset[1] || 0) * ratio]; });
    setTimeout(function () { toast("Sized to game scale (stands " + FXK.STAND_HEIGHT_PX + " px): FX scaled ×" + ratio.toFixed(2) + " to keep their placement. Save FX to folder to keep it.", 6000); }, 1200);
  }
  S.action = (local && names.indexOf(local.action) >= 0) ? local.action : names.indexOf("attack_normal") >= 0 ? "attack_normal" : names[0];
  S.sel = null; S.selGroup = null; S.multi = []; S.selAnchor = null; S.geo = null; S.geoPlace = false; S.figX = 0; S.figY = 0;
  $("charname").textContent = C.display + "  (" + name + ")" + (man ? "" : "  — no character.json: timing 100 ms/frame, head 58 px");
  $("empty").style.display = "none";
  rebuild(); resetSim(0); persist(); histReset();
  toast("Opened " + C.display + ": " + names.length + " actions, " + S.effects.length + " FX" + (S.openedFrom ? " — from " + S.openedFrom : ""), 5000);
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
    entry_sets: S.entries.map(function (e) { return FXK.normalizeEntrySet(clone(e)); }),
    paths: S.paths.map(function (p) { return FXK.normalizePath(clone(p)); }),
    aim: FXK.normalizeAim(clone(S.aim)),
    damaged: FXK.normalizeDamaged(clone(S.damaged)),
    retreat: FXK.normalizeRetreat(clone(S.retreat)),
    effects: S.effects.map(function (e) { return FXK.normalize(clone(e)); }),
    groups: clone(S.groups),
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
  // Grouped: built-in groups in the order they first appear, then your own presets.
  var groups = [], by = {};
  allPresets().forEach(function (x, i) {
    var g = x.builtin ? (x.p.group || "Other") : "★ Your presets";
    if (!by[g]) { by[g] = document.createElement("optgroup"); by[g].label = g; groups.push(g); }
    var o = document.createElement("option"); o.value = i; o.textContent = (x.builtin ? "" : "★ ") + x.p.name; by[g].appendChild(o);
  });
  groups.forEach(function (g) { s.appendChild(by[g]); });
  showPresetDesc();
}
function showPresetDesc() { var x = allPresets()[+$("presetSel").value]; $("presetDesc").textContent = x ? (x.p.desc || (x.builtin ? "" : "Your preset")) : ""; }
function addPreset() {
  if (!C) return toast("Open a character folder first");
  var x = allPresets()[+$("presetSel").value]; if (!x) return;
  // A group preset comes in as a new group on this action, members still
  // laid out around its pivot exactly as they were saved.
  var gr = x.p.group ? newGroup(x.p.name, x.p.group.anchor || (x.p.effects[0] || {}).anchor || "figure", x.p.group.offset) : null;
  var added = x.p.effects.map(function (e) {
    var fx = clone(e); fx.id = FXK.newEffect(fx.prim).id; fx.action = S.action;
    if (gr) { fx.group = gr.id; fx.anchor = gr.anchor; } else delete fx.group;
    if (!fx.flip || !fx.flip.enabled) fx.flip = {enabled: false, facing: S.target[0] < S.figX - 0.001 ? -1 : 1};   // created with the target on this side
    if (fx.prim === "ghost" && !fx.layer) fx.layer = "behind";
    return FXK.normalize(fx);
  });
  S.effects = S.effects.concat(added); S.multi = [];
  if (gr) { S.groups.push(gr); S.sel = null; S.selGroup = gr.id; } else S.sel = added[0].id;
  rebuild(); resetSim(S.t); save();
  var missing = added.filter(function (fx) { return fx.anchor !== "figure" && fx.anchor !== "target" && !S.labels[fx.anchor]; });
  if (missing.length) toast("This character has no \"" + missing[0].anchor + "\" anchor: " + (gr ? "pick another Pivot for the group (its effects keep their layout)." : "add it under Anchors, or pick another joint."), 6000);
}
function savePreset() {
  var fx = selFx(); if (!fx) return;
  askText("Save this effect as a preset named:", fx.name, function (name) {
  var e = clone(fx); delete e.id; delete e.action; delete e.group;
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

// ------------------------------------------------------------ groups
// S.groups[i] = {id, name, action, anchor, offset}: effects with
// fx.group === id ride ONE pivot (the group's anchor) and keep their own
// offsets from it, so the group moves and re-attaches as a rigid unit.
// The saved effects still carry a plain anchor + offset each (the game
// never reads groups); gr.offset is how far the whole group was moved.
var _gid = 1;
function newGroup(name, anchor, offset) {
  var off = offset || [0, 0];
  return {id: "G" + Date.now().toString(36) + (_gid++), name: name, action: S.action, anchor: anchor, offset: [+off[0] || 0, +off[1] || 0]};
}
function groupById(id) { return S.groups.filter(function (gr) { return gr.id === id; })[0] || null; }
function groupMembers(gr) { return S.effects.filter(function (e) { return e.group === gr.id; }); }
function selGroup() { var gr = S.selGroup && groupById(S.selGroup); return gr && gr.action === S.action ? gr : null; }
// Drop groups with no members, and memberships of groups that are gone.
function pruneGroups() {
  S.groups = (S.groups || []).filter(function (gr) { return S.effects.some(function (e) { return e.group === gr.id; }); });
  S.effects.forEach(function (e) { if (e.group && !groupById(e.group)) delete e.group; });
  if (S.selGroup && !groupById(S.selGroup)) S.selGroup = null;
}
function canGroup(fx) { return fx.prim !== "weapon" && fx.anchor.indexOf("set:") !== 0; }
// Effect-local (x forward, y down) <-> world, the way its offset is applied.
function fxTurn(fx, v, inverse) {
  var deg = FXK.bodyDeg(fx, host) * (inverse ? -1 : 1), a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
  return deg ? [v[0] * c - v[1] * s, v[0] * s + v[1] * c] : v;
}
function worldToLocal(fx, d) { var q = fxTurn(fx, d, true); return [q[0] * FXK.fxFacing(fx, host), q[1]]; }
// Where the effect sits on the frame under the playhead (keyed offset included).
function fxSpot(fx) { return jointAtFx(FXK.fxAt(fx, frameAt(S.t))); }
// Shift an effect's offset (and every offset key) by d, in its local px.
function shiftOffset(fx, d) {
  var r = function (v) { return Math.round(v * 100) / 100; };
  fx.offset = [r((+fx.offset[0] || 0) + d[0]), r((+fx.offset[1] || 0) + d[1])];
  (fx.keys || []).forEach(function (k) {
    if ("offset.0" in k.set) k.set["offset.0"] = r(+k.set["offset.0"] + d[0]);
    if ("offset.1" in k.set) k.set["offset.1"] = r(+k.set["offset.1"] + d[1]);
  });
}
// Group the Ctrl+clicked effects: every member moves onto the first one's
// pivot, its spot on this frame turned into an offset from that pivot, so
// nothing jumps.  Flip / Follow direction follow the first member so the
// group mirrors and turns as one piece.
function makeGroup() {
  if (!C) return toast("Open a character folder first");
  var ids = S.multi.slice(); if (S.sel && ids.indexOf(S.sel) < 0) ids.unshift(S.sel);
  var picked = actionEffects().filter(function (e) { return ids.indexOf(e.id) >= 0; });
  picked.sort(function (a, b) { return ids.indexOf(a.id) - ids.indexOf(b.id); });
  var bad = picked.filter(function (e) { return !canGroup(e); });
  if (bad.length) return toast("\"" + bad[0].name + "\" can't be grouped: weapon hitboxes and entry-set (⊕) effects use their own anchors.", 6000);
  if (picked.length < 2) return toast("Ctrl+click two or more effects in the list, then press Group.");
  var lead = picked[0], pivot = lead.anchor, spots = picked.map(fxSpot);
  var gr = newGroup("Group " + (S.groups.filter(function (x) { return x.action === S.action; }).length + 1), pivot);
  picked.forEach(function (fx, i) {
    if (fx !== lead) { fx.flip = clone(lead.flip); fx.follow_dir = lead.follow_dir; }
    var now = FXK.fxAt(fx, frameAt(S.t)).offset;
    fx.anchor = pivot; fx.group = gr.id;
    var b = jointAt(pivot, frameAt(S.t)), want = worldToLocal(fx, [spots[i][0] - b[0], spots[i][1] - b[1]]);
    shiftOffset(fx, [want[0] - (+now[0] || 0), want[1] - (+now[1] || 0)]);
  });
  S.groups.push(gr); pruneGroups();
  S.multi = []; S.sel = null; S.selGroup = gr.id;
  rebuild(); resetSim(S.t); save();
  toast("Grouped " + picked.length + " effects on " + (S.labels[pivot] || pivot) + ".");
}
function moveGroup(gr, d) {
  if (!d[0] && !d[1]) return;
  groupMembers(gr).forEach(function (fx) { shiftOffset(fx, d); });
  gr.offset = [Math.round((gr.offset[0] + d[0]) * 100) / 100, Math.round((gr.offset[1] + d[1]) * 100) / 100];
}
// Re-attach: every member takes the new pivot and keeps its offset, so the
// layout is unchanged and the whole group now rides the new joint.
function attachGroup(gr, anchor) { gr.anchor = anchor; groupMembers(gr).forEach(function (fx) { fx.anchor = anchor; }); }
function ungroup(gr) {
  groupMembers(gr).forEach(function (fx) { delete fx.group; });
  S.groups = S.groups.filter(function (x) { return x !== gr; });
  if (S.selGroup === gr.id) S.selGroup = null;
  rebuild(); resetSim(S.t); save(); toast("Ungrouped " + gr.name + ": every effect stays where it is.");
}
// Flip / Follow direction changed on one member: the rest follow it.
function syncGroupTurn(fx) {
  var gr = fx.group && groupById(fx.group); if (!gr) return;
  groupMembers(gr).forEach(function (e) { if (e !== fx) { e.flip = clone(fx.flip); e.follow_dir = fx.follow_dir; } });
}
// The group's handle on the stage: the middle of its members on this frame.
function groupCentre(gr) {
  var ms = groupMembers(gr); if (!ms.length) return null;
  var sx = 0, sy = 0; ms.forEach(function (fx) { var p = fxSpot(fx); sx += p[0]; sy += p[1]; });
  return [sx / ms.length, sy / ms.length];
}
function saveGroupPreset(gr) {
  askText("Save this group as a preset named:", gr.name, function (name) {
    var ms = groupMembers(gr).map(function (fx) { var e = clone(fx); delete e.id; delete e.action; delete e.group; return e; });
    var mine = userPresets().filter(function (p) { return p.name !== name; });
    mine.push({name: name, desc: "Your group preset (" + ms.length + " effects on one pivot)", group: {name: gr.name, anchor: gr.anchor, offset: gr.offset.slice()}, effects: ms});
    if (!lsSet(LS_PRESETS, mine)) toast("Browser storage unavailable; use Export to keep presets.", 5000);
    buildPresets(); toast("Saved group preset " + name);
  });
}
function buildGroupProps(d, gr) {
  var ms = groupMembers(gr);
  banner(d, "fx", "Editing a group", "▣ " + gr.name, ms.length + " effects on the " + gr.action + " action, riding one pivot. Moving or re-attaching the group keeps every effect's place relative to the others.",
    ["Done", function () { S.selGroup = null; buildEffects(); buildProps(); draw(); }]);
  var s = sec(d, "Group", "group", "The pivot every member rides, and where the whole group sits on it.");
  field(s, "Name", inp("text", gr.name, function (v) { gr.name = v; buildEffects(); save(); }));
  field(s, "Pivot", inp([["figure", "figure (image centre)"], ["target", "target"]].concat(anchorOptions(false)), gr.anchor, function (v) {
    attachGroup(gr, v); changed(true); buildEffects();
  })).title = "The joint the whole group rides. Changing it moves the group onto the new joint; the effects keep their layout.";
  field(s, "Move X px", inp("n", gr.offset[0], function (v) { moveGroup(gr, [v - gr.offset[0], 0]); changed(); }, -500, 500, 0.5));
  field(s, "Move Y px", inp("n", gr.offset[1], function (v) { moveGroup(gr, [0, v - gr.offset[1]]); changed(); }, -500, 500, 0.5));
  note(s, "Or drag the ▣ handle on the stage (Shift+drag anywhere also moves the group). X is forward, mirrored when facing left.");
  s = sec(d, "Members", "groupmembers", "Click one to edit it; its own Offset moves it within the group.");
  ms.forEach(function (fx) {
    var r = document.createElement("div"); r.className = "row";
    var b = document.createElement("button"); b.textContent = fx.name + " · " + fx.prim; b.style.flex = "1";
    b.onclick = function () { S.sel = fx.id; S.selGroup = null; buildEffects(); buildProps(); buildTimeline(); };
    var x = document.createElement("button"); x.textContent = "Remove"; x.title = "Take it out of the group (it stays where it is)";
    x.onclick = function () { delete fx.group; pruneGroups(); rebuild(); resetSim(S.t); save(); };
    r.appendChild(b); r.appendChild(x); s.appendChild(r);
  });
  var r = document.createElement("div"); r.className = "row";
  var bp = document.createElement("button"); bp.textContent = "Save group as preset…"; bp.onclick = function () { saveGroupPreset(gr); };
  var bu = document.createElement("button"); bu.textContent = "Ungroup"; bu.onclick = function () { ungroup(gr); };
  r.appendChild(bp); r.appendChild(bu); d.appendChild(r);
}

// ------------------------------------------------------------ lists
function rebuild() { buildActions(); buildAnchors(); buildEffects(); buildGeo(); buildProps(); buildTimeline(); syncContinuous(); }
function syncContinuous() { var c = $("contFx"); if (c) c.checked = !!(C && S.action && cfgOf(S.action).fx_continuous); }
function buildActions() {
  var d = $("actions"); d.innerHTML = "";
  if (!C) return;
  Object.keys(C.actions).forEach(function (n) {
    var a = C.actions[n], c = S.effects.filter(function (e) { return e.action === n; }).length;
    var el = document.createElement("div"); el.className = n === S.action ? "sel" : "";
    el.innerHTML = '<span class="n"></span><span class="m"></span>';
    el.querySelector(".n").textContent = n;
    el.querySelector(".m").textContent = a.images.length + "f · " + Math.round(a.images.length * a.frame_ms) + "ms" + (c ? " · " + c + " fx" : "");
    el.onclick = function () { S.action = n; S.sel = null; S.geo = null; S.geoPlace = false; rebuild(); resetSim(0); save(); };
    d.appendChild(el);
  });
}
function buildAnchors() {
  var d = $("anchors"), top = d.scrollTop; d.innerHTML = "";
  if (!C) return;
  var keepSel = null;
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
    if (id === S.selAnchor) keepSel = el;
  });
  d.scrollTop = top;   // rebuilding keeps the list where it was scrolled
  if (keepSel && (keepSel.offsetTop < d.scrollTop || keepSel.offsetTop + keepSel.offsetHeight > d.scrollTop + d.clientHeight)) d.scrollTop = keepSel.offsetTop;
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
  var list = actionEffects(), shown = {}, sg = !S.sel && selGroup();
  S.multi = S.multi.filter(function (id) { return list.some(function (e) { return e.id === id; }); });
  // Ctrl+click picks several effects (for Group); a plain click selects one.
  function row(fx, member) {
    var el = document.createElement("div");
    el.className = (fx.id === S.sel ? "sel" : "") + (S.multi.indexOf(fx.id) >= 0 ? " multi" : "") + (member ? " gm" : "");
    el.innerHTML = '<input type="checkbox"><span class="n"></span><span class="m"></span><span class="ct"></span><span class="x" title="Duplicate">⧉</span><span class="x" title="Delete">✕</span>';
    var cb = el.querySelector("input"); cb.checked = fx.enabled; cb.title = "Enabled";
    cb.onclick = function (ev) { ev.stopPropagation(); fx.enabled = cb.checked; resetSim(S.t); save(); };
    // Continuous toggle: the effect keeps producing, never resetting.
    var ct = el.querySelector(".ct"), can = FXK.canContinue(fx);
    ct.textContent = "∞"; ct.className = "ct" + (fx.continuous && can ? " on" : "") + (can ? "" : " off");
    ct.title = can ? (fx.continuous ? "Continuous: ON — keeps producing without resetting (click to turn off)" : "Continuous: off — click so it keeps producing without resetting (e.g. an always-on laser trail)")
      : "Continuous is for effects that stay on the fighter (attached, static or orbit motion, not arcs)";
    ct.onclick = function (ev) {
      ev.stopPropagation();
      if (!can) return toast("Continuous needs attached, static or orbit motion (not arcs)");
      fx.continuous = !fx.continuous; buildEffects(); changed(true);
    };
    el.querySelector(".n").textContent = fx.name;
    el.querySelector(".m").textContent = (fx.battle.deals_damage ? "⚔ " + fx.battle.damage + " · " : "visual · ") + fx.prim;
    el.title = (fx.battle.deals_damage ? "Deals " + fx.battle.damage + " HP per hit" : "Visual only — never damages") + ". Ctrl+click to pick several for Group.";
    var xs = el.querySelectorAll(".x");
    xs[0].onclick = function (ev) { ev.stopPropagation(); var c = clone(fx); c.id = FXK.newEffect(c.prim).id; c.name += " copy"; S.effects.push(c); S.sel = c.id; rebuild(); resetSim(S.t); save(); };
    xs[1].onclick = function (ev) { ev.stopPropagation(); S.effects = S.effects.filter(function (e) { return e !== fx; }); if (S.sel === fx.id) S.sel = null; pruneGroups(); rebuild(); resetSim(S.t); save(); };
    el.onclick = function (ev) {
      if (ev.ctrlKey || ev.metaKey) {
        if (S.sel && S.multi.indexOf(S.sel) < 0 && S.sel !== fx.id) S.multi.push(S.sel);
        var i = S.multi.indexOf(fx.id); if (i >= 0) S.multi.splice(i, 1); else S.multi.push(fx.id);
        buildEffects(); return;
      }
      S.multi = []; S.sel = fx.id; S.selGroup = null; S.geo = null; S.geoPlace = false; buildEffects(); buildGeo(); buildProps(); buildTimeline();
    };
    d.appendChild(el);
  }
  list.forEach(function (fx) {
    if (shown[fx.id]) return;
    var gr = fx.group && groupById(fx.group);
    if (!gr) { row(fx, false); return; }
    var ms = list.filter(function (e) { return e.group === gr.id; });
    var h = document.createElement("div"); h.className = "grp" + (sg === gr ? " sel" : "");
    h.innerHTML = '<span class="tw"></span><span class="n"></span><span class="m"></span><span class="x" title="Ungroup (every effect stays where it is)">⊟</span>';
    h.querySelector(".tw").textContent = gr.collapsed ? "▸" : "▾";
    h.querySelector(".tw").onclick = function (ev) { ev.stopPropagation(); gr.collapsed = !gr.collapsed; buildEffects(); save(); };
    h.querySelector(".n").textContent = "▣ " + gr.name;
    h.querySelector(".m").textContent = ms.length + " fx · " + (S.labels[gr.anchor] || gr.anchor);
    h.title = "Group: click to move it, re-attach it to another pivot or save it as a preset.";
    h.querySelector(".x").onclick = function (ev) { ev.stopPropagation(); ungroup(gr); };
    h.onclick = function () { S.sel = null; S.multi = []; S.selGroup = gr.id; S.geo = null; S.geoPlace = false; buildEffects(); buildGeo(); buildProps(); buildTimeline(); };
    d.appendChild(h);
    ms.forEach(function (e) { shown[e.id] = 1; if (!gr.collapsed) row(e, true); });
  });
  var bg = $("bGroup");
  if (bg) { var n = S.multi.length + (S.sel && S.multi.length && S.multi.indexOf(S.sel) < 0 ? 1 : 0); bg.textContent = n > 1 ? "Group " + n + " selected" : "Group"; bg.disabled = n < 2; }
}

// ------------------------------------------------------------ paths & entry points
// The character's shared library (every action can use it):
//   entry sets: groups of points around the fighter that effects come out
//     of, all at once or one after another (effect Anchor = ⊕ set);
//   paths: routes an effect travels along (effect Motion = path).
// Points are game px, x forward.  Placed by clicking the stage.
var GEO_PRESETS = [
  {kind: "set", desc: "Three points in an arc above the head, firing together.",
    item: {name: "Halo of 3", base: "figure", mode: "simultaneous", interval_ticks: 6, points: [[-16, -44], [0, -50], [16, -44]]}},
  {kind: "set", desc: "Three points behind the back, firing one after another.",
    item: {name: "Back row of 3", base: "figure", mode: "sequential", interval_ticks: 6, points: [[-22, -36], [-30, -18], [-22, 0]]}},
  {kind: "set", desc: "One point each side of the body, firing together.",
    item: {name: "Both sides", base: "figure", mode: "simultaneous", interval_ticks: 6, points: [[-26, -20], [26, -20]]}},
  {kind: "set", desc: "Six points in a ring around the fighter, firing in turn.",
    item: {name: "Ring of 6", base: "figure", mode: "sequential", interval_ticks: 4,
      points: [0, 1, 2, 3, 4, 5].map(function (i) { var a = i * Math.PI / 3 - Math.PI / 2; return [Math.round(Math.cos(a) * 34), Math.round(Math.sin(a) * 34 - 16)]; })}},
  {kind: "set", desc: "A column of four points in front of the body, firing top to bottom.",
    item: {name: "Front column of 4", base: "figure", mode: "sequential", interval_ticks: 5, points: [[16, -42], [18, -28], [18, -14], [16, 0]]}},
  {kind: "path", desc: "Straight ahead, turned toward the aim, and keeps going.",
    item: {name: "Straight", points: [[0, 0], [120, 0]], smooth: false, ticks: 20, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "Lobs up and over toward the aim, then keeps going.",
    item: {name: "Arc over", points: [[0, 0], [50, -40], [100, 0]], smooth: true, ticks: 24, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "Dips under toward the aim, then keeps going.",
    item: {name: "Arc under", points: [[0, 0], [50, 40], [100, 0]], smooth: true, ticks: 24, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "Weaves once each way on its way to the aim.",
    item: {name: "S-curve", points: [[0, 0], [30, -25], [60, 0], [90, 25], [120, 0]], smooth: true, ticks: 28, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "A tight wave toward the aim.",
    item: {name: "Sine wave", points: [0, 1, 2, 3, 4, 5, 6, 7, 8].map(function (i) { return [i * 20, i % 2 ? (i % 4 === 1 ? -14 : 14) : 0]; }), smooth: true, ticks: 36, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "A loop-the-loop, then on toward the aim.",
    item: {name: "Loop", points: [[0, 0], [40, 0], [62, -20], [40, -42], [18, -20], [40, 0], [110, 0]], smooth: true, ticks: 36, orient: "aim", end: "continue", follow: false}},
  {kind: "path", desc: "Out and back to the fighter, like a boomerang.",
    item: {name: "Boomerang", points: [[0, 0], [60, -18], [100, 0], [60, 18], [0, 0]], smooth: true, ticks: 40, orient: "aim", end: "stop", follow: true}},
  {kind: "path", desc: "Rises straight up above the fighter.",
    item: {name: "Rise up", points: [[0, 0], [0, -80]], smooth: false, ticks: 30, orient: "facing", end: "stop", follow: false}},
  {kind: "path", desc: "Spirals outward from where it starts.",
    item: {name: "Spiral out", points: (function () { var o = []; for (var i = 0; i <= 16; i++) { var a = i * Math.PI / 4, r = 3 + i * 3; o.push([Math.round(Math.cos(a) * r - 3), Math.round(Math.sin(a) * r)]); } o[0] = [0, 0]; return o; })(),
      smooth: true, ticks: 48, orient: "facing", end: "stop", follow: false}},
  {kind: "path", desc: "Circles the fighter again and again (use with ∞ Continuous).",
    item: {name: "Circle around", points: (function () { var o = []; for (var i = 0; i <= 12; i++) { var a = i * Math.PI / 6; o.push([Math.round(30 - Math.cos(a) * 30), Math.round(-Math.sin(a) * 30)]); } o[0] = [0, 0]; return o; })(),
      smooth: true, ticks: 60, orient: "facing", end: "loop", follow: true}}
];
function geoUserPresets() { return lsGet(LS_GEO) || []; }
function geoAllPresets() { return GEO_PRESETS.map(function (p) { return {p: p, builtin: true}; }).concat(geoUserPresets().map(function (p) { return {p: p, builtin: false}; })); }
function geoItem() {
  if (!S.geo) return null;
  var l = S.geo.kind === "set" ? S.entries : S.paths;
  return l.filter(function (x) { return x.id === S.geo.id; })[0] || null;
}
function geoUsers(kind, id) {
  return S.effects.filter(function (e) { return kind === "set" ? e.anchor === "set:" + id : e.motion.kind === "path" && e.motion.path === id; });
}
function geoSelect(kind, id) {
  S.geo = id ? {kind: kind, id: id} : null; S.geoPlace = false;
  if (S.geo) S.sel = null;
  buildEffects(); buildGeo(); buildProps(); buildTimeline();
}
function geoNew(kind, item) {
  var id = (kind === "set" ? "P" : "T") + Date.now().toString(36) + Math.floor(Math.random() * 1e4).toString(36);
  var o = clone(item); o.id = id;
  if (kind === "set") S.entries.push(FXK.normalizeEntrySet(o)); else S.paths.push(FXK.normalizePath(o));
  geoSelect(kind, id); resetSim(S.t); save();
  return id;
}
function buildGeo() {
  [["set", "entryList", S.entries], ["path", "pathList", S.paths]].forEach(function (g3) {
    var d = $(g3[1]); if (!d) return; d.innerHTML = "";
    g3[2].forEach(function (it) {
      var el = document.createElement("div"); el.className = S.geo && S.geo.kind === g3[0] && S.geo.id === it.id ? "sel" : "";
      el.innerHTML = '<span class="n"></span><span class="m"></span><span class="x" title="Duplicate">⧉</span><span class="x" title="Delete">✕</span>';
      el.querySelector(".n").textContent = (g3[0] === "set" ? "⊕ " : "↝ ") + it.name;
      var used = geoUsers(g3[0], it.id).length;
      el.querySelector(".m").textContent = (g3[0] === "set" ? it.points.length + " pts · " + (it.mode === "sequential" ? "seq" : "sim") : (it.points.length - 1) + " seg · " + it.ticks + "t") + (used ? " · " + used + " fx" : "");
      var xs = el.querySelectorAll(".x");
      xs[0].onclick = function (ev) { ev.stopPropagation(); var c = clone(it); c.name += " copy"; delete c.id; geoNew(g3[0], c); };
      xs[1].onclick = function (ev) {
        ev.stopPropagation();
        var users = geoUsers(g3[0], it.id);
        ask("Delete \"" + it.name + "\"?" + (users.length ? " " + users.length + " effect(s) use it and will " + (g3[0] === "set" ? "play from the figure instead." : "stop following a path (motion becomes static).") : ""), {ok: "Delete"}, function (ok) {
          if (!ok) return;
          users.forEach(function (e) { if (g3[0] === "set") e.anchor = "figure"; else { e.motion.kind = "static"; e.motion.path = ""; } });
          if (g3[0] === "set") S.entries = S.entries.filter(function (x) { return x !== it; }); else S.paths = S.paths.filter(function (x) { return x !== it; });
          if (S.geo && S.geo.id === it.id) { S.geo = null; S.geoPlace = false; }
          rebuild(); resetSim(S.t); save();
        });
      };
      el.onclick = function () { geoSelect(g3[0], S.geo && S.geo.id === it.id ? null : it.id); };
      d.appendChild(el);
    });
    if (!g3[2].length) { var e0 = document.createElement("div"); e0.className = "note empty"; e0.textContent = g3[0] === "set" ? "No entry sets yet." : "No paths yet."; d.appendChild(e0); }
  });
  var sel = $("geoPreset");
  if (sel && !sel.dataset.built) {
    sel.dataset.built = "1";
    var html = "", all = geoAllPresets();
    [["set", true, "Entry-set presets"], ["path", true, "Path presets"], ["set", false, "My entry sets"], ["path", false, "My paths"]].forEach(function (grp) {
      var opts = all.map(function (x, i) { return [x, i]; }).filter(function (q) { return q[0].p.kind === grp[0] && q[0].builtin === grp[1]; });
      if (!opts.length) return;
      html += '<optgroup label="' + grp[2] + '">' + opts.map(function (q) { return '<option value="' + q[1] + '"></option>'; }).join("") + "</optgroup>";
    });
    sel.innerHTML = html;
    Array.prototype.forEach.call(sel.options, function (o) { var x = all[+o.value]; o.textContent = (x.p.kind === "set" ? "⊕ " : "↝ ") + x.p.item.name; });
    geoPresetDesc();
  }
  geoTools();
}
function geoPresetDesc() { var x = geoAllPresets()[+$("geoPreset").value]; $("geoPresetDesc").textContent = x ? (x.p.desc || "Your preset") : ""; $("bGeoPresetDel").disabled = !x || x.builtin; }
function geoRefreshPresets() { $("geoPreset").dataset.built = ""; buildGeo(); }
function geoTools() {
  var it = geoItem(), b = $("bGeoPlace");
  if (!b) return;
  b.disabled = !it;
  b.className = S.geoPlace && it ? "on" : "";
  b.textContent = !it ? "Place points" : S.geoPlace ? "Placing… click the stage" : (S.geo.kind === "set" ? "Place entry points" : "Draw path points");
}
// Where a path is previewed from: the selected effect's spawn point when it
// uses this path, otherwise the figure.
function pathPreviewOrigin(path) {
  var fx = selFx();
  if (fx && fx.motion.kind === "path" && fx.motion.path === path.id) return jointAtFx(fx);
  var users = geoUsers("path", path.id).filter(function (e) { return e.action === S.action; });
  return users.length ? jointAtFx(users[0]) : [S.figX, S.figY];
}
function jointAtFx(fx) {
  var set = S.entries.filter(function (e) { return "set:" + e.id === fx.anchor; })[0], deg = FXK.bodyDeg(fx, host), ef = FXK.fxFacing(fx, host);
  var turn = function (v) { var a = deg * Math.PI / 180, c = Math.cos(a), s = Math.sin(a); return deg ? [v[0] * c - v[1] * s, v[0] * s + v[1] * c] : v; };
  var b = set && set.points.length ? (function () { var bb = jointAt(set.base, frameAt(S.t)), q = turn([set.points[0][0] * ef, set.points[0][1]]); return [bb[0] + q[0], bb[1] + q[1]]; })()
    : jointAt(fx.anchor.indexOf("set:") === 0 ? "figure" : fx.anchor, frameAt(S.t));
  var o = turn([(+fx.offset[0] || 0) * ef, +fx.offset[1] || 0]);
  return [b[0] + o[0], b[1] + o[1]];
}
function geoPlaceAt(w) {
  var it = geoItem(); if (!it) return;
  var f = facing(), b = S.geo.kind === "set" ? jointAt(it.base, frameAt(S.t)) : pathPreviewOrigin(it);
  var q = [Math.round((w[0] - b[0]) * f * 2) / 2, Math.round((w[1] - b[1]) * 2) / 2];
  it.points.push(q);
  buildGeo(); buildProps(); resetSim(S.t); save();
}
function buildGeoProps(d) {
  var it = geoItem(), isSet = S.geo.kind === "set", users = geoUsers(S.geo.kind, it.id);
  banner(d, "geo", isSet ? "Editing entry points" : "Editing a path", (isSet ? "⊕ " : "↝ ") + it.name,
    (isSet ? "Effects whose Anchor is this set come out of these points." : "Effects whose Motion is \"path\" with this path travel along it.") + " Shared by every action. Used by " + (users.length ? users.map(function (e) { return e.name + " (" + e.action + ")"; }).join(", ") : "no effects yet") + ".",
    ["Done", function () { geoSelect(null); }]);
  var s = sec(d, isSet ? "Entry set" : "Path", "g-main", isSet ? "Its name, what the points are measured from and how they fire." : "Its name, how long it takes and how it's turned.", "geo");
  field(s, "Name", inp("text", it.name, function (v) { it.name = v; buildGeo(); save(); }));
  if (isSet) {
    field(s, "Measured from", inp([["figure", "figure (image centre)"]].concat(anchorOptions(false)), it.base, function (v) { it.base = v; changed(true); })).title =
      "The points sit around this spot and move with it (pick an anchor to have them follow a hand, the head…).";
    field(s, "Firing", inp([["simultaneous", "Simultaneous (all at once)"], ["sequential", "Sequential (one after another)"]], it.mode, function (v) { it.mode = v; buildGeo(); changed(true); }));
    if (it.mode === "sequential") field(s, "Ticks between points", inp("n", it.interval_ticks, function (v) { it.interval_ticks = Math.max(0, Math.round(v)); changed(); }, 0, 600, 1)).title =
      "Point 1 fires when the effect fires, point 2 this many ticks later, and so on (16 ms per tick).";
  } else {
    field(s, "Ticks start → end", inp("n", it.ticks, function (v) { it.ticks = Math.max(1, Math.round(v)); buildGeo(); changed(); }, 1, 2000, 1)).title = "How long it takes to travel the whole path (16 ms per tick).";
    field(s, "Smooth curve", inp("chk", it.smooth, function (v) { it.smooth = v; changed(); })).title = "On: a smooth curve through the points. Off: straight lines between them.";
    field(s, "Turned", inp([["facing", "mirrored with the facing"], ["aim", "toward the aim"]], it.orient, function (v) { it.orient = v; changed(); })).title =
      "Mirrored: drawn to the right, flipped when facing left. Toward the aim: also turned so its start→end line points where the effect aims (set Aim in the effect's Motion).";
    field(s, "At the end", inp([["stop", "stop there"], ["loop", "start over"], ["continue", "carry on straight"]], it.end, function (v) { it.end = v; changed(); }));
    field(s, "Rides with the fighter", inp("chk", it.follow, function (v) { it.follow = v; changed(); })).title =
      "On: the whole path moves with the fighter (orbits, boomerangs). Off: it stays where it started.";
  }
  s = sec(d, "Points", "g-points", isSet ? "Click \"Place entry points\" (left) then click the stage around the figure to add points. X is forward, Y is down, in game px." :
    "Point 0 is where the effect starts. Click \"Draw path points\" (left) then click the stage to add the next points. X is forward, Y is down.", "geo");
  it.points.forEach(function (p, i) {
    var row = document.createElement("div"); row.className = "f pt";
    var l = document.createElement("label"); l.textContent = (isSet ? "#" + (i + 1) : "Point " + i) + (isSet && it.mode === "sequential" ? "  +" + i * it.interval_ticks + "t" : ""); row.appendChild(l);
    var bx = document.createElement("span"); bx.className = "xy";
    var ix = inp("n", p[0], function (v) { p[0] = v; changed(); }, -2000, 2000, 0.5), iy = inp("n", p[1], function (v) { p[1] = v; changed(); }, -2000, 2000, 0.5);
    ix.title = "X (forward)"; iy.title = "Y (down)";
    if (!isSet && i === 0) { ix.disabled = iy.disabled = true; }
    bx.appendChild(ix); bx.appendChild(iy);
    if (isSet || i > 0) { var del = document.createElement("button"); del.textContent = "✕"; del.title = "Remove this point"; del.onclick = function () { it.points.splice(i, 1); buildGeo(); changed(true); }; bx.appendChild(del); }
    row.appendChild(bx); s.appendChild(row);
  });
  if (!it.points.length || (!isSet && it.points.length < 2)) note(s, isSet ? "No points yet: effects using this set play from the figure until you add some." : "Add at least one more point so it has somewhere to go.");
  var r = document.createElement("div"); r.className = "row";
  var bp = document.createElement("button"); bp.textContent = S.geoPlace ? "Stop placing" : isSet ? "Place entry points" : "Draw path points"; bp.className = S.geoPlace ? "on" : "";
  bp.onclick = function () { S.geoPlace = !S.geoPlace; geoTools(); buildProps(); }; r.appendChild(bp);
  var bc = document.createElement("button"); bc.textContent = "Clear points";
  bc.onclick = function () { it.points = isSet ? [] : [[0, 0]]; buildGeo(); changed(true); }; r.appendChild(bc);
  var bs = document.createElement("button"); bs.textContent = "Save as preset";
  bs.onclick = function () {
    askText("Preset name", it.name, function (nm) {
      var item = clone(it); delete item.id; item.name = nm;
      var mine = geoUserPresets(); mine.push({kind: S.geo.kind, desc: "Your " + (isSet ? "entry set" : "path"), item: item});
      if (!lsSet(LS_GEO, mine)) return toast("Could not save the preset (browser storage unavailable)");
      geoRefreshPresets(); toast("Saved preset \"" + nm + "\"");
    });
  };
  r.appendChild(bs); s.appendChild(r);
}
// Stage overlay: the selected entry set's points (numbered in firing order)
// or the selected path, drawn from where it would start.
function drawGeo(g, z) {
  var it = geoItem(), fx = selFx(), f = fx && !(S.geoPlace && it) ? FXK.fxFacing(fx, host) : facing();
  var sets = it && S.geo.kind === "set" ? [it] : fx ? S.entries.filter(function (e) { return "set:" + e.id === fx.anchor; }) : [];
  var paths = it && S.geo.kind === "path" ? [it] : fx && fx.motion.kind === "path" ? S.paths.filter(function (p) { return p.id === fx.motion.path; }) : [];
  var col = isLight() ? "rgba(20,130,70," : "rgba(125,224,168,";
  g.save(); g.font = (9 / z * 1.2) + "px sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  sets.forEach(function (set) {
    var b = jointAt(set.base, frameAt(S.t));
    g.strokeStyle = col + ".5)"; g.lineWidth = 1 / z; g.setLineDash([2 / z, 2 / z]);
    g.beginPath(); g.moveTo(b[0] - 3 / z, b[1]); g.lineTo(b[0] + 3 / z, b[1]); g.moveTo(b[0], b[1] - 3 / z); g.lineTo(b[0], b[1] + 3 / z); g.stroke();
    set.points.forEach(function (p, i) {
      var q = [b[0] + p[0] * f, b[1] + p[1]];
      g.beginPath(); g.moveTo(b[0], b[1]); g.lineTo(q[0], q[1]); g.stroke();
    });
    g.setLineDash([]);
    set.points.forEach(function (p, i) {
      var q = [b[0] + p[0] * f, b[1] + p[1]], r = 6 / z;
      g.fillStyle = col + ".9)"; g.beginPath(); g.arc(q[0], q[1], r, 0, 6.2832); g.fill();
      g.fillStyle = isLight() ? "#fff" : "#061018"; g.fillText(String(i + 1), q[0], q[1] + 0.5 / z);
    });
  });
  paths.forEach(function (path) {
    // Turned toward the target the way it plays (aim "target"); while you
    // draw its points it shows unturned so clicks land where you click.
    var o = pathPreviewOrigin(path), pl = FXK.pathLine(path), M = [f, 0, 0, 1];
    if (path.orient === "aim" && !(S.geoPlace && it === path)) {
      var dx = S.target[0] - o[0], dy = S.target[1] - o[1], dm = Math.hypot(dx, dy) || 1;
      M = FXK.pathMatrix(path, {facing: f}, [dx / dm, dy / dm]);
    } else if (!(S.geoPlace && it === path)) {   // a Follow-direction user turns it with the body
      var sf = selFx(), pfx = sf && sf.motion.kind === "path" && sf.motion.path === path.id ? sf
        : geoUsers("path", path.id).filter(function (e) { return e.action === S.action; })[0];
      if (pfx) { var pf = FXK.fxFacing(pfx, host); M = FXK.pathMatrix(path, {facing: pf}, [pf, 0], FXK.bodyDeg(pfx, host)); }
    }
    var W = function (p) { return [o[0] + M[0] * p[0] + M[1] * p[1], o[1] + M[2] * p[0] + M[3] * p[1]]; };
    g.strokeStyle = col + ".85)"; g.lineWidth = 1.5 / z; g.setLineDash([4 / z, 3 / z]); g.beginPath();
    pl.pts.forEach(function (p, i) { var q = W(p); if (i) g.lineTo(q[0], q[1]); else g.moveTo(q[0], q[1]); });
    g.stroke(); g.setLineDash([]);
    if (pl.len > 0) {   // arrow at the end
      var e = FXK.pathAt(pl, 1), ep = W(e[0]), ed = [M[0] * e[1][0] + M[1] * e[1][1], M[2] * e[1][0] + M[3] * e[1][1]], L = 6 / z;
      g.fillStyle = col + ".95)"; g.beginPath(); g.moveTo(ep[0] + ed[0] * L, ep[1] + ed[1] * L);
      g.lineTo(ep[0] - ed[1] * L * 0.6, ep[1] + ed[0] * L * 0.6); g.lineTo(ep[0] + ed[1] * L * 0.6, ep[1] - ed[0] * L * 0.6); g.fill();
    }
    path.points.forEach(function (p, i) {
      var q = W(p);
      g.fillStyle = i ? col + ".9)" : (isLight() ? "rgba(0,0,0,.8)" : "rgba(255,255,255,.9)");
      g.beginPath(); g.arc(q[0], q[1], (i ? 2.5 : 3) / z, 0, 6.2832); g.fill();
    });
  });
  g.restore();
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
    ["jitter", "Jitter px", 0, 30, 0.5], ["detach_ticks", "Detach tick (0=never)", 0, 2000, 1], ["grow_ticks", "Grow ticks (held)", 0, 600, 1],
    ["tip_fade", "Tip fade (fraction)", 0, 1, 0.05]],
  sprite: [["shape", "Shape", ["orb", "bolt"]], ["radius", "Radius", 0.5, 60, 0.5], ["stretch", "Bolt stretch", 1, 8, 0.1],
    ["hot", "White-hot streak", "chk"], ["halo", "Pulsing halo", "chk"], ["fade", "Fade over life", "chk"], ["trail_len", "Trail points", 0, 60, 1],
    ["glow", "Glow %", 0, 200, 5], ["glow_size", "Glow size %", 0, 300, 5]],
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
var MOTION_KEYS = {attached: [], static: [], path: ["aim", "angle_deg", "aim_offset_deg"], travel: ["aim", "angle_deg", "aim_offset_deg", "speed"],
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
// A collapsible settings section.  `key` names it for the remembered
// open/closed state, `desc` says in one line what the section controls, and
// `scope` colours it: "fx" = this one effect, "act" = the whole action.
function sec(parent, title, key, desc, scope) {
  var s = document.createElement("details"); s.className = "sec " + (scope || "fx"); s.open = true;
  var lk = "pbfxstudio.v1.psec." + (key || title);
  if (lsGet(lk) === false) s.open = false;
  s.addEventListener("toggle", function () { lsSet(lk, s.open); });
  var sm = document.createElement("summary"), b = document.createElement("b"); b.textContent = title; sm.appendChild(b); s.appendChild(sm);
  if (desc) { var p = document.createElement("div"); p.className = "desc"; p.textContent = desc; s.appendChild(p); }
  parent.appendChild(s); return s;
}
// Top-of-panel banner: which thing the settings below belong to.
function banner(d, scope, label, name, sub, action) {
  var b = document.createElement("div"); b.className = "banner " + scope;
  var t = document.createElement("div"); t.className = "bk"; t.textContent = label; b.appendChild(t);
  var n = document.createElement("div"); n.className = "bn"; n.textContent = name; b.appendChild(n);
  if (sub) { var u = document.createElement("div"); u.className = "bs"; u.textContent = sub; b.appendChild(u); }
  if (action) { var a = document.createElement("button"); a.textContent = action[0]; a.onclick = action[1]; b.appendChild(a); }
  d.appendChild(b);
}
function note(parent, text) { var n = document.createElement("div"); n.className = "note"; n.textContent = text; parent.appendChild(n); }
function changed(rebuildProps) { syncKeyView(); resetSim(S.t); buildTimeline(); save(); if (rebuildProps) buildProps(); }
function anchorOptions(withSpecial) {
  var o = anchorIds().map(function (j) { return [j, S.labels[j] + (S.labels[j] !== j ? " (" + j + ")" : "")]; });
  if (!withSpecial) return o;
  var sets = S.entries.map(function (e) { return ["set:" + e.id, "⊕ " + e.name + " (" + e.points.length + " pts, " + e.mode + ")"]; });
  return [["figure", "figure (image centre)"], ["target", "target"]].concat(o, sets);
}

// ------------------------------------------------------------ effect keyframes
// fx.keys (FXK.fxAt): each key sets new values for some number / colour
// settings at a frame; they move there from the previous point along the
// key's ease.  Once an effect has keys, the panel edits the frame under the
// playhead: it shows the effect as it is at that frame, and the numbers /
// colours you change go into the key on that frame (one is added there if
// there isn't one yet).  Anything else (a choice, a toggle) changes the whole
// effect.  At or before the effect's start frame (with no key there) the
// panel edits the effect's own settings: the start of the animation.
var EASE_LABEL = {linear: "Linear", "in": "Ease in", out: "Ease out", inout: "Ease in-out", strong_in: "Strong in",
  strong_out: "Strong out", strong_inout: "Strong in-out", hold: "Hold (jump)", bounce: "Bounce", elastic: "Elastic"};
var KV = null;   // {fx (authored), key (maybe pending = not added yet), frame, view (what the panel edits), before}
var PROPS_FRAME = -1;   // playhead frame the effect panel was built for (rebuilt when it moves)
function keyAt(fx, f) { return (fx.keys || []).filter(function (k) { return k.frame === f; })[0] || null; }
// The object the effect panel edits: the effect itself, or its view at the playhead frame.
function keyViewFor(fx) {
  KV = null;
  if (!fx.keys || !fx.keys.length) return fx;
  var f = frameAt(S.t), key = keyAt(fx, f);
  if (!key && f <= Math.max(0, fx.start_frame)) return fx;
  if (!key) key = {frame: f, ease: "inout", set: {}, pending: true};
  var view = clone(FXK.fxAt(fx, f));
  FXK.keyPaths(view).forEach(function (p) {   // in-between values: shown rounded
    var v = FXK.getPath(view, p);
    if (typeof v !== "number" || Math.round(v * 1000) === v * 1000) return;
    var i = p.indexOf("."), r = Math.round(v * 1000) / 1000;
    if (i < 0) view[p] = r; else if (p.slice(0, i) === "offset") view.offset[+p.slice(i + 1)] = r; else view[p.slice(0, i)][p.slice(i + 1)] = r;
  });
  KV = {fx: fx, key: key, frame: f, view: view, before: clone(view)};
  return view;
}
// Copy the panel's edits back: keyable values into the playhead frame's key
// (adding it on the first change), the rest into the effect.
function syncKeyView() {
  if (!KV) return;
  var fx = KV.fx, v = KV.view, b = KV.before, paths = FXK.keyPaths(v), keyed = false;
  paths.forEach(function (p) {
    var nv = FXK.getPath(v, p), ov = FXK.getPath(b, p);
    if (nv !== ov) { KV.key.set[p] = nv; keyed = true; }
  });
  if (keyed && KV.key.pending) {
    delete KV.key.pending;
    fx.keys.push(KV.key); fx.keys.sort(function (x, y) { return x.frame - y.frame; });
    toast("Added a key at frame " + KV.key.frame);
    var bk = document.querySelector("#props .banner .bk"); if (bk) bk.textContent = "Editing keyframe at frame " + KV.key.frame;
    // Show it in the key list once you leave the field (rebuilding now would steal the focus).
    $("props").addEventListener("focusout", function () { setTimeout(buildProps, 0); }, {once: true});
  }
  Object.keys(v).forEach(function (k) {
    if (k === "keys" || k === "id") return;
    if (["params", "motion", "emit", "color", "battle", "intercept", "flip"].indexOf(k) >= 0) {
      Object.keys(v[k] || {}).forEach(function (q) {
        if (paths.indexOf(k + "." + q) >= 0) return;
        if (JSON.stringify(v[k][q]) !== JSON.stringify((b[k] || {})[q])) fx[k][q] = clone(v[k][q]);
      });
    } else if (k !== "offset" && k !== "life_ticks" && JSON.stringify(v[k]) !== JSON.stringify(b[k])) fx[k] = clone(v[k]);
  });
  KV.before = clone(v);
  var ls = $("kvChips"); if (ls && !KV.key.pending) fillKeyChips(ls, KV.key, true);
  if (keyed) buildTimeline();   // the new / changed diamond
}
function keyLabel(p) {
  var i = p.indexOf("."), g = i < 0 ? "" : p.slice(0, i), k = i < 0 ? p : p.slice(i + 1);
  if (g === "offset") return k === "0" ? "offset x" : "offset y";
  return (g && g !== "params" ? g + " " : "") + k.replace(/_/g, " ");
}
function keyValText(v) { return typeof v === "number" ? String(Math.round(v * 100) / 100) : String(v); }
// Select fx and put the playhead on frame f (its key there is then the one edited).
function editKey(fx, f) {
  S.sel = fx.id; S.geo = null;
  gotoFrame(f == null ? Math.max(0, fx.start_frame) : f);
  buildEffects(); buildProps(); buildTimeline();
}
// The values a key sets, as removable chips (the key being edited: id kvChips, refreshed as you type).
function keyChips(fx, k, on) {
  var ls = document.createElement("div"); ls.className = "keyset"; if (on) ls.id = "kvChips";
  fillKeyChips(ls, k, on);
  return ls;
}
function fillKeyChips(ls, k, on) {
  ls.innerHTML = "";
  var set = Object.keys(k.set);
  if (!set.length) ls.textContent = on ? "Nothing keyed yet: change any number or colour below." : "(sets nothing yet)";
  set.forEach(function (p) {
    var chip = document.createElement("span"); chip.className = "kchip";
    chip.textContent = keyLabel(p) + " → " + keyValText(k.set[p]);
    if (typeof k.set[p] === "string") chip.style.borderColor = k.set[p];
    var x = document.createElement("button"); x.textContent = "×"; x.title = "Stop keying " + keyLabel(p) + " here";
    x.onclick = function () { delete k.set[p]; changed(true); };
    chip.appendChild(x); ls.appendChild(chip);
  });
}
function buildKeyProps(d) {
  var fx = KV ? KV.fx : selFx(), keys = fx.keys, cur = frameAt(S.t), st = Math.max(0, fx.start_frame);
  var s = sec(d, "Keyframes (" + keys.length + ")", "fx-keys",
    "Animate this effect's numbers and colours over the action. Each key sets new values at a frame; they move there from the previous key across all the frames in between, along the key's ease, and hold after the last key.");
  var row0 = document.createElement("div"); row0.className = "keyrow" + (KV ? "" : " sel");
  row0.innerHTML = "<span class='kd'>●</span>";
  var t0 = document.createElement("span"); t0.className = "kt"; t0.textContent = "Start · frame " + st + " · the effect's own settings"; row0.appendChild(t0);
  var e0 = document.createElement("button"); e0.textContent = KV ? "Go to" : "Editing"; e0.disabled = !KV || !!keyAt(fx, st);
  e0.title = "Put the playhead on the start frame to edit the effect's own settings.";
  e0.onclick = function () { editKey(fx, st); }; row0.appendChild(e0); s.appendChild(row0);
  keys.forEach(function (k, i) {
    var on = KV && KV.key === k, r = document.createElement("div"); r.className = "keyrow" + (on ? " sel" : "");
    var dm = document.createElement("span"); dm.className = "kd"; dm.textContent = "◆"; r.appendChild(dm);
    var fr = inp("n", k.frame, function (v) {
      var nf = Math.max(0, Math.min(frames() - 1, Math.round(v)));
      if (nf === k.frame || keyAt(fx, nf)) return;   // one key per frame
      k.frame = nf; fx.keys.sort(function (x, y) { return x.frame - y.frame; });
      if (on) gotoFrame(nf);
      changed(true);
    }, 0, frames() - 1, 1);
    fr.title = "The frame this key sits on."; fr.className = "kf"; r.appendChild(fr);
    var prev = i ? keys[i - 1].frame : st;
    var ez = inp(FXK.EASES.map(function (e) { return [e, EASE_LABEL[e]]; }), k.ease, function (v) { k.ease = v; changed(); });
    ez.title = "How the values move into this key, over frames " + Math.min(prev, k.frame) + "–" + k.frame + ". Ease in: starts slow. Ease out: ends slow. Strong: more so. Hold: stays put, then jumps at this key. Bounce / Elastic: bounce or spring into the new value."; r.appendChild(ez);
    var ed = document.createElement("button"); ed.textContent = on ? "Editing" : "Go to"; ed.disabled = on;
    ed.title = "Put the playhead on frame " + k.frame + " to edit this key.";
    ed.onclick = function () { editKey(fx, k.frame); }; r.appendChild(ed);
    var rm = document.createElement("button"); rm.textContent = "✕"; rm.title = "Delete this keyframe";
    rm.onclick = function () { fx.keys.splice(fx.keys.indexOf(k), 1); changed(true); }; r.appendChild(rm);
    s.appendChild(r);
    s.appendChild(keyChips(fx, k, on));
  });
  var add = document.createElement("button"); add.id = "keyAdd";
  add.title = "Move the playhead (timeline or ← →) to the frame you want, then add a key there.";
  add.onclick = function () {
    var f = frameAt(S.t);
    if (!keyAt(fx, f)) { fx.keys.push({frame: f, ease: "inout", set: {}}); fx.keys.sort(function (x, y) { return x.frame - y.frame; }); save(); }
    editKey(fx, f);
  };
  s.appendChild(add); refreshKeyAdd();
  if (KV && KV.key.pending) note(s, "Frame " + cur + " has no key yet: change any number or colour below and a key is added here. It moves there from the previous key over every frame in between.");
  else if (KV) note(s, "Editing the key at frame " + KV.key.frame + " (the playhead). Move the playhead to edit another frame; numbers and colours you change are stored in the key on that frame. Choices and toggles change the whole effect.");
  else if (keys.length) note(s, "Editing the start (frame " + st + "): these settings are where the animation begins. Move the playhead to a later frame to key it.");
}

// "+ Key" follows the playhead (refreshed every frame by loop()).
function refreshKeyAdd() {
  var b = $("keyAdd"), fx = KV ? KV.fx : selFx();
  if (!b || !fx || !C) return;
  var f = frameAt(S.t), has = !!keyAt(fx, f);
  var t = has ? "◆ Key at frame " + f + " (playhead)" : "◆ + Key at frame " + f + " (playhead)";
  if (b.textContent !== t) b.textContent = t;
  b.disabled = has;
  // Once animated, the panel follows the playhead: rebuild when it lands on another frame.
  if (!S.playing && fx.keys && fx.keys.length && f !== PROPS_FRAME && document.activeElement && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) buildProps();
}
function buildProps() {
  var d = $("props"); d.innerHTML = ""; d.className = ""; KV = null;
  if (C && geoItem()) return buildGeoProps(d);
  var fx = selFx();
  if (fx) S.selGroup = null;
  else if (C && selGroup()) return buildGroupProps(d, selGroup());
  if (!fx) { if (C) buildActionProps(d); else { d.className = "note"; d.textContent = "Open a character folder to begin."; } return; }
  PROPS_FRAME = frameAt(S.t);
  fx = keyViewFor(fx);
  buildKeyProps(d);
  banner(d, "fx", KV ? (KV.key.pending ? "Frame " + KV.frame + " (no key yet)" : "Editing keyframe at frame " + KV.key.frame) : (fx.keys && fx.keys.length ? "Editing the start of the animation" : "Editing one effect"), fx.name + "  ·  " + fx.prim, "Plays on the " + fx.action + " action. The sections below change this effect only.",
    ["Action settings for " + fx.action, function () { S.sel = null; S.geo = null; buildEffects(); buildGeo(); buildProps(); buildTimeline(); }]);
  var s = sec(d, "Effect", "effect", "What this effect is: its name, FX-type tag, drawing primitive and draw layer.");
  field(s, "Name", inp("text", fx.name, function (v) { fx.name = v; buildEffects(); buildTimeline(); save(); }));
  field(s, "Tag (FX type)", inp("text", fx.tag, function (v) { fx.tag = v.trim().toLowerCase(); save(); })).title =
    "What kind of FX this is (e.g. fireball, slash, beam). Other characters' defend / deflect triggers react to these tags.";
  field(s, "Primitive", inp(FXK.PRIMS, fx.prim, function (v) { fx.prim = v; fx.params = {}; FXK.normalize(fx); buildEffects(); changed(true); }));
  if (fx.prim !== "weapon") {
    field(s, "Layer", inp([["front", "in front of figure"], ["behind", "behind figure"]], fx.layer, function (v) { fx.layer = v; changed(); }));
    field(s, "Blend", inp(["normal", "additive"], fx.blend, function (v) { fx.blend = v; changed(); }));
  }
  field(s, "Action", inp(Object.keys(C.actions), fx.action, function (v) { fx.action = v; S.action = v; delete fx.group; pruneGroups(); rebuild(); resetSim(0); save(); }));

  s = sec(d, "Purpose", "purpose", "Whether it damages the target where it touches, and how hard.");
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
      field(s, "Blockable", inp("chk", bt.blockable, function (v) { bt.blockable = v; changed(); })).title =
        "On: the other fighter's blocks stop it (defend action, special stance, parry stance, Intercept block / destroy). Off: blocks ignore it and the hit lands.";
      field(s, "Deflectable", inp("chk", bt.deflectable, function (v) { bt.deflectable = v; changed(); })).title =
        "On: the other fighter's deflects knock it away (Intercept deflect, parry ricochet). Off: deflects ignore it and the hit lands.";
    } else note(s, fx.prim === "weapon" ? "The weapon doesn't damage in this window." : "Visual only — this FX never damages.");
  }

  s = sec(d, "Timing (frames of " + fx.action + ": 0–" + (frames() - 1) + ")", "timing", "When it plays within the action's frames, how long each copy lives and how often it re-emits.");
  var canC = FXK.canContinue(fx), isC = canC && fx.continuous;
  if (canC) field(s, "∞ Continuous", inp("chk", fx.continuous, function (v) { fx.continuous = v; buildEffects(); changed(true); })).title =
    "On: starts at the start frame and never stops or resets while the action plays, loop after loop (an always-on laser trail). End frame, life and re-emit are ignored and it doesn't fade out.";
  else note(s, "Continuous (∞) is available for effects that stay on the fighter: attached, static or orbit motion, not arcs.");
  if (isC) note(s, "∞ Continuous is on: it starts at the start frame and keeps producing without resetting. End frame, life and re-emit below are ignored.");
  field(s, "Start frame", inp("n", fx.start_frame, function (v) { fx.start_frame = Math.max(0, Math.round(v)); changed(); }, 0, frames() - 1, 1));
  field(s, "End frame (-1 = end)", inp("n", fx.end_frame, function (v) { fx.end_frame = Math.round(v); changed(); }, -1, frames() - 1, 1));
  if (fx.prim !== "weapon") {
    field(s, "Life ticks (0 = to end)", inp("n", fx.life_ticks, function (v) { fx.life_ticks = Math.max(0, Math.round(v)); changed(); }, 0, 5000, 1));
    field(s, "Re-emit every N ticks", inp("n", fx.emit.every_ticks, function (v) { fx.emit.every_ticks = Math.max(0, Math.round(v)); changed(); }, 0, 600, 1));
    field(s, "Count per emit", inp("n", fx.emit.count, function (v) { fx.emit.count = Math.max(1, Math.round(v)); changed(); }, 1, 64, 1));
    field(s, "Fan ° (count > 1)", inp("n", fx.emit.fan_deg, function (v) { fx.emit.fan_deg = v; changed(); }, 0, 360, 1));
  }

  s = sec(d, fx.prim === "weapon" ? "Hitbox (from anchor → to anchor)" : "Anchor", "anchor",
    fx.prim === "weapon" ? "The two character anchors the hitbox runs between, frame by frame." : "Where on the character it starts: an anchor, or ⊕ an entry-point set (from Paths & entry points), plus an offset.");
  var fgr = fx.group && groupById(fx.group);
  if (fgr) {
    note(s, "Part of group \"" + fgr.name + "\": it rides the group's pivot (" + (S.labels[fgr.anchor] || fgr.anchor) + "). Its offset places it within the group.");
    var eg = document.createElement("button"); eg.textContent = "Edit group ▣ " + fgr.name;
    eg.onclick = function () { S.sel = null; S.selGroup = fgr.id; buildEffects(); buildProps(); buildTimeline(); };
    s.appendChild(eg);
  } else
  field(s, fx.prim === "weapon" ? "From anchor" : "Joint", inp(anchorOptions(fx.prim !== "weapon"), fx.anchor, function (v) { fx.anchor = v; changed(); }));
  if (fx.prim !== "weapon" && fx.anchor.indexOf("set:") === 0) {
    var es = S.entries.filter(function (e) { return "set:" + e.id === fx.anchor; })[0];
    if (es) note(s, "Comes out of " + es.points.length + " entry points, " + (es.mode === "sequential" ? "one after another every " + es.interval_ticks + " ticks." : "all at once.") + " Count per emit applies at each point.");
    else note(s, "That entry set no longer exists; it plays from the figure.");
  }
  if (fx.prim !== "weapon") {
    field(s, "Offset X px", inp("n", fx.offset[0], function (v) { fx.offset[0] = v; changed(); }, -500, 500, 0.5));
    field(s, "Offset Y px", inp("n", fx.offset[1], function (v) { fx.offset[1] = v; changed(); }, -500, 500, 0.5));
  }

  if (fx.prim !== "weapon") {
    s = sec(d, "Motion", "motion", "How it moves after it appears: stays attached, stays put, travels, homes, zigzags, orbits or follows a path.");
    field(s, MOTION_UI.kind[0], inp(MOTION_UI.kind[1], fx.motion.kind, function (v) { fx.motion.kind = v; changed(true); }));
    if (fx.motion.kind === "path") {
      var popts = [["", "— choose a path —"]].concat(S.paths.map(function (p) { return [p.id, p.name]; }));
      field(s, "Path", inp(popts, fx.motion.path, function (v) { fx.motion.path = v; changed(true); }));
      var pth = S.paths.filter(function (p) { return p.id === fx.motion.path; })[0];
      if (!S.paths.length) note(s, "No paths yet: add one under Paths & entry points on the left (there are presets).");
      else if (!pth) note(s, "Pick a path; until then it stays where it appears.");
      else note(s, "Runs start to end in " + pth.ticks + " ticks, " + (pth.orient === "aim" ? "turned toward the aim" : "mirrored with the facing") + (pth.follow ? ", riding along with the fighter" : "") + "; at the end it " + ({stop: "stops", loop: "starts over", "continue": "carries on straight"})[pth.end] + ".");
    }
    MOTION_KEYS[fx.motion.kind].forEach(function (k) {
      var u = MOTION_UI[k];
      if (k === "angle_deg" && fx.motion.aim !== "angle") return;
      field(s, u[0], Array.isArray(u[1]) ? inp(u[1], fx.motion[k], function (v) { fx.motion[k] = v; changed(true); })
        : inp("n", fx.motion[k], function (v) { fx.motion[k] = v; changed(); }, u[1], u[2], u[3]));
    });

    if (FXK.canIntercept(fx)) {
      s = sec(d, "Intercept", "intercept", "Auto-projectile tracker: this projectile goes after the enemy's projectiles when they come close, then blocks, deflects or destroys them.");
      var I = fx.intercept;
      field(s, "Auto-projectile tracker", inp("chk", I.enabled, function (v) { I.enabled = v; changed(true); })).title =
        "On: when an enemy projectile comes within the tracker radius, this projectile steers at it (like homing). With none in range it carries on with its own motion.";
      if (I.enabled) {
        field(s, "Tracker radius px", inp("n", I.radius, function (v) { I.radius = Math.max(0, v); changed(); }, 0, 1000, 1)).title =
          "Enemy projectiles closer than this are chased.";
        field(s, "Turn rate °/tick", inp("n", I.turn_deg, function (v) { I.turn_deg = Math.max(0, v); changed(); }, 0, 180, 0.5)).title =
          "How sharply it can turn toward the enemy projectile each tick.";
        field(s, "Contact px", inp("n", I.contact, function (v) { I.contact = Math.max(0, v); changed(); }, 0, 200, 0.5)).title =
          "The two projectiles collide when their centres come this close.";
        field(s, "On contact", inp([["block", "block: both nullified"], ["deflect", "deflect: knocked away"], ["destroy", "destroy: enemy's nullified"]], I.mode,
          function (v) { I.mode = v; changed(true); }));
        if (I.mode === "deflect") {
          field(s, "Deflect", inp([["enemy", "enemy projectile only"], ["both", "both projectiles"]], I.deflect_who, function (v) { I.deflect_who = v; changed(); })).title =
            "Enemy only: this projectile carries on. Both: this one is knocked away too. They fly off along their combined momentum.";
          field(s, "Deflected shot hurts its owner", inp("chk", I.hurts_owner, function (v) { I.hurts_owner = v; changed(); })).title =
            "On: the deflected enemy projectile turns against the fighter who fired it. Off: it flies off harmlessly.";
        }
        note(s, "Tick \"test shots\" under the stage to fire dummy enemy projectiles at the fighter and watch it work.");
      }
    }

    s = sec(d, "Flip & direction", "flip", "Flip: mirror left \u2194 right to whichever side the target is on. Follow direction: turn toward the target at any angle.");
    var F = fx.flip;
    if (fgr) note(s, "Shared by every effect in group \"" + fgr.name + "\", so the group mirrors and turns as one piece.");
    field(s, "Flip", inp("chk", F.enabled, function (v) { F.enabled = v; syncGroupTurn(fx); changed(true); })).title =
      "On: the effect plays on the side the target is on. When the target is on the other side from \"created side\", the whole effect plays as a mirror image: arc side and sweep, orbit spin and zigzag swing included. Off: it follows the fighter's facing only.";
    if (F.enabled) {
      field(s, "Created side", inp([["1", "target right"], ["-1", "target left"]], String(F.facing), function (v) { F.facing = +v < 0 ? -1 : 1; syncGroupTurn(fx); changed(true); })).title =
        "The side the target was on when this effect was authored. It plays as authored with the target on this side, and mirrored with the target on the other side.";
      note(s, "Target " + (F.facing < 0 ? "left" : "right") + ": plays as authored. Target " + (F.facing < 0 ? "right" : "left") + ": mirrored left \u2194 right (never up \u2194 down). Drag the target across the fighter to preview both.");
    }
    field(s, "Follow direction", inp("chk", fx.follow_dir, function (v) { fx.follow_dir = v; syncGroupTurn(fx); changed(true); })).title =
      "On: the whole effect turns toward the target. As authored it points straight ahead; with the target above or below it turns by that angle (offsets, arc, particles, orbit and paths included). Target-aimed effects already aim at the target.";
    if (fx.follow_dir) note(s, F.enabled ? "Mirrors to the target's side, then tilts up / down toward it. Drag the target around to preview."
      : "Turns toward the target at any angle; a target behind turns it right round (upside down). Tick Flip as well to mirror instead.");

    s = sec(d, "Colour", "colour", "Its colour: the character's palette, a two-colour gradient or a solid colour.");
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

  s = sec(d, fx.prim + " shape", "params", "Size and look settings that belong to the " + fx.prim + " primitive.");
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

// Trigger conditions (action_settings[action].conditions): grouped picker,
// labels, field editors and the live preview against the stage.
var COND_GROUPS = [
  ["Own state", ["hp_below", "hp_above", "self_speed_above", "self_speed_below"]],
  ["Target", ["target_within", "target_beyond", "target_between", "target_above", "target_below", "target_facing",
    "target_attacking", "target_defending", "target_hp_below", "target_hp_above", "target_speed_above", "target_speed_below"]],
  ["Hits & projectiles", ["attacks_made", "hits_taken", "damage_taken", "landed_hit", "hit_by_fx", "fx_near", "projectile_count", "bullet_deflected"]],
  ["Timing & order", ["after_actions", "since_action", "every_ms", "idle_for", "chance"]]];
var COND_LABEL = {hp_below: "own HP at or below %", hp_above: "own HP at or above %",
  self_speed_above: "own speed at least px/s", self_speed_below: "own speed at most px/s",
  target_within: "target closer than px", target_beyond: "target further than px", target_between: "target distance between px",
  target_above: "target above me", target_below: "target below me", target_facing: "target facing me / away",
  target_attacking: "target is attacking", target_defending: "target is defending",
  target_hp_below: "target HP at or below %", target_hp_above: "target HP at or above %",
  target_speed_above: "target speed at least px/s", target_speed_below: "target speed at most px/s",
  attacks_made: "after N attacks made", hits_taken: "after N hits taken", damage_taken: "HP lost recently",
  landed_hit: "just landed a hit", hit_by_fx: "hit by FX tagged", fx_near: "enemy FX tagged … within px",
  projectile_count: "enemy projectiles on screen", bullet_deflected: "a bullet was deflected",
  after_actions: "after completing actions in order", since_action: "time since an action last played",
  every_ms: "every N ms", idle_for: "idle (no action) for ms", chance: "random chance per second"};
var COND_HELP = {
  hp_below: "Own HP is at or below the %. Fires once each time HP drops past it, unless Repeat on cooldown is on.",
  hp_above: "Own HP is at or above the % (e.g. only while healthy).",
  self_speed_above: "This fighter is moving at least this fast (game px per second, averaged over ~0.1 s).",
  self_speed_below: "This fighter is moving at most this fast. Around 20 px/s means standing still.",
  target_within: "The target is this close or closer.", target_beyond: "The target is this far or further.",
  target_between: "The target's distance is inside the band (e.g. 60–200 px: not too close, not too far).",
  target_above: "The target is at least this many px higher on screen.", target_below: "The target is at least this many px lower on screen.",
  target_facing: "Toward: the target faces this fighter. Away: it has its back turned. In Solo the cursor faces the way it last moved sideways.",
  target_attacking: "The target is dashing / slashing, or playing an attack, attack_special or ultimate action. Battle only (the Solo cursor never attacks).",
  target_defending: "The target is parrying or playing its defend action. Battle only.",
  target_hp_below: "The target's HP is at or below the %. Battle only (the Solo cursor has no HP).",
  target_hp_above: "The target's HP is at or above the %. Battle only.",
  target_speed_above: "The target is moving at least this fast (px/s).", target_speed_below: "The target is moving at most this fast (px/s).",
  attacks_made: "This many attacks were made since this action last fired.", hits_taken: "Hit this many times since this action last fired.",
  damage_taken: "Lost at least this much HP within the time window.",
  landed_hit: "One of this fighter's damaging FX hit the target this tick (Battle).",
  hit_by_fx: "Hit this tick by an enemy FX with one of these tags (empty = any hit).",
  fx_near: "An enemy damaging FX / bullet with one of these tags is within the distance (empty = any).",
  projectile_count: "At least this many enemy projectiles and damaging FX are live at once.",
  bullet_deflected: "This fighter just started a parry / deflect.",
  after_actions: "The last actions completed were exactly these, in this order.",
  since_action: "The chosen action last ended at least this long ago (or has never played). Good for spacing moves apart.",
  every_ms: "At least this long since this action last started (or since the fight began): a repeating timer.",
  idle_for: "No attack or triggered action has played for at least this long.",
  chance: "A random roll: this % chance per second while the other conditions hold (100 = always)."};
var COND_FIELDS = {pct: ["HP %", 1, 100, 1], count: ["Count", 1, 200, 1], px: ["Distance px", 0, 2000, 1],
  min_px: ["From px", 0, 2000, 5], max_px: ["To px", 0, 2000, 5], px_s: ["Speed px/s", 0, 5000, 5],
  hp: ["HP lost", 1, 10000, 1], ms: ["Time ms", 0, 60000, 50], pct_s: ["Chance %/s", 0, 100, 1],
  tags: ["Tags (comma, empty = any)", "tags"], sequence: ["Actions in order", "sequence"], action: ["Action", "action"],
  dir: ["Target faces", "dir"], repeat: ["Repeat on cooldown", "chk"]};
// Preview-only state for the conditions the stage can't show (not saved).
var PREV = {hp: 100, thp: 100, tface: "toward", tatk: false, tdef: false, own: -1, tspeed: 0, attacks: 0, hits: 0, hplost: 0,
  landed: false, hitOn: false, hitTag: "", nearOn: false, nearTag: "", nearPx: 100, proj: 0, deflected: false, history: "",
  since: {}, everyMs: 0, idleMs: 0, chanceHit: false};
// Which preview inputs each condition type reads (the Live preview shows only these).
var PREV_USES = {hp_below: ["hp"], hp_above: ["hp"], self_speed_above: ["own"], self_speed_below: ["own"],
  target_facing: ["tface"], target_attacking: ["tatk"], target_defending: ["tdef"], target_hp_below: ["thp"], target_hp_above: ["thp"],
  target_speed_above: ["tspeed"], target_speed_below: ["tspeed"], attacks_made: ["attacks"], hits_taken: ["hits"],
  damage_taken: ["hplost"], landed_hit: ["landed"], hit_by_fx: ["hitOn", "hitTag"], fx_near: ["nearOn", "nearTag", "nearPx"],
  projectile_count: ["proj"], bullet_deflected: ["deflected"], after_actions: ["history"], since_action: ["since"],
  every_ms: ["everyMs"], idle_for: ["idleMs"], chance: ["chanceHit"]};
function prevTags(s) { return String(s || "").split(",").map(function (t) { return t.trim().toLowerCase(); }).filter(Boolean); }
function prevTagMatch(want, tag) { return !want.length || want.indexOf(String(tag || "").trim().toLowerCase()) >= 0; }
function condSelect() {
  var e = document.createElement("select");
  COND_GROUPS.forEach(function (gr) {
    var og = document.createElement("optgroup"); og.label = gr[0];
    gr[1].forEach(function (k) { var o = document.createElement("option"); o.value = k; o.textContent = COND_LABEL[k]; o.title = COND_HELP[k]; og.appendChild(o); });
    e.appendChild(og);
  });
  return e;
}
// Tags the hit_by_fx / fx_near fields can match: every effect's tag, plus "bullet".
function knownTags() {
  var t = {bullet: 1}; S.effects.forEach(function (e) { if (e.tag) t[e.tag] = 1; });
  ["fireball", "slash", "beam", "laser", "bolt", "orb"].forEach(function (k) { t[k] = 1; });
  return Object.keys(t).sort();
}
function tagsInput(c, k) {
  var e = inp("text", c[k], function (v) { c[k] = v; save(); });
  e.setAttribute("list", "fxTagList"); e.placeholder = "any";
  return e;
}
// after_actions: one picker per step, stored as the comma separated string.
function sequenceEditor(c) {
  var w = document.createElement("div"); w.className = "seq";
  var seq = String(c.sequence || "").split(",").map(function (x) { return x.trim(); }).filter(Boolean);
  var acts = Object.keys(C.actions).filter(function (k) { return FXK.actionKind(k) !== "locomotion"; });   // idle / run never "complete"
  function commit() { c.sequence = seq.join(", "); save(); buildProps(); }
  seq.forEach(function (a, i) {
    var r = document.createElement("div"); r.className = "row";
    var sl = inp(acts.indexOf(a) < 0 ? [a].concat(acts) : acts, a, function (v) { seq[i] = v; commit(); });
    var x = document.createElement("button"); x.textContent = "×"; x.title = "Remove this step"; x.onclick = function () { seq.splice(i, 1); commit(); };
    var n = document.createElement("span"); n.className = "note"; n.textContent = (i + 1) + ".";
    r.appendChild(n); r.appendChild(sl); r.appendChild(x); w.appendChild(r);
  });
  var r2 = document.createElement("div"); r2.className = "row";
  var add = inp([["", "+ add step…"]].concat(acts), "", function (v) { if (v) { seq.push(v); commit(); } });
  r2.appendChild(add); w.appendChild(r2);
  return w;
}
function condField(box, c, k) {
  var u = COND_FIELDS[k];
  if (!u) return;
  if (u[1] === "chk") return field(box, u[0], inp("chk", c[k], function (v) { c[k] = v; save(); }));
  if (u[1] === "tags") return field(box, u[0], tagsInput(c, k));
  if (u[1] === "sequence") return field(box, u[0], sequenceEditor(c));
  if (u[1] === "action") return field(box, u[0], inp([["", "— this action —"]].concat(Object.keys(C.actions).filter(function (a) { return a !== S.action; })),
    c[k], function (v) { c[k] = v; save(); }));
  if (u[1] === "dir") return field(box, u[0], inp([["toward", "toward me"], ["away", "away (back turned)"]], c[k], function (v) { c[k] = v; save(); }));
  return field(box, u[0], inp("n", c[k], function (v) { c[k] = Math.max(u[1], Math.min(u[2], v)); save(); }, u[1], u[2], u[3]));
}
// Live preview: what each condition reads right now against the stage
// (distance and height to the dragged target, the sim's movement) and the
// preview inputs in the Live preview section (same rules as laser/actions.py).
function condNow(c) {
  var dx = S.target[0] - S.figX, dy = S.target[1] - S.figY, dist = Math.hypot(dx, dy);
  var sim = Math.hypot(S.vel[0], S.vel[1]) * simMoveFactor() * 1000 / FXK.TICK_MS;
  var own = PREV.own >= 0 ? PREV.own : sim, v = null, why = "";
  switch (c.type) {
    case "hp_below": v = PREV.hp <= c.pct; break;
    case "hp_above": v = PREV.hp >= c.pct; break;
    case "self_speed_above": v = own >= c.px_s; break;
    case "self_speed_below": v = own <= c.px_s; break;
    case "target_within": v = dist <= c.px; break;
    case "target_beyond": v = dist >= c.px; break;
    case "target_between": v = dist >= Math.min(c.min_px, c.max_px) && dist <= Math.max(c.min_px, c.max_px); break;
    case "target_above": v = -dy >= c.px; break;
    case "target_below": v = dy >= c.px; break;
    case "target_facing": v = (c.dir === "away") === (PREV.tface === "away"); break;
    case "target_attacking": v = PREV.tatk; break;
    case "target_defending": v = PREV.tdef; break;
    case "target_hp_below": v = PREV.thp <= c.pct; break;
    case "target_hp_above": v = PREV.thp >= c.pct; break;
    case "target_speed_above": v = PREV.tspeed >= c.px_s; break;
    case "target_speed_below": v = PREV.tspeed <= c.px_s; break;
    case "attacks_made": v = PREV.attacks >= c.count; break;
    case "hits_taken": v = PREV.hits >= c.count; break;
    case "damage_taken": v = PREV.hplost >= c.hp; break;
    case "landed_hit": v = PREV.landed; break;
    case "hit_by_fx": v = PREV.hitOn && prevTagMatch(prevTags(c.tags), PREV.hitTag); break;
    case "fx_near": v = PREV.nearOn && PREV.nearPx <= c.px && prevTagMatch(prevTags(c.tags), PREV.nearTag); break;
    case "projectile_count": v = PREV.proj >= c.count; break;
    case "bullet_deflected": v = PREV.deflected; break;
    case "after_actions":
      var seq = String(c.sequence || "").split(",").map(function (x) { return x.trim(); }).filter(Boolean);
      var hist = String(PREV.history || "").split(",").map(function (x) { return x.trim(); }).filter(Boolean);
      v = seq.length > 0 && hist.slice(-seq.length).join(",") === seq.join(","); break;
    case "since_action": v = prevSince(c.action || S.action) >= c.ms; break;
    case "every_ms": v = PREV.everyMs >= c.ms; break;
    case "idle_for": v = PREV.idleMs >= c.ms; break;
    case "chance": v = PREV.chanceHit; break;
    default: why = "known in the game only";
  }
  if (v !== null && c.not) v = !v;
  return {v: v, why: why, dist: dist, own: own};
}
function prevSince(a) { var v = PREV.since[a]; return v == null ? 5000 : v; }
// The Live preview inputs for the condition types this action uses.
function buildPrevInputs(p, cfg) {
  var used = {}, sinceActs = [];
  cfg.conditions.forEach(function (c) {
    (PREV_USES[c.type] || []).forEach(function (k) { used[k] = 1; });
    if (c.type === "since_action") { var a = c.action || S.action; if (sinceActs.indexOf(a) < 0) sinceActs.push(a); }
  });
  var num = function (label, k, lo, hi, st, tip) {
    field(p, label, inp("n", PREV[k], function (v) { PREV[k] = Math.max(lo, Math.min(hi, v)); }, lo, hi, st)).title = tip || "";
  };
  var chk = function (label, k, tip) { field(p, label, inp("chk", PREV[k], function (v) { PREV[k] = v; })).title = tip || ""; };
  if (used.hp) num("Own HP %", "hp", 0, 100, 5);
  if (used.own) num("Own speed px/s", "own", -1, 5000, 10, "-1 = use the sim's movement below the stage.");
  if (used.thp) num("Target HP %", "thp", 0, 100, 5);
  if (used.tface) field(p, "Target faces", inp([["toward", "toward me"], ["away", "away"]], PREV.tface, function (v) { PREV.tface = v; }));
  if (used.tatk) chk("Target attacking", "tatk");
  if (used.tdef) chk("Target defending", "tdef");
  if (used.tspeed) num("Target speed px/s", "tspeed", 0, 5000, 10);
  if (used.attacks) num("Attacks made since", "attacks", 0, 200, 1, "Attacks made since this action last fired.");
  if (used.hits) num("Hits taken since", "hits", 0, 200, 1, "Hits taken since this action last fired.");
  if (used.hplost) num("HP lost in window", "hplost", 0, 10000, 1, "HP lost within the condition's time window.");
  if (used.landed) chk("Just landed a hit", "landed");
  if (used.hitOn) {
    chk("Hit this tick", "hitOn");
    var ht = inp("text", PREV.hitTag, function (v) { PREV.hitTag = v; }); ht.setAttribute("list", "fxTagList"); ht.placeholder = "(untagged)";
    field(p, "…by FX tagged", ht).title = "The tag of the FX that hit (empty = an untagged hit).";
  }
  if (used.nearOn) {
    chk("Enemy FX nearby", "nearOn");
    var nt = inp("text", PREV.nearTag, function (v) { PREV.nearTag = v; }); nt.setAttribute("list", "fxTagList"); nt.placeholder = "(untagged)";
    field(p, "…tagged", nt);
    num("…at distance px", "nearPx", 0, 2000, 5);
  }
  if (used.proj) num("Enemy projectiles live", "proj", 0, 200, 1);
  if (used.deflected) chk("Just deflected a bullet", "deflected");
  if (used.history) {
    var acts = Object.keys(C.actions).filter(function (k) { return FXK.actionKind(k) !== "locomotion"; });
    var hw = document.createElement("div"); hw.className = "seq";
    var hist = String(PREV.history || "").split(",").map(function (x) { return x.trim(); }).filter(Boolean);
    var redo = function () { PREV.history = hist.join(", "); buildProps(); };
    hist.forEach(function (a, i) {
      var r = document.createElement("div"); r.className = "row";
      var n = document.createElement("span"); n.className = "note"; n.textContent = (i + 1) + ".";
      var x = document.createElement("button"); x.textContent = "×"; x.onclick = function () { hist.splice(i, 1); redo(); };
      r.appendChild(n); r.appendChild(inp(acts, a, function (v) { hist[i] = v; redo(); })); r.appendChild(x); hw.appendChild(r);
    });
    var r2 = document.createElement("div"); r2.className = "row";
    r2.appendChild(inp([["", "+ completed…"]].concat(acts), "", function (v) { if (v) { hist.push(v); redo(); } }));
    hw.appendChild(r2);
    field(p, "Last completed (oldest → newest)", hw);
  }
  sinceActs.forEach(function (a) {
    field(p, "ms since " + a + " ended", inp("n", prevSince(a), function (v) { PREV.since[a] = Math.max(0, v); }, 0, 60000, 100)).title =
      "How long ago " + a + " last ended (a large value = it hasn't played).";
  });
  if (used.everyMs) num("ms since this started", "everyMs", 0, 60000, 100, "Time since " + S.action + " last started.");
  if (used.idleMs) num("ms idle (no action)", "idleMs", 0, 60000, 100);
  if (used.chanceHit) chk("Chance roll succeeds", "chanceHit", "In the game it's a random roll each tick; tick to preview a successful roll.");
  if (!Object.keys(used).length) note(p, cfg.conditions.length ? "These conditions read only the stage: drag the target." : "Add a condition to preview it.");
}
function condPreviewText(r) {
  return r.v === true ? "✓ met now" : r.v === false ? "✗ not met now" : "– " + r.why;
}
function refreshCondPreview() {
  var box = $("condAll");
  if (!box || !C || !S.action) return;
  var cfg = cfgOf(S.action), known = [], unknown = 0;
  cfg.conditions.forEach(function (c, i) {
    var r = condNow(c), el = document.querySelector('.cpv[data-i="' + i + '"]');
    if (el) { var t = condPreviewText(r); if (el.textContent !== t) { el.textContent = t; el.className = "cpv " + (r.v === true ? "ok" : r.v === false ? "bad" : "mute"); } }
    if (r.v === null) unknown++; else known.push(r.v);
  });
  var all = cfg.logic === "all", res;
  if (!cfg.conditions.length) res = FXK.actionKind(S.action) === "attack" ? "No conditions: attacks whenever the target is in range." : "No conditions: never fires.";
  else if (all ? known.indexOf(false) >= 0 : known.indexOf(true) >= 0) res = all ? "✗ would not fire now" : "✓ would fire now";
  else if (unknown) res = "– depends on game-only conditions";
  else res = all ? "✓ would fire now" : "✗ would not fire now";
  var r0 = condNow({type: "target_within", px: 0}), extra = "  (target " + Math.round(r0.dist) + " px away, own speed " + Math.round(r0.own) + " px/s)";
  if (FXK.actionKind(S.action) === "attack" && cfg.conditions.length && res.charAt(0) === "✓") res += " — when the target is in range";
  if (box.textContent !== res + extra) box.textContent = res + extra;
}
// Character-level Aim (pack.aim), shown under every action's settings.
function buildAimProps(d) {
  var s = sec(d, "Aim (whole character)", "a-aim", "Always face the target and turn every frame so the weapon points at it. Applies to all actions.", "act");
  var am = S.aim, ids = anchorIds().map(function (j) { return [j, S.labels[j] || j]; });
  var ch = function () { save(); buildProps(); resetSim(S.t); };
  field(s, "Aim at target", inp("chk", am.enabled, function (v) { am.enabled = v; ch(); })).title =
    "On: the fighter always faces the target, and each frame turns so the barrel line (from → to anchor) points at it.";
  if (!am.enabled) return;
  field(s, "Barrel from anchor", inp(ids, am.from_anchor, function (v) { am.from_anchor = v; ch(); })).title = "Where the weapon starts (e.g. the hand).";
  field(s, "Barrel to anchor", inp(ids, am.to_anchor, function (v) { am.to_anchor = v; ch(); })).title = "The point it shoots from (e.g. the muzzle / weapon tip).";
  field(s, "Fallback action", inp(Object.keys(C.actions), am.source, function (v) { am.source = v; ch(); })).title =
    "Frames without both anchors use this action's barrel, averaged over its frames (normally attack_normal).";
  field(s, "Max turn °", inp("n", am.max_deg, function (v) { am.max_deg = Math.max(0, Math.min(180, v)); save(); resetSim(S.t); }, 0, 180, 5)).title =
    "How far the frame may turn either way (180 = no limit, always on target).";
  if (!aimRef()) note(s, "No frames of " + am.source + " have both anchors placed: aiming is off until they are.");
  else note(s, "Preview: drag the target around the stage; the figure turns to keep the barrel on it (now " + Math.round(aimDeg()) + "°).");
}
// Character-level Damaged settings (pack.damaged), shown under every action's settings.
function buildDamagedProps(d) {
  var s = sec(d, "Damaged (whole character)", "a-damaged", "How this character takes hits. Applies to every action and every kind of hit.", "act");
  var dm = S.damaged, info = document.createElement("div"); info.className = "note";
  function say() {
    var ms = +dm.cooldown_ms || 0;
    info.textContent = ms > 0 ? "A hit takes HP, then the character is invincible for " + Math.round(ms) + " ms (about " + Math.max(1, Math.round(ms / FXK.TICK_MS)) + " ticks)."
      : "0: every hit takes HP.";
  }
  field(s, "Hit cooldown ms", inp("n", dm.cooldown_ms, function (v) { dm.cooldown_ms = Math.max(0, Math.min(10000, v)); say(); save(); }, 0, 10000, 10)).title =
    "After a hit takes HP, the character is invincible (no HP loss, no knockback) for this long. The next hit after it ends takes HP again. 0 = every hit takes HP.";
  say(); s.appendChild(info);
}
// Character-level Tactical retreat (pack.retreat), shown under every action's settings.
var RETREAT_COND_LABEL = {hp_below: "own HP at or below %", projectile_count: "enemy projectiles on screen at once"};
function buildRetreatProps(d) {
  var s = sec(d, "Tactical retreat (whole character)", "a-retreat",
    "Dash away from harm, or round to the target's back to attack it, when the conditions below are met. Applies to all actions.", "act");
  var rt = S.retreat, ch = function () { save(); buildProps(); };
  field(s, "Tactical retreat", inp("chk", rt.enabled, function (v) { rt.enabled = v; ch(); })).title =
    "On: the character dashes when the trigger conditions are met.";
  if (!rt.enabled) return;
  field(s, "Mode", inp([["avoid", "Avoid"], ["reengage", "Re-engage"]], rt.mode,
    function (v) { rt.mode = v; ch(); })).title =
    "Avoid: dashes along the angle and curve, steering away from enemy projectiles and the target. Re-engage: heads for the side opposite the way the target was facing when the retreat started, and attacks on arrival.";
  field(s, "Dash angle °", inp("n", rt.angle_deg, function (v) { rt.angle_deg = Math.max(-180, Math.min(180, v)); save(); }, -180, 180, 5)).title =
    "Measured from the direction to the target: 0 = straight at it, 180 or -180 = straight away, 90 = sideways (positive turns clockwise on screen).";
  field(s, "Curve °/s", inp("n", rt.curve_deg_s, function (v) { rt.curve_deg_s = Math.max(-1440, Math.min(1440, v)); save(); }, -1440, 1440, 5)).title =
    rt.mode === "reengage" ? "0 = straight to the target's back. Otherwise it leaves along the dash angle and swings round toward the target's back at this many degrees per second."
      : "How much the dash bends, in degrees per second (0 = straight, positive = clockwise).";
  field(s, "Speed %", inp("n", rt.speed_pct, function (v) { rt.speed_pct = Math.max(0, Math.min(1000, v)); save(); }, 0, 1000, 10)).title =
    "Dash speed as a % of the character's normal speed (100 = normal, 200 = twice as fast).";
  field(s, "Proximity px", inp("n", rt.proximity_px, function (v) { rt.proximity_px = Math.max(0, Math.min(1000, v)); save(); }, 0, 1000, 5)).title =
    "How close harm may get before the character steers away from it during the dash (enemy projectiles; in Avoid also the target itself). 0 = no steering.";
  if (rt.mode === "reengage") field(s, "Re-engage duration ms", inp("n", rt.reengage_duration_ms, function (v) { rt.reengage_duration_ms = v < 0 ? -1 : Math.min(60000, v); save(); }, -1, 60000, 50)).title =
    "How long it keeps trying to reach the target's back. -1 = no limit (until it gets there and attacks).";
  else field(s, "Avoid duration ms", inp("n", rt.avoid_duration_ms, function (v) { rt.avoid_duration_ms = v < 0 ? -1 : Math.min(60000, v); save(); }, -1, 60000, 50)).title =
    "How long the avoiding dash lasts. -1 = no limit (it never stops avoiding).";
  field(s, "Cooldown ms", inp("n", rt.cooldown_ms, function (v) { rt.cooldown_ms = Math.max(0, v); save(); }, 0, 60000, 50)).title =
    "After a retreat ends, how long before another can start.";
  field(s, "Trigger when", inp([["any", "ANY condition is met"], ["all", "ALL conditions are met"]], rt.logic, function (v) { rt.logic = v; save(); }));
  rt.conditions.forEach(function (c, i) {
    var box = sec(s, "Condition " + (i + 1) + ": " + RETREAT_COND_LABEL[c.type], "a-rcond", null, "act");
    if (c.type === "hp_below") {
      field(box, "HP %", inp("n", c.pct, function (v) { c.pct = Math.max(1, Math.min(100, v)); save(); }, 1, 100, 1));
      field(box, "Repeat on cooldown", inp("chk", c.repeat, function (v) { c.repeat = v; save(); })).title =
        "On: while HP stays at or below the %, it can retreat again every time the cooldown ends. Off: once when HP first drops to the %.";
    } else {
      field(box, "Projectiles", inp("n", c.count, function (v) { c.count = Math.max(1, Math.round(v)); save(); }, 1, 200, 1)).title =
        "Triggers when this many or more enemy projectiles are in the air at the same time.";
    }
    var rm = document.createElement("button"); rm.textContent = "Remove"; rm.onclick = function () { rt.conditions.splice(i, 1); ch(); };
    box.appendChild(rm);
  });
  var row = document.createElement("div"); row.className = "row";
  var sel = inp(Object.keys(FXK.RETREAT_CONDITIONS).map(function (k) { return [k, RETREAT_COND_LABEL[k]]; }), "hp_below", function () {});
  var add = document.createElement("button"); add.textContent = "+ Condition";
  add.onclick = function () { rt.conditions.push(FXK.normalizeRetreat({conditions: [{type: sel.value}]}).conditions[0]); ch(); };
  row.appendChild(sel); row.appendChild(add); s.appendChild(row);
  if (!rt.conditions.length) note(s, "No conditions yet: add one, or the retreat never triggers.");
}
// Blink (action_settings[action].blink): this action's own teleport.  The
// fighter vanishes at the start frame and reappears after the end frame.
function buildBlinkProps(d) {
  var a = S.action, bk = cfgOf(a).blink, n = frames();
  var s = sec(d, "Blink (this action)", "a-blink",
    "A teleport inside this action: the fighter vanishes at the start frame and reappears after the end frame. Each action has its own.", "act");
  var ch = function () { save(); buildProps(); resetSim(S.t); };
  field(s, "Blink", inp("chk", bk.enabled, function (v) { bk.enabled = v; ch(); })).title =
    "On: every time this action plays, the character vanishes at the start frame and reappears after the end frame.";
  if (!bk.enabled) return;
  field(s, "Vanish at frame", inp("n", bk.start_frame, function (v) { bk.start_frame = Math.max(0, Math.min(n - 1, Math.round(v))); ch(); }, 0, n - 1, 1)).title =
    "The frame the character disappears on.";
  field(s, "Reappear after frame (-1 = end)", inp("n", bk.end_frame, function (v) { bk.end_frame = Math.max(-1, Math.min(n - 1, Math.round(v))); ch(); }, -1, n - 1, 1)).title =
    "The last frame it stays gone for; it reappears on the next frame. -1 = gone until the action ends.";
  var e = bk.end_frame < 0 ? n - 1 : Math.min(n - 1, bk.end_frame);
  if (e < bk.start_frame) note(s, "The reappear frame is before the vanish frame, so it never vanishes. Set it to " + bk.start_frame + " or later.");
  else {
    var ms = Math.round((e - bk.start_frame + 1) * frameMs());
    note(s, "Gone for frames " + bk.start_frame + "\u2013" + e + " (about " + ms + " ms)" + (bk.end_frame < 0 || e === n - 1 ? ", then reappears when the action ends." : ", reappears on frame " + (e + 1) + ".")
      + " The animation keeps running while it's hidden.");
  }
  field(s, "Reappear near", inp([["target", "the target"], ["self", "where it vanished"]], bk.anchor, function (v) { bk.anchor = v; ch(); })).title =
    "What the distance below is measured from. The target: where the target is when it reappears. Where it vanished: the spot it disappeared from.";
  field(s, "Side", inp([["behind", "behind the target"], ["front", "in front of the target"], ["toward", "toward the target"],
    ["away", "away from the target"], ["random", "random"], ["angle", "fixed angle"]], bk.direction, function (v) { bk.direction = v; ch(); })).title =
    "Which way from that point it lands. Behind / in front: the far / near side of the target (in Battle, the target's back / front). Toward / away: along the line from where it vanished to the target. Fixed angle: the angle below.";
  if (bk.direction === "angle") field(s, "Angle \u00b0", inp("n", bk.angle_deg, function (v) { bk.angle_deg = Math.max(-180, Math.min(180, v)); ch(); }, -180, 180, 5)).title =
    "Measured from the direction to the target: 0 = toward it, 180 or -180 = away, 90 = sideways (positive turns clockwise on screen).";
  field(s, "Distance px", inp("n", bk.proximity_px, function (v) { bk.proximity_px = Math.max(0, Math.min(2000, v)); ch(); }, 0, 2000, 5)).title =
    "How far from that point it lands (game px). 0 = right on it.";
  field(s, "Flash FX", inp("chk", bk.flash, function (v) { bk.flash = v; save(); })).title =
    "On: a crackle and an afterimage where it vanishes and where it reappears.";
  note(s, "While gone: invisible, takes no hits, doesn't move, fires no new FX (shots already flying carry on). On the stage: the dashed outline is where it vanished, the green ring where it will land. Drag the target to move the landing spot.");
}
// Right panel when no effect is selected: WHEN this action plays.
function buildActionProps(d) {
  var a = S.action, cfg = cfgOf(a), kind = FXK.actionKind(a);
  banner(d, "act", "Action settings", a, "Applies to the whole action and every effect on it. Select an effect on the left or on the timeline to edit that effect.");
  var s = sec(d, "When it plays", "a-when", "What starts this action in the game, and how long it runs.", "act");
  note(s, kind === "locomotion" ? (a === "idle" ? "Plays while the fighter stands still." : "Plays while the fighter moves.")
    : kind === "attack" ? "Attacks when the target is in attack range and its trigger conditions (below, if any) pass. The attack plays in full, and only this action's FX with Deals damage (and weapon hitboxes) hurt."
    : "Plays when its conditions are met, then runs in full.");
  note(s, frames() + " frames × " + Math.round(frameMs() * 10) / 10 + " ms = " + Math.round(frames() * frameMs()) + " ms (timing comes from Rig Forge)");
  if (kind !== "locomotion") {
    field(s, "Animation loops", inp("n", cfg.anim_loops, function (v) { cfg.anim_loops = Math.max(1, Math.min(99, Math.round(v) || 1)); save(); buildProps(); resetSim(0); }, 1, 99, 1)).title =
      "How many times the animation plays before the action ends (1 = once). The FX loop with each pass as they normally do.";
    var nl = FXK.animLoops(a, cfg);
    if (nl > 1) note(s, "Plays the animation " + nl + " times = " + Math.round(nl * frames() * frameMs()) + " ms in all, then the action ends.");
  } else note(s, "Loops for as long as the fighter is " + (a === "idle" ? "standing still." : "moving."));
  field(s, "Continuous FX on loop", inp("chk", cfg.fx_continuous, function (v) { cfg.fx_continuous = v; save(); syncContinuous(); })).title =
    "On: effects that last to the end of the action keep running when the animation loops, instead of restarting.";
  s = sec(d, "Movement", "a-move", "Whether the fighter stands still while doing this action or can keep moving.", "act");
  if (kind === "locomotion") note(s, a === "idle" ? "Idle always stands still." : "Run always moves; it is the moving action.");
  else {
    field(s, "While doing it", inp([["stand", "Stand still"], ["move", "Keep moving"], ["back", "Move back from target"]], cfg.movement, function (v) { cfg.movement = v; save(); buildProps(); resetSim(S.t); })).title =
      "Stand still: the fighter stops in place for the whole action. Keep moving: it can keep moving while the action plays. Move back from target: it retreats straight away from the target, then holds.";
    if (cfg.movement === "back") field(s, "Stop at % of action", inp("n", cfg.back_stop_pct, function (v) { cfg.back_stop_pct = Math.max(0, Math.min(100, v)); save(); resetSim(S.t); }, 0, 100, 5)).title =
      "The retreat stops once this much of the whole action (all its animation loops) has played; it stands still for the rest.";
    if (cfg.movement === "move" || cfg.movement === "back") field(s, "Move speed %", inp("n", cfg.move_speed_pct, function (v) { cfg.move_speed_pct = Math.max(0, Math.min(300, v)); save(); resetSim(S.t); }, 0, 300, 5)).title =
      "How fast it moves during this action, as a % of its normal speed (100 = full speed, 50 = half).";
    note(s, cfg.movement === "back" ? "Preview: the figure backs away from the target (drag the target) at this % of the sim's move speed (2 px/tick when move is 0), stopping at " + cfg.back_stop_pct + "% of the action."
      : "Preview it with the direction sim below the stage (set move above 0): " + (cfg.movement === "move" ? "the figure keeps travelling while this action plays." : "the figure holds still while this action plays."));
  }
  buildBlinkProps(d);
  buildAimProps(d);
  buildDamagedProps(d);
  buildRetreatProps(d);
  if (kind === "locomotion") return;
  if (kind === "attack") {
    s = sec(d, "Attack chain (combo)", "a-chain", "Which attack action plays next when attacks are chained.", "act");
    var others = [["", "— none (every attack plays " + a + ") —"]].concat(Object.keys(C.actions).filter(function (k) { return k !== a && FXK.actionKind(k) === "attack"; }).map(function (k) { return [k, k]; }));
    field(s, "Next attack", inp(others, cfg.chain_next, function (v) { cfg.chain_next = v; save(); buildProps(); }));
    field(s, "Reset after ms idle", inp("n", cfg.chain_reset_ms, function (v) { cfg.chain_reset_ms = Math.max(0, v); save(); }, 0, 10000, 50));
    if (others.length === 1) note(s, "To chain, add more attack actions in Rig Forge named attack_normal_2, attack_normal_3 … and export again.");
  }
  buildTriggerProps(d, a, cfg, kind);
}
// Trigger conditions for an attack or triggered action.
function buildTriggerProps(d, a, cfg, kind) {
  var s = sec(d, "Trigger conditions", "a-trig", kind === "attack"
    ? "Extra conditions for this attack, checked on top of the target being in attack range. None = it attacks on range alone."
    : "The conditions that start this action, how they combine, and the cooldown.", "act");
  var ch = function () { save(); buildProps(); };
  field(s, "Fire when", inp([["any", "ANY condition is met"], ["all", "ALL conditions are met"]], cfg.logic, function (v) { cfg.logic = v; save(); }));
  field(s, "Cooldown ms", inp("n", cfg.cooldown_ms, function (v) { cfg.cooldown_ms = Math.max(0, v); save(); }, 0, 60000, 50)).title =
    "After it starts, how long before it can start again.";
  var dl = document.createElement("datalist"); dl.id = "fxTagList";
  knownTags().forEach(function (t) { var o = document.createElement("option"); o.value = t; dl.appendChild(o); });
  s.appendChild(dl);
  cfg.conditions.forEach(function (c, i) {
    var box = sec(s, "Condition " + (i + 1) + ": " + (c.not ? "NOT " : "") + COND_LABEL[c.type], "a-cond", COND_HELP[c.type], "act");
    Object.keys(FXK.CONDITION_TYPES[c.type]).forEach(function (k) { condField(box, c, k); });
    field(box, "Not (invert)", inp("chk", c.not, function (v) { c.not = v; ch(); })).title =
      "On: the condition counts as met when its check is FALSE (e.g. NOT target attacking).";
    var pv = document.createElement("div"); pv.className = "cpv mute"; pv.dataset.i = i; box.appendChild(pv);
    var row = document.createElement("div"); row.className = "row";
    var up = document.createElement("button"); up.textContent = "↑"; up.title = "Move up"; up.disabled = i === 0;
    up.onclick = function () { cfg.conditions.splice(i - 1, 0, cfg.conditions.splice(i, 1)[0]); ch(); };
    var dup = document.createElement("button"); dup.textContent = "Duplicate";
    dup.onclick = function () { cfg.conditions.splice(i + 1, 0, clone(c)); ch(); };
    var rm = document.createElement("button"); rm.textContent = "Remove"; rm.onclick = function () { cfg.conditions.splice(i, 1); ch(); };
    row.appendChild(up); row.appendChild(dup); row.appendChild(rm); box.appendChild(row);
  });
  var row = document.createElement("div"); row.className = "row";
  var sel = condSelect(), help = document.createElement("div"); help.className = "note";
  sel.onchange = function () { help.textContent = COND_HELP[sel.value]; };
  var add = document.createElement("button"); add.textContent = "+ Condition";
  add.onclick = function () { cfg.conditions.push(FXK.normalizeAction({conditions: [{type: sel.value}]}).conditions[0]); ch(); };
  row.appendChild(sel); row.appendChild(add); s.appendChild(row);
  help.textContent = COND_HELP[sel.value]; s.appendChild(help);
  if (!cfg.conditions.length) note(s, kind === "attack" ? "No conditions: it attacks whenever the target is in range." : "No conditions yet: this action never fires on its own.");
  // Live preview
  var p = sec(s, "Live preview", "a-cpv", "Test each condition: drag the target on the stage for distance and height, and set the values below for everything else. Each condition shows ✓ / ✗ and the result shows whether the action would fire (preview only, not saved).", "act");
  buildPrevInputs(p, cfg);
  var all = document.createElement("div"); all.id = "condAll"; all.className = "cpv"; p.appendChild(all);
  refreshCondPreview();
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
    var cont = FXK.isContinuous(fx);
    if (cont) b.className += " cont";
    var span = cont ? total - w[0] : (fx.life_ticks > 0 && !(fx.emit.every_ticks > 0)) ? fx.life_ticks : w[1] - w[0];
    b.style.left = (w[0] / total * W) + "px"; b.style.width = Math.max(4, span / total * W) + "px";
    b.title = fx.name + " — " + fx.prim + ", starts frame " + fx.start_frame;
    b.style.top = (18 + row * 15) + "px"; b.style.opacity = fx.enabled ? 1 : 0.4; b.textContent = (cont ? "∞ " : "") + fx.name;
    b.dataset.fx = fx.id;   // selected on release by the timeline's pointer handler
    tl.appendChild(b);
    (fx.keys || []).forEach(function (k, ki) {
      var dm = document.createElement("div");
      dm.className = "tlkey" + (fx.id === S.sel && k.frame === frameAt(S.t) ? " sel" : "");
      dm.style.left = (Math.round(k.frame * frameMs() / FXK.TICK_MS) / total * W - 5) + "px"; dm.style.top = (18 + row * 15 + 1) + "px";
      dm.title = fx.name + " key at frame " + k.frame + " (" + EASE_LABEL[k.ease] + "): " + (Object.keys(k.set).map(keyLabel).join(", ") || "nothing yet");
      dm.dataset.fx = fx.id; dm.dataset.key = ki;
      tl.appendChild(dm);
    });
  });
  placeHead();
}
function placeHead() { var W = $("timeline").clientWidth || 600; $("playhead").style.left = (Math.min(S.t, totalTicks()) / totalTicks() * W) + "px"; }

// ------------------------------------------------------------ simulation
// Scrubbing re-simulates deterministically from tick 0, so a paused frame
// shows exactly what that tick looks like during playback.
function resetSim(t) {
  player.reset(); S.figX = 0; S.figY = 0; S.vel = moveVector(); S.t = 0; S.cycle = 0; S.hits = []; S.dealt = 0; S.blink = null;
  S.shots = []; S.ricochets = []; S.bursts = []; S.clock = 0;
  var target = Math.max(0, Math.min(t, totalTicks() - 1));
  blinkStep();
  while (S.t < target) step(false);
}
function step(allowWrap) {
  if (!C) return;
  var gone = blinkGone();
  if (!gone) moveFigure();
  stepTestShots();
  var nLoops = FXK.animLoops(S.action, cfgOf(S.action)), lastPass = (S.cycle || 0) >= nLoops - 1;
  player.tick(actionEffects(), host, S.t, frames(), frameMs(), {continuous: (!lastPass || $("loop").checked) && !!cfgOf(S.action).fx_continuous, hold: gone});
  S.t += 1;
  if (S.t >= totalTicks() && allowWrap) {
    // Next pass of the animation (Animation loops); after the last pass the
    // action ends, and "loop" replays the whole action.
    if (!lastPass) { S.t = 0; S.cycle = (S.cycle || 0) + 1; }
    else if ($("loop").checked) { S.t = 0; S.cycle = 0; S.dealt = 0; S.hits = []; }
  }
  blinkStep();   // for the tick now on show (past the action's end: it reappears)
}
// Blink preview (the action's Blink): vanish when the frame on show enters
// the blink's frames, reappear at the landing spot once it leaves them (or
// the action ends).  Run for each new tick, so S.blink always matches S.t.  S.blink = {gone, from, to}; the Studio target has no
// facing, so behind / in front are the far / near side from the fighter.
function blinkGone() { return !!(S.blink && S.blink.gone); }
function blinkStep() {
  var b = cfgOf(S.action).blink, on = S.t < totalTicks() && FXK.blinkActive(b, frameAt(S.t), frames());
  if (on && !blinkGone()) S.blink = {gone: true, from: [S.figX, S.figY], to: null};
  else if (!on && blinkGone()) {
    var rnd = FXK.rng((S.cycle || 0) * 7919 + 17).uniform(0, 1);
    var to = FXK.blinkLanding(b, S.blink.from, S.target, null, facing(), rnd);
    S.figX = to[0]; S.figY = to[1]; S.blink.gone = false; S.blink.to = to;
  }
}
// Where the blink would land from here (drawn while it's gone).
function blinkPreviewLanding() {
  var b = cfgOf(S.action).blink, from = blinkGone() ? S.blink.from : [S.figX, S.figY];
  return FXK.blinkLanding(b, from, S.target, null, facing(), FXK.rng((S.cycle || 0) * 7919 + 17).uniform(0, 1));
}
function drawBlink(g, z, img) {
  var b = cfgOf(S.action).blink; if (!b.enabled) return;
  var col = isLight() ? "rgba(20,130,70," : "rgba(125,224,168,";
  var from = blinkGone() ? S.blink.from : S.blink && S.blink.to ? S.blink.from : [S.figX, S.figY];
  var to = blinkGone() || !(S.blink && S.blink.to) ? blinkPreviewLanding() : S.blink.to;
  g.save();
  if (blinkGone()) drawFrame(g, img, S.blink.from, facing(), 0.3, null, aimDeg());   // where it vanished
  g.setLineDash([3 / z, 3 / z]); g.strokeStyle = col + ".7)"; g.lineWidth = 1 / z;
  g.beginPath(); g.moveTo(from[0], from[1]); g.lineTo(to[0], to[1]); g.stroke();
  g.setLineDash([]); g.lineWidth = 1.5 / z; g.strokeStyle = col + ".95)";
  g.beginPath(); g.arc(to[0], to[1], 5, 0, 6.2832); g.stroke();
  g.fillStyle = col + ".95)"; g.font = (9 / z * 1.2) + "px sans-serif"; g.textAlign = "center";
  g.fillText(blinkGone() ? "gone \u2014 lands here" : S.blink && S.blink.to ? "blinked here" : "blink lands here", to[0], to[1] - 8);
  g.restore();
}
// ------------------------------------------------------------ test shots
// "test shots": a dummy enemy fires a projectile from the target marker at
// the fighter every TEST_SHOT_EVERY ticks, so the auto-projectile tracker
// (Intercept) can be previewed.  Deterministic from tick 0 like the rest of
// the sim.  Deflected ones fly off as ricochets: red when they now hurt
// their owner (the dummy), grey when harmless.
var TEST_SHOT_EVERY = 40, TEST_SHOT_SPEED = 4, TEST_SHOT_LIFE = 120, RICOCHET_LIFE = 60;
function stepTestShots() {
  S.clock = (S.clock || 0) + 1;
  S.shots = (S.shots || []).filter(function (q) { return !q.dead && q.age < TEST_SHOT_LIFE; });
  S.shots.forEach(function (q) { q.x += q.vx; q.y += q.vy; q.age += 1; });
  if ($("testShots").checked && S.clock % TEST_SHOT_EVERY === 1) {
    var d = [S.figX - S.target[0], S.figY - S.target[1]], m = Math.hypot(d[0], d[1]) || 1;
    S.shots.push({x: S.target[0], y: S.target[1], vx: d[0] / m * TEST_SHOT_SPEED, vy: d[1] / m * TEST_SHOT_SPEED, age: 0, dead: false});
  }
  S.ricochets = (S.ricochets || []).filter(function (q) { return q.age < RICOCHET_LIFE; });
  S.ricochets.forEach(function (q) { q.trail.push([q.x, q.y]); if (q.trail.length > 6) q.trail.shift(); q.x += q.vx; q.y += q.vy; q.age += 1; });
  S.bursts = (S.bursts || []).filter(function (q) { return q.age < 14; });
  S.bursts.forEach(function (q) { q.age += 1; });
}
function drawTestShots(g, z) {
  (S.shots || []).forEach(function (q) {
    if (q.dead) return;
    g.fillStyle = "rgba(255,70,70,.95)"; g.beginPath(); g.arc(q.x, q.y, 2.5, 0, 6.2832); g.fill();
    g.strokeStyle = "rgba(255,70,70,.4)"; g.lineWidth = 1 / z; g.beginPath(); g.moveTo(q.x, q.y); g.lineTo(q.x - q.vx * 3, q.y - q.vy * 3); g.stroke();
  });
  (S.ricochets || []).forEach(function (q) {
    var a = 1 - q.age / RICOCHET_LIFE, col = q.hurts ? "255,90,60" : "170,175,190";
    g.strokeStyle = "rgba(" + col + "," + (a * .5) + ")"; g.lineWidth = 1 / z; g.beginPath();
    q.trail.forEach(function (p, i) { if (i) g.lineTo(p[0], p[1]); else g.moveTo(p[0], p[1]); }); g.lineTo(q.x, q.y); g.stroke();
    g.fillStyle = "rgba(" + col + "," + a + ")"; g.beginPath(); g.arc(q.x, q.y, 2.5, 0, 6.2832); g.fill();
  });
  (S.bursts || []).forEach(function (q) {
    var a = 1 - q.age / 14, col = q.mode === "block" ? "240,194,74" : q.mode === "destroy" ? "255,90,90" : "125,224,168";
    g.strokeStyle = "rgba(" + col + "," + a + ")"; g.lineWidth = 1.5 / z;
    g.beginPath(); g.arc(q.x, q.y, 3 + q.age * 0.8, 0, 6.2832); g.stroke();
  });
}
// ------------------------------------------------------------ direction sim
// The figure travels at "move" px/tick toward "dir" degrees (0 right, 90
// down, -90 up) inside a 320 x 200 px area, bouncing off its edges or
// wrapping to the far side.  FX react as they do in the game: attached
// effects ride along, ribbons and ghosts stretch out behind, and spawned
// projectiles and particles keep their own world-space paths.
var AREA = [160, 100];
function moveVector() {
  var spd = +$("walk").value || 0, a = (+$("moveDir").value || 0) * Math.PI / 180;
  return [Math.cos(a) * spd, Math.sin(a) * spd];
}
// The action's Movement setting scales the sim (idle and run keep the sim's
// full speed so their FX can still be previewed in motion).
function simMoveFactor() { return FXK.actionKind(S.action) === "locomotion" ? 1 : FXK.moveFactor(S.action, cfgOf(S.action)); }
var BACK_BASE_SPEED = 2;   // px/tick "normal speed" for the back-away preview when the sim's move is 0
function moveFigure() {
  var cfg = cfgOf(S.action);
  if (FXK.actionKind(S.action) !== "locomotion" && cfg.movement === "back") {
    var nL = FXK.animLoops(S.action, cfg), done = ((S.cycle || 0) * totalTicks() + S.t) / (nL * totalTicks());
    if (done >= (+cfg.back_stop_pct || 0) / 100) return;
    var bx = S.figX - S.target[0], by = S.figY - S.target[1], d = Math.hypot(bx, by);
    if (d < 1e-3) { bx = -facing(); by = 0; d = 1; }
    var spd = (+$("walk").value || BACK_BASE_SPEED) * FXK.moveFactor(S.action, cfg);
    S.figX += bx / d * spd; S.figY += by / d * spd;
    return;
  }
  var v = S.vel, f = simMoveFactor();
  if ((!v[0] && !v[1]) || f <= 0) return;
  S.figX += v[0] * f; S.figY += v[1] * f;
  var wrap = $("moveMode").value === "wrap";
  [0, 1].forEach(function (i) {
    var key = i ? "figY" : "figX", lim = AREA[i];
    if (Math.abs(S[key]) <= lim) return;
    if (wrap) S[key] = S[key] > 0 ? -lim : lim;
    else { S[key] = Math.max(-lim, Math.min(lim, S[key])); v[i] = -v[i]; }
  });
}
function drawMoveGuide(g, z) {
  var v = S.vel; if ((!v[0] && !v[1]) || simMoveFactor() <= 0 || cfgOf(S.action).movement === "back") return;
  g.save();
  g.strokeStyle = "rgba(125,224,168,.25)"; g.lineWidth = 1 / z; g.setLineDash([4 / z, 4 / z]);
  g.strokeRect(-AREA[0], -AREA[1], AREA[0] * 2, AREA[1] * 2); g.setLineDash([]);
  var m = Math.hypot(v[0], v[1]), ux = v[0] / m, uy = v[1] / m, L = 22, x = S.figX, y = S.figY;
  g.strokeStyle = "rgba(125,224,168,.85)"; g.fillStyle = g.strokeStyle; g.lineWidth = 2 / z;
  g.beginPath(); g.moveTo(x, y); g.lineTo(x + ux * L, y + uy * L); g.stroke();
  g.beginPath(); g.moveTo(x + ux * (L + 6), y + uy * (L + 6));
  g.lineTo(x + ux * L - uy * 4, y + uy * L + ux * 4); g.lineTo(x + ux * L + uy * 4, y + uy * L - ux * 4); g.fill();
  g.restore();
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
  refreshCondPreview();
  refreshKeyAdd();
}

// ------------------------------------------------------------ render
function fit() { var r = cv.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1); var w = Math.round(r.width * dpr), h = Math.round(r.height * dpr); if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; } return dpr; }
function zoom() { return Math.max(0.25, +$("zoom").value || 4); }
// A "Move back from target" action travels further than the stage shows:
// the camera follows the figure while it plays.
function camFollow() { return C && S.action && FXK.actionKind(S.action) !== "locomotion" && cfgOf(S.action).movement === "back"; }
function camera(dpr) {
  var z = zoom(), fx = camFollow() ? S.figX * z : 0, fy = camFollow() ? S.figY * z : 0;
  return {x: cv.width / 2 / dpr + S.pan[0] - fx, y: cv.height * 0.55 / dpr + S.pan[1] - fy, z: z};
}
function toWorld(mx, my) { var dpr = Math.min(2, window.devicePixelRatio || 1), c = camera(dpr); return [(mx - c.x) / c.z, (my - c.y) / c.z]; }
// ------------------------------------------------------------ light / dark mode
// Light mode: white page and stage, black text (remembered per browser).
// Stage guides switch to dark ink so they stay visible on white.
function isLight() { return document.documentElement.dataset.theme === "light"; }
function applyTheme(light) {
  if (light) document.documentElement.dataset.theme = "light"; else delete document.documentElement.dataset.theme;
  var b = $("bTheme"); if (b) b.textContent = light ? "☾ Dark mode" : "☀ Light mode";
  lsSet("pbfxstudio.v1.theme", light ? "light" : "dark");
}
function ink(a) { return (isLight() ? "rgba(0,0,0," : "rgba(255,255,255,") + a + ")"; }
function draw() {
  var dpr = fit(); g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, cv.width, cv.height);
  if (!C || !act()) return;
  var c = camera(dpr), z = c.z;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.strokeStyle = ink(isLight() ? .07 : .04); g.lineWidth = 1;   // grid: one line per 10 game px
  var step10 = 10 * z, x0 = ((c.x % step10) + step10) % step10, y0 = ((c.y % step10) + step10) % step10;
  for (var x = x0; x < cv.width / dpr; x += step10) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, cv.height); g.stroke(); }
  for (var y = y0; y < cv.height / dpr; y += step10) { g.beginPath(); g.moveTo(0, y); g.lineTo(cv.width, y); g.stroke(); }
  g.translate(c.x, c.y); g.scale(z, z);
  var ps = pscale(), fr = frameAt(S.t), img = act().images[fr];
  if ($("lightbg").checked) { g.save(); g.translate(S.figX, S.figY); g.rotate(aimDeg() * Math.PI / 180); g.fillStyle = "rgba(235,238,244,.9)"; var k = imgScale() * ps; g.fillRect(-C.origin[0] * k, -C.origin[1] * k, img.naturalWidth * k, img.naturalHeight * k); g.restore(); }
  var gone = blinkGone();
  player.draw(g, host, "behind", ps, gone);
  if (!gone) drawFrame(g, img, [S.figX, S.figY], facing(), null, null, aimDeg());
  player.draw(g, host, "front", ps, gone);
  drawBlink(g, z, img);
  drawTestShots(g, z);
  drawMoveGuide(g, z);
  drawGeo(g, z);
  drawGroup(g, z);
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
    if (j === S.selAnchor || show) { g.fillStyle = isLight() ? "rgba(0,0,0,.85)" : "rgba(220,230,240,.8)"; g.font = (9 / z) + "px sans-serif"; g.fillText(S.labels[j], q[0] + 5 / z, q[1] - 4 / z); }
  });
  if (S.selAnchor) {   // the anchor's path over the whole action
    g.strokeStyle = "rgba(125,224,168,.35)"; g.lineWidth = 1 / z; g.beginPath();
    for (var f = 0; f < frames(); f++) { var pp = resolveAnchor(S.action, S.selAnchor, f); if (!pp) continue; var w = imgToGame(pp); if (f) g.lineTo(w[0], w[1]); else g.moveTo(w[0], w[1]); }
    g.stroke();
  }
  var nL = FXK.animLoops(S.action, cfgOf(S.action));
  $("hud").textContent = S.action + (nL > 1 ? "   loop " + Math.min(nL, (S.cycle || 0) + 1) + "/" + nL : "") + "   frame " + fr + "/" + (frames() - 1) + "   tick " + S.t + "/" + totalTicks() +
    "   " + Math.round(frameMs() * 10) / 10 + " ms/frame   " + player.insts.length + " live FX   damage this loop " + S.dealt + " HP" +
    ((S.vel[0] || S.vel[1]) && simMoveFactor() <= 0 ? "   stands still (Movement)" : "") +
    (blinkGone() ? "   BLINKED OUT" : "") +
    (S.geoPlace && geoItem() ? "   PLACING " + (S.geo.kind === "set" ? "entry points" : "path points") + " for \"" + geoItem().name + "\": click the stage" : "") +
    (S.place && S.selAnchor ? "   PLACING \"" + S.labels[S.selAnchor] + "\": click the figure" : "");
  $("frameInfo").textContent = "frame " + fr;
  placeHead();
}

// The selected group: its pivot, a line to each member, a dashed box round
// them and the ▣ handle (drag it, or Shift+drag anywhere, to move the group).
function drawGroup(g, z) {
  var gr = !S.sel && selGroup(); if (!gr) return;
  var c = groupCentre(gr); if (!c) return;
  var pv = jointAt(gr.anchor, frameAt(S.t)), spots = groupMembers(gr).map(fxSpot);
  var x0 = c[0], y0 = c[1], x1 = c[0], y1 = c[1];
  g.strokeStyle = "rgba(125,224,168,.55)"; g.lineWidth = 1 / z; g.beginPath();
  spots.forEach(function (p) { g.moveTo(pv[0], pv[1]); g.lineTo(p[0], p[1]); x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]); x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]); });
  g.stroke();
  var pad = 6 / z; g.setLineDash([4 / z, 3 / z]); g.strokeRect(x0 - pad, y0 - pad, x1 - x0 + pad * 2, y1 - y0 + pad * 2); g.setLineDash([]);
  g.fillStyle = "#7de0a8"; g.beginPath(); g.arc(pv[0], pv[1], 3 / z, 0, 6.2832); g.fill();
  var h = 5 / z; g.fillStyle = "rgba(125,224,168,.9)"; g.fillRect(c[0] - h, c[1] - h, h * 2, h * 2);
  g.strokeStyle = isLight() ? "#000" : "#0b0d11"; g.strokeRect(c[0] - h, c[1] - h, h * 2, h * 2);
  g.fillStyle = isLight() ? "rgba(0,0,0,.85)" : "rgba(220,230,240,.85)"; g.font = (9 / z) + "px sans-serif";
  g.fillText("▣ " + gr.name + " on " + (S.labels[gr.anchor] || gr.anchor), x0 - pad, y0 - pad - 3 / z);
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
$("contFx").onchange = function () {
  if (!C) { this.checked = false; return; }
  cfgOf(S.action).fx_continuous = this.checked; save(); buildProps();
  toast(this.checked ? "FX keep running when " + S.action + " loops" : "FX restart each time " + S.action + " loops");
};
$("bTheme").onclick = function () { applyTheme(!isLight()); draw(); };
applyTheme(lsGet("pbfxstudio.v1.theme") === "light");
$("bUndo").onclick = undo; $("bRedo").onclick = redo; histUI();
$("bAdd").onclick = function () {
  if (!C) return toast("Open a character folder first");
  var fx = FXK.newEffect($("newPrim").value, S.action);
  fx.flip.facing = S.target[0] < S.figX - 0.001 ? -1 : 1;   // Flip: the side the target was on when it was created
  if (fx.prim === "ghost") fx.layer = "behind";
  if (["arc", "beam", "sprite"].indexOf(fx.prim) >= 0) { fx.motion.kind = "travel"; fx.life_ticks = fx.prim === "arc" ? 5 : 60; }
  if (fx.prim === "particles") { fx.motion.kind = "static"; fx.life_ticks = 1; }
  if (fx.prim === "weapon") {
    fx.name = "Weapon hitbox"; fx.battle.deals_damage = true;
    fx.anchor = S.labels.haR ? "haR" : anchorIds()[0] || "figure";
    fx.params.to_anchor = S.labels.wtip ? "wtip" : anchorIds()[1] || fx.anchor;
  }
  S.effects.push(fx); S.sel = fx.id; S.geo = null; S.geoPlace = false; rebuild(); resetSim(S.t); save();
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
$("bEntryAdd").onclick = function () { if (!C) return toast("Open a character folder first"); geoNew("set", {name: "Entry set " + (S.entries.length + 1)}); S.geoPlace = true; geoTools(); buildProps(); toast("Click the stage around the figure to place entry points"); };
$("bPathAdd").onclick = function () { if (!C) return toast("Open a character folder first"); geoNew("path", {name: "Path " + (S.paths.length + 1)}); S.geoPlace = true; geoTools(); buildProps(); toast("Click the stage to draw the path's points, starting from the figure"); };
$("bGeoPlace").onclick = function () { if (!geoItem()) return; S.geoPlace = !S.geoPlace; geoTools(); buildProps(); };
$("geoPreset").onchange = geoPresetDesc;
$("bGeoPreset").onclick = function () {
  if (!C) return toast("Open a character folder first");
  var x = geoAllPresets()[+$("geoPreset").value]; if (!x) return;
  geoNew(x.p.kind, x.p.item); toast("Added " + (x.p.kind === "set" ? "entry set" : "path") + " \"" + x.p.item.name + "\"");
};
$("bGeoPresetDel").onclick = function () {
  var all = geoAllPresets(), x = all[+$("geoPreset").value]; if (!x || x.builtin) return;
  ask("Delete your preset \"" + x.p.item.name + "\"?", {ok: "Delete"}, function (ok) {
    if (!ok) return;
    var mine = geoUserPresets(), idx = mine.findIndex(function (m) { return JSON.stringify(m) === JSON.stringify(x.p); });
    if (idx >= 0) { mine.splice(idx, 1); lsSet(LS_GEO, mine); }
    geoRefreshPresets();
  });
};
$("bGroup").onclick = makeGroup;
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
// Changing the facing turns the fighter toward the target, as the game does
// (the fighter faces its target while it acts): a target left behind is
// mirrored to the new front.
$("facing").addEventListener("change", function () {
  var f = +$("facing").value;
  if (S.target[0] * f < 0) S.target = [-S.target[0], S.target[1]];   // about the start position (x 0)
});
["facing", "walk", "moveDir", "moveMode", "faceMove", "pscale", "hurtR", "testShots"].forEach(function (id) { $(id).onchange = function () { resetSim(S.t); }; });
// Timeline scrubbing: press and drag with the left button to move the
// playhead (the view re-simulates to each tick, so FX show exactly as they
// play).  A press on an effect's bar selects it on release unless the
// pointer moved, in which case it scrubs.
(function () {
  var tl = $("timeline"), scrub = null, pending = null;
  function tickAt(x) { var r = tl.getBoundingClientRect(); return Math.round(Math.max(0, Math.min(1, (x - r.left) / r.width)) * totalTicks()); }
  function go(x) {
    pending = x;
    if (scrub.raf) return;
    scrub.raf = requestAnimationFrame(function () { if (scrub) { scrub.raf = 0; resetSim(tickAt(pending)); } });
  }
  tl.addEventListener("pointerdown", function (ev) {
    if (!C || ev.button !== 0) return;
    S.playing = false; $("bPlay").textContent = "▶ Play";
    var onKey = ev.target.classList.contains("tlkey"), onBar = onKey || ev.target.classList.contains("tlbar");
    scrub = {x0: ev.clientX, live: !onBar, raf: 0, bar: onBar ? ev.target.dataset.fx : null, key: onKey ? +ev.target.dataset.key : null};
    try { tl.setPointerCapture(ev.pointerId); } catch (e) {}
    if (scrub.live) go(ev.clientX);
    ev.preventDefault();
  });
  tl.addEventListener("pointermove", function (ev) {
    if (!scrub) return;
    if (!scrub.live && Math.abs(ev.clientX - scrub.x0) > 3) scrub.live = true;
    if (scrub.live) go(ev.clientX);
  });
  function end(ev) {
    if (!scrub) return;
    if (scrub.live) { if (scrub.raf) cancelAnimationFrame(scrub.raf); resetSim(tickAt(ev.clientX)); }
    else if (scrub.bar && scrub.key != null) { var kf = S.effects.filter(function (e) { return e.id === scrub.bar; })[0]; if (kf && kf.keys[scrub.key]) { S.geoPlace = false; editKey(kf, kf.keys[scrub.key].frame); buildGeo(); } }
    else if (scrub.bar) { S.sel = scrub.bar; S.geo = null; S.geoPlace = false; buildEffects(); buildGeo(); buildProps(); buildTimeline(); }
    scrub = null;
  }
  tl.addEventListener("pointerup", end);
  tl.addEventListener("pointercancel", end);
})();
window.addEventListener("resize", buildTimeline);
document.addEventListener("keydown", function (ev) {
  var mod = ev.ctrlKey || ev.metaKey, k = (ev.key || "").toLowerCase(), ae = document.activeElement;
  if (mod && (k === "z" || k === "y") && $("dlg").hidden) {
    // A text field keeps the browser's own typing undo; everything else is the Studio's.
    var typing = ae && (ae.tagName === "TEXTAREA" || (ae.tagName === "INPUT" && /^(text|search)$/i.test(ae.type)));
    if (!typing) { ev.preventDefault(); if (k === "y" || ev.shiftKey) redo(); else undo(); return; }
  }
  if (/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
  if (ev.code === "Space") { ev.preventDefault(); $("bPlay").click(); }
  if (ev.key === "Escape" && S.geoPlace) { S.geoPlace = false; geoTools(); buildProps(); }
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
  if (e.button === 0 && S.geoPlace && geoItem()) { geoPlaceAt(w); return; }
  if (e.button === 0 && S.place && S.selAnchor) {
    var fr = frameAt(S.t); anchorRow(S.action, S.selAnchor)[fr] = gameToImg(w);
    buildAnchors(); save();
    if ($("autoNext").checked && fr < frames() - 1) gotoFrame(fr + 1); else resetSim(S.t);
    return;
  }
  var gsel = e.button === 0 && !S.sel && selGroup(), gc = gsel && groupCentre(gsel);
  if (gc && (e.shiftKey || Math.hypot(w[0] - gc[0], w[1] - gc[1]) * zoom() <= 9)) {
    drag = {kind: "group", gr: gsel, last: w}; cv.setPointerCapture(e.pointerId); return;
  }
  drag = e.button === 0 ? {kind: "target"} : {kind: "pan", x: e.clientX, y: e.clientY, p: S.pan.slice()};
  if (drag.kind === "target") { S.target = w; if (!S.playing) resetSim(S.t); }
  cv.setPointerCapture(e.pointerId);
});
cv.addEventListener("pointermove", function (e) {
  if (!drag) return;
  var r = cv.getBoundingClientRect();
  if (drag.kind === "group") {
    var w = toWorld(e.clientX - r.left, e.clientY - r.top), lead = groupMembers(drag.gr)[0];
    if (lead) moveGroup(drag.gr, worldToLocal(lead, [w[0] - drag.last[0], w[1] - drag.last[1]]));
    drag.last = w; drag.moved = true; if (!S.playing) resetSim(S.t);
  }
  else if (drag.kind === "target") { S.target = toWorld(e.clientX - r.left, e.clientY - r.top); if (!S.playing) resetSim(S.t); }
  else S.pan = [drag.p[0] + e.clientX - drag.x, drag.p[1] + e.clientY - drag.y];
});
cv.addEventListener("pointerup", function () { var d = drag; drag = null; if (d && d.kind === "group" && d.moved) { buildProps(); save(); } });
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
window.FXStudio = {S: S, get C() { return C; }, openFiles: openFiles, packData: packData, resetSim: resetSim, step: step, player: player, host: host, rebuild: rebuild};
})();
