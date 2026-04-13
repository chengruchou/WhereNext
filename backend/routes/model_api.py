import json
import os
import subprocess

from database import POI, UserHist
from flask import Blueprint, jsonify

model_bp = Blueprint("model", __name__, url_prefix="/api/model")


@model_bp.route("/genpoi/<int:user_id>", methods=["GET"])
def gen_poi(user_id):
    histories = (
        UserHist.query.filter_by(user_id=user_id).order_by(UserHist.visit_time).all()
    )

    if not histories:
        return jsonify([])

    temp_txt = f"datasets/tmp_visit_{user_id}.txt"
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
            "python",
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

        subprocess.run(cmd, check=True, capture_output=True, text=True)

        predicted_item_ids = []
        if os.path.exists(temp_out):
            with open(temp_out, "r", encoding="utf-8") as f:
                data = json.load(f)
                predicted_item_ids = [p["item_id"] for p in data.get("predictions", [])]

        poi_records = POI.query.filter(POI.item_id.in_(predicted_item_ids)).all()
        poi_map = {poi.item_id: poi.to_dict() for poi in poi_records}

        result = [poi_map[pid] for pid in predicted_item_ids if pid in poi_map]
        return jsonify(result)

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else e.stdout
        print("\n" + "="*50)
        print("[Model Inference Failed]")
        print(f"Command: {' '.join(e.cmd)}")
        print(f"Error Traceback:\n{error_msg}")
        print("="*50 + "\n")
        return jsonify({"error": "Model Execution Failed", "details": error_msg}), 500

    except Exception as e:
        print(f"Server Error: {str(e)}")
        return jsonify({"error": str(e)}), 500

    finally:
        if os.path.exists(temp_txt): os.remove(temp_txt)
        if os.path.exists(temp_out): os.remove(temp_out)