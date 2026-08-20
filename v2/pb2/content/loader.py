"""Character loading — parse, validate, migrate, resolve.

The pipeline is the standard one: parse -> detect schema_version -> validate
-> migrate one step at a time -> hand a normalised object to the engine.

Validation is LOUD.  v1's dominant failure mode was a character JSON whose
ability silently did nothing because an exception was swallowed; here a bad
file names the exact JSON path and refuses to load.

Dead fields are impossible by construction: if a key is not in the schema,
`strict` mode rejects it rather than ignoring it.  That is what stops
`defense: "block"`, `dual_defense` and `special_ability.preset` from
accumulating again.
"""

import json
import os

from ..core.registry import get_ability, get_cue, RegistryError
from ..core.tags import TagQuery
from ..sim.effects import build_effects

__all__ = ["CharacterDef", "load_character", "load_all", "ValidationError",
           "SCHEMA_VERSION"]

SCHEMA_VERSION = 2

_TOP_LEVEL = {
    "format", "schema_version", "key", "display_name", "description",
    "archetype", "attributes", "tags", "abilities", "visual", "movement",
    "brains", "notes",
}

_ABILITY_KEYS = {"key", "id", "params", "require", "priority", "note"}


class ValidationError(ValueError):
    def __init__(self, path, message):
        super().__init__("%s: %s" % (path, message))
        self.path = path


class CharacterDef:
    """A validated, resolved character ready to instantiate Actors from."""

    __slots__ = ("key", "display_name", "description", "archetype",
                 "attributes", "tags", "abilities", "visual", "movement",
                 "brain_specs", "source_path", "raw")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def default_brains(self):
        """Instantiate this character's brains.  Imported lazily so the
        content layer stays independent of the brain layer."""
        from ..brains.brains import UtilityBrain
        out = []
        for spec in (self.brain_specs or [{"key": "utility"}]):
            if spec.get("key") == "utility":
                out.append(UtilityBrain(
                    movement=self.movement.get("style", "kite"),
                    params=self.movement))
        return out

    def __repr__(self):
        return "<CharacterDef %s '%s' %d abilities>" % (
            self.key, self.display_name, len(self.abilities or ()))


# ======================================================================
# validation
# ======================================================================

def _require(cond, path, msg):
    if not cond:
        raise ValidationError(path, msg)


def validate(doc, path="<doc>", strict=True):
    """Structural validation.  Returns the doc; raises on any problem."""
    _require(isinstance(doc, dict), path, "root must be an object")
    _require(doc.get("format") == "pb_character_v2", path + ".format",
             "expected 'pb_character_v2', got %r" % doc.get("format"))

    ver = doc.get("schema_version", 1)
    _require(isinstance(ver, int), path + ".schema_version", "must be an integer")

    if strict:
        unknown = set(doc) - _TOP_LEVEL
        _require(not unknown, path,
                 "unknown top-level keys: %s (dead fields are rejected, not "
                 "ignored)" % sorted(unknown))

    key = doc.get("key")
    _require(isinstance(key, str) and key and key == key.lower().strip(),
             path + ".key", "must be a lowercase non-empty string")

    attrs = doc.get("attributes", {})
    _require(isinstance(attrs, dict), path + ".attributes", "must be an object")
    for k, v in attrs.items():
        _require(isinstance(v, (int, float)),
                 "%s.attributes.%s" % (path, k), "must be numeric, got %r" % (v,))

    tags = doc.get("tags", [])
    _require(isinstance(tags, list), path + ".tags", "must be a list")

    abilities = doc.get("abilities", [])
    _require(isinstance(abilities, list), path + ".abilities", "must be a list")
    seen = set()
    for i, ab in enumerate(abilities):
        p = "%s.abilities[%d]" % (path, i)
        _require(isinstance(ab, dict), p, "must be an object")
        akey = ab.get("key")
        _require(isinstance(akey, str) and akey, p + ".key", "missing ability key")
        # `id` names the INSTANCE; `key` names the implementation.  A
        # character may carry two projectile_volleys (a quick one and an
        # ultimate) provided each has a distinct id.
        aid = ab.get("id", akey)
        _require(isinstance(aid, str) and aid, p + ".id", "id must be a string")
        _require(aid not in seen, p + ".id",
                 "duplicate ability id %r on one character (give one an "
                 "explicit \"id\")" % aid)
        seen.add(aid)
        if strict:
            unknown = set(ab) - _ABILITY_KEYS
            _require(not unknown, p, "unknown keys: %s" % sorted(unknown))
        try:
            get_ability(akey)
        except RegistryError as e:
            raise ValidationError(p + ".key", str(e))
        params = ab.get("params", {})
        _require(isinstance(params, dict), p + ".params", "must be an object")
        # effect blocks are validated by construction
        for fx_field in ("on_hit", "on_start", "on_end"):
            if fx_field in params:
                try:
                    build_effects(params[fx_field])
                except Exception as e:
                    raise ValidationError("%s.params.%s" % (p, fx_field), str(e))

    _validate_visual(doc.get("visual", {}), path + ".visual", strict)
    return doc


_VISUAL_KEYS = {"palette", "sprite", "sprites", "outline_glow", "rig", "fx"}
_RIG_KEYS = {"bones", "weapon", "scale", "actions"}
_ACTION_KEYS = {"keyframes", "duration_ms", "ease", "loop"}
_EASES = {"linear", "in", "out", "inout", "snap", "overshoot"}
_FX_KEYS = {"afterimage", "trail", "crescent"}


def _validate_visual(vis, path, strict=True):
    """The visual block is cosmetic-only but still validated LOUDLY — a rig
    keyframe typo must name its JSON path, not silently render a T-pose."""
    _require(isinstance(vis, dict), path, "must be an object")
    if strict:
        unknown = set(vis) - _VISUAL_KEYS
        _require(not unknown, path, "unknown keys: %s" % sorted(unknown))
    pal = vis.get("palette", {})
    _require(isinstance(pal, dict), path + ".palette", "must be an object")
    for k, v in pal.items():
        _require(isinstance(v, int) and 0 <= v <= 0xFFFFFF,
                 "%s.palette.%s" % (path, k),
                 "must be an integer 0x000000-0xFFFFFF")

    og = vis.get("outline_glow", False)
    _require(isinstance(og, (bool, dict)), path + ".outline_glow",
             "must be a boolean or an object")

    rig = vis.get("rig")
    if rig is not None:
        p = path + ".rig"
        _require(isinstance(rig, dict), p, "must be an object")
        if strict:
            unknown = set(rig) - _RIG_KEYS
            _require(not unknown, p, "unknown keys: %s" % sorted(unknown))
        bones = rig.get("bones", {})
        _require(isinstance(bones, dict), p + ".bones", "must be an object")
        for k, v in bones.items():
            _require(isinstance(v, (int, float)), "%s.bones.%s" % (p, k),
                     "must be numeric")
        actions = rig.get("actions", {})
        _require(isinstance(actions, dict), p + ".actions", "must be an object")
        for name, act in actions.items():
            ap = "%s.actions.%s" % (p, name)
            _require(isinstance(act, dict), ap, "must be an object")
            if strict:
                unknown = set(act) - _ACTION_KEYS
                _require(not unknown, ap, "unknown keys: %s" % sorted(unknown))
            kfs = act.get("keyframes", [])
            _require(isinstance(kfs, list) and kfs, ap + ".keyframes",
                     "must be a non-empty list")
            for i, kf in enumerate(kfs):
                kp = "%s.keyframes[%d]" % (ap, i)
                _require(isinstance(kf, dict), kp, "must be an object")
                pose = kf.get("p", {})
                _require(isinstance(pose, dict), kp + ".p", "must be an object")
                for pk, pv in pose.items():
                    _require(isinstance(pv, (int, float)),
                             "%s.p.%s" % (kp, pk), "must be numeric")
            ease = act.get("ease", "inout")
            _require(ease in _EASES, ap + ".ease",
                     "must be one of %s" % sorted(_EASES))

    spr = vis.get("sprites")
    if spr is not None:
        p = path + ".sprites"
        _require(isinstance(spr, dict), p, "must be an object")
        sets = spr.get("sets", {})
        _require(isinstance(sets, dict) and sets, p + ".sets",
                 "must be a non-empty object of action -> glob pattern")
        for k, v in sets.items():
            _require(isinstance(v, str) and v, "%s.sets.%s" % (p, k),
                     "must be a glob pattern string")

    fx = vis.get("fx")
    if fx is not None:
        p = path + ".fx"
        _require(isinstance(fx, dict), p, "must be an object")
        if strict:
            unknown = set(fx) - _FX_KEYS
            _require(not unknown, p, "unknown keys: %s" % sorted(unknown))
        for k, v in fx.items():
            _require(isinstance(v, dict), "%s.%s" % (p, k),
                     "must be an object")


# ======================================================================
# migration
# ======================================================================

def migrate(doc, path="<doc>"):
    """Step the document up one schema version at a time."""
    ver = doc.get("schema_version", 1)
    while ver < SCHEMA_VERSION:
        fn = _MIGRATIONS.get(ver)
        if fn is None:
            raise ValidationError(
                path, "no migration from schema_version %d" % ver)
        doc = fn(doc)
        ver = doc.get("schema_version", ver + 1)
    return doc


def _m1_to_2(doc):
    doc = dict(doc)
    doc["schema_version"] = 2
    return doc


_MIGRATIONS = {1: _m1_to_2}


# ======================================================================
# resolution
# ======================================================================

def resolve(doc, source_path=None):
    """Validated doc -> CharacterDef with live implementation classes bound."""
    abilities = []
    for ab in doc.get("abilities", []):
        abilities.append({
            "key": ab.get("id", ab["key"]),
            "impl_key": ab["key"],
            "impl": get_ability(ab["key"]),
            "params": dict(ab.get("params", {})),
            "gate": TagQuery(ab["require"]) if ab.get("require") else None,
            "priority": ab.get("priority", 0.0),
        })
    return CharacterDef(
        key=doc["key"],
        display_name=doc.get("display_name", doc["key"].title()),
        description=doc.get("description", ""),
        archetype=doc.get("archetype", "generic"),
        attributes=dict(doc.get("attributes", {})),
        tags=list(doc.get("tags", [])),
        abilities=abilities,
        visual=dict(doc.get("visual", {})),
        movement=dict(doc.get("movement", {})),
        brain_specs=list(doc.get("brains", [])) or [{"key": "utility"}],
        source_path=source_path,
        raw=doc,
    )


def load_character(path, strict=True):
    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    doc = migrate(doc, path)
    validate(doc, path, strict=strict)
    return resolve(doc, path)


def load_all(folder, strict=True):
    """Load every character in a folder.  Returns (defs, errors).

    One bad file does not stop the others loading, but it is reported —
    never silently skipped.
    """
    defs, errors = {}, []
    if not os.path.isdir(folder):
        return defs, ["not a directory: %s" % folder]
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".json"):
            continue
        p = os.path.join(folder, name)
        try:
            d = load_character(p, strict=strict)
            if d.key in defs:
                errors.append("%s: duplicate character key %r" % (p, d.key))
                continue
            defs[d.key] = d
        except Exception as e:
            errors.append("%s: %s" % (name, e))
    return defs, errors
