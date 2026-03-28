@echo off
cd /d "%~dp0"
set "D=%~dp0"

echo ============================================================
echo  videoBetTransit - Validacao local
echo ============================================================
echo.

where dotnet >nul 2>&1
if errorlevel 1 (
    echo [ERRO] dotnet nao encontrado.
    exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo [ERRO] node nao encontrado.
    exit /b 1
)

if not exist "%D%.venv\Scripts\python.exe" (
    echo [ERRO] Python da .venv nao encontrado em %D%.venv\Scripts\python.exe
    exit /b 1
)

if not exist "%D%traffic-counter-front\package.json" (
    echo [ERRO] Frontend nao encontrado em %D%traffic-counter-front
    exit /b 1
)

echo [1/4] Validando sintaxe Python...
"%D%.venv\Scripts\python.exe" -m py_compile app.py backend_client.py manual_detection_smoke.py tests\test_engine_logic.py
if errorlevel 1 (
    echo [ERRO] Falha na validacao de sintaxe Python.
    exit /b 1
)
echo [OK] Sintaxe Python validada.
echo.

echo [2/4] Rodando testes Python...
"%D%.venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 (
    echo [ERRO] Falha nos testes Python.
    exit /b 1
)
echo [OK] Testes Python aprovados.
echo.

echo [3/4] Rodando testes da API .NET...
dotnet test TrafficCounter.Api.Tests\TrafficCounter.Api.Tests.csproj
if errorlevel 1 (
    echo [ERRO] Falha nos testes da API .NET.
    exit /b 1
)
echo [OK] Testes da API .NET aprovados.
echo.

echo [4/4] Gerando build do frontend...
pushd "%D%traffic-counter-front"
npm run build
if errorlevel 1 (
    popd
    echo [ERRO] Falha no build do frontend.
    exit /b 1
)
popd
echo [OK] Build do frontend aprovado.
echo.

echo ============================================================
echo  Validacao concluida com sucesso.
echo ============================================================
exit /b 0
