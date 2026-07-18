# AGENTS.md

This repository uses the reproducible research environment defined by
`research-template` (canonical source; instantiated per research project).

## Purpose

This project provides a reusable Python package for investment-efficiency
measurement, together with reproducible native environments for:

- Python analysis
- R analysis
- Japanese and English LaTeX document builds

The main goal is reproducibility across multiple Windows 11 PCs using local Python, R, and TeX installations.

## Repository structure

- `notebooks/python/`: Python notebooks
- `notebooks/r/`: R notebooks
- `src/investment_efficiency/`: reusable Python package
- `tests/`: data-free unit and CLI tests
- `docs/`: literature survey, methodology, schema, and provenance
- `examples/`: executable usage examples
- `src/python/`: project-specific Python scripts, if later needed
- `src/r/`: R scripts
- `paper/`: LaTeX source files
- `scripts/`: Utility scripts
- `data/raw/`: Original or repository-scoped input data
- `data/processed/`: Processed data and reproducibility artifacts
- `outputs/`: Generated figures, tables, models, and audit artifacts

## Environments

### Python

Use the host Python installation. Prefer a repository-local `.venv` when one
is present.

Expected checks:

    python --version
    python -c "import pandas as pd; import sklearn; import duckdb; print('Python OK')"

### R

Use the host R installation and restore project packages with `renv` when the
repository provides a lockfile.

Expected checks:

    R --version
    R -e "library(renv); library(languageserver); library(IRkernel); print('R OK')"

### TeX

Use the host TeX installation.

Expected checks:

    lualatex --version
    latexmk --version
    biber --version

Build PDF:

    bash scripts/build-pdf.sh

Expected output:

    paper/build/main.pdf

## Rules for editing

- Treat data files and generated outputs as normal project artifacts and tracking candidates.
- Do not avoid data work merely because the files are absent from GitHub.
- Do not commit credentials, API keys, tokens, or local AI-tool state.
- Prefer small, explicit changes.
- Do not silently change the project structure.
- When changing environment files, state which native dependencies must be refreshed.
- When changing `requirements.txt`, rerun the Python validation.
- When changing LaTeX source, test with `bash scripts/build-pdf.sh`.

## Git policy

Before editing, check:

    git status

After editing, summarize:

- files changed
- reason for change
- validation commands run
- whether native environment refresh is required

Use clear commit messages.

## Data resources (shared catalog)

External database resources (NEEDS-FinancialQUEST, eol, NEEDS disc data,
EDINET XBRL) live under `C:\Data` (layout v2, 2026-07-12) and are documented
in `docs/data/data-catalog.md` (synced from research-template). Acquisition
and processing code lives in the `data-pipeline` sibling repository.
Resolve paths with `scripts/data/data_paths.py` (Python) or
`scripts/data/data_paths.R` (R) using the keys in `docs/data/data-paths.json`
— never hardcode physical paths (the folder layout may change; only the
registry is updated, keys stay stable). Root override: `RESEARCH_DATA_ROOT`.
GitHub absence does not mean that data are unavailable and must not be used as
a reason to skip data access, processing, validation, generation, or tracking.
Do not blanket-ignore `data/` or `outputs/`: files below GitHub's 100MB hard
per-file limit are tracking candidates. Handle only actual files at or above
100MB, secrets, and non-redistributable source material individually. Record
repo-local copies in `docs/data-sources.md`; the `C:\Data` backup remains on
Google Drive (5TB).

## Data policy

Do not add secrets, credentials, API keys, tokens, or local Claude/Codex state
to git. Data, outputs, and paper artifacts are not blanket exclusions. Files at
or above 100MB require an explicit per-file handling decision because GitHub
cannot accept them through normal Git.

## AI-tool policy

Claude Code and Codex CLI may be used in this repository.

AI tools should:

- read `README.md` and `AGENTS.md` before making changes
- avoid modifying unrelated files
- ask before deleting files
- ask before adding large dependencies
- avoid embedding secrets in scripts, notebooks, or LaTeX files

## Current preferred workflow

For environment work:

1. Edit the dependency manifest or native setup script.
2. Refresh the relevant local dependencies.
3. Run the environment check.
4. Commit the change.

For analysis work:

1. Put reusable code in `src/`.
2. Use notebooks for exploration.
3. Write generated figures and tables to `outputs/`.
4. Keep data and outputs visible to git unless a specific file is excluded for a concrete reason.

For paper work:

1. Edit files under `paper/`.
2. Build with `bash scripts/build-pdf.sh`.
3. Treat generated PDF and build files as tracking candidates when they aid reproducibility.
