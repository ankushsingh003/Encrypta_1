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
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom Styling (Glassmorphism & Premium UI) ---
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

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: rgba(26, 27, 38, 0.8) !important;
        backdrop-filter: blur(10px);
        border-right: 1px solid rgba(122, 162, 247, 0.2);
    }

    /* Chat Bubbles Styling */
    .stChatMessage {
        background-color: rgba(36, 40, 59, 0.6) !important;
        backdrop-filter: blur(5px);
        border-radius: 15px !important;
        border: 1px solid rgba(122, 162, 247, 0.1) !important;
        margin-bottom: 20px !important;
        padding: 15px !important;
        transition: transform 0.2s ease-in-out;
    }
    
    .stChatMessage:hover {
        transform: translateY(-2px);
        border-color: rgba(122, 162, 247, 0.4) !important;
    }

    /* Assistant specific bubble accent */
    [data-testid="chatAvatarIcon-assistant"] {
        background-color: #7aa2f7 !important;
    }

    /* Custom Header */
    .header-container {
        display: flex;
        align-items: center;
        gap: 15px;
        margin-bottom: 30px;
    }
    .header-logo {
        font-size: 2.5rem;
        background: linear-gradient(90deg, #7aa2f7, #bb9af7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 600;
    }

    /* Follow-up Buttons Container */
    .followup-container {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        margin-top: 10px;
    }
    
    /* Input Box Styling */
    .stChatInputContainer {
        border-top: 1px solid rgba(122, 162, 247, 0.2) !important;
        background-color: #1a1b26 !important;
    }
</style>
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
        # In background threads, session_state might not be available directly
        # but with add_script_run_ctx it should work for the specific session.
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

# --- Sidebar Content ---
with st.sidebar:
    st.markdown('<div class="header-logo">Encrypta</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("### 🛡️ Secure AI Support")
    st.info("Ask anything about Encrypta's password management, security, and account setup.")
    
    st.markdown("### 📊 System Status")
    st.write("🟢 **Backend**: Online")
    st.write("🟢 **RAG Pipeline**: Active")
    st.write("🟢 **LLM (Groq)**: Ready")
    
    st.markdown("---")
    if st.button("Clear Chat History", use_container_width=True):
        st.session_state.history = []
        st.rerun()

# --- Main UI ---
st.markdown('<div class="header-container"><span class="header-logo">Support Assistant</span></div>', unsafe_allow_html=True)

# Render Chat History
for msg in st.session_state.history:
    role = "user" if msg['sender_role'] in ["user", "customer"] else "assistant"
    avatar = "🛡️" if role == "assistant" else "👤"
    
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg['content'])
        
        # Display Follow-up Questions as Interactive Buttons
        metadata = msg.get('metadata')
        if metadata and metadata.get('follow_up_questions'):
            st.markdown('<div class="followup-container">', unsafe_allow_html=True)
            cols = st.columns(len(metadata['follow_up_questions']))
            for i, q in enumerate(metadata['follow_up_questions']):
                if cols[i].button(q, key=f"fu_{msg['timestamp']}_{i}", type="secondary", use_container_width=True):
                    # Send follow-up question
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
            # We don't append to history here because the WS will broadcast it back to us
        except Exception as e:
            st.error(f"Failed to send message: {e}")
        st.session_state.user_input = "" # Clear input

st.chat_input("How can I help you today?", key="user_input", on_submit=handle_input)
