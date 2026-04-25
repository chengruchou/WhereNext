"""JSON-backed cache for generated POI descriptions."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DESCRIPTION_HASH_FIELDS = [
    "raw_poi_id",
    "item_id",
    "category_name",
    "raw_categories",
    "latitude",
    "longitude",
    "checkins_count",
    "users_count",
    "checkins_count_from_events",
    "users_count_from_events",
    "photos_count",
    "highlights_count",
    "items_count",
    "radius_meters",
]


def _sanitize_cache_part(value: Any) -> str:
    text = str(value if value is not None else "unknown")
    text = text.strip().replace("/", "-").replace("\\", "-").replace(":", "-")
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-") or "unknown"


def build_description_cache_key(
    poi_metadata: dict[str, Any],
    dataset: str = "Gowalla",
    backend: str = "template",
    model_name: str = "template",
    prompt_version: str = "v1",
) -> str:
    """Build a backend-aware cache key for POI descriptions."""

    raw_poi_id = (
        poi_metadata.get("raw_poi_id")
        or poi_metadata.get("id")
        or poi_metadata.get("raw_location_id")
        or "unknown_poi"
    )
    stable_payload = {
        field: poi_metadata.get(field)
        for field in DESCRIPTION_HASH_FIELDS
        if field in poi_metadata
    }
    metadata_json = json.dumps(stable_payload, ensure_ascii=False, sort_keys=True, default=str)
    metadata_hash = hashlib.sha256(metadata_json.encode("utf-8")).hexdigest()[:8]

    return ":".join(
        [
            _sanitize_cache_part(dataset),
            _sanitize_cache_part(raw_poi_id),
            _sanitize_cache_part(backend),
            _sanitize_cache_part(model_name),
            _sanitize_cache_part(prompt_version),
            metadata_hash,
        ]
    )


class CachedDescriptionStore:
    """Persist generated POI descriptions in a small JSON cache."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data: dict[str, Any] = self._empty_cache()
        self.load()

    def load(self) -> dict[str, Any]:
        """Load the cache file, creating an empty cache if it is missing."""

        if not self.path.exists():
            self.data = self._empty_cache()
            self.save()
            return self.data

        try:
            with self.path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (json.JSONDecodeError, OSError):
            loaded = self._empty_cache()

        if not isinstance(loaded, dict):
            loaded = self._empty_cache()
        loaded.setdefault("meta", self._empty_cache()["meta"])
        loaded.setdefault("items", {})
        if not isinstance(loaded["items"], dict):
            loaded["items"] = {}

        self.data = loaded
        return self.data

    def save(self) -> None:
        """Write the cache to disk."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key: str) -> dict[str, Any] | None:
        """Return a cached entry by key."""

        value = self.data.get("items", {}).get(key)
        return value if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        """Store one cache entry in memory. Call save() to persist it."""

        self.data.setdefault("items", {})[key] = value

    def get_many(self, keys: list[str]) -> dict[str, dict[str, Any]]:
        """Return cached entries for keys that are present."""

        return {key: value for key in keys if (value := self.get(key)) is not None}

    def missing_keys(self, keys: list[str]) -> list[str]:
        """Return keys that are absent from the cache."""

        return [key for key in keys if self.get(key) is None]

    @staticmethod
    def _empty_cache() -> dict[str, Any]:
        return {
            "meta": {
                "cache_type": "poi_descriptions",
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            "items": {},
        }


def run_cache_key_smoke_test() -> dict[str, str]:
    metadata = {
        "raw_poi_id": 8938,
        "item_id": 1089,
        "category_name": "Coffee Shop",
        "latitude": 39.0528237667,
        "longitude": -94.59031105,
    }
    return {
        "template": build_description_cache_key(metadata, backend="template", model_name="template"),
        "llama2_v1": build_description_cache_key(
            metadata,
            backend="llama2",
            model_name="meta-llama/Llama-2-7b-chat-hf",
            prompt_version="v1",
        ),
        "llama2_v2": build_description_cache_key(
            metadata,
            backend="llama2",
            model_name="meta-llama/Llama-2-7b-chat-hf",
            prompt_version="v2",
        ),
    }


if __name__ == "__main__":
    print(json.dumps(run_cache_key_smoke_test(), indent=2))
