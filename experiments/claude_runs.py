"""Claude-backed runs for E-D and E-A2, through the app's own parser and explainer.

Designs and predictions, written before any call: experiments/E-D_real_explanations.md and
experiments/E-A2_claude_parser.md. Every call goes through a recorder that counts it, stops at
--max-calls, and keeps its tokens and latency. The SDK does not retry (max_retries=0), so each
counted call is one API request. The key is read from backend/.env and never printed.

    python experiments/claude_runs.py --mode trial --test-split <path> --max-calls 5 --out trial.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import subprocess
import sys
import tempfile
import time
from itertools import pairwise
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import anthropic
import ea1_keyword_parser as ea1
import numpy as np
import requests
from contracts.intent import CategoryMatch, Intent
from dotenv import dotenv_values
from ec2_request_not_answer import draw, earlier_sessions, request, session_key
from ed1_verifier_mutation import OfflineRoutes
from offline_suite import REACH_KM, Setup
from routes import route_api
from services import grounded_explainer
from services.explanation_verifier import verify_explanation
from services.intent_parser import (
    CategoryVocabulary,
    IntentParser,
    parse_with_keywords,
    resolve_intent,
)

# USD per million tokens for claude-opus-5-5 (Claude API pricing; cache writes at 5-minute TTL).
PRICE = {"input": 4.0, "output": 20.0, "cache_read": 0.20, "cache_write": 5.0}
AUSTIN = [18417, 15326, 480992]  # the paper's Fig. 1 traveler: three coffee shops
VERIFIER_V1_COMMIT = "3889177"  # last commit before verifier/2


class CallLimit(Exception):
    pass


class Recorder:
    """Stands in for the Anthropic client: counts, caps and times every messages.parse call."""

    def __init__(self, client: anthropic.Anthropic, max_calls: int, max_usd: float = float("inf")):
        self._client = client
        self.max_calls = max_calls
        self.max_usd = max_usd
        self.calls: list[dict[str, Any]] = []
        self.beta = self
        self.messages = self
        self.kind = "?"

    def spent(self) -> float:
        return sum(c.get("usd", 0.0) for c in self.calls)

    def parse(self, **kwargs: Any) -> Any:
        if len(self.calls) >= self.max_calls:
            raise CallLimit(f"stopped before call {len(self.calls) + 1}: --max-calls reached")
        if self.spent() >= self.max_usd:
            raise CallLimit(f"stopped before call {len(self.calls) + 1}: --max-usd reached")
        started = time.perf_counter()
        record: dict[str, Any] = {"kind": self.kind}
        self.calls.append(record)
        try:
            response = self._client.beta.messages.parse(**kwargs)
        except Exception as exc:  # recorded, then raised to the app code as usual
            record.update(error=type(exc).__name__, seconds=time.perf_counter() - started)
            raise
        usage = response.usage
        record.update(
            seconds=time.perf_counter() - started,
            model=response.model,
            stop_reason=response.stop_reason,
            input=usage.input_tokens,
            output=usage.output_tokens,
            cache_write=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            cache_read=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )
        record["usd"] = sum(record[k] * PRICE[p] for k, p in (
            ("input", "input"), ("output", "output"), ("cache_read", "cache_read"),
            ("cache_write", "cache_write"))) / 1e6
        return response


def client_from_env() -> anthropic.Anthropic:
    key = dotenv_values(ROOT / "backend" / ".env").get("ANTHROPIC_API_KEY")
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY not found in backend/.env")
    return anthropic.Anthropic(api_key=key, max_retries=0)


def verifier_v1():
    """The earlier verifier, loaded from git history so sentences can be rechecked offline."""
    source = subprocess.run(
        ["git", "show", f"{VERIFIER_V1_COMMIT}:backend/services/explanation_verifier.py"],
        cwd=ROOT, capture_output=True, check=True).stdout
    path = Path(tempfile.mkdtemp()) / "explanation_verifier_v1.py"
    path.write_bytes(source)
    spec = importlib.util.spec_from_file_location("explanation_verifier_v1", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def explain(recorder: Recorder, ev: dict[str, Any], categories: list[str], v1,
            extra: dict[str, Any] | None = None) -> dict[str, Any]:
    recorder.kind = "explain"
    try:
        response = grounded_explainer.request_explanation(recorder, ev)
    except anthropic.AnthropicError as exc:
        return {"call": recorder.calls[-1], "error": f"{type(exc).__name__}: {exc}"[:300]}
    out: dict[str, Any] = {"call": recorder.calls[-1]}
    if response.parsed_output is None:
        out["error"] = f"no explanation (stop_reason={response.stop_reason})"
        return out
    explanation = response.parsed_output
    now = verify_explanation(explanation, ev, categories)
    before = v1.verify_explanation(explanation, ev, categories)
    sentences = [(None, i, s) for i, s in enumerate(explanation.summary)] + [
        (step.step, i, s) for step in explanation.steps for i, s in enumerate(step.sentences)]
    v2 = {(v.step, v.index): v for v in now.verdicts}
    v1_by = {(v.step, v.index): v for v in before.verdicts}
    out["sentences"] = [
        {"step": step, "text": s.text, "refs": s.evidence_refs,
         "v2": v2[(step, i)].verdict, "v2_reason": v2[(step, i)].reason,
         "v1": v1_by[(step, i)].verdict, "v1_reason": v1_by[(step, i)].reason}
        for step, i, s in sentences]
    out["verifier"] = now.verifier_version
    for name, module in (extra or {}).items():
        other = {(v.step, v.index): v
                 for v in module.verify_explanation(explanation, ev, categories).verdicts}
        for row, (step, i, _) in zip(out["sentences"], sentences, strict=True):
            row[name], row[f"{name}_reason"] = other[(step, i)].verdict, other[(step, i)].reason
    out["unmet_steps"] = [s["step"] for s in ev["steps"]
                          if (s.get("intent") or {}).get("in_range") == 0]
    return out


def trial(args, setup: Setup, recorder: Recorder) -> dict[str, Any]:
    """Five calls: the Fig. 1 request and route, one E-A2 request, two E-D routes."""
    routes = OfflineRoutes(setup)
    vocabulary = CategoryVocabulary.from_metadata(setup.config.poi_metadata_path)
    categories = vocabulary.names
    parser = IntentParser(setup.config, client=recorder)
    v1 = verifier_v1()
    out: dict[str, Any] = {}

    recorder.kind = "parse"
    austin_intent = parser.parse("A museum, nothing with coffee")
    out["fig1 parse"] = {"intent": austin_intent.model_dump(mode="json"),
                         "call": recorder.calls[-1]}
    out["fig1 route"] = explain(recorder, routes.evidence(AUSTIN, austin_intent), categories, v1)

    recorder.kind = "parse"
    probe = parser.parse("博物館に行きたい")
    out["E-A2 probe"] = {"query": "博物館に行きたい", "intent": probe.model_dump(mode="json"),
                         "call": recorder.calls[-1]}

    excluded = earlier_sessions(setup)
    for n, seed in ((1000, 14), (500, 15), (500, 17)):  # E-C2, E-G, E-N
        drawn, _ = draw(setup, n, seed, excluded)
        excluded |= {session_key(setup.test[c["index"]]) for c in drawn}
    cases, _ = draw(setup, 2, 18, excluded)
    other_case, walk_case = cases
    km = setup.km_from(other_case["history"][-1])
    nearby = sorted({c for c in setup.cats[(km <= REACH_KM["drive"])
                                           & ~np.isin(setup.ids, other_case["history"])]
                     if c and c.strip() != other_case["category"].strip()})
    other = nearby[len(nearby) // 2]
    out["E-D route 1 (another type, drive)"] = explain(
        recorder, routes.evidence(other_case["history"], request([other], other.lower())),
        categories, v1)
    walk = Intent(query=f"a {walk_case['category'].strip().lower()} on foot", source="user_edit",
                  want=[CategoryMatch(category_name=walk_case["category"],
                                      phrase=walk_case["category"].strip().lower(),
                                      method="user_edit")], travel_mode="walk")
    out["E-D route 2 (next type, on foot)"] = explain(
        recorder, routes.evidence(walk_case["history"], walk), categories, v1)
    return out


def projection(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Tokens and cost of the full batch from the trial's per-call averages."""
    plan = {"parse": 200 + 4, "explain": 50 + 4}  # E-A2 + demo cache, E-D + demo cache
    out: dict[str, Any] = {"planned calls": plan}
    total = 0.0
    for kind, n in plan.items():
        done = [c for c in calls if c["kind"] == kind and "usd" in c]
        if not done:
            continue
        mean = {k: sum(c[k] for c in done) / len(done)
                for k in ("input", "output", "cache_write", "cache_read", "usd", "seconds")}
        # In a batch the shared system prompt is written once and read by the later calls.
        prefix = max(c["cache_write"] + c["cache_read"] for c in done)
        warm = (mean["input"] * PRICE["input"] + mean["output"] * PRICE["output"]
                + prefix * PRICE["cache_read"]) / 1e6
        cost = mean["usd"] + (n - 1) * warm
        out[kind] = {"trial calls": len(done), "mean per call": mean,
                     "projected usd (cache warm after the first call)": cost,
                     "projected usd (every call as in the trial)": n * mean["usd"]}
        total += cost
    out["projected total usd"] = total
    return out


# ---- the batch ---------------------------------------------------------------------------

PROBES = ["a museum, nothing with coffee", "no coffee please", "something new on foot"]
DEMO = {"austin": ([18417, 15326, 480992], ["A museum, nothing with coffee", "A beach"]),
        "grapevine": ([15906, 18149, 9419], ["I want to see a museum",
                                             "A museum within 2 km on foot"])}
# Phrasings only E-A1's held-out set uses (its templates' additions).
HELD_OUT_ONLY = ("show me a", "skip the", "rather not", "but skip", "after that", "take the tram",
                 "at most", "it has to be", "haven't tried", "nice view")
GOOGLE_MODES = {"drive": "DRIVE", "walk": "WALK", "transit": "TRANSIT"}


def ea2_requests(seed: int = 19) -> list[dict[str, Any]]:
    """100 development and 100 held-out E-A1 requests, per family in proportion, at least 3."""
    vocabulary = CategoryVocabulary.from_metadata(ea1.METADATA)
    names = sorted({n.strip() for n in vocabulary.names if n.strip() and len(n.split()) <= 3})
    chosen = []
    for split in ("dev", "test"):
        rng = random.Random(16)
        types = rng.sample([n for n in names if ea1.split_of(n) == split], ea1.PER_SPLIT)
        rows = [{"split": split, "family": f, "text": t, "gold": g}
                for f, t, g in ea1.requests(split, types, random.Random(17))]
        families: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            families.setdefault(row["family"], []).append(row)
        quota = {f: max(3, round(100 * len(rs) / len(rows))) for f, rs in families.items()}
        while sum(quota.values()) > 100:  # trim the largest quotas back to 100
            quota[max(quota, key=quota.get)] -= 1
        pick = random.Random(seed)
        for family, rs in families.items():
            chosen += pick.sample(rs, min(quota[family], len(rs)))
    return chosen


def ed_routes(setup: Setup, seed: int = 18, skip: int = 2) -> list[dict[str, Any]]:
    """50 routes with E-D's request mix: seed 18 after the trial's two cases (E-D), or another
    seed from sessions E-D did not use either (E-D2)."""
    excluded = earlier_sessions(setup)
    earlier = ((1000, 14), (500, 15), (500, 17)) + (((52, 18),) if seed != 18 else ())
    for n, s in earlier:  # E-C2, E-G, E-N (and E-D)
        drawn, _ = draw(setup, n, s, excluded)
        excluded |= {session_key(setup.test[c["index"]]) for c in drawn}
    cases, _ = draw(setup, 50 + skip, seed, excluded)
    pick = random.Random(seed)
    plan = []
    for i, case in enumerate(cases[skip:]):
        category = case["category"]
        if i < 20:
            kind, intent = "next type, drive", request([category], category.strip().lower())
        elif i < 35:
            km = setup.km_from(case["history"][-1])
            nearby = sorted({c for c in setup.cats[(km <= REACH_KM["drive"])
                                                   & ~np.isin(setup.ids, case["history"])]
                             if c and c.strip() != category.strip()})
            other = pick.choice(nearby)
            kind, intent = "another type, drive", request([other], other.strip().lower())
        elif i < 45:
            kind = "next type, on foot"
            intent = request([category], category.strip().lower()).model_copy(
                update={"travel_mode": "walk"})
        else:
            kind = "no type, somewhere new"
            intent = Intent(query="somewhere new", source="user_edit", explore="new")
        plan.append({"index": case["index"], "kind": kind, "history": case["history"],
                     "intent": intent})
    return plan


def google_leg(key: str, mode: str, a: tuple[float, float], b: tuple[float, float]):
    """One Routes API call for one leg, bypassing the app's cache; returns seconds and outcome."""
    payload: dict[str, Any] = {"origin": route_api._waypoint(*a),
                               "destination": route_api._waypoint(*b),
                               "travelMode": mode, "polylineEncoding": "ENCODED_POLYLINE"}
    started = time.perf_counter()
    try:
        resp = requests.post(route_api.ROUTES_URL, json=payload, timeout=route_api.TIMEOUT_S,
                             headers={"X-Goog-Api-Key": key,
                                      "X-Goog-FieldMask": route_api.FIELD_MASK})
        ok = resp.status_code == 200 and bool(resp.json().get("routes"))
        status = resp.status_code
    except requests.RequestException as exc:
        ok, status = False, type(exc).__name__
    return {"seconds": time.perf_counter() - started, "ok": ok, "status": status, "mode": mode}


def batch(args, setup: Setup, recorder: Recorder) -> dict[str, Any]:
    """E-A2 parses and probes, demo parses, E-D and demo explanations, then Google legs."""
    vocabulary = CategoryVocabulary.from_metadata(setup.config.poi_metadata_path)
    categories = vocabulary.names
    parser = IntentParser(setup.config, client=recorder)
    routes = OfflineRoutes(setup)
    v1 = verifier_v1()
    out: dict[str, Any] = {"E-A2": [], "probes": [], "E-D": [], "demo": [], "google": []}

    def save() -> None:
        out["calls"] = recorder.calls
        args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    def parse(text: str) -> tuple[Intent, dict[str, Any]]:
        recorder.kind = "parse"
        before = len(recorder.calls)
        intent = parser.parse(text)
        return intent, (recorder.calls[-1] if len(recorder.calls) > before else {})

    # Parses first, so their shared system prompt stays in the cache.
    for n, row in enumerate(ea2_requests(), start=1):
        intent, call = parse(row["text"])
        keyword = resolve_intent(parse_with_keywords(row["text"], vocabulary), query=row["text"],
                                 vocabulary=vocabulary, source="keyword")
        out["E-A2"].append({**row, "claude": ea1.score(row["family"], row["gold"], intent),
                            "keyword": ea1.score(row["family"], row["gold"], keyword),
                            "fallback": intent.parser.fallback if intent.parser else None,
                            "intent": intent.model_dump(mode="json"), "call": call})
        if n % 25 == 0:
            print(f"E-A2 {n}, ${recorder.spent():.2f}", flush=True)
            save()
    for text in PROBES:
        intent, call = parse(text)
        out["probes"].append({"text": text, "intent": intent.model_dump(mode="json"),
                              "call": call})
    demo_intents = {}
    for name, (history, requests_) in DEMO.items():
        for text in requests_:
            demo_intents[(name, text)] = parse(text)
    save()

    for n, route in enumerate(ed_routes(setup), start=1):
        ev = routes.evidence(route["history"], route["intent"])
        result = explain(recorder, ev, categories, v1)
        out["E-D"].append({"index": route["index"], "kind": route["kind"],
                           "intent": route["intent"].model_dump(mode="json"), "evidence": ev,
                           **result})
        if n % 10 == 0:
            print(f"E-D {n}, ${recorder.spent():.2f}", flush=True)
            save()
    for (name, text), (intent, call) in demo_intents.items():
        history = DEMO[name][0]
        ev = routes.evidence(history, intent)
        out["demo"].append({"traveler": name, "request": text, "parse": call,
                            "intent": intent.model_dump(mode="json"), "evidence": ev,
                            **explain(recorder, ev, categories, v1)})
    save()

    key = (dotenv_values(ROOT / "backend" / ".env").get("GOOGLE_MAPS_API_KEY")
           or dotenv_values(ROOT / "backend" / ".env").get("VITE_GOOGLE_API_KEY"))
    if key:
        for route in out["E-D"]:
            ev = route["evidence"]
            points = [(p["latitude"], p["longitude"]) for p in ev["history"][-1:]] + [
                (s["poi"]["latitude"], s["poi"]["longitude"]) for s in ev["steps"]]
            mode = GOOGLE_MODES.get(route["intent"]["travel_mode"], "DRIVE")
            for a, b in pairwise(points):
                if len(out["google"]) >= args.max_google:
                    break
                out["google"].append(google_leg(key, mode, a, b))
    else:
        out["google_skipped"] = "no Google key in backend/.env"
    save()
    return out


def validate(args, setup: Setup, recorder: Recorder) -> dict[str, Any]:
    """E-D2: one explanation for each of 50 fresh routes, checked by verifier/2.2, verifier/2.1
    (experiments/verifier_v2_1.py) and the earlier check."""
    spec = importlib.util.spec_from_file_location(
        "verifier_v2_1", Path(__file__).resolve().parent / "verifier_v2_1.py")
    v21 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v21)
    categories = CategoryVocabulary.from_metadata(setup.config.poi_metadata_path).names
    routes = OfflineRoutes(setup)
    v1 = verifier_v1()
    out: dict[str, Any] = {"E-D2": []}
    for n, route in enumerate(ed_routes(setup, seed=21, skip=0), start=1):
        ev = routes.evidence(route["history"], route["intent"])
        out["E-D2"].append({"index": route["index"], "kind": route["kind"],
                            "intent": route["intent"].model_dump(mode="json"), "evidence": ev,
                            **explain(recorder, ev, categories, v1, {"v2.1": v21})})
        if n % 10 == 0:
            print(f"E-D2 {n}, ${recorder.spent():.2f}", flush=True)
            out["calls"] = recorder.calls
            args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def analyse_validation(data: dict[str, Any]) -> dict[str, Any]:
    routes = [r for r in data["E-D2"] if "sentences" in r]
    sentences = [s for r in routes for s in r["sentences"]]
    res: dict[str, Any] = {"routes": len(data["E-D2"]), "explained": len(routes),
                           "sentences": len(sentences),
                           "usd": sum(c.get("usd", 0.0) for c in data.get("calls", []))}
    for v, label in (("v2", "verifier/2.2"), ("v2.1", "verifier/2.1"), ("v1", "verifier/1")):
        res[label] = {k: float(np.mean([s[v] == k for s in sentences]))
                      for k in ("supported", "unverifiable", "unsupported")}
    shown = [any(s["step"] == st["step"] and s["v2"] != "unsupported" for s in r["sentences"])
             for r in routes for st in r["evidence"]["steps"]]
    res["stops with a shown sentence"] = float(np.mean(shown))
    res["removed by verifier/2.2"] = [
        {"text": s["text"], "reason": s["v2_reason"], "refs": s["refs"], "step": s["step"],
         "kind": r["kind"]}
        for r in routes for s in r["sentences"] if s["v2"] == "unsupported"]
    return res


def percentile(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def analyse(data: dict[str, Any]) -> dict[str, Any]:
    """The design's metrics from a saved batch."""
    res: dict[str, Any] = {}
    calls = data.get("calls", [])
    res["calls"] = {k: sum(c["kind"] == k for c in calls) for k in ("parse", "explain")}
    res["errors"] = sum("error" in c for c in calls)
    res["usd"] = sum(c.get("usd", 0.0) for c in calls)
    for kind in ("parse", "explain"):
        secs = [c["seconds"] for c in calls if c["kind"] == kind and "usd" in c]
        res[f"{kind} seconds p50 / p95"] = [percentile(secs, 50), percentile(secs, 95)]

    rows = data["E-A2"]
    fams: dict[str, dict[str, list[Any]]] = {}
    for r in rows:
        f = fams.setdefault(r["family"], {"claude": [], "keyword": []})
        f["claude"].append(r["claude"])
        f["keyword"].append(r["keyword"])
    ea2: dict[str, Any] = {}
    for fam, d in fams.items():
        ea2[fam] = {who: {m: float(np.mean([x[m] for x in d[who]]))
                          for m in ("right", "polarity", "silent")} | {"n": len(d[who])}
                    for who in ("claude", "keyword")}
    held_out = [r for r in rows if r["split"] == "test"
                and any(p in r["text"].casefold() for p in HELD_OUT_ONLY)]
    ea2["held-out-only phrasings"] = {
        "n": len(held_out),
        "claude right": float(np.mean([r["claude"]["right"] for r in held_out])) if held_out
        else None,
        "keyword right": float(np.mean([r["keyword"]["right"] for r in held_out])) if held_out
        else None}
    ea2["all"] = {who: float(np.mean([r[who]["right"] for r in rows]))
                  for who in ("claude", "keyword")}
    ea2["fallbacks"] = sum(bool(r["fallback"]) for r in rows)
    ea2["mean wanted types, W (claude)"] = float(np.mean(
        [r["claude"]["n_want"] for r in rows if r["family"] == "W want"]))
    res["E-A2"] = ea2
    res["probes"] = [{"text": p["text"],
                      "want": [m["category_name"] for m in p["intent"]["want"]],
                      "avoid": [m["category_name"] for m in p["intent"]["avoid"]],
                      "mode": p["intent"]["travel_mode"], "explore": p["intent"]["explore"]}
                     for p in data["probes"]]

    routes = [r for r in data["E-D"] if "sentences" in r]
    sentences = [s for r in routes for s in r["sentences"]]
    ed: dict[str, Any] = {"routes": len(data["E-D"]), "explained": len(routes),
                          "sentences": len(sentences)}
    for v in ("v2", "v1"):
        ed[v] = {k: float(np.mean([s[v] == k for s in sentences]))
                 for k in ("supported", "unverifiable", "unsupported")}
    reasons: dict[str, int] = {}
    for s in sentences:
        if s["v2"] == "unsupported":
            key = (s["v2_reason"] or "").split(",")[0].split(" which")[0][:60]
            reasons[key] = reasons.get(key, 0) + 1
    ed["v2 removal reasons"] = dict(sorted(reasons.items(), key=lambda kv: -kv[1]))
    shown = []
    unmet_said = []
    said = re.compile(
        r"\b(?:no|not|none|nothing|couldn't|could not|can't|cannot)\b[^.]*\b(?:within|nearby|near|"
        r"in reach|close|around)\b|\bhabits?\b", re.IGNORECASE)
    for r in routes:
        for step in {s["step"] for s in r["sentences"]} | {st["step"] for st in
                                                           r["evidence"]["steps"]}:
            if step is None:
                continue
            kept = [s for s in r["sentences"] if s["step"] == step and s["v2"] != "unsupported"]
            shown.append(bool(kept))
            if step in r["unmet_steps"]:
                texts = [s["text"] for s in r["sentences"]
                         if s["step"] in (step, None) and s["v2"] != "unsupported"]
                unmet_said.append(any(said.search(t) for t in texts))
    ed["stops with a shown sentence"] = float(np.mean(shown))
    ed["unmet stops whose explanation says so (heuristic)"] = (
        float(np.mean(unmet_said)) if unmet_said else None, len(unmet_said))
    ed["by kind (v2 removed share)"] = {
        kind: float(np.mean([s["v2"] == "unsupported" for r in routes if r["kind"] == kind
                             for s in r["sentences"]]))
        for kind in sorted({r["kind"] for r in routes})}
    res["E-D"] = ed
    res["demo"] = [{"traveler": d["traveler"], "request": d["request"],
                    "v2": [s["v2"] for s in d.get("sentences", [])], "error": d.get("error")}
                   for d in data["demo"]]
    legs = data.get("google", [])
    res["google"] = {"legs": len(legs), "ok": float(np.mean([g["ok"] for g in legs]))
                     if legs else None,
                     "seconds p50 / p95": [percentile([g["seconds"] for g in legs], 50),
                                           percentile([g["seconds"] for g in legs], 95)]}
    return res


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["trial", "batch", "validate", "analyse"],
                        required=True)
    parser.add_argument("--test-split", type=Path)
    parser.add_argument("--max-calls", type=int, default=5)
    parser.add_argument("--max-usd", type=float, default=float("inf"))
    parser.add_argument("--max-google", type=int, default=200)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    if args.mode == "analyse":
        data = json.loads(args.out.read_text(encoding="utf-8"))
        summary = analyse_validation(data) if "E-D2" in data else analyse(data)
        print(json.dumps(summary, ensure_ascii=False, indent=1))
        return
    recorder = Recorder(client_from_env(), args.max_calls, args.max_usd)
    setup = Setup(args.test_split)
    run = {"trial": trial, "batch": batch, "validate": validate}[args.mode]
    try:
        result = run(args, setup, recorder)
    except CallLimit as exc:
        result = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else {}
        result["stopped"] = str(exc)
    result["calls"] = recorder.calls
    if args.mode == "trial":
        result["projection"] = projection(recorder.calls)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"calls": len(recorder.calls), "usd": recorder.spent(),
                      **({"projection": result["projection"]} if "projection" in result else {})},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
