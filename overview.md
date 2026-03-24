# Encrypta RAG FAQ Chatbot

## Overview

The Encrypta RAG FAQ Chatbot is a sophisticated Retrieval-Augmented Generation (RAG) system designed to provide accurate, context-aware answers to user queries regarding Encrypta's products and services. By blending document ingestion, semantic search, and large language model (LLM) orchestration, the system minimizes a user's friction when seeking support.

### Key Features

*   **RAG-Powered Intelligence:** Core decisioning is driven by semantic retrieval using ChromaDB and response generation via the Groq API (utilizing Llama 3.1).
*   **The I0th Flow:** A structured clarification loop that activates when information is insufficient. Instead of guessing, the AI asks targeted questions to enrich the context before re-attempting a resolution.
*   **Omnichannel Support:** Deployed with a FastAPI WebSocket server at its core, supporting both automated AI interactions and seamless escalation to human agents via a Streamlit omnichannel UI.
*   **Robust Persistence:** All conversation states and ticket data are persisted, ensuring continuity across sessions and system restarts.
