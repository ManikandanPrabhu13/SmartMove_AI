"""
risk.py

Risk Categorization Module.

Converts the Random Forest's raw risk_probability into the
dashboard-facing LOW / MEDIUM / HIGH category, and provides small
shared geometry helpers (heading difference, pairwise distance)
that are reused by both the AI risk pipeline and the overtaking
safety module.

NOTE: this module previously implemented ad-hoc pairwise vehicle
collision-risk math with a broken import. That logic has been
superseded by the ML-driven pipeline in ml_model.py /
decision_engine.py. The heading/distance helpers are kept here
(and re-exported) since other modules already depend on this file's
public API.
"""

from backend.app.config import RISK_LOW_MAX, RISK_MEDIUM_MAX
from backend.app.engine.geofence import haversine_distance


def heading_difference(h1, h2):
    """
    Smallest angular difference between two compass headings, in
    degrees, in range [0, 180].
    """

    diff = abs(h1 - h2)

    if diff > 180:
        diff = 360 - diff

    return diff


def categorize_risk(risk_probability):
    """
    Map a continuous risk_probability (0-1) from the ML model into
    a discrete LOW / MEDIUM / HIGH category using the configured
    thresholds.
    """

    if risk_probability <= RISK_LOW_MAX:
        return "LOW"
    elif risk_probability <= RISK_MEDIUM_MAX:
        return "MEDIUM"
    else:
        return "HIGH"


def pairwise_distance(vehicle1, vehicle2):
    """
    Straight-line distance (meters) between two vehicles. Reused by
    the overtaking safety module and available for any future
    vehicle-to-vehicle proximity logic.
    """

    return haversine_distance(
        vehicle1["latitude"],
        vehicle1["longitude"],
        vehicle2["latitude"],
        vehicle2["longitude"]
    )
