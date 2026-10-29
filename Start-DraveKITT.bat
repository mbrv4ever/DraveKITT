@echo off
rem === Start-DraveKITT.bat - zet de omgeving op en start de voice box ===
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
call ".venv\Scripts\activate.bat"

python -m pip install --upgrade pip >nul 2>&1
rem llama-cpp-python eerst als kant-en-klare wheel (anders probeert pip te bouwen)
python -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python -m pip install -r requirements.txt

echo.
echo Brein: standaard draait het model IN de app (geen Ollama nodig). De eerste
echo keer wordt een klein modelbestand (~2 GB) gedownload naar DraveKITT-data.
echo Zie README.txt om over te schakelen naar Ollama.
echo.
python DraveKITT.py

pause
endlocal
