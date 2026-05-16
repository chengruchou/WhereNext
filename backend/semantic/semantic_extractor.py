import json
import os
import sys
import warnings

import requests

rq = requests.session()
rq.headers.update({"User-Agent": "POI_system"})

warnings.filterwarnings("ignore")

PYTHON_EXE = sys.executable
from database import POI


def extract_semantic(place_id, sessions=None):
    if sessions:  # In case you need visit history to extract semantic informations
        f"accessed {len(sessions)} visit history"
    try:
        poi = POI.query.get(place_id).to_dict()
        cat = poi["category_name"]

        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={poi['spot_latitude']}&lon={poi['spot_longitude']}"
        resp = rq.get(url, timeout=5).json()
        addr = resp.get("address", {})
        print("OSM found addr for place_id :", addr)

        return {
            "place_id": place_id,
            "semantic_information": {"cat_name": cat, "address": addr},
        }
    except Exception as e:
        print(f"Error for {place_id}: {e}")
        return {"place_id": place_id, "semantic_information": {}}


if __name__ == "main":
    from app import app

    app.app_context().push()

    data = json.load(open("temp_out_123.json"))  # retrieved pois for user_id 123
    session = data["session"]  # visit history
    predictions = data["predictions"]  # top-k retrievals

    res = {}

    for e in predictions:
        res[e["raw_location_id"]] = extract_semantic(e["raw_location_id"], session)

    with open("semantic_res.json", "w") as f:
        json.dump(res, f, indent=4)
