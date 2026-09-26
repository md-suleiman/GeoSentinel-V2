import pandas as pd
import requests
import numpy as np
import time
import math

INPUT = "data/landslides_ner_features.csv"
OUTPUT = "data/landslides_ner_slope.csv"

df = pd.read_csv(INPUT)

def get_elevations(coordinates):
    for attempt in range(5):
        try:
            response = requests.get(
                "https://api.open-meteo.com/v1/elevation",
                params={
                    "latitude": ",".join(str(point[0]) for point in coordinates),
                    "longitude": ",".join(str(point[1]) for point in coordinates),
                },
                timeout=15,
            )
            response.raise_for_status()
            return response.json()["elevation"]
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(2 * (attempt + 1))


def get_coordinates(lat, lon):
    offsets = [
        (0.0, 0.0),
        (0.01, 0.0),
        (-0.01, 0.0),
        (0.0, 0.01),
        (0.0, -0.01),
    ]
    return [(lat + dlat, lon + dlon) for dlat, dlon in offsets]


def calculate_slope(elevations, latitude):
    if len(elevations) != 5:
        raise ValueError("Expected center and four neighboring elevations")

    north, south = float(elevations[1]), float(elevations[2])
    east, west = float(elevations[3]), float(elevations[4])
    north_south_distance = 0.02 * 111000
    east_west_distance = max(
        0.02 * 111000 * math.cos(math.radians(latitude)),
        1.0,
    )
    north_south_gradient = abs(north - south) / north_south_distance
    east_west_gradient = abs(east - west) / east_west_distance
    slope_percent = math.sqrt(
        north_south_gradient ** 2 + east_west_gradient ** 2
    ) * 100
    return round(min(slope_percent, 60), 2)

slopes = []
BATCH_SIZE = 5

for start in range(0, len(df), BATCH_SIZE):
    batch = df.iloc[start:start + BATCH_SIZE]
    all_coordinates = []
    for _, row in batch.iterrows():
        all_coordinates.extend(get_coordinates(row["latitude"], row["longitude"]))

    try:
        elevations = get_elevations(all_coordinates)

        if len(elevations) != len(all_coordinates):
            raise ValueError("Elevation response length did not match request")

        for offset, (_, row) in enumerate(batch.iterrows()):
            elev = elevations[offset * 5:(offset + 1) * 5]
            slopes.append(calculate_slope(elev, row["latitude"]))

            print(
                f"{start + offset + 1}/{len(df)}  "
                f"slope={slopes[-1]:.2f}%"
            )

    except Exception as e:
        print("Error:", e)
        for _, row in batch.iterrows():
            try:
                elevations = get_elevations(
                    get_coordinates(row["latitude"], row["longitude"])
                )
                slope_percent = calculate_slope(elevations, row["latitude"])
                slopes.append(slope_percent)
            except Exception as row_error:
                print("Row error:", row_error)
                slopes.append(np.nan)

    time.sleep(0.1)

df["slope_percent"] = slopes
df.to_csv(OUTPUT, index=False)

print("\nSaved:", OUTPUT)
print("Valid slopes:", df["slope_percent"].notna().sum())