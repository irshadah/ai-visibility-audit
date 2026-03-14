#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/python/src"

python3 -m agentic_readiness.cli score \
  --input "$ROOT_DIR/fixtures/feed.xml" \
  --input-type merchant_xml \
  --output "$ROOT_DIR/out/report_feed_xml.json"

python3 -m agentic_readiness.cli score \
  --input "$ROOT_DIR/fixtures/feed.csv" \
  --input-type merchant_csv \
  --output "$ROOT_DIR/out/report_feed_csv.json"

python3 -m agentic_readiness.cli score \
  --input "$ROOT_DIR/fixtures/feed.json" \
  --input-type merchant_json \
  --output "$ROOT_DIR/out/report_feed_json.json"

node "$ROOT_DIR/node/cli/report.js" "$ROOT_DIR/out/report_feed_xml.json"
node "$ROOT_DIR/node/cli/report.js" "$ROOT_DIR/out/report_feed_csv.json"
node "$ROOT_DIR/node/cli/report.js" "$ROOT_DIR/out/report_feed_json.json"
