"""
battlestats.py — damage dealt per action, per fighter, for the post-battle
results window (laser/statsscreen.py: one 100% stacked bar per fighter).
Solo and Battle alike.  Nothing else is recorded.

World-owned (`world.stats`, a Stats).  Feeds:

  * Hit events, from the damage choke points:
      ai.apply_hp_damage        on_damage / on_negated
      ai.battle_hit             on_negated (bullet blocked)
      World.refresh_battle      note_source (FX owner + its action),
                                on_negated (FX parried / defended)
      targeting.note_hit        note_source (attacker known)
    The attacker of a hit is the one noted on the victim this tick or the
    last; otherwise the victim's last attacker (targeting.last_hit_by), or
    the only enemy fighter; else nobody (not counted).  Mirror Legion
    copies / Summoner constructs credit their owner.

  * Solo cursor hits (the cursor has no HP): cursor_hit / cursor_bullet /
    probe_hit, from fxkit.solo_cursor_probe, the built-in bullet-vs-cursor
    check (systems.py) and a built-in dash-slash landing (World.refresh_battle).

  * `step(world)` from Overlay._tick: the end-of-battle check (a KO left one
    team standing) -> world.stats_requested = "end".

Every hit / negated hit / KO also feeds the Fight rhythm director's heat
(tempo.count).  Nothing here changes the fight: it only reads.
"""

from . import config

END_DELAY_TICKS = int(round(1400 / config.TICK_MS))   # let the KO shot play first
SOURCE_TICKS = 2              # a noted attacker stays valid this many ticks

# Attacker noted on a victim just before its hit lands: id(victim) ->
# (attacker, action, tick).  Module level so targeting.note_hit (no world at
# hand) can feed it; _CLOCK is the world tick, kept by Stats.step.
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
    so a dark palette still reads on the dark results window."""
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


def _heat(world, i, v=1.0):
    """Fight rhythm director heat (laser/tempo.py)."""
    from . import tempo
    tempo.count(world, i, v)


class FighterStats:
    __slots__ = ("fig", "name", "rgb", "slot", "pick", "team", "first_tick", "dealt", "by_action")

    def __init__(self, fig, world):
        self.fig = fig
        self.name = _fig_name(fig)
        self.rgb = _fig_rgb(fig)
        self.slot = ""
        self.pick = 99
        self.team = 0
        self.first_tick = _now(world)
        self.dealt = 0.0
        self.by_action = {}               # action name -> damage dealt


class Stats:
    def __init__(self):
        self.reset(None)

    # ---- lifecycle --------------------------------------------------------
    def reset(self, world):
        self.fighters = {}            # id(fig) -> FighterStats
        self.had_battle = False
        self.battle_seen = False
        self.over = False             # a winner was decided (window shown once)
        self.winner = None            # team index, -1 = draw, None = undecided
        self.solo_end = False
        self.check_end = False
        self.end_wait = 0
        _PEND.clear()
        self._probe = {}              # id(fx inst) -> [hits, last_age, seen_tick, fx]
        self._proj_seen = {}          # id(bullet) -> tick credited (pierce re-hit)

    def record(self, fig, world):
        if fig is None or _is_clone(fig):
            return None
        st = self.fighters.get(id(fig))
        if st is None or st.fig is not fig:
            st = FighterStats(fig, world)
            self.fighters[id(fig)] = st
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
        return sorted(self.fighters.values(), key=lambda s: (s.team, s.pick, s.first_tick))

    # ---- attribution ------------------------------------------------------
    def _attacker(self, world, victim):
        now = _now(world)
        pend = _PEND.pop(id(victim), None)
        if pend is not None and now - pend[2] <= SOURCE_TICKS and pend[0] is not None:
            return _owner(pend[0]), pend[1]
        if not getattr(world, "battle_mode", False):
            return None, None
        sides = getattr(world, "sides", None) or []
        mine = next((t for t, sd in enumerate(sides) if any(f is victim for f in sd.figures)), None)
        if mine is None or len(sides) < 2:
            return None, None
        enemies = sides[1 - mine].figures
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

    def _credit(self, world, ast, amount, action):
        ast.dealt += amount
        ast.by_action[action] = ast.by_action.get(action, 0.0) + amount
        _heat(world, 0)
        _heat(world, 1, amount)

    # ---- hit events -------------------------------------------------------
    def on_damage(self, world, victim, amount, kind="melee", killed=False):
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return
        if amount <= 0 or victim is None:
            return
        attacker, action = self._attacker(world, victim)
        clone_victim = _is_clone(victim)
        if attacker is victim:
            attacker = None
        # Solo: own-team "attacker" guesses are never right.
        if attacker is not None and not clone_victim and not getattr(world, "battle_mode", False):
            attacker = None
        ast = self.record(attacker, world) if attacker is not None else None
        if ast is not None:
            self._credit(world, ast, amount, self._action_for(attacker, action, kind))
            if killed and not clone_victim:
                _heat(world, 4)
        if not clone_victim:
            _heat(world, 3, amount)
            if killed:
                self.check_end = True

    def on_negated(self, world, victim):
        _PEND.pop(id(victim), None)
        if not _is_clone(victim):
            _heat(world, 2)

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
        self._credit(world, ast, amount, action or "Other")

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
        if getattr(world, "battle_mode", False):
            self.battle_seen = True
        if now % 120 == 0:
            if self._probe:
                self._probe = {k: e for k, e in self._probe.items() if now - e[2] < 30}
            if self._proj_seen:
                self._proj_seen = {k: t for k, t in self._proj_seen.items() if now - t < 120}
            for k in [k for k, e in _PEND.items() if now - e[2] > SOURCE_TICKS]:
                del _PEND[k]
        self._check_end(world)

    def _check_end(self, world):
        """A KO left exactly one team (or none) standing in a battle: decide
        the winner, wait for the KO slow-mo + shot, then ask for the results
        window (World.stats_requested)."""
        if self.over:
            if self.end_wait > 0:
                if getattr(world, "slowmo_ticks", 0) <= 0:
                    self.end_wait -= 1
                    if self.end_wait == 0:
                        world.stats_requested = "end"
            elif not self.solo_end and all(self._teams_alive(world)):
                # Keep watching, then both teams fielded again (slot keys):
                # a new fight on the same sheet — it can end again.
                self.over, self.winner = False, None
                self.had_battle = True
            return
        if not self.check_end:
            # Both teams standing at least once = a fight that can end.
            if not self.had_battle and all(self._teams_alive(world)):
                self.had_battle = True
            return
        alive = self._teams_alive(world)
        if all(alive):
            self.had_battle = True
            self.check_end = False
            return
        self.check_end = False
        if not self.had_battle:
            return
        standing = [t for t, a in enumerate(alive) if a]
        self.winner = standing[0] if len(standing) == 1 else -1
        self.over = True
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
        """Before the results window reads the sheet: every fielded / slotted
        fighter gets a row (one that dealt nothing shows an empty bar)."""
        for side in getattr(world, "sides", None) or []:
            for f in side.figures:
                self.record(f, world)
        for s in getattr(world, "slots", None) or []:
            if s.fig is not None:
                self.record(s.fig, world)

    def solo_over(self, world):
        """Solo's final KO (World.on_figure_death): the run is over."""
        self.over = True
        self.solo_end = True
        self.winner = None


def _n(v):
    v = float(v)
    if abs(v) >= 100 or abs(v - round(v)) < 0.05:
        return "{:,}".format(int(round(v)))
    return "%.1f" % v


fmt_num = _n


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
