# E-A1: How well does the keyword parser read requests?

Written 2026-10-30, before the test code was written or run. The predictions are hypotheses;
results are reported against them as they come out. This is the offline half of E-A: the
keyword parser that takes over without an API key or when the Claude call fails. The Claude
parser and hand-written requests are E-A proper.

## Question

When the keyword parser reads a request whose meaning is known by construction, how often does
it put the named place type in the right list (wanted or avoided), read the travel mode, the
maximum hop, strength, novelty and unsupported asks correctly, and how often does it drop a
request silently (no type found and nothing reported as unresolved)?

## Requests

Built from templates over the dataset's place types (stripped, at most three words). Types are
split into a development half and a held-out half by a hash of the name; 60 types are drawn
from each half (seed 16). Each family has development templates, and the held-out set adds one
template per family that the development set never uses.

| Family | Development templates | Held-out adds | Gold |
|---|---|---|---|
| W want | "a {t}", "take me to a {t}", "I'd like to visit a {t}" | "show me a {t} please" | t wanted |
| P plural | "{t lower}s around here" | | t wanted |
| N1 negation the parser lists | "no {t}", "avoid {t}", "without a {t}" | "skip the {t}" | t avoided |
| N2 other negation | "I don't want a {t}", "anything but a {t}", "not in the mood for a {t}" | "I'd rather not go to a {t}" | t avoided |
| C combined | "a {a}, no {b}", "a {a} but not a {b}" | "{a} please, but skip {b}" | a wanted, b avoided |
| M two types | "a {a} and then a {b}" | "first a {a}, after that a {b}" | a and b wanted |
| T typo | "a {t with two adjacent letters swapped in its longest word}" | | t wanted, or reported unresolved |
| L other language | fixed translations for 10 types, half in each set | | t wanted, or reported unresolved |
| Mode | "a {t} on foot", "walk to a {t}", "a {t} by car", "a {t} by bus", "a {t} by subway" | "take the tram to a {t}" | walk / drive / transit |
| Distance | "a {t} within 2 km", "within 3 miles", "less than 500 m away", "under 1 km" | "at most 2 kilometers away" | max hop 2 / 4.83 / 0.5 / 1 / 2 km |
| Strength | firm: "I must go to a {t}", "only a {t}"; soft: "maybe a {t}" | firm: "it has to be a {t}" | firm / soft |
| Explore | new: "somewhere new, a {t}", "a {t} I've never been to"; familiar: "my usual {t}" | new: "a {t} I haven't tried" | new / familiar |
| Unsupported | "a cheap {t}", "a {t} that is open late", "a quiet {t}" | "a {t} with a nice view" | at least one unsupported ask |

## Metrics

Per family: the share of requests read right (the gold type in the right list; for C and M both
parts; for flags the gold value; distances within 5%), the share with the type in the wrong list
(polarity error), and the share dropped silently. Also the mean number of wanted types for a
one-type request.

## Predictions for the current parser

1. W and P read right in at least 95%.
2. N1 at least 90% avoided, polarity errors at most 5%.
3. N2 at most 35% avoided; at least 30% have the type wanted instead; at least 20% are dropped
   silently.
4. C and M at least 85% right.
5. T at most 25% right, at least 60% dropped silently. L at most 15% right, at least 70% dropped
   silently.
6. Mode at most 70% right ("on foot" and "subway" are not read). Distance at most 50% right
   (only "within N km/miles" is read).
7. Strength at least 80%, explore at least 70%, unsupported at least 70% right, the held-out
   "nice view" excepted.

## Fixes and decision rule (fixed now)

Changes to the keyword parser are written against the development requests only. They are kept
if no development family drops by more than 2 points and N2, T, L (silent drops), mode and
distance improve. The held-out requests are run once with the current parser before any change
and once with the changed one, and reported as they come out. The parser cannot translate; for
other languages the aim is only that nothing is dropped silently.

## Results (run 2026-10-30)

The predictions above are left as written. Script: `experiments/ea1_keyword_parser.py` (seed 16,
60 types per set; 1,125 development and 1,425 held-out requests). Share read right, held-out
set, before (v1) and after (v2) the changes; the share dropped silently is in brackets:

| Family | Held-out v1 | Held-out v2 | Development v1 | Development v2 |
|---|---|---|---|---|
| W want | 98.3% (1.7%) | 100.0% (0%) | 98.3% | 100.0% |
| P plural | 98.0% | 98.0% | 98.0% | 98.0% |
| N1 negation the parser lists | 98.3% | 100.0% | 98.3% | 100.0% |
| N2 other negation | 22.5% (28.3%; 49.2% wanted instead) | 100.0% (0%) | 0.0% (34.4%; 65.6% wanted) | 100.0% |
| C combined | 96.7% | 100.0% | 96.7% | 100.0% |
| M two types | 96.7% | 100.0% | 96.7% | 100.0% |
| T typo | 57.1% (40.8%) | 98.0% (0%) | 51.0% (49.0%) | 98.0% |
| L other language | 0% (100%) | 100% (0%), 5 requests | 0% (100%) | 80% (0%), 5 requests |
| Mode | 55.0% | 90.0% | 58.3% | 98.3% |
| Distance | 26.7% | 78.3% | 55.0% | 100.0% |
| Strength | 98.3% | 100.0% | 98.3% | 100.0% |
| Explore | 73.3% | 73.3% | 100.0% | 100.0% |
| Unsupported | 83.3% | 83.3% | 100.0% | 100.0% |

No request is dropped silently with v2: what names no type is now passed on as unresolved. The
mean number of wanted types for a one-type request stays at about 2.5 (2.55 before, 2.57 after).

Against the predictions for v1:

1. Held: W 98.3%, P 98.0%. The 1.7% are "AT&T", whose words are too short to match.
2. Held: N1 98.3% avoided, no polarity errors.
3. Held: N2 22.5% (held-out) and 0% (development) avoided; the type was wanted instead in 49.2%
   and 65.6%, and dropped silently in 28.3% and 34.4%. "I don't want a bar" asked for a bar.
4. Held: C and M 96.7%.
5. T failed: 57.1% and 51.0% read right, not at most 25%, and 40.8% and 49.0% dropped silently,
   not at least 60%; matching on the first five letters rescues typos late in a word. L held:
   0% read right, all dropped silently.
6. Mode held (55.0%, 58.3%). Distance held on the held-out set (26.7%) but not on the
   development set (55.0%, above 50%).
7. Held: strength 98.3%, explore 73.3% and 100%, unsupported 83.3% and 100%.

Decision: the changes, written against the development failures only, raised every development
family or left it unchanged, and improved N2, T, L, mode and distance, so they are kept. What
changed in `parse_with_keywords`: more negation triggers ("don't", "anything but", "not in the
mood for"), looking past the first words of a negation when they name nothing; whole category
names matched before single words ("AT&T"); a typo fix to the closest category word (difflib,
cutoff 0.8) when nothing else matches; "on foot" and "by subway" read as modes and, with
distance phrases, kept out of category matching ("under 1 km" had matched "London
Underground"); "under" and "less than" distances and metres; and every part of a request that
names no type passed on as unresolved.

What the held-out set still shows: each held-out-only phrasing fails where the development set
had nothing like it, and these were not fixed: "at most 2 kilometers" (distance 78.3%), "take
the tram" (mode 90.0%; it also wants the "Tram" type), "I haven't tried" (explore 73.3%) and "a
nice view" (unsupported 83.3%). Both request sets were written by the same author, so the
held-out set guards against fitting the 60 development types, not against phrasings nobody
thought of; that needs hand-written requests (E-A).

Remaining errors with v2: a typo can be fixed to the wrong type ("Hotsel" became Hotel, not
Hostel), and a typo in one word of a two-word type leaves only the other word to match
("Depatrment Store" wanted Pet Store); a foreign word can be read as a similar English one
("una playa" wanted Plaza); a type whose name holds a mode word sets the mode ("Rental Car by
bus" became drive); and a plural of a name with "&" ("h&ms") is unresolved. The parser still
reads "no coffee" as the types with "coffee" in their names, so Starbucks is not avoided.
