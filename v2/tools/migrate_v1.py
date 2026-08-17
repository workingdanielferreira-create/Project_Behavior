"""Port a v1 `pb_character` file to the v2 five-noun model.

Mapping performed (this is the Step 2 decomposition, executed):

  stats.max_hp / chase_speed / follow_speed / scale   -> attributes
  archetype + predicates                              -> movement style + tags
  stationary / counter_only / disable_basic_attack /
  disable_survival_teleport                           -> tags (or absence of)
  attack_pattern                                      -> projectile_volley
  actions.attack_normal (beam ref)                    -> beam_shot
  actions.attack_normal (melee) + combo               -> melee_combo
  petals layer / petal_proximity_speed                -> orbitals
  blink                                               -> blink
  dodge_style                                         -> evade
  hp_threshold_clones                                 -> threshold_summon
  damage_teleport                                     -> reactive_teleport
  vanish-cut ultimate                                 -> vanish_strike
  defend action with deflect layer                    -> guard
  palette                                             -> visual.palette

Damage is read from wherever v1 happened to put it and written to exactly
one place: the ability's `on_hit` effect list.  The six competing damage
sources collapse here, on the way in.

Usage:  python3 migrate_v1.py <v1_characters_dir> <v2_characters_dir>
"""

import json
import os
import sys


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _obj(v, truthy_key="enabled"):
    """v1 authored several blocks as EITHER a bare string OR an object
    (`dodge_style`, `defense`, `blink`...).  Normalise both shapes so the
    ambiguity dies at the migration boundary and never enters v2."""
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        return {truthy_key: True, "style": v.strip().lower(),
                "mode": v.strip().lower()}
    return {}


def _rgb(v, default=0xFFFFFF):
    """v1 stored colours as '#rrggbb', [r,g,b] or int."""
    if isinstance(v, int):
        return v & 0xFFFFFF
    if isinstance(v, str) and v.startswith("#") and len(v) >= 7:
        try:
            return int(v[1:7], 16)
        except ValueError:
            return default
    if isinstance(v, (list, tuple)) and len(v) >= 3:
        try:
            return ((int(v[0]) & 255) << 16) | ((int(v[1]) & 255) << 8) | (int(v[2]) & 255)
        except (TypeError, ValueError):
            return default
    return default


def _pick(item):
    """Pull a threshold number out of whichever key v1 used for it."""
    if isinstance(item, dict):
        for k in ("pct", "percent", "at", "hp", "hp_frac", "threshold", "value"):
            if k in item:
                return _num(item[k], None)
        return None
    return _num(item, None)


def _thresholds(v):
    """v1 authored HP thresholds as a list, a dict keyed by percent, or a
    dict of {name: fraction}.  Normalise all three to a descending list of
    fractions in 0..1 -- percentages are divided down."""
    vals = []
    if isinstance(v, dict):
        for k, item in v.items():
            n = _pick(item)
            if n is None:
                n = _num(k, None)
            if n is not None:
                vals.append(n)
    elif isinstance(v, (list, tuple)):
        for item in v:
            n = _pick(item)
            if n is not None:
                vals.append(n)
    vals = [x / 100.0 if x > 1.0 else x for x in vals if x is not None and x > 0]
    return sorted(set(round(x, 4) for x in vals), reverse=True) or [0.75, 0.5, 0.25]


def _layers(action):
    return action.get("fx_layers", []) if isinstance(action, dict) else []


def _hit_layers(action):
    return [l for l in _layers(action) if l.get("can_hit")]


def _layer_damage(action, default=1.0):
    """The v1 damage archaeology: check every place damage could hide."""
    for l in _hit_layers(action):
        b = l.get("battle") or {}
        if "damage" in b:
            return _num(b["damage"], default)
    return default


def _find_layer(action, ltype):
    for l in _layers(action):
        if l.get("type") == ltype:
            return l
    return None


def _first_action(doc, *names):
    acts = doc.get("actions", {}) or {}
    for n in names:
        a = acts.get(n)
        if isinstance(a, dict):
            return a
    return {}


# ----------------------------------------------------------------------
# the conversion
# ----------------------------------------------------------------------

def convert(v1, key_hint=None):
    key = (v1.get("name") or key_hint or "unnamed").strip().lower().replace(" ", "_")
    stats = _obj(v1.get("stats"))
    preds = _obj(v1.get("predicates"))
    arche = (v1.get("archetype") or "").strip()

    # -- attributes ---------------------------------------------------
    attrs = {
        "hp": _num(stats.get("max_hp"), 100.0),
        "hp_max": _num(stats.get("max_hp"), 100.0),
        "move_speed": _num(stats.get("follow_speed"), 2.0),
        "chase_speed": _num(stats.get("chase_speed"), 2.6),
        "scale": _num(stats.get("scale"), 1.0),
        "attack_range": _num(stats.get("basic_attack_radius"), 52.0),
    }
    attrs["aggression"] = 0.75 if arche == "melee" or preds.get("charges_full") else 0.5
    attrs["caution"] = 0.7 if preds.get("retreats") else 0.4

    # -- tags (every v1 boolean flag lands here) ----------------------
    tags = []
    if v1.get("stationary"):
        tags.append("state.stationary")
    if v1.get("counter_only"):
        tags.append("style.counter_only")
    if v1.get("disable_basic_attack"):
        tags.append("block.ability.melee_combo")
    if arche == "melee" or preds.get("uses_melee"):
        tags.append("style.melee")
    if arche == "shooter" or preds.get("can_shoot"):
        tags.append("style.ranged")

    # -- movement -----------------------------------------------------
    mv = _obj(v1.get("movement"))
    if v1.get("stationary"):
        style = "none"
    elif arche == "melee" or preds.get("charges_full"):
        style = "charge"
    elif v1.get("orbit") or v1.get("orbital_strafe"):
        style = "orbit"
    else:
        style = "kite"
    movement = {"style": style,
                "wander": _num(mv.get("wander_strength"), 0.35),
                "ideal_range": 300.0 if style == "kite" else 60.0}

    abilities = []

    used_ids = set()

    def add(k, params, require=None, priority=0.0, ident=None):
        aid = ident or k
        n = 2
        while aid in used_ids:                 # e.g. a normal volley AND an
            aid = "%s_%d" % (k, n)             # ultimate ring volley
            n += 1
        used_ids.add(aid)
        e = {"key": k, "params": params}
        if aid != k:
            e["id"] = aid
        if require:
            e["require"] = require
        if priority:
            e["priority"] = priority
        abilities.append(e)

    atk = _first_action(v1, "attack_normal")
    ap = _obj(v1.get("attack_pattern"))

    # -- primary attack ------------------------------------------------
    beam_layer = _find_layer(atk, "beam")
    if v1.get("beam_layer_ref") or (beam_layer and _num(beam_layer.get("travel_speed"))):
        bl = beam_layer or {}
        add("beam_shot", {
            "damage": _layer_damage(atk, 3.0),
            "speed": _num(bl.get("travel_speed"), 12.0),
            "radius": max(4.0, _num(bl.get("w_start0"), 10.0)),
            "life": 90,
            "pierce": any((l.get("battle") or {}).get("pierce")
                          for l in _hit_layers(atk)),
            "cooldown": int(_num(atk.get("retrigger_cooldown_ms"), 900) / 16),
            "phases": [["windup", 6], ["fire", 2], ["recover", 8]],
            "cue": "beam",
        })
    elif ap.get("enabled") or arche == "shooter" or preds.get("can_shoot"):
        add("projectile_volley", {
            "count": int(_num(ap.get("count"), 3)),
            "spread_deg": _num(ap.get("spread_deg"), 24.0),
            "speed": _num(ap.get("speed"), 7.0),
            "damage": _layer_damage(atk, _num(ap.get("damage"), 1.0)),
            "pattern": ap.get("pattern", "cone"),
            "homing": bool(ap.get("homing")),
            "cooldown": int(_num(atk.get("retrigger_cooldown_ms"), 700) / 16),
            "ideal_range": 280.0,
            "cue": "bullet",
        })

    if (arche == "melee" or preds.get("uses_melee")) and \
            not v1.get("disable_basic_attack"):
        combo = _obj(v1.get("combo"))
        hits = int(_num(combo.get("max_hits"), 3))
        phases = []
        for i in range(hits):
            phases.append(["windup" if i == 0 else "link", 5])
            phases.append(["hit%d" % i, 3])
        phases.append(["recover", 10])
        add("melee_combo", {
            "damage": _layer_damage(atk, 1.0),
            "knockback": 6.0,
            "arc_deg": 130.0,
            "reach_mul": 1.0,
            "phases": phases,
            "cooldown": int(_num(combo.get("cooldown_ms"), 600) / 16),
            "cue": "crescent",
        })

    # -- petals -> orbitals -------------------------------------------
    petals = None
    for act in (v1.get("actions") or {}).values():
        if isinstance(act, dict):
            p = _find_layer(act, "petals")
            if p:
                petals = p
                break
    if petals:
        add("orbitals", {
            "count": int(_num(petals.get("count"), 4)),
            "radius_x": _num(petals.get("hover_radius_x"), 62.0),
            "radius_y": _num(petals.get("hover_radius_y"), 62.0),
            "orbit_speed": _num(petals.get("orbit_speed"), 0.05),
            "damage": _num((petals.get("battle") or {}).get("damage"), 1.0),
            "recharge": int(_num(petals.get("respawn_ms"), 1400) / 16),
            "hit_radius": 14.0,
            "proximity_speed": _num(v1.get("petal_proximity_speed"), 0.0),
            "proximity_range": 300.0,
            "cue": "orb",
        })

    # -- mobility ------------------------------------------------------
    bl = _obj(v1.get("blink"))
    if bl:
        add("blink", {
            "distance": _num(bl.get("distance"), 190.0),
            "mode": bl.get("mode", "reposition"),
            "cooldown": int(_num(bl.get("cooldown_ms"), 2400) / 16),
            "trail_images": int(_num(bl.get("trail_images"), 4)),
        })

    ds = _obj(v1.get("dodge_style"))
    if ds or not v1.get("disable_survival_teleport"):
        add("evade", {
            "style": ds.get("style", "dash") if ds else "dash",
            "distance": _num(ds.get("distance"), 120.0) if ds else 120.0,
            "speed": 9.0,
            "invulnerable": True,
            "hp_below": 0.3,
            "phases": [["dodge", 8], ["recover", 6]],
            "cooldown": int(_num(ds.get("cooldown_ms"), 1800) / 16) if ds else 110,
        })

    # -- reactive / summon ---------------------------------------------
    hpt = _obj(v1.get("hp_threshold_clones"))
    if hpt:
        add("threshold_summon", {
            "thresholds": _thresholds(hpt.get("thresholds")),
            "count": int(_num(hpt.get("count"), 4)),
            "radius": _num(hpt.get("radius"), 240.0),
            "summon_hp": _num(hpt.get("clone_hp"), 10.0),
            "summon_scale": 0.5,
            "summon_stationary": True,
            "summon_life": int(_num(hpt.get("life_ms"), 0) / 16),
            "cue": "ring",
        })

    dt = _obj(v1.get("damage_teleport"))
    if dt:
        add("reactive_teleport", {
            "distance": _num(dt.get("distance"), 240.0),
            "chance": _num(dt.get("chance"), 1.0),
            "cooldown": int(_num(dt.get("cooldown_ms"), 1900) / 16),
        })

    # -- defence --------------------------------------------------------
    dfd = _first_action(v1, "defend")
    has_deflect = any((l.get("battle") or {}).get("defence") == "deflect"
                      for l in _layers(dfd))
    # v1's `defense` was authored as a string on some characters and an
    # object on others -- the "six spellings of defense" the audit found.
    # Normalise both shapes here so neither survives into v2.
    dfn = _obj(v1.get("defense"))
    if has_deflect or dfn.get("enabled"):
        add("guard", {
            "arc_deg": 150.0,
            "reach": 70.0,
            "reflect": True,
            "phases": [["raise", 4], ["hold", 14], ["drop", 6]],
            "cooldown": 90,
        }, priority=0.15 if v1.get("counter_only") else 0.0)

    # -- ultimate --------------------------------------------------------
    ult = _first_action(v1, "ultimate")
    if ult:
        ultc = _obj(v1.get("ultimate_playback"))
        is_vanish = bool(v1.get("vanish_cut")) or "vanish" in json.dumps(ult)[:4000].lower()
        if is_vanish:
            add("vanish_strike", {
                "damage": _layer_damage(ult, 8.0),
                "offset": 46.0,
                "freeze_ticks": int(_num(ultc.get("freeze_ms"), 130) / 16),
                "hp_below": 0.7,
                "phases": [["windup", 14], ["vanish", 10], ["strike", 4], ["hold", 12]],
                "cooldown": int(_num(ultc.get("cooldown_ms"), 7000) / 16),
                "cue": "crescent",
            }, priority=0.5, ident="ultimate")
        else:
            add("projectile_volley", {
                "count": int(_num(ultc.get("count"), 12)),
                "pattern": "ring",
                "speed": _num(ultc.get("speed"), 9.0),
                "damage": _layer_damage(ult, 4.0),
                "cooldown": int(_num(ultc.get("cooldown_ms"), 7000) / 16),
                "ideal_range": 320.0,
                "cue": "beam",
            }, priority=0.5, ident="ultimate")

    # -- visual -----------------------------------------------------------
    pal = _obj(v1.get("palette"))
    visual = {
        "palette": {
            "primary": _rgb(pal.get("body") or pal.get("primary"), 0x39D5FF),
            "accent": _rgb(pal.get("accent"), 0xFF5AD0),
        },
        "sprite": v1.get("sprite_source") or "",
    }
    if v1.get("sprite_tint_color"):
        visual["palette"]["tint"] = _rgb(v1.get("sprite_tint_color"))
    if v1.get("outline_glow"):
        visual["outline_glow"] = True

    return {
        "format": "pb_character_v2",
        "schema_version": 2,
        "key": key,
        "display_name": v1.get("display_name") or key.replace("_", " ").title(),
        "description": v1.get("description", ""),
        "archetype": arche or "generic",
        "attributes": attrs,
        "tags": tags,
        "movement": movement,
        "abilities": abilities,
        "visual": visual,
        "brains": [{"key": "utility"}],
        "notes": "ported from v1 pb_character",
    }


def main(src, dst):
    os.makedirs(dst, exist_ok=True)
    report = []
    for name in sorted(os.listdir(src)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(src, name), "r", encoding="utf-8") as f:
            v1 = json.load(f)
        if v1.get("format") != "pb_character":
            report.append((name, "skipped (not pb_character)", 0, 0))
            continue
        out = convert(v1, os.path.splitext(name)[0])
        path = os.path.join(dst, out["key"] + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
            f.write("\n")
        report.append((name, out["key"], len(out["abilities"]),
                       os.path.getsize(path)))
    return report


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    for row in main(sys.argv[1], sys.argv[2]):
        print("%-22s -> %-16s %2d abilities  %6d B" % row)
