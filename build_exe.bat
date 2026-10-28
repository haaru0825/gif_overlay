@echo off
REM Windows: double-click to build dist\GifOverlay.exe (calls build.py)
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo Install from https://www.python.org/downloads/ and check "Add python.exe to PATH".
    pause
    exit /b 1
)

python build.py
if errorlevel 1 (
    echo [ERROR] Build failed. Check the messages above.
    pause
    exit /b 1
)

echo Output: %~dp0dist\GifOverlay.exe
pause
