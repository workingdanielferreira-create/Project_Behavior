"""Rig Forge 3D move library pack: weapon combat moves as stock library moves (Daniel 2026-11-22).

`characters/ual_swordsman/ual_moves.glb` = the shared body's skeleton (no mesh) + one clip per library move, stored as
key poses (`pb_keys`, keyreduce.py) like every other clip, and scene extras `pb_moves` {clip: {name, cat, src}}.
Rig Forge 3D lists them in "Pose + move library" under their category (read-only stock moves, like "Body moves"); they
are NOT game clips: V3 never plays them until you apply one to an action and save.

Sources: Mesh2Motion human animations (CC0, github.com/Mesh2Motion/mesh2motion-assets, rigs/human); in-place
versions only. Moves the shared body already has as game clips (one-hand slash combo, air vertical, jump attack,
weapon block ...) are not repeated here: they stay under "Body moves".

Authored moves (Katana, Ethereal swords; no free mocap exists for them): key poses in `library/moves.anim3d.json`
(format pb_anim3d, solved by anim3d.py like a character's clips, + per clip "cat", "name", "approved"). A clip goes
into the pack only once Daniel approved its key-pose stills ("approved": true; v3-animation skill rule).

Build (cloud route, see RIG_SPEC section 8):
    python blender/m2m_moves.py <mesh2motion-assets>/rigs/human m2m_moves.glb      (bpy: bake onto the body, full glb)
    python move_library.py m2m_moves.glb                                           (key poses -> ual_moves.glb)
    python blender/fbx_moves.py UAL1_Standard.fbx ual1_moves.glb                   (bpy: Quaternius UAL1 FBX clips)
    python move_library.py ual1_moves.glb             (adds / replaces those moves; the pack's other moves are kept)
    python move_library.py -                       (authored moves changed: keep the pack's Mesh2Motion moves as they are)
    python move_library.py - out.glb --drafts      (a preview pack with the unapproved authored moves too)
    python move_library.py --check                 (anim_audit on the authored moves, drafts included)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# clip name -> (category, library name, Mesh2Motion file under rigs/human)
MOVES = {
    # ---- one-handed sword
    "sw_attack": ("Sword", "Sword attack (lunge cut)", "combat/melee/animation-human-sword-attack.blend"),
    "sw_regular_a_rec": ("Sword", "Regular A + recovery", "combat/melee/animation-human-sword-regular-a-rec.blend"),
    "sw_regular_b_rec": ("Sword", "Regular B + recovery", "combat/melee/animation-human-sword-regular-b-rec.blend"),
    "sw_regular_combo": ("Sword", "Regular combo (A > B > C)", "combat/melee/animation-human-sword-regular-combo.blend"),
    "sw_draw": ("Sword", "Draw weapon", "combat/melee/animation-human-weapon-draw.blend"),
    "sw_block": ("Sword", "Sword block", "combat/defense/animation-human-sword-block.blend"),
    "sw_idle": ("Sword", "Sword idle", "combat/melee/animation-human-idle-sword.blend"),
    "sw_idle_low": ("Sword", "One-hand weapon idle", "combat/melee/animation-human-one-hand-weapon-idle.blend"),
    "sw_stab": ("Sword", "Dagger stab", "combat/melee/animation-human-dagger-stab.blend"),
    # ---- dual swords
    "dw_combo": ("Dual swords", "Dual-wield combo", "combat/melee/animation-human-dual-wield-combo.blend"),
    "dw_cross": ("Dual swords", "Dual cross slash", "combat/melee/animation-human-dual-wield-cross-slash.blend"),
    # ---- great sword (two-handed)
    "gs_swing": ("Great sword", "Two-handed horizontal swing", "combat/melee/animation-human-two-handed-horizontal-swing.blend"),
    "gs_slam": ("Great sword", "Two-handed overhead slam", "combat/melee/animation-human-two-handed-overhead-slam.blend"),
    # ---- pistol
    "ps_idle": ("Pistol", "Pistol idle", "combat/ranged/animation-human-pistol-idle.blend"),
    "ps_idle_aim": ("Pistol", "Pistol idle aim", "combat/ranged/animation-human-pistol-idle-aim.blend"),
    "ps_aim_up": ("Pistol", "Aim up", "combat/ranged/animation-human-pistol-aim-up.blend"),
    "ps_aim": ("Pistol", "Aim level", "combat/ranged/animation-human-pistol-aim-neutral.blend"),
    "ps_aim_down": ("Pistol", "Aim down", "combat/ranged/animation-human-pistol-aim-down.blend"),
    "ps_fire": ("Pistol", "Fire (single shot)", "combat/ranged/animation-human-pistol-fire.blend"),
    "ps_shoot": ("Pistol", "Shoot (draw + shots)", "combat/ranged/animation-human-pistol-shoot.blend"),
    "ps_reload": ("Pistol", "Reload", "combat/ranged/animation-human-pistol-reload.blend"),
    "ps_reload_2": ("Pistol", "Reload (fast)", "combat/ranged/animation-human-pistol-reload-2.blend"),
    "ps_walk": ("Pistol", "Walk aiming", "combat/ranged/animation-human-pistol-walk.blend"),
    "ps_prone": ("Pistol", "Prone aim", "combat/ranged/animation-human-pistol-prone.blend"),
}
# Quaternius Universal Animation Library 1 Standard (CC0), FBX via blender/fbx_moves.py (Daniel 2026-11-23: the
# fight-useful clips only, grouped by type). clip name -> (category, library name, UAL1 clip)
UAL1 = {
    "u1_idle": ("Movement", "Idle (UAL1)", "Idle_Loop"),
    "u1_walk": ("Movement", "Walk (UAL1)", "Walk_Loop"),
    "u1_jog": ("Movement", "Jog (UAL1)", "Jog_Fwd_Loop"),
    "u1_sprint": ("Movement", "Sprint (UAL1)", "Sprint_Loop"),
    "u1_crouch_idle": ("Movement", "Crouch idle", "Crouch_Idle_Loop"),
    "u1_crouch_walk": ("Movement", "Crouch walk", "Crouch_Fwd_Loop"),
    "u1_jump_start": ("Movement", "Jump start", "Jump_Start"),
    "u1_jump_air": ("Movement", "Jump air loop", "Jump_Loop"),
    "u1_jump_land": ("Movement", "Jump land", "Jump_Land"),
    "u1_roll": ("Movement", "Roll (UAL1)", "Roll"),
    "u1_hit_chest": ("Reactions", "Hit chest", "Hit_Chest"),
    "u1_hit_head": ("Reactions", "Hit head", "Hit_Head"),
    "u1_death": ("Reactions", "Death", "Death01"),
    "u1_punch_jab": ("Unarmed", "Punch jab", "Punch_Jab"),
    "u1_punch_cross": ("Unarmed", "Punch cross", "Punch_Cross"),
    "u1_spell_enter": ("Magic", "Spell raise", "Spell_Simple_Enter"),
    "u1_spell_idle": ("Magic", "Spell hold", "Spell_Simple_Idle_Loop"),
    "u1_spell_shoot": ("Magic", "Spell cast", "Spell_Simple_Shoot"),
    "u1_spell_exit": ("Magic", "Spell lower", "Spell_Simple_Exit"),
    "u1_ps_idle": ("Pistol", "Pistol idle (UAL1)", "Pistol_Idle_Loop"),
    "u1_ps_aim_up": ("Pistol", "Aim up (UAL1)", "Pistol_Aim_Up"),
    "u1_ps_aim": ("Pistol", "Aim level (UAL1)", "Pistol_Aim_Neutral"),
    "u1_ps_aim_down": ("Pistol", "Aim down (UAL1)", "Pistol_Aim_Down"),
    "u1_ps_shoot": ("Pistol", "Shoot (UAL1)", "Pistol_Shoot"),
    "u1_ps_reload": ("Pistol", "Reload (UAL1)", "Pistol_Reload"),
    "u1_sw_attack": ("Sword", "Sword attack (UAL1)", "Sword_Attack"),
    "u1_sw_idle": ("Sword", "Sword idle (UAL1)", "Sword_Idle"),
}
STOCK = dict(MOVES, **UAL1)                            # every mocap move the pack can hold


def src_label(k):
    if k in UAL1:
        return "Quaternius UAL1 Standard (CC0) " + UAL1[k][2]
    return "Mesh2Motion (CC0) " + os.path.basename(MOVES[k][2])


# baked too, only to check the bake against the body's own copy of the same Mesh2Motion clip (not written)
CHECK = {"attack_normal_5": "combat/melee/animation-human-one-hand-slash-combo.blend"}

OUT = os.path.join(os.path.dirname(HERE), "..", "characters", "ual_swordsman", "ual_moves.glb")
AUTHORED = os.path.join(HERE, "library", "moves.anim3d.json")


def authored(drafts=False, notes=None, B=None):
    """{clip: (key times, key poses, eases)}, {clip: meta} for the authored moves (approved only unless drafts)."""
    import json
    import anim3d
    spec = json.load(open(AUTHORED, encoding="utf-8"))
    B = B or anim3d.Body()
    clips, meta = {}, {}
    for c, s in spec["clips"].items():
        if not (s.get("approved") or drafts):
            continue
        clips[c] = anim3d.bake_clip(B, s, notes)
        meta[c] = {"name": s["name"] + ("" if s.get("approved") else " (draft)"), "cat": s["cat"],
                   "src": "Authored key poses (v3/tools/library/moves.anim3d.json)"}
        print("  %-18s %3d keys  (%s)" % (c, len(clips[c][0]), meta[c]["name"]))
    return clips, meta


def build(src_glb, out=None, drafts=False):
    import numpy as np
    import keyreduce as kr
    import retarget2d as r
    out = os.path.normpath(out or OUT)
    bj, bb = r.read_glb(r.BODY)
    rig = r.Rig(bj, bb)
    if src_glb == "-":                                 # keep the pack's Mesh2Motion moves as they are (no bpy needed)
        return rebuild(out, drafts, bj, bb, rig)
    j, b = r.read_glb(src_glb)
    names = [n.get("name") for n in j["nodes"]]
    if [n.get("name") for n in bj["nodes"] if n.get("name") in names] != [n for n in names if n in
                                                                          {x.get("name") for x in bj["nodes"]}]:
        print("note: node order differs from the body; matched by name")
    # the bpy export's nodes -> the body's node indices (by bone name)
    remap = {i: rig.idx[n] for i, n in enumerate(names) if n in rig.idx}
    for an in j["animations"]:
        for ch in an["channels"]:
            ch["target"]["node"] = remap.get(ch["target"]["node"], -1)
        an["channels"] = [c for c in an["channels"] if c["target"]["node"] >= 0]
    jj = dict(bj)
    jj["accessors"], jj["bufferViews"], jj["buffers"] = j["accessors"], j["bufferViews"], j["buffers"]
    clips, check = {}, {}
    for an in j["animations"]:
        nm = an["name"]
        if nm not in STOCK and nm not in CHECK:
            continue
        times, poses = kr.clip_from_glb(rig, jj, b, an)
        if nm in CHECK:
            check[nm] = (times, poses)
            continue
        if len(times) == 1:                            # a single pose (aim up / level / down): hold it 0.5 s
            times, poses = [0.0, 0.5], [poses[0], poses[0]]
        clips[nm] = kr.reduce(rig, times, poses)
        print("  %-18s %4d frames -> %3d keys  (%s)" % (nm, len(times), len(clips[nm][0]), STOCK[nm][1]))
    # check: our bake of a clip vs the same clip already on the body (built by ual_to_spec.py)
    for nm, (times, poses) in check.items():
        an = next((a for a in bj["animations"] if a["name"] == nm), None)
        if an is None:
            continue
        bt, bp = kr.clip_from_glb(rig, bj, bb, an)
        n = min(len(times), len(bt))
        worst = 0.0
        for f in range(0, n, 3):
            p1 = kr._points(rig, poses[f])[0]
            p2 = kr._points(rig, bp[f])[0]
            worst = max(worst, float(np.max(np.linalg.norm(p1 - p2, axis=1))))
        print("check %s: worst joint gap vs the body's copy %.3f m over %d frames" % (nm, worst, n))
    meta = {k: {"name": STOCK[k][1], "cat": STOCK[k][0], "src": src_label(k)} for k in clips}
    # the pack's other stock moves (from another source file) stay as they are
    if os.path.exists(OUT):
        oc, om = stock_in_pack(rig)
        for k in oc:
            if k not in clips:
                clips[k], meta[k] = oc[k], om[k]
    missing = [k for k in STOCK if k not in clips]
    if missing:
        print("not in the pack:", missing)
    write(out, clips, meta, drafts, bj, bb, rig)


def rebuild(out, drafts, bj, bb, rig):
    """The pack's own mocap moves (already key poses: read back exactly, not reduced again) + the authored ones."""
    clips, meta = stock_in_pack(rig)
    write(out, clips, meta, drafts, bj, bb, rig)


def stock_in_pack(rig):
    """{clip: (times, poses, eases)}, {clip: meta} of the mocap moves already in the pack."""
    import retarget2d as r
    j, b = r.read_glb(OUT)
    ex = (j["scenes"][j.get("scene", 0)].get("extras") or {})
    pk, old = ex.get("pb_keys") or {}, ex.get("pb_moves") or {}
    clips, meta = {}, {}
    for an in j["animations"]:
        if an["name"] not in STOCK:
            continue
        tr = {}
        for ch in an["channels"]:
            s = an["samplers"][ch["sampler"]]
            tr[(ch["target"]["node"], ch["target"]["path"])] = (r.acc_array(j, b, s["input"])[:, 0],
                                                                 r.acc_array(j, b, s["output"]).astype(float))
        times = list(next(iter(tr.values()))[0].astype(float))
        hi = rig.i("Hips")
        poses = [({nd: r.q2m(v[k]) for (nd, path), (_, v) in tr.items() if path == "rotation"},
                  next(v[k] for (nd, path), (_, v) in tr.items() if path == "translation" and nd == hi))
                 for k in range(len(times))]
        clips[an["name"]] = (times, poses, (pk.get(an["name"]) or {}).get("e"))
        meta[an["name"]] = old.get(an["name"]) or {"name": STOCK[an["name"]][1], "cat": STOCK[an["name"]][0]}
    return clips, meta


def write(out, clips, meta, drafts, bj, bb, rig):
    import retarget2d as r
    ac, am = authored(drafts)
    clips.update(ac)
    meta.update(am)
    out = os.path.normpath(out or OUT)
    o, ob = r.pack(bj, bb, meshes=False, keep_anims=False, new_clips=clips, rig=rig,
                   extras={"pb_moves": meta, "pb_body": {"body": "ual_swordsman", "library": True}})
    total = r.save_glb(out, o, ob)
    print("wrote %s (%d KB, %d moves)" % (os.path.relpath(out, r.ROOT), total // 1024, len(clips)))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--check" in sys.argv:
        import anim3d
        import anim_audit
        import retarget2d as r
        B, notes = anim3d.Body(), []
        cl, _ = authored(True, notes, B)
        for n in notes:
            print("  note:", n)
        o, ob = r.pack(B.j, B.b, meshes=False, keep_anims=False, new_clips=cl, rig=B.rig)
        sys.exit(anim_audit.report_from(o, bytes(ob), B))
    if not args:
        print(__doc__)
    else:
        build(args[0], args[1] if len(args) > 1 else None, "--drafts" in sys.argv)
