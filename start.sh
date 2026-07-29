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




COMPOSE_FILE="$ROOT_DIR/opensearch/docker-compose-nginx.yml"
NEW_PATH="$DATA_DIR/opensearch"
CONTAINER_PATH="/usr/share/opensearch/data"

echo "OpenSearch folder: $NEW_PATH"

# =========================================================
# Validation
# =========================================================

if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "Error: Compose file not found: $COMPOSE_FILE" >&2
    exit 1
fi

if [[ -z "$NEW_PATH" ]]; then
    echo "Error: NEW_PATH cannot be empty." >&2
    exit 1
fi

if [[ "$NEW_PATH" != /* ]]; then
    echo "Error: NEW_PATH must be an absolute path: $NEW_PATH" >&2
    exit 1
fi

# Remove trailing slash
NEW_PATH="${NEW_PATH%/}"

# Check only for the container destination.
# The existing host path can be anything.
if ! grep -Fq ":${CONTAINER_PATH}" "$COMPOSE_FILE"; then
    echo "Error: No volume mapping was found for:" >&2
    echo "  $CONTAINER_PATH" >&2
    exit 1
fi

# =========================================================
# Back up and update Compose file
# =========================================================

BACKUP_FILE="${COMPOSE_FILE}.backup"
TEMP_FILE="${COMPOSE_FILE}.tmp"

cp "$COMPOSE_FILE" "$BACKUP_FILE"
TEMP_FILE="${COMPOSE_FILE}.tmp"

awk \
    -v new_path="$NEW_PATH" \
    -v container_path="$CONTAINER_PATH" '
{
    line = $0
    destination = ":" container_path
    position = index(line, destination)

    # Update any volume whose container destination is:
    # /usr/share/opensearch/data
    if (line ~ /^[[:space:]]*-[[:space:]]*/ && position > 0) {
        # Preserve indentation, dash, spaces, and an optional opening quote.
        match(line, /^[[:space:]]*-[[:space:]]*"?/)
        prefix = substr(line, 1, RLENGTH)

        # Preserve anything after the container path, such as :ro or a quote.
        suffix = substr(line, position + length(destination))

        print prefix new_path destination suffix
        updated++
        next
    }

    print
}

END {
    if (updated == 0) {
        print "Error: No OpenSearch data volume was updated." > "/dev/stderr"
        exit 1
    }
}
' "$COMPOSE_FILE" > "$TEMP_FILE"

mv "$TEMP_FILE" "$COMPOSE_FILE"

echo
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





# # =========================================================
# # Update Indexer .env file  
# # =========================================================

ENV_FILE="$ROOT_DIR/indexer/.env"

NEW_INPUT_ROOT="$ROOT_DIR/data/users"
NEW_OUTPUT_ROOT="$ROOT_DIR/data/users"

# =========================================================
# Validation
# =========================================================

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: .env file not found: $ENV_FILE" >&2
    exit 1
fi

if [[ -z "$NEW_INPUT_ROOT" || -z "$NEW_OUTPUT_ROOT" ]]; then
    echo "Error: Input and output paths cannot be empty." >&2
    exit 1
fi

if [[ "$NEW_INPUT_ROOT" != /* || "$NEW_OUTPUT_ROOT" != /* ]]; then
    echo "Error: Input and output paths must be absolute paths." >&2
    exit 1
fi

if ! grep -q '^DOCUMIND_INPUT_ROOT_HOST=' "$ENV_FILE"; then
    echo "Error: DOCUMIND_INPUT_ROOT_HOST does not exist in $ENV_FILE" >&2
    exit 1
fi

if ! grep -q '^DOCUMIND_OUTPUT_ROOT_HOST=' "$ENV_FILE"; then
    echo "Error: DOCUMIND_OUTPUT_ROOT_HOST does not exist in $ENV_FILE" >&2
    exit 1
fi


# =========================================================
# Back up and update the existing lines
# =========================================================

BACKUP_FILE="${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
cp "$ENV_FILE" "$BACKUP_FILE"

TEMP_FILE="$(mktemp "${ENV_FILE}.tmp.XXXXXX")"

awk \
    -v input_root="$NEW_INPUT_ROOT" \
    -v output_root="$NEW_OUTPUT_ROOT" '
BEGIN {
    input_updated = 0
    output_updated = 0
}

/^DOCUMIND_INPUT_ROOT_HOST=/ {
    print "DOCUMIND_INPUT_ROOT_HOST=" input_root
    input_updated = 1
    next
}

/^DOCUMIND_OUTPUT_ROOT_HOST=/ {
    print "DOCUMIND_OUTPUT_ROOT_HOST=" output_root
    output_updated = 1
    next
}

{
    print
}

END {
    if (!input_updated || !output_updated) {
        exit 1
    }
}
' "$ENV_FILE" > "$TEMP_FILE"

mv "$TEMP_FILE" "$ENV_FILE"

echo "Updated existing variables successfully:"
echo "  DOCUMIND_INPUT_ROOT_HOST=$NEW_INPUT_ROOT"
echo "  DOCUMIND_OUTPUT_ROOT_HOST=$NEW_OUTPUT_ROOT"
echo
echo "Backup created at:"
echo "  $BACKUP_FILE"