from pathlib import Path
import pandas as pd
import numpy as np


PROJECT_DIR = Path(__file__).parent
COMBINED_DIR = PROJECT_DIR / "combined"
CLEANED_DIR = PROJECT_DIR / "cleaned"

CLEANED_DIR.mkdir(exist_ok=True)


KEEP_COLUMNS = [
    # IDs / status
    "LIST_NO",
    "STATUS",
    "STATUS_DATE",
    "PROP_TYPE",

    # Address / location
    "ADDRESS",
    "STREET_NUM",
    "STREET_NAME",
    "TOWN",
    "STATE",
    "ZIP_CODE",
    "ZIP_CODE_4",
    "COUNTY",
    "AREA",
    "NEIGHBORHOOD",

    # Pricing
    "LIST_PRICE",
    "ORIG_PRICE",
    "PREV_LIST_PRICE",
    "SALE_PRICE",
    "PRICE_PER_SQFT",
    "LIST_PRICE_PER_SQFT",
    "SOLD_PRICE_PER_SQFT",
    "SALE_TO_ASSESSED",
    "SaleToList",
    "TAXES",
    "TAX_YEAR",

    # Dates
    "LIST_DATE",
    "LIST_DATE_RCVD",
    "OFF_MKT_DATE",
    "SETTLED_DATE",
    "OFFER_DATE",
    "UPDATE_DATE",
    "PHOTO_DATE",
    "MARKET_TIME",
    "MARKET_TIME_BROKER",
    "MARKET_TIME_PROPERTY",

    # Core property stats
    "NO_BEDROOMS",
    "TOTAL_BATHS",
    "NO_FULL_BATHS",
    "NO_HALF_BATHS",
    "NO_ROOMS",
    "SQUARE_FEET",
    "SQUARE_FEET_SOURCE",
    "LOT_SIZE",
    "ACRE",
    "YEAR_BUILT",
    "YEAR_BUILT_SOURCE",
    "YEAR_BUILT_DESCRP",

    # Parking
    "PARKING_SPACES_SF",
    "PARKING_SPACES_CC",
    "PARKING_SPACES_MF",
    "GARAGE_SPACES_SF",
    "GARAGE_SPACES_CC",
    "GARAGE_SPACES_MF",

    # Property-type detail
    "STYLE_SF",
    "MF_TYPE_MF",
    "CC_TYPE_CC",
    "NO_UNITS_MF",

    # Multifamily unit-level bedrooms
    "BEDRMS_1_MF",
    "BEDRMS_2_MF",
    "BEDRMS_3_MF",
    "BEDRMS_4_MF",
    "BEDRMS_5_MF",

    # Multifamily unit-level full baths
    "F_BTHS_1_MF",
    "F_BTHS_2_MF",
    "F_BTHS_3_MF",
    "F_BTHS_4_MF",
    "F_BTHS_5_MF",

    # Multifamily unit-level half baths
    "H_BTHS_1_MF",
    "H_BTHS_2_MF",
    "H_BTHS_3_MF",
    "H_BTHS_4_MF",
    "H_BTHS_5_MF",

    # Multifamily rents / income
    "RENT1_MF",
    "RENT2_MF",
    "RENT3_MF",
    "RENT4_MF",
    "RENT5_MF",
    "TOTAL_RENT_MF",
    "GOI_MF",
    "NOI_MF",

    # Remarks / notes
    "REMARKS",
    "DISCLOSURES",
]


COLUMN_MAP = {
    "LIST_NO": "mls_id",
    "STATUS": "status",
    "STATUS_DATE": "status_date",
    "PROP_TYPE": "property_type",

    "ADDRESS": "address",
    "STREET_NUM": "street_num",
    "STREET_NAME": "street_name",
    "TOWN": "town",
    "STATE": "state",
    "ZIP_CODE": "zip_code",
    "ZIP_CODE_4": "zip_code_4",
    "COUNTY": "county",
    "AREA": "area",
    "NEIGHBORHOOD": "neighborhood",

    "LIST_PRICE": "list_price",
    "ORIG_PRICE": "orig_price",
    "PREV_LIST_PRICE": "prev_list_price",
    "SALE_PRICE": "sale_price",
    "PRICE_PER_SQFT": "price_per_sqft_raw",
    "LIST_PRICE_PER_SQFT": "list_price_per_sqft_raw",
    "SOLD_PRICE_PER_SQFT": "sold_price_per_sqft_raw",
    "SALE_TO_ASSESSED": "sale_to_assessed",
    "SaleToList": "sale_to_list_ratio",
    "TAXES": "taxes",
    "TAX_YEAR": "tax_year",

    "LIST_DATE": "list_date",
    "LIST_DATE_RCVD": "list_date_received",
    "OFF_MKT_DATE": "off_market_date",
    "SETTLED_DATE": "settled_date",
    "OFFER_DATE": "offer_date",
    "UPDATE_DATE": "update_date",
    "PHOTO_DATE": "photo_date",
    "MARKET_TIME": "market_time",
    "MARKET_TIME_BROKER": "market_time_broker",
    "MARKET_TIME_PROPERTY": "market_time_property",

    "NO_BEDROOMS": "bedrooms",
    "TOTAL_BATHS": "total_baths",
    "NO_FULL_BATHS": "full_baths",
    "NO_HALF_BATHS": "half_baths",
    "NO_ROOMS": "rooms",
    "SQUARE_FEET": "square_feet",
    "SQUARE_FEET_SOURCE": "square_feet_source",
    "LOT_SIZE": "lot_size",
    "ACRE": "acre",
    "YEAR_BUILT": "year_built",
    "YEAR_BUILT_SOURCE": "year_built_source",
    "YEAR_BUILT_DESCRP": "year_built_desc",

    "PARKING_SPACES_SF": "parking_spaces_sf",
    "PARKING_SPACES_CC": "parking_spaces_cc",
    "PARKING_SPACES_MF": "parking_spaces_mf",
    "GARAGE_SPACES_SF": "garage_spaces_sf",
    "GARAGE_SPACES_CC": "garage_spaces_cc",
    "GARAGE_SPACES_MF": "garage_spaces_mf",

    "STYLE_SF": "style_sf",
    "MF_TYPE_MF": "mf_type",
    "CC_TYPE_CC": "cc_type",
    "NO_UNITS_MF": "no_units_mf",

    "BEDRMS_1_MF": "unit1_beds",
    "BEDRMS_2_MF": "unit2_beds",
    "BEDRMS_3_MF": "unit3_beds",
    "BEDRMS_4_MF": "unit4_beds",
    "BEDRMS_5_MF": "unit5_beds",

    "F_BTHS_1_MF": "unit1_full_baths",
    "F_BTHS_2_MF": "unit2_full_baths",
    "F_BTHS_3_MF": "unit3_full_baths",
    "F_BTHS_4_MF": "unit4_full_baths",
    "F_BTHS_5_MF": "unit5_full_baths",

    "H_BTHS_1_MF": "unit1_half_baths",
    "H_BTHS_2_MF": "unit2_half_baths",
    "H_BTHS_3_MF": "unit3_half_baths",
    "H_BTHS_4_MF": "unit4_half_baths",
    "H_BTHS_5_MF": "unit5_half_baths",

    "RENT1_MF": "unit1_rent",
    "RENT2_MF": "unit2_rent",
    "RENT3_MF": "unit3_rent",
    "RENT4_MF": "unit4_rent",
    "RENT5_MF": "unit5_rent",
    "TOTAL_RENT_MF": "mf_total_rent_raw",
    "GOI_MF": "mf_goi_raw",
    "NOI_MF": "mf_noi_raw",

    "REMARKS": "remarks",
    "DISCLOSURES": "disclosures",
}


NUMERIC_COLUMNS_AFTER_RENAME = [
    "list_price",
    "orig_price",
    "prev_list_price",
    "sale_price",
    "price_per_sqft_raw",
    "list_price_per_sqft_raw",
    "sold_price_per_sqft_raw",
    "sale_to_assessed",
    "sale_to_list_ratio",
    "taxes",
    "tax_year",
    "market_time",
    "market_time_broker",
    "market_time_property",
    "bedrooms",
    "total_baths",
    "full_baths",
    "half_baths",
    "rooms",
    "square_feet",
    "lot_size",
    "acre",
    "year_built",
    "parking_spaces_sf",
    "parking_spaces_cc",
    "parking_spaces_mf",
    "garage_spaces_sf",
    "garage_spaces_cc",
    "garage_spaces_mf",
    "no_units_mf",
    "unit1_beds",
    "unit2_beds",
    "unit3_beds",
    "unit4_beds",
    "unit5_beds",
    "unit1_full_baths",
    "unit2_full_baths",
    "unit3_full_baths",
    "unit4_full_baths",
    "unit5_full_baths",
    "unit1_half_baths",
    "unit2_half_baths",
    "unit3_half_baths",
    "unit4_half_baths",
    "unit5_half_baths",
    "unit1_rent",
    "unit2_rent",
    "unit3_rent",
    "unit4_rent",
    "unit5_rent",
    "mf_total_rent_raw",
    "mf_goi_raw",
    "mf_noi_raw",
]


DATE_COLUMNS_AFTER_RENAME = [
    "status_date",
    "list_date",
    "list_date_received",
    "off_market_date",
    "settled_date",
    "offer_date",
    "update_date",
    "photo_date",
]


def safe_to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def safe_to_datetime(series: pd.Series) -> pd.Series:
    # More stable than letting pandas infer with noisy mixed types everywhere
    return pd.to_datetime(series, errors="coerce")


def normalize_property_type(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.upper().str.strip()

    return np.select(
        [
            s.str.contains("RN", na=False),
            s.str.contains("MF", na=False),
            s.str.contains("CC", na=False),
            s.str.contains("SF", na=False),
        ],
        [
            "RENTAL",
            "MF",
            "CONDO",
            "SF",
        ],
        default=s
    )


def load_and_clean(input_file: Path, output_file: Path) -> Path:
    print(f"Loading: {input_file}")
    df = pd.read_csv(input_file, low_memory=False)

    dataset_type = "unknown"
    name_lower = input_file.name.lower()
    if "rental" in name_lower:
        dataset_type = "rentals"
    elif "sold" in name_lower:
        dataset_type = "sold"
    elif "active" in name_lower:
        dataset_type = "active"

    # Keep only columns that exist in the file
    available_keep_cols = [col for col in KEEP_COLUMNS if col in df.columns]
    missing_cols = [col for col in KEEP_COLUMNS if col not in df.columns]

    if missing_cols:
        print(f"Missing columns skipped: {len(missing_cols)}")

    df = df[available_keep_cols].copy()

    # Rename columns
    rename_map = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    if "zip_code" in df.columns:
        zip_series = (
            df["zip_code"]
            .where(df["zip_code"].notna(), pd.NA)
            .astype("string")
            .str.strip()
            .str.replace(r"\.0+$", "", regex=True)
        )

        # Ensure short numeric ZIPs are normalized to 5 digits.
        df["zip_code"] = zip_series.where(
            ~zip_series.str.fullmatch(r"\d{1,4}", na=False),
            zip_series.str.zfill(5),
        )

    # Drop exact duplicate MLS IDs if present
    if "mls_id" in df.columns:
        df = df.drop_duplicates(subset=["mls_id"], keep="first")

    # Convert numerics
    for col in NUMERIC_COLUMNS_AFTER_RENAME:
        if col in df.columns:
            df[col] = safe_to_numeric(df[col])

    # Convert dates
    for col in DATE_COLUMNS_AFTER_RENAME:
        if col in df.columns:
            df[col] = safe_to_datetime(df[col])

    # Add dataset type
    df["dataset_type"] = dataset_type

    # Normalize property type
    if "property_type" in df.columns:
        df["property_type_clean"] = normalize_property_type(df["property_type"])

    # Define rent_price
    # For rentals, LIST_PRICE is the monthly asking/closed rent in MLS exports
    if "list_price" in df.columns:
        df["rent_price"] = np.where(
            df["dataset_type"] == "rentals",
            df["list_price"],
            np.nan
        )

    # Derived fields
    if "acre" in df.columns:
        df["lot_sqft_from_acre"] = df["acre"] * 43560

    # Multifamily totals
    mf_bed_cols = [c for c in [
        "unit1_beds", "unit2_beds", "unit3_beds", "unit4_beds", "unit5_beds"
    ] if c in df.columns]

    mf_full_bath_cols = [c for c in [
        "unit1_full_baths", "unit2_full_baths", "unit3_full_baths", "unit4_full_baths", "unit5_full_baths"
    ] if c in df.columns]

    mf_half_bath_cols = [c for c in [
        "unit1_half_baths", "unit2_half_baths", "unit3_half_baths", "unit4_half_baths", "unit5_half_baths"
    ] if c in df.columns]

    if mf_bed_cols:
        df["mf_total_bedrooms"] = df[mf_bed_cols].fillna(0).sum(axis=1)

    if mf_full_bath_cols or mf_half_bath_cols:
        full_sum = df[mf_full_bath_cols].fillna(0).sum(axis=1) if mf_full_bath_cols else 0
        half_sum = df[mf_half_bath_cols].fillna(0).sum(axis=1) if mf_half_bath_cols else 0
        df["mf_total_bathrooms"] = full_sum + (half_sum * 0.5)

    if "no_units_mf" in df.columns:
        df["mf_unit_count_calc"] = df["no_units_mf"]
    elif mf_bed_cols:
        df["mf_unit_count_calc"] = df[mf_bed_cols].notna().sum(axis=1)

    # Price per sqft calc
    if "sale_price" in df.columns and "square_feet" in df.columns:
        df["price_per_sqft_calc_sale"] = np.where(
            (df["square_feet"].fillna(0) > 0),
            df["sale_price"] / df["square_feet"],
            np.nan
        )

    if "list_price" in df.columns and "square_feet" in df.columns:
        df["price_per_sqft_calc_list"] = np.where(
            (df["square_feet"].fillna(0) > 0),
            df["list_price"] / df["square_feet"],
            np.nan
        )

    # Price per bedroom
    if "sale_price" in df.columns and "bedrooms" in df.columns:
        df["price_per_bedroom_sale"] = np.where(
            (df["bedrooms"].fillna(0) > 0),
            df["sale_price"] / df["bedrooms"],
            np.nan
        )

    if "list_price" in df.columns and "bedrooms" in df.columns:
        df["price_per_bedroom_list"] = np.where(
            (df["bedrooms"].fillna(0) > 0),
            df["list_price"] / df["bedrooms"],
            np.nan
        )

    # Days on market
    if "off_market_date" in df.columns and "list_date" in df.columns:
        df["days_on_market_calc"] = (df["off_market_date"] - df["list_date"]).dt.days

    # Sale year
    if "settled_date" in df.columns:
        df["sale_year"] = df["settled_date"].dt.year

    # Address convenience
    for col in ["address", "town", "state", "zip_code"]:
        if col not in df.columns:
            df[col] = np.nan

    df["full_address"] = (
        df["address"].fillna("").astype(str).str.strip() + ", " +
        df["town"].fillna("").astype(str).str.strip() + ", " +
        df["state"].fillna("").astype(str).str.strip() + " " +
        df["zip_code"].fillna("").astype(str).str.strip()
    ).str.strip(", ").str.strip()

    # Clean blank strings
    df = df.replace(r"^\s*$", np.nan, regex=True)

    # Rental-specific cleanup:
    # Keep studios (bedrooms = 0), but remove obvious junk like parking/storage if rent is too low
    if dataset_type == "rentals" and "rent_price" in df.columns:
        before_rows = len(df)
        df = df[df["rent_price"].fillna(0) >= 700].copy()
        removed = before_rows - len(df)
        print(f"Rental cleanup removed {removed:,} rows with rent_price < 700")

    print(f"Saving cleaned file: {output_file}")
    df.to_csv(output_file, index=False)
    print(f"Rows saved: {len(df):,}")
    return output_file


def run_cleaning_jobs(jobs: list[tuple[str, str]] | None = None) -> list[Path]:
    if jobs is None:
        jobs = [
            ("sold_master_latest.csv", "sold_clean_latest.csv"),
            ("rentals_master_latest.csv", "rentals_clean_latest.csv"),
            ("active_latest.csv", "active_clean_latest.csv"),
        ]

    output_files: list[Path] = []
    for input_name, output_name in jobs:
        input_file = COMBINED_DIR / input_name
        output_file = CLEANED_DIR / output_name

        if input_file.exists():
            output_files.append(load_and_clean(input_file, output_file))
        else:
            print(f"Skipped missing file: {input_file}")
    return output_files


def main():
    run_cleaning_jobs()


if __name__ == "__main__":
    main()