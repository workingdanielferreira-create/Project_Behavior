"""Build the V3 3D test fighter for ronin_copy by script (no Blender UI needed).

Run with Blender's Python module (pip install bpy) or Blender itself:
    python build_ronin3d.py [out.glb] [--renders DIR]
    blender -b -P build_ronin3d.py -- [out.glb] [--renders DIR]

Makes a smooth anime-toon body + katana on a skeleton that follows v3/RIG_SPEC.md
(Mixamo bone names, fingers, Jaw / eyes + shape keys, weapon bones), keys the clips
idle, run, attack_normal, attack_special, ultimate, hit_light, ko (30 fps, in place)
and exports a .glb. With --renders it also writes pose-sheet frames (Workbench).

Space: Blender Z up, the character faces -Y (Front view), its left side is +X.
"""
import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Euler, Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
OUT = os.path.join(REPO, "characters", "ronin_copy", "ronin_copy.glb")
RENDERS = None
i = 0
while i < len(argv):
    if argv[i] == "--renders":
        RENDERS = argv[i + 1]
        i += 2
        continue
    OUT = argv[i]
    i += 1

FPS = 30
F, B, U, D = Vector((0, -1, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((0, 0, -1))


def v(*a):
    return Vector(a)


def nrm(*a):
    return Vector(a).normalized()


# ---------------------------------------------------------------- skeleton
A_DEG = 35.0                                   # A-pose: arms 35 deg below horizontal
CA, SA = math.cos(math.radians(A_DEG)), math.sin(math.radians(A_DEG))


def side_pts(s):
    """Joint points for one side (s = +1 left, -1 right)."""
    d = v(s * CA, 0, -SA)                       # arm direction
    sh = v(s * 0.17, 0, 1.40)
    el = sh + d * 0.28
    wr = el + d * 0.25
    kn = wr + d * 0.085                         # hand bone end (knuckles)
    n = v(-s * SA, 0, -CA)                      # palm normal (faces the thigh)
    return d, sh, el, wr, kn, n


BONES = []                                      # (name, head, tail, parent)


def bone(name, head, tail, parent):
    BONES.append((name, Vector(head), Vector(tail), parent))


bone("Hips", (0, 0, 0.95), (0, 0, 1.03), None)
bone("Spine", (0, 0, 1.03), (0, 0, 1.15), "Hips")
bone("Spine1", (0, 0, 1.15), (0, 0, 1.27), "Spine")
bone("Spine2", (0, 0, 1.27), (0, 0, 1.43), "Spine1")
bone("Neck", (0, 0, 1.43), (0, 0, 1.52), "Spine2")
bone("Head", (0, 0, 1.52), (0, 0, 1.70), "Neck")
bone("HeadTop_End", (0, 0, 1.70), (0, 0, 1.74), "Head")
bone("Jaw", (0, -0.01, 1.56), (0, -0.085, 1.515), "Head")
bone("LeftEye", (0.038, -0.07, 1.60), (0.038, -0.11, 1.60), "Head")
bone("RightEye", (-0.038, -0.07, 1.60), (-0.038, -0.11, 1.60), "Head")

FINGERS = ["Thumb", "Index", "Middle", "Ring", "Pinky"]
FINGER_HINGE = {}                               # bone -> rest hinge axis (curl toward the palm)
for s, S in ((1, "Left"), (-1, "Right")):
    d, sh, el, wr, kn, n = side_pts(s)
    bone(S + "Shoulder", (s * 0.03, 0, 1.40), sh, "Spine2")
    bone(S + "Arm", sh, el, S + "Shoulder")
    bone(S + "ForeArm", el, wr, S + "Arm")
    bone(S + "Hand", wr, kn, S + "ForeArm")
    for fi, fname in enumerate(FINGERS):
        if fname == "Thumb":
            root = wr + d * 0.02 + F * 0.022 + n * 0.012
            fdir = (d * 0.55 + F * 0.65 + n * 0.25).normalized()
            lens = (0.032, 0.026, 0.022, 0.015)
        else:
            spread = (-0.026, -0.009, 0.009, 0.026)[fi - 1]       # index at the front
            root = kn + v(0, spread, 0)
            fdir = (d + v(0, spread * 2.0, 0)).normalized()
            lens = (0.036, 0.024, 0.019, 0.014) if fname != "Pinky" else (0.028, 0.019, 0.016, 0.012)
        p = root
        parent = S + "Hand"
        for k in range(4):
            name = "%sHand%s%d" % (S, fname, k + 1)
            q = p + fdir * lens[k]
            bone(name, p, q, parent)
            FINGER_HINGE[name] = fdir.cross(n).normalized()
            parent, p = name, q
    hp = v(s * 0.09, 0, 0.93)
    knee = v(s * 0.10, -0.01, 0.50)
    ank = v(s * 0.10, 0.02, 0.085)
    toe = v(s * 0.10, -0.10, 0.02)
    bone(S + "UpLeg", hp, knee, "Hips")
    bone(S + "Leg", knee, ank, S + "UpLeg")
    bone(S + "Foot", ank, toe, S + "Leg")
    bone(S + "ToeBase", toe, toe + v(0, -0.07, 0), S + "Foot")
    bone(S + "Toe_End", toe + v(0, -0.07, 0), toe + v(0, -0.10, 0), S + "ToeBase")


def grip_point(s):
    d, sh, el, wr, kn, n = side_pts(s)
    return wr + d * 0.05 + n * 0.022


BLADE_LEN, HANDLE_BACK, TSUBA = 0.98, 0.17, 0.06
for s, S, X in ((-1, "Right", "R"), (1, "Left", "L")):
    g = grip_point(s)
    bone("Weapon_" + X, g, g + F * 0.25, S + "Hand")
    tip = g + F * (TSUBA + BLADE_LEN)
    bone("WeaponTip_" + X, tip, tip + F * 0.05, "Weapon_" + X)

# ---------------------------------------------------------------- scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.render.fps = FPS

arm_data = bpy.data.armatures.new("ronin_copy_rig")
arm = bpy.data.objects.new("ronin_copy", arm_data)
scn.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
for name, h, t, parent in BONES:
    eb = arm_data.edit_bones.new(name)
    eb.head, eb.tail = h, t
    if parent:
        eb.parent = arm_data.edit_bones[parent]
        eb.use_connect = False
    eb.use_deform = not name.endswith("_End") and not name.endswith("4") and not name.startswith("WeaponTip")
bpy.ops.object.mode_set(mode="OBJECT")

# ---------------------------------------------------------------- materials
COL = {
    "skin": (0.96, 0.80, 0.69), "top": (0.06, 0.15, 0.42), "top_dark": (0.0, 0.07, 0.24),
    "hakama": (0.03, 0.05, 0.15), "sash": (0.90, 0.88, 0.82), "hair": (0.06, 0.06, 0.09),
    "eye": (0.05, 0.10, 0.35), "mouth": (0.35, 0.10, 0.12), "brow": (0.06, 0.06, 0.09),
    "blade": (0.86, 0.90, 0.96), "steel": (0.25, 0.26, 0.30), "handle": (0.05, 0.05, 0.08),
    "gold": (0.80, 0.62, 0.25), "saya": (0.02, 0.04, 0.14), "foot": (0.10, 0.09, 0.10),
}
MATS = {}
for k, c in COL.items():
    m = bpy.data.materials.new("ronin_" + k)
    m.diffuse_color = (c[0], c[1], c[2], 1.0)
    try:
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (c[0], c[1], c[2], 1.0)
            bsdf.inputs["Roughness"].default_value = 0.35 if k == "blade" else 0.8
            if k == "blade":
                bsdf.inputs["Metallic"].default_value = 0.8
    except Exception:
        pass
    MATS[k] = m

# ---------------------------------------------------------------- mesh helpers
PARTS = []          # (object, weights): weights = bone name (rigid) or "auto"


def new_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scn.collection.objects.link(ob)
    return ob


def set_mat(ob, key):
    ob.data.materials.append(MATS[key])


def ellipsoid(name, c, r, mat, rig, segs=24, rings=16, xform=None):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=1.0)
    for vert in bm.verts:
        p = Vector((vert.co.x * r[0], vert.co.y * r[1], vert.co.z * r[2]))
        if xform:
            p = xform(p)
        vert.co = p + Vector(c)
    ob = new_obj(name, bm)
    set_mat(ob, mat)
    PARTS.append((ob, rig))
    return ob


def capsule(name, a, b, ra, rb, mat, rig, segs=12):
    """Tapered tube a->b with domed ends."""
    a, b = Vector(a), Vector(b)
    axis = (b - a)
    L = axis.length
    z = axis.normalized()
    x = z.orthogonal().normalized()
    y = z.cross(x)
    bm = bmesh.new()
    rings = []
    prof = []
    for k in range(4):                                  # bottom dome
        t = (k / 4.0) * (math.pi / 2)
        prof.append((-ra * math.cos(t), ra * math.sin(t)))
    for k in range(5):
        u = k / 4.0
        prof.append((L * u, ra + (rb - ra) * u))
    for k in range(1, 5):
        t = (k / 4.0) * (math.pi / 2)
        prof.append((L + rb * math.sin(t), rb * math.cos(t)))
    for h, rr in prof:
        ring = []
        for j in range(segs):
            ang = 2 * math.pi * j / segs
            p = a + z * h + (x * math.cos(ang) + y * math.sin(ang)) * max(rr, 1e-4)
            ring.append(bm.verts.new(p))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(segs):
            bm.faces.new((r0[j], r0[(j + 1) % segs], r1[(j + 1) % segs], r1[j]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = new_obj(name, bm)
    set_mat(ob, mat)
    PARTS.append((ob, rig))
    return ob


def cone(name, base, tip, r, mat, rig, segs=8, flat=1.0, up=None):
    base, tip = Vector(base), Vector(tip)
    z = (tip - base).normalized()
    x = (up.cross(z) if up is not None else z.orthogonal()).normalized()
    y = z.cross(x)
    bm = bmesh.new()
    ring = [bm.verts.new(base + (x * math.cos(2 * math.pi * j / segs) * r +
                                 y * math.sin(2 * math.pi * j / segs) * r * flat)) for j in range(segs)]
    t = bm.verts.new(tip)
    for j in range(segs):
        bm.faces.new((ring[j], ring[(j + 1) % segs], t))
    bm.faces.new(list(reversed(ring)))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = new_obj(name, bm)
    set_mat(ob, mat)
    PARTS.append((ob, rig))
    return ob


# ---------------------------------------------------------------- body (skin modifier)
SKIN = []   # (point, (rx, ry), material key)
EDGES = []


def sk(p, r, mat):
    SKIN.append((Vector(p), r if isinstance(r, tuple) else (r, r), mat))
    return len(SKIN) - 1


pel = sk((0, 0, 0.93), (0.155, 0.115), "hakama")
wai = sk((0, 0, 1.04), (0.125, 0.090), "top")
bel = sk((0, 0, 1.17), (0.130, 0.090), "top")
che = sk((0, 0, 1.30), (0.150, 0.100), "top")
upc = sk((0, 0, 1.385), (0.135, 0.085), "top")
nb = sk((0, 0, 1.44), (0.052, 0.052), "skin")
nt = sk((0, -0.005, 1.53), (0.044, 0.044), "skin")
EDGES += [(pel, wai), (wai, bel), (bel, che), (che, upc), (upc, nb), (nb, nt)]
for s in (1, -1):
    d, sh, el, wr, kn, n = side_pts(s)
    a0 = sk(sh + v(-s * 0.01, 0, -0.01), 0.058, "top")
    a1 = sk(el, 0.048, "top")
    a2 = sk(el + (wr - el) * 0.72, 0.050, "top_dark")      # sleeve cuff
    a3 = sk(wr, 0.030, "skin")
    EDGES += [(upc, a0), (a0, a1), (a1, a2), (a2, a3)]
    l0 = sk((s * 0.09, 0, 0.90), 0.090, "hakama")
    l1 = sk((s * 0.105, -0.01, 0.50), 0.085, "hakama")
    l2 = sk((s * 0.11, 0.02, 0.125), 0.092, "hakama")          # flared hakama hem
    EDGES += [(pel, l0), (l0, l1), (l1, l2)]

bm = bmesh.new()
vs = [bm.verts.new(p) for p, r, m in SKIN]
for a, b in EDGES:
    bm.edges.new((vs[a], vs[b]))
body = new_obj("body", bm)
mod = body.modifiers.new("skin", "SKIN")
for k, (p, r, m) in enumerate(SKIN):
    sv = body.data.skin_vertices[0].data[k]
    sv.radius = r
    sv.use_root = (k == pel)
sub = body.modifiers.new("sub", "SUBSURF")
sub.levels = 2
bpy.context.view_layer.objects.active = body
for mname in ("skin", "sub"):
    bpy.ops.object.modifier_apply(modifier=mname)
for k in ("top", "top_dark", "hakama", "skin"):
    set_mat(body, k)
MAT_IDX = {"top": 0, "top_dark": 1, "hakama": 2, "skin": 3}
PARTS.append((body, "auto"))

# head + face
HC, HR = v(0, -0.005, 1.605), (0.098, 0.108, 0.122)


def head_shape(p):
    if p.z < 0:                                 # narrower anime jaw, chin forward
        k = 1.0 + p.z / HR[2] * 0.38
        p = Vector((p.x * k, p.y * (1.0 + p.z / HR[2] * 0.12) - (p.z / HR[2]) ** 2 * 0.012, p.z * 1.05))
    return p


ellipsoid("head", HC, HR, "skin", "Head", segs=28, rings=20, xform=head_shape)


def face_y(x, z):
    """Front surface y of the head at (x, z) (pre-jaw shape is fine above the chin)."""
    u = 1.0 - (x / HR[0]) ** 2 - ((z - HC.z) / HR[2]) ** 2
    return HC.y - HR[1] * math.sqrt(max(u, 0.02))


# eyes + mouth: one mesh, with shape keys (spec: Blink_L / Blink_R / Mouth_Open + optional ones)
fbm = bmesh.new()
FACE_GROUPS = {"LeftEye": [], "RightEye": [], "Jaw": [], "Head": []}


def disc(cx, cz, rx, rz, group, segs=16, push=0.004):
    cy = face_y(cx, cz) - push
    c = fbm.verts.new((cx, cy, cz))
    ring = []
    for j in range(segs):
        ang = 2 * math.pi * j / segs
        x, z = cx + math.cos(ang) * rx, cz + math.sin(ang) * rz
        ring.append(fbm.verts.new((x, face_y(x, z) - push, z)))
    for j in range(segs):
        fbm.faces.new((c, ring[(j + 1) % segs], ring[j]))
    FACE_GROUPS[group] += [c] + ring


disc(0.038, 1.598, 0.020, 0.027, "LeftEye")
disc(-0.038, 1.598, 0.020, 0.027, "RightEye")
disc(0.0, 1.528, 0.012, 0.0035, "Jaw", push=0.003)
for s in (1, -1):                                   # brows (thin slanted bars)
    a = fbm.verts.new((s * 0.022, face_y(s * 0.022, 1.637) - 0.004, 1.635))
    b2 = fbm.verts.new((s * 0.060, face_y(s * 0.060, 1.645) - 0.004, 1.645))
    c2 = fbm.verts.new((s * 0.060, face_y(s * 0.060, 1.652) - 0.004, 1.652))
    d2 = fbm.verts.new((s * 0.022, face_y(s * 0.022, 1.643) - 0.004, 1.643))
    fbm.faces.new((a, b2, c2, d2) if s > 0 else (d2, c2, b2, a))
    FACE_GROUPS["Head"] += [a, b2, c2, d2]
for f in fbm.faces:
    if f.normal.y > 0:
        f.normal_flip()
fbm.verts.index_update()
idx_groups = {g: [vv.index for vv in vl] for g, vl in FACE_GROUPS.items()}
face = new_obj("face", fbm)
set_mat(face, "eye")
set_mat(face, "mouth")
set_mat(face, "brow")
for poly in face.data.polygons:
    vi = poly.vertices[0]
    poly.material_index = 1 if vi in idx_groups["Jaw"] else (2 if vi in idx_groups["Head"] else 0)
PARTS.append((face, idx_groups))

# shape keys
face.shape_key_add(name="Basis")


def add_key(name, fn):
    k = face.shape_key_add(name=name)
    for vi, vert in enumerate(face.data.vertices):
        k.data[vi].co = fn(vi, Vector(vert.co))


def squash(group, cz, amount, offset=0.0, sx=1.0):
    ids = set(idx_groups[group])

    def fn(vi, p):
        if vi in ids:
            cx = 0.038 if group == "LeftEye" else (-0.038 if group == "RightEye" else 0.0)
            return Vector((cx + (p.x - cx) * sx, p.y, cz + (p.z - cz) * amount + offset))
        return p
    return fn


add_key("Blink_L", squash("LeftEye", 1.592, 0.08))
add_key("Blink_R", squash("RightEye", 1.592, 0.08))
add_key("Mouth_Open", squash("Jaw", 1.524, 4.5, sx=0.85))
add_key("Mouth_Smile", squash("Jaw", 1.530, 0.6, sx=1.35))
add_key("Eyes_Wide", lambda vi, p: (squash("LeftEye", 1.598, 1.25, sx=1.1)(vi, p) if vi in idx_groups["LeftEye"]
                                    else squash("RightEye", 1.598, 1.25, sx=1.1)(vi, p)))
brow_ids = set(idx_groups["Head"])
add_key("Brow_Angry", lambda vi, p: Vector((p.x, p.y, p.z - (0.012 if abs(p.x) < 0.03 else 0.0)))
        if vi in brow_ids else p)
add_key("Brow_Up", lambda vi, p: Vector((p.x, p.y, p.z + 0.010)) if vi in brow_ids else p)

# hair: cap + bangs + spikes + ponytail (all rigid to Head)


cap = ellipsoid("hair_cap", HC + v(0, 0.006, 0.012), (0.106, 0.116, 0.126), "hair", "Head", segs=28, rings=20)
bm = bmesh.new()
bm.from_mesh(cap.data)
kill = [vv for vv in bm.verts if (vv.co.z < 1.655 and vv.co.y < -0.02) or vv.co.z < 1.545 or
        (vv.co.z < 1.60 and abs(vv.co.x) > 0.06 and vv.co.y < 0.03)]
bmesh.ops.delete(bm, geom=kill, context="VERTS")
bm.to_mesh(cap.data)
bm.free()
cap.modifiers.new("solid", "SOLIDIFY").thickness = 0.008
for k, (x, z0, ln, tilt) in enumerate(((-0.07, 1.68, 0.10, -0.25), (-0.035, 1.70, 0.12, -0.1), (0.0, 1.705, 0.11, 0.05),
                                       (0.04, 1.70, 0.12, 0.15), (0.075, 1.68, 0.095, 0.3))):
    y0 = face_y(x, z0) - 0.004
    cone("bang%d" % k, (x, y0 + 0.02, z0), (x + tilt * 0.05, y0 - 0.025, z0 - ln), 0.024, "hair", "Head",
         flat=0.45, up=F)
for k, (x, z, dx, dy, dz) in enumerate(((0.0, 1.725, 0.0, 0.20, 0.03), (-0.065, 1.69, -0.06, 0.16, -0.02),
                                        (0.065, 1.69, 0.06, 0.16, -0.02), (-0.035, 1.715, -0.04, 0.19, 0.01),
                                        (0.035, 1.715, 0.04, 0.19, 0.01), (-0.08, 1.64, -0.05, 0.12, -0.07),
                                        (0.08, 1.64, 0.05, 0.12, -0.07))):
    cone("spike%d" % k, (x, -0.01, z - 0.02), (x + dx, 0.0 + dy, z + dz), 0.04, "hair", "Head", flat=0.5, up=U)
cone("ponytail", (0, 0.095, 1.67), (0, 0.33, 1.47), 0.040, "hair", "Head", segs=10)
capsule("tie", (0, 0.085, 1.68), (0, 0.115, 1.665), 0.022, 0.022, "sash", "Head", segs=10)

# sash + collar (rigid parts on the torso)
bm = bmesh.new()
bmesh.ops.create_cone(bm, cap_ends=False, segments=28, radius1=0.135, radius2=0.128, depth=0.07)
for vv in bm.verts:
    vv.co = Vector((vv.co.x, vv.co.y * 0.75, vv.co.z + 1.00))
sash = new_obj("sash", bm)
sash.modifiers.new("solid", "SOLIDIFY").thickness = 0.01
set_mat(sash, "sash")
PARTS.append((sash, "Hips"))
for s in (1, -1):                                   # kimono collar: two crossing bands
    capsule("collar%d" % (s > 0), (s * 0.058, -0.035, 1.435), (-s * 0.012, -0.098, 1.13), 0.014, 0.012,
            "sash", "Spine2", segs=8)

# hands (palm) + fingers + feet
for s, S in ((1, "Left"), (-1, "Right")):
    d, sh, el, wr, kn, n = side_pts(s)
    side = F

    def palm_x(p, d=d, n=n, wr=wr):
        # local frame: x = across the palm (front-back), y = palm normal, z = hand direction
        return wr + d * (0.045 + p.z) + n * p.y + side * p.x
    ellipsoid(S + "_palm", (0, 0, 0), (0.042, 0.016, 0.050), "skin", S + "Hand", segs=16, rings=10, xform=palm_x)
    for fname in FINGERS:
        for k in range(3):
            bname = "%sHand%s%d" % (S, fname, k + 1)
            bh = [b for b in BONES if b[0] == bname][0]
            r = (0.0115 if fname == "Thumb" else 0.0095) * (1.0 - 0.12 * k)
            capsule(bname + "_m", bh[1], bh[2] + (bh[2] - bh[1]).normalized() * (0.006 if k == 2 else 0.0),
                    r, r * 0.92, "skin", bname, segs=8)
    ank = v(s * 0.10, 0.02, 0.085)
    capsule(S + "_ankle", ank + v(0, -0.004, 0.0), ank + v(0, -0.002, 0.16), 0.036, 0.040, "foot",
            S + "Leg", segs=10)                     # tabi: visible ankle inside the wide hem
    ellipsoid(S + "_foot", (s * 0.10, -0.045, 0.045), (0.048, 0.118, 0.048), "foot",
              {"bones": [S + "Foot", S + "ToeBase"]}, segs=16, rings=10)

# katana (Weapon_R)
g = grip_point(-1)
bm = bmesh.new()
W, T = 0.016, 0.004                                  # half width / half thickness
up = U                                               # spine of the blade up, edge down
pts = []
for k in range(9):
    u = k / 8.0
    p = g + F * (TSUBA + 0.01 + BLADE_LEN * u) + up * (0.03 * u * u)     # slight curve (sori)
    w = W * (1.0 - 0.25 * u)
    pts.append((p, w))
rows = []
for p, w in pts:
    rows.append([bm.verts.new(p + up * w), bm.verts.new(p + v(T, 0, 0)), bm.verts.new(p - up * w),
                 bm.verts.new(p - v(T, 0, 0))])
for r0, r1 in zip(rows, rows[1:]):
    for j in range(4):
        bm.faces.new((r0[j], r0[(j + 1) % 4], r1[(j + 1) % 4], r1[j]))
tipv = bm.verts.new(pts[-1][0] + F * 0.05 + up * 0.012)
for j in range(4):
    bm.faces.new((rows[-1][j], rows[-1][(j + 1) % 4], tipv))
bm.faces.new(list(reversed(rows[0])))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
blade = new_obj("blade", bm)
set_mat(blade, "blade")
PARTS.append((blade, "Weapon_R"))
capsule("handle", g - F * HANDLE_BACK, g + F * TSUBA, 0.016, 0.017, "handle", "Weapon_R", segs=8)
tsuba = capsule("tsuba", g + F * (TSUBA - 0.004), g + F * (TSUBA + 0.008), 0.038, 0.038, "gold", "Weapon_R", segs=14)

# ---------------------------------------------------------------- weights
DEFORM_BODY = ["Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftShoulder", "LeftArm", "LeftForeArm",
               "LeftHand", "RightShoulder", "RightArm", "RightForeArm", "RightHand", "LeftUpLeg", "LeftLeg",
               "LeftFoot", "RightUpLeg", "RightLeg", "RightFoot"]
BINFO = {b[0]: b for b in BONES}
CHILDREN = {}
for name, h, t, parent in BONES:
    CHILDREN.setdefault(parent, []).append(name)


def seg_dist(P, a, b):
    a, b = np.array(a), np.array(b)
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0.0, 1.0)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def weight_auto(ob):
    P = np.array([vv.co[:] for vv in ob.data.vertices])
    dist = np.stack([seg_dist(P, BINFO[n][1], BINFO[n][2]) for n in DEFORM_BODY], axis=1)
    near = dist.argmin(axis=1)
    groups = {n: ob.vertex_groups.new(name=n) for n in DEFORM_BODY}
    for vi in range(len(P)):
        nb = DEFORM_BODY[near[vi]]
        cands = [nb] + ([BINFO[nb][3]] if BINFO[nb][3] in groups else []) + \
                [c for c in CHILDREN.get(nb, []) if c in groups]
        ds = np.array([dist[vi, DEFORM_BODY.index(c)] for c in cands])
        w = 1.0 / np.maximum(ds, 0.004) ** 5
        order = np.argsort(-w)[:3]
        w = w[order] / w[order].sum()
        for c, ww in zip([cands[o] for o in order], w):
            if ww > 0.02:
                groups[c].add([vi], float(ww), "REPLACE")
    # material by the nearest bone (+ the skin / sleeve rings set on the skin graph)
    for poly in ob.data.polygons:
        c = np.array(poly.center[:])
        nb = DEFORM_BODY[int(np.argmin([seg_dist(c[None], BINFO[n][1], BINFO[n][2])[0] for n in DEFORM_BODY]))]
        if nb in ("Neck", "Head"):
            key = "skin"
        elif nb.endswith("Hand"):
            key = "skin"
        elif nb.endswith("ForeArm"):
            s = 1 if nb.startswith("Left") else -1
            _, _, el, wr, _, _ = side_pts(s)
            t = (Vector(c) - el).dot((wr - el).normalized()) / (wr - el).length
            key = "skin" if t > 0.80 else ("top_dark" if t > 0.55 else "top")
        elif nb in ("Hips",) or "Leg" in nb or "Foot" in nb:
            key = "hakama" if c[2] < 1.0 else "top"
        else:
            key = "top"
        poly.material_index = MAT_IDX[key]


meshes = []
for ob, rig in PARTS:
    bpy.context.view_layer.objects.active = ob
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)
    if rig == "auto":
        weight_auto(ob)
    elif isinstance(rig, str):
        ob.vertex_groups.new(name=rig).add(list(range(len(ob.data.vertices))), 1.0, "REPLACE")
    elif "bones" in rig:                                  # foot: split heel / toe along y
        b0, b1 = rig["bones"]
        g0, g1 = ob.vertex_groups.new(name=b0), ob.vertex_groups.new(name=b1)
        for vv in ob.data.vertices:
            t = min(max((-vv.co.y - 0.06) / 0.06, 0.0), 1.0)
            if t < 1:
                g0.add([vv.index], 1.0 - t, "REPLACE")
            if t > 0:
                g1.add([vv.index], t, "REPLACE")
    else:                                                 # face: per-group bones
        for gname, ids in rig.items():
            ob.vertex_groups.new(name=gname).add(ids, 1.0, "REPLACE")
    meshes.append(ob)

# join everything except the face (keeps its shape keys on a small mesh) into one body mesh
bpy.ops.object.select_all(action="DESELECT")
rest = [m for m in meshes if m is not face]
for m in rest:
    m.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
body.name = "ronin_copy_body"
face.name = "ronin_copy_face"
for ob in (body, face):
    ob.parent = arm
    am = ob.modifiers.new("Armature", "ARMATURE")
    am.object = arm
    for poly in ob.data.polygons:
        poly.use_smooth = True

# ---------------------------------------------------------------- posing
REST = {b.name: b.matrix_local.copy() for b in arm_data.bones}
ORDER = []


def walk(b):
    ORDER.append(b.name)
    for c in b.children:
        walk(c)


for b in arm_data.bones:
    if b.parent is None:
        walk(b)


def frame_of(d, ref):
    d = d.normalized()
    r = (ref - d * ref.dot(d))
    if r.length < 1e-6:
        r = d.orthogonal()
    r.normalize()
    return Matrix((d, r, d.cross(r))).transposed()


def solve(pose):
    """pose: bone -> dict(aim=vec, ref=(rest_vec, target_vec), rot=(x,y,z deg), curl=deg, loc=vec)."""
    posed, basis = {}, {}
    for name in ORDER:
        R0 = REST[name]
        par = arm_data.bones[name].parent
        if par:
            P, P0 = posed[par.name], REST[par.name]
            inh = P @ P0.inverted() @ R0
        else:
            inh = R0.copy()
        spec = pose.get(name)
        M = inh
        if spec:
            head = inh.to_translation()
            rot = inh.to_3x3()
            if "aim" in spec:
                d0 = (R0.to_3x3() @ Vector((0, 1, 0))).normalized()
                d1 = Vector(spec["aim"]).normalized()
                if "blade" in spec:                     # weapon hand: blade exact, hand direction second
                    A = frame_of(Vector(spec["blade"]), d1) @ frame_of(REST_BLADE, d0).inverted()
                elif "ref" in spec:
                    r0, r1 = Vector(spec["ref"][0]), Vector(spec["ref"][1])
                    A = frame_of(d1, r1) @ frame_of(d0, r0).inverted()
                else:
                    A = d0.rotation_difference(d1).to_matrix()
                rot = A @ R0.to_3x3()
            if "rot" in spec:
                rot = Euler([math.radians(a) for a in spec["rot"]], "XYZ").to_matrix() @ rot
            if "curl" in spec and name in FINGER_HINGE:
                ax = (rot @ R0.to_3x3().inverted()) @ FINGER_HINGE[name]
                rot = Matrix.Rotation(math.radians(spec["curl"]), 3, ax.normalized()) @ rot
            if "loc" in spec:
                head = head + Vector(spec["loc"])
            M = Matrix.Translation(head) @ rot.to_4x4()
        posed[name] = M
        if par:
            local_rest = REST[par.name].inverted() @ R0
            basis[name] = local_rest.inverted() @ posed[par.name].inverted() @ M
        else:
            basis[name] = R0.inverted() @ M
    return basis


def fist(S, amt=85, thumb=45):
    p = {}
    for fname in FINGERS:
        for k in range(3):
            a = thumb * (0.6 + 0.2 * k) if fname == "Thumb" else amt * (0.9 if k == 0 else 1.0)
            p["%sHand%s%d" % (S, fname, k + 1)] = {"curl": a}
    return p


def merge(*ds):
    out = {}
    for d in ds:
        for k, val in d.items():
            out.setdefault(k, {}).update(val)
    return out


REST_BLADE = F


def hand(S, d, blade=None):
    if blade is None:
        return {S + "Hand": {"aim": d}}
    return {S + "Hand": {"aim": d, "blade": Vector(blade)}}


def leg(S, thigh, shin, foot=(0, -1, -0.35)):
    return {S + "UpLeg": {"aim": thigh}, S + "Leg": {"aim": shin}, S + "Foot": {"aim": foot},
            S + "ToeBase": {"aim": (0, -1, 0)}}


def arm_(S, up, fore):
    return {S + "Arm": {"aim": up}, S + "ForeArm": {"aim": fore}}


def torso(hips=(0, 0, 0), loc=(0, 0, 0), spine=(0, 0, 0), chest=(0, 0, 0), head=(0, 0, 0), neck=(0, 0, 0)):
    return {"Hips": {"rot": hips, "loc": loc}, "Spine": {"rot": spine}, "Spine1": {"rot": spine},
            "Spine2": {"rot": chest}, "Neck": {"rot": neck}, "Head": {"rot": head}}


GRIP = fist("Right", 88, 50)
LOOSE_L = fist("Left", 22, 15)

# ---------------------------------------------------------------- poses
IDLE_A = merge(
    torso(hips=(0, 0, 12), loc=(0, 0, -0.035), spine=(4, 0, -3), chest=(3, 0, -4), head=(-4, 0, -6)),
    leg("Left", (0.10, -0.22, -1), (0.06, 0.05, -1), (0.25, -1, -0.3)),
    leg("Right", (-0.12, 0.12, -1), (-0.06, 0.30, -1), (-0.3, -1, -0.3)),
    arm_("Right", (-0.30, 0.10, -1), (-0.22, -0.25, -1)), hand("Right", (-0.12, -0.30, -1), (-0.25, 0.85, -0.45)),
    arm_("Left", (0.28, -0.02, -1), (0.15, -0.30, -1)), hand("Left", (0.10, -0.25, -1)),
    GRIP, LOOSE_L)
IDLE_B = merge(IDLE_A, torso(hips=(0, 0, 12), loc=(0, 0, -0.045), spine=(6, 0, -3), chest=(1, 0, -4),
                             head=(-2, 0, -6)),
               arm_("Left", (0.29, -0.04, -1), (0.16, -0.34, -1)))


def run_pose(phase):
    """phase 0 = left foot contact, 1 = passing (left support), mirrored by swap."""
    def legs(lead, trail, contact):
        if contact:
            return merge(leg(lead, (0.02, -0.62, -0.78), (0.0, -0.12, -1), (0, -1, -0.15)),
                         leg(trail, (0.0, 0.55, -0.83), (0.0, 0.95, -0.35), (0, 0.4, -1)))
        return merge(leg(lead, (0.0, 0.12, -1), (0.0, 0.45, -0.9), (0, -1, -0.5)),
                     leg(trail, (0.0, -0.75, -0.65), (0.0, 0.35, -0.95), (0, -0.6, -1)))
    lead, trail = ("Left", "Right") if phase in (0, 1) else ("Right", "Left")
    contact = phase in (0, 2)
    lz = -0.06 if contact else -0.0
    sw = 1 if lead == "Left" else -1                       # left leg forward -> left arm back
    p = merge(torso(hips=(0, 0, -8 * sw), loc=(0, 0, lz), spine=(10, 0, 4 * sw), chest=(8, 0, 6 * sw),
                    head=(-14, 0, -4 * sw)),
              legs(lead, trail, contact),
              arm_("Right", (-0.28, 0.65, -0.72), (-0.22, 0.75, -0.55)),
              hand("Right", (-0.15, 0.75, -0.6), (-0.12, 0.97, 0.12)),
              GRIP, fist("Left", 60, 40))
    if sw > 0:
        p = merge(p, arm_("Left", (0.18, 0.55, -0.82), (0.12, -0.10, -1)), hand("Left", (0.1, -0.4, -1)))
    else:
        p = merge(p, arm_("Left", (0.18, -0.55, -0.80), (0.05, -1, 0.35)), hand("Left", (0.05, -1, 0.1)))
    if not contact:
        p = merge(p, {"Left" + "Arm": {"aim": (0.22, 0.0, -1)}, "LeftForeArm": {"aim": (0.10, -0.6, -0.7)}})
    return p


AN_WIND = merge(
    torso(hips=(0, 0, -28), loc=(0, 0.05, -0.02), spine=(-6, 0, -10), chest=(-6, 0, -12), head=(0, 0, 30)),
    leg("Left", (0.12, -0.35, -1), (0.05, 0.05, -1), (0.25, -1, -0.3)),
    leg("Right", (-0.10, 0.25, -1), (-0.05, 0.35, -1), (-0.3, -1, -0.2)),
    arm_("Right", (-0.35, 0.25, 0.9), (-0.05, 0.55, 0.75)), hand("Right", (0.05, 0.75, 0.6), (0.25, 0.55, -0.80)),
    arm_("Left", (0.35, -0.75, -0.35), (0.2, -0.9, 0.1)), hand("Left", (0.1, -1, 0.15)),
    GRIP, fist("Left", 10, 10))
AN_STRIKE = merge(
    torso(hips=(0, 0, 18), loc=(0, -0.16, -0.14), spine=(14, 0, 8), chest=(12, 0, 10), head=(-20, 0, -12)),
    leg("Left", (0.12, -0.85, -0.5), (0.05, -0.05, -1), (0.1, -1, -0.2)),
    leg("Right", (-0.06, 0.70, -0.70), (-0.05, 0.90, -0.45), (0, 0.3, -1)),
    arm_("Right", (-0.30, -0.90, -0.05), (-0.15, -1, -0.25)), hand("Right", (-0.05, -1, -0.35), (0.55, -0.6, -0.55)),
    arm_("Left", (0.45, 0.4, -0.7), (0.3, 0.6, -0.6)), hand("Left", (0.2, 0.6, -0.7)),
    GRIP, fist("Left", 30, 20))
AN_FOLLOW = merge(
    torso(hips=(0, 0, 30), loc=(0, -0.18, -0.24), spine=(18, 0, 12), chest=(14, 0, 14), head=(-26, 0, -28)),
    leg("Left", (0.15, -0.95, -0.3), (0.05, -0.05, -1), (0.1, -1, -0.1)),
    leg("Right", (-0.08, 0.80, -0.55), (-0.05, 0.95, -0.2), (0, 0.2, -1)),
    arm_("Right", (0.25, -0.85, -0.45), (0.65, -0.35, -0.65)), hand("Right", (0.70, 0.15, -0.65), (0.45, 0.85, -0.10)),
    arm_("Left", (0.50, 0.55, -0.6), (0.35, 0.7, -0.4)), hand("Left", (0.2, 0.8, -0.5)),
    GRIP, fist("Left", 30, 20))
AN_END = merge(AN_FOLLOW, torso(hips=(0, 0, 26), loc=(0, -0.10, -0.18), spine=(12, 0, 10), chest=(10, 0, 12),
                                head=(-18, 0, -24)))

AS_COIL = merge(
    torso(hips=(0, 0, 35), loc=(0, 0.06, -0.24), spine=(20, 0, 10), chest=(14, 0, 14), head=(-30, 0, -40)),
    leg("Left", (0.30, -0.65, -0.70), (0.10, 0.25, -1), (0.2, -1, -0.2)),
    leg("Right", (-0.25, 0.45, -0.85), (-0.05, 0.85, -0.55), (-0.2, 0.1, -1)),
    arm_("Right", (0.30, -0.55, -0.70), (0.85, 0.05, -0.45)), hand("Right", (0.85, 0.40, -0.25), (-0.35, 0.80, 0.50)),
    arm_("Left", (0.35, -0.25, -0.85), (0.1, -0.4, -0.85)), hand("Left", (0.0, -0.2, -1)),
    GRIP, fist("Left", 70, 40))
AS_RELEASE = merge(
    torso(hips=(0, 0, -10), loc=(0, -0.22, -0.26), spine=(18, 0, -10), chest=(12, 0, -16), head=(-24, 0, 10)),
    leg("Left", (0.15, -0.95, -0.30), (0.05, -0.05, -1), (0.1, -1, -0.1)),
    leg("Right", (-0.10, 0.85, -0.45), (-0.05, 0.99, -0.1), (0, 0.3, -1)),
    arm_("Right", (-0.75, -0.65, 0.05), (-0.9, -0.35, 0.05)), hand("Right", (-0.95, -0.1, 0.0), (-0.20, -0.95, 0.05)),
    arm_("Left", (0.55, 0.55, -0.5), (0.4, 0.75, -0.3)), hand("Left", (0.2, 0.8, -0.4)),
    GRIP, fist("Left", 40, 20))
AS_FOLLOW = merge(
    torso(hips=(0, 0, -22), loc=(0, -0.26, -0.28), spine=(18, 0, -14), chest=(12, 0, -20), head=(-24, 0, 26)),
    leg("Left", (0.15, -0.95, -0.30), (0.05, -0.05, -1), (0.1, -1, -0.1)),
    leg("Right", (-0.10, 0.88, -0.42), (-0.05, 0.99, -0.05), (0, 0.3, -1)),
    arm_("Right", (-0.85, 0.35, 0.05), (-0.55, 0.85, 0.05)), hand("Right", (-0.3, 0.95, 0.0), (0.05, 0.99, 0.10)),
    arm_("Left", (0.55, 0.35, -0.6), (0.3, -0.5, -0.8)), hand("Left", (0.2, -0.5, -0.8)),
    GRIP, fist("Left", 40, 20))

U_STANCE = merge(
    torso(hips=(0, 0, 20), loc=(0, 0.02, -0.20), spine=(4, 0, 4), chest=(2, 0, 6), head=(-6, 0, -18)),
    leg("Left", (0.45, -0.45, -0.80), (0.20, 0.0, -1), (0.35, -1, -0.2)),
    leg("Right", (-0.45, 0.30, -0.85), (-0.25, 0.30, -1), (-0.4, -1, -0.1)),
    arm_("Right", (-0.55, -0.10, 0.80), (0.20, -0.20, 0.95)), hand("Right", (0.40, -0.10, 0.90), (-0.30, 0.85, 0.35)),
    arm_("Left", (0.55, -0.55, 0.40), (-0.20, -0.30, 0.95)), hand("Left", (-0.5, 0.0, 0.85)),
    GRIP, fist("Left", 80, 40))
U_AIM = merge(U_STANCE,
              torso(hips=(0, 0, 30), loc=(0, 0.03, -0.24), spine=(6, 0, 8), chest=(4, 0, 10), head=(-8, 0, -26)),
              arm_("Right", (-0.60, 0.25, 0.30), (0.55, -0.20, 0.25)), hand("Right", (0.70, -0.60, 0.05),
                                                                              (0.10, -0.99, 0.05)),
              arm_("Left", (0.45, -0.85, 0.10), (-0.10, -0.90, 0.20)), hand("Left", (-0.30, -0.9, 0.0)))


def u_slash(dirn):
    """dirn 1 = down-left diagonal, 2 = up-right diagonal, 3 = flat sweep."""
    b = {1: (0.70, -0.40, -0.60), 2: (-0.70, -0.40, 0.60), 3: (0.95, 0.20, 0.0)}[dirn]
    up = {1: (-0.20, -0.95, -0.10), 2: (-0.90, -0.40, 0.25), 3: (0.30, -0.95, -0.05)}[dirn]
    fo = {1: (0.30, -0.95, -0.30), 2: (-0.60, -0.70, 0.30), 3: (0.75, -0.65, 0.05)}[dirn]
    hd = {1: (0.55, -0.70, -0.45), 2: (-0.65, -0.55, 0.50), 3: (0.95, -0.25, 0.0)}[dirn]
    tw = {1: 25, 2: -20, 3: 35}[dirn]
    return merge(U_STANCE,
                 torso(hips=(0, 0, tw), loc=(0, -0.12, -0.22), spine=(12, 0, tw * 0.4), chest=(10, 0, tw * 0.5),
                       head=(-14, 0, -tw)),
                 leg("Left", (0.40, -0.75, -0.55), (0.15, -0.05, -1), (0.3, -1, -0.1)),
                 arm_("Right", up, fo), hand("Right", hd, b),
                 arm_("Left", (0.6, 0.35, -0.6), (0.4, 0.6, -0.5)), hand("Left", (0.2, 0.8, -0.5)),
                 fist("Left", 40, 20))


U_ZANSHIN = merge(
    torso(hips=(0, 0, 6), loc=(0, 0, -0.02), spine=(2, 0, -2), chest=(-2, 0, -2), head=(4, 0, -8)),
    leg("Left", (0.06, -0.10, -1), (0.04, 0.05, -1), (0.2, -1, -0.3)),
    leg("Right", (-0.06, 0.08, -1), (-0.04, 0.12, -1), (-0.2, -1, -0.3)),
    arm_("Right", (-0.25, -0.05, -1), (-0.20, -0.35, -1)), hand("Right", (-0.10, -0.25, -1), (-0.15, 0.88, -0.45)),
    arm_("Left", (0.22, 0.0, -1), (0.12, -0.2, -1)), hand("Left", (0.05, -0.2, -1)),
    GRIP, LOOSE_L)

HIT = merge(IDLE_A,
            torso(hips=(-4, 0, 18), loc=(0, 0.08, -0.06), spine=(-5, 0, 6), chest=(-6, 0, 8), head=(-12, 0, 10),
                  neck=(-6, 0, 0)),
            arm_("Right", (-0.55, 0.40, -0.65), (-0.45, 0.65, -0.5)), hand("Right", (-0.3, 0.8, -0.5),
                                                                          (-0.2, 0.7, 0.65)),
            arm_("Left", (0.65, 0.20, -0.55), (0.45, -0.35, -0.65)), hand("Left", (0.3, -0.4, -0.7)),
            leg("Right", (-0.12, 0.28, -1), (-0.06, 0.45, -1), (-0.3, -1, -0.2)),
            fist("Left", 5, 5))

KO_RECOIL = merge(HIT, torso(hips=(-8, 0, 10), loc=(0, 0.12, -0.08), spine=(-8, 0, 4), chest=(-8, 0, 4),
                             head=(-16, 0, 6), neck=(-8, 0, 0)))
KO_BUCKLE = merge(KO_RECOIL,
                  torso(hips=(-20, 0, 6), loc=(0, 0.20, -0.42), spine=(-6, 0, 2), chest=(-6, 0, 2), head=(-12, 0, 4)),
                  leg("Left", (0.15, -0.75, -0.65), (0.05, 0.6, -0.8), (0.2, -0.6, -0.8)),
                  leg("Right", (-0.15, -0.55, -0.80), (-0.05, 0.75, -0.65), (-0.2, -0.6, -0.8)),
                  arm_("Right", (-0.75, 0.30, -0.20), (-0.60, 0.55, -0.40)),
                  hand("Right", (-0.5, 0.6, -0.5), (-0.4, 0.6, -0.65)))
KO_FALL = merge(KO_BUCKLE,
                torso(hips=(-68, 0, 4), loc=(0, 0.38, -0.66), spine=(-6, 0, 0), chest=(-4, 0, 0), head=(-10, 0, 0)),
                leg("Left", (0.20, -0.95, -0.15), (0.08, -0.60, -0.80), (0.2, -0.2, -1)),
                leg("Right", (-0.20, -0.90, -0.05), (-0.08, -0.95, -0.25), (-0.2, -0.8, 0.5)),
                arm_("Right", (-0.95, 0.25, 0.25), (-0.85, 0.35, 0.40)), hand("Right", (-0.8, 0.4, 0.3),
                                                                               (-0.3, 0.95, 0.0)),
                arm_("Left", (0.95, 0.20, 0.25), (0.85, 0.40, 0.30)), hand("Left", (0.8, 0.5, 0.2)))
KO_DOWN = merge(KO_FALL,
                torso(hips=(-88, 0, 2), loc=(0, 0.46, -0.80), spine=(-2, 0, 0), chest=(0, 0, 0), head=(10, 0, -25),
                      neck=(0, 0, 0)),
                leg("Left", (0.22, -0.98, 0.02), (0.10, -0.99, 0.10), (0.25, -0.1, 1)),
                leg("Right", (-0.25, -0.97, 0.0), (-0.12, -0.99, 0.0), (-0.3, -0.1, 1)),
                arm_("Right", (-0.95, 0.30, -0.02), (-0.85, 0.50, -0.02)), hand("Right", (-0.7, 0.7, -0.05),
                                                                                (-0.55, 0.80, -0.05)),
                arm_("Left", (0.95, 0.25, -0.02), (0.80, 0.60, -0.02)), hand("Left", (0.6, 0.8, -0.05)),
                fist("Right", 40, 30), fist("Left", 15, 10))
KO_BOUNCE = merge(KO_DOWN, torso(hips=(-84, 0, 2), loc=(0, 0.46, -0.76), head=(4, 0, -25)))


def shake(pose, k, amt=1.2):
    """Small seeded tremble on the sword arm + head (charge holds)."""
    rnd = np.random.default_rng(1000 + k)
    j = lambda: tuple(float(x) for x in rnd.normal(0, amt, 3))
    return merge(pose, {"RightForeArm": {"rot": j()}, "Spine2": {"rot": j()}})


CLIPS = {
    "idle": [(0, IDLE_A), (15, IDLE_B), (30, IDLE_A)],
    "run": [(0, run_pose(0)), (5, run_pose(1)), (10, run_pose(2)), (15, run_pose(3)), (20, run_pose(0))],
    "attack_normal": [(0, IDLE_A), (4, AN_WIND), (6, AN_WIND), (8, AN_STRIKE), (10, AN_FOLLOW), (15, AN_END)],
    "attack_special": [(0, IDLE_A), (6, AS_COIL), (11, AS_COIL), (13, AS_RELEASE), (16, AS_FOLLOW), (24, AS_FOLLOW)],
    "ultimate": ([(0, IDLE_A), (12, U_STANCE)] +
                 [(15 + 3 * k, shake(U_STANCE, k)) for k in range(9)] +
                 [(46, U_AIM)] + [(49 + 3 * k, shake(U_AIM, 50 + k, 0.9)) for k in range(9)] +
                 [(78, U_AIM), (81, u_slash(1)), (84, u_slash(2)), (88, u_slash(3)), (92, u_slash(3)),
                  (104, U_ZANSHIN), (120, U_ZANSHIN)]),
    "hit_light": [(0, IDLE_A), (3, HIT), (12, IDLE_A)],
    "ko": [(0, IDLE_A), (3, KO_RECOIL), (10, KO_BUCKLE), (18, KO_FALL), (24, KO_DOWN), (28, KO_BOUNCE),
           (32, KO_DOWN), (36, KO_DOWN)],
}
LOOPS = {"idle", "run"}

arm.animation_data_create()
arm.rotation_mode = "XYZ"
for pb in arm.pose.bones:
    pb.rotation_mode = "QUATERNION"

for cname, keys in CLIPS.items():
    act = bpy.data.actions.new(cname)
    act.use_fake_user = True
    arm.animation_data.action = act
    prev = {}
    for fr, pose in keys:
        basis = solve(pose)
        for pb in arm.pose.bones:
            m = basis[pb.name]
            loc, q, _ = m.decompose()
            if pb.name in prev and prev[pb.name].dot(q) < 0:
                q.negate()
            prev[pb.name] = q.copy()
            pb.location = loc if pb.name == "Hips" else Vector((0, 0, 0))
            pb.rotation_quaternion = q
            pb.keyframe_insert("location", frame=fr, group=pb.name)
            pb.keyframe_insert("rotation_quaternion", frame=fr, group=pb.name)
    try:
        act.use_frame_range = True
        act.frame_range = (keys[0][0], keys[-1][0])
        act.use_cyclic = cname in LOOPS
    except Exception:
        pass

# ---------------------------------------------------------------- export
for kb in face.data.shape_keys.key_blocks[1:]:      # new keys can come in at 1.0: export them all at rest
    kb.value = 0.0
arm.animation_data.action = bpy.data.actions["idle"]
scn.frame_set(0)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.object.select_all(action="DESELECT")
for ob in (arm, body, face):
    ob.select_set(True)
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format="GLB", use_selection=True, export_yup=True, export_apply=False,
    export_skins=True, export_morph=True, export_try_sparse_sk=False,   # three.js r128 cannot read empty sparse targets
    export_animations=True, export_animation_mode="ACTIONS",
    export_force_sampling=True, export_def_bones=False, export_frame_range=False,
    export_optimize_animation_size=True, export_anim_slide_to_zero=True)
print("EXPORTED", OUT, os.path.getsize(OUT))

# ---------------------------------------------------------------- pose sheet renders
if RENDERS:
    os.makedirs(RENDERS, exist_ok=True)
    scn.render.engine = "BLENDER_WORKBENCH"
    sh = scn.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_object_outline = True
    sh.object_outline_color = (0, 0, 0)
    sh.show_cavity = False
    world = bpy.data.worlds.new("w")
    world.color = (0.93, 0.94, 0.96)
    scn.world = world
    scn.render.resolution_x, scn.render.resolution_y = 360, 420
    scn.render.film_transparent = False
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 2.6
    cam = bpy.data.objects.new("cam", cam_d)
    scn.collection.objects.link(cam)
    scn.camera = cam
    tgt = bpy.data.objects.new("tgt", None)
    scn.collection.objects.link(tgt)
    tgt.location = (0, -0.1, 0.85)
    con = cam.constraints.new("TRACK_TO")
    con.target = tgt
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    VIEWS = {"q": (-3.2, -4.2, 1.6), "side": (-5.0, 0.0, 1.0)}
    arm.animation_data.action = bpy.data.actions["idle"]
    scn.frame_set(0)
    cam_d.ortho_scale = 0.42
    tgt.location = (0, 0, 1.60)
    for nm, pos, key in (("face_front", (0, -4, 1.6), None), ("face_q", (-2.4, -3.2, 1.7), None),
                         ("face_blink", (0, -4, 1.6), "Blink_L"), ("face_open", (0, -4, 1.6), "Mouth_Open")):
        kb = face.data.shape_keys.key_blocks
        for k in kb[1:]:
            k.value = 0.0
        if key:
            kb[key].value = 1.0
            if key == "Blink_L":
                kb["Blink_R"].value = 1.0
        cam.location = pos
        scn.render.filepath = os.path.join(RENDERS, "zz_%s.png" % nm)
        bpy.ops.render.render(write_still=True)
    for k in face.data.shape_keys.key_blocks[1:]:
        k.value = 0.0
    cam_d.ortho_scale = 2.6
    tgt.location = (0, -0.1, 0.85)
    for cname, keys in CLIPS.items():
        arm.animation_data.action = bpy.data.actions[cname]
        last = keys[-1][0]
        n = 8
        frames = sorted(set(int(round(last * k / (n - 1))) for k in range(n)))
        if cname == "ultimate":
            frames = [0, 12, 30, 46, 81, 84, 88, 104]
        for vname, vpos in VIEWS.items():
            cam.location = vpos
            for fr in frames:
                scn.frame_set(fr)
                scn.render.filepath = os.path.join(RENDERS, "%s_%s_%03d.png" % (cname, vname, fr))
                bpy.ops.render.render(write_still=True)
    print("RENDERED", RENDERS)
