param(
    [Parameter(Mandatory)][string]$Destination,
    [switch]$IncludeSnapshots,
    [switch]$ConfirmStopped
)

$ErrorActionPreference = 'Stop'
if (-not $ConfirmStopped) { throw 'Pare backend e worker e repita com -ConfirmStopped para congelar configuracoes e imagens durante o backup.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$api = Join-Path $root 'backend/TrafficCounter.Api'
$worker = Join-Path $root 'vision-worker'
$python = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python da .venv ausente.' }

function Read-Json([string]$path) {
    if (Test-Path -LiteralPath $path) { return Get-Content -Raw -LiteralPath $path | ConvertFrom-Json }
    return $null
}
function Resolve-InProject([string]$base, [string]$configuredPath, [string]$label) {
    if ([string]::IsNullOrWhiteSpace($configuredPath)) { throw "Caminho ausente: $label" }
    $candidate = if ([IO.Path]::IsPathRooted($configuredPath)) { [IO.Path]::GetFullPath($configuredPath) } else { [IO.Path]::GetFullPath((Join-Path $base $configuredPath)) }
    $prefix = $root.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    if (-not $candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { throw "$label deve permanecer dentro do projeto para uma restauracao portavel: $candidate" }
    return $candidate
}
function Relative-ToRoot([string]$path) { return [IO.Path]::GetRelativePath($root, $path).Replace('\','/') }

$local = Read-Json (Join-Path $api 'appsettings.Local.json')
$development = Read-Json (Join-Path $api 'appsettings.Development.json')
$workerConfig = Read-Json (Join-Path $worker 'config.json')
if ($null -eq $local -or $null -eq $workerConfig) { throw 'Configuracoes locais ausentes. Execute scripts/configure-local.ps1.' }
$connection = [Environment]::GetEnvironmentVariable('ConnectionStrings__DefaultConnection')
if ([string]::IsNullOrWhiteSpace($connection)) { $connection = [string]$local.ConnectionStrings.DefaultConnection }
if ([string]::IsNullOrWhiteSpace($connection) -and $null -ne $development) { $connection = [string]$development.ConnectionStrings.DefaultConnection }
$connectionBuilder = [System.Data.Common.DbConnectionStringBuilder]::new()
$connectionBuilder.ConnectionString = $connection
if (-not $connectionBuilder.ContainsKey('Data Source')) { throw 'Este script cobre SQLite. Use o procedimento nativo do banco configurado para PostgreSQL.' }
$database = Resolve-InProject $api ([string]$connectionBuilder['Data Source']) 'Banco SQLite'
$outboxSetting = [Environment]::GetEnvironmentVariable('EVENT_OUTBOX_PATH')
if ([string]::IsNullOrWhiteSpace($outboxSetting)) { $outboxSetting = 'data/events.sqlite3' }
$outbox = Resolve-InProject $worker $outboxSetting 'Outbox'
$keySetting = [Environment]::GetEnvironmentVariable('DataProtection__KeyPath')
if ([string]::IsNullOrWhiteSpace($keySetting)) { $keySetting = [string]$local.DataProtection.KeyPath }
$keys = Resolve-InProject $api $keySetting 'Chaves de Data Protection'
$snapshots = if ([string]::IsNullOrWhiteSpace([string]$workerConfig.snapshot_dir)) { $null } else { Resolve-InProject $worker ([string]$workerConfig.snapshot_dir) 'Snapshots' }

if (-not (Test-Path -LiteralPath $Destination)) { New-Item -ItemType Directory -Force -Path $Destination | Out-Null }
$destinationRoot = Join-Path (Resolve-Path $Destination).Path ('videobet-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
foreach ($directory in @($keys, $snapshots) | Where-Object { $null -ne $_ }) {
    $directoryPrefix = $directory.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    if ($destinationRoot.StartsWith($directoryPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'O destino do backup nao pode ficar dentro de um diretorio copiado.' }
}
New-Item -ItemType Directory -Path $destinationRoot | Out-Null
$manifestItems = [System.Collections.Generic.List[object]]::new()
$absentItems = [System.Collections.Generic.List[string]]::new()
function Register-File([string]$path) {
    $relative = [IO.Path]::GetRelativePath($destinationRoot, $path).Replace('\','/')
    $manifestItems.Add([pscustomobject]@{ Path = $relative; Length = (Get-Item -LiteralPath $path).Length; Sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash })
}
function Copy-Regular([string]$source) {
    $relative = Relative-ToRoot $source
    $target = Join-Path $destinationRoot $relative
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
    if ((Get-Item -LiteralPath $target).PSIsContainer) { Get-ChildItem -LiteralPath $target -File -Recurse | ForEach-Object { Register-File $_.FullName } }
    else { Register-File $target }
}
function Copy-Sqlite([string]$source, [bool]$required) {
    $relative = Relative-ToRoot $source
    if (-not (Test-Path -LiteralPath $source)) {
        if ($required) { throw "SQLite obrigatorio ausente: $relative" }
        $absentItems.Add($relative)
        return
    }
    $target = Join-Path $destinationRoot $relative
    & $python (Join-Path $PSScriptRoot 'backup-sqlite.py') $source $target
    if ($LASTEXITCODE -ne 0) { throw "Falha no backup SQLite: $relative" }
    Register-File $target
}

Copy-Sqlite $database $true
Copy-Sqlite $outbox $false
Copy-Regular (Join-Path $api 'appsettings.Local.json')
Copy-Regular (Join-Path $worker 'config.json')
if (-not (Test-Path -LiteralPath $keys)) { throw 'Chaves de Data Protection ausentes; inicie a API ao menos uma vez antes do backup.' }
Copy-Regular $keys
if ($IncludeSnapshots -and $null -ne $snapshots) {
    if (Test-Path -LiteralPath $snapshots) { Copy-Regular $snapshots } else { $absentItems.Add((Relative-ToRoot $snapshots)) }
}
$manifest = [pscustomobject]@{ SchemaVersion = 2; CreatedAtUtc = (Get-Date).ToUniversalTime().ToString('O'); Items = $manifestItems; AbsentItems = $absentItems }
[IO.File]::WriteAllText((Join-Path $destinationRoot 'manifest.json'), ($manifest | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
Write-Host "Backup consistente criado: $destinationRoot"
