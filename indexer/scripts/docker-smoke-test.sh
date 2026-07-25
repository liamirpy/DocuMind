#!/usr/bin/env sh
set -eu

IMAGE="${DOCUMIND_INDEXER_IMAGE:-documind-indexer:3.0.0}"
OUTPUT_DIR="${1:-$(pwd)/docker-output}"

mkdir -p "${OUTPUT_DIR}"

docker build -t "${IMAGE}" .

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$(pwd)/examples/sample_pdf_output:/data/input:ro" \
  -v "${OUTPUT_DIR}:/data/output" \
  -v "$(pwd)/docker/chunking_config.smoke.json:/config/chunking_config.json:ro" \
  "${IMAGE}" \
  chunk /data/input \
  --user-id user_123 \
  --document-id doc_456 \
  --config /config/chunking_config.json \
  --output /data/output/chunks.smoke.json

printf '\nSmoke output: %s\n' "${OUTPUT_DIR}/chunks.smoke.json"
