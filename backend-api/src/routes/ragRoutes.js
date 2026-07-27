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

        documentId
      } = req.body;


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


      const result =
        await retrieveRagContext({
          question:
            question.trim(),

          userId:
            String(
              req.user.id
            ),

          documentIds
        });


        const ll_answer =  await generateRagAnswer({
            question: question.trim(),
            context: result.context
        })


      res
        .status(200)

        .json({
            answer: ll_answer,
            result: result
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