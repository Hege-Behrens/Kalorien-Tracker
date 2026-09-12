@echo off
REM Meldet sich beim Mailserver an und trennt sofort wieder.
REM Es wird KEINE Mail verschickt - niemand bekommt eine Testnachricht.
cd /d "%~dp0.."
chcp 65001 >nul
python inventur.py zugang --mailtest
echo.
echo ----------------------------------------------------------------
pause
