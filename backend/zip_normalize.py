"""Normalize user-entered US ZIP codes to 5-digit strings (leading zeros)."""
from __future__ import annotations

import re

from sqlalchemy import String, and_, cast, func
from sqlalchemy.sql.elements import ColumnElement


def normalize_us_zip_5(code: str | None) -> str | None:
    if code is None:
        return None
    stripped = str(code).strip()
    if not stripped:
        return None
    digits = re.sub(r"\D", "", stripped)
    if not digits:
        return None
    if len(digits) >= 9:
        digits = digits[:5]
    elif len(digits) > 5:
        digits = digits[:5]
    elif len(digits) < 5:
        digits = digits.zfill(5)
    return digits


def zip_column_eq_normalized(column, zip_norm: str) -> ColumnElement:
    """
    SQL filter: true when the column's ZIP matches zip_norm after digit-extract + 5-digit pad.

    Matches DB values stored as 2127, "2127", "02127", or 2127.0 from CSV float coercion.
    """
    z = cast(column, String)
    digits = func.regexp_replace(func.coalesce(z, ""), r"[^0-9]", "", "g")
    padded = func.lpad(func.substr(digits, 1, 5), 5, "0")
    return and_(func.length(digits) > 0, padded == zip_norm)
