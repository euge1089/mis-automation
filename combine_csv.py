from pathlib import Path
import pandas as pd

project_dir = Path(__file__).parent
downloads_dir = project_dir / "downloads"
combined_dir = project_dir / "combined"

combined_dir.mkdir(exist_ok=True)

def combine_sold_exports() -> Path:
    csv_files = sorted(downloads_dir.glob("mls_export_*.csv"))

    if not csv_files:
        raise FileNotFoundError("No sold CSV files found in downloads.")

    print(f"Found {len(csv_files)} sold CSV files")

    dataframes = []
    for file in csv_files:
        print(f"Loading {file.name}")
        df = pd.read_csv(file, low_memory=False)
        dataframes.append(df)

    print("Combining sold files...")
    combined_df = pd.concat(dataframes, ignore_index=True)

    print("Removing exact duplicate rows...")
    combined_df = combined_df.drop_duplicates()

    output_file = combined_dir / "sold_master_latest.csv"
    print(f"Saving combined file to {output_file}")
    combined_df.to_csv(output_file, index=False)
    print(f"Done. Rows saved: {len(combined_df):,}")
    return output_file


def main():
    combine_sold_exports()


if __name__ == "__main__":
    main()
