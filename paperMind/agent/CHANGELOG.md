# Changelog

## Unreleased

- Added `POST /v1/process-path` with `input_directory`, `input_filename`, and
  `output_directory` parameters for processing PDFs from mounted storage.
- Added `HOST_ACCESS_ROOT`, `ALLOWED_INPUT_DIRECTORIES`, and `PATH_API_ENABLED`.
- Stopped changing ownership of arbitrary allow-listed paths at container startup.
- Added per-run `output_directory` support to the HTTP API and local CLI.
- Added API output-root allow-list validation to prevent arbitrary filesystem writes.
- Added an optional Docker mount at `/data/custom-output` for selecting an alternate host root.
- Added `output_directory` to process responses and disabled static/download URLs
  whenever a request selects a non-default root.

## 0.3.0 - 2026-07-10

- Added a safe per-request `output_folder` field.
- Added optional per-request `overwrite` behavior with HTTP 409 collision protection.
- Added named-package static and ZIP download URLs.
- Added output-folder metadata to API responses and canonical JSON.
- Bumped the canonical JSON schema to `1.2.0`.
- Added Linux UID/GID mapping for host bind-mounted output directories.
- Added a root one-command Compose deployment with GROBID, Docling, Agent, Ollama, and automatic model pull.
- Added CPU and NVIDIA deployment modes.
- Added Linux/macOS and Windows installation scripts.
- Fixed GROBID health checks to use `/api/isalive` with endpoint-specific content negotiation.

## 0.2.0

- Preserve nested GROBID TEI sections and subsections.
- Add canonical section IDs, levels, parent IDs, full paths, child IDs, page ranges, and linked paragraph/asset IDs.
- Add canonical paragraph records and section links on Docling text blocks.
- Link figures, tables, and formulas to sections using exact GROBID TEI IDs when available, with page-range fallback and assignment confidence.
- Add optional Llama descriptions for every available figure, table, and formula image.
- Write `.description.txt` and `.description.json` files beside each described asset.
- Extend table repair and formula transcription responses with grounded descriptions.
- Add hierarchy, association, and all-element Llama description tests.
- Bump canonical schema to `1.1.0` and Agent version to `0.2.0`.
