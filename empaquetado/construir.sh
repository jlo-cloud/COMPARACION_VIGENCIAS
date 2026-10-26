#!/bin/sh
# Arma dist/Liquidador/Liquidador.exe. Con Python y no con PowerShell:
# la politica del equipo (AllSigned) no deja correr .ps1 sin firma.
#   sh empaquetado/construir.sh
set -e
cd "$(dirname "$0")/.."
[ -x .venv-exe/Scripts/python.exe ] || py -3.12 -m venv .venv-exe
P=.venv-exe/Scripts/python.exe
$P -m pip install -q --upgrade pip
$P -m pip install -q -r empaquetado/requirements-exe.txt
$P -m PyInstaller --noconfirm --clean --distpath dist --workpath build empaquetado/Liquidador.spec
echo "[OK] dist/Liquidador/Liquidador.exe"
