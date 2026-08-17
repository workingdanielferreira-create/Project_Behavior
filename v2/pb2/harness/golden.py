"""Golden checksum harness — one assertion covering the whole simulation.

v1 had no automated tests at all: validation was `ast.parse` + `py_compile`
(syntax only) plus a manual Windows run.  A 429-line FSM and a 92-branch
collision resolver were verified by eye, which is why the same classes of
bug kept recurring.

Because the v2 sim is deterministic (world-seeded RNG, fixed tick, pure
paint) a run is defined entirely by (seed, scenario, input tape).  Replay it,
hash the world state, compare to a recorded value.  If any behaviour anywhere
in the engine changes, the hash changes.

Storage is a few hundred bytes per scenario, versus v1's 25 MB of committed
capture bundles.

    python3 -m pb2.harness.golden record     # write goldens
    python3 -m pb2.harness.golden verify     # check against them
"""

import json
import os
import sys

from ..content import load_all
from ..sim import World
from ..brains.brains import ScriptBrain, PlayerBrain, Pad

__all__ = ["Scenario", "run_scenario", "record_all", "verify_all", "SCENARIOS"]

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_PATH = os.path.join(HERE, "goldens.json")
CHARS = os.path.join(os.path.dirname(os.path.dirname(HERE)), "characters")


class Scenario:
    __slots__ = ("name", "seed", "p1", "p2", "ticks", "tape", "checkpoints")

    def __init__(self, name, seed, p1, p2=None, ticks=600, tape=None,
                 checkpoints=(150, 300, 600)):
        self.name = name
        self.seed = seed
        self.p1 = p1
        self.p2 = p2
        self.ticks = ticks
        self.tape = tape or []
        self.checkpoints = checkpoints


SCENARIOS = [
    Scenario("solo_runner", 1001, "runner", None, 400),
    Scenario("solo_mage", 1002, "mage", None, 400),
    Scenario("battle_runner_swordsman", 2001, "runner", "swordsman", 600),
    Scenario("battle_mage_ronin", 2002, "mage", "ronin", 600),
    Scenario("battle_jumper_newfighter", 2003, "jumper", "new_fighter", 600),
    # hybrid control: a scripted player drives movement while the AI fights
    Scenario("hybrid_player_move", 3001, "swordsman", "runner", 400,
             tape=[{"move": (1.0, 0.0)}] * 100 +
                  [{"move": (0.0, -1.0)}] * 100 +
                  [{"move": (-1.0, 0.3)}] * 200),
]


def build_world(scn, defs, strict=True):
    w = World(seed=scn.seed, width=1600, height=900,
              config={"strict": strict, "log_events": False})
    w.cursor = (700.0, 450.0) if scn.p2 is None else (1200.0, 450.0)
    w.cursor_active = scn.p2 is None

    a = w.spawn_actor(defs[scn.p1], side=0, x=400.0, y=450.0)
    if scn.tape:
        # hybrid: player brain first (claims MOVE), utility brain second
        # (fills ABILITY).  Identical execution path either way.
        a.brains = [ScriptBrain(scn.tape)] + list(a.brains)
    if scn.p2:
        w.spawn_actor(defs[scn.p2], side=1, x=1200.0, y=450.0)
    return w


def run_scenario(scn, defs, strict=True):
    """Run and return {tick: checksum} plus a summary."""
    w = build_world(scn, defs, strict)
    marks = {}
    for _ in range(scn.ticks):
        w.step()
        if w.tick in scn.checkpoints:
            marks[str(w.tick)] = w.checksum()
    marks["final"] = w.checksum()
    summary = {
        "actors_alive": len(w.living_actors()),
        "motes_alive": w.motes.alive_count(),
        "cues_emitted": w.stats["cues"],
        "faults": w.stats["faults"],
        "hp": {a.archetype.key: round(a.hp, 1) for a in w.all_actors()},
    }
    return marks, summary, w


def record_all():
    defs, errs = load_all(CHARS)
    if errs:
        raise SystemExit("character errors:\n  " + "\n  ".join(errs))
    out = {"version": 1, "scenarios": {}}
    for scn in SCENARIOS:
        marks, summary, _ = run_scenario(scn, defs)
        out["scenarios"][scn.name] = {"marks": marks, "summary": summary}
        print("recorded %-28s final=%s  %s" % (
            scn.name, marks["final"][:16], summary["hp"]))
    with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print("\nwrote %s (%d B)" % (GOLDEN_PATH, os.path.getsize(GOLDEN_PATH)))
    return out


def verify_all(verbose=True):
    if not os.path.exists(GOLDEN_PATH):
        raise SystemExit("no goldens recorded — run `record` first")
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden = json.load(f)
    defs, errs = load_all(CHARS)
    if errs:
        raise SystemExit("character errors:\n  " + "\n  ".join(errs))

    failures = []
    for scn in SCENARIOS:
        want = golden["scenarios"].get(scn.name)
        if want is None:
            failures.append((scn.name, "no golden recorded"))
            continue
        marks, summary, _ = run_scenario(scn, defs)
        for k, v in want["marks"].items():
            if marks.get(k) != v:
                failures.append((scn.name,
                                 "checksum drift at %s: %s != %s"
                                 % (k, marks.get(k, "?")[:16], v[:16])))
                break
        else:
            if verbose:
                print("  PASS  %-28s %s" % (scn.name, marks["final"][:16]))
    if failures:
        print("\nFAILURES:")
        for name, msg in failures:
            print("  FAIL  %-28s %s" % (name, msg))
        return False
    print("\nall %d scenarios reproduce exactly" % len(SCENARIOS))
    return True


def check_determinism(runs=3):
    """Same seed, N runs, identical hashes — catches nondeterminism itself
    (unordered iteration, OS randomness, wall-clock leakage)."""
    defs, errs = load_all(CHARS)
    if errs:
        raise SystemExit("character errors: %s" % errs)
    ok = True
    for scn in SCENARIOS:
        seen = set()
        for _ in range(runs):
            marks, _s, _w = run_scenario(scn, defs)
            seen.add(marks["final"])
        status = "stable" if len(seen) == 1 else "NONDETERMINISTIC"
        print("  %-28s %s (%d distinct over %d runs)"
              % (scn.name, status, len(seen), runs))
        ok = ok and len(seen) == 1
    return ok


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "verify"
    if cmd == "record":
        record_all()
    elif cmd == "determinism":
        sys.exit(0 if check_determinism() else 1)
    else:
        sys.exit(0 if verify_all() else 1)
