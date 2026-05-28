$ErrorActionPreference = "Stop"

Write-Host "Offline Note Taker" -ForegroundColor Cyan
Write-Host "Launching local desktop app..." -ForegroundColor Cyan

try {
    $python = (Get-Command python -ErrorAction Stop).Source
}
catch {
    Write-Host "Python was not found on PATH. Install Python 3.12, then rerun this launcher." -ForegroundColor Yellow
    exit 2
}

try {
    & $python -c "import PySide6; import offline_meeting_notes" 2>$null
}
catch {
    Write-Host "App dependencies are missing. Installing editable local package..." -ForegroundColor Yellow
    & $python -m pip install -e ".[gui,dev]"
}

& $python -m offline_meeting_notes
