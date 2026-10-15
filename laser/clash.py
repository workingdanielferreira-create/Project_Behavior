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

  beam x beam         both damage over 10: they explode (beam_clash).
                      Both knockback STRUGGLE_KB or more: they lock in a
                      struggle (beam_struggle) for a fixed STRUGGLE_TICKS
                      (never fitted to the beams' remaining life), then the
                      winner blows through (overpower_blowout).  The struggle
                      FX is anchored to the two real beams: it draws each
                      beam from its origin (locked when the clash starts) to
                      the node with that beam's own look (tail / head width,
                      colours, glow), the real beams are hidden meanwhile,
                      and the node surges back and forth (a tug of war)
                      before it commits toward the loser's origin; the
                      blowout fires where the node ends up.  Equal knockback
                      (a tie) overloads instead: the node shakes and swells,
                      then blows up, costing each fighter OVERLOAD_HP_PCT of
                      its max HP and throwing it OVERLOAD_KB_PX (_overload).
                      Otherwise the
                      lesser version: a one-shot spark burst (the struggle's
                      finale only) at the contact, settled at once by the
                      knockback rule.  Both are sized from the beams' real
                      widths (_beam_scale).  Their sphere and shockwave rings
                      (and those of the blowout and the overload) are
                      soft-capped to BEAM_FX_CAP_HEIGHTS x the shorter
                      fighter's height, end to end (_cap_size)
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
                      dash in, their blades meet (some strikes are flurry
                      combos: World Clash Flurry %), they spring apart, and
                      it ends on one big clash.  That final hit decides it
                      (_final_hit): the knockback winner (a random one on a
                      tie) launches the other FINAL_KB_BASE_PX +
                      FINAL_KB_PER_KB x its trail's knockback away, then
                      finishes (_finisher): its attack_special at 50% HP or
                      less, its ultimate below 30%.  A duel cut short (a
                      fighter fell) is settled by the knockback rule as
                      before.  The FX is anchored
                      to their real positions every tick.  A pair that has
                      just duelled (DUEL_REARM_TICKS), or a Clash panel FX
                      other than a sword duel, plays a one-shot burst instead
  Sword Duel on any other slot (DUEL_RULES): each side whose effect is
                      attached to its fighter (_connected: a trail, or Attached
                      motion) is anchored — that fighter is moved along its
                      side of the duel like the trail x trail duel, which ends
                      the same way (final hit, finisher), with no clash budget.
                      A side whose effect is a projectile is cancelled and the
                      FX's stand-in plays its side.  No side attached: the
                      stand-ins play on their own, as before.  Only one sword
                      duel plays at a time (_duel_busy): any other clash that
                      would start one plays sword_slash_clash instead
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

Clash size (_pair_size): random for each clash FX, between SIZE_MIN (10%)
and the HIGHER battle knockback of the two effects (capped at 100) read as a
% of the slot's size % (knockback 100 -> up to 100% of it, 50 -> up to 50%).
No knockback = SIZE_MIN.  The split halves' end bursts reuse their clash's
size.

One clash, one FX (_quiet): every contact between the same two fighters that
starts within MERGE_TICKS of a clash FX between them, within MERGE_PX of it,
is part of that clash: it is still settled by the knockback rule, but plays
no FX and no clash action of its own (one effect touching several enemy
effects at once used to stack an FX per contact).  A full beam struggle is
the exception: an earlier contact never silences it (it always plays its
own FX), and more beams of the same two fighters (a beam built from several
beam layers) reaching a struggle already running between them join it —
pinned, hidden under its FX and settled with it (_struggle_of).

Overpower: when one effect's knockback beats the other's by more than
OVERPOWER_KB, there is no clash at all: the weaker one is destroyed at its
source (a trail's owner recoils instead) and the stronger carries on
untouched, never pinned, split or slowed.

Ultimates (_is_ult: an FX Studio effect fired by an `ultimate` action, or a
built-in ultimate crescent) still clash by every rule above, but a
non-ultimate effect can never nullify one: the knockback rule never cancels
it (whatever it loses on knockback), it is never pinned in a held clash by a
non-ultimate effect it out-knocks (that clash plays as a one-shot burst and
the weaker effect is destroyed), an ultimate beam is split only by a cutter
whose knockback beats its own, and a clash never cuts its fighter's ultimate
action short (no "clash" action while it plays).  Ultimate against ultimate
follows the plain rules.

While a sustained clash holds, both effects are pinned where they met.  Each
fighter involved shows its own Rig Forge "clash" action (if it has one),
standing still, for exactly the clash's length; the FX built on that action
play with it — but only a fighter whose body the clash point touches (its
hit circle + the clashing segment's half width + CONTACT_MARGIN,
_in_contact): two shots meeting out in the field play their clash and the
knockback rule, and leave both fighters free.  The full beam struggle and
the sword duel are fighter-vs-fighter lock-ins and engage both fighters
wherever they meet.  A full beam struggle also holds both fighters in place, doing
nothing new (no movement, attacks or shots), until its animation (hold +
finale) has played out (_hold_figs / hold_tick; timefx.run_side stops their
bodies while their FX run on).  Which clash FX plays for each rule (and
its size / density) comes from the world table: WORLD_SLOTS defaults, overridden by the shared
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
STRUGGLE_TICKS = 150         # beam struggle length (~2.4 s), fixed
STRUGGLE_KB = 100.0          # both beams need this much knockback for a full struggle
LESSER_SCALE = 0.5           # the lesser (one-shot) beam clash is drawn at this share of the struggle's size
STRUGGLE_REF_W = 40.0        # beam width (px, glow included) the struggle FX is drawn at its own size for
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
DUEL_ANCHOR_PX = 400.0       # an anchored fighter is at most this far from the clash (x character scale)
FINAL_KB_BASE_PX = 240.0     # sword duel final hit: the loser is launched this far...
FINAL_KB_PER_KB = 0.5        # ...plus this many px per point of the winning trail's knockback...
FINAL_KB_MAX_PX = 900.0      # ...up to this far
FINISH_SPECIAL_HP_PCT = 50.0  # duel winner at or below this % HP finishes with its attack_special...
FINISH_ULT_HP_PCT = 30.0     # ...below this % HP with its ultimate
FINISH_WAIT_TICKS = 90       # a finisher special waits this long for its fighter to be free, then is dropped
FINAL_HEAVY_TICKS = 60       # the final-hit launch can't be replaced by a weaker knockback for this long
MIN_TICKS = 6                # default shortest clash (~100 ms), however little life the effects have left
SIZE_MIN = 0.10              # smallest random clash FX size (10%)
SIZE_KB_FULL = 100.0         # knockback for the full slot size (higher counts as this)
MERGE_TICKS = 6              # contacts of the same two fighters this soon after a clash FX...
MERGE_PX = 60.0              # ...and this close to it are part of that clash (no FX of their own)
OVERLOAD_HP_PCT = 10.0       # a tied beam struggle overloads: each fighter loses this % of its max HP...
OVERLOAD_KB_PX = 500.0       # ...and is thrown this far from the blast (ignores knockback immunity)
OVERPOWER_KB = 100.0         # knockback lead that destroys the weaker effect outright, no clash
BEAM_FX_CAP_HEIGHTS = 2.0    # beam clash FX (struggle, its spark, blowout, overload): sphere + rings soft-capped
                             # to this many times the shorter fighter's height, end to end (_cap_size)

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
# Held rules (both effects pinned while they hold) -> the slot played as a
# one-shot burst instead when an ultimate out-knocks a non-ultimate effect.
HELD_SLOTS = {"beam_beam": "beam_struggle", "beam_orb": "beam_orb", "crescent_crescent": "crescent_crescent"}
# One-shot rules: settled by the knockback rule, their slot's FX plays.
BURST_RULES = ("orb_orb", "trail_trail", "sprite_sprite", "orb_trail", "orb_crescent", "orb_sprite",
               "trail_crescent", "trail_sprite", "crescent_sprite")
# Rules whose slot can start a real sword duel when it is set to Sword Duel
# (the slot is the rule's own).  The beam rules pick among several slots
# (beam_explode / beam_struggle / beam_split / beam_nosplit): Sword Duel
# there plays its stand-ins only.  Only one sword duel plays at a time.
DUEL_RULES = BURST_RULES + ("crescent_crescent", "beam_orb")

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
                      "density": _clamp_num(s0.get("density"), 100.0, 10.0, 400.0),
                      "loop_x": _clamp_num(s0.get("loop_x"), 100.0, 0.0, 400.0),
                      "loop_y": _clamp_num(s0.get("loop_y"), 100.0, 0.0, 400.0),
                      "flurry": _clamp_num(s0.get("flurry"), 30.0, 0.0, 100.0)}
    return {"format": WORLD_FORMAT, "slots": slots,
            "min_ticks": int(_clamp_num(c.get("min_ticks"), MIN_TICKS, 1, 600))}


WORLD = normalize_world({})


def duel_loop(slot="trail_trail"):
    """(x, y) scale of the sword duel's whole sequence on the screen axes,
    from `slot`'s Loop X / Y % (World Clash: shown on any slot whose clash
    FX is Sword Duel; 1.0 = as designed).  clashfx.duel_plan applies it."""
    cfg = WORLD["slots"].get(slot) or {}
    return (float(cfg.get("loop_x", 100.0)) / 100.0, float(cfg.get("loop_y", 100.0)) / 100.0)


def duel_flurry(slot="trail_trail"):
    """Chance (0..1) that a sword duel strike is a flurry combo, from
    `slot`'s Flurry % (World Clash: shown on any slot whose clash FX is
    Sword Duel).  clashfx.duel_plan uses it."""
    cfg = WORLD["slots"].get(slot) or {}
    return float(cfg.get("flurry", 30.0)) / 100.0


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
            for pl in [drv.player, drv.clane[0]] + [ln[0] for ln in drv.rlanes]:
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
    from . import ai, motion
    if fig is None or kb <= 0:
        return
    if ai.knockback_immune(fig, world):
        return
    dx, dy = _norm(fig.x - cx, fig.y - cy)
    spd = kb * (1.0 - config.BOUNCE_FRICTION)
    motion.launch_knockback(fig, dx * spd, dy * spd, world.global_tick)


def _is_ult(b):
    """True for an ultimate's effect: an FX Studio effect fired by an
    `ultimate` action (its split halves included) or a built-in ultimate
    crescent."""
    if b.kind == "ultc":
        return True
    return b.kind == "inst" and (b.ref.fx.get("action") == "ultimate")


def _ult_over(a, b):
    """The ultimate of the pair when exactly one of the two is an ultimate's
    effect and its knockback beats the other's, else None."""
    ua, ub = _is_ult(a), _is_ult(b)
    if ua and not ub and a.kb > b.kb:
        return a
    if ub and not ua and b.kb > a.kb:
        return b
    return None


def _settle(world, a, b, c, exempt=None):
    """Knockback rule.  Returns the winner (None on a tie).  `exempt` is
    never cancelled (a beam against its cutter).  An ultimate's effect is
    never cancelled by a non-ultimate one, whatever the knockback (it can
    still lose the clash: a stronger cutter splits it, laser rules below);
    ultimate against ultimate follows the plain rule."""
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
        if _is_ult(l) and not _is_ult(other):
            continue
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


_SIZE_RNG = random.Random()


def _pair_size(a, b, cfg):
    """Clash FX scale for the pair a, b (see the module notes): random
    between SIZE_MIN and the higher knockback (capped at SIZE_KB_FULL) as a
    share of the slot's size %; SIZE_MIN when that top is no bigger."""
    kb = min(SIZE_KB_FULL, max(0.0, a.kb, b.kb))
    top = float(cfg.get("size", 100)) / 100.0 * kb / SIZE_KB_FULL
    if top <= SIZE_MIN:
        return SIZE_MIN
    return _SIZE_RNG.uniform(SIZE_MIN, top)


def _spawn_fx(world, slot, c, angle, c1, c2, hold=None, winner=0, key=None, budget=None, pair=None, scale=None):
    """Spawn the slot's clash FX; with a budget (world ticks) its whole loop
    is fitted inside it (ClashFX.fit).  pair = the two clashing bodies (their
    knockback and width size it, _pair_size); scale = an explicit size (a
    split half's end burst reuses its clash's); neither = the slot's size %."""
    key0, cfg = _slot_fx(slot)
    key = key or key0
    if key == "none" or _state(world).get("quiet"):
        return None
    if clashfx.resolve(key)[0] == "sword_duel" and _duel_busy(world, _state(world)):
        key = "sword_slash_clash"   # one sword duel at a time, world-wide
    if scale is None:
        scale = _pair_size(pair[0], pair[1], cfg) if pair else float(cfg.get("size", 100)) / 100.0
    # Position scale is applied when it is drawn (clashfx.draw_all), except
    # for an anchored FX (its scale is set when it is anchored).
    fx = clashfx.spawn(world, key, c[0], c[1], angle=angle, c1=c1, c2=c2,
                       scale=scale, hold=hold, winner=winner,
                       density=float(cfg.get("density", 100)) / 100.0)
    fx.duel_slot = slot     # a Sword Duel FX reads this slot's Loop X / Y and Flurry %
    if budget is not None:
        fx.fit(budget)
    return fx


def _beam_look(world, bd):
    """How beam body bd is drawn right now (what the anchored struggle copies
    so its beams line up with the real ones): o = its origin (tail), wt / wh
    = tail / head width, ct / ch = tail / head colour, glow = extra glow
    width, gcol = glow colour (None = the beam's own), am = alpha, add =
    additive blend.  All in screen px."""
    r = bd.ref
    if bd.kind == "proj":
        ps = _pscale(world, r.x, r.y)
        prog = min(1.0, r.age / max(1, r.max_age))
        return dict(o=bd.pts[1],
                    wt=(r.w_start0 + (r.w_start1 - r.w_start0) * prog) * ps,
                    wh=(r.w_end0 + (r.w_end1 - r.w_end0) * prog) * ps,
                    ct=tuple(r.c1), ch=tuple(r.c2), glow=r.glow * ps, gcol=r.glow_color,
                    am=max(0.0, 1.0 - r.age / max(1, r.max_age)), add=bool(r.additive))
    P, ps = r.fx["params"], r.ps
    prog = fxkit.life_t(r)
    try:
        c1, c2 = fxkit.color_pair(r.fx, bd.owner.lut)
    except Exception:
        c1 = c2 = bd.col
    gc = fxkit.hex_rgb(P["glow_color"], None) if P.get("glow_color") else None
    return dict(o=bd.pts[1],
                wt=(P["w_start0"] + (P["w_start1"] - P["w_start0"]) * prog) * ps,
                wh=(P["w_end0"] + (P["w_end1"] - P["w_end0"]) * prog) * ps,
                ct=tuple(c1), ch=tuple(c2), glow=float(P.get("glow") or 0) * ps, gcol=gc,
                am=max(0.0, 1.0 - r.age / r.life) if r.life != fxkit.INF else 1.0, add=False)


def _beam_scale(slot, looks):
    """Struggle FX size from the beams' real widths: the slot's size % at
    STRUGGLE_REF_W, in proportion to the thicker beam (glow included)."""
    w = max(max(lk["wt"], lk["wh"]) + lk["glow"] for lk in looks)
    size = float(_slot_fx(slot)[1].get("size", 100)) / 100.0
    return max(0.15, min(3.0, size * w / STRUGGLE_REF_W))


def _stand_px(world, fig):
    """How tall fig stands on screen right now: the roster's standing height
    (config.IMAGE_STAND_HEIGHT_PX) times its character scale and the
    position scale where it is."""
    try:
        cs = float(fig.mode.body_scale())
    except Exception:
        cs = 1.0
    return config.IMAGE_STAND_HEIGHT_PX * cs * _pscale(world, fig.x, fig.y)


def _cap_size(world, fx, figs):
    """Soft size cap of a beam clash FX: its sphere and shockwave rings stay
    within BEAM_FX_CAP_HEIGHTS x the shorter fighter's height, end to end
    (ClashFX.cap_r is the reach from the centre, half of that)."""
    hs = [_stand_px(world, f) for f in figs if f is not None]
    if fx is not None and hs:
        fx.cap_r = BEAM_FX_CAP_HEIGHTS * min(hs) / 2.0
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


def _in_contact(fig, contact):
    """True when the clash point touches fig's body: its hit circle
    (PROJ_HIT_RADIUS x character scale, the circle FX hit) plus the half
    width of the clashing segment there, plus CONTACT_MARGIN — the same
    slack the clash itself uses to decide two effects touch."""
    (cx, cy), hw = contact
    reach = float(config.PROJ_HIT_RADIUS) * fig.mode.body_scale() + hw + CONTACT_MARGIN
    return (fig.x - cx) ** 2 + (fig.y - cy) ** 2 <= reach * reach


def _engage(world, figs, ticks, contact=None):
    """Each fighter shows its own Rig Forge "clash" action, standing still,
    for the clash's length (world rule: ticks).  With contact ((x, y), half
    width) only a fighter physically touching the clash point is staggered:
    two shots meeting out in the field leave their fighters alone
    (_in_contact).  Without it (beam struggle, sword duel) both are."""
    from . import actions
    if _state(world).get("quiet"):
        return      # part of a clash already showing (_quiet)
    now = world.global_tick
    for fig in figs:
        if fig is None or ticks <= 0:
            continue
        if contact is not None and not _in_contact(fig, contact):
            continue    # the clash is away from this fighter's body
        r = getattr(fig, "act", None)
        if r is not None and r.playing == "ultimate":
            continue    # a clash never cuts an ultimate's animation short
        fs = _state(world)["finishing"].get(id(fig))
        if r is not None and fs is not None and r.playing == "attack_special" and r.last_start.get("attack_special") == fs:
            continue    # nor a sword duel's finisher special (_finish_specials)
        actions.force_clash(fig, world, now + int(ticks), True)


def _quiet(st, a, b, c, now):
    """True when this contact is part of a clash FX that already started
    between the same two fighters (MERGE_TICKS / MERGE_PX); otherwise it
    becomes the new reference for that pair."""
    k = (id(a.owner), id(b.owner)) if a.side == 0 else (id(b.owner), id(a.owner))
    r = st["recent"].get(k)
    if r is not None and now - r[0] <= MERGE_TICKS and math.hypot(c[0] - r[1], c[1] - r[2]) <= MERGE_PX:
        return True
    st["recent"][k] = (now, c[0], c[1])
    return False


def _overpower(world, a, b, c):
    """One effect's knockback leads by more than OVERPOWER_KB: the weaker is
    destroyed (a trail's owner recoils), the stronger is left untouched.
    True when it happened (no clash then)."""
    if abs(a.kb - b.kb) <= OVERPOWER_KB:
        return False
    _settle(world, a, b, c)
    return True


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
    __slots__ = ("a", "b", "c", "rule", "until", "pins", "fx", "start", "hidden", "joined")

    def __init__(self, a, b, c, rule, until, fx, start, hidden=()):
        self.a, self.b, self.c, self.rule, self.until, self.fx, self.start = a, b, c, rule, until, fx, start
        self.pins = (_pin(a), _pin(b))
        self.hidden = tuple(hidden)     # ids in clashfx.HIDDEN while it holds
        self.joined = False             # extra beams riding another struggle (no FX / finale of their own)


def _struggle_of(st, a, b):
    """The beam struggle already holding between a's and b's fighters, or
    None."""
    for rec in st["active"]:
        if (rec.rule == "beam_beam" and rec.fx is not None and rec.a.owner is a.owner
                and rec.b.owner is b.owner):
            return rec
    return None


class Duel:
    """A sword duel in progress: fa / fb (side 0 / side 1) are moved along
    plan, one frame per tick — each only when anchored (its effect was
    attached to it); an unanchored side is the FX's stand-in."""
    __slots__ = ("a", "b", "fa", "fb", "plan", "i", "fx", "owns", "pair", "final", "anchor")

    def __init__(self, a, b, plan, fx, pair, anchor=(True, True)):
        self.a, self.b, self.fa, self.fb = a, b, a.owner, b.owner
        self.plan, self.i, self.fx, self.pair = plan, 0, fx, pair
        self.anchor = tuple(anchor)
        self.final = False      # True once it reached its final hit (_final_hit settles it)
        # Slash frames are shown through render.frame_override — only for an
        # anchored fighter that has slash frames and nothing else holding it.
        self.owns = tuple(on and bool(f.render.bundle.slash) and f.render.frame_override is None
                          for f, on in zip((self.fa, self.fb), self.anchor))


def _state(world):
    st = getattr(world, "clash_state", None)
    if st is None:
        st = world.clash_state = {"active": [], "busy": set(), "seen": {}, "tips": [],
                                  "rng": random.Random(), "halves": set(),
                                  "duels": [], "duel_pose": {}, "duel_figs": set(), "duel_cd": {},
                                  "recent": {}, "quiet": False, "held": {}, "finish": [], "finishing": {}}
    return st


# ---------------------------------------------------------------- struggle hold
def _hold_figs(world, st, figs, until):
    """The fighters of a beam struggle stay where they are, doing nothing
    new (no movement, attacks or shots), until tick `until` — the end of the
    struggle animation (hold + finale).  A later call replaces the time."""
    for f in figs:
        if f is not None:
            st["held"][id(f)] = (f, int(until))
            r = getattr(f, "act", None)
            if r is not None and r.forced == "clash":
                r.forced_until = min(r.forced_until, int(until))


def locked(world, obj):
    """True while effect obj (a projectile, an FX instance, ...) is held in
    a clash (busy): other systems leave it alone until the clash settles it
    (CollisionSystem's bullet-vs-bullet scatter would otherwise destroy two
    struggling beams the tick after they lock)."""
    st = getattr(world, "clash_state", None)
    return st is not None and id(obj) in st["busy"]


def held(world, fig):
    """True while fig is held in place by a beam struggle."""
    st = getattr(world, "clash_state", None)
    e = st["held"].get(id(fig)) if st is not None else None
    return e is not None and e[0] is fig and world.global_tick < e[1]


def holding(world):
    """True while any fighter is held by a beam struggle (app._tick then runs
    the sides through timefx.run_side, where a held body takes no step)."""
    st = getattr(world, "clash_state", None)
    if st is None or not st["held"]:
        return False
    now = world.global_tick
    return any(now < e[1] for e in st["held"].values())


def hold_tick(fig, world):
    """CombatSystem, for a fighter whose body is stopped this sub-pass
    (timefx.run_side): when a beam struggle holds it (and Time control does
    not also stop it), its FX and its "clash" action keep playing while it
    stays put.  True when it handled the figure."""
    from . import actions, fxkit, timefx
    if not held(world, fig) or timefx.state(fig).body_steps <= 0:
        return False
    t = fig.transform
    x, y = t.x, t.y
    r = getattr(fig, "act", None)
    if r is not None and r.forced is not None and r.playing == r.forced and world.global_tick < r.forced_until:
        actions.update(fig, world)      # the forced clash action plays on, rooted
        fxkit.update_figure(fig, world, frozen=not timefx.fx_on(world, fig))
    else:
        fxkit.update_figure(fig, world, hold="time")
    t.x, t.y = x, y
    fig.render.is_moving = False
    fig.render.advance()
    return True


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
    # Only a fighter whose body the clash point touches is staggered
    # (_engage); the full beam struggle below holds both regardless.
    touch = (c, max(a.hw, b.hw))
    budget = _budget(a, b)
    if rule in DUEL_RULES and clashfx.resolve(_slot_fx(rule)[0])[0] == "sword_duel":
        # Sword Duel on this pair's slot: an attached (melee) effect's
        # fighter is moved along its stand-in's path (_start_duel); with
        # none attached the stand-ins play on their own (the rule below).
        anchor = (_connected(a), _connected(b))
        if any(anchor) or _duel_busy(world, st):
            # No clash budget: once a fighter is anchored the duel owns it,
            # however little life its effect has left.
            if (any(anchor) and not st["quiet"] and not _duel_busy(world, st)
                    and _start_duel(world, st, a, b, c, now, slot=rule, anchor=anchor)):
                return None
            # A duel already running (one at a time), a merged contact, a
            # re-arming pair or no room for a duel: a one-shot burst instead.
            _settle(world, a, b, c)
            fx = _spawn_fx(world, rule, c, ang, a.col, b.col, key="sword_slash_clash", budget=budget, pair=(a, b))
            _engage(world, figs, _fx_ticks(fx, budget, 30), touch)
            return None
    if rule in HELD_SLOTS and _ult_over(a, b) is not None:
        # An ultimate that out-knocks a non-ultimate effect is never pinned
        # by it (no struggle / hold): the clash plays as a one-shot burst,
        # the knockback rule destroys the weaker, and the ultimate blasts on.
        _settle(world, a, b, c)
        fx = _spawn_fx(world, HELD_SLOTS[rule], c, _deg(*a.dir) if rule != "crescent_crescent" else ang,
                       a.col, b.col, hold=0, budget=budget, pair=(a, b))
        if fx is not None and fx.sustain:
            fx.release()
        _engage(world, figs, fx.length() if fx is not None else 30, touch)
        return None
    if rule == "beam_beam":
        if a.damage > STRONG_BEAM_DAMAGE and b.damage > STRONG_BEAM_DAMAGE:
            _settle(world, a, b, c)
            fx = _spawn_fx(world, "beam_explode", c, _deg(*a.dir), a.col, b.col, budget=budget, pair=(a, b))
            _engage(world, figs, _fx_ticks(fx, budget, 40), touch)
            return None
        looks = (_beam_look(world, a), _beam_look(world, b))
        scale = _beam_scale("beam_struggle", looks)
        if a.kb < STRUGGLE_KB or b.kb < STRUGGLE_KB:
            # The lesser version: a one-shot spark burst at the contact (the
            # struggle's finale only), settled at once by the knockback rule.
            _settle(world, a, b, c)
            fx = _cap_size(world, _spawn_fx(world, "beam_struggle", c, _deg(*a.dir), a.col, b.col, hold=0,
                                            scale=scale * LESSER_SCALE), figs)
            if fx is not None and fx.sustain:
                fx.release()
            _engage(world, figs, fx.length() if fx is not None else 30, touch)
            return None
        # The full struggle: a fixed STRUGGLE_TICKS, never fitted to the
        # beams' remaining life (both are pinned, their age frozen, while it
        # holds).
        joined = _struggle_of(st, a, b)
        if joined is not None:
            # More beams of the same two fighters (a beam built from several
            # beam layers) reaching the struggle already running between
            # them: they join it — pinned, hidden under its FX, and settled
            # with it — instead of locking in a second struggle with no FX.
            hidden = (id(a.ref), id(b.ref))
            clashfx.HIDDEN.update(hidden)
            rec = Clash(a, b, c, rule, joined.until, None, now, hidden)
            rec.joined = True
            return rec
        # Any other earlier contact of the pair (an orb pop, a bolt) never
        # silences a struggle: it always plays its own FX.
        st["quiet"] = False
        fx = _cap_size(world, _spawn_fx(world, "beam_struggle", c, _deg(*a.dir), a.col, b.col, hold=STRUGGLE_TICKS,
                                        scale=scale), figs)
        held = STRUGGLE_TICKS
        hidden = ()
        if fx is not None and fx.base == "beam_struggle":
            # Anchored: the FX draws both beams from their origins (the tail
            # of each, locked now) to the node with each beam's own look, so
            # the hand-over from the real beams is seamless, and the real
            # beams are hidden while it holds.
            w = _kb_winner(a, b)
            fx.anchor_beams(looks[0], looks[1], None if w is None else (1 if w is a else 0))
            hidden = (id(a.ref), id(b.ref))
            clashfx.HIDDEN.update(hidden)
        _engage(world, figs, fx.length() if fx is not None else held)
        # Both fighters stay where they are until the struggle animation
        # (hold + finale) has played out (_finish trims it when it ends early).
        _hold_figs(world, st, figs, now + (fx.length() if fx is not None else held))
        return Clash(a, b, c, rule, now + held, fx, now, hidden)
    if rule == "beam_orb":
        fx = _spawn_fx(world, "beam_orb", c, _deg(*a.dir), a.col, b.col, budget=budget, pair=(a, b))
        held = _held_ticks(fx, BEAM_ORB_TICKS, budget)
        _engage(world, figs, _fx_ticks(fx, budget, held + 20), touch)
        return Clash(a, b, c, rule, now + held, fx, now)
    if rule == "beam_cut":
        _settle(world, a, b, c, exempt=a)   # the beam itself is never cancelled by its cutter
        # A split half never splits again (no cascade): it is just cut.
        # An ultimate's beam is split only by a cutter whose knockback beats
        # its own (a non-ultimate cutter; ultimate x ultimate rolls as usual).
        if _is_ult(a) and not _is_ult(b):
            split = b.kb > a.kb
        else:
            split = rng.random() < SPLIT_CHANCE
        if id(a.ref) not in st["halves"] and split:
            fx = _spawn_fx(world, "beam_split", c, _deg(*a.dir), a.col, b.col, budget=budget, pair=(a, b))
            _split_beam(world, st, a, c, size=_pair_size(a, b, _slot_fx("split_tip")[1]))
        else:
            fx = _spawn_fx(world, "beam_nosplit", c, _deg(*a.dir), a.col, b.col, budget=budget, pair=(a, b))
        _engage(world, figs, _fx_ticks(fx, budget, 30), touch)
        return None
    if rule == "crescent_crescent":
        fx = _spawn_fx(world, "crescent_crescent", c, ang, a.col, b.col, hold=CRESCENT_TICKS, budget=budget, pair=(a, b))
        held = _held_ticks(fx, CRESCENT_TICKS, budget)
        _engage(world, figs, fx.length() if fx is not None else held + 20, touch)
        return Clash(a, b, c, rule, now + held, fx, now)
    slot = rule     # BURST_RULES: the rule's own slot
    _settle(world, a, b, c)
    fx = _spawn_fx(world, slot, c, ang, a.col, b.col, budget=budget, pair=(a, b))
    _engage(world, figs, _fx_ticks(fx, budget, 30), touch)
    return None


def _overload(world, figs, c):
    """A tied beam struggle overloads: the blast hurts both fighters
    (OVERLOAD_HP_PCT of each one's max HP, through any damage cooldown) and
    throws each OVERLOAD_KB_PX straight away from it."""
    from . import ai, blink, motion
    spd = OVERLOAD_KB_PX * (1.0 - config.BOUNCE_FRICTION)
    for f in figs:
        if f is None or blink.gone(f) or not any(f in s.figures for s in world.sides):
            continue
        dx, dy = _norm(f.x - c[0], f.y - c[1])
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            dx = -1.0 if f is figs[0] else 1.0
        f.motion.knock_tick = -10     # always (re)start: the blast is its own hit
        motion.launch_knockback(f, dx * spd, dy * spd, world.global_tick)
        p = f.personality
        p.dmg_immune_until = 0        # the blast lands whatever hit came before it
        ai.apply_hp_damage(f, world, max(1, int(round(p.max_hp * OVERLOAD_HP_PCT / 100.0))), unblockable=True)


def _finish(world, st, rec):
    """A held clash ends: the knockback rule decides it.  A beam struggle
    with a winner ends in the winner's blowout; a tie overloads (_overload)."""
    a, b, c = rec.a, rec.b, rec.c
    if rec.fx is not None and rec.fx.anchored:
        c = rec.fx.node_world()     # the struggle ends where the node was pushed to
    clashfx.HIDDEN.difference_update(rec.hidden)
    if rec.joined:
        # Extra beams of a struggle: settled with it, no finale of their own.
        if _alive(a) and _alive(b):
            _settle(world, a, b, c)
        st["busy"].discard(id(a.ref))
        st["busy"].discard(id(b.ref))
        return
    la, lb = _alive(a), _alive(b)
    over = rec.rule == "beam_beam" and la and lb and _kb_winner(a, b) is None
    if la and lb:
        w = _settle(world, a, b, c)
        if rec.rule == "beam_beam" and w is not None:
            ang = _deg(*a.dir)
            _cap_size(world, _spawn_fx(world, "beam_struggle_end", c, ang, a.col, b.col, winner=0 if w is a else 1,
                                       scale=rec.fx.S if rec.fx is not None else None, pair=(a, b)),
                      (a.owner, b.owner))
    if rec.fx is not None and rec.fx.phase == "hold":
        rec.fx.release()
    if over:
        if rec.fx is not None:
            rec.fx.overload()
        # Released at once so the blast throws them clear.
        _hold_figs(world, st, (a.owner, b.owner), world.global_tick)
        _overload(world, (a.owner, b.owner), c)
    elif rec.rule == "beam_beam":
        # The fighters go free once the struggle's finale has played.
        fin = 0 if rec.fx is None else max(0, int(math.ceil((rec.fx.life - rec.fx.ft) / rec.fx.rate - 1e-9)))
        _hold_figs(world, st, (a.owner, b.owner), world.global_tick + fin)
    st["busy"].discard(id(a.ref))
    st["busy"].discard(id(b.ref))


# ---------------------------------------------------------------- sword duel
def _connected(b):
    """A melee effect still on its fighter: a trail, or an FX Studio effect
    with Attached motion (not deflected free, not lodged).  Everything that
    travels (and built-in crescents / bullets) is a projectile."""
    if b.kind == "trail":
        return True
    if b.kind == "inst":
        r = b.ref
        return (r.fx["motion"]["kind"] == "attached" and not getattr(r, "free", False)
                and r.lodge is None)
    return False


def _duel_busy(world, st):
    """True while a sword duel plays anywhere (an anchored one, or a Sword
    Duel FX with its stand-ins): only one at a time."""
    if st["duels"]:
        return True
    return any(fx.base == "sword_duel" and fx.alive for fx in (getattr(world, "clash_fx", None) or ()))


def _body_pt(b, c):
    """The point of body b nearest the clash point c (a projectile's
    stand-in starts its duel there)."""
    return min(b.pts, key=lambda p: (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2)


def _start_duel(world, st, a, b, c, now, budget=None, slot="trail_trail", anchor=(True, True)):
    """Start a sword duel (`slot`'s Sword Duel FX).  anchor = per side
    (a, b) whether that effect is attached to its fighter: an anchored
    fighter is moved along its side of the duel (duel_tick); an effect that
    is a projectile is cancelled and its stand-in in the FX plays its side
    from where it was.  False when it cannot (a re-arming pair, no fighter
    to anchor, both sides one fighter, or the duel would outlast the clash
    budget)."""
    fa, fb = a.owner, b.owner
    if fa is None or fb is None or fa is fb or not any(anchor):
        return False
    if not (0.0 <= c[0] <= world.screen_w and 0.0 <= c[1] <= world.screen_h):
        return False    # an off-screen contact (FX not placed yet on the fight's first tick)
    for f, on in ((fa, anchor[0]), (fb, anchor[1])):
        if on and (not f.transform.init
                   or math.hypot(f.x - c[0], f.y - c[1]) > DUEL_ANCHOR_PX * f.mode.body_scale()):
            return False    # not placed yet, or nowhere near the clash: nothing to anchor
    pair = (id(fa), id(fb))
    if now < st["duel_cd"].get(pair, -1):
        return False
    key, cfg = _slot_fx(slot)
    _base, sp = clashfx.resolve(key)
    bs = 0.5 * (fa.mode.body_scale() + fb.mode.body_scale())
    a0 = (fa.x, fa.y) if anchor[0] else _body_pt(a, c)
    b0 = (fb.x, fb.y) if anchor[1] else _body_pt(b, c)
    plan = clashfx.duel_plan(st["rng"], a0, b0, c, float(sp.get("reach", 34)) * bs,
                             strikes=sp.get("strikes", (4, 7)), bind=float(sp.get("bind", 0.3)),
                             loop=duel_loop(slot), flurry=duel_flurry(slot))
    if budget is not None and len(plan) > budget:
        return False
    fx = clashfx.spawn(world, key, c[0], c[1], angle=0.0, c1=a.col, c2=b.col,
                       scale=_pair_size(a, b, cfg), hold=-1,
                       density=float(cfg.get("density", 100)) / 100.0)
    fx.duel_slot = slot
    fx.anchor_duel(_pscale(world, c[0], c[1]), sides=anchor)
    for body, on in ((a, anchor[0]), (b, anchor[1])):
        if not on:
            _cancel(body)       # its stand-in carries on in the duel
    st["duels"].append(Duel(a, b, plan, fx, pair, anchor))
    st["duel_figs"].update(id(f) for f, on in ((fa, anchor[0]), (fb, anchor[1])) if on)
    _engage(world, tuple(f for f, on in ((fa, anchor[0]), (fb, anchor[1])) if on), len(plan))
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
        if d.final:
            _final_hit(world, st, d)
        else:
            _settle(world, d.a, d.b, c)


def _final_hit(world, st, d):
    """The duel's final hit: the knockback winner (a random one on a tie)
    launches the loser straight away from it, FINAL_KB_BASE_PX +
    FINAL_KB_PER_KB x the winning trail's knockback (capped at
    FINAL_KB_MAX_PX), whatever damage cooldown it is in, then finishes
    (_finisher).  Both fighters' "clash" actions end here."""
    w = _kb_winner(d.a, d.b)
    if w is None:
        w = d.a if st["rng"].random() < 0.5 else d.b
    win, lose = w.owner, (d.b if w is d.a else d.a).owner
    now = world.global_tick
    for f in (win, lose):
        r = getattr(f, "act", None)
        if r is not None and r.forced == "clash":
            r.forced_until = min(r.forced_until, now)
    dist = min(FINAL_KB_MAX_PX, FINAL_KB_BASE_PX + FINAL_KB_PER_KB * max(0.0, w.kb))
    _launch(world, lose, win.x, win.y, dist, -1.0 if win.transform.facing_left else 1.0)
    _finisher(world, st, win)


def _launch(world, fig, fx, fy, dist, face):
    """Throw fig dist px straight away from (fx, fy) (along `face` when on
    top of it), through any damage cooldown — a blinked-out fighter is
    untouchable."""
    from . import blink, motion
    if fig is None or dist <= 0 or blink.gone(fig):
        return
    dx, dy = _norm(fig.x - fx, fig.y - fy)
    if abs(fig.x - fx) < 1e-6 and abs(fig.y - fy) < 1e-6:
        dx, dy = face, 0.0
    spd = dist * (1.0 - config.BOUNCE_FRICTION)
    fig.motion.knock_tick = -10     # always (re)start: the final hit is its own launch
    fig.motion.heavy_until = -1000
    # Heavy: a weaker knockback landing while it slides (the two trails
    # touching again, a stray punch) can't cut the launch short.
    motion.launch_knockback(fig, dx * spd, dy * spd, world.global_tick, heavy_ticks=FINAL_HEAVY_TICKS)


def _finisher(world, st, fig):
    """The duel winner's finisher, by its HP: below FINISH_ULT_HP_PCT its
    ultimate (the Ctrl+1 / Ctrl+2 manual-ultimate path, so every fighter's
    own ultimate, built-ins included), at FINISH_SPECIAL_HP_PCT or less its
    attack_special (queued in st["finish"], _finish_specials), otherwise
    none."""
    from . import action_log
    p = fig.personality
    hp = 100.0 * p.hp / max(1e-6, p.max_hp)
    if hp < FINISH_ULT_HP_PCT:
        fig.combat.manual_ult_queued = True
        action_log.log("CLASH", f"duel finisher ultimate mode={fig.mode.key} hp={hp:.0f}%")
    elif hp <= FINISH_SPECIAL_HP_PCT:
        st["finish"].append((fig, world.global_tick + FINISH_WAIT_TICKS))
        action_log.log("CLASH", f"duel finisher attack_special mode={fig.mode.key} hp={hp:.0f}%")


def _finish_specials(world, st):
    """Fire each queued duel-finisher attack_special as soon as its fighter
    is free: an image character plays its own action (actions.force_special),
    a JSON character fires its attack_special FX (combat.fire_json_action);
    a built-in fighter has none.  Dropped after FINISH_WAIT_TICKS, or when
    its fighter is gone."""
    from . import actions, combat
    if not st["finish"]:
        return
    now, keep = world.global_tick, []
    for fig, until in st["finish"]:
        if now > until or not any(fig in s.figures for s in world.sides):
            continue
        if actions.is_image(fig):
            if not actions.force_special(fig, world):
                keep.append((fig, until))
            elif getattr(fig, "act", None) is not None and fig.act.playing == "attack_special":
                st["finishing"][id(fig)] = now    # _engage leaves this special alone
            continue
        char = getattr(fig.mode, "character", None)
        if char and (char.get("actions") or {}).get("attack_special"):
            if fig.combat.busy:
                keep.append((fig, until))
                continue
            foes = [f for s in world.sides if fig not in s.figures for f in s.figures]
            if foes:
                t = min(foes, key=lambda f: (f.x - fig.x) ** 2 + (f.y - fig.y) ** 2)
                combat.fire_json_action(fig, world, "attack_special", t.x, t.y)
    st["finish"] = keep


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
    x, y, opp_x, swing, own = pose
    t = fig.transform
    ox, oy = t.x, t.y
    m = DUEL_MARGIN
    t.x = max(m, min(fig.screen_w - m, x))
    t.y = max(m, min(fig.screen_h - m, y))
    fig.face(ox, oy)
    if fig.aim is None:
        t.facing_left = opp_x < t.x     # always squared up to the other side (fighter or stand-in)
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
        if d.i < len(d.plan) and d.plan[d.i][5] == "release":
            # The big clash has landed: the final hit ends the duel here
            # (no walk back), launching the loser (_final_hit).
            d.final = True
        if d.final or d.i >= len(d.plan) or not _duel_fielded(world, d):
            _duel_end(world, st, d)
            continue
        fr = d.plan[d.i]
        d.i += 1
        # (x, y, the other side's x in the plan, swing, owns frames)
        if d.anchor[0]:
            poses[id(d.fa)] = (fr[0], fr[1], fr[2], fr[6], d.owns[0])
        if d.anchor[1]:
            poses[id(d.fb)] = (fr[2], fr[3], fr[0], fr[6], d.owns[1])
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
    for k in [k for k, e in st["held"].items() if now >= e[1]]:
        del st["held"][k]
    # 1b. Sword duels: where each dueling fighter is this tick; then any
    #     duel finisher special waiting for its fighter to be free.
    _duels(world, st)
    _finish_specials(world, st)
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
            if _overpower(world, a, b, c):
                continue    # the weaker is gone, the stronger flies on
            st["quiet"] = _quiet(st, a, b, c, now)
            try:
                rec = _start(world, st, a, b, c, rule, now)
            finally:
                st["quiet"] = False
            if rec is not None:
                st["active"].append(rec)
                busy.add(id(a.ref))
                busy.add(id(b.ref))
    # forget pairs apart for a while
    if len(seen) > 256 or now % 60 == 0:
        for k in [k for k, t in seen.items() if now - t > REARM_TICKS * 3]:
            del seen[k]
        rc = st["recent"]
        for k in [k for k, r in rc.items() if now - r[0] > MERGE_TICKS]:
            del rc[k]
