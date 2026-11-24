@echo off
rem Opens World Studio 3D (V3): the little planet V3 fights on - planet size, gravity, sky, atmosphere, ground cover,
rem landmarks, and the destructibles (pillars & boulders, ground damage, breakable scenery), each with its own on / off.
rem Pick the characters folder once (remembered); Save writes characters\world3d.json. run_v3.bat packs it for the game.
rem Edge (or Chrome) can save into the folder; other browsers download a copy.
start "" msedge "%~dp0v3\tools\worldstudio3d.html" 2>nul || start "" "%~dp0v3\tools\worldstudio3d.html"
