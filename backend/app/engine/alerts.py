"""
alerts.py

Central Alert Engine / Dispatcher.

Every module that can raise a dashboard-facing alert (GPS Recovery,
Geofencing, AI Risk Prediction, Overtaking Safety, Emergency API)
routes its findings through this module so alerts are persisted,
cached, and broadcast consistently in one place.
"""

import logging
from datetime import datetime

from backend.app.db.models import Alert
from backend.app.db.session import SessionLocal
from backend.app.redis_client import redis_db

logger = logging.getLogger("smartmove.alerts")


# Recent alerts are cached in Redis as a capped list so the
# dashboard's live alert panel can hydrate instantly on page load
# without a DB round trip.
ALERT_CACHE_KEY = "alerts:recent"
ALERT_CACHE_MAX_LEN = 200

# Overspeed threshold (km/h) used for the built-in overspeed check.
OVERSPEED_THRESHOLD_KMH = 90


def _persist_to_db(alert):
    """
    Persist an alert to Postgres. Failures here are logged but never
    block the real-time pipeline - the alert has already been
    cached in Redis and broadcast by the time this runs.
    """

    db = SessionLocal()

    try:
        record = Alert(
            vehicle_id=alert["vehicle_id"],
            alert_type=alert["alert_type"],
            severity=alert["priority"],
            message=alert.get("message", ""),
        )

        db.add(record)
        db.commit()

    except Exception as exc:
        logger.error("Failed to persist alert to DB: %s", exc)
        db.rollback()

    finally:
        db.close()


def _cache_alert(alert):
    """
    Push the alert onto the capped Redis recent-alerts list.
    """

    import json

    try:
        redis_db.lpush(ALERT_CACHE_KEY, json.dumps(alert))
        redis_db.ltrim(ALERT_CACHE_KEY, 0, ALERT_CACHE_MAX_LEN - 1)

    except Exception as exc:
        logger.error("Failed to cache alert in Redis: %s", exc)


def get_recent_alerts(limit=50):
    """
    Retrieve the most recent alerts from the Redis cache, newest
    first. Used by api/dashboard.py for initial page load.
    """

    import json

    try:
        raw = redis_db.lrange(ALERT_CACHE_KEY, 0, limit - 1)
        return [json.loads(item) for item in raw]

    except Exception as exc:
        logger.error("Failed to read recent alerts from Redis: %s", exc)
        return []


def raise_alert(vehicle_id, alert_type, priority, message, recommendation=""):
    """
    Core entry point: build a normalized alert dict, cache it,
    persist it, and return it so the caller (decision_engine.py)
    can include it in the WebSocket broadcast payload.
    """

    alert = {
        "vehicle_id": vehicle_id,
        "alert_type": alert_type,
        "priority": priority,
        "message": message,
        "recommendation": recommendation,
        "timestamp": datetime.utcnow().isoformat(),
    }

    _cache_alert(alert)
    _persist_to_db(alert)

    return alert


def evaluate_alerts(vehicle_data, gps_result, zone_result, road_health_result,
                     ml_result, overtaking_alerts):
    """
    Master alert-evaluation entry point, called once per telemetry
    message by decision_engine.py after every upstream engine has
    produced its result.

    Returns a list of alert dicts raised for this vehicle on this
    tick (may be empty).
    """

    vehicle_id = vehicle_data["vehicle_id"]
    raised = []

    # --- GPS Lost ---
    if gps_result.get("gps_lost"):
        raised.append(raise_alert(
            vehicle_id,
            "GPS Lost",
            "HIGH",
            f"GPS signal lost. Estimated position via dead "
            f"reckoning (confidence {gps_result.get('confidence')}).",
            recommendation="Verify Position Manually"
        ))

    # --- Zone-based alerts ---
    zone_type = zone_result.get("zone_type")

    if zone_result.get("inside") and zone_type:

        zone_alert_map = {
            "School": ("School Zone Entered", "Reduce Speed"),
            "Hairpin": ("Hairpin Ahead", "Slow Down and Honk"),
            "Hospital": ("Hospital Zone Entered", "Avoid Honking, Reduce Speed"),
            "Construction": ("Construction Zone", "Reduce Speed, Stay Alert"),
            "Flood": ("Flood Zone", "Avoid Route if Possible"),
            "Accident": ("Accident Zone", "Proceed with Caution"),
            "RoadBlock": ("Road Block", "Seek Alternate Route"),
            "Bridge": ("Bridge Ahead", "Maintain Safe Speed"),
        }

        alert_type, recommendation = zone_alert_map.get(
            zone_type, (f"{zone_type} Zone Entered", "Proceed with Caution")
        )

        raised.append(raise_alert(
            vehicle_id,
            alert_type,
            "MEDIUM",
            f"Vehicle {vehicle_id} entered {zone_type} zone.",
            recommendation=recommendation
        ))

    # --- Road health / hazard proximity ---
    nearest_hazard = road_health_result.get("nearest_hazard")
    nearest_distance = road_health_result.get("nearest_hazard_distance")

    if nearest_hazard and nearest_distance is not None and nearest_distance < 80:

        raised.append(raise_alert(
            vehicle_id,
            nearest_hazard.get("hazard_type", "Road Hazard"),
            "MEDIUM",
            f"{nearest_hazard.get('hazard_type', 'Hazard')} detected "
            f"{round(nearest_distance)}m ahead.",
            recommendation="Reduce Speed"
        ))

    # --- Overspeed ---
    if vehicle_data.get("speed", 0) > OVERSPEED_THRESHOLD_KMH:

        raised.append(raise_alert(
            vehicle_id,
            "Overspeed",
            "HIGH",
            f"Vehicle {vehicle_id} traveling at "
            f"{vehicle_data['speed']} km/h.",
            recommendation="Reduce Speed Immediately"
        ))

    # --- AI Risk Prediction ---
    if ml_result.get("risk_category") == "HIGH":

        raised.append(raise_alert(
            vehicle_id,
            "High AI Risk",
            "HIGH",
            f"AI predicts HIGH risk ({round(ml_result['risk_probability'] * 100)}%). "
            f"Reason: {ml_result.get('reason')}",
            recommendation=_recommendation_from_reason(ml_result.get("reason", ""))
        ))

    # --- Overtaking / V2V alerts (already built by overtaking.py) ---
    for alert in overtaking_alerts:

        raised.append(raise_alert(
            alert["target_vehicle_id"],
            alert["alert_type"],
            alert["priority"],
            alert["message"],
            recommendation=alert["recommendation"]
        ))

    return raised


def _recommendation_from_reason(reason):
    """
    Derive a single actionable recommendation string from the
    Explainable-AI reason text produced by ml_model.py.
    """

    reason_lower = reason.lower()

    if "school" in reason_lower or "hairpin" in reason_lower:
        return "Reduce Speed, Maintain Lane"
    if "overspeed" in reason_lower:
        return "Reduce Speed Immediately"
    if "gps" in reason_lower:
        return "Verify Position Manually"
    if "road health" in reason_lower or "construction" in reason_lower:
        return "Avoid Overtaking, Proceed with Caution"
    if "heavy vehicle" in reason_lower:
        return "Maintain Safe Following Distance"

    return "Proceed with Caution"
