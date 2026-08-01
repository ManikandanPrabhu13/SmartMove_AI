"""
client.py

MQTT Subscriber.

Subscribes to both telemetry/# and emergency/# and dispatches each
incoming message to mqtt/handlers.py by topic.
"""

import logging

import paho.mqtt.client as mqtt

from backend.app.config import MQTT_BROKER, MQTT_PORT
from backend.app.mqtt.handlers import process_message

logger = logging.getLogger("smartmove.mqtt.client")

BROKER = MQTT_BROKER
PORT = MQTT_PORT

TELEMETRY_TOPIC = "telemetry/#"
EMERGENCY_TOPIC = "emergency/#"


client = mqtt.Client()


def on_connect(client, userdata, flags, rc):

    logger.info("Connected to MQTT Broker (rc=%s)", rc)

    client.subscribe(TELEMETRY_TOPIC)
    client.subscribe(EMERGENCY_TOPIC)

    logger.info("Subscribed to %s and %s", TELEMETRY_TOPIC, EMERGENCY_TOPIC)


def on_message(client, userdata, msg):

    payload = msg.payload.decode()

    process_message(msg.topic, payload)


def on_disconnect(client, userdata, rc):

    logger.warning("Disconnected from MQTT Broker (rc=%s)", rc)


def start_mqtt():
    """
    Connect and start the MQTT network loop in a background thread.
    Connection failures are logged but do not crash the FastAPI app
    - the dashboard and REST APIs remain usable even if the broker
    is temporarily unavailable, and paho will keep retrying via
    loop_start()'s internal reconnect handling once connected.
    """

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    try:
        client.connect(BROKER, PORT)
        client.loop_start()

    except Exception as exc:
        logger.error("Failed to connect to MQTT broker: %s", exc)


def stop_mqtt():
    """
    Cleanly stop the MQTT network loop on FastAPI shutdown.
    """

    try:
        client.loop_stop()
        client.disconnect()
    except Exception as exc:
        logger.error("Error stopping MQTT client: %s", exc)
