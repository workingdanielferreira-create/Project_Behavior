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
  impact_shell: true, impact_shell_pct: 35, impact_ring: true, impact_spikes: 8, impact_spike_pct: 90, chunk_shape: 'shard', chunk_spread_pct: 60, chunk_size_pct: 120,
  strike_limb: 'auto', strike_glow_pct: 50, strike_spin_deg: 90, strike_ground: true};
const RENDERS = ['auto', '3d', 'card'];
const CHUNKS = ['shard', 'ball', 'cube'];
const TOON_PRIMS = ['ribbon', 'beam', 'particles', 'glow', 'pulse'];
// 3D strikes (Daniel 2026-11-25): the punch, the kicks and the serious punch. Energy-look parts are 3D shapes, ink / gritty
// parts stay on the card. strike_limb = the 3D fist / foot the strike drives out from (auto = picked from the body).
const STRIKE_KICKS = ['roundhouse_kick', 'thrust_kick', 'axe_kick', 'spinning_kick', 'rising_kick'];
const STRIKE_LIMBS = ['auto', 'haR', 'haL', 'ftR', 'ftL', 'none'];
const LIMB_ROOT = {haR: 'elR', haL: 'elL', ftR: 'knR', ftL: 'knL'};
function strikeKind(fx) {
  if (!fx || fx.prim !== 'technique') return '';
  const s = fx.params && fx.params.style;
  return s === 'impact_punch' ? 'punch' : STRIKE_KICKS.indexOf(s) >= 0 ? 'kick' : s === 'serious_punch' ? 'serious' : '';
}
const TOON_NUMS = ['toon_bands', 'toon_core_pct', 'toon_shade_pct', 'toon_ink_m', 'toon_alpha_pct', 'toon_sides', 'laser_streak', 'laser_max_m',
  'laser_width_pct', 'beam_bulb_pct', 'beam_flare_pct', 'beam_wobble_pct', 'beam_width_pct', 'impact_shell_pct', 'impact_spikes', 'impact_spike_pct',
  'chunk_spread_pct', 'chunk_size_pct', 'strike_glow_pct', 'strike_spin_deg'];
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
  if (STRIKE_LIMBS.indexOf(c.strike_limb) < 0) c.strike_limb = 'auto';
  c.strike_ground = c.strike_ground !== false;
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
  if (strikeKind(fx)) return true;
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
  // (cards bend through three.js's patched project_vertex, world3d.js installBend: the segments let a long card curve)
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, CARD_SEGS, CARD_SEGS), mat); mesh.renderOrder = 3; mesh.frustumCulled = false; scene.add(mesh);
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
// The planet (Daniel 2026-11-25, "FX should bend as the planet's ground bends"): the same globe bend as world3d.js
// installBend (uBend = World3D.BEND: anchor x / z, w = planet radius, 0 = flat), applied in world space after the
// taper / ink inflate, so a beam laid level on the flat sim plane is drawn following the ground at the same height.
// The normal is bent with it (for the bands). Tubes and cards are split along their length so they can curve.
const TOON_VS = [
  'uniform float uR0; uniform float uR1; uniform float uTaper; uniform float uInflate; uniform vec4 uBend;',
  'varying vec3 vN; varying vec3 vV; varying float vD;',
  'vec3 bendP( vec3 p ) {',
  '  if ( uBend.w <= 0.0 ) return p;',
  '  vec2 d = p.xz - uBend.xz; float r = length( d ); if ( r < 1e-5 ) return p;',
  '  float th = r / uBend.w, rr = uBend.w + p.y; vec2 dir = d / r;',
  '  return vec3( uBend.x + dir.x * sin( th ) * rr, cos( th ) * rr - uBend.w, uBend.z + dir.y * sin( th ) * rr );',
  '}',
  'void main() {',
  '  vec3 p = position;',
  '  if ( uTaper > 0.5 ) p.xz *= mix( uR0, uR1, clamp( p.y + 0.5, 0.0, 1.0 ) );',
  '  vec4 wp = modelMatrix * vec4( p, 1.0 );',
  '  vec3 nv = normalize( normalMatrix * normal );',
  '  vec3 nw = normalize( ( vec4( nv, 0.0 ) * viewMatrix ).xyz );',
  '  wp.xyz += nw * uInflate;',
  '  vec3 bp = bendP( wp.xyz );',
  '  vec3 bn = normalize( bendP( wp.xyz + nw * 0.05 ) - bp );',
  '  vec4 mv = viewMatrix * vec4( bp, 1.0 );',
  '  vN = normalize( ( viewMatrix * vec4( bn, 0.0 ) ).xyz ); vV = normalize( -mv.xyz ); vD = -mv.z;',
  '  gl_Position = projectionMatrix * mv;',
  '}'].join('\n');
const FLAT_BEND = {x: 0, y: 0, z: 0, w: 0};
const bendRef = () => (G.World3D && G.World3D.BEND) || FLAT_BEND;
const TUBE_SEGS = 28, CARD_SEGS = 16;   // along a tube / across a card: enough to follow the globe's curve
const TOON_FS = [
  'uniform vec3 uCol; uniform vec3 uShade; uniform vec3 uCore; uniform float uBands; uniform float uCoreT; uniform float uAlpha; uniform float uInk;',
  'varying vec3 vN; varying vec3 vV; varying float vD;',
  'void main() {',
  // near the camera a shape fades out (a big shock ring / flash passing the lens never blanks the screen)
  '  float nf = smoothstep( 0.35, 1.8, vD );',
  '  if ( nf <= 0.0 ) discard;',
  '  if ( uInk > 0.5 ) { gl_FragColor = vec4( 0.02, 0.027, 0.05, uAlpha * nf ); return; }',
  '  float f = abs( dot( normalize( vN ), normalize( vV ) ) );',
  '  vec3 c;',
  '  if ( uCoreT > 0.0 && f >= 1.0 - uCoreT ) c = uCore;',
  '  else { float k = f / max( 0.001, 1.0 - uCoreT ); float i = min( uBands - 1.0, floor( k * uBands ) );',
  '    c = mix( uShade, uCol, uBands > 1.0 ? i / ( uBands - 1.0 ) : 1.0 ); }',
  '  gl_FragColor = vec4( c, uAlpha * nf );',
  '}'].join('\n');
const GEO = {};
function toonGeo(kind, sides) {
  const k = kind + sides; if (GEO[k]) return GEO[k];
  let g;
  if (kind === 'tube') g = new THREE.CylinderGeometry(1, 1, 1, sides, TUBE_SEGS, false);
  else if (kind === 'sph') g = new THREE.SphereGeometry(1, sides, Math.max(4, Math.round(sides * 0.7)));
  else if (kind === 'ring') g = new THREE.TorusGeometry(1, 0.045, 5, Math.max(12, sides * 3));
  else if (kind === 'shard') g = new THREE.OctahedronGeometry(1, 0);
  else if (kind === 'cube') g = new THREE.BoxGeometry(1.3, 1.3, 1.3);
  else if (/^arc\d$/.test(kind)) g = new THREE.TorusGeometry(1, 0.045, 5, 18, Math.PI * 2 / +kind.slice(3) * 0.62);   // a broken ring's piece
  else g = new THREE.IcosahedronGeometry(1, 0);   // ball
  return (GEO[k] = g);
}
function toonUniforms(ink) {
  return {uCol: {value: new THREE.Color()}, uShade: {value: new THREE.Color()}, uCore: {value: new THREE.Color()}, uBands: {value: 3}, uCoreT: {value: 0.3},
    uAlpha: {value: 1}, uInk: {value: ink ? 1 : 0}, uR0: {value: 1}, uR1: {value: 1}, uTaper: {value: 0}, uInflate: {value: 0}, uBend: {value: bendRef()}};
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
  // a 3D strike: drawn as 3D shapes (+ a card for its ink / gritty parts), hit by FX Studio's own punch / kick line
  inst._s3 = inst._r3 ? strikeKind(inst.fx) : ''; if (inst._s3) { inst._r3 = false; inst._lay = inst._c.lay === 'auto' ? 'side' : inst._lay; }
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
/* ---- 3D strikes (Daniel 2026-11-25: "recreate the FX into 3D, start with punching motion and impact effects") ----
   The punch (strikefx.js), the kicks (kickfx.js) and the serious punch (powerfx.js). FX Studio's own timeline and random
   streams decide what happens (STRIKEFX / KICKFX .parts, POWERFX.sp); here it is rebuilt as 3D cel-shaded shapes:
     - motion: the fist / foot starts at the REAL 3D hand / foot (strike_limb, auto = the one driving forward) and drives
       out to FX Studio's full reach along the aim, then back; smear frames = tapered tubes of the forearm / shin, air
       strokes = tubes spiralling round its path (strike_spin_deg), the fist = a sphere stretched by its speed
     - impact: opens as a forward 3D cone round the blow: a white flash, pressure spheres pushed along it, rays, a star of
       spikes, a shock ring standing across the blow (+ a broken one), sparks thrown on with gravity; the impact frame
       (flash + focus lines) faces the camera
     - ground (fx_env): rings, dust, sparks, the axe crater (scorch disc, cracks, debris) and the spinning kick's vortex
       lie level on the floor (strike_ground) and spread all round
   Only the energy look is 3D for now (Daniel: "energy first"); ink / gritty parts stay on the effect's card. Hits are
   FX Studio's own punch / kick line in the effect's plane (unchanged). Glow sizes x strike_glow_pct (a 2D glow is soft,
   a sphere is solid). */
const _s1 = new THREE.Vector3(), _s2 = new THREE.Vector3(), _s3 = new THREE.Vector3(), _sq = new THREE.Quaternion(), ZV = new THREE.Vector3(0, 0, 1), XV = new THREE.Vector3(1, 0, 0);
const SLib = () => G.SWORDFX.lib;
function noCore(c) { return c._nc || (c._nc = Object.assign({}, c, {toon_core_pct: 0})); }
function easeO(u) { u = Math.max(0, Math.min(1, u)); return 1 - Math.pow(1 - u, 3); }
function easeI(u) { u = Math.max(0, Math.min(1, u)); return u * u * u; }
// a unit vector deg away from u, turned az round it
function coneDir(u, deg, az, out) {
  const p1 = Math.abs(u.y) < 0.9 ? _s1.set(0, 1, 0) : _s1.set(1, 0, 0); p1.crossVectors(u, p1).normalize();
  const p2 = _s2.crossVectors(u, p1);
  const s = Math.sin(deg * D), cz = Math.cos(deg * D);
  return out.copy(u).multiplyScalar(cz).addScaledVector(p1, Math.cos(az) * s).addScaledVector(p2, Math.sin(az) * s).normalize();
}
function strikeCard(inst) {
  if (inst._s3 === 'serious') return false;
  const P = inst.fx.params || {}, H = G.HITFX;
  return ['fx_motion', 'fx_impact', 'fx_env'].some(k => { const v = H.look(P, k); return v === 'ink' || v === 'gritty'; });
}
// while a strike's card is painted: its energy parts and impact frame are 3D, so the card leaves them out
function strikeCardPatch(insts) {
  const out = [];
  insts.forEach(i => {
    if (!i._s3) return; const P = i.fx.params; if (!P || out.some(x => x[0] === P)) return;
    out.push([P, P.fx_motion, P.fx_impact, P.fx_env, P.impact_frame]);
    ['fx_motion', 'fx_impact', 'fx_env'].forEach(k => { if (G.HITFX.look(P, k) === 'energy') P[k] = 'off'; });
    P.impact_frame = 'off';
  });
  return () => out.forEach(x => { ['fx_motion', 'fx_impact', 'fx_env', 'impact_frame'].forEach((k, j) => { if (x[j + 1] === undefined) delete x[0][k]; else x[0][k] = x[j + 1]; }); });
}
// a ring (torus) round axis n through C, radius R; zk = depth along the axis; rot = turn round n
Runner.prototype.torus = function (c, kind, C, n, R, zk, rot, rgb, a, ink) {
  if (!(R > 1e-3) || a <= 0.004) return null;
  const t = this.paint(this.toon(kind, kind === 'ring' ? c.toon_sides : 0), c, rgb, a, ink);
  _sq.setFromUnitVectors(ZV, n).multiply(_qa.setFromAxisAngle(ZV, rot || 0));
  [t.m, t.h].forEach(x => { x.position.copy(C); x.quaternion.copy(_sq); x.scale.set(R, R, R * (zk || 1)); x.material.uniforms.uTaper.value = 0; });
  return t;
};
// a strike's limb history: the 3D anchors it may drive out from, per tick of the effect
Runner.prototype.boneRec = function (inst, ids) {
  const h = inst._bh || (inst._bh = {}), a = Math.max(0, inst.age | 0);
  ids.forEach(id => { const r = h[id] || (h[id] = []); if (!r[a]) { const W = this.anchorWorld(id, new THREE.Vector3()); if (W) r[a] = W; } });
};
Runner.prototype.boneAt = function (inst, id, t, out) {
  const r = inst._bh && inst._bh[id]; if (!r || !r.length) return null;
  let i0 = Math.min(r.length - 1, Math.floor(t)), i1 = Math.max(0, Math.ceil(t));
  while (i0 >= 0 && !r[i0]) i0--; while (i1 < r.length && !r[i1]) i1++;
  if (i0 < 0 && i1 >= r.length) return null;
  if (i0 < 0) return out.copy(r[i1]); if (i1 >= r.length || i1 === i0) return out.copy(r[i0]);
  return out.copy(r[i0]).lerp(r[i1], Math.max(0, Math.min(1, (t - i0) / (i1 - i0))));
};
// which 3D fist / foot this strike drives out from (null = FX Studio's line only)
Runner.prototype.strikeLimbId = function (inst, S) {
  const c = inst._c; if (c.strike_limb === 'none') return null;
  if (c.strike_limb !== 'auto') return c.strike_limb;
  if (inst._lim) return inst._lim;
  const an = typeof inst.fx.anchor === 'string' ? inst.fx.anchor.replace(/^3d:/, '') : '';
  if (LIMB_ROOT[an]) return (inst._lim = an);
  const cand = S.kind === 'kick' ? ['ftR', 'ftL'] : ['haR', 'haL'], l = this.cur, t = inst.age;
  let best = null, bd = -Infinity;
  cand.forEach(id => { const r = inst._bh && inst._bh[id]; if (!r) return; const f = r.find(Boolean), n = this.boneAt(inst, id, t, _s3); if (!f || !n) return;
    const d = n.dot(l.X) - f.dot(l.X); if (d > bd) { bd = d; best = id; } });
  if (best && t >= S.M.tc) inst._lim = best;   // locked once the blow lands
  return best;
};
// how far out the strike is (0 = at the 3D fist, 1 = at FX Studio's reach)
function strikeOut(S, q, t) {
  const M = S.M;
  if (S.ext) return Math.max(0, Math.min(1, Math.hypot(q[2] - q[0], q[3] - q[1]) / Math.max(1, S.reach)));
  if (t <= M.t0) return 0; if (t < M.tc) return easeO((t - M.t0) / Math.max(1e-3, M.tc - M.t0)); if (t <= M.tm) return 1;
  return t < M.tout ? 1 - easeI((t - M.tm) / Math.max(1e-3, M.tout - M.tm)) : 0;
}
// the limb at tick t in 3D: {T tip, R root, u (unit motion), s}
Runner.prototype.limb3 = function (inst, xf, S, t) {
  const q = S.M.limb(t), T = this.w3(inst, xf, q[2], q[3], 0, new THREE.Vector3()), R = this.w3(inst, xf, q[0], q[1], 0, new THREE.Vector3());
  const s = S.lim ? strikeOut(S, q, t) : 1;
  if (S.lim && s < 1) {
    const B = this.boneAt(inst, S.lim, t, new THREE.Vector3()); if (B) T.copy(B.lerp(T, s));
    const BR = this.boneAt(inst, LIMB_ROOT[S.lim], t, new THREE.Vector3()); if (BR) R.copy(BR.lerp(R, s));
  }
  const u = xf.ax.clone().multiplyScalar(q[4]).addScaledVector(xf.ay, -q[5]);
  if (u.lengthSq() < 1e-8) u.copy(xf.ax); u.normalize();
  return {T, R, u, s};
};
Runner.prototype.drawStrike = function (l, inst, xf) {
  const Lb = SLib(), P = inst.fx.params || {}, c = inst._c, Us = xf.Us, kind = inst._s3, H = G.HITFX, ink = c.toon_ink_m;
  const col = Lb.colours(inst, this.host)[0], HOTc = [255, 255, 255], gk = c.strike_glow_pct / 100;
  if (kind === 'serious') return this.drawSerious(l, inst, xf, col, gk);
  const pt = (kind === 'punch' ? G.STRIKEFX : G.KICKFX).parts(inst, 1);
  const S = {kind, M: pt.motion, reach: pt.reach, ext: kind === 'punch' || !!pt.thrust, lim: null};
  const cand = kind === 'kick' ? ['ftR', 'ftL', 'knR', 'knL'] : ['haR', 'haL', 'elR', 'elL'];
  const an = typeof inst.fx.anchor === 'string' ? inst.fx.anchor.replace(/^3d:/, '') : '';
  if (LIMB_ROOT[an] && cand.indexOf(an) < 0) cand.push(an, LIMB_ROOT[an]);
  if (c.strike_limb !== 'auto' && LIMB_ROOT[c.strike_limb] && cand.indexOf(c.strike_limb) < 0) cand.push(c.strike_limb, LIMB_ROOT[c.strike_limb]);
  this.boneRec(inst, cand); S.lim = this.strikeLimbId(inst, S);
  const t = inst.age, M = S.M;
  // ---- motion (fx_motion)
  if (H.look(P, 'fx_motion') === 'energy') {
    const rf = M.rf * Us, Wd = M.W * Us;
    if (t < M.t0) {   // wind-up: a glint drawing in
      const L0 = this.limb3(inst, xf, S, M.t0), e = (t + 1) / Math.max(1, M.t0);
      this.sphere(c, L0.T, rf * (0.8 + 1.2 * e) * gk, col, (120 + 100 * e) / 255, ink);
      this.torus(noCore(c), 'ring', L0.T, L0.u, rf * (3 - 2 * e), 0.6, 0, HOTc, 150 * e / 255, 0);
    } else {
      const K = H.K;
      if ((P.motion_arcs === undefined ? true : P.motion_arcs) && t <= M.tm + K.ARC_LINGER) {   // air strokes spiralling round the path
        const te = Math.min(t, M.tm), f = t <= M.tm ? 1 : 1 - (t - M.tm) / (K.ARC_LINGER + 1);
        for (let j = 0; j < K.ARC_N + 1; j++) {
          const r = Lb.rngFor(inst.seed, j, 300);
          const off = r.uniform(-1, 1) * (rf * 0.6 + Wd * 0.4), lag = r.uniform(0, 0.5), span = r.uniform(2, 3.4), gap = r.uniform(0.38, 0.55), wmax = r.uniform(1.4, 2.6) * Us;
          const az0 = r() * Math.PI * 2, tw = r.uniform(-1, 1) * c.strike_spin_deg * D;
          const s1 = te - lag, s0 = Math.max(M.t0, s1 - span); if (s1 - s0 < 0.3) continue;
          [[0, gap - 0.06], [gap + 0.06, 1]].forEach(uu => {
            const N = 6, pts = [];
            for (let k = 0; k < N; k++) {
              const kk = uu[0] + (uu[1] - uu[0]) * k / (N - 1), L3 = this.limb3(inst, xf, S, s0 + (s1 - s0) * kk);
              pts.push(L3.T.addScaledVector(coneDir(L3.u, 90, az0 + tw * kk, _d), Math.abs(off)));
            }
            for (let k = 1; k < N; k++) this.tube(c, pts[k - 1], pts[k], wmax * 0.8 * Math.sin(Math.PI * (k - 1) / (N - 1)), wmax * 0.8 * Math.sin(Math.PI * k / (N - 1)), col, 150 / 255 * f, 0);
          });
        }
      }
      if ((P.motion_smear === undefined ? true : P.motion_smear) && t < M.tc) {   // smear frames of the forearm / shin
        for (let k = K.SMEAR_N; k > 0; k--) {
          const s = t - K.SMEAR_STEP * k; if (s < M.t0) continue;
          const L3 = this.limb3(inst, xf, S, s), ln = L3.T.distanceTo(L3.R); if (ln < 2 * Us) continue;
          const q = 1 - (k - 1) / K.SMEAR_N, Rr = _s2.copy(L3.T).lerp(L3.R, Math.min(1, K.SMEAR_LEN * rf / ln)).clone();
          this.tube(noCore(c), Rr, L3.T, rf * 0.45, rf * (0.75 + 0.2 * q), col, 95 / 255 * q * 1.6, 0);
        }
      }
      if (t < M.tout) {   // the fist / foot, stretched by its speed, with two after-glows
        const fade = t <= M.tm ? 1 : 1 - (t - M.tm) / Math.max(1, M.tout - M.tm), L3 = this.limb3(inst, xf, S, t);
        if (L3.T.distanceTo(L3.R) > Us) {
          [[2, 60], [1, 100]].forEach(ja => { const g = this.limb3(inst, xf, S, Math.max(M.t0, t - ja[0])); this.sphere(noCore(c), g.T, rf * 1.8 * gk, col, ja[1] / 255 * fade, 0); });
          const prev = this.limb3(inst, xf, S, Math.max(M.t0, t - 1)), v = L3.T.clone().sub(prev.T), sp = v.length();
          const st = 1 + Math.min(1.6, sp / Math.max(1e-3, rf * 3));
          _sq.setFromUnitVectors(XV, sp > 1e-4 ? v.divideScalar(sp) : L3.u);
          this.sphere(c, L3.T, rf * 1.4 * gk * 1.6, col, fade, ink, {q: _sq.clone(), x: st, y: 1 / Math.sqrt(st), z: 1 / Math.sqrt(st)});
        }
      }
    }
  }
  // ---- surroundings (fx_env), then the impacts (fx_impact)
  if (H.look(P, 'fx_env') === 'energy') pt.env.forEach(ev => this.strikeEnv(l, inst, xf, ev, col, gk));
  const doImp = H.look(P, 'fx_impact') === 'energy';
  pt.impacts.forEach(m => {
    const C = this.w3(inst, xf, m.x, m.y, 0, new THREE.Vector3());
    const u3 = xf.ax.clone().multiplyScalar(m.u[0]).addScaledVector(xf.ay, -m.u[1]); if (u3.lengthSq() < 1e-8) u3.copy(xf.ax); u3.normalize();
    this.impactFrame3d(inst, c, C, m.a, m.sc, m.salt, col, Us);
    if (doImp) this.impact3d(inst, c, C, u3, m.a, m.sc, m.salt, col, Us, gk, c.strike_ground ? l.groundY : null);
  });
};
// The energy impact as a forward 3D cone round the blow u3 (hitfx impEnergy).
Runner.prototype.impact3d = function (inst, c, C, u3, a, sc, salt, col, Us, gk, gy) {
  const Lb = SLib(), K = G.HITFX.K, P = inst.fx.params || {}, HOTc = [255, 255, 255], ink = c.toon_ink_m, nc = noCore(c);
  if (!(a >= 0 && a < K.IMPACT_LIFE)) return;
  const q = a / K.IMPACT_LIFE, d3 = new THREE.Vector3(), A = new THREE.Vector3(), B = new THREE.Vector3();
  if (a < 6) this.sphere(nc, C, (18 + 24 * easeO(a / 6)) * sc * Us * gk, HOTc, 1 - a / 6, 0);   // flash
  if (a < 10) { const e = easeO(a / 10);   // pressure spheres pushed along the blow
    for (let k = 0; k < 3; k++) this.sphere(c, A.copy(C).addScaledVector(u3, (6 + 16 * k) * sc * e * Us), (22 - 5 * k) * sc * (0.6 + 0.6 * e) * Us * gk, col, (190 - 50 * k) / 255 * (1 - a / 10), 0); }
  this.sphere(nc, C, (26 + 20 * easeO(q)) * sc * Us * gk, col, 120 / 255 * (1 - q) * 0.6, 0);   // halo
  if (a < 9) { const f = 1 - a / 9, e = easeO(a / 4);   // rays spilling forward
    for (let j = 0; j < 9; j++) { const r = Lb.rngFor(inst.seed, j, 500 + salt);
      const dg = r.uniform(-38, 38), ln = r.uniform(40, 110) * sc * e * Us, w = r.uniform(3, 6) * sc * Us, d0 = 6 * sc * Us; coneDir(u3, Math.abs(dg), r() * Math.PI * 2, d3);
      this.tube(c, A.copy(C).addScaledVector(d3, d0), B.copy(C).addScaledVector(d3, d0 + ln), w * 0.5 * f, 0, col, 170 / 255 * f, ink * 0.5); } }
  if (a < 7) { const qs = a / 7, e = easeO(a / 3);   // a star of spikes all round
    for (let j = 0; j < 8; j++) { const r = Lb.rngFor(inst.seed, j, 520 + salt), th = r() * Math.PI * 2, ph = Math.acos(r() * 2 - 1);
      d3.set(Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th));
      this.tube(c, C, B.copy(C).addScaledVector(d3, (14 + 22 * e) * sc * Us * r.uniform(0.7, 1.15)), (5 + 6 * e) * 0.35 * sc * Us, 0, col, 1 - qs, ink * 0.5); }
    this.sphere(c, C, (5 + 4 * e) * sc * Us, HOTc, Math.pow(1 - qs, 1.5), 0); }
  [[0, 0, 1], [1, 4, 1.6]].forEach(rg => {   // shock ring standing across the blow, and a broken one further out
    const aa = a - rg[1]; if (aa < 0) return;
    const qq = aa / (K.IMPACT_LIFE - rg[1]), ee = easeO(qq), kk = rg[2], P0 = A.copy(C).addScaledVector(u3, 10 * sc * ee * kk * Us), R = (10 + 46 * ee) * sc * kk * Us;
    if (rg[0] === 0) this.torus(c, 'ring', P0, u3, R, 0.7, 0, col, 210 / 255 * (1 - qq), ink * 0.5);
    else { const r = Lb.rngFor(inst.seed, 0, 540 + salt), n = 3 + Math.trunc(r() * 3), t0 = r() * Math.PI * 2;
      for (let i = 0; i < n; i++) this.torus(c, 'arc' + n, P0, u3, R, 0.7, t0 + i * Math.PI * 2 / n, col, 190 / 255 * (1 - qq), ink * 0.5); }
  });
  const nSp = Math.max(0, Math.round(14 * (+P.density || 1) * sc));   // sparks thrown on with the blow, falling
  for (let j = 0; j < nSp; j++) {
    const r = Lb.rngFor(inst.seed, j, 560 + salt), life = 10 + 10 * r(); if (a >= life) continue;
    const dg = r.uniform(-65, 65), sp = r.uniform(3, 9), fd = Lb.dragDist(0.87, a), dk = Math.pow(0.87, a), q2 = a / life;
    coneDir(u3, Math.abs(dg), r() * Math.PI * 2, d3);
    B.copy(C).addScaledVector(d3, sp * fd * Us); B.y -= 0.1 * a * a * Us;
    A.copy(B).addScaledVector(d3, -sp * dk * 2.4 * Us);
    if (gy != null && B.y < gy + 0.03) { const k = Math.max(0, gy + 0.03 - A.y); B.y = A.y = gy + 0.03; A.addScaledVector(d3, -k * 0.5); }   // skid on the floor
    this.tube(nc, A, B, 0, 0.9 * Us, Lb.mix(HOTc, col, q2), 1 - q2, 0);
  }
};
// FX Studio's impact frame (strike params impact_frame local / full): a flash + focus lines, facing the camera.
Runner.prototype.impactFrame3d = function (inst, c, C, a, sc, salt, col, Us) {
  const P = inst.fx.params || {}, mode = P.impact_frame || 'off', SF = G.STRIKEFX;
  if ((mode !== 'local' && mode !== 'full') || !(a >= 0 && a < SF.IMPACT_FRAME_TICKS) || SF.HIT_OPTION_STYLES.indexOf(P.style) < 0) return;
  const full = mode === 'full', camD = this._camPos ? C.distanceTo(this._camPos) : 20;
  const R = full ? Math.max(0.3, Math.min(7, camD * 0.6)) : (+P.impact_frame_r || 0) * sc * Us; if (R < 0.05) return;
  const Lb = SLib(), lit = a === 0, INKc = SF.INK, bg = lit ? [255, 255, 255] : INKc, fg = lit ? INKc : Lb.mix(col, [255, 255, 255], 0.5), nc = noCore(c);
  this.sphere(nc, C, R * (full ? 1 : 0.6), bg, (full ? (lit ? 190 : 150) : (lit ? 235 : 200)) / 255, 0);
  const Rl = full ? R * 4 : R, n = full ? 32 : 22, F = new THREE.Vector3().copy(C).addScaledVector(_cf, R * (full ? 1 : 0.6) * 1.02), d3 = new THREE.Vector3(), A = new THREE.Vector3(), B = new THREE.Vector3();
  for (let j = 0; j < n; j++) {
    const r = Lb.rngFor(inst.seed, j, 130 + salt), an = (j + r.uniform(-0.4, 0.4)) * Math.PI * 2 / n, r0 = Rl * r.uniform(0.18, 0.45), hw = r.uniform(0.012, 0.03);
    d3.copy(_cr).multiplyScalar(Math.cos(an)).addScaledVector(_cu, Math.sin(an));
    this.tube(nc, A.copy(F).addScaledVector(d3, r0), B.copy(F).addScaledVector(d3, Rl), 0, Rl * hw, fg, (lit ? 230 : 200) / 255, 0);
  }
};
// The energy surroundings (hitfx env): ev = [kind, age, x, y, ux, uy, size, salt] in the effect's 2D frame.
Runner.prototype.strikeEnv = function (l, inst, xf, ev, col, gk) {
  const Lb = SLib(), K = G.HITFX.K, P = inst.fx.params || {}, c = inst._c, nc = noCore(c), Us = xf.Us, kind = ev[0], a = ev[1], sc = ev[6], salt = ev[7];
  const UP = UPV, HOTc = [255, 255, 255], ink = c.toon_ink_m;
  const G0 = this.w3(inst, xf, ev[2], ev[3], 0, new THREE.Vector3()); if (c.strike_ground && kind !== 'vortex' && kind !== 'kickup') G0.y = l.groundY + 0.02;
  const hx = _s3.copy(xf.ax).setY(0); if (hx.lengthSq() < 1e-6) hx.copy(l.X); hx.normalize(); const hX = hx.clone();
  const A = new THREE.Vector3(), B = new THREE.Vector3(), d3 = new THREE.Vector3();
  // dust puffs (hitfx puffs, energy): drifting along the ground (dirx = the way along the aim; 0 = all round), rising
  const puffs = (life, n, spread, rise, size, sl, dirx) => {
    for (let j = 0; j < n; j++) {
      const r = Lb.rngFor(inst.seed, j, sl), lf = life * r.uniform(0.7, 1); if (a >= lf) continue;
      const q = a / lf, e = easeO(q), az = dirx ? Math.atan2(0, dirx) + r.uniform(-0.7, 0.7) : (j + r.uniform(-0.3, 0.3)) * Math.PI * 2 / n;
      const sp = spread * e * r.uniform(0.4, 1), hz = d3.copy(hX).applyAxisAngle(UP, az);
      A.copy(G0).addScaledVector(hz, sp * Us).addScaledVector(UP, rise * e * r.uniform(0.3, 1) * Us);
      this.sphere(nc, A, size * (0.6 + 0.9 * e) * r.uniform(0.7, 1.3) * 0.8 * Us * gk, col, 150 / 255 * (1 - q), 0);
    }
  };
  if (kind === 'push') {
    if (a < 0 || a >= 16) return; const q = a / 16, e = easeO(q);
    this.torus(nc, 'ring', G0, UP, (6 + 26 * e) * sc * Us, 0.5, 0, col, 180 / 255 * (1 - q), 0);
    puffs(16, 4, 26 * sc, 8 * sc, 6 * sc, 700 + salt, ev[4]); return;
  }
  if (kind === 'kickup') { if (a < 0 || a >= 18) return; puffs(18, Math.max(1, Math.round(5 * (+P.density || 1))), 12, 26, 7, 720 + salt, 0); return; }
  if (kind === 'vortex') {   // wind rings round the body, level, turning with the kick
    const Ln = ev[4], s = ev[5], fade = ev[6], cc = Lb.mix(col, HOTc, 0.3);
    for (let j = 0; j < 3; j++) { const R = Ln * (0.8 + 0.25 * j) * Us, Cj = A.copy(G0).addScaledVector(UP, -Ln * 0.15 * (j - 1) * Us).clone();
      for (let i = 0; i < 3; i++) this.torus(nc, 'arc3', Cj, UP, R, 0.6, -s * (a * 0.55 + j * 1.3) + i * Math.PI * 2 / 3, cc, (190 - 40 * j) / 255 * fade, 0); }
    return;
  }
  if (kind === 'crater') {   // axe kick: scorch disc, cracks running out all round, debris thrown up, a ground wave
    if (a < 0 || a >= K.CRATER_LIFE) return;
    const q = a / K.CRATER_LIFE, e = easeO(Math.min(1, a / 8)), R = (22 + 26 * e) * sc * Us;
    _sq.setFromUnitVectors(ZV, UP); this.sphere(nc, A.copy(G0).addScaledVector(UP, 0.01), R, K.SCORCH, 120 / 255 * (1 - q) * 1.5, 0, {q: _sq.clone(), x: 1, y: 1, z: 0.04});
    for (let j = 0; j < 7; j++) { const r = Lb.rngFor(inst.seed, j, 780 + salt), an = (j + r.uniform(-0.35, 0.35)) * Math.PI * 2 / 7, ln = (20 + 60 * e) * sc * r.uniform(0.6, 1.2);
      let prev = G0.clone().addScaledVector(UP, 0.03);
      for (let k = 1; k < 5; k++) { const hz = d3.copy(hX).applyAxisAngle(UP, an + r.uniform(-0.25, 0.25)), cur = G0.clone().addScaledVector(hz, ln * k / 4 * Us).addScaledVector(UP, 0.03);
        this.tube(c, prev, cur, 1.3 * Us * (1 - k / 6), 1.3 * Us * (1 - (k + 1) / 6), col, 1 - q, 0); prev = cur; } }
    const n = Math.max(0, Math.round(8 * (+P.density || 1)));
    for (let j = 0; j < n; j++) { const r = Lb.rngFor(inst.seed, j, 800 + salt), vx = r.uniform(-3, 3), vy = r.uniform(3, 7), h = vy * a - 0.225 * a * a; if (h < -4) continue;
      const hz = d3.copy(hX).applyAxisAngle(UP, r() * Math.PI * 2); A.copy(G0).addScaledVector(hz, Math.abs(vx) * a * Us).addScaledVector(UP, Math.max(0, h) * Us);
      const tn = this.paint(this.toon('shard', 0), c, K.ROCK, 1 - q, ink * 0.6), sz = r.uniform(2, 4) * Us, sp = a * 0.3;
      [tn.m, tn.h].forEach(x => { x.position.copy(A); x.rotation.set(j + sp, j * 0.7 + sp * 0.6, sp * 0.4); x.scale.setScalar(sz); x.material.uniforms.uTaper.value = 0; });
      this.sphere(nc, A, sz * 1.6 * gk, col, 200 / 255 * (1 - q) * 0.5, 0); }
    this.strikeEnv(l, inst, xf, ['ground', a, ev[2], ev[3], 0, 0, sc * 1.2, salt + 1], col, gk); return;
  }
  // ground wave under an impact: a level ring, a flat glow and sparks kicked up off its edge
  if (a < 0 || a >= K.ENV_LIFE) return;
  const q = a / K.ENV_LIFE, e = easeO(q), R = (14 + 56 * e) * sc * Us;
  this.torus(nc, 'ring', G0, UP, R, 0.5, 0, col, 200 / 255 * (1 - q), 0);
  _sq.setFromUnitVectors(ZV, UP); this.sphere(nc, G0, R * 0.7, col, 90 / 255 * (1 - q) * 0.7, 0, {q: _sq.clone(), x: 1, y: 1, z: 0.05});
  for (let j = 0; j < 6; j++) { const r = Lb.rngFor(inst.seed, j, 740 + salt), az = r() * Math.PI * 2, hz = d3.copy(hX).applyAxisAngle(UP, az).clone();
    A.copy(G0).addScaledVector(hz, R * r.uniform(0.5, 1)); B.copy(A).addScaledVector(hz, 8 * Us).addScaledVector(UP, r.uniform(2, 10) * (1 - q) * Us);
    this.tube(nc, A, B, 0.65 * Us, 0, Lb.mix(col, HOTc, 0.5), 220 / 255 * (1 - q), 0); }
};
// The serious punch (powerfx drawSerious) in 3D: a round shock cone with vapour rings, clouds blown out all round.
Runner.prototype.drawSerious = function (l, inst, xf, c0, gk) {
  const Lb = SLib(), SP = G.POWERFX.sp, P = inst.fx.params || {}, c = inst._c, nc = noCore(c), Us = xf.Us, t = inst.age, ink = c.toon_ink_m;
  const cs = Lb.colours(inst, this.host), col = cs[0], bright = cs[1], HOTc = [255, 255, 255];
  const Tw = SP.ti(P, 'swing_ticks', 1), Th = SP.ti(P, 'hold_ticks', 1), rf = +P.radius, Lr = +P.length, dens = +P.density || 1;
  const fw = (fr, x, y, o) => { const p = fr.w(x, y); return this.w3(inst, xf, p[0], p[1], 0, o || new THREE.Vector3()); };
  const aim = xf.ax.clone().multiplyScalar(inst.tq_f[0]).addScaledVector(xf.ay, -inst.tq_f[1]); if (aim.lengthSq() < 1e-8) aim.copy(xf.ax); aim.normalize();
  const A = new THREE.Vector3(), B = new THREE.Vector3(), d3 = new THREE.Vector3();
  if (t < Tw) {   // the wind-up: stillness, air pulling in, motes lifting, a glint
    const fr0 = Lb.frame(inst), u = t / Tw, fist = fw(fr0, -rf * easeO(u), 0);
    for (let j = 0; j < 2; j++) { const v = ((t / 9 + j * 0.5) % 1 + 1) % 1; this.torus(nc, 'ring', fist, aim, rf * (1.2 + 5 * (1 - v)) * Us, 0.6, 0, Lb.mix(col, HOTc, 0.5), 120 / 255 * u * v, 0); }
    for (let i = 0; i < Math.max(0, Math.round(8 * dens)); i++) { const r = Lb.rngFor(inst.seed, i, 601), per = r.uniform(26, 44), v = ((t / per + r()) % 1 + 1) % 1, dx = r.uniform(-60, 60);
      A.copy(fw(fr0, 0, 0, A)); A.addScaledVector(l.X, dx * Us).addScaledVector(l.L, r.uniform(-40, 40) * Us); A.y = l.groundY + v * 40 * Us;
      this.sphere(nc, A, 2.2 * Us, Lb.mix(col, HOTc, 0.3), 140 / 255 * Math.sin(Math.PI * v) * u, 0); }
    this.sphere(c, fist, rf * 2 * Us * gk, col, 100 / 255 * u + 0.25, ink);
    if (t >= Tw - 4) { const g = (t - (Tw - 4)) / 4;
      for (let j = 0; j < 6; j++) { coneDir(aim, 90, j * Math.PI / 3, d3); this.tube(nc, fist, B.copy(fist).addScaledVector(d3, rf * (1 + 2.5 * g) * Us * 1.4), rf * 0.25 * Us, 0, HOTc, 1, 0); }
      this.tube(nc, A.copy(fist).addScaledVector(aim, -rf * 3 * g * Us), B.copy(fist).addScaledVector(aim, rf * 3 * g * Us), 0.0, rf * 0.3 * Us, HOTc, 1, 0); }
    return;
  }
  const k = t - Tw, fr = SP.frame(inst), df = SP.cap(inst, SP.front(P, 1, k));
  const aC = k < SP.OUT + Th ? 1 : Math.max(0, 1 - (k - SP.OUT - Th) / 14);
  const aS = Math.max(0, Math.min(1, k / (Th * 0.6 + 1))) * (k < SP.OUT + Th ? 1 : Math.max(0, 1 - (k - SP.OUT - Th) / SP.SPLIT_LIFE));
  const O = fw(fr, 0, 0);
  // clouds blown apart all round the line
  const nC = Math.max(0, Math.round(10 * dens));
  for (let j = 0; j < nC; j++) for (let s = -1; s <= 1; s += 2) {
    const r = Lb.rngFor(inst.seed, j, 611 + (s > 0 ? 1 : 0)), clx = (j + 0.5) / nC * Lr * 1.4; if (clx > df * 1.4) continue;
    const push = (k - clx / (Lr * 1.4) * Th) * r.uniform(1.2, 2.4), rad = SP.hw(P, 1, Math.min(clx, Lr)) * 0.6 + Math.max(0, push), sz = r.uniform(18, 34);
    coneDir(aim, 90, (s > 0 ? 0 : Math.PI) + r.uniform(-1.4, 1.4), d3);
    A.copy(O).addScaledVector(aim, clx * Us).addScaledVector(d3, rad * Us);
    this.sphere(nc, A, sz * Us * 0.55, SP.CLOUD, 60 / 255 * aS * 2.2, ink * 0.6);
  }
  if (aC > 0 && df > 2) {
    // the shock cone: three nested round cones (outer colour, bright, white-hot core), curved like FX Studio's
    [[1, col, 55], [0.6, bright, 70], [0.22, HOTc, 110]].forEach(cn => {
      for (let i = 0; i < 4; i++) { const x0 = df * i / 4, x1 = df * (i + 1) / 4;
        this.tube(nc, A.copy(O).addScaledVector(aim, x0 * Us), B.copy(O).addScaledVector(aim, x1 * Us), SP.hw(P, 1, x0) * cn[0] * Us, SP.hw(P, 1, x1) * cn[0] * Us, cn[1], cn[2] / 255 * aC * 1.8, 0); }
    });
    for (let i = 0; i < SP.RINGS; i++) {   // vapour rings left where the front passed
      const ki = (i + 0.5) * Th / SP.RINGS, aa = k - ki; if (aa < 0 || aa >= 20) continue;
      const qq = aa / 20, rlx = SP.front(P, 1, ki);
      this.torus(nc, 'ring', A.copy(O).addScaledVector(aim, rlx * Us), aim, SP.hw(P, 1, rlx) * (1 + 0.3 * qq) * Us, 0.4, 0, HOTc, 170 / 255 * (1 - qq) * aC, 0);
    }
    for (let i = 0; i < Math.max(0, Math.round(18 * dens)); i++) {   // speed lines racing along it, all round
      const r = Lb.rngFor(inst.seed, i, 621), v = r.uniform(-1, 1), sln = r.uniform(40, 120), slx = ((k * r.uniform(0.04, 0.08) + r()) % 1) * df;
      coneDir(aim, 90, r() * Math.PI * 2, d3);
      const rad = Math.abs(v) * 0.9 * Us;
      A.copy(O).addScaledVector(aim, Math.max(0, slx - sln) * Us).addScaledVector(d3, SP.hw(P, 1, Math.max(0, slx - sln)) * rad);
      B.copy(O).addScaledVector(aim, slx * Us).addScaledVector(d3, SP.hw(P, 1, slx) * rad);
      this.tube(nc, A, B, 0, 0.8 * Us, Lb.mix(col, HOTc, 0.6), 200 / 255 * aC, 0);
    }
    if (k < SP.OUT + Th + 8) {   // the shock front
      const aF = k < SP.OUT + Th ? 1 : 1 - (k - SP.OUT - Th) / 8, hw = SP.hw(P, 1, df); A.copy(O).addScaledVector(aim, df * Us);
      this.torus(c, 'ring', A, aim, hw * Us, 1.6, 0, col, 120 / 255 * aF * 1.5, ink);
      this.torus(nc, 'ring', A, aim, hw * Us * 0.97, 0.8, 0, HOTc, 230 / 255 * aF, 0);
    }
  }
  if (aS > 0) {   // the sky split along its line
    const end = Math.min(Lr * 1.6, df * 1.6); B.copy(O).addScaledVector(aim, end * Us);
    this.tube(nc, O, B, 5 * Us, 5 * Us, col, 70 / 255 * aS, 0);
    this.tube(nc, O, B, 1.3 * Us, 1.3 * Us, HOTc, 230 / 255 * aS, 0);
    this.sphere(nc, B, 24 * Us * gk, HOTc, 160 / 255 * aS, 0);
  }
  const fist = A.copy(O).addScaledVector(aim, rf * 3 * easeO(Math.min(1, k / SP.OUT)) * Us).clone();   // the fist and its flash
  if (aC > 0) this.sphere(c, fist, rf * 2.4 * Us * gk, col, Math.min(1, 170 / 255 * aC + 0.3), ink);
  if (k < SP.FLASH) { const q = k / SP.FLASH, e = easeO(q);
    this.sphere(nc, fist, (30 + 60 * e) * Us * gk, HOTc, 1 - q, 0);
    for (let j = 0; j < 10; j++) { const r = Lb.rngFor(inst.seed, j, 631), th = r() * Math.PI * 2, ph = Math.acos(r() * 2 - 1);
      d3.set(Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th));
      this.tube(nc, fist, B.copy(fist).addScaledVector(d3, (20 + 50 * e) * Us), (7 + 10 * e) * 0.3 * Us, 0, HOTc, 240 / 255 * (1 - q), 0); } }
};
/* Paint every live effect onto its card(s) and place them. cam = the THREE camera, H = drawing buffer height (px).
   opts.hidden: hide body-bound FX (blinked out). */
Runner.prototype.draw = function (cam, H, opts) {
  const ctx = this.ctx; this.cards.forEach(c => { c.used = false; }); this.toons.forEach(t => { t.used = false; });
  if (!ctx) { this.cards.forEach(c => { c.mesh.visible = false; }); this.toons.forEach(t => { t.m.visible = t.h.visible = false; }); return; }
  const hidden = !!(opts && opts.hidden), tanH = Math.tan(cam.fov * Math.PI / 360); this._camPos = cam.position;
  _cr.set(1, 0, 0).applyQuaternion(cam.quaternion); _cu.set(0, 1, 0).applyQuaternion(cam.quaternion); _cf.set(0, 0, 1).applyQuaternion(cam.quaternion);
  const groups = new Map(), solid = [];
  for (const l of this.lanes) for (const inst of l.player.insts) {
    if (hidden && FXK.bodyBound(inst)) continue;
    this.initInst(l, inst);
    if (inst._r3) { solid.push([l, inst]); continue; }   // 3D cel-shaded shape, no card
    if (inst._s3) { solid.push([l, inst]); if (!strikeCard(inst)) continue; }   // 3D strike (+ a card for its ink / gritty parts)
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
      const keep = l.player.insts, unpatch = strikeCardPatch(g.insts); l.player.insts = g.insts;
      try { lays.forEach(ly => l.player.draw(q2, this.host, ly, 1, false)); } catch (err) { console.error('fx3d draw', err); }
      l.player.insts = keep; unpatch();
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
    try { if (inst._s3) this.drawStrike(l, inst, xs); else this.draw3d(l, inst, xs); } catch (err) { console.error('fx3d draw3d', err); } }
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

/* The live effects in world space, for the planet (Daniel 2026-11-25; fxlive.js -> planet.js planetFx): one entry per
   instance {inst, prim, moving (beam, or a travelling / non-attached motion), H (head, else centre), T (beam tail or
   null), r (m: beam half width, orb radius ...), dmg (its battle damage, 0 if it deals none), rEnd (pulse end radius,
   FX px)}. Scene metres on the flat sim plane (before the planet bend). */
Runner.prototype.worldFx = function () {
  const out = [], xf = {P: new THREE.Vector3(), q: new THREE.Quaternion(), Us: U, bill: false};
  if (!this.ctx) return out;
  for (const l of this.lanes) {
    this.cur = l;
    for (const inst of l.player.insts) {
      const fx = inst.fx, prim = fx.prim;
      if (inst.dead || inst.age < 0 || prim === 'ghost' || prim === 'particles') continue;
      if ((prim === 'sprite' || prim === 'glow') && inst.age >= inst.life) continue;
      try {
        this.initInst(l, inst); this.xform(l, inst, xf); this.axes(l, xf);
        const P = fx.params || {}, b = fx.battle || {}, mk = fx.motion && fx.motion.kind;
        const e = {inst, prim, moving: prim === 'beam' || (!!mk && mk !== 'attached' && mk !== 'orbit'), H: null, T: null, r: 0,
          dmg: b.deals_damage ? Math.max(0, +b.damage || 0) : 0, rEnd: 0};
        if (prim === 'beam') {
          const s = FXK.beamSegs(inst, this.host, 1); if (!s) continue;
          e.T = this.w3(inst, xf, s.tx, s.ty, 0, new THREE.Vector3()); e.H = this.w3(inst, xf, s.hx, s.hy, 0, new THREE.Vector3());
          e.r = Math.max(s.wH || 0, s.wT || 0, 2) / 2 * xf.Us;
        } else {
          let x = inst.x, y = inst.y;
          if (prim === 'ribbon') { const h = inst.hist || []; if (!h.length) continue; x = h[h.length - 1][0]; y = h[h.length - 1][1]; }
          e.H = this.w3(inst, xf, x, y, 0, new THREE.Vector3());
          e.r = (prim === 'sprite' ? Math.max(0.5, +P.radius || 3) : prim === 'glow' ? Math.max(+P.core_r || 0, (+P.r_end || 0) * 0.6, 2)
            : prim === 'ribbon' ? Math.max(1, +P.w_head || 4) / 2 : prim === 'pulse' ? 0 : 12) * xf.Us;
          if (prim === 'pulse') e.rEnd = Math.max(0, +P.r_end || 0) * xf.Us / U;
        }
        out.push(e);
      } catch (err) { console.error('fx3d worldFx', err); }
    }
  }
  this.cur = null; return out;
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

G.FX3D = {U, HURT, ANCHORS, LAYS, PIVOTS, DEF3D, MOVE_DEFAULTS, MOVE_PATHS, START_MODES, MOVE_EASES, RENDERS, CHUNKS, TOON_PRIMS, STRIKE_LIMBS,
  strikeKind, cfg3d, is3d, autoLay, layOf, moveCfg, byAction, Runner, movePlan, spotAround, easeU};
})(window);
