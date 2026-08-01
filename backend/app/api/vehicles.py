"""
vehicles.py

Vehicle API
"""

from fastapi import APIRouter
from backend.app.redis_client import get_all_vehicle_keys, get_vehicle, get_risk_result

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


@router.get("/")
def list_vehicles():
    """
    Return every live vehicle, enriched with its latest AI decision
    engine result (risk probability, driver score, category, and
    current alerts) so API consumers don't need a second round trip.
    """

    vehicles = []

    keys = get_all_vehicle_keys()

    for key in keys:

        vehicle_id = key.split(":")[1]

        vehicle = get_vehicle(vehicle_id)

        if vehicle:

            risk = get_risk_result(vehicle_id)

            vehicles.append({
                **vehicle,
                "risk": risk,
            })

    return vehicles


@router.get("/{vehicle_id}")
def get_vehicle_by_id(vehicle_id: str):

    vehicle = get_vehicle(vehicle_id)

    if not vehicle:
        return {
            "message": "Vehicle not found"
        }

    risk = get_risk_result(vehicle_id)

    return {
        **vehicle,
        "risk": risk,
    }
