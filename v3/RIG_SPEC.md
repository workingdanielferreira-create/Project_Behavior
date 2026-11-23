# V3 rig + animation spec

The rules a 3D fighter (.glb) must follow so V3 and the Rig Forge 3D importer can use it.
The machine-readable copy is `rig_spec.json` (same content; the importer and the Blender
check script read that file). If the two ever disagree, `rig_spec.json` wins.

Decisions (Daniel, 2026-11-22):

- Skeleton: **Mixamo-compatible** bone names, so Mixamo stock moves drop straight in.
- Required beyond the body: **fingers**, a **small face set**, **weapon bones**.
- No secondary-motion chains (hair / cloth) in the standard rig for now.
- Moves: the current FX Studio actions, plus a **locomotion set** and **hit reactions**.

## 1. Units and orientation

| What | Rule |
|---|---|
| Units | 1 Blender unit = 1 m |
| Height | 1.5 to 2.0 m (default 1.7 m). The game scales the model so its standing height = 28 px (one body). |
| Facing | The character faces Blender's Front view (-Y). The glTF exporter turns that into +Z, which three.js expects. |
| Origin | Between the feet, on the ground. |
| Rest pose | T-pose or A-pose (arms 0 to 45° below horizontal). |

## 2. Skeleton

Names are Mixamo's. A `mixamorig:` / `mixamorig_` prefix is allowed; the importer strips it.

### Body (25 bones, required)

```
Hips
├─ Spine ─ Spine1 ─ Spine2
│                    ├─ Neck ─ Head ─ HeadTop_End
│                    ├─ LeftShoulder ─ LeftArm ─ LeftForeArm ─ LeftHand
│                    └─ RightShoulder ─ RightArm ─ RightForeArm ─ RightHand
├─ LeftUpLeg ─ LeftLeg ─ LeftFoot ─ LeftToeBase ─ LeftToe_End
└─ RightUpLeg ─ RightLeg ─ RightFoot ─ RightToeBase ─ RightToe_End
```

### Fingers (40 bones, required)

`{Left|Right}Hand{Thumb|Index|Middle|Ring|Pinky}{1..4}`, each chain parented to its hand.
Segment 4 is the tip end bone. Example: `RightHandIndex1 → RightHandIndex2 → RightHandIndex3 → RightHandIndex4`.

### Face (required)

Mixamo has no face rig, so these are added in Blender.

- **Bones** (children of `Head`): `Jaw`, `LeftEye`, `RightEye`.
- **Shape keys** (exported as glTF morph targets):
  - Required: `Blink_L`, `Blink_R`, `Mouth_Open`.
  - Optional: `Brow_Angry`, `Brow_Up`, `Brow_Sad`, `Mouth_Smile`, `Mouth_Grit`, `Eyes_Wide`.

### Weapons (required when the character uses a weapon, else optional)

| Bone | Parent | Where |
|---|---|---|
| `Weapon_R` | `RightHand` | grip, in the palm (main weapon) |
| `WeaponTip_R` | `Weapon_R` | weapon tip |
| `Weapon_L` | `LeftHand` | grip (second weapon) |
| `WeaponTip_L` | `Weapon_L` | second weapon's tip |

- The weapon mesh is skinned 100 % to its `Weapon_*` bone.
- To swap hands mid-move, key a Child Of constraint on the weapon bone in Blender, then bake the action.

## 3. Anchors (FX Studio / Rig Forge ids → bones)

The FX keep using today's anchor ids. The importer reads each one from a bone.
"start" = the bone's head, "end" = its tail.

| Anchor | Bone | Point |
|---|---|---|
| `root` | `Hips` | dropped to the ground |
| `hip` | `Hips` | start |
| `chest` | `Spine2` | middle |
| `neck` | `Neck` | start |
| `head` | `Head` | middle |
| `shL` / `shR` | `LeftArm` / `RightArm` | start |
| `shB` | `Spine2` | end (back of the shoulders) |
| `elL` / `elR` | `LeftForeArm` / `RightForeArm` | start |
| `haL` / `haR` | `LeftHand` / `RightHand` | start |
| `hpL` / `hpR` | `LeftUpLeg` / `RightUpLeg` | start |
| `knL` / `knR` | `LeftLeg` / `RightLeg` | start |
| `ftL` / `ftR` | `LeftFoot` / `RightFoot` | start |
| `wtip` | `WeaponTip_R` | start (no weapon: `RightHandMiddle4`) |
| `wtip2` | `WeaponTip_L` | start (no weapon: `LeftHandMiddle4`) |
| `figure` | — | the fighter's position, not a bone |
| `target` | — | the enemy, not a bone |

Some characters have extra 2D anchors (`coat_f`, `coat_b`, `xl1`..`xl6`). They have no standard
bone; the importer lets you point each one at any bone.

## 4. Animation clips

- **30 fps.** One Blender Action per clip. The clip's name is the game action name below.
- **In place.** The sim moves the fighter. The hips may bob up and down but stay over the origin
  (Mixamo: tick "In Place").
  Exception (2026-11-23): an attack / action clip may travel; V3 turns hips ground travel of >= 0.25 m into root
  motion (README "Root motion"). Locomotion, hit reactions, dodges and switches stay in place.
- **Timing in the game** comes from the character's action length (frames × frame ms), as now.
  The importer stretches each clip to fit, and you set hit / release frames there, not in Blender.
- A missing optional clip plays its **fallback** (which may fall back again).

### Core (FX Studio actions)

| Clip | Loop | Required | Fallback |
|---|---|---|---|
| `idle` | yes | yes | |
| `run` | yes | yes | |
| `attack_normal` | | yes | |
| `attack_normal_N` (N = 2..9, chain steps) | | | `attack_normal` |
| `attack_special` | | yes | |
| `attack_special_N` | | | `attack_special` |
| `ultimate` | | yes | |
| `ultimate_N` | | | `ultimate` |
| `idle_ultimate` | yes | | `idle` |
| `defend` | | yes | |
| `defend_reflect` | | | `defend` |
| `defend_recovery` (guard break) | | | `stagger` |
| `parry` | | | `defend` |
| `switch_in` | | | `dash` |
| `switch_out` | | | `dodge_back` |
| `transform` | | | `ultimate` |

### Locomotion

| Clip | Loop | Required | Fallback |
|---|---|---|---|
| `dodge` (forward / generic) | | yes | |
| `dodge_back`, `dodge_left`, `dodge_right` | | | `dodge` |
| `walk` | yes | | `run` |
| `sprint` | yes | | `run` |
| `dash` (burst forward: snap, dash-in) | | | `dodge` |
| `jump` | | | `idle` |
| `air` (airborne / flying idle) | yes | | `idle` |
| `air_move` | yes | | `air` |
| `fall` | yes | | `air` |
| `land` | | | `idle` |
| `turn` (180° on the spot) | | | none = instant turn |

### Hit reactions

| Clip | Loop | Required | Fallback |
|---|---|---|---|
| `hit_light` | | yes | |
| `hit_heavy` | | | `hit_light` |
| `hit_air` | | | `hit_heavy` |
| `impact` (used by some FX Studio files) | | | `hit_light` |
| `stagger` (parried / perfect-parry) | | | `hit_heavy` |
| `knockdown` | | | `hit_heavy` |
| `getup` | | | `idle` |
| `ko` (ends on the floor, last frame held) | | yes | |

**Minimum set for a playable fighter (9 required clips):** `idle`, `run`, `attack_normal`,
`attack_special`, `ultimate`, `defend`, `dodge`, `hit_light`, `ko`. `walk` and `sprint` are
recommended next.

## 5. Export (Blender glTF)

- File: `characters/<name>/<name>.glb`, beside `character.json` and `<name>.fxkit.json`.
- Format glb, +Y up, selected objects (armature + its meshes).
- Mesh: apply modifiers, UVs, normals.
- Skinning on (4 weights per vertex at most). Shape keys on, with "Use Sparse Accessor if better" OFF
  (`export_try_sparse_sk = False`): three.js r128, which V3 uses, fails on the empty sparse shape keys Blender writes.
- Animation on, mode **Actions**, always sample, 30 fps.
- Materials: exported, but the game swaps them for its toon / ink look and keeps the base colour texture.

### Budget (proposed, can be changed)

*These limits are my proposal for 8 fighters in a browser, not measured yet.*

| | Max |
|---|---|
| Triangles | 30,000 per fighter |
| Bones | 100 (the standard rig is about 72 with weapons) |
| Texture size | 2048 px |

## 6. Mixamo route

1. Upload the model (T-pose) to Mixamo, auto-rig it with fingers ("Standard Skeleton").
2. Download each move as FBX, "In Place" ticked, 30 fps; the first one "With Skin".
3. In Blender: import the FBX files, rename each Action to its clip name above.
4. Add `Jaw`, `LeftEye`, `RightEye`, the weapon bones and the shape keys.
5. Export the .glb as in section 5.

## 7. Rigify route

Rigify's deform bones (`DEF-spine`, `DEF-hand.L` ...) don't match these names. Either
rename / retarget them to the Mixamo names before export, or the importer gets a Rigify name
table later. Mixamo naming stays the standard.

## 8. Free CC0 route (Quaternius + Mesh2Motion, scripted)

Both libraries are CC0 (public domain, commercial use allowed, no credit required) and share one
skeleton, the UE-mannequin set (`root`, `pelvis`, `spine_01`, `upperarm_l` ...). Two scripts in
`tools/blender/` turn them into a fighter on this rig, without the Blender UI
(`pip install bpy`; Blender 5.3's module needs Python 3.13):

1. Download Quaternius **Universal Animation Library** 1 and 2, Standard (free) editions
   (quaternius.itch.io), and clone `github.com/Mesh2Motion/mesh2motion-assets`.
2. `python m2m_bake.py <mesh2motion-assets>/rigs/human m2m_keys.json`: samples Mesh2Motion's
   human clips (they animate control bones; this reads the deform bones) and resamples 24 -> 30 fps.
3. `python ual_to_spec.py UAL2_Standard.glb UAL1_Standard.glb out.glb m2m_keys.json`
   (the files from each pack's `Unreal-Godot/` folder, NOT the `_RM` root-motion ones): renames
   the bones to Mixamo names, adds `HeadTop_End`, `Jaw`, the eyes and `Weapon_R` / `WeaponTip_R`
   (blade out the thumb side of the fist) with a plain blade mesh, keeps the clips named in the
   two scripts' `CLIPS` tables and exports as in section 5.

`characters/ual_swordsman/ual_swordsman.glb` is the result (35 clips, 13.8k triangles, 71 bones,
1.83 m). Known gaps:

- **No face shape keys** (the mannequin has no face). Add them in Blender to make the body spec-complete.
- Clips end on a neutral standing pose, and the non-sword clips (run, kicks, power-up ...) don't close
  the hand round the grip. Trim / fix in Rig Forge 3D.
- The motion is realistic mocap. The anime feel (holds, snaps, smears) is added on top in Rig Forge 3D.
- Mesh2Motion's rest pose is not byte-identical to Quaternius' (worst bone end ~0.4 units apart),
  but the clips are stored as local rotations and play correctly on the Quaternius body (checked by
  eye in Rig Forge 3D).

## 9. Clips from a character's 2D moves (scripted)

`v3/tools/retarget2d.py` builds `characters/<name>/<name>.glb` from the section 8 body plus one clip per 2D action,
posed from `character.json`'s per-frame joint anchors with depth inferred from bone lengths (details in
`v3/README.md`, "Animations from the 2D moves"). Done for `puck` (13 clips, no weapon), `ronin_copy` (12 clips,
katana), `hooded_blades` (14 clips, two blades: adds `Weapon_L` / `WeaponTip_L` + a `blade_L` mesh) and `Sueko`
(10 clips, no weapon), then every other character with joint data: new_fighter, pewpew, puff, rapid, sniper, swordsman_rig, sync, thear, thear_copy, tough. `ronin` and `nobody` have no joint
data and keep the shared body. The files are clips-only (skeleton + clips + `pb_body` {body, weapons {R, L}}, no mesh,
0.2-0.5 MB each); V3 and Rig Forge 3D put them on the shared body.

## 10. Swapping the placeholder body for the final model

`ual_swordsman.glb` is a placeholder. Every character's clips are bone-named and stored with the skeleton they were
made on, and `v3/js/retarget.js` moves them onto whatever body is loaded, in V3 and in Rig Forge 3D. It carries each
bone's world rotation change from rest, lines up the new rest pose first (T-pose or A-pose), and scales the hips' move
by hip height. So a new body needs:

1. **A humanoid skeleton with RIG_SPEC (Mixamo) bone names.** Accepted as they are: Mixamo auto-rig output (the
   `mixamorig:` / `mixamorig` prefix is ignored), Quaternius / Mesh2Motion / Unreal-mannequin names (`pelvis`,
   `spine_01`, `upperarm_l` ...). Other rigs (Blender Rigify, VRoid ...): rename the deform bones to section 2's names
   in Blender before export. Fingers and toes are optional; missing bones are simply skipped.
2. **Facing +Z with +Y up** (glTF default; Mixamo and Blender glTF exports already are). Any size (V3 scales it
   to 1.8 m), any rest pose.
3. **Weapon bones for blades:** `Weapon_R` / `WeaponTip_R` (+ `Weapon_L` / `WeaponTip_L`) with meshes named `blade` /
   `blade_L` (section 3). Without them the clips still play, just with no blades. `ual_to_spec.py` shows how to add
   them by script; `retarget2d.py` adds the left pair when `Weapon_R` exists.
4. **Its own clips for what the 2D moves don't cover:** `hit_light`, `hit_heavy`, `ko`, `dodge`, air / jump ...
   (section 4 names and fallbacks). Mixamo / Quaternius packs supply these.
5. Save it as `characters/ual_swordsman/ual_swordsman.glb` (or point `BODY_GLB` in `v3/tools/build_kits.py` and
   `BODY` in `v3/tools/retarget2d.py` at the new file) and run `run_v3.bat`.

Optional, for the closest match on very different proportions: `python v3/tools/retarget2d.py --body new.glb`
re-solves every character's 2D clips directly on the new body (this overwrites Rig Forge 3D edits in the character
files).

Checked 2026-11-22: Puck's and Hooded Blades' clips on the old script-built ronin body (other bone axes, other
proportions) match the placeholder pose for pose.

## 12. Clips are stored as key poses

Every clip (character files and the shared body) holds only its key poses plus scene extras `pb_keys` (the ease
into each key, per clip or per track); V3 and Rig Forge 3D tween the frames in between (`v3/README.md`, "Clips are key
poses + tweening"). A clip without `pb_keys` (e.g. a fresh Blender / Mixamo export) still plays as it is, frame by
frame; `v3/tools/keyreduce.py` turns it into key poses.

## 11. Authored key-pose clips (anim3d)

Clips can be authored as key poses in `characters/<name>/<name>.anim3d.json` and baked by `v3/tools/anim3d.py`
(details in `v3/README.md`, "Authored key-pose clips"). They follow section 4 (names, in place, fallbacks) except the
rate: **60 fps**, so a strike can snap in one frame. Every clip, authored or not, should pass
`v3/tools/anim_audit.py` with no hard fault.
