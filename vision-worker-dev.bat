@echo off
setlocal

set "ROOT=%~dp0"
set "WORKER_DIR=%ROOT%vision-worker"
set "PYTHON_EXE=%ROOT%.venv\Scripts\python.exe"

title [VISION] Python Worker
cd /d "%WORKER_DIR%"

echo ============================================================
echo  TrafficCounter Vision Worker
echo  Diretorio: %WORKER_DIR%
echo  Python   : %PYTHON_EXE%
echo ============================================================
echo.

if not exist "%PYTHON_EXE%" (
  echo [ERRO] Python do ambiente virtual nao encontrado.
  echo Verifique %ROOT%.venv\Scripts\python.exe
  pause
  exit /b 1
)

"%PYTHON_EXE%" app.py
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo [ERRO] O worker foi encerrado com codigo %EXIT_CODE%.
echo Verifique a saida acima antes de fechar esta janela.
pause
exit /b %EXIT_CODE%
