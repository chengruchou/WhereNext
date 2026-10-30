# E-C2: Does the filter still help when the request is not the answer?

Written 2026-10-30, before the code for it was written or run. The predictions are hypotheses;
results are reported against them as they come out.

## Why

In E-C, the filter found the actual next place better than soft weighting at the same lambda
(MRR +0.082 for F - W0.5). But the request there was the next place's own type, so the request
was the answer: the filter gains by deleting every competitor of another type, which only helps
because the requested type is right. Reviewers also noted that E-C dropped cases whose next
place lies beyond drive reach, never compared the filter with W0.8 by a paired interval, did not
measure how far the filter sends the traveler, and resampled cases that share a session.

## Question

1. When the request names a group of types that includes the next place's type, as the keyword
   parser resolves a type name ("museum" gives several museum types), does the filter still find
   the actual next place better than soft weighting?
2. When the request names another type, how much worse does each setting find the actual next
   place, and at what share of such mismatched requests does the filter stop being better?
3. How much farther is the filter's first stop, compared with no request?

## Data

Gowalla test split. Cases whose next place is not in the history (revisits are never
recommended), whose last and next places have metadata, and that the model knows; no reach
filter, so next places beyond 40 km stay in. One case per session (the test split repeats each
session at every history length; a session is identified by its first check-in), and no session
that any earlier sample (E-B seeds 7 to 9, E-C seed 10, E-F seed 11, E-D1 seeds 12 and 13) drew
from. 1,000 cases, seed 14. Because each case is its own session, bootstrapping over cases is
bootstrapping over sessions.

## Requests

| ID | Request | What it tests |
|---|---|---|
| R1 | The next place's type (as E-C) | Replication with paired F - W0.8 |
| R2 | The keyword parser's resolution of the next place's type name: up to eight types sharing a word with it (`CategoryVocabulary.lexical`), the type itself included | A request that contains the answer without being it |
| R3 | A random other type with an unvisited place within 40 km, outside the R2 group | A request that is not where the traveler went |

R2 is analysed on cases where the group has at least two types; the share is reported.

## Settings

First stop, drive reach, travel cost on, novelty weight 0.1, as in E-C: F (filter, lambda 0.5),
W0.5 and W0.8 (no filter), and N (no request) as the reference for distance.

## Metrics

- Actual next place: MRR, HR@1 and HR@5 in each setting's ranked list (absent counts as a miss),
  with paired differences F - W0.5 and F - W0.8; 95% bootstrap intervals, 1,000 resamples.
- Request met: first stop in the R2 group; first stop of the R3 type.
- If a share p of requests are R3 and the rest R1, each setting's expected MRR is
  (1 - p) MRR(R1) + p MRR(R3) on these paired cases. The crossover p* is where F and W0.5 (and
  F and W0.8) meet, with a bootstrap interval.
- First-leg km of the first stop: median, and the share over 10 km, per setting and request.
- R1 reported both on all cases and on cases whose next place is within 40 km.

## Predictions

1. R1 replicates E-C: F - W0.5 MRR has an interval above 0; F - W0.8 has an interval that
   includes 0.
2. R2: F - W0.5 MRR stays above 0 but is smaller than in R1; F - W0.8 includes 0.
3. R3: the filter's MRR of the actual next place is at most 0.05 (its type is removed whenever a
   requested place is in reach), and W0.5's is at least 0.15. The crossover p* for F against
   W0.5 lies between 0.2 and 0.5.
4. On all cases, every setting's R1 MRR is lower than on the within-reach cases, and F - W0.5
   stays above 0.
5. Distance: under R3, the filter's median first leg is longer than with no request, and its
   share of first legs over 10 km is at least 5 points higher. Under R1, the filter's median
   first leg is within 1 km of W0.8's.

## What the paper can say, depending on the outcome

If 2 holds, the paper can keep a comparison in which the request is not the answer. If 3 holds,
the paper states the filter's advantage as conditional on the request naming where the traveler
goes, and reports p*.

## Results (run 2026-10-30)

The predictions above are left as written. Script: `experiments/ec2_request_not_answer.py`
(seed 14, 1,000 bootstrap resamples, MG-DSGAT on CPU, 6.3 minutes). 1,000 cases from 1,000
sessions; over 1,883 cases drawn, 480 came from sessions an earlier sample used, 19 from a
session already taken, 352 were revisits and 32 lacked metadata or were unknown to the model.
The next place lies beyond 40 km in 181 cases.

MRR of the actual next place, with paired differences (HR@1, HR@5 and the per-case rows are in
the run's JSON):

| Request | Cases | F | W0.5 | W0.8 | F - W0.5 | F - W0.8 |
|---|---|---|---|---|---|---|
| R1, next place within 40 km | 819 | 0.646 | 0.559 | 0.649 | +0.087 [+0.069, +0.104] | -0.004 [-0.018, +0.010] |
| R1, all cases | 1,000 | 0.532 | 0.482 | 0.557 | +0.050 [+0.034, +0.066] | -0.024 [-0.038, -0.010] |
| R2, group of 2+ types | 598 | 0.471 | 0.451 | 0.523 | +0.021 [-0.000, +0.042] | -0.052 [-0.072, -0.032] |
| R3, another type | 999 | 0.000 | 0.135 | 0.075 | -0.135 [-0.151, -0.119] | -0.075 [-0.083, -0.067] |

Request met at the first stop: R1 F 0.936, W0.5 0.713, W0.8 0.990 (all cases); R2 F 0.911,
W0.5 0.706, W0.8 0.993; R3 F 1.000, W0.5 0.387, W0.8 1.000. W0.8 meets more R1 requests than
the filter only by leaving reach: in the 64 cases with no place of the requested type within
40 km, it met 54 at a median first leg of 469 km, where the filter lets habit decide.

Mixing mismatched requests (R3) into R1: the filter stays ahead of W0.5 up to p* = 0.274
[0.193, 0.341] mismatched requests. Against W0.8 there is no crossover on all cases (p* is
negative: the filter is already behind at p = 0).

First leg of the first stop (median km; share over 10 km): with no request 0.60 (18.6%); R1 all
cases F 1.90 (22.5%), W0.5 0.76 (15.9%), W0.8 1.79 (22.8%); R3 F 6.75 (41.5%), W0.5 1.00
(10.9%), W0.8 5.31 (36.5%).

Against the predictions:

1. Held on the within-reach cases, which is E-C's population: F - W0.5 +0.087 replicates E-C's
   +0.082, and F - W0.8 includes 0. On all cases F - W0.8 is below 0 (-0.024): next places
   beyond reach count against the filter.
2. Failed. F - W0.5 shrinks to +0.021 with an interval touching 0, and F - W0.8 is below 0
   (-0.052). When the request is a group of types, the filter no longer finds the actual next
   place better than soft weighting, and is worse than lambda 0.8.
3. Partly held. The filter's MRR is 0.000 (at most 0.05 predicted) and p* = 0.274 lies in
   (0.2, 0.5), but W0.5's MRR is 0.135, below the predicted 0.15.
4. Held: every setting's R1 MRR is lower on all cases than within reach, and F - W0.5 stays
   above 0 (+0.050).
5. Held: under R3 the filter's median first leg is 6.75 km against 0.60 km with no request,
   and 41.5% of first legs exceed 10 km against 18.6% (+22.9 points). Under R1 its median is
   within 1 km of W0.8's (1.90 against 1.79 km).

What the paper can say: at the default weight, the filter does what was asked within reach every
time, where soft weighting does about seven times in ten for the next place's type and four in
ten for another type. It finds the place the user actually went to better than soft weighting
at the same weight only when the request names that place's exact type (+0.087 within reach,
+0.050 overall), not when it names a group of types (+0.021, interval touching 0), and never
better than soft weighting at lambda 0.8. The MRR gain is therefore a property of exact-type
requests, not evidence that the filter recovers where travelers go. Honouring a request habit
does not support costs distance: a median first leg of 6.75 km instead of 0.60 km. Soft weighting
at lambda 0.8 meets as many requests only by sending the traveler past reach (median 469 km when
nothing fits within 40 km).

## Rerun after E-G2's reach limit (2026-10-30)

E-G2 made an unmet request keep its stops within reach (on by default). That changes the filter's
ranking only in cases where nothing of the requested types is within 40 km, so E-C2 was rerun
with the new default (same seed and cases; 6.1 minutes). Changed numbers:

| | Before | After |
|---|---|---|
| R1 all cases, F - W0.5 MRR | +0.050 [+0.034, +0.066] | +0.046 [+0.029, +0.062] |
| R1 all cases, F - W0.8 MRR | -0.024 [-0.038, -0.010] | -0.028 [-0.043, -0.013] |
| R2, F - W0.5 MRR | +0.021 [-0.000, +0.042] | +0.016 [-0.007, +0.038] |
| R2, F - W0.8 MRR | -0.052 [-0.072, -0.032] | -0.057 [-0.078, -0.037] |
| Crossover p*, F against W0.5 | 0.274 [0.193, 0.341] | 0.260 [0.176, 0.331] |

Unchanged: R1 within 40 km (+0.087, -0.004), all of R3, and the first-leg distances (6.75 km
against 0.60 km). The conclusions stand; the paper uses the numbers after the change.
