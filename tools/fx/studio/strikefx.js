/* Strikes — FX Studio's port of laser/strikefx.py: the ki barrage and impact
 * punch styles of the FX Kit "technique" primitive.  Same timeline, same
 * random streams (FXK.rng), same geometry and painting order as the game, so
 * the Studio preview draws what Solo and Battle draw.  Keep the two in step.
 * Builds on swordfx.js (frame, pen, maths) and hitfx.js (what the punch
 * paints: its motion, impact and environment partitions): load it after both.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };
var H_ = function () { return G.HITFX; };
var STYLES = ["ki_barrage", "impact_punch"];

var KI_SPEED = [9, 13], KI_RANGE = [0.85, 1.12], KI_SIDE = 7, KI_FLASH = 6, KI_BLAST_LIFE = 22, KI_SMOKE_LIFE = 44;
var SMOKE = [92, 86, 80];
var PUNCH_RETRACT = 5, PUNCH_IMPACT_LIFE = 24;
var IMPACT_FRAME_TICKS = 2, FULL_FRAME = 20000, INK = [16, 10, 22];
// Hit options (params hitstop / hitstop_ticks, kb_dir / kb_angle_deg,
// impact_frame / impact_frame_r): the strikes they apply to.
var HIT_OPTION_STYLES = ["impact_punch", "roundhouse_kick", "thrust_kick", "axe_kick", "spinning_kick", "rising_kick"];

// ---------------------------------------------------------------- timeline
function cad(P) { return Math.max(1, Math.trunc(+P.swing_ticks || 3)); }
function hold(P) { return L_().holdT(P); }
function kiCount(P) { return Math.floor(hold(P) / cad(P)) + 1; }
function kiFlightMax(P) { return Math.ceil(+P.length * KI_RANGE[1] / KI_SPEED[0]); }
function activeTicks(P) {
  if (L_().style(P) === "ki_barrage") return (kiCount(P) - 1) * cad(P) + kiFlightMax(P) + 1;
  return L_().swing(P) + hold(P) + 1;
}
function totalTicks(P) {
  if (L_().style(P) === "ki_barrage") return activeTicks(P) + KI_SMOKE_LIFE;
  return L_().swing(P) + hold(P) + PUNCH_RETRACT + PUNCH_IMPACT_LIFE;
}

// ---------------------------------------------------------------- ki shots
// One ki blast: everything about it is rolled from the seed.
function Shot(inst, i, ps) {
  var P = inst.fx.params, L = L_(), r = L.rngFor(inst.seed, i, 41);
  var su = r.uniform(KI_SPEED[0], KI_SPEED[1]);
  this.i = i;
  this.b = i * cad(P);
  this.sp = su * ps;
  this.ang = r.uniform(-0.5, 0.5) * (+P.span || 0) * L.D;
  this.curve = r.uniform(-22, 22) * ps;
  this.size = r.uniform(0.75, 1.25);
  if (r() < 0.18) this.size *= 1.55;   // now and then a much bigger one
  this.size *= (inst.tq_grow || {})[i] || 1;   // grown by absorbing (FXK.absorbGrow)
  var ru = r.uniform(KI_RANGE[0], KI_RANGE[1]);
  this.rng = +P.length * ru * ps;
  this.flight = Math.max(1, Math.ceil(+P.length * ru / su));
  this.side = i % 2 === 0 ? 1 : -1;
  this.tint = r.uniform(0, 0.4);
  this.kind = Math.min(2, Math.trunc(r() * 3));
  var path = inst.tq_path, o = path[Math.min(this.b, path.length - 1)];
  this.ox = o[0]; this.oy = o[1];
  this.trk = (inst.tq_kd || {})[i] || null;
}
// World position k ticks after launch; from the tick an intercept pulled it
// off its path, the recorded one.
Shot.prototype.pos = function (fr, k) {
  var tr = this.trk;
  if (tr && this.b + k >= tr[0]) {
    var h = tr[1], j = this.b + k - tr[0], n = Math.floor(j);
    if (n >= h.length - 1) return h[h.length - 1].slice();
    var u = j - n, a = h[n], b = h[n + 1];
    return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u];
  }
  var d = this.sp * k, u = this.rng > 0 ? Math.min(1, d / this.rng) : 1;
  var lat = this.curve * Math.sin(Math.PI * u), ca = Math.cos(this.ang), sa = Math.sin(this.ang);
  var w = fr.f.d(ca * d - sa * lat, sa * d + ca * lat + this.side * KI_SIDE * fr.s);
  return [this.ox + w[0], this.oy + w[1]];
};
Shot.prototype.end = function (inst) {   // [tick it detonates, stopped by a hit?]
  var h = inst.tq_ki[this.i];
  return h ? [h[0], true] : [this.b + this.flight, false];
};
function Fr(inst, ps) { this.f = new (L_().Frame)(0, 0, inst.tq_f, inst.tq_m); this.s = ps; }
function shots(inst, ps) {
  var out = [], n = kiCount(inst.fx.params);
  for (var i = 0; i < n; i++) out.push(new Shot(inst, i, ps));
  return out;
}
function live(inst, ps) {   // [[shot, position]] for the shots in flight this tick
  var out = [], fr = new Fr(inst, ps), t = inst.age, all = shots(inst, ps);
  for (var i = 0; i < all.length; i++) {
    var s = all[i];
    if (s.b > t) break;
    if (t < s.end(inst)[0]) out.push([s, s.pos(fr, t - s.b)]);
  }
  return out;
}
// [[i, x, y, vx, vy]] for the ki shots in flight this tick (ki barrage
// only).  laser/strikefx.py live_points.
function livePoints(inst, ps) {
  if (L_().style(inst.fx.params) !== "ki_barrage") return [];
  var fr = new Fr(inst, ps);
  return live(inst, ps).map(function (e) {
    var s = e[0], p = e[1], k = inst.age - s.b, q;
    if (k >= 1) { q = s.pos(fr, k - 1); return [s.i, p[0], p[1], p[0] - q[0], p[1] - q[1]]; }
    q = s.pos(fr, 1); return [s.i, p[0], p[1], q[0] - p[0], q[1] - p[1]];
  });
}
// Indices of the ki shots in flight this tick: each clashes on its own as a
// sprite.  laser/strikefx.py shot_ids.
function shotIds(inst, ps) {
  if (L_().style(inst.fx.params) !== "ki_barrage" || inst.age >= inst.life) return [];
  return live(inst, ps).map(function (e) { return e[0].i; });
}
// [x, y, vx, vy, radius, ticks left] of ki shot i while it flies, else null.
function shotAt(inst, i, ps) {
  var P = inst.fx.params;
  if (i < 0 || i >= kiCount(P)) return null;
  var s = new Shot(inst, i, ps), e = s.end(inst)[0];
  if (inst.age < s.b || inst.age >= e) return null;
  var fr = new Fr(inst, ps), k = inst.age - s.b, p = s.pos(fr, k), q = s.pos(fr, k + 1);
  return [p[0], p[1], q[0] - p[0], q[1] - p[1], +P.radius * ps * s.size, e - inst.age];
}
function kiHit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var r0 = +inst.fx.params.radius * ps, lv = live(inst, ps);
  for (var i = 0; i < lv.length; i++) {
    var p = lv[i][1];
    if (L_().hyp(p[0] - tx, p[1] - ty) <= hr + r0 * lv[i][0].size) return true;
  }
  return false;
}
function kiOnHit(inst, tx, ty, ps) {   // the shot nearest the target stops there and detonates
  var best = null, bd = null, lv = live(inst, ps);
  for (var i = 0; i < lv.length; i++) {
    var p = lv[i][1], d = L_().hyp(p[0] - tx, p[1] - ty);
    if (bd === null || d < bd) { best = lv[i]; bd = d; }
  }
  if (best) inst.tq_ki[best[0].i] = [inst.age, best[1][0], best[1][1]];
}

// ---------------------------------------------------------------- intercept
// Every orb in flight is its own auto-projectile tracker (fx.intercept):
// pulled off its path by an enemy projectile in range (up to turn_deg a
// tick), it flies a recorded path (inst.tq_kd: [from tick, positions, vx,
// vy, free]) from then on.  laser/strikefx.py track_step.
function trkPut(tr, t, x, y) {   // where a tracked orb is on tick t + 1
  var h = tr[1], n = t + 1 - tr[0];
  while (h.length < n) h.push(h[h.length - 1]);
  h.length = n;
  h.push([x, y]);
}
function trackStep(inst, host) {
  if (!host || L_().style(inst.fx.params) !== "ki_barrage" || inst.age >= inst.life) return;
  var fr = new Fr(inst, inst.ps || 1);
  trackShots(inst, host, live(inst, inst.ps || 1), function (s, k) { return s.pos(fr, k); });
}
// Intercept for a technique's own shots (ki orbs, the charged blast's orb:
// GUNFX.trackStep): lv = [[shot, [x, y]]] in flight, pos(s, k) = shot s k
// ticks after launch.  laser/strikefx.py track_shots.
function trackShots(inst, host, lv, pos) {
  var fx = inst.fx, K = FXK(), L = L_();
  var ic = fx.intercept || {}, on = !!ic.enabled;
  if (!on && !Object.keys(inst.tq_kd).length) return;
  var ps = inst.ps || 1, mode = K.INTERCEPT_MODES.indexOf(ic.mode) >= 0 ? ic.mode : "block";
  var contact = Math.max(0, +ic.contact || 0) * ps, radius = Math.max(0, +ic.radius || 0) * ps;
  var lim = Math.max(0, +ic.turn_deg || 0) * L.D, r0 = +fx.params.radius * ps;
  var cb = host.onIntercept, t = inst.age;
  for (var n = 0; n < lv.length; n++) {
    var s = lv[n][0], x = lv[n][1][0], y = lv[n][1][1], tr = s.trk, vx, vy, kb = K.instKnockback(inst, s.i);
    if (tr) { vx = tr[2]; vy = tr[3]; } else { var p1 = pos(s, t - s.b + 1); vx = p1[0] - x; vy = p1[1] - y; }
    if (on && !(tr && tr[4])) {
      var hit = K.orbContact(x, y, r0 * s.size, host, contact, mode, kb);
      if (hit) {
        hit.dead = true;
        if (mode === "deflect") {
          var both = ic.deflect_who === "both", dv = K.deflectVels({x: x, y: y, vx: vx, vy: vy}, hit, both);
          if (cb) cb.call(host, inst, hit, "deflect", dv.enemy, !!ic.hurts_owner);
          if (both) {   // knocked away too: flies straight on, tracking no more
            if (!tr) tr = inst.tq_kd[s.i] = [t, [[x, y]], vx, vy, false];
            tr[2] = dv.mine[0]; tr[3] = dv.mine[1]; tr[4] = true;
          }
        } else {
          if (cb) cb.call(host, inst, hit, mode, null, false);
          if (mode === "block") { inst.tq_ki[s.i] = [t, x, y]; continue; }   // both gone: the orb detonates there
          if (mode === "absorb") { K.absorbGrow(inst, s.i); kb = K.instKnockback(inst, s.i); }   // swallowed: this orb grows
        }
      }
      if (!tr || !tr[4]) {
        var tg = K.orbNearest(x, y, host, radius, mode, kb);
        if (tg) {
          var spd = Math.hypot(vx, vy), cur = Math.atan2(vy, vx), da = Math.atan2(tg.y - y, tg.x - x) - cur;
          while (da > Math.PI) da -= 2 * Math.PI;
          while (da < -Math.PI) da += 2 * Math.PI;
          cur += Math.max(-lim, Math.min(lim, da));
          vx = Math.cos(cur) * spd; vy = Math.sin(cur) * spd;
          if (!tr) tr = inst.tq_kd[s.i] = [t, [[x, y]], vx, vy, false];
          tr[2] = vx; tr[3] = vy;
        }
      }
    }
    if (tr) trkPut(tr, t, x + tr[2], y + tr[3]);
  }
}

// ---------------------------------------------------------------- punch
function reach(P, t, Lm) {
  var L = L_(), Ts = L.swing(P), Th = hold(P);
  if (t < Ts) return Lm * L.easeOut3(t / Ts);
  if (t < Ts + Th) return Lm;
  if (t < Ts + Th + PUNCH_RETRACT) return Lm * (1 - L.easeIn3((t - Ts - Th) / PUNCH_RETRACT));
  return 0;
}
function punchHit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life) return false;
  var P = inst.fx.params, l = reach(P, inst.age, +P.length * ps);
  if (l <= 2) return false;
  var b = L_().frame(inst).w(l, 0);
  return FXK().segDist(tx, ty, inst.x, inst.y, b[0], b[1]) <= hr + +P.radius * ps * 1.2;
}
function punchBody(inst, ps) {
  var P = inst.fx.params, l = reach(P, inst.age, +P.length * ps);
  if (l <= 2 || inst.age >= inst.life) return null;
  return [[[inst.x, inst.y], L_().frame(inst).w(l, 0)], +P.radius * ps];
}

// ---------------------------------------------------------------- hit options
function optsOn(P) { return HIT_OPTION_STYLES.indexOf(L_().style(P)) >= 0; }
// Hit-stop (params hitstop / hitstop_ticks): ticks the world freezes when the
// strike lands; 0 = none.
function hitstopTicks(P) {
  if (!optsOn(P) || !P.hitstop) return 0;
  return Math.max(0, Math.trunc(+P.hitstop_ticks || 0));
}
// The strike's hit weight: its hit-stop and screen shake, once per strike
// however often it re-hits.
function freeze(inst, host) {
  if (inst.tq_hs || !host || !optsOn(inst.fx.params)) return;
  inst.tq_hs = true;
  var n = hitstopTicks(inst.fx.params);
  if (n > 0 && host.hitstop) host.hitstop(n);
  H_().shake(inst, host);
}
// The strike just landed: its hit-stop.
function hitFreeze(inst, host) { freeze(inst, host); }
// No opponent (Solo; the Studio with every dummy down): nothing lands, so the
// strike freezes as its whiff bursts at full reach (onTick runs before the age moves on).
function hitstopStep(inst, host) {
  var P = inst.fx.params;
  if (!host || STYLES.indexOf(L_().style(P)) < 0 || !optsOn(P) || !host.solo) return;
  if (!inst.tq_imp.length && inst.age + 1 === L_().swing(P)) freeze(inst, host);
}
// Knockback direction of a landed strike (params kb_dir): aim = the effect's
// aim, tangent = the way the fist / foot moves at contact, custom =
// kb_angle_deg turned from that (clockwise, mirrors with the facing).
function hitDir(inst) {
  var P = inst.fx.params, mode = P.kb_dir || "aim";
  if (!optsOn(P) || (mode !== "tangent" && mode !== "custom")) return inst.dir;
  if (mode === "tangent") return inst.tq_f;
  return FXK().rot(inst.tq_f, (+P.kb_angle_deg || 0) * inst.tq_m);
}

// ---------------------------------------------------------------- public
function hit(inst, tx, ty, hr, ps) {
  return L_().style(inst.fx.params) === "ki_barrage" ? kiHit(inst, tx, ty, hr, ps) : punchHit(inst, tx, ty, hr, ps);
}
// A punch clashes along the arm; ki shots never clash as a blade.
function body(inst, ps) { return L_().style(inst.fx.params) === "ki_barrage" ? null : punchBody(inst, ps); }
function onHit(inst, x, y, ps) {
  var P = inst.fx.params;
  if (L_().style(P) === "ki_barrage") { kiOnHit(inst, x, y, ps); return; }
  // the impact stays where the fist landed
  var l = reach(P, inst.age, +P.length * ps) + +P.radius * ps * 0.8, w = L_().frame(inst).w(l, 0);
  inst.tq_imp.push([inst.age, w[0], w[1]]);
}

// ================================================================ drawing
// Shot i vanished without a blast (absorbed, or split by a clash).
function goneSilent(inst, i) { var h = inst.tq_ki[i]; return !!(h && h[3]); }
function blastAt(inst, s, fr) {
  var e = s.end(inst);
  if (e[1]) { var h = inst.tq_ki[s.i]; return [e[0], h[1], h[2]]; }
  var p = s.pos(fr, s.flight);
  return [e[0], p[0], p[1]];
}
function drawKi(pen, inst, host, ps) {
  var L = L_(), HOT = L.HOT, mix = L.mix, P = inst.fx.params, t = inst.age;
  var cs = L.colours(inst, host), c = cs[0], deep = cs[2];
  var fr = new Fr(inst, ps), r0 = +P.radius * ps, B0 = +P.thickness * ps, dens = +P.density || 1;
  var all = shots(inst, ps), smoke = mix(SMOKE, deep, 0.25), i, j, s;
  // 1: smoke piling up where the shots went off (painted normally, under the light)
  pen.add(false);
  var nPuff = Math.max(0, Math.round(3 * dens));
  for (i = 0; i < all.length; i++) {
    s = all[i];
    if (s.b > t) break;
    var bl = blastAt(inst, s, fr), a = t - bl[0];
    if (a < 0 || a >= KI_SMOKE_LIFE || goneSilent(inst, s.i)) continue;
    var q = a / KI_SMOKE_LIFE, B = B0 * s.size;
    for (j = 0; j < nPuff; j++) {
      var r = L.rngFor(inst.seed, s.i, 60 + j), an = r.uniform(0, Math.PI * 2);
      var dr = r.uniform(0.2, 0.9) * B * L.easeOut3(a / 18), rise = r.uniform(0.3, 0.8) * ps * a;
      var rad = B * r.uniform(0.6, 1) * (0.5 + 0.9 * L.easeOut3(a / 20));
      pen.glow(bl[1] + Math.cos(an) * dr, bl[2] + Math.sin(an) * dr - rise, rad, smoke,
               95 * Math.pow(1 - q, 1.5) * Math.min(1, a / 3), 0.6);
    }
  }
  pen.add(true);
  // 2: the hands glow while the barrage fires
  var last = all.length ? all[all.length - 1].b : 0;
  if (t <= last + 4) {
    var fa = t <= last ? 1 : 1 - (t - last) / 4, fl = 0.8 + 0.2 * Math.sin(t * 2.3);
    [1, -1].forEach(function (side) {
      var h = fr.f.d(0, side * KI_SIDE * ps);
      pen.glow(inst.x + h[0], inst.y + h[1], 16 * ps * fl, c, 150 * fa);
      pen.glow(inst.x + h[0], inst.y + h[1], 6 * ps, HOT, 220 * fa);
    });
  }
  for (i = 0; i < all.length; i++) {
    s = all[i];
    if (s.b > t) break;
    var k = t - s.b, en = s.end(inst), e = en[0], stopped = en[1];
    var tint = mix(c, HOT, 0.3 + s.tint), rs = r0 * s.size;
    // 3: muzzle flash at launch
    if (k < KI_FLASH) {
      var qf = k / KI_FLASH, m = s.pos(fr, 0), u = fr.f.d(Math.cos(s.ang), Math.sin(s.ang));
      pen.glow(m[0], m[1], (10 + 10 * L.easeOut3(qf)) * ps * s.size, c, 220 * (1 - qf));
      pen.glow(m[0], m[1], 6 * ps * s.size, HOT, 255 * (1 - qf));
      L.star(pen, m[0], m[1], u[0], u[1], 16 * ps * s.size * (1 - 0.4 * qf), 7 * ps * s.size, HOT, 230 * (1 - qf), 1.3 * ps);
    }
    // 4: the shot in flight — comet tail, halo, body, white-hot core
    if (t < e) {
      var p = s.pos(fr, k), tp = s.pos(fr, Math.max(0, k - 2.5)), fl2 = 0.88 + 0.12 * Math.sin(t * 1.7 + s.i * 2.1);
      pen.diamond(tp[0], tp[1], p[0], p[1], rs * 0.95, c, 140);
      pen.diamond(tp[0], tp[1], p[0], p[1], rs * 0.4, tint, 200);
      pen.glow(p[0], p[1], rs * 3.4 * fl2, c, 120);
      pen.glow(p[0], p[1], rs * 1.8, tint, 235);
      pen.glow(p[0], p[1], rs * 0.85, HOT, 255, 0.75);
      continue;
    }
    // 5: detonation
    var ad = t - e;
    if (ad >= KI_BLAST_LIFE || goneSilent(inst, s.i)) continue;
    var bp = blastAt(inst, s, fr), x = bp[1], y = bp[2];
    var qd = ad / KI_BLAST_LIFE, ee = L.easeOut3(ad / 8), Bd = B0 * s.size * (stopped ? 1 : 0.85);
    if (ad < 5) pen.glow(x, y, Bd * (0.7 + 0.9 * L.easeOut3(ad / 5)), HOT, 255 * (1 - ad / 5));
    pen.glow(x, y, Bd * (0.9 + 1.0 * ee), c, 210 * (1 - qd), 0.45);
    pen.glow(x, y, Bd * (0.5 + 0.45 * ee), mix(c, HOT, 0.6), 235 * Math.pow(1 - qd, 2));
    if (s.kind >= 1) {
      var rr = Bd * (0.5 + 1.7 * L.easeOut3(qd));
      pen.ring(x, y, rr, rr * (s.kind === 2 ? 0.75 : 1), 0, c, 190 * (1 - qd), 2.4 * ps * (1 - qd) + 0.2);
    }
    var nsp = Math.max(0, Math.round((4 + 5 * (s.kind === 2 ? 1 : 0)) * dens));
    for (j = 0; j < nsp; j++) {
      var rg = L.rngFor(inst.seed, s.i, 80 + j), life = 9 + 9 * rg();
      if (ad >= life) continue;
      var an2 = rg.uniform(0, Math.PI * 2), sp = rg.uniform(2.5, 6.5) * ps, fd = L.dragDist(0.87, ad);
      var sx = x + Math.cos(an2) * sp * fd, sy = y + Math.sin(an2) * sp * fd + 0.08 * ps * ad * ad;
      var dk = Math.pow(0.87, ad), qq = ad / life;
      pen.line(sx, sy, sx - Math.cos(an2) * sp * dk * 1.6, sy - Math.sin(an2) * sp * dk * 1.6, mix(HOT, c, qq), 255 * (1 - qq), 1.4 * ps);
    }
  }
}

// Impact frame (params impact_frame): a white flash crossed by ink focus lines
// converging on the contact point, then the inverse (ink, light lines).
// local = inside impact_frame_r, full = the whole overlay.
function impactFrame(pen, inst, c, ps, x, y, a, sc, salt) {
  var P = inst.fx.params, mode = P.impact_frame || "off";
  if (!optsOn(P) || (mode !== "local" && mode !== "full") || a < 0 || a >= IMPACT_FRAME_TICKS) return;
  var L = L_(), full = mode === "full", R = full ? FULL_FRAME : (+P.impact_frame_r || 0) * ps * sc;
  if (R <= 1) return;
  var lit = a === 0, bg = lit ? L.HOT : INK, fg = lit ? INK : L.mix(c, L.HOT, 0.5);
  pen.add(false);
  if (full) pen.poly([[x - R, y - R], [x + R, y - R], [x + R, y + R], [x - R, y + R]], bg, lit ? 190 : 150);
  else pen.glow(x, y, R, bg, lit ? 235 : 200, 0.7);
  var Rl = full ? 1400 * ps : R, n = full ? 32 : 22;
  for (var j = 0; j < n; j++) {
    var r = L.rngFor(inst.seed, j, 130 + salt), an = (j + r.uniform(-0.4, 0.4)) * Math.PI * 2 / n;
    var r0 = Rl * r.uniform(0.18, 0.45), hw = r.uniform(0.012, 0.03);
    pen.poly([[x + Math.cos(an - hw) * Rl, y + Math.sin(an - hw) * Rl], [x + Math.cos(an + hw) * Rl, y + Math.sin(an + hw) * Rl],
      [x + Math.cos(an) * r0, y + Math.sin(an) * r0]], fg, lit ? 230 : 200);
  }
  pen.add(true);
}
// [age, x, y, size, salt, tick] of every impact on show: where the fist was
// when it landed; a whiff bursts smaller at full reach.
function impacts(inst, P, fr, ps) {
  var t = inst.age;
  if (inst.tq_imp.length) return inst.tq_imp.map(function (h, n) { return [t - h[0], h[1], h[2], 1, 11 * n, h[0]]; });
  var w = fr.w(+P.length * ps + +P.radius * ps * 0.8, 0);
  return [[t - L_().swing(P), w[0], w[1], 0.55, 0, L_().swing(P)]];
}
// The punch for the motion partition (HITFX.Motion): shoulder -> fist.
function punchMotion(inst, P, fr, ps) {
  var L = +P.length * ps, Ts = L_().swing(P), Th = hold(P), f = inst.tq_f;
  var limb = function (t) { var w = fr.w(reach(P, t, L), 0); return [inst.x, inst.y, w[0], w[1], f[0], f[1]]; };
  var Motion = H_().Motion;
  return new Motion(limb, 0, Ts, Ts, Ts + Th + PUNCH_RETRACT, +P.radius * ps, +P.thickness * ps);
}
// Where the target's feet were on tick b.
function feet(inst, b, ps) {
  var tp = inst.tq_tp[Math.min(Math.max(0, b), inst.tq_tp.length - 1)];
  return +tp[1] + H_().FEET_DROP * ps;
}
function drawPunch(pen, inst, host, ps) {
  var Lb = L_(), H = H_(), P = inst.fx.params, t = inst.age, fr = Lb.frame(inst), c = Lb.colours(inst, host)[0];
  var imps = impacts(inst, P, fr, ps);
  // 0: the impact frame, under everything else
  imps.forEach(function (m) { impactFrame(pen, inst, c, ps, m[1], m[2], m[0], m[3], m[4]); });
  // 1: the surroundings (fx_env): push-off dust under the fighter, a ground wave under the target
  var p0 = inst.tq_path[0];
  H.env(pen, inst, P, c, ps, ["push", t, p0[0], p0[1] + H.FEET_DROP * ps, -inst.tq_m, 0, 0.8, 0]);
  imps.forEach(function (m) { H.env(pen, inst, P, c, ps, ["ground", m[0], m[1], feet(inst, m[5], ps), 0, 0, m[3] * 0.7, m[4]]); });
  // 2: the fist and its motion (fx_motion)
  H.motion(pen, inst, P, t, ps, c, punchMotion(inst, P, fr, ps));
  // 3: the impacts (fx_impact)
  imps.forEach(function (m) { H.impact(pen, inst, P, c, ps, m[1], m[2], m[0], m[3], m[4], inst.tq_f); });
  pen.add(false);
}

function draw(pen, inst, host, ps) {
  if (L_().style(inst.fx.params) === "ki_barrage") drawKi(pen, inst, host, ps);
  else drawPunch(pen, inst, host, ps);
}

G.STRIKEFX = {STYLES: STYLES, HIT_OPTION_STYLES: HIT_OPTION_STYLES, hitDir: hitDir, hitFreeze: hitFreeze, hitstopStep: hitstopStep, freeze: freeze,
                impactFrame: impactFrame, PUNCH_IMPACT_LIFE: PUNCH_IMPACT_LIFE, INK: INK, draw: draw, hit: hit, body: body, onHit: onHit, activeTicks: activeTicks, totalTicks: totalTicks, livePoints: livePoints, trackStep: trackStep,
                shotIds: shotIds, shotAt: shotAt, trackShots: trackShots};
})(window);
