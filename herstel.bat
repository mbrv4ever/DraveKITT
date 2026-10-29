@echo off
rem === herstel.bat - verwijdert .venv, build en dist voor een schone herstart ===
setlocal
cd /d "%~dp0"
echo Dit verwijdert .venv, build en dist (de omgeving en de bouwresultaten).
echo Je instellingen en geheugen (DraveKITT-data) blijven staan.
pause
if exist ".venv" rmdir /s /q ".venv"
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
echo Klaar. Draai daarna Start-DraveKITT.bat of Maak-DraveKITT-EXE.bat opnieuw.
pause
endlocal
