@echo off
REM Der komplette Tageslauf: Verkaeufe abbuchen, Bericht versenden.
REM Das ist derselbe Befehl, den die Aufgabenplanung nachts ausfuehrt.
REM
REM ACHTUNG: Dieser Lauf BUCHT ins Bewegungsjournal. Er darf erst benutzt
REM werden, wenn die Cloud-Routinen abgeschaltet sind - sonst buchen zwei
REM Stellen dieselben Verkaeufe in zwei getrennte Journale.
cd /d "%~dp0.."
chcp 65001 >nul
python inventur.py vensoft
if errorlevel 1 goto fehler
python inventur.py tagesbericht --mail
if errorlevel 1 goto fehler
echo.
echo Fertig.
goto ende
:fehler
echo.
echo FEHLGESCHLAGEN - siehe Meldung oben.
:ende
echo ----------------------------------------------------------------
pause
