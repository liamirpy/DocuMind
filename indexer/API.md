# DocuMind Indexer HTTP API

The API wraps the standalone chunking and embedding pipeline. The PDF extraction package is not
part of this container and must already have produced a directory containing
`canonical_document.json` and optional `figures/`, `tables/`, and `formulas/` sidecars.

## Start

```bash
docker compose up --build -d
```

The one-shot `init-permissions` service prepares the output and model-cache volumes before the
API starts. No manual `mkdir` or `chown` is required.

Readiness:

```bash
curl http://localhost:8000/health/ready
```

Interactive documentation:

```text
http://localhost:8000/docs
```

## Path model

Docker Compose mounts:

```text
DOCUMIND_INPUT_ROOT_HOST  -> /data/input  (read only)
DOCUMIND_OUTPUT_ROOT_HOST -> /data/output (read/write)
```

The API accepts:

- relative paths beneath those roots;
- absolute host paths beneath the configured host roots;
- absolute container paths beneath `/data/input` and `/data/output`.

Paths outside the mounted roots and path traversal are rejected.

## Create an indexing job

```bash
curl -X POST http://localhost:8000/v1/indexing/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "user_123",
    "document_id": "doc_456",
    "input_directory": "/srv/DocuMind/VRU_without_LLM",
    "output_directory": "/srv/DocuMind/indexer-output/doc_456",
    "output_filename": "chunks.json",
    "skip_embedding": false,
    "overwrite": false
  }'
```

`user_name` is accepted as an alias for `user_id`, but production systems should send the
PostgreSQL user UUID in `user_id`.

The response is `202 Accepted` and includes a `job_id`.

## Get job status

```bash
curl http://localhost:8000/v1/indexing/jobs/<job_id>
```

Stages:

```text
queued
validating_input
loading_model
chunking
embedding
writing_output
completed
failed
```

The full chunks and vectors are written to `chunks.json`; they are not returned in the status
response.

## List jobs

```bash
curl 'http://localhost:8000/v1/indexing/jobs?limit=50'
```

Job states are persisted under:

```text
DOCUMIND_OUTPUT_ROOT_HOST/.jobs/
```

The application recreates this directory before every state write. If the API restarts while a
job is running, that job is marked failed with `InterruptedJob` and can be resubmitted.

## Query embedding

```bash
curl -X POST http://localhost:8000/v1/embeddings/query \
  -H 'Content-Type: application/json' \
  -d '{
    "query_text": "How does the VR training workflow work?"
  }'
```

The response contains the dense query vector, model metadata, tokenizer name, and dimension.

## Optional API key

Set:

```dotenv
API_KEY=replace-with-a-long-random-secret
```

Then send:

```bash
-H 'X-API-Key: replace-with-a-long-random-secret'
```

Health endpoints remain unauthenticated for Docker health checks.

## Storage readiness

At application startup, the API verifies:

- the input root exists and can be read;
- the output root can be written;
- the `.jobs` directory can be written;
- the embedding cache can be written when Sentence Transformers is enabled.

A storage problem therefore prevents startup and appears immediately in container logs rather
than failing after a job has already been accepted.
