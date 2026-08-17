"""Uniform spatial hash -- broadphase for collision.

v1 tested every figure against every projectile: O(figures x motes).  Fine at
8 x 16, fatal at 8 x 2000.  Bucketing by cell reduces candidate pairs to
roughly O(n).

Cells are keyed by integer (cx, cy).  Query returns candidates from the 3x3
neighbourhood, in ascending slot order so results are deterministic.
"""

__all__ = ["SpatialGrid"]


class SpatialGrid:
    __slots__ = ("cell", "_buckets")

    def __init__(self, cell=96):
        self.cell = int(cell)
        self._buckets = {}

    def clear(self):
        self._buckets.clear()

    def insert(self, ident, x, y):
        c = self.cell
        key = (int(x // c), int(y // c))
        b = self._buckets.get(key)
        if b is None:
            self._buckets[key] = [ident]
        else:
            b.append(ident)

    def insert_many(self, idents, xs, ys):
        for i, ident in enumerate(idents):
            self.insert(ident, xs[i], ys[i])

    def query(self, x, y, radius=0.0):
        """Candidate idents near (x, y).  Sorted -> deterministic."""
        c = self.cell
        span = int(radius // c) + 1
        cx, cy = int(x // c), int(y // c)
        out = []
        for gx in range(cx - span, cx + span + 1):
            for gy in range(cy - span, cy + span + 1):
                b = self._buckets.get((gx, gy))
                if b:
                    out.extend(b)
        out.sort()
        return out

    def stats(self):
        if not self._buckets:
            return {"cells": 0, "max": 0, "avg": 0.0}
        sizes = [len(b) for b in self._buckets.values()]
        return {"cells": len(sizes), "max": max(sizes),
                "avg": sum(sizes) / len(sizes)}
