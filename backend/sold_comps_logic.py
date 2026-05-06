"""Multi-strategy matching for buyer sold comps — tight first, then safe fallbacks."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

from backend.zip_normalize import normalize_us_zip_5


@dataclass(frozen=True)
class CompStrategy:
    months_back: int
    sqft_band_pct: float  # e.g. 0.30 → ±30% of subject sq ft
    bed_delta: float  # e.g. 1.0 → beds within ±1
    label: str


def comp_strategies_for_lookback(months_back: int) -> tuple[CompStrategy, ...]:
    """
    For a chosen maximum lookback (6–36 months), relax match rules in order:
    standard → wider size band → wider bedroom band. All use the same time window.
    """
    return (
        CompStrategy(months_back, 0.30, 1.0, "standard"),
        CompStrategy(months_back, 0.50, 1.0, "wider_size"),
        CompStrategy(months_back, 0.50, 2.0, "wider_beds"),
    )


def filter_sold_comps_df(
    df: pd.DataFrame,
    *,
    subject_zip: str | None,
    subject_beds: float | None,
    subject_sqft: float | None,
    subject_mls_id: str | None,
    months_back: int,
    sqft_band_pct: float,
    bed_delta: float,
) -> pd.DataFrame:
    df_f = df.copy()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=30 * months_back)
    if "settled_dt" in df_f.columns:
        df_f = df_f[df_f["settled_dt"] >= cutoff]
    df_f = df_f[
        (pd.to_numeric(df_f["sale_price"], errors="coerce") > 0)
        & (df_f.get("dataset_type") == "sold")
    ]

    if subject_mls_id is not None and "mls_id" in df_f.columns:
        df_f = df_f[df_f["mls_id"].astype(str) != str(subject_mls_id)]

    if subject_zip:
        df_f = df_f[df_f["zip_code"].astype(str).str.zfill(5) == subject_zip]

    beds = pd.to_numeric(df_f["bedrooms"], errors="coerce")
    if subject_beds is not None:
        df_f = df_f[(beds >= subject_beds - bed_delta) & (beds <= subject_beds + bed_delta)]

    sqft = pd.to_numeric(df_f.get("square_feet"), errors="coerce")
    if subject_sqft is not None and subject_sqft > 0:
        low = subject_sqft * (1.0 - sqft_band_pct)
        high = subject_sqft * (1.0 + sqft_band_pct)
        df_f = df_f[(sqft >= low) & (sqft <= high)]

    return df_f


def pick_comp_candidates(
    df: pd.DataFrame,
    subject,
    *,
    max_months_back: int = 12,
    min_desirable: int = 3,
) -> tuple[pd.DataFrame, CompStrategy | None]:
    """
    Walk strategies until we have at least ``min_desirable`` rows, or use the
    broadest non-empty result. The time window is ``max_months_back`` (buyer lookback).
    """
    subj_zip = normalize_us_zip_5(subject.zip_code)
    subj_beds = float(subject.bedrooms) if subject.bedrooms is not None else None
    subj_sqft = float(subject.square_feet) if subject.square_feet is not None else None
    subj_mls = getattr(subject, "mls_id", None)

    chosen: pd.DataFrame | None = None
    chosen_strat: CompStrategy | None = None

    for strat in comp_strategies_for_lookback(max_months_back):
        d = filter_sold_comps_df(
            df,
            subject_zip=subj_zip,
            subject_beds=subj_beds,
            subject_sqft=subj_sqft,
            subject_mls_id=subj_mls,
            months_back=strat.months_back,
            sqft_band_pct=strat.sqft_band_pct,
            bed_delta=strat.bed_delta,
        )
        if d.empty:
            continue
        chosen = d
        chosen_strat = strat
        if len(d) >= min_desirable:
            break

    if chosen is None:
        return pd.DataFrame(), None
    return chosen, chosen_strat


def buyer_match_hint(strategy: CompStrategy | None) -> str | None:
    """Short UI hint when matches used a relaxed rule set."""
    if strategy is None:
        return None
    if strategy.label == "standard":
        return None
    if strategy.label == "wider_size":
        return "Comparable sales use a broader size range around this home."
    if strategy.label == "wider_beds":
        return "Comparable sales use a broader bedroom range."
    return "Comparable sales use relaxed matching rules for this area."
