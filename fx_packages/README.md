# FX Studio packages of the existing characters

One folder per fighter, exported from the game by `tools/fx/export_packages.py`:
`character.json` + `<action>_NN.png` frames, the same format Rig Forge exports.
The frames look exactly like the fighter in the game (same art, tints, size
ratios and frame timing), drawn 4x larger so anchors are easy to place.

**The game does not read this folder**, so nothing here changes play.

## Rework a character's FX
1. Open **FX Studio** (`FX Studio.bat`) -> **Open character folder...** -> pick
   `fx_packages/<name>`.
2. Place anchors where you need them (mage comes with every
   joint already placed; the image fighters have the joint names ready, with
   no positions yet), then build the FX, triggers and movement.
3. **Save FX to folder** -> writes `<name>.fxkit.json` into the same folder.

## Edit poses or add actions (Rig Forge)
1. Open **Rig Forge** (`Rig Forge.bat`) -> **Import package...** -> pick
   `fx_packages/<name>` (or pick `fx_packages` and choose the character).
2. Choose the rig to pose with: the default rig or one of your Rig Forge
   characters (its bones and weapon).
   - Skeleton characters (mage) have every joint in their
     package, so their frames come in as poses you can edit; the original
     frame shows underneath as a reference.
   - Image-only fighters (runner, swordsman, jumper, ronin, reverseswordman)
     come in as their art frames, per action. **+ Action** / **+ Keyframe**
     adds posed frames drawn with the chosen rig, at the art's size and colour.
3. **Export character package...** writes back into the same folder (frames,
   timing, character.json). The folder's `<name>.fxkit.json` is kept and stays
   aligned; actions whose frame count changed take the new anchor points.
   The package also records the rig and keyframes, so importing it again
   brings everything back exactly.

## Put it in the game
Copy the whole `fx_packages/<name>` folder (frames, `character.json`,
`<name>.fxkit.json`) into `drop/` in the repo and run `update_game.bat`, as with
rapid. From then on that fighter plays as an image character: the archetype
decides when it attacks, the Studio triggers decide its other actions, damage
comes only from FX with **Deals damage**, and it stands 28 px tall like the
rest of the roster.

Re-export after changing a character's art: `python tools\fx\export_packages.py`
(frames are rewritten; a saved `<name>.fxkit.json` is kept).
