@echo off
REM run-windows.bat -- Launch FlightGear + AI ATC sidecar (Windows)
REM
REM Run from the repo root or double-click in Explorer.
REM
REM Prerequisites:
REM   - FlightGear 2024.1.5+ installed; adjust FGFS_EXE below if not on PATH.
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

REM --- Auto-detect fgfs.exe path -------------------------------------------
REM 1) Use FGFS_EXE env var if set.
REM 2) Try fgfs.exe on PATH.
REM 3) Try FG 2024.1, then fall back to FG 2020, then give up.
if not defined FGFS_EXE (
    where fgfs.exe >nul 2>&1 && (
        set "FGFS_EXE=fgfs.exe"
    ) || (
        if exist "C:\Program Files\FlightGear 2024.1\bin\fgfs.exe" (
            set "FGFS_EXE=C:\Program Files\FlightGear 2024.1\bin\fgfs.exe"
        ) else if exist "C:\Program Files\FlightGear 2020\bin\fgfs.exe" (
            set "FGFS_EXE=C:\Program Files\FlightGear 2020\bin\fgfs.exe"
        ) else (
            set "FGFS_EXE=fgfs.exe"
        )
    )
)
set "ADDON_PATH=%REPO%\addon"
set "FG_TELNET_PORT=5501"
set "FG_HTTP_PORT=8080"
set "LOG_FILE=%REPO%\sidecar.log"
REM --------------------------------------------------------------------------

echo =^> Repo: %REPO%
echo =^> Addon: %ADDON_PATH%
echo =^> Using fgfs: %FGFS_EXE%

REM Verify executable exists before proceeding.
where "%FGFS_EXE%" >nul 2>&1 || if not exist "%FGFS_EXE%" (
    echo ERROR: FlightGear executable not found: %FGFS_EXE%
    echo        Install FlightGear or set FGFS_EXE=C:\path\to\fgfs.exe and re-run.
    pause
    exit /b 1
)

REM Launch FlightGear in a new window (so it can be closed separately).
REM --telnet=5501 : property/telnet server (--props=5501 is the legacy alias)
REM --httpd=8080  : HTTP property server
echo =^> Starting FlightGear...
start "FlightGear AI ATC" "%FGFS_EXE%" ^
    "--addon=%ADDON_PATH%" ^
    "--telnet=%FG_TELNET_PORT%" ^
    "--httpd=%FG_HTTP_PORT%" ^
    %*

REM Poll telnet port until open (PowerShell one-liner; timeout 120 s).
echo =^> Waiting for FlightGear telnet server on port %FG_TELNET_PORT%...
set "ELAPSED=0"
:poll_loop
powershell -NoProfile -Command ^
    "$tcp = New-Object System.Net.Sockets.TcpClient; try { $tcp.Connect('localhost',%FG_TELNET_PORT%); $tcp.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% == 0 goto telnet_ready
if %ELAPSED% GEQ 120 (
    echo ERROR: Timed out waiting for FlightGear telnet after 120 s.
    pause
    exit /b 1
)
timeout /t 2 /nobreak >nul
set /a ELAPSED+=2
goto poll_loop
:telnet_ready
echo     Telnet ready after %ELAPSED%s.

REM Launch the sidecar in this window, tee-ing output to sidecar.log.
echo =^> Starting sidecar (log: %LOG_FILE%)...
"%REPO%\.venv\Scripts\python.exe" -m sidecar.main 2>&1 | tee "%LOG_FILE%"

echo =^> Sidecar exited.
pause
