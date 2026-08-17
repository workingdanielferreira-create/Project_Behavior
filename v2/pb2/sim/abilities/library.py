"""The built-in ability library.

Every mechanic v1 hardcoded in combat.py lives here as a registered plugin.
Each is generic and parameterised — none names a character.  Adding a new
mechanic means adding one class in this folder; no engine file changes.

Coverage map (v1 -> v2):
    attack_pattern / bullet cycles  -> projectile_volley
    RichBeamProjectile normal       -> beam_shot
    petals / orbiting spheres       -> orbitals
    blink / blinkstorm              -> blink
    dodge_style / survival teleport -> evade
    hp_threshold_clones             -> threshold_summon
    damage_teleport                 -> reactive_teleport
    vanish_cut (Flash Cut)          -> vanish_strike
    combo strings                   -> melee_combo
    deflect / parry                 -> guard
    ultimate playback               -> (any ability with tier gating)
"""

import math

from ..ability import Ability, PhaseRunner, curve, SCORE_NEVER
from ..effects import build_effects, apply_effects
from ..motes import (K_BULLET, K_SPARK, K_PETAL, K_BEAM, K_RING, K_AFTERIMAGE)
from ...core.registry import ability

__all__ = []


# ======================================================================
# offence
# ======================================================================

@ability("projectile_volley")
class ProjectileVolley(Ability):
    """Fire a spread/cone/ring of projectiles at the target."""

    DEFAULT_COOLDOWN = 48

    def score(self, inst, actor, world):
        t = self.target_of(actor, world)
        if t is None:
            return SCORE_NEVER
        ideal = inst.p("ideal_range", 260.0)
        s = self.range_score(actor, world, ideal, inst.p("falloff", 300.0))
        return s * (0.4 + 0.6 * actor.attrs.get("aggression", 0.5))

    def start(self, inst, actor, world):
        t = self.target_of(actor, world)
        if t is None:
            return
        tx, ty = world.position_of(t)
        base = math.atan2(ty - actor.y, tx - actor.x)
        actor.facing = base

        count = int(inst.p("count", 3))
        spread = math.radians(float(inst.p("spread_deg", 24.0)))
        speed = float(inst.p("speed", 7.0))
        pattern = inst.p("pattern", "cone")

        for i in range(count):
            if count == 1:
                off = 0.0
            elif pattern == "ring":
                off = math.tau * i / count
            else:
                off = -spread / 2.0 + spread * i / max(1, count - 1)
            ang = base + off
            if pattern == "zigzag":
                ang += math.sin(i * 1.7) * spread * 0.5
            spd = speed * (1.0 + inst.p("speed_variance", 0.0)
                           * (actor.rng.random() - 0.5))
            world.motes.spawn(
                actor.x, actor.y,
                math.cos(ang) * spd, math.sin(ang) * spd,
                kind=K_BULLET, life=int(inst.p("life", 150)),
                radius=float(inst.p("radius", 6.0)),
                damage=float(inst.p("damage", 1.0)),
                size=float(inst.p("size", 1.0)),
                side=actor.side, owner=actor.id, rot=ang,
                cue=world.cue_id(inst.p("cue", "bullet")),
                color=world.color_id(actor, inst.p("color", "primary")),
                hits=True,
                pierce=bool(inst.p("pierce", False)),
                homing=bool(inst.p("homing", False)),
                homing_rate=float(inst.p("homing_rate", 0.06)))

        world.request_cue(inst.p("muzzle_cue", "muzzle"), actor,
                          {"angle": base}, actor)
        inst.start_cooldown(inst.p("cooldown", self.DEFAULT_COOLDOWN),
                            actor.attrs.get("cooldown_rate", 1.0))


@ability("beam_shot")
class BeamShot(Ability):
    """A travelling beam — v1's RichBeamProjectile as a normal attack."""

    DEFAULT_COOLDOWN = 70
    BODY_TAGS = ("state.busy",)

    def score(self, inst, actor, world):
        s = self.range_score(actor, world, inst.p("ideal_range", 340.0),
                             inst.p("falloff", 420.0))
        return s * float(inst.p("weight", 0.85))

    def start(self, inst, actor, world):
        t = self.target_of(actor, world)
        if t is None:
            return
        tx, ty = world.position_of(t)
        ang = math.atan2(ty - actor.y, tx - actor.x)
        actor.facing = ang
        PhaseRunner.begin(inst)
        inst.state["angle"] = ang

    def tick(self, inst, actor, world):
        if inst.phase == "fire" and inst.phase_t == 0:
            ang = inst.state.get("angle", actor.facing)
            spd = float(inst.p("speed", 12.0))
            world.motes.spawn(
                actor.x, actor.y,
                math.cos(ang) * spd, math.sin(ang) * spd,
                kind=K_BEAM, life=int(inst.p("life", 90)),
                radius=float(inst.p("radius", 10.0)),
                damage=float(inst.p("damage", 3.0)),
                size=float(inst.p("size", 1.0)),
                side=actor.side, owner=actor.id, rot=ang,
                cue=world.cue_id(inst.p("cue", "beam")),
                color=world.color_id(actor, inst.p("color", "accent")),
                hits=True, pierce=bool(inst.p("pierce", True)), fade=False)
            world.request_cue("flash", actor, {"angle": ang}, actor)

    def finish(self, inst, actor, world):
        inst.start_cooldown(inst.p("cooldown", self.DEFAULT_COOLDOWN),
                            actor.attrs.get("cooldown_rate", 1.0))


@ability("melee_combo")
class MeleeCombo(Ability):
    """A multi-hit close-range string.  Damage is authored per hit — v1's
    combo damage was hardcoded to a flat 1 HP regardless of the JSON."""

    DEFAULT_COOLDOWN = 40

    def score(self, inst, actor, world):
        t = self.target_of(actor, world)
        if t is None:
            return SCORE_NEVER
        tx, ty = world.position_of(t)
        d = math.hypot(tx - actor.x, ty - actor.y)
        reach = actor.attrs.get("attack_range", 52.0) * float(inst.p("reach_mul", 1.0))
        if d > reach:
            return SCORE_NEVER
        return curve(1.0 - d / max(1.0, reach), "quadratic") \
            * (0.5 + 0.5 * actor.attrs.get("aggression", 0.5))

    def start(self, inst, actor, world):
        PhaseRunner.begin(inst)
        inst.state["hits"] = 0
        inst.state["fx"] = build_effects(inst.p("on_hit", [
            {"effect": "damage", "amount": inst.p("damage", 1.0),
             "knockback": inst.p("knockback", 5.0), "hitstun": 6}]))

    def tick(self, inst, actor, world):
        if not inst.phase or not inst.phase.startswith("hit"):
            return
        if inst.phase_t != 0:
            return
        reach = actor.attrs.get("attack_range", 52.0) * float(inst.p("reach_mul", 1.0))
        arc = math.radians(float(inst.p("arc_deg", 120.0)))
        for foe in world.enemies_of(actor):
            d = actor.distance_to(foe)
            if d > reach:
                continue
            ang = abs(_wrap(actor.angle_to(foe.x, foe.y) - actor.facing))
            if ang > arc / 2.0:
                continue
            apply_effects(inst.state["fx"], actor, foe, world)
            inst.state["hits"] += 1
        world.request_cue(inst.p("cue", "crescent"), actor,
                          {"angle": actor.facing, "reach": reach}, actor)

    def finish(self, inst, actor, world):
        inst.start_cooldown(inst.p("cooldown", self.DEFAULT_COOLDOWN),
                            actor.attrs.get("cooldown_rate", 1.0))


@ability("vanish_strike")
class VanishStrike(Ability):
    """Vanish, reappear beside the target, strike.  v1's Flash Cut, generic."""

    DEFAULT_COOLDOWN = 420
    BODY_TAGS = ("state.busy", "state.vanished", "immune.damage")

    def score(self, inst, actor, world):
        t = self.target_of(actor, world)
        if t is None:
            return SCORE_NEVER
        if actor.hp_frac > float(inst.p("hp_below", 1.01)):
            return SCORE_NEVER
        return float(inst.p("weight", 0.95))

    def start(self, inst, actor, world):
        PhaseRunner.begin(inst)
        inst.state["fx"] = build_effects(inst.p("on_hit", [
            {"effect": "damage", "amount": inst.p("damage", 8.0),
             "knockback": inst.p("knockback", 14.0), "hitstun": 14}]))
        world.request_cue(inst.p("vanish_cue", "afterimage"), actor, {}, actor)
        if inst.p("freeze_ticks", 0):
            world.hitstop(int(inst.p("freeze_ticks", 8)))

    def tick(self, inst, actor, world):
        if inst.phase == "strike" and inst.phase_t == 0:
            t = self.target_of(actor, world)
            if t is not None:
                tx, ty = world.position_of(t)
                off = float(inst.p("offset", 46.0))
                ang = math.atan2(actor.y - ty, actor.x - tx)
                nx, ny = world.clamp_to_arena(tx + math.cos(ang) * off,
                                              ty + math.sin(ang) * off)
                actor.x, actor.y = nx, ny
                actor.facing = math.atan2(ty - ny, tx - nx)
                if isinstance(t, type(actor)):
                    apply_effects(inst.state["fx"], actor, t, world)
                world.request_cue(inst.p("cue", "crescent"), actor,
                                  {"angle": actor.facing}, actor)

    def finish(self, inst, actor, world):
        inst.start_cooldown(inst.p("cooldown", self.DEFAULT_COOLDOWN),
                            actor.attrs.get("cooldown_rate", 1.0))


# ======================================================================
# sustained / passive
# ======================================================================

@ability("orbitals")
class Orbitals(Ability):
    """Orbiting spheres that damage on contact — v1's petal system.

    Ellipse orbit via independent radius_x/radius_y, per-orb cooldown,
    invisible while recharging, contact damage through an invisible mote.
    """

    DEFAULT_COOLDOWN = 0
    BODY_TAGS = ()          # passive: does not occupy the body

    def score(self, inst, actor, world):
        # Passive abilities keep themselves active rather than competing.
        return SCORE_NEVER

    def start(self, inst, actor, world):
        inst.state.setdefault("phase", 0.0)
        inst.state.setdefault("orbs", [
            {"cd": 0, "alive": True} for _ in range(int(inst.p("count", 4)))])
        inst.state["fx"] = build_effects(inst.p("on_hit", [
            {"effect": "damage", "amount": inst.p("damage", 1.0),
             "knockback": inst.p("knockback", 3.0)}]))

    def passive_tick(self, inst, actor, world):
        if "orbs" not in inst.state:
            self.start(inst, actor, world)
        rx = float(inst.p("radius_x", 62.0))
        ry = float(inst.p("radius_y", 62.0))
        spd = float(inst.p("orbit_speed", 0.05))

        # proximity scales cadence, not travel speed (v1's petal_proximity_speed)
        t = self.target_of(actor, world)
        prox = 1.0
        if t is not None and inst.p("proximity_speed", 0.0):
            tx, ty = world.position_of(t)
            d = math.hypot(tx - actor.x, ty - actor.y)
            near = float(inst.p("proximity_range", 300.0))
            prox = 1.0 + float(inst.p("proximity_speed", 0.0)) * \
                max(0.0, 1.0 - d / max(1.0, near))

        inst.state["phase"] = (inst.state["phase"] + spd * prox) % math.tau
        orbs = inst.state["orbs"]
        n = len(orbs)
        recharge = int(inst.p("recharge", 90))

        for i, orb in enumerate(orbs):
            if orb["cd"] > 0:
                orb["cd"] -= 1
                if orb["cd"] == 0:
                    orb["alive"] = True
                continue
            if not orb["alive"]:
                continue
            a = inst.state["phase"] + math.tau * i / max(1, n)
            ox = actor.x + math.cos(a) * rx
            oy = actor.y + math.sin(a) * ry
            orb["x"], orb["y"] = ox, oy

            world.request_cue(inst.p("cue", "orb"), actor,
                              {"x": ox, "y": oy, "index": i}, actor)

            r = float(inst.p("hit_radius", 14.0))
            for foe in world.enemies_of(actor):
                if math.hypot(foe.x - ox, foe.y - oy) <= r + foe.attrs.get("hurt_radius", 18.0):
                    apply_effects(inst.state["fx"], actor, foe, world)
                    orb["alive"] = False
                    orb["cd"] = recharge
                    world.request_cue("spark", actor, {"x": ox, "y": oy}, actor)
                    break


@ability("guard")
class Guard(Ability):
    """Deflect incoming motes within an arc — v1's generalized parry."""

    DEFAULT_COOLDOWN = 90
    BODY_TAGS = ("state.busy", "state.guarding")

    def score(self, inst, actor, world):
        threat = world.incoming_threat(actor, float(inst.p("sense_range", 190.0)))
        if threat <= 0.0:
            return SCORE_NEVER
        return min(1.0, threat) * (0.4 + 0.6 * actor.attrs.get("caution", 0.5))

    def start(self, inst, actor, world):
        PhaseRunner.begin(inst)
        actor.add_tag("state.deflecting")
        world.request_cue(inst.p("cue", "crescent"), actor,
                          {"angle": actor.facing, "guard": True}, actor)

    def tick(self, inst, actor, world):
        arc = math.radians(float(inst.p("arc_deg", 150.0)))
        reach = float(inst.p("reach", 64.0))
        world.deflect_motes(actor, reach, arc,
                            reflect=bool(inst.p("reflect", True)))

    def finish(self, inst, actor, world):
        actor.remove_tag("state.deflecting")
        inst.start_cooldown(inst.p("cooldown", self.DEFAULT_COOLDOWN),
                            actor.attrs.get("cooldown_rate", 1.0))


# ======================================================================
# mobility
# ======================================================================

@ability("blink")
class Blink(Ability):
    """Instant relocation — v1's blink and blinkstorm."""

    DEFAULT_COOLDOWN = 150

    def score(self, inst, actor, world):
        mode = inst.p("mode", "reposition")
        if mode == "escape":
            return self.hp_score(actor, float(inst.p("hp_below", 0.35))) \
                * float(inst.p("weight", 1.0))
        threat = world.incoming_threat(actor, float(inst.p("sense_range", 140.0)))
        return min(1.0, threat * float(inst.p("weight", 0.7)))

    def start(self, inst, actor, world):
        dist = float(inst.p("distance", 190.0))
        mode = inst.p("mode", "reposition")
        t = self.target_of(actor, world)
        if mode == "escape" and t is not None:
            tx, ty = world.position_of(t)
            ang = math.atan2(actor.y - ty, actor.x - tx)
        elif mode == "flank" and t is not None:
            tx, ty = world.position_of(t)
            ang = math.atan2(actor.y - ty, actor.x - tx) + \
                (math.pi / 2 if actor.rng.chance(0.5) else -math.pi / 2)
        else:
            ang = actor.rng.uniform(0.0, math.tau)

        n = int(inst.p("trail_images", 4))
        for k in range(n):
            f = (k + 1) / (n + 1)
            world.motes.spawn(actor.x + math.cos(ang) * dist * f,
                              actor.y + math.sin(ang) * dist * f,
                              0.0, 0.0, kind=K_AFTERIMAGE,
                              life=int(inst.p("trail_life", 16)),
                              size=1.0, side=actor.side, owner=actor.id,
                              cue=world.cue_id("afterimage"),
                              color=world.color_id(actor, "primary"))

        nx, ny = world.clamp_to_arena(actor.x + math.cos(ang) * dist,
                                      actor.y + math.sin(ang) * dist)
        actor.x, actor.y = nx, ny
        world.bus.emit("actor.blinked", tick=world.tick, actor=actor.id)
        inst.start_cooldown(inst.p("cooldown", self.DEFAULT_COOLDOWN),
                            actor.attrs.get("cooldown_rate", 1.0))


@ability("evade")
class Evade(Ability):
    """Short dodge or survival teleport — v1's dodge_style plus the
    survival-teleport that used to be welded into the runner path."""

    DEFAULT_COOLDOWN = 110

    def score(self, inst, actor, world):
        s = world.incoming_threat(actor, float(inst.p("sense_range", 150.0)))
        panic = self.hp_score(actor, float(inst.p("hp_below", 0.3)))
        return min(1.0, max(s * 0.8, panic) * float(inst.p("weight", 0.9)))

    def start(self, inst, actor, world):
        PhaseRunner.begin(inst)
        style = inst.p("style", "dash")
        dist = float(inst.p("distance", 120.0))
        ang = world.threat_angle(actor)
        ang = (ang + math.pi) if ang is not None else actor.rng.uniform(0, math.tau)
        if style == "teleport":
            nx, ny = world.clamp_to_arena(actor.x + math.cos(ang) * dist,
                                          actor.y + math.sin(ang) * dist)
            actor.x, actor.y = nx, ny
            world.request_cue("flash", actor, {}, actor)
        else:
            actor.vx = math.cos(ang) * float(inst.p("speed", 9.0))
            actor.vy = math.sin(ang) * float(inst.p("speed", 9.0))
        if inst.p("invulnerable", True):
            actor.add_tag("immune.damage")
            inst.state["inv"] = True

    def finish(self, inst, actor, world):
        if inst.state.pop("inv", False):
            actor.remove_tag("immune.damage")
        inst.start_cooldown(inst.p("cooldown", self.DEFAULT_COOLDOWN),
                            actor.attrs.get("cooldown_rate", 1.0))


# ======================================================================
# reactive / summon
# ======================================================================

@ability("threshold_summon")
class ThresholdSummon(Ability):
    """Spawn helpers when HP crosses authored thresholds.

    v1's hp_threshold_clones, generalised: any character can declare any
    thresholds and any summon behaviour.
    """

    DEFAULT_COOLDOWN = 0
    BODY_TAGS = ()

    def score(self, inst, actor, world):
        ths = inst.state.get("_ths")
        if ths is None:
            raw = inst.p("thresholds", [0.75, 0.5, 0.25])
            if not isinstance(raw, (list, tuple)):
                raise TypeError(
                    "threshold_summon.thresholds must be a list of fractions, "
                    "got %r" % type(raw).__name__)
            ths = sorted((float(t) for t in raw), reverse=True)
            inst.state["_ths"] = ths
        fired = inst.state.setdefault("fired", [])
        for th in ths:                       # list, not set -> deterministic
            if actor.hp_frac <= th and th not in fired:
                inst.state["pending"] = th
                return 1.0
        return SCORE_NEVER

    def start(self, inst, actor, world):
        th = inst.state.pop("pending", None)
        if th is None:
            return
        inst.state.setdefault("fired", []).append(th)
        n = int(inst.p("count", 1))
        radius = float(inst.p("radius", 220.0))
        for i in range(n):
            ang = math.tau * i / max(1, n) + float(inst.p("angle_offset", 0.0))
            sx, sy = world.clamp_to_arena(actor.x + math.cos(ang) * radius,
                                          actor.y + math.sin(ang) * radius)
            world.spawn_summon(actor, sx, sy, dict(inst.params))
        world.request_cue(inst.p("cue", "ring"), actor, {}, actor)


@ability("reactive_teleport")
class ReactiveTeleport(Ability):
    """Teleport away in response to taking damage — v1's damage_teleport.

    Subscribes to the event bus rather than being welded into the damage
    path, which is why it composes with anything that deals damage.
    """

    DEFAULT_COOLDOWN = 120
    BODY_TAGS = ()

    def score(self, inst, actor, world):
        if not inst.state.pop("triggered", False):
            return SCORE_NEVER
        return float(inst.p("weight", 1.0))

    def on_damaged(self, inst, actor, world, ev):
        if ev.get("actor") != actor.id:
            return
        if actor.rng.chance(float(inst.p("chance", 1.0))):
            inst.state["triggered"] = True

    def start(self, inst, actor, world):
        dist = float(inst.p("distance", 240.0))
        ang = actor.rng.uniform(0.0, math.tau)
        nx, ny = world.clamp_to_arena(actor.x + math.cos(ang) * dist,
                                      actor.y + math.sin(ang) * dist)
        world.request_cue(inst.p("cue", "flash"), actor, {}, actor)
        actor.x, actor.y = nx, ny
        inst.start_cooldown(inst.p("cooldown", self.DEFAULT_COOLDOWN),
                            actor.attrs.get("cooldown_rate", 1.0))


def _wrap(a):
    while a > math.pi:
        a -= math.tau
    while a < -math.pi:
        a += math.tau
    return a
