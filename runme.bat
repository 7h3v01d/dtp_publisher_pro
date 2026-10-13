@echo off
rem SPDX-License-Identifier: Apache-2.0
rem DTP Publisher Pro - double-click to start. First run sets everything up.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Setting up DTP Publisher for the first time, please wait...
    python -m venv .venv || goto :nopython
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :failed
)
start "" ".venv\Scripts\pythonw.exe" run.py %*
exit /b 0

:nopython
echo Python 3.11 or newer is needed. Get it from https://www.python.org/downloads/
echo and tick "Add python.exe to PATH" during setup.
pause
exit /b 1

:failed
echo Could not install the required packages. Check the internet connection and try again.
pause
exit /b 1
