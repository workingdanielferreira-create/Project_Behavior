"""
Unique Abilities (FX Studio: the "Unique Abilities" section).

A character can carry ONE unique ability: the core mechanism it is built
around.  FX Studio saves it in <name>.fxkit.json as

    "unique_ability": {
        "type": "none" | "mirror_legion" | "berserker" | "phase_shift"
                | "ricochet" | "riposte" | "dual_form" | "summoner" | "aegis"
                | "terraform" | "rewind_bullets" | "phantom_swap"
                | "domain_expansion" | "fusion",
        "mirror_legion": {...}, "berserker": {...}, ...   # each one's settings
    }

Only the block named by `type` is used (the others are kept so switching
back in the Studio doesn't lose them).  A hand-written pb_character JSON can
carry the same block at its top level.  Mirror of tools/fx/studio/fxkit.js
UNIQUE_DEFAULTS / normalizeUnique.

    mirror_legion    split into full copies of the fighter (real Figures on its
                     side running its ticked actions) on a trigger
    berserker        attack + movement speed (every state) rise as HP falls
    phase_shift      a hit is nullified and the fighter teleports away
    ricochet         its bullets and moving FX bounce off walls / fighters / FX
    riposte          a hit inside the counter stance (or by chance) is
                     cancelled and answered with a counter-strike
    dual_form        Transformations: 2-6 forms (actions, palette, stats) cycled
                     in order on a trigger; each form pair has its own
                     transition (an action + a borrowed FX) played before the
                     new form takes over
    summoner         turrets / totems / familiars: real fighters on its side
                     (targetable) that are not copies of it
    aegis            a regenerating shield in front of HP; breaking it sends a
                     shockwave that damages, knocks back and stuns enemies
    terraform        walls / pillars / pits that block shots and bodies and
                     shatter into shrapnel
    rewind_bullets   its shots fly back along their path after a delay / recall
    phantom_swap     swaps places with the enemy, a copy / construct or one of
                     its own shots; can turn shots in flight around
    domain_expansion a gauge fills, then a domain rewrites the fight's rules
    fusion           two fielded team-mates (both with Fusion, different
                     characters) fuse into a chosen character with summed stats

Hooks (all shared by Solo and Battle; Solo's enemy is the cursor):
    ai.apply_hp_damage / ai.battle_hit   intercept(), heals_instead(), absorb(),
                                         after_damage(), taken_mult()
    actions.note_landed / ProjectileSystem   note_landed()
    actions.py action starts             clone_allows()
    systems.CombatSystem                 tick() once per body step
    systems.MotionSystem                 holds_still(), push_out(), blink_free()
    timefx.plan                          speed_mult() / fx_speed_mult()
    systems.ProjectileSystem             proj_step(), proj_wants_figures(), proj_off_point()
    systems.CollisionSystem              proj_off_figure(), proj_ghost()
    fxkit.spawn / tick_inst / hit        fx_size_mult(), inst_step(), inst_off_figure()
    app.refresh_battle / fxkit._Host     out_mult()
    blink._reappear                      blink_free()
    combat.spawn_clone                   on_dodge()
    figure.Figure.draw                   draw(), draw_construct()
    app.Overlay._tick                    world_tick() (copies, constructs, fusion,
                                         swaps, shockwaves, domains, stuns)
"""

import math
import random

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QPen, QBrush, QPainter, QRadialGradient, QPolygonF

from . import config
from . import modes as _modes

TICK_MS = config.TICK_MS
TYPES = ("none", "mirror_legion", "berserker", "phase_shift", "ricochet", "riposte",
         "dual_form", "summoner", "aegis", "terraform", "rewind_bullets",
         "phantom_swap", "domain_expansion", "fusion")

DEFAULTS = {
    "mirror_legion": dict(
        trigger="hp_below",          # hp_below | hits_taken | timer | on_dodge
        hp_thresholds="70,50,30",    # % HP; each fires once per life
        every_hits=5, every_ms=10000,
        count=2, duration_ms=4000, cooldown_ms=6000,
        formation="around",          # around | at_self | corners | mirror
        spread_px=90.0, speed_pct=100.0, opacity_pct=60.0,
        clone_hp=20.0, damage_pct=50.0, max_alive=6,
        actions={}),                 # action name -> False = the copies never play it
    "berserker": dict(
        start_lost_pct=0.0, max_lost_pct=90.0, max_bonus_pct=500.0,
        curve="linear",              # linear | exponential | steps
        steps=5, damage_bonus_pct=0.0, damage_taken_pct=0.0,
        speed_fx=True, aura=True, aura_color="#ff2a2a"),
    "phase_shift": dict(
        trigger="every_hit",         # every_hit | min_damage | hp_below | chance
        min_damage=5.0, hp_below_pct=50.0, chance_pct=50.0,
        charges=3, recharge_ms=8000,
        destinations=dict(behind_attacker=True, random=True, far_corner=False,
                          spawn=False, mirror=False, fixed=False),
        random_min_px=120.0, random_max_px=260.0, behind_px=70.0,
        fixed_x_pct=50.0, fixed_y_pct=50.0, invuln_ms=300, show_charges=True),
    "ricochet": dict(
        bounces=3, walls=True, characters=True, fx=True, fx_contact_px=18.0,
        keep_speed_pct=100.0, keep_damage_pct=100.0,
        angle="reflect",             # reflect | seek | random
        random_deg=25.0, split=0, split_deg=20.0, sparks=True),
    "riposte": dict(
        mode="stance",               # stance | chance | both
        stance_every_ms=3000, stance_ms=600, chance_pct=25.0,
        counter_mult_pct=150.0, base_damage=5.0,
        counter="strike",            # strike | blink_strike
        knockback_px=60.0, cooldown_ms=1500, invuln_ms=250, color="#ffd34a"),
    "dual_form": dict(               # shown as "Transformations" (key kept for old files)
        trigger="gauge",             # gauge | timer | hp_below | combo
        gauge_hits=12,               # gauge: hits landed + taken that fill it
        every_ms=8000, hp_thresholds="60,30", combo_hits=4, combo_window_ms=1500,
        cooldown_ms=2000,
        buff_ms=2000, buff_speed_pct=30.0, buff_damage_pct=30.0,
        transition_fx=True, show_gauge=True,
        forms=2,                     # how many forms (2-6), cycled a -> b -> ... -> a
        form_a=dict(name="Form A", speed_pct=100.0, damage_pct=100.0, taken_pct=100.0,
                    palette=False, body="#f2f4f6", accent="#3fb0ea", aura=False, aura_color="#3fb0ea",
                    fx="", lasts_ms=0.0),
        form_b=dict(name="Form B", speed_pct=120.0, damage_pct=130.0, taken_pct=120.0,
                    palette=True, body="#ffe0e0", accent="#ff3a3a", aura=True, aura_color="#ff3a3a",
                    fx="", lasts_ms=0.0),
        form_c=dict(name="Form C", speed_pct=100.0, damage_pct=100.0, taken_pct=100.0,
                    palette=True, body="#e0ffe6", accent="#3aff7a", aura=True, aura_color="#3aff7a",
                    fx="", lasts_ms=0.0),
        form_d=dict(name="Form D", speed_pct=100.0, damage_pct=100.0, taken_pct=100.0,
                    palette=True, body="#fff4d6", accent="#ffc23a", aura=True, aura_color="#ffc23a",
                    fx="", lasts_ms=0.0),
        form_e=dict(name="Form E", speed_pct=100.0, damage_pct=100.0, taken_pct=100.0,
                    palette=True, body="#efe0ff", accent="#a03aff", aura=True, aura_color="#a03aff",
                    fx="", lasts_ms=0.0),
        form_f=dict(name="Form F", speed_pct=100.0, damage_pct=100.0, taken_pct=100.0,
                    palette=True, body="#e0f9ff", accent="#3ae0ff", aura=True, aura_color="#3ae0ff",
                    fx="", lasts_ms=0.0),
        # "a>b" -> the transition played when leaving form a for form b:
        # action = an action of the character ("" = none; the form changes
        # when it ends; only its animation shows, its own FX stay off), fx =
        # "fx:<effect id>" | "group:<group id>" borrowed from an action and
        # played while it lasts, alongside the FX built on the transition's
        # own slot "@transform:a>b" (one pass of their timing without one).
        # time = Time control while it plays (fxkit.normalize_time fields, on
        # the action's frames; duration_ms = how long without an action).
        transitions={x + ">" + y: dict(action="", fx="", time=dict(
                         enabled=False, start_frame=0, end_frame=-1, scope="enemy_fighters",
                         speed=0.0, keys=[], logic="any", conditions=[], duration_ms=1000.0))
                     for x in "abcdef" for y in "abcdef" if x != y},
        # Each form: fx = its Character FX while it is in that form ("fx:<id>"
        # | "group:<id>", plus the FX built on "@form:<letter>"), replacing the
        # character's own; lasts_ms > 0 = it goes back to the first form
        # (through that transition) once the form has lasted that long.
        actions={}),                 # action name -> forms that play it, e.g. "ac"
                                     # (missing / "both" = every form, "" = none)
    "summoner": dict(
        construct="turret",          # turret | totem_heal | totem_shield | familiar
        trigger="timer",             # timer | hp_below | hits_taken
        every_ms=6000, hp_thresholds="75,50,25", every_hits=6,
        count=1, max_alive=3, life_ms=12000, construct_hp=15.0,
        placement="around",          # around | between | near_enemy | random
        spread_px=80.0,
        fire_ms=900, shot_damage=2.0, shot_speed_pct=100.0, range_px=500.0,
        heal_per_s=2.0, shield_pct=40.0, aura_px=220.0,
        bite_damage=3.0, bite_ms=700, chase_speed_pct=120.0,
        size_px=14.0, color="#7cf3ff"),
    "aegis": dict(
        shield_hp=30.0, regen_delay_ms=3000, regen_per_s=8.0,
        blocks=dict(projectiles=True, fx=True, melee=True),
        wave_px=180.0, wave_damage=4.0, wave_knockback_px=120.0, stun_ms=900,
        show_bar=True, color="#6fd0ff"),
    "terraform": dict(
        structure="pillar",          # wall | pillar | pit
        trigger="timer",             # timer | on_hit | enemy_near
        every_ms=5000, near_px=200.0, cooldown_ms=2000,
        max_alive=3, life_ms=10000, struct_hp=20.0,
        placement="between",         # between | front | around | near_enemy | random
        distance_px=110.0, size_px=26.0, wall_len_px=120.0,
        blocks_own=False,
        shatter=True, shrapnel=6, shrapnel_damage=2.0,
        color="#c9a46a"),
    "rewind_bullets": dict(
        trigger="delay",             # delay | recall
        delay_ms=700, recall_every_ms=2500,
        return_speed_pct=120.0, return_damage_pct=100.0,
        pass_fx=True, fx_too=True, tint=True, color="#b48cff"),
    "phantom_swap": dict(
        trigger="cooldown",          # cooldown | on_hit | chance
        cooldown_ms=4000, chance_pct=30.0, uses=0,
        targets=dict(enemy=True, clone=True, own_shot=False),
        reverse_enemy_shots=True, reverse_px=160.0, reaim_own_shots=True,
        invuln_ms=250, swap_fx=True, color="#e07bff"),
    "domain_expansion": dict(
        fill="hits_landed",          # hits_landed | damage_taken | timer | hp_below
        fill_hits=15, fill_damage=30.0, fill_ms=20000, hp_below_pct=40.0,
        duration_ms=6000, cooldown_ms=4000,
        rules=dict(enemy_shots_off=True, guaranteed_hits=False, gravity=False,
                   huge_fx=False, slow_enemy=False, heal_on_damage=False, blink_no_cd=False),
        gravity_mode="pull",         # pull | push
        gravity_to="owner",          # owner | centre
        gravity_px=2.5, fx_size_pct=180.0, slow_pct=50.0,
        tint=True, tint_color="#5a1aff", tint_pct=18.0, show_gauge=True),
    "fusion": dict(
        result="",                   # character the fused fighter plays as ("" = this one)
        conds=dict(hp_below=True, close=True, field_time=False, hits_landed=False),
        hp_below_pct=50.0, close_px=160.0, field_ms=10000, hits=10,
        ending="timed",              # timed | permanent
        duration_ms=15000, cooldown_ms=10000,
        aura=True, aura_color="#ffffff"),
}

_LIMITS = {
    "count": (1, 8), "max_alive": (1, 16), "every_hits": (1, 99), "bounces": (0, 20), "split": (0, 4),
    "charges": (0, 99), "steps": (1, 20), "max_bonus_pct": (0, 700),
    "gauge_hits": (1, 999), "combo_hits": (1, 99), "shrapnel": (0, 24), "uses": (0, 99),
    "fill_hits": (1, 999), "hits": (1, 999), "forms": (2, 6),
}
DF_FORMS = "abcdef"      # Transformations form letters (form_a .. form_f)


# ------------------------------------------------------------ config
def _coerce(dv, v):
    """`v` read as the type of its default `dv` (bool / int / float / str /
    dict).  A dict default is filled key by key; an empty one is an open
    table (Mirror Legion / Dual Form `actions`) kept as name -> bool / str."""
    try:
        if isinstance(dv, bool):
            return bool(v)
        if isinstance(dv, int):
            return int(round(float(v)))
        if isinstance(dv, float):
            return float(v)
        if isinstance(dv, list):
            return list(v) if isinstance(v, list) else list(dv)
        if isinstance(dv, dict) and not dv:
            if not isinstance(v, dict):
                return {}
            return {str(kk): (vv if isinstance(vv, bool) else str(vv)) for kk, vv in v.items()}
        if isinstance(dv, dict):
            v = v if isinstance(v, dict) else {}
            return {kk: _coerce(dd, v.get(kk, dd)) for kk, dd in dv.items()}
        return str(v)
    except (TypeError, ValueError):
        return dv


def _norm(kind, raw):
    """Fill one ability's settings from its defaults, keeping each value's
    type (bool / int / float / str / dict)."""
    out = {}
    raw = raw if isinstance(raw, dict) else {}
    for k, dv in DEFAULTS[kind].items():
        v = _coerce(dv, raw.get(k, dv))
        if k in _LIMITS and not isinstance(v, (bool, dict, str)):
            lo, hi = _LIMITS[k]
            v = max(lo, min(hi, v))
        out[k] = v
    return out


def cfg(fig):
    """(type, settings) of this figure's unique ability, or None.  Cached on
    the mode instance like the other generic *_cfg parsers."""
    mode = getattr(fig, "mode", None)
    if mode is None or is_clone(fig):
        return None       # a copy / construct carries no ability of its own
    if hasattr(mode, "_ua_cfg"):
        return mode._ua_cfg
    char = getattr(mode, "character", None) or {}
    raw = (char.get("_fxkit") or {}).get("unique_ability") or char.get("unique_ability")
    res = None
    if isinstance(raw, dict):
        kind = raw.get("type")
        if kind in DEFAULTS:
            res = (kind, _norm(kind, raw.get(kind)))
    mode._ua_cfg = res
    return res


def _of(fig, kind):
    c = cfg(fig) if fig is not None else None
    return c[1] if c is not None and c[0] == kind else None


def _ticks(ms):
    return max(1, int(round(float(ms) / TICK_MS)))


def _rgb(hexs, fallback=(255, 255, 255)):
    s = str(hexs or "").lstrip("#")
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except (ValueError, IndexError):
        return fallback


def _thresholds(text):
    out = []
    for part in str(text).replace(";", ",").split(","):
        try:
            out.append(float(part))
        except ValueError:
            continue
    return out


def _hp_pct(fig):
    p = fig.personality
    return 100.0 * p.hp / p.max_hp if p.max_hp else 100.0


# ------------------------------------------------------------ per-figure state
class UAState:
    __slots__ = ("shots", "sparks", "legion_fired", "legion_cd", "legion_timer", "hits",
                 "charges", "recharge", "spawn", "stance_left", "stance_timer",
                 "riposte_cd", "flash", "flash_rgb",
                 "clones", "pending", "clone_of", "clone_left", "clone_P",
                 # every figure
                 "t", "landed", "stun_left",
                 # Dual Form
                 "form", "df_gauge", "df_timer", "df_cd", "df_fired", "df_combo", "df_buff",
                 "df_lut0", "df_init", "df_want", "df_pending", "df_tr_act", "df_act",
                 "df_act_started", "df_wait", "df_fx", "df_fx_once", "df_fx_seq", "df_pair",
                 "df_pair_act", "df_left", "df_target", "df_form_seq", "df_time_new",
                 # Summoner (owner) / construct (the summoned figure)
                 "sm_timer", "sm_fired", "sm_hits", "construct", "con_cd", "con_aim",
                 # Aegis
                 "shield", "shield_idle", "waves",
                 # Terraform
                 "structs", "tf_timer", "tf_cd",
                 # Rewind Bullets
                 "rw_timer",
                 # Phantom Swap
                 "sw_cd", "sw_used", "swaps",
                 # Domain Expansion
                 "dm_gauge", "dm_left", "dm_cd", "dm_hp_fired",
                 # Fusion
                 "fu_cd", "fu_together", "fu_l0", "fu_parents", "fu_left", "fu_P",
                 "fu_mode", "fu_dmg")

    def __init__(self, fig):
        self.shots = []          # projectiles queued for this figure's side
        self.sparks = []
        self.legion_fired = set()
        self.legion_cd = 0
        self.legion_timer = 0
        self.hits = 0
        self.charges = None      # phase shift charges left (set on first use)
        self.recharge = 0
        self.spawn = (fig.transform.x, fig.transform.y)
        self.stance_left = 0
        self.stance_timer = 0
        self.riposte_cd = 0
        self.flash = 0
        self.flash_rgb = (255, 255, 255)
        self.clones = []         # owner: its live Mirror Legion copies / constructs
        self.pending = []        # owner: copies waiting to join its side (world_tick)
        self.clone_of = None     # copy / construct: the fighter it belongs to
        self.clone_left = 0      # copy / construct: ticks until it dissolves
        self.clone_P = None      # copy / construct: the owner's settings
        self.t = 0               # body steps taken (tick())
        self.landed = 0          # hits landed (note_landed)
        self.stun_left = 0       # Aegis shockwave stun (world_tick counts it down)
        self.form = "a"
        self.df_gauge = 0.0
        self.df_timer = 0
        self.df_cd = 0
        self.df_fired = set()
        self.df_combo = []       # tick (self.t) of each recent landed hit
        self.df_buff = 0
        self.df_lut0 = None      # the palette it had before any form palette
        self.df_init = False
        self.df_want = False     # a trigger fired: start the next transition (_df_tick)
        self.df_pending = None   # form letter it is transforming into (None = settled)
        self.df_tr_act = ""      # the transition's action ("" = none)
        self.df_act = None       # that action while it plays
        self.df_act_started = 0
        self.df_wait = 0         # ticks left to get the action started
        self.df_fx = ""          # the transition's borrowed FX (fxkit FxDriver)
        self.df_fx_once = False  # no action: the FX plays one pass on its own
        self.df_fx_seq = 0       # bumped per transition (restarts the FX lanes)
        self.df_pair = ""        # the transition playing its FX ("a>b")
        self.df_pair_act = ""    # its action (the FX's timing)
        self.df_left = 0         # ticks the current form has left (0 = no limit)
        self.df_target = None    # next transition goes here instead of the next form
        self.df_form_seq = 0     # bumped per form change (restarts the form FX)
        self.df_time_new = False # a transition without an action: start its Time control (timefx)
        self.sm_timer = 0
        self.sm_fired = set()
        self.sm_hits = 0
        self.construct = None    # construct: "turret" | "totem_heal" | "totem_shield" | "familiar"
        self.con_cd = 0
        self.con_aim = 0.0
        self.shield = None       # Aegis shield HP (None = not set up yet)
        self.shield_idle = 0     # ticks since the last hit
        self.waves = []          # Aegis break shockwaves for world_tick to deliver
        self.structs = []        # Terraform structures it owns
        self.tf_timer = 0
        self.tf_cd = 0
        self.rw_timer = 0
        self.sw_cd = 0
        self.sw_used = 0
        self.swaps = 0           # Phantom Swaps queued for world_tick
        self.dm_gauge = 0.0
        self.dm_left = 0
        self.dm_cd = 0
        self.dm_hp_fired = False
        self.fu_cd = 0
        self.fu_together = 0     # ticks fielded next to a fusion partner
        self.fu_l0 = 0           # `landed` when that started
        self.fu_parents = None   # fused fighter: (a, b) it was made from
        self.fu_left = None      # fused fighter: ticks until it splits (None = permanent)
        self.fu_P = None
        self.fu_mode = None
        self.fu_dmg = 1.0


def is_clone(fig):
    """A Mirror Legion copy or a Summoner construct: never a fighter slot,
    never a loss when it falls, carries no ability of its own."""
    st = getattr(fig, "ua", None)
    return st is not None and st.clone_of is not None


def is_construct(fig):
    st = getattr(fig, "ua", None)
    return st is not None and st.construct is not None


def state(fig):
    st = getattr(fig, "ua", None)
    if st is None:
        st = UAState(fig)
        fig.ua = st
    return st


# ------------------------------------------------------------ helpers
def _enemy_points(fig, world):
    """Where this figure's enemies are: the partner snapshot when the
    world is bound to its side, the other sides' fighters when called from
    the world-level hit delivery, the cursor in Solo."""
    if world is None:
        return []
    if getattr(world, "battle_mode", False):
        if fig in (world.figures or []) and world.partner_figures:
            return [(e[0], e[1]) for e in world.partner_figures]
        pts = []
        for s in getattr(world, "sides", ()) or ():
            if fig in s.figures:
                continue
            pts.extend((f.x, f.y) for f in s.figures)
        if pts:
            return pts
    return [tuple(world.cursor)]


def _nearest(pts, x, y):
    if not pts:
        return None
    return min(pts, key=lambda q: (q[0] - x) ** 2 + (q[1] - y) ** 2)


def _clamp_xy(fig, x, y, margin=24.0):
    return (max(margin, min(fig.screen_w - margin, x)),
            max(margin, min(fig.screen_h - margin, y)))


def _burst(dst, x, y, rgb, n=10, spd=(1.0, 4.0), rng=random):
    r, g, b = rgb
    for _ in range(n):
        a = rng.uniform(0.0, 2.0 * math.pi)
        s = rng.uniform(*spd)
        dst.append([x, y, math.cos(a) * s, math.sin(a) * s, 0, r, g, b])


def _warp(fig, nx, ny):
    """Move the figure, cancel any knockback slide, queue the blink crackle."""
    t, m = fig.transform, fig.motion
    ox, oy = t.x, t.y
    nx, ny = _clamp_xy(fig, nx, ny)
    t.x, t.y = nx, ny
    m.bouncing = False
    m.bounce_vx = m.bounce_vy = 0.0
    fig.combat.blink_fx_pending.append((ox, oy, nx, ny))


def _protect(fig, world, ms):
    """Nullified hit: invincible for `ms` and no knockback this tick."""
    if world is None:
        return
    p = fig.personality
    p.dmg_immune_until = max(p.dmg_immune_until, world.global_tick + max(2, _ticks(ms)))
    p.dmg_hit_tick = world.global_tick - 2


def _side_of(world, fig):
    for i, s in enumerate(world.sides):
        if fig in s.figures:
            return i
    return None


def _set_lut(fig, lut):
    """Palette swap: the body LUT and the trail LUT together (cycle_mode rule)."""
    fig.lut = lut
    fig.trail.lut = lut


def _shot(x, y, tx, ty, rgb, damage, owner, speed=None, max_age=None, trail=None):
    """A plain bullet from (x, y) at (tx, ty) for the bound side."""
    from . import combat
    spd = float(speed or config.PROJ_SPEED)
    dx, dy = tx - x, ty - y
    d = math.hypot(dx, dy) or 1.0
    pr = combat.Projectile(x, y, dx / d * spd, dy / d * spd, rgb, trail or config.PROJ_TRAIL_LEN)
    pr.damage = float(damage)
    pr.owner = owner
    if max_age is not None:
        pr.max_age = max(2, int(max_age))
    return pr


# ------------------------------------------------------------ per tick
def tick(fig, world):
    """CombatSystem hook, once per body step (world bound to fig's side)."""
    c = cfg(fig)
    st = getattr(fig, "ua", None)
    if c is None and st is None:
        return
    st = state(fig)
    st.t += 1
    if st.shots:
        world.projectiles.extend(st.shots)
        st.shots = []
    if st.sparks:
        world.sparks.extend(st.sparks)
        st.sparks = []
    if st.flash > 0:
        st.flash -= 1
    if st.construct is not None:
        _construct_tick(fig, world, st)
        return
    if c is None:
        return
    kind, P = c
    if kind == "mirror_legion":
        if st.legion_cd > 0:
            st.legion_cd -= 1
        if P["trigger"] == "timer":
            st.legion_timer += 1
            if st.legion_timer >= _ticks(P["every_ms"]) and st.legion_cd <= 0:
                st.legion_timer = 0
                _spawn_legion(fig, world, P)
    elif kind == "phase_shift":
        if st.charges is None:
            st.charges = P["charges"]
        if P["charges"] > 0 and P["recharge_ms"] > 0 and st.charges < P["charges"]:
            st.recharge += 1
            if st.recharge >= _ticks(P["recharge_ms"]):
                st.recharge = 0
                st.charges += 1
    elif kind == "riposte":
        if st.riposte_cd > 0:
            st.riposte_cd -= 1
        if st.stance_left > 0:
            st.stance_left -= 1
        elif P["mode"] in ("stance", "both"):
            st.stance_timer += 1
            if st.stance_timer >= _ticks(P["stance_every_ms"]) and st.riposte_cd <= 0:
                st.stance_timer = 0
                st.stance_left = _ticks(P["stance_ms"])
    elif kind == "dual_form":
        _df_tick(fig, world, st, P)
    elif kind == "summoner":
        if P["trigger"] == "timer":
            st.sm_timer += 1
            if st.sm_timer >= _ticks(P["every_ms"]):
                st.sm_timer = 0
                _summon(fig, world, P)
    elif kind == "aegis":
        _aegis_tick(fig, st, P)
    elif kind == "terraform":
        _tf_tick(fig, world, st, P)
    elif kind == "rewind_bullets":
        if P["trigger"] == "recall":
            st.rw_timer += 1
            if st.rw_timer >= _ticks(P["recall_every_ms"]):
                st.rw_timer = 0
                _recall(fig, world, P)
    elif kind == "phantom_swap":
        if st.sw_cd > 0:
            st.sw_cd -= 1
        elif P["trigger"] == "cooldown":
            _queue_swap(fig, P)
    elif kind == "domain_expansion":
        _dm_tick(fig, world, st, P)


# ------------------------------------------------------------ being hit
def intercept(fig, world, amount):
    """Called for every incoming hit before it lands (after the normal
    blocks).  True = the hit is nullified (Phase Shift / Riposte)."""
    c = cfg(fig)
    if c is None:
        return False
    # Domain Expansion "Guaranteed hits": inside an enemy domain nothing
    # phases out of or counters a hit.
    if _enemy_rule(fig, world, "guaranteed_hits"):
        return False
    kind, P = c
    if kind == "phase_shift":
        return _phase_shift(fig, world, amount, P)
    if kind == "riposte":
        return _riposte(fig, world, amount, P)
    return False


def heals_instead(fig, amount):
    """Domain Expansion "Damage heals": while its own domain is up, a hit on
    the owner restores that much HP instead.  True = handled (no damage)."""
    if not _own_rule(fig, "heal_on_damage"):
        return False
    p = fig.personality
    p.hp = min(p.max_hp, p.hp + amount)
    st = state(fig)
    st.flash = 8
    st.flash_rgb = (90, 255, 140)
    return True


def absorb(fig, world, amount, kind="melee"):
    """Aegis: the shield takes the hit first.  Returns what is left for HP.
    `kind` = projectile | fx | melee (the hit's source, per the Blocks
    ticks)."""
    P = _of(fig, "aegis")
    if P is None or amount <= 0:
        return amount
    st = state(fig)
    st.shield_idle = 0
    if st.shield is None:
        st.shield = P["shield_hp"]
    if st.shield <= 0 or not P["blocks"].get(kind, True):
        return amount
    take = min(st.shield, amount)
    st.shield -= take
    st.flash = 6
    st.flash_rgb = _rgb(P["color"], (111, 208, 255))
    if st.shield <= 1e-6:
        st.shield = 0.0
        st.waves.append((fig.transform.x, fig.transform.y))
        _burst(st.sparks, fig.transform.x, fig.transform.y, st.flash_rgb, n=24, spd=(2.0, 7.0),
               rng=fig.personality.rng)
        st.flash = 14
    return amount - take


def after_damage(fig, world, amount):
    """Called after a hit took HP (the figure is still alive)."""
    c = cfg(fig)
    if c is None:
        return
    kind, P = c
    st = state(fig)
    st.hits += 1
    if kind == "mirror_legion":
        if P["trigger"] == "hp_below":
            hp_pct = _hp_pct(fig)
            for th in _thresholds(P["hp_thresholds"]):
                if th not in st.legion_fired and hp_pct <= th:
                    st.legion_fired.add(th)
                    _spawn_legion(fig, world, P)
        elif P["trigger"] == "hits_taken":
            if st.hits >= P["every_hits"] and st.legion_cd <= 0:
                st.hits = 0
                _spawn_legion(fig, world, P)
    elif kind == "dual_form":
        if P["trigger"] == "gauge":
            _df_fill(fig, world, st, P)
        elif P["trigger"] == "hp_below":
            hp_pct = _hp_pct(fig)
            for th in _thresholds(P["hp_thresholds"]):
                if th not in st.df_fired and hp_pct <= th:
                    st.df_fired.add(th)
                    st.df_want = True
                    break
    elif kind == "summoner":
        if P["trigger"] == "hp_below":
            hp_pct = _hp_pct(fig)
            for th in _thresholds(P["hp_thresholds"]):
                if th not in st.sm_fired and hp_pct <= th:
                    st.sm_fired.add(th)
                    _summon(fig, world, P)
        elif P["trigger"] == "hits_taken":
            st.sm_hits += 1
            if st.sm_hits >= P["every_hits"]:
                st.sm_hits = 0
                _summon(fig, world, P)
    elif kind == "terraform":
        if P["trigger"] == "on_hit" and st.tf_cd <= 0:
            _raise_struct(fig, world, st, P)
    elif kind == "phantom_swap":
        if st.sw_cd <= 0:
            if P["trigger"] == "on_hit" or (
                    P["trigger"] == "chance"
                    and fig.personality.rng.uniform(0, 100) < P["chance_pct"]):
                _queue_swap(fig, P)
    elif kind == "domain_expansion":
        if P["fill"] == "damage_taken":
            _dm_fill(fig, st, P, 100.0 * amount / max(0.01, P["fill_damage"]))


def note_landed(fig):
    """One of this fighter's hits connected (melee, FX Studio hit, bullet)."""
    if fig is None:
        return
    st = getattr(fig, "ua", None)
    if st is not None and st.construct is not None:
        return
    c = cfg(fig)
    if c is None:
        return
    st = state(fig)
    st.landed += 1
    kind, P = c
    if kind == "dual_form":
        if P["trigger"] == "gauge":
            _df_fill(fig, None, st, P)
        elif P["trigger"] == "combo":
            win = _ticks(P["combo_window_ms"])
            st.df_combo = [t for t in st.df_combo if st.t - t <= win] + [st.t]
            if len(st.df_combo) >= P["combo_hits"] and st.df_cd <= 0 and st.df_pending is None:
                st.df_combo = []
                st.df_want = True
    elif kind == "domain_expansion" and P["fill"] == "hits_landed":
        _dm_fill(fig, st, P, 100.0 / max(1, P["fill_hits"]))


def taken_mult(fig):
    """Incoming damage multiplier: Berserker weakness, the Dual Form's
    damage taken, a Summoner's shield totem nearby."""
    k = 1.0
    c = cfg(fig)
    if c is None:
        return k
    kind, P = c
    if kind == "berserker" and P["damage_taken_pct"] != 0:
        k *= max(0.0, 1.0 + P["damage_taken_pct"] / 100.0 * _rage(fig, P))
    elif kind == "dual_form":
        k *= max(0.0, _form(fig, P)["taken_pct"] / 100.0)
    elif kind == "summoner" and P["construct"] == "totem_shield":
        st = getattr(fig, "ua", None)
        if st is not None:
            r2 = P["aura_px"] ** 2
            for t in st.clones:
                if (t.personality.hp > 0 and is_construct(t)
                        and (t.x - fig.x) ** 2 + (t.y - fig.y) ** 2 <= r2):
                    k *= max(0.0, 1.0 - P["shield_pct"] / 100.0)
                    break
    return k


def on_dodge(fig):
    """combat.spawn_clone hook: Mirror Legion with the on_dodge trigger
    spawns its legion instead.  True when it handled the dodge."""
    P = _of(fig, "mirror_legion")
    if P is None or P["trigger"] != "on_dodge":
        return False
    if state(fig).legion_cd <= 0:
        _spawn_legion(fig, None, P)
    return True


# ------------------------------------------------------------ Mirror Legion
def _spawn_legion(fig, world, P):
    """Queue P["count"] copies of `fig`: real Figures of the same character
    (its actions, FX, movement and AI), joined to its side by world_tick."""
    from .figure import Figure
    st = state(fig)
    st.legion_cd = _ticks(P["cooldown_ms"])
    st.clones = [c for c in st.clones if c.personality.hp > 0 and c.ua.clone_left > 0]
    room = P["max_alive"] - len(st.clones) - len(st.pending)
    n = min(P["count"], room)
    if n <= 0:
        return
    x, y = fig.transform.x, fig.transform.y
    rng = fig.personality.rng
    sp = P["spread_px"]
    pts = []
    if P["formation"] == "at_self":
        pts = [(x + rng.uniform(-12, 12), y + rng.uniform(-12, 12)) for _ in range(n)]
    elif P["formation"] == "corners":
        ins = 60.0
        cs = [(ins, ins), (fig.screen_w - ins, ins), (ins, fig.screen_h - ins),
              (fig.screen_w - ins, fig.screen_h - ins)]
        pts = [cs[i % 4] for i in range(n)]
    elif P["formation"] == "mirror":
        tgt = _nearest(_enemy_points(fig, world), x, y) if world is not None else None
        tx, ty = tgt if tgt else (x + 1.0, y)
        dx, dy = tx - x, ty - y
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        bx, by = tx + ux * sp, ty + uy * sp
        for i in range(n):
            off = (i - (n - 1) / 2.0) * 50.0
            pts.append((bx - uy * off, by + ux * off))
    else:   # around
        a0 = rng.uniform(0, 2 * math.pi)
        pts = [(x + math.cos(a0 + 2 * math.pi * i / n) * sp,
                y + math.sin(a0 + 2 * math.pi * i / n) * sp) for i in range(n)]
    k = P["speed_pct"] / 100.0
    whole = isinstance(fig.personality.max_hp, int)
    hp = max(1, int(round(P["clone_hp"]))) if whole else max(0.1, float(P["clone_hp"]))
    for i, (px, py) in enumerate(pts):
        px, py = _clamp_xy(fig, px, py)
        c = Figure(fig.mode, fig.render.bundle, fig.lut, fig.index + 1 + len(st.clones) + i,
                   fig.screen_w, fig.screen_h)
        c.transform.x, c.transform.y = px, py
        c.transform.facing_left = fig.transform.facing_left
        c.transform.init = True
        c.personality.max_hp = c.personality.hp = hp
        c.motion.speed *= k
        c.motion.follow_speed *= k
        cs_ = UAState(c)
        cs_.clone_of, cs_.clone_left, cs_.clone_P = fig, _ticks(P["duration_ms"]), P
        c.ua = cs_
        st.pending.append(c)
        fig.combat.blink_fx_pending.append((x, y, px, py))


def world_tick(world):
    """World level, once per tick before refresh_battle (so the snapshots
    already show the result).  Same in Solo and Battle:
      * copies / constructs whose time ran out, that died, or whose owner
        left the fight (a copy: or changed character) dissolve; queued ones
        join their owner's side
      * Fusion: team-mates fuse / a timed fusion splits
      * Phantom Swaps, Aegis shockwaves and stuns are delivered (they move
        or hurt the other side, so they go here like knockback does)
      * active domains: published as world.ua_domains, enemy shots fizzle,
        the gravity rule moves enemy fighters
      * structures: published as world.ua_structs for every side's pass."""
    dead = getattr(world, "_dead", ()) or ()
    for side in world.sides:
        figs = side.figures
        keep, changed = [], False
        for f in figs:
            st = getattr(f, "ua", None)
            if st is not None and st.clone_of is not None:
                o = st.clone_of
                st.clone_left -= 1
                gone = (st.clone_left <= 0 or f.personality.hp <= 0 or o not in figs or o in dead
                        or (st.construct is None and o.mode is not f.mode))
                if gone:
                    _burst(world.sparks, f.transform.x, f.transform.y,
                           _rgb(st.clone_P.get("color"), tuple(f.lut[200]))
                           if st.construct is not None else tuple(f.lut[200]), n=12)
                    for pr in side.projectiles:
                        if pr.owner is f:
                            pr.age = pr.max_age
                    if o.ua is not None and f in o.ua.clones:
                        o.ua.clones.remove(f)
                    changed = True
                    continue
            keep.append(f)
        for f in list(keep):
            st = getattr(f, "ua", None)
            if st is not None and st.pending:
                if f in dead:
                    st.pending = []
                    continue
                keep.extend(st.pending)
                st.clones.extend(st.pending)
                st.pending = []
                changed = True
        if changed:
            figs[:] = keep
    for f in world.all_figures():
        st = getattr(f, "ua", None)
        if st is not None and st.stun_left > 0:
            st.stun_left -= 1
    _fusion_world(world, dead)
    for si, side in enumerate(world.sides):
        for f in list(side.figures):
            st = getattr(f, "ua", None)
            if st is None:
                continue
            if st.swaps:
                n, st.swaps = st.swaps, 0
                if f not in dead:
                    for _ in range(n):
                        _do_swap(world, si, f)
            if st.waves:
                waves, st.waves = st.waves, []
                P = _of(f, "aegis")
                if P is not None:
                    for (x, y) in waves:
                        _shockwave(world, si, f, x, y, P)
    doms = []
    for si, side in enumerate(world.sides):
        for f in side.figures:
            P = _of(f, "domain_expansion")
            if P is not None and f.ua is not None and f.ua.dm_left > 0 and f not in dead:
                doms.append((si, f, P))
    world.ua_domains = doms
    for (si, f, P) in doms:
        _domain_world(world, si, f, P)
    structs = []
    for si, side in enumerate(world.sides):
        for f in side.figures:
            st = getattr(f, "ua", None)
            if st is not None and st.structs:
                structs.extend((s, si) for s in st.structs if s.hp > 0)
    world.ua_structs = structs


def clone_allows(fig, name):
    """actions.py gate: may this fighter start action `name`?  A Mirror
    Legion copy plays only its owner's ticked actions; a Transformations
    fighter plays only the actions of the form it is in (and the action of
    the transition it is going through)."""
    st = getattr(fig, "ua", None)
    if st is not None and st.clone_of is not None:
        return bool(((st.clone_P or {}).get("actions") or {}).get(name, True))
    P = _of(fig, "dual_form")
    if P is None:
        return True
    if st is not None and st.df_tr_act and st.df_pending is not None:
        if name == st.df_tr_act:
            return True
        # Waiting for the transition action to get its turn: no other
        # triggered action (ultimate, special, defend, ...) starts first.
        from . import actions
        if st.df_act is None and actions._kind(name) == "triggered":
            return False
    want = (P.get("actions") or {}).get(name, "both")
    if want == "both":
        return True
    return _df_cur(st, P) in want


def body_alpha(fig):
    """Sprite opacity 0..1 for a Mirror Legion copy, None for anyone else."""
    st = getattr(fig, "ua", None)
    if st is None or st.clone_of is None or st.construct is not None:
        return None
    return max(0.05, min(1.0, st.clone_P["opacity_pct"] / 100.0))


# ------------------------------------------------------------ Berserker
def _rage(fig, P):
    """0..1: how far into the rage curve the figure's lost HP is."""
    p = fig.personality
    if not p.max_hp:
        return 0.0
    lost = 100.0 * (1.0 - max(0.0, p.hp) / float(p.max_hp))
    lo, hi = P["start_lost_pct"], max(P["start_lost_pct"] + 0.01, P["max_lost_pct"])
    f = max(0.0, min(1.0, (lost - lo) / (hi - lo)))
    if P["curve"] == "exponential":
        f = f * f
    elif P["curve"] == "steps":
        n = max(1, P["steps"])
        f = math.floor(f * n + 1e-9) / n
    return f


def speed_mult(fig, world=None):
    """Body time scale (movement + attack speed, every state): Berserker
    rage, the Dual Form's speed (and its switch buff), an enemy domain's
    slow, and 0 while stunned by an Aegis shockwave (body stopped; its FX
    run on)."""
    st = getattr(fig, "ua", None)
    if st is not None and st.stun_left > 0:
        return 0.0
    k = 1.0
    c = cfg(fig)
    if c is not None:
        kind, P = c
        if kind == "berserker":
            k *= 1.0 + P["max_bonus_pct"] / 100.0 * _rage(fig, P)
        elif kind == "dual_form":
            k *= max(0.05, _form(fig, P)["speed_pct"] / 100.0)
            if st is not None and st.df_buff > 0:
                k *= 1.0 + P["buff_speed_pct"] / 100.0
    return k * _enemy_slow(fig, world)


def fx_speed_mult(fig, world=None):
    """Time scale of the figure's own FX / bullets (Berserker 'speed FX';
    an enemy domain's slow reaches its shots too)."""
    k = 1.0
    P = _of(fig, "berserker")
    if P is not None and P["speed_fx"]:
        k *= 1.0 + P["max_bonus_pct"] / 100.0 * _rage(fig, P)
    return k * _enemy_slow(fig, world)


def out_mult(fig):
    """Outgoing damage multiplier (Berserker damage bonus, the Dual Form's
    damage and switch buff, a fused fighter's summed damage; a Mirror Legion
    copy deals its owner's set % of the damage, a construct its own set
    damage)."""
    st = getattr(fig, "ua", None) if fig is not None else None
    if st is not None and st.clone_of is not None:
        if st.construct is not None:
            return 1.0
        return max(0.0, st.clone_P["damage_pct"] / 100.0)
    k = st.fu_dmg if st is not None and st.fu_parents is not None else 1.0
    c = cfg(fig) if fig is not None else None
    if c is None:
        return k
    kind, P = c
    if kind == "berserker" and P["damage_bonus_pct"] != 0:
        k *= max(0.0, 1.0 + P["damage_bonus_pct"] / 100.0 * _rage(fig, P))
    elif kind == "dual_form":
        k *= max(0.0, _form(fig, P)["damage_pct"] / 100.0)
        if st is not None and st.df_buff > 0:
            k *= 1.0 + P["buff_damage_pct"] / 100.0
    return k


# ------------------------------------------------------------ Phase Shift
def _phase_shift(fig, world, amount, P):
    st = state(fig)
    if st.charges is None:
        st.charges = P["charges"]
    if P["charges"] > 0 and st.charges <= 0:
        return False
    p = fig.personality
    trig = P["trigger"]
    if trig == "min_damage" and amount < P["min_damage"]:
        return False
    if trig == "hp_below" and (not p.max_hp or 100.0 * p.hp / p.max_hp > P["hp_below_pct"]):
        return False
    if trig == "chance" and p.rng.uniform(0, 100) >= P["chance_pct"]:
        return False
    dests = [k for k, on in P["destinations"].items() if on] or ["random"]
    pick = p.rng.choice(dests)
    x, y = fig.transform.x, fig.transform.y
    ex, ey = _nearest(_enemy_points(fig, world), x, y) or (x + 1.0, y)
    if pick == "behind_attacker":
        dx, dy = ex - x, ey - y
        d = math.hypot(dx, dy) or 1.0
        nx, ny = ex + dx / d * P["behind_px"], ey + dy / d * P["behind_px"]
    elif pick == "far_corner":
        ins = 40.0
        cs = [(ins, ins), (fig.screen_w - ins, ins), (ins, fig.screen_h - ins),
              (fig.screen_w - ins, fig.screen_h - ins)]
        nx, ny = max(cs, key=lambda q: (q[0] - ex) ** 2 + (q[1] - ey) ** 2)
    elif pick == "spawn":
        nx, ny = st.spawn
    elif pick == "mirror":
        nx, ny = 2 * ex - x, 2 * ey - y
    elif pick == "fixed":
        nx, ny = fig.screen_w * P["fixed_x_pct"] / 100.0, fig.screen_h * P["fixed_y_pct"] / 100.0
    else:   # random
        a = p.rng.uniform(0, 2 * math.pi)
        lo = P["random_min_px"]
        dist = p.rng.uniform(lo, max(lo, P["random_max_px"]))
        nx, ny = x + math.cos(a) * dist, y + math.sin(a) * dist
    _warp(fig, nx, ny)
    _protect(fig, world, P["invuln_ms"])
    if P["charges"] > 0:
        st.charges -= 1
    st.flash = 8
    st.flash_rgb = tuple(fig.lut[200])
    return True


# ------------------------------------------------------------ Riposte
def in_stance(fig):
    st = getattr(fig, "ua", None)
    return bool(st is not None and st.stance_left > 0 and _of(fig, "riposte") is not None)


def _riposte(fig, world, amount, P):
    from . import combat
    st = state(fig)
    if st.riposte_cd > 0:
        return False
    rng = fig.personality.rng
    ok = False
    if P["mode"] in ("stance", "both") and st.stance_left > 0:
        ok = True
    if not ok and P["mode"] in ("chance", "both") and rng.uniform(0, 100) < P["chance_pct"]:
        ok = True
    if not ok:
        return False
    st.stance_left = 0
    st.stance_timer = 0
    st.riposte_cd = _ticks(P["cooldown_ms"])
    _protect(fig, world, P["invuln_ms"])
    x, y = fig.transform.x, fig.transform.y
    ex, ey = _nearest(_enemy_points(fig, world), x, y) or (x + 1.0, y)
    if P["counter"] == "blink_strike":
        dx, dy = x - ex, y - ey
        d = math.hypot(dx, dy) or 1.0
        _warp(fig, ex + dx / d * 45.0, ey + dy / d * 45.0)
        x, y = fig.transform.x, fig.transform.y
    rgb = _rgb(P["color"], (255, 211, 74))
    dx, dy = ex - x, ey - y
    d = math.hypot(dx, dy) or 1.0
    spd = config.PROJ_SPEED * 1.6
    pr = combat.Projectile(x, y, dx / d * spd, dy / d * spd, rgb, config.BEAM_TRAIL_LEN)
    pr.style = "beam"
    pr.damage = max(P["base_damage"], float(amount) * P["counter_mult_pct"] / 100.0)
    pr.knockback_px = P["knockback_px"]
    pr.one_hit = True
    pr.owner = fig
    pr.max_age = max(6, int(d / spd) + 8)
    st.shots.append(pr)
    _burst(st.sparks, x, y, rgb, n=14, spd=(1.5, 5.0), rng=rng)
    st.flash = 12
    st.flash_rgb = rgb
    return True


# ------------------------------------------------------------ Ricochet
_RC_PRIMS_OFF = ("weapon", "ghost", "particles", "pulse")


def _reflect(vx, vy, nx, ny):
    dot = vx * nx + vy * ny
    if dot >= 0:            # already moving away from the surface
        return vx, vy
    return vx - 2 * dot * nx, vy - 2 * dot * ny


def _aim(P, vx, vy, x, y, targets, rng):
    """Apply the bounce angle style to an already reflected velocity."""
    spd = math.hypot(vx, vy)
    if P["angle"] == "seek" and targets:
        tx, ty = _nearest(targets, x, y)
        d = math.hypot(tx - x, ty - y)
        if d > 1.0:
            return (tx - x) / d * spd, (ty - y) / d * spd
    if P["angle"] == "random":
        a = math.atan2(vy, vx) + math.radians(rng.uniform(-P["random_deg"], P["random_deg"]))
        return math.cos(a) * spd, math.sin(a) * spd
    return vx, vy


def _proj_cfg(proj):
    rb = getattr(proj, "ua_rb", None)
    if rb is None:
        P = _of(getattr(proj, "owner", None), "ricochet")
        rb = P["bounces"] if P else 0
        proj.ua_rb = rb
        proj.ua_cd = 0
    if rb <= 0:
        return None
    return _of(proj.owner, "ricochet")


def _bounce_proj(proj, P, nx, ny, targets, rng):
    from . import combat
    vx, vy = _reflect(proj.vx, proj.vy, nx, ny)
    vx, vy = _aim(P, vx, vy, proj.x, proj.y, targets, rng)
    k = P["keep_speed_pct"] / 100.0
    proj.vx, proj.vy = vx * k, vy * k
    proj.damage = float(getattr(proj, "damage", 1.0)) * P["keep_damage_pct"] / 100.0
    proj.ua_rb -= 1
    proj.ua_cd = 3
    # A bounced shot gets a fresh life so it can reach its next surface.
    proj.age = 0
    st = state(proj.owner)
    if P["sparks"]:
        _burst(st.sparks, proj.x, proj.y, (proj.r, proj.g, proj.b), n=6, spd=(1.0, 3.5), rng=rng)
    for i in range(P["split"]):
        side = 1 if i % 2 == 0 else -1
        a = math.atan2(proj.vy, proj.vx) + math.radians(P["split_deg"] * (i // 2 + 1) * side)
        s = math.hypot(proj.vx, proj.vy)
        cp = combat.Projectile(proj.x, proj.y, math.cos(a) * s, math.sin(a) * s,
                               (proj.r, proj.g, proj.b), max(3, len(proj.trail)))
        for f in ("style", "damage", "pierce", "knockback_px", "owner", "no_knockback",
                  "max_age", "radius", "hit_r_sq", "one_hit"):
            setattr(cp, f, getattr(proj, f))
        cp.ua_rb = proj.ua_rb
        cp.ua_cd = 3
        st.shots.append(cp)


def _rc_proj_step(proj, world):
    """Ricochet, owner side, after the bullet moved: walls and
    enemy shots.  A bullet fired without an owner (older fire paths) belongs
    to its side's only fighter, the same fallback timefx.proj_steps uses."""
    if getattr(proj, "ua_rb", None) is None and proj.owner is None:
        figs = world.figures or []
        if len(figs) == 1 and _of(figs[0], "ricochet") is not None:
            proj.owner = figs[0]
    P = _proj_cfg(proj)
    if P is None:
        return
    if proj.ua_cd > 0:
        proj.ua_cd -= 1
        return
    rng = proj.owner.personality.rng
    targets = _enemy_points(proj.owner, world)
    if P["walls"]:
        sw, sh = world.screen_w, world.screen_h
        nx = 1.0 if proj.x < 0 else -1.0 if proj.x > sw else 0.0
        ny = 1.0 if proj.y < 0 else -1.0 if proj.y > sh else 0.0
        if nx or ny:
            proj.x = max(0.0, min(sw, proj.x))
            proj.y = max(0.0, min(sh, proj.y))
            n = math.hypot(nx, ny)
            _bounce_proj(proj, P, nx / n, ny / n, targets, rng)
            return
    if P["fx"]:
        cr = P["fx_contact_px"]
        for s in getattr(world, "enemy_shots", None) or ():
            if s.dead or s.threat:   # gun / ki bullets: threat-only
                continue
            dx, dy = proj.x - s.x, proj.y - s.y
            d = math.hypot(dx, dy)
            if d <= cr:
                if d < 0.01:
                    dx, dy, d = -proj.vx, -proj.vy, math.hypot(proj.vx, proj.vy) or 1.0
                nx, ny = dx / d, dy / d
                proj.x, proj.y = s.x + nx * (cr + 1), s.y + ny * (cr + 1)
                _bounce_proj(proj, P, nx, ny, targets, rng)
                return


def proj_wants_figures(proj):
    """True while this bullet bounces off fighters (the owner side then
    leaves it alive on contact; the struck side bounces it)."""
    P = _proj_cfg(proj)
    return bool(P and P["characters"])


def proj_off_point(proj, px, py, radius, world=None):
    """Bounce a bullet off a fighter / the cursor at (px, py).  True when it
    bounced (the caller must not destroy it)."""
    P = _proj_cfg(proj)
    if not (P and P["characters"]):
        return False
    dx, dy = proj.x - px, proj.y - py
    d = math.hypot(dx, dy)
    if d < 0.01:
        dx, dy, d = -proj.vx, -proj.vy, math.hypot(proj.vx, proj.vy) or 1.0
    nx, ny = dx / d, dy / d
    proj.x, proj.y = px + nx * (radius + 2), py + ny * (radius + 2)
    _bounce_proj(proj, P, nx, ny, None, proj.owner.personality.rng)
    return True


def proj_off_figure(proj, fx, fy, radius):
    """Struck-side hook (CollisionSystem): the bullet that just hit a
    fighter bounces off it instead of dying (sanctioned mutation of the
    source bullet through the snapshot's tuple[8])."""
    return proj_off_point(proj, fx, fy, radius)


def _inst_cfg(inst, host):
    fx = inst.fx
    if fx["prim"] in _RC_PRIMS_OFF:
        return None
    if not (inst.free or fx["motion"]["kind"] in ("travel", "homing", "zigzag")):
        return None
    if inst.ua_rb is None:
        P = _of(getattr(host, "fig", None), "ricochet")
        inst.ua_rb = P["bounces"] if P else 0
    if inst.ua_rb <= 0:
        return None
    return _of(host.fig, "ricochet")


def _bounce_inst(inst, host, P, nx, ny, targets):
    rng = host.fig.personality.rng
    vx, vy = _reflect(inst.vx, inst.vy, nx, ny)
    vx, vy = _aim(P, vx, vy, inst.x, inst.y, targets, rng)
    k = P["keep_speed_pct"] / 100.0
    inst.vx, inst.vy = vx * k, vy * k
    s = math.hypot(inst.vx, inst.vy)
    if s > 1e-6:
        inst.dir = [inst.vx / s, inst.vy / s]
    # zigzag: its side-to-side offset mirrors with the bounce
    inst.zx, inst.zy = _reflect(inst.zx, inst.zy, nx, ny)
    inst.ua_dm *= P["keep_damage_pct"] / 100.0
    inst.ua_rb -= 1
    inst.ua_cd = 3
    # Fresh life for the next leg (its hit window restarts too).
    inst.age = 0
    if P["sparks"] and getattr(host, "world", None) is not None:
        rgb = tuple(host.fig.lut[200])
        _burst(host.world.sparks, inst.x, inst.y, rgb, n=6, spd=(1.0, 3.5), rng=rng)


def _rc_inst_step(inst, host):
    """Ricochet, owner side, after the effect moved."""
    P = _inst_cfg(inst, host)
    if P is None:
        return
    if inst.ua_cd > 0:
        inst.ua_cd -= 1
        return
    fig = host.fig
    targets = [tuple(host.target)] if getattr(host, "target", None) else None
    if P["walls"]:
        sw, sh = fig.screen_w, fig.screen_h
        nx = 1.0 if inst.x < 0 else -1.0 if inst.x > sw else 0.0
        ny = 1.0 if inst.y < 0 else -1.0 if inst.y > sh else 0.0
        if nx or ny:
            inst.x = max(0.0, min(sw, inst.x))
            inst.y = max(0.0, min(sh, inst.y))
            n = math.hypot(nx, ny)
            _bounce_inst(inst, host, P, nx / n, ny / n, targets)
            return
    if P["fx"]:
        cr = P["fx_contact_px"]
        for s in getattr(host, "shots", None) or ():
            if s.dead or getattr(s, "threat", False):   # gun / ki bullets: threat-only
                continue
            dx, dy = inst.x - s.x, inst.y - s.y
            d = math.hypot(dx, dy)
            if d <= cr:
                if d < 0.01:
                    dx, dy, d = -inst.vx, -inst.vy, math.hypot(inst.vx, inst.vy) or 1.0
                nx, ny = dx / d, dy / d
                inst.x, inst.y = s.x + nx * (cr + 1), s.y + ny * (cr + 1)
                _bounce_inst(inst, host, P, nx, ny, targets)
                return


def inst_off_figure(inst, host, hx, hy, hr):
    """fxkit hit hook: the effect that just hit a fighter bounces off it
    instead of ending.  True when it bounced."""
    P = _inst_cfg(inst, host)
    if not (P and P["characters"]):
        return False
    dx, dy = inst.x - hx, inst.y - hy
    d = math.hypot(dx, dy)
    if d < 0.01:
        dx, dy, d = -inst.vx, -inst.vy, math.hypot(inst.vx, inst.vy) or 1.0
    nx, ny = dx / d, dy / d
    inst.x, inst.y = hx + nx * (hr + 2), hy + ny * (hr + 2)
    _bounce_inst(inst, host, P, nx, ny, None)
    return True


def inst_dmg_mult(inst):
    return getattr(inst, "ua_dm", 1.0) or 0.0


# ------------------------------------------------------------ Transformations (dual_form)
def _df_letters(P):
    """The form letters in use, in cycle order ("ab" .. "abcdef")."""
    return DF_FORMS[:max(2, min(len(DF_FORMS), int(P.get("forms", 2))))]


def _df_cur(st, P):
    """The form it is in (back to the first when the count was lowered)."""
    f = st.form if st is not None else "a"
    return f if f in _df_letters(P) else "a"


def _form(fig, P):
    return P["form_" + _df_cur(getattr(fig, "ua", None), P)]


def _form_lut(fig, st, F):
    from .palette import build_lut
    if F["palette"]:
        return build_lut([_rgb(F["body"], (242, 244, 246)), _rgb(F["accent"], (63, 176, 234))])
    return st.df_lut0


def _df_tick(fig, world, st, P):
    if not st.df_init:
        st.df_init = True
        st.df_lut0 = fig.lut
        lut = _form_lut(fig, st, P["form_a"])
        if lut is not None and lut is not fig.lut:
            _set_lut(fig, lut)
    if st.df_cd > 0:
        st.df_cd -= 1
    if st.df_buff > 0:
        st.df_buff -= 1
    if st.df_pending is not None:
        # One transition at a time: a trigger that fires meanwhile (an HP
        # threshold crossed mid-transition) stays queued in df_want and
        # starts the next transition once this one lands.
        _df_transition_tick(fig, world, st, P)
        return
    if st.df_left > 0:
        st.df_left -= 1
        if st.df_left <= 0 and _df_cur(st, P) != "a":
            st.df_target = "a"     # the form ran out: back to the first form
            st.df_want = True
    if P["trigger"] == "timer":
        st.df_timer += 1
        if st.df_timer >= _ticks(P["every_ms"]):
            st.df_timer = 0
            st.df_want = True
    elif P["trigger"] == "gauge" and st.df_gauge >= 100.0 and st.df_cd <= 0:
        st.df_want = True
    if st.df_want:
        st.df_want = False
        _df_begin(fig, world, st, P)


def _df_fill(fig, world, st, P):
    st.df_gauge = min(100.0, st.df_gauge + 100.0 / max(1, P["gauge_hits"]))


def _df_begin(fig, world, st, P):
    """A trigger fired: start the transition to the next form in the cycle.
    With a transition action the form changes when that action ends (its
    borrowed FX plays while it does); without one it changes now (and the
    FX plays one pass on its own)."""
    letters = _df_letters(P)
    cur = _df_cur(st, P)
    nxt = letters[(letters.index(cur) + 1) % len(letters)]
    if st.df_target and st.df_target in letters and st.df_target != cur:
        nxt = st.df_target
    st.df_target = None
    tr = (P.get("transitions") or {}).get(cur + ">" + nxt) or {}
    st.df_pending = nxt
    st.df_tr_act = str(tr.get("action") or "")
    st.df_act = None
    st.df_pair = cur + ">" + nxt
    st.df_pair_act = st.df_tr_act
    st.df_fx = str(tr.get("fx") or "")
    st.df_fx_once = False
    st.df_fx_seq += 1
    st.df_wait = _ticks(1000)    # longest wait for the action to get a turn
    from . import action_log
    action_log.log("COMBAT", f"transform {cur}->{nxt} action={st.df_tr_act or '-'} fx={st.df_fx or '-'}")
    if not st.df_tr_act:
        st.df_fx_once = True       # its FX play one pass on their own
        st.df_time_new = True      # and its Time control runs for its duration
        _df_switch(fig, st, P)
        return
    _df_transition_tick(fig, world, st, P)


def _df_start_act(fig, world, st):
    """Start the transition action.  True = playing, False = blocked this
    tick (another triggered action plays), None = it can never play here."""
    from . import actions
    r = getattr(fig, "act", None)
    if r is None or world is None or st.df_tr_act not in fig.render.bundle.extra:
        return None
    if actions.force_action(fig, world, st.df_tr_act):
        st.df_act, st.df_act_started = st.df_tr_act, r.started
        return True
    return False


def _df_transition_tick(fig, world, st, P):
    """Mid-transition: wait for the action to start, then for it to end; the
    new form takes over after that (or once the wait runs out)."""
    if st.df_act is not None:
        r = getattr(fig, "act", None)
        if r is not None and r.playing == st.df_act and r.started == st.df_act_started:
            return
        st.df_act = None
        _df_switch(fig, st, P)
        return
    res = _df_start_act(fig, world, st)
    if res:
        return
    # Blocked by a triggered action (ultimate, special, ...) already
    # playing: wait for it to end (clone_allows keeps new ones from
    # starting meanwhile).  Anything else (a forced clash) runs the wait down.
    from . import actions
    r = getattr(fig, "act", None)
    if not (res is False and r is not None and r.playing is not None and r.forced is None
            and actions._kind(r.playing) == "triggered"):
        st.df_wait -= 1
    if res is None or st.df_wait <= 0:
        st.df_fx_once = True       # the FX still play their pass
        st.df_time_new = True
        _df_switch(fig, st, P)


def _df_switch(fig, st, P):
    """Into the pending form: its palette, stats and actions from now on, a
    short buff and the transition burst."""
    if not st.df_init:
        st.df_init = True
        st.df_lut0 = fig.lut
    letters = _df_letters(P)
    nxt = st.df_pending
    if nxt not in letters:
        cur = _df_cur(st, P)
        nxt = letters[(letters.index(cur) + 1) % len(letters)]
    st.form = nxt
    st.df_form_seq += 1
    lasts = P["form_" + nxt].get("lasts_ms", 0.0) if nxt != "a" else 0.0
    st.df_left = _ticks(lasts) if lasts and lasts > 0 else 0
    st.df_pending = None
    st.df_act = None
    st.df_tr_act = ""
    st.df_gauge = 0.0
    st.df_cd = _ticks(P["cooldown_ms"])
    st.df_buff = _ticks(P["buff_ms"]) if P["buff_ms"] > 0 else 0
    F = _form(fig, P)
    lut = _form_lut(fig, st, F)
    if lut is not None:
        _set_lut(fig, lut)
    if P["transition_fx"]:
        rgb = _rgb(F["aura_color"], tuple(fig.lut[200]))
        _burst(st.sparks, fig.transform.x, fig.transform.y, rgb, n=26, spd=(1.5, 6.0),
               rng=fig.personality.rng)
        st.flash = 14
        st.flash_rgb = rgb


def transition_fx(fig):
    """fxkit.FxDriver hook: (borrowed fx key, transition "a>b", its action,
    transition number, once) for the transition FX playing now, or
    ("", "", "", 0, False).  They play while the transition action does
    (the borrowed "fx" and the FX built on "@transform:a>b"); `once` = no
    action (or it never got to play): one pass of their own timing, then
    the driver calls transition_fx_done."""
    st = getattr(fig, "ua", None)
    if st is None or not st.df_pair or _of(fig, "dual_form") is None:
        return "", "", "", 0, False
    if st.df_act is not None:
        return st.df_fx, st.df_pair, st.df_pair_act, st.df_fx_seq, False
    if st.df_fx_once:
        return st.df_fx, st.df_pair, st.df_pair_act, st.df_fx_seq, True
    return "", "", "", 0, False


def form_fx(fig):
    """fxkit.FxDriver hook: (borrowed fx key, form letter, form number) of
    the form it is in, or ("", "", 0).  The driver plays the borrowed FX and
    the FX built on "@form:<letter>" as its Character FX (in place of the
    character's own) while they exist."""
    P = _of(fig, "dual_form")
    if P is None:
        return "", "", 0
    st = getattr(fig, "ua", None)
    cur = _df_cur(st, P)
    return str(P["form_" + cur].get("fx") or ""), cur, (st.df_form_seq if st is not None else 0)


def _tr_time(st, P):
    from .fxkit import normalize_time
    tr = (P.get("transitions") or {}).get(st.df_pair) or {}
    tc = tr.get("time")
    if not isinstance(tc, dict) or not tc.get("enabled"):
        return None
    out = normalize_time(tc)
    out["duration_ms"] = max(0.0, float(tc.get("duration_ms") or 0.0))
    return out


def transition_time(fig, action):
    """timefx hook: the transition's Time control while `action` plays as
    that transition's action (in place of the action's own), else None."""
    if not in_transition_action(fig, action):
        return None
    P = _of(fig, "dual_form")
    return _tr_time(fig.ua, P) if P is not None else None


def take_transition_time(fig):
    """timefx hook: a transition without an action just happened: (its Time
    control, ticks it lasts) once, or None."""
    st = getattr(fig, "ua", None)
    if st is None or not st.df_time_new:
        return None
    st.df_time_new = False
    P = _of(fig, "dual_form")
    tc = _tr_time(st, P) if P is not None else None
    if tc is None or tc["duration_ms"] <= 0:
        return None
    return tc, _ticks(tc["duration_ms"])


def in_transition_action(fig, action):
    """True while `action` is playing as a transition's action: only its
    animation shows (its own FX stay for when it plays by itself)."""
    st = getattr(fig, "ua", None)
    return st is not None and st.df_act is not None and st.df_act == action


def transition_fx_done(fig):
    st = getattr(fig, "ua", None)
    if st is not None:
        st.df_fx_once = False


# ------------------------------------------------------------ Summoner
class _ConstructMode(_modes.FigureMode):
    """The mode a construct runs on: its owner's tuning (speeds, HP table)
    but no character, no shooting and no melee FSM, so the shared systems
    move it (familiar) and let it be hit, and unique.tick drives what it
    does.  Never registered: constructs are not a character."""
    character = None

    def __init__(self, base):
        self.key = base.key
        self._base = base

    def speeds(self):
        return self._base.speeds()

    def body_scale(self):
        return 1.0

    def charges_full(self):
        return True   # a familiar closes all the way in


_CMODES = {}


def _cmode(base):
    m = _CMODES.get(id(base))
    if m is None or m._base is not base:
        m = _ConstructMode(base)
        _CMODES[id(base)] = m
    return m


def _place(fig, world, P, n, key="spread_px"):
    """n points for new constructs / structures by P["placement"]."""
    x, y = fig.transform.x, fig.transform.y
    rng = fig.personality.rng
    sp = P[key]
    ex, ey = _nearest(_enemy_points(fig, world), x, y) or (x + 1.0, y)
    dx, dy = ex - x, ey - y
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    pl = P["placement"]
    pts = []
    for i in range(n):
        off = (i - (n - 1) / 2.0) * max(30.0, P.get("size_px", 20.0) * 2.5)
        if pl == "between":
            cx, cy = (x + ex) / 2.0, (y + ey) / 2.0
            pts.append((cx - uy * off, cy + ux * off))
        elif pl == "front":
            pts.append((x + ux * sp - uy * off, y + uy * sp + ux * off))
        elif pl == "near_enemy":
            pts.append((ex - ux * sp - uy * off, ey - uy * sp + ux * off))
        elif pl == "random":
            pts.append((rng.uniform(60, fig.screen_w - 60), rng.uniform(60, fig.screen_h - 60)))
        else:   # around
            a = rng.uniform(0, 2 * math.pi) if n == 1 else 2 * math.pi * i / n + rng.uniform(-0.3, 0.3)
            pts.append((x + math.cos(a) * sp, y + math.sin(a) * sp))
    return pts


def _summon(fig, world, P):
    """Queue P["count"] constructs: real Figures on the owner's side (enemies
    see and can target them), joined by world_tick."""
    from .figure import Figure
    st = state(fig)
    st.clones = [c for c in st.clones if c.personality.hp > 0 and c.ua.clone_left > 0]
    n = min(P["count"], P["max_alive"] - len(st.clones) - len(st.pending))
    if n <= 0:
        return
    whole = isinstance(fig.personality.max_hp, int)
    hp = max(1, int(round(P["construct_hp"]))) if whole else max(0.1, float(P["construct_hp"]))
    kind = P["construct"]
    rgb = _rgb(P["color"], (124, 243, 255))
    for i, (px, py) in enumerate(_place(fig, world, P, n)):
        px, py = _clamp_xy(fig, px, py)
        c = Figure(_cmode(fig.mode), fig.render.bundle, fig.lut,
                   fig.index + 1 + len(st.clones) + len(st.pending), fig.screen_w, fig.screen_h)
        c.transform.x, c.transform.y = px, py
        c.transform.facing_left = fig.transform.facing_left
        c.transform.init = True
        c.personality.max_hp = c.personality.hp = hp
        if kind == "familiar":
            k = P["chase_speed_pct"] / 100.0
            c.motion.speed = fig.motion.speed * k
            c.motion.follow_speed = fig.motion.follow_speed * k
        else:
            c.motion.speed = c.motion.follow_speed = 0.0
        cs = UAState(c)
        cs.clone_of, cs.clone_left, cs.clone_P = fig, _ticks(P["life_ms"]), P
        cs.construct = kind
        cs.con_cd = _ticks(P["fire_ms"] if kind == "turret" else P["bite_ms"]) // 2
        c.ua = cs
        st.pending.append(c)
        _burst(st.sparks, px, py, rgb, n=12, spd=(1.0, 4.0), rng=fig.personality.rng)


def holds_still(fig):
    """MotionSystem: turrets and totems never walk (a knockback still
    slides them)."""
    st = getattr(fig, "ua", None)
    return st is not None and st.construct is not None and st.construct != "familiar"


def _construct_tick(fig, world, st):
    P = st.clone_P
    o = st.clone_of
    if st.con_cd > 0:
        st.con_cd -= 1
    x, y = fig.transform.x, fig.transform.y
    rgb = _rgb(P["color"], (124, 243, 255))
    kind = st.construct
    tgt = _nearest(_enemy_points(fig, world), x, y)
    if tgt is not None:
        st.con_aim = math.atan2(tgt[1] - y, tgt[0] - x)
        fig.transform.facing_left = tgt[0] < x
    if kind == "turret":
        if tgt is not None and st.con_cd <= 0 and math.hypot(tgt[0] - x, tgt[1] - y) <= P["range_px"]:
            st.con_cd = _ticks(P["fire_ms"])
            spd = config.PROJ_SPEED * P["shot_speed_pct"] / 100.0
            pr = _shot(x, y, tgt[0], tgt[1], rgb, P["shot_damage"], fig, speed=spd,
                       max_age=P["range_px"] / max(0.5, spd) + 10)
            world.projectiles.append(pr)
            world.muzzle_flashes.append([x, y, 0] + list(rgb))
    elif kind == "familiar":
        reach = P["size_px"] + 26.0
        if tgt is not None and st.con_cd <= 0 and math.hypot(tgt[0] - x, tgt[1] - y) <= reach:
            st.con_cd = _ticks(P["bite_ms"])
            pr = _shot(x, y, tgt[0], tgt[1], rgb, P["bite_damage"], fig, speed=config.PROJ_SPEED,
                       max_age=reach / config.PROJ_SPEED + 4)
            pr.one_hit = True
            world.projectiles.append(pr)
            _burst(world.sparks, x, y, rgb, n=5, spd=(1.0, 3.0))
    elif kind == "totem_heal" and o is not None and o.personality.hp > 0:
        if (o.x - x) ** 2 + (o.y - y) ** 2 <= P["aura_px"] ** 2:
            p = o.personality
            if p.hp < p.max_hp:
                p.hp = min(p.max_hp, p.hp + P["heal_per_s"] * TICK_MS / 1000.0)
                if st.t % 12 == 0:
                    _burst(world.sparks, o.x, o.y - 10, (110, 255, 150), n=2, spd=(0.5, 1.5))


# ------------------------------------------------------------ Aegis
def _aegis_tick(fig, st, P):
    if st.shield is None:
        st.shield = P["shield_hp"]
    st.shield_idle += 1
    if st.shield < P["shield_hp"] and st.shield_idle >= _ticks(P["regen_delay_ms"]):
        st.shield = min(P["shield_hp"], st.shield + P["regen_per_s"] * TICK_MS / 1000.0)


def _shockwave(world, si, owner, x, y, P):
    """Aegis break: every enemy within the radius takes damage, is knocked
    away from the centre and stunned (Solo: no enemy fighters to reach)."""
    from . import ai, motion
    rgb = _rgb(P["color"], (111, 208, 255))
    world.impact_rings.append([x, y, 0, P["wave_px"]])
    r2 = P["wave_px"] ** 2
    for sj, side in enumerate(world.sides):
        if sj == si:
            continue
        for ef in list(side.figures):
            if not ef.transform.init:
                continue
            dx, dy = ef.x - x, ef.y - y
            if dx * dx + dy * dy > r2:
                continue
            d = math.hypot(dx, dy) or 1.0
            if P["wave_damage"] > 0:
                ai.apply_hp_damage(ef, world, P["wave_damage"])
            if P["wave_knockback_px"] > 0:
                spd = P["wave_knockback_px"] * (1.0 - config.BOUNCE_FRICTION)
                motion.launch_knockback(ef, dx / d * spd, dy / d * spd, world.global_tick)
            if P["stun_ms"] > 0:
                est = state(ef)
                est.stun_left = max(est.stun_left, _ticks(P["stun_ms"]))
            _burst(world.sparks, ef.x, ef.y, rgb, n=8, spd=(1.0, 3.5))


# ------------------------------------------------------------ Terraform
class _Struct:
    __slots__ = ("kind", "x", "y", "r", "ax", "ay", "bx", "by", "hp", "max_hp", "left", "life",
                 "owner", "P", "hit_flash")

    def __init__(self, owner, P, x, y, ux, uy):
        self.kind = P["structure"]
        self.owner, self.P = owner, P
        self.x, self.y = x, y
        self.r = P["size_px"] / 2.0 if self.kind == "wall" else P["size_px"]
        h = P["wall_len_px"] / 2.0
        # a wall stands across the line owner -> enemy
        self.ax, self.ay = x - uy * h, y + ux * h
        self.bx, self.by = x + uy * h, y - ux * h
        self.hp = self.max_hp = float(P["struct_hp"])
        self.life = self.left = _ticks(P["life_ms"])
        self.hit_flash = 0

    def dist(self, px, py):
        """Distance from (px, py) to the structure's surface line / centre,
        and the unit normal pointing out toward it."""
        if self.kind == "wall":
            vx, vy = self.bx - self.ax, self.by - self.ay
            L2 = vx * vx + vy * vy or 1.0
            t = max(0.0, min(1.0, ((px - self.ax) * vx + (py - self.ay) * vy) / L2))
            cx, cy = self.ax + vx * t, self.ay + vy * t
        else:
            cx, cy = self.x, self.y
        dx, dy = px - cx, py - cy
        d = math.hypot(dx, dy)
        if d < 0.01:
            return 0.0, 1.0, 0.0
        return d, dx / d, dy / d

    def blocks_shots(self):
        return self.kind != "pit" and self.hp > 0


def _tf_tick(fig, world, st, P):
    if st.tf_cd > 0:
        st.tf_cd -= 1
    live = []
    for s in st.structs:
        if s.hit_flash > 0:
            s.hit_flash -= 1
        if s.hp <= 0:
            _shatter(fig, world, s)
            continue
        s.left -= 1
        if s.left <= 0:
            _burst(world.sparks, s.x, s.y, _rgb(P["color"], (201, 164, 106)), n=8, spd=(0.5, 2.0))
            continue
        live.append(s)
    st.structs = live
    if st.tf_cd > 0:
        return
    if P["trigger"] == "timer":
        st.tf_timer += 1
        if st.tf_timer >= _ticks(P["every_ms"]):
            st.tf_timer = 0
            _raise_struct(fig, world, st, P)
    elif P["trigger"] == "enemy_near":
        x, y = fig.transform.x, fig.transform.y
        e = _nearest(_enemy_points(fig, world), x, y)
        if e is not None and math.hypot(e[0] - x, e[1] - y) <= P["near_px"]:
            _raise_struct(fig, world, st, P)


def _raise_struct(fig, world, st, P):
    st.tf_cd = _ticks(P["cooldown_ms"])
    if len([s for s in st.structs if s.hp > 0]) >= P["max_alive"]:
        return
    x, y = fig.transform.x, fig.transform.y
    ex, ey = _nearest(_enemy_points(fig, world), x, y) or (x + 1.0, y)
    d = math.hypot(ex - x, ey - y) or 1.0
    ux, uy = (ex - x) / d, (ey - y) / d
    px, py = _place(fig, world, P, 1, key="distance_px")[0]
    px, py = _clamp_xy(fig, px, py, margin=P["size_px"] + 4)
    s = _Struct(fig, P, px, py, ux, uy)
    st.structs.append(s)
    _burst(st.sparks, px, py, _rgb(P["color"], (201, 164, 106)), n=14, spd=(1.0, 4.0),
           rng=fig.personality.rng)


def _shatter(fig, world, s):
    P = s.P
    rgb = _rgb(P["color"], (201, 164, 106))
    _burst(world.sparks, s.x, s.y, rgb, n=18, spd=(1.5, 5.5))
    if not (P["shatter"] and P["shrapnel"] > 0 and s.kind != "pit"):
        return
    n = P["shrapnel"]
    a0 = fig.personality.rng.uniform(0, 2 * math.pi)
    for i in range(n):
        a = a0 + 2 * math.pi * i / n
        pr = _shot(s.x, s.y, s.x + math.cos(a), s.y + math.sin(a), rgb, P["shrapnel_damage"], fig,
                   speed=config.PROJ_SPEED * 1.1, max_age=40)
        pr.radius = 2.5
        world.projectiles.append(pr)


def _blocking(world, side_idx, for_shots):
    """Structures that block the side being simulated (an enemy's always,
    its own only with 'Also blocks own')."""
    for (s, si) in getattr(world, "ua_structs", ()) or ():
        if s.hp <= 0:
            continue
        if for_shots and not s.blocks_shots():
            continue
        if si == side_idx and not s.P["blocks_own"]:
            continue
        yield s


def _struct_hit(s, x, y, damage, sparks):
    s.hp -= max(0.0, float(damage))
    s.hit_flash = 5
    _burst(sparks, x, y, _rgb(s.P["color"], (201, 164, 106)), n=4, spd=(0.8, 2.5))


def _proj_blocked(proj, world):
    """A bullet entering a blocking structure dies there and chips it."""
    for s in _blocking(world, getattr(world, "side_idx", 0), True):
        d, _nx, _ny = s.dist(proj.x, proj.y)
        if d <= s.r + float(getattr(proj, "radius", 3.0)):
            _struct_hit(s, proj.x, proj.y, getattr(proj, "damage", 1.0), world.sparks)
            proj.age = proj.max_age
            return True
    return False


def push_out(fig, world):
    """MotionSystem: keep a fighter's body out of blocking structures and
    pits (a knockback into one stops at its surface)."""
    structs = getattr(world, "ua_structs", None)
    if not structs:
        return
    body = 16.0 * fig.mode.body_scale()
    for s in _blocking(world, getattr(world, "side_idx", 0), False):
        d, nx, ny = s.dist(fig.transform.x, fig.transform.y)
        lim = s.r + body
        if d < lim:
            t = fig.transform
            t.x += nx * (lim - d)
            t.y += ny * (lim - d)
            m = fig.motion
            if m.bouncing:
                dot = m.bounce_vx * nx + m.bounce_vy * ny
                if dot < 0:
                    m.bounce_vx -= dot * nx
                    m.bounce_vy -= dot * ny


# ------------------------------------------------------------ Rewind Bullets
def _rw_start(proj, P):
    """Turn a bullet around: from now on it retraces its own path."""
    proj.ua_rw = 1
    k = P["return_speed_pct"] / 100.0
    proj.vx, proj.vy = proj.vx * k, proj.vy * k
    if hasattr(proj, "turn_rate"):
        proj.speed *= k   # homing bullets hold their own speed
    proj.damage = float(getattr(proj, "damage", 1.0)) * P["return_damage_pct"] / 100.0
    if P["tint"]:
        proj.r, proj.g, proj.b = _rgb(P["color"], (180, 140, 255))


def _rw_proj(proj, P):
    """Rewind Bullets, owner side, after the bullet moved: record the path
    on the way out; on the way back step along it at the return speed
    until it is back where it was fired, then it ends.  While returning,
    the last path point is where the bullet is."""
    path = proj.ua_path
    if proj.ua_rw == 0:
        path.append((proj.x, proj.y))
        if P["trigger"] == "delay" and len(path) >= _ticks(P["delay_ms"]):
            _rw_start(proj, P)
        return
    if len(path) < 2:
        proj.age = proj.max_age
        return
    x0, y0 = path.pop()
    x, y = x0, y0
    left = max(0.5, math.hypot(proj.vx, proj.vy))
    spd = left
    while path and left > 0:
        tx, ty = path[-1]
        d = math.hypot(tx - x, ty - y)
        if d <= left:
            x, y = tx, ty
            left -= d
            path.pop()
        else:
            x += (tx - x) / d * left
            y += (ty - y) / d * left
            left = 0.0
    dx, dy = x - x0, y - y0
    dd = math.hypot(dx, dy)
    proj.x, proj.y = x, y
    if dd > 1e-6:
        proj.vx, proj.vy = dx / dd * spd, dy / dd * spd
    if not path:
        proj.age = proj.max_age       # back where it was fired
        return
    path.append((x, y))
    proj.age = min(proj.age, proj.max_age - 2)   # alive for the whole way back


def _recall(fig, world, P):
    """Rewind Bullets 'recall': every bullet / travelling effect of this
    fighter in flight turns round now."""
    for pr in world.projectiles:
        if getattr(pr, "owner", None) is fig and pr.alive and pr.hit_r_sq > 0.0:
            if getattr(pr, "ua_rw", None) is None:
                pr.ua_rw, pr.ua_path = 0, [(pr.x, pr.y)]
            if pr.ua_rw == 0 and pr.ua_path:
                _rw_start(pr, P)
    drv = getattr(fig, "fx", None)
    if drv is not None and P["fx_too"]:
        for inst in drv.player.insts + drv.clane[0].insts:
            if inst.ua_rw == 0:
                _rw_inst_start(inst, P)


def _rw_inst_ok(inst):
    fx = inst.fx
    return (fx["battle"]["deals_damage"] and fx["prim"] not in _RC_PRIMS_OFF
            and (inst.free or fx["motion"]["kind"] in ("travel", "zigzag")))


def _rw_inst_start(inst, P):
    inst.ua_rw = 1
    k = P["return_speed_pct"] / 100.0
    inst.vx, inst.vy = -inst.vx * k, -inst.vy * k
    inst.dir = [-inst.dir[0], -inst.dir[1]]
    inst.zx, inst.zy = -inst.zx, -inst.zy
    inst.ua_dm *= P["return_damage_pct"] / 100.0
    # Long enough to come all the way back.
    inst.life = max(inst.life, inst.age + int(inst.ua_t / max(0.1, k)) + 2)


def _rw_inst(inst, host, P):
    if inst.ua_rw is None:
        inst.ua_rw = 0 if (P["fx_too"] and _rw_inst_ok(inst)) else -1
        inst.ua_t = 0
    if inst.ua_rw != 0:
        return
    inst.ua_t += 1
    if P["trigger"] == "delay" and inst.ua_t >= _ticks(P["delay_ms"]):
        _rw_inst_start(inst, P)


def proj_ghost(proj):
    """CollisionSystem: a returning Rewind bullet with 'Passes through
    shots' on is not scattered by (and doesn't scatter) enemy bullets."""
    if getattr(proj, "ua_rw", None) not in (1, 2):
        return False
    P = _of(getattr(proj, "owner", None), "rewind_bullets")
    return bool(P and P["pass_fx"])


# ------------------------------------------------------------ Phantom Swap
def _queue_swap(fig, P):
    st = state(fig)
    if P["uses"] > 0 and st.sw_used >= P["uses"]:
        return
    st.sw_cd = _ticks(P["cooldown_ms"])
    st.swaps += 1


def _do_swap(world, si, fig):
    """World level: swap places with a ticked target (picked at random from
    the ones there are), then turn shots in flight round."""
    from . import blink
    P = _of(fig, "phantom_swap")
    if P is None or not fig.transform.init:
        return
    st = state(fig)
    rng = fig.personality.rng
    side = world.sides[si]
    T = P["targets"]
    opts = []
    if T["enemy"]:
        foes = [f for j, s in enumerate(world.sides) if j != si for f in s.figures
                if f.transform.init and not blink.gone(f)]
        if foes:
            opts.append(("enemy", min(foes, key=lambda e: (e.x - fig.x) ** 2 + (e.y - fig.y) ** 2)))
        elif not world.battle_mode:
            opts.append(("cursor", None))
    if T["clone"]:
        mine = [f for f in side.figures if f is not fig and is_clone(f)
                and getattr(f.ua, "clone_of", None) is fig and f.personality.hp > 0]
        if mine:
            opts.append(("clone", rng.choice(mine)))
    if T["own_shot"]:
        shots = [pr for pr in side.projectiles
                 if getattr(pr, "owner", None) is fig and pr.alive and pr.hit_r_sq > 0.0]
        if shots:
            opts.append(("shot", rng.choice(shots)))
    if not opts:
        return
    what, other = rng.choice(opts)
    ox, oy = fig.transform.x, fig.transform.y
    if what == "cursor":
        # Solo: the cursor can't be moved, so it lands mirrored through it.
        cx, cy = world.cursor
        _warp(fig, 2 * cx - ox, 2 * cy - oy)
    elif what == "shot":
        _warp(fig, other.x, other.y)
        other.x, other.y = ox, oy
        other.trail.clear()
    else:
        nx, ny = other.transform.x, other.transform.y
        _warp(fig, nx, ny)
        _warp(other, ox, oy)
        other.trail.clear()
    fig.trail.clear()
    st.sw_used += 1
    nx, ny = fig.transform.x, fig.transform.y
    _protect(fig, world, P["invuln_ms"])
    rgb = _rgb(P["color"], (224, 123, 255))
    if P["swap_fx"]:
        _burst(world.sparks, ox, oy, rgb, n=16, spd=(1.0, 5.0), rng=rng)
        _burst(world.sparks, nx, ny, rgb, n=16, spd=(1.0, 5.0), rng=rng)
        st.flash = 12
        st.flash_rgb = rgb
    if P["reverse_enemy_shots"]:
        r2 = P["reverse_px"] ** 2
        for j, s in enumerate(world.sides):
            if j == si:
                continue
            keep = []
            for pr in s.projectiles:
                near = ((pr.x - ox) ** 2 + (pr.y - oy) ** 2 <= r2
                        or (pr.x - nx) ** 2 + (pr.y - ny) ** 2 <= r2)
                if near and pr.alive and pr.hit_r_sq > 0.0:
                    # Turned round and now the swapper's: it flies back at
                    # the side that fired it.
                    pr.vx, pr.vy = -pr.vx, -pr.vy
                    pr.owner = fig
                    pr.ua_rb = None
                    pr.age = 0
                    if hasattr(pr, "target"):
                        pr.target[0], pr.target[1] = pr.x - pr.vx * 50, pr.y - pr.vy * 50
                    side.projectiles.append(pr)
                    continue
                keep.append(pr)
            s.projectiles[:] = keep
    if P["reaim_own_shots"]:
        pts = [(f.x, f.y) for j, s in enumerate(world.sides) if j != si for f in s.figures]
        if not pts and not world.battle_mode:
            pts = [tuple(world.cursor)]
        for pr in side.projectiles:
            if getattr(pr, "owner", None) is fig and pr.alive and pr.hit_r_sq > 0.0:
                t = _nearest(pts, pr.x, pr.y)
                if t is None:
                    break
                spd = math.hypot(pr.vx, pr.vy)
                d = math.hypot(t[0] - pr.x, t[1] - pr.y) or 1.0
                pr.vx, pr.vy = (t[0] - pr.x) / d * spd, (t[1] - pr.y) / d * spd


# ------------------------------------------------------------ Domain Expansion
def _dm_fill(fig, st, P, amount):
    if st.dm_left > 0 or st.dm_cd > 0:
        return
    st.dm_gauge = min(100.0, st.dm_gauge + amount)


def _dm_tick(fig, world, st, P):
    if st.dm_left > 0:
        st.dm_left -= 1
        if st.dm_left <= 0:
            st.dm_cd = _ticks(P["cooldown_ms"])
        return
    if st.dm_cd > 0:
        st.dm_cd -= 1
        return
    if P["fill"] == "timer":
        st.dm_gauge = min(100.0, st.dm_gauge + 100.0 / _ticks(P["fill_ms"]))
    elif P["fill"] == "hp_below" and not st.dm_hp_fired and _hp_pct(fig) <= P["hp_below_pct"]:
        st.dm_hp_fired = True
        st.dm_gauge = 100.0
    if st.dm_gauge >= 100.0:
        st.dm_gauge = 0.0
        st.dm_left = _ticks(P["duration_ms"])
        rgb = _rgb(P["tint_color"], (90, 26, 255))
        world.impact_rings.append([fig.x, fig.y, 0, max(fig.screen_w, fig.screen_h) * 0.6])
        _burst(world.sparks, fig.x, fig.y, rgb, n=30, spd=(2.0, 8.0))
        st.flash = 14
        st.flash_rgb = rgb


def _own_rule(fig, rule):
    st = getattr(fig, "ua", None)
    if st is None or st.dm_left <= 0:
        return False
    P = _of(fig, "domain_expansion")
    return bool(P and P["rules"].get(rule))


def _enemy_domains(fig, world):
    """(owner, settings) of every domain up on another side than fig's."""
    for (si, owner, P) in getattr(world, "ua_domains", ()) or ():
        if owner is fig:
            continue
        side = world.sides[si]
        if fig in side.figures:
            continue
        yield owner, P


def _enemy_rule(fig, world, rule):
    if world is None:
        return False
    return any(P["rules"].get(rule) for _o, P in _enemy_domains(fig, world))


def _enemy_slow(fig, world):
    if world is None:
        return 1.0
    k = 1.0
    for _o, P in _enemy_domains(fig, world):
        if P["rules"].get("slow_enemy"):
            k *= max(0.05, 1.0 - P["slow_pct"] / 100.0)
    return k


def _domain_world(world, si, owner, P):
    """World level, each tick a domain is up: enemy shots fizzle, gravity
    drags / pushes enemy fighters."""
    R = P["rules"]
    for sj, side in enumerate(world.sides):
        if sj == si:
            continue
        if R["enemy_shots_off"]:
            for pr in side.projectiles:
                if pr.alive and pr.hit_r_sq > 0.0:
                    world.sparks.append([pr.x, pr.y, 0.0, -0.6, 0, pr.r, pr.g, pr.b])
                    pr.age = pr.max_age
            for f in side.figures:
                drv = getattr(f, "fx", None)
                if drv is None:
                    continue
                for inst in drv.player.insts + drv.clane[0].insts:
                    fxd = inst.fx
                    if (fxd["battle"]["deals_damage"] and not inst.dead and inst.age < inst.life
                            and fxd["motion"]["kind"] in ("travel", "homing", "zigzag", "path")
                            and fxd["prim"] not in _RC_PRIMS_OFF):
                        inst.age = max(inst.age, inst.life)
        if R["gravity"] and P["gravity_px"] > 0:
            if P["gravity_to"] == "centre":
                gx, gy = owner.screen_w / 2.0, owner.screen_h / 2.0
            else:
                gx, gy = owner.x, owner.y
            sgn = -1.0 if P["gravity_mode"] == "push" else 1.0
            for ef in side.figures:
                if not ef.transform.init:
                    continue
                t = ef.transform
                dx, dy = gx - t.x, gy - t.y
                d = math.hypot(dx, dy)
                if d < 1.0:
                    continue
                step = min(d - 1.0, P["gravity_px"]) if sgn > 0 else P["gravity_px"]
                t.x = min(max(t.x + dx / d * step * sgn, 0.0), float(ef.screen_w))
                t.y = min(max(t.y + dy / d * step * sgn, 0.0), float(ef.screen_h))


def fx_size_mult(fig):
    """fxkit.spawn: an effect fired inside its owner's 'Huge FX' domain is
    launched at this size (its reach and speed scale with it)."""
    if fig is None or not _own_rule(fig, "huge_fx"):
        return 1.0
    return max(0.1, _of(fig, "domain_expansion")["fx_size_pct"] / 100.0)


def blink_free(fig):
    """'0 ms blink' domain rule: blinks come off cooldown at once."""
    return _own_rule(fig, "blink_no_cd")


def _dm_proj(proj, world, fig):
    """Own bullets inside the owner's domain: 'Huge FX' grows them once,
    'Guaranteed hits' steers them onto the nearest enemy."""
    P = _of(fig, "domain_expansion")
    st = getattr(fig, "ua", None)
    if P is None or st is None or st.dm_left <= 0:
        return
    R = P["rules"]
    if R["huge_fx"] and not getattr(proj, "ua_big", False) and proj.hit_r_sq > 0.0:
        k = max(0.1, P["fx_size_pct"] / 100.0)
        proj.radius *= k
        proj.hit_r_sq *= k * k
        proj.ua_big = True
    if R["guaranteed_hits"] and proj.hit_r_sq > 0.0:
        t = _nearest(_enemy_points(fig, world), proj.x, proj.y)
        if t is not None:
            spd = math.hypot(proj.vx, proj.vy)
            d = math.hypot(t[0] - proj.x, t[1] - proj.y)
            if d > 1.0 and spd > 0.01:
                proj.vx, proj.vy = (t[0] - proj.x) / d * spd, (t[1] - proj.y) / d * spd
                if hasattr(proj, "target"):
                    proj.target[0], proj.target[1] = t[0], t[1]


# ------------------------------------------------------------ Fusion
def _fusion_world(world, dead):
    """Timed fusions count down and split; team-mates that both carry Fusion
    (different characters) and both meet their ticked conditions fuse."""
    for si, side in enumerate(world.sides):
        figs = side.figures
        for f in list(figs):
            st = getattr(f, "ua", None)
            if st is None or st.fu_parents is None or f in dead:
                continue
            if f.mode is not st.fu_mode:
                st.fu_parents = None     # re-skinned by a key: the fusion is over
                continue
            if st.fu_left is not None:
                st.fu_left -= 1
                if st.fu_left <= 0:
                    _split(world, side, f, st)
        real = [f for f in figs if not is_clone(f) and f not in dead and f.transform.init]
        cands = []
        for f in real:
            P = _of(f, "fusion")
            st = getattr(f, "ua", None)
            if P is None:
                continue
            st = state(f)
            if st.fu_parents is not None:
                continue
            if st.fu_cd > 0:
                st.fu_cd -= 1
                st.fu_together = 0
                continue
            cands.append((f, P, st))
        for (f, P, st) in cands:
            if any(g.mode.key != f.mode.key for (g, _p, _s) in cands if g is not f):
                if st.fu_together == 0:
                    st.fu_l0 = st.landed
                st.fu_together += 1
            else:
                st.fu_together = 0
        pair = None
        for i in range(len(cands)):
            for j in range(i + 1, len(cands)):
                a, Pa, sa = cands[i]
                b, Pb, sb = cands[j]
                if (a.mode.key != b.mode.key and _fusion_ok(a, Pa, sa, b, sb)
                        and _fusion_ok(b, Pb, sb, a, sa)):
                    pair = (a, b, Pa)
                    break
            if pair:
                break
        if pair:
            _fuse(world, side, *pair)


def _fusion_ok(f, P, st, g, sg):
    C = P["conds"]
    if C["hp_below"] and _hp_pct(f) > P["hp_below_pct"]:
        return False
    if C["close"] and math.hypot(f.x - g.x, f.y - g.y) > P["close_px"]:
        return False
    if C["field_time"] and st.fu_together < _ticks(P["field_ms"]):
        return False
    if C["hits_landed"] and (st.landed - st.fu_l0) + (sg.landed - sg.fu_l0) < P["hits"]:
        return False
    return True


def _fuse(world, side, a, b, P):
    from .figure import Figure
    from .palette import lut_for_mode
    key = str(P["result"] or "").strip()
    if key not in _modes.MODE_REGISTRY:
        key = a.mode.key
    try:
        bundle = world.assets.bundle(key)
    except Exception:
        key, bundle = a.mode.key, a.render.bundle
    nf = Figure(_modes.get_mode(key), bundle, lut_for_mode(key, a.index), a.index,
                a.screen_w, a.screen_h)
    nf.transform.x, nf.transform.y = (a.x + b.x) / 2.0, (a.y + b.y) / 2.0
    nf.transform.facing_left = a.transform.facing_left
    nf.transform.init = True
    pa, pb, pn = a.personality, b.personality, nf.personality
    whole = isinstance(pa.max_hp, int) and isinstance(pb.max_hp, int)
    pn.max_hp = pa.max_hp + pb.max_hp
    pn.hp = pa.hp + pb.hp
    if whole:
        pn.max_hp, pn.hp = int(round(pn.max_hp)), max(1, int(round(pn.hp)))
    nf.motion.speed = max(a.motion.speed, b.motion.speed)
    nf.motion.follow_speed = max(a.motion.follow_speed, b.motion.follow_speed)
    st = state(nf)
    st.fu_parents = (a, b)
    st.fu_P = P
    st.fu_mode = nf.mode
    st.fu_dmg = out_mult(a) + out_mult(b)
    st.fu_left = _ticks(P["duration_ms"]) if P["ending"] == "timed" else None
    figs = side.figures
    figs[figs.index(a)] = nf
    figs.remove(b)
    rgb = _rgb(P["aura_color"], (255, 255, 255))
    for f in (a, b):
        _burst(world.sparks, f.x, f.y, tuple(f.lut[200]), n=16, spd=(1.0, 5.0))
        for pr in side.projectiles:
            if pr.owner is f:
                pr.owner = nf
    world.impact_rings.append([nf.x, nf.y, 0, 140.0])
    _burst(world.sparks, nf.x, nf.y, rgb, n=34, spd=(2.0, 8.0))
    st.flash = 16
    st.flash_rgb = rgb
    world.notice = ("Fusion: %s + %s -> %s" % (a.mode.key, b.mode.key, key), 150)


def _split(world, side, f, st):
    """A timed fusion ends: both team-mates come back, sharing the fused
    fighter's HP by their max HP, and can't fuse again for the cooldown."""
    a, b = st.fu_parents
    P = st.fu_P
    st.fu_parents = None
    hp, tot = f.personality.hp, float(a.personality.max_hp + b.personality.max_hp) or 1.0
    figs = side.figures
    i = figs.index(f)
    for k, (g, dx) in enumerate(((a, -30.0), (b, 30.0))):
        p = g.personality
        share = hp * p.max_hp / tot
        p.hp = max(1, int(round(share))) if isinstance(p.max_hp, int) else max(0.1, share)
        p.hp = min(p.hp, p.max_hp)
        p.dmg_immune_until = 0
        g.transform.x, g.transform.y = _clamp_xy(g, f.x + dx, f.y)
        g.motion.bouncing = g.motion.bounce_ending = False
        g.motion.bounce_vx = g.motion.bounce_vy = 0.0
        g.trail.clear()
        gs = state(g)
        gs.fu_cd = _ticks(P["cooldown_ms"])
        gs.fu_together = 0
        gs.fu_l0 = gs.landed
        _burst(world.sparks, g.x, g.y, tuple(g.lut[200]), n=14, spd=(1.0, 4.5))
    figs[i] = a
    figs.insert(i + 1, b)
    for pr in side.projectiles:
        if pr.owner is f:
            pr.owner = a
    world.notice = ("Fusion ended", 90)


# ------------------------------------------------------------ bullets / FX each tick
def proj_step(proj, world):
    """ProjectileSystem hook (the bullet's own side), after it moved:
    Terraform structures stop it, Rewind Bullets records / retraces its
    path, the owner's domain grows / steers it, Ricochet bounces it."""
    if proj.hit_r_sq > 0.0 and getattr(world, "ua_structs", None) and _proj_blocked(proj, world):
        return
    owner = proj.owner
    if owner is None:
        figs = world.figures or []
        if len(figs) == 1 and _of(figs[0], "rewind_bullets") is not None:
            proj.owner = owner = figs[0]
    if owner is not None:
        if getattr(proj, "ua_rw", None) is None:
            P = _of(owner, "rewind_bullets")
            if P is None or proj.hit_r_sq <= 0.0:
                proj.ua_rw = -1
            else:
                proj.ua_rw = 0
                proj.ua_path = [(proj.x - proj.vx, proj.y - proj.vy), (proj.x, proj.y)]
        if proj.ua_rw >= 0:
            P = _of(owner, "rewind_bullets")
            if P is not None:
                _rw_proj(proj, P)
                if not proj.alive:
                    return
        _dm_proj(proj, world, owner)
    _rc_proj_step(proj, world)


def _inst_blocked(inst, world):
    fx = inst.fx
    if (not fx["battle"]["deals_damage"] or fx["prim"] in _RC_PRIMS_OFF
            or not (inst.free or fx["motion"]["kind"] in ("travel", "homing", "zigzag", "path"))):
        return False
    for s in _blocking(world, getattr(world, "side_idx", 0), True):
        d, _nx, _ny = s.dist(inst.x, inst.y)
        if d <= s.r + 6.0 * (inst.ps or 1.0):
            _struct_hit(s, inst.x, inst.y, float(fx["battle"].get("damage") or 1.0), world.sparks)
            inst.age = max(inst.age, inst.life)
            return True
    return False


def inst_step(inst, host):
    """fxkit.tick_inst hook (owner side), after the effect moved:
    structures, Rewind Bullets, Ricochet."""
    world = getattr(host, "world", None)
    if world is not None and getattr(world, "ua_structs", None) and _inst_blocked(inst, world):
        return
    P = _of(getattr(host, "fig", None), "rewind_bullets")
    if P is not None:
        _rw_inst(inst, host, P)
    _rc_inst_step(inst, host)


# ------------------------------------------------------------ drawing
def _bar(p, x, y, w, frac, rgb, pscale, h=3.0):
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 0, 0, 120))
    p.drawRect(QRectF(x - w / 2.0, y, w, h * pscale))
    r, g, b = rgb
    p.setBrush(QColor(r, g, b, 220))
    p.drawRect(QRectF(x - w / 2.0, y, w * max(0.0, min(1.0, frac)), h * pscale))


def _glow(p, x, y, rr, rgb, a):
    r, g, b = rgb
    grad = QRadialGradient(QPointF(x, y), rr)
    grad.setColorAt(0.0, QColor(r, g, b, int(max(0, min(255, a)))))
    grad.setColorAt(1.0, QColor(r, g, b, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(QPointF(x, y), rr, rr)


def _draw_structs(p, st, pscale):
    for s in st.structs:
        if s.hp <= 0:
            continue
        r, g, b = _rgb(s.P["color"], (201, 164, 106))
        fade = min(1.0, s.left / 20.0)
        a = int(230 * fade)
        hit = s.hit_flash > 0
        if s.kind == "wall":
            pen = QPen(QColor(255, 255, 255, a) if hit else QColor(r, g, b, a), s.r * 2.0)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(s.ax, s.ay), QPointF(s.bx, s.by))
            p.setPen(QPen(QColor(min(255, r + 60), min(255, g + 60), min(255, b + 60), a), 1.5))
            p.drawLine(QPointF(s.ax, s.ay), QPointF(s.bx, s.by))
        elif s.kind == "pit":
            grad = QRadialGradient(QPointF(s.x, s.y), s.r)
            grad.setColorAt(0.0, QColor(0, 0, 0, int(220 * fade)))
            grad.setColorAt(0.75, QColor(r // 3, g // 3, b // 3, int(200 * fade)))
            grad.setColorAt(1.0, QColor(r, g, b, int(160 * fade)))
            p.setPen(QPen(QColor(r, g, b, a), 1.5))
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(s.x, s.y), s.r, s.r)
            continue
        else:
            p.setPen(QPen(QColor(255, 255, 255, a) if hit else QColor(r, g, b, a), 2.0))
            p.setBrush(QColor(r // 2, g // 2, b // 2, int(200 * fade)))
            p.drawEllipse(QPointF(s.x, s.y), s.r, s.r)
            p.setBrush(QColor(r, g, b, int(120 * fade)))
            p.drawEllipse(QPointF(s.x - s.r * 0.25, s.y - s.r * 0.25), s.r * 0.45, s.r * 0.45)
        if s.hp < s.max_hp:
            _bar(p, s.x, s.y - s.r - 8, 30.0 * pscale, s.hp / s.max_hp, (r, g, b), pscale, 2.5)


def draw_construct(fig, p):
    """Figure.draw: a construct is drawn as itself (turret / totem /
    familiar), not as its owner's sprite.  True when it drew."""
    st = getattr(fig, "ua", None)
    if st is None or st.construct is None:
        return False
    P = st.clone_P
    x, y = fig.transform.x, fig.transform.y
    pscale = fig._position_scale()
    R = P["size_px"] * pscale
    rgb = _rgb(P["color"], (124, 243, 255))
    r, g, b = rgb
    tk = st.t
    life = st.clone_left / float(max(1, _ticks(P["life_ms"])))
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    kind = st.construct
    if kind == "turret":
        _glow(p, x, y, R * 1.8, rgb, 70)
        p.setPen(QPen(QColor(r, g, b, 230), 2.0))
        p.setBrush(QColor(20, 24, 30, 220))
        p.drawEllipse(QPointF(x, y), R, R)
        pen = QPen(QColor(r, g, b, 240), max(2.0, R * 0.45))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x, y), QPointF(x + math.cos(st.con_aim) * R * 1.5,
                                          y + math.sin(st.con_aim) * R * 1.5))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(r, g, b, 255))
        p.drawEllipse(QPointF(x, y), R * 0.35, R * 0.35)
    elif kind in ("totem_heal", "totem_shield"):
        pulse = 0.5 + 0.5 * math.sin(tk * 0.12)
        ar = P["aura_px"]
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(r, g, b, int(40 + 40 * pulse)), 1.5, Qt.DashLine))
        p.drawEllipse(QPointF(x, y), ar, ar)
        _glow(p, x, y, R * 2.2, rgb, 90 + 60 * pulse)
        poly = QPolygonF([QPointF(x, y - R * 1.6), QPointF(x + R * 0.7, y),
                          QPointF(x, y + R * 1.2), QPointF(x - R * 0.7, y)])
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        p.setBrush(QColor(r, g, b, 210))
        p.drawPolygon(poly)
        p.setPen(QPen(QColor(255, 255, 255, 230), 2.0))
        if kind == "totem_heal":
            p.drawLine(QPointF(x - R * 0.3, y - R * 0.2), QPointF(x + R * 0.3, y - R * 0.2))
            p.drawLine(QPointF(x, y - R * 0.5), QPointF(x, y + R * 0.1))
        else:
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(x - R * 0.4, y - R * 0.6, R * 0.8, R * 0.8), 0, 180 * 16)
    else:   # familiar
        _glow(p, x, y, R * 1.9, rgb, 110)
        a = st.con_aim
        bob = math.sin(tk * 0.3) * 1.5
        p.setPen(QPen(QColor(255, 255, 255, 160), 1.2))
        p.setBrush(QColor(r, g, b, 230))
        p.drawEllipse(QPointF(x, y + bob), R * 0.8, R * 0.8)
        for s_ in (-1, 1):
            ex = x + math.cos(a + s_ * 0.45) * R * 0.45
            ey = y + bob + math.sin(a + s_ * 0.45) * R * 0.45
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 255))
            p.drawEllipse(QPointF(ex, ey), R * 0.18, R * 0.18)
    pp = fig.personality
    if pp.max_hp:
        _bar(p, x, y + R * 1.7, 26.0 * pscale, pp.hp / float(pp.max_hp), rgb, pscale, 2.5)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QColor(r, g, b, 120), 1.2))
    p.drawArc(QRectF(x - R * 1.3, y - R * 1.3, R * 2.6, R * 2.6), 90 * 16, int(360 * 16 * life))
    if st.flash > 0:
        p.setPen(QPen(QColor(255, 255, 255, int(200 * st.flash / 12.0)), 2.0))
        p.drawEllipse(QPointF(x, y), R * 1.5, R * 1.5)
    p.restore()
    return True


def draw(fig, p, pscale=1.0):
    """Ability overlays around the figure (drawn behind the sprite)."""
    st = getattr(fig, "ua", None)
    c = cfg(fig)
    if c is None and st is None:
        return
    x, y = fig.transform.x, fig.transform.y
    try:
        bs = float(fig.mode.body_scale())
    except Exception:
        bs = 1.0
    R = 34.0 * bs * pscale
    tk = getattr(fig.render, "anim_tick", 0)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    kind, P = c if c is not None else (None, None)
    if kind == "domain_expansion" and st is not None and st.dm_left > 0 and P["tint"]:
        r, g, b = _rgb(P["tint_color"], (90, 26, 255))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(r, g, b, int(255 * max(0.0, min(0.6, P["tint_pct"] / 100.0)))))
        p.drawRect(QRectF(0, 0, fig.screen_w, fig.screen_h))
        rr = R * (2.0 + 0.3 * math.sin(tk * 0.4))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(r, g, b, 200), 2.5 * pscale))
        p.drawEllipse(QPointF(x, y), rr, rr)
    if st is not None and st.fu_parents is not None and st.fu_P is not None and st.fu_P["aura"]:
        rgb = _rgb(st.fu_P["aura_color"], (255, 255, 255))
        _glow(p, x, y, R * (1.5 + 0.15 * math.sin(tk * 0.5)), rgb, 120)
        if st.fu_left is not None:
            frac = st.fu_left / float(max(1, _ticks(st.fu_P["duration_ms"])))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(*rgb, 170), 2.0 * pscale))
            p.drawArc(QRectF(x - R * 1.2, y - R * 1.2, R * 2.4, R * 2.4), 90 * 16, int(360 * 16 * frac))
    if st is not None and st.structs:
        _draw_structs(p, st, pscale)
    if kind == "berserker" and P["aura"]:
        f = _rage(fig, P)
        if f > 0.01:
            r, g, b = _rgb(P["aura_color"], (255, 42, 42))
            pulse = 0.85 + 0.15 * math.sin(tk * 0.6)
            rr = R * (1.1 + 0.6 * f) * pulse
            grad = QRadialGradient(QPointF(x, y), rr)
            grad.setColorAt(0.0, QColor(r, g, b, int(150 * f)))
            grad.setColorAt(1.0, QColor(r, g, b, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(x, y), rr, rr)
    if kind == "riposte" and st is not None and st.stance_left > 0:
        r, g, b = _rgb(P["color"], (255, 211, 74))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(r, g, b, 200), 2.5 * pscale))
        p.drawEllipse(QPointF(x, y), R * 1.15, R * 1.15)
    if kind == "phase_shift" and P["show_charges"] and P["charges"] > 0 and st is not None:
        n = st.charges if st.charges is not None else P["charges"]
        r, g, b = fig.lut[200]
        p.setPen(Qt.NoPen)
        tot = min(P["charges"], 10)
        for i in range(tot):
            on = i < n
            p.setBrush(QColor(r, g, b, 230 if on else 60))
            px = x + (i - (tot - 1) / 2.0) * 9 * pscale
            p.drawEllipse(QPointF(px, y - R * 1.6), 3 * pscale, 3 * pscale)
    if kind == "dual_form":
        F = _form(fig, P)
        if F["aura"]:
            k = 1.0 + (0.25 if st is not None and st.df_buff > 0 else 0.0)
            _glow(p, x, y, R * 1.3 * k * (0.92 + 0.08 * math.sin(tk * 0.5)),
                  _rgb(F["aura_color"], (255, 58, 58)), 110)
        if P["show_gauge"] and P["trigger"] == "gauge" and st is not None:
            _bar(p, x, y + R * 1.25, 34.0 * pscale, st.df_gauge / 100.0,
                 _rgb(_form(fig, P)["aura_color"], (255, 58, 58)), pscale)
    if kind == "aegis" and st is not None:
        sh = st.shield if st.shield is not None else P["shield_hp"]
        frac = sh / P["shield_hp"] if P["shield_hp"] > 0 else 0.0
        r, g, b = _rgb(P["color"], (111, 208, 255))
        if frac > 0:
            rr = R * 1.25
            grad = QRadialGradient(QPointF(x, y), rr)
            grad.setColorAt(0.0, QColor(r, g, b, 0))
            grad.setColorAt(0.8, QColor(r, g, b, int(40 + 50 * frac)))
            grad.setColorAt(1.0, QColor(r, g, b, int(90 + 110 * frac)))
            p.setPen(QPen(QColor(r, g, b, int(120 + 110 * frac)), 1.5 * pscale))
            p.setBrush(QBrush(grad))
            p.drawEllipse(QPointF(x, y), rr, rr)
        if P["show_bar"]:
            _bar(p, x, y + R * 1.35, 34.0 * pscale, frac, (r, g, b), pscale)
    if kind == "domain_expansion" and P["show_gauge"] and st is not None:
        rgb = _rgb(P["tint_color"], (90, 26, 255))
        if st.dm_left > 0:
            frac = st.dm_left / float(max(1, _ticks(P["duration_ms"])))
        else:
            frac = st.dm_gauge / 100.0 if st.dm_cd <= 0 else 0.0
        _bar(p, x, y + R * 1.25, 34.0 * pscale, frac, rgb, pscale)
    if st is not None and st.stun_left > 0:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 236, 120, 230))
        for i in range(3):
            a = tk * 0.25 + 2 * math.pi * i / 3
            p.drawEllipse(QPointF(x + math.cos(a) * R * 0.6, y - R * 1.1 + math.sin(a) * R * 0.2),
                          2.5 * pscale, 2.5 * pscale)
    if st is not None and st.flash > 0:
        r, g, b = st.flash_rgb
        a = int(220 * st.flash / 12.0)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(r, g, b, max(0, min(255, a))), 3 * pscale))
        rr = R * (1.6 - st.flash / 12.0 * 0.5)
        p.drawEllipse(QPointF(x, y), rr, rr)
    p.restore()
