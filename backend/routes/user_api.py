from flask import Blueprint, jsonify, request

from database import UserHist, db

user_bp = Blueprint("user", __name__, url_prefix="/api/user")


@user_bp.route("/<int:user_id>", methods=["GET"])
def fetch(user_id):
    data = UserHist.query.get(user_id).to_dict()
    return jsonify(data)


@user_bp.route("/<string:user_id>", methods=["POST"])
def add():
    rq = request.json
    new_hist = UserHist(
        user_id=rq["user_id"], poi_id=rq["poi_id"], visit_time=rq.get("visit_time")
    )
    db.session.add(new_hist)
    db.session.commit()
    return jsonify("write succeed")
