/*
 * app.js
 *
 * SmartMove AI — Traffic Command Center controller.
 *
 * Data flow:
 *   1. On load: fetch /dashboard/summary once to hydrate instantly.
 *   2. Open a WebSocket to /ws/live; every telemetry/emergency
 *      broadcast from the backend updates state in real time.
 *   3. A lightweight polling fallback re-fetches /dashboard/summary
 *      every 5s in case the WebSocket connection drops.
 *
 * The backend pipeline (decision_engine.py) already produces GPS
 * recovery, geofencing, road health, AI risk, and heavy-vehicle
 * overtaking alerts. This controller additionally derives a live
 * "nearby vehicle" relationship table and a radar-style AI Traffic
 * Visualization purely from vehicle positions/headings, so the
 * Command Center reads as a cohesive V2V safety view even with a
 * two-vehicle demo fleet.
 */

const HEAVY_VEHICLE_TYPES = new Set(["Truck", "Bus", "Lorry", "Container", "Tanker"]);

// Mirrors backend/app/config.py overtaking thresholds, kept in
// sync for consistent client-side relationship classification.
const OVERTAKE_PROXIMITY_THRESHOLD_M = 60;
const OVERTAKE_HEADING_TOLERANCE_DEG = 25;
const OVERTAKE_CLOSING_SPEED_THRESHOLD_KMH = 8;
const BLIND_SPOT_DISTANCE_M = 30;
const TRAFFIC_VIEW_RANGE_M = 150;

const state = {
    vehicles: {},         // vehicle_id -> latest enriched vehicle dict
    zones: [],
    hazards: [],
    alerts: [],            // newest first
    selectedVehicleId: null,
    emergencyCount: 0,
    speedHistory: {},      // vehicle_id -> array of recent speeds (for chart)
    alertFrequency: {},    // alert_type -> count
    zoneHistory: {},       // vehicle_id -> { current, previous }
};

const MAX_ALERTS_DISPLAYED = 60;
const MAX_SPEED_HISTORY_POINTS = 30;

let ws = null;
let wsConnected = false;

let chartSpeed, chartRisk, chartRoadHealth, chartAlertFreq;

const tvVehicleEls = {}; // vehicle_id -> SVG <g> element in the traffic view


// ---------------------------------------------------------
// Bootstrapping
// ---------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {

    SmartMoveMap.init("map", [13.0835, 80.2715], 15);
    SmartMoveMap.setVehicleClickHandler(selectVehicle);
    renderMapLegend();

    setupTrafficView();
    initCharts();
    startClock();

    fetchSummary().then(() => {
        renderAll();
    });

    connectWebSocket();

    setInterval(() => {
        if (!wsConnected) {
            fetchSummary().then(renderAll);
        }
    }, 5000);
});


function renderMapLegend() {

    const legend = document.getElementById("mapLegend");

    const items = [
        ["Car", "#2E86FF"],
        ["Heavy Vehicle", "#8B5A2B"],
        ["Ambulance", "#FFFFFF"],
        ["Police", "#0B1F5C"],
        ["Bike", "#2ECC71"],
        ["Auto", "#F1C40F"],
    ];

    legend.innerHTML = items.map(([label, color]) => `
        <span><span class="swatch" style="background:${color}"></span>${label}</span>
    `).join("");
}


function startClock() {

    const clockEl = document.getElementById("clock");

    setInterval(() => {
        const now = new Date();
        clockEl.textContent = now.toLocaleTimeString("en-GB");
    }, 1000);
}


// ---------------------------------------------------------
// Data fetching
// ---------------------------------------------------------

async function fetchSummary() {

    try {

        const res = await fetch("/dashboard/summary");
        const data = await res.json();

        data.vehicles.forEach((v) => {
            state.vehicles[v.vehicle_id] = v;
            _trackZoneHistory(v.vehicle_id, v.risk?.zone?.zone_type || null);
        });

        state.zones = data.zones || [];
        state.hazards = data.hazards || [];
        state.alerts = data.alerts || [];

        if (!state.selectedVehicleId) {
            const firstId = Object.keys(state.vehicles)[0];
            if (firstId) state.selectedVehicleId = firstId;
        }

    } catch (err) {
        console.error("Failed to fetch dashboard summary:", err);
    }
}


// ---------------------------------------------------------
// WebSocket live connection
// ---------------------------------------------------------

function connectWebSocket() {

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws/live`;

    ws = new WebSocket(url);

    ws.onopen = () => {
        wsConnected = true;
        _setLive(true);
    };

    ws.onclose = () => {
        wsConnected = false;
        _setLive(false);
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = () => {
        wsConnected = false;
        _setLive(false);
    };

    ws.onmessage = (event) => {

        try {
            const payload = JSON.parse(event.data);
            handleLiveMessage(payload);

        } catch (err) {
            console.error("Failed to parse WebSocket message:", err);
        }
    };
}


function _setLive(isLive) {

    const el = document.getElementById("liveIndicator");
    if (!el) return;

    el.classList.toggle("offline", !isLive);

    const textEl = document.getElementById("liveIndicatorText");
    if (textEl) textEl.textContent = isLive ? "LIVE" : "RECONNECTING";
}


function handleLiveMessage(payload) {

    if (payload.type === "telemetry") {

        const result = payload.data;

        const existing = state.vehicles[result.vehicle_id] || {};

        state.vehicles[result.vehicle_id] = {
            ...existing,
            vehicle_id: result.vehicle_id,
            vehicle_type: result.vehicle_type,
            latitude: result.latitude,
            longitude: result.longitude,
            heading: result.heading,
            speed: result.speed,
            gps_status: result.gps.gps_lost ? "LOST" : "OK",
            risk: {
                gps: result.gps,
                zone: result.zone,
                road_health: result.road_health,
                ai: result.ai,
            },
        };

        _trackZoneHistory(result.vehicle_id, result.zone?.zone_type || null);
        _trackSpeedHistory(result.vehicle_id, result.speed);

        if (!state.selectedVehicleId) {
            state.selectedVehicleId = result.vehicle_id;
        }

        if (result.alerts && result.alerts.length > 0) {
            result.alerts.forEach((alert) => addAlert(alert));
        }

        renderAll();

    } else if (payload.type === "emergency") {

        state.emergencyCount += 1;
        addAlert(payload.data);
        renderAll();
    }
}


function _trackZoneHistory(vehicleId, zoneType) {

    if (!state.zoneHistory[vehicleId]) {
        state.zoneHistory[vehicleId] = { current: null, previous: null };
    }

    const hist = state.zoneHistory[vehicleId];

    if (zoneType !== hist.current) {
        hist.previous = hist.current;
        hist.current = zoneType;
    }
}


function _trackSpeedHistory(vehicleId, speed) {

    if (!state.speedHistory[vehicleId]) {
        state.speedHistory[vehicleId] = [];
    }

    state.speedHistory[vehicleId].push(speed);

    if (state.speedHistory[vehicleId].length > MAX_SPEED_HISTORY_POINTS) {
        state.speedHistory[vehicleId].shift();
    }
}


function addAlert(alert) {

    state.alerts.unshift(alert);

    if (state.alerts.length > MAX_ALERTS_DISPLAYED) {
        state.alerts.length = MAX_ALERTS_DISPLAYED;
    }

    const type = alert.alert_type || "Unknown";
    state.alertFrequency[type] = (state.alertFrequency[type] || 0) + 1;
}


// ---------------------------------------------------------
// Geometry helpers (mirrors backend/app/engine/geofence.py and
// backend/app/engine/overtaking.py so the client-side "nearby
// vehicle" relationships and AI Traffic Visualization stay
// consistent with the server's own overtaking safety module).
// ---------------------------------------------------------

function haversineDistance(lat1, lon1, lat2, lon2) {

    const R = 6371000;
    const toRad = (d) => (d * Math.PI) / 180;

    const dLat = toRad(lat2 - lat1);
    const dLon = toRad(lon2 - lon1);

    const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;

    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

    return R * c;
}

function headingDiff(h1, h2) {
    const diff = Math.abs(h1 - h2) % 360;
    return diff > 180 ? 360 - diff : diff;
}

function relativeBearing(from, to) {

    const toRad = (d) => (d * Math.PI) / 180;

    const lat1 = toRad(from.latitude);
    const lat2 = toRad(to.latitude);
    const dLon = toRad(to.longitude - from.longitude);

    const x = Math.sin(dLon) * Math.cos(lat2);
    const y =
        Math.cos(lat1) * Math.sin(lat2) -
        Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);

    const bearing = (Math.atan2(x, y) * 180) / Math.PI;

    return (bearing + 360) % 360;
}

/**
 * Classify the relationship between the focused "subject" vehicle
 * and one nearby "other" vehicle: distance, closing speed, lane
 * alignment, blind-spot risk, and an overtaking advisory.
 */
function classifyRelation(subject, other) {

    const distance = haversineDistance(
        subject.latitude, subject.longitude,
        other.latitude, other.longitude
    );

    const relSpeed = (other.speed || 0) - (subject.speed || 0);

    const bearingToOther = relativeBearing(subject, other);
    const oppositeHeading = ((subject.heading || 0) + 180) % 360;

    const isBehind = headingDiff(bearingToOther, oppositeHeading) < 60;
    const headingAlign = headingDiff(subject.heading || 0, other.heading || 0);
    const sameLane = headingAlign < OVERTAKE_HEADING_TOLERANCE_DEG;

    const isHeavy = HEAVY_VEHICLE_TYPES.has(other.vehicle_type);
    const blindSpot = isBehind && sameLane && distance < BLIND_SPOT_DISTANCE_M;

    let statusKey = "clear";
    let statusLabel = "Clear";
    let recommendation = "Maintain Lane";

    if (!isHeavy) {
        statusKey = "clear"; statusLabel = "Clear"; recommendation = "Maintain Lane";
    } else if (!sameLane) {
        statusKey = "clear"; statusLabel = "Different Lane"; recommendation = "Maintain Lane";
    } else if (!isBehind) {
        statusKey = "clear"; statusLabel = "Ahead"; recommendation = "Maintain Speed";
    } else if (distance > OVERTAKE_PROXIMITY_THRESHOLD_M) {
        statusKey = "clear"; statusLabel = "Clear"; recommendation = "Maintain Lane";
    } else if (blindSpot) {
        statusKey = "blindspot"; statusLabel = "Blind Spot Warning"; recommendation = "Do Not Change Lane";
    } else if (relSpeed >= OVERTAKE_CLOSING_SPEED_THRESHOLD_KMH) {
        statusKey = "unsafe"; statusLabel = "Unsafe Overtake"; recommendation = "Reduce Speed";
    } else if (relSpeed <= -3) {
        statusKey = "safe"; statusLabel = "Safe To Overtake"; recommendation = "Proceed With Caution";
    } else {
        statusKey = "behind"; statusLabel = "Heavy Vehicle Behind"; recommendation = "Maintain Lane";
    }

    // Relative bearing to `other`, expressed relative to the
    // subject's own heading (0 = directly ahead), used to place
    // the vehicle in the radar view / infer left-right side.
    const relBearing = (bearingToOther - (subject.heading || 0) + 360) % 360;

    return {
        vehicleId: other.vehicle_id,
        vehicleType: other.vehicle_type,
        distance,
        relSpeed,
        sameLane,
        isBehind,
        isHeavy,
        blindSpot,
        statusKey,
        statusLabel,
        recommendation,
        relBearing,
    };
}

function computeNearby(subjectId) {

    const subject = state.vehicles[subjectId];
    if (!subject) return [];

    return Object.values(state.vehicles)
        .filter((v) => v.vehicle_id !== subjectId)
        .map((other) => classifyRelation(subject, other))
        .sort((a, b) => a.distance - b.distance);
}


// ---------------------------------------------------------
// Rendering — top level
// ---------------------------------------------------------

function renderAll() {

    renderTopMetrics();
    renderVehicleSelector();
    renderMapLayers();
    renderTrafficView();
    renderNearbyTable();
    renderDangerVehicles();
    renderExplainableAi();
    renderVehicleInfo();
    renderAlertFeed();
    renderCharts();
}


function renderTopMetrics() {

    const vehicles = Object.values(state.vehicles);

    document.getElementById("connectedVehicles").textContent = vehicles.length;
    document.getElementById("activeAlertsCount").textContent = state.alerts.length;
    document.getElementById("metricActiveAlerts").textContent = state.alerts.length;
    document.getElementById("metricEmergencyCount").textContent = state.emergencyCount;

    let highestRisk = 0;
    let highestRiskVehicle = null;

    vehicles.forEach((v) => {

        const prob = v.risk && v.risk.ai ? v.risk.ai.risk_probability : 0;

        if (prob >= highestRisk) {
            highestRisk = prob;
            highestRiskVehicle = v;
        }
    });

    document.getElementById("metricHighestRisk").textContent =
        Math.round(highestRisk * 100) + "%";

    if (highestRiskVehicle) {

        document.getElementById("metricSpeed").textContent =
            Math.round(highestRiskVehicle.speed || 0) + " km/h";

        document.getElementById("metricDriverScore").textContent =
            highestRiskVehicle.risk?.ai?.driver_score ?? "--";

        document.getElementById("metricRoadHealth").textContent =
            Math.round(highestRiskVehicle.risk?.road_health?.score ?? 0);

        document.getElementById("metricGpsConfidence").textContent =
            Math.round((highestRiskVehicle.risk?.gps?.confidence ?? 1) * 100) + "%";
    }
}


function renderVehicleSelector() {

    const wrap = document.getElementById("selectorTabs");
    const vehicles = Object.values(state.vehicles).sort((a, b) =>
        a.vehicle_id.localeCompare(b.vehicle_id)
    );

    if (vehicles.length === 0) {
        wrap.innerHTML = `<span class="empty-hint">Waiting for telemetry…</span>`;
        return;
    }

    wrap.innerHTML = vehicles.map((v) => {

        const isActive = v.vehicle_id === state.selectedVehicleId;
        const risk = v.risk?.ai?.risk_category || "LOW";
        const icon = HEAVY_VEHICLE_TYPES.has(v.vehicle_type) ? "fa-truck" : "fa-car-side";

        return `
            <button class="selector-tab ${isActive ? "active" : ""}" onclick="selectVehicle('${v.vehicle_id}')">
                <i class="fa-solid ${icon}"></i>
                ${v.vehicle_id} · ${v.vehicle_type || "-"}
                <span class="risk-dot ${risk}"></span>
            </button>
        `;
    }).join("");
}


function selectVehicle(vehicleId) {

    state.selectedVehicleId = vehicleId;
    renderAll();

    const vehicle = state.vehicles[vehicleId];

    if (vehicle) {
        SmartMoveMap.updatePopup(vehicleId, _buildPopupHtml(vehicle));
    }
}


// ---------------------------------------------------------
// Map
// ---------------------------------------------------------

function renderMapLayers() {

    if (state.zones.length) {
        SmartMoveMap.drawZones(state.zones);
    }

    if (state.hazards.length) {
        SmartMoveMap.drawHazards(state.hazards);
    }

    Object.values(state.vehicles).forEach((vehicle) => {
        SmartMoveMap.upsertVehicle(vehicle);
    });

    const selected = state.vehicles[state.selectedVehicleId];

    if (selected) {
        SmartMoveMap.updatePopup(state.selectedVehicleId, _buildPopupHtml(selected));
        SmartMoveMap.highlightActiveZone(selected.risk?.zone?.zone_type || null);
    }

    _renderActiveZoneStrip(selected);
    _renderMapNearbyOverlay(selected);
}


/**
 * Compact floating readout on the map itself: the nearest other
 * active vehicle to the currently focused vehicle, with distance
 * and relationship status. Makes the map a "hybrid" view rather
 * than markers alone, without duplicating the full Nearby Vehicles
 * table in the center panel.
 */
function _renderMapNearbyOverlay(subject) {

    const body = document.getElementById("mapNearbyBody");
    if (!body) return;

    if (!subject) {
        body.innerHTML = `<span class="empty-hint">No vehicle selected.</span>`;
        return;
    }

    const relations = computeNearby(subject.vehicle_id);

    if (relations.length === 0) {
        body.innerHTML = `<span class="empty-hint">No nearby vehicles.</span>`;
        return;
    }

    body.innerHTML = relations.slice(0, 3).map((rel) => `
        <div class="overlay-vehicle-row">
            <span>${rel.vehicleId} · ${rel.vehicleType || "-"}</span>
            <b>${Math.round(rel.distance)}m</b>
        </div>
        <div class="overlay-vehicle-row">
            <span class="status-pill ${rel.statusKey}" style="font-size:0.62rem;padding:1px 7px;">${rel.statusLabel}</span>
            <b>${rel.relSpeed >= 0 ? "+" : ""}${Math.round(rel.relSpeed)} km/h</b>
        </div>
    `).join("");
}


function _renderActiveZoneStrip(vehicle) {

    const strip = document.getElementById("activeZoneStrip");
    const label = document.getElementById("activeZoneLabel");

    const zoneType = vehicle?.risk?.zone?.zone_type;

    label.textContent = zoneType || "None";
    strip.classList.toggle("none", !zoneType);
}


function _buildPopupHtml(vehicle) {

    const risk = vehicle.risk || {};
    const ai = risk.ai || {};
    const gps = risk.gps || {};
    const zone = risk.zone || {};

    const nearby = computeNearby(vehicle.vehicle_id);
    const threat = nearby.find((n) => n.statusKey === "unsafe" || n.statusKey === "blindspot") || nearby[0];

    return `
        <div class="vehicle-popup">
            <h3 class="popup-id">${vehicle.vehicle_id}</h3>
            <div class="popup-row"><span>Type</span><b>${vehicle.vehicle_type || "-"}</b></div>
            <div class="popup-row"><span>Speed</span><b>${Math.round(vehicle.speed || 0)} km/h</b></div>
            <div class="popup-row"><span>Heading</span><b>${Math.round(vehicle.heading || 0)}°</b></div>
            <div class="popup-row"><span>Road Health</span><b>${Math.round(risk.road_health?.score ?? 0)}</b></div>
            <div class="popup-row"><span>AI Risk</span><b>${Math.round((ai.risk_probability ?? 0) * 100)}%</b></div>
            <div class="popup-row"><span>Driver Score</span><b>${ai.driver_score ?? "--"}</b></div>
            <div class="popup-row"><span>GPS Confidence</span><b>${Math.round((gps.confidence ?? 1) * 100)}%</b></div>
            <div class="popup-row"><span>Zone</span><b>${zone.zone_type || "None"}</b></div>
            <div class="popup-row"><span>Overtake Status</span><b>${threat ? threat.statusLabel : "Clear"}</b></div>
            <div class="popup-row"><span>Recommendation</span><b>${threat ? threat.recommendation : _recommendationFor(ai)}</b></div>
        </div>
    `;
}


// ---------------------------------------------------------
// AI Traffic Visualization (center panel radar view)
// ---------------------------------------------------------

function setupTrafficView() {

    const svg = document.getElementById("trafficView");
    const cx = 160, cy = 160;

    let chrome = `
        <g class="tv-chrome">
            <circle class="tv-ring" cx="${cx}" cy="${cy}" r="43"></circle>
            <circle class="tv-ring" cx="${cx}" cy="${cy}" r="86"></circle>
            <circle class="tv-ring" cx="${cx}" cy="${cy}" r="130"></circle>
            <line class="tv-axis" x1="${cx}" y1="30" x2="${cx}" y2="290"></line>
            <line class="tv-axis" x1="30" y1="${cy}" x2="290" y2="${cy}"></line>
            <text class="tv-range-label" x="${cx + 4}" y="${cy - 39}">50m</text>
            <text class="tv-range-label" x="${cx + 4}" y="${cy - 82}">100m</text>
            <text class="tv-range-label" x="${cx + 4}" y="${cy - 126}">150m</text>
        </g>
        <g class="tv-subject" transform="translate(${cx},${cy})">
            <circle class="tv-subject-glow" r="20"></circle>
            <polygon class="tv-subject-body" points="0,-11 9,10 0,5 -9,10"></polygon>
            <text class="tv-subject-label" text-anchor="middle" y="30">SUBJECT</text>
        </g>
        <g id="tvVehicles"></g>
    `;

    svg.innerHTML = chrome;
}


function _vehicleShapePoints(vehicleType) {

    if (HEAVY_VEHICLE_TYPES.has(vehicleType)) {
        // Larger rectangle silhouette for heavy vehicles.
        return { tag: "rect", attrs: { x: -8, y: -14, width: 16, height: 28, rx: 2 } };
    }

    if (vehicleType === "Bike" || vehicleType === "Auto") {
        return { tag: "polygon", attrs: { points: "0,-9 6,9 0,4 -6,9" } };
    }

    return { tag: "rect", attrs: { x: -6, y: -10, width: 12, height: 20, rx: 3 } };
}


function renderTrafficView() {

    const subjectId = state.selectedVehicleId;
    const subject = state.vehicles[subjectId];
    const group = document.getElementById("tvVehicles");
    const label = document.getElementById("trafficSubjectLabel");
    const banner = document.getElementById("overtakeBanner");
    const bannerText = document.getElementById("overtakeBannerText");

    if (!subject || !group) {
        if (label) label.textContent = "—";
        if (banner) banner.style.display = "none";
        return;
    }

    label.textContent = `${subject.vehicle_id} · ${subject.vehicle_type || "-"} · ${Math.round(subject.speed || 0)} km/h`;

    const relations = computeNearby(subjectId);
    const seen = new Set();

    relations.forEach((rel) => {

        seen.add(rel.vehicleId);

        const r = Math.min(130, Math.max(20, (rel.distance / TRAFFIC_VIEW_RANGE_M) * 130));
        const angleRad = (rel.relBearing * Math.PI) / 180;

        const x = 160 + r * Math.sin(angleRad);
        const y = 160 - r * Math.cos(angleRad);

        const isDanger = rel.statusKey === "unsafe" || rel.statusKey === "blindspot";
        const color = VEHICLE_COLOR(rel.vehicleType);

        let el = tvVehicleEls[rel.vehicleId];

        if (!el) {

            const shape = _vehicleShapePoints(rel.vehicleType);
            const shapeAttrs = Object.entries(shape.attrs)
                .map(([k, v]) => `${k}="${v}"`).join(" ");

            el = document.createElementNS("http://www.w3.org/2000/svg", "g");
            el.setAttribute("class", "tv-vehicle");
            el.innerHTML = `
                <circle class="tv-blindspot-ring" r="14" fill="none" stroke="#ff3b5c" stroke-width="1.5"></circle>
                <${shape.tag} class="tv-vehicle-body" ${shapeAttrs} fill="${color}"></${shape.tag}>
                <text class="tv-vehicle-label" text-anchor="middle" y="22"></text>
            `;
            group.appendChild(el);
            tvVehicleEls[rel.vehicleId] = el;
        }

        el.classList.toggle("danger", isDanger);
        el.classList.toggle("blindspot", rel.blindSpot);
        el.setAttribute("transform", `translate(${x},${y})`);
        el.querySelector(".tv-vehicle-label").textContent =
            `${rel.vehicleId} (${Math.round(rel.distance)}m)`;
    });

    // Remove markers for vehicles no longer present.
    Object.keys(tvVehicleEls).forEach((id) => {
        if (!seen.has(id)) {
            tvVehicleEls[id].remove();
            delete tvVehicleEls[id];
        }
    });

    const threat = relations.find((r) => r.statusKey === "unsafe" || r.statusKey === "blindspot");

    if (threat && banner) {
        banner.style.display = "flex";
        bannerText.textContent =
            `${threat.statusLabel}: ${threat.vehicleId} — ${threat.recommendation}`;
    } else if (banner) {
        banner.style.display = "none";
    }
}


function VEHICLE_COLOR(vehicleType) {

    const colors = {
        Car: "#2E86FF", Truck: "#8B5A2B", Bus: "#8B5A2B", Lorry: "#8B5A2B",
        Container: "#8B5A2B", Tanker: "#8B5A2B", Ambulance: "#FFFFFF",
        Police: "#0B1F5C", Bike: "#2ECC71", Auto: "#F1C40F",
    };

    return colors[vehicleType] || "#33e0ff";
}


// ---------------------------------------------------------
// Nearby vehicle panel
// ---------------------------------------------------------

function renderNearbyTable() {

    const tbody = document.getElementById("nearbyTableBody");
    const relations = computeNearby(state.selectedVehicleId);

    if (!state.selectedVehicleId || relations.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-hint">No nearby vehicles detected.</td></tr>`;
        return;
    }

    tbody.innerHTML = relations.map((rel) => `
        <tr>
            <td>${rel.vehicleId}</td>
            <td>${rel.vehicleType || "-"}</td>
            <td>${Math.round(rel.distance)} m</td>
            <td>${rel.relSpeed >= 0 ? "+" : ""}${Math.round(rel.relSpeed)} km/h</td>
            <td>${rel.sameLane ? "Same Lane" : "Adjacent Lane"}</td>
            <td>${rel.blindSpot ? '<span class="yes-flag">YES</span>' : '<span class="no-flag">No</span>'}</td>
            <td><span class="status-pill ${rel.statusKey}">${rel.statusLabel}</span></td>
            <td>${rel.recommendation}</td>
        </tr>
    `).join("");
}


// ---------------------------------------------------------
// Explainable AI panel
// ---------------------------------------------------------

function renderExplainableAi() {

    const body = document.getElementById("explainableAiBody");
    const vehicle = state.vehicles[state.selectedVehicleId];
    const ai = vehicle?.risk?.ai;

    if (!vehicle || !ai || ai.risk_category !== "HIGH") {
        body.innerHTML = `<p class="empty-hint">No high-risk prediction currently active${vehicle ? ` for ${vehicle.vehicle_id}` : ""}.</p>`;
        return;
    }

    const gps = vehicle.risk.gps || {};
    const zone = vehicle.risk.zone || {};
    const roadHealth = vehicle.risk.road_health || {};

    const reasons = (ai.reason || "").split(",").map((r) => r.trim()).filter(Boolean);

    body.innerHTML = `
        <div class="ai-risk-display">
            <span class="ai-risk-value HIGH">${Math.round((ai.risk_probability || 0) * 100)}%</span>
            <span>HIGH Risk Prediction</span>
        </div>
        <div class="location-row"><span>Current Polygon</span><b>${zone.zone_type || "None"}</b></div>
        <div class="location-row"><span>Road Health</span><b>${Math.round(roadHealth.score ?? 0)}</b></div>
        <div class="location-row"><span>GPS Confidence</span><b>${Math.round((gps.confidence ?? 1) * 100)}%</b></div>
        <div class="location-row"><span>Vehicle Type</span><b>${vehicle.vehicle_type || "-"}</b></div>
        <div class="location-row"><span>Speed</span><b>${Math.round(vehicle.speed || 0)} km/h</b></div>
        <div class="ai-reason-tags">
            ${reasons.map((r) => `<span class="ai-reason-tag">${r}</span>`).join("")}
        </div>
        <div class="ai-recommendation">
            <i class="fa-solid fa-lightbulb"></i> ${_recommendationFor(ai)}
        </div>
    `;
}


function _recommendationFor(ai) {

    if (!ai) return "-";

    if (ai.risk_category === "HIGH") return "Reduce Speed, Proceed with Caution";
    if (ai.risk_category === "MEDIUM") return "Stay Alert";
    return "Normal Driving";
}


// ---------------------------------------------------------
// Vehicle Information panel (right column)
// ---------------------------------------------------------

// ---------------------------------------------------------
// Danger Vehicle panel (right column) — dangerous vehicles only,
// highest AI risk first. A vehicle counts as "dangerous" if its
// AI risk category is MEDIUM or HIGH, it currently has an active
// heavy-vehicle overtaking threat, or its GPS is lost.
// ---------------------------------------------------------

function renderDangerVehicles() {

    const body = document.getElementById("dangerVehicleBody");
    const countLabel = document.getElementById("dangerCountLabel");
    if (!body) return;

    const vehicles = Object.values(state.vehicles);

    const flagged = vehicles
        .map((v) => {
            const ai = v.risk?.ai || {};
            const gps = v.risk?.gps || {};
            const relations = computeNearby(v.vehicle_id);
            const threat = relations.find((r) => r.statusKey === "unsafe" || r.statusKey === "blindspot");

            const isDangerous =
                ai.risk_category === "HIGH" ||
                ai.risk_category === "MEDIUM" ||
                !!gps.gps_lost ||
                !!threat;

            return {
                vehicle: v,
                ai,
                gps,
                threat,
                isDangerous,
                riskProbability: ai.risk_probability || 0,
            };
        })
        .filter((entry) => entry.isDangerous)
        .sort((a, b) => b.riskProbability - a.riskProbability);

    if (countLabel) countLabel.textContent = `${flagged.length} Flagged`;

    if (flagged.length === 0) {
        body.innerHTML = `<p class="empty-hint">No dangerous vehicles detected.</p>`;
        return;
    }

    body.innerHTML = flagged.map(({ vehicle, ai, gps, threat }) => {

        const category = ai.risk_category || "LOW";
        const reasonTags = (ai.reason || "").split(",").map((r) => r.trim()).filter(Boolean);

        return `
            <div class="danger-card ${category}" onclick="selectVehicle('${vehicle.vehicle_id}')">
                <div class="danger-card-top">
                    <span class="danger-card-id">${vehicle.vehicle_id} · ${vehicle.vehicle_type || "-"}</span>
                    <span class="danger-card-risk ${category}">${Math.round((ai.risk_probability || 0) * 100)}%</span>
                </div>
                <div class="danger-card-tags">
                    ${gps.gps_lost ? '<span class="danger-tag gps">GPS Lost</span>' : ""}
                    ${threat ? `<span class="danger-tag threat">${threat.statusLabel}</span>` : ""}
                    ${reasonTags.map((r) => `<span class="danger-tag">${r}</span>`).join("")}
                </div>
            </div>
        `;
    }).join("");
}


function renderVehicleInfo() {

    const body = document.getElementById("vehicleInfoBody");
    const vehicle = state.vehicles[state.selectedVehicleId];

    if (!vehicle) {
        body.innerHTML = `<p class="empty-hint">Select a vehicle to inspect.</p>`;
        return;
    }

    const risk = vehicle.risk || {};
    const zone = risk.zone || {};
    const roadHealth = risk.road_health || {};
    const ai = risk.ai || {};
    const gps = risk.gps || {};
    const zoneHist = state.zoneHistory[vehicle.vehicle_id] || {};

    const relations = computeNearby(vehicle.vehicle_id);
    const threat = relations.find((r) => r.statusKey === "unsafe" || r.statusKey === "blindspot");
    const recommendedAction = threat ? threat.recommendation : _recommendationFor(ai);

    body.innerHTML = `
        <div class="location-row"><span>Vehicle ID</span><b>${vehicle.vehicle_id}</b></div>
        <div class="location-row"><span>Vehicle Type</span><b>${vehicle.vehicle_type || "-"}</b></div>
        <div class="location-row"><span>Speed</span><b>${Math.round(vehicle.speed || 0)} km/h</b></div>
        <div class="location-row"><span>Driver Score</span><b>${ai.driver_score ?? "--"}</b></div>
        <div class="location-row"><span>AI Risk</span><b>${Math.round((ai.risk_probability ?? 0) * 100)}% (${ai.risk_category || "-"})</b></div>
        <div class="location-row"><span>GPS Confidence</span><b>${Math.round((gps.confidence ?? 1) * 100)}%</b></div>
        <div class="location-row"><span>Road Health</span><b>${Math.round(roadHealth.score ?? 0)}</b></div>
        <div class="location-row"><span>Current Polygon</span><b>${zone.zone_type || "None"}</b></div>
        <div class="location-row"><span>Previous Polygon</span><b>${zoneHist.previous || "None"}</b></div>
        <div class="location-row"><span>Distance to Next Polygon</span><b>${zone.inside ? "In Zone" : (zone.distance_to_nearest_zone != null ? Math.round(zone.distance_to_nearest_zone) + " m" : "-")}</b></div>
        <div class="location-row"><span>Nearest Hazard</span><b>${roadHealth.nearest_hazard?.hazard_type || "None"}</b></div>
        <div class="location-row"><span>Recommended Action</span><b>${recommendedAction}</b></div>
    `;
}


// ---------------------------------------------------------
// Live alerts feed
// ---------------------------------------------------------

function renderAlertFeed() {

    const feed = document.getElementById("alertFeed");

    if (state.alerts.length === 0) {
        feed.innerHTML = `<p class="empty-hint">No alerts yet.</p>`;
        return;
    }

    feed.innerHTML = state.alerts.slice(0, MAX_ALERTS_DISPLAYED).map((alert) => {

        const time = alert.timestamp
            ? new Date(alert.timestamp).toLocaleTimeString("en-GB")
            : "--:--:--";

        return `
            <div class="alert-item priority-${alert.priority || "MEDIUM"}">
                <div class="alert-top">
                    <span class="alert-type">${alert.alert_type || "Alert"} — ${alert.vehicle_id || ""}</span>
                    <span class="alert-time">${time}</span>
                </div>
                <div class="alert-msg">${alert.message || ""}</div>
                ${alert.recommendation ? `<div class="alert-rec"><i class="fa-solid fa-arrow-right"></i> ${alert.recommendation}</div>` : ""}
            </div>
        `;
    }).join("");
}


// ---------------------------------------------------------
// Charts
// ---------------------------------------------------------

function initCharts() {

    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#8ea0bd", font: { size: 10 } } } },
        scales: {
            x: { ticks: { color: "#56647d" }, grid: { color: "rgba(255,255,255,0.04)" } },
            y: { ticks: { color: "#56647d" }, grid: { color: "rgba(255,255,255,0.04)" } },
        },
    };

    chartSpeed = new Chart(document.getElementById("chartSpeed"), {
        type: "line",
        data: { labels: [], datasets: [] },
        options: commonOptions,
    });

    chartRisk = new Chart(document.getElementById("chartRisk"), {
        type: "doughnut",
        data: {
            labels: ["LOW", "MEDIUM", "HIGH"],
            datasets: [{
                data: [0, 0, 0],
                backgroundColor: ["#29e07a", "#ffb020", "#ff3b5c"],
                borderWidth: 0,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: "#8ea0bd", font: { size: 10 } } } },
        },
    });

    chartRoadHealth = new Chart(document.getElementById("chartRoadHealth"), {
        type: "bar",
        data: { labels: [], datasets: [{ label: "Road Health", data: [], backgroundColor: "#33e0ff" }] },
        options: commonOptions,
    });

    chartAlertFreq = new Chart(document.getElementById("chartAlertFreq"), {
        type: "bar",
        data: { labels: [], datasets: [{ label: "Alerts", data: [], backgroundColor: "#ff3b5c" }] },
        options: commonOptions,
    });
}


function renderCharts() {

    const vehicles = Object.values(state.vehicles);

    const speedLabels = Array.from(
        { length: MAX_SPEED_HISTORY_POINTS },
        (_, i) => i + 1
    );

    const colorPalette = ["#33e0ff", "#8B5A2B", "#8a7dff", "#29e07a"];

    chartSpeed.data.labels = speedLabels;
    chartSpeed.data.datasets = vehicles.map((v, idx) => ({
        label: v.vehicle_id,
        data: state.speedHistory[v.vehicle_id] || [],
        borderColor: colorPalette[idx % colorPalette.length],
        backgroundColor: "transparent",
        tension: 0.3,
    }));
    chartSpeed.update("none");

    const counts = { LOW: 0, MEDIUM: 0, HIGH: 0 };
    vehicles.forEach((v) => {
        const cat = v.risk?.ai?.risk_category;
        if (cat && counts[cat] !== undefined) counts[cat]++;
    });
    chartRisk.data.datasets[0].data = [counts.LOW, counts.MEDIUM, counts.HIGH];
    chartRisk.update("none");

    chartRoadHealth.data.labels = vehicles.map((v) => v.vehicle_id);
    chartRoadHealth.data.datasets[0].data = vehicles.map((v) => Math.round(v.risk?.road_health?.score ?? 0));
    chartRoadHealth.update("none");

    const alertTypes = Object.keys(state.alertFrequency);
    chartAlertFreq.data.labels = alertTypes;
    chartAlertFreq.data.datasets[0].data = alertTypes.map((t) => state.alertFrequency[t]);
    chartAlertFreq.update("none");
}