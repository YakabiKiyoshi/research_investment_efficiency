param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectName
)

$ErrorActionPreference = "Stop"

# This script is expected to live in:
#   research-template/scripts/new-project.ps1
# Therefore the template root is the parent directory of this script's directory.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$template = Split-Path -Parent $scriptDir

# Create the new project next to the template folder.
$parent = Split-Path -Parent $template
$target = Join-Path $parent $ProjectName

if (-not (Test-Path $template)) {
    throw "Template folder not found: $template"
}

if (Test-Path $target) {
    throw "Target project already exists: $target"
}

Copy-Item -Recurse -Path $template -Destination $target

# Remove template git history from the new project.
$gitDir = Join-Path $target ".git"
if (Test-Path $gitDir) {
    Remove-Item -Recurse -Force $gitDir
}

# Remove generated/local files if present.
$pathsToRemove = @(
    "paper\build",
    "data",
    "outputs"
)

foreach ($relativePath in $pathsToRemove) {
    $fullPath = Join-Path $target $relativePath
    if (Test-Path $fullPath) {
        Remove-Item -Recurse -Force $fullPath
    }
}

# Recreate the standard project scaffold (see README "Directory structure").
# data/ and outputs/ are git-ignored; docs/papers and scripts/analysis are
# tracked and normally arrive via the template copy -- recreated here too so
# an older template without them still yields the full structure.
New-Item -ItemType Directory -Force -Path `
    (Join-Path $target "data\raw"), `
    (Join-Path $target "data\processed"), `
    (Join-Path $target "docs\papers"), `
    (Join-Path $target "outputs\ai"), `
    (Join-Path $target "outputs\figures"), `
    (Join-Path $target "outputs\tables"), `
    (Join-Path $target "outputs\models"), `
    (Join-Path $target "scripts\analysis") | Out-Null

Write-Host "Created project: $target"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  cd `"$target`""
Write-Host "  code ."
Write-Host "  git init"
Write-Host "  git add ."
Write-Host "  git commit -m `"Initial research project`""