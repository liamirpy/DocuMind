import express from 'express';
import fs from 'fs';
import path from 'path';

import { pool } from '../db/pool.js';
import { authMiddleware } from '../middleware/authMiddleware.js';

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

function getUserDirectory(userId) {
    return path.join(
        uploadDir,
        String(userId)
    );
}

function getFolderDirectory(userId, folderName) {
    return path.join(
        getUserDirectory(userId),
        folderName
    );
}

router.post('/', async (req, res, next) => {
    const client = await pool.connect();

    let transactionStarted = false;
    let createdDirectory = false;
    let folderDirectory = null;

    try {
        const folderName = validateFolderName(
            req.body.name
        );

        if (!folderName) {
            return res.status(400).json({
                error: 'A valid folder name is required'
            });
        }

        await client.query('BEGIN');
        transactionStarted = true;

        const existingFolder =
            await client.query(
                `
                SELECT id
                FROM folders
                WHERE user_id = $1
                  AND LOWER(name) = LOWER($2)
                `,
                [req.user.id, folderName]
            );

        if (existingFolder.rowCount > 0) {
            await client.query('ROLLBACK');
            transactionStarted = false;

            return res.status(409).json({
                error:
                    'A folder with this name already exists'
            });
        }

        const result = await client.query(
            `
            INSERT INTO folders (
                user_id,
                name
            )
            VALUES ($1, $2)
            RETURNING
                id,
                user_id,
                name,
                created_at
            `,
            [req.user.id, folderName]
        );

        const folder = result.rows[0];

        folderDirectory = getFolderDirectory(
            req.user.id,
            folder.name
        );

        if (fs.existsSync(folderDirectory)) {
            await client.query('ROLLBACK');
            transactionStarted = false;

            return res.status(409).json({
                error:
                    'A physical folder with this name already exists'
            });
        }

        await fs.promises.mkdir(
            folderDirectory,
            {
                recursive: true
            }
        );

        createdDirectory = true;

        await client.query('COMMIT');
        transactionStarted = false;

        res.status(201).json({
            message: 'Folder created successfully',
            folder
        });
    } catch (error) {
        if (transactionStarted) {
            await client.query('ROLLBACK');
        }

        if (
            createdDirectory &&
            folderDirectory &&
            fs.existsSync(folderDirectory)
        ) {
            try {
                await fs.promises.rm(
                    folderDirectory,
                    {
                        recursive: true,
                        force: true
                    }
                );
            } catch (cleanupError) {
                console.error(
                    'Failed to clean up folder:',
                    cleanupError
                );
            }
        }

        if (error.code === '23505') {
            return res.status(409).json({
                error:
                    'A folder with this name already exists'
            });
        }

        next(error);
    } finally {
        client.release();
    }
});

router.get('/', async (req, res, next) => {
    try {
        const result = await pool.query(
            `
            SELECT
                f.id,
                f.name,
                f.created_at,
                COUNT(fd.document_id)::int
                    AS document_count
            FROM folders f
            LEFT JOIN folder_documents fd
              ON f.id = fd.folder_id
            WHERE f.user_id = $1
            GROUP BY
                f.id,
                f.name,
                f.created_at
            ORDER BY f.created_at DESC
            `,
            [req.user.id]
        );

        res.status(200).json({
            folders: result.rows
        });
    } catch (error) {
        next(error);
    }
});

router.get(
    '/:folderId/documents',
    async (req, res, next) => {
        try {
            const { folderId } = req.params;

            const folderResult =
                await pool.query(
                    `
                    SELECT id, name
                    FROM folders
                    WHERE id = $1
                      AND user_id = $2
                    `,
                    [
                        folderId,
                        req.user.id
                    ]
                );

            if (folderResult.rowCount === 0) {
                return res.status(404).json({
                    error: 'Folder not found'
                });
            }

            const documentsResult =
                await pool.query(
                    `
                    SELECT
                        d.id,
                        d.original_filename,
                        d.file_type,
                        d.file_size_bytes,
                        d.status,
                        d.uploaded_at
                    FROM documents d
                    JOIN folder_documents fd
                      ON fd.document_id = d.id
                    WHERE fd.folder_id = $1
                      AND d.user_id = $2
                    ORDER BY d.uploaded_at DESC
                    `,
                    [
                        folderId,
                        req.user.id
                    ]
                );

            res.status(200).json({
                folder: folderResult.rows[0],
                documents:
                    documentsResult.rows
            });
        } catch (error) {
            next(error);
        }
    }
);

router.get(
    '/:folderId',
    async (req, res, next) => {
        try {
            const { folderId } = req.params;

            const folderResult =
                await pool.query(
                    `
                    SELECT
                        id,
                        name,
                        created_at
                    FROM folders
                    WHERE id = $1
                      AND user_id = $2
                    `,
                    [
                        folderId,
                        req.user.id
                    ]
                );

            if (folderResult.rowCount === 0) {
                return res.status(404).json({
                    error: 'Folder not found'
                });
            }

            const documentsResult =
                await pool.query(
                    `
                    SELECT
                        d.id,
                        d.original_filename,
                        d.file_type,
                        d.file_size_bytes,
                        d.status,
                        d.uploaded_at
                    FROM documents d
                    JOIN folder_documents fd
                      ON d.id = fd.document_id
                    WHERE fd.folder_id = $1
                      AND d.user_id = $2
                    ORDER BY d.uploaded_at DESC
                    `,
                    [
                        folderId,
                        req.user.id
                    ]
                );

            res.status(200).json({
                folder: folderResult.rows[0],
                documents:
                    documentsResult.rows
            });
        } catch (error) {
            next(error);
        }
    }
);

router.patch(
    '/:folderId',
    async (req, res, next) => {
        const client = await pool.connect();

        let transactionStarted = false;
        let renamedDirectory = false;
        let createdNewDirectory = false;

        let oldDirectory = null;
        let newDirectory = null;

        try {
            const { folderId } = req.params;

            const newFolderName =
                validateFolderName(req.body.name);

            if (!newFolderName) {
                return res.status(400).json({
                    error:
                        'A valid folder name is required'
                });
            }

            await client.query('BEGIN');
            transactionStarted = true;

            const folderResult =
                await client.query(
                    `
                    SELECT id, name
                    FROM folders
                    WHERE id = $1
                      AND user_id = $2
                    FOR UPDATE
                    `,
                    [
                        folderId,
                        req.user.id
                    ]
                );

            if (folderResult.rowCount === 0) {
                await client.query('ROLLBACK');
                transactionStarted = false;

                return res.status(404).json({
                    error: 'Folder not found'
                });
            }

            const currentFolder =
                folderResult.rows[0];

            if (
                currentFolder.name ===
                newFolderName
            ) {
                await client.query('ROLLBACK');
                transactionStarted = false;

                return res.status(200).json({
                    message:
                        'Folder name has not changed',
                    folder: currentFolder
                });
            }

            const duplicateResult =
                await client.query(
                    `
                    SELECT id
                    FROM folders
                    WHERE user_id = $1
                      AND LOWER(name) = LOWER($2)
                      AND id != $3
                    `,
                    [
                        req.user.id,
                        newFolderName,
                        folderId
                    ]
                );

            if (duplicateResult.rowCount > 0) {
                await client.query('ROLLBACK');
                transactionStarted = false;

                return res.status(409).json({
                    error:
                        'A folder with this name already exists'
                });
            }

            const documentsResult =
                await client.query(
                    `
                    SELECT
                        d.id,
                        d.storage_key
                    FROM documents d
                    JOIN folder_documents fd
                      ON fd.document_id = d.id
                    WHERE fd.folder_id = $1
                      AND d.user_id = $2
                    FOR UPDATE OF d
                    `,
                    [
                        folderId,
                        req.user.id
                    ]
                );

            oldDirectory = getFolderDirectory(
                req.user.id,
                currentFolder.name
            );

            newDirectory = getFolderDirectory(
                req.user.id,
                newFolderName
            );

            if (fs.existsSync(newDirectory)) {
                await client.query('ROLLBACK');
                transactionStarted = false;

                return res.status(409).json({
                    error:
                        'A physical folder with this name already exists'
                });
            }

            if (fs.existsSync(oldDirectory)) {
                await fs.promises.rename(
                    oldDirectory,
                    newDirectory
                );

                renamedDirectory = true;
            } else {
                if (
                    documentsResult.rowCount > 0
                ) {
                    throw new Error(
                        'The physical folder is missing'
                    );
                }

                await fs.promises.mkdir(
                    newDirectory,
                    {
                        recursive: true
                    }
                );

                createdNewDirectory = true;
            }

            const updatedFolderResult =
                await client.query(
                    `
                    UPDATE folders
                    SET
                        name = $1,
                        updated_at = NOW()
                    WHERE id = $2
                      AND user_id = $3
                    RETURNING
                        id,
                        name,
                        created_at,
                        updated_at
                    `,
                    [
                        newFolderName,
                        folderId,
                        req.user.id
                    ]
                );

            for (
                const document
                of documentsResult.rows
            ) {
                const normalisedStorageKey =
                    document.storage_key.replace(
                        /\\/g,
                        '/'
                    );

                const filename =
                    path.posix.basename(
                        normalisedStorageKey
                    );

                const newStorageKey = [
                    String(req.user.id),
                    newFolderName,
                    filename
                ].join('/');

                await client.query(
                    `
                    UPDATE documents
                    SET storage_key = $1
                    WHERE id = $2
                      AND user_id = $3
                    `,
                    [
                        newStorageKey,
                        document.id,
                        req.user.id
                    ]
                );
            }

            await client.query('COMMIT');
            transactionStarted = false;

            res.status(200).json({
                message:
                    'Folder updated successfully',
                folder:
                    updatedFolderResult.rows[0]
            });
        } catch (error) {
            if (transactionStarted) {
                await client.query('ROLLBACK');
            }

            try {
                if (
                    renamedDirectory &&
                    newDirectory &&
                    oldDirectory &&
                    fs.existsSync(newDirectory) &&
                    !fs.existsSync(oldDirectory)
                ) {
                    await fs.promises.rename(
                        newDirectory,
                        oldDirectory
                    );
                }

                if (
                    createdNewDirectory &&
                    newDirectory &&
                    fs.existsSync(newDirectory)
                ) {
                    await fs.promises.rm(
                        newDirectory,
                        {
                            recursive: true,
                            force: true
                        }
                    );
                }
            } catch (cleanupError) {
                console.error(
                    'Failed to restore folder:',
                    cleanupError
                );
            }

            if (error.code === '23505') {
                return res.status(409).json({
                    error:
                        'A folder with this name already exists'
                });
            }

            next(error);
        } finally {
            client.release();
        }
    }
);

router.delete(
    '/:folderId',
    async (req, res, next) => {
        const client = await pool.connect();

        let transactionStarted = false;
        let removedDirectory = false;
        let folderDirectory = null;

        try {
            const { folderId } = req.params;

            await client.query('BEGIN');
            transactionStarted = true;

            const folderResult =
                await client.query(
                    `
                    SELECT id, name
                    FROM folders
                    WHERE id = $1
                      AND user_id = $2
                    FOR UPDATE
                    `,
                    [
                        folderId,
                        req.user.id
                    ]
                );

            if (folderResult.rowCount === 0) {
                await client.query('ROLLBACK');
                transactionStarted = false;

                return res.status(404).json({
                    error: 'Folder not found'
                });
            }

            const folder =
                folderResult.rows[0];

            const documentCountResult =
                await client.query(
                    `
                    SELECT
                        COUNT(*)::int
                            AS document_count
                    FROM folder_documents
                    WHERE folder_id = $1
                      AND user_id = $2
                    `,
                    [
                        folderId,
                        req.user.id
                    ]
                );

            if (
                documentCountResult.rows[0]
                    .document_count > 0
            ) {
                await client.query('ROLLBACK');
                transactionStarted = false;

                return res.status(409).json({
                    error:
                        'The folder must be empty before it can be deleted'
                });
            }

            folderDirectory =
                getFolderDirectory(
                    req.user.id,
                    folder.name
                );

            if (fs.existsSync(folderDirectory)) {
                try {
                    await fs.promises.rmdir(
                        folderDirectory
                    );

                    removedDirectory = true;
                } catch (filesystemError) {
                    if (
                        filesystemError.code ===
                        'ENOTEMPTY'
                    ) {
                        await client.query(
                            'ROLLBACK'
                        );

                        transactionStarted = false;

                        return res.status(409).json({
                            error:
                                'The physical folder is not empty'
                        });
                    }

                    throw filesystemError;
                }
            }

            await client.query(
                `
                DELETE FROM folders
                WHERE id = $1
                  AND user_id = $2
                `,
                [
                    folderId,
                    req.user.id
                ]
            );

            await client.query('COMMIT');
            transactionStarted = false;

            res.status(200).json({
                message:
                    'Folder deleted successfully'
            });
        } catch (error) {
            if (transactionStarted) {
                await client.query('ROLLBACK');
            }

            if (
                removedDirectory &&
                folderDirectory &&
                !fs.existsSync(folderDirectory)
            ) {
                try {
                    await fs.promises.mkdir(
                        folderDirectory,
                        {
                            recursive: true
                        }
                    );
                } catch (cleanupError) {
                    console.error(
                        'Failed to restore folder:',
                        cleanupError
                    );
                }
            }

            next(error);
        } finally {
            client.release();
        }
    }
);

export default router;