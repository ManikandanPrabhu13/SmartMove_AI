"""
decision_engine.py

Master Orchestrator.

Called once per incoming MQTT telemetry message (event-driven,
not a polling loop) from mqtt/handlers.py. Runs the complete
pipeline for a single vehicle:

    Polygon Geofencing
        -> GPS Recovery Engine
        -> Road Health Engine
        -> Feature Builder
        -> AI Risk Prediction (Random Forest)
        -> Driver Risk Score
        -> Overtaking / V2V Safety Check
        -> Alerts

Returns a single structured result dict that mqtt/handlers.py
persists (Redis + DB) and broadcasts over WebSocket to the
dashboard.
"""

import logging

from backend.app.redis_client import (
    save_risk_result,
    get_zone_cache,
    get_all_vehicles,
)

from backend.app.api.hazards import get_hazard_cache

from backend.app.engine.geofence import find_active_zone
from backend.app.engine.gps_monitor import process_gps
from backend.app.engine.road_health import compute_road_health
from backend.app.engine.feature_builder import build_feature_row
from backend.app.engine.ml_model import predict_risk
from backend.app.engine.risk import categorize_risk
from backend.app.engine.overtaking import evaluate_overtaking_risk
from backend.app.engine.alerts import evaluate_alerts

from backend.app.db.models import RiskLog
from backend.app.db.session import SessionLocal

logger = logging.getLogger("smartmove.decision_engine")


def _persist_risk_log(vehicle_data, gps_result, zone_result,
                       road_health_result, ml_result):
    """
    Persist one AI pipeline result to Postgres for audit / history.
    Failures are logged, never raised - the real-time pipeline must
    keep running even if the DB is unavailable.
    """

    db = SessionLocal()

    try:
        record = RiskLog(
            vehicle_id=vehicle_data["vehicle_id"],
            vehicle_type=vehicle_data.get("vehicle_type", "Car"),
            zone_type=zone_result.get("zone_type"),
            gps_lost=gps_result.get("gps_lost", False),
            gps_confidence=gps_result.get("confidence", 1.0),
            road_health_score=road_health_result.get("score", 100.0),
            distance_to_polygon=(
                0.0 if zone_result.get("inside")
                else zone_result.get("distance_to_nearest_zone")
            ),
            risk_probability=ml_result["risk_probability"],
            driver_score=ml_result["driver_score"],
            risk_category=ml_result["risk_category"],
            reason=ml_result.get("reason"),
        )

        db.add(record)
        db.commit()

    except Exception as exc:
        logger.error("Failed to persist risk log: %s", exc)
        db.rollback()

    finally:
        db.close()


def run(vehicle_data):
    """
    Execute the full decision pipeline for a single vehicle
    telemetry event.

    vehicle_data: dict as published by the simulator, containing at
    minimum vehicle_id, vehicle_type, latitude, longitude, speed,
    heading, and optionally gps_status.

    Returns a fully assembled result dict ready for broadcast:
        {
            "vehicle_id": str,
            "vehicle_type": str,
            "latitude": float,
            "longitude": float,
            "heading": float,
            "speed": float,
            "gps": {...},
            "zone": {...},
            "road_health": {...},
            "ai": {...},
            "alerts": [...],
        }
    """

    vehicle_id = vehicle_data["vehicle_id"]

    # 1. GPS Recovery Engine (dead reckoning + road snap + confidence)
    gps_result = process_gps(vehicle_data)

    # Use the (possibly recovered/snapped) position for every
    # downstream step, so a GPS-lost vehicle still gets accurate
    # zone/hazard/risk evaluation based on its best-estimate position.
    positioned_vehicle = dict(vehicle_data)
    positioned_vehicle["latitude"] = gps_result["latitude"]
    positioned_vehicle["longitude"] = gps_result["longitude"]

    # 2. Polygon Geofencing
    zones = get_zone_cache() or []
    zone_result = find_active_zone(positioned_vehicle, zones)

    # 3. Road Health Engine
    hazards = get_hazard_cache()
    road_health_result = compute_road_health(positioned_vehicle, hazards)

    # 4. Feature Builder
    feature_row = build_feature_row(
        vehicle_data, gps_result, zone_result, road_health_result
    )

    # 5. AI Risk Prediction (Random Forest) + Driver Score
    ml_result = predict_risk(feature_row)

    # Cross-check the model's own category against the configured
    # thresholds for consistency (defensive - the model already
    # returns a category, but this guards against threshold drift
    # between config.py and the trained encoders).
    ml_result["risk_category"] = categorize_risk(ml_result["risk_probability"])

    # 6. Overtaking / V2V Safety Check
    other_vehicles = [
        v for v in get_all_vehicles()
        if v.get("vehicle_id") != vehicle_id
    ]

    overtaking_alerts = evaluate_overtaking_risk(
        positioned_vehicle, other_vehicles
    )

    # 7. Alerts
    raised_alerts = evaluate_alerts(
        vehicle_data,
        gps_result,
        zone_result,
        road_health_result,
        ml_result,
        overtaking_alerts,
    )

    # Persist AI result for history/audit (best-effort).
    _persist_risk_log(
        vehicle_data, gps_result, zone_result, road_health_result, ml_result
    )

    result = {
        "vehicle_id": vehicle_id,
        "vehicle_type": vehicle_data.get("vehicle_type", "Car"),
        "latitude": positioned_vehicle["latitude"],
        "longitude": positioned_vehicle["longitude"],
        "heading": vehicle_data.get("heading", 0.0),
        "speed": vehicle_data.get("speed", 0.0),
        "gps": gps_result,
        "zone": {
            "zone_type": zone_result.get("zone_type"),
            "inside": zone_result.get("inside"),
            "distance_to_nearest_zone": zone_result.get(
                "distance_to_nearest_zone"
            ),
        },
        "road_health": road_health_result,
        "ai": ml_result,
        "alerts": raised_alerts,
    }

    save_risk_result(vehicle_id, result)

    return result
