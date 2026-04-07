from flask import Blueprint, jsonify, request
from model_core.model import fake_model

model_bp = Blueprint("model", __name__, url_prefix="/api/model")

@model_bp.route("/genpoi/<string:user_id>", methods=["GET"])
def gen_poi(user_id):
    res = fake_model(user_id)
    return jsonify(res)