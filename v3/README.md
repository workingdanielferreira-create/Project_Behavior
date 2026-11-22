# Project Behavior V3 — 3D

The 3D game, built on Playtest 2 (*Behavior 3D Playtest v2*), now in its own window.
Self-contained like `v2/`: nothing outside `v3/` is touched.

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
| `kits.js` | character kits: moves, timings, damage, triggers, colours |
| `renderer.js` | WebGL renderer, scene, toon / ink / additive materials, 2D→3D mapping (`V`, `VA`) |
| `arena.js` | the arena: floor, sky dome, floating rocks, pillars, rim, stars |
| `fx.js` | **FX design**: primitives (slash, ring, dome, sparks, dust, star, crack, streak, moons, blades) |
| `state.js` | world state, timers (`later`, `ms2t`) |
| `models.js` | **fighter rigs and models** (`buildBody`) |
| `movestyle.js` | **movement styles** (FX Studio `movement_style` phases) + intent speed table |
| `tempo.js` | fight rhythm intents (port of `laser/tempo.py`) |
| `director.js` | director heat: calm / build / burst |
| `motion.js` | drift & snap motion |
| `combat.js` | actions, triggers, hits, damage, stun, K.O., reactions, tagging, projectiles |
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

Gameplay is unchanged from Playtest 2. This step only moved it into the window
and the module layout.
