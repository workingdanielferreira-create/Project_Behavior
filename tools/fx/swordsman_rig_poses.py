#!/usr/bin/env python3
"""Pose generator for fx_packages/swordsman_rig (filled Rig Forge style).

Poses are authored as body targets, not raw bone angles: hip position, a
two-part spine (lower `sp` + upper `sp2`, so the back can curl and arch),
head tilt, the near hand's grip point, the blade angle and the two toe
positions.  Two-bone IK then places elbows and knees with fixed bone
lengths, knees always bending forward, both feet planted and both hands
on the hilt.  Frames are drawn with tools/fx/rigforge_bake.py's joints()
and weapon_poly(), plus fists, feet and darker far-side limbs for depth.

usage: swordsman_rig_poses.py <action> [--preview out.png]
Rewrites fx_packages/swordsman_rig/<action>_NN.png, the action's entry in
character.json (frames, frame_ms, duration_ms, anchors) and the action's
timing and anchors in swordsman_rig.fxkit.json.  Only attack_normal is
authored so far.
"""
import json, math, os, sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rigforge_bake as rb

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG = os.path.join(ROOT, "fx_packages", "swordsman_rig")

# Canvas: same size and origin as the rest of the package.
W, H = 608, 596
ORIGIN = (304.0, 298.0)
GROUND_Y = 458.0          # feet line shared with idle/run/defend/impact
PPU = 1.7                 # image px per rig unit
SS = 4                    # supersampling

# About 6.6 heads tall: thigh a little longer than shin, arm reaching
# mid-thigh, shoulders set 8 units under the neck so a neck shows.
CH = {
    "rig": {"bones": {"ua": 34, "fa": 36, "th": 44, "sh": 41, "torso": 58, "head": 13},
            "pivots": {"shoulder_x": 0, "shoulder_y": 8, "hip_x": 0, "hip_y": 0,
                       "side_separation": 3}},
    # Two-handed sword: grip at x=0 (near hand), pommel -14, guard +3, tip +70.
    "weapon": {"shapes": [
        [[-14, -1.6], [2, -1.6], [2, -5], [4, -5], [4, -2], [62, -2], [70, 0],
         [62, 2], [4, 2], [4, 5], [2, 5], [2, 1.6], [-14, 1.6]]]},
}
RIG = rb.rig_of(CH)
SHAPES = rb.weapon_shapes(CH)
BODY = (0xE8, 0x23, 0x1A)                       # palette.body
FAR = tuple(int(c * 0.62) for c in BODY)        # far-side limbs: darker, opaque
EDGE = (12, 14, 18)
SMEAR = (0xFF, 0x7A, 0x5C)                      # palette.accent
FOOT = 10.0                                     # ankle -> toe
ANKLE_H = 3.0
FAR_HAND = 9.0                                  # far hand sits this far down the grip

D = math.pi / 180.0


def lerp(a, b, t):
    return a + (b - a) * t


def ik(root, target, l1, l2, pick):
    """Two-bone IK -> (mid joint, end joint).  `pick` scores the two mid
    solutions; the higher score wins."""
    dx, dy = target[0] - root[0], target[1] - root[1]
    d = max(abs(l1 - l2) + 1e-3, min(l1 + l2 - 1e-3, math.hypot(dx, dy)))
    base = math.atan2(dy, dx)
    b = math.acos(max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d))))
    cands = [(root[0] + l1 * math.cos(base + s * b), root[1] + l1 * math.sin(base + s * b)) for s in (1, -1)]
    mid = max(cands, key=pick)
    ux, uy = target[0] - mid[0], target[1] - mid[1]
    n = math.hypot(ux, uy) or 1.0
    return mid, (mid[0] + ux / n * l2, mid[1] + uy / n * l2)


def ang(a, b):
    """Rig Forge bone angle (0 = down, + toward +x) of the segment a -> b."""
    return math.atan2(b[0] - a[0], b[1] - a[1]) / D


def ankle_of(toe, lift):
    return (toe[0] - FOOT * math.cos(lift * D), toe[1] - FOOT * math.sin(lift * D) - ANKLE_H)


def solve(k):
    """Pose targets -> Rig Forge keyframe params (+ extras for drawing)."""
    p = dict(rb.PDEF)
    so = k.get("open", 0.0)
    p.update(rx=k["hip"][0], ry=k["hip"][1], sp=k["sp"], sp2=k["sp2"], hd=k["hd"],
             shrx=so, shlx=-so, hprx=so * 0.5, hplx=-so * 0.5, wpx=0, wpy=0)
    j = rb.joints(p, RIG, SHAPES)
    phi = k["blade"]
    grip = k["grip"]
    fhand = (grip[0] - FAR_HAND * math.cos(phi * D), grip[1] - FAR_HAND * math.sin(phi * D))
    elbow_pick = {"down": lambda q: q[1], "fwd": lambda q: q[0] - q[1] * 0.25,
                  "out": lambda q: -q[1]}[k.get("elbow", "down")]
    for side, tgt in (("R", grip), ("L", fhand)):
        s = j["sh" + side]
        el, ha = ik(s, tgt, RIG["ua"], RIG["fa"], elbow_pick)
        up = ang(s, el)
        p[("r" if side == "R" else "l") + "ua"] = up
        p[("r" if side == "R" else "l") + "fa"] = ang(el, ha) - up
    toes = {"R": k["front"], "L": k["back"]}
    lifts = {"R": k.get("front_lift", 0.0), "L": k.get("back_lift", 30.0)}
    for side in ("R", "L"):
        h = j["hp" + side]
        an = ankle_of(toes[side], lifts[side])
        kn, ft = ik(h, an, RIG["th"], RIG["sh"], lambda q: q[0])   # knees point forward
        up = ang(h, kn)
        p[("r" if side == "R" else "l") + "th"] = up
        p[("r" if side == "R" else "l") + "sh"] = ang(kn, ft) - up
    p["wp"] = phi + 90 - (p["rua"] + p["rfa"])
    j = rb.joints(p, RIG, SHAPES)
    err = max(math.dist(j["haR"], grip), math.dist(j["haL"], fhand),
              math.dist(j["ftR"], ankle_of(toes["R"], lifts["R"])),
              math.dist(j["ftL"], ankle_of(toes["L"], lifts["L"])))
    return p, j, toes, err


def tf(q, s=1.0):
    return ((ORIGIN[0] + q[0] * PPU) * s, (GROUND_Y + q[1] * PPU) * s)


def draw(p, j, toes, smear=None):
    S = SS
    img = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))

    def stroke(d, a, b, w, col):
        a, b = tf(a, S), tf(b, S)
        wpx = max(1.0, w * PPU * S)
        d.line([a, b], fill=col, width=int(round(wpx)))
        r = wpx / 2.0
        for q in (a, b):
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=col)

    def disc(d, c, r, col):
        q = tf(c, S); r *= PPU * S
        d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=col)

    def group(parts):
        """One body part group: outline under the whole group, then fill, so
        joints inside a limb stay seamless while overlapping limbs separate."""
        nonlocal img
        edge = Image.new("RGBA", img.size, (0, 0, 0, 0))
        fill = Image.new("RGBA", img.size, (0, 0, 0, 0))
        de, df = ImageDraw.Draw(edge), ImageDraw.Draw(fill)
        for kind, a, b, w, far in parts:
            col = (FAR if far else BODY) + (255,)
            if kind == "disc":
                disc(de, a, b + 1.1, EDGE + (255,)); disc(df, a, b, col)
            else:
                wl = (9.4 if far else 10.0) * w
                stroke(de, a, b, wl + 2.2, EDGE + (255,)); stroke(df, a, b, wl, col)
        img = Image.alpha_composite(Image.alpha_composite(img, edge), fill)

    def toe(side, far):
        wl = (9.4 if far else 10.0) * 0.72
        t = toes[side]
        return ("bone", j["ft" + side], (t[0], t[1] - wl / 2.0 - 0.6), 0.72, far)

    def limb(a, b, c, w1, w2, far, end):
        return [("bone", j[a], j[b], w1, far), ("bone", j[b], j[c], w2, far), end]

    def weapon():
        d = ImageDraw.Draw(img)
        for pts in rb.weapon_poly(j, p, SHAPES, 0):
            t = [tf(q, S) for q in pts]
            d.polygon(t, fill=(27, 29, 32, 255))
            d.line(t + [t[0]], fill=(225, 232, 240, 230), width=max(1, int(round(1.5 * PPU * S))), joint="curve")

    group(limb("shL", "elL", "haL", 0.94, 0.83, True, ("disc", j["haL"], 4.5, 0, True)))
    group(limb("hpL", "knL", "ftL", 1.00, 0.88, True, toe("L", True)))
    group([("bone", j["hip"], j["hpL"], 0.98, False), ("bone", j["hip"], j["hpR"], 0.98, False),
           ("bone", j["hip"], j["chest"], 1.24, False), ("bone", j["chest"], j["neck"], 1.12, False),
           ("bone", j["neck"], j["shB"], 0.86, False), ("bone", j["shB"], j["shL"], 0.86, False),
           ("bone", j["shB"], j["shR"], 0.86, False), ("disc", j["head"], RIG["head"], 0, False)])
    group(limb("hpR", "knR", "ftR", 1.10, 0.96, False, toe("R", False)))
    group(limb("shR", "elR", "haR", 1.00, 0.90, False, ("bone", j["haR"], j["haR"], 0.0, False)))
    if smear:
        band = Image.new("RGBA", img.size, (0, 0, 0, 0))
        outer = [tf(q, S) for q in smear["tips"]]
        inner = [tf(q, S) for q in reversed(smear["mids"])]
        ImageDraw.Draw(band).polygon(outer + inner, fill=SMEAR + (smear.get("alpha", 110),))
        img = Image.alpha_composite(img, band)
    weapon()
    group([("disc", j["haR"], 4.5, 0, False)])
    return img.resize((W, H), Image.LANCZOS)


# ------------------------------------------------------------------ poses
# Units: rig units, y up is negative, ground at 0, x=0 is the figure origin.
# blade: screen angle of the blade (0 = forward, 90 = down, 270 = straight up);
# kept continuous so in-betweens sweep the right way round.
FRONT, BACK = (44.0, 0.0), (-36.0, 0.0)
K = {
    # guard: knees soft, chest over the hips, blade up-forward
    "ready":   dict(hip=(-4, -73), sp=10, sp2=6, hd=-6, grip=(34, -112), blade=303, open=1,
                    back_lift=28, elbow="down"),
    # anticipation 1: sink and coil, back rounds forward, hands pulled in
    "coil":    dict(hip=(-8, -66), sp=20, sp2=16, hd=-22, grip=(26, -100), blade=292, open=-1,
                    back_lift=24, elbow="down"),
    # anticipation 2: weight onto the back leg, back arches, sword cocked behind the head
    "windup":  dict(hip=(-11, -71), sp=-12, sp2=-22, hd=14, grip=(-26, -171), blade=166, open=-3,
                    back_lift=14, front_lift=0, elbow="fwd"),
    # held wind-up keeps drifting a touch further (moving hold)
    "windup2": dict(hip=(-12, -72), sp=-14, sp2=-25, hd=16, grip=(-29, -173), blade=172, open=-4,
                    back_lift=12, front_lift=0, elbow="fwd"),
    # release: hips drive forward first, spine unwinds, blade swings up over the head
    "release": dict(hip=(0, -72), sp=6, sp2=-4, hd=4, grip=(10, -178), blade=250, open=1,
                    back_lift=28, elbow="fwd"),
    # fast frame: chest whips forward, arms extend, blade past vertical
    "whip":    dict(hip=(12, -66), sp=22, sp2=10, hd=-12, grip=(74, -146), blade=318, open=5,
                    back_lift=38, elbow="down"),
    # contact: arms extended, back curled into the cut, front knee loaded
    "hit":     dict(hip=(16, -62), sp=30, sp2=16, hd=-24, grip=(108, -100), blade=379, open=7,
                    back_lift=44, elbow="down"),
    # impact squash held: hips sink, shoulders drop into the blow
    "hit2":    dict(hip=(17, -59), sp=33, sp2=17, hd=-26, grip=(109, -94), blade=383, open=7,
                    back_lift=46, elbow="down"),
    # follow-through: blade carries down past the target, body overshoots
    "follow":  dict(hip=(19, -60), sp=37, sp2=18, hd=-28, grip=(104, -72), blade=412, open=6,
                    back_lift=46, elbow="down"),
    # recoil: body rebounds up, blade lifts back toward guard
    "recoil":  dict(hip=(12, -66), sp=24, sp2=8, hd=-16, grip=(86, -98), blade=384, open=4,
                    back_lift=38, elbow="down"),
    # settle back into guard (ease out)
    "settle":  dict(hip=(2, -71), sp=14, sp2=6, hd=-8, grip=(50, -110), blade=334, open=2,
                    back_lift=30, elbow="down"),
}
for _k in K.values():
    _k.setdefault("front", FRONT); _k.setdefault("back", BACK)

NUM = ("hip", "sp", "sp2", "hd", "blade", "open", "back_lift", "front_lift", "front", "back")


def blend(a, b, t):
    """In-between of two poses.  The grip moves on an arc around the
    shoulder (polar lerp), not on a straight line."""
    a, b = K[a], K[b]
    out = {}
    for n in NUM:
        va, vb = a.get(n, 0.0), b.get(n, 0.0)
        out[n] = tuple(lerp(x, y, t) for x, y in zip(va, vb)) if isinstance(va, tuple) else lerp(va, vb, t)
    sa, sb = solve(a)[1]["shR"], solve(b)[1]["shR"]
    ra = (a["grip"][0] - sa[0], a["grip"][1] - sa[1]); rb_ = (b["grip"][0] - sb[0], b["grip"][1] - sb[1])
    la, lb = math.hypot(*ra), math.hypot(*rb_)
    aa, ab = math.atan2(ra[1], ra[0]), math.atan2(rb_[1], rb_[0])
    if ab - aa > math.pi: ab -= 2 * math.pi
    if aa - ab > math.pi: ab += 2 * math.pi
    mid = dict(a); mid.update(out)
    s = solve(mid)[1]["shR"]
    r, th = lerp(la, lb, t), lerp(aa, ab, t)
    out["grip"] = (s[0] + r * math.cos(th), s[1] + r * math.sin(th))
    out["elbow"] = (a if t < 0.5 else b).get("elbow", "down")
    return out


# Uneven spacing: slow in/out around the anticipation, wide steps through
# the swing, held contact; each hold drifts a little so it stays alive.
ACTIONS = {
    "attack_normal": dict(frame_ms=28, frames=[
        ("ready", "ready", 0.0),
        ("ready", "coil", 0.6),
        ("coil", "coil", 0.0),
        ("coil", "windup", 0.55),
        ("windup", "windup", 0.0),
        ("windup", "windup2", 0.6),
        ("windup2", "windup2", 0.0),     # anticipation peak, held ~3 frames
        ("release", "release", 0.0),
        ("whip", "whip", 0.0),           # fast frame, smeared
        ("hit", "hit", 0.0),             # contact
        ("hit", "hit2", 1.0),            # impact squash, held
        ("hit2", "hit2", 0.0),
        ("follow", "follow", 0.0),       # follow-through past the target
        ("recoil", "recoil", 0.0),
        ("settle", "settle", 0.0),
        ("settle", "ready", 0.7),
    ], smear={8: 7, 9: 8}),             # frame index -> sweep from that earlier frame
}


def blade_line(pose_j, a, b):
    """Blade point at local x = a..b (grip at 0) in world units."""
    phi = pose_j["wang"] - 90
    c, s = math.cos(phi * D), math.sin(phi * D)
    h = pose_j["haR"]
    return (h[0] + a * c, h[1] + a * s), (h[0] + b * c, h[1] + b * s)


def build(action):
    spec = ACTIONS[action]
    poses = [blend(a, b, t) for a, b, t in spec["frames"]]
    solved = [solve(p) for p in poses]
    worst = max(s[3] for s in solved)
    if worst > 0.5:
        raise SystemExit("IK target out of reach (%.2f units)" % worst)
    frames, anchors = [], {}
    for i, (p, j, toes, _e) in enumerate(solved):
        smear = None
        if i in spec.get("smear", {}):
            pj = solved[spec["smear"][i]][1]
            tips, mids = [], []
            for n in range(9):
                t = n / 8.0
                # sweep the blade between the earlier frame and this one
                ph = lerp(pj["wang"], j["wang"], t)
                hx, hy = lerp(pj["haR"][0], j["haR"][0], t), lerp(pj["haR"][1], j["haR"][1], t)
                c, s = math.cos((ph - 90) * D), math.sin((ph - 90) * D)
                tips.append((hx + 70 * c, hy + 70 * s)); mids.append((hx + 28 * c, hy + 28 * s))
            smear = dict(tips=tips, mids=mids, alpha=120 if i == 8 else 70)
        frames.append(draw(p, j, toes, smear))
        for name in rb.JOINT_NAMES:
            if name == "wtip2":
                continue
            x, y = tf(j[name])
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
    act = ch["actions"][action]
    act.update(frames=names, frame_ms=fm, duration_ms=fm * n)
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
    cols = 8; tw, th = W // 2, H // 2
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 14)), (36, 38, 46))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(frames):
        x, y = (i % cols) * tw, (i // cols) * (th + 14)
        bg = Image.new("RGBA", (W, H), (36, 38, 46, 255)); bg.alpha_composite(im)
        sheet.paste(bg.convert("RGB").resize((tw, th), Image.LANCZOS), (x, y + 14))
        d.line([(x, y + 14 + GROUND_Y / 2), (x + tw, y + 14 + GROUND_Y / 2)], fill=(70, 72, 84))
        d.text((x + 4, y + 1), "%s_%02d" % (action, i + 1), fill=(230, 230, 230))
    sheet.save(out)
    gif = []
    for im in frames:
        bg = Image.new("RGBA", (W, H), (36, 38, 46, 255)); bg.alpha_composite(im)
        gif.append(bg.convert("RGB").resize((tw, th), Image.LANCZOS))
    hold = [Image.new("RGB", (tw, th), (36, 38, 46))]
    gif[0].save(out[:-4] + ".gif", save_all=True, append_images=gif[1:] + hold,
                duration=[int(spec["frame_ms"]) * 4] * len(gif) + [400], loop=0)


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "attack_normal"
    if "--preview" in sys.argv:
        preview(a, sys.argv[sys.argv.index("--preview") + 1])
    else:
        write(a)
