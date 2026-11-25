"""Puck's authored 3D clips (Daniel 2026-11-24: "redo Puck's animations"), written into
characters/puck/puck.anim3d.json. One move at a time, each reviewed by Daniel from GIF stills.

    python v3/tools/puck/gen_puck.py           rewrite every clip defined here
    python v3/tools/anim3d.py puck --check     audit, then without --check to bake into puck.glb

Puck is unarmed: `blade` on a hand = the direction the THUMB side of the fist points (anim3d's blade comes out of
the thumb side, perpendicular to the forearm). Arms are designed in BODY space (+Z = target, +X = his left, m)
and converted to chest space per key, so a hook's arc is exact whatever the torso does.
"""
import json, os, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from anim3d import rot_euler, axis_angle, SPINE_SPLIT, HEAD_SPLIT

ANKLE = 0.104
OUT = os.path.join(HERE, '..', '..', '..', 'characters', 'puck', 'puck.anim3d.json')


def r3(v):
    return [round(float(x), 3) for x in v]


def U(v):
    v = np.array(v, float)
    return v / np.linalg.norm(v)


def arm(M, reach, elbow, thumb, clav=None):
    """Body-space hand offset from the shoulder, elbow direction, thumb direction -> chest-space controls."""
    out = {"reach": r3(M.T @ np.array(reach, float)), "elbow": r3(M.T @ U(elbow)), "blade": r3(M.T @ U(thumb))}
    if clav:
        out["clav"] = clav
    return out


def line(chest, ext=0.66, dx=0.0, dy=0.0):
    """A reach along the line of action: the chest's own spine direction (hips -> neck) carried on out through the
    arm, nudged by dx / dy (m, body space), ext m long (0.66 = straight once the shoulder girdle drives forward)."""
    v = rot_euler(*chest) @ np.array([0, 1.0, 0]) + np.array([dx, dy, 0])
    return r3(U(v) * ext)


def foot(x, z, y=0.0, yaw=0.0, pitch=0.0, knee=(0, 0.1, 1)):
    return {"ankle": r3([x, ANKLE + y, z]), "knee": r3(U(knee)), "yaw": yaw, "pitch": pitch}


def _chain(e, split):
    M = np.eye(3)
    for k in split:
        M = M @ rot_euler(e[0] * k, e[1] * k, e[2] * k)
    return M


def relative(parent, want, split):
    """Euler angles e (anim3d spine / head control) so that parent @ chain(e) = want: anim3d turns each spine / neck
    bone about its PARENT'S current axes, so a chest lean typed as `spine` pitch tips sideways once the hips have
    turned. Puck's keys give the chest / head in WORLD terms (turn, lean toward the target, side bend) instead."""
    e = np.zeros(3)
    for _ in range(30):
        err = axis_angle((parent @ _chain(e, split)).T @ want)
        if np.linalg.norm(err) < 1e-6:
            break
        J = np.zeros((3, 3))
        for i in range(3):
            d = np.zeros(3); d[i] = 0.01
            J[:, i] = (axis_angle((parent @ _chain(e + d, split)).T @ want) - err) / 0.01
        e = e - np.linalg.lstsq(J, err, rcond=None)[0]
    return [round(float(x), 2) for x in e]


def key(t, ease, hips, hrot, chest, head, R, L, fR, fL, bease=None, label=None):
    """chest / head = WORLD orientation [yaw (+ turn left), pitch (+ lean toward the target), roll (+ tip right)]."""
    H = rot_euler(*hrot)
    M = rot_euler(*chest)
    spine = relative(H, M, SPINE_SPLIT)
    headr = relative(M, rot_euler(*head), HEAD_SPLIT)
    k = {"t": t, "ease": ease, "hips": {"pos": r3(hips), "rot": hrot}, "spine": spine, "head": headr,
         "R": arm(M, *R), "L": arm(M, *L), "fR": fR, "fL": fL}
    if bease:
        k["bease"] = bease
    if label:
        k["label"] = label
    return k


# ---------------------------------------------------------------- attack_normal: dash > overhand right > follow-through
# Daniel 2026-11-24: both punches come OVER the top going DOWN onto the target (never from under going up); wrists
# locked straight with intention; bend the back - a committed punch moving forward folds the body over and the fist
# follows through past where it hit.
OVERLAP_LEAD = 0.025


def attack_normal():
    K = []
    # 0.00 (2D f1-f2) wind-up on the move (Daniel: "its a windup"): the right arm FOLDED, elbow driven back, fist
    # tucked close behind the shoulder, the shoulder pulled back and DOWN (never shrugged into the neck); the far (left) arm reaching forward as the lead / aim; body coiled toward the back hand on one
    # C-curve from the planted foot up the back; left foot swinging through
    K.append(key(0.0, "inout", [0, -0.16, -0.20], [-16, 40, 2], [-36, 50, 8], [10, 32, 2],
                 ([-0.08, -0.06, -0.24], [-0.35, -0.15, -1], [0.1, 1, 0.2], [-12, -34]),
                 ([0.06, 0.0, 0.64], [0.5, -1, 0], [-0.5, 0.8, 0], [0, 22]),
                 foot(-0.13, -0.05, pitch=10, yaw=-12), foot(0.12, -0.62, y=0.12, pitch=45, knee=(0.1, -0.4, 1)),
                 label="wind-up: right fist back, left arm leads"))
    # 0.09 (f3) load: left foot reaching to land, hips coil right, chest wrung back further and arched a little; the
    # right fist cocked HIGH behind the ear, elbow up and out; left hand forward as a guard / range finder
    K.append(key(0.09, "in", [0, -0.10, 0.08], [-30, 40, 6], [-46, 54, 8], [6, 32, 4],
                 ([-0.16, 0.0, -0.24], [-1, 0.2, -0.6], [0.2, 0.3, 1], [8, -24]),
                 ([0.10, -0.20, 0.30], [0.6, -1, 0], [0.2, 0.2, -1]),
                 foot(-0.13, -0.05, pitch=30, yaw=-15), foot(0.13, 0.62, y=0.05, yaw=10, knee=(0.2, 0, 1)),
                 label="load: fist cocked high"))
    # 0.13 breakdown: the fist comes over the top - high and wide above the shoulder, elbow leading, as the hips
    # start to whip left
    K.append(key(0.13, "in", [0, -0.12, 0.24], [-2, 44, 0], [-12, 60, 6], [4, 38, 0],
                 ([-0.32, 0.22, 0.28], [-1, 0.6, 0.1], [0.3, 0.3, 1], [18, 10]),
                 ([0.02, -0.06, 0.24], [0.5, -1, -0.3], [0.2, 0.2, -1], [0, -10]),
                 foot(-0.13, -0.05, pitch=35, yaw=-20, knee=(-0.2, -0.2, 1)), foot(0.13, 0.66, yaw=10, knee=(0.2, 0, 1)),
                 label="over the top"))
    # 0.165 (f4-f5) OVERHAND lands: the arm drives DOWN onto the target at full stretch, the right shoulder rolled
    # over it; hips lead, back folded forward and side-bent into the punch (left shoulder dropped), back leg long;
    # fist turned over (thumb down / in), left fist snapped back to the jaw
    K.append(key(0.165, "snap", [0, -0.14, 0.40], [24, 44, -6], [36, 66, -8], [8, 44, -6],
                 (line([36, 66, -8], dx=0.18, dy=-0.42), [-1, 0.5, 0.1], [0.6, -0.6, 0.1], [8, 36]),
                 ([-0.02, -0.06, 0.18], [0.4, -1, -0.5], [0.2, 0.2, -1], [0, -22]),
                 foot(-0.13, -0.05, pitch=40, yaw=-25, knee=(-0.3, -0.2, 1)), foot(0.13, 0.66, yaw=10, knee=(0.2, 0, 1)),
                 label="OVERHAND lands (down onto the target)"))
    # 0.21 (f6-f7) follow-through: the fist keeps going down and across, past where it hit; the back folds over
    # further, chest whips past the hips
    K.append(key(0.21, "out", [0, -0.18, 0.50], [32, 54, -8], [50, 82, -10], [14, 58, -8],
                 (line([50, 82, -10], dx=0.45, dy=-0.25), [-1, 0.4, 0.5], [0.6, -0.5, 0.3], [-2, 40]),
                 ([-0.04, -0.08, 0.14], [0.4, -1, -0.5], [0.2, 0.2, -1], [0, -24]),
                 foot(-0.13, -0.05, pitch=45, yaw=-25, knee=(-0.3, -0.2, 1)), foot(0.13, 0.66, yaw=10, knee=(0.2, 0, 1)),
                 label="follow-through: down and across"))
    # 0.27 (f8-f9) follow-through ends: the arm wraps across the body and folds, the fist finishing by the LEFT
    # shoulder / jaw, elbow pointing at the target; chest turned all the way through, the back foot stepping up
    # under him (one punch only - Daniel: "dont double hit", the "hook follow up" is this follow-through)
    K.append(key(0.27, "out", [0, -0.20, 0.66], [40, 46, -8], [64, 62, -10], [14, 46, -6],
                 ([0.36, 0.02, 0.18], [-0.1, 0.1, 1], [0.2, 1, 0], [2, 30]),
                 ([-0.02, -0.12, 0.14], [0.4, -1, -0.5], [0.2, 0.2, -1], [0, -20]),
                 foot(-0.12, 0.42, y=0.06, pitch=30, yaw=-10, knee=(-0.1, 0.2, 1)), foot(0.13, 0.66, yaw=15, knee=(0.2, 0, 1)),
                 label="follow-through ends: arm wrapped across"))
    # 0.33 (f10) settle (moving hold): the back foot plants under him, the body starts to unwind back toward square
    K.append(key(0.33, "inout", [0, -0.20, 0.74], [26, 44, -4], [44, 58, -6], [10, 42, -4],
                 ([0.28, -0.04, 0.16], [-0.3, -0.2, 1], [0.2, 1, 0], [0, 20]),
                 ([0.0, -0.14, 0.18], [0.4, -1, -0.5], [0.2, 0.2, -1], [0, -16]),
                 foot(-0.12, 0.58, yaw=-8, knee=(-0.1, 0, 1)), foot(0.13, 0.66, pitch=10, yaw=12, knee=(0.2, 0, 1)),
                 label="settle (moving hold)"))
    # 0.40 (f11-f12) springs back into the dash: pitched forward, left foot peeling off, fists gathering in front
    K.append(key(0.40, "out", [0, -0.16, 0.92], [-4, 46, 0], [-10, 64, 2], [-2, 44, 0],
                 ([0.02, -0.10, 0.40], [-0.6, -1, 0], [0.6, 0.6, 0], [0, 10]),
                 ([0.10, -0.24, 0.30], [0.6, -1, 0], [0.2, 0.2, -1]),
                 foot(-0.12, 0.58, pitch=20, yaw=-6), foot(0.13, 0.66, y=0.10, pitch=55, yaw=10, knee=(0.1, -0.4, 1)),
                 label="springs back into the dash"))
    # overlap lead (Daniel 2026-11-25, "pull body keys earlier"): the overlap springs make the fist trail the body,
    # so the inner keys come 25 ms (1.5 frames) early; measured: the fist still reaches 95% extension at 167 ms and
    # full at 183 ms, the same frames as the approved clip without overlap
    for k in K[1:-1]:
        k["t"] = round(k["t"] - OVERLAP_LEAD, 4)
    return {"length": 0.4, "arm_space": "chest", "physics": True, "fists": True,
            # overlap (2026-11-25, ZZZ-snappy 1-2 frames): hips lead, chest a frame behind, the striking arm then its
            # fist land last and overshoot most; the head trails loosest; the free left arm is tighter (counterweight)
            "overlap": {"spine": [1.0, 8], "R": [1.5, 10], "Rfist": [1.75, 12], "head": [1.75, 12],
                        "L": [1.0, 6], "Lfist": [1.25, 5]},
            "about": "Dash > wind-up > overhand right, over the top and down (lands 2D f5) > follow-through: down, "
                     "across and wrapped by the left shoulder (2D f7-f10) > back into the dash. ONE punch. Travels ~1.1 m.", "keys": K}


def palm(M, reach, elbow, face, fing, curl, clav=None):
    """Open hand (anim3d `palm`): body-space reach / elbow, the way the palm FACES and the way the fingers point."""
    out = arm(M, reach, elbow, face)
    # always keyed: anim3d carries a control a key leaves out over from the key before, but meet() solves the key alone
    out.update({"palm": True, "fing": r3(M.T @ U(fing)), "curl": curl, "clav": clav or [0, 0]})
    return out


_BODY = None


def meet(k, want, it=8, straight=None):
    """Move the hands' reach until the wrists sit exactly at want = {"R": body-space point, "L": ...} (heel to heel):
    the shoulders move with the chest, the clavicles and the torso, so solve the key and correct.
    straight = arm length (m): the wrists' depth (z) is pushed out until the SHORTER arm is that long (a locked
    thrust), keeping their x / y."""
    global _BODY
    import anim3d
    _BODY = _BODY or anim3d.Body()
    B = _BODY
    M = rot_euler(*k.pop("_M"))
    for _ in range(it):
        c = anim3d.full_keys(B, [k])[0]
        c["arm_space"] = "chest"
        sv = anim3d.Solver(B)
        sv.pose(c, 0.0)
        W, P = sv.fk()
        if straight:
            z = min(P[B.rig.i(S + "Arm")][2] + np.sqrt(max(0.0, straight ** 2 - (want[sd][0] - P[B.rig.i(S + "Arm")][0]) ** 2
                    - (want[sd][1] - P[B.rig.i(S + "Arm")][1]) ** 2)) for sd, S in (("R", "Right"), ("L", "Left")))
            want = {sd: [want[sd][0], want[sd][1], z] for sd in want}
        err = 0.0
        for sd, S in (("R", "Right"), ("L", "Left")):
            d = np.array(want[sd], float) - P[B.rig.i(S + "Hand")]
            err = max(err, np.linalg.norm(d))
            v = np.array(k[sd]["reach"]) + M.T @ d
            k[sd]["reach"] = r3(v * min(1.0, 0.64 / np.linalg.norm(v)))       # never past a locked arm
        if err < 0.004:
            break
    return k


# ---------------------------------------------------------------- attack_special: kamehameha (stays in place)
# Daniel 2026-11-25: "he's doing the kamehameha". 2D: 55 frames x 36.4 ms = 2.0 s; f1-35 the charge, hands cupped
# at the (back) hip in a wide low straddle; f36-55 the release, both arms thrust straight forward at shoulder
# height, the front knee over the foot (thigh flat), the back leg long and straight. The feet never move (both 2D
# phases put them on the same spots): the hips drive forward and the back leg locks out, the back foot pivoting on
# the ball from toes-out (straddle) to the lunge. OPEN palms, heel to heel.
FR_BACK, FL_FRONT = (-0.13, -0.58), (0.13, 0.50)


def attack_special():
    K = []
    fR = lambda yaw=-30, **kw: foot(FR_BACK[0], FR_BACK[1], yaw=yaw, **kw)
    fL = lambda **kw: foot(FL_FRONT[0], FL_FRONT[1], yaw=15, **kw)

    FING = [-0.85, -0.1, 0.45]      # both hands' fingers the same way: out past the hip and a little forward

    def charge(t, ease, hz, hy, hrot, chest, head, hip_pt, gap, curl, back_knee, label):
        """Hands cupped at the right (back) hip round a ball: right hand under, palm up; left on top, palm down;
        wrists together, fingers curling forward round it."""
        M = rot_euler(*chest)
        k = key(t, ease, [0, hy, hz], hrot, chest, head,
                ([-0.1, -0.4, -0.1], [-0.5, -0.6, -0.8], [0.15, 1, 0.1]),
                ([-0.4, -0.4, 0.1], [0.3, -1, 0.5], [0.0, 1, 0]),
                fR(yaw=-65, knee=back_knee), fL(knee=(0.4, 0.3, 1)), label=label)
        k["R"] = palm(M, [-0.1, -0.4, -0.1], [-0.6, -0.5, -0.7], [0.1, 1, 0.1], FING, curl)
        k["L"] = palm(M, [-0.4, -0.4, 0.1], [0.4, -1, 0.6], [-0.1, -1, -0.1], FING, curl, clav=[0, 20])
        k["_M"] = chest
        hp = np.array(hip_pt, float)
        return meet(k, {"R": hp + [0.0, -gap / 2, 0.02], "L": hp + [0.02, gap / 2, 0.0]})

    def release(t, ease, hz, hy, hrot, chest, head, at, label, bease=None):
        """Arms thrust straight forward at shoulder height; palms to the target, heels together: left hand on top,
        fingers up; right hand under it, fingers down. Hands stacked VERTICALLY (that is the kamehameha; Final Flash
        is horizontal), the palms cupped ~27 deg toward each other round the beam: a wrist bends back only 60-70
        deg, so locked arms can't hold both palms square to the target."""
        M = rot_euler(*chest)
        k = key(t, ease, [0, hy, hz], hrot, chest, head,
                ([0, 0, 0.6], [-0.6, -1, 0], [0, 0, 1]), ([0, 0, 0.6], [0.6, -1, 0], [0, 0, 1]),
                fR(pitch=-10, knee=(-0.2, -0.3, 1)), fL(knee=(0.2, 0.1, 1)), bease=bease, label=label)
        k["R"] = palm(M, [0.1, -0.1, 0.5], [-0.25, -1, 0.1], [0, 0.5, 1], [0, -1, 0.5], 0.35)
        k["L"] = palm(M, [-0.1, -0.1, 0.5], [0.25, -1, 0.1], [0, -0.5, 1], [0, 1, 0.5], 0.35)
        k["_M"] = chest
        a = np.array(at, float)
        # arms LOCKED straight (Daniel 2026-11-25 "what is happening with his arms": bent, flared elbows crossing in
        # an X in front of the face); they converge from the shoulders to the wrists, elbows down
        return meet(k, {"R": a + [0, -0.035, 0], "L": a + [0, 0.035, 0]}, straight=0.544)

    # 0.00 (f1) the hands sweep back to the hip: wide low straddle, body already coiling to the right
    K.append(charge(0.0, "inout", -0.04, -0.30, [-24, 10, 4], [-50, 12, 8], [-12, 8, 0],
                    [-0.26, 0.84, -0.06], 0.16, 0.2, (-0.8, 0.3, -0.45), "hands sweep back to the hip"))
    # 0.30 (f9) cupped at the back hip: coiled - hips turned right, chest wrung further back and side-bent over the
    # hands, eyes on the target
    K.append(charge(0.30, "out", -0.08, -0.38, [-40, 8, 8], [-88, 8, 16], [-30, 6, 0],
                    [-0.27, 0.74, -0.20], 0.11, 0.6, (-0.8, 0.3, -0.45), "KA-ME: cupped at the back hip"))
    # 0.80 (f23) moving hold: the coil keeps sinking
    K.append(charge(0.80, "inout", -0.10, -0.40, [-42, 8, 9], [-91, 9, 18], [-32, 6, 0],
                    [-0.28, 0.72, -0.22], 0.11, 0.65, (-0.8, 0.3, -0.45), "HA-ME: charging (moving hold)"))
    # 1.25 (f35) load: deepest coil, hips back over the back leg, the ball squeezed
    K.append(charge(1.25, "in", -0.14, -0.42, [-45, 8, 10], [-95, 9, 20], [-35, 6, 0],
                    [-0.29, 0.70, -0.24], 0.10, 0.7, (-0.8, 0.3, -0.45), "load: deepest coil"))
    # 1.30 (f36) HA!: the hips drive forward, the back leg locks out long and straight, the back folds forward on one
    # line from the back heel out through the arms; both arms snap straight forward, palms out, heels together
    K.append(release(1.30, "snap", 0.10, -0.33, [-14, 26, 0], [3, 44, 0], [0, 22, 0], [0.0, 0.96, 0.0],
                     "HA! arms thrust, palms out, heel to heel"))
    # 1.40 (f39) the beam's kick: rocked back a hair on the long back leg, arms locked
    K.append(release(1.40, "out", 0.06, -0.31, [-14, 22, 0], [3, 38, 0], [0, 20, 0], [0.0, 0.98, 0.0],
                     "recoil: the beam pushes back"))
    # 2.00 (f55) holding the beam (moving hold): leaning back in
    K.append(release(2.0, "inout", 0.09, -0.32, [-14, 25, 0], [3, 42, 0], [0, 22, 0], [0.0, 0.97, 0.0],
                     "holding the beam"))
    return {"length": 2.0, "arm_space": "chest",
            # overlap (2026-11-25): both hands share one setting (stacked heel to heel = one unit, they must not split);
            # the HA! drive goes hips > chest > arms > palms, the head settles last
            "overlap": {"spine": [1.0, 6], "R": [1.5, 8], "L": [1.5, 8], "Rfist": [2.0, 6], "Lfist": [2.0, 6],
                        "head": [2.0, 10]},
            "about": "Kamehameha in place: wide low straddle, open hands cupped at the back hip (2D f1-35), then "
                     "HA! (f36-37): hips drive forward, back leg locks out, both arms thrust, palms out heel to heel, "
                     "held to f55.", "keys": K}


# ---------------------------------------------------------------- ultimate: aerial two-handed kamehameha
# Daniel 2026-11-25 (blocking): jump from the ground; in the air BOTH arms pulled back like a bird's wings on the
# backstroke ("only the pull back of the motion"; replaces his first pick, hands cupped at the hip): back leg long,
# front knee up, body arched; at 2D f10-f11 (~0.9 s) BOTH palms thrust,
# flat, side by side (thumbs together, fingers up: a two-handed push), knee tucked; the beam FX fires at frame 13
# (~1.2 s) as drawn; ends tucked in the air (both knees forward). 2D: 27 frames x 92.6 ms = 2.5 s. He hangs at the apex
# through the charge and beam (an anime hang, not real flight time).
REST_HIPS = 0.917


def air_feet(H, back="long", front="knee", hz=0.0):
    """Ankles for a body whose hips are H m above rest: back (right) leg long and trailing / hanging straight down /
    tucked; front (left) knee up (thigh forward, shin hanging) / tucked / hanging."""
    hy = REST_HIPS + H - 0.05                         # hip joints
    legs = {"long": ([-0.10, hy - 0.60, hz - 0.56], (-0.1, -0.3, 1), 55),
            "down": ([-0.10, hy - 0.80, hz - 0.08], (-0.1, 0.0, 1), 30),
            "knee": ([0.12, hy - 0.30, hz + 0.40], (0.1, 0.5, 1), 35),
            "tuck": ([0.13, hy - 0.26, hz + 0.26], (0.1, 0.7, 1), 40),
            "rtuck": ([-0.13, hy - 0.34, hz + 0.26], (-0.1, 0.6, 1), 40)}
    a, kr, pr = legs[back]
    b, kl, pl = legs[front]
    return ({"ankle": r3(a), "knee": r3(U(kr)), "yaw": -10, "pitch": pr},
            {"ankle": r3(b), "knee": r3(U(kl)), "yaw": 10, "pitch": pl})


def ultimate():
    K = []

    def push(t, ease, H, hz, hrot, chest, head, feet, at_y, label, bease=None, bent=None):
        """Both palms flat toward the target, side by side, thumbs together, fingers up and tipped a little forward
        (a wrist only bends back 60-70 deg, so locked level arms can't stand the fingers straight up)."""
        M = rot_euler(*chest)
        k = key(t, ease, [0, H, hz], hrot, chest, head,
                ([0, 0, 0.6], [-0.6, -1, 0], [0, 0, 1]), ([0, 0, 0.6], [0.6, -1, 0], [0, 0, 1]),
                feet[0], feet[1], bease=bease, label=label)
        k["R"] = palm(M, [0.08, -0.1, 0.5], [-0.4, -1, 0.1], [0, -0.45, 1], [0.12, 1, 0.45], 0.1, clav=[-4, 22])
        k["L"] = palm(M, [-0.08, -0.1, 0.5], [0.4, -1, 0.1], [0, -0.45, 1], [-0.12, 1, 0.45], 0.1, clav=[-4, 22])
        k["_M"] = chest
        y = REST_HIPS + H + at_y                      # at_y above the hips (shoulders sit ~0.5 up)
        if bent:                                      # the whip: the wings swing forward wide, hands closing in
            return meet(k, {"R": [-0.34, y, hz + bent], "L": [0.36, y + 0.03, hz + bent]})
        return meet(k, {"R": [-0.05, y, hz], "L": [0.05, y, hz]}, straight=0.544)

    def wing(t, ease, H, hz, hrot, chest, head, feet, Rr, Lr, label, curl=0.15, bease=None, fwd=False):
        """Daniel 2026-11-25: on the pull back the arms are a bird's wings on the BACKSTROKE only: both arms long,
        spread and swept back behind the shoulders, palms open facing back / down, fingers trailing, shoulder blades
        squeezed (clav pulled back), chest thrust out. Rr / Lr = body-space reach from each shoulder (m); the two
        sides differ a little (never twinned)."""
        M = rot_euler(*chest)
        k = key(t, ease, [0, H, hz], hrot, chest, head,
                (Rr, [-0.3, -1, -0.4], [0, -0.5, -1]), (Lr, [0.3, -1, -0.4], [0, -0.5, -1]),
                feet[0], feet[1], bease=bease, label=label)
        back = lambda r_, sx: palm(M, r_, [0.3 * sx, -1, -0.5], [0.15 * sx, -0.6, -1], [1.0 * sx, -0.15, -0.7], curl,
                                    clav=[4, -24])
        if fwd:                                       # mid-swing forward: palms turning to the target, fingers out
            back = lambda r_, sx: palm(M, r_, [0.35 * sx, -1, -0.7], [0.1 * sx, -0.5, 1], [1.0 * sx, -0.25, 0.1], curl,
                                        clav=[2, 6])
        k["R"], k["L"] = back(Rr, -1), back(Lr, 1)
        return k

    ground = (foot(-0.17, -0.20, yaw=-20, knee=(-0.4, 0.1, 1)), foot(0.15, 0.20, yaw=15, knee=(0.4, 0.1, 1)))
    # 0.00 (before 2D f1) crouch to jump: knees buried, chest folded forward over them, both arms swung back low
    # behind the hips (the jump's arm swing, the wings starting their pull back)
    K.append(wing(0.0, "inout", -0.40, -0.04, [-8, 38, 4], [-14, 50, 6], [-6, 30, 0], ground,
                  [-0.16, -0.48, -0.22], [0.14, -0.50, -0.18], "crouch: arms swung back low"))
    # 0.10 (f1-f2) take-off: legs drive out straight, heels up, toes pushing off; the arms sweep out to the sides on
    # the way up, the chest starting to open
    K.append(wing(0.10, "in", 0.02, 0.08, [-10, 18, 4], [-16, 14, 6], [-8, 10, 0],
                  (foot(-0.17, -0.20, y=0.07, pitch=62, yaw=-20, knee=(-0.3, 0.1, 1)),
                   foot(0.15, 0.20, y=0.07, pitch=62, yaw=15, knee=(0.3, 0.1, 1))),
                  [-0.46, -0.30, -0.16], [0.44, -0.26, -0.12], "take-off: arms sweep out"))
    # 0.45 (f5) apex: WINGS PULLED BACK: both arms long and spread, swept behind the shoulders, palms back / down,
    # fingers trailing; shoulder blades squeezed, chest thrust out, back ARCHED; the right leg long and trailing, the
    # left knee up, eyes on the target
    K.append(wing(0.45, "out", 0.85, 0.10, [-10, -16, 4], [-14, -26, 6], [-6, 10, 0], air_feet(0.85, "long", "knee", 0.10),
                  [-0.25, -0.20, -0.47], [0.28, -0.16, -0.46], "apex: wings pulled back"))
    # 0.74 (f9) load (moving hold): the wings pull further back and a little up, the arch deepens
    K.append(wing(0.74, "inout", 0.88, 0.06, [-12, -22, 6], [-16, -34, 8], [-8, 12, 0], air_feet(0.88, "long", "knee", 0.06),
                  [-0.21, -0.13, -0.50], [0.24, -0.09, -0.49], "load: wings all the way back"))
    # 0.83 (f10) whip (breakdown): the hips come forward first, the chest folds over a beat behind, the arms swing
    # forward from the wings and the hands meet at chest height, arms still bent; the front knee starts to tuck, the back leg swings under
    K.append(wing(0.83, "in", 0.88, 0.10, [-4, 6, 2], [-8, 14, 4], [-4, 6, 0], air_feet(0.88, "down", "knee", 0.10),
                  [-0.54, -0.16, 0.12], [0.53, -0.12, 0.16], "whip: wings swing forward", fwd=True))
    # 0.93 (f11) PUSH: both arms snap out locked and level, palms flat side by side; knee tucked high, the other leg
    # hanging straight down; chest square to the target and leaning into it
    K.append(push(0.93, "snap", 0.86, 0.14, [0, -6, 0], [0, 18, 0], [0, 6, 0], air_feet(0.86, "down", "tuck", 0.14),
                  0.47, "PUSH: palms out, side by side"))
    # 1.20 (f13-14) the beam fires (moving hold up to it): a breath deeper into the push
    K.append(push(1.20, "inout", 0.86, 0.16, [0, -4, 0], [0, 22, 0], [0, 8, 0], air_feet(0.86, "down", "tuck", 0.16),
                  0.47, "beam fires"))
    # 1.30 recoil: the beam shoves him back in the air, chest rocked up, legs swinging forward
    K.append(push(1.30, "out", 0.88, 0.02, [0, -14, 0], [0, 8, 0], [0, 2, 0], air_feet(0.88, "down", "tuck", 0.02),
                  0.49, "recoil: the beam pushes back"))
    # 2.04 (f23) holding the beam (moving hold): leaning back into it
    K.append(push(2.04, "inout", 0.86, 0.06, [0, -8, 0], [0, 16, 0], [0, 6, 0], air_feet(0.86, "down", "tuck", 0.06),
                  0.47, "holding the beam"))
    # 2.13 (f24) the legs drop out straight as the beam ends
    K.append(push(2.13, "inout", 0.84, 0.06, [0, -4, 0], [0, 16, 0], [0, 6, 0], air_feet(0.84, "down", "knee", 0.06),
                  0.46, "legs drop out"))
    # 2.50 (f26-27) tucked in the air: both knees up forward, sitting back, arms still out, starting to fall
    K.append(push(2.50, "out", 0.74, 0.04, [0, -22, 0], [0, 4, 0], [0, -2, 0], air_feet(0.74, "rtuck", "tuck", 0.04),
                  0.44, "tucked in the air"))
    return {"length": 2.5, "arm_space": "chest",
            # overlap from blocking: the two hands move as one unit (side by side) so they share one value
            "overlap": {"spine": [1.0, 6], "R": [1.5, 8], "L": [1.5, 8], "Rfist": [2.0, 6], "Lfist": [2.0, 6],
                        "head": [2.0, 10]},
            "about": "Aerial two-handed kamehameha: jump, both arms pulled back like wings at the apex (2D f2-f9), "
                     "both palms pushed out flat side by side (f10-f11), beam from frame 13 held to f23, ends tucked "
                     "in the air (f26-27).", "keys": K}


CLIPS = {"attack_normal": attack_normal, "attack_special": attack_special, "ultimate": ultimate}


def main(argv):
    spec = json.load(open(OUT)) if os.path.exists(OUT) else {"format": "pb_anim3d", "version": 1, "clips": {}}
    spec["notes"] = (
        "Puck is unarmed: every hand is a locked-wrist punching fist (anim3d `fists`). Authored in "
        "v3/tools/puck/gen_puck.py, one move at a time, each reviewed by Daniel from GIF stills "
        "(v3/tools/puck/review/go.sh). Daniel's corrections (2026-11-24/25): wrists placed with intention, never "
        "flopping; never hit with the fingers - the first two knuckles lead, forearm pointing through them at the "
        "target; bend the back - a committed punch folds the body over and the fist follows through past the target; "
        "the line of action is ONE smooth curve from the back foot through the hips and back out along the arm (no "
        "hunched kink, head on the curve); watch the punch's line (attack_normal is an OVERHAND: over the top, going "
        "down); frame 1 of attack_normal is a WIND-UP (right arm folded behind a shoulder pulled back and down, left "
        "arm leads); no extra hits he did not describe ('hook follow up' = the follow-through). attack_normal approved "
        "('good enough') 2026-11-25. attack_special = kamehameha, IN PLACE, approved ('bake it') 2026-11-25: wide "
        "low side-on straddle, open hands cupped round a ball at the back hip (right under palm up, left on top palm "
        "down, wrists together, chest turned ~90 deg toward them, upright), then HA!: feet stay put, hips drive "
        "forward, back leg locks out, arms LOCKED straight and level, hands stacked VERTICALLY heel to heel (left "
        "fingers up, right fingers down), palms cupped ~27 deg toward each other round the beam (a wrist bends back "
        "only 60-70 deg). His 'what is happening with his arms' = bent, flared elbows crossing in an X: thrust arms "
        "are placed straight (gen_puck.meet straight=), and every open-hand key sets its clav (anim3d carries a "
        "left-out control over from the key before). Ultimate = Gogeta's Big Bang Kamehameha in the air: both arms cocked back, then "
        "a one-handed palm thrust with a knee tucked; reference: arm flung far back, body arched, other hand at the "
        "face, front knee up, back leg long and straight. attack_normal_3 = shoryuken: keep the coiled crouch as a "
        "moving hold. Moves travel (root motion); kamehamehas stay in place. Overlap pass (2026-11-25, Daniel: "
        "ZZZ-snappy 1-2 frames, per-part lag in anim3d, 'pull body keys earlier', kamehameha 'bake it'): clip "
        "`overlap` springs (hips lead > chest > arm > fist last, head loosest, free arm tighter; the kamehameha's "
        "stacked hands share one value so they never split); attack_normal's inner keys sit OVERLAP_LEAD 25 ms early "
        "so the lagging fist still lands on the approved frames (95% out at 167 ms, full at 183 ms). New moves get "
        "overlap from blocking.")
    for name in (argv or CLIPS):
        spec["clips"][name] = CLIPS[name]()
    json.dump(spec, open(OUT, "w"), indent=1)
    print("wrote", os.path.relpath(OUT), sorted(spec["clips"]))


if __name__ == "__main__":
    main(sys.argv[1:])
