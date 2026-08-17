@echo off
REM Optional. numpy raises the FX budget; V2 runs without it and produces
REM identical results either way.
setlocal
cd /d "%~dp0"
set "PY=%~dp0..\python.exe"
if not exist "%PY%" set "PY=python"
echo Installing numpy into the embedded runtime...
"%PY%" -m pip install numpy
echo.
"%PY%" -c "import numpy; print('numpy', numpy.__version__, 'OK')"
pause
endlocal
