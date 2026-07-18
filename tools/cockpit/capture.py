"""
Project Behavior — Dev Cockpit capture harness (cockpit_run v1).

Runs the REAL, unmodified `laser/` engine headless (QT_QPA_PLATFORM=offscreen)
and records every tick as a synchronized (frame, state, events) triple into a
single versioned bundle file that the Cockpit viewer artifact plays back.

Design pillars
--------------
* Zero engine modification.  The harness imports `laser` as-is.  The only
  runtime patches are harness-side and documented below (determinism +
  scripted cursor); they never touch repo files.
* Determinism.  `--seed` fixes the global `random` module AND `os.urandom`
  (which seeds each figure's Personality RNG), so the same seed replays the
  identical battle tick-for-tick — before/after captures of a code fix show
  the exact same scenario.
* Pluggable recorders.  Each data stream is one Recorder subclass with a
  begin_run / record_tick / end_run contract.  New streams (hitbox overlays,
  system timings, ...) are new classes appended to RECORDERS — existing
  recorders are never edited.

Usage
-----
    python3 capture.py --mode battle --p1 new_fighter --p2 mage \
        --ticks 625 --seed 42 --out run.pbrun.json

Bundle format (cockpit_run v1) is documented in COCKPIT.md next to this file.
"""

import argparse
import base64
import hashlib
import io
import json
import os
import random
import struct
import sys
import time

# --------------------------------------------------------------------------
# Environment must be set BEFORE any Qt import.
# --------------------------------------------------------------------------
# Make the repo root importable regardless of where the harness is invoked
# from (capture.py lives two levels below the root).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_RUNTIME_DIR", "/tmp/runtime-cockpit")
os.makedirs(os.environ["XDG_RUNTIME_DIR"], exist_ok=True)

BUNDLE_VERSION = "cockpit_run v1"


# --------------------------------------------------------------------------
# Determinism layer (harness-side patches — the engine itself is untouched).
# --------------------------------------------------------------------------
class DeterministicEntropy:
    """Replaces os.urandom with a seeded stream so Personality RNGs
    (seeded from OS entropy at Figure creation) become reproducible."""

    def __init__(self, seed):
        self._rng = random.Random(seed ^ 0x9E3779B97F4A7C15)

    def __call__(self, n):
        return bytes(self._rng.getrandbits(8) for _ in range(n))


def install_determinism(seed):
    random.seed(seed)
    os.urandom = DeterministicEntropy(seed)   # harness-process only


# --------------------------------------------------------------------------
# Recorder plugin contract.
# --------------------------------------------------------------------------
class Recorder:
    """One data stream.  Subclass and append an instance to RECORDERS."""

    name = "base"

    def begin_run(self, ctx):
        """Called once before tick 0.  ctx = CaptureContext."""

    def record_tick(self, ctx, tick, out):
        """Called after every engine tick.  Write fields into `out` (dict
        for this tick's bundle entry).  Never mutate engine state."""

    def end_run(self, ctx, meta):
        """Called once after the last tick.  May add bundle metadata."""


class FrameRecorder(Recorder):
    """Renders the real Overlay widget (its actual _paint path) into an
    offscreen pixmap, composites onto a dark backdrop (the overlay is
    translucent by design), scales, and stores JPEG base64."""

    name = "frame"

    def __init__(self, scale=0.5, quality=82, every=1):
        self.scale = scale
        self.quality = quality
        self.every = max(1, every)

    def begin_run(self, ctx):
        from PyQt5.QtGui import QPixmap, QPainter, QColor
        from PyQt5.QtCore import Qt, QBuffer, QByteArray
        self._QPixmap, self._QPainter = QPixmap, QPainter
        self._QColor, self._Qt = QColor, Qt
        self._QBuffer, self._QByteArray = QBuffer, QByteArray
        meta_w = int(ctx.overlay.width() * self.scale)
        meta_h = int(ctx.overlay.height() * self.scale)
        ctx.meta["frame_w"], ctx.meta["frame_h"] = meta_w, meta_h
        ctx.meta["world_w"] = ctx.overlay.width()
        ctx.meta["world_h"] = ctx.overlay.height()
        ctx.meta["frame_scale"] = self.scale
        ctx.meta["frame_every"] = self.every

    def record_tick(self, ctx, tick, out):
        if tick % self.every:
            return
        ov = ctx.overlay
        pm = self._QPixmap(ov.size())
        pm.fill(self._QColor(12, 12, 16))          # dark backdrop
        ov.render(pm)                               # runs the real paintEvent
        if self.scale != 1.0:
            pm = pm.scaled(int(pm.width() * self.scale),
                           int(pm.height() * self.scale),
                           self._Qt.KeepAspectRatio,
                           self._Qt.SmoothTransformation)
        ba = self._QByteArray()
        buf = self._QBuffer(ba)
        buf.open(self._QBuffer.WriteOnly)
        pm.save(buf, "JPG", self.quality)
        buf.close()
        out["png"] = base64.b64encode(bytes(ba)).decode("ascii")


class StateRecorder(Recorder):
    """Full simulation state per tick: figures, projectiles (with stable
    ids), and world-level flags.  This is what lets the Cockpit link a
    circled pixel to a concrete object at a concrete tick."""

    name = "state"

    def begin_run(self, ctx):
        self._proj_ids = {}       # id(obj) -> stable serial
        self._next_proj = 1

    def _pid(self, pr):
        k = id(pr)
        if k not in self._proj_ids:
            self._proj_ids[k] = self._next_proj
            self._next_proj += 1
        return self._proj_ids[k]

    def record_tick(self, ctx, tick, out):
        w = ctx.world
        figs = []
        for si, side in enumerate(w.sides):
            for f in side.figures:
                c, p = f.combat, f.personality
                figs.append(dict(
                    side=si, idx=f.index, mode=side.mode_key,
                    x=round(f.x, 1), y=round(f.y, 1),
                    hp=round(getattr(p, "hp", 0.0), 2),
                    max_hp=round(getattr(p, "max_hp", 0.0), 2),
                    facing_left=bool(f.transform.facing_left),
                    flags=[n for n in (
                        "slashing", "dashing", "rebounding", "parrying",
                        "dodge_dashing", "arc_combo_active", "combo_pending",
                        "blinking")
                        if getattr(c, n, False)],
                ))
        projs = []
        for si, side in enumerate(w.sides):
            for pr in side.projectiles:
                if not getattr(pr, "alive", True):
                    continue
                projs.append(dict(
                    id=self._pid(pr), side=si,
                    cls=type(pr).__name__,
                    x=round(pr.x, 1), y=round(pr.y, 1),
                    vx=round(pr.vx, 2), vy=round(pr.vy, 2),
                    dmg=round(float(getattr(pr, "damage", 1.0)), 2),
                    pierce=bool(getattr(pr, "pierce", False)),
                    hit=bool(getattr(pr, "hit_r_sq", 0.0) > 0.0),
                ))
        out["state"] = dict(
            battle=bool(w.battle_mode),
            hitstop=int(w.hitstop_ticks),
            figures=figs, projectiles=projs,
        )


class LogRecorder(Recorder):
    """Captures the engine's own action_log events (cancellation reasons,
    crashes, warnings) and attaches them to the tick they occurred on."""

    name = "log"

    def begin_run(self, ctx):
        from laser import action_log
        self._buf = []
        self._orig_log = action_log.log
        self._orig_warn = action_log.warn

        def cap_log(category, msg, _o=self._orig_log):
            self._buf.append(f"{category}: {msg}")
            _o(category, msg)

        def cap_warn(label, msg, _o=self._orig_warn):
            self._buf.append(f"WARN {label}: {msg}")
            _o(label, msg)

        action_log.log = cap_log
        action_log.warn = cap_warn

    def record_tick(self, ctx, tick, out):
        if self._buf:
            out["events"] = self._buf[:]
            self._buf.clear()

    def end_run(self, ctx, meta):
        from laser import action_log
        action_log.log = self._orig_log
        action_log.warn = self._orig_warn


# --------------------------------------------------------------------------
# Capture context + driver.
# --------------------------------------------------------------------------
class CaptureContext:
    def __init__(self, app, overlay, world, meta):
        self.app, self.overlay, self.world, self.meta = app, overlay, world, meta


class ScriptedCursor:
    """Replaces QCursor.pos inside laser.app so the cursor is deterministic.
    v1: fixed center.  v2 hook: pass a per-tick (x, y) script."""

    def __init__(self, x, y):
        from PyQt5.QtCore import QPoint
        self._p = QPoint(int(x), int(y))

    def pos(self):
        return self._p


class _FixedScreen:
    """primaryScreen() stand-in: the offscreen platform reports 640x480 by
    default, which is not the world the game plays in.  This shim makes the
    engine build the same 1920x1080 world Daniel's machine runs."""

    def __init__(self, w, h):
        from PyQt5.QtCore import QRect
        self._g = QRect(0, 0, w, h)

    def geometry(self):
        return self._g


class _AppShim:
    """Wraps the real QApplication, overriding only primaryScreen."""

    def __init__(self, real, screen):
        self._real, self._screen = real, screen

    def primaryScreen(self):
        return self._screen

    def __getattr__(self, name):
        return getattr(self._real, name)


def build_world(mode, p1, p2, world_w=1920, world_h=1080):
    """Field the requested matchup through World's own public API."""
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from laser import app as lapp

    _shim = _AppShim(app, _FixedScreen(world_w, world_h))
    _orig_qapp = lapp.QApplication
    lapp.QApplication = _shim              # Overlay.__init__ reads this
    try:
        overlay = lapp.Overlay()
    finally:
        lapp.QApplication = _orig_qapp
    # showFullScreen() sized the widget to the offscreen platform's tiny
    # default display; re-size it to the true world so frames are 1:1.
    overlay.showNormal()
    overlay.resize(world_w, world_h)
    overlay._timer.stop()                 # harness drives ticks manually
    w = overlay.world

    order = __import__("laser.modes", fromlist=["modes"]).ordered_modes()
    for key, label in ((p1, "p1"), (p2, "p2")):
        if key and key not in order:
            raise SystemExit(f"unknown character for {label}: {key!r} "
                             f"(available: {order})")

    w.sides[0].mode_key = p1
    w.mode_key = p1
    w._reskin_side(0)
    if mode == "battle":
        w.sides[1].mode_key = p2
        w.add_figure(1)
        w._reskin_side(1)

    # Combat gates: firing requires shoot_mode (the in-game toggle).  On by
    # default for captures — a capture of two idle fighters is rarely the
    # goal.  Both remain scriptable via CLI flags.
    w.shoot_mode = True
    w.runner_on = True

    # Deterministic cursor: overlay reads QCursor.pos() every tick.
    lapp.QCursor = ScriptedCursor(w.screen_w // 2, w.screen_h // 2)
    return app, overlay, w


def run_capture(args):
    install_determinism(args.seed)
    t0 = time.time()
    app, overlay, world = build_world(args.mode, args.p1, args.p2)

    engine_commit = os.environ.get("PB_ENGINE_COMMIT", "unknown")
    meta = dict(version=BUNDLE_VERSION, seed=args.seed, mode=args.mode,
                p1=args.p1, p2=(args.p2 if args.mode == "battle" else None),
                ticks=args.ticks, tick_ms=__import__(
                    "laser.config", fromlist=["config"]).TICK_MS,
                engine_commit=engine_commit,
                captured_at=time.strftime("%Y-%m-%d %H:%M:%S"))

    recorders = [FrameRecorder(scale=args.scale, quality=args.quality,
                               every=args.frame_every),
                 StateRecorder(), LogRecorder()]
    ctx = CaptureContext(app, overlay, world, meta)
    for r in recorders:
        r.begin_run(ctx)

    frames = []
    for t in range(args.ticks):
        overlay._tick()                   # the REAL engine tick, unmodified
        entry = {"t": t}
        for r in recorders:
            r.record_tick(ctx, t, entry)
        frames.append(entry)
        if t and t % 200 == 0:
            print(f"  tick {t}/{args.ticks} "
                  f"({time.time() - t0:.1f}s)", flush=True)

    for r in recorders:
        r.end_run(ctx, meta)

    bundle = dict(meta=meta, frames=frames)
    raw = json.dumps(bundle, separators=(",", ":"))
    with open(args.out, "w") as fh:
        fh.write(raw)
    print(f"bundle: {args.out}  {len(raw)/1e6:.1f} MB  "
          f"{args.ticks} ticks  {time.time() - t0:.1f}s  "
          f"sha256 {hashlib.sha256(raw.encode()).hexdigest()[:12]}")


def main():
    ap = argparse.ArgumentParser(description="Dev Cockpit capture harness")
    ap.add_argument("--mode", choices=["solo", "battle"], default="battle")
    ap.add_argument("--p1", default="new_fighter")
    ap.add_argument("--p2", default="mage")
    ap.add_argument("--ticks", type=int, default=625)     # ~10 s at 16 ms
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--quality", type=int, default=82)
    ap.add_argument("--frame-every", type=int, default=1)
    ap.add_argument("--out", default="run.pbrun.json")
    run_capture(ap.parse_args())


if __name__ == "__main__":
    main()
