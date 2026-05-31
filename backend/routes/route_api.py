import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from flask import Blueprint, jsonify, request

route_bp = Blueprint("route", __name__, url_prefix="/api/route")

load_dotenv(dotenv_path="../frontend/.env")
api_key = os.getenv("VITE_GOOGLE_API_KEY")

intermediates = [
    {
        "location": {
            "latLng": {"latitude": 25.183606029570072, "longitude": 121.41165835109268}
        }
    }
]


@route_bp.route("/", methods=["POST"])
def get_route():
    rq = request.json
    if len(rq) <= 1:
        return jsonify("")

    def to_waypoint(point):
        return {
            "location": {
                "latLng": {
                    "latitude": point["latitude"],
                    "longitude": point["longitude"],
                }
            }
        }

    points = rq["points"]
    time = rq["time"]
    type = rq["type"]

    time_utc = datetime.fromisoformat(time.replace("Z", "+00:00"))
    time_taiwan = time_utc.astimezone(ZoneInfo("Asia/Taipei")) + timedelta(minutes=1)
    time_str = time_taiwan.isoformat()

    origin = to_waypoint(points[0])
    destination = to_waypoint(points[-1])
    intermediates = [to_waypoint(e) for e in points[1:-1]]

    payload = {
        "origin": origin,
        "destination": destination,
        "travelMode": type,
        "polylineEncoding": "ENCODED_POLYLINE",
    }

    if type != "TRANSIT":
        payload["intermediates"] = intermediates
    else:
        payload["departureTime"] = time_str

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.viewport",
    }
    resp = (
        requests.session()
        .post(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            json=payload,
            headers=headers,
        )
        .json()
    )
    # print(resp)

    no_route = not resp or "routes" not in resp

    if no_route:
        payload["travelMode"] = "WALK"
        resp = (
            requests.session()
            .post(
                "https://routes.googleapis.com/directions/v2:computeRoutes",
                json=payload,
                headers=headers,
            )
            .json()
        )
        if not resp or "routes" not in resp:
            return jsonify({"message": "Fail to fetch route", "route": None})
        else:
            return jsonify(
                {
                    "message": "Fail to fetch route for Transit mode, fallback to walking mode",
                    "route": resp["routes"][0],
                }
            )

    else:
        return jsonify({"message": "success", "route": resp["routes"][0]})
