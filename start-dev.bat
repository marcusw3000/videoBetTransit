@echo off
setlocal

cd /d "%~dp0"
set "D=%~dp0"
set "BACKEND_PORT=8080"
set "FRONTEND_PORT=5173"
set "WORKER_PORT=8090"
set "BACKEND_URL=http://127.0.0.1:%BACKEND_PORT%/rounds/current?cameraId=cam_001"
set "WORKER_URL=http://127.0.0.1:%WORKER_PORT%/health"

echo ============================================================
echo  TrafficCounter MVP - Inicializando sistema (start-dev)
echo  Backend : http://127.0.0.1:%BACKEND_PORT%
echo  Frontend: http://127.0.0.1:%FRONTEND_PORT%
echo  MediaMTX: http://127.0.0.1:9997
echo  Worker oficial: vision-worker\app.py
echo ============================================================
echo.

where dotnet >nul 2>&1 || (echo [ERRO] dotnet nao encontrado.& pause & exit /b 1)
where node >nul 2>&1 || (echo [ERRO] node nao encontrado.& pause & exit /b 1)
where python >nul 2>&1 || (echo [ERRO] python nao encontrado.& pause & exit /b 1)

if not exist "%D%.venv\Scripts\python.exe" (
  echo [ERRO] Ambiente virtual Python nao encontrado.
  pause
  exit /b 1
)

if not exist "%D%backend-dev.bat" (
  echo [ERRO] Launcher do backend nao encontrado.
  pause
  exit /b 1
)

if not exist "%D%frontend-dev.bat" (
  echo [ERRO] Launcher do frontend nao encontrado.
  pause
  exit /b 1
)

if not exist "%D%vision-worker-dev.bat" (
  echo [ERRO] Launcher do worker nao encontrado.
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
call :wait_for_backend
if errorlevel 1 (
  echo [ERRO] O backend nao respondeu em http://127.0.0.1:%BACKEND_PORT%.
  echo Verifique a janela [BACKEND] antes de continuar.
  pause
  exit /b 1
)
echo [OK] Backend respondeu com sucesso.

echo 2. Iniciando frontend...
start cmd /k "cd /d %D% && call frontend-dev.bat"

echo 3. Iniciando worker...
start cmd /k "cd /d %D% && call vision-worker-dev.bat"
call :wait_for_worker
if errorlevel 1 (
  echo [ERRO] O worker nao respondeu em http://127.0.0.1:%WORKER_PORT%/health.
  echo Verifique a janela [VISION] antes de continuar.
  pause
  exit /b 1
)
echo [OK] Worker respondeu com sucesso.

echo.
echo Sistema iniciado.
echo Use este arquivo enquanto o start.bat principal estiver em uso/bloqueado.
pause
exit /b 0

:wait_for_backend
call :wait_for_url "%BACKEND_URL%" 60 BACKEND
exit /b %ERRORLEVEL%

:wait_for_worker
call :wait_for_url "%WORKER_URL%" 60 VISION
exit /b %ERRORLEVEL%

:wait_for_url
setlocal
set "WAIT_URL=%~1"
set "WAIT_ATTEMPTS=%~2"
set "WAIT_LABEL=%~3"

for /L %%I in (1,1,%WAIT_ATTEMPTS%) do (
  powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing '%WAIT_URL%' -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }"
  if not errorlevel 1 (
    endlocal & exit /b 0
  )
  echo    [aguardando %WAIT_LABEL%] tentativa %%I/%WAIT_ATTEMPTS%...
  timeout /t 2 /nobreak >nul
)

endlocal & exit /b 1
