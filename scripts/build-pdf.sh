#!/usr/bin/env bash
set -euo pipefail

cd /workspace/paper
mkdir -p build
latexmk -lualatex -interaction=nonstopmode -synctex=1 -outdir=build main.tex