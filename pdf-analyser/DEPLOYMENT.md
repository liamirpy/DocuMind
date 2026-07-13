# Distribution and release guide

## Recommended release contents

Ship these files in every tagged release:

```text
pdf-analyser/
├── compose.yaml
├── compose.nvidia.yaml
├── .env.example
├── scripts/
│   ├── install.sh
│   ├── install-nvidia.sh
│   └── install.ps1
├── tools/
├── agent/
├── README.md
└── DEPLOYMENT.md
```

A user can then unzip the release and run one installer script.

## Source-build release

This repository is immediately usable as a source-build release:

```bash
./scripts/install.sh
```

Docker builds `extractor-api` and `agent-api` locally. This is easy to publish but the first installation takes longer.

## Prebuilt-image release

For the easiest end-user installation, publish versioned application images, for example:

```text
ghcr.io/OWNER/pdf-analyser-extractor:0.3.0-cpu
ghcr.io/OWNER/pdf-analyser-extractor:0.3.0-cu126
ghcr.io/OWNER/pdf-analyser-agent:0.3.0
```

Then create a release Compose file containing only `image:` references. Pin application versions; do not depend on `latest` for your own images.

The CPU images can be published for more than one architecture only when every base image and binary dependency supports those architectures. Validate `linux/amd64` first, then add `linux/arm64` after full integration testing.

## Output contract

There are two independent output controls:

1. `OUTPUT_DIR` in `.env`: host parent directory.
2. `output_folder` in each API request: child package name.

Example:

```dotenv
OUTPUT_DIR=/srv/research-results
```

```bash
-F "output_folder=paper_2026_001"
```

Final host path:

```text
/srv/research-results/paper_2026_001/
```

The API never accepts an arbitrary output path from a request. This prevents a caller from writing outside the administrator-selected output root.

## Production hardening

Before exposing the service beyond localhost:

- place a reverse proxy in front of the Agent API;
- enable TLS;
- require an API key or identity-aware authentication;
- configure request-body size and rate limits;
- keep GROBID, Ollama, and the Tools API private unless external access is required;
- run vulnerability scans on released images;
- pin dependency versions and image tags;
- back up the selected `OUTPUT_DIR` and named model volumes as appropriate.
