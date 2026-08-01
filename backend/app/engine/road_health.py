"""
road_health.py

Road Health Index Engine.

Combines nearby road hazards (potholes, construction, flood,
road blocks, accidents, speed breakers, oil spills, fallen trees,
general road damage) plus traffic conditions into a single 0-100
Road Health Index for a vehicle's current position.

100 = perfect road condition.
0   = completely unsafe / impassable road condition.
"""

import math

from backend.app.config import (
    HAZARD_INFLUENCE_RADIUS,
    HAZARD_SEVERITY_PENALTY,
    ROAD_HEALTH_WEIGHTS
)

from backend.app.engine.geofence import haversine_distance


def _traffic_penalty(traffic_level):
    """
    traffic_level: 0.0 (free flowing) - 1.0 (gridlock)
    """

    return traffic_level * 100 * ROAD_HEALTH_WEIGHTS["traffic"]


def _hazard_penalty(vehicle, hazards):
    """
    Sum the severity penalty of every hazard within influence
    radius of the vehicle, weighted by inverse distance so closer
    hazards hurt the score more than distant ones.
    """

    total_penalty = 0.0

    for hazard in hazards:

        distance = haversine_distance(
            vehicle["latitude"],
            vehicle["longitude"],
            hazard["latitude"],
            hazard["longitude"]
        )

        if distance > HAZARD_INFLUENCE_RADIUS:
            continue

        base_penalty = HAZARD_SEVERITY_PENALTY.get(
            hazard.get("hazard_type"), 10
        )

        # Linear falloff: full penalty at distance 0, zero penalty
        # at the edge of the influence radius.
        proximity_factor = 1.0 - (distance / HAZARD_INFLUENCE_RADIUS)

        total_penalty += base_penalty * proximity_factor

    return total_penalty


def compute_road_health(vehicle, hazards, traffic_level=0.0):
    """
    Compute the 0-100 Road Health Index for a vehicle's current
    position.

    vehicle: dict with "latitude", "longitude"
    hazards: list of dicts, each with "hazard_type", "latitude",
             "longitude", and optionally "severity"
    traffic_level: float 0.0-1.0 describing current congestion

    Returns:
        {
            "score": float (0-100),
            "nearest_hazard": dict or None,
            "nearest_hazard_distance": float or None
        }
    """

    score = 100.0

    score -= _traffic_penalty(traffic_level)
    score -= _hazard_penalty(vehicle, hazards)

    score = max(0.0, min(100.0, round(score, 2)))

    nearest_hazard = None
    nearest_distance = float("inf")

    for hazard in hazards:

        distance = haversine_distance(
            vehicle["latitude"],
            vehicle["longitude"],
            hazard["latitude"],
            hazard["longitude"]
        )

        if distance < nearest_distance:
            nearest_distance = distance
            nearest_hazard = hazard

    return {
        "score": score,
        "nearest_hazard": nearest_hazard,
        "nearest_hazard_distance": (
            round(nearest_distance, 2)
            if nearest_hazard is not None else None
        )
    }
