"""
config.py

Stores application configuration.
"""

# -------------------------
# MQTT
# -------------------------

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "telemetry/#"


# -------------------------
# Redis
# -------------------------

REDIS_HOST = "localhost"
REDIS_PORT = 6379


# -------------------------
# PostgreSQL
# -------------------------

DB_HOST = "localhost"
DB_PORT = 5432
DB_NAME = "smartmove"
DB_USER = "postgres"
DB_PASSWORD = "password"


# -------------------------
# Paths
# -------------------------

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

AI_DIR = os.path.join(BASE_DIR, "ai")

MODEL_PATH = os.path.join(AI_DIR, "risk_model.pkl")
LABEL_ENCODER_PATH = os.path.join(AI_DIR, "label_encoder.pkl")
DATASET_PATH = os.path.join(AI_DIR, "dataset.csv")


# -------------------------
# GPS Recovery Engine
# -------------------------

# Confidence decays by this much per second of continuous GPS loss
GPS_CONFIDENCE_DECAY_PER_SEC = 0.15

# Minimum confidence floor (never fully hits 0)
GPS_CONFIDENCE_FLOOR = 0.1

# Distance (meters) beyond which snapped estimate is considered unreliable
ROAD_SNAP_MAX_DISTANCE = 150


# -------------------------
# Road Health Index
# -------------------------

ROAD_HEALTH_WEIGHTS = {
    "traffic": 0.20,
    "potholes": 0.20,
    "flood": 0.20,
    "construction": 0.15,
    "road_block": 0.15,
    "accident_history": 0.10,
}


# -------------------------
# Risk Thresholds
# -------------------------

RISK_LOW_MAX = 0.34
RISK_MEDIUM_MAX = 0.69
# anything above RISK_MEDIUM_MAX => HIGH


# -------------------------
# Zone Types
# -------------------------

ZONE_TYPES = [
    "School",
    "Hairpin",
    "Hospital",
    "Construction",
    "Flood",
    "Accident",
    "RoadBlock",
    "Bridge",
]


# -------------------------
# Road Hazard Types
# -------------------------
# Point-hazards (as opposed to zone polygons) that degrade the
# Road Health Index for vehicles passing near them.

HAZARD_TYPES = [
    "Pothole",
    "Construction",
    "Flood",
    "RoadBlock",
    "Accident",
    "SpeedBreaker",
    "OilSpill",
    "FallenTree",
    "RoadDamage",
]

# Radius (meters) within which a hazard affects a passing vehicle
HAZARD_INFLUENCE_RADIUS = 80

# Severity penalty applied to Road Health Index per hazard type
HAZARD_SEVERITY_PENALTY = {
    "Pothole": 8,
    "Construction": 15,
    "Flood": 25,
    "RoadBlock": 30,
    "Accident": 20,
    "SpeedBreaker": 5,
    "OilSpill": 18,
    "FallenTree": 22,
    "RoadDamage": 12,
}


# -------------------------
# Vehicle Fleet
# -------------------------

VEHICLE_TYPES = [
    "Car",
    "Truck",
    "Bus",
    "Lorry",
    "Tanker",
    "Container",
    "Ambulance",
    "Police",
    "Bike",
    "Auto",
]

HEAVY_VEHICLE_TYPES = ["Truck", "Bus", "Lorry", "Container", "Tanker"]

EMERGENCY_VEHICLE_TYPES = ["Ambulance", "Police"]

VEHICLE_COLORS = {
    "Car": "#2E86FF",
    "Truck": "#8B5A2B",
    "Bus": "#8B5A2B",
    "Lorry": "#8B5A2B",
    "Container": "#8B5A2B",
    "Tanker": "#8B5A2B",
    "Ambulance": "#FFFFFF",
    "Police": "#0B1F5C",
    "Bike": "#2ECC71",
    "Auto": "#F1C40F",
}


# -------------------------
# Overtaking / V2V Safety Module
# -------------------------

# Following-distance (meters) below which a heavy vehicle behind is
# considered "close enough" to be a potential overtaking threat.
OVERTAKE_PROXIMITY_THRESHOLD_M = 60

# Heading difference (degrees) below which two vehicles are
# considered to be travelling in a comparable direction (same lane
# of travel / same road).
OVERTAKE_HEADING_TOLERANCE_DEG = 25

# Relative speed (km/h) above which the vehicle behind is considered
# to be closing in fast enough to signal an overtaking maneuver.
OVERTAKE_CLOSING_SPEED_THRESHOLD_KMH = 8