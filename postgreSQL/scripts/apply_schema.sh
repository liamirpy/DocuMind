#!/usr/bin/env bash
set -euo pipefail

# Run this from the project root:
#   bash scripts/apply_schema.sh

if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found. Copy .env.example to .env first."
  exit 1
fi

if [ ! -f "schema.sql" ]; then
  echo "ERROR: schema.sql file not found in the project root."
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql is not installed."
  echo "Install it on Ubuntu/Debian with:"
  echo "  sudo apt update && sudo apt install -y postgresql-client"
  exit 1
fi

set -a
source .env
set +a

: "${POSTGRES_USER:?POSTGRES_USER is missing in .env}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is missing in .env}"
: "${POSTGRES_DB:?POSTGRES_DB is missing in .env}"
: "${PG_PORT:=5432}"

echo "Checking PostgreSQL connection on localhost:${PG_PORT}..."

for i in {1..30}; do
  if PGPASSWORD="${POSTGRES_PASSWORD}" pg_isready -h 127.0.0.1 -p "${PG_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    break
  fi

  if [ "$i" -eq 30 ]; then
    echo "ERROR: PostgreSQL is not ready after waiting."
    exit 1
  fi

  sleep 2
done

echo "Applying schema.sql to database ${POSTGRES_DB}..."

PGPASSWORD="${POSTGRES_PASSWORD}" psql \
  -h 127.0.0.1 \
  -p "${PG_PORT}" \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  -v ON_ERROR_STOP=1 \
  -f ./schema.sql

echo "Schema applied successfully."
