import 'dotenv/config';
import { Worker } from 'bullmq';
import axios from 'axios';
import FormData from 'form-data';
import fs from 'node:fs';
import path from 'node:path';

import {
    createWorkerRedisConnection
} from '../queues/redisConnection.js';

const QUEUE_NAME = 'document-processing';

const uploadDir = path.resolve(
    process.env.UPLOAD_DIR || 'src/uploads'
);

const resultsDir = path.resolve(
    process.env.PROCESSOR_RESULTS_DIR ||
    'src/processor-results'
);

const processorUrl =
    process.env.PROCESSOR_URL ||
    'http://127.0.0.1:5000/v1/process';

const processorTimeout = Number(
    process.env.PROCESSOR_TIMEOUT_MS || 600000
);

const redisConnection = createWorkerRedisConnection();

/**
 * Safely creates the full file path from the storage key.
 */
function getUploadedFilePath(storageKey) {
    const filePath = path.resolve(uploadDir, storageKey);

    const isInsideUploadDirectory =
        filePath.startsWith(`${uploadDir}${path.sep}`);

    if (!isInsideUploadDirectory) {
        throw new Error('Invalid file storage path');
    }

    return filePath;
}

/**
 * Extract a useful error message from Axios.
 */
function getProcessorError(error) {
    if (!axios.isAxiosError(error)) {
        return error.message;
    }

    if (!error.response) {
        return error.message;
    }

    const status = error.response.status;

    let responseBody = '';

    if (error.response.data) {
        responseBody = Buffer
            .from(error.response.data)
            .toString('utf8')
            .slice(0, 2000);
    }

    return responseBody
        ? `Processor returned HTTP ${status}: ${responseBody}`
        : `Processor returned HTTP ${status}`;
}

const worker = new Worker(
    QUEUE_NAME,

    async (job) => {
        console.log('--------------------------------');
        console.log(`Processing job: ${job.id}`);
        console.log('Job data:', job.data);

        if (job.name !== 'process-document') {
            throw new Error(`Unknown job type: ${job.name}`);
        }

        const {
            documentId,
            userId,
            storageKey,
            originalFilename,
            mimeType
        } = job.data;

        if (!documentId || !userId || !storageKey) {
            throw new Error(
                'documentId, userId and storageKey are required'
            );
        }

        const filePath = getUploadedFilePath(storageKey);

        console.log('Uploaded file path:', filePath);

        if (!fs.existsSync(filePath)) {
            throw new Error(
                `Uploaded file does not exist: ${filePath}`
            );
        }

        await job.updateProgress(10);

        /*
         * This creates the equivalent of:
         *
         * -F "file=@file.pdf;type=application/pdf"
         * -F "use_llm=true"
         * -F "output_folder=Results_with_LLM"
         * -F "overwrite=false"
         */
        const form = new FormData();

        form.append(
            'file',
            fs.createReadStream(filePath),
            {
                filename:
                    originalFilename ||
                    path.basename(filePath),

                contentType:
                    mimeType ||
                    'application/octet-stream'
            }
        );

        form.append(
            'use_llm',
            process.env.PROCESSOR_USE_LLM || 'true'
        );

        form.append(
            'output_folder',
            process.env.PROCESSOR_OUTPUT_FOLDER ||
            'Results_with_LLM_node'
        );

        form.append(
            'overwrite',
            process.env.PROCESSOR_OVERWRITE || 'false'
        );

        console.log('Sending file to:', processorUrl);

        await job.updateProgress(25);

        let response;

        try {
            response = await axios.post(
                processorUrl,
                form,
                {
                    headers: form.getHeaders(),

                    responseType: 'arraybuffer',

                    timeout: processorTimeout,

                    maxBodyLength: Infinity,
                    maxContentLength: Infinity,

                    validateStatus: (status) => {
                        return status >= 200 && status < 300;
                    }
                }
            );
        } catch (error) {
            throw new Error(getProcessorError(error));
        }

        await job.updateProgress(80);

        const responseBuffer = Buffer.from(response.data);
        const responseText = responseBuffer.toString('utf8');

        // Make sure the response is valid JSON.
        try {
            JSON.parse(responseText);
        } catch {
            throw new Error(
                'Processing API returned an invalid JSON response'
            );
        }

        /*
         * Save each document result separately:
         *
         * src/processor-results/
         *   7/
         *     25/
         *       agent-result.json
         */
        const documentResultsDir = path.join(
            resultsDir,
            String(userId),
            String(documentId)
        );

        fs.mkdirSync(documentResultsDir, {
            recursive: true
        });

        const resultFilePath = path.join(
            documentResultsDir,
            'agent-result.json'
        );

        fs.writeFileSync(resultFilePath, responseBuffer);

        await job.updateProgress(100);

        console.log('Processing completed');
        console.log('Result saved at:', resultFilePath);
        console.log('--------------------------------');

        return {
            documentId,
            resultFilePath
        };
    },

    {
        connection: redisConnection,
        concurrency: 1
    }
);

worker.on('ready', () => {
    console.log(
        `Worker is listening to queue: ${QUEUE_NAME}`
    );
});

worker.on('completed', (job, result) => {
    console.log(`Job ${job.id} completed successfully`);
    console.log('Result:', result);
});

worker.on('failed', (job, error) => {
    console.error(
        `Job ${job?.id || 'unknown'} failed:`,
        error.message
    );
});

worker.on('error', (error) => {
    console.error('Worker error:', error);
});

async function shutdown(signal) {
    console.log(`${signal} received. Closing worker...`);

    await worker.close();
    await redisConnection.quit();

    process.exit(0);
}

process.once('SIGINT', () => shutdown('SIGINT'));
process.once('SIGTERM', () => shutdown('SIGTERM'));