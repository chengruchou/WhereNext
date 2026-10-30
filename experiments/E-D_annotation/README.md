# E-D annotation: are Claude's explanation sentences true to the evidence?

200 sentences that Claude wrote for 50 routes (E-D), in a shuffled order. Two annotators label
every sentence on their own, without talking about it and without opening `key.csv`.

## For each sentence

Read the request, the traveler's history, the stop's facts and the cited values, then put one
label in `annotator label`:

- **supported**: everything the sentence states follows from the cited values, the stop's facts
  or the history.
- **unsupported**: it states at least one thing that is false or that the data does not hold
  (a rating, a price, opening hours, popularity, a comparison such as "the closest", a wrong
  number or type, "you often go" when the visits say otherwise).
- **nothing to check**: it states nothing that could be true or false against the data.

Use `note` for anything worth saying, for example a sentence that is true but misleading.

## After both have labelled

1. Cohen's kappa between the two annotators over the three labels.
2. Resolve disagreements together; the agreed label is the reference.
3. Open `key.csv` and compare each verifier with the reference: of the sentences it removed, how
   many were unsupported (precision), and of the unsupported sentences, how many it removed
   (recall). Report both verifiers.

`sentences.csv` and `key.csv` are written by `experiments/ed_export_annotation.py` from
`experiments/results/claude_batch_2026-10-30.json`; the shuffle uses seed 20.
