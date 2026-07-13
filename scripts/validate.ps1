param(
    [switch]$PythonOnly,
    [switch]$ROnly,
    [switch]$TexOnly
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $ProjectRoot

Write-Host "Project root: $ProjectRoot"

$runPython = $true
$runR = $true
$runTex = $true

if ($PythonOnly) {
    $runR = $false
    $runTex = $false
}

if ($ROnly) {
    $runPython = $false
    $runTex = $false
}

if ($TexOnly) {
    $runPython = $false
    $runR = $false
}

if (-not (Test-Path ".\docker-compose.yml")) {
    throw "docker-compose.yml not found in project root."
}

if ($runPython) {
    Write-Host ""
    Write-Host "=== Python validation ==="
    docker compose build python
    docker compose run --rm python python -c "import pandas as pd; import sklearn; import duckdb; print('Python OK')"
}

if ($runR) {
    Write-Host ""
    Write-Host "=== R validation ==="
    docker compose build r
    docker compose run --rm r R -e "library(renv); library(languageserver); library(IRkernel); print('R OK')"
}

if ($runTex) {
    Write-Host ""
    Write-Host "=== TeX validation ==="
    docker compose build tex
    docker compose run --rm tex bash scripts/build-pdf.sh
}

Write-Host ""
Write-Host "Validation finished."
