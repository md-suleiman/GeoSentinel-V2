import pandas as pd
import numpy as np

np.random.seed(42)

df = pd.read_csv("data/landslides_ner_final.csv")
weather = pd.read_csv("data/landslides_ner_weather.csv")
slope = pd.read_csv("data/landslides_ner_slope.csv")

df = df.drop(columns=["soil_moisture", "slope_percent"], errors="ignore")
df = df.merge(
    weather[["event_id", "soil_moisture"]],
    on="event_id",
    how="left"
)
df = df.merge(
    slope[["event_id", "slope_percent"]],
    on="event_id",
    how="left"
)

# Keep one record per event before removing repeated physical locations.
df = df.drop_duplicates(subset=["event_id"])

df = df.dropna(subset=[
    "latitude",
    "longitude",
    "rainfall_mm",
    "soil_moisture",
    "elevation_m",
    "slope_percent"
])

print("Positive samples after filtering:", len(df))

# Avoid counting repeated event locations as independent positives.
df = df.drop_duplicates(subset=["latitude", "longitude"])

# Positive samples = actual historical landslides
positive = df[[
    "latitude",
    "longitude",
    "rainfall_mm",
    "soil_moisture",
    "elevation_m",
    "slope_percent"
]].copy()

positive["landslide"] = 1

# Create background samples. Sample complete environmental rows so the
# synthetic negatives retain the observed relationships between features.
n_negative = len(positive) * 2
sampled_features = positive.sample(
    n=n_negative,
    replace=True,
    random_state=42
).reset_index(drop=True)

negative = pd.DataFrame({
    "latitude": np.random.uniform(
        positive.latitude.min(),
        positive.latitude.max(),
        n_negative
    ),
    "longitude": np.random.uniform(
        positive.longitude.min(),
        positive.longitude.max(),
        n_negative
    ),
    "rainfall_mm": sampled_features["rainfall_mm"],
    "soil_moisture": sampled_features["soil_moisture"],
    "elevation_m": sampled_features["elevation_m"],
    "slope_percent": sampled_features["slope_percent"]
})

negative["landslide"] = 0

training = pd.concat(
    [positive, negative],
    ignore_index=True
)

training = training.sample(
    frac=1,
    random_state=42
).reset_index(drop=True)

training.to_csv(
    "data/training_data.csv",
    index=False
)

print("Training samples:", len(training))
print(training["landslide"].value_counts())
print("\nFeatures:")
print(training[[
    "rainfall_mm",
    "soil_moisture",
    "elevation_m",
    "slope_percent"
]].describe())