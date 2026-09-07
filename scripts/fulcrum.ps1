param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArgs
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Run scripts\setup.ps1 with a Python 3.12+ executable first.'
}
Push-Location -LiteralPath $projectRoot
try {
    & $pythonPath -m app @CommandArgs
    $commandExit = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $commandExit
