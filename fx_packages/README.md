# FX Studio packages of the existing characters

One folder per fighter, exported from the game by `tools/fx/export_packages.py`:
`character.json` + `<action>_NN.png` frames, the same format Rig Forge exports.
The frames look exactly like the fighter in the game (same art, tints, size
ratios and frame timing), drawn 4x larger so anchors are easy to place.

**The game does not read this folder**, so nothing here changes play.

## Rework a character's FX
1. Open **FX Studio** (`FX Studio.bat`) -> **Open character folder...** -> pick
   `fx_packages/<name>`.
2. Place anchors where you need them (mage and new_fighter come with every
   joint already placed; the image fighters have the joint names ready, with
   no positions yet), then build the FX, triggers and movement.
3. **Save FX to folder** -> writes `<name>.fxkit.json` into the same folder.

## Put it in the game
Copy the whole `fx_packages/<name>` folder (frames, `character.json`,
`<name>.fxkit.json`) into `drop/` in the repo and run `update_game.bat`, as with
rapid. From then on that fighter plays as an image character: the archetype
decides when it attacks, the Studio triggers decide its other actions, damage
comes only from FX with **Deals damage**, and it stands 28 px tall like the
rest of the roster.

Re-export after changing a character's art: `python tools\fx\export_packages.py`
(frames are rewritten; a saved `<name>.fxkit.json` is kept).
