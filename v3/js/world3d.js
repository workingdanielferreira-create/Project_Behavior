'use strict';
/* World 3D (Daniel 2026-11-24): the little planet V3 fights on. Shared by the game (v3/js/planet.js) and
   World Studio 3D (v3/tools/worldstudio3d.html), so the studio preview IS the game's world.
   Settings file: characters/world3d.json (format pb_world3d), packed by build_kits.py into data/world.gen.js
   (window.PB3_WORLD). Every section and every destructible type has its own on / off.

   How the globe works:
   - The fight itself stays on the flat sim plane (2D px, no walls when the planet is on). A vertex-shader bend
     (installBend, patched into three.js's project_vertex chunk) wraps every normal object onto a sphere of radius R
     about the ANCHOR (the eased fight centre): a point d metres from the anchor sits at arc length d round the globe,
     its height along the local up. Fighters, FX, shots and dust need no changes and follow the curve.
   - The planet and everything ON it (ground, cover, pillars, scenery, landmarks, craters, clouds, ring) live in one
     group that is NOT bent (define PB_NOBEND). As the anchor moves the group rolls (quaternion Q), so you can run all
     the way round the globe and come back to the same rocks.
   - Planet-fixed things are stored as unit vectors u (planet space). flatOf(u) gives their spot on the sim plane
     right now (used for collisions); surfaceU(x, z) turns a sim spot into u (used for craters / blasts).
   The look is randomised each world (seed) from the assets that are switched on. */
const World3D = (function () {

/* ------------------------------------------------------------------ settings schema
   field: [key, label, type, default, min, max, step, help]   type: bool | num | list (default = array, min = options) */
const LOOKS = ['meadow', 'dusk', 'moon', 'crystal', 'lava', 'ice', 'desert'];
const SECTIONS = [
  {id: 'planet', title: 'Planet', help: 'The globe itself. Off = the flat walled arena exactly as before.', fields: [
    ['enabled', 'Planet on', 'bool', true, 0, 0, 0, 'Off = the old flat arena with walls (everything else on this page except Gravity is ignored).'],
    ['radius_m', 'Planet radius (m)', 'num', 55, 15, 400, 1, 'A fighter is 1.8 m tall. Smaller = the horizon comes closer and you run round it faster.'],
    ['seed', 'World seed', 'num', 0, 0, 99999, 1, '0 = a new random world every fight. Any other number = always the same world.'],
    ['looks', 'Ground looks to pick from', 'list', LOOKS.slice(), LOOKS, 0, 0, 'Each world picks one of the ticked looks at random (colours of ground, rocks, trees, sky).'],
    ['patches', 'Ground patchiness (%)', 'num', 60, 0, 100, 1, 'How blotchy the ground colours are.'],
    ['start_clear_m', 'Open ground at the start (m)', 'num', 14, 0, 80, 1, 'Nothing is placed this close to where the fight starts.'],
    ['roll_ease', 'Globe turn speed', 'num', 3, 0.5, 20, 0.5, 'How quickly the globe turns to keep the fight on top (higher = tighter).']]},
  {id: 'gravity', title: 'Gravity', help: 'Jumps, falls and throws. Used on the planet AND the flat arena; 100 % = as before.', fields: [
    ['gravity_pct', 'Gravity (%)', 'num', 100, 10, 400, 1, 'How hard everything falls back down.'],
    ['jump_pct', 'Jump height (%)', 'num', 100, 10, 400, 1, 'First jump and double jump height.'],
    ['max_jumps', 'Jumps in a row', 'num', 2, 1, 6, 1, '2 = jump + double jump.'],
    ['fast_fall_pct', 'Fast fall (F) strength (%)', 'num', 100, 0, 400, 1, ''],
    ['bounce_pct', 'Thrown-fighter bounce (%)', 'num', 22, 0, 100, 1, 'How high a thrown fighter bounces once when it lands.'],
    ['splat_speed', 'Ground splat speed (px/s)', 'num', 1500, 300, 6000, 50, 'A thrown fighter landing faster than this gets a GROUND SPLAT.'],
    ['launch_power_pct', 'Launch power (%)', 'num', 100, 10, 500, 5, 'Knockback speed when a hit throws a fighter into the air.'],
    ['launch_carry_pct', 'Launch carry (%)', 'num', 100, 10, 1000, 5, 'How far a thrown fighter keeps flying. 400+ = flies far over the horizon, round the globe.'],
    ['ground_slide_pct', 'Ground slide (%)', 'num', 100, 10, 400, 5, 'How far a knockback slides along the ground.']]},
  {id: 'sky', title: 'Sky', help: 'Stars, nebula, moons and a planetary ring.', fields: [
    ['enabled', 'Sky extras on', 'bool', true],
    ['stars', 'Stars', 'num', 900, 0, 5000, 50, ''],
    ['nebula', 'Nebula colours', 'bool', true, 0, 0, 0, 'Soft colour clouds painted on the sky.'],
    ['moons', 'Moons (up to)', 'num', 2, 0, 6, 1, 'Each world has 0 .. this many moons.'],
    ['moon_size_pct', 'Moon size (%)', 'num', 100, 20, 400, 5, ''],
    ['ring_chance', 'Ring chance (%)', 'num', 50, 0, 100, 1, 'Chance the planet has a ring round it.'],
    ['ring_width_pct', 'Ring width (%)', 'num', 100, 20, 300, 5, '']]},
  {id: 'atmosphere', title: 'Atmosphere', help: 'Haze, clouds and floating dust.', fields: [
    ['enabled', 'Atmosphere on', 'bool', true],
    ['fog', 'Horizon haze', 'bool', true, 0, 0, 0, 'Distance fog in the sky colour.'],
    ['fog_pct', 'Haze distance (%)', 'num', 100, 10, 400, 5, 'Higher = clearer, further view.'],
    ['clouds', 'Clouds', 'num', 22, 0, 150, 1, 'Clouds drifting round the planet.'],
    ['cloud_height_m', 'Cloud height (m)', 'num', 16, 3, 150, 1, ''],
    ['cloud_speed', 'Cloud speed (%)', 'num', 100, 0, 1000, 5, ''],
    ['motes', 'Floating dust motes', 'num', 220, 0, 2000, 10, 'Specks floating round the camera.']]},
  {id: 'cover', title: 'Ground cover', help: 'Small decoration on the ground (no collisions). Amounts are per 1,000 m² (a 32 m square).', fields: [
    ['enabled', 'Ground cover on', 'bool', true],
    ['grass', 'Grass tufts', 'num', 30, 0, 200, 1, ''],
    ['stones', 'Small stones', 'num', 6, 0, 80, 1, ''],
    ['crystals', 'Small crystals', 'num', 2, 0, 40, 0.5, ''],
    ['size_pct', 'Size (%)', 'num', 100, 20, 400, 5, '']]},
  {id: 'landmarks', title: 'Landmarks', help: 'A few big set pieces that work as cover. Never break.', fields: [
    ['enabled', 'Landmarks on', 'bool', true],
    ['count', 'How many', 'num', 4, 0, 16, 1, 'Over the whole planet.'],
    ['kinds', 'Kinds to pick from', 'list', ['arch', 'ruin_wall', 'giant_crystal', 'monolith', 'rock_spire'], ['arch', 'ruin_wall', 'giant_crystal', 'monolith', 'rock_spire'], 0, 0, ''],
    ['size_pct', 'Size (%)', 'num', 100, 30, 300, 5, ''],
    ['solid', 'Solid (blocks bodies and shots)', 'bool', true]]},
  {id: 'pillars', title: 'Destructible: pillars & boulders', help: 'Rock pillars and boulder stacks. Block bodies and shots; break on strong hits, throws and blasts.', fields: [
    ['enabled', 'Pillars on', 'bool', true],
    ['density', 'Pillars per 1,000 m²', 'num', 1.2, 0, 10, 0.1, ''],
    ['size_pct', 'Size (%)', 'num', 100, 30, 400, 5, ''],
    ['multi_chance', 'Boulder stacks (%)', 'num', 35, 0, 100, 1, 'Chance a pillar is a stack of 2-3 boulders instead.'],
    ['hp', 'Toughness (HP)', 'num', 120, 1, 2000, 1, ''],
    ['break_speed', 'Smash-through speed (px/s)', 'num', 1600, 100, 8000, 50, 'A thrown fighter at least this fast smashes straight through.'],
    ['break_damage', 'One-hit break damage', 'num', 45, 1, 500, 1, 'A single hit, shot or blast this strong breaks it at once.'],
    ['chip_pct', 'Chip damage (%)', 'num', 60, 0, 200, 5, 'Weaker hits still wear it down by this % of their damage.'],
    ['block_shots', 'Blocks shots', 'bool', true],
    ['splat', 'Pillar splat', 'bool', true, 0, 0, 0, 'A fighter thrown into one (and not breaking it) gets a PILLAR SPLAT.'],
    ['regrow_s', 'Regrow after (s)', 'num', 15, 0, 600, 1, '0 = stays broken until the next fight.']]},
  {id: 'ground', title: 'Destructible: ground damage', help: 'Craters, trenches and scorch marks left on the ground.', fields: [
    ['enabled', 'Ground damage on', 'bool', true],
    ['craters', 'Craters', 'bool', true, 0, 0, 0, 'Splats, heavy hits, hard landings, K.O.s and blasts.'],
    ['crater_pct', 'Crater size (%)', 'num', 100, 20, 400, 5, ''],
    ['trenches', 'Trenches', 'bool', true, 0, 0, 0, 'Fast knockback slides along the ground carve a trench.'],
    ['scorch', 'Scorch marks', 'bool', true, 0, 0, 0, 'Shots and blasts that hit the ground or a pillar.'],
    ['fade_s', 'Fade after (s)', 'num', 25, 0, 600, 1, '0 = stays until the next fight.'],
    ['max_marks', 'Most marks at once', 'num', 90, 5, 400, 5, 'The oldest goes first.']]},
  {id: 'scenery', title: 'Destructible: scenery', help: 'Trees, crystal clusters and old columns. They break when hit, thrown into or blasted.', fields: [
    ['enabled', 'Breakable scenery on', 'bool', true],
    ['trees', 'Trees per 1,000 m²', 'num', 1.5, 0, 20, 0.1, ''],
    ['tree_kinds', 'Tree kinds to pick from', 'list', ['pine', 'round', 'dead'], ['pine', 'round', 'dead'], 0, 0, ''],
    ['crystals', 'Crystal clusters per 1,000 m²', 'num', 0.5, 0, 10, 0.1, ''],
    ['columns', 'Old columns per 1,000 m²', 'num', 0.4, 0, 10, 0.1, ''],
    ['size_pct', 'Size (%)', 'num', 100, 30, 300, 5, ''],
    ['hp', 'Toughness (HP)', 'num', 40, 1, 1000, 1, ''],
    ['break_speed', 'Smash-through speed (px/s)', 'num', 900, 100, 8000, 50, ''],
    ['break_damage', 'One-hit break damage', 'num', 25, 1, 500, 1, ''],
    ['solid', 'Solid (fighters bump into them)', 'bool', true, 0, 0, 0, 'Off = fighters pass through; they still break when hit.'],
    ['regrow_s', 'Regrow after (s)', 'num', 20, 0, 600, 1, '0 = stays broken until the next fight.']]}
];
function defaults() {
  const o = {format: 'pb_world3d', version: 1};
  for (const s of SECTIONS) { o[s.id] = {}; for (const f of s.fields) o[s.id][f[0]] = Array.isArray(f[3]) ? f[3].slice() : f[3]; }
  return o;
}
// Defaults + whatever the file holds (wrong types / unknown keys dropped; numbers kept as typed, no clamping).
function merge(src) {
  const o = defaults(); if (!src || typeof src !== 'object') return o;
  for (const s of SECTIONS) { const v = src[s.id]; if (!v || typeof v !== 'object') continue;
    for (const f of s.fields) { const x = v[f[0]];
      if (f[2] === 'bool' && typeof x === 'boolean') o[s.id][f[0]] = x;
      else if (f[2] === 'num' && typeof x === 'number' && isFinite(x)) o[s.id][f[0]] = x;
      else if (f[2] === 'list' && Array.isArray(x)) o[s.id][f[0]] = x.filter(k => f[4].includes(k)); } }
  return o;
}

/* ------------------------------------------------------------------ the bend (vertex shader) */
const BEND = {x: 0, y: 0, z: 0, w: 0};   // x / z = anchor (scene units), w = planet radius (0 = flat, no bend)
function installBend() {
  if (THREE.__pbBend) return; THREE.__pbBend = true;
  const C = THREE.ShaderChunk;
  C.logdepthbuf_pars_vertex = C.logdepthbuf_pars_vertex + `
uniform vec4 pbBend;
vec3 pbBendP(vec3 p) {
  vec2 d = p.xz - pbBend.xz; float r = length(d); if (r < 1e-5) return p;
  float R = pbBend.w, th = r / R, rr = R + p.y; vec2 dir = d / r;
  return vec3(pbBend.x + dir.x * sin(th) * rr, cos(th) * rr - R, pbBend.z + dir.y * sin(th) * rr);
}`;
  C.project_vertex = `vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
#ifndef PB_NOBEND
if (pbBend.w > 0.0) { vec4 pbW = modelMatrix * mvPosition; pbW.xyz = pbBendP(pbW.xyz); mvPosition = viewMatrix * pbW; }
else mvPosition = modelViewMatrix * mvPosition;
#else
mvPosition = modelViewMatrix * mvPosition;
#endif
gl_Position = projectionMatrix * mvPosition;`;
  // one shared value object: UniformsUtils.clone copies plain objects by reference, so every material sees it
  for (const k in THREE.ShaderLib) { const s = THREE.ShaderLib[k]; if (s && s.uniforms) s.uniforms.pbBend = {value: BEND}; }
}
// The same bend in JS (camera, HUD labels): scene point v (flat) -> where it is drawn. Returns a new vector.
function bendV(v) {
  if (!(BEND.w > 0)) return v.clone();
  const dx = v.x - BEND.x, dz = v.z - BEND.z, r = Math.hypot(dx, dz); if (r < 1e-5) return v.clone();
  const R = BEND.w, th = r / R, rr = R + v.y;
  return new THREE.Vector3(BEND.x + dx / r * Math.sin(th) * rr, Math.cos(th) * rr - R, BEND.z + dz / r * Math.sin(th) * rr);
}

/* ------------------------------------------------------------------ looks (palettes) */
const PAL = {
  meadow: {ground: [0x4f8f3e, 0x6aa84a, 0x3b7134], dirt: 0x7a5c3a, rock: [0x8a8c98, 0x6c6f7d], grass: [0x7cc957, 0x5aa845], leaf: [0x3f9a4a, 0x2f7d3f, 0x7fb84a], trunk: 0x5a3d26, crystal: [0x7fe3ff, 0xa58bff], sky: [0x2b62b8, 0xa8d6f5], fog: 0xb4d4ec, neb: [0xffffff, 0xbfe0ff], ring: 0xdfe8f5, cloud: 0xffffff, moon: [0xf2f0e6, 0xd9d4c6]},
  dusk: {ground: [0x1a2148, 0x232c5c, 0x141a3a], dirt: 0x2c2552, rock: [0x2f3668, 0x242a52], grass: [0x3b4d8f, 0x4a3f8f], leaf: [0x3a3f8a, 0x2c3170, 0x5a4aa0], trunk: 0x1c1838, crystal: [0x9a7aff, 0x5fd0ff], sky: [0x0a0d24, 0x3a2f6a], fog: 0x1c1f44, neb: [0x7a4ad0, 0x3a6ad0], ring: 0x8a86c8, cloud: 0x8a86c8, moon: [0xe8e4ff, 0xb8b0e8]},
  moon: {ground: [0x8d8f96, 0x9fa1a8, 0x76787f], dirt: 0x5e6068, rock: [0x6e7079, 0x55575f], grass: [0x9a9ca4, 0x85878f], leaf: [0x7d7f88, 0x6a6c75, 0x92949c], trunk: 0x4a4c53, crystal: [0xcfe8ff, 0xffffff], sky: [0x02030a, 0x1a1c2a], fog: 0x14151f, neb: [0x40508a, 0x8a5070], ring: 0xb8b8c0, cloud: 0x9a9aa4, moon: [0x6aa0ff, 0xffa060]},
  crystal: {ground: [0x3b2a6a, 0x4d3a8a, 0x2c2054], dirt: 0x5a3f8f, rock: [0x5c4a9a, 0x463a7a], grass: [0x8a6aff, 0x5fd0e0], leaf: [0x6a5aff, 0x40c0e0, 0xb070ff], trunk: 0x2c2054, crystal: [0x70f0ff, 0xff7af0, 0xb0a0ff], sky: [0x120a30, 0x6a3fa0], fog: 0x40306a, neb: [0xff60d0, 0x60c0ff], ring: 0xc0a0ff, cloud: 0xd0c0ff, moon: [0xffd0f8, 0xc0f0ff]},
  lava: {ground: [0x2a1a1a, 0x3a2220, 0x1c1212], dirt: 0x6a2a10, rock: [0x3a2a28, 0x2a1e1c], grass: [0xff6a1a, 0x9a3a10], leaf: [0x5a2a1a, 0x3a1c14, 0xff7a2a], trunk: 0x1a1010, crystal: [0xff8a2a, 0xffd04a], sky: [0x1a0606, 0x8a2a10], fog: 0x4a1a10, neb: [0xff4a1a, 0xffa040], ring: 0xff9a5a, cloud: 0x5a4a48, moon: [0xffc080, 0xff7040]},
  ice: {ground: [0xdde8f2, 0xc4d8ea, 0xeef4fa], dirt: 0x9ab8d4, rock: [0xa8c4dc, 0x86a6c4], grass: [0xffffff, 0xcfe4f4], leaf: [0xbfe0f0, 0x9cc8e4, 0xe8f6ff], trunk: 0x6a7f94, crystal: [0x9fe8ff, 0xd0f4ff], sky: [0x3a6aa8, 0xcfe6f8], fog: 0xdcecf8, neb: [0xa0e0ff, 0xffffff], ring: 0xe8f4ff, cloud: 0xffffff, moon: [0xffffff, 0xd8e8ff]},
  desert: {ground: [0xd9a860, 0xe4b874, 0xc6924c], dirt: 0xa8703a, rock: [0xb07a4a, 0x8f5f38], grass: [0xa8a040, 0xc0b060], leaf: [0x6f8f3a, 0x5a7a30, 0x9aa848], trunk: 0x6a4a2a, crystal: [0x60e0d0, 0xffe080], sky: [0x3a7ac8, 0xf0d8a8], fog: 0xf0d8b0, neb: [0xffd0a0, 0xffffff], ring: 0xf0e0c0, cloud: 0xffffff, moon: [0xfff4e0, 0xe8d8c0]}
};

/* ------------------------------------------------------------------ helpers */
function rngOf(seed) { let a = (seed >>> 0) || 1; return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a);
  t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const UP = new THREE.Vector3(0, 1, 0);
function gradMap() { const d = new Uint8Array([70, 70, 70, 255, 150, 150, 150, 255, 255, 255, 255, 255]);
  const t = new THREE.DataTexture(d, 3, 1, THREE.RGBAFormat); t.minFilter = t.magFilter = THREE.NearestFilter; t.needsUpdate = true; return t; }
const NB = {PB_NOBEND: ''};
// built-in materials only take defines after construction (it is not a constructor option)
function nb(m) { m.defines = Object.assign({}, m.defines || {}, NB); return m; }

/* ------------------------------------------------------------------ the world */
class World {
  // scene: THREE.Scene. cfg: merged settings. opts: {seed, studio}
  constructor(scene, cfg, opts) {
    opts = opts || {}; this.scene = scene; this.cfg = cfg; this.studio = !!opts.studio;
    const P = cfg.planet; this.R = Math.max(2, P.radius_m);
    this.seed = opts.seed || P.seed || ((Math.random() * 1e9) | 0); this.rnd = rngOf(this.seed);
    const looks = (P.looks && P.looks.length ? P.looks : LOOKS); this.lookName = looks[(this.rnd() * looks.length) | 0]; this.pal = PAL[this.lookName] || PAL.dusk;
    this.Q = new THREE.Quaternion(); this.A = new THREE.Vector3();   // planet roll, anchor (scene units, flat)
    this.time = 0; this.items = []; this.solids = []; this.marks = []; this.debris = []; this.grows = [];
    this.grad = gradMap(); this.mats = {}; this.geos = [];
    this.inkMat = nb(new THREE.MeshBasicMaterial({color: 0x04050b, side: THREE.BackSide}));
    this.root = new THREE.Group(); this.root.name = 'pb_planet'; scene.add(this.root);   // rolls with Q
    this.sky = new THREE.Group(); this.sky.name = 'pb_sky'; scene.add(this.sky);          // follows the camera
    this.area = 4 * Math.PI * this.R * this.R;
    this._buildGround(); this._buildSky(); this._buildAtmos(); this._buildCover(); this._buildLandmarks();
    this._buildPillars(); this._buildScenery(); this._place();
  }
  // ---------------------------------------------------------------- materials
  toon(c, extra) { const k = 't' + c + (extra ? JSON.stringify(extra) : ''); if (!this.mats[k]) this.mats[k] = nb(new THREE.MeshToonMaterial(Object.assign({color: c, gradientMap: this.grad}, extra || {}))); return this.mats[k]; }
  basic(c, extra) { const k = 'b' + c + (extra ? JSON.stringify(extra) : ''); if (!this.mats[k]) this.mats[k] = nb(new THREE.MeshBasicMaterial(Object.assign({color: c}, extra || {}))); return this.mats[k]; }
  inked(geo, mat, s) { this.geos.push(geo); const a = new THREE.Mesh(geo, mat); const b = new THREE.Mesh(geo, this.inkMat); b.scale.setScalar(s || 1.06); a.add(b); return a; }
  pick(arr) { return arr[(this.rnd() * arr.length) | 0]; }
  r(a, b) { return a + this.rnd() * (b - a); }
  // ---------------------------------------------------------------- planet space helpers
  randU() { const z = this.r(-1, 1), a = this.r(0, Math.PI * 2), s = Math.sqrt(1 - z * z); return new THREE.Vector3(Math.cos(a) * s, z, Math.sin(a) * s); }
  // u far enough from the start spot (top, u = +Y at fight start) and from other solids
  freeU(rad, tries) { const clear = this.cfg.planet.start_clear_m / this.R;
    for (let i = 0; i < (tries || 30); i++) { const u = this.randU(); if (Math.acos(Math.min(1, u.y)) < clear + rad / this.R) continue;
      if (this.solids.some(s => s.u.angleTo(u) * this.R < s.r + rad + 0.6)) continue; return u; }
    return null; }
  // orient obj so its +Y is u, random spin, base lifted
  orient(obj, u, lift, spin) { obj.position.copy(u).multiplyScalar(this.R + (lift || 0)); obj.quaternion.setFromUnitVectors(UP, u);
    if (spin !== 0) obj.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(UP, spin == null ? this.r(0, Math.PI * 2) : spin)); }
  // planet space u -> spot on the flat sim plane, scene units {x, z} (valid near the anchor)
  flatOf(u) { const v = u.clone().applyQuaternion(this.Q); const th = Math.acos(Math.max(-1, Math.min(1, v.y))), h = Math.hypot(v.x, v.z);
    if (h < 1e-6) return {x: this.A.x, z: this.A.z, th}; return {x: this.A.x + v.x / h * th * this.R, z: this.A.z + v.z / h * th * this.R, th}; }
  // flat scene spot -> planet space unit vector
  surfaceU(x, z) { const dx = x - this.A.x, dz = z - this.A.z, d = Math.hypot(dx, dz), th = d / this.R;
    const v = d < 1e-6 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(dx / d * Math.sin(th), Math.cos(th), dz / d * Math.sin(th));
    return v.applyQuaternion(this.Q.clone().invert()); }
  // flat direction (dx, dz) at spot u -> planet-space tangent
  tangentAt(u, dx, dz) { const w = new THREE.Vector3(dx, 0, dz).applyQuaternion(this.Q.clone().invert()); w.addScaledVector(u, -w.dot(u)); return w.lengthSq() > 1e-9 ? w.normalize() : null; }
  // ---------------------------------------------------------------- anchor + roll
  setAnchor(x, z, snap, dt) {
    const k = snap ? 1 : 1 - Math.exp(-this.cfg.planet.roll_ease * (dt || 0.016));
    const nx = this.A.x + (x - this.A.x) * k, nz = this.A.z + (z - this.A.z) * k; const dx = nx - this.A.x, dz = nz - this.A.z, d = Math.hypot(dx, dz);
    if (d > 1e-7) { const axis = new THREE.Vector3(-dz / d, 0, dx / d); this.Q.premultiply(new THREE.Quaternion().setFromAxisAngle(axis, d / this.R)).normalize(); }
    this.A.set(nx, 0, nz); this._place(); }
  _place() { this.root.position.set(this.A.x, -this.R, this.A.z); this.root.quaternion.copy(this.Q);
    BEND.x = this.A.x; BEND.z = this.A.z; BEND.w = this.studio ? 0 : this.R; }
  // ---------------------------------------------------------------- ground
  _buildGround() {
    const P = this.cfg.planet, pal = this.pal, R = this.R;
    const det = Math.max(6, Math.min(60, Math.round(1.05 * R / 2.2) - 1));
    const g = new THREE.IcosahedronGeometry(R, det); this.geos.push(g);
    const pos = g.attributes.position, col = []; const c0 = new THREE.Color(pal.ground[0]), c1 = new THREE.Color(pal.ground[1]), c2 = new THREE.Color(pal.ground[2]), cd = new THREE.Color(pal.dirt);
    const K = []; for (let i = 0; i < 5; i++) K.push([this.randU().multiplyScalar(this.r(1.5, 5)), this.r(0, 6.28)]);
    const pt = P.patches / 100; const tmp = new THREE.Color(), v = new THREE.Vector3();
    // per face (non-indexed): one colour per triangle -> faceted toon patches
    for (let i = 0; i < pos.count; i += 3) {
      v.set((pos.getX(i) + pos.getX(i + 1) + pos.getX(i + 2)) / 3, (pos.getY(i) + pos.getY(i + 1) + pos.getY(i + 2)) / 3, (pos.getZ(i) + pos.getZ(i + 1) + pos.getZ(i + 2)) / 3).normalize();
      let n = 0; for (const [k, ph] of K) n += Math.sin(v.dot(k) + ph); n = n / K.length;   // -1..1
      const j = (Math.sin(i * 12.9898) * 43758.5453) % 1;   // a little per-face jitter
      tmp.copy(c0).lerp(n > 0 ? c1 : c2, Math.min(1, Math.abs(n) * 2.2 * pt));
      if (n > 0.55 && pt > 0) tmp.lerp(cd, Math.min(1, (n - 0.55) * 3 * pt));
      tmp.offsetHSL(0, 0, (j - 0.5) * 0.03);
      for (let q = 0; q < 3; q++) col.push(tmp.r, tmp.g, tmp.b);
    }
    g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
    const m = new THREE.Mesh(g, nb(new THREE.MeshToonMaterial({vertexColors: true, gradientMap: this.grad})));
    const ink = new THREE.Mesh(g, this.inkMat); ink.scale.setScalar(1.0015); m.add(ink);
    this.ground = m; this.root.add(m);
  }
  // ---------------------------------------------------------------- sky (stars, nebula, moons) + ring
  _buildSky() {
    const S = this.cfg.sky, pal = this.pal, on = S.enabled;
    // dome: sky gradient (+ nebula blotches), never fogged, drawn first
    const g = new THREE.SphereGeometry(300, 40, 20); this.geos.push(g); const pos = g.attributes.position, c = [];
    const top = new THREE.Color(pal.sky[0]), hz = new THREE.Color(pal.sky[1]); const nebs = [];
    if (on && S.nebula) for (let i = 0; i < 5; i++) nebs.push([this.randU(), this.r(.25, .6), new THREE.Color(this.pick(pal.neb)), this.r(.15, .35)]);
    const v = new THREE.Vector3(), tc = new THREE.Color();
    for (let i = 0; i < pos.count; i++) { v.set(pos.getX(i), pos.getY(i), pos.getZ(i)).normalize();
      tc.copy(hz).lerp(top, Math.pow(Math.max(0, v.y), .55));
      for (const [u, w, nc, a] of nebs) { const d = v.angleTo(u); if (d < w * 2) tc.lerp(nc, a * Math.max(0, 1 - d / (w * 2)) ** 2); }
      c.push(tc.r, tc.g, tc.b); }
    g.setAttribute('color', new THREE.Float32BufferAttribute(c, 3));
    const dome = new THREE.Mesh(g, nb(new THREE.MeshBasicMaterial({vertexColors: true, side: THREE.BackSide, fog: false, depthWrite: false})));
    dome.renderOrder = -10; this.sky.add(dome);
    if (on && S.stars > 0) { const n = Math.round(S.stars), p = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) { const u = this.randU(); u.y = Math.abs(u.y) * .95 + .05; u.normalize().multiplyScalar(this.r(250, 290)); p[i * 3] = u.x; p[i * 3 + 1] = u.y; p[i * 3 + 2] = u.z; }
      const sg = new THREE.BufferGeometry(); sg.setAttribute('position', new THREE.BufferAttribute(p, 3)); this.geos.push(sg);
      const st = new THREE.Points(sg, nb(new THREE.PointsMaterial({color: 0xdfe6ff, size: 1.1, sizeAttenuation: true, fog: false, transparent: true, opacity: this.lookName === 'meadow' || this.lookName === 'desert' || this.lookName === 'ice' ? .35 : .9, depthWrite: false})));
      st.renderOrder = -9; this.sky.add(st); }
    if (on) { const nm = Math.round(this.rnd() * (S.moons + .999)) | 0;
      for (let i = 0; i < Math.min(nm, S.moons); i++) { const r = this.r(6, 18) * S.moon_size_pct / 100; const mg = new THREE.IcosahedronGeometry(r, 3); this.geos.push(mg);
        const mm = new THREE.Mesh(mg, nb(new THREE.MeshBasicMaterial({color: this.pick(pal.moon), fog: false})));
        const u = this.randU(); u.y = this.r(.15, .75); u.normalize(); mm.position.copy(u).multiplyScalar(240); mm.renderOrder = -8;
        // a darker crescent shadow over one side
        const sh = new THREE.Mesh(mg, nb(new THREE.MeshBasicMaterial({color: pal.sky[0], fog: false, transparent: true, opacity: .55, depthWrite: false})));
        sh.position.set(r * .35, r * .1, r * .3); sh.scale.setScalar(.98); mm.add(sh); this.sky.add(mm); }
      if (this.rnd() * 100 < S.ring_chance) { const R = this.R, w = S.ring_width_pct / 100; const rg = new THREE.RingGeometry(R * 1.55, R * (1.55 + .8 * w), 128, 3); this.geos.push(rg);
        const rc = rg.attributes.position, cc = []; const a = new THREE.Color(pal.ring), b = new THREE.Color(pal.ring).offsetHSL(0, 0, -.25);
        for (let i = 0; i < rc.count; i++) { const d = Math.hypot(rc.getX(i), rc.getY(i)); const t = Math.sin(d * 1.7) * .5 + .5; const q = a.clone().lerp(b, t); cc.push(q.r, q.g, q.b); }
        rg.setAttribute('color', new THREE.Float32BufferAttribute(cc, 3));
        const ring = new THREE.Mesh(rg, nb(new THREE.MeshBasicMaterial({vertexColors: true, side: THREE.DoubleSide, transparent: true, opacity: .55, depthWrite: false, fog: false})));
        ring.rotation.set(Math.PI / 2 + this.r(-.5, .5), 0, this.r(-.4, .4)); this.root.add(ring); this.ring = ring; } }
  }
  // ---------------------------------------------------------------- atmosphere: clouds + motes (fog is set by the host)
  _buildAtmos() {
    const A = this.cfg.atmosphere; this.clouds = null; this.motes = null; if (!A.enabled) return;
    if (A.clouds > 0) { this.clouds = new THREE.Group(); this.root.add(this.clouds); const cm = this.toon(this.pal.cloud, {transparent: true, opacity: .85});
      for (let i = 0; i < A.clouds; i++) { const c = new THREE.Group(); const u = this.randU(); const n = 3 + (this.rnd() * 4 | 0); const s = this.r(1.5, 4);
        for (let k = 0; k < n; k++) { const sg = new THREE.IcosahedronGeometry(s * this.r(.6, 1.1), 1); this.geos.push(sg); const b = new THREE.Mesh(sg, cm); b.position.set((k - n / 2) * s * .8, this.r(-.2, .4) * s, this.r(-.5, .5) * s); b.scale.y = .55; c.add(b); }
        this.orient(c, u, A.cloud_height_m * this.r(.8, 1.25)); this.clouds.add(c); }
      this.cloudAxis = this.randU(); }
    if (A.motes > 0) { const n = Math.round(A.motes), p = new Float32Array(n * 3); for (let i = 0; i < n * 3; i++) p[i] = this.r(-30, 30);
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p, 3)); this.geos.push(g);
      this.motes = new THREE.Points(g, nb(new THREE.PointsMaterial({color: this.pick(this.pal.crystal), size: .12, transparent: true, opacity: .55, depthWrite: false, blending: THREE.AdditiveBlending})));
      this.motes.frustumCulled = false; this.motesV = Array.from({length: n}, () => [this.r(-.4, .4), this.r(-.2, .3), this.r(-.4, .4)]); this.sky.add(this.motes); }
  }
  // fog distances for the host scene (null = no fog)
  fogRange() { const A = this.cfg.atmosphere; if (!A.enabled || !A.fog) return null; const k = A.fog_pct / 100; const hz = Math.sqrt(2 * this.R * 12);
    return [Math.max(10, hz * .55 * k), Math.max(30, (hz * 1.6 + 40) * k)]; }
  // ---------------------------------------------------------------- ground cover (instanced, no collisions)
  _buildCover() {
    const C = this.cfg.cover; if (!C.enabled) return; const s = C.size_pct / 100, per = this.area / 1000;
    const kinds = [
      ['grass', new THREE.ConeGeometry(.09 * s, .55 * s, 4), this.pal.grass, .25 * s],
      ['stones', new THREE.DodecahedronGeometry(.22 * s, 0), this.pal.rock, .08 * s],
      ['crystals', new THREE.OctahedronGeometry(.22 * s, 0), this.pal.crystal, .3 * s]];
    const clear = this.cfg.planet.start_clear_m * .35 / this.R; const o = new THREE.Object3D(), col = new THREE.Color();
    for (const [k, geo, cols, lift] of kinds) { const n = Math.min(12000, Math.round(C[k] * per)); if (!n) continue; this.geos.push(geo);
      const mat = k === 'crystals' ? nb(new THREE.MeshBasicMaterial({color: 0xffffff})) : nb(new THREE.MeshToonMaterial({color: 0xffffff, gradientMap: this.grad}));
      const im = new THREE.InstancedMesh(geo, mat, k === 'grass' ? n * 3 : n); let j = 0;
      for (let i = 0; i < n; i++) { let u = this.randU(); if (Math.acos(Math.min(1, u.y)) < clear) u = this.randU();
        const blades = k === 'grass' ? 3 : 1;
        for (let b = 0; b < blades; b++) { this.orient(o, u, lift, null); if (k === 'grass') { o.translateX((b - 1) * .1 * s); o.rotateZ((b - 1) * .3); o.scale.setScalar(this.r(.7, 1.3)); }
          else if (k === 'stones') { o.scale.set(this.r(.6, 1.6), this.r(.4, .9), this.r(.6, 1.6)); }
          else { o.scale.set(1, this.r(1.6, 3), 1); o.rotateX(this.r(-.4, .4)); }
          o.updateMatrix(); im.setMatrixAt(j, o.matrix); col.set(this.pick(cols)).offsetHSL(0, 0, this.r(-.05, .05)); im.setColorAt(j, col); j++; } }
      im.count = j; im.instanceMatrix.needsUpdate = true; if (im.instanceColor) im.instanceColor.needsUpdate = true; this.root.add(im); }
  }
  // ---------------------------------------------------------------- items (solids): pillars, scenery, landmarks
  _addItem(kind, group, u, mesh, cols, o) {
    const it = Object.assign({kind, group, u, mesh, hp: 1, maxHp: 1, dead: false, regrowAt: 0, solid: true, breakable: true, color: 0x888888, height: 2}, o || {});
    it.cols = cols.map(c => ({item: it, u: c.u || u, r: c.r, h: c.h})); it.cols.forEach(c => this.solids.push(c));
    this.items.push(it); this.root.add(mesh); return it; }
  _buildLandmarks() {
    const L = this.cfg.landmarks; if (!L.enabled || !L.count || !L.kinds.length) return; const s = L.size_pct / 100, pal = this.pal;
    for (let i = 0; i < L.count; i++) { const kind = this.pick(L.kinds); const u = this.freeU(6 * s, 60); if (!u) continue;
      const g = new THREE.Group(); const rock = this.toon(pal.rock[0]), rock2 = this.toon(pal.rock[1]); let cols = [];
      const spin = this.r(0, Math.PI * 2); this.orient(g, u, 0, spin);
      const colAt = (lx, lz, r, h) => { const p = new THREE.Vector3(lx, 0, lz).applyQuaternion(g.quaternion).add(g.position).normalize(); return {u: p, r, h}; };
      if (kind === 'arch') { const h = this.r(7, 10) * s, sp = this.r(4, 6) * s;
        for (const x of [-sp, sp]) { const leg = this.inked(new THREE.BoxGeometry(1.4 * s, h, 1.4 * s), rock); leg.position.set(x, h / 2, 0); g.add(leg); cols.push(colAt(x, 0, .9 * s, h)); }
        const top = this.inked(new THREE.BoxGeometry(sp * 2 + 2.4 * s, 1.3 * s, 1.8 * s), rock2); top.position.y = h + .5 * s; top.rotation.z = this.r(-.05, .05); g.add(top); }
      else if (kind === 'ruin_wall') { const n = 3 + (this.rnd() * 3 | 0); let x = -n * 1.1 * s;
        for (let k = 0; k < n; k++) { const h = this.r(1.5, 6) * s; const b = this.inked(new THREE.BoxGeometry(2 * s, h, 1 * s), k % 2 ? rock : rock2); b.position.set(x, h / 2, this.r(-.2, .2)); b.rotation.y = this.r(-.1, .1); g.add(b); cols.push(colAt(x, 0, 1.05 * s, h)); x += 2.2 * s; } }
      else if (kind === 'giant_crystal') { const cm = this.basic(this.pick(pal.crystal)); const h = this.r(9, 15) * s;
        const c0 = this.inked(new THREE.OctahedronGeometry(1, 0), cm, 1.08); c0.scale.set(2 * s, h / 2, 2 * s); c0.position.y = h * .42; g.add(c0);
        for (let k = 0; k < 4; k++) { const c = this.inked(new THREE.OctahedronGeometry(1, 0), cm, 1.08); const a = k / 4 * 6.28 + this.r(-.3, .3); c.scale.set(.9 * s, this.r(2, 4) * s, .9 * s); c.position.set(Math.cos(a) * 1.8 * s, 1.4 * s, Math.sin(a) * 1.8 * s); c.rotation.set(Math.sin(a) * .5, 0, -Math.cos(a) * .5); g.add(c); }
        cols.push(colAt(0, 0, 2.4 * s, h)); }
      else if (kind === 'monolith') { const h = this.r(10, 16) * s; const m = this.inked(new THREE.BoxGeometry(2.2 * s, h, .9 * s), this.toon(0x15161c)); m.position.y = h / 2 - .5; m.rotation.z = this.r(-.08, .08); g.add(m);
        const glow = new THREE.Mesh(new THREE.PlaneGeometry(.25 * s, h * .7), this.basic(this.pick(pal.crystal), {side: THREE.DoubleSide})); glow.position.set(0, h * .5, .47 * s); g.add(glow); cols.push(colAt(0, 0, 1.3 * s, h)); }
      else { const h = this.r(12, 20) * s; let y = 0, r = 3 * s;   // rock spire
        while (y < h) { const seg = this.inked(new THREE.CylinderGeometry(r * .75, r, h / 4, 6), y % 2 ? rock : rock2, 1.04); seg.position.set(this.r(-.3, .3), y + h / 8, this.r(-.3, .3)); seg.rotation.y = this.r(0, 1); g.add(seg); y += h / 4; r *= .72; }
        cols.push(colAt(0, 0, 2.6 * s, h)); }
      if (!L.solid) cols = [];
      this._addItem('landmark', 'landmarks', u, g, cols, {breakable: false, solid: !!L.solid, color: pal.rock[0], height: 8 * s}); }
  }
  _pillarMesh(s, stack) { const pal = this.pal, g = new THREE.Group(); let y = 0; const parts = [];
    if (stack) { const n = 2 + (this.rnd() * 2 | 0); let r = this.r(1.2, 1.8) * s;
      for (let k = 0; k < n; k++) { const b = this.inked(new THREE.DodecahedronGeometry(r, 0), this.toon(pal.rock[k % 2])); b.scale.y = .8; b.position.set(this.r(-.2, .2) * r, y + r * .8, this.r(-.2, .2) * r); b.rotation.set(this.r(0, 3), this.r(0, 3), 0); g.add(b); parts.push(b); y += r * 1.45; r *= this.r(.65, .85); }
      return {g, h: y, r: 1.6 * s, parts}; }
    const h = this.r(3.5, 7) * s, r = this.r(.8, 1.5) * s; const n = 2 + (this.rnd() * 2 | 0);
    for (let k = 0; k < n; k++) { const sh = h / n; const b = this.inked(new THREE.CylinderGeometry(r * (1 - (k + 1) * .12), r * (1 - k * .12) * 1.05, sh, 6 + (this.rnd() * 2 | 0)), this.toon(pal.rock[k % 2]), 1.05); b.position.set(this.r(-.1, .1), y + sh / 2, this.r(-.1, .1)); b.rotation.y = this.r(0, 3); g.add(b); parts.push(b); y += sh; }
    const cap = this.inked(new THREE.DodecahedronGeometry(r * .7, 0), this.toon(pal.rock[1])); cap.position.y = y; cap.scale.y = .6; g.add(cap); parts.push(cap);
    return {g, h: y + r * .3, r: r * 1.05, parts}; }
  _buildPillars() {
    const P = this.cfg.pillars; if (!P.enabled) return; const s = P.size_pct / 100; const n = Math.min(400, Math.round(P.density * this.area / 1000));
    for (let i = 0; i < n; i++) { const stack = this.rnd() * 100 < P.multi_chance; const pm = this._pillarMesh(s, stack); const u = this.freeU(pm.r); if (!u) continue;
      this.orient(pm.g, u, -.1); this._addItem('pillar', 'pillars', u, pm.g, [{r: pm.r, h: pm.h}], {hp: P.hp, maxHp: P.hp, color: this.pal.rock[0], height: pm.h, parts: pm.parts}); }
  }
  _treeMesh(kind, s) { const pal = this.pal, g = new THREE.Group(); const trunk = this.toon(pal.trunk); let h;
    if (kind === 'pine') { h = this.r(4, 7) * s; const t = this.inked(new THREE.CylinderGeometry(.18 * s, .28 * s, h * .4, 6), trunk); t.position.y = h * .2; g.add(t);
      const lc = this.toon(this.pick(pal.leaf)); for (let k = 0; k < 3; k++) { const c = this.inked(new THREE.ConeGeometry((1.6 - k * .4) * s, h * .38, 7), lc, 1.05); c.position.y = h * (.38 + k * .2); c.rotation.y = this.r(0, 1); g.add(c); } }
    else if (kind === 'round') { h = this.r(3.5, 6) * s; const t = this.inked(new THREE.CylinderGeometry(.2 * s, .32 * s, h * .55, 6), trunk); t.position.y = h * .27; g.add(t);
      const lc = this.toon(this.pick(pal.leaf)); for (let k = 0; k < 3; k++) { const c = this.inked(new THREE.IcosahedronGeometry(this.r(1, 1.6) * s, 0), lc, 1.05); c.position.set(this.r(-.6, .6) * s, h * .7 + this.r(-.3, .4) * s, this.r(-.6, .6) * s); g.add(c); } }
    else { h = this.r(3, 5.5) * s; const t = this.inked(new THREE.CylinderGeometry(.12 * s, .3 * s, h, 5), trunk); t.position.y = h / 2; g.add(t);
      for (let k = 0; k < 4; k++) { const L = this.r(.8, 1.6) * s; const b = this.inked(new THREE.CylinderGeometry(.04 * s, .1 * s, L, 4), trunk); const a = this.r(0, 6.28); b.position.set(Math.cos(a) * L * .35, h * this.r(.55, .9), Math.sin(a) * L * .35); b.rotation.set(Math.sin(a) * .9, 0, -Math.cos(a) * .9); g.add(b); } }
    return {g, h, r: .45 * s}; }
  _buildScenery() {
    const S = this.cfg.scenery; if (!S.enabled) return; const s = S.size_pct / 100, per = this.area / 1000, pal = this.pal;
    const add = (kind, n, make) => { for (let i = 0; i < Math.min(500, Math.round(n * per)); i++) { const m = make(); const u = this.freeU(m.r + .5); if (!u) continue; this.orient(m.g, u, -.05);
      this._addItem(kind, 'scenery', u, m.g, S.solid ? [{r: m.r, h: m.h}] : [], {hp: S.hp, maxHp: S.hp, solid: !!S.solid, color: m.col, height: m.h}); } };
    if (S.tree_kinds.length) add('tree', S.trees, () => { const k = this.pick(S.tree_kinds); const m = this._treeMesh(k, s); m.col = pal.leaf[0]; return m; });
    add('crystal', S.crystals, () => { const g = new THREE.Group(); const c = this.pick(pal.crystal); const cm = this.basic(c); let h = 0;
      for (let k = 0; k < 4; k++) { const q = this.inked(new THREE.OctahedronGeometry(1, 0), cm, 1.1); const hh = this.r(1, 2.6) * s; q.scale.set(.35 * s, hh, .35 * s); const a = k * 1.7; q.position.set(Math.cos(a) * .4 * s, hh * .6, Math.sin(a) * .4 * s); q.rotation.set(Math.sin(a) * .35, 0, -Math.cos(a) * .35); g.add(q); h = Math.max(h, hh * 1.6); }
      return {g, h, r: .8 * s, col: c}; });
    add('column', S.columns, () => { const g = new THREE.Group(); const h = this.r(2, 5) * s; const m = this.toon(pal.rock[0]);
      const c = this.inked(new THREE.CylinderGeometry(.5 * s, .55 * s, h, 10), m); c.position.y = h / 2; g.add(c); const b = this.inked(new THREE.BoxGeometry(1.4 * s, .35 * s, 1.4 * s), this.toon(pal.rock[1])); b.position.y = .17 * s; g.add(b);
      if (this.rnd() < .5) { const t = this.inked(new THREE.BoxGeometry(1.3 * s, .3 * s, 1.3 * s), this.toon(pal.rock[1])); t.position.y = h; g.add(t); } else c.rotation.z = this.r(-.05, .05);
      return {g, h, r: .6 * s, col: pal.rock[0]}; });
  }
  // ---------------------------------------------------------------- hits on items
  cfgOf(it) { return it.group === 'pillars' ? this.cfg.pillars : it.group === 'scenery' ? this.cfg.scenery : null; }
  // dmg = damage of a hit / shot / blast, speed = px/s of a thrown fighter (0 if none). dir = planet tangent (optional).
  // Returns 'break', 'chip', 'block' (unbreakable) or null (dead / no effect).
  hitItem(it, dmg, speed, dir) {
    if (it.dead) return null; const C = this.cfgOf(it); if (!it.breakable || !C) return 'block';
    if ((speed && speed >= C.break_speed) || dmg >= C.break_damage) { this.breakItem(it, dir, Math.max(dmg, speed / 40)); return 'break'; }
    const chip = dmg * (C.chip_pct == null ? 100 : C.chip_pct) / 100; it.hp -= chip;
    if (it.hp <= 0) { this.breakItem(it, dir, dmg); return 'break'; }
    // wobble on a chip
    it.wob = 1; return 'chip'; }
  breakItem(it, dir, power) {
    if (it.dead) return; it.dead = true; it.mesh.visible = false; const C = this.cfgOf(it);
    it.regrowAt = C && C.regrow_s > 0 ? this.time + C.regrow_s : 0;
    // debris: chunks of the item fly off (planet gravity pulls them back), dust
    const n = it.kind === 'pillar' ? 12 : it.kind === 'tree' ? 8 : 7; const base = it.u.clone().multiplyScalar(this.R);
    const col = it.kind === 'tree' ? [this.pal.trunk, it.color] : [it.color, this.pal.rock[1]];
    for (let i = 0; i < n; i++) { const sz = this.r(.2, .55) * (it.kind === 'pillar' ? 1.4 : 1); const geo = new THREE.DodecahedronGeometry(sz, 0); this.geos.push(geo);
      const m = this.inked(geo, it.kind === 'crystal' ? this.basic(it.color) : this.toon(col[i % 2]));
      const p = base.clone().addScaledVector(it.u, this.r(.3, it.height)); m.position.copy(p); this.root.add(m);
      const t = new THREE.Vector3(this.r(-1, 1), this.r(-1, 1), this.r(-1, 1)); t.addScaledVector(it.u, -t.dot(it.u)).normalize();
      const v = t.multiplyScalar(this.r(2, 6)).addScaledVector(it.u, this.r(3, 9)); if (dir) v.addScaledVector(dir, this.r(4, 10) * Math.min(2, (power || 20) / 30));
      this.debris.push({m, v, life: this.r(1.4, 2.4), t: 0, spin: new THREE.Vector3(this.r(-8, 8), this.r(-8, 8), this.r(-8, 8)), sz}); }
    for (let i = 0; i < 6; i++) this._puff(it.u, this.r(.2, it.height * .7), this.pal.fog || 0xaaaaaa); }
  _puff(u, h, col) { const g = new THREE.IcosahedronGeometry(this.r(.5, 1), 0); this.geos.push(g); const m = new THREE.Mesh(g, nb(this.basic(col, {transparent: true, opacity: .45, depthWrite: false}).clone()));
    m.position.copy(u).multiplyScalar(this.R + h); this.root.add(m); const t = new THREE.Vector3(this.r(-1, 1), this.r(-1, 1), this.r(-1, 1)); t.addScaledVector(u, -t.dot(u));
    this.debris.push({m, v: t.multiplyScalar(this.r(1, 3)).addScaledVector(u, this.r(.5, 2)), life: this.r(.6, 1.1), t: 0, puff: true}); }
  // blast at planet spot u: radius m, damage. Returns how many items it broke.
  blastU(u, radius, dmg) { let n = 0; for (const it of this.items) { if (it.dead || !it.breakable) continue; const d = it.u.angleTo(u) * this.R; if (d > radius + 1) continue;
      const dir = it.u.clone().sub(u); dir.addScaledVector(it.u, -dir.dot(it.u)); if (dir.lengthSq() > 1e-9) dir.normalize();
      if (this.hitItem(it, dmg * (1 - .5 * Math.min(1, d / (radius + 1))), 0, dir.lengthSq() ? dir : null) === 'break') n++; }
    return n; }
  // ---------------------------------------------------------------- ground damage
  _mark(o) { const G = this.cfg.ground; this.marks.push(o); this.root.add(o.m); o.born = this.time; o.fade = G.fade_s;
    while (this.marks.length > G.max_marks) { const x = this.marks.shift(); this.root.remove(x.m); } }
  _decalMat(c, op) { return nb(new THREE.MeshBasicMaterial({color: c, transparent: true, opacity: op, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2})); }
  crater(u, size) { const G = this.cfg.ground; if (!G.enabled || !G.craters) return; const r = size * G.crater_pct / 100; if (r < .2) return;
    const g = new THREE.Group(); this.orient(g, u, .03); const dark = new THREE.Color(this.pal.dirt).multiplyScalar(.45);
    const floor = new THREE.Mesh(new THREE.CircleGeometry(r, 14), this._decalMat(dark, .85)); floor.rotation.x = -Math.PI / 2; g.add(floor);
    const lip = new THREE.Mesh(new THREE.RingGeometry(r * .92, r * 1.25, 14), this._decalMat(new THREE.Color(this.pal.dirt), .9)); lip.rotation.x = -Math.PI / 2; lip.position.y = .01; g.add(lip);
    for (let i = 0; i < Math.min(10, 3 + r * 2); i++) { const a = this.r(0, 6.28), sz = this.r(.06, .14) * Math.min(3, r); const b = new THREE.Mesh(new THREE.DodecahedronGeometry(sz, 0), nb(this.toon(this.pal.rock[1], {transparent: true}).clone()));
      b.position.set(Math.cos(a) * r * this.r(1, 1.4), sz * .3, Math.sin(a) * r * this.r(1, 1.4)); g.add(b); }
    g.children.forEach(c => this.geos.push(c.geometry)); this._mark({m: g, kind: 'crater'}); }
  trench(u, dir, len, w) { const G = this.cfg.ground; if (!G.enabled || !G.trenches) return; const g = new THREE.Group(); this.orient(g, u, .025, 0);
    if (dir) { const local = dir.clone().applyQuaternion(g.quaternion.clone().invert()); g.rotateY(Math.atan2(-local.z, local.x)); }
    const m = new THREE.Mesh(new THREE.CircleGeometry(1, 10), this._decalMat(new THREE.Color(this.pal.dirt).multiplyScalar(.5), .8)); m.rotation.x = -Math.PI / 2; m.scale.set(len * .6, w, 1); g.add(m);
    const edge = new THREE.Mesh(new THREE.RingGeometry(.85, 1.1, 10), this._decalMat(new THREE.Color(this.pal.dirt), .7)); edge.rotation.x = -Math.PI / 2; edge.scale.set(len * .6, w, 1); edge.position.y = .005; g.add(edge);
    g.children.forEach(c => this.geos.push(c.geometry)); this._mark({m: g, kind: 'trench'}); }
  scorch(u, size) { const G = this.cfg.ground; if (!G.enabled || !G.scorch) return; const g = new THREE.Group(); this.orient(g, u, .02);
    const m = new THREE.Mesh(new THREE.CircleGeometry(size, 12), this._decalMat(0x0a0806, .55)); m.rotation.x = -Math.PI / 2; g.add(m); this.geos.push(m.geometry); this._mark({m: g, kind: 'scorch'}); }
  // ---------------------------------------------------------------- per-frame update (real seconds)
  // camPos: camera position (scene); canRegrow(item) -> false while something stands in the way (host check)
  update(dt, camPos, canRegrow) {
    this.time += dt; const g = 53 * (this.cfg.gravity.gravity_pct / 100);   // 2600 px/s² in metres
    if (camPos) { this.sky.position.copy(camPos); }
    if (this.clouds && this.cloudAxis) this.clouds.quaternion.multiply(new THREE.Quaternion().setFromAxisAngle(this.cloudAxis, dt * .01 * this.cfg.atmosphere.cloud_speed / 100));
    if (this.motes) { const a = this.motes.geometry.attributes.position.array; for (let i = 0; i < this.motesV.length; i++) { for (let k = 0; k < 3; k++) { a[i * 3 + k] += this.motesV[i][k] * dt; if (a[i * 3 + k] > 30) a[i * 3 + k] -= 60; else if (a[i * 3 + k] < -30) a[i * 3 + k] += 60; } }
      this.motes.geometry.attributes.position.needsUpdate = true; }
    for (let i = this.debris.length - 1; i >= 0; i--) { const d = this.debris[i]; d.t += dt; const p = d.m.position; const len = p.length();
      if (d.puff) { p.addScaledVector(d.v, dt); d.m.scale.setScalar(1 + d.t * 2); d.m.material.opacity = .45 * (1 - d.t / d.life); }
      else { d.v.addScaledVector(p, -g * dt / len); p.addScaledVector(d.v, dt); d.m.rotation.x += d.spin.x * dt; d.m.rotation.y += d.spin.y * dt;
        const L = p.length(); if (L < this.R + d.sz * .5) { p.multiplyScalar((this.R + d.sz * .5) / L); const n = p.clone().normalize(); const vn = d.v.dot(n); if (vn < 0) d.v.addScaledVector(n, -vn * 1.35); d.v.multiplyScalar(.6); d.spin.multiplyScalar(.6); }
        if (d.t > d.life - .4) d.m.scale.setScalar(Math.max(.01, (d.life - d.t) / .4)); }
      if (d.t >= d.life) { this.root.remove(d.m); if (d.puff) d.m.material.dispose(); this.debris.splice(i, 1); } }
    for (const it of this.items) {
      if (it.wob > 0) { it.wob = Math.max(0, it.wob - dt * 4); const w = Math.sin(this.time * 60) * .06 * it.wob; it.mesh.children.forEach(c => { c.rotation.z = (c.userData.rz == null ? (c.userData.rz = c.rotation.z) : c.userData.rz) + w; }); }
      if (it.dead && it.regrowAt > 0 && this.time >= it.regrowAt && (!canRegrow || canRegrow(it))) { it.dead = false; it.hp = it.maxHp; it.mesh.visible = true; it.grow = 0; }
      if (it.grow != null) { it.grow = Math.min(1, it.grow + dt * 2.5); const e = 1 - Math.pow(1 - it.grow, 3); it.mesh.scale.setScalar(Math.max(.01, e)); if (it.grow >= 1) it.grow = null; } }
    for (let i = this.marks.length - 1; i >= 0; i--) { const mk = this.marks[i]; if (!(mk.fade > 0)) continue; const age = this.time - mk.born; const left = mk.fade - age;
      if (left < 2) mk.m.traverse(o => { if (o.material) { if (o.material.userData.op == null) o.material.userData.op = o.material.opacity; o.material.opacity = o.material.userData.op * Math.max(0, left / 2); } });
      if (left <= 0) { this.root.remove(mk.m); this.marks.splice(i, 1); } }
  }
  dispose() { this.scene.remove(this.root); this.scene.remove(this.sky); this.geos.forEach(g => g.dispose && g.dispose());
    for (const k in this.mats) this.mats[k].dispose(); this.inkMat.dispose(); this.grad.dispose(); BEND.w = 0; }
}

// Gravity numbers for the game (gravity.js / fighter.js / combat.js read these; 100 % = the old constants).
function gravityOf(cfg) { const G = cfg.gravity;
  return {gravity: 2600 * G.gravity_pct / 100, jump: G.jump_pct / 100, maxJumps: Math.max(1, Math.round(G.max_jumps)), fastFall: 3.2 * G.fast_fall_pct / 100,
    bounce: G.bounce_pct / 100, splat: G.splat_speed, launchPower: G.launch_power_pct / 100, airFric: 1.1 * 100 / Math.max(1, G.launch_carry_pct), groundFric: 7 * 100 / Math.max(1, G.ground_slide_pct)}; }

return {SECTIONS, LOOKS, PAL, defaults, merge, installBend, bendV, BEND, World, gravityOf};
})();
if (typeof window !== 'undefined') window.World3D = World3D;
