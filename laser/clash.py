"""
Clash interaction — what happens when two opposing effects touch.

Every tick (Overlay._tick, before World.refresh_battle) the live effects of
the two sides are reduced to bodies — a point, a line or a polyline with a
half width — in five categories:

  beam      FX Kit beam prim; built-in rich beams (RichBeamProjectile)
  orb       FX Kit orb sprites; mage petals; round / homing bullets
  trail     FX Kit ribbons (blade / laser trails); the built-in laser trail
            (its head part only: the end that is moving)
  crescent  FX Kit arc prim; swordsman crescents and ultimate crescents
  sprite    FX Kit bolt / blade sprites; the runner's bolts and other shots
  (ghost, glow, pulse, particles and weapon never clash)

When a body of one side touches a body of the other, the rule for their two
categories plays out (RULES; Daniel's clash table).  Pairs without a rule
pass through each other.

  beam x beam         both damage over 10: they explode (beam_clash);
                      otherwise they lock in a struggle (beam_struggle) for
                      STRUGGLE_TICKS, then the winner blows through
                      (overpower_blowout)
  beam x orb          the orb is held on the beam head (beam_orb), then bursts
  beam x trail / crescent / sprite
                      SPLIT_CHANCE: the beam splits at the contact into two
                      halves fanning +-SPLIT_DEG that run on to the beam's end
                      (both can hit) and explode there (split_burst);
                      otherwise the beam carries on as normal.  Either way the
                      cutter is settled by the knockback rule against the beam
                      (a beam is never cancelled by a cutter)
  orb x orb           little blasts popping (orb_pops)
  trail x trail       a sword-slash clash (sword_slash_clash)
  crescent x crescent the two blades grind (crescent_struggle), then shatter
  sprite x sprite     a kunai clash (kunai_clash)

Knockback rule: the effect with the higher battle knockback survives at full
power and the other is cancelled; a tie cancels both.  A trail cannot be
cancelled (it is on the fighter): its owner recoils instead, by the
knockback difference (a tie pushes both owners back a little).

While a sustained clash holds, both effects are pinned where they met.  Each
fighter involved shows its Rig Forge "clash" action (if it has one) for the
clash's length or the fixed time set in FX Studio's Clash panel
(pack.clash.anim, fxkit.normalize_clash), standing still when "freeze" is
on; the FX built on that action play with it.  Which clash FX plays for each
rule (and its size / density) comes from the Clash panel of the winning
side's character (the first side's on a tie); built-in characters use the
defaults.

One code path for Solo and Battle: clashes need two fielded sides, so Solo
(the cursor is the only opponent) simply never finds a pair.
"""

import copy
import math
import random

from . import clashfx, config, fxkit

CONTACT_MARGIN = 4.0         # px of slack on top of both half widths
STRONG_BEAM_DAMAGE = 10.0    # beam x beam explodes when BOTH deal more than this
STRUGGLE_TICKS = 90          # beam struggle length (~1.4 s)
BEAM_ORB_TICKS = 18          # how long the orb is held on the beam head
CRESCENT_TICKS = 48          # crescent struggle length
SPLIT_CHANCE = 0.5
SPLIT_DEG = 30.0
SPLIT_HELD_TICKS = 26        # a held beam's split halves grow out and burn this long
TRAIL_HEAD_POINTS = 8        # how much of a trail (from its moving end) can clash
REARM_TICKS = 20             # a pair can clash again after this long apart
TIE_RECOIL_KB = 6.0          # trail x trail tie: both owners pushed back this much
MAX_TIP_WATCH = 32

# category pair (sorted) -> rule name
RULES = {
    ("beam", "beam"): "beam_beam",
    ("beam", "orb"): "beam_orb",
    ("beam", "trail"): "beam_cut",
    ("beam", "crescent"): "beam_cut",
    ("beam", "sprite"): "beam_cut",
    ("orb", "orb"): "orb_orb",
    ("trail", "trail"): "trail_trail",
    ("crescent", "crescent"): "crescent_crescent",
    ("sprite", "sprite"): "sprite_sprite",
}


# ---------------------------------------------------------------- bodies
class Body:
    """One clashable effect of one side, as of this tick."""
    __slots__ = ("side", "cat", "kind", "ref", "owner", "pts", "hw", "damage", "kb", "col", "dir", "box", "lst")

    def __init__(self, side, cat, kind, ref, owner, pts, hw, damage, kb, col, d=(1.0, 0.0), lst=None):
        self.side, self.cat, self.kind, self.ref, self.owner = side, cat, kind, ref, owner
        self.pts, self.hw = pts, max(0.0, float(hw))
        self.damage, self.kb = float(damage or 0.0), float(kb or 0.0)
        self.col = tuple(int(max(0, min(255, v))) for v in col[:3])
        self.dir, self.lst = d, lst
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        h = self.hw + CONTACT_MARGIN
        self.box = (min(xs) - h, min(ys) - h, max(xs) + h, max(ys) + h)


def _lut_col(fig):
    try:
        return tuple(fig.lut[128])
    except (AttributeError, IndexError, TypeError):
        return (255, 255, 255)


def _norm(dx, dy):
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1e-6 else (1.0, 0.0)


def _inst_body(si, fig, inst, lst):
    if inst.dead or inst.age >= inst.life or inst.lodge is not None:
        return None
    fx, P = inst.fx, inst.fx["params"]
    prim = fx["prim"]
    b = fx["battle"]
    dmg, kb = float(b.get("damage") or 0), fxkit.fx_knockback(fx)
    try:
        col = fxkit.color_pair(fx, fig.lut)[0]
    except Exception:
        col = _lut_col(fig)
    ps = inst.ps
    if prim == "beam":
        hx, hy, ux, uy, reach = fxkit.beam_reach(inst, ps)
        if reach <= 0.5:
            return None
        hw = max(P["w_start0"], P["w_start1"], P["w_end0"], P["w_end1"]) * ps / 2
        return Body(si, "beam", "inst", inst, fig, [(hx, hy), (hx - ux * reach, hy - uy * reach)], hw, dmg, kb, col,
                    (ux, uy), lst)
    if prim == "sprite":
        cat = "orb" if P.get("shape") == "orb" else "sprite"
        hw = max(5.0, float(P.get("radius") or 3) * ps * max(1.0, float(P.get("stretch") or 1)))
        return Body(si, cat, "inst", inst, fig, [(inst.x, inst.y)], hw, dmg, kb, col,
                    _norm(inst.vx, inst.vy), lst)
    if prim == "ribbon":
        h = inst.hist[-TRAIL_HEAD_POINTS:]
        if len(h) < 2:
            return None
        hw = max(3.0, float(P.get("w_head") or 5) * ps / 2)
        return Body(si, "trail", "inst", inst, fig, list(h), hw, dmg, kb, col, _norm(h[-1][0] - h[-2][0],
                                                                                       h[-1][1] - h[-2][1]), lst)
    if prim == "arc":
        R = float(P["radius"]) * ps
        pts = []
        for q in fxkit.arc_segs(inst, ps):
            a = math.radians(q[0] + q[1] / 2.0)
            pts.append((inst.x + R * math.cos(a), inst.y - R * math.sin(a)))
        if len(pts) < 2:
            return None
        return Body(si, "crescent", "inst", inst, fig, pts, float(P["width"]) * ps / 2, dmg, kb, col,
                    _norm(inst.vx, inst.vy), lst)
    return None


def _arc_pts(cx, cy, R, centre_deg, span, n=7):
    out = []
    for i in range(n):
        a = math.radians(centre_deg - span / 2.0 + span * i / (n - 1))
        out.append((cx + R * math.cos(a), cy - R * math.sin(a)))
    return out


def _bodies(world, si):
    from . import combat
    side = world.sides[si]
    out = []
    for fig in side.figures:
        drv = getattr(fig, "fx", None)
        if drv is not None:
            for pl in [drv.player] + [ln[0] for ln in drv.rlanes]:
                for inst in pl.insts:
                    b = _inst_body(si, fig, inst, pl.insts)
                    if b is not None:
                        out.append(b)
        c = fig.combat
        lc = _lut_col(fig)
        for cw in c.crescents:
            if cw.alive:
                R = config.CRESCENT_RADIUS * (1.0 if cw.scale is None else float(cw.scale))
                out.append(Body(si, "crescent", "crescent", cw, fig,
                                _arc_pts(cw.x, cw.y, R, cw.centre_angle_deg, config.CRESCENT_SPAN),
                                config.CRESCENT_WIDTH / 2 + 2, 1.0, 0.0, cw.color_rgb or lc,
                                (cw.dir_x, cw.dir_y), c.crescents))
        for uc in c.ult_crescents:
            if uc.alive:
                cfg = uc.cfg
                out.append(Body(si, "crescent", "ultc", uc, fig,
                                _arc_pts(uc.x, uc.y, cfg["radius"], uc.centre_angle_deg, cfg["span"]),
                                cfg["width_outer"] / 2, 1.0, 0.0, lc, (uc.dir_x, uc.dir_y), c.ult_crescents))
        for pt in c.petals:
            if pt.state != "cooldown":
                cfg = pt.cfg or {}
                out.append(Body(si, "orb", "petal", pt, fig, [(pt.x, pt.y)], float(cfg.get("radius", 8.0) or 8.0) + 2,
                                float(cfg.get("damage", 1) or 0), 0.0, lc, (1.0, 0.0), c.petals))
        tr = getattr(getattr(fig, "trail", None), "trail", None)
        if tr is not None and len(tr) >= 2 and config.TRAIL_ENABLED:
            h = list(tr)[-TRAIL_HEAD_POINTS:]
            if h[-1] != h[0]:
                out.append(Body(si, "trail", "trail", fig.trail, fig, h, 4.0, 0.0, 0.0, lc,
                                _norm(h[-1][0] - h[-2][0], h[-1][1] - h[-2][1]), None))
    for pr in side.projectiles:
        if not pr.alive or pr.hit_r_sq <= 0.0:
            continue
        owner = pr.owner if pr.owner is not None else (side.figures[0] if side.figures else None)
        if owner is None:
            continue
        col = (pr.r, pr.g, pr.b)
        if isinstance(pr, combat.RichBeamProjectile):
            spd = math.hypot(pr.vx, pr.vy)
            if spd < 1e-4:
                continue
            ux, uy = pr.vx / spd, pr.vy / spd
            reach = _rich_reach(pr, spd)
            if reach <= 0.5:
                continue
            hw = max(pr.w_start0, pr.w_start1, pr.w_end0, pr.w_end1) / 2
            out.append(Body(si, "beam", "proj", pr, owner, [(pr.x, pr.y), (pr.x - ux * reach, pr.y - uy * reach)],
                            hw, pr.damage, pr.knockback_px, col, (ux, uy), side.projectiles))
            continue
        cat = "orb" if pr.style in (None, "homing") else "sprite"
        out.append(Body(si, cat, "proj", pr, owner, [(pr.x, pr.y)], max(4.0, pr.radius * 1.5), pr.damage,
                        pr.knockback_px, col, _norm(pr.vx, pr.vy), side.projectiles))
    return out


def _rich_reach(pr, spd):
    dist = spd * pr.age
    if pr.age < pr.detach_ticks:
        return min(pr.length, dist)
    rd = min(pr.length, spd * pr.detach_ticks)
    post = max(1, pr.max_age - pr.detach_ticks)
    return max(0.0, rd * (1.0 - min(1.0, (pr.age - pr.detach_ticks) / post)))


# ---------------------------------------------------------------- geometry
def _closest(p0, p1, q0, q1):
    """Closest points of segments p0p1 and q0q1: (distance, midpoint)."""
    d1x, d1y = p1[0] - p0[0], p1[1] - p0[1]
    d2x, d2y = q1[0] - q0[0], q1[1] - q0[1]
    rx, ry = p0[0] - q0[0], p0[1] - q0[1]
    a = d1x * d1x + d1y * d1y
    e = d2x * d2x + d2y * d2y
    f = d2x * rx + d2y * ry
    if a <= 1e-9 and e <= 1e-9:
        s = t = 0.0
    elif a <= 1e-9:
        s, t = 0.0, max(0.0, min(1.0, f / e))
    else:
        c = d1x * rx + d1y * ry
        if e <= 1e-9:
            t, s = 0.0, max(0.0, min(1.0, -c / a))
        else:
            b = d1x * d2x + d1y * d2y
            den = a * e - b * b
            s = max(0.0, min(1.0, (b * f - c * e) / den)) if den > 1e-9 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, max(0.0, min(1.0, -c / a))
            elif t > 1.0:
                t, s = 1.0, max(0.0, min(1.0, (b - c) / a))
    cx1, cy1 = p0[0] + d1x * s, p0[1] + d1y * s
    cx2, cy2 = q0[0] + d2x * t, q0[1] + d2y * t
    return math.hypot(cx1 - cx2, cy1 - cy2), ((cx1 + cx2) / 2, (cy1 + cy2) / 2)


def _segs(pts):
    if len(pts) == 1:
        return [(pts[0], pts[0])]
    return [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]


def contact(a, b):
    """Contact point of two bodies, or None when they don't touch."""
    if a.box[2] < b.box[0] or b.box[2] < a.box[0] or a.box[3] < b.box[1] or b.box[3] < a.box[1]:
        return None
    lim = a.hw + b.hw + CONTACT_MARGIN
    best = None
    for p0, p1 in _segs(a.pts):
        for q0, q1 in _segs(b.pts):
            d, c = _closest(p0, p1, q0, q1)
            if d <= lim and (best is None or d < best[0]):
                best = (d, c)
    return None if best is None else best[1]


# ---------------------------------------------------------------- object control
def _alive(b):
    r, k = b.ref, b.kind
    if k == "inst":
        return not r.dead and r.age < r.life
    if k == "petal":
        return r.state != "cooldown"
    if k == "trail":
        return True
    return bool(r.alive)


def _cancel(b):
    from . import combat
    r, k = b.ref, b.kind
    if k == "inst":
        r.age = max(r.age, r.life)
        r.dead = True
    elif k == "proj":
        combat.kill_projectile(r)
    elif k == "crescent":
        r.age = config.CRESCENT_LIFETIME
    elif k == "ultc":
        r.age = r.cfg["lifetime"]
    elif k == "petal":
        r.state = "cooldown"
        r.cooldown_ticks = max(1, int(float((r.cfg or {}).get("cooldown_ms", 2500)) / config.TICK_MS))


def _pin(b):
    r = b.ref
    if b.kind in ("trail",):
        return None
    pin = [r.x, r.y, getattr(r, "age", 0)]
    return pin


def _hold(b, pin):
    """Keep a pinned effect where it met (and its age where it was)."""
    if pin is None:
        return
    r = b.ref
    r.x, r.y = pin[0], pin[1]
    if b.kind == "inst":
        r.px, r.py = pin[0], pin[1]
        r.age = pin[2]
    elif b.kind in ("proj", "crescent", "ultc"):
        r.age = pin[2]


def _recoil(world, fig, cx, cy, kb):
    from . import ai
    if fig is None or kb <= 0:
        return
    m = fig.motion
    if m.bouncing or m.bounce_ending or ai.knockback_immune(fig, world):
        return
    dx, dy = _norm(fig.x - cx, fig.y - cy)
    spd = kb * (1.0 - config.BOUNCE_FRICTION)
    m.bounce_vx, m.bounce_vy = dx * spd, dy * spd
    m.bouncing = True


def _settle(world, a, b, c, exempt=None):
    """Knockback rule.  Returns the winner (None on a tie).  `exempt` is
    never cancelled (a beam against its cutter)."""
    if abs(a.kb - b.kb) < 1e-6:
        losers, winner = [a, b], None
    elif a.kb > b.kb:
        losers, winner = [b], a
    else:
        losers, winner = [a], b
    for l in losers:
        if l is exempt:
            continue
        other = b if l is a else a
        if l.cat == "trail":
            _recoil(world, l.owner, c[0], c[1], max(TIE_RECOIL_KB, other.kb - l.kb) if winner is None
                    else other.kb - l.kb)
        else:
            _cancel(l)
    return winner


# ---------------------------------------------------------------- settings / fx
def settings_for(fig):
    cfx = fxkit.character_fx(fig.mode) if fig is not None else None
    return cfx.clash if cfx is not None else fxkit.normalize_clash({})


def _spawn_fx(world, slot, fig, c, angle, c1, c2, hold=None, winner=0):
    cfg = settings_for(fig)["slots"].get(slot) or {}
    key = cfg.get("fx") or ""
    if key == "none":
        return None
    if key not in clashfx.BASES and key not in clashfx.VARIANTS:
        key = dict((s[0], s[1]) for s in fxkit.CLASH_SLOTS).get(slot, "collision_nova")
    # Position scale is applied when it is drawn (clashfx.draw_all).
    return clashfx.spawn(world, key, c[0], c[1], angle=angle, c1=c1, c2=c2,
                         scale=float(cfg.get("size", 100)) / 100.0, hold=hold, winner=winner,
                         density=float(cfg.get("density", 100)) / 100.0)


def _engage(world, figs, ticks):
    """Each fighter shows its Rig Forge "clash" action (pack.clash.anim)."""
    from . import actions
    now = world.global_tick
    for fig in figs:
        if fig is None:
            continue
        an = settings_for(fig)["anim"]
        n = ticks if an["hold"] == "clash" else int(round(an["hold_ms"] / config.TICK_MS))
        if n > 0:
            actions.force_clash(fig, world, now + n, an["freeze"])


def _deg(dx, dy):
    return math.degrees(math.atan2(dy, dx))


# ---------------------------------------------------------------- beam split
def _split_beam(world, st, beam, c):
    """Replace the part of `beam` beyond the contact with two halves fanning
    +-SPLIT_DEG that run on to the beam's end and can hit; each explodes
    where it ends.  Returns the halves."""
    head = beam.pts[0]
    ux, uy = beam.dir
    rem = math.hypot(head[0] - c[0], head[1] - c[1])
    halves = []
    if beam.kind == "inst":
        inst = beam.ref
        m = inst.fx["motion"]
        held = m["kind"] in ("attached", "static", "orbit") or math.hypot(inst.vx, inst.vy) < 1e-4
        rem = max(rem, 40.0 * inst.ps)
        for sgn in (1, -1):
            d = fxkit.rot([ux, uy], SPLIT_DEG * sgn)
            q = _half_inst(inst, d, c, rem, held)
            beam.lst.append(q)
            halves.append(("inst", q, beam.owner))
        if held:
            tail = beam.pts[1]
            inst.cap = max(0.0, math.hypot(c[0] - tail[0], c[1] - tail[1]))
            inst.life = min(inst.life, inst.age + SPLIT_HELD_TICKS)
        else:
            _cancel(beam)
    else:
        pr = beam.ref
        spd = math.hypot(pr.vx, pr.vy)
        rem = max(rem, 40.0)
        for sgn in (1, -1):
            d = fxkit.rot([ux, uy], SPLIT_DEG * sgn)
            q = copy.copy(pr)
            q.trail = type(pr.trail)(maxlen=pr.trail.maxlen)
            q.x, q.y = c[0], c[1]
            q.vx, q.vy = d[0] * spd, d[1] * spd
            q.age = 0
            q.length = rem
            q.max_age = max(8, int(rem / max(1e-3, spd)) + 8)
            q.detach_ticks = 10 ** 9
            beam.lst.append(q)
            halves.append(("proj", q, beam.owner))
        _cancel(beam)
    for h in halves:
        st["halves"].add(id(h[1]))
        if len(st["tips"]) < MAX_TIP_WATCH:
            st["tips"].append([h[0], h[1], h[2], beam.col, (c[0], c[1])])
    return halves


def _half_inst(inst, d, c, rem, held):
    fx = copy.deepcopy(inst.fx)
    fx["keys"] = []
    fx.setdefault("intercept", {})["enabled"] = False
    P = fx["params"]
    P["length"] = rem / max(1e-6, inst.ps)
    P["detach_ticks"] = 0
    q = copy.copy(inst)
    q.fx = fx
    q.src = fx
    q.r = fxkit.Rng((inst.seed ^ (0x9E3779B9 if d[1] > 0 else 0x7F4A7C15)) & fxkit.M32)
    q.hist, q.trail, q.parts, q.ghosts = [], [], [], []
    q.x, q.y, q.px, q.py = c[0], c[1], c[0], c[1]
    q.dir = [d[0], d[1]]
    q.age = 0
    q.hits, q.last_hit = 0, -1e9
    q.free = q.chase = q.cont = q.open = q.run = False
    q.clash_with = None
    q.lodge = None
    q.path = None
    q.cap = None
    q.ring_hits = None
    if held:
        fx["motion"]["kind"] = "static"
        P["grow_ticks"] = 6
        q.vx = q.vy = 0.0
        q.life = SPLIT_HELD_TICKS
    else:
        fx["motion"]["kind"] = "travel"
        spd = math.hypot(inst.vx, inst.vy)
        q.vx, q.vy = d[0] * spd, d[1] * spd
        q.life = max(8, int(rem / max(1e-3, spd)) + 8)
    q.mk, q.ma = fx["motion"]["kind"], fx["motion"]["aim"]
    return q


def _tip_pos(kind, obj):
    if kind == "inst":
        hx, hy, _ux, _uy, reach = fxkit.beam_reach(obj, obj.ps)
        return (hx, hy) if reach > 0 else (obj.x, obj.y)
    return (obj.x, obj.y)


def _tip_alive(kind, obj):
    return (not obj.dead and obj.age < obj.life) if kind == "inst" else obj.alive


# ---------------------------------------------------------------- the clash record
class Clash:
    """A clash that holds for a while (struggles, the orb on the beam head)."""
    __slots__ = ("a", "b", "c", "rule", "until", "pins", "fx", "start")

    def __init__(self, a, b, c, rule, until, fx, start):
        self.a, self.b, self.c, self.rule, self.until, self.fx, self.start = a, b, c, rule, until, fx, start
        self.pins = (_pin(a), _pin(b))


def _state(world):
    st = getattr(world, "clash_state", None)
    if st is None:
        st = world.clash_state = {"active": [], "busy": set(), "seen": {}, "tips": [],
                                  "rng": random.Random(), "halves": set()}
    return st


def _key(a, b):
    return (id(a.ref), id(b.ref)) if a.side == 0 else (id(b.ref), id(a.ref))


def _start(world, st, a, b, c, rule, now):
    """a is side 0's body, b side 1's.  Plays the rule; returns the Clash
    record for a clash that holds (both effects pinned), else None."""
    rng = st["rng"]
    if rule == "beam_cut" and a.cat != "beam":
        a, b = b, a     # the beam first
    if rule == "beam_orb" and a.cat != "beam":
        a, b = b, a
    ang = _deg(*_norm((b.owner.x if b.owner else c[0] + 1) - (a.owner.x if a.owner else c[0]),
                      (b.owner.y if b.owner else c[1]) - (a.owner.y if a.owner else c[1])))
    figs = (a.owner, b.owner)
    if rule == "beam_beam":
        if a.damage > STRONG_BEAM_DAMAGE and b.damage > STRONG_BEAM_DAMAGE:
            w = _settle(world, a, b, c)
            fx = _spawn_fx(world, "beam_explode", (w or a).owner, c, _deg(*a.dir), a.col, b.col)
            _engage(world, figs, fx.life if fx else 40)
            return None
        fx = _spawn_fx(world, "beam_struggle", a.owner, c, _deg(*a.dir), a.col, b.col, hold=STRUGGLE_TICKS)
        _engage(world, figs, STRUGGLE_TICKS)
        return Clash(a, b, c, rule, now + STRUGGLE_TICKS, fx, now)
    if rule == "beam_orb":
        fx = _spawn_fx(world, "beam_orb", a.owner, c, _deg(*a.dir), a.col, b.col)
        _engage(world, figs, BEAM_ORB_TICKS + 20)
        return Clash(a, b, c, rule, now + BEAM_ORB_TICKS, fx, now)
    if rule == "beam_cut":
        w = _settle(world, a, b, c, exempt=a)   # the beam itself is never cancelled by its cutter
        f_fig = (w or a).owner
        # A split half never splits again (no cascade): it is just cut.
        if id(a.ref) not in st["halves"] and rng.random() < SPLIT_CHANCE:
            _spawn_fx(world, "beam_split", f_fig, c, _deg(*a.dir), a.col, b.col)
            _split_beam(world, st, a, c)
        else:
            _spawn_fx(world, "beam_nosplit", f_fig, c, _deg(*a.dir), a.col, b.col)
        _engage(world, figs, 30)
        return None
    if rule == "crescent_crescent":
        fx = _spawn_fx(world, "crescent_crescent", a.owner, c, ang, a.col, b.col, hold=CRESCENT_TICKS)
        _engage(world, figs, CRESCENT_TICKS + 20)
        return Clash(a, b, c, rule, now + CRESCENT_TICKS, fx, now)
    slot = {"orb_orb": "orb_orb", "trail_trail": "trail_trail", "sprite_sprite": "sprite_sprite"}[rule]
    w = _settle(world, a, b, c)
    fx = _spawn_fx(world, slot, (w or a).owner, c, ang, a.col, b.col)
    _engage(world, figs, fx.life if fx else 30)
    return None


def _finish(world, st, rec):
    """A held clash ends: the knockback rule decides it."""
    a, b, c = rec.a, rec.b, rec.c
    la, lb = _alive(a), _alive(b)
    if la and lb:
        w = _settle(world, a, b, c)
        if rec.rule == "beam_beam" and w is not None:
            ang = _deg(*a.dir)
            _spawn_fx(world, "beam_struggle_end", w.owner, c, ang, a.col, b.col, winner=0 if w is a else 1)
    if rec.fx is not None and rec.fx.phase == "hold":
        rec.fx.release()
    st["busy"].discard(id(a.ref))
    st["busy"].discard(id(b.ref))


# ---------------------------------------------------------------- per tick
def step(world):
    """Once per tick, before World.refresh_battle (Overlay._tick)."""
    st = _state(world)
    now = world.global_tick
    # 1. Held clashes: keep both pinned; end on time, or early when one of
    #    the two is gone (taken out by something else).
    live = []
    for rec in st["active"]:
        if now >= rec.until or not (_alive(rec.a) and _alive(rec.b)):
            _finish(world, st, rec)
            continue
        _hold(rec.a, rec.pins[0])
        _hold(rec.b, rec.pins[1])
        live.append(rec)
    st["active"] = live
    # 2. Split halves: each explodes where it ends.
    tips = []
    for t in st["tips"]:
        kind, obj, owner, col, _last = t
        if _tip_alive(kind, obj):
            t[4] = _tip_pos(kind, obj)
            tips.append(t)
        else:
            st["halves"].discard(id(obj))
            p = t[4]
            ang = _deg(*_norm(p[0] - (owner.x if owner else p[0] - 1), p[1] - (owner.y if owner else p[1])))
            _spawn_fx(world, "split_tip", owner, p, ang, col, col)
    st["tips"] = tips
    # 3. New contacts (two fielded sides only: Solo never has a pair).
    if len(world.sides) < 2 or not (world.sides[0].figures and world.sides[1].figures):
        st["seen"].clear()
        return
    A, B = _bodies(world, 0), _bodies(world, 1)
    if not A or not B:
        return
    busy, seen = st["busy"], st["seen"]
    for a in A:
        if id(a.ref) in busy:
            continue
        for b in B:
            if id(b.ref) in busy or id(a.ref) in busy:
                continue
            rule = RULES.get(tuple(sorted((a.cat, b.cat))))
            if rule is None:
                continue
            c = contact(a, b)
            if c is None:
                continue
            k = _key(a, b)
            last = seen.get(k)
            seen[k] = now
            if last is not None and now - last <= REARM_TICKS:
                continue    # still touching since its last clash
            rec = _start(world, st, a, b, c, rule, now)
            if rec is not None:
                st["active"].append(rec)
                busy.add(id(a.ref))
                busy.add(id(b.ref))
    # forget pairs apart for a while
    if len(seen) > 256 or now % 60 == 0:
        for k in [k for k, t in seen.items() if now - t > REARM_TICKS * 3]:
            del seen[k]
