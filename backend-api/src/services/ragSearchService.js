// import { opensearchClient,OPENSEARCH_INDEX } from "../config/opensearchClient.js";
import { response } from "express";
// import { OPENSEARCH_INDEX, opensearchClient } from "../config/opensearchClient";
import { embedQuestion } from "./embeddingService.js";


process.env.OPENSEARCH_NODE="https://localhost:9200"
process.env.OPENSEARCH_USERNAME="admin"
process.env.OPENSEARCH_PASSWORD="DOCUMIND_opensearch_password_2026"
process.env.OPENSEARCH_TLS_REJECT_UNAUTHORIZED = "false";

const { OPENSEARCH_INDEX, opensearchClient }= await import( "../config/opensearchClient.js");



const SOURCE_FIELDS= [
    "user_id",

    "document_id",
    "document_public_id",

    "chunk_id",
    "chunk_index",
    "chunk_role",

    "parent_chunk_id",

    "source_type",

    "document_title",

    "original_filename",

    "section_path_text",

    "page_start",
    "page_end",

    "content",
    "retrieval_text",

    "caption",
    "summary",

    "details"

];

function createFilters({
  userId,
  documentIds = [],
  retrieveOnly = true,
}) {
  const filters = [
    {
      term: {
        user_id: String(userId),
      },
    },
  ];

  if (retrieveOnly) {
    filters.push({
      term: {
        retrieval_enabled: true,
      },
    });
  }

  if (documentIds.length > 0) {
    filters.push({
      terms: {
        document_id: documentIds.map(String),
      },
    });
  }

  return filters;
}

async function vectorSearch({
    vector,
    userId,
    documentIds,
    candidateK
}) {

    const response = 
    await opensearchClient.search({

        index: OPENSEARCH_INDEX,

        body: {
            size: candidateK,

            _source: SOURCE_FIELDS,

            query: {
                knn:{
                    embedding: {
                        vector,
                        k: candidateK,

                        filter: {
                            bool:{
                                filter: createFilters({
                                    userId,
                                    documentIds,
                                    retrieveOnly: true
                                })
                            }
                        }
                    }
                }
            }
        }
    });

return (response.body.hits?.hits || []);

}


async function lexialSearch({
    question,
    userId,
    documentIds,
    candidateK
}){
    const response = 
    await opensearchClient.search({
        index: OPENSEARCH_INDEX,

        body:{
            size: candidateK,
            _source: SOURCE_FIELDS,

            query: {
                bool: {
                    filter: createFilters({
                        userId,
                        documentIds,
                        retrieveOnly: true
                    }),
                    must: [
                        {multi_match: {
                            query: question,
                            type: "best_fields",
                            fields: [
                                "retrieval_text^3",
                                "document_title^2",
                                "section_path_text^2",

                                "caption^2",

                                "summary^2",
                                "content"
                                ]
                            }
                        }
                    ]

                }
            }
        }
    });

    return (
        response.body.hits?.hits || []
    );
}

function reciprocalRankFusion({
    vectorHits,
    lexialHits,
    limit,
    rrfk=60,
    vectorWeight =1,
    lexicalWeight = 0.7
}){
    const fused = new Map();

    function addHits(
        hits,
        searchType,
        weight
    ){
        hits.forEach((hit,index) => {
            const source=
                hit._source || {};
            
            const key =
                source.chunk_id ||
                hit._id;
            
            const current = 
            fused.get(key) || {
                hit,
                rrfScore: 0 ,
                matchTypes: [],
                vectorScore: null,
                lexicalScore : null
            };

            current.rrfScore +=
            weight / 
            (rrfk + index +1)

            if (!current.matchTypes.includes(searchType)){
                current.matchTypes.push(searchType)
            }

            if (searchType =='vector'){
                current.vectorScore = hit.__source;
            }else { 
                current.lexicalScore = hit._score;
            }

            fused.set(
                key,
                current
            );
            
        });
    }
    addHits(
        vectorHits,
        "vector",
        vectorWeight
    );
    addHits(
        lexialHits,
        "lexial",
        lexicalWeight
    )

    return [...fused.values()]
    .sort(
        (a,b) =>
            b.rrfScore - a.rrfScore
    )
    .slice(0,limit);

}


async function localParentChunks({parentChunkIds,userId,documentIds}){

        if (parentChunkIds.length==0){
            return new Map();
        }
        const filters = 
        createFilters({
            userId,
            documentIds,
            retrieveOnly: false
        });

        filters.push({
            terms: {
                chunk_id: parentChunkIds
            }
        });

        const response= 
        await opensearchClient.search({
            index: OPENSEARCH_INDEX,
            body:{
                size: parentChunkIds.length,

                _source:
                    SOURCE_FIELDS,

                query: {
                    bool: {
                        filter: filters
                    }
                }
            }
        });


        return new Map(
        (
            response.body.hits?.hits || []

        ).map((hit) => [
            hit._source.chunk_id,
            hit._source

        ])
    );
}



function chooseContextText(source){

    return (
        source.content ||
        source.retrieval_text ||
        source.summary ||
        source.caption ||
        ""
    ).trim()

}


function formatLocation(source){
    if (source.page_start ==null){
        return null
    }

    if(source.page_end==null || source.page_end === source.page_start){
        return (`page ${source.page_start}`);
    }

    


    return (
        `pages`+
        `${source.page_start}-` +
        `${source.page_end}`
    )
}


function buildContext(
    items,
    maxContexChars
){

    const contextBlocks=[];

    const sources=[];

    let usedCharacters=0;

    for (
        const item of items
    ){

    const citationId= 
        `S${sources.length + 1}`

    const source= 
        item.contextSource;
    
    const text = chooseContextText(source);

    if(!text){ continue };

    const metadataLines=[
        `[${citationId}]`,
        
        `Document: ${
            source.document_title ||
            source.original_filename ||
            "Untitled document"
        }`,

        source.section_path_text
        ? `Section : ${
            source.section_path_text
        }`
        : null,

        formatLocation(source)
        ? `Location: ${ formatLocation(source) }`
        : null,


        source.source_type
        ? `Section Type: ${ source.source_type}`
        : null,


        "Content:"
    ].filter(Boolean);


    const header= 
    `${metadataLines.join(
        "\n"
    )}\n`;

    const seperatorLength = 
    contextBlocks.length > 0 
    ? 2
    : 0 ;

    const remaining= 
    maxContexChars -
    usedCharacters - 
    header.length - 
    seperatorLength;

    if (remaining<200){
        break;
    }
    
    const finalText = text.length > remaining
    ? `${
        text.slice(
            0,
            Math.max(
                0, remaining -20
            )
        )
    } \n [truncated]`

    :text;

    const block= `${header}${finalText}`

    contextBlocks.push(block);

    usedCharacters +=
    block.length + 
    seperatorLength;


    const source_details= source.details?.source_locations?.[0]?.bbox
    ? source.details?.source_locations?.[0]?.bbox
    : "not available"



    sources.push({
        citationId,

        documentId:
            source.document_id,
        
        documentPublicId:
            source.document_public_id || null,

        
        title:
            source.document_title ||
            null,

        filename:
            source.original_filename ||
            null,

        section:
            source.section_path_text ||
            null,

        pageStart:
            source.page_start ??
            null,

        pageEnd:
            source.page_end ??
            null,

        sourceType:
            source.source_type ||
            null,

        
        matchedChunkId:
            item.matchedSource.chunk_id,

        
        contextChunkId:
            item.matchedSource.chunk_id,

        usedParentContext:
            item.matchedSource.chunk_id !==source.chunk_id,

        
        matchTypes:
            item.matchTypes,

        
        bbox:
            source_details,
        
        
        retrievalScore:
            item.rrfScore,

    });
    }

    return{
        context: contextBlocks.join("\n\n"),

        sources
    };
}

export async function retrieveRagContext({
    question,
    userId,
    documentIds=[],

    candidateK = Number(
        process.env.RAG_CANDIDATE_K || 30
    ),

    topK= Number(
        process.env.RAG_TOP_K ||
        8
    ),

    maxContexChars = Number(
        process.env.RAG_MAX_CONTEXT_CHARS ||
        18_000
    )
}){

    const {embedding,model,dimensions} = await embedQuestion(question);


    const[vectorHits,lexialHits]= await Promise.all([

        vectorSearch({
            vector: embedding,
            userId,
            documentIds,
            candidateK
        }),

        lexialSearch({
            question,
            userId,
            documentIds,
            candidateK
        })
    ]);

    const fusedHits = reciprocalRankFusion({
        vectorHits,
        lexialHits,
        limit: Math.max(topK * 3, topK)
    });


    const parentChunkIds=[
        ...new Set(
            fusedHits.map(({hit})=> hit._source?.parent_chunk_id)
        .filter(Boolean)
        )
    ];

    const parentChunks= 
        await localParentChunks({
            parentChunkIds,
            userId,
            documentIds
        });

// here we find the parent of 
// child if exist if not we using that child,
//  and if parent exist we use parent and remove the child 
// (because that child text exist in that parents)

    const deduplicatedContexts= 
        new Map();

    for (const fusedHit of fusedHits){

        const matchedSource=
            fusedHit.hit._source;
        
        const parentSource = matchedSource.parent_chunk_id  //(resut=condition   ?iftrue :if false)

        ? parentChunks.get(matchedSource.parent_chunk_id)

        : null;

        const contextSource = parentSource || matchedSource;

        // But still its possible that two same parent exist (duplicated)

        const contextKey= contextSource.chunk_id;

        const existing= deduplicatedContexts.get(contextKey);

        if (!existing || fusedHit.rrfScore > existing.rrfScore){

            deduplicatedContexts.set(
                contextKey,
                {
                    ...fusedHit,

                    matchedSource,

                    contextSource
                }
            );
        }

    }


    const selectedItems= [ 
        ...deduplicatedContexts.values()
    ].sort((a,b)=> b.rrfScore - a.rrfScore).slice(0,topK);


    // console.dir(selectedItems, {
    //     depth: null,
    // });


    const {context, sources} = buildContext(selectedItems,maxContexChars)
        
    console.dir(sources, {
            depth: null,
        });


}



















// LEXIAL SERACH

// try {
//   const textSearch = await lexialSearch({
//     question: "S TROKE is a leading cause of disability and mortality worldwide ",
//     userId: "user_123",
//     documentIds: ["doc_456"],
//     candidateK: 5,
//   });

//   console.dir(textSearch, {
//     depth: null,
//   });
// } catch (error) {
//   console.error("Search failed:", error);
// }


// Vector SERACH

// async function embedingQuestion(question) {
//   try {
//     const result = await embedQuestion(question);

//     return result.embedding;
//   } catch (error) {
//     console.error("Status:", error.statusCode);
//     console.error("Message:", error.message);

//     throw error;
//   }
// }

// try {
//   const embeded_question =
//     await embedingQuestion("what is stroke?");

//   const textSearch = await vectorSearch({
//     vector: embeded_question,
//     userId: "user_123",
//     documentIds: ["doc_456"],
//     candidateK: 5,
//   });

//   console.dir(textSearch, {
//     depth: null,
//   });
// } catch (error) {
//   console.error("Search failed:", error);
// }





// combine lexical and vector and ranking 


try {

    const textSearch = await lexialSearch({
        question: "S TROKE is a leading cause of disability and mortality worldwide ",
        userId: "user_123",
        documentIds: ["doc_456"],
        candidateK: 5,
    });



  async function embedingQuestion(question) {
  try {
    const result = await embedQuestion(question);

    return result.embedding;
  } catch (error) {
    console.error("Status:", error.statusCode);
    console.error("Message:", error.message);

    throw error;
  }
}



  const embeded_question =
    await embedingQuestion("what is stroke?");

  const vectorSearchoutput = await vectorSearch({
    vector: embeded_question,
    userId: "user_123",
    documentIds: ["doc_456"],
    candidateK: 5,
  });


//   console.dir(vectorSearchoutput, {
//     depth: null,
//   });

const ranking= await reciprocalRankFusion({
    vectorHits: vectorSearchoutput,
    lexialHits: textSearch,
    limit: 5,
    rrfk: 60,
    vectorWeight: 1,
    lexicalWeight: 0.7
})

//  console.dir(ranking[0], {
//     depth: null,
//   });


const finalbag= retrieveRagContext({
    question:"What is the Stroke?",
    userId: "user_123",
    documentIds: ["doc_456"],
    candidateK:30 ,

    topK:5,
    })




}catch (error) {
  console.error("Search failed:", error);
}

















// Create Filter 


// const filters = createFilters({
//   userId: 123,
//   documentIds: ["1", "2"],
//   retrieveOnly: true,
// });

// console.log(filters);

// console.log(JSON.stringify(filters, null, 2));
