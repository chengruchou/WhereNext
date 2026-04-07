import json

from flask import Blueprint, jsonify, request

db_bp = Blueprint("db", __name__, url_prefix="/api/db")


@db_bp.route("/fetch/<string:user_id>", methods=["GET"])
def fetch(user_id):
    with open("data/user_history.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data.get(user_id, []))


@db_bp.route("/add/<string:user_id>", methods=["POST"])
def add(user_id):
    with open("data/user_history.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    rq = request.json
    if data.get(user_id):
        data[user_id].append(rq)
    else:
        data[user_id] = [rq]
    with open("data/user_history.json", "w", encoding="utf-8") as f:
        json.dump(data, f)
    return jsonify({"message": "write succeed"})
