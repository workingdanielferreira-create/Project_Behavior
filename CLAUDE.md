# Project Behavior — Claude Session Rules

## Project Overview
A Python/PyQt5 desktop overlay game featuring two combat figures — a **swordsman** and a **runner/shooter** — engaging in autonomous combat across two running processes via shared-memory IPC.

- **Repo:** `workingdanielferreira-create/Project_Behavior`
- **Source files:** All game logic lives under `laser/` subdirectory

## Core Source Files
```
laser/__init__.py
laser/action_log.py
laser/ai.py
laser/app.py
laser/assets.py
laser/combat.py
laser/components.py
laser/config.py
laser/figure.py
laser/geometry.py
laser/ipc.py
laser/modes.py
laser/motion.py
laser/palette.py
laser/platform_win.py
laser/systems.py
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

### Code Patching Rules
- **Atomic block replacement only** — identify full start/end markers and rewrite the block completely in one operation
- Never chain multiple small `str_replace` patches on the same region — reindentation and ordering bugs accumulate
- After any successful edit, treat all earlier views of that file as stale — re-fetch before further edits

## Key Architecture Notes

### IPC & State
- `enemy_projs` is re-read from shared memory each tick — local filtering is discarded; persistent suppression requires fingerprinting or per-tick re-erasure
- State flag ordering matters: setting two mutually exclusive flags simultaneously causes one FSM branch to consume all ticks — use pending flags and arm second state after first completes
- `c.busy` side effects: setting `c.slashing = True` inside parry or secondary triggers halts figure movement via the `busy` property — avoid unless intentional

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
