"""E-A1: the keyword parser on requests whose meaning is known by construction.

Design and predictions, written before this ran: experiments/E-A1_keyword_parser.md.
No model and no external API are needed.

    python experiments/ea1_keyword_parser.py --split dev --label v1 --out ea1_dev_v1.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services.intent_parser import (
    CategoryVocabulary,
    content_words,
    parse_with_keywords,
    resolve_intent,
)

METADATA = Path(__file__).resolve().parents[1] / "backend" / "datasets" / "filtered_poi_metadata.json"
PER_SPLIT = 60

# (development templates, held-out additions); {t} is the type, {a} and {b} two types
WANT = (["a {t}", "take me to a {t}", "I'd like to visit a {t}"], ["show me a {t} please"])
PLURAL = (["{tl}s around here"], [])
NEGATION = (["no {t}", "avoid {t}", "without a {t}"], ["skip the {t}"])
OTHER_NEGATION = (["I don't want a {t}", "anything but a {t}", "not in the mood for a {t}"],
                  ["I'd rather not go to a {t}"])
COMBINED = (["a {a}, no {b}", "a {a} but not a {b}"], ["{a} please, but skip {b}"])
TWO_TYPES = (["a {a} and then a {b}"], ["first a {a}, after that a {b}"])
MODE = ([("a {t} on foot", "walk"), ("walk to a {t}", "walk"), ("a {t} by car", "drive"),
         ("a {t} by bus", "transit"), ("a {t} by subway", "transit")],
        [("take the tram to a {t}", "transit")])
DISTANCE = ([("a {t} within 2 km", 2.0), ("a {t} within 3 miles", 4.828),
             ("a {t} less than 500 m away", 0.5), ("a {t} under 1 km", 1.0)],
            [("a {t} at most 2 kilometers away", 2.0)])
STRENGTH = ([("I must go to a {t}", "firm"), ("only a {t}", "firm"), ("maybe a {t}", "soft")],
            [("it has to be a {t}", "firm")])
EXPLORE = ([("somewhere new, a {t}", "new"), ("a {t} I've never been to", "new"),
            ("my usual {t}", "familiar")], [("a {t} I haven't tried", "new")])
UNSUPPORTED = (["a cheap {t}", "a {t} that is open late", "a quiet {t}"],
               ["a {t} with a nice view"])
LANGUAGES = ([("un musée", "Museum"), ("una playa", "Beach"), ("eine Bäckerei", "Bakery"),
              ("我想去動物園", "Zoo"), ("una biblioteca", "Library")],
             [("博物館に行きたい", "Museum"), ("一間咖啡店", "Coffee Shop"),
              ("une église", "Church"), ("ein Flughafen", "Airport"), ("un acuario", "Aquarium")])


def split_of(name: str) -> str:
    return "dev" if int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % 2 == 0 else "test"


def typo(name: str) -> str | None:
    """Swap two adjacent letters in the middle of the longest word (five letters or more)."""
    words = name.split()
    longest = max(range(len(words)), key=lambda i: len(words[i]))
    word = words[longest]
    if len(word) < 5:
        return None
    i = len(word) // 2 - 1
    swapped = word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if swapped.casefold() == word.casefold():
        return None
    words[longest] = swapped
    return " ".join(words)


def requests(split: str, types: list[str], rng: random.Random):
    """Yield (family, text, gold) for one split."""
    held_out = split == "test"

    def pick(templates):
        dev, extra = templates
        return dev + extra if held_out else dev

    partners = types[1:] + types[:1]
    for t, b in zip(types, partners, strict=True):
        if set(content_words(t)) & set(content_words(b)):
            b = next(x for x in types if not set(content_words(t)) & set(content_words(x)))
        for template in pick(WANT):
            yield "W want", template.format(t=t), {"want": [t]}
        if not t.endswith("s"):
            for template in pick(PLURAL):
                yield "P plural", template.format(tl=t.lower()), {"want": [t]}
        for template in pick(NEGATION):
            yield "N1 negation", template.format(t=t), {"avoid": [t]}
        for template in pick(OTHER_NEGATION):
            yield "N2 other negation", template.format(t=t), {"avoid": [t]}
        for template in pick(COMBINED):
            yield "C combined", template.format(a=t, b=b), {"want": [t], "avoid": [b]}
        for template in pick(TWO_TYPES):
            yield "M two types", template.format(a=t, b=b), {"want": [t, b]}
        misspelled = typo(t)
        if misspelled:
            yield "T typo", f"a {misspelled}", {"want": [t], "unresolved_ok": True}
        template, mode = rng.choice(pick(MODE))
        yield "Mode", template.format(t=t), {"want": [t], "mode": mode}
        template, km = rng.choice(pick(DISTANCE))
        yield "Distance", template.format(t=t), {"want": [t], "km": km}
        template, strength = rng.choice(pick(STRENGTH))
        yield "Strength", template.format(t=t), {"want": [t], "strength": strength}
        template, explore = rng.choice(pick(EXPLORE))
        yield "Explore", template.format(t=t), {"want": [t], "explore": explore}
        template = rng.choice(pick(UNSUPPORTED))
        yield "Unsupported", template.format(t=t), {"want": [t], "unsupported": True}
    for text, t in LANGUAGES[1 if held_out else 0]:
        yield "L language", text, {"want": [t], "unresolved_ok": True}


def key(name: str) -> str:
    return name.strip().casefold()


def score(family: str, gold: dict[str, Any], intent) -> dict[str, Any]:
    want = {key(m.category_name) for m in intent.want}
    avoid = {key(m.category_name) for m in intent.avoid}
    silent = not want and not avoid and not intent.unresolved
    gold_want = [key(t) for t in gold.get("want", [])]
    gold_avoid = [key(t) for t in gold.get("avoid", [])]
    types_right = all(t in want for t in gold_want) and all(
        t in avoid and t not in want for t in gold_avoid)
    polarity = any(t in avoid for t in gold_want) or any(t in want for t in gold_avoid)
    if gold.get("unresolved_ok") and not want and intent.unresolved:
        types_right = True
    if "mode" in gold:
        right = intent.travel_mode == gold["mode"]
    elif "km" in gold:
        right = intent.max_hop_km is not None and abs(intent.max_hop_km - gold["km"]) <= 0.05 * gold["km"]
    elif "strength" in gold:
        right = intent.strength == gold["strength"]
    elif "explore" in gold:
        right = intent.explore == gold["explore"]
    elif gold.get("unsupported"):
        right = bool(intent.unsupported)
    else:
        right = types_right
    return {"right": right, "types_right": types_right, "polarity": polarity, "silent": silent,
            "n_want": len(want)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--label", required=True, help="parser version, e.g. v1")
    parser.add_argument("--seed", type=int, default=16)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    vocabulary = CategoryVocabulary.from_metadata(METADATA)
    names = sorted({n.strip() for n in vocabulary.names if n.strip() and len(n.split()) <= 3})
    rng = random.Random(args.seed)
    pool = [n for n in names if split_of(n) == args.split]
    types = rng.sample(pool, PER_SPLIT)

    rows = []
    for family, text, gold in requests(args.split, types, random.Random(args.seed + 1)):
        parsed = parse_with_keywords(text, vocabulary)
        intent = resolve_intent(parsed, query=text, vocabulary=vocabulary, source="keyword")
        rows.append({"family": family, "text": text, "gold": gold, **score(family, gold, intent),
                     "want": [m.category_name.strip() for m in intent.want],
                     "avoid": [m.category_name.strip() for m in intent.avoid],
                     "unresolved": intent.unresolved, "mode": intent.travel_mode,
                     "max_hop_km": intent.max_hop_km, "strength": intent.strength,
                     "explore": intent.explore, "unsupported": intent.unsupported})

    table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        table[row["family"]].append(row)
    summary = {}
    print(f"keyword parser {args.label}, {args.split}: {len(rows)} requests over {len(types)} types")
    print(f"{'family':20}{'n':>5}{'right':>8}{'wrong list':>12}{'silent':>8}")
    for family, group in table.items():
        n = len(group)
        summary[family] = {"n": n, **{k: sum(r[k] for r in group) / n
                                      for k in ("right", "polarity", "silent")}}
        s = summary[family]
        print(f"{family:20}{n:5d}{s['right']:8.1%}{s['polarity']:12.1%}{s['silent']:8.1%}")
    one_type = [r for r in table["W want"]]
    summary["mean wanted types, W"] = sum(r["n_want"] for r in one_type) / len(one_type)
    print(f"mean wanted types for a one-type request: {summary['mean wanted types, W']:.2f}")
    args.out.write_text(json.dumps({"label": args.label, "split": args.split, "types": types,
                                    "summary": summary, "rows": rows}, ensure_ascii=False,
                                   indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
