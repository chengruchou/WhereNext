#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Build Gowalla dataset artifacts for the current SBR pipeline.

Main outputs:
- train.txt                  : pickle((train_prefixes, train_targets))
- test.txt                   : pickle((test_prefixes, test_targets))
- train_with_timestamps.json : event-level supervised train examples
- test_with_timestamps.json  : event-level supervised test examples
- all_train_seq.txt          : pickle(list_of_full_train_sessions)
- raw_location2item.json     : raw_poi_id -> internal_item_id (1-based)
- item2raw_location.json     : internal_item_id -> raw_poi_id
- build_manifest.json        : preprocessing metadata
- poi_metadata.json          : optional metadata for semantic ID / reranking

Design goal:
- Keep the SBR backbone input unchanged
- Do NOT inject category into SBR train/test session artifacts
- Generate a separate POI metadata layer for later semantic ID / reranking

Example:
    python src/build_gowalla_dataset.py ^
        --input datasets\\ca\\loc-gowalla_totalCheckins.txt ^
        --spots_input datasets\\ca\\gowalla_spots_subset1.csv ^
        --output_dir datasets\\Gowalla ^
        --session_interval_days 1 ^
        --max_session_len 20 ^
        --min_session_len 2 ^
        --min_item_support 5 ^
        --top_n_items 30000 ^
        --test_split 0.2 ^
        --save_poi_metadata
        
    python .\src\build_gowalla_dataset.py `
        --input datasets\ca\loc-gowalla_totalCheckins.txt `
        --spots_input datasets\ca\gowalla_spots_subset1.csv `
        --output_dir datasets\Gowalla `
        --session_interval_days 1 `
        --max_session_len 20 `
        --min_session_len 2 `
        --min_item_support 5 `
        --top_n_items 30000 `
        --test_split 0.2 `
        --save_poi_metadata
"""

import argparse
import ast
import json
import os
import pickle
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class BuildConfig:
    input: str
    output_dir: str
    spots_input: str = ""
    session_interval_days: int = 1
    max_session_len: int = 20
    min_session_len: int = 2
    min_item_support: int = 5
    top_n_items: int = 30000
    test_split: float = 0.2
    save_poi_metadata: bool = False


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def save_pickle(obj, path: str) -> None:
    with open(path, "wb") as f:
        pickle.dump(obj, f)


def save_json(obj, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def read_raw_gowalla(path: str) -> pd.DataFrame:
    """
    Read raw Gowalla total checkins file.

    Expected format:
    user_id \t timestamp \t latitude \t longitude \t raw_poi_id
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input file not found: {path}")

    df = pd.read_csv(
        path,
        sep="\t",
        header=None,
        names=["user_id", "timestamp", "latitude", "longitude", "raw_poi_id"],
        parse_dates=["timestamp"],
    )

    df = df.dropna(subset=["user_id", "timestamp", "raw_poi_id"])
    df["user_id"] = df["user_id"].astype(int)
    df["raw_poi_id"] = df["raw_poi_id"].astype(int)

    if "latitude" in df.columns:
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    if "longitude" in df.columns:
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")

    return df


def assign_sessions(df: pd.DataFrame, session_interval_days: int) -> pd.DataFrame:
    """
    Split user trajectories into sessions by time gap.
    """
    df = df.sort_values(["user_id", "timestamp"]).reset_index(drop=True)

    prev_user = df["user_id"].shift(1)
    prev_time = df["timestamp"].shift(1)

    is_new_user = df["user_id"] != prev_user
    is_new_gap = (df["timestamp"] - prev_time) > pd.Timedelta(days=session_interval_days)
    is_new_session = is_new_user | is_new_gap
    df["session_id"] = is_new_session.cumsum().astype(int) - 1
    return df


def remove_immediate_repeats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove consecutive repeated POIs within the same session.
    """
    prev_session = df["session_id"].shift(1)
    prev_poi = df["raw_poi_id"].shift(1)

    keep = (df["session_id"] != prev_session) | (df["raw_poi_id"] != prev_poi)
    return df[keep].copy()


def truncate_long_sessions(df: pd.DataFrame, max_session_len: int) -> pd.DataFrame:
    """
    Keep only the first max_session_len events in each session.
    """
    df = df.sort_values(["session_id", "timestamp"]).copy()
    df["event_rank"] = df.groupby("session_id").cumcount()
    df = df[df["event_rank"] < max_session_len].copy()
    df = df.drop(columns=["event_rank"])
    return df


def keep_top_n_items(df: pd.DataFrame, top_n_items: int) -> pd.DataFrame:
    """
    Keep only the top-N most frequent POIs.
    """
    item_support = df.groupby("raw_poi_id").size()
    top_items = item_support.nlargest(top_n_items).index
    return df[df["raw_poi_id"].isin(top_items)].copy()


def filter_short_sessions(df: pd.DataFrame, min_session_len: int) -> pd.DataFrame:
    """
    Keep only sessions whose length >= min_session_len.
    """
    session_len = df.groupby("session_id").size()
    valid_sessions = session_len[session_len >= min_session_len].index
    return df[df["session_id"].isin(valid_sessions)].copy()


def filter_infreq_items(df: pd.DataFrame, min_item_support: int) -> pd.DataFrame:
    """
    Keep only items whose support >= min_item_support.
    """
    item_support = df.groupby("raw_poi_id").size()
    valid_items = item_support[item_support >= min_item_support].index
    return df[df["raw_poi_id"].isin(valid_items)].copy()


def iterative_filter(
    df: pd.DataFrame,
    min_session_len: int,
    min_item_support: int,
) -> pd.DataFrame:
    """
    Iteratively enforce session length and item support constraints until convergence.
    """
    while True:
        before = len(df)
        df = filter_short_sessions(df, min_session_len)
        df = filter_infreq_items(df, min_item_support)
        after = len(df)
        if after == before:
            break
    return df.copy()


def split_train_test_by_session_end_time(
    df: pd.DataFrame,
    test_split: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split sessions chronologically by session end time.
    """
    session_end = df.groupby("session_id")["timestamp"].max().sort_values()

    n_test = max(1, int(len(session_end) * test_split))
    test_session_ids = session_end.index[-n_test:]

    train_df = df[~df["session_id"].isin(test_session_ids)].copy()
    test_df = df[df["session_id"].isin(test_session_ids)].copy()
    return train_df, test_df


def build_item_mapping_from_train(train_df: pd.DataFrame) -> Tuple[Dict[int, int], Dict[int, int]]:
    """
    Build raw_poi_id -> internal_item_id mapping from train POIs only.

    internal_item_id starts from 1 because 0 is reserved for padding.
    """
    unique_train_pois = pd.Index(train_df["raw_poi_id"].unique())
    raw2item = {int(raw_poi): int(i + 1) for i, raw_poi in enumerate(unique_train_pois)}
    item2raw = {v: k for k, v in raw2item.items()}
    return raw2item, item2raw


def apply_item_mapping(
    df: pd.DataFrame,
    raw2item: Dict[int, int],
) -> pd.DataFrame:
    """
    Map raw_poi_id to internal item_id.
    Rows with unseen raw_poi_id will become NaN and can be dropped later.
    """
    df = df.copy()
    df["item_id"] = df["raw_poi_id"].map(raw2item)
    return df


def filter_test_after_mapping(
    test_df: pd.DataFrame,
    min_session_len: int,
) -> pd.DataFrame:
    """
    After train-based item mapping, remove unseen items and short test sessions.
    """
    test_df = test_df.dropna(subset=["item_id"]).copy()
    test_df["item_id"] = test_df["item_id"].astype(int)
    test_df = filter_short_sessions(test_df, min_session_len=min_session_len)
    return test_df


def group_sessions_as_sequences(
    df: pd.DataFrame,
    item_col: str = "item_id",
) -> List[List[int]]:
    """
    Convert event rows into full ordered session sequences.
    """
    df = df.sort_values(["session_id", "timestamp"]).copy()
    grouped = df.groupby("session_id")[item_col].apply(list)
    return grouped.tolist()


def make_supervised_examples(full_sessions: List[List[int]]) -> Tuple[List[List[int]], List[int]]:
    """
    Convert full sessions into (prefix, target) pairs.
    Example:
        [1,2,3,4] -> ([1],2), ([1,2],3), ([1,2,3],4)
    """
    prefixes: List[List[int]] = []
    targets: List[int] = []

    for seq in full_sessions:
        if len(seq) < 2:
            continue
        for i in range(1, len(seq)):
            prefixes.append(seq[:i])
            targets.append(seq[i])

    return prefixes, targets


def format_timestamp_iso(timestamp) -> str:
    """
    Format a pandas timestamp as the Gowalla-style UTC ISO string.
    """
    ts = pd.Timestamp(timestamp)
    if pd.isna(ts):
        raise ValueError("Cannot format missing timestamp.")
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def group_sessions_as_event_sequences(df: pd.DataFrame) -> List[List[dict]]:
    """
    Convert event rows into full ordered session event sequences.

    This intentionally mirrors group_sessions_as_sequences() so timestamp
    artifacts preserve the exact same session order and event order used by
    train.txt/test.txt.
    """
    df = df.sort_values(["session_id", "timestamp"]).copy()
    event_sessions: List[List[dict]] = []

    for _, session_df in df.groupby("session_id"):
        events: List[dict] = []
        for _, row in session_df.iterrows():
            events.append(
                {
                    "item_id": int(row["item_id"]),
                    "raw_location_id": int(row["raw_poi_id"]),
                    "timestamp": format_timestamp_iso(row["timestamp"]),
                }
            )
        event_sessions.append(events)

    return event_sessions


def make_supervised_event_examples(event_sessions: List[List[dict]]) -> List[dict]:
    """
    Convert event sessions into timestamp-aware prefix-target examples.

    The prefix-target loop is the same as make_supervised_examples().
    """
    samples: List[dict] = []
    sample_id = 0

    for session in event_sessions:
        if len(session) < 2:
            continue
        for i in range(1, len(session)):
            samples.append(
                {
                    "sample_id": sample_id,
                    "history_events": session[:i],
                    "target_event": session[i],
                }
            )
            sample_id += 1

    return samples


def validate_event_examples_against_pickle(
    pickle_path: str,
    event_examples: List[dict],
) -> None:
    """
    Ensure timestamp-aware examples match the existing MG-DSGAT examples.
    """
    with open(pickle_path, "rb") as f:
        prefixes, targets = pickle.load(f)

    if len(prefixes) != len(event_examples) or len(targets) != len(event_examples):
        raise ValueError(
            "Timestamp artifact validation failed: "
            f"pickle examples={len(prefixes)}, event examples={len(event_examples)}"
        )

    for index, (history_item_ids, target_item_id, event_sample) in enumerate(
        zip(prefixes, targets, event_examples)
    ):
        event_history_ids = [
            int(event["item_id"])
            for event in event_sample["history_events"]
        ]
        event_target_id = int(event_sample["target_event"]["item_id"])

        if event_history_ids != [int(item_id) for item_id in history_item_ids]:
            raise ValueError(
                "Timestamp artifact validation failed at sample "
                f"{index}: history mismatch"
            )
        if event_target_id != int(target_item_id):
            raise ValueError(
                "Timestamp artifact validation failed at sample "
                f"{index}: target mismatch"
            )


def parse_category_cell(cell) -> Tuple[Optional[int], Optional[str], list]:
    """
    Parse category-like columns such as:
    "[{'url': '/categories/45', 'name': 'Airport'}]"

    Returns:
        (category_id, category_name, raw_categories)
    """
    if pd.isna(cell):
        return None, None, []

    if isinstance(cell, list):
        raw_categories = cell
    else:
        text = str(cell).strip()
        if not text:
            return None, None, []
        try:
            raw_categories = ast.literal_eval(text)
        except Exception:
            return None, None, []

    if not isinstance(raw_categories, list) or len(raw_categories) == 0:
        return None, None, []

    first = raw_categories[0]
    if not isinstance(first, dict):
        return None, None, raw_categories

    category_name = first.get("name")
    category_url = first.get("url")

    category_id = None
    if isinstance(category_url, str):
        parts = category_url.rstrip("/").split("/")
        if parts:
            tail = parts[-1]
            if tail.isdigit():
                category_id = int(tail)

    return category_id, category_name, raw_categories


def read_spots_metadata(spots_path: str) -> pd.DataFrame:
    """
    Read Gowalla spots metadata file.

    Expected columns include:
    id, created_at, lng, lat, photos_count, checkins_count, users_count,
    radius_meters, highlights_count, items_count, max_items_count, spot_categories
    """
    if not spots_path:
        raise ValueError("Empty spots_input path.")
    if not os.path.exists(spots_path):
        raise FileNotFoundError(f"Spots metadata file not found: {spots_path}")

    spots = pd.read_csv(spots_path)

    required = ["id", "lat", "lng"]
    for col in required:
        if col not in spots.columns:
            raise ValueError(f"Missing required spots column: {col}")

    spots = spots.rename(columns={"id": "raw_poi_id", "lat": "spot_latitude", "lng": "spot_longitude"})
    spots["raw_poi_id"] = pd.to_numeric(spots["raw_poi_id"], errors="coerce")
    spots = spots.dropna(subset=["raw_poi_id"]).copy()
    spots["raw_poi_id"] = spots["raw_poi_id"].astype(int)

    for col in [
        "spot_latitude",
        "spot_longitude",
        "photos_count",
        "checkins_count",
        "users_count",
        "radius_meters",
        "highlights_count",
        "items_count",
        "max_items_count",
    ]:
        if col in spots.columns:
            spots[col] = pd.to_numeric(spots[col], errors="coerce")

    if "spot_categories" in spots.columns:
        parsed = spots["spot_categories"].apply(parse_category_cell)
        spots["category_id"] = parsed.apply(lambda x: x[0])
        spots["category_name"] = parsed.apply(lambda x: x[1])
        spots["raw_categories"] = parsed.apply(lambda x: x[2])
    else:
        spots["category_id"] = None
        spots["category_name"] = None
        spots["raw_categories"] = [[] for _ in range(len(spots))]

    return spots


def build_basic_poi_metadata_from_checkins(
    df: pd.DataFrame,
    raw2item: Dict[int, int],
) -> Dict[int, dict]:
    """
    Build lightweight POI metadata from raw check-in file.

    Used as base metadata, then optionally enriched with spots metadata.
    """
    meta = (
        df.groupby("raw_poi_id")
        .agg(
            latitude=("latitude", "median"),
            longitude=("longitude", "median"),
            checkins_count_from_events=("raw_poi_id", "size"),
            users_count_from_events=("user_id", pd.Series.nunique),
        )
        .reset_index()
    )

    result: Dict[int, dict] = {}
    for _, row in meta.iterrows():
        raw_poi = int(row["raw_poi_id"])
        payload = {
            "raw_poi_id": raw_poi,
            "latitude": None if pd.isna(row["latitude"]) else float(row["latitude"]),
            "longitude": None if pd.isna(row["longitude"]) else float(row["longitude"]),
            "checkins_count_from_events": int(row["checkins_count_from_events"]),
            "users_count_from_events": int(row["users_count_from_events"]),
        }
        if raw_poi in raw2item:
            payload["item_id"] = int(raw2item[raw_poi])
        result[raw_poi] = payload

    return result


def enrich_with_spots_metadata(
    base_meta: Dict[int, dict],
    spots_df: pd.DataFrame,
    raw2item: Dict[int, int],
) -> Dict[str, dict]:
    """
    Enrich base metadata with spots metadata from gowalla_spots_subset1.csv.

    Output keys are strings for JSON compatibility.
    """
    for _, row in spots_df.iterrows():
        raw_poi = int(row["raw_poi_id"])

        if raw_poi not in base_meta:
            base_meta[raw_poi] = {
                "raw_poi_id": raw_poi,
            }

        payload = base_meta[raw_poi]

        if raw_poi in raw2item:
            payload["item_id"] = int(raw2item[raw_poi])

        # Prefer event lat/lon if already present and non-null; otherwise use spots lat/lon
        if payload.get("latitude") is None and "spot_latitude" in row and not pd.isna(row["spot_latitude"]):
            payload["latitude"] = float(row["spot_latitude"])
        if payload.get("longitude") is None and "spot_longitude" in row and not pd.isna(row["spot_longitude"]):
            payload["longitude"] = float(row["spot_longitude"])

        # Keep spot-specific values separately as well
        if "spot_latitude" in row and not pd.isna(row["spot_latitude"]):
            payload["spot_latitude"] = float(row["spot_latitude"])
        if "spot_longitude" in row and not pd.isna(row["spot_longitude"]):
            payload["spot_longitude"] = float(row["spot_longitude"])

        if "category_id" in row and not pd.isna(row["category_id"]):
            payload["category_id"] = int(row["category_id"])
        else:
            payload.setdefault("category_id", None)

        if "category_name" in row and pd.notna(row["category_name"]):
            payload["category_name"] = str(row["category_name"])
        else:
            payload.setdefault("category_name", None)

        if "raw_categories" in row:
            payload["raw_categories"] = row["raw_categories"] if isinstance(row["raw_categories"], list) else []

        for col in [
            "photos_count",
            "checkins_count",
            "users_count",
            "radius_meters",
            "highlights_count",
            "items_count",
            "max_items_count",
            "created_at",
        ]:
            if col in row and pd.notna(row[col]):
                value = row[col]
                if col == "created_at":
                    payload[col] = str(value)
                elif isinstance(value, (int, float)):
                    payload[col] = float(value) if isinstance(value, float) else int(value)
                else:
                    payload[col] = str(value)

    # stringify keys for JSON output
    return {str(k): v for k, v in base_meta.items()}


def build_poi_metadata(
    df: pd.DataFrame,
    raw2item: Dict[int, int],
    spots_input: str = "",
) -> Dict[str, dict]:
    """
    Build POI metadata for semantic ID / reranking.

    Base source:
    - raw check-ins: lat/lon/checkins/users

    Optional enrichment:
    - gowalla_spots_subset1.csv:
        category_id
        category_name
        spot-specific stats
    """
    base_meta = build_basic_poi_metadata_from_checkins(df, raw2item)

    if spots_input:
        spots_df = read_spots_metadata(spots_input)
        return enrich_with_spots_metadata(base_meta, spots_df, raw2item)

    return {str(k): v for k, v in base_meta.items()}


def main():
    parser = argparse.ArgumentParser(description="Build Gowalla dataset artifacts for SBR")
    parser.add_argument("--input", type=str, required=True, help="Path to raw Gowalla totalCheckins file")
    parser.add_argument("--output_dir", type=str, required=True, help="Directory to save generated artifacts")
    parser.add_argument("--spots_input", type=str, default="", help="Optional path to gowalla_spots_subset1.csv")
    parser.add_argument("--session_interval_days", type=int, default=1)
    parser.add_argument("--max_session_len", type=int, default=20)
    parser.add_argument("--min_session_len", type=int, default=2)
    parser.add_argument("--min_item_support", type=int, default=5)
    parser.add_argument("--top_n_items", type=int, default=30000)
    parser.add_argument("--test_split", type=float, default=0.2)
    parser.add_argument("--save_poi_metadata", action="store_true")
    args = parser.parse_args()

    cfg = BuildConfig(
        input=args.input,
        output_dir=args.output_dir,
        spots_input=args.spots_input,
        session_interval_days=args.session_interval_days,
        max_session_len=args.max_session_len,
        min_session_len=args.min_session_len,
        min_item_support=args.min_item_support,
        top_n_items=args.top_n_items,
        test_split=args.test_split,
        save_poi_metadata=args.save_poi_metadata,
    )

    ensure_dir(cfg.output_dir)

    print("=" * 80)
    print("Step 1/9: Reading raw Gowalla check-ins")
    df_raw = read_raw_gowalla(cfg.input)
    print(f"Raw rows: {len(df_raw):,}")
    print(f"Raw users: {df_raw['user_id'].nunique():,}")
    print(f"Raw POIs: {df_raw['raw_poi_id'].nunique():,}")

    print("=" * 80)
    print("Step 2/9: Sessionization")
    df = assign_sessions(df_raw, cfg.session_interval_days)
    df = remove_immediate_repeats(df)
    df = truncate_long_sessions(df, cfg.max_session_len)
    print(f"Rows after sessionization/repeat removal/truncation: {len(df):,}")
    print(f"Sessions after sessionization: {df['session_id'].nunique():,}")

    print("=" * 80)
    print("Step 3/9: Top-N POI filtering")
    df = keep_top_n_items(df, cfg.top_n_items)
    print(f"Rows after top-N items: {len(df):,}")
    print(f"POIs after top-N items: {df['raw_poi_id'].nunique():,}")

    print("=" * 80)
    print("Step 4/9: Iterative filtering for short sessions / infrequent items")
    df = iterative_filter(
        df,
        min_session_len=cfg.min_session_len,
        min_item_support=cfg.min_item_support,
    )
    print(f"Rows after iterative filtering: {len(df):,}")
    print(f"Sessions after filtering: {df['session_id'].nunique():,}")
    print(f"POIs after filtering: {df['raw_poi_id'].nunique():,}")

    print("=" * 80)
    print("Step 5/9: Train/test split by session end time")
    train_df, test_df = split_train_test_by_session_end_time(df, cfg.test_split)
    print(f"Train rows: {len(train_df):,}")
    print(f"Test rows: {len(test_df):,}")
    print(f"Train sessions: {train_df['session_id'].nunique():,}")
    print(f"Test sessions: {test_df['session_id'].nunique():,}")

    print("=" * 80)
    print("Step 6/9: Build train-universe mapping")
    raw2item, item2raw = build_item_mapping_from_train(train_df)
    print(f"Mapped train-universe POIs: {len(raw2item):,}")

    train_df = apply_item_mapping(train_df, raw2item)
    test_df = apply_item_mapping(test_df, raw2item)
    test_df = filter_test_after_mapping(test_df, cfg.min_session_len)

    print(f"Test rows after dropping unseen POIs: {len(test_df):,}")
    print(f"Test sessions after mapping cleanup: {test_df['session_id'].nunique():,}")

    print("=" * 80)
    print("Step 7/9: Build full sessions")
    train_full_sessions = group_sessions_as_sequences(train_df, item_col="item_id")
    test_full_sessions = group_sessions_as_sequences(test_df, item_col="item_id")
    train_event_sessions = group_sessions_as_event_sequences(train_df)
    test_event_sessions = group_sessions_as_event_sequences(test_df)

    print(f"Full train sessions: {len(train_full_sessions):,}")
    print(f"Full test sessions: {len(test_full_sessions):,}")

    print("=" * 80)
    print("Step 8/9: Build supervised prefix-target pairs")
    train_prefixes, train_targets = make_supervised_examples(train_full_sessions)
    test_prefixes, test_targets = make_supervised_examples(test_full_sessions)
    train_event_examples = make_supervised_event_examples(train_event_sessions)
    test_event_examples = make_supervised_event_examples(test_event_sessions)

    print(f"Train examples: {len(train_prefixes):,}")
    print(f"Test examples: {len(test_prefixes):,}")

    print("=" * 80)
    print("Step 9/9: Saving artifacts")
    train_path = os.path.join(cfg.output_dir, "train.txt")
    test_path = os.path.join(cfg.output_dir, "test.txt")
    train_with_timestamps_path = os.path.join(cfg.output_dir, "train_with_timestamps.json")
    test_with_timestamps_path = os.path.join(cfg.output_dir, "test_with_timestamps.json")
    all_train_seq_path = os.path.join(cfg.output_dir, "all_train_seq.txt")
    raw2item_path = os.path.join(cfg.output_dir, "raw_location2item.json")
    item2raw_path = os.path.join(cfg.output_dir, "item2raw_location.json")
    manifest_path = os.path.join(cfg.output_dir, "build_manifest.json")

    save_pickle((train_prefixes, train_targets), train_path)
    save_pickle((test_prefixes, test_targets), test_path)
    validate_event_examples_against_pickle(train_path, train_event_examples)
    validate_event_examples_against_pickle(test_path, test_event_examples)
    save_json(train_event_examples, train_with_timestamps_path)
    save_json(test_event_examples, test_with_timestamps_path)
    save_pickle(train_full_sessions, all_train_seq_path)
    save_json(raw2item, raw2item_path)
    save_json(item2raw, item2raw_path)

    manifest = {
        "config": asdict(cfg),
        "stats": {
            "raw_rows": int(len(df_raw)),
            "filtered_rows": int(len(df)),
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "train_sessions": int(len(train_full_sessions)),
            "test_sessions": int(len(test_full_sessions)),
            "train_examples": int(len(train_prefixes)),
            "test_examples": int(len(test_prefixes)),
            "train_event_examples": int(len(train_event_examples)),
            "test_event_examples": int(len(test_event_examples)),
            "n_items": int(len(raw2item)),
            "n_node_for_model": int(len(raw2item) + 1),  # +1 for padding index 0
        },
        "artifacts": {
            "train.txt": train_path,
            "test.txt": test_path,
            "train_with_timestamps.json": train_with_timestamps_path,
            "test_with_timestamps.json": test_with_timestamps_path,
            "all_train_seq.txt": all_train_seq_path,
            "raw_location2item.json": raw2item_path,
            "item2raw_location.json": item2raw_path,
        },
    }

    if cfg.save_poi_metadata:
        poi_metadata = build_poi_metadata(
            df=df,
            raw2item=raw2item,
            spots_input=cfg.spots_input,
        )
        poi_metadata_path = os.path.join(cfg.output_dir, "poi_metadata.json")
        save_json(poi_metadata, poi_metadata_path)
        manifest["artifacts"]["poi_metadata.json"] = poi_metadata_path

    save_json(manifest, manifest_path)

    print(f"Saved: {train_path}")
    print(f"Saved: {test_path}")
    print(f"Saved: {train_with_timestamps_path}")
    print(f"Saved: {test_with_timestamps_path}")
    print(f"Saved: {all_train_seq_path}")
    print(f"Saved: {raw2item_path}")
    print(f"Saved: {item2raw_path}")
    print(f"Saved: {manifest_path}")

    if cfg.save_poi_metadata:
        print(f"Saved: {os.path.join(cfg.output_dir, 'poi_metadata.json')}")

    print("=" * 80)
    print("Done.")
    print(f"Effective n_items: {len(raw2item):,}")
    print(f"Recommended n_node: {len(raw2item) + 1:,}")
    print("=" * 80)


if __name__ == "__main__":
    main()
