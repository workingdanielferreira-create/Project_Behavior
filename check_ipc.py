"""
Run this WHILE laser_cursor is open (or after a crash) to inspect the IPC file.
Usage:  python check_ipc.py
Output is printed to console AND written to check_ipc_log.txt next to this script.
"""
import os, struct, time, mmap

_IPC_SIZE     = 778
_MAX_IPC_FIGS = 8
_MAX_IPC_PROJS= 16
_FIG_STRIDE   = 9
_PROJ_STRIDE  = 16
_SLOT_BASE    = [10, 138]
_PROJ_BASE    = [266, 522]

tmp = os.path.join(
    os.environ.get('TEMP', os.environ.get('TMP', 'C:\\Temp')),
    'laser_cursor_ipc.bin')

lines = []
def p(s=''):
    print(s)
    lines.append(s)

p(f"IPC file: {tmp}")
p(f"Exists:   {os.path.exists(tmp)}")

if not os.path.exists(tmp):
    p("File not found — no instance has run yet, or it was already deleted.")
else:
    size = os.path.getsize(tmp)
    p(f"Size:     {size} bytes (expected {_IPC_SIZE})")
    with open(tmp, 'rb') as f:
        raw = f.read()

    p()
    now = time.monotonic() % 1e6
    p(f"time.monotonic() % 1e6 = {now:.3f}")
    p()

    for s in range(2):
        claimed = raw[s]
        p(f"--- Slot {s} ---")
        p(f"  claimed flag : {claimed}  ({'TAKEN' if claimed else 'free'})")
        hb_off = 2 + s * 4
        hb_raw = raw[hb_off:hb_off+4]
        hb_val = struct.unpack('<f', hb_raw)[0]
        age    = now - hb_val
        p(f"  heartbeat    : {hb_val:.3f}  (age from now: {age:.3f}s)")
        p(f"  heartbeat raw: {hb_raw.hex()}")

        base = _SLOT_BASE[s]
        p(f"  figures ({_MAX_IPC_FIGS} slots):")
        for i in range(_MAX_IPC_FIGS):
            off = base + i * _FIG_STRIDE
            chunk = raw[off:off+_FIG_STRIDE]
            x, y, alive = struct.unpack('<ffB', chunk)
            if alive or i < 2:
                p(f"    [{i}] x={x:.1f} y={y:.1f} alive={alive}  raw={chunk.hex()}")

        pbase = _PROJ_BASE[s]
        p(f"  projectiles ({_MAX_IPC_PROJS} slots, showing non-zero only):")
        any_proj = False
        for i in range(_MAX_IPC_PROJS):
            off = pbase + i * _PROJ_STRIDE
            chunk = raw[off:off+_PROJ_STRIDE]
            if any(chunk):
                x, y, vx, vy, r, g, b, alive = struct.unpack('<ffffBBBB', chunk)
                p(f"    [{i}] x={x:.1f} y={y:.1f} vx={vx:.2f} vy={vy:.2f} "
                  f"rgb=({r},{g},{b}) alive={alive}")
                any_proj = True
        if not any_proj:
            p("    (all zero)")
        p()

    log = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check_ipc_log.txt')
    with open(log, 'w') as f:
        f.write('\n'.join(lines))
    print(f"\nLog written to: {log}")
    input("\nPress Enter to exit...")
