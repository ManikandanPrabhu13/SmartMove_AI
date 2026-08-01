"""
ml_model.py

Loads the trained Random Forest risk model + label encoders and
exposes a single predict() entry point used by decision_engine.py.

If the model artifacts don't exist yet (fresh clone, before
`python -m backend.app.ai.train_model` has been run), this module
trains them automatically on first import so the pipeline works
out of the box with zero manual steps.
"""

import os
import logging

import joblib
import pandas as pd

from backend.app.config import (
    MODEL_PATH,
    LABEL_ENCODER_PATH,
    HEAVY_VEHICLE_TYPES,
)

from backend.app.engine.feature_builder import FEATURE_COLUMNS

logger = logging.getLogger("smartmove.ml_model")


class RiskModel:

    def __init__(self):

        self._model = None
        self._encoders = None
        self._load_or_train()

    def _load_or_train(self):

        if not (os.path.exists(MODEL_PATH) and os.path.exists(LABEL_ENCODER_PATH)):

            logger.warning(
                "Risk model artifacts not found - training a fresh model "
                "from a generated synthetic dataset."
            )

            from backend.app.ai.train_model import train
            train()

        self._model = joblib.load(MODEL_PATH)
        self._encoders = joblib.load(LABEL_ENCODER_PATH)

        logger.info("Risk model and encoders loaded successfully.")

    def _encode_row(self, feature_row):
        """
        Encode a raw feature dict into the numeric row the model
        expects, safely handling categories unseen at training time
        by falling back to the most frequent known category.
        """

        encoded = dict(feature_row)

        for col in ("vehicle_type", "zone_type"):

            encoder = self._encoders[col]
            value = feature_row[col]

            if value not in encoder.classes_:
                # Unseen category (e.g. a new zone_type) - fall back
                # to the first known class rather than raising.
                value = encoder.classes_[0]

            encoded[col] = encoder.transform([value])[0]

        return encoded

    def predict(self, feature_row):
        """
        feature_row: dict produced by feature_builder.build_feature_row

        Returns:
            {
                "risk_probability": float (0-1),
                "risk_category": "LOW" | "MEDIUM" | "HIGH",
                "driver_score": float (0-100, higher = safer),
                "reason": str
            }
        """

        encoded = self._encode_row(feature_row)

        ordered = [encoded[col] for col in FEATURE_COLUMNS]

        X = pd.DataFrame([ordered], columns=FEATURE_COLUMNS)

        probabilities = self._model.predict_proba(X)[0]

        class_labels = self._encoders["risk_category"].classes_

        prob_by_label = dict(zip(class_labels, probabilities))

        predicted_index = max(
            range(len(probabilities)),
            key=lambda i: probabilities[i]
        )
        predicted_label = class_labels[predicted_index]

        # "Risk probability" = probability mass on MEDIUM + HIGH,
        # i.e. probability the situation is NOT low-risk.
        risk_probability = 1.0 - prob_by_label.get("LOW", 0.0)

        driver_score = round((1.0 - risk_probability) * 100, 1)

        reason = self._build_reason(feature_row, predicted_label)

        return {
            "risk_probability": round(float(risk_probability), 4),
            "risk_category": predicted_label,
            "driver_score": driver_score,
            "reason": reason,
        }

    def _build_reason(self, feature_row, predicted_label):
        """
        Explainable AI: build a human-readable reason string citing
        the actual drivers behind the prediction, so HIGH-risk
        alerts are never a black box.
        """

        reasons = []

        if feature_row["zone_type"] != "None":

            if feature_row["distance_to_polygon"] <= 0.0:
                reasons.append(f"Inside {feature_row['zone_type']} Zone")
            elif feature_row["distance_to_polygon"] < 100:
                reasons.append(f"Approaching {feature_row['zone_type']} Zone")

        if feature_row["vehicle_type"] in HEAVY_VEHICLE_TYPES:
            reasons.append("Heavy Vehicle")

        if feature_row["gps_confidence"] < 0.5:
            reasons.append("Low GPS Confidence")

        if feature_row["road_health"] < 50:
            reasons.append("Poor Road Health")

        if feature_row["speed"] > 80:
            reasons.append("Overspeed")

        if feature_row["hour_of_day"] < 5 or feature_row["hour_of_day"] > 21:
            reasons.append("Low Visibility Hours")

        if not reasons:
            reasons.append(
                "Normal driving conditions" if predicted_label == "LOW"
                else "Combined minor risk factors"
            )

        return ", ".join(reasons)


# Singleton instance - loaded once per process.
risk_model = RiskModel()


def predict_risk(feature_row):
    """
    Module-level convenience wrapper around the singleton model.
    """
    return risk_model.predict(feature_row)
