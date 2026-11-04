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
laser/camera.py
laser/worldscale.py
laser/terrain.py
laser/player.py
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
- Test keys (Solo + Battle): F10 = `World.toggle_freeze` (every fighter's body stops via `timefx.plan` body 0 = the Aegis-stun path: no moving / attacking / AI / cooldowns, still hittable; bullets, FX in flight, dust, pillars, camera keep running). F11 = `World.toggle_puppet`: `World.puppet_fig()` (first-picked FIELDED slot) has body 0 in `timefx.plan` and is moved by `motion.puppet_step` toward `w.cursor` in `Overlay._tick` after the side passes (own pace, walk frames, knockback still slides); ignores the freeze. F12 = `World.toggle_boulder_ghost` (`world.boulders_ghost`: pillars painted at `terrain.GHOST_ALPHA` 20% opacity via an offscreen layer). All three in `roster.RESERVED`
- Player control (`laser/player.py`, Solo + Battle): F4 = `World.toggle_player` (exclusive with F11). `World.player_fig()` = first-picked FIELDED fighter (`_first_fielded`) and only if `actions.is_image` (built-ins ignored). Arrows -> `world.player_dir` -> `motion.player_step` in MotionSystem (replaces AI movement, skips blinks/teleports; Alt+arrows unchanged). Ctrl+Z / X / C -> `player.press` buffers `world.player_req` (latest press, `BUFFER_MS`); `ActionRunner.update` calls `player.runner_tick` INSTEAD of the auto attack / triggered choice: chains attack_normal(_N) / attack_special(_N) / ultimate(_N), wrap, restart after the last one's `chain_reset_ms`; ignores conditions / cooldowns / Attack mode; special / ultimate cut into a normal attack. Tactical retreat off for it; Dodge (`dodge.tick` + counter) stays automatic. Ctrl+Space = `player.drop_hp` (HP to 25% of max, never raises). Ctrl+Shift held = sprint (`world.player_sprint` -> `motion.player_step(mult=player.sprint_mult)`: the character's tactical retreat `speed_pct`, else `SPRINT_PCT` 250; afterimages; sets `ctrl_used`). Keys in `roster.RESERVED`
- Pillar X-ray: `Terrain.paint_front` (pillars drawn over a fighter) paints every fighter behind that pillar as a flat tinted silhouette (`terrain._paint_silhouette`, HP-bar colour, `SILHOUETTE_ALPHA`) clipped to the rock's silhouette path (`_paint_pillar` returns it); skipped while F12 is on and in the start menu's frozen layer (`silhouettes=bodies`)
- `main()` uses `setQuitOnLastWindowClosed(False)`: the overlay is a Qt.Tool window, so closing the start menu would otherwise quit the game

### World Physics: Dust & Air
- `laser/worldfx.py` (Studio port `tools/fx/studio/worldfx.js`, page "🌪 Dust & Air"): world-owned dust / rocks / air. `worldfx.step(world)` runs once per tick after both sides (read-only on fighters); paint layers `paint_ground` (under fighters) / `paint_air` (over). Hybrid engine: closed-form rocks/sparks, simulated dust riding analytic air sources (blast, wake, curl, column, jet)
- Ground = slope: pscale grid; height z drawn straight up the screen; ground ellipses rounder the farther away (`flat_near` -> `flat_far`); screen edges are walls (`motion.check_walls` -> `note_wall`)
- Settings: `characters/world_physics.json` (`pb_world_physics`), per-character override `pack.world_physics` (any section). The Studio page writes the file directly once the game folder is linked; the game hot-reloads it (`watch_world`, ~1 s) and on F5 (`reload_characters` also clears `_wphys_cfg`). Smoke styles: `SMOKE_STYLES` (cel, billow, ink, swirl, flat, ring, stepped); `ground.style` default, per-event `style` (`default` = ground's), deep edit per style in section `smoke_<style>` (`smoke_look` = life curve; `ENUMS` validated). Sound barrier uses on-screen (position-scaled) speed. Hit-stop / shake / impact frames stay with each FX's own settings

### Destructible Terrain: Pillars & Rubble
- `laser/terrain.py`, settings = Dust & Air sections `pillars` (world only) and `rubble` (per-character override ok) in `world_physics.json`; Studio port tables in `worldfx.js` (`WP_SECTIONS` / DEFAULTS / RANGES / FIELDS / TITLES). `terrain.step(w)` runs in `Overlay._tick` after both sides, BEFORE `worldfx.step`; paint `terrain.paint_back` (rubble + pillars nobody stands behind, after `worldfx.paint_ground`) and `paint_front` (after the fighters). `apply_roster(reset=True)` -> `terrain.reset`
- Pillars: `count` kept around the fight (random within `radius_px` of the anchor / fighters' centre, `clear_px` from fighters, `gap_px` apart); a broken one is replaced after `respawn_s`, one at a time. Real obstacles for both sides (like walls; AI unaware): fighters pushed out of the flat ground footprint + subtle `repel` away from centre, knockback slides reflect; projectiles (side.projectiles -> `combat.kill_projectile`, travelling FX -> inst.age=life/dead, gun/ki rounds -> `RoundRef.stop`) blocked when `block_projectiles`; melee FX / built-in slashes & crescent waves (`melee_damage`) / blasts (`worldfx.scan_blasts` -> `terrain.note_blast`, `blast_reach`) hit once per source. ANY of speed (px/tick) >= `break_speed`, FX knockback >= `break_knockback`, damage >= `break_damage` breaks it and the hit passes; otherwise blocked + chip (`chip_pct` of damage, bodies `body_chip`), crumbles at 0 HP. Built-in ultimate crescents always break. Blink warps (`worldfx._WARPS`) are not speed
- Pillar look (2.5D): each pillar = a low-poly rock mesh (`terrain.rock_mesh(seed, facets)`, cached on `Pillar.mesh`), oblique projection screen = (bx + X', by - Z - Y'·s) so drawn height = collision height. Yaw = `view_yaw` x clamp((x - anchor x)/(`view_reach_frac` x width)): straight on at the anchor, one continuous rotation (no flip seam). s = sin(pitch), pitch `pitch_top`..`pitch_bottom` by screen y (never the underside). Back-face cull + far-first sort, cel-banded Lambert (light top-left), ink silhouette = fat ink pass under the facets; cracks/flash clipped to the silhouette
- Break FX (`Terrain._break`): 14 small puffs spread over the footprint and up the column (size NOT scaled by width, which made one capped 60px disc), drifting in a ~90 deg cone along the hit direction `ax` (away from the hitter), carried by a `terrain._Gust` air source. Leaves a crater (`Terrain.pits`, `_paint_pits`): jagged lip + inner wall + floor, rx = 1.25 x footprint half width, flattened by `flat_at`, lasts rubble `rest_s` + `fade_s`
- Rubble: `worldfx.WorldFx.move` hands landed rock-burst pieces to `terrain.note_rubble` at 72% of burst life (rest_s + fade_s). Boulders (`debris` with boulder sizes) on: knockback slide start >= `hit_knockback`, HP drop in a tick >= `hit_damage` (both crater if `crater`), fighter speed >= `speed` (half, smaller); `cooldown_ms` per fighter

### FX on the Ground & Rolling World
- Dust & Air section `ground_fx` (per-character override ok; `worldfx.WorldFx.scan_ground_fx`, after `scan_blasts`): FX Studio beams with battle damage MORE than `beam_min_damage` (30) lay a trench under their head (`terrain.note_mark` kind "trench"; ground = head y + the thrower's body-centre-to-foot offset `WorldFx.ground_off`), throw debris/dust there, and pull a spiral `Trail` from the head with the fighters' sound-barrier logic (`cfg(fig,"sonic")`, `ring_split`, Spiral `min_speed` gate on head speed / sscale). Travelling crescents (`crescent_wave` technique, travelling `arc`) with damage >= `crescent_min_damage` (40) lay a "streak". Ki/gun orb detonations (tq_ki, impact only) with damage >= `orb_min_damage` (40) -> `WorldFx.orb_crater` -> `terrain.note_crater` (a `Terrain.pits` crater with its own rest/fade, 9th field). Marks = `Terrain.marks` (`add_mark` / `end_mark` / `_age_marks` / `_paint_marks`, painted first in `paint_back`), last `mark_s` + `fade_s`
- Dust & Air section `roll` (world only; `Terrain.roll`, end of `Terrain.step`): anchor (`_centre`) in the outer `zone_frac` of the screen (x, and y if `vertical`) rolls the world the other way at up to `max_speed` px/s (linear to the edge, eased `ease_ms`). Pillars / rubble / pits / marks move and `worldfx.WorldFx.shift` moves dust, bursts, ground/crater rings and non-fighter air sources. Fighters, their FX and trails are NOT moved. Pillars past `margin_px` on the trailing side are dropped (no break); `_spawn_ahead` raises standing ones off the leading side (up to `spawn_ahead_px` out, staggered); the normal in-field respawn waits while rolling. Planet/anchor scaling unchanged (far ones come in small and grow)

### World Camera
- `laser/camera.py` (Studio port `tools/fx/studio/camera.js`, top-bar tab "🎥 World Camera"): paint-time VIEW only — never moves fighters; hit tests / walls / targeting / snapshots stay in screen coords. `World.camera` steps every tick (hit-stop included, not while the start menu pauses); `_paint_scene` applies it, the HUD is drawn after it (never zooms/shakes). Only the mouse cursor is mapped back (`Camera.screen_to_world` in `_tick`)
- Follow-cam frames all fielded fighters (Battle up to `max_zoom`, Solo fixed `solo_zoom`, never < 1.0x, view clamped on-screen); hit-stop punch-in via `World.punch_camera` (systems.py hit-stop + fxkit `_Host.hitstop`); `World.add_shake` = camera trauma (stacks)
- Cinematic shots (one at a time, priority ko > ultimate > switch_in > clash): ultimate is detected by the camera itself (`actions.current_action_name == "ultimate"`, clones excluded); `World.camera_shot(kind, x, y, fig)` from `tag._swap` (switch_in), `World.on_figure_death` (ko) and `clash.step` (clash). KO also runs a REAL slow-mo (`World.slowmo_*`, sim advances `ko_slow` of a tick per tick, both sides); Solo's final KO freezes the sim for the KO shot (`World.ko_quit_ticks`), then quits as before
- Depth tilt: a projective (perspective) term in the camera matrix, scene space, along `position_scale`'s depth axis (bottom-left near, top-right far): p' = A + (p-A)/w, w = 1 + k(t(p) - t(A)), A = NEAREST fighter (fighters only ever pulled in toward A, never off-screen). k = depth_base + depth_gain*(1 - t_A) + depth_shot during a cinematic shot. Drawing only: position_scale / hits / walls / dust untouched. `Camera.matrix` = the full 3x3 (QTransform row-vector convention), cursor inverse = its inverse. Qt raster perspective is ~2x paint cost: `Camera.note_paint` (timed in `Overlay._paint`) turns depth off for the session after ~2 s over `depth_budget_ms` (notice shown); reload/F5 re-arms
- World anchor scaling (`anchor_scale`, default on; `laser/worldscale.py`): invisible anchor = eased centre of all fielded fighters (`Camera._step_anchor` -> `worldscale.set_anchor`). `combat.position_scale` / `position_speed_scale` and `worldfx.pscale` / `sscale` use size = clamp(vertical (x5 bottom .. x1 top) x distance-from-anchor (x1 .. x0.10 at `dscale_far_frac` x width, `dscale_curve`), `scale_min`..`scale_max`); pace linear in size (`speed_min`..`speed_max`). While on: follow-cam centres on the anchor at fixed `anchor_zoom` (only reduced to fit; no closeness zoom-in, that's the scaling's job) and the depth tilt axis is vertical. Off = old corner grid + old follow zoom
- Tiny planet (`planet`, default on, needs `anchor_scale`; `laser/worldscale.py`): the anchor is the top of a small planet. worldscale's distance term becomes a sphere curve (theta = dist/(`planet_reach_frac` x width) x `planet_horizon_deg`; size = `planet_far` + (1-far) x normalised cos theta), so it applies to every fighter, FX and pace. The world layers (terrain pillars/rubble, worldfx rings/rocks/sparks/dust) are also squashed along the line to the anchor (k = 1 - `planet_squash` x (1-cos theta)) about each object's OWN spot via `worldscale.squasher(p, sw)` (`.at(x, y)` per object, `.done()`). Nothing moves, so collisions still line up. Trails and sonic cones stay flat. While on, `Camera.depth_live()` is False (planet replaces the depth tilt)
- Settings: `characters/camera.json` (`pb_camera`), hot-reloaded ~1 s and on F5; the Studio tab writes it through the Dust & Air folder link. `tools/fx/check_parity.py` checks DEFAULTS / RANGES / FORMAT

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
- Body ink outline: every fighter sprite (Figure.draw, prebattle idle pose, clones) is drawn via `combat.ink_outlined(frame)` = cached pixmap with a solid `config.BODY_OUTLINE_PX` (1) black line, padded by pad px (draw at -w//2-pad). Sits under a character's own `outline_glow` halo (both kept)
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
