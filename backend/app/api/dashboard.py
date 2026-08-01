"""
dashboard.py

Aggregate dashboard endpoints.
"""

import logging
import os
import traceback

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from backend.app.redis_client import get_all_vehicles, get_risk_result
from backend.app.api.zones import danger_zones
from backend.app.api.hazards import get_hazard_cache
from backend.app.engine.alerts import get_recent_alerts

logger = logging.getLogger("smartmove.api.dashboard")

router = APIRouter(tags=["Dashboard"])

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "templates"
)

templates = Jinja2Templates(directory=TEMPLATES_DIR)


@router.get("/dashboard", response_class=HTMLResponse)
def render_dashboard(request: Request):
    """
    Render SmartMove Dashboard.
    """
    try:
        logger.info("Rendering dashboard")

        return templates.TemplateResponse(
             request=request,
             name="dashboard.html",
             context={}
)

    except Exception as e:
        logger.exception("Dashboard rendering failed")
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/dashboard/summary")
def dashboard_summary():
    """
    Dashboard initial data.
    """

    try:

        try:
            vehicles = get_all_vehicles() or []
        except Exception as e:
            logger.exception("Vehicle retrieval failed")
            vehicles = []

        enriched = []

        for vehicle in vehicles:

            try:
                vehicle_id = vehicle.get("vehicle_id")

                risk = get_risk_result(vehicle_id) or {}

            except Exception:
                logger.exception("Risk retrieval failed")
                risk = {}

            enriched.append({
                **vehicle,
                "risk": risk
            })

        try:
            hazards = get_hazard_cache()
        except Exception:
            logger.exception("Hazard retrieval failed")
            hazards = []

        try:
            alerts = get_recent_alerts(limit=100)
        except Exception:
            logger.exception("Alert retrieval failed")
            alerts = []

        return {
            "vehicles": enriched,
            "zones": danger_zones,
            "hazards": hazards,
            "alerts": alerts,
            "connected_vehicles": len(enriched),
            "active_alert_count": len(alerts)
        }

    except Exception as e:

        logger.exception("Dashboard summary failed")
        traceback.print_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e)
            }
        )