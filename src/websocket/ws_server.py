import json
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from src.services.services import RetrievalService, LLMService, ResponseProcessor, TicketService
from src.core.logging_config import logger

app = FastAPI()

class MessageIn(BaseModel):
    type: str
    content: str
    sender_role: str = "customer"
    channel: str = "text"

class MessageOut(BaseModel):
    conversation_id: str
    type: str
    sender_role: str
    content: str
    channel: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[Dict] = None

    def __init__(self, **data):
        super().__init__(**data)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.message_history: Dict[str, List[MessageOut]] = {}

    async def connect(self, websocket: WebSocket, conversation_id: str):
        await websocket.accept()
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = []
        self.active_connections[conversation_id].append(websocket)
        logger.info(f"Connected: {conversation_id}")

    def disconnect(self, websocket: WebSocket, conversation_id: str):
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].remove(websocket)
            logger.info(f"Disconnected: {conversation_id}")

    async def broadcast(self, message: MessageOut):
        cid = message.conversation_id
        if cid not in self.message_history:
            self.message_history[cid] = []
        self.message_history[cid].append(message)
        
        if cid in self.active_connections:
            for connection in self.active_connections[cid]:
                await connection.send_text(message.model_dump_json())

manager = ConnectionManager()
retrieval_service = RetrievalService()
llm_service = LLMService()

@app.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    await manager.connect(websocket, conversation_id)
    try:
        while True:
            data = await websocket.receive_text()
            message_in = MessageIn.model_validate_json(data)
            
            if message_in.type == "user_message":
                try:
                    # 1. Retrieve
                    docs, meets, score = retrieval_service.retrieve_documents(message_in.content)
                    context = "\n".join([doc.page_content for doc, _ in docs])
                    
                    # 2. LLM Generate
                    history_lines = [f"{m.sender_role}: {m.content}" for m in manager.message_history.get(conversation_id, [])[-5:]]
                    history = "\n".join(history_lines)
                    
                    res_dict = await llm_service.generate_response(message_in.content, context, history)
                    
                    # 3. Process
                    rendered, should_escalate, follow_ups = ResponseProcessor.process(res_dict)
                    
                    # 4. Broadcast
                    out = MessageOut(
                        conversation_id=conversation_id,
                        type="assistant_message",
                        sender_role="ai",
                        content=rendered,
                        channel="text",
                        metadata={"low_confidence": not meets, "follow_up_questions": follow_ups}
                    )
                    await manager.broadcast(out)
                    
                    if should_escalate:
                        ticket_id = TicketService.create_support_ticket(message_in.content, [], escalation_metadata={"auto_escalated": True})
                        await manager.broadcast(MessageOut(
                            conversation_id=conversation_id,
                            type="ticket_created",
                            sender_role="system",
                            content=f"Ticket created: {ticket_id}",
                            channel="text"
                        ))
                except Exception as e:
                    logger.error(f"Error in handle_user_message: {e}")
                    await manager.broadcast(MessageOut(
                        conversation_id=conversation_id,
                        type="system",
                        sender_role="system",
                        content=f"Error processing your message: {str(e)}",
                        channel="text"
                    ))
            else:
                # Handle other message types (agent, etc.)
                out = MessageOut(
                    conversation_id=conversation_id,
                    type=message_in.type,
                    sender_role=message_in.sender_role,
                    content=message_in.content,
                    channel=message_in.channel
                )
                await manager.broadcast(out)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, conversation_id)

@app.get("/health")
def health():
    return {"status": "ok"}
