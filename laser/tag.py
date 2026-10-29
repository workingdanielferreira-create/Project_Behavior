"""
Tag battle state and the Switch action.

Every fighter is "single" by default: it fights on its own.  Two slots on
the same team that are both set to "tag" in the start menu
(laser/roster.py) are LINKED as a tag pair: one fights on the field, the
other waits on the bench, off screen and frozen — out of every system and
snapshot, so it can't act or be hit, and its HP, cooldowns and timers wait
(its cooldown clock leaves bench time out, see unique.cd_now).

Switch is the action that swaps them: the benched fighter comes in and the
on-field one goes out.  It is authored per character:

  * Rig Forge   — the `switch_in` animation (incoming fighter) and the
                  `switch_out` animation (outgoing fighter).
  * FX Studio   — each one's FX (they play with the animation like any
                  action's), and on `switch_in`: the trigger conditions
                  (ANY / ALL) and Cooldown ms.  The conditions are read
                  against the ON-FIELD partner — its HP, its target, hits it
                  took ... — since the incoming fighter is not in the fight.

A Switch starts when the benched fighter's switch_in conditions pass or its
"Tag in" hotkey is pressed, no sooner than the cooldown after the last one,
and only while the on-field fighter is free (not mid ultimate / special /
defend / clash).  The outgoing fighter plays switch_out where it stands;
when that ends the incoming fighter takes its place (same spot, same
facing) and plays switch_in, and the outgoing one goes to the bench.  A
missing animation is skipped.

KO: when the on-field fighter falls and its partner is still standing, the
partner switches in at once (conditions and cooldown skipped, no
switch_out).  The team — in Solo, the run — only ends when both are down.

World-level and run once per tick before refresh_battle, so Solo and Battle
go through the same code.
"""

from . import actions, config, modes, unique
from . import roster as _roster

TICK_MS = config.TICK_MS
OUT_TIMEOUT_TICKS = int(6000 / TICK_MS)   # a switch_out that never ends


def can_tag(key):
    """Only Rig Forge characters author switch_in / switch_out."""
    m = modes.MODE_REGISTRY.get(key) if key else None
    ch = getattr(m, "character", None) if m is not None else None
    return bool(ch and ch.get("_package"))


class TagPair:
    """A linked pair on one team: `on` is the slot fighting, `off` the slot
    on the bench (roster.Slot objects)."""

    __slots__ = ("team", "on", "off", "phase", "phase_tick", "cooldown_until", "request")

    def __init__(self, team, on, off):
        self.team = team
        self.on = on
        self.off = off
        self.phase = "idle"          # "idle" | "out" (outgoing plays switch_out)
        self.phase_tick = 0
        self.cooldown_until = 0      # world tick
        self.request = False         # "Tag in" hotkey pressed, waiting to start

    def slots(self):
        return (self.on, self.off)

    def same_link(self, a, b):
        return {self.on.index, self.off.index} == {a.index, b.index}


def build_pairs(world, slots, old_pairs):
    """One TagPair (or None) per team for `slots`; a pair that is still the
    same two slots keeps which one is on the field and its cooldown."""
    pairs = []
    for t in range(_roster.TEAM_COUNT):
        ts = _roster.tag_pair(slots, t, can_tag)
        if ts is None:
            pairs.append(None)
            continue
        a, b = ts
        old = old_pairs[t] if t < len(old_pairs) else None
        if old is not None and old.same_link(a, b):
            on = a if old.on.index == a.index else b
            off = b if on is a else a
            p = TagPair(t, on, off)
            p.cooldown_until = old.cooldown_until
        else:
            on, off = a, b           # first pick starts on the field
            p = TagPair(t, on, off)
        # A fallen on-field fighter with a standing partner: partner is on.
        if _ko(on.fig) and not _ko(off.fig):
            p.on, p.off = off, on
        pairs.append(p)
    return pairs


def _ko(fig):
    return fig is None or fig.personality.hp <= 0


def bench(fig, now):
    if fig is not None and fig.bench_since is None:
        fig.bench_since = now
        r = getattr(fig, "act", None)
        if r is not None:
            r.stop(fig)
        fig.combat.action_anim = None
        fig.combat.action_idx = 0
        fig.combat.hit_pending = False
        fig.aim = None


def unbench(fig, now):
    if fig is not None and fig.bench_since is not None:
        fig.bench_ticks += max(0, now - fig.bench_since)
        fig.bench_since = None


def request(world, slot_index):
    """"Tag in" hotkey for slot `slot_index`: queue a Switch when that slot
    is the benched half of a pair (no-op otherwise)."""
    for p in getattr(world, "tag_pairs", ()) or ():
        if p is not None and p.off.index == slot_index:
            if _ko(p.off.fig):
                world.notice = ("Slot %s is down — can't tag in" % p.off.name, 90)
            elif world.global_tick < p.cooldown_until and p.phase == "idle":
                left = (p.cooldown_until - world.global_tick) * TICK_MS / 1000.0
                world.notice = ("Switch cooling down (%.1fs)" % left, 60)
            else:
                p.request = True
            return


def covers_ko(world, fig):
    """True when `fig` is a pair's on-field fighter whose partner can still
    come in — its fall is then a Switch, not a loss (World.on_figure_death)."""
    for p in getattr(world, "tag_pairs", ()) or ():
        if p is not None and p.on.fig is fig and not _ko(p.off.fig):
            return True
    return False


def _free(fig):
    """The on-field fighter can be switched out now."""
    r = getattr(fig, "act", None)
    if r is None:
        return True
    if r.forced is not None:
        return False
    if r.playing is not None and actions._kind(r.playing) == "triggered":
        return False
    return fig.combat.vc_phase == 0


def _conds_pass(world, on_fig, off_fig):
    """off_fig's switch_in trigger conditions, read against on_fig."""
    cfg = actions._cfg(off_fig, "switch_in")
    if not cfg.get("conditions"):
        return False, cfg, None
    r = getattr(on_fig, "act", None)
    if r is None or r.ctx is None or r.ctx_tick is None or world.global_tick - r.ctx_tick > 2:
        return False, cfg, None
    return r._conds_pass(on_fig, "switch_in", cfg, r.ctx), cfg, r


def _cooldown_ticks(off_fig):
    cfg = actions._cfg(off_fig, "switch_in")
    return int(float(cfg.get("cooldown_ms") or 0) / TICK_MS)


def _swap(world, p, ko=False):
    """The benched fighter takes the on-field one's place and plays
    switch_in; the on-field one goes to the bench."""
    now = world.global_tick
    side = world.sides[p.team]
    out_fig, in_fig = p.on.fig, p.off.fig
    if out_fig in side.figures:
        i = side.figures.index(out_fig)
        side.figures[i] = in_fig
    else:
        real = [f for f in side.figures if not unique.is_clone(f)]
        i = len(real)
        side.figures.insert(i, in_fig)
    if out_fig is not None:
        it, ot = in_fig.transform, out_fig.transform
        it.x, it.y = ot.x, ot.y
        it.facing_left = ot.facing_left
        it.init = ot.init
        in_fig.trail.clear()
    if out_fig in world._dead:
        world._dead.remove(out_fig)
    unbench(in_fig, now)
    if not ko:
        bench(out_fig, now)
    p.on, p.off = p.off, p.on
    p.phase = "idle"
    p.request = False
    p.cooldown_until = now + _cooldown_ticks(in_fig)
    if side.figures and side.figures[0] is in_fig:
        side.mode_key = in_fig.mode.key
    if "switch_in" in in_fig.render.bundle.extra:
        actions.force_action(in_fig, world, "switch_in")
    world.notice = ("Team %d: %s in" % (p.team + 1, _name(in_fig)), 60)


def _name(fig):
    ch = getattr(fig.mode, "character", None) or {}
    return str(ch.get("display_name") or fig.mode.key).replace("_", " ")


def step(world):
    """Once per tick, before refresh_battle (Overlay._tick)."""
    now = world.global_tick
    frozen = getattr(world, "cinematic_frozen", None)
    for p in getattr(world, "tag_pairs", ()) or ():
        if p is None:
            continue
        on_fig, off_fig = p.on.fig, p.off.fig
        if on_fig is None or off_fig is None:
            continue
        # KO: the partner comes in at once (skips conditions and cooldown).
        if _ko(on_fig):
            if not _ko(off_fig):
                _swap(world, p, ko=True)
            continue
        if _ko(off_fig):
            p.request = False
            continue
        if frozen is not None and frozen(p.team):
            continue
        if p.phase == "out":
            r = getattr(on_fig, "act", None)
            if (r is None or r.playing != "switch_out"
                    or now - p.phase_tick > OUT_TIMEOUT_TICKS):
                _swap(world, p)
            continue
        if now < p.cooldown_until:
            p.request = False
            continue
        if not on_fig.transform.init or not _free(on_fig):
            continue                 # a queued hotkey request waits for it
        fire = p.request
        cfg = r = None
        if not fire:
            fire, cfg, r = _conds_pass(world, on_fig, off_fig)
            if fire:
                # Counters that belong to switch_in restart (hp_below fires
                # once per threshold) on the fighter whose state it read.
                r.mark_fired(on_fig, "switch_in", cfg, r.ctx, now)
        if not fire:
            continue
        p.request = False
        if "switch_out" in on_fig.render.bundle.extra and actions.force_action(on_fig, world, "switch_out"):
            p.phase = "out"
            p.phase_tick = now
        else:
            _swap(world, p)


def status(world, slot):
    """HP bar status of a slot: 'on', 'bench', 'ko' or 'off' (empty)."""
    fig = slot.fig
    if fig is None or not slot.char:
        return "off"
    if fig.personality.hp <= 0:
        return "ko"
    if fig.bench_since is not None:
        return "bench"
    return "on"


def partner_of(world, slot):
    for p in getattr(world, "tag_pairs", ()) or ():
        if p is not None and slot in p.slots():
            return p.off if p.on is slot else p.on
    return None
