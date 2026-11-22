"""Mesh2Motion (CC0) combat clips -> the shared body, for the Rig Forge 3D move library (v3/tools/move_library.py).

    python m2m_moves.py <mesh2motion-assets>/rigs/human out.glb

Same sampling as m2m_bake.py (deform bones' evaluated local loc + quaternion, resampled to 30 fps), then the keys
go straight onto characters/ual_swordsman/ual_swordsman.glb's armature (UE names -> Mixamo names, like
ual_to_spec.py) and the body is exported with ONLY these clips. move_library.py turns that into key poses.
"""
import os
import sys

import bpy
from mathutils import Quaternion

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import move_library as ml  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
ROOT, OUT = argv[:2]
FPS = 30
BODY = os.path.join(os.path.dirname(os.path.dirname(HERE)), "..", "characters", "ual_swordsman", "ual_swordsman.glb")

SIDE = {"l": "Left", "r": "Right"}
FING = {"thumb": "Thumb", "index": "Index", "middle": "Middle", "ring": "Ring", "pinky": "Pinky"}
BODYN = {"head": "Head", "pelvis": "Hips", "spine_01": "Spine", "spine_02": "Spine1", "spine_03": "Spine2",
         "neck_01": "Neck", "Head": "Head"}
LIMB = {"clavicle": "Shoulder", "upperarm": "Arm", "lowerarm": "ForeArm", "hand": "Hand",
        "thigh": "UpLeg", "calf": "Leg", "foot": "Foot", "ball": "ToeBase", "ball_leaf": "Toe_End"}


def mixamo_name(n):
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


def bake(rel):
    bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, rel))
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o.animation_data and o.animation_data.action)
    act = arm.animation_data.action
    scn = bpy.context.scene
    src_fps = scn.render.fps / scn.render.fps_base
    f0, f1 = act.frame_range
    f0 = max(f0, 0.0)
    n = int(round((f1 - f0) * FPS / src_fps)) + 1
    deform = [pb for pb in arm.pose.bones if pb.bone.use_deform]
    frames = []
    for k in range(n):
        t = f0 + k * src_fps / FPS
        scn.frame_set(int(t), subframe=t - int(t))
        fr = {}
        for pb in deform:
            m = arm.convert_space(pose_bone=pb, matrix=pb.matrix, from_space="POSE", to_space="LOCAL")
            loc, rot, _ = m.decompose()
            fr[pb.name] = list(loc) + list(rot)
        frames.append(fr)
    print("baked", rel, f0, f1, "@", src_fps, "->", n, "@30")
    return frames


todo = {k: v[2] for k, v in ml.MOVES.items()}
todo.update(ml.CHECK)
baked = {clip: bake(rel) for clip, rel in todo.items()}

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.fps = FPS
bpy.ops.import_scene.gltf(filepath=os.path.normpath(BODY))
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
arm.animation_data_create()
pbs = arm.pose.bones
for clip, frames in baked.items():
    act = bpy.data.actions.new(clip)
    act.use_fake_user = True
    arm.animation_data.action = act
    for f, fr in enumerate(frames):
        for old, v in fr.items():
            pb = pbs.get(mixamo_name(old))
            if pb is None:
                continue
            pb.rotation_mode = "QUATERNION"
            pb.location = v[:3]
            pb.rotation_quaternion = Quaternion(v[3:])
            pb.keyframe_insert("location", frame=f, group=pb.name)
            pb.keyframe_insert("rotation_quaternion", frame=f, group=pb.name)
arm.animation_data.action = None
for pb in pbs:
    pb.location = (0, 0, 0)
    pb.rotation_quaternion = (1, 0, 0, 0)
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format="GLB", export_animations=True, export_animation_mode="ACTIONS",
    export_force_sampling=True, export_frame_step=1, export_anim_slide_to_zero=True, export_yup=True)
print("WROTE", OUT)
