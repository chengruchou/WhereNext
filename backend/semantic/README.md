# Semantic Reranking Layer

## Overview

This folder implements the first-stage, backend-only semantic reranking layer for the repository's existing SBR-based POI recommendation system.

Its purpose is to take the top-k predictions produced by the existing session-based recommender, add a lightweight semantic signal at inference time, and reorder those candidates before the final POI list is serialized back to the client.

This layer was added to improve recommendation relevance without requiring:

- changes to the frontend API contract
- retraining or replacing the existing SBR model
- a full reproduction of the original POI-Enhancer paper

The current design is best understood as a practical, inference-time adaptation inspired by the POI-Enhancer idea. It borrows the notion of building multiple semantic views of each POI and using them for reranking, but it intentionally does not implement the paper's full training-time architecture.

## Current Integration Point

The semantic reranker is currently integrated into the backend request flow in [backend/routes/model_api.py](POI_System/backend/routes/model_api.py).

The runtime sequence is:

1. The backend loads a user's visit history from `UserHist`.
2. It writes a temporary visit file and runs `model_core/MG-DSGAT/src/infer_sbr.py`.
3. The SBR model returns top-k prediction objects in JSON form.
4. The backend calls `semantic.rerank_predictions_for_user(...)`.
5. The returned ranked `raw_location_id` order is used to fetch and serialize final POI objects.
6. The frontend receives the same style of POI list as before.

Important integration characteristics:

- The semantic reranker is triggered after SBR top-k predictions are generated.
- It runs before final POI serialization.
- The frontend response format is intentionally unchanged.
- If the semantic reranker fails, the backend logs the error and falls back to the original SBR order.

In other words, this folder changes ranking behavior, not the API contract.

## Folder Structure

### `__init__.py`

Main responsibility:
- Exposes the semantic package surface for backend integration.

Key exports:
- `SemanticRerankerConfig`
- `rerank_predictions_for_user`

This is the package entry point imported by `backend/routes/model_api.py`.

### `config.py`

Main responsibility:
- Defines static configuration for the semantic reranking layer.

Key class:
- `SemanticRerankerConfig`

Current fields:
- `ENABLE_SEMANTIC_RERANKER`
- `SEMANTIC_ALPHA`
- `SEMANTIC_BETA`
- `SEMANTIC_EMBEDDING_BACKEND`
- `SEMANTIC_MAX_HISTORY_ITEMS`
- `SEMANTIC_EMBEDDING_DIM`
- `SEMANTIC_VIEW_WEIGHTS`

This is the main place to tune behavior without changing the pipeline structure.

### `schemas.py`

Main responsibility:
- Defines the typed containers used across the semantic reranking pipeline.

Key dataclasses:
- `MultiViewPrompts`
  - Stores the three text views: `visit_pattern`, `location`, `category`
  - Includes `as_ordered_list()`
- `CandidatePOI`
  - Wraps one SBR candidate plus metadata and reranking fields
- `UserSemanticProfile`
  - Stores the aggregated user semantic vector from historical POIs
- `RerankResult`
  - Stores the final reranking output and debug information

These types are the easiest way to understand the data flow inside the folder.

### `prompt_builder.py`

Main responsibility:
- Builds the three semantic prompt views for each POI from available metadata.

Key functions:
- `build_visit_prompt(poi_metadata)`
- `build_location_prompt(poi_metadata)`
- `build_category_prompt(poi_metadata)`
- `build_views(poi_metadata)`

What it does:
- Converts raw POI metadata into short, structured prompt text
- Uses safe fallbacks when metadata fields are missing
- Maps limited repository metadata onto a POI-Enhancer-style multi-view prompt design

### `embedder.py`

Main responsibility:
- Defines the semantic embedding abstraction and backend factory.

Key classes and functions:
- `BaseSemanticEmbedder`
- `MockSemanticEmbedder`
- `HuggingFaceSemanticEmbedder`
- `build_embedder(backend_name, embedding_dim=128)`

What it does:
- Lets the reranker operate against a stable embedding interface
- Uses `MockSemanticEmbedder` by default for deterministic CPU-only behavior
- Leaves `HuggingFaceSemanticEmbedder` as a scaffold for future real model integration

### `fusion.py`

Main responsibility:
- Fuses the three view embeddings into one semantic vector per POI.

Key class:
- `WeightedSemanticFusion`

Key methods:
- `fuse(visit_embedding, location_embedding, category_embedding)`
- `_normalized_weights()`

What it does:
- Applies deterministic weighted fusion
- Normalizes view weights safely
- Returns a unit-normalized fused embedding

This is intentionally lightweight and non-trainable.

### `reranker.py`

Main responsibility:
- Orchestrates the end-to-end semantic reranking pipeline.

Key functions:
- `package_candidates(predictions, poi_by_id)`
- `build_poi_semantic_vector(candidate, embedder, fusion)`
- `build_user_semantic_profile(user_id, history_poi_metadata, embedder, fusion)`
- `rerank_packaged_candidates(user_id, candidates, history_poi_metadata, config=None)`
- `rerank_predictions_for_user(user_id, predictions, histories=None, config=None)`

What it does:
- Packages SBR predictions with POI metadata
- Builds prompt views
- Embeds and fuses candidate POIs
- Builds a user semantic profile from recent history
- Computes semantic similarity and combines it with normalized SBR scores
- Returns reranked predictions

This is the main file to start with if you want to understand the runtime logic.

### `utils.py`

Main responsibility:
- Provides helper functions for prompt construction, scoring, and local debugging.

Key functions:
- `safe_float(value)`
- `describe_count_band(value)`
- `infer_usage_tendency(poi_metadata)`
- `simple_region_summary(lat, lng)`
- `get_category_descriptors(poi_metadata)`
- `min_max_normalize(values)`
- `cosine_similarity(left, right)`
- `average_vectors(vectors)`
- `rank_predictions_by_raw_id(predictions)`
- `run_mock_rerank_demo()`

What it does:
- Converts raw metadata into safer semantic descriptors
- Provides vector math utilities
- Includes a small mock demo for sanity checking the reranker behavior

## Current Semantic Pipeline

The current semantic pipeline is entirely inference-time and runs after SBR prediction generation.

### 1. Receive SBR predictions

`rerank_predictions_for_user(...)` receives a list of prediction dictionaries produced by the existing SBR model. These prediction objects already include `rank`, `item_id`, `score`, and `raw_location_id`.

### 2. Load user history and POI metadata

The reranker loads:

- recent user visit history from `UserHist`
- POI records from `POI`

It collects:

- metadata for top-k candidate POIs
- metadata for recent historical POIs

User history is truncated by `SEMANTIC_MAX_HISTORY_ITEMS`.

### 3. Build multi-view prompts

For each POI, `build_views(...)` generates three prompt texts:

- visit-pattern view
- location view
- category/surrounding view

These prompts are built heuristically from available metadata such as:

- `category_name`
- `checkins_count`
- `users_count`
- event-related counts
- latitude and longitude
- raw category labels
- radius, photo count, highlight count, item count

### 4. Embed prompt texts

The three prompt strings are passed to the configured embedder through `embed_texts(...)`.

Today, the default backend is `MockSemanticEmbedder`, which:

- tokenizes the text
- hashes tokens into feature buckets
- produces a deterministic vector
- L2-normalizes the result

This keeps the pipeline lightweight and portable, but it is not a learned semantic model.

### 5. Fuse view embeddings

`WeightedSemanticFusion.fuse(...)` combines the three view embeddings using normalized deterministic weights from `SEMANTIC_VIEW_WEIGHTS`.

The result is one fused semantic vector for each POI.

### 6. Build user semantic vector

`build_user_semantic_profile(...)` converts recent historical POIs into fused semantic vectors using the same prompt-building and embedding pipeline, then aggregates them with `average_vectors(...)`.

The result is a single user semantic profile vector.

### 7. Compute semantic score

For each candidate POI, the reranker computes:

- `semantic_score = cosine_similarity(user_profile.vector, candidate_semantic_vector)`

If the user profile vector is unavailable, the semantic score safely falls back to `0.0`.

### 8. Combine with original SBR score

The original SBR scores are min-max normalized via `min_max_normalize(...)`.

Then the final score is computed as:

```text
final_score =
    SEMANTIC_ALPHA * normalized_sbr_score +
    SEMANTIC_BETA  * semantic_score
```

Current defaults:

- `SEMANTIC_ALPHA = 0.7`
- `SEMANTIC_BETA = 0.3`

### 9. Rerank predictions

Candidates are sorted by:

1. descending `final_score`
2. descending original `score`
3. ascending original `rank`

The reranker then returns prediction dictionaries containing:

- `rank`
- `item_id`
- `score`
- `raw_location_id`
- `normalized_sbr_score`
- `semantic_score`
- `final_score`

In the current backend integration, only the ranking order is used downstream for final POI serialization.

## Mapping to POI-Enhancer-Inspired Design

This implementation is inspired by POI-Enhancer-style semantic adaptation, but it is intentionally narrower in scope.

### Concepts borrowed from the POI-Enhancer-style design

The current code borrows these ideas at a high level:

- representing a POI through multiple semantic views
- building textual semantic descriptions from metadata
- embedding those views into vector space
- fusing multiple view representations
- using a semantic user profile derived from historical behavior
- combining semantic relevance with the original recommender score for reranking

### What is currently implemented

The codebase currently implements:

- three heuristic prompt views per POI
- an embedding backend abstraction
- a deterministic mock embedding backend
- deterministic weighted fusion of views
- history-based user semantic profile aggregation
- cosine-similarity semantic scoring
- linear combination of semantic score and normalized SBR score
- safe end-to-end inference-time reranking inside the existing backend flow

### What is intentionally not implemented yet

The current folder does not implement the full POI-Enhancer training stack. In particular, it does not currently include:

- Dual Feature Alignment
- Cross Attention Fusion
- Multi-View Contrastive Learning
- a trainable semantic module
- a frozen-LLM hidden-state pipeline
- joint optimization with the SBR backbone
- paper-level reproduction of the original architecture or experimental setup

This distinction matters. The current system is a deployable engineering layer, not a full research reproduction.

## Configuration

All current configuration lives in `config.py` through `SemanticRerankerConfig`.

### Enable or disable the reranker

- `ENABLE_SEMANTIC_RERANKER: bool = True`

If set to `False`, `rerank_predictions_for_user(...)` immediately returns the original SBR predictions unchanged.

### Score mixing weights

- `SEMANTIC_ALPHA: float = 0.7`
- `SEMANTIC_BETA: float = 0.3`

These control the balance between:

- normalized SBR score
- semantic similarity score

They are currently used in a simple linear combination.

### Embedding backend

- `SEMANTIC_EMBEDDING_BACKEND: str = "mock"`

Supported today:

- `"mock"`
- `"hf"` / `"huggingface"` / `"transformers"` as a future scaffold

Important note:
- the Hugging Face path is not implemented yet and will raise `NotImplementedError`

### Embedding dimensionality

- `SEMANTIC_EMBEDDING_DIM: int = 128`

This is currently used by the mock embedder.

### Maximum history items

- `SEMANTIC_MAX_HISTORY_ITEMS: int = 20`

This caps how many recent historical POIs are used when constructing the user semantic profile.

### View weights

- `SEMANTIC_VIEW_WEIGHTS`

Current default:

```python
{
    "visit_pattern": 0.45,
    "location": 0.25,
    "category": 0.30,
}
```

These are normalized inside `WeightedSemanticFusion` before fusion.

## Failure Handling / Fallback

The semantic reranker is designed to fail safely.

There are two important fallback behaviors:

### Reranker disabled

If `ENABLE_SEMANTIC_RERANKER` is `False`, the backend simply returns the original SBR predictions.

### Reranker runtime failure

In `backend/routes/model_api.py`, the call to `rerank_predictions_for_user(...)` is wrapped in `try/except`.

If semantic reranking throws an exception:

- the error is logged
- the system keeps the original SBR prediction order
- final POI serialization still proceeds

This preserves service continuity and keeps the backend contract stable even when the semantic layer misbehaves.

## Current Limitations

This folder is functional, but still intentionally minimal.

Current limitations include:

- The default embedder is a deterministic mock backend, not a learned semantic encoder.
- `HuggingFaceSemanticEmbedder` is only a scaffold and is not implemented yet.
- Prompt generation is heuristic and metadata-dependent.
- The system depends on the quality and completeness of `POI.to_dict()` metadata.
- The fusion layer is deterministic and non-trainable.
- There is no Dual Feature Alignment.
- There is no Cross Attention Fusion.
- There is no Multi-View Contrastive Learning.
- There is no frozen or trainable hidden-state LLM pipeline.
- There is no offline evaluation pipeline in this folder yet.
- There is no explicit seen-item penalty or revisit control mechanism yet.
- There is no embedding cache yet.
- There is no calibration or systematic sweep for `alpha`, `beta`, or view weights yet.
- The current integration mainly uses the reranked order; extra debug scores are not exposed to the frontend.

## Recommended Next Steps

The most useful next engineering and research steps are:

### 1. Add an offline evaluation pipeline

Build a reproducible evaluation path so the team can compare:

- baseline SBR ranking
- semantic reranked ranking
- different alpha/beta settings
- different prompt variants
- different embedding backends

Without this, improvements remain mostly qualitative.

### 2. Add seen-item control or revisit penalty

The current reranker can semantically favor items similar to user history, but it does not explicitly control:

- already visited POIs
- excessive same-category repetition
- re-recommendation frequency

That should be handled explicitly if the product requires novelty.

### 3. Run alpha/beta sweeps

Tune `SEMANTIC_ALPHA` and `SEMANTIC_BETA` systematically rather than relying on the current initial defaults.

### 4. Run prompt ablations

Measure how much each view contributes:

- visit-pattern only
- location only
- category only
- weighted combinations

This will help decide whether the current prompt design is actually helping.

### 5. Replace the mock embedder with a real embedding backend

Implement a real encoder behind `BaseSemanticEmbedder`, for example:

- sentence-transformers
- Hugging Face pooled encoders
- another lightweight production-friendly text embedding model

This is likely the single largest quality upgrade.

### 6. Add embedding caching

Many POIs are likely to recur across requests. Caching prompt embeddings or fused POI vectors could reduce latency and repeated work.

### 7. Consider richer fusion later

If the project moves toward a stronger research-grade semantic layer, possible upgrades include:

- trainable fusion
- cross-view interaction
- user-history weighting by recency
- joint semantic and SBR calibration

## Usage / Developer Notes

This folder is safe to modify if you keep one rule in mind:

The backend integration expects `rerank_predictions_for_user(...)` to accept SBR prediction dictionaries and return prediction dictionaries in ranking order. As long as that surface remains stable, you can evolve the internals freely.

### Safe places to modify

- Change prompt wording in `prompt_builder.py`
- Change view weighting in `config.py`
- Swap embedding backends in `embedder.py`
- Experiment with fusion logic in `fusion.py`
- Change score mixing logic in `reranker.py`

### Places to modify carefully

- `rerank_predictions_for_user(...)`
  - This is the integration boundary used by the backend route.
- `CandidatePOI` and returned prediction keys
  - Downstream code currently relies on `raw_location_id` ordering.
- error behavior
  - Preserve safe fallback to original SBR ranking

### Suggested starting point for developers

If you are new to this folder, start from:

1. `reranker.py`
2. `prompt_builder.py`
3. `config.py`
4. `embedder.py`
5. `fusion.py`
6. `schemas.py`
7. `utils.py`

This order matches the runtime flow and makes the design easiest to follow.

## Recommended Reading Order

For future developers and researchers, the recommended reading order is:

1. `backend/routes/model_api.py` to see where the semantic reranker is called
2. `backend/semantic/reranker.py` to understand the end-to-end pipeline
3. `backend/semantic/prompt_builder.py` to see how POI metadata becomes semantic text
4. `backend/semantic/embedder.py` to understand the embedding abstraction
5. `backend/semantic/fusion.py` to understand multi-view fusion
6. `backend/semantic/config.py` to see the tunable parameters
7. `backend/semantic/schemas.py` and `backend/semantic/utils.py` for supporting structures and helpers
