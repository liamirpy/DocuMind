# Changelog

## 4.1.0

- Added a one-shot `init-permissions` Compose service.
- Replaced the host bind-mounted Hugging Face cache with a Docker named volume.
- Automatically creates and prepares `/data/output/.jobs` on every Compose startup.
- Added startup read/write probes for input, output, job-state, and model-cache storage.
- Added clearer readiness details for mounted storage.
- Retained atomic job-state and output writes.
- Retained rollback of job/output locks when initial persistence fails.
- Added storage tests and updated Docker/API documentation.
