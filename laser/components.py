"""
Components — the small, focused pieces a Figure is composed of.

Each component owns one concern and (where it has visuals) draws itself.  A
localized feature touches a single component; nothing else needs to know.

  Transform   position, facing, rotation, init flag
  MotionState movement speeds + bounce/path/runaway state
  TrailComponent  the neon trail (owns its deque + draw)
  Renderable  sprite frames + animation indices (owns sprite draw)
  Combatant   dash/slash/dodge/combo/crescent state  (logic lands stage 2)
  Personality per-figure RNG + battle temperament    (used stage 3)
"""

import math
import os
import random
from collections import deque

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QRadialGradient

from . import config
from .palette import LUT_MASK


class Transform:
    __slots__ = ("x", "y", "facing_left", "angle", "init")

    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.facing_left = False
        self.angle = 0.0
        self.init = False


class MotionState:
    __slots__ = ("speed", "follow_speed", "offset_x", "offset_y",
                 "min_move_sq", "rotate",
                 "bounce_vx", "bounce_vy", "bouncing",
                 "bounce_ending", "bounce_end_ticks",
                 "path", "follow", "runaway",
                 "battle_bounce_vx", "battle_bounce_vy")

    def __init__(self, speed, follow_speed, offset_x=0, offset_y=0,
                 min_move=0.5, rotate=False):
        self.speed = speed
        self.follow_speed = follow_speed
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.min_move_sq = min_move * min_move
        self.rotate = rotate
        self.bounce_vx = self.bounce_vy = 0.0
        self.bouncing = False
        self.bounce_ending = False
        self.bounce_end_ticks = 0
        self.path = deque(maxlen=4000)
        self.follow = False
        self.runaway = False
        self.battle_bounce_vx = 0.0
        self.battle_bounce_vy = 0.0


class TrailComponent:
    __slots__ = ("trail", "flow_off", "lut", "gradient")

    def __init__(self, lut, gradient=None):
        self.trail = deque(maxlen=5000)
        self.flow_off = 0.0
        self.lut = lut
        self.gradient = gradient

    def clear(self):
        self.trail.clear()

    def update(self, x, y, facing_left, is_moving, path_follow,
               apply_offset=True):
        """Append a trail point behind/below the figure; decay when idle.

        apply_offset=False bypasses the TRAIL_BACK/TRAIL_DOWN body offset —
        used when (x, y) is already a specific anchor point (e.g. a
        sprite_emitter trail_anchor source), so the trail pins exactly to
        that point instead of being nudged behind/below it."""
        trail = self.trail
        if apply_offset:
            tx = x + config.TRAIL_BACK if facing_left else x - config.TRAIL_BACK
            ty = y + config.TRAIL_DOWN
        else:
            tx, ty = x, y
        if not trail:
            moved = True
        else:
            lx, ly = trail[-1]
            ddx, ddy = tx - lx, ty - ly
            moved = ddx * ddx + ddy * ddy >= config.TRAIL_MIN_D_SQ
        if moved:
            trail.append((tx, ty))
            if not path_follow:
                while len(trail) > config.TRAIL_LEN:
                    trail.popleft()
        if not path_follow and not is_moving:
            for _ in range(config.TRAIL_DECAY):
                if len(trail) > 1:
                    trail.popleft()
        self.flow_off = (self.flow_off + config.TRAIL_FLOW_SPD) % 1.0

    def _color_at(self, t):
        """(r, g, b) for trail position t in [0, 1] (0 = oldest/tail end,
        1 = newest/head end, at the figure). With a trail_gradient override
        set, this is a static two-colour gradient by position alone (no
        flow animation): solid start_color up to start_fraction, then a
        linear fade to end_color over the remainder. Without an override,
        falls back to the default flowing LUT colour (unchanged
        behaviour)."""
        g = self.gradient
        if g is not None:
            (sr, sg, sb), (er, eg, eb), sf = g
            if t <= sf:
                return sr, sg, sb
            span = max(1e-6, 1.0 - sf)
            k = (t - sf) / span
            return (sr + (er - sr) * k, sg + (eg - sg) * k,
                    sb + (eb - sb) * k)
        idx = int(((t + self.flow_off) % 1.0) * 256) & LUT_MASK
        return self.lut[idx]

    def draw(self, p, pen, path_follow):
        trail = self.trail
        n = len(trail)
        if n <= 1:
            return
        tl = list(trail)
        inv_n = 1.0 / n

        if path_follow:
            pen.setWidthF(3.0)
            for i in range(1, n):
                r, g, b = self._color_at(i * inv_n)
                pen.setColor(QColor(int(r), int(g), int(b), 215))
                p.setPen(pen)
                x0, y0 = tl[i - 1]; x1, y1 = tl[i]
                p.drawLine(int(x0), int(y0), int(x1), int(y1))
        else:
            tw0, tw1 = config.TRAIL_W_TAIL, config.TRAIL_W_HEAD
            for i in range(1, n):
                t = i * inv_n
                r, g, b = self._color_at(t)
                pen.setColor(QColor(int(r), int(g), int(b), int(220 * t)))
                pen.setWidthF(tw0 + (tw1 - tw0) * t)
                p.setPen(pen)
                x0, y0 = tl[i - 1]; x1, y1 = tl[i]
                p.drawLine(int(x0), int(y0), int(x1), int(y1))

        # Head glow + bright core
        hx, hy = int(tl[-1][0]), int(tl[-1][1])
        r, g, b = self._color_at(1.0)
        r, g, b = int(r), int(g), int(b)
        gr = config.TRAIL_GLOW_R
        grad = QRadialGradient(hx, hy, gr)
        grad.setColorAt(0.0, QColor(r, g, b, 140))
        grad.setColorAt(0.4, QColor(r, g, b, 60))
        grad.setColorAt(1.0, QColor(r, g, b, 0))
        p.setPen(Qt.NoPen); p.setBrush(grad)
        p.drawEllipse(hx - gr, hy - gr, gr * 2, gr * 2)

        dr = config.TRAIL_DOT_R
        core = QRadialGradient(hx, hy, dr)
        core.setColorAt(0.0, QColor(255, 255, 255, 200))
        core.setColorAt(0.5, QColor(r, g, b, 180))
        core.setColorAt(1.0, QColor(r, g, b, 100))
        p.setBrush(core)
        p.drawEllipse(hx - dr, hy - dr, dr * 2, dr * 2)


class Renderable:
    """Sprite frames + animation cursor. Frame *selection* lives in Figure.draw,
    which is the one place that sees motion + combat state together."""

    __slots__ = ("bundle", "run_idx", "idle_idx",
                 "anim_tick", "anim_speed", "idle_anim_speed", "is_moving",
                 "outline_glow", "afterimage_rgb")

    def __init__(self, bundle, anim_speed, idle_anim_speed, outline_glow=None,
                 afterimage_rgb=None):
        self.bundle = bundle
        self.run_idx = 0
        self.idle_idx = 0
        self.anim_tick = 0
        self.anim_speed = anim_speed
        self.idle_anim_speed = idle_anim_speed
        self.is_moving = False
        # Optional ((r,g,b), radius_px, opacity) for the generic outline-glow
        # feature (JSON `outline_glow` opt-in); None = no outline, drawn
        # identically in Solo and Battle since it lives in Figure.draw.
        self.outline_glow = outline_glow
        # Optional (r,g,b) opt-in (JSON `afterimage_color`) recolouring this
        # character's dash/blink speed-ghosts away from the default crimson
        # (combat.silhouette's own fallback covers every character that
        # doesn't set this).
        self.afterimage_rgb = afterimage_rgb

    def set_bundle(self, bundle):
        self.bundle = bundle
        self.run_idx = self.idle_idx = self.anim_tick = 0

    def advance(self):
        self.anim_tick += 1
        if self.is_moving:
            if self.anim_tick >= self.anim_speed:
                self.anim_tick = 0
                if self.bundle.run:
                    self.run_idx = (self.run_idx + 1) % len(self.bundle.run)
        else:
            if self.anim_tick >= self.idle_anim_speed:
                self.anim_tick = 0
                if self.bundle.idle:
                    self.idle_idx = (self.idle_idx + 1) % len(self.bundle.idle)


class Combatant:
    """Holds all swordsman/shooter combat state. Behaviour lands in combat.py
    at stage 2 — the fields live here now so the Figure shape stays stable."""

    __slots__ = ("dashing", "rebounding", "slashing",
                 "slash_phase", "slash_idx", "slash_tick", "slash_vx", "slash_vy",
                 "slash_dist_budget",
                 "combo_count", "combo_pending", "combo_target",
                 "combo_follow_ups", "combo_cooldown_ticks", "combo_delay_ticks",
                 "dodge_dashing", "dodge_vx", "dodge_vy", "dodge_dist_budget",
                 "dodge_interrupt", "dodge_counter",
                 "crescents", "acted",
                 "hit_pending", "hit_vx", "hit_vy",
                 "parrying", "parry_cooldown_ticks", "parry_stance_ticks",
                 "arc_combo_active", "arc_combo_hits", "arc_combo_dir",
                 "arc_recoiling", "arc_recoil_ticks",
                 "arc_repositioning", "arc_repo_t", "arc_repo_steps",
                 "arc_center_x", "arc_center_y",
                 "arc_start_angle", "arc_end_angle", "arc_orbit_r",
                 "arc_combo_cooldown_ticks",
                 "arc_recoil_pending",
                 "blink_windup", "blink_fx_pending",
                 "blinkstorm_strikes_left", "blinkstorm_tick",
                 "blinkstorm_angle",
                 "clones", "clone_cd",
                 "arc_r_start", "arc_r_end",
                 "attack_hits", "attack_cooldown_ticks",
                 "followup_pending", "followup_lock_ticks", "followup_lock_type",
                 "ult_crescents", "ult_crescent_pending",
                 "afterimages", "afterimage_tick",
                 "hitstop_request", "impact_fx_pending",
                 "petals", "petals_init",
                 "particle_bursts", "pending_bursts",
                 "hpt_fired", "dmg_teleport_accum",
                 "reaction_cd", "ult_charges",
                 "vc_phase", "vc_tick", "vc_hits_left", "vc_hidden",
                 "vc_dir_x", "vc_dir_y", "vc_shots_pending",
                 "sprite_particles", "sprite_emit_acc",
                 "sprite_prev_x", "sprite_prev_y",
                 "dodged_proj_ids",
                 "manual_ult_queued")

    def __init__(self):
        self.dashing = self.rebounding = self.slashing = False
        self.slash_phase = 0
        self.slash_idx = 0
        self.slash_tick = 0
        self.slash_vx = self.slash_vy = 0.0
        self.slash_dist_budget = 0.0
        self.combo_count = 0
        self.combo_pending = False
        self.combo_target = None
        self.combo_follow_ups = 0      # follow-up dashes used in this combo string
        self.combo_cooldown_ticks = 0  # ticks remaining before follow-ups allowed again
        self.combo_delay_ticks = 0     # ticks to wait before launching follow-up dash
        self.dodge_dashing = False
        self.dodge_vx = self.dodge_vy = 0.0
        self.dodge_dist_budget = 0.0
        self.dodge_interrupt = False
        self.dodge_counter = False
        self.crescents = []
        self.acted = False   # set each tick by CombatSystem; MotionSystem reads it
        self.hit_pending = False  # True when a dash-slash landed this tick
        self.hit_vx = self.hit_vy = 0.0  # knockback impulse dealt to the enemy side
        self.parrying = False           # True while the active parry window is open
        self.parry_cooldown_ticks = 0   # ticks remaining before next parry allowed
        self.parry_stance_ticks = 0     # ticks remaining in the active deflect window
        # Arc combo state
        self.arc_combo_active = False      # True while an arc combo string is running
        self.arc_combo_hits = 0            # hits landed so far in this arc combo string
        self.arc_combo_dir = 1             # +1 = CCW, -1 = CW (alternates each reposition)
        self.arc_recoiling = False         # True during the recoil-dash-back phase
        self.arc_recoil_ticks = 0          # ticks remaining in recoil
        self.arc_repositioning = False     # True during the curved arc reposition phase
        self.arc_repo_t = 0                # current tick within the reposition arc
        self.arc_repo_steps = 0            # total ticks for this reposition arc
        self.arc_center_x = 0.0           # target position when arc reposition started
        self.arc_center_y = 0.0
        self.arc_start_angle = 0.0        # radians: where on circle the reposition starts
        self.arc_end_angle = 0.0          # radians: where it ends
        self.arc_orbit_r = 0.0            # radius of the orbit arc
        self.arc_combo_cooldown_ticks = 0 # ticks before arc combo can fire again
        self.arc_recoil_pending = False    # True after slash anim completes on arc hit; arms recoil
        # Attack string state (50/50 dashslash vs arcslash; unified hit chain)
        self.arc_r_start = 0.0             # arc travel radius at start (interpolated)
        self.arc_r_end = 0.0               # arc travel radius at end
        self.attack_hits = 0               # hits landed in the current attack string
        self.attack_cooldown_ticks = 0     # ~1 s cooldown after a full 3-hit string
        self.followup_pending = 0          # queued follow-up: 0 none / 1 dashslash / 2 arcslash
        self.followup_lock_ticks = 0       # 0.2 s window locking the follow-up type
        self.followup_lock_type = 0        # locked type during the window (1 or 2)
        # Swordsman ultimate crescent state
        self.ult_crescents = []            # list of UltimateCrescent instances
        self.ult_crescent_pending = 0      # ticks until the 2nd ult crescent fires (0 = none)
        # Slash FX state
        self.afterimages = []              # [x, y, frame, age] crimson dash ghosts
        self.afterimage_tick = 0           # spawn-interval counter
        self.hitstop_request = False       # set on big hits; CombatSystem applies freeze
        self.impact_fx_pending = []        # (x, y) hit points awaiting ring+spark spawn
        # Petals defensive FX (see combat.Petal / combat.update_petals): a handful of
        # single particles hovering around the figure that intercept nearby enemy
        # projectiles. Works for ANY archetype (shooter or melee) — identical in
        # Solo & Battle. Lazily populated on first tick from the character's own
        # `petals` fx_layer config (built-ins have none, so this stays empty).
        self.petals = []
        self.petals_init = False
        # Character particle-burst FX (see combat.spawn_character_burst_fx /
        # update_character_bursts): purely cosmetic swarms matching a JSON
        # character's own 'particles' fx_layers (count/spread/speed/gravity/
        # size_over_life/color), spawned locally when that action fires.
        # pending_bursts holds [ticks_remaining, layer, scale, facing] queued
        # entries (authored delay_ms/trig_delay_ms); particle_bursts holds
        # the live BurstParticle instances. Purely local eye-candy.
        self.particle_bursts = []
        self.pending_bursts = []
        # Generic blink system (JSON `blink` block; see combat.blink_cfg).
        self.blink_windup = 0             # combo-warp wind-up counter
        self.blink_fx_pending = []        # (x, y) blink endpoints awaiting spark FX
        self.blinkstorm_strikes_left = 0  # remaining blinkstorm ultimate strikes
        self.blinkstorm_tick = 0          # ticks until the next storm strike
        self.blinkstorm_angle = 0.0       # rotating ring angle (radians)
        # Generic clone system (special_ability preset 'clone').
        self.clones = []                  # live CloneEffect instances
        self.clone_cd = 0                 # ticks until next clone allowed
        # Generic HP-threshold stationary-clone system (JSON
        # `hp_threshold_clones`, see combat.check_hpt_clone_spawns). Set of
        # pct thresholds already fired this life — each fires once ever.
        self.hpt_fired = set()
        # Generic damage-teleport system (JSON `damage_teleport`, see
        # combat.check_damage_teleport). Running total of damage taken
        # since the last teleport jump.
        self.dmg_teleport_accum = 0.0
        # Generic proximity-reaction system (JSON `reaction`, see
        # combat.check_reaction): shared counter/dodge cooldown + charge
        # counter for charge-based ultimates.
        self.reaction_cd = 0              # ticks until next reaction allowed
        self.ult_charges = 0              # charges toward a charge-based ult
        # Generic vanish-cut ultimate (ultimate_playback.style
        # 'vanish_cut', see combat.tick_vanish_cut).
        self.vc_phase = 0                 # 0 idle / 1 vanish / 2 blitz / 3 impact
        self.vc_tick = 0                  # ticks remaining in current phase
        self.vc_hits_left = 0             # blitz hits remaining
        self.vc_hidden = False            # sprite hidden while vanished
        self.vc_dir_x = 1.0               # walk-through direction (unit)
        self.vc_dir_y = 0.0
        self.vc_shots_pending = []        # invisible strike Projectiles
        # Sprite-line emitter FX (see combat.sprite_emitter_cfg /
        # update_sprite_emitter): purely cosmetic particles rising off
        # colour-matched lines inside the character's own sprite frames.
        # sprite_particles holds live SpriteEmitParticle instances;
        # sprite_emit_acc is the fractional spawn-rate accumulator.
        self.sprite_particles = []
        self.sprite_emit_acc = 0.0
        self.sprite_prev_x = None   # last-tick position for velocity derivation
        self.sprite_prev_y = None
        # Once-per-bullet dodge guard (see systems.py bullet-dodge trigger):
        # id() of every live enemy projectile this figure has already
        # dodged, so the same incoming bullet can never re-trigger a second
        # dodge (blink or physical) while it's still nearby/slow-moving —
        # only fixes repeat-dodging one bullet; every other bullet still
        # dodges normally. Pruned each tick against the current enemy_projs
        # snapshot so it never grows past what's actually still alive.
        self.dodged_proj_ids = set()
                                          # awaiting CombatSystem drain
        # Manual ultimate hotkey (Ctrl+1 / Ctrl+2, see systems.InputSystem /
        # combat.try_fire_manual_ultimate). True while a force-trigger
        # request is pending; consumed the instant the figure is free.
        self.manual_ult_queued = False

    def reset(self):
        self.__init__()

    @property
    def busy(self):
        """True while any attack/dodge state is active (movement is suspended)."""
        return (self.dashing or self.rebounding or self.slashing
                or self.dodge_dashing)


class Personality:
    """Per-figure RNG and battle temperament, seeded from OS entropy so figures
    are independent across processes regardless of launch timing."""

    __slots__ = ("rng", "aggression", "wander_strength", "wander_angle",
                 "wander_drift", "wander_sign", "battle_shoot_interval",
                 "shoot_tick", "daze_ticks", "retreat_ticks", "hit_power",
                 "hp", "max_hp",
                 "knockback_count", "immunity_hits",
                 "ultimate_ticks", "teleport_ticks",
                 "sword_ult_fired_thresholds",
                 "trigger_state")

    def __init__(self, mode_key="runner"):
        self.rng = random.Random(int.from_bytes(os.urandom(8), "little"))
        r = self.rng
        self.aggression = r.uniform(0.35, 1.0)
        self.wander_strength = r.uniform(0.4, 1.2)
        self.wander_angle = r.uniform(0, 2 * math.pi)
        self.wander_drift = r.uniform(0.04, 0.12)
        self.wander_sign = r.choice([-1, 1])
        self.battle_shoot_interval = r.randint(*config.SHOOT_INTERVAL_RANGE)
        self.shoot_tick = r.randint(0, 30)
        self.daze_ticks = 0
        self.retreat_ticks = 0
        self.hit_power = config.HIT_POWER_BASE
        _mhp = config.MODE_CONFIGS.get(mode_key, {}).get("max_hp", 30)
        self.max_hp = _mhp
        self.hp = _mhp
        self.knockback_count = 0
        self.immunity_hits = 0
        self.ultimate_ticks = 0   # ticks remaining in runner ultimate (0 = inactive)
        self.teleport_ticks = 0   # ticks until next survival teleport (0 = ready)
        self.sword_ult_fired_thresholds = set()  # set of thresholds (fractions) already fired
        self.trigger_state = {}  # per-action bookkeeping for ai.evaluate_activation_triggers




