# Backend-managed PaperMind jobs

The path-based asynchronous endpoint accepts a backend correlation ID:

```json
{
  "backend_job_id": "document-job-id",
  "input_directory": "/host/users/...",
  "input_filename": "article.pdf",
  "output_directory": "/host/users/...",
  "output_folder": "pdfMind_article",
  "use_llm": true,
  "overwrite": false
}
```

PaperMind returns `202` and a local `job_id`. Job execution remains local to the
selected agent replica, but lifecycle updates are sent to:

```text
POST ${BACKEND_CALLBACK_BASE_URL}/{backend_job_id}/status
```

with `X-PaperMind-Callback-Token`. The DocuMind backend stores those updates in
shared Redis. Backend workers poll Redis rather than `/v1/jobs/{job_id}`, so
`agent-api` can be scaled behind Nginx without sticky sessions.

Required environment variables:

```dotenv
BACKEND_CALLBACK_BASE_URL=http://api:3000/internal/papermind/jobs
PAPERMIND_CALLBACK_TOKEN=replace-with-a-long-random-secret
BACKEND_CALLBACK_TIMEOUT_SECONDS=10
BACKEND_CALLBACK_MAX_RETRIES=5
```
