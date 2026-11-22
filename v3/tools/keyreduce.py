"""Key poses + tweening for V3 clips (Daniel 2026-11-22: "work through key frames and let the tweening fill in the
in-betweens"; every clip of every character).

A clip is stored as KEY POSES only: its channels hold just the key times (on the 60 fps grid) and scene extras
`pb_keys` {clip: {"e": [ease per key]}} say how the motion eases INTO each key. V3 (js/keytween.js) and Rig Forge 3D
fill in the frames between keys; Rig Forge 3D edits the keys themselves.

Tweening (identical in Python, keytween.js and Rig Forge 3D): between key i and key i+1, u = ease(e[i+1], s) with s the
0..1 position in that segment; every bone rotation = slerp(q_i, q_i+1, u) (shortest way), the hips position = lerp.
Eases: linear, smooth, inout, in, out, snap, hold, back.

`reduce()` turns a dense clip (one pose per frame) into the fewest key poses whose tweening stays within
TOL_BODY (hands, feet, elbows, knees, head, hips) / TOL_TIP (blade tips) of the original, picking the best ease per
segment; `must` frames (authored keys, holds) are always kept.

    python v3/tools/keyreduce.py --body      reduce the shared body's own clips (hit reactions, K.O., dodges ...)
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retarget2d as r  # noqa: E402

FPS = 60
EASES = ("linear", "smooth", "inout", "in", "out", "snap", "hold", "back")
FIT_EASES = ("linear", "smooth", "inout", "in", "out", "snap")       # the reducer chooses among these
TOL_BODY = 0.03          # m
TOL_TIP = 0.07           # m (a blade tip 1 m from the hand: ~4 deg)
TRACK = ("RightHand", "LeftHand", "RightFoot", "LeftFoot", "RightForeArm", "LeftForeArm", "RightLeg", "LeftLeg",
         "Head", "Hips", "RightToe_End", "LeftToe_End")
TIPS = ("WeaponTip_R", "WeaponTip_L")


def ease(kind, u):
    u = min(max(float(u), 0.0), 1.0)
    if kind == "linear":
        return u
    if kind == "smooth":
        return u * u * (3 - 2 * u)
    if kind == "in":
        return u * u * u
    if kind == "out":
        return 1 - (1 - u) ** 3
    if kind == "snap":
        return 1 - (1 - u) ** 5
    if kind == "hold":
        return 1.0 if u >= 1 else 0.0
    if kind == "back":
        c1, w = 1.70158, u - 1
        return 1 + (c1 + 1) * w ** 3 + c1 * w * w
    return 4 * u ** 3 if u < .5 else 1 - (-2 * u + 2) ** 3 / 2          # inout


def slerp(a, b, u):
    if np.dot(a, b) < 0:
        b = -b
    d = float(np.clip(np.dot(a, b), -1, 1))
    if d > 0.9995:
        q = a + (b - a) * u
        return q / np.linalg.norm(q)
    th = math.acos(d)
    s = math.sin(th)
    return (math.sin((1 - u) * th) / s) * a + (math.sin(u * th) / s) * b


class Clip:
    """A dense clip as arrays: Q[node] = (n, 4) quaternions, H = (n, 3) hips translation, at times t (n,)."""

    def __init__(self, rig, times, poses):
        self.rig = rig
        self.t = np.array(times, float)
        self.nodes = list(rig.joints)
        self.Q = {}
        for node in self.nodes:
            qs, prev = [], None
            for local, _ in poses:
                q = r.m2q(local.get(node, rig.R[node]))
                if prev is not None and np.dot(q, prev) < 0:
                    q = -q
                qs.append(q)
                prev = q
            self.Q[node] = np.array(qs)
        self.H = np.array([p[1] for p in poses], float)

    def pose_at(self, k, idx, eases, f):
        """The tweened pose at frame f from key frames idx (sorted) and eases (per key)."""
        j = int(np.searchsorted(idx, f, side="right") - 1)
        j = min(max(j, 0), len(idx) - 1)
        if idx[j] == f or j == len(idx) - 1:
            return self.pose(idx[j])
        a, b = idx[j], idx[j + 1]
        u = ease(eases[j + 1], (f - a) / (b - a))
        local = {n: r.q2m(slerp(self.Q[n][a], self.Q[n][b], u)) for n in self.nodes}
        return local, self.H[a] * (1 - u) + self.H[b] * u

    def pose(self, f):
        return {n: r.q2m(self.Q[n][f]) for n in self.nodes}, self.H[f]


def _points(rig, pose):
    hi = rig.i("Hips")
    T0 = rig.T[hi]
    rig.T[hi] = pose[1]
    W, P = rig.fk(pose[0])
    rig.T[hi] = T0
    body = np.array([P[rig.i(n)] for n in TRACK])
    tips = np.array([P[rig.i(n)] for n in TIPS if n in rig.idx]) if any(n in rig.idx for n in TIPS) else np.zeros((0, 3))
    return body, tips


def reduce(rig, times, poses, must=(), tol_body=TOL_BODY, tol_tip=TOL_TIP, tips=True, max_keys=None):
    """Dense (times, poses) at 1/FPS -> (key times, key poses, eases). `must` = frame indices always kept;
    `max_keys` = stop adding keys at this count (the worst-fitting frame is always added first)."""
    n = len(times)
    if n <= 2:
        return list(times), list(poses), ["linear"] * n
    clip = Clip(rig, times, poses)
    ref = [_points(rig, p) for p in poses]
    keys = sorted(set([0, n - 1] + [int(m) for m in must if 0 <= m < n]))

    def seg_fit(a, b):
        """best ease for segment a..b and its worst frame (error ratio vs tolerance)."""
        best = None
        for e in FIT_EASES:
            worst, wf = 0.0, None
            for f in range(a + 1, b):
                u = ease(e, (f - a) / (b - a))
                local = {nd: r.q2m(slerp(clip.Q[nd][a], clip.Q[nd][b], u)) for nd in clip.nodes}
                body, tp = _points(rig, (local, clip.H[a] * (1 - u) + clip.H[b] * u))
                rb, rt = ref[f]
                err = float(np.max(np.linalg.norm(body - rb, axis=1))) / tol_body
                if tips and len(tp):
                    err = max(err, float(np.max(np.linalg.norm(tp - rt, axis=1))) / tol_tip)
                if err > worst:
                    worst, wf = err, f
                if best is not None and worst >= best[1]:
                    break                                      # already worse than the best ease
            if best is None or worst < best[1]:
                best = (e, worst, wf)
        return best

    fits = {}
    while True:
        worst = None
        for a, b in zip(keys, keys[1:]):
            if (a, b) not in fits:
                fits[(a, b)] = seg_fit(a, b) if b - a > 1 else ("linear", 0.0, None)
            e, err, wf = fits[(a, b)]
            if err > 1.0 and (worst is None or err > worst[0]):
                worst = (err, wf)
        if worst is None or (max_keys and len(keys) >= max_keys):
            break
        keys = sorted(set(keys + [worst[1]]))
    eases = ["linear"] + [fits[(a, b)][0] for a, b in zip(keys, keys[1:])]
    return [times[k] for k in keys], [poses[k] for k in keys], eases


def resample(rig, times, poses, eases=None, fps=FPS):
    """Keyed (times, poses[, eases]) -> dense at fps (tweened the same way V3 tweens)."""
    clip = Clip(rig, times, poses)
    eases = eases or ["linear"] * len(times)
    t = np.array(times, float)
    out_t = [min(t[-1], f / fps) for f in range(int(round(t[-1] * fps)) + 1)]
    out = []
    for x in out_t:
        j = int(np.searchsorted(t, x, side="right") - 1)
        j = min(max(j, 0), len(t) - 1)
        if j == len(t) - 1 or t[j + 1] <= t[j]:
            out.append(clip.pose(j))
            continue
        u = ease(eases[j + 1], (x - t[j]) / (t[j + 1] - t[j]))
        local = {nd: r.q2m(slerp(clip.Q[nd][j], clip.Q[nd][j + 1], u)) for nd in clip.nodes}
        out.append((local, clip.H[j] * (1 - u) + clip.H[j + 1] * u))
    return out_t, out


def snap_must(times, keep_times):
    """Indices of the dense frames nearest to the given times."""
    t = np.array(times, float)
    return sorted(set(int(np.argmin(np.abs(t - k))) for k in keep_times))


def seg_u(info, node_name, path, ts, k, x):
    """0..1 blend of channel segment k -> k+1 at time x: hold frames, then the in-between steps, then the ease (all
    stored for the key the segment runs INTO: info b / s / h [track][k+1], or the clip's shared e)."""
    tn = node_name + (".quaternion" if path == "rotation" else ".position" if path == "translation" else "." + path)
    n = len(ts)
    t0, t1 = ts[k], ts[k + 1]
    hold = ((info.get("h") or {}).get(tn) or [0] * n)[k + 1] if len((info.get("h") or {}).get(tn) or []) == n else 0
    steps = ((info.get("s") or {}).get(tn) or [0] * n)[k + 1] if len((info.get("s") or {}).get(tn) or []) == n else 0
    span = t1 - t0
    h = min(max(0.0, hold / FPS), max(0.0, span - 1.0 / FPS))
    s = 0.0 if x - t0 < h else (x - t0 - h) / max(1e-9, span - h)
    s = min(max(s, 0.0), 1.0)
    if steps and s < 1:
        s = math.floor(s * (steps + 1)) / (steps + 1)
    el = track_eases(info, node_name, path, n)
    return ease(el[k + 1], s) if el else s


def track_eases(info, node_name, path, n):
    """The eases of one channel: per track (Rig Forge 3D saves, info["b"]["Bone.quaternion"]) else the clip's shared list."""
    tn = node_name + (".quaternion" if path == "rotation" else ".position" if path == "translation" else "." + path)
    el = (info.get("b") or {}).get(tn)
    if el and len(el) == n:
        return el
    el = info.get("e")
    return el if el and len(el) == n else None


def clip_from_glb(rig, j, b, an):
    """A glb animation (any key times) -> dense 60 fps (times, poses), reading pb_keys eases if present."""
    hi = rig.i("Hips")
    tr = {}
    for ch in an["channels"]:
        s = an["samplers"][ch["sampler"]]
        tr[(ch["target"]["node"], ch["target"]["path"])] = (r.acc_array(j, b, s["input"])[:, 0].astype(float),
                                                             r.acc_array(j, b, s["output"]).astype(float))
    info = (((j.get("scenes") or [{}])[0].get("extras") or {}).get("pb_keys") or {}).get(an["name"]) or {}
    end = max(ts[-1] for ts, _ in tr.values())
    times = [min(end, f / FPS) for f in range(int(round(end * FPS)) + 1)]
    poses = []
    for x in times:
        local, hT = {}, rig.T[hi].copy()
        for (node, path), (ts, v) in tr.items():
            k = int(np.clip(np.searchsorted(ts, x, side="right") - 1, 0, len(ts) - 1))
            val = v[k]
            if k < len(ts) - 1 and ts[k + 1] > ts[k]:
                u = seg_u(info, j["nodes"][node].get("name", ""), path, ts, k, x)
                val = slerp(v[k], v[k + 1], u) if path == "rotation" else v[k] * (1 - u) + v[k + 1] * u
            if path == "rotation":
                local[node] = r.q2m(val)
            elif path == "translation" and node == hi:
                hT = np.array(val)
        poses.append((local, hT))
    return times, poses


def reduce_body(path=None):
    """The shared body's own clips (mocap) -> key poses + eases, in place."""
    path = path or r.BODY
    j, b = r.read_glb(path)
    rig = r.Rig(j, b)
    clips = {}
    for an in j["animations"]:
        times, poses = clip_from_glb(rig, j, b, an)
        clips[an["name"]] = reduce(rig, times, poses)
        print("  %-18s %4d frames -> %3d keys" % (an["name"], len(times), len(clips[an["name"]][0])))
    out, bin_ = r.pack(j, b, meshes=True, keep_anims=False, new_clips=clips, rig=rig)
    total = r.save_glb(path, out, bin_)
    print("body: %s (%d KB), clips as key poses" % (os.path.relpath(path, r.ROOT), total // 1024))


if __name__ == "__main__":
    if "--body" in sys.argv:
        reduce_body()
    else:
        print(__doc__)
