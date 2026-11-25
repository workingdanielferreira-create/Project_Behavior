"""Hooded Blades' authored 3D clips, written into characters/hooded_blades/hooded_blades.anim3d.json. One move at a
time, each reviewed by Daniel from GIF stills beside the 2D frames.

    python v3/tools/hooded/gen_hooded.py attack_normal_2                    rewrite that clip's key poses
    python v3/tools/anim3d.py hooded_blades --check --clips attack_normal_2 audit
    python v3/tools/anim3d.py hooded_blades --clips attack_normal_2         bake ONLY that clip into the .glb

attack_normal (hit 1) is NOT authored here: the .glb holds Daniel's own Rig Forge 3D version (kept, Daniel
2026-11-25). A full `retarget2d.py hooded_blades` rebuild regenerates every clip not in the spec from the 2D frames,
so it would wipe it: don't run that on Hooded Blades.

Body space: +Z = the target, +Y up, -X = his right (near) side, metres, deg. Chest / head are given in WORLD terms
(gen_puck.key): [yaw (+ turn left), pitch (+ lean to where the chest faces), roll (+ tip right)]. Both blades in a
FORWARD grip; arm `blade` = where the blade points.
"""
import json, math, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', 'puck'))
from gen_puck import key, foot, r3  # noqa: E402

OUT = os.path.join(HERE, '..', '..', '..', 'characters', 'hooded_blades', 'hooded_blades.anim3d.json')
F = 0.021875                    # 2D frame_ms (32 frames, 700 ms)


def fr(n):
    """time of 2D frame n (1-based)"""
    return round((n - 1) * F, 4)


def spun(fdict, th, c):
    """A foot control turned th deg (turn left) round the body point c = (x, z): position, yaw and knee."""
    a = math.radians(th)
    ca, sa = math.cos(a), math.sin(a)
    x, y, z = fdict["ankle"]
    dx, dz = x - c[0], z - c[1]
    k = fdict["knee"]
    out = dict(fdict)
    out["ankle"] = r3([c[0] + dx * ca + dz * sa, y, c[1] - dx * sa + dz * ca])
    out["knee"] = r3([k[0] * ca + k[2] * sa, k[1], -k[0] * sa + k[2] * ca])
    out["yaw"] = round(fdict["yaw"] + th, 1)
    return out


# ---------------------------------------------------------------- attack_normal_2: Oathkeeper & Oblivion flurry
# 2D (32 frames x 21.9 ms): f1-12 low crouch, both blades level and swept BACK (the wind-up, a moving hold); f13-16 the
# right blade sweeps round to the target (horizontal slash), the left trails back low, and he rises onto the FRONT leg
# with the back leg lifted behind; f17-19 opened out, arms straight front and back on one line; f20 a turn with both
# blades up (a pivot spin, feet together); f21-25 the spread again (second horizontal slash), standing taller;
# f26-28 both blades up and back, then down crossing in an X in front; f29-31 recovery, f32 back in the low wind-up.
# Feel (Daniel): ZZZ snap and weight on the hits, KH (Oathkeeper & Oblivion) spins and arcs between them.
# Physics (skill review question 2): no foot moves faster than ~7.5 m/s, the hips cross the ground <= ~6 m/s; the
# spin pivots on the balls of the feet 18 cm apart, so the 2D's one-frame turn takes ~90 ms here.
FRONT, BACK = (-0.12, 0.30), (0.10, -0.38)      # wind-up stance: right foot forward, left back (~0.7 m apart)
SUP = (-0.12, 0.30)                             # the right (front) foot: support on the hits and the spin's pivot
HX = -0.18                                      # hips over the support foot while the back leg is up (r2 audit: the
                                                # centre of mass sat 12 cm to his left of the standing foot)


def attack_normal_2():
    K = []
    fR = lambda **kw: foot(FRONT[0], FRONT[1], **{"yaw": -15, "knee": (-0.2, 0.2, 1), **kw})
    fL = lambda **kw: foot(BACK[0], BACK[1], **{"yaw": 35, "pitch": 30, "knee": (0.3, -0.5, 1), **kw})
    up_back = foot(0.10, -0.06, y=0.26, pitch=55, yaw=20, knee=(0.2, -1, 0.3))      # back leg lifted behind, toes pointed

    # f1 wind-up: deep and low, hips coiled right, chest wrung further back and leaning in, head glaring at the target;
    # both arms reach back, blades level behind him (upper at the shoulder, lower one angled down)
    K.append(key(fr(1), "inout", [0, -0.40, -0.02], [-35, 28, 4], [-75, 40, 12], [-10, 22, 0],
                 ([-0.10, -0.04, -0.54], [-0.6, -1, 0.1], [-0.1, 0.05, -1], [6, -20]),
                 ([-0.42, -0.18, -0.30], [0.2, -1, 0.3], [-0.15, -0.15, -1]),
                 fR(), fL(), label="f1 wind-up: low, blades swept back"))
    # f10 moving hold: sinks and coils a little further
    K.append(key(fr(10), "inout", [0, -0.43, -0.05], [-40, 30, 5], [-82, 42, 14], [-12, 22, 0],
                 ([-0.08, -0.02, -0.56], [-0.6, -1, 0.1], [-0.1, 0.08, -1], [8, -24]),
                 ([-0.44, -0.16, -0.30], [0.2, -1, 0.3], [-0.15, -0.22, -1]),
                 fR(), fL(), label="f10 coil (moving hold)"))
    # f13 HIT 1: horizontal slash - the back foot pushes off and lifts behind, hips whip left and drive over the front
    # foot, chest a beat behind; the right arm sweeps round straight at the target, blade level; the left trails back
    K.append(key(fr(13), "snap", [HX, -0.30, 0.26], [35, 30, -4], [22, 48, -8], [0, 24, 0],
                 ([0.04, 0.0, 0.62], [-1, -0.3, 0], [0.15, 0.04, 1], [-6, 26]),
                 ([0.10, -0.26, -0.46], [0.5, -1, 0], [0.2, -0.35, -1], [0, -14]),
                 fR(), fL(pitch=55, knee=(0.2, -0.2, 1)), bease="linear", label="f13 HIT 1: right blade sweeps to the target"))
    # f15 overshoot: the chest whips on past the hips
    K.append(key(fr(15), "out", [HX, -0.29, 0.28], [42, 32, -5], [50, 46, -10], [6, 24, 0],
                 ([0.18, 0.02, 0.60], [-1, -0.3, 0.2], [0.35, 0.06, 1], [-8, 28]),
                 ([0.08, -0.24, -0.50], [0.5, -1, 0], [0.2, -0.3, -1], [0, -16]),
                 fR(), up_back, label="f15 overshoot"))
    # f17 opened out: side-on, right shoulder to the target, arms straight out front and back on one line, front
    # blade rising, rear blade down; tipped toward the target over the standing leg, back leg reaching out behind
    K.append(key(fr(17), "out", [HX, -0.27, 0.26], [55, 22, -6], [85, 8, 28], [20, 22, 4],
                 ([0.0, 0.08, 0.62], [-0.3, -1, 0], [0.1, 0.35, 1], [-4, 24]),
                 ([0.0, -0.10, -0.62], [0.3, -1, 0], [0.0, -0.3, -1], [0, -20]),
                 fR(), foot(0.10, -0.10, y=0.30, pitch=60, yaw=20, knee=(0.2, -1, 0.2)), label="f17 spread"))

    # f20 pivot spin to the left (KH): the lifted foot comes down beside the standing one, he rises onto the balls of
    # both feet and turns a full circle round them, both blades up, hands in at the chest; head spots the target
    c = (-0.03, 0.30)
    gR = foot(-0.12, 0.30, pitch=25, yaw=40, knee=(-0.3, 0.1, 1))
    gL = foot(0.06, 0.30, pitch=25, yaw=60, knee=(0.3, 0.1, 1))
    up_R = ([-0.06, -0.26, 0.26], [-0.8, -1, -0.2], [0.05, 1, 0.15])
    up_L = ([0.06, -0.26, 0.26], [0.8, -1, -0.2], [-0.05, 1, 0.15])
    for t, ease, th, lab in ((0.43, "in", 0, "f20 gather: feet together, blades up"), (0.46, "linear", 120, "spin 120"),
                             (0.49, "linear", 240, "spin 240")):
        K.append(key(t, ease, [-0.05, -0.16, 0.30], [80 + th, 10, 0], [95 + th, 12, 6], [60 + th * 0.8, 14, 0],
                     up_R, up_L, spun(gR, th, c), spun(gL, th, c), label=lab))
    # f23 HIT 2: out of the spin straight into the spread, standing taller (2D f21-25): side-on, right blade at the
    # target, the front foot stepping on a little
    sR = foot(-0.12, 0.30, yaw=-10, knee=(-0.2, 0.2, 1))
    sL = foot(0.04, 0.20, pitch=35, yaw=40, knee=(0.3, -0.3, 1))
    K.append(key(0.52, "snap", [-0.07, -0.22, 0.26], [415, 18, -6], [445, 8, 26], [380, 22, 4],
                 ([0.0, 0.04, 0.62], [-0.3, -1, 0], [0.12, 0.05, 1], [-4, 26]),
                 ([0.0, -0.06, -0.62], [0.3, -1, 0], [0.0, -0.15, -1], [0, -20]),
                 sR, sL, label="f23 HIT 2: out of the spin into the spread"))
    # f26 both blades up and back over the shoulders: square to the target, back arched open, up on the legs
    K.append(key(0.55, "in", [-0.06, -0.18, 0.22], [372, 8, 0], [370, -12, 0], [360, 10, 0],
                 ([-0.16, 0.36, -0.20], [-1, 0.3, -0.4], [-0.2, 0.6, -1], [20, -20]),
                 ([0.16, 0.36, -0.20], [1, 0.3, -0.4], [0.2, 0.6, -1], [20, -20]),
                 sR, sL, label="f26 both blades up and back (X wind-up)"))
    # f28 HIT 3: the X - both blades come over and DOWN, crossing in front; back folds over, hips drop and drive onto
    # the front foot, arms all the way out and crossed at the wrists
    K.append(key(0.59, "snap", [-0.07, -0.36, 0.26], [365, 34, 0], [362, 62, 0], [360, 34, 0],
                 ([0.16, -0.30, 0.50], [-1, -0.2, 0.2], [0.6, -0.15, 1], [-4, 30]),
                 ([-0.16, -0.26, 0.50], [1, -0.2, 0.2], [-0.6, -0.15, 1], [-4, 30]),
                 foot(-0.12, 0.30, yaw=-10, knee=(-0.2, 0, 1)), foot(0.04, 0.20, pitch=45, yaw=40, knee=(0.3, -0.5, 1)),
                 label="f28 HIT 3: blades cross down in an X"))
    # f30 recovery: rising and turning back to the right, the right blade swept up, the left down and back; the back
    # foot stepping back out
    K.append(key(0.64, "out", [-0.03, -0.30, 0.16], [345, 24, 2], [320, 30, 8], [355, 20, 0],
                 ([-0.10, 0.16, 0.20], [-1, -0.2, -0.3], [0.0, 1, 0.1], [10, -10]),
                 ([-0.30, -0.30, -0.10], [0.4, -1, 0.2], [-0.2, -0.6, -1]),
                 foot(-0.12, 0.30, yaw=-12, knee=(-0.2, 0.2, 1)), foot(0.08, -0.08, y=0.08, pitch=35, yaw=35, knee=(0.3, -0.5, 1)),
                 label="f30 recovery: unwinding back"))
    # f32 back in the wind-up (as f1), ready to chain
    K.append(key(0.7, "inout", [0, -0.40, -0.02], [325, 28, 4], [285, 40, 12], [350, 22, 0],
                 ([-0.10, -0.04, -0.54], [-0.6, -1, 0.1], [-0.1, 0.05, -1], [6, -20]),
                 ([-0.42, -0.18, -0.30], [0.2, -1, 0.3], [-0.15, -0.15, -1]),
                 fR(), fL(), label="f32 back in the wind-up"))
    return {"length": 0.7, "arm_space": "chest", "physics": True, "key_tol": [0.08, 0.22],   # few key poses (library)
            "about": "Oathkeeper & Oblivion flurry: low wind-up, blades back (f1-12) > horizontal slash onto the front "
                     "leg, back leg up (f13) > opened out (f17) > pivot spin left on the balls of the feet, blades up "
                     "(0.43-0.52 s) > second slash into the spread (0.52) > blades up and back, then down crossing in "
                     "an X (0.59) > back to the wind-up (0.7).", "keys": K}


CLIPS = {"attack_normal_2": attack_normal_2}


# ================================================================ keyblade moves (DRAFTS, Daniel 2026-11-25)
# Daniel: "add these two blades (Oathkeeper & Oblivion) and animate them in line with the current oathblade & oblivion
# FX presets"; his pick "draft every FX move", stills first. Each clip is timed to its oath_oblivion FX (start frame x
# frame_ms + the sequence's beats x swing_ticks x 16 ms, laser/weaponfx.py WEAPONS / SEQS) and posed from the 2D frames.
# Oathkeeper = right hand, Oblivion = left (the FX presets' w_hand1 / w_hand2). While an FX blade is drawn the keyblade
# in the hand hides (weapons3d.js pbwFxHeld), so the arms SELL the FX blade's move: stab where it stabs, chop where it
# chops, flick where it is thrown, open to catch where it comes back.
# Drafts are NOT written into hooded_blades.anim3d.json until Daniel approves them (see main: --approve).
TK = 0.016                       # FX tick (s)
# arm shorthand (body space): (reach from shoulder, elbow direction, blade direction[, clav])
UP_BACK = [-0.1, 1, -0.5]
FWD = [0, 0, 1]


def stance(dz=0.0, wide=1.0):
    """the wind-up stance: right foot forward, left back, moved dz forward"""
    return (foot(-0.12, 0.30 + dz, yaw=-15, knee=(-0.2, 0.2, 1)),
            foot(0.10 * wide, -0.38 * wide + dz, yaw=35, pitch=30, knee=(0.3, -0.5, 1)))


def ready(t, ease, dz=0.0, label="ready"):
    """f1-style ready: hunched, Oathkeeper cocked over the right shoulder, Oblivion low at the left hip, forward"""
    fr, fl = stance(dz)
    return key(t, ease, [0, -0.24, dz - 0.02], [-15, 22, 0], [-25, 30, 4], [-8, 18, 0],
               ([-0.04, 0.10, -0.16], [-0.5, -1, -0.4], UP_BACK, [8, -10]),
               ([0.02, -0.42, 0.18], [0.6, -0.6, -0.4], [0.1, -0.3, 1]),
               fr, fl, label=label)


def attack_normal_3():
    """Pierce & Chop (800 ms; FX 200-584 ms: Oblivion stab u.32 = 0.323 s, held to 0.361; Oathkeeper chop u.58 =
    0.423 s, follow-through u.66 = 0.453). 2D: f1 ready, f2-3 coil low, f4 long low pierce, f5 crouch blades up,
    f6-7 chop raised / down, f8 ready again."""
    K = [ready(0.0, "inout", label="f1 ready: Oathkeeper cocked, Oblivion low")]
    fr, fl = stance()
    # 0.20 coil (FX starts): sink, chest wound LEFT (left shoulder back) so the left arm can drive; Oblivion drawn back
    # low at the hip, point forward (chambered); Oathkeeper cocked high up-back
    K.append(key(0.20, "in", [0, -0.40, -0.06], [25, 26, 0], [45, 30, -6], [10, 20, 0],
                 ([-0.04, 0.18, -0.18], [-0.5, -1, -0.5], [-0.2, 1, -0.6], [10, -16]),
                 ([0.10, -0.36, -0.30], [0.4, -0.5, -1], [0, -0.15, 1], [0, -18]),
                 fr, fl, label="f2-3 coil: Oblivion chambered at the hip"))
    # 0.32 PIERCE: front foot steps on, hips drop and drive, chest whips RIGHT so the left shoulder leads; Oblivion
    # stabs low and straight through the target, arm all the way out; Oathkeeper stays cocked high
    fr2 = foot(-0.12, 0.72, yaw=-15, knee=(-0.2, 0.1, 1))
    fl2 = foot(0.12, -0.30, pitch=40, yaw=35, knee=(0.3, -0.4, 1))
    K.append(key(0.32, "snap", [0.02, -0.46, 0.34], [-30, 34, 0], [-55, 42, 8], [-25, 24, 0],
                 ([-0.06, 0.24, -0.10], [-0.6, -1, -0.3], [-0.1, 1, -0.4], [12, -18]),
                 ([0.04, -0.30, 0.66], [0.6, -0.8, 0], [0, -0.22, 1], [-4, 28]),
                 fr2, fl2, bease="linear", label="f4 PIERCE: Oblivion low through the target"))
    K.append(key(0.36, "out", [0.02, -0.47, 0.38], [-34, 36, 0], [-60, 44, 9], [-28, 24, 0],
                 ([-0.06, 0.26, -0.10], [-0.6, -1, -0.3], [-0.1, 1, -0.4], [12, -18]),
                 ([0.04, -0.32, 0.68], [0.6, -0.8, 0], [0, -0.25, 1], [-4, 30]),
                 fr2, fl2, label="pierce held (FX to u.42)"))
    # 0.395 raise: Oathkeeper swings up OVER the head (the chop travels in the arm's plane, never a wrist spin)
    K.append(key(0.395, "in", [0.0, -0.44, 0.42], [0, 34, 0], [5, 40, 0], [-8, 24, 0],
                 ([-0.04, 0.46, 0.10], [-0.8, 0.2, -0.3], [0, 0.7, 0.7], [18, 0]),
                 ([0.08, -0.32, 0.30], [0.6, -0.7, -0.4], [0, -0.25, 1], [0, 6]),
                 fr2, fl2, label="raise: Oathkeeper up over the head"))
    # 0.42 CHOP: Oblivion rips out back to the hip as the chest whips LEFT and Oathkeeper comes over and down onto
    # the target (FX 50 deg below forward); the back foot drags up under the hips
    fl3 = foot(0.12, 0.10, pitch=30, yaw=30, knee=(0.3, -0.3, 1))
    K.append(key(0.42, "snap", [-0.04, -0.42, 0.50], [28, 38, 0], [50, 50, -10], [12, 26, 0],
                 ([-0.02, 0.20, 0.58], [-0.8, -0.5, -0.1], [0, -0.77, 0.64], [-6, 28]),
                 ([0.12, -0.34, -0.26], [0.5, -0.6, -1], [0.1, -0.3, 1], [0, -16]),
                 fr2, fl3, bease="linear", label="f6-7 CHOP: Oathkeeper down onto the target, Oblivion ripped out"))
    K.append(key(0.46, "out", [-0.05, -0.45, 0.52], [36, 42, 0], [62, 56, -12], [16, 26, 0],
                 ([0.04, 0.0, 0.58], [-0.8, -0.4, 0.1], [0.15, -0.95, 0.3], [-8, 30]),
                 ([0.14, -0.34, -0.30], [0.5, -0.6, -1], [0.1, -0.3, 1], [0, -16]),
                 fr2, fl3, label="chop follow-through (FX u.66)"))
    # 0.58 recover (FX u.85): rising, unwinding back to the right, Oathkeeper drawn back up, Oblivion low forward
    K.append(key(0.58, "inout", [-0.02, -0.32, 0.46], [0, 28, 0], [-5, 34, 2], [-4, 20, 0],
                 ([-0.06, 0.04, -0.04], [-0.6, -1, -0.3], [-0.1, 0.8, 0.3], [4, -6]),
                 ([0.04, -0.40, 0.20], [0.6, -0.6, -0.3], [0.1, -0.3, 1]),
                 foot(-0.12, 0.72, yaw=-15, knee=(-0.2, 0.2, 1)), foot(0.10, 0.06, pitch=30, yaw=35, knee=(0.3, -0.5, 1)),
                 label="recover"))
    K.append(ready(0.80, "inout", dz=0.42, label="f8 ready again, 0.42 m on"))
    return {"length": 0.8, "arm_space": "chest", "physics": True, "key_tol": [0.08, 0.22], "approved": False,
            "about": "DRAFT Pierce & Chop (FX pierce_chop 0.2-0.58 s): coil with Oblivion chambered at the hip > "
                     "lunge, Oblivion stabs low through the target (0.32) > chest whips, Oathkeeper chops down as "
                     "Oblivion rips out (0.42) > recover > ready 0.42 m on.", "keys": K}


def attack_normal_4():
    """Pierce & Chop on the dash (602 ms; FX 57-345 ms, follow hand: stab u.32 = 0.149 s, chop u.58 = 0.224 s).
    2D: f1-2 ready / thrust, f3 load low, f4-8 a flat flying lunge, blade raised high (f6) then chopping forward
    (f7-8), f9-12 blades down and back, f13-14 low, f15-17 rising, both blades forward, f18-21 settle, arms out."""
    K = [ready(0.0, "inout", label="f1 ready")]
    fr, fl = stance()
    K.append(key(0.06, "in", [0, -0.44, -0.04], [20, 30, 0], [35, 36, -4], [8, 22, 0],
                 ([-0.04, 0.16, -0.18], [-0.5, -1, -0.5], [-0.2, 1, -0.5], [10, -16]),
                 ([0.10, -0.38, -0.26], [0.4, -0.5, -1], [0, -0.2, 1], [0, -18]),
                 fr, fl, label="f3 load: low, Oblivion chambered"))
    # 0.149 PIERCE in the air: a skimming lunge, body long and low, back leg trailing, front knee tucked; Oblivion
    # straight out at the target, Oathkeeper cocked high (2D f6 blade up)
    K.append(key(0.149, "snap", [0, -0.30, 0.62], [-25, 48, 0], [-45, 58, 6], [-20, 34, 0],
                 ([-0.06, 0.30, -0.06], [-0.6, -1, -0.3], [0, 1, -0.2], [12, -18]),
                 ([0.04, -0.20, 0.66], [0.6, -0.8, 0], [0, -0.15, 1], [-4, 30]),
                 foot(-0.12, 0.92, y=0.16, pitch=20, yaw=-15, knee=(-0.2, 0.3, 1)),
                 foot(0.10, 0.06, y=0.22, pitch=60, yaw=20, knee=(0.2, -1, 0.3)),
                 bease="linear", label="f5-6 PIERCE on the lunge: Oblivion out, Oathkeeper high"))
    # 0.195 raise in the air: Oathkeeper swings up over the head before it comes down
    K.append(key(0.195, "in", [0, -0.32, 0.82], [0, 44, 0], [5, 52, 0], [-6, 32, 0],
                 ([-0.04, 0.46, 0.10], [-0.8, 0.2, -0.3], [0, 0.7, 0.7], [18, 0]),
                 ([0.08, -0.30, 0.30], [0.6, -0.7, -0.4], [0, -0.2, 1], [0, 6]),
                 foot(-0.12, 1.14, y=0.10, pitch=20, yaw=-15, knee=(-0.2, 0.3, 1)),
                 foot(0.10, 0.26, y=0.18, pitch=50, yaw=25, knee=(0.2, -1, 0.3)), label="raise in the air"))
    # 0.224 CHOP on landing: front foot lands, Oathkeeper over and down onto the target, Oblivion ripped back
    K.append(key(0.224, "snap", [-0.04, -0.44, 0.96], [28, 42, 0], [52, 54, -10], [12, 28, 0],
                 ([-0.02, 0.18, 0.58], [-0.8, -0.5, -0.1], [0, -0.77, 0.64], [-6, 28]),
                 ([0.12, -0.34, -0.26], [0.5, -0.6, -1], [0.1, -0.3, 1], [0, -16]),
                 foot(-0.12, 1.30, yaw=-15, knee=(-0.2, 0.1, 1)), foot(0.12, 0.40, pitch=45, yaw=35, knee=(0.3, -0.4, 1)),
                 bease="linear", label="f7-8 CHOP on landing"))
    # 0.30 follow-through down and back (2D f9-12): blade carried down past the hip, chest folded over
    K.append(key(0.30, "out", [-0.05, -0.50, 0.98], [36, 46, 0], [62, 60, -12], [16, 30, 0],
                 ([0.06, -0.40, 0.20], [-0.8, -0.3, 0.2], [0.1, -0.9, -0.4], [-6, 20]),
                 ([0.14, -0.30, -0.32], [0.5, -0.6, -1], [0.1, -0.4, 1], [0, -16]),
                 foot(-0.12, 1.30, yaw=-15, knee=(-0.2, 0.1, 1)), foot(0.12, 0.40, pitch=45, yaw=35, knee=(0.3, -0.4, 1)),
                 label="f9-12 follow-through down and back"))
    # 0.46 rising, both blades forward (2D f16-17)
    fr2 = foot(-0.12, 1.30, yaw=-15, knee=(-0.2, 0.2, 1))
    fl2 = foot(0.10, 0.62, pitch=30, yaw=35, knee=(0.3, -0.5, 1))
    K.append(key(0.46, "inout", [-0.02, -0.30, 1.00], [-5, 26, 0], [-10, 30, 2], [-6, 20, 0],
                 ([0.04, -0.10, 0.58], [-0.7, -0.6, 0], [0.1, 0.1, 1], [-4, 20]),
                 ([-0.02, -0.16, 0.56], [0.7, -0.6, 0], [-0.1, 0.0, 1], [-4, 20]),
                 fr2, fl2, label="f15-17 rising, both blades forward"))
    K.append(ready(0.602, "inout", dz=0.98, label="f21 settle, 0.98 m on"))
    return {"length": 0.602, "arm_space": "chest", "physics": True, "key_tol": [0.08, 0.22], "approved": False,
            "about": "DRAFT Pierce & Chop on the dash (FX 0.06-0.35 s, follows the hands): load low > skimming lunge, "
                     "Oblivion stabs out (0.149) > lands, Oathkeeper chops down (0.224) > follow-through down and "
                     "back > rising, both blades forward > settle ~1 m on.", "keys": K}


def attack_normal_5():
    """Satellite (806 ms; FX 90-426 ms, follow hand): Oblivion thrown into a loop round the body (leaves the left hand
    u.06-.12 = 0.11-0.13 s, back u.88 = 0.386 s); Oathkeeper sweeps low forward (u.30 = 0.191 s), back down (u.5 =
    0.258), rises up-forward (u.60-.68 = 0.292-0.318). 2D: f1-5 low, blades forward; f6-9 up; f10-12 long low
    lunge, both blades thrust forward-down; f13-14 spread, one up-back, one forward-down; f15-18 level spread, settle."""
    fr, fl = stance()
    K = [ready(0.0, "inout", label="f1 ready")]
    # 0.11 Oblivion flick: left arm whips out to the left and forward, releasing it into its orbit; hips turn left
    K.append(key(0.11, "snap", [0.02, -0.34, 0.02], [-25, 24, 0], [-40, 28, 6], [-10, 18, 0],
                 ([-0.10, -0.34, 0.10], [-0.6, -0.6, -0.5], [-0.1, -0.3, -1], [0, -10]),
                 ([0.48, -0.08, 0.36], [0.6, -0.6, -0.3], [0.6, 0.1, 0.8], [-4, 24]),
                 fr, fl, bease="linear", label="flick: Oblivion released into its orbit"))
    # 0.19 Oathkeeper sweeps LOW forward (FX x .9 y .5): deep, chest whips left, right arm long and low
    K.append(key(0.19, "snap", [-0.02, -0.48, 0.16], [30, 34, 0], [50, 44, -8], [14, 22, 0],
                 ([-0.06, -0.48, 0.52], [-0.8, -0.5, 0], [0.1, -0.2, 1], [-6, 26]),
                 ([0.40, -0.14, -0.10], [0.6, -0.6, -0.4], [0.3, 0.3, -1]),
                 foot(-0.12, 0.50, yaw=-15, knee=(-0.2, 0.1, 1)), fl, bease="linear", label="Oathkeeper sweeps low"))
    # 0.258 drawn back down (FX x .2 y .8, pointing down-back): coiling under for the rise
    K.append(key(0.258, "in", [-0.02, -0.50, 0.18], [5, 36, 0], [10, 44, 0], [0, 22, 0],
                 ([-0.04, -0.52, 0.02], [-0.8, -0.4, -0.2], [0, -0.8, -0.6], [0, 10]),
                 ([0.40, -0.12, -0.08], [0.6, -0.6, -0.4], [0.3, 0.3, -1]),
                 foot(-0.12, 0.50, yaw=-15, knee=(-0.2, 0.1, 1)), fl, label="coil under"))
    # 0.30 RISING slash up-forward (FX -70 .. -90 deg): drives up off the legs, back arched, Oathkeeper overhead
    K.append(key(0.30, "snap", [-0.04, -0.14, 0.26], [-15, 10, 0], [-25, -4, 8], [-10, 6, 0],
                 ([-0.02, 0.50, 0.24], [-0.8, 0.2, -0.3], [0.1, 1, 0.35], [24, 10]),
                 ([0.40, -0.10, -0.06], [0.6, -0.6, -0.4], [0.3, 0.3, -1]),
                 foot(-0.12, 0.50, pitch=20, yaw=-15, knee=(-0.2, 0.2, 1)), foot(0.10, -0.24, pitch=40, yaw=35, knee=(0.3, -0.5, 1)),
                 bease="linear", label="RISING slash: Oathkeeper up overhead"))
    # 0.39 catch: Oblivion comes home to the left hand in front; chest square, both hands at chest height
    K.append(key(0.39, "out", [-0.02, -0.26, 0.30], [0, 22, 0], [0, 24, 0], [0, 14, 0],
                 ([-0.04, 0.22, 0.20], [-0.8, -0.4, -0.3], [0, 1, 0.5], [10, 0]),
                 ([0.08, -0.12, 0.42], [0.8, -0.6, 0], [0, 0.2, 1], [-2, 16]),
                 foot(-0.12, 0.50, yaw=-15, knee=(-0.2, 0.2, 1)), foot(0.10, -0.24, pitch=30, yaw=35, knee=(0.3, -0.5, 1)),
                 label="catch: Oblivion home in the left hand"))
    # 0.49 long low lunge, both blades thrust forward-down (2D f10-12)
    K.append(key(0.49, "snap", [0.0, -0.50, 0.80], [-5, 46, 0], [-10, 58, 2], [-6, 34, 0],
                 ([0.06, -0.22, 0.62], [-0.7, -0.7, 0], [0.05, -0.35, 1], [-6, 30]),
                 ([-0.06, -0.28, 0.60], [0.7, -0.7, 0], [-0.05, -0.4, 1], [-6, 30]),
                 foot(-0.12, 1.12, yaw=-15, knee=(-0.2, 0.1, 1)), foot(0.12, 0.04, pitch=45, yaw=35, knee=(0.3, -0.4, 1)),
                 bease="linear", label="f10-12 lunge: both blades thrust forward-down"))
    # 0.60 spread (2D f13-14): Oathkeeper up and back, Oblivion forward-down; chest opened side-on
    K.append(key(0.60, "out", [-0.06, -0.34, 0.84], [45, 26, 0], [75, 12, 20], [30, 22, 4],
                 ([0.0, 0.30, -0.50], [0.3, -1, 0], [-0.2, 0.9, -0.5], [6, -20]),
                 ([0.0, -0.14, 0.60], [-0.3, -1, 0], [0.1, -0.6, 1], [-4, 24]),
                 foot(-0.12, 1.12, yaw=-15, knee=(-0.2, 0.2, 1)), foot(0.10, 0.38, pitch=35, yaw=35, knee=(0.3, -0.5, 1)),
                 label="f13-14 spread"))
    K.append(ready(0.806, "inout", dz=0.80, label="f18 settle, 0.8 m on"))
    return {"length": 0.806, "arm_space": "chest", "physics": True, "key_tol": [0.08, 0.22], "approved": False,
            "about": "DRAFT Satellite (FX 0.09-0.43 s): left arm flicks Oblivion into its orbit (0.11) > Oathkeeper "
                     "sweeps low (0.19) > coils under > rising slash overhead (0.30) > catches Oblivion (0.39) > "
                     "lunge, both blades thrust forward-down (0.49) > spread (0.60) > settle 0.8 m on.", "keys": K}


def attack_special():
    """Charged Oathkeeper thrust (600 ms; FX Hold: Oathkeeper drawn along the LEFT hand's line for 52 ticks).
    2D: f1 guard, blade up; f2-14 a long low lunge, the far arm locked out holding the blade level at the target (a
    charging hold); f15 slash; f16 up, blade vertical; f17 blade across."""
    fr, fl = stance()
    K = [key(0.0, "inout", [0, -0.20, 0], [-10, 16, 0], [-20, 22, 2], [-6, 14, 0],
             ([-0.02, 0.14, 0.10], [-0.6, -1, -0.2], [0, 1, 0.1], [6, -4]),
             ([0.14, -0.10, 0.30], [0.6, -0.8, -0.2], [0.1, 0.2, 1]),
             fr, fl, label="f1 guard")]
    # 0.04 the lunge: wide, low, side-on (chest turned RIGHT so the left shoulder points at the target); left arm
    # locked straight and level at the target; right arm flared back low as the counterweight
    lr = foot(-0.12, 0.92, yaw=-25, knee=(-0.3, 0.1, 1))
    ll = foot(0.14, -0.42, pitch=10, yaw=70, knee=(0.6, -0.2, 0.6))
    K.append(key(0.06, "snap", [-0.02, -0.52, 0.36], [-55, 22, 0], [-80, 16, -6], [-60, 14, 0],
                 ([-0.10, -0.26, -0.44], [-0.4, -1, -0.2], [-0.1, -0.5, -1], [0, -20]),
                 ([-0.02, 0.02, 0.68], [0.3, -1, 0], [0, 0.02, 1], [-2, 34]),
                 lr, ll, bease="linear", label="f2 lunge: left arm locked out at the target"))
    # moving hold (f3-14): the charge - sinks a little, the front knee buries, the arm stays on the line
    K.append(key(0.28, "inout", [-0.02, -0.55, 0.40], [-58, 24, 0], [-84, 18, -6], [-62, 14, 0],
                 ([-0.10, -0.28, -0.46], [-0.4, -1, -0.2], [-0.1, -0.5, -1], [0, -20]),
                 ([-0.02, 0.00, 0.70], [0.3, -1, 0], [0, 0.0, 1], [-2, 36]),
                 lr, ll, label="charge (moving hold)"))
    K.append(key(0.47, "inout", [-0.02, -0.57, 0.42], [-60, 26, 0], [-86, 20, -8], [-64, 16, 0],
                 ([-0.10, -0.28, -0.46], [-0.4, -1, -0.2], [-0.1, -0.5, -1], [0, -20]),
                 ([-0.02, -0.02, 0.70], [0.3, -1, 0], [0, -0.02, 1], [-2, 36]),
                 lr, ll, label="charge, deepest"))
    # 0.51 release slash (f15): chest whips back LEFT, the left arm cuts across and down
    K.append(key(0.51, "snap", [-0.04, -0.46, 0.46], [-10, 30, 0], [-5, 36, 4], [-10, 20, 0],
                 ([-0.10, -0.30, -0.30], [-0.4, -1, -0.2], [-0.1, -0.5, -1], [0, -14]),
                 ([0.36, -0.30, 0.40], [0.6, -0.8, 0], [0.6, -0.5, 0.6], [-4, 20]),
                 lr, ll, bease="linear", label="f15 release slash across"))
    # 0.565 up, blade vertical (f16), 0.6 settle (f17)
    K.append(key(0.565, "out", [-0.02, -0.22, 0.44], [0, 14, 0], [5, 12, 0], [0, 10, 0],
                 ([-0.06, -0.20, 0.10], [-0.6, -1, -0.2], [0, 0.2, 1]),
                 ([0.04, 0.10, 0.24], [0.7, -0.7, 0], [0, 1, 0.1], [6, 0]),
                 foot(-0.12, 0.92, yaw=-15, knee=(-0.2, 0.2, 1)), foot(0.10, 0.10, pitch=20, yaw=35, knee=(0.3, -0.5, 1)),
                 label="f16 up, blade vertical"))
    K.append(key(0.6, "inout", [-0.02, -0.24, 0.44], [-5, 18, 0], [-10, 20, 2], [-4, 14, 0],
                 ([-0.04, -0.18, 0.10], [-0.6, -1, -0.2], [0, 0.1, 1]),
                 ([0.10, -0.06, 0.30], [0.6, -0.8, -0.2], [-0.6, 0.4, 0.7]),
                 foot(-0.12, 0.92, yaw=-15, knee=(-0.2, 0.2, 1)), foot(0.10, 0.20, pitch=25, yaw=35, knee=(0.3, -0.5, 1)),
                 label="f17 settle, blade across"))
    return {"length": 0.6, "arm_space": "chest", "physics": True, "key_tol": [0.08, 0.22], "approved": False,
            "about": "DRAFT charged thrust (FX Hold: Oathkeeper rides the LEFT hand): wide low side-on lunge with the "
                     "left arm locked out at the target (0.06), held while it charges (moving hold, to 0.47) > release "
                     "slash across (0.51) > up, blade vertical > settle.", "keys": K}


def attack_special_2():
    """Oblivion's signature counter-spin (500 ms; FX Oblivion only, 45-605 ms: spins u0-.45, strike u.7 = 0.437 s).
    2D: f1 crouched, blades crossed; f2 blade up; f3-7 a full turn (back to the camera at f6); f8-10 big X spread
    lunging; f11 crouch, blades level."""
    fr, fl = stance()
    K = [key(0.0, "inout", [0, -0.40, 0], [-10, 30, 0], [-15, 38, 2], [-6, 22, 0],
             ([0.06, -0.22, 0.30], [-0.6, -0.8, -0.2], [0.6, 0.5, 0.6], [0, 10]),
             ([-0.06, -0.24, 0.30], [0.6, -0.8, -0.2], [-0.6, -0.5, 0.6], [0, 10]),
             fr, fl, label="f1 crouched, blades crossed in front")]
    # pivot spin to the RIGHT on the balls of the feet (feet gathered), both blades up and in, head spotting
    c = (-0.03, 0.30)
    gR = foot(-0.12, 0.30, pitch=25, yaw=-40, knee=(-0.3, 0.1, 1))
    gL = foot(0.06, 0.30, pitch=25, yaw=-20, knee=(0.3, 0.1, 1))
    up_R = ([-0.12, -0.16, 0.36], [-0.8, -1, -0.2], [-0.35, 1, 0.35])     # hands out in front, blades tilted away
    up_L = ([0.12, -0.16, 0.36], [0.8, -1, -0.2], [0.35, 1, 0.35])        # from the head (audit: blade through head)
    for t, ease, th, lab in ((0.09, "in", 0, "f2-3 gather, blades up"), (0.17, "linear", -120, "spin 120"),
                             (0.25, "linear", -240, "spin 240 (back to the camera)"), (0.32, "out", -330, "spin out")):
        K.append(key(t, ease, [-0.04, -0.20, 0.30], [-20 + th, 12, 0], [-30 + th, 14, -6], [-10 + th * 0.85, 14, 0],
                     up_R, up_L, spun(gR, th, c), spun(gL, th, c), label=lab))
    # 0.437 X STRIKE: out of the spin into a lunge, blades crossing - Oathkeeper up and back, Oblivion forward and down
    sR = foot(-0.12, 0.80, yaw=-15, knee=(-0.2, 0.1, 1))
    sL = foot(0.10, 0.10, pitch=40, yaw=35, knee=(0.3, -0.4, 1))
    K.append(key(0.437, "snap", [-0.04, -0.44, 0.52], [-370, 36, 0], [-345, 40, 10], [-365, 24, 0],
                 ([-0.10, 0.34, -0.36], [-0.4, -1, -0.2], [-0.4, 0.8, -0.5], [10, -18]),
                 ([0.0, -0.26, 0.64], [0.6, -0.8, 0], [0.3, -0.6, 0.8], [-4, 30]),
                 sR, sL, bease="linear", label="f8-10 X STRIKE: Oblivion forward-down, Oathkeeper up-back"))
    K.append(key(0.5, "out", [-0.04, -0.42, 0.54], [-365, 32, 0], [-360, 34, 4], [-362, 22, 0],
                 ([0.06, -0.20, 0.36], [-0.6, -0.8, -0.2], [0.7, 0.3, 0.6], [0, 10]),
                 ([-0.06, -0.24, 0.36], [0.6, -0.8, -0.2], [-0.7, -0.2, 0.6], [0, 10]),
                 sR, foot(0.10, 0.12, pitch=30, yaw=35, knee=(0.3, -0.5, 1)), label="f11 crouch, blades level"))
    return {"length": 0.5, "arm_space": "chest", "physics": True, "key_tol": [0.08, 0.22], "approved": False,
            "about": "DRAFT Oblivion counter-spin: crouched, blades crossed > gather, blades up > full pivot turn to "
                     "the right on the balls of the feet (0.09-0.32) > X strike lunge (0.437 = FX strike) > crouch.",
            "keys": K}


def switch_in():
    """Tag-in (520 ms; FX twin counter-spins, follow off, 0-400 ms, strike u.7 = 0.28 s; Thrust kick FX from f3).
    2D: f1-3 landing crouch, blades swept back; f4-6 low thrust kick forward; f7 blades up; f8-9 a flat flying thrust,
    both blades forward-up; f10 blade down; f11-14 crouch back into the ready, blades back."""
    K = [key(0.0, "out", [0, -0.46, 0], [-20, 30, 0], [-40, 38, 6], [-10, 22, 0],
             ([-0.10, -0.04, -0.54], [-0.6, -1, 0.1], [-0.1, 0.05, -1], [6, -20]),
             ([-0.42, -0.18, -0.30], [0.2, -1, 0.3], [-0.15, -0.15, -1]),
             foot(-0.14, 0.34, yaw=-15, knee=(-0.2, 0.3, 1)), foot(0.12, -0.40, pitch=30, yaw=35, knee=(0.3, -0.5, 1)),
             label="f1-3 landing crouch, blades swept back")]
    # 0.15 thrust kick (f4-6): the right leg drives straight out at the target, body leaning back over the left
    K.append(key(0.15, "snap", [0.04, -0.30, -0.10], [-10, -12, 0], [-15, -4, -4], [-5, 10, 0],
                 ([-0.10, -0.10, -0.50], [-0.6, -1, 0.1], [-0.1, 0.1, -1], [4, -16]),
                 ([-0.42, -0.10, -0.30], [0.2, -1, 0.3], [-0.15, -0.1, -1]),
                 foot(-0.10, 0.62, y=0.42, pitch=-40, yaw=-10, knee=(-0.1, 0.4, 1)),
                 foot(0.12, -0.40, pitch=10, yaw=35, knee=(0.3, -0.2, 1)), bease="linear",
                 label="f4-6 THRUST KICK"))
    # 0.24 recoil the kick, blades come up (f7)
    K.append(key(0.24, "in", [0.02, -0.30, 0.10], [0, 16, 0], [0, 10, 0], [0, 10, 0],
                 ([-0.04, 0.24, 0.10], [-0.8, -0.6, -0.3], [0, 1, 0.1], [14, 0]),
                 ([0.04, 0.24, 0.10], [0.8, -0.6, -0.3], [0, 1, 0.1], [14, 0]),
                 foot(-0.12, 0.46, y=0.14, pitch=20, yaw=-15, knee=(-0.2, 0.4, 1)),
                 foot(0.12, -0.40, pitch=20, yaw=35, knee=(0.3, -0.3, 1)), label="f7 kick recoils, blades up"))
    # 0.28 FLYING THRUST (FX strike): pushes off the back leg into a flat dive, both blades forward-up at the target
    K.append(key(0.28, "snap", [0, -0.36, 0.72], [0, 56, 0], [0, 64, 0], [0, 40, 0],
                 ([-0.02, -0.08, 0.64], [-0.7, -0.7, 0], [0, 0.35, 1], [-4, 30]),
                 ([0.02, -0.08, 0.64], [0.7, -0.7, 0], [0, 0.35, 1], [-4, 30]),
                 foot(-0.12, 1.00, y=0.10, pitch=30, yaw=-15, knee=(-0.2, 0.3, 1)),
                 foot(0.10, 0.14, y=0.24, pitch=60, yaw=20, knee=(0.2, -1, 0.3)), bease="linear",
                 label="f8-9 FLYING THRUST, both blades at the target"))
    K.append(key(0.37, "out", [-0.02, -0.44, 0.96], [10, 46, 0], [15, 52, -4], [6, 30, 0],
                 ([0.02, -0.36, 0.40], [-0.7, -0.7, 0], [0.1, -0.9, 0.3], [-4, 20]),
                 ([-0.04, -0.24, 0.40], [0.7, -0.7, 0], [-0.1, -0.2, 1], [-4, 20]),
                 foot(-0.12, 1.20, yaw=-15, knee=(-0.2, 0.1, 1)), foot(0.12, 0.42, pitch=40, yaw=35, knee=(0.3, -0.4, 1)),
                 label="f10 lands, blade carried down"))
    fr, fl = stance(dz=0.92)
    K.append(key(0.52, "inout", [0, -0.40, 0.90], [-35, 28, 4], [-75, 40, 12], [-10, 22, 0],
                 ([-0.10, -0.04, -0.54], [-0.6, -1, 0.1], [-0.1, 0.05, -1], [6, -20]),
                 ([-0.42, -0.18, -0.30], [0.2, -1, 0.3], [-0.15, -0.15, -1]),
                 fr, fl, label="f11-14 back in the wind-up, blades swept back"))
    return {"length": 0.52, "arm_space": "chest", "physics": True, "key_tol": [0.08, 0.22], "approved": False,
            "about": "DRAFT tag-in: landing crouch, blades swept back > thrust kick (0.15) > recoil, blades up > "
                     "flying thrust with both blades (0.28 = the FX's X strike) > lands > back into the wind-up "
                     "(chains into attack_normal_2).", "keys": K}


DRAFTS = {"attack_normal_3": attack_normal_3, "attack_normal_4": attack_normal_4, "attack_normal_5": attack_normal_5,
          "attack_special": attack_special, "attack_special_2": attack_special_2, "switch_in": switch_in}


def main(argv):
    """no args: rewrite CLIPS; names: those clips; --approve name[,name]: write approved DRAFTS into the spec"""
    spec = json.load(open(OUT))
    if "--approve" in argv:
        names = argv[argv.index("--approve") + 1].split(",")
        for n in names:
            c = DRAFTS[n]()
            c["approved"] = True
            spec["clips"][n] = c
    else:
        for name in (argv or CLIPS):
            spec["clips"][name] = CLIPS[name]()
    json.dump(spec, open(OUT, "w"), indent=1)
    print("wrote", os.path.relpath(OUT), sorted(spec["clips"]))


if __name__ == "__main__":
    main(sys.argv[1:])
