import pandas as pd
import requests
import numpy as np
import time

INPUT = "data/landslides_ner_features.csv"
OUTPUT = "data/landslides_ner_slope.csv"

df = pd.read_csv(INPUT)

def get_elevation(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": f"{lat},{lat+0.01},{lat-0.01}",
        "longitude": f"{lon},{lon+0.01},{lon-0.01}",
        "current": "temperature_2m"
    }

    r = requests.get(
        "https://api.open-meteo.com/v1/elevation",
        params={
            "latitude": f"{lat},{lat+0.01},{lat-0.01}",
            "longitude": f"{lon},{lon+0.01},{lon-0.01}"
        },
        timeout=30
    )
    r.raise_for_status()
    return r.json()["elevation"]

slopes = []

for i, row in df.iterrows():
    try:
        elev = get_elevation(row["latitude"], row["longitude"])

        # Approximate terrain gradient over ~1 km
        center = elev[0]
        north = elev[1]
        south = elev[2]

        distance_m = 1110

        slope_percent = abs(north - south) / (2 * distance_m) * 100
        slopes.append(slope_percent)

        print(f"{i+1}/{len(df)}  slope={slope_percent:.2f}%")

        time.sleep(0.1)

    except Exception as e:
        print("Error:", e)
        slopes.append(np.nan)

df["slope_percent"] = slopes
df.to_csv(OUTPUT, index=False)

print("\nSaved:", OUTPUT)
print("Valid slopes:", df["slope_percent"].notna().sum())