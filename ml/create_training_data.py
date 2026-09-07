import pandas as pd
import numpy as np

np.random.seed(42)

df = pd.read_csv("data/landslides_ner_final.csv")

df = df.dropna(subset=[
    "latitude",
    "longitude",
    "rainfall_mm",
    "elevation_m",
    "slope_percent"
])

# Remove duplicate locations
df = df.drop_duplicates(subset=["latitude", "longitude"])

# Positive samples = actual historical landslides
positive = df[[
    "latitude",
    "longitude",
    "rainfall_mm",
    "elevation_m",
    "slope_percent"
]].copy()

positive["landslide"] = 1

# Create background samples
n_negative = len(positive) * 2

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
    "rainfall_mm": np.random.choice(
        positive.rainfall_mm,
        n_negative
    ),
    "elevation_m": np.random.choice(
        positive.elevation_m,
        n_negative
    ),
    "slope_percent": np.random.choice(
        positive.slope_percent,
        n_negative
    )
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
    "elevation_m",
    "slope_percent"
]].describe())