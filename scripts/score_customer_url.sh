#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: ./scripts/score_customer_url.sh <URL> [output_json]"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
URL="$1"
OUTPUT="${2:-$ROOT_DIR/out/report_url.json}"

cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR/python/src"

python3 -m agentic_readiness.cli score-url \
  --url "$URL" \
  --output "$OUTPUT"

node "$ROOT_DIR/node/cli/report.js" "$OUTPUT"
