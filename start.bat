@echo off
cd /d "%~dp0"
set "D=%~dp0"
set "BACKEND_PORT=8080"
set "FRONTEND_PORT=5173"
set "BACKEND_URL=http://localhost:%BACKEND_PORT%"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"
set "MODE=%~1"

if /I "%MODE%"=="" set "MODE=dev"
if /I "%MODE%"=="supabase" goto :run_supabase
if /I "%MODE%"=="dev" goto :run_dev

echo [ERRO] Modo invalido: %MODE%
echo Uso:
echo   start.bat
echo   start.bat dev
echo   start.bat supabase
pause
exit /b 1

:run_dev
echo ============================================================
echo  TrafficCounter MVP - Inicializando sistema (modo dev)
echo  Backend : %BACKEND_URL%
echo  Frontend: %FRONTEND_URL%
echo  OBS: Em modo dev o backend usa SQLite local.
echo       MediaMTX sera validado/iniciado automaticamente.
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

if not exist "%D%tools\mediamtx\mediamtx.exe" (
    where docker >nul 2>&1
    if errorlevel 1 (
        echo [ERRO] MediaMTX local nao encontrado e docker indisponivel.
        pause & exit /b 1
    )
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

echo Garantindo MediaMTX...
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort 9997 -State Listen -ErrorAction SilentlyContinue){ exit 0 } else { exit 1 }"
if errorlevel 1 (
    if exist "%D%tools\mediamtx\mediamtx.exe" (
        echo [INFO] MediaMTX nao esta ativo. Subindo binario local...
        start cmd /k "cd /d %D%tools\mediamtx && title [MEDIAMTX] :9997/:8554/:8888/:8889 && mediamtx.exe %D%mediamtx\mediamtx.yml"
    ) else (
        echo [INFO] MediaMTX nao esta ativo. Subindo via Docker Compose...
        docker compose -f "%D%infra\docker-compose.yml" up -d mediamtx
        if errorlevel 1 (
            echo [ERRO] Falha ao iniciar o MediaMTX.
            pause & exit /b 1
        )
    )
)
echo [OK] MediaMTX pronto.
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
start cmd /k "cd /d %D% && call backend-dev.bat"

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
echo  MediaMTX : http://localhost:9997
echo  Docs API : %BACKEND_URL%/streams
echo.
echo  Para Supabase, use: start.bat supabase
echo  Para stack local Docker: cd infra ^&^& docker compose up postgres mediamtx backend vision-worker frontend
echo  Para encerrar: feche as 3 janelas do terminal.
echo ============================================================
pause
exit /b 0

:run_supabase
echo ============================================================
echo  TrafficCounter MVP - Inicializando sistema (modo supabase)
echo  Backend : %BACKEND_URL%
echo  Frontend: %FRONTEND_URL%
echo  Compose : infra\docker-compose.supabase.yml
echo ============================================================
echo.

if not exist "%D%.env" (
    echo [ERRO] Arquivo .env nao encontrado na raiz do projeto.
    echo Copie .env.supabase.example para .env e preencha as variaveis.
    pause & exit /b 1
)

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERRO] docker nao encontrado. Instale o Docker Desktop.
    pause & exit /b 1
)

where dotnet >nul 2>&1
if errorlevel 1 (
    echo [ERRO] dotnet nao encontrado. Instale o .NET 8 SDK: https://dot.net
    pause & exit /b 1
)

echo [OK] Dependencias encontradas.
echo.

echo 1. Aplicando migrations no banco configurado no .env...
start cmd /k "cd /d %D%backend\TrafficCounter.Api && title [MIGRATIONS] Supabase EF && powershell -NoProfile -Command \"$env:ConnectionStrings__DefaultConnection = (Get-Content '%D%.env' | Where-Object { $_ -like 'SUPABASE_DB_URL=*' } | Select-Object -First 1).Substring(16); dotnet ef database update\""

echo 2. Subindo stack Docker com Supabase...
start cmd /k "cd /d %D%infra && title [STACK] Supabase Compose && docker compose -f docker-compose.supabase.yml --env-file ..\.env up --build"

echo.
echo ============================================================
echo  Inicializacao Supabase disparada.
echo  Aguarde a janela [STACK] concluir o build e subir os servicos.
echo  Variaveis: .env na raiz do projeto
echo  Guia     : SUPABASE_SETUP.md
echo ============================================================
pause
exit /b 0
