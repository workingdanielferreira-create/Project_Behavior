"""
Tiny 2D math + collision helpers, dependency-free.

Kept deliberately small and allocation-light: these run in the per-tick hot
path, so they return plain tuples/floats rather than wrapper objects.
"""

import math


def dist_sq(ax, ay, bx, by):
    dx = ax - bx
    dy = ay - by
    return dx * dx + dy * dy


def dist(ax, ay, bx, by):
    return dist_sq(ax, ay, bx, by) ** 0.5


def normalise(dx, dy):
    """Unit vector of (dx, dy); returns (1, 0) for a zero vector."""
    d = (dx * dx + dy * dy) ** 0.5
    if d < 1e-6:
        return 1.0, 0.0
    return dx / d, dy / d


def reflect(vx, vy, nx, ny):
    """Reflect velocity (vx, vy) about unit normal (nx, ny)."""
    dot = vx * nx + vy * ny
    return vx - 2.0 * dot * nx, vy - 2.0 * dot * ny


def angle_deg_qt(dx, dy):
    """Direction of (dx, dy) in Qt arc convention (CCW from +X, Y flipped)."""
    return math.degrees(math.atan2(-dy, dx))


def angle_diff(a, b):
    """Smallest signed difference a-b, normalised to (-180, 180]."""
    return (a - b + 180.0) % 360.0 - 180.0
