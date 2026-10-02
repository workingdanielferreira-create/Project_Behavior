# Character creation pipeline

Characters are keyframe **images**; FX are data.

| Phase | Tool | Output (all in `characters/<name>/`) |
|---|---|---|
| 1. Rig & animate | `rigforge.html` (Rig Forge) → **Export character package…** | `<action>_NN.png` frames + `character.json` (name, archetype, stats, palette, timing, starting anchors) |
| 2. FX | `studio/fx_studio.html` (FX Studio) → **Open character folder…** / **Save FX to folder** | `<name>.fxkit.json` (FX, anchors, damage) |

**Component widths.** In Rig Forge's rig settings, under *component widths
(%)*, every body part has a width at each end (e.g. thigh: hip end / knee
end). Set them differently to taper the part, or double-click a slider to go
back to 100. Near and far limbs share one width unless *separate near / far
limbs* is ticked. Each weapon has a *thickness* (across the blade). Widths
belong to the character, so they apply to every action and frame, and the
exported frames use them.

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
- **Flip & direction.** Tick **Flip** on an effect to make it play on the
  side the target is on: drag the target behind the fighter and the effect
  mirrors left ↔ right to face it (never up ↔ down), arc sweep and orbit
  spin included. **Created side** is the side the target was on when you
  added the effect; you can change it. Tick **Follow direction** to make the
  whole effect turn toward the target at any angle: target above, it turns
  up. With both ticked it mirrors to the target's side and then tilts up or
  down toward it.
- **Blink (per action).** Under each action's settings: a teleport inside
  that action. The character vanishes at **Vanish at frame** and reappears
  after **Reappear after frame** (-1 = when the action ends). **Reappear
  near** + **Side** + **Distance** set where it lands. While gone it can't
  be hit, doesn't move and fires no new FX; its animation keeps running.
  The stage shows it: the figure disappears over those frames, a faint
  outline marks where it vanished and a ring marks where it lands.
- **Trigger conditions (per action).** Every attack and triggered action
  has them under its action settings. On a triggered action (defend,
  ultimate, attack_special, …) they decide when it plays; on an attack they
  are an extra check on top of the target being in range (none = attack on
  range alone). Pick from the grouped list (own state, target, hits &
  projectiles, timing & order), combine with ANY / ALL, and tick **Not** to
  invert one. **Live preview** tests every condition: drag the target for
  distance / height, and set a value for each other condition the action
  uses (HP, speeds, hits, projectiles, nearby FX tags, last actions, timers,
  the chance roll; only the ones in use are shown). Each condition shows
  ✓ / ✗ and the section says whether the action would fire (preview only,
  not saved).
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

Everything happens in the game folder on your PC; no GitHub, no updater.

1. **Rig Forge.** Double-click `Rig Forge.bat` in the game folder. Build the
   character, then **Export character package** and pick the game's
   `characters` folder. Rig Forge writes `characters\<name>\character.json`
   and the frames.
2. **FX Studio.** Double-click `FX Studio.bat`, **Open character folder**, and
   pick `characters\<name>`. Build the FX, then **Save FX to folder**. That
   writes `characters\<name>\<name>.fxkit.json`.
3. **Game.** Press **F5** to reload characters. The top-left corner shows
   "Reloaded <name>". Cycle to the character with `1` / `2`, and press Alt+Up
   for attacks.

The `.bat` launchers open Edge, which can save straight into folders. In
other browsers the tools download the files instead; move them into
`characters\<name>\`.

**Size.** Every image character stands 28 px tall in game, the roster's
height (`config.IMAGE_STAND_HEIGHT_PX`), measured on its first idle frame.
FX Studio shows it at that size, so FX look the same in both. An FX file
authored at an older scale is rescaled on load so its FX keep their place
around the figure.

**Your edits are safe.** `update_game.bat` never overwrites a character file
you changed on this PC; it lists the files it kept. Dropping a zip or FX file
into the repo still works (they are filed under `characters/`), but a newer
file already in the character folder always wins.

If a character has no FX file, its HP label says "(no FX file)".

## Reworking the existing characters' FX
`fx_packages/<name>/` holds an FX Studio package of every existing fighter
(runner, swordsman, jumper, mage, new_fighter, ronin, reverseswordman), made
from the game's own frames by `tools/fx/export_packages.py`. Open one with
**Open character folder...**, author its FX, save, then drop the folder into
`drop/` to switch that fighter over. Rig Forge's **Import package...** opens the
same folders to edit poses and add actions, and exports back into them. See
`fx_packages/README.md`.
