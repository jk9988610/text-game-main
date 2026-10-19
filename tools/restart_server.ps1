# Restart TextGameEngine Flask server. Idempotent: kill old, start new, verify single listener.
$ErrorActionPreference = 'Stop'
$Port = 5000
$PyExe = 'C:\Users\123mc\AppData\Local\Programs\Python\Python312\python.EXE'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Get-Listeners {
    netstat -ano | Select-String ":$Port\s+.*LISTENING" | ForEach-Object {
        (($_ -split '\s+') | Where-Object { $_ })[-1]
    } | Select-Object -Unique
}

$pids = @(Get-Listeners)
if ($pids.Count -gt 0) {
    foreach ($p in $pids) {
        Write-Host "kill PID $p"
        taskkill /F /PID $p 2>$null | Out-Null
    }
}

$deadline = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $deadline) {
    if (-not (Get-Listeners)) { break }
    Start-Sleep -Milliseconds 300
}
if (Get-Listeners) { Write-Error "port $Port still occupied"; exit 1 }

Start-Process -FilePath $PyExe -ArgumentList 'app.py' -WorkingDirectory $Root -WindowStyle Minimized

$deadline = (Get-Date).AddSeconds(15)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    $line = netstat -ano | Select-String ":$Port\s+.*LISTENING"
    if ($line) { Write-Host "OK: $line"; exit 0 }
}
Write-Error "server did not start within 15s"
exit 1
