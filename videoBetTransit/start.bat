@echo off
cd /d "%~dp0"
set "D=%~dp0"

echo Iniciando o sistema completo do Rodovia Market...

echo.
echo 1. Iniciando API .NET (Backend)...
start cmd /k "cd /d %D%TrafficCounter.Api && title [BACKEND] .NET API && dotnet run"

echo.
echo 2. Iniciando React (Frontend)...
start cmd /k "cd /d %D%traffic-counter-front && title [FRONTEND] React Vite && npm install && npm run dev"

echo.
echo 3. Iniciando Engine YOLO (Python)...
start cmd /k "cd /d %D% && title [ENGINE] Python YOLO && call .venv\Scripts\activate && python app.py"

echo.
echo Tudo iniciado! 3 janelas do terminal foram abertas.
echo Feche essas 3 novas janelas para desligar o sistema quando terminar.
pause
