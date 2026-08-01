"""
main.py

Entry point of SMARTMOVE AI Backend.
"""

import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.app.mqtt.client import start_mqtt, stop_mqtt
from backend.app.mqtt.handlers import set_event_loop

# Import API Routers
from backend.app.api.vehicles import router as vehicle_router
from backend.app.api.zones import router as zone_router
from backend.app.api.emergency import router as emergency_router
from backend.app.api.hazards import router as hazard_router
from backend.app.api.websocket import router as websocket_router
from backend.app.api.dashboard import router as dashboard_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

logger = logging.getLogger("smartmove.main")

# Resolve static/template directories relative to THIS file's own
# location, not the process's current working directory. Using a
# bare relative string like "backend/app/static" only works if the
# server happens to be launched from the exact repo root; launching
# from any other directory (IDE run button, different shell cwd,
# a different Docker WORKDIR, etc.) makes FastAPI/Jinja2 unable to
# find the directory/template, which is what was causing the
# dashboard's HTTP 500.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(
    title="SMARTMOVE AI",
    version="1.0"
)

# Register API Routers
app.include_router(vehicle_router)
app.include_router(zone_router)
app.include_router(emergency_router)
app.include_router(hazard_router)
app.include_router(websocket_router)
app.include_router(dashboard_router)

# Static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return {
        "message": "SMARTMOVE AI Backend Running",
        "dashboard": "/dashboard",
        "docs": "/docs"
    }


@app.on_event("startup")
def startup():

    logger.info("Starting SmartMove-AI backend...")

    # Register the running asyncio event loop so the MQTT network
    # thread (paho-mqtt runs its own thread) can safely schedule
    # WebSocket broadcasts onto it.
    loop = asyncio.get_event_loop()
    set_event_loop(loop)

    logger.info("Starting MQTT Client...")
    start_mqtt()

    logger.info("Backend Started Successfully")


@app.on_event("shutdown")
def shutdown():

    logger.info("Shutting down MQTT Client...")
    stop_mqtt()
