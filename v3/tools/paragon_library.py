"""Rig Forge 3D hero move packs: the Paragon heroes' animations as stock library moves (Daniel 2026-11-26).

One pack per hero, `characters/ual_swordsman/paragon/<Hero>.glb` = the shared body's skeleton (no mesh) + one clip
per animation stored as key poses (`pb_keys`, keyreduce.py), scene extras `pb_moves` {clip: {name, cat, src}} and
`pb_pack` {hero, set}. Rig Forge 3D lists the packs in its "Move pack" dropdown (Pose + move library); like
ual_moves.glb they are NOT game clips: V3 plays a move only once you apply it to an action and save.

Source: Daniel's export of Epic's Paragon animations retargeted to UE5 Manny (FBX, one folder per hero, sub folders by
kind: Attack, Ability, Jog, Emote ...; Daniel checked the licence 2026-11-26). *_MSA duplicates are skipped.

    python -I blender/paragon_moves.py <...>/KallariManny kallari_bake.glb       (bpy: bake every clip onto the body)
    python paragon_library.py kallari_bake.glb Kallari                          (key poses -> paragon/Kallari.glb)
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OUT_DIR = os.path.join(os.path.dirname(HERE), "..", "characters", "ual_swordsman", "paragon")
# sub folder (lower case) -> library category; the export's folder names vary per hero
CATS = {"attack": "Attack", "attacks": "Attack", "ability": "Ability", "abilities": "Ability",
        "emote": "Emote", "emotes": "Emote", "hitreact": "Hit react", "hitreacts": "Hit react",
        "jump": "Jump", "jog": "Jog", "sprint": "Sprint", "turninplace": "Turn in place",
        "travelmode": "Travel mode", "evade": "Evade", "evades": "Evade", "death": "Death", "deaths": "Death",
        "ao": "Aim offset", "aimingao": "Aim offset", "idleao": "Aim offset (idle)", "idle_ao": "Aim offset (idle)",
        "aoidle": "Aim offset (idle)", "ao_idles": "Aim offset (idle)", "idleaimoffset": "Aim offset (idle)",
        "stun": "Stun", "recall": "Recall", "idle": "Idle", "idles": "Idle", "knockback": "Knockback"}


def label(clip):
    """'Attack__Attack_GuardBreak_A' -> ('Attack', 'Attack GuardBreak A')."""
    parts = clip.split("__")
    name = parts[-1].replace("_", " ").strip()
    if len(parts) == 1:
        return "Other", name
    sub = parts[-2]
    return CATS.get(sub.lower(), sub.replace("_", " ").strip().capitalize()), name


def build(src_glb, hero, out=None):
    import keyreduce as kr
    import retarget2d as r
    bj, bb = r.read_glb(r.BODY)
    rig = r.Rig(bj, bb)
    j, b = r.read_glb(src_glb)
    names = [n.get("name") for n in j["nodes"]]
    remap = {i: rig.idx[n] for i, n in enumerate(names) if n in rig.idx}
    for an in j["animations"]:
        for ch in an["channels"]:
            ch["target"]["node"] = remap.get(ch["target"]["node"], -1)
        an["channels"] = [c for c in an["channels"] if c["target"]["node"] >= 0]
    jj = dict(bj)
    jj["accessors"], jj["bufferViews"], jj["buffers"] = j["accessors"], j["bufferViews"], j["buffers"]
    clips, meta = {}, {}
    for an in j["animations"]:
        nm = an["name"]
        times, poses = kr.clip_from_glb(rig, jj, b, an)
        if len(times) == 1:                                # a single pose (aim offsets): hold it 0.5 s
            times, poses = [0.0, 0.5], [poses[0], poses[0]]
        clips[nm] = kr.reduce(rig, times, poses)
        cat, name = label(nm)
        meta[nm] = {"name": name, "cat": cat, "src": "Paragon (Epic) %s, retargeted to Manny: %s" % (hero, nm.replace("__", "/"))}
    out = os.path.abspath(out or os.path.join(OUT_DIR, re.sub(r"[^A-Za-z0-9_-]+", "_", hero) + ".glb"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    o, ob = r.pack(bj, bb, meshes=False, keep_anims=False, new_clips=clips, rig=rig,
                   extras={"pb_moves": meta, "pb_pack": {"hero": hero, "set": "Paragon"},
                           "pb_body": {"body": "ual_swordsman", "library": True}})
    total = r.save_glb(out, o, ob)
    print("wrote %s (%d KB, %d moves)" % (os.path.relpath(out, r.ROOT), total // 1024, len(clips)))


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if len(a) < 2:
        print(__doc__)
    else:
        build(a[0], a[1], a[2] if len(a) > 2 else None)
