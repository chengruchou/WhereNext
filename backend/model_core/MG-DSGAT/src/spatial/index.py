"""Spatial nearest-neighbor index for POI candidate expansion."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

try:
    from sklearn.neighbors import BallTree
except ImportError:  # pragma: no cover - exercised only in minimal envs
    BallTree = None


EARTH_RADIUS_KM = 6371.0088


def haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Compute the great-circle distance between two latitude/longitude pairs."""

    lat1_rad = math.radians(float(lat1))
    lon1_rad = math.radians(float(lon1))
    lat2_rad = math.radians(float(lat2))
    lon2_rad = math.radians(float(lon2))

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = (
        math.sin(dlat / 2.0) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


class SpatialCandidateIndex:
    """Nearest-neighbor lookup over POI coordinates.

    The preferred backend is sklearn's BallTree with the haversine metric. If
    sklearn is not available, the class falls back to a linear haversine scan so
    smoke tests still work, albeit much more slowly for full Gowalla.
    """

    _CACHE: dict[str, dict[str, Any]] = {}

    def __init__(self, poi_metadata_json: str | Path):
        self.poi_metadata_json = str(Path(poi_metadata_json).resolve())
        cached = self._CACHE.get(self.poi_metadata_json)
        if cached is None:
            cached = self._build_index(Path(self.poi_metadata_json))
            self._CACHE[self.poi_metadata_json] = cached

        self.metadata_rows: list[dict[str, Any]] = cached["metadata_rows"]
        self.raw_id_to_index: dict[int, int] = cached["raw_id_to_index"]
        self.coordinates_rad: np.ndarray = cached["coordinates_rad"]
        self.tree = cached["tree"]

    def get_nearest_by_raw_location_id(
        self,
        raw_location_id: int,
        k: int,
        exclude_raw_ids: set[int] | list[int] | tuple[int, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """Return the k nearest POIs to a raw location id.

        The query POI itself is always excluded. Returned rows include
        raw_location_id, item_id when available, distance_km, spatial_rank, and
        spatial_score = 1 / (1 + distance_km).
        """

        query_raw_id = int(raw_location_id)
        if query_raw_id not in self.raw_id_to_index:
            raise KeyError(f"raw_location_id not found in spatial index: {query_raw_id}")

        target_count = max(int(k), 0)
        if target_count == 0:
            return []

        exclude = {query_raw_id}
        if exclude_raw_ids:
            exclude.update(int(raw_id) for raw_id in exclude_raw_ids)

        if self.tree is None:
            return self._nearest_by_linear_scan(query_raw_id, target_count, exclude)
        return self._nearest_by_balltree(query_raw_id, target_count, exclude)

    @classmethod
    def _build_index(cls, metadata_path: Path) -> dict[str, Any]:
        if not metadata_path.exists():
            raise FileNotFoundError(f"POI metadata file not found: {metadata_path}")

        with metadata_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        rows = cls._normalize_metadata(payload)
        if not rows:
            raise ValueError(f"No POIs with valid coordinates found in {metadata_path}")

        coordinates_rad = np.asarray(
            [
                [math.radians(row["latitude"]), math.radians(row["longitude"])]
                for row in rows
            ],
            dtype=np.float64,
        )
        tree = None
        if BallTree is not None:
            tree = BallTree(coordinates_rad, metric="haversine")

        return {
            "metadata_rows": rows,
            "raw_id_to_index": {
                int(row["raw_location_id"]): index for index, row in enumerate(rows)
            },
            "coordinates_rad": coordinates_rad,
            "tree": tree,
        }

    @staticmethod
    def _normalize_metadata(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            iterable = payload.items()
        elif isinstance(payload, list):
            iterable = enumerate(payload)
        else:
            raise ValueError("POI metadata JSON must be an object or list.")

        rows: list[dict[str, Any]] = []
        for key, metadata in iterable:
            if not isinstance(metadata, dict):
                continue

            raw_id = (
                metadata.get("raw_location_id")
                or metadata.get("raw_poi_id")
                or metadata.get("poi_id")
                or metadata.get("id")
                or key
            )
            latitude = metadata.get("latitude", metadata.get("lat"))
            longitude = metadata.get("longitude", metadata.get("lng", metadata.get("lon")))
            try:
                raw_id = int(raw_id)
                latitude = float(latitude)
                longitude = float(longitude)
            except (TypeError, ValueError):
                continue

            if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
                continue

            item_id = metadata.get("item_id")
            try:
                item_id = int(item_id) if item_id is not None else None
            except (TypeError, ValueError):
                item_id = None

            row = {
                "raw_location_id": raw_id,
                "item_id": item_id,
                "latitude": latitude,
                "longitude": longitude,
            }
            for field in ("category_id", "category_name", "name"):
                if field in metadata:
                    row[field] = metadata[field]
            rows.append(row)

        return rows

    def _nearest_by_balltree(
        self,
        query_raw_id: int,
        target_count: int,
        exclude: set[int],
    ) -> list[dict[str, Any]]:
        query_index = self.raw_id_to_index[query_raw_id]
        query_point = self.coordinates_rad[query_index : query_index + 1]
        search_k = min(len(self.metadata_rows), target_count + len(exclude) + 1)
        results: list[dict[str, Any]] = []
        used_raw_ids: set[int] = set()

        while True:
            distances_rad, indices = self.tree.query(query_point, k=search_k)
            for distance_rad, index in zip(distances_rad[0], indices[0]):
                metadata = self.metadata_rows[int(index)]
                raw_id = int(metadata["raw_location_id"])
                if raw_id in exclude or raw_id in used_raw_ids:
                    continue
                used_raw_ids.add(raw_id)
                results.append(self._format_neighbor(metadata, float(distance_rad) * EARTH_RADIUS_KM, len(results) + 1))
                if len(results) >= target_count:
                    return results

            if search_k >= len(self.metadata_rows):
                return results
            search_k = min(len(self.metadata_rows), search_k * 2)

    def _nearest_by_linear_scan(
        self,
        query_raw_id: int,
        target_count: int,
        exclude: set[int],
    ) -> list[dict[str, Any]]:
        query_row = self.metadata_rows[self.raw_id_to_index[query_raw_id]]
        distances: list[tuple[float, dict[str, Any]]] = []
        for row in self.metadata_rows:
            raw_id = int(row["raw_location_id"])
            if raw_id in exclude:
                continue
            distance_km = haversine_distance_km(
                query_row["latitude"],
                query_row["longitude"],
                row["latitude"],
                row["longitude"],
            )
            distances.append((distance_km, row))

        distances.sort(key=lambda pair: pair[0])
        return [
            self._format_neighbor(row, distance_km, rank)
            for rank, (distance_km, row) in enumerate(distances[:target_count], start=1)
        ]

    @staticmethod
    def _format_neighbor(
        metadata: dict[str, Any],
        distance_km: float,
        spatial_rank: int,
    ) -> dict[str, Any]:
        row = {
            "raw_location_id": int(metadata["raw_location_id"]),
            "item_id": metadata.get("item_id"),
            "latitude": float(metadata["latitude"]),
            "longitude": float(metadata["longitude"]),
            "distance_km": float(distance_km),
            "spatial_rank": int(spatial_rank),
            "spatial_score": 1.0 / (1.0 + float(distance_km)),
        }
        for field in ("category_id", "category_name", "name"):
            if field in metadata:
                row[field] = metadata[field]
        return row

