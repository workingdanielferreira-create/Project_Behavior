"""
Performance log (Daniel 2026-11-13, frame-rate drop with Fight rhythm on):
where each frame's time goes, written to laser_perf_log.txt (next to
laser_cursor_error.log) every REPORT_S seconds.  Always on, near-zero cost
(a perf_counter per section).  Solo and Battle alike.

Per report: frames painted per second, sim ticks per second, timer calls
that had to catch up (ran 2+ ticks), average / worst ms of the paint and of
every tick section (clash, tag, snapshots, each pipeline system, speedband,
terrain, worldfx, stats, tempo), live FX instances, fighters and their
Fight rhythm intent.
"""

import os
import time

REPORT_S = 5.0

_sec = {}            # name -> [total ms, count, worst ms]
_t = [0.0]           # last lap time
_frames = [0]
_ticks = [0]
_calls = [0]
_catchup = [0]
_start = [time.perf_counter()]
_path = [None]


def _add(name, ms):
    s = _sec.get(name)
    if s is None:
        _sec[name] = [ms, 1, ms]
    else:
        s[0] += ms
        s[1] += 1
        if ms > s[2]:
            s[2] = ms


def begin():
    _t[0] = time.perf_counter()


def lap(name):
    """Time since begin() / the last lap, booked under `name`."""
    now = time.perf_counter()
    _add(name, (now - _t[0]) * 1000.0)
    _t[0] = now


def add(name, ms):
    _add(name, ms)


def tick():
    _ticks[0] += 1


def call(steps):
    _calls[0] += 1
    if steps > 1:
        _catchup[0] += 1


def frame(world, paint_ms):
    _frames[0] += 1
    _add("PAINT", paint_ms)
    el = time.perf_counter() - _start[0]
    if el >= REPORT_S:
        try:
            _report(world, el)
        except Exception:
            pass
        _sec.clear()
        _frames[0] = _ticks[0] = _calls[0] = _catchup[0] = 0
        _start[0] = time.perf_counter()


def _report(world, el):
    if _path[0] is None:
        from . import action_log
        ep = getattr(action_log, "_error_path", None)
        d = os.path.dirname(ep) if ep else os.getcwd()
        _path[0] = os.path.join(d, "laser_perf_log.txt")
    figs = []
    nfx = 0
    from . import tempo
    for s in getattr(world, "sides", ()) or ():
        for f in s.figures:
            drv = getattr(f, "fx", None)
            if drv is not None:
                try:
                    nfx += len(drv.player.insts) + len(drv.clane[0].insts)
                except Exception:
                    pass
            st = getattr(f, "tempo", None)
            it = st.intent if (st is not None and tempo.config_for(f) is not None) else "-"
            figs.append("%s:%s" % (getattr(f.mode, "key", "?"), it))
    lines = ["%s  fps %.1f  ticks/s %.1f  catch-up calls %d/%d  fx %d  [%s]" % (
        time.strftime("%H:%M:%S"), _frames[0] / el, _ticks[0] / el, _catchup[0], _calls[0], nfx, ", ".join(figs))]
    for name, (tot, n, worst) in sorted(_sec.items(), key=lambda kv: -kv[1][0]):
        lines.append("    %-22s avg %7.3f ms  worst %7.2f ms  x%d" % (name, tot / max(1, n), worst, n))
    with open(_path[0], "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
