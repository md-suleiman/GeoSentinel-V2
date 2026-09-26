import pandas as pd
import requests
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor

INPUT_FILE = Path("data/landslides_ner_features.csv")
OUTPUT_FILE = Path("data/landslides_ner_weather.csv")

URL = "https://archive-api.open-meteo.com/v1/archive"


def get_weather(latitude, longitude, event_date):
    event_timestamp = pd.Timestamp(event_date)
    event_date_string = event_timestamp.strftime("%Y-%m-%d")
    start_date = (event_timestamp.normalize() - pd.Timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )

    for attempt in range(3):
        try:
            response = requests.get(
                URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "start_date": start_date,
                    "end_date": event_date_string,
                    "hourly": "precipitation,soil_moisture_0_to_7cm",
                    "timezone": "auto",
                },
                timeout=15,
            )
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1)

    data = response.json()

    hourly = data.get("hourly")

    if not hourly:
        return None, None

    hourly_times = pd.to_datetime(hourly.get("time", []), errors="coerce")
    precipitation_values = hourly.get("precipitation", [])
    soil_values = hourly.get("soil_moisture_0_to_7cm", [])

    event_hour = event_timestamp.floor("h")
    rainfall_values = [
        float(value)
        for timestamp, value in zip(hourly_times, precipitation_values)
        if (
            not pd.isna(timestamp)
            and event_hour - pd.Timedelta(hours=24) < timestamp <= event_hour
            and value is not None
        )
    ]
    rainfall = round(sum(rainfall_values), 1) if rainfall_values else None

    daily_soil_values = [
        float(value)
        for timestamp, value in zip(hourly_times, soil_values)
        if (
            not pd.isna(timestamp)
            and timestamp.date() == event_timestamp.date()
            and value is not None
        )
    ]
    soil_moisture = (
        round(sum(daily_soil_values) / len(daily_soil_values), 6)
        if daily_soil_values
        else None
    )

    return rainfall, soil_moisture


def main():
    df = pd.read_csv(INPUT_FILE)

    df["event_date"] = pd.to_datetime(
        df["event_date"],
        errors="coerce"
    )

    def fetch_row(row):
        date = row["event_date"]

        if pd.isna(date):
            return None, None

        try:
            return get_weather(
                row["latitude"],
                row["longitude"],
                date,
            )
        except Exception as error:
            print(f"Failed row: {error}")
            return None, None

    with ThreadPoolExecutor(max_workers=4) as executor:
        weather_values = list(
            executor.map(fetch_row, [row for _, row in df.iterrows()])
        )

    rainfall_values = [rainfall for rainfall, _ in weather_values]
    soil_values = [soil_moisture for _, soil_moisture in weather_values]

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