"""E-A3: a sentence encoder reads the request directly, with no LLM and no rules.

Design and predictions, written before this ran: experiments/E-A3_sentence_encoder.md.
Runs on a CPU and calls no external API; the LLM's and the keyword parser's scores come from the
saved E-A2 run.

    python experiments/ea3_sentence_encoder.py --out ea3.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import ea1_keyword_parser as ea1
from claude_runs import HELD_OUT_ONLY
from contracts.intent import IntentPhrase, ParsedIntent
from services.intent_parser import CategoryVocabulary, resolve_intent

ENCODER = "sentence-transformers/all-MiniLM-L6-v2"  # the app's default intent encoder
BATCH = Path(__file__).resolve().parent / "results" / "claude_batch_2026-10-30.json"
ENCODER_READERS = {"top 1": 1, "top 8": 8}
READERS = ("claude", "keyword", *ENCODER_READERS)
MEASURES = ("right", "types_right", "polarity")


def read(text: str, nearest: list[str], vocabulary: CategoryVocabulary):
    parsed = ParsedIntent(want=[IntentPhrase(phrase=text, category_hints=nearest)])
    return resolve_intent(parsed, query=text, vocabulary=vocabulary, source="keyword")


def mean(rows: list[dict[str, Any]], reader: str, measure: str) -> float:
    return float(np.mean([row[reader][measure] for row in rows]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    vocabulary = CategoryVocabulary.from_metadata(ea1.METADATA)
    names = list(vocabulary.names)
    model = SentenceTransformer(ENCODER, device="cpu")
    types = model.encode(names, normalize_embeddings=True, convert_to_numpy=True)

    batch = json.loads(BATCH.read_text(encoding="utf-8"))["E-A2"]
    rows = [{k: r[k] for k in ("split", "family", "text", "gold", "claude", "keyword")}
            for r in batch]
    requests = model.encode([r["text"] for r in rows], normalize_embeddings=True,
                            convert_to_numpy=True)
    for row, similarities in zip(rows, requests @ types.T, strict=True):
        order = np.argsort(-similarities)
        for reader, k in ENCODER_READERS.items():
            nearest = [names[i] for i in order[:k]]
            row[reader] = ea1.score(row["family"], row["gold"],
                                    read(row["text"], nearest, vocabulary))
            row[f"{reader} types"] = nearest

    families = sorted({r["family"] for r in rows})
    held_out = [r for r in rows if r["split"] == "test"
                and any(p in r["text"].casefold() for p in HELD_OUT_ONLY)]
    summary: dict[str, Any] = {"all": {}, "held-out-only": {}, "families": {}, "worst family": {}}
    for reader in READERS:
        summary["all"][reader] = {m: mean(rows, reader, m) for m in MEASURES}
        summary["held-out-only"][reader] = {m: mean(held_out, reader, m) for m in MEASURES}
    for family in families:
        group = [r for r in rows if r["family"] == family]
        summary["families"][family] = {"n": len(group)} | {
            reader: {m: mean(group, reader, m) for m in MEASURES} for reader in READERS}
    for reader in READERS:
        by_family = {f: summary["families"][f][reader]["right"] for f in families}
        worst = min(by_family, key=by_family.get)
        summary["worst family"][reader] = [worst, by_family[worst]]
    summary["held-out-only"]["n"] = len(held_out)

    print(f"{'family':22}{'n':>4}" + "".join(f"{r:>14}" for r in READERS))
    for family in families:
        row = summary["families"][family]
        cells = "".join(f"{row[r]['right']:8.1%} {row[r]['types_right']:5.0%}" for r in READERS)
        print(f"{family:22}{row['n']:4d}{cells}")
    for label, group in (("all", summary["all"]), ("held-out-only", summary["held-out-only"])):
        print(f"{label:26}" + "".join(f"{group[r]['right']:8.1%} {group[r]['types_right']:5.0%}"
                                      for r in READERS))
    print("worst family", summary["worst family"])
    for family in ("N1 negation", "N2 other negation"):
        print(family, "refused type chosen by top 1:",
              f"{summary['families'][family]['top 1']['polarity']:.1%}")

    args.out.write_text(json.dumps({"encoder": ENCODER, "summary": summary, "rows": rows},
                                   ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
