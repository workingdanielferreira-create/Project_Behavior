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

2026-11-22 cloud session: still no Blender tools, no Blender install and no attached computer.
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

## Next steps (agreed direction, not started)

1. **Done (2026-11-22):** `v3/RIG_SPEC.md` + `v3/rig_spec.json`. Mixamo-compatible skeleton,
   fingers, face set (Jaw / eyes + shape keys) and weapon bones required; no hair / cloth chains for
   now; clips = FX Studio actions + locomotion set + hit reactions, each with a fallback.
2. With the Blender plugin: build one test fighter (Rigify or Mixamo rig) and export a .glb.
3. Build the Rig Forge 3D importer. Swap V3's toon stand-in body for the .glb, driven by the sim's
   action / timing.
4. Later: 3D FX styles in FX Studio.

Follow `CLAUDE.md` session rules: ask before implementing (pop-up questions); push, open the PR and
merge it.
