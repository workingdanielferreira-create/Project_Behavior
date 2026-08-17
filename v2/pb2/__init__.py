"""Project Behavior V2.

Layering rule, enforced by import discipline:
    pb2.core      no dependencies at all
    pb2.sim       depends on core only          -- NO Qt
    pb2.brains    depends on core only          -- NO Qt
    pb2.content   depends on core + sim         -- NO Qt
    pb2.harness   depends on the above          -- NO Qt
    pb2.render    Qt
    pb2.app       Qt

Because the whole simulation is Qt-free it can be run, tested and
checksummed headless.  That is what makes the golden test possible.
"""

__version__ = "2.0.0"
__all__ = ["__version__"]
