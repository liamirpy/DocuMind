# Optional backend change for permanent citation history

The frontend can immediately use `result.sources` from `/api/rag/search` and caches it in the current browser. That means citations remain clickable when the same saved conversation is reopened in that browser.

To restore citations on every browser/device, store the source array with the assistant message.

## Simple schema option

```sql
ALTER TABLE public.messages
ADD COLUMN IF NOT EXISTS sources jsonb;
```

Optionally enforce an array shape:

```sql
ALTER TABLE public.messages
ADD CONSTRAINT messages_sources_is_array
CHECK (sources IS NULL OR jsonb_typeof(sources) = 'array');
```

## Save sources with the assistant message

When inserting the assistant message in `ragRoutes.js`, include `sources`:

```sql
INSERT INTO messages (
  conversation_id,
  user_id,
  role,
  content,
  model,
  token_count,
  sources
)
VALUES ($1, $2, 'assistant', $3, $4, $5, $6::jsonb)
RETURNING
  id,
  public_id,
  role,
  content,
  model,
  token_count,
  sources,
  created_at
```

Pass:

```js
JSON.stringify(result.sources ?? [])
```

## Return sources when loading a conversation

Add `sources` to the messages query in `GET /api/conversations/:conversationId`:

```sql
SELECT
  id,
  public_id,
  role,
  content,
  model,
  token_count,
  sources,
  created_at
FROM messages
...
```

The frontend already understands this optional field:

```json
{
  "id": "assistant-message-uuid",
  "role": "assistant",
  "content": "Answer [S2].",
  "sources": [
    {
      "citationId": "S2",
      "documentId": "document-uuid",
      "pageStart": 1,
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
```

This JSONB approach is separate from `message_sources`. The existing relational `message_sources` table is useful when each RAG source can be reliably mapped to a row in `document_chunks`; use that design later if you need SQL analytics or source-level integrity constraints.
