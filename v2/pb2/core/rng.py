"""Deterministic random.

v1 seeded each Personality from `os.urandom(8)`, which made runs
irreproducible unless the capture harness monkey-patched it.  v2 seeds
everything from the world seed, so a run is defined entirely by
(seed, input tape).  That is the precondition for the golden checksum test.

Never import `random` directly anywhere else in pb2.
"""

import hashlib
import random as _random

__all__ = ["Rng", "derive_seed"]


def derive_seed(root_seed, *parts):
    """Stable child seed from a root seed and any hashable path parts.

    derive_seed(42, "actor", 3, "personality") always gives the same number,
    on any machine, in any Python build (hashlib, not hash()).
    """
    h = hashlib.blake2b(digest_size=8)
    h.update(str(int(root_seed)).encode("utf-8"))
    for p in parts:
        h.update(b"\x00")
        h.update(str(p).encode("utf-8"))
    return int.from_bytes(h.digest(), "little")


class Rng:
    """Thin deterministic wrapper.  Exposes only the operations the engine
    actually needs, so no stray `random` call can sneak nondeterminism in."""

    __slots__ = ("_r", "seed", "calls")

    def __init__(self, seed):
        self.seed = int(seed)
        self._r = _random.Random(self.seed)
        self.calls = 0

    def child(self, *parts):
        return Rng(derive_seed(self.seed, *parts))

    def random(self):
        self.calls += 1
        return self._r.random()

    def uniform(self, a, b):
        self.calls += 1
        return self._r.uniform(a, b)

    def randint(self, a, b):
        self.calls += 1
        return self._r.randint(a, b)

    def chance(self, p):
        self.calls += 1
        return self._r.random() < p

    def choice(self, seq):
        self.calls += 1
        seq = list(seq)
        if not seq:
            return None
        return seq[self._r.randrange(len(seq))]

    def jitter(self, magnitude):
        """Symmetric jitter in [-magnitude, +magnitude]."""
        self.calls += 1
        return (self._r.random() * 2.0 - 1.0) * magnitude

    def reset(self, seed=None):
        if seed is not None:
            self.seed = int(seed)
        self._r = _random.Random(self.seed)
        self.calls = 0

    def __repr__(self):
        return "Rng(seed=%d calls=%d)" % (self.seed, self.calls)
