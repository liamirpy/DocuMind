import 'dotenv/config';

import {
  createStateRedisConnection,
} from '../queues/redisConnection.js';

const redis = createStateRedisConnection();

const parsedTtl = Number.parseInt(
  process.env.PAPERMIND_JOB_TTL_SECONDS || '86400',
  10,
);

const jobTtlSeconds =
  Number.isInteger(parsedTtl) && parsedTtl > 0
    ? parsedTtl
    : 86400;

function getJobKey(backendJobId) {
  return `papermind:job:${backendJobId}`;
}

function stringifyResult(value) {
  if (value === undefined || value === null) {
    return '';
  }

  return JSON.stringify(value);
}

function parseResult(value) {
  if (!value) {
    return null;
  }

  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function flattenFields(fields) {
  return Object.entries(fields).flatMap(([key, value]) => [key, String(value)]);
}

export async function createPaperMindJob({
  backendJobId,
  bullJobId,
  documentId,
  userId,
}) {
  const now = new Date().toISOString();
  const key = getJobKey(backendJobId);

  await redis.hset(
    key,
    ...flattenFields({
      backend_job_id: backendJobId,
      bull_job_id: bullJobId,
      document_id: documentId,
      user_id: userId,
      agent_job_id: '',
      status: 'queued',
      stage: 'queued',
      progress: '0',
      result: '',
      error: '',
      created_at: now,
      updated_at: now,
    }),
  );

  await redis.expire(key, jobTtlSeconds);
  return getPaperMindJob(backendJobId);
}

export async function resetPaperMindJob(backendJobId) {
  const existing = await getPaperMindJob(backendJobId);

  if (!existing) {
    return null;
  }

  return updatePaperMindJob(backendJobId, {
    agentJobId: null,
    status: 'queued',
    stage: 'queued',
    progress: 0,
    result: null,
    error: null,
  });
}

export async function updatePaperMindJob(
  backendJobId,
  changes,
) {
  const key = getJobKey(backendJobId);
  const fields = {
    updated_at: new Date().toISOString(),
  };

  if (changes.agentJobId !== undefined) {
    fields.agent_job_id = changes.agentJobId || '';
  }
  if (changes.status !== undefined) {
    fields.status = changes.status || '';
  }
  if (changes.stage !== undefined) {
    fields.stage = changes.stage || '';
  }
  if (changes.progress !== undefined) {
    fields.progress = Number.isFinite(Number(changes.progress))
      ? String(changes.progress)
      : '0';
  }
  if (changes.result !== undefined) {
    fields.result = stringifyResult(changes.result);
  }
  if (changes.error !== undefined) {
    fields.error = changes.error || '';
  }

  await redis.hset(key, ...flattenFields(fields));
  await redis.expire(key, jobTtlSeconds);

  return getPaperMindJob(backendJobId);
}

export async function getPaperMindJob(backendJobId) {
  const record = await redis.hgetall(getJobKey(backendJobId));

  if (!record.backend_job_id) {
    return null;
  }

  return {
    backendJobId: record.backend_job_id,
    bullJobId: record.bull_job_id,
    documentId: record.document_id,
    userId: record.user_id,
    agentJobId: record.agent_job_id || null,
    status: record.status || 'queued',
    stage: record.stage || null,
    progress: Number(record.progress) || 0,
    result: parseResult(record.result),
    error: record.error || null,
    createdAt: record.created_at,
    updatedAt: record.updated_at,
  };
}

export async function closePaperMindJobStore() {
  if (redis.status === 'end') {
    return;
  }

  try {
    await redis.quit();
  } catch {
    redis.disconnect();
  }
}
