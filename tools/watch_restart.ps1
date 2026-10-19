# Watch .py and game_data/*.json; call restart_server.ps1 on change.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$WatchPaths = @('app.py', 'engine', 'game_data')
$Restart = Join-Path $PSScriptRoot 'restart_server.ps1'

function Get-MaxMTime([string]$p) {
    $item = Get-Item -ErrorAction SilentlyContinue $p
    if (-not $item) { return $null }
    if ($item.PSIsContainer) {
        $mt = Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue |
              Measure-Object LastWriteTime -Maximum
        if ($mt.Count -eq 0) { return $null }
        return $mt.Maximum
    }
    return $item.LastWriteTime
}

$last = @{}
foreach ($p in $WatchPaths) { $last[$p] = Get-MaxMTime $p }

Write-Host "watching: $($WatchPaths -join ', '); Ctrl+C to stop"
while ($true) {
    Start-Sleep -Seconds 2
    foreach ($p in $WatchPaths) {
        $mt = Get-MaxMTime $p
        if ($mt -and $mt -ne $last[$p]) {
            Write-Host "[$(Get-Date -Format HH:mm:ss)] $p changed -> restart"
            $last[$p] = $mt
            & $Restart
            break
        }
    }
}
