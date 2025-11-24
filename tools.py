# lc_tools.py
from typing import Dict, Any
from langchain.tools import tool
from typing import Optional
from pydantic import BaseModel, Field


# --- bring in your existing implementations (from the file you pasted) ---
# If they live in the same file, you can remove these imports and use directly.
from all_tools import (
    get_buyer_availability as _get_buyer_availability,
    add_buyer_schedule as _add_buyer_schedule,
    car_retrieve as _car_retrieve,
    car_update as _car_update,
    car_add as _car_add,
    get_all_cars as _get_all_cars,
    get_closest as _get_closest,
    pickup_retrieve as _pickup_retrieve,
    pickup_update as _pickup_update,
    pickup_add as _pickup_add,
    get_all_pickups as _get_all_pickups,
    send_escalate_message as _send_escalate_message,
)

# FOR LOGGING 

# ---- simple per-turn tool trace ----
from datetime import datetime

TOOL_TRACE = []  # cleared each user turn by the CLI

def _log_tool(name: str, **kwargs):
    # keep args small & safe for logs
    safe = {}
    for k, v in kwargs.items():
        if k in {"patch"} and isinstance(v, dict):
            # truncate big dicts for readability
            safe[k] = {kk: v[kk] for kk in list(v)[:8]}
            if len(v) > 8:
                safe[k]["..."] = f"+{len(v)-8} more"
        else:
            safe[k] = v
    TOOL_TRACE.append({
        "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "tool": name,
        "args": safe,
    })



# --- simple session so tools auto-know which beta DB to use ---
SESSION: Dict[str, Any] = {
    "sqlite_path": None,   # set this once from your CLI
    "lead_id": None,       # handy if a tool later needs it
    "buyer_id": None,      # buyer ID for buyer-related operations
    "escalation_phone": None,  # phone number for escalation messages
}

# --------------- BUYER SCHEDULE ---------------

@tool("get_buyer_availability", return_direct=False)
def get_buyer_availability_tool() -> Dict[str, Any]:
    """Return all schedule rows for a buyer, ordered by schedule_time."""
    buyer_id = SESSION["buyer_id"]
    # LOGGING PURPOSE 
    _log_tool("get_buyer_availability", buyer_id=buyer_id)
    return _get_buyer_availability(sqlite_path=SESSION["sqlite_path"], buyer_id=buyer_id)

# -------- ADD BUYER SCHEDULE ------------

class AddBuyerScheduleInput(BaseModel):
    description: str
    schedule_time: str
    priority: Optional[str] = None  # Low/Medium/High

@tool("add_buyer_schedule", args_schema=AddBuyerScheduleInput, return_direct=False)
def add_buyer_schedule_tool(description: str,
                            schedule_time: str,
                            priority: Optional[str] = None):
    """Schedule a meeting or appointment for a buyer. Use this when a user wants to schedule, book, or set up a meeting/appointment. Requires description and schedule_time. The system will automatically check if the time is already booked and reject duplicate bookings."""
    buyer_id = SESSION["buyer_id"]
    patch = {"description": description, "schedule_time": schedule_time}
    if priority is not None:
        patch["priority"] = priority
    
    # LOGGING PURPOSE 
    _log_tool("add_buyer_schedule", buyer_id=buyer_id, patch=patch)
    return _add_buyer_schedule(buyer_id=buyer_id, sqlite_path=SESSION["sqlite_path"], patch=patch)


# --------------- CAR --------------------------

# REPLACE your current car_retrieve_tool with this:


class CarRetrieveInput(BaseModel):
    # auto-added by wrapper from SESSION; no need to expose
    # sqlite_path: str
    car_id: Optional[int] = Field(None, description="Exact car id if known.")
    vin: Optional[str] = Field(None, description="Full VIN if known.")
    model: Optional[str] = None
    make: Optional[str] = None
    year: Optional[int] = None

@tool("car_retrieve", args_schema=CarRetrieveInput, return_direct=False)
def car_retrieve_tool(car_id: Optional[int] = None,
                      vin: Optional[str] = None,
                      model: Optional[str] = None,
                      make: Optional[str] = None,
                      year: Optional[int] = None):
    """Get car details. Provide any of: car_id, vin, model, make, year."""
    query = {}
    if car_id is not None: query["car_id"] = car_id
    if vin:               query["vin"] = vin
    if model:             query["model"] = model
    if make:              query["make"] = make
    if year is not None:  query["year"] = year

    # LOGGING PURPOSE 
    _log_tool("car_retrieve", query=query)
    return _car_retrieve(sqlite_path=SESSION["sqlite_path"], query=query)






#-----------CAR UPDATE ----------

class CarUpdateInput(BaseModel):
    car_id: int
    vin: Optional[str] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    mileage: Optional[int] = None
    interior_condition: Optional[str] = None
    exterior_condition: Optional[str] = None
    seller_ask_cents: Optional[int] = None
    # Note: buyer_offer_cents can only be set by GMTV employees, not by Ava
    created_at: Optional[str] = None
    lead_id: Optional[int] = None

@tool("car_update", args_schema=CarUpdateInput, return_direct=False)
def car_update_tool(car_id: int,
                    vin: Optional[str] = None,
                    year: Optional[int] = None,
                    make: Optional[str] = None,
                    model: Optional[str] = None,
                    trim: Optional[str] = None,
                    mileage: Optional[int] = None,
                    interior_condition: Optional[str] = None,
                    exterior_condition: Optional[str] = None,
                    seller_ask_cents: Optional[int] = None,
                    created_at: Optional[str] = None,
                    lead_id: Optional[int] = None):
    """Update a car by ID; supply only fields you want to change. You can update seller_ask_cents (what the customer wants to sell for), but you CANNOT set buyer_offer_cents (GMTV's offer - only employees can set that)."""
    patch = {k: v for k, v in locals().items()
             if k not in ("car_id") and v is not None}
    # Remove buyer_offer_cents if somehow it got through (defense in depth)
    patch.pop("buyer_offer_cents", None)
    
    # LOGGING PURPOSE 
    _log_tool("car_update", car_id=car_id, patch=patch)
    return _car_update(car_id=car_id, sqlite_path=SESSION["sqlite_path"], patch=patch)


# --------------- CAR ADD TOOL -----------

class CarAddInput(BaseModel):
    vin: Optional[str] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    mileage: Optional[int] = None
    interior_condition: Optional[str] = None
    exterior_condition: Optional[str] = None
    seller_ask_cents: Optional[int] = None
    # Note: buyer_offer_cents can only be set by GMTV employees, not by Ava
    created_at: Optional[str] = None
    lead_id: Optional[int] = None  # will default to SESSION

@tool("car_add", args_schema=CarAddInput, return_direct=False)
def car_add_tool(**kwargs):
    """Create a new car listing in the database. Use this when a user wants to sell a car or is providing car information for a new listing (upserts by VIN if present). You can set seller_ask_cents (what the customer wants to sell for), but you CANNOT set buyer_offer_cents (GMTV's offer - only employees can set that)."""
    # Remove buyer_offer_cents if somehow it got through (defense in depth)
    kwargs.pop("buyer_offer_cents", None)
    patch = {k: v for k, v in kwargs.items() if v is not None}
    patch.setdefault("lead_id", SESSION["lead_id"])

    # LOGGING PURPOSE 
    _log_tool("car_add", patch=patch)
    return _car_add(sqlite_path=SESSION["sqlite_path"], patch=patch)

# --------------- GET ALL CARS -----------------------

@tool("get_all_cars", return_direct=False)
def get_all_cars_tool() -> Dict[str, Any]:
    """Retrieve all cars from the database. Returns all car records with all their details."""
    _log_tool("get_all_cars")
    return _get_all_cars(sqlite_path=SESSION["sqlite_path"])

# --------------- PICKUP -----------------------

@tool("pickup_retrieve", return_direct=False)
def pickup_retrieve_tool(pick_up_id: int) -> Dict[str, Any]:
    """Get details of an existing pickup by ID."""

    # LOGGING PURPOSE 
    _log_tool("pickup_retrieve", pick_up_id=pick_up_id)
    return _pickup_retrieve(pick_up_id=pick_up_id, sqlite_path=SESSION["sqlite_path"])

#------- PICKUP UPDATE ---------

class PickupUpdateInput(BaseModel):
    pick_up_id: int
    car_id: Optional[int] = None
    address: Optional[str] = None
    contact_phone: Optional[str] = None
    pick_up_info: Optional[str] = None
    created_at: Optional[str] = None
    dropoff_time: Optional[str] = None

@tool("pickup_update", args_schema=PickupUpdateInput, return_direct=False)
def pickup_update_tool(pick_up_id: int, **kwargs):
    """Update a pickup by ID; supply only fields you want to change."""
    patch = {k: v for k, v in kwargs.items() if v is not None}

    # LOGGING PURPOSE 
    _log_tool("pickup_update", pick_up_id=pick_up_id, patch=patch)
    return _pickup_update(pick_up_id=pick_up_id, sqlite_path=SESSION["sqlite_path"], patch=patch)


#------- PICKUP ADD --------------

class PickupAddInput(BaseModel):
    car_id: Optional[int] = None
    address: Optional[str] = None
    contact_phone: Optional[str] = None
    pick_up_info: Optional[str] = None
    created_at: Optional[str] = None
    dropoff_time: Optional[str] = None

@tool("pickup_add", args_schema=PickupAddInput, return_direct=False)
def pickup_add_tool(**kwargs):
    """Create a new pickup request."""
    patch = {k: v for k, v in kwargs.items() if v is not None}

    # LOGGING PURPOSE 
    _log_tool("pickup_add", patch=patch)
    return _pickup_add(sqlite_path=SESSION["sqlite_path"], patch=patch)

# --------------- GET ALL PICKUPS -----------------------

@tool("get_all_pickups", return_direct=False)
def get_all_pickups_tool() -> Dict[str, Any]:
    """Retrieve all pickups from the database. Returns all pickup records with all their details."""
    _log_tool("get_all_pickups")
    return _get_all_pickups(sqlite_path=SESSION["sqlite_path"])

# --------------- UTILITY ----------------------

@tool("get_closest", return_direct=False)
def get_closest_tool(user_address: str, state: str) -> Dict[str, Any]:
    """Find nearest drop-off to the user-provided address (state = 2-letter)."""

    # LOGGING PURPOSE 
    _log_tool("get_closest", user_address=user_address, state=state)
    return _get_closest(user_address=user_address, state=state) or {
        "status": "error",
        "message": "No nearby locations found."
    }

@tool("send_escalate_message", return_direct=False)
def send_escalate_message_tool(message_text: str) -> Dict[str, Any]:
    """Urgent internal SMS to escalation phone number (RingCentral-backed). Use this when a user is frustrated, angry, or needs immediate human intervention."""
    receiver_number = SESSION["escalation_phone"]
    
    # LOGGING PURPOSE 
    _log_tool("send_escalate_message", receiver_number=receiver_number, message_text=message_text[:60])

    try:
        _send_escalate_message(receiver_number=receiver_number, message_text=message_text)
        return {"status": "success", "message": "Escalation SMS sent."}
    except Exception as e:
        return {"status": "error", "message": f"Failed to send: {e!s}"}

# Export the list for quick import into the agent
ALL_TOOLS = [
    get_buyer_availability_tool,
    add_buyer_schedule_tool,
    car_retrieve_tool,
    car_update_tool,
    car_add_tool,
    get_all_cars_tool,
    pickup_retrieve_tool,
    pickup_update_tool,
    pickup_add_tool,
    get_all_pickups_tool,
    get_closest_tool,
    send_escalate_message_tool,
]
