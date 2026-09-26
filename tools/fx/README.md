# Character creation pipeline

Characters are keyframe **images**; FX are data.

| Phase | Tool | Output (all in `characters/<name>/`) |
|---|---|---|
| 1. Rig & animate | `rigforge.html` (Rig Forge) → **Export character package…** | `<action>_NN.png` frames + `character.json` (name, archetype, stats, palette, timing, starting anchors) |
| 2. FX | `studio/fx_studio.html` (FX Studio) → **Open character folder…** / **Save FX to folder** | `<name>.fxkit.json` (FX, anchors, damage) |

In Rig Forge, open the IO tab and use **Export character package…**. Pick the
game's `characters` folder; a `<name>` sub-folder is created. Chrome and Edge
write the files straight into the folder. Other browsers download them for you
to move there.

## FX Studio

Open `studio/fx_studio.html` straight from disk. **Open character folder…**
(or drop the folder on the page) loads the PNGs and `character.json`, plus the
`.fxkit.json` if one is already there. Every action plays at its Rig Forge
timing.

- **Anchors.** Rig Forge pre-fills them: hands, blade tip, head, feet and so on.
  Select one and press **Place (P)**, then click the figure to move it on the
  current frame. With **next frame after placing** ticked, you can step
  through the frames placing it each time. Frames you skip hold the previous
  position. **+ Anchor** adds your own, e.g. a gun muzzle.
- **FX** are built from the engine's own drawing primitives:
  - **ribbon**: laser trail
  - **arc**: crescent
  - **beam**
  - **sprite**: orbs and bolts
  - **particles**
  - **glow**
  - **ghost**: afterimages
  - **weapon**: an invisible melee hitbox between two anchors, e.g. near
    hand → weapon tip

  Each FX anchors to a joint, moves, takes a colour, plays over a range of
  frames, and has a **Deals damage** checkbox (HP per hit, pierce, re-hit,
  knockback). It hits wherever its drawn shape touches the target's hurt
  circle.
- **Presets.** Built-in presets rebuild the game's existing effects with their
  `config.py` numbers. **Save as preset** keeps your own, and
  **Export**/**Import** moves them between machines.
- **Saving.** **Save FX to folder** writes `<name>.fxkit.json` next to the
  images. Work also autosaves in the browser per character.
- **Controls.** `space` play/pause, `← →` step a frame, left-drag moves the
  target, right-drag pans, the mouse wheel zooms.

Format and engine contract: [`FX_KIT_SPEC.md`](FX_KIT_SPEC.md).
Runtime reference: `studio/fxkit.js`.

> **Status:** the tools are done. The game doesn't load character folders or
> play `.fxkit.json` yet; that's Phase 2 (`laser/fxkit.py`, see
> FX_KIT_SPEC.md §7).

## Getting a character into the game

1. **Rig Forge → Export character package.** You get `<name>.zip` (or a
   `<name>/` folder): `character.json` + the `<action>_NN.png` keyframes.
2. **FX Studio → Save FX to folder.** You get `<name>.fxkit.json`.
3. **Upload both to the repo's main branch** (GitHub → Add file → Upload
   files), at the top level or into a `drop/` folder. The zip can stay zipped.
4. **Run `update_game.bat`.** It downloads them and `laser/drops.py` files
   them as `characters/<name>/character.json`, `characters/<name>/*.png` and
   `characters/<name>/<name>.fxkit.json` (the game also does this at start-up).
   A newer export of the same character replaces the old one (old keyframes
   it no longer has are removed); if two exports of one character are in the
   repo, the newest is used and the updater tells you to delete the other.
5. **In the game**, press `1` / `2` to cycle to the character. It plays in
   Solo and Battle with its keyframes, frame timing and archetype. A package
   replaces an older rig-drawn `characters/<name>.json` of the same name.
   Its FX from the `.fxkit.json` play in game through `laser/fxkit.py`,
   locked to the frames on screen, and effects with Deals damage hurt the
   opponent in Battle. Triggered actions (special, ultimate…) and full-length
   action playback are still to come.



`fx_creator.html` + `rig.js` / `fx_engine.js` / `character_creator.js` /
`main.js` are the retired Character Wizard (see `WIZARD_AUDIT.md`). Its rig
differs from Rig Forge's, so it can't open Rig Forge characters. It stays only
for reference and for existing `pb_fx v1` files: `python tools/fx_preview.py`
still hot-reloads the newest `*.fx.json` in this folder.
