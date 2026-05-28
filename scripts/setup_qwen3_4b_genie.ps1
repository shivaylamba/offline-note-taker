param(
    [string]$RepoRoot = "C:\Users\Admin\Documents\executorch-voice-agent",
    [string]$BundleDir = "",
    [string]$QairtHome = "C:\Qualcomm\AIStack\QAIRT\2.45.0.260326"
)

$ErrorActionPreference = "Stop"

$modelRoot = Join-Path $RepoRoot "models\qwen3_4b"
if (-not $BundleDir.Trim()) {
    $BundleDir = Join-Path $modelRoot "genie_bundle"
}

$zipPath = Join-Path $modelRoot "qwen3_4b-genie-w4a16-qualcomm_snapdragon_x_elite.zip"
$downloadUrl = "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/qwen3_4b/releases/v0.54.0/qwen3_4b-genie-w4a16-qualcomm_snapdragon_x_elite.zip"
$expectedBytes = 2527470150

Write-Host "Setting up Qualcomm Qwen3-4B Genie bundle for Snapdragon X Elite..." -ForegroundColor Cyan

New-Item -ItemType Directory -Force $modelRoot, $BundleDir | Out-Null

if (-not (Test-Path -LiteralPath $zipPath) -or ((Get-Item -LiteralPath $zipPath).Length -lt $expectedBytes)) {
    Write-Host "Downloading ready-made Qwen3-4B Genie bundle from Qualcomm public assets..." -ForegroundColor Yellow
    curl.exe -L --fail --continue-at - --output $zipPath $downloadUrl
}

if (-not (Test-Path -LiteralPath (Join-Path $BundleDir "genie_config.json"))) {
    Write-Host "Expanding bundle..." -ForegroundColor Yellow
    Expand-Archive -Path $zipPath -DestinationPath $BundleDir -Force
}

$genieConfig = Get-ChildItem -LiteralPath $BundleDir -Recurse -Filter genie_config.json -File |
    Sort-Object FullName |
    Select-Object -First 1

if (-not $genieConfig) {
    throw "Qwen3-4B bundle was expanded, but genie_config.json was not found under $BundleDir."
}

$configJson = Get-Content -LiteralPath $genieConfig.FullName -Raw | ConvertFrom-Json
$configJson.dialog.engine.backend.QnnHtp.'use-mmap' = $false
$configJson | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $genieConfig.FullName -Encoding UTF8

if (-not (Test-Path -LiteralPath (Join-Path $QairtHome "bin\aarch64-windows-msvc\genie-t2t-run.exe"))) {
    Write-Host "WARNING: QAIRT Genie runtime was not found at $QairtHome." -ForegroundColor Yellow
    Write-Host "Install QAIRT 2.45.x and set QAIRT_HOME before running Qwen3-4B." -ForegroundColor Yellow
}
elseif ($QairtHome -notmatch "2\.45") {
    Write-Host "WARNING: Qwen3-4B assets are built for QAIRT 2.45.x, but QairtHome is $QairtHome." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Qwen3-4B Genie bundle is ready." -ForegroundColor Green
Write-Host "`$env:OFFLINE_NOTES_QWEN3_GENIE_CONFIG = '$($genieConfig.FullName)'" -ForegroundColor White
Write-Host "`$env:QAIRT_HOME = '$QairtHome'" -ForegroundColor White
Write-Host "`$env:Path = `"$QairtHome\bin\aarch64-windows-msvc;$QairtHome\lib\aarch64-windows-msvc;`" + `$env:Path" -ForegroundColor White
Write-Host "`$env:ADSP_LIBRARY_PATH = '$QairtHome\lib\hexagon-v73\unsigned'" -ForegroundColor White
