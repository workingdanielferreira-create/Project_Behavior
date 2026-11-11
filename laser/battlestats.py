"""
battlestats.py — per-fighter battle statistics for the post-battle results
window (laser/statsscreen.py).  Solo and Battle alike.

World-owned (`world.stats`, a Stats).  Two feeds:

  * Hit events, from the damage choke points:
      ai.apply_hp_damage        on_damage / on_negated / on_absorbed
      ai.battle_hit             on_negated (bullet blocked)
      World.refresh_battle      note_source (FX owner + its action),
                                on_negated (FX parried / defended)
      targeting.note_hit        note_source (attacker known)
    The attacker of a hit is the one noted on the victim this tick or the
    last; otherwise the victim's last attacker (targeting.last_hit_by), the
    only enemy fighter, or nobody ("Environment" / "Cursor" in Solo).
    Mirror Legion copies / Summoner constructs credit their owner.

  * Solo cursor hits (the cursor has no HP): cursor_hit, from
      fxkit.FxDriver lanes (read-only probe of each damaging FX against
      the cursor, own re-hit clock — the FX itself is untouched),
      the built-in bullet-vs-cursor check (systems.py) and a built-in
      dash-slash landing (World.refresh_battle).

  * Per-tick sampling, `step(world)` from Overlay._tick after both sides:
    distance, speed, knockback, teleports, action starts, dodges, healing,
    HP timeline, and the end-of-battle check (a KO left one team standing).

Nothing here changes the fight: it only reads.
"""

from collections import deque
import math

from . import config

TICK_S = config.TICK_MS / 1000.0
COMBO_GAP_TICKS = int(round(1200 / config.TICK_MS))   # hits <= 1.2 s apart chain
BURST_TICKS = int(round(1000 / config.TICK_MS))       # best 1-second burst window
TELEPORT_PX = 60.0            # one-tick moves longer than this = a warp, not running
SPEED_WINDOW = 4              # ticks averaged for the speed reading
STILL_PX = 0.35               # per-tick move under this = standing still
TIMELINE_EVERY = 8            # ticks between HP samples (doubles when it gets long)
TIMELINE_MAX = 480
END_DELAY_TICKS = int(round(1400 / config.TICK_MS))   # let the KO shot play first
SOURCE_TICKS = 2              # a noted attacker stays valid this many ticks
CURSOR = "CURSOR"

# Attacker noted on a victim just before its hit lands: id(victim) ->
# (attacker, action, tick).  Module level so targeting.note_hit (no world at
# hand) can feed it; _CLOCK is the world tick, kept by World ticks (Stats.step).
_PEND = {}
_CLOCK = [0]

_ACTION_LABELS = {
    "attack_normal": "Attack",
    "attack_special": "Special",
    "ultimate": "Ultimate",
    "defend": "Defend",
    "dodge": "Dodge",
    "switch_in": "Switch in",
    "switch_out": "Switch out",
    "idle": "Idle",
    "walk": "Walk",
}


def action_label(name):
    """'attack_normal_2' -> 'Attack 2', 'my_cool_move' -> 'My cool move'."""
    if not name:
        return "Other"
    name = str(name)
    if name in _ACTION_LABELS:
        return _ACTION_LABELS[name]
    base, _, tail = name.rpartition("_")
    if base in _ACTION_LABELS and tail.isdigit():
        return "%s %s" % (_ACTION_LABELS[base], tail)
    if name[:1].isupper() or " " in name:
        return name
    return name.replace("_", " ").capitalize()


def _now(world):
    return int(getattr(world, "global_tick", 0) or 0)


def _is_clone(fig):
    st = getattr(fig, "ua", None)
    return st is not None and getattr(st, "clone_of", None) is not None


def _owner(fig):
    """A Mirror Legion copy / Summoner construct -> the fighter it belongs to."""
    seen = 0
    while fig is not None and _is_clone(fig) and seen < 4:
        fig = fig.ua.clone_of
        seen += 1
    return fig


def _fig_name(fig):
    ch = getattr(fig.mode, "character", None) or {}
    return str(ch.get("display_name") or fig.mode.key).replace("_", " ").upper()


def _fig_rgb(fig):
    """The fighter's colour (its LUT midpoint, like the HP bars), brightened
    so a dark palette (the swordsman's deep red) still reads on the dark
    results window."""
    try:
        c = fig.lut[128]
        r, g, b = float(c[0]), float(c[1]), float(c[2])
    except Exception:
        return (200, 200, 200)
    top = max(r, g, b, 1.0)
    k = 255.0 / top
    r, g, b = r * k, g * k, b * k
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum < 110:
        t = (110 - lum) / (255 - lum)
        r, g, b = (v + (255 - v) * t for v in (r, g, b))
    return (int(r), int(g), int(b))


class ActionStat:
    __slots__ = ("uses", "hits", "dmg", "max_hit")

    def __init__(self):
        self.uses = 0
        self.hits = 0
        self.dmg = 0.0
        self.max_hit = 0.0


class FighterStats:
    def __init__(self, fig, world):
        self.fid = id(fig)
        self.fig = fig
        self.name = _fig_name(fig)
        self.key = fig.mode.key
        self.rgb = _fig_rgb(fig)
        self.slot = ""
        self.pick = 99
        self.team = 0
        self.first_tick = _now(world)
        self.left = False                 # left the roster before the end
        # Offence
        self.dealt = 0.0
        self.hits = 0
        self.max_hit = 0.0
        self.max_hit_action = ""
        self.max_hit_target = ""
        self.by_action = {}               # action name -> ActionStat
        self.by_target = {}               # target name -> damage
        self.kos = 0
        self.first_blood = False
        self.first_hit_tick = None
        self.combo_n = 0
        self.combo_dmg = 0.0
        self.combo_last = -10 ** 9
        self.combo_target = None
        self.best_combo = 0
        self.best_combo_dmg = 0.0
        self.top_combo_dmg = 0.0          # most damage in one combo (any length)
        self._burst = deque()
        self.best_burst = 0.0
        # Defence
        self.taken = 0.0
        self.hits_taken = 0
        self.max_taken = 0.0
        self.max_taken_from = ""
        self.by_source = {}               # attacker name -> damage taken
        self.blocked = 0                  # hits negated (parry / defend / stance / phase / riposte)
        self.absorbed = 0.0               # damage soaked by a shield
        self.healed = 0.0
        self.deaths = 0
        self.ko_tick = None
        self.max_hp = float(max(1, fig.personality.max_hp))
        self.hp = float(fig.personality.hp)
        self.low_hp = self.hp
        self.dodges = 0
        self.vanishes = 0
        # Movement
        self.distance = 0.0
        self.kb_distance = 0.0
        self.top_speed = 0.0              # px/s, own movement
        self.top_kb_speed = 0.0           # px/s, while knocked back
        self.teleports = 0
        self.tp_distance = 0.0
        self.moving_ticks = 0
        self.field_ticks = 0
        self._last_pos = None
        self._spd = deque(maxlen=SPEED_WINDOW)
        self._last_action = None
        self._was_dodge = False
        self._was_gone = False
        # Timeline: (tick, hp fraction)
        self.timeline = [(self.first_tick, self.hp / self.max_hp)]
        self.dealt_line = [(self.first_tick, 0.0)]

    # ---- helpers ----------------------------------------------------------
    def act(self, name):
        a = self.by_action.get(name)
        if a is None:
            a = self.by_action[name] = ActionStat()
        return a

    @property
    def avg_speed(self):
        return (self.distance / (self.moving_ticks * TICK_S)) if self.moving_ticks else 0.0

    @property
    def field_s(self):
        return self.field_ticks * TICK_S

    @property
    def dps(self):
        return self.dealt / self.field_s if self.field_ticks > 0 else 0.0


class Stats:
    def __init__(self):
        self.reset(None)

    # ---- lifecycle --------------------------------------------------------
    def reset(self, world):
        self.fighters = {}            # id(fig) -> FighterStats
        self.order = []               # first-seen order
        self.start_tick = _now(world) if world is not None else 0
        self.end_tick = None
        self.had_battle = False
        self.battle_seen = False
        self.over = False             # a winner was decided (window shown once)
        self.winner = None            # team index, -1 = draw, None = undecided
        self.solo_end = False
        self.check_end = False
        self.end_wait = 0
        self.first_blood_done = False
        _PEND.clear()
        self._probe = {}              # id(fx inst) -> [hits, last_age, seen_tick]
        self._proj_seen = {}          # id(bullet) -> tick credited (pierce re-hit)
        self._tl_every = TIMELINE_EVERY

    def record(self, fig, world):
        if fig is None or _is_clone(fig):
            return None
        st = self.fighters.get(id(fig))
        if st is None or st.fig is not fig:
            st = FighterStats(fig, world)
            self.fighters[id(fig)] = st
            self.order = [o for o in self.order if o != id(fig)] + [id(fig)]
            self._place(st, world)
        return st

    def _place(self, st, world):
        if world is None:
            return
        for s in getattr(world, "slots", None) or []:
            if s.fig is st.fig:
                st.slot, st.pick, st.team = s.name, s.pick, s.team
                return
        for t, side in enumerate(getattr(world, "sides", None) or []):
            if any(f is st.fig for f in side.figures):
                st.team = t
                return

    def ordered(self):
        out = [self.fighters[k] for k in self.order if k in self.fighters]
        return sorted(out, key=lambda s: (s.team, s.pick, s.first_tick))

    def duration_s(self, world):
        end = self.end_tick if self.end_tick is not None else _now(world)
        return max(0, end - self.start_tick) * TICK_S

    # ---- attribution ------------------------------------------------------
    def note_source(self, world, victim, attacker, action=None):
        note_attacker(victim, attacker, action, _now(world))

    def _attacker(self, world, victim, kind):
        now = _now(world)
        pend = _PEND.pop(id(victim), None)
        if pend is not None and now - pend[2] <= SOURCE_TICKS and pend[0] is not None:
            return _owner(pend[0]), pend[1]
        sides = getattr(world, "sides", None) or []
        mine = next((t for t, sd in enumerate(sides) if any(f is victim for f in sd.figures)), None)
        enemies = []
        if mine is not None and len(sides) > 1 and getattr(world, "battle_mode", False):
            enemies = [f for f in sides[1 - mine].figures]
        la = getattr(victim, "last_hit_by", None)
        if la is not None:
            for f in enemies:
                if id(f) == la:
                    return _owner(f), None
        real = [f for f in enemies if not _is_clone(f)]
        if len(real) == 1:
            return real[0], None
        return None, None

    @staticmethod
    def _action_for(attacker, action, kind):
        if action:
            return action
        if kind == "projectile":
            return "Shots"
        try:
            from . import actions as _actions
            a = _actions.current_action_name(attacker)
        except Exception:
            a = None
        if a:
            return a
        return "FX" if kind == "fx" else "Melee"

    def _credit(self, world, ast, amount, action, target_name, target_hp_frac=None):
        now = _now(world)
        ast.dealt += amount
        ast.hits += 1
        a = ast.act(action)
        a.hits += 1
        a.dmg += amount
        a.max_hit = max(a.max_hit, amount)
        ast.by_target[target_name] = ast.by_target.get(target_name, 0.0) + amount
        if amount > ast.max_hit:
            ast.max_hit = amount
            ast.max_hit_action = action
            ast.max_hit_target = target_name
        if ast.first_hit_tick is None:
            ast.first_hit_tick = now
        if not self.first_blood_done:
            self.first_blood_done = True
            ast.first_blood = True
        # Combo: hits on the same target no more than COMBO_GAP apart, broken
        # by the attacker taking a hit.
        if ast.combo_target == target_name and now - ast.combo_last <= COMBO_GAP_TICKS:
            ast.combo_n += 1
            ast.combo_dmg += amount
        else:
            ast.combo_n, ast.combo_dmg, ast.combo_target = 1, amount, target_name
        ast.combo_last = now
        if ast.combo_n > ast.best_combo or (ast.combo_n == ast.best_combo
                                            and ast.combo_dmg > ast.best_combo_dmg):
            ast.best_combo, ast.best_combo_dmg = ast.combo_n, ast.combo_dmg
        ast.top_combo_dmg = max(ast.top_combo_dmg, ast.combo_dmg)
        b = ast._burst
        b.append((now, amount))
        while b and now - b[0][0] >= BURST_TICKS:
            b.popleft()
        ast.best_burst = max(ast.best_burst, sum(x[1] for x in b))

    # ---- hit events -------------------------------------------------------
    def on_damage(self, world, victim, amount, kind="melee", killed=False):
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return
        if amount <= 0 or victim is None:
            return
        attacker, action = self._attacker(world, victim, kind)
        vst = self.record(victim, world)
        if attacker is victim:
            attacker = None
        ast = self.record(attacker, world) if attacker is not None else None
        if ast is not None and vst is not None and ast.team == vst.team \
                and getattr(world, "battle_mode", False) is False and not _is_clone(victim):
            ast = None   # Solo: own-team "attacker" guesses are never right
        src_name = ast.name if ast is not None else (
            "Cursor" if not getattr(world, "battle_mode", False) else "Environment")
        if ast is not None:
            act = self._action_for(attacker, action, kind)
            tgt = _fig_name(victim) if not _is_clone(victim) else "Copy / construct"
            self._credit(world, ast, amount, act, tgt)
            if killed and not _is_clone(victim):
                ast.kos += 1
        if vst is not None:
            vst.taken += amount
            vst.hits_taken += 1
            vst.by_source[src_name] = vst.by_source.get(src_name, 0.0) + amount
            if amount > vst.max_taken:
                vst.max_taken = amount
                vst.max_taken_from = src_name
            # Taking a hit breaks your own combo.
            vst.combo_n, vst.combo_dmg, vst.combo_target = 0, 0.0, None
            if killed:
                vst.deaths += 1
                vst.ko_tick = _now(world)
                self.check_end = True

    def on_negated(self, world, victim):
        vst = self.record(victim, world)
        if vst is not None:
            vst.blocked += 1
        _PEND.pop(id(victim), None)

    def on_absorbed(self, world, victim, amount):
        vst = self.record(victim, world)
        if vst is not None and amount > 0:
            vst.absorbed += float(amount)

    def cursor_hit(self, world, attacker, amount, action):
        """Solo: an attack of `attacker` reached the cursor (never once this
        sheet has seen a battle: a slash landing just after the last KO)."""
        if getattr(world, "battle_mode", False) or self.battle_seen:
            return
        attacker = _owner(attacker)
        ast = self.record(attacker, world) if attacker is not None else None
        if ast is None:
            return
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return
        if amount <= 0:
            return
        self._credit(world, ast, amount, action or "Other", CURSOR)

    def cursor_bullet(self, world, proj):
        """Solo: a built-in bullet touched the cursor (pierce re-credits at
        most every 15 ticks)."""
        if getattr(world, "battle_mode", False) or self.battle_seen:
            return
        now = _now(world)
        k = id(proj)
        last = self._proj_seen.get(k)
        if last is not None and now - last < 15:
            return
        self._proj_seen[k] = now
        self.cursor_hit(world, getattr(proj, "owner", None),
                        getattr(proj, "damage", 1.0), getattr(proj, "action", None) or "Shots")

    def probe_hit(self, inst, now_tick, rehit_ticks):
        """Re-hit clock for the Solo cursor probe (per FX instance).  True =
        count a hit now."""
        k = id(inst)
        e = self._probe.get(k)
        age = inst.age
        if e is None or e[3] is not inst.fx:
            self._probe[k] = [1, age, now_tick, inst.fx]
            return True
        e[2] = now_tick
        if rehit_ticks > 0 and age - e[1] >= rehit_ticks:
            e[0] += 1
            e[1] = age
            return True
        return False

    # ---- per tick ---------------------------------------------------------
    def step(self, world):
        now = _now(world)
        _CLOCK[0] = now
        try:
            from . import blink as _blink
            from . import dodge as _dodge
            from . import actions as _actions
        except Exception:
            return
        sides = getattr(world, "sides", None) or []
        if getattr(world, "battle_mode", False):
            self.battle_seen = True
        seen = set()
        for side in sides:
            for f in side.figures:
                if _is_clone(f):
                    continue
                st = self.record(f, world)
                if st is None:
                    continue
                seen.add(id(f))
                self._sample(world, st, f, now, _blink, _dodge, _actions)
        # Benched / fallen fighters: HP still followed (a benched partner
        # never changes, a fallen one reads 0).
        for st in self.fighters.values():
            if st.fid in seen:
                continue
            st._last_pos = None
            st._spd.clear()
            hp = float(st.fig.personality.hp)
            if hp != st.hp:
                st.hp = hp
                st.low_hp = min(st.low_hp, hp)
        if (now - self.start_tick) % self._tl_every == 0:
            for st in self.fighters.values():
                st.timeline.append((now, max(0.0, st.hp / st.max_hp)))
                st.dealt_line.append((now, st.dealt))
                if len(st.timeline) > TIMELINE_MAX:
                    st.timeline = st.timeline[::2]
                    st.dealt_line = st.dealt_line[::2]
            if any(len(st.timeline) > TIMELINE_MAX // 2 for st in self.fighters.values()) \
                    and self._tl_every < 64 and (now - self.start_tick) > self._tl_every * TIMELINE_MAX:
                self._tl_every *= 2
        # Housekeeping.
        if now % 120 == 0:
            self._probe = {k: e for k, e in self._probe.items() if now - e[2] < 30}
            self._proj_seen = {k: t for k, t in self._proj_seen.items() if now - t < 120}
            for k in [k for k, e in _PEND.items() if now - e[2] > SOURCE_TICKS]:
                del _PEND[k]
        self._check_end(world)

    def _sample(self, world, st, f, now, _blink, _dodge, _actions):
        st.field_ticks += 1
        st.left = False
        hp = float(f.personality.hp)
        if hp > st.hp + 1e-6:
            st.healed += hp - st.hp
        st.hp = hp
        st.low_hp = min(st.low_hp, hp)
        st.max_hp = float(max(1, f.personality.max_hp))
        gone = bool(_blink.gone(f))
        if gone and not st._was_gone:
            st.vanishes += 1
        st._was_gone = gone
        dg = False
        try:
            dg = bool(_dodge.untouchable(f, now))
        except Exception:
            pass
        if dg and not st._was_dodge:
            st.dodges += 1
        st._was_dodge = dg
        a = None
        try:
            a = _actions.current_action_name(f)
        except Exception:
            pass
        if a and a != st._last_action:
            st.act(a).uses += 1
        st._last_action = a
        if not f.transform.init:
            st._last_pos = None
            return
        x, y = float(f.x), float(f.y)
        lp = st._last_pos
        st._last_pos = (x, y)
        if lp is None or gone:
            st._spd.clear()
            return
        d = math.hypot(x - lp[0], y - lp[1])
        if d > TELEPORT_PX:
            st.teleports += 1
            st.tp_distance += d
            st._spd.clear()
            return
        kb = bool(getattr(f.motion, "bouncing", False))
        if d >= STILL_PX:
            st.moving_ticks += 1
            if kb:
                st.kb_distance += d
            else:
                st.distance += d
        st._spd.append((d, kb))
        if len(st._spd) == SPEED_WINDOW:
            v = sum(e[0] for e in st._spd) / (SPEED_WINDOW * TICK_S)
            if all(e[1] for e in st._spd):
                st.top_kb_speed = max(st.top_kb_speed, v)
            elif not any(e[1] for e in st._spd):
                st.top_speed = max(st.top_speed, v)

    def _check_end(self, world):
        """A KO left exactly one team (or none) standing in a battle: decide
        the winner, wait for the KO slow-mo + shot, then ask for the results
        window (World.stats_requested)."""
        alive = self._teams_alive(world)
        if self.over:
            if self.end_wait > 0 and getattr(world, "slowmo_ticks", 0) <= 0:
                self.end_wait -= 1
                if self.end_wait == 0:
                    world.stats_requested = "end"
            elif self.end_wait <= 0 and not self.solo_end and all(alive):
                # Keep watching, then both teams fielded again (slot keys):
                # a new fight on the same sheet — it can end again.
                self.over, self.winner, self.end_tick = False, None, None
                self.had_battle = True
            return
        if all(alive):
            self.had_battle = True
            self.check_end = False
            return
        if not self.check_end:
            return
        self.check_end = False
        if not self.had_battle:
            return
        standing = [t for t, a in enumerate(alive) if a]
        self.winner = standing[0] if len(standing) == 1 else -1
        self.over = True
        self.end_tick = _now(world)
        self.end_wait = END_DELAY_TICKS

    @staticmethod
    def _teams_alive(world):
        out = []
        slots = getattr(world, "slots", None) or []
        for t, side in enumerate(getattr(world, "sides", None) or []):
            a = any(not _is_clone(f) and f.personality.hp > 0 for f in side.figures)
            if not a:
                a = any(s.team == t and s.fig is not None and s.fig.personality.hp > 0
                        for s in slots)
            out.append(a)
        return out

    def sync(self, world):
        """Bring every sheet up to this instant before the results window
        reads it (a Solo KO hold or the KO slow-mo skips the per-tick
        sampling): current HP, lowest HP, a closing timeline point."""
        now = _now(world)
        for st in self.fighters.values():
            hp = float(st.fig.personality.hp)
            st.hp = hp
            st.low_hp = min(st.low_hp, hp)
            if not st.timeline or st.timeline[-1][0] < now:
                st.timeline.append((now, max(0.0, hp / st.max_hp)))
                st.dealt_line.append((now, st.dealt))

    def solo_over(self, world):
        """Solo's final KO (World.on_figure_death): the run is over."""
        self.over = True
        self.solo_end = True
        self.winner = None
        self.end_tick = _now(world)

    # ---- awards -----------------------------------------------------------
    def awards(self):
        """[(icon, title, fighter name, rgb, why)] — only fighters who earned
        something non-zero; ties go to the earlier pick."""
        fs = [s for s in self.ordered()]
        if not fs:
            return []
        out = []

        def best(key, title, icon, why, lowest=False, need=None):
            cands = [s for s in fs if (need is None or need(s))]
            if not cands:
                return
            vals = [(key(s), s) for s in cands]
            if lowest:
                v, s = min(vals, key=lambda e: e[0])
            else:
                v, s = max(vals, key=lambda e: e[0])
                if v <= 0:
                    return
            out.append((icon, title, s.name, s.rgb, why(v, s)))

        best(lambda s: s.dealt, "MVP", "\U0001F3C6", lambda v, s: "%s damage dealt" % _n(v))
        best(lambda s: s.max_hit, "Heavy Hitter", "\U0001F4A5",
             lambda v, s: "%s in one hit (%s)" % (_n(v), action_label(s.max_hit_action)))
        best(lambda s: s.best_combo, "Combo King", "\U0001F525",
             lambda v, s: "%d-hit combo (%s dmg)" % (v, _n(s.best_combo_dmg)),
             need=lambda s: s.best_combo >= 2)
        best(lambda s: s.best_burst, "Burst", "⚡", lambda v, s: "%s damage in 1 s" % _n(v))
        best(lambda s: s.top_speed, "Speed Demon", "\U0001F4A8", lambda v, s: "%s px/s top speed" % _n(v))
        best(lambda s: s.distance, "Marathon", "\U0001F45F", lambda v, s: "%s px travelled" % _n(v))
        best(lambda s: s.kos, "Finisher", "\U0001F480", lambda v, s: "%d KO%s" % (v, "" if v == 1 else "s"))
        best(lambda s: s.blocked, "Iron Wall", "\U0001F6E1", lambda v, s: "%d hits blocked / negated" % v)
        best(lambda s: s.teleports + s.vanishes, "Phantom", "\U0001F47B",
             lambda v, s: "%d warps / vanishes" % v)
        best(lambda s: s.taken, "Untouchable", "✨", lambda v, s: "only %s damage taken" % _n(v),
             lowest=True, need=lambda s: s.field_ticks > 0 and s.deaths == 0 and len(fs) > 1)
        best(lambda s: (1.0 - s.low_hp / s.max_hp) if s.deaths == 0 else 0.0, "Clutch", "❤",
             lambda v, s: "survived at %d%% HP" % int(round(100 * s.low_hp / s.max_hp)),
             need=lambda s: s.deaths == 0 and s.low_hp / s.max_hp <= 0.25)
        for s in fs:
            if s.first_blood:
                out.append(("\U0001FA78", "First Blood", s.name, s.rgb,
                            "landed the first hit at %s" % _clock((s.first_hit_tick or 0) - self.start_tick)))
                break
        return out


def _n(v):
    v = float(v)
    if abs(v) >= 100 or abs(v - round(v)) < 0.05:
        return "{:,}".format(int(round(v)))
    return "%.1f" % v


def _clock(ticks):
    s = max(0.0, ticks * TICK_S)
    return "%d:%04.1f" % (int(s // 60), s % 60)


fmt_num = _n
fmt_clock = _clock


# ---- module-level hooks (safe when the world has no stats) ----------------
def _st(world):
    return getattr(world, "stats", None) if world is not None else None


def note_attacker(victim, attacker, action=None, tick=None):
    """`attacker` is about to land a hit on `victim` (targeting.note_hit,
    World.refresh_battle).  `action` = the action it came from, if known."""
    if victim is None or attacker is None:
        return
    prev = _PEND.get(id(victim))
    if action is None and prev is not None and prev[0] is attacker and prev[1]:
        action = prev[1]     # keep the more specific note made this tick
    _PEND[id(victim)] = (attacker, action, _CLOCK[0] if tick is None else tick)


def note_source(world, victim, attacker, action=None):
    note_attacker(victim, attacker, action, getattr(world, "global_tick", None))


def on_damage(world, victim, amount, kind="melee", killed=False):
    s = _st(world)
    if s is not None:
        try:
            s.on_damage(world, victim, amount, kind, killed)
        except Exception as e:
            _log(e)


def on_negated(world, victim):
    s = _st(world)
    if s is not None:
        try:
            s.on_negated(world, victim)
        except Exception as e:
            _log(e)


def on_absorbed(world, victim, amount):
    s = _st(world)
    if s is not None:
        s.on_absorbed(world, victim, amount)


def cursor_hit(world, attacker, amount, action):
    s = _st(world)
    if s is not None:
        try:
            s.cursor_hit(world, attacker, amount, action)
        except Exception as e:
            _log(e)


def cursor_bullet(world, proj):
    s = _st(world)
    if s is not None:
        try:
            s.cursor_bullet(world, proj)
        except Exception as e:
            _log(e)


def _log(e):
    try:
        from . import action_log
        action_log.error("battlestats", e)
    except Exception:
        pass
