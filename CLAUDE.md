# Project Behavior — Claude Session Rules

## Project Overview
A Python/PyQt5 desktop overlay game featuring autonomous combat figures (built-ins: a **swordsman** and a **runner/shooter**, plus JSON-authored characters). Battle mode hosts two independent sides in ONE process: key `1` cycles P1's character, key `2` cycles P2's character and fields/retires them. Each side sees the other only through per-tick read-only snapshots (`partner_figures` / `enemy_projs`), preserving fully independent decision streams.

- **Repo:** `workingdanielferreira-create/Project_Behavior`
- **Source files:** All game logic lives under `laser/` subdirectory

## Core Source Files
```
laser/__init__.py
laser/action_log.py
laser/ai.py
laser/app.py
laser/assets.py
laser/clash.py
laser/clashfx.py
laser/swordfx.py
laser/strikefx.py
laser/kickfx.py
laser/hitfx.py
laser/powerfx.py
laser/roster.py
laser/startmenu.py
laser/tag.py
laser/hpbars.py
laser/gunfx.py
laser/combat.py
laser/components.py
laser/config.py
laser/figure.py
laser/geometry.py
laser/modes.py
laser/motion.py
laser/movestyle.py
laser/palette.py
laser/platform_win.py
laser/systems.py
laser/unique.py
laser/summoner.py
laser/weaponfx.py
laser/worldfx.py
```

## Mandatory Session Rules

### Before Every Implementation
- **Ask clarifying questions before making changes**, especially for spatial/geometric behavior — never interpret and act unilaterally
- Use the pop-up multiple choice function for new inclusions, implementations, or if a requested feature may already be completed
- **All changes must be applied to both Solo mode AND Battle mode** without exception

### GitHub Workflow
- Fetch files via GitHub REST API before patching: `GET /repos/workingdanielferreira-create/Project_Behavior/contents/laser/{file}`
- Decode content via `base64.b64decode(d['content'])`
- **Always fetch a fresh SHA immediately before each PUT request** — stale SHAs cause 409 conflicts
- Push via PUT with fresh SHA, base64-encoded content, and a descriptive commit message
- **Run `ast.parse()` syntax validation on every file before pushing** — this catches bugs before they reach the repo
- **Auto-merge after every update** — once an update is pushed and its PR is open (validation passed), merge the PR into `main` straight away; don't wait for Daniel to say "merge"

### Code Patching Rules
- **Atomic block replacement only** — identify full start/end markers and rewrite the block completely in one operation
- Never chain multiple small `str_replace` patches on the same region — reindentation and ordering bugs accumulate
- After any successful edit, treat all earlier views of that file as stale — re-fetch before further edits

## Key Architecture Notes

### Battle Snapshots & State
- `enemy_projs` is rebuilt from the opposing side's live projectiles each tick (tuple: x,y,vx,vy,r,g,b,damage,proj). Interceptions destroy the bullet AT THE SOURCE via `combat.kill_projectile(tuple[8])` — never mutate `alive` directly (it's a derived property)
- Cross-side knockback rides `fig.combat.hit_pending/hit_vx/hit_vy`, delivered by `World.refresh_battle` at the start of the next tick
- Deaths in battle remove the fallen fighter (survivor continues solo); deaths in solo end the run — routing lives in `World.on_figure_death`
- State flag ordering matters: setting two mutually exclusive flags simultaneously causes one FSM branch to consume all ticks — use pending flags and arm second state after first completes
- `c.busy` side effects: setting `c.slashing = True` inside parry or secondary triggers halts figure movement via the `busy` property — avoid unless intentional

### Roster, Start Menu & Tag
- `laser/roster.py`: 4 slots (A-D), each char / team (2 teams, ANY split: 1v3, 3v1, 2v2, 4v0 = Solo) / `link` (tag partner slot index, mutual, same team) / hotkeys (cycle, ultimate, special, tag); saved to `roster.json` (gitignored). `pick` = selection order (HP bars, fielding, which tag partner starts). `world.tag_pairs` is a LIST (a team can hold 2 pairs); `roster.PAIR_COLORS[pair index]` = menu border + HP bracket colour
- `laser/startmenu.py`: the character select WINDOW (the overlay is click-through). Opens on `--prebattle` and Ctrl+Shift+.; game pauses via `world.prebattle.open`. Start = keep unchanged fighters' state, Reset & Start = fresh
- Every roster change goes through `World.apply_roster` (menu, slot cycle keys, Alt+Left/Right)
- `laser/tag.py`: two Tag slots on one team = tag pair. Benched fighter is OUT of `side.figures` (frozen; `unique.cd_now` subtracts `fig.bench_ticks`). Switch = outgoing plays `switch_out`, then incoming takes its spot and plays `switch_in`. `switch_in`'s FX Studio conditions are read against the ON-FIELD partner's runner ctx; its cooldown_ms = pair cooldown. KO with a standing partner = forced switch (no loss). `switch_in`/`switch_out` never auto-trigger in `actions.py` (`SWITCH_ACTIONS`)
- `laser/hpbars.py`: Team 1 top-left, Team 2 top-right, selection order
- `laser/targeting.py`: FX Studio "Targeting" (`pack.targeting`). EVERY enemy lookup goes through `World.enemy_target(fig)` / `World.target_index(fig)` (taunt still overrides) — never call `_nearest_enemy(fig.x, fig.y)` for a fighter. Modes nearest/farthest/lowest_hp/highest_hp/stick/last_attacker/weighted + hold/margin, range, team focus/spread, conditional rules. Built-ins = nearest. Snapshots add `partner_ids` / `partner_hp` / `partner_target`; hits set `fig.last_hit_by`
- `main()` uses `setQuitOnLastWindowClosed(False)`: the overlay is a Qt.Tool window, so closing the start menu would otherwise quit the game

### World Physics: Dust & Air
- `laser/worldfx.py` (Studio port `tools/fx/studio/worldfx.js`, page "🌪 Dust & Air"): world-owned dust / rocks / air. `worldfx.step(world)` runs once per tick after both sides (read-only on fighters); paint layers `paint_ground` (under fighters) / `paint_air` (over). Hybrid engine: closed-form rocks/sparks, simulated dust riding analytic air sources (blast, wake, curl, column, jet)
- Ground = slope: pscale grid; height z drawn straight up the screen; ground ellipses rounder the farther away (`flat_near` -> `flat_far`); screen edges are walls (`motion.check_walls` -> `note_wall`)
- Settings: `characters/world_physics.json` (`pb_world_physics`), per-character override `pack.world_physics` (any section). The Studio page writes the file directly once the game folder is linked; the game hot-reloads it (`watch_world`, ~1 s) and on F5 (`reload_characters` also clears `_wphys_cfg`). Sound barrier uses on-screen (position-scaled) speed. Hit-stop / shake / impact frames stay with each FX's own settings

### Combat System
- Dashslash and arcslash chosen 50/50 per attack; follow-ups also 50/50 with 0.2s type lock; 3-hit cap with ~1s cooldown
- Parry: 30px detection radius, 0.3s cooldown and stance duration
- Swordsman ultimate triggers at HP thresholds (70%, 50%, 30%) tracked via `sword_ult_fired_thresholds` set
- Runner: 100 HP, ultimate triggers at 30% HP with survival teleport; shoot cycle is CONE→ZIGZAG→HOMING twice per second
- Knockback immunity: Runner cycles vulnerable (3 hits) → immune (10 hits) indefinitely

### Rendering
- LUT assignment on mode switch: `cycle_mode` must explicitly update `fig.lut` and `fig.trail.lut` after `set_mode()`
- Swordsman trail: red-to-crimson gradient (`LUT_RED`) via `lut_for_mode()`
- HP display: Runner label shifted 70px left; swordsman label unchanged; differentiated via `fig.mode.uses_melee()`
- One bullet per direction per phase: zigzag and multi-directional phases must fire exactly one bullet per direction

## Workflow for Recovering Lost Code
```bash
curl .../contents/laser/combat.py?ref={commit_sha}
```
Use against a known-good commit hash to retrieve prior versions for diffing.

## Communication Style
- Daniel communicates corrections directly and tersely — implement precisely as specified
- Design thinking happens before code — ideation phases are explicitly separated from implementation requests
- Daniel tests on Windows after each push and reports observed behavior; diagnose from symptoms
