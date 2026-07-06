# Project Behavior — FX Creator / Character Wizard: Full System Audit
Generated from a line-by-line read of `tools/fx/*` at current `main` SHAs (fx_creator.html `b96eadf4`, rig.js `99dadbb2`, fx_engine.js `fefb3911`, character_creator.js `8d4412bc`, main.js `bad7ca05`, fx_creator.css `1aca4ee5`).

This is not a "what's broken" bug list — it's a map of **every piece that exists**, **what it does**, **who else touches the same concept**, and **where that creates overlap, ambiguity, or dead weight**. Use it as the reference before touching anything in `tools/fx/`.

---

## 1. File map & responsibilities

| File | Lines | Role |
|---|---|---|
| `fx_creator.html` | 39 | Static shell: 3-pane layout (`#left` wizard/layers, `#mid` canvas/timeline/bottom bar, `#right` step form/layer props), plus the hidden `#json` export/import overlay. No logic. |
| `fx_creator.css` | 38 | Dark theme, fixed-width side panels (230px / flex / 300px), `.row`/`.wstep`/`.layer`/`#tl` primitives shared by every panel. |
| `rig.js` | 185 | Humanoid skeleton math: pose keys (`PK`), forward kinematics (`joints()`), body/weapon drawing, target-dummy geometry + hitboxes, mouse-driven pose dragging, camera pan/zoom, pivot gizmo for FX layers. **No JSON schema, no wizard flow — pure geometry + input.** |
| `fx_engine.js` | 413 | FX layer schema (`DEF`), field metadata (`FIELDS`), per-layer battle properties, trigger system for layers (`trig`/`trig_ref`), keyframe timeline, layer list UI, hit detection vs. dummy, simulation tick, canvas render, `pb_fx` export/import. |
| `character_creator.js` | 465 | The wizard itself: action definitions, attack-pattern/combo/ultimate-playback/special-ability subsystems, activation-trigger system for actions, character model (`CH`), weapon polyline math, wizard step navigation, per-step form rendering, `pb_character` export/import. |
| `main.js` | 4 | `window.onload=()=>{rsz();bootWizard()}` — the entire bootstrap. |

Load order in HTML: `rig.js → fx_engine.js → character_creator.js → main.js`. Everything is global scope, no modules — every function/const in every file is reachable from every other file. This is why the "overlap" *feels* structural: there is no namespacing to signal which subsystem a given identifier belongs to (e.g. `trig` the per-layer property vs. `trigToggle`/`TRIGGER_TYPES` the per-action property are one edit-distance apart in the same global scope).

---

## 2. The single biggest structural issue: **six systems that all answer "when/how does this character deal or take damage," with different vocab, different data homes, and only loose cross-references**

The wizard has accreted one subsystem per feature request, each self-contained with its own preset library, its own `_SEMANTICS` doc-string block, and its own step in the wizard — but they were never unified into one mental model. Concretely:

| # | System | Lives at | Governs | Damage field | Wired to engine? |
|---|---|---|---|---|---|
| 1 | **Per-FX-layer battle** (`ensureBattle`, `battleHtml`, `FX_SEMANTICS`, `BATTLE_SEMANTICS`) | `layer.battle = {damage, attack:{explode,scatter,pierce,slash}, defence}` on any FX layer with `can_hit=true` | Any hit from any action's FX layers (attack_normal, attack_special, ultimate, defend) | `battle.damage` (0–100, per layer) | Yes — `combat.py fire_character_action()` |
| 2 | **Attack Pattern** (`ensureAttackPattern`, cone/zigzag/homing/beam cycles) | top-level `attack_pattern{enabled,damage,interval_ticks,cycle_pause_ticks,cycle[]}` | A **second, parallel** ranged-fire loop that fires *instead of* attack_normal's own FX layers when `enabled` | `attack_pattern.damage` (separate number) | Yes — `combat.fire_attack_pattern()` / `systems.ProjectileSystem._fire_attack_pattern()` |
| 3 | **Combo** (`ensureCombo`, dash/arc FSM) | top-level `combo{max_hits,cooldown_ticks,...}` | Melee dash-in / follow-up timing for `uses_melee` characters | none (see below) | Partially — FSM timing yes, **damage still hardcoded flat 1 HP** (`COMBO_SEMANTICS.damage`) |
| 4 | **Ultimate Playback** (`ensureUltimatePlayback`, crescent/beam) | top-level `ultimate_playback{style,...}` | A big automatic visual (X-crescent or beam volley) that plays **on top of** whatever the Ultimate action's own FX layers/activation_triggers do | none — pure visual, damage still comes from system 1 on the ultimate action's own can_hit layers | Yes — `ultc_cfg()`/`beam_cfg()` in `combat.py` |
| 5 | **Special Ability** (`sabSet`, presets: shield/heal/clone/time_slow/rage/teleport/dual_defense) | `special_ability{preset, params:{duration_ms,cooldown_ms,magnitude}, fx_layers[]}` | A named mechanic slot | `magnitude` (generic, meaning changes per preset) | **Only the generic params are read anywhere per `IMPLEMENTATION_NOTES` — no note claims any engine code interprets `preset` to actually run "clone" or "time_slow" logic.** This is a label with no confirmed interpreter. |
| 6 | **Activation Triggers** (`ensureTriggers`, hp_threshold/on_impact/after_on_impact/after_on_hit/radius_proximity) | per-action `activation_triggers[]` + `retrigger_cooldown_ms` | *Whether the whole action fires at all* (OR logic across enabled trigger types) | n/a (gating, not damage) | Yes — `ai.py evaluate_activation_triggers()` |

**Why this matters for "syncing everything together":** systems 1–4 can all be active on the *same* action (e.g. `attack_normal`) simultaneously with no wizard-level warning. A character can have `attack_pattern.enabled=true` (system 2, its own damage number) **and** `can_hit` FX layers with `battle.damage` set on the `attack_normal` action (system 1) at the same time — nothing in the UI tells the author these are mutually exclusive in practice (system 2's note says "melee-style characters... fire through the existing per-layer battle path *instead*," implying exclusivity, but the wizard never disables/hides system 1's UI when system 2 is enabled, or vice versa).

---

## 3. A second, quieter overlap: **"trigger" means three different things depending on which panel you're looking at**

| Concept | UI location | Options | Scope | Consumed by |
|---|---|---|---|---|
| (a) **Top-bar "Action trigger"** dropdown (`$('trig')`) | Always-visible top bar of the mid canvas | `on_hit/on_dash/on_fire/on_death/on_parry/on_ult/ambient` | Stored as `a.trigger` per action, exported in both `pb_fx.trigger` and `pb_character.actions[k].trigger` | **No `IMPLEMENTATION_NOTES` entry references `actions[k].trigger` being read by any engine function.** For custom (non-swordsman/runner) actions this looks like a legacy/vestigial field carried over from the standalone-FX (`pb_fx`) format, where it once meant something, but not confirmed wired for character actions. |
| (b) **Per-FX-layer `trig`** (`TRIG_OPTS`, set in each layer's Properties panel) | Right panel, per selected layer | `immediate/on_hit/on_dash/on_fire/on_death/on_parry/on_ult/ambient/after_fx/after_layer` | Controls *when within the action's playback* this one layer spawns (chains off other layers/actions) | Yes — this is the authoring-time-only chain logic (`layerStart()`), it's baked into keyframe/layer timing before export, not a runtime concept the game engine re-derives |
| (c) **Per-action `activation_triggers[]`** (Activation Triggers section) | Right panel, shown only for `attack_special`/`ultimate`/`special_ability` steps | `hp_threshold/on_impact/after_on_impact/after_on_hit/radius_proximity` | Whether the **entire action** is allowed to start at all | Yes — `ai.py evaluate_activation_triggers()` |

The confusing part: **(b)'s `on_hit`** means *"this specific layer plays because another layer with `can_hit` already landed a hit"* (an offensive chaining concept — visual follow-through), while **(c)'s `on_impact`** means *"this whole action starts because THIS character got hit by the enemy"* (a defensive reaction concept). Same root word, opposite actor, different data model, different UI section. Anyone reading the exported JSON without the in-editor context has no way to tell these apart from naming alone.

---

## 4. Third overlap: **"defense/defence" has six different spellings of the same idea, none pointing at each other**

| Representation | Type | Values | Where it lives | Relationship to the others |
|---|---|---|---|---|
| `CH.defense` | character-level string | `'block' \| 'dodge'` | Setup step dropdown | Determines which keyframe set (`defend_block` vs `defend_dodge`) seeds the `defend` action |
| Action key `defend` | wizard step | n/a | `ACT_DEFS` | Primary defense action, trigger defaults to `on_parry` |
| Action key `defend2` | wizard step | n/a | conditionally injected in `wizSteps()` | Only appears if `special_ability.preset==='dual_defense'`; uses whichever of block/dodge `defend` did *not* use |
| `special_ability.preset==='dual_defense'` | enum value inside an unrelated 5-value-plus preset list (`SAB_PRESETS`) | boolean-ish | Special Ability step | The *only* way to unlock `defend2`; a defense-system toggle hidden inside the special-ability picker |
| exported top-level `dual_defense` | boolean, derived (`CH.special_ability.preset==='dual_defense'`) | `true/false` | `buildCharJson()` output | Per project memory: **"Top-level `defense`/`dual_defense` JSON fields remain unwired"** on the engine side — exported but not consumed |
| exported top-level `defense` | string, `CH.defense` passthrough | `'block'/'dodge'` | `buildCharJson()` output | Same unwired status per memory |
| `layer.battle.defence` | per-FX-layer enum | `'none' \| 'deflect' \| 'block'` | Any `can_hit` layer's Battle panel | **Completely separate system** — this is "what visual/effect happens to an *incoming enemy* FX that hits one of *my* `can_hit` layers," not the character's own defend action at all. Note `'block'` is reused here with a different meaning (ring erases incoming FX, −50% dmg) than `CH.defense==='block'` (defend-action animation style). |

Net effect: the word "block" appears with two unrelated meanings in the same JSON file, and "defense" has a top-level unwired stub sitting next to a fully-functional but differently-named `defend`/`defend2` action pair.

---

## 5. FX Layer type inventory (the `DEF` object, fx_engine.js)

Nine layer types, each with its own default-property bag. Property names are heavily reused across types but don't always mean the same thing, and three "steering" mechanisms (`homing`, `travel_forward`, `follow`) coexist on the same layer types with subtly different rules:

| Type | Unique purpose | Shares `homing`? | Shares `travel_forward`? | Notes |
|---|---|---|---|---|
| `particles` | burst or stream of dots/sparks/squares | ✅ | ✅ | `burst` bool switches burst-vs-stream; also has `size_over_life`, `shape` |
| `ring` | expanding circle | — | — | used both as an authored layer type *and* auto-spawned for `battle.defence==='block'` (`spawnBFX('ring',...)`) |
| `flash` | radial glow burst | — | — | has optional `rays` |
| `crescent` | arc sweep | ✅ | ✅ | used both as authored type *and* auto-spawned for `attack.slash`, `defence.deflect` (`onBattleHit`) |
| `trail` | continuous emission along a path | — | — | shares most particle fields but no `homing`/`travel_forward` |
| `afterimage` | ghost-pose or ghost-box trail | — | — | `ghost_rig:true` freezes a full skeleton snapshot; otherwise draws a rounded box |
| `image` | user-uploaded PNG/JPG billboard | — | — | only type with a pivot **and** independent scale handle (PowerPoint-style gizmo in `rig.js`) |
| `beam` | segmented line with animated width/travel | — | — | has its own `travel_speed`/`detach_ms` travel model, **separate from** `travel_forward`/`travel_forward_speed` (both can theoretically be set; `travel_speed` wins if nonzero, else falls back to `travel_forward_speed` when `travel_forward` is on — a 3rd travel knob living in the same object) |
| `petals` | orbiting defensive interceptors | — | — | only type with no `trig`/`can_hit` (deleted explicitly: `delete DEF.petals.can_hit`), its own state machine (`hover/intercept/cooldown`) |

Three independent "does this FX move toward the target" flags exist simultaneously on `particles`/`crescent`/`beam`:
1. `homing` (+ `homing_multi`, `hit_rate_ms`, `homing_speed` for crescent) — steers every tick *until first contact*, then by default freezes heading (`homing_multi` keeps it live).
2. `travel_forward` (+ `travel_forward_speed`, `travel_homing`) — aims **once** at spawn and flies straight, unless `travel_homing` is also on (which re-adds the "keep tracking" behavior `homing_multi` already provided, via a different flag).
3. `beam`'s own `travel_speed`/`detach_ms` — a **third**, beam-only, notion of "travel" (the head/tail of the beam segment advancing), unrelated to steering-toward-target at all — it's about the beam visually "growing out" from the source.

These three are documented individually in `FX_SEMANTICS` (each has its own paragraph) but nothing cross-references that `travel_homing` and `homing_multi` are two spellings of nearly the same re-aim-after-contact idea for different code paths.

---

## 6. Wizard step inventory (character_creator.js `wizSteps()`)

Fixed spine, in order:
1. **Character Setup** — name/display_name/description, archetype (`shooter/melee/New`) + predicates, wander, HP/speed/scale/attack-radius stats, palette, bone lengths, `defense` (block/dodge).
2. **Weapon Designer** — polyline point editor (click-to-add, drag-to-move) feeding `weapon.points/thickness/color`.
3. **`idle`** action (ambient, no FX by convention)
4. **`run`** action (ambient)
5. **`attack_normal`** action → then two extra steps inserted right after: **Attack Pattern**, **Melee Combo** (both apply to this one action conceptually, but live as separate wizard steps, not sub-tabs of it)
6. **`attack_special`** action (has Activation Triggers UI)
7. **`ultimate`** action (has Activation Triggers UI) → then **Ultimate Playback** step inserted right after
8. **`defend`** action (on_parry) — *(`defend2` conditionally inserted after Special Ability if `dual_defense`)*
9. **`special_ability`** action (preset picker + generic params + Activation Triggers UI)
10. **`impact`** action (on_hit, plays when the character itself is hit)
11. **Review & Export**

Observations:
- Attack Pattern / Melee Combo / Ultimate Playback are **injected mid-list** next to the action step they relate to, but are structurally identical in kind to top-level character fields (like Setup), not action-specific fields — the wizard's own step numbering conflates "one form per action" with "one form per top-level JSON block," which is why the flow feels like it's jumping between two different data models.
- `special_ability`'s Activation Triggers panel lets you gate a "shield/heal/clone/..." ability on HP thresholds etc. — but as noted in §2, nothing confirms the *preset itself* (shield vs clone vs time_slow) does anything engine-side beyond generic duration/cooldown/magnitude.
- `impact` action exists as a full wizard step (pose + FX layers) but has **no** Activation Triggers section and isn't cross-linked to the *separate* `activation_triggers: on_impact` type available on other actions — i.e., there's a dedicated `impact` action AND a generic `on_impact` trigger type usable on *other* actions, and it's not documented anywhere why both exist or how they differ in practice.

---

## 7. Export schema summary (`buildCharJson`, `pb_character` v2)

Top-level keys actually written: `format, version, name, display_name, description, archetype, predicates, movement{wander_strength}, stats{max_hp,chase_speed,follow_speed,scale,basic_attack_radius}, rig, modes, bones, palette, defense, dual_defense, weapon{points,thickness,color,anchors}, special_ability, attack_pattern, combo, ultimate_playback, actions{...}, target_dummy, battle_semantics, fx_semantics, activation_trigger_semantics, attack_pattern_semantics, combo_semantics, ultimate_playback_semantics, implementation_notes`, plus any unknown passthrough keys from `CH._extra`.

Each action in `actions{}` carries: `trigger, duration_ms, keyframes, fx_layers[], activation_triggers[], retrigger_cooldown_ms`.

Each `fx_layers[]` entry carries its type-specific `DEF` fields **plus** `trig/trig_ref/trig_delay_ms/can_hit` **plus**, if `can_hit`, `battle{damage,attack{explode,scatter,pierce,slash},defence}`.

The file also **re-embeds five large human-readable `_semantics` doc-string blocks every single export** (`BATTLE_SEMANTICS`, `FX_SEMANTICS`, `ACTIVATION_TRIGGER_SEMANTICS`, `ATTACK_PATTERN_SEMANTICS`, `COMBO_SEMANTICS`, `UP_SEMANTICS`, plus `IMPLEMENTATION_NOTES`) — by design, so a fresh Claude session reading one character file has the full contract without re-reading source. This is a deliberate and good pattern for hand-off, but it does mean every character JSON file duplicates several KB of identical prose (worth knowing when diffing/reviewing character files — differences in `*_semantics` blocks between two character files are almost always accidental drift from copy/paste of an older export, not intentional customization).

---

## 8. What is confirmed wired vs. confirmed NOT wired (per the code's own `IMPLEMENTATION_NOTES`)

**Confirmed wired (engine reads it, "no manual file edits" per the code's own claim):**
- stats/movement/archetype/predicates → `characters.py _register()`
- actions/keyframes/rig → `characters.py rasterize_character()`
- `attack_pattern` → `combat.fire_attack_pattern()` + `systems.ProjectileSystem._fire_attack_pattern()`
- `combo` (timing only, not damage) → `combat.combo_cfg()` feeding existing `advance_combat`
- `ultimate_playback` → `combat.ultimate_style()/ultc_cfg()/beam_cfg()`
- per-`can_hit`-layer `battle{}` → `combat.fire_character_action()`
- `activation_triggers` → `ai.evaluate_activation_triggers()`

**Confirmed NOT wired / explicitly flagged incomplete:**
- Melee **combo damage** — flat 1 HP regardless of `combo` block, "pending an IPC extension to carry a per-attacker amount" (same extension needed for `after_on_hit` crediting, per project memory).
- Top-level `defense` / `dual_defense` fields (per project memory).
- `special_ability.preset`-specific mechanics beyond generic duration/cooldown/magnitude — no `IMPLEMENTATION_NOTES` entry claims any preset (shield/heal/clone/time_slow/rage/teleport) has real behavior.
- Action-level `trigger` field (top-bar dropdown) for custom JSON actions — no `IMPLEMENTATION_NOTES` entry claims this is read anywhere.
- `target_dummy` — per your standing note, this is wizard-preview-only by design and must **never** be implemented as real spawn logic in `laser/`. Correctly, `IMPLEMENTATION_NOTES` doesn't claim engine wiring for it either — the wizard and the roadmap agree here, this one is *not* an inconsistency, just worth flagging so it isn't mistaken for a gap.

---

## 9. Smaller half-baked corners worth knowing about

- **Archetype `'New'`**: `wizSteps()`/Setup step supports a third archetype option `'New'` that unlocks manually editing all four `predicates` checkboxes independently — but `importChar()`'s archetype inference (`o.archetype || (weapon.points.length ? 'melee' : 'shooter')`) can never *produce* `'New'` on import; it's a setup-step-only escape hatch, not a durable schema value with defined re-import behavior.
- **`ATTACK_PATTERN_PRESETS`** advertises 4 presets (`runner_cycle/single_shot/wide_fan/homing_only`) but only `runner_cycle` claims to reproduce a real character's exact numbers (Runner's); the other three are original content with no engine-side character actually using them yet — fine as presets, but means "preset" here mixes "known-good replica" and "untested original" without labeling which is which.
- **`COMBO_PRESETS`/`UP_PRESETS`** same pattern: `swordsman_classic`/`crescent_classic`/`beam_classic` are replicas of existing hardcoded fighters; `fast_flurry`/`heavy_strikes` are untested originals.
- **Beam's three width knobs** (`width`, plus `w_start0/w_start1/w_end0/w_end1`): `width` (`FIELDS.width` exists) appears to be a legacy/unused single-value fallback (`const wBase=l.width??10`) now superseded by the four `w_*` fields — `width` itself has no visible UI row generator entry checked (`FIELDS` has `width` defined but I did not find it in the beam layer's `DEF` initial object — it's referenced defensively in render code (`l.width??10`) but never set by the Properties panel, meaning it's dead code reachable only via hand-edited or legacy-imported JSON).
- **`CH_KNOWN` passthrough allowlist** in `importChar()`: any top-level key not in this exact list gets silently stashed in `CH._extra` and round-tripped without ever being editable in the wizard — good for forward-compatibility, but it means a character file can carry data (e.g. from a future field a different tool added) that this wizard will faithfully preserve but never display, edit, or validate.

---

## 10. Recommended focus order (documentation-only judgment, not a decision — you asked for the map, this is what the map implies)

If/when you're ready to consolidate rather than just add more parallel systems:

1. **Pick one damage authority per action-type** (ranged vs melee vs ultimate) and make the wizard visually disable/gray the competing system(s) for that action, instead of letting `attack_pattern` and per-layer `battle.damage` coexist silently on `attack_normal`.
2. **Rename one of the two "block"s** (`CH.defense` value vs `layer.battle.defence` value) so a JSON reader — human or engine — can never confuse them.
3. **Collapse the three trigger vocabularies** (top-bar action `trigger`, per-layer `trig`, per-action `activation_triggers`) into clearly distinct field names in the exported JSON (they already are, technically — `trigger` vs `trig` vs `activation_triggers` — but the *UI labels* all say some variant of "Trigger," which is the actual source of the felt confusion even though the underlying JSON is fine).
4. **Confirm or cut** `special_ability` presets beyond the generic params — either wire `clone`/`time_slow`/etc. to real engine behavior, or relabel the preset picker as "cosmetic label only, not yet functional" so it stops reading as a finished feature.
5. **Resolve the top-level `defense`/`dual_defense` unwired fields** — either wire them or remove them from export so the JSON doesn't advertise a contract the engine doesn't honor.
6. **Delete or wire the dead `beam.width` field** once confirmed unused.

This document reflects the wizard code exactly as of the SHAs listed at the top — re-pull fresh SHAs before editing anything referenced here, per standing session rules.
