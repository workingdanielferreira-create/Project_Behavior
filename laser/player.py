"""
Player control — F4 hands character 1 to the keyboard.  Solo and Battle.

"Character 1" = the first-picked slot whose fighter is on the field (the
same fighter F11 uses, World.player_fig).  Only image characters (Rig
Forge / FX Studio JSON characters, actions.is_image) can be controlled;
the built-in swordsman / runner are not.

While control is on:

  * Arrow keys move the fighter (two held = diagonal) at its own pace
    (position speed scaled, an action's move_speed_pct still applies).
    No arrow held = it stands.  A knockback still slides it.  Alt+arrows
    keep their old jobs (no movement while Alt is held).
  * Ctrl+Z / Ctrl+X / Ctrl+C play the next action of a chain:
        Ctrl+Z  attack_normal  -> attack_normal_2  -> attack_normal_3  ...
        Ctrl+X  attack_special -> attack_special_2 -> ...
        Ctrl+C  ultimate       -> ultimate_2       -> ...
    After the last one it wraps back to the first.  When the last action of
    that chain ended more than its chain_reset_ms ago (default 1000 ms) the
    chain restarts at the first.  Only actions the character has frames for
    count.  Trigger conditions, cooldowns and Attack mode (Alt+Up) are
    ignored.  A press while an action plays is buffered (one press, the
    latest, kept for BUFFER_MS) and starts the moment it can: a special /
    ultimate cuts into a normal attack (like the AI), anything else waits.
  * Every automatic action (attacks, defend, condition-triggered specials /
    ultimates, tactical retreat, AI movement) is off.  Only the Dodge
    (laser/dodge.py, with its counter action) still runs on its own.
  * Ctrl+Space drops the fighter's HP to 25% of max (never raises it).

Freeze (F10) holds the player fighter like everyone else.  F4 and F11
(cursor puppet) are exclusive: turning one on turns the other off.
"""

import re

from . import config

TICK_MS = config.TICK_MS
BUFFER_MS = 600              # a buffered press is dropped after this long
DEFAULT_CHAIN_RESET_MS = 1000
HP_DROP_FRAC = 0.25

CHAINS = {
    "attack": "attack_normal",
    "special": "attack_special",
    "ultimate": "ultimate",
}


def chain_names(fig, kind):
    """The chain for `kind` in play order: base, base_2, base_3, ... (only
    actions the character has frames for)."""
    base = CHAINS.get(kind)
    if not base:
        return []
    extra = getattr(fig.render.bundle, "extra", {}) or {}
    rx = re.compile(r"^%s(?:_(\d+))?$" % re.escape(base))
    out = []
    for name in extra:
        m = rx.match(name)
        if m and extra.get(name) and extra[name][0]:
            out.append((int(m.group(1)) if m.group(1) else 1, name))
    out.sort()
    return [n for _i, n in out]


class PlayerState:
    """Per-fighter chain positions (kept on the action runner)."""
    __slots__ = ("pos", "last")

    def __init__(self):
        self.pos = {}    # kind -> index of the next action to play
        self.last = {}   # kind -> name of the last action played


def _state(r):
    st = getattr(r, "player", None)
    if st is None:
        st = PlayerState()
        r.player = st
    return st


def _next_name(fig, r, kind, now):
    from . import actions
    names = chain_names(fig, kind)
    if not names:
        return None
    st = _state(r)
    i = st.pos.get(kind, 0)
    last = st.last.get(kind)
    if last is not None and r.playing != last:
        cfg = actions._cfg(fig, last)
        try:
            reset = float(cfg.get("chain_reset_ms") or DEFAULT_CHAIN_RESET_MS)
        except (TypeError, ValueError):
            reset = DEFAULT_CHAIN_RESET_MS
        ended = r.last_end.get(last)
        if ended is not None and now - ended > int(reset / TICK_MS):
            i = 0
    if i >= len(names):
        i = 0
    return names[i], i, len(names)


def runner_tick(r, fig, world, ctx, now):
    """Called by the action runner (actions.Runner.update) for the player
    fighter, in place of the automatic attack / triggered-action choice.
    Starts the buffered press when it can."""
    from . import actions
    req = getattr(world, "player_req", None)
    if not req:
        return
    kind, at = req
    if now - at > int(BUFFER_MS / TICK_MS):
        world.player_req = None
        return
    if r.forced is not None:
        return                      # a forced clash action: wait for it
    pick = _next_name(fig, r, kind, now)
    if pick is None:
        world.player_req = None     # this character has no such action
        return
    name, i, n = pick
    if r.playing is not None:
        cut = kind in ("special", "ultimate") and actions._kind(r.playing) == "attack"
        if not cut:
            return                  # keep it buffered
        r._finish(fig, now)
    if r._start(fig, name, ctx, now):
        st = _state(r)
        st.pos[kind] = (i + 1) % n
        st.last[kind] = name
        world.player_req = None


def press(world, kind):
    """InputSystem: Ctrl+Z / X / C pressed (kind attack / special /
    ultimate).  Buffers the press for the player fighter."""
    if world.player_fig() is None:
        return
    world.player_req = (kind, world.global_tick)


def drop_hp(world):
    """Ctrl+Space: the player fighter's HP drops to 25% of max."""
    fig = world.player_fig()
    if fig is None:
        return
    p = fig.personality
    tgt = p.max_hp * HP_DROP_FRAC
    if isinstance(p.max_hp, int) and isinstance(p.hp, int):
        tgt = max(1, int(round(tgt)))
    if p.hp > tgt:
        p.hp = tgt
    world.notice = ("%s HP -> 25%%" % getattr(fig.mode, "key", "Fighter"), 90)
