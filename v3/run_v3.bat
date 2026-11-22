@echo off
REM ===================================================================
REM  Project Behavior V3  -  opens the game in its own app window
REM  (Edge or Chrome "app mode": no address bar or tabs, own taskbar
REM  icon, F11 = fullscreen, Alt+F4 = quit).  Nothing to install.
REM  The window keeps its own profile in v3\.window-profile so saved
REM  settings / teams stay put and it never joins your normal browser.
REM ===================================================================
setlocal
set "HERE=%~dp0"
set "PAGE=%HERE%index.html"
set "URL=file:///%PAGE:\=/%"
set "PROFILE=%HERE%.window-profile"

set "BROWSER="
for %%B in (
  "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
  "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
  "%LocalAppData%\Microsoft\Edge\Application\msedge.exe"
  "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  "%LocalAppData%\Google\Chrome\Application\chrome.exe"
) do if not defined BROWSER if exist %%B set "BROWSER=%%~B"

if not defined BROWSER (
  echo Edge / Chrome not found - opening in your default browser instead.
  start "" "%PAGE%"
  goto :eof
)

start "" "%BROWSER%" --app="%URL%" --user-data-dir="%PROFILE%" --window-size=1600,900 --no-first-run --no-default-browser-check --autoplay-policy=no-user-gesture-required
endlocal
