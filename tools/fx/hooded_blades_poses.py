#!/usr/bin/env python3
"""Hooded Blades -- Rig Forge key poses (source of truth for characters/hooded_blades).

Writes tools/fx/sources/HoodedBlades_rigforge.json, a pb_character v2 file in
Rig Forge's own pose format (rig, two weapons, added lines, every action's
keyframes with tween / hold / ease / layer order).  tools/fx/hooded_blades_bake.js
then loads it into rigforge.html (headless) and runs Rig Forge's own package
export, so the PNG frames, anchors and the embedded "rigforge" block are exactly
what Rig Forge itself would write; "Import package..." reopens every key.

Pose convention (house rules, combat-motion playbook s.2):
  limbs 0 = straight down, + toward facing (right); spine 0 = up, + leans forward.
  Forearm / shin angles are relative to their parent (Rig Forge).
  B = blade WORLD angle in the same limb convention (0 down, 90 forward,
  180 up, -90 back).  Rig Forge's weapon angle runs the other way vertically
  (wang 0 = up), so wp = 180 - B - (ua + fa) -- done here, never by hand.

Grounded keys are planted: ry is solved so the lowest foot sits on the idle
ground line (playbook QA 3).  Airborne keys give `air` = height above it.

usage: hooded_blades_poses.py [--check]
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rigforge_bake as rb  # noqa: E402  (exact Python port of rigforge.html joints())

OUT = os.path.join(HERE, "sources", "HoodedBlades_rigforge.json")

# ------------------------------------------------------------------ rig
# Head is the ruler (head radius 22).  Short, chibi limbs so poses must swing
# through big angles to read; head ~45 % of standing height (the 60 % house
# ratio leaves no room for a readable torso with Rig Forge's neck offset).
BONES = dict(ua=18, fa=17, th=16, sh=18, torso=27, head=22)
PIVOTS = dict(shoulder_x=0, shoulder_y=2, hip_x=0, hip_y=0, side_separation=4)
WIDTHS = {   # [start %, end %] of the layer's default width (10 units x layer w)
    "near_upper_arm": [105, 85], "far_upper_arm": [100, 80],
    "near_forearm": [90, 72], "far_forearm": [85, 68],
    "near_thigh": [110, 82], "far_thigh": [105, 78],
    "near_shin": [85, 60], "far_shin": [80, 58],
    "shoulder_girdle": [140, 105], "upper_spine": [170, 175],
    "lower_spine": [190, 150], "pelvis_girdle": [130, 110],
    "weapon": [110], "weapon2": [110],
    # one long tapered back tail = the coat's silhouette; a short front flap
    "x:hood": [300, 18], "x:coat_b": [150, 25], "x:coat_f": [95, 40],
}
# Added lines: hood point off the back of the head, two coat panels off the hip.
# ang = rest angle off the parent bone (head points up the neck; hip = 180 = up).
LINES = [
    dict(id="hood", name="hood point", at="head", len=36, ang=72, far=False, w=1),
    dict(id="coat_b", name="coat tail (back)", at="hip", len=30, ang=146, far=False, w=1),
    dict(id="coat_f", name="coat tail (front)", at="hip", len=12, ang=200, far=False, w=1),
]
# Straight blade + crossguard, pointing +x from the grip; tip = largest x.
BLADE = [[-8, -1.8], [0, -1.8], [0, -6.2], [2.6, -6.2], [2.6, -2.7], [55, -2.7], [63, 0],
         [55, 2.7], [2.6, 2.7], [2.6, 6.2], [0, 6.2], [0, 1.8], [-8, 1.8]]
GRIP = -4.0          # handle centre sits in the hand
BLADE_MID = 30.0     # blade centre (used when a blade flies free)

RIG = dict(bones=BONES, pivots=PIVOTS)
CH_RIG = {"rig": RIG, "weapon": {"points": BLADE, "attach": "haR"},
          "weapon2": {"points": BLADE, "attach": "haL"}}
RIGP = rb.rig_of(CH_RIG)
SHAPES = rb.weapon_shapes(CH_RIG)

DEFAULT_ORDER = ["far_upper_arm", "far_forearm", "weapon2", "far_thigh", "far_shin",
                 "pelvis_girdle", "x:coat_b", "x:coat_f", "lower_spine", "upper_spine",
                 "shoulder_girdle", "head", "x:hood", "near_thigh", "near_shin",
                 "near_upper_arm", "near_forearm", "weapon"]


def K(sp=0, sp2=0, hd=0, n=(40, 50, 140), f=(-30, -30, -120), nl=(45, -45), fl=(-40, 10),
      rx=0, air=None, coat=0, coatf=0, hood=0, wlen=1, w2len=1, rot=0,
      shr=(0, 0), shl=(0, 0), hold=0, steps=0, ease="inout", dirn="short",
      free=None, order=None, note=""):
    """One key.  n / f = near / far arm (upper-arm, forearm, blade world angle).
    nl / fl = near / far leg (thigh, shin).  free = {0|1: (gx, gy, B, wlen)}
    flies weapon 0/1 free of the hand: its blade centre at hip-relative (gx, gy)."""
    return dict(sp=sp, sp2=sp2, hd=hd, n=n, f=f, nl=nl, fl=fl, rx=rx, air=air, coat=coat,
                coatf=coatf, hood=hood, wlen=wlen, w2len=w2len, rot=rot, shr=shr, shl=shl,
                hold=hold, steps=steps, ease=ease, dirn=dirn, free=free or {}, order=order, note=note)


def wrap(a):
    return (a + 180.0) % 360.0 - 180.0


def raw_pose(k, ry=0.0):
    nua, nfa, nB = k["n"]
    fua, ffa, fB = k["f"]
    p = dict(rb.PDEF)
    p.update(rx=k["rx"], ry=ry, rot=k["rot"], sp=k["sp"], sp2=k["sp2"], hd=k["hd"],
             rua=nua, rfa=nfa, lua=fua, lfa=ffa,
             rth=k["nl"][0], rsh=k["nl"][1], lth=k["fl"][0], lsh=k["fl"][1],
             shrx=k["shr"][0], shry=k["shr"][1], shlx=k["shl"][0], shly=k["shl"][1],
             wp=wrap(180 - nB - nua - nfa), wpx=GRIP, wlen=k["wlen"],
             w2p=wrap(180 - fB - fua - ffa), w2px=GRIP, w2len=k["w2len"])
    return p


GROUND = None


def foot_low(p):
    j = rb.joints(p, RIGP, SHAPES)
    return max(j["ftL"][1], j["ftR"][1])


def solve(k):
    """Rig Forge pose dict for key k (planted / airborne, free blades placed)."""
    p = raw_pose(k, 0.0)
    ry = GROUND - foot_low(p)
    if k["air"]:
        ry -= k["air"]
    p["ry"] = round(ry, 3)
    if k["free"]:
        j = rb.joints(p, RIGP, SHAPES)
        hip = j["hip"]
        for wi, (gx, gy, B, wl) in k["free"].items():
            pk, pxk, pyk, lk, hand = (("wp", "wpx", "wpy", "wlen", "haR") if wi == 0
                                      else ("w2p", "w2px", "w2py", "w2len", "haL"))
            ang = (p["rua"] + p["rfa"]) if wi == 0 else (p["lua"] + p["lfa"])
            p[pk] = wrap(180 - B - ang)
            wang = ang + p[pk]
            wa = math.radians(wang - 90)
            H = j[hand]
            dx, dy = hip[0] + gx - H[0], hip[1] + gy - H[1]
            lx = dx * math.cos(wa) + dy * math.sin(wa)        # R^T (G - H)
            ly = -dx * math.sin(wa) + dy * math.cos(wa)
            p[lk] = wl
            p[pxk] = round(BLADE_MID - lx / wl, 3)
            p[pyk] = round(-ly, 3)
    for kk in ("wp", "w2p", "sp", "sp2", "hd"):
        p[kk] = round(p[kk], 3)
    p["_xl"] = {"hood": [k["hood"], 1], "coat_b": [k["coat"], 1], "coat_f": [k["coatf"], 1]}
    p["_tween"] = {"on": k["steps"] > 0, "steps": max(1, k["steps"]), "ease": k["ease"],
                   "dir": k["dirn"], "hold": k["hold"]}
    p["_layers"] = {"order": k["order"] or DEFAULT_ORDER, "hidden": {}}
    if k["note"]:
        p["_note"] = k["note"]
    return p


# ------------------------------------------------------------------ poses
# Guard: low, wide, coiled.  Near blade reaches forward-up at the enemy, far
# blade reverse-grip trailing back-up: two diverging lines = an "X" read.
READY = dict(sp=18, sp2=6, hd=-12, n=(38, 52, 138), f=(-28, -34, -122), nl=(52, -50), fl=(-42, 12),
             coat=0, hood=0)


def ready(**over):
    d = dict(READY); d.update(over); return K(**d)


ORBIT_POSE = dict(sp=-6, sp2=-4, hd=14, n=(122, 18, 150), f=(-122, -18, -150),
                  nl=(48, -40), fl=(-46, 14), coat=10, hood=10)


def orbit_key(t_deg, hold=0):
    """Both blades circling the body (ellipse round the chest, blade tangent).
    t = 0 front, 90 near side (toward camera), 180 back, 270 far side."""
    free, behind = {}, []
    for wi, off in ((0, 0), (1, 180)):
        t = math.radians(t_deg + off)
        gx, gy = 58 * math.cos(t) + 4, -30 + 13 * math.sin(t)
        # blade along the ellipse tangent (sd convention: angle = atan2(x, y));
        # full length crossing in front / behind, foreshortened at the sides
        # each blade also spins end over end as it flies (boomerang read):
        # 1.5 blade turns per orbit; the far-side blade is half a turn ahead
        B = 90 + 1.5 * (t_deg + off)
        wl = round(0.55 + 0.45 * abs(math.cos(t)), 3)   # shorter at the sides (depth)
        free[wi] = (gx, gy, B, round(wl, 3))
        if math.sin(t) < 0:
            behind.append("weapon" if wi == 0 else "weapon2")
    order = [x for x in DEFAULT_ORDER if x not in ("weapon", "weapon2")]
    for w in ("weapon", "weapon2"):
        if w in behind:
            order.insert(0, w)
        else:
            order.append(w)
    d = dict(ORBIT_POSE)
    return K(**d, free=free, order=order, hold=hold, note="orbit t=%d" % t_deg)


ACTIONS = {}

# idle: breathing guard, blade weight sways (sine-like inout, loops)
ACTIONS["idle"] = (1300, [
    ready(steps=5, ease="inout", note="guard"),
    ready(sp=22, hd=-10, n=(34, 56, 132), f=(-24, -36, -128), nl=(56, -56), fl=(-44, 14),
          coat=4, hood=3, steps=5, ease="inout", note="guard, breathe in (sink)"),
])

# run: forward lean, both blades streaming back, coat trailing (4 keys, loops)
RUN_ARMS = dict(sp=34, sp2=6, hd=-14, coat=-34, coatf=-20, hood=-14)
ACTIONS["run"] = (440, [
    K(**RUN_ARMS, n=(-78, 22, -96), f=(-58, 14, -132), nl=(66, -26), fl=(-58, -38), steps=2, note="contact, near foot ahead"),
    K(**RUN_ARMS, n=(-70, 26, -92), f=(-64, 12, -136), nl=(18, -80), fl=(-6, -12), steps=2, note="pass, near knee up"),
    K(**RUN_ARMS, n=(-84, 20, -98), f=(-52, 16, -130), nl=(-58, -38), fl=(66, -26), steps=2, note="contact, far foot ahead"),
    K(**RUN_ARMS, n=(-72, 24, -94), f=(-62, 12, -134), nl=(-6, -12), fl=(18, -80), steps=2, note="pass, far knee up"),
])

# 1 dash-in: sink, explode forward flat (one diagonal line foot->head),
# blades streaming behind, brake into guard.
ACTIONS["attack_normal"] = (None, [
    ready(steps=2, ease="in", note="guard"),
    K(sp=12, sp2=4, hd=-18, n=(-62, -18, -100), f=(-44, -30, -150), nl=(84, -112), fl=(-46, -44),
      coat=6, hood=4, hold=1, steps=1, ease="in3", note="coil: sink, blades swept low-back"),
    K(sp=56, sp2=8, hd=-22, n=(-104, 10, -92), f=(-130, 18, -128), nl=(74, -64), fl=(-70, -4),
      rx=34, coat=-58, coatf=-40, hood=-30, steps=2, ease="out", note="DASH: flat lunge, foot-to-head diagonal"),
    K(sp=26, sp2=6, hd=-12, n=(44, 58, 128), f=(-34, -40, -132), nl=(62, -58), fl=(-52, 8),
      rx=44, coat=22, coatf=14, hood=10, hold=2, steps=3, ease="inout", note="brake: plant, coat swings past"),
    ready(rx=0, note="guard (feet re-planted)"),
])

BLADE_BEHIND_HEAD = ["far_upper_arm", "far_forearm", "weapon2", "far_thigh", "far_shin", "pelvis_girdle",
                     "x:coat_b", "x:coat_f", "lower_spine", "upper_spine", "shoulder_girdle", "weapon",
                     "near_upper_arm", "near_forearm", "head", "x:hood", "near_thigh", "near_shin"]

# 2 overhead slash: lean back and load the near blade behind the head,
# far blade guards forward; then whip over the top into a full-reach lunge.
ACTIONS["attack_normal_2"] = (None, [
    ready(steps=1, ease="in", note="guard"),
    K(sp=-4, sp2=-4, hd=0, n=(-70, -10, -100), f=(56, 46, 146), nl=(40, -48), fl=(-38, 14),
      coat=4, hood=4, steps=1, ease="in", note="bd: near blade pulled down-back (keeps the wind-up behind the body)"),
    K(sp=-22, sp2=-10, hd=12, n=(-150, -22, -138), f=(72, 42, 152), nl=(34, -48), fl=(-36, 16),
      coat=10, hood=14, hold=1, steps=1, ease="in3", order=BLADE_BEHIND_HEAD,
      note="LOAD: lean back, near blade cocked behind head (drawn under it)"),
    K(sp=26, sp2=8, hd=-10, n=(124, 10, 112), f=(-60, 18, -96), nl=(58, -52), fl=(-50, 6),
      rx=10, coat=-20, hood=-10, steps=1, ease="out", note="breakdown: blade overhead, far arm pulls back"),
    K(sp=38, sp2=12, hd=-12, n=(96, -4, 76), f=(-100, 14, -112), nl=(80, -66), fl=(-66, 0),
      rx=22, wlen=1.15, coat=24, coatf=18, hood=12, hold=3, steps=3, ease="out",
      note="CONTACT: full-reach lunge, blade stretched (reach exaggeration)"),
    ready(note="guard"),
])

# 3 rising slash: crouch with the near blade crossed low in front, then
# rocket up onto the toes, blade finishing straight up-back.
ACTIONS["attack_normal_3"] = (None, [
    ready(steps=1, ease="in", note="guard"),
    K(sp=34, sp2=8, hd=-20, n=(30, 66, 76), f=(-104, -12, -134), nl=(76, -108), fl=(-48, -34),
      coat=4, hood=6, hold=1, steps=1, ease="in3", note="COIL: deep crouch, blade crossed low in front"),
    K(sp=8, sp2=2, hd=-4, n=(100, 16, 112), f=(-84, -10, -120), nl=(44, -48), fl=(-36, 0),
      rx=8, coat=-10, steps=1, ease="out", note="breakdown: rising, blade passes forward"),
    K(sp=-22, sp2=-8, hd=16, n=(148, 14, 168), f=(62, 12, 62), nl=(14, -8), fl=(-26, 12),
      rx=12, air=7, coat=-26, coatf=-20, hood=-16, hold=3, steps=3, ease="out",
      note="CONTACT: up on the toes, blade straight up-back, far blade counters low-forward"),
    ready(note="guard"),
])

# 4 back-jump: sink, spring up and back into a tucked spread-X, land low.
ACTIONS["attack_normal_4"] = (None, [
    ready(steps=1, ease="in", note="guard"),
    K(sp=26, sp2=4, hd=-14, n=(10, 80, 126), f=(-62, -22, -134), nl=(86, -118), fl=(-48, -44),
      hold=1, steps=1, ease="in3", note="sink: knees loaded"),
    K(sp=-26, sp2=-8, hd=10, n=(124, 22, 168), f=(-132, -24, -168), nl=(96, -128), fl=(64, -116),
      rx=-34, air=40, coat=40, coatf=30, hood=24, hold=1, steps=2, ease="out",
      note="APEX: tucked knees, blades flung wide (spread X)"),
    K(sp=30, sp2=6, hd=-12, n=(54, 42, 106), f=(-70, -30, -108), nl=(84, -104), fl=(-52, -32),
      rx=-44, coat=-18, hood=-10, hold=2, steps=3, ease="inout", note="land: low, blades wide"),
    ready(note="guard"),
])

SPIN = dict(sp=2, sp2=0, hd=-6, nl=(32, -32), fl=(-36, 12), hood=-4)
SPIN_BEHIND_N = ["weapon", "far_upper_arm", "far_forearm", "far_thigh", "far_shin", "pelvis_girdle",
                 "x:coat_b", "x:coat_f", "lower_spine", "upper_spine", "shoulder_girdle", "head", "x:hood",
                 "near_thigh", "near_shin", "near_upper_arm", "near_forearm", "weapon2"]

# 5 spin: twist away, whip round (arms swap sides, back blade foreshortens),
# finish with the near blade at full reach.
ACTIONS["attack_normal_5"] = (None, [
    ready(steps=1, ease="in", note="guard"),
    K(sp=22, sp2=-6, hd=-10, n=(-104, -22, -124), f=(-74, -30, -118), nl=(70, -92), fl=(-42, -26),
      shr=(-6, 0), shl=(4, 0), coat=8, hood=8, hold=1, steps=1, ease="in3", note="WIND: chest twisted away, both blades back"),
    # 1.5 turns, one key per quarter, no tweens: each quarter is its own frame
    # (speed from the frames not drawn).  Arms stay flat out; a blade pointing
    # at / away from the camera is foreshortened (wlen) and a blade behind the
    # body is drawn under it (layer order).
    K(**SPIN, n=(-70, 0, -78), f=(70, 0, 78), wlen=0.32, w2len=0.32, rx=3, coat=-10,
      note="1/4: near blade swings at the camera (foreshortened)"),
    K(**SPIN, n=(92, 0, 92), f=(-92, 0, -92), rx=6, coat=-24, coatf=-16, note="1/2: blades flat out front / back"),
    K(**SPIN, n=(70, 0, 78), f=(-70, 0, -78), wlen=0.32, w2len=0.4, rx=9, coat=-6, order=SPIN_BEHIND_N,
      shr=(-8, 0), shl=(8, 0), note="3/4: back to camera, near blade behind"),
    K(**SPIN, n=(-92, 0, -92), f=(92, 0, 92), rx=12, coat=22, coatf=14, order=SPIN_BEHIND_N,
      shr=(-8, 0), shl=(8, 0), note="1: blades swapped, near blade behind"),
    K(**SPIN, n=(-70, 0, -78), f=(70, 0, 78), wlen=0.32, w2len=0.32, rx=15, coat=8,
      note="1 1/4: near blade at the camera again"),
    K(sp=16, sp2=4, hd=-10, n=(96, -6, 86), f=(-104, 10, -96), nl=(60, -56), fl=(-56, 10),
      rx=18, wlen=1.15, coat=30, coatf=22, hood=12, hold=3, steps=3, ease="out",
      note="CONTACT: wide stance, near blade at full reach"),
    ready(note="guard"),
])

# 6 launch: deepest crouch, explode straight up (one vertical line), freeze
# at the apex in a flying-knee cross, drop into a landing crouch.
ACTIONS["attack_normal_6"] = (None, [
    ready(steps=1, ease="in", note="guard"),
    K(sp=42, sp2=10, hd=-24, n=(-62, 2, -100), f=(-62, -8, -112), nl=(96, -128), fl=(-56, -46),
      coat=10, hood=8, hold=2, steps=1, ease="in3", note="LOAD: deepest crouch, blades low behind"),
    K(sp=-4, sp2=-4, hd=8, n=(150, 6, 140), f=(-160, 0, 218), nl=(8, 6), fl=(-10, 16),
      rx=8, air=34, wlen=1.1, w2len=1.1, coat=-4, coatf=-4, hood=-20, steps=1, ease="out",
      note="LAUNCH: one straight vertical line, blades up"),
    K(sp=12, sp2=6, hd=-6, n=(138, 22, 142), f=(168, -26, 214), nl=(84, -96), fl=(-22, 12),
      rx=16, air=60, coat=34, coatf=26, hood=16, hold=4, steps=3, ease="inout",
      note="APEX HIT: flying knee, blades crossed forward-up / up-back"),
    K(sp=32, sp2=8, hd=-12, n=(68, 34, 102), f=(-68, -34, -102), nl=(90, -112), fl=(-50, -36),
      rx=20, coat=-20, coatf=-12, hood=-10, hold=2, steps=3, ease="inout", note="land: crouch, blades wide"),
    ready(note="guard"),
])

# 7 blade orbit + catch: arms flung open in a V, both blades circle the body
# (one blade in front while the other is behind), then snap back to the hands.
ACTIONS["attack_normal_7"] = (None, [
    ready(steps=1, ease="in", note="guard"),
    K(sp=-2, sp2=-2, hd=6, n=(108, 4, 108), f=(-108, -4, -108), nl=(46, -40), fl=(-46, 14),
      coat=-12, hood=-6, steps=1, ease="out", note="FLING: arms snap open, blades leave the hands"),
    orbit_key(0), orbit_key(45), orbit_key(90), orbit_key(135),
    orbit_key(180), orbit_key(225), orbit_key(270), orbit_key(315, hold=0),
    K(sp=16, sp2=6, hd=-10, n=(78, 34, 122), f=(-62, -30, -150), nl=(62, -56), fl=(-54, 18),
      coat=26, coatf=18, hood=12, hold=5, steps=3, ease="inout",
      note="CATCH: wide stance, forward blade up, reverse-grip blade back"),
    ready(note="guard"),
])


def playlen(keys):
    n = 0
    for i, k in enumerate(keys):
        n += 1 + k["hold"]
        if k["steps"] > 0 and len(keys) > 1:
            n += k["steps"]
    return n


# ------------------------------------------------------------------ QA (playbook s.8)
ANG = ("sp", "sp2", "hd", "lua", "lfa", "rua", "rfa", "lth", "lsh", "rth", "rsh", "wp", "w2p", "rot")


def check(name, keys, poses):
    msgs = []
    for i, p in enumerate(poses):
        j = rb.joints(p, RIGP, SHAPES)
        for tip in ("wtip", "wtip2"):
            if j[tip][1] > GROUND + 1.5:
                msgs.append("%s key %d: %s %.1f below ground" % (name, i, tip, j[tip][1] - GROUND))
        if keys[i]["air"] is None and abs(foot_low(p) - GROUND) > 0.01:
            msgs.append("%s key %d: foot off ground" % (name, i))
        nx = (i + 1) % len(poses)
        if keys[i]["steps"] > 0 and (nx or name in ("idle", "run")):
            for a in ANG:
                d = abs(wrap(poses[nx][a] - p[a]))
                if d > 150 and a not in ("wp", "w2p"):
                    msgs.append("%s key %d->%d: %s steps %.0f deg (> 150)" % (name, i, nx, a, d))
    return msgs


def build():
    global GROUND
    GROUND = 0.0
    GROUND = foot_low(raw_pose(READY_K, 0.0))
    actions, report = {}, []
    for name, (dur, keys) in ACTIONS.items():
        if name not in ("idle", "run"):
            keys[-1]["steps"] = 0          # clip ends on guard, never tweens back to its start
        poses = [solve(k) for k in keys]
        n = playlen(keys)
        ms = dur or int(round(n * 17))     # house cadence ~17 ms / frame for attacks
        trig = {"idle": "always", "run": "moving"}.get(name, "in_range")
        actions[name] = dict(trigger=trig, duration_ms=ms, retrigger_cooldown_ms=0, keyframes=poses)
        report.append("%-16s %2d keys %3d frames %5d ms" % (name, len(keys), n, ms))
        report += check(name, keys, poses)
    ch = {
        "format": "pb_character", "version": 2,
        "name": "hooded_blades", "display_name": "Hooded Blades",
        "description": "Hooded dual-blade duellist: explosive dashes, overhead and rising cuts, "
                       "a back-jump, a spin, a launch to an apex hit and a blade orbit. Rig Forge rig.",
        "archetype": "New",
        "predicates": {"can_shoot": False, "uses_melee": True, "retreats": False, "charges_full": True},
        "movement": {"wander_strength": 0.15},
        "stats": {"max_hp": 100, "chase_speed": 0.9, "follow_speed": 0.9, "scale": 1.0, "basic_attack_radius": 180},
        "rig": {"bones": BONES, "pivots": PIVOTS, "widths": WIDTHS, "lines": LINES, "anchors": []},
        "palette": {"body": "#2b2f45", "accent": "#8fd0ff"},
        "defense": [],
        "weapon": {"points": BLADE, "shapes": [BLADE], "attach": "haR", "weight": 0},
        "weapon2": {"points": BLADE, "shapes": [BLADE], "attach": "haL", "weight": 0},
        "special_ability": None,
        "actions": actions,
    }
    return ch, report


READY_K = ready()

if __name__ == "__main__":
    ch, rep = build()
    print("\n".join(rep))
    if "--check" not in sys.argv:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w") as fh:
            json.dump(ch, fh, indent=1)
        print("wrote", OUT)
