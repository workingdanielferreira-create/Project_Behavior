"""Scale benchmark -- how many fighters and motes fit in a 16 ms tick."""
import os, sys, time
from ..content import load_all
from ..sim import World
from ..sim.motes import HAVE_NUMPY

CHARS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "characters")


def bench(n_per_side=4, ticks=400, seed=7):
    defs, errs = load_all(CHARS)
    if errs:
        raise SystemExit(errs)
    keys = sorted(defs)
    w = World(seed=seed, width=1920, height=1080,
              config={"strict": False, "mote_capacity": 8192})
    for side in (0, 1):
        for i in range(n_per_side):
            d = defs[keys[i % len(keys)]]
            w.spawn_actor(d, side=side,
                          x=1920 * (0.2 if side == 0 else 0.8),
                          y=200 + i * 140)
    t0 = time.perf_counter()
    peak = 0
    for _ in range(ticks):
        w.step()
        peak = max(peak, w.motes.alive_count())
    dt = time.perf_counter() - t0
    return {
        "fighters": n_per_side * 2, "ticks": ticks,
        "ms_per_tick": dt * 1000 / ticks,
        "peak_motes": peak, "alive": len(w.living_actors()),
        "faults": w.stats["faults"],
    }


if __name__ == "__main__":
    print("backend:", "numpy" if HAVE_NUMPY else "pure-python")
    print("%-10s %-12s %-11s %-10s" % ("fighters", "ms/tick", "peak motes", "headroom"))
    for n in (1, 2, 4, 8, 16):
        r = bench(n)
        print("%-10d %-12.3f %-11d %-10s" % (
            r["fighters"], r["ms_per_tick"], r["peak_motes"],
            "%.1fx" % (16.0 / max(0.001, r["ms_per_tick"]))))
