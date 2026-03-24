import streamlit as st
import json
import asyncio
import threading
from datetime import datetime
import websocket

st.set_page_config(page_title="Encrypta AI Assistant", layout="wide")

if "history" not in st.session_state:
    st.session_state.history = []
if "active_route" not in st.session_state:
    st.session_state.active_route = "customer_to_faq"

st.title("Encrypta Omnichannel Support")

def on_message(ws, message):
    data = json.loads(message)
    st.session_state.history.append(data)
    st.rerun()

def run_ws():
    ws_url = f"ws://localhost:8000/ws/demo-session"
    ws = websocket.WebSocketApp(ws_url, on_message=on_message)
    ws.run_forever()

if "ws_thread" not in st.session_state:
    st.session_state.ws_thread = threading.Thread(target=run_ws, daemon=True)
    st.session_state.ws_thread.start()

# Render History
for msg in st.session_state.history:
    role = "user" if msg['sender_role'] == "user" or msg['sender_role'] == "customer" else "assistant"
    with st.chat_message(role):
        st.write(msg['content'])
        if msg.get('metadata') and msg['metadata'].get('follow_up_questions'):
            st.info(f"Clarification: {msg['metadata']['follow_up_questions'][0]}")

# Chat Input
prompt = st.chat_input("Ask a question...")
if prompt:
    # Send via websocket
    ws = websocket.create_connection("ws://localhost:8000/ws/demo-session")
    ws.send(json.dumps({"type": "user_message", "content": prompt, "sender_role": "customer", "channel": "text"}))
    ws.close()
    st.rerun()
