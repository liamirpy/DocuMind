Checkout my PaperMind repository 


bash ./scripts/install-nvida.sh 

curl \
  --fail \
  --show-error \
  -X POST \
  "http://127.0.01:5000/v1/process" \
  -F "file=@/srv/DocuMind/VRU.pdf;type=application/pdf" \
  -F "use_llm=false" \
  -F "output_folder=VRU_without_LLM_final" \
  -F "overwrite=false" \
  -o agent-result.json

