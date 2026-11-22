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
