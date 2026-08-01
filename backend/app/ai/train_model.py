"""
train_model.py

Generates a synthetic, rule-informed labeled dataset (dataset.csv)
from the same feature space produced by feature_builder.py, then
trains a RandomForestClassifier to predict risk category
(LOW / MEDIUM / HIGH) from those features.

Run directly to (re)generate both dataset.csv and the trained
model artifacts:

    python -m backend.app.ai.train_model

Outputs:
    backend/app/ai/dataset.csv
    backend/app/ai/risk_model.pkl
    backend/app/ai/label_encoder.pkl   (dict of per-column encoders)
"""

import os
import random

import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

from backend.app.config import (
    VEHICLE_TYPES,
    ZONE_TYPES,
    MODEL_PATH,
    LABEL_ENCODER_PATH,
    DATASET_PATH,
    HEAVY_VEHICLE_TYPES,
)

from backend.app.engine.feature_builder import FEATURE_COLUMNS


RANDOM_SEED = 42


def _synthetic_label(row):
    """
    Rule-informed labeling function used purely to generate a
    coherent training dataset (not used at inference time - the
    trained Random Forest takes over from here). Combines the same
    risk drivers a domain expert would flag.
    """

    risk_score = 0.0

    # High-risk zones
    if row["zone_type"] in ("School", "Hairpin", "Hospital", "Accident"):
        risk_score += 0.30
    elif row["zone_type"] in ("Construction", "Flood", "RoadBlock"):
        risk_score += 0.20

    # Being physically inside a zone matters more than being near one
    if row["distance_to_polygon"] <= 0.0:
        risk_score += 0.15
    elif row["distance_to_polygon"] < 50:
        risk_score += 0.08

    # GPS confidence
    risk_score += (1.0 - row["gps_confidence"]) * 0.25

    # Road health (inverted: low health = high risk)
    risk_score += ((100.0 - row["road_health"]) / 100.0) * 0.20

    # Speed risk (nonlinear - excessive speed matters most)
    if row["speed"] > 80:
        risk_score += 0.20
    elif row["speed"] > 60:
        risk_score += 0.10

    # Heavy vehicles carry inherently higher maneuvering risk
    if row["vehicle_type"] in HEAVY_VEHICLE_TYPES:
        risk_score += 0.10

    # Night-time (low visibility hours) adds risk
    if row["hour_of_day"] < 5 or row["hour_of_day"] > 21:
        risk_score += 0.08

    risk_score += random.uniform(-0.05, 0.05)  # natural noise

    risk_score = max(0.0, min(1.0, risk_score))

    if risk_score <= 0.34:
        return "LOW"
    elif risk_score <= 0.69:
        return "MEDIUM"
    else:
        return "HIGH"


def generate_dataset(n_samples=6000):
    """
    Generate a synthetic dataset spanning the realistic feature
    space seen from the simulator + engine pipeline.
    """

    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)

    rows = []

    zone_options = ZONE_TYPES + ["None"] * len(ZONE_TYPES)  # bias toward "None"

    for _ in range(n_samples):

        vehicle_type = random.choice(VEHICLE_TYPES)
        speed = round(np.random.uniform(0, 110), 1)
        heading = round(np.random.uniform(0, 359), 1)
        zone_type = random.choice(zone_options)

        gps_confidence = round(np.random.beta(5, 1.2), 3)  # skewed high
        road_health = round(np.random.uniform(10, 100), 1)

        if zone_type == "None":
            distance_to_polygon = round(np.random.uniform(100, 3000), 1)
        else:
            distance_to_polygon = round(
                random.choice([0.0, 0.0, np.random.uniform(1, 200)]), 1
            )

        hour_of_day = random.randint(0, 23)

        row = {
            "vehicle_type": vehicle_type,
            "speed": speed,
            "heading": heading,
            "zone_type": zone_type,
            "gps_confidence": gps_confidence,
            "road_health": road_health,
            "distance_to_polygon": distance_to_polygon,
            "hour_of_day": hour_of_day,
        }

        row["risk_category"] = _synthetic_label(row)

        rows.append(row)

    return pd.DataFrame(rows, columns=FEATURE_COLUMNS + ["risk_category"])


def train():

    os.makedirs(os.path.dirname(DATASET_PATH), exist_ok=True)

    df = generate_dataset()
    df.to_csv(DATASET_PATH, index=False)

    print(f"Dataset written to {DATASET_PATH} ({len(df)} rows)")

    encoders = {}

    encoded_df = df.copy()

    for col in ["vehicle_type", "zone_type"]:
        encoder = LabelEncoder()
        encoded_df[col] = encoder.fit_transform(df[col])
        encoders[col] = encoder

    label_encoder = LabelEncoder()
    encoded_df["risk_category"] = label_encoder.fit_transform(
        df["risk_category"]
    )
    encoders["risk_category"] = label_encoder

    X = encoded_df[FEATURE_COLUMNS]
    y = encoded_df["risk_category"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_SEED, stratify=y
    )

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=3,
        random_state=RANDOM_SEED,
        class_weight="balanced",
    )

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    print(classification_report(
        y_test, predictions, target_names=label_encoder.classes_
    ))

    joblib.dump(model, MODEL_PATH)
    joblib.dump(encoders, LABEL_ENCODER_PATH)

    print(f"Model written to {MODEL_PATH}")
    print(f"Encoders written to {LABEL_ENCODER_PATH}")


if __name__ == "__main__":
    train()
