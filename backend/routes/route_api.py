import os

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
    
    rq = rq.reverse()

    origin = to_waypoint(rq[0])
    destination = to_waypoint(rq[-1])
    intermediates = [to_waypoint(e) for e in rq[1:-1]]

    payload = {
        "origin": origin,
        "destination": destination,
        "intermediates": intermediates,
        "travelMode": "WALK",
        "polylineEncoding": "ENCODED_POLYLINE",
    }

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline",
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

    return jsonify(resp["routes"][0])
