"""Score annotators' labels of Claude's sentences against the verifiers' verdicts.

Input: the responses workbook of the four annotation forms, downloaded from Google Sheets as
.xlsx, plus the batch's key.csv and sentences.csv. Each form has its own tab with one row per
submission; a sentence's column is titled "#<id>［<stop>］<sentence>".

Prints, with annotators as A1, A2, ... in order of their first submission:
- how many sentences each labelled, and with which labels;
- agreement over the three labels: Cohen's kappa for every pair, Fleiss' kappa for three or more;
- each verifier's precision (of the sentences it removed, how many the annotator called
  unsupported) and recall (of the sentences the annotator called unsupported, how many it removed);
- the share of supported sentences marked misleading, overall and for habit wording.

Needs only the standard library.
Run: python experiments/ed_score_annotation.py RESPONSES.xlsx
         [--batch experiments/E-D2_annotation] [--labels OUT.csv] [--names]
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import zipfile
from collections import Counter
from itertools import combinations
from pathlib import Path
from xml.etree import ElementTree

MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DOC_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

# The forms' four choices: the label, and whether it also marks the sentence misleading.
CHOICES = {
    "有根據": ("supported", False),
    "有根據但會誤導": ("supported", True),
    "沒根據": ("unsupported", False),
    "無可查證": ("nothing to check", False),
}
NAME_COLUMN = "你的名字"
SENTENCE_COLUMN = re.compile(r"#(\d+)［")
# A word match, as in the E-D note: the sentence speaks of habits or of a usual pattern.
HABIT_WORDING = re.compile(r"habit|usual|pattern|routine", re.IGNORECASE)
VERIFIERS = ("verifier/2.2", "verifier/2.1", "verifier/1")


def read_workbook(path: Path) -> dict[str, list[dict[int, str]]]:
    """Each tab's rows as {column index: text}. Numbers come back as their text."""

    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            for item in ElementTree.fromstring(archive.read("xl/sharedStrings.xml")):
                runs = item.findall(f"{MAIN}t") + item.findall(f"{MAIN}r/{MAIN}t")
                shared.append("".join(run.text or "" for run in runs))
        targets = {
            rel.get("Id"): rel.get("Target")
            for rel in ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            if rel.tag == f"{PKG_REL}Relationship"
        }
        tabs: dict[str, list[dict[int, str]]] = {}
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        for sheet in workbook.iter(f"{MAIN}sheet"):
            target = targets[sheet.get(f"{DOC_REL}id")].lstrip("/")
            target = target if target.startswith("xl/") else f"xl/{target}"
            rows = []
            for row in ElementTree.fromstring(archive.read(target)).iter(f"{MAIN}row"):
                cells = {}
                for cell in row.iter(f"{MAIN}c"):
                    text = _cell_text(cell, shared)
                    if text != "":
                        cells[_column(cell.get("r"))] = text
                if cells:
                    rows.append(cells)
            tabs[sheet.get("name")] = rows
    return tabs


def _cell_text(cell: ElementTree.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{MAIN}t"))
    value = cell.find(f"{MAIN}v")
    if value is None or value.text is None:
        return ""
    return shared[int(value.text)] if kind == "s" else value.text


def _column(reference: str) -> int:
    index = 0
    for letter in reference:
        if letter.isalpha():
            index = index * 26 + ord(letter.upper()) - ord("A") + 1
    return index - 1


def read_labels(path: Path) -> tuple[dict[str, dict[int, tuple[str, bool]]], list[str]]:
    """Every annotator's labels by sentence id, annotators in order of first submission."""

    labels: dict[str, dict[int, tuple[str, bool]]] = {}
    first_seen: dict[str, float] = {}
    problems: list[str] = []
    for tab, rows in read_workbook(path).items():
        if not rows:
            continue
        header = rows[0]
        ids = {col: int(match.group(1)) for col, title in header.items()
               if (match := SENTENCE_COLUMN.match(title))}
        name_col = next((col for col, title in header.items() if title == NAME_COLUMN), None)
        if not ids or name_col is None:
            continue
        for row in rows[1:]:
            name = row.get(name_col, "").strip()
            if not name:
                problems.append(f"{tab}: a submission without a name was skipped")
                continue
            try:
                submitted = float(row.get(0, "0"))
            except ValueError:
                submitted = 0.0
            first_seen[name] = min(first_seen.get(name, submitted), submitted)
            own = labels.setdefault(name, {})
            for col, sentence_id in ids.items():
                choice = row.get(col, "").strip()
                if choice not in CHOICES:
                    problems.append(f"{tab}: #{sentence_id} has no usable label ({choice!r})")
                    continue
                if sentence_id in own and own[sentence_id] != CHOICES[choice]:
                    problems.append(f"{tab}: #{sentence_id} was labelled twice; the later one counts")
                own[sentence_id] = CHOICES[choice]
    order = sorted(labels, key=lambda name: (first_seen[name], name))
    return {name: labels[name] for name in order}, problems


def cohen_kappa(first: list[str], second: list[str]) -> float:
    total = len(first)
    observed = sum(a == b for a, b in zip(first, second)) / total
    expected = sum((first.count(c) / total) * (second.count(c) / total)
                   for c in set(first) | set(second))
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def fleiss_kappa(items: list[list[str]]) -> float:
    raters = len(items[0])
    categories = sorted({label for item in items for label in item})
    share = {c: sum(item.count(c) for item in items) / (len(items) * raters) for c in categories}
    per_item = [(sum(item.count(c) ** 2 for c in categories) - raters) / (raters * (raters - 1))
                for item in items]
    observed = sum(per_item) / len(items)
    expected = sum(value ** 2 for value in share.values())
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def ratio(part: int, whole: int) -> str:
    return f"{part}/{whole}" + (f" ({100 * part / whole:.1f}%)" if whole else " (none)")


def score_verifiers(reference: dict[int, str], key: dict[int, dict[str, str]]) -> None:
    unsupported = {i for i, label in reference.items() if label == "unsupported"}
    for verifier in VERIFIERS:
        removed = {i for i in reference if key[i][verifier] == "unsupported"}
        caught = sorted(removed & unsupported)
        print(f"    {verifier:13} removed {len(removed):3}: precision {ratio(len(caught), len(removed))}, "
              f"recall {ratio(len(caught), len(unsupported))}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("responses", type=Path, help="the forms' responses workbook (.xlsx)")
    parser.add_argument("--batch", type=Path, default=Path(__file__).parent / "E-D2_annotation",
                        help="folder with key.csv and sentences.csv")
    parser.add_argument("--labels", type=Path, help="write the labels to this CSV, by sentence id")
    parser.add_argument("--names", action="store_true", help="print which name is A1, A2, ...")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    with (args.batch / "key.csv").open(encoding="utf-8-sig", newline="") as handle:
        key = {int(row["id"]): row for row in csv.DictReader(handle)}
    with (args.batch / "sentences.csv").open(encoding="utf-8-sig", newline="") as handle:
        sentences = {int(row["id"]): row["sentence"] for row in csv.DictReader(handle)}

    by_name, problems = read_labels(args.responses)
    annotators = {f"A{n}": by_name[name] for n, name in enumerate(by_name, start=1)}
    for problem in problems:
        print("warning:", problem)
    if args.names:
        for code, name in zip(annotators, by_name):
            print(f"{code} = {name}")

    print(f"{len(key)} sentences in the key; {len(annotators)} annotator(s)")
    for code, own in annotators.items():
        unknown = sorted(set(own) - set(key))
        counts = Counter(label for label, _ in own.values())
        print(f"\n{code}: labelled {len(set(own) & set(key))} of {len(key)}"
              + (f"; {len(unknown)} ids not in the key" if unknown else ""))
        print("    " + ", ".join(f"{label} {counts[label]}"
                                 for label in ("supported", "unsupported", "nothing to check")))
        supported = [i for i, (label, _) in own.items() if label == "supported" and i in key]
        misleading = [i for i in supported if own[i][1]]
        habit = [i for i in supported if HABIT_WORDING.search(sentences[i])]
        print(f"    supported but misleading: {ratio(len(misleading), len(supported))}; with habit "
              f"wording: {ratio(sum(own[i][1] for i in habit), len(habit))}")
        print(f"    unsupported ids: {sorted(i for i, (label, _) in own.items() if label == 'unsupported')}")
        score_verifiers({i: label for i, (label, _) in own.items() if i in key}, key)

    for (code_a, a), (code_b, b) in combinations(annotators.items(), 2):
        both = sorted(set(a) & set(b) & set(key))
        if both:
            kappa = cohen_kappa([a[i][0] for i in both], [b[i][0] for i in both])
            same = sum(a[i][0] == b[i][0] for i in both)
            print(f"\n{code_a} and {code_b}: Cohen's kappa {kappa:.3f} on {len(both)} sentences, "
                  f"same label on {ratio(same, len(both))}")
    if len(annotators) >= 2:
        shared = sorted(set(key).intersection(*annotators.values()))
        if len(annotators) >= 3 and shared:
            table = [[own[i][0] for own in annotators.values()] for i in shared]
            print(f"\nFleiss' kappa {fleiss_kappa(table):.3f} on {len(shared)} sentences")
        agreed = {i: next(iter(annotators.values()))[i][0] for i in shared
                  if len({own[i][0] for own in annotators.values()}) == 1}
        split = sorted(set(shared) - set(agreed))
        print(f"\nAll annotators agree on {ratio(len(agreed), len(shared))}; to resolve: {split}")
        print("  against the sentences they agree on:")
        score_verifiers(agreed, key)

    if args.labels:
        with args.labels.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["id"] + [f"{code}{suffix}" for code in annotators
                                      for suffix in ("", " misleading")])
            for sentence_id in sorted(key):
                row: list[str | int] = [sentence_id]
                for own in annotators.values():
                    label, flag = own.get(sentence_id, ("", False))
                    row += [label, "yes" if flag else ""]
                writer.writerow(row)
        print(f"\nwrote {args.labels}")


if __name__ == "__main__":
    main()
