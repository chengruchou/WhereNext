import json

import pandas as pd
from app import app
from database import POI, db
from sqlalchemy import text
from tqdm import tqdm

data = json.load(open("backend/datasets/filtered_poi_metadata.json"))
df2 = pd.DataFrame.from_dict(data, orient="index")

with app.app_context():
    db.drop_all()
    db.create_all()

    db.session.execute(text("PRAGMA synchronous = OFF;"))
    db.session.execute(text("PRAGMA journal_mode = MEMORY;"))
    db.session.execute(text("PRAGMA cache_size = -1000000;"))

    pois_to_insert = []
    BATCH_SIZE = 10000
    for poi_id, poi_data in tqdm(data.items(), total=len(data)):
        # print(poi_id, poi_data)
        poi_dict = {
            "id": int(poi_id),
            "item_id": poi_data.get("item_id"),
            "lat": poi_data.get("latitude"),
            "lng": poi_data.get("longitude"),
            "cat_name": poi_data.get("category_name"),
            "raw_data": poi_data,
        }

        pois_to_insert.append(poi_dict)

        if len(pois_to_insert) >= BATCH_SIZE:
            db.session.bulk_insert_mappings(POI, pois_to_insert)
            db.session.commit()
            pois_to_insert.clear()

    if pois_to_insert:
        db.session.bulk_insert_mappings(POI, pois_to_insert)
        db.session.commit()

with app.app_context():
    print(db.session.query(POI).count())
