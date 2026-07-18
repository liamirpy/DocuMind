import { Client } from "@opensearch-project/opensearch";

const node = process.env.OPENSEARCH_NODE;

if (!node) {
  throw new Error("OPENSEARCH_NODE is required");
}

const rejectUnauthorized =
  process.env.OPENSEARCH_TLS_REJECT_UNAUTHORIZED !== "false";

const clientOptions = {
  node,

  ssl: {
    rejectUnauthorized,
  },
};

if (
  process.env.OPENSEARCH_USERNAME &&
  process.env.OPENSEARCH_PASSWORD
) {
  clientOptions.auth = {
    username: process.env.OPENSEARCH_USERNAME,
    password: process.env.OPENSEARCH_PASSWORD,
  };
}

export const opensearchClient = new Client(clientOptions);

export const OPENSEARCH_INDEX =
  process.env.OPENSEARCH_INDEX || "documind-chunks-*";