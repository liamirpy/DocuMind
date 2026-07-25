#!/usr/bin/env sh
set -eu

# Start the persistent API service. Ingest documents with POST /ingest.
docker compose up -d --build ingestor-api
