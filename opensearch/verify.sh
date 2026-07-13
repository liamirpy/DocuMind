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


OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"

CONTAINER_NAME="${CONTAINER_NAME:-documind-opensearch}"

TEMPLATE_NAME="${TEMPLATE_NAME:-documind-chunks-template}"

INDEX_NAME="${INDEX_NAME:-documind-chunks-v1}"

EXPECTED_DATA_DIR="${EXPECTED_DATA_DIR:-$SCRIPT_DIR/data}"

CONTAINER_DATA_DIR="/usr/share/opensearch/data"


# ============================================================
# Output helpers
# ============================================================

PASS_COUNT=0

WARNING_COUNT=0

FAIL_COUNT=0


print_header() {

  echo
  echo "============================================================"
  echo "$1"
  echo "============================================================"

}


pass() {

  PASS_COUNT=$((PASS_COUNT + 1))

  printf '✅ PASS: %s\n' "$1"

}


warning() {

  WARNING_COUNT=$((WARNING_COUNT + 1))

  printf '⚠️  WARNING: %s\n' "$1"

}


fail() {

  FAIL_COUNT=$((FAIL_COUNT + 1))

  printf '❌ FAIL: %s\n' "$1"

}


# ============================================================
# Temporary files
# ============================================================

TEMP_DIRECTORY="$(mktemp -d)"

cleanup() {

  rm -rf "$TEMP_DIRECTORY"

}

trap cleanup EXIT


# ============================================================
# Select Docker command
# ============================================================

if docker info >/dev/null 2>&1; then

  DOCKER=(docker)

else

  DOCKER=(sudo docker)

fi


# ============================================================
# Check required commands
# ============================================================

print_header "Checking required commands"


if command -v curl >/dev/null 2>&1; then

  pass "curl is installed."

else

  fail "curl is not installed."

fi


if command -v python3 >/dev/null 2>&1; then

  pass "python3 is installed."

else

  fail "python3 is not installed."

fi


if "${DOCKER[@]}" info >/dev/null 2>&1; then

  pass "Docker is available."

else

  fail "Docker is not available."

fi


if (( FAIL_COUNT > 0 )); then

  echo
  echo "Required commands are missing."

  exit 1

fi


# ============================================================
# Check Docker container
# ============================================================

print_header "Checking OpenSearch container"


if ! "${DOCKER[@]}" inspect \
  "$CONTAINER_NAME" \
  >/dev/null 2>&1
then

  fail "Container does not exist: $CONTAINER_NAME"

  echo
  echo "Run:"
  echo
  echo "  ./start.sh"

  exit 1

fi


CONTAINER_RUNNING="$(
  "${DOCKER[@]}" inspect \
    --format '{{.State.Running}}' \
    "$CONTAINER_NAME"
)"


if [[ "$CONTAINER_RUNNING" == "true" ]]; then

  pass "Container is running: $CONTAINER_NAME"

else

  fail "Container is not running: $CONTAINER_NAME"

fi


CONTAINER_STATUS="$(
  "${DOCKER[@]}" inspect \
    --format '{{.State.Status}}' \
    "$CONTAINER_NAME"
)"


echo "Container status: $CONTAINER_STATUS"


# ============================================================
# Check persistent data mount
# ============================================================

print_header "Checking persistent data directory"


MOUNT_INFORMATION="$(
  "${DOCKER[@]}" inspect \
    --format \
    '{{range .Mounts}}{{if eq .Destination "/usr/share/opensearch/data"}}{{.Type}}|{{.Source}}|{{.Destination}}|{{.RW}}{{end}}{{end}}' \
    "$CONTAINER_NAME"
)"


if [[ -z "$MOUNT_INFORMATION" ]]; then

  fail \
    "Nothing is mounted at $CONTAINER_DATA_DIR inside the container."

else

  IFS='|' read -r \
    MOUNT_TYPE \
    MOUNT_SOURCE \
    MOUNT_DESTINATION \
    MOUNT_READ_WRITE \
    <<< "$MOUNT_INFORMATION"


  echo "Mount type:        $MOUNT_TYPE"

  echo "PC directory:      $MOUNT_SOURCE"

  echo "Container path:    $MOUNT_DESTINATION"

  echo "Writable:          $MOUNT_READ_WRITE"


  ACTUAL_DATA_DIRECTORY="$(
    realpath -m "$MOUNT_SOURCE"
  )"


  EXPECTED_DATA_DIRECTORY="$(
    realpath -m "$EXPECTED_DATA_DIR"
  )"


  if [[ "$ACTUAL_DATA_DIRECTORY" == \
        "$EXPECTED_DATA_DIRECTORY" ]]
  then

    pass \
      "OpenSearch data is stored in $EXPECTED_DATA_DIRECTORY"

  else

    fail \
      "OpenSearch uses $ACTUAL_DATA_DIRECTORY instead of $EXPECTED_DATA_DIRECTORY"

  fi


  if [[ "$MOUNT_READ_WRITE" == "true" ]]; then

    pass "The OpenSearch data mount is writable."

  else

    fail "The OpenSearch data mount is read-only."

  fi

fi


if [[ -d "$EXPECTED_DATA_DIR" ]]; then

  pass "Data directory exists on the PC."

else

  fail "Data directory does not exist: $EXPECTED_DATA_DIR"

fi


# ============================================================
# Check OpenSearch API
# ============================================================

print_header "Checking OpenSearch REST API"


ROOT_RESPONSE="$TEMP_DIRECTORY/root.json"


if curl \
  --fail \
  --silent \
  --show-error \
  "$OPENSEARCH_URL" \
  > "$ROOT_RESPONSE"
then

  pass "OpenSearch responds at $OPENSEARCH_URL"

else

  fail "OpenSearch does not respond at $OPENSEARCH_URL"

  echo
  echo "Recent OpenSearch logs:"
  echo

  "${DOCKER[@]}" logs \
    --tail=100 \
    "$CONTAINER_NAME"

  exit 1

fi


python3 \
  - "$ROOT_RESPONSE" \
  <<'PYTHON'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    response = json.load(file)

print(
    "Cluster name:",
    response.get("cluster_name", "unknown"),
)

print(
    "Node name:",
    response.get("name", "unknown"),
)

version = response.get("version", {})

print(
    "OpenSearch version:",
    version.get("number", "unknown"),
)
PYTHON


# ============================================================
# Check cluster health
# ============================================================

print_header "Checking cluster health"


HEALTH_RESPONSE="$TEMP_DIRECTORY/health.json"


curl \
  --fail \
  --silent \
  --show-error \
  "$OPENSEARCH_URL/_cluster/health" \
  > "$HEALTH_RESPONSE"


read -r \
  CLUSTER_STATUS \
  NUMBER_OF_NODES \
  ACTIVE_PRIMARY_SHARDS \
  UNASSIGNED_SHARDS \
  <<< "$(
    python3 \
      - "$HEALTH_RESPONSE" \
      <<'PYTHON'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    health = json.load(file)

print(
    health.get("status", "unknown"),
    health.get("number_of_nodes", 0),
    health.get("active_primary_shards", 0),
    health.get("unassigned_shards", 0),
)
PYTHON
  )"


echo "Cluster status:       $CLUSTER_STATUS"

echo "Number of nodes:      $NUMBER_OF_NODES"

echo "Active primary shards: $ACTIVE_PRIMARY_SHARDS"

echo "Unassigned shards:    $UNASSIGNED_SHARDS"


case "$CLUSTER_STATUS" in

  green)

    pass "Cluster status is green."

    ;;


  yellow)

    warning \
      "Cluster status is yellow. Primary shards are available, but one or more replica shards are unassigned."

    ;;


  red)

    fail \
      "Cluster status is red."

    ;;


  *)

    fail \
      "Unknown cluster status: $CLUSTER_STATUS"

    ;;

esac


if (( NUMBER_OF_NODES >= 1 )); then

  pass "At least one OpenSearch node is available."

else

  fail "No OpenSearch node is available."

fi


# ============================================================
# Check index template
# ============================================================

print_header "Checking DocuMind index template"


TEMPLATE_RESPONSE="$TEMP_DIRECTORY/template.json"


TEMPLATE_HTTP_STATUS="$(
  curl \
    --silent \
    --output "$TEMPLATE_RESPONSE" \
    --write-out '%{http_code}' \
    "$OPENSEARCH_URL/_index_template/$TEMPLATE_NAME"
)"


if [[ "$TEMPLATE_HTTP_STATUS" == "200" ]]; then

  pass "Index template exists: $TEMPLATE_NAME"

else

  fail \
    "Index template was not found: $TEMPLATE_NAME"

fi


if [[ "$TEMPLATE_HTTP_STATUS" == "200" ]]; then

  TEMPLATE_CHECK_RESULT="$(
    python3 \
      - "$TEMPLATE_RESPONSE" \
      "$TEMPLATE_NAME" \
      <<'PYTHON'
import json
import sys

file_path = sys.argv[1]

expected_name = sys.argv[2]

with open(file_path, encoding="utf-8") as file:
    response = json.load(file)

templates = response.get(
    "index_templates",
    [],
)

for item in templates:

    if item.get("name") != expected_name:
        continue

    definition = item.get(
        "index_template",
        {},
    )

    patterns = definition.get(
        "index_patterns",
        [],
    )

    print(",".join(patterns))

    sys.exit(0)

sys.exit(1)
PYTHON
  )"


  echo "Index patterns: $TEMPLATE_CHECK_RESULT"


  if [[ "$TEMPLATE_CHECK_RESULT" == *"documind-chunks-"* ]]; then

    pass \
      "Template contains the DocuMind chunks index pattern."

  else

    warning \
      "Template pattern is unexpected: $TEMPLATE_CHECK_RESULT"

  fi

fi


# ============================================================
# Check actual index
# ============================================================

print_header "Checking DocuMind index"


INDEX_HTTP_STATUS="$(
  curl \
    --silent \
    --output /dev/null \
    --write-out '%{http_code}' \
    "$OPENSEARCH_URL/$INDEX_NAME"
)"


if [[ "$INDEX_HTTP_STATUS" == "200" ]]; then

  pass "Index exists: $INDEX_NAME"

else

  fail "Index does not exist: $INDEX_NAME"

fi


if [[ "$INDEX_HTTP_STATUS" != "200" ]]; then

  echo
  echo "Create the index with:"
  echo
  echo "  curl --request PUT \\"
  echo "    \"$OPENSEARCH_URL/$INDEX_NAME?pretty\""

  exit 1

fi


# ============================================================
# Check index settings
# ============================================================

print_header "Checking index settings"


SETTINGS_RESPONSE="$TEMP_DIRECTORY/settings.json"


curl \
  --fail \
  --silent \
  --show-error \
  "$OPENSEARCH_URL/$INDEX_NAME/_settings" \
  > "$SETTINGS_RESPONSE"


read -r \
  KNN_ENABLED \
  NUMBER_OF_SHARDS \
  NUMBER_OF_REPLICAS \
  <<< "$(
    python3 \
      - "$SETTINGS_RESPONSE" \
      "$INDEX_NAME" \
      <<'PYTHON'
import json
import sys

file_path = sys.argv[1]

index_name = sys.argv[2]

with open(file_path, encoding="utf-8") as file:
    response = json.load(file)

settings = (
    response
    .get(index_name, {})
    .get("settings", {})
    .get("index", {})
)

print(
    settings.get("knn", "false"),
    settings.get("number_of_shards", "unknown"),
    settings.get("number_of_replicas", "unknown"),
)
PYTHON
  )"


echo "k-NN enabled:       $KNN_ENABLED"

echo "Number of shards:   $NUMBER_OF_SHARDS"

echo "Number of replicas: $NUMBER_OF_REPLICAS"


if [[ "$KNN_ENABLED" == "true" ]]; then

  pass "k-NN is enabled on the index."

else

  fail "k-NN is not enabled on the index."

fi


if [[ "$NUMBER_OF_SHARDS" == "1" ]]; then

  pass "The index has one primary shard."

else

  warning \
    "Expected one primary shard, but found: $NUMBER_OF_SHARDS"

fi


if [[ "$NUMBER_OF_REPLICAS" == "0" ]]; then

  pass "The single-node index has zero replicas."

else

  warning \
    "The index has $NUMBER_OF_REPLICAS replica(s). A one-node cluster may remain yellow."

fi


# ============================================================
# Check vector mapping
# ============================================================

print_header "Checking embedding vector mapping"


MAPPING_RESPONSE="$TEMP_DIRECTORY/mapping.json"


curl \
  --fail \
  --silent \
  --show-error \
  "$OPENSEARCH_URL/$INDEX_NAME/_mapping" \
  > "$MAPPING_RESPONSE"


read -r \
  EMBEDDING_TYPE \
  EMBEDDING_DIMENSION \
  EMBEDDING_ENGINE \
  EMBEDDING_SPACE_TYPE \
  <<< "$(
    python3 \
      - "$MAPPING_RESPONSE" \
      "$INDEX_NAME" \
      <<'PYTHON'
import json
import sys

file_path = sys.argv[1]

index_name = sys.argv[2]

with open(file_path, encoding="utf-8") as file:
    response = json.load(file)

embedding = (
    response
    .get(index_name, {})
    .get("mappings", {})
    .get("properties", {})
    .get("embedding", {})
)

method = embedding.get(
    "method",
    {},
)

print(
    embedding.get("type", "missing"),
    embedding.get("dimension", "missing"),
    method.get("engine", "missing"),
    method.get("space_type", "missing"),
)
PYTHON
  )"


echo "Embedding type:      $EMBEDDING_TYPE"

echo "Embedding dimension: $EMBEDDING_DIMENSION"

echo "Vector engine:       $EMBEDDING_ENGINE"

echo "Vector space type:   $EMBEDDING_SPACE_TYPE"


if [[ "$EMBEDDING_TYPE" == "knn_vector" ]]; then

  pass "embedding is a knn_vector field."

else

  fail \
    "Expected embedding type knn_vector, found: $EMBEDDING_TYPE"

fi


if [[ "$EMBEDDING_DIMENSION" == "1024" ]]; then

  pass "Embedding dimension is 1024."

else

  fail \
    "Expected embedding dimension 1024, found: $EMBEDDING_DIMENSION"

fi


if [[ "$EMBEDDING_ENGINE" == "lucene" ]]; then

  pass "Vector engine is Lucene."

else

  warning \
    "Expected Lucene vector engine, found: $EMBEDDING_ENGINE"

fi


if [[ "$EMBEDDING_SPACE_TYPE" == "cosinesimil" ]]; then

  pass "Vector similarity type is cosine similarity."

else

  warning \
    "Expected cosinesimil, found: $EMBEDDING_SPACE_TYPE"

fi


# ============================================================
# Test document write, refresh, read, and delete
# ============================================================

print_header "Testing document operations"


TEST_DOCUMENT_ID="verification-$(date +%s)-$$"


TEST_DOCUMENT="$TEMP_DIRECTORY/test-document.json"


cat \
  > "$TEST_DOCUMENT" \
  <<JSON
{
  "user_id": "verification-user",
  "document_id": "verification-document",
  "document_public_id": "verification-public-document",
  "chunk_id": "$TEST_DOCUMENT_ID",
  "chunk_index": 0,
  "source_type": "verification",
  "chunk_role": "content",
  "retrieval_enabled": true,
  "oversized": false,
  "document_title": "OpenSearch verification document",
  "file_type": "txt",
  "language": "en",
  "content": "This temporary document verifies OpenSearch write and read operations.",
  "retrieval_text": "Temporary OpenSearch verification document.",
  "token_count": 9,
  "content_hash": "$TEST_DOCUMENT_ID",
  "indexed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON


WRITE_RESPONSE="$TEMP_DIRECTORY/write.json"


if curl \
  --fail-with-body \
  --silent \
  --show-error \
  --request PUT \
  "$OPENSEARCH_URL/$INDEX_NAME/_doc/$TEST_DOCUMENT_ID?refresh=true" \
  --header "Content-Type: application/json" \
  --data-binary "@$TEST_DOCUMENT" \
  > "$WRITE_RESPONSE"
then

  pass "A temporary document was indexed."

else

  fail "The temporary document could not be indexed."

fi


READ_RESPONSE="$TEMP_DIRECTORY/read.json"


if curl \
  --fail \
  --silent \
  --show-error \
  "$OPENSEARCH_URL/$INDEX_NAME/_doc/$TEST_DOCUMENT_ID" \
  > "$READ_RESPONSE"
then

  pass "The temporary document was read."

else

  fail "The temporary document could not be read."

fi


if python3 \
  - "$READ_RESPONSE" \
  "$TEST_DOCUMENT_ID" \
  <<'PYTHON'
import json
import sys

file_path = sys.argv[1]

expected_id = sys.argv[2]

with open(file_path, encoding="utf-8") as file:
    response = json.load(file)

source = response.get(
    "_source",
    {},
)

if not response.get("found", False):
    sys.exit(1)

if source.get("chunk_id") != expected_id:
    sys.exit(1)

if source.get("user_id") != "verification-user":
    sys.exit(1)

sys.exit(0)
PYTHON
then

  pass "The document content matches the written data."

else

  fail "The read document content is incorrect."

fi


if curl \
  --fail-with-body \
  --silent \
  --show-error \
  --request DELETE \
  "$OPENSEARCH_URL/$INDEX_NAME/_doc/$TEST_DOCUMENT_ID?refresh=true" \
  > /dev/null
then

  pass "The temporary verification document was deleted."

else

  warning \
    "The temporary verification document could not be deleted."

fi


# ============================================================
# Show index information
# ============================================================

print_header "Current index information"


curl \
  --fail \
  --silent \
  --show-error \
  "$OPENSEARCH_URL/_cat/indices/$INDEX_NAME?v"


# ============================================================
# Final result
# ============================================================

print_header "Verification result"


echo "Passed:   $PASS_COUNT"

echo "Warnings: $WARNING_COUNT"

echo "Failed:   $FAIL_COUNT"

echo


if (( FAIL_COUNT == 0 )); then

  echo "✅ DocuMind OpenSearch verification succeeded."

  echo

  echo "OpenSearch URL:"

  echo "  $OPENSEARCH_URL"

  echo

  echo "Index template:"

  echo "  $TEMPLATE_NAME"

  echo

  echo "Index:"

  echo "  $INDEX_NAME"

  echo

  echo "Persistent data directory:"

  echo "  $EXPECTED_DATA_DIR"

  exit 0

fi


echo "❌ DocuMind OpenSearch verification failed."

echo

echo "Check the failed items above."

exit 1