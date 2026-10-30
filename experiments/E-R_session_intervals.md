# E-R: E-B and E-F with intervals over sessions

Written 2026-10-30, before the reanalysis was run. The predictions are hypotheses; results are
reported against them as they come out.

## Why

The Gowalla test split repeats each session at every history length, so two cases in one sample
can come from the same session. E-B and E-F resampled cases, which treats such cases as
independent and can make intervals too narrow. Their runs also kept only summaries, so the paired
HR@1 and HR@5 differences in E-B, and a paired test and median for E-F's hop lengths (E-F
prediction 3, "not established"), were never computed.

## What is rerun

The same code, seeds and samples, now also writing each case's ranks and route hops:

- **E-B confirmation:** seed 9, excluding the seed 7 and 8 samples, rankings M4 and M5 plus the
  baselines (the numbers in the paper's Table 1).
- **E-F:** seed 11, 2,000 cases.

A session is identified by its first check-in. Intervals resample sessions (all of a session's
cases together), 1,000 resamples.

## Predictions

1. Every point estimate equals the reported one (the runs are deterministic).
2. Session intervals are at most 15% wider than the case intervals.
3. Every interval that excluded 0 still does, including E-F's HR@10 P - B (+0.005
   [+0.002, +0.009]).
4. E-B: M5 - M4 on HR@1 has an interval below 0 (the ablation is better at the first place);
   on HR@5 and MRR the intervals include 0.
5. E-F: route costs shorten hops: the paired difference in a route's mean hop (R - P) has an
   interval below 0, and the median hop is lower with route costs.

## Results (run 2026-10-30)

The predictions above are left as written. Scripts: the two reruns with `--rows-out`, then
`experiments/er_session_intervals.py` (1,000 resamples each way).

The samples hardly share sessions: E-B's 2,000 cases come from 1,939 sessions and E-F's from
1,942. Every point estimate matched the reported one to the last digit. Session intervals were
a median 0.99 times as wide as case intervals (at most 1.09 times).

New paired differences for E-B (Table 1's sample), session intervals:

| Difference | HR@1 | HR@5 | MRR |
|---|---|---|---|
| M5 - M1 nearest | +0.030 [+0.009, +0.052] | +0.042 [+0.023, +0.060] | +0.034 [+0.019, +0.049] |
| M5 - M2 most check-ins | +0.121 [+0.097, +0.149] | +0.090 [+0.071, +0.111] | +0.104 [+0.085, +0.123] |
| M5 - M4 ablation | -0.022 [-0.038, -0.007] | +0.013 [-0.001, +0.031] | -0.007 [-0.018, +0.004] |

E-F with session intervals: HR@10 P - B +0.005 [+0.001, +0.009] and R - P +0.009 [+0.003,
+0.017]; routes with a repeated category, R - P -0.149 [-0.164, -0.135]. Hops: the median hop is
0.92 km without route costs and 0.51 km with them; the share of hops over 2 km falls from 40.6%
to 31.9%; a route's mean hop changes by -14.8 km [-22.3, -6.6] on average. Most routes are the
same either way (the median paired difference is 0): route costs shorten 28.9% of routes and
lengthen 7.2%.

Against the predictions:

1. Held: every point estimate is identical.
2. Held: session intervals are at most 9% wider.
3. Held: every interval that excluded 0 still does; HR@10 P - B is [+0.001, +0.009].
4. Held: M5 - M4 is below 0 on HR@1 and includes 0 on HR@5 and MRR. The ablation puts the
   actual next place first more often; the default puts it in the top five slightly more often.
5. Held: route costs shorten hops (median 0.92 to 0.51 km; mean per route -14.8 km with an
   interval below 0). This settles E-F prediction 3.

What the paper can say: the intervals stand as reported; resampling sessions changes them by
at most a few thousandths. The Table 1 sentence about the ablation can name the trade-off: it is
better at HR@1 (-0.022 for the default) and no worse elsewhere. Route costs halve the median hop.
