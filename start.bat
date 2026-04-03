@echo off
cd /d "%~dp0"
set "D=%~dp0"
set "BACKEND_PORT=8080"
set "FRONTEND_PORT=5173"
set "BACKEND_URL=http://localhost:%BACKEND_PORT%"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"

echo ============================================================
echo  TrafficCounter MVP - Inicializando sistema (modo dev)
echo  Backend : %BACKEND_URL%
echo  Frontend: %FRONTEND_URL%
echo  OBS: MediaMTX e PostgreSQL devem estar rodando separadamente
echo       (via Docker ou servico local)
echo ============================================================
echo.

echo Verificando pre-requisitos...

where dotnet >nul 2>&1
if errorlevel 1 (
    echo [ERRO] dotnet nao encontrado. Instale o .NET 8 SDK: https://dot.net
    pause & exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo [ERRO] node nao encontrado. Instale o Node.js: https://nodejs.org
    pause & exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] python nao encontrado. Instale o Python 3.10+
    pause & exit /b 1
)

if not exist "%D%.venv\Scripts\activate.bat" (
    echo [ERRO] Ambiente virtual Python nao encontrado.
    echo Execute primeiro:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r vision-worker\requirements.txt
    pause & exit /b 1
)

if not exist "%D%frontend\package.json" (
    echo [ERRO] Frontend nao encontrado em %D%frontend
    pause & exit /b 1
)

if not exist "%D%backend\TrafficCounter.Api\TrafficCounter.Api.csproj" (
    echo [ERRO] Backend nao encontrado em %D%backend\TrafficCounter.Api
    pause & exit /b 1
)

echo [OK] Pre-requisitos encontrados.
echo.

echo Verificando dependencias Python do vision-worker...
call "%D%.venv\Scripts\activate.bat"
python -m pip install -r "%D%vision-worker\requirements.txt" --quiet
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias Python.
    pause & exit /b 1
)
echo [OK] Dependencias Python prontas.
echo.

echo Verificando porta %BACKEND_PORT%...
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort %BACKEND_PORT% -State Listen -ErrorAction SilentlyContinue){ exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo [ERRO] Porta %BACKEND_PORT% ja esta em uso.
    pause & exit /b 1
)
echo [OK] Porta %BACKEND_PORT% livre.
echo.

if not exist "%D%logs" mkdir "%D%logs"

echo 1. Iniciando Backend .NET (porta %BACKEND_PORT%)...
start cmd /k "cd /d %D%backend\TrafficCounter.Api && title [BACKEND] .NET API :8080 && set ASPNETCORE_ENVIRONMENT=Development && dotnet run"

echo 2. Iniciando Frontend React (porta %FRONTEND_PORT%)...
if exist "%D%frontend\node_modules" (
    start cmd /k "cd /d %D%frontend && title [FRONTEND] React :5173 && npm run dev"
) else (
    echo    [INFO] node_modules ausente - instalando dependencias...
    start cmd /k "cd /d %D%frontend && title [FRONTEND] React :5173 && npm install && npm run dev"
)

echo 3. Aguardando backend inicializar (5s)...
timeout /t 5 /nobreak >nul

echo 4. Iniciando Vision Worker (Python)...
start cmd /k "cd /d %D%vision-worker && title [VISION] Python Worker && call %D%.venv\Scripts\activate && python app.py"

echo.
echo ============================================================
echo  Sistema iniciado! 3 janelas abertas.
echo  Frontend : %FRONTEND_URL%
echo  Backend  : %BACKEND_URL%
echo  Docs API : %BACKEND_URL%/streams
echo.
echo  Certifique-se que PostgreSQL e MediaMTX estejam rodando.
echo  Para subir via Docker: cd infra ^&^& docker compose up postgres mediamtx
echo  Para encerrar: feche as 3 janelas do terminal.
echo ============================================================
pause
