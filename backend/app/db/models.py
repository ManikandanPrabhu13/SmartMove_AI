"""
models.py

Database tables.
"""

from sqlalchemy import (
    Column,
    Integer,
    Float,
    String,
    DateTime,
    Text,
    Boolean
)

from sqlalchemy.orm import declarative_base

from datetime import datetime

Base = declarative_base()


class VehicleHistory(Base):

    __tablename__ = "vehicle_history"

    id = Column(Integer, primary_key=True)

    vehicle_id = Column(String)

    latitude = Column(Float)

    longitude = Column(Float)

    speed = Column(Float)

    heading = Column(Float)

    recorded_at = Column(
        DateTime,
        default=datetime.utcnow
    )


class DangerZone(Base):

    __tablename__ = "danger_zones"

    id = Column(Integer, primary_key=True)

    zone_type = Column(String)

    # Legacy circle definition (kept for backward compatibility).
    # If polygon_geojson is populated, that takes precedence.
    latitude = Column(Float, nullable=True)

    longitude = Column(Float, nullable=True)

    radius = Column(Float, nullable=True)

    severity = Column(String)

    # JSON-encoded list of [lat, lon] vertices, e.g.
    # "[[13.08,80.27],[13.081,80.271],[13.082,80.2705]]"
    # Populated for true polygon zones. NULL means "circle zone,
    # auto-converted to a polygon at runtime by geofence.py".
    polygon_geojson = Column(Text, nullable=True)


class Alert(Base):

    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)

    vehicle_id = Column(String)

    alert_type = Column(String)

    severity = Column(String)

    message = Column(String, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )


class RiskLog(Base):
    """
    Stores every AI Risk Prediction pipeline result.
    Used for the dashboard, driver scoring history, and audit trail.
    """

    __tablename__ = "risk_logs"

    id = Column(Integer, primary_key=True)

    vehicle_id = Column(String)

    vehicle_type = Column(String)

    zone_type = Column(String, nullable=True)

    gps_lost = Column(Boolean, default=False)

    gps_confidence = Column(Float)

    road_health_score = Column(Float)

    distance_to_polygon = Column(Float, nullable=True)

    risk_probability = Column(Float)

    driver_score = Column(Float)

    risk_category = Column(String)

    reason = Column(String, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )