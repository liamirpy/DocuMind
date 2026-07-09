# Validation report

The repository was checked before packaging with:

- Ruff lint: passed
- Ruff formatting check: passed
- Unit tests: 8 passed
- Python compilation: passed
- YAML parsing for CPU Compose, GPU Compose, GROBID config, and GitHub workflows: passed
- Shell syntax for project scripts: passed
- Sample PDF signature: passed
- ZIP integrity: checked after packaging

Not executed in the packaging environment:

- Docker image builds
- GROBID container startup
- Docling model download/inference
- NVIDIA GPU runtime test
- Full PDF extraction smoke test

Those runtime checks are provided as local commands and GitHub Actions workflows. Run `make smoke` after starting the stack, and use the manual `GPU integration smoke test` workflow on a self-hosted GPU runner.
