#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/python/src"
python3 -m unittest discover -s python/tests -p 'test_*.py' -v

python3 -m agentic_readiness.cli score \
  --input "$ROOT_DIR/fixtures/products.json" \
  --rubric "$ROOT_DIR/fixtures/custom_rubric.json" \
  --previous "$ROOT_DIR/fixtures/previous_report.json" \
  --output "$ROOT_DIR/out/report_custom.json"

node "$ROOT_DIR/node/cli/report.js" "$ROOT_DIR/out/report_custom.json"
