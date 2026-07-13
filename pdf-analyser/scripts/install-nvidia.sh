#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! docker version >/dev/null 2>&1; then
  echo "Docker is not available. Install Docker Engine or Docker Desktop first." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required." >&2
  exit 1
fi

if ! docker run --rm --gpus all ubuntu nvidia-smi >/dev/null 2>&1; then
  echo "Docker cannot access the NVIDIA GPU. Install/configure NVIDIA Container Toolkit first." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

mkdir -p outputs

if command -v id >/dev/null 2>&1 && command -v awk >/dev/null 2>&1; then
  uid="$(id -u)"
  gid="$(id -g)"
  tmp="$(mktemp)"
  awk -v uid="$uid" -v gid="$gid" '
    /^HOST_UID=/ { print "HOST_UID=" uid; next }
    /^HOST_GID=/ { print "HOST_GID=" gid; next }
    { print }
  ' .env > "$tmp"
  mv "$tmp" .env
fi

docker compose -f compose.yaml -f compose.nvidia.yaml up -d --build

echo
echo "NVIDIA stack started. First startup downloads Docling and Ollama models."
echo "Check readiness with: docker compose -f compose.yaml -f compose.nvidia.yaml ps"
echo "Agent API: http://localhost:8100"
