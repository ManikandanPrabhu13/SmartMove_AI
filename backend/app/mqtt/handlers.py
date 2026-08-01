"""
handlers.py

Processes incoming MQTT messages.

Two topic families are handled:
    telemetry/{vehicle_id}  -> full decision engine pipeline
    emergency/{vehicle_id}  -> direct emergency alert + broadcast

This callback executes on paho-mqtt's own network thread, not on
the FastAPI/asyncio event loop. To safely push WebSocket broadcasts
from this thread, main.py registers the running event loop via
set_event_loop() at startup, and this module schedules the
coroutine onto it with asyncio.run_coroutine_threadsafe.
"""

import json
import logging
import asyncio

from backend.app.redis_client import save_vehicle
from backend.app.engine.decision_engine import run as run_decision_engine
from backend.app.engine.alerts import raise_alert
from backend.app.ws.manager import manager

logger = logging.getLogger("smartmove.mqtt.handlers")

# Populated by main.py on FastAPI startup via set_event_loop().
_event_loop = None


def set_event_loop(loop):
    """
    Register the FastAPI/uvicorn asyncio event loop so this thread
    (the MQTT network thread) can safely schedule WebSocket
    broadcasts onto it.
    """

    global _event_loop
    _event_loop = loop


def _broadcast(payload):
    """
    Thread-safe broadcast to every connected WebSocket dashboard
    client. No-op (with a debug log) if the event loop hasn't been
    registered yet, e.g. during very early startup.
    """

    if _event_loop is None:
        logger.debug("Event loop not yet registered - skipping broadcast.")
        return

    try:
        asyncio.run_coroutine_threadsafe(
            manager.broadcast(payload), _event_loop
        )
    except Exception as exc:
        logger.error("Failed to schedule WebSocket broadcast: %s", exc)


def process_telemetry(payload):
    """
    Handle a telemetry/{vehicle_id} MQTT message: save raw state to
    Redis, run it through the full decision engine pipeline, and
    broadcast the result to the dashboard.
    """

    try:
        data = json.loads(payload)

        # Save raw telemetry to Redis first, so overtaking.py /
        # dashboard reads always see the latest raw position even
        # while the pipeline below is executing.
        save_vehicle(data)

        result = run_decision_engine(data)

        _broadcast({
            "type": "telemetry",
            "data": result,
        })

    except Exception as exc:
        logger.error("Error processing telemetry message: %s", exc)


def process_emergency(payload):
    """
    Handle an emergency/{vehicle_id} MQTT message: raise a
    high-priority alert immediately and broadcast it, bypassing the
    full risk pipeline since emergencies are already unambiguous.
    """

    try:
        data = json.loads(payload)

        alert = raise_alert(
            vehicle_id=data.get("vehicle_id", "UNKNOWN"),
            alert_type=data.get("event", "Emergency"),
            priority="HIGH",
            message=(
                f"Emergency event '{data.get('event', 'Emergency')}' "
                f"reported by {data.get('vehicle_id', 'unknown vehicle')}."
            ),
            recommendation="Yield Immediately, Clear Path"
        )

        _broadcast({
            "type": "emergency",
            "data": alert,
        })

    except Exception as exc:
        logger.error("Error processing emergency message: %s", exc)


def process_message(topic, payload):
    """
    Single dispatch entry point used by mqtt/client.py, routing by
    topic prefix.
    """

    if topic.startswith("telemetry/"):
        process_telemetry(payload)
    elif topic.startswith("emergency/"):
        process_emergency(payload)
    else:
        logger.warning("Unrecognized MQTT topic: %s", topic)
