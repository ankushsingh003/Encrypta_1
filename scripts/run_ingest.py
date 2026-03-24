import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.config import Config
from src.core.logging_config import logger
from src.rag.ingest import load_and_split_pdfs, create_embeddings_and_vectorstore

def main():
    logger.info("Starting ingestion pipeline...")
    pdf_paths = Config.get_pdf_paths()
    if not pdf_paths:
        logger.error("No PDF files found in data/ directory.")
        return

    chunks = load_and_split_pdfs(pdf_paths, Config.CHUNK_SIZE, Config.CHUNK_OVERLAP)
    if not chunks:
        logger.warning("No text chunks extracted from PDFs.")
        return

    create_embeddings_and_vectorstore(chunks, Config.PERSIST_DIRECTORY)
    logger.info("Ingestion completed successfully.")

if __name__ == "__main__":
    main()
