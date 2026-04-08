@echo off
cd /d "%~dp0"
set "LEGACY_ROOT=%~dp0"
set "REPO_ROOT=%LEGACY_ROOT%.."

echo ============================================================
echo  Inicializador legado aposentado
echo  Fluxo oficial: %REPO_ROOT%\start.bat
echo  Worker oficial: %REPO_ROOT%\vision-worker\app.py
echo ============================================================
echo.

call "%REPO_ROOT%\start.bat" dev
