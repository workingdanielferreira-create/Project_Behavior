"""Generate schema/character.schema.json FROM the live registry.

Documentation cannot drift from code, because the contract is generated from
the code.  v1's schema drift (fields documented but unread, `ipc.py` rules for
a module that no longer existed) is structurally impossible here.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pb2.sim  # noqa: registers plugins
from pb2.core import registry
from pb2.content.loader import SCHEMA_VERSION, _TOP_LEVEL, _ABILITY_KEYS
from pb2.core.attributes import ATTR_DEFAULTS

def build():
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://project-behavior/v2/character.schema.json",
        "title": "pb_character_v2",
        "description": "A Project Behavior V2 character. Five nouns: "
                       "attributes, tags, abilities, effects, cues.",
        "type": "object",
        "required": ["format", "key"],
        "additionalProperties": False,
        "properties": {
            "format": {"const": "pb_character_v2"},
            "schema_version": {"type": "integer", "const": SCHEMA_VERSION},
            "key": {"type": "string", "pattern": "^[a-z0-9_]+$"},
            "display_name": {"type": "string"},
            "description": {"type": "string"},
            "archetype": {"type": "string"},
            "notes": {"type": "string"},
            "attributes": {
                "type": "object", "additionalProperties": {"type": "number"},
                "propertyNames": {"type": "string"},
                "description": "Numeric state. Engine-read names: %s"
                               % ", ".join(sorted(ATTR_DEFAULTS)),
            },
            "tags": {"type": "array", "items": {"type": "string"},
                     "description": "Hierarchical dotted tags. Replaces all "
                                    "boolean flags."},
            "movement": {"type": "object", "properties": {
                "style": {"enum": ["kite", "charge", "orbit", "retreat", "none"]},
                "wander": {"type": "number", "minimum": 0, "maximum": 1},
                "ideal_range": {"type": "number"},
                "band": {"type": "number"},
                "orbit_lead_deg": {"type": "number"},
                "threshold": {"type": "number"}}},
            "brains": {"type": "array", "items": {"type": "object",
                       "properties": {"key": {"enum": registry.known_brains()}}}},
            "abilities": {
                "type": "array",
                "items": {
                    "type": "object", "required": ["key"],
                    "additionalProperties": False,
                    "properties": {
                        "key": {"enum": registry.known_abilities()},
                        "id": {"type": "string",
                               "description": "instance name; required when a "
                                              "character carries two of the "
                                              "same ability"},
                        "params": {"type": "object"},
                        "require": {"$ref": "#/$defs/tagQuery"},
                        "priority": {"type": "number"},
                        "note": {"type": "string"}}}},
            "visual": {"type": "object", "properties": {
                "palette": {"type": "object",
                            "additionalProperties": {
                                "type": "integer", "minimum": 0,
                                "maximum": 16777215}},
                "sprite": {"type": "string"},
                "outline_glow": {"type": "boolean"}}},
        },
        "$defs": {
            "tagQuery": {"type": "object", "additionalProperties": False,
                         "properties": {
                             "all": {"type": "array", "items": {"type": "string"}},
                             "any": {"type": "array", "items": {"type": "string"}},
                             "none": {"type": "array", "items": {"type": "string"}}}},
            "effect": {"type": "object", "required": ["effect"],
                       "properties": {
                           "effect": {"enum": registry.known_effects()},
                           "chance": {"type": "number"},
                           "require": {"$ref": "#/$defs/tagQuery"}}},
        },
        "x-capabilities": registry.describe(),
    }

if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "schema", "character.schema.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(build(), f, indent=2); f.write("\n")
    print("wrote", out, os.path.getsize(out), "B")
    caps = registry.describe()
    print("abilities %d | effects %d | cues %d" % (
        len(caps["abilities"]), len(caps["effects"]), len(caps["cues"])))
