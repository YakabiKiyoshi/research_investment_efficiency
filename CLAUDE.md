# CLAUDE.md

Read `AGENTS.md` first. Treat it as the primary project instruction file.

This repository packages literature-based capital and labor investment-efficiency
measures for reuse across empirical-accounting projects. It uses native local environments for Python, R, and Japanese/English LaTeX.

Follow these rules:

- Do not commit or expose data, outputs, credentials, tokens, or API keys.
- Do not modify unrelated files.
- Prefer small, reviewable edits.
- After editing, report changed files and validation commands.
- If an environment file changes, state which native dependencies must be refreshed.

Important paths:

- Python environment: `.venv/`, `requirements.txt`, and `pyproject.toml` (when present)
- R environment: `renv.lock` and `renv/` (when present)
- TeX environment: `paper/` and `scripts/build-pdf.sh`
- Project root: repository root

Validation commands:

Python:

    python -c "import pandas as pd; import sklearn; import duckdb; print('Python OK')"

R:

    R -e "library(renv); library(languageserver); library(IRkernel); print('R OK')"

TeX:

    bash scripts/build-pdf.sh
