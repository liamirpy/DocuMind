# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG TORCH_VERSION=2.11.0
ARG TORCHVISION_VERSION=0.26.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       curl \
       gosu \
       libgl1 \
       libglib2.0-0 \
       libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-base.txt requirements-docling.txt ./

# Install the selected PyTorch build before Docling. The CPU Compose file passes
# the CPU wheel index; docker-compose.gpu.yml passes the CUDA 12.6 wheel index.
RUN python -m pip install --upgrade pip \
    && python -m pip install \
       "torch==${TORCH_VERSION}" \
       "torchvision==${TORCHVISION_VERSION}" \
       --index-url "${TORCH_INDEX_URL}" \
    && python -m pip install \
       -r requirements-base.txt \
       -r requirements-docling.txt \
    && python -m pip check

COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# RapidOCR downloads model weights into its package directory on first use.
# Make that directory writable by the non-root runtime user.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /models /data/assets \
    && RAPIDOCR_MODELS_DIR="$(python -c 'from pathlib import Path; import rapidocr; print(Path(rapidocr.__file__).resolve().parent / "models")')" \
    && mkdir -p "${RAPIDOCR_MODELS_DIR}" \
    && chown -R appuser:appuser /app /models /data/assets "${RAPIDOCR_MODELS_DIR}" \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]

EXPOSE 8000

# One worker is intentional. Each worker loads a separate copy of the Docling models.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
