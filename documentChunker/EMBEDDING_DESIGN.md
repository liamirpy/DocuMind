# Embedding design

## Production provider

The package uses `sentence-transformers` with the configured model. The default is
`BAAI/bge-m3` because the current DocuMind output can contain scientific language and may later
contain multiple languages. The provider:

1. loads the model once;
2. exposes the exact model tokenizer to the chunker;
3. calls `encode_document()` for chunk content when the installed Sentence Transformers version
   supports it;
4. calls `encode_query()` for user questions when supported;
5. batches document embeddings;
6. L2-normalizes vectors by default;
7. validates the output dimension;
8. records model, provider, tokenizer, dimension, device, and truncation metadata in JSON.

## Why parent chunks are skipped by default

Child chunks provide precise retrieval targets. Parent chunks are larger context containers.
Embedding both can create duplicate competing search results and increases vector storage.
Therefore the default is:

```text
child / table / figure / formula -> embedded
parent                            -> stored, not embedded
```

After retrieval, use `parent_chunk_id` to load the parent context.

## Overlong inputs

There are two independent size controls:

- chunking limits (`text.*.max_tokens` and `special_elements.max_tokens`);
- embedding limits (`embedding.max_input_tokens` and the model's native sequence length).

The default embedding policy is `error` so input is never silently truncated. Set
`overlong_policy` to `truncate` only when that behavior is explicitly acceptable. When
truncation occurs, the output records:

```json
{
  "embedding_truncated": true,
  "embedding_text": "the actual shortened text used by the model"
}
```

The original `retrieval_text` remains unchanged.

## Model changes

When changing the model:

1. update `embedding.model_name`;
2. update or clear `embedding.expected_dimensions`;
3. create a new OpenSearch physical index with the new vector dimension;
4. re-run this package to regenerate vectors;
5. switch the OpenSearch read/write aliases after validation.

Do not mix vectors from unrelated models in the same `knn_vector` field.
