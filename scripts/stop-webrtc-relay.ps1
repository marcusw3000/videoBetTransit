$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pidPath = Join-Path $repoRoot "tools\\mediamtx\\mediamtx.pid"

if (-not (Test-Path $pidPath)) {
  Write-Host "PID do MediaMTX nao encontrado."
  exit 0
}

$pidValue = (Get-Content $pidPath -Raw).Trim()
if (-not $pidValue) {
  Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
  Write-Host "PID vazio. Arquivo removido."
  exit 0
}

$process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
if ($process) {
  Stop-Process -Id $pidValue -Force
  Write-Host "MediaMTX parado. PID $pidValue"
} else {
  Write-Host "Processo $pidValue nao estava em execucao."
}

Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
