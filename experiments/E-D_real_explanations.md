# E-D: What does the verifier do to explanations Claude actually writes?

Written 2026-10-30, before any Claude call for it was made. The predictions are hypotheses;
results are reported against them as they come out. This is the automatic part of E-D; the
human part (two annotators judging the kept and removed sentences, Cohen's kappa) follows on
the sentences this run produces.

## Why

E-D1 measured the verifier on templated sentences with planted errors. Claude's own sentences
differ in wording, citations and claims, and the only live route so far (under the earlier
verifier) had 2 of 4 sentences removed, for reasons that were not saved.

## Data

50 routes, seed 18, one per session, from sessions no earlier sample used (seeds 7 to 17).
Evidence built offline as `/route` builds it, then sent to Claude with the app's own prompt and
settings (`grounded_explainer.request_explanation`, claude-opus-5-5, effort medium). Requests:
20 for the next place's type by car, 15 for another type within 40 km by car, 10 for the next
place's type on foot (some cannot be met within 2 km), 5 with no type ("somewhere new"). The
Austin route of the paper's Fig. 1 ("a museum, nothing with coffee", parsed by Claude) is run
once more and reported apart.

## Metrics

- Sentences per route; share supported, not checkable and removed by `verifier/2`, with the
  reason for each removal. The same sentences are also run through the earlier check
  (verifier/1) offline, at no extra calls.
- Share of stops left with at least one shown sentence.
- Whether the explanation mentions what the evidence most needs said: the request was met (a
  requested type), or could not be met within reach (`in_range` 0).
- Tokens and latency per call.

## Predictions

1. `verifier/2` removes at most 15% of Claude's sentences.
2. At least 60% of sentences are supported (checked), not merely not checkable.
3. At least 95% of stops keep at least one shown sentence.
4. The earlier check removes at least 5 points more sentences than `verifier/2`.
5. When a stop's request could not be met within reach, the explanation says so in at least 80%
   of such stops.
6. Explanation latency: p50 at most 15 s, p95 at most 30 s.

## Trial (5 calls, 2026-10-30)

Before the batch, `experiments/claude_runs.py --mode trial --max-calls 5` made five calls to
measure tokens and cost: two parses ("A museum, nothing with coffee" and "博物館に行きたい") and
three explanations (the Fig. 1 Austin route and the first two routes of seed 18). All five
succeeded on claude-opus-5-5 with no fallback; the trial cost $0.10.

- Explanations took 5.2 to 7.2 s, about 2,700 uncached input and 570 output tokens each, plus a
  1,417-token cached system prompt. Parses took 2.1 to 3.3 s, with a 3,870-token cached prompt.
- Claude read "nothing with coffee" as avoiding eight coffee types, Starbucks among them, and the
  Japanese request as the six museum types.
- Of 12 explanation sentences, `verifier/2` removed 4 and the earlier check 1. Read by hand, all
  four removals were wrong: three summary sentences counted the stops ("three museums", "three
  Karaoke places"), a number no cited field holds, and one used "usually" for the traveler's
  movement pattern ("fits the way you usually move between places"), which the frequency rule
  read as a claim about visiting that type. The Fig. 1 route kept 2 of 4 sentences.

These three routes are therefore development data: the batch's 50 routes are drawn after them
(seed 18, skipping its first two cases), and any change to the verifier made because of them is
recorded here before the batch runs.

## Change before the batch: verifier/2.1

Two rules changed, both because of the trial, before any batch call:

- The number of stops is a fact of the route, so a count such as "three museums" may match it.
- A frequency claim must pair a frequency word with a visiting verb ("you often go to",
  "usually visit", "favourite"); "the way you usually move" is no longer read as a claim about
  visiting the stop's type.

With verifier/2.1 all 12 trial sentences are supported. E-D1's planted-error test, rerun offline
on the same development and held-out routes, is unchanged in substance: every kind of error is
caught in at least 99.6% of sentences and no true sentence other than the uncited-window family
is removed (see E-D1). The batch reports `verifier/2.1`, and the earlier check as before.

## Results (run 2026-10-30)

The predictions above are left as written. Script: `experiments/claude_runs.py --mode batch`
(claude-opus-5-5; 54 explanation calls for E-D and the demo travelers, no errors or fallbacks).
50 routes, 200 sentences (one summary and one per stop each).

| | verifier/2.1 | earlier check (verifier/1) |
|---|---|---|
| Supported | 94.0% | 82.5% |
| Not checkable | 0.0% | 1.0% |
| Removed | 6.0% (12) | 16.5% (33) |

Removal share by request: next type by car 5.0%, another type by car 6.7%, next type on foot
7.5%, no type 5.0%. Stops left with at least one shown sentence: 97.3%. Of the 43 stops whose
request could not be met within reach, the kept text says so (a "no ... within/nearby" phrase
or "habits") at 88.4% of them; this is a word match, to be confirmed by the annotators.
Explanation latency: p50 5.2 s, p95 7.3 s.

Against the predictions:

1. Held: 6.0% removed (at most 15%).
2. Held: 94.0% supported (at least 60%).
3. Held: 97.3% of stops keep a sentence (at least 95%).
4. Held: the earlier check removed 10.5 points more (at least 5).
5. Held by the word match: 88.4% (at least 80%).
6. Held: p50 5.2 s and p95 7.3 s (at most 15 and 30 s).

Reading the 12 removed sentences by hand (an author's reading, not the annotators'), most look
true and were removed by three rules that real sentences trip over:

- **Counting some of the stops** (6): "two Arenas you asked for, then a Convention Center",
  "two more stops". The count matches the stops of one type, or the stops after the first, not
  the route's stop count.
- **"Usually" for the order of visits** (3): "fits the order of places you usually go". With
  verifier/2.1 a visiting verb makes it a frequency claim, but the object here is "places" in
  general, not the stop's type.
- **New place vs new type** (3): "you have not been to this place before" is about the place
  (`visited_this_poi`, always false), but the rule checks the type's visit count.

One removal looks right: in the demo route "A museum within 2 km on foot", "best matches your
past sequence" claims a comparison the evidence does not show. Whether the 188 kept sentences
contain unsupported claims the verifier missed is for the annotators; the sentences, their
citations and the cited values are exported for them without the verdicts.

What follows: the three patterns can be fixed (count stops per named type and after the first;
check frequency and novelty only within the clause that names a type; read "this place" and
"here" against `visited_this_poi`), but these 50 routes are now development data, so a fixed
verifier needs fresh routes to be measured on.

## E-D2: verifier/2.2 on fresh routes (design, written 2026-10-30 before the change)

The 50 routes above are now development data. verifier/2.2 changes the three rules they showed,
using only those routes:

- A count may also match the number of stops of a type the sentence names ("two Arenas") and the
  stops after the first ("two more stops").
- "Often" and "new to you" are checked against the types named in their own clause. A frequency
  word in a clause that names no type ("the order of places you usually go") is not a claim
  about a type and is not checked.
- "You have not been to this place" and "haven't been here" are about the place, and are
  checked against `visited_this_poi`, not the type's visits.

Validation: 50 fresh routes, seed 21, one per session, from sessions no earlier sample used
(seeds 7 to 18, all 52 of seed 18's cases included), with E-D's request mix (20 next type by
car, 15 another type by car, 10 next type on foot, 5 no type). One Claude explanation per route,
checked by verifier/2.2; verifier/2.1 and the earlier check are run on the same sentences
offline. Every removed sentence is read by hand (an author's reading).

Predictions:

1. On the development routes, verifier/2.2 keeps 11 of the 12 sentences verifier/2.1 removed
   and still removes "best matches your past sequence"; no sentence verifier/2.1 kept is
   removed.
2. E-D1's planted errors are caught as before (every kind at least 99%, no true sentence
   removed).
3. On the fresh routes, verifier/2.2 removes at most 3% of sentences, fewer than verifier/2.1.
4. At least half of verifier/2.2's removals on the fresh routes read as unsupported.
5. At least 98% of stops keep a shown sentence.

## E-D2 results (run 2026-10-30)

The predictions above are left as written. Script: `experiments/claude_runs.py --mode validate`
(50 explanation calls, no errors; $1.05). verifier/2.1 is kept in `experiments/verifier_v2_1.py`;
rebuilt from the committed verifier/2 and the two 2.1 changes, it reproduces all 216 verdicts of
the E-D batch. 50 fresh routes, 201 sentences:

| | verifier/2.2 | verifier/2.1 | verifier/1 |
|---|---|---|---|
| Supported | 97.5% | 94.0% | 85.6% |
| Not checkable | 0.5% | 0.5% | 2.0% |
| Removed | 2.0% (4) | 5.5% (11) | 12.4% (25) |

Stops left with at least one shown sentence: 97.3%.

Against the predictions:

1. Held in substance: on the development routes verifier/2.2 keeps all 12 sentences verifier/2.1
   removed, removes no sentence it kept, and still removes "best matches your past sequence".
   The prediction expected that sentence among the 12, but it came from a demo route.
2. Held: E-D1 is unchanged (every planted kind at least 99.6%, no true sentence removed apart
   from the uncited-window family, as designed).
3. Held: 2.0% removed (at most 3%), against 5.5% for verifier/2.1.
4. Failed: none of the four removals reads as unsupported. All four say the stop is new, meaning
   the place, while the traveler has visited its type: "new to you though you have visited Light
   Rail 3 times", "somewhere you have not been before", "new to you ... and 4 recent train station
   visits", "a spot you have not been to". Each cites `visited_this_poi`, which is false, so each
   is true about the place; verifier/2.2 reads "this place" and "here" as the place but not
   "somewhere", "a spot" or a bare "new to you".
5. Failed: 97.3% of stops keep a sentence (at least 98%); the four removals each emptied a stop.

Among the 197 kept sentences, 26 use words such as "only", "usually" or "all". The two "only"
claims ("the only one available in range", "the only remaining Terminal option nearby") were
checked by hand and are true (`in_range` is 1). Whether any kept sentence is unsupported is for
the annotators.

What follows: one pattern remains, place-level novelty in other words. Reading "new to you" and
"not been" as being about the place whenever the sentence cites `visited_this_poi` would keep all
four, but these routes are now development data as well. Rather than tune again, the remaining
question, how often the verifier misses or wrongly removes a sentence, is left to the annotators,
on E-D's 200 sentences and, if they have time, E-D2's 201.
