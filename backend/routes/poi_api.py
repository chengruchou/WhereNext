from database import POI, db
from flask import Blueprint, jsonify, request
from model_core.semantic_extractor_template import extract_semantic

poi_bp = Blueprint("poi", __name__, url_prefix="/api/poi")


@poi_bp.route("/id", methods=["POST"])
def fetch_id():
    rq = request.json
    print("rq: ", rq)
    poi = POI.query.get(rq.get("id"))
    if poi is None:
        return jsonify(None)
    else:
        return jsonify([poi.to_dict()])


@poi_bp.route("/cat", methods=["POST"])
def fetch_cat():
    rq = request.json
    print("rq: ", rq)
    pois = POI.query.filter(POI.cat_name == rq.get("cat"))
    if pois is None:
        return jsonify(None)
    else:
        return jsonify([e.to_dict() for e in pois])


@poi_bp.route("/allcat", methods=["GET"])
def allcat():
    data = db.session.query(POI.cat_name).distinct().all()
    all_cat = []
    for e in data:
        if e[0]:
            all_cat.append(e[0])
    return jsonify(all_cat)


@poi_bp.route("/detail/<int:poi_id>", methods=["GET"])
def detail(poi_id):
    semantic_data = extract_semantic(poi_id, sessions=None)
    return jsonify(semantic_data)