"""
Action runner for image characters (Rig Forge packages with an FX file).

Plays each action the way FX Studio previews it and triggers it the way it
was set up there (pack.action_settings):

  * idle / run   — locomotion, chosen by the renderer (standing / moving).
  * attacks      — attack_normal and its chain (chain_next ...).  The
                   archetype decides WHEN: melee attacks once the target is
                   inside stats.basic_attack_radius, shooters from shooting
                   range.  Consecutive attacks within chain_reset_ms continue
                   the chain.
  * Attack mode (Alt+Up) gates attacks and triggered actions the same way
    it gates the built-in fighters; `defend` always works.
  * Movement "back" retreats straight away from the target at
    move_speed_pct % speed until back_stop_pct % of the whole action.
  * Aim (pack.aim): the fighter always faces the target and its frame turns
    so the normal attack's barrel (from -> to anchor) points at it.
  * everything else (attack_special, ultimate, defend, ...) — plays when its
                   conditions are met (ANY / ALL), no more often than every
                   cooldown_ms.  An action with no conditions never
                   triggers by itself.

An action plays every frame at its own frame_ms, anim_loops times, then
ends.  Its Movement setting either roots the fighter ("stand") or lets it
keep moving at move_speed_pct % speed ("move").  The frames are shown
through the generic named-set driver (Combatant.action_anim / action_idx),
so the sprite, the FX (laser/fxkit.py) and the anchors all follow them.

Damage comes only from FX with Deals damage: the loader switches the
archetype's built-in bullets / dash-slash / ultimate off for these
characters, CombatSystem skips the melee FSM for them, and their body
contact never costs the opponent HP.  While `defend` plays, incoming hits
(bullets, FX, contact) are blocked.

Identical in Solo and Battle: both call update() from CombatSystem with the
same inputs (target = nearest enemy in Battle, the cursor in Solo).
"""

import re

from . import config

TICK_MS = config.TICK_MS
DEFAULT_ATTACK_GAP_MS = 350     # minimum gap between attacks without a cooldown
SHOOTER_RANGE_PX = 420          # shooters attack from this far (or their radius)
HISTORY = 12


def is_image(fig):
    char = getattr(fig.mode, "character", None)
    return bool(char and char.get("_package"))


def _settings(fig):
    from .fxkit import character_fx, normalize_action
    cfx = character_fx(fig.mode)
    if cfx is not None:
        return cfx.settings, normalize_action
    return {}, normalize_action


def _cfg(fig, action):
    settings, norm = _settings(fig)
    return settings.get(action) or norm({})


def _kind(name):
    if name in ("idle", "run"):
        return "locomotion"
    if re.match(r"^attack_normal", name or ""):
        return "attack"
    return "triggered"


def _tags(s):
    return [t.strip().lower() for t in str(s or "").split(",") if t.strip()]


def _tag_match(want, tag):
    return not want or (tag or "").lower() in want


class ActionRunner:
    __slots__ = ("playing", "elapsed", "loops_left", "started", "cooldown_until", "since_attacks", "since_hits",
                 "hp_fired", "history", "last_attack_end", "chain_pos", "hit_tags", "next_tag", "deflected",
                 "was_parrying", "base_speed", "acted", "attack_count")

    def __init__(self):
        self.playing = None
        self.elapsed = 0.0
        self.loops_left = 0
        self.started = 0
        self.cooldown_until = {}
        self.since_attacks = {}
        self.since_hits = {}
        self.hp_fired = {}
        self.history = []
        self.last_attack_end = -10 ** 9
        self.chain_pos = None
        self.hit_tags = []
        self.next_tag = None
        self.deflected = False
        self.was_parrying = False
        self.base_speed = None
        self.acted = False
        self.attack_count = 0

    # ------------------------------------------------------------ events
    def note_damage(self):
        tag = self.next_tag if self.next_tag is not None else ""
        self.next_tag = None
        self.hit_tags.append(tag)
        for k in list(self.since_hits.keys()):
            self.since_hits[k] += 1
        self.since_hits.setdefault("*", 0)
        self.since_hits["*"] += 1

    # ------------------------------------------------------------ conditions
    def _cond_true(self, fig, name, cond, ctx):
        t = cond.get("type")
        if t == "hp_below":
            pct = float(cond.get("pct", 50))
            if ctx["hp_pct"] > pct:
                return False
            return bool(cond.get("repeat")) or pct not in self.hp_fired.get(name, set())
        if t == "attacks_made":
            return self.since_attacks.get(name, self.attack_count) >= int(cond.get("count", 3))
        if t == "hits_taken":
            return self.since_hits.get(name, self.since_hits.get("*", 0)) >= int(cond.get("count", 3))
        if t == "target_within":
            return ctx["dist"] <= float(cond.get("px", 80))
        if t == "target_beyond":
            return ctx["dist"] >= float(cond.get("px", 200))
        if t == "hit_by_fx":
            want = _tags(cond.get("tags"))
            return any(_tag_match(want, tg) for tg in ctx["hit_tags"])
        if t == "fx_near":
            want, px = _tags(cond.get("tags")), float(cond.get("px", 60))
            px2 = px * px
            for (x, y, tg) in ctx["enemy_fx"]:
                if (x - fig.x) ** 2 + (y - fig.y) ** 2 <= px2 and _tag_match(want, tg):
                    return True
            return False
        if t == "bullet_deflected":
            return ctx["deflected"]
        if t == "after_actions":
            seq = [s.strip() for s in str(cond.get("sequence") or "").split(",") if s.strip()]
            return bool(seq) and self.history[-len(seq):] == seq
        return False

    def _triggered(self, fig, name, ctx, now):
        cfg = _cfg(fig, name)
        conds = cfg.get("conditions") or []
        if not conds or now < self.cooldown_until.get(name, 0):
            return False
        res = [self._cond_true(fig, name, c, ctx) for c in conds]
        return all(res) if cfg.get("logic") == "all" else any(res)

    # ------------------------------------------------------------ playback
    def _frames(self, fig, name):
        ex = fig.render.bundle.extra.get(name)
        n = len(ex[0]) if ex and ex[0] else 0
        char = fig.mode.character
        act = (char.get("actions") or {}).get(name) or {}
        fm = float(act.get("frame_ms") or 0) or (float(act.get("duration_ms") or 100 * max(1, n)) / max(1, n))
        return n, max(1.0, fm)

    def _start(self, fig, name, ctx, now):
        n, _fm = self._frames(fig, name)
        if n <= 0:
            return False
        cfg = _cfg(fig, name)
        self.playing = name
        self.elapsed = 0.0
        self.loops_left = max(1, int(round(float(cfg.get("anim_loops") or 1)))) if _kind(name) != "locomotion" else 1
        self.started = now
        cd = float(cfg.get("cooldown_ms") or 0)
        self.cooldown_until[name] = now + int(cd / TICK_MS)
        # Counters that belong to this action restart when it fires.
        self.since_attacks[name] = 0
        self.since_hits[name] = 0
        for c in cfg.get("conditions") or []:
            if c.get("type") == "hp_below" and ctx["hp_pct"] <= float(c.get("pct", 50)):
                self.hp_fired.setdefault(name, set()).add(float(c.get("pct", 50)))
        if _kind(name) == "attack":
            self.attack_count += 1
            for k in list(self.since_attacks.keys()):
                if k != name:
                    self.since_attacks[k] += 1
        c = fig.combat
        c.action_anim = name
        c.action_idx = 0
        return True

    def _finish(self, fig, now):
        name = self.playing
        self.playing = None
        c = fig.combat
        if c.action_anim == name:
            c.action_anim = None
            c.action_idx = 0
        self.history.append(name)
        del self.history[:-HISTORY]
        if _kind(name) == "attack":
            self.last_attack_end = now
            self.chain_pos = name
        self._restore_speed(fig)

    def _restore_speed(self, fig):
        if self.base_speed is not None:
            fig.motion.speed = self.base_speed
            self.base_speed = None

    def stop(self, fig):
        if self.playing:
            self._finish(fig, 0)

    def _attack_choice(self, fig, ctx, now):
        """Next attack to play, or None (archetype decides when)."""
        if ctx["target"] is None:
            return None
        if now < self.last_attack_end + int(DEFAULT_ATTACK_GAP_MS / TICK_MS):
            return None
        mode = fig.mode
        radius = float(config.MODE_CONFIGS.get(mode.key, {}).get("basic_attack_radius", config.SLASH_RADIUS))
        rng = radius if mode.uses_melee() or not mode.can_shoot() else max(radius, SHOOTER_RANGE_PX)
        if ctx["dist"] > rng:
            return None
        name = "attack_normal"
        if self.chain_pos:
            cfg = _cfg(fig, self.chain_pos)
            reset = float(cfg.get("chain_reset_ms") or 1000)
            nxt = cfg.get("chain_next") or ""
            if nxt and now - self.last_attack_end <= int(reset / TICK_MS):
                name = nxt
            else:
                self.chain_pos = None
        if now < self.cooldown_until.get(name, 0):
            return None
        return name if name in fig.render.bundle.extra else None

    def update(self, fig, world):
        """One tick.  Returns True when the fighter is rooted this tick
        (MotionSystem then leaves it where it is)."""
        now = world.global_tick
        c = fig.combat
        p = fig.personality
        battle = bool(world.battle_mode and world.partner_figures)
        if battle:
            tx, ty = world._nearest_enemy(fig.x, fig.y)
        else:
            tx, ty = world.cursor
        dist = ((tx - fig.x) ** 2 + (ty - fig.y) ** 2) ** 0.5
        parrying = bool(c.parrying)
        self.deflected = parrying and not self.was_parrying
        self.was_parrying = parrying
        ctx = {"target": (tx, ty), "dist": dist,
               "hp_pct": 100.0 * p.hp / max(1e-6, p.max_hp),
               "hit_tags": self.hit_tags, "deflected": self.deflected,
               "enemy_fx": getattr(world, "enemy_fx", None) or []}

        # Attack mode (Alt+Up) gates attacking exactly as it gates the
        # built-in fighters; defend is always allowed.
        armed = bool(getattr(world, "shoot_mode", True))
        # A triggered action (defend, ultimate, special, ...) whose conditions
        # are met cuts into a normal attack instead of waiting for it to end
        # — the moment (target in range, a hit, an incoming shot) would
        # otherwise be gone.  It never cuts into another triggered action.
        if self.playing is not None and _kind(self.playing) == "attack":
            names = [k for k in (fig.mode.character.get("actions") or {}) if _kind(k) == "triggered"]
            for name in sorted(names, key=lambda k: (0 if k == "defend" else 1 if k == "ultimate" else
                                                      2 if k == "attack_special" else 3, k)):
                if not armed and name != "defend":
                    continue
                if name in fig.render.bundle.extra and self._triggered(fig, name, ctx, now):
                    self._finish(fig, now)
                    self._start(fig, name, ctx, now)
                    break
        if self.playing is None:
            # Triggered actions first (defend, then ultimate, special, others).
            names = [k for k in (fig.mode.character.get("actions") or {}) if _kind(k) == "triggered"]
            order = sorted(names, key=lambda k: (0 if k == "defend" else 1 if k == "ultimate" else
                                                 2 if k == "attack_special" else 3, k))
            for name in order:
                if not armed and name != "defend":
                    continue
                if name in fig.render.bundle.extra and self._triggered(fig, name, ctx, now):
                    if self._start(fig, name, ctx, now):
                        break
            if self.playing is None and armed:
                atk = self._attack_choice(fig, ctx, now)
                if atk:
                    self._start(fig, atk, ctx, now)

        from .fxkit import character_fx
        cfx = character_fx(fig.mode)
        aiming = bool(cfx is not None and cfx.aim.get("enabled") and cfx.aim_ref is not None)

        rooted = False
        if self.playing is not None:
            name = self.playing
            n, fm = self._frames(fig, name)
            frame = int(self.elapsed // fm)
            if frame >= n:
                self.loops_left -= 1
                if self.loops_left > 0:
                    self.elapsed -= n * fm
                    frame = int(self.elapsed // fm)
                else:
                    self._finish(fig, now)
                    name = None
            if name is not None:
                c.action_anim = name
                c.action_idx = max(0, min(n - 1, frame))
                self.elapsed += TICK_MS
                cfg = _cfg(fig, name)
                total = n * fm * max(1, int(round(float(cfg.get("anim_loops") or 1))))
                done = ((max(1, int(round(float(cfg.get("anim_loops") or 1)))) - self.loops_left) * n * fm
                        + self.elapsed - TICK_MS)   # time into the whole action before this tick
                if cfg.get("movement") == "back" and not (fig.motion.bouncing or fig.motion.bounce_ending):
                    # Retreat straight away from the target at move_speed_pct %
                    # of normal speed until back_stop_pct % of the action.
                    rooted = True
                    fig.render.is_moving = False
                    if done < total * float(cfg.get("back_stop_pct") or 0) / 100.0:
                        from . import combat as _combat
                        bx, by = fig.x - tx, fig.y - ty
                        d = (bx * bx + by * by) ** 0.5
                        if d < 0.001:
                            bx, by, d = (1.0 if fig.transform.facing_left else -1.0), 0.0, 1.0
                        if self.base_speed is None:
                            self.base_speed = fig.motion.speed
                        sf = _combat.position_speed_scale(fig.x, fig.y, fig.screen_w, fig.screen_h)
                        step = self.base_speed * max(0.0, float(cfg.get("move_speed_pct") or 0)) / 100.0 * sf
                        fig.transform.x += bx / d * step
                        fig.transform.y += by / d * step
                        fig.render.is_moving = True
                    if not aiming:
                        dx = tx - fig.x
                        if dx < -0.001:
                            fig.transform.facing_left = True
                        elif dx > 0.001:
                            fig.transform.facing_left = False
                elif cfg.get("movement") == "move":
                    pct = max(0.0, float(cfg.get("move_speed_pct") or 0)) / 100.0
                    if self.base_speed is None:
                        self.base_speed = fig.motion.speed
                    fig.motion.speed = self.base_speed * pct
                elif fig.motion.bouncing or fig.motion.bounce_ending:
                    pass   # a knockback always moves the fighter, even mid-action
                else:
                    rooted = True
                    # Face the target while rooted.
                    dx = tx - fig.x
                    if dx < -0.001:
                        fig.transform.facing_left = True
                    elif dx > 0.001:
                        fig.transform.facing_left = False
                    fig.render.is_moving = False
        # Aiming (FX Studio pack.aim): face the target and turn the frame on
        # show so its barrel (the point the normal attack shoots from) points
        # at the target — always, in every action.
        if aiming:
            if not (fig.motion.bouncing or fig.motion.bounce_ending):
                from .fxkit import aim_angle, current_action
                dx = tx - fig.x
                if dx < -0.001:
                    fig.transform.facing_left = True
                elif dx > 0.001:
                    fig.transform.facing_left = False
                act, frame = current_action(fig)
                fig.aim = aim_angle(cfx, act, frame, -1.0 if fig.transform.facing_left else 1.0,
                                    fig._position_scale(), fig.x, fig.y, tx, ty)
        else:
            fig.aim = None
        self.hit_tags = []
        self.acted = rooted
        return rooted

    def blocking(self):
        return self.playing == "defend"


# ------------------------------------------------------------ module hooks
def runner(fig):
    r = getattr(fig, "act", None)
    if r is None and is_image(fig):
        r = ActionRunner()
        fig.act = r
    return r


def update(fig, world):
    """CombatSystem hook for image characters; returns 'rooted this tick'."""
    r = runner(fig)
    return r.update(fig, world) if r is not None else False


def blocks_hit(fig):
    """True while this fighter's `defend` action plays: the hit is blocked."""
    r = getattr(fig, "act", None)
    return bool(r is not None and r.blocking())


def note_fx_hit(fig, tag):
    r = getattr(fig, "act", None)
    if r is not None:
        r.next_tag = tag or ""


def note_damage(fig):
    r = getattr(fig, "act", None)
    if r is not None:
        r.note_damage()
