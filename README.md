# DocuMind

DocuMind is a self-hosted document question-answering platform built around a retrieval-augmented generation (RAG) pipeline. Users can upload PDFs, organize documents into folders, process them into canonical structured data, generate embeddings, index chunks in OpenSearch, and ask grounded questions with page-level citations.

The repository is a multi-service application containing a Next.js frontend, an Express API and background worker, Python document-processing services, PostgreSQL, Redis, OpenSearch, Ollama, and Nginx.

## Features

- User registration, login, refresh-token sessions, and authenticated APIs.
- PDF upload, document management, folder organization, and processing status.
- Scientific PDF extraction with Docling and GROBID.
- Canonical document generation with figures, tables, formulas, references, and provenance.
- Configurable parent, child, and special-element chunking.
- Dense query and document embeddings.
- OpenSearch vector and keyword retrieval.
- RAG answers generated through Ollama.
- Saved conversations and source metadata.
- Clickable PDF citations with page navigation and bounding-box highlights.
- Docker Compose deployment with internal Nginx load balancers.
- GitHub Actions CI for frontend, backend, Python services, PostgreSQL, OpenSearch, configuration, and Docker builds.

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
Express API :3000 ------------------------------+
  |                                              |
  | PostgreSQL / PgBouncer                       | Redis / BullMQ
  |                                              |
  |                                              v
  |                                      Document worker
  |                                              |
  |             +--------------------------------+------------------+
  |             |                                                   |
  |             v                                                   v
  |     PaperMind agent                                      Indexer API
  |     Docling + GROBID + Ollama                            Chunk + embed
  |             |                                                   |
  |             +---------------- canonical package ---------------+
  |                                                                 |
  |                                                                 v
  |                                                          Ingester API
  |                                                                 |
  +---------------- RAG search <----------------------------- OpenSearch
```

### Document-processing flow

1. The frontend uploads a PDF to the backend API.
2. The backend stores document metadata in PostgreSQL and places a job in Redis/BullMQ.
3. The document worker sends the PDF to PaperMind.
4. PaperMind extracts text and layout data, then creates a canonical document package.
5. The indexer converts the package into retrieval chunks and embeddings.
6. The ingester validates the generated `chunks.json` and bulk-indexes it into OpenSearch.
7. The document becomes available for global, folder-scoped, or document-scoped RAG queries.
8. The backend performs hybrid retrieval, sends the context to Ollama, and returns an answer with citations.

## Repository layout

| Path | Purpose |
| --- | --- |
| `frontend/` | Next.js 16 and React 19 web application. |
| `backend-api/` | Express API, authentication, RAG orchestration, BullMQ queue, and document worker. |
| `paperMind/agent/` | PDF canonicalization and enrichment service. |
| `paperMind/tools/api/` | Docling and GROBID extraction API. |
| `indexer/` | Canonical-package chunking and embedding service and CLI. |
| `ingester/` | OpenSearch ingestion API and CLI. |
| `postgreSQL/` | PostgreSQL, PgBouncer, and the application schema. |
| `opensearch/` | OpenSearch Compose files, index template, and verification scripts. |
| `nginx/` | Public gateway and internal service load-balancer configurations. |
| `.github/workflows/ci.yml` | Repository-wide continuous integration workflow. |
| `docker-compose.yml` | Full integrated stack. |

## Requirements

### Full Docker deployment

- Linux is recommended.
- Docker Engine 24 or newer.
- Docker Compose v2 with Compose `include` support.
- At least 16 GB RAM; more is recommended when running extraction and LLM services together.
- At least 30 GB free disk space for images, models, OpenSearch data, and uploaded documents.
- `vm.max_map_count=262144` for OpenSearch.
- An NVIDIA GPU, NVIDIA driver, and NVIDIA Container Toolkit for the default root Compose configuration, which includes the PaperMind GPU overlay.

### Local development

- Node.js 22+ for the frontend.
- Node.js 24 for the backend Docker image; Node.js 22+ also works for local source checks.
- Python 3.11+ for the indexer and ingester.
- Python 3.12 for PaperMind.
- PostgreSQL 16, Redis 7, and OpenSearch 3 when running services outside Docker.

## Configuration

Never commit real `.env` files. Create local files from the examples:

```bash
cp .env.example .env
cp postgreSQL/.env.example postgreSQL/.env
cp indexer/.env.example indexer/.env
cp ingester/.env.example ingester/.env
cp paperMind/.env.example paperMind/.env
cp backend-api/.env.example backend-api/.env
cp frontend/.env.example frontend/.env.local
```

At minimum, replace every value containing `change-me` and review these settings:

| File | Important settings |
| --- | --- |
| `postgreSQL/.env` | Database user, password, database name, and data directory. |
| `backend-api/.env` | JWT secret, database, Redis, processing, indexing, ingestion, OpenSearch, and Ollama endpoints. |
| `paperMind/.env` | Host-access root, output directories, LLM model, ports, CPU/GPU settings, and processing limits. |
| `indexer/.env` | Input/output mounts, API key, embedding model, embedding dimensions, and chunking policy. |
| `ingester/.env` | API key, OpenSearch credentials, index name, template, and expected vector dimensions. |
| `frontend/.env.local` | Backend proxy target for local frontend development. |

The indexer, ingester, backend, and OpenSearch vector mapping must use the same embedding dimension. The sample development data uses 32-dimensional deterministic embeddings; production defaults are intended for a real sentence-transformer model and must match the OpenSearch index template.

## Quick start with Docker Compose

### 1. Clone and configure

```bash
git clone <repository-url>
cd DocuMind

cp .env.example .env
cp postgreSQL/.env.example postgreSQL/.env
cp indexer/.env.example indexer/.env
cp ingester/.env.example ingester/.env
cp paperMind/.env.example paperMind/.env
cp backend-api/.env.example backend-api/.env
```

Edit the generated files and set strong passwords and API keys.

### 2. Prepare host directories

```bash
mkdir -p \
  data/users \
  data/postgreSQL \
  data/opensearch \
  paperMind/outputs
```

Set absolute host paths in the relevant `.env` files. In particular:

```dotenv
# postgreSQL/.env
DATA_DIR=/absolute/path/to/DocuMind/data/postgreSQL

# paperMind/.env
HOST_ACCESS_ROOT=/absolute/path/to/DocuMind/data
OUTPUT_DIR=/absolute/path/to/DocuMind/paperMind/outputs
CUSTOM_OUTPUT_DIR=/absolute/path/to/DocuMind/paperMind/outputs

# indexer/.env
DOCUMIND_INPUT_ROOT_HOST=/absolute/path/to/DocuMind/data/users
DOCUMIND_OUTPUT_ROOT_HOST=/absolute/path/to/DocuMind/data/users
```

The OpenSearch Compose file currently binds `/srv/DocuMind/data/opensearch`. Change that source path in `opensearch/docker-compose-nginx.yml` when your repository is stored elsewhere.

### 3. Configure the host for OpenSearch

```bash
sudo sysctl -w vm.max_map_count=262144
sudo mkdir -p /srv/DocuMind/data/opensearch
sudo chown -R 1000:1000 /srv/DocuMind/data/opensearch
```

Persist `vm.max_map_count` using your operating system's normal sysctl configuration before production use.

### 4. Validate and start

```bash
docker compose config --quiet
docker compose up -d --build
```

View status and logs:

```bash
docker compose ps
docker compose logs -f --tail=200
```

### 5. Apply the PostgreSQL schema

```bash
set -a
source postgreSQL/.env
set +a

docker compose exec -T postgres \
  psql -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" \
  < postgreSQL/schema.sql
```

### 6. Install the OpenSearch template

```bash
bash opensearch/apply_schema_nginx.sh
```

### 7. Open the application

- Web application: `http://localhost`
- Public gateway health: `http://localhost/health`

The browser sends `/api/*` requests to the Next.js proxy, which forwards them to the backend service on the private Docker network.

## CPU-only PaperMind deployment

The root Compose file includes the NVIDIA overlay. For a CPU-only PaperMind instance, run the standalone CPU Compose stack:

```bash
cd paperMind
cp .env.example .env
docker compose -f compose.yaml up -d --build
```

Then configure `PROCESSOR_URL` in `backend-api/.env` to point to the reachable PaperMind agent endpoint. When the backend is in a different Compose project, attach both projects to a shared external Docker network or publish the PaperMind port on a trusted interface.

## Local development

### Frontend

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Default development URL: `http://localhost:3000`.

Useful commands:

```bash
npm run lint
npm exec tsc -- --noEmit
npm run build
```

The postinstall script copies the PDF.js worker into `public/pdf.worker.min.mjs`.

### Backend API and worker

```bash
cd backend-api
cp .env.example .env
npm ci
npm run dev
```

Run the worker in a second terminal:

```bash
npm run worker:documents
```

Backend health endpoint:

```text
GET /api/health
```

### Indexer

```bash
cd indexer
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
pytest -q
```

Run an offline sample:

```bash
documind-indexer chunk examples/sample_pdf_output \
  --user-id local-user \
  --document-id local-document \
  --config examples/chunking_config.dev.json \
  --output /tmp/documind-chunks.json
```

Run the API:

```bash
uvicorn app.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Ingester

```bash
cd ingester
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install -e .
pytest -q
```

Validate sample chunks without connecting to OpenSearch:

```bash
documind-ingestor examples/chunks.json \
  --expected-embedding-dimensions 32 \
  --dry-run
```

Run the API:

```bash
uvicorn documind_ingestor.api:app --host 0.0.0.0 --port 8080 --reload
```

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

The lightweight unit tests use the base development requirements. A real extraction runtime additionally needs the pinned Docling and PyTorch dependencies used by the Docker image.

```bash
cd paperMind/tools/api
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
pytest -q
```

## API overview

### Backend API

All application endpoints are under `/api`.

| Area | Endpoints |
| --- | --- |
| Health | `GET /api/health` |
| Authentication | `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh-token`, `POST /api/auth/logout`, `GET /api/auth/me` |
| Documents | Upload, list, metadata, download, and delete under `/api/documents` |
| Folders | Create, list, read, update, manage documents, and delete under `/api/folders` |
| Conversations | Create, list, read, rename, and delete under `/api/conversations` |
| RAG | `POST /api/rag/search` |

Protected endpoints expect a bearer access token. Login and refresh operations also use an HTTP-only refresh-token cookie.

### PaperMind agent

| Endpoint | Purpose |
| --- | --- |
| `GET /health/live` | Liveness check. |
| `GET /health/ready` | Readiness check. |
| `GET /v1/runtime` | Runtime configuration summary. |
| `POST /v1/process` | Upload and process a PDF. |
| `POST /v1/process-path` | Process a PDF from an approved mounted path. |
| `GET /v1/documents/{document_id}` | Read generated document metadata. |
| `GET /v1/documents/{document_id}/download` | Download a generated document package. |

### Indexer

| Endpoint | Purpose |
| --- | --- |
| `GET /health/live` | Liveness check. |
| `GET /health/ready` | Storage and model readiness. |
| `POST /v1/indexing/jobs` | Start an indexing job for a mounted canonical package. |
| `GET /v1/indexing/jobs` | List recent jobs. |
| `GET /v1/indexing/jobs/{job_id}` | Read job state and output. |
| `POST /v1/embeddings/query` | Embed a search query. |

### Ingester

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Health check. |
| `POST /ingest` | Upload `chunks.json` or a ZIP and validate or index it. |
| `GET /docs` | FastAPI interactive documentation. |

## Testing

Run component checks from their own directories:

```bash
# Frontend
cd frontend && npm ci && npm run lint && npm exec tsc -- --noEmit && npm run build

# Backend syntax
cd backend-api && npm ci
find src -type f -name '*.js' -print0 | xargs -0 -n1 node --check

# Python services
cd indexer && python -m pip install -r requirements-dev.txt && pytest -q
cd ../ingester && python -m pip install -r requirements-dev.txt && pytest -q
cd ../paperMind/agent && python -m pip install -r requirements-dev.txt && pytest -q
cd ../tools/api && python -m pip install -r requirements-dev.txt && pytest -q
```

Validate Compose files from the repository root after creating local `.env` files:

```bash
docker compose config --quiet
```

## Continuous integration

`.github/workflows/ci.yml` runs on pushes, pull requests, and manual dispatches. It includes:

- Repository JSON, YAML, shell, and Compose validation.
- Protection against committed runtime `.env` files.
- Frontend dependency installation, ESLint, TypeScript, and production build.
- Backend dependency installation and JavaScript syntax checks.
- Ruff, formatting, compile, and pytest checks for all Python services.
- PostgreSQL 16 schema application and required-table verification.
- OpenSearch startup, template installation, test-index creation, and repository verification.
- Docker image builds for the frontend, backend, indexer, ingester, PaperMind agent, and PaperMind extraction API.
- A final required status job suitable for branch protection.

No production credentials are required by CI. Integration jobs use temporary local credentials and isolated service containers.

## Operations

### Common commands

```bash
# Start or update the stack
docker compose up -d --build

# Show service health
docker compose ps

# Follow logs
docker compose logs -f --tail=200

# Restart one service
docker compose restart api

# Stop containers without deleting volumes
docker compose down

# Stop containers and delete named volumes
docker compose down --volumes
```

Deleting volumes can permanently remove PostgreSQL, Redis, OpenSearch, model-cache, or application data. Back up persistent data first.

### OpenSearch host setting

OpenSearch may fail immediately with a bootstrap error when `vm.max_map_count` is too low:

```bash
sudo sysctl -w vm.max_map_count=262144
```

### Model startup

The first PaperMind and indexer startup can be slow because model images and model weights must be downloaded and initialized. Check service health and logs rather than repeatedly restarting containers.

### File permissions

The Python processing containers can run with configured host UID/GID values. Ensure mounted input directories are readable and output directories are writable by those IDs.

## Security notes

- Replace all example passwords, API keys, and JWT secrets before exposing the application.
- Keep PostgreSQL, Redis, OpenSearch, PaperMind, indexer, and ingester ports private unless external access is required.
- Use TLS at the public Nginx layer in production.
- Restrict `HOST_ACCESS_ROOT` to the smallest directory PaperMind needs. Do not mount `/` on an internet-accessible deployment.
- Keep `OPENSEARCH_TLS_REJECT_UNAUTHORIZED=true` when using a trusted TLS certificate.
- Use long random values for `JWT_SECRET`, `API_KEY`, and `INGESTOR_API_KEY`.
- Review upload limits and Nginx `client_max_body_size` together.
- Back up PostgreSQL and OpenSearch data regularly.

## Component documentation

Additional implementation details are available in:

- `paperMind/README.md`
- `paperMind/DEPLOYMENT.md`
- `indexer/README.md`
- `indexer/API.md`
- `indexer/DOCKER.md`
- `ingester/README.md`
- `postgreSQL/README.md`
- `frontend/README.md`

## Contributing

1. Create a feature branch.
2. Keep secrets and generated data out of Git.
3. Add or update tests for behavior changes.
4. Run the relevant component checks locally.
5. Open a pull request and wait for the repository-wide CI workflow to pass.

A root license file is not currently included. Add an explicit project license before distributing the repository publicly.
