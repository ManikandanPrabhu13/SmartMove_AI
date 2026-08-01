"""
zones.py

Danger Zone API.

Provides CRUD access to geofenced danger zones covering all
required zone types: School, Hairpin, Hospital, Construction,
Flood, Accident, RoadBlock, Bridge.

Zones are held in-memory (seeded with a realistic default set
around the simulator's operating area) and mirrored into the Redis
zone cache on every mutation, so engine/geofence.py can read them
without needing a live Postgres connection - this keeps the system
fully runnable for a demo/hackathon environment while still being
upgradable to full DB-backed persistence later (DangerZone model
already exists in db/models.py for that purpose).
"""

from fastapi import APIRouter

from backend.app.redis_client import save_zone_cache, get_zone_cache

router = APIRouter(
    prefix="/zones",
    tags=["Danger Zones"]
)


_default_zones = [
    {
        "id": 1,
        "zone_type": "School",
        "latitude": 13.0828,
        "longitude": 80.2707,
        "radius": 100,
        "severity": "MEDIUM",
        "polygon_geojson": None,
    },
    {
        "id": 2,
        "zone_type": "Hairpin",
        "latitude": 13.0838,
        "longitude": 80.2718,
        "radius": 60,
        "severity": "HIGH",
        "polygon_geojson": None,
    },
    {
        "id": 3,
        "zone_type": "Hospital",
        "latitude": 13.0844,
        "longitude": 80.2725,
        "radius": 90,
        "severity": "MEDIUM",
        "polygon_geojson": None,
    },
    {
        "id": 4,
        "zone_type": "Construction",
        "latitude": 13.0820,
        "longitude": 80.2715,
        "radius": 70,
        "severity": "MEDIUM",
        "polygon_geojson": None,
    },
    {
        "id": 5,
        "zone_type": "Flood",
        "latitude": 13.0812,
        "longitude": 80.2702,
        "radius": 120,
        "severity": "HIGH",
        "polygon_geojson": None,
    },
    {
        "id": 6,
        "zone_type": "Accident",
        "latitude": 13.0850,
        "longitude": 80.2740,
        "radius": 50,
        "severity": "HIGH",
        "polygon_geojson": None,
    },
    {
        "id": 7,
        "zone_type": "RoadBlock",
        "latitude": 13.0805,
        "longitude": 80.2695,
        "radius": 60,
        "severity": "MEDIUM",
        "polygon_geojson": None,
    },
    {
        "id": 8,
        "zone_type": "Bridge",
        "latitude": 13.0855,
        "longitude": 80.2755,
        "radius": 80,
        "severity": "HIGH",
        "polygon_geojson": None,
    },
]


danger_zones = list(_default_zones)

# Seed the Redis cache on import so geofence.py has data from the
# very first telemetry message, even before any API call is made.
save_zone_cache(danger_zones)


@router.get("/")
def get_all_zones():

    return danger_zones


@router.post("/")
def create_zone(zone: dict):

    zone["id"] = max((z["id"] for z in danger_zones), default=0) + 1

    zone.setdefault("polygon_geojson", None)

    danger_zones.append(zone)

    save_zone_cache(danger_zones)

    return {
        "message": "Zone Added",
        "zone": zone
    }


@router.get("/{zone_type}")
def get_zones_by_type(zone_type: str):

    return [
        z for z in danger_zones
        if z["zone_type"].lower() == zone_type.lower()
    ]
