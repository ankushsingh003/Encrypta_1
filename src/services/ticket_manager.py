import os
import json
import uuid
from datetime import datetime, timezone
from src.core.logging_config import logger

class TicketManager:
    TICKETS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'tickets.json'))

    @classmethod
    def create_ticket(cls, question, chat_history, user_info=None, escalation_metadata=None):
        ticket_id = str(uuid.uuid4())
        ticket = {
            "id": ticket_id,
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "question": question,
                "chat_history": chat_history,
                "user_info": user_info or {"email": "unknown"},
                "escalation_metadata": escalation_metadata or {}
            }
        }
        
        # Determine reason
        score = escalation_metadata.get("last_retrieval_score", 0.0) if escalation_metadata else 0.0
        if escalation_metadata.get("auto_escalated") and score < 0.3:
            ticket["payload"]["reason"] = "low_retrieval_confidence"
        elif escalation_metadata.get("auto_escalated"):
            ticket["payload"]["reason"] = "auto_escalated_policy_issue"
        else:
            ticket["payload"]["reason"] = "user_manual_escalation"

        cls._save_ticket(ticket)
        logger.info(f"Ticket created: {ticket_id}")
        return ticket_id

    @classmethod
    def _save_ticket(cls, ticket):
        tickets = cls._load_all_tickets()
        tickets.append(ticket)
        with open(cls.TICKETS_FILE, 'w') as f:
            json.dump(tickets, f, indent=2)

    @classmethod
    def _load_all_tickets(cls):
        if not os.path.exists(cls.TICKETS_FILE):
            return []
        try:
            with open(cls.TICKETS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []

    @classmethod
    def get_ticket_by_id(cls, ticket_id):
        tickets = cls._load_all_tickets()
        for t in tickets:
            if t['id'] == ticket_id:
                return t
        return None
