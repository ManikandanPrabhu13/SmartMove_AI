"""
emergency.py

Publishes emergency events (brake failure, engine failure,
accident, danger zone) to the MQTT broker on the emergency/#
topic family, reusing the event-generation functions already
defined in triggers.py rather than duplicating that logic.

publisher.py calls maybe_trigger_emergency() once per tick for
each vehicle; it fires rarely so emergencies read as occasional
demo events rather than constant noise.
"""

import json
import random

from triggers import (
    brake_failure,
    engine_failure,
    accident,
    danger_zone,
)


# Overall probability (per vehicle per tick) that an emergency
# event fires at all.
EMERGENCY_TRIGGER_PROBABILITY = 0.01

_EVENT_GENERATORS = [
    brake_failure,
    engine_failure,
    accident,
    danger_zone,
]


def maybe_trigger_emergency(mqtt_client, vehicle):
    """
    With small probability, generate a random emergency event for
    the given vehicle and publish it to emergency/{vehicle_id}.

    Returns the published event dict, or None if no event fired
    this tick.
    """

    if random.random() > EMERGENCY_TRIGGER_PROBABILITY:
        return None

    generator = random.choice(_EVENT_GENERATORS)

    event = generator(vehicle)

    topic = f"emergency/{vehicle.vehicle_id}"

    mqtt_client.publish(topic, json.dumps(event))

    print("Emergency Published:", event)

    return event
