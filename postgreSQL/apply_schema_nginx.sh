#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

PROJECT_DIR="$(
  cd -- "$SCRIPT_DIR/.."
  pwd
)"

SCHEMA_FILE="$SCRIPT_DIR/schema.sql"

# Change this if your PostgreSQL service has another name,
# such as postgresql, db, or database.
POSTGRES_SERVICE="${POSTGRES_SERVICE:-postgres}"

if [[ ! -f "$SCHEMA_FILE" ]]; then
  echo "ERROR: Schema file not found:"
  echo "  $SCHEMA_FILE"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed."
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "ERROR: sudo is not installed."
  exit 1
fi

cd "$PROJECT_DIR"

echo "Checking Docker permissions..."

if ! sudo docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is not running or sudo cannot access Docker."
  echo
  echo "Try:"
  echo "  sudo systemctl start docker"
  exit 1
fi

if ! sudo docker compose config --services | grep -Fxq "$POSTGRES_SERVICE"; then
  echo "ERROR: PostgreSQL Compose service '$POSTGRES_SERVICE' was not found."
  echo
  echo "Available services:"
  sudo docker compose config --services
  echo
  echo "Run the script with the correct service name, for example:"
  echo "  POSTGRES_SERVICE=postgresql sudo -E $0"
  exit 1
fi

echo "Starting PostgreSQL service: $POSTGRES_SERVICE"

sudo docker compose up -d "$POSTGRES_SERVICE"

echo "Waiting for PostgreSQL..."

POSTGRES_READY=false

for attempt in $(seq 1 30); do
  if sudo docker compose exec -T "$POSTGRES_SERVICE" \
    sh -c 'pg_isready \
      --username "$POSTGRES_USER" \
      --dbname "$POSTGRES_DB"' \
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
  echo
  echo "Recent PostgreSQL logs:"
  sudo docker compose logs --tail=100 "$POSTGRES_SERVICE"
  exit 1
fi

echo "Applying schema to PostgreSQL..."

sudo docker compose exec -T "$POSTGRES_SERVICE" \
  sh -c 'psql \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --set=ON_ERROR_STOP=1' \
  < "$SCHEMA_FILE"

echo "Schema applied successfully."
