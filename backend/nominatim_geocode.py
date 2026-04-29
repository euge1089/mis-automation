"""Nominatim geocoding for active listings (shared cache with geocode_active.py)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_DIR / "history" / "geocoding"
CACHE_FILE = CACHE_DIR / "geocode_cache.csv"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "mls-automation-geocoder/1.0"


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,")


def _strip_unit_details(address: str) -> str:
    """
    Remove apartment / unit / building tokens that break Nominatim (especially urban condos).
    Runs multiple passes; also drops ", 3," style unit-only segments between street and city.
    """
    if not address or not str(address).strip():
        return ""
    cleaned = str(address)
    patterns = [
        # Word-based units (allow optional # / dash glued to token)
        r"\b(APT|APARTMENT|UNIT|STE|SUITE|FL\.?|FLOOR|BLDG|BUILDING|PH|PENTHOUSE|LVL|LEVEL)\b\.?[#\s,/-]*[A-Z0-9\-/]+",
        r"#\s*[A-Z0-9\-/]+",
        r",\s*(APT|APARTMENT|UNIT|STE|SUITE)\s*\.?[#\s]*[A-Z0-9\-/]+",
        r"\b(NO\.?|NUMBER|NOS?\.?)\s*[A-Z0-9\-]+",
        r"\b(ROOM|RM)\s*[#\s]*[A-Z0-9\-]+",
        # MLS-style unit shorthand like "U:635" or "U:3"
        r"\bU:[A-Z0-9\-]+",
        # Trailing " - 2B" or " - PH1"
        r"\s+-\s*[A-Z0-9]{1,6}\s*(?=,|\s*$)",
    ]
    for _ in range(6):
        prev = cleaned
        for pat in patterns:
            cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE)
        cleaned = _normalize_whitespace(cleaned)
        if cleaned == prev:
            break
    # "100 Main St, 4, Boston, MA" → drop the middle numeric unit chunk
    cleaned = re.sub(r",\s*\d{1,3}[A-Za-z]?\s*,", ",", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r",\s*,", ",", cleaned)
    return _normalize_whitespace(cleaned)


def address_query_candidates(
    full_address: str | None,
    address: str | None,
    town: str | None,
    state: str | None,
    zip_code: str | None,
) -> list[str]:
    fa = _normalize_whitespace(str(full_address or ""))
    ad = _normalize_whitespace(str(address or ""))
    tn = _normalize_whitespace(str(town or ""))
    st = _normalize_whitespace(str(state or ""))
    zc = _normalize_whitespace(str(zip_code or ""))

    base_line = _normalize_whitespace(", ".join([x for x in [ad, tn, st] if x]))
    base_with_zip = _normalize_whitespace(", ".join([x for x in [ad, tn, st, zc] if x]))

    candidates = [
        fa,
        _strip_unit_details(fa),
        base_with_zip,
        _strip_unit_details(base_with_zip),
        base_line,
        _strip_unit_details(base_line),
        _normalize_whitespace(", ".join([x for x in [tn, st, zc] if x])),
    ]
    if base_with_zip:
        candidates.append(f"{base_with_zip}, USA")
    elif base_line:
        candidates.append(f"{base_line}, USA")

    out: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        if not c or c.lower() in seen:
            continue
        seen.add(c.lower())
        out.append(c)
    return out


def nominatim_lookup(query: str) -> tuple[float, float] | None:
    url = f"{NOMINATIM_BASE}?q={quote(query)}&format=json&limit=1"
    req = Request(url=url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
        return None

    if not payload:
        return None
    try:
        lat = float(payload[0]["lat"])
        lon = float(payload[0]["lon"])
        return lat, lon
    except (KeyError, ValueError, TypeError):
        return None


def load_query_cache() -> dict[str, tuple[float, float] | None]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not CACHE_FILE.exists():
        return {}
    cache_df = pd.read_csv(CACHE_FILE, low_memory=False)
    cache: dict[str, tuple[float, float] | None] = {}
    for _, row in cache_df.iterrows():
        q = str(row.get("query", "")).strip()
        if not q:
            continue
        lat, lon = row.get("latitude"), row.get("longitude")
        if pd.isna(lat) or pd.isna(lon):
            cache[q] = None
        else:
            cache[q] = (float(lat), float(lon))
    return cache


def save_query_cache(cache: dict[str, tuple[float, float] | None]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for query, value in cache.items():
        if value is None:
            rows.append({"query": query, "latitude": None, "longitude": None})
        else:
            rows.append({"query": query, "latitude": value[0], "longitude": value[1]})
    pd.DataFrame(rows).to_csv(CACHE_FILE, index=False)


def geocode_one_listing(
    *,
    full_address: str | None,
    address: str | None,
    town: str | None,
    state: str | None,
    zip_code: str | None,
    cache: dict[str, tuple[float, float] | None],
    rate_limit_seconds: float,
) -> tuple[float, float] | None:
    for candidate in address_query_candidates(
        full_address, address, town, state, zip_code
    ):
        if candidate in cache:
            found = cache[candidate]
        else:
            found = nominatim_lookup(candidate)
            cache[candidate] = found
            time.sleep(rate_limit_seconds)
        if found is not None:
            return found
    return None
