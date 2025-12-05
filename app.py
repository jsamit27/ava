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

# Configure logging to stdout (visible in Render logs)
# Force logging to stdout/stderr so it appears in Render logs
import sys
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)  # Explicitly use stdout
    ],
    force=True  # Override any existing configuration
)
logger = logging.getLogger(__name__)
# Also set root logger level
logging.getLogger().setLevel(logging.INFO)

app = FastAPI()

# Store Ava clients and logs per session
ava_clients: Dict[str, AvaClient] = {}
user_logs: Dict[str, List[Dict[str, Any]]] = {}
user_sessions: Dict[str, Dict[str, Any]] = {}

# Templates
templates = Jinja2Templates(directory="templates")

def get_ava_client(session_id: str) -> AvaClient:
    """Get Ava client for a session (session_id is now Ava's session_id)."""
    if session_id not in ava_clients:
        raise HTTPException(status_code=400, detail="Session not found. Please initialize session first.")
    return ava_clients[session_id]

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main chat interface."""
    return templates.TemplateResponse("index.html", {"request": request})

class InitRequest(BaseModel):
    lead_id: str
    buyer_id: str
    escalation_phone: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

@app.post("/api/init")
async def init_session(data: InitRequest):
    """Initialize a new session with user credentials."""
    lead_id = data.lead_id.strip()
    buyer_id = data.buyer_id.strip()
    escalation_phone = data.escalation_phone.strip()
    
    if not all([lead_id, buyer_id, escalation_phone]):
        raise HTTPException(status_code=400, detail="lead_id, buyer_id, and escalation_phone are required")
    
    # Require DATABASE_URL (PostgreSQL on Render)
    db_connection = os.getenv("DATABASE_URL")
    if not db_connection:
        error_msg = "DATABASE_URL environment variable is required. Please configure PostgreSQL database."
        logger.error(error_msg)
        print(error_msg, flush=True)
        raise HTTPException(status_code=500, detail=error_msg)
    
    logger.info(f"[SESSION INIT] Using PostgreSQL database (DATABASE_URL is set)")
    
    # Create Ava client using lead_id as the user_id
    # This ensures each lead gets their own conversation context
    try:
        # Use lead_id as the user identifier for Ava sessions
        lead_id_str = str(lead_id)
        PASS = os.getenv("AVA_PASS", "sta6952907")
        
        log_msg = f"[SESSION INIT] Creating Ava session with user_id={lead_id_str} (lead_id)"
        logger.info(log_msg)
        print(log_msg, flush=True)
        
        # Check if we already have a session for this lead_id
        # Look for existing session by checking if any ava_clients has this user_id
        existing_session_id = None
        for sess_id, ava_client in ava_clients.items():
            if ava_client.user == lead_id_str:
                existing_session_id = sess_id
                log_msg = f"[SESSION INIT] Found existing session {sess_id[:8]} for lead_id={lead_id_str}, reusing it"
                logger.info(log_msg)
                print(log_msg, flush=True)
                break
        
        if existing_session_id:
            # Reuse existing session - don't create a new one
            ava = ava_clients[existing_session_id]
            ava_session_id = existing_session_id
        else:
            # Create new AvaClient with lead_id as user_id
            ava = AvaClient(lead_id_str, PASS)  # Use lead_id as user_id
            ava.login()
            # Get Ava's session_id - this will be our primary key
            ava_session_id = ava.get_session(force_new=True)
            
            log_msg = f"[SESSION INIT] Created new Ava session_id: {ava_session_id} (full ID) for lead_id={lead_id_str}"
            logger.info(log_msg)
            print(log_msg, flush=True)
            
            # Store session data using Ava's session_id as the key
            user_sessions[ava_session_id] = {
                "sqlite_path": db_connection,  # PostgreSQL URL (stored in sqlite_path for compatibility with tools)
                "lead_id": int(lead_id) if lead_id.isdigit() else lead_id,
                "buyer_id": int(buyer_id) if buyer_id.isdigit() else buyer_id,
                "escalation_phone": escalation_phone,
            }
            
            # Initialize logs using Ava's session_id
            user_logs[ava_session_id] = []
            
            # Store AvaClient using Ava's session_id
            ava_clients[ava_session_id] = ava
        
        log_msg = f"[SESSION INIT] Session {ava_session_id[:8]} initialized successfully for lead_id={lead_id}, buyer_id={buyer_id}"
        logger.info(log_msg)
        print(log_msg, flush=True)
        return {"success": True, "session_id": ava_session_id, "message": "Session initialized successfully"}
    except Exception as e:
        error_msg = f"[SESSION INIT] Failed to initialize session: {str(e)}"
        logger.error(error_msg, exc_info=True)
        print(error_msg, flush=True)
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
    
    # Log incoming user message (both logger and print for visibility)
    log_msg = f"[SESSION {session_id[:8]}] User message: {user_msg}"
    logger.info(log_msg)
    print(log_msg, flush=True)  # Also print to ensure it shows in Render logs
    
    try:
        ava = get_ava_client(session_id)
        logs = user_logs.get(session_id, [])
        reply = controller_turn(ava, user_msg, logs)
        user_logs[session_id] = logs  # Update logs
        
        # Log Ava's response (both logger and print for visibility)
        log_msg = f"[SESSION {session_id[:8]}] Ava response: {reply[:200]}"
        logger.info(log_msg)
        print(log_msg, flush=True)  # Also print to ensure it shows in Render logs
        
        return {"reply": reply}
    except Exception as e:
        error_msg = f"[SESSION {session_id[:8]}] Error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        print(error_msg, flush=True)
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

