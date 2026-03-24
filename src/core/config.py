import os
from typing import List
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../../config/.env'))

class Config:
    # Vector Database
    COLLECTION_NAME    = "faq_collection"
    PERSIST_DIRECTORY  = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../chroma_db'))
    EMBEDDING_MODEL    = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2")

    # LLM Settings
    GROQ_API_KEY       = os.getenv("GROQ_API_KEY")
    LLM_MODEL          = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
    LLM_TEMPERATURE    = 0.1

    # Chunking Settings
    CHUNK_SIZE         = 512    # tokens
    CHUNK_OVERLAP      = 50     # tokens
    USE_TOKEN_CHUNKING = True

    # Retrieval Settings
    USE_METADATA_FILTERING = True
    RETRIEVAL_THRESHOLD    = 0.3
    TOP_AREAS              = 3
    TOP_K_PER_AREA         = 2

    # Response Settings
    USE_JSON_RESPONSES = True

    @classmethod
    def validate(cls):
        if not cls.GROQ_API_KEY:
            raise ValueError("GROQ_API_KEY is missing from environment/config")

    @classmethod
    def get_pdf_paths(cls) -> List[str]:
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data'))
        if not os.path.exists(data_dir):
            return []
        return [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith('.pdf')]
