@echo off
REM run-windows.bat -- Launch FlightGear + AI ATC sidecar (Windows)
REM
REM Run from the repo root or double-click in Explorer.
REM
REM Prerequisites:
REM   - FlightGear 2024.1.5+ installed; adjust FGFS_EXE below if needed.
REM   - Python venv created:
REM       python -m venv .venv
REM       .venv\Scripts\pip install -r requirements.txt
REM   - .env in the repo root containing: GEMINI_API_KEY=<your-key>
REM
REM Any extra arguments after this script are forwarded to fgfs.exe.

setlocal EnableDelayedExpansion

REM Change to the repo root (works when double-clicked from Explorer).
cd /d "%~dp0\.."
set "REPO=%CD%"

REM --- Configurable paths ---------------------------------------------------
REM Adjust FGFS_EXE if FlightGear is installed in a non-default location.
set "FGFS_EXE=fgfs.exe"
set "ADDON_PATH=%REPO%\addon"
set "FG_TELNET_PORT=5501"
set "FG_HTTP_PORT=8080"
REM --------------------------------------------------------------------------

echo =^> Repo: %REPO%
echo =^> Addon: %ADDON_PATH%

REM Launch FlightGear in a new window (so it can be closed separately).
REM --telnet=5501 : property/telnet server (--props=5501 is the legacy alias)
REM --httpd=8080  : HTTP property server
echo =^> Starting FlightGear...
start "FlightGear AI ATC" "%FGFS_EXE%" ^
    "--addon=%ADDON_PATH%" ^
    "--telnet=%FG_TELNET_PORT%" ^
    "--httpd=%FG_HTTP_PORT%" ^
    %*

REM Give FlightGear time to start its telnet server.
echo =^> Waiting 15 seconds for FlightGear telnet server...
timeout /t 15 /nobreak >nul

REM Launch the sidecar in this window (Ctrl-C stops it cleanly).
echo =^> Starting sidecar...
"%REPO%\.venv\Scripts\python.exe" -m sidecar.main

echo =^> Sidecar exited.
pause
