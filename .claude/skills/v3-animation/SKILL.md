---
name: v3-animation
description: Author, fix or review a V3 (3D) fighter's animation clips for Project Behavior - key poses on the RIG_SPEC rig with IK, pole vectors, joint limits, foot locking and anime timing, baked by v3/tools/anim3d.py and gated by v3/tools/anim_audit.py. Use whenever a request touches a character's 3D clips (attack / special / ultimate / idle / run / defend ...), their posing, timing, "physics", skeleton or rig, or asks to make a fighter move like Zenless Zone Zero / Kingdom Hearts.
---

# V3 animation (key poses on a real rig)

Daniel's bar (2026-11-22): clips that "rival Zenless Zone Zero and Kingdom Hearts". The 2D-guessed clips
(`v3/tools/retarget2d.py`) break that: knees / elbows bend backward or sideways, limbs flip, the body floats off
balance. Authored clips replace them one by one.

## Before posing anything: ASK

Daniel asked for this explicitly: if you are not sure what the character is doing in a move, ask (pop-up
questions) before posing. Look at the 2D frames first (`characters/<name>/<action>_NN.png`, joints in
`character.json` `anchors`), write your reading of the move frame by frame, and get it confirmed. Things he has
already settled are in the character's `<name>.anim3d.json` `notes`. Hooded Blades so far:

- Forward grip on BOTH blades. Blades swept back past the body = the wind-up of a horizontal double slash.
- Bent knees = ready to lunge / dash sideways, NOT a crouch.
- Feel: a blend: ZZZ snap and weight on the hits, KH (Oathkeeper & Oblivion) spins and arcs between them.
- The body turns freely in 3D (hips / chest open up on spins and spreads); strikes still land toward the target.

## Clips are KEY POSES (Daniel 2026-11-22)

Never ship a frame-by-frame clip: every clip is stored as key poses + `pb_keys` eases and tweened by V3 / Rig Forge 3D
(`v3/tools/keyreduce.py`, `v3/js/keytween.js`, README "Clips are key poses + tweening"). Authored keys stay keys;
reduce anything dense. Daniel edits in Rig Forge 3D's filmstrip (key-pose cards), so keep the key count low and put
keys on real poses (anticipation, strike, recoil, follow-through), not on every frame.

## Files

| File | What |
|---|---|
| `characters/<name>/<name>.anim3d.json` | the key poses (format `pb_anim3d`, see `v3/tools/anim3d.py` docstring) |
| `v3/tools/anim3d.py` | solver + baker: `python v3/tools/anim3d.py <name>` writes the clips into `<name>.glb`; `--check` audits without writing |
| `v3/tools/anim_audit.py` | `python v3/tools/anim_audit.py <name or .glb>`; exit 1 on a hard fault |
| `v3/tools/keyreduce.py` | dense clip -> key poses + eases; `--body` for the shared body |
| `v3/js/keytween.js` | V3: key poses -> tweened frames at load |
| `v3/tools/retarget2d.py` | 2D-guessed clips for everything not authored yet; it keeps authored clips (calls `anim3d.bake_file`) |

## Controls (body space: +Z forward to the target, +Y up, -X = the fighter's right / near side, metres, deg)

- `hips` `pos` (offset from rest hips; y < 0 = knees bend) and `rot` [yaw, pitch, roll] (yaw + = turn left,
  pitch + = lean forward, roll + = tip to the right).
- `spine` [yaw, pitch, roll] spread 25 / 35 / 40 % over Spine / Spine1 / Spine2; `head` over Neck / Head.
- `R` / `L` arm: `reach` = hand offset from its shoulder (0.55 m = arm straight; preferred over `hand`, it rides the
  torso), `elbow` = direction the elbow points from the shoulder (preferred over `pole`), `blade` direction, optional
  `roll`, `swivel`. Legs: `knee` = direction the knee points from the hip (preferred over `pole`).
- `hips.rot` / `spine` / `head`: the body TURNS first, then LEANS toward the target (+Z). Daniel's drawings lean
  55-65 deg with the head carried forward on the same line; keep the head pitch small (-10..-25) or the figure
  reads upright.
  Clip `"arm_space": "chest"` (use it): hand / pole / blade are given as if the chest were at rest, so the arms
  ride with the torso; body-space arms get left behind when the torso snaps.
- `fR` / `fL`: `ankle` target, `pole` (knee), `yaw`, `pitch` (+ = toes down). Same ankle value on two keys =
  planted, no sliding. Lift a foot through an in-between key (ankle y up) when it steps.
- Each key's `ease` is how the move INTO it eases: `snap` (strikes: most of the move at once, then settle),
  `out` (overshoot / follow-through), `in` (anticipation into a strike), `inout`, `linear`, `hold`.

Rest numbers (ual_swordsman, 1.83 m): hips 0.917, shoulders y 1.44 x +-0.19, arm 0.27 + 0.27, leg 0.40 + 0.43,
ankle y 0.104 x +-0.09, blade ~1.0 m out of the thumb side of the fist (perpendicular to the forearm).

## Key poses as stills FIRST (Daniel 2026-11-22, after a rejected clip)

Never show or merge a clip whose key poses Daniel hasn't seen. For each 2D key frame: render the 3D pose LARGE
from the side (same view as the 2D frame: camera on -X, fighter facing screen right) and a three-quarter view,
placed beside the 2D frame, and correct it until the silhouette matches: torso angle, head line, hand height and
distance from the face, blade lines, stance width, which leg is straight. Common misses: hands jammed against the
face (reach too short / too high), torso upright (lean too small, head pitched back), blades through the head
(angle them out over the shoulder), crouched / cowering when the drawing stands taller. Read the drawings, not
`anchors`: some frames' joint data doesn't match the image. Then retime the keys onto the 2D frame times (frame
index x frame_ms) and render the motion beside the 2D frames at the same times before shipping.

The solver helps: feet never go under the floor (ground contact), a foot that moves between keys steps through an
arc, planted feet stay put. An audit pass is necessary, never sufficient.

## How a move is built (the order matters)

1. Timing from the 2D action: clip `length` = frames x frame_ms; put the strike keys on the 2D strike frames
   (V3 stretches the clip to the action length, FX start frames stay in step).
2. Block the golden poses only (anticipation, strike, recoil / follow-through) on the hips and feet first: weight,
   stance width, which foot is planted. A strike drives from the back foot through the hips into the arm.
3. Arms and blades in chest space. Pick poles so the blade is reachable with little forearm twist (the solver
   also swivels the elbow up to `SWIVEL` deg and notes "blade off by" / "out of reach" when it can't).
4. Anime timing: hold the coil (moving hold, small drift, never dead still), snap into the hit in 1-2 frames
   at 60 fps, overshoot one key past the hit, settle. Overlap: head / chest lead or trail the hips by a key.
5. `python v3/tools/anim3d.py <name> --check` until no HARD line; then render and LOOK (side + rear + top) before
   showing Daniel. A pose that passes the audit can still read badly from the game camera.

## Audit (what "breaks physics" means here)

Measured against the body's motion-capture clips: knee / elbow bending backward or off its hinge, limb / wrist
past range, feet through the floor, legs through each other, blades / hands through the body, centre of mass
outside the feet while standing, planted feet sliding, flips (a limb spinning > 120 deg in 1/60 s while its hand
/ foot stays put). "very fast" and short "off balance" during a step or lunge are information, not faults.

## Rendering for review

Headless Chromium + `v3/lib/three.min.js` + `GLTFLoader.js`: pack a full-mesh preview with
`retarget2d.pack(body_j, body_b, meshes=True, keep_anims=False, new_clips=anim3d.bake_file(name), rig=Body().rig)`,
load it, set `mixer` time, render side (-X), rear-3/4 and top cameras with a `SkeletonHelper`, and send the
contact sheet to Daniel. Blades pointing at / away from the camera look short; check from another view
before "fixing" them.

## Session rules still apply

V3 only; ask first; syntax-check (`python -m py_compile`); push, open the PR and merge it. Update
`v3/HANDOFF.md`, `v3/README.md` and the character's `notes` with what Daniel confirmed.
