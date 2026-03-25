import streamlit as st
import json
import asyncio
import threading
from datetime import datetime
import websocket
import time

# --- Page Configuration ---
st.set_page_config(
    page_title="Encrypta AI Assistant",
    page_icon="🛡️",
    layout="centered", # Centered layout for a more focused experience
    initial_sidebar_state="collapsed" # Hide sidebar by default
)

# --- Custom Styling (Glassmorphism & Centered Layout & Watermark) ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }

    /* Main Background */
    .stApp {
        background: radial-gradient(circle at top right, #1a1b26, #16161e);
        color: #a9b1d6;
    }
    
    /* Hide Sidebar Completely */
    [data-testid="stSidebar"] {
        display: none;
    }

    /* Watermark Styling */
    .watermark {
        position: fixed;
        top: 55%;
        left: 50%;
        transform: translate(-50%, -50%);
        font-size: 3.5rem;
        font-weight: 600;
        color: rgba(122, 162, 247, 0.08); /* Low opacity */
        text-transform: lowercase;
        white-space: nowrap;
        pointer-events: none;
        z-index: -1; /* Place behind everything */
        user-select: none;
        text-align: center;
    }

    /* Chat Bubbles Styling */
    .stChatMessage {
        background-color: rgba(36, 40, 59, 0.4) !important;
        backdrop-filter: blur(8px);
        border-radius: 12px !important;
        border: 1px solid rgba(122, 162, 247, 0.1) !important;
        margin-bottom: 12px !important;
        padding: 12px !important;
    }

    /* Custom Header */
    .header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 2rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid rgba(122, 162, 247, 0.2);
    }
    .header-logo {
        font-size: 1.8rem;
        background: linear-gradient(90deg, #7aa2f7, #bb9af7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 600;
    }

    /* Follow-up Buttons */
    .stButton>button {
        border-radius: 8px !important;
    }
</style>

<div class="watermark">hii, there , this is agent trisha</div>
""", unsafe_allow_html=True)

from streamlit.runtime.scriptrunner import add_script_run_ctx

# --- Session State Initialization ---
if "history" not in st.session_state:
    st.session_state.history = []
if "session_id" not in st.session_state:
    st.session_state.session_id = f"sess-{int(time.time())}"

# --- WebSocket Handling ---
def on_message(ws, message):
    try:
        data = json.loads(message)
        if "history" in st.session_state:
            st.session_state.history.append(data)
            st.rerun()
    except Exception as e:
        print(f"WS Error: {e}")

def run_ws():
    ws_url = f"ws://127.0.0.1:8000/ws/{st.session_state.session_id}"
    ws = websocket.WebSocketApp(ws_url, on_message=on_message)
    ws.run_forever()

if "ws_thread" not in st.session_state:
    ctx = st.runtime.scriptrunner.get_script_run_ctx()
    st.session_state.ws_thread = threading.Thread(target=run_ws, daemon=True)
    add_script_run_ctx(st.session_state.ws_thread, ctx)
    st.session_state.ws_thread.start()

# --- Main UI ---
header_col1, header_col2 = st.columns([4, 1])
with header_col1:
    st.markdown('<div class="header-logo">Encrypta AI</div>', unsafe_allow_html=True)
with header_col2:
    if st.button("Clear History", type="secondary", use_container_width=True):
        st.session_state.history = []
        st.rerun()

# Render Chat History
for msg in st.session_state.history:
    role = "user" if msg['sender_role'] in ["user", "customer"] else "assistant"
    avatar = "🛡️" if role == "assistant" else "👤"
    
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg['content'])
        
        # Display Follow-up Questions as Interactive Buttons
        metadata = msg.get('metadata')
        if metadata and metadata.get('follow_up_questions'):
            cols = st.columns(len(metadata['follow_up_questions']))
            for i, q in enumerate(metadata['follow_up_questions']):
                if cols[i].button(q, key=f"fu_{msg['timestamp']}_{i}", use_container_width=True):
                    try:
                        ws_temp = websocket.create_connection(f"ws://127.0.0.1:8000/ws/{st.session_state.session_id}")
                        ws_temp.send(json.dumps({
                            "type": "user_message", 
                            "content": q, 
                            "sender_role": "user", 
                            "channel": "web"
                        }))
                        ws_temp.close()
                    except Exception as e:
                        st.error(f"Failed to send follow-up: {e}")
            st.markdown('</div>', unsafe_allow_html=True)

# --- Chat Input ---
def handle_input():
    if st.session_state.user_input:
        content = st.session_state.user_input
        try:
            ws_temp = websocket.create_connection(f"ws://127.0.0.1:8000/ws/{st.session_state.session_id}")
            ws_temp.send(json.dumps({
                "type": "user_message", 
                "content": content, 
                "sender_role": "user", 
                "channel": "web"
            }))
            ws_temp.close()
        except Exception as e:
            st.error(f"Failed to send message: {e}")
        st.session_state.user_input = "" 

st.chat_input("Ask Trisha anything...", key="user_input", on_submit=handle_input)
