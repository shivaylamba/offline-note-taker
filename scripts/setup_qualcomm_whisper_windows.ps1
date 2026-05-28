param(
    [string]$RepoRoot = "C:\Users\Admin\Documents\executorch-voice-agent",
    [string]$Device = "Snapdragon X Elite CRD"
)

$ErrorActionPreference = "Stop"

$appDir = Join-Path $RepoRoot "external\ai-hub-apps\apps\whisper_windows_py"
$venvPython = Join-Path $RepoRoot "external\aihub-whisper-venv311\Scripts\python.exe"
$assetDir = Join-Path $appDir "export_assets"
$bundleDir = Join-Path $assetDir "whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite"
$encoderPath = Join-Path $bundleDir "HfWhisperEncoder.onnx"
$decoderPath = Join-Path $bundleDir "HfWhisperDecoder.onnx"

Write-Host "Setting up Qualcomm AI Hub Whisper Windows..." -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $appDir)) {
    New-Item -ItemType Directory -Force (Split-Path $appDir -Parent) | Out-Null
    git clone --depth 1 --filter=blob:none --sparse https://github.com/qualcomm/ai-hub-apps.git (Join-Path $RepoRoot "external\ai-hub-apps")
    Push-Location (Join-Path $RepoRoot "external\ai-hub-apps")
    try {
        git sparse-checkout set apps/whisper_windows_py tutorials/llm_on_genie
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    py -3.11 -m venv (Join-Path $RepoRoot "external\aihub-whisper-venv311")
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install "qai_hub_models[whisper-base]~=0.48.0"
& $venvPython -m pip uninstall -y onnxruntime
& $venvPython -m pip install "onnxruntime-qnn==1.24.4"

New-Item -ItemType Directory -Force $assetDir | Out-Null
Push-Location $appDir
try {
    & $venvPython -m qai_hub_models.models.whisper_base.export `
        --target-runtime precompiled_qnn_onnx `
        --device $Device `
        --fetch-static-assets

    $zipPath = Join-Path $assetDir "whisper_base-precompiled_qnn_onnx-float-qualcomm_snapdragon_x_elite.zip"
    if (-not (Test-Path -LiteralPath $zipPath)) {
        throw "Whisper asset zip was not downloaded to $zipPath"
    }
    Expand-Archive -Path $zipPath -DestinationPath $assetDir -Force
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $encoderPath) -or -not (Test-Path -LiteralPath $decoderPath)) {
    throw "Whisper ONNX assets were not found after extraction."
}

Write-Host ""
Write-Host "Whisper Windows is ready." -ForegroundColor Green
Write-Host "`$env:OFFLINE_NOTES_WHISPER_APP_DIR = '$appDir'" -ForegroundColor White
Write-Host "`$env:OFFLINE_NOTES_WHISPER_PYTHON = '$venvPython'" -ForegroundColor White
Write-Host "`$env:OFFLINE_NOTES_WHISPER_ENCODER_PATH = '$encoderPath'" -ForegroundColor White
Write-Host "`$env:OFFLINE_NOTES_WHISPER_DECODER_PATH = '$decoderPath'" -ForegroundColor White
