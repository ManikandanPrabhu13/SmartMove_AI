# SmartMove AI

SmartMove AI is a mini-project that tries to simulate a real-time vehicle safety and traffic risk monitoring system — the kind of thing you'd see in a fleet-tracking or smart-city dashboard. It takes live vehicle location data (simulated), runs it through a small pipeline of checks (GPS loss, danger zones, road conditions), predicts a risk level using a trained ML model, and shows everything live on a map dashboard.

Built as part of a college project to explore how MQTT, FastAPI, Redis, and Machine Learning can be combined into one working real-time system.

---

## Table of Contents

- [What it does](#what-it-does)
- [Technology Stack](#technology-stack)
- [How the pipeline works](#how-the-pipeline-works)
- [Algorithms Used](#algorithms-used)
- [Project Structure](#project-structure)
- [How to Run](#how-to-run)
- [API Endpoints](#api-endpoints)
- [Config](#config)

---

## What it does

- Simulates a small fleet of vehicles (car, truck, bus, ambulance, etc.) moving along routes and publishing GPS + speed data over MQTT.
- Backend picks up each update and runs it through a decision pipeline:
  - checks if GPS signal is lost and estimates position anyway
  - checks if vehicle is inside a danger zone (school, hairpin, flood zone, etc.)
  - checks road condition/hazards nearby
  - feeds all that into a trained ML model to predict risk (LOW / MEDIUM / HIGH)
  - checks if a heavy vehicle is trying to overtake dangerously
- Every result gets pushed live to a dashboard (map + alerts panel) using WebSockets.
- Also has an "emergency" system — brake failure, accident, engine failure events can be triggered and instantly shown as alerts.

Basically it's trying to answer: *"can we predict when a vehicle is in a risky situation, in real time, and explain why?"*

---

## Technology Stack

### Backend
- **Python + FastAPI** – main backend framework, handles all APIs
- **Uvicorn** – runs the FastAPI server
- **MQTT (paho-mqtt)** – used for sending vehicle telemetry (like an IoT device would)
- **WebSockets** – used to push live updates to the dashboard without refreshing
- **Redis** – stores live vehicle data / cache (so we don't hit the DB every time)
- **PostgreSQL + SQLAlchemy** – stores alert history and risk logs for later reference
- **Jinja2** – used to render the dashboard HTML page

### Machine Learning
- **scikit-learn** – trained a `RandomForestClassifier` to predict risk level
- **pandas / NumPy** – for building the dataset and features
- **joblib** – to save/load the trained model (.pkl files)
- **Shapely** – for all the geometry stuff (checking if a point is inside a polygon zone, snapping to nearest road, etc.)

### Frontend / Dashboard
- **Leaflet.js** – for the live map showing vehicles
- **Chart.js** – for some basic stats/graphs on the dashboard
- **Font Awesome** – icons
- Plain HTML/CSS/JS (no frontend framework, kept it simple)

### Simulator
- A separate Python script that fakes a fleet of moving vehicles and publishes their data over MQTT, including random GPS dropouts and occasional emergency events, so the backend has something realistic to react to.

---

## How the pipeline works

Every time the simulator sends a new location update, this is roughly what happens on the backend:

```
Simulator (publishes MQTT) 
        ↓
MQTT handler receives it
        ↓
Decision Engine runs, step by step:
    1. GPS Recovery      → is GPS lost? estimate position if needed
    2. Geofencing         → is vehicle inside a danger zone?
    3. Road Health         → how bad is the road/hazards nearby?
    4. Feature Builder     → combine all of the above into one feature row
    5. ML Model             → predict risk: LOW / MEDIUM / HIGH
    6. Overtaking Check     → is a heavy vehicle overtaking unsafely?
    7. Alerts                → raise alerts based on all of the above
        ↓
Save to Redis + Postgres
        ↓
Broadcast over WebSocket → Dashboard updates live
```

Nothing runs on a timer/loop — it's all triggered by the incoming MQTT message, so it's event-driven.

---

## Algorithms Used

### 1. Risk Prediction — Random Forest
This is the main ML part. A `RandomForestClassifier` (200 trees, max depth 12) takes 8 features:

```
vehicle_type, speed, heading, zone_type, gps_confidence,
road_health, distance_to_polygon, hour_of_day
```

and predicts LOW / MEDIUM / HIGH risk.

Since we didn't have real accident data, the training dataset (6000 rows) was generated synthetically — wrote a scoring function based on common sense rules (e.g. higher speed = higher risk, being inside a school zone = higher risk, poor GPS confidence = higher risk, late night = higher risk) and used that to label the data before training.

The model also returns a plain-English `reason` (like "Overspeed, Approaching School Zone") so the risk score isn't just a random number — you can actually see why it flagged something. Did this by checking which feature values crossed certain thresholds after prediction.

### 2. GPS Recovery (Dead Reckoning)
When GPS signal is "lost" (simulated), the system doesn't just stop tracking the vehicle. Instead:
- estimates the new position using the last known position + speed + heading + time elapsed (basic physics — distance = speed × time, split into north/east direction using the heading angle)
- snaps that estimated point onto the nearest known road (using Shapely) so it doesn't end up somewhere impossible like inside a building
- confidence score keeps dropping the longer GPS stays lost, and resets back to 1.0 once GPS comes back

### 3. Geofencing (Point-in-Polygon)
Used Shapely's polygon logic to properly check if a vehicle's coordinates fall inside a zone (school zone, hairpin bend, flood zone, etc.) instead of just doing a rough radius check. Also handles the case where a zone is defined as a circle (lat/lon/radius) by converting it into an approximate polygon first.

If the vehicle isn't inside any zone, it also calculates the distance to the nearest zone boundary, which is one of the features fed into the ML model.

### 4. Road Health Score
A simple scoring formula, starts at 100 and subtracts penalties:
- traffic congestion penalty
- penalty for every nearby hazard (pothole, flood, oil spill, etc.), where closer hazards reduce the score more than far away ones (distance-based falloff)

Final score is clamped between 0–100.

### 5. Overtaking / Heavy Vehicle Safety Check
This one checks if a truck/bus/lorry behind another vehicle is attempting an unsafe overtake:
- distance between the two vehicles (using haversine formula)
- both vehicles roughly heading the same direction (same lane/road)
- confirms the heavy vehicle is actually behind (using bearing calculation)
- if it's closing in fast (relative speed), it raises an "unsafe overtaking" + "blind spot" warning

### 6. Alert System
All the modules above (GPS, geofence, road health, ML risk, overtaking) send their findings to one central alert function. This function saves the alert to Redis (for quick access on dashboard load), saves it to Postgres (for history), and broadcasts it over WebSocket — so every alert goes through the same path no matter which module raised it.

---

## Project Structure

```
SmartMovee-AI/
├── backend/
│   ├── app/
│   │   ├── ai/                  # dataset, training script, saved model
│   │   │   ├── train_model.py
│   │   │   ├── dataset.csv
│   │   │   ├── risk_model.pkl
│   │   │   └── label_encoder.pkl
│   │   ├── api/                 # all the API routes
│   │   │   ├── vehicles.py
│   │   │   ├── zones.py
│   │   │   ├── hazards.py
│   │   │   ├── emergency.py
│   │   │   ├── websocket.py
│   │   │   └── dashboard.py
│   │   ├── engine/               # the actual logic/pipeline
│   │   │   ├── decision_engine.py
│   │   │   ├── geofence.py
│   │   │   ├── gps_monitor.py
│   │   │   ├── road_health.py
│   │   │   ├── feature_builder.py
│   │   │   ├── ml_model.py
│   │   │   ├── risk.py
│   │   │   ├── overtaking.py
│   │   │   └── alerts.py
│   │   ├── db/                   # database models
│   │   ├── mqtt/                 # mqtt client + handlers
│   │   ├── ws/                   # websocket manager
│   │   ├── static/                # dashboard js/css
│   │   ├── templates/             # dashboard html
│   │   ├── config.py
│   │   ├── redis_client.py
│   │   └── main.py                # entry point
│   └── requirements.txt
└── simulator/
    ├── vehicle.py                 # simulated vehicle movement
    ├── publisher.py                # publishes fake telemetry over MQTT
    ├── triggers.py                 # emergency event generators
    └── emergency.py                # publishes emergency events
```

---

## How to Run

### You'll need:
- Python 3.10+
- MQTT broker running locally (e.g. Mosquitto) — port 1883
- Redis running locally — port 6379
- PostgreSQL running locally (database name: `smartmove`)

### Steps

1. Install dependencies:
```bash
pip install -r backend/requirements.txt
```

2. (Optional) Train the model manually — it'll auto-train on first run anyway if you skip this:
```bash
python -m backend.app.ai.train_model
```

3. Start the backend:
```bash
uvicorn backend.app.main:app --reload
```
Dashboard will be at `http://localhost:8000/dashboard`
API docs at `http://localhost:8000/docs`

4. In a separate terminal, run the simulator to start generating fake vehicle data:
```bash
cd simulator
python publisher.py
```
It gives you a `sim>` prompt where you can add/remove/edit vehicles while it's running.

---

## API Endpoints

| Endpoint | What it does |
|---|---|
| `GET /vehicles/` | list of all vehicles + their current risk |
| `GET /vehicles/{id}` | one vehicle's data + risk |
| `GET /zones/` | manage danger zones |
| `GET /hazards/` | manage road hazards |
| `POST /emergency/broadcast` | manually trigger an emergency alert |
| `WS /ws/live` | live feed used by the dashboard |
| `GET /dashboard` | the actual dashboard page |
| `GET /dashboard/summary` | summary stats for dashboard |

---
