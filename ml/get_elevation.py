import pandas as pd
import requests
from pathlib import Path

INPUT_FILE = Path("data/landslides_ner.csv")
OUTPUT_FILE = Path("data/landslides_ner_features.csv")

BATCH_SIZE = 100


def main():
    df = pd.read_csv(INPUT_FILE)

    elevations = []

    for start in range(0, len(df), BATCH_SIZE):
        batch = df.iloc[start:start + BATCH_SIZE]

        latitudes = ",".join(batch["latitude"].astype(str))
        longitudes = ",".join(batch["longitude"].astype(str))

        url = "https://api.open-meteo.com/v1/elevation"

        response = requests.get(
            url,
            params={
                "latitude": latitudes,
                "longitude": longitudes,
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()
        elevations.extend(data["elevation"])

        print(
            f"Processed {min(start + BATCH_SIZE, len(df))}/{len(df)} locations"
        )

    df["elevation_m"] = elevations

    df.to_csv(OUTPUT_FILE, index=False)

    print()
    print(f"Saved: {OUTPUT_FILE}")
    print()
    print(df[["state", "latitude", "longitude", "elevation_m"]].head(10))


if __name__ == "__main__":
    main()