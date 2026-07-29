#!/usr/bin/env bash

set -Eeuo pipefail


# ============================================================
# Project paths
# ============================================================

SCRIPT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

ROOT_DIR="$(
  cd -- "$SCRIPT_DIR/.."
  pwd
)"

# Change this if your main Compose file has another filename.
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.yml}"

TEMPLATE_FILE="$SCRIPT_DIR/index-template.json"

DATA_DIRECTORY="$ROOT_DIR/data/opensearch"


# ============================================================
# OpenSearch configuration
# ============================================================

# This URL is used by curl running INSIDE the OpenSearch
# container, not from the Docker host.
OPENSEARCH_INTERNAL_URL="https://127.0.0.1:9200"

OPENSEARCH_USERNAME="${OPENSEARCH_USERNAME:-admin}"

OPENSEARCH_PASSWORD="${OPENSEARCH_PASSWORD:-DOCUMIND_opensearch_password_2026}"

OPENSEARCH_SERVICE="${OPENSEARCH_SERVICE:-opensearch}"

TEMPLATE_NAME="${TEMPLATE_NAME:-documind-chunks-template}"

INDEX_NAME="${INDEX_NAME:-documind-chunks-v1}"


# ============================================================
# Select Docker command
# ============================================================

if docker info >/dev/null 2>&1; then
  DOCKER=(docker)
else
  DOCKER=(sudo docker)
fi


COMPOSE=(
  "${DOCKER[@]}"
  compose
  -f "$COMPOSE_FILE"
)


# ============================================================
# Helper functions
# ============================================================

opensearch_curl() {
  "${COMPOSE[@]}" exec -T "$OPENSEARCH_SERVICE" \
    curl \
      --insecure \
      --user "${OPENSEARCH_USERNAME}:${OPENSEARCH_PASSWORD}" \
      "$@"
}


show_opensearch_logs() {
  "${COMPOSE[@]}" logs \
    --tail=200 \
    "$OPENSEARCH_SERVICE"
}


# ============================================================
# Validate required files and commands
# ============================================================

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 is not installed." >&2
  exit 1
fi


if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: Main Compose file does not exist:" >&2
  echo "  $COMPOSE_FILE" >&2
  echo >&2
  echo "Set COMPOSE_FILE when using another filename:" >&2
  echo "  COMPOSE_FILE=/srv/DocuMind/compose.yaml $0" >&2

  exit 1
fi


if [[ ! -f "$TEMPLATE_FILE" ]]; then
  echo "ERROR: Template file does not exist:" >&2
  echo "  $TEMPLATE_FILE" >&2

  exit 1
fi


echo "Validating index-template.json..."

python3 -m json.tool \
  "$TEMPLATE_FILE" \
  >/dev/null

echo "Template JSON is valid."


# ============================================================
# Validate Docker Compose configuration
# ============================================================

echo "Validating Docker Compose configuration..."

"${COMPOSE[@]}" config --quiet


if ! "${COMPOSE[@]}" config --services |
  grep -Fxq "$OPENSEARCH_SERVICE"
then
  echo "ERROR: OpenSearch service was not found in:" >&2
  echo "  $COMPOSE_FILE" >&2

  exit 1
fi


echo "Compose configuration is valid."


# ============================================================
# Configure Linux for OpenSearch
# ============================================================

echo "Configuring vm.max_map_count..."

sudo sysctl \
  -w vm.max_map_count=262144 \
  >/dev/null


# ============================================================
# Prepare persistent OpenSearch directory
# ============================================================

echo "Preparing OpenSearch data directory..."

sudo mkdir \
  -p "$DATA_DIRECTORY"


# The OpenSearch container normally runs with UID/GID 1000.
sudo chown \
  -R 1000:1000 \
  "$DATA_DIRECTORY"


sudo chmod \
  -R u+rwX \
  "$DATA_DIRECTORY"


# ============================================================
# Start OpenSearch
# ============================================================

echo "Starting OpenSearch..."

"${COMPOSE[@]}" up \
  -d \
  --force-recreate \
  "$OPENSEARCH_SERVICE"


# ============================================================
# Wait until the authenticated REST API is available
# ============================================================

echo "Waiting for OpenSearch..."

OPENSEARCH_READY=false


for attempt in $(seq 1 90); do
  if opensearch_curl \
    --fail \
    --silent \
    --output /dev/null \
    --connect-timeout 2 \
    --max-time 5 \
    "$OPENSEARCH_INTERNAL_URL"
  then
    OPENSEARCH_READY=true
    break
  fi

  echo "OpenSearch is not ready yet: attempt $attempt/90"

  sleep 2
done


if [[ "$OPENSEARCH_READY" != "true" ]]; then
  echo
  echo "ERROR: OpenSearch did not become available."
  echo
  echo "OpenSearch logs:"

  show_opensearch_logs

  exit 1
fi


echo "OpenSearch is available."


# ============================================================
# Install or update the DocuMind index template
# ============================================================

echo "Installing index template: $TEMPLATE_NAME"


# index-template.json remains on the host.
# Its contents are piped to curl running inside the
# OpenSearch container.
cat "$TEMPLATE_FILE" |
  "${COMPOSE[@]}" exec -T "$OPENSEARCH_SERVICE" \
    curl \
      --insecure \
      --user "${OPENSEARCH_USERNAME}:${OPENSEARCH_PASSWORD}" \
      --fail-with-body \
      --show-error \
      --request PUT \
      "${OPENSEARCH_INTERNAL_URL}/_index_template/${TEMPLATE_NAME}" \
      --header "Content-Type: application/json" \
      --data-binary @-


echo
echo "Index template installed successfully."


# ============================================================
# Create the real index if it does not already exist
# ============================================================

echo "Checking index: $INDEX_NAME"


HTTP_STATUS="$(
  opensearch_curl \
    --silent \
    --output /dev/null \
    --write-out "%{http_code}" \
    "${OPENSEARCH_INTERNAL_URL}/${INDEX_NAME}"
)"


if [[ "$HTTP_STATUS" == "404" ]]; then
  echo "Creating index: $INDEX_NAME"

  opensearch_curl \
    --fail-with-body \
    --show-error \
    --request PUT \
    "${OPENSEARCH_INTERNAL_URL}/${INDEX_NAME}?pretty"

  echo
  echo "Index created successfully."

elif [[ "$HTTP_STATUS" == "200" ]]; then
  echo "Index already exists. It will not be recreated."

else
  echo "ERROR: Unexpected HTTP status: $HTTP_STATUS" >&2
  exit 1
fi


# ============================================================
# Verification
# ============================================================

echo
echo "OpenSearch cluster health:"

opensearch_curl \
  --fail \
  --silent \
  --show-error \
  "${OPENSEARCH_INTERNAL_URL}/_cluster/health?pretty"


echo
echo
echo "Installed template:"

opensearch_curl \
  --fail \
  --silent \
  --show-error \
  "${OPENSEARCH_INTERNAL_URL}/_index_template/${TEMPLATE_NAME}?pretty"


echo
echo
echo "Indexes:"

opensearch_curl \
  --fail \
  --silent \
  --show-error \
  "${OPENSEARCH_INTERNAL_URL}/_cat/indices?v"


echo
echo
echo "Index mapping:"

opensearch_curl \
  --fail \
  --silent \
  --show-error \
  "${OPENSEARCH_INTERNAL_URL}/${INDEX_NAME}/_mapping?pretty"


echo
echo "============================================================"
echo "DocuMind OpenSearch is ready."
echo
echo "Docker-internal URL:"
echo "  https://opensearch:9200"
echo
echo "OpenSearch username:"
echo "  $OPENSEARCH_USERNAME"
echo
echo "Template:"
echo "  $TEMPLATE_NAME"
echo
echo "Index:"
echo "  $INDEX_NAME"
echo
echo "Data directory:"
echo "  $DATA_DIRECTORY"
echo
echo "Compose service:"
echo "  $OPENSEARCH_SERVICE"
echo
echo "Host port:"
echo "  Not published"
echo "============================================================"