#!/usr/bin/env python3
# ------------------------------------------------------------
# Classify Manheim locations by state from address strings.
# Input : manheim_locations.csv  (expects columns incl. 'address' and 'website')
# Output: manheim_locations_enriched.csv
#         state_summary.csv
#         by_state_csv/<ST>.csv
#
# pip install pandas
# ------------------------------------------------------------

import os
import re
import pandas as pd
from html import unescape

INPUT   = "manheim_locations.csv"
OUTPUT  = "manheim_locations_enriched.csv"
SUMMARY = "state_summary.csv"
BY_STATE_DIR = "by_state_csv"

# --- State maps ---
STATE_NAME_TO_ABBR = {
    "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO",
    "Connecticut":"CT","Delaware":"DE","District Of Columbia":"DC","District of Columbia":"DC",
    "Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA",
    "Kansas":"KS","Kentucky":"KY","Louisiana":"LA","Maine":"ME","Maryland":"MD","Massachusetts":"MA",
    "Michigan":"MI","Minnesota":"MN","Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE",
    "Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ","New Mexico":"NM","New York":"NY",
    "North Carolina":"NC","North Dakota":"ND","Ohio":"OH","Oklahoma":"OK","Oregon":"OR",
    "Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD","Tennessee":"TN",
    "Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA","West Virginia":"WV",
    "Wisconsin":"WI","Wyoming":"WY","Puerto Rico":"PR"
}
STATE_ABBRS = set(STATE_NAME_TO_ABBR.values())

# --- Regex helpers ---
# Primary strict pattern: "Street..., City, ST ZIP" or "Street..., City, StateName ZIP"
CITY_STATE_ZIP_STRICT = re.compile(
    r"^\s*(?P<street>.+?),\s*"
    r"(?P<city>[A-Za-z0-9 .'\-]+?),\s*"
    r"(?P<state>(?:[A-Z]{2}|[A-Za-z .'\-]{3,}?))(?:,)?\s+"
    r"(?P<zip>\d{5}(?:-\d{3,4})?)\s*$"
)

# Loose fallback: just grab the last "City, ST ZIP" (allows extra commas elsewhere)
CITY_STATE_ZIP_LOOSE = re.compile(
    r"(?P<city>[A-Za-z0-9 .'\-]+?),\s*(?P<state>(?:[A-Z]{2}|[A-Za-z .'\-]{3,}?))(?:,)?\s+"
    r"(?P<zip>\d{5}(?:-\d{3,4})?)\s*$"
)

def clean(s: str) -> str:
    if s is None:
        return ""
    s = unescape(str(s))
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip(" ,;\t\r\n")
    return s

def strip_noise(addr: str) -> str:
    s = clean(addr)
    # Drop trailing "Get Directions" noise (and any trailing commas/spaces)
    s = re.sub(r"\bGet Directions\b", "", s, flags=re.I)
    s = re.sub(r"\s{2,}", " ", s).strip(" ,")
    # Collapse accidental double commas
    s = re.sub(r",\s*,", ", ", s)
    return s

def norm_state_code(val: str) -> str:
    v = clean(val)
    if not v:
        return ""
    up = v.upper()
    if len(up) == 2 and up in STATE_ABBRS:
        return up
    # Map full name → code
    name = v.title()
    return STATE_NAME_TO_ABBR.get(name, "")

def parse_address(addr: str):
    """
    Returns (street, city, state_code, zip).
    Tries a strict pattern; if it fails, uses a looser pattern that pulls the last City/ST/ZIP.
    """
    s = strip_noise(addr)
    if not s:
        return "", "", "", ""

    # Strict first
    m = CITY_STATE_ZIP_STRICT.search(s)
    if m:
        street = clean(m.group("street"))
        city   = clean(m.group("city"))
        st_raw = clean(m.group("state"))
        zipc   = clean(m.group("zip"))
        st     = norm_state_code(st_raw) or st_raw  # keep raw if we can’t map
        return street, city, st, zipc

    # Loose fallback
    m = CITY_STATE_ZIP_LOOSE.search(s)
    if m:
        city   = clean(m.group("city"))
        st_raw = clean(m.group("state"))
        zipc   = clean(m.group("zip"))
        st     = norm_state_code(st_raw) or st_raw
        # Street is whatever precedes the match
        street = clean(s[:m.start()]).rstrip(", ")
        return street, city, st, zipc

    return "", "", "", ""

def main():
    # --- Load input ---
    if not os.path.exists(INPUT):
        raise SystemExit(f"Input CSV not found: {INPUT}")
    df = pd.read_csv(INPUT)

    # Keep originals for reference (avoid name collisions later)
    for c in ["address","city","state","zip"]:
        if c in df.columns:
            df.rename(columns={c: f"{c}_orig"}, inplace=True)

    # Ensure required columns exist
    for c in ["address_orig","website","phone","name"]:
        if c not in df.columns:
            df[c] = ""

    # Clean & parse
    df["address_clean"] = df["address_orig"].fillna("").map(strip_noise)

    parsed = df["address_clean"].apply(parse_address)
    df[["street_norm","city_norm","state_norm","zip_norm"]] = pd.DataFrame(parsed.tolist(), index=df.index)

    # Prefer existing non-empty city/state/zip over parsed; otherwise use parsed
    def prefer(a, b):
        a = clean(a); b = clean(b)
        return a if a else b

    df["city_final"]   = [prefer(a, b) for a, b in zip(df.get("city_orig",""), df["city_norm"])]
    # normalize any full state names to 2-letter codes
    df["state_final"]  = [prefer(norm_state_code(a), b) for a, b in zip(df.get("state_orig",""), df["state_norm"])]
    df["zip_final"]    = [prefer(a, b) for a, b in zip(df.get("zip_orig",""), df["zip_norm"])]
    # address street: if we already had a full city/state/zip originally, keep original street; else parsed
    df["street_final"] = [
        clean(a) if (clean(df.get("city_orig","")[i]) and clean(df.get("state_orig","")[i]) and clean(df.get("zip_orig","")[i]))
        else clean(df["street_norm"][i])
        for i, a in enumerate(df.get("address_orig",""))
    ]

    # Build final output frame (no duplicate column names)
    cols_front = [
        "name",
        "street_final", "city_final", "state_final", "zip_final",
        "phone", "website",
    ]
    # Keep lat/long if present (optional)
    for c in ["latitude","longitude"]:
        if c in df.columns:
            cols_front.append(c)

    out = df[cols_front].rename(columns={
        "street_final": "address_street",
        "city_final":   "city",
        "state_final":  "state",
        "zip_final":    "zip",
    }).copy()

    # Safety: ensure unique columns
    out = out.loc[:, ~out.columns.duplicated()]

    # --- Write enriched CSV ---
    out.to_csv(OUTPUT, index=False)

    # --- Summary by state ---
    summary = (
        out.groupby("state", dropna=False)
           .size()
           .reset_index(name="count")
           .query("state != ''")
           .sort_values(["count","state"], ascending=[False, True])
    )
    summary.to_csv(SUMMARY, index=False)

    # --- Per-state CSVs ---
    os.makedirs(BY_STATE_DIR, exist_ok=True)
    for st, sub in out.groupby("state", dropna=False):
        if isinstance(st, str) and st:
            sub.to_csv(os.path.join(BY_STATE_DIR, f"{st}.csv"), index=False)

    # Console preview
    print("Top states by location count:")
    if not summary.empty:
        print(summary.head(10).to_string(index=False))
    print(f"\nWrote:\n  {OUTPUT}\n  {SUMMARY}\n  per-state files in ./{BY_STATE_DIR}/")

if __name__ == "__main__":
    main()
