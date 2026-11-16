import logging
import traceback

from flask import Blueprint, jsonify, request
from services.intent_parser import MAX_QUERY_CHARS, controls_for, get_intent_parser


logger = logging.getLogger(__name__)

intent_bp = Blueprint("intent", __name__, url_prefix="/api/intent")


@intent_bp.route("/parse", methods=["POST"])
def parse():
    """Parse a natural-language request into an Intent and the weights it implies."""

    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    if len(query) > MAX_QUERY_CHARS:
        return jsonify({"error": f"query is longer than {MAX_QUERY_CHARS} characters"}), 400
    try:
        parser = get_intent_parser()
        intent = parser.parse(query)
        controls = controls_for(intent, parser.config)
        return jsonify(
            {
                "intent": intent.model_dump(mode="json"),
                "controls": controls.model_dump(mode="json"),
            }
        )
    except Exception as exc:
        # Log where it failed, not the request or the error text, which can quote the request.
        logger.error(
            "Intent parsing failed with %s for a request of %d characters\n%s",
            type(exc).__name__,
            len(query),
            "".join(traceback.format_tb(exc.__traceback__)),
        )
        return jsonify({"error": str(exc)}), 500
