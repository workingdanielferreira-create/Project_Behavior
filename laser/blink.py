"""
Blink — a teleport inside one action.  Set per action in FX Studio
("Blink (this action)", action_settings[action].blink) for image characters
(Rig Forge + FX Studio).  Actions without it are untouched.  (Not the
built-in swordsman's blink-dodge / blink-warp in combat.py: that is a
separate JSON block.)

While an action with Blink on plays, the fighter vanishes when the frame on
show reaches start_frame and reappears once it passes end_frame (-1 = the
last frame), or when the action ends, whichever comes first.  A looping
action blinks again on every loop.  cooldown_ms (0 = none): after the
fighter reappears, that action's Blink stays off for this long — the action
still plays when its own triggers say so, just without vanishing.  It reappears proximity_px from the
landing anchor:

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
keep flying.  It doesn't move.  Its action and animation keep running
hidden, so the frames tick on to end_frame.

Driven from CombatSystem for every figure, so Solo and Battle run the same
code.  Solo has no enemy projectiles, and the cursor has no facing.
"""

import math

from . import config

MARGIN_PX = 20.0        # keep the landing spot this far inside the screen


def config_for(fig, action):
    """The normalised Blink of fig's `action`, or None when it has none."""
    from . import fxkit
    cfx = fxkit.character_fx(fig.mode)
    if cfx is None:
        return None
    b = (cfx.settings.get(action) or {}).get("blink")   # normalised on load (fxkit.normalize_action)
    return b if isinstance(b, dict) and b.get("enabled") else None


def _active(fig, cfg, action, frame):
    """True when `frame` of `action` is inside cfg's blink frames."""
    from . import fxkit
    cfx = fxkit.character_fx(fig.mode)
    n = cfx.timing.get(action, (1, 100.0))[0] if cfx is not None else 1
    e = n - 1 if cfg["end_frame"] < 0 else min(n - 1, cfg["end_frame"])
    return cfg["start_frame"] <= frame <= e


class BlinkState:
    __slots__ = ("gone", "x0", "y0", "cfg", "action", "ready_at", "play")

    def __init__(self):
        self.gone = False
        self.x0 = self.y0 = 0.0
        self.cfg = None
        self.action = None
        self.ready_at = {}    # action -> tick its Blink is off cooldown
        self.play = None      # the play (_play_key) that last blinked


def _play_key(fig, action):
    """Identifies one play of `action` (a new play = a new key)."""
    r = getattr(fig, "act", None)
    return (action, r.started if r is not None and r.playing == action else None)


def _cooling(st, action, now):
    return st is not None and now < st.ready_at.get(action, -1)


def fx_on(fig, action, now):
    """Whether the FX built on `action`'s Blink play now (its Blink is on):
    not while the Blink is on cooldown, unless this play already blinked."""
    st = getattr(fig, "blink", None)
    if st is None or st.gone or not _cooling(st, action, now):
        return True
    return st.play == _play_key(fig, action)


def gone(fig):
    """True while fig has blinked out (invisible, untouchable)."""
    st = getattr(fig, "blink", None)
    return bool(st is not None and st.gone)


def _can_start(fig):
    c = fig.combat
    # Never cut into an ultimate / stance that owns the figure, or a
    # tactical-retreat dash in progress.
    rt = getattr(fig, "retreat", None)
    return not (c.vc_phase or c.sp_phase or c.lb_phase
                or c.blinkstorm_strikes_left > 0
                or (rt is not None and rt.active))


def _vanish(fig, st, cfg, action):
    from . import combat
    st.gone = True
    st.cfg = cfg
    st.action = action
    st.play = _play_key(fig, action)
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
    prox = max(0.0, float(cfg.get("proximity_px") or 0)) * fig.mode.body_scale()   # character scale
    nx, ny = ax + dx * prox, ay + dy * prox
    nx = max(MARGIN_PX, min(fig.screen_w - MARGIN_PX, nx))
    ny = max(MARGIN_PX, min(fig.screen_h - MARGIN_PX, ny))
    return nx, ny, tx


def _reappear(fig, st, world):
    cfg = st.cfg or {}
    nx, ny, tx = _landing(fig, st, cfg, world)
    t = fig.transform
    t.x, t.y = nx, ny
    if tx < nx - 0.001:
        t.facing_left = True
    elif tx > nx + 0.001:
        t.facing_left = False
    fig.trail.clear()           # no streak from the old spot to the new one
    st.gone = False
    st.cfg = None
    # Cooldown from the moment it reappears.
    cd = max(0.0, float(cfg.get("cooldown_ms") or 0))
    if cd > 0 and st.action is not None:
        st.ready_at[st.action] = world.global_tick + int(round(cd / config.TICK_MS))
    if cfg.get("flash", True):
        fig.combat.blink_fx_pending.append((nx, ny, nx, ny))


def tick(fig, world):
    """One tick, before the fighter's action runner and FX.  True while the
    fighter is gone this tick (the caller then holds its FX and leaves it
    out of movement; its action keeps running)."""
    from . import actions, fxkit
    st = fig.blink
    if not actions.is_image(fig) or fxkit.character_fx(fig.mode) is None:
        if st is not None and st.gone:
            _reappear(fig, st, world)
        return False
    action, frame = fxkit.current_action(fig)
    cfg = config_for(fig, action)
    on = cfg is not None and _active(fig, cfg, action, frame)
    if st is None:
        if not on:
            return False
        st = BlinkState()
        fig.blink = st
    if st.gone:
        if on:
            return True
        _reappear(fig, st, world)
        return False
    if on and fig.transform.init and _can_start(fig) and not _cooling(st, action, world.global_tick):
        _vanish(fig, st, cfg, action)
        return True
    return False


def reset(fig):
    fig.blink = None
