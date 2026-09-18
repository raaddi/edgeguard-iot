@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Brak srodowiska .venv. Wykonaj instalacje opisana w README.md.
    exit /b 1
)
pushd "%~dp0"
if errorlevel 1 exit /b 1
"%~dp0.venv\Scripts\python.exe" -m simulator.desktop %*
set "laboratoryExitCode=%errorlevel%"
popd
exit /b %laboratoryExitCode%
