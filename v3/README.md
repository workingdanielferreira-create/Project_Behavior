# Project Behavior V3 — 3D

The 3D game, built on Playtest 2 (*Behavior 3D Playtest v2*), now in its own window.
Self-contained like `v2/`: nothing outside `v3/` is touched.

## Update

`update_v3.bat` (here) or `Update V3.bat` (game folder) runs `tools/update_v3.py`: downloads the newest
commit on `main` and writes only the V3 parts that changed — `v3/` (game + Rig Forge 3D + FX Studio 3D + World Studio 3D), `Rig Forge 3D.bat`,
`FX Studio 3D.bat`, `World Studio 3D.bat`, `Update V3.bat`, `tools/fx/studio/` (FX runtime V3 uses) and `characters/`. Local edits to `characters/`
files (e.g. a .glb saved from Rig Forge 3D) are kept, using the same `.sync_state.json` record as
`update_latest.py`. The 2D game files are left to `update_latest.bat`. Afterwards it asks:
1 = V3 game, 2 = Rig Forge 3D, 3 = FX Studio 3D, 4 = World Studio 3D, Enter = nothing. Installed commit: `.last_update_v3.json`.

## Run

```bat
run_v3.bat
```

Opens the game in an Edge or Chrome app window. The window has no address bar,
gets its own taskbar icon and keeps its own profile in `v3\.window-profile`.
F11 = fullscreen, Alt+F4 = quit. It works offline, because three.js r128 is
bundled in `lib/`. If neither browser is found, it opens `index.html` in the
default browser.

## Screens

Title → Fight / Training / Teams / Settings / Controls / Fullscreen. In a fight: Esc or P
pauses (Resume, Restart, Settings, Controls, Quit to title). After a fight:
Results (Rematch, Change teams, Title).

**Training** (Daniel 2026-11-23): your one fighter alone on the field with practice dummies (no opponent team).
The Training screen is a top-down map of the arena: click = drop a dummy (up to 8), drag = move it, right-click /
Delete = remove it; the panel picks your fighter and, for the selected dummy, its behaviour (**Stand** = never moves
or acts; **Guard** = blocks every hit, parries by chance; **Fight back** = its character's AI at half damage), its
character and its height (an air dummy hangs there). Saved with the settings. In training nobody is K.O.'d (HP refills
1.5 s after the last hit), a knocked-back stand / guard dummy drifts home, and the top readout shows the combo (hits
no more than 1.1 s apart), its damage, the best combo, the last hit and damage per second. Your target is the nearest
dummy; FX hit every dummy they touch (FX Studio 3D, 2026-11-24), and so do shots and the stand-in kits' melee. Pause → Training settings edits the dummies live (Back rebuilds them, your fighter keeps its state);
Restart training starts over. With no dummies your fighter only acts on your inputs and faces the way you move.

Menus work with the mouse or the keyboard:

- Up / Down: move between items
- Left / Right: change a value
- Enter: press
- Esc: back

Settings and teams are saved between sessions.

## Code layout (`js/`, loaded in this order by `index.html`)

| File | What it holds |
|---|---|
| `world3d.js` | **the little planet** (shared with World Studio 3D): settings schema + defaults, the globe bend (vertex shader), ground, sky, atmosphere, ground cover, landmarks, destructibles, debris, craters / trenches / scorch |
| `core.js` | constants (arena size, tick, body size), world settings + planet flag (`WORLD_CFG`, `PLANET`, `MAPW` x `MAPH`), maths helpers |
| `settings.js` | saved settings (control level, speed, camera, quality, teams) |
| `kits.js` | stand-in kits (fallback when `data/kits.gen.js` is missing) |
| `realkits.js` | real kits from `data/kits.gen.js` → V3 kits (actions, triggers, dodge, movement) |
| `renderer.js` | WebGL renderer, scene, toon / ink / additive materials, 2D→3D mapping (`V`, `VA`) |
| `arena.js` | the flat arena (planet off): floor, sky dome, floating rocks, pillars, rim, stars (`arenaG`) |
| `planet.js` | the planet in the fight: new world per fight, globe roll (anchor), collisions with pillars / scenery / landmarks, shots blocked, blasts, craters, trenches, gravity numbers `GRAV` |
| `fx.js` | **FX design**: primitives (slash, ring, dome, sparks, dust, star, crack, streak, moons, blades) |
| `state.js` | world state, timers (`later`, `ms2t`) |
| `glbody.js` | **.glb body**: parses `data/body.gen.js` once at boot, gives each fighter a skinned copy (toon + ink, kit colour), picks its clip from the fight state |
| `models.js` | **fighter rigs and models** (`buildBody`) |
| `movestyle.js` | **movement styles** (FX Studio `movement_style` phases) + intent speed table |
| `tempo.js` | fight rhythm intents (port of `laser/tempo.py`) |
| `director.js` | director heat: calm / build / burst |
| `motion.js` | drift & snap motion |
| `sprint.js` | **continuous movement + sprint**: speed levels Lv1 / Lv2 / Lv3, Shift (hold / double-tap), AI sprint choice, eased velocity |
| `gravity.js` | jumps: R = jump / double jump, F = fast fall, gravity; flight (R / F climb / descend) only for kits that can fly |
| `combat.js` | actions, triggers, hits, damage, stun, K.O., reactions, tagging, projectiles |
| `fx3d.js` | **FX 3D runtime** (shared with FX Studio 3D): the basic FX kinds as 3D cel-shaded shapes, the rest as FX Studio's 2D drawings on cards placed in 3D, 3D anchors from the bones, every-enemy hits (3D shapes hit with their 3D shape), `move3d` planner |
| `fxlive.js` | real kits' FX in the fight (one `FX3D.Runner` per fighter) + per-action 3D body movement (`move3d`) |
| `parry.js` | parry / deflect: Ctrl+Space timing windows, perfect-parry stagger + counter, shot reflect / deflect, AI rolls |
| `fxlib.js` | **FX animation**: every action effect (`runFx`) |
| `fighter.js` | fighter creation, per-tick update, altitude, wall / ground splats |
| `training.js` | training mode: dummies (stand / guard / fight back), target pick, HP refill, combo readout |
| `input.js` | keyboard commands |
| `camera.js` | camera modes (over the shoulder / dynamic / wide), cuts, shake, punch |
| `anim.js` | **animations**: pose, swing, lean, legs, recoil, flashes, shadows |
| `hud.js` | HUD, callouts, command bar, damage numbers, feel panel |
| `menus.js` | title, training (dummy map), teams, settings, controls, pause, results |
| `main.js` | game loop, fight flow, boot |

The files are plain scripts sharing one scope rather than ES modules, so the
game runs straight from disk (`file://`) without a local server. A file may
use anything declared in the files loaded before it. Code that runs at load
time has to respect that order; functions called later can reach anything.

## 3D bodies (spec)

In a fight every fighter wears ONE shared body mesh, `characters/ual_swordsman/ual_swordsman.glb` (RIG_SPEC section 8;
a placeholder until the final model, see RIG_SPEC section 10), tinted in its kit colour. `tools/build_kits.py` packs it
into `data/body.gen.js` (gitignored, rebuilt by `run_v3.bat`; ~10 MB with every character's clips). A kit whose folder
holds its own `<folder>.glb` (every character with joint data; only plain `ronin` and `nobody` have none) gets that
file packed too (`window.PB3_BODIES[folder]`): it holds only a skeleton + that character's clips (no mesh, 0.2-0.5 MB)
and `pb_body.weapons` {R, L}. `js/retarget.js` puts those clips on the shared body (unchanged while it is the
placeholder) and `js/glbody.js` merges them with the body's own hit / K.O. / dodge / air clips. Blades show on melee
kits only, in the hands the character's file names (`blade` right, `blade_L` left). No `body.gen.js` = stand-ins.
Clips: an action whose own clip is in the body (own bodies have one per 2D action, e.g. `attack_normal_basic`) plays it;
otherwise action -> `attack_normal(_N)` / `attack_special(_N)` /
`ultimate` / `transform` / `switch_in` / `defend`, stretched to the action's length; stun -> `hit_light` / `hit_heavy` /
`hit_air` / `knockdown`; K.O. -> `ko`; parry / block -> `parry` / `defend`; snap -> `sprint` (`dodge_back` going
away); moving -> `run`, still -> `idle`, in the air -> `air_move` / `air`. Missing clips fall back as in `rig_spec.json`.

`RIG_SPEC.md` (+ `rig_spec.json`) is the rig + animation spec for 3D fighters: Mixamo bone
names, fingers, face set, weapon bones, FX anchor → bone map, clip list with fallbacks, glb export.

First 3D test fighter: `characters/ronin_copy/ronin_copy.glb`, built by `tools/blender/build_ronin3d.py`
(runs on Blender's `bpy` Python package, no Blender UI). `tools/blender/make_viewer.py` makes a
self-contained viewer page for any .glb. V3 doesn't load the .glb yet.

## Animations from the 2D moves (every character with joint data)

`python v3/tools/retarget2d.py [name ...]` (default: puck ronin_copy hooded_blades Sueko; pass any other folder) (numpy only, no Blender) turns a character's 2D animations into 3D
clips on the ual_swordsman body and writes `characters/<name>/<name>.glb`: one clip per action in its
`character.json` (same name, frame_ms timing, stored as 3-8 key poses: see "Clips are key poses + tweening"; loops for idle / run). It reads the per-frame
joint anchors (hip, chest, neck, head, shoulders, elbows, hands, hips, knees, feet, weapon tip):

- 2D x = forward, 2D up = up; the near (R) limbs are on the viewer's side.
- Depth is inferred (Daniel 2026-11-22): every bone keeps its 3D length; a 2D limb shorter than its rig length swings
  the rest into depth (upper arm / thigh outward, forearm / shin back toward the shoulder / hip line).
- Pelvis / chest turn from how far apart the 2D hip / shoulder points are; spine, neck and head follow the 2D line.
- The blade points at the 2D weapon tip; no weapon (Puck, Sueko) = blade mesh removed. A second blade in the far
  hand (Hooded Blades, `wtip2`) adds `Weapon_L` / `WeaponTip_L` (Weapon_R mirrored) + a `blade_L` mesh to that
  character's .glb, aimed at `wtip2` the same way. Hands closed, feet flat, lowest foot
  on the floor plus the 2D air gap; clips stay in place (the sim moves the fighter).
- From the body at run time: hit reactions, K.O., dodges, air / jump clips. Its other attack / locomotion clips are left
  out so the character's own clips play through the fallbacks; a character with `parry` but no `defend` gets
  `defend` = parry.

Ranged kits (pewpew, sniper ...) keep the hand aimed at their 2D gun tip; V3 hides the blade mesh on non-melee kits.
Re-run it after changing a character's 2D animation; touch up the result in Rig Forge 3D (re-running overwrites it).
The character files are clips-only (skeleton + clips, no mesh); `--body new.glb` re-solves every clip exactly on another
body (RIG_SPEC section 10). The first run also gives the shared body its left blade (`Weapon_L` / `WeaponTip_L` +
`blade_L`, hidden unless a character holds a second blade).

## Clips are key poses + tweening (Daniel 2026-11-22)

Every clip of every character (and the shared body's own clips) is stored as KEY POSES only: the channels hold
just the key times (60 fps grid) and scene extras `pb_keys` {clip: {e: [ease INTO each key]}} or, after a Rig Forge
3D save, {clip: {b: {"Bone.quaternion": [eases]}}} (each bone its own keys). The frames in between are filled in by
tweening, the same in all tools: u = ease(into-ease, position in the segment), rotations slerp, positions lerp; eases
linear / smooth / inout / in / out / snap / hold / back.

- `v3/js/keytween.js` (`ktExpandAll`): V3 fills in the frames when it loads a .glb (glbody.js, before retargeting).
- `v3/tools/keyreduce.py`: `reduce()` = fewest key poses whose tweening stays within 3 cm (blade tips 7 cm) of a
  dense clip, best ease per segment; `max_keys` caps it. `retarget2d.py` keeps 3..8 key poses per 2D-drawn clip (about
  a third of the drawn frames), `anim3d.py` keeps every authored key, `python v3/tools/keyreduce.py --body` did the
  body's mocap clips (within 3 cm).
- Rig Forge 3D edits the key poses themselves (see below); `anim_audit.py` tweens the same way when it checks.

## Authored key-pose clips (anim3d) + animation audit

The 2D-guessed clips break physics (Hooded Blades, 2026-11-22 audit: elbows / knees bending backward in 74 % of
frames, 46 % bending off their hinge, the body off balance in 50 %; the body's own motion capture: about 0 %). So
clips are now authored as key poses, one by one, and replace the 2D-guessed ones:

- `characters/<name>/<name>.anim3d.json` (format `pb_anim3d`): per clip a `length` and `keys`, each key = controls
  (hips pos / turn, spine + head turn, hand + elbow pole + blade direction per arm, ankle + knee pole + yaw / pitch
  per foot) and how the move into it eases (`snap`, `out`, `in`, `inout`, `linear`, `hold`).
- `python v3/tools/anim3d.py <name>` solves every 1/60 s on the rig: two-bone IK with poles where the elbow / knee can
  only fold about its own hinge (measured from the body's mocap) and within its range, forearm twist + wrist limits for
  the blade, an automatic elbow swivel that saves twist, clavicles that follow the arm, planted feet that never slide,
  arms in chest space (they ride with the torso), smooth curves through the keys. Baked at 60 fps (a thrust can snap in
  one frame) into `<name>.glb`; other clips in the file are kept. `--check` audits instead of writing.
  `--clips a,b` bakes / checks only those clips (use it when the file holds a clip edited in Rig Forge 3D that the
  spec still has an older version of). NOTE: a full `retarget2d.py <name>` rebuild regenerates every clip that is not
  in the spec from the 2D frames, so it wipes clips edited in Rig Forge 3D (e.g. Hooded Blades' attack_normal). The new clips are written onto the file's
  bones BY NAME (a Rig Forge 3D re-save can reorder the nodes), and `anim_audit.py` reads them by name too.
- `retarget2d.py` keeps authored clips when it rebuilds a character (`pb_body.anim3d` lists them).
- `python v3/tools/anim_audit.py <name | file.glb>`: per clip, frames with knees / elbows backward or off their hinge,
  limb / wrist past range, feet through the floor, legs crossing through, blades / hands through the body, centre of
  mass outside the feet, sliding planted feet, flips (a limb spinning > 120 deg in 1/60 s while its hand / foot stays
  put), plus "very fast" turns (info). Ranges come from the body's motion-capture clips. Exit 1 on a hard fault.
- Done: Hooded Blades `attack_normal`. The project skill `.claude/skills/v3-animation` has the workflow and what
  Daniel confirmed about each move.

## Rig Forge 3D

**Collapsible menu (Daniel 2026-11-22).** Every section of the menu on the right folds on its title (▾); Collapse all
/ Expand all; **Hide menu** (top bar, or M) gives the 3D view the whole width. Folds and the hidden menu are remembered
(localStorage); every section starts collapsed to its header (Daniel: "collapse it to the headers").

**From the original Rig Forge (Daniel 2026-11-22), part 1.** **Actions** panel (replaces the Clip dropdown): every
action with its length and key count; Name + Rename; **Length (ms) + Set length** = how long the move plays in the game:
the clip and its key poses are retimed (`S.data.len`, undo-able) and on Save the FX file's `timing[action].frame_ms` =
length / frames (frames kept, so its FX stay in step; `character.json` `frame_ms` / `duration_ms` follow); Trigger
(`character.json`), Cooldown (FX `action_settings.cooldown_ms`); **+ Action** (0.5 s, the pose on screen as two key poses,
FX timing added), **Duplicate**, **Remove** (clip + FX timing; its FX effects stay). Needs the characters folder for
the file writes; add / rename / remove can't be undone. Key poses always fill the action like v1 (Daniel 2026-11-23):
Set length stretches them so the first sits on frame 0 and the last on the last frame, and a key-pose clip never fades
to the rest / T-pose (before the first key it holds the first, after the last it holds the last; Blend out only acts
on frame-by-frame clips). **Tween** panel per key pose: **In-betweens** = frames from this key pose to the next; a new
value makes that gap exactly that long and re-spaces the other gaps (in proportion) so the action keeps its length
(2 key poses: the one gap always fills it); **Stretch keys to fill the length** re-fits an older clip whose keys stop
early. Filmstrip **Duplicate** always works (v1): the copy goes right after the key pose, and with no free frame there the key poses are re-spaced to make room (length kept). **◀ / ▶** hop a key pose over its neighbours (re-spaced to make room at the clip ends); **Delete key pose** works down to none (1 key pose = a still pose). **Choppy steps** (0 = smooth; N = the pose jumps N+1 times on the way: anime timing), **Hold** (frames still first), Easing, **Apply to** key poses
a..b / All (copies the in-betweens too); stored per key (`st`, `h`) and in the file as `pb_keys` `s` / `h` per track (V3 keytween.js and
keyreduce.seg_u play them the same). Filmstrip: **Mirror L/R**, **Turn around** (180 deg on the hips), **Centre** (hips
over the feet spot); Shift = every key pose, one undo step.

**Part 2: reference images.** Panel "Reference images": an image per key pose (load / paste / Ctrl+V; shown from that
key pose until the next one with an image; Image → all key poses), or **Follow the character's 2D drawings**: its own
PNG frame at the same point of the move (characters folder needed), standing on the 3D floor at the 3D size (scale
from the 2D rig's leg length, ground = the idle feet) and following the camera. Behind (the 3D view turns
see-through) or in front, opacity, size, across / up-down offsets per action, **Side view** button (camera side on, like
the drawings). Kept in IndexedDB per character file, never in the .glb.

**Part 3: pose + move library.** ◆ poses (the whole pose on a frame, applied as a key pose; mirrored too) and ▶ moves
(an action's key poses with their tweens, times 0..1; applied to the current action, replacing its key poses, at this
action's length or the move's; mirrored = every key pose mirrored afterwards). Categories + search, Export / Import
(`pb_rf3d_library` JSON). **Body moves** = the shared body's own clips (hit reactions, dodges, sword attacks …) as stock
moves. Stored in IndexedDB ("lib"), shared by every character (bone names; fingers included).

**Move pack (weapon combat moves, 2026-11-22).** `characters/ual_swordsman/ual_moves.glb` = the shared body's skeleton +
library moves as key poses, scene extras `pb_moves` {clip: {name, cat, src}}. Rig Forge 3D lists them under their
category (read-only, like Body moves; hover = source), read from the connected characters folder by itself (hidden from
the character dropdown) or picked once with **Load move pack…** (kept in IndexedDB). `ual_moves_drafts.glb` (the same moves + the authored ones waiting for approval) is hidden too and loaded instead when present; Update V3 always overwrites both packs (generated, never kept as local edits). Not game clips: V3 never loads the
file. Now: Sword 9, Dual swords 2, Great sword 2, Pistol 11 (Mesh2Motion CC0 mocap via `v3/tools/blender/m2m_moves.py`; plus 27 Quaternius UAL1 Standard moves `u1_*` from Daniel's FBX upload 2026-11-23 via `v3/tools/blender/fbx_moves.py` (armature-space transfer, any bone axes): Movement 10, Reactions 3, Unarmed 2, Magic 4, Pistol 6, Sword 2; plus 25 UAL2 Standard moves `u2_*` (same route, table `UAL2`): Sword 9, Shield 4, Unarmed 3, Movement 7, Reactions 2 = 76 mocap moves; `move_library.py <src.glb>` now merges into the pack instead of replacing it
+ `v3/tools/move_library.py`; checked against the body's own copy of a Mesh2Motion clip: 2.5 cm). Katana and Ethereal
swords have no free mocap: they are authored key poses (Katana 4 + Ethereal swords 4 + Aggressive 6, rebuilt as travelling moves 2026-11-23 by `library/gen_moves.py`, waiting for approval; `ual_moves_drafts.glb` has them) in `v3/tools/library/moves.anim3d.json` (anim3d.py solver;
audit clean) and join the pack only once Daniel approved their stills (`"approved": true`, then
`python v3/tools/move_library.py -`). Weapon editor shape **pistol** (weapons3d.js: len = barrel, w = slide height,
handle = grip, guard = trigger guard, curve = grip rake; barrel along the edge side, roll turns it).

**Root motion (2026-11-23).** V3 clips were all in place; travelling moves are now allowed. `glbody.js glbPrepRM`
(at load): a clip whose hips end >= 0.25 m (ground plane) from where they started, and whose name is not a sim-driven
clip (`GLB_RM_SKIP`: idle / run / ko / getup / hit_* / dodge / switch_* / jump / defend ...), has its hips' ground path
taken out of the clip (hips keep their height, so cross-fades stay put) and kept in `clip.userData.rm`; `glbAnim`
moves the fighter's sim position along it while it plays (facing = body +Z, clamped to the arena). Solo + Battle.
Today only the body's `attack_normal_4` (0.3 m) qualifies among game clips; library moves applied to an action do.

**Fists (anim3d, 2026-11-24).** Per hand `fist: true` (clip `"fists": true` = every hand): the wrist stays locked
straight (the forearm twist alone turns the fist so its thumb side points along `blade`) and the fingers close into a
punching fist (`Body.fist`). Unarmed characters (Puck) use it; `anim_audit` skips the blade checks for hands their
`pb_body.weapons` says hold nothing. Puck's clips are authored in `v3/tools/puck/gen_puck.py` and reviewed with
`v3/tools/puck/review/go.sh <clip> <tag>` (GIF stills beside the 2D frames).

**Open hands (anim3d, 2026-11-25, Puck's kamehameha).** Per hand `palm: true`: `blade` = the way the PALM faces,
`fing` = the way the fingers point (made square to it), `curl` 0 (flat) .. 1 (cupped round a ball), all tweened between
keys. The forearm twist (within `PRONATE`) does what it can and the wrist bends the rest up to `PALM_WRIST` 75 deg (a
real wrist extends ~60-70 deg: a locked-arm kamehameha cups its palms toward each other instead of facing them square);
past that the solver notes "palm off by". Finger pose `Body.palm_pose` from the grip pose's own curl axes; the palm's
facing in the hand frame (`Body.palm_frame`) = the way a curling finger moves.

**Grip and twirl (anim3d, 2026-11-23).** Per hand `grip` "fwd" / "rev" (reverse grip: blade out of the pinky side)
and `twirl` (deg, the weapon turned in the fingers about the axis across the fist). Between a forward and a reverse
key the weapon flips 180 deg in the fingers while the fist's aim turns; `twirl` 360 = one spin. `blade` is always
where the blade points. Per hand `clav` [lift, forward] (deg) = shoulder girdle shrug / drive forward / pull back on top of the automatic follow. Left hand `hilt: true` = two-hand grip (left fist on the right weapon's handle). Clip `physics: true` = the hips travel with a lunge (never a one-frame snap) and a stepping foot swings on its own timing with a real lift; key `bease` = the hips' own ease (gravity: out going up, in coming down). Per clip `key_tol` [body m, tip m] = looser key reduction (fewer stored key poses).

**Part 4: weapon editor.** Panel "Weapons": Weapon 1 (right hand) / Weapon 2 (left hand): holds a weapon or not, and
"Build it here": shape (sword, katana, dagger, greatsword, rapier, cleaver) + length, width, thickness, curve, point,
guard, handle, grip (slides along the hand's weapon line), roll; copy from the other hand; reset. `v3/js/weapons3d.js`
builds it (child of the Weapon_R / Weapon_L bone, the body's skinned blade hidden) in Rig Forge 3D and in V3
(glbody.js glbBuild). Saved as `pb_body.weapons` {R, L} (true / false or the cfg); `retarget2d.py` keeps an edited cfg
when it rebuilds. The original's weight / swing settings drove its 2D blade drag, which V3 doesn't have (not ported).

**Key poses (Daniel 2026-11-22).** A clip with `pb_keys` opens as its key poses: they become the tool's own keys on
every bone over a still rest pose, so posing a key pose IS editing the clip and the frames up to the neighbouring key
poses follow (tweening). Posing between key poses adds a key there. Timeline (the original Rig Forge's frame cards):
a **filmstrip** of key-pose cards (side-view thumbnails, number, frame, tween to the next), **+ Key pose**,
**Duplicate** (copy halfway to the next), **← Move / Move →** (Shift = 5 frames, never past a neighbour), **Delete key
pose** (a clip keeps two), **Tween to next** (every pivot's ease on that frame); a strip of every frame (gold = key
pose); a scrub bar. The per-pivot timeline is folded away under **Pivot keys (advanced)**. 60 fps. Save writes key
poses only (each bone its own key times + `pb_keys.b` eases; no `pb_rig3d.edits` for these clips): checked
2026-11-22, a saved Hooded Blades plays back identical (0.00 cm) and stays key poses.

**Character files are clips-only** (Daniel 2026-11-22). Opening one (no mesh inside) shows its clips on the shared
body: taken from the connected characters folder (below) when it holds it, else the first time **Pick shared body…** asks for `characters/ual_swordsman/ual_swordsman.glb` (or the final model);
Edge remembers that file (IndexedDB) for later opens. Clips go through `js/retarget.js`, so another body works too.
Saving writes back the skeleton + clips + `pb_rig3d` / `pb_body` extras only, never the body's mesh.

`Rig Forge 3D.bat` (repo root) opens `tools/rigforge3d.html` in Edge. Pick a fighter from the **Character**
dropdown (above Clip): **Characters folder…** once on the repo's `characters` folder lists every .glb in it and
its subfolders (`<name>/<name>.glb` shows as `name`, others as their path; ↻ rescans). The folder is remembered
(IndexedDB); on a new visit the browser wants one click on **Reconnect**, then the last character reopens.
Saves still write straight into the picked .glb. **Open .glb…** / drag and drop still work. Then:

- **Afterimages (onion skin)** (View panel, on by default): see-through copies of the clip's pose on the
  frames before (red) and after (green) the current one, 0-5 each, fainter further away; **Step** spreads
  them (2 = every other frame), **Wrap** carries them round the clip ends. Shown while posing and playing,
  always behind the current pose (stencil), keys included. Settings live in the browser, not in the .glb.

- **Pose per keyframe.** Click a pivot dot (or pick it in the Pivot list), go to a frame and turn the X / Y / Z
  rings (red / green / blue; grey = free turn, yellow outer ring = turn about the view). The rings follow the
  mouse round the ring (the pointer is put on the ring's plane; a ring seen edge-on turns by dragging along
  it); **Shift** = 5° steps; the HUD shows the turn. A ring under the mouse wins over a nearby dot unless you
  press right on another dot. Hips also have move arrows (**Move**, `T`). Each change sets a key on that frame;
  frames in between blend, and **Blend out** sets how far a key fades before the first / after the last key
  (all the way right = the whole clip; frame-by-frame clips only, key-pose clips hold their first / last key). **Local / World** (`L`) picks the axes of the rings AND the arrows
  (anchors too): **World** = the scene's fixed X / Y / Z wheels whichever way the camera faces, **Local** = the
  selected bone's own axes as posed. The wheels are full circles (three's half circles spun to face the camera).
  `v3/lib/TransformControls.js` had the gizmo's space test inverted (it always drew Local); fixed there; the readout / HUD / status name the axes in use and say when a bone's own axes line up with
  World (then the switch looks the same).
- **Keys** (Daniel 2026-11-22). **◆ Key** (`K`) keys the selected pivot's pose as shown on this frame (also an
  untouched pivot = hold it); **Key whole pose** (`Shift+K`) keys every pivot with keys in the clip. **Delete key**
  (`Del`), **Delete all keys here** (`Shift+Del`), **Clear pivot in clip**. **Into next key** = how the move leaves
  that key: smooth (default) / linear / ease in / ease out / hold (snaps at the next key) / overshoot (stored
  as `e` on the key). **Copy pivot** / **Copy whole pose** (`Ctrl+C`: selected pivot, or the whole pose with
  nothing selected) and **Paste** (`Ctrl+V`) / **Paste mirrored** (`Ctrl+Shift+V`, left / right swapped and
  mirrored across the body's middle using the rest-pose frames) key the pose as it looked onto the current
  frame of any clip. **Timeline = dope sheet**: an All pivots row + one row per keyed pivot (+ the selected
  one), key shape = its ease, dashes = hold, faint ends = blend out. Click a key to jump to it (selects its
  pivot), drag to retime, **Alt + drag** to copy (a key already there is replaced), click / drag empty space
  to scrub. ◆◀ / ▶◆ jump between keys.
- **Pivots on the model.** Click a pivot dot for its rings. **Press and hold, or press and drag** a pivot to pull
  the body toward the mouse (keys on that frame): hand and foot pivots bend their arm / leg with a two-bone
  solver that keeps the elbow / knee bending the way it already does; other pivots bend up their chain (neck / head down the spine). **Hips**
  moves the body through the hierarchy while both hands and both feet stay planted (arms and legs re-bend, the
  weapon stays put), like the 2D Rig Forge's pelvis drag; **Shift + drag** the hips to move everything.
  Every mouse move re-solves from the pose the drag started with, so turns never pile up. **Collarbone**
  (Daniel 2026-11-22): a hand, elbow or shoulder pull past its reach swings it only by the missing bit, never
  more than **Joint limits > Collarbone** (default 30°) off the clip's own pose on that frame (an old
  over-swung collarbone is pulled back in on the next pull); its own rings are not limited.
- **Skeleton tree.** Every bone in its hierarchy (Hips > Spine > …), with each bone's anchors (◆) and added
  bones (✚) under it. It starts collapsed and opens down to whatever you select. FX anchors are hidden on the
  model unless their card's **Show this FX anchor on the model** is ticked (or **All FX anchors** in View). Click a row (or a dot on the model) to select it; its card opens
  under the tree.
- **FX anchors** (card): **Sits on** any bone, **Along bone** 0–100 % (pivot to end), typed X / Y / Z offset
  on top, **Snap to** start / middle / end / ground. On the model: **click** an anchor for its move arrows
  (slide along X / Y / Z) and rings (swing it around its bone's pivot, keeping its distance); **press and hold
  (0.25 s) or press and drag** to move it freely with the mouse, in a plane facing the camera. **+ Anchor here** on any bone card adds
  your own. Anchor spots are per character, not per frame.
- **Added bones** (the 2D Rig Forge's added lines): **+ Bone** from a pivot, an anchor or another added bone's
  end; name, **Starts at**, length, rest angle X / Y / Z; posed per keyframe with the rings. Removing one also
  removes what hangs off it (click Remove twice).
- **Weapon attach** (Weapon_R / Weapon_L card): **Attach to** any bone; the weapon keeps its spot at rest and
  follows that bone. **Edit grip spot** makes the rings / arrows set where it sits on that bone in every clip.
- **Model placement.** Size, height and facing of the whole model.
- **Joint limits** (on by default): elbows and knees can't bend backwards. The natural fold side is read
  from the body at rest (elbows toward the front, knees toward the back) and turns with the upper arm /
  thigh. Elbow / knee bend range in degrees (default 0 = straight to 160); **Flip** per limb puts its limit
  on the other side. Applied while you pose (elbow / knee rings stop at the limit, hand / foot pulls and
  hip drags solve on the natural side, chain pulls such as a weapon pull clamp the elbow); keys already in
  the file are left as they are until edited. The readout shows the selected elbow / knee's bend (and a
  collarbone's swing). Saved in `pb_rig3d.limits` (+ `collar`, tool only).
- **Save into .glb** (Ctrl+S) writes straight back into the file you opened (Edge; other browsers download a
  copy). The keys are baked into the clips, and the key list, anchors and placement are stored in the file's
  scene extras (`pb_rig3d`), so reopening the file lets you keep editing, delete keys or undo a pivot.
- Undo / redo: Ctrl+Z / Ctrl+Y.

Saving re-writes the file with three.js's exporter: the body comes back as one mesh per material and the file
is bigger (about 1.5 MB for ronin_copy); Blender opens it the same (72 bones, 7 clips).

## Real characters

V3 plays the real characters from `characters/`. On every launch `run_v3.bat` runs
`tools/build_kits.py` with the repo's own `python.exe`, which packs each character into
`data/kits.gen.js` (generated, gitignored). A character is packed if its folder has a
`character.json`, a `*.fxkit.json` and at least one damaging effect. Whatever FX Studio /
Rig Forge last saved is what you fight with.

- **From the files:** name, palette, max HP, speed, reach, melee / ranged, the action list
  with each action's length (frames × frame ms), attack chain, cooldowns, trigger conditions
  (`realkits.js realCond`), dodge and movement style (orbit / chase).
- **The FX:** played by FX Studio's own runtime (`../tools/fx/studio/fxkit.js` and its style
  files, loaded unchanged). They keep their 2D anime look, timing, damage, knockback and re-hits, laid in the 3D
  world by `fx3d.js` (see "FX Studio 3D" below). 28 px = one 1.8 m body.
- **Not ported yet:** unique abilities, states, transformations, blinks, the 2D travel movements (FX Studio 3D's
  `move3d` replaces them in 3D) and intercepts.
- **Bodies:** the .glb test body (or the kit's own .glb), toon-shaded in the character's palette colours (see 3D bodies).

If `data/kits.gen.js` is missing, the old hand-made stand-in kits in `kits.js` are used.

Gameplay rules are Playtest 2's, plus:

- **Parry / deflect (Ctrl+Space)**, for every fighter. You press it; the AI rolls a chance (Settings > AI parries).
  - **Perfect** (first 130 ms of the window): no damage, no knockback. A melee attacker is staggered and a counter
    window opens, in which the parrier's hits deal 150 %. A shot is sent back at its shooter, or away the way you
    hold WASD.
  - **Normal** (to 330 ms): damage −60 %, knockback 40 %.
  - Then a 420 ms cooldown.
  - A staggered fighter can parry the counter back.
  - The perfect snap (Space) and Ronin / Tough's own parry / block stay as they were.
- **Jumps** (Daniel 2026-11-23; replaces "speed gravity", where speed set how high a fighter could fly):
  - R = jump (about 3.4 bodies), R again in the air = double jump (about 2.7 more); then gravity brings you down.
  - F in the air = fast fall (stronger gravity, a dust ring on landing).
  - The AI jumps too: to reach a target in the air (double jump near the top), now and then to hop over an attack,
    and after a launch it chases the target up. Snaps never lift a ground fighter. Launches / spikes still throw
    fighters up, and a thrown fighter still bounces / ground-splats.
  - Only characters that can fly stay in the air: `flight: {enabled: true}` in their `*.fxkit.json` (packed by
    `build_kits.py`; the toggle will live in the future FX Studio 3D). None has it yet. Flyers: hold R / F to climb /
    descend, let go to stay at that height; the AI picks their heights freely; Space + R / F snaps straight up / down.
  - Jump clips: rising = `jump`, falling = `fall`, touch-down = `land` (body clips, fallbacks in `rig_spec.json`).

## FX Studio 3D (Daniel 2026-11-24)

`FX Studio 3D.bat` (repo root) opens `v3/tools/fxstudio3d.html` in Edge. It does for V3 what FX Studio did for 2D:
per action, the FX (look, timing, where they start, how they lie in 3D, their movement and damage) and how the body
moves through the action. Daniel's choices: a new page that reads / writes the character's own `<name>.fxkit.json`
(the 2D data stays shared, 3D settings sit beside it); the FX keep their **2D anime look** but fit the 3D world
(2.5D: FX Studio's own drawings laid on cards placed in 3D, no new 3D FX); an effect hits **every enemy it touches**.

- **Characters folder…** once (remembered; Reconnect on a new visit): every folder with a `.fxkit.json` is listed.
  The fighter wears the shared body (`ual_swordsman.glb`) with its own clips (`<name>.glb`, retargeted as in V3), in
  its palette colour; a grey dummy stands as the target (distance / angle / height, or drag it).
- **Preview**: Play / scrub / ◀ ▶ frames / loop / speed; the timeline shows each effect's frames and the body
  movement; after the action it runs 0.7 s more so shots finish. Hits on the dummy flash it and show the damage.
  Stage toggles: **Planes** (an outline of the plane each live effect lies in: yellow side, green flat, blue ground,
  violet billboard), **Anchors** (the body's FX anchor points), **Path** (the body's movement), Camera presets.
- **Actions**: every action in the FX file's `timing`, its length (frames × ms) and cooldown.
- **FX of this action**: on / off, **+ Add from preset** (FX Studio's 184 presets), **+ Blank** (any kind),
  **Copy from** another action, Duplicate, Delete, Go to start.
- **Start spot & 3D placement** (per effect, `effects[i].fx3d`, see below), **Look & timing**, **FX movement**,
  **Damage** (incl. hit depth), **All look settings** (every `params` value, filterable) and **Effect JSON**
  (the whole effect, for anything the panels don't show).
- **Keyed settings** (Daniel 2026-11-24): an effect's keyframes (`keys`, made in the 2D FX Studio) can switch a
  setting mid-action (hooded_blades' blades: frame 8 sets Moves = travel). Such rows show a ◆ badge (`f8 → travel`) with
  × to drop the key; changing a keyed setting in a panel also drops it from every key, so the value you pick plays the
  whole action (the key's other values stay). The FX list marks keyed effects `◆n`.
- **Action movement** (per action, `action_settings[a].move3d`, see below).
- **Character**: **Can fly** (`flight.enabled`, gravity.js); **Sprint Lv2 (%)**, **Lv3 speed** on / off and **Lv3 speed (%)**
  (`sprint: {lv2_pct, lv3, lv3_pct}`, sprint.js; see "Movement: continuous + sprint").
- **3D shape & cel look** (per effect, the `fx3d` render / toon keys below).
- **Save** (Ctrl+S) writes the `.fxkit.json` back (Edge / Chrome; other browsers download it). Undo / Redo (Ctrl+Z /
  Ctrl+Y), Space = play, ← → = frames. `run_v3.bat` repacks the characters, so the game plays what was saved.

**How the 2D FX live in 3D (`v3/js/fx3d.js`, shared by the game and the studio).** Each action gets its own lane: an
`FXK.Player` in a 2D frame locked when the action starts (origin = body centre, 2D x = level toward the target,
2D y = down). Shots keep flying where they were fired; FX on the body follow it. Anchors (`haR`, `wtip`, `head` ...)
are read from the 3D bones (RIG_SPEC section 3 map; Rig Forge 3D's own `pb_rig3d` anchors; `bone:<Name>`), 2D-only
anchors (coat tails, extra lines) fall back to the 2D drawing's point. Each effect is painted onto its own card
(per spawn point) laid by its `fx3d` block:

| `fx3d` key | Meaning (default) |
|---|---|
| `lay` | `auto` (glow / particles / pulse / ghost → billboard, the rest → side), `side` = upright through the aim line, `flat` = level at its height, `ground` = on the floor, `billboard` = faces the camera |
| `tilt_deg` / `yaw_deg` / `pitch_deg` | roll about the aim line (90 lays a side effect level), turn about up, tip up / down (0) |
| `pivot` | turn about `spawn` (its start point) or `figure` (the body centre) |
| `anchor` | where it starts on the 3D body, overriding the effect's 2D anchor ("" = its own) |
| `offset` | [forward, up, side] metres added to where it lies ([0, 0, 0]) |
| `size_pct` | drawn size (100) |
| `ink_px` | dark cel outline round the drawing, card pixels (0 = none) |
| `depth_m` | an enemy body within this many metres of the effect's plane can be hit (0.8; billboard x2) |

Hits: every enemy within `depth_m` (+ its body) of the plane is tested in that plane with FX Studio's own rules
(`FXK.resolveHits`, exported for this), each enemy with its own hit count, so a slash can cut through a crowd and a
non-piercing shot stops at the first. In training every dummy can be hit.

**Action movement (`action_settings[a].move3d`, fxlive.js in the game).** `enabled`; start: `start_mode` stay / blink /
dash (`start_ms`) to a spot `start_dist_m` from the target at `start_angle_deg` (0 = the fighter's side of the target,
180 = behind it, mirrored by `side`) and `start_height_m`; then `path` none / line / leap / arc / zigzag / flank /
hit_retreat from `from_frame` to `to_frame` (-1 = the end) to the end spot (`end_dist_m`, `end_angle_deg`,
`end_height_m`), shaped by `arc_m` / `zigs`, eased by `ease`; `face` target / travel. While it runs, the clip's root
motion, the lunge, drift and gravity stand aside; afterwards a ground fighter falls back down. Solo + Battle.

**3D cel-shaded FX (Daniel 2026-11-24: "3D in shape, 2D in cell shading", starting with the foundational kinds).**
Per effect `fx3d.render`: `auto` (default) = a real 3D shape for the kinds below, a card for the rest; `3d`; `card` =
the 2D drawing as before. Blades and every technique / gun / kick / defender style stay cards for now.

| Kind | 3D shape |
|---|---|
| ribbon (laser trail) | a tube along its trail, thick at the head, tapering to the tail (`laser_width_pct`) |
| sprite orb / bolt | a sphere head (a bolt stretches into a capsule along its flight) + a **laser streak**: a tapered tube stretched away opposite the way it moves, `laser_streak` ticks of its travel long (faster = longer), capped at `laser_max_m` |
| beam | a tube from the base (hand) to the head with FX Studio's base / head widths (`beam_width_pct`, `beam_wobble_pct` throb), a bulb at the head (`beam_bulb_pct`) and a flare at the base (`beam_flare_pct`) |
| particles | 3D chunks (`chunk_shape` shard / ball / cube, `chunk_size_pct`) that spin and also fly out of the plane (`chunk_spread_pct`) |
| glow (orb) | a sphere (its visible radius, pulse) |
| pulse (impact) | per ring: a see-through expanding shell (`impact_shell`, `impact_shell_pct`), a flat shock ring spreading level (`impact_ring`) and radial spikes on the first ring (`impact_spikes`, `impact_spike_pct`) |

Look (every effect, tunable in FX Studio 3D's "3D shape & cel look"): `toon_bands` flat colour bands from the edge
(`toon_shade_pct` brightness) to the full colour, a white-hot flat core where the surface faces the camera
(`toon_core_pct`, `toon_core` colour), a dark ink outline (`toon_ink_m`, an inverted hull), `toon_alpha_pct`,
`toon_sides` facets. Colours = FX Studio's colour mode / palette. Hits: a 3D shape hits with its 3D shape. The enemy's
distance off the effect's plane is folded into its 2D offset from the nearest point of the shape (exact for spheres
and tubes), so FX Studio's own rules (damage, re-hit, pierce, pulse ring sweep, per-particle hits) still decide.
`depth_m` applies to cards only.

## Movement: continuous + sprint (Daniel 2026-11-24)

`js/sprint.js`. Fighters no longer step-and-plant (a 0.1 s step, then a 0.14 s stand): every fighter moves
continuously, its velocity eased toward the wanted one (`SPRINT.accel` / `decel`), so starts, stops and turns are smooth.
Three speed levels:

- **Lv1** = the character's base speed.
- **Lv2** = sprint, `SPRINT.lv2Pct` (185 %) of base; per character `sprint.lv2_pct`.
- **Lv3** = heightened speed beyond sprint, only for characters with FX Studio 3D's **Lv3 speed** on (`sprint.lv3`,
  `sprint.lv3_pct`, default 300 %). Afterimages + light streaks while it runs; Lv2 kicks up dust.

Player: hold **Shift** = Lv2; **double-tap and hold Shift** (second press within 280 ms) = Lv3 (Lv2 for a character
without it); let go = Lv1. The AI (enemies, your fighter while the AI drives it, Fight-back dummies) sprints when it
closes in or chases (engage / pressure / punish / feint / reset / movement styles): Lv2 when its move target is more than
380 px away, Lv3 (if it has it) past 820 px or when punishing. During an action the move speed stays Lv1 x 25 %. The body
plays its `sprint` clip at Lv2 / Lv3 (falls back to `run`). Perfect parry: a parried melee attacker is staggered
**0.5 s** (`PARRY_DEFAULTS.staggerMs` 500, Daniel 2026-11-24; shots keep their reflect / deflect).

## The little planet + World Studio 3D (Daniel 2026-11-24)

Fights run on a little planet you can run all the way round (like v1's tiny planet, now a real globe). Settings are made in
**World Studio 3D** (`World Studio 3D.bat` -> `tools/worldstudio3d.html`) and saved to `characters/world3d.json`
(format `pb_world3d`); `run_v3.bat` (`tools/build_kits.py`) packs it into `data/world.gen.js` (`window.PB3_WORLD`,
gitignored). No file = the defaults. The studio's preview runs the game's own `js/world3d.js`, so what you see there is what
the game builds.

- **How the globe works.** The sim stays a flat plane (2D px + height), but with the planet on it has no walls
  (`W` / `H` are huge; `MAPW` x `MAPH` round the centre = the old arena, used for start spots and the training map). A vertex
  shader bend (`World3D.installBend`, patched into three.js's `project_vertex`) wraps every normal object onto a sphere about
  the **anchor** (the eased fight centre): a point d m away sits d m round the curve, heights along the local up. Fighters,
  FX, shots, dust and the camera need no changes. The planet and everything on it live in one group that is not bent
  (define `PB_NOBEND`) and **rolls** under the fight as the anchor moves, so you come back to the same rocks after a lap.
  Planet things are stored as unit vectors (`flatOf` / `surfaceU` convert to / from the sim plane).
- **Planet off** (Planet section) = the flat walled arena exactly as before (no bend, old bounds, old start spots).
- **Sections** (each has its own on / off): Planet (radius, seed: 0 = new random world each fight, ground looks to pick
  from, patchiness, open ground at the start, globe turn speed), Gravity (gravity, jump height, jumps in a row, fast fall,
  bounce, ground splat speed, launch power, launch carry = how far throws fly round the globe, ground slide; 100 % = the old
  numbers; also used on the flat arena), Sky (stars, nebula, moons, ring chance / width), Atmosphere (haze + distance,
  clouds, cloud height / speed, dust motes), Ground cover (grass, stones, small crystals per 1,000 m², size), Landmarks
  (count, kinds: arch / ruined wall / giant crystal / monolith / rock spire, size, solid).
- **Destructibles** (each type on / off, each with its own regrow time; 0 = stays broken until the next fight):
  - *Pillars & boulders*: block bodies and shots; break on a single hit / shot / blast of at least `break_damage`, or a
    thrown fighter at least `break_speed` fast (smashes through, keeps 70 % speed); weaker hits chip `chip_pct` %; a thrown
    fighter that doesn't break it gets a PILLAR SPLAT (toggle). Boulder stacks by `multi_chance`.
  - *Ground damage*: craters (ground splats, heavy hits, hard landings, K.O.s, blasts), trenches (fast knockback slides),
    scorch marks (blocked shots, blasts); fade after `fade_s`, at most `max_marks`.
  - *Breakable scenery*: trees (pine / round / dead), crystal clusters, old columns; same break rules with their own numbers;
    `solid` off = fighters pass through (they still break when hit).
  - What hits them: landed hits reach whatever stands round the target (`planetHit`), shots (`planetShot`), thrown fighters
    (`planetTick`), ground splats / K.O.s (`planetBlast`). FX Studio FX hit them only through the hits they land on fighters.
- **Look**: each world picks one ticked ground look (meadow, dusk = the old V3 night, rocky moon, crystal, lava, ice,
  desert) and randomises moons, ring, nebula, tree kinds, landmark kinds and every placement from the seed.
- **Studio**: Orbit / Ground view, Spin, New random world (preview seed), click the planet = test blast (radius 6 m, damage
  80: breaks things, crater + scorch); two 1.8 m stand-ins on the start spot, one jumping with the Gravity numbers (the
  readout gives jump height in bodies and air time). Characters folder (remembered) -> Save writes `world3d.json` there;
  without folder access Save downloads it. The current edit is also kept in the browser (draft) until saved.
- Title screen: the planet seen from orbit.

## Knockback tracking shot (Daniel 2026-11-24)

Over the shoulder and Dynamic camera (`js/camera.js`, `camKnock` / `trackStep`), for either on-field fighter (the
enemy in front or your own): when ONE hit's knockback will carry the fighter at least **Starts at knockback** px
(predicted carry = the added speed / the slide friction: air `GRAV.airFric` when thrown up or airborne, else
`GRAV.groundFric`), the camera makes one continuous move (eased swoop + zoom, no cut) to just behind the fighter,
facing the way it travels, then rides rigidly with it (same speed, so it stays in frame) until it lands and stops
sliding (or **Longest track**), then glides back to the normal shot (which keeps updating underneath). View only:
the sim never reads it. Hit again while tracked = keeps riding. Settings screen group "Knockback tracking shot":
on / off, starts at knockback (px), distance behind, height above, zoom in (% narrower fov), swoop-in time,
glide-back time, longest track, **cooldown** between two shots.

Update (Daniel 2026-11-24): the camera sits **Angle** (45 deg) off straight behind the flight line, on the **Side**
setting's quarter (default Right of the flight line; Left available) (3/4 view; straight behind = the full face of a fighter thrown backwards). It starts the glide back **Ease out
early** (250 ms) before the knockback is predicted to end (`trackLeft`: fall time under stunned gravity + ground slide
down to 220 px/s), leaving from the live chase pose. While it rides, the globe keeps the tracked fighter on top.

Globe wrap (`planet.js planetWrap`): a fighter or shot more than half way round the planet from the anchor is moved once
round (same globe spot, other side), so a far throw keeps flying the same way round instead of appearing to reverse past
the far side; the anchor is the two fighters' midpoint measured the short way round. Training dummies now stay where a
knockback leaves them (they only float back to their placed height); Restart training puts them back.

Golden-ratio framing (Daniel 2026-11-24, setting **Golden-ratio framing**, on by default): while the shot rides, the camera
aims so the flying fighter sits on the top-right crossing of the golden-ratio grid (61.8 % across, 38.2 % down;
`goldenLook`, worked out in drawn space on the planet via `planet.js unbendP`). Off = centred as before. The swoop in /
glide back blend into and out of it.

