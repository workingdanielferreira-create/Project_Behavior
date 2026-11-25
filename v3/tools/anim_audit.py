"""Skeleton / physics audit of V3 clips (v3/RIG_SPEC.md rig), measured against the shared body's motion capture.

    python v3/tools/anim_audit.py hooded_blades                 audit characters/hooded_blades/hooded_blades.glb
    python v3/tools/anim_audit.py path/to/file.glb [--json out.json] [--clips a,b]

Every key of every clip is solved on the shared body (characters/ual_swordsman/ual_swordsman.glb) and checked for:
knees / elbows bending backward or sideways off their hinge, limb / wrist twist and bend past the range the mocap
clips use, feet through the floor, legs passing through each other, blades / hands through the body, the centre of
mass outside the feet while standing, planted feet sliding, flips (a limb turning > 120 deg between two 60 fps
frames while its hand / foot moves < 12 cm) and very fast
turns (> 60 deg, info: an anime snap can be that fast).
Ranges come from the body's own mocap clips, so the numbers say "further than a real person moved", not a medical
limit. Exit code 1 when a clip has a hard fault (backward / sideways joint, flip, blade through the body).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import retarget2d as r  # noqa: E402

HINGES = {"RightLeg": "knee R", "LeftLeg": "knee L", "RightForeArm": "elbow R", "LeftForeArm": "elbow L"}
TWISTERS = {"RightForeArm": "forearm R", "LeftForeArm": "forearm L", "RightArm": "upper arm R", "LeftArm": "upper arm L",
            "RightUpLeg": "thigh R", "LeftUpLeg": "thigh L", "RightLeg": "shin R", "LeftLeg": "shin L"}
WRISTS = {"RightHand": "wrist R", "LeftHand": "wrist L"}
SNAP_BONES = ("RightArm", "RightForeArm", "RightHand", "LeftArm", "LeftForeArm", "LeftHand", "RightUpLeg", "LeftUpLeg",
              "RightLeg", "LeftLeg", "Hips", "Spine2", "Head")
MASS = [("Hips", "Spine", .11), ("Spine", "Spine2", .20), ("Spine2", "Neck", .19), ("Neck", "HeadTop_End", .08),
        ("RightUpLeg", "RightLeg", .10), ("LeftUpLeg", "LeftLeg", .10), ("RightLeg", "RightFoot", .047),
        ("LeftLeg", "LeftFoot", .047), ("RightFoot", "RightToe_End", .015), ("LeftFoot", "LeftToe_End", .015),
        ("RightArm", "RightForeArm", .028), ("LeftArm", "LeftForeArm", .028), ("RightForeArm", "RightHand", .016),
        ("LeftForeArm", "LeftHand", .016)]
END_OF = {b: (("Right" if b.startswith("Right") else "Left") + ("Hand" if "Arm" in b or "Hand" in b else "Foot"))
          for b in SNAP_BONES if b.startswith(("Right", "Left"))}
HARD = ("knee/elbow bending backward", "knee/elbow bending sideways", "flip (>120 deg in 1/60 s)", "blade through own body")


def axis_angle(R):
    q = r.m2q(R)
    if q[3] < 0:
        q = -q
    s = np.linalg.norm(q[:3])
    return q[:3] / s * 2 * math.atan2(s, q[3]) if s > 1e-9 else np.zeros(3)


def swing_twist(D, axis):
    q = r.m2q(D)
    if q[3] < 0:
        q = -q
    p = np.dot(q[:3], axis) * axis
    tw = r.unit(np.array([*p, q[3]]))
    twist = 2 * math.atan2(np.dot(tw[:3], axis), tw[3])
    swing = np.linalg.norm(axis_angle(r.q2m(q) @ r.q2m(tw).T))
    return math.degrees(twist), math.degrees(swing)


def segdist(p1, q1, p2, q2):
    best = 1e9
    d2 = q2 - p2
    for a in np.linspace(0, 1, 9):
        x = p1 + (q1 - p1) * a
        t = np.clip(np.dot(x - p2, d2) / max(np.dot(d2, d2), 1e-12), 0, 1)
        best = min(best, np.linalg.norm(x - (p2 + d2 * t)))
    return best


def hull_out(pt, pts):
    """Distance of 2D point pt outside the convex hull of pts (<= 0 = inside)."""
    pts = sorted(set(map(tuple, np.round(pts, 4))))
    if len(pts) < 3:
        return 9.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(hi) >= 2 and cross(hi[-2], hi[-1], p) <= 0:
            hi.pop()
        hi.append(p)
    h = lo[:-1] + hi[:-1]
    inside = all(cross(h[k], h[(k + 1) % len(h)], pt) >= 0 for k in range(len(h)))
    z = lambda p: np.array([p[0], p[1], 0.0])
    d = min(segdist(z(h[k]), z(h[(k + 1) % len(h)]), z(pt), z(pt)) for k in range(len(h)))
    return -d if inside else d


class Auditor:
    def __init__(self, body_path=None):
        self.J, self.B = r.read_glb(body_path or r.BODY)
        if "Weapon_L" not in [n.get("name") for n in self.J["nodes"]]:
            self.J, self.B = r.add_left_blade(self.J, self.B)
        self.rig = r.Rig(self.J, self.B)
        self.HI = self.rig.i("Hips")
        self.ground = self.rig.rest_low
        self.axis = {b: r.unit(self.rig.T[self._child(b)]) for b in set(HINGES) | set(TWISTERS) | set(WRISTS)}
        self._envelope()

    def _child(self, bone):
        i = self.rig.i(bone)
        return next(c for c in self.J["nodes"][i].get("children", []) if self.J["nodes"][c].get("name"))

    def tracks(self, j, b, an):
        out = {}
        for ch in an["channels"]:
            s = an["samplers"][ch["sampler"]]
            out[(ch["target"]["node"], ch["target"]["path"])] = (r.acc_array(j, b, s["input"])[:, 0].astype(float),
                                                                 r.acc_array(j, b, s["output"]).astype(float))
        return out

    def sample(self, tr, t, eases=None):
        """Pose at time t, tweened like V3 (keyreduce: ease INTO each key, slerp / lerp)."""
        import keyreduce
        local, hipsT = {}, self.rig.T[self.HI].copy()
        for (node, path), (ts, v) in tr.items():
            k = int(np.clip(np.searchsorted(ts, t, side="right") - 1, 0, len(ts) - 1))
            x = v[k]
            if k < len(ts) - 1 and ts[k + 1] > ts[k]:
                a = min(max((t - ts[k]) / (ts[k + 1] - ts[k]), 0), 1)
                if isinstance(eases, dict):
                    a = keyreduce.seg_u(eases, self.names.get(node, ""), path, ts, k, t)
                elif eases and len(eases) == len(ts):
                    a = keyreduce.ease(eases[k + 1], a)
                x1 = v[k + 1]
                if path == "rotation":
                    x = keyreduce.slerp(x, x1, a)
                else:
                    x = x * (1 - a) + x1 * a
            if path == "rotation":
                local[node] = r.q2m(x)
            elif path == "translation" and node == self.HI:
                hipsT = np.array(x)
        return local, hipsT

    def fk(self, local, hipsT):
        T0 = self.rig.T[self.HI]
        self.rig.T[self.HI] = hipsT
        W, P = self.rig.fk(local)
        self.rig.T[self.HI] = T0
        return W, P

    def delta(self, local, bone):
        i = self.rig.i(bone)
        return self.rig.R[i].T @ local.get(i, self.rig.R[i])

    @staticmethod
    def swing(D, axis):
        """axis * angle of D's swing part (D = swing @ twist about `axis`)."""
        q = r.m2q(D)
        if q[3] < 0:
            q = -q
        p = np.dot(q[:3], axis) * axis
        tw = r.unit(np.array([*p, q[3]]))
        return axis_angle(r.q2m(q) @ r.q2m(tw).T)

    def _envelope(self):
        bones = set(HINGES) | set(TWISTERS) | set(WRISTS)
        env = {b: [] for b in bones}
        pk_all = ((self.J.get("scenes") or [{}])[0].get("extras") or {}).get("pb_keys") or {}
        for an in self.J["animations"]:
            tr = self.tracks(self.J, self.B, an)
            end = max(ts[-1] for ts, _ in tr.values())
            for t in np.arange(0, end + 1e-6, 1 / 30):
                self.names = {i: nd.get("name", "") for i, nd in enumerate(self.J["nodes"])}
                local, _ = self.sample(tr, t, pk_all.get(an["name"]) or {})
                for b in bones:
                    env[b].append(self.delta(local, b))
        self.hinge, self.flex = {}, {}
        for b in HINGES:
            V = np.array([self.swing(D, self.axis[b]) for D in env[b]])
            big = V[np.linalg.norm(V, axis=1) > math.radians(15)]
            ax = np.linalg.svd(big, full_matrices=False)[2][0]
            if np.mean(big @ ax) < 0:
                ax = -ax
            self.hinge[b] = ax
            f = [math.degrees(np.dot(v, ax)) for v in V]
            self.flex[b] = (float(np.percentile(f, 1)), float(np.percentile(f, 99)))
            # how far off its hinge a bent joint goes in the mocap (bends > 25 deg only; a straight joint has no plane)
            dev = [math.degrees(math.acos(min(1, abs(np.dot(v, ax)) / np.linalg.norm(v)))) for v in big
                   if np.linalg.norm(v) > math.radians(25)]
            self.devlim = getattr(self, "devlim", {})
            self.devlim[b] = float(np.percentile(dev, 99)) + 10
        self.lim = {}
        for b in bones:
            st = [swing_twist(D, self.axis[b]) for D in env[b]]
            self.lim[b] = (max(abs(x[0]) for x in st), max(x[1] for x in st))

    def clip(self, tr, eases=None):
        rig, P_ = self.rig, (lambda P, n: P[self.rig.i(n)])
        end = max(ts[-1] for ts, _ in tr.values())
        times = list(np.arange(0, end + 1e-6, 1 / 60))
        res = {k: [] for k in ("knee/elbow bending backward", "knee/elbow bending sideways", "limb twisted past range",
                               "wrist past range", "feet through the floor", "legs through each other",
                               "blade through own body", "hand inside torso", "off balance", "planted foot sliding",
                               "flip (>120 deg in 1/60 s)", "very fast (>60 deg in 1/60 s)")}
        prev = None
        for f, t in enumerate(times):
            local, hT = self.sample(tr, t, eases)
            W, P = self.fk(local, hT)
            for b, lab in HINGES.items():
                v = self.swing(self.delta(local, b), self.axis[b])     # forearm / shin twist about itself is allowed
                flex = math.degrees(np.dot(v, self.hinge[b]))
                if flex < self.flex[b][0] - 10:
                    res["knee/elbow bending backward"].append((f, lab, round(flex)))
                n = np.linalg.norm(v)
                if n > math.radians(25):
                    dev = math.degrees(math.acos(min(1, abs(np.dot(v, self.hinge[b])) / n)))
                    if dev > self.devlim[b]:
                        res["knee/elbow bending sideways"].append((f, lab, round(dev)))
            for b, lab in TWISTERS.items():
                tw, _ = swing_twist(self.delta(local, b), self.axis[b])
                if abs(tw) > self.lim[b][0] + 15:
                    res["limb twisted past range"].append((f, lab, round(tw)))
            for b, lab in WRISTS.items():
                tw, sw = swing_twist(self.delta(local, b), self.axis[b])
                if sw > self.lim[b][1] + 15 or abs(tw) > self.lim[b][0] + 15:
                    res["wrist past range"].append((f, lab, round(sw), round(tw)))
            low = r.lowest_point(rig, P)
            if low < self.ground - 0.03:
                res["feet through the floor"].append((f, round((self.ground - low) * 100, 1)))
            dl = min(segdist(P_(P, "RightLeg"), P_(P, "RightFoot"), P_(P, "LeftLeg"), P_(P, "LeftFoot")) / .07,
                     segdist(P_(P, "RightUpLeg"), P_(P, "RightLeg"), P_(P, "LeftUpLeg"), P_(P, "LeftLeg")) / .09)
            if dl < 1:
                res["legs through each other"].append((f,))
            parts = {"torso": (P_(P, "Spine"), P_(P, "Neck"), .11), "head": (P_(P, "Head"), P_(P, "HeadTop_End"), .10),
                     "thigh R": (P_(P, "RightUpLeg"), P_(P, "RightLeg"), .08), "thigh L": (P_(P, "LeftUpLeg"), P_(P, "LeftLeg"), .08)}
            for wb, tp, lab in (("Weapon_R", "WeaponTip_R", "blade R"), ("Weapon_L", "WeaponTip_L", "blade L")):
                if wb not in rig.idx or not self.held.get(wb[-1], True):     # an unarmed hand's hidden blade
                    continue
                a, b_ = P_(P, wb), P_(P, tp)
                a = a + (b_ - a) * 0.25
                for part, (p, q, rad) in parts.items():   # radii = body surface, the grip end skipped
                    if segdist(a, b_, p, q) < rad:
                        res["blade through own body"].append((f, lab, part))
            for hand, lab in (("RightHand", "hand R"), ("LeftHand", "hand L")):
                if segdist(P_(P, hand), P_(P, hand), P_(P, "Spine"), P_(P, "Spine2")) < 0.10:
                    res["hand inside torso"].append((f, lab))
            com = sum(m * (P_(P, a) + P_(P, b_)) / 2 for a, b_, m in MASS) / sum(m for *_, m in MASS)
            sup = []
            for s in ("Right", "Left"):
                pts = [P_(P, s + "Foot") - np.array([0, .09, 0]), P_(P, s + "ToeBase"), P_(P, s + "Toe_End")]
                if min(p[1] for p in pts) < self.ground + 0.04:
                    sup += [(p[0], p[2]) for p in pts] + [(P_(P, s + "Foot")[0] + d, P_(P, s + "Foot")[2] - .05) for d in (-.04, .04)]
            if sup and hull_out((com[0], com[2]), np.array(sup)) > 0.06:
                res["off balance"].append((f, round(hull_out((com[0], com[2]), np.array(sup)) * 100)))
            if prev is not None:
                pl, pP = prev
                for s in ("Right", "Left"):
                    a0, a1 = pP[rig.i(s + "Foot")], P_(P, s + "Foot")
                    if a0[1] < self.ground + 0.13 and a1[1] < self.ground + 0.13 and math.hypot(a1[0] - a0[0], a1[2] - a0[2]) > 0.05:
                        res["planted foot sliding"].append((f, s[0], round(100 * math.hypot(a1[0] - a0[0], a1[2] - a0[2]))))
                for b in SNAP_BONES:
                    i = rig.i(b)
                    ang = math.degrees(np.linalg.norm(axis_angle(pl.get(i, rig.R[i]).T @ local.get(i, rig.R[i]))))
                    # a flip = the limb spins round while what it carries barely moves (an IK / twist solution jump);
                    # a big turn that also carries the hand / foot far is a fast move, not a flip
                    end = END_OF.get(b)
                    moved = np.linalg.norm(P[rig.i(end)] - pP[rig.i(end)]) if end else 0.0
                    if ang > 120 and moved < 0.12:
                        res["flip (>120 deg in 1/60 s)"].append((f, b, round(ang)))
                    elif ang > 60:
                        res["very fast (>60 deg in 1/60 s)"].append((f, b, round(ang)))
            prev = (local, P)
        return len(times), res

    def run(self, j, b, only=None, held=None):
        """held = {"R": bool, "L": bool}: which hands hold a blade (pb_body.weapons; unarmed = not checked)."""
        self.held = held if held is not None else held_from(j)
        out = {}
        # Tracks are matched to the shared body's bones BY NAME: a file re-saved by Rig Forge 3D can store its nodes
        # in another order (hooded_blades 2026-11-24: 45 of 75 shifted), and an index match then audits the wrong bones.
        body_idx = {nd.get("name"): i for i, nd in enumerate(self.J["nodes"]) if nd.get("name")}
        names = [nd.get("name", "") for nd in j["nodes"]]
        self.names = {i: nd.get("name", "") for i, nd in enumerate(self.J["nodes"])}
        for an in j["animations"]:
            if only and an["name"] not in only:
                continue
            pk = (((j.get("scenes") or [{}])[0].get("extras") or {}).get("pb_keys") or {}).get(an["name"]) or {}
            tr = {(body_idx[names[node]], path): v for (node, path), v in self.tracks(j, b, an).items()
                  if names[node] in body_idx}
            out[an["name"]] = self.clip(tr, pk)
        return out


def held_from(j):
    """Which hands hold a blade, from a character file's pb_body.weapons (missing = both checked)."""
    w = ((((j.get("scenes") or [{}])[0].get("extras") or {}).get("pb_body") or {}).get("weapons")) or {}
    return {s: bool(w.get(s, True)) for s in ("R", "L")}


def print_report(rep):
    hard = 0
    tot = {}
    for clip, (n, res) in rep.items():
        bad = [(k, len(set(x[0] for x in v))) for k, v in res.items() if v]
        print("== %-18s %3d frames  %s" % (clip, n, "clean" if not bad else ""))
        for k, c in bad:
            print("     %-30s %3d/%d frames%s" % (k, c, n, "  <- HARD" if k in HARD else ""))
            hard += k in HARD
        for k, v in res.items():
            a = tot.setdefault(k, [0, 0])
            a[0] += len(set(x[0] for x in v))
            a[1] += n
    print("-- all clips:")
    for k, (a, n) in tot.items():
        print("     %-30s %4d/%d frames (%.0f%%)" % (k, a, n, 100 * a / max(n, 1)))
    return 1 if hard else 0


def report_from(j, b, body=None, only=None, held=None):
    return print_report(Auditor().run(j, b, only, held))


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    p = argv[0]
    if not p.endswith(".glb"):
        p = os.path.join(r.CHARS, p, p + ".glb")
    only = None
    if "--clips" in argv:
        only = set(argv[argv.index("--clips") + 1].split(","))
    j, b = r.read_glb(p)
    rep = Auditor().run(j, b, only)
    if "--json" in argv:
        json.dump({c: {"frames": n, **res} for c, (n, res) in rep.items()}, open(argv[argv.index("--json") + 1], "w"), indent=1)
    return print_report(rep)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
