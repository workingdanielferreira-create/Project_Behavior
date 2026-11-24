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


# ---------------------------------------------------------------- attack_normal: dash > overhand right > overhand follow-up
# Daniel 2026-11-24: both punches come OVER the top going DOWN onto the target (never from under going up); wrists
# locked straight with intention; bend the back - a committed punch moving forward folds the body over and the fist
# follows through past where it hit.
def attack_normal():
    K = []
    # 0.00 (2D f1-f2) mid-dash: pitched hard forward, right foot planted, left foot swinging through, right fist
    # forward at chest height, left arm back as a counterweight
    K.append(key(0.0, "inout", [0, -0.16, -0.20], [-8, 52, 0], [-14, 70, 4], [-4, 46, 0],
                 (line([-14, 70, 4], ext=0.72, dx=0.06), [-1, -0.3, 0], [0.7, 0.6, 0], [0, 24]),
                 ([0.12, -0.30, -0.42], [0.4, -0.6, -1], [0.2, 0.2, -1]),
                 foot(-0.13, -0.05, pitch=10, yaw=-8), foot(0.12, -0.62, y=0.12, pitch=45, knee=(0.1, -0.4, 1)),
                 label="mid-dash"))
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
    # 0.26 (f8) step through + re-cock: the back foot drives through, the body rises and turns back right, the right
    # fist pulled back up beside the head, elbow forward (2D f8-f10)
    K.append(key(0.26, "inout", [0, -0.14, 0.66], [-16, 38, 6], [-34, 50, 8], [8, 30, 4],
                 ([-0.12, 0.0, -0.10], [-1, 0.1, -0.2], [0.2, 0.3, 1], [8, -10]),
                 ([0.06, 0.0, 0.32], [0.6, -1, 0], [0.2, 0.2, -1]),
                 foot(-0.12, 0.40, y=0.18, pitch=20, yaw=-10, knee=(-0.1, 0.3, 1)), foot(0.13, 0.66, pitch=15, yaw=10, knee=(0.2, 0, 1)),
                 label="step through + re-cock high"))
    # 0.31 (f10) coiled hold (moving): right foot lands in front, fist drifts higher and further back, chest wrung
    K.append(key(0.31, "out", [0, -0.12, 0.80], [-22, 36, 8], [-44, 50, 8], [10, 28, 4],
                 ([-0.16, 0.02, -0.22], [-1, 0.2, -0.5], [0.2, 0.3, 1], [8, -20]),
                 ([0.10, -0.18, 0.30], [0.6, -1, 0], [0.2, 0.2, -1]),
                 foot(-0.12, 0.92, yaw=-10, knee=(-0.1, 0, 1)), foot(0.13, 0.66, pitch=25, yaw=15, knee=(0.2, -0.1, 1)),
                 label="coiled (hold)"))
    # 0.36 (f11) FOLLOW-UP OVERHAND lands: over the top and down again, the whole back folded over it
    K.append(key(0.36, "snap", [0, -0.13, 0.98], [26, 44, -8], [36, 66, -8], [8, 44, -6],
                 (line([36, 66, -8], dx=0.16, dy=-0.42), [-1, 0.5, 0.1], [0.6, -0.6, 0.1], [8, 36]),
                 ([-0.02, -0.06, 0.18], [0.4, -1, -0.5], [0.2, 0.2, -1], [0, -22]),
                 foot(-0.12, 0.92, yaw=-10, knee=(-0.1, 0, 1)), foot(0.13, 0.66, pitch=40, yaw=20, knee=(0.3, -0.2, 1)),
                 label="FOLLOW-UP OVERHAND lands"))
    # 0.40 (f12) follow-through and on: fist down and across past the target, back foot peeling off to keep moving
    K.append(key(0.40, "out", [0, -0.17, 1.08], [32, 54, -10], [50, 82, -10], [14, 58, -8],
                 (line([50, 82, -10], dx=0.45, dy=-0.25), [-1, 0.4, 0.5], [0.6, -0.5, 0.3], [-2, 40]),
                 ([-0.04, -0.08, 0.14], [0.4, -1, -0.5], [0.2, 0.2, -1], [0, -24]),
                 foot(-0.12, 0.92, pitch=15, yaw=-10, knee=(-0.1, 0, 1)), foot(0.13, 0.66, y=0.08, pitch=55, yaw=20, knee=(0.2, -0.4, 1)),
                 label="follow-through, moving on"))
    return {"length": 0.4, "arm_space": "chest", "physics": True, "fists": True,
            "about": "Dash > overhand right, over the top and down (lands 2D f5) > step through, re-cock high > "
                     "follow-up overhand (2D f11) > follow-through. Travels ~1.3 m.", "keys": K}


CLIPS = {"attack_normal": attack_normal}


def main(argv):
    spec = json.load(open(OUT)) if os.path.exists(OUT) else {"format": "pb_anim3d", "version": 1, "clips": {}}
    spec["notes"] = ("Puck is unarmed (fists). Authored in v3/tools/puck/gen_puck.py, one move at a time, each "
                     "reviewed by Daniel from GIF stills (2026-11-24). Ultimate = Gogeta's Big Bang Kamehameha in the "
                     "air: both arms cocked back, then a one-handed palm thrust with a knee tucked.")
    for name in (argv or CLIPS):
        spec["clips"][name] = CLIPS[name]()
    json.dump(spec, open(OUT, "w"), indent=1)
    print("wrote", os.path.relpath(OUT), sorted(spec["clips"]))


if __name__ == "__main__":
    main(sys.argv[1:])
