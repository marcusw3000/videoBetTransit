@echo off
cd /d "%~dp0"
set "D=%~dp0"
set "BACKEND_PORT=5000"
set "FRONTEND_PORT=5173"
set "MJPEG_PORT=8090"
set "BACKEND_URL=http://localhost:%BACKEND_PORT%"
set "FRONTEND_URL=http://localhost:%FRONTEND_PORT%"
set "MJPEG_URL=http://127.0.0.1:%MJPEG_PORT%/video_feed"
set "MJPEG_HEALTH_URL=http://127.0.0.1:%MJPEG_PORT%/health"

echo ============================================================
echo  Rodovia Market - Inicializando sistema
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
    echo   pip install -r requirements.txt
    pause & exit /b 1
)

if not exist "%D%traffic-counter-front\package.json" (
    echo [ERRO] Frontend nao encontrado em %D%traffic-counter-front
    pause & exit /b 1
)

echo [OK] Todos os pre-requisitos encontrados.
echo.

echo Validando estrutura local...
if exist "%D%traffic-counter-front\node_modules" (
    echo [OK] node_modules encontrado.
) else (
    echo [INFO] node_modules nao encontrado. O frontend vai instalar dependencias ao iniciar.
)

if exist "%D%.venv\Scripts\python.exe" (
    echo [OK] .venv encontrada.
) else (
    echo [ERRO] Python da .venv nao encontrado.
    pause & exit /b 1
)
echo.

echo Verificando portas...
powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort %BACKEND_PORT% -State Listen -ErrorAction SilentlyContinue){ exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo [ERRO] Porta %BACKEND_PORT% ja esta em uso. Backend nao sera iniciado.
    pause & exit /b 1
)

powershell -NoProfile -Command "if(Get-NetTCPConnection -LocalPort %MJPEG_PORT% -State Listen -ErrorAction SilentlyContinue){ exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo [ERRO] Porta %MJPEG_PORT% ja esta em uso. Engine/MJPEG nao sera iniciado.
    pause & exit /b 1
)

echo [OK] Portas principais livres.
echo.

echo Atualizando dependencias Python da engine...
call "%D%.venv\Scripts\activate.bat"
python -m pip install -r "%D%requirements.txt"
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias Python.
    pause & exit /b 1
)
echo [OK] Dependencias Python prontas.
echo.

if not exist "%D%logs" mkdir "%D%logs"

echo 1. Iniciando API .NET (Backend)...
start cmd /k "cd /d %D%TrafficCounter.Api && title [BACKEND] .NET API && set ASPNETCORE_ENVIRONMENT=Development && dotnet run"

echo 2. Iniciando React (Frontend)...
if exist "%D%traffic-counter-front\node_modules" (
    start cmd /k "cd /d %D%traffic-counter-front && title [FRONTEND] React Vite && npm run dev"
) else (
    echo    [INFO] node_modules ausente - rodando npm install ^(so na primeira vez^)...
    start cmd /k "cd /d %D%traffic-counter-front && title [FRONTEND] React Vite && npm install && npm run dev"
)

echo 3. Aguardando backend inicializar ^(5s^)...
timeout /t 5 /nobreak >nul

echo 4. Iniciando Engine YOLO (Python)...
start cmd /k "cd /d %D% && title [ENGINE] Python YOLO && call .venv\Scripts\activate && python app.py"

echo 5. Aguardando MJPEG inicializar ^(6s^)...
timeout /t 6 /nobreak >nul

echo 6. Testando health do MJPEG...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri '%MJPEG_HEALTH_URL%' -UseBasicParsing -TimeoutSec 5; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
    echo [AVISO] Health do MJPEG nao respondeu com sucesso em %MJPEG_HEALTH_URL%
) else (
    echo [OK] Health do MJPEG respondeu com sucesso.
)

echo.
echo ============================================================
echo  Tudo iniciado! 3 janelas abertas.
echo  Logs disponiveis em: %D%logs\
echo  Frontend: %FRONTEND_URL%
echo  Backend:  %BACKEND_URL%
echo  MJPEG:    %MJPEG_URL%
echo  Health:   %MJPEG_HEALTH_URL%
echo  Para encerrar: feche as 3 janelas do terminal.
echo ============================================================
pause
