"""
Time control (FX Studio: action_settings[action].time).

An image character's action can pause / unpause time: the pause sits
between two neighbouring frames of the action.  When the action passes from
`frame` to frame + 1 and its trigger conditions pass (ANY / ALL, every action
trigger condition; none = always), time runs at `speed` for what `scope`
names for duration_ms - its own length, whatever the action does meanwhile -
then goes back to normal.  The fighter doing the action (the caster)
controls the time: it is never slowed by its own time effect and keeps
playing.

    speed   0 = stopped, 1 = normal, up to fxkit.TIME_SPEED_MAX (8)
    keys    [{ms, speed, ease}] - the speed eases from the previous point to
            each key, ms counted from the moment the pause started
            (fxkit.time_speed), so a cut can slow, stop, then burst forward
    scope   enemy_fx / own_fx / all_fx       - FX Studio effects and bullets
            enemy_fighters / all_fighters    - fighters (not the caster)
            everything                       - every FX and every fighter
                                               except the caster

Each pass of the action can trigger it again once the last one has ended
(a new crossing while it runs is ignored).  Several time effects at once multiply, and a
fighter running its own time effect is never slowed by another one (its FX
can be), so two at once both play out instead of stopping each other.

How a time scale is applied (World tick, app.py):
  * plan() runs once per tick after refresh_battle.  Every figure gets a
    body scale and an FX scale; an accumulator turns each into a number of
    steps this tick (0.5 = a step every other tick, 3 = three steps).
  * run_side() runs a side's pipeline pass as sub-passes.  In sub-pass s a
    figure takes part in CombatSystem / MotionSystem / ProjectileSystem
    firing only while its body has more than s steps, and its FX Studio
    effects (fxkit.FxDriver) and bullets move only while its FX scale has
    more than s steps.  CollisionSystem (being hit, reacting) runs once per
    tick: a stopped fighter still takes hits and their knockback (it flies
    once time resumes) but cannot dodge, parry or counter.
  * A stopped FX holds still and lands no hits; FX its fighter fires while
    they are stopped appear and hold too.  Stopped enemy bullets are left out
    of the damage snapshot (enemy_projs) so they never hit while stopped.
Built-in archetype FX (crescents, petals, ...) follow their fighter's body
time.  Cooldowns and timers that read the global clock run on real time.

Solo and Battle run the same code: in Solo there is no enemy, so the enemy
scopes affect nothing and the own / all scopes act on the fighter's own FX.
"""

from . import config, action_log

TICK_MS = config.TICK_MS
MAX_STEPS = 8          # most steps one thing takes in a tick (speed 8)
_EPS = 1e-9


class TimeState:
    """Per figure: its own time effect (as a caster), the time scales other
    casters put on it this tick, and the action tracking action_triggered
    reads."""
    __slots__ = ("active", "action", "t", "last_action", "last_frame", "cfg", "speed",
                 "body", "fx", "body_acc", "fx_acc", "body_steps", "fx_steps", "frozen",
                 "act_name", "act_start")

    def __init__(self):
        self.active = False       # this figure's time effect is running
        self.action = None
        self.t = 0                # its ticks since it started (keys read t * TICK_MS)
        self.last_action = None   # action / frame on show last step (frame crossing)
        self.last_frame = -1
        self.cfg = None
        self.speed = 1.0
        self.body = 1.0           # time scale on this figure's body this tick
        self.fx = 1.0             # time scale on this figure's FX / bullets this tick
        self.body_acc = 0.0
        self.fx_acc = 0.0
        self.body_steps = 1
        self.fx_steps = 1
        self.frozen = False       # body takes no step at all this tick
        self.act_name = None      # actions.action_info
        self.act_start = 0


def state(fig):
    st = getattr(fig, "time", None)
    if st is None:
        st = TimeState()
        fig.time = st
    return st


# ------------------------------------------------------------ the caster
def _conds_ok(fig, world, action, cfg):
    if not cfg["conditions"]:
        return True
    from . import actions
    r, ctx = actions.tracker_ctx(fig, world)
    key = "@time:" + action
    if r._conds_pass(fig, key, cfg, ctx):
        r.mark_fired(key, cfg, ctx, world.global_tick)
        return True
    return False


def update_caster(fig, world):
    """CombatSystem hook, once per body step of an image character, after
    its action runner: start / advance / end this figure's time effect.  It
    starts on the step the action on show passes from `frame` to a later
    frame of the same pass, and lasts duration_ms of the caster's own time."""
    from .fxkit import character_fx, current_action, time_speed
    st = state(fig)
    cfx = character_fx(fig.mode)
    if cfx is None:
        st.active = False
        st.speed = 1.0
        return
    action, frame = current_action(fig)
    prev_action, prev_frame = st.last_action, st.last_frame
    st.last_action, st.last_frame = action, frame
    if st.active:
        st.t += 1
        if st.t * TICK_MS >= st.cfg["duration_ms"]:
            st.active = False
    if not st.active and action == prev_action:
        cfg = (cfx.settings.get(action) or {}).get("time")
        if (cfg and cfg["enabled"] and prev_frame <= cfg["frame"] < frame
                and _conds_ok(fig, world, action, cfg)):
            st.active, st.t, st.cfg, st.action = True, 0, cfg, action
            action_log.log("TIME", "%s %s: %s x%.2f between frames %d-%d for %d ms" % (
                fig.mode.key, action, cfg["scope"], cfg["speed"], cfg["frame"], cfg["frame"] + 1,
                cfg["duration_ms"]))
    st.speed = time_speed(st.cfg, st.t * TICK_MS) if st.active else 1.0


# ------------------------------------------------------------ the world
def _steps(acc, scale):
    """(steps this tick, new accumulator) for a time scale."""
    if scale == 1.0:
        return 1, 0.0
    acc += scale
    n = int(acc + _EPS)
    return min(MAX_STEPS, n), acc - n


def plan(world):
    """Once per tick, after refresh_battle: each figure's body / FX scale and
    steps from every running time effect.  None when no time effect runs
    (the pipeline then runs exactly as it always has)."""
    casters = []
    for si, side in enumerate(world.sides):
        for f in side.figures:
            st = getattr(f, "time", None)
            if st is not None and st.active:
                casters.append((f, si, st.cfg["scope"], st.speed))
    if not casters:
        for f in world.all_figures():
            st = getattr(f, "time", None)
            if st is not None:
                st.body = st.fx = 1.0
                st.body_acc = st.fx_acc = 0.0
                st.body_steps = st.fx_steps = 1
                st.frozen = False
        return None
    for sj, side in enumerate(world.sides):
        for f in side.figures:
            body = fx = 1.0
            # A fighter running its own time effect controls time: no other
            # time effect slows its body (two at once both play out instead
            # of stopping each other for good).  Its FX can still be slowed.
            casting = state(f).active
            for (c, si, scope, sp) in casters:
                enemy = sj != si
                if not casting and (scope in ("all_fighters", "everything") or (scope == "enemy_fighters" and enemy)):
                    body *= sp
                if scope in ("all_fx", "everything") or (scope == "enemy_fx" and enemy) or (scope == "own_fx" and f is c):
                    fx *= sp
            st = state(f)
            st.body, st.fx = body, fx
            st.body_steps, st.body_acc = _steps(st.body_acc, body)
            st.fx_steps, st.fx_acc = _steps(st.fx_acc, fx)
    # Stopped bullets never hit: leave them out of each side's damage
    # snapshot of the opponent (they stay in fx_near / Intercept views).
    for i, side in enumerate(world.sides):
        if side.enemy_projs:
            other = world.sides[1 - i]
            side.enemy_projs = [tp for tp in side.enemy_projs
                                if proj_steps(tp[8], other.figures) > 0]
    return True


def proj_steps(pr, figures):
    """FX steps this tick of a bullet: its owner's, or (no owner on the
    side) the side's first fighter's."""
    owner = getattr(pr, "owner", None)
    f = owner if (owner is not None and owner in figures) else (figures[0] if figures else None)
    st = getattr(f, "time", None) if f is not None else None
    return st.fx_steps if st is not None else 1


def fx_on(world, fig):
    """True when this figure's FX take a step in the current sub-pass."""
    on = getattr(world, "time_fx_on", None)
    return on is None or id(fig) in on


def frozen(fig):
    """True while this figure's body is stopped this tick (it can be hit but
    cannot react)."""
    st = getattr(fig, "time", None)
    return bool(st is not None and st.frozen)


def run_side(world, pipeline):
    """One side's pipeline pass (side already bound) as time sub-passes.
    Returns False when the game is quitting."""
    from .systems import CollisionSystem
    full = world.figures
    nb = {id(f): state(f).body_steps for f in full}
    nx = {id(f): state(f).fx_steps for f in full}
    lead = full[0] if full else None
    S = max([0] + list(nb.values()) + list(nx.values()))
    for f in full:
        state(f).frozen = nb[id(f)] == 0
    try:
        for s in range(max(1, S)):
            active = [f for f in full if nb[id(f)] > s]
            world.time_fx_on = {id(f) for f in full if nx[id(f)] > s}
            world.time_fx_only = [f for f in full if nb[id(f)] <= s < nx[id(f)]]
            world.time_side_fx = lead is None or nx[id(lead)] > s
            held, run = [], []
            for pr in world.projectiles:
                (run if proj_steps(pr, full) > s else held).append(pr)
            world.projectiles = run
            for system in pipeline:
                if isinstance(system, CollisionSystem):
                    if s:
                        continue      # being hit / reacting: once per tick
                    world.figures = full
                else:
                    world.figures = active
                try:
                    system.update(world)
                except Exception as e:
                    action_log.crash(type(system).__name__, e)
                if world.quitting:
                    return False
            world.projectiles = held + world.projectiles
    finally:
        world.figures = full
        world.time_fx_on = None
        world.time_fx_only = ()
        world.time_side_fx = True
        for f in full:
            state(f).frozen = False
    return True
