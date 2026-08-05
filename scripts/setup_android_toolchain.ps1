param(
    [switch]$SkipSdkPackages,
    [string]$BootstrapProxy = ''
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ToolRoot = Join-Path $ProjectRoot '.toolchains'
$DownloadRoot = Join-Path $ToolRoot 'downloads'
$JdkRoot = Join-Path $ToolRoot 'jdk'
$SdkRoot = Join-Path $ToolRoot 'android-sdk'
$GradleRoot = Join-Path $ToolRoot 'gradle-8.9'

New-Item -ItemType Directory -Force -Path $DownloadRoot,$JdkRoot,$SdkRoot | Out-Null

function Get-Download([string]$Uri, [string]$Destination) {
    if (-not (Test-Path -LiteralPath $Destination)) {
        Write-Host "Downloading $Uri"
        if ($BootstrapProxy) {
            & curl.exe --proxy $BootstrapProxy -L --fail --retry 10 --retry-all-errors --retry-delay 2 --connect-timeout 20 -o $Destination $Uri
            if ($LASTEXITCODE -ne 0) { throw "curl download failed with exit code $LASTEXITCODE" }
        } else {
            Invoke-WebRequest -Uri $Uri -OutFile $Destination -UseBasicParsing
        }
    }
}

$JdkArchive = Join-Path $DownloadRoot 'temurin17-jdk.zip'
if (-not (Get-ChildItem -LiteralPath $JdkRoot -Directory -ErrorAction SilentlyContinue | Select-Object -First 1)) {
    Get-Download 'https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse' $JdkArchive
    Expand-Archive -LiteralPath $JdkArchive -DestinationPath $JdkRoot -Force
}
$JavaHome = (Get-ChildItem -LiteralPath $JdkRoot -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'bin\java.exe') } | Select-Object -First 1).FullName
if (-not $JavaHome) { throw 'JDK extraction did not produce bin\java.exe' }

$GradleArchive = Join-Path $DownloadRoot 'gradle-8.9-bin.zip'
if (-not (Test-Path -LiteralPath (Join-Path $GradleRoot 'bin\gradle.bat'))) {
    Get-Download 'https://services.gradle.org/distributions/gradle-8.9-bin.zip' $GradleArchive
    Expand-Archive -LiteralPath $GradleArchive -DestinationPath $ToolRoot -Force
}

$SdkManager = Join-Path $SdkRoot 'cmdline-tools\latest\bin\sdkmanager.bat'
if (-not (Test-Path -LiteralPath $SdkManager)) {
    $CommandToolsArchive = Join-Path $DownloadRoot 'commandlinetools-win-latest.zip'
    Get-Download 'https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip' $CommandToolsArchive
    $ExtractRoot = Join-Path $ToolRoot 'cmdline-tools-extract'
    New-Item -ItemType Directory -Force -Path $ExtractRoot | Out-Null
    Expand-Archive -LiteralPath $CommandToolsArchive -DestinationPath $ExtractRoot -Force
    $LatestRoot = Join-Path $SdkRoot 'cmdline-tools\latest'
    New-Item -ItemType Directory -Force -Path $LatestRoot | Out-Null
    Copy-Item -Path (Join-Path $ExtractRoot 'cmdline-tools\*') -Destination $LatestRoot -Recurse -Force
    if (-not (Test-Path -LiteralPath $SdkManager)) { throw 'Android command-line tools layout is invalid' }
}

$env:JAVA_HOME = $JavaHome
$env:ANDROID_HOME = $SdkRoot
$env:ANDROID_SDK_ROOT = $SdkRoot

if (-not $SkipSdkPackages) {
    $Accept = 1..200 | ForEach-Object { 'y' }
    $Accept | & $SdkManager --sdk_root=$SdkRoot --licenses | Out-Host
    & $SdkManager --sdk_root=$SdkRoot 'platform-tools' 'platforms;android-35' 'build-tools;35.0.0'
    if ($LASTEXITCODE -ne 0) { throw "sdkmanager failed with exit code $LASTEXITCODE" }
}

Write-Host "JAVA_HOME=$JavaHome"
Write-Host "ANDROID_HOME=$SdkRoot"
Write-Host "GRADLE_HOME=$GradleRoot"
