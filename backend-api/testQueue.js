import { documentQueue } from './src/queues/documentQueue.js';

async function testQueue() {
    try {
        await documentQueue.waitUntilReady();

        console.log('Queue connected to Redis successfully');

        const job = await documentQueue.add('test-job', {
            message: 'Redis queue is working'
        });

        console.log('Test job created:', job.id);
    } catch (error) {
        console.error('Queue test failed:', error);
    } finally {
        await documentQueue.close();
        process.exit();
    }
}

testQueue();