param(
    [string]$Username = 'admin',
    [ValidateSet('admin', 'player')][string]$Role = 'admin'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$apiDirectory = Join-Path $projectRoot 'backend/TrafficCounter.Api'
$accountsFile = Join-Path $apiDirectory 'appsettings.Local.json'
$workerFile = Join-Path $projectRoot 'vision-worker/config.json'
if (-not (Test-Path -LiteralPath $workerFile)) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'vision-worker/config.example.json') -Destination $workerFile
}
$config = if (Test-Path -LiteralPath $accountsFile) { Get-Content -Raw -LiteralPath $accountsFile | ConvertFrom-Json } else { [pscustomobject]@{} }
if (-not $config.PSObject.Properties['Security']) { $config | Add-Member -NotePropertyName Security -NotePropertyValue ([pscustomobject]@{}) }
if (-not $config.PSObject.Properties['ConnectionStrings']) { $config | Add-Member -NotePropertyName ConnectionStrings -NotePropertyValue ([pscustomobject]@{}) }
if ([string]::IsNullOrWhiteSpace([string]$config.ConnectionStrings.DefaultConnection)) {
    $config.ConnectionStrings | Add-Member -NotePropertyName DefaultConnection -NotePropertyValue 'Data Source=trafficcounter.db' -Force
}
if (-not $config.PSObject.Properties['DataProtection']) { $config | Add-Member -NotePropertyName DataProtection -NotePropertyValue ([pscustomobject]@{}) }
if ([string]::IsNullOrWhiteSpace([string]$config.DataProtection.KeyPath)) {
    $config.DataProtection | Add-Member -NotePropertyName KeyPath -NotePropertyValue '.auth-keys' -Force
}
$workerKey = $config.Security.BackendApiKey
if ([string]::IsNullOrWhiteSpace($workerKey) -or $workerKey -eq 'CHANGE_ME') {
    $keyBytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($keyBytes) } finally { $rng.Dispose() }
    $workerKey = [BitConverter]::ToString($keyBytes).Replace('-', '').ToLowerInvariant()
    $config.Security | Add-Member -NotePropertyName BackendApiKey -NotePropertyValue $workerKey -Force
}
$workerConfig = Get-Content -Raw -LiteralPath $workerFile | ConvertFrom-Json
$workerConfig | Add-Member -NotePropertyName api_key -NotePropertyValue $workerKey -Force
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText($accountsFile, ($config | ConvertTo-Json -Depth 100), $utf8)
[IO.File]::WriteAllText($workerFile, ($workerConfig | ConvertTo-Json -Depth 100), $utf8)
dotnet run --project $apiDirectory --no-launch-profile -- --create-user $Username --role $Role --accounts-file $accountsFile
if ($LASTEXITCODE -ne 0) { throw 'Falha ao configurar a conta.' }
Write-Host 'Credencial do worker sincronizada. Reinicie backend e worker para usar a configuracao.'
