# app.py - FastAPI web application
import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from ava_client import AvaClient
from agent_controller import controller_turn
from tools import SESSION
import uuid

# Configure logging to stdout (visible in Render logs)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Store Ava clients and logs per session
ava_clients: Dict[str, AvaClient] = {}
user_logs: Dict[str, List[Dict[str, Any]]] = {}
user_sessions: Dict[str, Dict[str, Any]] = {}

# Templates
templates = Jinja2Templates(directory="templates")

def get_or_create_ava_client(session_id: str) -> AvaClient:
    """Get or create Ava client for a session."""
    if session_id not in ava_clients:
        USER = os.getenv("AVA_USER", "amit")
        PASS = os.getenv("AVA_PASS", "sta6952907")
        ava = AvaClient(USER, PASS)
        ava.login()
        ava.get_session(force_new=True)
        ava_clients[session_id] = ava
    return ava_clients[session_id]

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main chat interface."""
    return templates.TemplateResponse("index.html", {"request": request})

class InitRequest(BaseModel):
    sqlite_path: str
    lead_id: str
    buyer_id: str
    escalation_phone: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

@app.post("/api/init")
async def init_session(data: InitRequest):
    """Initialize a new session with user credentials."""
    sqlite_path = data.sqlite_path.strip()
    lead_id = data.lead_id.strip()
    buyer_id = data.buyer_id.strip()
    escalation_phone = data.escalation_phone.strip()
    
    if not all([sqlite_path, lead_id, buyer_id, escalation_phone]):
        raise HTTPException(status_code=400, detail="All fields are required")
    
    # Create new session
    session_id = str(uuid.uuid4())
    
    # Store session data
    user_sessions[session_id] = {
        "sqlite_path": sqlite_path,
        "lead_id": int(lead_id) if lead_id.isdigit() else lead_id,
        "buyer_id": int(buyer_id) if buyer_id.isdigit() else buyer_id,
        "escalation_phone": escalation_phone,
    }
    
    # Initialize logs
    user_logs[session_id] = []
    
    # Create Ava client
    try:
        logger.info(f"[SESSION INIT] Initializing session {session_id[:8]} - sqlite_path: {sqlite_path}, lead_id: {lead_id}, buyer_id: {buyer_id}")
        ava = get_or_create_ava_client(session_id)
        logger.info(f"[SESSION INIT] Session {session_id[:8]} initialized successfully")
        return {"success": True, "session_id": session_id, "message": "Session initialized successfully"}
    except Exception as e:
        logger.error(f"[SESSION INIT] Failed to initialize session {session_id[:8]}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to initialize: {str(e)}")

@app.post("/api/chat")
async def chat(data: ChatRequest):
    """Handle a chat message."""
    session_id = data.session_id
    
    if not session_id or session_id not in user_sessions:
        raise HTTPException(status_code=400, detail="Invalid or missing session_id. Please initialize session first.")
    
    # Restore SESSION for this user
    sess_data = user_sessions[session_id]
    SESSION["sqlite_path"] = sess_data["sqlite_path"]
    SESSION["lead_id"] = sess_data["lead_id"]
    SESSION["buyer_id"] = sess_data["buyer_id"]
    SESSION["escalation_phone"] = sess_data["escalation_phone"]
    
    user_msg = data.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message is required")
    
    if user_msg.lower() in ("exit", "quit"):
        return {"reply": "Session ended. Thank you!"}
    
    # Log incoming user message
    logger.info(f"[SESSION {session_id[:8]}] User message: {user_msg}")
    
    try:
        ava = get_or_create_ava_client(session_id)
        logs = user_logs.get(session_id, [])
        reply = controller_turn(ava, user_msg, logs)
        user_logs[session_id] = logs  # Update logs
        
        # Log Ava's response
        logger.info(f"[SESSION {session_id[:8]}] Ava response: {reply[:200]}")
        
        return {"reply": reply}
    except Exception as e:
        logger.error(f"[SESSION {session_id[:8]}] Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/logs")
async def get_logs(session_id: Optional[str] = None):
    """Get recent logs for debugging."""
    if not session_id or session_id not in user_logs:
        raise HTTPException(status_code=400, detail="Invalid or missing session_id")
    
    logs = user_logs.get(session_id, [])
    return {"logs": logs[-10:]}

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('PORT', 8080))
    uvicorn.run(app, host='0.0.0.0', port=port)

