# tools.py
from typing import Dict, Any, Optional
from langchain.tools import tool
from pydantic import BaseModel, Field
from all_tools import (
    get_buyer_availability as _get_buyer_availability,
    add_buyer_schedule as _add_buyer_schedule,
    remove_buyer_schedule as _remove_buyer_schedule,
    update_buyer_schedule as _update_buyer_schedule,
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

# Note: TOOL_TRACE and _log_tool were removed as they were never read/used
# Note: SESSION was removed - tool wrappers are only used for metadata, never executed.
# Actual execution happens in agent_controller.py which uses session_data parameter.

# --------------- BUYER SCHEDULE ---------------

@tool("get_buyer_availability", return_direct=False)
def get_buyer_availability_tool() -> Dict[str, Any]:
    """Return all schedule rows for a buyer, ordered by schedule_time."""
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}

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
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}

# -------- REMOVE BUYER SCHEDULE ------------

class RemoveBuyerScheduleInput(BaseModel):
    schedule_time: str

@tool("remove_buyer_schedule", args_schema=RemoveBuyerScheduleInput, return_direct=False)
def remove_buyer_schedule_tool(schedule_time: str):
    """Remove or cancel a buyer's schedule by schedule time. Use this when a user wants to cancel, remove, or delete a scheduled meeting/appointment. Requires schedule_time to identify which schedule to remove."""
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}

# -------- UPDATE BUYER SCHEDULE ------------

class UpdateBuyerScheduleInput(BaseModel):
    schedule_time: str  # The time of the schedule to update
    description: Optional[str] = None
    new_schedule_time: Optional[str] = None  # New time if rescheduling
    priority: Optional[str] = None  # Low/Medium/High

@tool("update_buyer_schedule", args_schema=UpdateBuyerScheduleInput, return_direct=False)
def update_buyer_schedule_tool(schedule_time: str,
                                description: Optional[str] = None,
                                new_schedule_time: Optional[str] = None,
                                priority: Optional[str] = None):
    """Update or reschedule a buyer's existing schedule. Use this when a user wants to change, reschedule, or modify an existing meeting/appointment. Requires schedule_time to identify which schedule to update. Can update description, schedule_time (use new_schedule_time to reschedule), or priority."""
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}


# --------------- CAR --------------------------

class CarRetrieveInput(BaseModel):
    # sqlite_path is automatically injected by agent_controller.py from session_data
    # sqlite_path: str  # Not exposed to LLM
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
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}



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
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}


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
    lead_id: Optional[int] = None  # will default to session_data["lead_id"] in agent_controller.py

@tool("car_add", args_schema=CarAddInput, return_direct=False)
def car_add_tool(**kwargs):
    """Create a new car listing in the database. Use this when a user wants to sell a car or is providing car information for a new listing (upserts by VIN if present). You can set seller_ask_cents (what the customer wants to sell for), but you CANNOT set buyer_offer_cents (GMTV's offer - only employees can set that)."""
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}

# --------------- GET ALL CARS -----------------------

@tool("get_all_cars", return_direct=False)
def get_all_cars_tool() -> Dict[str, Any]:
    """Retrieve all cars from the database. Returns all car records with all their details."""
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}

# --------------- PICKUP -----------------------

@tool("pickup_retrieve", return_direct=False)
def pickup_retrieve_tool(pick_up_id: int) -> Dict[str, Any]:
    """Get details of an existing pickup by ID."""
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}

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
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}


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
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}

# --------------- GET ALL PICKUPS -----------------------

@tool("get_all_pickups", return_direct=False)
def get_all_pickups_tool() -> Dict[str, Any]:
    """Retrieve all pickups from the database. Returns all pickup records with all their details."""
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}

# --------------- UTILITY ----------------------

@tool("get_closest", return_direct=False)
def get_closest_tool(user_address: str, state: str) -> Dict[str, Any]:
    """Find nearest drop-off to the user-provided address (state = 2-letter)."""
    return _get_closest(user_address=user_address, state=state) or {
        "status": "error",
        "message": "No nearby locations found."
    }

@tool("send_escalate_message", return_direct=False)
def send_escalate_message_tool(message_text: str) -> Dict[str, Any]:
    """Urgent internal SMS to escalation phone number (RingCentral-backed). Use this when a user is frustrated, angry, or needs immediate human intervention."""
    # This function is never executed - only metadata is used by planner.py
    # Actual execution happens in agent_controller.py via all_tools.py
    return {"status": "error", "message": "This wrapper should never be executed"}

# Export the list for quick import into the agent
ALL_TOOLS = [
    get_buyer_availability_tool,
    add_buyer_schedule_tool,
    remove_buyer_schedule_tool,
    update_buyer_schedule_tool,
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
