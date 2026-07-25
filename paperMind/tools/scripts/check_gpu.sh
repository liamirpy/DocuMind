#!/usr/bin/env bash
set -euo pipefail

command -v nvidia-smi >/dev/null || {
  echo "nvidia-smi is not installed or the NVIDIA driver is unavailable." >&2
  exit 1
}

nvidia-smi

echo
echo "Testing Docker GPU access..."
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
