"""
Parry / Deflect (Daniel 2026-11-22), Solo + Battle, every fighter.

The F4 player fighter parries with Ctrl+Space; every other fighter (AI)
parries on its own with a chance roll.  A parry opens a timing window:

    0 .. perfect_ms       PERFECT: the hit does no damage and no knockback,
                          the attacker is staggered (body stopped through
                          the timefx Aegis-stun path, stagger_ms) and a
                          counter window opens (counter_ms): the parrier's
                          hits on that attacker deal counter_dmg_pct %, and
                          an AI image character plays its counter action
                          (counter_action, else its first attack_normal)
                          straight away.  Enemy shots / FX that come within
                          reach_px (x body scale) are sent off at their
                          source (dodge.py's parry path, fxkit
                          _Host.on_intercept): back at the target
                          ("reflect") or away ("deflect").  Player: an arrow
                          held = deflected that way, none held = reflected
                          back.  AI: fx_result (reflect / deflect / random).
    perfect_ms .. window_ms  NORMAL: damage x (100 - normal_reduce_pct) %,
                          knockback x normal_kb_pct %, no counter.

After the window a cooldown (cooldown_ms) stops a new parry, so mashing the
key whiffs.  A staggered attacker can still parry the counter back
(player: the key; AI: recover_pct chance), so parries can chain.

AI parry: a hit arriving on an AI fighter that has no window open and is
off cooldown is rolled once per tick: ai_perfect_pct -> perfect,
ai_normal_pct -> normal (as if it pressed with that timing).  An enemy shot
within reach is rolled once (ai_fx_pct) -> a perfect window that deflects it.
While staggered only recover_pct is rolled (perfect).

Settings: per character `pack.parry` (FX Studio file, any key below) over
DEFAULTS; built-ins use DEFAULTS.  enabled False = no parry at all (the
player key does nothing either).
"""

import math

from . import config, action_log

TICK_MS = config.TICK_MS

DEFAULTS = dict(
    enabled=True,
    perfect_ms=130.0, window_ms=330.0, cooldown_ms=420.0,
    normal_reduce_pct=60.0, normal_kb_pct=40.0,
    stagger_ms=520.0, counter_ms=900.0, counter_dmg_pct=150.0,
    counter_action="",
    reach_px=46.0, fx_result="random",      # AI only; player = arrows
    ai=True, ai_perfect_pct=10.0, ai_normal_pct=14.0, ai_fx_pct=18.0,
    recover_pct=22.0,
    hitstop_ticks=5, shake_px=4.0,
)
FX_RESULTS = ("reflect", "deflect", "random")
FLASH_TICKS = 18


def _ticks(ms):
    return max(0, int(round(max(0.0, float(ms or 0)) / TICK_MS)))


def config_for(fig):
    """Normalised parry settings for fig (cached on its mode), or None when
    switched off."""
    mode = fig.mode
    cfg = getattr(mode, "_parry_cfg", False)
    if cfg is not False:
        return cfg
    out = dict(DEFAULTS)
    char = getattr(mode, "character", None)
    if char and char.get("_package"):
        raw = (char.get("_fxkit") or {}).get("parry")
        if isinstance(raw, dict):
            for k, v in raw.items():
                if k in DEFAULTS:
                    out[k] = v
    if out.get("fx_result") not in FX_RESULTS:
        out["fx_result"] = DEFAULTS["fx_result"]
    cfg = out if out.get("enabled") else None
    try:
        mode._parry_cfg = cfg
    except Exception:
        pass
    return cfg


class ParryState:
    __slots__ = ("start", "until", "cd_until", "grade", "roll_tick", "seen",
                 "parries", "stun_until", "stun_by", "counter_on", "counter_until",
                 "counter_pending", "flash", "flash_kind", "player")

    def __init__(self):
        self.start = -10 ** 9       # tick the window opened
        self.until = -1             # tick it closes
        self.cd_until = 0           # no new parry before this tick
        self.grade = None           # "perfect" / "normal" forced by an AI roll
        self.roll_tick = -1         # an AI roll was made this tick
        self.seen = set()           # id() of shots already rolled for
        self.parries = 0
        self.stun_until = -1        # staggered by a perfect parry until
        self.stun_by = None         # id() of who parried it
        self.counter_on = None      # id() of the attacker it may counter
        self.counter_until = -1
        self.counter_pending = False
        self.flash = 0              # ticks left of the parry flash
        self.flash_kind = None      # "open" / "perfect" / "normal"
        self.player = False         # this window came from the key


def state(fig):
    st = getattr(fig, "parry", None)
    if st is None:
        st = ParryState()
        fig.parry = st
    return st


def _now(world):
    return int(getattr(world, "global_tick", 0) or 0)


def _open(fig, world, cfg, st, now, grade=None, player=False):
    st.start = now
    st.until = now + max(1, _ticks(cfg["window_ms"]))
    st.cd_until = st.until + _ticks(cfg["cooldown_ms"])
    st.grade = grade
    st.player = player
    st.flash, st.flash_kind = 8, "open"


def window(fig, world):
    """'perfect' / 'normal' while a parry window is open, else None."""
    st = getattr(fig, "parry", None)
    if st is None:
        return None
    now = _now(world)
    if now > st.until:
        return None
    if st.grade:
        return st.grade
    cfg = config_for(fig)
    if cfg is None:
        return None
    return "perfect" if now - st.start <= _ticks(cfg["perfect_ms"]) else "normal"


def stunned(fig, world):
    st = getattr(fig, "parry", None)
    return st is not None and _now(world) < st.stun_until


# ------------------------------------------------------------------ input
def press(world):
    """Ctrl+Space: the player fighter parries (opens the window)."""
    fig = world.player_fig()
    if fig is None:
        return
    cfg = config_for(fig)
    if cfg is None:
        world.notice = ("Parry is off for this character", 60)
        return
    st = state(fig)
    now = _now(world)
    if now < st.cd_until:
        return                     # still recovering from the last parry: whiff
    _open(fig, world, cfg, st, now, None, player=True)


# ------------------------------------------------------------------ AI roll
def _ai_on(fig, world, cfg):
    if not cfg.get("ai"):
        return False
    return fig is not world.player_fig() if hasattr(world, "player_fig") else True


def _ai_roll_hit(fig, world, cfg, st, now):
    """An AI fighter about to take a hit: maybe it parried in time."""
    if st.roll_tick == now or now <= st.until or now < st.cd_until:
        return
    if not _ai_on(fig, world, cfg):
        return
    st.roll_tick = now
    rng = fig.personality.rng.random() * 100.0
    if stunned(fig, world):
        if rng < float(cfg["recover_pct"]):
            _open(fig, world, cfg, st, now, "perfect")
        return
    pp, pn = float(cfg["ai_perfect_pct"]), float(cfg["ai_normal_pct"])
    if rng < pp:
        _open(fig, world, cfg, st, now, "perfect")
    elif rng < pp + pn:
        _open(fig, world, cfg, st, now, "normal")


# ------------------------------------------------------------------ attacker
def _attacker(fig, world):
    from . import battlestats, guard
    now = _now(world)
    pend = battlestats._PEND.get(id(fig))
    if pend is not None and pend[0] is not None and now - int(pend[2] or 0) <= 2:
        return pend[0]
    fid = getattr(fig, "last_hit_by", None)
    return guard._find_fig(world, fid) if fid is not None else None


def _perfect(fig, world, cfg, st, att, x=None, y=None):
    """A perfect parry landed: stagger the attacker, open the counter."""
    now = _now(world)
    st.parries += 1
    st.flash, st.flash_kind = FLASH_TICKS, "perfect"
    if att is not None and att is not fig:
        ast = state(att)
        ast.stun_until = now + _ticks(cfg["stagger_ms"])
        ast.stun_by = id(fig)
        ast.flash, ast.flash_kind = FLASH_TICKS, "stun"
        st.counter_on = id(att)
        st.counter_until = now + _ticks(cfg["counter_ms"])
        st.counter_pending = _ai_on(fig, world, cfg)
    try:
        world.hitstop_ticks = max(int(getattr(world, "hitstop_ticks", 0) or 0), int(cfg["hitstop_ticks"]))
        world.add_shake(float(cfg["shake_px"]), 10)
        world.punch_camera(fig.x if x is None else x, fig.y if y is None else y)
    except Exception:
        pass
    dots = getattr(world, "collision_dots", None)
    if dots is not None:
        dots.append([fig.x if x is None else x, fig.y if y is None else y, 0])
    if st.player:
        world.notice = ("PERFECT PARRY", 45)
    action_log.log("COMBAT", "perfect parry by %s" % getattr(fig.mode, "key", "?"))


# ------------------------------------------------------------------ hit hooks
def on_hit(fig, world, amount, kind="melee"):
    """ai.apply_hp_damage: a blockable hit is about to land on fig.  Returns
    the amount that still lands (0 = parried)."""
    if world is None:
        return amount
    cfg = config_for(fig)
    if cfg is None:
        return amount
    st = state(fig)
    now = _now(world)
    _ai_roll_hit(fig, world, cfg, st, now)
    w = window(fig, world)
    if w == "perfect":
        if st.flash_kind != "perfect" or st.flash < FLASH_TICKS - 2:
            _perfect(fig, world, cfg, st, _attacker(fig, world))
        return 0
    if w == "normal":
        if st.flash_kind != "normal":
            st.flash, st.flash_kind = 12, "normal"
            if st.player:
                world.notice = ("Parry", 30)
        return amount * max(0.0, 100.0 - float(cfg["normal_reduce_pct"])) / 100.0
    return amount


def kb_mult(fig, world):
    """Knockback kept on fig for a hit landing now (after on_hit)."""
    if world is None:
        return 1.0
    cfg = config_for(fig)
    if cfg is None:
        return 1.0
    w = window(fig, world)
    if w == "perfect":
        return 0.0
    if w == "normal":
        return max(0.0, float(cfg["normal_kb_pct"])) / 100.0
    return 1.0


def counter_mult(victim, world):
    """Damage multiplier for a hit on `victim`: x counter_dmg_pct when the
    hitter perfect-parried it and its counter window is still open."""
    vst = getattr(victim, "parry", None)
    if vst is None or vst.stun_by is None:
        return 1.0
    att = _attacker(victim, world)
    if att is None or id(att) != vst.stun_by:
        return 1.0
    ast = getattr(att, "parry", None)
    if ast is None or ast.counter_on != id(victim) or _now(world) > ast.counter_until:
        return 1.0
    cfg = config_for(att) or DEFAULTS
    return max(0.0, float(cfg["counter_dmg_pct"])) / 100.0


# ------------------------------------------------------------------ per tick
def _fx_cfg(fig, world, cfg, st):
    """dodge.py's parry settings for this window's shot deflect."""
    res = "reflect"
    vel_dir = None
    if st.player:
        dx, dy = getattr(world, "player_dir", (0, 0)) or (0, 0)
        if dx or dy:
            res, vel_dir = "deflect", (dx, dy)
    else:
        res = cfg["fx_result"]
        if res == "random":
            res = "reflect" if fig.personality.rng.random() < 0.5 else "deflect"
    return dict(parry_result=res, react_to="all_fx", parry_reach_px=cfg["reach_px"],
                parry_hurts=True), vel_dir


class _DodgeView:
    """The two fields dodge._parry_step reads / writes on its state."""
    __slots__ = ("seen", "parries")

    def __init__(self, seen, parries):
        self.seen = seen
        self.parries = parries


def _deflect_shots(fig, world, cfg, st, shots, area):
    from . import dodge, fxkit
    dcfg, vel_dir = _fx_cfg(fig, world, cfg, st)
    before = st.parries
    if vel_dir is None:
        view = _DodgeView(st.seen, st.parries)
        dodge._parry_step(fig, world, dcfg, view, shots, area)
        st.parries = view.parries
    else:
        # Player holding an arrow: each shot leaves along the arrow.
        reach = max(0.0, float(cfg["reach_px"])) * fig.mode.body_scale()
        host = None
        drv = getattr(fig, "fx", None)
        dl = math.hypot(vel_dir[0], vel_dir[1]) or 1.0
        ux, uy = vel_dir[0] / dl, vel_dir[1] / dl
        for s, still in [(s, False) for s in shots] + [(s, True) for s in area]:
            if not dodge._parryable(s, dcfg) or dodge._parry_gap(fig, s) > reach:
                continue
            s.dead = True
            st.seen.add(id(s.ref))
            st.parries += 1
            if still:
                s.ref.age = max(s.ref.age, s.ref.life)
                s.ref.dead = True
                continue
            spd = max(dodge.PARRY_MIN_SPEED, math.hypot(s.vx, s.vy))
            if drv is not None and host is None:
                host = fxkit._Host(drv, fig, world)
            if host is not None:
                host.on_intercept(None, s, "deflect", [ux * spd, uy * spd], True)
            else:
                dodge._kill_at_source(s)
    if st.parries > before:
        _perfect(fig, world, cfg, st, None)


def tick(fig, world):
    """CombatSystem, every fighter, Solo + Battle: the AI shot roll, the
    perfect window's shot / FX deflect, the AI counter."""
    cfg = config_for(fig)
    if cfg is None:
        return
    st = state(fig)
    now = _now(world)
    shots = getattr(world, "enemy_shots", None) or []
    area = getattr(world, "enemy_area", None) or []
    if st.seen:
        live = {id(s.ref) for s in shots} | {id(s.ref) for s in area}
        st.seen &= live
    # AI: a shot coming within reach is rolled once.
    if (shots or area) and now > st.until and now >= st.cd_until and _ai_on(fig, world, cfg):
        from . import dodge
        reach = max(0.0, float(cfg["reach_px"])) * fig.mode.body_scale()
        for s in list(shots) + list(area):
            if id(s.ref) in st.seen or s.dead:
                continue
            if dodge._parry_gap(fig, s) > reach:
                continue
            st.seen.add(id(s.ref))
            if fig.personality.rng.random() * 100.0 < float(cfg["ai_fx_pct"]):
                _open(fig, world, cfg, st, now, "perfect")
                break
    if (shots or area) and window(fig, world) == "perfect":
        # Shots seen by the AI roll still need deflecting: use a fresh set.
        seen_before = st.seen
        st.seen = set()
        _deflect_shots(fig, world, cfg, st, shots, area)
        st.seen |= seen_before
    # AI counter after a perfect parry.
    if st.counter_pending:
        st.counter_pending = False
        _counter(fig, world, cfg)


def _counter(fig, world, cfg):
    from . import actions, player
    if not actions.is_image(fig):
        return                      # built-ins just attack the staggered foe
    name = cfg.get("counter_action") or ""
    if not name:
        names = player.chain_names(fig, "attack")
        name = names[0] if names else ""
    if name:
        actions.force_action(fig, world, name)


# ------------------------------------------------------------------ drawing
def draw(p, fig, pscale):
    """Figure.draw, before the body: the parry ring (window open / perfect
    flash) and the stagger stars."""
    st = getattr(fig, "parry", None)
    if st is None or st.flash <= 0:
        return
    from PyQt5.QtGui import QColor, QPen
    from PyQt5.QtCore import Qt, QPointF
    k = st.flash / float(FLASH_TICKS)
    if st.flash_kind == "perfect":
        rgb, base, grow, width = (255, 245, 190), 16.0, 22.0, 2.4
    elif st.flash_kind == "normal":
        rgb, base, grow, width = (170, 210, 255), 15.0, 10.0, 1.6
    elif st.flash_kind == "stun":
        rgb, base, grow, width = (255, 120, 90), 12.0, 4.0, 1.4
    else:
        rgb, base, grow, width = (220, 235, 255), 14.0, 3.0, 1.2
    r = (base + grow * (1.0 - k)) * pscale
    p.save()
    p.translate(fig.transform.x, fig.transform.y - lift_z(fig) * pscale)
    c = QColor(*rgb)
    c.setAlpha(int(230 * min(1.0, k * 1.6)))
    pen = QPen(c)
    pen.setWidthF(width * max(0.6, pscale))
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if st.flash_kind == "perfect":
        p.drawEllipse(QPointF(0, 0), r, r)
        n = 8
        for i in range(n):
            a = (i / float(n)) * math.tau + st.parries * 0.7
            p.drawLine(QPointF(math.cos(a) * r * 0.7, math.sin(a) * r * 0.7),
                       QPointF(math.cos(a) * r * 1.25, math.sin(a) * r * 1.25))
    elif st.flash_kind == "stun":
        for i in range(3):
            a = (i / 3.0) * math.tau + st.flash * 0.35
            q = QPointF(math.cos(a) * r, -16 * pscale + math.sin(a) * r * 0.35)
            p.drawEllipse(q, 1.6 * pscale, 1.6 * pscale)
    else:
        p.drawArc(int(-r), int(-r), int(2 * r), int(2 * r), 30 * 16, 120 * 16)
        p.drawArc(int(-r), int(-r), int(2 * r), int(2 * r), 210 * 16, 120 * 16)
    p.restore()


def step(world):
    """Overlay sim tick, after both sides: flash timers for every fighter
    (a staggered fighter's body is stopped, so its CombatSystem pass
    doesn't run)."""
    for fig in world.all_figures():
        st = getattr(fig, "parry", None)
        if st is None:
            continue
        if st.flash > 0:
            st.flash -= 1
        if stunned(fig, world) and (st.flash <= 0 or st.flash_kind == "stun"):
            st.flash_kind = "stun"
            st.flash = max(st.flash, 6)


def lift_z(fig):
    lf = getattr(fig, "lift", None)
    return lf.z if lf is not None else 0.0


def reset(fig):
    fig.parry = None
