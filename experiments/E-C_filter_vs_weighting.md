# E-C: Keep only the requested types, or weigh the request against habit?

Written 2026-10-29, before the evaluation code for it was written or run. The predictions are
hypotheses; results are reported against them as they come out.

## Question

WhereNext keeps only places of the requested types when any are within reach (the filter).
The alternative is a soft weighting, `(1 - lambda) * habit + lambda * request`, with nothing
removed. How do the two compare on (1) doing what was asked and (2) still finding the place the
user actually went to? And how often can a request be met at all within each travel mode's
reach?

## Data

Gowalla test split; cases whose next place is not in the history (revisits are never
recommended). New seeds, separate from E-B's samples:

- **C1 feasibility:** 2,000 cases (seed 10). For each case, is there at least one
  not-yet-visited place of the next place's type within 2 km (walk), 15 km (transit) and 40 km
  (drive) of the last visit?
- **C2 contrary requests:** 1,000 cases (seed 10, E-B's filters). The request is a type the
  user has not visited, other than the next place's type, with at least one place within 40 km;
  drawn at random per case. This is a request habit does not support.
- **C3 matched requests:** the same 1,000 cases, with the request set to the next place's type,
  as in E-B.

## Settings compared

The first stop of a route (travel cost included), drive reach:

| ID | Setting |
|---|---|
| F | Filter on, lambda = 0.5 (the soft-strength default) |
| W0.2, W0.5, W0.8, W1.0 | Filter off, lambda = 0.2, 0.5, 0.8, 1.0 |

## Metrics

- C1: share of cases with at least one place within reach, per travel mode.
- C2: the share of first stops of the requested type (request met at 1), and the share of
  requested-type places among the top five.
- C3: MRR and HR@5 of the actual next place, with 95% bootstrap intervals, and the paired MRR
  difference F - W0.5.

## Predictions

1. C1: a request for the next place's type can be met within reach in at least 50% of cases on
   foot, 80% by transit and 90% by car.
2. C2: with the filter, every first stop is of the requested type. With soft weighting, the share
   rises with lambda, stays below 90% at lambda = 0.5, and reaches 99% or more only at
   lambda >= 0.8.
3. C3: the filter finds the actual next place at least as well as soft weighting at the same
   lambda: F - W0.5 has a paired MRR interval above 0, because high-habit places of other types
   no longer push the requested ones down.

## Results (run 2026-10-29)

The predictions above are left as written. Script: `experiments/offline_suite.py --experiment C`
(seed 10, 1,000 bootstrap resamples, MG-DSGAT on CPU, 4.8 minutes).

**C1** (2,000 cases; 627 revisits and 54 others excluded along the way): a request for the next
place's type can be met within reach in 57.5% [55.3, 59.5] of cases on foot, 85.3% [83.8, 86.8]
by transit and 92.6% [91.5, 93.8] by car.

**C2** (1,000 cases, each with a type the user has not visited):

| Setting | Request met at the first stop | Requested type among the top five |
|---|---|---|
| F, filter, lambda 0.5 | 1.000 | 1.000 |
| W0.2 | 0.026 [0.017, 0.036] | 0.031 [0.026, 0.037] |
| W0.5 | 0.351 [0.322, 0.382] | 0.446 [0.429, 0.461] |
| W0.8 | 1.000 | 0.538 [0.516, 0.560] |
| W1.0 | 1.000 | 0.538 [0.516, 0.559] |

**C3** (the same 1,000 cases, requesting the next place's type):

| Setting | MRR | HR@5 |
|---|---|---|
| F, filter, lambda 0.5 | 0.570 [0.545, 0.592] | 0.757 [0.730, 0.785] |
| W0.2 | 0.259 [0.239, 0.279] | 0.329 [0.300, 0.359] |
| W0.5 | 0.488 [0.465, 0.511] | 0.704 [0.674, 0.733] |
| W0.8 | 0.567 [0.542, 0.590] | 0.750 [0.724, 0.776] |
| W1.0 | 0.538 [0.512, 0.564] | 0.723 [0.696, 0.752] |

Paired MRR difference F - W0.5: +0.082 [+0.065, +0.098].

Against the predictions:

1. Held: 57.5%, 85.3% and 92.6% against 50%, 80% and 90%.
2. Held: the filter met every request; soft weighting met 35.1% at lambda 0.5 and all of them only
   from 0.8. Even then, half the top five were other types.
3. Held: +0.082 MRR over soft weighting at the same lambda. Soft weighting matches the filter only
   at lambda 0.8 (MRR 0.567).

What the paper can say: keeping only the requested types does what was asked every time it can
(in 93% of drive-reach cases), and finds the place the user actually went to as well as the best
soft weighting, while soft weighting at the default lambda ignores most requests habit does not
support.
