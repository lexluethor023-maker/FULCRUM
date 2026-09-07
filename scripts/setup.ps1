param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    & $Python -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ required"'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ is required.' }
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
    }
    & .\.venv\Scripts\python.exe -m app init
    if ($LASTEXITCODE -ne 0) { throw 'Initialization failed.' }
    & .\.venv\Scripts\python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Verification failed.' }
} finally {
    Pop-Location
}
