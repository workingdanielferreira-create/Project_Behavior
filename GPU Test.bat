@echo off
rem GPU overlay test: checks whether this PC can run the game on a GPU canvas
rem (Skia on OpenGL in a see-through GLFW window) instead of the CPU painter.
rem Installs glfw + skia-python into THIS folder's Python (no admin rights),
rem runs about a minute, changes nothing in the game, and writes
rem gpu_test_result.txt here.  Paste that file to Claude.
cd /d "%~dp0"
"%~dp0python.exe" -c "import glfw, skia" 2>/dev/null && goto run
echo Installing the test libraries (glfw, skia-python) into this folder...
"%~dp0python.exe" -m pip --version >/dev/null 2>/dev/null || "%~dp0python.exe" "%~dp0get-pip.py"
"%~dp0python.exe" -m pip install glfw skia-python
"%~dp0python.exe" -c "import glfw, skia" 2>/dev/null && goto run
echo Adding the Microsoft C++ runtime files (also into this folder)...
"%~dp0python.exe" -m pip install msvc-runtime
"%~dp0python.exe" -c "import glfw, skia" || goto failed
:run
"%~dp0python.exe" "%~dp0tools\gputest\gpu_test.py"
pause
exit /b
:failed
echo.
echo The test libraries could not be installed or loaded. Copy the text above to Claude.
pause
