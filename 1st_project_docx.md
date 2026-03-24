# Encrypta RAG FAQ Chatbot - Complete Implementation Documentation

## Overview

This project implements a Retrieval-Augmented Generation (RAG) based FAQ chatbot for Encrypta products and services. The system combines document ingestion, semantic search, LLM integration, and intelligent conversation management to provide accurate, context-aware answers to user queries. When the AI cannot resolve an issue confidently, it applies a structured information-gathering loop (the I0th flow) before escalating to a human agent.

The full system is deployed as two long-running processes: a FastAPI WebSocket server (`src/websocket/ws_server.py`) and a Streamlit omnichannel UI (`src/ui/omnichannel_streamlit_client.py`). All conversation state is persisted to `conversation_store.json` on every message so the system survives restarts and supports history replay.

## Reference Diagrams

The following diagrams are included as visual references for the architecture, session lifecycle, and I0th flow.

### Diagram 1 — Single Chat Session Lifecycle (Sequence)

![Encrypta Diagram 1](../pics/img1.png)

This sequence diagram shows how a single user query flows across UI, WebSocket server, retrieval, LLM, response processing, follow-up handling, and ticket escalation.

### Diagram 2 — I0th State Machine

![Encrypta Diagram 2](../pics/img2.png)

This state diagram captures transitions between `normal`, `follow_up_active`, `resolved`, and `escalated` based on confidence, retrieval quality, and follow-up outcomes.

### Diagram 3 — End-to-End Operational Flow (Training + Runtime)

![Encrypta Diagram 3](../pics/img3.png)

This architecture view combines offline ingestion (PDF -> chunking -> embeddings -> ChromaDB) with live runtime orchestration (chat UI, retrieval, LLM, processor, ticketing).

### Diagram 4 — Extended Visual Reference

![Encrypta Diagram 4](../pics/img4.jpeg)

This visual provides an additional reference view of the Encrypta chatbot workflow and supporting components.

### Diagram 5 — Extended Visual Reference (Alternate)

![Encrypta Diagram 5](../pics/img5.jpeg)

This alternate visual complements the prior diagrams with another perspective on process flow and escalation handling.

---

## Architecture Overview

```
PDF Documents -> Text Extraction -> Chunking -> Embeddings -> ChromaDB Vector Store
                                                                       |
User Query -> WebSocket Server -> RetrievalService -> LLMService -> ResponseProcessor
                                        |                                  |
                                  ConversationState               follow_up broadcast
                                  (summaries, history)                     |
                                                               I0th Loop (clarify)
                                                                           |
                                                               Escalation + TicketService
                                                                           |
                                                               Human Agent (WebSocket)
```

All components communicate through the WebSocket hub. Core decisioning (retrieval/LLM/escalation) is server-side; the Streamlit UI implements presentation, routing controls, and a small amount of client-side state restoration (e.g., remembering which route was chosen after a ticket is created).

---

## Core Components

### 1. Document Ingestion Pipeline (`scripts/run_ingest.py`)

Processes PDF documents and builds the ChromaDB vector store that powers retrieval.

**Implementation details:**
- Loads PDF files using `PyMuPDFLoader`
- Splits documents into chunks of 512 tokens with a 50-token overlap using LangChain's `RecursiveCharacterTextSplitter`
- Generates dense vector embeddings using `sentence-transformers/all-mpnet-base-v2` via HuggingFace
- Persists embeddings into ChromaDB with metadata fields: `area`, `topic`, `source`

**Usage:**
```bash
cd temp-task-for-Encrypta
python scripts/run_ingest.py
```

The resulting `chroma_db/` directory is read at server startup. If the directory is absent or empty, retrieval scores will be 0.0 for all queries and the I0th flow will activate on every message.

---

### 2. Retrieval Service (`src/services/services.py` -> `RetrievalService`)

Performs semantic search against the ChromaDB vector store.

**How it works:**
1. Converts the user query to a 768-dimensional embedding using the same model used during ingestion
2. Runs a cosine similarity search in ChromaDB
3. Returns `(docs_with_score, meets_threshold, score)` where `score` is the top similarity value
4. The `meets_threshold` flag drives downstream branching: if false, the LLM receives an empty document list and typically returns a low-confidence answer, triggering the I0th flow

The retrieval call inside `ws_server.py` extracts the top 6 documents:

```python
docs_with_score, _meets_threshold, score = state.retrieval_service.retrieve_documents(question)
docs = [doc for doc, _ in docs_with_score[:6]] if docs_with_score else []
```

Source metadata from the top 3 documents is collected into a `sources` list and attached to the `assistant_message` metadata so the UI can render them alongside the answer.

---

### 3. LLM Service (`src/services/services.py` -> `LLMService`)

Generates structured responses using the Groq API (Llama 3.1).

**How it works:**
1. Receives the user question, retrieved document chunks, and a compact chat history string
2. Constructs a prompt using LangChain Expression Language (LCEL)
3. Calls the Groq API and parses the JSON response
4. Returns a dict with keys: `domain_relevant`, `response_type`, `answer`, `confidence`, `correctness`, `escalate`, `follow_up_questions`, `reasoning`

The chat history passed to the LLM is built in `ws_server.py` from two sources: a rolling extractive summary (last 2000 characters of recent turns) and the last 10 raw messages:

```python
summary_blob = state.summaries.get(conversation_id)
if summary_blob:
    history_lines.append("Summary so far:\n" + summary_blob)
for m in prior_messages[-10:]:
    if m.sender_role in ("user", "ai"):
        role = "user" if m.sender_role == "user" else "assistant"
        history_lines.append(f"{role}: {m.content}")
```

This means Trisha already has context from earlier in the conversation when answering follow-up replies, which is what allows the second pass to produce a more targeted response.

---

### 4. Response Processor (`src/services/services.py` -> `ResponseProcessor`)

Processes the raw LLM dict into a rendered answer string and an escalation decision.

Key tasks:
- Formats the answer with confidence and correctness appended: `*Confidence: 0.31 | Correctness: low*`
- Sets `should_escalate = True` when `escalate` is true in the LLM response
- Extracts `follow_up_questions` from the LLM response and passes them back to the server

A low-confidence guardrail fires independently in `ws_server.py` after broadcasting the AI reply:

```python
low_conf = isinstance(metadata, dict) and metadata.get("low_confidence") and not should_escalate
if low_conf:
    await state.broadcast(MessageOut(..., content="Confidence is low. Please add details..."))
```

This system message is distinct from the I0th follow_up message. It prompts the user in natural language while the follow_up message carries the machine-readable question list used by the UI.

---

### 5. Conversation State and Persistence (`src/websocket/ws_server.py` -> `ConversationState`)

`ConversationState` is a singleton instantiated at module load. It owns all runtime state.

**Fields:**
- `connections`: maps `conversation_id` to the list of live WebSocket connections
- `messages`: maps `conversation_id` to the ordered list of `MessageOut` objects
- `summaries`: maps `conversation_id` to the rolling extractive summary string
- `ticket_conversations`: maps ticket UUIDs to their originating `conversation_id` for replay

**Persistence:**
Every call to `append_message` immediately writes the full state to `conversation_store.json`. The file is read back on startup via `_load_store`. This means the server can be restarted without losing conversation history. The store uses a flat JSON structure:

```json
{
  "conversations": {
    "conversation_id": [ <list of serialized MessageOut dicts> ]
  },
  "summaries": {
    "conversation_id": "<plain text summary>"
  }
}
```

The rolling summary is updated after every AI reply via `update_summary`. It scans the last 20 messages and concatenates `USER:`, `AI:`, and `AGENT:` prefixed lines, hard-truncating at 2000 characters.

---

### 6. WebSocket Message Protocol

The server exposes one endpoint: `ws://host:8000/ws/{conversation_id}`.

**Inbound message types** (`MessageIn`):
- `user_message` — a customer turn, routed to the AI FAQ pipeline
- `agent_message` — a human agent reply, broadcast as-is
- `call_transcript` — a voice transcript, broadcast as-is

**Outbound message types** (`MessageOut`):
- `assistant_message` — AI answer, carries `metadata` with confidence, sources, follow_up_questions
- `follow_up` — I0th trigger, carries `metadata.follow_up_questions` list
- `ticket_created` — escalation notification with ticket UUID in content
- `history_snapshot` — full transcript replay when reconnecting with a `ticket_id` query param
- `system` — operational events (connected, low-confidence warning, mode switch)

All outbound messages are broadcast to every WebSocket connection registered under the same `conversation_id`, so multiple clients (e.g., the Streamlit UI and a terminal agent client) see the same timeline.

---

## The I0th Flow: Ideation, Design, and Implementation

### What Is the I0th Flow?

The I0th flow is the system's structured response to uncertainty. The name refers to the zeroth iteration: before the system attempts to answer, it determines whether it has enough information to answer well. If the retrieved documents are sparse or the LLM confidence is below a meaningful threshold, the system does not guess. Instead it emits a set of targeted clarifying questions back to the user, waits for the answers, and re-runs the full pipeline with the enriched context.

The key design constraint is that this must feel like a natural conversation. The AI does not present a form or enumerate questions. It asks one question at a time, surfaced via an `st.info` banner in the UI directly below the AI message that triggered the need for clarification.

### Why This Matters

Without a clarification mechanism, a RAG system has two failure modes: it either returns a vague low-confidence answer (which erodes user trust) or it immediately escalates to a human (which wastes human capacity). The I0th flow creates a third path: the system asks a targeted question, the user answers it, and the second attempt often succeeds because the enriched context lands in a different, more specific part of the vector store.

If the second attempt still fails, the system escalates with a ticket that already contains the gathered context. The human agent receives the full thread including what was tried and why it failed, rather than starting from scratch.

### Trigger Conditions

The I0th flow activates when the LLM returns `follow_up_questions` as a non-empty list alongside a low-confidence answer. In practice this happens when:

1. `retrieval_score` is near 0: the vector store returned no documents above the similarity threshold, so the LLM has nothing to reason from
2. `confidence` in the LLM response is below the low-confidence threshold (in the current system this is `< 0.4`, checked via `metadata.get("low_confidence")`)
3. The LLM sets `escalate: False` — if the LLM already believes escalation is warranted, the follow-up step is skipped and the ticket is created immediately

The check in `ws_server.py` after broadcasting the AI reply:

```python
if follow_ups:
    await state.broadcast(
        MessageOut(
            conversation_id=conversation_id,
            type="follow_up",
            sender_role="ai",
            content="Follow-up questions to help resolve this.",
            channel="text",
            timestamp=datetime.now(timezone.utc),
            metadata={"follow_up_questions": follow_ups},
        )
    )
```

The `follow_ups` variable comes directly from the LLM response dict via `ResponseProcessor`:

```python
fu = metadata.get("follow_up_questions")
if isinstance(fu, list) and all(isinstance(x, str) for x in fu):
    follow_ups = fu
```

### The UI Layer: Showing One Question at a Time

The Streamlit client (`src/ui/omnichannel_streamlit_client.py`) handles the I0th follow_up message by finding the most recent unanswered `follow_up` message in history and rendering a single `st.info` prompt showing only the first question in the list:

```python
# Before the history render loop: find the last follow_up without a subsequent user reply
last_followup_idx: Optional[int] = None
for i, _m in enumerate(history):
    if _m.get("type") == "follow_up":
        last_followup_idx = i
if last_followup_idx is not None:
    for _m in history[last_followup_idx + 1:]:
        if _m.get("type") == "user_message":
            last_followup_idx = None
            break
```

Inside the loop, only the message at `last_followup_idx` gets the prompt:

```python
if idx == last_followup_idx:
    fu_list = meta.get("follow_up_questions") if isinstance(meta, dict) else None
    if fu_list:
        question_to_ask = fu_list[0]
        st.info(f"To help resolve this, could you tell me: **{question_to_ask}**")
```

The prompt disappears as soon as the next `user_message` arrives. This avoids the need for any button widgets or session state keys and ensures there are no duplicate-key errors across re-renders.

### The Follow-up Question Generator (`src/followup/generate_followups.py`)

The `generate_followups` function is the engine that produces candidate questions before they are passed to the LLM. In the current deployment the LLM itself emits the `follow_up_questions` field in its response, but `generate_followups` is available for cases where the LLM output does not include them or where a standalone clarification step is needed.

**Function signature:**
```python
def generate_followups(category, initial_question, conversation,
                       use_model=False, apply_ranking=True)
```

**Generation strategy — two paths:**

Path 1: T5 model (when `use_model=True`):
```python
prompt = (
    f"Generate {num_return_sequences} concise follow-up questions for the user.\n"
    f"Category: {category}\nConversation: {conversation}\n"
    f"User question: {initial_question}\nFollow-ups:"
)
inputs = _tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
outputs = _model.generate(**inputs, max_length=128, num_return_sequences=num_return_sequences,
                           do_sample=True, top_p=0.95, temperature=0.8)
```

The model at `./followup_model/` was fine-tuned from `t5-small` on the JSONL files in `data_files/`. If model loading fails for any reason, the function falls back immediately to rule-based generation without raising an exception.

Path 2: Rule-based (default, `use_model=False`):

The function inspects `initial_question` for specific keywords and selects a pre-written bank of targeted questions:

```python
if 'password' in question_lower and ('reset' in question_lower or 'forgot' in question_lower):
    candidate_questions = [
        "What browser are you using?",
        "Did you receive the password reset email?",
        "What error message are you seeing, if any?"
    ]
```

For unrecognized topics it falls back to the category bank (technical, billing, transaction, account, general).

**Ranking (when `apply_ranking=True`):**

All candidates pass through `rank_and_filter_followup_questions` which computes a weighted composite score across five dimensions:

| Factor | Weight | Source |
|---|---|---|
| Relevance | 0.25 | Cosine similarity of question embedding vs. query+conversation embedding |
| Historical success rate | 0.20 | Scans `conversation_store.json` for similar resolved conversations |
| Information gain | 0.25 | Keyword analysis: high-gain terms (`error message`, `version`, `date`) vs. vague terms |
| User friction | 0.15 | Question structure: yes/no scores 0.85, how/why scores 0.50, penalises compound questions |
| Context fit | 0.15 | Overlap with category-specific keywords + word overlap with original query |

```python
composite_score = (
    relevance * 0.25 +
    historical_success * 0.20 +
    info_gain * 0.25 +
    user_friction * 0.15 +
    context_fit * 0.15
)
```

Questions scoring below `min_score=0.5` are dropped. The top 3 are returned as `(question, score, factor_scores)` tuples.

---

### Response Relevance Checker (`src/followup/response_relevance.py`)

After a follow-up answer arrives from the user, `ResponseRelevanceChecker` validates that the answer is topically related to what was asked. This prevents irrelevant or off-topic responses from polluting the enriched context passed to the second RAG call.

```python
class ResponseRelevanceChecker:
    def __init__(self, similarity_threshold: float = 0.3):
        self.embedding_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-mpnet-base-v2"
        )
        self.similarity_threshold = similarity_threshold

    def check_relevance(self, original_query, user_response, followup_question=None):
        query_embedding = np.array(self.embedding_model.embed_query(original_query))
        response_embedding = np.array(self.embedding_model.embed_query(user_response))
        query_similarity = self.cosine_similarity(query_embedding, response_embedding)
        if followup_question:
            followup_embedding = np.array(self.embedding_model.embed_query(followup_question))
            followup_similarity = self.cosine_similarity(followup_embedding, response_embedding)
            final_similarity = max(query_similarity, followup_similarity)
        else:
            final_similarity = query_similarity
        return final_similarity >= self.similarity_threshold, final_similarity
```

The threshold of 0.3 is intentionally permissive. Users rarely phrase their follow-up answers to mirror the question vocabulary, so a strict threshold would discard valid short answers like "yes, I did" or "macOS 3.4.1". The `max` of the two similarity scores (against original query and against the follow-up question itself) ensures that answers relevant to either pass through.

---

### T5 Follow-up Model Training (`src/followup/train_followup_model.py`)

The fine-tuned T5-small model was trained on the JSONL files in `data_files/`:
- `followup_training_data.jsonl` — base training set
- `followup_training_data_enhanced.jsonl` — augmented set with metadata and category fields

**Training entry point:**
```python
def main():
    data = load_data('followup_training_data_enhanced.jsonl')
    tokenizer = T5Tokenizer.from_pretrained("t5-small")
    model = T5ForConditionalGeneration.from_pretrained("t5-small")
    training_args = TrainingArguments(
        output_dir='./results',
        num_train_epochs=5,
        per_device_train_batch_size=4,
        learning_rate=3e-4,
        warmup_steps=100,
        weight_decay=0.01,
        save_steps=50,
        save_total_limit=2,
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=train_dataset)
    trainer.train()
    model.save_pretrained('./followup_model')
```

Each JSONL line has `input` and `output` fields. The input is a prompt describing the category, conversation context, and original query. The output is the target follow-up question. The enhanced file additionally carries `category`, `metadata`, and `key_value_pairs` fields that are used for filtering and weighting during data loading but stripped before training.

**To retrain:**
```bash
cd temp-task-for-Encrypta
python src/followup/train_followup_model.py
```

The output model is saved to `./followup_model/`. The generation code in `generate_followups.py` reads from that path:

```python
def load_model():
    model_path = './followup_model'
    tokenizer = T5Tokenizer.from_pretrained(model_path)
    model = T5ForConditionalGeneration.from_pretrained(model_path)
    return tokenizer, model
```

---

### End-to-End I0th Test (`tests/test_websocket_i0th_flow.py`)

The integration test verifies the complete I0th sequence: user query with no matching docs -> low-confidence AI reply with follow-up questions -> user answers -> escalation -> ticket created.

The test sequence:
1. Connect to `/ws/i0th-flow-test` and assert the initial `system` message
2. Send `user_message` with a non-existent feature name
3. Collect messages until `follow_up` arrives; assert its `metadata.follow_up_questions` is a non-empty list
4. Send two user replies simulating I0th answers
5. Collect messages until `ticket_created` arrives; assert it contains "Ticket created"

The `_recv_json` helper wraps `receive_json()` in a `ThreadPoolExecutor` because Starlette's test WebSocket client blocks without a timeout:

```python
def _recv_json(ws, timeout_s: float = 2.0):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(ws.receive_json)
        try:
            return future.result(timeout=timeout_s)
        except FutureTimeoutError as e:
            raise _WsRecvTimeout(...) from e
```

**To run:**
```bash
cd temp-task-for-Encrypta
pytest tests/test_websocket_i0th_flow.py -v
```

---

### Demo Transcript: I0th Flow in Action

The file `data_files/demo_transcript.json` contains a pre-built conversation demonstrating the full I0th sequence. It can be loaded into the Streamlit UI via the sidebar button "Load Demo Transcript (demo_transcript.json)" without needing a live WebSocket session.

What it demonstrates (high level):

1. A technical user issue that the AI cannot answer confidently
2. A low-confidence AI response (with `follow_up_questions` present in metadata)
3. A `follow_up` event in the timeline and a single-question prompt shown in the UI
4. A subsequent AI attempt using the richer context
5. Escalation via `ticket_created`
6. A route switch to human assistant text mode and a human agent reply

Note: demo ticket IDs may be formatted for readability. In live runs, tickets are created by `src/services/ticket_manager.py` and IDs are UUID strings.

When loaded from the sidebar, `_maybe_update_ticket_state_from_history` detects the `Mode set to: human_assistant_text` message after the ticket event and sets `ticket_prompt_active = False`, so the conversation renders as a completed exchange rather than pausing at the mode selector. The chat input hint changes to "Human assistant (text) message" to reflect the route.

---

## Escalation and Ticketing

### Escalation Flow

Escalation is triggered when `ResponseProcessor` returns `should_escalate = True`. The conditions for this are set in the LLM prompt: the model returns `"escalate": true` when it cannot formulate a confident answer even with retrieved context, or when the query involves security, data loss, or a scenario outside the FAQ knowledge base.

The escalation path in `ws_server.py`:

```python
if should_escalate:
    from src.services.services import TicketService
    history = []
    for m in state.messages.get(conversation_id, [])[-30:]:
        history.append({
            "type": m.type, "sender_role": m.sender_role,
            "content": m.content, "channel": m.channel,
            "timestamp": m.timestamp.isoformat(),
        })
    ticket_id = TicketService.create_support_ticket(
        question=question,
        chat_history=history,
        user_info={"email": "unknown"},
        escalation_metadata={
            "auto_escalated": True,
            "last_retrieval_score": score,
            "response_metadata": metadata or {},
        },
    )
    state.ticket_conversations[ticket_id] = conversation_id
    await state.broadcast(MessageOut(
        type="ticket_created",
        content=f"Ticket created: {ticket_id}. Choose whether to continue with AI FAQ (RAG) or switch to a human assistant (text/call).",
        ...
    ))
```

The full last 30 messages are included in the ticket payload. This means the human agent who opens the ticket sees the complete thread including what the AI tried, what follow-up questions were asked, and what the user answered.

### Ticket Replay

When a human agent reconnects to a conversation using the `ticket_id` query parameter (`ws://host:8000/ws/{conv_id}?ticket_id=TKT-...`), the server hydrates the conversation history from the stored ticket and sends a `history_snapshot` message containing the full transcript plus ticket metadata:

```python
seeded = state.seed_conversation_from_ticket(history_conv_id, ticket_id)
```

This allows the agent interface to reconstruct the exact state of the conversation at escalation time.

---

## Omnichannel Routing

The Streamlit UI supports three routing modes set via `st.session_state.active_route`:

| Route constant | Value | Chat input sends |
|---|---|---|
| `ROUTE_FAQ` | `customer_to_faq` | `user_message` (routed to AI pipeline) |
| `ROUTE_HUMAN_TEXT` | `human_assistant_text` | `agent_message` (broadcast as human turn) |
| `ROUTE_HUMAN_CALL` | `human_assistant_call` | `call_transcript` (broadcast as voice transcript) |

The mode selector appears as a `st.selectbox` only when `ticket_prompt_active` is True in session state. Once the operator makes a choice and clicks Apply, a `system` message with `"Mode set to: <route>"` is appended to history and `ticket_prompt_active` is set to False.

The `_maybe_update_ticket_state_from_history` function reads this message on every render to ensure the route and prompt state survive page refreshes:

```python
for msg in history[ticket_idx + 1:]:
    content = msg.get("content", "")
    if msg.get("type") == "system" and "Mode set to:" in content:
        mode_switched = True
        if ROUTE_HUMAN_TEXT in content:
            _set_route(ROUTE_HUMAN_TEXT)
        ...
        break
st.session_state.ticket_prompt_active = not mode_switched
```

---

## Technical Stack

- **WebSocket server**: FastAPI + Uvicorn
- **UI**: Streamlit
- **Backend**: Python 3.12
- **Vector database**: ChromaDB (local persistence)
- **Embeddings**: `sentence-transformers/all-mpnet-base-v2` via HuggingFace
- **LLM**: Groq API (Llama 3.1)
- **Follow-up model**: Fine-tuned T5-small (Hugging Face Transformers)
- **Document processing**: PyMuPDF, LangChain
- **Data storage**: JSON files, ChromaDB

---

## Configuration

Environment variables are loaded from `config/.env`.

**Required:**
- `GROQ_API_KEY` — Groq API key for LLM calls

**Key thresholds (set in service code):**

| Parameter | Default | Effect |
|---|---|---|
| Low-confidence threshold | 0.4 | Below this, `low_confidence` metadata flag is set |
| Retrieval similarity threshold | configured in `RetrievalService` | Below this, `meets_threshold` is False |
| Follow-up ranking minimum score | 0.5 | Questions below this are dropped |
| Follow-up top_k | 3 | Max questions returned by ranking |
| Response relevance threshold | 0.3 | Below this, user response is considered off-topic |
| Rolling summary window | 20 messages | Messages included in extractive summary |
| Chat history passed to LLM | last 10 turns | Recent turns appended after summary |
| Ticket history window | last 30 messages | Included in ticket payload |

---

## Running the System

**Start both services:**
```bash
cd temp-task-for-Encrypta

# WebSocket server
uvicorn src.websocket.ws_server:app --host 0.0.0.0 --port 8000 &

# Streamlit UI
streamlit run src/ui/omnichannel_streamlit_client.py --server.port 8503 --server.headless true &
```

**Health check:**
```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","retrieval_ready":true,"llm_ready":true}
```

**Send a human agent reply from the terminal (WebSocket client):**
```python
import asyncio, json, websockets

async def send_agent_reply(conv_id: str, message: str):
    async with websockets.connect(f"ws://127.0.0.1:8000/ws/{conv_id}") as ws:
        await ws.send(json.dumps({
            "type": "agent_message",
            "sender_role": "agent",
            "content": message,
            "channel": "text",
        }))

asyncio.run(send_agent_reply("demo-i0th", "Hi, I'm Trisha. I can see the full thread..."))
```

**Retrain the follow-up model:**
```bash
python src/followup/train_followup_model.py
# Output saved to ./followup_model/
```

---

## Known Gaps and To-Do Items

### Previously Solved Questions as a Separate Database

Currently, resolved conversations are stored only in `conversation_store.json` alongside active conversations. A dedicated resolved-cases store with vector indexing would allow the system to match the current query against past resolutions before hitting the LLM, potentially resolving more queries without human escalation.

### Full I0th Integration with Real-Time Learning

The current I0th flow gathers follow-up answers and re-runs the RAG pipeline but does not yet feed successful resolutions back into the follow-up model training data automatically. This requires a webhook or listener on ticket closure events that triggers template extraction and incremental model retraining.

### Advanced Similarity for Re-escalation

When a past resolution is found and attempted but fails (the user reports it did not help), the system should automatically detect the mismatch, generate a diff of what is different about the current user's context versus the resolved case, and include that diff in the escalation metadata so the human agent immediately knows what was tried.

### Multi-modal Input

The system currently processes only text. Supporting screenshot uploads of error dialogs and log file pastes would significantly improve first-contact resolution rates for technical issues where the error message is the primary diagnostic signal.

---

## Notes on Optional / Not-Wired Modules

This repo contains additional follow-up utilities that are not currently called from the WebSocket server path:

- `src/followup/generate_followups.py` implements T5-based generation plus a ranking function.
- `src/followup/response_relevance.py` implements embedding-based relevance checking.

The current WebSocket I0th behavior comes from the LLM returning `follow_up_questions` in its response JSON; the server forwards those via a `follow_up` message and the Streamlit UI surfaces only the first question as a prompt.

---

## Project Structure

```
temp-task-for-Encrypta/
├── config/
│   └── .env                          # GROQ_API_KEY and optional overrides
├── data/
│   ├── Getting_Started_with_Encrypta.pdf
│   └── Getting_Started_with_Password_Manager.pdf
├── data_files/
│   ├── demo_transcript.json          # Pre-built I0th demo (9 messages)
│   ├── followup_training_data.jsonl  # Base T5 training set
│   └── followup_training_data_enhanced.jsonl  # Augmented training set
├── chroma_db/                        # ChromaDB vector store (created by ingest)
├── followup_model/                   # Fine-tuned T5-small (created by training)
├── conversation_store.json           # Persistent conversation history
├── src/
│   ├── core/
│   │   ├── config.py                 # Centralized Config class
│   │   ├── llm.py                    # Groq LLM setup and qa_chain factory
│   │   ├── logging_config.py         # Shared logger
│   │   └── embeddings.py             # HuggingFace embedding model loader
│   ├── rag/
│   │   ├── ingest.py                 # PDF loading, chunking, vector store creation
│   │   └── retriever.py              # ChromaDB retrieval, threshold check, metadata filtering
│   ├── services/
│   │   ├── services.py               # RetrievalService, LLMService, TicketService,
│   │   │                             #   IngestionService, ResponseProcessor
│   │   ├── ticket_manager.py         # JSON-backed ticket CRUD (tickets.json)
│   │   └── tickets.json              # Persisted ticket records
│   ├── followup/
│   │   ├── generate_followups.py     # Follow-up generation + 5-factor ranking
│   │   ├── response_relevance.py     # Cosine-similarity response validator
│   │   └── train_followup_model.py   # T5-small fine-tuning script
│   ├── ui/
│   │   └── omnichannel_streamlit_client.py   # Streamlit chat UI
│   └── websocket/
│       └── ws_server.py              # FastAPI WebSocket hub + handle_ai_faq
├── scripts/
│   └── run_ingest.py                 # Entry point for PDF ingestion
├── tests/
│   ├── test_websocket_i0th_flow.py   # End-to-end I0th integration test
│   └── test_simulate_chat.py         # Chat simulation test
└── docs/
    ├── document.md                   # This file
    └── archive/                      # Historical reports
```

---

## Configuration Reference (`src/core/config.py`)

All runtime configuration is centralised in the `Config` class loaded from `config/.env`.

```python
class Config:
    # Vector Database
    COLLECTION_NAME    = "faq_collection"
    PERSIST_DIRECTORY  = "./chroma_db"
    EMBEDDING_MODEL    = "sentence-transformers/all-mpnet-base-v2"

    # LLM Settings
    GROQ_API_KEY       = os.getenv("GROQ_API_KEY")          # required
    LLM_MODEL          = os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
    LLM_TEMPERATURE    = 0.1

    # Chunking Settings
    CHUNK_SIZE         = 512    # tokens
    CHUNK_OVERLAP      = 50     # tokens
    USE_TOKEN_CHUNKING = True

    # Retrieval Settings
    USE_METADATA_FILTERING = True
    RETRIEVAL_THRESHOLD    = 0.3
    TOP_AREAS              = 3
    TOP_K_PER_AREA         = 2

    # Response Settings
    USE_JSON_RESPONSES = True
```

`Config.validate()` raises `ValueError` if `GROQ_API_KEY` is absent or empty. It is called inside `LLMService.__init__()` so the error surfaces immediately at first use, not at import time.

The `get_pdf_paths()` class method resolves `data/` relative to the project root regardless of where the process is started from, avoiding common path bugs when running from subdirectories.

**To override the model:**
```bash
LLM_MODEL=llama-3.3-70b-versatile uvicorn src.websocket.ws_server:app --port 8000
```

---

## Ingestion Pipeline in Detail (`src/rag/ingest.py`, `scripts/run_ingest.py`)

The ingestion pipeline runs once (or whenever the PDFs are updated) and produces the ChromaDB collection read by `RetrievalService`.

**Steps:**

1. `load_and_split_pdfs(paths, chunk_size=512, chunk_overlap=50, use_token_chunking=True)` — loads each PDF with `PyMuPDFLoader`, splits using LangChain's `RecursiveCharacterTextSplitter` in token mode. Each chunk carries metadata: `source` (file path), `page`, and any custom `area`/`topic` fields in the PDF if present.

2. `create_embeddings_and_vectorstore(chunks, collection_name, embedding_model, persist_directory)` — initialises a `HuggingFaceEmbeddings` instance with the configured model, batches the chunk texts through it, and upserts into a ChromaDB persistent client at `./chroma_db/`.

3. The returned `vectorstore` object is not saved in memory; ChromaDB writes to disk. On the next server start, `get_retriever()` opens the same directory with a `PersistentClient`.

**Metadata-based retrieval (`USE_METADATA_FILTERING = True`):**

When enabled, `MetadataBasedRetriever` in `retriever.py` first classifies the query into an `area` (e.g., "password_manager", "account") and then targets `TOP_K_PER_AREA` (2) chunks from each of the top `TOP_AREAS` (3) matching areas. This improves precision for multi-topic FAQs by preventing a single area from dominating results.

When disabled, a standard similarity search returns the globally top-k documents.

---

## Ticket Manager (`src/services/ticket_manager.py`)

Tickets are persisted as a JSON array in `src/services/tickets.json`. Each record has the shape:

```json
{
  "id": "uuid4-string",
  "status": "open",
  "created_at": "2026-02-18T10:05:00",
  "payload": {
    "product": "password_manager",
    "question": "original user query",
    "chat_history": [ ... last 30 messages ... ],
    "user_info": { "email": "unknown" },
    "reason": "low_retrieval_confidence",
    "escalation_metadata": {
      "auto_escalated": true,
      "last_retrieval_score": 0.09,
      "response_metadata": { ... }
    }
  }
}
```

**Reason classification** is applied at creation time in `create_ticket()`:

| Condition | `reason` value |
|---|---|
| `auto_escalated=True` and `retrieval_score < 0.3` | `low_retrieval_confidence` |
| `auto_escalated=True` and score >= 0.3 | `auto_escalated_policy_issue` |
| Not auto-escalated | `user_manual_escalation` |

`get_ticket_by_id(ticket_id)` is used by `seed_conversation_from_ticket` to hydrate the conversation history when an agent reconnects via `?ticket_id=` query parameter.

---

## Streamlit UI Architecture (`src/ui/omnichannel_streamlit_client.py`)

The Streamlit client is a pure WebSocket consumer; all business logic runs in the server. Its responsibilities are:

1. Maintain a WebSocket connection in a background thread (using `websocket-client`)
2. Append incoming `MessageOut` JSON objects to `st.session_state.history`
3. Re-render the conversation timeline on every Streamlit rerun
4. Send outgoing messages typed in the chat input
5. Provide the sidebar demo loader and route selector

### WebSocket Background Thread

The connection is opened in a daemon thread to avoid blocking Streamlit's rendering loop. Incoming messages are appended to `st.session_state.history` (a list of raw dicts) via a thread-safe append:

```python
def on_message(_ws, message):
    data = json.loads(message)
    st.session_state.history.append(data)
    st.rerun()
```

`st.rerun()` triggers a full Streamlit re-render so the new message appears immediately without the user having to interact with the page.

### Message Rendering

The history render loop in the main body iterates over `st.session_state.history`. Each message type is rendered differently:

| `type` | Rendered as |
|---|---|
| `user_message` | `st.chat_message("user")` |
| `assistant_message` | `st.chat_message("assistant")` with `role_label()` = "Trisha"; sources shown as expander |
| `agent_message` | `st.chat_message("assistant")` labelled "Trisha (Specialist)" |
| `call_transcript` | `st.chat_message("assistant")` labelled "Voice" |
| `ticket_created` | `st.warning()` box |
| `follow_up` | Rendered as a normal message; additionally triggers a single-question `st.info()` prompt (first question only) |
| `system` | `st.caption()` in grey |
| `history_snapshot` | Renders an expandable JSON viewer for the agent |

### I0th Follow-up Rendering

Before the render loop starts, a scan determines whether there is an unanswered `follow_up` message:

```python
last_followup_idx = None
for i, m in enumerate(history):
    if m.get("type") == "follow_up":
        last_followup_idx = i
# Invalidate if user has already replied
if last_followup_idx is not None:
    for m in history[last_followup_idx + 1:]:
        if m.get("type") == "user_message":
            last_followup_idx = None
            break
```

Inside the loop, only the message at `last_followup_idx` renders the prompt. It shows only the first question from `follow_up_questions` to avoid overwhelming the user:

```python
if idx == last_followup_idx:
    fu_list = meta.get("follow_up_questions") if isinstance(meta, dict) else None
    if fu_list:
        st.info(f"To help resolve this, could you tell me: **{fu_list[0]}**")
```

### Ticket Route Selector

When `st.session_state.ticket_prompt_active` is `True`, a `st.selectbox` appears above the chat input offering three routing options. Clicking Apply broadcasts a `system` message with `"Mode set to: <route>"` and sets `ticket_prompt_active = False`. The route is stored in `st.session_state.active_route`.

`_maybe_update_ticket_state_from_history` restores this state on every render (page refreshes, demo loads) by scanning for the `"Mode set to:"` system message. If found, `ticket_prompt_active` is set to `False` and `active_route` is set to the value in the message.

### Chat Input

The chat input placeholder changes by route:

```python
if route == ROUTE_FAQ:
    placeholder = "Ask a question..."
elif route == ROUTE_HUMAN_TEXT:
    placeholder = "Human assistant (text) message"
else:
    placeholder = "Call transcript / voice message"
```

Submitted text is sent as the appropriate `type` over WebSocket:

```python
if route == ROUTE_FAQ:
    ws.send(json.dumps({"type": "user_message", ...}))
elif route == ROUTE_HUMAN_TEXT:
    ws.send(json.dumps({"type": "agent_message", ...}))
elif route == ROUTE_HUMAN_CALL:
    ws.send(json.dumps({"type": "call_transcript", ...}))
```

---

## Deployment

This repository does not include a Docker Compose definition for the omnichannel (WebSocket + Streamlit) deployment. Run the services directly.

### Running Locally

**Prerequisites:**
```bash
pip install -r requirements.txt
```

**1. Ingest documents (once):**
```bash
cd temp-task-for-Encrypta
python scripts/run_ingest.py
```

**2. Start the WebSocket server:**
```bash
uvicorn src.websocket.ws_server:app --host 0.0.0.0 --port 8000
```

**3. Start the Streamlit UI:**
```bash
streamlit run src/ui/omnichannel_streamlit_client.py --server.port 8503 --server.headless true
```

**4. Verify both are running:**
```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","retrieval_ready":true,"llm_ready":true}
# or {"status":"degraded","error":"..."} if GROQ_API_KEY/deps are missing
```

Open http://localhost:8503 in a browser.

### Environment

The only required environment variable is `GROQ_API_KEY`. Create `config/.env`:

```
GROQ_API_KEY=gsk_...
```

Optional overrides:
```
LLM_MODEL=llama-3.3-70b-versatile
EMBEDDING_MODEL=sentence-transformers/all-mpnet-base-v2
```

---

## Testing


### Smoke Test: Live WebSocket

Minimal live-connect check (prints the first message and exits):

```bash
python - <<'PY'
import asyncio, json
import websockets

async def main():
    async with websockets.connect("ws://127.0.0.1:8000/ws/smoke-test") as ws:
        msg = await ws.recv()
        print(json.loads(msg))

asyncio.run(main())
PY
```

### Dependency Health Check

A `_check_omni.py` script at the project root verifies that all imports in `omnichannel_streamlit_client.py` work and that the file is syntactically valid:

```bash
python _check_omni.py
```

---

## Training the Follow-up Model

### Data Format

The training script (`src/followup/train_followup_model.py`) looks for `followup_training_data_enhanced.jsonl` in the current working directory. This repository stores the dataset under `data_files/`, so copy it into the repo root before training.

Each JSONL line uses the enhanced format:

```json
{
  "input": "Category: technical. Initial question: I can't reset my password. Conversation: User says app crashes on startup.",
  "output": "What error message are you seeing? | What browser are you using? | Did this start after a recent update?",
  "metadata": { "priority": "high", "tags": ["password", "login"], "reranking_score": 0.95 },
  "categories": ["technical", "security"],
  "key_value_pairs": { "issue_type": "password_reset" }
}
```

The `metadata`, `categories`, and `key_value_pairs` fields are stripped at load time; only `input` and `output` are used for training. The `output` field is a pipe-separated list of questions.

### Running Training

```bash
cd temp-task-for-Encrypta
cp data_files/followup_training_data_enhanced.jsonl .
cp data_files/followup_training_data.jsonl .
python src/followup/train_followup_model.py
# Saves to: ./followup_model/
```

**Parameters:**

| Param | Value |
|---|---|
| Base model | `t5-small` |
| Epochs | 5 |
| Batch size | 4 |
| Learning rate | 3e-4 |
| Warmup steps | 100 |
| Weight decay | 0.01 |
| Max input length | 512 tokens |
| Max output length | 128 tokens |

### Adding Training Data

Append new JSONL lines to `followup_training_data_enhanced.jsonl` and re-run the training script. The model will overwrite `./followup_model/`. Restart the server after retraining if `use_model=True` is configured in `generate_followups.py`.

---

## Troubleshooting

### Server won't start: LangChain version conflict

```
ImportError: cannot import name 'convert_to_json_schema' from 'langchain_core.utils.function_calling'
```

Fix by aligning versions:
```bash
pip install --upgrade langchain langchain-core langchain-huggingface
# or pin explicit compatible versions:
pip install langchain==0.1.20 langchain-core==0.1.48 langchain-huggingface==0.0.16
```

### Retrieval returns nothing / score is always 0.0

The `chroma_db/` directory is missing or empty. Run the ingestion pipeline:
```bash
python scripts/run_ingest.py
```

Verify the PDFs exist at `data/Getting_Started_with_Encrypta.pdf` and `data/Getting_Started_with_Password_Manager.pdf`. The server will continue to function without them (the I0th flow activates on every query), but AI answers will be low-confidence.

### LLM returns "technical difficulties" constantly

The `GROQ_API_KEY` is missing, expired, or has exhausted its quota. Check `config/.env`. The server falls back to an extractive snippet from retrieved documents when this happens, so conversations remain functional.
