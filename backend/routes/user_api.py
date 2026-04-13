from datetime import datetime

from database import UserHist, db
from flask import Blueprint, jsonify, request

user_bp = Blueprint("user", __name__, url_prefix="/api/user")


@user_bp.route("/<int:user_id>", methods=["GET"])
def fetch(user_id):
    data = UserHist.query.filter(UserHist.user_id==user_id).all()
    if data is None:
        return jsonify(None)
    return jsonify([e.to_dict() for e in data])


@user_bp.route("/<int:user_id>", methods=["POST"])
def add(user_id):
    rq = request.json
    print("rq", rq)
    new_hist = UserHist(
        user_id=user_id,
        poi_id=rq["poi_id"],
        visit_time=datetime.fromisoformat(rq.get("visit_time")),
    )
    db.session.add(new_hist)
    db.session.commit()
    return jsonify("write succeed")

@user_bp.route("/<int:user_id>", methods=["DELETE"])
def delete(user_id):
    UserHist.query.filter(UserHist.user_id == user_id).delete()
    db.session.commit()

    return jsonify("delete succeed")

@user_bp.route("delone/<int:log_id>", methods=["DELETE"])
def delete_one(log_id):
    db.session.delete(UserHist.query.get(log_id))
    db.session.commit()
    return jsonify("delete one succeed")