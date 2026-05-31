#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Standalone inference pipeline for the current Session-Based Recommendation (SBR) model.

Supported input modes:
1) Internal item-id session directly:
    python infer_sbr.py \
        --dataset Gowalla \
        --checkpoint ./checkpoints/weight.pt \
        --session 12,45,91,203 \
        --topk 10

2) Internal item-id session from txt:
    python infer_sbr.py \
        --dataset Gowalla \
        --checkpoint ./checkpoints/weight.pt \
        --session_file ./session.txt \
        --topk 10

3) Raw Gowalla visit-path txt:
    python infer_sbr.py \
        --dataset Gowalla \
        --checkpoint ./checkpoints/weight.pt \
        --gowalla_visit_file ./examples/example_visit.txt \
        --mapping_json ./datasets/Gowalla/raw_location2item.json \
        --reverse_mapping_json ./datasets/Gowalla/item2raw_location.json \
        --topk 10

Notes:
1. The model itself consumes internal item ids, not raw Gowalla location ids.
2. Therefore, raw visit-path inference requires raw_location_id -> internal_item_id mapping.
3. Score index 0 corresponds to internal item id 1, because training uses `targets - 1`.
"""

import argparse
import json
import os
import re
from datetime import datetime
from types import SimpleNamespace
from typing import Dict, List, Tuple

import numpy as np
import torch

from model_exp30 import SessionGraph
from utils import infer_n_node


def get_dataset_n_node(dataset: str) -> int:
    """
    Match the current hardcoded dataset -> n_node logic in main_model_exp30.py
    """
    inferred_n_node = infer_n_node(dataset)
    if inferred_n_node is not None:
        return inferred_n_node

    mapping = {
        "diginetica": 43098,
        "Nowplaying": 60417,
        "Tmall": 40728,
        "RetailRocket": 36969,
        "Gowalla": 29511,
    }
    if dataset not in mapping:
        raise ValueError(
            f"Unknown dataset: {dataset}. "
            f"Supported datasets: {list(mapping.keys())}"
        )
    return mapping[dataset]


def build_opt_from_args(args: argparse.Namespace) -> SimpleNamespace:
    """
    Build an opt object compatible with SessionGraph(opt, n_node, device).
    Keep defaults aligned with current repo as much as possible.
    """
    opt = SimpleNamespace()

    # core
    opt.dataset = args.dataset
    opt.batchSize = getattr(args, "batchSize", 1)
    opt.hiddenSize = args.hiddenSize
    opt.epochs = 0
    opt.lr = args.lr
    opt.lr_dc = args.lr_dc
    opt.lr_dc_step = args.lr_dc_step
    opt.l2 = args.l2
    opt.step = args.step
    opt.ggnn_layers = args.ggnn_layers
    opt.patience = 3
    opt.validation = False
    opt.valid_portion = 0.2
    opt.gama = args.gama
    opt.num_attention_heads = args.num_attention_heads
    opt.neighbor_n = args.neighbor_n
    opt.seed = args.seed
    opt.num_workers = 0

    # group representation
    opt.len_session = args.len_session
    opt.last_k = args.last_k
    opt.l_p = args.l_p
    opt.use_attn_conv = args.use_attn_conv
    opt.heads = args.heads
    opt.dot = args.dot

    # dataset-specific overrides to match training script
    if opt.dataset == "Nowplaying":
        opt.neighbor_n = 4
    elif opt.dataset == "Tmall":
        opt.neighbor_n = 7
        opt.last_k = 3
        opt.step = 2
    elif opt.dataset == "Gowalla":
        opt.last_k = 4
    if opt.ggnn_layers is None:
        opt.ggnn_layers = opt.step
    else:
        opt.step = opt.ggnn_layers

    return opt


def parse_session(session_str: str) -> List[int]:
    """
    Parse comma-separated session ids like: "12,45,91,203"
    """
    if not session_str.strip():
        raise ValueError("Empty --session input.")
    try:
        session = [int(x.strip()) for x in session_str.split(",") if x.strip()]
    except ValueError as exc:
        raise ValueError(
            f"Invalid session format: {session_str}. Expected comma-separated integers."
        ) from exc

    if len(session) == 0:
        raise ValueError("Parsed session is empty.")

    if any(x <= 0 for x in session):
        raise ValueError(
            "All session item ids must be positive integers. Padding id 0 is reserved."
        )
    return session


def parse_session_file(file_path: str) -> List[int]:
    """
    Read a txt file and parse it into a single internal-id session.

    Supported formats:
    1) 12,45,91,203
    2) 12 45 91 203
    3) one item id per line
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Session file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        raise ValueError(f"Session file is empty: {file_path}")

    tokens = re.findall(r"\d+", content)
    if not tokens:
        raise ValueError(f"No valid item ids found in session file: {file_path}")

    session = [int(x) for x in tokens if int(x) > 0]
    if len(session) == 0:
        raise ValueError(f"No positive item ids found in session file: {file_path}")

    return session


def parse_gowalla_visit_file(file_path: str) -> List[int]:
    """
    Parse a Gowalla-style raw visit path file.

    Expected row format:
    [user] [check-in time] [latitude] [longitude] [location id]

    Example:
    196514  2010-07-24T13:45:06Z  53.3648119  -2.2723465833  145064

    Returns:
        Raw location-id sequence ordered by time ascending.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Visit file not found: {file_path}")

    records = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            lower_line = line.lower()
            if "check-in time" in lower_line or "location id" in lower_line:
                continue

            parts = line.split()
            if len(parts) < 5:
                continue

            try:
                user_id = parts[0]
                checkin_time = parts[1]
                lat = float(parts[2])
                lon = float(parts[3])
                location_id = int(parts[4])

                dt = datetime.strptime(checkin_time, "%Y-%m-%dT%H:%M:%SZ")
                records.append(
                    {
                        "user_id": user_id,
                        "checkin_time": dt,
                        "lat": lat,
                        "lon": lon,
                        "location_id": location_id,
                    }
                )
            except Exception:
                print(f"[Warning] Skip malformed line {line_num}: {line}")
                continue

    if not records:
        raise ValueError(f"No valid Gowalla visit records parsed from: {file_path}")

    # sort oldest -> newest for sequential input
    records = sorted(records, key=lambda x: x["checkin_time"])
    return [r["location_id"] for r in records]


def load_location_mapping(mapping_path: str) -> Dict[int, int]:
    """
    Load raw location id -> internal item id mapping from JSON.
    Example:
    {
      "145064": 12,
      "1275991": 45
    }
    """
    if not os.path.exists(mapping_path):
        raise FileNotFoundError(f"Mapping file not found: {mapping_path}")

    if not mapping_path.endswith(".json"):
        raise ValueError("Currently only JSON mapping is supported.")

    with open(mapping_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {int(k): int(v) for k, v in data.items()}


def load_item2raw_mapping(mapping_path: str) -> Dict[int, int]:
    """
    Optional reverse mapping:
    internal item id -> raw location id
    """
    if not mapping_path:
        return {}

    if not os.path.exists(mapping_path):
        raise FileNotFoundError(f"Reverse mapping file not found: {mapping_path}")

    with open(mapping_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {int(k): int(v) for k, v in data.items()}


def convert_location_ids_to_internal_ids(
    location_ids: List[int],
    location2item: Dict[int, int],
) -> List[int]:
    """
    Convert raw Gowalla location ids to model internal item ids.
    Unmapped ids are dropped with warnings.
    """
    converted = []
    missing = []

    for loc_id in location_ids:
        if loc_id in location2item:
            converted.append(location2item[loc_id])
        else:
            missing.append(loc_id)

    if missing:
        print(f"[Warning] {len(missing)} location ids not found in mapping.")
        print(f"[Warning] Missing examples: {missing[:10]}")

    if not converted:
        raise ValueError("No valid mapped internal item ids remained after conversion.")

    return converted


def truncate_and_pad_session(session: List[int], max_len: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Follow the repo's style:
    - keep the most recent max_len items if too long
    - right-pad with 0
    - mask is 1 for valid tokens, 0 for padding
    """
    if len(session) > max_len:
        session = session[-max_len:]

    valid_len = len(session)
    padded = session + [0] * (max_len - valid_len)
    mask = [1] * valid_len + [0] * (max_len - valid_len)

    return np.asarray(padded, dtype=np.int64), np.asarray(mask, dtype=np.int64)


def build_single_sample(
    session: List[int],
    max_len: int,
    target: int = 1,
    index: int = 0,
) -> Dict[str, torch.Tensor]:
    """
    Reproduce DataSampler.get_data() / __getitem__() format for a single inference sample.

    Current repo logic:
        node = np.unique(u_input)
        items = node.tolist() + (self.max_len - len(node)) * [0]
        alias_inputs = [np.where(node == i)[0][0] for i in u_input]

    Important:
    - np.unique sorts values. We intentionally keep the same behavior for compatibility.
    - targets/index default to placeholders during inference, but can be supplied
      by parity/debug callers.
    """
    u_input, mask = truncate_and_pad_session(session, max_len=max_len)

    node = np.unique(u_input)
    items = node.tolist() + (max_len - len(node)) * [0]
    alias_inputs = [np.where(node == i)[0][0] for i in u_input]

    sample = {
        "alias_inputs": torch.tensor(alias_inputs, dtype=torch.long).unsqueeze(0),
        "items": torch.tensor(items, dtype=torch.long).unsqueeze(0),
        "mask": torch.tensor(mask, dtype=torch.long).unsqueeze(0),
        "targets": torch.tensor([target], dtype=torch.long),
        "inputs": torch.tensor(u_input, dtype=torch.long).unsqueeze(0),
        "index": torch.tensor([index], dtype=torch.long),
    }
    return sample


def move_batch_to_device(batch: Dict[str, torch.Tensor], device: torch.device) -> Dict[str, torch.Tensor]:
    return {k: v.to(device) for k, v in batch.items()}


def load_checkpoint_model(
    opt: SimpleNamespace,
    checkpoint_path: str,
    device: torch.device,
) -> SessionGraph:
    """
    Load current repo checkpoint format:
    - assumed to be raw state_dict saved by torch.save(model.state_dict(), path)
    """
    n_node = get_dataset_n_node(opt.dataset)
    model = SessionGraph(opt, n_node, device).to(device)

    ckpt = torch.load(checkpoint_path, map_location=device)

    if isinstance(ckpt, dict) and all(isinstance(k, str) for k in ckpt.keys()):
        try:
            model.load_state_dict(ckpt, strict=True)
        except RuntimeError as exc:
            raise RuntimeError(
                "Failed to load checkpoint. "
                "Please check whether the model hyperparameters match training."
            ) from exc
    else:
        raise ValueError(
            "Unsupported checkpoint format. Expected raw model state_dict."
        )

    model.eval()
    return model


def mask_seen_items(scores: torch.Tensor, session: List[int]) -> torch.Tensor:
    """
    Optionally suppress already seen items.
    scores shape: (1, n_items)
    score index 0 corresponds to internal item id 1
    """
    masked_scores = scores.clone()
    for item_id in set(session):
        score_idx = item_id - 1
        if 0 <= score_idx < masked_scores.size(1):
            masked_scores[0, score_idx] = float("-inf")
    return masked_scores


@torch.no_grad()
def predict_topk(
    model: SessionGraph,
    batch: Dict[str, torch.Tensor],
    k: int,
    original_session: List[int],
    exclude_seen: bool = False,
    item2raw: Dict[int, int] = None,
) -> List[Dict]:
    """
    Run model forward and return top-k predictions.
    """
    if item2raw is None:
        item2raw = {}

    _, scores = model(batch)  # scores shape: (B, N-1)

    if exclude_seen:
        scores = mask_seen_items(scores, original_session)

    top_scores, top_indices = torch.topk(scores, k=k, dim=1)

    # score index 0 corresponds to internal item id 1
    pred_item_ids = top_indices[0].cpu().numpy() + 1
    pred_scores = top_scores[0].cpu().numpy()

    results = []
    for rank, (item_id, score) in enumerate(zip(pred_item_ids, pred_scores), start=1):
        row = {
            "rank": rank,
            "item_id": int(item_id),
            "score": float(score),
        }
        if int(item_id) in item2raw:
            row["raw_location_id"] = int(item2raw[int(item_id)])
        results.append(row)

    return results


def print_results(session: List[int], results: List[Dict]) -> None:
    print("=" * 80)
    print("Input internal item-id session:")
    print(session)
    print("-" * 80)
    print("Top-k predictions:")
    for row in results:
        msg = (
            f"rank={row['rank']:>2d} | "
            f"item_id={row['item_id']:>6d} | "
            f"score={row['score']:.6f}"
        )
        if "raw_location_id" in row:
            msg += f" | raw_location_id={row['raw_location_id']}"
        print(msg)
    print("=" * 80)


def save_results_json(output_path: str, session: List[int], results: List[Dict]) -> None:
    payload = {
        "session": session,
        "predictions": results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser("SBR inference pipeline")

    # required
    parser.add_argument("--dataset", type=str, required=True,
                        help="Dataset name: diginetica / Nowplaying / Tmall / RetailRocket / Gowalla")
    parser.add_argument("--checkpoint", type=str, required=True,
                        help="Path to trained checkpoint (.pt)")

    # input modes
    parser.add_argument("--session", type=str, default="",
                        help='Comma-separated internal item ids, e.g. "12,45,91,203"')
    parser.add_argument("--session_file", type=str, default="",
                        help="Path to txt file containing one session of internal item ids")
    parser.add_argument("--gowalla_visit_file", type=str, default="",
                        help="Path to Gowalla-style raw visit path txt file")
    parser.add_argument("--mapping_json", type=str, default="",
                        help="JSON file for raw location id -> internal item id mapping")
    parser.add_argument("--reverse_mapping_json", type=str, default="",
                        help="Optional JSON file for internal item id -> raw location id")

    # inference behavior
    parser.add_argument("--topk", type=int, default=10, help="Number of predictions to return")
    parser.add_argument("--exclude_seen", action="store_true",
                        help="Exclude items already appearing in the input session")
    parser.add_argument("--device", type=str, default="cuda",
                        choices=["cuda", "cpu"], help="Inference device")
    parser.add_argument("--output_json", type=str, default="",
                        help="Optional path to save predictions as JSON")

    # model hyperparameters: must match training
    parser.add_argument("--batchSize", type=int, default=1)
    parser.add_argument("--hiddenSize", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--lr_dc", type=float, default=0.1)
    parser.add_argument("--lr_dc_step", type=int, default=5)
    parser.add_argument("--l2", type=float, default=1e-5)
    parser.add_argument("--step", type=int, default=1)
    parser.add_argument("--ggnn_layers", type=int, default=None,
                        help="Number of GGNN propagation/message-passing layers; defaults to dataset-specific --step")
    parser.add_argument("--gama", type=float, default=1.7)
    parser.add_argument("--num_attention_heads", type=int, default=4)
    parser.add_argument("--neighbor_n", type=int, default=3)
    parser.add_argument("--seed", type=int, default=2023)

    parser.add_argument("--len_session", type=int, default=50)
    parser.add_argument("--last_k", type=int, default=7)
    parser.add_argument("--l_p", type=int, default=4)
    parser.add_argument("--use_attn_conv", type=str, default="True")
    parser.add_argument("--heads", type=int, default=8)
    parser.add_argument("--dot", action="store_true", default=True)

    return parser


def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        print("[Warning] CUDA requested but not available. Falling back to CPU.")
        device = torch.device("cpu")
    else:
        device = torch.device(args.device)

    # -------- Input resolution --------
    if args.gowalla_visit_file:
        if not args.mapping_json:
            raise ValueError(
                "When using --gowalla_visit_file, you must also provide --mapping_json"
            )

        raw_location_ids = parse_gowalla_visit_file(args.gowalla_visit_file)
        print(f"Loaded raw Gowalla path from file: {args.gowalla_visit_file}")
        print(f"Raw location id sequence: {raw_location_ids}")

        location2item = load_location_mapping(args.mapping_json)
        session = convert_location_ids_to_internal_ids(raw_location_ids, location2item)
        print(f"Mapped internal item-id session: {session}")

    elif args.session_file:
        session = parse_session_file(args.session_file)
        print(f"Loaded session from file: {args.session_file}")

    elif args.session:
        session = parse_session(args.session)

    else:
        raise ValueError(
            "Please provide one of: --session, --session_file, or --gowalla_visit_file"
        )

    item2raw = load_item2raw_mapping(args.reverse_mapping_json) if args.reverse_mapping_json else {}

    opt = build_opt_from_args(args)
    model = load_checkpoint_model(opt, args.checkpoint, device)

    batch = build_single_sample(session=session, max_len=opt.len_session)
    batch = move_batch_to_device(batch, device)

    results = predict_topk(
        model=model,
        batch=batch,
        k=args.topk,
        original_session=session,
        exclude_seen=args.exclude_seen,
        item2raw=item2raw,
    )

    print_results(session, results)

    if args.output_json:
        save_results_json(args.output_json, session, results)
        print(f"Saved predictions to: {args.output_json}")


if __name__ == "__main__":
    main()
