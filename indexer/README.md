# DocuMind Indexer API 4.1.0

A standalone FastAPI service that consumes an **already generated DocuMind PDF output
directory** and produces `chunks.json` containing:

- parent and child paragraph chunks;
- one standalone chunk for every table, figure, and formula;
- separate reference records;
- model-tokenizer token counts;
- dense embeddings for retrievable chunks.

The PDF extraction package is not included, imported, executed, or modified.

## Start with one command

The included `.env` is configured for:

```text
input root:  /srv/DocuMind
output root: /srv/DocuMind/indexer-output
API:         http://localhost:8000
```

Start:

```bash
docker compose up --build -d
```

No manual creation or `chown` of `.jobs`, the output directory, or the model cache is required.
A one-shot initialization container prepares writable storage before the API starts. The model
cache is a Docker named volume, avoiding host UID/GID permission problems.

Check:

```bash
docker compose ps -a
curl http://localhost:8000/health/ready
```

Expected:

```text
init-permissions   Exited (0)
indexer-api        Up (healthy)
```

API documentation:

```text
http://localhost:8000/docs
```

## Submit an indexing job

```bash
curl -X POST http://localhost:8000/v1/indexing/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "user_123",
    "document_id": "doc_456",
    "input_directory": "/srv/DocuMind/VRU_without_LLM",
    "output_directory": "/srv/DocuMind/indexer-output/doc_456"
  }'
```

The API returns `202 Accepted` and a `job_id`. Poll:

```bash
curl http://localhost:8000/v1/indexing/jobs/<job_id>
```
curl \
  "http://localhost:8000/v1/indexing/jobs?limit=50"

  
When the job succeeds, the result is written to:

```text
/srv/DocuMind/indexer-output/doc_456/chunks.json
```

## Configuration

All service and pipeline configuration is in `.env`, including:

- host input/output roots;
- API port, API key, CORS, concurrency, and job history;
- parent and child token targets, maxima, and overlaps;
- table/figure/formula behavior;
- reference behavior;
- embedding provider, model, device, batch size, dimensions, normalization, and limits.

The only values commonly changed before first startup are:

```dotenv
DOCUMIND_INPUT_ROOT_HOST=/srv/DocuMind
DOCUMIND_OUTPUT_ROOT_HOST=/srv/DocuMind/indexer-output
APP_UID=1000
APP_GID=1000
```

On Linux, compare the last two values with:

```bash
id -u
id -g
```

## Default embedding stack

```text
provider: Sentence Transformers
model: BAAI/bge-m3
dimensions: 1024
normalization: enabled
selection: retrieval-enabled chunks only
```

The first production job downloads the model into the Docker named volume configured by:

```dotenv
HF_CACHE_VOLUME_NAME=documind-huggingface-cache
```

The cache survives `docker compose down`. Avoid `docker compose down -v` unless you intentionally
want to remove the downloaded model.

For a fast non-semantic smoke test, set:

```dotenv
EMBEDDING_PROVIDER=development_hash
EMBEDDING_MODEL_NAME=development-hash-v1
EMBEDDING_EXPECTED_DIMENSIONS=32
EMBEDDING_DEVELOPMENT_HASH_DIMENSIONS=32
```

Never use the development provider for production retrieval.

## Query embeddings

```bash
curl -X POST http://localhost:8000/v1/embeddings/query \
  -H 'Content-Type: application/json' \
  -d '{
    "query_text": "How does the VR training workflow work?"
  }'
```

Use the returned vector with the same OpenSearch vector field used for chunk embeddings.

## Operational documentation

- [DOCKER.md](DOCKER.md): startup, volumes, permissions, cache, and operations.
- [API.md](API.md): endpoints and request/response shapes.
- [INPUT_CONTRACT.md](INPUT_CONTRACT.md): required PDF-output directory structure.
- [EMBEDDING_DESIGN.md](EMBEDDING_DESIGN.md): embedding behavior.
- [VALIDATION.md](VALIDATION.md): validation notes.





### 
curl -X POST http://localhost:8000/v1/indexing/jobs \
  -H 'Content-Type: application/json' \
   -H "X-API-Key:hello" \
  -d '{
    "user_id": "user_123",
    "document_id": "doc_456",
    "input_directory": "/srv/DocuMind/data/users/ad95c672-0056-4302-b815-db84a09929bd/stroke/pdfMind_example",
    "output_directory": "/srv/DocuMind/data/users/ad95c672-0056-4302-b815-db84a09929bd/chunk_example"
  }'


  

curl \
     -H "X-API-Key:hello" \
  "http://localhost:8000/v1/indexing/jobs?limit=50"
