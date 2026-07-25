import IORedis from "ioredis";

const redisUrl = `redis://${process.env.REDIS_HOST}:${process.env.REDIS_PORT}` || 'redis://127.0.0.1:6379';
// const redisUrl =  'redis://127.0.0.1:6379';

console.log(redisUrl)

function addConnectionLogging(connection,connectionName){
    connection.on('connect',()=>{
        console.log(`[Redis:${connectionName} Connected]`)
    });

    connection.on('ready',()=>{
        console.log(`[Redis:${connectionName}] Ready`)
    });

    connection.on('error',(error)=> {
        console.log(`[Redis:${connectionName}] Error:`, error.message)

    });

    connection.on('close',()=>{
        console.warn(`[Redis:${connectionName}] Connection closed`)
    });


    return connection;

}


export function createProducerRedisConnection(){
    const connection= new IORedis(redisUrl,{
        maxRetriesPerRequest:1, 
        enableReadyCheck: true
    });
    return addConnectionLogging(connection,'producer')
}


export function createWorkerRedisConnection(){
    const connection= new IORedis(redisUrl,{
        maxRetriesPerRequest: null,
        enableReadyCheck: true
    });

    return addConnectionLogging(connection,'Worker')
}