"""Key-pose animation authoring for V3 fighters (v3/RIG_SPEC.md rig), no Blender needed.

    python v3/tools/anim3d.py hooded_blades            bake characters/hooded_blades/hooded_blades.anim3d.json
                                                       into characters/hooded_blades/hooded_blades.glb
    python v3/tools/anim3d.py hooded_blades --check    bake in memory + run v3/tools/anim_audit.py on it

Why (Daniel 2026-11-22): clips guessed from 2D drawings (retarget2d.py) bend elbows / knees backward, flip limbs and
float off balance. Here a clip is a short list of KEY POSES written as controls an animator would use, and every
frame is solved on a real rig:

- Arms / legs = two-bone IK to a hand / ankle target with a POLE (which way the elbow / knee points). The upper bone
  is turned so the joint's own hinge axis (measured from the body's motion-capture clips) is the bend axis, so an
  elbow or knee can only fold the way it really folds, and never past its range.
- Blades: `blade` = the direction the blade points. The forearm turns (pronation, limited) to bring the blade round
  its axis and the wrist bends the rest (limited); what's left over is reported, never forced through the wrist.
- Feet: an ankle target + yaw / pitch. A foot that keeps the same target between keys stays planted (no sliding).
- Hips position / turn, a spine turn spread over the 3 spine bones, a head turn spread over neck + head, clavicles
  lift on their own when an arm goes up.
- Timing: key times in seconds; each key says how the move INTO it eases (linear, in, out, inout, snap = fast
  start then settle, hold = step). Positions follow a smooth curve through the keys (arcs, no corners); then the
  clip is baked at 30 fps.

File format (`characters/<name>/<name>.anim3d.json`, format `pb_anim3d`):
    {"format": "pb_anim3d", "version": 1, "clips": {"attack_normal": {"length": 0.5, "keys": [
        {"t": 0.0, "ease": "inout",
         "hips": {"pos": [x, y, z], "rot": [yaw, pitch, roll]},      (pos = offset from rest hips, m; deg)
         "spine": [yaw, pitch, roll], "head": [yaw, pitch, roll],    (deg, relative to the parent)
         "R": {"hand": [x, y, z], "pole": [x, y, z], "blade": [x, y, z], "roll": deg,    (body space, m)
               "grip": "fwd" | "rev", "twirl": deg},     (reverse grip / blade spun in the fingers; tweened between keys)
         "L": {...},
         "fR": {"ankle": [x, y, z], "pole": [x, y, z], "yaw": deg, "pitch": deg},
         "fL": {...}}, ...]}}}
Body space: +Z = forward (toward the target), +Y = up, -X = the fighter's right (near) side, origin between the feet
on the ground, metres. Any control left out of a key is carried from the previous key (first key: rest-ish default).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retarget2d as r  # noqa: E402
import anim_audit  # noqa: E402

FPS = 60                # fast anime snaps (a thrust to a recoil in 30 ms) need 60 fps keys; V3 plays any rate
# joint limits (deg)
FLEX_MAX = {"elbow": 150.0, "knee": 155.0}
PRONATE = 95.0          # forearm twist either way
WRIST = 75.0            # wrist bend
SWIVEL = 35.0           # the solver may swing an elbow this far round the shoulder->hand line to save twist / wrist
SPINE_SPLIT = (0.25, 0.35, 0.40)
HEAD_SPLIT = (0.4, 0.6)
D2R = math.pi / 180


def rot_euler(yaw, pitch, roll):
    """yaw about +Y (positive = turn to the fighter's LEFT, i.e. +Z toward +X), pitch about the body's left/right axis
    (positive = lean forward / look down), roll about +Z (positive = tip toward the fighter's right side, -X)."""
    ry = r.rot_axis(np.array([0, 1.0, 0]), yaw * D2R)
    rx = r.rot_axis(np.array([1.0, 0, 0]), pitch * D2R)
    rz = r.rot_axis(np.array([0, 0, 1.0]), roll * D2R)
    return rx @ ry @ rz          # turn first, then lean toward the TARGET (+Z) whatever way the body is turned


def ease(kind, u):
    u = min(max(u, 0.0), 1.0)
    if kind == "linear":
        return u
    if kind == "in":
        return u * u * u
    if kind == "out":
        return 1 - (1 - u) ** 3
    if kind == "snap":                     # most of the move in the first third, then a long settle
        return 1 - (1 - u) ** 5
    if kind == "hold":
        return 0.0 if u < 1 else 1.0
    return u * u * (3 - 2 * u) if kind == "smooth" else (4 * u ** 3 if u < .5 else 1 - (-2 * u + 2) ** 3 / 2)   # inout


def catmull(p0, p1, p2, p3, s):
    """Centripetal-ish Catmull-Rom between p1 and p2 (uniform; keys are poses, so spacing is fine)."""
    s2, s3 = s * s, s * s * s
    return 0.5 * ((2 * p1) + (-p0 + p2) * s + (2 * p0 - 5 * p1 + 4 * p2 - p3) * s2 + (-p0 + 3 * p1 - 3 * p2 + p3) * s3)


class Body:
    """The shared body's rig + what the solver needs to know about it."""

    def __init__(self, path=None):
        self.j, self.b = r.read_glb(path or r.BODY)
        if "Weapon_L" not in [n.get("name") for n in self.j["nodes"]]:
            self.j, self.b = r.add_left_blade(self.j, self.b)
        rig = self.rig = r.Rig(self.j, self.b)
        self.grip = r.grip_pose(rig)
        self.HI = rig.i("Hips")
        self.hp = rig.parent[self.HI]
        self.hinge = self._hinges()

    def P(self, name):
        return self.rig.restP[self.rig.i(name)]

    def _hinges(self):
        """Elbow / knee hinge axis (in the lower bone's rest-local frame, positive = flexion) from the body's mocap."""
        rig, j, b = self.rig, self.j, self.b
        out = {}
        for bone in ("RightForeArm", "LeftForeArm", "RightLeg", "LeftLeg"):
            i = rig.i(bone)
            V = []
            for an in j["animations"]:
                for ch in an["channels"]:
                    if ch["target"]["node"] != i or ch["target"]["path"] != "rotation":
                        continue
                    q = r.acc_array(j, b, an["samplers"][ch["sampler"]]["output"]).astype(float)
                    ax_bone = r.unit(rig.T[next(c for c in j["nodes"][i]["children"] if j["nodes"][c].get("name"))])
                    for x in q:
                        D = rig.R[i].T @ r.q2m(x)
                        v = anim_audit.Auditor.swing(D, ax_bone)      # twist about the bone itself left out
                        if np.linalg.norm(v) > 15 * D2R:
                            V.append(v)
            V = np.array(V)
            ax = np.linalg.svd(V, full_matrices=False)[2][0]
            if np.mean(V @ ax) < 0:
                ax = -ax
            out[bone] = r.unit(ax)
        return out


def axis_angle(R):
    q = r.m2q(R)
    if q[3] < 0:
        q = -q
    s = np.linalg.norm(q[:3])
    return q[:3] / s * 2 * math.atan2(s, q[3]) if s > 1e-9 else np.zeros(3)


def frame_from(a_loc, a_w, b_loc, b_w):
    """Rotation M with M @ a_loc = a_w exactly and M @ b_loc as close to b_w as possible."""
    a1, b1 = r.unit(a_loc), r.unit(b_loc - np.dot(b_loc, r.unit(a_loc)) * r.unit(a_loc))
    a2, b2 = r.unit(a_w), r.unit(b_w - np.dot(b_w, r.unit(a_w)) * r.unit(a_w))
    L = np.column_stack([a1, b1, np.cross(a1, b1)])
    W = np.column_stack([a2, b2, np.cross(a2, b2)])
    return W @ L.T


class Solver:
    def __init__(self, body):
        self.B = body
        self.rig = body.rig
        self.notes = []
        self.prev = {}          # last frame's choices (twist, bend side): keeps the solution continuous

    # -- helpers on the working pose
    def fk(self):
        rig = self.rig
        T0 = rig.T[self.B.HI]
        rig.T[self.B.HI] = self.hipsT
        W, P = rig.fk(self.local)
        rig.T[self.B.HI] = T0
        return W, P

    def set_world(self, name, Wn, W=None):
        rig = self.rig
        i = rig.i(name)
        if W is None:
            W, _ = self.fk()
        self.local[i] = W[rig.parent[i]].T @ Wn

    def pose(self, c, t):
        """Solve one frame from the interpolated controls c -> (local rotations, hips translation)."""
        rig, B = self.rig, self.B
        self.local = dict(B.grip)
        # hips
        hips_rot = rot_euler(*c["hips_rot"])
        world_hips = B.P("Hips") + np.array(c["hips_pos"])
        W, P = rig.fk(self.local)
        self.hipsT = W[B.hp].T @ (world_hips - P[B.hp])
        self.set_world("Hips", hips_rot @ rig.restW[B.HI])
        # spine: parts of the spine turn, each relative to its parent
        sy, sp, sr = c["spine"]
        for name, k in zip(("Spine", "Spine1", "Spine2"), SPINE_SPLIT):
            W, _ = self.fk()
            i = rig.i(name)
            par = W[rig.parent[i]] @ rig.R[i]
            # the turn is about the parent's CURRENT body axes (a leaning spine keeps leaning)
            Wp = W[rig.parent[i]] @ rig.restW[rig.parent[i]].T
            self.local[i] = W[rig.parent[i]].T @ (Wp @ rot_euler(sy * k, sp * k, sr * k) @ Wp.T) @ par
        hy, hpitch, hr = c["head"]
        for name, k in zip(("Neck", "Head"), HEAD_SPLIT):
            W, _ = self.fk()
            i = rig.i(name)
            par = W[rig.parent[i]] @ rig.R[i]
            Wp = W[rig.parent[i]] @ rig.restW[rig.parent[i]].T
            self.local[i] = W[rig.parent[i]].T @ (Wp @ rot_euler(hy * k, hpitch * k, hr * k) @ Wp.T) @ par
        # legs before arms (arms don't change the legs)
        for side, S in (("fR", "Right"), ("fL", "Left")):
            f = c[side]
            W, P = self.fk()
            pole = np.array(f["pole"]) if f.get("knee") is None else P[rig.i(S + "UpLeg")] + r.unit(np.array(f["knee"], float))
            self.limb(S + "UpLeg", S + "Leg", S + "Foot", np.array(f["ankle"]), pole, "knee")
            W, P = self.fk()
            i = rig.i(S + "Foot")
            yaw = r.rot_axis(np.array([0, 1.0, 0]), f["yaw"] * D2R)
            right = yaw @ np.array([1.0, 0, 0])
            pitch = r.rot_axis(right, f["pitch"] * D2R)      # + = toes down
            self.set_world(S + "Foot", pitch @ yaw @ rig.restW[i], W)
            # ground contact: a heel / toe that ends up under the floor lifts the whole foot back onto it
            W, P = self.fk()
            low = min(P[rig.i(S + "ToeBase")][1], P[rig.i(S + "Toe_End")][1], P[i][1] - 0.09)
            if low < rig.rest_low - 0.005:
                ank = np.array(f["ankle"], float) + [0.0, rig.rest_low - low, 0.0]
                self.limb(S + "UpLeg", S + "Leg", S + "Foot", ank, pole, "knee")
                self.set_world(S + "Foot", pitch @ yaw @ rig.restW[i])
        to_body = self.chest_xform() if c.get("arm_space") == "chest" else (lambda p, d=False: np.array(p, float))
        for side, S in (("R", "Right"), ("L", "Left")):
            a = c[side]
            hand, pole = to_body(a["hand"]), to_body(a["pole"])
            if a.get("reach") is not None or a.get("elbow") is not None:
                W, P = self.fk()
                sh = P[rig.i(S + "Arm")]
                if a.get("reach") is not None:        # hand = shoulder + reach (arm length ~0.55 m = straight)
                    hand = sh + to_body(a["reach"], True)
                if a.get("elbow") is not None:        # the elbow points this way from the shoulder
                    pole = sh + r.unit(to_body(a["elbow"], True))
            self.clavicle(S, hand)
            want = to_body(a["blade"], True) if a.get("blade") is not None else None
            # grip (Daniel 2026-11-23): "rev" = reverse grip, the blade comes out of the pinky side; between a forward
            # and a reverse key the weapon turns 180 deg in the fingers (the flip). `twirl` = extra turns (deg).
            g = a["g"] if a.get("g") is not None else (1.0 if a.get("grip") == "rev" else 0.0)
            self.weapon(S, a.get("twirl", 0.0) + 180.0 * g)
            if want is not None:                         # the fist aims as for a forward grip: reverse = the other way
                want = to_body(a["aim"], True) if a.get("aim") is not None else (-want if g > 0.5 else want)
            self.limb(S + "Arm", S + "ForeArm", S + "Hand", hand, pole, "elbow", swivel=a.get("swivel", SWIVEL),
                      want=want, roll=a.get("roll", 0.0), t=t)
            if want is not None:
                self.blade(S, want, a.get("roll", 0.0), t)
        return dict(self.local), self.hipsT.copy()

    def chest_xform(self):
        """Chest space -> body space: a point / direction given as if the chest (Spine2) were at rest goes where the
        chest is now, so the arms ride with the torso (a turning, leaning body carries its hands)."""
        rig = self.rig
        W, P = self.fk()
        i = rig.i("Spine2")
        M = W[i] @ rig.restW[i].T
        o0, o1 = rig.restP[i], P[i]
        return lambda p, d=False: M @ np.array(p, float) if d else o1 + M @ (np.array(p, float) - o0)

    def body_to_chest(self):
        """Inverse of chest_xform (to convert body-space keys)."""
        rig = self.rig
        W, P = self.fk()
        i = rig.i("Spine2")
        M = W[i] @ rig.restW[i].T
        o0, o1 = rig.restP[i], P[i]
        return lambda p, d=False: M.T @ np.array(p, float) if d else o0 + M.T @ (np.array(p, float) - o1)

    def clavicle(self, S, hand):
        """Shoulder (clavicle) follows the arm a little: up to 20 deg up / 15 forward toward the hand."""
        rig = self.rig
        W, P = self.fk()
        i = rig.i(S + "Shoulder")
        sh = P[rig.i(S + "Arm")]
        d = r.unit(hand - sh)
        lift = max(0.0, d[1]) * 20.0
        fwd = d[2] * 12.0
        side = 1.0 if S == "Left" else -1.0
        R = r.rot_axis(np.array([0, 0, 1.0]), side * lift * D2R) @ r.rot_axis(np.array([0, 1.0, 0]), -side * fwd * D2R)
        self.set_world(S + "Shoulder", R @ W[i], W)

    def limb(self, upper, lower, end, target, pole, kind, swivel=0.0, want=None, roll=0.0, t=0.0):
        """Two-bone IK with a pole; the bend happens about the lower joint's own hinge axis, within its range.
        With a blade to point (want) and swivel > 0, the elbow may swing up to `swivel` deg round the shoulder->hand
        line, picking the spot that needs the least forearm twist / wrist bend (and stays near last frame's)."""
        if want is None or swivel <= 0:
            return self._limb(upper, lower, end, target, pole, kind)
        side = "R" if upper.startswith("Right") else "L"
        W, P = self.fk()
        base = P[self.rig.i(upper)]
        dn = r.unit(target - base)
        keep, kprev = dict(self.local), dict(self.prev)
        last = self.prev.get("sw" + side, 0.0)
        best = None
        for a in np.arange(-swivel, swivel + 1e-6, 5.0):
            self.local, self.prev = dict(keep), dict(kprev)
            self._limb(upper, lower, end, target, base + r.rot_axis(dn, a * D2R) @ (pole - base), kind)
            sc = self.blade(upper[:-3], want, roll, t, apply=False) + abs(a) * 0.03 + abs(a - last) * 0.1
            if best is None or sc < best[0]:
                best = (sc, a)
        self.local, self.prev = keep, kprev
        self.prev["sw" + side] = best[1]
        self._limb(upper, lower, end, target, base + r.rot_axis(dn, best[1] * D2R) @ (pole - base), kind)

    def _limb(self, upper, lower, end, target, pole, kind):
        rig, B = self.rig, self.B
        W, P = self.fk()
        iu, il, ie = rig.i(upper), rig.i(lower), rig.i(end)
        L1 = np.linalg.norm(rig.T[il])
        L2 = np.linalg.norm(rig.T[ie])
        base = P[iu]
        d = target - base
        dist = np.linalg.norm(d)
        lo = abs(L1 - L2) + 1e-3
        flexmax = FLEX_MAX[kind]
        lo = max(lo, math.sqrt(L1 * L1 + L2 * L2 - 2 * L1 * L2 * math.cos((180 - flexmax) * D2R)))
        hi = (L1 + L2) * 0.9995
        if dist > hi + 0.02 or dist < lo - 0.02:
            self.notes.append("%s target %s by %.0f cm" % (lower, "out of reach" if dist > hi else "too close", 100 * abs(dist - min(max(dist, lo), hi))))
        dist = min(max(dist, lo), hi)
        dn = r.unit(d)
        target = base + dn * dist
        # elbow / knee in the plane (base, target, pole)
        pv = pole - base
        pv = pv - np.dot(pv, dn) * dn
        if np.linalg.norm(pv) < 1e-6:
            pv = np.cross(dn, [0, 1.0, 0])
        pv = r.unit(pv)
        cosA = (L1 * L1 + dist * dist - L2 * L2) / (2 * L1 * dist)
        A = math.acos(max(-1, min(1, cosA)))
        elbow = base + L1 * (math.cos(A) * dn + math.sin(A) * pv)
        u_dir = r.unit(elbow - base)
        l_dir = r.unit(target - elbow)
        # hinge axis: the bend must be a positive (flexing) rotation of the lower bone about it
        # bend-plane normal from the pole (not from the bones: that one flips sign when the limb passes straight)
        n = -r.unit(np.cross(dn, pv))
        h_in_upper = rig.R[il] @ B.hinge[lower]           # hinge axis in the upper bone's local frame
        best = None
        prev_s = self.prev.get(upper)
        for s in (1.0, -1.0):
            Wu = frame_from(rig.T[il], u_dir, h_in_upper, s * n)
            Wl0 = Wu @ rig.R[il]
            cur = Wl0 @ r.unit(rig.T[ie])
            hw = Wu @ h_in_upper
            ang = math.atan2(np.dot(np.cross(cur, l_dir), hw), np.dot(cur, l_dir))
            score = abs(ang - min(max(ang, 0.0), flexmax * D2R)) + (0.0 if prev_s in (None, s) else 1e-3)
            if best is None or score < best[0]:
                best = (score, Wu, ang, s)
        _, Wu, ang, self.prev[upper] = best
        ang = min(max(ang, 0.0), flexmax * D2R)
        self.set_world(upper, Wu, W)
        W, P = self.fk()
        self.local[il] = rig.R[il] @ r.rot_axis(B.hinge[lower], ang)

    def weapon(self, S, deg):
        """Turn the weapon in the fingers by deg about the axis across the fist (blade x fingers): 180 = reverse grip
        (blade out of the pinky side), 360 = a full twirl back to forward grip."""
        rig = self.rig
        side = "R" if S == "Right" else "L"
        iw, it = rig.i("Weapon_" + side), rig.i("WeaponTip_" + side)
        if abs(deg) < 1e-6:
            self.local.pop(iw, None)
            return
        blade_h = rig.R[iw] @ r.unit(rig.T[it])
        fing = r.unit(rig.T[rig.i(S + "HandMiddle1")])
        ax = r.unit(np.cross(blade_h, fing))
        self.local[iw] = r.rot_axis(ax, deg * D2R) @ rig.R[iw]

    def blade(self, S, want, roll, t, apply=True):
        """Point the blade: forearm twist (within PRONATE) brings the blade round the forearm, the wrist bends the rest
        (within WRIST). `roll` turns the blade about itself only through the forearm twist."""
        rig = self.rig
        side = "R" if S == "Right" else "L"
        W, P = self.fk()
        ifa, ih, iw, it = rig.i(S + "ForeArm"), rig.i(S + "Hand"), rig.i("Weapon_" + side), rig.i("WeaponTip_" + side)
        want = r.unit(want)
        axis_l = r.unit(rig.T[ih])                       # forearm axis in its own frame
        blade_h = rig.R[iw] @ r.unit(rig.T[it])          # blade dir in the hand frame
        base_fa = self.local.get(ifa, rig.R[ifa])
        Wpar = W[rig.parent[ifa]]
        best = None
        prev = self.prev.get("tw" + side)
        for tw in np.linspace(-PRONATE, PRONATE, 77):
            loc = base_fa @ r.rot_axis(axis_l, tw * D2R)
            Wfa = Wpar @ loc
            Wh = Wfa @ rig.R[ih]
            cur = Wh @ blade_h
            err = math.degrees(math.acos(max(-1, min(1, np.dot(cur, want)))))
            # least wrist bend, a little less twist, and above all no jump from last frame's twist
            score = max(0.0, err - WRIST) * 2 + err * 0.15 + abs(tw) * 0.02 + (0 if prev is None else abs(tw - prev) * 0.6)
            if best is None or score < best[0]:
                best = (score, tw, err)
        if not apply:
            return best[0]
        _, tw, err = best
        self.prev["tw" + side] = tw
        tw = min(max(tw + roll, -PRONATE), PRONATE)
        self.local[ifa] = base_fa @ r.rot_axis(axis_l, tw * D2R)
        W, P = self.fk()
        Wh = W[ifa] @ rig.R[ih]
        cur = Wh @ blade_h
        R = r.rot_between(cur, want)
        a = math.degrees(math.acos(max(-1, min(1, np.dot(r.unit(cur), want)))))
        if a > WRIST:
            R = r.rot_axis(r.unit(np.cross(cur, want)), WRIST * D2R)
            if a > WRIST + 8:
                self.notes.append("t=%.2f %s blade off by %.0f deg (wrist limit)" % (t, side, a - WRIST))
        self.set_world(S + "Hand", R @ Wh, W)


DEFAULTS = None


def defaults(B):
    """A neutral standing pose in controls (rest-ish arms down)."""
    P = B.P
    return {"hips_pos": [0.0, 0.0, 0.0], "hips_rot": [0.0, 0.0, 0.0], "spine": [0.0, 0.0, 0.0], "head": [0.0, 0.0, 0.0],
            "R": {"hand": (P("RightArm") + [-0.05, -0.5, 0.1]).tolist(), "pole": [-0.3, 1.2, -0.6], "blade": [0, 0, 1], "roll": 0},
            "L": {"hand": (P("LeftArm") + [0.05, -0.5, 0.1]).tolist(), "pole": [0.3, 1.2, -0.6], "blade": [0, 0, 1], "roll": 0},
            "fR": {"ankle": P("RightFoot").tolist(), "pole": [-0.1, 0.5, 1.0], "yaw": 0, "pitch": 0},
            "fL": {"ankle": P("LeftFoot").tolist(), "pole": [0.1, 0.5, 1.0], "yaw": 0, "pitch": 0}}


def full_keys(B, keys):
    """Every key with every control (missing ones carried from the previous key)."""
    out, cur = [], defaults(B)
    for k in keys:
        nk = json.loads(json.dumps(cur))
        for name in ("spine", "head"):
            if name in k:
                nk[name] = list(k[name])
        if "hips" in k:
            if "pos" in k["hips"]:
                nk["hips_pos"] = list(k["hips"]["pos"])
            if "rot" in k["hips"]:
                nk["hips_rot"] = list(k["hips"]["rot"])
        for s in ("R", "L", "fR", "fL"):
            if s in k:
                nk[s].update(k[s])
        nk["t"], nk["ease"] = float(k["t"]), k.get("ease", "inout")
        out.append(nk)
        cur = nk
    return out


VEC_FIELDS = [("hips_pos",), ("hips_rot",), ("spine",), ("head",)] + \
    [(s, f) for s in ("R", "L") for f in ("hand", "pole")] + [(s, f) for s in ("fR", "fL") for f in ("ankle", "pole")]


OPT_FIELDS = [(s, f) for s in ("R", "L") for f in ("reach", "elbow")] + [(s, "knee") for s in ("fR", "fL")]


def _has(k, path):
    v = k
    for p in path:
        if not isinstance(v, dict) or v.get(p) is None:
            return False
        v = v[p]
    return True


def get(k, path):
    v = k
    for p in path:
        v = v[p]
    return np.array(v, float)


def interp(keys, t):
    """Controls at time t: eased time into the segment, Catmull-Rom on vectors, slerp on blade directions."""
    if t <= keys[0]["t"]:
        return keys[0]
    if t >= keys[-1]["t"]:
        return keys[-1]
    n = next(i for i in range(1, len(keys)) if keys[i]["t"] >= t)
    k1, k2 = keys[n - 1], keys[n]
    u = ease(k2["ease"], (t - k1["t"]) / max(k2["t"] - k1["t"], 1e-6))
    k0 = keys[max(0, n - 2)]
    k3 = keys[min(len(keys) - 1, n + 1)]
    c = json.loads(json.dumps(k1))
    for path in VEC_FIELDS + OPT_FIELDS:
        if _has(k1, path) and _has(k2, path):
            p1, p2 = get(k1, path), get(k2, path)
        else:                                          # an optional control on one side only: take the new key's
            tgt = c
            for p in path[:-1]:
                tgt = tgt[p]
            tgt[path[-1]] = k2[path[0]].get(path[1])
            continue
        # a held segment (same value) must stay exactly put: planted feet
        if np.allclose(p1, p2):
            v = p1
        else:
            v = catmull(get(k0, path) if _has(k0, path) else p1, p1, p2, get(k3, path) if _has(k3, path) else p2, u)
        tgt = c
        for p in path[:-1]:
            tgt = tgt[p]
        tgt[path[-1]] = v.tolist()
    for s in ("R", "L"):
        a, b = r.unit(np.array(k1[s]["blade"], float)), r.unit(np.array(k2[s]["blade"], float))
        ang = math.acos(max(-1, min(1, np.dot(a, b))))
        if ang < 1e-6:
            v = a
        else:
            ax = r.unit(np.cross(a, b)) if ang < math.pi - 1e-3 else r.unit(np.cross(a, [0, 1.0, 0]))
            v = r.rot_axis(ax, ang * u) @ a
        c[s]["blade"] = v.tolist()
        c[s]["roll"] = k1[s].get("roll", 0) * (1 - u) + k2[s].get("roll", 0) * u
        g1, g2 = (1.0 if k1[s].get("grip") == "rev" else 0.0), (1.0 if k2[s].get("grip") == "rev" else 0.0)
        c[s]["g"] = g1 * (1 - u) + g2 * u
        if g1 != g2:                                   # the fist's aim turns from one grip's aim to the other's
            a1, a2 = a * (1 - 2 * g1), b * (1 - 2 * g2)
            ang = math.acos(max(-1, min(1, np.dot(a1, a2))))
            ax = r.unit(np.cross(a1, a2)) if 1e-6 < ang < math.pi - 1e-3 else r.unit(np.cross(a1, [0, 1.0, 0]))
            c[s]["aim"] = (r.rot_axis(ax, ang * u) @ a1).tolist()
        else:
            c[s].pop("aim", None)
        c[s]["twirl"] = k1[s].get("twirl", 0) * (1 - u) + k2[s].get("twirl", 0) * u
    for s in ("fR", "fL"):
        for f in ("yaw", "pitch"):
            c[s][f] = k1[s][f] * (1 - u) + k2[s][f] * u
        # a foot moving to a new spot steps: it lifts through an arc instead of sliding over the floor
        a1, a2 = np.array(k1[s]["ankle"], float), np.array(k2[s]["ankle"], float)
        d = math.hypot(a2[0] - a1[0], a2[2] - a1[2])
        if d > 0.04:
            c[s]["ankle"][1] += min(0.18, 0.35 * d) * math.sin(math.pi * u)
    return c


def bake_clip(B, spec, notes=None, dense=False):
    keys = full_keys(B, spec["keys"])
    for k in keys:
        k["arm_space"] = spec.get("arm_space", "body")
    length = float(spec.get("length") or keys[-1]["t"])
    n = max(2, int(round(length * FPS)) + 1)
    times = [min(length, f / FPS) for f in range(n)]
    sv = Solver(B)
    poses = [sv.pose(interp(keys, t), t) for t in times]
    if notes is not None:
        notes.extend(sorted(set(sv.notes)))
    if dense:
        return times, poses
    # stored as key poses: the authored keys always, plus whatever the tweening needs to stay on the solved motion
    import keyreduce
    must = keyreduce.snap_must(times, [k["t"] for k in keys])
    tol = spec.get("key_tol") or (keyreduce.TOL_BODY, keyreduce.TOL_TIP)   # looser = fewer key poses (library moves)
    return keyreduce.reduce(B.rig, times, poses, must=must, tol_body=tol[0], tol_tip=tol[1])


def spec_path(name):
    return os.path.join(r.CHARS, name, name + ".anim3d.json")


def bake_file(name, B=None, notes=None):
    """{clip: (times, poses)} for every clip in the character's .anim3d.json ({} if it has none)."""
    p = spec_path(name)
    if not os.path.exists(p):
        return {}
    spec = json.load(open(p, encoding="utf-8"))
    B = B or Body()
    return {c: bake_clip(B, s, notes) for c, s in spec["clips"].items()}


def write_into(name, clips, B):
    """Replace / add these clips in characters/<name>/<name>.glb (clips-only file), keep the rest."""
    path = os.path.join(r.CHARS, name, name + ".glb")
    cj, cb = r.read_glb(path)
    rig = B.rig
    w = r.Writer()
    anims = []
    for a in cj["animations"]:
        if a["name"] in clips:
            continue
        a = json.loads(json.dumps(a))
        for sm in a["samplers"]:
            sm["input"] = w.copy(cj, cb, sm["input"])
            sm["output"] = w.copy(cj, cb, sm["output"])
        anims.append(a)
    out = json.loads(json.dumps(cj))
    out["animations"] = []
    out["accessors"], out["bufferViews"] = w.accs, w.views
    # the new clips through retarget2d.pack, then their accessors copied into this file's buffer
    tmp, tbin = r.pack(B.j, B.b, meshes=False, keep_anims=False, new_clips=clips, rig=rig)
    remap = {}
    for a in tmp["animations"]:
        for sm in a["samplers"]:
            for key in ("input", "output"):
                ai = sm[key]
                if ai not in remap:
                    remap[ai] = w.copy(tmp, tbin, ai)
                sm[key] = remap[ai]
        anims.append(a)
    order = {n: i for i, n in enumerate([a["name"] for a in cj["animations"]])}
    anims.sort(key=lambda a: order.get(a["name"], 999))
    out["animations"] = anims
    out["accessors"], out["bufferViews"] = w.accs, w.views
    while len(w.bin) % 4:
        w.bin.append(0)
    out["buffers"] = [{"byteLength": len(w.bin)}]
    ex = out["scenes"][out.get("scene", 0)].setdefault("extras", {})
    ex.setdefault("pb_body", {})["anim3d"] = sorted(clips)
    pk = {k: v for k, v in (ex.get("pb_keys") or {}).items() if k not in clips}
    pk.update((tmp["scenes"][tmp.get("scene", 0)].get("extras") or {}).get("pb_keys") or {})
    ex["pb_keys"] = pk
    total = r.save_glb(path, out, bytes(w.bin))
    return path, total


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    name = argv[0]
    B = Body()
    notes = []
    clips = bake_file(name, B, notes)
    if not clips:
        print("no %s" % os.path.relpath(spec_path(name), r.ROOT))
        return 1
    for n in notes:
        print("  note:", n)
    if "--check" in argv:
        out, bin_ = r.pack(B.j, B.b, meshes=False, keep_anims=False, new_clips=clips, rig=B.rig)
        return anim_audit.report_from(out, bytes(bin_), B)
    path, total = write_into(name, clips, B)
    print("%s: %s (%d KB) - authored clips: %s" % (name, os.path.relpath(path, r.ROOT), total // 1024, ", ".join(sorted(clips))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
