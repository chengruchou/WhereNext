# E-B: Does habit find the right place once the request fixes the type?

Written 2026-10-29, before the evaluation script was written or run. The predictions below
are hypotheses. Results are reported against them as they come out, including where they
fail.

## Question

When a request names a place type and places of that type are within reach, WhereNext keeps
only those places and ranks them. Does ranking them by the sequence model's habit score
find the place the user actually went to next more often than ranking by distance or by
popularity, which is what a planner without the user's history could do?

## Data

- Gowalla test split (`test_with_timestamps.json`): each case is a history and the next
  check-in.
- Sample: 2,000 cases, seed 7, drawn from cases where
  - the next place is not in the history (WhereNext never recommends a visited place; about
    23% of test cases are revisits, and they are excluded by design),
  - the next place has a category and lies within the drive reach (40 km) of the last visit,
  - at least two not-yet-visited places of that category lie within reach, so ranking is not
    trivial.
- How many cases each filter removes is reported with the results.

## Request

The request is the category of the actual next place ("I want a History Museum"), with the
default drive reach and the soft strength (lambda = 0.5); the firm strength (0.8) is a
secondary setting. Because the request is built from the answer, this measures whether the
system picks the right place once the type is known. It does not measure what real users
ask for.

## Rankings compared

All rankings score the same candidates: every not-yet-visited place of the requested category
within 40 km of the last visit.

| ID | Ranking | Role |
|---|---|---|
| M0 | Random | Floor; expected values computed exactly |
| M1 | Nearest to the last visit first | Request-only baseline |
| M2 | Most check-ins first | Request-only baseline |
| M3 | Sequence-model score alone | Habit without distance |
| M4 | WhereNext, request-matched places without a habit score | The system before this change |
| M5 | WhereNext, every request-matched place scored by the sequence model | The system |

M4 and M5 rank the candidates the system itself keeps (the backbone's top candidates plus the
nearest places of the requested type), so they can miss the target; the share of cases where
the target is among the kept candidates is reported. The first stop of a route is used, with
the route planner's travel cost included, as in the deployed system.

## Metrics

HR@1, HR@5 and MRR of the actual next place, each with a 95% bootstrap confidence interval
(1,000 resamples over cases), and paired bootstrap intervals for M5 - M1 and M5 - M2. Broken
down by history length (1, 2, 3 or more) and by candidate-pool size.

## Predictions

1. M3 beats both M1 and M2 on HR@1 and MRR, with intervals that do not overlap; M1, M2 and M3
   all beat M0. No prediction is made about M1 versus M2.
2. M4 is within the confidence interval of M1, because places that join only through the
   request are then ordered by distance.
3. M5 beats M4 by more than the confidence interval, and is close to M3: adding the travel
   cost changes the habit ranking little.
4. The gain of M5 over M1 is larger for histories of three or more check-ins than for a
   single check-in.
5. The target is among the candidates WhereNext keeps in at least 95% of cases.

## What would change the paper

If M3 does not beat M2 (habit is no better than popularity within the requested type), the
claim that habit ranks places within a request is not supported. The paper then reports the
request-first behaviour with distance and popularity as the within-type ranking and states
this result.

## Results (run 2026-10-29)

The predictions above are left as written. A 50-case smoke run checked the pipeline first;
its numbers were not used.

Setup as designed: 2,000 cases, seed 7, soft strength (lambda = 0.5), 40 km reach, up to 100
request-matched places, 1,000 bootstrap resamples, MG-DSGAT checkpoint on CPU. Filters over
the 3,734 test cases drawn: 929 revisits, 62 without metadata, 392 beyond reach, 351 with fewer
than two candidates. The target was among the places WhereNext kept in 99.2% of cases.

| Ranking | HR@1 | HR@5 | MRR |
|---|---|---|---|
| M0 random | 0.158 [0.151, 0.165] | 0.535 [0.518, 0.551] | 0.332 [0.321, 0.342] |
| M1 nearest | 0.416 [0.396, 0.440] | 0.733 [0.713, 0.751] | 0.558 [0.540, 0.577] |
| M2 most check-ins | 0.308 [0.287, 0.329] | 0.686 [0.665, 0.705] | 0.477 [0.460, 0.494] |
| M3 habit alone | 0.421 [0.401, 0.444] | 0.738 [0.719, 0.757] | 0.565 [0.549, 0.582] |
| M4 WhereNext, no habit scoring | 0.449 [0.425, 0.470] | 0.759 [0.738, 0.778] | 0.586 [0.569, 0.604] |
| M5 WhereNext | 0.433 [0.411, 0.456] | 0.755 [0.737, 0.774] | 0.577 [0.559, 0.593] |

Paired MRR differences: M5 - M1 = +0.018 [+0.003, +0.034]; M5 - M2 = +0.100 [+0.083, +0.118];
M5 - M4 = -0.010 [-0.021, +0.001].

| History length | Cases | MRR M1 | MRR M3 | MRR M4 | MRR M5 | M5 - M1 | M5 - M4 |
|---|---|---|---|---|---|---|---|
| 1 | 797 | 0.549 | 0.575 | 0.582 | 0.578 | +0.028 [+0.006, +0.052] | -0.005 [-0.022, +0.012] |
| 2 | 432 | 0.553 | 0.583 | 0.589 | 0.604 | +0.051 [+0.018, +0.084] | +0.014 [-0.010, +0.038] |
| 3 or more | 771 | 0.571 | 0.544 | 0.588 | 0.560 | -0.011 [-0.034, +0.014] | -0.028 [-0.045, -0.009] |

Against the predictions:

1. Partly failed. Habit alone beats popularity and random, but not nearest: M3 and M1 overlap
   on every metric.
2. Failed. M4 is above M1 (MRR 0.586 against 0.558): putting the model's own top candidates
   first and the rest by distance beats distance alone.
3. Failed. Scoring every request-matched place did not help: M5 is no better than M4 overall
   and worse for histories of three or more check-ins.
4. Failed, in the opposite direction: the gain over nearest is largest for short histories and
   absent for three or more.
5. Held: 99.2%.

The stop criterion was not met (M3 beats M2), so the paper can say that WhereNext's ranking
within the request finds the next place more often than distance (+0.018 MRR) or popularity
(+0.100 MRR). It cannot say that the sequence model alone beats distance, or that scoring
every candidate improved ranking.

A possible reading, not yet tested: min-max normalizing the model's raw scores over the
candidates spreads habit evenly from best to worst whether or not the model is confident, so
habit outweighs distance even when it carries little information. M4 uses habit only where the
model ranked a place among its own top candidates, which is where it is most informative. Any
change made on this basis needs its own written prediction and a fresh sample (another seed),
not this one.
