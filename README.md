# Agentic Readiness Assessment - MVP

Deterministic scoring engine MVP with:
- Custom rubric support with global fallback
- Confidence gate (blocks final score if confidence < 70)
- Regression mode (compare with previous report)
- CLI-only visualization

## Project Structure
- `python/src/agentic_readiness`: scoring engine and Python CLI
- `node/cli/report.js`: terminal report renderer
- `fixtures`: sample input and previous report
- `scripts/run_mvp.sh`: run end-to-end scoring and CLI output
- `scripts/run_feed_demo.sh`: score real Merchant XML/CSV/JSON fixtures
- `scripts/score_customer_url.sh`: fetch + score any live customer URL
- `scripts/test.sh`: run tests + render sample custom-rubric report

## Run MVP
```bash
./scripts/run_mvp.sh
```

## Run Tests
```bash
./scripts/test.sh
```

## Run Merchant Feed Demo
```bash
./scripts/run_feed_demo.sh
```

## Test Any Customer URL From CLI
Option 1 (recommended one-liner script):
```bash
./scripts/score_customer_url.sh "https://example.com/product-or-collection-page"
```

With custom output path:
```bash
./scripts/score_customer_url.sh "https://example.com/product-or-collection-page" ./out/my_customer_report.json
```

Option 2 (direct Python CLI + Node renderer):
```bash
export PYTHONPATH=$(pwd)/python/src
python3 -m agentic_readiness.cli score-url \
  --url "https://example.com/product-or-collection-page" \
  --output ./out/report_url.json

node ./node/cli/report.js ./out/report_url.json
```

With custom rubric:
```bash
export PYTHONPATH=$(pwd)/python/src
python3 -m agentic_readiness.cli score-url \
  --url "https://example.com/product-or-collection-page" \
  --rubric ./fixtures/custom_rubric.json \
  --output ./out/report_url_custom.json
```

## Python CLI
```bash
export PYTHONPATH=$(pwd)/python/src
python3 -m agentic_readiness.cli score \
  --input ./fixtures/products.json \
  --input-type auto \
  --output ./out/report.json \
  [--rubric ./fixtures/custom_rubric.json] \
  [--previous ./fixtures/previous_report.json]
```

For URL scoring:
```bash
python3 -m agentic_readiness.cli score-url \
  --url "https://example.com/product-or-collection-page" \
  --output ./out/report_url.json \
  [--rubric ./fixtures/custom_rubric.json] \
  [--previous ./out/older_report.json] \
  [--timeout-sec 30]
```

For real feed ingestion set:
- `--input-type merchant_xml`
- `--input-type merchant_csv`
- `--input-type merchant_json`

Input format is JSON with either:
- `{ "products": [ ... ] }`
- `[ ... ]`

Each product contains normalized extracted signals used by the rule engine.

## Deploy on Railway

See [docs/deployment.md](docs/deployment.md) for step-by-step instructions. Summary:

1. Connect the repo to [Railway](https://railway.app/), add a Postgres plugin, and set `DATABASE_URL` (and optional API keys for the AI Visibility tab).
2. Run migrations once (Release Command or one-off): `./scripts/migrate_visibility.sh` or `python scripts/run_migrations.py`.
3. Deploy using the repo Dockerfile (builds frontend, serves with gunicorn). Playwright + Chromium are installed in the image, so browser fallback works for bot-protected URLs.
