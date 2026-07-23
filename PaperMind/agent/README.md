# PDF Canonicalization Agent

This service is the second stage of the `pdf-analyser` pipeline. It does **not** parse PDFs directly as its primary path. Instead, it:

1. receives a PDF;
2. sends the PDF to the existing `tools` extraction API;
3. receives Docling JSON/Markdown, GROBID TEI-derived JSON, and exported figure/table assets;
4. deterministically aligns and merges the two parser views;
5. runs quality checks per document and per element;
6. optionally uses a bounded local Llama vision model through Ollama to repair difficult tables/formulas and generate grounded descriptions for every available figure, table, and formula image;
7. writes one canonical JSON file plus all derived assets into a self-contained output folder;
8. optionally creates a ZIP archive of that folder.

The deterministic pipeline works without an LLM. Llama is an optional fallback, not the source of truth.

## Architecture

```text
PDF
 │
 ▼
Agent API :8100
 │
 ├── POST PDF to Tools API :8090
 │      ├── Docling
 │      │    ├── text/layout
 │      │    ├── structured tables
 │      │    ├── formulas
 │      │    └── figure/table images
 │      └── GROBID
 │           ├── metadata
 │           ├── sections
 │           ├── references
 │           ├── equation numbers
 │           └── figure/table labels and captions
 │
 ├── deterministic alignment and merge
 ├── quality gate
 ├── optional Ollama/Llama vision fallback
 ├── formula crops from the original PDF
 └── canonical package
```

## Output package

Each document is identified by its SHA-256 hash:

```text
data/outputs/
├── <sha256>/
│   ├── canonical_document.json       # the single canonical JSON file
│   ├── source/
│   │   └── original.pdf
│   ├── text/
│   │   ├── full_text.txt
│   │   └── full_text.md
│   ├── figures/
│   │   ├── figure_001.png
│   │   ├── figure_001.caption.txt
│   │   ├── figure_001.description.txt      # when Llama is enabled
│   │   ├── figure_001.description.json     # grounded structured description
│   │   └── ...
│   ├── tables/
│   │   ├── table_001.png
│   │   ├── table_001.caption.txt
│   │   ├── table_001.csv
│   │   ├── table_001.md
│   │   ├── table_001.html
│   │   ├── table_001.tex
│   │   ├── table_001.description.txt       # when Llama is enabled
│   │   ├── table_001.description.json
│   │   └── ...
│   ├── formulas/
│   │   ├── formula_001.png
│   │   ├── formula_001.txt
│   │   ├── formula_001.tex
│   │   ├── formula_001.description.txt     # when Llama is enabled
│   │   ├── formula_001.description.json
│   │   └── ...
│   └── latex/
│       ├── formulas.tex
│       ├── tables.tex
│       └── document_assets.tex
└── <sha256>.zip
```

`canonical_document.json` contains:

- document identity and source PDF path;
- title, authors, abstract, DOI, journal, date, and language from GROBID when available;
- Docling text blocks with page/bounding-box provenance and section links;
- a canonical article hierarchy with sections, subsections, parent IDs, levels, paths, child IDs, and section-linked paragraphs;
- a nested `section_tree` representation in addition to the flat section list;
- references from GROBID;
- figures with local image paths, captions, labels, section paths, alignment confidence, optional Llama descriptions, and both parser sources;
- tables with local images, columns, rows, inline LaTeX, CSV/Markdown/HTML/LaTeX paths, section paths, quality status, optional Llama repair/description evidence, and both parser sources;
- formulas with local image crops, LaTeX, plain text, equation numbers, section paths, parser candidates, optional Llama transcription/description evidence, and both parser sources;
- a document quality report;
- parser versions, counts, status, and LLM provenance.

## Canonical section hierarchy

The canonical JSON schema is `1.2.0`. A scientific article is represented both as a flat relational list and as a recursive tree:

```json
{
  "content": {
    "sections": [
      {
        "id": "sec_001",
        "title": "Methods",
        "number": "2",
        "level": 1,
        "parent_id": null,
        "path": ["Methods"],
        "child_section_ids": ["sec_002"],
        "paragraph_ids": ["para_00001"],
        "figure_ids": [],
        "table_ids": [],
        "formula_ids": []
      },
      {
        "id": "sec_002",
        "title": "Dataset",
        "number": "2.1",
        "level": 2,
        "parent_id": "sec_001",
        "path": ["Methods", "Dataset"],
        "child_section_ids": [],
        "paragraph_ids": ["para_00002"],
        "figure_ids": ["figure_001"],
        "table_ids": ["table_001"],
        "formula_ids": ["formula_001"]
      }
    ],
    "section_tree": [
      {
        "id": "sec_001",
        "title": "Methods",
        "children": [
          {
            "id": "sec_002",
            "title": "Dataset",
            "children": []
          }
        ]
      }
    ],
    "paragraphs": [
      {
        "id": "para_00002",
        "section_id": "sec_002",
        "section_path": ["Methods", "Dataset"],
        "text": "The dataset contains ..."
      }
    ]
  }
}
```

Figures, tables, formulas, and matched Docling text blocks also receive `section_id`, `section_title`, and `section_path`.

## Prerequisites

### Required

Install these before starting the agent:

- Linux, macOS, or Windows with a current Docker installation;
- Docker Engine or Docker Desktop;
- Docker Compose v2 (`docker compose`, not the old `docker-compose` command);
- the `tools` service running and reachable on port `8090`;
- `curl` and `jq` for the command-line examples.

Recommended host resources for the full tools + agent stack:

- 8 CPU cores or more;
- 16 GB RAM minimum, 32 GB preferred for larger scientific PDFs;
- enough disk space for Docling/GROBID models and generated assets.

The agent itself does not require a GPU. GPU requirements belong to Docling in `../tools` and to the optional Ollama server.

### Optional: Ollama and Llama vision

The agent supports the Ollama REST API. On Linux, install Ollama:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Start or verify the service:

```bash
sudo systemctl enable --now ollama
curl http://localhost:11434/api/tags | jq
```

Pull the default model:

```bash
ollama pull llama3.2-vision:11b
```

Then set in `.env`:

```dotenv
LLM_ENABLED=true
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2-vision:11b
```

Important for an 8 GB GTX 1080: Llama 3.2 Vision 11B is a large model. Docling GPU inference and Ollama may not fit in VRAM at the same time. Practical options are:

- keep the LLM disabled during normal extraction;
- run Ollama on another machine/GPU;
- run Docling on CPU and reserve the GPU for Ollama;
- use a remote Ollama-compatible endpoint;
- accept CPU offload and slower LLM repair.

The LLM is called only when requested with `use_llm=true`, when `LLM_ENABLED=true`, and while the per-document item budget has not been exceeded.

## Upgrade from Agent 0.1

The `make init` command does not overwrite an existing `.env`. If you already have `agent/.env`, add or update these values manually:

```dotenv
APP_VERSION=0.3.0
LLM_DESCRIBE_ALL_ELEMENTS=true
LLM_MAX_ITEMS_PER_DOCUMENT=500
```

Then rebuild the Agent container:

```bash
cd agent
docker compose up -d --build --force-recreate
```

The canonical JSON schema is now `1.2.0`. Existing packages remain readable; newly processed PDFs also include output-folder metadata while retaining `content.paragraphs`, `content.section_tree`, hierarchical section fields, section links on visual elements, and optional vision-model description assets.

## Quick start

### 1. Start the tools service first

From the repository root:

CPU:

```bash
make tools-up-cpu
```

GPU:

```bash
make tools-up-gpu
```

Verify:

```bash
curl -fsS http://localhost:8090/health/ready | jq
```

### 2. Start the agent

```bash
cd agent
cp -n .env.example .env
mkdir -p data/outputs
docker compose up -d --build
```

Or from the repository root:

```bash
make agent-up
```

Verify:

```bash
curl -fsS http://localhost:8100/health/ready | jq
```

Expected:

```json
{
  "status": "ready",
  "tools_ready": true,
  "llm_enabled": false,
  "llm_alive": null,
  "ready": true
}
```

## Process a PDF

Without Llama:

```bash
curl --fail --show-error \
  -X POST http://localhost:8100/v1/process \
  -F "file=@/absolute/path/article.pdf;type=application/pdf" \
  -F "use_llm=false" \
  -o agent-result.json

jq . agent-result.json
```

With the configured Llama/Ollama fallback:

```bash
curl --fail --show-error \
  -X POST http://localhost:8100/v1/process \
  -F "file=@/absolute/path/article.pdf;type=application/pdf" \
  -F "use_llm=true" \
  -o agent-result.json
```

The response includes:

- document ID;
- output folder path;
- canonical JSON path;
- ZIP path;
- package URLs;
- quality status and score;
- element counts;
- warnings;
- extraction and canonicalization timings.

Example:

```json
{
  "status": "completed_with_warnings",
  "document_id": "...sha256...",
  "package_directory": "/data/outputs/...sha256...",
  "canonical_json": "/data/outputs/.../canonical_document.json",
  "zip_file": "/data/outputs/...sha256....zip",
  "quality": {
    "status": "yellow",
    "score": 0.85
  }
}
```

## Download and inspect results

Get the canonical JSON:

```bash
curl -o canonical_document.json \
  http://localhost:8100/v1/documents/<sha256>
```

Download the complete ZIP:

```bash
curl -OJ \
  http://localhost:8100/v1/documents/<sha256>/download
```

Direct static package paths are available under:

```text
http://localhost:8100/packages/<sha256>/
```

## Run from Python without Docker

The tools service still needs to be running.

```bash
cd agent
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.example .env
```

Set the tools URL for a host process:

```bash
export TOOLS_BASE_URL=http://localhost:8090
export OUTPUT_DIR="$PWD/data/outputs"
```

Run the CLI:

```bash
python -m app.cli /path/to/article.pdf
```

With Llama:

```bash
export LLM_ENABLED=true
export OLLAMA_BASE_URL=http://localhost:11434
python -m app.cli /path/to/article.pdf --use-llm
```

## Merge strategy

The first version intentionally uses a conservative merge:

### Metadata

- GROBID is primary for title, authors, abstract, DOI, journal, publication date, and language.
- Docling identity is retained as source metadata.

### Text and article hierarchy

- Docling is primary for ordered text blocks and page/bounding-box provenance.
- The agent parses the raw GROBID TEI and preserves nested `<div>` structure rather than flattening it.
- Every canonical section includes `level`, `parent_id`, `path`, `child_section_ids`, `paragraph_ids`, page range, and linked figure/table/formula IDs.
- Every canonical paragraph includes `section_id` and `section_path`.
- Docling text blocks are matched to GROBID paragraphs/headings and receive the same section links when possible.
- A nested `section_tree` is generated for consumers that prefer recursive traversal.
- If raw TEI is unavailable, the agent falls back to the flat GROBID section list and infers subsection levels from section numbers such as `2.1` and `2.1.3`.
- The full Docling Markdown is exported as `text/full_text.md`.

### Figures

- Docling supplies image assets and PDF provenance.
- GROBID supplies figure labels/captions when available.
- Elements are matched using caption similarity, page agreement, and order.
- Each figure is linked to the nearest/exact GROBID section and receives `section_id`, `section_title`, and `section_path`.
- When Llama is enabled and `LLM_DESCRIBE_ALL_ELEMENTS=true`, every available figure image receives a grounded structured description.
- Llama descriptions are stored as derived data and never replace the original caption.

### Tables

- Docling TableFormer is primary for cells, rows, and columns.
- GROBID supplies table labels/captions and coordinates.
- Every table is linked to its article section when a reliable link can be established.
- Empty Docling table structures are quality failures.
- If Llama is enabled, empty tables can be transcribed into strict columns/rows JSON.
- With `LLM_DESCRIBE_ALL_ELEMENTS=true`, every available table image also receives a grounded description and summary. The repair call itself supplies the description when a repair is required.
- Llama output is marked as derived evidence; it never erases parser evidence.

### Formulas

- Docling is primary for enriched formula text/LaTeX and PDF provenance.
- GROBID supplies equation numbering and another text candidate.
- Every formula is linked to its article section when possible.
- The agent crops a high-resolution formula image directly from the original PDF using Docling coordinates.
- Optional Llama transcription is used when the parser result is empty or clearly malformed.
- With `LLM_DESCRIBE_ALL_ELEMENTS=true`, every available formula image receives a grounded structural description even when the parser LaTeX is already accepted.

## Quality gate

The quality report is embedded in `canonical_document.json`:

```json
{
  "quality": {
    "status": "green",
    "score": 0.95,
    "issues": []
  }
}
```

Current checks include:

- Docling/GROBID completion;
- required metadata presence;
- text presence;
- missing or invalid section hierarchy;
- unresolved element-to-section links;
- empty table structures;
- missing formula LaTeX;
- missing formula/figure image assets;
- parser count disagreements.

Status thresholds:

```dotenv
QUALITY_GREEN_THRESHOLD=0.90
QUALITY_YELLOW_THRESHOLD=0.65
```

These rules are deliberately transparent. Before production indexing, calibrate them against a manually reviewed set of your own PDFs.

## LLM safety and reproducibility

The LLM is bounded by these rules:

- disabled by default;
- explicitly requested per document;
- maximum model calls per document;
- optional descriptions for every figure, table, and formula image;
- temperature defaults to zero;
- Ollama structured JSON schemas are used;
- parser output is always retained;
- LLM output is labeled as derived evidence;
- LLM table values are not accepted silently—the quality record identifies repairs and warnings;
- no unrestricted autonomous loop is used.

## Configuration reference

Important variables:

| Variable | Default | Purpose |
|---|---:|---|
| `TOOLS_BASE_URL` | `http://host.docker.internal:8090` | Existing extraction API |
| `TOOLS_TIMEOUT_SECONDS` | `1800` | Maximum tools request time |
| `OUTPUT_HOST_DIR` | `./data/outputs` | Host output directory |
| `FORMULA_CROP_SCALE` | `3.0` | Formula crop rendering scale |
| `LLM_ENABLED` | `false` | Enables Ollama calls in the service |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.2-vision:11b` | Vision model |
| `LLM_DESCRIBE_ALL_ELEMENTS` | `true` | Describe every available figure, table, and formula image when Llama is used |
| `LLM_MAX_ITEMS_PER_DOCUMENT` | `500` | Hard LLM call budget; reduce this to cap cost/latency |
| `KEEP_RAW_EXTRACTOR_RESPONSE` | `false` | Save raw tools response for debugging |
| `CREATE_ZIP_PACKAGE` | `true` | Create downloadable ZIP |

See `.env.example` for the complete list.

## Tests

Local:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
make check
```

The tests cover:

- nested GROBID TEI section/subsection hierarchy;
- flat-section fallback and inferred subsection levels;
- paragraph, text-block, figure, table, and formula section links;
- Llama descriptions and description asset files for all visual element types;
- Docling reference resolution;
- table matrix reconstruction;
- Markdown/LaTeX generation;
- parser element matching;
- coordinate conversion and formula cropping;
- quality rules;
- settings defaults.

## Production notes

Before production deployment:

1. Put the tools and agent APIs behind a reverse proxy with TLS.
2. Add authentication and request authorization; these services currently trust callers on the network.
3. Use object storage for long-term assets instead of a local bind mount.
4. Add retention/cleanup rules for output packages.
5. Run one agent worker per writable output volume, or move package generation to a shared object store with distributed locking.
6. Keep `MAX_CONCURRENCY=1` initially because one request can trigger expensive PDF processing and optional vision inference.
7. Add metrics for parser duration, LLM calls, quality status, failures, and output size.
8. Scan uploaded PDFs and enforce upload limits.
9. Do not expose GROBID admin ports publicly.
10. Keep raw parser outputs during evaluation, even if disabled later in production.

For OpenSearch RAG, index from `canonical_document.json`, not directly from Docling or GROBID. Create separate chunk records for narrative text, tables, formulas, and figures while retaining `document_id`, page, bounding box, element ID, and asset path.

## Troubleshooting

### Agent is not ready

```bash
docker compose logs -f agent-api
curl http://localhost:8090/health/ready | jq
```

The agent is considered ready when the tools service is ready. The LLM is optional.

### Agent container cannot reach tools on Linux

The Compose file includes:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Confirm tools binds to `0.0.0.0:8090`, not only `127.0.0.1`.

### Figure/table download fails

Confirm tools serves assets:

```bash
curl -I http://localhost:8090/assets/<sha256>/figures/figure_001.png
```

The agent falls back to a PDF provenance crop when an asset cannot be downloaded.

### Formula image is cropped incorrectly

Inspect the formula provenance in `canonical_document.json`. The cropper converts Docling `BOTTOMLEFT` coordinates to PyMuPDF page coordinates. Increase:

```dotenv
FORMULA_CROP_PADDING_POINTS=12
FORMULA_CROP_SCALE=4.0
```

### Empty table structure

The canonical table will show:

```json
{
  "data_source": "none",
  "quality": {
    "status": "failed"
  }
}
```

Enable Ollama only after reviewing the exported table image. Llama repair is a fallback, not guaranteed ground truth.

### Ollama unavailable

```bash
curl http://localhost:11434/api/tags | jq
ollama list
ollama pull llama3.2-vision:11b
```

The document still completes without LLM enrichment and records a warning.

## Custom output root and package folder names

The standalone Agent Compose file uses `OUTPUT_HOST_DIR` for the host parent directory. The root all-in-one Compose stack uses `OUTPUT_DIR`.

Each `/v1/process` request can also provide a safe package folder name:

```bash
curl \
  --fail \
  --show-error \
  -X POST \
  http://localhost:8100/v1/process \
  -F "file=@/absolute/path/article.pdf;type=application/pdf" \
  -F "use_llm=true" \
  -F "output_folder=article_run_001" \
  -F "overwrite=false" \
  -o agent-result.json
```

The Agent writes the package to:

```text
<configured-output-root>/article_run_001/
```

and writes the ZIP to:

```text
<configured-output-root>/article_run_001.zip
```

The output folder is strictly a single name. Path separators and traversal values are rejected. If a package already exists, the request returns HTTP 409 unless `overwrite=true` is supplied.
