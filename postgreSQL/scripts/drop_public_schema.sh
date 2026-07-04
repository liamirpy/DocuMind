#!/usr/bin/env bash
set -euo pipefail

# WARNING:
# This deletes everything inside the public schema.
# Use this only in development.
#
# Run:
#   bash scripts/drop_public_schema.sh

if [ ! -f ".env" ]; then
  echo "ERROR: .env file not found. Copy .env.example to .env first."
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

echo "WARNING: This will delete all tables, sequences, indexes, triggers, functions, and extensions inside public."
echo "Database: ${POSTGRES_DB}"
echo "Host: localhost:${PG_PORT}"
echo
read -r -p "Type RESET to continue: " CONFIRM

if [ "${CONFIRM}" != "RESET" ]; then
  echo "Cancelled."
  exit 0
fi

PGPASSWORD="${POSTGRES_PASSWORD}" psql \
  -h 127.0.0.1 \
  -p "${PG_PORT}" \
  -U "${POSTGRES_USER}" \
  -d "${POSTGRES_DB}" \
  -v ON_ERROR_STOP=1 \
  <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;

-- Optional but useful for normal local development behavior.
GRANT ALL ON SCHEMA public TO public;
SQL

echo "Public schema dropped and recreated."
