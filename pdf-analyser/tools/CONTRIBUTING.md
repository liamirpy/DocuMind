# Contributing

## Development checks

Create a Python 3.12 virtual environment and install lightweight development dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r api/requirements-dev.txt
```

Before opening a pull request:

```bash
make format
make lint
make test

docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.gpu.yml config --quiet
```

For extraction changes, run the smoke test against both CPU and GPU when hardware is available. Record any changes in table structure, formulas, image crops, performance, and memory use against the project benchmark PDFs.

Do not commit:

- `.env`
- user PDFs
- extracted assets
- API results containing article content
- model caches
- credentials or organization-specific endpoints
