# Validation

Validated for release 4.1.0:

- 29 automated Python tests passed;
- Python source compilation passed;
- Docker Compose YAML parsed successfully;
- standalone directory → chunks → development embeddings → JSON smoke run passed;
- `.jobs` recreation is covered by an API test;
- startup storage probes are covered by unit and API tests;
- string and array reference-coordinate formats are accepted.

The production `BAAI/bge-m3` model was not downloaded during package validation. The first
production job downloads it into the Docker-managed `huggingface-cache` volume.

A Docker daemon was not available in the packaging environment, so the image was not built or
started there. The Compose file was validated structurally and the application was exercised
outside Docker with the development embedding provider.
