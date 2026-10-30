# E-D annotation: are Claude's explanation sentences true to the evidence?

200 sentences that Claude wrote for 50 routes (E-D), in a shuffled order. At least two people
label every sentence on their own, without talking about it and without opening `key.csv`.

Label [`../E-D2_annotation`](../E-D2_annotation/README.md) first: the paper reports that batch.
This batch can follow if there is time. The rules below apply to both.

## What each row shows

The request, the traveler's history (oldest first; the last visit is where the route starts), the
sentence, the values it cites, and the whole route: for every stop its type, the distance from the
stop before, whether it is a requested type, how many requested places were within reach, how
many earlier visits were of its type (the history plus the earlier stops), whether the traveler
has been to that exact place, its place number, the main signal that chose it and its habit
score. `▶` marks the stop the sentence is about; `summary` rows are about the whole route.

## For each sentence

Judge against the whole row, not only the cited values, and put one label in
`annotator label`:

- **supported**: everything the sentence states follows from the row.
- **unsupported**: it states at least one thing that is false or that the data does not hold
  (a rating, a price, opening hours, popularity, a comparison the row does not bear out, a wrong
  number or type).
- **nothing to check**: it states nothing that could be true or false against the data.

Two rules settle the cases a reader cannot decide from the data alone:

- **Habits.** Main signal `habit` means the model ranked the place highly from the order of the
  traveler's recent visits; it does not mean the traveler has visited that type. "Fits your
  habits", "your usual pattern" or "your past movements" is supported when that stop's main
  signal is habit or its habit score is at least 0.80. "Resembles places you have visited" is a
  claim about the history and is checked against it.
- **Near.** "Near", "close", "right beside" and "a short drive" are judged against the distance
  and the travel mode, roughly 1 km on foot and 3 km by car.

Put `yes` in `misleading` when a sentence is supported but a traveler would likely read it as
something false, for example "fits your habits" for a type the traveler has never visited. Use
`note` for anything else worth saying.

Annotators receive a workbook made from `sentences.csv`: the same rows with these instructions in
English and Chinese, drop-down lists and the input columns in yellow. The workbook itself is not
kept in the repository.

## After everyone has labelled

1. Agreement over the three labels: Cohen's kappa for two annotators, Fleiss' kappa and every
   pair's Cohen's kappa for more.
2. Resolve disagreements together; the agreed label is the reference.
3. Open `key.csv` and compare each verifier with the reference: of the sentences it removed, how
   many were unsupported (precision), and of the unsupported sentences, how many it removed
   (recall). Report verifier/2.2, verifier/2.1 and verifier/1.
4. Report the share of supported sentences marked misleading, overall and for habit wording.

## Why the rows show the whole route

An earlier version of this sheet showed only the facts of the sentence's own stop. In a pilot
with three LLM annotators, most of the sentences labelled unsupported were true of the route but
could not be checked from the row: "a longer 29.17 km drive" needs the earlier legs, "from the
Apple Store" needs the stop before, "three different places" needs the place numbers. They also
split on whether "fits your habits" needs the type in the history or only the model's habit
signal. The pilot's labels are not a reference; the sheet now shows the route and the two rules
above.

`sentences.csv` and `key.csv` are written by `experiments/ed_export_annotation.py` from
`experiments/results/claude_batch_2026-10-30.json`; the shuffle uses seed 20, so ids are the same
as in the earlier sheet. verifier/2.2's verdicts are computed by the script; the other two come
from the batch.
