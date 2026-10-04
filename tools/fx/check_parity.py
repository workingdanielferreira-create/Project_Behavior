"""Check that FX Studio and the game agree on every shared table.

    python tools/fx/check_parity.py            (from the game folder)

FX Studio's runtime (tools/fx/studio/fxkit.js) is the reference the game's
laser/fxkit.py, laser/actions.py and laser/retreat.py mirror by hand.  When
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
PY = {name: os.path.join(ROOT, "laser", name + ".py") for name in ("fxkit", "actions", "retreat", "config")}


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
             "ENTRY_DEFAULTS", "PATH_DEFAULTS", "BLINK_DEFAULTS", "BLINK_ANCHORS", "BLINK_DIRECTIONS",
             "TIME_DEFAULTS", "TIME_SCOPES", "TIME_SPEED_MAX", "TIME_MAX_MS",
             "EASES", "KEY_GROUPS", "KEY_CHOICES", "CYCLE_DEFAULTS", "CYCLE_MAX_RUNS", "LAUNCH_LIFE", "DEFLECT_FAN_DEG", "CLASH_KB_MARGIN", "PULSE_MIN_STRETCH", "TICK_MS",
             ("SCALE_PARAMS", "_SCALE_PARAMS"), ("SCALE_MOTION", "_SCALE_MOTION"), ("SCALE_INTERCEPT", "_SCALE_INTERCEPT")]
    for p in pairs:
        j, y = p if isinstance(p, tuple) else (p, p)
        diff(js.get(j), fx.get(y), "fxkit " + j, out)

    # Conditions (laser/actions.py) and Tactical retreat defaults (laser/retreat.py).
    diff(js.get("CONDITION_TYPES"), act.get("CONDITION_TYPES"), "CONDITION_TYPES", out)
    diff(js.get("RETREAT_DEFAULTS"), rt.get("DEFAULTS"), "RETREAT_DEFAULTS", out)

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


if __name__ == "__main__":
    sys.exit(main())
