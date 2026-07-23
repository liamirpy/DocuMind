import {Ollama} from "ollama";

export const OLLAMA_MODEL = 
    process.env.OLLAMA_MODEL ||
    "qwen2.5vl:7b";


export const ollamaClient= new Ollama({
    host: process.env.OLLAMA_BASE_URL ||
    "http://localhost:11434"
});


