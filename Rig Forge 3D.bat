@echo off
rem Opens Rig Forge 3D (V3): pose a character's .glb with X/Y/Z rings, move / add FX anchors,
rem set its placement, then "Save into .glb" writes straight back into characters\<name>\<name>.glb.
rem Edge can save into the file you opened; other browsers download a copy instead.
start "" msedge "%~dp0v3\tools\rigforge3d.html" 2>nul || start "" "%~dp0v3\tools\rigforge3d.html"
