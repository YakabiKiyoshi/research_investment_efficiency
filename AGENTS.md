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
- `data/raw/`: Original data, not committed
- `data/processed/`: Processed data, not committed
- `outputs/`: Generated outputs, not committed

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

- Do not commit data files.
- Do not commit generated outputs.
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
Data files themselves are NEVER committed to git (GitHub size limits and
licensing): copy small masters to `data/raw/`, extract only needed columns
from GB-scale files to `data/processed/*.parquet`, and record repo-local
copies in the repo's own `docs/data-sources.md`. Backup of `C:\Data` goes
to Google Drive (5TB), not GitHub.

## Data policy

Do not add these to git:

- `data/`
- `outputs/`
- `paper/build/`
- `.env`
- credentials
- API keys
- tokens
- local Claude or Codex state

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
4. Do not commit data or outputs unless explicitly requested.

For paper work:

1. Edit files under `paper/`.
2. Build with `bash scripts/build-pdf.sh`.
3. Keep generated PDF and build files out of git unless explicitly requested.
