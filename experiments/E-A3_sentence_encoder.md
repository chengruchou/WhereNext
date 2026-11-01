# E-A3: What if a sentence encoder reads the request directly?

Written 2026-11-01, before the test code was written or run. The predictions are hypotheses;
results are reported against them as they come out.

## Why

E-A2 compares the LLM with the keyword parser, which is the offline fallback. The other natural
choice needs no API and no rules: encode the request and take the nearest place types. The paper
wants to say whether letting an LLM decide is worth an API call, so this reader has to be measured
rather than assumed.

## Data

E-A2's 200 requests, with the same scorer (`ea1_keyword_parser.score`). The LLM's and the keyword
parser's scores are read from the saved run, `experiments/results/claude_batch_2026-10-30.json`,
so no API is called.

## Readers

The whole request is encoded with the app's intent encoder (all-MiniLM-L6-v2), and every dataset
place type is ranked by cosine similarity. There are no rules, so nothing is avoided and travel
mode, distance, strength and novelty stay at their defaults.

| ID | Wanted types |
|---|---|
| top 1 | The nearest place type |
| top 8 | The eight nearest, the most the app keeps for one phrase, so a named type is easier to hit |

## Metrics

Per family and overall: `right` (E-A1's score), `types_right` (the place types alone, which is
all an encoder can read), the share with an avoided type wanted instead (`polarity`), and the
mean number of wanted types. Also the 23 held-out-only phrasings, and each reader's worst family.
This measures how well a reader holds across phrasings. It does not measure repeated calls on one
request.

## Predictions

1. Top 1 reads at most 50% of the 200 requests right; the LLM read 99.5%.
2. Both encoder readers read 0% of N1, N2 and C right, since they have no avoid list. For top 1,
   the type the traveler refused is the one chosen in at least 60% of N1 and N2 requests.
3. Top 1 reads at least 70% of W and P right.
4. Top 1 reads at least 50% of T and at most 50% of L right.
5. On the held-out-only phrasings, top 1 is at least 30 points below the LLM.
6. On place types alone, the LLM is at or above top 1 and top 8 in every family.

## What the paper can say, depending on the outcome

If 1 and 2 hold, the paper can say a direct encoder cannot stand in for the LLM, and name the
reason: it finds similar words, not what the traveler means. If top 1 matches the LLM on W and P,
the paper says the gap comes from everything beyond naming a type, not from finding the type.

## Results (run 2026-11-01)

The predictions above are left as written. Script: `experiments/ea3_sentence_encoder.py` (CPU, no
external API; the LLM's and the keyword parser's scores are E-A2's saved ones).

| | LLM | Keyword parser | Top 1 | Top 8 |
|---|---|---|---|---|
| All 200 requests read right | 99.5% | 97.0% | 22.0% | 31.0% |
| Place types alone | 100% | 99.5% | 42.5% | 52.5% |
| Held-out-only phrasings (23) | 95.7% | 78.3% | 13.0% | 26.1% |
| Plain ask, W (31) | 100% | 100% | 96.8% | 100% |
| Negation, N1 and N2 (65) | 100% | 100% | 0% | 0% |
| Typo (8) | 100% | 100% | 50.0% | 87.5% |
| Other language (6) | 100% | 83.3% | 0% | 16.7% |
| Worst family | 88.9% | 77.8% | 0% | 0% |

For every one of the 65 negated requests, top 1 chose the type the traveler refused: "no Condo"
wants Condo. Its one miss on W is "Other - Zoo", read as Zoo. Other languages land on unrelated
types: "una playa" reads as Italian, "博物館に行きたい" as Lab.

Against the predictions:

1. Held: top 1 read 22.0%.
2. Held: 0% of N1, N2 and C right, and the refused type was chosen in all 65 N1 and N2 requests.
3. Held: 96.8% of W and 100% of P.
4. Held: 50.0% of T and 0% of L.
5. Held: 13.0% on the held-out-only phrasings, 82.7 points below the LLM.
6. Held: on place types alone the LLM is at or above both encoder readers in every family.

Part of the gap is by construction: an encoder has no way to read a travel mode, a distance or
wording, so those families score 0 or close to it on `right`. Place types alone (42.5%) is the
fairer number, and it still fails on negation and other languages. Finding a type the request
names is not the problem: top 1 nearly matches the LLM there. The gap is everything beyond naming
a type.

What the paper can say: on the same requests the LLM holds across phrasings where a direct encoder
does not. "Holds" here means across phrasings and request families, not across repeated calls on
one request, which was not measured. The templates are an author's, as in E-A2.

## Offline check (2026-11-01)

The backend's own endpoints were run with no API keys, every non-loopback connection refused and
the Hugging Face hub in offline mode, on the four demo requests. All four were read by the keyword
parser and returned a three-stop route with its evidence (the Austin route has the same legs as
with the LLM: 0.11, 0.73 and 1.08 km). `/api/chat/grounded` returned 503, so there is no written
explanation offline, and `/api/route/` returned no road route. The sentence encoder loaded from
the local cache. The map's own tiles were not part of this check.
