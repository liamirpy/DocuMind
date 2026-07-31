import 'dotenv/config';

import crypto from 'node:crypto';
import express from 'express';

import {
  getPaperMindJob,
  updatePaperMindJob,
} from '../services/papermindJobStore.js';

const router = express.Router();
const backendJobIdPattern = /^[A-Za-z0-9._:-]{1,200}$/;
const allowedStatuses = new Set([
  'queued',
  'running',
  'completed',
  'failed',
]);
const terminalStatuses = new Set([
  'completed',
  'failed',
]);

function tokensMatch(receivedToken, expectedToken) {
  if (!receivedToken || !expectedToken) {
    return false;
  }

  const received = Buffer.from(receivedToken);
  const expected = Buffer.from(expectedToken);

  if (received.length !== expected.length) {
    return false;
  }

  return crypto.timingSafeEqual(received, expected);
}

router.post('/:backendJobId/status', async (request, response, next) => {
  try {
    const expectedToken = process.env.PAPERMIND_CALLBACK_TOKEN?.trim();
    const receivedToken = request.get('X-PaperMind-Callback-Token');

    if (!tokensMatch(receivedToken, expectedToken)) {
      return response.status(401).json({
        error: 'Invalid PaperMind callback token',
      });
    }

    const { backendJobId } = request.params;

    if (!backendJobIdPattern.test(backendJobId)) {
      return response.status(400).json({
        error: 'Invalid backend PaperMind job ID',
      });
    }

    const existing = await getPaperMindJob(backendJobId);

    if (!existing) {
      return response.status(404).json({
        error: 'Backend PaperMind job not found',
      });
    }

    const status = String(request.body?.status || '')
      .trim()
      .toLowerCase();

    if (!allowedStatuses.has(status)) {
      return response.status(400).json({
        error: `Invalid PaperMind status: ${status}`,
      });
    }

    // A delayed callback must not move a terminal job backwards or replace
    // one terminal outcome with another.
    if (
      terminalStatuses.has(existing.status) &&
      status !== existing.status
    ) {
      return response.status(204).end();
    }

    const rawProgress = Number(request.body?.progress);
    const progress = Number.isFinite(rawProgress)
      ? Math.min(100, Math.max(0, rawProgress))
      : existing.progress;

    await updatePaperMindJob(backendJobId, {
      agentJobId:
        request.body?.agent_job_id ||
        existing.agentJobId,
      status,
      stage: request.body?.stage || null,
      progress,
      result:
        request.body?.result === undefined
          ? existing.result
          : request.body.result,
      error:
        request.body?.error === undefined
          ? existing.error
          : request.body.error,
    });

    return response.status(204).end();
  } catch (error) {
    next(error);
  }
});

export default router;
