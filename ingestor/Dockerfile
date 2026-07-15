FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY templates ./templates

RUN pip install --no-cache-dir .

# Runtime contract:
# - mount indexer output under /input (read-only)
# - set INPUT_FILE or INPUT_DIR
# - set OPENSEARCH_* connection values
ENTRYPOINT ["documind-ingestor"]
