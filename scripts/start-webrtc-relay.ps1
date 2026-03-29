$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$configPath = Join-Path $repoRoot "config.json"
$mediamtxDir = Join-Path $repoRoot "tools\\mediamtx"
$mediamtxExe = Join-Path $mediamtxDir "mediamtx.exe"
$generatedConfigPath = Join-Path $mediamtxDir "mediamtx.generated.yml"
$pidPath = Join-Path $mediamtxDir "mediamtx.pid"

if (-not (Test-Path $mediamtxExe)) {
  throw "MediaMTX nao encontrado em $mediamtxExe"
}

if (-not (Test-Path $configPath)) {
  throw "config.json nao encontrado em $configPath"
}

$appConfig = Get-Content $configPath -Raw | ConvertFrom-Json
$streamUrl = [string]$appConfig.stream_url

if ([string]::IsNullOrWhiteSpace($streamUrl)) {
  throw "stream_url nao configurada em config.json"
}

$generatedConfig = @"
logLevel: info
logDestinations: [stdout]

hls: true
hlsAddress: :8888
hlsAllowOrigins: ['*']
hlsVariant: lowLatency
hlsSegmentCount: 7
hlsSegmentDuration: 1s
hlsPartDuration: 200ms

webrtc: true
webrtcAddress: :8889
webrtcAllowOrigins: ['*']
webrtcLocalUDPAddress: :8189
webrtcLocalTCPAddress: ''
webrtcIPsFromInterfaces: true
webrtcAdditionalHosts: [127.0.0.1, localhost]

pathDefaults:
  sourceOnDemand: true
  sourceOnDemandStartTimeout: 15s
  sourceOnDemandCloseAfter: 15s

paths:
  rodovia-live:
    source: $streamUrl
"@

Set-Content -Path $generatedConfigPath -Value $generatedConfig -Encoding ASCII

if (Test-Path $pidPath) {
  $existingPid = (Get-Content $pidPath -Raw).Trim()
  if ($existingPid) {
    $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($existingProcess) {
      Write-Host "MediaMTX ja esta em execucao com PID $existingPid"
      exit 0
    }
  }
}

$process = Start-Process `
  -FilePath $mediamtxExe `
  -ArgumentList "`"$generatedConfigPath`"" `
  -WorkingDirectory $mediamtxDir `
  -PassThru

Set-Content -Path $pidPath -Value $process.Id -Encoding ASCII

Write-Host "MediaMTX iniciado com PID $($process.Id)"
Write-Host "WebRTC: http://127.0.0.1:8889/rodovia-live?controls=false&muted=true&autoplay=true&playsInline=true"
Write-Host "HLS: http://127.0.0.1:8888/rodovia-live/index.m3u8"
