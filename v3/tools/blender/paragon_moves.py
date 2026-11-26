"""Paragon animations (retargeted to UE5 Manny, FBX) -> the shared body, for the Rig Forge 3D hero move packs
(paragon_library.py, Daniel 2026-11-26).

    python -I paragon_moves.py <hero folder with *.FBX (subfolders too)> out.glb [--limit N] [--check]

The source skeleton is UE5 Manny (160 bones, centimetres, A-pose rest, 5 spine bones) and the body is the UE4-style
Mixamo-named skeleton (T-pose rest, 3 spine bones), so fbx_moves.py's same-rest transfer does not fit. Here each mapped
body bone takes the source bone's WORLD rotation, after a rest alignment that turns the body bone's rest direction
(head -> mapped child head) onto the source bone's rest direction:
    want(t) = srcPose(s) x srcRest(s)^-1 x align(t) x bodyRest(t)        (rotations only, armature space)
so an arm points where the source arm points whatever the two rests are. Bone lengths stay the body's; only Hips
moves (the pelvis path, scaled by the hip height ratio), so root motion is kept. *_MSA duplicates are skipped.
Clips are named by their path under the hero folder (sub folder + file name); paragon_library.py reads them back.
"""
import math
import os
import re
import sys
import time

import bpy
from mathutils import Matrix, Quaternion  # noqa: F401

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paragon_library as pl  # noqa: E402  (categories; paragon_library.DROP ones are not baked)

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
LIMIT = None
CHECK = "--check" in argv
argv = [a for a in argv if a != "--check"]
per = {}
worst = [0.0, 0.0]                                                 # --check: worst bone angle (deg), hips height gap (m)
if "--limit" in argv:
    i = argv.index("--limit")
    LIMIT = int(argv[i + 1])
    del argv[i:i + 2]
HERO_DIR, OUT = argv[:2]
FPS = 30
HERE = os.path.dirname(os.path.abspath(__file__))
BODY = os.path.normpath(os.path.join(HERE, "..", "..", "..", "characters", "ual_swordsman", "ual_swordsman.glb"))

SIDE = {"l": "Left", "r": "Right"}
FING = {"thumb": "Thumb", "index": "Index", "middle": "Middle", "ring": "Ring", "pinky": "Pinky"}
LIMB = {"clavicle": "Shoulder", "upperarm": "Arm", "lowerarm": "ForeArm", "hand": "Hand",
        "thigh": "UpLeg", "calf": "Leg", "foot": "Foot", "ball": "ToeBase"}
# Manny's 5 spine bones -> the body's 3, by height (body Spine 1.05-1.17 m ~ spine_02/03, Spine1 1.17-1.32 ~ spine_04,
# Spine2 1.32-1.46 ~ spine_05); world rotations are copied, so the whole spine bend still arrives at the chest
BODYN = {"pelvis": "Hips", "spine_02": "Spine", "spine_04": "Spine1", "spine_05": "Spine2",
         "neck_01": "Neck", "head": "Head"}
# the child whose head gives a body bone its direction (the source uses the mapped bones' heads)
DIR_CHILD = {"Spine": "Spine1", "Spine1": "Spine2", "Spine2": "Neck", "Neck": "Head"}
for s in ("Left", "Right"):
    DIR_CHILD.update({s + "Shoulder": s + "Arm", s + "Arm": s + "ForeArm", s + "ForeArm": s + "Hand",
                      s + "Hand": s + "HandMiddle1", s + "UpLeg": s + "Leg", s + "Leg": s + "Foot",
                      s + "Foot": s + "ToeBase"})
    for f in FING.values():
        for k in (1, 2):
            DIR_CHILD[s + "Hand" + f + str(k)] = s + "Hand" + f + str(k + 1)


def body_name(n):
    if n in BODYN:
        return BODYN[n]
    base, _, s = n.rpartition("_")
    if s in SIDE:
        if base in LIMB:
            return SIDE[s] + LIMB[base]
        parts = base.split("_")
        if parts[0] in FING and len(parts) == 2 and parts[1].isdigit():
            return SIDE[s] + "Hand" + FING[parts[0]] + str(int(parts[1]))
    return None


def clip_id(rel):
    """'Attack/Attack01.FBX' -> 'Attack__Attack01' (unique in the hero's pack, glTF-safe)."""
    p = os.path.splitext(rel.replace("\\", "/"))[0]
    return re.sub(r"[^A-Za-z0-9_]+", "_", p.replace("/", "__"))


def purge(objs):
    arms = {o.data for o in objs if o.type == "ARMATURE"}
    meshes = {o.data for o in objs if o.type == "MESH"}
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    for d in arms:
        bpy.data.armatures.remove(d)
    for d in meshes:
        bpy.data.meshes.remove(d)
    for coll in (bpy.data.materials, bpy.data.images, bpy.data.textures):
        for d in list(coll):
            if d.users == 0:
                coll.remove(d)


bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.render.fps = FPS
bpy.ops.import_scene.gltf(filepath=BODY)
tgt = next(o for o in bpy.data.objects if o.type == "ARMATURE")
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
TW = tgt.matrix_world.copy()
tb = tgt.data.bones
tpb = tgt.pose.bones
t_order = [b.name for b in tb]                                   # parents first
t_rest_q = {n: (TW @ tb[n].matrix_local).to_quaternion() for n in t_order}
t_head = {n: TW @ tb[n].head_local for n in t_order}
# local rest of each bone relative to its parent (rotation only)
t_rel_q = {n: ((tb[n].parent.matrix_local.inverted() @ tb[n].matrix_local).to_quaternion() if tb[n].parent
               else tb[n].matrix_local.to_quaternion()) for n in t_order}
hips_h = t_head["Hips"].z
tgt.animation_data_create()

files = []
for root, _, names in os.walk(HERO_DIR):
    for f in names:
        if f.lower().endswith(".fbx") and not re.search(r"_msa\.fbx$", f, re.I):
            rel = os.path.relpath(os.path.join(root, f), HERO_DIR)
            if pl.label(clip_id(rel))[0] not in pl.DROP:
                files.append(rel)
files.sort(key=str.lower)
if LIMIT:
    files = files[:LIMIT]
print("files", len(files))

done, bad, t0 = [], [], time.time()
for fi, rel in enumerate(files):
    before = set(bpy.data.objects)
    acts_before = set(bpy.data.actions)
    try:
        bpy.ops.import_scene.fbx(filepath=os.path.join(HERO_DIR, rel))
    except Exception as e:                                          # noqa: BLE001
        bad.append((rel, str(e)[:80]))
        purge(list(set(bpy.data.objects) - before))
        continue
    new = list(set(bpy.data.objects) - before)
    src = next((o for o in new if o.type == "ARMATURE"), None)
    new_acts = [a for a in bpy.data.actions if a not in acts_before]
    if src is None or not new_acts:
        bad.append((rel, "no armature / no animation"))
        purge(new)
        for a in new_acts:
            bpy.data.actions.remove(a)
        continue
    SW = src.matrix_world.copy()
    sb = src.data.bones
    pair = {}                                                       # body bone -> source bone
    for b in sb:
        t = body_name(b.name)
        if t and t in tb:
            pair[t] = b.name
    if "Hips" not in pair:
        bad.append((rel, "no pelvis"))
        purge(new)
        for a in new_acts:
            bpy.data.actions.remove(a)
        continue
    s_head = {t: SW @ sb[s].head_local for t, s in pair.items()}
    s_rest_q = {t: (SW @ sb[s].matrix_local).to_quaternion() for t, s in pair.items()}
    align = {}
    for t in pair:
        c = DIR_CHILD.get(t)
        if c and c in pair:
            dt = (t_head[c] - t_head[t]).normalized()
            ds = (s_head[c] - s_head[t]).normalized()
            align[t] = dt.rotation_difference(ds)
        else:
            align[t] = Quaternion()
    # offset applied on the right of the source pose: srcRest^-1 x align x bodyRest
    off = {t: s_rest_q[t].inverted() @ align[t] @ t_rest_q[t] for t in pair}
    k_h = hips_h / max(1e-6, s_head["Hips"].z)
    order = [n for n in t_order if n in pair]

    act_src = src.animation_data.action if src.animation_data and src.animation_data.action else new_acts[0]
    src.animation_data_create()
    src.animation_data.action = act_src
    f0, f1 = act_src.frame_range
    n = max(1, int(math.floor(f1 - f0 + 1e-4)) + 1)
    cid = clip_id(rel)
    act = bpy.data.actions.new(cid)
    act.use_fake_user = True
    tgt.animation_data.action = act
    spb = src.pose.bones
    for k in range(n):
        fr = min(f0 + k, f1)
        scn.frame_set(int(math.floor(fr)), subframe=fr - math.floor(fr))
        want = {}
        for t in t_order:
            b = tb[t]
            par = b.parent.name if b.parent else None
            pw = want.get(par) if par else None
            if t in pair:
                q = (SW @ spb[pair[t]].matrix).to_quaternion() @ off[t]
            elif pw is not None:
                q = pw @ t_rel_q[t]                                 # unmapped: keeps its rest under its parent
            else:
                q = t_rest_q[t]
            want[t] = q
            if t not in pair:
                continue
            pq = pw if pw is not None else (TW.to_quaternion() if not b.parent else t_rest_q[par])
            basis = t_rel_q[t].inverted() @ pq.inverted() @ q
            pbn = tpb[t]
            pbn.rotation_mode = "QUATERNION"
            pbn.rotation_quaternion = basis.normalized()
            pbn.keyframe_insert("rotation_quaternion", frame=k, group=t)
            if t == "Hips":
                # pelvis path (scaled) -> Hips head; location basis is in the bone's rest frame
                p = (SW @ spb[pair[t]].matrix).to_translation() * k_h
                rest_m = TW @ b.matrix_local
                if b.parent:
                    par_m = TW @ b.parent.matrix_local                # root bone never moves
                    loc_par = par_m.inverted() @ p
                    rl = b.parent.matrix_local.inverted() @ b.matrix_local
                    loc = rl.to_3x3().inverted() @ (loc_par - rl.to_translation())
                else:
                    loc = rest_m.to_3x3().inverted() @ (p - rest_m.to_translation())
                pbn.location = loc
                pbn.keyframe_insert("location", frame=k, group=t)
        if CHECK and k % 5 == 0:                                     # body bone directions vs the source's
            bpy.context.view_layer.update()
            for t, c in DIR_CHILD.items():
                if t in pair and c in pair and "Hand" not in t:
                    dt = (TW @ tpb[c].head - TW @ tpb[t].head).normalized()
                    ds = ((SW @ spb[pair[c]].head) - (SW @ spb[pair[t]].head)).normalized()
                    g = math.degrees(dt.angle(ds))
                    worst[0] = max(worst[0], g)
                    per[t] = max(per.get(t, 0.0), g)
            hp = (TW @ tpb["Hips"].head).z, (SW @ spb[pair["Hips"]].head).z * k_h
            worst[1] = max(worst[1], abs(hp[0] - hp[1]))
    done.append(cid)
    tgt.animation_data.action = None
    purge(new)
    for a in new_acts:
        bpy.data.actions.remove(a)
    if fi % 10 == 0 or fi == len(files) - 1:
        print("%4d/%d  %-50s %3d frames  %.0fs" % (fi + 1, len(files), rel, n, time.time() - t0), flush=True)

for pb in tpb:
    pb.location = (0, 0, 0)
    pb.rotation_quaternion = (1, 0, 0, 0)
for a in list(bpy.data.actions):
    if a.name not in done:
        bpy.data.actions.remove(a)
for rel, why in bad:
    print("SKIPPED", rel, why)
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format="GLB", export_animations=True, export_animation_mode="ACTIONS",
    export_force_sampling=True, export_frame_step=1, export_anim_slide_to_zero=True, export_yup=True)
if CHECK:
    print("  per bone:", ", ".join("%s %.1f" % kv for kv in sorted(per.items(), key=lambda kv: -kv[1])[:8]))
    print("check: worst limb / spine direction gap %.2f deg, hips height gap %.4f m" % tuple(worst))
print("WROTE", OUT, len(done), "clips,", len(bad), "skipped, %.0fs" % (time.time() - t0))
