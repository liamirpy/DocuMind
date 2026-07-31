import "dotenv/config";

import {
  createStateRedisConnection,
} from "../queues/redisConnection.js";

let redisConnection = null;

const parsedTtlSeconds =
  Number.parseInt(
    process.env.PAPERMIND_JOB_TTL_SECONDS ||
      "86400",
    10,
  );

const jobTtlSeconds =
  Number.isInteger(parsedTtlSeconds) &&
  parsedTtlSeconds > 0
    ? parsedTtlSeconds
    : 86400;

function getRedisConnection() {
  if (
    !redisConnection ||
    redisConnection.status === "end"
  ) {
    redisConnection =
      createStateRedisConnection();
  }

  return redisConnection;
}

function getJobKey(backendJobId) {
  return `papermind:job:${backendJobId}`;
}

function stringifyResult(value) {
  if (
    value === undefined ||
    value === null
  ) {
    return "";
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
  return Object.entries(fields)
    .flatMap(([key, value]) => [
      key,
      value === undefined ||
      value === null
        ? ""
        : String(value),
    ]);
}

function hasOwn(object, property) {
  return Object.prototype.hasOwnProperty.call(
    object,
    property,
  );
}

export async function createPaperMindJob({
  backendJobId,
  bullJobId,
  documentId,
  userId,
}) {
  const redis =
    getRedisConnection();

  const now =
    new Date().toISOString();

  const key =
    getJobKey(backendJobId);

  await redis.hset(
    key,
    ...flattenFields({
      backend_job_id:
        backendJobId,

      bull_job_id:
        bullJobId,

      document_id:
        documentId,

      user_id:
        userId,

      agent_job_id:
        "",

      status:
        "queued",

      stage:
        "queued",

      progress:
        0,

      result:
        "",

      error:
        "",

      created_at:
        now,

      updated_at:
        now,
    }),
  );

  await redis.expire(
    key,
    jobTtlSeconds,
  );

  return getPaperMindJob(
    backendJobId,
  );
}

/*
 * Used by documentProcessorWorker when a previous
 * PaperMind attempt failed.
 *
 * The backend job ID remains unchanged, but the old
 * agent job ID and terminal failure information are
 * cleared so a new agent job can be submitted.
 */
export async function resetPaperMindJob(
  backendJobId,
) {
  const existing =
    await getPaperMindJob(
      backendJobId,
    );

  if (!existing) {
    return null;
  }

  return updatePaperMindJob(
    backendJobId,
    {
      agentJobId:
        null,

      status:
        "queued",

      stage:
        "queued",

      progress:
        0,

      result:
        null,

      error:
        null,
    },
  );
}

export async function updatePaperMindJob(
  backendJobId,
  changes,
) {
  const redis =
    getRedisConnection();

  const key =
    getJobKey(backendJobId);

  const fields = {
    updated_at:
      new Date().toISOString(),
  };

  /*
   * Support both camelCase calls from the worker and
   * snake_case calls from other backend components.
   */
  if (
    hasOwn(changes, "agentJobId") ||
    hasOwn(changes, "agent_job_id")
  ) {
    const value =
      hasOwn(changes, "agentJobId")
        ? changes.agentJobId
        : changes.agent_job_id;

    fields.agent_job_id =
      value || "";
  }

  if (hasOwn(changes, "status")) {
    fields.status =
      changes.status || "";
  }

  if (hasOwn(changes, "stage")) {
    fields.stage =
      changes.stage || "";
  }

  if (hasOwn(changes, "progress")) {
    const progress =
      Number(changes.progress);

    fields.progress =
      Number.isFinite(progress)
        ? Math.min(
            100,
            Math.max(0, progress),
          )
        : 0;
  }

  if (hasOwn(changes, "result")) {
    fields.result =
      stringifyResult(
        changes.result,
      );
  }

  if (hasOwn(changes, "error")) {
    fields.error =
      changes.error || "";
  }

  await redis.hset(
    key,
    ...flattenFields(fields),
  );

  await redis.expire(
    key,
    jobTtlSeconds,
  );

  return getPaperMindJob(
    backendJobId,
  );
}

export async function getPaperMindJob(
  backendJobId,
) {
  const redis =
    getRedisConnection();

  const record =
    await redis.hgetall(
      getJobKey(backendJobId),
    );

  if (!record.backend_job_id) {
    return null;
  }

  return {
    backendJobId:
      record.backend_job_id,

    bullJobId:
      record.bull_job_id ||
      null,

    documentId:
      record.document_id ||
      null,

    userId:
      record.user_id ||
      null,

    agentJobId:
      record.agent_job_id ||
      null,

    status:
      record.status ||
      "queued",

    stage:
      record.stage ||
      null,

    progress:
      Number(record.progress) ||
      0,

    result:
      parseResult(
        record.result,
      ),

    error:
      record.error ||
      null,

    createdAt:
      record.created_at ||
      null,

    updatedAt:
      record.updated_at ||
      null,
  };
}

export async function closePaperMindJobStore() {
  const connection =
    redisConnection;

  redisConnection = null;

  if (
    !connection ||
    connection.status === "end"
  ) {
    return;
  }

  try {
    await connection.quit();
  } catch (error) {
    console.warn(
      "[Redis:papermind-state] " +
        "Graceful shutdown failed:",
      error.message,
    );

    connection.disconnect();
  }
}