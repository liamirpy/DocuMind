# PaperMind

## Start Docker once and process PDFs by filesystem path

The Agent now provides two APIs:

- `POST /v1/process` uploads a PDF through HTTP.
- `POST /v1/process-path` reads an existing PDF from a mounted directory and writes the result to a selected mounted directory.

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
