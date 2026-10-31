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

`sentences.csv` and `key.csv` are written by `experiments/ed_export_annotation.py` from
`experiments/results/claude_validate_2026-10-30.json`; the shuffle uses seed 20. verifier/2.2's
verdicts are computed by the script and match those saved in the run; the other two come from the
run.
