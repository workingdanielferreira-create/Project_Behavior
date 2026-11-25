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
- `R` / `L` `grip`: "fwd" (default) / "rev" (reverse grip); `twirl` deg = the weapon spun in the fingers. A key change
  of grip = a flip in the fingers on the way. Keep the hand OUT from the body while it flips / twirls (the blade sweeps
  the forearm's plane) or the audit flags a blade through the body.
- Travel (2026-11-23): moves may travel (V3 root motion, README "Root motion"); library moves should start mid-stride
  and end moving, not back in a guard (Daniel: "very mobile game").
- `fR` / `fL`: `ankle` target, `pole` (knee), `yaw`, `pitch` (+ = toes down). Same ankle value on two keys =
  planted, no sliding. Lift a foot through an in-between key (ankle y up) when it steps.
- Each key's `ease` is how the move INTO it eases: `snap` (strikes: most of the move at once, then settle),
  `out` (overshoot / follow-through), `in` (anticipation into a strike), `inout`, `linear`, `hold`.

Rest numbers (ual_swordsman, 1.83 m): hips 0.917, shoulders y 1.44 x +-0.19, arm 0.27 + 0.27, leg 0.40 + 0.43,
ankle y 0.104 x +-0.09, blade ~1.0 m out of the thumb side of the fist (perpendicular to the forearm).

## Attitude: spine, hips, shoulders, line of action (Daniel 2026-11-23, with reference sheets)

Daniel: "they have backs and spines that bend ... hips and shoulders rotate: it creates emphasis and telegraphs
actions". Upright, square, polite poses are rejected. Every key (`v3/tools/library/gen_moves.py` `key()` /
`attitude()` does this by default for library moves):
- **Line of action**: strikes and wind-ups are ONE C-curve: planted foot -> pelvis tilt -> spine side bend -> head
  tilt all bend the same way. In-between / prowl keys use contrapposto (pelvis tilted against the shoulders).
- **Hunch**: never stand straight; the chest carries forward and the head glares UP at the target from under the brow.
  Hits crunch the chest into the strike side; wind-ups arch the chest open; air keys arch the back.
- **Hip-shoulder separation**: wind-up = chest coiled further back than the hips; hit = hips lead, chest a beat
  behind; follow-through = chest whips past the hips.
- **Shoulder girdle** (`clav` [lift, forward]): wind-up pulls the sword shoulder back and shrugs it; the hit drives it
  forward and down; the free shoulder counters.
- **Stances** (his references): wide and deep, feet ~1.2-1.5 m apart, one leg locked straight, the front knee buried;
  the hips drop until the legs reach. Hits put the weight on the front foot (long straight back leg), wind-ups sit
  back on the loaded leg. Arms all the way out on hits, the free hand flared low and wide as a counterweight.
- **Air**: never a pencil jump: body pitched forward, one knee tucked high, the other leg trailing straight back with
  the toes pointed; spins tuck both knees.

## Unarmed fighters and Daniel's review notes (Puck attack_normal, 2026-11-24/25)

- **Fists**: clip `"fists": true` (or per hand `fist: true`) = wrist LOCKED straight (only the forearm turns the fist;
  `blade` = where the thumb side points) and a real punching fist (base knuckles past square, fingers rolled in).
  "Never make a fighter hit with his fingers": whenever a fist points at the target, the FOREARM points through the
  knuckles at it (thumb up on hooks / cocked, turned over on an overhand, knuckles up on a guard at the jaw).
- **Line of action**: one smooth curve from the back foot through the hips, up the back and out along the striking
  arm. Let the pelvis carry a good part of the lean (a big `spine` pitch on a small hips pitch = hunched hook in the
  upper back), keep the head ON that curve (not cranked up, not drooping), extend the leading arm along it
  (`gen_puck.line()`).
- **Spine controls are relative to the parent's TURNED axes**: once the hips yaw, `spine` pitch tips the chest
  sideways. Pose the chest / head in WORLD terms and solve the relative angles (`gen_puck.relative()`); measure the
  forward lean (hips -> neck) instead of trusting the numbers. A `roll` before a big yaw eats the forward lean.
- **Reach and the shoulder girdle**: `reach` is measured from the shoulder BEFORE the clavicle moves; a clav driven
  forward ~30 deg costs ~15 cm, so a straight punch needs `reach` ~0.66 m.
- **Commit**: bend the back; a punch moving forward folds the body over and the fist follows through past the target.
  Check the punch's LINE against the drawing (over-and-down vs under-and-up). Frame 1 is often the WIND-UP. Never add
  hits Daniel did not describe ("hook follow up" = the follow-through of the one hook). Shoulders pull back and down
  on a wind-up, never shrug into the neck; a cocked arm folds (elbow back, fist close), not a straight wing.
- **Open palms** (kamehameha, 2026-11-25): per hand `palm: true` + `fing` + `curl` (anim3d); `blade` = where the palm
  faces. A wrist bends back only ~60-70 deg (`PALM_WRIST` 75): locked arms can't hold palms square to the target, so
  cup them toward each other (~27 deg). Kamehameha hands stack VERTICALLY (heel to heel, top fingers up, bottom down);
  thrust arms LOCKED straight and level (bent, flared elbows read as arms crossed in an X: Daniel "what is happening
  with his arms"); in the charge both arms fold (elbows 60-75 deg), never a straight stick across the belly.
- **Keys inherit what they leave out**: anim3d carries a missing control (e.g. `clav`) over from the key before, so a
  pose solved per key (gen_puck `meet`) differs from the clip unless the key sets it. Measure the BAKED clip.
- **Review loop**: `bash v3/tools/puck/review/go.sh <clip> <tag>` -> `v3/tools/puck/review/out/<clip>_keys_<tag>.gif`
  (each key 1.1 s: 2D frame | side | 3/4 | front) + `_motion_` GIF; send both, score /10 honestly, take his
  corrections. One move at a time.

## Review questions (Daniel 2026-11-23): ask them of EVERY clip before showing it

1. **"Why is he holding his weapon like that? What's wrong with his wrist?"** A held sword sits about square to the
   forearm; the wrist only angles it (~20-30 deg). Measure the wrist bend per frame: more than a few frames past 60
   deg = the blade directions fight the arm (gen_moves.py keeps blades within `WRIST_OFF` 25 deg of square to the
   arm; anim3d "blade off by" notes = the solver could not get there).
2. **"Why does he float around like that? What's wrong with his physics?"** Measure, don't eyeball:
   - a stepping foot averages <= ~7.5 m/s (a sprint stride ~2 m in ~0.25 s); a planted foot never slides;
   - the hips cross the ground <= ~6 m/s between keys (a lunge), except a deliberate flash step (`flash` keys);
   - flight time matches height: apex = HANG (1.5) x g t^2 / 8, the rise eases out and the fall accelerates in;
     push-off and landing absorb take ~0.1 s each. A jump that rises 0.45 m in 0.3 s is on wires.
   `physical_timing()` in gen_moves.py retimes segments to these limits; anim3d's `physics` clips give the body a
   lunge (never a one-frame snap across the floor) and the feet their own swing timing + lift.
3. **"Have I ever seen movement like that in any media?"** Name the reference (ZZZ, Kingdom Hearts, DMC, Sekiro,
   Bleach shunpo for flash steps...). Ground is covered by real strides or by an explicit flash step, never by
   skating between two planted feet.

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
