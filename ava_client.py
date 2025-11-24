# ava_client.py
"""
AvaClient: small helper to
- log in (get token)
- fetch a Prism session id (string)
- send one prompt over WS and read the streamed reply
It automatically falls back to the legacy payload if the minimal one fails.
"""

import json
import logging
from typing import Optional, Tuple
import requests
from websocket import create_connection

# Configure logging
logger = logging.getLogger(__name__)

END_MARKER = "<<END_OF_RESPONSE>>"

def _read_stream(ws) -> Tuple[str, bool]:
    """Collect streamed frames. Return (text, saw_bad_request)."""
    chunks = []
    saw_bad = False
    while True:
        try:
            frame = ws.recv()
        except Exception:
            break
        if not frame:
            break
        if isinstance(frame, str) and frame.strip().lower().startswith("bad request"):
            saw_bad = True
            break
        try:
            obj = json.loads(frame)
        except Exception:
            chunks.append(str(frame))
            continue
        if isinstance(obj, dict):
            if obj.get("response") == END_MARKER:
                break
            if "text" in obj:
                chunks.append(str(obj["text"]))
    return "".join(chunks).strip(), saw_bad


class AvaClient:
    def __init__(self, user: str, password: Optional[str] = None, *, token: Optional[str] = None):
        self.user = user
        self._password = password
        self.token = token
        self.session_id: Optional[str] = None  # keep as string

    # ---------- Auth / session ----------
    def login(self) -> str:
        """POST /api/v1/user -> authorization token."""
        if self.token:
            return self.token
        if not self._password:
            raise RuntimeError("No password provided and no token set.")
        r = requests.post(
            "https://ava.andrew-chat.com/api/v1/user",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"username": self.user, "password": self._password}),
            timeout=15,
        )
        r.raise_for_status()
        self.token = r.json()["authorization"]
        return self.token

    def get_session(self, *, force_new: bool = False) -> str:
        """GET Prism session id as a string."""
        if not self.token:
            self.login()
        url = f"https://prism.andrew-chat.com/api/v1/prism/get_session/{self.user}/ava"
        if force_new:
            url += "?new=true"
        r = requests.get(url, headers={"Authorization": self.token}, timeout=15)
        r.raise_for_status()
        data = r.json()
        self.session_id = str(data["id"])
        return self.session_id

    # Optional no-ops so your CLI doesn't break
    def connect_ws(self) -> None:
        """No-op: ask_once opens WS per call."""
        return

    def close(self) -> None:
        """No-op: ask_once closes WS per call."""
        return

    # ---------- Chat once ----------
    def ask_once(self, prompt: str) -> str:
        """
        Send one user message and return concatenated reply text.
        Tries minimal payload, falls back to legacy payload if needed.
        """
        if not self.token:
            self.login()
        if not self.session_id:
            self.get_session()

        # Attempt 1: minimal schema
        ws = create_connection(
            f"wss://ava.andrew-chat.com/api/v1/stream?token={self.token}",
            header=["Origin: https://ava.andrew-chat.com"],
        )
        minimal = {
            "user_id": self.user,
            "session_id": self.session_id,  # string
            "message": prompt,
        }
        
        # Log what we're sending to Ava API
        log_msg = f"[AVA API] Sending message to Ava (session: {self.session_id[:8]}, length: {len(prompt)} chars)"
        logger.info(log_msg)
        print(log_msg, flush=True)
        logger.debug(f"[AVA API] Message preview: {prompt[:300]}...")
        
        ws.send(json.dumps(minimal, separators=(",", ":")))
        text, bad = _read_stream(ws)
        ws.close()
        if not bad and text:
            # Log what we received from Ava API
            log_msg = f"[AVA API] Received response from Ava (length: {len(text)} chars)"
            logger.info(log_msg)
            print(log_msg, flush=True)
            logger.debug(f"[AVA API] Response preview: {text[:300]}...")
            return text

        # Attempt 2: legacy payload (temporary server requirement)
        log_msg = f"[AVA API] Minimal payload failed, trying legacy payload"
        logger.info(log_msg)
        print(log_msg, flush=True)
        ws = create_connection(
            f"wss://ava.andrew-chat.com/api/v1/stream?token={self.token}",
            header=["Origin: https://ava.andrew-chat.com"],
        )
        legacy = {
            "action": "create",
            "message": prompt,
            "user_id": self.user,
            "session_id": self.session_id,
            "car": {
                "vin": "",
                "year": -1,
                "make": "",
                "model": "",
                "trim": "",
                "mileage": -1,
                "condition": 0,
                "color": "blue",
                "region": "WC",
            },
        }
        ws.send(json.dumps(legacy, separators=(",", ":")))
        text2, _ = _read_stream(ws)
        ws.close()
        
        if text2:
            log_msg = f"[AVA API] Received response via legacy payload (length: {len(text2)} chars)"
            logger.info(log_msg)
            print(log_msg, flush=True)
            logger.debug(f"[AVA API] Response preview: {text2[:300]}...")
        else:
            log_msg = f"[AVA API] No response received from Ava"
            logger.warning(log_msg)
            print(log_msg, flush=True)
        
        return text2 or "Sorry—no response from Ava."
