@echo off
setlocal

set "ROOT=%~dp0"
set "FRONTEND_DIR=%ROOT%frontend"

title [FRONTEND] React :5173
cd /d "%FRONTEND_DIR%"

echo ============================================================
echo  TrafficCounter Frontend
echo  Diretorio: %FRONTEND_DIR%
echo  URL      : http://127.0.0.1:5173
echo ============================================================
echo.

if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERRO] package.json do frontend nao encontrado.
  pause
  exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
  echo [INFO] node_modules ausente. Instalando dependencias...
  npm install
  if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias do frontend.
    pause
    exit /b 1
  )
)

echo [INFO] Iniciando Vite com config loader native para contornar erro local do Rolldown no Windows...
npm run dev -- --host 127.0.0.1 --configLoader native
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo [ERRO] O frontend foi encerrado com codigo %EXIT_CODE%.
echo Verifique a saida acima antes de fechar esta janela.
pause
exit /b %EXIT_CODE%
