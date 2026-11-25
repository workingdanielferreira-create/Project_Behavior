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


def main(argv):
    spec = json.load(open(OUT))
    for name in (argv or CLIPS):
        spec["clips"][name] = CLIPS[name]()
    json.dump(spec, open(OUT, "w"), indent=1)
    print("wrote", os.path.relpath(OUT), sorted(spec["clips"]))


if __name__ == "__main__":
    main(sys.argv[1:])
