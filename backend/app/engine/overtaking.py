"""
overtaking.py

Heavy Vehicle Overtaking Safety Module.

Focused on Indian road conditions where heavy vehicles (trucks,
buses, lorries, containers, tankers) frequently attempt risky
overtaking maneuvers on narrow or undivided roads.

This module is intentionally decoupled from any single-vehicle
telemetry format: it operates on the shared pool of "live" vehicle
positions (as cached in Redis) so it can evolve into a full
Vehicle-to-Vehicle (V2V) communication module later without
changing its public interface - `evaluate_overtaking_risk` takes
a snapshot of nearby vehicles and returns alerts, it does not care
how those vehicles' data arrived (MQTT today, direct V2V broadcast
tomorrow).
"""

import math

from backend.app.config import (
    HEAVY_VEHICLE_TYPES,
    OVERTAKE_PROXIMITY_THRESHOLD_M,
    OVERTAKE_HEADING_TOLERANCE_DEG,
    OVERTAKE_CLOSING_SPEED_THRESHOLD_KMH
)

from backend.app.engine.geofence import haversine_distance


def _heading_diff(h1, h2):
    """
    Smallest angular difference between two compass headings,
    in degrees, in range [0, 180].
    """

    diff = abs(h1 - h2) % 360

    return diff if diff <= 180 else 360 - diff


def _relative_bearing(from_vehicle, to_vehicle):
    """
    Compass bearing (degrees) from from_vehicle's position to
    to_vehicle's position.
    """

    lat1 = math.radians(from_vehicle["latitude"])
    lat2 = math.radians(to_vehicle["latitude"])

    dlon = math.radians(to_vehicle["longitude"] - from_vehicle["longitude"])

    x = math.sin(dlon) * math.cos(lat2)

    y = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    )

    bearing = math.degrees(math.atan2(x, y))

    return (bearing + 360) % 360


def is_behind(rear_vehicle, front_vehicle):
    """
    True if rear_vehicle is positioned behind front_vehicle, i.e.
    the bearing from front_vehicle back to rear_vehicle roughly
    opposes front_vehicle's own heading of travel.
    """

    bearing_to_rear = _relative_bearing(front_vehicle, rear_vehicle)

    # "Behind" means the bearing to the rear vehicle is roughly
    # opposite to the direction the front vehicle is heading.
    opposite_heading = (front_vehicle["heading"] + 180) % 360

    return _heading_diff(bearing_to_rear, opposite_heading) < 60


def evaluate_overtaking_risk(subject_vehicle, nearby_vehicles):
    """
    Evaluate whether any nearby heavy vehicle is attempting, or
    about to attempt, an overtaking maneuver on subject_vehicle.

    subject_vehicle: dict with vehicle_id, vehicle_type, latitude,
                      longitude, heading, speed
    nearby_vehicles: list of the same dict shape, excluding
                      subject_vehicle itself

    Returns a list of alert dicts (empty list if no risk detected):
        {
            "alert_type": str,
            "target_vehicle_id": str,   (the vehicle the alert is FOR)
            "threat_vehicle_id": str,   (the heavy vehicle behind)
            "message": str,
            "recommendation": str,
            "priority": "HIGH" | "MEDIUM"
        }
    """

    alerts = []

    for other in nearby_vehicles:

        if other["vehicle_id"] == subject_vehicle["vehicle_id"]:
            continue

        if other.get("vehicle_type") not in HEAVY_VEHICLE_TYPES:
            continue

        distance = haversine_distance(
            subject_vehicle["latitude"],
            subject_vehicle["longitude"],
            other["latitude"],
            other["longitude"]
        )

        if distance > OVERTAKE_PROXIMITY_THRESHOLD_M:
            continue

        heading_alignment = _heading_diff(
            subject_vehicle["heading"], other["heading"]
        )

        if heading_alignment > OVERTAKE_HEADING_TOLERANCE_DEG:
            # Not travelling in the same direction / same lane of
            # traffic, so not a same-road overtaking scenario.
            continue

        if not is_behind(other, subject_vehicle):
            continue

        closing_speed = other["speed"] - subject_vehicle["speed"]

        # Heavy vehicle is directly behind, aligned in heading, and
        # within proximity threshold - always worth a baseline
        # "heavy vehicle behind" advisory.
        alerts.append({
            "alert_type": "Heavy Vehicle Behind",
            "target_vehicle_id": subject_vehicle["vehicle_id"],
            "threat_vehicle_id": other["vehicle_id"],
            "message": (
                f"{other.get('vehicle_type', 'Heavy vehicle')} "
                f"{other['vehicle_id']} detected {round(distance)}m behind."
            ),
            "recommendation": "Maintain Lane Discipline",
            "priority": "MEDIUM"
        })

        if closing_speed >= OVERTAKE_CLOSING_SPEED_THRESHOLD_KMH:

            alerts.append({
                "alert_type": "Unsafe Overtaking",
                "target_vehicle_id": subject_vehicle["vehicle_id"],
                "threat_vehicle_id": other["vehicle_id"],
                "message": (
                    f"{other['vehicle_id']} closing fast "
                    f"({round(closing_speed)} km/h faster) - "
                    f"likely overtaking maneuver."
                ),
                "recommendation": "Do Not Change Lane",
                "priority": "HIGH"
            })

            alerts.append({
                "alert_type": "Blind Spot Warning",
                "target_vehicle_id": subject_vehicle["vehicle_id"],
                "threat_vehicle_id": other["vehicle_id"],
                "message": (
                    f"{other['vehicle_id']} may be entering your blind spot."
                ),
                "recommendation": "Reduce Speed",
                "priority": "HIGH"
            })

    return alerts
