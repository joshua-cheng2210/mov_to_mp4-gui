@echo off
REM ============================================================
REM  Double-click this file to launch the MOV -> MP4 converter.
REM  It makes sure the video engine (imageio-ffmpeg) is installed,
REM  then opens the GUI.
REM ============================================================

cd /d "%~dp0"

SET logfile=mov_to_mp4.log

if "%~1"=="__main__" goto :main
echo Logging to %logfile%
cmd /c "%~f0" __main__ 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath '%logfile%' -Append"
@REM cmd /c "%~f0" __main__ 2>&1 | powershell -NoProfile -Command "$input >> '%logfile%'"
exit /b %errorlevel%

:main
echo ============================================================
echo python %0 %1 
echo Run started: %date% %time%
echo ============================================================

echo Checking dependencies (first run may take a minute for installing packages)...
python -m pip install --quiet --disable-pip-version-check imageio-ffmpeg

echo Launching converter...
python "%~dp0mov_to_mp4.py"

if errorlevel 1 (
    echo.
    echo Something went wrong. Make sure Python is installed and on your PATH.
    pause
)
