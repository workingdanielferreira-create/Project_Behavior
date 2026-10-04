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
- **Keyframes (per effect).** Animate an effect's numbers and colours over
  the action. Press **◆ + Key at frame N** to add the first key. From then
  on the effect's panel edits the frame under the playhead: move the
  playhead (timeline or ← →) and change any number or colour, and it's
  stored in the key on that frame (a key is added there if there isn't one
  yet). Between keys the panel shows the in-between values. Each key's
  **ease** (Linear, Ease in / out / in-out, Strong in / out / in-out, Hold,
  Bounce, Elastic) shapes the change from the previous key, spread across
  every frame in between; values hold after the last key. The effect's own
  settings are the start (playhead on the start frame). Keys show as ◆ on the
  effect's timeline row; click one to jump there. Shots already flying follow
  the animation (e.g. speed 20 → 100 mid-flight).
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
  **Blink cooldown ms** (0 = none): after it reappears, the action plays
  without blinking (and without its Blink FX) until the cooldown is over.
- **Attack distance (normal attacks).** Under each `attack_normal*` action:
  **Attack distance px** — the attack starts once the target is this close
  (scales with Character scale). 0 = the character's basic attack radius.
- **Radial pulse FX.** Primitive `pulse`: rings that expand from **Radius
  start** to **Radius end** over **Expand ms**, **Rings** of them **Gap** ms
  apart (0 = repeat for the whole effect). With Deals damage each ring hits
  a target once as its edge sweeps over it, knocking it outward.
- **Tactical retreat conditions.** The retreat takes every action trigger
  condition (with Not). "This action" counters and timers count from the
  last retreat.
- **Tactical retreat FX.** Under *Tactical retreat (whole character)*,
  **Retreat FX** picks an optional effect, or a whole ▣ group, from any action
  to play for as long as the dash lasts. FX that stay on the fighter are held
  for the dash; shots keep firing on their action's timing. It still plays on
  its own action too.
- **Character scale (whole character).** Under every action's settings:
  **Scale %** (10-200, default 100) sizes the whole character in the game:
  sprite, anchors, every FX, its body hit circles, attack range and retreat /
  blink distances, all in proportion. Movement speed stays the same. The stage
  shows it; effects keep their numbers at 100 %.
- **FX scale with the fighter.** Build FX at **pscale** 1 (the fighter's
  base size). In the game, and in the Studio when you raise **pscale**, every
  FX distance grows with the fighter's on-screen size, like a zoom: offsets,
  entry points, orbits, paths, beam length, arc placement, particle spread
  and gravity, intercept range, and shot speed (so range scales too). Shots
  keep the size they were fired at.
- **Triggered reactions (Actions panel).** Under the actions list, a
  *Triggered reactions* subsection always lists **⚡ Tactical retreat** and
  **⚡ Blink** ("(off)" until switched on). Select one to build FX that play
  when that reaction triggers, and to preview it on the stage:
  - **Tactical retreat**: FX are built on the run frames and play for the
    whole dash, replaying each loop of the frames (effects that last to the
    end of the frames keep running across loops). The stage dashes the
    figure from its start spot with the retreat's settings (angle, curve,
    speed, avoid / re-engage, duration; -1 previews 3 s), and the loop replays
    it. Its settings panel is the same Tactical retreat block; the old
    **Retreat FX (borrowed)** dropdown still adds an effect / group from
    another action on top.
  - **Blink**: a dropdown at the top picks which action's Blink you work on.
    FX are built on that action's frames and play alongside its own FX
    whenever it plays with Blink on. The Blink settings are the same ones as
    under the action's settings (both edit the same data).
  An effect's **Action** dropdown also lists the reactions, so an effect can
  be moved onto or off one.
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
- **Presets.** Grouped in the list: Trails, Slashes, Shots, Beams, Orbs &
  auras, Bursts & afterimages, plus special abilities: **Fire** (Fireball,
  Flame slash, Eruption), **Lightning** (Chain lightning, Thunder strike,
  Spark volley), **Shadow** (Void orb, Shadow dash, Void collapse),
  **Holy** (Radiant beam, Halo burst), **Ice & wind** (Ice shards, Frost
  nova, Wind blades, Cyclone), **Earth & poison** (Quake, Toxic cloud),
  **Arcane & cosmic** (Arcane missiles, Rune circle, Meteor, Starfall),
  **Energy** (Charged laser) and **Ethereal** (**Ethereal blade**: one still
  sword of light, visual only, to build your own blade FX from; **Ethereal
  blades**: a sword formation for a 30-frame action — six swords rise over the
  fighter, three rows of upright swords close in round the target and circle
  it, swords rain down six lanes and lodge in it, then a giant blade drops and
  lodges). The first groups rebuild the game's
  existing effects with their `config.py` numbers; the special abilities use
  keyframes. Every preset effect carries its FX tag. **Save as preset** keeps
  your own (listed under ★ Your presets); saving a name you already have
  replaces it. **Export**/**Import** moves them between machines, together
  with your path and entry-set presets.
- **Groups.** Ctrl+click two or more effects in the effect list and press
  **Group**. They now ride one pivot (the first one's joint) as a single
  piece: each keeps its place relative to the others, and they share Flip and
  Follow direction so they mirror and turn together. Click the ▣ group row to
  edit it: **Pivot** re-attaches the whole group to another joint (or figure /
  target) without changing its layout, **Move X / Y** shifts every member
  equally, and on the stage you drag the ▣ handle (or Shift+drag anywhere).
  A member's own Offset moves it within the group. **Save group as preset…**
  stores the whole group as one preset; adding it brings the group back on
  the current action. **Ungroup** (⊟) leaves every effect where it is.
  Weapon hitboxes and ⊕ entry-set effects can't be grouped.
- **Blade shape.** Orbs and bolts (sprite) also come as **blade**: a sword of
  light (faceted blade with a white ridge, crystal guard, grip, halo and a
  glint at the tip). **Radius** is its half-width and **Stretch** its length
  (2 × Radius × Stretch, tip to pommel). **Blade points** = motion: it points
  where it is moving (shots, orbits) and straight down when still; = angle: it
  holds **Blade angle °** (90 = down, -90 = up; Flip mirrors it). It hits
  along its whole length.
- **Lodging blades.** A damaging blade *without Pierce* doesn't vanish when
  it hits: it lodges in the target at the angle it struck (turned up to 10°
  so a stream of blades doesn't stack), only the part outside the target
  showing, and stays stuck there, following the target, for **Lodge ms**
  (fading over the last 300 ms). A lodged blade deals no more damage and
  can't be intercepted. **Lodge ms** 0 = it ends on the hit like any shot.
  Hits only happen where damage is dealt, so lodging shows in Battle (and in
  the Studio preview), not in Solo, where nothing takes damage.
- **Orb glow.** Orbs and bolts (sprite) have **Glow %** (brightness of the
  soft outer glow, 0 = none, 100 = as before) and **Glow size %** (how far it
  spreads). Both can be keyframed. *Soft petal orbs* is a dim-glow petal preset.
  The game's legacy JSON petals layer (mage, new_fighter) reads the same as
  `orb_glow` / `orb_glow_size` (the layer's old `glow` field is unrelated).
- **Saving.** **Save FX to folder** writes `<name>.fxkit.json` next to the
  images. Work also autosaves in the browser per character.
- **Controls.** `space` play/pause, `← →` step a frame, left-drag moves the
  target, right-drag pans, the mouse wheel zooms.

Format and engine contract: [`FX_KIT_SPEC.md`](FX_KIT_SPEC.md).
Runtime reference: `studio/fxkit.js`.

**Keeping the Studio and the game in step.** The game plays `.fxkit.json`
with `laser/fxkit.py`, a hand-kept port of `studio/fxkit.js`; trigger
conditions run in `laser/actions.py` and the Tactical retreat in
`laser/retreat.py`. After changing a default, a condition type, a scaled
parameter or a retreat constant on either side, run (from the game folder):

    python tools\fx\check_parity.py

It compares every table the two sides share and lists any difference (exit
code 1). "agree on every shared table" means an effect plays in Solo and
Battle exactly as the Studio previews it.

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
