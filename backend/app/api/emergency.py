"""
emergency.py

Emergency Alert API.

Allows any client (dashboard operator, external system, or a
vehicle's own emergency button) to broadcast an emergency directly
via REST, in addition to the MQTT emergency/{vehicle_id} topic
handled by mqtt/handlers.py. Both paths converge on the same
alerts.raise_alert() function so emergencies are always persisted
and broadcast consistently regardless of origin.
"""

import logging

from fastapi import APIRouter

from backend.app.engine.alerts import raise_alert
from backend.app.ws.manager import manager

logger = logging.getLogger("smartmove.api.emergency")

router = APIRouter(
    prefix="/emergency",
    tags=["Emergency"]
)


@router.post("/broadcast")
async def broadcast_emergency(data: dict):

    vehicle_id = data.get("vehicle_id", "UNKNOWN")
    event = data.get("event", "Emergency")

    alert = raise_alert(
        vehicle_id=vehicle_id,
        alert_type=event,
        priority="HIGH",
        message=(
            f"Emergency event '{event}' reported by {vehicle_id} "
            f"at ({data.get('latitude')}, {data.get('longitude')})."
        ),
        recommendation="Yield Immediately, Clear Path"
    )

    await manager.broadcast({
        "type": "emergency",
        "data": alert,
    })

    return {
        "status": "success",
        "alert": alert
    }
