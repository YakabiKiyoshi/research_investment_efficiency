#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
cd "$PROJECT_ROOT/paper"
mkdir -p build
latexmk -lualatex -interaction=nonstopmode -synctex=1 -outdir=build main.tex
