"""
Ally support: defend types, the guard bar and the dash to an ally
(Daniel 2026-11-18, first used by `tough`).  Solo and Battle run the same
code: everything here is driven from CombatSystem / the action runner /
ai.apply_hp_damage, which both modes share.

Defend types (FX Studio, per triggered action: action_settings[a].defend,
DEFEND_DEFAULTS; one type per action).  While an action with a type plays
(and, with Movement "Dash to ally", once the dash has arrived) it guards a
circle of radius_px round the fighter (x character scale; 0 = its own body,
BODY_PX).  Its team-mates standing inside that circle are protected too.
  block    hits on the defender / a team-mate inside the circle lose
           reduce_pct % of their damage; knockback x kb_keep_pct %
  deflect  enemy shots / FX entering the circle are knocked aside at their
           source (dodge parry code: Deflectable flags respected; a still FX
           such as a melee slash is cancelled); hurts = the deflected shot
           can damage the enemy.  What can't be deflected is blocked
           (reduce_pct)
  reflect  like deflect, but the shot flies back at whoever fired it (else
           the defender's target).  Counter: a hit that still lands (melee,
           contact, an unreflectable shot) is blocked (reduce_pct) and
           counter_pct % of its damage is dealt to the attacker
  absorb   absorb_pct % of every hit is soaked; heal_pct % of what was
           soaked heals; share_pct % of that heal goes to the team-mate
           protected (the one hit, else the one he dashed to), the rest to
           the defender
  cover    stands between the covered team-mate and the threat nearest to
           them (cover_px from the team-mate, re-placed every tick at
           follow_speed_pct % speed when follow is on) and catches every
           enemy shot / FX entering its circle (destroyed at the source);
           the defender takes the caught damage minus reduce_pct.  Body
           block only: a hit that lands on the team-mate itself is not
           redirected
Every defended hit drains the DEFENDER's guard by its damage x drain_pct %.

Guard bar (FX Studio "Guard bar (whole character)", pack.guard,
GUARD_DEFAULTS): max, refills regen_per_s after regen_delay_ms without a
drain; open_drain_pct % of the damage of hits taken while NOT defending
drains it too (0 = only defended hits).  At 0 it breaks: the defend playing
is cut, break_action (e.g. defend_recovery) plays as a stagger (open to
hits), and no defend action (any action with a defend type, or named
defend*) can start for lockout_ms; then the bar refills from
refill_on_break_pct %.  Drawn under the fighter's feet (show: always /
not_full / defending), sized from the body on show (width_pct /
height_pct / offset_pct of its height).

Ally support: condition "ally_threatened" (a team-mate within px of an
enemy FX / enemy / another team-mate, the team-mate at most max_px from the
fighter) remembers the most threatened team-mate; Movement "ally_dash"
(action_settings[a].ally, ALLY_DASH_DEFAULTS) dashes to it (between it and
its threat, or beside it), the action holding hold_frame until it arrives,
then the action plays and its defend type switches on.
"""

import copy
import math

from . import config

TICK_MS = config.TICK_MS
BODY_PX = 34.0                 # "body only" guard reach (x character scale)
LOOKAHEAD_TICKS = 2            # same look-ahead as the dodge parry
DEFEND_TYPES = ("", "block", "deflect", "reflect", "absorb", "cover")
THREAT_BY = ("fx", "enemy", "fx_or_enemy", "ally", "any")
DASH_PLACES = ("between", "beside", "onto")
GUARD_SHOW = ("not_full", "always", "defending")

DEFEND_DEFAULTS = dict(type="", radius_px=0.0, reduce_pct=70.0, kb_keep_pct=0.0, drain_pct=100.0,
                       hurts=True, counter_pct=50.0, absorb_pct=100.0, heal_pct=50.0, share_pct=0.0,
                       cover_px=46.0, follow=True, follow_speed_pct=180.0)
ALLY_DASH_DEFAULTS = dict(speed_pct=320.0, place="between", stop_px=46.0, max_ms=900.0,
                          hold_frame=0, afterimages=True)
GUARD_DEFAULTS = dict(enabled=True, max=100.0, regen_per_s=22.0, regen_delay_ms=1200.0,
                      open_drain_pct=0.0, lockout_ms=2500.0, break_action="defend_recovery",
                      refill_on_break_pct=30.0, show="not_full", width_pct=70.0, height_pct=7.0,
                      offset_pct=3.0)


def _fill(d, defaults):
    for k, v in defaults.items():
        if k not in d:
            d[k] = copy.deepcopy(v)
    return d


def _num(d, k, lo=None):
    try:
        v = float(d.get(k))
    except (TypeError, ValueError):
        v = float(DEFEND_DEFAULTS.get(k, ALLY_DASH_DEFAULTS.get(k, GUARD_DEFAULTS.get(k, 0))) or 0)
    if lo is not None:
        v = max(lo, v)
    d[k] = v
    return v


def normalize_defend(d):
    d = _fill(dict(d or {}), DEFEND_DEFAULTS)
    if d.get("type") not in DEFEND_TYPES:
        d["type"] = ""
    for k in ("radius_px", "reduce_pct", "kb_keep_pct", "drain_pct", "counter_pct", "absorb_pct",
              "heal_pct", "share_pct", "cover_px", "follow_speed_pct"):
        _num(d, k, 0.0)
    d["hurts"], d["follow"] = bool(d.get("hurts")), bool(d.get("follow"))
    return d


def normalize_ally(d):
    d = _fill(dict(d or {}), ALLY_DASH_DEFAULTS)
    if d.get("place") not in DASH_PLACES:
        d["place"] = "between"
    for k in ("speed_pct", "stop_px", "max_ms"):
        _num(d, k, 0.0)
    d["hold_frame"] = int(_num(d, "hold_frame", 0.0))
    d["afterimages"] = bool(d.get("afterimages"))
    return d


def normalize_guard(d):
    d = _fill(dict(d or {}), GUARD_DEFAULTS)
    if d.get("show") not in GUARD_SHOW:
        d["show"] = "not_full"
    for k in ("max", "regen_per_s", "regen_delay_ms", "open_drain_pct", "lockout_ms",
              "refill_on_break_pct", "width_pct", "height_pct"):
        _num(d, k, 0.0)
    _num(d, "offset_pct")
    d["max"] = max(1.0, d["max"])
    d["enabled"] = bool(d.get("enabled"))
    d["break_action"] = str(d.get("break_action") or "")
    return d


# ---------------------------------------------------------------- config
def _ticks(ms):
    return max(0, int(round(max(0.0, float(ms or 0)) / TICK_MS)))


def _settings(fig):
    from .fxkit import character_fx
    cfx = character_fx(fig.mode)
    return cfx.settings if cfx is not None else {}


def defend_cfg(fig, name):
    """The normalised defend settings of action `name`, or None when it
    has no defend type."""
    if not name:
        return None
    a = _settings(fig).get(name) or {}
    d = a.get("defend")
    if not isinstance(d, dict) or not d.get("type"):
        return None
    if not d.get("_n"):
        d.update(normalize_defend(d))
        d["_n"] = True
    return d


def ally_cfg(fig, name):
    a = _settings(fig).get(name) or {}
    d = a.get("ally")
    if not isinstance(d, dict) or not d.get("_n"):
        d = normalize_ally(d)
        d["_n"] = True
        a["ally"] = d
    return d


def config_for(fig):
    """Normalised guard bar settings, or None: the fighter has no guard bar
    (no defend type on any action, or the bar switched off)."""
    mode = fig.mode
    if hasattr(mode, "_guard_cfg"):
        return mode._guard_cfg
    cfg = None
    char = getattr(mode, "character", None)
    if char and char.get("_package"):
        pack = char.get("_fxkit") or {}
        typed = any(isinstance(v, dict) and (v.get("defend") or {}).get("type")
                    for v in (pack.get("action_settings") or {}).values())
        raw = pack.get("guard")
        if typed or isinstance(raw, dict):
            n = normalize_guard(raw if isinstance(raw, dict) else {})
            if n["enabled"]:
                cfg = n
    mode._guard_cfg = cfg
    return cfg


def is_defend_action(fig, name):
    """A defend action for the guard-break lockout: it has a defend type, or
    is named defend* (the break action itself never counts)."""
    if not name:
        return False
    cfg = config_for(fig)
    if cfg is not None and name == cfg.get("break_action"):
        return False
    return name.startswith("defend") or defend_cfg(fig, name) is not None


# ---------------------------------------------------------------- state
class GuardState:
    __slots__ = ("value", "last_drain", "broken", "broken_until", "pending_break", "ally", "threat",
                 "cand_tick", "dash_key", "dash_t0", "dash_ally", "arrived", "parries", "seen", "flash", "t")

    def __init__(self, cfg):
        self.value = float(cfg["max"]) if cfg else 100.0
        self.last_drain = -10 ** 9
        self.broken = False
        self.broken_until = 0
        self.pending_break = False
        self.ally = None          # the team-mate it supports (ally_threatened / dash)
        self.threat = None        # (x, y) of that team-mate's nearest threat
        self.cand_tick = -1
        self.dash_key = None      # runner.started of the action whose dash runs
        self.dash_t0 = 0
        self.dash_ally = None     # the team-mate this dash goes to (None = plays in place)
        self.arrived = True
        self.parries = 0
        self.seen = set()
        self.flash = 0            # ticks of hit flash on the bar
        self.t = 0                # world tick of the last guard tick (bar blink)


def state(fig):
    st = getattr(fig, "guard", None)
    if st is None:
        st = GuardState(config_for(fig))
        fig.guard = st
    return st


def reset(fig):
    fig.guard = None


def allows(fig, name):
    """False while the guard is broken and `name` is a defend action."""
    st = getattr(fig, "guard", None)
    return not (st is not None and st.broken and is_defend_action(fig, name))


def active_defend(fig):
    """(name, defend cfg) of the defend that guards right now, else None.
    A Dash-to-ally defend only guards once it has arrived."""
    r = getattr(fig, "act", None)
    if r is None or not r.playing or fig.personality.hp <= 0:
        return None
    d = defend_cfg(fig, r.playing)
    if d is None:
        return None
    st = getattr(fig, "guard", None)
    if st is not None and st.dash_key == r.started and not st.arrived:
        return None
    return r.playing, d


def defending(fig):
    return active_defend(fig) is not None


def _reach(fig, d):
    r = float(d.get("radius_px") or 0)
    return (r if r > 0 else BODY_PX) * fig.mode.body_scale()


def _mates(world, fig):
    from . import tempo
    return [m for m in tempo.team_mates(world, fig) if getattr(m, "bench_since", None) is None]


# ---------------------------------------------------------------- drain
def drain(fig, world, amount):
    """Take `amount` off fig's guard bar (no-op without one)."""
    cfg = config_for(fig)
    if cfg is None or amount <= 0 or world is None:
        return
    st = state(fig)
    if st.broken:
        return
    st.value = max(0.0, st.value - float(amount))
    st.last_drain = world.global_tick
    st.flash = 6
    if st.value <= 0.0:
        st.pending_break = True


def _heal(fig, amount):
    if amount <= 0:
        return
    p = fig.personality
    p.hp = min(float(p.max_hp), p.hp + amount)


def _find_fig(world, fid):
    for s in getattr(world, "sides", ()) or ():
        for f in s.figures:
            if id(f) == fid:
                return f
    return None


# ---------------------------------------------------------------- hits
def _protector(fig, world):
    """(defender, defend cfg) whose guard covers a hit on fig: fig's own
    active defend, else a team-mate's whose circle fig stands in (cover:
    body only, never a team-mate's hit)."""
    own = active_defend(fig)
    if own is not None:
        return fig, own[1]
    if world is None:
        return None
    best = None
    for m in _mates(world, fig):
        a = active_defend(m)
        if a is None or a[1]["type"] == "cover" or float(a[1].get("radius_px") or 0) <= 0:
            continue
        dd = math.hypot(m.x - fig.x, m.y - fig.y)
        if dd <= _reach(m, a[1]) and (best is None or dd < best[0]):
            best = (dd, m, a[1])
    return None if best is None else (best[1], best[2])


def on_hit(fig, world, amount, kind="melee"):
    """ai.apply_hp_damage, a blockable hit about to land on fig: the
    defend that protects it changes it.  Returns the damage that still
    lands (0 = negated)."""
    if amount <= 0:
        return amount
    pr = _protector(fig, world)
    if pr is None:
        cfg = config_for(fig)
        if cfg is not None and cfg["open_drain_pct"] > 0:
            drain(fig, world, amount * cfg["open_drain_pct"] / 100.0)
        return amount
    dfd, d = pr
    t = d["type"]
    drain(dfd, world, amount * d["drain_pct"] / 100.0)
    if t == "absorb":
        soak = amount * min(100.0, d["absorb_pct"]) / 100.0
        heal = soak * d["heal_pct"] / 100.0
        share = heal * min(100.0, d["share_pct"]) / 100.0
        to = fig if fig is not dfd else getattr(state(dfd), "ally", None)
        if to is not None and to is not dfd and getattr(to.transform, "init", False) and to.personality.hp > 0:
            _heal(to, share)
            _heal(dfd, heal - share)
        else:
            _heal(dfd, heal)
        return amount - soak
    if t == "cover" and fig is dfd:
        return amount * (1.0 - min(100.0, d["reduce_pct"]) / 100.0)
    if t == "cover":
        return amount
    left = amount * (1.0 - min(100.0, d["reduce_pct"]) / 100.0)
    if t == "reflect" and d["counter_pct"] > 0:
        att = _find_fig(world, getattr(fig, "last_hit_by", None))
        if att is not None and att.personality.hp > 0:
            from . import ai
            ai.apply_hp_damage(att, world, amount * d["counter_pct"] / 100.0, kind="melee")
    return left


def kb_mult(fig, world):
    """Knockback multiplier on fig from the defend protecting it."""
    pr = _protector(fig, world)
    if pr is None:
        return 1.0
    d = pr[1]
    if d["type"] == "cover" and pr[0] is not fig:
        return 1.0
    if d["type"] == "absorb":
        return max(0.0, 1.0 - min(100.0, d["absorb_pct"]) / 100.0)
    return max(0.0, d["kb_keep_pct"]) / 100.0


# ---------------------------------------------------------------- threats
def _shot_damage(s):
    from . import fxkit
    ref = s.ref
    try:
        if isinstance(ref, fxkit.RoundRef):
            return float((ref.inst.fx.get("battle") or {}).get("damage") or 1.0)
        if s.kind == "bullet":
            return float(getattr(ref, "damage", 1.0) or 1.0)
        return float((ref.fx.get("battle") or {}).get("damage") or 0.0)
    except Exception:
        return 1.0


def _gap(s, x, y):
    """Distance from (x, y) to shot s over its next LOOKAHEAD_TICKS (a beam:
    its whole line)."""
    from . import fxkit
    b = s.body
    if b[0] != b[2] or b[1] != b[3]:
        return fxkit.shot_nearest(s, x, y)[2]
    dx, dy = s.x - x, s.y - y
    mx, my = s.vx * LOOKAHEAD_TICKS, s.vy * LOOKAHEAD_TICKS
    mm = mx * mx + my * my
    k = max(0.0, min(1.0, -(dx * mx + dy * my) / mm)) if mm > 1e-9 else 0.0
    return math.hypot(dx + mx * k, dy + my * k)


def _enemies(world):
    if getattr(world, "battle_mode", False) and world.partner_figures:
        return [(pf[0], pf[1]) for pf in world.partner_figures]
    return [tuple(world.cursor)] if getattr(world, "cursor", None) else []


def _nearest_threat(world, who, by, exclude=()):
    """(gap, (x, y)) of the nearest threat of kind `by` to fighter `who`."""
    best = None
    if by in ("fx", "fx_or_enemy", "any"):
        for s in list(getattr(world, "enemy_shots", None) or []) + list(getattr(world, "enemy_area", None) or []):
            if s.dead:
                continue
            g = _gap(s, who.x, who.y)
            if best is None or g < best[0]:
                best = (g, (s.x, s.y))
    if by in ("enemy", "fx_or_enemy", "any"):
        for (ex, ey) in _enemies(world):
            g = math.hypot(ex - who.x, ey - who.y)
            if best is None or g < best[0]:
                best = (g, (ex, ey))
    if by in ("ally", "any"):
        for m in _mates(world, who):
            if m in exclude:
                continue
            g = math.hypot(m.x - who.x, m.y - who.y)
            if best is None or g < best[0]:
                best = (g, (m.x, m.y))
    return best


def cond_ally_threatened(fig, world, cond):
    """Condition "ally_threatened": a team-mate (not fig, at most max_px
    away; 0 = any) has a threat of kind `by` within px.  Remembers the most
    threatened one for Dash to ally / cover."""
    if world is None:
        return False
    px = float(cond.get("px", 120) or 0)
    mx = float(cond.get("max_px", 0) or 0)
    by = cond.get("by") if cond.get("by") in THREAT_BY else "fx_or_enemy"
    best = None
    for m in _mates(world, fig):
        if m.personality.hp <= 0:
            continue
        if mx > 0 and math.hypot(m.x - fig.x, m.y - fig.y) > mx:
            continue
        t = _nearest_threat(world, m, by, exclude=(fig,))
        if t is not None and t[0] <= px and (best is None or t[0] < best[0]):
            best = (t[0], m, t[1])
    if best is None:
        return False
    st = state(fig)
    st.ally, st.threat, st.cand_tick = best[1], best[2], world.global_tick
    return True


FRESH_TICKS = 20               # a dash only follows a recent ally_threatened pick


def _support_target(fig, world, fresh=False):
    """The team-mate fig supports now (remembered by the condition, else the
    one with the nearest threat), with its threat spot.  fresh: only a
    team-mate the condition picked within FRESH_TICKS (a defend triggered
    by something else then plays in place)."""
    st = state(fig)
    m = st.ally
    mates = _mates(world, fig)
    if fresh and world.global_tick - st.cand_tick > FRESH_TICKS:
        return None, None
    if m is None or m not in mates or m.personality.hp <= 0:
        if fresh:
            return None, None
        best = None
        for mm in mates:
            if mm.personality.hp <= 0:
                continue
            t = _nearest_threat(world, mm, "fx_or_enemy")
            if t is not None and (best is None or t[0] < best[0]):
                best = (t[0], mm)
        m = best[1] if best else None
        st.ally = m
    if m is None:
        return None, None
    t = _nearest_threat(world, m, "fx_or_enemy")
    st.threat = t[1] if t else st.threat
    return m, st.threat


def _spot(fig, m, threat, place, dist):
    """Where to stand for team-mate m: between it and its threat (dist px
    from m), beside it, or onto it."""
    if place == "onto":
        return m.x, m.y
    if place == "between" and threat is not None:
        dx, dy = threat[0] - m.x, threat[1] - m.y
        d = math.hypot(dx, dy)
        if d > 1e-6:
            k = min(dist, d * 0.5) / d
            return m.x + dx * k, m.y + dy * k
    side = -1.0 if fig.x < m.x else 1.0
    return m.x + side * dist, m.y


def _clamp(fig, x, y):
    return (max(20.0, min(fig.screen_w - 20.0, x)), max(20.0, min(fig.screen_h - 20.0, y)))


def _step_to(fig, x, y, speed):
    """Move fig toward (x, y) by speed px.  True once there."""
    from . import combat
    t = fig.transform
    dx, dy = x - t.x, y - t.y
    d = math.hypot(dx, dy)
    if d <= max(2.0, speed):
        t.x, t.y = _clamp(fig, x, y)
        return True
    t.x, t.y = _clamp(fig, t.x + dx / d * speed, t.y + dy / d * speed)
    if dx < -0.5:
        t.facing_left = True
    elif dx > 0.5:
        t.facing_left = False
    combat._apply_trail_update(fig, t, True, False)
    return False


def _speed(fig, runner, pct):
    from . import combat
    base = runner.base_speed if runner.base_speed is not None else fig.motion.speed
    return base * pct / 100.0 * combat.position_speed_scale(fig.x, fig.y, fig.screen_w, fig.screen_h)


# ---------------------------------------------------------------- dash
def dash_step(fig, world, runner, name, now):
    """Movement "ally_dash", one tick (from ActionRunner.update).  Returns
    True while it still dashes: the caller holds the action's frame."""
    from . import combat
    st = state(fig)
    a = ally_cfg(fig, name)
    if st.dash_key != runner.started:
        st.dash_key, st.dash_t0, st.arrived = runner.started, now, False
        st.dash_ally = _support_target(fig, world, fresh=True)[0]
    if st.arrived:
        return False
    m, threat = _support_target(fig, world) if st.dash_ally is not None else (None, None)
    if m is None or (fig.motion.bouncing or fig.motion.bounce_ending):
        st.arrived = True
        return False
    tx, ty = _spot(fig, m, threat, a["place"], a["stop_px"] * fig.mode.body_scale())
    there = _step_to(fig, tx, ty, _speed(fig, runner, a["speed_pct"]))
    fig.render.is_moving = not there
    if a["afterimages"] and (now - st.dash_t0) % 2 == 0:
        combat.spawn_afterimage(fig)
    if there or now - st.dash_t0 >= max(1, _ticks(a["max_ms"])):
        st.arrived = True
        if threat is not None:
            fig.transform.facing_left = threat[0] < fig.x
        return False
    return True


# ---------------------------------------------------------------- tick
def _catch(fig, world, d, st):
    """Deflect / reflect / cover: every enemy shot / FX inside the guard
    circle is taken at its source (the dodge parry path)."""
    from . import fxkit, dodge, retreat, ai, action_log
    t = d["type"]
    reach = _reach(fig, d)
    shots = getattr(world, "enemy_shots", None) or []
    area = getattr(world, "enemy_area", None) or []
    if st.seen:
        st.seen &= {id(s.ref) for s in shots} | {id(s.ref) for s in area}
    host = None
    mode = "block" if t == "cover" else "deflect"
    for s, still in [(s, False) for s in shots] + [(s, True) for s in area]:
        if s.dead or fxkit._shot_gone(s) or id(s.ref) in st.seen:
            continue
        if not fxkit.orb_takes(s, mode) or _gap(s, fig.x, fig.y) > reach:
            continue
        s.dead = True
        st.seen.add(id(s.ref))
        st.parries += 1
        dmg = _shot_damage(s)
        if still:
            s.ref.age = max(s.ref.age, s.ref.life)
            s.ref.dead = True
            dots = getattr(world, "collision_dots", None)
            if dots is not None:
                dots.append([s.x, s.y, 0])
        else:
            drv = getattr(fig, "fx", None)
            if drv is not None and host is None:
                host = fxkit._Host(drv, fig, world)
            vel = None
            if mode == "deflect":
                cfg = {"parry_result": "reflect" if t == "reflect" else "deflect"}
                vel = _parry_vel(fig, world, cfg, st, s)
            if host is not None:
                host.on_intercept(None, s, mode, vel, bool(d["hurts"]))
            else:
                dodge._kill_at_source(s)
        drain(fig, world, dmg * d["drain_pct"] / 100.0)
        if t == "cover" and dmg > 0:
            # Caught on the body: the defender takes it, minus its block.
            left = dmg * (1.0 - min(100.0, d["reduce_pct"]) / 100.0)
            if left > 0:
                ai.apply_hp_damage(fig, world, left, unblockable=True, _ua_checked=True, kind="fx")
        action_log.log("COMBAT", f"guard {t} shot={s.kind}{' (fx)' if still else ''} at=({fig.x:.0f},{fig.y:.0f})")


def _parry_vel(fig, world, cfg, st, s):
    from . import dodge

    class _S:
        parries = st.parries
    return dodge._parry_vel(fig, world, cfg, _S, s)


def tick(fig, world):
    """One tick for every fighter, after the action runner: guard bar
    refill / break, the active defend's catches and cover footwork."""
    cfg = config_for(fig)
    if cfg is None:
        return
    st = state(fig)
    now = world.global_tick
    st.t = now
    if st.flash > 0:
        st.flash -= 1
    r = getattr(fig, "act", None)
    if st.pending_break:
        st.pending_break = False
        st.broken = True
        st.broken_until = now + _ticks(cfg["lockout_ms"])
        st.value = 0.0
        from . import actions, action_log
        if r is not None and r.playing and is_defend_action(fig, r.playing) and r.forced is None:
            r._finish(fig, now)
        if cfg["break_action"]:
            actions.force_action(fig, world, cfg["break_action"])
        action_log.log("COMBAT", f"guard break at=({fig.x:.0f},{fig.y:.0f})")
    if st.broken:
        if now >= st.broken_until:
            st.broken = False
            st.value = cfg["max"] * min(100.0, cfg["refill_on_break_pct"]) / 100.0
            st.last_drain = now
        return
    if now - st.last_drain >= _ticks(cfg["regen_delay_ms"]) and st.value < cfg["max"]:
        st.value = min(cfg["max"], st.value + cfg["regen_per_s"] * TICK_MS / 1000.0)
    a = active_defend(fig)
    if a is None:
        return
    from . import blink, timefx
    if blink.gone(fig) or timefx.frozen(fig):
        return
    d = a[1]
    if d["type"] == "cover" and d["follow"] and not (fig.motion.bouncing or fig.motion.bounce_ending):
        m, threat = _support_target(fig, world)
        if m is not None:
            tx, ty = _spot(fig, m, threat, "between", d["cover_px"] * fig.mode.body_scale())
            _step_to(fig, tx, ty, _speed(fig, r, d["follow_speed_pct"]))
            if threat is not None:
                fig.transform.facing_left = threat[0] < fig.x
    if d["type"] in ("deflect", "reflect", "cover"):
        _catch(fig, world, d, st)


# ---------------------------------------------------------------- draw
_BOX = {}            # QPixmap.cacheKey() -> (feet centre x, top, bottom) of its opaque pixels
FEET_FRAC = 0.2      # the bottom fifth of the body = the feet (bar centre)


def _body_box(fr):
    """(feet centre x, top, bottom) of the frame's opaque pixels, frame px
    (cached per frame).  The feet centre keeps the bar steady when an arm
    or weapon reaches out."""
    key = fr.cacheKey()
    box = _BOX.get(key)
    if box is None:
        box = (fr.width() / 2.0, 0.0, float(fr.height()))
        try:
            from PyQt5.QtCore import QRect
            from PyQt5.QtGui import QRegion
            m = fr.mask()
            if not m.isNull():
                reg = QRegion(m)
                r = reg.boundingRect()
                if not r.isEmpty():
                    fh = max(1, int(round(r.height() * FEET_FRAC)))
                    feet = reg.intersected(QRegion(QRect(r.left(), r.bottom() + 1 - fh, r.width(), fh))).boundingRect()
                    fx = (feet.left() + feet.right() + 1) / 2.0 if not feet.isEmpty() else (r.left() + r.right() + 1) / 2.0
                    box = (fx, float(r.top()), float(r.bottom() + 1))
        except Exception:
            pass
        if len(_BOX) > 4000:
            _BOX.clear()
        _BOX[key] = box
    return box


def draw(p, fig, pscale):
    """The guard bar under the fighter's feet (Figure.draw): sized from the
    body on show (width_pct / height_pct / offset_pct of its height), so it
    grows and shrinks with the sprite."""
    cfg = config_for(fig)
    st = getattr(fig, "guard", None)
    if cfg is None or st is None:
        return
    full = st.value >= cfg["max"] - 1e-6 and not st.broken
    dfd = defending(fig)
    show = cfg["show"]
    if (show == "not_full" and full and not dfd) or (show == "defending" and not dfd and not st.broken):
        return
    fr = fig._current_frame()
    if fr is None or fr.isNull():
        return
    from PyQt5.QtCore import QRectF, Qt
    from PyQt5.QtGui import QColor, QPen
    ps = pscale or 1.0
    fx, t, b = _body_box(fr)
    body_h = max(4.0, (b - t) * ps)
    feet = fig.y + (b - fr.height() / 2.0) * ps
    cx = fig.x + (fx - fr.width() / 2.0) * ps
    w = max(6.0, body_h * cfg["width_pct"] / 100.0)
    bh = max(2.0, body_h * cfg["height_pct"] / 100.0)
    x0 = cx - w / 2.0
    y0 = feet + body_h * cfg["offset_pct"] / 100.0
    k = max(0.0, min(1.0, st.value / cfg["max"]))
    rad = bh / 2.0
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 170))
    p.drawRoundedRect(QRectF(x0 - 1, y0 - 1, w + 2, bh + 2), rad + 1, rad + 1)
    if st.broken:
        # Broken: blinking red, shrinking with the lockout left.
        left = max(0.0, min(1.0, (st.broken_until - st.t) / float(max(1, _ticks(cfg["lockout_ms"])))))
        p.setBrush(QColor(230, 50, 50, 235 if (st.t // 4) % 2 == 0 else 110))
        if left > 0:
            p.drawRoundedRect(QRectF(x0, y0, w * left, bh), rad, rad)
    else:
        if st.flash > 0:
            c = QColor(255, 255, 255)
        elif k > 0.5:
            c = QColor(90, 200, 255)
        elif k > 0.25:
            c = QColor(255, 190, 60)
        else:
            c = QColor(255, 80, 60)
        p.setBrush(c)
        if k > 0:
            p.drawRoundedRect(QRectF(x0, y0, w * k, bh), rad, rad)
        if dfd:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 210), 1.0))
            p.drawRoundedRect(QRectF(x0 - 1, y0 - 1, w + 2, bh + 2), rad + 1, rad + 1)
    p.restore()
