"""
Tag battle state and the Switch action.

Every fighter is "single" by default: it fights on its own.  Two slots on
the same team linked as Tag partners in the start menu (laser/roster.py;
a team can hold more than one pair) form a tag pair, three linked as a Trio
form a trio: one fights on the field, the
other(s) wait on the bench, off screen and frozen — out of every system and
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

Trio (Daniel 2026-11-17): the rotation (roster.ROTATIONS, per trio) picks
who comes in: 1 > 2 > 3 > 1 (default), ping-pong, healthiest benched or
random benched; KO'd members are skipped.  A member's own Tag in hotkey or
a click on its benched HP card brings THAT fighter in, and the rotation
carries on from it.  switch_in conditions / cooldown are the incoming
member's.

KO: when the on-field fighter falls and a team-mate on its bench is still
standing, the next one by the rotation switches in at once (conditions and
cooldown skipped, no switch_out).  The team — in Solo, the run — only ends
when all of them are down.

World-level and run once per tick before refresh_battle, so Solo and Battle
go through the same code.
"""

import random

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
    """A tag group on one team: a linked pair (2) or a trio (3).  `members`
    = its roster.Slots in rotation order (a pair: first pick first), `on`
    = the slot fighting, the rest wait on the bench.  `rot` = who a Switch
    brings in (roster.ROTATIONS; a pair always has one choice).  `off` =
    the member the next Switch brings in (the pair's partner), so pair code
    reads as before."""

    __slots__ = ("team", "members", "on", "rot", "dir", "rng", "phase", "phase_tick",
                 "cooldown_until", "request", "incoming")

    def __init__(self, team, members, on, rot="cycle"):
        self.team = team
        self.members = list(members)
        self.on = on
        self.rot = rot if rot in _roster.ROTATIONS else "cycle"
        self.dir = 1                 # ping-pong direction through `members`
        self.rng = random.Random(1009 * (members[0].index + 1) + 17 * len(members))
        self.phase = "idle"          # "idle" | "out" (outgoing plays switch_out)
        self.phase_tick = 0
        self.cooldown_until = 0      # world tick
        self.request = None          # Tag in asked: True = next by rotation, or a Slot
        self.incoming = None         # the Slot a running switch_out hands over to

    @property
    def trio(self):
        return len(self.members) == 3

    def slots(self):
        return tuple(self.members)

    def benched(self):
        return [m for m in self.members if m is not self.on]

    @property
    def off(self):
        return self.pick_next(peek=True) or (self.benched() or [self.on])[0]

    def same_link(self, a, b):
        # `src` = the slot's index before a start-menu slot removal
        # (roster.remove_slot) moved it up; World.apply_roster resets it.
        return {m.index for m in self.members} == {a.src, b.src}

    def same_group(self, members):
        return (len(members) == len(self.members)
                and {m.index for m in self.members} == {m.src for m in members})

    def pick_next(self, peek=False):
        """The benched member the rotation brings in next (standing ones
        only), or None.  peek = don't advance random / ping-pong state."""
        up = [m for m in self.benched() if not _ko(m.fig)]
        if not up:
            return None
        if len(up) == 1:
            return up[0]
        n = len(self.members)
        i = self.members.index(self.on) if self.on in self.members else 0
        if self.rot == "healthiest":
            def frac(m):
                pf = m.fig.personality
                return pf.hp / float(max(1, pf.max_hp))
            best = max(frac(m) for m in up)
            for k in range(1, n):            # ties: rotation order
                m = self.members[(i + k) % n]
                if m in up and frac(m) >= best - 1e-9:
                    return m
        if self.rot == "random":
            if peek:
                return None if not up else _Peek(self, up).pick()
            return up[self.rng.randrange(len(up))]
        if self.rot == "pingpong":
            d = self.dir
            j = i
            for _ in range(2 * n):
                if not (0 <= j + d < n):
                    d = -d
                j += d
                if self.members[j] in up:
                    if not peek:
                        self.dir = d
                    return self.members[j]
        for k in range(1, n):                # cycle 1 > 2 > 3 > 1
            m = self.members[(i + k) % n]
            if m in up:
                return m
        return up[0]


class _Peek:
    """Random rotation, peeked: the pick the rng would make, without
    advancing it (the Ready Gate / HUD only need to know someone can come)."""

    def __init__(self, p, up):
        self.p, self.up = p, up

    def pick(self):
        st = self.p.rng.getstate()
        m = self.up[self.p.rng.randrange(len(self.up))]
        self.p.rng.setstate(st)
        return m


def build_pairs(world, slots, old_pairs):
    """A TagPair for every linked pair and trio in `slots`
    (roster.tag_groups order = colour); a group that is still the same
    slots keeps who is on the field, its cooldown and rotation state."""
    pairs = []
    old_pairs = [p for p in (old_pairs or []) if p is not None]
    for g in _roster.tag_groups(slots, can_tag):
        g = list(g)
        rot = g[0].rot if len(g) == 3 else "cycle"
        old = next((p for p in old_pairs if p.same_group(g)), None)
        if old is not None:
            on = next((m for m in g if m.src == old.on.index), g[0])
            p = TagPair(g[0].team, g, on, rot)
            p.cooldown_until = old.cooldown_until
            p.dir = old.dir
            p.rng = old.rng
        else:
            p = TagPair(g[0].team, g, g[0], rot)  # first pick / rotation 1 starts
        # A fallen on-field fighter with a standing team-mate: that one is on.
        if _ko(p.on.fig):
            nxt = p.pick_next()
            if nxt is not None:
                p.on = nxt
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


def group_of(world, slot):
    """The tag pair / trio holding roster slot `slot`, or None."""
    for p in getattr(world, "tag_pairs", ()) or ():
        if p is not None and slot in p.members:
            return p
    return None


def request(world, slot_index):
    """"Tag in" for slot `slot_index` (its hotkey, or a click on its
    benched HP card): queue a Switch that brings THAT fighter in (a trio
    then rotates on from it).  True when queued."""
    for p in getattr(world, "tag_pairs", ()) or ():
        if p is None:
            continue
        m = next((x for x in p.benched() if x.index == slot_index), None)
        if m is None:
            continue
        if _ko(m.fig):
            world.notice = ("Slot %s is down — can't tag in" % m.name, 90)
        elif p.phase != "idle":
            return False
        elif world.global_tick < p.cooldown_until:
            left = (p.cooldown_until - world.global_tick) * TICK_MS / 1000.0
            world.notice = ("Switch cooling down (%.1fs)" % left, 60)
        else:
            p.request = m
            return True
        return False
    return False


def request_next(world, p):
    """The TAG icon: queue a Switch to whoever the rotation brings next."""
    if p is None or p.phase != "idle" or world.global_tick < p.cooldown_until:
        return False
    if p.pick_next(peek=True) is None and not any(not _ko(m.fig) for m in p.benched()):
        return False
    p.request = True
    return True


def covers_ko(world, fig):
    """True when `fig` is a group's on-field fighter and a team-mate on its
    bench can still come in — its fall is then a Switch, not a loss
    (World.on_figure_death)."""
    for p in getattr(world, "tag_pairs", ()) or ():
        if p is not None and p.on.fig is fig and any(not _ko(m.fig) for m in p.benched()):
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


def _swap(world, p, in_slot, ko=False):
    """Benched `in_slot` takes the on-field fighter's place and plays
    switch_in; the on-field one goes to the bench."""
    now = world.global_tick
    side = world.sides[p.team]
    out_fig, in_fig = p.on.fig, in_slot.fig
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
    p.on = in_slot
    p.phase = "idle"
    p.request = None
    p.incoming = None
    p.cooldown_until = now + _cooldown_ticks(in_fig)
    if side.figures and side.figures[0] is in_fig:
        side.mode_key = in_fig.mode.key
    if "switch_in" in in_fig.render.bundle.extra:
        actions.force_action(in_fig, world, "switch_in")
    world.notice = ("Team %d: %s in" % (p.team + 1, _name(in_fig)), 60)
    # World Camera (laser/camera.py): switch-in shot on the incoming
    # partner (view only; a running KO shot keeps priority).
    shot = getattr(world, "camera_shot", None)
    if shot is not None:
        shot("switch_in", fig=in_fig)


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
        on_fig = p.on.fig
        if on_fig is None or any(m.fig is None for m in p.members):
            continue
        # KO: the next standing team-mate by the rotation comes in at once
        # (skips conditions and cooldown).
        if _ko(on_fig):
            nxt = p.pick_next()
            if nxt is not None:
                _swap(world, p, nxt, ko=True)
            continue
        if not any(not _ko(m.fig) for m in p.benched()):
            p.request = None
            continue
        if frozen is not None and frozen(p.team):
            continue
        if p.phase == "out":
            r = getattr(on_fig, "act", None)
            if (r is None or r.playing != "switch_out"
                    or now - p.phase_tick > OUT_TIMEOUT_TICKS):
                inc = p.incoming
                if inc is None or _ko(inc.fig) or inc is p.on:
                    inc = p.pick_next()
                if inc is not None:
                    _swap(world, p, inc)
                else:
                    p.phase = "idle"
            continue
        if now < p.cooldown_until:
            p.request = None
            continue
        if not on_fig.transform.init or not _free(on_fig):
            continue                 # a queued Tag in waits for it
        req = p.request
        if req is not None and req is not True and (_ko(req.fig) or req is p.on):
            req = p.request = None
        inc = req if (req is not None and req is not True) else None
        fire = req is not None
        if not fire:
            # switch_in conditions of the member the rotation brings next,
            # read against the on-field fighter.
            cand = p.pick_next(peek=True)
            if cand is None:
                continue
            fire, cfg, r = _conds_pass(world, on_fig, cand.fig)
            if fire:
                # Counters that belong to switch_in restart (hp_below fires
                # once per threshold) on the fighter whose state it read.
                r.mark_fired(on_fig, "switch_in", cfg, r.ctx, now)
        if not fire:
            continue
        if inc is None:
            inc = p.pick_next()
        else:
            # A hand-picked member: the rotation carries on from it.
            pass
        if inc is None:
            p.request = None
            continue
        p.request = None
        p.incoming = inc
        if "switch_out" in on_fig.render.bundle.extra and actions.force_action(on_fig, world, "switch_out"):
            p.phase = "out"
            p.phase_tick = now
        else:
            _swap(world, p, inc)


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
    """A team-mate in slot's tag pair / trio (the one a Switch brings in if
    slot is on the field, else the on-field one), or None."""
    p = group_of(world, slot)
    if p is None:
        return None
    return p.off if p.on is slot else p.on
