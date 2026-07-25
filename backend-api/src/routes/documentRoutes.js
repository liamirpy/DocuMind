import express from 'express';
import multer from 'multer';
import path from 'path';
import fs from 'fs';
import crypto from 'crypto';

import { pool } from '../db/pool.js';
import { authMiddleware } from '../middleware/authMiddleware.js';
import { documentQueue } from '../queues/documentQueue.js';

const router = express.Router();

router.use(authMiddleware);

const uploadDir = path.resolve(
    process.env.UPLOAD_DIR || 'src/uploads'
);

fs.mkdirSync(uploadDir, { recursive: true });

function validateFolderName(value) {
    if (typeof value !== 'string') {
        return null;
    }

    const folderName = value.trim().normalize('NFC');

    if (
        !folderName ||
        folderName.length > 100 ||
        folderName === '.' ||
        folderName === '..' ||
        /[<>:"/\\|?*\u0000-\u001F]/.test(folderName) ||
        /[. ]$/.test(folderName)
    ) {
        return null;
    }

    const reservedNames =
        /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$/i;

    if (reservedNames.test(folderName)) {
        return null;
    }

    return folderName;
}

function sanitizeFilename(value) {
    const originalName = path
        .basename(value)
        .trim()
        .normalize('NFC');

    const safeFilename = originalName
        .replace(/[<>:"/\\|?*\u0000-\u001F]/g, '_')
        .replace(/[. ]+$/g, '');

    if (
        !safeFilename ||
        safeFilename === '.' ||
        safeFilename === '..'
    ) {
        throw new Error('Invalid filename');
    }

    return safeFilename;
}

function getFolderDirectory(userId, folderName) {
    return path.join(
        uploadDir,
        String(userId),
        folderName
    );
}

function getAbsoluteStoragePath(storageKey) {
    const absolutePath = path.resolve(
        uploadDir,
        storageKey
    );

    const uploadRoot = `${uploadDir}${path.sep}`;

    if (
        absolutePath !== uploadDir &&
        !absolutePath.startsWith(uploadRoot)
    ) {
        throw new Error('Invalid storage path');
    }

    return absolutePath;
}

function getFileType(filename) {
    const lowerName = filename.toLowerCase();

    if (lowerName.endsWith('.nii.gz')) {
        return 'nii.gz';
    }

    const extension = path
        .extname(lowerName)
        .replace('.', '');

    const allowedTypes = [
        'pdf',
        'txt',
        'json',
        'nii'
    ];

    if (!allowedTypes.includes(extension)) {
        return null;
    }

    return extension;
}

function getSha256Hash(filePath) {
    const fileBuffer = fs.readFileSync(filePath);

    return crypto
        .createHash('sha256')
        .update(fileBuffer)
        .digest('hex');
}

async function loadUploadFolder(req, res, next) {
    try {
        const folderName = validateFolderName(
            req.params.folderName
        );

        if (!folderName) {
            return res.status(400).json({
                error: 'A valid folder name is required'
            });
        }

        const result = await pool.query(
            `
            SELECT id, name
            FROM folders
            WHERE user_id = $1
              AND name = $2
            `,
            [req.user.id, folderName]
        );

        if (result.rowCount === 0) {
            return res.status(404).json({
                error: 'Folder not found'
            });
        }

        const folder = result.rows[0];

        const folderDirectory = getFolderDirectory(
            req.user.id,
            folder.name
        );

        if (
            fs.existsSync(folderDirectory) &&
            !fs.statSync(folderDirectory).isDirectory()
        ) {
            return res.status(409).json({
                error: 'The folder path is not a directory'
            });
        }

        await fs.promises.mkdir(folderDirectory, {
            recursive: true
        });

        req.uploadFolder = folder;
        req.uploadDirectory = folderDirectory;

        next();
    } catch (error) {
        next(error);
    }
}

const storage = multer.diskStorage({
    destination: (req, file, cb) => {
        cb(null, req.uploadDirectory);
    },

    filename: (req, file, cb) => {
        try {
            const safeFilename = sanitizeFilename(
                file.originalname
            );

            const finalPath = path.join(
                req.uploadDirectory,
                safeFilename
            );

            if (fs.existsSync(finalPath)) {
                const error = new Error(
                    'A file with this name already exists in this folder'
                );

                error.code = 'FILE_ALREADY_EXISTS';

                return cb(error);
            }

            // The file is stored using its original name.
            // No date or timestamp is added.
            cb(null, safeFilename);
        } catch (error) {
            cb(error);
        }
    }
});

const upload = multer({
    storage,

    limits: {
        fileSize: 10 * 1024 * 1024
    },

    fileFilter: (req, file, cb) => {
        const fileType = getFileType(
            file.originalname
        );

        if (!fileType) {
            const error = new Error(
                'Invalid file type. Allowed types: pdf, txt, json, nii, nii.gz'
            );

            error.code = 'INVALID_FILE_TYPE';

            return cb(error);
        }

        cb(null, true);
    }
});

function uploadSingleFile(req, res, next) {
    upload.single('file')(req, res, error => {
        if (!error) {
            return next();
        }

        if (error.code === 'FILE_ALREADY_EXISTS') {
            return res.status(409).json({
                error: error.message
            });
        }

        if (error.code === 'INVALID_FILE_TYPE') {
            return res.status(400).json({
                error: error.message
            });
        }

        if (
            error instanceof multer.MulterError &&
            error.code === 'LIMIT_FILE_SIZE'
        ) {
            return res.status(413).json({
                error: 'File is too large. Maximum size is 10 MB'
            });
        }

        next(error);
    });
}

router.post(
    '/upload/:folderName',
    loadUploadFolder,
    uploadSingleFile,
    async (req, res, next) => {
        const client = await pool.connect();

        let transactionStarted = false;
        let transactionCommitted = false;

        try {
            if (!req.file) {
                return res.status(400).json({
                    error: 'No file uploaded'
                });
            }

            const folder = req.uploadFolder;

            const fileType = getFileType(
                req.file.originalname
            );

            const sha256Hash = getSha256Hash(
                req.file.path
            );

            const storageKey = path
                .relative(uploadDir, req.file.path)
                .replace(/\\/g, '/');

            await client.query('BEGIN');
            transactionStarted = true;

            const folderResult = await client.query(
                `
                SELECT id, name
                FROM folders
                WHERE id = $1
                  AND user_id = $2
                  AND name = $3
                FOR SHARE
                `,
                [
                    folder.id,
                    req.user.id,
                    folder.name
                ]
            );

            if (folderResult.rowCount === 0) {
                await client.query('ROLLBACK');
                transactionStarted = false;

                await fs.promises.rm(req.file.path, {
                    force: true
                });

                return res.status(404).json({
                    error: 'Folder not found'
                });
            }

            const documentResult = await client.query(
                `
                INSERT INTO documents (
                    user_id,
                    original_filename,
                    file_type,
                    mime_type,
                    storage_key,
                    file_size_bytes,
                    sha256_hash,
                    status,
                    uploaded_at
                )
                VALUES (
                    $1,
                    $2,
                    $3,
                    $4,
                    $5,
                    $6,
                    $7,
                    'uploaded',
                    NOW()
                )
                RETURNING
                    id,
                    public_id,
                    user_id,
                    original_filename,
                    file_type,
                    mime_type,
                    file_size_bytes,
                    status,
                    uploaded_at
                `,
                [
                    req.user.id,
                    req.file.originalname,
                    fileType,
                    req.file.mimetype,
                    storageKey,
                    req.file.size,
                    sha256Hash
                ]
            );

            const document =
                documentResult.rows[0];

            await client.query(
                `
                INSERT INTO folder_documents (
                    folder_id,
                    document_id,
                    user_id
                )
                VALUES ($1, $2, $3)
                `,
                [
                    folder.id,
                    document.id,
                    req.user.id
                ]
            );

            await client.query('COMMIT');

            transactionStarted = false;
            transactionCommitted = true;

            const responseBody = {
                document: {
                    ...document,
                    folder_id: folder.id,
                    folder_name: folder.name
                }
            };

            if (fileType === 'pdf') {
                try {
                    const job =
                        await documentQueue.add(
                            'process-document',
                            {
                                documentId:
                                    document.id,
                                userId:
                                    req.user.id,
                                storageKey,
                                originalFilename:
                                    req.file.originalname,
                                mimetype:
                                    req.file.mimetype
                            },
                            {
                                jobId:
                                    `document-${document.id}`
                            }
                        );

                    responseBody.processing_job = {
                        id: job.id,
                        name: job.name,
                        status: 'queued'
                    };
                } catch (queueError) {
                    console.error(
                        'Failed to queue document:',
                        queueError
                    );

                    responseBody.processing_job = {
                        status: 'queue_failed'
                    };
                }
            }

            res.status(201).json(responseBody);
        } catch (error) {
            if (transactionStarted) {
                await client.query('ROLLBACK');
            }

            if (
                !transactionCommitted &&
                req.file?.path &&
                fs.existsSync(req.file.path)
            ) {
                await fs.promises.rm(req.file.path, {
                    force: true
                });
            }

            if (error.code === '23505') {
                return res.status(409).json({
                    error: 'This document already exists'
                });
            }

            next(error);
        } finally {
            client.release();
        }
    }
);

router.get('/', async (req, res, next) => {
    try {
        const result = await pool.query(
            `
            SELECT
                id,
                public_id,
                original_filename,
                file_type,
                mime_type,
                file_size_bytes,
                title,
                page_count,
                status,
                uploaded_at,
                processed_at
            FROM documents
            WHERE user_id = $1
              AND status != 'deleted'
            ORDER BY uploaded_at DESC
            `,
            [req.user.id]
        );

        res.json(result.rows);
    } catch (error) {
        next(error);
    }
});

router.get(
    '/:documentId/download',
    async (req, res, next) => {
        try {
            const { documentId } = req.params;

            const result = await pool.query(
                `
                SELECT
                    id,
                    original_filename,
                    mime_type,
                    storage_key
                FROM documents
                WHERE id = $1
                  AND user_id = $2
                  AND status != 'deleted'
                `,
                [documentId, req.user.id]
            );

            if (result.rowCount === 0) {
                return res.status(404).json({
                    error: 'Document not found'
                });
            }

            const document = result.rows[0];

            const filePath = getAbsoluteStoragePath(
                document.storage_key
            );

            if (!fs.existsSync(filePath)) {
                return res.status(404).json({
                    error: 'File not found on server'
                });
            }

            res.setHeader(
                'Content-Type',
                document.mime_type ||
                    'application/octet-stream'
            );

            res.download(
                filePath,
                document.original_filename
            );
        } catch (error) {
            next(error);
        }
    }
);

router.get(
    '/:documentId',
    async (req, res, next) => {
        try {
            const { documentId } = req.params;

            const result = await pool.query(
                `
                SELECT
                    id,
                    public_id,
                    original_filename,
                    file_type,
                    mime_type,
                    file_size_bytes,
                    title,
                    page_count,
                    status,
                    uploaded_at,
                    processed_at
                FROM documents
                WHERE id = $1
                  AND user_id = $2
                `,
                [documentId, req.user.id]
            );

            if (result.rowCount === 0) {
                return res.status(404).json({
                    error: 'Document not found'
                });
            }

            const foldersResult =
                await pool.query(
                    `
                    SELECT f.id, f.name
                    FROM folders f
                    JOIN folder_documents fd
                      ON fd.folder_id = f.id
                    WHERE fd.document_id = $1
                      AND f.user_id = $2
                    `,
                    [
                        documentId,
                        req.user.id
                    ]
                );

            res.json({
                document: {
                    ...result.rows[0],
                    folders: foldersResult.rows
                }
            });
        } catch (error) {
            next(error);
        }
    }
);

router.delete(
    '/:documentId',
    async (req, res, next) => {
        const client = await pool.connect();

        let transactionStarted = false;

        try {
            const { documentId } = req.params;

            await client.query('BEGIN');
            transactionStarted = true;

            const result = await client.query(
                `
                SELECT
                    id,
                    original_filename,
                    storage_key
                FROM documents
                WHERE id = $1
                  AND user_id = $2
                FOR UPDATE
                `,
                [documentId, req.user.id]
            );

            if (result.rowCount === 0) {
                await client.query('ROLLBACK');
                transactionStarted = false;

                return res.status(404).json({
                    error: 'Document not found'
                });
            }

            const document = result.rows[0];

            const filePath = getAbsoluteStoragePath(
                document.storage_key
            );

            await client.query(
                `
                DELETE FROM folder_documents
                WHERE document_id = $1
                  AND user_id = $2
                `,
                [documentId, req.user.id]
            );

            await client.query(
                `
                DELETE FROM documents
                WHERE id = $1
                  AND user_id = $2
                `,
                [documentId, req.user.id]
            );

            if (fs.existsSync(filePath)) {
                await fs.promises.rm(filePath, {
                    force: true
                });
            }

            await client.query('COMMIT');
            transactionStarted = false;

            res.status(200).json({
                message:
                    'Document deleted successfully'
            });
        } catch (error) {
            if (transactionStarted) {
                await client.query('ROLLBACK');
            }

            next(error);
        } finally {
            client.release();
        }
    }
);

export default router;