from pathlib import Path
import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).parent
CLEANED_DIR = PROJECT_DIR / "cleaned"
ANALYTICS_DIR = PROJECT_DIR / "analytics"

ANALYTICS_DIR.mkdir(exist_ok=True)

INPUT_FILE = CLEANED_DIR / "rentals_clean_latest.csv"
OUTPUT_BEDROOM_FILE = ANALYTICS_DIR / "rent_by_zip_bedrooms.csv"
OUTPUT_SQFT_FILE = ANALYTICS_DIR / "rent_by_zip_sqft.csv"


def confidence_label(n: int) -> str:
    if n >= 20:
        return "High"
    elif n >= 8:
        return "Medium"
    elif n >= 1:
        return "Low"
    return "None"


def load_rentals() -> pd.DataFrame:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_FILE}")

    print(f"Loading rentals from: {INPUT_FILE}")
    # Read ZIPs as strings so leading zeroes are preserved (e.g., 02116).
    df = pd.read_csv(INPUT_FILE, low_memory=False, dtype={"zip_code": "string"})

    # Ensure expected columns exist
    required_cols = ["zip_code", "bedrooms", "rent_price"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in rentals file: {missing}")

    # Coerce types
    df["zip_code"] = (
        df["zip_code"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0+$", "", regex=True)
        .str.extract(r"(\d{1,5})", expand=False)
        .str.zfill(5)
    )
    df["bedrooms"] = pd.to_numeric(df["bedrooms"], errors="coerce")
    df["rent_price"] = pd.to_numeric(df["rent_price"], errors="coerce")

    if "square_feet" in df.columns:
        df["square_feet"] = pd.to_numeric(df["square_feet"], errors="coerce")
    else:
        df["square_feet"] = np.nan

    if "town" not in df.columns:
        df["town"] = np.nan

    # Keep studios (0 beds), but drop nonsense
    df = df[df["zip_code"].notna()].copy()
    df = df[df["rent_price"].notna()].copy()
    df = df[df["rent_price"] >= 700].copy()
    df = df[df["rent_price"] <= 20000].copy()

    # Bedrooms:
    # keep studios (0), and reasonable upper range
    df = df[df["bedrooms"].notna()].copy()
    df = df[(df["bedrooms"] >= 0) & (df["bedrooms"] <= 8)].copy()

    # Rent per sqft for backup model
    df["rent_per_sqft"] = np.where(
        (df["square_feet"].fillna(0) > 0),
        df["rent_price"] / df["square_feet"],
        np.nan
    )

    print(f"Rows remaining after rent-model filtering: {len(df):,}")
    return df


def build_zip_bedroom_model(df: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        df.groupby(["zip_code", "bedrooms"], dropna=False)
        .agg(
            sample_size=("mls_id", "count"),
            avg_rent=("rent_price", "mean"),
            median_rent=("rent_price", "median"),
            min_rent=("rent_price", "min"),
            max_rent=("rent_price", "max"),
            avg_sqft=("square_feet", "mean"),
            median_sqft=("square_feet", "median"),
            avg_rent_per_sqft=("rent_per_sqft", "mean"),
            median_rent_per_sqft=("rent_per_sqft", "median"),
            towns_seen=("town", lambda s: ", ".join(sorted(set([str(x) for x in s.dropna()]))[:5])),
        )
        .reset_index()
    )

    grouped["confidence"] = grouped["sample_size"].apply(confidence_label)

    # Round for readability
    for col in ["avg_rent", "median_rent", "min_rent", "max_rent", "avg_sqft", "median_sqft",
                "avg_rent_per_sqft", "median_rent_per_sqft"]:
        if col in grouped.columns:
            grouped[col] = grouped[col].round(2)

    # Sort nicely
    grouped = grouped.sort_values(["zip_code", "bedrooms"]).reset_index(drop=True)
    return grouped


def build_zip_sqft_model(df: pd.DataFrame) -> pd.DataFrame:
    sqft_df = df[df["rent_per_sqft"].notna()].copy()

    grouped = (
        sqft_df.groupby(["zip_code"], dropna=False)
        .agg(
            sample_size=("mls_id", "count"),
            avg_rent=("rent_price", "mean"),
            median_rent=("rent_price", "median"),
            avg_sqft=("square_feet", "mean"),
            median_sqft=("square_feet", "median"),
            avg_rent_per_sqft=("rent_per_sqft", "mean"),
            median_rent_per_sqft=("rent_per_sqft", "median"),
            towns_seen=("town", lambda s: ", ".join(sorted(set([str(x) for x in s.dropna()]))[:5])),
        )
        .reset_index()
    )

    grouped["confidence"] = grouped["sample_size"].apply(confidence_label)

    for col in ["avg_rent", "median_rent", "avg_sqft", "median_sqft",
                "avg_rent_per_sqft", "median_rent_per_sqft"]:
        if col in grouped.columns:
            grouped[col] = grouped[col].round(2)

    grouped = grouped.sort_values(["zip_code"]).reset_index(drop=True)
    return grouped


def build_rent_models() -> tuple[Path, Path]:
    df = load_rentals()

    print("Building ZIP + bedroom rent model...")
    rent_by_zip_bed = build_zip_bedroom_model(df)
    rent_by_zip_bed.to_csv(OUTPUT_BEDROOM_FILE, index=False)
    print(f"Saved: {OUTPUT_BEDROOM_FILE} ({len(rent_by_zip_bed):,} rows)")

    print("Building ZIP + sqft fallback model...")
    rent_by_zip_sqft = build_zip_sqft_model(df)
    rent_by_zip_sqft.to_csv(OUTPUT_SQFT_FILE, index=False)
    print(f"Saved: {OUTPUT_SQFT_FILE} ({len(rent_by_zip_sqft):,} rows)")

    print("Done.")
    return OUTPUT_BEDROOM_FILE, OUTPUT_SQFT_FILE


def main():
    build_rent_models()


if __name__ == "__main__":
    main()
