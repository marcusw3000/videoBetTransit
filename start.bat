@echo off
cd /d "%~dp0"
set "D=%~dp0"

echo ============================================================
echo  Rodovia Market - Inicializando sistema
echo ============================================================
echo.

:: Verificar pre-requisitos
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

echo [OK] Todos os pre-requisitos encontrados.
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

:: Criar pasta de logs
if not exist "%D%logs" mkdir "%D%logs"

:: 1. Backend .NET
echo 1. Iniciando API .NET (Backend)...
start cmd /k "cd /d %D%TrafficCounter.Api && title [BACKEND] .NET API && dotnet run"

:: 2. Frontend React
echo 2. Iniciando React (Frontend)...
if exist "%D%traffic-counter-front\node_modules" (
    start cmd /k "cd /d %D%traffic-counter-front && title [FRONTEND] React Vite && npm run dev"
) else (
    echo    [INFO] node_modules ausente - rodando npm install ^(so na primeira vez^)...
    start cmd /k "cd /d %D%traffic-counter-front && title [FRONTEND] React Vite && npm install && npm run dev"
)

:: 3. Engine YOLO - aguarda backend subir (5s)
echo 3. Aguardando backend inicializar ^(5s^)...
timeout /t 5 /nobreak >nul
echo 3. Iniciando Engine YOLO (Python)...
start cmd /k "cd /d %D% && title [ENGINE] Python YOLO && call .venv\Scripts\activate && python app.py"

echo.
echo ============================================================
echo  Tudo iniciado! 3 janelas abertas.
echo  Logs disponiveis em: %D%logs\
echo  Feed MJPEG: http://127.0.0.1:8090/video_feed
echo  Para encerrar: feche as 3 janelas do terminal.
echo ============================================================
pause
