#!/usr/bin/env python3
"""Rig Forge -> transparent PNG frame baker.

Port of rigforge.html joints()/drawFigure() (the authoring truth for pb_character
Rig Forge exports).  Renders every keyframe of every action to a transparent PNG.

usage: rigforge_bake.py <character.json> <out_dir> [--px-per-unit 2] [--ss 4]
Writes  <out_dir>/<action>/<action>_NN.png  and  <out_dir>/bake_manifest.json

The manifest also carries each action's per-frame joint table (`joints`),
in rig units relative to the bake origin with rx zeroed -- the same space as
the sprite pixels / px_per_unit.  FX Studio exports the identical table as
`fx_studio.joint_track` (tools/fx/studio/rig_rf.js jointTrack()), so FX
anchored to a hand or blade tip follow the baked animation exactly.

usage: rigforge_bake.py <character.json> --joints-only [out.json]
Writes only the joint table (no PNGs, Pillow not required).
"""
import json, math, os, sys

D = math.pi / 180.0
LAYERS = [  # id, a, b, b2, mid, width, far, kind
    ("far_upper_arm", "shL", "elL", None, None, 0.94, True, "bone"),
    ("far_forearm", "elL", "haL", None, None, 0.83, True, "bone"),
    ("far_thigh", "hpL", "knL", None, None, 1.00, True, "bone"),
    ("far_shin", "knL", "ftL", None, None, 0.88, True, "bone"),
    ("pelvis_girdle", "hip", "hpL", "hpR", None, 0.98, False, "pair"),
    ("lower_spine", "hip", "chest", None, None, 1.24, False, "bone"),
    ("upper_spine", "chest", "neck", None, None, 1.12, False, "bone"),
    ("shoulder_girdle", "neck", "shL", "shR", "shB", 0.86, False, "pair"),
    ("head", "neck", "head", None, None, 1, False, "head"),
    ("near_thigh", "hpR", "knR", None, None, 1.10, False, "bone"),
    ("near_shin", "knR", "ftR", None, None, 0.96, False, "bone"),
    ("near_upper_arm", "shR", "elR", None, None, 1.00, False, "bone"),
    ("near_forearm", "elR", "haR", None, None, 0.90, False, "bone"),
    ("weapon", "haR", "wtip", None, None, 1, False, "weapon"),
]
PDEF = dict(rx=0, ry=0, rot=0, sp=0, sp2=0, hd=0, shlx=0, shly=0, shrx=0, shry=0,
            hplx=0, hply=0, hprx=0, hpry=0, lua=168, lfa=12, rua=192, rfa=-12,
            lth=8, lsh=10, rth=-8, rsh=12, luas=1, lfas=1, ruas=1, rfas=1,
            lths=1, lshs=1, rths=1, rshs=1, torsos=1, wp=0, wpx=4, wpy=0,
            wspin=0, wlen=1)


def sd(a, l): return (math.sin(a * D) * l, math.cos(a * D) * l)
def su(a, l): return (math.sin(a * D) * l, -math.cos(a * D) * l)
def add(p, v): return (p[0] + v[0], p[1] + v[1])


def rig_of(ch):
    r = ch["rig"]; b = r.get("bones", {}); pv = r.get("pivots", {})
    return dict(ua=b.get("ua", 30), fa=b.get("fa", 30), th=b.get("th", 38),
                sh=b.get("sh", 36), torso=b.get("torso", 54), head=b.get("head", 15),
                shx=pv.get("shoulder_x", 0), shy=pv.get("shoulder_y", 1),
                hipx=pv.get("hip_x", 0), hipy=pv.get("hip_y", 0), sep=pv.get("side_separation", 3))


def weapon_shapes(ch):
    w = ch.get("weapon") or {}
    sh = w.get("shapes") or ([w["points"]] if w.get("points") else [])
    return [s for s in sh if s]


def joints(p, rig, shapes):
    p = {**PDEF, **p}
    hipC = (p["rx"] + rig["hipx"], p["ry"] + rig["hipy"])
    chest = add(hipC, su(p["sp"], rig["torso"] * 0.55 * p["torsos"]))
    neck = add(chest, su(p["sp"] + p["sp2"], rig["torso"] * 0.45 * p["torsos"]))
    head = add(neck, su(p["sp"] + p["sp2"] + p["hd"], rig["head"] * 1.30))
    shB = (neck[0] + rig["shx"], neck[1] + rig["shy"])
    shL = (shB[0] - rig["sep"] * 0.8 + p["shlx"], shB[1] + p["shly"])
    shR = (shB[0] + rig["sep"] * 0.8 + p["shrx"], shB[1] + p["shry"])
    hpL = (hipC[0] - rig["sep"] + p["hplx"], hipC[1] + p["hply"])
    hpR = (hipC[0] + rig["sep"] + p["hprx"], hipC[1] + p["hpry"])
    elL = add(shL, sd(p["lua"], rig["ua"] * p["luas"])); haL = add(elL, sd(p["lua"] + p["lfa"], rig["fa"] * p["lfas"]))
    elR = add(shR, sd(p["rua"], rig["ua"] * p["ruas"])); haR = add(elR, sd(p["rua"] + p["rfa"], rig["fa"] * p["rfas"]))
    knL = add(hpL, sd(p["lth"], rig["th"] * p["lths"])); ftL = add(knL, sd(p["lth"] + p["lsh"], rig["sh"] * p["lshs"]))
    knR = add(hpR, sd(p["rth"], rig["th"] * p["rths"])); ftR = add(knR, sd(p["rth"] + p["rsh"], rig["sh"] * p["rshs"]))
    wang = p["rua"] + p["rfa"] + p["wp"]
    out = dict(hip=hipC, shB=shB, hpL=hpL, hpR=hpR, chest=chest, neck=neck, head=head, shL=shL, shR=shR,
               elL=elL, haL=haL, elR=elR, haR=haR, knL=knL, ftL=ftL, knR=knR, ftR=ftR)
    # Rig Forge's weapon tip (the weapon point with the largest x, carried
    # through the grip transform) and "root" marker above the head.
    out["root"] = (head[0], head[1] - rig["head"] * 2.4)
    allp = [q for sh in shapes for q in sh]
    wtip = haR
    if len(allp) > 2:
        tp = allp[0]
        for q in allp:
            if q[0] > tp[0]:
                tp = q
        wa = (wang - 90) * D; wca, wsa = math.cos(wa), math.sin(wa)
        wsy = math.cos(p["wspin"] * D)
        lx = (tp[0] - p["wpx"]) * p["wlen"]; ly = (tp[1] - p["wpy"]) * wsy
        wtip = (haR[0] + lx * wca - ly * wsa, haR[1] + lx * wsa + ly * wca)
    out["wtip"] = wtip
    if p["rot"]:
        rc, rs = math.cos(p["rot"] * D), math.sin(p["rot"] * D)
        for k, v in list(out.items()):
            dx, dy = v[0] - hipC[0], v[1] - hipC[1]
            out[k] = (hipC[0] + dx * rc - dy * rs, hipC[1] + dx * rs + dy * rc)
        out["hip"] = hipC; wang += p["rot"]
    out["wang"] = wang
    return out


def weapon_poly(j, p, shapes):
    p = {**PDEF, **p}
    wa = (j["wang"] - 90) * D; ca, sa = math.cos(wa), math.sin(wa)
    sy = math.cos(p["wspin"] * D)
    if abs(sy) < 0.035: sy = (-1 if sy < 0 else 1) * 0.035
    hx, hy = j["haR"]
    polys = []
    for sh in shapes:
        pts = []
        for x, y in sh:
            lx = (x - p["wpx"]) * p["wlen"]; ly = (y - p["wpy"]) * sy
            pts.append((hx + lx * ca - ly * sa, hy + lx * sa + ly * ca))
        polys.append(pts)
    return polys


def hexrgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def draw_frame(p, rig, shapes, pal, S, cx, cy, W, H, outline=True):
    """Render at S px/unit onto a W x H RGBA canvas whose centre = world (cx, cy)."""
    j = joints(p, rig, shapes)
    body = hexrgb(pal.get("body", "#f2f4f6"))
    tf = lambda q: ((q[0] - cx) * S + W / 2.0, (q[1] - cy) * S + H / 2.0)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def stroke(layer_img, a, b, w, col):
        d = ImageDraw.Draw(layer_img)
        a, b = tf(a), tf(b); wpx = max(1.0, w * S)
        d.line([a, b], fill=col, width=int(round(wpx)))
        r = wpx / 2.0
        for q in (a, b):
            d.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=col)

    for (lid, a, b, b2, mid, w, far, kind) in LAYERS:
        lay_fill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        lay_edge = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        alpha = int(255 * (0.82 if far else 1.0))
        col = body + (alpha,); edge = (12, 14, 18, alpha)
        Wl = (9.4 if far else 10.0) * w
        if kind == "head":
            for img, c, grow in ((lay_edge, edge, 1.4 / S * 2.2), (lay_fill, col, 0)):
                q = tf(j["head"]); r = (rig["head"] + (grow if img is lay_edge else 0)) * S
                ImageDraw.Draw(img).ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=c)
        elif kind == "pair":
            hub = j[mid] if mid else j[a]
            segs = ([(j[a], hub)] if mid else []) + [(hub, j[b]), (hub, j[b2])]
            for s0, s1 in segs:
                stroke(lay_edge, s0, s1, Wl + 2.2, edge); stroke(lay_fill, s0, s1, Wl, col)
        elif kind == "bone":
            stroke(lay_edge, j[a], j[b], Wl + 2.2, edge); stroke(lay_fill, j[a], j[b], Wl, col)
        else:
            polys = weapon_poly(j, p, shapes)
            for pts in polys:
                if len(pts) < 3: continue
                t = [tf(q) for q in pts]
                d = ImageDraw.Draw(lay_fill)
                d.polygon(t, fill=(27, 29, 32, 255))
                d.line(t + [t[0]], fill=(225, 232, 240, 210), width=max(1, int(round(1.6 * S))), joint="curve")
            lay_edge = None
        if outline and lay_edge is not None:
            canvas = Image.alpha_composite(canvas, lay_edge)
        canvas = Image.alpha_composite(canvas, lay_fill)
    return canvas, j


def extent(p, rig, shapes, zero_rx):
    q = dict(p)
    if zero_rx: q["rx"] = 0
    j = joints(q, rig, shapes)
    pts = [j[k] for k in j if k not in ("wang", "root", "wtip")]
    for poly in weapon_poly(j, q, shapes): pts += poly
    r = rig["head"] + 3
    xs = [x for x, y in pts]; ys = [y for x, y in pts]
    return min(xs) - 6, max(xs) + 6, min(ys) - r - 6, max(ys) + 6


JOINT_NAMES = ("hip", "chest", "neck", "head", "shB", "shL", "shR", "elL", "elR",
               "haL", "haR", "hpL", "hpR", "knL", "knR", "ftL", "ftR", "wtip", "root")


def bake_origin(ch, rig, shapes, zero_rx=True):
    """hip x = 0, y = centre of the idle action's bounding box."""
    idle = ch["actions"]["idle"]["keyframes"]
    e = [extent(p, rig, shapes, zero_rx) for p in idle]
    return 0.0, (min(x[2] for x in e) + max(x[3] for x in e)) / 2.0


def joint_frames(kfs, rig, shapes, cx, cy, zero_rx=True):
    """Per-frame joint positions relative to the bake origin (rig units,
    rounded to 0.01) plus the weapon world angle -- one dict per keyframe."""
    out = []
    for p in kfs:
        q = dict(p)
        if zero_rx: q["rx"] = 0
        j = joints(q, rig, shapes)
        f = {k: [round(j[k][0] - cx, 2), round(j[k][1] - cy, 2)] for k in JOINT_NAMES}
        f["wang"] = round(j["wang"], 2)
        out.append(f)
    return out


def joint_track(ch):
    rig = rig_of(ch); shapes = weapon_shapes(ch)
    cx, cy = bake_origin(ch, rig, shapes)
    return {name: dict(duration_ms=act.get("duration_ms"),
                       frames=joint_frames(act["keyframes"], rig, shapes, cx, cy),
                       root_rx=[round(p.get("rx", 0), 2) for p in act["keyframes"]],
                       root_ry=[round(p.get("ry", 0), 2) for p in act["keyframes"]])
            for name, act in ch["actions"].items() if act.get("keyframes")}


def _job(args):
    (fn, q, rig, shapes, pal, S, cx, cy, Wf, Hf, ss, out) = args
    im, _ = draw_frame(q, rig, shapes, pal, S * ss, cx, cy, Wf * ss, Hf * ss)
    im = im.resize((Wf, Hf), Image.LANCZOS)
    im.save(os.path.join(out, fn))
    return fn


def main():
    from multiprocessing import Pool
    if "--joints-only" in sys.argv:
        ch = json.load(open(sys.argv[1]))
        args = [a for a in sys.argv[2:] if a != "--joints-only"]
        txt = json.dumps(joint_track(ch), indent=1)
        if args:
            open(args[0], "w").write(txt)
        else:
            print(txt)
        return
    global Image, ImageDraw
    from PIL import Image, ImageDraw
    src, out = sys.argv[1], sys.argv[2]
    ppu = float(sys.argv[sys.argv.index("--px-per-unit") + 1]) if "--px-per-unit" in sys.argv else 2.0
    ss = int(sys.argv[sys.argv.index("--ss") + 1]) if "--ss" in sys.argv else 4
    zero_rx = "--keep-rx" not in sys.argv
    ch = json.load(open(src)); rig = rig_of(ch); shapes = weapon_shapes(ch); pal = ch.get("palette", {})
    # common origin: idle bbox centre (y) and hip x=0 so every set registers to the same world point
    cx, cy = bake_origin(ch, rig, shapes, zero_rx)
    manifest = dict(px_per_unit=ppu, head_diameter_px=rig["head"] * 2 * ppu, origin_world=[cx, cy], zero_rx=zero_rx, actions={})
    for name, act in ch["actions"].items():
        kfs = act["keyframes"]
        ex = [extent(p, rig, shapes, zero_rx) for p in kfs]
        hw = max(max(abs(x[0] - cx), abs(x[1] - cx)) for x in ex)
        hh = max(max(abs(x[2] - cy), abs(x[3] - cy)) for x in ex)
        Wf = int(math.ceil(hw * 2 * ppu / 2) * 2) + 4; Hf = int(math.ceil(hh * 2 * ppu / 2) * 2) + 4
        os.makedirs(os.path.join(out, name), exist_ok=True)
        files, travel, jobs = [], [], []
        for i, p in enumerate(kfs):
            q = dict(p); travel.append(round(p.get("rx", 0), 2))
            if zero_rx: q["rx"] = 0
            fn = "%s/%s_%02d.png" % (name, name, i)
            jobs.append((fn, q, rig, shapes, pal, ppu, cx, cy, Wf, Hf, ss, out)); files.append(fn)
        with Pool(os.cpu_count() or 2) as pool:
            pool.map(_job, jobs)
        manifest["actions"][name] = dict(files=files, size=[Wf, Hf], duration_ms=act.get("duration_ms"), root_rx=travel,
                                          root_ry=[round(p.get("ry", 0), 2) for p in kfs],
                                          joints=joint_frames(kfs, rig, shapes, cx, cy, zero_rx))
        print(name, len(files), "frames", Wf, "x", Hf)
    json.dump(manifest, open(os.path.join(out, "bake_manifest.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
