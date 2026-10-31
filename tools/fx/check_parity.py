"""Check that FX Studio and the game agree on every shared table.

    python tools/fx/check_parity.py            (from the game folder)

FX Studio's runtime (tools/fx/studio/fxkit.js) is the reference the game's
laser/fxkit.py, laser/actions.py and laser/retreat.py mirror by hand (and
tools/fx/studio/movestyle.js mirrors laser/movestyle.py).  When
one side gains a default, a condition type or a scaled parameter and the
other does not, an effect previews one way in the Studio and plays another
way in Solo and Battle.  This script compares the tables both sides keep and
lists every difference.  Exit code 0 = in step, 1 = differences found.

Standard library only: the JavaScript tables are read with a small literal
reader and the Python ones with ast (laser/fxkit.py imports PyQt5, so it is
never imported here).
"""
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FXKIT_JS = os.path.join(ROOT, "tools", "fx", "studio", "fxkit.js")
STUDIO_JS = os.path.join(ROOT, "tools", "fx", "studio", "studio.js")
PY = {name: os.path.join(ROOT, "laser", name + ".py") for name in ("fxkit", "actions", "retreat", "dodge", "config", "clash")}


# ---------------------------------------------------------------- JavaScript
_TOKEN = re.compile(r"""\s*(?:
    (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<num>-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)
  | (?P<id>[A-Za-z_$][\w$]*)
  | (?P<p>[{}\[\]:,])
)""", re.X)


def _strip_comments(src):
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1]); i = j + 1
        elif src.startswith("//", i):
            j = src.find("\n", i); i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2); i = n if j < 0 else j + 2
        else:
            out.append(c); i += 1
    return "".join(out)


class JsTables:
    """`var NAME = <literal>;` tables from a JavaScript file."""

    def __init__(self, path):
        self.src = _strip_comments(open(path, encoding="utf-8").read())
        self.cache = {}

    def get(self, name):
        if name not in self.cache:
            m = re.search(r"(?:var|,)\s*" + re.escape(name) + r"\s*=\s*", self.src)
            if not m:
                raise KeyError(name)
            self.cache[name] = self._parse(m.end())[0]
        return self.cache[name]

    def _parse(self, pos):
        m = _TOKEN.match(self.src, pos)
        if not m:
            raise ValueError("cannot read JavaScript at: " + self.src[pos:pos + 40])
        pos = m.end()
        if m.group("str"):
            return ast.literal_eval(m.group("str")), pos
        if m.group("num"):
            return float(m.group("num")), pos
        if m.group("id"):
            w = m.group("id")
            if w in ("true", "false", "null"):
                return {"true": True, "false": False, "null": None}[w], pos
            nxt = _TOKEN.match(self.src, pos)
            if nxt and nxt.group("p") in (",", "}", "]") or self.src[pos:].lstrip().startswith(";"):
                return self.get(w), pos          # a reference to another table
            raise ValueError("not a plain literal near: " + self.src[m.start():m.start() + 60])
        p = m.group("p")
        if p == "[":
            out = []
            while True:
                t = _TOKEN.match(self.src, pos)
                if t.group("p") == "]":
                    return out, t.end()
                v, pos = self._parse(pos); out.append(v)
                t = _TOKEN.match(self.src, pos)
                pos = t.end()
                if t.group("p") == "]":
                    return out, pos
        if p == "{":
            out = {}
            while True:
                t = _TOKEN.match(self.src, pos)
                if t.group("p") == "}":
                    return out, t.end()
                key = ast.literal_eval(t.group("str")) if t.group("str") else t.group("id") or t.group("num")
                colon = _TOKEN.match(self.src, t.end())
                v, pos = self._parse(colon.end()); out[key] = v
                t = _TOKEN.match(self.src, pos)
                pos = t.end()
                if t.group("p") == "}":
                    return out, pos
        raise ValueError("unexpected " + p)


# ---------------------------------------------------------------- Python
class PyTables:
    """Module-level `NAME = <literal or dict(...)>` tables, read with ast."""

    def __init__(self, path, others=None):
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        self.nodes = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                self.nodes[node.targets[0].id] = node.value
        self.others = others or {}

    def get(self, name):
        return self._eval(self.nodes[name])

    def _eval(self, n):
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, (ast.List, ast.Tuple)):
            return [self._eval(e) for e in n.elts]
        if isinstance(n, ast.Set):
            return sorted(self._eval(e) for e in n.elts)
        if isinstance(n, ast.Dict):
            return {self._eval(k): self._eval(v) for k, v in zip(n.keys, n.values)}
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "dict" and not n.args:
            return {k.arg: self._eval(k.value) for k in n.keywords}
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -self._eval(n.operand)
        if isinstance(n, ast.Name) and n.id in self.nodes:
            return self.get(n.id)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in self.others:
            return self.others[n.value.id].get(n.attr)
        raise ValueError("not a plain literal: " + ast.dump(n)[:80])


# ---------------------------------------------------------------- compare
def _norm(v):
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items()}
    return v


def diff(a, b, path, out):
    a, b = _norm(a), _norm(b)
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in b:
                out.append("%s.%s: only in the Studio (%r)" % (path, k, a[k]))
            elif k not in a:
                out.append("%s.%s: only in the game (%r)" % (path, k, b[k]))
            else:
                diff(a[k], b[k], path + "." + str(k), out)
    elif a != b:
        out.append("%s: Studio %r, game %r" % (path, a, b))


def same_keys(a, b, path, out, a_name, b_name):
    for k in sorted(set(a) - set(b)):
        out.append("%s: %r is in %s but not in %s" % (path, k, a_name, b_name))
    for k in sorted(set(b) - set(a)):
        out.append("%s: %r is in %s but not in %s" % (path, k, b_name, a_name))


def main():
    # A Windows console or a redirected log may not use UTF-8: escape what it
    # can't show instead of failing halfway through the report.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    js = JsTables(FXKIT_JS)
    studio = JsTables(STUDIO_JS)
    cfg = PyTables(PY["config"])
    fx = PyTables(PY["fxkit"], {"config": cfg})
    act = PyTables(PY["actions"], {"config": cfg})
    rt = PyTables(PY["retreat"], {"config": cfg})
    out = []

    # fxkit.js <-> laser/fxkit.py: same name on both sides unless mapped here.
    pairs = ["PRIMS", "PARAM_DEFAULTS", "MOTION_DEFAULTS", "COLOR_DEFAULTS", "BATTLE_DEFAULTS",
             "INTERCEPT_DEFAULTS", "FLIP_DEFAULTS", "ACTION_DEFAULTS", "AIM_DEFAULTS", "DAMAGED_DEFAULTS",
             "ENTRY_DEFAULTS", "PATH_DEFAULTS", "BLINK_DEFAULTS", "BLINK_STEP_DEFAULTS", "BLINK_ANCHORS", "BLINK_DIRECTIONS",
             "TIME_DEFAULTS", "TIME_SCOPES", "TIME_SPEED_MAX",
             "EASES", "KEY_GROUPS", "KEY_CHOICES", "CYCLE_DEFAULTS", "CYCLE_MAX_RUNS", "LAUNCH_LIFE", "DEFLECT_FAN_DEG", "PULSE_MIN_STRETCH", "TICK_MS",
             "INTERCEPT_MODES",
             "TECH_STYLES", "TECH_STYLE_DEFAULTS",
             ("SCALE_PARAMS", "_SCALE_PARAMS"), ("SCALE_MOTION", "_SCALE_MOTION"), ("SCALE_INTERCEPT", "_SCALE_INTERCEPT")]
    for p in pairs:
        j, y = p if isinstance(p, tuple) else (p, p)
        diff(js.get(j), fx.get(y), "fxkit " + j, out)

    # The world clash table (laser/clash.py) and the clash explosions the
    # World Clash page offers.
    cl = PyTables(PY["clash"], {"config": cfg})
    diff(js.get("CLASH_SLOTS"), [list(r) for r in cl.get("WORLD_SLOTS")], "clash WORLD_SLOTS", out)
    diff(js.get("MIN_TICKS"), cl.get("MIN_TICKS"), "clash MIN_TICKS", out)
    diff(js.get("WORLD_CLASH_FORMAT"), cl.get("WORLD_FORMAT"), "clash WORLD_FORMAT", out)
    same_keys({r[0] for r in js.get("CLASH_FX")}, _clashfx_keys(), "CLASH_FX", out,
              "FX Studio's clash FX list", "laser/clashfx.py BASES")

    # World physics: Dust & Air (laser/worldfx.py, studio/worldfx.js): its
    # settings tables and the position grids the preview copies.
    wf_js = JsTables(os.path.join(ROOT, "tools", "fx", "studio", "worldfx.js"))
    wf_py = PyTables(os.path.join(ROOT, "laser", "worldfx.py"), {"config": cfg})
    for j, y in (("WP_DEFAULTS", "DEFAULTS"), ("WP_RANGES", "RANGES"), ("WP_FORMAT", "FORMAT"),
                 ("WP_SECTIONS", "SECTIONS")):
        diff(wf_js.get(j), wf_py.get(y), "worldfx " + y, out)
    diff(wf_js.get("PS"), [cfg.get("POSITION_SCALE_" + k) for k in ("TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT")],
         "worldfx PS (config.POSITION_SCALE_*)", out)
    diff(wf_js.get("SS"), [cfg.get("SPEED_SCALE_" + k) for k in ("TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT")],
         "worldfx SS (config.SPEED_SCALE_*)", out)
    diff(wf_js.get("TELEPORT_PX"), cfg.get("ARENA_OVAL_TELEPORT_PX"), "worldfx TELEPORT_PX", out)

    # Hand-drawn techniques: the slash-family cut table (laser/swordfx.py),
    # the ki barrage / impact punch constants (laser/strikefx.py), the power
    # techniques (laser/powerfx.py), the guns (laser/gunfx.py) and the
    # weapons (laser/weaponfx.py).
    sw_js = JsTables(os.path.join(ROOT, "tools", "fx", "studio", "swordfx.js"))
    sw_py = PyTables(os.path.join(ROOT, "laser", "swordfx.py"))
    for name in ("CUTS", "CROSS_LIFE", "SLASH_SLICES", "SPARK_LIFE", "HIT_MARK_LIFE"):
        diff(sw_js.get(name), sw_py.get(name), "swordfx " + name, out)
    st_js = JsTables(os.path.join(ROOT, "tools", "fx", "studio", "strikefx.js"))
    st_py = PyTables(os.path.join(ROOT, "laser", "strikefx.py"))
    for name in ("STYLES", "KI_SPEED", "KI_RANGE", "KI_SIDE", "KI_FLASH", "KI_BLAST_LIFE", "KI_SMOKE_LIFE", "SMOKE",
                 "PUNCH_RETRACT", "PUNCH_IMPACT_LIFE"):
        diff(st_js.get(name), st_py.get(name), "strikefx " + name, out)
    # ... the kicks' constants (laser/kickfx.py).
    kk_js = JsTables(os.path.join(ROOT, "tools", "fx", "studio", "kickfx.js"))
    kk_py = PyTables(os.path.join(ROOT, "laser", "kickfx.py"))
    for name in ("STYLES", "ARC_STYLES", "WIND", "RETRACT", "RISE_REACH", "CONTACT", "HEAVY"):
        diff(kk_js.get(name), kk_py.get(name), "kickfx " + name, out)
    # ... the strike FX partitions the punch and kicks paint (laser/hitfx.py).
    hf_js = JsTables(os.path.join(ROOT, "tools", "fx", "studio", "hitfx.js"))
    hf_py = PyTables(os.path.join(ROOT, "laser", "hitfx.py"))
    for name in ("LOOKS", "PARTS", "IMPACT_LIFE", "ENV_LIFE", "CRATER_LIFE", "FEET_DROP", "SMEAR_N", "SMEAR_STEP",
                 "SMEAR_LEN", "ARC_N", "ARC_LINGER", "INK", "PAPER", "DUST", "GREY", "ROCK", "SCORCH"):
        diff(hf_js.get(name), hf_py.get(name), "hitfx " + name, out)
    diff(kk_js.get("FEET_DROP"), hf_py.get("FEET_DROP"), "kickfx FEET_DROP / hitfx FEET_DROP", out)
    diff(st_js.get("PUNCH_IMPACT_LIFE"), hf_py.get("IMPACT_LIFE"), "strikefx PUNCH_IMPACT_LIFE / hitfx IMPACT_LIFE", out)
    # ... and the power techniques' constants (laser/powerfx.py).
    pw_js = JsTables(os.path.join(ROOT, "tools", "fx", "studio", "powerfx.js"))
    pw_py = PyTables(os.path.join(ROOT, "laser", "powerfx.py"))
    for name in ("STYLES", "PULL_STYLES", "AURA_FADE", "AURA_N", "AURA_LICK_LIFE", "AURA_RATE", "AURA_RISE", "AURA_LAG",
                 "AURA_STRETCH", "AURA_FULL", "AURA_SWING", "AURA_SWING_N", "AURA_DRIFT", "AURA_FRAG_LIFE", "AURA_FRAG_P", "AURA_SURGE_SLOT", "AURA_SURGE_LEN", "AURA_CRACKS", "AURA_ROCK_EVERY", "AURA_ROCK_LIFE",
                 "ROCK", "CRACK", "AURA_SLOT", "AURA_BOLT_LIFE", "AURA_BOLT_FLICKER", "BOLT",
                 "RS_SPEED", "RS_SPIN", "RS_GROW", "RS_SHRINK", "RS_FADE", "MET_FALL", "MET_LOB", "MET_GROW_DRAG",
                 "MET_BLAST_HIT", "MET_BLAST_LIFE", "DUST", "GH_FLOAT", "GH_OUT", "GH_DRAG", "GH_SPEED", "GH_ACCEL", "GH_TURN",
                 "GH_FAN", "GH_ARRIVE", "GH_BLAST_LIFE", "GH_BODY", "SMOKE", "SP_OUT", "SP_FLASH", "SP_RINGS", "SP_SPLIT_LIFE",
                 "CLOUD", "BH_COLLAPSE", "BH_BURST_HIT", "BH_BURST_LIFE", "BH_TILT", "BH_SQ", "BH_CLUMPS"):
        diff(pw_js.get(name), pw_py.get(name), "powerfx " + name, out)
    # ... and the guns' constants (laser/gunfx.py).
    gn_js = JsTables(os.path.join(ROOT, "tools", "fx", "studio", "gunfx.js"))
    gn_py = PyTables(os.path.join(ROOT, "laser", "gunfx.py"))
    for name in ("STYLES", "GUNS", "IMPACT_LIFE", "EXPLODES", "TRACER_TAIL", "FADE_TAIL", "CASING_LIFE", "CASING_G",
                 "SMOKE_LIFE", "GAT_GAP", "GAT_RAMP", "GAT_BARREL", "GAT_SPIN", "GAT_SPIN_DOWN", "RAIL_HIT", "RAIL_DELAY",
                 "CHARGE_P", "CHARGE_RING", "ROCKET_ARC", "ROCKET_EASE", "ROCKET_MIN", "ROCKET_PUFF", "DRILL_SPIN",
                 "DRILL_RING", "BOLT_SEG", "BRASS", "HULL", "SMOKE", "STEEL"):
        diff(gn_js.get(name), gn_py.get(name), "gunfx " + name, out)
    # ... and the weapons' tables (laser/weaponfx.py): models, sequences, timings.
    wp_js = JsTables(os.path.join(ROOT, "tools", "fx", "studio", "weaponfx.js"))
    wp_py = PyTables(os.path.join(ROOT, "laser", "weaponfx.py"))
    for name in ("STYLES", "HU", "SUMMON", "DISMISS", "FOCAL", "THICK_K", "TRAIL_N", "TRAIL_SUB", "TRAIL_BAND", "EVT_HIT",
                 "BEAM_T", "RAIL_T", "LINE_T", "LINE_HW", "IMPLODE_IN", "VOID", "IMPACT_LIFE", "TAIL", "EVT_LIFE", "EVT_R", "SHOTS", "GLOWS", "MODELS", "WEAPONS"):
        diff(wp_js.get(name), wp_py.get(name), "weaponfx " + name, out)
    for st in wp_py.get("STYLES"):
        if st not in fx.get("TECH_STYLES"):
            out.append("weaponfx %s: not in laser/fxkit.py TECH_STYLES" % st)
    tech_ui = [r for r in studio.get("PARAM_UI")["technique"] if r[0] == "style"][0][2]
    diff(tech_ui, fx.get("TECH_STYLES"), "studio technique style list", out)

    # Conditions (laser/actions.py) and Tactical retreat defaults (laser/retreat.py).
    diff(js.get("CONDITION_TYPES"), act.get("CONDITION_TYPES"), "CONDITION_TYPES", out)
    diff(js.get("RETREAT_DEFAULTS"), rt.get("DEFAULTS"), "RETREAT_DEFAULTS", out)
    # Dodge (laser/dodge.py).
    dg = PyTables(PY["dodge"], {"config": cfg})
    diff(js.get("DODGE_DEFAULTS"), dg.get("DEFAULTS"), "DODGE_DEFAULTS", out)
    for name in ("STYLES", "SIDES", "REACT_TO"):
        diff(js.get("DODGE_" + name), list(dg.get(name)), "DODGE_" + name, out)
    # Unique Abilities (laser/unique.py).
    ua = PyTables(os.path.join(ROOT, "laser", "unique.py"), {"config": cfg})
    diff(js.get("UNIQUE_TYPES"), list(ua.get("TYPES")), "UNIQUE_TYPES", out)
    diff(js.get("UNIQUE_DEFAULTS"), ua.get("DEFAULTS"), "UNIQUE_DEFAULTS", out)
    # Summoner summons (laser/unique.py SUMMON_*, run by laser/summoner.py).
    diff(js.get("SUMMON_CONSTRUCTS"), list(ua.get("SUMMON_CONSTRUCTS")), "SUMMON_CONSTRUCTS", out)
    diff(js.get("SUMMON_DEFAULTS"), ua.get("SUMMON_DEFAULTS"), "SUMMON_DEFAULTS", out)
    diff(js.get("SUMMON_LIMITS"), {k: list(v) for k, v in ua.get("SUMMON_LIMITS").items()}, "SUMMON_LIMITS", out)
    diff(js.get("SUMMON_MAX"), ua.get("SUMMON_MAX"), "SUMMON_MAX", out)
    diff(js.get("SUMMON_MOVE_TARGETS"), list(ua.get("SUMMON_MOVE_TARGETS")), "SUMMON_MOVE_TARGETS", out)

    # Movement style (laser/movestyle.py <-> tools/fx/studio/movestyle.js).
    mv_js = JsTables(os.path.join(ROOT, "tools", "fx", "studio", "movestyle.js"))
    mv_py = PyTables(os.path.join(ROOT, "laser", "movestyle.py"), {"config": cfg})
    for name in ("PATTERNS", "SELECTS", "FACES", "ATTACKING", "ENEMIES", "ENUMS", "SIGNED", "PATTERN_DEFAULTS",
                 "MODIFIER_DEFAULTS", "WHEN_DEFAULTS", "PHASE_DEFAULTS", "DEFAULTS",
                 "ATTACK_LINGER_MS", "SWAP_DEFAULT_HOLD_MS", "HEADING_MIN_SPEED"):
        diff(mv_js.get(name), mv_py.get(name), "movestyle " + name, out)
    for name, py_name in (("TICK_MS", "TICK_MS"), ("WALL_ZONE", "WALL_ZONE"), ("WALL_PUSH", "WALL_PUSH")):
        diff(mv_js.get(name), cfg.get(py_name), "movestyle " + name + " (config)", out)

    # Constants the Studio's previews copy from the game.
    diff(js.get("STAND_HEIGHT_PX"), cfg.get("IMAGE_STAND_HEIGHT_PX"), "STAND_HEIGHT_PX", out)
    diff(studio.get("TARGET_HEAD_PX"), cfg.get("TARGET_HEAD_PX"), "studio TARGET_HEAD_PX", out)
    for name in ("ARRIVE_PX", "BACK_STANDOFF_PX", "STEER_WEIGHT"):
        diff(studio.get(name), rt.get(name), "studio " + name + " (retreat preview)", out)

    # Inside the Studio: every primitive parameter has a panel row and every
    # condition type has its label, help and field list.
    ui = studio.get("PARAM_UI")
    defaults = js.get("PARAM_DEFAULTS")
    for prim in js.get("PRIMS"):
        same_keys({r[0] for r in ui.get(prim, [])}, set(defaults.get(prim, {})), "PARAM_UI " + prim, out,
                  "the Studio panel", "PARAM_DEFAULTS")
    conds = set(js.get("CONDITION_TYPES"))
    meta = studio.get("COND_META")
    same_keys(set(meta), conds, "COND_META", out, "the Studio condition list", "CONDITION_TYPES")
    for t, m in sorted(meta.items()):
        for k in ("group", "label", "help"):
            if not m.get(k):
                out.append("COND_META.%s: no %s" % (t, k))

    if out:
        print("FX Studio and the game are out of step (%d):" % len(out))
        for line in out:
            print("  - " + line)
        return 1
    print("FX Studio and the game agree on every shared table.")
    return 0


def _clashfx_keys():
    """The keys of laser/clashfx.py BASES (read with ast: it imports PyQt5)."""
    with open(os.path.join(ROOT, "laser", "clashfx.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "BASES" for t in node.targets):
            return {k.value for k in node.value.keys}
    return set()


if __name__ == "__main__":
    sys.exit(main())
