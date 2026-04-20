"""Offline evaluation pipeline for SBR vs. SBR + semantic reranking."""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import pickle
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import torch

THIS_FILE = Path(__file__).resolve()
EVAL_DIR = THIS_FILE.parent
BACKEND_DIR = EVAL_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

# IMPORTANT:
# The real folder name is MG-DSGAT, and infer_sbr.py is written like a script
# that expects its src/ directory to be on sys.path.
MODEL_SRC_DIR = BACKEND_DIR / "model_core" / "MG-DSGAT" / "src"

DEFAULT_TEST_PATH = EVAL_DIR / "test.txt"
DEFAULT_OUTPUT_DIR = EVAL_DIR / "outputs"
DEFAULT_MAPPING_PATH = BACKEND_DIR / "datasets" / "Gowalla" / "raw_location2item.json"
DEFAULT_REVERSE_MAPPING_PATH = BACKEND_DIR / "datasets" / "Gowalla" / "item2raw_location.json"
DEFAULT_CHECKPOINT_PATH = (
    BACKEND_DIR
    / "model_core"
    / "MG-DSGAT"
    / "save_model"
    / "Demo_model_exp30_Gowalla_512_seed_2023-last_k_4_best_model.pt"
)

# Ensure backend package imports and legacy SBR script-style imports both work.
for path in (BACKEND_DIR, MODEL_SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from app import app as backend_app
from analysis import seen_item_ratio, summarize_analysis, top1_is_seen
from metrics import compute_ranking_metrics
from semantic import rerank_predictions_for_user
from semantic.config import SemanticRerankerConfig

from infer_sbr import (
    build_opt_from_args,
    build_single_sample,
    load_checkpoint_model,
    load_item2raw_mapping,
    move_batch_to_device,
    predict_topk,
)


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline evaluation for original SBR vs SBR + semantic reranking."
    )
    parser.add_argument("--test-path", type=Path, default=DEFAULT_TEST_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dataset", type=str, default="Gowalla")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--reverse-mapping-json", type=Path, default=DEFAULT_REVERSE_MAPPING_PATH)
    parser.add_argument("--topk", type=int, default=10)
    parser.add_argument("--exclude-seen", action="store_true", default=False)
    parser.add_argument("--device", type=str, default="cuda", choices=["cuda", "cpu"])
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of samples to evaluate")
    parser.add_argument(
        "--semantic-embedding-backend",
        type=str,
        default="hf",
        help="Embedding backend for offline semantic reranking, e.g. mock or hf.",
    )

    # Model hyperparameters: aligned with infer_sbr.py expectations.
    parser.add_argument("--hiddenSize", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--lr_dc", type=float, default=0.1)
    parser.add_argument("--lr_dc_step", type=int, default=5)
    parser.add_argument("--l2", type=float, default=1e-5)
    parser.add_argument("--step", type=int, default=1)
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


def load_test_samples(test_path: Path) -> list[dict[str, Any]]:
    """Load the pickle test split and normalize it into history/target samples."""
    if not test_path.exists():
        raise FileNotFoundError(f"Test split not found: {test_path}")

    with test_path.open("rb") as f:
        raw_data = pickle.load(f)

    return normalize_samples(raw_data)


def normalize_samples(raw_data: Any) -> list[dict[str, Any]]:
    """Normalize multiple possible pickle shapes into a common sample format."""
    if isinstance(raw_data, tuple) and len(raw_data) == 2:
        histories, targets = raw_data
        if len(histories) != len(targets):
            raise ValueError("Tuple test split has mismatched histories and targets lengths.")
        return [
            {
                "sample_id": index,
                "history_item_ids": coerce_int_list(history),
                "target_item_id": int(target),
            }
            for index, (history, target) in enumerate(zip(histories, targets))
        ]

    if isinstance(raw_data, list):
        samples = []
        for index, sample in enumerate(raw_data):
            normalized = normalize_single_sample(index, sample)
            if normalized is not None:
                samples.append(normalized)
        return samples

    raise ValueError(
        "Unsupported test split format. Expected tuple(histories, targets) or a list of samples."
    )


def normalize_single_sample(index: int, sample: Any) -> dict[str, Any] | None:
    """Normalize one sample into history prefix + target next item."""
    if isinstance(sample, dict):
        history = (
            sample.get("history_item_ids")
            or sample.get("history")
            or sample.get("prefix")
            or sample.get("session")
        )
        target = sample.get("target_item_id", sample.get("target"))
        if history is None or target is None:
            raise ValueError(f"Unsupported dict sample at index {index}: {sample!r}")
        return {
            "sample_id": index,
            "history_item_ids": coerce_int_list(history),
            "target_item_id": int(target),
        }

    if isinstance(sample, (list, tuple)) and len(sample) == 2:
        history, target = sample
        return {
            "sample_id": index,
            "history_item_ids": coerce_int_list(history),
            "target_item_id": int(target),
        }

    return None


def coerce_int_list(values: Any) -> list[int]:
    return [int(value) for value in list(values)]


def resolve_device(device_name: str) -> torch.device:
    if device_name == "cuda" and not torch.cuda.is_available():
        print("[Warning] CUDA requested but not available. Falling back to CPU.")
        return torch.device("cpu")
    return torch.device(device_name)


@contextlib.contextmanager
def pushd(path: Path):
    """Temporarily switch the working directory for legacy relative-path code."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def build_history_records(history_item_ids: list[int], item2raw: dict[int, int]) -> list[SimpleNamespace]:
    """Convert internal item ids into lightweight history records for the reranker."""
    history_records = []
    for item_id in history_item_ids:
        raw_location_id = item2raw.get(int(item_id))
        if raw_location_id is None:
            continue
        history_records.append(SimpleNamespace(poi_id=int(raw_location_id)))
    return history_records


def find_rank(predictions: list[dict[str, Any]], *, target_item_id: int) -> int | None:
    """Return the 1-based rank of the target item inside predictions, if present."""
    for index, pred in enumerate(predictions, start=1):
        if int(pred.get("item_id", -1)) == int(target_item_id):
            return index
    return None


def summarize_sample(
    sample_id: int,
    history_item_ids: list[int],
    target_item_id: int,
    sbr_predictions: list[dict[str, Any]],
    semantic_predictions: list[dict[str, Any]],
    sbr_time: float,
    rerank_time: float,
    total_sample_time: float,
) -> dict[str, Any]:
    """Create one per-sample evaluation record."""
    rank_before = find_rank(sbr_predictions, target_item_id=target_item_id)
    rank_after = find_rank(semantic_predictions, target_item_id=target_item_id)
    return {
        "sample_id": sample_id,
        "history_length": len(history_item_ids),
        "history_item_ids": history_item_ids,
        "target_item_id": int(target_item_id),
        "target_rank_before": rank_before,
        "target_rank_after": rank_after,
        "rank_delta": (
            None if rank_before is None or rank_after is None
            else int(rank_after) - int(rank_before)
        ),
        "hit_before": rank_before is not None,
        "hit_after": rank_after is not None,
        "top1_item_before": sbr_predictions[0]["item_id"] if sbr_predictions else None,
        "top1_item_after": semantic_predictions[0]["item_id"] if semantic_predictions else None,
        "top1_seen_before": top1_is_seen(sbr_predictions, history_item_ids),
        "top1_seen_after": top1_is_seen(semantic_predictions, history_item_ids),
        "seen_item_ratio_before": seen_item_ratio(sbr_predictions, history_item_ids),
        "seen_item_ratio_after": seen_item_ratio(semantic_predictions, history_item_ids),
        "candidate_count_before": len(sbr_predictions),
        "candidate_count_after": len(semantic_predictions),
        "timing": {
            "sbr_time_sec": round(sbr_time, 6),
            "rerank_time_sec": round(rerank_time, 6),
            "total_sample_time_sec": round(total_sample_time, 6),
        },
        "sbr_predictions": sbr_predictions,
        "semantic_predictions": semantic_predictions,
    }


def write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def write_csv(path: Path, samples: list[dict[str, Any]]) -> None:
    fieldnames = [
        "sample_id",
        "history_length",
        "target_item_id",
        "target_rank_before",
        "target_rank_after",
        "rank_delta",
        "hit_before",
        "hit_after",
        "top1_item_before",
        "top1_item_after",
        "top1_seen_before",
        "top1_seen_after",
        "seen_item_ratio_before",
        "seen_item_ratio_after",
        "candidate_count_before",
        "candidate_count_after",
        "sbr_time_sec",
        "rerank_time_sec",
        "total_sample_time_sec",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for sample in samples:
            timing = sample.get("timing", {})
            row = {field: sample.get(field) for field in fieldnames}
            row["sbr_time_sec"] = timing.get("sbr_time_sec")
            row["rerank_time_sec"] = timing.get("rerank_time_sec")
            row["total_sample_time_sec"] = timing.get("total_sample_time_sec")
            writer.writerow(row)


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()

    args.test_path = args.test_path.resolve()
    args.output_dir = args.output_dir.resolve()
    args.checkpoint = args.checkpoint.resolve()
    args.reverse_mapping_json = args.reverse_mapping_json.resolve()

    print("=== eval path debug ===")
    print("BACKEND_DIR =", BACKEND_DIR)
    print("MODEL_SRC_DIR =", MODEL_SRC_DIR, "exists =", MODEL_SRC_DIR.exists())
    print("checkpoint =", args.checkpoint, "exists =", args.checkpoint.exists())
    print("test_path =", args.test_path, "exists =", args.test_path.exists())
    print("reverse_mapping_json =", args.reverse_mapping_json, "exists =", args.reverse_mapping_json.exists())

    total_start_time = time.time()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    samples = load_test_samples(args.test_path)
    if args.limit and args.limit > 0:
        samples = samples[: args.limit]

    device = resolve_device(args.device)
    opt = build_opt_from_args(args)

    print("[Eval] Loading checkpoint model...")
    with pushd(BACKEND_DIR):
        model = load_checkpoint_model(opt, str(args.checkpoint), device)
    print("[Eval] Model loaded.")

    item2raw = load_item2raw_mapping(str(args.reverse_mapping_json))
    semantic_config = SemanticRerankerConfig(
        SEMANTIC_EMBEDDING_BACKEND=args.semantic_embedding_backend
    )

    detailed_results: list[dict[str, Any]] = []
    timing_stats = {
        "sbr_time_sec": [],
        "rerank_time_sec": [],
        "total_sample_time_sec": [],
    }

    with backend_app.app_context():
        total_samples = len(samples)

        for idx, normalized in enumerate(samples, start=1):
            sample_start = time.time()

            history_item_ids = normalized["history_item_ids"]
            target_item_id = normalized["target_item_id"]
            sample_id = normalized["sample_id"]

            print(f"\n[Eval] Sample {idx}/{total_samples} (id={sample_id})")

            # ===== SBR =====
            sbr_start = time.time()

            batch = build_single_sample(session=history_item_ids, max_len=opt.len_session)
            batch = move_batch_to_device(batch, device)

            sbr_predictions = predict_topk(
                model=model,
                batch=batch,
                k=args.topk,
                original_session=history_item_ids,
                exclude_seen=args.exclude_seen,
                item2raw=item2raw,
            )

            sbr_time = time.time() - sbr_start
            print(f"[Timing] SBR time: {sbr_time:.4f}s")

            # ===== RERANK =====
            rerank_start = time.time()

            history_records = build_history_records(history_item_ids, item2raw)
            semantic_predictions = rerank_predictions_for_user(
                user_id=-1,
                predictions=sbr_predictions,
                histories=history_records,
                config=semantic_config,
            )

            rerank_time = time.time() - rerank_start
            print(f"[Timing] Rerank time: {rerank_time:.4f}s")

            # ===== TOTAL =====
            total_sample_time = time.time() - sample_start
            print(f"[Timing] Total sample time: {total_sample_time:.4f}s")

            timing_stats["sbr_time_sec"].append(sbr_time)
            timing_stats["rerank_time_sec"].append(rerank_time)
            timing_stats["total_sample_time_sec"].append(total_sample_time)

            detailed_results.append(
                summarize_sample(
                    sample_id=sample_id,
                    history_item_ids=history_item_ids,
                    target_item_id=target_item_id,
                    sbr_predictions=sbr_predictions,
                    semantic_predictions=semantic_predictions,
                    sbr_time=sbr_time,
                    rerank_time=rerank_time,
                    total_sample_time=total_sample_time,
                )
            )

    metrics_summary = compute_ranking_metrics(detailed_results)
    analysis_summary = summarize_analysis(detailed_results)

    timing_summary = {
        "avg_sbr_time_sec": round(avg(timing_stats["sbr_time_sec"]), 6),
        "avg_rerank_time_sec": round(avg(timing_stats["rerank_time_sec"]), 6),
        "avg_total_sample_time_sec": round(avg(timing_stats["total_sample_time_sec"]), 6),
        "total_evaluation_time_sec": round(time.time() - total_start_time, 6),
    }

    summary = {
        "config": {
            "test_path": str(args.test_path),
            "checkpoint": str(args.checkpoint),
            "dataset": args.dataset,
            "topk": args.topk,
            "exclude_seen": bool(args.exclude_seen),
            "device": str(device),
            "sample_limit": args.limit if args.limit > 0 else None,
            "reverse_mapping_json": str(args.reverse_mapping_json),
            "semantic_embedding_backend": args.semantic_embedding_backend,
        },
        "metrics": metrics_summary,
        "analysis": analysis_summary,
        "timing": timing_summary,
    }

    write_json(args.output_dir / "detailed_results.json", detailed_results)
    write_json(args.output_dir / "summary_metrics.json", summary)
    write_csv(args.output_dir / "detailed_results.csv", detailed_results)

    print("\n=== Timing Summary ===")
    print(f"Avg SBR time: {timing_summary['avg_sbr_time_sec']:.4f}s")
    print(f"Avg Rerank time: {timing_summary['avg_rerank_time_sec']:.4f}s")
    print(f"Avg Total sample time: {timing_summary['avg_total_sample_time_sec']:.4f}s")
    print(f"Total evaluation time: {timing_summary['total_evaluation_time_sec']:.2f}s")

    print(f"\nEvaluated {len(detailed_results)} samples.")
    print(f"Wrote detailed JSON: {args.output_dir / 'detailed_results.json'}")
    print(f"Wrote detailed CSV: {args.output_dir / 'detailed_results.csv'}")
    print(f"Wrote summary JSON: {args.output_dir / 'summary_metrics.json'}")


if __name__ == "__main__":
    main()