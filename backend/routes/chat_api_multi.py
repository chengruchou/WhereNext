import os

import anthropic
from contracts.evidence import RouteEvidence
from flask import Blueprint, jsonify, request
from pydantic import ValidationError
from services import grounded_explainer
from services.intent_parser import get_intent_parser, has_credentials

_client: anthropic.Anthropic | None = None

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


def _get_client() -> anthropic.Anthropic | None:
    # Created on first use, so the backend starts without Claude credentials.
    global _client
    if _client is None:
        client = anthropic.Anthropic()
        if has_credentials(client):
            _client = client
    return _client


@chat_bp.route("/explain", methods=["POST"])
def explain():
    rq = request.json
    hists = rq[
        "hists"
    ]  # 大小為 : min(10, len(user_hist)) * 1，資料格式參照下方 30~52 行的 dict structure
    multi_recs = rq[
        "recs"
    ]  # 大小為 : 推論次數 * 每次推論點數(5)，資料格式參照下方 30~52 行的 dict structure

    if hists == []:
        return jsonify("No user history.")
    if multi_recs == []:
        return jsonify("Get next POIs first.")

    ### modify the code below ###
    hist_ids = [e["raw_poi_id"] for e in hists]

    # 整理 history
    hist_lines = [f"- {e['category_name']} (id:{e['raw_poi_id']})" for e in hists]

    # 每一輪只取 top-1（round[0]）組成路徑，與地圖 recRoutePoints 一致，同時維護 hist_ids
    route_lines = []
    for i, single_recs in enumerate(multi_recs):
        poi = single_recs[0]
        route_lines.append(
            f"Step {i + 1}: {poi['category_name']} (id:{poi['raw_poi_id']}, "
            f"checkins:{poi['checkins_count']}, lat:{poi['latitude']:.4f}, lng:{poi['longitude']:.4f})"
        )
        hist_ids.append(poi["raw_poi_id"])

    prompt = f"""You are a travel route recommendation assistant.

    User's visited history:
    {chr(10).join(hist_lines)}

    Recommended route steps:
    {chr(10).join(route_lines)}

    Please output:
    1. In the beginning, an "Overall Route Summary" paragraph (2-3 sentences) explaining why this route suits the user.
    2. Next, for each step, one short sentence explaining why this POI is recommended.

    Use ONLY the POI ids listed above. Do not invent, alter, or add any id.

    Please use **Markdown** formatting to make the output readable. 

    Format Example:
    ### Overall Route Summary
    <summary>

    **Step 1: <category>** `(<id>)`
    <reason>

    **Step 2: ...**
    ...
    """

    client = _get_client()
    if client is None:
        return jsonify("Explanations need Claude API credentials (ANTHROPIC_API_KEY)."), 503
    try:
        response = client.beta.messages.create(
            model=os.getenv("WHERENEXT_EXPLAIN_MODEL", "claude-opus-5-5"),
            max_tokens=16000,
            output_config={"effort": "low"},
            # If a safety classifier declines, the API retries on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.RateLimitError:
        return jsonify("The explanation service is busy. Try again in a moment."), 503
    except anthropic.APIStatusError as exc:
        return jsonify(f"The explanation request failed (HTTP {exc.status_code})."), 502
    except anthropic.AnthropicError:
        return jsonify("Explanations need Claude API credentials and a network connection."), 503
    if response.stop_reason == "refusal":
        return jsonify("No explanation was generated for this route.")
    full_text = "".join(block.text for block in response.content if block.type == "text")

    # # 以 "Overall Route Summary" 為界，拆成「逐點 top-1 原因」與「整體路徑摘要」
    # marker = "Overall Route Summary"
    # if marker in full_text:
    #     steps_part, summary_part = full_text.split(marker, 1)
    #     summary_part = marker + summary_part
    # else:
    #     steps_part = ""
    #     summary_part = full_text

    # # 逐點 top-1 推薦原因 → 只印在後端 terminal
    # print("=== Top-1 推薦原因 ===")
    # print(steps_part.strip())
    # print("=====================")

    # # 前端只顯示 Overall Route Summary
    # return_str = summary_part.strip()

    ### Place dict structure ###
    # print(hists[0])
    # {
    #     "category_id": 95,
    #     "category_name": "Train Station",
    #     "checkins_count": 794,
    #     "checkins_count_from_events": 56,
    #     "created_at": "2009-11-11T05:07:48Z",
    #     "highlights_count": 1,
    #     "item_id": 3558,
    #     "items_count": 10,
    #     "latitude": 35.6983968045,
    #     "longitude": 139.773055315,
    #     "max_items_count": 10,
    #     "photos_count": 12,
    #     "radius_meters": 75,
    #     "raw_categories": [{"name": "Train Station", "url": "/categories/95"}],
    #     "raw_poi_id": 92728,
    #     "spot_latitude": 35.6983968045,
    #     "spot_longitude": 139.773055315,
    #     "users_count": 267,
    #     "users_count_from_events": 34,
    # }

    ### modify the code above ###

    # print(full_text)

    return jsonify(full_text)


@chat_bp.route("/grounded", methods=["POST"])
def grounded():
    """Explain a route from its evidence; every sentence is checked against what it cites."""

    payload = request.get_json(silent=True) or {}
    try:
        evidence = RouteEvidence.model_validate(payload.get("evidence"))
    except ValidationError as exc:
        return jsonify({"error": f"invalid evidence: {exc.errors()[0]['msg']}"}), 400
    if not evidence.steps:
        return jsonify("Get next POIs first.")

    client = _get_client()
    if client is None:
        return jsonify("Explanations need Claude API credentials (ANTHROPIC_API_KEY)."), 503
    evidence_json = grounded_explainer.evidence_for_prompt(evidence)
    try:
        response = grounded_explainer.request_explanation(client, evidence_json)
    except anthropic.RateLimitError:
        return jsonify("The explanation service is busy. Try again in a moment."), 503
    except anthropic.APIStatusError as exc:
        return jsonify(f"The explanation request failed (HTTP {exc.status_code})."), 502
    except (anthropic.AnthropicError, ValidationError):
        return jsonify("Explanations need Claude API credentials and a network connection."), 503
    if response.stop_reason == "refusal" or response.parsed_output is None:
        return jsonify("No explanation was generated for this route.")

    categories = get_intent_parser().vocabulary().names
    verified, markdown = grounded_explainer.explain(
        response.parsed_output, evidence_json, categories
    )
    return jsonify(
        {
            "markdown": markdown,
            "explanation": verified.model_dump(mode="json"),
            "model": response.model,
        }
    )
