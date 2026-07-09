#!/usr/bin/env bash
set -euo pipefail

PDF_PATH="${1:-tests/fixtures/scientific_sample.pdf}"
API_URL="${API_URL:-http://localhost:${API_PORT:-8090}}"
OUTPUT_DIR="${OUTPUT_DIR:-output}"

if [[ ! -f "$PDF_PATH" ]]; then
  echo "PDF not found: $PDF_PATH" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
python scripts/wait_for_url.py "$API_URL/health/ready" --timeout "${READY_TIMEOUT_SECONDS:-900}"

RESULT="$OUTPUT_DIR/smoke-result.json"
curl --fail --show-error --silent \
  --max-time "${EXTRACTION_TIMEOUT_SECONDS:-1800}" \
  -X POST "$API_URL/v1/extract" \
  -H "accept: application/json" \
  -F "file=@${PDF_PATH};type=application/pdf" \
  -F "include_docling_markdown=true" \
  -F "include_docling_json=true" \
  -F "include_grobid_tei=true" \
  -F "export_picture_images=true" \
  -F "export_table_images=true" \
  -F "grobid_consolidate_header=0" \
  -F "grobid_consolidate_citations=0" \
  -o "$RESULT"

python -m json.tool "$RESULT" > "$OUTPUT_DIR/smoke-result.pretty.json"

python - "$RESULT" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
print(json.dumps({
    "status": result["status"],
    "docling": result["docling"]["status"],
    "grobid": result["grobid"]["status"],
    "docling_stats": result["docling"].get("stats", {}),
    "grobid_stats": result["grobid"].get("stats", {}),
    "warnings": result.get("warnings", []),
}, indent=2))

if result["status"] == "failed":
    raise SystemExit(1)
PY

echo "Full result: $RESULT"
echo "Pretty result: $OUTPUT_DIR/smoke-result.pretty.json"
