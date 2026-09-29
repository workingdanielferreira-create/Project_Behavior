"""
Blink — character-level teleports.  Set in FX Studio ("Blink (whole
character)", pack.blink) for image characters (Rig Forge + FX Studio).
Characters without it are untouched.  (Not the built-in swordsman's
blink-dodge / blink-warp in combat.py: that is a separate JSON block.)

pack.blink = {"enabled": bool, "entries": [entry, ...]}.  Each entry is one
blink with its own trigger conditions (ANY / ALL), cooldown and settings.
The entries are checked in order; the first whose conditions pass starts,
and only one blink runs at a time.

An entry's `action`:

  ""  (none)  it vanishes the moment it triggers.  Freeze on: gone for
              freeze_ms, its animation stopped.  Freeze off: gone for
              gone_ms ("Teleport speed"), its animation running hidden.
  an action   the action starts when the entry triggers (cutting into an
              attack or locomotion, never into another triggered action).
              It plays up to start_frame (S), where the fighter vanishes.
              Freeze on:  the animation holds on S for freeze_ms, then
                          jumps to end_frame (E): it reappears and plays on
                          from E (the frames between are skipped, FX in
                          them included).
              Freeze off: frames S..E play while hidden; it reappears on E
                          and plays on.
              end_frame -1 = the last frame.  If the action is cut off
              before S, the blink is dropped (the cooldown still starts).

It reappears proximity_px from the landing anchor:

  anchor     "target"  measured from the target (nearest enemy in Battle,
                       the cursor in Solo), where it is when the fighter
                       reappears
             "self"    measured from the spot the fighter vanished from
  direction  "behind"  the target's back: opposite the way it faces (Solo:
                       the far side from the fighter)
             "front"   the side the target faces (Solo: the fighter's side)
             "toward"  along the line from the fighter to the target
             "away"    along the line from the target to the fighter
             "random"  any direction
             "angle"   angle_deg from the fighter -> target line (0 = toward,
                       180 = away, positive = clockwise on screen)

While gone the fighter is invisible and untouchable: it takes no hits,
knockback or body contact, its body-bound FX (attached / orbit / weapon)
are hidden and deal no hits, and no new FX spawn.  Shots already in flight
keep flying.  It doesn't move.

An entry can start again cooldown_ms after the fighter reappears.  Every
reappearance is recorded as "blink" in the action history, so an action's
after_actions condition can follow it (e.g. "blink" -> attack_special).

Conditions: every action trigger condition (hp_below, attacks_made,
hits_taken, target_within, target_beyond, hit_by_fx, fx_near,
bullet_deflected, after_actions; evaluated by the fighter's ActionRunner
exactly as for its actions, under the name "__blink__:<entry id>") plus
projectile_count (count or more enemy projectiles in the air at once).

Driven from CombatSystem for every figure (tick() before the action runner,
after_action() right after it), so Solo and Battle run the same code.  Solo
has no enemy projectiles, and the cursor has no facing.
"""

import copy
import math

from . import config

NAME = "__blink__"      # ActionRunner counter key prefix for blink conditions
HISTORY_NAME = "blink"  # what a blink adds to the action history

ENTRY_DEFAULTS = dict(id="", name="Blink", enabled=True, action="", start_frame=0, end_frame=-1,
                      freeze=True, freeze_ms=300.0, gone_ms=300.0, anchor="target",
                      direction="behind", angle_deg=0.0, proximity_px=60.0,
                      flash=True, cooldown_ms=3000.0, logic="any", conditions=[])
CONDITIONS = {"hp_below": dict(pct=50.0, repeat=False),
              "attacks_made": dict(count=3),
              "hits_taken": dict(count=3),
              "target_within": dict(px=80.0),
              "target_beyond": dict(px=200.0),
              "hit_by_fx": dict(tags=""),
              "fx_near": dict(tags="", px=60.0),
              "bullet_deflected": dict(),
              "after_actions": dict(sequence=""),
              "projectile_count": dict(count=5)}
ANCHORS = ("target", "self")
DIRECTIONS = ("behind", "front", "toward", "away", "random", "angle")
MARGIN_PX = 20.0        # keep the landing spot this far inside the screen


def normalize_entry(e, i=0):
    out = dict(e or {})
    for k, v in ENTRY_DEFAULTS.items():
        if k not in out:
            out[k] = copy.deepcopy(v)
    if not out.get("id"):
        out["id"] = "B%d" % i
    if out.get("anchor") not in ANCHORS:
        out["anchor"] = ENTRY_DEFAULTS["anchor"]
    if out.get("direction") not in DIRECTIONS:
        out["direction"] = ENTRY_DEFAULTS["direction"]
    out["action"] = str(out.get("action") or "")
    conds = []
    for c in out.get("conditions") or []:
        t = (c or {}).get("type")
        if t in CONDITIONS:
            cc = dict(CONDITIONS[t])
            cc.update(c)
            conds.append(cc)
    out["conditions"] = conds
    return out


def normalize(cfg):
    """pack.blink -> {"enabled", "entries"}.  The first version kept one
    blink's settings directly in pack.blink; that becomes entry 1 (no
    action, its gone_ms is also its freeze time)."""
    cfg = dict(cfg or {})
    if "entries" not in cfg and ("conditions" in cfg or "gone_ms" in cfg):
        old = dict(cfg)
        old.pop("enabled", None)
        old.setdefault("freeze_ms", old.get("gone_ms", ENTRY_DEFAULTS["gone_ms"]))
        cfg = {"enabled": bool(cfg.get("enabled")), "entries": [old]}
    return {"enabled": bool(cfg.get("enabled", False)),
            "entries": [normalize_entry(e, i) for i, e in enumerate(cfg.get("entries") or [])]}


def config_for(fig):
    """Normalised blink settings for fig ({"entries": [...]} holding only the
    enabled entries that have conditions), or None when it has none."""
    mode = fig.mode
    if hasattr(mode, "_fxblink_cfg"):
        return mode._fxblink_cfg
    cfg = None
    char = getattr(mode, "character", None)
    if char and char.get("_package"):
        raw = (char.get("_fxkit") or {}).get("blink")
        if isinstance(raw, dict):
            n = normalize(raw)
            live = [e for e in n["entries"] if e.get("enabled", True) and e["conditions"]]
            if n["enabled"] and live:
                cfg = {"entries": live}
    mode._fxblink_cfg = cfg
    return cfg


class BlinkState:
    __slots__ = ("phase", "entry", "timed", "ticks_left", "x0", "y0", "cooldown_until")

    def __init__(self):
        self.phase = None           # None | "pre" (action playing up to S) | "gone"
        self.entry = None
        self.timed = False          # gone ends on a countdown (else at frame E)
        self.ticks_left = 0
        self.x0 = self.y0 = 0.0
        self.cooldown_until = {}    # entry id -> world.global_tick


def gone(fig):
    """True while fig has blinked out (invisible, untouchable)."""
    st = getattr(fig, "blink", None)
    return bool(st is not None and st.phase == "gone")


def frozen(fig):
    """True while fig is gone with freeze on (its action clock stops)."""
    st = getattr(fig, "blink", None)
    return bool(st is not None and st.phase == "gone" and st.entry["freeze"])


def _ticks(ms):
    return max(0, int(round(max(0.0, float(ms or 0)) / config.TICK_MS)))


def _hp_pct(fig):
    p = fig.personality
    return 100.0 * p.hp / max(1e-6, p.max_hp)


def _key(e):
    return NAME + ":" + str(e["id"])


def _ctx(fig, world, tx, ty):
    """The same inputs ActionRunner.update gives its conditions this tick."""
    from . import actions
    r = actions.runner(fig)
    return r, {"target": (tx, ty),
               "dist": math.hypot(tx - fig.x, ty - fig.y),
               "hp_pct": _hp_pct(fig),
               "hit_tags": list(r.hit_tags) if r is not None else [],
               "deflected": bool(fig.combat.parrying) and not (r is not None and r.was_parrying),
               "enemy_fx": getattr(world, "enemy_fx", None) or []}


def _cond_true(fig, r, e, c, ctx, world):
    if c["type"] == "projectile_count":
        return len(getattr(world, "enemy_shots", None) or []) >= max(1, int(c.get("count", 5)))
    if r is None:
        return False
    return r._cond_true(fig, _key(e), c, ctx)


def _triggered(fig, e, r, ctx, world):
    res = [_cond_true(fig, r, e, c, ctx, world) for c in e["conditions"]]
    return all(res) if e.get("logic") == "all" else any(res)


def _can_start(fig):
    c = fig.combat
    # Never cut into an ultimate / stance that owns the figure, or a
    # tactical-retreat dash in progress.
    rt = getattr(fig, "retreat", None)
    return not (c.vc_phase or c.sp_phase or c.lb_phase
                or c.blinkstorm_strikes_left > 0
                or (rt is not None and rt.active))


def _span(e, n):
    """(S, E) of an entry on an action of n frames (E -1 = last frame)."""
    s = max(0, min(n - 1, int(e.get("start_frame") or 0)))
    ef = int(e.get("end_frame") if e.get("end_frame") is not None else -1)
    ef = n - 1 if ef < 0 else min(n - 1, ef)
    return s, max(s, ef)


def _begin(fig, st, e, r, ctx, now):
    """Conditions passed: start this entry.  False when it can't start yet
    (its action can't play now)."""
    from . import actions
    act = e["action"]
    if act:
        if r is None or act not in fig.render.bundle.extra:
            return False
        if r.playing is not None and r.playing != act and actions._kind(r.playing) == "triggered":
            return False        # never cut into another triggered action
        if r.playing is not None:
            r._finish(fig, now)
        if not r._start(fig, act, ctx, now):
            return False
    # Its conditions' counters restart, like an action's when it fires.
    if r is not None:
        k = _key(e)
        r.since_attacks[k] = 0
        r.since_hits[k] = 0
        for c in e["conditions"]:
            if c["type"] == "hp_below" and ctx["hp_pct"] <= float(c.get("pct", 50)):
                r.hp_fired.setdefault(k, set()).add(float(c.get("pct", 50)))
    st.entry = e
    if act:
        st.phase = "pre"
    else:
        _vanish(fig, st, e)
        st.timed = True
        st.ticks_left = _ticks(e["freeze_ms"] if e["freeze"] else e["gone_ms"])
    return True


def _vanish(fig, st, e):
    from . import combat
    st.phase = "gone"
    st.x0, st.y0 = fig.x, fig.y
    # A blink takes the fighter out of any knockback or melee move.
    m, c = fig.motion, fig.combat
    m.bouncing = m.bounce_ending = False
    m.bounce_vx = m.bounce_vy = 0.0
    c.dashing = c.rebounding = c.slashing = False
    c.arc_repositioning = c.arc_recoiling = False
    c.dodge_dashing = c.dodge_counter = c.dodge_interrupt = False
    c.combo_delay_ticks = 0
    c.followup_pending = 0
    if e.get("flash", True):
        combat.spawn_afterimage(fig)
        c.blink_fx_pending.append((fig.x, fig.y, fig.x, fig.y))


def _landing(fig, st, e, world):
    from . import retreat
    tx, ty, tface = retreat._target(world, fig)
    # The fighter -> target line, from where the fighter vanished.
    lx, ly = tx - st.x0, ty - st.y0
    d = math.hypot(lx, ly)
    if d > 0.001:
        ux, uy = lx / d, ly / d
    else:
        ux, uy = (-1.0 if fig.transform.facing_left else 1.0), 0.0
    dmode = e.get("direction")
    if dmode == "toward":
        dx, dy = ux, uy
    elif dmode == "away":
        dx, dy = -ux, -uy
    elif dmode in ("behind", "front"):
        if tface is None:
            dx, dy = ux, uy                     # far side from the fighter
        else:
            dx, dy = (1.0, 0.0) if tface else (-1.0, 0.0)   # opposite its facing
        if dmode == "front":
            dx, dy = -dx, -dy
    elif dmode == "random":
        a = fig.personality.rng.uniform(0.0, 2.0 * math.pi)
        dx, dy = math.cos(a), math.sin(a)
    else:   # "angle"
        a = math.atan2(uy, ux) + math.radians(float(e.get("angle_deg") or 0))
        dx, dy = math.cos(a), math.sin(a)
    ax, ay = (tx, ty) if e.get("anchor") == "target" else (st.x0, st.y0)
    prox = max(0.0, float(e.get("proximity_px") or 0))
    nx, ny = ax + dx * prox, ay + dy * prox
    nx = max(MARGIN_PX, min(fig.screen_w - MARGIN_PX, nx))
    ny = max(MARGIN_PX, min(fig.screen_h - MARGIN_PX, ny))
    return nx, ny, tx


def _reappear(fig, st, world, now):
    from . import actions
    e = st.entry
    nx, ny, tx = _landing(fig, st, e, world)
    t = fig.transform
    t.x, t.y = nx, ny
    if tx < nx - 0.001:
        t.facing_left = True
    elif tx > nx + 0.001:
        t.facing_left = False
    fig.trail.clear()           # no streak from the old spot to the new one
    _done(st, now)
    r = actions.runner(fig)
    if r is not None:
        r.history.append(HISTORY_NAME)
        del r.history[:-12]
    if e.get("flash", True):
        fig.combat.blink_fx_pending.append((nx, ny, nx, ny))


def _done(st, now):
    st.cooldown_until[st.entry["id"]] = now + _ticks(st.entry.get("cooldown_ms"))
    st.phase = None
    st.timed = False


def _jump_to_end(fig, st):
    """Freeze with an action: the hold is over — continue from frame E."""
    r = getattr(fig, "act", None)
    act = st.entry["action"]
    if r is None or r.playing != act:
        return
    n, fm = r._frames(fig, act)
    _s, e = _span(st.entry, n)
    r.elapsed = e * fm
    fig.combat.action_idx = e
    drv = getattr(fig, "fx", None)
    if drv is not None:
        drv.jump(act, e)


def tick(fig, world):
    """One tick, before the fighter's action runner and FX: triggers and
    timed reappearances.  True while the fighter is gone this tick (the
    caller then holds its FX, skips its action runner when frozen, and
    leaves it out of movement)."""
    cfg = config_for(fig)
    st = getattr(fig, "blink", None)
    if cfg is None:
        if st is not None and st.phase is not None:
            fig.blink = None    # settings removed (F5) mid-blink
        return False
    if st is None:
        st = BlinkState()
        fig.blink = st
    now = world.global_tick
    if st.phase is None:
        if not fig.transform.init or not _can_start(fig):
            return False
        from . import retreat
        tx, ty, _tf = retreat._target(world, fig)
        r, ctx = _ctx(fig, world, tx, ty)
        for e in cfg["entries"]:
            if now < st.cooldown_until.get(e["id"], 0):
                continue
            if _triggered(fig, e, r, ctx, world) and _begin(fig, st, e, r, ctx, now):
                break
    if st.phase != "gone":
        return False
    if st.timed:
        if st.ticks_left <= 0:
            if st.entry["action"] and st.entry["freeze"]:
                _jump_to_end(fig, st)
            _reappear(fig, st, world, now)
            return False
        st.ticks_left -= 1
    # Hits taken before vanishing belong to the tick they landed on; a
    # frozen runner won't clear them, so they don't carry over.
    r = getattr(fig, "act", None)
    if r is not None and st.entry["freeze"]:
        r.hit_tags = []
    return True


def after_action(fig, world):
    """Right after the fighter's action runner: vanish on the action's start
    frame, and (freeze off) reappear on its end frame.  True while the
    fighter is gone this tick."""
    st = getattr(fig, "blink", None)
    if st is None or st.phase is None:
        return False
    e = st.entry
    act = e["action"]
    r = getattr(fig, "act", None)
    now = world.global_tick
    if st.phase == "pre":
        if r is None or r.playing != act:
            _done(st, now)          # the action was cut off before its start frame
            return False
        n, _fm = r._frames(fig, act)
        s, ef = _span(e, n)
        if fig.combat.action_idx < s:
            return False
        _vanish(fig, st, e)
        if e["freeze"]:
            st.timed = True
            st.ticks_left = _ticks(e["freeze_ms"])
            if st.ticks_left <= 0:      # no hold: straight to E
                _jump_to_end(fig, st)
                _reappear(fig, st, world, now)
                return False
            return True
        st.timed = False
        if ef <= s:
            _reappear(fig, st, world, now)
            return False
        return True
    if st.phase == "gone" and act and not st.timed:
        # Freeze off: the frames play hidden until the end frame.
        n, _fm = r._frames(fig, act) if r is not None else (1, 1.0)
        _s, ef = _span(e, n)
        if r is None or r.playing != act or fig.combat.action_idx >= ef:
            _reappear(fig, st, world, now)
            return False
    return st.phase == "gone"


def reset(fig):
    fig.blink = None
