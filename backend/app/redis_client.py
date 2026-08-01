"""
redis_client.py

Handles Redis connection and live vehicle data.
"""

import redis
import json

from backend.app.config import REDIS_HOST, REDIS_PORT


# Connect to Redis
redis_db = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)


def save_vehicle(vehicle_data):
    """
    Store vehicle data in Redis.
    """

    key = f"vehicle:{vehicle_data['vehicle_id']}"

    redis_db.set(
        key,
        json.dumps(vehicle_data)
    )


def get_vehicle(vehicle_id):
    """
    Get one vehicle.
    """

    key = f"vehicle:{vehicle_id}"

    data = redis_db.get(key)

    if data:
        return json.loads(data)

    return None


def get_all_vehicle_keys():
    """
    Return all active vehicle Redis keys.
    """

    return redis_db.keys("vehicle:*")


def get_all_vehicles():
    """
    Return the full live vehicle data dicts for every vehicle
    currently tracked in Redis. Used by the overtaking safety
    module and the dashboard aggregate endpoint.
    """

    vehicles = []

    for key in get_all_vehicle_keys():

        data = redis_db.get(key)

        if data:
            vehicles.append(json.loads(data))

    return vehicles


def save_risk_result(vehicle_id, risk_data):
    """
    Store the latest AI decision-engine result for a vehicle.
    """

    key = f"risk:{vehicle_id}"

    redis_db.set(
        key,
        json.dumps(risk_data)
    )


def get_risk_result(vehicle_id):
    """
    Get the latest risk result for one vehicle.
    """

    key = f"risk:{vehicle_id}"

    data = redis_db.get(key)

    if data:
        return json.loads(data)

    return None


def get_all_risk_keys():
    """
    Return all vehicles that currently have a stored risk result.
    """

    return redis_db.keys("risk:*")


def save_zone_cache(zones):
    """
    Cache the full zone list (used by geofence.py to avoid hitting
    the DB on every single telemetry message).
    """

    redis_db.set("zones:cache", json.dumps(zones))


def get_zone_cache():
    """
    Retrieve the cached zone list. Returns None if not cached yet.
    """

    data = redis_db.get("zones:cache")

    if data:
        return json.loads(data)

    return None