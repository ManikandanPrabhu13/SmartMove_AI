"""
feature_builder.py

Builds the ML feature vector consumed by ml_model.py from the raw
outputs of every upstream engine (geofence, gps_monitor,
road_health).

Feature schema (order matters - must match ai/train_model.py):

    vehicle_type        (categorical, label-encoded)
    speed               (float, km/h)
    heading             (float, degrees)
    zone_type           (categorical, label-encoded; "None" if none)
    gps_confidence      (float, 0-1)
    road_health         (float, 0-100)
    distance_to_polygon (float, meters; 0 if inside a zone)
    hour_of_day         (int, 0-23)
"""

from datetime import datetime


FEATURE_COLUMNS = [
    "vehicle_type",
    "speed",
    "heading",
    "zone_type",
    "gps_confidence",
    "road_health",
    "distance_to_polygon",
    "hour_of_day",
]


def build_feature_row(vehicle_data, gps_result, zone_result, road_health_result):
    """
    Assemble a single feature row (dict) from every upstream
    engine's output for one vehicle at one point in time.
    """

    distance_to_polygon = zone_result.get("distance_to_nearest_zone")

    if zone_result.get("inside"):
        distance_to_polygon = 0.0

    if distance_to_polygon is None:
        # No zones configured / nothing nearby at all.
        distance_to_polygon = 9999.0

    return {
        "vehicle_type": vehicle_data.get("vehicle_type", "Car"),
        "speed": float(vehicle_data.get("speed", 0.0)),
        "heading": float(vehicle_data.get("heading", 0.0)),
        "zone_type": zone_result.get("zone_type") or "None",
        "gps_confidence": float(gps_result.get("confidence", 1.0)),
        "road_health": float(road_health_result.get("score", 100.0)),
        "distance_to_polygon": float(distance_to_polygon),
        "hour_of_day": datetime.utcnow().hour,
    }


def feature_row_to_ordered_list(row):
    """
    Return feature values in FEATURE_COLUMNS order, suitable for
    encoding + model input.
    """

    return [row[col] for col in FEATURE_COLUMNS]
