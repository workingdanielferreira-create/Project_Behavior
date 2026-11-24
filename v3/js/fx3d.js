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
   3D cel-shaded FX (Daniel 2026-11-24, "3D in shape, 2D in cell shading"): the foundational kinds are real 3D meshes
   instead of a drawing on a card, per effect `fx3d.render` (auto / 3d = 3D toon, card = the 2D drawing as before;
   auto = 3D for the kinds below, a card for the rest):
     - ribbon (laser trail): a tube along its trail, tapering to its tail; sprite orb / bolt: a sphere / capsule head
       with a laser streak, a tapered tube stretched away opposite the way it flies (longer the faster it goes)
     - beam: a tube (base -> head widths, wobble, side count) with a bulb at the head and a flare at the base
     - particles: 3D chunks (shards / balls) that spin and also spread out of the plane
     - glow (orb): a sphere; pulse (impact): an expanding shell + a flat shock ring + radial spikes
   Look = flat colour bands by how much the surface faces the camera (no gradients), a white-hot flat core where it faces
   the camera, a dark ink outline (inverted hull); every part tunable (fx3d toon_* / laser_* / beam_* / impact_* /
   chunk_*). Hits of a 3D effect use its 3D shape: an enemy's distance off the effect's plane is folded into the 2D
   hit test, so a sphere / tube hits whatever it touches in 3D (FX Studio's damage / re-hit / pierce rules kept).
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
const DEF3D = {lay: 'auto', tilt_deg: 0, yaw_deg: 0, pitch_deg: 0, pivot: 'spawn', anchor: '', offset: [0, 0, 0], size_pct: 100, ink_px: 0, depth_m: 0.8,
  render: 'auto', toon_bands: 3, toon_core_pct: 30, toon_shade_pct: 55, toon_core: '#ffffff', toon_ink_m: 0.02, toon_alpha_pct: 100, toon_sides: 12,
  laser_streak: 5, laser_max_m: 6, laser_width_pct: 85, beam_bulb_pct: 130, beam_flare_pct: 150, beam_wobble_pct: 8, beam_width_pct: 100,
  impact_shell: true, impact_shell_pct: 35, impact_ring: true, impact_spikes: 8, impact_spike_pct: 90, chunk_shape: 'shard', chunk_spread_pct: 60, chunk_size_pct: 120};
const RENDERS = ['auto', '3d', 'card'];
const CHUNKS = ['shard', 'ball', 'cube'];
const TOON_PRIMS = ['ribbon', 'beam', 'particles', 'glow', 'pulse'];
const TOON_NUMS = ['toon_bands', 'toon_core_pct', 'toon_shade_pct', 'toon_ink_m', 'toon_alpha_pct', 'toon_sides', 'laser_streak', 'laser_max_m',
  'laser_width_pct', 'beam_bulb_pct', 'beam_flare_pct', 'beam_wobble_pct', 'beam_width_pct', 'impact_shell_pct', 'impact_spikes', 'impact_spike_pct',
  'chunk_spread_pct', 'chunk_size_pct'];
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
  if (RENDERS.indexOf(c.render) < 0) c.render = 'auto';
  if (CHUNKS.indexOf(c.chunk_shape) < 0) c.chunk_shape = 'shard';
  TOON_NUMS.forEach(k => { c[k] = num(c[k], DEF3D[k]); });
  c.toon_bands = Math.max(1, Math.min(6, Math.round(c.toon_bands))); c.toon_sides = Math.max(3, Math.min(48, Math.round(c.toon_sides)));
  c.impact_spikes = Math.max(0, Math.min(48, Math.round(c.impact_spikes)));
  c.impact_shell = c.impact_shell !== false; c.impact_ring = c.impact_ring !== false;
  if (typeof c.toon_core !== 'string' || !/^#[0-9a-f]{6}$/i.test(c.toon_core)) c.toon_core = DEF3D.toon_core;
  return c;
}
// Does this effect draw as a 3D cel-shaded shape? (render 3d / auto for the foundational kinds; blades stay cards)
function is3d(fx, c) {
  c = c || cfg3d(fx); if (!fx || c.render === 'card') return false;
  if (fx.prim === 'sprite') return !(fx.params && fx.params.shape === 'blade');
  return TOON_PRIMS.indexOf(fx.prim) >= 0;
}
// auto: soft / round FX (glows, particles, rings, afterimages) face the camera, everything else lies in the aim plane
function autoLay(fx) { return ['glow', 'particles', 'pulse', 'ghost'].indexOf(fx.prim) >= 0 ? 'billboard' : 'side'; }
function layOf(fx, c) { c = c || cfg3d(fx); const l = c.lay === 'auto' ? autoLay(fx) : c.lay; return l === 'billboard' && is3d(fx, c) ? 'side' : l; }
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

/* ---------------------------------------------------------------- 3D cel-shaded shapes */
// Bands by how much the surface faces the camera; the facing middle = the white-hot core; uInk = the hull pass (ink).
// Tubes are a unit cylinder (y -0.5 tail .. 0.5 head) tapered in the shader (uR0 tail, uR1 head radius, metres).
const TOON_VS = [
  'uniform float uR0; uniform float uR1; uniform float uTaper; uniform float uInflate;',
  'varying vec3 vN; varying vec3 vV;',
  'void main() {',
  '  vec3 p = position;',
  '  if ( uTaper > 0.5 ) p.xz *= mix( uR0, uR1, clamp( p.y + 0.5, 0.0, 1.0 ) );',
  '  vec4 mv = modelViewMatrix * vec4( p, 1.0 );',
  '  vec3 n = normalize( normalMatrix * normal );',
  '  mv.xyz += n * uInflate;',
  '  vN = n; vV = normalize( -mv.xyz );',
  '  gl_Position = projectionMatrix * mv;',
  '}'].join('\n');
const TOON_FS = [
  'uniform vec3 uCol; uniform vec3 uShade; uniform vec3 uCore; uniform float uBands; uniform float uCoreT; uniform float uAlpha; uniform float uInk;',
  'varying vec3 vN; varying vec3 vV;',
  'void main() {',
  '  if ( uInk > 0.5 ) { gl_FragColor = vec4( 0.02, 0.027, 0.05, uAlpha ); return; }',
  '  float f = abs( dot( normalize( vN ), normalize( vV ) ) );',
  '  vec3 c;',
  '  if ( uCoreT > 0.0 && f >= 1.0 - uCoreT ) c = uCore;',
  '  else { float k = f / max( 0.001, 1.0 - uCoreT ); float i = min( uBands - 1.0, floor( k * uBands ) );',
  '    c = mix( uShade, uCol, uBands > 1.0 ? i / ( uBands - 1.0 ) : 1.0 ); }',
  '  gl_FragColor = vec4( c, uAlpha );',
  '}'].join('\n');
const GEO = {};
function toonGeo(kind, sides) {
  const k = kind + sides; if (GEO[k]) return GEO[k];
  let g;
  if (kind === 'tube') g = new THREE.CylinderGeometry(1, 1, 1, sides, 1, false);
  else if (kind === 'sph') g = new THREE.SphereGeometry(1, sides, Math.max(4, Math.round(sides * 0.7)));
  else if (kind === 'ring') g = new THREE.TorusGeometry(1, 0.045, 5, Math.max(12, sides * 3));
  else if (kind === 'shard') g = new THREE.OctahedronGeometry(1, 0);
  else if (kind === 'cube') g = new THREE.BoxGeometry(1.3, 1.3, 1.3);
  else g = new THREE.IcosahedronGeometry(1, 0);   // ball
  return (GEO[k] = g);
}
function toonUniforms(ink) {
  return {uCol: {value: new THREE.Color()}, uShade: {value: new THREE.Color()}, uCore: {value: new THREE.Color()}, uBands: {value: 3}, uCoreT: {value: 0.3},
    uAlpha: {value: 1}, uInk: {value: ink ? 1 : 0}, uR0: {value: 1}, uR1: {value: 1}, uTaper: {value: 0}, uInflate: {value: 0}};
}
function makeToon(scene, kind, sides) {
  const geo = toonGeo(kind, sides);
  const mk = ink => new THREE.ShaderMaterial({uniforms: toonUniforms(ink), vertexShader: TOON_VS, fragmentShader: TOON_FS,
    transparent: true, depthWrite: true, side: ink ? THREE.BackSide : THREE.FrontSide});
  const m = new THREE.Mesh(geo, mk(false)), h = new THREE.Mesh(geo, mk(true));
  m.renderOrder = 4; h.renderOrder = 5; m.frustumCulled = h.frustumCulled = false; scene.add(m); scene.add(h);
  return {key: kind + sides, m, h, used: false};
}
const _col = new THREE.Color(), _a = new THREE.Vector3(), _b = new THREE.Vector3(), _d = new THREE.Vector3(), _bx = new THREE.Matrix4();
function rgb01(c, out) { return out.setRGB(Math.max(0, Math.min(255, c[0])) / 255, Math.max(0, Math.min(255, c[1])) / 255, Math.max(0, Math.min(255, c[2])) / 255); }
// nearest point to (x, y) on the polyline pts [[x, y] ...]
function nearOnLine(pts, x, y) {
  let best = null, bd = Infinity;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[Math.min(pts.length - 1, i + 1)], dx = b[0] - a[0], dy = b[1] - a[1], L = dx * dx + dy * dy;
    const t = L > 1e-9 ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / L)) : 0, px = a[0] + dx * t, py = a[1] + dy * t;
    const d = (px - x) * (px - x) + (py - y) * (py - y); if (d < bd) { bd = d; best = [px, py]; }
  }
  return best;
}
// a sprite's motion this tick (px / tick): its velocity, else its last trail step
function spriteVel(inst) {
  let vx = +inst.vx || 0, vy = +inst.vy || 0;
  if (vx * vx + vy * vy < 1e-4 && inst.trail && inst.trail.length > 1) { const t = inst.trail, n = t.length; vx = t[n - 1][0] - t[n - 2][0]; vy = t[n - 1][1] - t[n - 2][1]; }
  return [vx, vy];
}

/* ---------------------------------------------------------------- runner: one per fighter */
const _v = new THREE.Vector3(), _w = new THREE.Vector3(), _q = new THREE.Quaternion(), _qa = new THREE.Quaternion(), _m = new THREE.Matrix4();
const _cr = new THREE.Vector3(), _cu = new THREE.Vector3(), _cf = new THREE.Vector3();
const UPV = new THREE.Vector3(0, 1, 0);
/* o = {fx: fxkit json, palette {body, accent}, anchors3d: pb_rig3d anchors or null, scene,
        onHit(enemyRef, damage, knockback, inst), onHitstop(ticks), onShake(px)} */
function Runner(o) {
  this.o = o; this.by = byAction(o.fx); this.lanes = []; this.cards = []; this.toons = []; this.ctx = null; this.cur = null;
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
Runner.prototype.reset = function () { this.lanes = []; this.cards.forEach(c => { c.mesh.visible = false; }); this.toons.forEach(t => { t.m.visible = t.h.visible = false; }); };
Runner.prototype.clear = function () {
  this.lanes = [];
  this.toons.forEach(t => { [t.m, t.h].forEach(x => { if (x.parent) x.parent.remove(x); x.material.dispose(); }); }); this.toons = [];
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
  const src = inst.src || inst.fx; inst._c = src._c3 || cfg3d(src); inst._r3 = is3d(inst.fx, inst._c); inst._lay = layOf(inst.fx, inst._c);
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
    if (inst._r3) { this.hits3d(l, inst, en, xf); continue; }
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
// The plane axes of an instance (after xform): along (2D x), up (2D -y), out of the plane.
Runner.prototype.axes = function (l, xf) {
  xf.ax = (xf.ax || new THREE.Vector3()).copy(l.X).applyQuaternion(xf.q); xf.ay = (xf.ay || new THREE.Vector3()).copy(l.Y).applyQuaternion(xf.q);
  xf.az = (xf.az || new THREE.Vector3()).copy(l.L).applyQuaternion(xf.q); return xf;
};
// 2D frame point (+ px out of the plane) -> world
Runner.prototype.w3 = function (inst, xf, x, y, z, out) {
  return out.copy(xf.P).addScaledVector(xf.ax, (x - inst._pv[0]) * xf.Us).addScaledVector(xf.ay, -(y - inst._pv[1]) * xf.Us).addScaledVector(xf.az, (z || 0) * xf.Us);
};
// The 2D point of the shape an enemy at (ex, ey) is measured from (null = nothing to hit now).
Runner.prototype.shapePoint = function (inst, ex, ey) {
  const p = inst.fx.prim;
  if (p === 'beam') { const b = FXK.beamSegs(inst, this.host, 1); if (!b) return null; return nearOnLine(b.segs.length > 1 && !(inst.fx.params.jitter > 0) ? [[b.tx, b.ty], [b.hx, b.hy]] : b.segs.reduce((a, q) => a.concat([[q[0], q[1]], [q[2], q[3]]]), []), ex, ey); }
  if (p === 'ribbon') { const h = inst.hist || []; return h.length ? nearOnLine(h, ex, ey) : null; }
  return [inst.x, inst.y];
};
// 3D hits: the enemy's distance off the plane (n) is folded into its 2D offset from the nearest point of the shape, so
// FX Studio's own 2D test measures the true 3D distance (exact for spheres round a point and tubes round a line).
Runner.prototype.hits3d = function (l, inst, en, xf) {
  this.xform(l, inst, xf); this.axes(l, xf);
  const hb = inst._hb || (inst._hb = new Map()), r = HURT * U / xf.Us;
  const fold = (S, ex, ey, nn) => { let dx = ex - S[0], dy = ey - S[1], d = Math.hypot(dx, dy); if (d < 1e-6) { dx = 0; dy = -1; d = 1; }
    const D3 = Math.hypot(d, nn); return {x: S[0] + dx / d * D3, y: S[1] + dy / d * D3, r}; };
  for (const e of en) {
    const dv = _d.copy(e.centre).sub(xf.P), ex = inst._pv[0] + dv.dot(xf.ax) / xf.Us, ey = inst._pv[1] - dv.dot(xf.ay) / xf.Us, nn = dv.dot(xf.az) / xf.Us;
    this.curEnemy = e;
    if (inst.fx.prim === 'particles') {   // each chunk is out of the plane by its own spread
      const keep = [], all = inst.parts || [];
      for (const q of all) {
        inst.parts = [q]; this.hurtNow = fold([q.x, q.y], ex, ey, nn - (q._lv || 0) * (q.age || 0));
        try { FXK.resolveHits(inst, this.host, 1); } catch (err) { console.error('fx3d hit', err); }
        if (inst.parts.length) keep.push(q);
      }
      inst.parts = keep; continue;
    }
    if (Math.abs(nn) > 4000) continue;
    const S = this.shapePoint(inst, ex, ey); if (!S) continue;
    let st = hb.get(e.ref); if (!st) { st = {hits: 0, lastHit: -1e9, ringHits: {}}; hb.set(e.ref, st); }
    const sv = [inst.hits, inst.lastHit, inst.ringHits];
    inst.hits = st.hits; inst.lastHit = st.lastHit; inst.ringHits = st.ringHits;
    this.hurtNow = fold(S, ex, ey, nn);
    try { FXK.resolveHits(inst, this.host, 1); } catch (err) { console.error('fx3d hit', err); }
    st.hits = inst.hits; st.lastHit = inst.lastHit; st.ringHits = inst.ringHits;
    inst.hits = sv[0]; inst.lastHit = sv[1]; inst.ringHits = sv[2];
    if (inst.dead) break;
  }
  this.hurtNow = null; this.curEnemy = null;
};
/* ---- drawing the 3D shapes ---- */
Runner.prototype.toon = function (kind, sides) {
  const key = kind + sides; let t = this.toons.find(x => !x.used && x.key === key);
  if (!t) { t = makeToon(this.o.scene, kind, sides); this.toons.push(t); }
  t.used = true; t.m.visible = t.h.visible = true; return t;
};
// colour / look onto a shape; rgb = [r, g, b] 0..255, alpha 0..1, ink = metres (0 = none)
Runner.prototype.paint = function (t, c, rgb, alpha, ink) {
  const a = Math.max(0, Math.min(1, alpha * c.toon_alpha_pct / 100));
  [t.m, t.h].forEach(x => { const u = x.material.uniforms;
    rgb01(rgb, u.uCol.value); u.uShade.value.copy(u.uCol.value).multiplyScalar(Math.max(0, c.toon_shade_pct) / 100);
    u.uCore.value.set(c.toon_core); u.uBands.value = c.toon_bands; u.uCoreT.value = Math.max(0, Math.min(0.95, c.toon_core_pct / 100)); u.uAlpha.value = a;
  });
  const ik = ink == null ? c.toon_ink_m : ink;
  // the colour pass draws first and keeps its depth when there is an ink outline, so the ink shell (drawn after) only
  // shows round the silhouette; a see-through shape with no ink (impact shell) never hides what is behind it
  t.m.material.depthWrite = a > 0.97 || ik > 0;
  t.h.material.uniforms.uInflate.value = Math.max(0, ik); t.h.visible = ik > 0 && a > 0.02; t.m.visible = a > 0.005;
  return t;
};
Runner.prototype.sphere = function (c, P, r, rgb, alpha, ink, scl) {
  const t = this.paint(this.toon('sph', c.toon_sides), c, rgb, alpha, ink);
  [t.m, t.h].forEach(x => { x.position.copy(P); x.quaternion.identity(); x.scale.set(r, r, r); x.material.uniforms.uTaper.value = 0; });
  if (scl) [t.m, t.h].forEach(x => { x.quaternion.copy(scl.q); x.scale.set(r * scl.x, r * scl.y, r * scl.z); });
  return t;
};
// tapered tube from A (radius r0) to B (radius r1)
Runner.prototype.tube = function (c, A, B, r0, r1, rgb, alpha, ink) {
  const L = _b.copy(B).sub(A).length(); if (L < 1e-4) return null;
  const t = this.paint(this.toon('tube', c.toon_sides), c, rgb, alpha, ink);
  _a.copy(_b).divideScalar(L); _q.setFromUnitVectors(UPV, _a);
  [t.m, t.h].forEach(x => { x.position.copy(A).addScaledVector(_a, L / 2); x.quaternion.copy(_q); x.scale.set(1, L, 1);
    const u = x.material.uniforms; u.uTaper.value = 1; u.uR0.value = Math.max(0, r0); u.uR1.value = Math.max(0, r1); });
  return t;
};
Runner.prototype.draw3d = function (l, inst, xf) {
  const fx = inst.fx, P = fx.params || {}, c = inst._c, Us = xf.Us, lut = this.lut;
  const col = FXK.colorPair(fx, lut)[0], ink = c.toon_ink_m, W = (x, y, z, o) => this.w3(inst, xf, x, y, z, o || new THREE.Vector3());
  const prim = fx.prim;
  if (prim === 'beam') {
    const b = FXK.beamSegs(inst, this.host, 1); if (!b) return;
    const wk = c.beam_width_pct / 100, wob = 1 + c.beam_wobble_pct / 100 * Math.sin(inst.age * 0.9 + (inst.seed || 0)), a = b.am;
    const segs = b.segs.length > 1 && !(P.jitter > 0) ? [[b.tx, b.ty, b.hx, b.hy, b.wT, b.wH]] : b.segs.map(q => [q[2], q[3], q[0], q[1], q[4], q[4]]);
    segs.forEach(q => this.tube(c, W(q[0], q[1]), W(q[2], q[3]), q[4] / 2 * Us * wk * wob, q[5] / 2 * Us * wk * wob, col, a, ink));
    if (c.beam_bulb_pct > 0) this.sphere(c, W(b.hx, b.hy), b.wH / 2 * Us * wk * wob * c.beam_bulb_pct / 100, col, a, ink);
    if (c.beam_flare_pct > 0) this.sphere(c, W(b.tx, b.ty), b.wT / 2 * Us * wk * wob * c.beam_flare_pct / 100, col, a, ink);
    return;
  }
  if (prim === 'ribbon') {   // laser trail: a tube along it, thick at the head, thinning to the tail
    const h = inst.hist || [], n = h.length; if (n < 2) return;
    const wk = c.laser_width_pct / 100, wAt = t => (P.taper ? P.w_tail + (P.w_head - P.w_tail) * t : P.w_head) / 2 * Us * wk, al = Math.max(0, Math.min(1, (+P.alpha || 255) / 255));
    let prev = W(h[0][0], h[0][1]);
    for (let i = 1; i < n; i++) { const cur = W(h[i][0], h[i][1]); this.tube(c, prev, cur, wAt((i - 1) / n), wAt(i / n), col, al, ink); prev = cur; }
    this.sphere(c, prev, wAt(1) * 1.15, col, al, ink);
    return;
  }
  if (prim === 'sprite') {   // orb / bolt: a head + a laser streak stretched opposite its motion
    if (inst.age >= inst.life) return;
    const fade = P.fade ? Math.max(0, 1 - inst.age / inst.life) : 1, r = Math.max(0.5, +P.radius || 3) * Us * 1.25, H = W(inst.x, inst.y);
    const v = spriteVel(inst), sp = Math.hypot(v[0], v[1]);
    if (P.shape === 'bolt' && sp > 0.01 && (+P.stretch || 1) > 1.001) {
      _bx.makeBasis(xf.ax, xf.ay, xf.az); const q = new THREE.Quaternion().setFromRotationMatrix(_bx).multiply(_qa.setFromAxisAngle(new THREE.Vector3(0, 0, 1), -Math.atan2(v[1], v[0])));
      this.sphere(c, H, r, col, fade, ink, {q, x: +P.stretch, y: 1, z: 1});
    } else this.sphere(c, H, r, col, fade, ink);
    const L = Math.min(c.laser_max_m, sp * c.laser_streak * Us);
    if (L > r * 0.8) { const T = W(inst.x - v[0] / sp * L / Us, inst.y - v[1] / sp * L / Us); this.tube(c, T, H, 0, r * c.laser_width_pct / 100, col, fade, ink); }
    return;
  }
  if (prim === 'glow') {   // orb
    if (inst.age >= inst.life) return;
    const t = FXK.lifeT(inst);
    let k = P.fade === 'out' ? 1 - t : P.fade === 'in' ? t : P.fade === 'inout' ? Math.sin(t * Math.PI) : 1;
    if (inst.cont) k = P.fade === 'in' ? t : 1;
    const pk = P.pulse_hz > 0 ? 0.85 + 0.15 * Math.sin(2 * Math.PI * P.pulse_hz * (inst.age * FXK.TICK_MS / 1000)) : 1;
    const gr = Math.max(+P.core_r || 0, (P.r_start + (P.r_end - P.r_start) * t) * 0.6) * Us * pk;
    if (gr > 0 && k > 0) this.sphere(c, W(inst.x, inst.y), gr, col, k, ink);
    return;
  }
  if (prim === 'particles') {   // 3D chunks
    const parts = inst.parts || [], kind = c.chunk_shape;
    parts.forEach((q, i) => {
      if (q._lv == null) { const v = Math.hypot(q.vx || 0, q.vy || 0) || 1; q._lv = (Math.random() * 2 - 1) * v * c.chunk_spread_pct / 100; q._sp = [Math.random() * 6, Math.random() * 6, 0.08 + Math.random() * 0.25]; }
      const tt = Math.min(1, q.age / q.life); let size = q.s0;
      if (P.size_over_life === 'shrink') size = q.s1 + (q.s0 - q.s1) * (1 - tt); else if (P.size_over_life === 'grow') size = q.s0 + (q.s1 - q.s0) * tt;
      else if (P.size_over_life === 'pulse') size = q.s0 + (q.s1 - q.s0) * Math.sin(Math.min(1, tt) * Math.PI);
      const rr = Math.max(0.5, size) / 2 * Us * c.chunk_size_pct / 100;
      const rgb = [q.rgb1[0] + (q.rgb2[0] - q.rgb1[0]) * tt, q.rgb1[1] + (q.rgb2[1] - q.rgb1[1]) * tt, q.rgb1[2] + (q.rgb2[2] - q.rgb1[2]) * tt];
      const tn = this.paint(this.toon(kind, 0), c, rgb, Math.max(0, 1 - tt), ink * 0.6), a = q.age * q._sp[2];
      [tn.m, tn.h].forEach(x => { this.w3(inst, xf, q.x, q.y, q._lv * q.age, x.position); x.rotation.set(q._sp[0] + a, q._sp[1] + a * 0.7, a * 0.4); x.scale.setScalar(rr);
        x.material.uniforms.uTaper.value = 0; });
    });
    return;
  }
  if (prim === 'pulse') {   // impact: shell + shock ring + spikes
    const rings = FXK.pulseRings(inst, 1), sh = FXK.pulseShape(inst, this.host), C = W(inst.x, inst.y);
    _bx.makeBasis(xf.ax, xf.ay, xf.az); const qb = new THREE.Quaternion().setFromRotationMatrix(_bx).multiply(_qa.setFromAxisAngle(new THREE.Vector3(0, 0, 1), -sh.tilt * D));
    const c2 = FXK.colorPair(fx, lut)[1];
    rings.forEach((q, j) => {
      if (q.a <= 0.004 || q.r <= 0) return;
      const R = q.r * Us;
      if (c.impact_shell) { const s0 = Object.assign({}, c, {toon_core_pct: 0}); this.sphere(s0, C, R, c2, q.a * c.impact_shell_pct / 100, 0, {q: qb, x: sh.sx, y: sh.sy, z: Math.max(sh.sx, sh.sy)}); }
      if (c.impact_ring) { const t = this.paint(this.toon('ring', c.toon_sides), c, col, q.a, ink * 0.5);
        [t.m, t.h].forEach(x => { x.position.copy(C); x.quaternion.setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2); x.scale.set(R * sh.sx, R * sh.sy, R * (1 + q.w * Us * 2)); x.material.uniforms.uTaper.value = 0; }); }
      if (j === 0 && c.impact_spikes > 0) {
        const rnd = FXK.rng((inst.seed || 1) + 7), L = R * c.impact_spike_pct / 100, base = Math.max(0.02, (q.w || 2) * Us * 0.8);
        for (let k = 0; k < c.impact_spikes; k++) {
          const th = rnd() * Math.PI * 2, ph = Math.acos(rnd() * 2 - 1), dir = _d.set(Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th));
          const len = L * (0.55 + 0.45 * rnd()), A = C.clone().addScaledVector(dir, R * 0.35), B = C.clone().addScaledVector(dir, R * 0.35 + len);
          this.tube(c, A, B, base, 0, col, q.a, ink * 0.5);
        }
      }
    });
  }
};
/* Paint every live effect onto its card(s) and place them. cam = the THREE camera, H = drawing buffer height (px).
   opts.hidden: hide body-bound FX (blinked out). */
Runner.prototype.draw = function (cam, H, opts) {
  const ctx = this.ctx; this.cards.forEach(c => { c.used = false; }); this.toons.forEach(t => { t.used = false; });
  if (!ctx) { this.cards.forEach(c => { c.mesh.visible = false; }); this.toons.forEach(t => { t.m.visible = t.h.visible = false; }); return; }
  const hidden = !!(opts && opts.hidden), tanH = Math.tan(cam.fov * Math.PI / 360);
  _cr.set(1, 0, 0).applyQuaternion(cam.quaternion); _cu.set(0, 1, 0).applyQuaternion(cam.quaternion); _cf.set(0, 0, 1).applyQuaternion(cam.quaternion);
  const groups = new Map(), solid = [];
  for (const l of this.lanes) for (const inst of l.player.insts) {
    if (hidden && FXK.bodyBound(inst)) continue;
    this.initInst(l, inst);
    if (inst._r3) { solid.push([l, inst]); continue; }   // 3D cel-shaded shape, no card
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
  const xs = {P: new THREE.Vector3(), q: new THREE.Quaternion(), Us: U, bill: false};
  for (const [l, inst] of solid) { this.cur = l; this.xform(l, inst, xs); this.axes(l, xs);
    try { this.draw3d(l, inst, xs); } catch (err) { console.error('fx3d draw3d', err); } }
  this.cur = null;
  this.cards.forEach(c => { if (!c.used) c.mesh.visible = false; });
  this.toons.forEach(t => { if (!t.used) t.m.visible = t.h.visible = false; });
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

G.FX3D = {U, HURT, ANCHORS, LAYS, PIVOTS, DEF3D, MOVE_DEFAULTS, MOVE_PATHS, START_MODES, MOVE_EASES, RENDERS, CHUNKS, TOON_PRIMS,
  cfg3d, is3d, autoLay, layOf, moveCfg, byAction, Runner, movePlan, spotAround, easeU};
})(window);
