# DocuMind
A general-purpose AI document assistant built with RAG. Users can upload files, organize them into folders, and ask questions based on all documents, selected folders, or specific files.



pdf/
├── agent/
├── tools/
│
├── indexer/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models.py
│   │
│   │   ├── canonical/
│   │   │   ├── reader.py
│   │   │   └── validator.py
│   │
│   │   ├── chunking/
│   │   │   ├── base.py
│   │   │   ├── structural.py
│   │   │   ├── tables.py
│   │   │   └── visual_elements.py
│   │
│   │   ├── embeddings/
│   │   │   ├── base.py
│   │   │   └── sentence_transformers.py
│   │
│   │   ├── search/
│   │   │   ├── client.py
│   │   │   ├── mappings.py
│   │   │   └── bulk_writer.py
│   │
│   │   └── pipeline.py
│   │
│   ├── tests/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── docker-compose.yml




python3 \
    -m app.cli \
    chunk \
    /srv/DocuMind/VRU_without_LLM \
    --user-id user_123 \
    --document-id doc_456 \
    --config examples/chunking_config.json \
    --output /srv/DocuMind/indexer-output/chunks.json
