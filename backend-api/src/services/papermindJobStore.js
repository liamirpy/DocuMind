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
  Number.isFinite(parsedTtlSeconds) &&
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

function parseJson(value) {
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
  const values = [];

  for (const [field, value] of Object.entries(fields)) {
    values.push(
      field,
      value === null || value === undefined
        ? ""
        : String(value),
    );
  }

  return values;
}

export async function createPaperMindJob({
  backendJobId,
  bullJobId,
  documentId,
  userId,
}) {
  const redis =
    getRedisConnection();

  const key =
    getJobKey(backendJobId);

  const now =
    new Date().toISOString();

  await redis.hset(
    key,
    ...flattenFields({
      backend_job_id: backendJobId,
      bull_job_id: bullJobId,
      document_id: documentId,
      user_id: userId,
      agent_job_id: "",
      status: "submitting",
      stage: "",
      progress: 0,
      result: "",
      error: "",
      created_at: now,
      updated_at: now,
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

  for (
    const [field, value]
    of Object.entries(changes)
  ) {
    if (value === undefined) {
      continue;
    }

    if (field === "result") {
      fields.result =
        value === null
          ? ""
          : JSON.stringify(value);

      continue;
    }

    fields[field] =
      value === null
        ? ""
        : value;
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
      record.bull_job_id || null,

    documentId:
      record.document_id || null,

    userId:
      record.user_id || null,

    agentJobId:
      record.agent_job_id || null,

    status:
      record.status || null,

    stage:
      record.stage || null,

    progress:
      Number(record.progress) || 0,

    result:
      parseJson(record.result),

    error:
      record.error || null,

    createdAt:
      record.created_at || null,

    updatedAt:
      record.updated_at || null,
  };
}

export async function closePaperMindJobStore() {
  const connection =
    redisConnection;

  redisConnection = null;

  if (!connection) {
    return;
  }

  if (connection.status === "end") {
    return;
  }

  try {
    if (
      connection.status === "ready" ||
      connection.status === "connect"
    ) {
      await connection.quit();
    } else {
      connection.disconnect();
    }
  } catch (error) {
    console.warn(
      "[Redis:papermind-state] Graceful shutdown failed:",
      error.message,
    );

    connection.disconnect();
  }
}