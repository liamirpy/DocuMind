import { Queue } from "bullmq";

import { createProducerRedisConnection } from "./redisConnection.js";


export const DOCUMENT_QUEUE_NAME='document-processing';
const redisConnection = createProducerRedisConnection();

export const documentQueue= new Queue(DOCUMENT_QUEUE_NAME,{
    connection: redisConnection,

    defaultJobOptions: {
        attempts: 1,
        
        backoff:{ 
        
            type: 'exponential',
        
            delay: 2000
        },

        removeOnComplete: {
            age: 24 * 60 * 60,
            count: 1000
        },

        removeOnFail: {
            age: 7 * 24 * 60 * 60,

            count: 5000
        }
    }
});


documentQueue.on('error',(error)=>{
    console.error('[Document queue] Redis error ',error)
})