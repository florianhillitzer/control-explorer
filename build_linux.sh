#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [ ! -x ".venv-build-linux/bin/python" ]; then
    python3 -m venv .venv-build-linux
fi

.venv-build-linux/bin/python -m pip install --upgrade pip
.venv-build-linux/bin/python -m pip install -r requirements-build.txt
.venv-build-linux/bin/python -m PyInstaller --noconfirm --clean control_explorer.spec

echo
echo "Build abgeschlossen:"
echo "  $PROJECT_DIR/dist/ControlExplorer/ControlExplorer"
echo
echo "Zum Verteilen den gesamten Ordner dist/ControlExplorer verpacken."
