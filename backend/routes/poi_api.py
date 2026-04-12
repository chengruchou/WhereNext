from flask import Blueprint, jsonify, request

from database import db, POI

poi_bp = Blueprint("poi", __name__, url_prefix="/api/poi")


@poi_bp.route("/", methods=["POST"])
def fetch():
    rq = request.json
    pois = POI.query.filter((POI.cat_name == rq['cat_name'])).all()
    return jsonify([e.to_dict for e in pois])