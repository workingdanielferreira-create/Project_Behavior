"""
IPC bridge — named shared memory letting two running instances see each other's
figures and projectiles so they can fight.

The byte layout is declared once, in one place, derived from struct strides so
the offsets can never silently drift from the format strings (the old code kept
two hand-written layout comments that had already disagreed).

  [0..1]    2 x uint8    slot-claim flags (0=free, 1=taken)
  [2..17]   2 x float64  heartbeats (wall-clock seconds)
  figures      per slot: MAX_FIGS x (f x, f y, B alive, B dashing)  = 10B each
  projectiles  per slot: MAX_PROJS x (4f pos/vel, 4B rgba)          = 20B each
"""

import mmap
import os
import struct
import time

_NAME       = "LaserCursorIPC_v1"
MAX_FIGS    = 8
MAX_PROJS   = 16

_FIG_FMT    = "<ffBB"
_PROJ_FMT   = "<ffffBBBB"
_HB_FMT     = "<d"
_FIG_STRIDE  = struct.calcsize(_FIG_FMT)    # 10
_PROJ_STRIDE = struct.calcsize(_PROJ_FMT)   # 20
_HB_SIZE     = struct.calcsize(_HB_FMT)     # 8

# Derived offsets ----------------------------------------------------------
_CLAIMS      = 0
_HB_BASE     = _CLAIMS + 2
_FIG_BASE    = [_HB_BASE + 2 * _HB_SIZE,
                _HB_BASE + 2 * _HB_SIZE + MAX_FIGS * _FIG_STRIDE]
_PROJ_BASE   = [_FIG_BASE[1] + MAX_FIGS * _FIG_STRIDE,
                _FIG_BASE[1] + MAX_FIGS * _FIG_STRIDE + MAX_PROJS * _PROJ_STRIDE]
_SIZE        = _PROJ_BASE[1] + MAX_PROJS * _PROJ_STRIDE + 8   # +pad

HEARTBEAT_MAX = 1.5   # seconds; partner considered dead past this


class IPCBridge:
    """mmap-backed two-slot bridge built on a temp file."""

    def __init__(self):
        self._mm = None
        self._fh = None
        self._slot = -1
        self._open()

    def _open(self):
        try:
            tmp = os.path.join(
                os.environ.get("TEMP", os.environ.get("TMP", "C:\\Temp")),
                "laser_cursor_ipc.bin")
            if not os.path.exists(tmp):
                with open(tmp, "wb") as f:
                    f.write(b"\x00" * _SIZE)
            self._fh = open(tmp, "r+b")
            self._mm = mmap.mmap(self._fh.fileno(), _SIZE)

            # Wipe a stale file left by a crashed run (no recent heartbeat).
            now = time.time()
            stale = True
            for s in range(2):
                if self._mm[s] == 1:
                    t = struct.unpack(_HB_FMT, self._read(_HB_BASE + s * _HB_SIZE, _HB_SIZE))[0]
                    if abs(now - t) < HEARTBEAT_MAX * 4:
                        stale = False
                        break
            if stale:
                self._mm.seek(0)
                self._mm.write(b"\x00" * _SIZE)
                self._mm.flush()

            for s in range(2):
                if self._mm[s] == 0:
                    self._mm[s] = 1
                    self._slot = s
                    self._mm.flush()
                    break
        except Exception:
            self._close_handles()

    # low-level -------------------------------------------------------------
    def _read(self, off, n):
        self._mm.seek(off)
        return self._mm.read(n)

    def _write(self, off, data):
        self._mm.seek(off)
        self._mm.write(data)

    def _close_handles(self):
        try:
            if self._mm is not None:
                self._mm.close()
            if self._fh is not None:
                self._fh.close()
        except Exception:
            pass
        self._mm = self._fh = None

    # state -----------------------------------------------------------------
    def alive(self):
        return self._mm is not None and self._slot >= 0

    def _partner(self):
        return 1 - self._slot if self._slot >= 0 else -1

    def write_heartbeat(self):
        self._write(_HB_BASE + self._slot * _HB_SIZE, struct.pack(_HB_FMT, time.time()))

    def partner_alive(self):
        if not self.alive():
            return False
        ps = self._partner()
        if self._mm[ps] == 0:
            return False
        t = struct.unpack(_HB_FMT, self._read(_HB_BASE + ps * _HB_SIZE, _HB_SIZE))[0]
        return abs(time.time() - t) < HEARTBEAT_MAX

    # figures ---------------------------------------------------------------
    def write_figures(self, figures):
        base = _FIG_BASE[self._slot]
        for i in range(MAX_FIGS):
            off = base + i * _FIG_STRIDE
            if i < len(figures):
                f = figures[i]
                self._write(off, struct.pack(
                    _FIG_FMT, f.x, f.y,
                    1 if f.transform.init else 0,
                    1 if f.combat.dashing else 0))
            else:
                self._write(off, struct.pack(_FIG_FMT, 0.0, 0.0, 0, 0))

    def read_partner_figures(self):
        base = _FIG_BASE[self._partner()]
        out = []
        for i in range(MAX_FIGS):
            x, y, alive, dashing = struct.unpack(
                _FIG_FMT, self._read(base + i * _FIG_STRIDE, _FIG_STRIDE))
            if alive:
                out.append((x, y, bool(dashing)))
        return out

    # projectiles -----------------------------------------------------------
    def write_projectiles(self, projectiles):
        base = _PROJ_BASE[self._slot]
        written = 0
        for proj in projectiles:
            if written >= MAX_PROJS:
                break
            if not proj.alive:
                continue
            self._write(base + written * _PROJ_STRIDE, struct.pack(
                _PROJ_FMT, proj.x, proj.y, proj.vx, proj.vy,
                proj.r, proj.g, proj.b, 1))
            written += 1
        for i in range(written, MAX_PROJS):
            self._write(base + i * _PROJ_STRIDE, b"\x00" * _PROJ_STRIDE)

    def read_partner_projectiles(self):
        base = _PROJ_BASE[self._partner()]
        out = []
        for i in range(MAX_PROJS):
            x, y, vx, vy, r, g, b, alive = struct.unpack(
                _PROJ_FMT, self._read(base + i * _PROJ_STRIDE, _PROJ_STRIDE))
            if alive:
                out.append((x, y, vx, vy, r, g, b))
        return out

    # cleanup ---------------------------------------------------------------
    def release(self):
        try:
            if self._mm is not None and self._slot >= 0:
                self._mm[self._slot] = 0
                self._mm.flush()
        except Exception:
            pass
        self._close_handles()
        self._slot = -1
