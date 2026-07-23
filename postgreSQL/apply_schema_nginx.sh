#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

ENV_FILE="$SCRIPT_DIR/.env"
SCHEMA_FILE="$SCRIPT_DIR/schema.sql"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: Environment file not found:"
  echo "  $ENV_FILE"
  exit 1
fi

if [[ ! -f "$SCHEMA_FILE" ]]; then
  echo "ERROR: Schema file not found:"
  echo "  $SCHEMA_FILE"
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "ERROR: psql is not installed."
  echo
  echo "Install it on Ubuntu/Debian with:"
  echo "  sudo apt update"
  echo "  sudo apt install -y postgresql-client"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${POSTGRES_USER:?POSTGRES_USER is missing in .env}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is missing in .env}"
: "${POSTGRES_DB:?POSTGRES_DB is missing in .env}"

# These can be overridden when running the script.
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-15432}"

echo "Checking PostgreSQL through ${DB_HOST}:${DB_PORT}..."

POSTGRES_READY=false

for attempt in $(seq 1 30); do
  if PGPASSWORD="$POSTGRES_PASSWORD" pg_isready \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    >/dev/null 2>&1
  then
    POSTGRES_READY=true
    break
  fi

  echo "PostgreSQL is not ready: attempt ${attempt}/30"
  sleep 2
done

if [[ "$POSTGRES_READY" != "true" ]]; then
  echo "ERROR: PostgreSQL did not become ready."
  exit 1
fi

echo "Applying schema to database: $POSTGRES_DB"

PGPASSWORD="$POSTGRES_PASSWORD" psql \
  --host="$DB_HOST" \
  --port="$DB_PORT" \
  --username="$POSTGRES_USER" \
  --dbname="$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --file="$SCHEMA_FILE"

echo "Schema applied successfully."