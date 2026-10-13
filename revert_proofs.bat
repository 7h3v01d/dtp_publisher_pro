@echo off
rem SPDX-License-Identifier: Apache-2.0
rem Re-break every fixed bug in a temp copy and check its regression test fails.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt
".venv\Scripts\python.exe" tools\revert_proofs.py
pause
