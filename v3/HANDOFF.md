# V3 handoff (2026-11-22)

Read this first in a new session to pick up the V3 (3D) work where it stopped.

## Where V3 is now (all merged to `main`)

- **Window build** (PR #310): `v3/` is the 3D game, three.js r128 bundled. `run_v3.bat` opens it in an
  Edge / Chrome app window. It has in-game title / teams / settings / controls / pause / results screens.
  Code layout is in `v3/README.md`.
- **Parry + speed gravity** (PR #311):
  - `v3/js/parry.js`: Ctrl+Space parry, a perfect / normal window, counters, and AI rolls.
  - `v3/js/gravity.js`: speed sets the flight ceiling.
  - The earlier 2D (`laser/`) version was reverted on purpose. Keep parry / gravity in V3 only.
- **Real characters** (PR #312):
  - `v3/tools/build_kits.py` packs `characters/*` into `v3/data/kits.gen.js` (gitignored, rebuilt by
    `run_v3.bat`).
  - `v3/js/realkits.js` turns them into V3 kits.
  - `v3/js/fx2d.js` plays each fighter's FX with FX Studio's own runtime (`tools/fx/studio/*.js`,
    loaded unchanged). The FX happen in a 2D space centred on the fighter (x = camera right,
    28 px = one body), drawn on camera-facing cards in the 3D scene (behind / front of the body).
  - Daniel's direction: "no need to create a whole new engine for this placeholder; let the FX occur in
    their 2D space but respect the 3D environment".
- **Not ported yet:** unique abilities, states / transformations, blinks / travel movements, FX
  intercepts. Bodies are still toon stand-ins (`v3/js/models.js`).
- **Data quirks:**
  - `characters/ronin/character.json` has max_hp 100; `ronin_copy` is the usable one.
  - `swordsman_rig` has 100000 HP (a test dummy).

## Decisions made

- **Tooling** (researched 2026-11-22):
  - Don't rebuild Rig Forge / FX Studio from scratch.
  - 3D bodies + animation come from **Blender** (glTF / .glb export; Rigify for humanoid rigs) and/or
    **Mixamo** (auto-rig + stock moves; humanoid only).
  - Claude builds a small local **"Rig Forge 3D"** importer (three.js page). It loads a .glb, maps
    clips to game actions, picks anchor bones (hand, weapon tip, head), sets timing / scale / palette,
    and writes the `character.json` layout.
  - **FX Studio stays local** and keeps all gameplay data (damage, triggers, conditions, dodge, movement).
    3D FX styles come later, likely on **three.quarks** (three.js particle system; licence shown as MIT
    on third-party listings, not yet checked on the licence file). Effekseer is a later option for
    cinematic ultimates.
- **Cascadeur**: the free tier can't export glTF / FBX (that needs the paid Indie plan), so it's not
  the free route.

## Blender plugin

2026-11-22 cloud session: no Blender plugin tools and no attached computer. Blender is NOT installable on
Daniel's company laptop (no admin). Use the cloud `bpy` route above instead.
Daniel added a Blender plugin, but the cloud session could not see it (no connector / plugin / tools
listed). Run the next session **in the Claude desktop app on the machine where Blender and the
plugin are installed**, and check that its tools are available before starting.

## Reference for rigs and animation (design reference only)

Zenless Zone Zero showcase on skowt.cc (e.g. Ellen: https://skowt.cc/a/C7sbRpSCm).

- **Licence on the page:** "Official assets from Zenless Zone Zero. Non-commercial fan use only" and
  "© All rights reserved by miHoYo". Do not import or trace their models; study only.
- **Move set** (from the viewer):

  | Group | Moves |
  |---|---|
  | Idle | Still, Idle, Idle (AFK), Idle (city), Idle (city 2) |
  | Move | Walk, Run, Sprint, Dodge |
  | Combat | Combat run, Switch in, Basic attack, Dash attack, Counter, Assist, Chain attack, Ultimate |
  | Extras | Home screen, Showcase, Showcase 2, Signal search |

- **Rig** (Pose tab):
  - Body controls: head, neck, chest, spine, hips, shoulders, elbows, wrists, knees, ankles.
  - Separate Hands (fingers) and Face sets.
  - Hair / apron / skirt move as secondary motion.
  - Model listed as 1.62 m.
  - No bone names or counts are shown.

## Latest (2026-11-22, later)

- Puck and Ronin (ronin_copy) have 3D animations made from their 2D ones: `v3/tools/retarget2d.py` ->
  `characters/puck/puck.glb`, `characters/ronin_copy/ronin_copy.glb` (ual_swordsman body, replaces the old bpy-built
  ronin_copy body; `build_ronin3d.py` can still rebuild that). V3 now puts a kit's own .glb on it
  (`build_kits.py` packs `PB3_BODIES`, `glbody.js` picks per kit and plays an action's own clip by its 2D name).
- Daniel's choices: ual_swordsman body, ronin_copy as the Ronin source, inferred depth, wired into V3.
- Then Hooded Blades + Sueko the same way (`hooded_blades.glb`, `Sueko.glb`). Hooded Blades' far-hand blade
  (wtip2): Daniel chose to add a left blade (`Weapon_L` / `WeaponTip_L` + `blade_L` mesh, only in its own .glb).
- Then the rest: new_fighter, pewpew, puff, rapid, sniper, swordsman_rig, sync, thear, thear_copy, tough (each `characters/<name>/<name>.glb`). Not possible: `ronin`, `nobody` (no joint
  anchors). Size note: each .glb carries its own copy of the mesh + kept body clips (~2.5 MB), so
  `v3/data/body.gen.js` was ~50 MB of base64.
- Slimmed (Daniel 2026-11-22: "share one mesh and slim the files"): character .glb files are clips-only (0.2-0.5 MB,
  8 MB for all, was ~40 MB); body.gen.js ~10 MB. `v3/js/retarget.js` (V3 + Rig Forge 3D) retargets clips onto
  whatever body is loaded. Daniel: the current model is a PLACEHOLDER, and swapping in a model from Mixamo /
  Quaternius etc. must need very little adjustment -> RIG_SPEC section 10 (checklist), tested on a body with
  other bone axes. Rig Forge 3D opens clips-only files on the shared body (Pick shared body…, remembered) and saves
  clips-only.
- Not done yet: Puck's hair lines (xl1..4) and 2D stretch / smear (bone scale) have no 3D counterpart.

## Animation quality pass (2026-11-22, later)

- Audit of Hooded Blades' 2D-guessed clips (`v3/tools/anim_audit.py`, against the body's motion capture): elbows /
  knees bending backward in 74 % of frames, off their hinge 46 %, off balance 50 %, sliding feet 13 %, wrist past range
  8 %. Cause: `retarget2d.py` guesses depth per frame with no pole vectors / joint limits / continuity.
- Daniel's choices: author 3D key poses (2D only for timing / hit frames), write a project skill
  (`.claude/skills/v3-animation`), start with the attack_normal chain. Feel = ZZZ snap + KH spins; body turns freely.
- Confirmed by Daniel: Hooded Blades holds both blades in a FORWARD grip; blades swept back = winding up a horizontal
  double slash; bent knees = ready to lunge / dash, not a crouch. Ask him whenever a move's intent is unclear.
- Done: `v3/tools/anim3d.py` (solver + baker), `v3/tools/anim_audit.py`, `characters/hooded_blades/hooded_blades.anim3d.json`.
- 2026-11-25 (review of Hooded Blades): `anim_audit.py` now matches clip tracks to the shared body's bones BY NAME.
  Rig Forge 3D's re-save (upload 2026-11-24) stores the nodes in another order (45 of 75 shifted), and the old index
  match audited the wrong bones (feet "70 cm through the floor" even in idle). Correctly ordered files audit the same
  as before. Hooded Blades' `attack_normal` (hit 1) = Daniel's Rig Forge 3D version in the .glb (14 keys); Daniel
  2026-11-25 "replace the old with the new": the old authored hit-1 keys were removed from `hooded_blades.anim3d.json`
  (still in git, commit 9ad02e6) and from `pb_body.anim3d`, so `anim3d.py hooded_blades` only bakes attack_normal_2.
  Do NOT run `retarget2d.py hooded_blades`: it regenerates every clip not in the spec from the 2D frames and would
  wipe his hit 1 (true for any Rig Forge 3D edit). `anim3d.py <name> --clips <clip>` bakes only the named clips.
- 2026-11-25: Hooded Blades attack_normal_2 round 1 (draft) authored in `v3/tools/hooded/gen_hooded.py` from the 2D
  frames (Daniel "go ahead" on the reading; the old 2D-guessed clip had knees backward on 34/43 frames, arms never
  extended). Now: no hard faults, off balance 0, every step averages <= 7.5 m/s, hips <= ~6.6 m/s, 26 stored keys.
  Waiting for Daniel's review. Also fixed in anim3d.py: `full_keys` dropped each key's `bease`, so a "snap" key's
  hips always took "out" (affects library moves only if they are rebaked).
- First hit 1 was REJECTED by Daniel (hands stuck at the face, arms never extend, blades unreadable, no weight shift).
  Lesson: key poses as large stills beside the 2D frames first, shown to Daniel before animating (skill section
  "Key poses as stills FIRST"). Hit 1 rebuilt from six poses matched to 2D frames 7, 10, 11, 14, 17, 18 and retimed
  onto the 2D frame times; Daniel said "replace it with the latest version". Solver gained `reach` / `elbow` / `knee`
  controls, turn-then-lean, ground contact and stepping feet. **Next:** Daniel's verdict on the new hit 1 in game,
  then hits 2..5 the same way (stills first).

## Oathkeeper & Oblivion keyblades on Hooded Blades (2026-11-25)

- Daniel uploaded "Oathkeeper and Oblivion (Kingdom Hearts)" (Sketchfab, PronoesPro, CC-BY-4.0: credit in
  `characters/weapons3d/CREDITS.md`) and asked to put them on hooded_blades, animated in line with the oath_oblivion FX
  presets. His picks: hands as the FX (Oathkeeper right, Oblivion left); decimate (~4k tris each); the held blade
  HIDES while its FX copy is out (one of each blade); draft EVERY FX move.
- Done: `characters/weapons3d/*.glb` (`v3/tools/blender/keyblades.py`), weapons3d.js shape `mesh` + `pbwFxHeld`,
  build_kits packs them, Rig Forge 3D "Modelled" shape, FX Studio 3D reads them; README "Modelled weapons".
- Drafts (NOT baked, `approved: false`, in `v3/tools/hooded/gen_hooded.py` DRAFTS): attack_normal_3 / _4 (Pierce & Chop),
  attack_normal_5 (Satellite), attack_special (Oathkeeper charged thrust, FX Hold rides the LEFT hand), attack_special_2
  (Oblivion counter-spin), switch_in (kick > flying thrust). Each is timed to its FX beats and posed from the 2D frames;
  audit: no hard fault. Review loop `bash v3/tools/hooded/review/go.sh <clip> <tag>` (keyblades in the renders).
  Bake after his OK: `python v3/tools/hooded/gen_hooded.py --approve <clip>[,<clip>]` then
  `python v3/tools/anim3d.py hooded_blades --clips <clip>`. attack_normal (his own) and attack_normal_2 untouched.
- Not confirmed (ask): which way the keyblade teeth face (roll 0 = teeth on the weapon's edge side; `keyblades_on.py
  <roll_R> <roll_L>` turns them); the keyblades' size (grip -> tip 1.05 m Oathkeeper, ~1.15 m Oblivion).
- Arcs pass on attack_normal_3 (Daniel 2026-11-25, /motion-arcs-supervisor, "fix at the keys"): `review/arcs.js` +
  `arcs.py` sample hips / chest|hips / head|chest / hand|shoulder / keyblade tips at 60 fps (`build_preview.py --game` =
  the stored key poses tweened as V3 does) and flag kinks (> 55 deg turn or > 2.2x speed pop in one frame). Fixed at
  the keys: coil eases in AND out (it arrived at full speed and cornered into the pierce), the 2-frame "pierce held"
  hold removed (hands stalled and reversed), the patch "raise" became the chop's breakdown on the over-the-top arc
  (0.375, inout, hips carry the lunge), Oathkeeper cocked high at the pierce (overlap), default key tolerance (the
  loose one cut a straight corner into the recovery). Chest + head layers clean. Left on purpose: the chop's 4-frame
  over-the-top snap (FX lands it at 0.423), the stick on the hit, Oblivion's rip-out reversal, the anticipation
  reversal at the coil (chest wound left, whips right).
- **Next:** Daniel's verdict on the six drafts' stills, one move at a time (attack_normal_3 first, after its arcs pass).

## Key poses + tweening (2026-11-22, later)

- Daniel: editing meant fixing every frame ("instead of baking every frame, work through key frames and let the
  tweening fill in the in-betweens"); scope = every clip of every character, 2D-drawn clips reduced to key poses,
  edited in Rig Forge 3D; and "collapse the animation panel that shows all anchors' changes, use the framing style of
  the original Rig Forge" -> filmstrip of key-pose cards, per-pivot timeline folded under "Pivot keys (advanced)".
- Done: `keyreduce.py`, `js/keytween.js`, pb_keys format, all characters + the body rebuilt, Rig Forge 3D key mode +
  filmstrip, audit tweens the same way. Characters edited locally in Rig Forge 3D (not pushed) keep their old frame-by-
  frame clips until re-saved / rebuilt (the updater never overwrites local character edits).

## Original Rig Forge features -> Rig Forge 3D (2026-11-22, Daniel picked)

Picked: Actions panel (with settable length), Tween panel (in-betweens per key pose, hold, easing, range), Mirror +
face left, Reference images, Pose + move library, Weapon editor. Not picked: IK solve + arc guides, Character tab +
PNG / package export. Part 1 done (actions, length, tween, mirror / turn / centre); part 2 done (reference images incl.
the character's own 2D drawings behind the figure); part 3 done (pose + move library, body moves as stock); part 4 done (weapon editor, built in V3 too).
Tween panel follow-up (Daniel 2026-11-22): remove tween = "Tween to the next key pose" tick box per key pose + Remove
tween / Restore (From-To) and Remove all / Restore all, like the 2D "In-between from this keyframe" toggle. Off = ease
`hold` on every pivot keyed there (still, then a cut; the game already plays hold), the pivot's own ease kept on the key
as `pe` and given back on Restore (picking an ease drops `pe`).

Move library expansion (Daniel 2026-11-22: "combat animations for swords, dual swords, katana, ethereal swords,
pistols, great swords"). Daniel picked: library pack only (no game clips replaced); katana + ethereal = look for
references and author them; add a pistol shape. Done: `ual_moves.glb` (24 Mesh2Motion moves: Sword / Dual swords /
Great sword / Pistol), Rig Forge 3D loads it, pistol shape. Authored moves (all approved 2026-11-23) (Katana: iai
draw-cut, kirioroshi, chiburi + noto, battojutsu dash slash; Ethereal: summon, command point, sweep + volley, rain of
blades) in `v3/tools/library/moves.anim3d.json`, references = iai nukitsuke / kirioroshi / chiburi / noto and anime
battojutsu; ethereal hands are fists (anim3d has no finger controls yet). Mark a clip `"approved": true` and run
`python v3/tools/move_library.py -` to add it.
Daniel 2026-11-23: approved all 4 katana moves, then all 4 ethereal moves -> in the pack (32 moves).
UAL1 upload (Daniel 2026-11-23, FBX `UAL1_Standard.fbx`): picked fight-useful clips only, grouped by type. Done:
`v3/tools/blender/fbx_moves.py` (FBX -> body, armature-space transfer; checked vs the body's own UAL1 copies of
Death01 / Hit_Chest / Roll / Walk / Sprint: worst joint gap 1.6 - 2.8 cm) + `move_library.py` (`UAL1` table,
`STOCK`, builds merge into the pack). Pack = 51 mocap moves (+27 `u1_*`: Movement, Reactions, Unarmed, Magic,
Pistol, Sword); skipped: T-pose, sitting, swim, drive, dance, fixing, pick-up, push, interact, formal walk, talking /
torch idles.
UAL2 upload (same day, `UAL2_Standard.fbx`, same picks): +25 `u2_*` (Sword 9 incl. the body's own attack / dash /
heavy combo / block as library copies, Shield 4, Unarmed 3 (hook, throw), Movement 7 (ninja jump, slide, climb),
Reactions 2 (knockback, get up)); `fbx_moves.py <fbx> <out> UAL2`. Checked vs the body's UAL2 clips: 0.9 - 2.8 cm.
Pack = 76 mocap moves. Skipped: T-pose, chest, consume, farm, fold-arms / lantern / rail / phone idles, yes / no,
tree chopping, carry walk, zombie.
Move classes (Daniel 2026-11-23): he likes the body's attack_normal / attack_normal_2 / attack_special / ultimate
(Quaternius UAL2 mocap: urgency, decisiveness, fluidity) and wants many more at that level in classes Aggressive,
Stylish, Defensive, Counter. Free capture is exhausted (UAL2 Standard's sword clips are all already used; UAL PRO is
paid) -> he picked HAND-POSED new sword moves, ~5 per class, one class at a time. Aggressive first, focus = horizontal
sweeps, backhand slashes, spinning follow-ups.
Mobile rebuild (Daniel 2026-11-23: "very mobile game; moves progress forward, never return to the start; kicks,
forward <-> reverse grip mid-attack, blade spins; some cover a lot of ground; few keys, let the tween do the rest").
His picks: rebuild the 14 hand-posed moves (mocap stays), add ROOT MOTION to V3, replace the approved ones now (they
left the pack until he approves the new stills). Done: all 14 rewritten by `v3/tools/library/gen_moves.py` (replaces
gen_aggressive.py): each travels 1.6 - 4.4 m, starts mid-stride and ends stepping on, 5-9 authored key poses
(`key_tol` [0.08, 0.22] keeps the stored keys at 14-27 with spins / twirls); kicks (et_command back kick,
ag_spin_backhand hook kick, ag_backhand_spin push kick), reverse grip + twirls (kt_iai, kt_chiburi_noto,
kt_dash_slash, ag_sweep_return, ag_backhand_spin, ag_cyclone), air keys (kt_kirioroshi, et_rain, ag_low_high_spin).
Audit: no hard fault. All 14 `approved: false`: `ual_moves.glb` = the 24 mocap moves only until he approves;
`ual_moves_drafts.glb` has all 38. anim3d.py gained per-hand `grip` ("fwd" / "rev") + `twirl` (deg) and per-clip
`key_tol`; V3 glbody.js gained root motion (README "Root motion").
Attitude pass (same day, Daniel: "they look like good-two-shoes ... they have backs and spines that bend", "hips and
shoulders rotate ... telegraphs actions", "research lines of motion", plus reference sheets of wide low stances, flying
lunges, spread arms): gen_moves.py `attitude()` + `key()` now pose every key with a line of action (C-curve on
strikes / wind-ups, contrapposto between), hunch + glaring head, hip-shoulder separation (coil / hips lead / chest
whips), shoulder girdle `clav` (new anim3d per-arm control), stances x2.6 wider with the hips auto-dropping so the
legs reach, weight onto the front foot on hits, straight sword arm + flared free hand, air keys tucked / trailing.
Rules written into the v3-animation skill ("Attitude"). Audit: no hard fault. Still waiting for his approval.
Review + physics pass (same day; Daniel: "ask yourself: what's wrong with his wrist? why does he float? have I seen
movement like that in any media?"). Measured: wrists bent 60-76 deg most of the time, feet stepping 1.5-3.4 m in
0.03-0.13 s (skating), jumps rising 2-4x higher than gravity allows for their airtime. Fixed: natural wrist
(`WRIST_OFF`), anim3d `physics` clips (body lunges instead of a one-frame snap, feet swing on their own timing with a
real lift), `physical_timing()` (stride / lunge speed limits, gravity-timed jumps, flash steps flagged), lower jumps.
Also from the review: class attitudes (`PROFILES`: Aggressive brawler / Katana low compact / Ethereal tall open),
two-hand katana grip (anim3d `L.hilt`, kirioroshi), curved / sideways travel (`PATHS`: side, arc, hook), varied
entries for the six Aggressive moves, the dash exit's fist no longer at the face. The three questions are in the
v3-animation skill ("Review questions").

## Training mode + jumps (2026-11-23)

- Daniel: "training mode: only 1 character on the field, no opponent; a training settings menu to place dummies
  anywhere" and "change flight from speed = height to R / F incline / decline; only specific characters can stay in
  flight (a future FX Studio 3D toggle); for now R = jump with a double jump, then gravity".
- His picks: per-dummy behaviour Stand / Guard / Fight back, HP refills + combo readout; placement on a top-down map;
  F = fast fall for ground fighters; the AI jumps too.
- Done: `js/training.js` (+ Training screen in `menus.js`, title button, pause items), `js/gravity.js` rewritten (jump,
  double jump, fast fall, AI jumps, flyers keep R / F flight with no speed ceiling), Settings "Speed gravity" removed,
  kit flag `flight` (fxkit `flight.enabled`, packed by `build_kits.py`, none set yet). See README "Screens" / "Jumps".
- Known limit: FX Studio FX hit only your target (the nearest dummy); shots and stand-in melee hit every dummy.

## FX Studio 3D (2026-11-24)

- Daniel: "create the FX Studio 3D: the same function the initial FX Studio played for 2D: the movement of the actions,
  the FX of the actions, the visuals, the start and spot locations".
- His picks: a new page on the same `<name>.fxkit.json` (3D settings beside the 2D data); the FX **keep their 2D anime
  feeling** ("2.5D with cell shading", no 3D FX), so FX Studio's drawings are laid on cards placed in 3D; "start and
  spot locations" = both where each FX starts / lies AND where the body starts / ends the move; FX hit **every enemy
  they touch**; first build = preview foundation + FX editor + action movement + damage + V3 playback.
- Done: `v3/js/fx3d.js` (shared runtime: lanes per action, `fx3d` lay / tilt / anchor / offset / size / ink / depth,
  3D anchors from bones, every-enemy hits through the newly exported `FXK.resolveHits`, `move3d` planner),
  `v3/js/fxlive.js` (replaces `fx2d.js` in the game + training), `v3/tools/fxstudio3d.html` + `FX Studio 3D.bat`, the
  updater lists it (3 = FX Studio 3D). README section "FX Studio 3D".
- Fix (Daniel 2026-11-24, "snaps to this stupid pose ... for the remainder of the timeline"): the preview timeline was
  the action + a fixed 700 ms tail with the body switched to `idle`. Now the timeline = the action's own length + only
  as long as its FX are still alive (`measureTail`, capped at 700 ms), and past the action's end the body HOLDS the
  clip's last pose (never idle).
- Fix (Daniel 2026-11-24, "the fx are not following the action I select" = the FX movement choice is ignored, seen on
  hooded_blades): the effects' keyframes (`keys`, e.g. blades `f8: motion.kind = travel`) overrode the panel value
  mid-action and the studio had no key view. His pick "panel wins + keyed badge": keyed rows show a ◆ badge with ×,
  and changing a keyed setting drops it from every key (`dropKeyed`), so the pick plays the whole action.
- **Next:** Daniel's verdict in the studio and the game; then likely per-effect lay presets for the most-used styles,
  keyframing the 3D placement, and the not-yet-ported parts (blinks, states, intercepts).

## Little planet + World Studio 3D (2026-11-24)

- Daniel: "make the world environment more like a little planet like we had in v1; settings for the planet and the
  environment such as destructibles, environment additions, planet size, gravity".
- His picks: a **real globe you can walk all the way round**; destructibles = pillars / boulders, ground damage,
  breakable scenery, **each individually togglable**, each with its **own regrow time** (0 = stays broken); additions =
  sky (moons, ring, stars), ground cover, atmosphere, landmarks; gravity = jump & fall strength + launches that fly round
  the globe; look = **randomised from all toggled assets**; settings in a **separate World Studio 3D** tool; the planet
  replaces the arena with a toggle back to the flat one.
- Done: `js/world3d.js` (shared runtime + schema), `js/planet.js` (game glue), `tools/worldstudio3d.html` +
  `World Studio 3D.bat`, `build_kits.py` packs `characters/world3d.json` -> `data/world.gen.js`, updater option 4.
  README "The little planet + World Studio 3D".
- Not yet: rubble that stays (Daniel did not pick it), gravity tied to planet size (not picked). (FX hitting scenery and
  beams carving trenches: done 2026-11-25, below.)
- **Next:** Daniel's verdict in game + studio.

## FX follow the planet + deep craters (2026-11-25)

- Daniel: "make the 3D FX respect the gravity of the planet: FX that move keep their distance from the ground as they
  travel" (Puck's attack_special beam shot straight off the curve) and "add depth to the craters and let moving FX leave
  craters, like v1's world".
- Cause: the 3D cel-shaded FX shapes use their own shader (`fx3d.js TOON_VS`), which skipped the globe bend, and tubes /
  cards had one segment along their length. Fixed: the bend in `TOON_VS` + segmented tubes / cards.
- His picks: moving FX **hit & break scenery and keep going**; craters as a **cut-in bowl** (stencil hole, not a dented
  ground mesh); ground marks from **beams (trenches), low flyers (furrows) and big impacts (craters)** (not shots on
  impact); previews in **World Studio 3D only** (FX Studio 3D stays flat).
- Done: World Studio 3D section "FX and the world" (`fxworld`) + ground `crater_depth_pct` / `trench_depth_pct` /
  `lip_pct` / `debris` (`max_marks` default 90 -> 120); `world3d.js _bowl` / `_digMats` / `kick` / `_hideCover`;
  `fx3d.js Runner.worldFx`; `planet.js planetFx` / `digChain`; knockback trenches use the same chains. README "The little
  planet" (Ground damage + FX and the world).
- Checked headless (Playwright + SwiftShader): Puck's charged laser curves round the globe and digs a trench; a pillar on
  its line is chipped (30 x 60 %), Pewpew's Thunder Bullet breaks one, Hooded Blades' card blades chip one; World Studio
  test blasts leave deep craters; FX Studio 3D loads with no errors.
- **Next:** Daniel's verdict in game (beam height setting `beam_low_m` 1.6 m: a beam aimed slightly upward only digs
  until its head passes that height).

## Knockback tracking shot (2026-11-24)

- Daniel: over-the-shoulder camera follows a fighter knocked back, at its speed, after one continuous move + zoom in.
- His picks: trigger = a single hit carrying a fighter > 500 px; camera faces the way the fighter moves and never
  affects movement; ends on landing with a glide back; settings (+ a cooldown); also in Dynamic; also when YOUR fighter
  is knocked. README "Knockback tracking shot". **Next:** his verdict in game.
- Fix round (same day): Daniel saw thrown fighters "fly about halfway round the planet, then reverse" during the shot
  (the bend wrapped them past the far side). His picks: keep flying round (globe wrap), the globe follows the tracked
  fighter, anchor = short-way midpoint; dummies stay where they land; camera at a 3/4 angle; ease out just before the
  knockback ends.

## Parry stagger, sprint, 3D cel-shaded FX (2026-11-24)

- Daniel: perfect parry staggers the attacker 0.5 s; a sprint with continuous movement (no stop-start) at 3 speed levels
  (Lv1 base, Lv2 sprint, Lv3 per character toggled in FX Studio 3D); and "recreate the FX to be 3D in shape and 2D in cell
  shading, starting with laser, beam, particles, sprites, orbs, impacts".
- His picks: stagger = melee only (520 -> 500 ms); Shift hold = Lv2, double-tap + hold = Lv3; continuous at every level;
  the AI sprints when closing / chasing. FX: per-effect Render switch, 3D by default; flat bands + ink + white-hot core,
  all tunable; laser = a tapered tube stretched away opposite its motion (fast light); beams = tunable tubes; particles =
  3D chunks; impacts = 3D bursts; **hits use the 3D shape**.
- Done: `js/sprint.js` (+ fighter.js movement, input.js Shift, glbody.js sprint clip, realkits / build_kits `sprint`,
  FX Studio 3D Character rows); fx3d.js 3D shapes + 3D hits (+ `FXK.beamSegs / pulseRings / pulseShape / lifeT`
  exported from fxkit.js, no behaviour change); FX Studio 3D section "3D shape & cel look". README "3D cel-shaded FX"
  and "Movement: continuous + sprint".
- Not yet: blades, techniques (slashes, crescents), guns, kicks, defender styles as 3D shapes (still cards); the shapes
  are not lit by the scene (flat energy bands by view angle).
- **Next:** Daniel's verdict in game + studio; then the next batch of kinds as 3D shapes.

## Puck's 3D clips redone (2026-11-24/25)

- Daniel: "redo Puck's animations ... I need you to do the heavy lifting ... score it out of 10". His picks: one move at
  a time, key poses shown as GIF stills (2D frame | side | 3/4 | front) + a motion GIF, he corrects; moves travel; the
  ultimate is airborne (Big Bang Kamehameha: both arms cocked back, then a one-handed palm thrust, knee tucked); the
  shoryuken keeps its coiled crouch as a moving hold.
- Done: `v3/tools/puck/gen_puck.py` (writes `characters/puck/puck.anim3d.json`), review loop
  `v3/tools/puck/review/go.sh`, anim3d fist mode, audit skips unarmed blades. **attack_normal approved** ("good
  enough") and baked into `puck.glb`: wind-up > overhand right over the top and down > follow-through wrapped to the
  left shoulder > back into the dash (one punch). His corrections are in the puck notes and the v3-animation skill.
- **attack_special approved** ("bake it", 2026-11-25) and baked: kamehameha in place. Charge = wide low straddle, open
  hands cupped round a ball at the back hip (chest turned ~90 deg, upright); HA! = feet stay, hips drive forward,
  back leg locks out, arms locked straight and level, hands stacked vertically heel to heel, palms cupped ~27 deg round
  the beam. New: anim3d open-hand mode (`palm` / `fing` / `curl`, `PALM_WRIST`), `gen_puck.palm()` and `meet()`
  (solves a key until the wrists land on given points; `straight=` locks the arms). Gotcha he caught ("what is
  happening with his arms"): anim3d carries a control a key leaves out (e.g. `clav`) over from the key before, so a
  helper that solves a key alone must key it explicitly.
- **Overlap pass (2026-11-25), baked:** Daniel picked per-part lag in anim3d, ZZZ-snappy 1-2 frames. anim3d clip
  `overlap` (README "Overlap / follow-through") on both approved clips: before, every part started and stopped on the
  same frame; now hips > chest > arm > fist settle in turn, head loosest. "Pull body keys earlier": attack_normal's
  inner keys 25 ms early, the fist lands on the approved frames. Kamehameha "bake it" (10 -> 13 keys for the settle).
  Audit: no hard faults (a 170 deg forearm flip from the fist spring was fixed: directions spring on the sphere, Rfist
  1.75 frames). New moves get `overlap` from blocking.
- **Next, in order:** ultimate (Big Bang Kamehameha), attack_normal_2 (double axe handle
  overhead), attack_normal_3 (shoryuken uppercut jump), attack_normal_4 (180 spin > backhand), attack_special_2 (hands
  pumping forward and back). Puck's other clips are still the 2D-guessed ones (the audit's hard faults are theirs).

## 3D punches, kicks and impacts (2026-11-25)

- Daniel: "recreate the FX we have into 3D versions; start with punching motion effects and impact effects".
- His picks: scope = impact punch + kicks + ground FX + serious punch; fist path = from the real 3D fist out along the aim
  to FX Studio's reach (hits stay FX Studio's line); impact = forward 3D cone (flash / focus lines face the camera);
  **energy look first** (ink / gritty parts stay cards).
- Done: `fx3d.js drawStrike / impact3d / impactFrame3d / strikeEnv / drawSerious` + `strike_*` keys, FX Studio 3D
  "Strike" rows, exports `STRIKEFX.parts`, `KICKFX.parts`, `POWERFX.sp`, `HITFX.K` (no 2D change), 3D FX fade near the
  camera. README "3D punches, kicks and impacts".
- Checked headless (Playwright + SwiftShader): every style in a test kit, then Watch battles with Puck / Puff / Sync /
  Sueko / new_fighter: punches, thrust / spinning / rising kicks and the serious punch draw in 3D, hands / feet picked
  automatically, no errors; FX Studio 3D loads.
- **Next:** Daniel's verdict in game + studio.
- Daniel then: "ignore those other variations (ink / gritty), continue creating more 3D FX"; picked all four families, in
  order: sword slashes + crescents, gunfire + ki barrage, ethereal blades, auras + power techniques.
- **Batch 2 done: sword slashes + crescents** (`fx3d.js drawBlade` + band mesh, `blade_thick_pct`, README "3D sword FX").
  Checked headless: every style from FX Studio's presets renders, a Ronin (ronin_copy) battle runs with no errors.
  **Next batch: gunfire + ki barrage.**

## Next steps (agreed direction, not started)

1. **Done (2026-11-22):** `v3/RIG_SPEC.md` + `v3/rig_spec.json`. Mixamo-compatible skeleton,
   fingers, face set (Jaw / eyes + shape keys) and weapon bones required; no hair / cloth chains for
   now; clips = FX Studio actions + locomotion set + hit reactions, each with a fallback.
2. **Done (2026-11-22), cloud route** (Daniel can't install Blender on his company laptop):
   - Blender runs in the cloud session as the `bpy` package (`pip install bpy`, 5.3.0), no UI.
   - `v3/tools/blender/build_ronin3d.py` builds the ronin_copy test fighter by script: smooth anime-toon
     body (skin modifier), head, hair, face decals + 7 shape keys, katana; 72 bones on the spec; clips
     idle, run, attack_normal, attack_special, ultimate, hit_light, ko keyed by script (pose solver aims
     bones in armature space; weapon hand = blade direction first).
   - Output `characters/ronin_copy/ronin_copy.glb` (~0.95 MB, 15.8k triangles). `--renders DIR` writes
     Workbench pose frames (needs `libegl1` / `libgl1` from apt in the container).
   - Viewer: `v3/tools/blender/viewer_template.html` + `make_viewer.py` (embeds the .glb, three.js r128).
   - Export gotchas, both fixed in the script: sparse shape keys off (r128 can't read them) and shape key
     values reset to 0 before export (they exported at 1).
   - Open question for step 3: in r128, swapping the face (morph) meshes to MeshToonMaterial /
     MeshBasicMaterial made them disappear; the viewer keeps the loader's material for them. Cause not
     found yet.
   - Mixamo route stays open: Daniel downloads FBX in his own browser and uploads them; the cloud session
     converts them to the spec. Never take his account details.
3. **Rig Forge 3D, tool part done (2026-11-22):** `v3/tools/rigforge3d.html` + `Rig Forge 3D.bat`.
   Daniel's choices: edits = pose per keyframe + move anchors + add anchors + model placement; gizmo =
   rotation rings on every pivot (TransformControls + the reference's dark / light-blue discs, bright yellow
   view ring, white axis line while dragging) + move arrows on Hips; saved straight into the .glb
   (`pb_rig3d` scene extras: `edits` {clip: {bone: {rot: [{f, q}], pos: [{f, v}]}}} with q = local delta
   after the base rotation, `fade`, `anchors` {id: {bone, off (bone space, m), ground?, custom?}},
   `placement` {scale, height, yaw}). Baked into the clips on save, un-baked on open.
   Then (same day): skeleton tree panel + options cards. pb_rig3d version 2: anchors are
   {bone, t (0..1 along the bone), side [x,y,z], ground?, custom?} (v1 `off` still loads); `xbones`
   [{id, name, at (pivot / "a:<anchor>" / added bone end), len, rest [deg]}] exported as plain nodes with a
   rotation track in every clip; `attach` {Weapon_R: {bone, pos, quat, home}} = weapon on another bone /
   custom grip, its tracks become that grip + keys.
   Then (same day): Character dropdown above Clip, filled from a picked `characters` folder (recursive .glb
   scan, folder handle remembered in IndexedDB, one-click Reconnect), and afterimages / onion skin (0-5 frames
   before red / after green, step, wrap; per-ghost model clone + own mixer; stencil keeps the current pose clean).
   **Next:** V3 swaps its stand-in body for the .glb (sim actions / timing drive the clips, anchors +
   placement from `pb_rig3d`).
4. **Done (2026-11-24), the 2.5D route Daniel picked instead of 3D FX styles:** FX Studio 3D (see above).

Follow `CLAUDE.md` session rules: ask before implementing (pop-up questions); push, open the PR and
merge it.
