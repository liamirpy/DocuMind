# Scientific PDF Extraction Stack

Production-oriented first-stage extraction for scientific articles using **Docling** and **GROBID**.

One HTTP request processes a PDF with both extractors in parallel and returns:

- Docling document JSON
- Docling Markdown
- Docling formulas with provenance
- Docling structured-table summaries and explicit failure flags
- Persisted figure crops as PNG
- Persisted table crops as PNG
- GROBID TEI XML
- Parsed GROBID metadata, sections, references, figures/tables, and formulas
- A conservative merged preview that does not hide parser disagreements

The repository supports two runtime modes from the same codebase:

- **CPU:** portable default; no GPU is required
- **NVIDIA GPU:** CUDA-accelerated Docling with a separate Compose override

> This service is the extraction layer. It intentionally does not perform the final canonical merge, quality scoring, agentic repair, chunking, embedding, or OpenSearch indexing. Those should consume this service's output as later pipeline stages.

---

## 1. Architecture

```text
                              PDF upload
                                   |
                                   v
                    FastAPI /v1/extract endpoint
                                   |
                  +----------------+----------------+
                  |                                 |
                  v                                 v
      Docling in extractor-api               GROBID REST service
      - layout and reading order              - scholarly metadata
      - OCR                                    - article sections
      - accurate table structure              - citations/references
      - formula enrichment                    - figure/table/formula TEI
      - figure/table image crops              - PDF coordinates
                  |                                 |
                  +----------------+----------------+
                                   |
                                   v
                         Combined JSON response
                                   |
                                   +--> persisted assets
                                        data/assets/<sha256>/
                                        ├── figures/*.png
                                        └── tables/*.png
```

Docling and GROBID outputs remain separately available. The `merged` field is deliberately conservative so that later quality checks can compare the parsers rather than losing information through an early merge.

---

## 2. Repository layout

```text
.
├── .github/workflows/
│   ├── ci.yml                  # lint, unit tests, Compose validation
│   ├── docker-build.yml        # CPU build on PR/main; optional GPU build
│   ├── publish.yml             # publish CPU/GPU images to GHCR on version tags
│   └── gpu-smoke.yml           # real GPU test on a self-hosted GPU runner
├── api/
│   ├── app/
│   │   ├── parsers/
│   │   │   ├── docling.py
│   │   │   └── tei.py
│   │   ├── services/
│   │   │   ├── docling_service.py
│   │   │   ├── grobid_service.py
│   │   │   └── merge_service.py
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── utils.py
│   ├── tests/
│   ├── Dockerfile              # parameterized CPU/GPU image
│   ├── docker-entrypoint.sh
│   ├── requirements-base.txt
│   ├── requirements-docling.txt
│   ├── requirements-dev.txt
│   └── pyproject.toml
├── data/assets/                # persisted figure/table PNGs; ignored by Git
├── scripts/
│   ├── check_gpu.sh
│   ├── smoke_test.sh
│   └── wait_for_url.py
├── tests/fixtures/
│   └── scientific_sample.pdf
├── .env.example
├── docker-compose.yml          # CPU/default stack
├── docker-compose.gpu.yml      # NVIDIA CUDA override
├── grobid.yaml
├── Makefile
└── README.md
```

---

## 3. What to install before using the project

### 3.1 Required on every machine

Recommended host:

- Linux x86_64
- 16 GB RAM or more
- 25–40 GB free disk space for Docker images and model caches
- Several CPU cores; accurate OCR/table/formula processing is compute-intensive

Install:

1. **Git**
2. **Docker Engine**
3. **Docker Compose v2 plugin**
4. `curl`, `jq`, and `make` for the documented commands

On Ubuntu/Debian, the small command-line tools can be installed with:

```bash
sudo apt-get update
sudo apt-get install -y git curl jq make
```

Install Docker Engine and the Compose plugin using Docker's official installation guide:

- https://docs.docker.com/engine/install/
- https://docs.docker.com/compose/install/linux/

Verify:

```bash
docker --version
docker compose version
```

You do **not** need to install Python, Docling, GROBID, Java, PyTorch, or the CUDA toolkit directly on the host. They are provided by the containers.

### 3.2 Additional requirements for NVIDIA GPU mode

GPU mode additionally requires:

1. A supported NVIDIA GPU
2. A working NVIDIA host driver
3. NVIDIA Container Toolkit configured for Docker

Verify the host driver:

```bash
nvidia-smi
```

Install NVIDIA Container Toolkit using NVIDIA's current official guide:

- https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

After installation, configure and restart Docker:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify container access:

```bash
docker run --rm --gpus all \
  nvidia/cuda:12.6.3-base-ubuntu24.04 \
  nvidia-smi
```

The repository uses the PyTorch **CUDA 12.6** wheel in GPU mode. This is intentional because it supports Pascal GPUs such as the GTX 1080 (`compute capability 6.1`) while also supporting newer architectures in the tested wheel. Do not switch this project to the CUDA 12.8 wheel on a GTX 1080; current CUDA 12.8 PyTorch builds may omit the required Pascal kernels.

---

## 4. First-time setup

Clone the repository:

```bash
git clone https://github.com/YOUR_ORG/YOUR_REPOSITORY.git
cd YOUR_REPOSITORY
```

Create the local environment file and runtime directories:

```bash
make init
```

Equivalent manual commands:

```bash
cp .env.example .env
mkdir -p data/assets output
```

### Important: update the GROBID contact email

Before public or production use, edit:

```text
grobid.yaml
```

Replace:

```yaml
mailto: "replace-with-your-email@example.com"
```

with a monitored contact email. This is used only if Crossref consolidation is enabled. The supplied configuration uses Glutton and the extraction endpoint defaults consolidation to `0`, so ordinary extraction does not require Glutton or Crossref.

---

## 5. Start in CPU mode

CPU mode is the portable default and works on a machine without an NVIDIA GPU.

Build and start:

```bash
make up-cpu
```

Equivalent Compose command:

```bash
docker compose \
  -f docker-compose.yml \
  up -d --build
```

Follow logs:

```bash
docker compose logs -f --tail=200
```

The first startup can take several minutes because:

- the full GROBID image is large
- GROBID preloads models according to `grobid.yaml`
- Docling/RapidOCR/Hugging Face model files are downloaded into the persistent model cache

Check readiness:

```bash
curl -fsS http://localhost:8090/health/ready | jq
```

Expected:

```json
{
  "status": "ready",
  "grobid": true,
  "docling": true
}
```

Inspect runtime details:

```bash
curl -fsS http://localhost:8090/v1/runtime | jq
```

In CPU mode you should see approximately:

```json
{
  "docling": {
    "configured_device": "cpu",
    "ocr_backend": "onnxruntime",
    "cuda_available": false
  }
}
```

---

## 6. Start in NVIDIA GPU mode

First verify GPU access:

```bash
./scripts/check_gpu.sh
```

Build and start with both Compose files:

```bash
make up-gpu
```

Equivalent command:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  up -d --build
```

The GPU override changes only the Docling service:

```text
PyTorch wheel:        CUDA 12.6
Docling device:       cuda
RapidOCR backend:     torch
GROBID:               CPU
Accuracy settings:    unchanged
```

Verify CUDA inside the running extractor:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  exec -T extractor-api \
  python -c '
import torch
print({
    "torch": torch.__version__,
    "cuda_available": torch.cuda.is_available(),
    "cuda_version": torch.version.cuda,
    "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    "capability": torch.cuda.get_device_capability(0) if torch.cuda.is_available() else None,
    "compiled_architectures": torch.cuda.get_arch_list() if torch.cuda.is_available() else [],
})
'
```

For a GTX 1080, a healthy result looks similar to:

```json
{
  "torch": "2.11.0+cu126",
  "cuda_available": true,
  "cuda_version": "12.6",
  "gpu": "NVIDIA GeForce GTX 1080",
  "capability": [6, 1],
  "compiled_architectures": [
    "sm_50",
    "sm_60",
    "sm_70",
    "sm_75",
    "sm_80",
    "sm_86",
    "sm_90"
  ]
}
```

Monitor GPU use during extraction:

```bash
watch -n 1 nvidia-smi
```

### Switching between GPU and CPU

Stop with the same Compose definition used to start the stack:

```bash
make down-gpu
```

Then start CPU mode:

```bash
make up-cpu
```

The CPU and GPU extractor images have different local names, so both may remain cached.

---

## 7. Service URLs

Default local endpoints:

| Service | URL |
|---|---|
| Extraction API | `http://localhost:8090` |
| Swagger UI | `http://localhost:8090/docs` |
| OpenAPI JSON | `http://localhost:8090/openapi.json` |
| Liveness | `http://localhost:8090/health/live` |
| Readiness | `http://localhost:8090/health/ready` |
| Runtime/GPU diagnostics | `http://localhost:8090/v1/runtime` |
| GROBID API | `http://127.0.0.1:8086` |
| GROBID admin | `http://127.0.0.1:8085` |
| Extracted assets | `http://localhost:8090/assets/...` |

GROBID is bound to localhost by default. The extraction API is bound to all host interfaces by default; change `API_BIND_HOST` in `.env` if needed.

---

## 8. Process a PDF

Run:

```bash
curl --fail --show-error \
  -X POST "http://localhost:8090/v1/extract" \
  -H "accept: application/json" \
  -F "file=@./article.pdf;type=application/pdf" \
  -F "include_docling_markdown=true" \
  -F "include_docling_json=true" \
  -F "include_grobid_tei=true" \
  -F "export_picture_images=true" \
  -F "export_table_images=true" \
  -F "grobid_consolidate_header=0" \
  -F "grobid_consolidate_citations=0" \
  -o result.json
```

Pretty-print the result:

```bash
jq . result.json > result.pretty.json
```

or:

```bash
python -m json.tool result.json > result.pretty.json
```

For large JSON files, inspect only the useful sections:

```bash
jq '.docling.stats' result.json
jq '.docling.parsed.formulas' result.json
jq '.docling.parsed.tables' result.json
jq '.docling.parsed.quality_flags' result.json
jq '.grobid.stats' result.json
jq '.grobid.parsed.metadata' result.json
jq '.grobid.parsed.formulas' result.json
```

Run the included end-to-end smoke script:

```bash
make smoke
```

It uses `tests/fixtures/scientific_sample.pdf` and writes results to `output/`.

---

## 9. Output structure

Simplified response:

```json
{
  "schema_version": "0.2.0",
  "request_id": "...",
  "status": "completed",
  "document": {
    "filename": "article.pdf",
    "size_bytes": 123456,
    "sha256": "...",
    "asset_namespace": "..."
  },
  "docling": {
    "status": "completed",
    "version": "2.111.0",
    "stats": {
      "pages": 12,
      "tables": 4,
      "tables_structured": 3,
      "tables_empty_structure": 1,
      "pictures": 6,
      "formulas": 18,
      "exported_pictures": 6,
      "exported_tables": 4
    },
    "raw": {
      "document_json": {},
      "markdown": "...",
      "assets": {
        "pictures": [],
        "tables": []
      }
    },
    "parsed": {
      "formulas": [],
      "tables": [],
      "pictures": [],
      "quality_flags": []
    }
  },
  "grobid": {
    "status": "completed",
    "raw": {
      "tei_xml": "..."
    },
    "parsed": {
      "metadata": {},
      "sections": [],
      "references": [],
      "figures_and_tables": [],
      "formulas": []
    }
  },
  "merged": {
    "merge_status": "preview_only"
  },
  "warnings": []
}
```

### Partial success

If one parser fails but the other succeeds, the endpoint returns HTTP 200 with:

```json
{
  "status": "partial",
  "docling": {
    "status": "completed"
  },
  "grobid": {
    "status": "failed",
    "error": "..."
  }
}
```

If both fail, the endpoint returns HTTP 502.

---

## 10. Figure and table image persistence

Docling image generation and image saving are separate operations. This repository performs both.

The relevant defaults are:

```env
DOCLING_GENERATE_PAGE_IMAGES=true
DOCLING_GENERATE_PICTURE_IMAGES=true
DOCLING_IMAGES_SCALE=2.0
DOCLING_EXPORT_PICTURES=true
DOCLING_EXPORT_TABLES=true
```

Images are stored on the host:

```text
data/assets/<pdf-sha256>/
├── figures/
│   ├── figure_001.png
│   ├── figure_002.png
│   └── ...
└── tables/
    ├── table_001.png
    ├── table_002.png
    └── ...
```

The JSON contains relative HTTP URLs such as:

```json
{
  "relative_path": "<sha256>/figures/figure_001.png",
  "url": "/assets/<sha256>/figures/figure_001.png",
  "width": 1600,
  "height": 900,
  "size_bytes": 248123
}
```

Open locally:

```text
http://localhost:8090/assets/<sha256>/figures/figure_001.png
```

### Image quality

`DOCLING_IMAGES_SCALE=2.0` is the recommended starting point. Approximate behavior:

- `1.0`: smaller/faster; roughly standard PDF rendering scale
- `2.0`: good balance for charts, diagrams, and labels
- `3.0`: larger and slower; useful for very small labels
- `4.0`: high memory/storage cost; use only after measurement

Increasing scale enlarges vector/rendered content. It cannot recover detail missing from a low-resolution raster image embedded in the original PDF.

---

## 11. Formula output

Docling formulas are available under:

```text
docling.parsed.formulas
```

Each item contains:

- Docling ID
- enriched formula text
- original recognized text
- page/bounding-box provenance

Example:

```json
{
  "id": "#/texts/47",
  "text": "\\mathcal{L}=-\\sum_i y_i\\log(p_i)",
  "original": "L = - Σ yᵢ log(pᵢ)",
  "provenance": [
    {
      "page_no": 5,
      "bbox": {}
    }
  ]
}
```

GROBID formulas are available under:

```text
grobid.parsed.formulas
```

GROBID is useful for equation labels/numbers, TEI structure, and coordinates. Docling is generally more useful for enriched mathematical text. Final formula alignment belongs in the later canonical merge/quality stage.

---

## 12. Table output and early quality flags

Docling tables are available in full under:

```text
docling.raw.document_json.tables
```

A compact summary is available under:

```text
docling.parsed.tables
```

Example successful table:

```json
{
  "rows": 5,
  "columns": 4,
  "cell_count": 20,
  "structure_status": "structured"
}
```

A layout region can be detected as a table while structure reconstruction fails. This looks like:

```json
{
  "rows": 0,
  "columns": 0,
  "cell_count": 0,
  "structure_status": "empty_structure"
}
```

The service adds a quality flag:

```json
{
  "type": "table_empty_structure",
  "table_id": "#/tables/0",
  "index": 1,
  "provenance": []
}
```

This is not the final quality gate, but it is a useful deterministic signal for the next stage. Real PDFs vary greatly; some tables will reconstruct correctly and others will require a fallback or later agentic repair.

To experiment with cell matching:

```env
DOCLING_TABLE_DO_CELL_MATCHING=true
```

For a problematic PDF, try:

```env
DOCLING_TABLE_DO_CELL_MATCHING=false
```

Recreate the extractor and compare results. Do not assume one setting is universally best; evaluate against your PDF benchmark set.

---

## 13. Configuration reference

Edit `.env` rather than changing Compose files.

### API

| Variable | Default | Meaning |
|---|---:|---|
| `API_PORT` | `8090` | Host API port |
| `MAX_UPLOAD_SIZE_MB` | `100` | Maximum PDF upload size |
| `SERVE_ASSETS` | `true` | Serve persisted assets through FastAPI |
| `ASSETS_HOST_DIR` | `./data/assets` | Host asset directory |
| `ASSETS_URL_PREFIX` | `/assets` | URL prefix for assets |

### Docling

| Variable | Default | Meaning |
|---|---:|---|
| `DOCLING_PRELOAD_ON_STARTUP` | `true` | Load converter during startup |
| `DOCLING_MAX_NUM_PAGES` | `300` | Maximum processed pages |
| `DOCLING_MAX_CONCURRENCY` | `1` | Concurrent Docling conversions in one container |
| `DOCLING_DOCUMENT_TIMEOUT_SECONDS` | `1800` | Docling document timeout |
| `DOCLING_ACCELERATOR_DEVICE` | `cpu` | `cpu`, `auto`, `cuda`, or `cuda:N` |
| `DOCLING_ACCELERATOR_NUM_THREADS` | `4` | CPU inference threads |
| `DOCLING_OCR_BACKEND` | `onnxruntime` | `onnxruntime` or `torch` |
| `DOCLING_DO_OCR` | `true` | Enable OCR |
| `DOCLING_OCR_FORCE_FULL_PAGE` | `false` | OCR the entire page rather than selected bitmap regions |
| `DOCLING_OCR_BITMAP_AREA_THRESHOLD` | `0.05` | Bitmap-area threshold for OCR |
| `DOCLING_DO_TABLE_STRUCTURE` | `true` | Enable table structure recognition |
| `DOCLING_TABLE_MODE` | `accurate` | `accurate` or `fast` |
| `DOCLING_TABLE_DO_CELL_MATCHING` | `true` | Match predicted table structure to PDF cells |
| `DOCLING_DO_FORMULA_ENRICHMENT` | `true` | Enable formula enrichment |
| `DOCLING_GENERATE_PAGE_IMAGES` | `true` | Preserve page images for element crops |
| `DOCLING_GENERATE_PICTURE_IMAGES` | `true` | Generate picture images |
| `DOCLING_IMAGES_SCALE` | `2.0` | Render scale for page/element images |
| `DOCLING_EXPORT_PICTURES` | `true` | Save picture PNG files |
| `DOCLING_EXPORT_TABLES` | `true` | Save table PNG files |

### GROBID

| Variable | Default | Meaning |
|---|---:|---|
| `GROBID_PORT` | `8086` | Host GROBID service port |
| `GROBID_ADMIN_PORT` | `8085` | Host GROBID admin port |
| `GROBID_TIMEOUT_SECONDS` | `300` | Timeout per GROBID request |
| `GROBID_MAX_RETRIES` | `2` | Maximum request attempts |
| `GROBID_TEI_COORDINATES` | comma-separated list | TEI elements receiving PDF coordinates |

The `GROBID_TEI_COORDINATES` setting uses Pydantic Settings `NoDecode`, allowing a normal comma-separated environment value without a JSON parsing error.

---

## 14. Development without Docker

The application runtime is designed for Docker because Docling/PyTorch model dependencies are heavy. Unit tests and static checks are intentionally lightweight and do not require installing Docling.

Install Python 3.12 and create a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r api/requirements-dev.txt
```

Run tests:

```bash
cd api
pytest --cov=app --cov-report=term-missing
```

Run lint and formatting checks:

```bash
ruff check .
ruff format --check .
```

Auto-fix:

```bash
ruff check --fix .
ruff format .
```

Or use:

```bash
make test
make lint
make format
```

---

## 15. GitHub Actions CI/CD

The repository includes four workflows.

### `.github/workflows/ci.yml`

Runs on every pull request and push to `main`:

- installs lightweight dependencies
- Ruff lint
- Ruff formatting check
- unit tests with coverage
- Python bytecode compilation
- CPU and GPU Compose configuration validation

It intentionally does not download all Docling models or the large GROBID image.

### `.github/workflows/docker-build.yml`

- builds the CPU image on relevant pull requests and pushes to `main`
- optionally builds the CUDA 12.6 image when manually triggered
- uses GitHub Actions build cache

### `.github/workflows/publish.yml`

On tags matching `v*`, publishes two images to GitHub Container Registry:

```text
ghcr.io/<owner>/pdf-extractor-api:<version>-cpu
ghcr.io/<owner>/pdf-extractor-api:<version>-gpu-cu126
```

It also publishes moving variant tags:

```text
cpu
gpu-cu126
```

Repository Actions permissions must allow package writes. The workflow already requests:

```yaml
permissions:
  contents: read
  packages: write
```

### `.github/workflows/gpu-smoke.yml`

This is a real extraction test and therefore requires a **self-hosted GPU runner** with these labels:

```text
self-hosted
linux
x64
gpu
```

The workflow:

1. verifies `nvidia-smi`
2. verifies Docker GPU access
3. builds/starts the GPU stack
4. asserts `torch.cuda.is_available()`
5. processes `tests/fixtures/scientific_sample.pdf`
6. collects logs on failure
7. stops the stack

GitHub-hosted standard runners should not be used for this GPU workflow because the job requires direct NVIDIA GPU access and a large model cache.

---

## 16. Put the project on GitHub

Create an empty repository, then run:

```bash
git init
git add .
git commit -m "Initial scientific PDF extraction stack"
git branch -M main
git remote add origin git@github.com:YOUR_ORG/YOUR_REPOSITORY.git
git push -u origin main
```

Before making the repository public:

- confirm `.env` is not committed
- replace the placeholder GROBID email
- decide on a license and add a `LICENSE` file
- review `grobid.yaml` for organization-specific endpoints
- do not commit user PDFs or extracted assets

---

## 17. Production deployment guidance

The stack is production-oriented, but a real high-volume deployment should add infrastructure around it.

### Recommended before internet exposure

- Put the API behind a reverse proxy or API gateway.
- Add authentication and authorization.
- Add TLS.
- Set request-size and request-timeout limits at the proxy.
- Restrict or disable public asset serving if documents are sensitive.
- Do not expose GROBID publicly; keep it on the private Docker network.
- Add malware scanning and PDF security controls for untrusted uploads.

### Use asynchronous jobs for large workloads

The current endpoint is synchronous: the HTTP request remains open until both parsers finish. This is convenient for development and low throughput.

For production ingestion, prefer:

```text
POST /jobs
    -> store PDF
    -> enqueue extraction
    -> return job ID

worker
    -> Docling + GROBID
    -> persist JSON/assets
    -> update status

GET /jobs/<id>
    -> status/result
```

Use a queue such as Redis/RQ, Celery, RabbitMQ, Kafka, or your existing job system.

### Model memory and scaling

The API intentionally starts one Uvicorn worker:

```text
--workers 1
```

Every worker would load another copy of Docling/PyTorch models. To scale throughput:

- keep one worker per container
- run multiple extractor containers
- assign one GPU or controlled GPU share per container
- keep `DOCLING_MAX_CONCURRENCY=1` until memory and throughput are measured

### Storage

The local bind mount is suitable for development and a single node. For production:

- store original PDFs in object storage
- store figure/table images in object storage
- store extraction JSON in object storage or a document database
- store only URLs, hashes, metadata, chunks, and vectors in OpenSearch
- implement retention and deletion policies

### Observability

Add:

- structured JSON logging
- request/job correlation IDs
- Prometheus metrics
- extraction durations by parser
- failure counts by stage
- GPU memory/utilization monitoring
- model version/configuration metadata in every result

### Deduplication

The API calculates SHA-256 while streaming the upload. The same hash is used as the asset namespace. Use that hash as a stable document identity and deduplication key in the ingestion layer.

---

## 18. GROBID consolidation and Glutton

The supplied `grobid.yaml` points Glutton to:

```text
http://host.docker.internal:8080
```

Normal extraction sends:

```text
consolidateHeader=0
consolidateCitations=0
```

Therefore Glutton is not required for the normal path.

Only enable consolidation when Glutton is running and reachable:

```bash
-F "grobid_consolidate_header=1" \
-F "grobid_consolidate_citations=1"
```

External consolidation can increase latency and introduces an external dependency. Keep it disabled in deterministic extraction benchmarks unless the benchmark explicitly includes consolidation.

---

## 19. Troubleshooting

### `could not select device driver "nvidia"`

Cause: Docker cannot access the NVIDIA runtime.

Check:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
```

Install/configure NVIDIA Container Toolkit, then restart Docker.

### `no kernel image is available for execution on the device`

Cause: the PyTorch wheel does not include kernels compatible with the GPU architecture.

For a GTX 1080 (`CC 6.1`), use this repository's CUDA 12.6 build. Verify:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  exec -T extractor-api \
  python -c 'import torch; print(torch.__version__, torch.version.cuda, torch.cuda.get_arch_list())'
```

You should see `+cu126` and an architecture list that includes the Pascal major family (`sm_60`).

### RapidOCR permission denied in `site-packages/rapidocr/models`

The Dockerfile makes the RapidOCR model directory writable by the non-root application user. The entrypoint also fixes mounted asset/model directory ownership.

If migrating an old root-owned model volume, remove it and allow the repository to create a fresh one:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.gpu.yml \
  down -v
```

Then rebuild/start.

### Pydantic `grobid_tei_coordinates` JSON decoding error

This repository uses `NoDecode` and a comma-splitting validator. Keep the environment value as:

```env
GROBID_TEI_COORDINATES=persName,figure,ref,biblStruct,formula,s,p,title,affiliation,note
```

### Images are detected but no PNG files appear

Check:

```bash
curl -fsS http://localhost:8090/v1/runtime | jq
find data/assets -type f -name '*.png'
```

Confirm:

```env
DOCLING_GENERATE_PAGE_IMAGES=true
DOCLING_GENERATE_PICTURE_IMAGES=true
DOCLING_EXPORT_PICTURES=true
DOCLING_EXPORT_TABLES=true
```

The code must call `PictureItem.get_image()` / `TableItem.get_image()` and save the returned images. This repository does that in `api/app/services/docling_service.py`.

### Exported images are too small

Increase:

```env
DOCLING_IMAGES_SCALE=3.0
```

Then recreate the extractor. Higher values increase runtime, memory use, and storage.

### Table object has zero rows, columns, and cells

This means the layout stage detected a table region but the structure stage did not reconstruct a usable grid.

Inspect:

```bash
jq '.docling.parsed.tables' result.json
jq '.docling.parsed.quality_flags' result.json
```

Try changing:

```env
DOCLING_TABLE_DO_CELL_MATCHING=false
```

and compare results. Keep this as a quality-gate failure for later specialized fallback/agentic repair.

### Extraction takes a long time

Accurate table mode, OCR, formula enrichment, and image rendering are all enabled. First-run model downloads are also slow.

Inspect:

```bash
docker stats
curl -fsS http://localhost:8090/v1/runtime | jq
```

GPU mode should show a Python process and utilization in:

```bash
watch -n 1 nvidia-smi
```

Do not increase Uvicorn workers to improve speed; that duplicates model memory. Scale containers after benchmarking.

### Old container-name conflicts

This repository does not set `container_name`, so independent Compose projects do not compete for global fixed names. If old manually named containers remain from a previous prototype:

```bash
docker ps -a
docker rm -f grobid pdf-extractor-api
```

### Compose warns that `version` is obsolete

This repository does not include the legacy top-level `version:` key.

---

## 20. Upgrade procedure

Do not update Docling, PyTorch, CUDA wheels, FastAPI, or GROBID blindly in production.

Recommended process:

1. Create a branch.
2. Update one dependency family at a time.
3. Build CPU and GPU images.
4. Run unit tests.
5. Run the GPU smoke workflow.
6. Process your manually reviewed benchmark PDF set.
7. Compare:
   - page/text counts
   - table rows/columns/cells
   - formula outputs
   - figure/table crops
   - extraction time
   - GPU memory
8. Record the new parser/model versions.
9. Deploy to staging before production.

Your benchmark should include simple born-digital articles, two-column layouts, scanned pages, complex/multi-page tables, equations, charts, diagrams, and low-quality PDFs.

---

## 21. Next pipeline stage

The next service should consume this response and generate a quality report with:

- technical validity
- text completeness
- reading-order checks
- Docling/GROBID section agreement
- metadata agreement
- table structure validity
- formula presence/syntax/context checks
- figure-caption relationships
- page/bounding-box provenance checks
- Green / Yellow / Red routing

Only uncertain pages or elements should be sent to specialized fallback tools or an agentic repair workflow.

After quality control:

```text
canonical document
    -> structure-aware chunks
    -> embeddings
    -> OpenSearch BM25 + vector fields
    -> hybrid retrieval
    -> reranking
    -> grounded RAG
```

---

## 22. Useful commands

```bash
# Initialize local files/directories
make init

# CPU
make up-cpu
make down

# GPU
make up-gpu
make down-gpu

# Logs/status
make logs
make ps
make ready
make runtime

# Local lightweight checks
make test
make lint
make format

# End-to-end smoke test against a running stack
make smoke

# Remove containers, volumes, model cache, and local output
make clean
```

