#!/usr/bin/env bash
set -euo pipefail

PDF_PATH="${1:-../tools/tests/fixtures/scientific_sample.pdf}"
AGENT_URL="${AGENT_URL:-http://localhost:8100}"
RESULT_FILE="${RESULT_FILE:-/tmp/pdf-agent-smoke-result.json}"

curl --fail --show-error \
  -X POST "${AGENT_URL}/v1/process" \
  -F "file=@${PDF_PATH};type=application/pdf" \
  -F "use_llm=false" \
  -o "${RESULT_FILE}"

jq . "${RESULT_FILE}"
DOCUMENT_ID=$(jq -r .document_id "${RESULT_FILE}")
CANONICAL="data/outputs/${DOCUMENT_ID}/canonical_document.json"

test -f "${CANONICAL}"
jq -e '.schema_version == "1.2.0"' "${CANONICAL}" >/dev/null
jq -e '.quality.status | IN("green", "yellow", "red")' "${CANONICAL}" >/dev/null

echo "Smoke test passed: ${CANONICAL}"
