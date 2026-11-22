"""Quaternius Universal Animation Library (UAL1 + UAL2, CC0) -> one V3 fighter .glb on the RIG_SPEC rig.

    python ual_to_spec.py UAL2_Standard.glb UAL1_Standard.glb out.glb [m2m_keys.json]

The optional m2m_keys.json (from m2m_bake.py, Mesh2Motion CC0 clips) adds / replaces clips by game name.

- renames the UE-mannequin bones to Mixamo names (v3/RIG_SPEC.md section 2)
- adds HeadTop_End, Jaw, LeftEye, RightEye (non-deforming) and Weapon_R / WeaponTip_R + a plain blade mesh
- keeps the sword-fighter clips from both libraries, renamed to game action names (section 4)
- exports with the section 5 settings (no sparse shape keys, Actions mode, 30 fps)
No face shape keys are made: the mannequin has no face.
"""
import json
import sys

import bpy
from mathutils import Quaternion, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
UAL2, UAL1, OUT = argv[:3]
M2M = argv[3] if len(argv) > 3 else None

SIDE = {"l": "Left", "r": "Right"}
FING = {"thumb": "Thumb", "index": "Index", "middle": "Middle", "ring": "Ring", "pinky": "Pinky"}
BODY = {"head": "Head", "pelvis": "Hips", "spine_01": "Spine", "spine_02": "Spine1", "spine_03": "Spine2", "neck_01": "Neck", "Head": "Head"}
LIMB = {"clavicle": "Shoulder", "upperarm": "Arm", "lowerarm": "ForeArm", "hand": "Hand",
        "thigh": "UpLeg", "calf": "Leg", "foot": "Foot", "ball": "ToeBase", "ball_leaf": "Toe_End"}


def mixamo_name(n):
    if n in BODY:
        return BODY[n]
    base, _, s = n.rpartition("_")
    if s in SIDE:
        if base in LIMB:
            return SIDE[s] + LIMB[base]
        parts = base.split("_")                       # index_01 / index_04_leaf
        if parts[0] in FING:
            return SIDE[s] + "Hand" + FING[parts[0]] + str(int(parts[1]))
    return n


# game clip <- (library, UAL clip)
CLIPS = {
    "idle": "Sword_Idle", "run": "Jog_Fwd_Loop", "walk": "Walk_Loop", "sprint": "Sprint_Loop",
    "attack_normal": "Sword_Regular_A", "attack_normal_2": "Sword_Regular_B", "attack_normal_3": "Sword_Regular_C",
    "attack_normal_4": "Melee_Hook", "attack_special": "Sword_Dash", "ultimate": "Sword_Heavy_Combo",
    "defend": "Sword_Block", "dodge": "Roll", "hit_light": "Hit_Chest", "hit_heavy": "Hit_Knockback",
    "ko": "Death01", "jump": "NinjaJump_Start", "air": "NinjaJump_Idle_Loop", "land": "NinjaJump_Land",
}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = 30


def fcurves(act):
    if hasattr(act, "layers") and act.layers:          # Blender 4.4+ slotted actions
        for layer in act.layers:
            for strip in layer.strips:
                for slot in act.slots:
                    cb = strip.channelbag(slot)
                    if cb:
                        yield from cb.fcurves
    else:
        yield from act.fcurves


before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=UAL1)
for ob in set(bpy.data.objects) - before:             # keep only UAL1's actions
    bpy.data.objects.remove(ob, do_unlink=True)
ual1_acts = {a.name: a for a in bpy.data.actions}
for a in ual1_acts.values():
    a.name = "UAL1__" + a.name
bpy.ops.import_scene.gltf(filepath=UAL2)

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = [o for o in bpy.data.objects if o.type == "MESH" and any(m.type == "ARMATURE" for m in o.modifiers)]
for o in [o for o in bpy.data.objects if o.type == "MESH" and o not in body]:
    print("dropping unskinned mesh", o.name, tuple(round(d, 2) for d in o.dimensions))
    bpy.data.objects.remove(o, do_unlink=True)
print("armature", arm.name, "meshes", [m.name for m in body])

# ---- pick + rename actions
lib = {}
for a in bpy.data.actions:
    n = a.name
    if n.startswith("UAL1__"):
        lib.setdefault(n[6:], a)
    else:
        lib.setdefault(n, a)
keep = {}
for game, src in CLIPS.items():
    a = lib.get(src)
    if a is None:
        cand = [k for k in lib if k.startswith(src)]  # importer may suffix names with the object name
        a = lib[cand[0]] if cand else None
    if a is None:
        print("MISSING CLIP", src)
        continue
    keep[game] = a
for a in list(bpy.data.actions):
    if a not in keep.values():
        bpy.data.actions.remove(a)
for game, a in keep.items():
    a.name = game
    a.use_fake_user = True

# ---- rename bones (pose / vertex groups via Blender, every action's paths by hand)
ren = {b.name: mixamo_name(b.name) for b in arm.data.bones}
for a in bpy.data.actions:
    for fc in fcurves(a):
        p = fc.data_path
        if p.startswith('pose.bones["'):
            old = p.split('"')[1]
            if old in ren and ren[old] != old:
                fc.data_path = p.replace('"%s"' % old, '"%s"' % ren[old], 1)
        if fc.group and fc.group.name in ren:
            fc.group.name = ren[fc.group.name]
arm.animation_data_create()
arm.animation_data.action = None
for b in arm.data.bones:
    b.name = ren[b.name]
for m in body:
    for vg in m.vertex_groups:
        if vg.name in ren:
            vg.name = ren[vg.name]

# ---- Mesh2Motion clips (same mannequin skeleton, keys are local loc + quat per deform bone)
if M2M:
    mk = json.load(open(M2M))
    worst = 0.0
    for old, (h, t) in mk["rest"].items():
        b = arm.data.bones.get(mixamo_name(old))
        if b:
            worst = max(worst, (b.head_local - Vector(h)).length, (b.tail_local - Vector(t)).length)
    print("m2m rest vs UAL rest: worst bone offset %.4f (armature units)" % worst)
    pbs = arm.pose.bones
    for clip, d in mk["clips"].items():
        if clip in bpy.data.actions:
            bpy.data.actions.remove(bpy.data.actions[clip])
        act = bpy.data.actions.new(clip)
        act.use_fake_user = True
        arm.animation_data.action = act
        for f, fr in enumerate(d["frames"]):
            for old, v in fr.items():
                pb = pbs.get(mixamo_name(old))
                if pb is None:
                    continue
                pb.rotation_mode = "QUATERNION"
                pb.location = v[:3]
                pb.rotation_quaternion = Quaternion(v[3:])
                pb.keyframe_insert("location", frame=f, group=pb.name)
                pb.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)
        keep[clip] = act
        print("m2m clip", clip, len(d["frames"]), "frames from", d["src"])
    arm.animation_data.action = None
    for pb in pbs:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)

# ---- extra bones
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
eb = arm.data.edit_bones
mw = arm.matrix_world
H = eb["Head"]
hlen = (H.tail - H.head).length
up = (H.tail - H.head).normalized()


def add(name, head, tail, parent, deform=False):
    b = eb.new(name)
    b.head, b.tail = head, tail
    b.parent = eb[parent]
    b.use_deform = deform
    return b


# facing: toes point forward
fwd = (eb["LeftToe_End"].head - eb["LeftFoot"].head)
fwd.z = 0
fwd.normalize()
print("rest forward (armature space)", tuple(round(c, 3) for c in fwd))
top = H.tail + up * hlen * 0.05
if "HeadTop_End" not in eb:
    add("HeadTop_End", top, top + up * 0.05, "Head")
add("Jaw", H.head + fwd * 0.02, H.head + fwd * 0.09, "Head")
side = fwd.cross(up).normalized()
for s, nm in ((1, "LeftEye"), (-1, "RightEye")):
    e = H.head + up * hlen * 0.55 + fwd * 0.08 + side * 0.032 * s
    add(nm, e, e + fwd * 0.03, "Head")
# weapon: grip in the palm, blade out the thumb side of the fist (pinky knuckle -> index knuckle)
hand = eb["RightHand"]
g = (eb["RightHandIndex1"].head + eb["RightHandPinky1"].head) * 0.5
g = hand.head + (g - hand.head) * 0.6
bdir = (eb["RightHandIndex1"].head - eb["RightHandPinky1"].head).normalized()
BLADE = 0.95
add("Weapon_R", g, g + bdir * 0.25, "RightHand", deform=True)
tip = g + bdir * (0.06 + BLADE)
add("WeaponTip_R", tip, tip + bdir * 0.05, "Weapon_R")
bpy.ops.object.mode_set(mode="OBJECT")

# ---- blade mesh, skinned 100 % to Weapon_R
gw, bw = mw @ g, (mw.to_3x3() @ bdir).normalized()
n1 = bw.cross(Vector((0, 0, 1)))
if n1.length < 1e-3:
    n1 = bw.cross(Vector((1, 0, 0)))
n1.normalize()
n2 = bw.cross(n1).normalized()
segs = [(-0.17, 0.014, 0.014), (0.06, 0.03, 0.006), (0.06 + BLADE * 0.97, 0.022, 0.004), (0.06 + BLADE, 0.0, 0.002)]
verts, faces = [], []
for d, w, t in segs:
    c = gw + bw * d
    verts += [c + n1 * w + n2 * t, c - n1 * w + n2 * t, c - n1 * w - n2 * t, c + n1 * w - n2 * t]
for i in range(len(segs) - 1):
    a, b = i * 4, i * 4 + 4
    for k in range(4):
        faces.append((a + k, a + (k + 1) % 4, b + (k + 1) % 4, b + k))
faces.append((3, 2, 1, 0))
me = bpy.data.meshes.new("blade")
me.from_pydata([tuple(v) for v in verts], [], faces)
mat = bpy.data.materials.new("blade")
mat.diffuse_color = (0.86, 0.9, 0.96, 1)
me.materials.append(mat)
blade = bpy.data.objects.new("blade", me)
bpy.context.scene.collection.objects.link(blade)
vg = blade.vertex_groups.new(name="Weapon_R")
vg.add(range(len(verts)), 1.0, "REPLACE")
blade.parent = arm
blade.matrix_parent_inverse = arm.matrix_world.inverted()
mod = blade.modifiers.new("Armature", "ARMATURE")
mod.object = arm

# ---- report
zs = [(m.matrix_world @ v.co).z for m in body for v in m.data.vertices]
print("height m", round(max(zs) - min(zs), 3), "min z", round(min(zs), 3))
print("tris", sum(len(p.vertices) - 2 for m in body for p in m.data.polygons))
print("bones", len(arm.data.bones))
for game, a in sorted(keep.items()):
    print("clip", game, "frames", a.frame_range[:], )

# ---- export (RIG_SPEC section 5)
arm.animation_data.action = bpy.data.actions["idle"]
bpy.ops.object.select_all(action="DESELECT")
for ob in [arm, blade] + body:
    ob.select_set(True)
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format="GLB", use_selection=True, export_yup=True, export_apply=False,
    export_skins=True, export_morph=True, export_try_sparse_sk=False,
    export_animations=True, export_animation_mode="ACTIONS",
    export_force_sampling=True, export_def_bones=False, export_frame_range=False,
    export_optimize_animation_size=True, export_anim_slide_to_zero=True)
print("EXPORTED", OUT)
