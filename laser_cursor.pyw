"""
laser_cursor launcher.

Keep this file (and the sprite PNGs) at the project root, alongside the `laser/`
package folder.  Double-click with pythonw, or run `pythonw laser_cursor.pyw`.

    project_root/
        laser_cursor.pyw      <- this file
        laser/                <- the package
        Picture*.png, standing*.png, swordrun*.png, ...   <- sprite assets

Controls:
    Ctrl+Alt+Enter  quit
    F9              toggle figures on/off
    Ctrl+Shift+.    start menu (character select: slots, teams, tag, hotkeys);
                    launching with --prebattle (the updaters) opens it first
    F7 / F8         add / remove an extra P1 figure (outside the slots)
    1 / 2 / 3 / 4   field / cycle / retire slot A / B / C / D's character
                    (default; set per slot in the start menu).  Fielding a
                    Team 2 fighter starts a Battle in this same window
    Ctrl+1..4       that slot's ultimate (default)
    Ctrl+Shift+1..4 that slot's attack_special (default)
    Alt+1..4        tag that slot in (tag pairs, default)
    Ctrl (tap)      toggle cursor collision
    Ctrl+Q          toggle follow-path vs chase
    Ctrl+R          toggle runaway
    Alt+Up          toggle attack/shoot mode
    Alt+Left/Right  cycle Team 1's first fighter (runner / swordsman / ...)
"""

import os
import sys

# Make the sibling `laser/` package importable regardless of launch directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from laser import main

if __name__ == "__main__":
    main()
