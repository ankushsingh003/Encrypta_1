from langchain_community.vectorstores import Chroma
from src.core.config import Config
from src.core.embeddings import get_embedding_model
from src.core.logging_config import logger

class RetrievalService:
    def __init__(self):
        self.embeddings = get_embedding_model()
        self.vectorstore = Chroma(
            persist_directory=Config.PERSIST_DIRECTORY,
            embedding_function=self.embeddings,
            collection_name=Config.COLLECTION_NAME
        )

    def retrieve_documents(self, query: str, top_k: int = 6):
        logger.info(f"Retrieving documents for query: {query}")
        # Perform standard similarity search for now
        # Metadata-based filtering could be added here if needed
        docs_with_score = self.vectorstore.similarity_search_with_relevance_scores(query, k=top_k)
        
        if not docs_with_score:
            return [], False, 0.0
        
        top_score = docs_with_score[0][1]
        meets_threshold = top_score >= Config.RETRIEVAL_THRESHOLD
        
        return docs_with_score, meets_threshold, top_score

def get_retriever():
    return RetrievalService()
