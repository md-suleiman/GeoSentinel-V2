import pandas as pd
from pathlib import Path

DATA_DIR = Path("data")
INPUT_FILE = DATA_DIR / "Global_Landslide_Catalog_Export_rows.csv"
OUTPUT_FILE = DATA_DIR / "landslides_ner.csv"


NER_STATES = {
    "Assam": "Assam",
    "Nāgāland": "Nagaland",
    "Nagaland": "Nagaland",
    "Manipur": "Manipur",
    "Sikkim": "Sikkim",
    "Mizoram": "Mizoram",
    "Arunāchal Pradesh": "Arunachal Pradesh",
    "Arunachal Pradesh": "Arunachal Pradesh",
    "Meghalaya": "Meghalaya",
    "Meghālaya": "Meghalaya",
    "Tripura": "Tripura",
}


def main():
    df = pd.read_csv(INPUT_FILE)

    # Keep only records whose administrative division
    # corresponds to one of the eight Northeast states.
    ner = df[df["admin_division_name"].isin(NER_STATES)].copy()

    # Normalize state names.
    ner["state"] = ner["admin_division_name"].map(NER_STATES)

    # Keep useful fields for our project.
    ner = ner[
        [
            "event_id",
            "event_date",
            "landslide_category",
            "landslide_trigger",
            "landslide_size",
            "landslide_setting",
            "latitude",
            "longitude",
            "fatality_count",
            "state",
        ]
    ]

    # Remove records without coordinates.
    ner = ner.dropna(subset=["latitude", "longitude"])

    ner.to_csv(OUTPUT_FILE, index=False)

    print(f"NER landslide records: {len(ner)}")
    print()
    print("Records by state:")
    print(ner["state"].value_counts().to_string())
    print()
    print(f"Saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()