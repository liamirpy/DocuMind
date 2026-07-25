# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG APP_UID=1000
ARG APP_GID=1000
# Optional. Leave empty for the default PyTorch wheel selected by pip.
# For an NVIDIA build, pass the PyTorch CUDA wheel index matching the host.
ARG TORCH_INDEX_URL=""

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models/huggingface \
    HF_HUB_CACHE=/models/huggingface/hub \
    HUGGINGFACE_HUB_CACHE=/models/huggingface/hub \
    SENTENCE_TRANSFORMERS_HOME=/models/huggingface/sentence-transformers \
    TOKENIZERS_PARALLELISM=false

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgomp1 \
        tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first so source-code edits do not invalidate the heavy
# model dependency layer.
COPY requirements.txt pyproject.toml README.md ./
RUN python -m pip install --upgrade pip setuptools wheel \
    && if [ -n "${TORCH_INDEX_URL}" ]; then \
         python -m pip install --index-url "${TORCH_INDEX_URL}" torch; \
       fi \
    && python -m pip install -r requirements.txt

COPY app ./app
COPY examples ./examples
COPY INPUT_CONTRACT.md EMBEDDING_DESIGN.md VALIDATION.md API.md DOCKER.md CHANGELOG.md ./

RUN python -m pip install --no-deps . \
    && groupadd --gid "${APP_GID}" app \
    && useradd \
        --uid "${APP_UID}" \
        --gid "${APP_GID}" \
        --create-home \
        --shell /usr/sbin/nologin \
        app \
    && mkdir -p \
        /data/input \
        /data/output \
        /data/output/.jobs \
        /models/huggingface \
        /models/huggingface/hub \
        /models/huggingface/sentence-transformers \
    && chown -R \
        "${APP_UID}:${APP_GID}" \
        /data \
        /models \
        /app

USER app

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
