"""Rig Forge 3D hero move packs: the Paragon heroes' animations as stock library moves (Daniel 2026-11-26).

One pack per hero, `characters/ual_swordsman/paragon/<Hero>.glb` = the shared body's skeleton (no mesh) + one clip
per animation stored as key poses (`pb_keys`, keyreduce.py), scene extras `pb_moves` {clip: {name, cat, src}} and
`pb_pack` {hero, set}. Rig Forge 3D lists the packs in its "Move pack" dropdown (Pose + move library); like
ual_moves.glb they are NOT game clips: V3 plays a move only once you apply it to an action and save.

Source: Daniel's export of Epic's Paragon animations retargeted to UE5 Manny (FBX, one folder per hero, sub folders by
kind: Attack, Ability, Jog, Emote ...; Daniel checked the licence 2026-11-26). *_MSA duplicates are skipped.

    python -I blender/paragon_moves.py <...>/KallariManny kallari_bake.glb       (bpy: bake every clip onto the body)
    python paragon_library.py kallari_bake.glb Kallari                          (key poses -> paragon/Kallari.glb)
    python paragon_library.py --recat ../../characters/ual_swordsman/paragon/*.glb   (categories / DROP changed: rewrite them)
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
        "stun": "Stun", "recall": "Intro & menu", "idle": "Idle", "idles": "Idle", "knockback": "Knockback",
        "ult": "Ability", "fire": "Attack"}
# clips at the top of a hero's folder (no sub folder): category from the name's words, first match wins
NAME_KEYS = [
    (r"aimoffset|^ao$|aim$|^(l|r|c|lb|rb)[cud]$", "Aim offset"),
    (r"^(death|dead|die|dying)", "Death"),
    (r"^(stun|stunned)", "Stun"),
    (r"^(knockback|knock|knockdown|knockup|launch|airborne|getup|bound)", "Knockback"),
    (r"^(hitreact|hit|flinch)", "Hit react"),
    (r"^(evade|dodge|roll|dash)", "Evade"),
    (r"^(emote|taunt|dance|laugh|cheer|wave)", "Emote"),
    (r"^(recall|respawn|levelstart|selectscreen|frontendpose|frontend|spawn|intro|victory|defeat|lobby)", "Intro & menu"),
    (r"^(ultimate|ult|ability|cast|q|e|r|rmb|lmb|special|spell|channel)$", "Ability"),
    (r"^(attack|primary|melee|combo|slash|swing|punch|kick|fire|shoot|shot|throw)", "Attack"),
    (r"^(jump|land|fall|apex|doublejump|airdash)", "Jump"),
    (r"^(turn|turninplace|rotate)", "Turn in place"),
    (r"^(travelmode|travel)", "Travel mode"),
    (r"^sprint", "Sprint"),
    (r"^jog", "Jog"),
    (r"^(run|walk|locomotion|strafe|start|stop|pivot|slope)", "Locomotion"),
    (r"^(idle|stand|rest|breathe)", "Idle"),
]


# categories left out of the packs (Daniel 2026-11-26: too many near-identical clips / not fight moves)
DROP = {"Jog", "Aim offset (idle)", "Intro & menu"}


def name_cat(name):
    words = [w.lower() for w in re.split(r"[_\s\-]+", name) if w]
    for rx, cat in NAME_KEYS:
        if any(re.search(rx, w) for w in words):
            return cat
    return "Other"


def label(clip):
    """'Attack__Attack_GuardBreak_A' -> ('Attack', 'Attack GuardBreak A')."""
    parts = clip.split("__")
    name = parts[-1].replace("_", " ").strip()
    if len(parts) == 1:
        return name_cat(parts[-1]), name
    sub = parts[-2]
    return CATS.get(sub.lower(), sub.replace("_", " ").strip().capitalize()), name


def recat(path):
    """Re-label a built pack's moves and leave out the DROP categories (key poses read back exactly, not reduced)."""
    import retarget2d as r
    bj, bb = r.read_glb(r.BODY)
    rig = r.Rig(bj, bb)
    j, b = r.read_glb(path)
    ex = j["scenes"][j.get("scene", 0)].get("extras") or {}
    pk, old = ex.get("pb_keys") or {}, ex.get("pb_moves") or {}
    hi = rig.i("Hips")
    clips, meta = {}, {}
    for an in j["animations"]:
        nm = an["name"]
        cat, name = label(nm)
        if cat in DROP:
            continue
        tr = {}
        for ch in an["channels"]:
            sm = an["samplers"][ch["sampler"]]
            tr[(ch["target"]["node"], ch["target"]["path"])] = (r.acc_array(j, b, sm["input"])[:, 0],
                                                                 r.acc_array(j, b, sm["output"]).astype(float))
        times = list(next(iter(tr.values()))[0].astype(float))
        poses = [({nd: r.q2m(v[k]) for (nd, path), (_, v) in tr.items() if path == "rotation"},
                  next(v[k] for (nd, path), (_, v) in tr.items() if path == "translation" and nd == hi))
                 for k in range(len(times))]
        clips[nm] = (times, poses, (pk.get(nm) or {}).get("e"))
        meta[nm] = dict(old.get(nm) or {}, cat=cat, name=name)
    o, ob = r.pack(bj, bb, meshes=False, keep_anims=False, new_clips=clips, rig=rig,
                   extras={"pb_moves": meta, "pb_pack": ex.get("pb_pack") or {},
                           "pb_body": {"body": "ual_swordsman", "library": True}})
    total = r.save_glb(path, o, ob)
    print("recat %s: %d of %d moves kept (%d KB)" % (os.path.basename(path), len(clips), len(j["animations"]), total // 1024))


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
        if label(nm)[0] in DROP:
            continue
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
    if "--recat" in sys.argv:
        for x in a:
            recat(x)
    elif len(a) < 2:
        print(__doc__)
    else:
        build(a[0], a[1], a[2] if len(a) > 2 else None)
