import os
from groq import Groq
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from src.core.config import Config

def get_llm():
    Config.validate()
    return ChatGroq(
        groq_api_key=Config.GROQ_API_KEY,
        model_name=Config.LLM_MODEL,
        temperature=Config.LLM_TEMPERATURE
    )

def get_qa_chain_prompt():
    system_prompt = (
        "You are Trisha, an AI assistant for Encrypta. Use the following context to answer the user's question.\n"
        "If you don't know the answer or the context is insufficient, explain why and set 'escalate' to true or provide 'follow_up_questions'.\n\n"
        "Context:\n{context}\n\n"
        "History:\n{history}"
    )
    return ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{question}"),
    ])
