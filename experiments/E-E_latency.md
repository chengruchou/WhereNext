# E-E: Is it fast enough for a live demo?

Written 2026-10-29, before the timing code was written or run. The predictions are hypotheses;
results are reported against them as they come out.

## Question

How long does each stage take per request, and does a three-stop route come back fast enough
to feel interactive at a booth?

## Scope of this run

The model stages only, on CPU: sequence model, spatial and semantic reranking, request steering
(including the habit scores within a request) and route planning. Reading the request with
Claude, writing the explanation with Claude, and Google road routes call external services;
they are timed separately on a small sample with the authors' keys.

## Data

300 cases from the E-F sample (first 300), each run once without a request and once with a
request for the next place's type. The model is loaded and warmed up before timing; the cold
start is timed once and reported apart.

## Metrics

p50 and p95 per stage and for the whole route (three stops), from the stage timings the system
already records in its evidence, plus wall-clock time per route.

## Predictions

1. Every model stage has p95 under 100 ms on CPU.
2. A three-stop route with a request has p95 under 1 s on CPU.
3. The cold start (loading the model, metadata and embeddings) takes more than 5 s, so the
   server must load everything at startup, before the first visitor.

## Results (run 2026-10-29, model stages only)

The predictions above are left as written. Script: `experiments/offline_suite.py --experiment E`
(CPU, 300 timed routes of three stops each, after 5 untimed warm-up routes; 1.1 minutes).

| Stage, per step | No request: p50 / p95 (ms) | With request: p50 / p95 (ms) |
|---|---|---|
| Sequence model | 15.4 / 20.8 | 15.3 / 20.6 |
| Spatial reranking | 0.5 / 0.6 | 0.5 / 0.6 |
| Semantic reranking | 0.5 / 0.6 | 0.5 / 0.6 |
| Request steering (with habit scores) | skipped | 21.2 / 27.7 |
| Route planning | 0.2 / 0.3 | 0.2 / 0.7 |
| **Three-stop route, wall clock** | **50.0 / 66.0** | **112.9 / 143.2** |

Cold start: 12.0 s to load everything and return the first route, plus 5.4 s the first time a
request is scored (the sentence encoder for the request signal loads then).

Against the predictions:

1. Held: the slowest stage, request steering, has p95 27.7 ms.
2. Held: p95 143 ms for a three-stop route with a request.
3. Held: 12.0 s, and 17.4 s in total including the first request. The server should load the
   model, metadata, embeddings and the sentence encoder at startup.

Not covered yet: reading the request with Claude, writing the explanation with Claude, and
Google road routes. These call external services and are timed separately with the authors' keys.

Rerun on the code of 2026-11-01, with the CPU idle: a route with a request took p50 112.4 ms and
p95 129.7 ms, and without one 50.1 and 57.9 ms. The p50s match; the paper keeps the first run's
higher p95s.

## External services (run 2026-10-30)

Timed during the E-A2 and E-D batch (`experiments/claude_runs.py --mode batch`), one call at a
time, from the authors' machine in Taiwan:

| Call | Calls | p50 | p95 |
|---|---|---|---|
| Claude reads a request (claude-opus-5-5, effort low) | 207 | 1.7 s | 2.7 s |
| Claude writes a route's explanation (effort medium) | 54 | 5.2 s | 7.3 s |
| Google Routes API, one leg (the 150 legs of E-D's routes) | 150 | 0.08 s | 0.12 s |

No call failed; every leg returned a road route. A request at the booth therefore takes about
2 s to read, the route under 0.2 s on the CPU, and the explanation about 5 s more, which the
interface shows after the route.
