@{
    # Manifest for sync-template-tools.ps1 (template -> research repo, one-way).
    # Paths are relative to the repo root and use forward slashes.
    SchemaVersion = 1

    # Copied verbatim from template to target repo. Directories are copied
    # recursively; files that exist only in the target repo are NEVER deleted.
    Overwrite = @(
        '.claude/skills/README.md'
        '.claude/skills/check-missing-citations'
        '.claude/skills/citation-check'
        '.claude/skills/commit-push'
        '.claude/skills/math-proof-check'
        '.claude/skills/notation-refactor'
        '.claude/skills/overclaim-check'
        '.claude/skills/proofread-paper'
        '.claude/skills/proportional-fs'
        '.claude/skills/rename-papers'
        '.claude/skills/save-progress'
        '.claude/skills/sort-papers'
        '.claude/skills/translate-paper'
        '.claude/skills/pdf-ingestion'
        # Shared data catalog and path resolvers (data itself is NEVER in git;
        # these are docs + helpers only).
        'docs/data'
        'scripts/data'
        'docs/machine-setup.md'
        # PDF pipeline scripts, listed individually so the Edit/Write guard
        # never blocks a repo's own files elsewhere under scripts/research.
        'scripts/research/pdf_ingest.py'
        'scripts/research/pdf_quality_report.py'
        'scripts/research/pdf_make_query_packet.py'
        'scripts/research/pdf_render_page.py'
        'scripts/research/pdf_extract_figures.py'
        'scripts/research/pdf_extract_references.py'
        'scripts/research/pdf_build_citation_contexts.py'
        'scripts/research/pdf_pipeline_smoke_test.py'
    )

    # File name patterns never copied (applies inside Overwrite directories).
    # pre_edit_policy.py honors these too: a repo-local edit to an excluded
    # file is allowed even when its directory is Overwrite-managed.
    ExcludePatterns = @(
        '__pycache__'
        '*.pyc'
    )

    # Marker-based merge: only the region between
    #   <!-- BEGIN SHARED:<Block> ... -->  and  <!-- END SHARED:<Block> -->
    # in the target file is inserted/replaced. Target files are otherwise
    # repo-specific and must never be overwritten wholesale.
    MarkerMerge = @(
        @{
            Target = 'CLAUDE.md'
            Source = 'docs/ai/shared-claude-blocks.md'
            Block  = 'data-access'
        }
    )

    # Known shared assets that are intentionally NOT synced yet.
    # (pdf-ingestion P1-P3 was promoted to Overwrite on 2026-07-09 after the
    # P2/P3 commit passed the 36-check smoke test.)
    Deferred = @()
}
