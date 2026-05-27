"""Spatial candidate expansion for SBR top-k predictions."""

from __future__ import annotations

from typing import Any


def expand_candidates_with_spatial_neighbors(
    sbr_candidates: list[dict[str, Any]],
    history_raw_ids: list[int],
    spatial_index,
    spatial_k: int,
    exclude_seen: bool = True,
) -> list[dict[str, Any]]:
    """Merge SBR candidates with nearest spatial neighbors of the last POI.

    SBR rows are preserved. Spatial-only rows are appended in spatial-rank
    order. Candidates present in both sources are merged and marked
    ``sbr+spatial``.
    """

    expanded_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    ordered_rows: list[dict[str, Any]] = []

    for sbr_rank, candidate in enumerate(
        sorted(sbr_candidates, key=lambda row: int(row.get("rank", 10**9))),
        start=1,
    ):
        row = dict(candidate)
        row.setdefault("sbr_rank", int(row.get("rank", sbr_rank)))
        row.setdefault("original_sbr_rank", int(row.get("rank", sbr_rank)))
        row.setdefault("sbr_score", float(row.get("score", row.get("sbr_score", 0.0))))
        row.setdefault("candidate_source", "sbr")
        row["rank"] = int(row.get("rank", sbr_rank))
        key = _candidate_key(row)
        if key is None:
            key = ("__row__", len(ordered_rows))
        expanded_by_key[key] = row
        ordered_rows.append(row)

    if not history_raw_ids:
        return _renumber_expanded(ordered_rows)

    last_raw_id = int(history_raw_ids[-1])
    exclude_raw_ids = set(int(raw_id) for raw_id in history_raw_ids) if exclude_seen else set()
    try:
        spatial_candidates = spatial_index.get_nearest_by_raw_location_id(
            raw_location_id=last_raw_id,
            k=spatial_k,
            exclude_raw_ids=exclude_raw_ids,
        )
    except KeyError:
        return _renumber_expanded(ordered_rows)

    for spatial_row in sorted(spatial_candidates, key=lambda row: int(row["spatial_rank"])):
        row_key = _candidate_key(spatial_row)
        if row_key is not None and row_key in expanded_by_key:
            existing = expanded_by_key[row_key]
            existing["candidate_source"] = "sbr+spatial"
            existing["spatial_rank"] = int(spatial_row["spatial_rank"])
            existing["spatial_score"] = float(spatial_row["spatial_score"])
            existing["distance_km"] = float(spatial_row["distance_km"])
            existing.setdefault("raw_location_id", int(spatial_row["raw_location_id"]))
            if spatial_row.get("item_id") is not None:
                existing.setdefault("item_id", int(spatial_row["item_id"]))
            _copy_optional_metadata(existing, spatial_row)
            continue

        new_row = {
            "rank": len(ordered_rows) + 1,
            "item_id": (
                None if spatial_row.get("item_id") is None else int(spatial_row["item_id"])
            ),
            "raw_location_id": int(spatial_row["raw_location_id"]),
            "score": 0.0,
            "sbr_score": None,
            "sbr_rank": None,
            "original_sbr_rank": None,
            "spatial_score": float(spatial_row["spatial_score"]),
            "spatial_rank": int(spatial_row["spatial_rank"]),
            "distance_km": float(spatial_row["distance_km"]),
            "candidate_source": "spatial",
        }
        _copy_optional_metadata(new_row, spatial_row)
        if row_key is None:
            row_key = ("raw_location_id", int(spatial_row["raw_location_id"]))
        expanded_by_key[row_key] = new_row
        ordered_rows.append(new_row)

    return _renumber_expanded(ordered_rows)


def _candidate_key(row: dict[str, Any]) -> tuple[str, int] | None:
    item_id = row.get("item_id")
    if item_id is not None:
        try:
            return ("item_id", int(item_id))
        except (TypeError, ValueError):
            pass
    raw_id = row.get("raw_location_id")
    if raw_id is not None:
        try:
            return ("raw_location_id", int(raw_id))
        except (TypeError, ValueError):
            pass
    return None


def _renumber_expanded(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def _copy_optional_metadata(target: dict[str, Any], source: dict[str, Any]) -> None:
    for field in ("latitude", "longitude", "category_id", "category_name", "name"):
        if field in source and field not in target:
            target[field] = source[field]

