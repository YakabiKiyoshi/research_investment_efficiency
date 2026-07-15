param(
    [switch]$PythonOnly,
    [switch]$ROnly,
    [switch]$TexOnly
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $ProjectRoot

Write-Host "Project root: $ProjectRoot"

$runPython = -not ($ROnly -or $TexOnly)
$runR = -not ($PythonOnly -or $TexOnly)
$runTex = -not ($PythonOnly -or $ROnly)

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

function Invoke-ProjectPython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython) {
        & $venvPython @Arguments
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 @Arguments
    } elseif (Get-Command uv -ErrorAction SilentlyContinue) {
        $pyproject = Join-Path $ProjectRoot "pyproject.toml"
        $requirements = Join-Path $ProjectRoot "requirements.txt"
        if (Test-Path -LiteralPath $pyproject) {
            & uv run python @Arguments
        } elseif (Test-Path -LiteralPath $requirements) {
            & uv run --no-project --with-requirements $requirements python @Arguments
        } else {
            & uv run --no-project python @Arguments
        }
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python @Arguments
    } else {
        throw "Python was not found. Install Python or create .venv."
    }
    Assert-LastExitCode "Python validation"
}

if ($runPython) {
    Write-Host ""
    Write-Host "=== Python validation ==="
    Invoke-ProjectPython --version
    Invoke-ProjectPython -c "import pandas as pd; import sklearn; import duckdb; print('Python OK')"
}

if ($runR) {
    Write-Host ""
    Write-Host "=== R validation ==="
    if (-not (Get-Command Rscript -ErrorAction SilentlyContinue)) {
        throw "Rscript was not found. Install R and add it to PATH."
    }
    Rscript -e "library(renv); library(languageserver); library(IRkernel); cat('R OK\n')"
    Assert-LastExitCode "R validation"
}

if ($runTex) {
    Write-Host ""
    Write-Host "=== TeX validation ==="
    foreach ($command in @("lualatex", "latexmk", "biber")) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "$command was not found. Install TeX Live and add it to PATH."
        }
    }
    if (Test-Path -LiteralPath (Join-Path $ProjectRoot "scripts\build-pdf.sh")) {
        if (-not (Get-Command bash -ErrorAction SilentlyContinue)) {
            throw "bash was not found. Install Git for Windows or run the TeX commands manually."
        }
        bash scripts/build-pdf.sh
        Assert-LastExitCode "TeX validation"
    } else {
        lualatex --version
        latexmk --version
        biber --version
    }
}

Write-Host ""
Write-Host "Validation finished."
