@echo off
cd /d "%~dp0"
set "D=%~dp0"
set "BACKEND_PORT=8080"
set "FRONTEND_PORT=5173"

echo ============================================================
echo  TrafficCounter MVP - Inicializando sistema (start-dev)
echo  Backend : http://localhost:%BACKEND_PORT%
echo  Frontend: http://localhost:%FRONTEND_PORT%
echo ============================================================
echo.

where dotnet >nul 2>&1 || (echo [ERRO] dotnet nao encontrado.& pause & exit /b 1)
where node >nul 2>&1 || (echo [ERRO] node nao encontrado.& pause & exit /b 1)
where python >nul 2>&1 || (echo [ERRO] python nao encontrado.& pause & exit /b 1)

if not exist "%D%.venv\Scripts\activate.bat" (
  echo [ERRO] Ambiente virtual Python nao encontrado.
  pause
  exit /b 1
)

if not exist "%D%backend\TrafficCounter.Api\TrafficCounter.Api.csproj" (
  echo [ERRO] Backend nao encontrado.
  pause
  exit /b 1
)

if not exist "%D%frontend\package.json" (
  echo [ERRO] Frontend nao encontrado.
  pause
  exit /b 1
)

echo 1. Iniciando backend local...
start cmd /k "cd /d %D% && call backend-dev.bat"

echo 2. Iniciando frontend...
if exist "%D%frontend\node_modules" (
  start cmd /k "cd /d %D%frontend && title [FRONTEND] React :5173 && npm run dev"
) else (
  start cmd /k "cd /d %D%frontend && title [FRONTEND] React :5173 && npm install && npm run dev"
)

echo 3. Iniciando worker...
start cmd /k "cd /d %D%vision-worker && title [VISION] Python Worker && call %D%.venv\Scripts\activate && python app.py"

echo.
echo Sistema iniciado.
echo Use este arquivo enquanto o start.bat principal estiver em uso/bloqueado.
pause
