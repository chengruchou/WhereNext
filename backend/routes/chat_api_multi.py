from flask import Blueprint, jsonify, request
import os
from google import genai
import time
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@chat_bp.route("/explain", methods=["POST"])
def explain():
    rq = request.json
    hists = rq["hists"] # 大小為 : min(10, len(user_hist)) * 1，資料格式參照下方 30~52 行的 dict structure
    multi_recs = rq["recs"] # 大小為 : 推論次數 * 每次推論點數(5)，資料格式參照下方 30~52 行的 dict structure

    if hists == []:
        return_str = "No user history."
    elif multi_recs == []:
        return_str = "Get next POIs first."

    ### modify the code below ###
    hist_ids = [e["raw_poi_id"] for e in hists]

    # 整理 history
    hist_lines = [f"- {e['category_name']} (id:{e['raw_poi_id']})" for e in hists]

    # 每一輪只取 top-1（round[0]）組成路徑，與地圖 recRoutePoints 一致，同時維護 hist_ids
    route_lines = []
    for i, single_recs in enumerate(multi_recs):
        poi = single_recs[0]
        route_lines.append(
            f"Step {i+1}: {poi['category_name']} (id:{poi['raw_poi_id']}, "
            f"checkins:{poi['checkins_count']}, lat:{poi['latitude']:.4f}, lng:{poi['longitude']:.4f})"
        )
        hist_ids.append(poi["raw_poi_id"])

    prompt = f"""You are a travel route recommendation assistant.

    User's visited history:
    {chr(10).join(hist_lines)}

    Recommended route steps:
    {chr(10).join(route_lines)}

    Please output:
    1. For each step, one short sentence explaining why this POI is recommended.
    2. At the end, an "Overall Route Summary" paragraph (2-3 sentences) explaining why this route suits the user.

    Use ONLY the POI ids listed above. Do not invent, alter, or add any id.

    Format:
    Step 1: <category (id)>: <reason>
    Step 2: ...
    Overall Route Summary:
    <summary>
    """

    response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt
    )
    full_text = response.text

    # 以 "Overall Route Summary" 為界，拆成「逐點 top-1 原因」與「整體路徑摘要」
    marker = "Overall Route Summary"
    if marker in full_text:
        steps_part, summary_part = full_text.split(marker, 1)
        summary_part = marker + summary_part
    else:
        steps_part = ""
        summary_part = full_text

    # 逐點 top-1 推薦原因 → 只印在後端 terminal
    print("=== Top-1 推薦原因 ===")
    print(steps_part.strip())
    print("=====================")

    # 前端只顯示 Overall Route Summary
    return_str = summary_part.strip()

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

    return jsonify(return_str)
