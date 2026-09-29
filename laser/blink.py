"""
Blink — a character-level teleport.  Set in FX Studio ("Blink (whole
character)", pack.blink) for image characters (Rig Forge + FX Studio).
Characters without it are untouched.  (Not the built-in swordsman's
blink-dodge / blink-warp in combat.py: that is a separate JSON block.)

When its conditions are met (ANY / ALL) the fighter vanishes where it
stands, stays gone for gone_ms (the Studio's "Teleport speed"), then
reappears proximity_px from the landing anchor:

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

  freeze on   its action and animation stop and resume on the same frame
              when it reappears
  freeze off  its action and animation keep running while hidden

A new blink can start cooldown_ms after the fighter reappears.  Every
reappearance is recorded as "blink" in the action history, so an action's
after_actions condition can follow it (e.g. "blink" -> attack_special).

Conditions: every action trigger condition (hp_below, attacks_made,
hits_taken, target_within, target_beyond, hit_by_fx, fx_near,
bullet_deflected, after_actions; evaluated by the fighter's ActionRunner
exactly as for its actions, under the name "__blink__") plus
projectile_count (count or more enemy projectiles in the air at once).

Driven from CombatSystem for every figure, so Solo and Battle run the same
code.  Solo has no enemy projectiles, and the cursor has no facing.
"""

import copy
import math

from . import config

NAME = "__blink__"      # the ActionRunner counter key for blink's conditions
HISTORY_NAME = "blink"  # what a blink adds to the action history

DEFAULTS = dict(enabled=False, gone_ms=300.0, freeze=True, anchor="target",
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


def normalize(cfg):
    out = dict(cfg or {})
    for k, v in DEFAULTS.items():
        if k not in out:
            out[k] = copy.deepcopy(v)
    if out.get("anchor") not in ANCHORS:
        out["anchor"] = DEFAULTS["anchor"]
    if out.get("direction") not in DIRECTIONS:
        out["direction"] = DEFAULTS["direction"]
    conds = []
    for c in out.get("conditions") or []:
        t = (c or {}).get("type")
        if t in CONDITIONS:
            cc = dict(CONDITIONS[t])
            cc.update(c)
            conds.append(cc)
    out["conditions"] = conds
    return out


def config_for(fig):
    """Normalised blink settings for fig, or None when it has none."""
    mode = fig.mode
    if hasattr(mode, "_fxblink_cfg"):
        return mode._fxblink_cfg
    cfg = None
    char = getattr(mode, "character", None)
    if char and char.get("_package"):
        raw = (char.get("_fxkit") or {}).get("blink")
        if isinstance(raw, dict):
            n = normalize(raw)
            if n.get("enabled") and n["conditions"]:
                cfg = n
    mode._fxblink_cfg = cfg
    return cfg


class BlinkState:
    __slots__ = ("gone", "ticks_left", "x0", "y0", "freeze", "cooldown_until")

    def __init__(self):
        self.gone = False
        self.ticks_left = 0
        self.x0 = self.y0 = 0.0
        self.freeze = True
        self.cooldown_until = 0


def gone(fig):
    """True while fig has blinked out (invisible, untouchable)."""
    st = getattr(fig, "blink", None)
    return bool(st is not None and st.gone)


def frozen(fig):
    """True while fig is gone with freeze on (its action clock stops)."""
    st = getattr(fig, "blink", None)
    return bool(st is not None and st.gone and st.freeze)


def _ticks(ms):
    return max(0, int(round(max(0.0, float(ms or 0)) / config.TICK_MS)))


def _hp_pct(fig):
    p = fig.personality
    return 100.0 * p.hp / max(1e-6, p.max_hp)


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


def _cond_true(fig, r, c, ctx, world):
    if c["type"] == "projectile_count":
        return len(getattr(world, "enemy_shots", None) or []) >= max(1, int(c.get("count", 5)))
    if r is None:
        return False
    return r._cond_true(fig, NAME, c, ctx)


def _triggered(fig, cfg, world, tx, ty):
    r, ctx = _ctx(fig, world, tx, ty)
    res = [_cond_true(fig, r, c, ctx, world) for c in cfg["conditions"]]
    return (all(res) if cfg.get("logic") == "all" else any(res)), r, ctx


def _can_start(fig):
    c = fig.combat
    # Never cut into an ultimate / stance that owns the figure, or a
    # tactical-retreat dash in progress.
    rt = getattr(fig, "retreat", None)
    return not (c.vc_phase or c.sp_phase or c.lb_phase
                or c.blinkstorm_strikes_left > 0
                or (rt is not None and rt.active))


def _vanish(fig, st, cfg, r, ctx, now):
    from . import combat
    st.gone = True
    st.x0, st.y0 = fig.x, fig.y
    st.freeze = bool(cfg.get("freeze", True))
    st.ticks_left = _ticks(cfg.get("gone_ms"))
    # Its conditions' counters restart, like an action's when it fires.
    if r is not None:
        r.since_attacks[NAME] = 0
        r.since_hits[NAME] = 0
        for c in cfg["conditions"]:
            if c["type"] == "hp_below" and ctx["hp_pct"] <= float(c.get("pct", 50)):
                r.hp_fired.setdefault(NAME, set()).add(float(c.get("pct", 50)))
    # A blink takes the fighter out of any knockback or melee move.
    m, c = fig.motion, fig.combat
    m.bouncing = m.bounce_ending = False
    m.bounce_vx = m.bounce_vy = 0.0
    c.dashing = c.rebounding = c.slashing = False
    c.arc_repositioning = c.arc_recoiling = False
    c.dodge_dashing = c.dodge_counter = c.dodge_interrupt = False
    c.combo_delay_ticks = 0
    c.followup_pending = 0
    if cfg.get("flash", True):
        combat.spawn_afterimage(fig)
        c.blink_fx_pending.append((fig.x, fig.y, fig.x, fig.y))


def _landing(fig, st, cfg, world):
    from . import retreat
    tx, ty, tface = retreat._target(world, fig)
    # The fighter -> target line, from where the fighter vanished.
    lx, ly = tx - st.x0, ty - st.y0
    d = math.hypot(lx, ly)
    if d > 0.001:
        ux, uy = lx / d, ly / d
    else:
        ux, uy = (-1.0 if fig.transform.facing_left else 1.0), 0.0
    dmode = cfg.get("direction")
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
        a = math.atan2(uy, ux) + math.radians(float(cfg.get("angle_deg") or 0))
        dx, dy = math.cos(a), math.sin(a)
    ax, ay = (tx, ty) if cfg.get("anchor") == "target" else (st.x0, st.y0)
    prox = max(0.0, float(cfg.get("proximity_px") or 0))
    nx, ny = ax + dx * prox, ay + dy * prox
    nx = max(MARGIN_PX, min(fig.screen_w - MARGIN_PX, nx))
    ny = max(MARGIN_PX, min(fig.screen_h - MARGIN_PX, ny))
    return nx, ny, tx


def _reappear(fig, st, cfg, world, now):
    from . import actions
    nx, ny, tx = _landing(fig, st, cfg, world)
    t = fig.transform
    t.x, t.y = nx, ny
    if tx < nx - 0.001:
        t.facing_left = True
    elif tx > nx + 0.001:
        t.facing_left = False
    fig.trail.clear()           # no streak from the old spot to the new one
    st.gone = False
    st.cooldown_until = now + _ticks(cfg.get("cooldown_ms"))
    r = actions.runner(fig)
    if r is not None:
        r.history.append(HISTORY_NAME)
        del r.history[:-12]
    if cfg.get("flash", True):
        fig.combat.blink_fx_pending.append((nx, ny, nx, ny))


def tick(fig, world):
    """One tick, before the fighter's action runner and FX.  True while the
    fighter is gone this tick (the caller then holds its FX, skips its
    action runner when frozen, and leaves it out of movement)."""
    cfg = config_for(fig)
    if cfg is None:
        return False
    st = fig.blink
    if st is None:
        st = BlinkState()
        fig.blink = st
    now = world.global_tick
    if not st.gone:
        if (now < st.cooldown_until or not fig.transform.init
                or not _can_start(fig)):
            return False
        from . import retreat
        tx, ty, _tf = retreat._target(world, fig)
        ok, r, ctx = _triggered(fig, cfg, world, tx, ty)
        if not ok:
            return False
        _vanish(fig, st, cfg, r, ctx, now)
    if st.ticks_left <= 0:
        _reappear(fig, st, cfg, world, now)
        return False
    st.ticks_left -= 1
    # Hits taken before vanishing belong to the tick they landed on; a
    # frozen runner won't clear them, so they don't carry over.
    r = getattr(fig, "act", None)
    if r is not None and st.freeze:
        r.hit_tags = []
    return True


def reset(fig):
    fig.blink = None
