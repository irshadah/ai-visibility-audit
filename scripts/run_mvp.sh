#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/python/src"
python3 -m agentic_readiness.cli score \
  --input "$ROOT_DIR/fixtures/products.json" \
  --previous "$ROOT_DIR/fixtures/previous_report.json" \
  --output "$ROOT_DIR/out/report.json"

node "$ROOT_DIR/node/cli/report.js" "$ROOT_DIR/out/report.json"
