"""
publisher.py

Publishes vehicle telemetry to the MQTT broker via a dynamic,
controllable simulator instead of an uncontrolled infinite loop.

Reuses the existing Vehicle class (vehicle.py) and emergency event
generation (emergency.py / triggers.py) unchanged - only the
publishing loop around them is now driven by a SimulatorController
that supports:

    add      <id> <type> [speed]   - add a new simulated vehicle
    remove   <id>                  - remove a vehicle
    edit     <id> <field> <value>  - edit speed/type of a vehicle
    start                          - start/resume publishing
    pause                          - pause publishing (state kept)
    resume                         - alias for start
    stop                           - stop publishing (loop exits)
    list                           - show current fleet
    help                           - show available commands

Defaults to exactly two vehicles on startup, matching the existing
demo setup:

    V001 - Car
    V002 - Truck (heavy vehicle, used to demonstrate the
                  Overtaking Safety Module against V001)

The truck's route intentionally overlaps the car's route so the
Overtaking Safety Module has a realistic "heavy vehicle behind"
scenario to detect during a live demo.

Run interactively:

    python publisher.py

Then type commands at the `sim>` prompt. Typing nothing (just
Enter) is fine while the simulator is running - the publish loop
runs on a background thread, so the prompt never blocks telemetry.
"""

import json
import threading
import time

import paho.mqtt.client as mqtt

from vehicle import Vehicle
from emergency import maybe_trigger_emergency


BROKER = "localhost"
PORT = 1883

TICK_SECONDS = 1

# Shared route for both default vehicles - a short stretch of road
# that also matches the seed ROAD_NETWORK in
# backend/app/engine/gps_monitor.py, so simulated GPS-loss dead
# reckoning snaps onto a road the backend actually knows about.
DEFAULT_ROUTE = [
    (13.0827, 80.2707),
    (13.0832, 80.2712),
    (13.0838, 80.2718),
    (13.0844, 80.2725),
    (13.0850, 80.2732),
]


class SimulatorController:
    """
    Owns the MQTT client, the live vehicle fleet, and a background
    publish loop that can be started, paused, resumed, and stopped
    without restarting the process - so a live demo can add/remove/
    edit vehicles on the fly instead of relying on a fixed, always-on
    loop.
    """

    def __init__(self, broker=BROKER, port=PORT, tick_seconds=TICK_SECONDS):

        self.tick_seconds = tick_seconds

        self.client = mqtt.Client()
        self.client.connect(broker, port)

        self.vehicles = {}   # vehicle_id -> Vehicle instance
        self._lock = threading.Lock()

        self._running = False     # loop thread alive
        self._paused = False      # loop alive but not publishing
        self._thread = None

    # -----------------------------------------------------
    # Fleet management
    # -----------------------------------------------------

    def add_vehicle(self, vehicle_id, vehicle_type="Car", speed=45, route=None):
        """
        Add a new simulated vehicle to the fleet. Returns True on
        success, False if the vehicle_id is already in use.
        """

        with self._lock:

            if vehicle_id in self.vehicles:
                print(f"[simulator] Vehicle {vehicle_id} already exists.")
                return False

            self.vehicles[vehicle_id] = Vehicle(
                vehicle_id,
                route or DEFAULT_ROUTE,
                vehicle_type=vehicle_type,
                speed=speed,
            )

            print(f"[simulator] Added {vehicle_id} ({vehicle_type}, {speed} km/h).")
            return True

    def remove_vehicle(self, vehicle_id):
        """
        Remove a vehicle from the fleet. Returns True on success,
        False if it doesn't exist.
        """

        with self._lock:

            if vehicle_id not in self.vehicles:
                print(f"[simulator] Vehicle {vehicle_id} not found.")
                return False

            del self.vehicles[vehicle_id]

            print(f"[simulator] Removed {vehicle_id}.")
            return True

    def edit_vehicle(self, vehicle_id, field, value):
        """
        Edit a live property of an existing vehicle. Supported
        fields: "speed" (float, km/h) and "type" (vehicle_type
        string, affects icon color/classification on the dashboard).
        """

        with self._lock:

            vehicle = self.vehicles.get(vehicle_id)

            if not vehicle:
                print(f"[simulator] Vehicle {vehicle_id} not found.")
                return False

            if field in ("speed", "base_speed"):
                vehicle.base_speed = float(value)
                vehicle.speed = float(value)

            elif field in ("type", "vehicle_type"):
                vehicle.vehicle_type = value

            else:
                print(f"[simulator] Unknown field '{field}'. Use 'speed' or 'type'.")
                return False

            print(f"[simulator] Updated {vehicle_id}.{field} = {value}")
            return True

    def list_vehicles(self):

        with self._lock:

            if not self.vehicles:
                print("[simulator] No vehicles in the fleet.")
                return

            for vehicle_id, vehicle in self.vehicles.items():
                state = "paused" if self._paused else ("running" if self._running else "stopped")
                print(
                    f"  {vehicle_id:6s} {vehicle.vehicle_type:10s} "
                    f"{vehicle.base_speed:5.1f} km/h  [{state}]"
                )

    # -----------------------------------------------------
    # Publish loop control
    # -----------------------------------------------------

    def start(self):
        """
        Start the background publish loop if it isn't already
        running, or unpause it if it was paused.
        """

        if self._running and not self._paused:
            print("[simulator] Already running.")
            return

        if self._running and self._paused:
            self._paused = False
            print("[simulator] Resumed.")
            return

        self._running = True
        self._paused = False

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        print("[simulator] Started.")

    def resume(self):
        self.start()

    def pause(self):
        """
        Pause publishing without tearing down the fleet or the MQTT
        connection - vehicles keep their position/state and pick up
        exactly where they left off on resume.
        """

        if not self._running:
            print("[simulator] Not running.")
            return

        self._paused = True
        print("[simulator] Paused.")

    def stop(self):
        """
        Stop the publish loop entirely. The fleet definition is kept
        in memory so start() can be called again without re-adding
        vehicles.
        """

        self._running = False
        self._paused = False

        if self._thread:
            self._thread.join(timeout=self.tick_seconds * 2)

        print("[simulator] Stopped.")

    def _loop(self):

        while self._running:

            if not self._paused:

                with self._lock:
                    active_vehicles = list(self.vehicles.values())

                for vehicle in active_vehicles:

                    vehicle.move()
                    data = vehicle.get_data()

                    topic = f"telemetry/{vehicle.vehicle_id}"
                    self.client.publish(topic, json.dumps(data))

                    print("Published:", data)

                    maybe_trigger_emergency(self.client, vehicle)

            time.sleep(self.tick_seconds)


# -----------------------------------------------------
# Interactive CLI
# -----------------------------------------------------

HELP_TEXT = """
Available commands:
  add <id> <type> [speed]     e.g. add V003 Bike 30
  remove <id>                 e.g. remove V003
  edit <id> speed <value>     e.g. edit V002 speed 60
  edit <id> type <value>      e.g. edit V002 type Bus
  list                        show current fleet
  start | resume              start/resume publishing
  pause                        pause publishing (state kept)
  stop                          stop publishing
  help                          show this message
  quit / exit                   stop and exit the simulator
"""


def _seed_default_fleet(sim: SimulatorController):
    """
    Default fleet on startup = exactly two vehicles, matching the
    existing demo setup:

        V001 - Car
        V002 - Truck (heavy vehicle, staggered slightly behind V001
                      on the same route so the Overtaking Safety
                      Module has a realistic scenario to detect)
    """

    sim.add_vehicle("V001", vehicle_type="Car", speed=45, route=DEFAULT_ROUTE)
    sim.add_vehicle("V002", vehicle_type="Truck", speed=52, route=DEFAULT_ROUTE)


def _run_cli():

    sim = SimulatorController()
    _seed_default_fleet(sim)
    sim.start()

    print("SmartMove-AI Vehicle Simulator")
    print("Default fleet: V001 (Car), V002 (Truck) - already running.")
    print("Type 'help' for commands.\n")

    while True:

        try:
            raw = input("sim> ").strip()
        except (EOFError, KeyboardInterrupt):
            raw = "quit"

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]

        try:

            if cmd == "add" and len(args) >= 2:
                vehicle_id = args[0]
                vehicle_type = args[1]
                speed = float(args[2]) if len(args) >= 3 else 45
                sim.add_vehicle(vehicle_id, vehicle_type, speed)

            elif cmd == "remove" and len(args) >= 1:
                sim.remove_vehicle(args[0])

            elif cmd == "edit" and len(args) >= 3:
                sim.edit_vehicle(args[0], args[1], args[2])

            elif cmd == "list":
                sim.list_vehicles()

            elif cmd in ("start", "resume"):
                sim.start()

            elif cmd == "pause":
                sim.pause()

            elif cmd == "stop":
                sim.stop()

            elif cmd == "help":
                print(HELP_TEXT)

            elif cmd in ("quit", "exit"):
                sim.stop()
                print("[simulator] Exiting.")
                break

            else:
                print("[simulator] Unrecognized command. Type 'help' for a list.")

        except Exception as exc:
            print(f"[simulator] Command failed: {exc}")


if __name__ == "__main__":
    _run_cli()