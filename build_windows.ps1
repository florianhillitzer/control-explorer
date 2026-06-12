$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectDir ".venv-build\Scripts\python.exe"

Set-Location $ProjectDir

if (-not (Test-Path $VenvPython)) {
    python -m venv .venv-build
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements-build.txt
& $VenvPython -m PyInstaller --noconfirm --clean control_explorer.spec

Write-Host ""
Write-Host "Build abgeschlossen:"
Write-Host "  $ProjectDir\dist\ControlExplorer\ControlExplorer.exe"
Write-Host ""
Write-Host "Zum Verteilen den gesamten Ordner dist\ControlExplorer als ZIP verpacken."
