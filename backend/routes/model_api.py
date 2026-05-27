import logging

from flask import Blueprint, jsonify, request
from services.recommendation_service import get_recommendation_service


logger = logging.getLogger(__name__)

model_bp = Blueprint("model", __name__, url_prefix="/api/model")


@model_bp.route("/genpoi/<int:user_id>", methods=["POST"])
def gen_poi(user_id):
    payload = request.get_json(silent=True) or {}
    append_back = payload.get("append_back", [])
    try:
        result = get_recommendation_service().recommend_for_user(
            user_id=user_id,
            append_back=append_back,
        )
        return jsonify(result)
    except Exception as exc:
        logger.exception("Recommendation endpoint failed for user_id=%s", user_id)
        return jsonify({"error": str(exc)}), 500
