@echo off
REM ============================================================
REM  Double-click this file to launch the YouTube audio extractor.
REM  It makes sure yt-dlp is installed and up to date (YouTube
REM  changes often, and old yt-dlp versions stop working),
REM  then opens the GUI.
REM
REM  You can also pass links to skip the GUI:
REM    YouTube_Audio_Extractor.bat https://youtu.be/xxxx https://youtu.be/yyyy
REM ============================================================

cd /d "%~dp0"

SET logfile=youtube_audio_extractor.log

if "%~1"=="__main__" goto :main
echo Logging to %logfile%
if exist "%logfile%" powershell -NoProfile -Command "if ((Get-Item '%logfile%').Length -gt 1MB) { (Get-Content '%logfile%' -Tail 2000) | Set-Content '%logfile%' }"
cmd /c "%~f0" __main__ %* 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath '%logfile%' -Append"
exit /b %errorlevel%

:main
shift
echo ============================================================
echo Run started: %date% %time%
echo -------------------------------------------------------------

echo Checking dependencies (first run may take a minute)...
python -m pip install --quiet --disable-pip-version-check -U yt-dlp

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo.
    echo ffmpeg was not found on your PATH. Install it, e.g.:  winget install Gyan.FFmpeg
    pause
    exit /b 1
)

echo Launching YouTube audio extractor...
python -u "%~dp0youtube audio extractor.py" %1 %2 %3 %4 %5 %6 %7 %8 %9

if errorlevel 1 (
    echo.
    echo Something went wrong. Make sure Python is installed and on your PATH.
    pause
)
