# Offline Evaluation Toolkit

## Purpose

This folder provides an offline backend-side evaluation pipeline for comparing:

1. the original SBR ranking
2. the same SBR top-k after semantic reranking

It exists only as an evaluation tool. It does not modify:

- the frontend
- the API routes
- the online serving contract
- the main recommendation serving path

The goal is to measure whether the current semantic reranker improves ranking quality when applied to the existing SBR model outputs.

## Expected Inputs

### Test split

Place the evaluation split at:

`backend/eval/test.txt`

Current assumption:

- `test.txt` is a pickle file
- it contains evaluation samples in the same logical format as the original test split
- each sample represents:
  - a history prefix
  - a target next item

The current loader supports:

- `tuple(histories, targets)`
- list-style samples that normalize into `history_item_ids + target_item_id`

### Metadata source

This evaluation pipeline uses the current system database for POI metadata lookup through the existing backend app context.

### Reranker source

This evaluation pipeline reuses the existing semantic reranker implementation in `backend/semantic/`. It does not reimplement semantic reranking inside `backend/eval/`.

## What Gets Reused

The evaluation script intentionally reuses current backend logic:

- SBR inference from `backend/model_core/MG-DSGAT/src/infer_sbr.py`
- semantic reranking from `semantic.rerank_predictions_for_user(...)`
- POI metadata lookup through `backend/app.py` and `backend/database.py`

This keeps offline evaluation aligned with the deployed backend behavior.

## Files

### `evaluate_reranker.py`

Main offline evaluation entry point.

It:

- loads `test.txt`
- normalizes samples into `history_item_ids` and `target_item_id`
- runs original SBR top-k prediction
- runs semantic reranking on the same candidate set
- compares target rank before and after reranking
- writes detailed outputs under `backend/eval/outputs/`

### `metrics.py`

Computes summary ranking metrics, including:

- Hit@1
- Hit@5
- MRR
- average ground-truth rank before rerank
- average ground-truth rank after rerank

Note:
- average ground-truth rank is computed over samples where the target appears in top-k
- the summary also reports how many samples were missing from top-k

### `analysis.py`

Provides additional diagnostics, including:

- seen-item ratio in top-k before rerank
- seen-item ratio in top-k after rerank
- whether top-1 is a previously seen item
- improved sample list
- worsened sample list

### `outputs/`

Generated evaluation artifacts are written here.

Current outputs:

- `detailed_results.json`
- `detailed_results.csv`
- `summary_metrics.json`

## How Evaluation Works

For each test sample:

1. Read the history prefix and target next item from the pickle split.
2. Run the current SBR model to produce top-k predictions.
3. Apply the current semantic reranker to that same top-k list.
4. Measure where the target item ranks before reranking.
5. Measure where the target item ranks after reranking.
6. Record detailed per-sample diagnostics.
7. Aggregate summary metrics.

This is an offline comparison pipeline only. It does not go through the frontend and does not call the existing API routes.

## How This Differs From Online Serving

Online serving path:

- reads live user history from the database
- runs the SBR model for a single request
- applies semantic reranking in the backend route
- returns serialized POIs to the frontend

Offline evaluation path:

- reads a stored pickle test split from `backend/eval/test.txt`
- runs SBR and semantic reranking sample-by-sample offline
- compares ranking quality against ground truth
- writes analysis artifacts to `backend/eval/outputs/`

The serving path remains unchanged.

## How To Run

From the repository root:

```bash
python backend/eval/evaluate_reranker.py
```

Example with a sample limit:

```bash
python backend/eval/evaluate_reranker.py --limit 1000
```

Optional useful arguments:

- `--topk 10`
- `--test-path backend/eval/test.txt`
- `--output-dir backend/eval/outputs`
- `--checkpoint backend/model_core/MG-DSGAT/save_model/Demo_model_exp30_Gowalla_512_seed_2023-last_k_4_best_model.pt`
- `--reverse-mapping-json backend/datasets/Gowalla/item2raw_location.json`
- `--semantic-embedding-backend mock`

If `--device cuda` is requested but CUDA is unavailable, the script falls back to CPU.

For offline evaluation, the script defaults to `--semantic-embedding-backend mock` so it can run without downloading external embedding models. If you already have a local Hugging Face embedding model path configured and available, you can override this with a different backend value.

## Metrics

The summary output currently includes:

- `before.hit@1`
- `before.hit@5`
- `before.mrr`
- `before.average_ground_truth_rank`
- `after.hit@1`
- `after.hit@5`
- `after.mrr`
- `after.average_ground_truth_rank`
- metric deltas between after and before

Additional analysis includes:

- average seen-item ratio before rerank
- average seen-item ratio after rerank
- top-1 seen-item rate before rerank
- top-1 seen-item rate after rerank
- improved sample count
- worsened sample count

## Notes

- This toolkit assumes the item ids in the pickle test split are the SBR model's internal item ids.
- Semantic reranking still depends on raw POI metadata from the database, so reverse mapping coverage matters.
- The main recommendation serving logic is not modified by this evaluation toolkit.
