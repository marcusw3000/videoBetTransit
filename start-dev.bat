@echo off
cd /d "%~dp0"
set "D=%~dp0"
set "BACKEND_PORT=8080"
set "FRONTEND_PORT=5173"

echo ============================================================
echo  TrafficCounter MVP - Inicializando sistema (start-dev)
echo  Backend : http://localhost:%BACKEND_PORT%
echo  Frontend: http://localhost:%FRONTEND_PORT%
echo  MediaMTX: http://localhost:9997
echo  Worker oficial: vision-worker\app.py
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

if not exist "%D%tools\mediamtx\mediamtx.exe" (
  where docker >nul 2>&1 || (echo [ERRO] MediaMTX local nao encontrado e docker indisponivel.& pause & exit /b 1)
)

echo 0. Garantindo MediaMTX...
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 9997 -State Listen -ErrorAction SilentlyContinue){ exit 0 } else { exit 1 }"
if errorlevel 1 (
  if exist "%D%tools\mediamtx\mediamtx.exe" (
    echo    [INFO] MediaMTX nao esta ativo. Subindo binario local...
    start cmd /k "cd /d %D%tools\mediamtx && title [MEDIAMTX] :9997/:8554/:8888/:8889 && mediamtx.exe %D%mediamtx\mediamtx.yml"
  ) else (
    echo    [INFO] MediaMTX nao esta ativo. Subindo via Docker Compose...
    docker compose -f "%D%infra\docker-compose.yml" up -d mediamtx
    if errorlevel 1 (
      echo [ERRO] Falha ao iniciar o MediaMTX.
      pause
      exit /b 1
    )
  )
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
