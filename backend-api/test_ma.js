import { embedQuestion } from "./src/services/embeddingService.js";


process.env.OPENSEARCH_NODE="https://localhost:9200"
process.env.OPENSEARCH_USERNAME="admin"
process.env.OPENSEARCH_PASSWORD="DOCUMIND_opensearch_password_2026"

const { OPENSEARCH_INDEX, opensearchClient }= await import( "./src/config/opensearchClient.js");



// try {
//   const result = await embedQuestion("What is OpenSearch?");
//   console.log("Success:", result);
// } catch (error) {
//   console.error("Status:", error.statusCode);
//   console.error("Message:", error.message);
// }







// OPENAI_API_BASE_URL=http://localhost:8080 \
// EMBEDDING_DIMENSIONS=1024 \
// node test_ma.js



// OPENSEARCH_NODE="https://localhost:9200" \
// OPENSEARCH_USERNAME="admin" \
// OPENSEARCH_PASSWORD="your-password" \
// OPENSEARCH_TLS_REJECT_UNAUTHORIZED="false" \
// OPENSEARCH_INDEX="documind-chunk-*" \
// npm run test:opensearch