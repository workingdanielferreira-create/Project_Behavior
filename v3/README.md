# Project Behavior V3 — 3D

The 3D game, built on Playtest 2 (*Behavior 3D Playtest v2*), now in its own window.
Self-contained like `v2/`: nothing outside `v3/` is touched.

## Update

`update_v3.bat` (here) or `Update V3.bat` (game folder) runs `tools/update_v3.py`: downloads the newest
commit on `main` and writes only the V3 parts that changed — `v3/` (game + Rig Forge 3D), `Rig Forge 3D.bat`,
`Update V3.bat`, `tools/fx/studio/` (FX runtime V3 uses) and `characters/`. Local edits to `characters/`
files (e.g. a .glb saved from Rig Forge 3D) are kept, using the same `.sync_state.json` record as
`update_latest.py`. The 2D game files are left to `update_latest.bat`. Afterwards it asks:
1 = V3 game, 2 = Rig Forge 3D, Enter = nothing. Installed commit: `.last_update_v3.json`.

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

Title → Fight / Teams / Settings / Controls / Fullscreen. In a fight: Esc or P
pauses (Resume, Restart, Settings, Controls, Quit to title). After a fight:
Results (Rematch, Change teams, Title).

Menus work with the mouse or the keyboard:

- Up / Down: move between items
- Left / Right: change a value
- Enter: press
- Esc: back

Settings and teams are saved between sessions.

## Code layout (`js/`, loaded in this order by `index.html`)

| File | What it holds |
|---|---|
| `core.js` | constants (arena size, tick, body size), maths helpers |
| `settings.js` | saved settings (control level, speed, camera, quality, teams) |
| `kits.js` | stand-in kits (fallback when `data/kits.gen.js` is missing) |
| `realkits.js` | real kits from `data/kits.gen.js` → V3 kits (actions, triggers, dodge, movement) |
| `renderer.js` | WebGL renderer, scene, toon / ink / additive materials, 2D→3D mapping (`V`, `VA`) |
| `arena.js` | the arena: floor, sky dome, floating rocks, pillars, rim, stars |
| `fx.js` | **FX design**: primitives (slash, ring, dome, sparks, dust, star, crack, streak, moons, blades) |
| `state.js` | world state, timers (`later`, `ms2t`) |
| `glbody.js` | **.glb body**: parses `data/body.gen.js` once at boot, gives each fighter a skinned copy (toon + ink, kit colour), picks its clip from the fight state |
| `models.js` | **fighter rigs and models** (`buildBody`) |
| `movestyle.js` | **movement styles** (FX Studio `movement_style` phases) + intent speed table |
| `tempo.js` | fight rhythm intents (port of `laser/tempo.py`) |
| `director.js` | director heat: calm / build / burst |
| `motion.js` | drift & snap motion |
| `gravity.js` | speed gravity: speed sets how high a fighter may fly, gravity pulls it down above that |
| `combat.js` | actions, triggers, hits, damage, stun, K.O., reactions, tagging, projectiles |
| `fx2d.js` | real kits' 2D FX: FX Studio's Player per fighter, drawn on camera-facing cards in the 3D scene |
| `parry.js` | parry / deflect: Ctrl+Space timing windows, perfect-parry stagger + counter, shot reflect / deflect, AI rolls |
| `fxlib.js` | **FX animation**: every action effect (`runFx`) |
| `fighter.js` | fighter creation, per-tick update, altitude, wall / ground splats |
| `input.js` | keyboard commands |
| `camera.js` | camera modes (over the shoulder / dynamic / wide), cuts, shake, punch |
| `anim.js` | **animations**: pose, swing, lean, legs, recoil, flashes, shadows |
| `hud.js` | HUD, callouts, command bar, damage numbers, feel panel |
| `menus.js` | title, teams, settings, controls, pause, results |
| `main.js` | game loop, fight flow, boot |

The files are plain scripts sharing one scope rather than ES modules, so the
game runs straight from disk (`file://`) without a local server. A file may
use anything declared in the files loaded before it. Code that runs at load
time has to respect that order; functions called later can reach anything.

## 3D bodies (spec)

In a fight every fighter wears the test body `characters/ual_swordsman/ual_swordsman.glb` (RIG_SPEC section 8),
tinted in its kit colour, sword on melee kits only. `tools/build_kits.py` packs it into `data/body.gen.js` (gitignored,
rebuilt by `run_v3.bat`). A kit whose folder holds its own `<folder>.glb` (today: ronin_copy) keeps its stand-in
body for now. No `body.gen.js` = stand-ins for everyone. Clips: action -> `attack_normal(_N)` / `attack_special(_N)` /
`ultimate` / `transform` / `switch_in` / `defend`, stretched to the action's length; stun -> `hit_light` / `hit_heavy` /
`hit_air` / `knockdown`; K.O. -> `ko`; parry / block -> `parry` / `defend`; snap -> `sprint` (`dodge_back` going
away); moving -> `run`, still -> `idle`, in the air -> `air_move` / `air`. Missing clips fall back as in `rig_spec.json`.

`RIG_SPEC.md` (+ `rig_spec.json`) is the rig + animation spec for 3D fighters: Mixamo bone
names, fingers, face set, weapon bones, FX anchor → bone map, clip list with fallbacks, glb export.

First 3D test fighter: `characters/ronin_copy/ronin_copy.glb`, built by `tools/blender/build_ronin3d.py`
(runs on Blender's `bpy` Python package, no Blender UI). `tools/blender/make_viewer.py` makes a
self-contained viewer page for any .glb. V3 doesn't load the .glb yet.

## Rig Forge 3D

`Rig Forge 3D.bat` (repo root) opens `tools/rigforge3d.html` in Edge. **Open .glb…** a character's
`characters/<name>/<name>.glb`, then:

- **Pose per keyframe.** Click a pivot dot (or pick it in the Pivot list), go to a frame and turn the X / Y / Z
  rings (red / green / blue; grey = free turn, yellow outer ring = turn about the view). The rings follow the
  mouse round the ring (the pointer is put on the ring's plane; a ring seen edge-on turns by dragging along
  it); **Shift** = 5° steps; the HUD shows the turn. A ring under the mouse wins over a nearby dot unless you
  press right on another dot. Hips also have move arrows (**Move**, `T`). Each change sets a key on that frame;
  frames in between blend, and **Blend out** sets how far a key fades before the first / after the last key
  (all the way right = the whole clip). **Local / World** (`L`) picks the axes of the rings AND the arrows
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
  files, loaded unchanged). They keep their 2D look, timing, damage, knockback and re-hits.
  `fx2d.js` runs one `FXK.Player` per fighter in a 2D space centred on its body, with
  2D x = camera right, 2D y = camera down, and 28 px = one body.
  - The enemy sits in that space where it appears from the camera, so shots fly at it and
    hits land where they touch.
  - The drawing is painted onto two camera-facing cards in the 3D scene: the 2D "behind"
    layer just behind the body, "front" just in front. Perspective, fog and anything in
    front of them still apply.
- **Not ported yet:** unique abilities, states, transformations, blinks, travel movements
  and intercepts.
- **Bodies:** still 3D toon stand-ins, in the character's palette colours.

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
- **Speed gravity** (Settings > Speed gravity). Speed sets a ceiling on how high a fighter may fly:
  - up to 650 px/s it stays on the ground;
  - the ceiling rises with speed, to the full 1,500 px of air at 3,000 px/s (snap speed);
  - above its ceiling a fighter falls with accelerating gravity.
  - AI heights and R / F still pick a height under the ceiling, a snap can climb as high as its own speed allows,
    and launches / spikes still throw fighters up.
