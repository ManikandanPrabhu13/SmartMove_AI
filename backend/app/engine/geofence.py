"""
geofence.py

Polygon Geofencing Engine.

Supports true point-in-polygon detection using Shapely for all
danger zone types:

    School
    Hairpin
    Hospital
    Construction
    Flood
    Accident
    RoadBlock

Also supports legacy circle-defined zones (lat/lon/radius) by
auto-converting them into an approximate circular polygon, so
older zone records keep working without migration.
"""

import json
import math

from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points


# -------------------------
# Distance utility (kept from the original implementation)
# -------------------------

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two GPS points.
    Returns distance in meters.
    """

    R = 6371000  # Earth radius (meters)

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)

    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# -------------------------
# Circle -> Polygon conversion
# -------------------------

def _meters_to_degrees_lat(meters):
    """
    Approximate conversion of meters to degrees of latitude.
    """
    return meters / 111320.0


def _meters_to_degrees_lon(meters, latitude):
    """
    Approximate conversion of meters to degrees of longitude,
    accounting for latitude shrinkage of longitude degrees.
    """
    return meters / (111320.0 * max(math.cos(math.radians(latitude)), 1e-6))


def circle_to_polygon(latitude, longitude, radius_m, num_points=16):
    """
    Approximate a circular zone as a Shapely polygon so it can be
    processed by the same point-in-polygon pipeline as true
    polygon zones.
    """

    points = []

    for i in range(num_points):
        angle = 2 * math.pi * (i / num_points)

        dlat = _meters_to_degrees_lat(radius_m) * math.sin(angle)
        dlon = _meters_to_degrees_lon(radius_m, latitude) * math.cos(angle)

        points.append((latitude + dlat, longitude + dlon))

    # Shapely expects (x, y) = (lon, lat) ordering
    return Polygon([(lon, lat) for lat, lon in points])


def zone_to_polygon(zone):
    """
    Build a Shapely Polygon from a zone record.

    A zone dict may contain either:
      - "polygon_geojson": a JSON string / list of [lat, lon] vertices, or
      - "latitude", "longitude", "radius": a legacy circle definition.
    """

    polygon_data = zone.get("polygon_geojson")

    if polygon_data:

        vertices = polygon_data

        if isinstance(vertices, str):
            vertices = json.loads(vertices)

        # vertices are [lat, lon] pairs; Shapely wants (lon, lat)
        shapely_coords = [(lon, lat) for lat, lon in vertices]

        return Polygon(shapely_coords)

    # Fall back to circle definition
    return circle_to_polygon(
        zone["latitude"],
        zone["longitude"],
        zone["radius"]
    )


# -------------------------
# Point-in-Polygon Detection
# -------------------------

def is_inside_zone(vehicle, zone):
    """
    Check whether a vehicle's position is inside a danger zone
    polygon (true polygon geometry, not just circle-radius math).

    Returns:
        (is_inside: bool, distance_to_boundary_m: float)
    """

    polygon = zone_to_polygon(zone)

    point = Point(vehicle["longitude"], vehicle["latitude"])

    if polygon.contains(point):
        return True, 0.0

    # Not inside: compute distance from point to nearest polygon edge,
    # converted from degrees to meters via haversine on the nearest point.
    nearest_on_poly, _ = nearest_points(polygon, point)

    distance = haversine_distance(
        vehicle["latitude"],
        vehicle["longitude"],
        nearest_on_poly.y,
        nearest_on_poly.x
    )

    return False, round(distance, 2)


def find_active_zone(vehicle, zones):
    """
    Given a vehicle position and a list of zone dicts, return the
    zone the vehicle is currently inside (if any), plus the
    distance to the nearest zone boundary overall.

    Returns:
        {
            "zone": zone_dict_or_None,
            "zone_type": str_or_None,
            "severity": str_or_None,
            "inside": bool,
            "distance_to_nearest_zone": float
        }
    """

    active_zone = None
    min_distance = float("inf")

    for zone in zones:

        inside, distance = is_inside_zone(vehicle, zone)

        if inside:
            active_zone = zone
            min_distance = 0.0
            break

        if distance < min_distance:
            min_distance = distance

    if active_zone:
        return {
            "zone": active_zone,
            "zone_type": active_zone.get("zone_type"),
            "severity": active_zone.get("severity"),
            "inside": True,
            "distance_to_nearest_zone": 0.0
        }

    return {
        "zone": None,
        "zone_type": None,
        "severity": None,
        "inside": False,
        "distance_to_nearest_zone": (
            round(min_distance, 2) if min_distance != float("inf") else None
        )
    }
