param(
    [int]$Port = 3000
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$toolsDir = Join-Path $repoRoot ".tools"
$nodeVersion = "v22.14.0"
$nodeDir = Join-Path $toolsDir "node-v22.14.0-win-x64"
$nodeExe = Join-Path $nodeDir "node.exe"
$npmCli = Join-Path $nodeDir "node_modules\npm\bin\npm-cli.js"
$mintEntry = Join-Path $toolsDir "mint-runtime\node_modules\mint\index.js"
$nodeZip = Join-Path $toolsDir "node-v22.14.0-win-x64.zip"

if (-not (Test-Path $toolsDir)) {
    New-Item -ItemType Directory -Path $toolsDir | Out-Null
}

if (-not (Test-Path $nodeExe)) {
    $nodeUrl = "https://nodejs.org/dist/$nodeVersion/node-v22.14.0-win-x64.zip"
    Write-Host "Downloading local Node $nodeVersion..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeZip
    Expand-Archive -Path $nodeZip -DestinationPath $toolsDir -Force
    Remove-Item $nodeZip -Force
}

if (-not (Test-Path $mintEntry)) {
    Write-Host "Installing local Mintlify CLI..." -ForegroundColor Cyan
    & $nodeExe $npmCli install mint --prefix (Join-Path $toolsDir "mint-runtime")
}

$env:PATH = "$nodeDir;$env:PATH"

Write-Host "Starting Mintlify docs preview on http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop." -ForegroundColor DarkGray

& $nodeExe $mintEntry dev --port $Port
