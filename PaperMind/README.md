Checkout my PaperMind repository 


bash ./scripts/install-nvida.sh 

curl \
  --fail \
  --show-error \
  -X POST \
  "http://127.0.01:5000/v1/process" \
  -F "file=@/srv/DocuMind/pdf_example/RAX_NET.pdf;type=application/pdf" \
  -F "use_llm=true" \
  -F "output_folder=Results_with_LLM" \
  -F "overwrite=false" \
  -o agent-result.json





for indexer 


curl -X POST http://localhost:8000/v1/indexing/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "user_id": "user_123",
    "document_id": "doc_456",
    "input_directory": "/srv/DocuMind/pdf_example/pdf_analyser_output/Results_with_LLM",
    "output_directory": "/srv/DocuMind/pdf_example/indexer_output/doc_456"
  }'

