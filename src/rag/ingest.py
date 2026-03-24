import os
from langchain_community.document_loaders import PyMuPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from src.core.config import Config
from src.core.embeddings import get_embedding_model
from src.core.logging_config import logger

def load_and_split_pdfs(paths: list, chunk_size=512, chunk_overlap=50):
    all_chunks = []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False
    )
    
    for path in paths:
        if not os.path.exists(path):
            logger.warning(f"File not found: {path}")
            continue
        logger.info(f"Processing {path}...")
        loader = PyMuPDFLoader(path)
        docs = loader.load()
        chunks = splitter.split_documents(docs)
        for chunk in chunks:
            # Assign area metadata if possible, else default to 'general'
            filename = os.path.basename(path).lower()
            if 'password' in filename:
                chunk.metadata['area'] = 'password_manager'
            elif 'getting_started' in filename:
                chunk.metadata['area'] = 'general'
            else:
                chunk.metadata['area'] = 'account'
        all_chunks.extend(chunks)
    return all_chunks

def create_embeddings_and_vectorstore(chunks, persist_directory):
    logger.info(f"Creating vector store at {persist_directory} with {len(chunks)} chunks...")
    embeddings = get_embedding_model()
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_directory,
        collection_name=Config.COLLECTION_NAME
    )
    return vectorstore
