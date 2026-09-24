from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import math
import base64
import uuid
import json
import os
import requests
import joblib
import time
from concurrent.futures import ThreadPoolExecutor
from numbers import Integral

import firebase_admin
from firebase_admin import credentials, firestore

from shapely.geometry import LineString, Point, box
from shapely.strtree import STRtree
from fastapi.staticfiles import StaticFiles


app = FastAPI(title="GeoSentinel API")


# ---------------------------------------------------------
# FIELD REPORT PHOTO STORAGE
# ---------------------------------------------------------

UPLOAD_DIR = "../data/report_photos"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# ---------------------------------------------------------
# FIREBASE / FIRESTORE
# ---------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_PATH = os.path.abspath(
    os.path.join(BASE_DIR, "..", "firebase-service-account.json")
)

if not os.path.exists(SERVICE_ACCOUNT_PATH):
    raise RuntimeError(
        "Firebase service account file not found. "
        "Place firebase-service-account.json in the GeoSentinel project root."
    )

if not firebase_admin._apps:
    firebase_admin.initialize_app(
        credentials.Certificate(SERVICE_ACCOUNT_PATH)
    )

db = firestore.client()
REPORTS_COLLECTION = "reports"


def load_reports_from_firestore():
    loaded_reports = []

    for document in db.collection(REPORTS_COLLECTION).stream():
        report = document.to_dict()

        # Keep the API shape compatible with the existing frontend.
        report["id"] = int(report.get("id", document.id))

        loaded_reports.append(report)

    loaded_reports.sort(key=lambda item: item["id"])
    return loaded_reports


# Keep a small in-memory cache for fast reads, but Firestore is the
# source of truth so reports survive backend restarts.
reports = load_reports_from_firestore()

if reports:
    next_report_id = max(report["id"] for report in reports) + 1
else:
    next_report_id = 1

print(f"Firebase connected. Reports loaded: {len(reports)}")


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# LOAD ML MODEL
# ---------------------------------------------------------

MODEL_PATH = "../ml/models/landslide_model.joblib"

model = joblib.load(MODEL_PATH)


# ---------------------------------------------------------
# LOAD OSM INFRASTRUCTURE
# ---------------------------------------------------------

ROADS_PATH = "../data/roads/roads.json"
SETTLEMENTS_PATH = "../data/settlements/settlements.json"


print("Loading infrastructure data...")


roads = []
settlements = []


# ---------------------------------------------------------
# LOAD ROADS
# ---------------------------------------------------------

try:

    with open(
        ROADS_PATH,
        "r",
        encoding="utf-8",
    ) as file:

        roads = json.load(file)

    print(
        f"Roads loaded: {len(roads)}"
    )

except Exception as error:

    print(
        "Road loading error:",
        error,
    )


# ---------------------------------------------------------
# LOAD SETTLEMENTS
# ---------------------------------------------------------

try:

    with open(
        SETTLEMENTS_PATH,
        "r",
        encoding="utf-8",
    ) as file:

        settlements = json.load(file)

    print(
        f"Settlements loaded: {len(settlements)}"
    )

except Exception as error:

    print(
        "Settlement loading error:",
        error,
    )


print("Infrastructure loading complete.")


# ---------------------------------------------------------
# ROAD SPATIAL INDEX
# ---------------------------------------------------------
# Build road geometries once so each prediction does not scan all roads.
road_geometries = []
road_records = []
road_geometry_lookup = {}

for road in roads:
    coordinates = road.get("coordinates", [])
    if len(coordinates) < 2:
        continue
    try:
        geometry = LineString(coordinates)
        road_geometries.append(geometry)
        road_records.append(road)
        road_geometry_lookup[id(geometry)] = road
    except Exception:
        continue

road_tree = STRtree(road_geometries) if road_geometries else None
print(f"Road spatial index ready: {len(road_geometries)} geometries")


# ---------------------------------------------------------
# ENVIRONMENT CACHE
# ---------------------------------------------------------

environment_cache = {}
ENVIRONMENT_CACHE_TTL_SECONDS = 5 * 60


def get_cache_key(
    latitude,
    longitude,
):

    return (
        round(float(latitude), 4),
        round(float(longitude), 4),
    )


# ---------------------------------------------------------
# REQUEST MODEL
# ---------------------------------------------------------

class LocationRequest(BaseModel):

    latitude: float
    longitude: float


# ---------------------------------------------------------
# ELEVATION
# ---------------------------------------------------------

def get_elevation(
    latitude,
    longitude,
):

    try:

        response = requests.get(
            "https://api.open-meteo.com/v1/elevation",
            params={
                "latitude": latitude,
                "longitude": longitude,
            },
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        elevation = data.get(
            "elevation"
        )

        if isinstance(
            elevation,
            list,
        ):

            elevation = elevation[0]

        if elevation is None:

            return 500.0

        return float(elevation)

    except Exception as error:

        print(
            "Elevation error:",
            error,
        )

        return 500.0


# ---------------------------------------------------------
# RAINFALL
# ---------------------------------------------------------

def get_rainfall(
    latitude,
    longitude,
):

    try:

        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "precipitation,rain",
                "hourly": "precipitation,rain",
                "past_days": 7,
                "forecast_days": 1,
                "timezone": "auto",
            },
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        hourly = data.get("hourly", {})
        hourly_times = hourly.get("time", [])
        hourly_precipitation = hourly.get("precipitation", [])
        current = data.get("current", {})

        if not hourly_times or not hourly_precipitation:
            raise ValueError("Forecast response did not include hourly precipitation")

        current_time = current.get("time")
        completed_values = []
        for index, value in enumerate(hourly_precipitation):
            if index >= len(hourly_times):
                break
            if current_time is None or hourly_times[index] <= current_time:
                completed_values.append(0.0 if value is None else float(value))

        latest_values = completed_values[-168:]
        if not latest_values:
            raise ValueError("Forecast response did not include completed hourly precipitation")

        current_precipitation = current.get("precipitation")
        if current_precipitation is None:
            current_precipitation = latest_values[-1]

        rainfall_24h = sum(latest_values[-24:])
        rainfall_3d = sum(latest_values[-72:])
        rainfall_7d = sum(latest_values)
        rainfall_intensity = max(latest_values[-24:])

        return {
            "rainfall_mm": round(rainfall_24h, 1),
            "rainfall_current_mm": round(float(current_precipitation), 1),
            "rainfall_24h_mm": round(rainfall_24h, 1),
            "rainfall_3d_mm": round(rainfall_3d, 1),
            "rainfall_7d_mm": round(rainfall_7d, 1),
            "rainfall_intensity_mm_h": round(rainfall_intensity, 1),
            "rainfall_source": "open-meteo-forecast",
        }

    except Exception as live_error:

        print(
            "Live rainfall error:",
            live_error,
        )

    try:
        response = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "start_date": "2025-01-01",
                "end_date": "2025-12-31",
                "daily": "precipitation_sum",
                "timezone": "auto",
            },
            timeout=10,
        )
        response.raise_for_status()

        rainfall_values = response.json().get("daily", {}).get("precipitation_sum", [])
        rainfall_values = [
            float(value) for value in rainfall_values if value is not None
        ]
        fallback_rainfall = round(max(rainfall_values), 1) if rainfall_values else 0.0

        return {
            "rainfall_mm": fallback_rainfall,
            "rainfall_current_mm": 0.0,
            "rainfall_24h_mm": fallback_rainfall,
            "rainfall_3d_mm": fallback_rainfall,
            "rainfall_7d_mm": fallback_rainfall,
            "rainfall_intensity_mm_h": fallback_rainfall,
            "rainfall_source": "open-meteo-archive-fallback",
        }

    except Exception as fallback_error:
        print("Historical rainfall fallback error:", fallback_error)
        return {
            "rainfall_mm": 0.0,
            "rainfall_current_mm": 0.0,
            "rainfall_24h_mm": 0.0,
            "rainfall_3d_mm": 0.0,
            "rainfall_7d_mm": 0.0,
            "rainfall_intensity_mm_h": 0.0,
            "rainfall_source": "unavailable",
        }


# ---------------------------------------------------------
# SLOPE
# ---------------------------------------------------------

def get_slope(
    latitude,
    longitude,
):
    """Calculate slope using the same batched terrain request."""
    _, slope = get_terrain_features(latitude, longitude)
    return slope


def get_terrain_features(
    latitude,
    longitude,
):
    """Fetch center elevation and four neighboring elevations in one request."""
    offsets = [
        (0.0, 0.0),
        (0.01, 0.0),
        (-0.01, 0.0),
        (0.0, 0.01),
        (0.0, -0.01),
    ]
    coordinates = [(latitude + dlat, longitude + dlon) for dlat, dlon in offsets]

    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/elevation",
            params={
                "latitude": ",".join(str(point[0]) for point in coordinates),
                "longitude": ",".join(str(point[1]) for point in coordinates),
            },
            timeout=10,
        )
        response.raise_for_status()
        elevations = response.json().get("elevation", [])
        if len(elevations) != 5:
            return 500.0, 5.0

        elevation = float(elevations[0])
        north, south = float(elevations[1]), float(elevations[2])
        east, west = float(elevations[3]), float(elevations[4])

        north_south_distance = 0.02 * 111000
        east_west_distance = max(0.02 * 111000 * math.cos(math.radians(latitude)), 1.0)
        north_south_gradient = abs(north - south) / north_south_distance
        east_west_gradient = abs(east - west) / east_west_distance
        slope_percent = math.sqrt(north_south_gradient ** 2 + east_west_gradient ** 2) * 100

        return elevation, round(min(slope_percent, 60), 2)
    except Exception as error:
        print("Terrain error:", error)
        return 500.0, 5.0


# ---------------------------------------------------------
# GET ENVIRONMENT
# ---------------------------------------------------------

def get_environment(
    latitude,
    longitude,
):
    cache_key = get_cache_key(latitude, longitude)

    cached_entry = environment_cache.get(cache_key)
    if (
        cached_entry
        and time.time() - cached_entry["timestamp"] < ENVIRONMENT_CACHE_TTL_SECONDS
    ):
        print(f"Using cached environment for {cache_key}")
        return cached_entry["data"]

    print(f"Fetching environment for {cache_key}")

    # These are independent network calls, so run them concurrently.
    # Terrain also combines elevation + slope into a single API request.
    with ThreadPoolExecutor(max_workers=2) as executor:
        rainfall_future = executor.submit(get_rainfall, latitude, longitude)
        terrain_future = executor.submit(get_terrain_features, latitude, longitude)
        rainfall = rainfall_future.result()
        elevation, slope = terrain_future.result()

    environment = {
        "rainfall": rainfall["rainfall_mm"],
        **rainfall,
        "elevation": elevation,
        "slope": slope,
    }
    environment_cache[cache_key] = {
        "timestamp": time.time(),
        "data": environment,
    }
    return environment


# ---------------------------------------------------------
# DISTANCE CALCULATION
# ---------------------------------------------------------

def haversine_distance(
    lat1,
    lon1,
    lat2,
    lon2,
):

    earth_radius = 6371000

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlat = math.radians(
        lat2 - lat1
    )

    dlon = math.radians(
        lon2 - lon1
    )

    a = (
        math.sin(dlat / 2) ** 2
        +
        math.cos(lat1)
        * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    c = (
        2
        * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a),
        )
    )

    return earth_radius * c


# ---------------------------------------------------------
# FIND NEAREST ROAD
# ---------------------------------------------------------

def find_nearest_road(
    latitude,
    longitude,
):
    if not road_tree:
        return None

    point = Point(longitude, latitude)
    search_box = box(
        longitude - 0.15,
        latitude - 0.15,
        longitude + 0.15,
        latitude + 0.15,
    )
    candidates = road_tree.query(search_box)

    best_road = None
    best_distance = float("inf")

    for candidate in candidates:
        if isinstance(candidate, Integral):
            index = int(candidate)
            road_line = road_geometries[index]
            road = road_records[index]
        else:
            road_line = candidate
            road = road_geometry_lookup.get(id(road_line))
            if road is None:
                continue

        nearest_point = road_line.interpolate(road_line.project(point))
        distance = haversine_distance(
            latitude, longitude, nearest_point.y, nearest_point.x
        )

        if distance < best_distance:
            best_distance = distance
            best_road = {
                "name": road.get("name") or "Unnamed road",
                "type": road.get("type", "road"),
                "distance_m": round(distance, 1),
            }

    return best_road


# ---------------------------------------------------------
# FIND NEAREST SETTLEMENT
# ---------------------------------------------------------

def find_nearest_settlement(
    latitude,
    longitude,
):

    if not settlements:

        return None

    best_settlement = None
    best_distance = float("inf")

    for settlement in settlements:

        settlement_lat = settlement.get(
            "latitude"
        )

        settlement_lon = settlement.get(
            "longitude"
        )

        if (
            settlement_lat is None
            or settlement_lon is None
        ):

            continue

        # Rough bounding-box filter.
        if (
            abs(
                latitude
                - float(settlement_lat)
            )
            > 0.5
        ):

            continue

        if (
            abs(
                longitude
                - float(settlement_lon)
            )
            > 0.5
        ):

            continue

        distance = haversine_distance(
            latitude,
            longitude,
            float(settlement_lat),
            float(settlement_lon),
        )

        if distance < best_distance:

            best_distance = distance

            best_settlement = {

                "name": (
                    settlement.get("name")
                    or "Unnamed settlement"
                ),

                "type": settlement.get(
                    "type",
                    "settlement",
                ),

                "distance_m": round(
                    distance,
                    1,
                ),

            }

    return best_settlement


# ---------------------------------------------------------
# INFRASTRUCTURE IMPACT
# ---------------------------------------------------------

def assess_infrastructure(
    latitude,
    longitude,
    risk_score,
):

    nearest_road = find_nearest_road(
        latitude,
        longitude,
    )

    nearest_settlement = (
        find_nearest_settlement(
            latitude,
            longitude,
        )
    )

    exposed_roads = []

    exposed_settlements = []

    # High/medium risk locations near roads
    # are considered potentially exposed.
    #
    # IMPORTANT:
    # This does NOT mean the road is blocked
    # or damaged.

    if (
        nearest_road
        and nearest_road["distance_m"] <= 1000
        and risk_score >= 40
    ):

        exposed_roads.append(
            nearest_road
        )

    if (
        nearest_settlement
        and nearest_settlement["distance_m"] <= 2000
        and risk_score >= 40
    ):

        exposed_settlements.append(
            nearest_settlement
        )

    return {

        "nearest_road": nearest_road,

        "nearest_settlement":
            nearest_settlement,

        "potentially_exposed_roads":
            exposed_roads,

        "potentially_exposed_settlements":
            exposed_settlements,

    }


# ---------------------------------------------------------
# RISK CALCULATION
# ---------------------------------------------------------

def calculate_risk(
    rainfall,
    elevation,
    slope,
):

    features = [[
        rainfall,
        elevation,
        slope,
    ]]

    try:

        prediction = int(
            model.predict(
                features
            )[0]
        )

    except Exception as error:

        print(
            "ML prediction error:",
            error,
        )

        prediction = 0

    slope_score = (
        min(
            slope / 30.0,
            1.0,
        )
        * 40
    )

    rainfall_score = (
        min(
            rainfall / 150.0,
            1.0,
        )
        * 35
    )

    elevation_score = (
        min(
            elevation / 3000.0,
            1.0,
        )
        * 10
    )

    ml_score = prediction * 15

    total_score = (
        slope_score
        + rainfall_score
        + elevation_score
        + ml_score
    )

    total_score = min(
        round(
            total_score,
            1,
        ),
        100.0,
    )

    if total_score >= 70:

        risk_level = "High"

    elif total_score >= 40:

        risk_level = "Medium"

    else:

        risk_level = "Low"

    explanation = []

    if slope >= 15:

        explanation.append(
            "Steep terrain increases landslide susceptibility."
        )

    elif slope >= 7:

        explanation.append(
            "Moderate terrain slope contributes to slope instability."
        )

    else:

        explanation.append(
            "Relatively gentle terrain reduces slope-related susceptibility."
        )

    if rainfall >= 100:

        explanation.append(
            "High rainfall conditions can increase soil saturation and instability."
        )

    elif rainfall >= 50:

        explanation.append(
            "Elevated rainfall conditions may increase slope instability."
        )

    else:

        explanation.append(
            "Lower rainfall conditions reduce the rainfall contribution to risk."
        )

    if elevation >= 1500:

        explanation.append(
            "High-elevation terrain contributes additional terrain susceptibility."
        )

    if prediction == 1:

        explanation.append(
            "The machine-learning model classified these environmental conditions as potentially landslide-prone."
        )

    else:

        explanation.append(
            "The machine-learning model did not classify these environmental conditions as strongly landslide-prone."
        )

    return (
        risk_level,
        total_score,
        prediction,
        explanation,
    )


# ---------------------------------------------------------
# PREDICT ENDPOINT
# ---------------------------------------------------------

@app.post("/predict")
def predict(
    location: LocationRequest,
):

    latitude = float(
        location.latitude
    )

    longitude = float(
        location.longitude
    )

    print(
        f"Analyzing location: "
        f"{latitude:.5f}, "
        f"{longitude:.5f}"
    )

    environment = get_environment(
        latitude,
        longitude,
    )

    rainfall = environment[
        "rainfall"
    ]

    elevation = environment[
        "elevation"
    ]

    slope = environment[
        "slope"
    ]

    (
        risk_level,
        risk_score,
        prediction,
        explanation,
    ) = calculate_risk(
        rainfall,
        elevation,
        slope,
    )

    infrastructure = (
        assess_infrastructure(
            latitude,
            longitude,
            risk_score,
        )
    )

    return {

        "risk_level":
            risk_level,

        "risk_score":
            risk_score,

        "landslide_prediction":
            prediction,

        "environment": {

            "rainfall_mm":
                rainfall,

            "rainfall_current_mm":
                environment["rainfall_current_mm"],

            "rainfall_24h_mm":
                environment["rainfall_24h_mm"],

            "rainfall_3d_mm":
                environment["rainfall_3d_mm"],

            "rainfall_7d_mm":
                environment["rainfall_7d_mm"],

            "rainfall_intensity_mm_h":
                environment["rainfall_intensity_mm_h"],

            "rainfall_source":
                environment["rainfall_source"],

            "elevation_m":
                round(
                    elevation,
                    1,
                ),

            "slope_percent":
                slope,

        },

        "explanation":
            explanation,

        "location": {

            "latitude":
                latitude,

            "longitude":
                longitude,

        },

        "infrastructure":
            infrastructure,

    }


# ---------------------------------------------------------
# FIELD REPORTS
# ---------------------------------------------------------

class ReportRequest(BaseModel):
    latitude: float
    longitude: float
    report_type: str
    description: str = ""
    photo_name: str | None = None
    photo_data: str | None = None


def save_report_photo(photo_name, photo_data):
    if not photo_data:
        return None

    # Accept a browser FileReader data URL, e.g. data:image/jpeg;base64,...
    try:
        if "," in photo_data:
            header, encoded = photo_data.split(",", 1)
        else:
            header, encoded = "", photo_data

        raw = base64.b64decode(encoded, validate=True)
    except Exception as error:
        raise HTTPException(status_code=400, detail="Invalid photo data.") from error

    # Keep the prototype safe and lightweight.
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Photo must be 5 MB or smaller.")

    extension = os.path.splitext(photo_name or "photo.jpg")[1].lower()
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if extension not in allowed_extensions:
        extension = ".jpg"

    filename = f"report_{uuid.uuid4().hex}{extension}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as file:
        file.write(raw)

    return f"/uploads/{filename}"


@app.post("/reports")
def create_report(report: ReportRequest):
    global next_report_id

    if not report.report_type.strip():
        raise HTTPException(status_code=400, detail="Report type is required.")

    photo_url = save_report_photo(
        report.photo_name,
        report.photo_data,
    )

    report_id = next_report_id
    next_report_id += 1

    from datetime import datetime, timezone

    new_report = {
        "id": report_id,
        "latitude": float(report.latitude),
        "longitude": float(report.longitude),
        "report_type": report.report_type.strip(),
        "description": report.description.strip(),
        "photo_name": report.photo_name,
        "photo_url": photo_url,
        "status": "Pending",
        "created_at": datetime.now(timezone.utc),
    }

    # Persist to Firestore first.
    db.collection(REPORTS_COLLECTION).document(str(report_id)).set(
        new_report
    )

    # Then update the local cache.
    reports.append(new_report)

    return {
        "message": "Report submitted successfully.",
        "report": new_report,
    }


@app.get("/reports")
def get_reports():
    # Refresh from Firestore so multiple browser sessions and
    # authority updates are reflected without restarting the API.
    global reports
    reports = load_reports_from_firestore()

    return {
        "reports": reports,
        "count": len(reports),
    }


@app.get("/reports/{report_id}")
def get_report(report_id: int):
    document = (
        db.collection(REPORTS_COLLECTION)
        .document(str(report_id))
        .get()
    )

    if not document.exists:
        raise HTTPException(status_code=404, detail="Report not found.")

    report = document.to_dict()
    report["id"] = int(report.get("id", report_id))

    return report


class ReportStatusUpdate(BaseModel):
    status: str


@app.patch("/reports/{report_id}")
def update_report(report_id: int, update: ReportStatusUpdate):
    allowed_statuses = {"Pending", "Verified", "Rejected"}

    if update.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail="Status must be Pending, Verified, or Rejected.",
        )

    document_ref = db.collection(REPORTS_COLLECTION).document(
        str(report_id)
    )
    document = document_ref.get()

    if not document.exists:
        raise HTTPException(status_code=404, detail="Report not found.")

    document_ref.update({
        "status": update.status,
    })

    updated_report = document_ref.get().to_dict()
    updated_report["id"] = int(updated_report.get("id", report_id))

    # Keep the local cache synchronized as well.
    global reports
    reports = load_reports_from_firestore()

    return {
        "message": "Report status updated successfully.",
        "report": updated_report,
    }


# ---------------------------------------------------------
# ROOT
# ---------------------------------------------------------

@app.get("/")
def root():

    return {

        "name":
            "GeoSentinel",

        "status":
            "online",

        "cached_locations":
            len(
                environment_cache
            ),

        "roads_loaded":
            len(roads),

        "settlements_loaded":
            len(settlements),

    }
