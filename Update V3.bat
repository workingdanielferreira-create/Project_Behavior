@echo off
rem Project Behavior V3 updater (same as v3\update_v3.bat): updates v3\ (game + Rig Forge 3D),
rem FX Studio runtime and characters\ from GitHub, then asks: 1 = V3 game, 2 = Rig Forge 3D, Enter = nothing.
rem One block on purpose: the updater may rewrite this .bat while it runs.
cd /d "%~dp0"
(
  if exist "%~dp0python.exe" ("%~dp0python.exe" "%~dp0v3\tools\update_v3.py") else (python "%~dp0v3\tools\update_v3.py")
  pause
  exit /b
)
