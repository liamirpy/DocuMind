# DocuMind Docker Ingestor

A standalone, one-shot Docker job that reads the `chunks.json` produced by the DocuMind indexer and transfers it to OpenSearch.

It does **not** extract PDFs, create chunks, generate embeddings, or run OpenSearch.

```text
indexer output directory
        |
        | read-only Docker mount
        v
DocuMind ingestor container
        |
        | bulk upsert
        v
OpenSearch
```

## Runtime contract

The container receives all configuration at runtime:

- `INDEXER_OUTPUT_HOST_DIR`: host directory mounted at `/input`.
- `INPUT_DIR`: directory inside the container that contains `chunks.json`.
- `INPUT_FILENAME`: defaults to `chunks.json`.
- `INPUT_FILE`: optional exact file path; takes precedence over `INPUT_DIR`.
- `OPENSEARCH_URL`: OpenSearch root URL.
- `OPENSEARCH_INDEX`: target chunk index.
- Optional OpenSearch username, password, TLS, timeout, and batch settings.

On success, the final line is machine-readable:

```text
INGESTION_DONE {"status":"done", ...}
```

The process exits with code `0`.

On failure, it prints:

```text
INGESTION_FAILED {"status":"failed","error":"..."}
```

and exits with a nonzero code.

## 1. Create a shared Docker network

Do this once:

```bash
docker network create documind
```

## 2. Connect your existing OpenSearch service to the network

Add only the `networks` sections shown below to your existing OpenSearch Compose file:

```yaml
services:
  opensearch:
    image: opensearchproject/opensearch:3.7.0

    # Keep all of your existing environment, ports, volumes, ulimits, and restart settings.

    networks:
      - documind

networks:
  documind:
    external: true
```

Then recreate the OpenSearch container so the network attachment is applied:

```bash
cd /path/to/opensearch
docker compose up -d
```

No change is required to your existing data volume, port mappings, k-NN settings, shard settings, or JVM settings.

For your current local-development configuration with `DISABLE_SECURITY_PLUGIN=true`, leave the ingestor username and password empty. Do not expose an unsecured OpenSearch node to untrusted networks.

## 3. Configure the ingestor

Copy the environment example:

```bash
cd /path/to/documind-ingestor-docker-job
cp .env.example .env
```

Edit at least these values:

```dotenv
INDEXER_OUTPUT_HOST_DIR=/srv/documind_database/indexer-output

INPUT_DIR=/input/document-123
INPUT_FILENAME=chunks.json
INPUT_FILE=

OPENSEARCH_URL=http://opensearch:9200
OPENSEARCH_INDEX=documind-chunks-v1
```

Example host layout:

```text
/srv/documind_database/indexer-output/
└── document-123/
    ├── chunks.json
    └── canonical_document.json     # optional
```

The host directory is mounted as:

```text
/input/
└── document-123/
    ├── chunks.json
    └── canonical_document.json
```

Therefore `INPUT_DIR=/input/document-123` resolves automatically to `/input/document-123/chunks.json`.

## 4. Build the image

```bash
docker compose build
```

The image name is:

```text
documind-ingestor:1.2.0
```

## 5. Run a dry validation

```bash
docker compose run --rm \
  -e INGESTOR_DRY_RUN=true \
  ingestor
```

A successful dry run ends with something like:

```text
INGESTION_VALIDATED {"chunks":120,"document_id":"document-123","dry_run":true,"status":"validated",...}
```

No OpenSearch request is made in dry-run mode.

## 6. Run the real transfer

```bash
docker compose run --rm ingestor
```

The ingestor will:

1. Resolve `INPUT_DIR` to `chunks.json`.
2. Validate the indexer JSON.
3. Transform fields to the strict OpenSearch mapping.
4. Validate embedding dimensions.
5. Wait for OpenSearch if it is still starting.
6. Install/update the bundled index template when `OPENSEARCH_INSTALL_TEMPLATE=true`.
7. Create the target index if needed.
8. Bulk-upsert chunks using `_id = chunk_id`.
9. Delete stale chunks only after the new batch succeeds.
10. Refresh the index and print `INGESTION_DONE`.

Example final line:

```text
INGESTION_DONE {"deleted_stale":0,"document_id":"document-123","index":"documind-chunks-v1","indexed":120,"status":"done",...}
```

Check the exit code:

```bash
echo $?
```

`0` means the transfer completed successfully.

## Process another document

Override only the input directory for that run:

```bash
docker compose run --rm \
  -e INPUT_DIR=/input/document-456 \
  ingestor
```

Or provide the exact file:

```bash
docker compose run --rm \
  -e INPUT_FILE=/input/document-456/chunks.json \
  ingestor
```

`INPUT_FILE` takes precedence over `INPUT_DIR`.

## Index template behavior

The Docker configuration defaults to:

```dotenv
OPENSEARCH_INSTALL_TEMPLATE=true
OPENSEARCH_TEMPLATE_NAME=documind-chunks-template
OPENSEARCH_TEMPLATE_FILE=/app/templates/documind-chunks-template.json
```

The bundled template is your strict `documind-chunks-*` mapping with a 1024-dimensional `knn_vector`.

Important: an index template applies when an index is created. Updating a template does not rewrite the mapping of an already-existing index. If `documind-chunks-v1` already exists with an incompatible mapping, either use a new index name or delete/recreate the old index only when it is safe to lose its data.

## Useful verification commands

From the host:

```bash
curl http://localhost:9200
```

Check the template:

```bash
curl 'http://localhost:9200/_index_template/documind-chunks-template?pretty'
```

Check the indexed count:

```bash
curl 'http://localhost:9200/documind-chunks-v1/_count?pretty'
```

Check the mapping:

```bash
curl 'http://localhost:9200/documind-chunks-v1/_mapping?pretty'
```

## Configuration reference

```dotenv
# Host mount
INDEXER_OUTPUT_HOST_DIR=/srv/documind_database/indexer-output

# Input
INPUT_DIR=/input/document-123
INPUT_FILENAME=chunks.json
INPUT_FILE=

# Connection
OPENSEARCH_URL=http://opensearch:9200
OPENSEARCH_INDEX=documind-chunks-v1
OPENSEARCH_USERNAME=
OPENSEARCH_PASSWORD=
OPENSEARCH_VERIFY_CERTS=false
OPENSEARCH_CA_CERTS=

# Startup and request timing
OPENSEARCH_WAIT_TIMEOUT_SECONDS=120
OPENSEARCH_WAIT_INTERVAL_SECONDS=2
OPENSEARCH_REQUEST_TIMEOUT_SECONDS=120

# Template
OPENSEARCH_INSTALL_TEMPLATE=true
OPENSEARCH_TEMPLATE_NAME=documind-chunks-template
OPENSEARCH_TEMPLATE_FILE=/app/templates/documind-chunks-template.json

# Data rules
OPENSEARCH_EMBEDDING_DIMENSIONS=1024
OPENSEARCH_BULK_BATCH_SIZE=250
INGESTOR_ALLOW_MISSING_EMBEDDINGS=false
INGESTOR_REPLACE_DOCUMENT=true
INGESTOR_REFRESH=true
INGESTOR_DRY_RUN=false
```

## Development checks

```bash
python -m pip install -r requirements-dev.txt -r requirements.txt
pytest
ruff check .
ruff format --check .
```





#####


docker network create documind


docker compose run --rm \
  -e INPUT_DIR=/input/document-456 \
  ingestor


  
