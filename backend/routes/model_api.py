import json
import os
import subprocess
import sys

PYTHON_EXE = sys.executable
from database import POI, UserHist
from flask import Blueprint, jsonify
from semantic import rerank_predictions_for_user

model_bp = Blueprint("model", __name__, url_prefix="/api/model")


@model_bp.route("/genpoi/<int:user_id>", methods=["GET"])
def gen_poi(user_id):
    histories = (
        UserHist.query.filter_by(user_id=user_id).order_by(UserHist.visit_time).all()
    )

    if not histories:
        return jsonify([])

    temp_txt = f"datasets/temp_visit_{user_id}.txt"
    temp_out = f"datasets/temp_out_{user_id}.json"

    try:
        with open(temp_txt, "w", encoding="utf-8") as f:
            for h in histories:
                poi = POI.query.get(h.poi_id)
                if not poi:
                    continue

                t_str = h.visit_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                f.write(f"{user_id} {t_str} {poi.lat} {poi.lng} {poi.id}\n")

        cmd = [
            PYTHON_EXE,
            "model_core/MG-DSGAT/src/infer_sbr.py",

            "--dataset",
            "Gowalla",

            "--checkpoint",
            "model_core/MG-DSGAT/save_model/Demo_model_exp30_Gowalla_512_seed_2023-last_k_4_best_model.pt",

            "--gowalla_visit_file",
            temp_txt,

            "--mapping_json",
            "datasets/Gowalla/raw_location2item.json",

            "--reverse_mapping_json",
            "datasets/Gowalla/item2raw_location.json",

            "--topk",
            "10",

            "--output_json",
            temp_out,
        ]

        # subprocess.run(cmd, check=True, capture_output=True, text=True)
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )

        print("=== infer_sbr stdout ===")
        print(result.stdout)
        print("=== infer_sbr stderr ===")
        print(result.stderr)

        if result.returncode != 0:
            raise RuntimeError(
                f"infer_sbr failed with code {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n\n"
                f"STDERR:\n{result.stderr}"
            )
        
        
        with open(temp_out, "r", encoding="utf-8") as f:
            data = json.load(f)
            predicts = data.get("predictions", [])

        try:
            predicts = rerank_predictions_for_user(
                user_id=user_id,
                predictions=predicts,
                histories=histories,
            )
        except Exception as rerank_error:
            print(f"Semantic reranker fallback to original SBR order: {rerank_error}")

        raw_ids = [e["raw_location_id"] for e in predicts if "raw_location_id" in e]

        pois = POI.query.filter(POI.id.in_(raw_ids)).all()
        poi_by_id = {int(poi.id): poi.to_dict() for poi in pois}
        res = [poi_by_id[raw_id] for raw_id in raw_ids if raw_id in poi_by_id]

        return jsonify(res)

    except Exception as e:
        print(f"Server Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        if os.path.exists(temp_txt): 
            os.remove(temp_txt)
        if os.path.exists(temp_out): 
            os.remove(temp_out)
