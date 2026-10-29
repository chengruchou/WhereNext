"""Road routes for the map, from the Google Routes API.

The key is GOOGLE_MAPS_API_KEY in backend/.env (VITE_GOOGLE_API_KEY is accepted
too), read on each request. Without a key, or when Google returns no route, the
response says why and the map joins the stops with straight dashed lines.
Successful routes are cached by travel mode and coordinates, since the map asks
for the same legs again whenever it redraws.
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

route_bp = Blueprint("route", __name__, url_prefix="/api/route")

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.duration,routes.distanceMeters,routes.polyline.encodedPolyline,routes.viewport"
TRAVEL_MODES = {"DRIVE", "WALK", "TRANSIT", "BICYCLE"}
TIMEOUT_S = 10
CACHE_SIZE = 512

_cache: OrderedDict[tuple, dict[str, Any]] = OrderedDict()


def _api_key() -> str | None:
    return os.getenv("GOOGLE_MAPS_API_KEY") or os.getenv("VITE_GOOGLE_API_KEY")


def _waypoint(lat: float, lng: float) -> dict[str, Any]:
    return {"location": {"latLng": {"latitude": lat, "longitude": lng}}}


def _departure(time: str | None) -> str:
    """Transit needs a departure in the future: the given time or now, plus a minute."""
    now = datetime.now(timezone.utc)
    try:
        asked = datetime.fromisoformat((time or "").replace("Z", "+00:00"))
    except ValueError:
        asked = now
    if asked.tzinfo is None:
        asked = asked.replace(tzinfo=timezone.utc)
    return (max(asked, now) + timedelta(minutes=1)).isoformat()


def _compute(
    mode: str, coords: tuple[tuple[float, float], ...], time: str | None, key: str
) -> dict[str, Any] | None:
    cache_key = (mode, coords)
    if mode != "TRANSIT" and cache_key in _cache:
        _cache.move_to_end(cache_key)
        return _cache[cache_key]

    payload: dict[str, Any] = {
        "origin": _waypoint(*coords[0]),
        "destination": _waypoint(*coords[-1]),
        "travelMode": mode,
        "polylineEncoding": "ENCODED_POLYLINE",
    }
    if mode == "TRANSIT":
        payload["departureTime"] = _departure(time)
    elif len(coords) > 2:
        payload["intermediates"] = [_waypoint(*c) for c in coords[1:-1]]

    try:
        resp = requests.post(
            ROUTES_URL,
            json=payload,
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        logger.warning("Routes API request failed: %s", exc)
        return None
    if resp.status_code != 200:
        logger.warning("Routes API answered %s: %s", resp.status_code, resp.text[:300])
        return None
    routes = resp.json().get("routes") or []
    if not routes:
        return None

    route = routes[0]
    if mode != "TRANSIT":
        _cache[cache_key] = route
        if len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return route


@route_bp.route("/", methods=["POST"])
def get_route():
    rq = request.get_json(silent=True) or {}
    points = rq.get("points") or []
    coords = tuple(
        (float(p["latitude"]), float(p["longitude"]))
        for p in points
        if p and p.get("latitude") is not None and p.get("longitude") is not None
    )
    if len(coords) < 2:
        return jsonify({"message": "A route needs at least two points.", "route": None})

    key = _api_key()
    if not key:
        return jsonify(
            {"message": "Road routes need GOOGLE_MAPS_API_KEY in backend/.env.", "route": None}
        )

    mode = str(rq.get("type") or "DRIVE").upper()
    if mode not in TRAVEL_MODES:
        mode = "DRIVE"

    route = _compute(mode, coords, rq.get("time"), key)
    if route is not None:
        return jsonify({"message": "success", "route": route})
    if mode == "TRANSIT":
        # Many legs have no transit service; walking is the closest road route.
        route = _compute("WALK", coords, None, key)
        if route is not None:
            return jsonify(
                {"message": "No transit route; showing the walking route.", "route": route}
            )
    return jsonify({"message": "Google returned no route for these points.", "route": None})
