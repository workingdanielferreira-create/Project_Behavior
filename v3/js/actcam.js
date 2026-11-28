'use strict';
/* Action camera shots (Daniel 2026-11-28: "set how the camera will behave when the action is used so that it plays out to
   the best shot of each effect"). Shared by the game (camera.js) and FX Studio 3D (its Game camera preview).

   DATA: characters/<name>/<name>.fxkit.json action_settings[action].cam3d (ACTCAM.DEFAULTS). Edited in FX Studio 3D,
   section "Camera shot". His picks: a framing preset + a few sliders (no keys); plays for the fighter the camera follows
   AND the opponent, in every camera mode; a per-shot priority against the game's own shots; extras slow-mo, shake +
   crash zoom, letterbox bars.

   POSE (ACTCAM.pose): everything is measured from the LINE fighter -> target (flat, m). The camera sits round a pivot
   (fighter / target / midpoint) at Angle (0 = on the fighter's side of the pivot, i.e. behind the fighter when it is the
   pivot; 90 = to the line's right; 180 = the far side), Distance away, Height above the pivot's feet, slid Side metres
   to its own right; it looks at a look point (fighter / target / midpoint) Look height up. Over the shot it orbits
   (deg/s), pushes in (% of the distance, negative pulls out), rises (m) and zooms to an end fov. Flip mirrors the
   angle + side (always / random each use). Lock line = the line is taken once at the start (else it follows both).

   Also here, moved out of camera.js / cinecam.js unchanged so the studio previews the same shots:
   ACTCAM.gameShot (over the shoulder / reverse / side / low / wide), ACTCAM.cinePose (the Cinematic director's base
   shots) and ACTCAM.evPose (Cinematic event shots: ultimate / launch / K.O.). */
(function () {
const V = THREE.Vector3;
const DEFAULTS = {enabled: false, shot: 'shoulder',
  pivot: 'fighter', angle_deg: 0, dist_m: 3.6, height_m: 1.6, side_m: 1.25, look: 'mid', look_h_m: 1.0, fov: 50, dutch_deg: 0,
  orbit_dps: 0, push_pct: 0, rise_m: 0, fov_end: 0, flip: 'none', lock_line: false,
  length_ms: 0, hold_ms: 250, in_ms: 220, out_ms: 450, priority: 'normal',
  slow_pct: 100, slow_at_ms: 0, slow_ms: 400, shake: 0, shake_at_ms: 0, crash_pct: 0, crash_at_ms: 0, letterbox: false};
// framing presets: picking one fills the framing sliders (the sliders are what is stored and played)
const PRESETS = {
  shoulder: ['Over the shoulder', {pivot: 'fighter', angle_deg: 0, dist_m: 3.6, height_m: 1.6, side_m: 1.25, look: 'mid', look_h_m: 1.0, fov: 50}],
  reverse: ['Over the target\'s shoulder', {pivot: 'target', angle_deg: 180, dist_m: 3.6, height_m: 1.6, side_m: -1.25, look: 'mid', look_h_m: 1.0, fov: 50}],
  side: ['Side on', {pivot: 'mid', angle_deg: 90, dist_m: 6.5, height_m: 1.4, side_m: 0, look: 'mid', look_h_m: 1.0, fov: 50}],
  three_q: ['3/4 front of the fighter', {pivot: 'fighter', angle_deg: 140, dist_m: 3.8, height_m: 1.5, side_m: 0, look: 'fighter', look_h_m: 1.2, fov: 46}],
  face: ['Close-up, face on', {pivot: 'fighter', angle_deg: 170, dist_m: 2.2, height_m: 1.6, side_m: 0.3, look: 'fighter', look_h_m: 1.55, fov: 38}],
  low: ['Low hero angle', {pivot: 'fighter', angle_deg: 145, dist_m: 3.0, height_m: 0.35, side_m: 0, look: 'fighter', look_h_m: 1.4, fov: 60}],
  crane: ['High crane', {pivot: 'mid', angle_deg: 60, dist_m: 5.5, height_m: 7, side_m: 0, look: 'mid', look_h_m: 0.5, fov: 52}],
  top: ['Straight down', {pivot: 'mid', angle_deg: 0, dist_m: 0.6, height_m: 12, side_m: 0, look: 'mid', look_h_m: 0, fov: 50}],
  impact: ['On the target (impact)', {pivot: 'target', angle_deg: 120, dist_m: 3.6, height_m: 1.2, side_m: 0, look: 'target', look_h_m: 1.0, fov: 46}],
  tele: ['Long lens', {pivot: 'mid', angle_deg: 90, dist_m: 18, height_m: 2.2, side_m: 0, look: 'mid', look_h_m: 1.0, fov: 20}],
  wide: ['Wide', {pivot: 'mid', angle_deg: 70, dist_m: 13, height_m: 8, side_m: 0, look: 'mid', look_h_m: 0.5, fov: 54}]};
const PRIO = {low: 1, normal: 2, high: 3, always: 4};
const num = (v, d) => { const n = +v; return v !== '' && v != null && isFinite(n) ? n : d; };
// stored block -> a full config (missing = default); null when off
function cfg(c) { if (!c || !c.enabled) return null; const o = {};
  for (const k in DEFAULTS) { const d = DEFAULTS[k]; o[k] = typeof d === 'number' ? num(c[k], d) : typeof d === 'boolean' ? (k in c ? !!c[k] : d) : (c[k] != null && c[k] !== '' ? String(c[k]) : d); }
  o.fov = Math.max(5, Math.min(120, o.fov)); o.dist_m = Math.max(0, o.dist_m); o.slow_pct = Math.max(5, Math.min(100, o.slow_pct));
  if (!PRIO[o.priority]) o.priority = 'normal'; return o; }
// the editor's view of a block (every key filled, enabled kept)
function view(c) { return Object.assign({}, DEFAULTS, c || {}); }
const ease = u => u < .5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2;
const _d = new V(), _r = new V(), _o = new V();
/* F, T = fighter / target feet (flat, m); face = the fighter's facing (unit, flat) for when they stand on one spot;
   ms = time into the shot, len = shot length (ms), flip = 1 / -1, line = a locked line (unit) or null.
   out = {p, l, fov, roll} (Vector3s reused). */
function pose(c, F, T, face, ms, len, flip, line, out) {
  out.p = out.p || new V(); out.l = out.l || new V();
  if (line) _d.copy(line); else { _d.set(T.x - F.x, 0, T.z - F.z); if (_d.lengthSq() < 1e-4) _d.set(face.x, 0, face.z); if (_d.lengthSq() < 1e-6) _d.set(0, 0, -1); _d.normalize(); }
  const right = _r.set(-_d.z, 0, _d.x), u = len > 0 ? ease(Math.max(0, Math.min(1, ms / len))) : 0, fl = flip || 1;
  const at = w => w === 'target' ? T : w === 'fighter' ? F : null;
  const Pv = at(c.pivot) || new V().lerpVectors(F, T, .5), Lp = at(c.look) || new V().lerpVectors(F, T, .5);
  const a = (c.angle_deg + c.orbit_dps * ms / 1000) * Math.PI / 180 * fl;
  _o.set(-_d.x * Math.cos(a) + right.x * Math.sin(a), 0, -_d.z * Math.cos(a) + right.z * Math.sin(a));   // pivot -> camera (flat)
  const dist = Math.max(.3, c.dist_m * (1 - c.push_pct / 100 * u));
  out.p.copy(Pv).addScaledVector(_o, dist);
  out.p.x += _o.z * c.side_m * fl; out.p.z += -_o.x * c.side_m * fl;   // the camera's own right (it looks along -_o)
  out.p.y = Pv.y + c.height_m + c.rise_m * u; if (out.p.y < .35) out.p.y = .35;
  out.l.copy(Lp); out.l.y += c.look_h_m;
  out.fov = c.fov_end > 0 ? c.fov + (c.fov_end - c.fov) * u : c.fov;
  out.roll = c.dutch_deg * fl * Math.PI / 180;
  return out; }
// the line to lock at a shot's start
function lineOf(F, T, face) { const d = new V(T.x - F.x, 0, T.z - F.z); if (d.lengthSq() < 1e-4) d.set(face.x, 0, face.z); if (d.lengthSq() < 1e-6) d.set(0, 0, -1); return d.normalize(); }
// shot length (ms): the action's own length (or Length) + Hold
function lenOf(c, actMs) { return (c.length_ms > 0 ? c.length_ms : actMs) + Math.max(0, c.hold_ms); }
// one-off moments the clock crossed between ms0 (exclusive) and ms1 (inclusive): ['slow' | 'shake' | 'crash']
// (the first call of a shot passes ms0 = -1 so a moment at 0 ms fires)
function moments(c, ms0, ms1) { const o = [], hit = t => ms0 < t && t <= ms1;
  if (c.slow_pct < 100 && c.slow_ms > 0 && hit(c.slow_at_ms)) o.push('slow');
  if (c.shake > 0 && hit(c.shake_at_ms)) o.push('shake');
  if (c.crash_pct > 0 && hit(c.crash_at_ms)) o.push('crash');
  return o; }

/* ---- the game's own shots (moved here unchanged so FX Studio 3D previews them) ---- */
// camera.js camShot: over the shoulder / reverse / side / low / wide. pa / pb = the two fighters at 1.2 m, sep = their distance
function gameShot(mode, pa, pb, sep) { const dir = new V().subVectors(pb, pa); dir.y *= .35; if (dir.lengthSq() < 1e-4) dir.set(0, 0, -1); dir.normalize(); const right = new V(-dir.z, 0, dir.x).normalize();
  if (mode === 'shoulder' || mode === 'reverse') { const A = mode === 'shoulder' ? pa : pb, B = mode === 'shoulder' ? pb : pa, dd = mode === 'shoulder' ? dir : dir.clone().negate(); const r2 = mode === 'shoulder' ? right : right.clone().negate();
    const back = 3.6 + sep * .24; const t = A.clone().addScaledVector(dd, -back).addScaledVector(r2, 1.25 + sep * .05); t.y = A.y + .9 + sep * .1; return [t, A.clone().lerp(B, .6).add(new V(0, .35, 0))]; }
  if (mode === 'side') { const m = pa.clone().lerp(pb, .5); const t = m.clone().addScaledVector(right, 5.5 + sep * .75); t.y = m.y + 1.2 + sep * .12; return [t, m]; }
  if (mode === 'low') { const t = pa.clone().addScaledVector(dir, -2.6).addScaledVector(right, 1.9); t.y = Math.max(.35, pa.y - 1.3); return [t, pb.clone().add(new V(0, .8, 0))]; }
  const m = pa.clone().lerp(pb, .5); const t = m.clone().add(new V(0, 13 + sep * .35, 19 + sep * .4)); return [t, m]; }
// cinecam.js cinePose: S = the shot (cineShot), ctx = {pa, pb, mid, dir, right, sep}, side = the 180-degree-rule side; writes W {p, l, fov, roll}
function cinePose(S, ctx, age, side, W) { const {pa, pb, mid, dir, right, sep} = ctx, up = new V(0, 1, 0); let p, l, fov = 50;
  const k = S.kind;
  if (k === 'two') { const d = (4.2 + sep * .55) * S.dk; p = mid.clone().addScaledVector(right, side * d * .87).addScaledVector(dir, -S.fb * d * .42); p.y = mid.y + 1.1 + sep * .08 * S.hk; l = mid.clone().addScaledVector(up, .75); fov = 50; }
  else if (k === 'ots') { const A = S.subj ? pb : pa, B = S.subj ? pa : pb, dd = B.clone().sub(A); dd.y = 0; if (dd.lengthSq() < 1e-4) dd.copy(dir); dd.normalize();
    const back = 3.2 + sep * .22; p = A.clone().addScaledVector(dd, -back).addScaledVector(right, side * (1.25 + sep * .05)); p.y = A.y + .9 + sep * .08; l = A.clone().lerp(B, .62).addScaledVector(up, .3); fov = 46; }
  else if (k === 'low') { p = mid.clone().addScaledVector(right, side * (3.2 + sep * .42) * S.dk).addScaledVector(dir, -S.fb * 1.6); p.y = Math.max(.75, Math.min(pa.y, pb.y) - .45); l = mid.clone().addScaledVector(up, 1.25); fov = 60; }   // low, but above crater lips
  else if (k === 'high') { p = mid.clone().addScaledVector(right, side * (5 + sep * .4)).addScaledVector(dir, -S.fb * 3); p.y = mid.y + (7 + sep * .35) * S.hk; l = mid.clone(); fov = 52; }
  else if (k === 'orbit') { const th = S.th0 + S.orbitW * age, c = Math.cos(th), s = Math.sin(th), r = (5 + sep * .55) * S.dk;
    const off = new V(right.x * c - right.z * s, 0, right.x * s + right.z * c).multiplyScalar(side * r); p = mid.clone().add(off); p.y = mid.y + 1.4 + sep * .1; l = mid.clone().addScaledVector(up, .7); fov = 50; }
  else if (k === 'tele') { const d = (16 + sep * 1.1) * S.dk; p = mid.clone().addScaledVector(right, side * d).addScaledVector(dir, -S.fb * d * .25); p.y = mid.y + 2.2 * S.hk; l = mid.clone().addScaledVector(up, .7);
    fov = Math.max(14, Math.min(40, 2 * Math.atan((sep * .62 + 2.4) / d) * 180 / Math.PI)); }
  else { p = mid.clone().addScaledVector(right, side * (9 + sep * .5)).addScaledVector(dir, -S.fb * (6 + sep * .3)); p.y = mid.y + 8 + sep * .3; l = mid.clone(); fov = 54; }   // wide
  // the shot's own drift: dolly in / out, truck round the look point
  const dl = Math.max(.6, 1 - S.dolly * age), tr = S.truck * age, dx = p.x - l.x, dz = p.z - l.z, c = Math.cos(tr), s = Math.sin(tr);
  p.set(l.x + (dx * c - dz * s) * dl, l.y + (p.y - l.y) * dl, l.z + (dx * s + dz * c) * dl);
  W.p.copy(p); W.l.copy(l); W.fov = fov; W.roll = S.roll; }
// cinecam.js cineEvPose (fighter shots): kind ult / launch / ko; P = that fighter's feet, fd = its facing (unit flat),
// u = 0..1 through the shot, th0 = the K.O. orbit's start angle, dutch = settings.cineDutch (deg)
function evPose(kind, P, fd, ctx, age, u, side, th0, dutch, W) { const up = new V(0, 1, 0);
  if (kind === 'ult') { const pr = new V(-fd.z, 0, fd.x); const d = 2.9 * (1 - .2 * u);
    W.p.copy(P).addScaledVector(fd, d).addScaledVector(pr, side * 1.4); W.p.y = P.y + .75; W.l.copy(P).addScaledVector(up, 1.45).addScaledVector(fd, .2); W.fov = 52; W.roll = side * dutch * .8 * Math.PI / 180; }
  else if (kind === 'launch') { const o = ctx.pa.distanceToSquared(P) < ctx.pb.distanceToSquared(P) ? ctx.pb : ctx.pa; const ln = P.clone().sub(o); ln.y = 0; if (ln.lengthSq() < 1e-4) ln.copy(ctx.dir); ln.normalize();
    const pr = new V(-ln.z, 0, ln.x); W.p.copy(P).addScaledVector(pr, side * (6.5 + P.y * .4)).addScaledVector(ln, -2); W.p.y = Math.max(.6, P.y * .45 + .8); W.l.copy(P).addScaledVector(up, 1); W.fov = 54; W.roll = 0; }
  else { const th = th0 + .35 * age, r = 4.2; W.p.set(P.x + Math.cos(th) * r, P.y + .9, P.z + Math.sin(th) * r); W.l.copy(P).addScaledVector(up, .6); W.fov = 48; W.roll = side * dutch * .5 * Math.PI / 180; } }

window.ACTCAM = {DEFAULTS, PRESETS, PRIO, cfg, view, pose, lineOf, lenOf, moments, ease, gameShot, cinePose, evPose};
})();
