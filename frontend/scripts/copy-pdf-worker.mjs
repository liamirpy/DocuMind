import { copyFile, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(
  projectRoot,
  "node_modules/pdfjs-dist/build/pdf.worker.min.mjs",
);
const destination = resolve(projectRoot, "public/pdf.worker.min.mjs");

await mkdir(dirname(destination), { recursive: true });
await copyFile(source, destination);
console.log("Copied PDF.js worker to public/pdf.worker.min.mjs");
