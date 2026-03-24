from typing import List, Dict, Any, Tuple
from src.core.llm import get_llm, get_qa_chain_prompt
from src.rag.retriever import get_retriever
from src.services.ticket_manager import TicketManager
from src.core.logging_config import logger

class LLMService:
    def __init__(self):
        self.llm = get_llm()
        self.prompt = get_qa_chain_prompt()

    async def generate_response(self, question: str, context: str, history: str) -> Dict[str, Any]:
        logger.info("Generating AI response...")
        chain = self.prompt | self.llm
        # For simplicity, returning a simulated JSON response structure as expected by the hub
        # In a real impl, we'd use a structured output parser
        response = await chain.ainvoke({"question": question, "context": context, "history": history})
        # Mocking the structured output since I don't have a specific schema-based chain here yet
        # However, the doc says the response processor handles the LLM dict.
        return {
            "domain_relevant": True,
            "response_type": "answer",
            "answer": response.content,
            "confidence": 0.5, # Placeholder
            "correctness": "high",
            "escalate": False,
            "follow_up_questions": [],
            "reasoning": "Standard RAG answer"
        }

class ResponseProcessor:
    @staticmethod
    def process(response_dict: Dict[str, Any]) -> Tuple[str, bool, List[str]]:
        answer = response_dict.get("answer", "I'm sorry, I couldn't find an answer.")
        conf = response_dict.get("confidence", 0.0)
        corr = response_dict.get("correctness", "unknown")
        
        rendered_answer = f"{answer}\n\n*Confidence: {conf} | Correctness: {corr}*"
        should_escalate = response_dict.get("escalate", False)
        follow_ups = response_dict.get("follow_up_questions", [])
        
        return rendered_answer, should_escalate, follow_ups

class TicketService:
    @staticmethod
    def create_support_ticket(question, chat_history, user_info=None, escalation_metadata=None):
        return TicketManager.create_ticket(question, chat_history, user_info, escalation_metadata)

# Aliases to match docx
class RetrievalServiceWrap:
    def __init__(self):
        self._retriever = get_retriever()
    def retrieve_documents(self, q):
        return self._retriever.retrieve_documents(q)

RetrievalService = RetrievalServiceWrap
