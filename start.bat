@echo off
echo Iniciando o sistema completo do Rodovia Market...

echo.
echo 1. Iniciando API .NET (Backend)...
start cmd /k "cd TrafficCounter.Api && title [BACKEND] .NET API && dotnet run"

echo.
echo 2. Iniciando React (Frontend)...
start cmd /k "cd traffic-counter-front && title [FRONTEND] React Vite && npm run dev"

echo.
echo 3. Iniciando Engine YOLO (Python)...
start cmd /k "title [ENGINE] Python YOLO && call .venv\Scripts\activate && python app.py"

echo.
echo Tudo iniciado! 3 janelas do terminal foram abertas.
echo Feche essas 3 novas janelas para desligar o sistema quando terminar.
pause
