#!/usr/bin/env python3
# scrapper.py
# ------------------------------------------------------------
# Scrapes ALL Manheim US locations from the paginated list.
# Output: manheim_locations.csv with:
#   name,address,city,state,zip,phone,latitude,longitude,website
#
# Install:
#   pip install requests beautifulsoup4 pandas
# Run:
#   python scrapper.py
# ------------------------------------------------------------

import re, time, requests, pandas as pd
from bs4 import BeautifulSoup, Tag
from html import unescape
from urllib.parse import urljoin

BASE = "https://site.manheim.com"
INDEX = f"{BASE}/en/country/us-locations"
UA    = "GMTV-Manheim-Locations-Scraper/6.0 (+you@example.com)"
PAUSE = 0.5  # be polite

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "en"})

# ---------- helpers ----------

CITY_ST_ZIP = re.compile(r"([A-Za-z .'\-]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$")
PHONE_RE    = re.compile(r"(\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4})")

def clean(s: str) -> str:
    s = unescape(s or "")
    s = s.replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip(' "\'\t\r\n')

def split_br_lines_html(inner_html: str) -> list[str]:
    """Split an address block by <br>, drop noise like 'Get Directions'."""
    parts = re.split(r"<br\s*/?>", inner_html or "", flags=re.I)
    lines = [clean(re.sub(r"<.*?>", "", p)) for p in parts]
    return [ln for ln in lines if ln and ln.lower() not in {"get directions","directions"}]

def parse_city_state_zip(lines: list[str]):
    """Use the last 'City, ST ZIP' line; earlier lines form the street address."""
    idx = -1
    for i in range(len(lines)-1, -1, -1):
        if CITY_ST_ZIP.search(lines[i]):
            idx = i; break
    if idx == -1:
        return "", "", "", ", ".join(lines)
    m = CITY_ST_ZIP.search(lines[idx])
    city, st, zipc = clean(m.group(1)), m.group(2), m.group(3)
    street = ", ".join([l for l in lines[:idx] if l])
    return city, st, zipc, street

def dedupe_rows(rows):
    seen, out = set(), []
    for r in rows:
        key = (r.get("name",""), r.get("city",""), r.get("state",""))
        if key in seen:
            continue
        seen.add(key); out.append(r)
    return out

# ---------- core scraping ----------

def fetch(url: str) -> BeautifulSoup:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def get_total_pages(soup: BeautifulSoup) -> int:
    """Find the highest /page/N link; default to 1 if none."""
    max_n = 1
    for a in soup.select('a[href*="/en/country/us-locations/page/"]'):
        m = re.search(r"/page/(\d+)", a.get("href", ""))
        if m:
            max_n = max(max_n, int(m.group(1)))
    return max_n

def fragment_after_h3_until_next_h3(h3: Tag) -> BeautifulSoup:
    """
    Build a fragment that starts at this <h3> and includes all subsequent
    elements (depth-first) up to (but not including) the NEXT <h3>.
    This is more robust than walking only next_sibling.
    """
    parts = [str(h3)]
    node = h3.next_element
    while node:
        # stop at the next *separate* <h3>
        if isinstance(node, Tag) and node.name == "h3" and node is not h3:
            break
        parts.append(str(node))
        node = node.next_element
    return BeautifulSoup("".join(parts), "html.parser")

def parse_card_fragment(card: BeautifulSoup):
    # name
    h = card.find("h3")
    name = clean(h.get_text(" ", strip=True)) if h else ""
    if not name:
        return None

    # 1) Try labeled 'Address' then its following <p>
    street = city = state = zipc = ""
    addr_lines = []
    addr_label = card.find(lambda t: t.name in ["h4","h5","strong"] and "address" in t.get_text(" ", strip=True).lower())
    if addr_label:
        # prefer the first following <p> or <div> that contains the address lines
        nxt = addr_label.find_next(lambda t: t.name in ["p","div"] and t.get_text(strip=True))
        if nxt:
            addr_lines = split_br_lines_html(str(nxt))

    # 2) Fallback: last <p> in the fragment that looks like it contains "City, ST ZIP"
    if not addr_lines:
        candidates = [p for p in card.find_all("p") if CITY_ST_ZIP.search(p.get_text(" ", strip=True))]
        if candidates:
            addr_lines = split_br_lines_html(str(candidates[-1]))

    if addr_lines:
        city, state, zipc, street = parse_city_state_zip(addr_lines)

    # phone: search near 'Phone' label; else anywhere in fragment
    phone = ""
    phone_label = card.find(lambda t: t.name in ["h4","h5","strong"] and "phone" in t.get_text(" ", strip=True).lower())
    if phone_label:
        # look in the next block
        nxt = phone_label.find_next(lambda t: t.name in ["p","div"] and t.get_text(strip=True))
        chunk = clean(nxt.get_text(" ", strip=True)) if nxt else ""
        m = PHONE_RE.search(chunk)
        if not m:
            m = PHONE_RE.search(card.get_text(" ", strip=True))
        if m:
            phone = m.group(1)
    else:
        m = PHONE_RE.search(card.get_text(" ", strip=True))
        if m:
            phone = m.group(1)

    # detail page link (optional)
    website = ""
    for a in card.find_all("a", href=True):
        href = a["href"]
        if "/en/locations/us-locations/" in href:
            website = href if href.startswith("http") else urljoin(BASE, href)
            break

    # keep only meaningful rows
    if not (street or (city and state) or website):
        return None

    return {
        "name": name,
        "address": clean(street),
        "city": clean(city),
        "state": clean(state),
        "zip": clean(zipc),
        "phone": clean(phone),
        "latitude": "",
        "longitude": "",
        "website": website
    }

def scrape_all_pages():
    rows = []
    soup = fetch(INDEX)
    total = get_total_pages(soup)
    print(f"Detected {total} pages of US locations at {INDEX}")

    for page_n in range(1, total + 1):
        url = INDEX if page_n == 1 else f"{INDEX}/page/{page_n}"
        print(f"Scraping page {page_n}/{total}: {url}")
        soup = fetch(url)

        # Preferred: if the page provides explicit card containers, use them
        containers = soup.select(".single_location_container, .single-location_container")
        if containers:
            for cont in containers:
                frag = BeautifulSoup(str(cont), "html.parser")
                data = parse_card_fragment(frag)
                if data:
                    rows.append(data)
        else:
            # Fallback: slice by <h3> headings using depth-first traversal
            for h3 in soup.find_all("h3"):
                frag = fragment_after_h3_until_next_h3(h3)
                data = parse_card_fragment(frag)
                if data:
                    rows.append(data)

        time.sleep(PAUSE)
    return rows

def main():
    rows = scrape_all_pages()
    rows = dedupe_rows(rows)
    df = pd.DataFrame(rows, columns=[
        "name","address","city","state","zip","phone","latitude","longitude","website"
    ])
    df.to_csv("manheim_locations.csv", index=False)
    print(f"Wrote manheim_locations.csv with {len(df)} rows.")

if __name__ == "__main__":
    main()
