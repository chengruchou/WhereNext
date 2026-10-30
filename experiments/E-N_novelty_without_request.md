# E-N: Does "somewhere new" change routes when no type is requested?

Written 2026-10-30, before the code for it was written or run. The predictions are hypotheses;
results are reported against them as they come out.

## Why

E-G found that while a type is requested, the novelty weight changes at most 2% of first stops:
every kept place has the same type, so it has the same novelty. The paper still presents
novelty as one of the weights the wording sets ("somewhere new" 0.3, "familiar" 0, otherwise
0.1). Without a requested type, every candidate competes, and novelty can separate types the
traveler has visited from new ones. Does it?

## Data

500 cases, seed 17, one per session, from sessions no earlier sample used (E-B seeds 7 to 9,
E-C 10, E-F 11, E-D1 12 and 13, E-C2 14, E-G 15). Same filters as E-C2: the next place is new to
the user and known to the model and metadata.

## Settings

A request with no type (`want` empty) and novelty set by its wording, so lambda is 0 and the
score is the base plus novelty: familiar (novelty 0), balanced (0.1, the default when a request
names no preference) and new (0.3). Three-stop routes, drive, built as `/route` builds them.

## Metrics

- Share of routes whose first stop, and whose stop sequence, differ from balanced.
- Share of stops whose type the history contains.
- The actual next place: HR@1, HR@10 and MRR in the first step's ranking.
- Median first leg (km).

## Predictions

1. "New" changes at least 20% of first stops compared with balanced; "familiar" at least 5%.
2. "New" lowers the share of stops in a history type by at least 5 points compared with
   balanced; "familiar" raises it by at least 2 points.
3. The actual next place's HR@10 differs from balanced by less than 0.03 for either setting.

## What follows

If 1 and 2 hold, the paper can say novelty works when no type is requested and does little
within one. If they fail, the paper should drop novelty as a lever.

## Results (run 2026-10-30)

The predictions above are left as written. Script: `experiments/en_novelty_without_request.py`
(seed 17, MG-DSGAT on CPU, 2.6 minutes). 500 cases from 500 sessions; over 990 drawn, 293 came
from sessions an earlier sample used, 3 from a session already taken, 179 were revisits and 15
lacked metadata or were unknown to the model.

| | Familiar (0) | Balanced (0.1) | New (0.3) |
|---|---|---|---|
| First stop differs from balanced | 2.6% | | 5.0% |
| Route differs from balanced | 5.4% | | 10.6% |
| Stops in a type the history contains | 12.3% | 11.1% | 9.2% |
| Actual next place: HR@1 / HR@10 / MRR | 0.094 / 0.288 / 0.166 | 0.096 / 0.282 / 0.166 | 0.096 / 0.280 / 0.164 |
| Median first leg (km) | 0.62 | 0.57 | 0.57 |

Against the predictions:

1. Failed: "new" changes 5.0% of first stops (at least 20% predicted), "familiar" 2.6% (at
   least 5%).
2. Failed: "new" lowers the share of stops in a history type by 1.9 points (at least 5
   predicted), "familiar" raises it by 1.2 (at least 2).
3. Held: HR@10 moves by at most 0.006.

Why: novelty can only separate candidates of familiar and new types, and the pool rarely holds
familiar ones. Visited places are excluded and the backbone's candidates are mostly of types the
traveler has not visited, so only 11% of stops are of a history type even at balance; the
novelty bonus lifts nearly every candidate by the same amount. A probe of three cases showed
every top candidate with novelty 1.0.

What follows: the paper should not present "somewhere new" or "my usual" as levers that change
the route. The wording sets them, the evidence records them, and their effect is small with or
without a requested type (E-G and here). Making them matter would need candidates of familiar
types in the pool (for "my usual") or a stronger, distance-aware novelty term; neither is tested.
