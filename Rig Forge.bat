@echo off
rem Opens Rig Forge from this game folder. "Export character package" and pick
rem this game's characters folder; press F5 in the game to reload.
start "" msedge "%~dp0tools\fx\rigforge.html" 2>nul || start "" "%~dp0tools\fx\rigforge.html"
