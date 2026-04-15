# A. Env setup

## 1. backend
```bash
cd backend
uv sync
```

## 2. frontend
```bash
cd frontend
npm install
```

---
---

# B. Files setup

## 1. to add files
- `.env`
    - path : `frontend/.env`
    - method : 手動建立
    - contnet : VITE_GOOGLE_API_KEY=AIza...

- `app.db`
    - method : 
    ```bash
    # Under backend folder
    uv run python json_to_db.py
    ```
    > should see 
    > 100%|█████████| 29511/29511 [00:00<00:00, 65331.29it/s]29511

## 2. Overall file hierachy
> exclude .env .vscode and other unnecessary folders
```bash
bpthomson@LAPTOP-1PJ0UPNO:~/POI_Frontend$ tree -I '.env|.vscode|node_modules|__pycache__|*.md'
.
├── backend
│   ├── app.py
│   ├── database.py
│   ├── datasets
│   │   ├── Gowalla
│   │   │   ├── item2raw_location.json
│   │   │   └── raw_location2item.json
│   │   ├── build_manifest.json
│   │   ├── filtered_poi_metadata.json
│   │   └── poi_metadata.json
│   ├── instance
│   │   └── app.db
│   ├── json_to_db.ipynb
│   ├── json_to_db.py
│   ├── model_core
│   │   └── MG-DSGAT
│   │       ├── LICENSE
│   │       ├── save_model
│   │       │   └── Demo_model_exp30_Gowalla_512_seed_2023-last_k_4_best_model.pt
│   │       └── src
│   │           ├── build_gowalla_dataset.py
│   │           ├── infer_sbr.py
│   │           ├── main_model_exp30.py
│   │           ├── model_exp30.py
│   │           ├── running_script.py
│   │           ├── trainer.py
│   │           └── utils.py
│   ├── pyproject.toml
│   ├── routes
│   │   ├── model_api.py
│   │   ├── poi_api.py
│   │   └── user_api.py
│   └── uv.lock
└── frontend
    ├── env.d.ts
    ├── eslint.config.js
    ├── index.html
    ├── package-lock.json
    ├── package.json
    ├── public
    │   └── favicon.ico
    ├── src
    │   ├── App.vue
    │   ├── assets
    │   │   ├── logo.png
    │   │   └── logo.svg
    │   ├── components
    │   │   ├── HistoryList.vue
    │   │   ├── MapCanvas.vue
    │   │   ├── PlaceCard.vue
    │   │   ├── SearchPanel.vue
    │   │   └── UserLogin.vue
    │   ├── main.ts
    │   ├── plugins
    │   │   ├── index.ts
    │   │   └── vuetify.ts
    │   ├── styles
    │   │   └── settings.scss
    │   └── types
    │       └── place.ts
    ├── tsconfig.app.json
    ├── tsconfig.json
    ├── tsconfig.node.json
    └── vite.config.mts

18 directories, 47 files
```
---
---

# C. Run
Start the backend API server and the frontend development server simultaneously.

## 1. Open two terminals
> 建議開 split terminal (點擊終端機右上角垃圾桶 icon 右邊的 split terminal (ctrl + shift + 5) )

## 2. In first terminal
```bash
cd backend
uv run app.py
```

## 3. In second terminal
```bash
cd frontend
npm run dev
```

## 4. Visit site http://localhost:3000/
type ctrl + c in both terminals to terminate both backend and frontend