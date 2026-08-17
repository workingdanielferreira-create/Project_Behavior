"""Entry point.  `python -m pb2.app.main [p1] [p2]`"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CHARS = os.path.join(ROOT, "characters")


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    p1 = argv[0] if argv else "runner"
    p2 = argv[1] if len(argv) > 1 else "swordsman"
    seed = int(argv[2]) if len(argv) > 2 else None
    strict = "--strict" in argv
    from .overlay import run
    return run(CHARS, p1=p1, p2=p2, seed=seed, strict=strict)


if __name__ == "__main__":
    sys.exit(main())
