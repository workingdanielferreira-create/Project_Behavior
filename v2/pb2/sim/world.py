"""World — the simulation.

Contains ZERO Qt.  This is deliberate and load-bearing: the whole simulation
can be run, tested and checksummed headless, which is what makes the golden
test possible.  Only pb2/render and pb2/app import Qt.

Parity rules carried forward from v1 (both proven, both kept):
  * Solo/Battle is not a branch.  "Battle" is simply both sides fielded.
    The pipeline runs once per fielded side against a frozen snapshot of the
    other, so neither side can see a half-updated world.
  * Cross-side knockback is queued and delivered on the following tick.

New in v2:
  * The tick is pure.  Rendering reads state and writes nothing, so a frame
    that is never painted produces identical simulation results.
  * Everything random comes from the world seed.
"""

import math

from ..core.attributes import AttributeSet
from ..core.events import EventBus
from ..core.intent import Intent, MOVE, ABILITY
from ..core.rng import Rng, derive_seed
from .actor import Actor, AbilityInstance
from .grid import SpatialGrid
from .motes import (MotePool, F_ALIVE, F_HITS, K_SPARK, HAVE_NUMPY)
from .scaling import BilinearField
from .ability import PhaseRunner

__all__ = ["World", "SideState"]


class SideState:
    __slots__ = ("index", "actors", "snapshot")

    def __init__(self, index):
        self.index = index
        self.actors = []
        self.snapshot = ()

    def living(self):
        return [a for a in self.actors if a.alive]


class World:
    def __init__(self, seed=1, width=1920, height=1080, config=None):
        self.cfg = dict(DEFAULTS)
        if config:
            self.cfg.update(config)

        self.seed = int(seed)
        self.rng = Rng(derive_seed(self.seed, "world"))
        self.width = width
        self.height = height

        self.tick = 0
        self.sides = (SideState(0), SideState(1))
        self.motes = MotePool(self.cfg["mote_capacity"])
        self.grid = SpatialGrid(self.cfg["grid_cell"])
        self.bus = EventBus(log_enabled=self.cfg["log_events"])

        self.size_field = BilinearField(self.cfg["size_corners"], width, height,
                                        self.cfg["size_scaling"])
        self.speed_field = BilinearField(self.cfg["speed_corners"], width, height,
                                         self.cfg["speed_scaling"])

        self.cursor = (width * 0.5, height * 0.5)
        self.cursor_active = True          # Solo: the cursor is the enemy
        self.hitstop_ticks = 0

        self._next_id = 1
        self._actor_index = {}
        self._knockback = []               # delivered next tick
        self._timers = []                  # (due_tick, callback)
        self._cue_requests = []            # drained by the render layer
        self._cue_ids = {}
        self._faults = []
        self.strict = self.cfg["strict"]   # fail loud in dev

        self.stats = {"actors": 0, "motes": 0, "cues": 0, "faults": 0}

    # ==================================================================
    # identity / lookup
    # ==================================================================
    def new_id(self):
        i = self._next_id
        self._next_id += 1
        return i

    def actor_by_id(self, ident):
        return self._actor_index.get(ident)

    def _reindex(self):
        self._actor_index = {a.id: a for s in self.sides for a in s.actors}

    def all_actors(self):
        return list(self.sides[0].actors) + list(self.sides[1].actors)

    def living_actors(self):
        return [a for a in self.all_actors() if a.alive]

    @property
    def battle_mode(self):
        """Not a flag anyone sets — derived, exactly as in v1."""
        return bool(self.sides[0].living() and self.sides[1].living())

    def enemies_of(self, actor):
        return [a for a in self.sides[1 - actor.side].actors if a.alive]

    def allies_of(self, actor):
        return [a for a in self.sides[actor.side].actors
                if a.alive and a is not actor]

    def target_for(self, actor):
        """Nearest living enemy; in Solo, the cursor."""
        foes = self.enemies_of(actor)
        if foes:
            best, bd = None, 1e18
            for f in foes:
                d = (f.x - actor.x) ** 2 + (f.y - actor.y) ** 2
                if d < bd:
                    best, bd = f, d
            return best
        if self.cursor_active:
            return self.cursor
        return None

    @staticmethod
    def position_of(target):
        if isinstance(target, tuple):
            return target
        return (target.x, target.y)

    # ==================================================================
    # spawning
    # ==================================================================
    def spawn_actor(self, chardef, side=0, x=None, y=None, brains=None):
        ident = self.new_id()
        attrs = AttributeSet(chardef.attributes)
        a = Actor(ident, chardef, side,
                  x if x is not None else self.width * (0.25 if side == 0 else 0.75),
                  y if y is not None else self.height * 0.5,
                  attrs, Rng(derive_seed(self.seed, "actor", ident)))
        a.world = self
        a.spawn_tick = self.tick
        a.visual = dict(chardef.visual)
        for t in chardef.tags:
            a.add_tag(t)

        for spec in chardef.abilities:
            inst = AbilityInstance(spec["key"], spec["impl"](), spec.get("params", {}))
            inst.gate = spec.get("gate")
            inst.priority = float(spec.get("priority", 0.0))
            a.grant(inst)
            # reactive abilities subscribe to the bus
            hook = getattr(inst.impl, "on_damaged", None)
            if hook is not None:
                self.bus.on("actor.damaged",
                            lambda ev, i=inst, ac=a, h=hook: h(i, ac, self, ev))

        a.brains = list(brains) if brains else list(chardef.default_brains())
        self.sides[side].actors.append(a)
        self._reindex()
        self.bus.emit("actor.spawned", tick=self.tick, actor=ident, side=side)
        return a

    def spawn_summon(self, owner, x, y, params):
        """Summons are Actors — no separate clone system, unlike v1."""
        chardef = params.get("summon_def") or owner.archetype
        a = self.spawn_actor(chardef, owner.side, x, y)
        a.add_tag("kind.summon")
        a.attrs.set_base("hp_max", float(params.get("summon_hp", 10)))
        a.attrs.set_base("hp", float(params.get("summon_hp", 10)))
        a.attrs.set_base("scale", owner.attrs.get("scale") *
                         float(params.get("summon_scale", 0.6)))
        if params.get("summon_stationary", True):
            a.add_tag("state.stationary")
        life = int(params.get("summon_life", 0))
        if life:
            self.schedule(life, lambda ac=a: self.despawn(ac))
        self.bus.emit("actor.summoned", tick=self.tick,
                      actor=a.id, owner=owner.id)
        return a

    def despawn(self, actor):
        if actor.alive:
            actor.alive = False
            self.bus.emit("actor.despawned", tick=self.tick, actor=actor.id)

    def on_actor_death(self, actor, source=None):
        """Death routing.  Battle: remove the fallen, survivor continues.
        Solo: the run ends.  Same rule as v1."""
        self.bus.emit("actor.died", tick=self.tick, actor=actor.id,
                      killer=(source.id if source else -1))
        self.request_cue("burst", actor, {"scale": 2.0}, actor)

    # ==================================================================
    # scheduling / deferred work
    # ==================================================================
    def schedule(self, delay, fn):
        self._timers.append((self.tick + max(1, int(delay)), fn))

    def queue_knockback(self, actor, vx, vy):
        self._knockback.append((actor.id, vx, vy))

    def hitstop(self, ticks):
        self.hitstop_ticks = max(self.hitstop_ticks, int(ticks))

    def fault(self, stage, key, actor_id):
        """A mechanic misbehaved.  In dev this raises; in shipping it logs.

        v1 swallowed every exception into a file, so a typo produced no
        symptom at all.  Strict mode is the fix.
        """
        import traceback
        detail = traceback.format_exc(limit=6)
        msg = "fault in %s: %s (actor %s) tick %d" % (stage, key, actor_id, self.tick)
        self._faults.append(msg + "\n" + detail)
        self.stats["faults"] += 1
        if self.strict:
            # Chain the real cause.  v1 swallowed exceptions into a log file,
            # so a typo produced no symptom at all -- the single most costly
            # failure mode in the old engine.
            raise RuntimeError(msg + "\n" + detail)

    def faults(self):
        return list(self._faults)

    # ==================================================================
    # geometry helpers
    # ==================================================================
    def clamp_to_arena(self, x, y):
        m = self.cfg["margin"]
        if self.cfg["arena_oval"] and self.battle_mode:
            cx, cy = self.width / 2.0, self.height / 2.0
            rx = self.width / 2.0 - m
            ry = self.height / 2.0 - m
            dx, dy = (x - cx) / rx, (y - cy) / ry
            d = math.hypot(dx, dy)
            if d > 1.0:
                x, y = cx + dx / d * rx, cy + dy / d * ry
            return x, y
        return (min(max(x, m), self.width - m),
                min(max(y, m), self.height - m))

    def incoming_threat(self, actor, radius):
        """0..1 danger from hostile motes closing on `actor`.

        Vectorised: this is queried by every ability score of every actor
        every tick, so a Python loop here is O(actors x abilities x motes)
        and was the top profile entry before batching it.
        """
        idx = self.motes.hitting_indices(side=1 - actor.side)
        if len(idx) == 0:
            return 0.0
        a = self.motes._arrays
        r2 = radius * radius
        if HAVE_NUMPY:
            import numpy as np
            dx = a["x"][idx] - actor.x
            dy = a["y"][idx] - actor.y
            d2 = dx * dx + dy * dy
            closing = -(dx * a["vx"][idx] + dy * a["vy"][idx])
            m = (d2 <= r2) & (closing > 0.0)
            if not m.any():
                return 0.0
            return float((1.0 - np.sqrt(d2[m] / r2)).max())
        worst = 0.0
        for i in idx:
            i = int(i)
            dx, dy = a["x"][i] - actor.x, a["y"][i] - actor.y
            d2 = dx * dx + dy * dy
            if d2 > r2:
                continue
            if -(dx * a["vx"][i] + dy * a["vy"][i]) <= 0:
                continue
            worst = max(worst, 1.0 - (d2 / r2) ** 0.5)
        return worst

    def threat_angle(self, actor):
        """Angle of the nearest closing hostile mote, or None."""
        best, bd = None, 1e18
        a = self.motes._arrays
        for i in self.motes.hitting_indices(side=1 - actor.side):
            i = int(i)
            dx, dy = a["x"][i] - actor.x, a["y"][i] - actor.y
            d2 = dx * dx + dy * dy
            if d2 < bd:
                bd, best = d2, math.atan2(dy, dx)
        return best

    def deflect_motes(self, actor, reach, arc, reflect=True):
        """Parry: reverse or destroy hostile motes inside the guard arc."""
        a = self.motes._arrays
        n = 0
        for i in self.motes.hitting_indices(side=1 - actor.side):
            i = int(i)
            dx, dy = a["x"][i] - actor.x, a["y"][i] - actor.y
            if dx * dx + dy * dy > reach * reach:
                continue
            ang = _wrap(math.atan2(dy, dx) - actor.facing)
            if abs(ang) > arc / 2.0:
                continue
            if reflect:
                a["vx"][i] = -a["vx"][i]
                a["vy"][i] = -a["vy"][i]
                a["side"][i] = actor.side
                a["owner"][i] = actor.id
            else:
                self.motes.kill(i)
            n += 1
            self.request_cue("spark", actor,
                             {"x": float(a["x"][i]), "y": float(a["y"][i])}, actor)
        if n:
            self.bus.emit("mote.deflected", tick=self.tick,
                          actor=actor.id, count=n)
        return n

    # ==================================================================
    # cues (cosmetic only — never gameplay)
    # ==================================================================
    def cue_id(self, name):
        i = self._cue_ids.get(name)
        if i is None:
            i = len(self._cue_ids) + 1
            self._cue_ids[name] = i
        return i

    def color_id(self, actor, slot):
        pal = actor.visual.get("palette", {})
        c = pal.get(slot) or pal.get("primary") or 0xFFFFFF
        return int(c) if isinstance(c, int) else 0xFFFFFF

    def request_cue(self, name, anchor, params, source=None):
        """Queue a cosmetic request.  The sim never renders; it only asks.

        A cue can carry no gameplay consequence — that separation is
        structural, which is what kills v1's can_hit FX-layer confusion.
        """
        self._cue_requests.append((name, anchor.id if anchor else -1,
                                   anchor.x if anchor else 0.0,
                                   anchor.y if anchor else 0.0,
                                   params, self.tick))
        self.stats["cues"] += 1

    def drain_cues(self):
        out, self._cue_requests = self._cue_requests, []
        return out

    # ==================================================================
    # THE TICK
    # ==================================================================
    def step(self):
        """Advance exactly one simulation tick.  Pure: no painting, no
        wall-clock, no OS randomness."""
        self.tick += 1

        if self.hitstop_ticks > 0:
            self.hitstop_ticks -= 1
            self._run_timers()
            return

        self._refresh_snapshots()
        self._deliver_knockback()

        # one identical pass per fielded side — this is the parity guarantee
        for side in self.sides:
            if not side.actors:
                continue
            for actor in list(side.actors):
                if not actor.alive:
                    continue
                self._think(actor)
                self._execute(actor)
                self._move(actor)

        self._tick_motes()
        self._collide()
        self._cursor_contact()
        self._run_timers()
        self.bus.drain()
        self._cull()

        self.stats["actors"] = len(self.living_actors())
        self.stats["motes"] = self.motes.alive_count()

    def _refresh_snapshots(self):
        for s in self.sides:
            s.snapshot = tuple(a.snapshot() for a in s.actors if a.alive)

    def _deliver_knockback(self):
        if not self._knockback:
            return
        pending, self._knockback = self._knockback, []
        for ident, vx, vy in pending:
            a = self.actor_by_id(ident)
            if a is not None and a.alive:
                a.vx += vx
                a.vy += vy

    def _think(self, actor):
        actor.intent.clear()
        for b in actor.brains:              # ordered: first writer wins ties
            try:
                b.think(actor, self, actor.intent)
            except Exception:
                self.fault("think", getattr(b, "KEY", "?"), actor.id)

    def _execute(self, actor):
        if actor.hitstun > 0:
            actor.hitstun -= 1

        # passive abilities run every tick regardless of selection
        for inst in actor.ordered_abilities():
            pt = getattr(inst.impl, "passive_tick", None)
            if pt is not None:
                try:
                    pt(inst, actor, self)
                except Exception:
                    self.fault("passive", inst.key, actor.id)
            if inst.cooldown > 0:
                inst.cooldown -= 1

        # advance the currently active ability
        for inst in actor.ordered_abilities():
            if not inst.active:
                continue
            try:
                inst.impl.tick(inst, actor, self)
            except Exception:
                self.fault("tick", inst.key, actor.id)
            if not PhaseRunner.advance(inst):
                self._end_ability(inst, actor)
            return                      # only one active body ability at a time

        # start the winner, if any
        key = actor.intent.ability_key
        if not key:
            return
        inst = actor.ability(key)
        if inst is None or not inst.ready():
            return
        if inst.gate is not None and not inst.gate.test(actor.tags):
            return
        self._start_ability(inst, actor)

    def _start_ability(self, inst, actor):
        inst.active = True
        inst.uses += 1
        inst.last_used = self.tick
        for t in inst.impl.BODY_TAGS:
            actor.add_tag(t)
            inst.tags_while_active.append(t)
        PhaseRunner.begin(inst)
        try:
            inst.impl.start(inst, actor, self)
        except Exception:
            self.fault("start", inst.key, actor.id)
        self.bus.emit("ability.started", tick=self.tick,
                      actor=actor.id, ability=inst.key)
        if not inst.params.get("phases") and \
                int(inst.params.get("duration", 0)) <= 1:
            self._end_ability(inst, actor)

    def _end_ability(self, inst, actor):
        for t in inst.tags_while_active:
            actor.remove_tag(t)
        inst.tags_while_active = []
        inst.active = False
        inst.phase = None
        inst.phase_t = 0
        try:
            inst.impl.finish(inst, actor, self)
        except Exception:
            self.fault("finish", inst.key, actor.id)
        self.bus.emit("ability.ended", tick=self.tick,
                      actor=actor.id, ability=inst.key)

    def _move(self, actor):
        sf = self.speed_field.at(actor.x, actor.y)

        if not actor.busy and not actor.tags.has("state.stationary"):
            mx, my = actor.intent.normalized_move()
            spd = actor.attrs.get("move_speed")
            actor.vx += mx * spd * self.cfg["accel"]
            actor.vy += my * spd * self.cfg["accel"]

        actor.vx *= self.cfg["friction"]
        actor.vy *= self.cfg["friction"]

        actor.x += actor.vx * sf
        actor.y += actor.vy * sf
        actor.x, actor.y = self.clamp_to_arena(actor.x, actor.y)

        if actor.intent.face is not None:
            actor.facing = actor.intent.face
        elif abs(actor.vx) + abs(actor.vy) > 0.05:
            actor.facing = math.atan2(actor.vy, actor.vx)

        moving = (actor.vx * actor.vx + actor.vy * actor.vy) > 0.09
        new_anim = "run" if moving and not actor.busy else "idle"
        if actor.busy:
            new_anim = "attack"
        if new_anim != actor.anim:
            actor.anim, actor.anim_t = new_anim, 0
        else:
            actor.anim_t += 1          # NOT dilated — animation cadence is
                                       # explicitly excluded, as in v1

    def _tick_motes(self):
        self.motes.tick(speed_field=self.speed_field.sample,
                        gravity=self.cfg["gravity"],
                        bounds=(0, 0, self.width, self.height))
        if self.tick % 120 == 0:
            self.motes.compact()

    def _collide(self):
        """Broadphase by grid, then exact test.  Deterministic ordering."""
        living = self.living_actors()
        if not living:
            return
        self.grid.clear()
        for a in living:
            self.grid.insert(a.id, a.x, a.y)

        arr = self.motes._arrays
        from .effects import build_effects, apply_effects
        hurt = {a.id: a.attrs.get("hurt_radius") for a in living}
        for i in self.motes.hitting_indices():
            i = int(i)
            mx, my = float(arr["x"][i]), float(arr["y"][i])
            mside = int(arr["side"][i])
            mr = float(arr["radius"][i])
            for ident in self.grid.query(mx, my, mr + 40.0):
                a = self.actor_by_id(ident)
                if a is None or not a.alive or a.side == mside:
                    continue
                if a.tags.has("state.vanished"):
                    continue
                rr = mr + hurt.get(ident, 18.0)
                dx, dy = a.x - mx, a.y - my
                if dx * dx + dy * dy > rr * rr:
                    continue
                owner = self.actor_by_id(int(arr["owner"][i]))
                dmg = float(arr["damage"][i])
                if dmg > 0.0:
                    fx = build_effects([{"effect": "damage", "amount": dmg,
                                         "knockback": self.cfg["mote_knockback"],
                                         "hitstun": 3}])
                    apply_effects(fx, owner, a, self)
                self.request_cue("impact", a, {"x": mx, "y": my}, owner)
                if not (arr["flag"][i] & 4):        # F_PIERCE
                    self.motes.kill(i)
                break

    def _cursor_contact(self):
        """Solo mode: the cursor is the enemy.  Contact costs HP, exactly as
        in v1.  Routed through the damage Effect like everything else -- there
        is no separate cursor-damage path."""
        if not self.cursor_active or self.battle_mode:
            return
        cx, cy = self.cursor
        r = self.cfg["cursor_radius"]
        from .effects import build_effects, apply_effects
        for a in self.living_actors():
            cool = a.scratch.get("cursor_cool", 0)
            if cool > 0:
                a.scratch["cursor_cool"] = cool - 1
                continue
            rr = r + a.attrs.get("hurt_radius")
            dx, dy = a.x - cx, a.y - cy
            if dx * dx + dy * dy > rr * rr:
                continue
            fx = build_effects([{"effect": "damage",
                                 "amount": self.cfg["cursor_damage"],
                                 "hitstun": 2}])
            apply_effects(fx, None, a, self)
            d = (dx * dx + dy * dy) ** 0.5 or 1.0
            kb = self.cfg["cursor_knockback"]
            a.vx += dx / d * kb
            a.vy += dy / d * kb
            a.scratch["cursor_cool"] = self.cfg["cursor_cooldown"]
            self.request_cue("impact", a, {"x": cx, "y": cy}, None)

    def _run_timers(self):
        if not self._timers:
            return
        due = [t for t in self._timers if t[0] <= self.tick]
        if not due:
            return
        self._timers = [t for t in self._timers if t[0] > self.tick]
        for _, fn in due:
            try:
                fn()
            except Exception:
                self.fault("timer", "scheduled", -1)

    def _cull(self):
        for s in self.sides:
            s.actors = [a for a in s.actors if a.alive]
        self._reindex()

    # ==================================================================
    # determinism checksum — the golden test's assertion
    # ==================================================================
    def checksum(self):
        import hashlib
        h = hashlib.blake2b(digest_size=16)
        h.update(b"pb2|%d|" % self.tick)
        for a in sorted(self.all_actors(), key=lambda z: z.id):
            h.update(repr(a.checksum_row()).encode("utf-8"))
            h.update(b"|")
        for row in self.motes.checksum_rows():
            h.update(repr(row).encode("utf-8"))
        return h.hexdigest()

    def digest(self):
        """Compact human-readable state, used by the cockpit."""
        return {
            "tick": self.tick,
            "battle": self.battle_mode,
            "hitstop": self.hitstop_ticks,
            "actors": [
                {"id": a.id, "side": a.side, "mode": a.archetype.key,
                 "x": round(a.x, 1), "y": round(a.y, 1),
                 "hp": round(a.hp, 1), "hp_max": round(a.hp_max, 1),
                 "anim": a.anim, "tags": list(a.tags)}
                for a in self.all_actors()],
            "motes": self.motes.alive_count(),
            "checksum": self.checksum(),
        }


DEFAULTS = {
    "mote_capacity": 4096,
    "grid_cell": 96,
    "margin": 40,
    "accel": 0.5,
    "friction": 0.82,
    "gravity": 0.28,
    "mote_knockback": 4.0,
    "arena_oval": True,        # Battle-only, as signed off in v1
    "size_scaling": True,
    "speed_scaling": True,
    "size_corners": (2.33, 1.00, 5.00, 2.33),
    "speed_corners": (0.60, 0.40, 1.00, 0.60),
    "cursor_radius": 14.0,
    "cursor_damage": 1.0,
    "cursor_knockback": 7.0,
    "cursor_cooldown": 20,
    "log_events": False,
    "strict": True,            # dev default: fail loud
}


def _wrap(a):
    while a > math.pi:
        a -= math.tau
    while a < -math.pi:
        a += math.tau
    return a
