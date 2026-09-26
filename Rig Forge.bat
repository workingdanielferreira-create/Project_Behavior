@echo off
rem Opens Rig Forge from this game folder. "Export character package" and pick
rem this game's characters folder; press F5 in the game to reload.
rem "Import package..." opens fx_packages\<name> (or any package folder) to edit
rem poses and add actions; export then writes back into that same folder.
start "" msedge "%~dp0tools\fx\rigforge.html" 2>nul || start "" "%~dp0tools\fx\rigforge.html"
