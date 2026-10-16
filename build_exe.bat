@echo off
rem SPDX-License-Identifier: LicenseRef-Restricted-Use-1.1
rem Build a stand-alone Windows program in dist\DTP Publisher\ (no Python needed to run it).
rem Copy that whole folder to the other PC and double-click "DTP Publisher.exe".
rem (For a single .exe file instead, use build_onefile.bat.)
setlocal
cd /d "%~dp0"
if not exist ".venv-build\Scripts\python.exe" (
    python -m venv .venv-build || goto :failed
)
".venv-build\Scripts\python.exe" -m pip install -q -r requirements.txt pyinstaller==6.22.3 || goto :failed
".venv-build\Scripts\python.exe" packaging\make_icon.py || goto :failed
".venv-build\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\dtp_publisher.spec || goto :failed
rem the printable manual goes next to the program, where it's easy to find
copy /y "User Manual.pdf" "dist\DTP Publisher\" >nul || goto :failed
echo Checking the new program...
"dist\DTP Publisher\DTP Publisher.exe" --self-test=dist\self-test.json
if errorlevel 1 (
    echo The self-test FAILED - see dist\self-test.json
    pause
    exit /b 1
)
echo Self-test passed.
echo.
echo Done: dist\DTP Publisher\DTP Publisher.exe
echo       dist\DTP Publisher\User Manual.pdf
pause
exit /b 0

:failed
echo The build failed - see the messages above.
pause
exit /b 1
