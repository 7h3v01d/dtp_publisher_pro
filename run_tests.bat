@echo off
rem SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
rem Run the test suite (creates/updates .venv with dev requirements).
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt
set QT_QPA_PLATFORM=offscreen
".venv\Scripts\python.exe" -m pytest -q %*
pause
