param(
    [switch]$SkipInstall,
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $Repo '.venv-build'
$Python = Join-Path $Venv 'Scripts\python.exe'

Set-Location -LiteralPath $Repo

if (-not (Test-Path -LiteralPath $Python)) {
    py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12), 'Se requiere Python 3.12.x'; print(sys.version)"
    py -3.12 -m venv $Venv
}

& $Python -c "import sys; assert sys.version_info[:2] == (3, 12), 'El entorno de build debe usar Python 3.12.x'"

if (-not $SkipInstall) {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install --requirement requirements-build.txt
}

& $Python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw "Las pruebas fallaron: no se construye el ejecutable" }
& $Python -m compileall -q src

$ArgsPyInstaller = @('--noconfirm')
if ($Clean) { $ArgsPyInstaller += '--clean' }
$ArgsPyInstaller += 'LiquidadorCatastral.spec'
& $Python -m PyInstaller @ArgsPyInstaller

if ($LASTEXITCODE -ne 0) { throw "PyInstaller termino con codigo $LASTEXITCODE" }
$Exe = Join-Path $Repo 'dist\LiquidadorCatastral\LiquidadorCatastral.exe'
if (-not (Test-Path -LiteralPath $Exe)) { throw "No se genero $Exe" }
$SelfTest = Start-Process -FilePath $Exe -ArgumentList '--self-test' -Wait -PassThru -WindowStyle Hidden
if ($SelfTest.ExitCode -ne 0) { throw "El self-test del ejecutable fallo con codigo $($SelfTest.ExitCode)" }
Write-Host "[OK] Ejecutable generado: $Exe"
