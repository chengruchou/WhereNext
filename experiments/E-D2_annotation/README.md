# E-D2 annotation: the sentences to label first

201 sentences that Claude wrote for 50 routes (E-D2), in a shuffled order. The paper reports this
batch, and its routes were not used while writing the checks, so annotators label it first. E-D's
200 sentences in `../E-D_annotation` can follow if there is time. Their routes shaped verifier/2.2,
and their ids are not these ids.

The procedure, labels and rules are in [`../E-D_annotation/README.md`](../E-D_annotation/README.md):
at least two people label every sentence on their own, without talking about it and without
opening `key.csv`.

Annotators receive `sentences_E-D2.xlsx`, a workbook made from `sentences.csv`. It is not kept in
the repository.

The labels were collected with four Google Forms built from the same rows instead of the workbook.
The forms differ from the sheet described in `../E-D_annotation/README.md` in three ways: the
sentences are grouped by route, one page per route, not shuffled; each sentence has one question
with four choices (supported, supported but misleading, unsupported, nothing to check) in place of
a label column and a misleading column; and the page shows the route's lines without the row of
cited values. Notes are per route.

`experiments/ed_score_annotation.py` scores the forms' responses workbook. `labels.csv` holds the
labels by sentence id, with annotators as A1, A2, ... in order of their first submission. Both
labelled all 201 sentences: A1 on 2026-11-15, A2 the 104 of the first two forms on 2026-11-15 and
the other 97 on 2026-11-17, after the first results were public here but without knowing them. The
results are in the last three sections of `../E-D_real_explanations.md`.

`sentences.csv` and `key.csv` are written by `experiments/ed_export_annotation.py` from
`experiments/results/claude_validate_2026-10-30.json`; the shuffle uses seed 20. verifier/2.2's
verdicts are computed by the script and match those saved in the run; the other two come from the
run.
