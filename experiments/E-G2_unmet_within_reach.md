# E-G2: Keep an unmet request's stops within reach

Written 2026-10-30, before the change was written or run. The predictions are hypotheses;
results are reported against them as they come out.

## Why

In E-G (G2), a request on foot that the data could not meet within 2 km left habit to pick the
stop from the whole candidate pool: 46.7% of those first legs exceeded 2 km and 26.6% exceeded
10 km. The travel cost stops growing once a hop passes the reach (beta = 0.2 at most), so habit
can outweigh any distance. A traveler who said "on foot" should not be sent 10 km.

## Change

When a request is in force and no place of the requested types lies within reach of the previous
stop (`in_range` = 0), habit ranks only the candidates within that reach: the stated maximum hop,
else the travel mode's reach. If no candidate is within reach, it ranks the five nearest. A
configuration flag (`intent_unmet_within_reach`, on by default) keeps the old behaviour
available. Steps where the request is met are not touched.

## Data

The 500 E-G cases (seed 15, one per session). Request: the next place's type (R1), soft. Three-
stop routes on foot (2 km) and by car (40 km), each built with the change off and on.

## Metrics

- Hops at unmet steps: median, share beyond the mode's reach, share over 10 km.
- All hops of the three-stop routes: share beyond reach.
- Routes in which every step meets the request: share identical with and without the change.
- Cases unmet at the first step: MRR of the actual next place in the first step's ranking.

## Predictions

1. With the change off, the first legs of unmet walk cases reproduce E-G: 46.7% over 2 km and
   26.6% over 10 km. With it on, at most 10% exceed 2 km and at most 3% exceed 10 km.
2. By car, at most 5% of first legs in unmet cases exceed 40 km with the change on.
3. Every route whose steps all meet the request is identical with and without the change.
4. In cases unmet at the first step on foot, the actual next place's MRR falls, to at most 0.02
   with the change on: that place is of the requested type, so it lies beyond reach, and keeping
   the stop near rules it out.
5. Over all hops of the walk routes, the share beyond 2 km falls by at least half.

## Results (run 2026-10-30)

The predictions above are left as written. Script: `experiments/eg2_unmet_within_reach.py`
(MG-DSGAT on CPU, 5.5 minutes). Code: `steering.py` (the reach limit, `UNMET_NEAREST` = 5) and
`model_config.py` (`intent_unmet_within_reach`, env `WHERENEXT_UNMET_WITHIN_REACH`).

| | On foot, off | On foot, on | By car, off | By car, on |
|---|---|---|---|---|
| Cases unmet at the first step | 229 | 229 | 43 | 43 |
| First leg of those: median km | 1.19 | 0.47 | 4.67 | 1.28 |
| ... beyond reach (2 / 40 km) | 46.7% | 15.3% | 23.3% | 0.0% |
| ... over 10 km | 26.6% | 3.5% | 37.2% | 20.9% |
| All unmet steps beyond reach | 33.5% | 12.5% | 8.2% | 1.2% |
| All route hops beyond reach | 19.4% | 7.5% | 1.7% | 0.3% |
| MRR of the actual next place, unmet first step | 0.110 | 0.025 | 0.047 | 0.000 |
| Routes met at every step: identical | 132 of 132 | | 329 of 329 | |

All 35 first legs on foot that still exceed 2 km with the change on start where the data has no
unvisited place within 2 km at all, so the stop is the nearest the data offers.

Against the predictions:

1. Partly held. With the change off, the walk numbers reproduce E-G exactly (46.7%, 26.6%). With
   it on, 15.3% exceed 2 km (at most 10% predicted) and 3.5% exceed 10 km (at most 3%): every one
   of those cases has nothing unvisited within 2 km, which the prediction did not allow for.
2. Held: no first leg by car exceeds 40 km (23.3% before).
3. Held: every route whose steps all meet the request is unchanged (132 on foot, 329 by car).
4. Partly held: the actual next place's MRR falls, from 0.110 to 0.025 on foot (at most 0.02
   predicted) and from 0.047 to 0 by car.
5. Held: the share of walk hops beyond 2 km falls from 19.4% to 7.5%.

Decision: the change stays on by default. It costs finding the actual next place in cases the
request cannot meet (MRR 0.110 to 0.025 on foot), because that place lies beyond the reach the
traveler stated; keeping the stated mode is the behaviour the interface promises ("These stops
follow your habits instead" within the stated reach). The paper's sentence "When no wanted place
is in reach, habit decides" should add "among places within reach".
