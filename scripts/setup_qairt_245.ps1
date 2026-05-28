param(
    [string]$InstallerPath = "$HOME\Downloads\Qualcomm_AI_Runtime_SDK.2.45.0.260326154327.Windows-AnyCPU.exe",
    [string]$ExpectedQairtHome = "C:\Qualcomm\AIStack\QAIRT\2.45.0.260326"
)

$ErrorActionPreference = "Stop"

$genie = Join-Path $ExpectedQairtHome "bin\aarch64-windows-msvc\genie-t2t-run.exe"
if (Test-Path -LiteralPath $genie) {
    Write-Host "QAIRT 2.45 is already installed." -ForegroundColor Green
    Write-Host "`$env:QAIRT_HOME = '$ExpectedQairtHome'" -ForegroundColor White
    Write-Host "`$env:Path = `"$ExpectedQairtHome\bin\aarch64-windows-msvc;$ExpectedQairtHome\lib\aarch64-windows-msvc;`" + `$env:Path" -ForegroundColor White
    Write-Host "`$env:ADSP_LIBRARY_PATH = '$ExpectedQairtHome\lib\hexagon-v73\unsigned'" -ForegroundColor White
    exit 0
}

if (-not (Test-Path -LiteralPath $InstallerPath)) {
    $alternateInstaller = "$HOME\Downloads\Qualcomm_AI_Runtime_SDK.2.45.0.260326.Windows-AnyCPU.exe"
    if (Test-Path -LiteralPath $alternateInstaller) {
        $InstallerPath = $alternateInstaller
    }
}

if (-not (Test-Path -LiteralPath $InstallerPath)) {
    Write-Host "QAIRT 2.45 installer was not found at:" -ForegroundColor Yellow
    Write-Host "  $InstallerPath" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Download this exact version from Qualcomm Software Center:" -ForegroundColor Yellow
    Write-Host "  Qualcomm AI Runtime SDK 2.45.0.260326154327 Windows-AnyCPU" -ForegroundColor White
    Write-Host ""
    Write-Host "Direct SDK downloads are gated by Qualcomm Software Center login/license; an AI Hub API token is not enough." -ForegroundColor Yellow
    Write-Host "After downloading, rerun:" -ForegroundColor White
    Write-Host "  .\scripts\setup_qairt_245.ps1" -ForegroundColor White
    exit 2
}

$extractScript = Join-Path (Split-Path $InstallerPath -Parent) "extract_qairt245.ps1"
$logPath = Join-Path (Split-Path $InstallerPath -Parent) "extract_qairt245.log"
@"
`$ErrorActionPreference = 'Continue'
& '$InstallerPath' EXTRACT qairt -version 2.45.0.260326 -Silent -ver *> '$logPath'
exit `$LASTEXITCODE
"@ | Set-Content -LiteralPath $extractScript -Encoding ASCII

Write-Host "Extracting QAIRT 2.45 with elevated QIK wrapper..." -ForegroundColor Cyan
Start-Process -FilePath powershell.exe -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $extractScript) -Verb RunAs -Wait

if (-not (Test-Path -LiteralPath $genie)) {
    throw "Installer finished, but QAIRT 2.45 was not found at $ExpectedQairtHome. Set QAIRT_HOME manually if it installed elsewhere."
}

Write-Host ""
Write-Host "QAIRT 2.45 is installed." -ForegroundColor Green
Write-Host "`$env:QAIRT_HOME = '$ExpectedQairtHome'" -ForegroundColor White
Write-Host "`$env:Path = `"$ExpectedQairtHome\bin\aarch64-windows-msvc;$ExpectedQairtHome\lib\aarch64-windows-msvc;`" + `$env:Path" -ForegroundColor White
Write-Host "`$env:ADSP_LIBRARY_PATH = '$ExpectedQairtHome\lib\hexagon-v73\unsigned'" -ForegroundColor White
