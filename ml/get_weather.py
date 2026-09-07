import pandas as pd
import requests
from pathlib import Path
import time

INPUT_FILE = Path("data/landslides_ner_features.csv")
OUTPUT_FILE = Path("data/landslides_ner_weather.csv")

URL = "https://archive-api.open-meteo.com/v1/archive"


def get_weather(latitude, longitude, date):
    response = requests.get(
        URL,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "start_date": date,
            "end_date": date,
            "daily": "precipitation_sum,soil_moisture_0_to_10cm_mean",
            "timezone": "UTC",
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    daily = data.get("daily")

    if not daily:
        return None, None

    rainfall = daily["precipitation_sum"][0]
    soil_moisture = daily["soil_moisture_0_to_10cm_mean"][0]

    return rainfall, soil_moisture


def main():
    df = pd.read_csv(INPUT_FILE)

    df["event_date"] = pd.to_datetime(
        df["event_date"],
        errors="coerce"
    )

    rainfall_values = []
    soil_values = []

    for index, row in df.iterrows():

        date = row["event_date"]

        if pd.isna(date):
            rainfall_values.append(None)
            soil_values.append(None)
            continue

        date_string = date.strftime("%Y-%m-%d")

        try:
            rainfall, soil_moisture = get_weather(
                row["latitude"],
                row["longitude"],
                date_string,
            )

            rainfall_values.append(rainfall)
            soil_values.append(soil_moisture)

        except Exception as error:
            print(f"Failed row {index}: {error}")
            rainfall_values.append(None)
            soil_values.append(None)

        print(f"Processed {index + 1}/{len(df)}")

        time.sleep(0.2)

    df["rainfall_mm"] = rainfall_values
    df["soil_moisture"] = soil_values

    df.to_csv(OUTPUT_FILE, index=False)

    print()
    print(f"Saved: {OUTPUT_FILE}")
    print()
    print(
        df[
            [
                "state",
                "event_date",
                "rainfall_mm",
                "soil_moisture",
            ]
        ].head(10).to_string(index=False)
    )


if __name__ == "__main__":
    main()