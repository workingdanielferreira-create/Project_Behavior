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
    return {"length": 0.4, "arm_space": "chest", "physics": True, "fists": True,
            "about": "Dash > wind-up > overhand right, over the top and down (lands 2D f5) > follow-through: down, "
                     "across and wrapped by the left shoulder (2D f7-f10) > back into the dash. ONE punch. Travels ~1.1 m.", "keys": K}


CLIPS = {"attack_normal": attack_normal}


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
        "('good enough') 2026-11-25. Ultimate = Gogeta's Big Bang Kamehameha in the air: both arms cocked back, then "
        "a one-handed palm thrust with a knee tucked; reference: arm flung far back, body arched, other hand at the "
        "face, front knee up, back leg long and straight. attack_normal_3 = shoryuken: keep the coiled crouch as a "
        "moving hold. Moves travel (root motion); kamehamehas stay in place.")
    for name in (argv or CLIPS):
        spec["clips"][name] = CLIPS[name]()
    json.dump(spec, open(OUT, "w"), indent=1)
    print("wrote", os.path.relpath(OUT), sorted(spec["clips"]))


if __name__ == "__main__":
    main(sys.argv[1:])
