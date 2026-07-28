import express from "express";
import {pool} from "../db/pool.js";
import {authMiddleware} from "../middleware/authMiddleware.js";
import { retrieveRagContext } from "../services/ragSearchService.js";

import { generateRagAnswer } from "../services/llmService.js";






const router =
  express.Router();


router.use(
  authMiddleware
);


function createConversationTitle(question) {
  const normalized = question.trim().replace(/\s+/g, " ");
  const maximumLength = 60;

  if (normalized.length <= maximumLength) {
    return normalized;
  }

  return `${normalized.slice(0, maximumLength - 3).trimEnd()}...`;
}




router.use(authMiddleware);



router.post(
  "/search",

  async (
    req,
    res,
    next
  ) => {
    try {
      const {
        question,
        documentId,
        conversationId
      } = req.body;


      if (
          conversationId !== undefined &&
          conversationId !== null &&
          typeof conversationId !== "string"
        ) {
          return res.status(400).json({
            error: "conversationId must be a string"
          });
        }

      const normalizedQuestion = question.trim();


      if (conversationId) {
          const conversationResult = await pool.query(
            `
            SELECT id
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
        }


      if (
        typeof question !==
          "string" ||

        !question.trim()
      ) {
        return res
          .status(400)

          .json({
            error:
              "Question is required"
          });
      }


      if (
        question.length >
        10_000
      ) {
        return res
          .status(400)

          .json({
            error:
              "Question is too long"
          });
      }


      const documentIds = [];


      if (documentId) {
        const documentResult =
          await pool.query(
            `
            SELECT id

            FROM documents

            WHERE id = $1

              AND user_id = $2

              AND status != 'deleted'
            `,

            [
              documentId,

              req.user.id
            ]
          );


        if (
          documentResult
            .rowCount === 0
        ) {
          return res
            .status(404)

            .json({
              error:
                "Document not found"
            });
        }


        documentIds.push(
          String(documentId)
        );
      }


      const result = await retrieveRagContext({
        question: normalizedQuestion,
        userId: String(req.user.id),
        documentIds
      });

      const llAnswer = await generateRagAnswer({
        question: normalizedQuestion,
        context: result.context
      });


      const client = await pool.connect();

      let savedConversation;
      let savedUserMessage;
      let savedAssistantMessage;

      try {
        await client.query("BEGIN");

        if (conversationId) {
          const existingConversation = await client.query(
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
            FOR UPDATE
            `,
            [conversationId, req.user.id]
          );

          if (existingConversation.rowCount === 0) {
            const error = new Error("Conversation not found");
            error.statusCode = 404;
            throw error;
          }

          savedConversation = existingConversation.rows[0];
        } else {
          const createdConversation = await client.query(
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
            [
              req.user.id,
              createConversationTitle(normalizedQuestion)
            ]
          );

          savedConversation = createdConversation.rows[0];
        }

        const userMessageResult = await client.query(
          `
          INSERT INTO messages (
            conversation_id,
            user_id,
            role,
            content
          )
          VALUES ($1, $2, 'user', $3)
          RETURNING
            id,
            public_id,
            role,
            content,
            model,
            token_count,
            created_at
          `,
          [
            savedConversation.id,
            req.user.id,
            normalizedQuestion
          ]
        );

        savedUserMessage = userMessageResult.rows[0];

        const assistantContent =
          typeof llAnswer === "string"
            ? llAnswer
            : llAnswer.answer;

        if (!assistantContent) {
          throw new Error("The LLM returned an empty answer");
        }

        const assistantMessageResult = await client.query(
          `
          INSERT INTO messages (
            conversation_id,
            user_id,
            role,
            content,
            model,
            token_count
          )
          VALUES ($1, $2, 'assistant', $3, $4, $5)
          RETURNING
            id,
            public_id,
            role,
            content,
            model,
            token_count,
            created_at
          `,
          [
            savedConversation.id,
            req.user.id,
            assistantContent,
            typeof llAnswer === "object"
              ? llAnswer.model || null
              : null,
            typeof llAnswer === "object"
              ? llAnswer.usage?.totalTokens ?? null
              : null
          ]
        );

        savedAssistantMessage = assistantMessageResult.rows[0];

        const updatedConversation = await client.query(
          `
          UPDATE conversations
          SET updated_at = NOW()
          WHERE id = $1
            AND user_id = $2
          RETURNING
            id,
            public_id,
            title,
            created_at,
            updated_at
          `,
          [savedConversation.id, req.user.id]
        );

        savedConversation = updatedConversation.rows[0];

        await client.query("COMMIT");
      } catch (error) {
        await client.query("ROLLBACK");
        throw error;
      } finally {
        client.release();
      }


      res.status(200).json({
        answer: llAnswer,
        result,
        conversation: savedConversation,
        messages: {
          user: savedUserMessage,
          assistant: savedAssistantMessage
        }
      });

    } catch (error) {
      next(error);
    }
  }
);


export default router;




// curl \
//   -X POST \
//   http://localhost:8001/api/rag/search \
//   \
//   -H "Content-Type: application/json" \
//   \
//   -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
//   \
//   -d '{
//     "question": "What are the main findings of the document?"
//   }'


// curl \
//   -X POST \
//   http://localhost:8001/api/rag/search \
//   \
//   -H "Content-Type: application/json" \
//   \
//   -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
//   \
//   -d '{
//     "question": "What methodology was used?",

//     "documentId": "YOUR-DOCUMENT-ID"
//   }'