from langchain_huggingface import HuggingFaceEmbeddings
from src.core.config import Config

def get_embedding_model():
    return HuggingFaceEmbeddings(model_name=Config.EMBEDDING_MODEL)
