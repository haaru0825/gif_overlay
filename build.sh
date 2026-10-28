#!/usr/bin/env bash
# Linux / macOS: build a standalone binary (calls build.py inside a throwaway venv)
set -euo pipefail
cd "$(dirname "$0")"

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python build.py
