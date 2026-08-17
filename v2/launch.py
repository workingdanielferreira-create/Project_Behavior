"""Entry point for the embedded CPython runtime.

Why this file exists
--------------------
The repo ships an embedded Python whose `python314._pth` puts the interpreter
in ISOLATED mode.  In that mode Python:

  * ignores PYTHONPATH entirely, and
  * does NOT prepend the script directory or the working directory to
    sys.path (the -P behaviour implied by isolation).

The `.` line inside `python314._pth` resolves to the directory holding
python.exe -- the REPO ROOT.  So `laser/` is importable (which is why v1
works) but `v2/pb2/` is not, and `python -m pb2.app.main` fails with
ModuleNotFoundError no matter what the working directory is.

Running this file fixes it without editing `python314._pth`, so v1's runtime
configuration is left completely untouched.

Usage
-----
    python.exe launch.py run  [p1] [p2] [seed]
    python.exe launch.py test [determinism|verify|record|bench|all]
    python.exe launch.py doctor
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def doctor():
    """Report the environment.  Run this first when anything misbehaves."""
    print("Project Behavior V2 - environment check")
    print("-" * 52)
    print("python      :", sys.version.split()[0])
    print("executable  :", sys.executable)
    print("v2 folder   :", HERE)
    print("sys.path[0] :", sys.path[0])
    ok = True

    try:
        import pb2
        print("pb2         : OK (v%s)" % pb2.__version__)
    except Exception as e:
        print("pb2         : FAIL -", e)
        ok = False

    try:
        import numpy
        print("numpy       : OK (%s) - full FX budget" % numpy.__version__)
    except Exception:
        print("numpy       : absent - pure-Python fallback "
              "(identical results, lower FX budget)")

    try:
        import PyQt5
        from PyQt5 import QtWidgets      # noqa: F401
        print("PyQt5       : OK - overlay available")
    except Exception as e:
        print("PyQt5       : FAIL -", e)
        print("              the simulation and tests still run; only the "
              "overlay needs Qt")

    chars = os.path.join(HERE, "characters")
    try:
        import pb2.sim                    # noqa: F401  registers plugins
        from pb2.content import load_all
        defs, errs = load_all(chars)
        print("characters  : %d loaded %s" % (len(defs), sorted(defs)))
        for e in errs:
            print("              ERROR", e)
            ok = False
    except Exception as e:
        print("characters  : FAIL -", e)
        ok = False

    print("-" * 52)
    print("RESULT      :", "ready" if ok else "problems found (see above)")
    return 0 if ok else 1


def test(what="all"):
    from pb2.harness import golden
    rc = 0
    if what in ("all", "determinism"):
        print("============ DETERMINISM ============")
        rc |= 0 if golden.check_determinism() else 1
        print()
    if what in ("all", "verify"):
        print("============ GOLDEN CHECKSUMS =======")
        rc |= 0 if golden.verify_all() else 1
        print()
    if what == "record":
        golden.record_all()
        return 0
    if what in ("all", "bench"):
        print("============ SCALE BENCHMARK ========")
        from pb2.harness import bench as b
        from pb2.sim.motes import HAVE_NUMPY
        print("backend:", "numpy" if HAVE_NUMPY else "pure-python")
        print("%-10s %-12s %-11s %-10s" % ("fighters", "ms/tick",
                                           "peak motes", "headroom"))
        for n in (1, 2, 4, 8):
            r = b.bench(n, ticks=250)
            print("%-10d %-12.3f %-11d %-10s" % (
                r["fighters"], r["ms_per_tick"], r["peak_motes"],
                "%.1fx" % (16.0 / max(0.001, r["ms_per_tick"]))))
    return rc


def run(argv):
    p1 = argv[0] if argv else "runner"
    p2 = argv[1] if len(argv) > 1 else "swordsman"
    seed = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else None
    try:
        from pb2.app.overlay import run as run_overlay
    except ImportError as e:
        print("[pb2] cannot start the overlay:", e)
        print("[pb2] PyQt5 is required for the overlay. The headless tests")
        print("[pb2] (launch.py test) do not need it.")
        return 1
    return run_overlay(os.path.join(HERE, "characters"),
                       p1=p1, p2=p2, seed=seed,
                       strict="--strict" in argv)


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    cmd = argv[0] if argv else "run"
    rest = argv[1:]
    if cmd == "doctor":
        return doctor()
    if cmd == "test":
        return test(rest[0] if rest else "all")
    if cmd == "run":
        return run(rest)
    return run(argv)          # bare args treated as fighter names


if __name__ == "__main__":
    sys.exit(main())
