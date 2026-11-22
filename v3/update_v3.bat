@echo off
rem Project Behavior V3 updater: updates v3\ (game + Rig Forge 3D), FX Studio runtime and
rem characters\ from GitHub, then asks: 1 = V3 game, 2 = Rig Forge 3D, Enter = nothing.
rem One block on purpose: the updater may rewrite this .bat while it runs.
cd /d "%~dp0"
(
  if exist "%~dp0..\python.exe" ("%~dp0..\python.exe" "%~dp0tools\update_v3.py") else (python "%~dp0tools\update_v3.py")
  pause
  exit /b
)
