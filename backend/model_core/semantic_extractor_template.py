import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from app import app
from database import POI


def extract_semantic(place_id, sessions=None):
    if sessions:  # In case you need visit history to extract semantic informations
        f"accessed {len(sessions)} visit history"
    ###
    ###
    # Define your extract logic below
    ###
    ###

    poi = POI.query.get(place_id).to_dict()
    cat = poi["category_name"]

    return {
        "place_id": place_id,
        "semantic_information": {
            "cat_name": cat
            # "street_name": street_name...
            # "country": country...
        },  # Apply other semantic informtaion in this dict
    }


app.app_context().push()

data = json.load(open("temp_out_123.json")) # retrieved pois for user_id 123
session = data["session"]  # visit history
predictions = data["predictions"]  # top-k retrievals

res = {}

for e in predictions:
    res[e["raw_location_id"]] = extract_semantic(e["raw_location_id"], session)

with open("semantic_res.json", "w") as f:
    json.dump(res, f, indent=4)
