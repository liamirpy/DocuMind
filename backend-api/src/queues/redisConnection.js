import 'dotenv/config';
import IORedis from 'ioredis';

const configuredRedisUrl = process.env.REDIS_URL?.trim();
const redisHost = process.env.REDIS_HOST?.trim() || '127.0.0.1';
const redisPort = process.env.REDIS_PORT?.trim() || '6379';
const redisUrl = configuredRedisUrl || `redis://${redisHost}:${redisPort}`;

function addConnectionLogging(connection, connectionName) {
  connection.on('connect', () => {
    console.log(`[Redis:${connectionName}] Connected`);
  });

  connection.on('ready', () => {
    console.log(`[Redis:${connectionName}] Ready`);
  });

  connection.on('error', (error) => {
    console.error(`[Redis:${connectionName}] Error:`, error.message);
  });

  connection.on('close', () => {
    console.warn(`[Redis:${connectionName}] Connection closed`);
  });

  return connection;
}

export function createProducerRedisConnection() {
  return addConnectionLogging(
    new IORedis(redisUrl, {
      maxRetriesPerRequest: 1,
      enableReadyCheck: true,
    }),
    'producer',
  );
}

export function createWorkerRedisConnection() {
  return addConnectionLogging(
    new IORedis(redisUrl, {
      maxRetriesPerRequest: null,
      enableReadyCheck: true,
    }),
    'worker',
  );
}

export function createStateRedisConnection() {
  return addConnectionLogging(
    new IORedis(redisUrl, {
      maxRetriesPerRequest: 3,
      enableReadyCheck: true,
    }),
    'papermind-state',
  );
}
