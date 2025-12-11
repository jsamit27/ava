# agent_controller.py
"""
Single turn controller:
- Ask planner (via Ava) for a plan (chat or tool)
- If chat: return answer
- If tool: dispatch local Python tool, then return a user-facing summary
- Log each step into `logs` for debugging (/logs in CLI)
"""

import logging
import json
import re
from typing import Dict, Any, List
from ava_client import AvaClient
from planner import build_planner_prompt, extract_json_block, validate_plan

# Configure logging
logger = logging.getLogger(__name__)

# Import your actual tool implementations (not the LangChain wrappers)
from all_tools import (
    car_retrieve,
    car_add,
    car_update,
    get_all_cars,
    get_buyer_availability,
    add_buyer_schedule,
    remove_buyer_schedule,
    update_buyer_schedule,
    pickup_retrieve,
    pickup_add,
    pickup_update,
    get_all_pickups,
    get_closest,
    send_escalate_message,
)
from db_connection import get_db_connection, execute_query
# Map planner -> concrete Python call
def _dispatch_tool(name: str, args: Dict[str, Any], session_data: Dict[str, Any]) -> Dict[str, Any]:
    sp = session_data.get("sqlite_path")

    if name == "car_retrieve":
        return car_retrieve(sqlite_path=sp, query=args)

    if name == "car_add":
        patch = dict(args or {})
        patch.setdefault("lead_id", session_data.get("lead_id"))
        # Block buyer_offer_cents - only GMTV employees can set this
        if "buyer_offer_cents" in patch:
            return {"status": "error", "code": "FORBIDDEN", "message": "Ava cannot set buyer_offer_cents. Only GMTV employees can set the company's offer."}
        return car_add(sqlite_path=sp, patch=patch)

    # ADDED A LOGIC TO CHECK IF CAR_ID IS PRESENT IN THE ARGS IF NOT THEN RETRIRVE THE CAR AND THEN USE CAR_ID
    # FROM THAT TO UPDATE THE CAR 
    if name == "car_update":
        # Check if car_id is already provided
        car_id = args.get("car_id")
        
        # If no car_id, try to resolve it using car_retrieve
        if not car_id:
            # Extract potential identifier fields (car_retrieve priority: car_id > vin > model > make > year)
            query_fields = {}
            for field in ["vin", "make", "model", "year"]:
                if field in args and args[field]:
                    query_fields[field] = args[field]
            
            if not query_fields:
                return {"status": "error", "code": "INVALID_INPUT", 
                        "message": "Provide car_id, vin, make, model, or year to identify the car to update."}
            
            # Call car_retrieve to get car_id
            retrieve_result = car_retrieve(sqlite_path=sp, query=query_fields)
            
            if retrieve_result["status"] == "error":
                return retrieve_result  # Return the error (NOT_FOUND, etc.)
            elif retrieve_result["status"] == "unsure":
                # Ambiguous match - return helpful error
                return {
                    "status": "error",
                    "code": "AMBIGUOUS",
                    "message": retrieve_result.get("message", "Multiple cars match. Please provide VIN or car_id to uniquely identify the car."),
                    "data": retrieve_result.get("data", {})
                }
            
            # Extract car_id from the retrieved car
            car_data = retrieve_result.get("data", {})
            car = car_data.get("car", {})
            car_id = car.get("id")
            
            if not car_id:
                return {"status": "error", "code": "TXN_FAILED", 
                        "message": "Could not extract car_id from retrieved car."}
        
        # Build patch: exclude identifier fields and car_id
        excluded_fields = {"car_id", "vin", "make", "model", "year"}
        patch = {k: v for k, v in args.items() if k not in excluded_fields and v is not None}
        
        # Block buyer_offer_cents - only GMTV employees can set this
        if "buyer_offer_cents" in patch:
            return {"status": "error", "code": "FORBIDDEN", 
                    "message": "Ava cannot set buyer_offer_cents. Only GMTV employees can set the company's offer."}
        
        # Now call car_update with resolved car_id
        return car_update(car_id=car_id, sqlite_path=sp, patch=patch)

    if name == "get_all_cars":
        return get_all_cars(sqlite_path=sp)

    if name == "get_buyer_availability":
        return get_buyer_availability(sqlite_path=sp, buyer_id=session_data.get("buyer_id"))

    if name == "add_buyer_schedule":
        return add_buyer_schedule(buyer_id=session_data.get("buyer_id"), sqlite_path=sp, patch=args)

    if name == "remove_buyer_schedule":
        schedule_time = args.get("schedule_time", "")
        return remove_buyer_schedule(buyer_id=session_data.get("buyer_id"), sqlite_path=sp, schedule_time=schedule_time)

    if name == "update_buyer_schedule":
        schedule_time = args.get("schedule_time", "")
        # Extract schedule_time and use rest as patch
        patch = {k: v for k, v in args.items() if k != "schedule_time" and v is not None}
        # Map new_schedule_time to schedule_time in patch
        if "new_schedule_time" in patch:
            patch["schedule_time"] = patch.pop("new_schedule_time")
        return update_buyer_schedule(buyer_id=session_data.get("buyer_id"), sqlite_path=sp, schedule_time=schedule_time, patch=patch)

    if name == "pickup_retrieve":
        # Check if pick_up_id is already provided
        pick_up_id = args.get("pick_up_id")
        
        # If no pick_up_id, try to resolve it using car_id (via car_retrieve if needed)
        
        # THIS IS USED TO GET THE CAR_ID AND FRO THERE QUERY THE PICKUP DB TO GET THE PICKUP DETAILS. 
        
        if not pick_up_id:
            # Extract potential car identifier fields
            car_query_fields = {}
            for field in ["car_id", "vin", "make", "model", "year"]:
                if field in args and args[field]:
                    car_query_fields[field] = args[field]
            
            if not car_query_fields:
                return {"status": "error", "code": "INVALID_INPUT", 
                        "message": "I need to know which car you're referring to. Please provide the VIN, or tell me the make, model, and year of the car."}
            
            # Resolve car_id using car_retrieve
            car_result = car_retrieve(sqlite_path=sp, query=car_query_fields)
            
            if car_result["status"] == "error":
                return car_result
            elif car_result["status"] == "unsure":
                return {
                    "status": "error",
                    "code": "AMBIGUOUS",
                    "message": "I found multiple cars matching that description. Could you provide the VIN to help me identify the exact car?",
                    "data": car_result.get("data", {})
                }
            
            # Extract car_id from retrieved car
            car_data = car_result.get("data", {})
            car = car_data.get("car", {})
            resolved_car_id = car.get("id")
            
            if not resolved_car_id:
                return {"status": "error", "code": "TXN_FAILED", 
                        "message": "I had trouble finding that car. Please try again with more details."}
            
            # Find pickup(s) by car_id
            try:
                conn, is_pg = get_db_connection(sp)
            except Exception as e:
                return {"status": "error", "code": "DB_UNAVAILABLE", 
                        "message": f"Could not open database: {e}", "data": {}}
            
            try:
                cur = execute_query(conn, is_pg, "SELECT pick_up_id FROM pickup WHERE car_id = ?", (resolved_car_id,))
                pickups = cur.fetchall()
                
                if not pickups:
                    return {"status": "error", "code": "NOT_FOUND", 
                            "message": "I couldn't find a pickup scheduled for that car.", 
                            "data": {"car_id": resolved_car_id}}
                
                if len(pickups) > 1:
                    # Handle both SQLite (Row objects) and PostgreSQL (dicts)
                    pickup_ids = []
                    for p in pickups:
                        if isinstance(p, dict):
                            pickup_ids.append(p["pick_up_id"])
                        else:
                            # SQLite Row object or tuple
                            pickup_ids.append(p[0] if isinstance(p, tuple) else p["pick_up_id"])
                    return {
                        "status": "error",
                        "code": "AMBIGUOUS",
                        "message": "I found multiple pickups for this car. Could you provide more details (like the address or pickup date) to help me identify which one you mean?",
                        "data": {"car_id": resolved_car_id, "pickup_ids": pickup_ids}
                    }
                
                # Exactly one pickup found
                first_pickup = pickups[0]
                if isinstance(first_pickup, dict):
                    pick_up_id = first_pickup["pick_up_id"]
                else:
                    # SQLite Row object or tuple
                    pick_up_id = first_pickup[0] if isinstance(first_pickup, tuple) else first_pickup["pick_up_id"]
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        
        # Now call pickup_retrieve with resolved pick_up_id
        return pickup_retrieve(pick_up_id=pick_up_id, sqlite_path=sp)

    if name == "pickup_add":
        return pickup_add(sqlite_path=sp, patch=args)

    if name == "pickup_update":
        # Check if pick_up_id is already provided
        pick_up_id = args.get("pick_up_id")
        
        # If no pick_up_id, try to resolve it using car_id (via car_retrieve if needed)
        if not pick_up_id:
            # Extract potential car identifier fields
            car_query_fields = {}
            for field in ["car_id", "vin", "make", "model", "year"]:
                if field in args and args[field]:
                    car_query_fields[field] = args[field]
            
            if not car_query_fields:
                return {"status": "error", "code": "INVALID_INPUT", 
                        "message": "I need to know which car you're referring to. Please provide the VIN, or tell me the make, model, and year of the car."}
            
            # Resolve car_id using car_retrieve
            car_result = car_retrieve(sqlite_path=sp, query=car_query_fields)
            
            if car_result["status"] == "error":
                return car_result
            elif car_result["status"] == "unsure":
                return {
                    "status": "error",
                    "code": "AMBIGUOUS",
                    "message": "I found multiple cars matching that description. Could you provide the VIN to help me identify the exact car?",
                    "data": car_result.get("data", {})
                }
            
            # Extract car_id from retrieved car
            car_data = car_result.get("data", {})
            car = car_data.get("car", {})
            resolved_car_id = car.get("id")
            
            if not resolved_car_id:
                return {"status": "error", "code": "TXN_FAILED", 
                        "message": "I had trouble finding that car. Please try again with more details."}
            
            # Find pickup(s) by car_id
            try:
                conn, is_pg = get_db_connection(sp)
            except Exception as e:
                return {"status": "error", "code": "DB_UNAVAILABLE", 
                        "message": f"Could not open database: {e}", "data": {}}
            
            try:
                cur = execute_query(conn, is_pg, "SELECT pick_up_id FROM pickup WHERE car_id = ?", (resolved_car_id,))
                pickups = cur.fetchall()
                
                if not pickups:
                    return {"status": "error", "code": "NOT_FOUND", 
                            "message": "I couldn't find a pickup scheduled for that car to update.", 
                            "data": {"car_id": resolved_car_id}}
                
                if len(pickups) > 1:
                    # Handle both SQLite (Row objects) and PostgreSQL (dicts)
                    pickup_ids = []
                    for p in pickups:
                        if isinstance(p, dict):
                            pickup_ids.append(p["pick_up_id"])
                        else:
                            # SQLite Row object or tuple
                            pickup_ids.append(p[0] if isinstance(p, tuple) else p["pick_up_id"])
                    return {
                        "status": "error",
                        "code": "AMBIGUOUS",
                        "message": "I found multiple pickups for this car. Could you provide more details (like the address or pickup date) to help me identify which one you want to update?",
                        "data": {"car_id": resolved_car_id, "pickup_ids": pickup_ids}
                    }
                
                # Exactly one pickup found
                first_pickup = pickups[0]
                if isinstance(first_pickup, dict):
                    pick_up_id = first_pickup["pick_up_id"]
                else:
                    # SQLite Row object or tuple
                    pick_up_id = first_pickup[0] if isinstance(first_pickup, tuple) else first_pickup["pick_up_id"]
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        
        # Build patch: exclude identifier fields and pick_up_id
        excluded_fields = {"pick_up_id", "car_id", "vin", "make", "model", "year"}
        patch = {k: v for k, v in args.items() if k not in excluded_fields and v is not None}
        
        # Now call pickup_update with resolved pick_up_id
        return pickup_update(pick_up_id=pick_up_id, sqlite_path=sp, patch=patch)

    if name == "get_all_pickups":
        return get_all_pickups(sqlite_path=sp)

    if name == "get_closest":
        return get_closest(user_address=args.get("user_address", ""), state=args.get("state", "")) or {
            "status": "error", "message": "No nearby locations found."
        }

    if name == "send_escalate_message":
        txt = args.get("message_text", "")
        to = session_data.get("escalation_phone")
        try:
            send_escalate_message(receiver_number=to, message_text=txt)
            return {"status": "success", "message": "Escalation SMS sent."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send: {e!s}"}

    return {"status": "error", "message": f"Unknown tool '{name}'."}

def controller_turn(ava: AvaClient, user_msg: str, logs: List[Dict[str, Any]], session_data: Dict[str, Any]) -> str:
    # Log user input for conversation history
    logs.append({"event": "user_input", "detail": user_msg})
    
    # build planner prompt and ask Ava
    recent = logs[-3:] if logs else [] # THIS CAN BE REMOVED IN FUTURE AS VERTEX AI GIVES SESSION DATA AS CONTEXT ALREADY SO NO NEED OF THIS STEP IN FUTURE 
    logs_snippet = "; ".join(f"{r.get('event')}:{r.get('detail')}" for r in recent if r)
    planner_prompt = build_planner_prompt(user_msg, session_data, logs_snippet)

    # Log message sent to Ava (planner prompt)
    log_msg = f"[TO AVA - PLANNER] Sending planner prompt (length: {len(planner_prompt)} chars)"
    logger.info(log_msg)
    print(log_msg, flush=True)
    logger.debug(f"[TO AVA - PLANNER] Prompt: {planner_prompt[:500]}...")  # First 500 chars
    
    # Try to get a valid plan (with retry logic)
    plan = None
    max_retries = 2  # Initial attempt + 1 retry

    # WE ARE ADDING THIS TO CHECK IF THE RESPONSE WHICH WE ARE GETTING FROM AVA 
    # IF THAT IS NOT IN A PARTICULAR FORMAT THEN WE RETRY ONLY THAT IS CHECKED 
    # IF THERE IS NO RESPONSE FROM AVA THEN WE DONT RETRY AS THERE IS A RETRY LOGIC FOR THAT IN ASK ONCE 
    # AND STILL IF WE GET NO RESPONSE HERE THAT MEANS THE RETRY LOGIC IN ASK ONCE HAS BEEN EXECUTED AND AFTER ALL ATTEMTS 
    # IT RETURNED SORRY - NO REPONSE FROM AVA ... 

    for attempt in range(max_retries):
        raw = ava.ask_once(planner_prompt)
        
        # Log Ava's planner response
        attempt_label = "RETRY" if attempt > 0 else "INITIAL"
        log_msg = f"[FROM AVA - PLANNER {attempt_label}] Received response (length: {len(raw)} chars)"
        logger.info(log_msg)
        print(log_msg, flush=True)
        logger.debug(f"[FROM AVA - PLANNER {attempt_label}] Response: {raw[:500]}...")  # First 500 chars
        
        # If ask_once() returned an error message (after its own retries), don't retry again
        if raw and raw.startswith("Sorry—no response from Ava"):
            logs.append({"event": "planner_fail", "detail": "Ava API connection failed after retries"})
            return raw  # Return the error message from ask_once()
        
        plan = extract_json_block(raw)
        if not plan:
            if attempt < max_retries - 1:
                log_msg = f"[PLANNER] No plan extracted, retrying... (attempt {attempt + 1}/{max_retries})"
                logger.info(log_msg)
                print(log_msg, flush=True)
                continue
            else:
                logs.append({"event": "planner_fail", "detail": raw[:200]})
                return "Sorry—I couldn't figure out a plan. Could you rephrase?"

        # Validate the plan
        err = validate_plan(plan)
        if err:
            if attempt < max_retries - 1:
                log_msg = f"[PLANNER] Plan validation failed: {err}, retrying... (attempt {attempt + 1}/{max_retries})"
                logger.info(log_msg)
                print(log_msg, flush=True)
                continue
            else:
                logs.append({"event": "plan_invalid", "detail": err, "raw": raw[:200]})
                return "Sorry—my plan came out malformed. Please try again."
        
        # If we get here, we have a valid plan
        break

    if plan["action"] == "chat":
        answer = plan["answer"]
        
        # Check if answer is a JSON string (escaped or not) and extract text
        answer = answer.strip()
        
        # Try to parse as JSON string first (handles escaped JSON)
        try:
            # If it's an escaped JSON string like "{\"key\": \"value\"}"
            if answer.startswith('"') and answer.endswith('"'):
                unescaped = json.loads(answer)
                # Try parsing the unescaped content
                try:
                    parsed = json.loads(unescaped)
                    if isinstance(parsed, dict):
                        # If it's structured data (has arrays/objects), it's not conversational
                        if any(isinstance(v, (list, dict)) for v in parsed.values()):
                            answer = "I have that information, but I need to format it better. Let me get back to you with a clearer answer."
                        else:
                            # Extract text fields
                            found_text = False
                            for field in ["response", "message", "text", "answer"]:
                                if field in parsed and isinstance(parsed[field], str):
                                    answer = parsed[field]
                                    found_text = True
                                    break
                            # If no text field found but it's a dict with one string value, use that
                            if not found_text and len(parsed) == 1:
                                first_value = list(parsed.values())[0]
                                if isinstance(first_value, str):
                                    answer = first_value
                except (json.JSONDecodeError, ValueError):
                    # Unescaped is not JSON, use it
                    answer = unescaped if isinstance(unescaped, str) else answer
            else:
                # Try parsing directly
                parsed = json.loads(answer)
                if isinstance(parsed, dict):
                    # Structured data check
                    if any(isinstance(v, (list, dict)) for v in parsed.values()):
                        answer = "I have that information, but I need to format it better. Let me get back to you with a clearer answer."
                    else:
                        # Extract text fields
                        found_text = False
                        for field in ["response", "message", "text", "answer"]:
                            if field in parsed and isinstance(parsed[field], str):
                                answer = parsed[field]
                                found_text = True
                                break
                        # If no text field found but it's a dict with one string value, use that
                        if not found_text and len(parsed) == 1:
                            first_value = list(parsed.values())[0]
                            if isinstance(first_value, str):
                                answer = first_value
        except (json.JSONDecodeError, ValueError):
            # Not JSON, use as-is
            pass
        
        logs.append({"event": "chat", "detail": answer[:120]})
        return answer

    # IF IT ISNT CHAT THEN THAT MEANS IT IS A TOOL CALL 
    # tool path
    name = plan["name"]
    args = plan.get("args", {})
    logs.append({"event": "tool_call", "detail": f"{name}({args})"})

    result = _dispatch_tool(name, args, session_data)
    logs.append({"event": "tool_result", "detail": str(result)[:200]})

    # Handle errors - still format these directly
    status = result.get("status", "success")
    if status != "success":
        error_code = result.get("code", "")
        if error_code == "TIME_ALREADY_BOOKED":
            data = result.get("data", {})
            existing = data.get("existing_schedule", {})
            existing_time = existing.get("schedule_time", "")
            return f"The buyer is already booked at {existing_time}. Please choose another time."
        msg = result.get("message", "")
        return f"{msg or 'That did not work.'}"

    # For successful tool results, send back to Ava to generate natural response

    # This is the scond call to ava after tools gave some output 
    
    tool_result_prompt = f"""The user asked: "{user_msg}"

            I called the tool '{name}' and got this result:
            {result}

            Please provide a natural, conversational response to the user's question based on this tool result. Be concise and directly answer what they asked. Return ONLY the response text, no JSON, no code blocks, just plain conversational text."""
                
    # Log message sent to Ava (response generation)
    log_msg = f"[TO AVA - RESPONSE GEN] Sending tool result for natural response generation"
    logger.info(log_msg)
    print(log_msg, flush=True)
    logger.debug(f"[TO AVA - RESPONSE GEN] Prompt: {tool_result_prompt[:500]}...")
    
    ava_response = ava.ask_once(tool_result_prompt)
    
    # Log Ava's response generation
    log_msg = f"[FROM AVA - RESPONSE GEN] Received response (length: {len(ava_response)} chars)"
    logger.info(log_msg)
    print(log_msg, flush=True)
    logger.debug(f"[FROM AVA - RESPONSE GEN] Response: {ava_response[:500]}...")
    # Extract text if Ava wrapped it in JSON or code blocks
    ava_response = ava_response.strip()
    
    # First, try to remove code block markers
    ava_response = re.sub(r'^```json\s*', '', ava_response)
    ava_response = re.sub(r'^```\s*', '', ava_response)
    ava_response = re.sub(r'```\s*$', '', ava_response)
    ava_response = ava_response.strip()
    
    # Try to parse as JSON
    try:
        parsed = json.loads(ava_response)
        if isinstance(parsed, dict):
            # Look for common text fields in JSON
            for field in ["response", "message", "text", "answer", "content"]:
                if field in parsed and isinstance(parsed[field], str):
                    ava_response = parsed[field]
                    break
            # If no text field found but it's a dict with one string value, use that
            if ava_response == parsed and len(parsed) == 1:
                first_value = list(parsed.values())[0]
                if isinstance(first_value, str):
                    ava_response = first_value
    except (json.JSONDecodeError, ValueError):
        # Not JSON, keep original response
        pass
    
    logs.append({"event": "tool_response_generated", "detail": ava_response[:120]})
    return ava_response.strip()
