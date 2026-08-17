"""Position-based bilinear scaling -- v1's signature mechanic, generalised.

Two independent four-corner grids sampled from an entity's own screen
position:

  size  -- purely visual.  Hurtboxes and hit tests are NEVER scaled by it,
           exactly as in v1 (this decoupling is why it works at all).
  speed -- time dilation.  Applied to the position step AND the age step
           together, so travel range is preserved and motion simply plays
           slower.

Vectorised when numpy is present, scalar otherwise.  Same numbers either way.
"""

try:
    import numpy as _np
    HAVE_NUMPY = True
except Exception:
    _np = None
    HAVE_NUMPY = False

__all__ = ["BilinearField"]


class BilinearField:
    """corners = (top_left, top_right, bottom_left, bottom_right)"""

    __slots__ = ("tl", "tr", "bl", "br", "w", "h", "enabled")

    def __init__(self, corners=(1.0, 1.0, 1.0, 1.0), w=1920, h=1080, enabled=True):
        self.tl, self.tr, self.bl, self.br = [float(c) for c in corners]
        self.w = float(max(1, w))
        self.h = float(max(1, h))
        self.enabled = bool(enabled)

    def resize(self, w, h):
        self.w = float(max(1, w))
        self.h = float(max(1, h))

    def at(self, x, y):
        """Scalar sample."""
        if not self.enabled:
            return 1.0
        u = x / self.w
        v = y / self.h
        u = 0.0 if u < 0.0 else (1.0 if u > 1.0 else u)
        v = 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)
        top = self.tl + (self.tr - self.tl) * u
        bot = self.bl + (self.br - self.bl) * u
        return top + (bot - top) * v

    def sample(self, xs, ys):
        """Vector sample -- the callable handed to MotePool.tick()."""
        if not self.enabled:
            if HAVE_NUMPY and hasattr(xs, "shape"):
                return _np.ones_like(xs)
            return 1.0
        if HAVE_NUMPY and hasattr(xs, "shape"):
            u = _np.clip(xs / self.w, 0.0, 1.0)
            v = _np.clip(ys / self.h, 0.0, 1.0)
            top = self.tl + (self.tr - self.tl) * u
            bot = self.bl + (self.br - self.bl) * u
            return top + (bot - top) * v
        return self.at(xs, ys)

    def __call__(self, xs, ys):
        return self.sample(xs, ys)

    def __repr__(self):
        return "BilinearField(tl=%.2f tr=%.2f bl=%.2f br=%.2f)" % (
            self.tl, self.tr, self.bl, self.br)
