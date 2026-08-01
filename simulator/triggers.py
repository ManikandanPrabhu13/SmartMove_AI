"""
triggers.py

This file generates emergency events
for demonstration purposes.
"""

import time


def brake_failure(vehicle):
    """
    Simulate brake failure.
    """

    return {
        "event": "brake_failure",
        "vehicle_id": vehicle.vehicle_id,
        "latitude": vehicle.latitude,
        "longitude": vehicle.longitude,
        "timestamp": time.time()
    }


def engine_failure(vehicle):
    """
    Simulate engine failure.
    """

    return {
        "event": "engine_failure",
        "vehicle_id": vehicle.vehicle_id,
        "latitude": vehicle.latitude,
        "longitude": vehicle.longitude,
        "timestamp": time.time()
    }


def accident(vehicle):
    """
    Simulate an accident.
    """

    return {
        "event": "accident",
        "vehicle_id": vehicle.vehicle_id,
        "latitude": vehicle.latitude,
        "longitude": vehicle.longitude,
        "timestamp": time.time()
    }


def danger_zone(vehicle):
    """
    Simulate a danger zone event.
    """

    return {
        "event": "danger_zone",
        "vehicle_id": vehicle.vehicle_id,
        "latitude": vehicle.latitude,
        "longitude": vehicle.longitude,
        "timestamp": time.time()
    }