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

const uploadDir = process.env.UPLOAD_DIR || 'src/uploads';

function getFileType(filename) {
    const lowerName = filename.toLowerCase();

    if (lowerName.endsWith('.nii.gz')) {
        return 'nii.gz';
    }

    const extension = path.extname(lowerName).replace('.', '');

    const allowedTypes = ['pdf', 'txt', 'json', 'nii'];

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





if (!fs.existsSync(uploadDir)) {
    fs.mkdirSync(uploadDir, { recursive: true });
}

const storage = multer.diskStorage({
    destination: (req, file, cb) => {
        const userDir = path.join(uploadDir, req.user.id.toString());
        if (!fs.existsSync(userDir)) {
            fs.mkdirSync(userDir, { recursive: true });
        }
        cb(null, userDir); 
    },
    filename: function (req, file, cb) {
    const safeOriginalName = file.originalname.replace(/[^a-zA-Z0-9._-]/g, "_");
    const uniqueName = `${Date.now()}-${safeOriginalName}`;

    cb(null, uniqueName);
  }
});

const upload = multer({ storage: storage,
    limits: { fileSize: 10 * 1024 * 1024 }, // 10 MB limit
});


router.post('/upload', upload.single('file'), async (req, res, next) => {
    const client = await pool.connect();

    try {
        const { folder_id } = req.body;


        if(!folder_id){
            return res.status(400).json({error: "You have to define the folder"})
        }

        if (!req.file) {
            return res.status(400).json({ error: 'No file uploaded' });
        }

        const fileType = getFileType(req.file.originalname);

        if (!fileType) {
            fs.unlinkSync(req.file.path);

            return res.status(400).json({
                error: 'Invalid file type. Allowed types: pdf, txt, json, nii, nii.gz'
            });
        }

        const sha256Hash = getSha256Hash(req.file.path);

        const storageKey = path
            .relative(uploadDir, req.file.path)
            .replace(/\\/g, '/');

        await client.query('BEGIN');

        if (folder_id) {
            const folderResult = await client.query(
                `
                SELECT id
                FROM folders
                WHERE id = $1 AND user_id = $2
                `,
                [folder_id, req.user.id]
            );

            if (folderResult.rows.length === 0) {
                await client.query('ROLLBACK');

                fs.unlinkSync(req.file.path);

                return res.status(404).json({ error: 'Folder not found' });
            }
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
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'uploaded', NOW())
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

        const document = documentResult.rows[0];

        if (folder_id) {
            await client.query(
                `
                INSERT INTO folder_documents (folder_id, document_id,user_id)
                VALUES ($1, $2, $3)
                `,
                [folder_id, document.id, req.user.id]
            );
        }

        await client.query('COMMIT');

        if (fileType=='pdf'){
            const job= await documentQueue.add(
                'process-document',
                {
                    documentId: document.id,
                    userId: req.user.id,
                    storageKey,
                    originalFilename: req.file.originalname,
                    mimetype: req.file.mimetype
                },
                {
                jobId: `document-${document.id}`
                }
            );

            res.status(201).json({
                    document: {
                        ...document,
                        folder_id: folder_id || null
                    },
                    processing_job: {
                        id: job.id,
                        name: job.name,
                        status: 'queued'
                    }
                });
        }
        else{


        res.status(201).json({
            document: {
                ...document,
                folder_id: folder_id || null
            }
        });


        }

    } catch (error) {
        await client.query('ROLLBACK');

        if (req.file?.path && fs.existsSync(req.file.path)) {
            fs.unlinkSync(req.file.path);
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
});


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


router.get('/:documentId', async (req, res, next) => {
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
            WHERE id = $1 AND user_id = $2
            `,
            [documentId, req.user.id]
        );

        if (result.rowCount === 0) {
            return res.status(404).json({ error: 'Document not found' });
        }

            const foldersResult = await pool.query(
      `
      SELECT f.id, f.name
      FROM folders f
      JOIN folder_documents fd ON fd.folder_id = f.id
      WHERE fd.document_id = $1
        AND f.user_id = $2
      `,
      [documentId, req.user.id]
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
});

router.get('/:documentId/download', async (req, res, next) => {
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
            return res.status(404).json({ error: 'Document not found' });
        }

        const document = result.rows[0];

        const filePath = path.join(uploadDir, document.storage_key);

        if (!fs.existsSync(filePath)) {
            return res.status(404).json({ error: 'File not found on server' });
        }

        res.setHeader('Content-Type', document.mime_type || 'application/octet-stream');

        res.download(filePath, document.original_filename);
    } catch (error) {
        next(error);
    }
});

router.delete('/:documentId', async (req, res, next) => {
    const client = await pool.connect();

    try {
        const { documentId } = req.params;

        await client.query('BEGIN');

        const result = await client.query(
            `
            SELECT
                id,
                original_filename,
                storage_key
            FROM documents
            WHERE id = $1
              AND user_id = $2
            `,
            [documentId, req.user.id]
        );

        if (result.rowCount === 0) {
            await client.query('ROLLBACK');

            return res.status(404).json({ error: 'Document not found' });
        }

        const document = result.rows[0];

        const filePath = path.join(uploadDir, document.storage_key);

        await client.query(
            `
            DELETE FROM folder_documents
            WHERE document_id = $1
            `,
            [documentId]
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
            fs.unlinkSync(filePath);
        }

        await client.query('COMMIT');

        res.status(200).json({
            message: 'Document deleted successfully'
        });
    } catch (error) {
        await client.query('ROLLBACK');
        next(error);
    } finally {
        client.release();
    }
});



export default router;