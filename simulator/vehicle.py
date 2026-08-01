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

        self.current_index = 0
        self.segment_progress = 0.0

        self.latitude = waypoints[0][0]
        self.longitude = waypoints[0][1]

        self.heading = 0

        self.gps_status = "OK"
        self._gps_lost_ticks_remaining = 0

        # -----------------------------------------------------
        # DEMO MODE
        # Increased movement speed for a 1-minute presentation.
        # -----------------------------------------------------
        self._step_fraction = 0.60

    def calculate_heading(self, current, next_point):

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

        if self._gps_lost_ticks_remaining > 0:

            self._gps_lost_ticks_remaining -= 1

            if self._gps_lost_ticks_remaining == 0:
                self.gps_status = "OK"

            return

        # Higher probability for demo
        if random.random() < 0.12:

            self.gps_status = "LOST"

            # Faster recovery
            self._gps_lost_ticks_remaining = random.randint(2, 3)

    def move(self):

        if self.current_index >= len(self.waypoints) - 1:
            self.current_index = 0
            self.segment_progress = 0.0

        current = self.waypoints[self.current_index]
        next_point = self.waypoints[self.current_index + 1]

        self.heading = self.calculate_heading(current, next_point)

        # Faster movement
        self.segment_progress += self._step_fraction

        while self.segment_progress >= 1.0:

            self.segment_progress -= 1.0

            self.current_index += 1

            if self.current_index >= len(self.waypoints) - 1:
                self.current_index = 0

            current = self.waypoints[self.current_index]
            next_point = self.waypoints[self.current_index + 1]

            self.heading = self.calculate_heading(current, next_point)

        self.latitude, self.longitude = self._interpolate(
            current,
            next_point,
            self.segment_progress
        )

        # Larger speed variation for demo
        self.speed = round(
            max(
                20,
                self.base_speed + random.uniform(-15, 20)
            ),
            1
        )

        self._maybe_toggle_gps()

    def get_data(self):

        return {
            "vehicle_id": self.vehicle_id,
            "vehicle_type": self.vehicle_type,
            "latitude": round(self.latitude, 7),
            "longitude": round(self.longitude, 7),
            "speed": self.speed,
            "heading": self.heading,
            "gps_status": self.gps_status,
        }