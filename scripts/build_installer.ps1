$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Candidates = @(
    'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    'C:\Program Files\Inno Setup 6\ISCC.exe',
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
)
$Iscc = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $Iscc) { throw 'Inno Setup 6 was not found. Install package JRSoftware.InnoSetup with winget.' }
& $Iscc (Join-Path $ProjectRoot 'installer\RouteWeaver.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ProjectRoot 'artifacts\RouteWeaver-Windows-Setup-1.3.1.exe') | Format-List
