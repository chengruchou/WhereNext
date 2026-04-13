from database import POI
from flask import Blueprint, jsonify, request

poi_bp = Blueprint("poi", __name__, url_prefix="/api/poi")


@poi_bp.route("/", methods=["POST"])
def fetch():
    rq = request.json
    # pois = POI.query.filter((POI.cat_name == rq['cat_name'])).all()
    print("rq: ", rq)
    poi = POI.query.get(rq.get("id"))
    if poi is None:
        return jsonify(None)
    else:
        return jsonify(poi.to_dict())
