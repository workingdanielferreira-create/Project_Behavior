"""
action_log.py — runtime action log + error/crash capture for laser_cursor.

Two output files, written next to the launcher:
  laser_cursor_log.txt   — action events (only when LOG_ENABLED = True)
  laser_cursor_error.log — errors, exceptions, and crash tracebacks
                           (ALWAYS written, regardless of LOG_ENABLED)

Captured action categories
--------------------------
  SHOT_PHASE   which runner cycle phase fired (0=CONE, 1=ZIGZAG, 2=HOMING)
  SHOT_PAUSE   inter-cycle pause counting down (sampled every 15 ticks)
  SHOT_SKIP    a figure was skipped because mode.can_shoot() == False
  BATTLE_SHOT  battle-mode shot fired
  BULLET_HIT   bullet-vs-bullet scatter collision
  COMBAT       swordsman state: dash / slash / dodge / combo transitions
  KNOCKBACK    knockback dealt or received across sides
  COLLISION    body and projectile hits

Error log entries
-----------------
  [ERROR]   — a caught exception (non-fatal, execution continued)
  [CRASH]   — an exception that killed a tick or system call
  [FATAL]   — uncaught exception reaching sys.excepthook (process about to die)
  [WARN]    — recoverable unexpected condition

Usage
-----
  # Startup (World.__init__):
  from . import action_log
  action_log.init(log_dir=<launcher_dir>, enabled=config.LOG_ENABLED)

  # Action events:
  action_log.log("SHOT_PHASE", "phase=0 ...")

  # Error capture (always writes, even if log disabled):
  action_log.error("label", exc)          # caught non-fatal
  action_log.crash("_tick", exc)          # caught tick-level crash
  action_log.warn("combat", "side eliminated")  # warning

  # Shutdown:
  action_log.close()
"""

import os
import queue
import sys
import threading
import time
import traceback

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_enabled    = False          # action log on/off (set by init())
_log_path   = None           # laser_cursor_log.txt
_error_path = None           # laser_cursor_error.log  (always written once init'd)
_buffer: list  = []
_flush_every   = 60
_event_count   = 0
_start_time    = 0.0
_session_label = ""          # "SOLO" or "BATTLE" — set by init(), used in headers


# ---------------------------------------------------------------------------
# Background file writer (Daniel 2026-11-14: the game froze ~17 s every
# 30-60 s).  Appending to the log files on the game thread blocked whenever
# Windows held the file (cloud sync / antivirus scanning the growing log), and
# the whole overlay stopped with it.  Every log append (action log, error log,
# laser/perf.py's performance log) is now queued and written by ONE daemon
# thread, in order; the game thread never touches the disk.  close() and a
# fatal crash drain the queue (bounded wait) so nothing is lost on exit.
# ---------------------------------------------------------------------------
_wq = queue.Queue()
_wthread = [None]
_wlock = threading.Lock()


def _writer() -> None:
    while True:
        path, text = _wq.get()
        try:
            if path is not None:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(text)
        except OSError:
            pass
        finally:
            _wq.task_done()


def append(path, text: str) -> None:
    """Append `text` to the file at `path` off the game thread (never blocks)."""
    if not path or not text:
        return
    if _wthread[0] is None:
        with _wlock:
            if _wthread[0] is None:
                t = threading.Thread(target=_writer, name="log-writer", daemon=True)
                t.start()
                _wthread[0] = t
    _wq.put((path, text))


def drain(timeout: float = 3.0) -> None:
    """Wait (at most `timeout` s) for queued log writes to reach the disk."""
    if _wthread[0] is None:
        return
    end = time.time() + timeout
    while _wq.unfinished_tasks and time.time() < end:
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# Init / shutdown
# ---------------------------------------------------------------------------
def init(log_dir: str, enabled: bool, session_label: str = "") -> None:
    """Call once at startup from World.__init__.

    Always initialises the error log path so crash() / error() work even when
    the action log is disabled.
    """
    global _enabled, _log_path, _error_path, _start_time
    global _event_count, _buffer, _session_label

    _enabled       = enabled
    _buffer        = []
    _event_count   = 0
    _start_time    = time.time()
    _session_label = session_label or ""

    stamp = time.strftime("%Y-%m-%d %H:%M:%S")

    # ── Error log — always created/appended ──────────────────────────────
    _error_path = os.path.join(log_dir, "laser_cursor_error.log")
    try:
        with open(_error_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n"
                    f"=== SESSION START  {stamp}"
                    f"{'  ' + _session_label if _session_label else ''}  ===\n"
                    f"{'='*60}\n")
    except OSError:
        _error_path = None

    # ── Action log — only when enabled ───────────────────────────────────
    if not enabled:
        return
    _log_path = os.path.join(log_dir, "laser_cursor_log.txt")
    try:
        with open(_log_path, "w", encoding="utf-8") as f:
            f.write(f"=== laser_cursor action log  {stamp} ===\n\n")
    except OSError:
        _enabled = False


def close() -> None:
    """Flush remaining action events, write a clean session-end marker and
    wait (bounded) for the background writer to finish."""
    _flush()
    if _error_path:
        elapsed = time.time() - _start_time if _start_time else 0
        append(_error_path, f"=== SESSION END  (uptime {elapsed:.1f}s) ===\n")
    drain()


# ---------------------------------------------------------------------------
# Action logging
# ---------------------------------------------------------------------------
def _ts() -> str:
    return f"{time.time() - _start_time:8.2f}s"


def log(category: str, msg: str) -> None:
    """Record one action event.  No-op when logging is disabled."""
    if not _enabled:
        return
    global _event_count
    _buffer.append(f"[{_ts()}] [{category:<12s}] {msg}")
    _event_count += 1
    if _event_count % _flush_every == 0:
        _flush()


def _flush() -> None:
    if not _log_path or not _buffer:
        return
    append(_log_path, "\n".join(_buffer) + "\n")
    _buffer.clear()


# ---------------------------------------------------------------------------
# Error / crash capture  (always active once init() has been called)
# ---------------------------------------------------------------------------
def _write_error(level: str, label: str, msg: str, tb: str = "") -> None:
    """Queue one error entry for the error log right away (background writer)."""
    if not _error_path:
        return
    stamp = time.strftime("%H:%M:%S")
    elapsed = f"{time.time() - _start_time:.2f}s" if _start_time else "?.??s"
    lines = [f"[{stamp}] [{elapsed}] [{level}] {label}: {msg}"]
    if tb:
        for tline in tb.rstrip().splitlines():
            lines.append(f"    {tline}")
    lines.append("")          # blank separator
    append(_error_path, "\n".join(lines) + "\n")


def warn(label: str, msg: str) -> None:
    """Log a recoverable unexpected condition."""
    _write_error("WARN ", label, msg)


def error(label: str, exc: BaseException) -> None:
    """Log a caught non-fatal exception with its traceback."""
    tb = traceback.format_exc()
    _write_error("ERROR", label, str(exc), tb)


def crash(label: str, exc: BaseException) -> None:
    """Log a caught tick/system-level crash with its traceback."""
    tb = traceback.format_exc()
    _write_error("CRASH", label, str(exc), tb)
    # Also surface in the action log if it's enabled, so the two files
    # can be read together without cross-referencing timestamps.
    log("CRASH", f"{label}: {exc}")


def install_excepthook() -> None:
    """Replace sys.excepthook so unhandled exceptions also land in the error log.

    The original hook is chained so the normal stderr output still appears.
    Call once after init().
    """
    _original = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        _write_error("FATAL", type(exc_value).__name__, str(exc_value), tb_str)
        drain(1.0)
        _original(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
