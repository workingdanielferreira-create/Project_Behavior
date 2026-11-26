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
  strike_limb: 'auto', strike_glow_pct: 50, strike_spin_deg: 90, strike_ground: true, blade_thick_pct: 35};
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
// Hyper FX (Daniel 2026-11-26, tools/fx/studio/hyperfx.js): punching FX riding the 3D fist + standalone impact FX
function hyperKind(fx) {
  if (!fx || fx.prim !== 'technique' || !G.HYPERFX) return '';
  return G.HYPERFX.isHyper(fx.params && fx.params.style) ? 'hyper' : '';
}
const TOON_NUMS = ['toon_bands', 'toon_core_pct', 'toon_shade_pct', 'toon_ink_m', 'toon_alpha_pct', 'toon_sides', 'laser_streak', 'laser_max_m',
  'laser_width_pct', 'beam_bulb_pct', 'beam_flare_pct', 'beam_wobble_pct', 'beam_width_pct', 'impact_shell_pct', 'impact_spikes', 'impact_spike_pct',
  'chunk_spread_pct', 'chunk_size_pct', 'strike_glow_pct', 'strike_spin_deg', 'blade_thick_pct'];
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
  if (strikeKind(fx) || bladeKind(fx) || gunKind(fx) || hyperKind(fx)) return true;
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
  'uniform float uR0; uniform float uR1; uniform float uTaper; uniform float uInflate; uniform vec4 uBend; uniform float uVA;',
  'attribute float aA;',
  'varying vec3 vN; varying vec3 vV; varying float vD; varying float vA;',
  'vec3 bendP( vec3 p ) {',
  '  if ( uBend.w <= 0.0 ) return p;',
  '  vec2 d = p.xz - uBend.xz; float r = length( d ); if ( r < 1e-5 ) return p;',
  '  float th = r / uBend.w, rr = uBend.w + p.y; vec2 dir = d / r;',
  '  return vec3( uBend.x + dir.x * sin( th ) * rr, cos( th ) * rr - uBend.w, uBend.z + dir.y * sin( th ) * rr );',
  '}',
  'void main() {',
  '  vA = uVA > 0.5 ? aA : 1.0;',
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
  'varying vec3 vN; varying vec3 vV; varying float vD; varying float vA;',
  'void main() {',
  // near the camera a shape fades out (a big shock ring / flash passing the lens never blanks the screen)
  '  float nf = smoothstep( 0.35, 1.8, vD ) * vA;',
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
    uAlpha: {value: 1}, uInk: {value: ink ? 1 : 0}, uR0: {value: 1}, uR1: {value: 1}, uTaper: {value: 0}, uInflate: {value: 0}, uVA: {value: 0}, uBend: {value: bendRef()}};
}
function makeToon(scene, kind, sides) {
  const geo = kind === 'band' ? bandGeo() : toonGeo(kind, sides);   // a band (sword FX) has its own changing geometry
  const mk = ink => { const m = new THREE.ShaderMaterial({uniforms: toonUniforms(ink), vertexShader: TOON_VS, fragmentShader: TOON_FS,
    transparent: true, depthWrite: true, side: ink ? THREE.BackSide : THREE.FrontSide}); m.uniforms.uVA.value = kind === 'band' ? 1 : 0; return m; };
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
  this.toons.forEach(t => { [t.m, t.h].forEach(x => { if (x.parent) x.parent.remove(x); x.material.dispose(); }); if (t.key === 'band0') t.m.geometry.dispose(); }); this.toons = [];
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
  // FX Studio 3D's "Start at" rides as "3d:<id>" (byAction), so strip that BEFORE the figure / target check: a
  // "3d:target" used to miss it, find no bone and fall back to the body centre (Daniel 2026-11-26)
  const id = typeof n === 'string' && n.indexOf('3d:') === 0 ? n.slice(3) : n;
  if (id === 'figure') return l.fig.slice();
  if (id === 'target') return l.target.slice();
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
  l.tgtLat = ctx.target ? _v.copy(ctx.target.centre).sub(l.O).dot(l.L) : l.figLat;   // the target off the lane's plane
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
  inst._s3 = inst._r3 ? strikeKind(inst.fx) || bladeKind(inst.fx) || gunKind(inst.fx) || hyperKind(inst.fx) : ''; if (inst._s3) { inst._r3 = false; inst._lay = inst._c.lay === 'auto' ? 'side' : inst._lay; }
  inst._pv = inst._c.pivot === 'figure' ? l.fig.slice() : [inst.x, inst.y];
  const an = typeof inst.fx.anchor === 'string' ? inst.fx.anchor.replace(/^3d:/, '') : '';
  const W = an && an !== 'figure' && an !== 'target' && this.ctx ? this.anchorWorld(an, new THREE.Vector3()) : null;
  inst._tgt = an === 'target';   // started ON the target: it lies where the target is, not in the fighter's plane
  inst._lat = W ? _v.copy(W).sub(l.O).dot(l.L) : inst._tgt ? num(l.tgtLat, l.figLat) : l.figLat; inst._latF = l.figLat;
};
// where an instance's card lies: pivot (world), turn, metres per 2D px
Runner.prototype.xform = function (l, inst, out) {
  const c = inst._c, lay = inst._lay, Us = U * c.size_pct / 100;
  const lat = inst._tgt && FXK.bodyBound(inst) ? num(l.tgtLat, inst._lat) : inst._lat + (FXK.bodyBound(inst) ? l.figLat - inst._latF : 0);
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
  if (inst._s3 !== 'punch' && inst._s3 !== 'kick') return false;
  const P = inst.fx.params || {}, H = G.HITFX;
  return ['fx_motion', 'fx_impact', 'fx_env'].some(k => { const v = H.look(P, k); return v === 'ink' || v === 'gritty'; });
}
// while a strike's card is painted: its energy parts and impact frame are 3D, so the card leaves them out
function strikeCardPatch(insts) {
  const out = [];
  insts.forEach(i => {
    if (i._s3 !== 'punch' && i._s3 !== 'kick') return; const P = i.fx.params; if (!P || out.some(x => x[0] === P)) return;
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
  if (kind === 'hyper') return this.drawHyper(l, inst, xf);
  if (kind === 'gun') return this.drawGun(l, inst, xf);
  if (kind === 'ki') return this.drawKi(l, inst, xf);
  if (kind !== 'punch' && kind !== 'kick') return this.drawBlade(l, inst, xf);
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
/* ---- Hyper FX (Daniel 2026-11-26: "10 punching FX and 10 impact FX, anime hyper action, stylised") ----
   hyperfx.js gives each style as a list of shapes in a local blow frame [f, v, s] (px); here they become cel-shaded 3D
   shapes. A punching FX stands on its anchor's REAL 3D point (default the right hand) and reads that point's path tick by
   tick, so afterimages, trails and jets follow whatever punch clip plays; forward = toward the target (else the way the
   fist moves, else the aim). An impact stands where it was spawned (normally ON the target), forward = caster -> it. */
const _hF = new THREE.Vector3(), _hV = new THREE.Vector3(), _hS = new THREE.Vector3(), _hO = new THREE.Vector3(), _hA = new THREE.Vector3(), _hB = new THREE.Vector3();
Runner.prototype.drawHyper = function (l, inst, xf) {
  const H = G.HYPERFX, ctx = this.ctx; if (!H || !ctx) return;
  const P = inst.fx.params || {}, c = inst._c, Us = xf.Us, punch = H.isPunch(P.style);
  const an = typeof inst.fx.anchor === 'string' ? inst.fx.anchor.replace(/^3d:/, '') : '';
  const O = _hO;
  let id = null;
  if (punch) {   // the fist: its anchor's real 3D point, kept per tick
    id = an && an !== 'figure' && an !== 'target' && this.anchorWorld(an, _hA) ? an : 'haR';
    this.boneRec(inst, [id]);
    if (!this.boneAt(inst, id, inst.age, O)) this.w3(inst, xf, inst.x, inst.y, 0, O);
  } else this.w3(inst, xf, inst.x, inst.y, 0, O);
  // forward
  const F = _hF.set(0, 0, 0);
  if (punch) {
    if (ctx.target) { F.copy(ctx.target.centre).sub(O); if (F.dot(l.X) < 0.05 * F.length()) F.set(0, 0, 0); }
    if (F.lengthSq() < 1e-6 && this.boneAt(inst, id, inst.age - 2, _hA)) F.copy(O).sub(_hA);
  } else { F.copy(O).sub(ctx.centre); F.y *= 0.35; }
  if (F.lengthSq() < 1e-6) F.copy(xf.ax);
  F.normalize();
  const V = _hV.copy(UPV).addScaledVector(F, -F.y); if (V.lengthSq() < 1e-6) V.copy(l.L).cross(F); V.normalize();
  const S = _hS.crossVectors(F, V).normalize();
  const loc = (W, out) => { _hA.copy(W).sub(O); out.push([_hA.dot(F) / Us, _hA.dot(V) / Us, _hA.dot(S) / Us]); };
  const path = []; let sp = 0;
  if (punch) {
    for (let k = 12; k >= 0; k--) if (this.boneAt(inst, id, inst.age - k, _hB)) loc(_hB, path);
    const n = path.length; if (n > 1) sp = Math.hypot(path[n - 1][0] - path[n - 2][0], path[n - 1][1] - path[n - 2][1], path[n - 1][2] - path[n - 2][2]);
  }
  const gy = (num(l.groundY, 0) + 0.03 - O.y) / Us / Math.max(0.3, V.y);
  const shapes = H.parts(inst, this.host, {t: inst.age, ps: 1, path, sp, gy, solo: !ctx.target});
  const w = (p, out) => out.copy(O).addScaledVector(F, p[0] * Us).addScaledVector(V, p[1] * Us).addScaledVector(S, p[2] * Us);
  const dirW = (d, out) => out.set(0, 0, 0).addScaledVector(F, d[0]).addScaledVector(V, d[1]).addScaledVector(S, d[2]).normalize();
  for (const e of shapes) {
    const cc = e.core === false ? noCore(c) : c, ink = (e.ink == null ? 1 : e.ink) * c.toon_ink_m, P0 = w(e.p, new THREE.Vector3());
    if (e.k === 'sph') {
      let st = null;
      if (e.st > 1.01 && e.d) { const q = new THREE.Quaternion().setFromUnitVectors(XV, dirW(e.d, _hA)); st = {q, x: e.st, y: 1, z: 1}; }
      this.sphere(cc, P0, e.r * Us, e.c, e.a, ink, st);
    } else if (e.k === 'tube') this.tube(cc, P0, w(e.q, new THREE.Vector3()), e.r * Us, e.r1 * Us, e.c, e.a, ink);
    else if (e.k === 'ring') this.torus(cc, 'ring', P0, dirW(e.n, new THREE.Vector3()), e.r * Us, 1, 0, e.c, e.a, ink);
    else {   // a chunk (shard / cube / ball)
      const t = this.paint(this.toon(e.k, 0), cc, e.c, e.a, ink), rt = e.rot || [0, 0, 0];
      [t.m, t.h].forEach(x => { x.position.copy(P0); x.rotation.set(rt[0], rt[1], rt[2]); x.scale.setScalar(e.r * Us); x.material.uniforms.uTaper.value = 0; });
    }
  }
};
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
/* ---- 3D sword FX (Daniel 2026-11-25, batch 2 "sword slashes + crescents") ----
   Slash-family techniques (every SWORDFX.CUTS style incl. the combos), straight_slash, crescent_wave, the six crescent
   styles, forward_thrust and the `arc` kind. The blade itself is a BAND: FX Studio's crescent outline (outer rim -> inner
   edge, slice by slice) given a real bevelled thickness (blade_thick_pct of its width, a lens section) with its tail fading
   per vertex, an aura band round it, a white-hot leading edge and (crescents) a dark core and flame tongues off its back.
   Around it: the head glint, air lines, the afterglow path, sparks (thrown out of the plane too, with gravity), hit marks,
   launch bursts, X glints, embers, end shards, the drag's contact point and the moonfall's slam on the floor. Ground
   crescents (drag / fall) stand on the floor (strike_ground). Hits stay FX Studio's own (unchanged). */
const BAND_MAX = 64, BAND_IX = [];
function bandIndex(flip) {
  if (BAND_IX[flip]) return BAND_IX[flip];
  // 6 vertices a row: the +nz face (outer, ridge, inner) and the -nz face (inner, ridge, outer), each face its own
  // vertices so it shades flat-bright with a light ridge (shared edges made the whole face fall into the shade band)
  const ix = [];
  for (let i = 0; i < BAND_MAX - 1; i++) for (const r of [0, 1, 3, 4]) {
    const a = i * 6 + r, b = a + 1, c = a + 6, d = b + 6;
    if (flip) ix.push(a, b, c, b, d, c); else ix.push(a, c, b, b, c, d);
  }
  return (BAND_IX[flip] = new THREE.BufferAttribute(new Uint16Array(ix), 1));
}
function bandGeo() {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(BAND_MAX * 18), 3).setUsage(THREE.DynamicDrawUsage));
  g.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(BAND_MAX * 18), 3).setUsage(THREE.DynamicDrawUsage));
  g.setAttribute('aA', new THREE.BufferAttribute(new Float32Array(BAND_MAX * 6), 1).setUsage(THREE.DynamicDrawUsage));
  g.setIndex(bandIndex(0)); return g;
}
const BLADE_STYLES = ['straight_slash', 'crescent_wave', 'forward_thrust'];
function bladeKind(fx) {
  if (!fx) return '';
  if (fx.prim === 'arc') return 'arc';
  if (fx.prim !== 'technique') return '';
  const s = fx.params && fx.params.style, SW = G.SWORDFX, CR = G.CRESCENTFX;
  if (SW && SW.CUTS[s]) return 'slash';
  if (s === 'straight_slash') return 'line';
  if (s === 'crescent_wave') return 'wave';
  if (s === 'forward_thrust') return 'thrust';
  if (CR && CR.STYLES.indexOf(s) >= 0) return 'crescent';
  return '';
}
const _bm = new THREE.Vector3(), _bo = new THREE.Vector3(), _bs = new THREE.Vector3(), _bc = new THREE.Vector3();
/* rows [{O, I, th (m), a}] -> a closed lens-section band (outer, +nz face, inner, -nz face) */
Runner.prototype.band = function (c, rows, nz, rgb, alpha, ink) {
  const n = Math.min(BAND_MAX, rows.length); if (n < 2 || alpha <= 0.004) return null;
  const t = this.paint(this.toon('band', 0), c, rgb, alpha, ink), g = t.m.geometry, P = g.attributes.position.array, A = g.attributes.aA.array;
  for (let i = 0; i < BAND_MAX; i++) {
    const r = rows[Math.min(i, n - 1)], th = Math.max(0, r.th || 0), a = r.a == null ? 1 : Math.max(0, Math.min(1, r.a)), k = i * 18;
    _bm.copy(r.O).add(r.I).multiplyScalar(0.5);
    const V = [r.O, null, r.I, r.I, null, r.O];
    for (let j = 0; j < 6; j++) {
      const q = k + j * 3;
      if (V[j]) { P[q] = V[j].x; P[q + 1] = V[j].y; P[q + 2] = V[j].z; }
      else { const sg = j === 1 ? th : -th; P[q] = _bm.x + nz.x * sg; P[q + 1] = _bm.y + nz.y * sg; P[q + 2] = _bm.z + nz.z * sg; }
      A[i * 6 + j] = a;
    }
  }
  // winding so the faces point out (the ink hull inflates along the normals)
  const r0 = rows[0], r1 = rows[n - 1];
  _bs.copy(r1.O).add(r1.I).sub(r0.O).sub(r0.I); _bo.copy(rows[n >> 1].O).sub(rows[n >> 1].I);
  const flip = _bc.crossVectors(_bs, _bo).dot(nz) > 0 ? 1 : 0;
  if (g.index !== bandIndex(flip)) g.setIndex(bandIndex(flip));
  g.attributes.position.needsUpdate = true; g.attributes.aA.needsUpdate = true;
  g.computeVertexNormals(); g.setDrawRange(0, (n - 1) * 24);
  [t.m, t.h].forEach(x => { x.position.set(0, 0, 0); x.quaternion.identity(); x.scale.set(1, 1, 1); x.material.uniforms.uTaper.value = 0; });
  return t;
};
// a thin lens-section line through world points pts, half width r (m)
Runner.prototype.line3 = function (c, pts, r, nz, rgb, alpha, ink, aFn) {
  if (pts.length < 2 || r <= 0) return null;
  const rows = pts.map((p, i) => {
    const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)], tg = _bs.copy(b).sub(a);
    const n = _bo.crossVectors(tg, nz); if (n.lengthSq() < 1e-12) n.set(0, 1, 0); n.normalize();
    return {O: p.clone().addScaledVector(n, r), I: p.clone().addScaledVector(n, -r), th: r, a: aFn ? aFn(i / (pts.length - 1)) : 1};
  });
  return this.band(c, rows, nz, rgb, alpha, ink);
};
// a diamond streak A -> B (thick in the middle), as two cones
Runner.prototype.diamond3 = function (c, A, B, w, rgb, a, ink) {
  const M = _bm.copy(A).add(B).multiplyScalar(0.5).clone();
  this.tube(c, A, M, 0, w, rgb, a, ink); this.tube(c, M, B, w, 0, rgb, a, ink);
};
// FX Studio's hit marks (swordfx hitMarks): an X glint, a ring and a flash where each hit landed
Runner.prototype.hitMarks3 = function (inst, xf, WP, col, u2, dirf, gk) {
  const Lb = SLib(), Gm = G.SWORDFX.geo, c = inst._c, nc = noCore(c), Us = xf.Us, t = inst.age, HOTc = [255, 255, 255];
  (inst.tq_hits || []).forEach(h => {
    const k = t - h[2]; if (k < 0 || k >= Gm.HIT_MARK_LIFE) return;
    const u0 = dirf ? dirf(h[2]) : u2, f = 1 - k / Gm.HIT_MARK_LIFE, e = easeO(k / 4), L = (18 + 10 * e) * Us, C = WP(h[0], h[1]);
    [u0, FXK.rot(u0.slice(), 70)].forEach(u => {
      const d = this.dir3(xf, u);
      this.diamond3(nc, C.clone().addScaledVector(d, -L), C.clone().addScaledVector(d, L), 1.6 * Us * f + 0.01, col, 220 / 255 * f, 0);
    });
    this.torus(nc, 'ring', C, _cf, (4 + 20 * easeO(k / Gm.HIT_MARK_LIFE)) * Us, 0.5, 0, col, 200 / 255 * f, 0);
    this.sphere(nc, C, 14 * Us * f * gk, HOTc, 230 / 255 * f, 0);
  });
};
Runner.prototype.dir3 = function (xf, u) { const d = xf.ax.clone().multiplyScalar(u[0]).addScaledVector(xf.ay, -u[1]); return d.lengthSq() > 1e-12 ? d.normalize() : d.copy(xf.ax); };
// a 2D spark (start, 2D velocity, drag, age, gravity px/tick^2) thrown out of the plane by vz, streaked along its motion
Runner.prototype.spark3 = function (c, xf, P0, vx, vy, vz, drag, k, grav, len, r, rgb, a, gy) {
  const Us = xf.Us, fd = SLib().dragDist(drag, k), dk = Math.pow(drag, k);
  const v = this.dir3(xf, [vx, vy]).multiplyScalar(Math.hypot(vx, vy) * Us).addScaledVector(xf.az, vz * Us);
  const B = P0.clone().addScaledVector(v, fd); B.y -= 0.5 * grav * k * k * Us;
  const cv = v.clone().multiplyScalar(dk); cv.y -= grav * k * Us;
  const A = B.clone().addScaledVector(cv, -len);
  if (gy != null && B.y < gy + 0.03) { B.y = gy + 0.03; A.y = Math.max(A.y, gy + 0.03); }
  this.tube(c, A, B, 0, r, rgb, a, 0);
};
Runner.prototype.drawBlade = function (l, inst, xf) {
  const kind = inst._s3, Lb = SLib(), cs = kind === 'arc' ? FXK.colorPair(inst.fx, this.lut) : Lb.colours(inst, this.host), c = inst._c, gk = c.strike_glow_pct / 100;
  const gy = c.strike_ground ? l.groundY : null;
  let dy = 0;
  if (kind === 'crescent' && c.strike_ground && G.CRESCENTFX.onGround(inst)) {   // a ground crescent stands on the floor
    const gp = G.CRESCENTFX.groundPoint(inst, 1); dy = l.groundY + 0.02 - this.w3(inst, xf, gp[0], gp[1], 0, _bc).y;
  }
  const WP = (x, y, o) => { o = this.w3(inst, xf, x, y, 0, o || new THREE.Vector3()); o.y += dy; return o; };
  const A = {l, inst, xf, WP, col: cs[0], bright: cs[1], deep: cs[2] || cs[0], gk, gy, kth: c.blade_thick_pct / 100};
  if (kind === 'slash') this.slash3(A);
  else if (kind === 'line') this.sline3(A);
  else if (kind === 'wave') this.wave3(A);
  else if (kind === 'crescent') this.crescent3(A);
  else if (kind === 'thrust') this.thrust3(A);
  else if (kind === 'arc') this.arc3(A);
};
/* slash family (swordfx drawSlash / drawCut / drawCross) */
Runner.prototype.slash3 = function (A) {
  const {inst, xf, WP, col, bright, gk} = A, SW = G.SWORDFX, Gm = SW.geo, Lb = SLib(), P = inst.fx.params, fr = Lb.frame(inst);
  const starts = Gm.cutStarts(P), end = Lb.swing(P) + Gm.fadeT(P) + Gm.SPARK_LIFE, geos = starts.map((s, ci) => new Gm.SlashGeo(inst, 1, ci));
  starts.forEach((s, ci) => { const t = inst.age - s; if (t >= 0 && t < end) this.cut3(A, geos[ci], fr, t, ci); });
  if (P.style === 'combo_cross') this.cross2(A, fr, geos, starts);
  const dirf = starts.length > 1 ? b => { let ci = 0; starts.forEach((s, i) => { if (s <= b) ci = i; }); return fr.d(geos[ci].d[0], geos[ci].d[1]); } : null;
  this.hitMarks3(inst, xf, WP, col, fr.d(geos[0].d[0], geos[0].d[1]), dirf, gk);
};
Runner.prototype.cut3 = function (A, g, fr, t, ci) {
  const {inst, xf, WP, col, bright, gk, gy, kth} = A, Lb = SLib(), P = inst.fx.params, c = inst._c, nc = noCore(c), Us = xf.Us, nz = xf.az, ink = c.toon_ink_m, HOTc = [255, 255, 255];
  const st = g.state(t), tail = st[0], head = st[1], ga = st[2], R = g.R, Ts = g.Ts, sl = g.slices(t);
  const W = (s, r) => { const q = g.local(s, r), p = fr.w(q[0], q[1]); return WP(p[0], p[1]); };
  if (sl.length) {
    if (t <= Ts + 6) { const bf = ga * (t <= Ts ? 1 : 1 - (t - Ts) / 6); this.sphere(nc, W(tail + (head - tail) * 0.7, R), Math.min(0.9 * R, 36) * Us * gk * 0.8, col, 80 / 255 * bf, 0); }
    const hz = 5;
    this.band(nc, sl.map(q => ({O: W(q[0], R + 0.3 * q[2] + hz), I: W(q[0], R - 0.7 * q[2] - hz), th: q[2] * kth * Us * 0.3, a: ga * Math.pow(q[1], 0.9)})), nz, col, 70 / 255, 0);
    this.band(c, sl.map(q => ({O: W(q[0], R + 0.3 * q[2]), I: W(q[0], R - 0.7 * q[2]), th: q[2] * kth * Us * 0.5, a: ga * Math.pow(q[1], 0.9)})), nz, Lb.mix(col, bright, 0.55), 235 / 255, ink);
    this.band(nc, sl.map(q => { const e = Math.max(1.2, 0.3 * q[2]); return {O: W(q[0], R + 0.3 * q[2] + 0.3), I: W(q[0], R + 0.3 * q[2] - e), th: q[2] * kth * Us * 0.55, a: Math.pow(ga * Math.pow(q[1], 0.9), 1.2)}; }), nz, HOTc, 1, 0);
  }
  if (t <= Ts + 4 && head - tail > 0.05) {   // air lines riding the cut
    const sf = t <= Ts ? 1 : 1 - (t - Ts) / 4;
    for (let k = 0; k < 3; k++) { const r = R + 5 + 4 * k, sa = Math.max(tail, head - 0.45 + 0.1 * k), sb = head - 0.05; if (sb - sa < 0.02) continue;
      const pl = []; for (let j = 0; j < 10; j++) pl.push(W(sa + (sb - sa) * j / 9, r));
      this.line3(nc, pl, 0.55 * Us, nz, col, 120 / 255 * sf * (1 - k * 0.25), 0, u => Math.sin(Math.PI * u)); }
  }
  const k2 = (t - (Ts - 1)) / 10;   // the whole path, glowing as it ends
  if (k2 >= 0 && k2 < 1) { const path = []; for (let j = 0; j < 25; j++) path.push(W(j / 24, R + 0.1 * g.W));
    this.line3(nc, path, 1.75 * Us, nz, col, 160 / 255 * (1 - k2), 0); this.line3(nc, path, 0.6 * Us, nz, HOTc, Math.pow(1 - k2, 2), 0); }
  const k3 = (t - Ts) / 12;   // a pressure line widening off it
  if (k3 >= 0 && k3 < 1) { const rr = R * (1 + 0.35 * easeO(k3)), pw = []; for (let j = 0; j < 21; j++) pw.push(W(0.1 + 0.8 * j / 20, rr));
    this.line3(nc, pw, (1 * (1 - k3) + 0.1) * Us, nz, col, 130 / 255 * (1 - k3), 0, u => Math.sin(Math.PI * u)); }
  if (t <= Ts + 3) {   // the head glint
    const fa = t <= Ts ? 1 : 1 - (t - Ts) / 3, hp = W(head, R), pp = W(Math.max(0, head - 0.03), R), u = hp.clone().sub(pp); if (u.lengthSq() < 1e-10) u.copy(xf.ax); u.normalize();
    this.sphere(c, hp, 7 * Us * gk, col, Math.min(1, 200 / 255 * fa + 0.2), ink * 0.5); this.sphere(nc, hp, 6 * Us * gk, HOTc, fa, 0);
    const v = _bo.crossVectors(u, nz).normalize().clone();
    this.diamond3(nc, hp.clone().addScaledVector(u, -16 * Us), hp.clone().addScaledVector(u, 16 * Us), 0.9 * Us, HOTc, 230 / 255 * fa, 0);
    this.diamond3(nc, hp.clone().addScaledVector(v, -6 * Us), hp.clone().addScaledVector(v, 6 * Us), 0.7 * Us, HOTc, 230 / 255 * fa, 0);
  }
  const nsp = Math.max(0, Math.round(16 * (+P.density || 1)));   // sparks thrown off the edge, out of the plane too
  for (let i = 0; i < nsp; i++) {
    const rg = Lb.rngFor(inst.seed, i, 7 + 100 * ci), b = 1 + rg() * (Ts - 1), life = 10 + rg() * 10, kk = t - b; if (kk < 0 || kk >= life) continue;
    const sb2 = easeO(b / Ts), q0 = g.local(sb2, R + 0.2 * g.W), q1 = g.local(Math.min(1, sb2 + 0.02), R + 0.2 * g.W), p0 = fr.w(q0[0], q0[1]), p1 = fr.w(q1[0], q1[1]);
    let tx = p1[0] - p0[0], ty = p1[1] - p0[1]; const nn = Math.hypot(tx, ty) || 1; tx /= nn; ty /= nn;
    const ph = g.phi(sb2), rd = fr.d(ph[0], ph[1]), sp = rg.uniform(2.5, 6.5), out = rg.uniform(0.1, 0.7), vz = rg.uniform(-0.8, 0.8) * sp, q = kk / life;
    this.spark3(nc, xf, WP(p0[0], p0[1]), (tx + rd[0] * out) * sp, (ty + rd[1] * out) * sp, vz, 0.88, kk, 0.22, 1.6, 0.8 * Us, Lb.mix(HOTc, col, q), 1 - q, gy);
  }
};
Runner.prototype.cross2 = function (A, fr, geos, starts) {   // combo_cross: the X flaring where the two cuts cross
  const {inst, xf, WP, col, gk} = A, Lb = SLib(), Gm = G.SWORDFX.geo, c = inst._c, nc = noCore(c), Us = xf.Us, HOTc = [255, 255, 255];
  const a = inst.age - (starts[1] + Lb.swing(inst.fx.params)); if (a < 0 || a >= Gm.CROSS_LIFE) return;
  const ga = geos[0], gb = geos[1], pa = ga.local(0.5, ga.R), pb = gb.local(0.5, gb.R), m = fr.w((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2), C = WP(m[0], m[1]);
  const q = a / Gm.CROSS_LIFE, e = easeO(a / 6), L = (0.9 + 0.5 * e) * ga.R * Us;
  [ga, gb].forEach(gg => { const d = this.dir3(xf, fr.d(gg.d[0], gg.d[1]));
    this.diamond3(c, C.clone().addScaledVector(d, -L), C.clone().addScaledVector(d, L), 3 * Us * (1 - q) + 0.01, col, 230 / 255 * (1 - q), c.toon_ink_m * 0.5); });
  this.sphere(nc, C, (20 + 26 * e) * Us * (1 - q) * gk, HOTc, 240 / 255 * (1 - q), 0);
  this.torus(nc, 'ring', C, xf.az, (8 + 0.9 * ga.R * easeO(q)) * Us, 0.6, 0, col, 200 / 255 * (1 - q), 0);
  for (let i = 0; i < 10; i++) { const r = Lb.rngFor(inst.seed, i, 31), life = 10 + 8 * r(); if (a >= life) continue;
    const an = r.uniform(0, Math.PI * 2), sp = r.uniform(3, 8), qq = a / life;
    this.spark3(nc, xf, C, Math.cos(an) * sp, Math.sin(an) * sp, r.uniform(-1, 1) * sp, 0.86, a, 0, 1.8, 0.75 * Us, Lb.mix(HOTc, col, qq), 1 - qq, null); }
};
/* straight_slash (slashline.js) */
Runner.prototype.sline3 = function (A) {
  const {inst, xf, WP, col, bright, gk, gy, kth} = A, Lb = SLib(), SL = G.SLASHLINE, P = inst.fx.params, t = inst.age, c = inst._c, nc = noCore(c), Us = xf.Us, nz = xf.az, ink = c.toon_ink_m, HOTc = [255, 255, 255];
  const S = SL.size(inst, 1), g = new SL.Geo(inst, S), fr = Lb.frame(inst), Ts = Lb.swing(P), hd = SL.hold(P);
  const sp = SL.span(P, t), lo = sp[0], hi = sp[1], head = sp[2], ga = sp[3], wf = sp[4];
  const AT = s => { const p = fr.w.apply(fr, g.at(s)); return WP(p[0], p[1]); };
  const E = (s, off) => { const p = g.at(s), tg = g.tangent(s), q = fr.w(p[0] - tg[1] * off, p[1] + tg[0] * off); return WP(q[0], q[1]); };
  if (t < Ts + hd + SL.fade(P) && hi - lo > 0.004 && ga > 0.01) {
    const sl = SL.slices(g, lo, hi, wf), uA = s => head !== null && hi > lo ? 1 - Math.abs(s - head) / Math.max(1e-6, hi - lo) : 0.7;
    if (t <= Ts + 6) this.sphere(nc, AT((lo + hi) / 2), Math.min(0.45 * g.L, 40 * S) * Us * gk * 0.8, col, 80 / 255 * (t <= Ts ? 1 : 1 - (t - Ts) / 6) * ga, 0);
    const hz = 5 * S;
    this.band(nc, sl.map(q => ({O: E(q[0], 0.5 * q[1] + hz), I: E(q[0], -0.5 * q[1] - hz), th: q[1] * kth * Us * 0.3, a: ga * (0.35 + 0.65 * uA(q[0]))})), nz, col, 70 / 255, 0);
    this.band(c, sl.map(q => ({O: E(q[0], 0.5 * q[1]), I: E(q[0], -0.5 * q[1]), th: q[1] * kth * Us * 0.5, a: ga * (0.35 + 0.65 * uA(q[0]))})), nz, Lb.mix(col, bright, 0.55), 235 / 255, ink);
    this.band(nc, sl.map(q => { const e = Math.max(0.8 * S, 0.22 * q[1]); return {O: E(q[0], e * 0.5), I: E(q[0], -e * 0.5), th: q[1] * kth * Us * 0.56, a: Math.pow(ga * (0.35 + 0.65 * uA(q[0])), 1.2)}; }), nz, HOTc, 1, 0);
    if (t <= Ts + 4) { const sf = t <= Ts ? 1 : 1 - (t - Ts) / 4;
      for (let k = 0; k < 2; k++) [1, -1].forEach(sd => { const off = sd * (g.W * 0.5 + (5 + 5 * k) * S), a0 = lo + (hi - lo) * (0.1 + 0.1 * k), a1 = hi - (hi - lo) * 0.05; if (a1 - a0 < 0.02) return;
        const pl = []; for (let j = 0; j < 10; j++) pl.push(E(a0 + (a1 - a0) * j / 9, off));
        this.line3(nc, pl, 0.55 * S * Us, nz, col, 110 / 255 * sf * (1 - 0.35 * k), 0, u => Math.sin(Math.PI * u)); }); }
  }
  const k2 = (t - (Ts - 1)) / 10;
  if (k2 >= 0 && k2 < 1) { const path = []; for (let j = 0; j < 25; j++) path.push(AT(j / 24));
    this.line3(nc, path, 1.75 * S * Us, nz, col, 160 / 255 * (1 - k2), 0); this.line3(nc, path, 0.6 * S * Us, nz, HOTc, Math.pow(1 - k2, 2), 0); }
  const k3 = (t - Ts) / 12;
  if (k3 >= 0 && k3 < 1) { const off3 = g.W * 0.5 + 18 * S * easeO(k3);
    [1, -1].forEach(sd => { const pl = []; for (let j = 0; j <= 20; j++) pl.push(E(0.1 + 0.8 * j / 20, sd * off3));
      this.line3(nc, pl, (0.9 * S * (1 - k3) + 0.1) * Us, nz, col, 110 / 255 * (1 - k3), 0, u => Math.sin(Math.PI * u)); }); }
  const frm = SL.from_(P);
  if (t <= Ts + 3) { const fa = t <= Ts ? 1 : 1 - (t - Ts) / 3, kk = Lb.easeOut3(Math.min(t, Ts) / Ts);
    (frm === 'end' ? [1 - kk] : frm === 'centre' ? [0.5 - 0.5 * kk, 0.5 + 0.5 * kk] : [kk]).forEach(hs => {
      const hp = AT(hs); let u = this.dir3(xf, fr.d.apply(fr, g.tangent(hs))); if (frm === 'end' || (frm === 'centre' && hs < 0.5)) u.negate();
      this.sphere(c, hp, 7 * S * Us * gk, col, Math.min(1, 200 / 255 * fa + 0.2), ink * 0.5); this.sphere(nc, hp, 6 * S * Us * gk, HOTc, fa, 0);
      const v = _bo.crossVectors(u, nz).normalize().clone();
      this.diamond3(nc, hp.clone().addScaledVector(u, -16 * S * Us), hp.clone().addScaledVector(u, 16 * S * Us), 0.9 * S * Us, HOTc, 230 / 255 * fa, 0);
      this.diamond3(nc, hp.clone().addScaledVector(v, -6 * S * Us), hp.clone().addScaledVector(v, 6 * S * Us), 0.7 * S * Us, HOTc, 230 / 255 * fa, 0); }); }
  const nSp = Math.max(0, Math.round(16 * (+P.density || 1)));
  for (let i = 0; i < nSp; i++) {
    const r = Lb.rngFor(inst.seed, i, 211), b = 1 + r() * (Ts - 1), life = 10 + r() * 10, kt = t - b; if (kt < 0 || kt >= life) continue;
    const kb = Lb.easeOut3(b / Ts), sb = frm === 'end' ? 1 - kb : frm === 'centre' ? 0.5 + (i % 2 ? 0.5 : -0.5) * kb : kb;
    const p0 = fr.w.apply(fr, g.at(sb)), td = fr.d.apply(fr, g.tangent(sb)); let tx = td[0], ty = td[1];
    if (frm === 'end' || (frm === 'centre' && i % 2 === 0)) { tx = -tx; ty = -ty; }
    const side = r.uniform(-0.7, 0.7), spd = r.uniform(2.5, 6.5) * S, vz = r.uniform(-0.8, 0.8) * spd, q = kt / life;
    this.spark3(nc, xf, WP(p0[0], p0[1]), (tx - ty * side) * spd, (ty + tx * side) * spd, vz, 0.88, kt, 0.22 * S, 1.6, 0.8 * S * Us, Lb.mix(HOTc, col, q), 1 - q, gy);
  }
  this.hitMarks3(inst, xf, WP, col, SL.cutDir(inst), null, gk);
};
/* one crescent moon in 3D (crescentfx blade / swordfx drawWave): fr = its 2D frame (w(x, y)) */
Runner.prototype.moon3 = function (A, fr, R, W, k, tl, mi, fade, half) {
  const {inst, xf, WP, col, deep, gk, kth} = A, Lb = SLib(), CR = G.CRESCENTFX, c = inst._c, nc = noCore(c), Us = xf.Us, nz = xf.az, ink = c.toon_ink_m, HOTc = [255, 255, 255];
  if (fade <= 0) return;
  const ph = (inst.seed % 1000) * 0.01 + mi * 1.7, pts = CR.pts(R, W, k, 20, half), P3 = (x, y) => { const p = fr.w(x, y); return WP(p[0], p[1]); };
  const rowsAt = (o0, o1, thk) => pts.map(q => ({O: P3(q[1][0] - q[2][0] * q[3] * o0, q[1][1] - q[2][1] * q[3] * o0), I: P3(q[1][0] - q[2][0] * q[3] * o1, q[1][1] - q[2][1] * q[3] * o1), th: q[3] * kth * Us * thk}));
  this.band(nc, pts.map(q => ({O: P3(q[1][0] + q[2][0] * 6 * k, q[1][1] + q[2][1] * 6 * k), I: P3(q[1][0] - q[2][0] * (q[3] + 4 * k), q[1][1] - q[2][1] * (q[3] + 4 * k)), th: q[3] * kth * Us * 0.3})), nz, col, 80 / 255 * fade, 0);
  this.band(c, rowsAt(0, 1, 0.5), nz, Lb.mix(col, HOTc, 0.25), 235 / 255 * fade, ink);
  const e = half ? pts.length : pts.length - 2;   // the dark core, standing just proud of both faces
  this.band(nc, pts.slice(2, e).map(q => { const mm = q[3] * (0.88 + 0.2 * Lb.flame(q[0], tl, ph)); return {O: P3(q[1][0] - q[2][0] * q[3] * 0.3, q[1][1] - q[2][1] * q[3] * 0.3), I: P3(q[1][0] - q[2][0] * mm, q[1][1] - q[2][1] * mm), th: q[3] * kth * Us * 0.56}; }), nz, Lb.mix(deep, col, 0.3), 240 / 255 * fade, 0);
  const front = []; pts.forEach(q => { if (Math.abs(q[0]) < 0.85) front.push(P3(q[1][0], q[1][1])); });
  this.line3(nc, front, 1.1 * k * Us, nz, HOTc, fade, 0, u => Math.pow(Math.sin(Math.PI * u), 0.5));
  for (let i = 0; i < 11; i++) {   // flame tongues off its back, fanning out of the plane
    const v = -0.9 + 1.8 * i / 10, r = Lb.rngFor(inst.seed, i, 17 + 40 * mi), u1 = r.uniform(0.6, 1.4), u2 = r.uniform(3.4, 5.2), zf = r.uniform(-0.45, 0.45);
    if (half && v > 0.05) continue;
    const a = v * CR.K.ARC_DEG * D, dx = Math.cos(a), dy = Math.sin(a), ww = W * k * Math.pow(1 - Math.pow(Math.abs(v), 1.8), 0.85);
    const bx = (CR.K.CX * R + R * dx) * k - dx * ww * 0.8, by = R * dy * k - dy * ww * 0.8;
    const ln = (18 + 30 * Lb.flame(v, tl, ph + i) * u1) * k * (1 - 0.45 * Math.abs(v));
    const ux = -1, uy = 0.6 * v + 0.25 * Math.sin(tl * 0.7 + i * 1.7 + mi), n = Math.hypot(ux, uy);
    const B0 = P3(bx, by), B1 = P3(bx + ux / n * ln, by + uy / n * ln).addScaledVector(nz, zf * ln * Us);
    this.tube(nc, B0, B1, u2 * k * Us * 0.5, 0, col, 170 / 255 * fade, 0);
  }
  const mid = half ? pts[pts.length - 1] : pts[pts.length >> 1];
  this.sphere(nc, P3(mid[1][0], mid[1][1]), 20 * k * Us * gk * 0.7, col, 130 / 255 * fade, 0);
};
// launch flash (crescentfx burst): glow, a cross-cut diamond and a ring (flat < 1 = lying on the ground)
Runner.prototype.burst3 = function (A, x, y, vx, vy, t, flat) {
  const {inst, xf, WP, col, gk} = A, nc = noCore(inst._c), Us = xf.Us, HOTc = [255, 255, 255]; if (t < 0 || t >= 14) return;
  const q = t / 14, e = easeO(q), C = WP(x, y), d = this.dir3(xf, [vx, vy]);
  this.sphere(nc, C, (14 + 30 * e) * Us * gk, col, 160 / 255 * (1 - q), 0);
  this.diamond3(nc, C.clone().addScaledVector(d, -45 * Us), C.clone().addScaledVector(d, 45 * Us), 2 * Us * (1 - q) + 0.01, col, 220 / 255 * (1 - q), 0);
  this.diamond3(nc, C.clone().addScaledVector(d, -40 * Us), C.clone().addScaledVector(d, 40 * Us), 0.7 * Us * (1 - q) + 0.01, HOTc, 1 - q, 0);
  this.torus(nc, 'ring', C, flat != null && flat < 1 ? UPV : xf.az, (6 + 26 * e) * Us, 0.6, 0, col, 180 / 255 * (1 - q), 0);
};
// an X glint where blades cross / split (crescentfx cross)
Runner.prototype.xglint3 = function (A, x, y, f, a, life, size) {
  const {inst, xf, WP, col, gk} = A, nc = noCore(inst._c), Us = xf.Us, HOTc = [255, 255, 255], C = WP(x, y), q = a / life, e = easeO(a / 5), ln = size * (0.7 + 0.5 * e) * Us;
  [38, -38].forEach(dg => { const d = this.dir3(xf, FXK.rot([f[0], f[1]], dg));
    this.diamond3(inst._c, C.clone().addScaledVector(d, -ln), C.clone().addScaledVector(d, ln), 1.7 * Us * (1 - q) + 0.01, col, 230 / 255 * (1 - q), inst._c.toon_ink_m * 0.5); });
  this.sphere(nc, C, (10 + 16 * e) * Us * (1 - q) * gk, HOTc, 230 / 255 * (1 - q), 0);
  this.torus(nc, 'ring', C, xf.az, (6 + size * 0.8 * easeO(q)) * Us, 0.6, 0, col, 190 / 255 * (1 - q), 0);
};
// a blade shattering where it ended (crescentfx shards): spinning 3D diamond chips
Runner.prototype.shards3 = function (A, fr, R, k, mi, a, half, cnt) {
  const {inst, xf, WP, col, gk} = A, Lb = SLib(), CR = G.CRESCENTFX, c = inst._c, Us = xf.Us, HOTc = [255, 255, 255], q = a / CR.K.SHARD_LIFE; if (q >= 1 || a < 0) return;
  const ff = 1 - Math.min(1, a / 10), cp = fr.w((CR.K.CX + 1) * R * k * 0.5, half ? -0.4 * R * k : 0);
  this.sphere(noCore(c), WP(cp[0], cp[1]), 40 * k * Us * ff * gk * 0.7, HOTc, 200 / 255 * ff, 0);
  for (let i = 0; i < cnt; i++) {
    const r = Lb.rngFor(inst.seed, i, 91 + 40 * mi); let v = r.uniform(-0.9, 0.9); const j1 = r.uniform(-0.4, 0.4), j2 = r.uniform(-0.4, 0.4), sp = r.uniform(2, 6);
    const rot = r.uniform(0, Math.PI * 2) + r.uniform(-0.25, 0.25) * a, ln = r.uniform(7, 12) * (0.6 + 0.4 * k), vz = r.uniform(-0.7, 0.7) * sp;
    if (half) v = -Math.abs(v);
    const an = v * CR.K.ARC_DEG * D, p = fr.w((CR.K.CX * R + R * Math.cos(an)) * k, R * Math.sin(an) * k), dd = fr.d(Math.cos(an) + j1, Math.sin(an) + j2), fd = Lb.dragDist(0.93, a);
    const X = WP(p[0], p[1]).addScaledVector(this.dir3(xf, dd), sp * fd * Us * Math.hypot(dd[0], dd[1])).addScaledVector(xf.az, vz * fd * Us); X.y -= 0.05 * a * a * Us;
    const tn = this.paint(this.toon('shard', 0), c, Lb.mix(col, HOTc, 0.35), 1 - q, c.toon_ink_m * 0.6);
    [tn.m, tn.h].forEach(x => { x.position.copy(X); x.rotation.set(rot, rot * 0.7 + i, a * 0.2); x.scale.set(ln * Us, 2.4 * Us * (1 - q) + 0.01, 1.2 * Us); x.material.uniforms.uTaper.value = 0; });
  }
};
// embers shed off the blades' backs (crescentfx embers), as small glowing chips (capped)
Runner.prototype.embers3 = function (A, list, R, W) {
  const {inst, xf, WP, col, deep} = A, Lb = SLib(), CR = G.CRESCENTFX, P = inst.fx.params, nc = noCore(inst._c), Us = xf.Us, HOTc = [255, 255, 255], t = inst.age;
  const per = Math.max(0, Math.round(3 * (+P.density || 1) / Math.sqrt(Math.max(1, list.n)))); if (!per) return;
  let left = 40;
  for (let b = t - 1; b >= Math.max(0, t - CR.K.EMBER_LIFE) && left > 0; b--) {
    const mo = list.at(b);
    for (const m of mo) {
      const mi = m[0], fr = m[1], k = m[2], half = m[5]; if (m[6] >= 0) continue;
      for (let j = 0; j < per && left > 0; j++) {
        const r = Lb.rngFor(inst.seed, b * 16 + mi, 300 + j), life = 14 + 16 * r(), a = t - b; let v = r.uniform(-0.9, 0.9); const bv = r.uniform(0.5, 2.5), pv = r.uniform(-1.2, 1.2);
        if (a >= life) continue; if (half) v = -Math.abs(v);
        const an = v * CR.K.ARC_DEG * D, ww = W * Math.pow(1 - Math.pow(Math.abs(v), 1.8), 0.85);
        const s = fr.w((CR.K.CX * R + R * Math.cos(an) - Math.cos(an) * ww) * k, (R * Math.sin(an) - Math.sin(an) * ww) * k), vv = fr.d(-bv, pv), fd = Lb.dragDist(0.93, a);
        const X = WP(s[0] + vv[0] * fd, s[1] + vv[1] * fd).addScaledVector(xf.az, Math.sin(b * 1.7 + j * 2.3 + mi) * 1.6 * fd * Us); X.y -= 0.5 * 0.18 * a * a * Us;
        const q = a / life, ec = q < 0.5 ? Lb.mix(HOTc, col, Math.min(1, q * 2)) : Lb.mix(col, deep, (q - 0.5) * 2);
        this.sphere(nc, X, 1.6 * Us * (1 - q * 0.5), ec, 230 / 255 * (1 - q), 0); left--;
      }
    }
  }
};
/* crescent_wave (swordfx drawWave): one travelling moon */
Runner.prototype.wave3 = function (A) {
  const {inst, xf, WP, col, gk} = A, Lb = SLib(), Gm = G.SWORDFX.geo, P = inst.fx.params, t = inst.age, g = new Gm.WaveGeo(inst, 1), fr = Lb.frame(inst), Us = xf.Us, nc = noCore(inst._c);
  const L = g.L, k = g.grow(t), fade = t < L ? 1 : 1 - Lb.cl((t - L) / 8), f = inst.tq_f, o0 = inst.tq_o;
  const spd = Math.hypot(inst.x - o0[0], inst.y - o0[1]) / Math.max(1, Math.min(t, L)), posAt = b => { b = Math.min(b, L); return [o0[0] + f[0] * spd * b, o0[1] + f[1] * spd * b]; };
  const aim = this.dir3(xf, f);
  for (let b = 0; b <= Math.min(t, L); b += 8) { const a = t - b; if (a >= 14) continue;   // pressure rings left along its path
    const e = easeO(a / 14), cc = posAt(b); this.torus(nc, 'ring', WP(cc[0] - f[0] * 0.2 * g.R, cc[1] - f[1] * 0.2 * g.R), aim, (0.9 + 0.6 * e) * g.R * k * Us, 0.3, 0, col, 90 / 255 * (1 - a / 14), 0); }
  this.burst3(A, o0[0], o0[1], fr.vx, fr.vy, t);
  if (fade > 0) {
    for (let j = 1; j < 4; j++) { const ox = -spd * 2.2 * j, frj = {w: (x, y) => fr.w(x + ox, y)}, pts = G.CRESCENTFX.pts(g.R, g.W, k, 20, false);   // afterimages
      this.band(nc, pts.map(q => ({O: WP.apply(null, frj.w(q[1][0], q[1][1])), I: WP.apply(null, frj.w(q[1][0] - q[2][0] * q[3], q[1][1] - q[2][1] * q[3])), th: q[3] * A.kth * Us * 0.3})), xf.az, col, 55 / 255 / j * fade, 0); }
    this.moon3(A, fr, g.R, g.W, k, t, 0, fade, false);
  }
  this.embers3(A, {n: 1, at: b => { if (b >= L) return []; const p = posAt(b); return [[0, new Lb.Frame(p[0], p[1], f, inst.tq_m), g.grow(b), 1, b, false, -1]]; }}, g.R, g.W);
  if (t >= L) this.shards3(A, fr, g.R, k, 0, t - L, false, 10);
  this.hitMarks3(inst, xf, WP, col, f, null, gk);
};
/* the six crescent styles (crescentfx draw) */
Runner.prototype.crescent3 = function (A) {
  const {inst, xf, WP, col, gk, gy} = A, Lb = SLib(), CR = G.CRESCENTFX, P = inst.fx.params, st = P.style, t = inst.age, R = +P.radius, W = +P.thickness, Us = xf.Us;
  const c = inst._c, nc = noCore(c), HOTc = [255, 255, 255], f = inst.tq_f, m = inst.tq_m, o = inst.tq_o, nx = -f[1] * m, ny = f[0] * m, Lf = CR.activeTicks(P);
  // under the blades: launch flashes, crossing glints, the moonfall's mark
  if (st === 'crescent_drag') this.burst3(A, o[0], o[1] + CR.gp(inst, 1), 0, -1, t, 0.4);
  else if (st === 'crescent_helix' || st === 'crescent_split' || st === 'crescent_return') this.burst3(A, o[0], o[1], nx, ny, t);
  const spd = CR.spd(inst);
  if (st === 'crescent_helix' && spd > 0.01) {
    const d0 = CR.reach(inst, 1), wv = Math.max(0.25, +(P.weaves == null ? 2 : P.weaves));
    for (let j = 1; j < 40; j++) { const sj = j * d0 / wv, tj = sj / spd; if (tj >= Lf) break; const a = t - tj; if (a >= 0 && a < 10) this.xglint3(A, o[0] + f[0] * sj, o[1] + f[1] * sj, f, a, 10, 0.8 * R); }
  } else if (st === 'crescent_split' && spd > 0.01) {
    const ss = Lb.cl(+(P.split_pct == null ? 45 : P.split_pct) / 100) * CR.reach(inst, 1), a = t - ss / spd;
    if (a >= 0 && a < 14 && ss / spd < Lf) { this.xglint3(A, o[0] + f[0] * ss, o[1] + f[1] * ss, f, a, 14, 1.5 * R); this.xglint3(A, o[0] + f[0] * ss, o[1] + f[1] * ss, [nx, ny], a, 14, R); }
  } else if (st === 'crescent_scatter') {
    CR.scatterPlan(inst, P, CR.count(P)).forEach(pl => { const a2 = t - pl[0]; if (a2 < 0 || a2 >= 8) return;
      const q = a2 / 8, d = FXK.rot([f[0], f[1]], pl[1] * m), ln = 38 * pl[3], C = WP(o[0], o[1]);
      this.sphere(nc, C, (10 + 18 * easeO(q)) * Us * gk, col, 150 / 255 * (1 - q), 0);
      this.diamond3(nc, WP(o[0] + d[1] * ln, o[1] - d[0] * ln), WP(o[0] - d[1] * ln, o[1] + d[0] * ln), 1.5 * Us * (1 - q) + 0.01, col, 220 / 255 * (1 - q), 0);
      this.diamond3(nc, C, WP(o[0] + d[0] * ln * 1.6, o[1] + d[1] * ln * 1.6), 0.7 * Us * (1 - q) + 0.01, HOTc, 240 / 255 * (1 - q), 0); });
  } else if (st === 'crescent_fall') {
    const ti = CR.impactTick(P), g = CR.groundPoint(inst, 1);
    if (t < ti) { const u = t / ti, rx = R * (1.6 - 0.5 * u), G0 = WP(g[0], g[1]), th = +(P.fall_angle_deg == null ? 18 : P.fall_angle_deg) * D, hh = (+P.length || 0) + 2 * R;
      this.torus(nc, 'ring', G0, UPV, rx * Us, 0.5, 0, col, (60 + 160 * u) / 255, 0); this.torus(nc, 'ring', G0, UPV, rx * 0.55 * Us, 0.5, 0, HOTc, 140 / 255 * u * u, 0);
      this.tube(nc, WP(g[0] - Math.sin(th) * m * hh, g[1] - Math.cos(th) * hh), G0, 0.4 * Us * (1 + u), 0.6 * Us * (1 + u), col, (30 + 90 * u) / 255, 0);
      this.sphere(nc, G0, (8 + 14 * u) * Us * gk, col, 120 / 255 * u, 0); }
  }
  const mo = CR.moons(inst, 1, t);
  (st === 'crescent_fall' && t > CR.impactTick(P) + 1 ? [] : [3, 2, 1]).forEach(j => {   // afterimages
    CR.moons(inst, 1, t - 2 * j).forEach(q => { if (q[6] >= 0) return; const now = mo.find(z => z[0] === q[0]); if (!now || now[3] <= 0) return;
      const pts = CR.pts(R, W, q[2], 20, q[5]), fr = q[1];
      this.band(nc, pts.map(p => { const a = fr.w(p[1][0], p[1][1]), b = fr.w(p[1][0] - p[2][0] * p[3], p[1][1] - p[2][1] * p[3]); return {O: WP(a[0], a[1]), I: WP(b[0], b[1]), th: p[3] * A.kth * Us * 0.3}; }), xf.az, col, 55 / 255 / j * now[3], 0); });
  });
  mo.forEach(q => { if (q[3] > 0) this.moon3(A, q[1], R, W, q[2], q[4], q[0], q[3], q[5]); });
  const n = ['crescent_helix', 'crescent_scatter', 'crescent_split'].indexOf(st) >= 0 ? CR.count(P) : 1;
  this.embers3(A, {n, at: b => CR.moons(inst, 1, b)}, R, W);
  if (st === 'crescent_drag') this.drag3(A, mo, R, W);
  else if (st === 'crescent_fall') this.fall3(A, mo, R, W);
  const cnt = mo.length <= 1 ? 10 : 6;
  mo.forEach(q => { if (q[6] >= 0) this.shards3(A, q[1], R, q[2], q[0], q[6], q[5], cnt); });
  this.hitMarks3(inst, xf, WP, col, f, null, gk);
};
// the ground drag: wind streaks off the fin, the white-hot contact point, sparks / chips thrown back along the floor
Runner.prototype.drag3 = function (A, mo, R, W) {
  const {inst, xf, WP, col, gk, gy} = A, Lb = SLib(), CR = G.CRESCENTFX, P = inst.fx.params, t = inst.age, Us = xf.Us, c = inst._c, nc = noCore(c), HOTc = [255, 255, 255];
  const f = inst.tq_f, m = inst.tq_m, Lf = CR.activeTicks(P), dens = +P.density || 1, sx = (m >= 0 ? 1 : -1) * Math.max(Math.abs(f[0]), 0.3), gp = CR.gp(inst, 1);
  if (t < Lf && mo.length) {
    const fr = mo[0][1], k = mo[0][2];
    for (let j = 0; j < Math.round(6 * dens); j++) {
      const slot = Math.floor((t + j * 3) / 5), r = Lb.rngFor(inst.seed, slot, 600 + j), v = -r.uniform(0.05, 0.92), ln = r.uniform(1.4, 3.6) * R, rise = r.uniform(-0.18, 0.1);
      const u = ((t + j * 3) % 5) / 5, an = v * CR.K.ARC_DEG * D, ww = W * k * Math.pow(1 - Math.pow(Math.abs(v), 1.8), 0.85);
      const p0 = fr.w((CR.K.CX * R + R * Math.cos(an)) * k - Math.cos(an) * ww - u * 0.5 * R, R * Math.sin(an) * k), p1 = [p0[0] - sx * ln * (0.4 + 0.6 * u), p0[1] - f[1] * ln * (0.4 + 0.6 * u) + rise * ln];
      this.tube(nc, WP(p1[0], p1[1]), WP(p0[0], p0[1]), 0, (0.5 + 0.7 * (1 - Math.abs(v))) * Us, col, 150 / 255 * Math.sin(Math.PI * u), 0);
    }
    const g = CR.groundPoint(inst, 1), G0 = WP(g[0], g[1]), fl = 0.75 + 0.25 * Math.sin(t * 1.9 + (inst.seed % 97));
    this.sphere(nc, G0, 26 * k * Us * gk * 0.7, col, 170 / 255 * fl, 0); this.sphere(nc, G0, 11 * k * Us * gk, HOTc, fl, 0);
    this.torus(nc, 'ring', G0, UPV, 0.9 * R * k * Us, 0.5, t * 0.3, col, 150 / 255 * fl, 0);
  }
  const per = Math.max(0, Math.round(4 * dens)), grav = 0.34;
  for (let b = Math.max(0, t - 20); b < Math.min(t, Lf); b++) {
    const pp = inst.tq_path[Math.max(0, Math.min(inst.tq_path.length - 1, b))], px = pp[0], py = pp[1] + gp, P0 = WP(px, py);
    for (let j = 0; j < per; j++) {
      const r = Lb.rngFor(inst.seed, b, 500 + j), life = 8 + 12 * r(), a = t - b, bv = r.uniform(1.5, 7.5), up = r.uniform(0.6, 5.5), side = r.uniform(-1, 1), chip = r() < 0.3; if (a >= life) continue;
      const q = a / life, vz = side * 2.5;
      if (chip) { const fd = Lb.dragDist(0.9, a), X = P0.clone().addScaledVector(this.dir3(xf, [-sx, 0]), bv * fd * Us).addScaledVector(xf.az, vz * fd * Us);
        X.y += Math.max(0, up * fd - 0.5 * grav * a * a) * Us;
        const tn = this.paint(this.toon('shard', 0), c, Lb.mix(col, HOTc, 0.2), 1 - q, c.toon_ink_m * 0.5);
        [tn.m, tn.h].forEach(x => { x.position.copy(X); x.rotation.set(a * 0.4 + j, b, a * 0.3); x.scale.setScalar(2 * Us * (1 - q * 0.4)); x.material.uniforms.uTaper.value = 0; }); }
      else this.spark3(nc, xf, P0, -sx * bv + side * 0.4, -f[1] * bv - up, vz, 0.9, a, grav, 1.9, 0.75 * Us, Lb.mix(HOTc, col, q), 1 - q, gy);
    }
  }
};
// the moonfall: speed lines as it drops, then the slam on the floor
Runner.prototype.fall3 = function (A, mo, R, W) {
  const {inst, xf, WP, col, gk, gy} = A, Lb = SLib(), CR = G.CRESCENTFX, P = inst.fx.params, t = inst.age, Us = xf.Us, c = inst._c, nc = noCore(c), HOTc = [255, 255, 255];
  const m = inst.tq_m, ti = CR.impactTick(P), th = +(P.fall_angle_deg == null ? 18 : P.fall_angle_deg) * D, ax = Math.sin(th) * m, ay = Math.cos(th), g = CR.groundPoint(inst, 1), G0 = WP(g[0], g[1]);
  if (t >= CR.K.FALL_WIND && t < ti && mo.length) {
    const fr = mo[0][1], k = mo[0][2];
    for (let j = 0; j < 7; j++) { const r = Lb.rngFor(inst.seed, Math.floor(t / 2), 700 + j), yy = r.uniform(-0.95, 0.95) * R * k, ln = r.uniform(1.2, 3.2) * R, p0 = fr.w(CR.K.CX * R * k - 0.2 * R, yy);
      this.tube(nc, WP(p0[0] - ax * ln, p0[1] - ay * ln).addScaledVector(xf.az, r.uniform(-0.6, 0.6) * R * Us), WP(p0[0], p0[1]), 0, 0.7 * Us, col, 150 / 255, 0); }
  }
  const a = t - ti; if (a < 0 || a >= 24) return;
  const q = a / 24, e = easeO(a / 9), ff = 1 - Math.min(1, a / 10);
  this.sphere(nc, G0, (30 + 50 * e) * Us * gk, HOTc, 240 / 255 * ff, 0);
  this.sphere(nc, G0, 2.2 * R * (0.5 + 0.5 * e) * Us * gk, col, 150 / 255 * (1 - q), 0);
  const hh = ((+P.length || 0) * 0.6 + 2.5 * R) * (1 - 0.3 * q);   // the light pillar along its fall
  this.diamond3(nc, G0, WP(g[0] - ax * hh, g[1] - ay * hh), ((0.5 * W + 6) * ff + 0.3) * Us * 0.5, col, 200 / 255 * ff, 0);
  this.diamond3(nc, G0, WP(g[0] - ax * hh * 0.92, g[1] - ay * hh * 0.92), ((0.16 * W + 2) * ff + 0.2) * Us * 0.5, HOTc, ff, 0);
  for (let j = 0; j < 3; j++) { const aa = a - j * 3; if (aa < 0) continue; const qq = aa / 20; if (qq >= 1) continue;
    this.torus(j ? nc : c, 'ring', G0, UPV, (0.5 + 2.3 * easeO(qq)) * R * (1 + 0.25 * j) * Us, 0.5, 0, j ? col : HOTc, 220 / 255 * (1 - qq), j ? 0 : c.toon_ink_m * 0.5); }
  for (let i = 0; i < Math.max(0, Math.round(18 * (+P.density || 1))); i++) {   // shards thrown up all round
    const r = Lb.rngFor(inst.seed, i, 720), life = 12 + 12 * r(), an = -Math.PI * r.uniform(0.08, 0.92), sp = r.uniform(3, 10), ln = r.uniform(5, 11); if (a >= life) continue;
    const az = r() * Math.PI * 2, hz = new THREE.Vector3(Math.cos(az), 0, Math.sin(az)), fd = Lb.dragDist(0.92, a), q2 = a / life;
    const X = G0.clone().addScaledVector(hz, Math.cos(an) * sp * fd * Us * Math.sign(Math.cos(an) || 1)).addScaledVector(UPV, Math.max(0, -Math.sin(an) * sp * fd - 0.15 * a * a) * Us);
    const tn = this.paint(this.toon('shard', 0), c, Lb.mix(col, HOTc, 0.3), 1 - q2, c.toon_ink_m * 0.5);
    [tn.m, tn.h].forEach(x => { x.position.copy(X); x.rotation.set(a * 0.3 + i, az, a * 0.2); x.scale.set(ln * Us, 1.1 * Us * (1 - q2) + 0.01, 1.1 * Us); x.material.uniforms.uTaper.value = 0; });
  }
};
/* forward_thrust (swordfx drawThrust): a tapered spear of light */
Runner.prototype.thrust3 = function (A) {
  const {inst, xf, WP, col, bright, gk, gy} = A, Lb = SLib(), Gm = G.SWORDFX.geo, P = inst.fx.params, t = inst.age, fr = Lb.frame(inst), c = inst._c, nc = noCore(c), Us = xf.Us, HOTc = [255, 255, 255], ink = c.toon_ink_m;
  const Lmax = +P.length, Wd = +P.thickness, T = Gm.thrTimes(P), l = Gm.thrLen(P, t, Lmax), O = WP(inst.x, inst.y), aim = this.dir3(xf, inst.tq_f), dens = +P.density || 1;
  if (t < T[0] + 1) { const cp = Lb.cl(t / T[0]), fa = t < T[0] ? 1 : 0.5; this.tube(nc, O.clone().addScaledVector(aim, -14 * cp * Us), O, 0, 1 * Us, Lb.mix(col, HOTc, cp), 200 / 255 * fa, 0);
    this.sphere(nc, O, (5 + 8 * cp) * Us * gk, HOTc, 220 / 255 * fa, 0); }
  if (t >= T[0] && t < T[1] + 6) { const fa = t < T[1] ? 1 : 1 - (t - T[1]) / 6, reach = t < T[1] ? l : Lmax;   // speed lines all round it
    for (let i = 0; i < Math.max(0, Math.round(7 * dens)); i++) { const r = Lb.rngFor(inst.seed, i, 21), side = r.uniform(-2.4, 2.4) * Wd, su0 = r.uniform(0, 0.45), su1 = Math.min(1, su0 + r.uniform(0.3, 0.55)), az = r() * Math.PI * 2;
      const off = coneDir(aim, 90, az, new THREE.Vector3()).multiplyScalar(Math.abs(side) * Us);
      this.tube(nc, O.clone().addScaledVector(aim, su0 * reach * Us).add(off), O.clone().addScaledVector(aim, su1 * reach * Us).add(off), 0, 0.55 * Us, Lb.mix(col, HOTc, 0.4), 150 / 255 * fa, 0); } }
  if (l > 1) {
    const segs = 4, at = u => O.clone().addScaledVector(aim, u * l * Us);
    for (let j = 0; j < segs; j++) { const u0 = j / segs, u1 = (j + 1) / segs, h0 = Gm.thrHw(u0, Wd) * Us, h1 = Gm.thrHw(u1, Wd) * Us;
      this.tube(nc, at(u0), at(u1), h0 * 1.6, h1 * 1.6, col, 110 / 255, 0);
      this.tube(c, at(u0), at(u1), h0, h1, Lb.mix(col, bright, u1), 225 / 255, ink);
      this.tube(nc, at(u0), at(u1), h0 * 0.35, h1 * 0.35, HOTc, 1, 0); }
    const tip = at(1); this.sphere(nc, tip, 8 * Us * gk, col, 110 / 255, 0); this.sphere(nc, tip, 7 * Us * gk, HOTc, 230 / 255, 0);
    const v = coneDir(aim, 90, 0, new THREE.Vector3());
    this.diamond3(nc, tip.clone().addScaledVector(aim, -14 * Us), tip.clone().addScaledVector(aim, 14 * Us), 0.6 * Us, HOTc, 230 / 255, 0);
    this.diamond3(nc, tip.clone().addScaledVector(v, -5 * Us), tip.clone().addScaledVector(v, 5 * Us), 0.6 * Us, HOTc, 230 / 255, 0);
    this.sphere(nc, O, 7 * Us * gk, col, 150 / 255, 0);
  }
  const a = t - T[1];
  if (a >= 0 && a < 12) {   // pressure rings round the point + sparks thrown forward
    const q = a / 12, e = easeO(q), tip = O.clone().addScaledVector(aim, Lmax * Us);
    this.torus(nc, 'ring', tip, aim, (5 + 22 * e) * Us, 0.4, 0, col, 220 / 255 * (1 - q), 0);
    this.torus(nc, 'ring', O.clone().addScaledVector(aim, Lmax * (0.72 - 0.1 * e) * Us), aim, (4 + 14 * e) * Us, 0.4, 0, HOTc, 160 / 255 * (1 - q), 0);
    this.sphere(nc, tip, 22 * Us * (1 - q) * gk, HOTc, 210 / 255 * (1 - q), 0);
    for (let i = 0; i < Math.max(0, Math.round(10 * dens)); i++) { const r = Lb.rngFor(inst.seed, i, 23), life = 9 + 7 * r(); if (a >= life) continue;
      const dg = r.uniform(-35, 35), sp = r.uniform(3, 8), qq = a / life, d3 = coneDir(aim, Math.abs(dg), r() * Math.PI * 2, new THREE.Vector3()), fd = Lb.dragDist(0.86, a), dk = Math.pow(0.86, a);
      const B = tip.clone().addScaledVector(d3, sp * fd * Us); this.tube(nc, B.clone().addScaledVector(d3, -sp * dk * 1.5 * Us), B, 0, 0.6 * Us, Lb.mix(HOTc, col, qq), 1 - qq, 0); }
  }
  if (t >= T[2] && t < T[3] + Gm.THR_FADE) { const q = (t - T[2]) / (Gm.THR_RETRACT + Gm.THR_FADE), bt = O.clone().addScaledVector(aim, Lmax * Us);   // the pierced line, hanging
    this.tube(nc, O, bt, (1.3 * (1 - q) + 0.15) * Us, (1.3 * (1 - q) + 0.15) * Us, col, 150 / 255 * (1 - q), 0);
    this.tube(nc, O, bt, 0.5 * Us, 0.5 * Us, HOTc, 220 / 255 * (1 - q) * (1 - q), 0); }
  this.hitMarks3(inst, xf, WP, col, inst.tq_f, null, gk);
};
/* the `arc` kind (FXK arcSegs): a crescent band round its centre, its tail fading, a white core */
Runner.prototype.arc3 = function (A) {
  const {inst, xf, WP, col, kth} = A, P = inst.fx.params, c = inst._c, nc = noCore(c), Us = xf.Us, segs = FXK.arcSegs(inst, 1), R = +P.radius;
  if (!segs.length) return;
  const rows = [], core = [];
  segs.slice().sort((p, q) => p[5] - q[5]).forEach((q, i, arr) => {
    const ends = i === arr.length - 1 ? [q[0], q[0] + q[1]] : [q[0]];
    ends.forEach(a0 => { const a = a0 * D, dx = Math.cos(a), dy = -Math.sin(a), w = q[2], cw = P.width * P.core_width * (0.25 + 0.75 * q[3]);
      rows.push({O: WP(inst.x + dx * (R + w / 2), inst.y + dy * (R + w / 2)), I: WP(inst.x + dx * (R - w / 2), inst.y + dy * (R - w / 2)), th: w * kth * Us * 0.5, a: q[4] / 255});
      core.push({O: WP(inst.x + dx * (R + cw / 2), inst.y + dy * (R + cw / 2)), I: WP(inst.x + dx * (R - cw / 2), inst.y + dy * (R - cw / 2)), th: w * kth * Us * 0.56, a: q[4] / 255 * P.core_alpha}); });
  });
  this.band(c, rows, xf.az, col, 1, c.toon_ink_m);
  this.band(nc, core, xf.az, [255, 255, 255], 1, 0);
};
/* ---- 3D gunfire + ki barrage (Daniel 2026-11-26, batch 3 of "more 3D FX") ----
   The ten GUNFX styles (machine gun, shotgun, magnum, charged blast, dual pistols, sniper rail, gatling, rocket barrage,
   drill bullet, thunder bullet) and STRIKEFX's ki barrage. Rounds fly exactly where FX Studio puts them (GUNFX.geo.rounds,
   STRIKEFX.ki.shots), so hits are unchanged; each is rebuilt in 3D: tracers / pellets / slugs = tapered streaks with a
   hot head (slugs wrapped in rifling rings), the orb = a sphere with ghosts and spinning rings, the rocket = a steel
   missile with fins, an exhaust flame and a smoke trail, the drill = a cone with spiral wind, the thunder bullet = a
   jagged 3D lightning trail. Muzzles: flash, star, prongs fanned in 3D, the shotgun's flash cone, pressure rings, the gun
   kata's swing. Around them: brass / shells tumbling out and bouncing on the floor, smoke, the gatling's spinning barrels,
   the charged blast's gathering orb, the sniper's laser + reticle (facing the camera) and its rail with a true 3D helix.
   Impacts: sparks thrown back in a cone, the heavy hit (3D spike star, shock rings across the line), fireballs, lightning
   dropping from the sky, drill shards. Ki: comet shots, hand glows, flashes, detonations with smoke piling up. */
function gunKind(fx) {
  if (!fx || fx.prim !== 'technique') return '';
  const s = fx.params && fx.params.style;
  if (G.GUNFX && G.GUNFX.STYLES.indexOf(s) >= 0) return 'gun';
  return s === 'ki_barrage' ? 'ki' : '';
}
// jagged lightning in 3D from A to B (offsets in both directions across the line)
function jag3(inst, key, A, B, n, amp) {
  const r = SLib().rngFor(inst.seed, key, 700), d = B.clone().sub(A), u = d.clone().normalize();
  const p1 = Math.abs(u.y) < 0.9 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0); p1.cross(u).normalize(); const p2 = u.clone().cross(p1);
  const pts = [A.clone()];
  for (let m = 1; m < n; m++) pts.push(A.clone().addScaledVector(d, m / n).addScaledVector(p1, r.uniform(-1, 1) * amp).addScaledVector(p2, r.uniform(-1, 1) * amp));
  pts.push(B.clone()); return pts;
}
// a polyline of tubes (lightning, arcs)
Runner.prototype.poly3 = function (c, pts, r, rgb, a) { for (let i = 1; i < pts.length; i++) this.tube(c, pts[i - 1], pts[i], r, r, rgb, a, 0); };
// smoke / dust puffs (gunfx puffs): grey balls drifting out and rising, fading in then out
Runner.prototype.puffs3 = function (inst, key, C, a, life, n, size, rgb, rise, Us) {
  if (a < 0 || a >= life || n <= 0) return;
  const Lb = SLib(), nc = noCore(inst._c), q = a / life;
  for (let j = 0; j < n; j++) {
    const r = Lb.rngFor(inst.seed, key, 300 + j), an = r.uniform(0, Math.PI * 2), dr = r.uniform(0.2, 1.0) * size * easeO(a / 14);
    const el = r.uniform(-0.6, 0.6), X = C.clone().add(new THREE.Vector3(Math.cos(an) * Math.cos(el), Math.sin(el), Math.sin(an) * Math.cos(el)).multiplyScalar(dr * Us));
    X.y += r.uniform(0.3, 1.0) * rise * a * Us;
    this.sphere(nc, X, size * r.uniform(0.5, 0.9) * (0.5 + 0.8 * easeO(a / 18)) * Us * 0.6, rgb, 0.55 * Math.pow(1 - q, 1.5) * Math.min(1, a / 3), 0);
  }
};
// sparks (gunfx sparks) in a 3D cone round dir
Runner.prototype.sparks3 = function (inst, key, C, dir, cone, a, n, col, spLo, spHi, life0, Us, gy) {
  const Lb = SLib(), nc = noCore(inst._c), HOTc = [255, 255, 255], d3 = new THREE.Vector3();
  for (let j = 0; j < n; j++) {
    const r = Lb.rngFor(inst.seed, key, 500 + j), life = life0 * (0.6 + 0.6 * r()); if (a >= life) continue;
    const dg = Math.abs(r.uniform(-cone, cone)), sp = r.uniform(spLo, spHi), fd = Lb.dragDist(0.86, a), dk = Math.pow(0.86, a), qq = a / life;
    coneDir(dir, dg, r() * Math.PI * 2, d3);
    const B = C.clone().addScaledVector(d3, sp * fd * Us); B.y -= 0.1 * a * a * Us;
    const A = B.clone().addScaledVector(d3, -sp * dk * 1.6 * Us);
    if (gy != null && B.y < gy + 0.03) { B.y = gy + 0.03; A.y = Math.max(A.y, gy + 0.03); }
    this.tube(nc, A, B, 0, 0.65 * Us, Lb.mix(HOTc, col, qq), 1 - qq, 0);
  }
};
// a 3D spike star (gunfx spikes): n spikes round dir's plane + a few out of it
Runner.prototype.star3 = function (inst, key, C, dir, n, rOut, rIn, rgb, a, rot) {
  const Lb = SLib(), nc = noCore(inst._c), d3 = new THREE.Vector3(), r = Lb.rngFor(inst.seed, key, 760);
  for (let j = 0; j < n + 3; j++) {
    if (j < n) coneDir(dir, 90, (rot || 0) + j * Math.PI * 2 / n, d3); else coneDir(dir, r.uniform(10, 60) * (j % 2 ? 1 : -1) + (j % 2 ? 0 : 180), r() * 6.28, d3);
    this.tube(nc, C.clone().addScaledVector(d3, rIn * 0.4), C.clone().addScaledVector(d3, rOut), rIn * 0.45, 0, rgb, a, 0);
  }
};
Runner.prototype.drawGun = function (l, inst, xf) {
  const Lb = SLib(), GF = G.GUNFX, Gm = GF.geo, P = inst.fx.params, st = P.style, g = GF.GUNS[st], t = inst.age, c = inst._c, nc = noCore(c), Us = xf.Us, ink = c.toon_ink_m;
  const cs = Lb.colours(inst, this.host), col = cs[0], deep = cs[2] || cs[0], HOTc = [255, 255, 255], gk = c.strike_glow_pct / 100, gy = c.strike_ground ? l.groundY : null;
  const dens = +P.density || 1, all = Gm.rounds(inst, 1), smoke = Lb.mix(Gm.SMOKE, deep, 0.25), lb = GF.launches(P);
  const WP = (x, y, o) => this.w3(inst, xf, x, y, 0, o || new THREE.Vector3()), D3 = u => this.dir3(xf, u);
  const nDust = Math.max(0, Math.round(g.dust * dens)), nSmoke = Math.max(0, Math.round(g.smoke * dens));
  const hside = new THREE.Vector3().crossVectors(UPV, D3([inst.tq_f[0], 0])).normalize();
  // 1: smoke, casings, rockets
  for (const s of all) {
    const k = t - s.b;
    if (s.j === 0) {
      const h = s.head(0), O = WP(s.ox, s.oy);
      if (nSmoke) this.puffs3(inst, s.i * 4 + 2, O.clone().addScaledVector(D3(h), 8 * Us), k, Gm.SMOKE_LIFE, nSmoke, g.flash_px * 0.7, smoke, 0.45, Us);
      if (g.shells && dens > 0) this.casing3(inst, s.i * 4 + 3, O, D3(h), hside, k, g.shells, Us, gy);
    }
    if (s.look === 'rail') { inst.tq_imp.forEach((im, n) => this.puffs3(inst, 9100 + n, WP(im[1], im[2]), t - im[0] - Gm.RAIL_DELAY, Gm.SMOKE_LIFE, nDust, +P.thickness * 0.6, smoke, 0.35, Us)); continue; }
    const en = s.end(inst);
    if (s.look === 'rocket') {
      for (let kp = 0; kp < Math.min(k, en[0] - s.b); kp += Gm.ROCKET_PUFF) { const pp = s.pos(kp); this.puffs3(inst, 20000 + s.i * 64 + Math.floor(kp / Gm.ROCKET_PUFF), WP(pp[0], pp[1]), k - kp, 30, 1, +P.radius * 1.6, smoke, 0.15, Us); }
      if (t < en[0]) this.rocket3(inst, xf, s, k, t, col, Us);
    }
    const bl = Gm.blastAt(inst, s); if (bl && nDust) this.puffs3(inst, s.i * 4 + 1, WP(bl[1], bl[2]), t - bl[0], Gm.SMOKE_LIFE, nDust, +P.thickness * 0.6 * s.size, smoke, 0.35, Us);
  }
  if (st === 'gatling' && t > lb[lb.length - 1]) { const mp = Gm.at(inst.tq_path, t);
    for (let m = 0; m < 4; m++) this.puffs3(inst, 9200 + m, WP(mp[0], mp[1] - 4), t - lb[lb.length - 1] - m * 3, Gm.SMOKE_LIFE, Math.max(0, Math.round(2 * dens)), 6, smoke, 0.6, Us); }
  // 2: the gun before / while it fires
  if (st === 'gatling') this.gatling3(inst, xf, P, col, t, lb.filter(b => b <= t).length, lb.length, Us, gk);
  else if (st === 'charged_blast') this.charge3(inst, xf, P, col, Lb.mix(col, HOTc, 0.4), t, lb[0], dens, Us, gk);
  else if (st === 'sniper_rail') this.aim3(inst, xf, P, col, t, lb[0], Us, gk);
  // 3: muzzles, rounds, impacts
  for (const s of all) {
    const k = t - s.b;
    if (s.j === 0) this.muzzle3(inst, xf, g, s, k, col, P, Us, gk);
    if (s.look === 'rail') { this.rail3(inst, xf, s, P, col, t, dens, Us, gk, gy); continue; }
    const en = s.end(inst);
    if (t < en[0]) { this.round3(inst, xf, s, k, t, col, Lb.mix(col, HOTc, 0.25 + s.tint), P, en[1], Us, gk); continue; }
    const bl = Gm.blastAt(inst, s); if (bl) this.gunImpact3(inst, xf, s, t - bl[0], WP(bl[1], bl[2]), bl[3], col, P, dens, Us, gk, gy);
  }
  if (g.look === 'drill') inst.tq_imp.forEach((im, n) => this.heavy3(inst, 9300 + n, WP(im[1], im[2]), D3(inst.tq_f), t - im[0], Gm.IMPACT_LIFE.drill, +P.thickness * Us, dens, col, Us, gk, gy));
};
// a brass casing / shotgun shell kicked out sideways, tumbling, bouncing on the floor
Runner.prototype.casing3 = function (inst, key, O, aim, side, a, kind, Us, gy) {
  const Gm = G.GUNFX.geo, Lb = SLib(), c = inst._c; if (a < 0 || a >= Gm.CASING_LIFE) return;
  const r = Lb.rngFor(inst.seed, key, 200), vb = r.uniform(1.0, 2.2), vu = r.uniform(2.4, 3.8), vs = r.uniform(1.2, 2.6) * (r() < 0.5 ? -1 : 1);
  const X = O.clone().addScaledVector(aim, -vb * a * 0.5 * Us).addScaledVector(side, vs * a * Us); X.y += (vu * a - 0.5 * Gm.CASING_G * a * a) * Us;
  if (gy != null && X.y < gy + 0.02) X.y = gy + 0.02;
  const fade = a < Gm.CASING_LIFE - 8 ? 1 : (Gm.CASING_LIFE - a) / 8, hl = (kind === 2 ? 5.5 : 3.6) / 2 * Us, hw = (kind === 2 ? 2.4 : 1.5) / 2 * Us;
  const rt = r.uniform(0, 6.28) + a * r.uniform(0.35, 0.6), u = new THREE.Vector3(Math.cos(rt), Math.sin(rt * 0.7) * 0.6, Math.sin(rt)).normalize();
  if (kind === 2) { this.tube(c, X.clone().addScaledVector(u, -hl), X.clone().addScaledVector(u, hl * 0.35), hw, hw, Gm.HULL, fade, c.toon_ink_m * 0.4);
    this.tube(c, X.clone().addScaledVector(u, hl * 0.35), X.clone().addScaledVector(u, hl), hw, hw, Gm.BRASS, fade, c.toon_ink_m * 0.4); }
  else this.tube(c, X.clone().addScaledVector(u, -hl), X.clone().addScaledVector(u, hl), hw, hw, Gm.BRASS, fade, c.toon_ink_m * 0.4);
};
Runner.prototype.muzzle3 = function (inst, xf, g, s, k, col, P, Us, gk) {
  if (k >= g.flash || k < 0) return;
  const Lb = SLib(), c = inst._c, nc = noCore(c), HOTc = [255, 255, 255], q = k / g.flash, X = this.w3(inst, xf, s.ox, s.oy, 0, new THREE.Vector3()), u = this.dir3(xf, s.head(0));
  const fs = g.flash_px * s.size * (1 - 0.35 * q) * Us, e = easeO(q), d3 = new THREE.Vector3();
  this.sphere(nc, X, fs * 1.3 * gk, col, 210 / 255 * (1 - q), 0); this.sphere(nc, X, fs * 0.5 * gk * 1.4, HOTc, 1 - q, 0);
  const v = coneDir(u, 90, k * 0.7, new THREE.Vector3());
  this.diamond3(nc, X.clone().addScaledVector(u, -fs * 1.4), X.clone().addScaledVector(u, fs * 1.4), 0.8 * Us, HOTc, 235 / 255 * (1 - q), 0);
  this.diamond3(nc, X.clone().addScaledVector(v, -fs * 0.6), X.clone().addScaledVector(v, fs * 0.6), 0.8 * Us, HOTc, 235 / 255 * (1 - q), 0);
  [-28, 0, 28, 28, 28].forEach((dg, jj) => {   // prongs fanned round the barrel
    const r = Lb.rngFor(inst.seed, s.i, 120 + jj), ln = fs * (dg === 0 ? 1.2 : 0.75) * r.uniform(0.8, 1.2) * (1 - 0.5 * q);
    coneDir(u, Math.abs(dg), jj * 2.1 + (dg < 0 ? Math.PI : 0), d3);
    this.tube(nc, X, X.clone().addScaledVector(d3, ln), fs * 0.11, 0, Lb.mix(col, HOTc, 0.5), 230 / 255 * (1 - q), 0);
  });
  if (s.look === 'pellet') {   // the shotgun's flash cone + pressure ring
    const half = ((+P.span || 0) * 0.6 + 6) * D, lnc = fs * 2.4 * (0.6 + 0.4 * e);
    this.tube(nc, X, X.clone().addScaledVector(u, lnc), fs * 0.15, Math.tan(half) * lnc, col, 120 / 255 * (1 - q), 0);
    this.torus(nc, 'ring', X.clone().addScaledVector(u, fs * 1.4 * e), u, fs * (0.6 + 1.3 * e), 0.5, 0, HOTc, 200 / 255 * (1 - q), 0);
  } else if (['slug', 'orb', 'rail', 'drill'].indexOf(s.look) >= 0) {
    if (s.look === 'slug') [1, -1].forEach(sd => { const w = coneDir(u, 90, sd > 0 ? 0 : Math.PI, new THREE.Vector3()), J = X.clone().addScaledVector(u, fs * 0.25);
      this.tube(nc, J, J.clone().addScaledVector(w, fs * 0.8), fs * 0.08, 0, HOTc, 220 / 255 * (1 - q), 0); });
    [[0, 1.0], [2, 1.5]].forEach(dk => { const aa = k - dk[0], kk = dk[1]; if (aa < 0) return; const qq = g.flash > dk[0] ? aa / (g.flash - dk[0]) : 1, ee = easeO(qq);
      this.torus(nc, 'ring', X.clone().addScaledVector(u, fs * 0.6 * ee * kk), u, fs * (0.5 + 1.1 * ee) * kk, 0.4, 0, HOTc, 200 / 255 * (1 - qq), 0); });
  } else if (s.look === 'rocket') this.tube(nc, X.clone().addScaledVector(u, -fs * 1.6), X, 0, fs * 0.35, Lb.mix(col, HOTc, 0.3), 200 / 255 * (1 - q), 0);
  if (P.style === 'dual_pistols') {   // gun-kata: the swing arc of the hand that fired
    const sd2 = s.v % 2 === 0 ? 1 : -1, pts = [];
    for (let m = 0; m < 9; m++) pts.push(X.clone().addScaledVector(coneDir(u, (-0.9 + 1.4 * m / 8) * sd2 / D, sd2 > 0 ? Math.PI / 2 : -Math.PI / 2, d3), 14 * Us));
    this.line3(nc, pts, (1 * (1 - q) + 0.15) * Us, xf.az, Lb.mix(col, HOTc, 0.4), 200 / 255 * (1 - q), 0, uu => Math.sin(Math.PI * uu));
  }
};
Runner.prototype.round3 = function (inst, xf, s, k, t, col, tint, P, stopped, Us, gk) {
  const Lb = SLib(), Gm = G.GUNFX.geo, c = inst._c, nc = noCore(c), ink = c.toon_ink_m, HOTc = [255, 255, 255], r = +P.radius * s.size * Us;
  const WPp = p => this.w3(inst, xf, p[0], p[1], 0, new THREE.Vector3()), X = WPp(s.pos(k)), u = this.dir3(xf, s.head(k)), look = s.look;
  const fa = ['tracer', 'pellet', 'slug'].indexOf(look) >= 0 ? (stopped ? 1 : Math.max(0, Math.min(1, (s.flight - k) / Math.max(1, s.flight * Gm.FADE_TAIL)))) : 1;
  if (look === 'tracer' || look === 'pellet') {
    const T = WPp(s.pos(Math.max(0, k - (look === 'tracer' ? Gm.TRACER_TAIL : 1.6))));
    this.tube(nc, T, X, 0, r * (look === 'tracer' ? 0.75 : 0.6), tint, 230 / 255 * fa, 0);
    this.sphere(c, X, r * 1.2 * gk * 1.4, col, fa, ink * 0.4);
  } else if (look === 'slug') {
    for (let j = 0; j < 4; j++) { const kj = k - (j + 1) * 0.8; if (kj < 0) break;
      this.torus(nc, 'ring', WPp(s.pos(kj)), u, r * (1.6 + 0.5 * j), 0.5, 0, Lb.mix(col, HOTc, 0.3), 170 / 255 * (1 - j / 4) * fa, 0); }
    const T = WPp(s.pos(Math.max(0, k - 2.6)));
    this.tube(nc, T, X, 0, r * 0.9, col, 150 / 255 * fa, 0); this.tube(nc, T, X, 0, r * 0.35, HOTc, 230 / 255 * fa, 0);
    _sq.setFromUnitVectors(XV, u); this.sphere(c, X, r * 1.5 * gk * 1.3, col, fa, ink, {q: _sq.clone(), x: 1.6, y: 1, z: 1});
  } else if (look === 'orb') {
    const fl = 0.88 + 0.12 * Math.sin(t * 1.7);
    [[4, 40], [2, 70]].forEach(ja => this.sphere(nc, WPp(s.pos(Math.max(0, k - ja[0]))), r * 1.8 * gk, col, ja[1] / 255, 0));
    const T = WPp(s.pos(Math.max(0, k - 5))); this.tube(nc, T, X, 0, r * 0.7, col, 120 / 255, 0);
    this.sphere(c, X, r * 1.6 * fl * gk * 1.3, tint, 1, ink);
    for (let j = 0; j < 2; j++) this.torus(nc, 'ring', X, coneDir(u, 55, t * 0.35 + j * Math.PI, new THREE.Vector3()), r * 1.4, 0.6, t * 0.2, HOTc, 170 / 255, 0);
  } else if (look === 'drill') {
    const R = r, base = X.clone().addScaledVector(u, -R * 0.6), tip = X.clone().addScaledVector(u, R * 2.4);
    this.sphere(nc, X, R * 2.8 * gk * 0.7, col, 0.35, 0);
    this.tube(c, base, tip, R * 1.05, 0, col, 1, ink); this.tube(nc, base, tip, R * 0.6, 0, Lb.mix(col, HOTc, 0.6), 0.9, 0);
    for (let j = 0; j < 4; j++) {   // spiral grooves turning round the cone
      const pts = []; for (let m = 0; m <= 6; m++) { const pp = m / 6, an = j * Math.PI / 2 + t * Gm.DRILL_SPIN * 6.28 + pp * 3;
        pts.push(base.clone().lerp(tip, pp).addScaledVector(coneDir(u, 90, an, new THREE.Vector3()), R * 1.1 * (1 - pp))); }
      this.poly3(nc, pts, 0.35 * Us, HOTc, 0.8); }
    [1, -1].forEach(sd => { const pts = []; for (let m = 0; m < 15; m++) { const db = m * R * 0.9;   // wind helix behind it
      pts.push(base.clone().addScaledVector(u, -db).addScaledVector(coneDir(u, 90, sd * (t * 0.9 + m * 0.7), new THREE.Vector3()), R * (1.3 - m * 0.06))); }
      this.line3(nc, pts, 0.7 * Us, xf.az, col, 150 / 255, 0, uu => 1 - uu); });
  } else if (look === 'bolt') {
    const d = s.sp * k, d0 = Math.max(0, d - 160), n = Math.max(1, Math.min(24, Math.trunc((d - d0) / Gm.BOLT_SEG) + 1)), rr = Lb.rngFor(inst.seed, s.i, 400 + Math.floor(t / 2)), pts = [];
    for (let m = 0; m < n + 1; m++) { const dm = d0 + (d - d0) * m / n, o = m === n ? 0 : rr.uniform(-7, 7), oz = m === n ? 0 : rr.uniform(-7, 7), w = s.fr.d(Math.cos(s.ang) * dm, Math.sin(s.ang) * dm), h = s.head(k);
      pts.push(this.w3(inst, xf, s.ox + w[0] - h[1] * o, s.oy + w[1] + h[0] * o, oz, new THREE.Vector3())); }
    const flb = 0.7 + 0.3 * Math.sin(t * 2.7 + s.i);
    this.poly3(nc, pts, 1.3 * Us, col, 150 / 255 * flb); this.poly3(nc, pts, 0.5 * Us, HOTc, 200 / 255 * flb);
    this.sphere(c, X, r * 1.4 * gk * 1.4, Lb.mix(col, HOTc, 0.4), 1, ink * 0.5);
    for (let j = 0; j < 3; j++) { const ra = Lb.rngFor(inst.seed, s.i, 420 + Math.floor(t / 2) * 3 + j), apts = [X.clone()], d3 = new THREE.Vector3(ra.uniform(-1, 1), ra.uniform(-1, 1), ra.uniform(-1, 1)).normalize();
      for (let m = 0; m < 3; m++) { d3.add(new THREE.Vector3(ra.uniform(-0.8, 0.8), ra.uniform(-0.8, 0.8), ra.uniform(-0.8, 0.8))).normalize(); apts.push(apts[m].clone().addScaledVector(d3, r * 1.6)); }
      this.poly3(nc, apts, 0.6 * Us, Lb.mix(col, HOTc, 0.5), 200 / 255); }
  }
};
Runner.prototype.rocket3 = function (inst, xf, s, k, t, col, Us) {
  const Lb = SLib(), Gm = G.GUNFX.geo, c = inst._c, nc = noCore(c), HOTc = [255, 255, 255], r = +inst.fx.params.radius * s.size * Us;
  const p = s.pos(k), X = this.w3(inst, xf, p[0], p[1], 0, new THREE.Vector3()), u = this.dir3(xf, s.head(k)), body = Lb.mix(Gm.STEEL, col, 0.15);
  _sq.setFromUnitVectors(XV, u); const q = _sq.clone();
  this.sphere(c, X, r * 0.65, body, 1, c.toon_ink_m * 0.6, {q, x: 2.9, y: 1, z: 1});   // the body
  this.sphere(c, X.clone().addScaledVector(u, r * 1.4), r * 0.5, col, 1, c.toon_ink_m * 0.6);   // the nose band
  for (let j = 0; j < 4; j++) {   // four fins
    const w = coneDir(u, 90, j * Math.PI / 2 + k * 0.15, new THREE.Vector3()), F = X.clone().addScaledVector(u, -r * 1.3).addScaledVector(w, r * 0.7);
    const tn = this.paint(this.toon('shard', 0), c, col, 1, c.toon_ink_m * 0.5);
    [tn.m, tn.h].forEach(x => { x.position.copy(F); x.quaternion.setFromUnitVectors(XV, u); x.scale.set(r * 0.6, r * 0.55, r * 0.09); x.material.uniforms.uTaper.value = 0; });
    x_rot(tn, w, u);
  }
  const r2 = Lb.rngFor(inst.seed, s.i, 140 + t % 16), ln = r * (2.6 + 1.6 * r2()), B = X.clone().addScaledVector(u, -r * 1.8);   // the exhaust
  this.tube(nc, B.clone().addScaledVector(u, -ln), B, 0, r * 0.55, col, 220 / 255, 0); this.tube(nc, B.clone().addScaledVector(u, -ln * 0.6), B, 0, r * 0.25, HOTc, 1, 0);
  this.sphere(nc, B, r * 2.2 * 0.5, col, 150 / 255, 0);
};
function x_rot(tn, w, u) {   // stand a fin's flat side along w (its spine along u)
  const m = new THREE.Matrix4().makeBasis(u, w, new THREE.Vector3().crossVectors(u, w));
  [tn.m, tn.h].forEach(x => x.quaternion.setFromRotationMatrix(m));
}
Runner.prototype.gunImpact3 = function (inst, xf, s, a, X, stopped, col, P, dens, Us, gk, gy) {
  const Gm = G.GUNFX.geo, look = s.look, life = Gm.IMPACT_LIFE[look], B = +P.thickness * s.size * Us, nc = noCore(inst._c), HOTc = [255, 255, 255];
  const u = this.dir3(xf, s.head(!stopped ? s.flight : Math.max(0, inst.tq_ki[s.i][0] - s.b))), key = s.i * 4 + 1;
  if (look === 'tracer' || look === 'pellet') {
    if (a >= life) return; const sc = look === 'pellet' ? 0.7 : 1, q = a / life;
    if (a < 3) this.sphere(nc, X, B * (0.5 + 0.5 * easeO(a / 3)) * sc * gk * 1.4, HOTc, 1 - a / 3, 0);
    this.sphere(nc, X, B * (0.8 + 0.8 * easeO(q)) * sc * gk, col, 180 / 255 * (1 - q) * 0.7, 0);
    this.sparks3(inst, key, X, u.clone().negate(), 70, a, Math.max(0, Math.round(4 * dens)), col, 2, 5.5, 12, Us, gy);
  } else if (look === 'slug') this.heavy3(inst, key, X, u, a, life, B, dens, col, Us, gk, gy);
  else if (look === 'orb' || look === 'rocket') this.explode3(inst, key, X, a, life, B, dens, col, Us, gk, gy);
  else if (look === 'bolt') this.strike3(inst, key, X, a, life, B, dens, col, Us, gk, gy);
  else if (look === 'drill') this.shatter3(inst, key, X, u, a, life, B, dens, col, Us, gk);
};
Runner.prototype.heavy3 = function (inst, key, X, u, a, life, B, dens, col, Us, gk, gy) {
  if (a < 0 || a >= life) return;
  const Lb = SLib(), nc = noCore(inst._c), HOTc = [255, 255, 255], q = a / life, d3 = new THREE.Vector3();
  if (a < 5) this.sphere(nc, X, B * (0.6 + 0.8 * easeO(a / 5)) * gk * 1.3, HOTc, 1 - a / 5, 0);
  if (a < 9) { const e = easeO(a / 4), qs = a / 9; this.star3(inst, key, X, u, 6, B * (0.5 + 0.9 * e), B * (0.2 + 0.2 * e), col, 225 / 255 * (1 - qs), 0.2 * qs);
    this.star3(inst, key + 1, X, u, 6, B * (0.3 + 0.5 * e), B * (0.12 + 0.1 * e), HOTc, Math.pow(1 - qs, 1.5), 0.2 * qs + 0.5); }
  this.sphere(nc, X, B * (0.9 + 0.7 * easeO(q)) * gk, col, 140 / 255 * (1 - q) * 0.6, 0);
  [[0, 1.0], [3, 1.4]].forEach(dk => { const aa = a - dk[0], k = dk[1]; if (aa < 0) return; const qq = aa / (life - dk[0]), ee = easeO(qq);
    this.torus(nc, 'ring', X.clone().addScaledVector(u, B * 0.4 * ee * k), u, B * (0.3 + 1.5 * ee) * k, 0.4, 0, col, 210 / 255 * (1 - qq), 0); });
  if (a < 11) { const ql = a / 11; for (let j = 0; j < 10; j++) { const r = Lb.rngFor(inst.seed, key, 600 + j), th = r() * 6.28, ph = Math.acos(r() * 2 - 1);
    d3.set(Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th)); const r1 = B * (0.4 + 1.5 * easeO(ql)) * r.uniform(0.8, 1.2), ln = B * r.uniform(0.4, 0.8) * (1 - ql);
    this.tube(nc, X.clone().addScaledVector(d3, r1), X.clone().addScaledVector(d3, r1 + ln), 0.5 * Us, 0, Lb.mix(HOTc, col, ql), 230 / 255 * (1 - ql), 0); } }
  this.sparks3(inst, key, X, u.clone().negate(), 80, a, Math.max(0, Math.round(9 * dens)), col, 3, 7.5, 18, Us, gy);
};
Runner.prototype.explode3 = function (inst, key, X, a, life, B, dens, col, Us, gk, gy) {
  if (a < 0 || a >= life) return;
  const Lb = SLib(), c = inst._c, nc = noCore(c), HOTc = [255, 255, 255], q = a / life, ee = easeO(a / 9);
  if (a < 6) this.sphere(nc, X, B * (0.8 + 0.9 * easeO(a / 6)) * gk * 1.3, HOTc, 1 - a / 6, 0);
  this.sphere(nc, X, B * (1.0 + 0.9 * ee) * gk, col, 215 / 255 * (1 - q) * 0.6, 0);   // the fireball swelling, its hot heart
  this.sphere(c, X, B * (0.55 + 0.5 * ee) * gk * 1.2, Lb.mix(col, HOTc, 0.6), Math.pow(1 - q, 2), c.toon_ink_m * 0.6);
  for (let j = 0; j < 5; j++) { const r = Lb.rngFor(inst.seed, key, 860 + j), th = r() * 6.28, ph = Math.acos(r() * 2 - 1), d3 = new THREE.Vector3(Math.sin(ph) * Math.cos(th), Math.abs(Math.cos(ph)) * 0.8, Math.sin(ph) * Math.sin(th));
    this.sphere(c, X.clone().addScaledVector(d3, B * 0.7 * ee), B * r.uniform(0.3, 0.5) * (1 - 0.6 * q) * gk * 1.4, Lb.mix(col, HOTc, 0.25), (1 - q) * 0.85, c.toon_ink_m * 0.5); }   // billows
  [[0, 1.0, UPV], [4, 1.5, _cf]].forEach(dk => { const aa = a - dk[0]; if (aa < 0) return; const qq = aa / (life - dk[0]);
    this.torus(nc, 'ring', X, dk[2], B * (0.5 + 1.6 * easeO(qq)) * dk[1], 0.5, 0, col, 190 / 255 * (1 - qq), 0); });
  this.sparks3(inst, key, X, UPV, 180, a, Math.max(0, Math.round(12 * dens)), col, 3, 8, 22, Us, gy);
};
Runner.prototype.strike3 = function (inst, key, X, a, life, B, dens, col, Us, gk, gy) {   // lightning drops from the sky
  if (a < 0 || a >= life) return;
  const Lb = SLib(), nc = noCore(inst._c), HOTc = [255, 255, 255], q = a / life;
  if (a < 10) { const r = Lb.rngFor(inst.seed, key, 800), top = X.clone().add(new THREE.Vector3(r.uniform(-30, 30) * Us, 170 * Us, r.uniform(-30, 30) * Us)), fl = 0.75 + 0.25 * Math.sin(a * 3.1);
    const pts = jag3(inst, key * 64 + Math.floor(a / 2), top, X, 9, 12 * Us); this.poly3(nc, pts, 2.1 * Us, col, 210 / 255 * fl * (1 - a / 10)); this.poly3(nc, pts, 0.8 * Us, HOTc, 1 - a / 10); }
  if (a < 5) this.sphere(nc, X, B * (0.8 + 0.8 * easeO(a / 5)) * gk * 1.3, HOTc, 1 - a / 5, 0);
  this.sphere(nc, X, B * (0.9 + 0.6 * easeO(q)) * gk, col, 160 / 255 * (1 - q) * 0.6, 0);
  const G0 = X.clone(); if (gy != null) G0.y = gy + 0.02;
  this.torus(nc, 'ring', G0, UPV, B * (0.4 + 1.4 * easeO(q)), 0.5, 0, col, 190 / 255 * (1 - q), 0);
  if (a < 14) for (let j = 0; j < 6; j++) { const r2 = Lb.rngFor(inst.seed, key, 820 + j), th = r2() * 6.28, ph = Math.acos(r2() * 2 - 1), ln = B * r2.uniform(0.6, 1.1);
    const E = X.clone().addScaledVector(new THREE.Vector3(Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th)), ln);
    this.poly3(nc, jag3(inst, key * 64 + 32 + j + Math.floor(a / 2) * 6, X, E, 4, 5 * Us), 0.6 * Us, Lb.mix(col, HOTc, 0.5), 230 / 255 * (1 - a / 14)); }
  this.sparks3(inst, key, X, UPV, 60, a, Math.max(0, Math.round(6 * dens)), col, 2.5, 6, 16, Us, gy);
};
Runner.prototype.shatter3 = function (inst, key, X, u, a, life, B, dens, col, Us, gk) {   // the drill bursts into spinning shards
  if (a < 0 || a >= life) return;
  const Lb = SLib(), c = inst._c, nc = noCore(c), HOTc = [255, 255, 255], q = a / life, d3 = new THREE.Vector3();
  if (a < 5) this.sphere(nc, X, B * (0.6 + 0.6 * easeO(a / 5)) * gk * 1.3, HOTc, 1 - a / 5, 0);
  this.sphere(nc, X, B * (0.7 + 0.6 * easeO(q)) * gk, col, 150 / 255 * (1 - q) * 0.6, 0);
  for (let j = 0; j < Math.max(0, Math.round(8 * dens)); j++) { const r = Lb.rngFor(inst.seed, key, 900 + j), sp = r.uniform(2.5, 6), fd = Lb.dragDist(0.9, a), sz = B * r.uniform(0.15, 0.3);
    coneDir(u, Math.abs(r.uniform(-70, 70)), r() * 6.28, d3); const S = X.clone().addScaledVector(d3, sp * fd * Us), rt = r.uniform(0, 6.28) + a * r.uniform(-0.4, 0.4);
    const tn = this.paint(this.toon('shard', 0), c, Lb.mix(col, HOTc, 0.5), 1 - q, c.toon_ink_m * 0.5);
    [tn.m, tn.h].forEach(x => { x.position.copy(S); x.rotation.set(rt, rt * 0.6 + j, a * 0.3); x.scale.set(sz, sz * 0.5, sz * 0.35); x.material.uniforms.uTaper.value = 0; }); }
};
Runner.prototype.gatling3 = function (inst, xf, P, col, t, fired, total, Us, gk) {   // six barrels turning round the aim
  const Gm = G.GUNFX.geo, Lb = SLib(), c = inst._c, nc = noCore(c), endf = Gm.cad(P) + Gm.hold(P); if (t > endf + Gm.GAT_SPIN_DOWN) return;
  const am = Gm.aim(inst, t), f = am[2], u = this.dir3(xf, f), fade = t <= endf ? 1 : 1 - (t - endf) / Gm.GAT_SPIN_DOWN, phi = Gm.gatPhi(P, t);
  const M = this.w3(inst, xf, am[0] + f[0] * 4, am[1] + f[1] * 4, 0, new THREE.Vector3());
  this.torus(c, 'ring', M, u, 6 * Us, 1.2, 0, col, 170 / 255 * fade, c.toon_ink_m * 0.4);
  for (let j = 0; j < 6; j++) { const w = coneDir(u, 90, phi + j * Math.PI / 3, new THREE.Vector3()), Bp = M.clone().addScaledVector(w, 5 * Us);
    this.tube(c, Bp.clone().addScaledVector(u, -6 * Us), Bp.clone().addScaledVector(u, 4 * Us), 1.1 * Us, 1.1 * Us, Lb.mix(Gm.STEEL, col, 0.3), fade, c.toon_ink_m * 0.4); }
  const heat = fired / Math.max(1, total);
  this.sphere(nc, M, 10 * Us * gk * 0.8, Lb.mix([255, 90, 30], col, 0.3), 170 / 255 * heat * fade, 0);
  this.sphere(nc, M, 4 * Us * gk * 1.2, Lb.mix([255, 200, 120], [255, 255, 255], 0.3), 200 / 255 * heat * fade, 0);
};
Runner.prototype.charge3 = function (inst, xf, P, col, tint, t, b, dens, Us, gk) {   // the charged blast gathering its orb
  if (t > b) return;
  const Gm = G.GUNFX.geo, Lb = SLib(), c = inst._c, nc = noCore(c), HOTc = [255, 255, 255], c0 = Gm.cad(P), am = Gm.aim(inst, t), f = am[2], u = this.dir3(xf, f);
  const M = this.w3(inst, xf, am[0] + f[0] * 6, am[1] + f[1] * 6, 0, new THREE.Vector3()), R = +P.radius * Us, e = easeO(t / c0), fl = 0.85 + 0.15 * Math.sin(t * 1.3), rr = R * (0.25 + 0.85 * e);
  this.sphere(nc, M, rr * 2.4 * fl * gk * 0.8, col, 150 / 255 * 0.6, 0); this.sphere(c, M, rr * 1.3 * gk * 1.3, tint, 1, c.toon_ink_m * 0.6);
  const d3 = new THREE.Vector3();
  for (let j = 0; j < Math.max(0, Math.round(12 * dens)); j++) {   // streaks pulled in from all round
    const r0 = Lb.rngFor(inst.seed, j, 640), off = r0.uniform(0, Gm.CHARGE_P), cyc = Math.floor((t + off) / Gm.CHARGE_P), p = (((t + off) / Gm.CHARGE_P) % 1 + 1) % 1;
    const r = Lb.rngFor(inst.seed, j, 650 + cyc), th = r.uniform(0, 6.28), ph = Math.acos(r() * 2 - 1), rad = r.uniform(36, 70) * Us;
    d3.set(Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th)); const dd = rad * (1 - easeI(p)) + rr * 0.6, d2 = dd + rad * 0.25 * (1 - p);
    this.tube(nc, M.clone().addScaledVector(d3, d2), M.clone().addScaledVector(d3, dd), 0, 0.7 * Us, Lb.mix(col, HOTc, p), 230 / 255 * p, 0);
  }
  if (t < c0) for (let m = 0; m < 2; m++) { const q = (((t + m * Gm.CHARGE_RING) / (2 * Gm.CHARGE_RING)) % 1 + 1) % 1, rg = 50 * Us * (1 - easeI(q)) + rr * 0.3;
    this.torus(nc, 'ring', M, coneDir(u, m ? 60 : 0, t * 0.2, new THREE.Vector3()), rg, 0.5, 0, col, 180 / 255 * q, 0); }
  else { const a = t - c0; if (a < 5) this.star3(inst, 690, M, _cf, 4, R * 3.2 * (1 - a / 5), R * 0.4, HOTc, 1 - a / 5, Math.PI / 4);
    if (e > 0.6) for (let j = 0; j < 2; j++) { const ra = Lb.rngFor(inst.seed, j, 680 + Math.floor(t / 2)); d3.set(ra.uniform(-1, 1), ra.uniform(-1, 1), ra.uniform(-1, 1)).normalize();
      this.poly3(nc, jag3(inst, 690 + Math.floor(t / 2) * 2 + j, M, M.clone().addScaledVector(d3, rr * 2.2), 3, 3 * Us), 0.5 * Us, HOTc, 200 / 255); } }
};
Runner.prototype.aim3 = function (inst, xf, P, col, t, b, Us, gk) {   // the sniper's laser + a reticle facing the camera
  if (t >= b) return;
  const Gm = G.GUNFX.geo, Lb = SLib(), nc = noCore(inst._c), HOTc = [255, 255, 255], am = Gm.aim(inst, t), f = am[2], Lp = +P.length;
  const e = easeO(t / Math.max(1, b)), fl = 0.6 + 0.4 * Math.sin(t * 2.1), O = this.w3(inst, xf, am[0], am[1], 0, new THREE.Vector3());
  let ex = am[0] + f[0] * Lp, ey = am[1] + f[1] * Lp;
  this.tube(nc, O, this.w3(inst, xf, ex, ey, 0, new THREE.Vector3()), 0.5 * Us, 0.5 * Us, col, 120 / 255 * fl, 0);
  this.tube(nc, O, this.w3(inst, xf, ex, ey, 0, new THREE.Vector3()), 0.22 * Us, 0.22 * Us, HOTc, 150 / 255 * fl, 0);
  if (Gm.tracks(inst)) { const tp = Gm.at(inst.tq_tp, Gm.lockTick(inst, t)); if (Math.hypot(tp[0] - am[0], tp[1] - am[1]) < Lp) { ex = tp[0]; ey = tp[1]; } }
  const E = this.w3(inst, xf, ex, ey, 0, new THREE.Vector3()), rad = (26 - 18 * e) * Us, rt = (1 - e) * Math.PI / 2;
  this.torus(nc, 'ring', E, _cf, rad, 0.3, 0, col, 210 / 255, 0);
  for (let j = 0; j < 4; j++) { const an = rt + j * Math.PI / 2, d3 = _cr.clone().multiplyScalar(Math.cos(an)).addScaledVector(_cu, Math.sin(an));
    this.tube(nc, E.clone().addScaledVector(d3, rad * 0.6), E.clone().addScaledVector(d3, rad * 1.4), 0.6 * Us, 0.6 * Us, HOTc, 230 / 255, 0); }
  if (e > 0.8 && t % 4 < 2) this.sphere(nc, E, 4 * Us * gk * 1.4, HOTc, 1, 0);
  if (b - t <= 6) { const q = (b - t) / 6; this.star3(inst, 691, O, _cf, 4, (14 * (1 - q) + 2) * Us, 1.2 * Us, HOTc, 1 - q, 0); }
};
Runner.prototype.rail3 = function (inst, xf, s, P, col, t, dens, Us, gk, gy) {   // the rail: a beam with a true 3D helix, rings, heavy hits
  const Gm = G.GUNFX.geo, Lb = SLib(), nc = noCore(inst._c), HOTc = [255, 255, 255], k = t - s.b, linger = Math.max(1, Gm.hold(P)); if (k < 0) return;
  const ln = Gm.railLine(s), A = this.w3(inst, xf, ln[0], ln[1], 0, new THREE.Vector3()), Bp = this.w3(inst, xf, ln[2], ln[3], 0, new THREE.Vector3()), u = Bp.clone().sub(A), Lr = u.length(); u.normalize();
  if (k < linger) {
    const q = k / linger, W = +P.radius * (k < 2 ? 2.2 : 1.0) * (1 - q) * Us;
    this.tube(nc, A, Bp, W * 1.3 + 0.01, W * 1.3 + 0.01, col, 200 / 255 * (1 - q), 0); this.tube(nc, A, Bp, W * 0.5 + 0.01, W * 0.5 + 0.01, HOTc, Math.pow(1 - q, 1.5), 0);
    const amp = +P.radius * (1.8 + 2.4 * easeO(q)) * Us;
    [0, 1].forEach(sd => { const pts = []; for (let m = 0; m < 41; m++) { const d = Lr * m / 40, an = d / (14 * Us) + sd * Math.PI + k * 0.5;
      pts.push(A.clone().addScaledVector(u, d).addScaledVector(coneDir(u, 90, an, new THREE.Vector3()), amp)); }
      this.line3(nc, pts, 0.65 * Us, xf.az, Lb.mix(col, HOTc, 0.3), 170 / 255 * (1 - q), 0); });
    [0.15, 0.4, 0.65, 0.9].forEach((fr_, j) => { const aa = k - j; if (aa < 0) return; const qq = Math.min(1, aa / linger), ee = easeO(qq);
      this.torus(nc, 'ring', A.clone().addScaledVector(u, Lr * fr_), u, (6 + 22 * ee) * Us, 0.3, 0, col, 170 / 255 * (1 - qq), 0); });
  }
  inst.tq_imp.forEach((im, n) => { const a = t - im[0] - Gm.RAIL_DELAY, X = this.w3(inst, xf, im[1], im[2], 0, new THREE.Vector3());
    if (a < 0) { if (t >= im[0]) this.sphere(nc, X, 6 * Us * gk * 1.3, HOTc, 230 / 255, 0); return; }
    this.heavy3(inst, 9000 + n, X, u, a, Gm.IMPACT_LIFE.rail, +P.thickness * Us, dens, col, Us, gk, gy); });
};
/* the ki barrage (strikefx drawKi) */
Runner.prototype.drawKi = function (l, inst, xf) {
  const Lb = SLib(), K = G.STRIKEFX.ki, P = inst.fx.params, t = inst.age, c = inst._c, nc = noCore(c), Us = xf.Us, ink = c.toon_ink_m, HOTc = [255, 255, 255];
  const cs = Lb.colours(inst, this.host), col = cs[0], deep = cs[2] || cs[0], gk = c.strike_glow_pct / 100, gy = c.strike_ground ? l.groundY : null;
  const fr = new K.Fr(inst, 1), r0 = +P.radius * Us, B0 = +P.thickness * Us, dens = +P.density || 1, all = K.shots(inst, 1), smoke = Lb.mix(K.SMOKE, deep, 0.25);
  const WPp = p => this.w3(inst, xf, p[0], p[1], 0, new THREE.Vector3()), d3 = new THREE.Vector3();
  for (const s of all) {   // smoke piling up where they went off
    if (s.b > t) break; const bl = K.blastAt(inst, s, fr), a = t - bl[0];
    if (a < 0 || a >= K.SMOKE_LIFE || K.goneSilent(inst, s.i)) continue;
    this.puffs3(inst, 6000 + s.i, WPp([bl[1], bl[2]]), a, K.SMOKE_LIFE, Math.max(0, Math.round(3 * dens)), +P.thickness * s.size, smoke, 0.55, Us);
  }
  const last = all.length ? all[all.length - 1].b : 0;
  if (t <= last + 4) { const fa = t <= last ? 1 : 1 - (t - last) / 4, fl = 0.8 + 0.2 * Math.sin(t * 2.3);   // the hands glow
    [1, -1].forEach(side => { const h = fr.f.d(0, side * K.SIDE), X = WPp([inst.x + h[0], inst.y + h[1]]);
      this.sphere(nc, X, 16 * Us * fl * gk * 0.7, col, 150 / 255 * fa, 0); this.sphere(nc, X, 6 * Us * gk * 1.3, HOTc, 220 / 255 * fa, 0); }); }
  for (const s of all) {
    if (s.b > t) break;
    const k = t - s.b, en = s.end(inst), e = en[0], stopped = en[1], tint = Lb.mix(col, HOTc, 0.3 + s.tint), rs = r0 * s.size;
    if (k < K.FLASH) { const qf = k / K.FLASH, M = WPp(s.pos(fr, 0)), u = this.dir3(xf, fr.f.d(Math.cos(s.ang) * fr.h, Math.sin(s.ang) * fr.v));   // muzzle flash
      this.sphere(nc, M, (10 + 10 * easeO(qf)) * Us * s.size * gk * 0.8, col, 220 / 255 * (1 - qf) * 0.7, 0); this.sphere(nc, M, 6 * Us * s.size * gk * 1.2, HOTc, 1 - qf, 0);
      this.star3(inst, 6100 + s.i, M, u, 4, 16 * Us * s.size * (1 - 0.4 * qf), 1.2 * Us, HOTc, 230 / 255 * (1 - qf), 0); }
    if (t < e) {   // in flight: comet tail, glowing body, white-hot core
      const X = WPp(s.pos(fr, k)), T = WPp(s.pos(fr, Math.max(0, k - 2.5))), fl2 = 0.88 + 0.12 * Math.sin(t * 1.7 + s.i * 2.1);
      this.tube(nc, T, X, 0, rs * 0.95, col, 140 / 255, 0); this.tube(nc, T, X, 0, rs * 0.4, tint, 200 / 255, 0);
      this.sphere(nc, X, rs * 3.4 * fl2 * gk * 0.6, col, 120 / 255 * 0.7, 0);
      this.sphere(c, X, rs * 1.8 * gk * 1.2, tint, 1, ink * 0.6);
      continue;
    }
    const ad = t - e; if (ad >= K.BLAST_LIFE || K.goneSilent(inst, s.i)) continue;   // detonation
    const bp = K.blastAt(inst, s, fr), X = WPp([bp[1], bp[2]]), qd = ad / K.BLAST_LIFE, ee = easeO(ad / 8), Bd = B0 * s.size * (stopped ? 1 : 0.85);
    if (ad < 5) this.sphere(nc, X, Bd * (0.7 + 0.9 * easeO(ad / 5)) * gk * 1.3, HOTc, 1 - ad / 5, 0);
    this.sphere(nc, X, Bd * (0.9 + 1.0 * ee) * gk, col, 210 / 255 * (1 - qd) * 0.6, 0);
    this.sphere(c, X, Bd * (0.5 + 0.45 * ee) * gk * 1.2, Lb.mix(col, HOTc, 0.6), Math.pow(1 - qd, 2), ink * 0.6);
    if (s.kind >= 1) this.torus(nc, 'ring', X, s.kind === 2 ? UPV : _cf, Bd * (0.5 + 1.7 * easeO(qd)), 0.5, 0, col, 190 / 255 * (1 - qd), 0);
    const nsp = Math.max(0, Math.round((4 + 5 * (s.kind === 2 ? 1 : 0)) * dens));
    for (let j = 0; j < nsp; j++) { const rg = Lb.rngFor(inst.seed, s.i, 80 + j), life = 9 + 9 * rg(); if (ad >= life) continue;
      const th = rg.uniform(0, 6.28), ph = Math.acos(rg() * 2 - 1), sp = rg.uniform(2.5, 6.5), fd = Lb.dragDist(0.87, ad), dk = Math.pow(0.87, ad), qq = ad / life;
      d3.set(Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th));
      const Bq = X.clone().addScaledVector(d3, sp * fd * Us); Bq.y -= 0.08 * ad * ad * Us; if (gy != null && Bq.y < gy + 0.03) Bq.y = gy + 0.03;
      this.tube(nc, Bq.clone().addScaledVector(d3, -sp * dk * 1.6 * Us), Bq, 0, 0.7 * Us, Lb.mix(HOTc, col, qq), 1 - qq, 0); }
  }
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

G.FX3D = {hyperKind, U, HURT, ANCHORS, LAYS, PIVOTS, DEF3D, MOVE_DEFAULTS, MOVE_PATHS, START_MODES, MOVE_EASES, RENDERS, CHUNKS, TOON_PRIMS, STRIKE_LIMBS,
  strikeKind, bladeKind, gunKind, cfg3d, is3d, autoLay, layOf, moveCfg, byAction, Runner, movePlan, spotAround, easeU};
})(window);
