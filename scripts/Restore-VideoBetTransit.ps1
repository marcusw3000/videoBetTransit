param(
    [Parameter(Mandatory)][string]$BackupPath,
    [Parameter(Mandatory)][string]$TargetRoot,
    [switch]$ConfirmOverwrite
)

$ErrorActionPreference = 'Stop'
if (-not $ConfirmOverwrite) { throw 'A restauracao grava arquivos locais. Repita com -ConfirmOverwrite apos preparar uma instalacao separada e parada.' }
$backup = (Resolve-Path $BackupPath).Path
$target = (Resolve-Path $TargetRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $target 'backend/TrafficCounter.Api')) -or -not (Test-Path -LiteralPath (Join-Path $target 'vision-worker'))) { throw 'TargetRoot deve apontar para uma copia preparada do projeto.' }
$manifestPath = Join-Path $backup 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'manifest.json ausente.' }
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.SchemaVersion -ne 2) { throw 'Versao de manifesto nao suportada.' }
$backupPrefix = $backup.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
$targetPrefix = $target.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
if (((Get-Item -LiteralPath $backup).Attributes -band [IO.FileAttributes]::ReparsePoint) -or
    ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'BackupPath e TargetRoot nao podem ser junctions ou links.' }
$verified = [System.Collections.Generic.List[object]]::new()
foreach ($item in $manifest.Items) {
    $relative = [string]$item.Path
    if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative)) { throw "Caminho invalido no manifesto: $relative" }
    $source = [IO.Path]::GetFullPath((Join-Path $backup $relative))
    $destination = [IO.Path]::GetFullPath((Join-Path $target $relative))
    if (-not $source.StartsWith($backupPrefix, [StringComparison]::OrdinalIgnoreCase) -or -not $destination.StartsWith($targetPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw "Caminho fora do escopo no manifesto: $relative" }
    if (-not (Test-Path -LiteralPath $source) -or (Get-Item -LiteralPath $source).PSIsContainer) { throw "Arquivo ausente: $relative" }
    if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Origem contem link: $relative" }
    if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $item.Sha256 -or (Get-Item -LiteralPath $source).Length -ne $item.Length) { throw "Checksum ou tamanho invalido: $relative" }
    $verified.Add([pscustomobject]@{ Source = $source; Destination = $destination; Relative = $relative })
}
foreach ($item in $verified) {
    $cursor = Split-Path $item.Destination -Parent
    while ($cursor.StartsWith($targetPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -LiteralPath $cursor).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Destino contem junction ou link: $($item.Relative)" }
        }
        if ($cursor -eq $target) { break }
        $cursor = Split-Path $cursor -Parent
    }
}
foreach ($item in $verified) {
    New-Item -ItemType Directory -Force -Path (Split-Path $item.Destination -Parent) | Out-Null
    Copy-Item -LiteralPath $item.Source -Destination $item.Destination -Force
}
Write-Host 'Restauracao concluida e verificada. Execute scripts/Test-LocalInstallation.ps1 -RequireExistingDataProtectionKeys antes de iniciar os servicos.'
