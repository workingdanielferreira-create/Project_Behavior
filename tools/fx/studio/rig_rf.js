/* FX Studio — Rig Forge rig (read-only port).
 *
 * Forward kinematics and figure drawing copied from tools/fx/rigforge.html
 * (joints(), drawFigure()) and tools/fx/rigforge_bake.py (draw_frame(),
 * extent(), weapon_poly()), so an imported Rig Forge pb_character plays here
 * exactly as Rig Forge shows it and exactly as the baked sprites look in-game.
 *
 * Space: Rig Forge "rig units", y down.  The bake step renders every frame
 * with rx zeroed (the engine moves the figure itself) around a common origin
 * (hip x = 0, y = centre of the idle bounding box).  RF.origin() reproduces
 * that origin, so joint positions from RF.jointTrack() line up 1:1 with the
 * baked sprite pixels.
 */
(function (G) {
"use strict";
var D = Math.PI / 180;
var PDEF = {rx:0,ry:0,rot:0,sp:0,sp2:0,hd:0,shlx:0,shly:0,shrx:0,shry:0,
  hplx:0,hply:0,hprx:0,hpry:0,lua:168,lfa:12,rua:192,rfa:-12,lth:8,lsh:10,
  rth:-8,rsh:12,luas:1,lfas:1,ruas:1,rfas:1,lths:1,lshs:1,rths:1,rshs:1,
  torsos:1,wp:0,wpx:4,wpy:0,wspin:0,wlen:1};
// id, a, b, b2, mid, width, far, kind  (rigforge_bake.LAYERS, default draw order)
var LAYERS = [
  ["far_upper_arm","shL","elL",null,null,0.94,true,"bone"],
  ["far_forearm","elL","haL",null,null,0.83,true,"bone"],
  ["far_thigh","hpL","knL",null,null,1.00,true,"bone"],
  ["far_shin","knL","ftL",null,null,0.88,true,"bone"],
  ["pelvis_girdle","hip","hpL","hpR",null,0.98,false,"pair"],
  ["lower_spine","hip","chest",null,null,1.24,false,"bone"],
  ["upper_spine","chest","neck",null,null,1.12,false,"bone"],
  ["shoulder_girdle","neck","shL","shR","shB",0.86,false,"pair"],
  ["head","neck","head",null,null,1,false,"head"],
  ["near_thigh","hpR","knR",null,null,1.10,false,"bone"],
  ["near_shin","knR","ftR",null,null,0.96,false,"bone"],
  ["near_upper_arm","shR","elR",null,null,1.00,false,"bone"],
  ["near_forearm","elR","haR",null,null,0.90,false,"bone"],
  ["weapon","haR","wtip",null,null,1,false,"weapon"]
];
// Anchor joints an effect can attach to (Rig Forge JOINTLBL + root).
var JOINTS = ["hip","chest","neck","head","shB","shL","shR","elL","elR",
  "haL","haR","hpL","hpR","knL","knR","ftL","ftR","wtip","root"];
var JOINT_LABEL = {hip:"hip centre",chest:"chest",neck:"neck",head:"head",
  shB:"shoulder base",shL:"far shoulder",shR:"near shoulder",elL:"far elbow",
  elR:"near elbow",haL:"far hand",haR:"near hand",hpL:"far hip",hpR:"near hip",
  knL:"far knee",knR:"near knee",ftL:"far foot",ftR:"near foot",
  wtip:"weapon tip",root:"above head"};

function sd(a, l) { return [Math.sin(a * D) * l, Math.cos(a * D) * l]; }
function su(a, l) { return [Math.sin(a * D) * l, -Math.cos(a * D) * l]; }
function add(p, v) { return [p[0] + v[0], p[1] + v[1]]; }
function pose(p) { var o = {}, k; for (k in PDEF) o[k] = PDEF[k]; for (k in p) if (typeof p[k] === "number") o[k] = p[k]; return o; }

function rigOf(ch) {
  var r = ch.rig || {}, b = r.bones || {}, pv = r.pivots || {};
  return {ua: num(b.ua, 30), fa: num(b.fa, 30), th: num(b.th, 38), sh: num(b.sh, 36),
    torso: num(b.torso, 54), head: num(b.head, 15),
    shx: num(pv.shoulder_x, 0), shy: num(pv.shoulder_y, 1), hipx: num(pv.hip_x, 0),
    hipy: num(pv.hip_y, 0), sep: num(pv.side_separation, 3)};
}
function num(v, d) { v = +v; return isFinite(v) ? v : d; }
function shapesOf(ch) {
  var w = ch.weapon || {};
  var sh = w.shapes || (w.points && w.points.length ? [w.points] : []);
  return sh.filter(function (s) { return s && s.length; });
}

// rigforge.html joints(): identical maths, arrays instead of {x,y}.
function joints(p, rig, shapes) {
  p = pose(p);
  var hipC = [p.rx + rig.hipx, p.ry + rig.hipy];
  var chest = add(hipC, su(p.sp, rig.torso * 0.55 * p.torsos));
  var neck = add(chest, su(p.sp + p.sp2, rig.torso * 0.45 * p.torsos));
  var head = add(neck, su(p.sp + p.sp2 + p.hd, rig.head * 1.30));
  var shB = [neck[0] + rig.shx, neck[1] + rig.shy];
  var shL = [shB[0] - rig.sep * 0.8 + p.shlx, shB[1] + p.shly];
  var shR = [shB[0] + rig.sep * 0.8 + p.shrx, shB[1] + p.shry];
  var hpL = [hipC[0] - rig.sep + p.hplx, hipC[1] + p.hply];
  var hpR = [hipC[0] + rig.sep + p.hprx, hipC[1] + p.hpry];
  var elL = add(shL, sd(p.lua, rig.ua * p.luas)), haL = add(elL, sd(p.lua + p.lfa, rig.fa * p.lfas));
  var elR = add(shR, sd(p.rua, rig.ua * p.ruas)), haR = add(elR, sd(p.rua + p.rfa, rig.fa * p.rfas));
  var knL = add(hpL, sd(p.lth, rig.th * p.lths)), ftL = add(knL, sd(p.lth + p.lsh, rig.sh * p.lshs));
  var knR = add(hpR, sd(p.rth, rig.th * p.rths)), ftR = add(knR, sd(p.rth + p.rsh, rig.sh * p.rshs));
  var root = [head[0], head[1] - rig.head * 2.4];
  var wang = p.rua + p.rfa + p.wp, wtip = haR;
  var all = [];
  shapes.forEach(function (s) { s.forEach(function (q) { all.push(q); }); });
  if (all.length > 2) {
    var tp = all.reduce(function (m, q) { return q[0] > m[0] ? q : m; }, all[0]);
    var wa = (wang - 90) * D, wca = Math.cos(wa), wsa = Math.sin(wa), wsy = Math.cos(p.wspin * D);
    var lx = (tp[0] - p.wpx) * p.wlen, ly = (tp[1] - p.wpy) * wsy;
    wtip = [haR[0] + lx * wca - ly * wsa, haR[1] + lx * wsa + ly * wca];
  }
  var out = {hip: hipC, root: root, shB: shB, hpL: hpL, hpR: hpR, wtip: wtip, chest: chest,
    neck: neck, head: head, shL: shL, shR: shR, elL: elL, haL: haL, elR: elR, haR: haR,
    knL: knL, ftL: ftL, knR: knR, ftR: ftR};
  if (p.rot) {
    var rc = Math.cos(p.rot * D), rs = Math.sin(p.rot * D);
    Object.keys(out).forEach(function (k) {
      var v = out[k], dx = v[0] - hipC[0], dy = v[1] - hipC[1];
      out[k] = [hipC[0] + dx * rc - dy * rs, hipC[1] + dx * rs + dy * rc];
    });
    out.hip = hipC; wang += p.rot;
  }
  out.wang = wang;
  return out;
}

// rigforge_bake.weapon_poly()
function weaponPolys(j, p, shapes) {
  p = pose(p);
  var wa = (j.wang - 90) * D, ca = Math.cos(wa), sa = Math.sin(wa);
  var sy = Math.cos(p.wspin * D);
  if (Math.abs(sy) < 0.035) sy = (sy < 0 ? -1 : 1) * 0.035;
  var hx = j.haR[0], hy = j.haR[1];
  return shapes.map(function (sh) {
    return sh.map(function (q) {
      var lx = (q[0] - p.wpx) * p.wlen, ly = (q[1] - p.wpy) * sy;
      return [hx + lx * ca - ly * sa, hy + lx * sa + ly * ca];
    });
  });
}

// rigforge_bake.extent()
function extent(p, rig, shapes) {
  var q = pose(p); q.rx = 0;
  var j = joints(q, rig, shapes), pts = [];
  Object.keys(j).forEach(function (k) { if (k !== "wang" && k !== "root" && k !== "wtip") pts.push(j[k]); });
  weaponPolys(j, q, shapes).forEach(function (poly) { pts = pts.concat(poly); });
  var r = rig.head + 3;
  var xs = pts.map(function (a) { return a[0]; }), ys = pts.map(function (a) { return a[1]; });
  return [Math.min.apply(null, xs) - 6, Math.max.apply(null, xs) + 6,
          Math.min.apply(null, ys) - r - 6, Math.max.apply(null, ys) + 6];
}

// Bake origin: hip x = 0, y = centre of the idle action's bounding box.
function origin(ch) {
  var rig = rigOf(ch), shapes = shapesOf(ch);
  var idle = ((ch.actions || {}).idle || {}).keyframes || [];
  if (!idle.length) {
    var first = Object.keys(ch.actions || {})[0];
    idle = first ? (ch.actions[first].keyframes || []) : [];
  }
  if (!idle.length) return [0, 0];
  var e = idle.map(function (p) { return extent(p, rig, shapes); });
  var y0 = Math.min.apply(null, e.map(function (x) { return x[2]; }));
  var y1 = Math.max.apply(null, e.map(function (x) { return x[3]; }));
  return [0, (y0 + y1) / 2];
}

// Per-frame joints in rig units relative to the bake origin, rx zeroed
// (the same space as the baked sprite, centre = origin).  Rounded to 0.01.
function jointTrack(ch) {
  var rig = rigOf(ch), shapes = shapesOf(ch), o = origin(ch), out = {};
  Object.keys(ch.actions || {}).forEach(function (name) {
    var a = ch.actions[name], kfs = a.keyframes || [];
    var frames = kfs.map(function (p) {
      var q = pose(p); q.rx = 0;
      var j = joints(q, rig, shapes), f = {};
      JOINTS.forEach(function (k) { f[k] = [r2(j[k][0] - o[0]), r2(j[k][1] - o[1])]; });
      f.wang = r2(j.wang);
      return f;
    });
    out[name] = {duration_ms: +a.duration_ms || 0, frames: frames,
      root_rx: kfs.map(function (p) { return r2(+p.rx || 0); }),
      root_ry: kfs.map(function (p) { return r2(+p.ry || 0); })};
  });
  return out;
}
function r2(v) { return Math.round(v * 100) / 100; }

function hexRgb(h, d) {
  if (typeof h !== "string") return d;
  h = h.replace("#", "");
  if (h.length !== 6) return d;
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

// rigforge_bake.draw_frame(): outline pass + fill per layer, far limbs at
// 82 % alpha, dark weapon with light rim.  `S` = canvas px per rig unit;
// the caller has already translated to the figure origin and mirrored for
// facing.  opt.tint = [r,g,b] draws a flat silhouette (afterimage ghosts).
function drawFigure(g, p, ch, S, opt) {
  opt = opt || {};
  var rig = rigOf(ch), shapes = shapesOf(ch), o = origin(ch);
  var q = pose(p); q.rx = 0;
  var j = joints(q, rig, shapes);
  var body = opt.tint || hexRgb((ch.palette || {}).body, [242, 244, 246]);
  var tf = function (v) { return [(v[0] - o[0]) * S, (v[1] - o[1]) * S]; };
  var alphaMul = opt.alpha == null ? 1 : opt.alpha;
  g.save();
  g.lineCap = "round"; g.lineJoin = "round";
  function seg(a, b, w, col) {
    a = tf(a); b = tf(b);
    g.strokeStyle = col; g.lineWidth = Math.max(1, w * S);
    g.beginPath(); g.moveTo(a[0], a[1]); g.lineTo(b[0], b[1]); g.stroke();
  }
  LAYERS.forEach(function (L) {
    var kind = L[7], far = L[6], w = L[5];
    var al = (far ? 0.82 : 1) * alphaMul;
    var col = "rgba(" + body[0] + "," + body[1] + "," + body[2] + "," + al + ")";
    var edge = "rgba(12,14,18," + al + ")";
    var Wl = (far ? 9.4 : 10.0) * w;
    var outline = !opt.tint;
    if (kind === "head") {
      var hq = tf(j.head);
      if (outline) { g.fillStyle = edge; g.beginPath(); g.arc(hq[0], hq[1], (rig.head + 1.4 / S * 2.2) * S, 0, 6.2832); g.fill(); }
      g.fillStyle = col; g.beginPath(); g.arc(hq[0], hq[1], rig.head * S, 0, 6.2832); g.fill();
    } else if (kind === "pair") {
      var hub = L[4] ? j[L[4]] : j[L[1]];
      var segs = (L[4] ? [[j[L[1]], hub]] : []).concat([[hub, j[L[2]]], [hub, j[L[3]]]]);
      if (outline) segs.forEach(function (s) { seg(s[0], s[1], Wl + 2.2, edge); });
      segs.forEach(function (s) { seg(s[0], s[1], Wl, col); });
    } else if (kind === "bone") {
      if (outline) seg(j[L[1]], j[L[2]], Wl + 2.2, edge);
      seg(j[L[1]], j[L[2]], Wl, col);
    } else {
      weaponPolys(j, q, shapes).forEach(function (pts) {
        if (pts.length < 3) return;
        g.beginPath();
        pts.forEach(function (v, i) { v = tf(v); if (i) g.lineTo(v[0], v[1]); else g.moveTo(v[0], v[1]); });
        g.closePath();
        g.fillStyle = opt.tint ? col : "rgba(27,29,32," + alphaMul + ")"; g.fill();
        if (!opt.tint) { g.strokeStyle = "rgba(225,232,240," + (210 / 255 * alphaMul) + ")"; g.lineWidth = Math.max(1, 1.6 * S); g.stroke(); }
      });
    }
  });
  g.restore();
}

// A file is a Rig Forge export when its keyframes are flat pose dicts and it
// carries rig.bones (the legacy wizard used {t, p} keyframes).
function inspect(ch) {
  if (!ch || ch.format !== "pb_character") return {ok: false, why: "Not a pb_character file (the format key must be \"pb_character\")."};
  var acts = ch.actions || {}, names = Object.keys(acts);
  if (!names.length) return {ok: false, why: "The file has no actions."};
  var legacy = names.some(function (n) { var k = (acts[n].keyframes || [])[0]; return k && typeof k === "object" && "p" in k; });
  if (legacy) return {ok: false, why: "This file uses the retired wizard's rig ({t, p} keyframes). Open it in Rig Forge and export it again."};
  var withFrames = names.filter(function (n) { return (acts[n].keyframes || []).some(function (k) { return k && Object.keys(k).length; }); });
  if (!withFrames.length) {
    var src = (ch.rigforge_bake || {}).source_json;
    return {ok: false, why: "This file only references baked sprites; its keyframes are empty." + (src ? " Open the Rig Forge source instead: " + src : "")};
  }
  if (!ch.rig || !ch.rig.bones) return {ok: false, why: "The file has no rig.bones block, so it is not a Rig Forge export."};
  return {ok: true};
}

G.RF = {PDEF: PDEF, JOINTS: JOINTS, JOINT_LABEL: JOINT_LABEL, rigOf: rigOf, shapesOf: shapesOf,
  joints: joints, weaponPolys: weaponPolys, origin: origin, jointTrack: jointTrack,
  drawFigure: drawFigure, inspect: inspect, hexRgb: hexRgb, pose: pose};
})(window);
