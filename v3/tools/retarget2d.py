"""2D joint tracks -> 3D clips on the V3 test body (v3/RIG_SPEC.md rig), no Blender needed.

    python v3/tools/retarget2d.py [names ...] [--body path/to/body.glb]   (default: every character in ALL)

Reads characters/<name>/character.json: every action's frames, frame_ms and per-frame joint anchors
(hip, chest, neck, head, shL/shR, elL/elR, haL/haR, hpL/hpR, knL/knR, ftL/ftR, wtip; image px, the
figure faces right, R = near side, L = far side). Writes characters/<name>/<name>.glb = the body's SKELETON
(no mesh) + one clip per action (clip name = action name, one linear key per 2D frame), plus scene extras
pb_body {body, weapons {R, L}}. V3 and Rig Forge 3D put those clips on the shared body (ual_swordsman.glb, a
placeholder: the clips are bone-named and V3 retargets them onto whatever RIG_SPEC body is loaded; --body re-solves
them exactly on a new body). The shared body gets Weapon_L / WeaponTip_L + a blade_L mesh once (hidden unless a
character holds a second blade).

How a 2D pose becomes 3D (Daniel 2026-11-22: "infer depth"):
- 2D x = forward (+Z), 2D -y = up (+Y); the viewer's side is the near (right) side of the body (-X).
- Every bone keeps its 3D length. Where a 2D limb is shorter than its rig length, the rest of the length
  goes into depth: upper arms / thighs swing outward (near limbs toward the viewer, far limbs away),
  forearms / shins pick the side that brings the hand / foot back toward the shoulder / hip line.
- Pelvis and chest turn (yaw) from how far apart the 2D hip / shoulder points are; spine, neck and head
  lean along the 2D hip -> chest -> neck -> head line.
- A weapon hand turns so the blade (Weapon_R -> WeaponTip_R) points at the 2D weapon tip (wtip).
  Characters without a weapon (wtip on the hand) get the blade mesh removed. A blade in the far hand too
  (wtip2 off the hand, e.g. hooded_blades) adds Weapon_L / WeaponTip_L (Weapon_R mirrored) + a blade_L mesh,
  aimed at wtip2 the same way (Daniel 2026-11-22).
- Feet stay flat (turned with the pelvis) on the ground and follow the shin when lifted.
- Hips height follows the 2D hip point above the ground line, scaled by leg length; forward, the hips keep
  their 2D spot over the feet (relative to idle), so clips stay in place (RIG_SPEC 4) and the sim does the travel.
- Fingers: a closed grip (from the body's sword clip) on both hands.
- Clips without a 2D source (hit reactions, K.O., dodges, air, jump ...) come from the body at run time; V3 ignores
  the body's other attack / special / ultimate / locomotion clips for these characters so their own clips are used
  through the rig_spec fallbacks (e.g. attack_normal_3 -> attack_normal, sprint -> run).
"""
import json
import math
import os
import re
import struct
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHARS = os.path.join(ROOT, "characters")
BODY = os.path.join(CHARS, "ual_swordsman", "ual_swordsman.glb")

# body clips dropped when a character brings its own moves (they fall back to the character's clips)
DROP = re.compile(r"^(idle|run|walk|sprint|attack_normal(_\d+)?|attack_special(_\d+)?|ultimate(_\d+)?|transform|"
                  r"switch_in|switch_out|defend|parry)$")
CAM = np.array([-1.0, 0.0, 0.0])        # toward the viewer = the body's near (right) side


# ---------------------------------------------------------------- glb io
def read_glb(path):
    b = open(path, "rb").read()
    off, chunks = 12, {}
    while off < len(b):
        ln, typ = struct.unpack_from("<II", b, off)
        chunks[typ] = b[off + 8:off + 8 + ln]
        off += 8 + ln
    return json.loads(chunks[0x4E4F534A]), chunks.get(0x004E4942, b"")


NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
CSIZE = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}
CDT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}


def acc_bytes(j, b, ai):
    """An accessor's data, tightly packed."""
    a = j["accessors"][ai]
    bv = j["bufferViews"][a["bufferView"]]
    n, cs = NCOMP[a["type"]], CSIZE[a["componentType"]]
    el = n * cs
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0) or el
    if stride == el:
        return b[start:start + el * a["count"]]
    return b"".join(b[start + i * stride:start + i * stride + el] for i in range(a["count"]))


def acc_array(j, b, ai):
    a = j["accessors"][ai]
    return np.frombuffer(acc_bytes(j, b, ai), dtype=CDT[a["componentType"]]).reshape(a["count"], NCOMP[a["type"]])


class Writer:
    """Rebuilds the buffer: copies the accessors that are still used, appends new ones."""

    def __init__(self):
        self.bin = bytearray()
        self.views, self.accs = [], []
        self.done = {}

    def _view(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            v["target"] = target
        self.bin += data
        self.views.append(v)
        return len(self.views) - 1

    def copy(self, j, b, ai, target=None):
        if ai in self.done:                 # an accessor shared by several samplers / primitives is copied once
            return self.done[ai]
        self.done[ai] = self._copy(j, b, ai, target)
        return self.done[ai]

    def _copy(self, j, b, ai, target=None):
        a = dict(j["accessors"][ai])
        a.pop("byteOffset", None)
        a["bufferView"] = self._view(acc_bytes(j, b, ai), target)
        self.accs.append(a)
        return len(self.accs) - 1

    def floats(self, arr, typ, minmax=False):
        arr = np.ascontiguousarray(arr, dtype=np.float32)
        a = {"bufferView": self._view(arr.tobytes()), "componentType": 5126, "count": int(arr.shape[0]), "type": typ}
        if minmax:
            flat = arr.reshape(arr.shape[0], -1)
            a["min"] = [float(x) for x in flat.min(0)]
            a["max"] = [float(x) for x in flat.max(0)]
        self.accs.append(a)
        return len(self.accs) - 1


# ---------------------------------------------------------------- maths
def q2m(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def m2q(m):
    t = np.trace(m)
    if t > 0:
        s = math.sqrt(t + 1) * 2
        q = [(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, s / 4]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [s / 4, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s]
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 1] + m[1, 0]) / s, s / 4, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s]
    else:
        s = math.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, s / 4, (m[1, 0] - m[0, 1]) / s]
    q = np.array(q)
    return q / np.linalg.norm(q)


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def rot_between(a, b):
    """Smallest rotation turning direction a onto direction b."""
    a, b = unit(a), unit(b)
    c = float(np.dot(a, b))
    if c > 1 - 1e-9:
        return np.eye(3)
    if c < -1 + 1e-9:
        axis = unit(np.cross(a, [1, 0, 0] if abs(a[0]) < .9 else [0, 1, 0]))
        return rot_axis(axis, math.pi)
    return rot_axis(unit(np.cross(a, b)), math.acos(max(-1, min(1, c))))


def rot_axis(axis, ang):
    x, y, z = axis
    c, s = math.cos(ang), math.sin(ang)
    C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


def slerp_m(a, b, t):
    qa, qb = m2q(a), m2q(b)
    if np.dot(qa, qb) < 0:
        qb = -qb
    q = unit(qa * (1 - t) + qb * t)          # nlerp is plenty for a blend
    return q2m(q)


def body_frame(up, fwd):
    """Rotation taking the rest body axes (right = +X... i.e. X, up = Y, forward = Z) to the new ones."""
    u = unit(up)
    f = unit(fwd - np.dot(fwd, u) * u)
    return np.column_stack([np.cross(u, f), u, f])


# ---------------------------------------------------------------- the rig
class Rig:
    def __init__(self, j, b):
        self.j, self.b = j, b
        N = j["nodes"]
        self.names = [n.get("name", "") for n in N]
        self.idx = {n: i for i, n in enumerate(self.names)}
        self.parent = {}
        for i, n in enumerate(N):
            for c in n.get("children", []):
                self.parent[c] = i
        self.T = [np.array(n.get("translation", [0, 0, 0]), float) for n in N]
        self.R = [q2m(n.get("rotation", [0, 0, 0, 1])) for n in N]
        self.joints = j["skins"][0]["joints"]
        order, seen = [], set()

        def visit(i):
            if i in seen:
                return
            if i in self.parent:
                visit(self.parent[i])
            seen.add(i)
            order.append(i)
        for i in range(len(N)):
            visit(i)
        self.order = order                      # parents before children
        self.restW, self.restP = self.fk({})
        self.rest_low = lowest_point(self, self.restP)

    def fk(self, local):
        W, P = {}, {}
        for i in self.order:
            R = local.get(i, self.R[i])
            if i in self.parent:
                p = self.parent[i]
                W[i] = W[p] @ R
                P[i] = P[p] + W[p] @ self.T[i]
            else:
                W[i], P[i] = R, self.T[i].copy()
        return W, P

    def i(self, name):
        return self.idx[name]

    def clip_locals(self, name, t=0.0):
        """Local rotations of every rotated node at time t of a body clip."""
        j, b = self.j, self.b
        an = next(a for a in j["animations"] if a["name"] == name)
        out = {}
        for ch in an["channels"]:
            if ch["target"]["path"] != "rotation":
                continue
            s = an["samplers"][ch["sampler"]]
            ts = acc_array(j, b, s["input"])[:, 0]
            v = acc_array(j, b, s["output"])
            k = int(np.searchsorted(ts, t, side="right") - 1)
            out[ch["target"]["node"]] = q2m(v[max(0, k)])
        return out


FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")


def grip_pose(rig):
    """Closed hands: the right hand's fingers from the body's sword clip, mirrored onto the left."""
    src = rig.clip_locals("attack_normal", 0.0)
    out = {}
    for i, n in enumerate(rig.names):
        m = re.match(r"RightHand(%s)\d$" % "|".join(FINGERS), n)
        if m and i in src:
            out[i] = src[i]
            li = rig.idx.get(n.replace("Right", "Left"))
            if li is not None:
                q = m2q(src[i])
                out[li] = q2m(np.array([q[0], -q[1], -q[2], q[3]]))   # mirror across the body's middle (X)
    return out


# ---------------------------------------------------------------- 2D -> 3D
LIMBS = {   # 3D upper bone, lower bone, end bone; 2D base, mid, end joint; rig length keys; near side?
    "armR": ("RightArm", "RightForeArm", "RightHand", "shR", "elR", "haR", "ua", "fa", True),
    "armL": ("LeftArm", "LeftForeArm", "LeftHand", "shL", "elL", "haL", "ua", "fa", False),
    "legR": ("RightUpLeg", "RightLeg", "RightFoot", "hpR", "knR", "ftR", "th", "sh", True),
    "legL": ("LeftUpLeg", "LeftLeg", "LeftFoot", "hpL", "knL", "ftL", "th", "sh", False),
}


class Source:
    """One character's 2D data."""

    def __init__(self, name):
        self.name = name
        self.d = json.load(open(os.path.join(CHARS, name, "character.json"), encoding="utf-8"))
        rf = self.d.get("rigforge") or {}
        rig = rf.get("rig") or {}
        ppu = float(self.d["image"].get("px_per_rig_unit") or 1.0)
        A = self.d["anchors"]
        self.A = A

        def lengths(a, b):
            return np.array([math.dist(J[a][f], J[b][f]) for J in A.values() for f in range(len(J[a]))])
        # rig lengths in px (a limb drawn longer than this is a stretch, not depth)
        self.base = {}
        for key, (a, b) in {"ua": ("shR", "elR"), "fa": ("elR", "haR"), "th": ("hpR", "knR"), "sh": ("knR", "ftR")}.items():
            seen = max(np.percentile(lengths(a, b), 90), np.percentile(lengths(a.replace("R", "L"), b.replace("R", "L")), 90))
            self.base[key] = float(rig[key]) * ppu if rig.get(key) else seen
        self.hipW = float(max(lengths("hpL", "hpR").max(), 1e-3)) * 1.15
        self.shW = float(max(lengths("shL", "shR").max(), 1e-3)) * 1.15
        self.has_weapon = float(lengths("haR", "wtip").max()) > 4
        self.bladeL = float(lengths("haR", "wtip").max()) if self.has_weapon else 1.0
        self.has_weapon2 = all("wtip2" in J for J in A.values()) and float(lengths("haL", "wtip2").max()) > 4   # a blade in the far hand too
        self.blade2L = float(lengths("haL", "wtip2").max()) if self.has_weapon2 else 1.0
        idle = A.get("idle") or next(iter(A.values()))
        self.ground = max(max(idle["ftL"][f][1], idle["ftR"][f][1]) for f in range(len(idle["ftL"])))
        self.hip_over_feet = idle["hip"][0][0] - (idle["ftL"][0][0] + idle["ftR"][0][0]) / 2
        self.leg2d = self.base["th"] + self.base["sh"]

    def pt(self, act, joint, f):
        return np.array(self.A[act][joint][f], float)


def v3d(v2, base_len, depth_sign):
    """2D bone vector (px) -> 3D unit direction with the missing length put into depth."""
    inplane = np.array([0.0, -v2[1], v2[0]])
    d2 = float(np.linalg.norm(v2))
    r = min(1.0, d2 / base_len) if base_len > 0 else 1.0
    if d2 < 1e-6:
        return depth_sign * CAM, 0.0
    dep = math.sqrt(max(0.0, 1 - r * r))
    return unit(inplane / d2 * r + depth_sign * dep * CAM), depth_sign * dep


def lowest_point(rig, P):
    """Lowest spot of the feet: toes, and the heel just under each ankle."""
    ys = [P[rig.i(n)][1] for n in ("LeftToeBase", "LeftToe_End", "RightToeBase", "RightToe_End")]
    ys += [P[rig.i(n)][1] - 0.09 for n in ("LeftFoot", "RightFoot")]
    return min(ys)


def solve_frame(rig, src, act, f, base_local):
    P2 = lambda n: src.pt(act, n, f)
    local = dict(base_local)
    yaw_h = math.asin(max(-1, min(1, (P2("hpR")[0] - P2("hpL")[0]) / src.hipW)))
    yaw_c = math.asin(max(-1, min(1, (P2("shR")[0] - P2("shL")[0]) / src.shW)))
    fwd_h = np.array([math.sin(yaw_h), 0, math.cos(yaw_h)])
    fwd_c = np.array([math.sin(yaw_c), 0, math.cos(yaw_c)])
    to3 = lambda v: np.array([0.0, -v[1], v[0]])
    up_low = to3(P2("chest") - P2("hip"))
    up_mid = to3(P2("neck") - P2("chest"))
    up_head = to3(P2("head") - P2("neck"))
    frames = {"Hips": body_frame(up_low, fwd_h), "Spine": body_frame(up_low, unit(fwd_h + fwd_c)),
              "Spine1": body_frame(unit(unit(up_low) + unit(up_mid)), unit(fwd_h + 2 * fwd_c)),
              "Spine2": body_frame(up_mid, fwd_c), "Neck": body_frame(unit(up_mid + up_head), fwd_c),
              "Head": body_frame(up_head, fwd_c)}
    W = {}

    def set_world(name, Wn):
        i = rig.i(name)
        p = rig.parent[i]
        local[i] = W_of(p).T @ Wn

    def W_of(i):
        Wd, _ = rig.fk(local)
        return Wd[i]

    for name in ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Head"):
        set_world(name, frames[name] @ rig.restW[rig.i(name)])
    # hips position: leg-length scale, relative to the idle pose's hip point and the ground line
    k = (np.linalg.norm(rig.restP[rig.i("RightLeg")] - rig.restP[rig.i("RightUpLeg")]) +
         np.linalg.norm(rig.restP[rig.i("RightFoot")] - rig.restP[rig.i("RightLeg")])) / src.leg2d
    hip = P2("hip")
    ankle = rig.restP[rig.i("RightFoot")][1]
    hips_off = rig.restP[rig.i("Hips")][1] - rig.restP[rig.i("RightUpLeg")][1]
    # in place (RIG_SPEC 4: the sim moves the fighter): the hips keep their spot over the feet, the 2D travel goes
    feet_x = (P2("ftL")[0] + P2("ftR")[0]) / 2
    world_hips = np.array([0.0, ankle + (src.ground - hip[1]) * k + hips_off, (hip[0] - feet_x - src.hip_over_feet) * k])
    hi = rig.i("Hips")
    hp = rig.parent[hi]
    Wd, Pd = rig.fk(local)
    hips_T = Wd[hp].T @ (world_hips - Pd[hp])

    def fk_t():
        T0 = rig.T[hi]
        rig.T[hi] = hips_T
        r = rig.fk(local)
        rig.T[hi] = T0
        return r

    for key, (b1, b2, b3, j1, j2, j3, l1, l2, near) in LIMBS.items():
        out = 1.0 if near else -1.0
        d1, e1 = v3d(P2(j2) - P2(j1), src.base[l1], out)
        Wd, Pd = fk_t()
        i1 = rig.i(b1)
        axis = rig.T[rig.i(b2)]
        a = Wd[i1] @ unit(axis)
        set_world(b1, rot_between(a, d1) @ Wd[i1])
        # lower bone: the depth side that brings the end back toward the base line
        L1 = np.linalg.norm(rig.T[rig.i(b2)])
        L2 = np.linalg.norm(rig.T[rig.i(b3)])
        best = None
        for s in ((out,) if e1 == 0 else (1.0, -1.0)):
            d2, e2 = v3d(P2(j3) - P2(j2), src.base[l2], s)
            score = abs(e1 * L1 + e2 * L2)
            if best is None or score < best[0]:
                best = (score, d2)
        Wd, Pd = fk_t()
        i2 = rig.i(b2)
        a = Wd[i2] @ unit(rig.T[rig.i(b3)])
        set_world(b2, rot_between(a, best[1]) @ Wd[i2])
    # feet: flat on the ground (turned with the pelvis), following the shin once lifted
    Wd, Pd = fk_t()
    yaw = body_frame(np.array([0, 1.0, 0]), fwd_h)
    for foot in ("RightFoot", "LeftFoot"):
        i = rig.i(foot)
        flat = yaw @ rig.restW[i]
        follow = Wd[rig.parent[i]] @ rig.R[i]
        h = Pd[i][1] - ankle
        set_world(foot, slerp_m(flat, follow, max(0.0, min(1.0, (h - 0.04) / 0.18))))
    # ground: the lowest foot sits on the floor, plus the 2D air gap (2D legs are often drawn stretched, so the
    # 2D hip height alone floats or sinks the body)
    Wd, Pd = fk_t()
    air2d = max(0.0, src.ground - max(P2("ftL")[1], P2("ftR")[1])) * k
    low = lowest_point(rig, Pd)
    hips_T = hips_T + Wd[hp].T @ np.array([0.0, rig.rest_low + air2d - low, 0.0])
    # weapon hands: each blade points at its 2D weapon tip (near blade outward to the viewer, far one away)
    for on, hand, wb, tip, h2, w2, blen, side in (
            (src.has_weapon, "RightHand", "Weapon_R", "WeaponTip_R", "haR", "wtip", src.bladeL, 1.0),
            (src.has_weapon2, "LeftHand", "Weapon_L", "WeaponTip_L", "haL", "wtip2", src.blade2L, -1.0)):
        if not on or wb not in rig.idx:
            continue
        Wd, Pd = fk_t()
        ih, iw, it = rig.i(hand), rig.i(wb), rig.i(tip)
        blade_local = rig.R[iw] @ unit(rig.T[it])
        d, _ = v3d(P2(w2) - P2(h2), blen, side)
        a = Wd[ih] @ blade_local
        set_world(hand, rot_between(a, d) @ Wd[ih])
    return local, hips_T


def _append(j, b, arr, comp, typ, target=None):
    """Append an accessor (own bufferView) to an in-memory glb; returns (new bin, accessor index)."""
    b = bytearray(b)
    while len(b) % 4:
        b.append(0)
    data = np.ascontiguousarray(arr).tobytes()
    v = {"buffer": 0, "byteOffset": len(b), "byteLength": len(data)}
    if target:
        v["target"] = target
    j["bufferViews"].append(v)
    b += data
    a = {"bufferView": len(j["bufferViews"]) - 1, "componentType": comp, "count": int(arr.shape[0]), "type": typ}
    if typ == "VEC3" and comp == 5126:
        a["min"] = [float(x) for x in arr.min(0)]
        a["max"] = [float(x) for x in arr.max(0)]
    j["accessors"].append(a)
    return bytes(b), len(j["accessors"]) - 1


def add_left_blade(j, b):
    """Weapon_L + WeaponTip_L on the left hand (Weapon_R mirrored across the body's middle) and a copy of the
    blade mesh skinned to it (named blade_L, so V3 tints / hides it like the right blade)."""
    rig = Rig(j, b)
    N = j["nodes"]
    iwr, itr, ilh = rig.i("Weapon_R"), rig.i("WeaponTip_R"), rig.i("LeftHand")
    mir_t = lambda t: [-t[0], t[1], t[2]]
    mir_q = lambda q: [q[0], -q[1], -q[2], q[3]]
    wr, tr = N[iwr], N[itr]
    iwl, itl = len(N), len(N) + 1
    N.append({"name": "Weapon_L", "translation": mir_t(wr.get("translation", [0, 0, 0])),
              "rotation": mir_q(wr.get("rotation", [0, 0, 0, 1])), "children": [itl]})
    N.append({"name": "WeaponTip_L", "translation": mir_t(tr.get("translation", [0, 0, 0])),
              "rotation": mir_q(tr.get("rotation", [0, 0, 0, 1]))})
    N[ilh].setdefault("children", []).append(iwl)
    rig = Rig(j, b)
    W4 = lambda i: np.block([[rig.restW[i], rig.restP[i].reshape(3, 1)], [np.zeros((1, 3)), np.ones((1, 1))]])
    move = W4(iwl) @ np.linalg.inv(W4(iwr))
    skin = j["skins"][0]
    skin["joints"] += [iwl, itl]
    jl = len(skin["joints"]) - 2
    ibm = acc_array(j, b, skin["inverseBindMatrices"]).astype(np.float32)
    extra = np.array([np.linalg.inv(W4(i)).T.reshape(16) for i in (iwl, itl)], np.float32)   # glTF MAT4 = column-major
    b, skin["inverseBindMatrices"] = _append(j, b, np.vstack([ibm, extra]), 5126, "MAT4")
    src_mesh = next(m for m in j["meshes"] if m.get("name") == "blade")
    prim = src_mesh["primitives"][0]
    pos = acc_array(j, b, prim["attributes"]["POSITION"]).astype(float)
    nrm = acc_array(j, b, prim["attributes"]["NORMAL"]).astype(float)
    pos = (move[:3, :3] @ pos.T).T + move[:3, 3]
    nrm = (move[:3, :3] @ nrm.T).T
    n = pos.shape[0]
    b, ap = _append(j, b, pos.astype(np.float32), 5126, "VEC3", 34962)
    b, an = _append(j, b, nrm.astype(np.float32), 5126, "VEC3", 34962)
    joints = np.zeros((n, 4), np.uint16)
    joints[:, 0] = jl
    b, aj = _append(j, b, joints, 5123, "VEC4", 34962)
    wts = np.zeros((n, 4), np.float32)
    wts[:, 0] = 1
    b, aw = _append(j, b, wts, 5126, "VEC4", 34962)
    j["meshes"].append({"name": "blade_L", "primitives": [{"attributes": {"POSITION": ap, "NORMAL": an, "JOINTS_0": aj,
                                                                        "WEIGHTS_0": aw}, "indices": prim["indices"], "material": prim.get("material", 0)}]})
    blade_node = next(nd for nd in N if nd.get("name") == "blade")
    N.append({"name": "blade_L", "mesh": len(j["meshes"]) - 1, "skin": blade_node.get("skin", 0)})
    armature = next(i for i, nd in enumerate(N) if blade_node is not nd and N.index(blade_node) in nd.get("children", []))
    N[armature]["children"].append(len(N) - 1)
    return j, b


def build(name, body=None):
    j, b = read_glb(body or BODY)
    if "Weapon_L" not in [n.get("name") for n in j["nodes"]]:
        j, b = add_left_blade(j, b)          # same skeleton as the shared body (run --body once to add it there)
    src = Source(name)
    rig = Rig(j, b)
    base_local = grip_pose(rig)
    acts = src.d["actions"]
    clips = {}
    for act, spec in acts.items():
        if act not in src.A:
            continue
        n = len(spec["frames"])
        fms = float(spec.get("frame_ms") or 50) / 1000.0
        poses = [solve_frame(rig, src, act, f, base_local) for f in range(n)]
        loop = spec.get("trigger") in ("always", "moving") or act in ("idle", "run")
        poses.append(poses[0] if loop else poses[-1])
        times = [f * fms for f in range(n)] + [n * fms]
        clips[act] = (times, poses)
    if "defend" not in clips and "parry" in clips:   # a block plays the parry pose rather than nothing
        clips["defend"] = clips["parry"]
    return j, b, rig, src, clips


def pack(j, b, meshes=True, keep_anims=True, new_clips=None, rig=None, extras=None):
    """glTF json + bin from the body. meshes=False = skeleton only (no mesh / skin / materials);
    keep_anims = keep the body's own clips; new_clips = {name: (times, poses)} solved on `rig`."""
    out = json.loads(json.dumps(j))
    w = Writer()
    if meshes:
        out_meshes = []
        for m in j["meshes"]:
            m = json.loads(json.dumps(m))
            for p in m["primitives"]:
                for k, ai in list(p["attributes"].items()):
                    p["attributes"][k] = w.copy(j, b, ai, 34962)
                if "indices" in p:
                    p["indices"] = w.copy(j, b, p["indices"], 34963)
                if "targets" in p:
                    p["targets"] = [{k: w.copy(j, b, ai, 34962) for k, ai in t.items()} for t in p["targets"]]
            out_meshes.append(m)
        out["meshes"] = out_meshes
        for sk in out["skins"]:
            if "inverseBindMatrices" in sk:
                sk["inverseBindMatrices"] = w.copy(j, b, sk["inverseBindMatrices"])
    else:
        for k in ("meshes", "skins", "materials", "textures", "images", "samplers"):
            out.pop(k, None)
        for n in out["nodes"]:
            n.pop("mesh", None)
            n.pop("skin", None)
    anims = []
    if keep_anims:
        for a in j["animations"]:
            a = json.loads(json.dumps(a))
            for sm in a["samplers"]:
                sm["input"] = w.copy(j, b, sm["input"])
                sm["output"] = w.copy(j, b, sm["output"])
            anims.append(a)
    if new_clips:
        hi = rig.i("Hips")
        for act, (times, poses) in new_clips.items():
            t_acc = w.floats(np.array(times).reshape(-1, 1), "SCALAR", minmax=True)
            samplers, channels = [], []
            for node in rig.joints:
                qs, prev = [], None
                for local, _ in poses:
                    q = m2q(local.get(node, rig.R[node]))
                    if prev is not None and np.dot(q, prev) < 0:
                        q = -q
                    qs.append(q)
                    prev = q
                samplers.append({"input": t_acc, "output": w.floats(np.array(qs), "VEC4"), "interpolation": "LINEAR"})
                channels.append({"sampler": len(samplers) - 1, "target": {"node": node, "path": "rotation"}})
            samplers.append({"input": t_acc, "output": w.floats(np.array([p[1] for p in poses]), "VEC3"),
                             "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1, "target": {"node": hi, "path": "translation"}})
            anims.append({"name": act, "samplers": samplers, "channels": channels})
    out["animations"] = anims
    out["accessors"], out["bufferViews"] = w.accs, w.views
    while len(w.bin) % 4:
        w.bin.append(0)
    out["buffers"] = [{"byteLength": len(w.bin)}]
    if extras:
        out["scenes"][out.get("scene", 0)].setdefault("extras", {}).update(extras)
    return out, bytes(w.bin)


def save_glb(path, out, bin_):
    js = json.dumps(out, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    with open(path + ".tmp", "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(bin_), 0x004E4942) + bin_)
    os.replace(path + ".tmp", path)
    return total


def write(name, j, b, rig, src, clips, body=None):
    """characters/<name>/<name>.glb = skeleton + the character's own clips only (no mesh). V3 and Rig Forge 3D
    put them on the shared body; extras pb_body says which body and which blades the character holds."""
    body_name = os.path.splitext(os.path.basename(body or BODY))[0]
    meta = {"pb_body": {"body": body_name, "weapons": {"R": bool(src.has_weapon), "L": bool(src.has_weapon2)},
                        "source": "v3/tools/retarget2d.py from characters/%s/character.json" % name}}
    out, bin_ = pack(j, b, meshes=False, keep_anims=False, new_clips=clips, rig=rig, extras=meta)
    path = os.path.join(CHARS, name, name + ".glb")
    total = save_glb(path, out, bin_)
    print("%s: %s (%d KB) - clips: %s; weapon: %s" % (name, os.path.relpath(path, ROOT), total // 1024, ", ".join(sorted(clips)),
                                                     ("two blades" if src.has_weapon2 else "yes") if src.has_weapon else "none"))
    return path


def update_body(body=None):
    """Give the shared body the left blade (Weapon_L / WeaponTip_L + blade_L, hidden unless a character holds one)."""
    path = body or BODY
    j, b = read_glb(path)
    if "Weapon_L" in [n.get("name") for n in j["nodes"]]:
        print("body: %s already has the left blade" % os.path.relpath(path, ROOT))
        return
    j, b = add_left_blade(j, b)
    total = save_glb(path, *pack(j, b))
    print("body: %s + left blade (%d KB)" % (os.path.relpath(path, ROOT), total // 1024))


ALL = ["puck", "ronin_copy", "hooded_blades", "Sueko", "new_fighter", "pewpew", "puff", "rapid", "sniper",
       "swordsman_rig", "sync", "thear", "thear_copy", "tough"]


def main(argv):
    body = None
    if "--body" in argv:                      # --body PATH: solve on another body (the final model, same RIG_SPEC rig)
        k = argv.index("--body")
        body = os.path.abspath(argv[k + 1])
        argv = argv[:k] + argv[k + 2:]
    update_body(body)
    names = argv or [n for n in ALL if os.path.exists(os.path.join(CHARS, n, "character.json"))]
    for n in names:
        write(n, *build(n, body), body=body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
