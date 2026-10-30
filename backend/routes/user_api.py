from datetime import datetime

from flask import Blueprint, jsonify, request
from services import visit_store

user_bp = Blueprint("user", __name__, url_prefix="/api/user")

# The panel shows a traveler's latest visits, oldest first.
SHOWN_VISITS = 10


@user_bp.route("/<int:user_id>", methods=["GET"])
def fetch(user_id):
    data = visit_store.visits(user_id)[-SHOWN_VISITS:]
    return jsonify(
        {
            "userHist": [e.to_dict() for e in data],
            "userHistPlace": [e.to_dict()["poi_detail"] for e in data],
        }
    )


@user_bp.route("/<int:user_id>", methods=["POST"])
def add(user_id):
    rq = request.json
    visit_time = rq.get("visit_time")
    try:
        visit_store.add(
            user_id,
            int(rq["poi_id"]),
            datetime.fromisoformat(visit_time) if visit_time else None,
        )
    except visit_store.EditRefused as exc:
        return jsonify({"error": str(exc)}), 403
    return jsonify("write succeed")


@user_bp.route("/<int:user_id>", methods=["DELETE"])
def delete(user_id):
    try:
        visit_store.clear(user_id)
    except visit_store.EditRefused as exc:
        return jsonify({"error": str(exc)}), 403
    return jsonify("delete succeed")


@user_bp.route("delone/<int:log_id>", methods=["DELETE"])
def delete_one(log_id):
    try:
        visit_store.remove(log_id)
    except visit_store.EditRefused as exc:
        return jsonify({"error": str(exc)}), 403
    return jsonify("delete one succeed")
