# Backend requirements for saved conversations

This archive changes only the frontend. The backend must persist RAG conversations.

## Conversation list

`GET /api/conversations` should return:

```json
{
  "conversations": [
    {
      "id": "uuid",
      "title": "Beginning of the first question",
      "created_at": "...",
      "updated_at": "...",
      "message_count": 2,
      "last_message": "..."
    }
  ]
}
```

## Conversation detail

`GET /api/conversations/:conversationId` should return:

```json
{
  "conversation": {
    "id": "uuid",
    "title": "Beginning of the first question",
    "created_at": "...",
    "updated_at": "..."
  },
  "messages": [
    {
      "id": "uuid",
      "role": "user",
      "content": "...",
      "created_at": "..."
    },
    {
      "id": "uuid",
      "role": "assistant",
      "content": "...",
      "created_at": "..."
    }
  ]
}
```

## RAG persistence

`POST /api/rag/search` must accept an optional `conversationId`.

When it is absent, create a conversation whose title is the normalised first 60 characters of the first question. When it is present, verify that the conversation belongs to the authenticated user and append the new user and assistant messages.

Return the saved `conversation`, `messages.user`, and `messages.assistant` in the response. The frontend relies on those objects for immediate sidebar and chat updates.
