$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = $env:ROUTEWEAVER_PYTHON
if (-not $Python) {
    $Python = (Get-Command python -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Python 3.11+ was not found. Set ROUTEWEAVER_PYTHON to python.exe.'
}
$ArtifactRoot = Join-Path $ProjectRoot 'artifacts'
New-Item -ItemType Directory -Force -Path $ArtifactRoot | Out-Null

& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --exclude-module numpy --name RouteWeaver --paths (Join-Path $ProjectRoot 'src') (Join-Path $ProjectRoot 'scripts\routeweaver_entry.py')
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
Copy-Item -LiteralPath (Join-Path $ProjectRoot 'dist\RouteWeaver.exe') -Destination (Join-Path $ArtifactRoot 'RouteWeaver-Windows-1.3.2.exe') -Force
Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $ArtifactRoot 'RouteWeaver-Windows-1.3.2.exe') | Format-List
