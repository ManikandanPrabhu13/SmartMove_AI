"""
hazards.py

Road Hazard API.

Point-hazards (as opposed to zone polygons) that feed
engine/road_health.py: Pothole, Construction, Flood, RoadBlock,
Accident, SpeedBreaker, OilSpill, FallenTree, RoadDamage.

Same in-memory + Redis-cache pattern as zones.py, so
road_health.py can read the current hazard set on every telemetry
tick without a live Postgres dependency.
"""

from fastapi import APIRouter

from backend.app.redis_client import redis_db
import json

router = APIRouter(
    prefix="/hazards",
    tags=["Road Hazards"]
)

HAZARD_CACHE_KEY = "hazards:cache"

_default_hazards = [
    {"id": 1, "hazard_type": "Pothole", "latitude": 13.0830, "longitude": 80.2709},
    {"id": 2, "hazard_type": "Construction", "latitude": 13.0822, "longitude": 80.2716},
    {"id": 3, "hazard_type": "Flood", "latitude": 13.0813, "longitude": 80.2703},
    {"id": 4, "hazard_type": "RoadBlock", "latitude": 13.0806, "longitude": 80.2696},
    {"id": 5, "hazard_type": "Accident", "latitude": 13.0851, "longitude": 80.2741},
    {"id": 6, "hazard_type": "SpeedBreaker", "latitude": 13.0834, "longitude": 80.2713},
    {"id": 7, "hazard_type": "OilSpill", "latitude": 13.0840, "longitude": 80.2720},
    {"id": 8, "hazard_type": "FallenTree", "latitude": 13.0846, "longitude": 80.2727},
    {"id": 9, "hazard_type": "RoadDamage", "latitude": 13.0817, "longitude": 80.2710},
]

hazards = list(_default_hazards)


def _save_cache():
    redis_db.set(HAZARD_CACHE_KEY, json.dumps(hazards))


def get_hazard_cache():
    """
    Read the current hazard list from Redis. Falls back to the
    in-memory default set if the cache hasn't been written yet
    (e.g. Redis was flushed).
    """

    data = redis_db.get(HAZARD_CACHE_KEY)

    if data:
        return json.loads(data)

    return hazards


_save_cache()


@router.get("/")
def get_all_hazards():

    return hazards


@router.post("/")
def create_hazard(hazard: dict):

    hazard["id"] = max((h["id"] for h in hazards), default=0) + 1

    hazards.append(hazard)

    _save_cache()

    return {
        "message": "Hazard Added",
        "hazard": hazard
    }
