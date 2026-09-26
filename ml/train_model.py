import pandas as pd
import numpy as np
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
import joblib
import os

df = pd.read_csv("data/training_data.csv")

features = [
    "rainfall_mm",
    "soil_moisture",
    "elevation_m",
    "slope_percent"
]

X = df[features]
y = df["landslide"]

print("Total samples:", len(df))
print("Positive samples:", int((y == 1).sum()))
print("Negative samples:", int((y == 0).sum()))
print("Features:", features)

# Hold out spatial cells so nearby synthetic/background points do not appear
# in both sets. This gives a more realistic estimate for unseen locations.
spatial_groups = (
    np.floor(df["latitude"] / 0.1).astype(int).astype(str)
    + "_"
    + np.floor(df["longitude"] / 0.1).astype(int).astype(str)
)

splitter = StratifiedGroupKFold(
    n_splits=5,
    shuffle=True,
    random_state=42
)
train_indices, test_indices = next(
    splitter.split(X, y, groups=spatial_groups)
)

X_train = X.iloc[train_indices]
X_test = X.iloc[test_indices]
y_train = y.iloc[train_indices]
y_test = y.iloc[test_indices]

print("Train samples:", len(X_train))
print("Test samples:", len(X_test))

model = RandomForestClassifier(
    n_estimators=200,
    max_depth=8,
    random_state=42,
    class_weight="balanced"
)

model.fit(X_train, y_train)

predictions = model.predict(X_test)
probabilities = model.predict_proba(X_test)[:, 1]

print("\nClassification Report:")
print(classification_report(y_test, predictions))

print("Confusion Matrix:")
print(confusion_matrix(y_test, predictions))

print("\nROC-AUC:", round(roc_auc_score(y_test, probabilities), 3))
print("PR-AUC:", round(average_precision_score(y_test, probabilities), 3))

print("\nFeature Importance:")
for feature, importance in zip(features, model.feature_importances_):
    print(f"{feature}: {importance:.3f}")

os.makedirs("ml/models", exist_ok=True)

joblib.dump(
    model,
    "ml/models/landslide_model.joblib"
)

print("\nModel saved successfully.")