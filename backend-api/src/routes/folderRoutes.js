import express from 'express';
import { pool } from '../db/pool.js';

import { authMiddleware } from '../middleware/authMiddleware.js';

const router = express.Router();
router.use(authMiddleware);


router.post('/', async (req, res,next ) => {
    try {
        const {name} = req.body;

        if (!name) {
            return res.status(400).json({ error: 'Folder name is required' });
        }

        const result= await pool.query(
           `INSERT INTO folders (user_id,name)
            VALUES ($1,$2)
            RETURNING id, user_id, name,created_at`,
            [req.user.id, name]
        );

        res.status(201).json({
            message: 'Folder created successfully',
            folder: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});



router.get('/',async (req, res,next) => {
    try {
        const result = await pool.query(
            `
            SELECT 
            f.id,
            f.name,
            f.created_at,
            COUNT(fd.document_id)::int AS document_count
            FROM folders f
            LEFT JOIN folder_documents fd ON f.id = fd.folder_id
            WHERE f.user_id = $1
            GROUP BY f.id, f.name, f.created_at
            ORDER BY f.created_at DESC  
            `,
            [req.user.id]
        );

        res.status(200).json({
            folders: result.rows
        });
    }   catch (error) {
        next(error);
    }
});


router.get('/:folderID', async (req, res,next) => {
    try {
        const { folderID } = req.params;

        const folderResult = await pool.query(
            `
            SELECT id,name, created_at
            FROM folders
            WHERE id = $1 AND user_id = $2
            `,
            [folderID, req.user.id]
        );

        if (folderResult.rowCount === 0) {
            return res.status(404).json({ error: 'Folder not found' });
        }


        const documentsResult = await pool.query(
            `
        SELECT 
            d.id,
            d.original_filename,
            d.file_type,
            d.file_size_bytes,
            d.status,
            d.uploaded_at
        FROM documents d
        JOIN folder_documents fd ON d.id = fd.document_id
        WHERE fd.folder_id = $1 
        AND d.user_id = $2
        ORDER BY d.uploaded_at DESC
            `,
            [folderID, req.user.id]
        );

        res.status(200).json({
            folder: folderResult.rows[0],
            documents: documentsResult.rows
        });
    } catch (error) {
        next(error);
    }
}); 

router.patch('/:folderId', async (req, res,next) => {
    try {
        const { folderId } = req.params;
        const { name } = req.body;

        if (!name) {
            return res.status(400).json({ error: 'Folder name is required' });
        }

        const result = await pool.query(
            `
            UPDATE folders
            SET name = $1,
                updated_at = NOW()
            WHERE id = $2
             AND user_id = $3
            RETURNING id, name, created_at, updated_at
            `,
            [name, folderId, req.user.id]
        );

        if (result.rowCount === 0) {
            return res.status(404).json({ error: 'Folder not found' });
        }

        res.status(200).json({
            message: 'Folder updated successfully',
            folder: result.rows[0]
        });
    } catch (error) {
        next(error);
    }
});

router.delete('/:folderId', async (req, res,next) => {
    try {
        const { folderId } = req.params;

        const result = await pool.query(
            `
            DELETE FROM folders
            WHERE id = $1 AND user_id = $2
            RETURNING id
            `,
            [folderId, req.user.id]
        );

        if (result.rowCount === 0) {
            return res.status(404).json({ error: 'Folder not found' });
        }

        res.status(200).json({
            message: 'Folder deleted successfully'
        });
    } catch (error) {
        next(error);
    }
});

router.get("/:folderId/documents", async (req, res, next) => {
  try {
    const { folderId } = req.params;

    const folderResult = await pool.query(
      `
      SELECT id, name
      FROM folders
      WHERE id = $1
        AND user_id = $2
      `,
      [folderId, req.user.id]
    );

    if (folderResult.rowCount === 0) {
      return res.status(404).json({
        error: "Folder not found"
      });
    }

    const documentsResult = await pool.query(
      `
      SELECT
        d.id,
        d.original_filename,
        d.file_type,
        d.file_size_bytes,
        d.status,
        d.uploaded_at
      FROM documents d
      JOIN folder_documents fd ON fd.document_id = d.id
      WHERE fd.folder_id = $1
        AND d.user_id = $2
      ORDER BY d.uploaded_at DESC
      `,
      [folderId, req.user.id]
    );

    res.json({
      folder: folderResult.rows[0],
      documents: documentsResult.rows
    });
  } catch (error) {
    next(error);
  }
});

export default router;