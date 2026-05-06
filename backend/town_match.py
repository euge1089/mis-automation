"""Match buyer-entered town names to MLS rows that often store \"City, ST\"."""
from __future__ import annotations

import re

import pandas as pd
from sqlalchemy import false, func, or_

# Trailing US state abbreviation after a comma (e.g. "Hingham, MA" -> "Hingham").
_TOWN_STATE_SUFFIX = re.compile(r",\s*[A-Za-z]{2}\s*$")


def normalize_town_query(town: str | None) -> str | None:
    """Strip trailing \", ST\" so \"Hingham\" and \"Hingham, MA\" both map to the same base name."""
    if town is None:
        return None
    s = str(town).strip()
    if not s:
        return None
    s = _TOWN_STATE_SUFFIX.sub("", s).strip()
    return s or None


def town_column_matches(column, town: str | None):
    """
    SQL filter: exact city name OR \"City,...\" (e.g. \"Hingham\" matches \"Hingham, MA\").
    If ``town`` is blank, returns None (caller should not filter).
    If ``town`` is unusable after normalization, returns a filter that matches no rows.
    """
    if not town or not str(town).strip():
        return None
    base = normalize_town_query(town)
    if not base:
        return false()
    tl = base.lower()
    return or_(func.lower(column) == tl, func.lower(column).like(tl + ",%"))


def pandas_town_matches(series: pd.Series, town: str | None) -> pd.Series:
    """Boolean mask aligned with ``series`` for sold/analytics dataframes."""
    if not town or not str(town).strip():
        return pd.Series(True, index=series.index)
    base = normalize_town_query(town)
    if not base:
        return pd.Series(False, index=series.index)
    tl = base.lower()
    col = series.astype(str).str.lower()
    return col.eq(tl) | col.str.startswith(tl + ",")
