export async function embedQuestion(question) {
    const normalizedQuestion = question?.trim();

    if (!normalizedQuestion) {
        const error = new Error("Question is required");
        error.statusCode = 400;
        throw error;
    };
    console.log(process.env.INDEXER_BASE_URL)
    const baseUrl = (process.env.INDEXER_BASE_URL ||
        "http://localhost:8000"
    ).replace(/\/$/, "");


    const headers = {
        "content-type": "application/json",
    }

    if (process.env.INDEXER_API_KEY) {
        headers["X-API-Key"] = process.env.INDEXER_API_KEY;
    }

    let response;

    try {
        response = await fetch(`${baseUrl}/v1/embeddings/query`,
            {
                method: "POST",
                headers,
                body: JSON.stringify({
                    query_text: normalizedQuestion
                }),
                signal: AbortSignal.timeout(30_000)
            }
        );
    } catch (cause) {
        console.log('ffff')
        const error = new Error(`Could not connect to the indexer embedding service: ${cause.message}`);
        error.statusCode=500;
        throw error;
    }

    if(!response.ok){
        const responseText=
          await response.text();
        const error= new Error(`Embedding service failed with status ${response.status}:${responseText}`);
        error.statusCode=502;
        throw error; 
    }

    const data= await response.json();

    const expectedDimensions= Number(
        process.env.EMEDDING_DIMENSIONS ||
        1024
    );

    if(!Array.isArray(data.embedding)){
        const error = new Error("Embedding service retured an invalid embedding");
        error.statusCode=502;
        throw error;
    }

    if (
        data.embedding.length !== expectedDimensions ||
        data.dimensions !== expectedDimensions
    ){
        const error = new Error(`Embedding dimension mismatch. Expected ${expectedDimensions}, received ${data.embedding.length}`)
        error.statusCode=502;
        throw error;
    }


    return {
        embedding: data.embedding,
        model: data.model,
        dimensions:data.dimensions
    }


}