import logging

from contracts.intent import Intent, SteeringControls
from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from services.intent_parser import controls_for
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


@model_bp.route("/route/<int:user_id>", methods=["POST"])
def gen_route(user_id):
    """Run every recommendation round in one call and return the route's evidence.

    Optional body fields: "intent" (an Intent from /api/intent/parse, possibly edited)
    and "controls" (inspector override of the weights the intent implies).
    """

    payload = request.get_json(silent=True) or {}
    append_back = payload.get("append_back", [])
    service = get_recommendation_service()
    try:
        intent = Intent.model_validate(payload["intent"]) if payload.get("intent") else None
        if payload.get("controls"):
            controls = SteeringControls.model_validate(
                {**payload["controls"], "source": "inspector"}
            )
        else:
            controls = controls_for(intent, service.config)
    except ValidationError as exc:
        return jsonify({"error": f"invalid intent or controls: {exc.errors()[0]['msg']}"}), 400
    default_stops = intent.num_stops if intent else 3
    try:
        num_stops = min(max(int(payload.get("num_stops", default_stops)), 1), 5)
    except (TypeError, ValueError):
        return jsonify({"error": "num_stops must be an integer"}), 400
    try:
        rounds, evidence = service.recommend_route(
            user_id=user_id,
            append_back=append_back,
            num_stops=num_stops,
            intent=intent,
            controls=controls,
        )
        return jsonify({"rounds": rounds, "evidence": evidence.model_dump(mode="json")})
    except Exception as exc:
        logger.exception("Route endpoint failed for user_id=%s", user_id)
        return jsonify({"error": str(exc)}), 500
