from pathlib import Path
import pandas as pd

project_dir = Path(__file__).parent
downloads_dir = project_dir / "downloads" / "rentals"
combined_dir = project_dir / "combined"

combined_dir.mkdir(exist_ok=True)

def combine_rental_exports() -> Path:
    csv_files = sorted(downloads_dir.glob("rentals_export_*.csv"))

    if not csv_files:
        raise FileNotFoundError("No rental CSV files found in downloads/rentals.")

    print(f"Found {len(csv_files)} rental CSV files")

    dataframes = []
    for file in csv_files:
        print(f"Loading {file.name}")
        df = pd.read_csv(file, low_memory=False)
        dataframes.append(df)

    print("Combining rental files...")
    combined_df = pd.concat(dataframes, ignore_index=True)

    print("Removing exact duplicate rows...")
    combined_df = combined_df.drop_duplicates()

    output_file = combined_dir / "rentals_master_latest.csv"
    print(f"Saving combined rental file to {output_file}")
    combined_df.to_csv(output_file, index=False)
    print(f"Done. Rows saved: {len(combined_df):,}")
    return output_file


def main():
    combine_rental_exports()


if __name__ == "__main__":
    main()
