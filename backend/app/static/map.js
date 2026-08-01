/*
 * map.js
 *
 * Leaflet map setup for the SmartMove AI Command Center: vehicle
 * markers (rotated by heading, colored by type), danger zone
 * polygons (with the vehicle's currently-active polygon
 * highlighted), road hazard markers, and a GPS recovery trail
 * drawn whenever a vehicle's GPS is lost and its position is being
 * estimated via dead reckoning / road-snap.
 *
 * Exposes a small global `SmartMoveMap` API that app.js drives
 * with live data.
 */

const SmartMoveMap = (() => {

    const VEHICLE_COLORS = {
        Car: "#2E86FF",
        Truck: "#8B5A2B",
        Bus: "#8B5A2B",
        Lorry: "#8B5A2B",
        Container: "#8B5A2B",
        Tanker: "#8B5A2B",
        Ambulance: "#FFFFFF",
        Police: "#0B1F5C",
        Bike: "#2ECC71",
        Auto: "#F1C40F",
    };

    const ZONE_COLORS = {
        School: "#ffb020",
        Hairpin: "#ff3b5c",
        Hospital: "#33e0ff",
        Construction: "#ffb020",
        Flood: "#3388ff",
        Accident: "#ff3b5c",
        RoadBlock: "#ff3b5c",
        Bridge: "#8a7dff",
    };

    const HAZARD_COLORS = {
        Pothole: "#ff3b5c",
        Construction: "#ffb020",
        Flood: "#3388ff",
        RoadBlock: "#ff3b5c",
        Accident: "#ff3b5c",
        SpeedBreaker: "#ffb020",
        OilSpill: "#8a7dff",
        FallenTree: "#29e07a",
        RoadDamage: "#ff8a3d",
    };

    const EMERGENCY_TYPES = new Set(["Ambulance", "Police"]);

    let map = null;
    const vehicleMarkers = {};
    const zoneLayers = [];       // { layer, zoneType }
    const hazardLayers = [];
    const recoveryPaths = {};    // vehicle_id -> polyline layer
    const lastGoodFix = {};      // vehicle_id -> [lat, lon]

    let onVehicleClick = null;

    function init(containerId, center, zoom) {

    map = L.map(containerId, {
        center: center,
        zoom: zoom,
        zoomControl: true,
        attributionControl: false,
    });

    // ===========================
    // Esri Satellite Imagery
    // ===========================
    const satellite = L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        {
            maxZoom: 20,
            attribution:
                '&copy; Esri, Maxar, Earthstar Geographics, CNES/Airbus, USDA, USGS'
        }
    );

    // ===========================
    // Labels (Roads, Places)
    // ===========================
    const labels = L.tileLayer(
        "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        {
            maxZoom: 20,
            pane: "overlayPane"
        }
    );

    satellite.addTo(map);
    labels.addTo(map);

    // Optional Layer Control
    const street = L.tileLayer(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        {
            maxZoom: 20,
            attribution: "&copy; OpenStreetMap"
        }
    );

    L.control.layers(
        {
            "Satellite": satellite,
            "Street": street
        }, 
        {},
        {
            collapsed: false
        }
    ).addTo(map);

    return map;
}

    function setVehicleClickHandler(handler) {
        onVehicleClick = handler;
    }

    function _vehicleIconHtml(vehicleType, heading, isDanger, isGpsLost) {

        const color = VEHICLE_COLORS[vehicleType] || "#2E86FF";
        const pulse = isDanger ? "pulse" : "";
        const ringColor = isGpsLost ? "#ffb020" : "transparent";

        return `
            <div class="vehicle-marker ${pulse}" style="transform: rotate(${heading}deg);">
                <svg width="26" height="26" viewBox="0 0 26 26">
                    <circle cx="13" cy="13" r="11.5" fill="none" stroke="${ringColor}" stroke-width="1.4" stroke-dasharray="2 2"/>
                    <polygon points="13,2 22,22 13,17 4,22" fill="${color}" stroke="#0a0f18" stroke-width="1.2"/>
                </svg>
            </div>
        `;
    }

    function upsertVehicle(vehicle) {

        const id = vehicle.vehicle_id;
        const lat = vehicle.latitude;
        const lon = vehicle.longitude;
        const heading = vehicle.heading || 0;
        const vehicleType = vehicle.vehicle_type || "Car";
        const riskCategory = (vehicle.risk && vehicle.risk.ai && vehicle.risk.ai.risk_category) || "LOW";
        const isDanger = riskCategory === "HIGH";
        const isEmergency = EMERGENCY_TYPES.has(vehicleType);
        const isGpsLost = !!(vehicle.risk && vehicle.risk.gps && vehicle.risk.gps.gps_lost);

        // Track the GPS recovery trail: remember the last good fix,
        // and while lost, draw a dashed line from that fix to the
        // current dead-reckoned / road-snapped estimate.
        if (!isGpsLost) {
            lastGoodFix[id] = [lat, lon];
            _clearRecoveryPath(id);
        } else if (lastGoodFix[id]) {
            _drawRecoveryPath(id, lastGoodFix[id], [lat, lon]);
        }

        const icon = L.divIcon({
            html: _vehicleIconHtml(vehicleType, heading, isDanger, isGpsLost),
            className: "vehicle-icon-wrapper",
            iconSize: [26, 26],
            iconAnchor: [13, 13],
        });

        if (vehicleMarkers[id]) {

            vehicleMarkers[id].setLatLng([lat, lon]);
            vehicleMarkers[id].setIcon(icon);

            if (isEmergency) {
                vehicleMarkers[id].setZIndexOffset(1000);
            }

        } else {

            const marker = L.marker([lat, lon], { icon }).addTo(map);

            marker.on("click", () => {
                if (onVehicleClick) onVehicleClick(id);
            });

            if (isEmergency) {
                marker.setZIndexOffset(1000);
            }

            vehicleMarkers[id] = marker;
        }

        return vehicleMarkers[id];
    }

    function _clearRecoveryPath(vehicleId) {

        if (recoveryPaths[vehicleId]) {
            map.removeLayer(recoveryPaths[vehicleId]);
            delete recoveryPaths[vehicleId];
        }
    }

    function _drawRecoveryPath(vehicleId, fromLatLng, toLatLng) {

        _clearRecoveryPath(vehicleId);

        const line = L.polyline([fromLatLng, toLatLng], {
            color: "#ffb020",
            weight: 2,
            opacity: 0.85,
            className: "gps-recovery-path",
        }).addTo(map);

        recoveryPaths[vehicleId] = line;
    }

    function updatePopup(vehicleId, html) {

        const marker = vehicleMarkers[vehicleId];

        if (marker) {
            marker.bindPopup(html, { className: "smartmove-popup" });
        }
    }

    function _circleToLatLngs(lat, lon, radiusMeters, points = 24) {

        const coords = [];
        const earthRadius = 6371000;

        for (let i = 0; i < points; i++) {

            const angle = (2 * Math.PI * i) / points;

            const dLat = (radiusMeters / earthRadius) * (180 / Math.PI) * Math.cos(angle);
            const dLon = (radiusMeters / (earthRadius * Math.cos((lat * Math.PI) / 180))) *
                         (180 / Math.PI) * Math.sin(angle);

            coords.push([lat + dLat, lon + dLon]);
        }

        return coords;
    }

    function drawZones(zones) {

        zoneLayers.forEach((entry) => map.removeLayer(entry.layer));
        zoneLayers.length = 0;

        zones.forEach((zone) => {

            const color = ZONE_COLORS[zone.zone_type] || "#33e0ff";

            let latlngs;

            if (zone.polygon_geojson) {

                const vertices = typeof zone.polygon_geojson === "string"
                    ? JSON.parse(zone.polygon_geojson)
                    : zone.polygon_geojson;

                latlngs = vertices;

            } else {

                latlngs = _circleToLatLngs(zone.latitude, zone.longitude, zone.radius || 80);
            }

            const polygon = L.polygon(latlngs, {
                color: color,
                weight: 1.5,
                fillColor: color,
                fillOpacity: 0.12,
                dashArray: "4 4",
            }).addTo(map);

            polygon.bindTooltip(`${zone.zone_type} Zone`, { sticky: true });

            zoneLayers.push({ layer: polygon, zoneType: zone.zone_type });
        });
    }

    /**
     * Bold/highlight the polygon matching the focused vehicle's
     * current zone_type (the polygon it is physically inside),
     * dimming every other zone slightly so the active one reads
     * clearly at a glance.
     */
    function highlightActiveZone(zoneType) {

        zoneLayers.forEach((entry) => {

            const isActive = zoneType && entry.zoneType === zoneType;

            entry.layer.setStyle({
                weight: isActive ? 3.5 : 1.5,
                fillOpacity: isActive ? 0.32 : 0.1,
                dashArray: isActive ? null : "4 4",
                opacity: isActive ? 1 : 0.55,
            });

            if (isActive) {
                entry.layer.bringToFront();
            }
        });
    }

    function drawHazards(hazards) {

        hazardLayers.forEach((layer) => map.removeLayer(layer));
        hazardLayers.length = 0;

        hazards.forEach((hazard) => {

            const color = HAZARD_COLORS[hazard.hazard_type] || "#ff3b5c";

            const marker = L.circleMarker([hazard.latitude, hazard.longitude], {
                radius: 5,
                color: color,
                fillColor: color,
                fillOpacity: 0.6,
                weight: 1,
            }).addTo(map);

            marker.bindTooltip(hazard.hazard_type, { sticky: true });

            hazardLayers.push(marker);
        });
    }

    return {
        init,
        setVehicleClickHandler,
        upsertVehicle,
        updatePopup,
        drawZones,
        drawHazards,
        highlightActiveZone,
    };

})();