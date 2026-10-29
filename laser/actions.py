"""
Action runner for image characters (Rig Forge packages with an FX file).

Plays each action the way FX Studio previews it and triggers it the way it
was set up there (pack.action_settings):

  * idle / run   — locomotion, chosen by the renderer (standing / moving).
  * attacks      — attack_normal and its chain (chain_next ...).  The
                   archetype decides WHEN: melee attacks once the target is
                   inside stats.basic_attack_radius, shooters from shooting
                   range — or, when the attack sets its own attack_px
                   (Attack distance), once the target is that close (times
                   the character scale).  Consecutive attacks within chain_reset_ms continue
                   the chain.  An attack with trigger conditions also needs
                   them to pass (ANY / ALL) on top of that range check; with
                   none it attacks on range alone.  An attack_normal_N with
                   conditions is also a conditional alternate: once they
                   pass it plays in place of attack_normal, chained or not.
                   An attack whose Blink lands on the target reaches at
                   least that blink's proximity_px.
  * Attack mode (Alt+Up) gates attacks and triggered actions the same way
    it gates the built-in fighters; `defend` always works.
  * Movement "back" retreats straight away from the target at
    move_speed_pct % speed until back_stop_pct % of the whole action.
  * Movement "leap" jumps onto the target: at leap.start_frame the target's
    spot is locked and the fighter travels there in a hop arc
    (leap.height_px high), arriving as leap.land_frame starts, placed so
    the action's hit point lands on that spot (see _leap_hit_offset).
  * Aim (pack.aim): the fighter always faces the target and its frame turns
    so the normal attack's barrel (from -> to anchor) points at it.
  * everything else (attack_special, ultimate, defend, ...) — plays when its
                   conditions are met (ANY / ALL), no more often than every
                   cooldown_ms.  An action with no conditions never
                   triggers by itself.

Every condition can be inverted (`not`: met when the check is false).  The
condition types are listed in CONDITION_TYPES below (mirror of the Studio's
FXK.CONDITION_TYPES).  Target state in Battle comes from the per-tick
read-only snapshots (partner_figures / partner_facing / partner_state); in
Solo the target is the cursor, which has no HP and never attacks or defends
(those checks are false), and "faces" the way it last moved sideways.

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

import random
import re

from . import config
from . import unique as _unique
from . import movestyle as _movestyle

TICK_MS = config.TICK_MS
DEFAULT_ATTACK_GAP_MS = 350     # minimum gap between attacks without a cooldown
SHOOTER_RANGE_PX = 420          # shooters attack from this far (or their radius)
HISTORY = 12
SPEED_WINDOW = 6                # ticks averaged for own / target speed (px/s)
DAMAGE_WINDOW_MS = 60000        # how far back damage_taken can look

# Condition types and their defaults (Studio: FXK.CONDITION_TYPES).  Every
# condition also carries `not` (False): True inverts it.
CONDITION_TYPES = {
    "hp_below": dict(pct=50.0, repeat=False), "hp_above": dict(pct=80.0),
    "self_speed_above": dict(px_s=120.0), "self_speed_below": dict(px_s=20.0),
    "target_within": dict(px=80.0), "target_beyond": dict(px=200.0),
    "target_between": dict(min_px=60.0, max_px=200.0),
    "target_above": dict(px=40.0), "target_below": dict(px=40.0),
    "target_facing": dict(dir="toward"), "target_attacking": {}, "target_defending": {},
    "target_hp_below": dict(pct=50.0), "target_hp_above": dict(pct=80.0),
    "target_speed_above": dict(px_s=120.0), "target_speed_below": dict(px_s=20.0),
    "attacks_made": dict(count=3), "hits_taken": dict(count=3), "damage_taken": dict(hp=10.0, ms=2000.0),
    "landed_hit": {}, "hit_by_fx": dict(tags=""), "fx_near": dict(tags="", px=60.0),
    "projectile_count": dict(count=5), "bullet_deflected": {},
    "after_actions": dict(sequence=""), "since_action": dict(action="", ms=2000.0),
    "every_ms": dict(ms=3000.0), "idle_for": dict(ms=1000.0), "chance": dict(pct_s=30.0),
    "action_triggered": dict(who="target", action="", ms=300.0),
}


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


# The Switch actions (laser/tag.py): a tag pair's incoming fighter plays
# switch_in, the outgoing one switch_out.  They count as triggered actions
# (so a forced ultimate, a dodge, ... waits for them to end) but never start
# on their own here: laser/tag.py starts them.  switch_in's trigger
# conditions are read against the ON-FIELD partner (tag.py), its cooldown_ms
# is the pair's switch cooldown.
SWITCH_ACTIONS = ("switch_in", "switch_out")


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


def _track_speed(track, x, y):
    """Append (x, y) and return the average speed over the window, px/s."""
    track.append((x, y))
    del track[:-(SPEED_WINDOW + 1)]
    if len(track) < 2:
        return 0.0
    (x0, y0), n = track[0], len(track) - 1
    return ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5 / n * (1000.0 / TICK_MS)


def _nearest_index(partners, fx, fy):
    best, bi = float("inf"), -1
    for i, f in enumerate(partners or []):
        d = (f[0] - fx) ** 2 + (f[1] - fy) ** 2
        if d < best:
            best, bi = d, i
    return bi


class ActionRunner:
    __slots__ = ("playing", "elapsed", "loops_left", "started", "cooldown_until", "since_attacks", "since_hits",
                 "hp_fired", "history", "last_attack_end", "chain_pos", "hit_tags", "next_tag", "deflected",
                 "was_parrying", "base_speed", "acted", "attack_count", "born", "last_start", "last_end",
                 "idle_since", "own_track", "tgt_track", "last_hp", "hp_drops", "landed", "cursor_facing_left",
                 "rng", "ctx", "ctx_tick", "was_attacking", "forced", "forced_until", "forced_root",
                 "next_resisted", "resisted_hp", "resisted_drops", "defend_tags", "leap", "leap_dmg", "gap_until",
                 "cd_born", "cd_start", "cd_end", "cd_idle")

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
        self.gap_until = -10 ** 9     # attack gap end, on the cooldown clock (unique.cd_now)
        self.chain_pos = None
        self.hit_tags = []
        self.next_tag = None
        self.deflected = False
        self.was_parrying = False
        self.base_speed = None
        self.acted = False
        self.attack_count = 0
        self.born = None
        self.last_start = {}
        self.last_end = {}
        self.idle_since = None
        # The same moments on the fighter's cooldown clock (unique.cd_now):
        # timer conditions (every_ms, since_action, idle_for) read these, so
        # Berserker rage speeds them up as it does cooldowns.
        self.cd_born = None
        self.cd_start = {}
        self.cd_end = {}
        self.cd_idle = None
        self.own_track = []
        self.tgt_track = []
        self.last_hp = None
        self.hp_drops = []
        # Anti-knockback (ai.resists_knockback): a resisted hit still counts
        # for every action except `defend`.  next_resisted marks the next
        # note_damage; resisted_hp is its HP waiting for observe() to log it
        # in resisted_drops; defend_tags = this tick's hit tags minus them.
        self.next_resisted = False
        self.resisted_hp = 0.0
        self.resisted_drops = []
        self.defend_tags = []
        self.landed = 0
        self.cursor_facing_left = None
        self.rng = random.Random()
        # A forced action (the "clash" action while one of this fighter's
        # FX clashes, laser/clash.py): loops until forced_until, standing
        # still when forced_root.
        self.forced = None
        self.forced_until = 0
        self.forced_root = False
        self.ctx = None              # the last observe() result (conditions read it)
        self.ctx_tick = None         # the tick it was taken on
        self.was_attacking = False   # tracker for non-image fighters: dash / slash edge
        # Movement "leap": None = not taken off yet this loop; a dict while
        # in the air / landed (sx, sy, ex, ey, t0, t1, h, left, done).
        self.leap = None
        # (action, damage) while a "range"-damage leap's FX can hit, else None.
        self.leap_dmg = None

    # ------------------------------------------------------------ events
    def note_damage(self, amount=0.0):
        tag = self.next_tag if self.next_tag is not None else ""
        self.next_tag = None
        resisted, self.next_resisted = self.next_resisted, False
        self.hit_tags.append(tag)
        if resisted:
            # Anti-knockback: `defend` keeps its count from before this hit.
            self.since_hits.setdefault("defend", self.since_hits.get("*", 0))
            self.resisted_hp += max(0.0, float(amount or 0))
        else:
            self.defend_tags.append(tag)
        for k in list(self.since_hits.keys()):
            if not (resisted and k == "defend"):
                self.since_hits[k] += 1
        self.since_hits.setdefault("*", 0)
        self.since_hits["*"] += 1

    # ------------------------------------------------------------ conditions
    def _cond_true(self, fig, name, cond, ctx):
        """The condition's own check (before `not`)."""
        t = cond.get("type")
        now = ctx["now"]
        if t == "hp_below":
            pct = float(cond.get("pct", 50))
            if ctx["hp_pct"] > pct:
                return False
            return bool(cond.get("repeat")) or pct not in self.hp_fired.get(name, set())
        if t == "hp_above":
            return ctx["hp_pct"] >= float(cond.get("pct", 80))
        if t == "self_speed_above":
            return ctx["own_speed"] >= float(cond.get("px_s", 120))
        if t == "self_speed_below":
            return ctx["own_speed"] <= float(cond.get("px_s", 20))
        if t == "attacks_made":
            return self.since_attacks.get(name, self.attack_count) >= int(cond.get("count", 3))
        if t == "hits_taken":
            return self.since_hits.get(name, self.since_hits.get("*", 0)) >= int(cond.get("count", 3))
        if t == "damage_taken":
            since = now - int(float(cond.get("ms", 2000)) / TICK_MS)
            lost = sum(d for (tk, d) in self.hp_drops if tk > since)
            if name == "defend":
                lost -= sum(d for (tk, d) in self.resisted_drops if tk > since)
            return lost >= float(cond.get("hp", 10))
        if t == "landed_hit":
            return ctx["landed"] > 0
        if t == "target_within":
            return ctx["dist"] <= float(cond.get("px", 80))
        if t == "target_beyond":
            return ctx["dist"] >= float(cond.get("px", 200))
        if t == "target_between":
            lo, hi = float(cond.get("min_px", 60)), float(cond.get("max_px", 200))
            return min(lo, hi) <= ctx["dist"] <= max(lo, hi)
        if t == "target_above":
            return ctx["target"][1] <= fig.y - float(cond.get("px", 40))
        if t == "target_below":
            return ctx["target"][1] >= fig.y + float(cond.get("px", 40))
        if t == "target_facing":
            fl = ctx["tgt_facing_left"]
            if fl is None:
                return False
            toward = (fig.x < ctx["target"][0]) == bool(fl)
            return toward if cond.get("dir", "toward") != "away" else not toward
        if t == "target_attacking":
            return bool(ctx["tgt_state"] and ctx["tgt_state"][1])
        if t == "target_defending":
            return bool(ctx["tgt_state"] and ctx["tgt_state"][2])
        if t == "target_hp_below":
            return bool(ctx["tgt_state"]) and ctx["tgt_state"][0] <= float(cond.get("pct", 50))
        if t == "target_hp_above":
            return bool(ctx["tgt_state"]) and ctx["tgt_state"][0] >= float(cond.get("pct", 80))
        if t == "target_speed_above":
            return ctx["tgt_speed"] >= float(cond.get("px_s", 120))
        if t == "target_speed_below":
            return ctx["tgt_speed"] <= float(cond.get("px_s", 20))
        if t == "hit_by_fx":
            want = _tags(cond.get("tags"))
            tags = ctx["defend_tags"] if name == "defend" else ctx["hit_tags"]
            return any(_tag_match(want, tg) for tg in tags)
        if t == "fx_near":
            want, px = _tags(cond.get("tags")), float(cond.get("px", 60))
            px2 = px * px
            for (x, y, tgs, _air) in ctx["enemy_fx"]:
                if (x - fig.x) ** 2 + (y - fig.y) ** 2 <= px2 and (
                        not want or any(_tag_match(want, tg) for tg in tgs)):
                    return True
            return False
        if t == "projectile_count":
            return sum(1 for e in ctx["enemy_fx"] if e[3]) >= int(cond.get("count", 5))
        if t == "bullet_deflected":
            return ctx["deflected"]
        if t == "after_actions":
            seq = [s.strip() for s in str(cond.get("sequence") or "").split(",") if s.strip()]
            return bool(seq) and self.history[-len(seq):] == seq
        if t == "since_action":
            other = str(cond.get("action") or "") or name
            ref = self.cd_end.get(other, self.cd_born)
            return other != self.playing and _unique.cd_now(fig, now) - ref >= int(float(cond.get("ms", 2000)) / TICK_MS)
        if t == "every_ms":
            ref = self.cd_start.get(name, self.cd_born)
            return _unique.cd_now(fig, now) - ref >= int(float(cond.get("ms", 3000)) / TICK_MS)
        if t == "idle_for":
            return self.playing is None and _unique.cd_now(fig, now) - self.cd_idle >= int(float(cond.get("ms", 1000)) / TICK_MS)
        if t == "chance":
            p = max(0.0, min(100.0, float(cond.get("pct_s", 30)))) / 100.0
            return self.rng.random() < 1.0 - (1.0 - p) ** (TICK_MS / 1000.0)
        if t == "action_triggered":
            info = ctx.get("own_action") if cond.get("who") == "self" else ctx.get("tgt_action")
            if not info or not info[0]:
                return False
            want = str(cond.get("action") or "").strip()
            if want and info[0] != want:
                return False
            return now - info[1] <= int(float(cond.get("ms", 300)) / TICK_MS)
        return False

    def _cond_met(self, fig, name, cond, ctx):
        r = self._cond_true(fig, name, cond, ctx)
        return (not r) if cond.get("not") else r

    def _conds_pass(self, fig, name, cfg, ctx):
        res = [self._cond_met(fig, name, c, ctx) for c in cfg.get("conditions") or []
               if c.get("type") in CONDITION_TYPES]
        if not res:
            return False
        return all(res) if cfg.get("logic") == "all" else any(res)

    def _triggered(self, fig, name, ctx, now):
        cfg = _cfg(fig, name)
        if not cfg.get("conditions") or _unique.cd_now(fig, now) < self.cooldown_until.get(name, 0):
            return False
        return self._conds_pass(fig, name, cfg, ctx)

    # ------------------------------------------------------------ playback
    def _frames(self, fig, name):
        ex = fig.render.bundle.extra.get(name)
        n = len(ex[0]) if ex and ex[0] else 0
        char = fig.mode.character
        act = (char.get("actions") or {}).get(name) or {}
        fm = float(act.get("frame_ms") or 0) or (float(act.get("duration_ms") or 100 * max(1, n)) / max(1, n))
        return n, max(1.0, fm)

    def stamp_start(self, fig, name, now):
        """`name` started at world tick `now` (and on the cooldown clock)."""
        self.last_start[name] = now
        self.cd_start[name] = _unique.cd_now(fig, now)

    def stamp_end(self, fig, name, now):
        """`name` ended at world tick `now` (and on the cooldown clock)."""
        self.last_end[name] = now
        self.cd_end[name] = _unique.cd_now(fig, now)

    def stamp_idle(self, fig, now):
        """Idle since world tick `now` (and on the cooldown clock)."""
        self.idle_since = now
        self.cd_idle = _unique.cd_now(fig, now)

    def mark_fired(self, fig, name, cfg, ctx, now):
        """`name` fired now: the counters that belong to it restart (an
        action, or a Time control keyed "@time:<action>")."""
        self.stamp_start(fig, name, now)
        self.since_attacks[name] = 0
        self.since_hits[name] = 0
        for c in cfg.get("conditions") or []:
            if c.get("type") == "hp_below" and not c.get("not") and ctx["hp_pct"] <= float(c.get("pct", 50)):
                self.hp_fired.setdefault(name, set()).add(float(c.get("pct", 50)))

    def _start(self, fig, name, ctx, now):
        n, _fm = self._frames(fig, name)
        if n <= 0:
            return False
        cfg = _cfg(fig, name)
        self.playing = name
        self.elapsed = 0.0
        self.loops_left = max(1, int(round(float(cfg.get("anim_loops") or 1)))) if _kind(name) != "locomotion" else 1
        self.started = now
        self.leap = None
        if self.leap_dmg is not None and self.leap_dmg[0] == name:
            self.leap_dmg = None
        # Cooldowns run on the fighter's cooldown clock (Berserker rage
        # speeds it up, laser/unique.py).
        cd = float(cfg.get("cooldown_ms") or 0)
        self.cooldown_until[name] = _unique.cd_now(fig, now) + int(cd / TICK_MS)
        # Counters that belong to this action restart when it fires.
        self.mark_fired(fig, name, cfg, ctx, now)
        if _kind(name) == "attack":
            self.attack_count += 1
            for k in list(self.since_attacks.keys()):
                if k != name:
                    self.since_attacks[k] += 1
        c = fig.combat
        c.action_anim = name
        c.action_idx = 0
        _unique.on_action_start(fig, name)   # Basic Stacks: a normal attack fires orbs
        return True

    def _finish(self, fig, now):
        name = self.playing
        self.playing = None
        self._leap_settle(fig)
        c = fig.combat
        if c.action_anim == name:
            c.action_anim = None
            c.action_idx = 0
        self.history.append(name)
        del self.history[:-HISTORY]
        self.stamp_end(fig, name, now)
        self.stamp_idle(fig, now)
        if _kind(name) == "attack":
            self.last_attack_end = now
            self.gap_until = _unique.cd_now(fig, now) + int(DEFAULT_ATTACK_GAP_MS / TICK_MS)
            self.chain_pos = name
        self._restore_speed(fig)

    def _restore_speed(self, fig):
        if self.base_speed is not None:
            fig.motion.speed = self.base_speed
            self.base_speed = None

    def stop(self, fig):
        if self.playing:
            self._finish(fig, 0)

    def _attack_ok(self, fig, name, ctx, now):
        """Attack `name` may start now: off cooldown, target inside its
        range, its trigger conditions (if any) pass, and it has frames."""
        if _unique.cd_now(fig, now) < self.cooldown_until.get(name, 0):
            return False
        if ctx["dist"] > attack_range(fig, name, now):
            return False
        cfg = _cfg(fig, name)
        if cfg.get("conditions") and not self._conds_pass(fig, name, cfg, ctx):
            return False
        if not _unique.clone_allows(fig, name):   # Mirror Legion copy: ticked actions only
            return False
        return name in fig.render.bundle.extra

    def _attack_choice(self, fig, ctx, now):
        """Next attack to play, or None (archetype decides when).

        1. The chain: within chain_reset_ms of the last attack, its
           chain_next plays when it can start.
        2. Conditional alternates: any other attack_normal_N with trigger
           conditions plays in place of attack_normal once they pass (and
           the target is inside its range); first by name.
        3. attack_normal.
        A chained attack that can't start falls through to 2 / 3 instead of
        holding every attack until the chain resets."""
        if ctx["target"] is None:
            return None
        if _unique.cd_now(fig, now) < self.gap_until:
            return None
        nxt = ""
        if self.chain_pos:
            cfg = _cfg(fig, self.chain_pos)
            reset = float(cfg.get("chain_reset_ms") or 1000)
            nxt = cfg.get("chain_next") or ""
            if nxt and now - self.last_attack_end <= int(reset / TICK_MS):
                if self._attack_ok(fig, nxt, ctx, now):
                    return nxt
            else:
                self.chain_pos = None
                nxt = ""
        names = sorted(k for k in (fig.mode.character.get("actions") or {})
                       if _kind(k) == "attack" and k != "attack_normal" and k != nxt)
        for name in names:
            if _cfg(fig, name).get("conditions") and self._attack_ok(fig, name, ctx, now):
                return name
        return "attack_normal" if self._attack_ok(fig, "attack_normal", ctx, now) else None

    def observe(self, fig, world):
        """Take this tick's readings (HP lost, speeds, the target's state)
        and return the condition context.  Once per tick: update() calls it
        for image characters; laser/retreat.py calls it (through
        tracker_ctx) for any other fighter with a Tactical retreat."""
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
        if self.born is None:
            self.born = now
            self.cd_born = _unique.cd_now(fig, now)
            self.stamp_idle(fig, now)
        # HP lost (damage_taken), own / target speed (px/s over SPEED_WINDOW ticks).
        if self.last_hp is not None and p.hp < self.last_hp:
            self.hp_drops.append((now, self.last_hp - p.hp))
            if self.resisted_hp > 0:
                self.resisted_drops.append((now, min(self.resisted_hp, self.last_hp - p.hp)))
        self.resisted_hp = 0.0
        self.last_hp = p.hp
        keep = now - int(DAMAGE_WINDOW_MS / TICK_MS)
        while self.hp_drops and self.hp_drops[0][0] <= keep:
            self.hp_drops.pop(0)
        while self.resisted_drops and self.resisted_drops[0][0] <= keep:
            self.resisted_drops.pop(0)
        if self.tgt_track and not battle:
            dxc = tx - self.tgt_track[-1][0]
            if dxc < -0.5:
                self.cursor_facing_left = True
            elif dxc > 0.5:
                self.cursor_facing_left = False
        own_speed = _track_speed(self.own_track, fig.x, fig.y)
        tgt_speed = _track_speed(self.tgt_track, tx, ty)
        tgt_state, tgt_facing_left = None, (None if battle else self.cursor_facing_left)
        if battle:
            i = _nearest_index(world.partner_figures, fig.x, fig.y)
            # A Black Ox Effigy taunting it (laser/summoner.py): read the effigy.
            _taunt = _unique.taunt_point(world, fig.x, fig.y)
            if _taunt is not None:
                i = _nearest_index(world.partner_figures, _taunt[0], _taunt[1])
            st = getattr(world, "partner_state", None) or []
            fc = getattr(world, "partner_facing", None) or []
            if 0 <= i < len(st):
                tgt_state = st[i]
            if 0 <= i < len(fc):
                tgt_facing_left = fc[i]
        ctx = {"target": (tx, ty), "dist": dist, "now": now,
               "hp_pct": 100.0 * p.hp / max(1e-6, p.max_hp),
               "hit_tags": self.hit_tags, "defend_tags": self.defend_tags, "deflected": self.deflected,
               "enemy_fx": getattr(world, "enemy_fx", None) or [],
               "own_speed": own_speed, "tgt_speed": tgt_speed, "tgt_state": tgt_state,
               "tgt_facing_left": tgt_facing_left, "landed": self.landed,
               "own_action": action_info(fig, now),
               "tgt_action": (tuple(tgt_state[3:5]) if tgt_state and len(tgt_state) >= 5 else None)}
        self.ctx = ctx
        self.ctx_tick = now
        return ctx

    def end_tick(self):
        """Per-tick events (hits taken, hits landed) are read: clear them."""
        self.hit_tags = []
        self.defend_tags = []
        self.landed = 0

    def force(self, fig, name, until, root, now):
        """Play `name` now (cutting into whatever plays) and keep looping it
        until tick `until`; a later call can only extend it."""
        if self.forced == name and self.playing == name:
            self.forced_until = max(self.forced_until, until)
            self.forced_root = self.forced_root or bool(root)
            return True
        n, _fm = self._frames(fig, name)
        if n <= 0:
            return False
        if self.playing is not None:
            self._finish(fig, now)
        self.playing = name
        self.elapsed = 0.0
        self.loops_left = 10 ** 6
        self.started = now
        self.forced, self.forced_until, self.forced_root = name, until, bool(root)
        fig.combat.action_anim = name
        fig.combat.action_idx = 0
        return True

    def update(self, fig, world):
        """One tick.  Returns True when the fighter is rooted this tick
        (MotionSystem then leaves it where it is)."""
        now = world.global_tick
        c = fig.combat
        ctx = self.observe(fig, world)
        tx, ty = ctx["target"]
        if not fig.transform.init:
            # Not placed yet (MotionSystem places a fighter on its first
            # un-rooted tick): starting an action now would root it at its
            # spawn corner, with distances measured from there.
            self.end_tick()
            self.acted = False
            return False
        if self.forced is not None and (self.playing != self.forced or now >= self.forced_until):
            if self.playing == self.forced:
                self._finish(fig, now)
            self.forced = None

        # Attack mode (Alt+Up) gates attacking exactly as it gates the
        # built-in fighters; defend is always allowed.
        armed = bool(getattr(world, "shoot_mode", True))
        # A triggered action (defend, ultimate, special, ...) whose conditions
        # are met cuts into a normal attack instead of waiting for it to end
        # — the moment (target in range, a hit, an incoming shot) would
        # otherwise be gone.  It never cuts into another triggered action.
        if self.playing is not None and self.forced is None and _kind(self.playing) == "attack":
            names = [k for k in (fig.mode.character.get("actions") or {})
                     if _kind(k) == "triggered" and k not in SWITCH_ACTIONS]
            for name in sorted(names, key=lambda k: (0 if k == "defend" else 1 if k == "ultimate" else
                                                      2 if k == "attack_special" else 3, k)):
                if not armed and name != "defend":
                    continue
                if not _unique.clone_allows(fig, name):   # Mirror Legion copy: ticked actions only
                    continue
                if name in fig.render.bundle.extra and self._triggered(fig, name, ctx, now):
                    self._finish(fig, now)
                    self._start(fig, name, ctx, now)
                    break
        if self.playing is None:
            # Triggered actions first (defend, then ultimate, special, others).
            names = [k for k in (fig.mode.character.get("actions") or {})
                     if _kind(k) == "triggered" and k not in SWITCH_ACTIONS]
            order = sorted(names, key=lambda k: (0 if k == "defend" else 1 if k == "ultimate" else
                                                 2 if k == "attack_special" else 3, k))
            for name in order:
                if not armed and name != "defend":
                    continue
                if not _unique.clone_allows(fig, name):   # Mirror Legion copy: ticked actions only
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
                if name == self.forced:
                    cfg = dict(cfg, movement="stand" if self.forced_root else "move", move_speed_pct=100.0)
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
                elif cfg.get("movement") == "leap" and not (fig.motion.bouncing or fig.motion.bounce_ending):
                    rooted = True
                    fig.render.is_moving = False
                    self._leap_step(fig, name, cfg, n, fm, tx, ty)
                elif cfg.get("movement") == "move":
                    pct = max(0.0, float(cfg.get("move_speed_pct") or 0)) / 100.0
                    if self.base_speed is None:
                        self.base_speed = fig.motion.speed
                    fig.motion.speed = self.base_speed * pct
                elif fig.motion.bouncing or fig.motion.bounce_ending:
                    # A knockback always moves the fighter, even mid-action
                    # (and knocks a leap out of the air: it doesn't resume).
                    if self.leap is not None:
                        self.leap["done"] = True
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
        self.end_tick()
        self.acted = rooted
        return rooted

    def blocking(self):
        return self.playing == "defend"

    # ------------------------------------------------------------ leap
    def _leap_step(self, fig, name, cfg, n, fm, tx, ty):
        """Movement "leap", one tick (the action's frames carry the pose; this
        carries the body).  Before leap.start_frame: stand facing the target.
        At it: lock the target's spot.  Until leap.land_frame starts: travel
        there along a hop arc.  After: stay landed.  Each loop leaps anew."""
        lp = cfg.get("leap") or {}
        f0 = max(0, int(lp.get("start_frame") or 0))
        f1 = int(lp.get("land_frame") if lp.get("land_frame") is not None else -1)
        if f1 < 0 or f1 > n:
            f1 = n
        f1 = max(f0 + 1, f1)
        t = self.elapsed - TICK_MS          # time into this loop before this tick
        st = self.leap
        if st is not None and t < st["t0"]:
            st = self.leap = None           # a new loop: leap again
        if st is None:
            if t < f0 * fm:
                dx = tx - fig.x
                if dx < -0.001:
                    fig.transform.facing_left = True
                elif dx > 0.001:
                    fig.transform.facing_left = False
                return
            from . import combat as _combat
            left = (tx < fig.x) if abs(tx - fig.x) > 0.001 else fig.transform.facing_left
            sw, sh = fig.screen_w, fig.screen_h
            ps = _combat.position_scale(tx, ty, sw, sh)
            ox, oy = _leap_hit_offset(fig, name, cfg, f1, -1.0 if left else 1.0, ps)
            ex = max(0.0, min(float(sw), tx - ox))
            ey = max(0.0, min(float(sh), ty - oy))
            frac = _leap_frac(lp, ((tx - fig.x) ** 2 + (ty - fig.y) ** 2) ** 0.5)
            h = _leap_height(lp, frac) * fig._position_scale()
            if lp.get("damage_mode") == "range":
                d0, d1 = float(lp.get("damage_min") or 0), float(lp.get("damage_max") or 0)
                self.leap_dmg = (name, round(max(0.0, d0 + (d1 - d0) * frac), 2))
            else:
                self.leap_dmg = None
            st = self.leap = dict(sx=fig.x, sy=fig.y, ex=ex, ey=ey, t0=f0 * fm, t1=f1 * fm,
                                  h=h, left=left, done=False)
        fig.transform.facing_left = st["left"]
        if st["done"]:
            return
        u = max(0.0, min(1.0, (t + TICK_MS - st["t0"]) / max(1.0, st["t1"] - st["t0"])))
        fig.transform.x = st["sx"] + (st["ex"] - st["sx"]) * u
        fig.transform.y = st["sy"] + (st["ey"] - st["sy"]) * u - st["h"] * 4.0 * u * (1.0 - u)
        if u >= 1.0:
            st["done"] = True

    def _leap_settle(self, fig):
        """The action ended (or was cut) mid-air: drop straight to the ground
        line under the arc so the fighter isn't left hanging."""
        st = self.leap
        self.leap = None
        if st is None or st["done"] or st["h"] <= 0:
            return
        dx = st["ex"] - st["sx"]
        u = (fig.x - st["sx"]) / dx if abs(dx) > 1e-6 else 0.0
        u = max(0.0, min(1.0, u))
        fig.transform.y = st["sy"] + (st["ey"] - st["sy"]) * u


def _leap_frac(lp, dist):
    """Where this leap sits in its range, 0..1: the target at dist_min_px or
    closer = 0, at dist_max_px or farther = 1, in proportion between.  It
    picks the arc height (height_px .. height_max_px) and, in "range" damage
    mode, the damage (damage_min .. damage_max)."""
    lo = float(lp.get("dist_min_px") or 0)
    hi = float(lp.get("dist_max_px") or 0)
    if hi <= lo:
        return 1.0 if dist >= lo else 0.0
    return max(0.0, min(1.0, (dist - lo) / (hi - lo)))


def _leap_height(lp, frac):
    """Arc height (game px at 100 %): height_px, or with height_max_px set,
    height_px .. height_max_px by frac."""
    h0 = max(0.0, float(lp.get("height_px") or 0))
    h1 = lp.get("height_max_px")
    if h1 is None:
        return h0
    return h0 + (max(0.0, float(h1 or 0)) - h0) * frac


def leap_damage(fig, action):
    """Damage every Deals-damage FX of `action` deals for this fighter's
    current leap ("range" damage mode), or None = the FX's own damage."""
    r = getattr(fig, "act", None)
    ld = getattr(r, "leap_dmg", None) if r is not None else None
    if ld is not None and ld[0] == action:
        return ld[1]
    return None


def _leap_hit_offset(fig, name, cfg, land, facing, ps):
    """Where the leap's hit lands relative to the fighter's position (game
    px, facing +1 right / -1 left, at position scale ps), so the leap can
    put that point on the target: leap.hit_px [x forward, y] when set; else
    the action's damaging FX (Deals damage) starting nearest land_frame —
    its anchor plus offset; else the weapon tip (wtip) on land_frame; else
    the body itself."""
    from .fxkit import character_fx
    hp = (cfg.get("leap") or {}).get("hit_px")
    if isinstance(hp, (list, tuple)) and len(hp) >= 2:
        return float(hp[0] or 0) * ps * facing, float(hp[1] or 0) * ps
    cfx = character_fx(fig.mode)
    if cfx is None:
        return 0.0, 0.0

    def anchor_off(ident):
        if not ident or ident in ("figure", "target") or str(ident).startswith("set:"):
            return 0.0, 0.0
        p = cfx.anchor_px(name, ident, land)
        if p is None:
            return 0.0, 0.0
        k = cfx.k * ps
        return (p[0] - cfx.origin[0]) * k * facing, (p[1] - cfx.origin[1]) * k

    best = None
    for fx in cfx.effects:
        if fx.get("action") != name or not (fx.get("battle") or {}).get("deals_damage"):
            continue
        d = abs(int(fx.get("start_frame") or 0) - land)
        if best is None or d < best[0]:
            best = (d, fx)
    if best is not None:
        fx = best[1]
        if fx.get("anchor") == "target":
            return 0.0, 0.0
        ax, ay = anchor_off(fx.get("anchor"))
        off = fx.get("offset") or [0, 0]
        return ax + float(off[0] or 0) * ps * facing, ay + float(off[1] or 0) * ps
    return anchor_off("wtip")


# ------------------------------------------------------------ module hooks
def runner(fig):
    r = getattr(fig, "act", None)
    if r is None and is_image(fig):
        r = ActionRunner()
        fig.act = r
    return r


def attack_range(fig, name, now=None):
    """How close the target must be for attack `name` to start: its own
    attack_px (Attack distance) when set, else stats.basic_attack_radius
    (shooters: at least SHOOTER_RANGE_PX); times the character scale.  An
    attack whose Blink lands on the target ("target" anchor) reaches at
    least as far as that blink's proximity_px (character scale too) —
    unless its Blink is on cooldown at tick `now`."""
    mode = fig.mode
    own = float(_cfg(fig, name).get("attack_px") or 0)
    if own > 0:
        rng = own * mode.body_scale()
    else:
        radius = float(config.MODE_CONFIGS.get(mode.key, {}).get("basic_attack_radius", config.SLASH_RADIUS)) * mode.body_scale()
        rng = radius if mode.uses_melee() or not mode.can_shoot() else max(radius, SHOOTER_RANGE_PX)
    from . import blink as _blink
    b = _blink.config_for(fig, name)
    if b and not (now is not None and _blink._cooling(fig, getattr(fig, "blink", None), name, now)):
        reach = [float(x.get("proximity_px") or 0) for x in b.get("blinks") or () if x.get("anchor") == "target"]
        if reach:
            rng = max(rng, max(reach) * mode.body_scale())
    return rng


CHASE_REACH = 0.5     # a chasing image character closes to this share of its attack range


def chase_offset(fig, world):
    """MotionSystem: the chase offset for an image character, or None = its
    formation offset (config.FIGURE_OFFSETS, which spreads fighters round
    their target).  While Attack mode is on, the offset is shortened to
    CHASE_REACH of its normal attack's range, so the chase ends where it can
    attack: P1's 100 px slot used to hold a short-range fighter (Puck: 40 px)
    just out of reach, attacking only when the enemy walked into it.  Same
    for Solo (the cursor) and Battle (the nearest enemy)."""
    if not is_image(fig) or not getattr(world, "shoot_mode", True):
        return None
    m = fig.motion
    d = (m.offset_x * m.offset_x + m.offset_y * m.offset_y) ** 0.5
    reach = attack_range(fig, "attack_normal") * CHASE_REACH
    if d <= reach:
        return None
    k = reach / d if d > 1e-6 else 0.0
    return m.offset_x * k, m.offset_y * k


def tracker_ctx(fig, world):
    """(runner, ctx) for conditions evaluated outside the action runner
    (the Tactical retreat).  Image characters reuse their ActionRunner and
    the readings it took this tick; any other fighter gets a runner used
    only as a condition tracker (it never plays actions), whose attacks are
    its dashes / slashes."""
    r = getattr(fig, "act", None)
    if r is None:
        r = ActionRunner()
        fig.act = r
    now = world.global_tick
    if r.ctx is not None and r.ctx_tick == now:
        return r, r.ctx
    if not is_image(fig):
        c = fig.combat
        attacking = bool(c.dashing or c.slashing)
        if attacking and not r.was_attacking:
            r.attack_count += 1
            for k in list(r.since_attacks.keys()):
                r.since_attacks[k] += 1
        r.was_attacking = attacking
        if attacking:
            r.stamp_idle(fig, now)
    ctx = r.observe(fig, world)
    if not is_image(fig):
        r.end_tick()
    return r, ctx


def update(fig, world):
    """CombatSystem hook for image characters; returns 'rooted this tick'."""
    r = runner(fig)
    return r.update(fig, world) if r is not None else False


def force_clash(fig, world, until, root):
    """laser/clash.py: one of this fighter's FX is clashing — show its
    "clash" action (a Rig Forge action; none = nothing happens) until tick
    `until`, standing still when `root`.  True when it plays."""
    r = runner(fig)
    if r is None or "clash" not in fig.render.bundle.extra:
        return False
    return r.force(fig, "clash", until, root, world.global_tick)


def force_attack(fig, world):
    """Start attack_normal now if nothing is playing (tactical retreat's
    re-engage strike).  True when it started."""
    r = runner(fig)
    if r is None or r.playing is not None or "attack_normal" not in fig.render.bundle.extra:
        return False
    if not _unique.clone_allows(fig, "attack_normal"):
        return False
    p = fig.personality
    return r._start(fig, "attack_normal", {"hp_pct": 100.0 * p.hp / max(1e-6, p.max_hp)},
                    world.global_tick)


def force_ultimate(fig, world):
    """Manual ultimate hotkey (Ctrl+1 / Ctrl+2, see
    combat.try_fire_manual_ultimate) for an image character: start its
    `ultimate` action now, skipping its trigger conditions, its cooldown
    and Attack mode.  It cuts into a normal attack (or idle / run) but
    waits for another triggered action (defend, special, ...) to end.  True = the request is
    used up (started, or the character has no ultimate frames); False =
    keep it queued and try again next tick."""
    r = runner(fig)
    if r is None or "ultimate" not in fig.render.bundle.extra:
        return True
    if not _unique.clone_allows(fig, "ultimate"):   # Mirror Legion copy without it
        return True
    if r.playing is not None:
        if _kind(r.playing) == "triggered":
            return False
        r._finish(fig, world.global_tick)
    p = fig.personality
    r._start(fig, "ultimate", {"hp_pct": 100.0 * p.hp / max(1e-6, p.max_hp)},
             world.global_tick)
    return True


def force_special(fig, world):
    """Sword duel finisher (laser/clash.py): start this image character's
    attack_special now, skipping its trigger conditions, its cooldown and
    Attack mode.  It cuts into a normal attack, idle / run, or the forced
    "clash" action, but waits for another triggered action (defend,
    ultimate, ...) to end.  True = the request is used up (started, or no
    attack_special frames); False = try again next tick."""
    r = runner(fig)
    if r is None or "attack_special" not in fig.render.bundle.extra:
        return True
    if not _unique.clone_allows(fig, "attack_special"):
        return True
    now = world.global_tick
    if r.playing is not None:
        if _kind(r.playing) == "triggered" and r.playing != r.forced:
            return False
        r._finish(fig, now)
        r.forced = None
    p = fig.personality
    r._start(fig, "attack_special", {"hp_pct": 100.0 * p.hp / max(1e-6, p.max_hp)}, now)
    return True


def force_action(fig, world, name):
    """laser/dodge.py: play `name` now (the dodge action, or the counter
    after it), skipping its trigger conditions and cooldown.  It cuts into
    idle / run, a normal attack, or `name` itself, but never into another
    triggered action, the ultimate or a forced clash.  True when it started."""
    r = runner(fig)
    if r is None or not name or name not in fig.render.bundle.extra:
        return False
    if not _unique.clone_allows(fig, name):
        return False
    now = world.global_tick
    if r.playing is not None:
        if r.forced is not None or (_kind(r.playing) == "triggered" and r.playing != name):
            return False
        r._finish(fig, now)
    p = fig.personality
    return r._start(fig, name, {"hp_pct": 100.0 * p.hp / max(1e-6, p.max_hp)}, now)


def blocks_hit(fig):
    """True while this fighter's `defend` action plays: the hit is blocked."""
    r = getattr(fig, "act", None)
    return bool(r is not None and r.blocking())


def note_fx_hit(fig, tag):
    r = getattr(fig, "act", None)
    if r is not None:
        r.next_tag = tag or ""


def note_damage(fig, amount=0.0):
    r = getattr(fig, "act", None)
    if r is not None:
        r.note_damage(amount)


def note_resisted(fig):
    """The next hit this fighter takes was resisted by its anti-knockback
    (ai.resists_knockback): it won't count toward `defend`'s conditions."""
    r = getattr(fig, "act", None)
    if r is not None:
        r.next_resisted = True


def clear_resisted(fig):
    """Drop an unused note_resisted mark (the hit was blocked or immune)."""
    r = getattr(fig, "act", None)
    if r is not None:
        r.next_resisted = False


def note_landed(fig, amount=1.0):
    """One of this fighter's FX hits connected (landed_hit condition);
    amount = its damage."""
    _movestyle.note_hit_landed(fig)
    _unique.note_landed(fig, amount)   # Dual Form gauge / combo, Domain gauge, Fusion, Basic Stacks
    r = getattr(fig, "act", None)
    if r is not None:
        r.landed += 1


def target_state(fig, now=0):
    """(hp_pct, attacking, defending, action, action_start_tick) as the
    opponent's conditions see this fighter: attacking = dashing / slashing,
    or an image character playing an attack, attack_special or ultimate;
    defending = parrying or `defend`; action / start = action_info."""
    p, c = fig.personality, fig.combat
    hp = 100.0 * p.hp / max(1e-6, p.max_hp)
    attacking = bool(c.dashing or c.slashing)
    r = getattr(fig, "act", None)
    if r is not None and r.playing:
        attacking = attacking or r.playing.startswith("attack") or r.playing == "ultimate"
    defending = bool(c.parrying) or blocks_hit(fig)
    name, start = action_info(fig, now)
    return (hp, attacking, defending, name, start)


def current_action_name(fig):
    """The action this fighter is doing, as the action_triggered condition
    names it: an image character's playing action; for a built-in fighter
    its ultimate (vanish-cut, special stance, loop beam, ultimate crescents)
    = "ultimate", a dash / slash = "attack_normal", a parry = "defend".
    None while it only stands or moves."""
    r = getattr(fig, "act", None)
    if r is not None and r.playing:
        return r.playing
    if is_image(fig):
        return None
    c = fig.combat
    if c.vc_phase or getattr(c, "sp_phase", 0) or getattr(c, "lb_phase", 0) or c.ult_crescents:
        return "ultimate"
    if c.dashing or c.slashing:
        return "attack_normal"
    if c.parrying:
        return "defend"
    return None


def action_info(fig, now):
    """(action, tick it started) for the action_triggered condition; the
    start is the first tick the action was seen (an image character's own
    start tick when it has one).  (None, 0) while no action plays."""
    from .timefx import state
    st = state(fig)
    name = current_action_name(fig)
    if name != st.act_name:
        st.act_name = name
        r = getattr(fig, "act", None)
        st.act_start = (r.last_start.get(name, now) if (r is not None and name and r.playing == name) else now)
    return (name, st.act_start) if name else (None, 0)
