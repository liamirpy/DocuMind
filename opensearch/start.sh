#!/usr/bin/env bash

set -Eeuo pipefail


# ============================================================
# Configuration
# ============================================================

SCRIPT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

cd "$SCRIPT_DIR"


OPENSEARCH_URL="http://localhost:9200"

CONTAINER_NAME="documind-opensearch"

TEMPLATE_NAME="documind-chunks-template"

TEMPLATE_FILE="$SCRIPT_DIR/index-template.json"

INDEX_NAME="documind-chunks-v1"

DATA_DIRECTORY="$SCRIPT_DIR/data"


# ============================================================
# Select Docker command
# ============================================================

if docker info >/dev/null 2>&1; then

  DOCKER=(docker)

else

  DOCKER=(sudo docker)

fi


# ============================================================
# Validate required files and commands
# ============================================================

if ! command -v curl >/dev/null 2>&1; then

  echo "ERROR: curl is not installed."

  exit 1

fi


if ! command -v python3 >/dev/null 2>&1; then

  echo "ERROR: python3 is not installed."

  exit 1

fi


if [[ ! -f "$TEMPLATE_FILE" ]]; then

  echo "ERROR: Template file does not exist:"

  echo "$TEMPLATE_FILE"

  exit 1

fi


echo "Validating index-template.json..."

python3 -m json.tool \
  "$TEMPLATE_FILE" \
  > /dev/null


echo "Template JSON is valid."


# ============================================================
# Configure Linux for OpenSearch
# ============================================================

echo "Configuring vm.max_map_count..."

sudo sysctl \
  -w vm.max_map_count=262144 \
  > /dev/null


# ============================================================
# Prepare persistent OpenSearch directory
# ============================================================

echo "Preparing OpenSearch data directory..."

sudo mkdir \
  -p "$DATA_DIRECTORY"


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

"${DOCKER[@]}" compose \
  up \
  -d \
  --force-recreate \
  opensearch


# ============================================================
# Wait until the REST API is available
# ============================================================

echo "Waiting for OpenSearch..."

OPENSEARCH_READY=false


for attempt in $(seq 1 90); do

  if curl \
    --fail \
    --silent \
    "$OPENSEARCH_URL" \
    > /dev/null
  then

    OPENSEARCH_READY=true

    break

  fi


  sleep 2

done


if [[ "$OPENSEARCH_READY" != "true" ]]; then

  echo

  echo "ERROR: OpenSearch did not become available."

  echo

  echo "OpenSearch logs:"

  "${DOCKER[@]}" compose \
    logs \
    --tail=200 \
    opensearch

  exit 1

fi


echo "OpenSearch is available."


# ============================================================
# Install or update the DocuMind index template
# ============================================================

echo "Installing index template: $TEMPLATE_NAME"

curl \
  --fail-with-body \
  --show-error \
  --request PUT \
  "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME" \
  --header "Content-Type: application/json" \
  --data-binary "@$TEMPLATE_FILE"


echo

echo "Index template installed successfully."


# ============================================================
# Create the real index if it does not already exist
# ============================================================

echo "Checking index: $INDEX_NAME"

HTTP_STATUS="$(
  curl \
    --silent \
    --output /dev/null \
    --write-out "%{http_code}" \
    "$OPENSEARCH_URL/$INDEX_NAME"
)"


if [[ "$HTTP_STATUS" == "404" ]]; then

  echo "Creating index: $INDEX_NAME"


  curl \
    --fail-with-body \
    --show-error \
    --request PUT \
    "$OPENSEARCH_URL/$INDEX_NAME?pretty"


  echo

  echo "Index created successfully."


elif [[ "$HTTP_STATUS" == "200" ]]; then

  echo "Index already exists. It will not be recreated."


else

  echo "ERROR: Unexpected HTTP status: $HTTP_STATUS"

  exit 1

fi


# ============================================================
# Verification
# ============================================================

echo

echo "OpenSearch cluster health:"

curl \
  --fail \
  --silent \
  "$OPENSEARCH_URL/_cluster/health?pretty"


echo

echo

echo "Installed template:"

curl \
  --fail \
  --silent \
  "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME?pretty"


echo

echo

echo "Indexes:"

curl \
  --fail \
  --silent \
  "$OPENSEARCH_URL/_cat/indices?v"


echo

echo "============================================================"

echo "DocuMind OpenSearch is ready."

echo

echo "OpenSearch URL:"

echo "  $OPENSEARCH_URL"

echo

echo "Template:"

echo "  $TEMPLATE_NAME"

echo

echo "Index:"

echo "  $INDEX_NAME"

echo

echo "Data directory:"

echo "  $DATA_DIRECTORY"

echo "============================================================"