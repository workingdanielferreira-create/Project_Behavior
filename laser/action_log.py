"""
action_log.py — lightweight runtime action log for laser_cursor.

Writes a rolling text log to  laser_cursor_log.txt  next to the launcher.
Enabled by setting  LOG_ENABLED = True  in laser/config.py.

Captured event categories
--------------------------
  SHOT_PHASE   which runner cycle phase fired (0=CONE, 1=ZIGZAG, 2=HOMING)
  SHOT_PAUSE   inter-cycle pause counting down (sampled every 15 ticks)
  SHOT_SKIP    a figure was skipped because mode.can_shoot() == False
  BATTLE_SHOT  battle-mode legacy fan shot
  COMBAT       swordsman state: dash / slash / dodge / combo transitions
  KNOCKBACK    knockback sent or received over IPC
  COLLISION    body and projectile hits with collision dots

Usage
-----
  # In World.__init__ (app.py):
  from . import action_log
  action_log.init(log_dir=<launcher_dir>, enabled=config.LOG_ENABLED)

  # Anywhere else:
  from . import action_log
  action_log.log("SHOT_PHASE", f"phase={phase} fig=({fig.x:.0f},{fig.y:.0f})")

  # On shutdown (Overlay.closeEvent):
  action_log.close()
"""

import time
import os

_enabled = False
_log_path = None
_buffer: list = []
_flush_every = 60
_event_count = 0
_start_time = 0.0


def init(log_dir: str, enabled: bool) -> None:
    """Call once at startup from World.__init__."""
    global _enabled, _log_path, _start_time, _event_count, _buffer
    _enabled = enabled
    _buffer = []
    _event_count = 0
    if not enabled:
        return
    _start_time = time.time()
    _log_path = os.path.join(log_dir, "laser_cursor_log.txt")
    try:
        with open(_log_path, "w", encoding="utf-8") as f:
            f.write(
                f"=== laser_cursor action log  {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n\n"
            )
    except OSError:
        _enabled = False


def _ts() -> str:
    return f"{time.time() - _start_time:8.2f}s"


def log(category: str, msg: str) -> None:
    """Record one event.  No-op when logging is disabled."""
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
    try:
        with open(_log_path, "a", encoding="utf-8") as f:
            f.write("\n".join(_buffer) + "\n")
        _buffer.clear()
    except OSError:
        pass


def close() -> None:
    """Flush any remaining events on shutdown."""
    if _enabled:
        _flush()
