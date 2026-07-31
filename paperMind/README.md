# PaperMind

## Start Docker once and process PDFs by filesystem path

The Agent provides synchronous APIs for short documents and asynchronous job APIs for long documents:

- `POST /v1/process` uploads and processes a PDF synchronously.
- `POST /v1/process-path` processes a mounted PDF synchronously.
- `POST /v1/process-async` uploads a PDF and immediately returns a job ID.
- `POST /v1/process-path-async` queues a mounted PDF and immediately returns a job ID.
- `GET /v1/jobs/{job_id}` reports queued, running, completed, or failed status.

Docker cannot see arbitrary host paths unless they are bind-mounted. Configure one host root once in `.env`:

```dotenv
# Recommended: expose only the common parent directory you need.
HOST_ACCESS_ROOT=/srv/DocuMind

# For a trusted, local-only Linux deployment that must reach the whole host:
# HOST_ACCESS_ROOT=/

PATH_API_ENABLED=true
ALLOWED_INPUT_DIRECTORIES=/host
ALLOWED_OUTPUT_DIRECTORIES=/data/outputs,/data/custom-output,/host
HOST_UID=1000
HOST_GID=1000
```

`HOST_ACCESS_ROOT` is mounted inside the Agent container at `/host`.

Examples:

| Host path | API/container path when `HOST_ACCESS_ROOT=/srv/DocuMind` |
| --- | --- |
| `/srv/DocuMind/pdf_example` | `/host/pdf_example` |
| `/srv/DocuMind/results` | `/host/results` |

Start the stack once:

```bash
docker compose up -d --build
```

For long PDFs, use the asynchronous path endpoint so the client or reverse proxy does not need to keep one request open during OCR, extraction, packaging, and LLM work:

```bash
curl \
  --fail \
  --show-error \
  -X POST \
  "http://127.0.0.1:5000/v1/process-path-async" \
  -H "Content-Type: application/json" \
  -d '{
    "input_directory": "/host/pdf_example",
    "input_filename": "RAX_NET.pdf",
    "output_directory": "/host/pdf_analyser_output",
    "output_folder": "Results_with_LLM",
    "use_llm": true,
    "overwrite": false
  }'
```

Poll the returned `status_url`, or call `GET /v1/jobs/<job-id>`. Use the synchronous command below only when the whole operation is expected to finish within the caller's timeout.

Large-file limits are independent of request timeouts. Increase `MAX_UPLOAD_SIZE_MB`
for PDFs above the configured byte limit, and increase `DOCLING_MAX_NUM_PAGES` for
documents above the configured page limit. Keep `TOOLS_TIMEOUT_SECONDS` greater
than the Docling/GROBID timeout plus asset-export overhead.

Then process any PDF below the mounted root without restarting Docker:

```bash
curl \
  --fail \
  --show-error \
  -X POST \
  "http://127.0.0.1:5000/v1/process-path" \
  -H "Content-Type: application/json" \
  -d '{
    "input_directory": "/host/pdf_example",
    "input_filename": "RAX_NET.pdf",
    "output_directory": "/host/pdf_analyser_output",
    "output_folder": "Results_with_LLM",
    "use_llm": true,
    "overwrite": false
  }' \
  -o agent-result.json
```

The result is written on the host to:

```text
/srv/DocuMind/pdf_analyser_output/Results_with_LLM/
```

When `HOST_ACCESS_ROOT=/`, prepend `/host` to the normal Linux host path. For example, host path `/mnt/papers` is `/host/mnt/papers` in the API request.

The container runs with `HOST_UID` and `HOST_GID`, so it can read and write only where that host user has permission. Keep the API bound to `127.0.0.1` when mounting broad host paths.

## Existing upload API

The upload API remains available:

```bash
curl \
  --fail \
  --show-error \
  -X POST \
  "http://127.0.0.1:5000/v1/process" \
  -F "file=@/srv/DocuMind/pdf_example/RAX_NET.pdf;type=application/pdf" \
  -F "use_llm=true" \
  -F "output_folder=Results_with_LLM" \
  -F "overwrite=false" \
  -o agent-result.json
```

## Install

```bash
bash ./scripts/install-nvidia.sh
```

## Load-balanced backend-managed asynchronous jobs

The `/v1/process-path-async` endpoint now accepts `backend_job_id`. PaperMind
executes the job in the selected replica and sends authenticated lifecycle
callbacks to the DocuMind backend. The backend stores status in shared Redis and
its BullMQ worker polls Redis instead of PaperMind `/v1/jobs/{job_id}`.

This permits multiple `agent-api` replicas behind Nginx without sticky sessions:

```bash
docker compose up -d --scale agent-api=3
```

Configure:

```dotenv
BACKEND_CALLBACK_BASE_URL=http://api:3000/internal/papermind/jobs
PAPERMIND_CALLBACK_TOKEN=replace-with-a-long-random-secret
BACKEND_CALLBACK_TIMEOUT_SECONDS=10
BACKEND_CALLBACK_MAX_RETRIES=5
```

The same callback token must be configured in `backend-api/.env`. See
`BACKEND_MANAGED_JOBS.md` and the accompanying backend integration package.
