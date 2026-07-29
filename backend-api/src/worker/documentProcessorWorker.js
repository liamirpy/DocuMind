import 'dotenv/config';
import { Worker } from 'bullmq';
import axios from 'axios';
import FormData from 'form-data';
import fs from 'node:fs';
import path from 'node:path';
import { pool } from "../db/pool.js";


import {
    createWorkerRedisConnection
} from '../queues/redisConnection.js';

const QUEUE_NAME = 'document-processing';

/*
 * Backend storage:
 *
 * ../data/users/
 *   <userId>/
 *     <folderName>/
 *       document.pdf
 */
const uploadDir = path.resolve(
    process.env.UPLOAD_DIR || '../data/users'
);

/*
 * PaperMind configuration.
 *
 * Based on your current mount:
 *
 * Host:
 * /srv/DocuMind/data
 *
 * PaperMind:
 * /host
 *
 * Therefore:
 * /srv/DocuMind/data/users
 * becomes:
 * /host/users
 */
const processorMountRoot = normalizeMountRoot(
    process.env.PROCESSOR_MOUNT_ROOT ||
    '/host/users'
);

const processorUrl = (
    process.env.PROCESSOR_URL ||
    'http://127.0.0.1:5000/v1/process-path'
).replace(/\/+$/, '');


console.log('Indexing request configuration:',processorUrl
);

const processorTimeout = parsePositiveNumber(
    process.env.PROCESSOR_TIMEOUT_MS,
    600000
);

const processorUseLlm = parseBoolean(
    process.env.PROCESSOR_USE_LLM,
    true
);

const processorOverwrite = parseBoolean(
    process.env.PROCESSOR_OVERWRITE,
    false
);

/*
 * Indexing service configuration.
 */
const indexingJobsUrl = (
    process.env.INDEXING_URL ||
    'http://127.0.0.1:8000/v1/indexing/jobs'
).replace(/\/+$/, '');

const indexingApiKey =
    process.env.INDEXING_API_KEY || 'hello';

const indexingRequestTimeout =
    parsePositiveNumber(
        process.env.INDEXING_TIMEOUT_MS,
        30000
    );

const indexingPollInterval =
    parsePositiveNumber(
        process.env.INDEXING_POLL_INTERVAL_MS,
        3000
    );

const indexingMaximumWait =
    parsePositiveNumber(
        process.env.INDEXING_MAX_WAIT_MS,
        1800000
    );

const indexingMaximumStatusErrors =
    parsePositiveInteger(
        process.env.INDEXING_MAX_STATUS_ERRORS,
        3
    );

/*
 * Leave empty when the indexing service can access the
 * same absolute host paths as the Node.js worker.
 *
 * Set to /host when the indexer runs inside Docker and
 * UPLOAD_DIR is mounted there.
 */

const indexingInputMountRoot = normalizeMountRoot(
    process.env.INDEXING_INPUT_MOUNT_ROOT ||
    '/data/users'
);

const indexingOutputMountRoot = normalizeMountRoot(
    process.env.INDEXING_OUTPUT_MOUNT_ROOT ||
    '/data/users'
);

/*
 * OpenSearch ingestion service configuration.
 */
const ingestUrl = (
    process.env.INGEST_URL ||
    'http://127.0.0.1:8080/ingest'
).replace(/\/+$/, '');

const ingestTimeout = parsePositiveNumber(
    process.env.INGEST_TIMEOUT_MS,
    600000
);

/*
 * false means the ingestion service should write the
 * chunk data to OpenSearch.
 */
const ingestDryRun = parseBoolean(
    process.env.INGEST_DRY_RUN,
    false
);

const expectedEmbeddingDimensions =
    parsePositiveInteger(
        process.env.EXPECTED_EMBEDDING_DIMENSIONS,
        1024
    );

/*
 * After the indexing API reports completion, wait briefly
 * for chunks.json to become visible on the filesystem.
 */
const chunksFileWaitTimeout =
    parsePositiveNumber(
        process.env.CHUNKS_FILE_WAIT_MS,
        30000
    );

const chunksFilePollInterval =
    parsePositiveNumber(
        process.env.CHUNKS_FILE_POLL_INTERVAL_MS,
        1000
    );

const redisConnection =
    createWorkerRedisConnection();

console.log('Worker configuration:');
console.log('UPLOAD_DIR:', uploadDir);
console.log('PROCESSOR_URL:', processorUrl);
console.log(
    'PROCESSOR_MOUNT_ROOT:',
    processorMountRoot
);
console.log(
    'INDEXING_URL:',
    indexingJobsUrl
);
console.log(
    'INDEXING_MOUNT_ROOT:',
    indexingInputMountRoot ||
    'same host filesystem'
);
console.log('INGEST_URL:', ingestUrl);
console.log('INGEST_DRY_RUN:', ingestDryRun);
console.log(
    'EXPECTED_EMBEDDING_DIMENSIONS:',
    expectedEmbeddingDimensions
);

function parseBoolean(value, defaultValue) {
    if (
        value === undefined ||
        value === null
    ) {
        return defaultValue;
    }

    const normalizedValue = String(value)
        .trim()
        .toLowerCase();

    if (
        normalizedValue === 'true' ||
        normalizedValue === '1' ||
        normalizedValue === 'yes'
    ) {
        return true;
    }

    if (
        normalizedValue === 'false' ||
        normalizedValue === '0' ||
        normalizedValue === 'no'
    ) {
        return false;
    }

    return defaultValue;
}

function parsePositiveNumber(
    value,
    defaultValue
) {
    const parsedValue = Number(value);

    if (
        !Number.isFinite(parsedValue) ||
        parsedValue <= 0
    ) {
        return defaultValue;
    }

    return parsedValue;
}

function parsePositiveInteger(
    value,
    defaultValue
) {
    const parsedValue = Number.parseInt(
        value,
        10
    );

    if (
        !Number.isInteger(parsedValue) ||
        parsedValue <= 0
    ) {
        return defaultValue;
    }

    return parsedValue;
}

function normalizeMountRoot(value) {
    let normalizedValue = String(value)
        .trim()
        .replace(/\\/g, '/');

    if (!normalizedValue) {
        throw new Error(
            'A valid mount root is required'
        );
    }

    if (normalizedValue !== '/') {
        normalizedValue =
            normalizedValue.replace(/\/+$/, '');
    }

    return normalizedValue;
}

function isPathInside(
    parentPath,
    childPath
) {
    const relativePath = path.relative(
        parentPath,
        childPath
    );

    return (
        relativePath === '' ||
        (
            relativePath !== '..' &&
            !relativePath.startsWith(
                `..${path.sep}`
            ) &&
            !path.isAbsolute(relativePath)
        )
    );
}

function delay(milliseconds) {
    return new Promise(resolve => {
        setTimeout(resolve, milliseconds);
    });
}

/**
 * Resolve a database storage key inside UPLOAD_DIR.
 *
 * Example storageKey:
 *
 * user-id/stroke/example.pdf
 */
function getUploadedFilePath(storageKey) {
    if (
        typeof storageKey !== 'string' ||
        !storageKey.trim()
    ) {
        throw new Error(
            'A valid storageKey is required'
        );
    }

    const filePath = path.resolve(
        uploadDir,
        storageKey
    );

    if (
        !isPathInside(
            uploadDir,
            filePath
        )
    ) {
        throw new Error(
            'Invalid document storage path'
        );
    }

    return filePath;
}

/**
 * Convert a backend filesystem path into a mounted path
 * visible inside another service.
 *
 * Backend:
 * /srv/DocuMind/data/users/user-id/stroke
 *
 * PaperMind:
 * /host/users/user-id/stroke
 */
function convertToMountedPath(
    localPath,
    mountRoot
) {
    const absoluteLocalPath =
        path.resolve(localPath);

    if (
        !isPathInside(
            uploadDir,
            absoluteLocalPath
        )
    ) {
        throw new Error(
            `Path is outside UPLOAD_DIR: ` +
            absoluteLocalPath
        );
    }

    const relativePath = path.relative(
        uploadDir,
        absoluteLocalPath
    );

    if (!relativePath) {
        return mountRoot;
    }

    const normalizedRelativePath =
        relativePath
            .split(path.sep)
            .join('/');

    return path.posix.join(
        mountRoot,
        normalizedRelativePath
    );
}

function getProcessorPath(localPath) {
    return convertToMountedPath(
        localPath,
        processorMountRoot
    );
}

/**
 * When INDEXING_MOUNT_ROOT is empty, the indexer receives
 * the real absolute host path.
 */
function getIndexerPath(localPath, mountRoot) {
    const absoluteLocalPath = path.resolve(localPath);

    if (!isPathInside(uploadDir, absoluteLocalPath)) {
        throw new Error(
            `Indexer path is outside UPLOAD_DIR: ${absoluteLocalPath}`
        );
    }

    return convertToMountedPath(
        absoluteLocalPath,
        mountRoot
    );
}

function getFilenameWithoutExtension(
    filename
) {
    const baseFilename =
        path.basename(filename);

    if (
        baseFilename
            .toLowerCase()
            .endsWith('.nii.gz')
    ) {
        return baseFilename.slice(0, -7);
    }

    return path.parse(baseFilename).name;
}

/**
 * Medical Report.pdf
 * becomes:
 * Medical_Report
 */
function getSafeDocumentName(filename) {
    const filenameWithoutExtension =
        getFilenameWithoutExtension(filename);

    const safeName =
        filenameWithoutExtension
            .normalize('NFC')
            .replace(
                /[<>:"/\\|?*\u0000-\u001F]/g,
                '_'
            )
            .replace(/\s+/g, '_')
            .replace(/[. ]+$/g, '')
            .slice(0, 150);

    return safeName || 'document';
}

function getPaperMindFolderName(filename) {
    return (
        `pdfMind_${getSafeDocumentName(filename)}`
    );
}

function getIndexerFolderName(filename) {
    return (
        `indexer_${getSafeDocumentName(filename)}`
    );
}

function stringifyResponseData(data) {
    if (
        data === undefined ||
        data === null
    ) {
        return '';
    }

    if (Buffer.isBuffer(data)) {
        return data.toString('utf8');
    }

    if (data instanceof ArrayBuffer) {
        return Buffer
            .from(data)
            .toString('utf8');
    }

    if (typeof data === 'string') {
        return data;
    }

    try {
        return JSON.stringify(data);
    } catch {
        return '';
    }
}

function getAxiosError(
    error,
    serviceName
) {
    if (!axios.isAxiosError(error)) {
        return (
            error?.message ||
            `${serviceName} returned an unknown error`
        );
    }

    if (!error.response) {
        return (
            `${serviceName} request failed: ` +
            error.message
        );
    }

    const status =
        error.response.status;

    const responseBody =
        stringifyResponseData(
            error.response.data
        )
            .trim()
            .slice(0, 2000);

    return responseBody
        ? `${serviceName} returned HTTP ${status}: ${responseBody}`
        : `${serviceName} returned HTTP ${status}`;
}

async function getDirectoryEntries(
    directoryPath
) {
    try {
        return await fs.promises.readdir(
            directoryPath
        );
    } catch (error) {
        if (error.code === 'ENOENT') {
            return null;
        }

        throw error;
    }
}

/**
 * Task 1: run PaperMind.
 *
 * PaperMind creates:
 *
 * pdfMind_<filename>
 *
 * The worker does not create or save agent-result.json.
 */
async function runPaperMind({
    inputFilename,
    localDocumentDirectory,
    localPaperMindDirectory,
    paperMindFolderName
}) {
    /*
     * Makes BullMQ retries safer. If PaperMind already
     * completed and overwrite is disabled, skip this step.
     */
    if (!processorOverwrite) {
        const existingEntries =
            await getDirectoryEntries(
                localPaperMindDirectory
            );

        if (
            existingEntries &&
            existingEntries.length > 0
        ) {
            console.log(
                'PaperMind output already exists; skipping:',
                localPaperMindDirectory
            );

            return {
                skipped: true,
                outputDirectory:
                    localPaperMindDirectory,
                generatedEntries:
                    existingEntries
            };
        }
    }

    const processorDocumentDirectory =
        getProcessorPath(
            localDocumentDirectory
        );

    const requestBody = {
        input_directory:
            processorDocumentDirectory,

        input_filename:
            inputFilename,

        output_directory:
            processorDocumentDirectory,

        output_folder:
            paperMindFolderName,

        use_llm:
            processorUseLlm,

        overwrite:
            processorOverwrite
    };

    console.log(
        'Sending PaperMind request to:',
        processorUrl
    );

    console.log(
        'PaperMind request:',
        requestBody
    );

    try {
        await axios.post(
            processorUrl,
            requestBody,
            {
                headers: {
                    'Content-Type':
                        'application/json',

                    Accept:
                        'application/json'
                },

                timeout:
                    processorTimeout,

                maxBodyLength:
                    Infinity,

                maxContentLength:
                    Infinity,

                validateStatus: status =>
                    status >= 200 &&
                    status < 300
            }
        );
    } catch (error) {
        throw new Error(
            getAxiosError(
                error,
                'PaperMind'
            )
        );
    }

    let outputStats;

    try {
        outputStats =
            await fs.promises.stat(
                localPaperMindDirectory
            );
    } catch (error) {
        if (error.code === 'ENOENT') {
            throw new Error(
                `PaperMind did not create its output directory: ` +
                localPaperMindDirectory
            );
        }

        throw error;
    }

    if (!outputStats.isDirectory()) {
        throw new Error(
            `PaperMind output path is not a directory: ` +
            localPaperMindDirectory
        );
    }

    const generatedEntries =
        await fs.promises.readdir(
            localPaperMindDirectory
        );

    if (generatedEntries.length === 0) {
        throw new Error(
            `PaperMind created an empty output directory: ` +
            localPaperMindDirectory
        );
    }

    return {
        skipped: false,
        outputDirectory:
            localPaperMindDirectory,
        generatedEntries
    };
}

/**
 * Task 2a: submit the asynchronous indexing job.
 */
async function submitIndexingJob({
    userId,
    documentId,
    inputDirectory,
    outputDirectory
}) {
    const requestBody = {
        user_id:
            String(userId),

        document_id:
            String(documentId),

        input_directory:
            inputDirectory,

        output_directory:
            outputDirectory
    };

    console.log(
        'Sending indexing request to:',
        indexingJobsUrl
    );

    console.log(
        'Indexing request:',
        requestBody
    );

    let response;

    try {
        response = await axios.post(
            indexingJobsUrl,
            requestBody,
            {
                headers: {
                    'Content-Type':
                        'application/json',

                    'X-API-Key':
                        indexingApiKey,

                    Accept:
                        'application/json'
                },

                timeout:
                    indexingRequestTimeout,

                maxBodyLength:
                    Infinity,

                maxContentLength:
                    Infinity,

                validateStatus: status =>
                    status >= 200 &&
                    status < 300
            }
        );
    } catch (error) {
        throw new Error(
            getAxiosError(
                error,
                'Indexing service'
            )
        );
    }

    const submittedJob =
        response.data;

    if (
        !submittedJob ||
        !submittedJob.job_id
    ) {
        throw new Error(
            'Indexing service did not return a job_id'
        );
    }

    return submittedJob;
}

/**
 * Task 2b: get one indexing job.
 *
 * GET /v1/indexing/jobs/<job_id>
 */
async function getIndexingJob(
    indexingJobId
) {
    const statusUrl =
        `${indexingJobsUrl}/` +
        encodeURIComponent(indexingJobId);

    try {
        const response = await axios.get(
            statusUrl,
            {
                headers: {
                    'X-API-Key':
                        indexingApiKey,

                    Accept:
                        'application/json'
                },

                timeout:
                    indexingRequestTimeout,

                validateStatus: status =>
                    status >= 200 &&
                    status < 300
            }
        );

        return response.data;
    } catch (error) {
        throw new Error(
            getAxiosError(
                error,
                'Indexing status API'
            )
        );
    }
}

/**
 * Task 2c: wait until indexing completes.
 */
async function waitForIndexingJob({
    indexingJobId,
    bullJob
}) {
    const successfulStatuses =
        new Set([
            'completed',
            'succeeded',
            'success',
            'finished',
            'done'
        ]);

    const failedStatuses =
        new Set([
            'failed',
            'error',
            'cancelled',
            'canceled'
        ]);

    const startedAt = Date.now();

    let lastStatus = null;
    let lastStage = null;
    let consecutiveErrors = 0;

    while (true) {
        const elapsedTime =
            Date.now() - startedAt;

        if (
            elapsedTime >
            indexingMaximumWait
        ) {
            throw new Error(
                `Indexing job timed out after ` +
                `${indexingMaximumWait}ms: ` +
                indexingJobId
            );
        }

        let indexingJob;

        try {
            indexingJob =
                await getIndexingJob(
                    indexingJobId
                );

            consecutiveErrors = 0;
        } catch (error) {
            consecutiveErrors += 1;

            console.error(
                `Failed to check indexing status ` +
                `(${consecutiveErrors}/` +
                `${indexingMaximumStatusErrors}):`,
                error.message
            );

            if (
                consecutiveErrors >=
                indexingMaximumStatusErrors
            ) {
                throw error;
            }

            await delay(
                indexingPollInterval
            );

            continue;
        }

        const status = String(
            indexingJob?.status || ''
        )
            .trim()
            .toLowerCase();

        const stage = String(
            indexingJob?.stage || ''
        )
            .trim()
            .toLowerCase();

        if (!status) {
            throw new Error(
                `Indexing status API returned no status ` +
                `for job: ${indexingJobId}`
            );
        }

        if (
            status !== lastStatus ||
            stage !== lastStage
        ) {
            console.log(
                `Indexing job ${indexingJobId}:`,
                {
                    status,
                    stage:
                        stage || null
                }
            );

            lastStatus = status;
            lastStage = stage;
        }

        if (
            successfulStatuses.has(status)
        ) {
            return indexingJob;
        }

        if (
            failedStatuses.has(status)
        ) {
            const errorMessage =
                indexingJob.error_message ||
                indexingJob.error ||
                (
                    `Indexing job ended with ` +
                    `status: ${status}`
                );

            throw new Error(errorMessage);
        }

        if (status === 'queued') {
            await bullJob.updateProgress(82);
        } else {
            await bullJob.updateProgress(88);
        }

        await delay(
            indexingPollInterval
        );
    }
}

/**
 * Wait for chunks.json after the indexing service reports
 * successful completion.
 */
async function waitForChunksFile(
    chunksFilePath
) {
    const startedAt = Date.now();

    while (true) {
        try {
            const stats =
                await fs.promises.stat(
                    chunksFilePath
                );

            if (stats.isFile()) {
                return stats;
            }

            throw new Error(
                `Chunks path is not a file: ` +
                chunksFilePath
            );
        } catch (error) {
            if (error.code !== 'ENOENT') {
                throw error;
            }
        }

        if (
            Date.now() - startedAt >
            chunksFileWaitTimeout
        ) {
            throw new Error(
                `chunks.json was not created after indexing completed: ` +
                chunksFilePath
            );
        }

        await delay(
            chunksFilePollInterval
        );
    }
}

/**
 * Task 3: send chunks.json to the OpenSearch ingestion
 * service as multipart/form-data.
 */
async function ingestChunks({
    chunksFilePath
}) {
    const chunksStats =
        await waitForChunksFile(
            chunksFilePath
        );

    if (chunksStats.size === 0) {
        throw new Error(
            `chunks.json is empty: ${chunksFilePath}`
        );
    }

    const parameters = {
        dry_run:
            ingestDryRun,

        expected_embedding_dimensions:
            expectedEmbeddingDimensions
    };

    const form = new FormData();

    form.append(
        'payload',
        fs.createReadStream(
            chunksFilePath
        ),
        {
            filename:
                path.basename(
                    chunksFilePath
                ),

            contentType:
                'application/json',

            knownLength:
                chunksStats.size
        }
    );

    form.append(
        'parameters',
        JSON.stringify(parameters)
    );

    console.log(
        'Sending ingestion request to:',
        ingestUrl
    );

    console.log(
        'Ingestion request:',
        {
            payload:
                chunksFilePath,

            parameters
        }
    );

    try {
        const response = await axios.post(
            ingestUrl,
            form,
            {
                headers: {
                    ...form.getHeaders(),
                    Accept:
                        'application/json'
                },

                timeout:
                    ingestTimeout,

                maxBodyLength:
                    Infinity,

                maxContentLength:
                    Infinity,

                validateStatus: status =>
                    status >= 200 &&
                    status < 300
            }
        );

        return response.data;
    } catch (error) {
        throw new Error(
            getAxiosError(
                error,
                'OpenSearch ingestion service'
            )
        );
    }
}


async function updateDocumentStatus({
  documentId,
  userId,
  status,
  errorMessage = null,
}) {
  const allowedStatuses = new Set([
    "uploaded",
    "ready",
    "failed",
  ]);

  if (!allowedStatuses.has(status)) {
    throw new Error(
      `Invalid document status: ${status}`,
    );
  }

  const result = await pool.query(
    `
    UPDATE documents
    SET
      status = $1,

      processed_at = CASE
        WHEN $1 = 'ready' THEN NOW()
        ELSE NULL
      END,

      error_message = CASE
        WHEN $1 = 'failed' THEN $2
        ELSE NULL
      END

    WHERE id = $3
      AND user_id = $4
      AND deleted_at IS NULL

    RETURNING
      id,
      original_filename,
      status,
      processed_at,
      error_message
    `,
    [
      status,

      errorMessage
        ? String(errorMessage).slice(0, 5000)
        : null,

      documentId,
      userId,
    ],
  );

  if (result.rowCount === 0) {
    throw new Error(
      `Document ${documentId} was not found`,
    );
  }

  return result.rows[0];
}







const worker = new Worker(
    QUEUE_NAME,

    async job => {
        console.log(
            '--------------------------------'
        );

        console.log(
            `Processing job: ${job.id}`
        );

        console.log(
            'Job data:',
            job.data
        );

        if (
            job.name !==
            'process-document'
        ) {
            throw new Error(
                `Unknown job type: ${job.name}`
            );
        }

        const {
            documentId,
            userId,
            storageKey
        } = job.data;

        if (
            !documentId ||
            !userId ||
            !storageKey
        ) {
            throw new Error(
                'documentId, userId and storageKey are required'
            );
        }

        /*
         * Uploaded PDF:
         *
         * ../data/users/
         *   <userId>/
         *     <folderName>/
         *       example.pdf
         */
        const filePath =
            getUploadedFilePath(storageKey);

        console.log(
            'Uploaded file path:',
            filePath
        );

        let fileStats;

        try {
            fileStats =
                await fs.promises.stat(
                    filePath
                );
        } catch (error) {
            if (error.code === 'ENOENT') {
                throw new Error(
                    `Uploaded file does not exist: ` +
                    filePath
                );
            }

            throw error;
        }

        if (!fileStats.isFile()) {
            throw new Error(
                `Uploaded path is not a file: ` +
                filePath
            );
        }

        await job.updateProgress(5);

        const inputFilename =
            path.basename(filePath);

        const localDocumentDirectory =
            path.dirname(filePath);

        const paperMindFolderName =
            getPaperMindFolderName(
                inputFilename
            );

        const indexerFolderName =
            getIndexerFolderName(
                inputFilename
            );

        /*
         * Sibling output folders:
         *
         * pdfMind_example/
         * indexer_example/
         */
        const localPaperMindDirectory =
            path.join(
                localDocumentDirectory,
                paperMindFolderName
            );

        const localIndexerDirectory =
            path.join(
                localDocumentDirectory,
                indexerFolderName
            );

        /*
         * Task 1: PaperMind.
         */
        await job.updateProgress(10);

        const paperMindResult =
            await runPaperMind({
                inputFilename,
                localDocumentDirectory,
                localPaperMindDirectory,
                paperMindFolderName
            });

        console.log(
            'PaperMind completed:',
            paperMindResult
        );

        await job.updateProgress(55);

        /*
         * Task 2: indexing.
         *
         * Input:
         * pdfMind_<filename>
         *
         * Output:
         * indexer_<filename>
         */
        const indexingInputDirectory =
            getIndexerPath(
                localPaperMindDirectory,
                indexingInputMountRoot
            );

        const indexingOutputDirectory =
            getIndexerPath(
                localIndexerDirectory,
                indexingOutputMountRoot
            );

        console.log(
            'Indexer local input:',
            localPaperMindDirectory
        );

        console.log(
            'Indexer local output:',
            localIndexerDirectory
        );

        console.log(
            'Indexer request input:',
            indexingInputDirectory
        );

        console.log(
            'Indexer request output:',
            indexingOutputDirectory
        );

        await job.updateProgress(65);

        const submittedIndexingJob =
            await submitIndexingJob({
                userId,
                documentId,

                inputDirectory:
                    indexingInputDirectory,

                outputDirectory:
                    indexingOutputDirectory
            });

        console.log(
            'Indexing job submitted:',
            submittedIndexingJob
        );

        await job.updateProgress(75);

        const completedIndexingJob =
            await waitForIndexingJob({
                indexingJobId:
                    submittedIndexingJob.job_id,

                bullJob:
                    job
            });

        console.log(
            'Indexing completed successfully:',
            completedIndexingJob
        );

        /*
         * The indexer normally reports its output filename.
         * Fall back to chunks.json.
         */
        const indexingOutputFilename =
            completedIndexingJob
                ?.output_filename ||
            submittedIndexingJob
                ?.output_filename ||
            'chunks.json';

        const safeOutputFilename =
            path.basename(
                indexingOutputFilename
            );

        const chunksFilePath = path.join(
            localIndexerDirectory,
            safeOutputFilename
        );

        console.log(
            'Chunks file:',
            chunksFilePath
        );

        /*
         * Task 3: OpenSearch ingestion.
         */
        await job.updateProgress(92);

        const ingestionResult =
            await ingestChunks({
                chunksFilePath
            });

        await job.updateProgress(100);

        await updateDocumentStatus({
            documentId,
            userId,
            status: "ready",
            });

        console.log(
            'OpenSearch ingestion completed:',
            ingestionResult
        );

        console.log(
            'Entire processing pipeline completed successfully'
        );

        console.log(
            'PaperMind output:',
            localPaperMindDirectory
        );

        console.log(
            'Indexer output:',
            localIndexerDirectory
        );

        console.log(
            'Ingested chunks:',
            chunksFilePath
        );

        console.log(
            '--------------------------------'
        );

        return {
            documentId,
            userId,
            storageKey,
            inputFilename,

            paperMind: {
                folderName:
                    paperMindFolderName,

                outputDirectory:
                    localPaperMindDirectory,

                skipped:
                    paperMindResult.skipped,

                generatedEntries:
                    paperMindResult
                        .generatedEntries
            },

            indexing: {
                jobId:
                    submittedIndexingJob.job_id,

                inputDirectory:
                    localPaperMindDirectory,

                folderName:
                    indexerFolderName,

                outputDirectory:
                    localIndexerDirectory,

                chunksFilePath,

                requestPaths: {
                    inputDirectory:
                        indexingInputDirectory,

                    outputDirectory:
                        indexingOutputDirectory
                },

                submittedJob:
                    submittedIndexingJob,

                completedJob:
                    completedIndexingJob
            },

            ingestion: {
                url:
                    ingestUrl,

                chunksFilePath,

                dryRun:
                    ingestDryRun,

                expectedEmbeddingDimensions:
                    expectedEmbeddingDimensions,

                result:
                    ingestionResult
            }
        };
    },

    {
        connection:
            redisConnection,

        concurrency:
            1
    }
);

worker.on('ready', () => {
    console.log(
        `Worker is listening to queue: ` +
        QUEUE_NAME
    );
});

worker.on(
    'completed',
    (job, result) => {
        console.log(
            `Job ${job.id} completed successfully`
        );

        console.log(
            'Result:',
            result
        );
    }
);

// worker.on(
//     'failed',
//     (job, error) => {

//         console.error(
//             `Job ${job?.id || 'unknown'} failed:`,
//             error.message
//         );
//     }
// );

worker.on(
  "failed",
  async (job, error) => {
    const jobId =
      job?.id || "unknown";

    const errorMessage =
      error instanceof Error
        ? error.message
        : String(error);

    console.error(
      `Job ${jobId} failed:`,
      errorMessage,
    );

    if (!job) {
      console.error(
        "Cannot update document status because the failed job is unavailable.",
      );

      return;
    }

    const {
      documentId,
      userId,
    } = job.data || {};

    if (!documentId || !userId) {
      console.error(
        "Cannot update document status because documentId or userId is missing.",
        {
          jobId,
          documentId,
          userId,
        },
      );

      return;
    }

    /*
     * When BullMQ retries are enabled, do not mark the
     * document failed until the final attempt fails.
     */
    const maximumAttempts = Math.max(
      Number(job.opts?.attempts) || 1,
      1,
    );

    const isFinalAttempt =
      job.attemptsMade >= maximumAttempts;

    if (!isFinalAttempt) {
      console.warn(
        `Job ${jobId} will retry. Document remains uploaded.`,
        {
          attemptsMade:
            job.attemptsMade,
          maximumAttempts,
        },
      );

      return;
    }

    try {
      const updatedDocument =
        await updateDocumentStatus({
          documentId,
          userId,
          status: "failed",
          errorMessage,
        });

      console.log(
        `Document ${documentId} marked as failed.`,
        {
          status:
            updatedDocument.status,

          errorMessage:
            updatedDocument.error_message,
        },
      );
    } catch (statusError) {
      console.error(
        `Could not mark document ${documentId} as failed:`,
        statusError instanceof Error
          ? statusError.message
          : statusError,
      );
    }
  },
);

worker.on(
    'error',
    error => {
        console.error(
            'Worker error:',
            error
        );
    }
);

let isShuttingDown = false;

async function shutdown(signal) {
    if (isShuttingDown) {
        return;
    }

    isShuttingDown = true;

    console.log(
        `${signal} received. Closing worker...`
    );

    try {
        await worker.close();
        await redisConnection.quit();

        console.log(
            'Worker closed successfully'
        );

        process.exit(0);
    } catch (error) {
        console.error(
            'Failed to shut down cleanly:',
            error
        );

        process.exit(1);
    }
}

process.once(
    'SIGINT',
    () => shutdown('SIGINT')
);

process.once(
    'SIGTERM',
    () => shutdown('SIGTERM')
);