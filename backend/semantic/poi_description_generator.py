"""Deterministic POI natural-language description generation.

This module prepares short text descriptions for future LLM-based reranking.
It does not call external APIs and does not create embeddings.
"""

from __future__ import annotations

from typing import Any

from .utils import (
    describe_count_band,
    get_category_descriptors,
    infer_usage_tendency,
    safe_float,
    simple_region_summary,
)


class POIDescriptionGenerator:
    """Generate three concise natural-language descriptions for one POI."""

    def build_visit_pattern_text(self, poi_metadata: dict[str, Any]) -> str:
        """Describe likely visit behavior from category and popularity signals."""

        category = poi_metadata.get("category_name") or "Unknown category"
        checkins = safe_float(poi_metadata.get("checkins_count"))
        users = safe_float(poi_metadata.get("users_count"))
        event_checkins = safe_float(poi_metadata.get("checkins_count_from_events"))
        usage_tendency = infer_usage_tendency(poi_metadata)

        return (
            f"Visit pattern: {category}. "
            f"Check-in volume is {describe_count_band(checkins)}. "
            f"Visitor breadth is {describe_count_band(users)}. "
            f"Event activity is {describe_count_band(event_checkins)}. "
            f"Likely behavior is {usage_tendency}."
        )

    def build_location_text(self, poi_metadata: dict[str, Any]) -> str:
        """Describe coarse location semantics from latitude and longitude."""

        lat = safe_float(
            poi_metadata.get("latitude", poi_metadata.get("spot_latitude", poi_metadata.get("lat")))
        )
        lon = safe_float(
            poi_metadata.get("longitude", poi_metadata.get("spot_longitude", poi_metadata.get("lng")))
        )

        if lat is None or lon is None:
            return "Location: coordinates are unavailable. Coarse region is unknown."

        region = simple_region_summary(lat, lon)
        return (
            f"Location: latitude {lat:.5f}, longitude {lon:.5f}. "
            f"Coarse region: {region}."
        )

    def build_category_text(self, poi_metadata: dict[str, Any]) -> str:
        """Describe the semantic meaning of the POI category."""

        category = poi_metadata.get("category_name") or "Unknown category"
        descriptors = get_category_descriptors(poi_metadata)

        return (
            f"Category context: primary category is {category}. "
            f"Related labels are {descriptors}. "
            f"This category is the main semantic cue for matching user intent."
        )

    def generate_descriptions(self, poi_metadata: dict[str, Any]) -> dict[str, str]:
        """Return the three deterministic descriptions used by LLM reranking."""

        return {
            "visit_pattern": self.build_visit_pattern_text(poi_metadata),
            "location": self.build_location_text(poi_metadata),
            "category_context": self.build_category_text(poi_metadata),
        }
