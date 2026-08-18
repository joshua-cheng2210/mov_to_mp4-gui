@echo on
REM ============================================================
REM  Double-click this file to launch the MOV -> MP4 converter.
REM  It makes sure the video engine (imageio-ffmpeg) is installed,
REM  then opens the GUI.
REM ============================================================

cd /d "%~dp0"

echo Checking dependencies (first run may take a minute)...
python -m pip install --quiet --disable-pip-version-check imageio-ffmpeg

echo Launching converter...
python "%~dp0mov_to_mp4.py"

if errorlevel 1 (
    echo.
    echo Something went wrong. Make sure Python is installed and on your PATH.
    pause
)
