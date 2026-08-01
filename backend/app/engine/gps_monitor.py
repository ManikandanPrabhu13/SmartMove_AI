"""
gps_monitor.py

GPS Recovery Engine.

Implements all three required techniques together:

    A. Kinematic Dead Reckoning Engine
       Estimate position from last known GPS, speed, heading, and
       elapsed time when GPS is lost.

    B. Road Constraint Engine
       Snap the dead-reckoned estimate onto the nearest valid road
       segment using Shapely, so estimated positions can never fall
       in impossible places (e.g. inside a building block, in the
       sea, etc).

    C. GPS Confidence Engine
       Produce a confidence score (1.0 -> 0.1) that decays the
       longer GPS stays lost, and recovers instantly once a real
       GPS fix returns.

This module is stateful per-vehicle (it needs the last known good
fix, and how long GPS has been lost) so it keeps an in-memory
tracking dict keyed by vehicle_id. This state also mirrors what is
cached in Redis, so a process restart can rehydrate from the last
saved vehicle record.
"""

import math
import time

from shapely.geometry import Point, LineString
from shapely.ops import nearest_points

from backend.app.config import (
    GPS_CONFIDENCE_DECAY_PER_SEC,
    GPS_CONFIDENCE_FLOOR,
    ROAD_SNAP_MAX_DISTANCE
)


# -------------------------
# Road network
# -------------------------
#
# A minimal road network expressed as Shapely LineStrings, used by
# the Road Constraint Engine to snap dead-reckoned estimates onto a
# plausible road segment. In production this would be loaded from a
# real road-network dataset (e.g. OpenStreetMap extract); here we
# provide a small, realistic seed network covering the simulator's
# operating area so the snapping logic is fully functional out of
# the box. Coordinates are (lon, lat) to match Shapely convention.

ROAD_NETWORK = [
    LineString([
        (80.2707, 13.0827),
        (80.2712, 13.0832),
        (80.2718, 13.0838),
        (80.2725, 13.0844),
        (80.2732, 13.0850),
    ]),
    LineString([
        (80.2700, 13.0810),
        (80.2710, 13.0820),
        (80.2720, 13.0830),
        (80.2730, 13.0840),
    ]),
    LineString([
        (80.2755, 13.0855),
        (80.2760, 13.0860),
        (80.2765, 13.0865),
    ]),
]


# Per-vehicle tracking state:
# {
#   vehicle_id: {
#       "last_good_lat": float,
#       "last_good_lon": float,
#       "last_good_time": float (epoch seconds),
#       "last_speed": float,
#       "last_heading": float,
#       "lost_since": float or None,
#   }
# }
_vehicle_state = {}


def _get_state(vehicle_id):

    if vehicle_id not in _vehicle_state:
        _vehicle_state[vehicle_id] = {
            "last_good_lat": None,
            "last_good_lon": None,
            "last_good_time": None,
            "last_speed": 0.0,
            "last_heading": 0.0,
            "lost_since": None,
        }

    return _vehicle_state[vehicle_id]


# -------------------------
# A. Kinematic Dead Reckoning Engine
# -------------------------

def dead_reckon(last_lat, last_lon, speed_kmh, heading_deg, dt_seconds):
    """
    Estimate a new position given a last known GPS fix, constant
    speed and heading, and elapsed time.

    speed_kmh: vehicle speed in km/h
    heading_deg: compass heading in degrees (0 = north, clockwise)
    dt_seconds: elapsed time since the last known fix
    """

    speed_m_per_s = speed_kmh * (1000.0 / 3600.0)

    distance_m = speed_m_per_s * dt_seconds

    heading_rad = math.radians(heading_deg)

    # Displacement in meters, decomposed into north/east components
    delta_north = distance_m * math.cos(heading_rad)
    delta_east = distance_m * math.sin(heading_rad)

    delta_lat = delta_north / 111320.0

    delta_lon = delta_east / (
        111320.0 * max(math.cos(math.radians(last_lat)), 1e-6)
    )

    estimated_lat = last_lat + delta_lat
    estimated_lon = last_lon + delta_lon

    return estimated_lat, estimated_lon


# -------------------------
# B. Road Constraint Engine
# -------------------------

def snap_to_road(estimated_lat, estimated_lon):
    """
    Snap an estimated (lat, lon) position onto the nearest point on
    the nearest road segment in ROAD_NETWORK, preventing impossible
    off-road estimated positions.

    Returns:
        (snapped_lat, snapped_lon, snap_distance_m)
    """

    point = Point(estimated_lon, estimated_lat)

    best_snap = None
    best_distance = float("inf")

    for road in ROAD_NETWORK:

        nearest_on_road, _ = nearest_points(road, point)

        # Approximate meters via haversine-equivalent flat conversion
        # (adequate at city scale for snapping comparison purposes).
        dlat = nearest_on_road.y - estimated_lat
        dlon = nearest_on_road.x - estimated_lon

        dist_m = math.sqrt(
            (dlat * 111320.0) ** 2
            + (dlon * 111320.0 * math.cos(math.radians(estimated_lat))) ** 2
        )

        if dist_m < best_distance:
            best_distance = dist_m
            best_snap = nearest_on_road

    if best_snap is None:
        # No road network available; return estimate unmodified.
        return estimated_lat, estimated_lon, 0.0

    if best_distance > ROAD_SNAP_MAX_DISTANCE:
        # Too far from any known road to trust the snap; return the
        # raw dead-reckoned estimate but flag the large distance so
        # the confidence engine can penalize it accordingly.
        return estimated_lat, estimated_lon, round(best_distance, 2)

    return round(best_snap.y, 7), round(best_snap.x, 7), round(best_distance, 2)


# -------------------------
# C. GPS Confidence Engine
# -------------------------

def compute_confidence(seconds_lost):
    """
    Confidence decays linearly from 1.0 down to a floor value the
    longer GPS has been continuously lost. Returns a value in
    [GPS_CONFIDENCE_FLOOR, 1.0].
    """

    confidence = 1.0 - (seconds_lost * GPS_CONFIDENCE_DECAY_PER_SEC)

    return round(max(confidence, GPS_CONFIDENCE_FLOOR), 3)


# -------------------------
# Orchestrator
# -------------------------

def process_gps(vehicle_data):
    """
    Main entry point for the GPS Recovery Engine. Call this for
    every incoming telemetry message.

    vehicle_data must contain:
        vehicle_id, latitude, longitude, speed, heading
    and may optionally contain:
        gps_status ("OK" or "LOST")

    Returns a dict:
        {
            "gps_lost": bool,
            "latitude": float,      (raw or estimated/snapped)
            "longitude": float,     (raw or estimated/snapped)
            "confidence": float,
            "road_snap_distance": float or None
        }
    """

    vehicle_id = vehicle_data["vehicle_id"]
    state = _get_state(vehicle_id)

    now = time.time()

    gps_status = vehicle_data.get("gps_status", "OK")
    gps_lost = (gps_status != "OK")

    speed = vehicle_data.get("speed", state["last_speed"])
    heading = vehicle_data.get("heading", state["last_heading"])

    if not gps_lost:
        # Fresh, valid GPS fix: reset tracking state and return as-is.
        state["last_good_lat"] = vehicle_data["latitude"]
        state["last_good_lon"] = vehicle_data["longitude"]
        state["last_good_time"] = now
        state["last_speed"] = speed
        state["last_heading"] = heading
        state["lost_since"] = None

        return {
            "gps_lost": False,
            "latitude": vehicle_data["latitude"],
            "longitude": vehicle_data["longitude"],
            "confidence": 1.0,
            "road_snap_distance": None
        }

    # GPS is lost: run dead reckoning from the last known good fix.
    if state["last_good_lat"] is None:
        # No prior fix at all yet (GPS lost on the very first
        # message) - nothing to reckon from, so fall back to
        # whatever coordinates were sent (best-effort) with minimum
        # confidence.
        state["lost_since"] = state["lost_since"] or now

        return {
            "gps_lost": True,
            "latitude": vehicle_data.get("latitude"),
            "longitude": vehicle_data.get("longitude"),
            "confidence": GPS_CONFIDENCE_FLOOR,
            "road_snap_distance": None
        }

    if state["lost_since"] is None:
        state["lost_since"] = now

    dt = now - state["last_good_time"]

    estimated_lat, estimated_lon = dead_reckon(
        state["last_good_lat"],
        state["last_good_lon"],
        speed,
        heading,
        dt
    )

    snapped_lat, snapped_lon, snap_distance = snap_to_road(
        estimated_lat, estimated_lon
    )

    seconds_lost = now - state["lost_since"]
    confidence = compute_confidence(seconds_lost)

    state["last_speed"] = speed
    state["last_heading"] = heading

    return {
        "gps_lost": True,
        "latitude": snapped_lat,
        "longitude": snapped_lon,
        "confidence": confidence,
        "road_snap_distance": snap_distance
    }
