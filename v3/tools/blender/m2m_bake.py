"""Bake Mesh2Motion (CC0) human animation .blend files to plain deform-bone keys (JSON), resampled to 30 fps.

    python m2m_bake.py <mesh2motion-assets/rigs/human> out.json

Mesh2Motion's human rig animates control bones (IK / FK / DRV_*); its deform bones are the
UE-mannequin set Quaternius uses (root, pelvis, spine_01 ...). This samples each deform bone's
evaluated pose (constraints included) and stores it as local loc + quaternion per frame, plus the
rest heads / tails so ual_to_spec.py can check the rest pose matches before using the keys.
"""
import json
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
ROOT, OUT = argv[:2]
FPS = 30

# game clip <- Mesh2Motion file (in-place versions, not *_RM)
CLIPS = {
    "run": "locomotion/animation-human-run-anime.blend",
    "dodge_back": "combat/defense/animation-human-dodge-back.blend",
    "dodge_left": "combat/defense/animation-human-dodge-left.blend",
    "dodge_right": "combat/defense/animation-human-dodge-right.blend",
    "parry": "combat/melee/animation-human-weapon-block.blend",
    "attack_normal_5": "combat/melee/animation-human-one-hand-slash-combo.blend",
    "attack_normal_6": "combat/unarmed/animation-human-kick-roundhouse.blend",
    "attack_normal_7": "combat/unarmed/animation-human-kick-spin.blend",
    "attack_special_2": "combat/melee/animation-human-sword-attack-air-vertical.blend",
    "attack_special_3": "combat/melee/animation-human-jump-attack.blend",
    "ultimate_2": "abilities/animation-human-power-burst.blend",
    "transform": "abilities/animation-human-power-up.blend",
    "air": "abilities/animation-human-levitate-idle.blend",
    "air_move": "abilities/animation-human-flying-forward-super.blend",
    "fall": "locomotion/animation-human-freefall.blend",
    "switch_in": "locomotion/animation-human-land-three-point.blend",
    "stagger": "combat/reactions/animation-human-dizzy.blend",
    "knockdown": "combat/reactions/animation-human-hit-knockback.blend",
    "getup": "combat/reactions/animation-human-laytoidle.blend",
}

out = {"fps": FPS, "clips": {}, "rest": None}
for clip, rel in CLIPS.items():
    bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, rel))
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o.animation_data and o.animation_data.action)
    act = arm.animation_data.action
    scn = bpy.context.scene
    src_fps = scn.render.fps / scn.render.fps_base
    f0, f1 = act.frame_range
    f0 = max(f0, 0.0)                                  # some actions start at -1 (a lead-in key)
    n = int(round((f1 - f0) * FPS / src_fps)) + 1
    deform = [pb for pb in arm.pose.bones if pb.bone.use_deform]
    if out["rest"] is None:
        out["rest"] = {pb.name: [list(pb.bone.head_local), list(pb.bone.tail_local)] for pb in deform}
    frames = []
    for k in range(n):
        t = f0 + k * src_fps / FPS
        scn.frame_set(int(t), subframe=t - int(t))
        fr = {}
        for pb in deform:
            m = arm.convert_space(pose_bone=pb, matrix=pb.matrix, from_space="POSE", to_space="LOCAL")
            loc, rot, _ = m.decompose()
            fr[pb.name] = [round(c, 6) for c in list(loc) + list(rot)]
        frames.append(fr)
    out["clips"][clip] = {"src": rel, "src_fps": src_fps, "frames": frames}
    print("baked", clip, act.name, "src frames", f0, f1, "@", src_fps, "->", n, "@30")

with open(OUT, "w") as f:
    json.dump(out, f)
print("WROTE", OUT)
