# E-F: Without a request, does the pipeline keep the backbone's accuracy, and do route costs stop repetition?

Written 2026-10-29, before the evaluation code for it was written or run. The predictions are
hypotheses; results are reported against them as they come out.

## Question

With no request, WhereNext ranks by the sequence model plus spatial and semantic reranking,
and the route planner adds a travel cost and a repeat cost at each step. Does that keep the
backbone's accuracy at finding the next place, and does it make three-stop routes less
repetitive?

## Data

Gowalla test split, 2,000 cases (seed 11) whose next place is not in the history and is known
to the model. The backbone never recommends a visited place, so revisits are left out; their
share is reported.

## Rankings compared

| ID | Ranking |
|---|---|
| B | Backbone only: the sequence model's own top candidates |
| P | Pipeline: backbone plus spatial and semantic reranking, no route costs (what `/genpoi` returns) |
| R | Pipeline plus route costs (travel and repeat), the `/route` default |

## Metrics

- Accuracy at the first stop: HR@1, HR@5, HR@10 and NDCG@10 of the actual next place, with 95%
  bootstrap intervals and paired differences P - B and R - P.
- Three-stop routes built greedily (each stop appended to the history before the next): the
  share of routes with a repeated category, the share of stops in the same category as the last
  visit, and the mean hop length in km. Compared for P and R.

## Predictions

1. P - B and R - P on HR@10 both have intervals that include 0: reranking and route costs do not
   change accuracy measurably.
2. Route costs at least halve the share of routes with a repeated category (R against P).
3. Route costs shorten the mean hop.

## Results (run 2026-10-29)

The predictions above are left as written. Script: `experiments/offline_suite.py --experiment F`
(seed 11, 1,000 bootstrap resamples, MG-DSGAT on CPU, 5.2 minutes). 2,000 cases; 643 revisits
and 49 others were excluded along the way.

| Ranking | HR@1 | HR@5 | HR@10 | NDCG@10 |
|---|---|---|---|---|
| B backbone | 0.099 [0.086, 0.113] | 0.231 [0.212, 0.249] | 0.301 [0.281, 0.322] | 0.190 [0.176, 0.204] |
| P pipeline | 0.103 [0.090, 0.117] | 0.237 [0.218, 0.257] | 0.306 [0.285, 0.325] | 0.194 [0.180, 0.209] |
| R pipeline and route costs | 0.108 [0.096, 0.121] | 0.242 [0.223, 0.262] | 0.316 [0.294, 0.336] | 0.200 [0.186, 0.214] |

Paired HR@10 differences: P - B +0.005 [+0.002, +0.009]; R - P +0.009 [+0.004, +0.016].

| Three-stop routes | Routes with a repeated category | Stops of the last visit's category | Mean hop (km) |
|---|---|---|---|
| P without route costs | 0.252 [0.234, 0.270] | 0.117 [0.108, 0.126] | 83.0 [64.8, 104.6] |
| R with route costs | 0.102 [0.089, 0.115] | 0.092 [0.085, 0.100] | 68.2 [51.0, 88.7] |

Against the predictions:

1. Failed, in the favourable direction: reranking and route costs did change accuracy, upward.
   HR@10 rose from 0.301 to 0.316, and both paired intervals exclude 0.
2. Held: routes with a repeated category fell from 25.2% to 10.2%.
3. Not established: the mean hop is lower (68.2 against 83.0 km), but the intervals overlap and
   no paired difference was computed. Hop lengths are heavily skewed (a few very long hops pull
   the mean), so a median and a paired test would be needed to make the claim.
