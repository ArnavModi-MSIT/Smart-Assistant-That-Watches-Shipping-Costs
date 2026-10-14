param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonExecutable = $null
$pythonOnPath = Get-Command python -ErrorAction SilentlyContinue
if ($pythonOnPath) { $pythonExecutable = $pythonOnPath.Source }
if (-not $pythonExecutable) { throw 'Install Python 3.10 or newer and make python available on PATH.' }
if (-not (Test-Path -LiteralPath '.\output\results.json')) {
    & $pythonExecutable -m freight_watch verify --output-dir output
    if ($LASTEXITCODE -ne 0) { throw 'Analysis failed. Check the input files.' }
}
Write-Host "Open http://127.0.0.1:$Port in your browser. Press Ctrl+C to stop."
& $pythonExecutable -m freight_watch serve --output-dir output --port $Port
exit $LASTEXITCODE
