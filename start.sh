#!/usr/bin/env bash
set -Eeuo pipefail


# ---------------------------------------------------
# Creating a Directory for saving data  (current directory/data)
# ---------------------------------------------------

ROOT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"
cd "$ROOT_DIR"
DATA_DIR="$ROOT_DIR/data"


echo "Creating data folder..."

mkdir -p "$DATA_DIR"
echo "Data folder: $DATA_DIR"


# ---------------------------------------------------
# Set up PostgreSQL .env file 
# ---------------------------------------------------

#!/usr/bin/env bash


echo "Creating postgreSQL folder..."

mkdir -p "$DATA_DIR/postgreSQL"
echo "postgreSQL folder: $DATA_DIR/postgreSQL"



# Change these paths as needed
TARGET_DIR="postgreSQL"


cd "$ROOT_DIR/$TARGET_DIR"

# Create or overwrite the .env file
cat > .env <<EOF
POSTGRES_USER=documind
POSTGRES_PASSWORD=documind12345678
POSTGRES_DB=documind_postgresql


PG_PORT=5433
PGBOUNCER_PORT=6433
DATA_DIR=$DATA_DIR/postgreSQL
EOF

# Restrict access because the file contains a password
chmod 600 .env

echo "Created: $TARGET_DIR/.env"




# ---------------------------------------------------
# Update Volume directory for opensearch 
# ---------------------------------------------------


echo "Creating opensearch folder..."

mkdir -p "$DATA_DIR/opensearch"
echo "opensearch folder: $DATA_DIR/opensearch"


# =========================
# Configuration
# =========================

COMPOSE_FILE="$ROOT_DIR/opensearch/docker-compose-nginx.yml"

# Change this value to the directory where OpenSearch data should be saved

NEW_PATH="$DATA_DIR/opensearch"
echo $NEW_PATH
OLD_PATH="../data/opensearch"
CONTAINER_PATH="/usr/share/opensearch/data"

# =========================
# Validation
# =========================

if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "Error: Compose file not found: $COMPOSE_FILE" >&2
    exit 1
fi

if [[ -z "$NEW_PATH" ]]; then
    echo "Error: NEW_PATH cannot be empty." >&2
    exit 1
fi

if [[ "$NEW_PATH" != /* ]]; then
    echo "Error: NEW_PATH must be an absolute path." >&2
    exit 1
fi

# Remove a trailing slash
NEW_PATH="${NEW_PATH%/}"

if ! grep -Fq "${OLD_PATH}:${CONTAINER_PATH}" "$COMPOSE_FILE"; then
    echo "Error: Could not find this volume mapping:"
    echo "  ${OLD_PATH}:${CONTAINER_PATH}"
    exit 1
fi

# =========================
# Create directory
# =========================

mkdir -p "$NEW_PATH"

# Set the permissions required by OpenSearch
chown -R 1000:1000 "$NEW_PATH"
chmod -R u+rwX "$NEW_PATH"

# =========================
# Update Compose file
# =========================

BACKUP_FILE="${COMPOSE_FILE}.backup"
cp "$COMPOSE_FILE" "$BACKUP_FILE"

awk \
    -v old_path="$OLD_PATH" \
    -v new_path="$NEW_PATH" \
    -v container_path="$CONTAINER_PATH" '
{
    volume_mapping = old_path ":" container_path

    if (index($0, volume_mapping) > 0) {
        sub(old_path ":" container_path,
            new_path ":" container_path)
    }

    print
}
' "$COMPOSE_FILE" > "${COMPOSE_FILE}.tmp"

mv "${COMPOSE_FILE}.tmp" "$COMPOSE_FILE"

echo "OpenSearch configuration updated successfully."
echo "Data directory: $NEW_PATH"
echo "Compose file:   $COMPOSE_FILE"
echo "Backup file:    $BACKUP_FILE"






# ---------------------------------------------------
# Update PaperMind .env file  
# ---------------------------------------------------


echo "Adding data diretory in paperMind env file"

ENV_FILE="$ROOT_DIR/paperMind/.env"
touch "$ENV_FILE"

# Remove an existing DATA_DIR entry, then add the current value.
sed -i.bak '/^HOST_ACCESS_ROOT=/d' "$ENV_FILE"
printf 'HOST_ACCESS_ROOT=%s\n' "$DATA_DIR" >> "$ENV_FILE"
rm -f "$ENV_FILE.bak"

echo "Saved HOST_ACCESS to $ENV_FILE for paperMind"


