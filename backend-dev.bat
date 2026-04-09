@echo off
setlocal

set "ROOT=%~dp0"
set "API_DIR=%ROOT%backend\TrafficCounter.Api"
set "API_DLL=%API_DIR%\bin\Debug\net8.0\TrafficCounter.Api.dll"
set "API_URL=http://0.0.0.0:8080"

title [BACKEND] .NET API :8080
cd /d "%API_DIR%"
set "ASPNETCORE_ENVIRONMENT=Development"

echo ============================================================
echo  TrafficCounter Backend - modo Development
echo  Diretorio: %API_DIR%
echo  URL      : %API_URL%
echo  Banco    : SQLite local ^(appsettings.Development.json^)
echo ============================================================
echo.

if not exist "%API_DLL%" (
  echo [INFO] Build inicial nao encontrada. Compilando backend...
  dotnet build TrafficCounter.Api.csproj -p:UseAppHost=false
  if errorlevel 1 (
    echo [ERRO] Falha ao compilar o backend.
    pause
    exit /b 1
  )
)

echo [INFO] Iniciando API via DLL para evitar inconsistencias do dotnet run...
dotnet "%API_DLL%" --urls %API_URL%
set "EXIT_CODE=%ERRORLEVEL%"

echo.
echo [ERRO] O backend foi encerrado com codigo %EXIT_CODE%.
echo Verifique a saida acima antes de fechar esta janela.
pause
exit /b %EXIT_CODE%
