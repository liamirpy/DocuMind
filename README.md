# DocuMind

DocuMind is a self-hosted document intelligence and question-answering platform built around a retrieval-augmented generation (RAG) pipeline. Users can upload PDFs, organize documents into folders, convert them into structured canonical packages, create hierarchical chunks and embeddings, index those chunks in OpenSearch, and ask grounded questions with page-level citations.

The repository is a multi-service application composed of a Next.js frontend, an Express API, BullMQ background workers, PaperMind PDF-processing services, an indexer, an ingester, PostgreSQL, Redis, OpenSearch, Ollama, and Nginx.

> **Demo video:** [Watch DocuMind in action](https://youtu.be/XaCr_LLDI0k)

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Backend-managed PaperMind jobs](#backend-managed-papermind-jobs)
- [Document-processing pipeline](#document-processing-pipeline)
- [Repository layout](#repository-layout)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Scaling](#scaling)
- [Operations and verification](#operations-and-verification)
- [API overview](#api-overview)
- [Local development](#local-development)
- [Testing](#testing)
- [Continuous integration](#continuous-integration)
- [Troubleshooting](#troubleshooting)
- [Security](#security)
- [Data persistence and backups](#data-persistence-and-backups)
- [Contributing](#contributing)

## Features

- User registration, login, refresh-token sessions, and authenticated APIs.
- PDF upload, download, deletion, status tracking, and folder organization.
- Scientific PDF extraction using Docling and GROBID.
- Canonical document generation with text, figures, tables, formulas, references, provenance, and quality information.
- Optional visual enrichment through Ollama vision-language models.
- Configurable parent, child, and special-element chunking.
- Dense document and query embeddings.
- OpenSearch vector, keyword, and hybrid retrieval.
- RAG answers generated through Ollama.
- Saved conversations and source metadata.
- Clickable PDF citations with page navigation and bounding-box highlighting.
- Redis/BullMQ document-processing queue.
- Backend-managed PaperMind job state that supports multiple load-balanced agent replicas.
- Docker Compose deployment with internal Nginx gateways.
- GitHub Actions validation for frontend, backend, Python services, PostgreSQL, OpenSearch, Compose files, and Docker images.

## Architecture

```text
Browser
  |
  v
Public Nginx :80
  |
  v
Next.js frontend :3000
  |
  | /api proxy
  v
Express API :3000 ----------------------------------------------+
  |                                                            |
  | PostgreSQL / PgBouncer                                     | Redis
  |                                                            | - BullMQ queue
  |                                                            | - PaperMind job state
  |                                                            |
  |                                                            v
  |                                                   Document workers
  |                                                            |
  |                        +-----------------------------------+-------------------+
  |                        |                                                       |
  |                        v                                                       v
  |               Agent load balancer                                     Indexer gateway
  |                        |                                                       |
  |             +----------+----------+                                            |
  |             |          |          |                                            |
  |             v          v          v                                            v
  |         agent-api  agent-api  agent-api                                indexer-api
  |             |          |          |                                            |
  |             +----------+----------+                                            |
  |                        |                                                       |
  |              PaperMind extractor + Ollama                                     |
  |                        |                                                       |
  |                        +--------------- canonical package ---------------------+
  |                                                                                |
  |                                                                                v
  |                                                                        ingester gateway
  |                                                                                |
  |                                                                                v
  +-------------------------- RAG search <----------------------------------- OpenSearch
```

### Main service responsibilities

| Service | Responsibility |
| --- | --- |
| `frontend` | Next.js web application, PDF viewer, folders, conversations, and citations. |
| `api` | Authentication, document metadata, folders, RAG orchestration, callback endpoint, and PostgreSQL access. |
| `document-worker` | BullMQ consumer that runs PaperMind, indexing, and ingestion as one document pipeline. |
| `redis` | BullMQ queue data and shared PaperMind lifecycle records. |
| `agent-load-balancer` | Routes PaperMind submission requests to healthy `agent-api` replicas. |
| `agent-api` | Accepts PDF-processing work and reports lifecycle callbacks to the backend. |
| `extractor-api` | Runs Docling and coordinates GROBID extraction. |
| `grobid` | Scientific text, reference, and structure extraction. |
| `ollama` | Visual enrichment and final RAG answer generation. |
| `indexer-api` | Validates canonical packages, creates hierarchical chunks, and generates embeddings. |
| `ingester-api` | Validates `chunks.json` and writes document chunks to OpenSearch. |
| `opensearch` | Stores searchable chunks and vectors. |
| `postgres` / `pgbouncer` | Stores users, documents, folders, conversations, and application metadata. |
| `public-nginx` | Public HTTP entry point for the application. |

## Backend-managed PaperMind jobs

DocuMind uses asynchronous PaperMind processing, but the canonical job status is stored in **backend Redis**, not in one PaperMind replica's private memory.

### Why this is required

A load balancer may route two related HTTP requests to different replicas:

```text
POST /v1/process-path-async  -> agent-api-1
GET  /v1/jobs/<job-id>       -> agent-api-2
```

If every replica stores jobs only in an in-memory Python dictionary, `agent-api-2` does not know the job created by `agent-api-1` and returns `404 Job not found`.

The final design removes that dependency:

```text
1. document-worker creates papermind:job:<backendJobId> in Redis
2. document-worker submits backend_job_id through agent-load-balancer
3. any agent-api replica accepts and processes the job
4. that replica sends authenticated lifecycle callbacks to the backend API
5. the backend API updates the shared Redis record
6. document-worker polls Redis instead of PaperMind /v1/jobs/<job-id>
```

Because all backend workers and API replicas read the same Redis state, `agent-api` can safely be scaled without sticky sessions.

### Redis job lifecycle

A job uses a key similar to:

```text
papermind:job:papermind-document-<document-id>
```

The stored lifecycle is:

```text
queued -> running -> completed
                  \-> failed
```

Typical fields include:

```json
{
  "backend_job_id": "papermind-document-123",
  "bull_job_id": "document-123",
  "document_id": "123",
  "user_id": "user-123",
  "agent_job_id": "2aa71f5c-...",
  "status": "running",
  "stage": "processing",
  "progress": 5,
  "result": null,
  "error": null,
  "created_at": "2026-07-31T12:00:00Z",
  "updated_at": "2026-07-31T12:00:05Z"
}
```

### Callback endpoint

PaperMind reports lifecycle changes to:

```text
POST /internal/papermind/jobs/:backendJobId/status
```

The request must include:

```text
X-PaperMind-Callback-Token: <shared-secret>
```

The callback endpoint is intended only for trusted services on the private Docker network.

### Current durability boundary

Shared Redis fixes replica routing and job-status visibility. The actual PaperMind task still runs inside the selected `agent-api` process. If that container exits while processing, the in-process task is lost. The backend maximum-wait setting and BullMQ retry policy provide recovery, but fully durable execution would require a separate PaperMind worker consuming a persistent queue.

## Document-processing pipeline

1. The frontend uploads a PDF to the backend API.
2. The backend stores metadata in PostgreSQL and creates a BullMQ job in Redis.
3. A `document-worker` creates the backend PaperMind job record in Redis.
4. The worker submits the mounted PDF path to `agent-load-balancer`.
5. An `agent-api` replica returns `202 Accepted` and begins processing.
6. PaperMind uses the extractor, GROBID, and optionally Ollama to create a canonical package.
7. PaperMind sends `running`, `completed`, or `failed` callbacks to the backend API.
8. The document worker reads the shared Redis state until processing completes.
9. The worker submits the canonical package to the indexer.
10. The indexer creates hierarchical chunks and embeddings and writes `chunks.json`.
11. The worker uploads `chunks.json` to the ingester.
12. The ingester bulk-indexes the chunks into OpenSearch.
13. The backend marks the document as processed in PostgreSQL.
14. RAG requests perform hybrid retrieval and return answers with citations.

### Output layout

A processed document normally resembles:

```text
data/users/<user-id>/<folder>/
├── source-document.pdf
├── pdfMind_<safe-document-name>/
│   ├── canonical_document.json
│   ├── manifest.json
│   ├── assets/
│   └── ...
└── indexer_<safe-document-name>/
    ├── chunks.json
    └── ...
```

`canonical_document.json` is treated as the PaperMind completion marker. A merely non-empty directory is not considered complete because it may contain partial output from an interrupted task.

## Repository layout

| Path | Purpose |
| --- | --- |
| `frontend/` | Next.js and React web application. |
| `backend-api/` | Express API, authentication, RAG orchestration, BullMQ queue, callbacks, and document worker. |
| `paperMind/agent/` | Canonicalization agent and backend callback client. |
| `paperMind/tools/api/` | Docling and GROBID extraction API. |
| `indexer/` | Canonical-package validation, chunking, embeddings, API, and CLI. |
| `ingester/` | OpenSearch validation and ingestion API and CLI. |
| `postgreSQL/` | PostgreSQL, PgBouncer, schema, and setup scripts. |
| `opensearch/` | OpenSearch Compose files, index template, and verification scripts. |
| `nginx/` | Public gateway and internal load-balancer configurations. |
| `.github/workflows/ci.yml` | Repository-wide continuous integration workflow. |
| `docker-compose.yml` | Integrated root Compose project. |
| `start.sh` | Local bootstrap helper. Review it before production use. |

## Requirements

### Docker deployment

- Linux is recommended.
- Docker Engine 24 or newer.
- Docker Compose v2 with Compose `include` support.
- At least 16 GB RAM; 32 GB or more is recommended for extraction, embeddings, OpenSearch, and LLM services together.
- At least 30 GB free disk space for images, uploaded PDFs, models, OpenSearch data, and generated packages.
- `vm.max_map_count=262144` for OpenSearch.
- NVIDIA driver and NVIDIA Container Toolkit for the default GPU overlay.

### Local development

- Node.js 22+ for the frontend.
- Node.js 24 for backend parity with CI and the backend image.
- Python 3.12 for PaperMind and the indexer.
- Python 3.11+ for the ingester.
- PostgreSQL 16.
- Redis 7.
- OpenSearch 3.

## Quick start

### 1. Clone the repository

```bash
git clone <repository-url>
cd DocuMind
```

### 2. Create local environment files

```bash
cp .env.example .env
cp postgreSQL/.env.example postgreSQL/.env
cp indexer/.env.example indexer/.env
cp ingester/.env.example ingester/.env
cp paperMind/.env.example paperMind/.env
cp paperMind/agent/.env.example paperMind/agent/.env
cp paperMind/tools/.env.example paperMind/tools/.env
cp backend-api/.env.example backend-api/.env
cp frontend/.env.example frontend/.env.local
```

Do not commit runtime `.env` files or real credentials.

### 3. Generate the shared PaperMind callback secret

```bash
CALLBACK_TOKEN="$(openssl rand -hex 32)"
printf '%s\n' "$CALLBACK_TOKEN"
```

Set the exact same value in both files:

```dotenv
# backend-api/.env
PAPERMIND_CALLBACK_TOKEN=<generated-secret>
```

```dotenv
# paperMind/.env
PAPERMIND_CALLBACK_TOKEN=<generated-secret>
```

### 4. Prepare host directories

```bash
mkdir -p \
  data/users \
  data/postgreSQL \
  data/opensearch \
  paperMind/outputs
```

Use absolute host paths where required:

```dotenv
# postgreSQL/.env
DATA_DIR=/absolute/path/to/DocuMind/data/postgreSQL
```

```dotenv
# paperMind/.env
HOST_ACCESS_ROOT=/absolute/path/to/DocuMind/data
OUTPUT_DIR=/absolute/path/to/DocuMind/paperMind/outputs
CUSTOM_OUTPUT_DIR=/absolute/path/to/DocuMind/paperMind/outputs
```

```dotenv
# indexer/.env
DOCUMIND_INPUT_ROOT_HOST=/absolute/path/to/DocuMind/data/users
DOCUMIND_OUTPUT_ROOT_HOST=/absolute/path/to/DocuMind/data/users
```

The backend mounts `./data/users` at `/data/users`. PaperMind mounts the root data directory at `/host`, so `/data/users/...` in the backend corresponds to `/host/users/...` in PaperMind.

### 5. Configure OpenSearch host requirements

```bash
sudo sysctl -w vm.max_map_count=262144
```

Persist this setting using your operating system's sysctl configuration before production deployment.

Ensure the OpenSearch data directory is writable by the container:

```bash
sudo mkdir -p data/opensearch
sudo chown -R 1000:1000 data/opensearch
```

Update the OpenSearch bind mount when its Compose file still points to a different absolute host path.

### 6. Validate Compose

```bash
sudo docker compose config --quiet
```

### 7. Build and start the recommended topology

```bash
sudo docker compose up -d \
  --build \
  --force-recreate \
  --remove-orphans \
  --scale document-worker=3 \
  --scale agent-api=3 \
  --scale indexer-api=1 \
  --scale ingester-api=2
```

Recommended initial replica counts:

| Service | Replicas | Reason |
| --- | ---: | --- |
| `document-worker` | 3 | Three independently queued document pipelines. |
| `agent-api` | 3 | Safe because status is stored in backend Redis and reported by callback. |
| `indexer-api` | 1 | Indexing job state is still process-local while jobs are active. |
| `ingester-api` | 2 | Each ingestion request is independent and mostly stateless. |

### 8. Apply the PostgreSQL schema

```bash
set -a
source postgreSQL/.env
set +a

sudo docker compose exec -T postgres \
  psql -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  < postgreSQL/schema.sql
```

Or run the repository helper:

```bash
bash postgreSQL/apply_schema_nginx.sh
```

### 9. Apply the OpenSearch template

```bash
bash opensearch/apply_schema_nginx.sh
```

### 10. Open the application

- Web application: `http://localhost`
- Public gateway health: `http://localhost/health`

### About `start.sh`

`start.sh` is a local convenience script that prepares directories and environment values. Review it before use because it may overwrite local `.env` values and may contain development-only credentials. For the final multi-agent topology, its Compose command should include the replica flags shown above.

## Configuration

### Backend API and document worker

Important settings in `backend-api/.env`:

```dotenv
# Application
PORT=3000
JWT_SECRET=replace-with-a-long-random-secret
SESSION_DAYS=7
UPLOAD_DIR=/data/users

# PostgreSQL / PgBouncer
DB_HOST=pgbouncer
DB_PORT=6432
DB_USER=documind
DB_PASSWORD=replace-me
DB_NAME=documind_postgresql

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
# REDIS_URL=redis://redis:6379

# PaperMind submission and backend-owned status
PROCESSOR_SUBMIT_URL=http://agent-load-balancer:8080/v1/process-path-async
PROCESSOR_REQUEST_TIMEOUT_MS=30000
PROCESSOR_POLL_INTERVAL_MS=5000
PROCESSOR_MAX_WAIT_MS=7200000
PROCESSOR_MOUNT_ROOT=/host/users
PROCESSOR_USE_LLM=true
PROCESSOR_OVERWRITE=false
PAPERMIND_CALLBACK_TOKEN=replace-with-the-shared-secret
PAPERMIND_JOB_TTL_SECONDS=86400

# BullMQ worker concurrency per container
DOCUMENT_WORKER_CONCURRENCY=1

# Indexer
INDEXING_URL=http://indexer-load-balancer:8080/v1/indexing/jobs
INDEXING_API_KEY=replace-with-indexer-api-key
INDEXING_TIMEOUT_MS=30000
INDEXING_POLL_INTERVAL_MS=3000
INDEXING_MAX_WAIT_MS=1800000
INDEXING_MAX_STATUS_ERRORS=3
INDEXING_INPUT_MOUNT_ROOT=/data/input
INDEXING_OUTPUT_MOUNT_ROOT=/data/output

# Ingester
INGEST_URL=http://ingester-load-balancer:8080/ingest
INGEST_API_KEY=replace-with-ingester-api-key
INGEST_TIMEOUT_MS=0
INGEST_DRY_RUN=false
EXPECTED_EMBEDDING_DIMENSIONS=1024
CHUNKS_FILE_WAIT_MS=30000
CHUNKS_FILE_POLL_INTERVAL_MS=1000

# Query embeddings and OpenSearch
INDEXER_BASE_URL=http://indexer-load-balancer:8080
INDEXER_API_KEY=replace-with-indexer-api-key
OPENSEARCH_NODE=https://opensearch:9200
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=replace-me
OPENSEARCH_INDEX=documind-chunks-*
OPENSEARCH_TLS_REJECT_UNAUTHORIZED=false
EMBEDDING_DIMENSIONS=1024
RAG_CANDIDATE_K=30
RAG_TOP_K=8
RAG_MAX_CONTEXT_CHARS=18000

# Ollama RAG generation
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5vl:3b
OLLAMA_KEEP_ALIVE=5m
LLM_CONTEXT_SIZE=16384
LLM_MAX_OUTPUT_TOKENS=1200
LLM_TEMPERATURE=0.1
LLM_TOP_P=0.9
LLM_REPEAT_PENALTY=1.1
```

Do not configure the old setting below in the backend-managed callback architecture:

```dotenv
PROCESSOR_JOBS_URL=...
```

The worker must poll backend Redis, not PaperMind's replica-local status endpoint.

### PaperMind

Important settings in `paperMind/.env`:

```dotenv
# Mounted paths
PATH_API_ENABLED=true
HOST_ACCESS_ROOT=/absolute/path/to/DocuMind/data
ALLOWED_INPUT_DIRECTORIES=/host
ALLOWED_OUTPUT_DIRECTORIES=/host,/data/outputs,/data/custom-output
OUTPUT_DIR=/absolute/path/to/DocuMind/paperMind/outputs
CUSTOM_OUTPUT_DIR=/absolute/path/to/DocuMind/paperMind/outputs

# Backend lifecycle callbacks
BACKEND_CALLBACK_BASE_URL=http://api:3000/internal/papermind/jobs
PAPERMIND_CALLBACK_TOKEN=replace-with-the-shared-secret
BACKEND_CALLBACK_TIMEOUT_SECONDS=10
BACKEND_CALLBACK_MAX_RETRIES=5

# Agent and extraction limits
MAX_UPLOAD_SIZE_MB=100
MAX_CONCURRENCY=1
DOCLING_MAX_NUM_PAGES=300
DOCLING_MAX_CONCURRENCY=1
DOCLING_DOCUMENT_TIMEOUT_SECONDS=3600
TOOLS_TIMEOUT_SECONDS=3900
GROBID_TIMEOUT_SECONDS=1800
GROBID_MAX_RETRIES=2

# Output
KEEP_RAW_EXTRACTOR_RESPONSE=false
OVERWRITE_EXISTING_PACKAGE=false
CREATE_ZIP_PACKAGE=true

# Ollama enrichment
LLM_ENABLED=true
OLLAMA_MODEL=qwen2.5vl:3b
OLLAMA_TIMEOUT_SECONDS=600
LLM_DESCRIBE_ALL_ELEMENTS=true
LLM_MAX_ITEMS_PER_DOCUMENT=500
```

`BACKEND_CALLBACK_BASE_URL` should use the internal Compose service name `api`, not `localhost`.

### Indexer

Important settings in `indexer/.env`:

```dotenv
API_KEY=replace-with-indexer-api-key
MAX_CONCURRENT_JOBS=1
JOB_HISTORY_LIMIT=1000
MODEL_PRELOAD=false

DOCUMIND_INPUT_ROOT_HOST=/absolute/path/to/DocuMind/data/users
DOCUMIND_OUTPUT_ROOT_HOST=/absolute/path/to/DocuMind/data/users
HF_CACHE_VOLUME_NAME=documind-huggingface-cache

CHILD_TARGET_TOKENS=300
CHILD_MAX_TOKENS=420
CHILD_OVERLAP_TOKENS=50
PARENT_TARGET_TOKENS=900
PARENT_MAX_TOKENS=1100
SPECIAL_ELEMENTS_MAX_TOKENS=1800

EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_BATCH_SIZE=8
EMBEDDING_DEVICE=auto
EMBEDDING_EXPECTED_DIMENSIONS=1024
```

The indexer, ingester, backend RAG configuration, and OpenSearch mapping must all use the same embedding dimension.

### Ingester

Important settings in `ingester/.env`:

```dotenv
INGESTOR_API_KEY=replace-with-ingester-api-key
INGESTOR_MAX_UPLOAD_BYTES=536870912

OPENSEARCH_URL=https://opensearch:9200
OPENSEARCH_INDEX=documind-chunks-v1
OPENSEARCH_USERNAME=admin
OPENSEARCH_PASSWORD=replace-me
OPENSEARCH_VERIFY_CERTS=false

OPENSEARCH_INSTALL_TEMPLATE=true
OPENSEARCH_TEMPLATE_NAME=documind-chunks-template
OPENSEARCH_EMBEDDING_DIMENSIONS=1024
OPENSEARCH_BULK_BATCH_SIZE=250
INGESTOR_REPLACE_DOCUMENT=true
INGESTOR_REFRESH=true
```

### PostgreSQL

Important settings in `postgreSQL/.env`:

```dotenv
POSTGRES_USER=documind
POSTGRES_PASSWORD=replace-me
POSTGRES_DB=documind_postgresql
PG_PORT=5433
PGBOUNCER_PORT=6432
DATA_DIR=/absolute/path/to/DocuMind/data/postgreSQL
```

## Scaling

### Recommended single-GPU topology

```bash
sudo docker compose up -d \
  --build \
  --force-recreate \
  --remove-orphans \
  --scale document-worker=3 \
  --scale agent-api=3 \
  --scale indexer-api=1 \
  --scale ingester-api=2
```

This configuration accepts and tracks three document pipelines concurrently. It does not guarantee that three documents perform heavy extraction simultaneously.

### What each replica count changes

#### `document-worker`

Each worker container consumes BullMQ jobs. With:

```dotenv
DOCUMENT_WORKER_CONCURRENCY=1
```

three containers provide up to three active end-to-end pipelines.

#### `agent-api`

Multiple replicas are now safe because lifecycle state is stored in backend Redis. Nginx can send each submission to any healthy replica.

#### `extractor-api`

PaperMind agents share the extraction service. With:

```dotenv
DOCLING_MAX_CONCURRENCY=1
```

only one heavy Docling operation runs at a time. Additional agent replicas improve request distribution and isolation, but extraction throughput remains limited by Docling, Ollama, GPU memory, CPU, and RAM.

Increase extraction concurrency only after measuring memory use and stability. On multi-GPU systems, the more reliable design is one controlled extraction worker per assigned GPU.

#### `indexer-api`

Keep one active replica for asynchronous indexing jobs. Its current job manager uses process-local live state, so submission and status polling can fail when routed to different replicas.

#### `ingester-api`

The ingester handles one complete request and writes to shared OpenSearch. Multiple replicas are generally safe. Its process-local document lock does not coordinate duplicate writes across replicas, so the backend should still submit only one ingestion request per document.

### Scaling does not replace capacity planning

More HTTP replicas do not automatically make GPU or embedding work faster. Measure:

- GPU memory and utilization.
- System RAM.
- Docling processing duration.
- Ollama model latency.
- Indexer embedding throughput.
- OpenSearch indexing latency.
- Redis queue depth.

## Operations and verification

### Service status

```bash
sudo docker compose ps
```

### Follow the complete document pipeline

```bash
sudo docker compose logs -f \
  api \
  document-worker \
  agent-load-balancer \
  agent-api \
  extractor-api \
  indexer-load-balancer \
  indexer-api \
  ingester-load-balancer \
  ingester-api
```

### Verify multiple PaperMind replicas

```bash
sudo docker compose ps agent-api
```

Nginx access logs include the selected upstream address:

```bash
sudo docker compose logs --since=10m agent-load-balancer \
  | grep 'process-path-async'
```

### Verify shared PaperMind state

List keys:

```bash
sudo docker compose exec redis \
  redis-cli KEYS 'papermind:job:*'
```

Inspect one job:

```bash
sudo docker compose exec redis \
  redis-cli HGETALL 'papermind:job:<backend-job-id>'
```

Expected states:

```text
queued
running
completed
```

There should be no document-worker polling requests to:

```text
GET /v1/jobs/<job-id>
```

### Verify callbacks

```bash
sudo docker compose logs --since=10m api \
  | grep '/internal/papermind/jobs/'
```

A successful callback returns HTTP `204`.

### Rebuild one changed service

Docker can reuse an existing image even after containers and source folders have been removed. Force a clean rebuild when source and container code differ:

```bash
sudo docker compose stop document-worker
sudo docker compose rm -sf document-worker
sudo docker compose build --no-cache --pull document-worker
sudo docker compose up -d \
  --force-recreate \
  --scale document-worker=3 \
  document-worker
```

Use the same pattern for `agent-api`, `indexer-api`, or another service.

### Stop the stack

Keep volumes:

```bash
sudo docker compose down
```

Delete named volumes as well:

```bash
sudo docker compose down --volumes
```

Deleting volumes can permanently remove Redis data, model caches, and other persistent data. Bind-mounted PostgreSQL and OpenSearch directories must be managed separately.

## API overview

### Backend API

All public application endpoints are under `/api`.

| Area | Example endpoints |
| --- | --- |
| Health | `GET /api/health` |
| Authentication | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh-token`, `POST /api/auth/logout`, `GET /api/auth/me` |
| Documents | Upload, list, metadata, download, and deletion under `/api/documents` |
| Folders | Create, list, read, update, manage documents, and delete under `/api/folders` |
| Conversations | Create, list, read, rename, and delete under `/api/conversations` |
| RAG | `POST /api/rag/search` |

Internal service endpoint:

| Endpoint | Purpose |
| --- | --- |
| `POST /internal/papermind/jobs/:backendJobId/status` | Authenticated PaperMind lifecycle callback. |

### PaperMind agent

| Endpoint | Purpose |
| --- | --- |
| `GET /health/live` | Liveness check. |
| `GET /health/ready` | Readiness check. |
| `GET /v1/runtime` | Runtime configuration summary. |
| `POST /v1/process` | Upload and synchronously process a PDF. |
| `POST /v1/process-path` | Synchronously process a PDF from an approved mounted path. |
| `POST /v1/process-path-async` | Accept a backend-managed asynchronous path job. |
| `GET /v1/jobs/{job_id}` | Local agent job diagnostics; not used by the backend worker. |
| `GET /v1/documents/{document_id}` | Read generated document metadata. |
| `GET /v1/documents/{document_id}/download` | Download a generated package. |

Example asynchronous request:

```json
{
  "backend_job_id": "papermind-document-123",
  "input_directory": "/host/users/user-123/folder",
  "input_filename": "article.pdf",
  "output_directory": "/host/users/user-123/folder",
  "output_folder": "pdfMind_article",
  "use_llm": true,
  "overwrite": false
}
```

### Indexer

| Endpoint | Purpose |
| --- | --- |
| `GET /health/live` | Liveness check. |
| `GET /health/ready` | Storage and model readiness. |
| `POST /v1/indexing/jobs` | Start indexing for a mounted canonical package. |
| `GET /v1/indexing/jobs` | List recent local jobs. |
| `GET /v1/indexing/jobs/{job_id}` | Read job state and output. |
| `POST /v1/embeddings/query` | Embed a search query. |

### Ingester

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Health check. |
| `POST /ingest` | Validate and optionally index `chunks.json` or a ZIP package. |
| `GET /docs` | FastAPI interactive documentation. |

## Local development

### Frontend

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Default URL: `http://localhost:3000`

Useful commands:

```bash
npm run lint
npm run typecheck
npm run build
```

The postinstall script copies the PDF.js worker into `public/pdf.worker.min.mjs`.

### Backend API

```bash
cd backend-api
cp .env.example .env
npm ci
npm run dev
```

Run a document worker in another terminal:

```bash
npm run worker:documents
```

For local non-Docker development, the API, worker, Redis, PostgreSQL, PaperMind, indexer, ingester, OpenSearch, and Ollama endpoints must be reachable using the configured URLs.

### PaperMind agent

```bash
cd paperMind/agent
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
```

### PaperMind extraction API

```bash
cd paperMind/tools/api
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest -q
```

The real extraction runtime also requires the pinned Docling, PyTorch, OCR, and model dependencies installed by the Docker image.

### Indexer

```bash
cd indexer
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
pytest -q
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

Offline sample:

```bash
documind-indexer chunk examples/sample_pdf_output \
  --user-id local-user \
  --document-id local-document \
  --config examples/chunking_config.dev.json \
  --output /tmp/documind-chunks.json
```

### Ingester

```bash
cd ingester
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
pytest -q
uvicorn documind_ingestor.api:app --host 0.0.0.0 --port 8080 --reload
```

Dry-run validation:

```bash
documind-ingestor examples/chunks.json \
  --expected-embedding-dimensions 32 \
  --dry-run
```

## Testing

Run component checks from their own directories.

### Frontend

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run build
```

### Backend

```bash
cd backend-api
npm ci
find src -type f -name '*.js' -print0 \
  | xargs -0 -n1 node --check
```

### Python services

```bash
cd indexer
python -m pip install -r requirements-dev.txt
pytest -q

cd ../ingester
python -m pip install -r requirements-dev.txt
pytest -q

cd ../paperMind/agent
python -m pip install -r requirements-dev.txt
pytest -q

cd ../tools/api
python -m pip install -r requirements-dev.txt
pytest -q
```

### Compose validation

After creating local environment files:

```bash
sudo docker compose config --quiet
```

## Continuous integration

`.github/workflows/ci.yml` runs on pushes, pull requests, and manual dispatches. The workflow includes:

- JSON and YAML validation.
- Shell syntax validation.
- Merge-conflict marker checks.
- Rejection of committed runtime `.env` files.
- Rejection of committed `.next` output and TypeScript build metadata.
- Docker Compose configuration validation.
- Frontend dependency installation, ESLint, TypeScript route generation/checking, and production build.
- Backend dependency installation, JavaScript syntax checks, and module imports with Redis available.
- Ruff, formatting, compilation, and pytest checks for Python services.
- PostgreSQL schema application and required-table verification.
- OpenSearch startup, index-template application, and verification.
- Docker image builds for application services.
- A final required status job suitable for branch protection.

CI uses temporary credentials and service containers. Production secrets are not required.

## Troubleshooting

### PaperMind returns `Job not found`

This indicates the backend is still polling PaperMind's local job endpoint or is running an old worker image.

Verify that `backend-api/.env` contains:

```dotenv
PROCESSOR_SUBMIT_URL=http://agent-load-balancer:8080/v1/process-path-async
```

Remove:

```dotenv
PROCESSOR_JOBS_URL=...
```

Search worker logs. There should be no HTTP status polling against `/v1/jobs/<job-id>`.

Rebuild the worker without cache:

```bash
sudo docker compose build --no-cache document-worker
sudo docker compose up -d \
  --force-recreate \
  --scale document-worker=3 \
  document-worker
```

### PaperMind remains `queued` or `running`

Check callback connectivity:

```bash
sudo docker compose logs --since=10m agent-api api
```

Verify:

- `BACKEND_CALLBACK_BASE_URL=http://api:3000/internal/papermind/jobs`
- Both services use the same `PAPERMIND_CALLBACK_TOKEN`.
- `api` and `agent-api` share `backend_network`.
- The backend Redis job key exists.

A callback `401` means the tokens do not match. A callback `404` means the backend Redis job record does not exist or the correlation ID is incorrect.

### PaperMind submission returns `502`, `503`, or `504`

Check the agent and downstream services:

```bash
sudo docker compose ps agent-api extractor-api grobid ollama
sudo docker compose logs --tail=200 \
  agent-load-balancer agent-api extractor-api grobid ollama
```

The asynchronous submission should return quickly, so a submission `504` usually means the request never reached a ready agent or the running containers use old source/configuration.

### Worker source differs from the running container

Check a known line inside the container:

```bash
sudo docker compose exec -T document-worker \
  grep -n 'waitForBackendPaperMindJob' \
  /app/src/worker/documentProcessorWorker.js
```

If it is missing, rebuild with `--no-cache` and recreate the containers.

### Indexer error: `A text unit has 360 tokens, above body max 359`

This is a tokenizer decode/re-encode boundary issue. The Hugging Face tokenizer adapter must verify the token count after decoding each split and shrink the source window until the decoded text fits.

After applying the corrected `indexer/app/embedding/tokenizer.py`, rebuild the indexer:

```bash
sudo docker compose stop indexer-api
sudo docker compose rm -sf indexer-api
sudo docker compose build --no-cache indexer-api
sudo docker compose up -d \
  --force-recreate \
  --scale indexer-api=1 \
  indexer-api indexer-load-balancer
```

Verify the corrected helper exists:

```bash
sudo docker compose exec -T indexer-api \
  grep -n '_decode_fitting_window' \
  /app/app/embedding/tokenizer.py
```

Increasing `CHILD_MAX_TOKENS` may hide one occurrence but does not fix the boundary condition.

### Indexer status intermittently returns `404`

Keep:

```bash
--scale indexer-api=1
```

The indexer's active asynchronous job state is not yet shared across replicas.

### OpenSearch fails during startup

Apply:

```bash
sudo sysctl -w vm.max_map_count=262144
```

Then inspect:

```bash
sudo docker compose logs --tail=200 opensearch
```

Also verify permissions on the bind-mounted data directory.

### Embedding dimension mismatch

These values must match:

- Indexer `EMBEDDING_EXPECTED_DIMENSIONS`.
- Backend `EMBEDDING_DIMENSIONS`.
- Backend `EXPECTED_EMBEDDING_DIMENSIONS`.
- Ingester `OPENSEARCH_EMBEDDING_DIMENSIONS`.
- OpenSearch vector mapping dimension.

For `BAAI/bge-m3`, the expected dimension is normally `1024`.

### Frontend route or generated type is stale

Remove generated output and rebuild:

```bash
rm -rf frontend/.next frontend/tsconfig.tsbuildinfo
cd frontend
npm run typecheck
npm run build
```

Do not commit `.next` or `tsconfig.tsbuildinfo`.

### File permission errors

Check the host UID/GID and mounted directories:

```bash
id -u
id -g
ls -ld data data/users paperMind/outputs
```

Set `HOST_UID`, `HOST_GID`, `APP_UID`, and `APP_GID` to values appropriate for the host. Ensure input directories are readable and output directories are writable.

### Hugging Face cache volume warning

The indexer model cache is a named Docker volume. Preserve it between restarts to avoid downloading models again. Do not run `docker compose down -v` unless model-cache deletion is intentional.

## Security

- Replace all example passwords, API keys, callback tokens, and JWT secrets.
- Never commit runtime `.env` files.
- Keep Redis, PostgreSQL, PgBouncer, OpenSearch, PaperMind, indexer, ingester, GROBID, Ollama, and internal Nginx services private.
- Expose only the public gateway unless another interface is explicitly required.
- Use TLS at the public Nginx layer in production.
- Use a long random `PAPERMIND_CALLBACK_TOKEN` and rotate it when exposure is suspected.
- Restrict `HOST_ACCESS_ROOT` to the smallest directory PaperMind needs. Do not mount `/` in an internet-accessible deployment.
- Keep OpenSearch certificate verification enabled when using trusted certificates.
- Review upload limits in the frontend, backend, Nginx, and PaperMind together.
- Use least-privilege file ownership for bind-mounted data.
- Protect backups because they may contain uploaded documents and conversation data.

## Data persistence and backups

Important persistent data includes:

| Data | Typical location |
| --- | --- |
| Uploaded PDFs and generated packages | `data/users/` |
| PostgreSQL | Configured `postgreSQL/.env` `DATA_DIR` |
| OpenSearch | Configured OpenSearch host bind mount |
| Redis | Docker named volume `redis_data` |
| Indexer model cache | Docker named volume such as `documind-huggingface-cache` |
| PaperMind/Docling/Ollama models | Docker named volumes in the PaperMind Compose project |

Back up PostgreSQL, OpenSearch, uploaded documents, and generated packages regularly. Redis job records are operational state and should not be treated as the only permanent record of document completion.

## Component documentation

Additional details are available in:

- `paperMind/README.md`
- `paperMind/BACKEND_MANAGED_JOBS.md`
- `paperMind/DEPLOYMENT.md`
- `paperMind/SECURITY.md`
- `indexer/README.md`
- `indexer/API.md`
- `indexer/DOCKER.md`
- `ingester/README.md`
- `postgreSQL/README.md`
- `opensearch/README.md`
- `frontend/README.md`
