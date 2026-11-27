'use strict';
/* Action trigger conditions in V3 (Daniel 2026-11-27): one catalogue shared by the game (realkits.js realCond reads
   every type below against the V3 sim) and FX Studio 3D (its Conditions panel is built from it).
   Data = FX Studio's own `action_settings[a]` {logic any / all, cooldown_ms, conditions [{type, not, ...}]}, so a file
   still opens in the 2D FX Studio. Distances / speeds of FX Studio's types stay in 2D game px (28 px = one 1.8 m body);
   FX Studio 3D shows and edits them in metres (COND3D.PX_M). The V3-only types (group "3D") store metres directly. */
(function (G) {
  const PX_M = 1.8 / 28;   // metres per 2D game px (one body = 28 px = 1.8 m)
  // field kinds: px / pxs (stored 2D px / px per s, edited in m / m/s), m / ms_ / num / pct / count, chk, text, tags,
  // action (one of the character's actions), sel (options)
  const INTENTS = ['neutral', 'feint', 'engage', 'pressure', 'punish', 'reset', 'wait'];
  const T = {
    // ---- own state
    hp_below: {g: 'Own state', l: 'own HP at or below %', f: [['pct', 'HP %', 'pct', 50], ['repeat', 'Repeat (every crossing)', 'chk', false]],
      h: 'Own HP is at or below the %. Fires once per fight unless Repeat is on.'},
    hp_above: {g: 'Own state', l: 'own HP at or above %', f: [['pct', 'HP %', 'pct', 80]], h: 'Own HP is at or above the % (e.g. only while healthy).'},
    self_speed_above: {g: 'Own state', l: 'own speed at least', f: [['px_s', 'Speed (m/s)', 'pxs', 120]], h: 'This fighter is moving at least this fast (averaged over ~0.1 s, height included; blinks ignored).'},
    self_speed_below: {g: 'Own state', l: 'own speed at most', f: [['px_s', 'Speed (m/s)', 'pxs', 20]], h: 'This fighter is moving at most this fast. About 1.3 m/s or less = standing still.'},
    // ---- target
    target_within: {g: 'Target', l: 'target closer than', f: [['px', 'Distance (m)', 'px', 80]], h: 'The target is this close or closer (ground distance).'},
    target_beyond: {g: 'Target', l: 'target further than', f: [['px', 'Distance (m)', 'px', 200]], h: 'The target is this far or further (ground distance).'},
    target_between: {g: 'Target', l: 'target distance between', f: [['min_px', 'From (m)', 'px', 60], ['max_px', 'To (m)', 'px', 200]], h: 'The target\'s ground distance is inside the band.'},
    target_above: {g: 'Target', l: 'target above me', f: [['px', 'Height gap (m)', 'px', 40]], h: 'The target is at least this much higher in the air than this fighter.'},
    target_below: {g: 'Target', l: 'target below me', f: [['px', 'Height gap (m)', 'px', 40]], h: 'The target is at least this much lower than this fighter.'},
    target_facing: {g: 'Target', l: 'target facing me / away', f: [['dir', 'Target faces', 'sel', 'toward', ['toward', 'away']]], h: 'Toward: the target faces this fighter (within 90°). Away: its back is turned.'},
    target_attacking: {g: 'Target', l: 'target is attacking', f: [], h: 'The target is playing an attack, special or ultimate.'},
    target_defending: {g: 'Target', l: 'target is defending', f: [], h: 'The target is blocking, in an old-style parry or in a parry window (Ctrl+Space / AI roll).'},
    target_hp_below: {g: 'Target', l: 'target HP at or below %', f: [['pct', 'HP %', 'pct', 50]], h: 'The target\'s HP is at or below the %.'},
    target_hp_above: {g: 'Target', l: 'target HP at or above %', f: [['pct', 'HP %', 'pct', 80]], h: 'The target\'s HP is at or above the %.'},
    target_speed_above: {g: 'Target', l: 'target speed at least', f: [['px_s', 'Speed (m/s)', 'pxs', 120]], h: 'The target is moving at least this fast.'},
    target_speed_below: {g: 'Target', l: 'target speed at most', f: [['px_s', 'Speed (m/s)', 'pxs', 20]], h: 'The target is moving at most this fast.'},
    // ---- hits & projectiles
    attacks_made: {g: 'Hits & projectiles', l: 'after N attacks made', f: [['count', 'Count', 'count', 3]], h: 'This fighter started this many actions since this one last fired.'},
    hits_taken: {g: 'Hits & projectiles', l: 'after N hits taken', f: [['count', 'Count', 'count', 3]], h: 'Hit this many times since this action last fired.'},
    damage_taken: {g: 'Hits & projectiles', l: 'HP lost recently', f: [['hp', 'HP lost', 'num', 10], ['ms', 'Within (ms)', 'ms_', 2000]], h: 'Lost at least this much HP within the time window.'},
    landed_hit: {g: 'Hits & projectiles', l: 'just landed a hit', f: [], h: 'This fighter\'s hit (FX, shot or melee) landed on this tick.'},
    hit_by_fx: {g: 'Hits & projectiles', l: 'hit by FX tagged', f: [['tags', 'Tags (comma, empty = any)', 'tags', '']],
      h: 'Hit by an enemy FX with one of these tags (untagged FX go by their primitive, e.g. beam, sprite). Shots = "bullet", melee = "melee". Empty = any hit. Holds 0.5 s (the fighter is usually still reeling), used up by the first action it starts.'},
    fx_near: {g: 'Hits & projectiles', l: 'enemy FX tagged … within', f: [['tags', 'Tags (comma, empty = any)', 'tags', ''], ['px', 'Distance (m)', 'px', 60]],
      h: 'An enemy damaging FX (tags / primitive as above) or shot ("bullet") is within the distance of this fighter\'s body, in 3D.'},
    projectile_count: {g: 'Hits & projectiles', l: 'enemy projectiles live', f: [['count', 'Count', 'count', 5]], h: 'At least this many enemy shots and travelling damaging FX are live at once.'},
    bullet_deflected: {g: 'Hits & projectiles', l: 'just deflected a shot', f: [], h: 'This fighter parried / deflected / reflected a shot or travelling FX (perfect parry, old-style parry). Holds 0.5 s, used up by the first action it starts (one counter per deflect).'},
    // ---- timing & order
    after_actions: {g: 'Timing & order', l: 'after completing actions in order', f: [['sequence', 'Actions in order (comma)', 'text', '']], h: 'The last actions this fighter completed were exactly these, in this order (e.g. attack_normal_2, attack_special).'},
    since_action: {g: 'Timing & order', l: 'time since an action last ended', f: [['action', 'Action (empty = this one)', 'action', ''], ['ms', 'At least (ms)', 'ms_', 2000]], h: 'The chosen action last ended at least this long ago (or never played).'},
    every_ms: {g: 'Timing & order', l: 'every N ms', f: [['ms', 'Every (ms)', 'ms_', 3000]], h: 'At least this long since this action last fired (or the fight began): a repeating timer.'},
    idle_for: {g: 'Timing & order', l: 'idle (no action) for', f: [['ms', 'At least (ms)', 'ms_', 1000]], h: 'No action has played for at least this long.'},
    chance: {g: 'Timing & order', l: 'random chance per second', f: [['pct_s', 'Chance %/s', 'pct', 30]], h: 'A random roll: this % chance per second while the other conditions hold.'},
    // ---- actions
    action_triggered: {g: 'Actions', l: 'own / enemy action started', f: [['who', 'Whose', 'sel', 'target', ['target', 'self']], ['action', 'Action (empty = any)', 'action', ''], ['ms', 'Within (ms)', 'ms_', 300]],
      h: 'This fighter (self) or the target started the named action within the time window (0 ms = only on the tick it starts).'},
    // ---- blade hop
    hop_blades: {g: 'Blade hop', l: 'own hop blades out ≥ count', f: [['count', 'Count', 'count', 1], ['which', 'Which', 'sel', 'field', ['field', 'thrown', 'any']]],
      h: 'At least Count of this fighter\'s hop blades (blade FX with Blade hop on) are out. Field = planted or standing still, thrown = flying.'},
    hop_blade_near: {g: 'Blade hop', l: 'own hop blade within', f: [['px', 'Distance (m)', 'px', 60]], h: 'One of this fighter\'s hop blades is within the distance of its body (3D).'},
    // ---- fight rhythm & team
    tempo_intent: {g: 'Fight rhythm & team', l: 'own rhythm intent is', f: [['intent', 'Intent', 'sel', 'engage', INTENTS]], h: 'This fighter\'s Fight rhythm intent (tempo.js) is the chosen one.'},
    director_phase: {g: 'Fight rhythm & team', l: 'director phase is', f: [['phase', 'Phase', 'sel', 'burst', ['calm', 'build', 'burst']]], h: 'The fight director is calm, building or bursting.'},
    director_above: {g: 'Fight rhythm & team', l: 'director intensity at least %', f: [['pct', 'Intensity %', 'pct', 60]], h: 'The fight director\'s intensity is at least this %.'},
    has_token: {g: 'Fight rhythm & team', l: 'holds a melee attack token', f: [], h: 'V3 fields one fighter per side, so the attacker always holds the token: always true (kept for FX Studio files).'},
    target_open: {g: 'Fight rhythm & team', l: 'target is open (recovering / dazed)', f: [], h: 'The target is stunned / knocked back, or just whiffed an attack: a punish window.'},
    partner_intent: {g: 'Fight rhythm & team', l: 'a team-mate\'s rhythm intent is', f: [['intent', 'Intent', 'sel', 'pressure', INTENTS]], h: 'A team-mate ON THE FIELD is in this intent. V3 fields one fighter per side, so this is only true once several fight at once.'},
    partner_within: {g: 'Fight rhythm & team', l: 'a team-mate within', f: [['px', 'Distance (m)', 'px', 200]], h: 'A team-mate ON THE FIELD is this close (see above).'},
    partner_hp_below: {g: 'Fight rhythm & team', l: 'a team-mate\'s HP at or below %', f: [['pct', 'HP %', 'pct', 40]], h: 'A standing team-mate (benched tag partners included) is at or below this HP %.'},
    outnumbered: {g: 'Fight rhythm & team', l: 'outnumbered', f: [], h: 'Its team has fewer fighters standing (not K.O.\'d, bench included) than the enemy team.'},
    // ---- ally support
    ally_threatened: {g: 'Ally support', l: 'a team-mate is threatened', f: [['px', 'Threat within (m)', 'px', 120], ['by', 'Threat', 'sel', 'fx_or_enemy', ['fx', 'enemy', 'fx_or_enemy', 'ally', 'any']], ['max_px', 'Team-mate at most (m, 0 = any)', 'px', 600]],
      h: 'A team-mate ON THE FIELD has a threat (enemy FX / shot, the enemy fighter, another team-mate) within the distance. V3 fields one fighter per side, so this is only true once several fight at once.'},
    // ---- V3-only (3D): metres / m/s stored as such
    self_airborne: {g: '3D (V3 only)', l: 'own height above ground at least', f: [['m', 'Height (m)', 'm', 0.5]], h: 'This fighter is at least this high off the ground (jump, flight, launch).'},
    target_airborne: {g: '3D (V3 only)', l: 'target height above ground at least', f: [['m', 'Height (m)', 'm', 0.5]], h: 'The target is at least this high off the ground: anti-air, air combos.'},
    target_vertical: {g: '3D (V3 only)', l: 'target rising / falling', f: [['dir', 'Target is', 'sel', 'falling', ['rising', 'falling']], ['m_s', 'At least (m/s)', 'm', 2]], h: 'The target is in the air and moving up (rising) or down (falling) at least this fast.'},
    height_gap: {g: '3D (V3 only)', l: 'height gap to target between', f: [['min_m', 'From (m, + = target higher)', 'm', -1], ['max_m', 'To (m)', 'm', 1]], h: 'Target height minus own height is inside the band (negative = target lower).'},
    target_dist_3d: {g: '3D (V3 only)', l: '3D distance to target between', f: [['min_m', 'From (m)', 'm', 0], ['max_m', 'To (m, 0 = no limit)', 'm', 4]], h: 'Body centre to body centre, height included.'},
    self_sprinting: {g: '3D (V3 only)', l: 'own speed level at least', f: [['level', 'Level', 'sel', '2', ['2', '3']]], h: 'This fighter is moving at sprint speed (Lv2) or heightened speed (Lv3, sprint.js).'},
    self_flying: {g: '3D (V3 only)', l: 'own character can fly', f: [], h: 'This character has Can fly on (FX Studio 3D Character).'},
    target_knocked_back: {g: '3D (V3 only)', l: 'target knocked back at least', f: [['m_s', 'Speed (m/s)', 'm', 5]], h: 'The target is stunned and flying from a knockback at least this fast.'},
    target_juggled: {g: '3D (V3 only)', l: 'target is in a combo', f: [['count', 'Combo hits at least', 'count', 1]], h: 'The target is juggled in a knockback combo (combo.js) with at least this many hits so far.'},
    target_behind_me: {g: '3D (V3 only)', l: 'target behind me', f: [['deg', 'Outside the front (°)', 'num', 90]], h: 'The target is at least this many degrees off the way this fighter faces (90 = to the side or behind, 150 = right behind).'},
    target_stunned: {g: '3D (V3 only)', l: 'target stunned / staggered', f: [['kind', 'Kind', 'sel', 'any', ['any', 'stag', 'down', 'air']]], h: 'The target is stunned: stag = staggered (parry, light hit), down = knocked down, air = launched.'},
    locked_on: {g: '3D (V3 only)', l: 'locked on to the target', f: [], h: 'Your fighter holds the lock-on (T / middle mouse) on this target. The AI never locks on: always false for it.'},
    self_parry_window: {g: '3D (V3 only)', l: 'own parry window open', f: [['grade', 'Window', 'sel', 'any', ['any', 'perfect', 'normal']]], h: 'This fighter\'s parry window (Ctrl+Space / AI roll, parry.js) is open: a counter as the hit comes in.'},
    counter_ready: {g: '3D (V3 only)', l: 'counter window after a perfect parry', f: [], h: 'This fighter perfect-parried the target and its counter window (hits x counter bonus) is still open.'}
  };
  // actions V3 never starts from conditions (locomotion, poses, hit reactions; attack_normal = first chain hit; switch_in plays on a tag-in)
  const NONTRIG = new Set(['idle', 'run', 'attack_normal', 'switch_in', 'switch_out', 'transform', 'walk', 'sprint', 'dash', 'jump', 'air', 'air_move',
    'fall', 'land', 'turn', 'run_back', 'run_left', 'run_right', 'run_stop', 'jump_start', 'jump_air', 'jump_land', 'fly_forward', 'fly_back',
    'fly_left', 'fly_right', 'fly_incline', 'fly_decline', 'dodge', 'dodge_back', 'dodge_left', 'dodge_right', 'hit_light', 'hit_heavy', 'hit_air',
    'stagger', 'knockdown', 'getup', 'ko']);
  const triggerable = a => !!a && !NONTRIG.has(a);
  const groups = [];
  Object.keys(T).forEach(k => { let gr = groups.find(x => x[0] === T[k].g); if (!gr) groups.push(gr = [T[k].g, []]); gr[1].push(k); });
  function blank(type) { const m = T[type]; const c = {type, not: false}; if (m) m.f.forEach(f => { c[f[0]] = f[3]; }); return c; }
  // "a, B ,c" -> ["a", "b", "c"]
  const tags = s => String(s || '').split(',').map(x => x.trim().toLowerCase()).filter(Boolean);
  const tagMatch = (want, tag) => !want.length || want.includes(String(tag || '').toLowerCase());
  G.COND3D = {TYPES: T, GROUPS: groups, PX_M, triggerable, NONTRIG, blank, tags, tagMatch};
})(typeof window !== 'undefined' ? window : globalThis);
