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

Clashing is world physics, not a character choice: every fighter's
effects are bound by the same rules.  When a body of one side touches a
body of the other, the rule for their two categories plays out (RULES;
Daniel's clash table) and the clash FX for that pair plays (WORLD_SLOTS).
Every pair of categories has a rule.

  beam x beam         both damage over 10: they explode (beam_clash);
                      otherwise they lock in a struggle (beam_struggle) for
                      STRUGGLE_TICKS, then the winner blows through
                      (overpower_blowout).  The struggle FX is anchored to
                      the two real beams: it draws each beam from its origin
                      (locked when the clash starts) to the node at its real
                      width, the real beams are hidden meanwhile, and the
                      node is pushed toward the loser's origin; the blowout
                      fires where the node ends up
  beam x orb          the orb is held on the beam head (beam_orb), then bursts
  beam x trail / crescent / sprite
                      SPLIT_CHANCE: the beam splits at the contact into two
                      halves fanning +-SPLIT_DEG that run on to the beam's end
                      (both can hit) and explode there (split_burst);
                      otherwise the beam carries on as normal.  Either way the
                      cutter is settled by the knockback rule against the beam
                      (a beam is never cancelled by a cutter)
  orb x orb           little blasts popping (orb_pops)
  trail x trail       a sword duel (sword_duel): the two fighters are moved
                      by the clash (clashfx.duel_plan, duel_tick) — they
                      dash in, their blades meet, they spring apart, and it
                      ends on one big clash, back where they started; the
                      knockback rule then settles it.  The FX is anchored
                      to their real positions every tick.  A pair that has
                      just duelled (DUEL_REARM_TICKS), or a Clash panel FX
                      other than a sword duel, plays a one-shot burst instead
  crescent x crescent the two blades grind (crescent_struggle), then shatter
  sprite x sprite     a kunai clash (kunai_clash)
  orb x trail         sword_slash_clash      orb x crescent      getsuga_cross
  orb x sprite        collision_nova         trail x crescent    sword_slash_clash
  trail x sprite      kunai_clash            crescent x sprite   getsuga_cross
                      (one-shot bursts; the knockback rule settles them)

Knockback rule: the effect with the higher battle knockback survives at full
power and the other is cancelled; a tie cancels both.  A trail cannot be
cancelled (it is on the fighter): its owner recoils instead, by the
knockback difference (a tie pushes both owners back a little).

Clash length (_budget): a clash lasts no longer than the shorter REMAINING
life of the two effects at contact, and never less than min_ticks.  An
effect with no lifespan (a fighter's own sword trail, a hovering petal, an
FX with endless life) leaves it to the other one; when neither has one the
clash FX plays at its normal length.  A clash FX longer than that budget
plays faster so its whole loop fits (ClashFX.fit); a held clash (struggle,
the orb on the beam head) holds for the fitted share of its hold, and a
sword duel that cannot fit plays the one-shot sword_slash_clash instead.

Clash size (_pair_size): base = the larger of the slot's size % (the floor)
and the two effects' average native width relative to SIZE_REF_HW; that base
then grows linearly with their TOTAL battle knockback (+KB_SIZE_PER_POINT per
point), capped at KB_SIZE_CAP times the base.  No knockback on either side =
the base alone.  The split halves' end bursts reuse their clash's size.

While a sustained clash holds, both effects are pinned where they met.  Each
fighter involved shows its own Rig Forge "clash" action (if it has one),
standing still, for exactly the clash's length; the FX built on that action
play with it.  Which clash FX plays for each rule (and its size / density)
comes from the world table: WORLD_SLOTS defaults, overridden by the shared
characters/world_clash.json (FX Studio's World Clash page; load_world).

One code path for Solo and Battle: clashes need two fielded sides, so Solo
(the cursor is the only opponent) simply never finds a pair.
"""

import copy
import math
import random

from . import clashfx, config, fxkit, swordfx

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
DUEL_REARM_TICKS = 90        # the same two fighters cannot start another duel this soon after one
DUEL_MARGIN = 20.0           # a dueling fighter is kept this far inside the screen
MIN_TICKS = 6                # default shortest clash (~100 ms), however little life the effects have left
SIZE_REF_HW = 6.0            # native half width (px) of an effect pair whose clash FX plays at 1x
KB_SIZE_PER_POINT = 0.10     # clash FX grows +10% per point of total knockback (A + B)...
KB_SIZE_CAP = 3.0            # ...up to this many times its base size

# category pair (sorted) -> rule name.  Every pair has one.
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
    ("orb", "trail"): "orb_trail",
    ("crescent", "orb"): "orb_crescent",
    ("orb", "sprite"): "orb_sprite",
    ("crescent", "trail"): "trail_crescent",
    ("sprite", "trail"): "trail_sprite",
    ("crescent", "sprite"): "crescent_sprite",
}
# One-shot rules: settled by the knockback rule, their slot's FX plays.
BURST_RULES = ("orb_orb", "trail_trail", "sprite_sprite", "orb_trail", "orb_crescent", "orb_sprite",
               "trail_crescent", "trail_sprite", "crescent_sprite")

# The world clash table: which clash FX (laser/clashfx.py key, "none" = no
# FX) plays for each slot, at size / density %.  Same for every character.
# FX Studio's World Clash page edits it (FXK.CLASH_SLOTS mirrors this) and
# saves characters/world_clash.json, which overrides these defaults.
WORLD_SLOTS = (
    ("beam_explode", "beam_clash", "Beam × beam (both damage over 10)"),
    ("beam_struggle", "beam_struggle", "Beam × beam struggle (a damage of 10 or less)"),
    ("beam_struggle_end", "overpower_blowout", "Beam struggle won"),
    ("beam_orb", "beam_orb", "Beam × orb / petal"),
    ("beam_split", "beam_split", "Beam split by a trail / crescent / sprite"),
    ("split_tip", "split_burst", "End of each split half"),
    ("beam_nosplit", "split_burst", "Beam not split (cutter hit)"),
    ("orb_orb", "orb_pops", "Orb × orb"),
    ("trail_trail", "sword_duel", "Trail × trail"),
    ("crescent_crescent", "crescent_struggle", "Crescent × crescent"),
    ("sprite_sprite", "kunai_clash", "Sprite × sprite"),
    ("orb_trail", "sword_slash_clash", "Orb × trail"),
    ("orb_crescent", "getsuga_cross", "Orb × crescent"),
    ("orb_sprite", "collision_nova", "Orb × sprite"),
    ("trail_crescent", "sword_slash_clash", "Trail × crescent"),
    ("trail_sprite", "kunai_clash", "Trail × sprite"),
    ("crescent_sprite", "getsuga_cross", "Crescent × sprite"),
)
WORLD_FORMAT = "pb_world_clash"
WORLD_FILE = "world_clash.json"     # in characters/


def _clamp_num(v, d, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return d
    if v != v:
        return d
    return max(lo, min(hi, v))


def normalize_world(c):
    """The world clash settings (FXK.normalizeWorldClash): every slot filled
    in, unknown keys dropped."""
    c = dict(c or {})
    slots_in = c.get("slots") or {}
    slots = {}
    for key, fx_default, _label in WORLD_SLOTS:
        s0 = dict(slots_in.get(key) or {})
        fxk = s0.get("fx")
        slots[key] = {"fx": fxk if isinstance(fxk, str) and fxk else fx_default,
                      "size": _clamp_num(s0.get("size"), 100.0, 10.0, 400.0),
                      "density": _clamp_num(s0.get("density"), 100.0, 10.0, 400.0)}
    return {"format": WORLD_FORMAT, "slots": slots,
            "min_ticks": int(_clamp_num(c.get("min_ticks"), MIN_TICKS, 1, 600))}


WORLD = normalize_world({})


def load_world(root_dir):
    """Read characters/world_clash.json (FX Studio's World Clash page) into
    WORLD; the defaults stay when it is missing or unreadable.  Called once
    at start-up (assets), so Solo and Battle share it."""
    import json
    import os
    global WORLD
    path = os.path.join(root_dir, "characters", WORLD_FILE)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            obj = json.load(f)
    except (OSError, ValueError):
        WORLD = normalize_world({})
        return WORLD
    WORLD = normalize_world(obj if isinstance(obj, dict) and obj.get("format") == WORLD_FORMAT else {})
    return WORLD


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
    if prim == "technique":
        # Every sword technique is a cutting blade: it clashes as a crescent.
        bd = swordfx.body(inst, ps)
        if bd is None or len(bd[0]) < 2:
            return None
        return Body(si, "crescent", "inst", inst, fig, list(bd[0]), max(2.0, bd[1]), dmg, kb, col,
                    _norm(inst.vx, inst.vy) if (inst.vx or inst.vy) else tuple(inst.dir), lst)
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
def _slot_fx(slot):
    """(clash FX key, slot settings) for `slot` from the world table; the
    key is "none" for no FX."""
    cfg = WORLD["slots"].get(slot) or {}
    key = cfg.get("fx") or ""
    if key != "none" and key not in clashfx.BASES and key not in clashfx.VARIANTS:
        key = dict((s[0], s[1]) for s in WORLD_SLOTS).get(slot, "collision_nova")
    return key, cfg


def _native_hw(b):
    """Half width of body b before the position scale (an FX Kit instance's
    hw already carries its ps; the clash FX gets the position scale when it
    is drawn, so it must not be counted twice)."""
    if b.kind == "inst":
        return b.hw / max(1e-6, float(getattr(b.ref, "ps", 1.0) or 1.0))
    return b.hw


def _pair_size(a, b, cfg):
    """Clash FX scale for the pair a, b (see the module notes): the slot's
    size % is the floor of the base, the base is otherwise the pair's
    average native width over SIZE_REF_HW, and total knockback grows it
    linearly up to KB_SIZE_CAP times the base."""
    floor = float(cfg.get("size", 100)) / 100.0
    rel = 0.5 * (_native_hw(a) + _native_hw(b)) / SIZE_REF_HW
    base = max(floor, rel)
    kb = max(0.0, a.kb) + max(0.0, b.kb)
    return base * min(KB_SIZE_CAP, 1.0 + KB_SIZE_PER_POINT * kb)


def _spawn_fx(world, slot, c, angle, c1, c2, hold=None, winner=0, key=None, budget=None, pair=None, scale=None):
    """Spawn the slot's clash FX; with a budget (world ticks) its whole loop
    is fitted inside it (ClashFX.fit).  pair = the two clashing bodies (their
    knockback and width size it, _pair_size); scale = an explicit size (a
    split half's end burst reuses its clash's); neither = the slot's size %."""
    key0, cfg = _slot_fx(slot)
    key = key or key0
    if key == "none":
        return None
    if scale is None:
        scale = _pair_size(pair[0], pair[1], cfg) if pair else float(cfg.get("size", 100)) / 100.0
    # Position scale is applied when it is drawn (clashfx.draw_all), except
    # for an anchored FX (its scale is set when it is anchored).
    fx = clashfx.spawn(world, key, c[0], c[1], angle=angle, c1=c1, c2=c2,
                       scale=scale, hold=hold, winner=winner,
                       density=float(cfg.get("density", 100)) / 100.0)
    if budget is not None:
        fx.fit(budget)
    return fx


def _left(b):
    """Ticks of life body b has left; None = no lifespan (a fighter's own
    trail, a hovering petal, an FX with endless life)."""
    r, k = b.ref, b.kind
    if k == "inst":
        return None if r.life == fxkit.INF else max(0.0, r.life - r.age)
    if k == "proj":
        return max(0.0, r.max_age - r.age)
    if k == "crescent":
        return max(0.0, config.CRESCENT_LIFETIME - r.age)
    if k == "ultc":
        return max(0.0, r.cfg["lifetime"] - r.age)
    return None


def _budget(a, b):
    """World ticks the clash of a and b may last: the shorter remaining life
    of the two (never under min_ticks); None when neither has a lifespan
    (the clash FX then plays at its normal length)."""
    ls = [x for x in (_left(a), _left(b)) if x is not None]
    if not ls:
        return None
    return max(int(WORLD["min_ticks"]), int(min(ls)))


def _held_ticks(fx, hold, budget):
    """World ticks a held clash of `hold` clash-FX ticks lasts (fx already
    fitted to the budget, so its hold ends with it)."""
    if fx is None:
        return hold if budget is None else max(1, min(hold, budget))
    return max(1, min(fx.length(), int(math.ceil(hold / fx.rate - 1e-9))))


def _fx_ticks(fx, budget, default):
    """World ticks a one-shot clash shows for (the fighters' clash action)."""
    if fx is not None:
        return fx.length()
    return default if budget is None else budget


def _kb_winner(a, b):
    """Who the knockback rule will favour (no side effects); None = a tie."""
    if abs(a.kb - b.kb) < 1e-6:
        return None
    return a if a.kb > b.kb else b


def _pscale(world, x, y):
    from . import combat
    return combat.position_scale(x, y, world.screen_w, world.screen_h)


def _engage(world, figs, ticks):
    """Each fighter shows its own Rig Forge "clash" action, standing still,
    for the clash's length (world rule: ticks)."""
    from . import actions
    now = world.global_tick
    for fig in figs:
        if fig is not None and ticks > 0:
            actions.force_clash(fig, world, now + int(ticks), True)


def _deg(dx, dy):
    return math.degrees(math.atan2(dy, dx))


# ---------------------------------------------------------------- beam split
def _split_beam(world, st, beam, c, size=None):
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
            st["tips"].append([h[0], h[1], h[2], beam.col, (c[0], c[1]), size])
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
    __slots__ = ("a", "b", "c", "rule", "until", "pins", "fx", "start", "hidden")

    def __init__(self, a, b, c, rule, until, fx, start, hidden=()):
        self.a, self.b, self.c, self.rule, self.until, self.fx, self.start = a, b, c, rule, until, fx, start
        self.pins = (_pin(a), _pin(b))
        self.hidden = tuple(hidden)     # ids in clashfx.HIDDEN while it holds


class Duel:
    """A sword duel in progress: fa / fb (side 0 / side 1) are moved along
    plan, one frame per tick."""
    __slots__ = ("a", "b", "fa", "fb", "plan", "i", "fx", "owns", "pair")

    def __init__(self, a, b, plan, fx, pair):
        self.a, self.b, self.fa, self.fb = a, b, a.owner, b.owner
        self.plan, self.i, self.fx, self.pair = plan, 0, fx, pair
        # Slash frames are shown through render.frame_override — only for a
        # fighter that has slash frames and nothing else holding the override.
        self.owns = tuple(bool(f.render.bundle.slash) and f.render.frame_override is None
                          for f in (self.fa, self.fb))


def _state(world):
    st = getattr(world, "clash_state", None)
    if st is None:
        st = world.clash_state = {"active": [], "busy": set(), "seen": {}, "tips": [],
                                  "rng": random.Random(), "halves": set(),
                                  "duels": [], "duel_pose": {}, "duel_figs": set(), "duel_cd": {}}
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
    budget = _budget(a, b)
    if rule == "beam_beam":
        if a.damage > STRONG_BEAM_DAMAGE and b.damage > STRONG_BEAM_DAMAGE:
            _settle(world, a, b, c)
            fx = _spawn_fx(world, "beam_explode", c, _deg(*a.dir), a.col, b.col, budget=budget, pair=(a, b))
            _engage(world, figs, _fx_ticks(fx, budget, 40))
            return None
        fx = _spawn_fx(world, "beam_struggle", c, _deg(*a.dir), a.col, b.col, hold=STRUGGLE_TICKS, budget=budget, pair=(a, b))
        held = _held_ticks(fx, STRUGGLE_TICKS, budget)
        hidden = ()
        if fx is not None and fx.base == "beam_struggle":
            # Anchored: the FX draws both beams from their origins (the tail
            # of each, locked now) to the node, at their real widths, and the
            # real beams are hidden while it holds.
            w = _kb_winner(a, b)
            ws = [bd.hw * 2.0 * (_pscale(world, bd.ref.x, bd.ref.y) if bd.kind == "proj" else 1.0)
                  for bd in (a, b)]
            fx.anchor_beams(a.pts[1], ws[0], b.pts[1], ws[1], None if w is None else (1 if w is a else 0),
                            pscale=_pscale(world, c[0], c[1]))
            hidden = (id(a.ref), id(b.ref))
            clashfx.HIDDEN.update(hidden)
        _engage(world, figs, fx.length() if fx is not None else held)
        return Clash(a, b, c, rule, now + held, fx, now, hidden)
    if rule == "beam_orb":
        fx = _spawn_fx(world, "beam_orb", c, _deg(*a.dir), a.col, b.col, budget=budget, pair=(a, b))
        held = _held_ticks(fx, BEAM_ORB_TICKS, budget)
        _engage(world, figs, _fx_ticks(fx, budget, held + 20))
        return Clash(a, b, c, rule, now + held, fx, now)
    if rule == "beam_cut":
        _settle(world, a, b, c, exempt=a)   # the beam itself is never cancelled by its cutter
        # A split half never splits again (no cascade): it is just cut.
        if id(a.ref) not in st["halves"] and rng.random() < SPLIT_CHANCE:
            fx = _spawn_fx(world, "beam_split", c, _deg(*a.dir), a.col, b.col, budget=budget, pair=(a, b))
            _split_beam(world, st, a, c, size=_pair_size(a, b, _slot_fx("split_tip")[1]))
        else:
            fx = _spawn_fx(world, "beam_nosplit", c, _deg(*a.dir), a.col, b.col, budget=budget, pair=(a, b))
        _engage(world, figs, _fx_ticks(fx, budget, 30))
        return None
    if rule == "crescent_crescent":
        fx = _spawn_fx(world, "crescent_crescent", c, ang, a.col, b.col, hold=CRESCENT_TICKS, budget=budget, pair=(a, b))
        held = _held_ticks(fx, CRESCENT_TICKS, budget)
        _engage(world, figs, fx.length() if fx is not None else held + 20)
        return Clash(a, b, c, rule, now + held, fx, now)
    slot = rule     # BURST_RULES: the rule's own slot
    key = None
    if rule == "trail_trail":
        if clashfx.resolve(_slot_fx(slot)[0])[0] == "sword_duel":
            if _start_duel(world, st, a, b, c, now, budget):
                return None
            key = "sword_slash_clash"   # re-arming pair / no room for a duel: a one-shot burst instead
    _settle(world, a, b, c)
    fx = _spawn_fx(world, slot, c, ang, a.col, b.col, key=key, budget=budget, pair=(a, b))
    _engage(world, figs, _fx_ticks(fx, budget, 30))
    return None


def _finish(world, st, rec):
    """A held clash ends: the knockback rule decides it."""
    a, b, c = rec.a, rec.b, rec.c
    if rec.fx is not None and rec.fx.anchored:
        c = rec.fx.node_world()     # the struggle ends where the node was pushed to
    clashfx.HIDDEN.difference_update(rec.hidden)
    la, lb = _alive(a), _alive(b)
    if la and lb:
        w = _settle(world, a, b, c)
        if rec.rule == "beam_beam" and w is not None:
            ang = _deg(*a.dir)
            _spawn_fx(world, "beam_struggle_end", c, ang, a.col, b.col, winner=0 if w is a else 1, pair=(a, b))
    if rec.fx is not None and rec.fx.phase == "hold":
        rec.fx.release()
    st["busy"].discard(id(a.ref))
    st["busy"].discard(id(b.ref))


# ---------------------------------------------------------------- sword duel
def _start_duel(world, st, a, b, c, now, budget=None):
    """trail x trail: start a sword duel between the two trails' owners.
    False when it cannot (a re-arming pair, no two distinct fighters, or
    the duel would outlast the clash budget)."""
    fa, fb = a.owner, b.owner
    if fa is None or fb is None or fa is fb:
        return False
    pair = (id(fa), id(fb))
    if now < st["duel_cd"].get(pair, -1):
        return False
    key, cfg = _slot_fx("trail_trail")
    _base, sp = clashfx.resolve(key)
    bs = 0.5 * (fa.mode.body_scale() + fb.mode.body_scale())
    plan = clashfx.duel_plan(st["rng"], (fa.x, fa.y), (fb.x, fb.y), c, float(sp.get("reach", 34)) * bs,
                             strikes=sp.get("strikes", (4, 7)), bind=float(sp.get("bind", 0.3)))
    if budget is not None and len(plan) > budget:
        return False
    fx = clashfx.spawn(world, key, c[0], c[1], angle=0.0, c1=a.col, c2=b.col,
                       scale=_pair_size(a, b, cfg), hold=-1,
                       density=float(cfg.get("density", 100)) / 100.0)
    fx.anchor_duel(_pscale(world, c[0], c[1]))
    st["duels"].append(Duel(a, b, plan, fx, pair))
    st["duel_figs"].update(pair)
    _engage(world, (fa, fb), len(plan))
    return True


def _duel_fielded(world, d):
    return d.fa in world.sides[0].figures and d.fb in world.sides[1].figures if len(world.sides) >= 2 else False


def _duel_end(world, st, d):
    """A duel is over (played out, or a fighter fell): give the fighters
    back, then the knockback rule decides it."""
    for f, own in zip((d.fa, d.fb), d.owns):
        if own:
            f.render.frame_override = None
    st["duel_figs"].discard(id(d.fa))
    st["duel_figs"].discard(id(d.fb))
    st["duel_cd"][d.pair] = world.global_tick + DUEL_REARM_TICKS
    if d.fx is not None and d.fx.phase == "hold":
        d.fx.release()
    if _duel_fielded(world, d):
        fr = d.plan[min(d.i, len(d.plan)) - 1] if d.i > 0 else None
        c = ((fr[0] + fr[2]) / 2.0, (fr[1] + fr[3]) / 2.0) if fr else ((d.fa.x + d.fb.x) / 2.0, (d.fa.y + d.fb.y) / 2.0)
        _settle(world, d.a, d.b, c)


def duel_tick(fig, world):
    """CombatSystem, once per tick per figure: while fig is in a sword duel
    the duel owns its movement (MotionSystem and the melee FSM skip it).
    True when it moved the figure this tick."""
    st = getattr(world, "clash_state", None)
    if st is None:
        return False
    pose = st["duel_pose"].get(id(fig))
    if pose is None:
        return False
    from . import combat
    x, y, opp, swing, own = pose
    t = fig.transform
    ox, oy = t.x, t.y
    m = DUEL_MARGIN
    t.x = max(m, min(fig.screen_w - m, x))
    t.y = max(m, min(fig.screen_h - m, y))
    fig.face(ox, oy)
    if fig.aim is None:
        t.facing_left = opp.x < t.x     # always squared up to the other fighter
    if (t.x - ox) ** 2 + (t.y - oy) ** 2 > 36.0:
        combat.spawn_afterimage(fig)
    combat._apply_trail_update(fig, t, True, False)
    if own:
        b = fig.render.bundle
        fs = b.slash_flipped if t.facing_left else b.slash
        if swing is not None and fs:
            fig.render.frame_override = fs[min(len(fs) - 1, int(swing * len(fs)))]
        else:
            fig.render.frame_override = None
    fig.render.advance()
    return True


def _duels(world, st):
    """Advance every duel one frame: this tick's pose for each fighter
    (duel_tick applies it) and the anchored FX."""
    poses = st["duel_pose"] = {}
    live = []
    for d in st["duels"]:
        if d.i >= len(d.plan) or not _duel_fielded(world, d):
            _duel_end(world, st, d)
            continue
        fr = d.plan[d.i]
        d.i += 1
        poses[id(d.fa)] = (fr[0], fr[1], d.fb, fr[6], d.owns[0])
        poses[id(d.fb)] = (fr[2], fr[3], d.fa, fr[6], d.owns[1])
        if d.fx is not None:
            d.fx.duel_frame(fr)
        live.append(d)
    st["duels"] = live


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
    # 1b. Sword duels: where each dueling fighter is this tick.
    _duels(world, st)
    # 2. Split halves: each explodes where it ends.
    tips = []
    for t in st["tips"]:
        kind, obj, owner, col, _last, size = t
        if _tip_alive(kind, obj):
            t[4] = _tip_pos(kind, obj)
            tips.append(t)
        else:
            st["halves"].discard(id(obj))
            p = t[4]
            ang = _deg(*_norm(p[0] - (owner.x if owner else p[0] - 1), p[1] - (owner.y if owner else p[1])))
            _spawn_fx(world, "split_tip", p, ang, col, col, scale=size)
    st["tips"] = tips
    # 3. New contacts (two fielded sides only: Solo never has a pair).
    if len(world.sides) < 2 or not (world.sides[0].figures and world.sides[1].figures):
        st["seen"].clear()
        return
    A, B = _bodies(world, 0), _bodies(world, 1)
    if not A or not B:
        return
    busy, seen, dueling = st["busy"], st["seen"], st["duel_figs"]
    if dueling:     # a fighter mid-duel clashes with nothing else
        A = [x for x in A if id(x.owner) not in dueling]
        B = [x for x in B if id(x.owner) not in dueling]
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
