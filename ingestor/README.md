# DocuMind Chunk Ingestor Upload API

A persistent HTTP API that receives a `chunks.json` file or a ZIP containing a complete chunk directory and ingests it into OpenSearch.

**Version 2 no longer requires an input-folder Docker mount.** Start the container once, then upload each document with an HTTP request.

```text
local directory or chunks.json
          |
          | multipart upload
          v
DocuMind ingestor API ---- bulk upsert ----> OpenSearch
          |
          +---- temporary files are deleted after the request
```

## Why a full host path cannot be sent as JSON

A path such as `/home/me/data/doc_457` exists on the client/host machine, not inside the isolated Docker container. Sending that text does not transfer the files and does not grant the container access to the directory.

The replacement API therefore uploads either:

- the `chunks.json` file directly; or
- a ZIP containing the whole directory.

The included `upload-directory.sh` helper accepts a full local directory path, creates a temporary ZIP, uploads it, and removes the ZIP automatically.

## Start the API

Create the shared Docker network once if it does not already exist:

```bash
docker network create documind
```

Copy and edit the environment file:

```bash
cp .env.example .env
```

At minimum, configure OpenSearch:

```dotenv
OPENSEARCH_URL=http://opensearch:9200
OPENSEARCH_INDEX=documind-chunks-v1
```

Start the API:

```bash
docker compose up -d --build
```

No input volume is configured in `compose.yml`.

- Health check: `http://localhost:8080/health`
- Interactive API documentation: `http://localhost:8080/docs`

## Upload a complete directory

Assume the local directory is:

```text
/home/me/chunk-data/doc_457/
├── chunks.json
└── canonical_document.json
```

Use the helper with the full directory path:

```bash
./upload-directory.sh /home/me/chunk-data/doc_457
```

For validation without OpenSearch:

```bash
./upload-directory.sh \
  /home/me/chunk-data/doc_457 \
  http://localhost:8080/ingest \
  '{"dry_run":true,"expected_embedding_dimensions":1024}'
```

The full directory path is used by the **client helper** to read and upload the data. It is not passed to Docker as a server-side filesystem path.

## Upload a ZIP manually

Create a ZIP:

```bash
cd /home/me/chunk-data
zip -r doc_457.zip doc_457
```

Upload it. When the ZIP contains only one `chunks.json`, the API finds it automatically:

```bash
curl -X POST http://localhost:8080/ingest \
  -F 'payload=@doc_457.zip;type=application/zip' \
  -F 'parameters={"dry_run":false}'
```

When the ZIP contains multiple documents, choose one with `chunks_path`:

```bash
curl -X POST http://localhost:8080/ingest \
  -F 'payload=@many-documents.zip;type=application/zip' \
  -F 'parameters={"chunks_path":"doc_457","dry_run":true}'
```

Both of these are accepted:

```json
{"chunks_path":"doc_457"}
```

```json
{"chunks_path":"doc_457/chunks.json"}
```

## Upload only `chunks.json`

```bash
curl -X POST http://localhost:8080/ingest \
  -F 'payload=@/home/me/chunk-data/doc_457/chunks.json;type=application/json' \
  -F 'parameters={"dry_run":true,"expected_embedding_dimensions":1024}'
```

To send a separate canonical file:

```bash
curl -X POST http://localhost:8080/ingest \
  -F 'payload=@/home/me/chunk-data/doc_457/chunks.json;type=application/json' \
  -F 'canonical_file=@/home/me/chunk-data/doc_457/canonical_document.json;type=application/json' \
  -F 'parameters={"dry_run":true}'
```

## Request parameters

The multipart field `parameters` is a JSON object. Available fields include:

| Field | Purpose |
|---|---|
| `chunks_path` | File or directory inside a ZIP. Defaults to `chunks.json` with automatic discovery. |
| `canonical_path` | Optional canonical JSON path inside a ZIP. |
| `index` | Override the target OpenSearch index. |
| `expected_embedding_dimensions` | Override the expected vector dimensions. |
| `allow_missing_embeddings` | Permit retrieval chunks without embeddings. |
| `replace_document` | Remove stale chunks after successful indexing. |
| `refresh` | Refresh the index after ingestion. |
| `install_template` | Install/update the configured index template. |
| `dry_run` | Validate and transform without contacting OpenSearch. |
| metadata fields | Override public ID, title, authors, original filename, file type, or language. |

Example:

```json
{
  "chunks_path": "doc_457",
  "index": "documind-chunks-v1",
  "expected_embedding_dimensions": 1024,
  "replace_document": true,
  "dry_run": false,
  "document_title": "Example document",
  "document_authors": ["A. Author"]
}
```

Infrastructure credentials and timeouts remain environment variables rather than request parameters.

## Optional API key

Set this in `.env`:

```dotenv
INGESTOR_API_KEY=replace-with-a-long-random-value
```

Then include the header:

```bash
curl -X POST http://localhost:8080/ingest \
  -H 'X-API-Key: replace-with-a-long-random-value' \
  -F 'payload=@doc_457.zip;type=application/zip' \
  -F 'parameters={"dry_run":true}'
```

The helper reads the same value from the client environment:

```bash
export INGESTOR_API_KEY=replace-with-a-long-random-value
./upload-directory.sh /home/me/chunk-data/doc_457
```

## Upload limits and ZIP safety

The API rejects path traversal, symbolic links, encrypted ZIP members, oversized uploads, and oversized extracted archives. Defaults:

```dotenv
INGESTOR_MAX_UPLOAD_BYTES=536870912
INGESTOR_MAX_ARCHIVE_FILES=10000
INGESTOR_MAX_EXTRACTED_BYTES=2147483648
```

Uploaded data is stored in a request-specific temporary directory and deleted after success or failure.

## Run without Docker

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install .

export OPENSEARCH_URL=http://localhost:9200
export OPENSEARCH_INDEX=documind-chunks-v1
export OPENSEARCH_TEMPLATE_FILE="$PWD/templates/documind-chunks-template.json"

uvicorn documind_ingestor.api:app --host 0.0.0.0 --port 8080
```

## CLI compatibility

The original local CLI remains available:

```bash
documind-ingestor /full/path/to/chunks.json \
  --expected-embedding-dimensions 32 \
  --dry-run
```

## Development checks

```bash
python -m pip install -r requirements-dev.txt
pytest
ruff check .
ruff format --check .
```



### test 


curl -X POST http://localhost:8080/ingest \
  -F 'payload=@/srv/DocuMind/data/users/ad95c672-0056-4302-b815-db84a09929bd/stroke/indexer_example/chunks.json;type=application/json' \
  -F 'parameters={"dry_run":false,"expected_embedding_dimensions":1024}'



  