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

import firebase_admin
from firebase_admin import credentials, firestore

from shapely.geometry import LineString, Point
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
# ENVIRONMENT CACHE
# ---------------------------------------------------------

environment_cache = {}


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
# HISTORICAL RAINFALL
# ---------------------------------------------------------

def get_rainfall(
    latitude,
    longitude,
):

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

        data = response.json()

        rainfall_values = (
            data
            .get("daily", {})
            .get(
                "precipitation_sum",
                [],
            )
        )

        rainfall_values = [
            float(value)
            for value in rainfall_values
            if value is not None
        ]

        if not rainfall_values:

            return 0.0

        return round(
            max(rainfall_values),
            1,
        )

    except Exception as error:

        print(
            "Rainfall error:",
            error,
        )

        return 0.0


# ---------------------------------------------------------
# SLOPE
# ---------------------------------------------------------

def get_slope(
    latitude,
    longitude,
):

    offsets = [
        (0.01, 0),
        (-0.01, 0),
        (0, 0.01),
        (0, -0.01),
    ]

    coordinates = [
        (
            latitude + dlat,
            longitude + dlon,
        )
        for dlat, dlon in offsets
    ]

    try:

        latitudes = ",".join(
            str(point[0])
            for point in coordinates
        )

        longitudes = ",".join(
            str(point[1])
            for point in coordinates
        )

        response = requests.get(
            "https://api.open-meteo.com/v1/elevation",
            params={
                "latitude": latitudes,
                "longitude": longitudes,
            },
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        elevations = data.get(
            "elevation",
            [],
        )

        if len(elevations) != 4:

            return 5.0

        north = float(
            elevations[0]
        )

        south = float(
            elevations[1]
        )

        east = float(
            elevations[2]
        )

        west = float(
            elevations[3]
        )

        north_south_distance = (
            0.02 * 111000
        )

        east_west_distance = (
            0.02
            * 111000
            * math.cos(
                math.radians(
                    latitude
                )
            )
        )

        north_south_gradient = (
            abs(north - south)
            / north_south_distance
        )

        east_west_gradient = (
            abs(east - west)
            / east_west_distance
        )

        gradient = math.sqrt(
            north_south_gradient ** 2
            + east_west_gradient ** 2
        )

        slope_percent = (
            gradient * 100
        )

        return round(
            min(
                slope_percent,
                60,
            ),
            2,
        )

    except Exception as error:

        print(
            "Slope error:",
            error,
        )

        return 5.0


# ---------------------------------------------------------
# GET ENVIRONMENT
# ---------------------------------------------------------

def get_environment(
    latitude,
    longitude,
):

    cache_key = get_cache_key(
        latitude,
        longitude,
    )

    if cache_key in environment_cache:

        print(
            f"Using cached environment "
            f"for {cache_key}"
        )

        return environment_cache[
            cache_key
        ]

    print(
        f"Fetching environment "
        f"for {cache_key}"
    )

    elevation = get_elevation(
        latitude,
        longitude,
    )

    rainfall = get_rainfall(
        latitude,
        longitude,
    )

    slope = get_slope(
        latitude,
        longitude,
    )

    environment = {

        "rainfall": rainfall,

        "elevation": elevation,

        "slope": slope,

    }

    environment_cache[
        cache_key
    ] = environment

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

    if not roads:

        return None

    best_road = None
    best_distance = float("inf")

    # Limit the expensive search to a reasonable
    # number of road records at a time.
    #
    # For the prototype this gives us a real
    # infrastructure lookup without needing
    # a large spatial database.

    for road in roads:

        coordinates = road.get(
            "coordinates",
            [],
        )

        if not coordinates:

            continue

        # Quick bounding-box filter.
        lons = [
            point[0]
            for point in coordinates
        ]

        lats = [
            point[1]
            for point in coordinates
        ]

        min_lon = min(lons)
        max_lon = max(lons)
        min_lat = min(lats)
        max_lat = max(lats)

        # Rough ~15 km search window.
        lat_margin = 0.15

        lon_margin = 0.15

        if (
            latitude < min_lat - lat_margin
            or latitude > max_lat + lat_margin
            or longitude < min_lon - lon_margin
            or longitude > max_lon + lon_margin
        ):

            continue

        road_line = LineString(
            coordinates
        )

        point = Point(
            longitude,
            latitude,
        )

        # Approximate geographic distance.
        nearest_point = road_line.interpolate(
            road_line.project(point)
        )

        distance = haversine_distance(
            latitude,
            longitude,
            nearest_point.y,
            nearest_point.x,
        )

        if distance < best_distance:

            best_distance = distance

            best_road = {

                "name": (
                    road.get("name")
                    or "Unnamed road"
                ),

                "type": road.get(
                    "type",
                    "road",
                ),

                "distance_m": round(
                    distance,
                    1,
                ),

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
