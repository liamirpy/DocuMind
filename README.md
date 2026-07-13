# DocuMind
A general-purpose AI document assistant built with RAG. Users can upload files, organize them into folders, and ask questions based on all documents, selected folders, or specific files.



pdf/
├── agent/
├── tools/
│
├── indexer/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models.py
│   │
│   │   ├── canonical/
│   │   │   ├── reader.py
│   │   │   └── validator.py
│   │
│   │   ├── chunking/
│   │   │   ├── base.py
│   │   │   ├── structural.py
│   │   │   ├── tables.py
│   │   │   └── visual_elements.py
│   │
│   │   ├── embeddings/
│   │   │   ├── base.py
│   │   │   └── sentence_transformers.py
│   │
│   │   ├── search/
│   │   │   ├── client.py
│   │   │   ├── mappings.py
│   │   │   └── bulk_writer.py
│   │
│   │   └── pipeline.py
│   │
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── docker-compose.yml




python3 \
    -m app.cli \
    chunk \
    /srv/DocuMind/VRU_without_LLM \
    --user-id user_123 \
    --document-id doc_456 \
    --config examples/chunking_config.json \
    --output /srv/DocuMind/indexer-output/chunks.json



Run python -m ruff \
I001 [*] Import block is un-sorted or un-formatted
  --> app/api/main.py:1:1
   |
 1 | / from __future__ import annotations
 2 | |
 3 | | import logging
 4 | | from contextlib import asynccontextmanager
 5 | | from typing import Annotated
 6 | |
 7 | | from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
 8 | | from fastapi.middleware.cors import CORSMiddleware
 9 | | from starlette.concurrency import run_in_threadpool
10 | |
11 | | from app.api.jobs import JobManager, JobNotFoundError, OutputAlreadyInUseError
12 | | from app.api.models import (
13 | |     HealthResponse,
14 | |     IndexJobRequest,
15 | |     JobListResponse,
16 | |     JobRecord,
17 | |     QueryEmbeddingRequest,
18 | |     QueryEmbeddingResponse,
19 | | )
20 | | from app.api.paths import PathResolutionError, resolve_mounted_directory
21 | | from app.api.runtime import IndexerRuntime
22 | | from app.api.security import require_api_key
23 | | from app.api.storage import verify_readable_directory, verify_writable_directory
24 | | from app.api.settings import ApiSettings, get_settings
   | |______________________________________________________^
25 |
26 |   logger = logging.getLogger(__name__)
   |
help: Organize imports

Found 1 error.
[*] 1 fixable with the `--fix` option.
Error: Process completed with exit code 1.