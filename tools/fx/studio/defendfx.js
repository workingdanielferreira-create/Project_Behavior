/* Defender FX — FX Studio's port of laser/defendfx.py: six ATTACHED
 * techniques of the FX Kit "technique" primitive that are the defender doing
 * the work, each with its own mechanics:
 *   aegis_wall        hex-cell energy wall in front, blocks shots, cracks, shatters past df_hp
 *   mirror_kata       crescent blades whirling round the body: deflect / reflect / destroy shots
 *   chain_bastion     spectral chains lash out to catch shots (and enemies, pulling them in)
 *   repulse_nova      charge, then a dome shockwave: knocks enemies straight out, destroys shots
 *   sanctuary_tether  tether + dome of light round a team-mate (Battle only in the game)
 *   lotus_mend        petals stream into a team-mate, a lotus sigil heals it (Battle only)
 * Same timeline, random streams (FXK.rng), geometry and painting order as the
 * game.  Keep the two in step.
 *
 * Studio differences: no world scale (size = the size it was fired at); the
 * ally styles play on a stand-in team-mate behind the fighter (marked by a
 * faint ring); direct-hit damage cuts, healing and the enemy melee / area FX
 * cancel (df_area) are game-only.
 * Builds on swordfx.js (pen, maths, colours): load it after it.
 */
(function (G) {
"use strict";
var FXK = function () { return G.FXK; };
var L_ = function () { return G.SWORDFX.lib; };
var STYLES = ["aegis_wall", "mirror_kata", "chain_bastion", "repulse_nova", "sanctuary_tether", "lotus_mend"];
var ALLY_STYLES = ["sanctuary_tether", "lotus_mend"];
var RESULTS = ["destroy", "deflect", "reflect"];
var PICKS = ["threatened", "lowest_hp", "nearest"];
var HOT = [255, 255, 255], D = Math.PI / 180, TWO_PI = Math.PI * 2;
var FADE = 14, SHATTER = 30, TAIL = 40, IMPACT_LIFE = 22;
var LASH = 4, CHAIN_HOLD = 3, RETRACT = 8, FOE_COOLDOWN = 30, HEAL_EVERY = 12, NOVA_AFTER = 30;
var PREVIEW_ALLY = [-70, 0];
var HEX_HU = 0.358, HEX_HV = 0.1033;
var CELLS = [];
for (var j_ = -6; j_ <= 6; j_++) {
  (Math.abs(j_) % 2 === 0 ? [-0.62, 0, 0.62] : [-0.31, 0.31]).forEach(function (u) { CELLS.push([u, j_ * 0.155]); });
}
var KEYN = 0;

// ---------------------------------------------------------------- params / timeline
function num(P, k, d) { var v = P[k]; if (v === undefined || v === null || v === "") return d; v = +v; return isFinite(v) ? v : d; }
function style(P) { return L_().style(P); }
function rise(P) { return L_().swing(P); }
function hold(P) { return Math.max(0, Math.trunc(num(P, "hold_ticks", 60))); }
function result(P) { return RESULTS.indexOf(P.df_result) >= 0 ? P.df_result : "destroy"; }
function flag(P, k, d) { return P[k] === undefined || P[k] === null ? d : !!P[k]; }
function frac(x) { return x - Math.floor(x); }
function hyp(x, y) { return Math.sqrt(x * x + y * y); }
function activeTicks(P) {
  if (style(P) === "repulse_nova") return rise(P) + Math.max(1, hold(P)) + 2;
  return rise(P) + hold(P);
}
function totalTicks(P) {
  if (style(P) === "repulse_nova") return activeTicks(P) + NOVA_AFTER;
  return activeTicks(P) + FADE + SHATTER + TAIL;
}

// ---------------------------------------------------------------- state
function onSpawn(inst, host) {
  var P = inst.fx.params, st = style(P);
  var df = {end: null, broke: false, imp: [], dmg: 0, chains: [], seen: {}, foes: {}, ally: null, ax: 0, ay: 0,
            sx: inst.x, sy: inst.y, aim: [inst.tq_f[0], inst.tq_f[1]], sc: null, healed: 0, shook: false, skip: false};
  inst.df = df;
  if (ALLY_STYLES.indexOf(st) >= 0) {
    // The Studio has no team-mate: a stand-in behind the fighter.
    df.ally = true;
    var S = size(inst, 1);
    df.ax = inst.x + PREVIEW_ALLY[0] * inst.facing * S; df.ay = inst.y + PREVIEW_ALLY[1] * S;
    inst.x = df.ax; inst.y = df.ay;
  }
}
function size(inst, ps) { return inst.ps || ps || 1; }
function end(inst, broke) {
  var df = inst.df;
  if (df.end === null) { df.end = inst.age; df.broke = !!broke; }
  inst.life = Math.min(inst.life, inst.age);
}
function shotKey(s) {
  var r = s.ref || s;
  if (r.__dfk == null) r.__dfk = ++KEYN;
  return s.round != null ? r.__dfk + ":" + s.round : "" + r.__dfk;
}
function shotDmg(s) {
  var r = s.ref;
  if (r && r.fx && r.fx.battle) return +r.fx.battle.damage || (s.round != null ? 1 : 0);
  return 1;
}
function takes(s, mode) { return !(s.dead || FXK().shotGone(s)) && FXK().orbTakes(s, mode); }
function body(s) { return s.body || [s.x, s.y, s.x, s.y, 0]; }
function catchShot(inst, host, s, res, outV) {
  s.dead = true;
  if (!host.onIntercept) return;
  if (res === "destroy" || !outV) host.onIntercept(inst, s, "block", null, false);
  else host.onIntercept(inst, s, "deflect", outV, flag(inst.fx.params, "df_hurts", true));
}
function wear(inst, dmg) {
  var P = inst.fx.params, df = inst.df;
  df.dmg += Math.max(0, dmg);
  var hp = num(P, "df_hp", 0);
  if (hp > 0 && df.dmg >= hp && df.end === null) end(inst, true);
}
function segSeg(a, b) {
  var rx = a[2] - a[0], ry = a[3] - a[1], sx = b[2] - b[0], sy = b[3] - b[1], den = rx * sy - ry * sx;
  if (Math.abs(den) > 1e-9) {
    var qx = b[0] - a[0], qy = b[1] - a[1], t = (qx * sy - qy * sx) / den, u = (qx * ry - qy * rx) / den;
    if (t >= 0 && t <= 1 && u >= 0 && u <= 1) return 0;
  }
  var sd = FXK().segDist;
  return Math.min(sd(a[0], a[1], b[0], b[1], b[2], b[3]), sd(a[2], a[3], b[0], b[1], b[2], b[3]),
                  sd(b[0], b[1], a[0], a[1], a[2], a[3]), sd(b[2], b[3], a[0], a[1], a[2], a[3]));
}
function hurtsOf(host) { var h = host.hurt; return h ? [[h.x, h.y, h.r, "t"]] : []; }

// ---------------------------------------------------------------- per-tick mechanics
function step(inst, host) {
  var df = inst.df;
  if (!df) return;
  var P = inst.fx.params, st = style(P), t = inst.age;
  if (df.end === null && t >= inst.life) df.end = inst.life;
  if (df.end !== null && t > df.end + FADE + SHATTER) { inst.dead = true; return; }
  if (ALLY_STYLES.indexOf(st) >= 0) allyTrack(inst, host);
  else if (df.end === null) { df.sx = inst.x; df.sy = inst.y; }
  if (df.end !== null) { if (st === "chain_bastion") chainStep(inst, host, false); return; }
  if (st === "aegis_wall") aegisStep(inst, host);
  else if (st === "mirror_kata") mirrorStep(inst, host);
  else if (st === "chain_bastion") chainStep(inst, host, true);
  else if (st === "repulse_nova") novaStep(inst, host);
  else if (st === "sanctuary_tether") sanctStep(inst, host);
  else if (st === "lotus_mend") lotusStep(inst, host);
}
function allyTrack(inst, host) {
  var df = inst.df;
  if (df.end === null) {
    df.sx = inst.x; df.sy = inst.y;
    var S = size(inst, host.pscale || 1);
    df.ax = df.sx + PREVIEW_ALLY[0] * inst.facing * S; df.ay = df.sy + PREVIEW_ALLY[1] * S;
  }
  inst.x = df.ax; inst.y = df.ay;
}

// -- aegis wall
function aimEase(inst, host) {
  var df = inst.df, tx = host.target[0] - inst.x, ty = host.target[1] - inst.y, n = hyp(tx, ty);
  if (n < 1e-6) return;
  var ax = df.aim[0] + (tx / n - df.aim[0]) * 0.35, ay = df.aim[1] + (ty / n - df.aim[1]) * 0.35, m = hyp(ax, ay) || 1;
  df.aim = [ax / m, ay / m];
}
function WallGeo(inst, S) {
  var P = inst.fx.params;
  this.H = Math.max(4, num(P, "radius", 26)) * S;
  this.d0 = num(P, "length", 14) * S;
  this.B = 0.32 * this.H; this.Wd = 0.30 * this.H;
  this.fr = new (L_().Frame)(inst.x, inst.y, inst.df.aim, 1);
}
WallGeo.prototype.local = function (u, v) {
  var c = Math.sqrt(Math.max(0, 1 - v * v));
  return [this.d0 + this.B * (1 - v * v) + u * this.Wd * c, v * this.H];
};
WallGeo.prototype.at = function (u, v) { var l = this.local(u, v); return this.fr.w(l[0], l[1]); };
WallGeo.prototype.uv = function (x, y) {
  var fr = this.fr, dx = x - fr.ox, dy = y - fr.oy, lx = dx * fr.fx + dy * fr.fy, ly = dx * fr.vx + dy * fr.vy;
  var v = Math.max(-0.95, Math.min(0.95, ly / this.H)), c = Math.sqrt(Math.max(0, 1 - v * v));
  var u = (lx - this.d0 - this.B * (1 - v * v)) / Math.max(1e-6, this.Wd * c);
  return [Math.max(-1, Math.min(1, u)), v];
};
WallGeo.prototype.spine = function (n) {
  var out = [];
  for (var i = 0; i <= n; i++) out.push(this.at(0, -0.98 + 1.96 * i / n));
  return out;
};
function aegisStep(inst, host) {
  var df = inst.df, P = inst.fx.params;
  aimEase(inst, host);
  if (inst.age < Math.max(1, Math.floor(rise(P) / 2))) return;
  var S = size(inst, host.pscale || 1), g = new WallGeo(inst, S), sp = g.spine(10), tol = 0.22 * g.H;
  var shots = host.shots || [];
  for (var k = 0; k < shots.length; k++) {
    var s = shots[k];
    if (!takes(s, "block")) continue;
    var b = body(s), path = [s.x, s.y, s.x + s.vx, s.y + s.vy];
    if (b[0] !== b[2] || b[1] !== b[3]) path = b.slice(0, 4);
    var hw = b[4] || 0, hit = null;
    for (var i = 1; i < sp.length; i++) {
      if (segSeg([sp[i - 1][0], sp[i - 1][1], sp[i][0], sp[i][1]], path) - hw <= tol) { hit = i; break; }
    }
    if (hit === null) continue;
    var dmg = shotDmg(s);
    catchShot(inst, host, s, "destroy");
    var uv = g.uv(s.x, s.y);
    df.imp.push([inst.age, uv[0], uv[1], 0]);
    wear(inst, dmg);
    if (df.end !== null) return;
  }
}

// -- mirror kata
function ring(inst, S, t) {
  var P = inst.fx.params, L = L_(), k = L.easeOut3(t / rise(P));
  var R = Math.max(4, num(P, "radius", 28)) * S * (0.4 + 0.6 * k);
  var ph = L.rngFor(inst.seed, 7, 1)() * TWO_PI;
  var tilt = (-14 + 8 * Math.sin(t * 0.05 + ph)) * D * inst.tq_m;
  return [inst.x, inst.y, R, R * 0.58, tilt];
}
function ringMetric(x, y, rg) {
  var dx = x - rg[0], dy = y - rg[1], ca = Math.cos(rg[4]), sa = Math.sin(rg[4]);
  var a = (dx * ca + dy * sa) / rg[2], b = (-dx * sa + dy * ca) / rg[3];
  return Math.sqrt(a * a + b * b);
}
function bladeTheta(inst, i, n, t) {
  var P = inst.fx.params, r = L_().rngFor(inst.seed, i, 31);
  var gap = (i + r.uniform(-0.22, 0.22)) * TWO_PI / Math.max(1, n), p1 = r() * TWO_PI, p2 = r() * TWO_PI;
  var base = num(P, "spin_deg", 19) * D;
  var th = gap + base * t + 0.9 * Math.sin(t * 0.11 + p1) + 0.5 * Math.sin(t * 0.27 + p2);
  return th * inst.tq_m;
}
function mirrorStep(inst, host) {
  var df = inst.df, P = inst.fx.params, S = size(inst, host.pscale || 1), rg = ring(inst, S, inst.age);
  var res = result(P), mode = res === "destroy" ? "block" : "deflect", shots = host.shots || [];
  for (var k = 0; k < shots.length; k++) {
    var s = shots[k];
    if (!takes(s, mode)) continue;
    var m0 = ringMetric(s.x, s.y, rg), m1 = ringMetric(s.x + s.vx, s.y + s.vy, rg);
    if (Math.min(m0, m1) > 1.12) continue;
    var spd = Math.max(6, hyp(s.vx, s.vy)), nx = s.x - rg[0], ny = s.y - rg[1], nl = hyp(nx, ny) || 1;
    nx /= nl; ny /= nl;
    var r = L_().rngFor(inst.seed, df.imp.length, 47), vel, kind;
    if (res === "reflect") {
      var tx = host.target[0] - s.x, ty = host.target[1] - s.y, tl = hyp(tx, ty) || 1;
      vel = [tx / tl * spd, ty / tl * spd]; kind = 2;
    } else if (res === "deflect") {
      var dot = s.vx * nx + s.vy * ny, vx = s.vx - 2 * dot * nx, vy = s.vy - 2 * dot * ny;
      if (vx * nx + vy * ny < 0) { vx = -s.vx; vy = -s.vy; }
      var rv = FXK().rot([vx, vy], r.uniform(-18, 18)), vl = hyp(rv[0], rv[1]) || 1;
      vel = [rv[0] / vl * spd, rv[1] / vl * spd]; kind = 1;
    } else { vel = [nx * spd, ny * spd]; kind = 3; }
    catchShot(inst, host, s, res, vel);
    var vl2 = hyp(vel[0], vel[1]) || 1;
    df.imp.push([inst.age, s.x - rg[0], s.y - rg[1], vel[0] / vl2, vel[1] / vl2, kind]);
  }
}

// -- chain bastion
function sigil(inst, S) { return [inst.x - inst.facing * 10 * S, inst.y - 9 * S]; }
function chainFree(df, t, n) {
  var busy = 0;
  df.chains.forEach(function (c) { if (t - c.t0 < LASH + CHAIN_HOLD + RETRACT) busy++; });
  return busy < n;
}
function chainStep(inst, host, live) {
  var df = inst.df, P = inst.fx.params, t = inst.age, shots = host.shots || [], byKey = {}, L = L_();
  shots.forEach(function (s) { byKey[shotKey(s)] = s; });
  var hurts = hurtsOf(host);
  df.chains.forEach(function (c) {
    var k = t - c.t0;
    if (c.kind === "shot" && !c.done) {
      var s = byKey[c.key];
      if (s && !s.dead && !FXK().shotGone(s)) {
        c.tx = s.x; c.ty = s.y;
        if (k >= LASH && live) {
          var res = result(P), vel = null;
          if (res !== "destroy") {
            var spd = Math.max(6, hyp(s.vx, s.vy)), ox, oy;
            if (res === "reflect") { ox = host.target[0] - s.x; oy = host.target[1] - s.y; }
            else { ox = s.x - inst.x; oy = s.y - inst.y; }
            var ol = hyp(ox, oy) || 1;
            vel = [ox / ol * spd, oy / ol * spd];
          }
          catchShot(inst, host, s, res, vel);
          c.done = true;
          df.imp.push([t, s.x, s.y, 0, 0, 0]);
        }
      } else if (k < LASH) c.done = true;
    } else if (c.kind === "foe" && k <= LASH + CHAIN_HOLD) {
      if (c.fi !== null && c.fi < hurts.length) { c.tx = hurts[c.fi][0]; c.ty = hurts[c.fi][1]; }
    }
  });
  if (!live) return;
  var S = size(inst, host.pscale || 1), reach = num(P, "length", 180) * S, n = Math.max(1, Math.trunc(num(P, "moons", 3)));
  if (t < rise(P)) return;
  var res2 = result(P), mode = res2 === "destroy" ? "block" : "deflect", cand = [];
  shots.forEach(function (s) {
    if (!takes(s, mode)) return;
    var key = shotKey(s);
    if (df.seen[key]) return;
    var d = hyp(s.x - inst.x, s.y - inst.y);
    if (d <= reach) cand.push([d, 0, key, s.x, s.y, null]);
  });
  if (flag(P, "df_enemies", true)) {
    hurts.forEach(function (h, i) {
      if (t - (df.foes[i] == null ? -1e9 : df.foes[i]) < FOE_COOLDOWN) return;
      var d = hyp(h[0] - inst.x, h[1] - inst.y);
      if (d <= reach) cand.push([d, 1, h[3], h[0], h[1], i]);
    });
  }
  cand.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
  for (var q = 0; q < cand.length; q++) {
    if (!chainFree(df, t, n)) break;
    var cd = cand[q], side = L.rngFor(inst.seed, df.chains.length, 53)() < 0.5 ? 1 : -1;
    df.chains.push({t0: t, kind: cd[1] ? "foe" : "shot", key: cd[2], fi: cd[5], tx: cd[3], ty: cd[4], done: false, side: side, n: df.chains.length});
    if (cd[1]) df.foes[cd[5]] = t; else df.seen[cd[2]] = true;
  }
}
function chainCurve(inst, S, c, t) {
  var L = L_(), sg = sigil(inst, S), sx = sg[0], sy = sg[1], k = t - c.t0, e;
  if (k < 0 || k >= LASH + CHAIN_HOLD + RETRACT) return null;
  if (k < LASH) e = L.easeOut3((k + 1) / LASH);
  else if (k < LASH + CHAIN_HOLD) e = 1;
  else e = 1 - L.easeIn3((k - LASH - CHAIN_HOLD + 1) / RETRACT);
  var tx = c.tx, ty = c.ty, dx = tx - sx, dy = ty - sy, dl = hyp(dx, dy) || 1, px = -dy / dl, py = dx / dl;
  var bend = 0.35 * dl * c.side, mx = sx + dx * 0.5 + px * bend, my = sy + dy * 0.5 + py * bend;
  var whip = k < LASH + CHAIN_HOLD ? 0 : (k - LASH - CHAIN_HOLD) / RETRACT, pts = [], N = 18;
  for (var j = 0; j <= N; j++) {
    var u = e * j / N, a = (1 - u) * (1 - u), b = 2 * u * (1 - u);
    var x = a * sx + b * mx + u * u * tx, y = a * sy + b * my + u * u * ty;
    var w = Math.sin(u * 9 - t * 0.9 + c.n) * (2 + 9 * whip) * S * Math.sin(Math.PI * j / N);
    pts.push([x + px * w, y + py * w]);
  }
  return pts;
}
function idleChain(inst, S, i, n, t, kOut) {
  var sg = sigil(inst, S), r = L_().rngFor(inst.seed, i, 61);
  var base = n > 1 ? (-100 - 130 * i / Math.max(1, n - 1) + r.uniform(-14, 14)) : -125;
  var a0 = base * D, ux = Math.cos(a0) * -inst.facing, uy = Math.sin(a0);
  var Ln = (20 + r() * 16) * S * kOut, f = 0.10 + r() * 0.08, ph = r() * TWO_PI, pts = [];
  for (var j = 0; j < 13; j++) {
    var s = j / 12, sw = 0.55 * Math.sin(s * 4.5 - t * f * 1.6 + ph) * s, ca = Math.cos(sw), sa = Math.sin(sw);
    var vx = ux * ca - uy * sa, vy = ux * sa + uy * ca;
    pts.push([sg[0] + vx * s * Ln, sg[1] + vy * s * Ln]);
  }
  return pts;
}

// -- repulse nova
function novaRadius(inst, S, t) {
  var P = inst.fx.params, C = rise(P), E = Math.max(1, hold(P));
  if (t < C) return 0;
  return Math.max(4, num(P, "radius", 120)) * S * L_().easeOut3((t - C + 1) / E);
}
function novaStep(inst, host) {
  var df = inst.df, P = inst.fx.params, C = rise(P), t = inst.age;
  if (t < C) return;
  if (!df.shook) { df.shook = true; if (host.shake) host.shake(6, 12); }
  var S = size(inst, host.pscale || 1), r = novaRadius(inst, S, t);
  (host.shots || []).forEach(function (s) {
    if (!takes(s, "block")) return;
    if (hyp(s.x - inst.x, s.y - inst.y) <= r) { catchShot(inst, host, s, "destroy"); df.imp.push([t, s.x, s.y, 0, 0, 3]); }
  });
}

// -- sanctuary tether
function dome(inst, S) {
  var P = inst.fx.params, R = Math.max(4, num(P, "radius", 24)) * S, gp = num(P, "ground_px", 14) * S;
  return [inst.x, inst.y + gp, R, Math.max(R * 1.3, gp * 2.6)];
}
function domeMetric(x, y, cx, cy, R, Hd) {
  var a = (x - cx) / Math.max(1e-6, R * 1.1), b = (y - cy) / Math.max(1e-6, Hd * 0.55);
  return Math.sqrt(a * a + b * b);
}
function sanctStep(inst, host) {
  var df = inst.df, P = inst.fx.params;
  if (inst.age < Math.max(1, Math.floor(rise(P) / 2))) return;
  var S = size(inst, host.pscale || 1), dm = dome(inst, S), cx = dm[0], gy = dm[1], R = dm[2], Hd = dm[3], cy = gy - Hd * 0.5;
  var shots = host.shots || [];
  for (var k = 0; k < shots.length; k++) {
    var s = shots[k];
    if (!takes(s, "block")) continue;
    if (domeMetric(s.x, s.y, cx, cy, R, Hd) > 1 && domeMetric(s.x + s.vx, s.y + s.vy, cx, cy, R, Hd) > 1) continue;
    var dmg = shotDmg(s);
    catchShot(inst, host, s, "destroy");
    df.imp.push([inst.age, s.x - cx, s.y - gy, 0, 0, 0]);
    wear(inst, dmg);
    if (df.end !== null) return;
  }
}

// -- lotus mend (the heal itself is game-only)
function lotusStep(inst, host) {
  var df = inst.df, P = inst.fx.params, t = inst.age, H = Math.max(1, hold(P));
  if (t < rise(P)) return;
  df.healed += Math.max(0, num(P, "df_heal", 30)) / H;
}

// ---------------------------------------------------------------- hit / body / knockback
function hit(inst, tx, ty, hr, ps) {
  if (inst.age >= inst.life || !inst.df) return false;
  var P = inst.fx.params, st = style(P), S = size(inst, ps), t = inst.age, i;
  if (st === "repulse_nova") {
    var C = rise(P);
    if (t < C) return false;
    var r0 = t > C ? novaRadius(inst, S, t - 1) : 0, r1 = novaRadius(inst, S, t), d = hyp(tx - inst.x, ty - inst.y);
    return r0 - hr - 10 * S <= d && d <= r1 + hr;
  }
  if (st === "chain_bastion") {
    var ch = inst.df.chains;
    for (i = 0; i < ch.length; i++) {
      var c = ch[i], k = t - c.t0;
      if (c.kind !== "foe" || k < LASH - 1 || k > LASH + CHAIN_HOLD) continue;
      var pts = chainCurve(inst, S, c, t);
      if (pts && hyp(pts[pts.length - 1][0] - tx, pts[pts.length - 1][1] - ty) <= hr + 6 * S) return true;
    }
    return false;
  }
  if (st === "aegis_wall") {
    var g = new WallGeo(inst, S), sp = g.spine(10);
    for (i = 1; i < sp.length; i++) if (FXK().segDist(tx, ty, sp[i - 1][0], sp[i - 1][1], sp[i][0], sp[i][1]) <= hr + 0.2 * g.H) return true;
    return false;
  }
  if (st === "mirror_kata") {
    var rg = ring(inst, S, t);
    return Math.abs(ringMetric(tx, ty, rg) - 1) * rg[2] <= hr + 4 * S;
  }
  return false;
}
function bodyOf() { return null; }
function hitDir(inst, x, y) {
  var st = style(inst.fx.params);
  if (x == null || y == null) return inst.dir;
  if (st === "repulse_nova" || st === "chain_bastion") {
    var dx = x - inst.x, dy = y - inst.y, d = hyp(dx, dy);
    if (d < 1e-6) return inst.dir;
    if (st === "chain_bastion" && flag(inst.fx.params, "df_pull", true)) return [-dx / d, -dy / d];
    return [dx / d, dy / d];
  }
  return inst.dir;
}

// ---------------------------------------------------------------- drawing
function cols(inst, host) {
  var L = L_();
  if (inst.fx.color.mode === "palette") { var c = G.SWORDFX.vivid(host.lut); return [c, c, L.mix(c, HOT, 0.5)]; }
  var cp = FXK().colorPair(inst.fx, host.lut);
  return [cp[0], cp[1], L.mix(cp[0], HOT, 0.5)];
}
function fadeK(inst) {
  var df = inst.df;
  if (df.end === null) return 1;
  return Math.max(0, 1 - (inst.age - df.end) / FADE);
}
function flicker(seed, i, t) {
  var r = L_().rngFor(seed, i, 71), f1 = 0.17 + r() * 0.2, f2 = 0.41 + r() * 0.3, p1 = r() * TWO_PI, p2 = r() * TWO_PI;
  return 0.5 + 0.3 * Math.sin(t * f1 + p1) + 0.2 * Math.sin(t * f2 + p2);
}
function draw(pen, inst, host, ps) {
  var df = inst.df;
  if (!df || df.skip) return;
  var st = style(inst.fx.params);
  pen.add(true);
  if (st === "aegis_wall") drawAegis(pen, inst, host, ps);
  else if (st === "mirror_kata") drawMirror(pen, inst, host, ps);
  else if (st === "chain_bastion") drawChain(pen, inst, host, ps);
  else if (st === "repulse_nova") drawNova(pen, inst, host, ps);
  else if (st === "sanctuary_tether") drawSanct(pen, inst, host, ps);
  else if (st === "lotus_mend") drawLotus(pen, inst, host, ps);
  if (ALLY_STYLES.indexOf(st) >= 0 && fadeK(inst) > 0) {   // Studio only: the stand-in team-mate
    var S = size(inst, ps);
    pen.ring(df.ax, df.ay, 10 * S, 26 * S, 0, [200, 200, 210], 60 * fadeK(inst), 1);
  }
}
function shards(pen, inst, ptsFn, n, c, bright, S, t0, ux, uy) {
  var L = L_(), t = inst.age - t0;
  if (t < 0 || t >= SHATTER) return;
  var q = t / SHATTER;
  for (var i = 0; i < n; i++) {
    var r = L.rngFor(inst.seed, i, 83), p0 = ptsFn(i, r), x0 = p0[0], y0 = p0[1];
    var ang = Math.atan2(uy, ux) + r.uniform(-1.3, 1.3), sp = r.uniform(2, 7) * S, fd = L.dragDist(0.9, t);
    var x = x0 + Math.cos(ang) * sp * fd, y = y0 + Math.sin(ang) * sp * fd + 0.5 * 0.25 * S * t * t;
    var rot = r() * TWO_PI + t * r.uniform(-0.4, 0.4), sz = r.uniform(2, 5) * S * (1 - 0.5 * q), pts = [];
    for (var k = 0; k < 3; k++) {
      var m = k === 0 ? 1 : 0.6;
      pts.push([x + Math.cos(rot + k * 2.1) * sz * m, y + Math.sin(rot + k * 2.1) * sz * m]);
    }
    pen.poly(pts, L.mix(bright, c, q), 230 * (1 - q));
    pen.glow(x, y, sz * 1.6, c, 90 * (1 - q));
  }
  if (t < 6) { var p1 = ptsFn(-1, null); pen.glow(p1[0], p1[1], (18 + 26 * t / 6) * S, HOT, 230 * (1 - t / 6)); }
}
function crack(inst, n, u0, v0, t, kLen) {
  var out = [], L = L_();
  for (var b = 0; b < 3; b++) {
    var r = L.rngFor(inst.seed, n * 7 + b, 97), a = r() * TWO_PI, Lc = (0.25 + r() * 0.3) * kLen;
    var pts = [[u0, v0]], u = u0, v = v0;
    for (var s = 0; s < 4; s++) {
      a += r.uniform(-0.8, 0.8);
      u += Math.cos(a) * Lc / 4 * 1.6; v += Math.sin(a) * Lc / 4 * 0.6;
      pts.push([Math.max(-1, Math.min(1, u)), Math.max(-0.97, Math.min(0.97, v))]);
    }
    out.push(pts);
  }
  return out;
}
function drawAegis(pen, inst, host, ps) {
  var L = L_(), df = inst.df, P = inst.fx.params, t = inst.age, S = size(inst, ps), g = new WallGeo(inst, S);
  var cc = cols(inst, host), c1 = cc[0], c2 = cc[1], bright = cc[2], Rz = rise(P), fk = fadeK(inst);
  var hp = num(P, "df_hp", 0), wr = hp > 0 ? Math.min(1, df.dmg / hp) : 0;
  if (df.broke) {
    shards(pen, inst, function (i) { if (i < 0) return g.at(0, 0); var cl = CELLS[i % CELLS.length]; return g.at(cl[0], cl[1]); },
           CELLS.length, c1, bright, S, df.end, g.fr.fx, g.fr.fy);
    return;
  }
  if (fk <= 0) return;
  var mid = g.at(0, 0), riseK = L.easeOut3(t / Rz);
  pen.glow(mid[0], mid[1], g.H * 1.1, c1, 70 * fk * riseK, 0.4);
  CELLS.forEach(function (cl, i) {
    var u = cl[0], v = cl[1], r = L.rngFor(inst.seed, i, 101);
    var delay = (Math.abs(v) * 0.75 + Math.abs(u) * 0.25) * Rz * 0.8 + r() * Rz * 0.4, k = t - delay;
    if (k < 0) return;
    var pop = Math.min(1, k / 3), fl = flicker(inst.seed, i, t);
    var a = (0.30 + 0.35 * fl) * (1 - 0.45 * wr * fl) * fk * pop;
    df.imp.forEach(function (im) {
      var q = t - im[0];
      if (q >= 0 && q < IMPACT_LIFE) {
        var front = q * 0.11, dd = hyp((u - im[1]) * 0.55, v - im[2]);
        if (Math.abs(dd - front) < 0.14) a += 0.9 * (1 - q / IMPACT_LIFE) * fk;
      }
    });
    var flash = Math.max(0, 1 - k / 4), pts = [];
    for (var kk = 0; kk < 6; kk++) pts.push(g.at(u + HEX_HU * Math.cos((30 + 60 * kk) * D) * 0.92, v + HEX_HV * Math.sin((30 + 60 * kk) * D) * 0.92));
    pen.poly(pts, L.mix(c1, c2, 0.5 + 0.5 * Math.sin(v * 3 + t * 0.07)), 90 * Math.min(1.6, a));
    pts.push(pts[0]);
    pen.polyline(pts, L.mix(bright, HOT, flash), 230 * Math.min(1, a + flash), 1.1 * S);
  });
  [1, -1].forEach(function (side) {
    var rim = [];
    for (var j = 0; j <= 16; j++) rim.push(g.at(side, -1 + 2 * j / 16));
    pen.polyline(rim, c1, 140 * fk * riseK, 3.2 * S);
    pen.polyline(rim, HOT, 200 * fk * riseK, 1.0 * S);
  });
  for (var j = 0; j < 3; j++) {
    var r = L.rngFor(inst.seed, j, 113), sp = 0.04 + r() * 0.05, v = -1 + 2 * frac(r() + t * sp);
    var p = g.at(r.uniform(-0.6, 0.6), v * 0.95);
    pen.glow(p[0], p[1], 4.5 * S, bright, 200 * fk);
  }
  df.imp.forEach(function (im, n) {
    var q = t - im[0];
    if (q < 0) return;
    crack(inst, n, im[1], im[2], t, Math.min(1, q / 4)).forEach(function (br) {
      pen.polyline(br.map(function (w) { return g.at(w[0], w[1]); }), HOT, 170 * fk * (0.45 + 0.55 * Math.max(0, 1 - q / 30)), 1.0 * S);
    });
    if (q < IMPACT_LIFE) {
      var f = 1 - q / IMPACT_LIFE, p = g.at(im[1], im[2]);
      pen.glow(p[0], p[1], (9 + 7 * L.easeOut3(q / 6)) * S, bright, 230 * f * fk);
      L.star(pen, p[0], p[1], -g.fr.vx, -g.fr.vy, 12 * S * f, 5 * S * f, HOT, 255 * f, 1.2 * S);
      for (var k = 0; k < 6; k++) {
        var r = L.rngFor(inst.seed, n * 11 + k, 127), a = Math.atan2(-g.fr.fy, -g.fr.fx) + r.uniform(-1.1, 1.1);
        var sp = r.uniform(3, 7) * S, fd = L.dragDist(0.85, q);
        var x = p[0] + Math.cos(a) * sp * fd, y = p[1] + Math.sin(a) * sp * fd + 0.1 * S * q * q;
        pen.line(x, y, x - Math.cos(a) * sp, y - Math.sin(a) * sp, L.mix(HOT, c1, 1 - f), 255 * f, 1.4 * S);
      }
    }
  });
}
function drawMirror(pen, inst, host, ps) {
  var L = L_(), df = inst.df, P = inst.fx.params, t = inst.age, S = size(inst, ps);
  var cc = cols(inst, host), c1 = cc[0], c2 = cc[1], bright = cc[2], fk = fadeK(inst);
  if (fk <= 0) return;
  var rg = ring(inst, S, t), cx = rg[0], cy = rg[1], R = rg[2], ry = rg[3], tilt = rg[4], ca = Math.cos(tilt), sa = Math.sin(tilt);
  function ringPt(th, rr) {
    if (rr === undefined) rr = 1;
    var x = Math.cos(th) * R * rr, y = Math.sin(th) * ry * rr;
    return [cx + x * ca - y * sa, cy + x * sa + y * ca];
  }
  pen.ring(cx, cy, R, ry, tilt, c1, 70 * fk, 1.2 * S);
  if (t < 6) pen.glow(cx, cy, R * (0.6 + 0.08 * t), HOT, 200 * (1 - t / 6));
  var n = Math.max(1, Math.trunc(num(P, "moons", 3))), span = 1.15, W = Math.max(1, num(P, "thickness", 7)) * S;
  for (var i = 0; i < n; i++) {
    var th = bladeTheta(inst, i, n, t), thPrev = bladeTheta(inst, i, n, t - 1), dirn = th >= thPrev ? 1 : -1;
    var depth = Math.sin(th), da = 0.45 + 0.55 * (0.5 + 0.5 * depth);
    [2, 1, 0].forEach(function (gg) {
      var thg = bladeTheta(inst, i, n, t - gg), ag = da * fk * (gg === 0 ? 1 : 0.28 / gg), po = [], pi = [], j;
      for (j = 0; j < 13; j++) {
        var s = j / 12, a = thg - dirn * span * (1 - s);
        var w = W * Math.pow(Math.sin(Math.PI * Math.pow(s, 0.7)), 0.8) * (0.3 + 0.7 * s);
        po.push(ringPt(a, 1 + w / (2 * R))); pi.push(ringPt(a, 1 - w / (2 * R)));
      }
      if (gg === 0) {
        var spine = [];
        for (j = 0; j < 13; j++) spine.push(ringPt(thg - dirn * span * (1 - j / 12), 1));
        pen.polyline(spine, c1, 70 * ag, W * 1.7);
      }
      pen.poly(po.concat(pi.slice().reverse()), L.mix(c2, c1, 0.6), 190 * ag);
      if (gg === 0) pen.polyline(po, HOT, 235 * ag, 1.3 * S);
    });
    var hp = ringPt(th);
    pen.glow(hp[0], hp[1], 6 * S, bright, 210 * da * fk);
    for (var k = 0; k < 3; k++) {
      var r = L.rngFor(inst.seed, i * 5 + k, 139), life = 8 + Math.trunc(r() * 8);
      var b = t - ((t + Math.trunc(r() * life)) % life), q = (t - b) / life, bp = ringPt(bladeTheta(inst, i, n, b), 1 + 0.25 * q);
      pen.glow(bp[0], bp[1], 2.4 * S * (1 - q) + 0.4, bright, 220 * (1 - q) * fk);
    }
  }
  df.imp.forEach(function (im) {
    var q = t - im[0];
    if (q < 0 || q >= IMPACT_LIFE) return;
    var f = 1 - q / IMPACT_LIFE, x = cx + im[1], y = cy + im[2], ux = im[3], uy = im[4], kd = im[5];
    var rr = (5 + 10 * L.easeOut3(q / 8)) * S * (kd === 2 ? 1.4 : 1), rot = Math.atan2(uy, ux) + q * 0.08, col = kd === 2 ? HOT : bright;
    [0, Math.PI].forEach(function (tri) {
      var pts = [];
      for (var k = 0; k < 4; k++) pts.push([x + Math.cos(rot + tri + k * TWO_PI / 3) * rr, y + Math.sin(rot + tri + k * TWO_PI / 3) * rr]);
      pen.polyline(pts, col, 230 * f * fk, 1.3 * S);
    });
    pen.ring(x, y, rr * 1.15, rr * 1.15, 0, c1, 160 * f * fk, 1.0 * S);
    pen.glow(x, y, 9 * S * f + 2, HOT, 255 * f * fk);
    var Ls = (14 + 44 * L.easeOut3(q / 6)) * S;
    pen.line(x, y, x + ux * Ls, y + uy * Ls, bright, 200 * f * fk, 2.4 * S * f + 0.3);
    pen.line(x, y, x + ux * Ls * 0.8, y + uy * Ls * 0.8, HOT, 255 * f * fk, 1.0 * S);
  });
}
function drawLinks(pen, pts, c, bright, S, a, glowTip) {
  if (glowTip === undefined) glowTip = true;
  if (pts.length < 2) return;
  pen.polyline(pts, c, 70 * a, 3 * S);
  var acc = 0, idx = 0, step = 5.5 * S, d;
  for (var j = 1; j < pts.length; j++) {
    var x0 = pts[j - 1][0], y0 = pts[j - 1][1], x1 = pts[j][0], y1 = pts[j][1], sl = hyp(x1 - x0, y1 - y0);
    if (sl < 1e-6) continue;
    var ux = (x1 - x0) / sl, uy = (y1 - y0) / sl;
    d = step - acc;
    while (d <= sl) {
      var x = x0 + ux * d, y = y0 + uy * d;
      if (idx % 2 === 0) pen.ring(x, y, 3.0 * S, 1.6 * S, Math.atan2(uy, ux), bright, 220 * a, 1.0 * S);
      else pen.line(x - ux * 2.2 * S, y - uy * 2.2 * S, x + ux * 2.2 * S, y + uy * 2.2 * S, HOT, 230 * a, 1.2 * S);
      idx++; d += step;
    }
    acc = sl - (d - step);
  }
  if (glowTip) {
    var a0 = pts[pts.length - 2], a1 = pts[pts.length - 1], dx = a1[0] - a0[0], dy = a1[1] - a0[1], dl = hyp(dx, dy) || 1;
    var vx = dx / dl, vy = dy / dl, X = a1[0], Y = a1[1];
    pen.diamond(X - vx * 3 * S, Y - vy * 3 * S, X + vx * 8 * S, Y + vy * 8 * S, 2.8 * S, bright, 240 * a);
    pen.diamond(X - vx * 1.5 * S, Y - vy * 1.5 * S, X + vx * 6.5 * S, Y + vy * 6.5 * S, 1.1 * S, HOT, 255 * a);
    pen.glow(X, Y, 6 * S, c, 160 * a);
  }
}
function drawChain(pen, inst, host, ps) {
  var L = L_(), df = inst.df, P = inst.fx.params, t = inst.age, S = size(inst, ps);
  var cc = cols(inst, host), c1 = cc[0], c2 = cc[1], bright = cc[2], fk = fadeK(inst);
  if (fk <= 0) return;
  var sg = sigil(inst, S), sx = sg[0], sy = sg[1], Rz = rise(P), kOut = L.easeOut3(t / Rz), i, k;
  var rs = 8 * S * (0.4 + 0.6 * kOut);
  pen.glow(sx, sy, rs * 2.2, c1, 110 * fk);
  pen.ring(sx, sy, rs, rs * 0.55, -0.35 * inst.facing, bright, 220 * fk, 1.6 * S);
  for (k = 0; k < 8; k++) {
    var a = k * TWO_PI / 8 + t * 0.06 * inst.facing, x = sx + Math.cos(a) * rs, y = sy + Math.sin(a) * rs * 0.55;
    pen.line(x, y, sx + Math.cos(a) * rs * 1.25, sy + Math.sin(a) * rs * 1.25 * 0.55, HOT, 200 * fk, 1.1 * S);
  }
  var n = Math.max(1, Math.trunc(num(P, "moons", 3))), busy = 0;
  df.chains.forEach(function (c) { if (t - c.t0 < LASH + CHAIN_HOLD + RETRACT) busy++; });
  for (i = 0; i < Math.max(0, n - busy); i++) drawLinks(pen, idleChain(inst, S, i, n, t, kOut), c2, bright, S, 0.85 * fk);
  df.chains.forEach(function (c) {
    var pts = chainCurve(inst, S, c, t);
    if (!pts) return;
    drawLinks(pen, pts, c1, bright, S, fk);
    var kk = t - c.t0;
    if (kk >= LASH - 1 && kk <= LASH + 1) { var tp = pts[pts.length - 1]; pen.glow(tp[0], tp[1], 13 * S, HOT, 220 * fk); }
  });
  df.imp.forEach(function (im, n_) {
    var q = t - im[0];
    if (q < 0 || q >= IMPACT_LIFE) return;
    var f = 1 - q / IMPACT_LIFE, x = im[1], y = im[2], rr = (4 + 14 * L.easeOut3(q / 10)) * S;
    pen.ring(x, y, rr, rr, 0, bright, 200 * f, 1.6 * S * f);
    pen.glow(x, y, 10 * S * f + 2, HOT, 255 * f);
    for (var k2 = 0; k2 < 7; k2++) {
      var r = L.rngFor(inst.seed, n_ * 13 + k2, 149), a2 = r() * TWO_PI, sp = r.uniform(2.5, 6.5) * S, fd = L.dragDist(0.86, q);
      var x2 = x + Math.cos(a2) * sp * fd, y2 = y + Math.sin(a2) * sp * fd + 0.12 * S * q * q;
      pen.line(x2, y2, x2 - Math.cos(a2) * sp * 1.3, y2 - Math.sin(a2) * sp * 1.3, L.mix(HOT, c1, 1 - f), 255 * f, 1.3 * S);
    }
  });
}
function jagRing(inst, cx, cy, rx, ry, t, amp, salt) {
  var r = L_().rngFor(inst.seed, salt, 157), p1 = r() * TWO_PI, p2 = r() * TWO_PI, pts = [];
  for (var j = 0; j <= 40; j++) {
    var a = j / 40 * TWO_PI, w = 1 + amp * (0.6 * Math.sin(a * 5 + t * 0.31 + p1) + 0.4 * Math.sin(a * 11 - t * 0.47 + p2));
    pts.push([cx + Math.cos(a) * rx * w, cy + Math.sin(a) * ry * w]);
  }
  return pts;
}
function drawNova(pen, inst, host, ps) {
  var L = L_(), df = inst.df, P = inst.fx.params, t = inst.age, S = size(inst, ps);
  var cc = cols(inst, host), c1 = cc[0], c2 = cc[1], bright = cc[2], C = rise(P), E = Math.max(1, hold(P));
  var Rn = Math.max(4, num(P, "radius", 120)) * S, gy = inst.y + num(P, "ground_px", 14) * S, cx = inst.x, cy = inst.y, j, k, r, a;
  if (t >= C + E + 2 + NOVA_AFTER) return;
  var kc = t < C ? L.easeOut3(t / C) : 1, after = Math.max(0, (t - C - E) / NOVA_AFTER), ga = (1 - after) * kc;
  var gr = (0.35 + 0.25 * kc) * Rn * 0.5;
  pen.ring(cx, gy, gr, gr * 0.36, 0, c1, 200 * ga, 2 * S);
  pen.ring(cx, gy, gr * 0.72, gr * 0.72 * 0.36, 0, bright, 160 * ga, 1.2 * S);
  for (k = 0; k < 12; k++) {
    a = k * TWO_PI / 12 + t * 0.05;
    pen.line(cx + Math.cos(a) * gr * 0.72, gy + Math.sin(a) * gr * 0.72 * 0.36, cx + Math.cos(a) * gr, gy + Math.sin(a) * gr * 0.36, HOT, 170 * ga, 1 * S);
  }
  for (k = 0; k < 9; k++) {
    r = L.rngFor(inst.seed, k, 163); a = r() * TWO_PI;
    var Lc = (0.35 + 0.5 * r()) * Rn * Math.min(1, kc * 0.6 + (t >= C ? 0.4 : 0)), pts = [[cx, gy]], x = cx, y = gy;
    for (var s = 0; s < 5; s++) { a += r.uniform(-0.5, 0.5); x += Math.cos(a) * Lc / 5; y += Math.sin(a) * Lc / 5 * 0.36; pts.push([x, y]); }
    pen.polyline(pts, L.mix(bright, c1, 0.3), 170 * ga, 1.6 * S);
  }
  if (t < C) {
    for (k = 0; k < 18; k++) {
      r = L.rngFor(inst.seed, k, 167);
      var b = r() * C * 0.7, q = (t - b) / Math.max(1, C - b);
      if (q < 0 || q >= 1) continue;
      a = r() * TWO_PI;
      var d0 = Rn * (0.5 + 0.4 * r()), e = L.easeIn3(q);
      pen.line(cx + Math.cos(a) * d0 * (1 - e), cy + Math.sin(a) * d0 * (1 - e) * 0.7,
               cx + Math.cos(a) * d0 * (1 - e) * 1.18, cy + Math.sin(a) * d0 * (1 - e) * 1.18 * 0.7, bright, 230 * q, 1.6 * S);
    }
    pen.glow(cx, cy, (12 + 18 * kc) * S, c1, 150 * kc);
    pen.glow(cx, cy, (5 + 6 * kc) * S, HOT, 200 * kc);
    return;
  }
  var kb = t - C;
  if (kb < 5) pen.glow(cx, cy, (26 + 40 * kb / 5) * S, HOT, 255 * (1 - kb / 5));
  var r1 = novaRadius(inst, S, Math.min(t, C + E - 1)), e2 = Math.min(1, (t - C + 1) / E), fa = t < C + E ? 1 - e2 * e2 : 0;
  if (r1 > 1 && fa > 0) {
    var shell = jagRing(inst, cx, gy, r1, r1 * 0.38, t, 0.05, 1);
    pen.polyline(shell, c1, 200 * fa, 4 * S);
    pen.polyline(shell, HOT, 230 * fa, 1.4 * S);
    var domePts = [];
    for (j = 0; j <= 20; j++) domePts.push([cx + Math.cos(Math.PI + j / 20 * Math.PI) * r1, gy + Math.sin(Math.PI + j / 20 * Math.PI) * r1 * 0.78]);
    pen.polyline(domePts, bright, 170 * fa, 2.6 * S);
    pen.glow(cx, gy - r1 * 0.3, r1 * 0.9, c1, 70 * fa, 0.55);
    for (j = 0; j < 14; j++) {
      r = L.rngFor(inst.seed, j, 173); a = j * TWO_PI / 14 + r.uniform(-0.2, 0.2);
      var ln = (10 + 18 * r()) * S, x0 = cx + Math.cos(a) * r1, y0 = gy + Math.sin(a) * r1 * 0.38;
      pen.line(x0, y0, x0 + Math.cos(a) * ln, y0 + Math.sin(a) * ln * 0.38, HOT, 210 * fa, 1.4 * S);
    }
  }
  if (t >= C + E - 2) {
    var qa = (t - (C + E - 2)) / (NOVA_AFTER + 4), Rf = novaRadius(inst, S, C + E - 1);
    for (j = 0; j < 16; j++) {
      r = L.rngFor(inst.seed, j, 179); a = j * TWO_PI / 16 + r.uniform(-0.15, 0.15);
      var px = cx + Math.cos(a) * Rf * (1 + 0.15 * qa), py = gy + Math.sin(a) * Rf * 0.38 * (1 + 0.15 * qa);
      pen.glow(px, py - 8 * S * qa, (10 + 14 * qa) * S * (0.7 + 0.6 * r()), L.mix(c2, [200, 200, 200], 0.5), 120 * (1 - qa));
    }
  }
  df.imp.forEach(function (im) {
    var q = t - im[0];
    if (q >= 0 && q < 12) { var f = 1 - q / 12; pen.glow(im[1], im[2], 12 * S * f + 2, HOT, 240 * f); }
  });
}
function drawSanct(pen, inst, host, ps) {
  var L = L_(), df = inst.df, P = inst.fx.params, t = inst.age, S = size(inst, ps);
  var cc = cols(inst, host), c1 = cc[0], c2 = cc[1], bright = cc[2], dm = dome(inst, S), cx = dm[0], gy = dm[1], R = dm[2], Hd = dm[3];
  var Rz = rise(P), j, k;
  if (df.broke) {
    shards(pen, inst, function (i, r) {
      if (i < 0) return [cx, gy - Hd * 0.5];
      var a = Math.PI + r() * Math.PI;
      return [cx + Math.cos(a) * R, gy + Math.sin(a) * Hd];
    }, 22, c1, bright, S, df.end, 0, -1);
    return;
  }
  var fk = fadeK(inst);
  if (fk <= 0) return;
  var kr = L.easeOut3(t / Rz), hp = num(P, "df_hp", 0), wr = hp > 0 ? Math.min(1, df.dmg / hp) : 0;
  var sx = df.sx, sy = df.sy - 5 * S, tx = cx, ty = gy - Hd * 0.62, dx = tx - sx, dy = ty - sy, dl = hyp(dx, dy) || 1;
  var px = -dy / dl, py = dx / dl, reach = Math.min(1, t / Math.max(1, Rz * 0.6));
  [1, -1].forEach(function (strand) {
    var pts = [];
    for (var jj = 0; jj < 25; jj++) {
      var s = jj / 24 * reach, w = strand * 4 * S * Math.sin(s * Math.PI * 5 - t * 0.35) * Math.sin(Math.PI * s);
      pts.push([sx + dx * s + px * w, sy + dy * s + py * w]);
    }
    pen.polyline(pts, c1, 170 * fk, 1.8 * S);
  });
  pen.line(sx, sy, sx + dx * reach, sy + dy * reach, HOT, 200 * fk, 1.1 * S);
  for (k = 0; k < 6; k++) {
    var r = L.rngFor(inst.seed, k, 191), s2 = frac(r() + t * (0.02 + 0.03 * r()));
    if (s2 > reach) continue;
    pen.glow(sx + dx * s2, sy + dy * s2, 4 * S, bright, 230 * fk);
  }
  pen.glow(sx, sy, 7 * S, c1, 150 * fk);
  var hk = Hd * kr, fl = 0.75 + 0.25 * flicker(inst.seed, 3, t) - 0.35 * wr * flicker(inst.seed, 5, t * 2);
  pen.glow(cx, gy - hk * 0.45, Math.max(R, hk * 0.6), c1, 60 * fk * fl, 0.6);
  var shell = [];
  for (j = 0; j <= 24; j++) shell.push([cx + Math.cos(Math.PI + j / 24 * Math.PI) * R, gy + Math.sin(Math.PI + j / 24 * Math.PI) * hk]);
  pen.polyline(shell, c1, 190 * fk * fl, 3.4 * S);
  pen.polyline(shell, HOT, 210 * fk * fl, 1.1 * S);
  for (var m = 0; m < 4; m++) {
    var ph = m * Math.PI / 4 + t * 0.03, cm = Math.cos(ph), mer = [];
    for (j = 0; j <= 16; j++) mer.push([cx + cm * Math.cos(Math.PI + j / 16 * Math.PI) * R, gy + Math.sin(Math.PI + j / 16 * Math.PI) * hk]);
    pen.polyline(mer, bright, 90 * fk * fl * (0.4 + 0.6 * Math.abs(Math.sin(ph))), 1 * S);
  }
  [0.35, 0.7].forEach(function (lat) {
    var yy = gy - hk * lat, rx = R * Math.sqrt(Math.max(0, 1 - lat * lat));
    pen.ring(cx, yy, rx, rx * 0.3, 0, bright, 80 * fk * fl, 1 * S);
  });
  pen.ring(cx, gy, R * 1.05, R * 1.05 * 0.32, 0, c1, 200 * fk, 2.2 * S);
  for (k = 0; k < 10; k++) {
    var a = k * TWO_PI / 10 + t * 0.04, x = cx + Math.cos(a) * R * 1.05, y = gy + Math.sin(a) * R * 1.05 * 0.32;
    pen.diamond(x - 2 * S, y, x + 2 * S, y, 1.4 * S, HOT, 220 * fk);
  }
  if (t < Rz + 6) {
    var q = t / (Rz + 6);
    pen.poly([[cx - R * 0.5 * (1 - q), gy], [cx + R * 0.5 * (1 - q), gy], [cx + 3 * S, gy - Hd * 1.6], [cx - 3 * S, gy - Hd * 1.6]], bright, 150 * (1 - q));
  }
  df.imp.forEach(function (im) {
    var q2 = t - im[0];
    if (q2 < 0 || q2 >= IMPACT_LIFE) return;
    var f = 1 - q2 / IMPACT_LIFE, x2 = cx + im[1], y2 = gy + im[2], rr = (3 + 14 * L.easeOut3(q2 / 10)) * S;
    pen.ring(x2, y2, rr, rr * 0.7, 0, bright, 220 * f * fk, 2 * S * f + 0.3);
    pen.glow(x2, y2, 12 * S * f + 2, HOT, 255 * f * fk);
  });
}
function leaf(pen, x, y, ux, uy, Lp, Wp, c, a) {
  var px = -uy, py = ux;
  pen.poly([[x, y], [x + ux * Lp * 0.33 + px * Wp, y + uy * Lp * 0.33 + py * Wp], [x + ux * Lp, y + uy * Lp],
            [x + ux * Lp * 0.33 - px * Wp, y + uy * Lp * 0.33 - py * Wp]], c, a);
}
function drawLotus(pen, inst, host, ps) {
  var L = L_(), df = inst.df, P = inst.fx.params, t = inst.age, S = size(inst, ps);
  var cc = cols(inst, host), c1 = cc[0], c2 = cc[1], bright = cc[2], fk = fadeK(inst);
  if (fk <= 0) return;
  var Rz = rise(P), H = Math.max(1, hold(P)), Rl = Math.max(4, num(P, "radius", 24)) * S, gp = num(P, "ground_px", 14) * S;
  var cx = inst.x, gy = inst.y + gp, j, k, r;
  [[8, 1, 0, c1], [8, 0.62, Math.PI / 8, c2]].forEach(function (ly, layer) {
    for (var kk = 0; kk < ly[0]; kk++) {
      var rr = L.rngFor(inst.seed, layer * 20 + kk, 197), op = L.easeOut3((t - rr() * Rz * 0.5) / Rz);
      if (op <= 0) continue;
      var a = ly[2] + kk * TWO_PI / ly[0] + t * 0.01, ux = Math.cos(a), uy = Math.sin(a) * 0.4, ul = hyp(ux, uy) || 1;
      var Lp = Rl * ly[1] * op * (1 + 0.06 * Math.sin(t * 0.13 + kk));
      leaf(pen, cx, gy, ux / ul, uy / ul, Lp * ul, Lp * 0.2 * (0.55 + 0.45 * Math.abs(Math.cos(a))), ly[3], 120 * fk * op);
    }
  });
  pen.ring(cx, gy, Rl * 1.08, Rl * 1.08 * 0.4, 0, bright, 170 * fk, 1.4 * S);
  pen.ring(cx, gy, Rl * 0.3, Rl * 0.3 * 0.4, 0, HOT, 200 * fk, 1.2 * S);
  pen.glow(cx, gy, Rl * 0.6, c1, 100 * fk);
  var sx = df.sx, sy = df.sy - 4 * S, tx = cx, ty = inst.y, dx = tx - sx, dy = ty - sy, dl = hyp(dx, dy) || 1;
  var px = -dy / dl, py = dx / dl, liveEnd = df.end === null ? Rz + H : df.end;
  for (j = 0; j < Math.trunc((Rz + H) / 2) + 1; j++) {
    r = L.rngFor(inst.seed, j, 211);
    var b = j * 2 + r() * 2.5, fl = 16 + r() * 10, q = (t - b) / fl;
    if (q < 0 || q >= 1 || b > liveEnd) continue;
    var side = r.uniform(-1, 1) * 0.45 * dl, u = L.easeInOut3(q), a_ = (1 - u) * (1 - u), b_ = 2 * u * (1 - u);
    var mx = sx + dx * 0.5 + px * side, my = sy + dy * 0.5 + py * side - 18 * S;
    var x = a_ * sx + b_ * mx + u * u * tx, y = a_ * sy + b_ * my + u * u * ty;
    var spin = r() * TWO_PI + t * r.uniform(0.15, 0.35), col = L.mix(c2, c1, r()), sz = 0.8 + 0.6 * r();
    leaf(pen, x, y, Math.cos(spin), Math.sin(spin), 9 * S * sz, 2.6 * S * sz, col, 230 * (1 - q * q) * fk);
    pen.glow(x, y, 4.5 * S * sz, bright, 130 * (1 - q) * fk);
  }
  for (k = 0; k < 14; k++) {
    r = L.rngFor(inst.seed, k, 223);
    var per = 22 + Math.trunc(r() * 14), qm = frac((t + r() * per) / per), am = r() * TWO_PI, rm = Rl * 0.8 * r();
    var xm = cx + Math.cos(am) * rm + Math.sin(t * 0.1 + k) * 4 * S, ym = gy + Math.sin(am) * rm * 0.4 - qm * gp * 2.6;
    pen.glow(xm, ym, 3 * S * (1 - qm) + 0.5, bright, 220 * Math.sin(Math.PI * qm) * fk);
  }
  if (t >= Rz) {
    for (var n_ = 0; n_ < Math.trunc((Math.min(t, liveEnd) - Rz) / HEAL_EVERY) + 1; n_++) {
      var bb = Rz + n_ * HEAL_EVERY, qq = (t - bb) / 16;
      if (qq < 0 || qq >= 1) continue;
      var yh = gy - gp * 2.4 * L.easeOut3(qq), rx = Rl * (0.7 - 0.25 * qq);
      pen.ring(cx, yh, rx, rx * 0.3, 0, bright, 220 * (1 - qq) * fk, 2 * S);
      r = L.rngFor(inst.seed, n_, 229);
      var gx = cx + r.uniform(-0.6, 0.6) * Rl, gyy = inst.y - r() * gp, ln = 5 * S * (1 - qq);
      pen.line(gx - ln, gyy, gx + ln, gyy, HOT, 255 * (1 - qq) * fk, 1.6 * S);
      pen.line(gx, gyy - ln, gx, gyy + ln, HOT, 255 * (1 - qq) * fk, 1.6 * S);
    }
  }
}

G.DEFENDFX = {STYLES: STYLES, ALLY_STYLES: ALLY_STYLES, RESULTS: RESULTS, PICKS: PICKS, activeTicks: activeTicks, totalTicks: totalTicks,
              onSpawn: onSpawn, step: step, hit: hit, body: bodyOf, hitDir: hitDir, draw: draw};
})(window);
