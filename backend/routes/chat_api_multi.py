from flask import Blueprint, jsonify, request
import time

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
    hist_ids = [e["item_id"] for e in hists]

    for single_recs in multi_recs:
        rec_ids = [e["item_id"] for e in single_recs]

        return_str = f"This is a test for \nhist : \n{hist_ids} \nrecs : \n{rec_ids}\n"

        time.sleep(5)

        hist_ids.append(rec_ids[0]) # 將第 n 次推薦的 top-1 當作下次推薦的最後一點

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
