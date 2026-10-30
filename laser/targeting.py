"""
Targeting — which enemy a fighter fights (FX Studio "Targeting", the
character-level pack.targeting).

Every "who is my enemy" read in the game goes through World.enemy_target /
World.target_index, so the chosen target drives everything: movement and
chasing, attacks and aiming, FX aimed at the target, and every target_*
trigger condition.  A Black Ox Effigy's taunt still overrides it.  Without
the setting (built-in characters, or Targeting off) it is the nearest
enemy, as it always was.

Settings (all optional, defaults in DEFAULTS):

  mode            nearest | farthest | lowest_hp | highest_hp | stick |
                  last_attacker | weighted
  hp_basis        pct (HP %) or amount (raw HP) for lowest / highest HP and
                  the weighted score's HP term
  fallback        the mode stick / last_attacker use when they have no one
                  (stick: before the first target, or once it falls;
                  last_attacker: nobody has hit it yet or they're gone)
  weights         weighted score sliders, -100..100 %: closeness, low HP,
                  attacking (mid attack), targets me (that enemy's own target
                  is this fighter), melee, ranged.  Each term is 0..1 across
                  the enemies on screen; the highest total wins.
  min_hold_ms     stay on a target at least this long before switching
  switch_margin_pct  switch only when the new pick scores this much better
                  (0..100 % of the score range)
  min_range_px / max_range_px  only enemies inside this band count (0 = no
                  limit); when none is, the nearest enemy
  ignore_blinked  skip enemies that are blinked out / invulnerable mid
                  dodge (when every enemy is, they all count)
  team            none | focus (prefer team-mates' targets) | spread
                  (prefer enemies no team-mate has), team_pct strength
  rules           [{logic, conditions, mode, hp_basis}]: the first rule
                  whose trigger conditions pass (the same conditions as
                  actions, read against this fighter's last tick) sets the
                  mode instead of `mode`

Snapshots only: the enemy list is the side's partner_figures with
partner_ids / partner_hp / partner_state / partner_melee / partner_gone /
partner_target (World.refresh_battle), so the two sides stay independent.
Identical in Solo and Battle; Solo has no enemies (the cursor).
"""

import copy

from . import config
from .actions import CONDITION_TYPES as CONDITIONS

TICK_MS = config.TICK_MS
MODES = ("nearest", "farthest", "lowest_hp", "highest_hp", "stick", "last_attacker", "weighted")
BASIC_MODES = ("nearest", "farthest", "lowest_hp", "highest_hp", "weighted")
HP_BASIS = ("pct", "amount")
TEAM = ("none", "focus", "spread")
WEIGHTS = dict(closeness=100.0, low_hp=0.0, attacking=0.0, targets_me=0.0, melee=0.0, ranged=0.0)
DEFAULTS = dict(enabled=False, mode="nearest", hp_basis="pct", fallback="nearest",
                weights=WEIGHTS, min_hold_ms=0.0, switch_margin_pct=0.0,
                min_range_px=0.0, max_range_px=0.0, ignore_blinked=True,
                team="none", team_pct=50.0, rules=[])
RULE_DEFAULTS = dict(logic="any", conditions=[], mode="farthest", hp_basis="pct")


def _norm_conds(raw):
    out = []
    for c in raw or []:
        t = (c or {}).get("type")
        if t in CONDITIONS:
            cc = dict(CONDITIONS[t])
            cc["not"] = False
            cc.update(c)
            out.append(cc)
    return out


def normalize(cfg):
    out = dict(cfg or {})
    for k, v in DEFAULTS.items():
        if k not in out:
            out[k] = copy.deepcopy(v)
    if out["mode"] not in MODES:
        out["mode"] = "nearest"
    if out["fallback"] not in BASIC_MODES:
        out["fallback"] = "nearest"
    if out["hp_basis"] not in HP_BASIS:
        out["hp_basis"] = "pct"
    if out["team"] not in TEAM:
        out["team"] = "none"
    w = dict(WEIGHTS)
    w.update({k: float(v) for k, v in (out.get("weights") or {}).items() if k in WEIGHTS})
    out["weights"] = w
    rules = []
    for r in out.get("rules") or []:
        rr = dict(RULE_DEFAULTS)
        rr.update(r or {})
        if rr["mode"] not in MODES:
            rr["mode"] = "nearest"
        if rr["hp_basis"] not in HP_BASIS:
            rr["hp_basis"] = "pct"
        rr["conditions"] = _norm_conds(rr.get("conditions"))
        rules.append(rr)
    out["rules"] = rules
    return out


def config_for(fig):
    """Normalised Targeting settings, or None (nearest enemy)."""
    mode = fig.mode
    if hasattr(mode, "_target_cfg"):
        return mode._target_cfg
    cfg = None
    char = getattr(mode, "character", None)
    if char and char.get("_package"):
        raw = (char.get("_fxkit") or {}).get("targeting")
        if isinstance(raw, dict):
            n = normalize(raw)
            if n.get("enabled"):
                cfg = n
    mode._target_cfg = cfg
    return cfg


class TargetState:
    __slots__ = ("target_id", "since", "tick", "index")

    def __init__(self):
        self.target_id = None   # id() of the enemy figure it is on
        self.since = 0          # world tick it picked that one
        self.tick = None        # cache: the tick `index` was chosen on
        self.index = -1


def state(fig):
    st = getattr(fig, "tgt", None)
    if st is None:
        st = TargetState()
        fig.tgt = st
    return st


def note_hit(fig, attacker):
    """`attacker` (an enemy Figure, or None) just landed a hit on fig."""
    if attacker is not None and fig is not None:
        fig.last_hit_by = id(attacker)


def nearest_index(world, fx, fy):
    best, bi = float("inf"), -1
    for i, f in enumerate(world.partner_figures or []):
        d = (f[0] - fx) ** 2 + (f[1] - fy) ** 2
        if d < best:
            best, bi = d, i
    return bi


def _get(lst, i, default=None):
    return lst[i] if lst is not None and 0 <= i < len(lst) else default


def _scores(world, fig, cands, mode, cfg, hp_basis):
    """{index: raw score} for `mode`, higher = better."""
    pf = world.partner_figures
    hp = getattr(world, "partner_hp", None) or []
    st = getattr(world, "partner_state", None) or []
    d = {i: ((pf[i][0] - fig.x) ** 2 + (pf[i][1] - fig.y) ** 2) ** 0.5 for i in cands}

    def hpv(i):
        if hp_basis == "amount":
            h = _get(hp, i)
            return float(h[0]) if h else 0.0
        s = _get(st, i)
        return float(s[0]) if s else 100.0

    if mode == "farthest":
        return d
    if mode == "lowest_hp":
        return {i: -hpv(i) for i in cands}
    if mode == "highest_hp":
        return {i: hpv(i) for i in cands}
    if mode == "weighted":
        w = cfg["weights"]
        melee = getattr(world, "partner_melee", None) or []
        tgts = getattr(world, "partner_target", None) or []
        me = id(fig)
        dl, dh = min(d.values()), max(d.values())
        hl = min(hpv(i) for i in cands)
        hh = max(hpv(i) for i in cands)
        out = {}
        for i in cands:
            close = 1.0 - ((d[i] - dl) / (dh - dl) if dh > dl else 0.0)
            low = 1.0 - ((hpv(i) - hl) / (hh - hl) if hh > hl else 0.0)
            s = _get(st, i)
            atk = 1.0 if (s and len(s) > 1 and s[1]) else 0.0
            tme = 1.0 if _get(tgts, i) == me else 0.0
            ml = 1.0 if _get(melee, i) else 0.0
            out[i] = (w["closeness"] * close + w["low_hp"] * low + w["attacking"] * atk
                      + w["targets_me"] * tme + w["melee"] * ml + w["ranged"] * (1.0 - ml)) / 100.0
        return out
    return {i: -d[i] for i in cands}     # nearest


def _normalized(sc):
    lo, hi = min(sc.values()), max(sc.values())
    if hi <= lo:
        return {i: 1.0 for i in sc}
    return {i: (v - lo) / (hi - lo) for i, v in sc.items()}


def _rule_mode(world, fig, cfg):
    """(mode, hp_basis) — the first passing rule's, else the base."""
    rules = cfg["rules"]
    if rules:
        r = getattr(fig, "act", None)
        ctx = getattr(r, "ctx", None) if r is not None else None
        if ctx is not None:
            for n, rule in enumerate(rules):
                if rule["conditions"] and r._conds_pass(fig, "@target:%d" % n, rule, ctx):
                    return rule["mode"], rule["hp_basis"]
    return cfg["mode"], cfg["hp_basis"]


def choose_index(world, fig):
    """Index into world.partner_figures of fig's target this tick (-1 = no
    enemies).  Cached per tick, so every read in one tick agrees."""
    pf = world.partner_figures or []
    if not pf:
        return -1
    cfg = config_for(fig)
    now = world.global_tick
    st = state(fig)
    if st.tick == now and 0 <= st.index < len(pf):
        return st.index
    ids = getattr(world, "partner_ids", None) or []
    if cfg is None:
        i = nearest_index(world, fig.x, fig.y)
    else:
        i = _choose(world, fig, cfg, st, ids, now)
    nid = _get(ids, i)
    if nid != st.target_id:
        st.target_id = nid
        st.since = now
    st.tick, st.index = now, i
    return i


def _choose(world, fig, cfg, st, ids, now):
    pf = world.partner_figures
    cands = list(range(len(pf)))
    if cfg["ignore_blinked"]:
        gone = getattr(world, "partner_gone", None) or []
        vis = [i for i in cands if not _get(gone, i, False)]
        if vis:
            cands = vis
    lo, hi = float(cfg["min_range_px"] or 0), float(cfg["max_range_px"] or 0)
    if lo > 0 or hi > 0:
        inr = []
        for i in cands:
            dd = ((pf[i][0] - fig.x) ** 2 + (pf[i][1] - fig.y) ** 2) ** 0.5
            if dd >= lo and (hi <= 0 or dd <= hi):
                inr.append(i)
        if not inr:
            return nearest_index(world, fig.x, fig.y)
        cands = inr
    cur = ids.index(st.target_id) if st.target_id in ids else -1
    if cur not in cands:
        cur = -1
    mode, basis = _rule_mode(world, fig, cfg)
    if mode == "stick":
        if cur >= 0:
            return cur
        mode = cfg["fallback"]
    elif mode == "last_attacker":
        la = getattr(fig, "last_hit_by", None)
        if la in ids and ids.index(la) in cands:
            return ids.index(la)
        mode = cfg["fallback"]
    sc = _normalized(_scores(world, fig, cands, mode, cfg, basis))
    # Team coordination: team-mates' current targets.
    if cfg["team"] != "none":
        mates = [getattr(getattr(f, "tgt", None), "target_id", None)
                 for f in (world.figures or []) if f is not fig]
        mates = [m for m in mates if m is not None]
        if mates:
            k = float(cfg["team_pct"]) / 100.0 * (1.0 if cfg["team"] == "focus" else -1.0)
            for i in cands:
                share = sum(1 for m in mates if m == _get(ids, i)) / float(len(mates))
                sc[i] += k * share
    best = max(cands, key=lambda i: (sc[i], -i))
    if cur >= 0 and best != cur:
        hold = int(float(cfg["min_hold_ms"] or 0) / TICK_MS)
        if now - st.since < hold:
            return cur
        if sc[best] - sc[cur] < float(cfg["switch_margin_pct"] or 0) / 100.0:
            return cur
    return best
