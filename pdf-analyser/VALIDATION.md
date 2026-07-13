# Validation Report

Validation performed on the v0.3.0 packaged repository:

- Agent Ruff formatting: passed.
- Agent Ruff linting: passed.
- Agent unit tests: 24 passed.
- Agent Python compilation: passed.
- Nested TEI section/subsection hierarchy tests: passed.
- Section-to-paragraph and section-to-asset linking tests: passed.
- Vision-model description generation tests for figures, tables, and formulas: passed.
- Safe custom output-folder normalization and traversal protection tests: passed.
- Existing-package collision protection tests: passed.
- Tools Ruff formatting: passed.
- Tools Ruff linting: passed.
- Tools unit tests: 10 passed.
- GROBID `/api/isalive` and XML content-negotiation tests: passed.
- Tools Python compilation: passed.
- Root CPU Compose YAML parsed successfully.
- NVIDIA Compose override YAML parsed successfully.
- Standalone Tools and Agent Compose YAML parsed successfully.
- Linux installer shell syntax: passed.
- NVIDIA installer shell syntax: passed.
- Agent entrypoint shell syntax: passed.
- Public repository scan found no personal email address or user-specific local deployment path.

Not executed in the packaging environment:

- Docker Compose image builds;
- GROBID startup;
- Docling model downloads/inference;
- NVIDIA GPU inference;
- Ollama/Qwen inference;
- full HTTP end-to-end processing.

Validate the release on at least one clean CPU host and one NVIDIA host before publishing it as a production release.
