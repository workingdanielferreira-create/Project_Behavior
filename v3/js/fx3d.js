'use strict';
/* FX 3D runtime (Daniel 2026-11-24): FX Studio's 2D FX laid in the 3D world, shared by the V3 game (fxlive.js) and
   FX Studio 3D (tools/fxstudio3d.html). The FX keep their 2D anime look: FX Studio's own runtime (fxkit.js + style
   files, unchanged) plays and draws them, and each effect is painted onto a flat card PLACED in 3D (2.5D):
     - Every action gets its own "lane": an FXK.Player in a 2D frame locked when the action starts: origin = the
       fighter's body centre, 2D x = level toward the target (else the facing), 2D y = straight down. So shots fly at
       the target in a real vertical plane and keep flying where they were fired when the fighter moves on.
     - Anchors (haR, wtip, head ...) come from the 3D body's bones (RIG_SPEC section 3 map, Rig Forge 3D's pb_rig3d
       anchors, or any bone "bone:<Name>"), so FX start where the 3D hand / blade really is.
     - Each effect's `fx3d` block (fxkit.json, beside the 2D data) says how it lies: side (the vertical plane through
       the aim line), flat (horizontal at its height), ground (flat on the floor), billboard (faces the camera); plus
       tilt / yaw / pitch, pivot, a 3D offset, size, an ink edge and the hit depth.
     - Hits: every enemy whose body is within depth_m of the effect's plane is tested in that plane with FX Studio's
       own hit rules (FXK.resolveHits), one hit count per enemy (Daniel: "every enemy it touches").
   Per-action body movement in 3D (`action_settings[a].move3d`): start spot (stay / blink / dash to a spot round the
   target), then a path (line / leap / arc / zigzag / flank / hit & retreat) to an end spot round the target.
   Units here: metres, y up. */
(function (G) {
const THREE = G.THREE, FXK = G.FXK;
const D = Math.PI / 180;
const U = 1.8 / 28;                 // metres per 2D px (a 2D fighter stands 28 px = a 1.8 m body)
const HURT = 16;                    // 2D hurt radius in px (PROJ_HIT_RADIUS)
const MAX_TEX = 2048;
// FX Studio / Rig Forge anchor ids -> [bone, where on it, fallback bone] (v3/rig_spec.json "anchors")
const ANCHORS = {root: ['Hips', 'ground'], hip: ['Hips', 'head'], chest: ['Spine2', 'mid'], neck: ['Neck', 'head'], head: ['Head', 'mid'],
  shL: ['LeftArm', 'head'], shR: ['RightArm', 'head'], shB: ['Spine2', 'tail'], elL: ['LeftForeArm', 'head'], elR: ['RightForeArm', 'head'],
  haL: ['LeftHand', 'head'], haR: ['RightHand', 'head'], hpL: ['LeftUpLeg', 'head'], hpR: ['RightUpLeg', 'head'], knL: ['LeftLeg', 'head'],
  knR: ['RightLeg', 'head'], ftL: ['LeftFoot', 'head'], ftR: ['RightFoot', 'head'],
  wtip: ['WeaponTip_R', 'head', 'RightHandMiddle4'], wtip2: ['WeaponTip_L', 'head', 'LeftHandMiddle4']};
const LAYS = ['auto', 'side', 'flat', 'ground', 'billboard'];
const PIVOTS = ['spawn', 'figure'];
const DEF3D = {lay: 'auto', tilt_deg: 0, yaw_deg: 0, pitch_deg: 0, pivot: 'spawn', anchor: '', offset: [0, 0, 0], size_pct: 100, ink_px: 0, depth_m: 0.8};
const MOVE_PATHS = ['none', 'line', 'leap', 'arc', 'zigzag', 'flank', 'hit_retreat'];
const START_MODES = ['stay', 'blink', 'dash'];
const MOVE_EASES = ['inout', 'linear', 'in', 'out'];
const MOVE_DEFAULTS = {enabled: false, start_mode: 'stay', start_dist_m: 2.5, start_angle_deg: 0, start_height_m: 0, start_ms: 120,
  path: 'line', from_frame: 0, to_frame: -1, end_dist_m: 0.9, end_angle_deg: 0, end_height_m: 0, arc_m: 1.5, side: 'left', zigs: 3,
  ease: 'inout', face: 'target'};

function num(v, d) { v = +v; return isFinite(v) ? v : d; }
// An effect's 3D block with every field filled (the file keeps only what was set).
function cfg3d(fx) {
  const s = (fx && fx.fx3d) || {}, c = {};
  for (const k in DEF3D) c[k] = s[k] === undefined ? (Array.isArray(DEF3D[k]) ? DEF3D[k].slice() : DEF3D[k]) : s[k];
  if (LAYS.indexOf(c.lay) < 0) c.lay = 'auto';
  if (PIVOTS.indexOf(c.pivot) < 0) c.pivot = 'spawn';
  c.offset = [0, 1, 2].map(i => num((c.offset || [])[i], 0));
  ['tilt_deg', 'yaw_deg', 'pitch_deg', 'ink_px', 'depth_m'].forEach(k => { c[k] = num(c[k], DEF3D[k]); });
  c.size_pct = Math.max(1, num(c.size_pct, 100));
  c.anchor = typeof c.anchor === 'string' ? c.anchor : '';
  return c;
}
// auto: soft / round FX (glows, particles, rings, afterimages) face the camera, everything else lies in the aim plane
function autoLay(fx) { return ['glow', 'particles', 'pulse', 'ghost'].indexOf(fx.prim) >= 0 ? 'billboard' : 'side'; }
function layOf(fx, c) { c = c || cfg3d(fx); return c.lay === 'auto' ? autoLay(fx) : c.lay; }
function moveCfg(m) { const c = {}; m = m || {}; for (const k in MOVE_DEFAULTS) c[k] = m[k] === undefined ? MOVE_DEFAULTS[k] : m[k]; return c; }
// effects of a fxkit file, per action, normalised (runtime copies; the 3D anchor rides as "3d:<id>")
function byAction(F) {
  const by = {};
  for (const raw of (F && F.effects) || []) {
    if (raw.enabled === false || !raw.action) continue;
    let e; try { e = FXK.normalize(JSON.parse(JSON.stringify(raw))); } catch (err) { continue; }
    e._c3 = cfg3d(raw); if (e._c3.anchor) e.anchor = '3d:' + e._c3.anchor;
    (by[e.action] || (by[e.action] = [])).push(e);
  }
  return by;
}

/* ---------------------------------------------------------------- ink-edged card material */
const INK_FRAG = [
  '#ifdef USE_MAP',
  'vec4 texelColor = texture2D( map, vUv );',
  'if ( uInk > 0.0 ) {',
  '  float m = 0.0;',
  '  for ( int i = 0; i < 8; i ++ ) { float an = float( i ) * 0.7853982; m = max( m, texture2D( map, vUv + vec2( cos( an ), sin( an ) ) * uTexel * uInk ).a ); }',
  '  float e = clamp( ( m - texelColor.a ) * 1.6, 0.0, 1.0 ) * step( 0.2, m );',
  '  texelColor += vec4( 0.02, 0.027, 0.05, 1.0 ) * e * ( 1.0 - texelColor.a );',
  '}',
  'texelColor = mapTexelToLinear( texelColor );',
  'diffuseColor *= texelColor;',
  '#endif'].join('\n');
function makeCard(scene) {
  const cv = document.createElement('canvas'); cv.width = cv.height = 256;
  const tex = new THREE.CanvasTexture(cv); tex.premultiplyAlpha = true; tex.minFilter = THREE.LinearFilter; tex.generateMipmaps = false;
  const u = {uInk: {value: 0}, uTexel: {value: new THREE.Vector2(1 / 256, 1 / 256)}};
  const mat = new THREE.MeshBasicMaterial({map: tex, transparent: true, depthWrite: false, premultipliedAlpha: true, side: THREE.DoubleSide});
  mat.onBeforeCompile = sh => { sh.uniforms.uInk = u.uInk; sh.uniforms.uTexel = u.uTexel;
    sh.fragmentShader = 'uniform float uInk;\nuniform vec2 uTexel;\n' + sh.fragmentShader.replace('#include <map_fragment>', INK_FRAG); };
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), mat); mesh.renderOrder = 3; mesh.frustumCulled = false; scene.add(mesh);
  return {cv, ctx: cv.getContext('2d'), tex, mat, mesh, u, used: false};
}
function sizeCard(c, w, h) {
  const p2 = v => Math.min(MAX_TEX, Math.max(256, 1 << Math.ceil(Math.log2(Math.max(1, v)))));
  const W2 = p2(w), H2 = p2(h);
  if (c.cv.width < W2 || c.cv.height < H2 || c.cv.width > W2 * 4 || c.cv.height > H2 * 4) {
    c.cv.width = W2; c.cv.height = H2; c.tex.dispose(); c.u.uTexel.value.set(1 / W2, 1 / H2);
  }
}

/* ---------------------------------------------------------------- runner: one per fighter */
const _v = new THREE.Vector3(), _w = new THREE.Vector3(), _q = new THREE.Quaternion(), _qa = new THREE.Quaternion(), _m = new THREE.Matrix4();
const _cr = new THREE.Vector3(), _cu = new THREE.Vector3(), _cf = new THREE.Vector3();
const UPV = new THREE.Vector3(0, 1, 0);
/* o = {fx: fxkit json, palette {body, accent}, anchors3d: pb_rig3d anchors or null, scene,
        onHit(enemyRef, damage, knockback, inst), onHitstop(ticks), onShake(px)} */
function Runner(o) {
  this.o = o; this.by = byAction(o.fx); this.lanes = []; this.cards = []; this.ctx = null; this.cur = null;
  this.hurtNow = null; this.curEnemy = null; this.laneId = 0;
  const F = o.fx || {}, pal = o.palette || {}, rgb = h => FXK.hexRgb(h || '#ffffff', [255, 255, 255]), sp = F.space || {};
  this.lut = FXK.buildLut([rgb(pal.body), rgb(pal.accent)]);
  this.lib = {entry_sets: F.entry_sets || [], paths: F.paths || []};
  this.a2d = F.anchors || {}; this.origin = sp.image_origin_px || [240, 240];
  this.kImg = (+sp.game_px_per_image_px || 0.27) * (+F.character_scale || 1);
  const R = this;
  this.host = {
    get facing() { return R.cur ? R.cur.facing : 1; }, get target() { return R.cur ? R.cur.target : [40, 0]; },
    get hurt() { return R.hurtNow; }, get wang() { return 90; }, get lut() { return R.lut; }, get pscale() { return 1; },
    get lib() { return R.lib; }, get showHitboxes() { return false; }, get solo() { return !(R.ctx && R.ctx.target); },
    get shots() { return []; },
    anchor(n) { return R.anchor2d(n); },
    blinkPoint() { return null; }, snapshot() { return {}; }, outline() { return null; }, drawGhost() {},
    hitstop(n) { if (o.onHitstop) o.onHitstop(n); }, shake(px) { if (o.onShake) o.onShake(px); },
    onIntercept() {}, onDrag() {},
    onHit(inst, dmg, dx, dy, kb) { const e = R.curEnemy; if (e && o.onHit) o.onHit(e.ref, dmg, kb, inst); }};
}
Runner.prototype.reload = function (fx) { this.o.fx = fx; this.by = byAction(fx); };
Runner.prototype.reset = function () { this.lanes = []; this.cards.forEach(c => { c.mesh.visible = false; }); };
Runner.prototype.clear = function () {
  this.lanes = [];
  this.cards.forEach(c => { if (c.mesh.parent) c.mesh.parent.remove(c.mesh); c.tex.dispose(); c.mat.dispose(); c.mesh.geometry.dispose(); });
  this.cards = [];
};
Runner.prototype.liveCount = function () { let n = 0; this.lanes.forEach(l => { n += l.player.insts.length; }); return n; };
// world point -> a lane's 2D frame (px, y down)
Runner.prototype.toFrame = function (l, W) { _v.copy(W).sub(l.O); return [_v.dot(l.X) / U, -_v.dot(l.Y) / U]; };
Runner.prototype.boneHead = function (n, out) { const b = this.ctx && this.ctx.bone ? this.ctx.bone(n) : null; if (!b) return null; return b.getWorldPosition(out); };
Runner.prototype.boneTail = function (n, out) {
  const b = this.ctx && this.ctx.bone ? this.ctx.bone(n) : null; if (!b) return null;
  const c = b.children.find(x => x.isBone && !/^Weapon/.test(x.name)) || b.children.find(x => x.isBone);
  return c ? c.getWorldPosition(out) : b.getWorldPosition(out);
};
// a 3D anchor in world space, or null (not on this body)
Runner.prototype.anchorWorld = function (id, out) {
  out = out || new THREE.Vector3(); const ctx = this.ctx; if (!ctx || !id) return null;
  if (id === 'figure') return out.copy(ctx.centre);
  if (id === 'root' || id === 'ground') return out.copy(ctx.feet);
  const A3 = this.o.anchors3d && this.o.anchors3d[id];
  if (A3 && ctx.bone) {
    const b = ctx.bone(A3.bone);
    if (b) {
      const c = b.children.find(x => x.isBone && !/^Weapon/.test(x.name)) || b.children.find(x => x.isBone);
      out.set(0, 0, 0); if (c) out.copy(c.position).multiplyScalar(+A3.t || 0);
      const sd = A3.side || A3.off || [0, 0, 0]; out.x += +sd[0] || 0; out.y += +sd[1] || 0; out.z += +sd[2] || 0;
      b.updateWorldMatrix(true, false); b.localToWorld(out);
      if (A3.ground) out.y = ctx.feet.y;
      return out;
    }
  }
  if (id.indexOf('bone:') === 0) return this.boneHead(id.slice(5), out);
  const m = ANCHORS[id]; if (!m) return null;
  let p = this.boneHead(m[0], out);
  if (!p && m[2]) p = this.boneHead(m[2], out);
  if (!p) return null;
  if (m[1] === 'ground') out.y = ctx.feet.y;
  else if (m[1] === 'tail' || m[1] === 'mid') { const t = this.boneTail(m[0], _w); if (t) { if (m[1] === 'tail') out.copy(t); else out.lerp(t, 0.5); } }
  return out;
};
Runner.prototype.anchor2d = function (n) {
  const l = this.cur, ctx = this.ctx; if (!l || !ctx) return [0, 0];
  if (n === 'figure') return l.fig.slice();
  if (n === 'target') return l.target.slice();
  const id = typeof n === 'string' && n.indexOf('3d:') === 0 ? n.slice(3) : n;
  const W = this.anchorWorld(id, new THREE.Vector3());
  if (W) return this.toFrame(l, W);
  // a 2D-only anchor (coat tails, extra lines): the 2D drawing's own point, round the body centre
  const row = (this.a2d[l.name] || {})[id]; if (!row) return l.fig.slice();
  const fr = ctx.frame || 0; let p = null;
  for (let i = Math.min(fr, row.length - 1); i >= 0 && !p; i--) p = row[i];
  for (let j = fr + 1; j < row.length && !p; j++) p = row[j];
  return p ? [l.fig[0] + (p[0] - this.origin[0]) * this.kImg * l.facing, l.fig[1] + (p[1] - this.origin[1]) * this.kImg] : l.fig.slice();
};
Runner.prototype.newLane = function (key, name, a, ctx) {
  const X = new THREE.Vector3();
  if (ctx.target) X.copy(ctx.target.centre).sub(ctx.centre); X.y = 0;
  if (X.lengthSq() < 1e-6) X.copy(ctx.facing).setY(0);
  if (X.lengthSq() < 1e-6) X.set(0, 0, 1);
  X.normalize();
  const Y = UPV.clone(), L = new THREE.Vector3().crossVectors(X, Y).normalize();
  return {id: ++this.laneId, key, name, active: true, player: new FXK.Player(), t: 0, frames: a ? Math.max(1, a.frames | 0) : 1,
    frameMs: a ? Math.max(1, +a.frameMs || 16) : FXK.TICK_MS, O: ctx.centre.clone(), X, Y, L, groundY: num(ctx.groundY, 0),
    follow: !a, fig: [0, 0], figLat: 0, target: [40, 0], facing: 1};
};
Runner.prototype.laneLive = function (l, ctx) {
  if (l.follow && l.active && !l.player.insts.some(i => !FXK.bodyBound(i))) {   // idle / run auras ride the fighter
    l.O.copy(ctx.centre);
    const X = ctx.target ? _v.copy(ctx.target.centre).sub(ctx.centre).setY(0) : _v.copy(ctx.facing).setY(0);
    if (X.lengthSq() > 1e-6) { l.X.copy(X).normalize(); l.L.crossVectors(l.X, l.Y).normalize(); }
  }
  l.fig = this.toFrame(l, ctx.centre); l.figLat = _v.copy(ctx.centre).sub(l.O).dot(l.L);
  l.target = ctx.target ? this.toFrame(l, ctx.target.centre) : [40, 0];
  l.facing = l.target[0] - l.fig[0] < 0 ? -1 : 1;
};
/* One 16 ms tick. ctx = {centre, feet: Vector3 (world), facing: level unit Vector3, bone(name) -> Object3D | null,
   target: {centre} | null, enemies: [{centre, r (m), ref}], action: {key, name, frames, frameMs} | null,
   moving, gone, frame (2D frame index, for 2D-only anchors), groundY} */
Runner.prototype.tick = function (ctx) {
  this.ctx = ctx;
  const a = ctx.action, key = a ? a.key : ctx.moving ? '~run' : '~idle', name = a ? a.name : ctx.moving ? 'run' : 'idle';
  let lane = this.lanes.find(l => l.active);
  if (!lane || lane.key !== key) { if (lane) lane.active = false; lane = this.newLane(key, name, a, ctx); this.lanes.push(lane); }
  for (const l of this.lanes) {
    this.cur = l; this.laneLive(l, ctx); this.hurtNow = null;
    try { l.player.tick(l.active ? (this.by[l.name] || []) : [], this.host, l.t, l.frames, l.frameMs, {}); }
    catch (err) { console.error('fx3d tick', err); }
    l.t++;
    this.hits(l, ctx);
  }
  this.cur = null;
  this.lanes = this.lanes.filter(l => l.active || l.player.insts.length);
  while (this.lanes.length > 8) { const i = this.lanes.findIndex(l => !l.active); if (i < 0) break; this.lanes.splice(i, 1); }
};
Runner.prototype.initInst = function (l, inst) {
  if (inst._c) return;
  const src = inst.src || inst.fx; inst._c = src._c3 || cfg3d(src); inst._lay = layOf(inst.fx, inst._c);
  inst._pv = inst._c.pivot === 'figure' ? l.fig.slice() : [inst.x, inst.y];
  const an = typeof inst.fx.anchor === 'string' ? inst.fx.anchor.replace(/^3d:/, '') : '';
  const W = an && an !== 'figure' && an !== 'target' && this.ctx ? this.anchorWorld(an, new THREE.Vector3()) : null;
  inst._lat = W ? _v.copy(W).sub(l.O).dot(l.L) : l.figLat; inst._latF = l.figLat;
};
// where an instance's card lies: pivot (world), turn, metres per 2D px
Runner.prototype.xform = function (l, inst, out) {
  const c = inst._c, lay = inst._lay, Us = U * c.size_pct / 100;
  const lat = inst._lat + (FXK.bodyBound(inst) ? l.figLat - inst._latF : 0);
  const P = out.P.copy(l.O).addScaledVector(l.X, inst._pv[0] * U).addScaledVector(l.Y, -inst._pv[1] * U).addScaledVector(l.L, lat);
  if (lay === 'ground') P.y = l.groundY + 0.03;
  P.addScaledVector(l.X, c.offset[0]).addScaledVector(l.Y, c.offset[1]).addScaledVector(l.L, c.offset[2]);
  const roll = (lay === 'flat' || lay === 'ground' ? 90 : 0) + c.tilt_deg;
  out.q.setFromAxisAngle(l.Y, c.yaw_deg * D).multiply(_qa.setFromAxisAngle(l.L, c.pitch_deg * D)).multiply(_q.setFromAxisAngle(l.X, roll * D));
  out.Us = Us; out.bill = lay === 'billboard'; return out;
};
// an enemy body in an instance's plane: its 2D hurt circle, or null (too far from the plane)
Runner.prototype.hurtFor = function (l, inst, e, xf) {
  this.xform(l, inst, xf);
  const d = _w.copy(e.centre).sub(xf.P);
  if (!xf.bill) d.applyQuaternion(_q.copy(xf.q).invert());
  const n = Math.abs(d.dot(l.L)), tol = (xf.bill ? inst._c.depth_m * 2 : inst._c.depth_m) + (e.r || 0.4);
  if (n > tol) return null;
  return {x: inst._pv[0] + d.dot(l.X) / xf.Us, y: inst._pv[1] - d.dot(l.Y) / xf.Us, r: HURT * U / xf.Us};
};
Runner.prototype.hits = function (l, ctx) {
  const en = ctx.enemies || []; if (!en.length) return;
  const xf = {P: new THREE.Vector3(), q: new THREE.Quaternion(), Us: U, bill: false};
  for (const inst of l.player.insts.slice()) {
    const b = inst.fx.battle; if (!b || !b.deals_damage || inst.dead) continue;
    this.initInst(l, inst);
    const hb = inst._hb || (inst._hb = new Map());
    for (const e of en) {
      const h = this.hurtFor(l, inst, e, xf); if (!h) continue;
      let s = hb.get(e.ref); if (!s) { s = {hits: 0, lastHit: -1e9, ringHits: {}}; hb.set(e.ref, s); }
      const sv = [inst.hits, inst.lastHit, inst.ringHits];
      inst.hits = s.hits; inst.lastHit = s.lastHit; inst.ringHits = s.ringHits;
      this.hurtNow = h; this.curEnemy = e;
      try { FXK.resolveHits(inst, this.host, 1); } catch (err) { console.error('fx3d hit', err); }
      s.hits = inst.hits; s.lastHit = inst.lastHit; s.ringHits = inst.ringHits;
      inst.hits = sv[0]; inst.lastHit = sv[1]; inst.ringHits = sv[2];
      if (inst.dead) break;
    }
  }
  this.hurtNow = null; this.curEnemy = null;
};
/* Paint every live effect onto its card(s) and place them. cam = the THREE camera, H = drawing buffer height (px).
   opts.hidden: hide body-bound FX (blinked out). */
Runner.prototype.draw = function (cam, H, opts) {
  const ctx = this.ctx; this.cards.forEach(c => { c.used = false; });
  if (!ctx) { this.cards.forEach(c => { c.mesh.visible = false; }); return; }
  const hidden = !!(opts && opts.hidden), tanH = Math.tan(cam.fov * Math.PI / 360);
  _cr.set(1, 0, 0).applyQuaternion(cam.quaternion); _cu.set(0, 1, 0).applyQuaternion(cam.quaternion); _cf.set(0, 0, 1).applyQuaternion(cam.quaternion);
  const groups = new Map();
  for (const l of this.lanes) for (const inst of l.player.insts) {
    if (hidden && FXK.bodyBound(inst)) continue;
    this.initInst(l, inst);
    const src = inst.src || inst.fx, k = l.id + '|' + (src.id || src.name) + (inst._c.pivot === 'spawn' ? '|' + inst.seed + '|' + (inst.ep == null ? '' : inst.ep) : '');
    let g = groups.get(k); if (!g) { g = {l, insts: []}; groups.set(k, g); } g.insts.push(inst);
  }
  let ci = 0;
  const xf = {P: new THREE.Vector3(), q: new THREE.Quaternion(), Us: U, bill: false};
  for (const g of groups.values()) {
    const l = g.l, i0 = g.insts[0]; this.xform(l, i0, xf);
    let x0 = -40, y0 = -40, x1 = 40, y1 = 40;
    for (const i of g.insts) {
      const P = i.fx.params || {}, m = Math.min(1400, Math.max(60, +P.length || 0, +P.radius || 0, +P.r_end || 0, +P.span || 0) + 30);
      x0 = Math.min(x0, i.x - m); x1 = Math.max(x1, i.x + m); y0 = Math.min(y0, i.y - m); y1 = Math.max(y1, i.y + m);
      if (i.x2 != null) { x0 = Math.min(x0, i.x2 - m); x1 = Math.max(x1, i.x2 + m); y0 = Math.min(y0, i.y2 - m); y1 = Math.max(y1, i.y2 + m); }
    }
    x0 = Math.max(x0, -1600); y0 = Math.max(y0, -1600); x1 = Math.min(x1, 1600); y1 = Math.min(y1, 1600);
    const bw = x1 - x0, bh = y1 - y0, cx = x0 + bw / 2, cy = y0 + bh / 2, Us = xf.Us;
    // card centre + axes
    let ax, ay, sx = 1;
    if (xf.bill) { ax = _cr.clone(); ay = _cu.clone(); sx = l.X.dot(_cr) < 0 ? -1 : 1; }
    else { ax = l.X.clone().applyQuaternion(xf.q); ay = l.Y.clone().applyQuaternion(xf.q); }
    const C = xf.P.clone().addScaledVector(ax, (cx - i0._pv[0]) * Us * sx).addScaledVector(ay, -(cy - i0._pv[1]) * Us);
    const dist = Math.max(0.5, _w.copy(C).sub(cam.position).dot(_cf) * -1);
    let dens = Math.max(0.4, Math.min(3, H / (2 * tanH * dist) * Us)); dens = Math.min(dens, MAX_TEX / bw, MAX_TEX / bh);
    const cw = Math.ceil(bw * dens), ch = Math.ceil(bh * dens);
    const layers = xf.bill ? [['behind'], ['front']] : [['behind', 'front']];
    this.cur = l;
    layers.forEach((lays, li) => {
      const c = this.cards[ci] || (this.cards[ci] = makeCard(this.o.scene)); ci++; c.used = true;
      sizeCard(c, cw, ch); const q2 = c.ctx;
      q2.setTransform(1, 0, 0, 1, 0, 0); q2.clearRect(0, 0, c.cv.width, c.cv.height); q2.globalAlpha = 1; q2.globalCompositeOperation = 'source-over';
      q2.setTransform(dens, 0, 0, dens, -x0 * dens, -y0 * dens);
      const keep = l.player.insts; l.player.insts = g.insts;
      try { lays.forEach(ly => l.player.draw(q2, this.host, ly, 1, false)); } catch (err) { console.error('fx3d draw', err); }
      l.player.insts = keep;
      c.tex.repeat.set(cw / c.cv.width, ch / c.cv.height); c.tex.offset.set(0, 1 - ch / c.cv.height); c.tex.needsUpdate = true;
      c.u.uInk.value = Math.max(0, i0._c.ink_px);
      const m = c.mesh; m.visible = true;
      if (xf.bill) { m.quaternion.copy(cam.quaternion); m.position.copy(C).addScaledVector(_cf, li ? 0.38 : -0.38); }
      else { const az = new THREE.Vector3().crossVectors(ax, ay); m.quaternion.setFromRotationMatrix(_m.makeBasis(ax, ay, az)); m.position.copy(C); }
      m.scale.set(bw * Us * sx, bh * Us, 1);
    });
  }
  this.cur = null;
  this.cards.forEach(c => { if (!c.used) c.mesh.visible = false; });
};
/* Debug outline of where each live effect lies (FX Studio 3D): [{P (pivot), ax, ay, w, h, lay}] */
Runner.prototype.planes = function () {
  const out = [], xf = {P: new THREE.Vector3(), q: new THREE.Quaternion(), Us: U, bill: false};
  for (const l of this.lanes) for (const inst of l.player.insts) {
    this.initInst(l, inst); this.xform(l, inst, xf);
    out.push({P: xf.P.clone(), ax: l.X.clone().applyQuaternion(xf.q), ay: l.Y.clone().applyQuaternion(xf.q), lay: inst._lay, fx: inst.src || inst.fx});
  }
  return out;
};

/* ---------------------------------------------------------------- per-action body movement (move3d) */
function easeU(k, u) { u = Math.max(0, Math.min(1, u)); return k === 'linear' ? u : k === 'in' ? u * u : k === 'out' ? 1 - (1 - u) * (1 - u) : u * u * (3 - 2 * u); }
// a spot round the target T: dist from it, angle 0 = on the side S stands on, 180 = behind it; height over T's feet
function spotAround(T, S, dist, ang, h) {
  let dx = S.x - T.x, dz = S.z - T.z, l = Math.hypot(dx, dz); if (l < 1e-4) { dx = -1; dz = 0; l = 1; } dx /= l; dz /= l;
  const c = Math.cos(ang * D), s = Math.sin(ang * D);
  return new THREE.Vector3(T.x + (dx * c - dz * s) * dist, Math.max(0, T.y + h), T.z + (dx * s + dz * c) * dist);
}
/* cfg = move3d, S = the fighter's feet, T = the target's feet (world, m), frames / frameMs = the action's timing,
   rnd = random 0..1. Returns {at(ms, out) -> feet Vector3, total, face, P0, E, startEnd, t0, t1, samples(n)}. */
function movePlan(cfg, S, T, frames, frameMs, rnd) {
  const c = moveCfg(cfg), sgn = c.side === 'right' ? -1 : c.side === 'random' ? ((rnd || Math.random)() < 0.5 ? 1 : -1) : 1;
  S = S.clone(); T = T.clone();
  const total = Math.max(1, frames) * frameMs;
  const P0 = c.start_mode === 'stay' ? S.clone() : spotAround(T, S, num(c.start_dist_m, 2.5), num(c.start_angle_deg, 0) * sgn, num(c.start_height_m, 0));
  const startEnd = c.start_mode === 'dash' ? Math.max(16, num(c.start_ms, 120)) : 0;
  const E = c.path === 'none' ? P0.clone() : spotAround(T, P0, num(c.end_dist_m, 0.9), num(c.end_angle_deg, 0) * sgn, num(c.end_height_m, 0));
  let t0 = Math.max(0, num(c.from_frame, 0)) * frameMs, t1 = (num(c.to_frame, -1) < 0 ? frames : Math.min(frames, num(c.to_frame, frames))) * frameMs;
  t0 = Math.max(t0, startEnd); if (t1 <= t0) t1 = t0 + frameMs;
  const dx = E.x - P0.x, dz = E.z - P0.z, dl = Math.hypot(dx, dz) || 1, px = -dz / dl * sgn, pz = dx / dl * sgn, arc = num(c.arc_m, 1.5);
  const zigs = Math.max(1, Math.round(num(c.zigs, 3)));
  function path(u, out) {
    if (c.path === 'hit_retreat') { const v = u < 0.5 ? easeU(c.ease, u * 2) : 1 - easeU(c.ease, (u - 0.5) * 2); return out.copy(P0).lerp(E, v); }
    const v = easeU(c.ease, u); out.copy(P0).lerp(E, v);
    if (c.path === 'leap') out.y += arc * 4 * v * (1 - v);
    else if (c.path === 'arc') { const k = arc * Math.sin(Math.PI * v); out.x += px * k; out.z += pz * k; }
    else if (c.path === 'zigzag') { const k = arc * 0.5 * (2 / Math.PI) * Math.asin(Math.sin(Math.PI * zigs * v)); out.x += px * k; out.z += pz * k; }
    else if (c.path === 'flank') {   // round the target's side: quadratic curve through a point beside it
      const Cx = T.x + px * arc * 2, Cz = T.z + pz * arc * 2, w = 1 - v;
      out.x = w * w * P0.x + 2 * w * v * Cx + v * v * E.x; out.z = w * w * P0.z + 2 * w * v * Cz + v * v * E.z;
    }
    return out;
  }
  const endP = c.path === 'hit_retreat' ? P0 : E;
  function at(ms, out) {
    out = out || new THREE.Vector3();
    if (ms < startEnd) return out.copy(S).lerp(P0, easeU('out', ms / startEnd));
    if (c.path === 'none' || ms <= t0) return out.copy(P0);
    if (ms >= t1) return out.copy(endP);
    return path((ms - t0) / (t1 - t0), out);
  }
  function samples(n) { const pts = []; n = n || 48; for (let i = 0; i <= n; i++) pts.push(at(total * i / n)); return pts; }
  return {at, total, face: c.face, P0, E: endP, S, T, startEnd, t0, t1, samples, cfg: c, blink: c.start_mode === 'blink'};
}

G.FX3D = {U, HURT, ANCHORS, LAYS, PIVOTS, DEF3D, MOVE_DEFAULTS, MOVE_PATHS, START_MODES, MOVE_EASES,
  cfg3d, autoLay, layOf, moveCfg, byAction, Runner, movePlan, spotAround, easeU};
})(window);
