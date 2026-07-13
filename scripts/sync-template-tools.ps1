# sync-template-tools.ps1
#
# One-way sync of the shared research toolset from research-template
# (canonical source) into existing research repositories.
#
# What it does (driven by scripts/sync-manifest.psd1):
#   - Overwrite    : copy listed files/directories template -> repo.
#                    Never deletes files that exist only in the target repo.
#   - MarkerMerge  : replace only the <!-- BEGIN SHARED:x --> .. <!-- END SHARED:x -->
#                    region inside repo-specific files (e.g. CLAUDE.md);
#                    appends the block if the markers are absent.
#   - EnsureGitIgnoreLines: add required tracking exceptions without replacing
#                    any repo-specific .gitignore rules.
#   - Deferred     : listed for documentation only; never touched.
#
# Safety:
#   - Default is DRY-RUN. Nothing is written without -Apply.
#   - Aborts if the TEMPLATE has uncommitted changes inside managed paths
#     (so in-development work never propagates by accident).
#   - Uses the target's recorded template commit for an incremental three-way
#     check. Changed Overwrite files must still equal the old template blob;
#     unchanged managed files are outside this run's copy/clean scope.
#   - Marker targets may have repo-specific edits outside their managed block;
#     managed-region edits conflict. .gitignore changes are additive only.
#   - Preflights every target before writing and rolls back exact target files
#     if an apply-time error occurs. Never runs repository-wide reset/clean.
#   - Never runs git commit/push; review and commit in each repo yourself.
#
# Usage:
#   .\scripts\sync-template-tools.ps1 -Repo ..\research_theme_retirement            # dry-run
#   .\scripts\sync-template-tools.ps1 -Repo ..\research_edinet,..\research_umezawa -Apply
#
# PowerShell 5.1 compatible (no &&/||, no ternary, UTF-8 no BOM writes).

param(
    [Parameter(Mandatory = $true)]
    [string[]]$Repo,

    [switch]$Apply
)

$ErrorActionPreference = 'Stop'

$scriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$templateRoot = Split-Path -Parent $scriptDir
$manifestPath = Join-Path $scriptDir 'sync-manifest.psd1'
$manifest     = Import-PowerShellDataFile -Path $manifestPath

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$treeBlobCache = @{}
$manifestAtCommitCache = @{}
$templateSourceBytes = @{}
$sharedBlocks = @{}

function Get-SafeRepoPath {
    # Resolve a manifest-controlled relative path without following a target
    # junction/symlink out of the repository. Missing leaf/parents are allowed,
    # but every existing component beneath the root must be a normal directory
    # or file, never a reparse point.
    param([string]$root, [string]$relativePath)
    $normalized = $relativePath.Replace('\', '/').Trim('/')
    if ([string]::IsNullOrWhiteSpace($normalized) -or
            [System.IO.Path]::IsPathRooted($normalized) -or
            $normalized -match '(^|/)\.\.?(?:/|$)' -or
            $normalized -match '[:*?"<>|\x00-\x1f]') {
        throw "Unsafe repository-relative path: '$relativePath'"
    }
    $rootFull = [System.IO.Path]::GetFullPath($root).TrimEnd('\')
    $full = [System.IO.Path]::GetFullPath(
        (Join-Path $rootFull ($normalized -replace '/', '\')))
    $prefix = $rootFull + [System.IO.Path]::DirectorySeparatorChar
    if (-not $full.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path escapes repository root: '$relativePath' -> '$full'"
    }

    $current = $rootFull
    $segments = @($normalized -split '/')
    for ($index = 0; $index -lt $segments.Count; $index++) {
        $current = Join-Path $current $segments[$index]
        if (-not (Test-Path -LiteralPath $current)) { continue }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing repository path through a symlink/junction: $current"
        }
        if (($index -lt ($segments.Count - 1)) -and (-not $item.PSIsContainer)) {
            throw "Non-directory parent in repository path: $current"
        }
    }
    return $full
}

function Get-ManagedFiles {
    # Returns repo-relative paths (forward slashes) of all files under the
    # manifest's Overwrite entries, as found in $root. Missing entries are
    # skipped (a target repo may not have them yet).
    param([string]$root)
    $files = @()
    foreach ($entry in $manifest.Overwrite) {
        $full = Join-Path $root ($entry -replace '/', '\')
        if (-not (Test-Path $full)) { continue }
        if (Test-Path $full -PathType Leaf) {
            $files += $entry
            continue
        }
        Get-ChildItem -Path $full -Recurse -File | ForEach-Object {
            $rel = $_.FullName.Substring($root.Length).TrimStart('\') -replace '\\', '/'
            $excluded = $false
            foreach ($pat in $manifest.ExcludePatterns) {
                if ($_.Name -like $pat) { $excluded = $true }
                if ($rel -match ('(^|/)' + [regex]::Escape(($pat -replace '\*.*$', '')) )) {
                    # directory-name patterns like "__pycache__"
                    if ($pat -notmatch '\*') { $excluded = $true }
                }
            }
            if (-not $excluded) { $files += $rel }
        }
    }
    return $files | Sort-Object -Unique
}

function Invoke-GitCapture {
    # Run git without letting PowerShell 5.1 wrap native stderr into a
    # terminating ErrorRecord. The caller decides whether a non-zero code is
    # an expected probe or a failure.
    param([string]$root, [string[]]$GitArgs, [switch]$AllowFailure)
    $previousEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $raw = @(& git -C $root @GitArgs 2>&1)
    $code = $LASTEXITCODE
    $ErrorActionPreference = $previousEap
    $lines = @($raw | ForEach-Object { $_.ToString() })
    if (($code -ne 0) -and (-not $AllowFailure)) {
        throw "git -C '$root' $($GitArgs -join ' ') failed ($code): $($lines -join ' ')"
    }
    return [pscustomobject]@{ ExitCode = $code; Output = $lines }
}

function Assert-GitRepository {
    param([string]$root, [string]$label)
    $probe = Invoke-GitCapture -root $root -GitArgs @('rev-parse', '--is-inside-work-tree') -AllowFailure
    if (($probe.ExitCode -ne 0) -or (($probe.Output -join '').Trim() -ne 'true')) {
        throw "$label ($root) is not a git worktree"
    }
}

function Assert-CleanPaths {
    param([string]$root, [string]$label, [string[]]$Pathspecs)
    $paths = @($Pathspecs | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        Sort-Object -Unique)
    if ($paths.Count -eq 0) { return }
    $status = Invoke-GitCapture -root $root -GitArgs (@('status', '--porcelain', '--') + $paths)
    if ($status.Output.Count -gt 0) {
        Write-Host "ABORT: $label has uncommitted changes in paths this sync would overwrite:" -ForegroundColor Red
        $status.Output | ForEach-Object { Write-Host "  $_" }
        throw "Commit, stash, or reconcile those paths before re-running."
    }
}

function Assert-CleanManagedPaths {
    param(
        [string]$root,
        [string]$label,
        [switch]$IncludeMarkerSources,
        [string[]]$CandidateOverwritePaths = @()
    )
    if ($IncludeMarkerSources) {
        # The canonical template must be clean across every possible source.
        $pathspecs = @($manifest.Overwrite) + @(
            '.gitignore',
            'docs/ai/template-sync-state.json',
            'scripts/sync-manifest.psd1',
            'scripts/sync-template-tools.ps1')
        foreach ($m in $manifest.MarkerMerge) {
            $pathspecs += $m.Target
            $pathspecs += $m.Source
        }
    }
    else {
        # A target is checked only where this template revision changed a
        # verbatim Overwrite file, plus the state file written by every run.
        # Marker targets are checked region-wise; .gitignore is additive and
        # byte-snapshotted, so project-specific edits outside those managed
        # portions remain safe.
        $pathspecs = @($CandidateOverwritePaths) + @('docs/ai/template-sync-state.json')
    }
    Assert-CleanPaths -root $root -label $label -Pathspecs $pathspecs
}

function Test-GitTracked {
    param([string]$root, [string]$relativePath)
    $probe = Invoke-GitCapture -root $root -GitArgs @(
        'ls-files', '--error-unmatch', '--', $relativePath) -AllowFailure
    return ($probe.ExitCode -eq 0)
}

function Get-TargetTemplateCommit {
    param([string]$repoRoot, [string]$currentTemplateCommit)
    $statePath = Get-SafeRepoPath -root $repoRoot `
        -relativePath 'docs/ai/template-sync-state.json'
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) { return $null }
    if (-not (Test-GitTracked -root $repoRoot -relativePath 'docs/ai/template-sync-state.json')) {
        throw "Existing template sync state is not tracked: $statePath"
    }
    try {
        $state = [System.IO.File]::ReadAllText($statePath, [System.Text.Encoding]::UTF8) |
            ConvertFrom-Json
    }
    catch {
        throw "Invalid template sync state in ${repoRoot}: $($_.Exception.Message)"
    }
    $recorded = "$($state.templateCommit)".Trim()
    if ($recorded -notmatch '^[0-9a-fA-F]{7,40}$') {
        throw "Invalid templateCommit '$recorded' in $statePath"
    }
    $resolved = Invoke-GitCapture -root $templateRoot -GitArgs @(
        'rev-parse', '--verify', ($recorded + '^{commit}')) -AllowFailure
    if ($resolved.ExitCode -ne 0) {
        throw "Recorded template commit '$recorded' from $repoRoot is unavailable in $templateRoot"
    }
    $oldCommit = ($resolved.Output -join '').Trim()
    $ancestor = Invoke-GitCapture -root $templateRoot -GitArgs @(
        'merge-base', '--is-ancestor', $oldCommit, $currentTemplateCommit) -AllowFailure
    if ($ancestor.ExitCode -ne 0) {
        throw "Recorded template commit '$oldCommit' is not an ancestor of '$currentTemplateCommit' for $repoRoot"
    }
    return $oldCommit
}

function Get-CandidateTemplateFiles {
    param(
        [string]$oldTemplateCommit,
        [string]$currentTemplateCommit,
        [string[]]$allTemplateFiles
    )
    if ([string]::IsNullOrWhiteSpace($oldTemplateCommit)) {
        return @($allTemplateFiles)
    }
    if ($oldTemplateCommit -eq $currentTemplateCommit) { return @() }
    $changed = Invoke-GitCapture -root $templateRoot -GitArgs (@(
        'diff', '--name-only', '--diff-filter=ACMRT', $oldTemplateCommit,
        $currentTemplateCommit, '--') + @($manifest.Overwrite))
    $changedSet = @{}
    foreach ($line in $changed.Output) {
        $changedSet[$line.Replace('\', '/')] = $true
    }
    $oldManifest = Get-ManifestAtCommit -commit $oldTemplateCommit
    return @($allTemplateFiles | Where-Object {
            $changedSet.ContainsKey($_) -or
            (-not (Test-ManagedByManifest -relativePath $_ -candidateManifest $oldManifest))
        })
}

function Get-ManifestAtCommit {
    param([string]$commit)
    if ([string]::IsNullOrWhiteSpace($commit)) { return $null }
    if ($manifestAtCommitCache.ContainsKey($commit)) {
        return $manifestAtCommitCache[$commit]
    }
    $spec = $commit + ':scripts/sync-manifest.psd1'
    $content = Invoke-GitCapture -root $templateRoot -GitArgs @('show', $spec) -AllowFailure
    if ($content.ExitCode -ne 0) {
        $manifestAtCommitCache[$commit] = $null
        return $null
    }
    $tempPath = Join-Path ([System.IO.Path]::GetTempPath()) (
        'sync-manifest-' + [guid]::NewGuid().ToString('N') + '.psd1')
    try {
        [System.IO.File]::WriteAllText($tempPath, ($content.Output -join "`n"), $utf8NoBom)
        $oldManifest = Import-PowerShellDataFile -LiteralPath $tempPath
    }
    catch {
        throw "Could not parse sync manifest at template commit ${commit}: $($_.Exception.Message)"
    }
    finally {
        if (Test-Path -LiteralPath $tempPath) { Remove-Item -LiteralPath $tempPath -Force }
    }
    $manifestAtCommitCache[$commit] = $oldManifest
    return $oldManifest
}

function Test-ManagedByManifest {
    param([string]$relativePath, $candidateManifest)
    if ($null -eq $candidateManifest) { return $false }
    $rel = $relativePath.Replace('\', '/').Trim('/')
    $managed = $false
    foreach ($entryRaw in @($candidateManifest.Overwrite)) {
        $entry = "$entryRaw".Replace('\', '/').Trim('/')
        if (($rel -eq $entry) -or $rel.StartsWith(
                $entry + '/', [System.StringComparison]::OrdinalIgnoreCase)) {
            $managed = $true
            break
        }
    }
    if (-not $managed) { return $false }

    $leaf = Split-Path $rel -Leaf
    foreach ($patternRaw in @($candidateManifest.ExcludePatterns)) {
        $pattern = "$patternRaw"
        if ($leaf -like $pattern) { return $false }
        if ($pattern -notmatch '\*') {
            foreach ($segment in @($rel -split '/')) {
                if ($segment -eq $pattern) { return $false }
            }
        }
    }
    return $true
}

function Get-TreeBlobId {
    param([string]$root, [string]$commit, [string]$relativePath)
    if ([string]::IsNullOrWhiteSpace($commit)) { return $null }
    $cacheKey = $root.ToLowerInvariant() + '|' + $commit + '|' + $relativePath
    if ($treeBlobCache.ContainsKey($cacheKey)) { return $treeBlobCache[$cacheKey] }
    $spec = $commit + ':' + $relativePath
    $exists = Invoke-GitCapture -root $root -GitArgs @('cat-file', '-e', $spec) -AllowFailure
    if ($exists.ExitCode -ne 0) {
        $treeBlobCache[$cacheKey] = $null
        return $null
    }
    $blob = Invoke-GitCapture -root $root -GitArgs @('rev-parse', '--verify', $spec)
    $blobId = ($blob.Output -join '').Trim()
    $treeBlobCache[$cacheKey] = $blobId
    return $blobId
}

function Get-WorkingBlobId {
    param([string]$root, [string]$relativePath)
    $full = Get-SafeRepoPath -root $root -relativePath $relativePath
    if (-not (Test-Path -LiteralPath $full)) { return $null }
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw "Expected a file but found another path type: $full"
    }
    # --path applies the target repository's clean/eol attributes, making the
    # working file comparable to a committed template blob.
    $blob = Invoke-GitCapture -root $root -GitArgs @(
        'hash-object', ("--path=$relativePath"), '--', $full)
    return ($blob.Output -join '').Trim()
}

function New-TemplateSourceSnapshot {
    # Freeze committed source bytes once. Apply never rereads the live template,
    # so concurrent edits cannot make target state claim a different commit.
    param([string[]]$relativePaths, [string]$templateCommit)
    $snapshot = @{}
    foreach ($rel in @($relativePaths | Sort-Object -Unique)) {
        if (-not (Test-GitTracked -root $templateRoot -relativePath $rel)) {
            throw "Template source is not tracked: $rel"
        }
        $headBlob = Get-TreeBlobId -root $templateRoot -commit $templateCommit -relativePath $rel
        $workingBlob = Get-WorkingBlobId -root $templateRoot -relativePath $rel
        if ([string]::IsNullOrWhiteSpace($headBlob) -or ($workingBlob -ne $headBlob)) {
            throw "Template source does not match fixed commit ${templateCommit}: $rel"
        }
        $full = Get-SafeRepoPath -root $templateRoot -relativePath $rel
        $snapshot[$rel] = [System.IO.File]::ReadAllBytes($full)
    }
    return $snapshot
}

function Get-OverwriteActions {
    param(
        [string]$repoRoot,
        [string]$oldTemplateCommit,
        [string]$currentTemplateCommit,
        [string[]]$candidateFiles
    )
    $actions = @()
    $oldManifest = Get-ManifestAtCommit -commit $oldTemplateCommit
    foreach ($rel in $candidateFiles) {
        $newBlob = Get-TreeBlobId -root $templateRoot -commit $currentTemplateCommit -relativePath $rel
        if ([string]::IsNullOrWhiteSpace($newBlob)) {
            throw "Current template blob is missing for managed file '$rel'"
        }
        $oldWasManaged = Test-ManagedByManifest `
            -relativePath $rel -candidateManifest $oldManifest
        $oldBlob = if ($oldWasManaged) {
            Get-TreeBlobId -root $templateRoot -commit $oldTemplateCommit -relativePath $rel
        } else { $null }
        $targetBlob = Get-WorkingBlobId -root $repoRoot -relativePath $rel
        $tracked = Test-GitTracked -root $repoRoot -relativePath $rel

        if ([string]::IsNullOrWhiteSpace($targetBlob)) {
            if (-not [string]::IsNullOrWhiteSpace($oldBlob)) {
                throw "SYNC CONFLICT in $repoRoot for '$rel': the old template had this file, but the target no longer does. Refusing to resurrect a committed local deletion."
            }
            $action = 'NEW'
        }
        elseif ($targetBlob -eq $newBlob) {
            $action = 'SAME'
        }
        elseif ((-not [string]::IsNullOrWhiteSpace($oldBlob)) -and
                ($targetBlob -eq $oldBlob) -and $tracked) {
            $action = 'UPDATE'
        }
        else {
            $basis = if ([string]::IsNullOrWhiteSpace($oldTemplateCommit)) {
                'no prior template state is recorded'
            } else {
                "target does not match old template blob $oldBlob or new blob $newBlob"
            }
            throw "SYNC CONFLICT in $repoRoot for '$rel': $basis. Preserve or reconcile the target file explicitly."
        }
        $actions += [pscustomobject]@{
            RelativePath = $rel
            Action = $action
            OldBlob = $oldBlob
            NewBlob = $newBlob
        }
    }
    return $actions
}

function New-TargetTransactionSnapshot {
    param(
        [string]$repoRoot,
        [string[]]$relativePaths,
        [string[]]$preserveBytesPaths
    )
    $preserve = @{}
    foreach ($rel in $preserveBytesPaths) { $preserve[$rel] = $true }
    $snapshot = @()
    foreach ($rel in @($relativePaths | Sort-Object -Unique)) {
        $full = Get-SafeRepoPath -root $repoRoot -relativePath $rel
        $exists = Test-Path -LiteralPath $full
        if ($exists -and (-not (Test-Path -LiteralPath $full -PathType Leaf))) {
            throw "Transaction path is not a file: $full"
        }
        $keepBytes = $exists -and $preserve.ContainsKey($rel)
        $bytes = if ($keepBytes) { [System.IO.File]::ReadAllBytes($full) } else { $null }
        $sha256 = if ($exists) { (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash } else { $null }
        $snapshot += [pscustomobject]@{
            RelativePath = $rel
            FullPath = $full
            Existed = $exists
            Tracked = if ($exists) { Test-GitTracked -root $repoRoot -relativePath $rel } else { $false }
            PreserveBytes = $keepBytes
            Bytes = $bytes
            Sha256 = $sha256
            Attempted = $false
            WrittenSha256 = $null
        }
    }
    return $snapshot
}

function Set-TransactionAttempted {
    param([object[]]$snapshot, [string]$relativePath)
    $entry = @($snapshot | Where-Object { $_.RelativePath -eq $relativePath }) |
        Select-Object -First 1
    if ($null -eq $entry) { throw "Transaction path was not snapshotted: $relativePath" }
    $entry.Attempted = $true
}

function Complete-TransactionWrite {
    param([object[]]$snapshot, [string]$relativePath)
    $entry = @($snapshot | Where-Object { $_.RelativePath -eq $relativePath }) |
        Select-Object -First 1
    if ($null -eq $entry) { throw "Transaction path was not snapshotted: $relativePath" }
    if (-not (Test-Path -LiteralPath $entry.FullPath -PathType Leaf)) {
        throw "Transaction write did not produce a file: $($entry.FullPath)"
    }
    $entry.WrittenSha256 = (Get-FileHash -LiteralPath $entry.FullPath -Algorithm SHA256).Hash
}

function Assert-TransactionSnapshotUnchanged {
    param([object[]]$snapshot)
    foreach ($entry in $snapshot) {
        $existsNow = Test-Path -LiteralPath $entry.FullPath -PathType Leaf
        if ($entry.Existed -ne $existsNow) {
            throw "Target changed after preflight: $($entry.FullPath)"
        }
        if ($entry.Existed) {
            $hashNow = (Get-FileHash -LiteralPath $entry.FullPath -Algorithm SHA256).Hash
            if ($hashNow -ne $entry.Sha256) {
                throw "Target changed after preflight: $($entry.FullPath)"
            }
        }
    }
}

function Restore-TargetTransaction {
    # Restore only exact paths captured for this target. Never reset/clean the
    # repository, and never recursively delete anything.
    param([string]$repoRoot, [object[]]$snapshot)
    $errors = @()

    $eligible = @()
    foreach ($entry in $snapshot | Where-Object { $_.Attempted }) {
        try {
            $safeNow = Get-SafeRepoPath -root $repoRoot -relativePath $entry.RelativePath
            if (-not [string]::Equals($safeNow, $entry.FullPath,
                    [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "resolved path changed"
            }
        }
        catch {
            $errors += "unsafe rollback path retained: $($entry.RelativePath): $($_.Exception.Message)"
            continue
        }
        $currentHash = if (Test-Path -LiteralPath $entry.FullPath -PathType Leaf) {
            (Get-FileHash -LiteralPath $entry.FullPath -Algorithm SHA256).Hash
        } else { $null }
        if ([string]::IsNullOrWhiteSpace($entry.WrittenSha256)) {
            # A failed write with no completed hash is safe to ignore only when
            # the preimage is still byte-identical.
            if ($currentHash -ne $entry.Sha256) {
                $errors += "uncertain partial/concurrent write retained: $($entry.FullPath)"
            }
            continue
        }
        if ($currentHash -ne $entry.WrittenSha256) {
            $errors += "concurrent modification retained during rollback: $($entry.FullPath)"
            continue
        }
        $eligible += $entry
    }

    $trackedRestore = @($eligible | Where-Object {
            $_.Existed -and $_.Tracked -and (-not $_.PreserveBytes)
        } | ForEach-Object { $_.RelativePath })
    if ($trackedRestore.Count -gt 0) {
        $restored = Invoke-GitCapture -root $repoRoot -GitArgs (
            @('restore', '--worktree', '--') + $trackedRestore) -AllowFailure
        if ($restored.ExitCode -ne 0) {
            $errors += "git restore failed: $($restored.Output -join ' ')"
        }
    }

    foreach ($entry in $eligible) {
        try {
            if ($entry.Existed -and $entry.PreserveBytes) {
                $currentHash = if (Test-Path -LiteralPath $entry.FullPath -PathType Leaf) {
                    (Get-FileHash -LiteralPath $entry.FullPath -Algorithm SHA256).Hash
                } else { $null }
                if ($currentHash -ne $entry.Sha256) {
                    [System.IO.File]::WriteAllBytes($entry.FullPath, $entry.Bytes)
                }
            }
            elseif (-not $entry.Existed) {
                if (Test-Path -LiteralPath $entry.FullPath -PathType Leaf) {
                    Remove-Item -LiteralPath $entry.FullPath -Force
                }
                elseif (Test-Path -LiteralPath $entry.FullPath) {
                    $errors += "refused non-file rollback removal: $($entry.FullPath)"
                }
            }
        }
        catch {
            $errors += "rollback failed for $($entry.FullPath): $($_.Exception.Message)"
        }
    }

    foreach ($entry in $snapshot | Where-Object { $_.Existed }) {
        if (-not (Test-Path -LiteralPath $entry.FullPath -PathType Leaf)) {
            $errors += "rollback verification missing file: $($entry.FullPath)"
            continue
        }
        $hashNow = (Get-FileHash -LiteralPath $entry.FullPath -Algorithm SHA256).Hash
        if ($hashNow -ne $entry.Sha256) {
            $errors += "rollback verification hash mismatch: $($entry.FullPath)"
        }
    }
    foreach ($entry in $snapshot | Where-Object { (-not $_.Existed) -and $_.Attempted }) {
        if (Test-Path -LiteralPath $entry.FullPath) {
            $errors += "rollback verification found new path: $($entry.FullPath)"
        }
    }
    if ($errors.Count -gt 0) { throw ($errors -join '; ') }
}

function Get-MissingGitIgnoreLines {
    param([string]$repoRoot)
    $required = @($manifest.EnsureGitIgnoreLines)
    if ($required.Count -eq 0) { return @() }
    $targetPath = Get-SafeRepoPath -root $repoRoot -relativePath '.gitignore'
    $current = ''
    if (Test-Path -LiteralPath $targetPath -PathType Leaf) {
        $current = [System.IO.File]::ReadAllText($targetPath, [System.Text.Encoding]::UTF8)
    }
    $currentLines = @($current -split '\r?\n')
    return @($required | Where-Object { $_ -notin $currentLines })
}

function Sync-GitIgnoreLines {
    # Add manifest-required lines while preserving every existing target rule.
    # Returns the lines that were absent before this call.
    param([string]$repoRoot, [string[]]$MissingLines)
    $targetPath = Get-SafeRepoPath -root $repoRoot -relativePath '.gitignore'
    if ((Test-Path -LiteralPath $targetPath) -and
            (-not (Test-Path -LiteralPath $targetPath -PathType Leaf))) {
        throw "Expected .gitignore to be a file: $targetPath"
    }
    $current = ''
    if (Test-Path -LiteralPath $targetPath -PathType Leaf) {
        $current = [System.IO.File]::ReadAllText($targetPath, [System.Text.Encoding]::UTF8)
    }
    $missing = @($MissingLines)
    if (($missing.Count -gt 0) -and $Apply) {
        $prefix = $current
        if (($prefix.Length -gt 0) -and -not $prefix.EndsWith("`n")) {
            $prefix += "`r`n"
        }
        $updated = $prefix + ($missing -join "`r`n") + "`r`n"
        [System.IO.File]::WriteAllText($targetPath, $updated, $utf8NoBom)
    }
    return $missing
}

function Get-SharedBlock {
    # Extracts the marker-delimited block (inclusive of marker lines) from the
    # source file in the template.
    param([string]$sourceRel, [string]$blockName)
    if (-not $templateSourceBytes.ContainsKey($sourceRel)) {
        throw "Shared-block source was not snapshotted: $sourceRel"
    }
    $text = [System.Text.Encoding]::UTF8.GetString($templateSourceBytes[$sourceRel])
    $begin = "<!-- BEGIN SHARED:$blockName"
    $end   = "<!-- END SHARED:$blockName"
    $i = $text.IndexOf($begin)
    if ($i -lt 0) { throw "Block '$blockName' not found in $sourceRel" }
    $j = $text.IndexOf($end, $i)
    if ($j -lt 0) { throw "END marker for block '$blockName' not found in $sourceRel" }
    $close = $text.IndexOf('-->', $j)
    if ($close -lt 0) { throw "END marker for block '$blockName' is not closed in $sourceRel" }
    $j = $close + 3
    return $text.Substring($i, $j - $i)
}

function Get-ManagedMarkerRegion {
    # Return only the marker-managed (or pre-marker legacy) region, normalized
    # to LF. This lets target files carry unrelated repo-specific edits.
    param([string]$text, [hashtable]$merge, [string]$label)
    $current = $text.Replace("`r`n", "`n").Replace("`r", "`n")
    $begin = "<!-- BEGIN SHARED:$($merge.Block)"
    $end = "<!-- END SHARED:$($merge.Block)"
    $i = $current.IndexOf($begin)
    $j = $current.IndexOf($end)
    if (($i -ge 0) -or ($j -ge 0)) {
        if (($i -lt 0) -or ($j -lt 0) -or ($j -le $i)) {
            throw "$label has malformed markers for '$($merge.Block)'"
        }
        $close = $current.IndexOf('-->', $j)
        if ($close -lt 0) {
            throw "$label has an unclosed END marker for '$($merge.Block)'"
        }
        if (($current.IndexOf($begin, $i + $begin.Length) -ge 0) -or
                ($current.IndexOf($end, $j + $end.Length) -ge 0)) {
            throw "$label has duplicate markers for '$($merge.Block)'"
        }
        return 'MARKER|' + $current.Substring($i, ($close + 3) - $i)
    }

    $legacyStart = "$($merge.LegacyStart)"
    $legacyEnd = "$($merge.LegacyEnd)"
    $startConfigured = -not [string]::IsNullOrWhiteSpace($legacyStart)
    $endConfigured = -not [string]::IsNullOrWhiteSpace($legacyEnd)
    if ($startConfigured -xor $endConfigured) {
        throw "MarkerMerge '$($merge.Block)' must configure both LegacyStart and LegacyEnd"
    }
    if (-not $startConfigured) { return 'ABSENT|' }

    $legacyI = $current.IndexOf($legacyStart)
    $legacyJ = $current.IndexOf($legacyEnd)
    if (($legacyI -ge 0) -xor ($legacyJ -ge 0)) {
        throw "$label has only one legacy boundary for '$($merge.Block)'"
    }
    if (($legacyI -ge 0) -and ($legacyJ -le $legacyI)) {
        throw "$label has reversed legacy boundaries for '$($merge.Block)'"
    }
    if ($legacyI -ge 0) {
        if (($current.IndexOf($legacyStart, $legacyI + $legacyStart.Length) -ge 0) -or
                ($current.IndexOf($legacyEnd, $legacyJ + $legacyEnd.Length) -ge 0)) {
            throw "$label has duplicate legacy boundaries for '$($merge.Block)'"
        }
        return 'LEGACY|' + $current.Substring($legacyI, $legacyJ - $legacyI)
    }
    return 'ABSENT|'
}

function Assert-MarkerTargetReady {
    # Validate marker structure and compare only its managed region with HEAD.
    # Whole-file dirtiness outside that region is intentionally preserved.
    param([string]$repoRoot, [hashtable]$merge)
    $relativePath = "$($merge.Target)".Replace('\', '/')
    $targetPath = Get-SafeRepoPath -root $repoRoot -relativePath $relativePath
    $workingExists = Test-Path -LiteralPath $targetPath -PathType Leaf
    if ((Test-Path -LiteralPath $targetPath) -and (-not $workingExists)) {
        throw "Marker target is not a file: $targetPath"
    }
    $tracked = Test-GitTracked -root $repoRoot -relativePath $relativePath
    if ($workingExists -and (-not $tracked)) {
        throw "Marker target exists but is not tracked; refusing to modify it: $targetPath"
    }
    if ($tracked -and (-not $workingExists)) {
        throw "Tracked marker target is deleted in the working tree: $targetPath"
    }

    $workingText = ''
    if ($workingExists) {
        $workingText = [System.IO.File]::ReadAllText($targetPath, [System.Text.Encoding]::UTF8)
    }
    $workingRegion = Get-ManagedMarkerRegion -text $workingText -merge $merge -label $targetPath
    if (-not $tracked) { return }

    $headSpec = 'HEAD:' + $relativePath
    $headResult = Invoke-GitCapture -root $repoRoot -GitArgs @('show', $headSpec)
    $headText = $headResult.Output -join "`n"
    $headRegion = Get-ManagedMarkerRegion -text $headText -merge $merge -label "$headSpec in $repoRoot"
    $indexSpec = ':0:' + $relativePath
    $indexResult = Invoke-GitCapture -root $repoRoot -GitArgs @('show', $indexSpec)
    $indexText = $indexResult.Output -join "`n"
    $indexRegion = Get-ManagedMarkerRegion -text $indexText -merge $merge -label "$indexSpec in $repoRoot"
    if ((-not [string]::Equals($workingRegion, $headRegion,
                [System.StringComparison]::Ordinal)) -or
            (-not [string]::Equals($indexRegion, $headRegion,
                [System.StringComparison]::Ordinal))) {
        throw "Managed marker/legacy region is modified in $targetPath; reconcile it before sync. Edits outside the managed region are allowed."
    }
}

function Sync-MarkerBlock {
    # Returns 'SAME', 'UPDATE', 'MIGRATE' or 'APPEND'; writes only with -Apply.
    param([string]$repoRoot, [hashtable]$merge)
    if (-not $sharedBlocks.ContainsKey($merge.Block)) {
        throw "Shared block was not frozen during preflight: $($merge.Block)"
    }
    $block      = $sharedBlocks[$merge.Block]
    $targetPath = Get-SafeRepoPath -root $repoRoot -relativePath $merge.Target
    $begin      = "<!-- BEGIN SHARED:$($merge.Block)"
    $end        = "<!-- END SHARED:$($merge.Block)"

    $current = ''
    if (Test-Path $targetPath) {
        $current = [System.IO.File]::ReadAllText($targetPath, [System.Text.Encoding]::UTF8)
    }

    $i = $current.IndexOf($begin)
    if ($i -ge 0) {
        $j = $current.IndexOf($end, $i)
        if ($j -lt 0) { throw "$($merge.Target) in $repoRoot has BEGIN but no END marker for '$($merge.Block)'" }
        $j = $current.IndexOf('-->', $j) + 3
        $existing = $current.Substring($i, $j - $i)
        if ($existing -eq $block) { return 'SAME' }
        $new = $current.Substring(0, $i) + $block + $current.Substring($j)
        if ($Apply) { [System.IO.File]::WriteAllText($targetPath, $new, $utf8NoBom) }
        return 'UPDATE'
    }

    # Targets from the pre-marker rollout contain an unmarked legacy section.
    # Replace that section through immediately before the following heading;
    # preserve the following heading and all repo-specific content around it.
    $legacyStart = "$($merge.LegacyStart)"
    $legacyEnd = "$($merge.LegacyEnd)"
    if ((-not [string]::IsNullOrWhiteSpace($legacyStart)) -and
            (-not [string]::IsNullOrWhiteSpace($legacyEnd))) {
        $legacyI = $current.IndexOf($legacyStart)
        $legacyJ = $current.IndexOf($legacyEnd)
        if (($legacyI -ge 0) -and ($legacyJ -gt $legacyI)) {
            $suffix = $current.Substring($legacyJ)
            $separator = ''
            if ((-not $block.EndsWith("`n")) -and (-not $suffix.StartsWith("`n"))) {
                $separator = "`r`n`r`n"
            }
            $new = $current.Substring(0, $legacyI) + $block + $separator + $suffix
            if ($Apply) { [System.IO.File]::WriteAllText($targetPath, $new, $utf8NoBom) }
            return 'MIGRATE'
        }
    }

    $sep = "`r`n"
    if ($current -match "`n$") { $sep = '' }
    $new = $current + $sep + "`r`n" + $block + "`r`n"
    if ($Apply) { [System.IO.File]::WriteAllText($targetPath, $new, $utf8NoBom) }
    return 'APPEND'
}

# ---------------------------------------------------------------------------

Write-Host "Template : $templateRoot"
Write-Host "Mode     : $(if ($Apply) { 'APPLY' } else { 'DRY-RUN (use -Apply to write)' })"
Write-Host ""

# Phase 1: resolve and validate every source/target before any target write.
# This makes -Apply all-or-nothing with respect to discoverable preflight
# failures (missing repo, duplicate repo, dirty managed path, malformed marker).
Assert-GitRepository -root $templateRoot -label 'TEMPLATE'
Assert-CleanManagedPaths -root $templateRoot -label 'TEMPLATE' -IncludeMarkerSources
$templateCommitResult = Invoke-GitCapture -root $templateRoot -GitArgs @(
    'rev-parse', '--verify', 'HEAD^{commit}')
$templateSha = ($templateCommitResult.Output -join '').Trim()
$templateFiles = @(Get-ManagedFiles -root $templateRoot)
$templateSourcePaths = @($templateFiles) + @(
    'scripts/sync-manifest.psd1', 'scripts/sync-template-tools.ps1')
foreach ($m in $manifest.MarkerMerge) { $templateSourcePaths += $m.Source }
$templateSourceBytes = New-TemplateSourceSnapshot `
    -relativePaths $templateSourcePaths -templateCommit $templateSha
foreach ($m in $manifest.MarkerMerge) {
    $sharedBlocks[$m.Block] = Get-SharedBlock `
        -sourceRel $m.Source -blockName $m.Block
}

$resolvedRepos = @()
$seenRepos = @{}
foreach ($r in $Repo) {
    $requestedRoot = (Resolve-Path -LiteralPath $r).Path
    Assert-GitRepository -root $requestedRoot -label 'TARGET'
    $topResult = Invoke-GitCapture -root $requestedRoot -GitArgs @(
        'rev-parse', '--show-toplevel')
    $repoRoot = (Resolve-Path -LiteralPath (($topResult.Output -join '').Trim())).Path
    if ([string]::Equals($repoRoot, $templateRoot,
            [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to sync the template onto itself."
    }
    $repoKey = $repoRoot.ToLowerInvariant()
    if ($seenRepos.ContainsKey($repoKey)) {
        throw "Duplicate target repository after path resolution: $repoRoot"
    }
    $seenRepos[$repoKey] = $true
    $resolvedRepos += $repoRoot
}

$plans = @()
foreach ($repoRoot in $resolvedRepos) {
    # Read provenance only after proving that the state itself is clean.
    Assert-CleanPaths -root $repoRoot -label 'TARGET STATE' -Pathspecs @(
        'docs/ai/template-sync-state.json')
    $oldTemplateSha = Get-TargetTemplateCommit -repoRoot $repoRoot `
        -currentTemplateCommit $templateSha
    $candidateFiles = @(Get-CandidateTemplateFiles `
        -oldTemplateCommit $oldTemplateSha `
        -currentTemplateCommit $templateSha `
        -allTemplateFiles $templateFiles)
    $actions = @(Get-OverwriteActions -repoRoot $repoRoot `
        -oldTemplateCommit $oldTemplateSha `
        -currentTemplateCommit $templateSha `
        -candidateFiles $candidateFiles)
    # Files already byte-equivalent to the new template are SAME even when a
    # prior interrupted/manual distribution left them uncommitted. Only paths
    # this run would actually create/overwrite must be clean.
    $overwritePaths = @($actions | Where-Object { $_.Action -ne 'SAME' } |
        ForEach-Object { $_.RelativePath })
    Assert-CleanManagedPaths -root $repoRoot -label 'TARGET' `
        -CandidateOverwritePaths $overwritePaths
    foreach ($m in $manifest.MarkerMerge) {
        Assert-MarkerTargetReady -repoRoot $repoRoot -merge $m
    }
    $missingIgnoreLines = @(Get-MissingGitIgnoreLines -repoRoot $repoRoot)
    $writePaths = @($actions | Where-Object { $_.Action -in @('NEW', 'UPDATE') } |
        ForEach-Object { $_.RelativePath })
    $markerTargets = @($manifest.MarkerMerge | ForEach-Object {
            "$($_.Target)".Replace('\', '/')
        } | Sort-Object -Unique)
    $transactionPaths = @($writePaths) + @($markerTargets) + @(
        'docs/ai/template-sync-state.json', '.gitignore')
    $preserveBytesPaths = @($markerTargets) + @('.gitignore')
    $preflightSnapshot = @(New-TargetTransactionSnapshot -repoRoot $repoRoot `
        -relativePaths $transactionPaths `
        -preserveBytesPaths $preserveBytesPaths)
    $plans += [pscustomobject]@{
        Root = $repoRoot
        OldTemplateCommit = $oldTemplateSha
        Actions = @($actions)
        MissingGitIgnoreLines = @($missingIgnoreLines)
        Snapshot = @($preflightSnapshot)
    }
    $baseLabel = if ([string]::IsNullOrWhiteSpace($oldTemplateSha)) {
        'none (safe bootstrap: differing existing files conflict)'
    } else {
        $oldTemplateSha.Substring(0, 7)
    }
    Write-Host "  PREFLIGHT $repoRoot : base=$baseLabel candidates=$($actions.Count)"
}
Write-Host "Preflight: $($resolvedRepos.Count) target(s) validated; no writes performed."
Write-Host ""

# Phase 2: only now may -Apply mutate targets.
foreach ($plan in $plans) {
    $repoRoot = $plan.Root
    Write-Host "=== $repoRoot ===" -ForegroundColor Cyan
    $snapshot = @($plan.Snapshot)
    if ($Apply) { Assert-TransactionSnapshotUnchanged -snapshot $snapshot }

    try {
        if ($Apply -and $plan.MissingGitIgnoreLines.Count -gt 0) {
            Set-TransactionAttempted -snapshot $snapshot -relativePath '.gitignore'
        }
        $gitIgnoreAdded = @(Sync-GitIgnoreLines -repoRoot $repoRoot `
            -MissingLines $plan.MissingGitIgnoreLines)
        if ($Apply -and $plan.MissingGitIgnoreLines.Count -gt 0) {
            Complete-TransactionWrite -snapshot $snapshot -relativePath '.gitignore'
        }
        foreach ($line in $gitIgnoreAdded) {
            Write-Host "  GITIGNORE ADD $line"
        }

        # Detect any still-ignored integration path after the additive repair.
        foreach ($sentinel in @('.claude/skills/pdf-ingestion/SKILL.md',
                'scripts/research/pdf_ingest.py')) {
            $ignored = Invoke-GitCapture -root $repoRoot -GitArgs @(
                'check-ignore', '-q', '--no-index', $sentinel) -AllowFailure
            if ($ignored.ExitCode -eq 0) {
                Write-Host "  WARNING: .gitignore ignores '$sentinel' - synced files will not be committable." -ForegroundColor Yellow
            }
        }

        $new = 0; $upd = 0; $same = 0
        foreach ($action in $plan.Actions) {
            $rel = $action.RelativePath
            Write-Host ("  {0,-6} {1}" -f $action.Action, $rel)
            switch ($action.Action) {
                'NEW' { $new++ }
                'UPDATE' { $upd++ }
                'SAME' { $same++; continue }
            }
            if ($Apply) {
                Set-TransactionAttempted -snapshot $snapshot -relativePath $rel
                if (-not $templateSourceBytes.ContainsKey($rel)) {
                    throw "Template source bytes were not frozen for '$rel'"
                }
                $dst = Get-SafeRepoPath -root $repoRoot -relativePath $rel
                $dstDir = Split-Path -Parent $dst
                if (-not (Test-Path -LiteralPath $dstDir)) {
                    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
                }
                $null = Get-SafeRepoPath -root $repoRoot -relativePath $rel
                [System.IO.File]::WriteAllBytes($dst, $templateSourceBytes[$rel])
                Complete-TransactionWrite -snapshot $snapshot -relativePath $rel
            }
        }

        foreach ($m in $manifest.MarkerMerge) {
            $markerRel = "$($m.Target)".Replace('\', '/')
            if ($Apply) {
                Set-TransactionAttempted -snapshot $snapshot -relativePath $markerRel
            }
            $result = Sync-MarkerBlock -repoRoot $repoRoot -merge $m
            if ($Apply -and $result -ne 'SAME') {
                Complete-TransactionWrite -snapshot $snapshot -relativePath $markerRel
            }
            if ($result -eq 'SAME') {
                Write-Host "  MARKER $($m.Target) [$($m.Block)]: up to date"
            } else {
                Write-Host "  MARKER $($m.Target) [$($m.Block)]: $result"
            }
        }

        Write-Host "  candidate files: $new new, $upd updated, $same already-current"
        if ($Apply) {
            # State is deliberately the final write in the target transaction.
            $stateRel = 'docs/ai/template-sync-state.json'
            Set-TransactionAttempted -snapshot $snapshot -relativePath $stateRel
            $statePath = Get-SafeRepoPath -root $repoRoot -relativePath $stateRel
            $stateDir = Split-Path -Parent $statePath
            if (-not (Test-Path -LiteralPath $stateDir)) {
                New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
            }
            $null = Get-SafeRepoPath -root $repoRoot -relativePath $stateRel
            $stateJson = "{`r`n" +
                "  `"templateCommit`": `"$templateSha`",`r`n" +
                "  `"syncedAt`": `"$(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss')`",`r`n" +
                "  `"tool`": `"sync-template-tools.ps1`"`r`n" +
                "}`r`n"
            [System.IO.File]::WriteAllText(
                $statePath, $stateJson, $utf8NoBom)
            Complete-TransactionWrite -snapshot $snapshot -relativePath $stateRel
            Write-Host "  state: docs/ai/template-sync-state.json -> $($templateSha.Substring(0,7))"

            Write-Host "  post-sync git status:"
            $postStatus = Invoke-GitCapture -root $repoRoot -GitArgs @('status', '--short')
            $postStatus.Output | ForEach-Object { Write-Host $_ }
            Write-Host "  -> review with: git -C `"$repoRoot`" diff"
        }
    }
    catch {
        $applyMessage = $_.Exception.Message
        if ($Apply -and $snapshot.Count -gt 0) {
            try {
                Restore-TargetTransaction -repoRoot $repoRoot -snapshot $snapshot
                Write-Host "  ROLLBACK restored exact pre-apply files for $repoRoot" -ForegroundColor Yellow
            }
            catch {
                throw "Target apply failed: $applyMessage; ROLLBACK INCOMPLETE: $($_.Exception.Message)"
            }
        }
        throw "Target apply failed and was rolled back: $applyMessage"
    }
    Write-Host ""
}

if (-not $Apply) {
    Write-Host "Dry-run complete. Re-run with -Apply to write changes." -ForegroundColor Yellow
}

# Don't leak the exit code of the last native command (e.g. check-ignore).
exit 0
