# E-A2: How well does Claude read requests, compared with the keyword parser?

Written 2026-10-30, before any Claude call for it was made. The predictions are hypotheses;
results are reported against them as they come out. Hand-written requests from people other
than the authors remain the last part of E-A.

## Data

200 requests from E-A1's constructed sets, whose meaning is known by construction: 100 from the
development set and 100 from the held-out set, drawn per family in proportion to its size
(seed 19), every family at least 3. Plus three probes outside E-A1: "a museum, nothing with
coffee", "no coffee please" and "something new on foot". Parsed by the app's own Claude parser
(`IntentParser.parse`, claude-opus-5-5, effort low) and scored with E-A1's scorer; the keyword
parser (v2) reads the same requests offline for comparison.

## Metrics

Per family: share read right, share with a type in the wrong list, share dropped silently;
the number of wanted types for a one-type request; for the coffee probes, whether Starbucks and
the other coffee chains are avoided. Tokens and latency per call; how often the keyword parser
had to take over (API failure).

## Predictions

1. Claude reads at least 90% of all requests right, against about 94% for the keyword parser
   on the same requests (it was fitted to the development set).
2. Claude reads other negations, typos and other languages right in at least 90% each.
3. Claude reads at least 90% of the held-out-only phrasings that the keyword parser misses
   ("at most", "take the tram", "I haven't tried", "a nice view").
4. For "nothing with coffee", Claude avoids Starbucks.
5. Parse latency: p50 at most 8 s, p95 at most 15 s; no fallback to the keyword parser.

## Results (run 2026-10-30)

The predictions above are left as written. Script: `experiments/claude_runs.py --mode batch`
(207 parse calls: 200 requests, 3 probes and the 4 demo requests; no errors, no fallback to the
keyword parser).

| | Claude | Keyword parser (v2) |
|---|---|---|
| All 200 requests read right | 99.5% | 97.0% |
| Held-out-only phrasings (23) | 95.7% | 78.3% |
| Distance (9) | 100% | 77.8% |
| Explore (9) | 100% | 77.8% |
| Other language (6) | 100% | 83.3% |
| Unsupported (9) | 88.9% | 88.9% |
| Wanted types for a one-type request (mean) | 1.13 | about 2.5 |

Every other family (want, plural, both negation families, combined, two types, typo, mode,
strength) was read right by both. Claude's one miss: "a Toys & Games with a nice view" wanted
Scenic Lookout instead of listing the view as unsupported. Probes: "a museum, nothing with
coffee" and "no coffee please" both avoided eight and seven coffee types including Starbucks,
Tim Hortons and Seattle's Best; "something new on foot" gave walk and new. Parse latency: p50
1.7 s, p95 2.7 s.

Against the predictions:

1. Held: Claude 99.5% (at least 90%). The keyword parser read 97.0%, more than the predicted
   about 94%.
2. Held: other negations, typos and other languages all 100%.
3. Held: 95.7% of held-out-only phrasings (at least 90%).
4. Held: Starbucks is avoided.
5. Held: p50 1.7 s, p95 2.7 s, no fallback.

Caveat: these requests are E-A1's templates, written by an author; they test the parser on
known structures. Requests written by other people remain the last part of E-A.
