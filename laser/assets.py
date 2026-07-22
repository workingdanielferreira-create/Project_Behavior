"""
Asset loading: background removal, scaling, and frame bundles.

A `FrameBundle` is a named container for one figure-mode's full set of sprite
frames (run / idle / slide / slash) plus their horizontally-flipped twins.
Replacing the old 10-tuple with named fields removes a whole class of
unpacking-order bugs (the original `swap_frames` had to keep a 10-item tuple
in perfect sync by hand).
"""

import glob
import os
import re

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage, QTransform

from . import config


def natural_key(path):
    """Numeric sort key from the digits in a filename (standing.png -> 0)."""
    m = re.search(r"(\d+)", os.path.basename(path))
    return int(m.group(1)) if m else 0


def remove_background(pixmap, tol=config.BG_REMOVE_TOLERANCE):
    """Turn a near-black background transparent (alpha 0 below the threshold)."""
    img = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    ptr = img.bits()
    ptr.setsize(w * h * 4)
    buf = bytearray(ptr)
    tol_sq = tol * tol * 3
    for i in range(0, len(buf), 4):
        b, g, r = buf[i], buf[i + 1], buf[i + 2]
        if r * r + g * g + b * b <= tol_sq:
            buf[i + 3] = 0
    result = QImage(bytes(buf), w, h, img.bytesPerLine(), QImage.Format_ARGB32)
    return QPixmap.fromImage(result.copy())


def _load_frames(files, scale, remove_bg=True):
    """Load, de-background, scale, and pre-flip a list of image files.
    `remove_bg=False` skips the near-black -> transparent pass for source
    art that already ships a real alpha channel (generic `sprite_files`
    characters) so dark outline pixels are never eaten."""
    frames, flipped = [], []
    flip = QTransform().scale(-1, 1)
    for fp in files:
        px = QPixmap(fp)
        if px.isNull():
            continue
        if remove_bg:
            px = remove_background(px)
        if scale != 1.0:
            px = px.scaled(max(1, int(px.width() * scale)),
                           max(1, int(px.height() * scale)),
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
        frames.append(px)
        flipped.append(px.transformed(flip))
    return frames, flipped


def _glob(folder, pattern):
    return sorted(glob.glob(os.path.join(folder, pattern)), key=natural_key)


class FrameBundle:
    """All sprite frames for one figure mode, with pre-flipped variants."""

    __slots__ = ("run", "run_flipped", "idle", "idle_flipped",
                 "slide", "slide_flipped", "slide2", "slide2_flipped",
                 "slash", "slash_flipped")

    def __init__(self, run, run_flipped, idle, idle_flipped,
                 slide=None, slide_flipped=None, slide2=None, slide2_flipped=None,
                 slash=None, slash_flipped=None):
        self.run = run
        self.run_flipped = run_flipped
        self.idle = idle
        self.idle_flipped = idle_flipped
        self.slide = slide
        self.slide_flipped = slide_flipped
        self.slide2 = slide2
        self.slide2_flipped = slide2_flipped
        self.slash = slash or []
        self.slash_flipped = slash_flipped or []

    @property
    def has_frames(self):
        return bool(self.run or self.idle)

    @classmethod
    def load(cls, run_files, idle_files, run_scale, idle_scale,
             slide_files=None, slide_scale=None,
             slash_files=None, slash_scale=None, remove_bg=True):
        run, run_fl = _load_frames(run_files, run_scale, remove_bg)
        idle, idle_fl = _load_frames(idle_files, idle_scale, remove_bg)

        s1 = s1f = s2 = s2f = None
        if slide_files and len(slide_files) >= 2:
            ssc = slide_scale if slide_scale is not None else idle_scale
            a, af = _load_frames([slide_files[0]], ssc, remove_bg)
            b, bf = _load_frames([slide_files[1]], ssc, remove_bg)
            s1, s1f = (a[0] if a else None), (af[0] if af else None)
            s2, s2f = (b[0] if b else None), (bf[0] if bf else None)

        slsc = slash_scale if slash_scale is not None else run_scale
        slash, slash_fl = (_load_frames(slash_files, slsc, remove_bg)
                           if slash_files else ([], []))

        return cls(run, run_fl, idle, idle_fl,
                   s1, s1f, s2, s2f, slash, slash_fl)


class AssetLibrary:
    """Loads and owns every mode's FrameBundle, keyed by mode key."""

    def __init__(self, asset_dir):
        self.dir = asset_dir
        self.bundles = {}
        self._load_all()

    def _load_all(self):
        d = self.dir
        # --- Runner (default) ---
        run_files  = _glob(d, "Picture*.png")
        idle_files = _glob(d, "standing*.png")
        slide_files = [os.path.join(d, "slidingback.png"),
                       os.path.join(d, "slidingback2.png")]
        runner = FrameBundle.load(
            run_files, idle_files,
            config.TARGET_HEAD_PX / config.RUN_SRC_HEAD,
            config.TARGET_HEAD_PX / config.IDLE_SRC_HEAD,
            slide_files=slide_files,
            slide_scale=config.TARGET_HEAD_PX / config.SLIDE_SRC_HEAD,
        )
        self.bundles["runner"] = runner

        # --- Swordsman ---
        sword_run   = _glob(d, "swordrun*.png")
        sword_idle  = _glob(d, "swordstanding*.png")
        sword_slash = _glob(d, "slash*.png")
        if sword_run or sword_idle:
            self.bundles["swordsman"] = FrameBundle.load(
                sword_run, sword_idle,
                config.TARGET_HEAD_PX / config.SWORD_RUN_SRC_HEAD,
                config.TARGET_HEAD_PX / config.SWORD_IDLE_SRC_HEAD,
                slash_files=sword_slash,
                slash_scale=config.TARGET_HEAD_PX / config.SWORD_SLASH_SRC_HEAD,
            )
        else:
            # Fall back to the runner bundle so the mode still renders something.
            self.bundles["swordsman"] = runner

        # --- Custom characters (Character Creator pb_character JSONs) ---
        # Registers modes/tuning/LUTs and adds rasterised FrameBundles.
        # Runs in every process, so Solo and Battle see identical rosters.
        from . import characters as _characters
        _characters.load_all(d, self.bundles)

    def bundle(self, mode_key):
        return self.bundles.get(mode_key, self.bundles["runner"])

    @property
    def ok(self):
        r = self.bundles.get("runner")
        return bool(r and r.has_frames)

