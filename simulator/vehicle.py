"""
vehicle.py

This file defines the Vehicle class.
Each vehicle stores its current position and moves along predefined
waypoints, interpolating smoothly between them so the dashboard map
shows continuous motion rather than teleporting jumps. Also
simulates intermittent GPS loss so the backend's GPS Recovery
Engine has real signal dropouts to react to.
"""

import math
import random


class Vehicle:

    def __init__(self, vehicle_id, waypoints, vehicle_type="Car", speed=40):
        """
        Initialize a vehicle.

        vehicle_id: unique identifier, e.g. "V001"
        waypoints: list of (lat, lon) tuples describing the route
        vehicle_type: one of config.VEHICLE_TYPES (Car, Truck, etc.)
        speed: base cruising speed in km/h
        """

        self.vehicle_id = vehicle_id
        self.waypoints = waypoints
        self.vehicle_type = vehicle_type
        self.base_speed = speed
        self.speed = speed

        # Start from the first waypoint
        self.current_index = 0

        # Fraction of progress (0.0 - 1.0) between current_index and
        # current_index + 1, enabling smooth interpolated motion.
        self.segment_progress = 0.0

        self.latitude = waypoints[0][0]
        self.longitude = waypoints[0][1]

        self.heading = 0

        # GPS status simulation
        self.gps_status = "OK"
        self._gps_lost_ticks_remaining = 0

        # How much of a waypoint segment to advance per move() call,
        # roughly proportional to speed. Tuned so a full route loop
        # takes a reasonable number of ticks for a live demo.
        self._step_fraction = 0.08

    def calculate_heading(self, current, next_point):
        """
        Calculate the compass direction of travel between two
        (lat, lon) points.
        """

        lat_diff = next_point[0] - current[0]
        lon_diff = next_point[1] - current[1]

        angle = math.degrees(math.atan2(lon_diff, lat_diff))

        if angle < 0:
            angle += 360

        return round(angle, 2)

    def _interpolate(self, current, next_point, fraction):

        lat = current[0] + (next_point[0] - current[0]) * fraction
        lon = current[1] + (next_point[1] - current[1]) * fraction

        return lat, lon

    def _maybe_toggle_gps(self):
        """
        Randomly simulate GPS signal loss and recovery so the
        backend's GPS Recovery Engine has real scenarios to handle
        during a live demo. GPS loss lasts a few consecutive ticks
        once triggered, rather than flickering every tick.
        """

        if self._gps_lost_ticks_remaining > 0:

            self._gps_lost_ticks_remaining -= 1

            if self._gps_lost_ticks_remaining == 0:
                self.gps_status = "OK"

            return

        # Small chance per tick to enter a GPS-loss episode.
        if random.random() < 0.04:

            self.gps_status = "LOST"
            self._gps_lost_ticks_remaining = random.randint(3, 6)

    def move(self):
        """
        Advance the vehicle smoothly along its route, wrapping back
        to the start once the final waypoint is reached, and update
        simulated speed and GPS status.
        """

        if self.current_index >= len(self.waypoints) - 1:
            self.current_index = 0
            self.segment_progress = 0.0

        current = self.waypoints[self.current_index]
        next_point = self.waypoints[self.current_index + 1]

        self.heading = self.calculate_heading(current, next_point)

        self.segment_progress += self._step_fraction

        if self.segment_progress >= 1.0:

            self.segment_progress = 0.0
            self.current_index += 1

            if self.current_index >= len(self.waypoints) - 1:
                self.current_index = 0

            current = self.waypoints[self.current_index]
            next_point = self.waypoints[self.current_index + 1]

        self.latitude, self.longitude = self._interpolate(
            current, next_point, self.segment_progress
        )

        # Natural speed variation around the base cruising speed.
        self.speed = round(
            max(5, self.base_speed + random.uniform(-8, 8)), 1
        )

        self._maybe_toggle_gps()

    def get_data(self):
        """
        Return the current vehicle telemetry payload as published
        over MQTT.
        """

        return {
            "vehicle_id": self.vehicle_id,
            "vehicle_type": self.vehicle_type,
            "latitude": round(self.latitude, 7),
            "longitude": round(self.longitude, 7),
            "speed": self.speed,
            "heading": self.heading,
            "gps_status": self.gps_status,
        }
