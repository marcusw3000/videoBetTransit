param(
    [switch]$CheckRunning,
    [switch]$RequireExistingDataProtectionKeys
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$api = Join-Path $root 'backend/TrafficCounter.Api'
$worker = Join-Path $root 'vision-worker'
$failures = [System.Collections.Generic.List[string]]::new()
function Require([bool]$condition, [string]$message) { if (-not $condition) { $failures.Add($message) } }

foreach ($command in 'dotnet', 'node') { Require ([bool](Get-Command $command -ErrorAction SilentlyContinue)) "Comando ausente: $command" }
Require (Test-Path -LiteralPath (Join-Path $root '.venv/Scripts/python.exe')) 'Python da .venv ausente.'
Require (Test-Path -LiteralPath (Join-Path $root 'frontend/package-lock.json')) 'frontend/package-lock.json ausente.'
Require (Test-Path -LiteralPath (Join-Path $api 'appsettings.Local.json')) 'Execute scripts/configure-local.ps1 para criar appsettings.Local.json.'
Require (Test-Path -LiteralPath (Join-Path $worker 'config.json')) 'Execute scripts/configure-local.ps1 para criar vision-worker/config.json.'

if ($failures.Count -eq 0) {
    try {
        $local = Get-Content -Raw -LiteralPath (Join-Path $api 'appsettings.Local.json') | ConvertFrom-Json
        $workerConfig = Get-Content -Raw -LiteralPath (Join-Path $worker 'config.json') | ConvertFrom-Json
        $key = [Environment]::GetEnvironmentVariable('Security__BackendApiKey')
        if ([string]::IsNullOrWhiteSpace($key)) { $key = [string]$local.Security.BackendApiKey }
        $workerKey = [Environment]::GetEnvironmentVariable('BACKEND_API_KEY')
        if ([string]::IsNullOrWhiteSpace($workerKey)) { $workerKey = [Environment]::GetEnvironmentVariable('API_KEY') }
        if ([string]::IsNullOrWhiteSpace($workerKey)) { $workerKey = [string]$workerConfig.api_key }
        Require (-not [string]::IsNullOrWhiteSpace($key) -and $key -ne 'CHANGE_ME') 'BackendApiKey ausente ou padrao.'
        Require ($key -eq $workerKey) 'A chave efetiva do worker nao corresponde a do backend.'
        Require (@($local.Auth.Users).Count -gt 0) 'Nenhuma conta local configurada.'
        Require (@($local.Auth.Users | Where-Object { $_.Role -eq 'admin' -and -not [string]::IsNullOrWhiteSpace($_.PasswordHash) }).Count -gt 0) 'Nenhuma conta admin valida configurada.'
        $connection = [Environment]::GetEnvironmentVariable('ConnectionStrings__DefaultConnection')
        if ([string]::IsNullOrWhiteSpace($connection)) { $connection = [string]$local.ConnectionStrings.DefaultConnection }
        Require (-not [string]::IsNullOrWhiteSpace($connection) -and $connection -notmatch 'CHANGE_ME|YOUR_PROJECT') 'ConnectionStrings:DefaultConnection ausente ou com placeholder.'
        $keyPath = [Environment]::GetEnvironmentVariable('DataProtection__KeyPath')
        if ([string]::IsNullOrWhiteSpace($keyPath)) { $keyPath = [string]$local.DataProtection.KeyPath }
        Require (-not [string]::IsNullOrWhiteSpace($keyPath)) 'DataProtection:KeyPath ausente.'
        $resolvedKeyPath = if ([IO.Path]::IsPathRooted($keyPath)) { $keyPath } else { Join-Path $api $keyPath }
        if ($RequireExistingDataProtectionKeys) {
            Require ((Test-Path -LiteralPath $resolvedKeyPath) -and @((Get-ChildItem -LiteralPath $resolvedKeyPath -File -ErrorAction SilentlyContinue)).Count -gt 0) 'Chaves persistidas de Data Protection ausentes.'
        }
        Require (-not [string]::IsNullOrWhiteSpace([string]$workerConfig.snapshot_dir)) 'snapshot_dir do worker ausente.'
    } catch { $failures.Add("Configuracao local invalida: $($_.Exception.Message)") }
}

if ($CheckRunning) {
    foreach ($endpoint in 'http://127.0.0.1:8080/health', 'http://127.0.0.1:8090/health') {
        try { $null = Invoke-WebRequest -UseBasicParsing $endpoint -TimeoutSec 3 }
        catch {
            $status = if ($null -ne $_.Exception.Response) { [int]$_.Exception.Response.StatusCode } else { 0 }
            if ($status -lt 400 -or $status -ge 500) { $failures.Add("Servico nao respondeu: $endpoint") }
        }
    }
}

if ($failures.Count -gt 0) { $failures | ForEach-Object { Write-Error $_ }; exit 1 }
Write-Host 'Instalacao local aprovada.'
