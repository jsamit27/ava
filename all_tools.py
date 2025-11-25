import logging
import os
import sys
from datetime import datetime
from typing import List, Dict, Any, Union, Optional
from pathlib import Path
import csv
import requests
from dotenv import load_dotenv
from ringcentral import SDK
from db_connection import get_db_connection, execute_query

# Load environment variables once at module level
load_dotenv()


PRIORITIES = {"Low", "Medium", "High"}

def _dt_str(v: Union[str, datetime]) -> str:
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    s = (str(v or "")).strip().replace("T", " ").rstrip("Z")
    try:
        return datetime.fromisoformat(s.split(".")[0]).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return s


def get_buyer_availability(sqlite_path: str, buyer_id: int) -> Dict[str, Any]:
    """
    Return all schedule rows for a buyer, ordered by schedule_time.
    Response: {"status":"success|error","message":str,"data":{...},["code":str]}
    """
    # 0) validate buyer_id
    try:
        buyer_id = int(buyer_id)
    except Exception:
        return {
            "status": "error",
            "code": "INVALID_INPUT",
            "message": "buyer_id must be an integer.",
            "data": {"received": buyer_id},
        }

    # 1) open DB (supports both SQLite and PostgreSQL)
    try:
        conn, is_pg = get_db_connection(sqlite_path)
    except Exception as e:
        return {
            "status": "error",
            "code": "DB_UNAVAILABLE",
            "message": f"Could not open database: {e}",
            "data": {},
        }

    try:
        # 2) ensure buyer exists (so empty schedules vs. missing buyer are distinct)
        cur = execute_query(conn, is_pg, "SELECT 1 FROM buyers WHERE id = ? LIMIT 1", (buyer_id,))
        if cur.fetchone() is None:
            return {
                "status": "error",
                "code": "NOT_FOUND",
                "message": f"Buyer id {buyer_id} not found.",
                "data": {},
            }

        # 3) fetch schedules
        cur = execute_query(conn, is_pg, """
            SELECT id, buyer_id, description, schedule_time, priority
            FROM buyer_schedule
            WHERE buyer_id = ?
            ORDER BY schedule_time ASC
        """, (buyer_id,))
        rows = cur.fetchall()
        schedules = [dict(r) for r in rows]

        msg = "Availability retrieved." if schedules else "No schedules found."
        return {
            "status": "success",
            "message": msg,
            "data": {"buyer_id": buyer_id, "schedules": schedules},
        }

    except Exception as e:
        return {
            "status": "error",
            "code": "TXN_FAILED",
            "message": f"Lookup failed: {e}",
            "data": {},
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


#-------------------------------------------------

#-----------------add buyer----------------------

#-------------------------------------------------




def add_buyer_schedule(
    buyer_id: int,
    sqlite_path: str,
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Insert a buyer_schedule row.
    Signature style: (buyer_id, sqlite_path, patch)
    Required in patch: description, schedule_time
    Optional in patch: priority (defaults to 'Medium')
    Returns: {"status":"success|error","message":str,"data":{...},["code":str]}
    """
    # validate buyer_id & patch
    try:
        buyer_id = int(buyer_id)
    except Exception:
        return {"status":"error","code":"INVALID_INPUT","message":"buyer_id must be an integer.","data":{"received": buyer_id}}
    if not isinstance(patch, dict) or not patch:
        return {"status":"error","code":"INVALID_INPUT","message":"patch must be a non-empty object.","data":{}}

    # extract fields
    desc = str(patch.get("description") or "").strip()
    if not desc:
        return {"status":"error","code":"INVALID_INPUT","message":"description is required.","data":{}}

    pr = str(patch.get("priority") or "Medium").strip().title()
    if pr not in PRIORITIES:
        return {"status":"error","code":"INVALID_INPUT","message":f"priority must be one of {sorted(PRIORITIES)}","data":{"received": patch.get("priority")}}

    st = _dt_str(patch.get("schedule_time"))
    if not st:
        return {"status":"error","code":"INVALID_INPUT","message":"schedule_time is invalid.","data":{"received": str(patch.get("schedule_time"))}}

    # DB work
    try:
        conn, is_pg = get_db_connection(sqlite_path)
    except Exception as e:
        return {"status":"error","code":"DB_UNAVAILABLE","message":f"Could not open database: {e}","data":{}}

    try:
        # ensure buyer exists
        cur = execute_query(conn, is_pg, "SELECT 1 FROM buyers WHERE id = ? LIMIT 1", (buyer_id,))
        if cur.fetchone() is None:
            return {"status":"error","code":"NOT_FOUND","message":f"Buyer id {buyer_id} not found.","data":{}}

        # check if time is already booked
        cur = execute_query(conn, is_pg, """
            SELECT id, description, schedule_time, priority
            FROM buyer_schedule
            WHERE buyer_id = ? AND schedule_time = ?
            LIMIT 1
        """, (buyer_id, st))
        existing = cur.fetchone()
        if existing:
            existing_dict = dict(existing)
            return {
                "status": "error",
                "code": "TIME_ALREADY_BOOKED",
                "message": f"The buyer is already booked at {st}. Please choose another time.",
                "data": {"existing_schedule": existing_dict, "requested_time": st}
            }

        # insert (ignore any patch['buyer_id'] to avoid conflicts)
        if is_pg:
            # PostgreSQL: use RETURNING clause to get the ID
            cur = execute_query(conn, is_pg, """
                INSERT INTO buyer_schedule (buyer_id, description, schedule_time, priority)
                VALUES (?, ?, ?, ?) RETURNING id
            """, (buyer_id, desc, st, pr))
            schedule_id = cur.fetchone()["id"]
        else:
            # SQLite: use lastrowid
            cur = execute_query(conn, is_pg, """
                INSERT INTO buyer_schedule (buyer_id, description, schedule_time, priority)
                VALUES (?, ?, ?, ?)
            """, (buyer_id, desc, st, pr))
            schedule_id = cur.lastrowid
        conn.commit()

        # fetch & return
        cur = execute_query(conn, is_pg, "SELECT id, buyer_id, description, schedule_time, priority FROM buyer_schedule WHERE id = ?", (schedule_id,))
        row = cur.fetchone()
        return {"status":"success","message":"Schedule added.","data":{"schedule": dict(row) if row else {"id": schedule_id}}}

    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        msg = str(e).lower()
        if "foreign key" in msg or "integrity" in msg:
            return {"status":"error","code":"PRECONDITION_FAILED","message":"Invalid reference (foreign key).","data":{"buyer_id": buyer_id}}
        return {"status":"error","code":"TXN_FAILED","message":f"Insert failed: {e}","data":{}}

    finally:
        try: conn.close()
        except Exception: pass

PRIORITY = ["car_id", "vin", "model", "make", "year"]

def car_retrieve(sqlite_path: str, query: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieve a car using ONE input by priority: car_id > vin > model > make > year.
    Returns: {"status": "success|error|unsure", "message": str, "data": {...}, ["code": str]}
    """
    # validate & pick one key
    if not isinstance(query, dict):
        return {"status": "error", "code": "INVALID_INPUT", "message": "query must be an object.", "data": {}}

    provided = [k for k in PRIORITY if k in query and str(query[k]).strip() != ""]
    if not provided:
        return {"status": "error", "code": "INVALID_INPUT", "message": "Provide car_id, vin, model, make, or year.", "data": {}}

    key = provided[0]
    value = query[key]
    ignored = provided[1:]

    # normalize numerics
    if key in ("car_id", "year"):
        try:
            value = int(value)
        except Exception:
            return {"status": "error", "code": "INVALID_INPUT", "message": f"{key} must be an integer.", "data": {"received": value}}

    # open DB
    try:
        conn, is_pg = get_db_connection(sqlite_path)
    except Exception as e:
        return {"status": "error", "code": "DB_UNAVAILABLE", "message": f"Could not open database: {e}", "data": {}}

    try:
        # query using ONLY the selected key
        if key == "car_id":
            cur = execute_query(conn, is_pg, "SELECT * FROM cars WHERE id = ?", (value,))
            row = cur.fetchone()
            meta = {"selected_key": key, "selected_value": value, "ignored_keys": ignored}
            if not row:
                return {"status": "error", "code": "NOT_FOUND", "message": "No matching car found.", "data": meta}
            meta["car"] = dict(row)
            return {"status": "success", "message": "Car retrieved.", "data": meta}

        elif key == "vin":
            cur = execute_query(conn, is_pg, "SELECT * FROM cars WHERE vin = ?", (str(value).strip(),))
        elif key == "model":
            cur = execute_query(conn, is_pg, "SELECT * FROM cars WHERE LOWER(model) LIKE ?", (f"%{str(value).strip().lower()}%",))
        elif key == "make":
            cur = execute_query(conn, is_pg, "SELECT * FROM cars WHERE LOWER(make) LIKE ?", (f"%{str(value).strip().lower()}%",))
        elif key == "year":
            cur = execute_query(conn, is_pg, "SELECT * FROM cars WHERE year = ?", (value,))
        else:
            return {"status": "error", "code": "INVALID_INPUT", "message": f"Unsupported key '{key}'.", "data": {}}

        rows = cur.fetchall()
        meta = {"selected_key": key, "selected_value": value, "ignored_keys": ignored}

        if not rows:
            return {"status": "error", "code": "NOT_FOUND", "message": "No matching car found.", "data": meta}

        # ✅ include VIN in ambiguity check
        if key in ("vin", "model", "make", "year") and len(rows) > 1:
            meta["candidates"] = [
                {"id": r["id"], "year": r["year"], "make": r["make"], "model": r["model"], "vin": r["vin"]}
                for r in rows[:5]
            ]
            return {"status": "unsure", "code": "AMBIGUOUS",
                    "message": "Multiple cars match—refine with VIN or car_id.", "data": meta}

        meta["car"] = dict(rows[0])
        return {"status": "success", "message": "Car retrieved.", "data": meta}
    except Exception as e:
        return {"status": "error", "code": "TXN_FAILED", "message": f"Lookup failed: {e}", "data": {}}
    finally:
        try:
            conn.close()
        except Exception:
            pass

#-------------------------------------------------

#-----------------Get All Cars----------------------

#-------------------------------------------------

def get_all_cars(sqlite_path: str) -> Dict[str, Any]:
    """
    Retrieve all cars from the database.
    Returns: {"status": "success|error", "message": str, "data": {"cars": [...]}, ["code": str]}
    """
    try:
        conn, is_pg = get_db_connection(sqlite_path)
    except Exception as e:
        return {"status": "error", "code": "DB_UNAVAILABLE", "message": f"Could not open database: {e}", "data": {}}

    try:
        cur = execute_query(conn, is_pg, "SELECT * FROM cars ", ())
        rows = cur.fetchall()
        
        cars = [dict(row) for row in rows]
        return {
            "status": "success",
            "message": f"Retrieved {len(cars)} car(s).",
            "data": {"cars": cars, "count": len(cars)}
        }
    except Exception as e:
        return {"status": "error", "code": "TXN_FAILED", "message": f"Query failed: {e}", "data": {}}
    finally:
        try:
            conn.close()
        except Exception:
            pass

#-------------------------------------------------

#-----------------Car update----------------------

#-------------------------------------------------


def car_update(car_id: int, sqlite_path: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Safely update a car row in the local SQLite sandbox.
    Returns: {"status": "success|error", "message": str, "data": {...}, ["code": str]}
    """
    # 0) basic input checks
    if not isinstance(patch, dict) or not patch:
        return {"status": "error", "code": "INVALID_INPUT", "message": "patch must be a non-empty object.", "data": {}}
    try:
        car_id = int(car_id)
    except Exception:
        return {"status": "error", "code": "INVALID_INPUT", "message": "car_id must be an integer.", "data": {"received": car_id}}

    # 1) whitelist fields (prevents SQL injection on column names)
    ALLOWED_FIELDS = {
        "vin", "year", "make", "model", "trim", "mileage",
        "interior_condition", "exterior_condition",
        "seller_ask_cents", "buyer_offer_cents",
        "created_at", "lead_id"
    }
    sanitized = {k: v for k, v in patch.items() if k in ALLOWED_FIELDS}
    if not sanitized:
        return {
            "status": "error",
            "code": "INVALID_INPUT",
            "message": "No allowed fields to update.",
            "data": {"allowed_fields": sorted(ALLOWED_FIELDS)}
        }

    # 2) open DB
    try:
        conn, is_pg = get_db_connection(sqlite_path)
    except Exception as e:
        return {"status": "error", "code": "DB_UNAVAILABLE", "message": f"Could not open database: {e}", "data": {}}

    try:
        # 3) ensure the car exists
        cur = execute_query(conn, is_pg, "SELECT 1 FROM cars WHERE id = ? LIMIT 1", (car_id,))
        if cur.fetchone() is None:
            return {"status": "error", "code": "NOT_FOUND", "message": f"Car id {car_id} not found.", "data": {}}

        # 4) apply updates (one UPDATE per field)
        updated_fields = 0
        for field, value in sanitized.items():
            # safe because 'field' is whitelisted above
            cur = execute_query(conn, is_pg, f"UPDATE cars SET {field} = ? WHERE id = ?", (value, car_id))
            if cur.rowcount > 0:
                updated_fields += 1

        conn.commit()

        msg = "Car updated ({} fields).".format(updated_fields) if updated_fields else "No fields changed."
        return {
            "status": "success",
            "message": msg,
            "data": {"car_id": car_id, "updated_fields": updated_fields}
        }

    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        msg = str(e).lower()
        if "unique" in msg and "vin" in msg:
            return {
                "status": "error",
                "code": "CONFLICT_VIN",
                "message": "VIN already exists.",
                "data": {"vin": patch.get("vin")}
            }
        if "foreign key" in msg or "integrity" in msg:
            return {"status": "error", "code": "PRECONDITION_FAILED", "message": f"Integrity error: {e}", "data": {}}
        return {"status": "error", "code": "TXN_FAILED", "message": f"Update failed: {e}", "data": {}}

    finally:
        try: conn.close()
        except Exception: pass


#-------------------------------------------------

#-----------------Car add----------------------

#-------------------------------------------------




def _next_temp_car_id(conn, is_pg: bool) -> int:
    cur = execute_query(conn, is_pg, "SELECT MIN(id) as min_id FROM cars", ())
    row = cur.fetchone()
    if row is None:
        return -1
    # Handle both SQLite (tuple) and PostgreSQL (dict)
    if is_pg:
        min_id = row.get("min_id") if isinstance(row, dict) else row[0]
    else:
        min_id = row[0] if isinstance(row, tuple) else row.get("min_id")
    return -1 if (min_id is None or min_id > 0) else (min_id - 1)

def car_add(sqlite_path: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a new car OR, if VIN already exists, update that existing row with the new values.
    Returns: {"status": "success|error", "message": str, "data": {...}, ["code": str]}
    """
    if not isinstance(patch, dict):
        return {"status": "error", "code": "INVALID_INPUT", "message": "patch must be an object.", "data": {}}

    # whitelist columns we will insert/update
    ALLOWED = {
        "vin", "year", "make", "model", "trim", "mileage",
        "interior_condition", "exterior_condition",
        "seller_ask_cents", "buyer_offer_cents",
        "created_at", "lead_id"
    }

    try:
        conn, is_pg = get_db_connection(sqlite_path)
    except Exception as e:
        return {"status": "error", "code": "DB_UNAVAILABLE", "message": f"Could not open database: {e}", "data": {}}

    try:
        # Normalize VIN (allow None/empty to mean "no VIN")
        vin = patch.get("vin")
        if isinstance(vin, str):
            vin_norm = vin.strip() or None
        else:
            vin_norm = vin

        # If VIN provided, try UPSERT: update existing row instead of erroring
        if vin_norm is not None:
            cur = execute_query(conn, is_pg, "SELECT id FROM cars WHERE vin = ?", (vin_norm,))
            existing = cur.fetchone()
            if existing:
                car_id = existing["id"]

                # Build a sanitized dict of only fields we want to update
                sanitized = {k: v for k, v in patch.items() if k in ALLOWED}

                # Always keep VIN normalized if present
                if "vin" in sanitized:
                    sanitized["vin"] = vin_norm

                # If nothing to update, just return the row
                if not sanitized:
                    cur = execute_query(conn, is_pg, "SELECT * FROM cars WHERE id = ?", (car_id,))
                    row = cur.fetchone()
                    return {"status": "success", "message": "Car upserted (existing VIN, no changes).",
                            "data": {"car": dict(row) if row else {"id": car_id}}}

                # Apply updates field-by-field (kept simple/explicit)
                updated = 0
                for field, value in sanitized.items():
                    cur = execute_query(conn, is_pg, f"UPDATE cars SET {field} = ? WHERE id = ?", (value, car_id))
                    if cur.rowcount > 0:
                        updated += 1

                conn.commit()
                cur = execute_query(conn, is_pg, "SELECT * FROM cars WHERE id = ?", (car_id,))
                row = cur.fetchone()
                return {"status": "success",
                        "message": "Car upserted (existing VIN updated)." if updated else "No fields changed.",
                        "data": {"car": dict(row) if row else {"id": car_id}, "updated_fields": updated}}

        # No VIN provided OR VIN does not exist -> insert a new row with a negative temp id
        temp_id = _next_temp_car_id(conn, is_pg)

        cur = execute_query(conn, is_pg, """
            INSERT INTO cars (
                id, vin, year, make, model, trim, mileage,
                interior_condition, exterior_condition,
                seller_ask_cents, buyer_offer_cents,
                created_at, lead_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            temp_id,
            vin_norm,
            patch.get("year"),
            patch.get("make"),
            patch.get("model"),
            patch.get("trim"),
            patch.get("mileage"),
            patch.get("interior_condition"),
            patch.get("exterior_condition"),
            patch.get("seller_ask_cents"),
            patch.get("buyer_offer_cents"),
            patch.get("created_at"),
            patch.get("lead_id"),
        ))

        conn.commit()
        cur = execute_query(conn, is_pg, "SELECT * FROM cars WHERE id = ?", (temp_id,))
        row = cur.fetchone()
        return {"status": "success", "message": "Car added.", "data": {"car": dict(row) if row else {"id": temp_id}}}

    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        # Get full error details
        error_msg = str(e)
        error_type = type(e).__name__
        msg_lower = error_msg.lower()
        
        # Log the full error for debugging
        logger = logging.getLogger(__name__)
        logger.error(f"car_add error: {error_type}: {error_msg}", exc_info=True)
        
        if "foreign key" in msg_lower:
            return {"status": "error", "code": "PRECONDITION_FAILED", "message": "Invalid reference (foreign key).",
                    "data": {"lead_id": patch.get("lead_id"), "error": error_msg}}
        if "unique" in msg_lower or "integrity" in msg_lower or "duplicate" in msg_lower:
            return {"status": "error", "code": "PRECONDITION_FAILED", "message": f"Integrity error: {error_msg}", "data": {"error": error_msg}}
        if "not null" in msg_lower:
            return {"status": "error", "code": "INVALID_INPUT", "message": f"Required field missing: {error_msg}", "data": {"error": error_msg}}
        return {"status": "error", "code": "TXN_FAILED", "message": f"Insert/upsert failed: {error_type}: {error_msg}", "data": {"error": error_msg, "error_type": error_type}}

    finally:
        try: conn.close()
        except Exception: pass


# helper_distance.py
# --- API key from .env ---
API_KEY = os.getenv("API_KEY")

# --- Directory where state CSV files live ---
CSV_DIR = Path("manheim_auction/by_state_csv")

# --- All bordering states (land borders; AK/HI/PR have none) ---
NEIGHBORS: Dict[str, List[str]] = {
    "AL": ["TN","GA","FL","MS"],
    "AK": [],
    "AZ": ["CA","NV","UT","CO","NM"],
    "AR": ["MO","TN","MS","LA","TX","OK"],
    "CA": ["OR","NV","AZ"],
    "CO": ["WY","NE","KS","OK","NM","AZ","UT"],
    "CT": ["NY","MA","RI"],
    "DE": ["MD","PA","NJ"],
    "FL": ["AL","GA"],
    "GA": ["FL","AL","TN","NC","SC"],
    "HI": [],
    "ID": ["WA","MT","WY","UT","NV","OR"],
    "IL": ["WI","IA","MO","KY","IN"],
    "IN": ["MI","OH","KY","IL"],
    "IA": ["MN","SD","NE","MO","IL","WI"],
    "KS": ["NE","MO","OK","CO"],
    "KY": ["IL","IN","OH","WV","VA","TN","MO"],
    "LA": ["TX","AR","MS"],
    "ME": ["NH"],
    "MD": ["VA","WV","PA","DE"],
    "MA": ["NY","VT","NH","CT","RI"],
    "MI": ["OH","IN","WI"],
    "MN": ["ND","SD","IA","WI"],
    "MS": ["TN","AL","LA","AR"],
    "MO": ["IA","IL","KY","TN","AR","OK","KS","NE"],
    "MT": ["ND","SD","WY","ID"],
    "NE": ["SD","IA","MO","KS","CO","WY"],
    "NV": ["OR","ID","UT","AZ","CA"],
    "NH": ["ME","VT","MA"],
    "NJ": ["NY","PA","DE"],
    "NM": ["AZ","UT","CO","OK","TX"],
    "NY": ["PA","NJ","CT","MA","VT"],
    "NC": ["VA","TN","GA","SC"],
    "ND": ["MT","SD","MN"],
    "OH": ["MI","PA","WV","KY","IN"],
    "OK": ["CO","KS","MO","AR","TX","NM"],
    "OR": ["WA","ID","NV","CA"],
    "PA": ["NY","NJ","DE","MD","WV","OH"],
    "RI": ["CT","MA"],
    "SC": ["NC","GA"],
    "SD": ["ND","MT","WY","NE","IA","MN"],
    "TN": ["KY","VA","NC","GA","AL","MS","AR","MO"],
    "TX": ["NM","OK","AR","LA"],
    "UT": ["ID","WY","CO","NM","AZ","NV"],
    "VT": ["NY","NH","MA"],
    "VA": ["NC","TN","KY","WV","MD"],
    "WA": ["OR","ID"],
    "WV": ["OH","PA","MD","VA","KY"],
    "WI": ["MN","IA","IL","MI"],
    "WY": ["MT","SD","NE","CO","UT","ID"],
    "PR": [],  # Puerto Rico present in your CSV set; no land borders
}

def _available_states() -> List[str]:
    """List state codes that actually have a CSV file in CSV_DIR."""
    return sorted(
        p.stem.upper()
        for p in CSV_DIR.glob("*.csv")
        if len(p.stem) == 2  # guard against weird filenames
    )

def _csv_path_for_state(state: str) -> Path:
    """Return the path to the CSV for the given 2-letter state code (raises if missing)."""
    state = (state or "").strip().upper()
    csv_file = CSV_DIR / f"{state}.csv"
    if not csv_file.exists():
        raise FileNotFoundError(f"No CSV file found for state '{state}' at {csv_file}")
    return csv_file

def _state_addresses(state: str, limit: int = 25) -> List[str]:
    """Read up to `limit` full addresses from a state's CSV."""
    path = _csv_path_for_state(state)
    addrs: List[str] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parts = []
            if row.get("address_street"):
                parts.append(row["address_street"])
            if row.get("city"):  parts.append(row["city"])
            if row.get("state"): parts.append(row["state"])
            if row.get("zip"):   parts.append(row["zip"])
            full = ", ".join(p for p in parts if p and str(p).lower() != "nan")
            if full:
                addrs.append(full)
            if len(addrs) >= limit:
                break
    return addrs

def _distance_matrix_best(user_address: str, dests: List[str]) -> Optional[Dict]:
    """One Distance Matrix call; return best element or None on error/empty."""
    if not API_KEY or not dests:
        return None
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": user_address,
        "destinations": "|".join(dests),
        "mode": "driving",
        "key": API_KEY,
    }
    try:
        data = requests.get(url, params=params, timeout=20).json()
    except Exception:
        return None
    if data.get("status") != "OK" or not data.get("rows"):
        return None
    elements = data["rows"][0].get("elements", [])
    if not elements:
        return None

    best_idx, best_dist_m = None, float("inf")
    for i, e in enumerate(elements):
        if e.get("status") == "OK":
            m = e["distance"]["value"]  # meters
            if m < best_dist_m:
                best_idx, best_dist_m = i, m
    if best_idx is None:
        return None

    best_el = elements[best_idx]
    return {
        "address": dests[best_idx],
        "distance_meters": best_dist_m,
        "duration_text": best_el["duration"]["text"],
    }

def _meters_to_miles(m: float) -> float:
    return round(m / 1609.344, 2)

def _best_in_state(user_address: str, state: str) -> Optional[Dict]:
    """Find the closest auction in a single state (if CSV exists)."""
    try:
        dests = _state_addresses(state)
    except FileNotFoundError:
        return None
    if not dests:
        return None
    # Append state to address for better geocoding accuracy
    normalized_address = user_address
    if state and state.upper() not in user_address.upper():
        normalized_address = f"{user_address}, {state}"
    best = _distance_matrix_best(normalized_address, dests)
    if not best:
        return None
    best["state"] = state
    best["state_csv"] = str(CSV_DIR / f"{state}.csv")
    best["distance_miles"] = _meters_to_miles(best.pop("distance_meters"))
    return best

def _best_among_states(user_address: str, states: List[str]) -> Optional[Dict]:
    """One Distance Matrix call per state; return overall best among those with CSVs."""
    overall = None
    for st in states:
        res = _best_in_state(user_address, st)
        if res and (overall is None or res["distance_miles"] < overall["distance_miles"]):
            overall = res
    return overall

def get_closest(user_address: str, state: str, max_miles: float = 100.0) -> Optional[Dict]:
    state = (state or "").strip().upper()
    available = _available_states()

    # 1) In-state (compute but don't early-return)
    in_state_best = _best_in_state(user_address, state) if state in available else None

    # 2) Neighbors (compute too)
    neighbors = [s for s in NEIGHBORS.get(state, []) if s in available]
    neighbor_best = _best_among_states(user_address, neighbors) if neighbors else None

    # If either in-state or neighbor is within threshold, pick the closest of those two
    candidates_under = [x for x in (in_state_best, neighbor_best) if x and x["distance_miles"] <= max_miles]
    if candidates_under:
        best = min(candidates_under, key=lambda x: x["distance_miles"])
        if best is neighbor_best:
            best["layer"] = "neighbor"
        else:
            best["layer"] = "in_state"
        best["neighbors_checked"] = neighbors
        best["threshold_exceeded"] = False
        return best

    # 3) National fallback (absolute nearest among remaining)
    excluded = set(([state] if state in available else []) + neighbors)
    remaining_states = [s for s in available if s not in excluded]
    national_best = _best_among_states(user_address, remaining_states)

    # Choose the absolute nearest among what we have
    candidates = [x for x in (in_state_best, neighbor_best, national_best) if x]
    if not candidates:
        return None
    best = min(candidates, key=lambda x: x["distance_miles"])

    # Correct layer labeling even when > max_miles
    if best is national_best:
        best["layer"] = "national"
    elif best is neighbor_best:
        best["layer"] = "neighbor"
    else:
        best["layer"] = "in_state"

    best["neighbors_checked"] = neighbors
    best["threshold_exceeded"] = best["distance_miles"] > max_miles
    return best


#-------------------------------------------------

#-----------------pickup-retrieve----------------------

#-------------------------------------------------


def pickup_retrieve(pick_up_id: int, sqlite_path: str) -> Dict[str, Any]:
    """
    Get one pickup row by pick_up_id from the sandbox DB.
    Returns: {"status": "success|error", "message": str, "data": {...}, ["code": str]}
    """
    # validate input
    try:
        pick_up_id = int(pick_up_id)
    except Exception:
        return {
            "status": "error",
            "code": "INVALID_INPUT",
            "message": "pick_up_id must be an integer.",
            "data": {"received": pick_up_id},
        }

    # open DB
    try:
        conn, is_pg = get_db_connection(sqlite_path)
    except Exception as e:
        return {
            "status": "error",
            "code": "DB_UNAVAILABLE",
            "message": f"Could not open database: {e}",
            "data": {},
        }

    try:
        # query
        cur = execute_query(conn, is_pg, "SELECT * FROM pickup WHERE pick_up_id = ?", (pick_up_id,))
        row = cur.fetchone()

        if not row:
            return {
                "status": "error",
                "code": "NOT_FOUND",
                "message": "Pickup not found.",
                "data": {"pick_up_id": pick_up_id},
            }

        return {
            "status": "success",
            "message": "Pickup retrieved.",
            "data": {"pickup": dict(row)},
        }

    except Exception as e:
        return {
            "status": "error",
            "code": "TXN_FAILED",
            "message": f"Lookup failed: {e}",
            "data": {},
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass

#-------------------------------------------------

#-----------------Get All Pickups----------------------

#-------------------------------------------------

def get_all_pickups(sqlite_path: str) -> Dict[str, Any]:
    """
    Retrieve all pickups from the database.
    Returns: {"status": "success|error", "message": str, "data": {"pickups": [...]}, ["code": str]}
    """
    try:
        conn, is_pg = get_db_connection(sqlite_path)
    except Exception as e:
        return {"status": "error", "code": "DB_UNAVAILABLE", "message": f"Could not open database: {e}", "data": {}}

    try:
        cur = execute_query(conn, is_pg, "SELECT * FROM pickup", ())
        rows = cur.fetchall()
        
        pickups = [dict(row) for row in rows]
        return {
            "status": "success",
            "message": f"Retrieved {len(pickups)} pickup(s).",
            "data": {"pickups": pickups, "count": len(pickups)}
        }
    except Exception as e:
        return {"status": "error", "code": "TXN_FAILED", "message": f"Query failed: {e}", "data": {}}
    finally:
        try:
            conn.close()
        except Exception:
            pass

#-------------------------------------------------

#-----------------pickup-update----------------------

#-------------------------------------------------




def pickup_update(pick_up_id: int, sqlite_path: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a pickup row. Only fields in `patch` are updated.
    Returns: {"status": "success|error", "message": str, "data": {...}, ["code": str]}
    """
    # 0) basic input checks
    if not isinstance(patch, dict) or not patch:
        return {"status": "error", "code": "INVALID_INPUT", "message": "patch must be a non-empty object.", "data": {}}
    try:
        pick_up_id = int(pick_up_id)
    except Exception:
        return {"status": "error", "code": "INVALID_INPUT", "message": "pick_up_id must be an integer.", "data": {"received": pick_up_id}}

    # 1) whitelist fields (prevents SQL injection via column names)
    ALLOWED_FIELDS = {"car_id", "address", "contact_phone", "pick_up_info", "created_at", "dropoff_time"}
    sanitized = {k: v for k, v in patch.items() if k in ALLOWED_FIELDS}
    if not sanitized:
        return {
            "status": "error",
            "code": "INVALID_INPUT",
            "message": "No allowed fields to update.",
            "data": {"allowed_fields": sorted(ALLOWED_FIELDS)}
        }

    # 2) open DB
    try:
        conn, is_pg = get_db_connection(sqlite_path)
    except Exception as e:
        return {"status": "error", "code": "DB_UNAVAILABLE", "message": f"Could not open database: {e}", "data": {}}

    try:
        # 3) ensure the pickup exists
        cur = execute_query(conn, is_pg, "SELECT 1 FROM pickup WHERE pick_up_id = ?", (pick_up_id,))
        if cur.fetchone() is None:
            return {"status": "error", "code": "NOT_FOUND", "message": f"Pickup id {pick_up_id} not found.", "data": {}}

        # 4) apply updates (one UPDATE per field)
        updated_fields = 0
        for field, value in sanitized.items():
            # safe because 'field' is whitelisted above
            cur = execute_query(conn, is_pg, f"UPDATE pickup SET {field} = ? WHERE pick_up_id = ?", (value, pick_up_id))
            if cur.rowcount > 0:
                updated_fields += 1

        conn.commit()
        msg = f"Pickup updated ({updated_fields} fields)." if updated_fields else "No fields changed."
        return {"status": "success", "message": msg, "data": {"pick_up_id": pick_up_id, "updated_fields": updated_fields}}

    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        msg = str(e).lower()
        if "foreign key" in msg:
            return {"status": "error", "code": "PRECONDITION_FAILED", "message": "Invalid reference (foreign key).", "data": {"car_id": patch.get("car_id")}}
        if "integrity" in msg:
            return {"status": "error", "code": "PRECONDITION_FAILED", "message": f"Integrity error: {e}", "data": {}}
        return {"status": "error", "code": "TXN_FAILED", "message": f"Update failed: {e}", "data": {}}

    finally:
        try: conn.close()
        except Exception: pass

#-------------------------------------------------

#-----------------pickup-add----------------------

#-------------------------------------------------



# ---------- PICKUP ADD (negative temp IDs like cars) ----------
def _next_temp_pickup_id(conn, is_pg: bool) -> int:
    """
    Next negative pick_up_id for sandbox-created rows.
    Starts at -1, then -2, -3, ...
    """
    cur = execute_query(conn, is_pg, "SELECT MIN(pick_up_id) as min_id FROM pickup", ())
    row = cur.fetchone()
    if row is None:
        return -1
    # Handle both SQLite (tuple) and PostgreSQL (dict)
    if is_pg:
        min_id = row.get("min_id") if isinstance(row, dict) else row[0]
    else:
        min_id = row[0] if isinstance(row, tuple) else row.get("min_id")
    return -1 if (min_id is None or min_id > 0) else (min_id - 1)

def pickup_add(sqlite_path: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add a new pickup with a negative pick_up_id (temporary).
    Expects at least car_id (if provided, it should exist).
    Returns: {"status": "success|error", "message": str, "data": {...}, ["code": str]}
    """
    # 0) basic input checks
    if not isinstance(patch, dict):
        return {"status": "error", "code": "INVALID_INPUT", "message": "patch must be an object.", "data": {}}

    # only allow known fields for insert
    ALLOWED = {"car_id", "address", "contact_phone", "pick_up_info", "created_at", "dropoff_time"}
    # (we'll still insert None for missing fields)
    try:
        conn, is_pg = get_db_connection(sqlite_path)
    except Exception as e:
        return {"status": "error", "code": "DB_UNAVAILABLE", "message": f"Could not open database: {e}", "data": {}}

    try:
        # 1) optional FK precheck (since PRAGMA foreign_keys might be OFF)
        car_id = patch.get("car_id")
        if car_id is not None:
            try:
                car_id_int = int(car_id)
            except Exception:
                return {"status": "error", "code": "INVALID_INPUT", "message": "car_id must be an integer.", "data": {"received": car_id}}
            cur = execute_query(conn, is_pg, "SELECT 1 FROM cars WHERE id = ?", (car_id_int,))
            if cur.fetchone() is None:
                return {"status": "error", "code": "PRECONDITION_FAILED", "message": "Invalid car_id (no such car).", "data": {"car_id": car_id_int}}
        else:
            car_id_int = None

        # 2) allocate negative temp id
        temp_id = _next_temp_pickup_id(conn, is_pg)

        # 3) insert (fill missing with None; ignore unknown keys)
        cur = execute_query(conn, is_pg, """
            INSERT INTO pickup (
                pick_up_id, car_id, address, contact_phone, pick_up_info, created_at, dropoff_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            temp_id,
            car_id_int,
            patch.get("address"),
            patch.get("contact_phone"),
            patch.get("pick_up_info"),
            patch.get("created_at"),
            patch.get("dropoff_time"),
        ))

        conn.commit()

        # 4) fetch & return
        cur = execute_query(conn, is_pg, "SELECT * FROM pickup WHERE pick_up_id = ?", (temp_id,))
        row = cur.fetchone()
        return {
            "status": "success",
            "message": "Pickup added.",
            "data": {"pickup": dict(row) if row else {"pick_up_id": temp_id}}
        }

    except Exception as e:
        try: conn.rollback()
        except Exception: pass
        msg = str(e).lower()
        if "foreign key" in msg:
            return {"status": "error", "code": "PRECONDITION_FAILED", "message": "Invalid reference (foreign key).", "data": {"car_id": car_id}}
        if "integrity" in msg:
            return {"status": "error", "code": "PRECONDITION_FAILED", "message": f"Integrity error: {e}", "data": {}}
        return {"status": "error", "code": "TXN_FAILED", "message": f"Insert failed: {e}", "data": {}}

    finally:
        try: conn.close()
        except Exception: pass

# Initialize SDK
rcsdk = SDK(
    os.environ.get("RC_APP_CLIENT_ID"),
    os.environ.get("RC_APP_CLIENT_SECRET"),
    "https://platform.ringcentral.com"
)
platform = rcsdk.platform()

# Login with JWT
def login():
    try:
        platform.login(jwt=os.environ.get("RC_USER_JWT"))
    except Exception as e:
        sys.exit("Unable to authenticate. Check credentials. " + str(e))

# Function to send message
def send_escalate_message(receiver_number: str, message_text: str):
    try:
        # Ensure we're logged in before sending
        if not platform.logged_in():
            login()
        
        # Pick the first phone number that has SMS capability
        try:
            resp = platform.get("/restapi/v1.0/account/~/extension/~/phone-number")
        except Exception as auth_error:
            # If API call fails due to auth, try logging in again
            if "token" in str(auth_error).lower() or "unauthorized" in str(auth_error).lower() or "expired" in str(auth_error).lower():
                login()
                resp = platform.get("/restapi/v1.0/account/~/extension/~/phone-number")
            else:
                raise
        
        jsonObj = resp.json()

        from_number = None
        for record in jsonObj.records:
            if "SmsSender" in record.features:
                from_number = record.phoneNumber
                break

        if not from_number:
            print("No SMS-capable number found for this account.")
            return

        # Send the SMS
        bodyParams = {
            "from": {"phoneNumber": from_number},
            "to": [{"phoneNumber": receiver_number}],
            "text": message_text,
        }
        endpoint = "/restapi/v1.0/account/~/extension/~/sms"
        try:
            resp = platform.post(endpoint, bodyParams)
            # Message sent successfully (ID logged but not printed to user)
        except Exception as auth_error:
            # If SMS send fails due to auth, try logging in again and retry
            if "token" in str(auth_error).lower() or "unauthorized" in str(auth_error).lower() or "expired" in str(auth_error).lower():
                login()
                resp = platform.post(endpoint, bodyParams)
                # Message sent successfully (ID logged but not printed to user)
            else:
                raise

    except Exception as e:
        print("Error sending message:", e)

