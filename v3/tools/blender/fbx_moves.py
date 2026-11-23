"""Quaternius UAL1 Standard (CC0) FBX clips -> the shared body, for the Rig Forge 3D move library (move_library.py).

    python fbx_moves.py UAL1_Standard.fbx out.glb

Same skeleton as the body (UE mannequin, renamed to Mixamo names like ual_to_spec.py), but the FBX importer gives
other bone axes (and turns the armature object 180 deg in the scene), so the clips are moved over in ARMATURE space: each bone's
pose = (source pose x source rest^-1) x body rest, then turned back into a local basis down the hierarchy. Works
for any bone axes; positions are kept as is (same rest skeleton, checked on load). The body is exported with ONLY
the clips in move_library.UAL1 (30 fps); move_library.py turns that into key poses.
"""
import os
import sys

import bpy
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import move_library as ml  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
FBX, OUT = argv[:2]
FPS = 30
SIDE = {"l": "Left", "r": "Right"}
FING = {"thumb": "Thumb", "index": "Index", "middle": "Middle", "ring": "Ring", "pinky": "Pinky"}
BODYN = {"head": "Head", "pelvis": "Hips", "spine_01": "Spine", "spine_02": "Spine1", "spine_03": "Spine2",
         "neck_01": "Neck", "Head": "Head"}
LIMB = {"clavicle": "Shoulder", "upperarm": "Arm", "lowerarm": "ForeArm", "hand": "Hand",
        "thigh": "UpLeg", "calf": "Leg", "foot": "Foot", "ball": "ToeBase", "ball_leaf": "Toe_End"}


def mixamo_name(n):
    """UE mannequin bone -> Mixamo name (same table as ual_to_spec.py / m2m_moves.py)."""
    if n in BODYN:
        return BODYN[n]
    base, _, s = n.rpartition("_")
    if s in SIDE:
        if base in LIMB:
            return SIDE[s] + LIMB[base]
        parts = base.split("_")
        if parts[0] in FING:
            return SIDE[s] + "Hand" + FING[parts[0]] + str(int(parts[1]))
    return n

BODY = os.path.join(os.path.dirname(os.path.dirname(HERE)), "..", "characters", "ual_swordsman", "ual_swordsman.glb")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = FPS
bpy.ops.import_scene.gltf(filepath=os.path.normpath(BODY))
tgt = next(o for o in bpy.data.objects if o.type == "ARMATURE")
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
before = set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=FBX)
new = set(bpy.data.objects) - before
src = next(o for o in new if o.type == "ARMATURE")

# source bone -> body bone, in hierarchy order of the body
pair = {}
for b in src.data.bones:
    t = mixamo_name(b.name)
    if t in tgt.data.bones:
        pair[t] = b.name
order = [b.name for b in tgt.data.bones if b.name in pair]   # bones list is parents-first
# the two ARMATURE spaces are the same (only the FBX object is turned 180 deg in the scene, which says nothing
# about the moves), so no object transform is applied
S2T = Matrix.Identity(4)
worst = max((S2T @ src.data.bones[s].head_local - tgt.data.bones[t].head_local).length for t, s in pair.items())
for t, s in pair.items():
    d = (S2T @ src.data.bones[s].head_local - tgt.data.bones[t].head_local).length
    if d > 0.02:
        print("  offset", s, t, round(d, 3))
print("rest check: worst joint offset %.4f m over %d bones" % (worst, len(pair)))
if worst > 0.02:
    sys.exit("FBX rest skeleton does not match the body")
delta = {t: (S2T @ src.data.bones[s].matrix_local).inverted() @ tgt.data.bones[t].matrix_local for t, s in pair.items()}

acts = {}
for a in bpy.data.actions:
    nm = a.name.split("|")[-1]
    acts.setdefault(nm, a)
src.animation_data_create()
scn = bpy.context.scene
tpb = tgt.pose.bones
tgt.animation_data_create()
done = []
for clip, (_, _, name) in ml.UAL1.items():
    a = acts.get(name)
    if a is None:
        print("MISSING", name)
        continue
    src.animation_data.action = a
    f0, f1 = a.frame_range
    n = int(round(f1 - f0)) + 1
    act = bpy.data.actions.new(clip)
    act.use_fake_user = True
    tgt.animation_data.action = act
    for k in range(n):
        scn.frame_set(int(f0) + k)
        want = {}
        for t in order:
            s = pair[t]
            want[t] = S2T @ src.pose.bones[s].matrix @ delta[t]       # desired body pose, armature space
            bone = tgt.data.bones[t]
            if bone.parent and bone.parent.name in want:
                p = bone.parent
                basis = (p.matrix_local.inverted() @ bone.matrix_local).inverted() @ want[p.name].inverted() @ want[t]
            else:
                basis = bone.matrix_local.inverted() @ want[t]
            loc, rot, _ = basis.decompose()
            pb = tpb[t]
            pb.rotation_mode = "QUATERNION"
            pb.location = loc
            pb.rotation_quaternion = rot
            pb.keyframe_insert("location", frame=k, group=t)
            pb.keyframe_insert("rotation_quaternion", frame=k, group=t)
    done.append(clip)
    print("baked %-20s %-24s %3d frames" % (clip, name, n))

for o in new:
    bpy.data.objects.remove(o, do_unlink=True)
tgt.animation_data.action = None
for pb in tpb:
    pb.location = (0, 0, 0)
    pb.rotation_quaternion = (1, 0, 0, 0)
for a in list(bpy.data.actions):
    if a.name not in done:
        bpy.data.actions.remove(a)
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format="GLB", export_animations=True, export_animation_mode="ACTIONS",
    export_force_sampling=True, export_frame_step=1, export_anim_slide_to_zero=True, export_yup=True)
print("WROTE", OUT, len(done), "clips")
