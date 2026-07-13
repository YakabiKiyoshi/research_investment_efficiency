# CLAUDE.md

Read `AGENTS.md` first. Treat it as the primary project instruction file.

This repository packages literature-based capital and labor investment-efficiency
measures for reuse across empirical-accounting projects. It retains the shared
Docker research environment for Python, R, and Japanese/English LaTeX.

Follow these rules:

- Do not commit or expose data, outputs, credentials, tokens, or API keys.
- Do not change Docker base images without asking first.
- Do not modify unrelated files.
- Keep Dockerfiles UTF-8 without BOM.
- Prefer small, reviewable edits.
- After editing, report changed files and validation commands.
- If an environment file changes, state which Dev Container must be rebuilt.

Important paths:

- Python environment: `.devcontainer/python/`, `docker/python/Dockerfile`, `requirements.txt`
- R environment: `.devcontainer/r/`, `docker/r/Dockerfile`
- TeX environment: `.devcontainer/tex/`, `docker/tex/Dockerfile`, `paper/`, `scripts/build-pdf.sh`
- Project root inside containers: `/workspace`

Validation commands:

Python:

    python -c "import pandas as pd; import sklearn; import duckdb; print('Python OK')"

R:

    R -e "library(renv); library(languageserver); library(IRkernel); print('R OK')"

TeX:

    bash scripts/build-pdf.sh
