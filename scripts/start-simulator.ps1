$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Najpierw utworz srodowisko .venv zgodnie z docs/step-02-interactive.md.'
}
Push-Location $repoRoot
try {
    & $pythonPath -m streamlit run simulator_app.py --server.address 127.0.0.1 --server.port 8501
    if ($LASTEXITCODE -ne 0) { throw 'Nie udalo sie uruchomic aplikacji. Sprawdz requirements-ui.txt i port 8501.' }
} finally {
    Pop-Location
}
