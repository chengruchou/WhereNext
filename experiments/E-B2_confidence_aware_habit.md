# E-B2: A habit score that follows the model's confidence

Written 2026-10-29 after E-B and before any code for this follow-up was written or run.
The predictions below are hypotheses; results are reported against them as they come out.

## Why

In E-B, scoring every request-matched place with the sequence model and min-max normalizing
the scores over those places (M5) did not rank better than using habit only for the model's
own top candidates (M4), and habit alone (M3) only tied with nearest-first (M1). One possible
reason: min-max spreads habit from 1 to 0 across the candidates whether or not the model is
confident, so a near-random habit order outweighs distance. If so, a habit score that stays
flat when the model is unsure and peaks when it is sure should let distance decide in the
first case and habit in the second.

## Variants

Let s_i be the model's raw score for candidate i among the request-matched places.

| ID | Habit value for candidate i | Behaviour |
|---|---|---|
| M5 | (s_i - min s) / (max s - min s) | E-B system: always spans 0 to 1 |
| M6a | exp(s_i - max s) | Relative likelihood: the top place is 1, the others fall with the model's confidence |
| M6b | exp(s_i) / sum_j exp(s_j) | The model's probability renormalized over the candidates; sums to 1 |

M6a and M6b use the model's own scale (temperature 1, as trained with cross-entropy); nothing
is tuned. Everything else (signals, weights, travel cost, lambda) is as in E-B.

## Data

Same filters as E-B. Two fresh samples of 2,000 cases each, excluding every case the E-B
sample (seed 7) used and each other:

- **Selection sample (seed 8):** all rankings M0 to M6b are run; the default is chosen here.
- **Confirmation sample (seed 9):** only after the choice is fixed; reports the chosen
  default against M1, M2 and M4. The paper reports the confirmation numbers.

## Mechanism check

Model confidence for a case is the largest M6b value among its candidates. Cases are split,
before looking at results, into low (< 0.3), medium (0.3 to 0.6) and high (>= 0.6) confidence.

## Predictions (selection sample)

1. M6a and M6b both have higher MRR than M5, and at least one of them by a paired interval that
   excludes 0.
2. The better of M6a and M6b is at least as good as M4: its paired MRR difference against M4 has
   a lower bound above -0.01.
3. Mechanism: M3 (habit alone) beats M1 (nearest) in high-confidence cases and loses to it in
   low-confidence cases.
4. For histories of three or more check-ins, the better variant is not worse than M1 (its paired
   interval against M1 includes 0 or lies above it), unlike M5 in E-B.

## Decision rule (fixed now)

On the selection sample, the default habit normalization becomes the variant among M4, M5, M6a
and M6b with the highest MRR, provided its paired MRR difference against M1 excludes 0;
differences under 0.005 MRR go to the simpler variant, in the order M4, M5, M6a, M6b. The
confirmation sample then reports that default once, with no further changes.

## Results: selection sample (seed 8, run 2026-10-29)

2,000 cases after excluding the 2,000 E-B cases. Filters over 3,721 cases drawn: 863 revisits,
65 without metadata, 484 beyond reach, 309 with fewer than two candidates. The target was among
the kept places in 99.6% of cases for every variant.

| Ranking | HR@1 | HR@5 | MRR | MRR minus M1 |
|---|---|---|---|---|
| M0 random | 0.152 | 0.522 | 0.323 [0.313, 0.333] | |
| M1 nearest | 0.390 | 0.728 | 0.541 [0.523, 0.557] | |
| M2 most check-ins | 0.307 | 0.663 | 0.470 [0.453, 0.487] | |
| M3 habit alone | 0.412 | 0.737 | 0.558 [0.540, 0.575] | +0.017 [+0.002, +0.034] |
| M4 no habit scoring | 0.419 | 0.743 | 0.564 [0.547, 0.581] | +0.023 [+0.013, +0.033] |
| M5 min-max habit | 0.424 | 0.754 | 0.571 [0.553, 0.588] | +0.031 [+0.016, +0.046] |
| M6a relative habit | 0.412 | 0.760 | 0.564 [0.548, 0.581] | +0.024 [+0.009, +0.038] |
| M6b softmax habit | 0.419 | 0.763 | 0.569 [0.552, 0.587] | +0.028 [+0.015, +0.043] |

Paired MRR differences among variants: M6a - M5 = -0.007 [-0.011, -0.002]; M6b - M5 = -0.002
[-0.006, +0.002]; M5 - M4 = +0.008 [-0.004, +0.019]; M6b - M4 = +0.005 [-0.005, +0.016].

| Model confidence | Cases | MRR M1 | MRR M3 | M3 - M1 | M5 - M1 |
|---|---|---|---|---|---|
| Low (< 0.3) | 163 | 0.224 | 0.224 | +0.000 [-0.053, +0.055] | +0.023 [-0.025, +0.073] |
| Medium (0.3 to 0.6) | 634 | 0.426 | 0.413 | -0.013 [-0.042, +0.018] | +0.012 [-0.015, +0.038] |
| High (>= 0.6) | 1,203 | 0.644 | 0.679 | +0.035 [+0.013, +0.055] | +0.041 [+0.022, +0.060] |

For histories of three or more check-ins (774 cases), M6b - M1 = +0.016 [-0.007, +0.040] and
M5 - M1 = +0.018 [-0.007, +0.043].

Against the predictions:

1. Failed. Neither confidence-aware variant beat min-max: M6a is lower by an interval that
   excludes 0, and M6b is within noise of M5.
2. Held. M6b - M4 has a lower bound of -0.005, above -0.01.
3. Partly held. Habit alone beats nearest where the model is confident (+0.035, 60% of cases)
   but only ties it at low and medium confidence; it does not lose there.
4. Held. For histories of three or more, M6b is not worse than M1; nor is M5 on this sample.

Decision: M5 has the highest MRR (0.571), leads the simpler M4 by 0.008 (more than 0.005), and
its difference against M1 excludes 0. The default stays min-max (M5).

## Results: confirmation sample (seed 9, run 2026-10-29)

Run once, after the decision, with only M4 and the chosen default; these are the numbers the
paper reports. 2,000 cases after excluding the 4,000 cases of seeds 7 and 8. Filters over 3,814
cases drawn: 927 revisits, 71 without metadata, 466 beyond reach, 350 with fewer than two
candidates. The target was among the kept places in 99.9% of cases.

| Ranking | HR@1 | HR@5 | MRR |
|---|---|---|---|
| M0 random | 0.155 [0.148, 0.162] | 0.526 [0.510, 0.543] | 0.328 [0.319, 0.338] |
| M1 nearest | 0.388 [0.367, 0.411] | 0.716 [0.697, 0.737] | 0.534 [0.517, 0.551] |
| M2 most check-ins | 0.296 [0.278, 0.317] | 0.667 [0.646, 0.687] | 0.463 [0.446, 0.480] |
| M3 habit alone | 0.404 [0.381, 0.426] | 0.746 [0.725, 0.764] | 0.554 [0.537, 0.572] |
| M4 no habit scoring | 0.441 [0.418, 0.463] | 0.745 [0.726, 0.764] | 0.575 [0.558, 0.592] |
| M5 WhereNext (default) | 0.418 [0.396, 0.440] | 0.758 [0.739, 0.776] | 0.568 [0.550, 0.585] |

Paired MRR differences for the default: against M1 +0.034 [+0.019, +0.048]; against M2 +0.104
[+0.085, +0.123]; against M4 -0.007 [-0.018, +0.005]. Habit alone against M1: +0.020
[+0.005, +0.036].

| Subset | Cases | MRR M1 | MRR M5 | M5 - M1 |
|---|---|---|---|---|
| History 1 | 812 | 0.558 | 0.581 | +0.023 [-0.000, +0.045] |
| History 2 | 424 | 0.496 | 0.536 | +0.039 [+0.006, +0.074] |
| History 3 or more | 764 | 0.529 | 0.571 | +0.042 [+0.017, +0.067] |
| Confidence low (< 0.3) | 185 | 0.256 | 0.233 | -0.022 [-0.070, +0.026] |
| Confidence medium (0.3 to 0.6) | 619 | 0.401 | 0.406 | +0.006 [-0.023, +0.036] |
| Confidence high (>= 0.6) | 1,196 | 0.646 | 0.703 | +0.057 [+0.038, +0.075] |

## What the paper can say

- Within the requested type, WhereNext finds the place the user actually went next more often
  than nearest-first (MRR +0.034, HR@5 0.758 against 0.716) and than most-check-ins (MRR
  +0.104), on a sample untouched by any design decision.
- The gain comes from cases where the sequence model is confident (60% of cases, +0.057 MRR);
  where it is unsure, WhereNext is no different from nearest-first.
- Scoring every request-matched place with the model did not change ranking quality in any of
  the three samples (M5 - M4: -0.010, +0.008, -0.007, all intervals including 0). Its purpose is
  that every candidate carries the same, real habit signal in the evidence; the paper should not
  claim a ranking gain from it.
- The request is built from the actual next place's type, so this measures choosing within a
  known type, not what real users ask for.

