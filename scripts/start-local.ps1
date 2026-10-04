$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$bootstrapPath = Join-Path $PSScriptRoot 'bootstrap.py'
$launcherArgs = @()
if ($env:PYTHON) {
    $pythonCommand = $env:PYTHON
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = 'py'
    $launcherArgs = @('-3')
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = 'python'
} else {
    throw 'Python 3.12+ (64-bit) is required. Install Python and run this command again.'
}
Push-Location -LiteralPath $projectRoot
try {
    & $pythonCommand @launcherArgs $bootstrapPath @args
    $resultCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $resultCode
