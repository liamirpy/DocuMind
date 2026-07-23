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


Run docker compose \
  
  docker compose \
    config \
    --quiet
  shell: /usr/bin/bash -e {0}
  env:
    PYTHON_VERSION: 3.12
no configuration file provided: not found
Error: Process completed with exit code 1.







POST /api/rag/search
          │
          ▼
Read authenticated user from req.user.id
          │
          ▼
Send question to indexer
POST http://localhost:8000/v1/embeddings/query
          │
          ▼
Receive 1024-dimensional question embedding
          │
          ├───────────────┐
          ▼               ▼
OpenSearch k-NN       OpenSearch BM25
vector search         keyword search
          │               │
          └───────┬───────┘
                  ▼
        Merge search results
                  │
                  ▼
 Load parent chunks when available
                  │
                  ▼
 Return context and sources





### process

User upload  PDF 

PDF uploaded sucessfully 

then the PDF will goes to PDF analyser 

when it finished 

The pdf will goes to ingestor for converting to chunk 

After that it will go for indexer to index the data to Opensearch

After that that PDF is ready to talk 




### before all of that 

The postgresql will go up 

The opensearch will go up too 


 

 containers=$(sudo docker ps -q)

if [ -n "$containers" ]; then
    sudo docker stop $containers
else
    echo "No Docker containers are running."
fi





                         Internet / LAN
                               |
                        ports 80 and 443
                               |
                         ┌───────────┐
                         │   Nginx   │
                         │  Gateway  │
                         └─────┬─────┘
                               |
          ┌────────────────────┼────────────────────┐
          |                    |                    |
     api.example.com      tool1.example.com    tool2.example.com
          |                    |                    |
    ┌──────────┐         ┌──────────┐         ┌──────────┐
    │ Node API │         │  Tool 1  │         │  Tool 2  │
    │   :3000  │         │  :4000   │         │  :5000   │
    └────┬─────┘         └────┬─────┘         └────┬─────┘
         |                    |                    |
         └────────────────────┼────────────────────┘
                              |
                     Private data network
                              |
          ┌───────────────────┼───────────────────┐
          |                   |                   |
     PostgreSQL            Redis             OpenSearch
       :5432               :6379                :9200


      
      






                               PUBLIC REQUESTS
User / Frontend
       │
       │ POST /api/documents/upload
       ▼
┌──────────────────────────────┐
│            NGINX             │
│      Public gateway :80      │
└──────────────┬───────────────┘
               │
               ▼
        Express API
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
 PostgreSQL        Redis / BullMQ
                        │
                        │ job waiting
                        ▼
                  Node.js Worker
                        │
                        │ POST /pdf-analyser
                        ▼
┌──────────────────────────────┐
│            NGINX             │
│ Internal load balancer :8080 │
└──────────────┬───────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
 Analyser 1 Analyser 2 Analyser 3










 User / Frontend
       │
       │ POST /api/documents/upload
       ▼
┌──────────────────────────────┐
│         Public NGINX         │
│             :80              │
└──────────────┬───────────────┘
               │
               ▼
          Express API
               │
       ┌───────┴─────────────┐
       │                     │
       ▼                     ▼
   PgBouncer             Redis / BullMQ
       │                     │
       ▼                     ▼
  PostgreSQL             Node.js Worker
                               │
                               │ POST /pdf-analyser
                               ▼
                    ┌─────────────────────┐
                    │   Internal NGINX    │
                    │        :8080        │
                    └──────────┬──────────┘
                               │
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
                Analyser 1 Analyser 2 Analyser 3