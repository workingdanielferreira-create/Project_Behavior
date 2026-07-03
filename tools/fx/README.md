# FX Pipeline

1. Create/tune an effect in the **FX Creator** (HTML tool, live preview).
2. Export → save the `*.fx.json` into this `tools/fx/` folder.
3. Run `python tools/fx_preview.py` — it auto-loads the newest `.fx.json`
   and hot-reloads instantly whenever the file changes on disk.
4. Hand the JSON to Claude with your request; it will be implemented
   identically in **both Solo and Battle modes**.

Schema: `format=pb_fx v1` — name, trigger (on_hit/on_dash/on_fire/on_death/
on_parry/on_ult/ambient), duration_ms, anchor, layers[] of type
particles | ring | flash | crescent | trail | afterimage | beam.
