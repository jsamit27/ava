# cli_ava.py
import os
from typing import List, Dict, Any
from ava_client import AvaClient
from agent_controller import controller_turn
# Removed SESSION import - now using session_data parameter instead

def main():
    print("Enter beta DB sqlite_path:", end=" ")
    sqlite_path = input().strip()
    print("Enter lead_id:", end=" ")
    lead_id = input().strip()
    print("Enter buyer_id:", end=" ")
    buyer_id = input().strip()
    print("Enter escalation phone number:", end=" ")
    escalation_phone = input().strip()

    # Prepare session data (no longer using global SESSION)
    lead_id_int = int(lead_id) if lead_id.isdigit() else lead_id
    buyer_id_int = int(buyer_id) if buyer_id.isdigit() else buyer_id
    session_data = {
        "sqlite_path": sqlite_path,
        "lead_id": lead_id_int,
        "buyer_id": buyer_id_int,
        "escalation_phone": escalation_phone,
    }

    # Ava creds (from your message)
    AVA_USER = os.getenv("AVA_USER", "amit")
    AVA_PASS = os.getenv("AVA_PASS", "sta6952907")
    
    # Use lead_id as user_id for sessions, but "amit" + password for login
    lead_id_str = str(lead_id_int)
    
    # AvaClient is a class, it has login, getsessions etc as methods in the class 
    ava = AvaClient(user_id=lead_id_str, ava_username=AVA_USER, ava_password=AVA_PASS)
    ava.login()
    ava.get_session(force_new=True)
    ava.connect_ws()

    logs: List[Dict[str, Any]] = []

    print("\nAva (Ava-backed) is ready. Type your message (or 'exit', '/logs').\n")
    while True:
        user = input("You: ").strip()
        if user.lower() in ("exit", "quit"):
            break
        if user == "/logs":
            from pprint import pprint
            print("---- recent logs ----")
            for row in logs[-5:]:
                pprint(row, width=100)
            print("---------------------")
            continue

        try:
            reply = controller_turn(ava, user, logs, session_data)
            print(f"Ava: {reply}\n")
        except Exception as e:
            print("Ava (error):", e)

    ava.close()
    print("Bye!")

if __name__ == "__main__":
    main()
