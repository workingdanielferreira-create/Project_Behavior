// Summoner preview: a floating window that plays the summons on a small
// arena, so each construct can be watched moving and attacking before it is
// tried in the game.  A canvas port of laser/summoner.py: the same triggers,
// placement, lite movement (movestyle.js Sim), attacks, auras, finishers and
// drawings.  Borrowed / "@summon:<id>" FX are not played here (the stage
// previews those in the summon's FX slot); a small spark marks each time they
// would fire.
//
// It reads the summons live from S.unique.summoner.summons, so editing a
// summon's settings changes the preview straight away.  Shown: the summon
// whose settings are open (S.smPage), plus every summon ticked in the window.
(function (G) {
"use strict";
var TICK_MS = 16, PROJ_SPEED = 8.0;               // laser/config.py
var ARRIVE_TICKS = 36, FADE_TICKS = 30, DIVE_TICKS = 90, IMP_BLAST_PX = 60;
var W = 1600, H = 900, WHITE = [255, 255, 255];
var PASSIVE = ["totem_heal", "totem_shield", "black_ox", "soul_link", "commander", "earthbind",
  "hex_ward", "earthly_star", "liturgy_bell", "grounding"];
var ENEMY_AURAS = ["earthbind", "hex_ward"];
// laser/summoner.py AUTO_MOVE: [pattern, round what, its settings].
var AUTO_MOVE = {
  familiar: ["legacy", "enemy", {}],
  trance_eidolon: ["chase", "enemy", {}],
  soul_link: ["orbit", "owner", {radius_px: 55, lead_deg: 40, direction: "cw"}],
  imp_swarm: ["orbit", "enemy", {radius_px: 170}],
  automaton_queen: ["kite", "enemy", {min_px: 150, max_px: 280}],
  demi_bahamut: ["shadow", "owner", {offset_px: 70, angle_deg: 180, lag_ms: 200}]
};

function ticks(ms) { return Math.max(1, Math.floor(+ms / TICK_MS)); }
function rgbOf(hex) {
  var m = /^#?([0-9a-f]{6})$/i.exec(String(hex || ""));
  if (!m) return [124, 243, 255];
  var n = parseInt(m[1], 16); return [n >> 16 & 255, n >> 8 & 255, n & 255];
}
function thresholds(text) {
  return String(text || "").split(",").map(function (t) { return parseFloat(t); })
    .filter(function (v) { return isFinite(v) && v > 0 && v < 100; }).sort(function (a, b) { return b - a; });
}
function uni(a, b) { return a + (b - a) * Math.random(); }
function hyp(x, y) { return Math.sqrt(x * x + y * y); }
// Seeded rng (the game seeds its lightning so a bolt holds still for a tick).
function seeded(seed) { var s = (Math.floor(seed) * 2654435761) >>> 0 || 1; return function () { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; }; }

// What studio.js shares with the preview (its own state lives in a closure).
var X = {S: null, C: function () { return null; }, inp: null, info: {}, charScale: function () { return 1; }};
function constructName(E) { return E.name || (X.info[E.construct] ? X.info[E.construct][0] : E.construct); }

// ------------------------------------------------------------ state
var SP = {win: null, cv: null, list: null, info: null, running: false, last: 0, acc: 0,
  extra: {}, mode: "battle", tmode: "still", enemyFire: true, enemyDmg: 5, enemyMs: 1200,
  ownerHitMs: 1500, zoom: 1.5, cam: [0, 0, W], drag: null, w: null};

function fresh() {
  SP.w = {t: 0, owner: {x: 520, y: 470, hp: 100, max_hp: 100, landed: 0, entries: {}, echoes: [], flashes: [], speed: 3},
    enemy: {x: 1120, y: 450, fire: 0, hit: 0, slow: 1, out: 1, inn: 1, dmg: 0, stun: 0},
    cons: [], shots: [], sparks: [], rings: [], nums: [], marks: [], ownerHit: 0};
}
function summonList() { var S = X.S; return (S && S.unique && S.unique.summoner && S.unique.summoner.summons) || []; }
function shownIds() {
  var out = {};
  summonList().forEach(function (E) { if (E.id === X.S.smPage || SP.extra[E.id]) out[E.id] = 1; });
  return out;
}
function shown() { var ids = shownIds(); return summonList().filter(function (E) { return ids[E.id]; }); }
function battle() { return SP.mode === "battle"; }

function entry(E) {
  var o = SP.w.owner, es = o.entries[E.id];
  if (!es) { es = o.entries[E.id] = {timer: 0, fired: {}, hits: 0, landed0: o.landed}; }
  return es;
}
function alive(c) { return c.hp > 0 && c.left > 0; }
function mine(kind, sid) {
  return SP.w.cons.filter(function (c) { return alive(c) && (kind == null || c.kind === kind) && (sid == null || c.E.id === sid); });
}
function inside(a, b, r) { var dx = a.x - b.x, dy = a.y - b.y; return dx * dx + dy * dy <= r * r; }
function heal(amount) {
  var o = SP.w.owner; if (amount <= 0 || o.hp <= 0) return 0;
  var b = o.hp; o.hp = Math.min(o.max_hp, o.hp + amount); return o.hp - b;
}
function burst(x, y, rgb, n, lo, hi) {
  for (var i = 0; i < n; i++) { var a = uni(0, 2 * Math.PI), s = uni(lo, hi); SP.w.sparks.push([x, y, Math.cos(a) * s, Math.sin(a) * s, 0, rgb]); }
}
// Where the summon's FX would play (laser/summoner.py _fire).
function fire(E, x, y) { SP.w.marks.push([x, y, 0, rgbOf(E.color)]); }
function num(x, y, v, rgb) { if (v > 0.001) SP.w.nums.push([x, y, 0, Math.round(v * 10) / 10, rgb || [255, 120, 120]]); }

// The enemy as the game sees it: the target in Battle; in Solo the cursor
// (blasts, auras, taunts and drains only show their FX there).
function enemyPt() { return [SP.w.enemy.x, SP.w.enemy.y]; }
function hitEnemy(dmg, rgb, kind) {
  var e = SP.w.enemy, d = dmg * e.inn;
  if (!battle()) return 0;
  e.hit = 10; e.dmg += d; num(e.x, e.y - 22, d, rgb);
  return d;
}

// ------------------------------------------------------------ summoning
function styleOf(E) {
  var m = E.movement || {}, kind = E.construct, pat = m.pattern, tgt = m.target, params = m.params || {};
  if (pat === "none") return {sty: null, owner: false, moves: false};
  if (pat === "auto") {
    var a = AUTO_MOVE[kind];
    if (!a) return {sty: null, owner: false, moves: false};
    if (a[0] === "legacy") return {sty: null, owner: false, moves: true, legacy: true};
    pat = a[0]; tgt = a[1]; params = Object.assign({}, MOVESTYLE.PATTERN_DEFAULTS[a[0]], a[2]);
  }
  var sty = MOVESTYLE.normalize({enabled: true, select: "priority", daze: false, phases: [
    {name: kind, pattern: pat, params: params, modifiers: {wall_avoid: true}}]});
  return {sty: sty, owner: tgt === "owner", moves: true};
}
function place(E, n) {
  var o = SP.w.owner, ep = enemyPt(), dx = ep[0] - o.x, dy = ep[1] - o.y, d = hyp(dx, dy) || 1, ux = dx / d, uy = dy / d;
  var sp = E.spread_px, pl = E.placement, pts = [];
  for (var i = 0; i < n; i++) {
    var off = (i - (n - 1) / 2) * Math.max(30, (E.size_px || 20) * 2.5);
    if (pl === "between") { var cx = (o.x + ep[0]) / 2, cy = (o.y + ep[1]) / 2; pts.push([cx - uy * off, cy + ux * off]); }
    else if (pl === "near_enemy") pts.push([ep[0] - ux * sp - uy * off, ep[1] - uy * sp + ux * off]);
    else if (pl === "random") pts.push([uni(60, W - 60), uni(60, H - 60)]);
    else { var a = n === 1 ? uni(0, 2 * Math.PI) : 2 * Math.PI * i / n + uni(-0.3, 0.3); pts.push([o.x + Math.cos(a) * sp, o.y + Math.sin(a) * sp]); }
  }
  return pts.map(function (p) { return [Math.max(24, Math.min(W - 24, p[0])), Math.max(24, Math.min(H - 24, p[1]))]; });
}
function movementKey(E) { return E.construct + "|" + JSON.stringify(E.movement || {}); }
function summon(E) {
  var w = SP.w, o = w.owner;
  w.cons = w.cons.filter(alive);
  var n = Math.min(E.count, E.max_alive - mine(null, E.id).length);
  if (n <= 0) return;
  var kind = E.construct, rgb = rgbOf(E.color), es = entry(E), power = 1;
  if (kind === "automaton_queen") { power = Math.min(E.max_power_pct, 100 + E.per_hit_pct * Math.max(0, o.landed - es.landed0)) / 100; es.landed0 = o.landed; }
  place(E, n).forEach(function (p) {
    var c = {E: E, kind: kind, x: p[0], y: p[1], hp: Math.max(0.1, +E.construct_hp), max_hp: Math.max(0.1, +E.construct_hp),
      left: ticks(E.life_ms), t: 0, cd: Math.floor(ticks(kind === "familiar" || kind === "trance_eidolon" ? E.bite_ms : E.fire_ms) / 2),
      armed: 0, cycle: 0, aim: 0, links: [], flash: 0, flash_rgb: rgb, power: power, charges: E.charges, dive: 0,
      buff: 1, det: false, fx_cd: 0, facing_left: o.x > p[0], idx: w.cons.length, sim: null, mkey: null};
    setMove(c);
    w.cons.push(c);
    burst(p[0], p[1], rgb, 14, 1, 4.5);
    if (kind === "commander") rally(E);
    if (PASSIVE.indexOf(kind) < 0) fire(E, p[0], p[1]);
  });
}
function setMove(c) {
  var m = styleOf(c.E), spd = o_speed() * ((c.E.movement || {}).speed_pct == null ? 100 : c.E.movement.speed_pct) / 100;
  c.mv = m; c.mkey = movementKey(c.E); c.speed = m.moves ? spd : 0;
  c.sim = m.sty ? new MOVESTYLE.Sim(m.sty, {x: c.x, y: c.y, speed: c.speed, facing_left: c.facing_left, hp: c.hp, max_hp: c.max_hp,
    attacking: false, enemy_melee: true, w: W, h: H}) : null;
}
function o_speed() { var C = X.C(); return C && C.man && C.man.stats ? +C.man.stats.chase_speed || 3 : 3; }
function rally(E) {
  var k = 1 + Math.max(0, E.buff_pct) / 100, ext = E.extend_ms > 0 ? ticks(E.extend_ms) : 0;
  mine().forEach(function (c) {
    if (c.kind === "commander") return;
    c.left += ext; c.max_hp *= k; c.hp = Math.min(c.max_hp, c.hp * k); c.flash = 12; c.flash_rgb = [255, 214, 102];
  });
}

// ------------------------------------------------------------ the summoner
function ownerTick() {
  var w = SP.w;
  shown().forEach(function (E) {
    var es = entry(E);
    if (E.trigger === "timer" && ++es.timer >= ticks(E.every_ms)) { es.timer = 0; summon(E); }
  });
  if (w.owner.echoes.length) echoTick();
  w.owner.flashes = w.owner.flashes.filter(function (f) { return f[3] < f[4]; });
  w.owner.flashes.forEach(function (f) { f[3]++; });
}
// A hit on the summoner (Hit taken button / an enemy shot): Grounding
// Totem, Soul-Linked Familiar, Shield Totem, Hex Ward, then the HP-threshold
// and hits-taken triggers and the Liturgy Bells (laser/summoner.py absorb,
// shield_mult, on_hurt).
function hurtOwner(amount, kind) {
  var w = SP.w, o = w.owner;
  amount *= w.enemy.out;
  if (kind === "projectile" || kind === "fx") {
    var gt = mine("grounding").filter(function (t) { return t.armed <= 0 && inside(o, t, t.E.aura_px); })[0];
    if (gt) {
      gt.armed = ticks(gt.E.rearm_ms); gt.hp = Math.max(0, gt.hp - amount); gt.flash = 14; gt.flash_rgb = WHITE;
      gt.links = [[o.x, o.y]]; gt.cycle = 0; fire(gt.E, gt.x, gt.y); burst(o.x, o.y, rgbOf(gt.E.color), 10, 1.5, 4.5);
      num(gt.x, gt.y - 20, amount, [200, 200, 255]);
      return;
    }
  }
  var sl = mine("soul_link")[0];
  if (sl) {
    var share = amount * Math.max(0, Math.min(100, sl.E.link_pct)) / 100, take = Math.min(share, Math.max(0, sl.hp));
    if (share > 0) { sl.hp -= take; sl.flash = 10; sl.flash_rgb = rgbOf(sl.E.color); num(sl.x, sl.y - 20, take, [200, 200, 255]); amount -= take; }
  }
  var sh = mine("totem_shield").filter(function (t) { return inside(o, t, t.E.aura_px); })[0];
  if (sh) amount *= Math.max(0, 1 - sh.E.shield_pct / 100);
  if (amount <= 0) return;
  o.hp = Math.max(0, o.hp - amount); w.ownerHit = 10; num(o.x, o.y - 26, amount, [255, 90, 90]);
  onHurt();
  if (o.hp <= 0) {   // the preview never ends: a fresh life
    o.hp = o.max_hp; summonList().forEach(function (E) { entry(E).fired = {}; });
  }
}
function onHurt() {
  var o = SP.w.owner, pct = 100 * o.hp / o.max_hp;
  shown().forEach(function (E) {
    var es = entry(E);
    if (E.trigger === "hp_below") thresholds(E.hp_thresholds).forEach(function (th) { if (!es.fired[th] && pct <= th) { es.fired[th] = 1; summon(E); } });
    else if (E.trigger === "hits_taken" && ++es.hits >= E.every_hits) { es.hits = 0; summon(E); }
  });
  var bells = mine("liturgy_bell");
  for (var i = 0; i < bells.length; i++) {
    var b = bells[i];
    if (b.charges > 0 && inside(o, b, b.E.aura_px)) {
      b.charges--; heal(b.E.charge_heal); num(o.x, o.y - 40, b.E.charge_heal, [110, 255, 150]);
      b.flash = 14; b.flash_rgb = [255, 236, 160]; b.links = [[o.x, o.y]]; fire(b.E, b.x, b.y);
      if (b.charges <= 0) b.left = Math.min(b.left, 2);
      break;
    }
  }
}
function onLanded() {
  SP.w.owner.landed++;
  mine("demi_bahamut").forEach(function (c) { c.queue = Math.min(3, (c.queue || 0) + 1); });
}
function setOwnerHp(pct) {
  var o = SP.w.owner, before = o.hp;
  o.hp = Math.max(1, Math.min(100, pct)) / 100 * o.max_hp;
  if (o.hp < before) onHurtThresholdsOnly();
}
function onHurtThresholdsOnly() {
  var o = SP.w.owner, pct = 100 * o.hp / o.max_hp;
  shown().forEach(function (E) {
    var es = entry(E);
    if (E.trigger === "hp_below") thresholds(E.hp_thresholds).forEach(function (th) { if (!es.fired[th] && pct <= th) { es.fired[th] = 1; summon(E); } });
  });
}

// ------------------------------------------------------------ constructs
function shoot(c, tgt, rgb, damage, speedK, style) {
  var E = c.E, spd = PROJ_SPEED * E.shot_speed_pct / 100 * (speedK || 1), dx = tgt[0] - c.x, dy = tgt[1] - c.y, d = hyp(dx, dy) || 1;
  SP.w.shots.push({x: c.x, y: c.y, vx: dx / d * spd, vy: dy / d * spd, age: 0, max: E.range_px / Math.max(0.5, spd) + 10,
    rgb: rgb, dmg: damage * c.buff, style: style || "", mine: true, hist: []});
  SP.w.marks.push([c.x, c.y, 0, rgb, "muzzle"]);
  fire(E, c.x, c.y);
}
function strike(c, tgt, rgb, damage) {
  var reach = c.E.size_px + 26, dx = tgt[0] - c.x, dy = tgt[1] - c.y, d = hyp(dx, dy) || 1;
  SP.w.shots.push({x: c.x, y: c.y, vx: dx / d * PROJ_SPEED, vy: dy / d * PROJ_SPEED, age: 0, max: reach / PROJ_SPEED + 4,
    rgb: rgb, dmg: damage * c.buff, style: "strike", mine: true, hist: []});
  burst(c.x, c.y, rgb, 5, 1, 3);
  fire(c.E, c.x, c.y);
}
function blast(c, x, y, r, dmg, rgb, stun, drain, ring) {
  var e = SP.w.enemy, k = c ? c.buff : 1;
  if (ring !== false) SP.w.rings.push([x, y, 0, r, rgb]);
  if (!inside(e, {x: x, y: y}, r)) return;
  if (!battle()) return;          // Solo: the cursor only sees the FX
  if (drain) { var got = hitEnemy(dmg * k, rgb); for (var i = 0; i < 3; i++) SP.w.sparks.push([e.x, e.y, 0, -1.2, 0, rgb]); if (got > 0) { heal(got); num(SP.w.owner.x, SP.w.owner.y - 40, got, [110, 255, 150]); } }
  else { if (dmg > 0) hitEnemy(dmg * k, rgb); if (stun > 0) e.stun = Math.max(e.stun, ticks(stun)); burst(e.x, e.y, rgb, 8, 1, 3.5); }
  if (c) { c.links = [[e.x, e.y]]; c.flash = 10; c.flash_rgb = rgb; }
}
var TICKS = {
  turret: function (c, tgt, rgb) {
    if (tgt && c.cd <= 0 && hyp(tgt[0] - c.x, tgt[1] - c.y) <= c.E.range_px) { c.cd = ticks(c.E.fire_ms); shoot(c, tgt, rgb, c.E.shot_damage); }
  },
  familiar: function (c, tgt, rgb) {
    if (tgt && c.cd <= 0 && hyp(tgt[0] - c.x, tgt[1] - c.y) <= c.E.size_px + 26) { c.cd = ticks(c.E.bite_ms); c.flash = 8; c.flash_rgb = rgb; strike(c, tgt, rgb, c.E.bite_damage); }
  },
  totem_heal: function (c) {
    var o = SP.w.owner;
    if (o.hp > 0 && inside(o, c, c.E.aura_px) && heal(c.E.heal_per_s * TICK_MS / 1000) > 0 && c.t % 12 === 0) {
      burst(o.x, o.y - 10, [110, 255, 150], 2, 0.5, 1.5); c.links = [[o.x, o.y]];
    }
  },
  spirit_link: function (c, tgt, rgb) {
    if (c.cycle < ticks(c.E.link_ms)) return;
    c.cycle = 0;
    var r = c.E.aura_px, o = SP.w.owner, mem = mine().filter(function (m) { return inside(m, c, r); });
    if (o.hp > 0 && inside(o, c, r)) mem.push(o);
    if (mem.length < 2) return;
    var tot = 0, cap = 0; mem.forEach(function (m) { tot += Math.max(0, m.hp); cap += m.max_hp; });
    var frac = tot / (cap || 1);
    mem.forEach(function (m) { m.hp = Math.max(0.01, m.max_hp * frac); });
    c.links = mem.filter(function (m) { return m !== c; }).map(function (m) { return [m.x, m.y]; });
    c.flash = 12; c.flash_rgb = rgb; fire(c.E, c.x, c.y);
  },
  earthly_star: function (c) {
    var o = SP.w.owner;
    if (c.E.detonate_hp_pct > 0 && !c.det && 100 * o.hp / o.max_hp <= c.E.detonate_hp_pct) { c.det = true; c.left = Math.min(c.left, 1); }
  },
  capacitor: function (c, tgt, rgb) {
    if (c.cycle < ticks(c.E.charge_ms)) return;
    c.cycle = 0; c.flash = 16; c.flash_rgb = WHITE;
    blast(c, c.x, c.y, c.E.aura_px, c.E.zap_damage, rgb, c.E.stun_ms);
    burst(c.x, c.y, rgb, 22, 2, 7); fire(c.E, c.x, c.y);
  },
  siphon: function (c, tgt, rgb) {
    if (c.cycle < ticks(c.E.link_ms)) return;
    c.cycle = 0;
    blast(c, c.x, c.y, c.E.aura_px, c.E.drain_per_s * c.E.link_ms / 1000, rgb, 0, true, false);
    fire(c.E, c.x, c.y);
  },
  imp_swarm: function (c, tgt, rgb) {
    var E = c.E;
    if (c.dive > 0) {
      c.dive++;
      if (!tgt) tgt = [c.x + Math.cos(c.aim) * 10, c.y + Math.sin(c.aim) * 10];
      var dx = tgt[0] - c.x, dy = tgt[1] - c.y, d = hyp(dx, dy), sp = Math.max(6, o_speed() * 3.2);
      if (d <= Math.max(18, sp) || c.dive > DIVE_TICKS) {
        c.flash = 0;
        blast(c, c.x, c.y, IMP_BLAST_PX, E.implode_damage, rgb);
        burst(c.x, c.y, [255, 180, 80], 16, 2, 6); fire(E, c.x, c.y);
        c.hp = 0; c.boom = true; return;
      }
      c.aim = Math.atan2(dy, dx); c.x += dx / d * sp; c.y += dy / d * sp; return;
    }
    var idle = mine("imp_swarm", E.id).filter(function (m) { return m.dive <= 0; });
    if (idle.length >= E.implode_at) { idle.forEach(function (m) { m.dive = 1; }); return; }
    TICKS.turret(c, tgt, rgb);
  },
  automaton_queen: function (c, tgt, rgb) {
    if (tgt && c.cd <= 0 && hyp(tgt[0] - c.x, tgt[1] - c.y) <= c.E.range_px) { c.cd = ticks(c.E.fire_ms); shoot(c, tgt, rgb, c.E.shot_damage * c.power); }
  },
  demi_bahamut: function (c, tgt, rgb) {
    if ((c.queue || 0) > 0 && tgt && c.cd <= 0) {
      c.queue--; c.cd = 4; c.links = [tgt]; c.flash = 8; c.flash_rgb = WHITE;
      var spd = PROJ_SPEED * 2.6, dx = tgt[0] - c.x, dy = tgt[1] - c.y, d = hyp(dx, dy) || 1;
      SP.w.shots.push({x: c.x, y: c.y, vx: dx / d * spd, vy: dy / d * spd, age: 0, max: d / spd + 12, rgb: rgb,
        dmg: c.E.echo_damage * c.buff, style: "beam", mine: true, hist: []});
      fire(c.E, c.x, c.y);
    }
  },
  trance_eidolon: function (c, tgt, rgb) {
    if (tgt && c.cd <= 0 && hyp(tgt[0] - c.x, tgt[1] - c.y) <= c.E.size_px + 30) {
      c.cd = ticks(c.E.bite_ms); c.flash = 10; c.flash_rgb = WHITE;
      SP.w.owner.flashes.push([c.x, c.y, c.aim, 0, 12, rgb, true]);
      strike(c, tgt, rgb, c.E.bite_damage);
    }
  }
};
function constructTick(c) {
  var E = c.E, rgb = rgbOf(E.color);
  if (c.cd > 0) c.cd--;
  if (c.armed > 0) c.armed--;
  c.cycle++;
  var tgt = enemyPt();
  if (c.dive <= 0) { c.aim = Math.atan2(tgt[1] - c.y, tgt[0] - c.x); c.facing_left = tgt[0] < c.x; }
  if (c.t % 4 === 0) c.links = [];
  if (TICKS[c.kind]) TICKS[c.kind](c, tgt, rgb);
  if (PASSIVE.indexOf(c.kind) >= 0 && --c.fx_cd <= 0) { c.fx_cd = ticks(Math.max(100, E.fx_every_ms)); fire(E, c.x, c.y); }
}
function moveTick(c) {
  if (c.mkey !== movementKey(c.E)) setMove(c);
  if (c.dive > 0 || !c.mv.moves) return;
  var e = SP.w.enemy, o = SP.w.owner, auto = 60 * X.charScale();
  if (c.sim) {
    var f = c.sim.fig; f.x = c.x; f.y = c.y; f.hp = c.hp; f.max_hp = c.max_hp; f.speed = c.speed;
    var cx = c.mv.owner ? o.x : e.x, cy = c.mv.owner ? o.y : e.y;
    c.sim.tick(cx, cy, auto);
    c.x = f.x; c.y = f.y;
  } else if (c.mv.legacy) {   // the old familiar chase: straight at the enemy
    var dx = e.x - c.x, dy = e.y - c.y, d = hyp(dx, dy), stop = c.E.size_px + 14;
    if (d > stop) { var v = Math.min(c.speed, d - stop); c.x += dx / d * v; c.y += dy / d * v; }
  }
}
function onGone(c, expired) {
  var E = c.E, rgb = rgbOf(E.color), o = SP.w.owner, tgt = enemyPt();
  if (!expired) { burst(c.x, c.y, rgb, 10, 1, 3.5); return; }
  if (c.kind === "liturgy_bell" && c.charges > 0) {
    heal(E.charge_heal * c.charges); num(o.x, o.y - 40, E.charge_heal * c.charges, [110, 255, 150]);
    SP.w.rings.push([c.x, c.y, 0, E.aura_px, rgb]); fire(E, c.x, c.y);
  } else if (c.kind === "earthly_star") {
    var k = c.t >= ticks(E.mature_ms) ? E.mature_pct / 100 : 1;
    if (inside(o, c, E.aura_px)) { heal(E.star_heal * k); num(o.x, o.y - 40, E.star_heal * k, [110, 255, 150]); }
    blast(c, c.x, c.y, E.aura_px, E.star_damage * k, rgb);
    burst(c.x, c.y, WHITE, Math.floor(18 + 14 * k), 2, 7 * k);
    o.flashes.push([c.x, c.y, 0, 0, 20, rgb, "star", E.aura_px * (k === 1 ? 1 : 1.15)]);
    fire(E, c.x, c.y);
  } else if (c.kind === "automaton_queen" || c.kind === "demi_bahamut") {
    var dmg = E.finisher_damage * (c.kind === "automaton_queen" ? c.power : 1);
    blast(c, tgt[0], tgt[1], E.aura_px, dmg, rgb);
    o.flashes.push([c.x, c.y, Math.atan2(tgt[1] - c.y, tgt[0] - c.x), 0, 24, rgb, "flare", tgt[0], tgt[1], E.aura_px]);
    burst(tgt[0], tgt[1], rgb, 26, 2, 8); fire(E, tgt[0], tgt[1]);
  } else if (c.kind === "trance_eidolon" && E.echo_ms > 0) {
    o.echoes.push([ticks(E.echo_ms), Math.floor(ticks(E.reappear_ms) / 2), E]);
  }
}
function echoTick() {
  var o = SP.w.owner, keep = [];
  o.echoes.forEach(function (e) {
    e[0]--; e[1]--;
    var E = e[2];
    if (e[1] <= 0) {
      e[1] = ticks(E.reappear_ms);
      var tgt = enemyPt(), a = uni(0, 2 * Math.PI), sx = tgt[0] + Math.cos(a) * 46, sy = tgt[1] + Math.sin(a) * 46, rgb = rgbOf(E.color);
      var dx = tgt[0] - sx, dy = tgt[1] - sy, d = hyp(dx, dy) || 1;
      SP.w.shots.push({x: sx, y: sy, vx: dx / d * PROJ_SPEED * 1.5, vy: dy / d * PROJ_SPEED * 1.5, age: 0, max: 12, rgb: rgb,
        dmg: E.bite_damage, style: "strike", mine: true, hist: []});
      o.flashes.push([sx, sy, a + Math.PI, 0, 16, rgb, true]);
      burst(sx, sy, rgb, 8, 1, 3.5); fire(E, sx, sy);
    }
    if (e[0] > 0) keep.push(e);
  });
  o.echoes = keep;
}
// World level: commander buffs, the enemy auras, taunts.
function worldTick() {
  var w = SP.w, e = w.enemy, buff = 1;
  mine("commander").forEach(function (c) { buff = Math.max(buff, 1 + c.E.buff_pct / 100); });
  w.cons.forEach(function (c) { c.buff = c.kind === "commander" ? 1 : buff; });
  e.slow = e.out = e.inn = 1;
  mine().forEach(function (a) {
    if (ENEMY_AURAS.indexOf(a.kind) < 0) return;
    if (!battle() || !inside(e, a, a.E.aura_px)) { a.links = []; return; }
    if (a.kind === "earthbind") e.slow *= Math.max(0.05, 1 - a.E.slow_pct / 100);
    else { e.out *= Math.max(0, 1 - a.E.weaken_pct / 100); e.inn *= 1 + Math.max(0, a.E.expose_pct) / 100; }
    a.links = [[e.x, e.y]];
  });
}
function taunt() {
  if (!battle()) return null;
  var e = SP.w.enemy, best = null;
  mine("black_ox").forEach(function (c) {
    var d = (c.x - e.x) * (c.x - e.x) + (c.y - e.y) * (c.y - e.y);
    if (d <= c.E.taunt_px * c.E.taunt_px && (!best || d < best[0])) best = [d, c];
  });
  return best ? best[1] : null;
}

// ------------------------------------------------------------ one tick
function step() {
  var w = SP.w, e = w.enemy, o = w.owner;
  w.t++;
  // the enemy moves (slowed by an Earthbind Obelisk, held by a stun)
  var a = w.t / 62.5, tx = e.x, ty = e.y, tt = taunt();
  if (SP.tmode === "wander") { tx = 1000 + 420 * Math.sin(a * 0.45) + 120 * Math.sin(a * 1.3); ty = 450 + 230 * Math.sin(a * 0.7); }
  else if (SP.tmode === "circle") { tx = o.x + 330 * Math.cos(a * 0.5); ty = o.y + 230 * Math.sin(a * 0.5); }
  else if (SP.tmode === "charge") { var ch = tt || o; tx = ch.x; ty = ch.y; }
  if (SP.drag !== "enemy" && SP.tmode !== "still" && e.stun <= 0) {
    var dx = tx - e.x, dy = ty - e.y, d = hyp(dx, dy), lim = (SP.tmode === "charge" ? 2.2 : 4) * e.slow;
    if (SP.tmode === "charge" && d < 50) lim = 0;
    if (d > 0.01) { var v = Math.min(lim, d); e.x += dx / d * v; e.y += dy / d * v; }
  }
  if (e.stun > 0) e.stun--;
  if (e.hit > 0) e.hit--;
  if (w.ownerHit > 0) w.ownerHit--;
  // the enemy shoots (Battle): at a taunting Black Ox Effigy, else the summoner
  if (battle() && SP.enemyFire && e.stun <= 0 && ++e.fire >= ticks(SP.enemyMs / e.slow)) {
    e.fire = 0;
    var at = tt || o, ddx = at.x - e.x, ddy = at.y - e.y, dd = hyp(ddx, ddy) || 1;
    w.shots.push({x: e.x, y: e.y, vx: ddx / dd * PROJ_SPEED, vy: ddy / dd * PROJ_SPEED, age: 0, max: 400, rgb: [255, 90, 90],
      dmg: SP.enemyDmg, style: "", mine: false, hist: []});
  }
  // the summoner lands hits (Automaton Queen power, Demi-Bahamut echoes)
  if (SP.ownerHitMs > 0 && w.t % ticks(SP.ownerHitMs) === 0) {
    var ox = e.x - o.x, oy = e.y - o.y, od = hyp(ox, oy) || 1;
    w.shots.push({x: o.x, y: o.y, vx: ox / od * PROJ_SPEED * 1.4, vy: oy / od * PROJ_SPEED * 1.4, age: 0, max: 400, rgb: [63, 176, 234],
      dmg: 0, style: "owner", mine: true, hist: []});
  }
  ownerTick();
  worldTick();
  w.cons.forEach(function (c) {
    if (!alive(c)) return;
    c.t++; c.left--;
    if (c.flash > 0) c.flash--;
    moveTick(c);
    c.x = Math.max(10, Math.min(W - 10, c.x)); c.y = Math.max(10, Math.min(H - 10, c.y));
    constructTick(c);
  });
  var keep = [];
  w.cons.forEach(function (c) {
    if (c.hp > 0 && c.left > 0) keep.push(c);
    else if (!c.boom) onGone(c, c.hp > 0);
  });
  w.cons = keep;
  // shots
  w.shots = w.shots.filter(function (s) {
    s.hist.push([s.x, s.y]); if (s.hist.length > 6) s.hist.shift();
    s.x += s.vx; s.y += s.vy; s.age++;
    if (s.age > s.max || s.x < -20 || s.y < -20 || s.x > W + 20 || s.y > H + 20) return false;
    if (s.mine) {
      if (hyp(s.x - e.x, s.y - e.y) <= 18) {
        if (s.style === "owner") { onLanded(); burst(e.x, e.y, s.rgb, 4, 1, 2.5); return false; }
        hitEnemy(s.dmg, s.rgb); burst(e.x, e.y, s.rgb, 6, 1, 3.5); return false;
      }
      return true;
    }
    var bodies = mine().concat([o]);
    for (var i = 0; i < bodies.length; i++) {
      var b = bodies[i], r = b === o ? 18 : Math.max(10, b.E.size_px);
      if (hyp(s.x - b.x, s.y - b.y) > r) continue;
      burst(s.x, s.y, s.rgb, 6, 1, 3);
      if (b === o) hurtOwner(s.dmg, "projectile");
      else { var dmg = s.dmg * e.out; b.hp -= dmg; b.flash = 8; b.flash_rgb = WHITE; num(b.x, b.y - 20, dmg, [255, 160, 160]); }
      return false;
    }
    return true;
  });
  w.sparks = w.sparks.filter(function (p) { p[0] += p[2]; p[1] += p[3]; p[2] *= 0.92; p[3] *= 0.92; return ++p[4] < 26; });
  w.rings = w.rings.filter(function (r) { return ++r[2] < 18; });
  w.nums = w.nums.filter(function (n) { n[1] -= 0.6; return ++n[2] < 50; });
  w.marks = w.marks.filter(function (m) { return ++m[2] < 14; });
}

// ================================================================ drawing
// laser/summoner.py's drawing, QPainter -> canvas: CompositionMode_Plus is
// "lighter", Qt angles are degrees counter-clockwise (canvas: radians clockwise).
var g = null;
function col(rgb, a) { return "rgba(" + (rgb[0] | 0) + "," + (rgb[1] | 0) + "," + (rgb[2] | 0) + "," + Math.max(0, Math.min(255, a)) / 255 + ")"; }
function mix(a, b, t) { return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]; }
function add() { g.globalCompositeOperation = "lighter"; }
function over() { g.globalCompositeOperation = "source-over"; }
function pen(c, w, cap) { g.strokeStyle = c; g.lineWidth = w; g.lineCap = cap || "butt"; g.lineJoin = "miter"; }
function ell(x, y, rx, ry) { g.beginPath(); g.ellipse(x, y, Math.max(0.01, rx), Math.max(0.01, ry), 0, 0, 2 * Math.PI); }
function line(x0, y0, x1, y1) { g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke(); }
function halo(x, y, r, rgb, a, core) {
  if (r <= 0.5 || a <= 1) return;
  var gr = g.createRadialGradient(x, y, 0, x, y, r);
  gr.addColorStop(0, col(mix(rgb, WHITE, 0.85), a));
  gr.addColorStop(core == null ? 0.18 : core, col(mix(rgb, WHITE, 0.35), a * 0.8));
  gr.addColorStop(0.5, col(rgb, a * 0.35));
  gr.addColorStop(1, col(rgb, 0));
  g.fillStyle = gr; ell(x, y, r, r); g.fill();
}
function sparkle(x, y, r, rgb, a, rot) {
  if (r <= 0.5 || a <= 1) return;
  [[1, 0.16], [1, 0.16], [0.45, 0.1], [0.45, 0.1]].forEach(function (lw, i) {
    var ang = (rot || 0) + (i === 0 ? 0 : i === 1 ? Math.PI / 2 : i === 2 ? Math.PI / 4 : -Math.PI / 4);
    var ca = Math.cos(ang), sa = Math.sin(ang), L = r * lw[0], Wd = r * lw[1];
    g.fillStyle = col(mix(rgb, WHITE, 0.6), a);
    g.beginPath(); g.moveTo(x + ca * L, y + sa * L); g.lineTo(x - sa * Wd, y + ca * Wd); g.lineTo(x - ca * L, y - sa * L); g.lineTo(x + sa * Wd, y - ca * Wd); g.closePath(); g.fill();
  });
  halo(x, y, r * 0.35, rgb, a);
}
function strokeLayers(path, layers) {
  layers.forEach(function (l) { g.strokeStyle = l[1]; g.lineWidth = l[0]; g.lineCap = "round"; g.lineJoin = "round"; path(); g.stroke(); });
}
function bolt(x0, y0, x1, y1, rgb, a, seed, w, jag) {
  w = w || 2; jag = jag == null ? 10 : jag;
  var r = seeded(seed + 7), dx = x1 - x0, dy = y1 - y0, d = hyp(dx, dy) || 1, nx = -dy / d, ny = dx / d, n = Math.max(3, Math.floor(d / 18));
  var pts = [[x0, y0]];
  for (var i = 1; i < n; i++) { var t = i / n, o = (r() * 2 - 1) * jag * Math.sin(Math.PI * t); pts.push([x0 + dx * t + nx * o, y0 + dy * t + ny * o]); }
  pts.push([x1, y1]);
  strokeLayers(function () { g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (var j = 1; j < pts.length; j++) g.lineTo(pts[j][0], pts[j][1]); },
    [[w * 3.2, col(rgb, a * 0.45)], [w * 1.6, col(rgb, a)], [w * 0.6, col(WHITE, a)]]);
}
function wave(x0, y0, x1, y1, rgb, a, phase, w, amp) {
  w = w || 2; amp = amp == null ? 6 : amp;
  var dx = x1 - x0, dy = y1 - y0, d = hyp(dx, dy) || 1, nx = -dy / d, ny = dx / d, n = Math.max(6, Math.floor(d / 10));
  strokeLayers(function () {
    g.beginPath(); g.moveTo(x0, y0);
    for (var i = 1; i <= n; i++) { var t = i / n, o = Math.sin(t * Math.PI * 3 + phase) * amp * Math.sin(Math.PI * t); g.lineTo(x0 + dx * t + nx * o, y0 + dy * t + ny * o); }
  }, [[w * 2.6, col(rgb, a * 0.4)], [w, col(mix(rgb, WHITE, 0.6), a)]]);
}
function beam(x0, y0, x1, y1, rgb, a, w) {
  strokeLayers(function () { g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); },
    [[w * 2.4, col(rgb, a * 0.35)], [w * 1.3, col(rgb, a)], [w * 0.5, col(WHITE, a)]]);
}
function sigil(x, y, R, rgb, a, rot, sides, squash) {
  sides = sides || 6; squash = squash == null ? 0.42 : squash;
  if (a <= 1 || R <= 1) return;
  g.save(); g.translate(x, y); g.scale(1, squash);
  pen(col(rgb, a * 0.55), 3.2); ell(0, 0, R, R); g.stroke();
  pen(col(mix(rgb, WHITE, 0.55), a), 1.3); ell(0, 0, R, R); g.stroke(); ell(0, 0, R * 0.8, R * 0.8); g.stroke();
  for (var i = 0; i < 24; i++) {
    var ang = rot + 2 * Math.PI * i / 24, r0 = R * 0.82, r1 = R * (i % 3 ? 0.97 : 0.9);
    line(Math.cos(ang) * r0, Math.sin(ang) * r0, Math.cos(ang) * r1, Math.sin(ang) * r1);
  }
  var pts = []; for (i = 0; i < sides; i++) { var b = -rot * 1.5 + 2 * Math.PI * i / sides; pts.push([Math.cos(b) * R * 0.78, Math.sin(b) * R * 0.78]); }
  var st = sides >= 5 ? 2 : 1;
  for (i = 0; i < sides; i++) line(pts[i][0], pts[i][1], pts[(i + st) % sides][0], pts[(i + st) % sides][1]);
  g.restore();
}
function pillar(x, y, w, h, rgb, a) {
  if (a <= 1 || w <= 0.5 || h <= 0.5) return;
  [[w, a * 0.55, 0.25], [w * 0.3, a, 0.8]].forEach(function (l) {
    g.save(); g.translate(x, y - h * 0.45); g.scale(l[0] / h, 1);
    var gr = g.createRadialGradient(0, 0, 0, 0, 0, h * 0.55);
    gr.addColorStop(0, col(mix(rgb, WHITE, l[2]), l[1])); gr.addColorStop(0.5, col(rgb, l[1] * 0.45)); gr.addColorStop(1, col(rgb, 0));
    g.fillStyle = gr; ell(0, 0, h * 0.55, h * 0.55); g.fill(); g.restore();
  });
}
function poly(pts, fill, rim, rimW) {
  g.beginPath(); g.moveTo(pts[0][0], pts[0][1]); for (var i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]); g.closePath();
  g.fillStyle = fill; g.fill(); pen(rim, rimW == null ? 1.6 : rimW); g.stroke();
}
function speedlines(x, y, ang, R, rgb, a, seed) {
  var r = seeded(seed + 3), ca = Math.cos(ang), sa = Math.sin(ang);
  for (var i = 0; i < 5; i++) {
    var off = (r() * 2 - 1) * R, L = R * 1.5 + r() * R * 1.7, sx = x - ca * R * 0.8 - sa * off, sy = y - sa * R * 0.8 + ca * off;
    pen(col(mix(rgb, WHITE, 0.5), a * (0.4 + r() * 0.5)), 0.8 + r()); line(sx, sy, sx - ca * L, sy - sa * L);
  }
}
function auraRing(x, y, r, rgb, a, tk, dash) {
  pen(col(rgb, a), 1.4);
  if (dash !== false) { g.setLineDash([5.6, 2.8]); g.lineDashOffset = -tk * 0.4; }
  ell(x, y, r, r); g.stroke(); g.setLineDash([]);
}
function chain(x0, y0, x1, y1, rgb, a) {
  var d = hyp(x1 - x0, y1 - y0) || 1, n = Math.max(2, Math.floor(d / 12)), ang = Math.atan2(y1 - y0, x1 - x0);
  for (var i = 0; i < n; i++) {
    var t = (i + 0.5) / n;
    g.save(); g.translate(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t); g.rotate(ang + (i % 2 ? Math.PI / 2 : 0));
    pen(col(rgb, a), 1.6); ell(0, 0, 5, 2.6); g.stroke(); g.restore();
  }
}
function links(c, x, y, rgb, tk, kind, a) {
  if (!c.links.length) return;
  a = a == null ? 220 : a; add();
  c.links.forEach(function (l, i) {
    if (kind === "bolt") bolt(x, y, l[0], l[1], rgb, a, Math.floor(tk / 2) * 31 + i, 1.6, 9);
    else if (kind === "wave") wave(x, y, l[0], l[1], rgb, a * 0.8, tk * 0.3 + i, 1.6);
    else if (kind === "beam") beam(x, y, l[0], l[1], rgb, a, 3);
    else if (kind === "chain") chain(x, y, l[0], l[1], rgb, a);
  });
  over();
}
function bar(x, y, w, frac, rgb, h) {
  h = h || 2;
  g.fillStyle = "rgba(0,0,0,.47)"; g.fillRect(x - w / 2, y, w, h);
  g.fillStyle = col(rgb, 220); g.fillRect(x - w / 2, y, w * Math.max(0, Math.min(1, frac)), h);
}
function crystal(x, y, R, rgb, tk) {
  var bob = Math.sin(tk * 0.08) * R * 0.15;
  poly([[x, y - R * 1.7 + bob], [x + R * 0.75, y - R * 0.2 + bob], [x, y + R * 1.25 + bob], [x - R * 0.75, y - R * 0.2 + bob]], col(rgb, 210), col(WHITE, 220), 1.5);
  pen(col(WHITE, 170), 1); line(x, y - R * 1.7 + bob, x, y + R * 1.25 + bob);
  add(); sparkle(x - R * 0.25, y - R * 0.9 + bob, R * 0.7, rgb, 150 + 80 * Math.sin(tk * 0.2), tk * 0.02); over();
  return bob;
}
var DRAW = {
  turret: function (c, x, y, R, rgb, tk) {
    add(); halo(x, y, R * 2, rgb, 90); over();
    var hex = []; for (var i = 0; i < 6; i++) { var b = Math.PI / 6 + i * Math.PI / 3; hex.push([x + Math.cos(b) * R * 1.1, y + Math.sin(b) * R * 1.1]); }
    poly(hex, "rgba(18,22,30,.92)", col(rgb, 240), 2);
    var ca = Math.cos(c.aim), sa = Math.sin(c.aim);
    pen(col(mix(rgb, WHITE, 0.3), 245), Math.max(2, R * 0.42)); line(x, y, x + ca * R * 1.7, y + sa * R * 1.7);
    add(); halo(x, y, R * 0.7, rgb, 255);
    if (c.cd > ticks(c.E.fire_ms) - 4) sparkle(x + ca * R * 1.9, y + sa * R * 1.9, R * 1.2, rgb, 230, c.aim);
    over();
  },
  totem_heal: function (c, x, y, R, rgb, tk) { DRAW._totem(c, x, y, R, rgb, tk); },
  totem_shield: function (c, x, y, R, rgb, tk) { DRAW._totem(c, x, y, R, rgb, tk); },
  _totem: function (c, x, y, R, rgb, tk) {
    var pulse = 0.5 + 0.5 * Math.sin(tk * 0.12);
    add(); auraRing(x, y, c.E.aura_px, rgb, 50 + 40 * pulse, tk); halo(x, y, R * 2.4, rgb, 90 + 60 * pulse); over();
    var bob = crystal(x, y, R, rgb, tk);
    pen(col(WHITE, 235), 2);
    if (c.kind === "totem_heal") {
      line(x - R * 0.3, y - R * 0.25 + bob, x + R * 0.3, y - R * 0.25 + bob); line(x, y - R * 0.55 + bob, x, y + R * 0.05 + bob);
      links(c, x, y, [110, 255, 150], tk, "wave");
    } else { g.beginPath(); g.ellipse(x, y - R * 0.25 + bob, R * 0.4, R * 0.4, 0, Math.PI, 2 * Math.PI); g.stroke(); }
  },
  familiar: function (c, x, y, R, rgb, tk) {
    var a = c.aim, bob = Math.sin(tk * 0.3) * 1.5;
    add(); if (c.kind === "familiar" || (c.sim && c.sim.live)) speedlines(x, y + bob, a, R * 0.8, rgb, 120, Math.floor(tk / 3));
    halo(x, y + bob, R * 2, rgb, 120); over();
    var ca = Math.cos(a), sa = Math.sin(a), sw = Math.sin(tk * 0.4) * R * 0.25;
    poly([[x - ca * R * 1.9 - sw * sa, y + bob - sa * R * 1.9 + sw * ca], [x - sa * R * 0.8, y + bob + ca * R * 0.8],
      [x + ca * R * 0.9, y + bob + sa * R * 0.9], [x + sa * R * 0.8, y + bob - ca * R * 0.8]], col(rgb, 225), col(WHITE, 150), 1.2);
    g.fillStyle = col(WHITE, 255);
    [-1, 1].forEach(function (s) { ell(x + Math.cos(a + s * 0.5) * R * 0.45, y + bob + Math.sin(a + s * 0.5) * R * 0.45, R * 0.17, R * 0.22); g.fill(); });
  },
  spirit_link: function (c, x, y, R, rgb, tk) {
    add(); auraRing(x, y, c.E.aura_px, rgb, 60, tk); sigil(x, y + R * 1.1, R * 1.8, rgb, 120, tk * 0.04, 5); halo(x, y, R * 2.2, rgb, 100); over();
    g.fillStyle = "rgba(26,30,40,.92)"; ell(x, y, R * 0.95, R * 1.15); g.fill(); pen(col(rgb, 230), 2); g.stroke();
    pen(col(mix(rgb, WHITE, 0.5), 230), 1.4); ell(x, y, R * 0.45, R * 0.55); g.stroke();
    add(); for (var i = 0; i < 3; i++) { var a = tk * 0.09 + 2 * Math.PI * i / 3; halo(x + Math.cos(a) * R * 1.7, y + Math.sin(a) * R * 0.7, R * 0.55, rgb, 230); } over();
    links(c, x, y, rgb, tk, "wave", 230);
  },
  liturgy_bell: function (c, x, y, R, rgb, tk) {
    var sw = Math.sin(tk * 0.1) * (c.flash > 0 ? 0.35 : 0.08);
    add(); auraRing(x, y, c.E.aura_px, rgb, 55, tk); halo(x, y, R * 2.2, rgb, 110);
    if (c.flash > 0) { var k = c.flash / 14; for (var j = 0; j < 3; j++) { var rr = R * (1.5 + (1 - k) * 4 + j * 0.9); pen(col(mix(rgb, WHITE, 0.6), 200 * k / (j + 1)), 2); ell(x, y, rr, rr * 0.9); g.stroke(); } }
    over();
    g.save(); g.translate(x, y - R * 1.2); g.rotate(sw);
    g.beginPath(); g.moveTo(-R * 0.55, R * 0.45);
    g.bezierCurveTo(-R * 0.55, -R * 0.15, R * 0.55, -R * 0.15, R * 0.55, R * 0.45);
    g.bezierCurveTo(R * 0.6, R * 1.3, R * 0.8, R * 1.7, R * 1.2, R * 2.0);
    g.quadraticCurveTo(0, R * 2.3, -R * 1.2, R * 2.0);
    g.bezierCurveTo(-R * 0.8, R * 1.7, -R * 0.6, R * 1.3, -R * 0.55, R * 0.45);
    g.closePath();
    var gr = g.createLinearGradient(-R, 0, R, 0);
    gr.addColorStop(0, col(mix(rgb, [40, 30, 10], 0.4), 240)); gr.addColorStop(0.45, col(mix(rgb, WHITE, 0.7), 250)); gr.addColorStop(1, col(mix(rgb, [40, 30, 10], 0.5), 240));
    g.fillStyle = gr; g.fill(); pen(col(WHITE, 210), 1.3); g.stroke();
    g.fillStyle = col(WHITE, 240); ell(0, R * 2.2, R * 0.25, R * 0.25); g.fill();
    g.restore();
    var n = Math.min(12, Math.max(1, c.E.charges | 0));
    for (var i = 0; i < n; i++) { var on = i < c.charges; g.fillStyle = on ? col(mix(rgb, WHITE, 0.5), 240) : "rgba(60,60,70,.55)"; ell(x + (i - (n - 1) / 2) * R * 0.55, y + R * 1.25, R * 0.16, R * 0.16); g.fill(); }
    links(c, x, y, [255, 236, 160], tk, "wave");
  },
  earthly_star: function (c, x, y, R, rgb, tk) {
    var grow = Math.min(1, c.t / Math.max(1, ticks(c.E.mature_ms))), mature = grow >= 1;
    add(); sigil(x, y, c.E.aura_px * (0.35 + 0.65 * grow), rgb, 70 + 90 * grow, tk * 0.02, 6, 1); halo(x, y, R * (1.5 + 2 * grow), rgb, 110 + 100 * grow);
    var rot = tk * (0.03 + 0.05 * grow), ro = R * (0.8 + grow), ri = R * (0.35 + 0.4 * grow), pts = [];
    for (var i = 0; i < 12; i++) { var a = rot + Math.PI * i / 6, rr = i % 2 ? ri : ro; pts.push([x + Math.cos(a) * rr, y + Math.sin(a) * rr]); }
    poly(pts, col(mix(rgb, WHITE, 0.4 + 0.5 * grow), 230), col(WHITE, 240), 1.2);
    if (mature) { var tw = 0.75 + 0.25 * Math.sin(tk * 0.5); sparkle(x, y, R * 3 * tw, rgb, 200, 0); sparkle(x, y, R * 1.8 * tw, WHITE, 160, Math.PI / 4); }
    over(); bar(x, y - R * 2.6, 22, grow, mature ? WHITE : rgb);
  },
  grounding: function (c, x, y, R, rgb, tk) {
    var armed = c.armed <= 0;
    add(); auraRing(x, y, c.E.aura_px, rgb, armed ? 45 : 20, tk); halo(x, y - R * 0.6, R * (armed ? 2.2 : 1.4), rgb, armed ? 120 : 60); over();
    pen(col(mix(rgb, [30, 30, 40], 0.5), 240), Math.max(2, R * 0.28)); line(x, y + R * 1.2, x, y - R * 1.9);
    for (var i = 0; i < 3; i++) { var rr = R * (0.55 + i * 0.22); pen(col(mix(rgb, WHITE, 0.4), armed ? 230 : 110), 1.8); ell(x, y - R * (1.3 - i * 0.75), rr, rr * 0.32); g.stroke(); }
    add();
    if (armed) { halo(x, y - R * 2, R * 0.7, rgb, 255); if (tk % 9 < 3) { var a = (tk * 1.7) % (2 * Math.PI); bolt(x, y - R * 2, x + Math.cos(a) * R * 2, y - R * 2 + Math.sin(a) * R * 2, rgb, 200, tk, 1, 5); } }
    over();
    if (c.links.length && c.flash > 0) links(c, x, y - R * 2, rgb, tk, "bolt", 255);
  },
  black_ox: function (c, x, y, R, rgb, tk) {
    var red = [255, 70, 60];
    add();
    for (var j = 0; j < 3; j++) { var k = ((tk + j * 20) % 60) / 60, rr = R * 1.6 + c.E.taunt_px * 0.35 * k; pen(col(red, 160 * (1 - k)), 2.2); ell(x, y, rr, rr * 0.85); g.stroke(); }
    halo(x, y, R * 2.4, rgb, 110); over();
    poly([[x - R * 0.9, y + R * 1.3], [x - R * 0.7, y - R * 0.3], [x, y - R * 0.9], [x + R * 0.7, y - R * 0.3], [x + R * 0.9, y + R * 1.3]], "rgba(30,22,18,.94)", col(rgb, 230), 2);
    [-1, 1].forEach(function (s) {
      pen(col(mix(rgb, WHITE, 0.5), 240), Math.max(2, R * 0.26), "round");
      g.beginPath(); g.moveTo(x + s * R * 0.55, y - R * 0.55); g.bezierCurveTo(x + s * R * 1.6, y - R * 0.6, x + s * R * 1.7, y - R * 1.4, x + s * R * 1.2, y - R * 2); g.stroke();
    });
    add(); [-1, 1].forEach(function (s) { halo(x + s * R * 0.32, y - R * 0.2, R * 0.38, red, 255); }); over();
  },
  soul_link: function (c, x, y, R, rgb, tk) {
    var o = SP.w.owner;
    add(); chain(x, y, o.x, o.y, mix(rgb, WHITE, 0.3), 120 + (c.flash > 0 ? 100 : 0)); over();
    DRAW.familiar(c, x, y, R, rgb, tk);
    add(); sparkle(x, y - R * 1.5, R * 0.9, rgb, 160 + 80 * Math.sin(tk * 0.25), tk * 0.05); over();
  },
  commander: function (c, x, y, R, rgb, tk) {
    var gold = [255, 214, 102];
    add(); sigil(x, y + R * 1.3, R * 2.2, gold, 120, tk * 0.03, 8); halo(x, y - R, R * 2.6, gold, 100); over();
    pen("rgba(220,220,230,.94)", Math.max(2, R * 0.2)); line(x - R * 0.6, y + R * 1.4, x - R * 0.6, y - R * 2.6);
    var pts = [], n = 8, i, t;
    for (i = 0; i <= n; i++) { t = i / n; pts.push([x - R * 0.6 + t * R * 1.7, y - R * 2.5 + Math.sin(tk * 0.2 - t * 3) * R * 0.2 * t]); }
    pts.push([x + R * 0.85, y - R * 1.75 + Math.sin(tk * 0.2 - 3) * R * 0.2]);
    for (i = n; i >= 0; i--) { t = i / n; pts.push([x - R * 0.6 + t * R * 1.7, y - R * 1.15 + Math.sin(tk * 0.2 - t * 3) * R * 0.2 * t]); }
    poly(pts, col(rgb, 230), col(gold, 240), 1.6);
    var ex = x + R * 0.2, ey = y - R * 1.85 + Math.sin(tk * 0.2 - 1.5) * R * 0.1;
    poly([[ex - R * 0.35, ey + R * 0.1], [ex, ey - R * 0.3], [ex + R * 0.35, ey + R * 0.1], [ex, ey - R * 0.05]], col(gold, 240), col(WHITE, 200), 1);
    add(); sparkle(x - R * 0.6, y - R * 2.7, R * 1.1, gold, 230, tk * 0.04); over();
  },
  capacitor: function (c, x, y, R, rgb, tk) {
    var ch = Math.min(1, c.cycle / Math.max(1, ticks(c.E.charge_ms)));
    add(); auraRing(x, y, c.E.aura_px, rgb, 30 + 120 * ch * ch, tk, ch < 0.85); halo(x, y - R * 0.8, R * (1.6 + 1.6 * ch), rgb, 80 + 150 * ch); over();
    poly([[x - R, y + R * 1.2], [x + R, y + R * 1.2], [x + R * 0.6, y + R * 0.7], [x - R * 0.6, y + R * 0.7]], "rgba(24,26,34,.94)", col(rgb, 200), 1.4);
    for (var i = 0; i < 4; i++) { pen(col(mix(rgb, [60, 50, 30], 0.4), 240), 2.2); ell(x, y + R * (0.5 - i * 0.45), R * (0.65 - i * 0.07), R * 0.2); g.stroke(); }
    add(); halo(x, y - R * 1.4, R * (0.6 + 0.4 * ch), rgb, 255);
    var r = seeded(Math.floor(tk / 2) + 11);
    for (i = 0; i < Math.floor(1 + 4 * ch); i++) { var a = r() * 2 * Math.PI, L = R * (1.2 + r() * (1.2 + 2.5 * ch)); bolt(x, y - R * 1.4, x + Math.cos(a) * L, y - R * 1.4 + Math.sin(a) * L, rgb, 220, tk + i, 0.9, 4); }
    over(); links(c, x, y - R * 1.4, rgb, tk, "bolt", 255);
  },
  earthbind: function (c, x, y, R, rgb, tk) {
    add(); sigil(x, y, c.E.aura_px, rgb, 90, tk * 0.015, 4, 1); halo(x, y, R * 2.2, rgb, 100); over();
    poly([[x, y - R * 2.2], [x + R * 0.6, y - R * 0.2], [x + R * 0.45, y + R * 1.3], [x - R * 0.45, y + R * 1.3], [x - R * 0.6, y - R * 0.2]], "rgba(28,24,40,.94)", col(rgb, 230), 1.8);
    add(); for (var i = 0; i < 3; i++) halo(x, y - R * (1.4 - i * 0.7), R * 0.25, rgb, 230 * (0.6 + 0.4 * Math.sin(tk * 0.15 + i))); over();
    links(c, x, y, rgb, tk, "chain", 170);
  },
  hex_ward: function (c, x, y, R, rgb, tk) {
    add(); sigil(x, y, c.E.aura_px, rgb, 80, -tk * 0.02, 5, 1); halo(x, y, R * 2.4, rgb, 110); over();
    g.beginPath(); g.moveTo(x - R * 1.4, y); g.quadraticCurveTo(x, y - R * 1.3, x + R * 1.4, y); g.quadraticCurveTo(x, y + R * 1.3, x - R * 1.4, y);
    g.fillStyle = "rgba(20,10,26,.94)"; g.fill(); pen(col(mix(rgb, WHITE, 0.4), 240), 1.8); g.stroke();
    var px = x + Math.cos(c.aim) * R * 0.35, py = y + Math.sin(c.aim) * R * 0.25;
    add(); halo(px, py, R * 0.75, rgb, 255); over();
    g.fillStyle = "rgba(10,0,10,.98)"; ell(px, py, R * 0.12, R * 0.42); g.fill();
    links(c, x, y, rgb, tk, "wave", 160);
  },
  siphon: function (c, x, y, R, rgb, tk) {
    add(); auraRing(x, y, c.E.aura_px, rgb, 55, -tk); halo(x, y, R * 2.2, rgb, 110); over();
    var bob = Math.sin(tk * 0.09) * R * 0.15;
    poly([[x, y + R * 1.6 + bob], [x + R * 0.8, y - R * 0.4 + bob], [x + R * 0.35, y - R * 1.3 + bob], [x - R * 0.35, y - R * 1.3 + bob], [x - R * 0.8, y - R * 0.4 + bob]],
      col(mix(rgb, [20, 0, 10], 0.35), 235), col(WHITE, 200), 1.4);
    add(); halo(x, y - R * 0.3 + bob, R * 0.7, rgb, 230);
    c.links.forEach(function (l, i) {
      wave(l[0], l[1], x, y, rgb, 170, -tk * 0.4 + i, 1.4, 8);
      for (var j = 0; j < 3; j++) { var t = (tk * 0.04 + j / 3 + i * 0.13) % 1; halo(l[0] + (x - l[0]) * t, l[1] + (y - l[1]) * t, R * 0.35, rgb, 220); }
    });
    over();
  },
  imp_swarm: function (c, x, y, R, rgb, tk) {
    var r = R * 0.75, a = c.aim;
    if (c.dive > 0) { var fire_ = [255, 150, 60]; add(); speedlines(x, y, a, r * 1.4, fire_, 220, tk); halo(x, y, r * 2.6, fire_, 230); halo(x, y, r * 1.2, WHITE, 230); over(); return; }
    var bob = Math.sin(tk * 0.35 + c.idx) * 1.5;
    add(); halo(x, y + bob, r * 2, rgb, 110); over();
    g.fillStyle = col(mix(rgb, [40, 0, 0], 0.35), 240); ell(x, y + bob, r, r * 0.9); g.fill(); pen(col(WHITE, 150), 1); g.stroke();
    [-1, 1].forEach(function (s) {
      poly([[x + s * r * 0.4, y - r * 0.6 + bob], [x + s * r * 0.9, y - r * 1.5 + bob], [x + s * r * 0.75, y - r * 0.45 + bob]], col(WHITE, 220), col(rgb, 200), 0.8);
      var flap = Math.sin(tk * 0.6) * r * 0.4;
      poly([[x + s * r * 0.8, y + bob], [x + s * r * 1.9, y - r * 0.5 + bob - flap], [x + s * r * 1.6, y + r * 0.4 + bob]], col(rgb, 170), col(rgb, 220), 0.8);
    });
    add(); [-1, 1].forEach(function (s) { halo(x + Math.cos(a + s * 0.5) * r * 0.45, y + bob + Math.sin(a + s * 0.5) * r * 0.4, r * 0.28, [255, 230, 120], 255); }); over();
  },
  automaton_queen: function (c, x, y, R, rgb, tk) {
    var pw = Math.max(1, c.power), face = c.facing_left ? -1 : 1;
    add(); halo(x, y, R * (2 + 0.4 * (pw - 1)), rgb, 110); over();
    poly([[x - R * 0.7, y - R * 0.6], [x + R * 0.7, y - R * 0.6], [x + R, y + R * 1.3], [x - R, y + R * 1.3]], "rgba(30,32,44,.94)", col(rgb, 230), 1.8);
    poly([[x - R * 0.5, y - R * 0.6], [x - R * 0.55, y - R * 1.5], [x + R * 0.55, y - R * 1.5], [x + R * 0.5, y - R * 0.6]], "rgba(220,222,232,.96)", col(rgb, 230), 1.4);
    [[-1, 0.5], [0, 0.8], [1, 0.5]].forEach(function (q) {
      poly([[x + q[0] * R * 0.38 - R * 0.14, y - R * 1.5], [x + q[0] * R * 0.38, y - R * (1.5 + q[1])], [x + q[0] * R * 0.38 + R * 0.14, y - R * 1.5]], col([255, 214, 102], 240), col(WHITE, 220), 0.8);
    });
    add(); pen(col(rgb, 255), R * 0.18); line(x - R * 0.35 + face * R * 0.08, y - R * 1.05, x + R * 0.35 + face * R * 0.08, y - R * 1.05);
    halo(x, y + R * 0.2, R * 0.6 * Math.sqrt(pw), rgb, 255); halo(x + Math.cos(c.aim) * R * 1.3, y + Math.sin(c.aim) * R * 1.3, R * 0.5, rgb, 230); over();
  },
  demi_bahamut: function (c, x, y, R, rgb, tk) {
    var flap = Math.sin(tk * 0.18), face = c.facing_left ? -1 : 1;
    add(); halo(x, y, R * 2.8, rgb, 120); over();
    [-1, 1].forEach(function (s) {
      var tipY = y - R * (1.9 + 0.7 * flap);
      poly([[x + s * R * 0.3, y - R * 0.2], [x + s * R * 2.6, tipY], [x + s * R * 2.2, y + R * 0.1], [x + s * R * 1.6, y - R * 0.2], [x + s * R * 1.3, y + R * 0.6]],
        col(mix(rgb, [10, 10, 30], 0.45), 230), col(mix(rgb, WHITE, 0.4), 230), 1.4);
      pen(col(mix(rgb, WHITE, 0.55), 200), 1);
      [[2.2, 0.1], [1.6, -0.2], [1.3, 0.6]].forEach(function (q) { line(x + s * R * 2.6, tipY, x + s * R * q[0], y + R * q[1]); });
    });
    poly([[x - R * 0.45, y + R * 1.2], [x, y - R * 0.6], [x + R * 0.45, y + R * 1.2]], "rgba(26,26,40,.96)", col(rgb, 230), 1.4);
    var hx = x + face * R * 0.35;
    poly([[hx - face * R * 0.3, y - R * 0.5], [hx + face * R * 0.9, y - R * 0.9], [hx - face * R * 0.1, y - R * 1.1]], "rgba(30,30,46,.96)", col(rgb, 230), 1.2);
    add(); halo(x, y + R * 0.2, R * 0.6, rgb, 255); halo(hx + face * R * 0.35, y - R * 0.88, R * 0.2, WHITE, 255); over();
    links(c, x, y, rgb, tk, "beam", 255);
  },
  trance_eidolon: function (c, x, y, R, rgb, tk) {
    var a = c.aim;
    add();
    for (var j = 0; j < 3; j++) { var k = (j + 1) / 4; halo(x - Math.cos(a) * R * 1.2 * (j + 1), y - Math.sin(a) * R * 1.2 * (j + 1), R * (1.6 - 0.3 * j), rgb, 80 * (1 - k)); }
    halo(x, y, R * 2.3, rgb, 130); over();
    var fl = Math.sin(tk * 0.25) * R * 0.3;
    [-1, 1].forEach(function (s) { poly([[x, y - R * 0.3], [x + s * R * 2, y - R * 1.6 - fl], [x + s * R * 1.4, y + R * 0.2]], col(mix(rgb, WHITE, 0.55), 150), col(WHITE, 200), 1); });
    poly([[x, y - R * 1.4], [x + R * 0.55, y], [x, y + R * 1.5], [x - R * 0.55, y]], col(mix(rgb, WHITE, 0.4), 200), col(WHITE, 240), 1.4);
    add(); sparkle(x, y - R * 0.2, R * 1.2, rgb, 230, tk * 0.06); over();
  }
};
function drawConstruct(c) {
  var E = c.E, x = c.x, y = c.y, R = E.size_px, rgb = rgbOf(E.color), tk = c.t, lifeMax = Math.max(1, ticks(E.life_ms));
  g.save();
  var arr = Math.max(0, 1 - tk / ARRIVE_TICKS);
  if (arr > 0) { add(); sigil(x, y + R * 0.9, R * (2.2 + (1 - arr)), rgb, 230 * arr, tk * 0.09); pillar(x, y + R * 0.9, R * 1.6 * arr, R * 4.5 * (0.5 + 0.5 * arr), rgb, 190 * arr * arr); over(); }
  var fade = Math.min(1, c.left / FADE_TICKS), op = Math.min(1, 0.25 + tk / 12) * (fade >= 1 ? 1 : fade * (0.6 + 0.4 * (Math.floor(tk / 3) % 2)));
  g.globalAlpha = Math.max(0.05, op);
  (DRAW[c.kind] || DRAW.turret)(c, x, y, R, rgb, tk);
  g.globalAlpha = 1;
  if (c.buff > 1) { add(); poly([[x - R * 0.5, y - R * 2], [x, y - R * 2.4], [x + R * 0.5, y - R * 2], [x, y - R * 2.2]], col([255, 214, 102], 220), col(WHITE, 200), 1); over(); }
  bar(x, y + R * 1.8, 26, c.hp / c.max_hp, rgb, 2.5);
  pen(col(rgb, 120), 1.2); g.beginPath(); g.arc(x, y, R * 1.35, -Math.PI / 2, -Math.PI / 2 - 2 * Math.PI * Math.max(0, Math.min(1, c.left / lifeMax)), true); g.stroke();
  if (c.flash > 0) {
    var k = c.flash / 14, rr = R * (1.3 + 1.6 * (1 - k));
    add(); halo(x, y, R * (1.6 + 1.2 * (1 - k)), c.flash_rgb, 200 * k); pen(col(WHITE, 230 * k), 2); ell(x, y, rr, rr); g.stroke(); over();
  }
  g.restore();
}
function drawOwnerFlashes() {
  add();
  SP.w.owner.flashes.forEach(function (f) {
    var x = f[0], y = f[1], a = f[2], age = f[3], life = f[4], rgb = f[5], kind = f[6], k = 1 - age / Math.max(1, life);
    if (kind === true) {   // eidolon slash: a crescent cut with speed lines
      var R = 26;
      g.beginPath(); g.ellipse(x, y, R, R, 0, a + 70 * Math.PI / 180, a - 70 * Math.PI / 180, true);
      g.ellipse(x, y, R * 0.7, R * 0.6, 0, a - 70 * Math.PI / 180, a + 70 * Math.PI / 180, false); g.closePath();
      g.fillStyle = col(mix(rgb, WHITE, 0.6), 240 * k); g.fill();
      halo(x, y, R * 1.4, rgb, 180 * k); speedlines(x, y, a, R * 0.6, rgb, 200 * k, Math.floor(x + y));
    } else if (kind === "star") {
      var r = f[7] * (0.4 + 0.6 * (1 - k)); halo(x, y, r, rgb, 230 * k, 0.3); sparkle(x, y, r * 1.1, WHITE, 240 * k, age * 0.05);
    } else if (kind === "flare") {
      beam(x, y, f[7], f[8], rgb, 255 * k, 7 * (0.5 + k)); halo(f[7], f[8], f[9] * (0.5 + 0.7 * (1 - k)), rgb, 255 * k, 0.3); sparkle(f[7], f[8], f[9] * 0.9, WHITE, 230 * k, 0.3);
    }
  });
  over();
}
function drawFigure(x, y, rgb, label, hit, facing) {
  add(); halo(x, y, 30, rgb, hit > 0 ? 200 : 90); over();
  g.fillStyle = col(rgb, 255); ell(x, y, 11, 11); g.fill();
  pen(hit > 0 ? "#fff" : "rgba(255,255,255,.6)", hit > 0 ? 3 : 1.5); g.stroke();
  if (facing != null) { pen("#fff", 2); line(x, y, x + facing * 18, y); }
  g.fillStyle = "rgba(223,228,236,.85)"; g.font = "18px system-ui,sans-serif"; g.textAlign = "center"; g.fillText(label, x, y + 34);
}
function draw() {
  var cv = SP.cv, w = SP.w, cw = cv.clientWidth || 480, chh = Math.round(cw * 9 / 16);
  if (cv.width !== cw || cv.height !== chh) { cv.width = cw; cv.height = chh; }
  g = cv.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0); g.globalCompositeOperation = "source-over"; g.globalAlpha = 1;
  g.fillStyle = "#0b0d11"; g.fillRect(0, 0, cv.width, cv.height);
  // the camera: Zoom x, centred between the summoner and the enemy
  var vw = W / SP.zoom, vh = H / SP.zoom, mx = (SP.w.owner.x + SP.w.enemy.x) / 2, my = (SP.w.owner.y + SP.w.enemy.y) / 2;
  var left = Math.max(0, Math.min(W - vw, mx - vw / 2)), top = Math.max(0, Math.min(H - vh, my - vh / 2));
  if (!SP.drag) SP.cam = [left, top, vw];
  left = SP.cam[0]; top = SP.cam[1];
  var sc = cv.width / SP.cam[2]; g.setTransform(sc, 0, 0, sc, -left * sc, -top * sc);
  g.strokeStyle = "rgba(42,47,58,.8)"; g.lineWidth = 1 / sc;
  for (var gx = 100; gx < W; gx += 100) line(gx, 0, gx, H);
  for (var gy = 100; gy < H; gy += 100) line(0, gy, W, gy);
  var o = w.owner, e = w.enemy;
  // taunt line and stun ring on the enemy
  var tt = taunt();
  if (tt) { g.setLineDash([10, 8]); pen("rgba(255,70,60,.6)", 2); line(e.x, e.y, tt.x, tt.y); g.setLineDash([]); }
  w.cons.forEach(drawConstruct);
  drawOwnerFlashes();
  drawFigure(o.x, o.y, [63, 176, 234], "Summoner", w.ownerHit, null);
  drawFigure(e.x, e.y, battle() ? [255, 107, 107] : [240, 194, 74], battle() ? "Enemy" : "Cursor", e.hit, null);
  if (e.stun > 0) { pen("rgba(255,255,160,.9)", 2); ell(e.x, e.y - 22, 14, 5); g.stroke(); }
  bar(o.x, o.y + 42, 70, o.hp / o.max_hp, [63, 176, 234], 6);
  // shots
  add();
  w.shots.forEach(function (s) {
    if (s.style === "beam") { beam(s.x - s.vx * 3, s.y - s.vy * 3, s.x, s.y, s.rgb, 255, 3); return; }
    if (s.hist.length) { pen(col(s.rgb, 160), s.style === "strike" ? 5 : 3, "round"); g.beginPath(); g.moveTo(s.hist[0][0], s.hist[0][1]); s.hist.forEach(function (p) { g.lineTo(p[0], p[1]); }); g.lineTo(s.x, s.y); g.stroke(); }
    halo(s.x, s.y, s.style === "strike" ? 16 : 10, s.rgb, 255);
  });
  w.sparks.forEach(function (p) { g.fillStyle = col(p[5], 255 * (1 - p[4] / 26)); g.fillRect(p[0] - 1.5, p[1] - 1.5, 3, 3); });
  w.rings.forEach(function (r) { var k = r[2] / 18; pen(col(r[4], 255 * (1 - k)), 3); ell(r[0], r[1], r[3] * (0.3 + 0.7 * k), r[3] * (0.3 + 0.7 * k)); g.stroke(); });
  w.marks.forEach(function (m) {
    var k = m[2] / 14;
    if (m[4] === "muzzle") halo(m[0], m[1], 18 * (1 - k) + 4, m[3], 220 * (1 - k));
    else { pen(col(mix(m[3], WHITE, 0.5), 200 * (1 - k)), 1.5); ell(m[0], m[1], 8 + 20 * k, 8 + 20 * k); g.stroke(); }
  });
  over();
  g.textAlign = "center"; g.font = "bold 20px system-ui,sans-serif";
  w.nums.forEach(function (n) { g.fillStyle = col(n[4], 255 * (1 - n[2] / 50)); g.fillText((n[4][1] > 200 && n[4][0] < 150 ? "+" : "") + n[3], n[0], n[1]); });
  g.setTransform(1, 0, 0, 1, 0, 0);
}

// ------------------------------------------------------------ the window
function loop(now) {
  if (!SP.win || SP.win.hidden) { SP.running = false; SP.last = 0; return; }
  if (!SP.w) fresh();
  SP.acc = Math.min(64, SP.acc + (SP.last ? now - SP.last : 16)); SP.last = now;
  for (; SP.acc >= TICK_MS; SP.acc -= TICK_MS) step();
  // summons that are no longer shown (or were removed) leave the arena
  var ids = shownIds();
  SP.w.cons = SP.w.cons.filter(function (c) { return ids[c.E.id] && summonList().indexOf(c.E) >= 0; });
  draw();
  info();
  requestAnimationFrame(loop);
}
function info() {
  if (!SP.info) return;
  var w = SP.w, list = shown(), parts = list.map(function (E) {
    var n = mine(null, E.id).length, es = entry(E), next = "";
    if (E.trigger === "timer") next = "next in " + Math.max(0, (ticks(E.every_ms) - es.timer) * TICK_MS / 1000).toFixed(1) + " s";
    else if (E.trigger === "hits_taken") next = es.hits + "/" + E.every_hits + " hits";
    else next = "at HP " + thresholds(E.hp_thresholds).filter(function (t) { return !es.fired[t]; }).join(", ") + " %";
    return constructName(E) + ": " + n + "/" + E.max_alive + " out · " + next;
  });
  var t = (parts.join("  |  ") || "No summon to show.") + "   ·   Summoner HP " + Math.round(w.owner.hp) +
    (battle() ? "   ·   Damage dealt " + Math.round(w.enemy.dmg * 10) / 10 : "");
  if (SP.info.textContent !== t) SP.info.textContent = t;
}
function buildList() {
  if (!SP.list) return;
  SP.list.innerHTML = "";
  var L = summonList();
  var S = X.S;
  if (!L.length || S.unique.type !== "summoner") {
    var m = document.createElement("span"); m.className = "note";
    m.textContent = S.unique.type === "summoner" ? "No summons yet." : "Summoner is not this character's unique ability.";
    SP.list.appendChild(m); return;
  }
  L.forEach(function (E, i) {
    var lab = document.createElement("label"), cb = document.createElement("input"); cb.type = "checkbox";
    var open = E.id === S.smPage;
    cb.checked = open || !!SP.extra[E.id]; cb.disabled = open;
    cb.onchange = function () { SP.extra[E.id] = cb.checked; if (cb.checked) summon(E); };
    lab.title = open ? "The summon whose settings are open: always shown." : "Tick to show this summon too.";
    lab.appendChild(cb);
    lab.appendChild(document.createTextNode(" " + (i + 1) + ". " + constructName(E) + (open ? " (open)" : "")));
    SP.list.appendChild(lab);
  });
}
function restart() { fresh(); shown().forEach(summon); }
function mkBtn(parent, text, title, fn) { var b = document.createElement("button"); b.textContent = text; b.title = title; b.onclick = fn; parent.appendChild(b); return b; }
function mkField(parent, label, el, title) {
  var l = document.createElement("label"); l.className = "spvf"; l.title = title || "";
  l.appendChild(document.createTextNode(label + " ")); l.appendChild(el); parent.appendChild(l); return el;
}
function build() {
  var css = document.createElement("style");
  css.textContent = "#spv{position:fixed;left:270px;top:60px;width:720px;min-width:340px;min-height:260px;max-width:96vw;max-height:94vh;z-index:7;" +
    "background:var(--panel);border:1px solid var(--line);border-radius:9px;box-shadow:0 10px 32px rgba(0,0,0,.5);display:flex;flex-direction:column;resize:both;overflow:hidden}" +
    "#spv[hidden]{display:none}#spv .spvh{display:flex;align-items:center;gap:8px;padding:6px 10px;border-bottom:1px solid var(--line);cursor:move;user-select:none;background:var(--panel2)}" +
    "#spv .spvh b{flex:1}#spv .spvb{overflow:auto;padding:8px 10px;display:flex;flex-direction:column;gap:6px}" +
    "#spv canvas{width:100%;display:block;border:1px solid var(--line);border-radius:6px;cursor:crosshair}" +
    "#spv .spvr{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center}#spv .spvf{display:inline-flex;gap:4px;align-items:center;font-size:12px}" +
    "#spv .spvf input[type=number]{width:64px}#spv .spvl{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px}";
  document.head.appendChild(css);
  var win = document.createElement("div"); win.id = "spv"; win.hidden = true;
  var hd = document.createElement("div"); hd.className = "spvh";
  var tt = document.createElement("b"); tt.textContent = "⚡ Summon preview"; hd.appendChild(tt);
  mkBtn(hd, "✕", "Close the preview", function () { win.hidden = true; });
  win.appendChild(hd);
  var body = document.createElement("div"); body.className = "spvb"; win.appendChild(body);
  var cv = document.createElement("canvas");
  cv.title = "Drag the Summoner (blue) or the Enemy (red) to move them.";
  body.appendChild(cv);
  var inf = document.createElement("div"); inf.className = "note"; body.appendChild(inf);
  var lst = document.createElement("div"); lst.className = "spvl"; body.appendChild(lst);
  var r1 = document.createElement("div"); r1.className = "spvr"; body.appendChild(r1);
  mkBtn(r1, "Summon now", "Places the shown summons now (Per summon each, up to Most at once), whatever their trigger.", function () { shown().forEach(summon); });
  mkBtn(r1, "Hit taken", "The Summoner takes one enemy shot: Hits taken / HP triggers, Liturgy Bell, Grounding, Soul Link and Shield Totem react.", function () { hurtOwner(SP.enemyDmg, "projectile"); });
  mkBtn(r1, "Hit landed", "The Summoner lands one hit: Demi-Bahamut answers it, the next Automaton Queen gets stronger.", function () { onLanded(); });
  mkBtn(r1, "Restart", "Clears the arena, refills HP and summons the shown summons once.", restart);
  var r2 = document.createElement("div"); r2.className = "spvr"; body.appendChild(r2);
  var modeSel = X.inp([["battle", "Battle (enemy fighter)"], ["solo", "Solo (the cursor)"]], SP.mode, function (v) { SP.mode = v; });
  mkField(r2, "Mode", modeSel, "Battle: the target is an enemy fighter (blasts, auras, taunts and drains reach it, and it shoots back). Solo: the target is the cursor (those only show their FX).");
  mkField(r2, "Zoom", X.inp([["1", "100 %"], ["1.5", "150 %"], ["2", "200 %"], ["3", "300 %"]], String(SP.zoom), function (v) { SP.zoom = +v; }),
    "Zooms in on the Summoner and the enemy (the arena is a 1600 x 900 screen).");
  mkField(r2, "Enemy", X.inp([["still", "Still (drag it)"], ["wander", "Wanders"], ["circle", "Circles the Summoner"], ["charge", "Charges the Summoner"]], SP.tmode, function (v) { SP.tmode = v; }),
    "How the enemy moves. Charging, it goes for a taunting Black Ox Effigy instead.");
  var r3 = document.createElement("div"); r3.className = "spvr"; body.appendChild(r3);
  mkField(r3, "Enemy shoots", X.inp("chk", SP.enemyFire, function (v) { SP.enemyFire = v; }), "Battle: the enemy fires at the Summoner (or a taunting Black Ox Effigy).");
  mkField(r3, "every ms", X.inp("n", SP.enemyMs, function (v) { SP.enemyMs = Math.max(100, v); }, 100, 20000, 100), "Time between enemy shots.");
  mkField(r3, "damage", X.inp("n", SP.enemyDmg, function (v) { SP.enemyDmg = Math.max(0, v); }, 0, 1000, 1), "Damage of each enemy shot (and of Hit taken).");
  mkField(r3, "Summoner hits every ms", X.inp("n", SP.ownerHitMs, function (v) { SP.ownerHitMs = Math.max(0, v); }, 0, 20000, 100), "The Summoner lands a hit this often (0 = never): feeds Demi-Bahamut and the Automaton Queen.");
  var hpIn = X.inp("n", 100, function (v) { if (SP.w) setOwnerHp(v); }, 1, 100, 5);
  mkField(r3, "Summoner HP %", hpIn, "Sets the Summoner's HP: HP-threshold summons and Earthly Star early detonation react.");
  document.body.appendChild(win);
  // drag the window by its header
  hd.onmousedown = function (ev) {
    if (ev.target.tagName === "BUTTON") return;
    var r = win.getBoundingClientRect(), ox = ev.clientX - r.left, oy = ev.clientY - r.top;
    win.style.right = "auto";
    function mv(e2) { win.style.left = Math.max(0, Math.min(innerWidth - 60, e2.clientX - ox)) + "px"; win.style.top = Math.max(0, Math.min(innerHeight - 30, e2.clientY - oy)) + "px"; }
    function up() { removeEventListener("mousemove", mv); removeEventListener("mouseup", up); }
    addEventListener("mousemove", mv); addEventListener("mouseup", up); ev.preventDefault();
  };
  // drag the summoner / the enemy on the arena
  var toWorld = function (ev) { var r = cv.getBoundingClientRect(), k = SP.cam[2] / r.width; return [SP.cam[0] + (ev.clientX - r.left) * k, SP.cam[1] + (ev.clientY - r.top) * k]; };
  cv.onmousedown = function (ev) {
    if (!SP.w) return;
    var p = toWorld(ev), o = SP.w.owner, e = SP.w.enemy;
    SP.drag = hyp(p[0] - o.x, p[1] - o.y) < hyp(p[0] - e.x, p[1] - e.y) ? "owner" : "enemy";
    cv.onmousemove(ev);
  };
  cv.onmousemove = function (ev) {
    if (!SP.drag || !SP.w) return;
    var p = toWorld(ev), b = SP.drag === "owner" ? SP.w.owner : SP.w.enemy;
    b.x = Math.max(10, Math.min(W - 10, p[0])); b.y = Math.max(10, Math.min(H - 10, p[1]));
  };
  cv.onmouseup = cv.onmouseleave = function () { SP.drag = null; };
  SP.win = win; SP.cv = cv; SP.info = inf; SP.list = lst;
}
// Opens (or brings back) the window; Restart the first time.
function open() {
  if (!SP.win) build();
  var first = !SP.w;
  SP.win.hidden = false;
  buildList();
  if (first) restart();
  if (!SP.running) { SP.running = true; SP.last = 0; requestAnimationFrame(loop); }
}
// The settings panel calls this when it rebuilds (summon picked, added,
// removed, renamed): the window's summon list follows.
function refresh() { if (SP.win && !SP.win.hidden) buildList(); }

// studio.js hands over its state and helpers once it has loaded.
function bind(x) { X = x; }

G.SUMMONPREVIEW = {bind: bind, open: open, refresh: refresh};
})(window);
