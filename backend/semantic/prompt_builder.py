"""Prompt construction for POI semantic views.

This module maps the limited metadata available in this repository onto a
POI-Enhancer-inspired multi-view prompting strategy:

1. Visit-pattern view:
   Uses category, popularity signals, and a heuristic usage tendency derived from
   counts available in stored POI metadata.
2. Address/location view:
   Uses category, coordinates, and a simple region-like location summary derived
   from latitude and longitude.
3. Surrounding/category view:
   Uses category descriptors and whatever semantic context is present in raw
   metadata, such as raw category labels, radius, media counts, and highlights.

This is intentionally an inference-time adaptation only. We do not reproduce the
paper's original training-time semantic optimization pipeline here.
"""

from __future__ import annotations

from .schemas import MultiViewPrompts
from .utils import (
    describe_count_band,
    get_category_descriptors,
    infer_usage_tendency,
    safe_float,
    simple_region_summary,
)


def build_visit_prompt(poi_metadata: dict) -> str:
    """Build the visit-pattern semantic view for one POI.

    POI-Enhancer concept mapping:
    - Prompt generation for visit behavior semantics
    - Adapted here using category + popularity/checkin signals + heuristic usage

    Graceful degradation:
    - If fields are missing, fallback text still yields a valid prompt
    """

    category = poi_metadata.get("category_name") or "Unknown category"
    checkins = safe_float(poi_metadata.get("checkins_count"))
    users = safe_float(poi_metadata.get("users_count"))
    event_checkins = safe_float(poi_metadata.get("checkins_count_from_events"))
    event_users = safe_float(poi_metadata.get("users_count_from_events"))
    usage_tendency = infer_usage_tendency(poi_metadata)

    return (
        f"Visit-pattern view. This POI is a {category}. "
        f"Popularity summary: total checkins={describe_count_band(checkins)}, "
        f"total users={describe_count_band(users)}, "
        f"event checkins={describe_count_band(event_checkins)}, "
        f"event users={describe_count_band(event_users)}. "
        f"Inferred usage tendency: {usage_tendency}."
    )


def build_location_prompt(poi_metadata: dict) -> str:
    """Build the address/location semantic view for one POI.

    POI-Enhancer concept mapping:
    - Prompt generation for address/location semantics
    - Adapted here using category + lat/lng + simple region-like summary
    """

    category = poi_metadata.get("category_name") or "Unknown category"
    lat = safe_float(
        poi_metadata.get("latitude", poi_metadata.get("spot_latitude", poi_metadata.get("lat")))
    )
    lng = safe_float(
        poi_metadata.get("longitude", poi_metadata.get("spot_longitude", poi_metadata.get("lng")))
    )
    region = simple_region_summary(lat, lng)

    coord_text = "coordinates unavailable"
    if lat is not None and lng is not None:
        coord_text = f"latitude={lat:.5f}, longitude={lng:.5f}"

    return (
        f"Address/location view. This POI is a {category}. "
        f"Location summary: {coord_text}. "
        f"Region-like descriptor: {region}."
    )


def build_category_prompt(poi_metadata: dict) -> str:
    """Build the surrounding/category semantic view for one POI.

    POI-Enhancer concept mapping:
    - Prompt generation for surrounding semantic context
    - Adapted here using category descriptors and any available metadata cues
    """

    category = poi_metadata.get("category_name") or "Unknown category"
    category_descriptors = get_category_descriptors(poi_metadata)
    radius = safe_float(poi_metadata.get("radius_meters"))
    photos = safe_float(poi_metadata.get("photos_count"))
    highlights = safe_float(poi_metadata.get("highlights_count"))
    items = safe_float(poi_metadata.get("items_count"))

    return (
        f"Surrounding/category view. Primary category: {category}. "
        f"Category descriptors: {category_descriptors}. "
        f"Nearby semantic context hints: radius={describe_count_band(radius)}, "
        f"photos={describe_count_band(photos)}, "
        f"highlights={describe_count_band(highlights)}, "
        f"items={describe_count_band(items)}."
    )


def build_views(poi_metadata: dict) -> MultiViewPrompts:
    """Build all three semantic prompt views for a POI."""

    return MultiViewPrompts(
        visit_pattern=build_visit_prompt(poi_metadata),
        location=build_location_prompt(poi_metadata),
        category=build_category_prompt(poi_metadata),
    )

