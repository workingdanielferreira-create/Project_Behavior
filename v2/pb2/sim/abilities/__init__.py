"""Built-in ability plugins.

To add a mechanic: drop a module in this folder that uses @ability(...),
then import it here.  Nothing else in the engine changes.
"""
from . import library          # noqa: F401

__all__ = ["library"]
