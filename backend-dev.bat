@echo off
cd /d "%~dp0backend\TrafficCounter.Api"
title [BACKEND] .NET API :8080
set "ASPNETCORE_ENVIRONMENT=Development"
dotnet run --urls http://0.0.0.0:8080
