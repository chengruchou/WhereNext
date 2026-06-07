# WhereNext: Interactive Semantic-Spatial POI Exploration

WhereNext is a runnable full-stack demo system for interactive Point-of-Interest (POI) exploration.
It turns next-POI recommendation from a static top-K ranking task into an editable, explainable, and map-based urban exploration workflow.

Users can load or edit a POI trajectory, search and add POIs, request short-horizon next-POI recommendations, inspect recommended destinations on a Google Map, visualize planned routes, and view LLM-generated route-level explanations.

> This repository contains the runnable demo system.
> It is not the full offline training or benchmark evaluation repository.

---

## Features

* Load user trajectories by user ID.
* Display observed POI visits on a map.
* Search POIs by raw POI ID or category.
* Add or remove POIs from the current trajectory.
* Request short-horizon next-POI recommendations.
* Display recommendation cards and map markers.
* Visualize routes using the Google Maps API.
* Generate route-level explanations with an LLM.
* Apply semantic-spatial reranking on top of a deployed SBR backbone.

---

## System Components

WhereNext consists of four main components:

1. **Vue/Vite Frontend**
   Provides the map-centered interface, trajectory editing, POI search, recommendation display, and explanation panel.

2. **Flask Backend**
   Provides REST APIs for user history, POI lookup, recommendation, route planning, and LLM explanation.

3. **Recommendation Service**
   Uses a deployed session-based recommendation backbone to generate candidate POIs.

4. **Semantic-Spatial Reranking**
   Refines backbone-generated candidates using spatial retrieval and semantic similarity before returning hydrated POI objects to the frontend.

The current demo deploys **MG-DSGAT** as the SBR candidate-generation backbone. The system is designed so that other SBR backbones can be adapted by replacing the model adapter that maps user trajectories to ranked raw POI IDs.

---

## Repository Structure

```text
WhereNext/
├── frontend/                         # Vue/Vite frontend
│   ├── src/
│   │   ├── App.vue                    # Main frontend orchestration
│   │   ├── main.ts                    # Frontend entry point
│   │   └── components/
│   │       ├── UserLogin.vue          # User ID input and trajectory loading
│   │       ├── HistoryList.vue        # Observed visit list
│   │       ├── SearchPanel.vue        # POI search interface
│   │       ├── RecommendPanel.vue     # Recommendation cards
│   │       ├── MapCanvas.vue          # Google Map, markers, and info windows
│   │       ├── DrawRoute.vue          # Route polyline rendering
│   │       ├── ChatPanel.vue          # LLM rationale display
│   │       └── POIDetailDialog.vue    # POI semantic/spatial profile dialog
│   ├── package.json
│   └── vite.config.mts
│
├── backend/                          # Flask backend
│   ├── app.py                         # Backend entry point
│   ├── database.py                    # SQLAlchemy models
│   ├── json_to_db.py                  # Build SQLite DB from metadata
│   ├── routes/
│   │   ├── user_api.py                # User history APIs
│   │   ├── poi_api.py                 # POI search/detail APIs
│   │   ├── model_api.py               # Recommendation API
│   │   ├── route_api.py               # Google Routes API proxy
│   │   └── chat_api_multi.py          # LLM route explanation API
│   ├── services/
│   │   ├── recommendation_service.py  # Request-level recommendation pipeline
│   │   ├── model_config.py            # Model and artifact configuration
│   │   └── latest_model_adapter.py    # MG-DSGAT adapter and reranking logic
│   ├── model_core/
│   │   └── MG-DSGAT/                  # Deployed SBR backbone implementation
│   ├── datasets/                      # POI metadata and mapping files
│   ├── pyproject.toml
│   └── uv.lock
│
└── README.md
```

---

## Prerequisites

### Frontend

* Node.js 20 or newer is recommended.
* npm

### Backend

* Python 3.13 or newer
* uv
* SQLite
* PyTorch-compatible environment

The backend can run on CPU, but GPU inference is recommended for faster recommendation.

---

## Configuration

### Frontend Environment

Create a frontend environment file:

```bash
cp frontend/.env.example frontend/.env
```

Example `frontend/.env`:

```env
VITE_GOOGLE_API_KEY=your_google_maps_api_key
VITE_API_BASE_URL=http://127.0.0.1:5000/api
```

### Backend Environment

Create a backend environment file:

```bash
cp backend/.env.example backend/.env
```

Example `backend/.env`:

```env
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_MAPS_API_KEY=your_google_maps_api_key

DATABASE_URL=sqlite:///app.db
FLASK_HOST=127.0.0.1
FLASK_PORT=5000

WHERENEXT_MODEL_REPO=backend/model_core/MG-DSGAT
WHERENEXT_MODEL_CHECKPOINT=backend/model_core/MG-DSGAT/checkpoints/weight.pt
WHERENEXT_RAW2ITEM_JSON=backend/model_core/MG-DSGAT/datasets/Gowalla/raw_location2item.json
WHERENEXT_ITEM2RAW_JSON=backend/model_core/MG-DSGAT/datasets/Gowalla/item2raw_location.json
WHERENEXT_POI_METADATA_JSON=backend/model_core/MG-DSGAT/datasets/Gowalla/filtered_poi_metadata.json
WHERENEXT_SEMANTIC_EMBEDDING_PATH=backend/model_core/MG-DSGAT/artifact/Gowalla/poi_semantic_embeddings.pt

WHERENEXT_DEVICE=cpu
WHERENEXT_MODEL_TOP_K=20
WHERENEXT_RETURN_TOP_K=5
WHERENEXT_ENABLE_SPATIAL=true
WHERENEXT_ENABLE_SEMANTIC=true
WHERENEXT_SEMANTIC_MODE=single
```

Do not commit real `.env` files or API keys.

---

## Required Artifacts

The runnable demo requires several data and model artifacts.

| Artifact                    | Expected Path                                                             | Required                   |
| --------------------------- | ------------------------------------------------------------------------- | -------------------------- |
| POI metadata                | `backend/datasets/filtered_poi_metadata.json`                             | Yes                        |
| Raw-to-internal POI mapping | `backend/model_core/MG-DSGAT/datasets/Gowalla/raw_location2item.json`     | Yes                        |
| Internal-to-raw POI mapping | `backend/model_core/MG-DSGAT/datasets/Gowalla/item2raw_location.json`     | Yes                        |
| SQLite database             | `backend/instance/app.db`                                                 | Generated                  |
| MG-DSGAT checkpoint         | `backend/model_core/MG-DSGAT/checkpoints/weight.pt`                       | Yes for recommendation     |
| Semantic POI embeddings     | `backend/model_core/MG-DSGAT/artifact/Gowalla/poi_semantic_embeddings.pt` | Yes for semantic reranking |

Large model artifacts such as `.pt` checkpoints and semantic embeddings should not be tracked directly in normal Git history. Use Git LFS, GitHub Release assets, Zenodo, or an external download link.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/chengruchou/WhereNext.git
cd POI_System
```

Install backend dependencies:

```bash
cd backend
uv sync
```

Download the pretrained model checkpoint from the following [link](https://drive.google.com/file/d/1TOCfHrGnm9WyyLQV_lV2U43T0ccYDL2B/view?usp=drive_link)


Place the downloaded checkpoint file under the following directory:

```bash
backend/model_core/MG-DSGAT/checkpoints/
```

The expected checkpoint path is:

```bash
backend/model_core/MG-DSGAT/checkpoints/weight.pt
```

Install frontend dependencies:

```bash
cd ../frontend
npm install
```

---

## Prepare the Database

From the backend directory, build the local SQLite database from the POI metadata file:

```bash
cd backend
uv run python json_to_db.py
```

This creates the local database used by the Flask backend.

---

## Run the Backend

From the backend directory:

```bash
cd backend
uv run python app.py
```

By default, the backend runs at:

```text
http://127.0.0.1:5000
```

---

## Run the Frontend

From the frontend directory:

```bash
cd frontend
npm run dev
```

Open the local frontend URL shown by Vite, for example:

```text
http://localhost:3000/
```

---

## Demo Workflow

A typical WhereNext demo follows this workflow:

1. Enter a user ID and load the user trajectory.
2. Inspect observed POI visits in the history panel.
3. View the historical trajectory on the Google Map.
4. Search POIs by ID or category.
5. Add selected POIs to the current trajectory.
6. Remove unwanted POIs if needed.
7. Click **Get next POIs** to request recommendations.
8. Inspect recommendation cards and map markers.
9. View route visualization connecting the current trajectory and recommended destinations.
10. Read the LLM-generated route-level explanation.

---

## API Overview

### User History APIs

Used for loading, adding, and deleting user visit histories.

```text
GET    /api/user/...
POST   /api/user/...
DELETE /api/user/...
```

### POI APIs

Used for POI search and POI detail retrieval.

```text
GET /api/poi/...
```

### Recommendation API

Used when the frontend requests next-POI recommendations.

```text
POST /api/model/genpoi/<user_id>
```

The backend retrieves the user trajectory, maps raw POI IDs to internal item IDs, runs the deployed SBR backbone, applies spatial and semantic reranking, hydrates the final POI objects, and returns them to the frontend.

### Route Planning API

Used by the frontend to request planned routes.

```text
POST /api/route/
```

This endpoint proxies route-planning requests to the Google Routes API and returns route geometry for frontend visualization.

### LLM Explanation API

Used to generate route-level recommendation rationales.

```text
POST /api/chat/explain
```

The backend sends historical POIs and recommended POIs to the LLM provider and returns a Markdown explanation to the frontend.

---

## Recommendation Pipeline

The recommendation pipeline proceeds as follows:

1. The server retrieves the user’s current trajectory.
2. Raw Gowalla POI IDs are mapped to internal item IDs.
3. The deployed SBR backbone generates candidate next POIs.
4. Candidate internal item IDs are decoded back to raw POI IDs.
5. BallTree-based spatial retrieval expands geographically plausible POIs.
6. Semantic reranking compares candidates with the user’s recent semantic profile.
7. Final ranked candidates are hydrated with POI metadata.
8. The frontend receives POI objects for map-based interaction and explanation.

---

## Notes on the Model Backbone

The current demo implementation deploys MG-DSGAT as the session-based recommendation backbone. MG-DSGAT is used as a black-box candidate generator in this system.

WhereNext itself does not propose a new SBR architecture. Instead, it demonstrates how a deployed SBR backbone can be connected with semantic-spatial reranking, map-based interaction, route visualization, and LLM-based explanation.

The system design can be adapted to other SBR backbones if they provide ranked candidate POIs that can be mapped back to raw POI identifiers.

---

## Notes on Google Maps and LLM APIs

WhereNext uses the Google Maps API for map rendering, marker display, and route planning. A valid Google Maps API key is required.

WhereNext uses an LLM provider to generate route-level explanations. The current implementation uses Gemini. A valid API key is required for explanation generation.

LLM outputs may vary across runs. They are intended for qualitative route explanation and should not be treated as benchmark evidence.

API calls to Google Maps and LLM providers may incur cost depending on your account and usage.

---

## Troubleshooting

### Backend fails because `GEMINI_API_KEY` is missing

Set `GEMINI_API_KEY` before starting the backend, or configure the chat route to be optional.

### Google Map does not load

Check that `VITE_GOOGLE_API_KEY` is correctly set in `frontend/.env`.

### Route visualization does not appear

Check that the backend route proxy can access the Google Routes API and that the Google API key has the required permissions.

### Recommendation endpoint fails because checkpoint is missing

Make sure the MG-DSGAT checkpoint exists at:

```text
backend/model_core/MG-DSGAT/checkpoints/weight.pt
```

or set `WHERENEXT_MODEL_CHECKPOINT` to the correct path.

### Semantic reranking is skipped or fails

Make sure the semantic embedding file exists at:

```text
backend/model_core/MG-DSGAT/artifact/Gowalla/poi_semantic_embeddings.pt
```

or set `WHERENEXT_SEMANTIC_EMBEDDING_PATH` to the correct path.

---

## Open-Source Scope

This repository focuses on the runnable WhereNext demo system. It does not include the full offline training, benchmark evaluation, or reproduction pipeline for all reported baselines.

For academic results, please refer to the paper. If a separate evaluation repository is released, link it here.

---

## Citation

<!-- If you use this system, please cite:

```bibtex
@inproceedings{chou2026wherenext,
  title     = {WhereNext: An Interactive Semantic-Spatial System for Point-of-Interest Exploration},
  author    = {Chou, Cheng-Ru and Cai, Zong-Ze and Lin, Ting-Hsuan and Liu, Kuan-Yu and Li, Pei-Xuan and Tsai, Shou-Po and Hsieh, Hsun-Ping and Yen, I-Hsuan},
  booktitle = {Proceedings of the 35th International ACM Conference on Knowledge and Information Management},
  year      = {2026}
}
``` -->

The deployed SBR backbone is based on MG-DSGAT:

```bibtex
@inproceedings{li2025mgdsgat,
  title     = {Session-Based Recommendation with Multi-granularity User Intent and Dual-Channel Sparse Graph Attention Networks},
  author    = {Li, Pei-Xuan and Lin, Chia-Lung and Hsieh, Hsun-Ping},
  booktitle = {Advances in Knowledge Discovery and Data Mining},
  year      = {2025},
  pages     = {265--277},
  doi       = {10.1007/978-981-96-8180-8_21}
}
```

---

## License

Please add a license before public release. Common options for academic demo systems include MIT, Apache-2.0, or BSD-3-Clause. Make sure the selected license is compatible with third-party dependencies and model artifacts.
