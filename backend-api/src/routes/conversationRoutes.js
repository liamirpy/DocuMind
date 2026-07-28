import express from "express";

import { pool } from "../db/pool.js";
import { authMiddleware } from "../middleware/authMiddleware.js";

const router = express.Router();

router.use(authMiddleware);

function normalizeTitle(value) {
  if (typeof value !== "string") {
    return null;
  }

  const title = value.trim().replace(/\s+/g, " ");

  if (!title || title.length > 160) {
    return null;
  }

  return title;
}

/*
 * GET /api/conversations
 *
 * Return all active conversations belonging to the
 * currently authenticated user.
 */
router.get("/", async (req, res, next) => {
  try {
    const result = await pool.query(
      `
      SELECT
        c.id,
        c.public_id,
        c.title,
        c.created_at,
        c.updated_at,

        (
          SELECT COUNT(*)::integer
          FROM messages count_messages
          WHERE count_messages.conversation_id = c.id
            AND count_messages.user_id = c.user_id
        ) AS message_count,

        (
          SELECT latest_message.content
          FROM messages latest_message
          WHERE latest_message.conversation_id = c.id
            AND latest_message.user_id = c.user_id
          ORDER BY
            latest_message.created_at DESC,
            latest_message.id DESC
          LIMIT 1
        ) AS last_message

      FROM conversations c

      WHERE c.user_id = $1
        AND c.deleted_at IS NULL

      ORDER BY c.updated_at DESC
      `,
      [req.user.id]
    );

    res.status(200).json({
      conversations: result.rows
    });
  } catch (error) {
    next(error);
  }
});

/*
 * POST /api/conversations
 *
 * Creating conversations directly is optional because
 * the RAG endpoint will also create one automatically.
 */
router.post("/", async (req, res, next) => {
  try {
    const suppliedTitle = req.body?.title;

    const title =
      suppliedTitle == null
        ? "New conversation"
        : normalizeTitle(suppliedTitle);

    if (!title) {
      return res.status(400).json({
        error: "Title must be between 1 and 160 characters"
      });
    }

    const result = await pool.query(
      `
      INSERT INTO conversations (
        user_id,
        title
      )
      VALUES ($1, $2)

      RETURNING
        id,
        public_id,
        title,
        created_at,
        updated_at
      `,
      [req.user.id, title]
    );

    res.status(201).json({
      conversation: result.rows[0]
    });
  } catch (error) {
    next(error);
  }
});

/*
 * GET /api/conversations/:conversationId
 *
 * Return one conversation and its complete message history.
 */
router.get("/:conversationId", async (req, res, next) => {
  try {
    const { conversationId } = req.params;

    const conversationResult = await pool.query(
      `
      SELECT
        id,
        public_id,
        title,
        created_at,
        updated_at

      FROM conversations

      WHERE id = $1
        AND user_id = $2
        AND deleted_at IS NULL
      `,
      [conversationId, req.user.id]
    );

    if (conversationResult.rowCount === 0) {
      return res.status(404).json({
        error: "Conversation not found"
      });
    }

    const messagesResult = await pool.query(
      `
      SELECT
        id,
        public_id,
        role,
        content,
        model,
        token_count,
        created_at

      FROM messages

      WHERE conversation_id = $1
        AND user_id = $2

      ORDER BY
        created_at ASC,
        id ASC
      `,
      [conversationId, req.user.id]
    );

    res.status(200).json({
      conversation: conversationResult.rows[0],
      messages: messagesResult.rows
    });
  } catch (error) {
    next(error);
  }
});

/*
 * PATCH /api/conversations/:conversationId
 *
 * Rename a conversation.
 */
router.patch("/:conversationId", async (req, res, next) => {
  try {
    const { conversationId } = req.params;
    const title = normalizeTitle(req.body?.title);

    if (!title) {
      return res.status(400).json({
        error: "Title must be between 1 and 160 characters"
      });
    }

    const result = await pool.query(
      `
      UPDATE conversations

      SET title = $1

      WHERE id = $2
        AND user_id = $3
        AND deleted_at IS NULL

      RETURNING
        id,
        public_id,
        title,
        created_at,
        updated_at
      `,
      [title, conversationId, req.user.id]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({
        error: "Conversation not found"
      });
    }

    res.status(200).json({
      conversation: result.rows[0]
    });
  } catch (error) {
    next(error);
  }
});

/*
 * DELETE /api/conversations/:conversationId
 *
 * Soft-delete the conversation.
 */
router.delete("/:conversationId", async (req, res, next) => {
  try {
    const { conversationId } = req.params;

    const result = await pool.query(
      `
      UPDATE conversations

      SET deleted_at = NOW()

      WHERE id = $1
        AND user_id = $2
        AND deleted_at IS NULL

      RETURNING id
      `,
      [conversationId, req.user.id]
    );

    if (result.rowCount === 0) {
      return res.status(404).json({
        error: "Conversation not found"
      });
    }

    res.status(200).json({
      message: "Conversation deleted successfully"
    });
  } catch (error) {
    next(error);
  }
});

export default router;