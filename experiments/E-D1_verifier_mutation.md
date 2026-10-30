# E-D1: Does the verifier remove false sentences and keep true ones?

Written 2026-10-30, before the test code was written or run. The predictions are hypotheses;
results are reported against them as they come out. This is the automatic part of E-D; the
human part (annotators rating real explanations) is separate.

## Question

The verifier is meant to remove every explanation sentence the route evidence does not support
and to keep the ones it does. With sentences whose truth is known by construction, how often
does it remove a false sentence (catch rate), and how often does it remove a true one (false
removal)? Which kinds of error does it miss?

## Why now

On the live Austin route, 2 of 4 Claude sentences were removed and the reasons were not saved.
A probe with 10 hand-written sentences found 8 wrong verdicts: true sentences removed for
metres, the word "highly" and naming an avoided type, and false sentences kept when a number
matched another cited value, a signal was misnamed, or the claim was a superlative or praise.

## Data

Route evidence built offline exactly as `/route` builds it (the database lookup of the
history is replaced by the test case's history). Gowalla test split, `new_place_cases`, three
stops per route, MG-DSGAT on CPU, no external API.

- **Development routes:** 150 cases, seed 12. The fix is written while looking only at these.
- **Held-out routes:** 150 cases, seed 13, excluding the seed-12 cases. Run once with the old
  verifier before the fix and once with the fixed one after; the paper reports these.

Each route has a request: want the next place's type; avoid the history's most frequent type
when it differs; travel mode cycles walk, transit, drive by case, so some walk routes have no
requested place in reach (`intent.in_range` = 0).

## Sentences

Built from each route's evidence, following the explainer's rules (only distances and visit
counts as numbers, place types spelled as in the evidence, every sentence cites the paths it
uses). `i` is the stop index, `cat` the stop's type, `d` its leg in km, `n` and `w` its
same-type visits and the history window.

**True, as the explainer is told to write (T).**
T1 `It is {d:.2f} km from the previous stop.` T2 `It is a {cat}, one of the place types you
asked for.` (requested stops) T3 `You visited {cat} places {n} times in your last {w} visits.`,
or for n = 0 `A {cat} is new to you: none of your last {w} visits were one.` T4 `No place of
the requested types is within {r} km of the previous stop, so this stop follows your habits.`
(in_range = 0) T5 `It is a {cat}, not a {avoid}, as you asked.` (when avoiding) T6 summary
`Your last visit was a {type}.` T7 summary `The route starts {d:.2f} km from your last visit.`

**True, phrased against the rules or under-cited (P).** P1 metres `{1000d:.0f} m`; P2 `about
{d:.1f} km`; P3 lowercase plural `one of the {cat}s you asked for`; P4 ordinal `The 2nd stop is
{d:.2f} km from the one before.`; P5 number word `{n as a word} times` (2 to 12); P6 `{n} of
your last {w} visits` citing only n; P7 `It is a {cat} instead of another {avoid}.` citing only
the stop's type; P8 `It is a {cat}, new to you.` (n = 0) citing only the stop's type.

**False by construction (M),** each a T sentence changed in one way:
M1 distance off by at least 0.5 km (and at least doubled); M2 visit count n + 2; M3 a type that
appears nowhere in the route's evidence; M4a an absent attribute the verifier lists ("highly
rated"); M4b one it does not list ("popular with locals", "the best {cat} in town", "a lively
spot"); M5 a citation to a path that does not exist; M6 another stop's distance, citing that
stop; M7 `It is not a {cat}.`; M8 km written as miles; M9 a visit count equal to some other
integer in the stop's record (rank, pool size), citing the whole record; M10 `It is the closest
{cat} to your last stop.` (nothing in the evidence shows this); M11 `This stop is a {avoid}.`
citing the avoid list; M12 `You often visit {cat} places.` when n = 0; M13 `A {cat} is new to
you.` when n >= 1.

## Metrics

Per family: the share of sentences removed (catch rate for M, false-removal rate for T and P)
and, for T and P, the share kept as checked rather than not checkable. Counts, not intervals:
every sentence is deterministic given its route.

## Predictions for the current verifier (verifier/1)

1. T: false removal at most 1%, and every T sentence checked.
2. P: P1 and P4 removed in at least 90% of cases; P6 and P7 removed in most cases; P2, P3, P5 and
   P8 removed in at most 5%; P3 kept as not checkable.
3. M caught in at least 90% of cases: M1, M3, M4a, M5. M2 mostly caught, except when n + 2
   equals the cited window w. Caught in at most 10%: M4b, M6, M7, M8, M9, M10, M11, M12, M13.
   So the verifier catches about 5 of the 14 kinds of error.

## Fix and decision rule (fixed now)

A fixed verifier (verifier/2) is written against the development routes only. It is accepted if,
on the development routes, every M family is caught in at least 90% of cases and T false
removal stays at most 1%, with P1 to P5 and P8 (true, only phrased differently) removed in at
most 5%. Under-cited sentences that name an uncited number or type (P6, P7) may stay removed:
the explainer is told to cite what it states. The held-out routes are then run once with each
verifier and reported as they come out, with no further changes.

## What this does not show

The sentences are templated, so the catch rates hold for these kinds of error, not for the mix
Claude actually writes. That needs real explanations (Claude calls) and human labels (E-D).

## Results (run 2026-10-30)

The predictions above are left as written. Script: `experiments/ed1_verifier_mutation.py`
(MG-DSGAT on CPU, no external API). Building the evidence first hit a crash in the backend: the
request similarity came out as 1.0000001 in float32, above the evidence schema's bound of 1, so
`/route` would fail for that request. `steering.py` now clamps it to [-1, 1]; nothing else in
the ranking changed.

Held-out routes (seed 13, 150 routes), share of sentences removed:

| Family | Sentences | verifier/1 | verifier/2 | verifier/2 not checkable |
|---|---|---|---|---|
| T1 to T7 (true, as instructed) | 2,028 | 0.0% | 0.0% | 0.0% |
| P1 metres | 447 | 100.0% | 0.0% | 0.0% |
| P2 rounded km | 447 | 0.0% | 0.0% | 0.0% |
| P3 lowercase plural | 299 | 0.7% | 0.0% | 60.5% |
| P4 ordinal | 447 | 90.6% | 0.0% | 0.0% |
| P5 number word | 104 | 0.0% | 0.0% | 0.0% |
| P6 window not cited | 184 | 100.0% | 100.0% | 0.0% |
| P7 avoided type not cited | 384 | 100.0% | 0.0% | 0.0% |
| P8 "new to you" | 236 | 0.0% | 0.0% | 0.0% |
| M1 wrong distance | 447 | 100.0% | 100.0% | |
| M2 wrong visit count | 447 | 78.5% | 100.0% | |
| M3 type not on the route | 447 | 100.0% | 100.0% | |
| M4a "highly rated" | 447 | 100.0% | 100.0% | |
| M4b praise not listed in v1 | 447 | 0.0% | 100.0% | |
| M5 path that does not exist | 447 | 100.0% | 100.0% | |
| M6 another stop's distance | 447 | 0.0% | 100.0% | |
| M7 "It is not a {cat}" | 447 | 0.0% | 100.0% | |
| M8 km written as miles | 445 | 0.0% | 99.6% | |
| M9 count from a whole-record citation | 332 | 0.0% | 100.0% | |
| M10 "the closest" | 447 | 0.0% | 100.0% | |
| M11 the stop called the avoided type | 384 | 0.0% | 100.0% | |
| M12 false "often" | 236 | 0.0% | 100.0% | |
| M13 false "new to you" | 211 | 0.0% | 100.0% | |

Pooled over the 14 kinds of error (5,631 false sentences), verifier/1 removed 38.0% and
verifier/2 99.96%. Of the 4,392 true sentences other than P6, verifier/1 removed 1,086 (24.7%)
and verifier/2 none. The development routes (seed 12) gave the same picture: 38.2% and 99.96%
of false sentences, 0 true sentences removed by verifier/2.

Against the predictions for verifier/1:

1. Held: no T sentence removed, all checked.
2. Held: P1 100% and P4 90.6% removed; P6 and P7 100%; P2, P5 and P8 0%; P3 0.7% removed and
   99.3% not checkable.
3. Held: M1, M3, M4a and M5 100%; M2 78.5% (missed when n + 2 equals the cited window); the
   other nine 0%. verifier/1 reliably caught 4 of the 14 kinds of error, and a fifth partly.

Decision: verifier/2 met the rule on the development routes (every M family at least 99.6%,
no T or P1 to P5, P8 sentence removed) and was run once on the held-out routes. Two further
changes were made before that run, after a reviewer's 16-sentence hand probe exposed them: a
share in % must now be a share of visits (it matched a weight of 0.5 as "50%"), and citing a
whole stop record no longer vouches for the numbers inside it. On that probe, verifier/1 gave
13 wrong verdicts of 16 (2 true sentences removed, 11 false ones kept), the first verifier/2
gave 2 and the final one 0.

What verifier/2 changes: numbers are read with their unit (km, m, miles, %, "times", "visits")
against fields of that kind; a stop's sentence may not take numbers from another stop; a type
may be named if it is cited or appears in the route's history, request or stops, but a stop
may not be called a type it is not, or not be called its own type; "often" and "new to you"
must agree with the visit counts; ordinals and number words are read; the list of absent
attributes grows (popular, locals, lively, ...) and comparisons such as "the closest" are
removed; place-type names are taken out before those word lists apply ("Best Buy" is a type).

Remaining misses and limits:

- The two M8 misses are 0.01 and 0.02 miles for legs under 0.04 km, which are true at the
  precision shown; the mutation, not the verifier, is wrong there.
- A bare decimal with no unit is read against any cited value, so a quoted score ("habit added
  0.11") can match a distance. The explainer is told not to quote scores; the verifier does not
  enforce it.
- One-word types in lower case ("museums") are not read, so such sentences are often not
  checkable (P3: 60.5%). Matching them in any case would collide with words such as "home" or
  "target", which are also types.
- A type from the history named in a wrong relation ("your last visit was a Bakery" when the
  Bakery was earlier) passes. The word lists (praise, comparisons, "often") are finite; words
  outside them pass, and "best" in "best matches your request" would be removed.
- All of this is on templated sentences; what share of Claude's real sentences each rule
  affects is for E-D.

## Rerun with verifier/2.1 (2026-10-30)

Two rules changed after E-D's five-call trial showed true Claude sentences being removed (see
E-D): a stop count may match the route's number of stops, and a frequency claim needs a visiting
verb. Rerun on the same seeds; the routes differ slightly from the first run because E-G2 has
since kept unmet requests within reach, so the sentence counts differ a little. Held-out routes:
all 14 kinds of error caught in at least 99.6% of sentences (M8 miles 99.6%, the rest 100%), and
no T, P1 to P5, P7 or P8 sentence removed; P6 (an uncited window) is still removed, as designed.
The development routes give the same picture.
