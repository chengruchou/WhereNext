# E-G: Wording-derived weights, unmet requests and evidence that adds up

Written 2026-10-30, before the code for it was written or run. The predictions are hypotheses;
results are reported against them as they come out.

## Why

Three claims in the paper have only code behind them. (1) A fixed policy turns the request's
wording into weights: lambda 0.5 or 0.8 for a soft or firm request, novelty 0, 0.1 or 0.3. But
when one type is requested, the request relevance r and the novelty n are the same for every
kept place, so the weights may change little. (2) When no requested place is in reach, habit
decides; with no stated maximum hop nothing caps how far that stop is. (3) Each stop's evidence
parts add up to its score; the code only logs a warning when they do not match the pipeline's
score.

## Data

500 cases, seed 15, one per session, from sessions that no earlier sample (E-B seeds 7 to 9,
E-C 10, E-F 11, E-D1 12 and 13, E-C2 14) used; same filters as E-C2. Three-stop routes built
with evidence as `/route` builds them (database lookup replaced by the case's history).

## G1: wording

Requests as in E-C2: R1 the next place's type, R2 the parser's group for that type name, R3 a
random other type within 40 km (drive). Each route is built four times: default (soft,
balanced: lambda 0.5, novelty 0.1), firm (lambda 0.8), new (novelty 0.3) and familiar
(novelty 0). Metrics: share of routes whose first stop, and whose stop sequence, differ from the
default; share of stops in a type the history contains.

Predictions:

1. For one-type requests (R1, R3), firm changes at most 20% of first stops, and new or familiar
   at most 5%.
2. For group requests (R2), firm changes more first stops than for R1.
3. For one-type requests, "new" lowers the share of stops in a type the history contains by at
   most 2 points.

## G2: unmet requests on foot

R1 with travel mode walk (2 km reach). Metric: the first leg's km, split by whether a requested
place was in reach at the first stop (`intent.in_range`).

Predictions:

4. When a requested place is in reach, every first leg is at most 2 km.
5. When none is, at least 40% of first legs exceed 2 km and at least 15% exceed 10 km.

## G3: evidence adds up

Over every stop record built in G1 and G2: the number whose signal contributions differ from the
pipeline's score by more than 1e-6 (the warning `evidence_builder` logs).

Prediction:

6. None.

## Results (run 2026-10-30)

The predictions above are left as written. Script: `experiments/eg_steering_checks.py` (seed 15,
MG-DSGAT on CPU, 14.9 minutes). 500 cases from 500 sessions; over 989 drawn, 297 came from
sessions an earlier sample used, 2 from a session already taken, 169 were revisits and 21 lacked
metadata or were unknown to the model.

**G1.** Share of routes that change when only the wording changes (first stop / any stop):

| Request | Cases | Firm (lambda 0.8) | New (novelty 0.3) | Familiar (novelty 0) |
|---|---|---|---|---|
| R1 next place's type | 500 | 6.8% / 23.0% | 0.4% / 1.4% | 1.0% / 2.4% |
| R2 group of types | 293 | 11.6% / 37.5% | 2.0% / 10.6% | 1.7% / 11.3% |
| R3 another type | 499 | 3.8% / 20.4% | 0.0% / 1.2% | 0.0% / 1.2% |

Share of stops in a type the history contains (default / new / familiar): R1 13.8% / 13.3% /
14.5%; R2 15.2% / 13.9% / 17.0%; R3 2.7% / 2.5% / 3.1%.

**G2.** On foot, a requested place was in reach at the first stop in 271 cases; every first leg
there was at most 2 km. In the 229 cases with none in reach, the median first leg was 1.19 km,
46.7% exceeded 2 km and 26.6% exceeded 10 km.

**G3.** 0 of 17,004 stop records differ from the pipeline's score.

Against the predictions:

1. Held: for one-type requests, firm changes 6.8% and 3.8% of first stops; new and familiar at
   most 1.0%.
2. Held: firm changes 11.6% of first stops for group requests, against 6.8% for R1.
3. Held: "new" lowers the share of stops in a history type by 0.5 points (R1) and 0.2 (R3).
4. Held: all first legs within 2 km when the request can be met on foot.
5. Held: 46.7% over 2 km and 26.6% over 10 km when it cannot.
6. Held: every record adds up.

What this means for the paper and the system:

- The novelty weight does almost nothing while a request is in force: "somewhere new" or "my
  usual" changes at most 2% of first stops, and moves the share of familiar types by about half
  a point for one-type requests. Within one requested type every kept place has the same novelty,
  so only route costs and later stops can move. The paper should not present novelty as a lever
  of request-first routes; its effect without a request was not tested here.
- "Firm" works mainly through the route costs: with less weight on habit, travel and repetition
  costs count for more, which changes later stops (20% to 38% of routes) more than first ones.
- An unmet request on foot sends a quarter of travelers more than 10 km on the first leg. The
  travel cost is capped at beta = 0.2 once a hop exceeds the reach, so habit can outweigh any
  distance. Either the planner should keep unmet stops within reach of the stated mode, or the
  interface should say how far the habit stop is.
- The evidence claim holds: every record's parts add up to its score.
