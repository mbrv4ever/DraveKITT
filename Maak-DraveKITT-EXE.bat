@echo off
rem === Maak-DraveKITT-EXE.bat - bouwt dist\DraveKITT\DraveKITT.exe ===
setlocal
cd /d "%~dp0"

set PY=
for %%V in (3.13 3.12 3.11 3.10) do (
  if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V" )
)
if not defined PY ( py -3 -c "import sys" >nul 2>&1 && set "PY=py -3" )
if not defined PY ( python -c "import sys" >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo Geen geschikte Python gevonden. Installeer Python 3.10-3.13 van python.org
  pause
  exit /b 1
)

if not exist ".venv" (
  echo Eenmalige installatie van de omgeving...
  %PY% -m venv .venv
)
rem Altijd de Python van KITT zelf gebruiken (activate.bat kan naar een oude map wijzen)
set "VPY=%~dp0.venv\Scripts\python.exe"
if not exist "%VPY%" (
  echo De KITT-omgeving .venv werkt niet. Verwijder de map .venv en start opnieuw.
  pause
  exit /b 1
)

"%VPY%" -m pip install --upgrade pip
rem llama-cpp-python als kant-en-klare AVX2-wheel (de cpu/standaard crasht op
rem sommige CPU's met "illegal instruction"; AVX2 werkt o.a. op Ryzen 5 3600)
"%VPY%" -m pip install --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/avx2 llama-cpp-python
if errorlevel 1 "%VPY%" -m pip install --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/basic llama-cpp-python
"%VPY%" -m pip install -r requirements.txt
"%VPY%" -m pip install pyinstaller

rem KITT's geheugen + model (DraveKITT-data) veilig opzij zetten: PyInstaller
rem maakt dist\DraveKITT bij elke bouw helemaal leeg.
set "BEWAAR=%~dp0_bewaar_DraveKITT-data"
if exist "dist\DraveKITT\DraveKITT-data" (
  echo KITT-data veilig opzij zetten...
  if exist "%BEWAAR%" rmdir /s /q "%BEWAAR%"
  move "dist\DraveKITT\DraveKITT-data" "%BEWAAR%" >nul
)

echo.
echo === Bouwen met PyInstaller... dit kan een paar minuten duren ===
"%VPY%" -m PyInstaller --noconfirm DraveKITT.spec
set "FOUT=%errorlevel%"

if exist "%BEWAAR%" (
  echo KITT-data terugzetten...
  if not exist "dist\DraveKITT" mkdir "dist\DraveKITT"
  move "%BEWAAR%" "dist\DraveKITT\DraveKITT-data" >nul
)
if not "%FOUT%"=="0" goto mislukt
if not exist "dist\DraveKITT\DraveKITT.exe" goto mislukt

echo.
echo KLAAR! De app staat in:  dist\DraveKITT\DraveKITT.exe
echo De stem, het Whisper- en het taalmodel downloaden zichzelf bij de EERSTE
echo start naar dist\DraveKITT\DraveKITT-data (eenmalig, kan even duren).
echo.
pause
endlocal
exit /b 0

:mislukt
echo.
echo MISLUKT - kijk hierboven voor de fout. KITT-data is teruggezet.
pause
endlocal
exit /b 1
