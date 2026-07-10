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
    F7 / F8         add / remove a P1 figure
    1               cycle P1's character
    2               cycle P2's character (past the last one = P2 off);
                    fielding P2 starts a Battle in this same window
    Ctrl (tap)      toggle cursor collision
    Ctrl+Q          toggle follow-path vs chase
    Ctrl+R          toggle runaway
    Alt+Up          toggle attack/shoot mode
    Alt+Left/Right  cycle P1 behaviour mode (runner / swordsman / ...)
"""

import os
import sys

# Make the sibling `laser/` package importable regardless of launch directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from laser import main

if __name__ == "__main__":
    main()
