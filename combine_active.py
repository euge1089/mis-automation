from pathlib import Path
import pandas as pd


PROJECT_DIR = Path(__file__).parent
DOWNLOADS_DIR = PROJECT_DIR / "downloads" / "active"
COMBINED_DIR = PROJECT_DIR / "combined"

COMBINED_DIR.mkdir(exist_ok=True)


def combine_active_exports() -> Path:
    csv_files = sorted(DOWNLOADS_DIR.glob("active_export_*.csv"))
    if not csv_files:
        raise FileNotFoundError("No active CSV files found in downloads/active.")

    print(f"Found {len(csv_files)} active CSV files")

    dataframes = []
    for file in csv_files:
        print(f"Loading {file.name}")
        dataframes.append(pd.read_csv(file, low_memory=False))

    print("Combining active files...")
    combined_df = pd.concat(dataframes, ignore_index=True).drop_duplicates()

    output_file = COMBINED_DIR / "active_latest.csv"
    print(f"Saving combined active file to {output_file}")
    combined_df.to_csv(output_file, index=False)
    print(f"Done. Rows saved: {len(combined_df):,}")
    return output_file


def main():
    combine_active_exports()


if __name__ == "__main__":
    main()
