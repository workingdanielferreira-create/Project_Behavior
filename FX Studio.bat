@echo off
rem Opens FX Studio from this game folder. Use "Open character folder" and pick
rem characters\<name>; "Save FX to folder" then writes straight into the game.
rem Edge (or Chrome) can save into folders; press F5 in the game to reload.
start "" msedge "%~dp0tools\fx\studio\fx_studio.html" 2>nul || start "" "%~dp0tools\fx\studio\fx_studio.html"
