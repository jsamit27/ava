# agent_controller.py
"""
Single turn controller:
- Ask planner (via Ava) for a plan (chat or tool)
- If chat: return answer
- If tool: dispatch local Python tool, then return a user-facing summary
- Log each step into `logs` for debugging (/logs in CLI)
"""

from typing import Dict, Any, List
from ava_client import AvaClient
from planner import build_planner_prompt, extract_json_block, validate_plan

# Import your actual tool implementations (not the LangChain wrappers)
from all_tools import (
    car_retrieve,
    car_add,
    car_update,
    get_all_cars,
    get_buyer_availability,
    add_buyer_schedule,
    pickup_retrieve,
    pickup_add,
    pickup_update,
    get_all_pickups,
    get_closest,
    send_escalate_message,
)
from tools import SESSION  # for sqlite_path, lead_id

# Map planner -> concrete Python call
def _dispatch_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    sp = SESSION.get("sqlite_path")

    if name == "car_retrieve":
        return car_retrieve(sqlite_path=sp, query=args)

    if name == "car_add":
        patch = dict(args or {})
        patch.setdefault("lead_id", SESSION.get("lead_id"))
        # Block buyer_offer_cents - only GMTV employees can set this
        if "buyer_offer_cents" in patch:
            return {"status": "error", "code": "FORBIDDEN", "message": "Ava cannot set buyer_offer_cents. Only GMTV employees can set the company's offer."}
        return car_add(sqlite_path=sp, patch=patch)

    if name == "car_update":
        # Extract car_id and use rest as patch
        car_id = args.get("car_id")
        patch = {k: v for k, v in args.items() if k != "car_id" and v is not None}
        # Block buyer_offer_cents - only GMTV employees can set this
        if "buyer_offer_cents" in patch:
            return {"status": "error", "code": "FORBIDDEN", "message": "Ava cannot set buyer_offer_cents. Only GMTV employees can set the company's offer."}
        return car_update(car_id=car_id, sqlite_path=sp, patch=patch)

    if name == "get_all_cars":
        return get_all_cars(sqlite_path=sp)

    if name == "get_buyer_availability":
        return get_buyer_availability(sqlite_path=sp, buyer_id=SESSION.get("buyer_id"))

    if name == "add_buyer_schedule":
        return add_buyer_schedule(buyer_id=SESSION.get("buyer_id"), sqlite_path=sp, patch=args)

    if name == "pickup_retrieve":
        return pickup_retrieve(pick_up_id=args.get("pick_up_id"), sqlite_path=sp)

    if name == "pickup_add":
        return pickup_add(sqlite_path=sp, patch=args)

    if name == "pickup_update":
        # Extract pick_up_id and use rest as patch
        pick_up_id = args.get("pick_up_id")
        patch = {k: v for k, v in args.items() if k != "pick_up_id"}
        return pickup_update(pick_up_id=pick_up_id, sqlite_path=sp, patch=patch)

    if name == "get_all_pickups":
        return get_all_pickups(sqlite_path=sp)

    if name == "get_closest":
        return get_closest(user_address=args.get("user_address", ""), state=args.get("state", "")) or {
            "status": "error", "message": "No nearby locations found."
        }

    if name == "send_escalate_message":
        txt = args.get("message_text", "")
        to = SESSION.get("escalation_phone")
        try:
            send_escalate_message(receiver_number=to, message_text=txt)
            return {"status": "success", "message": "Escalation SMS sent."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to send: {e!s}"}

    return {"status": "error", "message": f"Unknown tool '{name}'."}

def controller_turn(ava: AvaClient, user_msg: str, logs: List[Dict[str, Any]]) -> str:
    # Log user input for conversation history
    logs.append({"event": "user_input", "detail": user_msg})
    
    # build planner prompt and ask Ava
    recent = logs[-3:] if logs else []
    logs_snippet = "; ".join(f"{r.get('event')}:{r.get('detail')}" for r in recent if r)
    planner_prompt = build_planner_prompt(user_msg, SESSION, logs_snippet)

    raw = ava.ask_once(planner_prompt)
    plan = extract_json_block(raw)
    if not plan:
        logs.append({"event": "planner_fail", "detail": raw[:200]})
        return "Sorry—I couldn’t figure out a plan. Could you rephrase?"

    err = validate_plan(plan)
    if err:
        logs.append({"event": "plan_invalid", "detail": err, "raw": raw[:200]})
        return "Sorry—my plan came out malformed. Please try again."

    if plan["action"] == "chat":
        answer = plan["answer"]
        logs.append({"event": "chat", "detail": answer[:120]})
        return answer

    # tool path
    name = plan["name"]
    args = plan.get("args", {})
    logs.append({"event": "tool_call", "detail": f"{name}({args})"})

    result = _dispatch_tool(name, args)
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
    tool_result_prompt = f"""The user asked: "{user_msg}"

I called the tool '{name}' and got this result:
{result}

Please provide a natural, conversational response to the user's question based on this tool result. Be concise and directly answer what they asked. Return ONLY the response text, no JSON, no code blocks, just plain conversational text."""
    
    ava_response = ava.ask_once(tool_result_prompt)
    # Extract text if Ava wrapped it in JSON or code blocks
    ava_response = ava_response.strip()
    
    # Remove JSON code blocks if present
    import re
    json_match = re.search(r'```json\s*\{.*?"message"\s*:\s*"([^"]+)"', ava_response, re.DOTALL)
    if json_match:
        ava_response = json_match.group(1)
    else:
        # Remove any code block markers
        ava_response = re.sub(r'```json\s*', '', ava_response)
        ava_response = re.sub(r'```\s*$', '', ava_response)
        ava_response = re.sub(r'^```\s*', '', ava_response)
    
    logs.append({"event": "tool_response_generated", "detail": ava_response[:120]})
    return ava_response.strip()
