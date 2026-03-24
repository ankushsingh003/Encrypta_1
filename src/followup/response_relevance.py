import numpy as np
from src.core.embeddings import get_embedding_model

class ResponseRelevanceChecker:
    def __init__(self, similarity_threshold: float = 0.3):
        self.embedding_model = get_embedding_model()
        self.similarity_threshold = similarity_threshold

    def check_relevance(self, original_query: str, user_response: str, followup_question: str = None) -> Tuple[bool, float]:
        query_emb = np.array(self.embedding_model.embed_query(original_query))
        resp_emb = np.array(self.embedding_model.embed_query(user_response))
        
        sim_query = self._cosine_similarity(query_emb, resp_emb)
        
        if followup_question:
            fu_emb = np.array(self.embedding_model.embed_query(followup_question))
            sim_fu = self._cosine_similarity(fu_emb, resp_emb)
            final_sim = max(sim_query, sim_fu)
        else:
            final_sim = sim_query
            
        return final_sim >= self.similarity_threshold, final_sim

    def _cosine_similarity(self, a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
