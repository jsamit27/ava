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
    def __init__(self, user_id: str, ava_username: str = "amit", ava_password: Optional[str] = None, *, token: Optional[str] = None):
        """
        Initialize AvaClient.
        
        Args:
            user_id: The user ID to use for sessions and messages (typically lead_id)
            ava_username: Ava account username for login (default: "amit")
            ava_password: Ava account password for login
            token: Optional pre-existing auth token
        """
        self.user_id = user_id  # Used for sessions and WebSocket messages
        self.ava_username = ava_username  # Used for login
        self._ava_password = ava_password  # Used for login
        self.token = token
        self.session_id: Optional[str] = None  # keep as string

    # ---------- Auth / session ----------
    def login(self) -> str:
        """POST /api/v1/user -> authorization token. Uses ava_username and ava_password for login."""
        if self.token:
            return self.token
        if not self._ava_password:
            raise RuntimeError("No password provided and no token set.")
        r = requests.post(
            "https://ava.andrew-chat.com/api/v1/user",
            headers={"Content-Type": "application/json"},
            data=json.dumps({"username": self.ava_username, "password": self._ava_password}),
            timeout=30,
        )
        r.raise_for_status()
        self.token = r.json()["authorization"]
        return self.token

    def close_session(self, session_id: Optional[str] = None) -> bool:
        """Close/delete an Ava session. Returns True if successful, False otherwise."""
        if not self.token:
            self.login()
        
        session_to_close = session_id or self.session_id
        if not session_to_close:
            log_msg = "[AVA API] No session_id to close"
            logger.info(log_msg)
            print(log_msg, flush=True)
            return False
        
        try:
            url = f"https://ava.andrew-chat.com/api/v1/session/{self.user_id}"
            payload = {"session_id": session_to_close}
            r = requests.post(
                url,
                headers={"Authorization": self.token, "Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=30
            )
            r.raise_for_status()
            log_msg = f"[AVA API] Successfully closed session: {session_to_close[:8]}"
            logger.info(log_msg)
            print(log_msg, flush=True)
            return True
        except Exception as e:
            log_msg = f"[AVA API] Failed to close session {session_to_close[:8]}: {e}"
            logger.warning(log_msg)
            print(log_msg, flush=True)
            return False

    def get_session(self, *, force_new: bool = False) -> str:
        """GET Prism session id as a string."""
        if not self.token:
            self.login()
        
        # If force_new and we have an existing session, close it first
        if force_new and self.session_id:
            log_msg = f"[AVA API] Closing existing session {self.session_id[:8]} before creating new one"
            logger.info(log_msg)
            print(log_msg, flush=True)
            self.close_session()
            self.session_id = None  # Clear it after closing
        
        url = f"https://prism.andrew-chat.com/api/v1/prism/get_session/{self.user_id}/ava"
        if force_new:
            log_msg = f"[AVA API] Requesting NEW session with force_new=True"
            logger.info(log_msg)
            print(log_msg, flush=True)
        r = requests.get(url, headers={"Authorization": self.token}, timeout=30)
        r.raise_for_status()
        data = r.json()
        new_session_id = str(data["id"])
        
        # Log if we got the same session_id as before
        if self.session_id and new_session_id == self.session_id:
            log_msg = f"[AVA API] WARNING: Got same session_id as before: {new_session_id[:8]} (Ava server may be reusing sessions)"
            logger.warning(log_msg)
            print(log_msg, flush=True)
        else:
            log_msg = f"[AVA API] Got session_id: {new_session_id[:8]} (previous: {self.session_id[:8] if self.session_id else 'none'})"
            logger.info(log_msg)
            print(log_msg, flush=True)
        
        self.session_id = new_session_id
        return self.session_id

    # Optional no-ops so your CLI doesn't break
    def connect_ws(self) -> None:
        """No-op: ask_once opens WS per call."""
        return

    def close(self) -> None:
        """No-op: ask_once closes WS per call."""
        return

    def _send_message(self, prompt: str) -> Optional[str]:
        """
        Internal method to send a message and get response.
        Returns response text or None if no response.
        Tries minimal payload, falls back to legacy payload if needed.
        """
        if not self.token:
            self.login()
        if not self.session_id:
            self.get_session()

        # Attempt 1: minimal schema
        try:
            ws = create_connection(
                f"wss://ava.andrew-chat.com/api/v1/stream?token={self.token}",
                header=["Origin: https://ava.andrew-chat.com"],
            )
            minimal = {
                "user_id": self.user_id,
                "session_id": self.session_id,
                "message": prompt,
            }
            
            ws.send(json.dumps(minimal, separators=(",", ":")))
            text, bad = _read_stream(ws)
            ws.close()
            if not bad and text:
                return text
        except Exception as e:
            log_msg = f"[AVA API] Minimal payload error: {e}"
            logger.warning(log_msg)
            print(log_msg, flush=True)

        # Attempt 2: legacy payload
        try:
            ws = create_connection(
                f"wss://ava.andrew-chat.com/api/v1/stream?token={self.token}",
                header=["Origin: https://ava.andrew-chat.com"],
            )
            legacy = {
                "action": "create",
                "message": prompt,
                "user_id": self.user_id,
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
                return text2
        except Exception as e:
            log_msg = f"[AVA API] Legacy payload error: {e}"
            logger.warning(log_msg)
            print(log_msg, flush=True)
        
        return None

    # ---------- Chat once ----------
    def ask_once(self, prompt: str) -> str:
        """
        Send one user message and return concatenated reply text.
        Implements retry logic with session recreation ONLY when no response.
        Retry flow:
        1. Try to get response
        2. If no response, retry once
        3. If still no response, close session, create new session with same user_id, retry
        4. If still no response, close session, create new session, retry again
        """
        # Log what we're sending to Ava API
        log_msg = f"[AVA API] Sending message to Ava (user_id: {self.user_id}, session: {self.session_id[:8] if self.session_id else 'none'}, length: {len(prompt)} chars)"
        logger.info(log_msg)
        print(log_msg, flush=True)
        logger.debug(f"[AVA API] Message preview: {prompt[:300]}...")
        
        # Attempt 1: Try to get response
        response = self._send_message(prompt)
        if response:
            log_msg = f"[AVA API] Received response from Ava (length: {len(response)} chars)"
            logger.info(log_msg)
            print(log_msg, flush=True)
            logger.debug(f"[AVA API] Response preview: {response[:300]}...")
            return response
        
        # Attempt 2: Retry once (session might be temporarily stuck)
        log_msg = f"[AVA API] No response on first attempt, retrying once..."
        logger.warning(log_msg)
        print(log_msg, flush=True)
        response = self._send_message(prompt)
        if response:
            log_msg = f"[AVA API] Received response on retry (length: {len(response)} chars)"
            logger.info(log_msg)
            print(log_msg, flush=True)
            return response
        
        # Attempt 3: Session might be "filled" - close it and create new one with same user_id
        log_msg = f"[AVA API] No response after retry, session may be filled. Closing session and creating new one with user_id={self.user_id}..."
        logger.warning(log_msg)
        print(log_msg, flush=True)
        if self.session_id:
            self.close_session()
        self.session_id = None
        self.get_session(force_new=True)
        response = self._send_message(prompt)
        if response:
            log_msg = f"[AVA API] Received response after session recreation (length: {len(response)} chars)"
            logger.info(log_msg)
            print(log_msg, flush=True)
            return response
        
        # Attempt 4: Close session again, create new session, retry one more time
        log_msg = f"[AVA API] Still no response, closing session again and creating new one for final retry (user_id={self.user_id})..."
        logger.warning(log_msg)
        print(log_msg, flush=True)
        if self.session_id:
            self.close_session()
        self.session_id = None
        self.get_session(force_new=True)
        response = self._send_message(prompt)
        if response:
            log_msg = f"[AVA API] Received response after second session recreation (length: {len(response)} chars)"
            logger.info(log_msg)
            print(log_msg, flush=True)
            return response
        
        # All attempts failed
        log_msg = f"[AVA API] All retry attempts failed, no response from Ava"
        logger.error(log_msg)
        print(log_msg, flush=True)
        return "Sorry—no response from Ava after multiple attempts. Please try again."
