"""Precompute and cache POI descriptions for semantic reranking."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
BACKEND_DIR = THIS_FILE.parents[1]
REPO_ROOT = BACKEND_DIR.parent
for path in (BACKEND_DIR, REPO_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from semantic.cached_description_store import CachedDescriptionStore, build_description_cache_key
from semantic.description_backend import build_description_generator

DEFAULT_METADATA_PATH = BACKEND_DIR / "datasets" / "filtered_poi_metadata.json"
DEFAULT_CACHE_PATH = BACKEND_DIR / "datasets" / "semantic_cache" / "poi_descriptions.json"


def build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser("Precompute POI semantic descriptions")
    parser.add_argument("--metadata-path", type=Path, default=DEFAULT_METADATA_PATH)
    parser.add_argument("--cache-path", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--dataset", type=str, default="Gowalla")
    parser.add_argument(
        "--description-backend",
        type=str,
        default="template",
        choices=["template", "llama2"],
    )
    parser.add_argument(
        "--description-model-name",
        type=str,
        default="meta-llama/Llama-2-7b-chat-hf",
    )
    parser.add_argument("--description-prompt-version", type=str, default="v1")
    parser.add_argument("--description-use-4bit", action="store_true", default=False)
    parser.add_argument("--description-max-new-tokens", type=int, default=220)
    parser.add_argument("--description-temperature", type=float, default=0.2)
    parser.add_argument(
        "--debug-llama-output",
        action="store_true",
        default=False,
        help="Print the Llama prompt, raw output, and parse/fallback status.",
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--only-missing", action="store_true", default=False)
    parser.add_argument("--save-every", type=int, default=10)
    return parser


def load_metadata(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        rows = []
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            metadata = dict(value)
            metadata.setdefault("raw_poi_id", int(key) if str(key).isdigit() else key)
            rows.append(metadata)
        return rows

    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]

    raise ValueError(f"Unsupported metadata JSON shape in {path}")


def main() -> None:
    parser = build_argparser()
    args = parser.parse_args()

    metadata_path = args.metadata_path.resolve()
    cache_path = args.cache_path.resolve()
    model_name = (
        args.description_model_name
        if args.description_backend == "llama2"
        else "template"
    )

    print(f"metadata_path = {metadata_path}")
    print(f"cache_path = {cache_path}")
    print(f"description_backend = {args.description_backend}")
    print(f"description_model_name = {model_name}")

    metadata_rows = load_metadata(metadata_path)
    end_index = None if args.limit <= 0 else args.start_index + args.limit
    selected_rows = metadata_rows[args.start_index:end_index]

    store = CachedDescriptionStore(cache_path)
    generator = build_description_generator(
        backend=args.description_backend,
        model_name=args.description_model_name,
        prompt_version=args.description_prompt_version,
        use_4bit=args.description_use_4bit,
        max_new_tokens=args.description_max_new_tokens,
        temperature=args.description_temperature,
        debug_output=args.debug_llama_output,
    )

    generated_or_updated = 0
    skipped = 0
    for offset, metadata in enumerate(selected_rows, start=args.start_index):
        raw_poi_id = metadata.get("raw_poi_id") or metadata.get("id") or metadata.get("raw_location_id")
        started = time.time()
        cache_key = build_description_cache_key(
            poi_metadata=metadata,
            dataset=args.dataset,
            backend=args.description_backend,
            model_name=model_name,
            prompt_version=args.description_prompt_version,
        )

        if args.only_missing and store.get(cache_key) is not None:
            skipped += 1
            print(f"[{offset}] raw_poi_id={raw_poi_id} cache=hit skipped")
            continue

        try:
            descriptions = generator.generate_descriptions(metadata)
            store.set(
                cache_key,
                {
                    "raw_poi_id": raw_poi_id,
                    "item_id": metadata.get("item_id"),
                    "description_backend": args.description_backend,
                    "description_model_name": model_name,
                    "description_prompt_version": args.description_prompt_version,
                    "descriptions": descriptions,
                },
            )
            generated_or_updated += 1
            elapsed = time.time() - started
            print(
                f"[{offset}] raw_poi_id={raw_poi_id} cache=miss generated "
                f"time={elapsed:.3f}s"
            )
        except Exception as exc:
            print(f"[{offset}] raw_poi_id={raw_poi_id} warning: generation failed: {exc}")
            continue

        if generated_or_updated % max(args.save_every, 1) == 0:
            store.save()
            print(f"Saved cache after {generated_or_updated} generated/updated POIs.")

    store.save()
    print(
        "Done. "
        f"generated_or_updated={generated_or_updated}, skipped={skipped}, "
        f"cache_path={cache_path}"
    )


if __name__ == "__main__":
    main()
