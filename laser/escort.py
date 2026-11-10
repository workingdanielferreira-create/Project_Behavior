"""
Escort FX: effects that leave the caster and guard an ally.

FX Studio, per effect: the "Escort" section (fx.escort, defaults
fxkit.ESCORT_DEFAULTS = FXK.ESCORT_DEFAULTS):

  enabled           the effect is an escort
  ms                how long its copies live once cast, wherever they are
  solo_contact_pct  guard / tracker Contact % with no tag partner

Who is guarded (Daniel 2026-11-10):
  * the caster is in a tag pair (laser/tag.py): the pair's ON-FIELD fighter.
    While the caster is in, that is the caster; after a Switch the escort
    carries over to the incoming partner (cast it on switch_out and the
    swords leave the caster for the partner).  A KO with a standing partner
    is a forced switch, so the escort moves on with it.  Full strength.
  * no standing tag partner (Solo, a single fighter, partner KO'd): the
    caster, with its guard / tracker Contact cut to solo_contact_pct %
    (Inst.esc_k).  Solo and Battle run the same rule.

The escort ends when its copies' `ms` runs out, or when no one is left to
guard (the guarded fighter is down with no partner to take over, or has
left the field / roster).

How it runs: the caster's lanes spawn the copies as usual (fxkit
Player._spawn_job); fxkit.update_figure then hands that tick's new copies
to a world escort (`adopt`) — one per caster per cast — and ticks every
escort guarding the fighter being updated (`tick`), inside that fighter's
side pass, so its guards catch that side's enemy shots and its hits are
queued for that side.  `step` (once per tick in Overlay._tick, after the
Switch) re-picks who each escort guards.  Escort copies are drawn with the
guarded fighter (Figure.draw, Overlay._paint_abs_layer).
"""

from . import config, fxkit

TICK_MS = config.TICK_MS

_W = None   # the world (draw has no world argument)


def _on(fx):
    e = fx.get("escort") if fx else None
    return bool(e and e.get("enabled"))


def _fielded(world, fig):
    if fig is None or fig.personality.hp <= 0 or getattr(fig, "bench_since", None) is not None:
        return False
    return any(fig is f for s in world.sides for f in s.figures)


def _pair_of(world, fig):
    for p in getattr(world, "tag_pairs", ()) or ():
        if p is not None and (p.on.fig is fig or p.off.fig is fig):
            return p
    return None


def guard_for(world, caster):
    """(fighter guarded, full strength) for an escort cast by `caster`;
    (None, False) when there is no one to guard."""
    p = _pair_of(world, caster)
    if p is not None:
        on, off = p.on.fig, p.off.fig
        if not _fielded(world, on):
            return None, False
        partner = off if on is caster else on
        if on is not caster:
            return on, True     # carried over to the partner
        return on, partner is not None and partner.personality.hp > 0
    if not _fielded(world, caster):
        return None, False
    return caster, False


class _Proxy:
    """Stands in for the caster's FxDriver while the escort plays: the
    caster's FX file (colours, library) and the escort's own player, so
    deflected copies and hits stay with the escort even with the caster
    benched."""

    def __init__(self, cfx, player):
        self.cfx = cfx
        self.player = player
        self.target = (0.0, 0.0)
        self.hurts = []
        self.hits_out = []
        self.drags_out = []
        self.pulls_out = []
        self.action = None
        self.frame = 0


class _Host(fxkit._Host):
    """The escort's host: placed on the guarded fighter (every anchor is
    its centre; the effect's own offset still applies), aiming at the
    guarded fighter's target, in the caster's colours."""

    def __init__(self, esc, fig, world):
        esc.proxy.target, esc.proxy.hurts = fxkit.aim_for(fig, world)
        super().__init__(esc.proxy, fig, world)
        self.esc = esc
        self.lut = esc.caster.lut

    def anchor(self, name):
        if name == "target":
            return list(self.target)
        return [self.fig.x, self.fig.y]

    def on_hit(self, inst, damage, dx, dy, knockback, key):
        from . import unique as _unique
        c = self.esc.caster
        damage = float(damage) * _unique.out_mult(c) * _unique.inst_dmg_mult(inst)
        self.drv.hits_out.append((key, float(damage), dx, dy, float(knockback or 0), inst.fx.get("tag", ""), inst))


class Escort:
    __slots__ = ("caster", "proxy", "player", "guard", "full", "last", "host")

    def __init__(self, caster, drv):
        self.caster = caster
        self.player = fxkit.Player()
        self.proxy = _Proxy(drv.cfx, self.player)
        self.guard = caster
        self.full = False
        self.last = -1
        self.host = None


def _lanes(drv):
    return [drv.player, drv.clane[0]] + [ln[0] for ln in drv.rlanes] + drv.stack_players()


def adopt(fig, world, drv):
    """Hand this tick's new escort copies from fig's lanes to a new world
    escort (they live `ms` from now, wherever the guarded fighter is)."""
    got = []
    for pl in _lanes(drv):
        mine = [i for i in pl.insts if _on(i.src or i.fx)]
        if mine:
            pl.insts = [i for i in pl.insts if not _on(i.src or i.fx)]
            got.extend(mine)
    if not got:
        return
    esc = Escort(fig, drv)
    esc.player._fms = drv.player._fms
    esc.guard, esc.full = guard_for(world, fig)
    if esc.guard is None:
        return
    for inst in got:
        e = (inst.src or inst.fx)["escort"]
        inst.cont = inst.open = inst.run = False
        inst.life = inst.age + max(1, int(round(float(e.get("ms") or 0) / TICK_MS)))
        inst.esc_k = 1.0 if esc.full else max(0.0, float(e.get("solo_contact_pct", 100))) / 100.0
    esc.player.insts = got
    esc.last = world.global_tick   # already ticked this tick in the caster's lane
    if not hasattr(world, "escorts") or world.escorts is None:
        world.escorts = []
    world.escorts.append(esc)


def step(world):
    """Once per tick (Overlay._tick, after the Switch): re-pick who each
    escort guards; drop finished escorts and ones with no one to guard."""
    global _W
    _W = world
    keep = []
    for esc in getattr(world, "escorts", None) or ():
        if not esc.player.insts and not esc.player.pending:
            continue
        g, full = guard_for(world, esc.caster)
        if g is None:
            continue
        if g is not esc.guard or full != esc.full:
            esc.guard, esc.full = g, full
            for inst in esc.player.insts:
                e = (inst.src or inst.fx).get("escort") or {}
                inst.esc_k = 1.0 if full else max(0.0, float(e.get("solo_contact_pct", 100))) / 100.0
        keep.append(esc)
    world.escorts = keep


def tick(fig, world, frozen=False):
    """Tick every escort guarding `fig` (from its side pass)."""
    for esc in getattr(world, "escorts", None) or ():
        if esc.guard is not fig or esc.last == world.global_tick:
            continue
        esc.last = world.global_tick
        host = _Host(esc, fig, world)
        esc.host = host
        esc.player.tick((), host, 0, 1, TICK_MS, t_prev=0, frozen=frozen)
        px = esc.proxy
        hits, px.hits_out = px.hits_out, []
        drags, px.drags_out = px.drags_out, []
        if world.battle_mode:
            if hits:
                world.queue_fx_hits(hits)
            if drags:
                world.queue_fx_drags(drags)


def reset(world):
    world.escorts = []


def draw(p, fig, layer, hidden=False):
    """Escort copies guarding `fig`, on `layer` (with the fighter's own FX)."""
    w = _W
    if w is None:
        return
    from . import speedband as _speedband
    from . import blink as _blink
    for esc in getattr(w, "escorts", None) or ():
        host = esc.host
        if esc.guard is not fig or host is None or not esc.player.insts:
            continue
        host.fig = fig
        ps_tick = host.pscale
        if _speedband._W is not None:
            host.pscale = fig._position_scale()
        try:
            esc.player.draw(p, host, layer, hidden or _blink.gone(fig))
        finally:
            host.pscale = ps_tick
