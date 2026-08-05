$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ToolRoot = Join-Path $ProjectRoot '.toolchains'
$JdkRoot = Join-Path $ToolRoot 'jdk'
$SdkRoot = Join-Path $ToolRoot 'android-sdk'
$Gradle = Join-Path $ToolRoot 'gradle-8.9\bin\gradle.bat'
$JavaHome = (Get-ChildItem -LiteralPath $JdkRoot -Directory -ErrorAction SilentlyContinue | Where-Object { Test-Path (Join-Path $_.FullName 'bin\java.exe') } | Select-Object -First 1).FullName

if (-not $JavaHome -or -not (Test-Path -LiteralPath $Gradle)) {
    & (Join-Path $PSScriptRoot 'setup_android_toolchain.ps1')
    $JavaHome = (Get-ChildItem -LiteralPath $JdkRoot -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'bin\java.exe') } | Select-Object -First 1).FullName
}

$env:JAVA_HOME = $JavaHome
$EffectiveSdkRoot = $SdkRoot
if ($SdkRoot -match '[^\x00-\x7F]') {
    $SdkBridge = Join-Path $env:LOCALAPPDATA 'RouteWeaverBuild\android-sdk'
    if (-not (Test-Path -LiteralPath $SdkBridge)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $SdkBridge) | Out-Null
        New-Item -ItemType Junction -Path $SdkBridge -Target $SdkRoot | Out-Null
    }
    $EffectiveSdkRoot = $SdkBridge
}
$env:ANDROID_HOME = $EffectiveSdkRoot
$env:ANDROID_SDK_ROOT = $EffectiveSdkRoot
$ArtifactRoot = Join-Path $ProjectRoot 'artifacts'
New-Item -ItemType Directory -Force -Path $ArtifactRoot | Out-Null

$AndroidProject = Join-Path $ProjectRoot 'android'
if ($AndroidProject -match '[^\x00-\x7F]') {
    # AGP's Windows test worker still corrupts non-ASCII classpaths. Keep source in
    # the repository, but compile from a stable ASCII staging directory.
    $StageRoot = Join-Path $env:LOCALAPPDATA 'RouteWeaverBuild\android'
    New-Item -ItemType Directory -Force -Path $StageRoot | Out-Null
    Get-ChildItem -LiteralPath $AndroidProject -Force | Where-Object { $_.Name -notin @('build','.gradle','local.properties') } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $StageRoot -Recurse -Force
    }
    $AndroidProject = $StageRoot
}

& $Gradle --no-daemon --stacktrace testDebugUnitTest assembleDebug -p $AndroidProject
if ($LASTEXITCODE -ne 0) { throw "Android build failed with exit code $LASTEXITCODE" }

$SourceApk = Join-Path $AndroidProject 'app\build\outputs\apk\debug\app-debug.apk'
$TargetApk = Join-Path $ArtifactRoot 'RouteWeaver-Android-1.2.0-debug.apk'
Copy-Item -LiteralPath $SourceApk -Destination $TargetApk -Force
Get-FileHash -Algorithm SHA256 -LiteralPath $TargetApk | Format-List
Write-Host "APK: $TargetApk"
