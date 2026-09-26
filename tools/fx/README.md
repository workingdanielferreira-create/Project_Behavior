# Character creation pipeline

| Phase | Tool | Output |
|---|---|---|
| 1. Rig & animate | `rigforge.html` (Rig Forge) | `pb_character` JSON: rig, weapon, every action's keyframes |
| 2. FX | `studio/fx_studio.html` (FX Studio) | the same character plus an `fx_studio` block, or a standalone `<name>.fxkit.json` FX pack |
| 3. Bake | `rigforge_bake.py` | sprite PNGs + `bake_manifest.json` (now including the per-frame joint table) |

## FX Studio

Open `studio/fx_studio.html` in a browser, straight from disk; it needs no
server. Import (or drop) a Rig Forge export; sources are in `sources/`. Every
action plays frame for frame as it does in Rig Forge, and you build FX on it
from the engine's own drawing primitives:

- **ribbon**: the laser-trail routine
- **arc**: crescent slash
- **beam**: segmented rich beam
- **sprite**: orbs and bolts
- **particles**
- **glow**: spheres
- **ghost**: afterimages

Each effect anchors to a joint (hand, blade tip, head…), moves (attached,
static, travel, homing, zigzag, orbit), takes a colour (the character palette,
a gradient or a solid colour) and plays over a range of frames.

Each effect also has a **Deals damage** checkbox (Purpose panel). Unticked, the
effect is visual only. Ticked, it's an attack with HP per hit, pierce, a re-hit
interval and knockback. It hits wherever its drawn shape touches the target's
hurt circle (16 px, adjustable as "hurt r"). The Studio shows the circle
flashing, floating damage numbers and a per-loop damage total. Damaging effects
show ⚔ in the list and a red bar on the timeline.

- Built-in presets rebuild the game's existing effects with their `config.py`
  numbers. **Save as preset** keeps your own, and **Export**/**Import** moves
  them between machines.
- Work autosaves in the browser.
- Controls: `space` play/pause, `← →` step a frame, left-drag moves the target,
  right-drag pans, the mouse wheel zooms.

Format and engine contract: [`FX_KIT_SPEC.md`](FX_KIT_SPEC.md).
Runtime reference: `studio/fxkit.js`.

> **Status:** Phase 1 (Studio + format + joint table) is done. The game does
> not play `fx_studio` effects yet; that's Phase 2 (`laser/fxkit.py`, see the
> checklist in FX_KIT_SPEC.md §7).

## Legacy

`fx_creator.html` + `rig.js` / `fx_engine.js` / `character_creator.js` /
`main.js` are the retired Character Wizard (see `WIZARD_AUDIT.md`). Its rig
differs from Rig Forge's, so it can't open Rig Forge characters. It stays only
for reference and for existing `pb_fx v1` files: `python tools/fx_preview.py`
still hot-reloads the newest `*.fx.json` in this folder.
