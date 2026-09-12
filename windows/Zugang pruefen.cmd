@echo off
REM Zeigt, ob die Zugangsdaten gefunden werden
REM
REM Wechselt zuerst in den Ordner dieser Datei - sonst sucht Python das
REM Programm dort, wo der Explorer gerade steht, und findet nichts.
cd /d "%~dp0.."
chcp 65001 >nul
python inventur.py zugang
echo.
echo ----------------------------------------------------------------
pause
