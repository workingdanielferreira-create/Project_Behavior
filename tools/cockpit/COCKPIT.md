# Dev Cockpit — capture/replay/annotate loop

The Cockpit lets Daniel dissect real engine runs frozen tick-by-tick and
send pixel-and-object-precise change requests to Claude.

## Components

* `capture.py` — runs the REAL `laser/` engine headless in Claude's sandbox
  (PyQt5 offscreen) and records every tick. Zero engine modification; the
  only patches are harness-side (deterministic `os.urandom` + global
  `random` seed, scripted cursor, virtual 1920x1080 screen).
* `cockpit.html` — the viewer/annotator. Fetches
  `captures/latest.pbrun.json` from the repo (raw, public), or opens a
  local bundle file. Also usable directly as a Claude artifact.

## The loop

1. Claude captures a run: `python3 capture.py --mode battle --p1 X --p2 Y
   --seed N --ticks 625 --out latest.pbrun.json` and pushes it to
   `captures/latest.pbrun.json`.
2. Daniel opens the Cockpit, scrubs/pauses/steps, selects entities, draws
   arrows/circles/pen/text, attaches a reference image, types a request per
   annotation, and hits **Build request package**.
3. Daniel pastes the package JSON (and optionally the annotated PNG) into
   the Claude chat. The package carries the tick, the seed, the full state
   digest, and world-space coordinates + linked entity ids — enough for
   Claude to identify the exact object and code path.
4. Claude changes the real code, re-captures with the SAME seed (identical
   scenario), pushes the new bundle. Daniel presses **Reload run** —
   internal refresh, no rebuild.

## Bundle format — `cockpit_run v1`

```json
{
  "meta": {
    "version": "cockpit_run v1",
    "seed": 42, "mode": "battle", "p1": "new_fighter", "p2": "mage",
    "ticks": 625, "tick_ms": 16,
    "world_w": 1920, "world_h": 1080,
    "frame_w": 960, "frame_h": 540, "frame_scale": 0.5, "frame_every": 1,
    "engine_commit": "<sha>", "captured_at": "YYYY-MM-DD HH:MM:SS"
  },
  "frames": [
    {
      "t": 0,
      "png": "<base64 JPEG of the real paintEvent output>",
      "state": {
        "battle": true, "hitstop": 0,
        "figures": [{"side":0,"idx":0,"mode":"...","x":0,"y":0,
                     "hp":0,"max_hp":0,"facing_left":false,"flags":[]}],
        "projectiles": [{"id":1,"side":0,"cls":"Projectile","x":0,"y":0,
                         "vx":0,"vy":0,"dmg":1,"pierce":false,"hit":true}]
      },
      "events": ["CATEGORY: engine action_log line", "..."]
    }
  ]
}
```

Rules: fields are only ever ADDED to v1, never renamed/removed. A breaking
change bumps the version string and the Cockpit's ingest gate.

Projectile `id` is a per-run stable serial (StateRecorder identity map);
`hit: false` marks cosmetic projectiles (`hit_r_sq == 0`). `events` are the
engine's own `action_log` lines captured on the tick they fired.

## Request package — `cockpit_request v1`

Produced by the Cockpit's export. Contains run identity (seed/commit),
tick, the tick's full state digest, and annotations with `world_pts`
(engine pixel space), optional `linked_entity`, label, and Daniel's typed
request.

## Extending

* New capture stream → new `Recorder` subclass in `capture.py`, append to
  the recorder list. Never edit existing recorders.
* New annotation tool → new entry in the `TOOLS` registry in
  `cockpit.html` (down/move/up handlers in world coords).
* Scripted inputs / cursor paths → planned v2 recorder + `ScriptedCursor`
  per-tick script hook.

## Known limits (v1)

* Runs are AI-driven; no live steering. Same-seed determinism holds as
  long as engine logic stays wall-clock-free (it is today).
* Solo captures follow the scripted (fixed-center) cursor.
* Bundle size ≈ 25–30 MB for 625 ticks at 960x540; use `--frame-every 2`
  or lower `--quality` for longer runs.
