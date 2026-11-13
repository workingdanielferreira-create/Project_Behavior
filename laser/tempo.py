"""
Fight rhythm (Daniel 2026-11-13, step 1 of the team-play plan): the tempo
of a fight.  Three parts, Solo and Battle alike:

  * TEMPO — per fighter (FX Studio "Fight rhythm (whole character)",
    pack.fight_rhythm; image characters only, the built-in swordsman /
    runner are always left out).  Each fighter runs its own intent machine
    on seeded, uneven timing:

      neutral   spacing just outside its reach, swaying in / out, circling;
                tension builds (faster as the director heats up)
      feint     a fake: a dash in that cuts away (dash_in) or a fake
                retreat that turns into a dive (fake_retreat).  An enemy
                that bites (attacks / dodges / blinks) gets punished
      engage    a burst in (engage_speed_pct) to land the opener
      pressure  a string of string_min..string_max attacks whose gaps
                shrink from gap_start_ms to gap_end_ms (accelerando, with
                gap_jitter_pct of jitter so no two strings match)
      punish    the target is open (recovering from an attack, dazed,
                knocked back): snap onto it at punish_speed_pct, near-zero
                gaps, for punish_ms
      reset     back off reset_px at a seeded angle, breathe, then neutral
      wait      a melee fighter whose team already has every attack token
                on that target: flanks / circles / zones (wait_style, by
                role when "mixed") — never stands still

    Gating: normal attacks only start in engage / pressure / punish (and
    in wait for a non-melee fighter); `defend` is never gated, other
    triggered actions only when gate_triggered is on.  Movement: in Battle,
    a fighter WITHOUT a movement style (movement "auto"), or any fighter
    (movement "always"), moves by its intent; "speed_only" just scales
    speed.  Solo keeps the Solo default movement (which replaces every
    character's own movement), the intents still gate attacks / scale
    speed against the cursor.  Player control (F4) ignores tempo but still
    counts on the squad board and takes attack tokens.

  * DIRECTOR — one per world (Dust & Air section "director", world only):
    an intensity 0..1 pushed up by closing distance, hits, counters
    (dodges / negated hits), HP swings, low HP, KOs and long quiet spells,
    decaying back to calm on its own.  Phases calm < build_at <= build <
    burst_at (seeded jitter) -> burst for burst_s_min..max s, then it drops
    to after_burst_pct.  Fighters read it (director_pct): neutral shortens,
    feints / strings grow, resets shorten in a burst.  It never picks moves.

  * SQUAD BOARD — one per side (= team; Dust & Air section "team"): roles,
    each fighter's intent, callouts and MELEE ATTACK TOKENS: at most
    tokens_team1 / tokens_team2 fighters (0 = no limit) of that team may
    melee one target at once.  Same-side only: enemies are still seen only
    through the per-tick snapshots (partner_open is the one new field: the
    enemy is recovering / dazed), so the two sides stay independent.

Stats: feints / punishes / engages / longest string (laser/battlestats.py).
Wireframe: intent labels, token lines, the director bar (laser/wireframe.py).
Studio port + live preview: tools/fx/studio/tempo.js (check_parity.py).
"""

import copy
import math
import random

from . import config

TICK_MS = config.TICK_MS

INTENTS = ["neutral", "feint", "engage", "pressure", "punish", "reset", "wait"]
ATTACK_INTENTS = ("engage", "pressure", "punish")
PRESET_NAMES = ["custom", "berserker", "duelist", "trickster", "counter", "sniper"]
ROLES = ["auto", "vanguard", "striker", "flanker", "controller", "support"]
MOVES = ["auto", "always", "speed_only"]
WAITS = ["mixed", "flank", "circle", "zone"]
FEINTS = ["mixed", "dash_in", "fake_retreat"]
PHASES = ["calm", "build", "burst"]
ENUMS = {"preset": PRESET_NAMES, "role": ROLES, "movement": MOVES, "wait_style": WAITS, "feint_kind": FEINTS}

# Every setting with its default (FX Studio: TEMPO.DEFAULTS).
DEFAULTS = dict(
    enabled=False, preset="duelist", role="auto", movement="auto", wait_style="mixed",
    neutral_ms_min=700.0, neutral_ms_max=2200.0, spacing_px=60.0, sway_px=40.0,
    feint_pct=25.0, feint_kind="mixed", feint_ms=380.0,
    engage_speed_pct=175.0, engage_ms_max=1400.0,
    string_min=2.0, string_max=5.0, gap_start_ms=380.0, gap_end_ms=80.0, gap_jitter_pct=35.0,
    pressure_speed_pct=115.0,
    punish_pct=70.0, punish_range_px=280.0, punish_ms=900.0, punish_speed_pct=230.0,
    reset_ms_min=350.0, reset_ms_max=1100.0, reset_px=220.0,
    director_pct=100.0, aggression_pct=100.0, momentum_pct=35.0, gate_triggered=False,
)
# Number ranges (clamped on load; Studio fields use the same).
RANGES = dict(
    neutral_ms_min=[0, 20000], neutral_ms_max=[0, 20000], spacing_px=[-200, 2000], sway_px=[0, 600],
    feint_pct=[0, 100], feint_ms=[50, 5000], engage_speed_pct=[10, 1000], engage_ms_max=[100, 20000],
    string_min=[1, 30], string_max=[1, 30], gap_start_ms=[0, 5000], gap_end_ms=[0, 5000],
    gap_jitter_pct=[0, 100], pressure_speed_pct=[10, 1000],
    punish_pct=[0, 100], punish_range_px=[0, 3000], punish_ms=[50, 10000], punish_speed_pct=[10, 1000],
    reset_ms_min=[0, 20000], reset_ms_max=[0, 20000], reset_px=[0, 3000],
    director_pct=[0, 300], aggression_pct=[10, 400], momentum_pct=[0, 200],
)
# Temperament presets: the settings each one changes from DEFAULTS
# ("custom" changes nothing; picking a preset in the Studio writes these).
PRESETS = {
    "custom": {},
    "berserker": dict(neutral_ms_min=250.0, neutral_ms_max=900.0, feint_pct=8.0, engage_speed_pct=210.0,
                      string_min=4.0, string_max=8.0, gap_start_ms=260.0, gap_end_ms=50.0,
                      punish_pct=85.0, reset_ms_min=200.0, reset_ms_max=600.0, reset_px=140.0,
                      aggression_pct=140.0, wait_style="circle"),
    "duelist": {},
    "trickster": dict(feint_pct=60.0, feint_ms=420.0, neutral_ms_min=600.0, neutral_ms_max=1800.0,
                      string_min=2.0, string_max=4.0, gap_start_ms=340.0, gap_end_ms=90.0,
                      wait_style="flank", feint_kind="mixed"),
    "counter": dict(neutral_ms_min=1200.0, neutral_ms_max=3000.0, feint_pct=15.0, punish_pct=100.0,
                    punish_range_px=340.0, punish_speed_pct=260.0, string_min=2.0, string_max=3.0,
                    aggression_pct=70.0),
    "sniper": dict(spacing_px=220.0, neutral_ms_min=900.0, neutral_ms_max=2400.0, engage_speed_pct=130.0,
                   string_min=3.0, string_max=6.0, gap_start_ms=300.0, gap_end_ms=140.0,
                   wait_style="zone", reset_px=320.0, punish_pct=40.0),
}
# Role priority for attack tokens (lower = served first) and the wait
# style "mixed" picks for a role.
ROLE_ORDER = {"striker": 0, "vanguard": 1, "flanker": 2, "controller": 3, "support": 4}
ROLE_WAIT = {"vanguard": "circle", "flanker": "flank", "support": "zone", "controller": "circle"}

OPEN_MS = 260            # an enemy whose attack ended this recently is "open" (recovering)
PUNISH_OWN_MS = 700      # openings within this long of its own last landed hit are its own combo
PUNISH_FROM = ("neutral", "wait", "feint", "reset")   # intents a punish can cut in from
PUNISH_CD_MS = 1500      # after a punish ends, the next one waits this long
WHIFF_MS = 500           # an enemy attack that ended is a whiff only if it hit nothing of ours this recently
TOKEN_HOLD_TICKS = 3     # a token not refreshed for this long is free again
CALLOUT_MS = 1500        # callouts kept on the board this long
LOW_PCT = 0.15           # momentum decay per second
STRING_BURST_BONUS = 2   # pressure strings get this many more hits in a burst
# The live director (phase / intensity), for readers without the world
# (movement style phases, laser/movestyle.py).
CURRENT = {"phase": "calm", "intensity": 0.0}


def _ticks(ms):
    return max(1, int(round(float(ms) / TICK_MS)))


# ------------------------------------------------------------ settings
def normalize(raw):
    """A complete, range-checked Fight rhythm block (TEMPO.normalize)."""
    raw = raw if isinstance(raw, dict) else {}
    out = copy.deepcopy(DEFAULTS)
    for k, d in DEFAULTS.items():
        if k not in raw:
            continue
        v = raw[k]
        if isinstance(d, bool):
            out[k] = bool(v)
        elif k in ENUMS:
            out[k] = v if v in ENUMS[k] else d
        else:
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue
            if v != v:
                continue
            lo, hi = RANGES.get(k, [-1e9, 1e9])
            out[k] = max(float(lo), min(float(hi), v))
    return out


def config_for(fig):
    """Normalised Fight rhythm of an image character with it on, else None.
    The built-in fighters never have one."""
    mode = getattr(fig, "mode", None)
    if mode is None:
        return None
    if hasattr(mode, "_tempo_cfg"):
        return mode._tempo_cfg
    cfg = None
    char = getattr(mode, "character", None)
    if char and char.get("_package"):
        raw = (char.get("_fxkit") or {}).get("fight_rhythm")
        if isinstance(raw, dict):
            n = normalize(raw)
            if n.get("enabled"):
                cfg = n
    try:
        mode._tempo_cfg = cfg
    except AttributeError:
        pass
    return cfg


def _cfg(fig):
    """config_for, but never for a Mirror Legion copy or a Summoner
    construct (they share their owner's character): they keep playing as
    before and take no attack token."""
    cfg = config_for(fig)
    if cfg is None:
        return None
    from . import unique as _unique
    try:
        if _unique.is_clone(fig) or _unique.construct_anchor(fig) is not None:
            return None
    except Exception:
        pass
    return cfg


def _world_cfg(name):
    from . import worldfx
    return worldfx.WORLD.get(name) or worldfx.DEFAULTS.get(name) or {}


# ------------------------------------------------------------ director
class Director:
    """World intensity 0..1 and its phase (calm / build / burst)."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.intensity = 0.0
        self.phase = "calm"
        self.burst_left = 0
        self.rng = random.Random()
        self.burst_at = None          # this cycle's (jittered) burst threshold
        self.last = None              # last totals read from the stats sheet
        self.quiet = 0                # ticks since the last hit
        self.alive = 0                # fighters standing last tick
        self.history = []             # recent intensity samples (wireframe sparkline)
        CURRENT["phase"], CURRENT["intensity"] = "calm", 0.0

    def _threshold(self, c):
        j = float(c.get("burst_jitter_pct", 0)) / 100.0
        return max(0.05, min(1.0, float(c["burst_at"]) / 100.0 * (1.0 + self.rng.uniform(-j, j))))

    def step(self, world):
        c = _world_cfg("director")
        if not c.get("enabled", True):
            self.intensity, self.phase, self.burst_left = 0.0, "calm", 0
            CURRENT["phase"], CURRENT["intensity"] = "calm", 0.0
            return
        if self.burst_at is None:
            self.burst_at = self._threshold(c)
        dt = TICK_MS / 1000.0
        figs = [f for s in getattr(world, "sides", ()) for f in s.figures
                if getattr(f.transform, "init", False)]
        # Totals from the post-battle stats sheet (laser/battlestats.py):
        # hits, damage, dodges + negated hits, damage taken, KOs.
        tot = [0.0, 0.0, 0.0, 0.0, 0.0]
        maxhp = []
        st = getattr(world, "stats", None)
        for fs in (getattr(st, "fighters", None) or {}).values():
            tot[0] += fs.hits
            tot[1] += fs.dealt
            tot[2] += fs.dodges + fs.blocked
            tot[3] += fs.taken
            tot[4] += fs.kos
        for f in figs:
            maxhp.append(float(max(1, f.personality.max_hp)))
        ref = (sum(maxhp) / len(maxhp)) if maxhp else 100.0
        if self.last is None or any(t < l for t, l in zip(tot, self.last)):
            self.last = list(tot)          # first read / the sheet was reset
        d = [t - l for t, l in zip(tot, self.last)]
        self.last = list(tot)
        add = 0.0
        add += d[0] * float(c["hit_pct"]) / 100.0
        add += d[1] / ref * float(c["damage_pct"]) / 100.0
        add += d[2] * float(c["counter_pct"]) / 100.0
        add += d[3] / ref * float(c["hp_swing_pct"]) / 100.0
        add += d[4] * float(c["ko_pct"]) / 100.0
        alive = len(figs)
        if alive < self.alive:
            add += (self.alive - alive) * float(c["ko_pct"]) / 100.0 * 0.5
        self.alive = alive
        # Closing distance: the nearest pair of opposing fighters (Solo: a
        # fighter and the cursor).
        dmin = None
        sides = getattr(world, "sides", ())
        if getattr(world, "battle_mode", False) and len(sides) >= 2:
            for a in sides[0].figures:
                for b in sides[1].figures:
                    dd = math.hypot(a.x - b.x, a.y - b.y)
                    dmin = dd if dmin is None else min(dmin, dd)
        else:
            cx, cy = getattr(world, "cursor", (0.0, 0.0))
            for a in figs:
                dd = math.hypot(a.x - cx, a.y - cy)
                dmin = dd if dmin is None else min(dmin, dd)
        if dmin is not None and c["close_px"] > 0:
            k = max(0.0, 1.0 - dmin / float(c["close_px"]))
            add += k * float(c["close_pct_s"]) / 100.0 * dt
        # Low HP: anyone below low_hp_at % keeps the heat up.
        if any(100.0 * f.personality.hp / max(1e-6, f.personality.max_hp) <= float(c["low_hp_at"]) for f in figs):
            add += float(c["low_hp_pct_s"]) / 100.0 * dt
        # Quiet spell: tension builds by itself, so a burst always comes.
        if d[0] > 0 or d[2] > 0:
            self.quiet = 0
        else:
            self.quiet += 1
        if self.quiet * dt >= float(c["idle_after_s"]):
            add += float(c["idle_pct_s"]) / 100.0 * dt
        if self.phase == "burst":
            self.burst_left -= 1
            self.intensity = min(1.0, self.intensity + add * 0.25)
            if self.burst_left <= 0:
                self.intensity = float(c["after_burst_pct"]) / 100.0
                self.phase = "calm"
                self.burst_at = self._threshold(c)
        else:
            self.intensity = max(0.0, min(1.0, self.intensity + add - float(c["decay_pct_s"]) / 100.0 * dt))
            if self.intensity >= self.burst_at and figs:
                self.phase = "burst"
                lo, hi = float(c["burst_s_min"]), float(c["burst_s_max"])
                self.burst_left = _ticks(1000.0 * self.rng.uniform(min(lo, hi), max(lo, hi)))
            else:
                self.phase = "build" if self.intensity >= float(c["build_at"]) / 100.0 else "calm"
        self.history.append(self.intensity)
        del self.history[:-180]
        CURRENT["phase"], CURRENT["intensity"] = self.phase, self.intensity


def director(world):
    d = getattr(world, "director", None)
    if d is None:
        d = Director()
        world.director = d
    return d


# ------------------------------------------------------------ squad board
class Squad:
    """One side's (team's) shared board.  Written and read only by that
    side's own fighters."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.tokens = {}       # target id -> {fighter id: last refreshed tick}
        self.intents = {}      # fighter id -> (intent, tick)
        self.roles = {}        # fighter id -> role
        self.callouts = []     # (kind, fighter id, target id, tick)
        self.where = {}        # fighter id -> (x, y, hp_pct, tick)

    def cap(self, side_idx):
        c = _world_cfg("team")
        if not c.get("enabled", True):
            return 0
        n = int(c.get("tokens_team1" if side_idx == 0 else "tokens_team2", 2))
        return max(0, n)

    def _live(self, tid, now):
        held = self.tokens.get(tid) or {}
        for k in [k for k, t in held.items() if now - t > TOKEN_HOLD_TICKS]:
            del held[k]
        return held

    def holds(self, tid, fid, now):
        return fid in self._live(tid, now)

    def free(self, tid, side_idx, now, fid=None):
        cap = self.cap(side_idx)
        if cap <= 0:
            return True
        held = self._live(tid, now)
        return fid in held or len(held) < cap

    def claim(self, tid, fid, side_idx, now):
        if tid is None:
            return True
        cap = self.cap(side_idx)
        held = self._live(tid, now)
        if cap > 0 and fid not in held and len(held) >= cap:
            return False
        # A fighter holds a token on one target at a time.
        for other, h in self.tokens.items():
            if other != tid:
                h.pop(fid, None)
        self.tokens.setdefault(tid, {})[fid] = now
        return True

    def release(self, fid):
        for h in self.tokens.values():
            h.pop(fid, None)

    def note(self, fig, intent, now):
        self.intents[id(fig)] = (intent, now)
        p = fig.personality
        self.where[id(fig)] = (fig.x, fig.y, 100.0 * p.hp / max(1e-6, p.max_hp), now)

    def call(self, kind, fig, tid, now):
        self.callouts.append((kind, id(fig), tid, now))
        keep = now - _ticks(CALLOUT_MS)
        self.callouts = [c for c in self.callouts if c[3] > keep][-24:]


def squad(world, side_idx=None):
    """The board of side `side_idx` (default: the side being simulated)."""
    sides = getattr(world, "sides", None) or []
    if side_idx is None:
        side_idx = getattr(world, "side_idx", 0)
    if not (0 <= side_idx < len(sides)):
        return None
    s = sides[side_idx]
    sq = getattr(s, "squad", None)
    if sq is None:
        sq = Squad()
        s.squad = sq
    return sq


def side_of(world, fig):
    for i, s in enumerate(getattr(world, "sides", ()) or ()):
        if any(f is fig for f in s.figures):
            return i
    return getattr(world, "side_idx", 0)


def team_mates(world, fig):
    sides = getattr(world, "sides", None) or []
    i = side_of(world, fig)
    if not (0 <= i < len(sides)):
        return []
    return [f for f in sides[i].figures if f is not fig and getattr(f.transform, "init", False)]


def role_of(world, fig, cfg=None):
    """The fighter's role: its own setting, else auto (ranged = support;
    melee in team order: striker, flanker, vanguard, controller)."""
    cfg = cfg if cfg is not None else config_for(fig)
    if cfg is not None and cfg["role"] != "auto":
        return cfg["role"]
    if not fig.mode.uses_melee():
        return "support"
    order = ["striker", "flanker", "vanguard", "controller"]
    n = 0
    sides = getattr(world, "sides", None) or []
    i = side_of(world, fig)
    if 0 <= i < len(sides):
        for f in sides[i].figures:
            if f is fig:
                break
            if f.mode.uses_melee():
                n += 1
    return order[n % len(order)]


# ------------------------------------------------------------ per fighter
class TempoState:
    __slots__ = ("intent", "since", "until", "rng", "string_n", "string_done", "seen_attacks",
                 "seen_end", "momentum", "orbit_dir", "sway_ph", "sway_ms", "feint_kind",
                 "feint_bit", "open_seen", "reset_ang", "wait_style", "tid", "token", "role",
                 "best_string", "last_hp_drop", "far_ticks", "stamp", "last_landed", "punish_ready")

    def __init__(self):
        self.intent = "neutral"
        self.since = 0
        self.until = 0
        self.rng = random.Random()
        self.string_n = 0
        self.string_done = 0
        self.seen_attacks = None
        self.seen_end = None
        self.momentum = 0.0
        self.orbit_dir = 1.0 if self.rng.random() < 0.5 else -1.0
        self.sway_ph = self.rng.uniform(0, 2 * math.pi)
        self.sway_ms = self.rng.uniform(900, 2200)
        self.feint_kind = "dash_in"
        self.feint_bit = False         # the enemy reacted to the feint
        self.open_seen = False         # already punished this opening
        self.reset_ang = 0.0
        self.wait_style = "circle"
        self.tid = None                # id() of its target (Battle)
        self.token = False
        self.role = "striker"
        self.best_string = 0
        self.last_hp_drop = None
        self.far_ticks = 0
        self.stamp = None              # tick of the last think()
        self.last_landed = -10 ** 9    # tick it last landed a hit (its own openings don't count)
        self.punish_ready = 0          # no new punish before this tick


def state(fig):
    st = getattr(fig, "tempo", None)
    if st is None:
        st = TempoState()
        fig.tempo = st
    return st


def intent_of(fig):
    st = getattr(fig, "tempo", None)
    if st is None or _cfg(fig) is None:
        return None
    return st.intent


def _rand_ms(st, lo, hi, k=1.0):
    lo, hi = float(lo), float(hi)
    if hi < lo:
        lo, hi = hi, lo
    # Uneven: a skewed draw (two uniforms, one squared) so short and long
    # spells both happen and no two cycles match.
    u = st.rng.random()
    u = u * u if st.rng.random() < 0.5 else 1.0 - (1.0 - u) * (1.0 - u)
    return _ticks(max(0.0, (lo + (hi - lo) * u) * k))


def _stats(world, fig):
    s = getattr(world, "stats", None)
    if s is None:
        return None
    try:
        return s.record(fig, world)
    except Exception:
        return None


def _enter(fig, world, st, cfg, intent, now, I, burst):
    """Switch to `intent` and roll its timing."""
    prev = st.intent
    st.intent = intent
    st.since = now
    sq = squad(world, side_of(world, fig))
    fs = None
    if intent == "neutral" or intent == "wait":
        # Shorter as the director heats up; much shorter in a burst.
        k = (1.0 - 0.6 * I) * (0.45 if burst else 1.0) / max(0.25, _aggr(st, cfg))
        st.until = now + _rand_ms(st, cfg["neutral_ms_min"], cfg["neutral_ms_max"], k)
        if intent == "wait":
            st.until = now + max(_ticks(200), (st.until - now) // 2)
    elif intent == "feint":
        kind = cfg["feint_kind"]
        if kind == "mixed":
            kind = "dash_in" if st.rng.random() < 0.6 else "fake_retreat"
        st.feint_kind = kind
        st.feint_bit = False
        st.until = now + _rand_ms(st, cfg["feint_ms"] * 0.7, cfg["feint_ms"] * 1.3)
        fs = "feints"
    elif intent == "engage":
        st.until = now + _ticks(cfg["engage_ms_max"])
        lo, hi = int(cfg["string_min"]), int(cfg["string_max"])
        if hi < lo:
            lo, hi = hi, lo
        st.string_n = st.rng.randint(lo, hi) + (STRING_BURST_BONUS if burst else 0)
        st.string_done = 0
        fs = "engages"
    elif intent == "punish":
        st.until = now + _rand_ms(st, cfg["punish_ms"] * 0.8, cfg["punish_ms"] * 1.2)
        st.open_seen = True
        if st.string_n - st.string_done < 2:
            st.string_n = st.string_done + 2 + st.rng.randint(0, 2)
        fs = "punishes"
    elif intent == "reset":
        k = 0.5 if burst else 1.0
        st.until = now + _rand_ms(st, cfg["reset_ms_min"], cfg["reset_ms_max"], k)
        st.reset_ang = st.rng.uniform(-0.8, 0.8)
        st.orbit_dir = -st.orbit_dir if st.rng.random() < 0.5 else st.orbit_dir
        if prev in ("pressure", "punish", "engage"):
            st.best_string = max(st.best_string, st.string_done)
            s = _stats(world, fig)
            if s is not None:
                s.best_string = max(getattr(s, "best_string", 0), st.string_done)
    elif intent == "pressure":
        st.until = now + _ticks(8000)
    if fs is not None:
        s = _stats(world, fig)
        if s is not None:
            setattr(s, fs, getattr(s, fs, 0) + 1)
    if sq is not None:
        sq.note(fig, intent, now)
        if intent in ("engage", "punish", "feint"):
            sq.call(intent, fig, st.tid, now)


def _aggr(st, cfg):
    return float(cfg["aggression_pct"]) / 100.0 * (1.0 + float(cfg["momentum_pct"]) / 100.0 * st.momentum)


def _target_open(world, fig):
    """The target is open (Battle snapshot partner_open): 1 dazed / knocked
    back, 2 recovering from an attack, 0 not open."""
    if not (getattr(world, "battle_mode", False) and world.partner_figures):
        return 0
    i = world.target_index(fig) if hasattr(world, "target_index") else -1
    op = getattr(world, "partner_open", None) or []
    return int(op[i]) if 0 <= i < len(op) else 0


def _target_id(world, fig):
    if not (getattr(world, "battle_mode", False) and world.partner_figures):
        return "cursor"
    i = world.target_index(fig) if hasattr(world, "target_index") else -1
    ids = getattr(world, "partner_ids", None) or []
    return ids[i] if 0 <= i < len(ids) else None


def open_state(fig, now):
    """Snapshot value for the opponents: 1 = dazed / knocked back, 2 =
    recovering from an attack that just ended, 0 = not open."""
    m, p = fig.motion, fig.personality
    if m.bouncing or m.bounce_ending or getattr(p, "daze_ticks", 0) > 0:
        return 1
    r = getattr(fig, "act", None)
    if r is not None and r.playing is None and now - r.last_attack_end <= _ticks(OPEN_MS):
        return 2
    return 0


def think(fig, world, runner, ctx, now):
    """ActionRunner.update, before anything starts: advance the intent.
    Returns the TempoState, or None (no Fight rhythm: nothing gated)."""
    cfg = _cfg(fig)
    if cfg is None:
        return None
    st = state(fig)
    if st.stamp == now:
        return st
    st.stamp = now
    d = director(world)
    I = max(0.0, min(1.0, d.intensity * float(cfg["director_pct"]) / 100.0))
    burst = d.phase == "burst" and cfg["director_pct"] > 0
    side_idx = side_of(world, fig)
    sq = squad(world, side_idx)
    st.role = role_of(world, fig, cfg)
    st.tid = _target_id(world, fig)
    # Momentum: landed hits raise it, hits taken lower it; drifts back to 0.
    if ctx.get("landed"):
        st.momentum = min(1.0, st.momentum + 0.15 * ctx["landed"])
        st.last_landed = now
    drops = runner.hp_drops
    if drops and drops[-1][0] == now and st.last_hp_drop != now:
        st.last_hp_drop = now
        st.momentum = max(-1.0, st.momentum - 0.2)
    st.momentum *= 1.0 - LOW_PCT * TICK_MS / 1000.0
    if st.seen_attacks is None:
        st.seen_attacks = runner.attack_count
        st.seen_end = runner.last_attack_end
        _enter(fig, world, st, cfg, "neutral", now, I, burst)
    dist = ctx["dist"]
    from . import actions as _actions
    reach = _actions.attack_range(fig, "attack_normal", now)
    melee = bool(fig.mode.uses_melee())
    # Attacks started / ended since last tick.
    started = runner.attack_count - st.seen_attacks
    st.seen_attacks = runner.attack_count
    ended = runner.last_attack_end != st.seen_end
    st.seen_end = runner.last_attack_end
    # Openings: a fresh one can be punished once.  Not one its own hits just
    # made (that is its string going on), and not mid-string.
    op = _target_open(world, fig)
    took = any(now - tk <= _ticks(WHIFF_MS) for (tk, _d) in runner.hp_drops)
    is_open = bool(op == 1 or (op == 2 and not took)) and now - st.last_landed > _ticks(PUNISH_OWN_MS)
    if not is_open:
        st.open_seen = False
    can_punish = (is_open and not st.open_seen and now >= st.punish_ready
                  and dist <= float(cfg["punish_range_px"]) * fig.mode.body_scale()
                  and st.intent in PUNISH_FROM)
    if can_punish:
        st.open_seen = True
        if st.rng.random() * 100.0 < float(cfg["punish_pct"]) * (0.7 + 0.6 * I):
            if not melee or sq is None or sq.free(st.tid, side_idx, now, id(fig)):
                _enter(fig, world, st, cfg, "punish", now, I, burst)
    it = st.intent
    if it in ("neutral", "wait"):
        token_ok = (not melee) or sq is None or sq.free(st.tid, side_idx, now, id(fig))
        # Walked into reach: an aggressive fighter takes the chance.
        if (token_ok and dist <= reach and (now - st.since) % _ticks(200) == 0
                and st.rng.random() < 0.35 * _aggr(st, cfg) * (0.6 + I)):
            _enter(fig, world, st, cfg, "engage", now, I, burst)
        elif now >= st.until:
            if not token_ok:
                ws = cfg["wait_style"]
                if ws == "mixed":
                    ws = ROLE_WAIT.get(st.role) or st.rng.choice(["flank", "circle", "zone"])
                st.wait_style = ws
                _enter(fig, world, st, cfg, "wait", now, I, burst)
            elif st.rng.random() * 100.0 < float(cfg["feint_pct"]) * (0.7 + 0.8 * I):
                _enter(fig, world, st, cfg, "feint", now, I, burst)
            else:
                _enter(fig, world, st, cfg, "engage", now, I, burst)
    elif it == "feint":
        ts = ctx.get("tgt_state")
        if ts and ts[1]:
            st.feint_bit = True       # it bit: attacked into the fake
        gone = False
        i = world.target_index(fig) if getattr(world, "battle_mode", False) and hasattr(world, "target_index") else -1
        pg = getattr(world, "partner_gone", None) or []
        if 0 <= i < len(pg) and pg[i]:
            st.feint_bit = True       # it dodged / blinked away from nothing
            gone = True
        if now >= st.until or gone:
            if st.feint_bit and st.rng.random() * 100.0 < float(cfg["punish_pct"]):
                _enter(fig, world, st, cfg, "punish", now, I, burst)
            elif st.feint_kind == "fake_retreat":
                _enter(fig, world, st, cfg, "engage", now, I, burst)
            else:
                _enter(fig, world, st, cfg, "neutral", now, I, burst)
                st.until = st.since + max(_ticks(150), (st.until - st.since) // 3)
    elif it == "engage":
        if started > 0:
            st.string_done += started
            _enter(fig, world, st, cfg, "pressure", now, I, burst)
        elif now >= st.until:
            _enter(fig, world, st, cfg, "reset", now, I, burst)
    elif it in ("pressure", "punish"):
        if started > 0:
            st.string_done += started
        far = dist > reach * 2.5
        st.far_ticks = st.far_ticks + 1 if far else 0
        # Combo broken: two hits taken in half a second.
        recent = sum(1 for (tk, _d) in runner.hp_drops if now - tk <= _ticks(500))
        if it == "punish" and now >= st.until:
            st.punish_ready = now + _ticks(PUNISH_CD_MS)
            _enter(fig, world, st, cfg, "pressure", now, I, burst)
        elif (st.string_done >= st.string_n and runner.playing is None) or st.far_ticks > _ticks(600) or recent >= 2:
            _enter(fig, world, st, cfg, "reset", now, I, burst)
    elif it == "reset":
        if now >= st.until:
            _enter(fig, world, st, cfg, "neutral", now, I, burst)
    # Uneven, accelerating gaps inside a string (and near-zero in a punish).
    if ended and st.intent in ("pressure", "punish", "engage"):
        from . import unique as _unique
        u = min(1.0, st.string_done / max(1.0, float(st.string_n)))
        g0, g1 = float(cfg["gap_start_ms"]), float(cfg["gap_end_ms"])
        gap = g0 + (g1 - g0) * (u ** 0.7)
        if st.intent == "punish":
            gap = min(gap, g1) * 0.5
        if burst:
            gap *= 0.7
        j = float(cfg["gap_jitter_pct"]) / 100.0
        gap *= 1.0 + st.rng.uniform(-j, j)
        runner.gap_until = _unique.cd_now(fig, now) + int(max(0.0, gap) / TICK_MS)
    # Squad board: intent, token.
    if sq is not None:
        if melee and st.intent in ATTACK_INTENTS:
            st.token = sq.claim(st.tid, id(fig), side_idx, now)
            if not st.token and st.intent != "punish":
                ws = cfg["wait_style"]
                if ws == "mixed":
                    ws = ROLE_WAIT.get(st.role) or st.rng.choice(["flank", "circle", "zone"])
                st.wait_style = ws
                _enter(fig, world, st, cfg, "wait", now, I, burst)
        else:
            st.token = not melee
            sq.release(id(fig))
        sq.note(fig, st.intent, now)
        sq.roles[id(fig)] = st.role
    return st


def note_player(fig, world, ctx, now):
    """Player control (F4): no tempo, but it is on the squad board and takes
    a melee token while it is in reach of its target."""
    side_idx = side_of(world, fig)
    sq = squad(world, side_idx)
    if sq is None:
        return
    from . import actions as _actions
    tid = _target_id(world, fig)
    c = _world_cfg("team")
    reach = _actions.attack_range(fig, "attack_normal", now) * float(c.get("token_range_pct", 160)) / 100.0
    if fig.mode.uses_melee() and ctx["dist"] <= reach:
        sq.claim(tid, id(fig), side_idx, now)
    else:
        sq.release(id(fig))
    sq.note(fig, "player", now)
    sq.roles[id(fig)] = "player"


def allows_attack(fig):
    """May a normal attack start now?  True without Fight rhythm."""
    cfg = _cfg(fig)
    st = getattr(fig, "tempo", None)
    if cfg is None or st is None:
        return True
    if st.intent in ATTACK_INTENTS:
        return True
    # A ranged fighter keeps zoning while it waits for an opening.
    return st.intent == "wait" and not fig.mode.uses_melee()


def allows_triggered(fig, name):
    cfg = _cfg(fig)
    st = getattr(fig, "tempo", None)
    if cfg is None or st is None or not cfg["gate_triggered"] or name == "defend":
        return True
    return st.intent in ATTACK_INTENTS


def speed_mult(fig):
    cfg = _cfg(fig)
    st = getattr(fig, "tempo", None)
    if cfg is None or st is None:
        return 1.0
    it = st.intent
    if it == "engage":
        return float(cfg["engage_speed_pct"]) / 100.0
    if it == "punish":
        return float(cfg["punish_speed_pct"]) / 100.0
    if it == "pressure":
        return float(cfg["pressure_speed_pct"]) / 100.0
    if it == "feint":
        return float(cfg["engage_speed_pct"]) / 100.0 * 1.1
    if it == "reset":
        return 1.2
    return 1.0


def moves(fig):
    """Does the intent drive this fighter's movement (Battle)?"""
    cfg = _cfg(fig)
    if cfg is None or getattr(fig, "tempo", None) is None:
        return False
    if cfg["movement"] == "always":
        return True
    if cfg["movement"] == "speed_only":
        return False
    from . import movestyle
    return movestyle.cfg(fig) is None


def move_target(fig, world):
    """Battle: where the intent moves the fighter this tick, or None."""
    if not moves(fig):
        return None
    if not (getattr(world, "battle_mode", False) and world.partner_figures):
        return None
    cfg = config_for(fig)
    st = fig.tempo
    ex, ey = world.enemy_target(fig)
    dx, dy = fig.x - ex, fig.y - ey
    d = math.hypot(dx, dy)
    if d < 1e-3:
        dx, dy, d = (1.0 if fig.transform.facing_left else -1.0), 0.0, 1.0
    ux, uy = dx / d, dy / d                # from the target out to the fighter
    from . import actions as _actions
    from . import ai as _ai
    bs = fig.mode.body_scale()
    now = getattr(world, "global_tick", 0)
    reach = _actions.attack_range(fig, "attack_normal", now)
    it = st.intent

    def ring(radius, lead):
        a = math.atan2(uy, ux) + lead * st.orbit_dir
        return ex + math.cos(a) * radius, ey + math.sin(a) * radius

    if it == "neutral":
        sway = float(cfg["sway_px"]) * bs * math.sin(st.sway_ph + 2 * math.pi * now * TICK_MS / st.sway_ms)
        r = max(10.0, reach + float(cfg["spacing_px"]) * bs + sway)
        if st.rng.random() < 0.004:
            st.orbit_dir = -st.orbit_dir
        tx, ty = ring(r, 0.35)
    elif it == "wait":
        ws = st.wait_style
        if ws == "flank":
            i = world.target_index(fig) if hasattr(world, "target_index") else -1
            fc = getattr(world, "partner_facing", None) or []
            back = 1.0 if (0 <= i < len(fc) and fc[i]) else -1.0     # behind = opposite the way it faces
            tx, ty = ex + back * (reach + 40.0 * bs), ey + 20.0 * bs * st.orbit_dir
        elif ws == "zone":
            r = max(reach * 1.6, 300.0 * bs)
            tx, ty = ring(r, 0.15)
        else:
            tx, ty = ring(max(reach * 1.4, reach + 90.0 * bs), 0.5)
    elif it == "feint":
        u = (now - st.since) / max(1.0, float(st.until - st.since))
        if st.feint_kind == "fake_retreat":
            tx, ty = ex + ux * (d + 160.0 * bs), ey + uy * (d + 160.0 * bs)
        elif u < 0.6 and d > reach * 1.15:
            tx, ty = ex + ux * reach * 1.1, ey + uy * reach * 1.1     # in fast, stop just short
        else:
            tx, ty = ring(reach * 1.6, 1.1)                          # cut away sideways
    elif it in ("engage", "punish", "pressure"):
        r = reach * 0.5
        tx, ty = ex + ux * r, ey + uy * r
    elif it == "reset":
        a = math.atan2(uy, ux) + st.reset_ang
        r = d + float(cfg["reset_px"]) * bs
        tx, ty = ex + math.cos(a) * r, ey + math.sin(a) * r
    else:
        return None
    rx, ry = _ai._wall_repulsion(fig)
    return tx + rx, ty + ry


def reset_world(world):
    """apply_roster(reset=True): fresh boards and director."""
    for s in getattr(world, "sides", None) or []:
        sq = getattr(s, "squad", None)
        if sq is not None:
            sq.reset()
    d = getattr(world, "director", None)
    if d is not None:
        d.reset()
    for s in getattr(world, "sides", None) or []:
        for f in s.figures:
            if getattr(f, "tempo", None) is not None:
                f.tempo = None


def step(world):
    """Overlay._tick, after the stats sheet: the director's tick."""
    director(world).step(world)


# ------------------------------------------------------------ conditions
def cond_true(fig, world, t, cond, ctx):
    """FX Studio trigger conditions of the Fight rhythm group
    (actions.CONDITION_TYPES)."""
    if t == "tempo_intent":
        return intent_of(fig) == str(cond.get("intent") or "engage")
    if t == "director_phase":
        return director(world).phase == str(cond.get("phase") or "burst")
    if t == "director_above":
        return director(world).intensity * 100.0 >= float(cond.get("pct", 60))
    if t == "has_token":
        if not fig.mode.uses_melee():
            return True
        sq = squad(world, side_of(world, fig))
        if sq is None:
            return True
        return sq.holds(_target_id(world, fig), id(fig), world.global_tick)
    if t == "target_open":
        return _target_open(world, fig) > 0
    mates = team_mates(world, fig)
    if t == "partner_intent":
        want = str(cond.get("intent") or "pressure")
        sq = squad(world, side_of(world, fig))
        if sq is None:
            return False
        now = world.global_tick
        return any((sq.intents.get(id(m)) or ("", -10 ** 9))[0] == want
                   and now - sq.intents[id(m)][1] <= 2 for m in mates)
    if t == "partner_within":
        px = float(cond.get("px", 200))
        return any(math.hypot(m.x - fig.x, m.y - fig.y) <= px for m in mates)
    if t == "partner_hp_below":
        pct = float(cond.get("pct", 40))
        return any(100.0 * m.personality.hp / max(1e-6, m.personality.max_hp) <= pct for m in mates)
    if t == "outnumbered":
        if not (getattr(world, "battle_mode", False) and world.partner_figures):
            return False
        return len(mates) + 1 < len(world.partner_figures)
    return False


COND_TYPES = ("tempo_intent", "director_phase", "director_above", "has_token", "target_open",
              "partner_intent", "partner_within", "partner_hp_below", "outnumbered")
