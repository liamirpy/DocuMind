#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

cd "$ROOT_DIR"

DATA_DIR="$ROOT_DIR/data"

echo "Creating data folder..."

mkdir -p "$DATA_DIR"
echo "Data folder: $DATA_DIR"






if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
else
  DOCKER=(sudo docker)
fi

echo "Validating Compose configuration..."

"${DOCKER[@]}" compose config --quiet

echo "Building Nginx..."

"${DOCKER[@]}" compose build public-nginx







echo "Creating PosgreSQL data directory"

mkdir -p "$DATA_DIR/postgreSQL"

echo "Data folder: $DATA_DIR/postgreSQL"

echo "Adding data diretory in PostgreSQL env file"

ENV_FILE="$ROOT_DIR/postgreSQL/.env"
touch "$ENV_FILE"

# Remove an existing DATA_DIR entry, then add the current value.
sed -i.bak '/^DATA_DIR=/d' "$ENV_FILE"
printf 'DATA_DIR=%s\n' "$DATA_DIR/postgreSQL" >> "$ENV_FILE"
rm -f "$ENV_FILE.bak"

echo "Saved DATA_DIR to $ENV_FILE"







echo "Starting PostgreSQL/pgbouncer and Nginx..."

"${DOCKER[@]}" compose up \
  -d \
  postgres \
  pgbouncer \
  public-nginx \
  api

# echo "Applying PostgreSQL schema through Nginx..."
# echo $ROOT_DIR
# DB_HOST=127.0.0.1 \
# DB_PORT=15432 \
# bash "$ROOT_DIR/postgreSQL/apply_schema_nginx.sh"

# echo
# echo "Container status:"

"${DOCKER[@]}" compose ps

# echo
# echo "PostgreSQL is available through:"
# echo "  127.0.0.1:15432"




# echo "Starting pdf-analyser (PaperMind)"
