"""
Summoner constructs (Unique Ability "summoner", laser/unique.py).

A Summoner carries a LIST of summons (FX Studio: "Add summon").  Each entry
is independent: its own construct, trigger (timer / HP thresholds / hits
taken), count, cap, life, placement, lite movement style and FX.  Settings:
unique.SUMMON_DEFAULTS; the entry is the construct's clone_P.

Constructs are real Figures on the summoner's side (enemies see, target and
destroy them), never a fighter slot and never a loss.  Same code in Solo and
Battle; in Solo the enemy is the cursor, so what reaches enemy FIGHTERS
(blasts, auras, taunts, drains) only shows its FX there.

Constructs (SUMMON_CONSTRUCTS), after the summons of WoW / FFXIV / other FF
titles:
  turret          stands and shoots the nearest enemy
  totem_heal      heals the summoner inside its aura
  totem_shield    the summoner takes less damage inside its aura
  familiar        chases and bites
 supportive
  spirit_link     every pulse evens out the HP % of the summoner and every
                  construct inside its aura (constructs are HP batteries)
  liturgy_bell    N charges: each hit the summoner takes inside its aura
                  spends one to heal it; charges left heal when it ends
  earthly_star    matures over mature_ms, then detonates when its life ends
                  (or below detonate_hp_pct of the summoner's HP): heals the
                  summoner and blasts enemies in its aura, mature_pct
                  stronger once mature
 defensive
  grounding       the next shot / FX hit on the summoner inside its aura is
                  pulled into the totem instead; re-arms after rearm_ms
  black_ox        taunt: enemies within taunt_px aim at it, not the summoner
  soul_link       a familiar that takes link_pct of the summoner's damage
  commander       on arrival: the summoner's other constructs last
                  extend_ms longer and gain buff_pct HP; while it stands they
                  deal buff_pct more damage
 weakens the enemy
  capacitor       charges for charge_ms, then discharges: damage + stun to
                  every enemy in its aura; charges again
  earthbind       enemies in its aura are slowed (movement + attacks)
  hex_ward        enemies in its aura deal weaken_pct less, take expose_pct more
  siphon          each pulse drains enemies in its aura and heals the summoner
 offensive
  imp_swarm       small imps that shoot; once implode_at of them are out
                  they dive at the enemy and explode (more imps, more blasts)
  automaton_queen its power is set by the hits the summoner landed since the
                  last one; shoots, and blasts the enemy when its life ends
  demi_bahamut    every hit the summoner lands, it fires a beam at the same
                  target; a megaflare finisher when its life ends
  trance_eidolon  chases and strikes; after its life ends it keeps flashing
                  back in to strike for echo_ms

Movement (the lite style): one movestyle pattern per summon (or "auto" =
the construct's own way / "none" = stands still), round the enemy or the
summoner.  movestyle.cfg returns st.con_style for a construct;
World.movement_target centres it on the summoner (unique.construct_anchor).

FX: every time a construct acts (shot, bite, pulse, blast, ...) it queues
(summon id, borrowed fx, x, y) on its owner; fxkit.FxDriver._summon_tick
plays the borrowed FX and the FX built on "@summon:<id>" once from there,
aimed at the target.  Constructs that never attack play them on arrival and
every fx_every_ms.

Cross-side effects (blasts, drains, stuns, auras, taunts) are queued on the
owner and delivered by world_tick (unique.world_tick), like Aegis waves.
"""

import math
import random

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import (QColor, QPen, QBrush, QPainter, QRadialGradient, QLinearGradient,
                         QPolygonF, QPainterPath)

from . import config
from . import movestyle
from . import unique as U

TICK_MS = config.TICK_MS
SLOT_KEY = "@summon:"          # "@summon:<id>": a summon's own FX slot (laser/fxkit.py)

CATEGORY = {
    "turret": "offensive", "familiar": "offensive", "imp_swarm": "offensive",
    "automaton_queen": "offensive", "demi_bahamut": "offensive", "trance_eidolon": "offensive",
    "totem_heal": "support", "spirit_link": "support", "liturgy_bell": "support", "earthly_star": "support",
    "totem_shield": "defensive", "grounding": "defensive", "black_ox": "defensive",
    "soul_link": "defensive", "commander": "defensive",
    "capacitor": "debuff", "earthbind": "debuff", "hex_ward": "debuff", "siphon": "debuff",
}
# Constructs with an aura that reaches enemy fighters (world_tick).
ENEMY_AURAS = ("earthbind", "hex_ward")
# Constructs that never attack: their FX play on arrival and every fx_every_ms.
PASSIVE = ("totem_heal", "totem_shield", "black_ox", "soul_link", "commander", "earthbind",
           "hex_ward", "earthly_star", "liturgy_bell", "grounding")
# "auto" movement: (pattern, round what, its settings).  "legacy" = the old
# familiar chase (no style); missing = stands still.
AUTO_MOVE = {
    "familiar": ("legacy", "enemy", {}),
    "trance_eidolon": ("chase", "enemy", {}),
    "soul_link": ("orbit", "owner", dict(radius_px=55, lead_deg=40, direction="cw")),
    "imp_swarm": ("orbit", "enemy", dict(radius_px=170)),
    "automaton_queen": ("kite", "enemy", dict(min_px=150, max_px=280)),
    "demi_bahamut": ("shadow", "owner", dict(offset_px=70, angle_deg=180, lag_ms=200)),
}
DIVE_TICKS = 90                # imp implosion dive gives up after this long
IMP_BLAST_PX = 60.0


# ------------------------------------------------------------ helpers
def _alive(c):
    return c.personality.hp > 0 and c.ua is not None and c.ua.clone_left > 0


def _mine(st, kind=None, sid=None):
    """The summoner's live constructs (of one kind / one summon)."""
    out = []
    for c in st.clones:
        cs = c.ua
        if cs is None or cs.construct is None or not _alive(c):
            continue
        if kind is not None and cs.construct != kind:
            continue
        if sid is not None and cs.clone_P.get("id") != sid:
            continue
        out.append(c)
    return out


def _inside(a, b, r):
    return (a.transform.x - b.transform.x) ** 2 + (a.transform.y - b.transform.y) ** 2 <= r * r


def _heal(fig, amount):
    p = fig.personality
    if amount <= 0 or p.hp <= 0:
        return 0.0
    before = p.hp
    p.hp = min(p.max_hp, p.hp + amount)
    return p.hp - before


def _fire(o, E, x, y):
    """Queue the summon's FX (borrowed + "@summon:<id>") from (x, y)."""
    if o is None or o.ua is None:
        return
    if len(o.ua.sm_fires) < 24:
        o.ua.sm_fires.append((E["id"], str(E["fx"] or ""), x, y))


def _blast(fig, x, y, r, dmg, rgb, stun_ms=0.0, drain=False, ring=True):
    """Queue a hit on every enemy fighter within r of (x, y) (world_tick)."""
    o = fig.ua.clone_of if fig.ua is not None and fig.ua.clone_of is not None else fig
    if o.ua is None:
        return
    k = U.out_mult(fig) if fig is not o else 1.0
    o.ua.sm_blasts.append(dict(x=x, y=y, r=r, dmg=dmg * k, rgb=rgb, stun=stun_ms, drain=drain,
                               ring=ring, src=fig))


def _entry(st, E):
    es = st.sm_entries.get(E["id"])
    if es is None:
        es = dict(timer=0, fired=set(), hits=0, landed0=st.landed)
        st.sm_entries[E["id"]] = es
    return es


# ------------------------------------------------------------ the summoner
def owner_tick(fig, world, st, P):
    """unique.tick for a Summoner: each summon's timer, Trance Eidolon
    echoes and their strikes on screen."""
    for E in P["summons"]:
        es = _entry(st, E)
        if E["trigger"] == "timer":
            es["timer"] += 1
            if es["timer"] >= U._ticks(E["every_ms"]):
                es["timer"] = 0
                summon(fig, world, E)
    if st.sm_echoes:
        _echo_tick(fig, world, st)
    if st.sm_flashes:
        st.sm_flashes = [f for f in st.sm_flashes if f[3] < f[4]]
        for f in st.sm_flashes:
            f[3] += 1


def on_hurt(fig, world, st, P, amount):
    """unique.after_damage: HP-threshold / hits-taken summons, Liturgy Bells."""
    hp_pct = U._hp_pct(fig)
    for E in P["summons"]:
        es = _entry(st, E)
        if E["trigger"] == "hp_below":
            for th in U._thresholds(E["hp_thresholds"]):
                if th not in es["fired"] and hp_pct <= th:
                    es["fired"].add(th)
                    summon(fig, world, E)
        elif E["trigger"] == "hits_taken":
            es["hits"] += 1
            if es["hits"] >= E["every_hits"]:
                es["hits"] = 0
                summon(fig, world, E)
    for b in _mine(st, "liturgy_bell"):
        cs = b.ua
        E = cs.clone_P
        if cs.con_charges > 0 and _inside(fig, b, E["aura_px"]):
            cs.con_charges -= 1
            _heal(fig, E["charge_heal"])
            cs.flash, cs.flash_rgb = 14, (255, 236, 160)
            cs.con_links = [(fig.transform.x, fig.transform.y)]
            _fire(fig, E, b.transform.x, b.transform.y)
            if cs.con_charges <= 0:
                cs.clone_left = min(cs.clone_left, 2)   # spent: it fades out
            break


def on_landed(fig, st, P):
    """unique.note_landed: each Demi-Bahamut answers the hit with a beam."""
    for c in _mine(st, "demi_bahamut"):
        c.ua.con_queue = min(3, c.ua.con_queue + 1)


def shield_mult(fig):
    """unique.taken_mult: a shield totem whose aura holds the summoner."""
    st = getattr(fig, "ua", None)
    if st is None:
        return 1.0
    for t in _mine(st, "totem_shield"):
        E = t.ua.clone_P
        if _inside(fig, t, E["aura_px"]):
            return max(0.0, 1.0 - E["shield_pct"] / 100.0)
    return 1.0


def absorb(fig, world, amount, kind):
    """unique.absorb: a Grounding Totem pulls a shot / FX hit into itself;
    a Soul-Linked Familiar takes its share.  Returns what is left."""
    st = getattr(fig, "ua", None)
    if st is None:
        return amount
    if kind in ("projectile", "fx"):
        for t in _mine(st, "grounding"):
            cs = t.ua
            E = cs.clone_P
            if cs.con_armed <= 0 and _inside(fig, t, E["aura_px"]):
                cs.con_armed = U._ticks(E["rearm_ms"])
                t.personality.hp = max(0, t.personality.hp - amount)
                cs.flash, cs.flash_rgb = 14, (255, 255, 255)
                cs.con_links = [(fig.transform.x, fig.transform.y)]
                cs.con_cycle = 0
                _fire(fig, E, t.transform.x, t.transform.y)
                if world is not None:
                    U._burst(world.sparks, fig.transform.x, fig.transform.y, U._rgb(E["color"]), n=10,
                             spd=(1.5, 4.5))
                return 0.0
    for t in _mine(st, "soul_link"):
        cs = t.ua
        share = amount * max(0.0, min(100.0, cs.clone_P["link_pct"])) / 100.0
        if share <= 0:
            break
        take = min(share, max(0.0, float(t.personality.hp)))
        t.personality.hp -= take
        if isinstance(t.personality.max_hp, int):
            t.personality.hp = int(math.floor(t.personality.hp))
        cs.flash, cs.flash_rgb = 10, U._rgb(cs.clone_P["color"])
        return amount - take
    return amount


# ------------------------------------------------------------ summoning
def _style_of(E):
    """(lite movement style or None, centred on the summoner, moves at all)."""
    m = E["movement"]
    kind = E["construct"]
    pat, tgt, params = m["pattern"], m["target"], m["params"]
    if pat == "none":
        return None, False, False
    if pat == "auto":
        a = AUTO_MOVE.get(kind)
        if a is None:
            return None, False, False
        if a[0] == "legacy":
            return None, False, True
        pat, tgt, params = a[0], a[1], dict(movestyle.PATTERN_DEFAULTS[a[0]], **a[2])
    sty = movestyle.normalize(dict(enabled=True, select="priority", daze=False, phases=[
        dict(name=kind, pattern=pat, params=params, modifiers=dict(wall_avoid=True))]))
    return sty, tgt == "owner", True


def summon(fig, world, E):
    """Queue E["count"] constructs of one summon: real Figures on the
    owner's side, joined by unique.world_tick."""
    from .figure import Figure
    st = U.state(fig)
    st.clones = [c for c in st.clones if c.personality.hp > 0 and c.ua.clone_left > 0]
    mine = len(_mine(st, sid=E["id"])) + len([c for c in st.pending if c.ua.clone_P.get("id") == E["id"]])
    n = min(E["count"], E["max_alive"] - mine)
    if n <= 0:
        return
    whole = isinstance(fig.personality.max_hp, int)
    hp = max(1, int(round(E["construct_hp"]))) if whole else max(0.1, float(E["construct_hp"]))
    kind = E["construct"]
    rgb = U._rgb(E["color"], (124, 243, 255))
    sty, owner_anchor, moves = _style_of(E)
    spd = E["movement"]["speed_pct"] / 100.0
    es = _entry(st, E)
    power = 1.0
    if kind == "automaton_queen":
        power = min(E["max_power_pct"], 100.0 + E["per_hit_pct"] * max(0, st.landed - es["landed0"])) / 100.0
        es["landed0"] = st.landed
    for (px, py) in U._place(fig, world, E, n):
        px, py = U._clamp_xy(fig, px, py)
        c = Figure(U._cmode(fig.mode), fig.render.bundle, fig.lut,
                   fig.index + 1 + len(st.clones) + len(st.pending), fig.screen_w, fig.screen_h)
        c.transform.x, c.transform.y = px, py
        c.transform.facing_left = fig.transform.facing_left
        c.transform.init = True
        c.personality.max_hp = c.personality.hp = hp
        if moves:
            c.motion.speed = fig.motion.speed * spd
            c.motion.follow_speed = fig.motion.follow_speed * spd
        else:
            c.motion.speed = c.motion.follow_speed = 0.0
        cs = U.UAState(c)
        cs.clone_of, cs.clone_left, cs.clone_P = fig, U._ticks(E["life_ms"]), E
        cs.construct = kind
        cs.con_style, cs.con_owner_anchor = sty, owner_anchor
        cs.con_power = power
        cs.con_charges = E["charges"]
        cs.con_cd = U._ticks(E["bite_ms"] if kind in ("familiar", "trance_eidolon") else E["fire_ms"]) // 2
        c.ua = cs
        st.pending.append(c)
        U._burst(st.sparks, px, py, rgb, n=14, spd=(1.0, 4.5), rng=fig.personality.rng)
        if kind == "commander":
            _rally(fig, E)
        if kind not in PASSIVE:
            _fire(fig, E, px, py)


def _rally(o, E):
    """Commander arrival: the summoner's other constructs last longer and
    gain HP."""
    k = 1.0 + max(0.0, E["buff_pct"]) / 100.0
    ext = U._ticks(E["extend_ms"]) if E["extend_ms"] > 0 else 0
    for c in _mine(o.ua):
        cs = c.ua
        if cs.construct == "commander":
            continue
        cs.clone_left += ext
        p = c.personality
        if isinstance(p.max_hp, int):
            p.max_hp = int(round(p.max_hp * k))
            p.hp = min(p.max_hp, int(round(p.hp * k)))
        else:
            p.max_hp *= k
            p.hp = min(p.max_hp, p.hp * k)
        cs.flash, cs.flash_rgb = 12, (255, 214, 102)


def holds_still(fig, st):
    """unique.holds_still: diving imps are moved here, constructs without
    movement never walk."""
    if st.con_dive > 0:
        return True
    if st.con_style is not None:
        return False
    return not (st.construct == "familiar" and st.clone_P["movement"]["pattern"] == "auto")


# ------------------------------------------------------------ constructs
def construct_tick(fig, world, st):
    E = st.clone_P
    o = st.clone_of
    kind = st.construct
    if st.con_cd > 0:
        st.con_cd -= 1
    if st.con_armed > 0:
        st.con_armed -= 1
    st.con_cycle += 1
    x, y = fig.transform.x, fig.transform.y
    rgb = U._rgb(E["color"], (124, 243, 255))
    tgt = U._nearest(U._enemy_points(fig, world), x, y)
    if tgt is not None and st.con_dive <= 0:
        st.con_aim = math.atan2(tgt[1] - y, tgt[0] - x)
        fig.transform.facing_left = tgt[0] < x
    if st.t % 4 == 0:
        st.con_links = []
    fn = _TICKS.get(kind)
    if fn is not None:
        fn(fig, world, st, E, o, x, y, tgt, rgb)
    if kind in PASSIVE and o is not None:
        st.con_fx_cd -= 1
        if st.con_fx_cd <= 0:
            st.con_fx_cd = U._ticks(max(100.0, E["fx_every_ms"]))
            _fire(o, E, x, y)


def _shoot(fig, world, st, E, o, x, y, tgt, rgb, damage, speed_k=1.0, style=None):
    spd = config.PROJ_SPEED * E["shot_speed_pct"] / 100.0 * speed_k
    pr = U._shot(x, y, tgt[0], tgt[1], rgb, damage, fig, speed=spd,
                 max_age=E["range_px"] / max(0.5, spd) + 10)
    if style is not None:
        pr.style = style
    world.projectiles.append(pr)
    world.muzzle_flashes.append([x, y, 0] + list(rgb))
    _fire(o, E, x, y)


def _t_turret(fig, world, st, E, o, x, y, tgt, rgb):
    if tgt is not None and st.con_cd <= 0 and math.hypot(tgt[0] - x, tgt[1] - y) <= E["range_px"]:
        st.con_cd = U._ticks(E["fire_ms"])
        _shoot(fig, world, st, E, o, x, y, tgt, rgb, E["shot_damage"])


def _strike(fig, world, st, E, o, x, y, tgt, rgb, damage):
    """A contact hit: a short one-hit shot at the target."""
    reach = E["size_px"] + 26.0
    pr = U._shot(x, y, tgt[0], tgt[1], rgb, damage, fig, speed=config.PROJ_SPEED,
                 max_age=reach / config.PROJ_SPEED + 4)
    pr.one_hit = True
    world.projectiles.append(pr)
    U._burst(world.sparks, x, y, rgb, n=5, spd=(1.0, 3.0))
    _fire(o, E, x, y)


def _t_familiar(fig, world, st, E, o, x, y, tgt, rgb):
    if tgt is not None and st.con_cd <= 0 and math.hypot(tgt[0] - x, tgt[1] - y) <= E["size_px"] + 26.0:
        st.con_cd = U._ticks(E["bite_ms"])
        st.flash, st.flash_rgb = 8, rgb
        _strike(fig, world, st, E, o, x, y, tgt, rgb, E["bite_damage"])


def _t_totem_heal(fig, world, st, E, o, x, y, tgt, rgb):
    if o is not None and o.personality.hp > 0 and _inside(o, fig, E["aura_px"]):
        if _heal(o, E["heal_per_s"] * TICK_MS / 1000.0) > 0 and st.t % 12 == 0:
            U._burst(world.sparks, o.x, o.y - 10, (110, 255, 150), n=2, spd=(0.5, 1.5))
            st.con_links = [(o.transform.x, o.transform.y)]


def _t_spirit_link(fig, world, st, E, o, x, y, tgt, rgb):
    if o is None or st.con_cycle < U._ticks(E["link_ms"]):
        return
    st.con_cycle = 0
    r = E["aura_px"]
    mem = [c for c in _mine(o.ua) if _inside(c, fig, r)]
    if o.personality.hp > 0 and _inside(o, fig, r):
        mem.append(o)
    if len(mem) < 2:
        return
    tot = sum(max(0.0, float(m.personality.hp)) for m in mem)
    cap = sum(float(m.personality.max_hp) for m in mem) or 1.0
    frac = tot / cap
    for m in mem:
        p = m.personality
        v = p.max_hp * frac
        p.hp = max(1, int(round(v))) if isinstance(p.max_hp, int) else max(0.01, v)
    st.con_links = [(m.transform.x, m.transform.y) for m in mem if m is not fig]
    st.flash, st.flash_rgb = 12, rgb
    _fire(o, E, x, y)


def _t_earthly_star(fig, world, st, E, o, x, y, tgt, rgb):
    if (o is not None and E["detonate_hp_pct"] > 0 and not st.con_det
            and U._hp_pct(o) <= E["detonate_hp_pct"]):
        st.con_det = True
        st.clone_left = min(st.clone_left, 1)


def _t_grounding(fig, world, st, E, o, x, y, tgt, rgb):
    pass   # unique.absorb -> absorb()


def _t_capacitor(fig, world, st, E, o, x, y, tgt, rgb):
    if st.con_cycle < U._ticks(E["charge_ms"]):
        return
    st.con_cycle = 0
    st.flash, st.flash_rgb = 16, (255, 255, 255)
    _blast(fig, x, y, E["aura_px"], E["zap_damage"], rgb, stun_ms=E["stun_ms"])
    U._burst(world.sparks, x, y, rgb, n=22, spd=(2.0, 7.0))
    _fire(o, E, x, y)


def _t_siphon(fig, world, st, E, o, x, y, tgt, rgb):
    if st.con_cycle < U._ticks(E["link_ms"]):
        return
    st.con_cycle = 0
    _blast(fig, x, y, E["aura_px"], E["drain_per_s"] * E["link_ms"] / 1000.0, rgb, drain=True, ring=False)
    _fire(o, E, x, y)


def _t_imp(fig, world, st, E, o, x, y, tgt, rgb):
    if st.con_dive > 0:
        st.con_dive += 1
        if tgt is None:
            tgt = (x + math.cos(st.con_aim) * 10, y + math.sin(st.con_aim) * 10)
        dx, dy = tgt[0] - x, tgt[1] - y
        d = math.hypot(dx, dy)
        sp = max(6.0, (o.motion.speed if o is not None else 3.0) * 3.2)
        if d <= max(18.0, sp) or st.con_dive > DIVE_TICKS:
            st.flash = 0
            _blast(fig, x, y, IMP_BLAST_PX, E["implode_damage"], rgb)
            U._burst(world.sparks, x, y, (255, 180, 80), n=16, spd=(2.0, 6.0))
            world.impact_rings.append([x, y, 0, IMP_BLAST_PX])
            _fire(o, E, x, y)
            fig.personality.hp = 0
            return
        st.con_aim = math.atan2(dy, dx)
        fig.transform.x += dx / d * sp
        fig.transform.y += dy / d * sp
        return
    if o is not None:
        swarm = _mine(o.ua, "imp_swarm", E["id"])
        idle = [c for c in swarm if c.ua.con_dive <= 0]
        if len(idle) >= E["implode_at"]:
            for c in idle:
                c.ua.con_dive = 1
            return
    if tgt is not None and st.con_cd <= 0 and math.hypot(tgt[0] - x, tgt[1] - y) <= E["range_px"]:
        st.con_cd = U._ticks(E["fire_ms"])
        _shoot(fig, world, st, E, o, x, y, tgt, rgb, E["shot_damage"])


def _t_queen(fig, world, st, E, o, x, y, tgt, rgb):
    if tgt is not None and st.con_cd <= 0 and math.hypot(tgt[0] - x, tgt[1] - y) <= E["range_px"]:
        st.con_cd = U._ticks(E["fire_ms"])
        _shoot(fig, world, st, E, o, x, y, tgt, rgb, E["shot_damage"] * st.con_power)


def _t_bahamut(fig, world, st, E, o, x, y, tgt, rgb):
    if st.con_queue > 0 and tgt is not None and st.con_cd <= 0:
        st.con_queue -= 1
        st.con_cd = 4
        st.con_links = [tgt]
        st.flash, st.flash_rgb = 8, (255, 255, 255)
        spd = config.PROJ_SPEED * 2.6
        pr = U._shot(x, y, tgt[0], tgt[1], rgb, E["echo_damage"], fig, speed=spd,
                     max_age=math.hypot(tgt[0] - x, tgt[1] - y) / spd + 12)
        pr.style = "beam"
        world.projectiles.append(pr)
        _fire(o, E, x, y)


def _t_eidolon(fig, world, st, E, o, x, y, tgt, rgb):
    if tgt is not None and st.con_cd <= 0 and math.hypot(tgt[0] - x, tgt[1] - y) <= E["size_px"] + 30.0:
        st.con_cd = U._ticks(E["bite_ms"])
        st.flash, st.flash_rgb = 10, (255, 255, 255)
        if o is not None and o.ua is not None:
            o.ua.sm_flashes.append([x, y, st.con_aim, 0, 12, rgb, True])
        _strike(fig, world, st, E, o, x, y, tgt, rgb, E["bite_damage"])


_TICKS = {
    "turret": _t_turret, "familiar": _t_familiar, "totem_heal": _t_totem_heal,
    "spirit_link": _t_spirit_link, "earthly_star": _t_earthly_star, "grounding": _t_grounding,
    "capacitor": _t_capacitor, "siphon": _t_siphon, "imp_swarm": _t_imp,
    "automaton_queen": _t_queen, "demi_bahamut": _t_bahamut, "trance_eidolon": _t_eidolon,
}


def on_gone(fig, o, world, expired):
    """unique.world_tick: a construct dissolves.  expired = its life ran out
    (not destroyed) with its summoner still standing: finishers go off."""
    st = fig.ua
    E = st.clone_P
    kind = st.construct
    x, y = fig.transform.x, fig.transform.y
    rgb = U._rgb(E["color"], (124, 243, 255))
    if not expired or o is None or o.ua is None:
        return
    tgt = U._nearest(_enemy_pts_world(o, world), x, y)
    if kind == "liturgy_bell" and st.con_charges > 0:
        _heal(o, E["charge_heal"] * st.con_charges)
        world.impact_rings.append([x, y, 0, E["aura_px"]])
        _fire(o, E, x, y)
    elif kind == "earthly_star":
        k = E["mature_pct"] / 100.0 if st.t >= U._ticks(E["mature_ms"]) else 1.0
        if _inside(o, fig, E["aura_px"]):
            _heal(o, E["star_heal"] * k)
        _blast(fig, x, y, E["aura_px"], E["star_damage"] * k, rgb)
        U._burst(world.sparks, x, y, (255, 255, 255), n=int(18 + 14 * k), spd=(2.0, 7.0 * k))
        o.ua.sm_flashes.append([x, y, 0.0, 0, 20, rgb, "star", E["aura_px"] * (1.0 if k == 1.0 else 1.15)])
        _fire(o, E, x, y)
    elif kind in ("automaton_queen", "demi_bahamut") and tgt is not None:
        dmg = E["finisher_damage"] * (st.con_power if kind == "automaton_queen" else 1.0)
        _blast(fig, tgt[0], tgt[1], E["aura_px"], dmg, rgb)
        o.ua.sm_flashes.append([x, y, math.atan2(tgt[1] - y, tgt[0] - x), 0, 24, rgb, "flare",
                                tgt[0], tgt[1], E["aura_px"]])
        U._burst(world.sparks, tgt[0], tgt[1], rgb, n=26, spd=(2.0, 8.0))
        _fire(o, E, tgt[0], tgt[1])
    elif kind == "trance_eidolon" and E["echo_ms"] > 0:
        o.ua.sm_echoes.append([U._ticks(E["echo_ms"]), U._ticks(E["reappear_ms"]) // 2, E])


def _enemy_pts_world(o, world):
    si = U._side_of(world, o)
    pts = []
    for sj, side in enumerate(world.sides):
        if sj != si:
            pts.extend((f.transform.x, f.transform.y) for f in side.figures if f.transform.init)
    return pts or [tuple(world.cursor)]


def _echo_tick(fig, world, st):
    """Trance Eidolon after its life: it flashes back in next to the enemy
    and strikes, every reappear_ms, for echo_ms."""
    keep = []
    rng = fig.personality.rng
    for e in st.sm_echoes:
        e[0] -= 1
        e[1] -= 1
        E = e[2]
        if e[1] <= 0:
            e[1] = U._ticks(E["reappear_ms"])
            tgt = U._nearest(U._enemy_points(fig, world), fig.transform.x, fig.transform.y)
            if tgt is not None:
                a = rng.uniform(0, 2 * math.pi)
                sx, sy = tgt[0] + math.cos(a) * 46, tgt[1] + math.sin(a) * 46
                rgb = U._rgb(E["color"], (124, 243, 255))
                pr = U._shot(sx, sy, tgt[0], tgt[1], rgb, E["bite_damage"], fig, speed=config.PROJ_SPEED * 1.5,
                             max_age=12)
                pr.one_hit = True
                world.projectiles.append(pr)
                st.sm_flashes.append([sx, sy, a + math.pi, 0, 16, rgb, True])
                U._burst(world.sparks, sx, sy, rgb, n=8, spd=(1.0, 3.5))
                _fire(fig, E, sx, sy)
        if e[0] > 0:
            keep.append(e)
    st.sm_echoes = keep


# ------------------------------------------------------------ world level
def world_tick(world, dead):
    """Once per tick (unique.world_tick): deliver the constructs' blasts
    and drains to the other sides; publish taunts (world.ua_taunts) and the
    enemy auras on every fighter (ca_slow / ca_out / ca_in)."""
    taunts, auras = [], []
    for si, side in enumerate(world.sides):
        for f in list(side.figures):
            st = getattr(f, "ua", None)
            if st is None:
                continue
            if st.construct is not None and _alive(f):
                E = st.clone_P
                if st.construct == "black_ox":
                    taunts.append((si, f.transform.x, f.transform.y, E["taunt_px"]))
                elif st.construct in ENEMY_AURAS:
                    auras.append((si, f, E))
            if st.sm_blasts:
                blasts, st.sm_blasts = st.sm_blasts, []
                if f not in dead:
                    for b in blasts:
                        _deliver(world, si, f, b)
            if st.clone_of is None and st.clones:
                buff = 1.0
                for c in _mine(st, "commander"):
                    buff = max(buff, 1.0 + c.ua.clone_P["buff_pct"] / 100.0)
                for c in st.clones:
                    if c.ua is not None and c.ua.construct is not None:
                        c.ua.con_buff = buff if c.ua.construct != "commander" else 1.0
    world.ua_taunts = taunts
    for f in world.all_figures():
        st = getattr(f, "ua", None)
        if st is not None:
            st.ca_slow = st.ca_out = st.ca_in = 1.0
    for (si, a, E) in auras:
        r2 = E["aura_px"] ** 2
        hit = []
        for sj, side in enumerate(world.sides):
            if sj == si:
                continue
            for ef in side.figures:
                if (ef.transform.x - a.transform.x) ** 2 + (ef.transform.y - a.transform.y) ** 2 > r2:
                    continue
                est = U.state(ef)
                if a.ua.construct == "earthbind":
                    est.ca_slow *= max(0.05, 1.0 - E["slow_pct"] / 100.0)
                else:
                    est.ca_out *= max(0.0, 1.0 - E["weaken_pct"] / 100.0)
                    est.ca_in *= 1.0 + max(0.0, E["expose_pct"]) / 100.0
                hit.append((ef.transform.x, ef.transform.y))
        a.ua.con_links = hit


def _deliver(world, si, owner, b):
    from . import ai
    r2 = b["r"] ** 2
    if b["ring"]:
        world.impact_rings.append([b["x"], b["y"], 0, b["r"]])
    drained = 0.0
    hits = []
    for sj, side in enumerate(world.sides):
        if sj == si:
            continue
        for ef in list(side.figures):
            if not ef.transform.init:
                continue
            if (ef.x - b["x"]) ** 2 + (ef.y - b["y"]) ** 2 > r2:
                continue
            hits.append((ef.x, ef.y))
            if b["drain"]:
                drained += _drain(world, ef, b["dmg"], b["rgb"])
                continue
            if b["dmg"] > 0:
                ai.apply_hp_damage(ef, world, b["dmg"], kind="fx")
            if b["stun"] > 0:
                est = U.state(ef)
                est.stun_left = max(est.stun_left, U._ticks(b["stun"]))
            U._burst(world.sparks, ef.x, ef.y, b["rgb"], n=8, spd=(1.0, 3.5))
    src = b.get("src")
    if src is not None and src.ua is not None and hits:
        src.ua.con_links = hits
        src.ua.flash, src.ua.flash_rgb = 10, b["rgb"]
    if drained > 0 and owner.personality.hp > 0:
        _heal(owner, drained)


def _drain(world, ef, amount, rgb):
    """Siphon: HP straight out (no damage cooldown, no knockback)."""
    from . import dmgnum
    p = ef.personality
    if p.hp <= 0 or amount <= 0:
        return 0.0
    take = min(float(p.hp), amount)
    if isinstance(p.max_hp, int):
        take = float(max(1, int(round(take)))) if take >= 0.5 else 0.0
        if take <= 0:
            return 0.0
        p.hp = int(p.hp - take)
    else:
        p.hp -= take
    dmgnum.note(world, ef, take, dmgnum.fig_rgb(ef))
    for _ in range(3):
        world.sparks.append([ef.x, ef.y, 0.0, -1.2, 0] + list(rgb))
    if p.hp <= 0:
        p.hp = 0
        world.on_figure_death(ef)
    return take


# ================================================================ drawing
# The anime look of the FX techniques (laser/strikefx.py / swordfx.py):
# white-hot cores in coloured halos laid on additively, crisp bright rims,
# jagged lightning, four-point sparkles, speed lines and a summoning circle
# with a light pillar when each one arrives.
ARRIVE_TICKS = 36
FADE_TICKS = 30
WHITE = (255, 255, 255)


def _c(rgb, a):
    return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]), int(max(0, min(255, a))))


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _add(p):
    p.setCompositionMode(QPainter.CompositionMode_Plus)


def _over(p):
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)


def _halo(p, x, y, r, rgb, a, core=0.18):
    """Energy glow: white-hot centre fading through the colour (additive)."""
    if r <= 0.5 or a <= 1:
        return
    g = QRadialGradient(QPointF(x, y), r)
    g.setColorAt(0.0, _c(_mix(rgb, WHITE, 0.85), a))
    g.setColorAt(core, _c(_mix(rgb, WHITE, 0.35), a * 0.8))
    g.setColorAt(0.5, _c(rgb, a * 0.35))
    g.setColorAt(1.0, _c(rgb, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(g))
    p.drawEllipse(QPointF(x, y), r, r)


def _sparkle(p, x, y, r, rgb, a, rot=0.0):
    """Anime four-point glint: two long thin rays and two short ones."""
    if r <= 0.5 or a <= 1:
        return
    for i, (ln, w) in enumerate(((1.0, 0.16), (1.0, 0.16), (0.45, 0.1), (0.45, 0.1))):
        ang = rot + (0 if i == 0 else math.pi / 2 if i == 1 else math.pi / 4 if i == 2 else -math.pi / 4)
        ca, sa = math.cos(ang), math.sin(ang)
        L, W = r * ln, r * w
        poly = QPolygonF([QPointF(x + ca * L, y + sa * L), QPointF(x - sa * W, y + ca * W),
                          QPointF(x - ca * L, y - sa * L), QPointF(x + sa * W, y - ca * W)])
        p.setPen(Qt.NoPen)
        p.setBrush(_c(_mix(rgb, WHITE, 0.6), a))
        p.drawPolygon(poly)
    _halo(p, x, y, r * 0.35, rgb, a)


def _bolt(p, x0, y0, x1, y1, rgb, a, seed, w=2.0, jag=10.0):
    """Jagged lightning: a coloured outer stroke and a white core."""
    rng = random.Random(seed)
    dx, dy = x1 - x0, y1 - y0
    d = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / d, dx / d
    n = max(3, int(d / 18))
    pts = [QPointF(x0, y0)]
    for i in range(1, n):
        t = i / float(n)
        o = rng.uniform(-jag, jag) * math.sin(math.pi * t)
        pts.append(QPointF(x0 + dx * t + nx * o, y0 + dy * t + ny * o))
    pts.append(QPointF(x1, y1))
    path = QPainterPath(pts[0])
    for q in pts[1:]:
        path.lineTo(q)
    p.setBrush(Qt.NoBrush)
    for width, col in ((w * 3.2, _c(rgb, a * 0.45)), (w * 1.6, _c(rgb, a)), (w * 0.6, _c(WHITE, a))):
        pen = QPen(col, width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)


def _wave(p, x0, y0, x1, y1, rgb, a, phase, w=2.0, amp=6.0):
    """A flowing spirit tether (sine ribbon)."""
    dx, dy = x1 - x0, y1 - y0
    d = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / d, dx / d
    n = max(6, int(d / 10))
    path = QPainterPath(QPointF(x0, y0))
    for i in range(1, n + 1):
        t = i / float(n)
        o = math.sin(t * math.pi * 3 + phase) * amp * math.sin(math.pi * t)
        path.lineTo(QPointF(x0 + dx * t + nx * o, y0 + dy * t + ny * o))
    p.setBrush(Qt.NoBrush)
    for width, col in ((w * 2.6, _c(rgb, a * 0.4)), (w, _c(_mix(rgb, WHITE, 0.6), a))):
        pen = QPen(col, width)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawPath(path)


def _beam(p, x0, y0, x1, y1, rgb, a, w):
    p.setBrush(Qt.NoBrush)
    for width, col in ((w * 2.4, _c(rgb, a * 0.35)), (w * 1.3, _c(rgb, a)), (w * 0.5, _c(WHITE, a))):
        pen = QPen(col, width)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x0, y0), QPointF(x1, y1))


def _sigil(p, x, y, R, rgb, a, rot, sides=6, squash=0.42):
    """Summoning circle on the ground: double ring, rune ticks, a star."""
    if a <= 1 or R <= 1:
        return
    p.save()
    p.translate(x, y)
    p.scale(1.0, squash)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(_c(rgb, a * 0.55), 3.2))
    p.drawEllipse(QPointF(0, 0), R, R)
    p.setPen(QPen(_c(_mix(rgb, WHITE, 0.55), a), 1.3))
    p.drawEllipse(QPointF(0, 0), R, R)
    p.drawEllipse(QPointF(0, 0), R * 0.8, R * 0.8)
    for i in range(24):
        ang = rot + 2 * math.pi * i / 24
        r0, r1 = R * 0.82, R * (0.97 if i % 3 else 0.9)
        p.drawLine(QPointF(math.cos(ang) * r0, math.sin(ang) * r0), QPointF(math.cos(ang) * r1, math.sin(ang) * r1))
    pts = [QPointF(math.cos(-rot * 1.5 + 2 * math.pi * i / sides) * R * 0.78,
                   math.sin(-rot * 1.5 + 2 * math.pi * i / sides) * R * 0.78) for i in range(sides)]
    step = 2 if sides >= 5 else 1
    for i in range(sides):
        p.drawLine(pts[i], pts[(i + step) % sides])
    p.restore()


def _pillar(p, x, y, w, h, rgb, a):
    """The column of light a construct rises in: a tall soft glow, its
    white-hot core thinner, fading out at the top and the sides."""
    if a <= 1 or w <= 0.5 or h <= 0.5:
        return
    for ww, aa, white in ((w, a * 0.55, 0.25), (w * 0.3, a, 0.8)):
        p.save()
        p.translate(x, y - h * 0.45)
        p.scale(ww / h, 1.0)
        g = QRadialGradient(QPointF(0, 0), h * 0.55)
        g.setColorAt(0.0, _c(_mix(rgb, WHITE, white), aa))
        g.setColorAt(0.5, _c(rgb, aa * 0.45))
        g.setColorAt(1.0, _c(rgb, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(QPointF(0, 0), h * 0.55, h * 0.55)
        p.restore()


def _poly(p, pts, fill, rim, rim_w=1.6):
    p.setBrush(fill)
    pen = QPen(rim, rim_w)
    pen.setJoinStyle(Qt.MiterJoin)
    p.setPen(pen)
    p.drawPolygon(QPolygonF([QPointF(a, b) for a, b in pts]))


def _speedlines(p, x, y, ang, R, rgb, a, seed):
    rng = random.Random(seed)
    ca, sa = math.cos(ang), math.sin(ang)
    for _ in range(5):
        off = rng.uniform(-R, R)
        L = rng.uniform(R * 1.5, R * 3.2)
        sx, sy = x - ca * R * 0.8 - sa * off, y - sa * R * 0.8 + ca * off
        p.setPen(QPen(_c(_mix(rgb, WHITE, 0.5), a * rng.uniform(0.4, 0.9)), rng.uniform(0.8, 1.8)))
        p.drawLine(QPointF(sx, sy), QPointF(sx - ca * L, sy - sa * L))


def _aura_ring(p, x, y, r, rgb, a, tk, dash=True):
    p.setBrush(Qt.NoBrush)
    pen = QPen(_c(rgb, a), 1.4, Qt.DashLine if dash else Qt.SolidLine)
    pen.setDashOffset(tk * 0.4)
    p.setPen(pen)
    p.drawEllipse(QPointF(x, y), r, r)


def draw_construct(fig, p, st):
    E = st.clone_P
    x, y = fig.transform.x, fig.transform.y
    ps = fig._position_scale()
    R = E["size_px"] * ps
    rgb = U._rgb(E["color"], (124, 243, 255))
    tk = st.t
    life_max = float(max(1, U._ticks(E["life_ms"])))
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    # arrival: summoning circle + pillar, the body fading in
    arr = max(0.0, 1.0 - tk / float(ARRIVE_TICKS))
    if arr > 0:
        _add(p)
        _sigil(p, x, y + R * 0.9, R * (2.2 + 1.0 * (1 - arr)), rgb, 230 * arr, tk * 0.09)
        _pillar(p, x, y + R * 0.9, R * 1.6 * arr, R * 4.5 * (0.5 + 0.5 * arr), rgb, 190 * arr * arr)
        _over(p)
    fade = min(1.0, st.clone_left / float(FADE_TICKS))
    op = min(1.0, 0.25 + tk / 12.0) * (fade if fade >= 1.0 else fade * (0.6 + 0.4 * ((tk // 3) % 2)))
    p.setOpacity(max(0.05, op))
    draw = _DRAW.get(st.construct, _d_turret)
    draw(p, fig, st, E, x, y, R, rgb, tk, ps)
    p.setOpacity(1.0)
    # commander's buff: a golden chevron
    if st.con_buff > 1.0:
        _add(p)
        _poly(p, [(x - R * 0.5, y - R * 2.0), (x, y - R * 2.4), (x + R * 0.5, y - R * 2.0),
                  (x, y - R * 2.2)], _c((255, 214, 102), 220), _c(WHITE, 200), 1.0)
        _over(p)
    pp = fig.personality
    if pp.max_hp:
        U._bar(p, x, y + R * 1.8, 26.0 * ps, pp.hp / float(pp.max_hp), rgb, ps, 2.5)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(_c(rgb, 120), 1.2))
    p.drawArc(QRectF(x - R * 1.35, y - R * 1.35, R * 2.7, R * 2.7), 90 * 16,
              int(360 * 16 * max(0.0, min(1.0, st.clone_left / life_max))))
    if st.flash > 0:
        _add(p)
        k = st.flash / 14.0
        _halo(p, x, y, R * (1.6 + 1.2 * (1 - k)), st.flash_rgb, 200 * k)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_c(WHITE, 230 * k), 2.0))
        p.drawEllipse(QPointF(x, y), R * (1.3 + 1.6 * (1 - k)), R * (1.3 + 1.6 * (1 - k)))
        _over(p)
    p.restore()


def _d_turret(p, fig, st, E, x, y, R, rgb, tk, ps):
    _add(p)
    _halo(p, x, y, R * 2.0, rgb, 90)
    _over(p)
    _poly(p, [(x + math.cos(a) * R * 1.1, y + math.sin(a) * R * 1.1)
              for a in [math.pi / 6 + i * math.pi / 3 for i in range(6)]],
          QColor(18, 22, 30, 235), _c(rgb, 240), 2.0)
    a = st.con_aim
    ca, sa = math.cos(a), math.sin(a)
    pen = QPen(_c(_mix(rgb, WHITE, 0.3), 245), max(2.0, R * 0.42))
    pen.setCapStyle(Qt.FlatCap)
    p.setPen(pen)
    p.drawLine(QPointF(x, y), QPointF(x + ca * R * 1.7, y + sa * R * 1.7))
    _add(p)
    _halo(p, x, y, R * 0.7, rgb, 255)
    if st.con_cd > U._ticks(E["fire_ms"]) - 4:
        _sparkle(p, x + ca * R * 1.9, y + sa * R * 1.9, R * 1.2, rgb, 230, a)
    _over(p)


def _crystal(p, x, y, R, rgb, tk, fill_a=210):
    bob = math.sin(tk * 0.08) * R * 0.15
    pts = [(x, y - R * 1.7 + bob), (x + R * 0.75, y - R * 0.2 + bob), (x, y + R * 1.25 + bob),
           (x - R * 0.75, y - R * 0.2 + bob)]
    _poly(p, pts, _c(rgb, fill_a), _c(WHITE, 220), 1.5)
    p.setPen(QPen(_c(WHITE, 170), 1.0))
    p.drawLine(QPointF(x, y - R * 1.7 + bob), QPointF(x, y + R * 1.25 + bob))
    _add(p)
    _sparkle(p, x - R * 0.25, y - R * 0.9 + bob, R * 0.7, rgb, 150 + 80 * math.sin(tk * 0.2), tk * 0.02)
    _over(p)
    return bob


def _d_totem(p, fig, st, E, x, y, R, rgb, tk, ps):
    pulse = 0.5 + 0.5 * math.sin(tk * 0.12)
    _add(p)
    _aura_ring(p, x, y, E["aura_px"], rgb, 50 + 40 * pulse, tk)
    _halo(p, x, y, R * 2.4, rgb, 90 + 60 * pulse)
    _over(p)
    bob = _crystal(p, x, y, R, rgb, tk)
    p.setPen(QPen(_c(WHITE, 235), 2.0))
    if st.construct == "totem_heal":
        p.drawLine(QPointF(x - R * 0.3, y - R * 0.25 + bob), QPointF(x + R * 0.3, y - R * 0.25 + bob))
        p.drawLine(QPointF(x, y - R * 0.55 + bob), QPointF(x, y + R * 0.05 + bob))
        _links(p, st, x, y, (110, 255, 150), tk, "wave")
    else:
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(x - R * 0.4, y - R * 0.65 + bob, R * 0.8, R * 0.8), 0, 180 * 16)


def _d_familiar(p, fig, st, E, x, y, R, rgb, tk, ps):
    a = st.con_aim
    bob = math.sin(tk * 0.3) * 1.5
    _add(p)
    if fig.motion.style is not None and fig.motion.style.live or st.construct == "familiar":
        _speedlines(p, x, y + bob, a, R * 0.8, rgb, 120, tk // 3)
    _halo(p, x, y + bob, R * 2.0, rgb, 120)
    _over(p)
    # flame-tipped spirit body: a teardrop trailing away from the aim
    ca, sa = math.cos(a), math.sin(a)
    tail = [(x - ca * R * 1.9 + math.sin(tk * 0.4) * R * 0.25 * -sa,
             y + bob - sa * R * 1.9 + math.sin(tk * 0.4) * R * 0.25 * ca),
            (x - sa * R * 0.8, y + bob + ca * R * 0.8), (x + ca * R * 0.9, y + bob + sa * R * 0.9),
            (x + sa * R * 0.8, y + bob - ca * R * 0.8)]
    _poly(p, tail, _c(rgb, 225), _c(WHITE, 150), 1.2)
    for s_ in (-1, 1):
        ex = x + math.cos(a + s_ * 0.5) * R * 0.45
        ey = y + bob + math.sin(a + s_ * 0.5) * R * 0.45
        p.setPen(Qt.NoPen)
        p.setBrush(_c(WHITE, 255))
        p.drawEllipse(QPointF(ex, ey), R * 0.17, R * 0.22)


def _links(p, st, x, y, rgb, tk, kind="bolt", a=220):
    if not st.con_links:
        return
    _add(p)
    for i, (lx, ly) in enumerate(st.con_links):
        if kind == "bolt":
            _bolt(p, x, y, lx, ly, rgb, a, seed=tk // 2 * 31 + i, w=1.6, jag=9.0)
        elif kind == "wave":
            _wave(p, x, y, lx, ly, rgb, a * 0.8, tk * 0.3 + i, w=1.6)
        elif kind == "beam":
            _beam(p, x, y, lx, ly, rgb, a, 3.0)
        elif kind == "chain":
            _chain(p, x, y, lx, ly, rgb, a)
    _over(p)


def _chain(p, x0, y0, x1, y1, rgb, a):
    d = math.hypot(x1 - x0, y1 - y0) or 1.0
    n = max(2, int(d / 12))
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    p.setBrush(Qt.NoBrush)
    for i in range(n):
        t = (i + 0.5) / n
        cx, cy = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        p.save()
        p.translate(cx, cy)
        p.rotate(ang + (90 if i % 2 else 0))
        p.setPen(QPen(_c(rgb, a), 1.6))
        p.drawEllipse(QPointF(0, 0), 5.0, 2.6)
        p.restore()


def _d_spirit_link(p, fig, st, E, x, y, R, rgb, tk, ps):
    _add(p)
    _aura_ring(p, x, y, E["aura_px"], rgb, 60, tk)
    _sigil(p, x, y + R * 1.1, R * 1.8, rgb, 120, tk * 0.04, sides=5)
    _halo(p, x, y, R * 2.2, rgb, 100)
    _over(p)
    # a carved ring-stone with three spirit motes orbiting it
    p.setBrush(QColor(26, 30, 40, 235))
    p.setPen(QPen(_c(rgb, 230), 2.0))
    p.drawEllipse(QPointF(x, y), R * 0.95, R * 1.15)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(_c(_mix(rgb, WHITE, 0.5), 230), 1.4))
    p.drawEllipse(QPointF(x, y), R * 0.45, R * 0.55)
    _add(p)
    for i in range(3):
        a = tk * 0.09 + 2 * math.pi * i / 3
        _halo(p, x + math.cos(a) * R * 1.7, y + math.sin(a) * R * 0.7, R * 0.55, rgb, 230)
    _over(p)
    _links(p, st, x, y, rgb, tk, "wave", 230)


def _d_bell(p, fig, st, E, x, y, R, rgb, tk, ps):
    sw = math.sin(tk * 0.1) * (0.35 if st.flash > 0 else 0.08)
    _add(p)
    _aura_ring(p, x, y, E["aura_px"], rgb, 55, tk)
    _halo(p, x, y, R * 2.2, rgb, 110)
    if st.flash > 0:
        k = st.flash / 14.0
        for j in range(3):
            rr = R * (1.5 + (1 - k) * 4 + j * 0.9)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(_c(_mix(rgb, WHITE, 0.6), 200 * k / (j + 1)), 2.0))
            p.drawEllipse(QPointF(x, y), rr, rr * 0.9)
    _over(p)
    p.save()
    p.translate(x, y - R * 1.2)
    p.rotate(math.degrees(sw))
    path = QPainterPath(QPointF(-R * 0.55, R * 0.45))
    path.cubicTo(QPointF(-R * 0.55, -R * 0.15), QPointF(R * 0.55, -R * 0.15), QPointF(R * 0.55, R * 0.45))
    path.cubicTo(QPointF(R * 0.6, R * 1.3), QPointF(R * 0.8, R * 1.7), QPointF(R * 1.2, R * 2.0))
    path.quadTo(QPointF(0, R * 2.3), QPointF(-R * 1.2, R * 2.0))
    path.cubicTo(QPointF(-R * 0.8, R * 1.7), QPointF(-R * 0.6, R * 1.3), QPointF(-R * 0.55, R * 0.45))
    path.closeSubpath()
    g = QLinearGradient(QPointF(-R, 0), QPointF(R, 0))
    g.setColorAt(0.0, _c(_mix(rgb, (40, 30, 10), 0.4), 240))
    g.setColorAt(0.45, _c(_mix(rgb, WHITE, 0.7), 250))
    g.setColorAt(1.0, _c(_mix(rgb, (40, 30, 10), 0.5), 240))
    p.setBrush(QBrush(g))
    p.setPen(QPen(_c(WHITE, 210), 1.3))
    p.drawPath(path)
    p.setBrush(_c(WHITE, 240))
    p.drawEllipse(QPointF(0, R * 2.2), R * 0.25, R * 0.25)
    p.restore()
    n = max(1, int(E["charges"]))
    for i in range(min(n, 12)):
        on = i < st.con_charges
        px = x + (i - (min(n, 12) - 1) / 2.0) * R * 0.55
        p.setPen(Qt.NoPen)
        p.setBrush(_c(_mix(rgb, WHITE, 0.5) if on else (60, 60, 70), 240 if on else 140))
        p.drawEllipse(QPointF(px, y + R * 1.25), R * 0.16, R * 0.16)
    _links(p, st, x, y, (255, 236, 160), tk, "wave")


def _d_star(p, fig, st, E, x, y, R, rgb, tk, ps):
    grow = min(1.0, st.t / float(max(1, U._ticks(E["mature_ms"]))))
    mature = grow >= 1.0
    _add(p)
    _sigil(p, x, y, E["aura_px"] * (0.35 + 0.65 * grow), rgb, 70 + 90 * grow, tk * 0.02, sides=6, squash=1.0)
    _halo(p, x, y, R * (1.5 + 2.0 * grow), rgb, 110 + 100 * grow)
    n, rot = 6, tk * (0.03 + 0.05 * grow)
    r_out, r_in = R * (0.8 + 1.0 * grow), R * (0.35 + 0.4 * grow)
    pts = []
    for i in range(n * 2):
        a = rot + math.pi * i / n
        rr = r_out if i % 2 == 0 else r_in
        pts.append((x + math.cos(a) * rr, y + math.sin(a) * rr))
    _poly(p, pts, _c(_mix(rgb, WHITE, 0.4 + 0.5 * grow), 230), _c(WHITE, 240), 1.2)
    if mature:
        tw = 0.75 + 0.25 * math.sin(tk * 0.5)
        _sparkle(p, x, y, R * 3.0 * tw, rgb, 200, 0.0)
        _sparkle(p, x, y, R * 1.8 * tw, WHITE, 160, math.pi / 4)
    _over(p)
    _bar(p, x, y - R * 2.6, 22.0 * ps, grow, (255, 255, 255) if mature else rgb, ps)


def _bar(p, x, y, w, frac, rgb, ps):
    U._bar(p, x, y, w, frac, rgb, ps, 2.0)


def _d_grounding(p, fig, st, E, x, y, R, rgb, tk, ps):
    armed = st.con_armed <= 0
    _add(p)
    _aura_ring(p, x, y, E["aura_px"], rgb, 45 if armed else 20, tk)
    _halo(p, x, y - R * 0.6, R * (2.2 if armed else 1.4), rgb, 120 if armed else 60)
    _over(p)
    # a lightning rod: a pole with three tilted rings
    p.setPen(QPen(_c(_mix(rgb, (30, 30, 40), 0.5), 240), max(2.0, R * 0.28)))
    p.drawLine(QPointF(x, y + R * 1.2), QPointF(x, y - R * 1.9))
    p.setBrush(Qt.NoBrush)
    for i in range(3):
        yy = y - R * (1.3 - i * 0.75)
        rr = R * (0.55 + i * 0.22)
        p.setPen(QPen(_c(_mix(rgb, WHITE, 0.4), 230 if armed else 110), 1.8))
        p.drawEllipse(QPointF(x, yy), rr, rr * 0.32)
    _add(p)
    if armed:
        _halo(p, x, y - R * 2.0, R * 0.7, rgb, 255)
        if tk % 9 < 3:
            a = (tk * 1.7) % (2 * math.pi)
            _bolt(p, x, y - R * 2.0, x + math.cos(a) * R * 2.0, y - R * 2.0 + math.sin(a) * R * 2.0,
                  rgb, 200, tk, w=1.0, jag=5.0)
    _over(p)
    if st.con_links and st.flash > 0:
        _links(p, st, x, y - R * 2.0, rgb, tk, "bolt", 255)


def _d_black_ox(p, fig, st, E, x, y, R, rgb, tk, ps):
    red = (255, 70, 60)
    _add(p)
    for j in range(3):   # taunt pulses rolling outward
        k = ((tk + j * 20) % 60) / 60.0
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(_c(red, 160 * (1 - k)), 2.2))
        rr = R * 1.6 + (E["taunt_px"] * 0.35) * k
        p.drawEllipse(QPointF(x, y), rr, rr * 0.85)
    _halo(p, x, y, R * 2.4, rgb, 110)
    _over(p)
    # the effigy: an ox-headed idol, horns sweeping up
    _poly(p, [(x - R * 0.9, y + R * 1.3), (x - R * 0.7, y - R * 0.3), (x, y - R * 0.9),
              (x + R * 0.7, y - R * 0.3), (x + R * 0.9, y + R * 1.3)], QColor(30, 22, 18, 240), _c(rgb, 230), 2.0)
    for s_ in (-1, 1):
        path = QPainterPath(QPointF(x + s_ * R * 0.55, y - R * 0.55))
        path.cubicTo(QPointF(x + s_ * R * 1.6, y - R * 0.6), QPointF(x + s_ * R * 1.7, y - R * 1.4),
                     QPointF(x + s_ * R * 1.2, y - R * 2.0))
        pen = QPen(_c(_mix(rgb, WHITE, 0.5), 240), max(2.0, R * 0.26))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    _add(p)
    for s_ in (-1, 1):
        _halo(p, x + s_ * R * 0.32, y - R * 0.2, R * 0.38, red, 255)
    _over(p)


def _d_soul_link(p, fig, st, E, x, y, R, rgb, tk, ps):
    o = st.clone_of
    if o is not None:
        _add(p)
        _chain(p, x, y, o.transform.x, o.transform.y, _mix(rgb, WHITE, 0.3), 120 + (100 if st.flash > 0 else 0))
        _over(p)
    _d_familiar(p, fig, st, E, x, y, R, rgb, tk, ps)
    _add(p)
    _sparkle(p, x, y - R * 1.5, R * 0.9, rgb, 160 + 80 * math.sin(tk * 0.25), tk * 0.05)
    _over(p)


def _d_commander(p, fig, st, E, x, y, R, rgb, tk, ps):
    gold = (255, 214, 102)
    _add(p)
    _sigil(p, x, y + R * 1.3, R * 2.2, gold, 120, tk * 0.03, sides=8)
    _halo(p, x, y - R, R * 2.6, gold, 100)
    _over(p)
    p.setPen(QPen(QColor(220, 220, 230, 240), max(2.0, R * 0.2)))
    p.drawLine(QPointF(x - R * 0.6, y + R * 1.4), QPointF(x - R * 0.6, y - R * 2.6))
    # the banner, rippling
    pts = []
    n = 8
    for i in range(n + 1):
        t = i / float(n)
        pts.append((x - R * 0.6 + t * R * 1.7, y - R * 2.5 + math.sin(tk * 0.2 - t * 3.0) * R * 0.2 * t))
    pts.append((x + R * 0.85, y - R * 1.75 + math.sin(tk * 0.2 - 3.0) * R * 0.2))   # swallowtail notch
    for i in range(n, -1, -1):
        t = i / float(n)
        pts.append((x - R * 0.6 + t * R * 1.7, y - R * 1.15 + math.sin(tk * 0.2 - t * 3.0) * R * 0.2 * t))
    _poly(p, pts, _c(rgb, 230), _c(gold, 240), 1.6)
    ex, ey = x + R * 0.2, y - R * 1.85 + math.sin(tk * 0.2 - 1.5) * R * 0.1
    _poly(p, [(ex - R * 0.35, ey + R * 0.1), (ex, ey - R * 0.3), (ex + R * 0.35, ey + R * 0.1), (ex, ey - R * 0.05)],
          _c(gold, 240), _c(WHITE, 200), 1.0)
    _add(p)
    _sparkle(p, x - R * 0.6, y - R * 2.7, R * 1.1, gold, 230, tk * 0.04)
    _over(p)


def _d_capacitor(p, fig, st, E, x, y, R, rgb, tk, ps):
    ch = min(1.0, st.con_cycle / float(max(1, U._ticks(E["charge_ms"]))))
    _add(p)
    _aura_ring(p, x, y, E["aura_px"], rgb, 30 + 120 * ch * ch, tk, dash=ch < 0.85)
    _halo(p, x, y - R * 0.8, R * (1.6 + 1.6 * ch), rgb, 80 + 150 * ch)
    _over(p)
    # a tesla coil: base, stacked coils, a bright ball
    _poly(p, [(x - R, y + R * 1.2), (x + R, y + R * 1.2), (x + R * 0.6, y + R * 0.7), (x - R * 0.6, y + R * 0.7)],
          QColor(24, 26, 34, 240), _c(rgb, 200), 1.4)
    for i in range(4):
        yy = y + R * (0.5 - i * 0.45)
        p.setPen(QPen(_c(_mix(rgb, (60, 50, 30), 0.4), 240), 2.2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(x, yy), R * (0.65 - i * 0.07), R * 0.2)
    _add(p)
    _halo(p, x, y - R * 1.4, R * (0.6 + 0.4 * ch), rgb, 255)
    rng = random.Random(tk // 2)
    for i in range(int(1 + 4 * ch)):
        a = rng.uniform(0, 2 * math.pi)
        L = R * rng.uniform(1.2, 2.4 + 2.5 * ch)
        _bolt(p, x, y - R * 1.4, x + math.cos(a) * L, y - R * 1.4 + math.sin(a) * L, rgb, 220, tk + i,
              w=0.9, jag=4.0)
    _over(p)
    _links(p, st, x, y - R * 1.4, rgb, tk, "bolt", 255)


def _d_earthbind(p, fig, st, E, x, y, R, rgb, tk, ps):
    _add(p)
    _sigil(p, x, y, E["aura_px"], rgb, 90, tk * 0.015, sides=4, squash=1.0)
    _halo(p, x, y, R * 2.2, rgb, 100)
    _over(p)
    _poly(p, [(x, y - R * 2.2), (x + R * 0.6, y - R * 0.2), (x + R * 0.45, y + R * 1.3),
              (x - R * 0.45, y + R * 1.3), (x - R * 0.6, y - R * 0.2)],
          QColor(28, 24, 40, 240), _c(rgb, 230), 1.8)
    _add(p)
    for i in range(3):
        _halo(p, x, y - R * (1.4 - i * 0.7), R * 0.25, rgb, 230 * (0.6 + 0.4 * math.sin(tk * 0.15 + i)))
    _over(p)
    _links(p, st, x, y, rgb, tk, "chain", 170)


def _d_hex(p, fig, st, E, x, y, R, rgb, tk, ps):
    _add(p)
    _sigil(p, x, y, E["aura_px"], rgb, 80, -tk * 0.02, sides=5, squash=1.0)
    _halo(p, x, y, R * 2.4, rgb, 110)
    _over(p)
    # an eye sigil: almond with a slit pupil that tracks the enemy
    path = QPainterPath(QPointF(x - R * 1.4, y))
    path.quadTo(QPointF(x, y - R * 1.3), QPointF(x + R * 1.4, y))
    path.quadTo(QPointF(x, y + R * 1.3), QPointF(x - R * 1.4, y))
    p.setBrush(QColor(20, 10, 26, 240))
    p.setPen(QPen(_c(_mix(rgb, WHITE, 0.4), 240), 1.8))
    p.drawPath(path)
    a = st.con_aim
    px, py = x + math.cos(a) * R * 0.35, y + math.sin(a) * R * 0.25
    _add(p)
    _halo(p, px, py, R * 0.75, rgb, 255)
    _over(p)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(10, 0, 10, 250))
    p.drawEllipse(QPointF(px, py), R * 0.12, R * 0.42)
    _links(p, st, x, y, rgb, tk, "wave", 160)


def _d_siphon(p, fig, st, E, x, y, R, rgb, tk, ps):
    _add(p)
    _aura_ring(p, x, y, E["aura_px"], rgb, 55, -tk)
    _halo(p, x, y, R * 2.2, rgb, 110)
    _over(p)
    bob = math.sin(tk * 0.09) * R * 0.15
    pts = [(x, y + R * 1.6 + bob), (x + R * 0.8, y - R * 0.4 + bob), (x + R * 0.35, y - R * 1.3 + bob),
           (x - R * 0.35, y - R * 1.3 + bob), (x - R * 0.8, y - R * 0.4 + bob)]
    _poly(p, pts, _c(_mix(rgb, (20, 0, 10), 0.35), 235), _c(WHITE, 200), 1.4)
    _add(p)
    _halo(p, x, y - R * 0.3 + bob, R * 0.7, rgb, 230)
    # drained life streaming in from each victim
    for i, (lx, ly) in enumerate(st.con_links):
        _wave(p, lx, ly, x, y, rgb, 170, -tk * 0.4 + i, w=1.4, amp=8.0)
        for j in range(3):
            t = ((tk * 0.04 + j / 3.0 + i * 0.13) % 1.0)
            _halo(p, lx + (x - lx) * t, ly + (y - ly) * t, R * 0.35, rgb, 220)
    _over(p)


def _d_imp(p, fig, st, E, x, y, R, rgb, tk, ps):
    r = R * 0.75
    a = st.con_aim
    if st.con_dive > 0:
        fire = (255, 150, 60)
        _add(p)
        _speedlines(p, x, y, a, r * 1.4, fire, 220, tk)
        _halo(p, x, y, r * 2.6, fire, 230)
        _halo(p, x, y, r * 1.2, WHITE, 230)
        _over(p)
        return
    bob = math.sin(tk * 0.35 + fig.index) * 1.5
    _add(p)
    _halo(p, x, y + bob, r * 2.0, rgb, 110)
    _over(p)
    p.setBrush(_c(_mix(rgb, (40, 0, 0), 0.35), 240))
    p.setPen(QPen(_c(WHITE, 150), 1.0))
    p.drawEllipse(QPointF(x, y + bob), r, r * 0.9)
    for s_ in (-1, 1):   # horns and little wings
        _poly(p, [(x + s_ * r * 0.4, y - r * 0.6 + bob), (x + s_ * r * 0.9, y - r * 1.5 + bob),
                  (x + s_ * r * 0.75, y - r * 0.45 + bob)], _c(WHITE, 220), _c(rgb, 200), 0.8)
        flap = math.sin(tk * 0.6) * r * 0.4
        _poly(p, [(x + s_ * r * 0.8, y + bob), (x + s_ * r * 1.9, y - r * 0.5 + bob - flap),
                  (x + s_ * r * 1.6, y + r * 0.4 + bob)], _c(rgb, 170), _c(rgb, 220), 0.8)
    _add(p)
    for s_ in (-1, 1):
        _halo(p, x + math.cos(a + s_ * 0.5) * r * 0.45, y + bob + math.sin(a + s_ * 0.5) * r * 0.4, r * 0.28,
              (255, 230, 120), 255)
    _over(p)


def _d_queen(p, fig, st, E, x, y, R, rgb, tk, ps):
    pw = max(1.0, st.con_power)
    _add(p)
    _halo(p, x, y, R * (2.0 + 0.4 * (pw - 1)), rgb, 110)
    _over(p)
    face = -1 if fig.transform.facing_left else 1
    # torso, armoured skirt, a crown of three spikes, a glowing visor
    _poly(p, [(x - R * 0.7, y - R * 0.6), (x + R * 0.7, y - R * 0.6), (x + R, y + R * 1.3),
              (x - R, y + R * 1.3)], QColor(30, 32, 44, 240), _c(rgb, 230), 1.8)
    _poly(p, [(x - R * 0.5, y - R * 0.6), (x - R * 0.55, y - R * 1.5), (x + R * 0.55, y - R * 1.5),
              (x + R * 0.5, y - R * 0.6)], QColor(220, 222, 232, 245), _c(rgb, 230), 1.4)
    for i, h in ((-1, 0.5), (0, 0.8), (1, 0.5)):
        _poly(p, [(x + i * R * 0.38 - R * 0.14, y - R * 1.5), (x + i * R * 0.38, y - R * (1.5 + h)),
                  (x + i * R * 0.38 + R * 0.14, y - R * 1.5)], _c((255, 214, 102), 240), _c(WHITE, 220), 0.8)
    _add(p)
    p.setPen(QPen(_c(rgb, 255), R * 0.18))
    p.drawLine(QPointF(x - R * 0.35 + face * R * 0.08, y - R * 1.05), QPointF(x + R * 0.35 + face * R * 0.08, y - R * 1.05))
    _halo(p, x, y + R * 0.2, R * 0.6 * pw ** 0.5, rgb, 255)
    a = st.con_aim
    _halo(p, x + math.cos(a) * R * 1.3, y + math.sin(a) * R * 1.3, R * 0.5, rgb, 230)
    _over(p)


def _d_bahamut(p, fig, st, E, x, y, R, rgb, tk, ps):
    flap = math.sin(tk * 0.18)
    _add(p)
    _halo(p, x, y, R * 2.8, rgb, 120)
    _over(p)
    face = -1 if fig.transform.facing_left else 1
    for s_ in (-1, 1):   # great swept wings
        tip_y = y - R * (1.9 + 0.7 * flap)
        _poly(p, [(x + s_ * R * 0.3, y - R * 0.2), (x + s_ * R * 2.6, tip_y), (x + s_ * R * 2.2, y + R * 0.1),
                  (x + s_ * R * 1.6, y - R * 0.2), (x + s_ * R * 1.3, y + R * 0.6)],
              _c(_mix(rgb, (10, 10, 30), 0.45), 230), _c(_mix(rgb, WHITE, 0.4), 230), 1.4)
        p.setPen(QPen(_c(_mix(rgb, WHITE, 0.55), 200), 1.0))
        for tx_, ty_ in ((2.2, 0.1), (1.6, -0.2), (1.3, 0.6)):
            p.drawLine(QPointF(x + s_ * R * 2.6, tip_y), QPointF(x + s_ * R * tx_, y + R * ty_))
    _poly(p, [(x - R * 0.45, y + R * 1.2), (x, y - R * 0.6), (x + R * 0.45, y + R * 1.2)],
          QColor(26, 26, 40, 245), _c(rgb, 230), 1.4)
    hx = x + face * R * 0.35
    _poly(p, [(hx - face * R * 0.3, y - R * 0.5), (hx + face * R * 0.9, y - R * 0.9), (hx - face * R * 0.1, y - R * 1.1)],
          QColor(30, 30, 46, 245), _c(rgb, 230), 1.2)
    _add(p)
    _halo(p, x, y + R * 0.2, R * 0.6, rgb, 255)
    _halo(p, hx + face * R * 0.35, y - R * 0.88, R * 0.2, WHITE, 255)
    _over(p)
    _links(p, st, x, y, rgb, tk, "beam", 255)


def _d_eidolon(p, fig, st, E, x, y, R, rgb, tk, ps):
    a = st.con_aim
    _add(p)
    for j in range(3):   # afterimages trailing behind
        k = (j + 1) / 4.0
        gx, gy = x - math.cos(a) * R * 1.2 * (j + 1), y - math.sin(a) * R * 1.2 * (j + 1)
        _halo(p, gx, gy, R * (1.6 - 0.3 * j), rgb, 80 * (1 - k))
    _halo(p, x, y, R * 2.3, rgb, 130)
    _over(p)
    fl = math.sin(tk * 0.25) * R * 0.3
    for s_ in (-1, 1):
        _poly(p, [(x, y - R * 0.3), (x + s_ * R * 2.0, y - R * 1.6 - fl), (x + s_ * R * 1.4, y + R * 0.2)],
              _c(_mix(rgb, WHITE, 0.55), 150), _c(WHITE, 200), 1.0)
    _poly(p, [(x, y - R * 1.4), (x + R * 0.55, y), (x, y + R * 1.5), (x - R * 0.55, y)],
          _c(_mix(rgb, WHITE, 0.4), 200), _c(WHITE, 240), 1.4)
    _add(p)
    _sparkle(p, x, y - R * 0.2, R * 1.2, rgb, 230, tk * 0.06)
    _over(p)


_DRAW = {
    "turret": _d_turret, "totem_heal": _d_totem, "totem_shield": _d_totem, "familiar": _d_familiar,
    "spirit_link": _d_spirit_link, "liturgy_bell": _d_bell, "earthly_star": _d_star,
    "grounding": _d_grounding, "black_ox": _d_black_ox, "soul_link": _d_soul_link,
    "commander": _d_commander, "capacitor": _d_capacitor, "earthbind": _d_earthbind,
    "hex_ward": _d_hex, "siphon": _d_siphon, "imp_swarm": _d_imp,
    "automaton_queen": _d_queen, "demi_bahamut": _d_bahamut, "trance_eidolon": _d_eidolon,
}


def draw_owner(fig, p, st, pscale=1.0):
    """unique.draw: strikes and finishers drawn from the summoner's list
    (Trance Eidolon echoes, Earthly Star detonations, Queen / Bahamut
    finishers)."""
    if not st.sm_flashes:
        return
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    _add(p)
    for f in st.sm_flashes:
        x, y, a, age, life, rgb, kind = f[0], f[1], f[2], f[3], f[4], f[5], f[6]
        k = 1.0 - age / float(max(1, life))
        if kind is True:        # eidolon slash: a crescent cut with speed lines
            R = 26.0 * pscale
            path = QPainterPath()
            rect = QRectF(x - R, y - R, 2 * R, 2 * R)
            start = -math.degrees(a) - 70
            path.arcMoveTo(rect, start)
            path.arcTo(rect, start, 140)
            inner = QRectF(x - R * 0.7, y - R * 0.6, 1.4 * R, 1.2 * R)
            path.arcTo(inner, start + 140, -140)
            path.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(_c(_mix(rgb, WHITE, 0.6), 240 * k))
            p.drawPath(path)
            _halo(p, x, y, R * 1.4, rgb, 180 * k)
            _speedlines(p, x, y, a, R * 0.6, rgb, 200 * k, int(x + y))
        elif kind == "star":    # earthly star detonation: a white nova
            r = f[7] * (0.4 + 0.6 * (1 - k))
            _halo(p, x, y, r, rgb, 230 * k, core=0.3)
            _sparkle(p, x, y, r * 1.1, WHITE, 240 * k, age * 0.05)
        elif kind == "flare":   # queen / bahamut finisher: beam + blast
            tx, ty, r = f[7], f[8], f[9]
            _beam(p, x, y, tx, ty, rgb, 255 * k, 7.0 * pscale * (0.5 + k))
            _halo(p, tx, ty, r * (0.5 + 0.7 * (1 - k)), rgb, 255 * k, core=0.3)
            _sparkle(p, tx, ty, r * 0.9, WHITE, 230 * k, 0.3)
    _over(p)
    p.restore()
