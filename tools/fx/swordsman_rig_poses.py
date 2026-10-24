#!/usr/bin/env python3
"""3D pose generator for fx_packages/swordsman_rig (filled style).

The fighter lives in a 3D world seen from the side, so key poses are built
as a real 3D body and then drawn flat:

  world: x forward (the way he faces), y up, z toward the camera; his right
  side (sword hand, near side) is +z.  Ground is y = 0.

Each key pose gives the pelvis position and turn, a two-part spine (lean,
curl, chest twist against the hips), head pitch, the sword grip point and
blade direction in 3D, and each foot's toe position and heel lift.  Two-bone
IK with pole points places elbows and knees at fixed bone lengths.  The
camera looks from the near side, turned a little toward his front (3/4) and
tilted down, so twist, foreshortening and ground depth all show.

Drawing: body groups (far arm, far leg, torso + head, near leg, near arm)
and the blade's pieces are depth-sorted and drawn far to near; each bone's
thickness and tone follow its depth.

Every frame is checked before anything is written: IK reach, joint range
of motion (elbow, knee, wrist, chest twist), knees bending forward, elbows
not winging up, the thumb-side sword grip, and feet above the ground.

usage: swordsman_rig_poses.py <action> [--preview out.png]
Rewrites fx_packages/swordsman_rig/<action>_NN.png, the action's entry in
character.json (frames, frame_ms, duration_ms, anchors) and the action's
timing and anchors in swordsman_rig.fxkit.json.
"""
import json, math, os, sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG = os.path.join(ROOT, "fx_packages", "swordsman_rig")

# Canvas: same size and origin as the rest of the package.
W, H = 608, 596
ORIGIN_X, GROUND_Y = 304.0, 458.0
PPU = 1.7                 # image px per body unit
SS = 4                    # supersampling

# Camera: side view from the near (+z) side, turned toward his front and
# tilted down.
YAW, PITCH = 20.0, 10.0

# Body (units).  About 6.6 heads tall; thigh a little longer than shin.
UA, FA, TH, SH = 34.0, 36.0, 44.0, 41.0
LOW_SPINE, UP_SPINE = 32.0, 26.0
HEAD_R = 13.0
SHOULDER_DROP, SHOULDER_HALF, HIP_HALF = 8.0, 17.0, 8.0
FOOT, ANKLE_H = 10.0, 3.0
FIST_GAP = 9.0                      # far hand sits one fist down the handle
GRIP_BACK, BLADE_LEN, BLADE_W = 14.0, 70.0, 2.4

BODY = (0xE8, 0x23, 0x1A)                       # palette.body
SMEAR = (0xFF, 0x7A, 0x5C)                      # palette.accent
EDGE = (12, 14, 18)
D = math.pi / 180.0

# Range-of-motion limits (degrees) — overlap of published tables.
ELBOW_MAX, KNEE_MAX, TWIST_MAX = 145.0, 140.0, 35.0
GRIP_MIN, GRIP_MAX = 15.0, 125.0    # forearm -> blade angle, thumb side
BLADE_MIN_SCREEN = 0.6              # blade keeps >= 60 % of its length on screen


# ------------------------------------------------------------- vectors
def add(*v): return tuple(sum(c) for c in zip(*v))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def mul(a, s): return tuple(x * s for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))
def unit(a):
    n = norm(a) or 1.0
    return mul(a, 1.0 / n)
def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def angle(a, b):
    return math.acos(max(-1.0, min(1.0, dot(unit(a), unit(b))))) / D


UP = (0.0, 1.0, 0.0)


def facing(yaw):
    """Forward and right vectors for a body part turned `yaw` degrees
    (positive = its front turns toward the camera)."""
    f = (math.cos(yaw * D), 0.0, math.sin(yaw * D))
    r = (-math.sin(yaw * D), 0.0, math.cos(yaw * D))
    return f, r


def lean(f, a):
    """Up vector leaned `a` degrees toward f (negative arches back)."""
    return add(mul(UP, math.cos(a * D)), mul(f, math.sin(a * D)))


def ik(root, target, l1, l2, pole):
    """Two-bone IK in 3D.  The middle joint bends toward the pole point."""
    d_vec = sub(target, root)
    d = max(abs(l1 - l2) + 1e-3, min(l1 + l2 - 1e-3, norm(d_vec)))
    n = unit(d_vec)
    a = (l1 * l1 + d * d - l2 * l2) / (2 * d)
    h = math.sqrt(max(0.0, l1 * l1 - a * a))
    v = sub(pole, root)
    v = unit(sub(v, mul(n, dot(v, n))))
    mid = add(root, mul(n, a), mul(v, h))
    end = add(mid, mul(unit(sub(target, mid)), l2))
    return mid, end


def seg_dist(p, a, b):
    """2D distance from point p to segment a-b."""
    ax, ay = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / ((ax * ax + ay * ay) or 1.0)))
    return math.hypot(p[0] - a[0] - t * ax, p[1] - a[1] - t * ay)


# ------------------------------------------------------------- body
def solve(k):
    """Key pose -> 3D joints."""
    j = {}
    P = k["pelvis"]
    fp, rp = facing(k["hip_yaw"])
    fc, rc = facing(k["hip_yaw"] + k["twist"])
    j["hip"] = P
    j["hpR"], j["hpL"] = add(P, mul(rp, HIP_HALF)), add(P, mul(rp, -HIP_HALF))
    u1 = lean(fp, k["lean"])
    j["chest"] = add(P, mul(u1, LOW_SPINE))
    u2 = lean(fc, k["lean"] + k["curl"])
    j["neck"] = add(j["chest"], mul(u2, UP_SPINE))
    j["shB"] = add(j["neck"], mul(u2, -SHOULDER_DROP))
    j["shR"], j["shL"] = add(j["shB"], mul(rc, SHOULDER_HALF)), add(j["shB"], mul(rc, -SHOULDER_HALF))
    u3 = lean(fc, k["lean"] + k["curl"] + k["head"])
    j["head"] = add(j["neck"], mul(u3, HEAD_R * 1.3))
    j["root"] = add(j["head"], mul(UP, HEAD_R * 2.4))

    g = unit(k["blade"])
    j["haR"] = tuple(k["grip"])
    j["haL"] = sub(j["haR"], mul(g, FIST_GAP))
    j["wtip"] = add(j["haR"], mul(g, BLADE_LEN))
    j["pommel"] = sub(j["haR"], mul(g, GRIP_BACK))
    for s, side in (("R", 1.0), ("L", -1.0)):
        # elbows point down and out to their own side (plus any per-pose nudge)
        pole = add(j["sh" + s], mul(UP, -40.0), mul(rc, side * 25.0), mul(fc, k.get("elbow_fwd", 0.0)))
        j["el" + s], end = ik(j["sh" + s], j["ha" + s], UA, FA, pole)
        j["_ha" + s] = end
    for s, key in (("R", "front"), ("L", "back")):
        toe, lift = k[key]["toe"], k[key].get("lift", 0.0)
        ff, _r = facing(k[key].get("yaw", k["hip_yaw"]))
        ankle = add(toe, mul(ff, -FOOT * math.cos(lift * D)), mul(UP, FOOT * math.sin(lift * D) + ANKLE_H))
        side = 1.0 if s == "R" else -1.0
        pole = add(j["hp" + s], mul(ff, 60.0), mul(rp, side * 8.0), mul(UP, -20.0))
        j["kn" + s], end = ik(j["hp" + s], ankle, TH, SH, pole)
        j["ft" + s], j["_an" + s], j["toe" + s] = end, ankle, toe
    return j


def faults(j, k):
    """Every anatomy / grip rule the frame breaks (empty list = good)."""
    out = []
    g = unit(sub(j["wtip"], j["haR"]))
    for s, name in (("R", "near"), ("L", "far")):
        if norm(sub(j["_ha" + s], j["ha" + s])) > 0.5:
            out.append("%s hand can't reach the grip" % name)
        up, fo = sub(j["el" + s], j["sh" + s]), sub(j["ha" + s], j["el" + s])
        if angle(up, fo) > ELBOW_MAX:
            out.append("%s elbow bends %.0f > %.0f" % (name, angle(up, fo), ELBOW_MAX))
        a = angle(fo, g)
        if not GRIP_MIN <= a <= GRIP_MAX:
            out.append("%s grip: blade %.0f deg off the forearm (allowed %.0f..%.0f)" % (name, a, GRIP_MIN, GRIP_MAX))
        mid = mul(add(j["sh" + s], j["ha" + s]), 0.5)
        if j["el" + s][1] > max(j["sh" + s][1], j["ha" + s][1]) + 2 and j["el" + s][1] > mid[1] + 6 \
                and j["ha" + s][1] < j["sh" + s][1]:
            out.append("%s elbow winging up (chicken wing)" % name)
        if norm(sub(j["ft" + s], j["_an" + s])) > 0.5:
            out.append("%s leg can't reach its foot" % name)
        th, sh = sub(j["kn" + s], j["hp" + s]), sub(j["ft" + s], j["kn" + s])
        if angle(th, sh) > KNEE_MAX:
            out.append("%s knee bends %.0f > %.0f" % (name, angle(th, sh), KNEE_MAX))
        fp, _r = facing(k["hip_yaw"])
        line = sub(j["ft" + s], j["hp" + s])
        off = sub(sub(j["kn" + s], j["hp" + s]), mul(unit(line), dot(sub(j["kn" + s], j["hp" + s]), unit(line))))
        if norm(off) > 2 and dot(off, fp) < 0:
            out.append("%s knee points backward" % name)
        if min(j["ft" + s][1], j["toe" + s][1]) < -0.5:
            out.append("%s foot below ground" % name)
    # readability: the blade keeps most of its length on screen, and the
    # near arm never crosses in front of the face
    pa, pb = img(j["haR"]), img(j["wtip"])
    if math.hypot(pb[0] - pa[0], pb[1] - pa[1]) < BLADE_MIN_SCREEN * BLADE_LEN * PPU:
        out.append("blade foreshortened past readability")
    hc = img(j["head"]); hz = cam(j["head"])[2]
    for a_, b_ in (("shR", "elR"), ("elR", "haR")):
        if depth(j[a_], j[b_]) > hz and seg_dist(hc, img(j[a_]), img(j[b_])) < (HEAD_R + 4) * PPU:
            out.append("near arm crosses the face")
            break
    if abs(k["twist"]) > TWIST_MAX:
        out.append("chest twist %.0f > %.0f" % (abs(k["twist"]), TWIST_MAX))
    if j["wtip"][1] < 0:
        out.append("blade tip in the ground")
    return out


# ------------------------------------------------------------- camera
def cam(p):
    """3D point -> (screen x, screen y up, depth toward camera)."""
    x, y, z = p
    cy, sy = math.cos(YAW * D), math.sin(YAW * D)
    sx = x * cy - z * sy
    d0 = x * sy + z * cy
    cp, sp = math.cos(PITCH * D), math.sin(PITCH * D)
    return sx, y * cp - d0 * sp, d0 * cp + y * sp


def img(p, s=1.0):
    sx, sy, _d = cam(p)
    return ((ORIGIN_X + sx * PPU) * s, (GROUND_Y - sy * PPU) * s)


def depth(*ps):
    return sum(cam(p)[2] for p in ps) / len(ps)


def tone(dz):
    t = max(0.0, min(1.0, (dz + 22.0) / 44.0))
    k = 0.6 + 0.4 * t
    return tuple(int(c * k) for c in BODY) + (255,)


def thick(dz):
    return 1.0 + max(-0.12, min(0.12, dz * 0.006))


# ------------------------------------------------------------- drawing
def draw(j, smear=None):
    S = SS
    ref = cam(j["hip"])[2]      # tone/thickness are relative to his own body

    def rel(*ps):
        return depth(*ps) - ref
    im = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))

    def stroke(d, a, b, w, col):
        a, b = img(a, S), img(b, S)
        wpx = max(1.0, w * PPU * S)
        d.line([a, b], fill=col, width=int(round(wpx)))
        r = wpx / 2.0
        for q in (a, b):
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=col)

    def disc(d, c, r, col):
        q = img(c, S); r *= PPU * S
        d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=col)

    # body groups: bones (a, b, base width), discs (centre, radius)
    groups = {
        "far_arm": [("b", "shL", "elL", 9.0), ("b", "elL", "haL", 8.0), ("d", "haL", 4.4)],
        "near_arm": [("b", "shR", "elR", 9.6), ("b", "elR", "haR", 8.6), ("d", "haR", 4.6)],
        "far_leg": [("b", "hpL", "knL", 10.0), ("b", "knL", "ftL", 9.0), ("f", "L")],
        "near_leg": [("b", "hpR", "knR", 10.6), ("b", "knR", "ftR", 9.6), ("f", "R")],
        "torso": [("b", "hpL", "hpR", 10.0), ("b", "hip", "chest", 12.4), ("b", "chest", "neck", 11.2),
                  ("b", "shL", "shR", 8.6), ("d", "head", HEAD_R)],
    }
    items = []
    for name, parts in groups.items():
        pts = [j[p[1]] for p in parts if p[0] in "bd"]
        dz = depth(*pts)
        if name == "torso":
            dz = depth(j["hip"], j["chest"], j["neck"])
        items.append((dz, "group", name, parts))
    # blade in pieces so it can pass behind or in front of the body
    n = 6
    for i in range(n):
        a = add(j["pommel"], mul(sub(j["wtip"], j["pommel"]), i / float(n)))
        b = add(j["pommel"], mul(sub(j["wtip"], j["pommel"]), (i + 1) / float(n)))
        items.append((depth(a, b), "blade", i, (a, b)))
    items.sort(key=lambda t: t[0])

    if smear:
        band = Image.new("RGBA", im.size, (0, 0, 0, 0))
        outer = [img(q, S) for q in smear["tips"]]
        inner = [img(q, S) for q in reversed(smear["mids"])]
        ImageDraw.Draw(band).polygon(outer + inner, fill=SMEAR + (smear["alpha"],))
        im = Image.alpha_composite(im, band)

    for dz, kind, name, parts in items:
        if kind == "blade":
            a, b = parts
            d = ImageDraw.Draw(im)
            pa, pb = img(a, S), img(b, S)
            vx, vy = pb[0] - pa[0], pb[1] - pa[1]
            L = math.hypot(vx, vy) or 1.0
            nx, ny = -vy / L * BLADE_W * PPU * S, vx / L * BLADE_W * PPU * S
            tip = name == n - 1
            hilt = (name + 1) / float(n) * (GRIP_BACK + BLADE_LEN) <= GRIP_BACK + 0.5
            w2 = 0.0 if tip else 1.0
            poly = [(pa[0] + nx, pa[1] + ny), (pb[0] + nx * w2, pb[1] + ny * w2),
                    (pb[0] - nx * w2, pb[1] - ny * w2), (pa[0] - nx, pa[1] - ny)]
            d.polygon(poly, fill=(27, 29, 32, 255) if not hilt else (60, 40, 30, 255))
            lw = max(1, int(round(1.3 * PPU * S)))
            d.line([poly[0], poly[1]], fill=(225, 232, 240, 230), width=lw)
            d.line([poly[3], poly[2]], fill=(225, 232, 240, 230), width=lw)
            continue
        edge = Image.new("RGBA", im.size, (0, 0, 0, 0))
        fill = Image.new("RGBA", im.size, (0, 0, 0, 0))
        de, df = ImageDraw.Draw(edge), ImageDraw.Draw(fill)
        for p in parts:
            if p[0] == "b":
                a, b = j[p[1]], j[p[2]]
                z = rel(a, b); w = p[3] * thick(z)
                stroke(de, a, b, w + 2.2, EDGE + (255,)); stroke(df, a, b, w, tone(z))
            elif p[0] == "d":
                c = j[p[1]]; z = rel(c); r = p[2] * (thick(z) if p[1] != "head" else 1.0)
                disc(de, c, r + 1.1, EDGE + (255,)); disc(df, c, r, tone(z))
            else:
                s = p[1]; a, t = j["ft" + s], j["toe" + s]
                t = (t[0], t[1] + 3.4, t[2])
                z = rel(a, t); w = 7.0 * thick(z)
                stroke(de, a, t, w + 2.2, EDGE + (255,)); stroke(df, a, t, w, tone(z))
        im = Image.alpha_composite(Image.alpha_composite(im, edge), fill)
    return im.resize((W, H), Image.LANCZOS)


# ------------------------------------------------------------- poses
# Units: body units, ground y = 0, x = 0 is the figure origin.
#   pelvis: (x, y, z); hip_yaw: hips turned toward the camera (deg);
#   twist: chest turn against the hips; lean: lower spine forward (neg = arch);
#   curl: upper spine on top of that; head: head pitch on top of that;
#   grip: near (right) hand on the handle at the guard; blade: direction;
#   front/back: toe position, heel lift, foot yaw.
K = {
    # Ichigo-style two-handed kesagiri, both fists on the handle and the
    # blade carried out in front of the body the whole time.  Anime keys:
    # sharp held poses, one shunpo smear frame, the impact held on twos.
    #
    # GUARD: deep wide stance, weight forward, both hands out in front of the
    # belly, blade pointing forward-up at the target (aggressive chudan).
    "guard": dict(
        pelvis=(-6, 62, 0), hip_yaw=10, twist=10, lean=18, curl=6, head=-14,
        grip=(50, 95, 4), blade=(0.80, 0.55, -0.10),
        front=dict(toe=(40, 0, 8), lift=0), back=dict(toe=(-48, 0, -8), lift=20, yaw=-15)),
    # RAISE: anticipation.  Blade pulled up vertical in front of him, both
    # fists at chest height ahead of the near shoulder, chest open, weight
    # rocked onto the back leg.
    "raise": dict(
        pelvis=(-14, 66, 0), hip_yaw=12, twist=18, lean=-4, curl=-6, head=12,
        grip=(14, 128, 16), blade=(-0.15, 0.98, -0.10),
        front=dict(toe=(34, 0, 8), lift=0), back=dict(toe=(-52, 0, -8), lift=10, yaw=-15)),
    # DASH: the shunpo in-between.  Body thrown low and forward off the back
    # toe, blade coming over and down in front of him, eyes on the target.
    "dash": dict(
        pelvis=(18, 56, 2), hip_yaw=-6, twist=-10, lean=30, curl=12, head=-30,
        grip=(80, 116, 2), blade=(0.70, 0.68, 0.05),
        front=dict(toe=(62, 0, 10), lift=0), back=dict(toe=(-32, 8, -8), lift=60)),
    # IMPACT: long low lunge, arms driven out in front, the cut finished
    # diagonally down in front of the lead knee.  Held for two frames.
    "impact": dict(
        pelvis=(34, 48, 2), hip_yaw=-14, twist=-18, lean=34, curl=16, head=-34,
        grip=(96, 64, 2), blade=(0.72, -0.62, 0.10),
        front=dict(toe=(78, 0, 10), lift=0), back=dict(toe=(-34, 0, -8), lift=45)),
    # SETTLE: zanshin.  Weight eases back up, blade still out in front, low
    # and pointed at the opponent.
    "settle": dict(
        pelvis=(30, 58, 2), hip_yaw=-6, twist=-6, lean=22, curl=8, head=-20,
        grip=(84, 76, 2), blade=(0.92, -0.30, 0.05),
        front=dict(toe=(78, 0, 10), lift=0), back=dict(toe=(-22, 0, -8), lift=30)),
}

ACTIONS = {
    # smear: frame -> (key it swings from, start fraction, alpha)
    # ghost: frame -> [(key drawn as a shunpo afterimage, alpha)]
    # speed: frame -> speed-line count
    "attack_normal": dict(frame_ms=60, keys=["guard", "raise", "dash", "impact", "impact", "settle"],
                          smear={2: (1, 0.0, 110), 3: (2, 0.0, 135), 4: (2, 0.4, 70)},
                          ghost={2: [("raise", 0.30)], 3: [("raise", 0.14), ("dash", 0.28)]},
                          speed={2: 14, 3: 10}),
}


def slerp(a, b, t):
    a, b = unit(a), unit(b)
    om = math.acos(max(-1.0, min(1.0, dot(a, b))))
    if om < 1e-4:
        return a
    return unit(add(mul(a, math.sin((1 - t) * om) / math.sin(om)), mul(b, math.sin(t * om) / math.sin(om))))


ANCHORS = ("hip", "chest", "neck", "head", "shB", "shL", "shR", "elL", "elR",
           "haL", "haR", "hpL", "hpR", "knL", "knR", "ftL", "ftR", "wtip", "root")


def afterimage(j, alpha):
    """Shunpo afterimage: the pose washed out toward the accent, faded."""
    im = draw(j)
    r, g, b, a = im.split()
    wash = Image.new("RGBA", im.size, SMEAR + (0,))
    im = Image.blend(im, wash, 0.55)
    im.putalpha(a.point(lambda v: int(v * alpha)))
    return im


def speed_lines(j, count, seed):
    """Horizontal anime speed lines trailing behind the body."""
    import random
    rnd = random.Random(seed)
    im = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    hx, _hy = img(j["hip"], SS)
    top, bot = img(j["head"], SS)[1] - 10 * SS, (GROUND_Y - 4) * SS
    for _ in range(count):
        y = rnd.uniform(top, bot)
        x1 = hx - rnd.uniform(20, 70) * SS
        x0 = x1 - rnd.uniform(70, 200) * SS
        w = rnd.choice((1, 1, 2, 3)) * SS
        d.line([(x0, y), (x1, y)], fill=(255, 236, 228, rnd.randint(90, 190)), width=w)
    return im.resize((W, H), Image.LANCZOS)


def build(action):
    spec = ACTIONS[action]
    keys = [K[n] for n in spec["keys"]]
    joints = [solve(k) for k in keys]
    bad = []
    for n, (k, j) in enumerate(zip(keys, joints)):
        bad += ["frame %d (%s): %s" % (n + 1, spec["keys"][n], f) for f in faults(j, k)]
    if bad:
        raise SystemExit("\n".join(bad))
    frames, anchors = [], {}
    for i, j in enumerate(joints):
        smear = None
        if i in spec.get("smear", {}):
            src, skip, alpha = spec["smear"][i]
            a, b = keys[src], keys[i]
            tips, mids = [], []
            for s in range(13):
                t = skip + (1.0 - skip) * s / 12.0
                g = slerp(a["blade"], b["blade"], t)
                h = add(mul(a["grip"], 1 - t), mul(b["grip"], t))
                tips.append(add(h, mul(g, BLADE_LEN))); mids.append(add(h, mul(g, 26.0)))
            smear = dict(tips=tips, mids=mids, alpha=alpha)
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if i in spec.get("speed", {}):
            im = Image.alpha_composite(im, speed_lines(j, spec["speed"][i], i * 7 + 3))
        for name, alpha in spec.get("ghost", {}).get(i, []):
            im = Image.alpha_composite(im, afterimage(solve(K[name]), alpha))
        frames.append(Image.alpha_composite(im, draw(j, smear)))
        for name in ANCHORS:
            x, y = img(j[name])
            anchors.setdefault(name, []).append([round(x, 2), round(y, 2)])
    return spec, frames, anchors


def write(action):
    spec, frames, anchors = build(action)
    for f in os.listdir(PKG):
        if f.startswith(action + "_") and f[len(action) + 1:-4].isdigit() and f.endswith(".png"):
            os.remove(os.path.join(PKG, f))
    names = []
    for i, im in enumerate(frames):
        fn = "%s_%02d.png" % (action, i + 1)
        im.save(os.path.join(PKG, fn)); names.append(fn)
    n, fm = len(names), float(spec["frame_ms"])
    cpath = os.path.join(PKG, "character.json")
    ch = json.load(open(cpath))
    ch["actions"][action].update(frames=names, frame_ms=fm, duration_ms=fm * n)
    ch["anchors"][action] = anchors
    json.dump(ch, open(cpath, "w"), indent=1)
    kpath = os.path.join(PKG, "swordsman_rig.fxkit.json")
    kit = json.load(open(kpath))
    kit["timing"][action] = {"frame_ms": int(fm), "frames": n}
    ka = dict(anchors)
    ka["wtip2"] = [list(q) for q in anchors["haL"]]
    kit["anchors"][action] = {k: ka[k] for k in kit["anchors"][action]} if kit["anchors"].get(action) else ka
    json.dump(kit, open(kpath, "w"), indent=1)
    print(action, n, "frames @", fm, "ms =", fm * n, "ms")


def preview(action, out):
    spec, frames, _a = build(action)
    tw, th = W, H
    sheet = Image.new("RGB", (len(frames) * tw, th + 18), (36, 38, 46))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(frames):
        bg = Image.new("RGBA", (W, H), (36, 38, 46, 255)); bg.alpha_composite(im)
        sheet.paste(bg.convert("RGB"), (i * tw, 18))
        d.line([(i * tw, 18 + GROUND_Y), ((i + 1) * tw, 18 + GROUND_Y)], fill=(70, 72, 84))
        d.text((i * tw + 6, 3), "%s_%02d  %s" % (action, i + 1, spec["keys"][i]), fill=(230, 230, 230))
    sheet.save(out)


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "attack_normal"
    if "--preview" in sys.argv:
        preview(a, sys.argv[sys.argv.index("--preview") + 1])
    else:
        write(a)
