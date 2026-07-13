# Contributing

## Development setup

```bash
cd agent
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
make check
```

For tools development:

```bash
cd tools/api
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff format --check .
ruff check .
pytest -q
```

## Pull requests

- Keep deterministic extraction/validation separate from LLM-derived data.
- Never overwrite parser evidence with an LLM result.
- Add tests for schema or merge changes.
- Update the README when configuration, commands, or output paths change.
- Do not commit PDFs containing private or licensed content.
- Do not commit `.env`, model caches, generated assets, or output packages.

## Code quality

Root CI requires:

```bash
make check
```

Use focused commits and describe any output-schema changes explicitly.
