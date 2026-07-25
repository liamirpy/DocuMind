#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 3 ]]; then
  echo "Usage: $0 FULL_DIRECTORY [API_URL] [PARAMETERS_JSON]" >&2
  echo "Example: $0 /data/doc_457 http://localhost:8080/ingest '{\"dry_run\":true}'" >&2
  exit 2
fi

DIRECTORY="$(cd "$1" && pwd)"
API_URL="${2:-http://localhost:8080/ingest}"
PARAMETERS_JSON='{}'
if [[ $# -ge 3 ]]; then
  PARAMETERS_JSON="$3"
fi
ARCHIVE="$(mktemp --suffix=.zip)"
trap 'rm -f "$ARCHIVE"' EXIT

python - "$DIRECTORY" "$ARCHIVE" <<'PY'
from pathlib import Path
import shutil
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
base = target.with_suffix("")
created = Path(shutil.make_archive(str(base), "zip", root_dir=source.parent, base_dir=source.name))
if created != target:
    created.replace(target)
PY

CURL_ARGS=(
  --fail-with-body
  --silent
  --show-error
  -X POST "$API_URL"
  -F "payload=@${ARCHIVE};filename=$(basename "$DIRECTORY").zip;type=application/zip"
  -F "parameters=${PARAMETERS_JSON}"
)

if [[ -n "${INGESTOR_API_KEY:-}" ]]; then
  CURL_ARGS+=( -H "X-API-Key: ${INGESTOR_API_KEY}" )
fi

curl "${CURL_ARGS[@]}"
echo
