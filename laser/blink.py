"""
Blink — a teleport inside one action.  Set per action in FX Studio
("Blink (this action)", action_settings[action].blink) for image characters
(Rig Forge + FX Studio).  Actions without it are untouched.  (Not the
built-in swordsman's blink-dodge / blink-warp in combat.py: that is a
separate JSON block.)

An action's Blink is a list of blinks (`blinks`), run in order as the
action's frames pass them; Blink is on while the list holds any.  For each
blink, the fighter vanishes when the frame on show reaches its start_frame
and reappears once it passes its end_frame (-1 = the last frame), or when
the action ends, whichever comes first.  When the next blink's frames start
right after, it vanishes again on the same tick (back-to-back hops).  A
looping action runs the list again on every loop.  cooldown_ms (0 = none,
shared by the whole list): after the fighter reappears, that action's Blink
stays off for this long — the action still plays when its own triggers say
so, just without vanishing — but the later blinks of the same pass still
run.  Each blink reappears proximity_px from its landing anchor:

  anchor     "target"  measured from the target (nearest enemy in Battle,
                       the cursor in Solo), where it is when the fighter
                       reappears
             "self"    measured from the spot the fighter vanished from
                       (for a later blink: where the last one landed)
  direction  "behind"  the target's back: opposite the way it faces (Solo:
                       the far side from the fighter, left / right only;
                       straight above / below it, the way it faces)
             "front"   the side the target faces (Solo: the fighter's side)
             "toward"  along the line from the fighter to the target
             "away"    along the line from the target to the fighter
             "above" / "below"            straight up / down on screen
             "above_left" / "above_right" / "below_left" / "below_right"
                       45° diagonals, screen left / right (not the facing)
             "random"  any direction
             "angle"   angle_deg from the fighter -> target line (0 = toward,
                       180 = away, positive = clockwise on screen); with
                       mirror on, a fighter on the target's right lands
                       flipped left / right only (up / down unchanged)

While gone the fighter is invisible and untouchable: it takes no hits,
knockback or body contact, and it doesn't move.  It moves too fast to see,
so its FX carry on as normal: they keep firing on the action's frames,
its body-bound FX (attached / orbit / weapon) stay visible and still hit.
Its action and animation keep running hidden, so the frames tick on to
end_frame.

point() gives where each blink of the playing action vanishes / lands
(FX paths pin their points to these: laser/fxkit.py path_anchor_pos).
Once a blink of this pass has happened, its real spots; until then, where
it would happen now (the same rule as the landing, with the random
direction rolled once per blink so the prediction holds still).

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


def _active_index(fig, cfg, action, frame):
    """The index of the first blink in cfg["blinks"] whose frames hold
    `frame` of `action`, or -1 when none does."""
    from . import fxkit
    cfx = fxkit.character_fx(fig.mode)
    n = cfx.timing.get(action, (1, 100.0))[0] if cfx is not None else 1
    for i, b in enumerate(cfg.get("blinks") or ()):
        e = n - 1 if b["end_frame"] < 0 else min(n - 1, b["end_frame"])
        if b["start_frame"] <= frame <= e:
            return i
    return -1


class BlinkState:
    __slots__ = ("gone", "x0", "y0", "cfg", "action", "ready_at", "play", "idx", "cooldown_ms",
                 "marks", "mplay", "mframe", "rolls")

    def __init__(self):
        self.gone = False
        self.x0 = self.y0 = 0.0
        self.cfg = None       # the blink (one entry of `blinks`) it is gone for
        self.action = None
        self.ready_at = {}    # action -> tick its Blink is off cooldown
        self.play = None      # the play (_play_key) that last blinked
        self.idx = -1         # the index of the blink that last vanished
        self.cooldown_ms = 0.0  # its action's Blink cooldown (shared by the list)
        # This pass's blinks (point): index -> [(x, y) vanished, (x, y) landed or None]
        self.marks = {}
        self.mplay = None     # the play the marks belong to
        self.mframe = -1      # the frame last seen (a lower one = a new pass)
        self.rolls = {}       # index -> its random-direction angle (radians), until it lands


def _play_key(fig, action):
    """Identifies one play of `action` (a new play = a new key)."""
    r = getattr(fig, "act", None)
    return (action, r.started if r is not None and r.playing == action else None)


def _cooling(fig, st, action, now):
    from . import unique
    return st is not None and unique.cd_now(fig, now) < st.ready_at.get(action, -1)


def fx_on(fig, action, now):
    """Whether the FX built on `action`'s Blink play now (its Blink is on):
    not while the Blink is on cooldown, unless this play already blinked."""
    st = getattr(fig, "blink", None)
    if st is None or st.gone or not _cooling(fig, st, action, now):
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


def _may_vanish(fig, st, action, i, now):
    """Blink i of `action` may start: the action's Blink is off cooldown, or
    an earlier blink of this same pass already ran (the rest of the list
    still plays; a loop back to the start waits for the cooldown)."""
    if not _cooling(fig, st, action, now):
        return True
    return st.play == _play_key(fig, action) and st.action == action and i > st.idx


def _vanish(fig, st, cfg, action, i, cooldown_ms):
    from . import combat
    st.gone = True
    st.cfg = cfg
    st.cooldown_ms = cooldown_ms
    st.action = action
    st.play = _play_key(fig, action)
    st.idx = i
    st.x0, st.y0 = fig.x, fig.y
    for j in [j for j in st.marks if j >= i]:
        del st.marks[j]     # a loop back: this blink and the later ones happen anew
    st.mplay = st.play
    st.marks[i] = [(fig.x, fig.y), None]
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


def _roll(fig, st, i):
    """Blink i's random direction (radians), rolled once and kept until it
    lands, so its predicted landing (point) and the real one agree."""
    if i not in st.rolls:
        st.rolls[i] = fig.personality.rng.uniform(0.0, 2.0 * math.pi)
    return st.rolls[i]


def _landing(fig, st, cfg, world, x0=None, y0=None, i=None):
    """Where a blink measured from (x0, y0) (default: where the fighter
    vanished) lands now: (x, y, target x).  i = its index (random roll)."""
    from . import retreat
    tx, ty, tface = retreat._target(world, fig)
    if x0 is None:
        x0, y0 = st.x0, st.y0
    # The fighter -> target line, from where the fighter vanished.
    lx, ly = tx - x0, ty - y0
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
            # No facing (Solo cursor): the far side from the fighter,
            # left / right only; straight above / below it, the way the
            # fighter faces.
            if abs(lx) > 0.001:
                dx = 1.0 if lx > 0 else -1.0
            else:
                dx = -1.0 if fig.transform.facing_left else 1.0
            dy = 0.0
        else:
            dx, dy = (1.0, 0.0) if tface else (-1.0, 0.0)   # opposite its facing
        if dmode == "front":
            dx, dy = -dx, -dy
    elif dmode in _SCREEN_DIRS:
        dx, dy = _SCREEN_DIRS[dmode]
    elif dmode == "random":
        a = _roll(fig, st, st.idx if i is None else i)
        dx, dy = math.cos(a), math.sin(a)
    else:   # "angle"
        # mirror: the angle is set for a fighter on the target's left; from
        # its right only the horizontal flips (up / down stay as set).
        mx = -1.0 if cfg.get("mirror") and lx < -0.001 else 1.0
        a = math.atan2(uy, ux * mx) + math.radians(float(cfg.get("angle_deg") or 0))
        dx, dy = math.cos(a) * mx, math.sin(a)
    ax, ay = (tx, ty) if cfg.get("anchor") == "target" else (x0, y0)
    prox = max(0.0, float(cfg.get("proximity_px") or 0)) * fig.mode.body_scale()   # character scale
    nx, ny = ax + dx * prox, ay + dy * prox
    nx = max(MARGIN_PX, min(fig.screen_w - MARGIN_PX, nx))
    ny = max(MARGIN_PX, min(fig.screen_h - MARGIN_PX, ny))
    return nx, ny, tx


_D = math.sqrt(0.5)
_SCREEN_DIRS = {"above": (0.0, -1.0), "below": (0.0, 1.0),       # screen y grows downward
                "above_left": (-_D, -_D), "above_right": (_D, -_D),
                "below_left": (-_D, _D), "below_right": (_D, _D)}


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
    st.rolls.pop(st.idx, None)  # the next pass rolls afresh
    if st.mplay == st.play:
        st.marks[st.idx] = [(st.x0, st.y0), (nx, ny)]
    # Cooldown from the moment it reappears.
    cd = max(0.0, float(st.cooldown_ms or 0))
    # Domain Expansion '0 ms blink' (laser/unique.py): no cooldown.
    from . import unique
    if unique.blink_free(fig):
        cd = 0.0
    if cd > 0 and st.action is not None:
        st.ready_at[st.action] = unique.cd_now(fig, world.global_tick) + int(round(cd / config.TICK_MS))
    if cfg.get("flash", True):
        fig.combat.blink_fx_pending.append((nx, ny, nx, ny))


def tick(fig, world):
    """One tick, before the fighter's action runner and FX.  True while the
    fighter is gone this tick (the caller leaves it out of movement; its
    action and FX keep running)."""
    from . import actions, fxkit
    st = fig.blink
    if not actions.is_image(fig) or fxkit.character_fx(fig.mode) is None:
        if st is not None and st.gone:
            _reappear(fig, st, world)
        return False
    action, frame = fxkit.current_action(fig)
    cfg = config_for(fig, action)
    i = _active_index(fig, cfg, action, frame) if cfg is not None else -1
    if st is None:
        if i < 0:
            return False
        st = BlinkState()
        fig.blink = st
    if st.gone:
        if i == st.idx and action == st.action:
            st.mframe = frame
            return True
        _reappear(fig, st, world)
        # The next blink's frames may start right away: vanish again below.
    _new_pass(fig, st, action, frame)
    if (i >= 0 and fig.transform.init and _can_start(fig)
            and _may_vanish(fig, st, action, i, world.global_tick)):
        _vanish(fig, st, cfg["blinks"][i], action, i, cfg.get("cooldown_ms"))
        return True
    return False


def _new_pass(fig, st, action, frame):
    """Forget the last pass's blinks (point) when a new play or loop starts."""
    key = _play_key(fig, action)
    if key != st.mplay or frame < st.mframe:
        st.marks = {}
        st.mplay = key
    st.mframe = frame


def point(fig, world, action, i, which):
    """Where blink i (0 = the first) of `action` vanishes ("start") or lands
    ("end") this pass: where it did, else where it would now.  A blink
    starts where the one before it lands (until that one has), else where
    the fighter is.  None when `action` has no blink i."""
    cfg = config_for(fig, action)
    blinks = (cfg or {}).get("blinks") or ()
    if not 0 <= i < len(blinks):
        return None
    st = fig.blink
    if st is None:
        st = BlinkState()
        fig.blink = st
    key = _play_key(fig, action)
    marks = st.marks if st.mplay == key else {}

    def start(j):
        m = marks.get(j)
        if m is not None:
            return m[0]
        if j > 0 and (marks.get(j - 1) or (None, None))[1] is None:
            return end(j - 1)
        return (fig.x, fig.y)

    def end(j):
        m = marks.get(j)
        if m is not None and m[1] is not None:
            return m[1]
        x0, y0 = start(j)
        nx, ny, _tx = _landing(fig, st, blinks[j], world, x0, y0, j)
        return (nx, ny)

    p = start(i) if which == "start" else end(i)
    return [p[0], p[1]]


def reset(fig):
    fig.blink = None
