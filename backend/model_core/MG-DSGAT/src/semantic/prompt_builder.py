"""Deterministic POI semantic prompt construction.

This module is Stage 2 M1 only: it builds compact text prompts from filtered
Gowalla POI metadata. It does not embed text, build session profiles, or rerank
candidates.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any


PROMPT_VERSION = "stage2_m1_v1"
SUPPORTED_VIEWS = {"all", "visit_pattern", "location", "category_context"}
COUNT_FIELDS = (
    "checkins_count",
    "users_count",
    "checkins_count_from_events",
    "users_count_from_events",
    "photos_count",
    "highlights_count",
    "items_count",
    "radius_meters",
)
PRESERVED_FIELDS = (
    "item_id",
    "raw_location_id",
    "latitude",
    "longitude",
    "category_id",
    "category_name",
    "raw_categories",
    "checkins_count",
    "users_count",
    "checkins_count_from_events",
    "users_count_from_events",
    "photos_count",
    "highlights_count",
    "items_count",
    "radius_meters",
    "created_at",
)


def normalize_metadata_row(row: dict) -> dict:
    """Normalize one POI metadata row into stable model-side keys."""

    if not isinstance(row, dict):
        raise TypeError(f"metadata row must be a dict, got {type(row).__name__}")

    raw_location_id = _first_int(row, ("raw_poi_id", "raw_location_id", "id"))
    item_id = _first_int(row, ("item_id",))
    latitude = _first_float(row, ("latitude", "spot_latitude", "lat"))
    longitude = _first_float(row, ("longitude", "spot_longitude", "lng", "lon"))

    normalized = {
        "item_id": item_id,
        "raw_location_id": raw_location_id,
        "latitude": latitude,
        "longitude": longitude,
        "category_id": _first_int(row, ("category_id",)),
        "category_name": _clean_text(row.get("category_name")),
        "raw_categories": _normalize_raw_categories(row.get("raw_categories")),
        "checkins_count": _first_float(row, ("checkins_count",)),
        "users_count": _first_float(row, ("users_count",)),
        "checkins_count_from_events": _first_float(row, ("checkins_count_from_events",)),
        "users_count_from_events": _first_float(row, ("users_count_from_events",)),
        "photos_count": _first_float(row, ("photos_count",)),
        "highlights_count": _first_float(row, ("highlights_count",)),
        "items_count": _first_float(row, ("items_count",)),
        "radius_meters": _first_float(row, ("radius_meters",)),
        "created_at": _clean_text(row.get("created_at")),
    }
    return normalized


def build_poi_prompt(metadata: dict, view: str = "all") -> str:
    """Build a compact deterministic semantic prompt for one POI."""

    if view not in SUPPORTED_VIEWS:
        raise ValueError(f"Unsupported prompt view: {view}. Expected one of {sorted(SUPPORTED_VIEWS)}")

    row = normalize_metadata_row(metadata)
    if view == "visit_pattern":
        return _build_visit_pattern_prompt(row)
    if view == "location":
        return _build_location_prompt(row)
    if view == "category_context":
        return _build_category_context_prompt(row)
    return _build_all_prompt(row)


def build_multi_view_prompts(metadata: dict) -> dict[str, str]:
    """Build all supported prompt views for one POI."""

    return {
        "all": build_poi_prompt(metadata, view="all"),
        "visit_pattern": build_poi_prompt(metadata, view="visit_pattern"),
        "location": build_poi_prompt(metadata, view="location"),
        "category_context": build_poi_prompt(metadata, view="category_context"),
    }


def metadata_hash(metadata: dict) -> str:
    """Return a stable SHA256 hash of normalized metadata."""

    normalized = normalize_metadata_row(metadata)
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prompt_hash(prompt: str) -> str:
    """Return a SHA256 hash of prompt text."""

    return hashlib.sha256(str(prompt).encode("utf-8")).hexdigest()


def build_prompt_cache(metadata_rows: list[dict], view: str = "all") -> list[dict]:
    """Build prompt cache rows for one prompt view or all views."""

    if view != "multi_view" and view not in SUPPORTED_VIEWS:
        raise ValueError(
            f"Unsupported prompt cache view: {view}. Expected all, visit_pattern, "
            "location, category_context, or multi_view."
        )

    cache_rows = []
    for metadata in metadata_rows:
        normalized = normalize_metadata_row(metadata)
        base = {
            "item_id": normalized.get("item_id"),
            "raw_location_id": normalized.get("raw_location_id"),
            "prompt_version": PROMPT_VERSION,
            "metadata_hash": metadata_hash(normalized),
            "metadata_summary": metadata_summary(normalized),
        }
        if view == "multi_view":
            prompts = build_multi_view_prompts(normalized)
            cache_rows.append(
                {
                    **base,
                    "view": "multi_view",
                    "prompts": prompts,
                    "prompt_hashes": {
                        prompt_view: prompt_hash(prompt)
                        for prompt_view, prompt in prompts.items()
                    },
                }
            )
            continue

        prompt = build_poi_prompt(normalized, view=view)
        cache_rows.append(
            {
                **base,
                "view": view,
                "prompt": prompt,
                "prompt_hash": prompt_hash(prompt),
            }
        )
    return cache_rows


def metadata_summary(metadata: dict) -> dict:
    """Create a compact stable metadata summary for cache diagnostics."""

    row = normalize_metadata_row(metadata)
    return {
        "category_name": row.get("category_name"),
        "has_coordinates": row.get("latitude") is not None and row.get("longitude") is not None,
        "has_visit_counts": any(row.get(field) is not None for field in COUNT_FIELDS),
        "raw_category_names": raw_category_names(row.get("raw_categories")),
        "count_fields_present": [
            field for field in COUNT_FIELDS if row.get(field) is not None
        ],
    }


def raw_category_names(raw_categories: Any) -> list[str]:
    """Extract stable raw category names."""

    categories = _normalize_raw_categories(raw_categories)
    names = []
    for category in categories:
        name = _clean_text(category.get("name"))
        if name and name not in names:
            names.append(name)
    return names


def _build_all_prompt(row: dict) -> str:
    parts = ["POI semantic profile."]
    parts.append(f"Category/function: {_category_text(row)}.")

    location = _coordinate_sentence(row)
    if location:
        parts.append(location)

    visit = _visit_sentence(row)
    if visit:
        parts.append(visit)

    activity = _activity_sentence(row)
    if activity:
        parts.append(activity)

    return " ".join(parts)


def _build_visit_pattern_prompt(row: dict) -> str:
    parts = ["POI visit pattern."]
    observed_checkins = _format_count(row.get("checkins_count_from_events"))
    observed_users = _format_count(row.get("users_count_from_events"))
    public_checkins = _format_count(row.get("checkins_count"))
    public_users = _format_count(row.get("users_count"))

    if observed_checkins is not None:
        parts.append(f"Observed check-ins: {observed_checkins}.")
    if observed_users is not None:
        parts.append(f"Observed users: {observed_users}.")
    if public_checkins is not None:
        parts.append(f"Public check-ins: {public_checkins}.")
    if public_users is not None:
        parts.append(f"Public users: {public_users}.")
    if len(parts) == 1:
        parts.append("Visit statistics unavailable.")
    return " ".join(parts)


def _build_location_prompt(row: dict) -> str:
    parts = ["POI location context."]
    lat = row.get("latitude")
    lon = row.get("longitude")
    if lat is not None and lon is not None:
        parts.append(f"Latitude: {_format_float(lat)}.")
        parts.append(f"Longitude: {_format_float(lon)}.")
    else:
        parts.append("Coordinates unavailable.")

    radius = _format_count(row.get("radius_meters"))
    if radius is not None:
        parts.append(f"Radius: {radius} meters.")
    return " ".join(parts)


def _build_category_context_prompt(row: dict) -> str:
    category = _category_text(row)
    raw_names = raw_category_names(row.get("raw_categories"))
    parts = ["POI functional context.", f"Category: {category}."]
    if raw_names:
        parts.append(f"Raw categories: {', '.join(raw_names)}.")
    else:
        parts.append("Raw categories unavailable.")
    parts.append("This describes the likely function of the POI, without inferring unavailable facts.")
    return " ".join(parts)


def _category_text(row: dict) -> str:
    category = _clean_text(row.get("category_name"))
    return category or "unknown"


def _coordinate_sentence(row: dict) -> str | None:
    lat = row.get("latitude")
    lon = row.get("longitude")
    if lat is None or lon is None:
        return None
    return f"Location: latitude {_format_float(lat)}, longitude {_format_float(lon)}."


def _visit_sentence(row: dict) -> str | None:
    phrases = []
    observed_checkins = _format_count(row.get("checkins_count_from_events"))
    observed_users = _format_count(row.get("users_count_from_events"))
    public_checkins = _format_count(row.get("checkins_count"))
    public_users = _format_count(row.get("users_count"))

    if observed_checkins is not None and observed_users is not None:
        phrases.append(f"{observed_checkins} observed check-ins by {observed_users} observed users")
    elif observed_checkins is not None:
        phrases.append(f"{observed_checkins} observed check-ins")
    elif observed_users is not None:
        phrases.append(f"{observed_users} observed users")

    if public_checkins is not None and public_users is not None:
        phrases.append(f"public metadata reports {public_checkins} check-ins and {public_users} users")
    elif public_checkins is not None:
        phrases.append(f"public metadata reports {public_checkins} check-ins")
    elif public_users is not None:
        phrases.append(f"public metadata reports {public_users} users")

    if not phrases:
        return None
    return f"Visit pattern: {'; '.join(phrases)}."


def _activity_sentence(row: dict) -> str | None:
    fields = [
        ("photos", row.get("photos_count")),
        ("highlights", row.get("highlights_count")),
        ("items", row.get("items_count")),
    ]
    entries = [
        f"{label}={formatted}"
        for label, value in fields
        if (formatted := _format_count(value)) is not None
    ]
    if not entries:
        return None
    return f"Activity indicators: {', '.join(entries)}."


def _normalize_raw_categories(raw_categories: Any) -> list[dict[str, Any]]:
    if raw_categories is None:
        return []
    if isinstance(raw_categories, list):
        normalized = []
        for entry in raw_categories:
            if isinstance(entry, dict):
                clean_entry = {}
                if "name" in entry:
                    clean_entry["name"] = _clean_text(entry.get("name"))
                if "url" in entry:
                    clean_entry["url"] = _clean_text(entry.get("url"))
                for key, value in entry.items():
                    if key not in clean_entry and (
                        isinstance(value, (str, int, float, bool)) or value is None
                    ):
                        clean_entry[key] = value
                normalized.append(clean_entry)
            elif entry is not None:
                normalized.append({"name": str(entry).strip()})
        return normalized
    if isinstance(raw_categories, dict):
        return _normalize_raw_categories([raw_categories])
    return [{"name": str(raw_categories).strip()}] if str(raw_categories).strip() else []


def _first_int(row: dict, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = _safe_int(row.get(key))
        if value is not None:
            return value
    return None


def _first_float(row: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _safe_float(row.get(key))
        if value is not None:
            return value
    return None


def _safe_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    if abs(numeric - round(numeric)) > 1e-6:
        return None
    return int(round(numeric))


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return float(numeric)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_float(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _format_count(value: Any) -> str | None:
    numeric = _safe_float(value)
    if numeric is None:
        return None
    if abs(numeric - round(numeric)) < 1e-6:
        return str(int(round(numeric)))
    return f"{numeric:.3f}".rstrip("0").rstrip(".")
