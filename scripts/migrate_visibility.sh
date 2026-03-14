#!/usr/bin/env bash
set -euo pipefail

# Load .env if present (so DATABASE_URL etc. are available)
if [ -f ".env" ]; then
  # shellcheck disable=SC2046
  export $(grep -v '^#' .env | xargs || true)
fi

DB_URL="${DATABASE_URL:-}"

if [ -z "$DB_URL" ]; then
  echo "ERROR: DATABASE_URL is not set. Please set it in .env or your shell."
  exit 1
fi

echo "Using DATABASE_URL=$DB_URL"

# Extract DB name from the URL (last path segment)
DB_NAME="${DB_URL##*/}"

if [ -z "$DB_NAME" ]; then
  echo "ERROR: Could not parse database name from DATABASE_URL."
  exit 1
fi

echo "Ensuring database '$DB_NAME' exists..."
if createdb "$DB_NAME" 2>/dev/null; then
  echo "Created database '$DB_NAME'."
else
  echo "Database '$DB_NAME' already exists or cannot be created (continuing)."
fi

echo "Applying visibility schema..."
psql "$DB_URL" -f scripts/sql/visibility_schema.sql

echo "Migration completed."

