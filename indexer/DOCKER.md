# Docker deployment

This package is designed so normal startup is only:

```bash
docker compose up --build -d
```

The PDF extraction package is external. This service only reads its generated output directory.

## Why this version avoids the previous permission failures

Docker Compose starts a one-shot `init-permissions` service before the API. It:

- creates the host-mounted output directory structure;
- creates `/data/output/.jobs`;
- initializes the Docker-managed Hugging Face cache volume;
- assigns both writable locations to `APP_UID:APP_GID`;
- exits successfully before `indexer-api` starts.

The API then performs real write probes during startup. If a mount is still unusable, the
container fails immediately with a clear storage error instead of accepting a job and failing
later during model download or job-state persistence.

## Initial configuration

The included `.env` works for the directory layout used in the examples:

```dotenv
DOCUMIND_INPUT_ROOT_HOST=/srv/DocuMind
DOCUMIND_OUTPUT_ROOT_HOST=/srv/DocuMind/indexer-output
APP_UID=1000
APP_GID=1000
```

On Linux, check your IDs once:

```bash
id -u
id -g
```

Change `APP_UID` and `APP_GID` only when those values are not `1000`.

The model cache is a Docker named volume:

```dotenv
HF_CACHE_VOLUME_NAME=documind-huggingface-cache
```

No host model-cache directory and no manual `chown` are required.

## Start

```bash
docker compose up --build -d
```

Check services:

```bash
docker compose ps -a
```

Expected state:

```text
init-permissions   Exited (0)
indexer-api        Up (healthy)
```

Check readiness:

```bash
curl http://localhost:8000/health/ready
```

Open API documentation:

```text
http://localhost:8000/docs
```

## Submit a job

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

## Normal operations

Start:

```bash
docker compose up -d
```

Stop without deleting the model cache:

```bash
docker compose down
```

Rebuild after code changes:

```bash
docker compose up --build -d
```

Follow logs:

```bash
docker compose logs -f indexer-api
```

Inspect initialization:

```bash
docker compose logs init-permissions
```

Do **not** normally run:

```bash
docker compose down -v
```

The `-v` option deletes the named Hugging Face cache volume and causes the embedding model to
be downloaded again.

## SELinux hosts

On Fedora/RHEL with SELinux enforcing, bind mounts may require relabeling. Add `selinux: Z` to
the input/output bind mounts in the long Compose syntax if the host denies the mounts even after
the initialization service succeeds. This is not needed on ordinary Ubuntu/Debian Docker hosts.
