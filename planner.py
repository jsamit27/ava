"""
Planner = tiny policy layer that tells Ava to:
- either reply directly {"action":"chat", "answer":"..."}
- or call ONE tool {"action":"tool", "name":"...", "args":{...}}

It receives the user message + a bit of context (sqlite_path, lead_id),
and returns a STRICT JSON plan that agent_controller.py can execute.
"""
import json
import re
from typing import Dict, Any, Optional

# Import tools to extract their descriptions
from tools import ALL_TOOLS

# ---- What tools the planner is allowed to call (names must match tools.py) ----
ALLOWED_TOOL_NAMES = [tool.name for tool in ALL_TOOLS]


def _build_tool_catalog() -> str:
    """
    Build a formatted catalog of available tools with their descriptions.
    Extracts info from LangChain tool objects.
    """
    catalog_lines = []
    for tool in ALL_TOOLS:
        name = tool.name
        description = tool.description or "No description available"
        # Try to get args info from schema if available
        args_info = ""
        if hasattr(tool, 'args_schema') and tool.args_schema:
            schema = tool.args_schema
            if hasattr(schema, 'schema'):
                fields = schema.schema().get('properties', {})
                if fields:
                    arg_names = list(fields.keys())
                    args_info = f" (args: {', '.join(arg_names)})"
        
        catalog_lines.append(f"- {name}{args_info}: {description}")
    
    return "\n".join(catalog_lines)

# ---- System guidance for the planner LLM (Ava) ----
PLANNER_SYSTEM = f"""You are a planner that decides whether to respond directly or call ONE tool.

Return EXACTLY ONE JSON object (and nothing else) inside ```json code fences.

Valid outputs:

```json
{{"action":"chat","answer":"<final user-facing text>"}}
```
OR
```json
{{"action":"tool","name":"<one_of:{ALLOWED_TOOL_NAMES}>","args":{{}}}}
```

Rules:
- If you do not have enough details to call a tool, ask a short clarifying question with action="chat".
- NEVER include sqlite_path, lead_id, buyer_id, receiver_number, or buyer_offer_cents in args (runtime injects the first four; buyer_offer_cents can only be set by GMTV employees, not by Ava).
- IMPORTANT: You represent GMTV(Give me the vin company) (the buyer). Customers are sellers. You can ask customers what they want to sell for (seller_ask_cents), but you CANNOT set buyer_offer_cents (GMTV's offer - only employees can do that).
- Use ONE tool only per response.
- Keep args minimal and valid for the chosen tool (e.g., for car_retrieve use one of: car_id, vin, model, make, year).
- Output must be valid JSON (double quotes, no trailing commas).
- Always attempt tool calls when the user's request matches a tool's purpose, even if previous tool calls failed. Previous errors don't mean all tools are broken - try the appropriate tool for the current request.

"""


def build_planner_prompt(user_msg: str, session: Dict[str, Any], logs_snippet: str = "") -> str:
    """
    Produces the message we send to Ava as the 'planner' prompt.
    We include light context (so planner knows the environment),
    but we explicitly tell it NOT to include sqlite_path/lead_id in args.
    """
    tool_catalog = _build_tool_catalog()
    
    ctx_lines = [
        f"- sqlite_path: {session.get('sqlite_path')}",
        f"- lead_id: {session.get('lead_id')}",
    ]
    if logs_snippet:
        ctx_lines.append(f"- recent_logs: {logs_snippet[:300]}")

    prompt = (
        PLANNER_SYSTEM
        + "\n\nAvailable Tools:\n"
        + tool_catalog
        + "\n\nContext:\n"
        + "\n".join(ctx_lines)
        + "\n\nUser says:\n"
        + user_msg
        + "\n\nReturn only ONE JSON object inside ```json fences."
    )
    return prompt


def extract_json_block(text: str) -> Optional[Dict[str, Any]]:
    """
    Pull the first JSON object from Ava's reply.
    1) Prefer ```json ... ``` fenced block
    2) Fallback to first {...} object in the text
    Returns dict or None.
    """
    # Prefer fenced block
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    candidate = m.group(1) if m else None

    # Fallback: any { ... } block
    if not candidate:
        m2 = re.search(r"(\{.*\})", text, flags=re.S)
        if m2:
            candidate = m2.group(1)

    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except Exception:
        return None


def validate_plan(plan: Dict[str, Any]) -> Optional[str]:
    """
    (Optional) quick sanity validator for the plan structure
    Returns None if valid, or an error string if invalid.
    """
    if not isinstance(plan, dict):
        return "plan is not a JSON object"

    action = plan.get("action")
    if action not in {"chat", "tool"}:
        return "action must be 'chat' or 'tool'"

    if action == "chat":
        if "answer" not in plan or not isinstance(plan["answer"], str):
            return "chat plan must include string 'answer'"
        return None

    if action == "tool":
        name = plan.get("name")
        args = plan.get("args")
        if name not in ALLOWED_TOOL_NAMES:
            return f"unknown tool '{name}'"
        if not isinstance(args, dict):
            return "tool plan must include object 'args'"
        # extra safety: forbid runtime keys and business-restricted fields
        if "sqlite_path" in args or "lead_id" in args or "buyer_id" in args or "receiver_number" in args:
            return "args must not include sqlite_path, lead_id, buyer_id, or receiver_number"
        if "buyer_offer_cents" in args:
            return "args must not include buyer_offer_cents (only GMTV employees can set the company's offer)"
        return None

    return "invalid plan"