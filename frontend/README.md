# DocuMind frontend — clickable RAG citations

This frontend keeps the existing authentication, folder, upload, status, saved-conversation, and chat features, and adds an in-app PDF citation viewer.

## What was added

- Parses citations such as `[S1]` and `[S2]` in assistant answers.
- Matches each marker to `result.sources[].citationId`.
- Opens the authenticated source PDF through the existing `/api/documents/:id/download` endpoint.
- Jumps directly to `pageStart`.
- Uses PDF.js to render the page.
- Converts PDF `BOTTOMLEFT` bbox coordinates using the PDF.js viewport transform.
- Draws a translucent highlight when a numeric bbox exists.
- Supports previous/next page navigation, zoom, close, and download.
- Caches source metadata by assistant-message ID in localStorage so citations still work after reopening the conversation in the same browser.
- Also accepts `sources` returned directly on stored conversation messages, ready for server-side citation persistence later.

## Install and run

```bash
cp .env.local.example .env.local
npm install
npm run dev
```

`npm install` runs a postinstall script that copies the PDF.js worker to:

```text
public/pdf.worker.min.mjs
```

Do not use `npm install --ignore-scripts`, unless you manually run:

```bash
node scripts/copy-pdf-worker.mjs
```

Open the application at:

```text
http://192.168.0.102:3000
```

## Expected RAG source shape

```json
{
  "answer": {
    "answer": "The answer text [S2]."
  },
  "result": {
    "sources": [
      {
        "citationId": "S2",
        "documentId": "document-uuid",
        "pageStart": 1,
        "pageEnd": 1,
        "bbox": {
          "l": 311.97,
          "b": 237.02,
          "r": 563.03,
          "t": 629.95,
          "coord_origin": "BOTTOMLEFT"
        }
      }
    ]
  }
}
```

When `bbox` is `"not available"`, the cited page still opens but no highlight is drawn.

## Backend requirements

The existing authenticated endpoint must continue returning the original PDF bytes:

```http
GET /api/documents/:documentId/download
Authorization: Bearer <access-token>
```

No backend change is required for citations in a newly generated answer because the RAG response already contains `result.sources`.

For permanent citation restoration on another device or browser, read `CITATION-BACKEND-NOTES.md`.
