@echo off
rem Opens FX Studio 3D (V3): a character's actions on its 3D body, their FX (FX Studio's 2D anime FX laid in 3D:
rem side / flat / ground / billboard), where they start, their damage, and how the body moves through each action.
rem Pick the characters folder once (remembered); Save writes characters\<name>\<name>.fxkit.json.
rem Edge (or Chrome) can save into the folder; other browsers download a copy. run_v3.bat repacks the characters.
start "" msedge "%~dp0v3\tools\fxstudio3d.html" 2>nul || start "" "%~dp0v3\tools\fxstudio3d.html"
