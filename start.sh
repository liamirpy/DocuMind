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

echo "Saved DATA_DIR to $ENV_FILE for PostgreSQL"






echo "Creating user data (uploding) directory"

mkdir -p "$DATA_DIR/users"

echo "Data folder: $DATA_DIR/users"

echo "Adding data diretory in Node js env file"

ENV_FILE="$ROOT_DIR/backend-api/.env"
touch "$ENV_FILE"

# Remove an existing DATA_DIR entry, then add the current value.
sed -i.bak '/^UPLOAD_DIR=/d' "$ENV_FILE"
printf 'UPLOAD_DIR=%s\n' "$DATA_DIR/users" >> "$ENV_FILE"
rm -f "$ENV_FILE.bak"

echo "Saved UPLOAD_DIR to $ENV_FILE for PostgreSQL"










echo "Starting PostgreSQL/pgbouncer and public Nginx..."

"${DOCKER[@]}" compose up \
  -d \
  postgres \
  pgbouncer \
  public-nginx \
  api


chmod +x "$ROOT_DIR/postgreSQL/apply_schema_nginx.sh"
bash "$ROOT_DIR/postgreSQL/apply_schema_nginx.sh"

echo
echo "Container status:"

"${DOCKER[@]}" compose ps



