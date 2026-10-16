@echo off
rem SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
rem Build DTP Publisher as ONE file: dist-single\DTP Publisher.exe (no Python needed).
rem Easier to copy, but it unpacks itself each time it starts, so it opens a few
rem seconds slower than the folder made by build_exe.bat.
setlocal
cd /d "%~dp0"
if not exist ".venv-build\Scripts\python.exe" (
    python -m venv .venv-build || goto :failed
)
".venv-build\Scripts\python.exe" -m pip install -q -r requirements.txt pyinstaller==6.22.3 || goto :failed
".venv-build\Scripts\python.exe" packaging\make_icon.py || goto :failed
set DTP_ONEFILE=1
".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath dist-single --workpath build-single packaging\dtp_publisher.spec || goto :failed
copy /y "User Manual.pdf" "dist-single\" >nul || goto :failed
echo.
echo Checking the new program...
"dist-single\DTP Publisher.exe" --self-test=dist-single\self-test.json
if errorlevel 1 (
    echo The self-test FAILED - see dist-single\self-test.json
    pause
    exit /b 1
)
echo Self-test passed.
echo.
echo Done: dist-single\DTP Publisher.exe
echo       dist-single\User Manual.pdf
pause
exit /b 0

:failed
echo The build failed - see the messages above.
pause
exit /b 1
